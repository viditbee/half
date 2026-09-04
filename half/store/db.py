"""SQLite: the materialized fold plus the FTS5 index (AD-3, AD-5).

Entirely derived. Delete this file and rebuild it from the log — that is the
replay invariant (AD-4), and it is a test rather than a promise.

Retrieval runs on FTS5 ``bm25()``, which ships in the standard library's
sqlite3. No vector service and no reranker in the hot path (AD-5): the mission
requires this to run on a self-hoster's cheap box.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

from half.errors import QueryTooLargeError, StoreError, TokenGrowthLimitError
from half.store.fold import State
from half.store.records import underived
from half.text import index_text, phrases

logger = logging.getLogger(__name__)

#: Builds the indexed contextual prefix for one belief. Injected rather than
#: imported: the prefix is retrieval's idea, and ``half.store`` may not depend
#: on ``half.retrieval`` — the arrow runs the other way and reversing it would
#: close a cycle between the two.
PrefixFn = Callable[[Mapping[str, Any]], str]

#: The keys the ``governance`` table holds. Both are folded state that belongs
#: to the main rather than to any one belief.
CEILING_KEY: Final[str] = "ceiling"
CRISIS_KEY: Final[str] = "crisis"
AFTERCARE_KEY: Final[str] = "aftercare"
SCHEDULE_KEY: Final[str] = "schedule"
SPOKE_KEY: Final[str] = "spoke"

#: Shape of the derived view. Bumped whenever a column or an FTS table changes.
#: SQLite here is derived and disposable (AD-3), so a mismatch is resolved by
#: discarding it and replaying the log — never by an in-place migration, which
#: would be a second way for derived state to exist that the log does not
#: describe.
#:
#: v12 added the ``underived`` column, which is **the retrieval door's whole
#: enforcement** (CAP-5, story 15a). A message is evidence and not a belief, and
#: the two functions below that hand beliefs up to ``half.retrieval`` exclude it
#: in SQL rather than leaving each consumer to filter — story 10's lesson, and
#: the only version of a rule like this that has held here. A v11 view surviving
#: the upgrade would have no column to exclude on, so every rebuild would raise
#: on a missing column; discarding and replaying costs one rebuild and is what
#: makes the derived view disposable (AD-3).
#:
#: v11 reshaped what story 10 added: the ``last_touch`` row became ``spoke``,
#: which holds the newest **day marker** rather than the newest raise of any
#: loop. A v10 view surviving the upgrade would have no ``spoke`` row at all
#: and would read every main as never having spoken — a second unprompted
#: message on a day one was already sent, produced by the derived store rather
#: than by the log. Discard and replay (AD-3).
#:
#: v10 added the ``touches`` table and story 10's governance row. A view built
#: by v9 has nowhere to put either, so a stale one surviving the upgrade would
#: report every loop as never raised — the nagging bound answering *yes* for
#: the whole population.
#:
#: v9 changed the fold's **tension** semantics (story 9c), and the bump is not
#: optional even though no table changed. Two things moved at once: a tension
#: record is now merged over the tension it names rather than replacing it, and
#: a correction to either of a tension's two entries resolves that tension in
#: place. A v8 view surviving the upgrade would therefore hold tensions still
#: reading `fresh` over entries the main has already retracted — so the nightly
#: pass would keep computing drift between a live claim and a deleted one, and
#: the morning surface would reach for it. A derived view that disagrees with
#: the log about which disagreements are still open is exactly what AD-3 says
#: to discard and replay.
#:
#: v8 added the ``schedule`` row (story 9a). A view built by v7 has no place to
#: put a due time, so a stale one surviving the upgrade would report every main
#: as never scheduled — and the scheduler would reschedule the whole population
#: at once, which is the herd AD-9 exists to prevent, produced by the derived
#: store rather than by the log.
#:
#: v7 added ``expunged_loops`` (story 8), and the bump is not optional for a
#: reason a new *table* makes obvious but which would hold even without one:
#: the fold's loop semantics changed. A view built by v6 recorded an expunged
#: loop in the shared ``expunged`` set, where the new transition guard does not
#: look — so a stale view surviving the upgrade would have a main's ranking
#: function disagree with their own log about which wantings are still open.
DERIVED_VERSION: Final[int] = 12

#: Every object this module owns, in an order safe to drop: the FTS table
#: references ``beliefs`` as its external content.
_TABLES: Final[tuple[str, ...]] = (
    "belief_fts", "beliefs", "tensions", "loops", "expunged", "expunged_loops",
    "governance", "touches",
)

#: There is deliberately no ``license`` column. One existed, materialized from
#: the record's stated field, and it was a second opinion: since story 5a a
#: belief stating `assert` without a receipt *resolves* to `ask`, and a column
#: reading `assert` beside it is the disagreement this story exists to remove.
#: Nothing read it. The rung a belief is on is answered in exactly one place —
#: ``half.context.build.resolve`` — from the record in ``data``, under the
#: actor's ceiling, which is not a property of a belief and could not live in a
#: belief row anyway.
SCHEMA = """
CREATE TABLE IF NOT EXISTS beliefs (
    id           TEXT PRIMARY KEY,
    t            TEXT NOT NULL,
    subject      TEXT,
    claim        TEXT,
    prefix       TEXT,
    claim_terms  TEXT,
    prefix_terms TEXT,
    ledger       TEXT,
    independent  INTEGER NOT NULL DEFAULT 0,
    -- Whether this record is a message the main sent rather than a claim
    -- (CAP-5, story 15a). A materialized column and not a read of ``data``,
    -- because it is what the two retrieval doors below filter on and a filter
    -- that has to parse JSON per row is one somebody moves back out of SQL.
    -- Defaults to 0, which is *a claim*: the direction that never silently
    -- excludes, and the same reading ``records.underived`` gives an absent
    -- mark.
    underived    INTEGER NOT NULL DEFAULT 0,
    data         TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS tensions (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS loops    (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS expunged (id TEXT PRIMARY KEY) STRICT;

-- Loops the main erased, kept apart from the beliefs and tensions they erased
-- (CAP-6). One shared table was a demotion wearing another name: a belief
-- whose id collided with a loop's slug froze that loop's future transitions
-- for ever. See ``State.expunged_loops``.
CREATE TABLE IF NOT EXISTS expunged_loops (id TEXT PRIMARY KEY) STRICT;

-- Folded governance state that belongs to the main rather than to any one
-- belief: the license ceiling (AD-28), whether the crisis mode is open, and
-- where the aftercare conversation got to (CAP-12). Derived and disposable
-- like every other table here — the authority is the ``ceiling``, ``crisis``
-- and ``aftercare`` ops in the log.
CREATE TABLE IF NOT EXISTS governance (key TEXT PRIMARY KEY, value TEXT) STRICT;

-- What Half raised and when, one row per loop (CAP-8). Keyed by the loop's own
-- slug rather than by the append's id, because the question is always "when did
-- Half last raise this wanting?". Kept apart from ``loops`` for the reason
-- ``expunged_loops`` is kept apart from ``expunged``: a raise written into the
-- loop row would be Half's own attention indistinguishable from the main's
-- progress, and every ranking function above reads that row.
CREATE TABLE IF NOT EXISTS touches (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;

-- Indexes the *terms* columns rather than the raw text, because a script
-- written without word spaces arrives as one unicode61 token and is then
-- findable only by the whole sentence. ``half.text.index_text`` cuts such a run
-- into grapheme clusters, and ``_match_expression`` quotes the same clusters as
-- a phrase — one expansion, used on both sides, or the index and the query
-- drift apart and the fix is worse than the defect. The raw ``claim`` and
-- ``prefix`` columns stay beside them and are the only ones a caller reads: a
-- search result carries the belief's own words, never index text.
CREATE VIRTUAL TABLE IF NOT EXISTS belief_fts USING fts5(
    claim_terms,
    prefix_terms,
    content = 'beliefs',
    content_rowid = 'rowid'
);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 5000")
    _discard_if_stale(conn)
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {DERIVED_VERSION}")
    path.chmod(0o600)  # holds a full copy of every claim
    return conn


def _discard_if_stale(conn: sqlite3.Connection) -> None:
    """Drop a derived view whose shape this build no longer writes.

    Nothing is lost: the log is the only authority and the caller rebuilds from
    it. Leaving an older shape in place would instead make every future rebuild
    raise on a missing column, forever, with "delete half.db" as the only cure —
    a derived store that has to be repaired by hand is not disposable.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == DERIVED_VERSION:
        return
    with conn:
        for table in _TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")


def is_empty(conn: sqlite3.Connection) -> bool:
    """True when the derived view holds nothing — fresh, or just discarded."""
    for table in ("beliefs", "tensions", "loops", "expunged", "expunged_loops",
                  "governance"):
        if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
            return False
    return True


def rebuild(
    conn: sqlite3.Connection, state: State, *, prefix: PrefixFn | None = None
) -> None:
    """Replace the whole derived view with ``state``.

    Wholesale rather than incremental on purpose: an incremental writer is how
    a derived store starts accumulating rows that exist nowhere in the log.

    ``prefix`` regenerates the indexed contextual prefix for every belief on
    every rebuild, so the prefix column is as derived and disposable as the row
    it sits in. Omitting it leaves the column NULL — the FTS index is then claim
    text only, which is correct but loses prefix hits.

    The ``*_terms`` columns hold what the index actually reads: the same text
    expanded by ``half.text.index_text``, so a query for a word inside an
    unspaced sentence finds it. ``Store.append`` refuses a record past the
    tokenizer's ceiling before it reaches the log, so this build never writes a
    line it would then be unable to rebuild — but a rebuild must survive text
    that got past that guard anyway, and two ways exist. A log written before
    the ceiling existed is one. A *prefix* assembled from three fields that were
    each legal alone is the other, and it is not preventable at append time
    because the prefix builder is injected. So each column degrades on its own,
    exactly as ``_prefix_of`` does and for the same reason: this runs inside the
    rebuild that follows an append, the log line is already durable by then, and
    a raise here would abort every later rebuild forever with the offending line
    unremovable. The belief stays in the fold and stays reachable through the
    retrieval backstop (AD-24); only its term index is missing, and a warning
    records that rather than leaving it silent.
    """
    with conn:
        # FTS5's own reset command, not ``DELETE FROM belief_fts``. This is an
        # external-content index: a plain DELETE re-reads ``beliefs`` to work
        # out which tokens to remove, so it raises "database disk image is
        # malformed" the moment the index and the content table disagree —
        # which they legitimately do, because a belief with neither claim nor
        # prefix is never indexed. ``delete-all`` discards the index outright
        # and consults nothing.
        conn.execute("INSERT INTO belief_fts(belief_fts) VALUES('delete-all')")
        for table in ("beliefs", "tensions", "loops", "expunged",
                      "expunged_loops", "governance", "touches"):
            conn.execute(f"DELETE FROM {table}")

        for ident, data in state.beliefs.items():
            claim = _text_or_none(data.get("claim"))
            belief_prefix = _prefix_of(data, ident, prefix)
            conn.execute(
                "INSERT INTO beliefs (id, t, subject, claim, prefix,"
                " claim_terms, prefix_terms, ledger,"
                " independent, underived, data) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    _require_str(data, "t", ident, default=""),
                    _text_or_none(data.get("subject")),
                    claim,
                    belief_prefix,
                    _terms_of(claim, ident, "claim"),
                    _terms_of(belief_prefix, ident, "prefix"),
                    _text_or_none(data.get("ledger")),
                    _require_int(data, "independent", ident),
                    # The mark, read through ``records.underived`` rather than
                    # off the field, so the store and every other reader of it
                    # give one answer to *is this a message?* rather than five.
                    1 if underived(data) else 0,
                    json.dumps(data, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False),
                ),
            )
        if state.ceiling is not None:
            conn.execute("INSERT INTO governance (key, value) VALUES (?,?)",
                         (CEILING_KEY, state.ceiling))
        if state.crisis is not None:
            conn.execute("INSERT INTO governance (key, value) VALUES (?,?)",
                         (CRISIS_KEY, _dump(state.crisis)))
        if state.aftercare is not None:
            conn.execute("INSERT INTO governance (key, value) VALUES (?,?)",
                         (AFTERCARE_KEY, _dump(state.aftercare)))
        if state.schedule is not None:
            conn.execute("INSERT INTO governance (key, value) VALUES (?,?)",
                         (SCHEDULE_KEY, _dump(state.schedule)))
        if state.spoke is not None:
            conn.execute("INSERT INTO governance (key, value) VALUES (?,?)",
                         (SPOKE_KEY, _dump(state.spoke)))
        for ident, data in state.tensions.items():
            conn.execute("INSERT INTO tensions (id, data) VALUES (?,?)",
                         (ident, _dump(data)))
        for ident, data in state.loops.items():
            conn.execute("INSERT INTO loops (id, data) VALUES (?,?)",
                         (ident, _dump(data)))
        for ident, data in state.touches.items():
            conn.execute("INSERT INTO touches (id, data) VALUES (?,?)",
                         (ident, _dump(data)))
        for ident in sorted(state.expunged):
            conn.execute("INSERT INTO expunged (id) VALUES (?)", (ident,))
        for ident in sorted(state.expunged_loops):
            conn.execute("INSERT INTO expunged_loops (id) VALUES (?)", (ident,))

        conn.execute(
            "INSERT INTO belief_fts(rowid, claim_terms, prefix_terms)"
            " SELECT rowid, claim_terms, prefix_terms FROM beliefs"
            " WHERE claim_terms IS NOT NULL OR prefix_terms IS NOT NULL"
        )


def read_state(conn: sqlite3.Connection) -> State:
    """Read the derived view back as a ``State``.

    Ordered explicitly so the result is deterministic — the replay test
    compares canonical JSON of this against the in-memory fold.
    """
    state = State()
    for row in conn.execute("SELECT id, data FROM beliefs ORDER BY id"):
        state.beliefs[row["id"]] = json.loads(row["data"])
    for row in conn.execute("SELECT id, data FROM tensions ORDER BY id"):
        state.tensions[row["id"]] = json.loads(row["data"])
    for row in conn.execute("SELECT id, data FROM loops ORDER BY id"):
        state.loops[row["id"]] = json.loads(row["data"])
    for row in conn.execute("SELECT id, data FROM touches ORDER BY id"):
        state.touches[row["id"]] = json.loads(row["data"])
    for row in conn.execute("SELECT id FROM expunged ORDER BY id"):
        state.expunged.add(row["id"])
    for row in conn.execute("SELECT id FROM expunged_loops ORDER BY id"):
        state.expunged_loops.add(row["id"])
    row = conn.execute("SELECT value FROM governance WHERE key = ?",
                       (CEILING_KEY,)).fetchone()
    state.ceiling = row["value"] if row is not None else None
    row = conn.execute("SELECT value FROM governance WHERE key = ?",
                       (CRISIS_KEY,)).fetchone()
    state.crisis = json.loads(row["value"]) if row is not None else None
    row = conn.execute("SELECT value FROM governance WHERE key = ?",
                       (AFTERCARE_KEY,)).fetchone()
    state.aftercare = json.loads(row["value"]) if row is not None else None
    row = conn.execute("SELECT value FROM governance WHERE key = ?",
                       (SCHEDULE_KEY,)).fetchone()
    state.schedule = json.loads(row["value"]) if row is not None else None
    row = conn.execute("SELECT value FROM governance WHERE key = ?",
                       (SPOKE_KEY,)).fetchone()
    state.spoke = json.loads(row["value"]) if row is not None else None
    return state


def search(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """BM25-ranked search over the claim's terms and the contextual prefix's.

    Lower bm25() is a better match. The query is a main's own words, so FTS5
    operator characters are ordinary input rather than syntax: each word is
    quoted as a phrase and the words are OR'd. A sqlite error is translated to
    a ``StoreError`` — nothing here leaks a bare sqlite3 exception to a caller.

    Column weighting is deliberately left at FTS5's default. How much a prefix
    hit is worth relative to a claim hit is ranking policy, and ranking policy
    lives above the store in ``half.retrieval`` (AD-5).
    """
    return _search(conn, query, limit, "b.id, b.claim")


def search_beliefs(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    """``search`` plus everything ranking needs: prefix and the folded belief.

    A separate function rather than a wider ``search`` so the narrow one keeps
    its narrow contract; this is the retrieval layer's read door.

    Deliberately **unbounded**, like ``all_beliefs``. A ``LIMIT`` here is a cap
    ordered by bm25, and the story requires any bound on how many beliefs a
    turn scores to be ordered by salience and announced in the result. Neither
    is expressible in this query, so the whole matching set is handed up and
    ``half.retrieval`` does the bounding where salience is computable.
    """
    return _decode(_search(conn, query, None, "b.id, b.claim, b.prefix, b.data"))


def all_beliefs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every belief, id-ordered, with ``score`` absent.

    The backstop behind a query that matches no term, and deliberately
    **unbounded**. An earlier version carried ``ORDER BY id LIMIT 500``, which
    is a silent cap ordered by an accident of identifier assignment: past five
    hundred beliefs a main's oldest ids won every backstop and the rest were
    invisible, with nothing in the result saying so.

    Choosing which beliefs matter is ranking policy and does not belong in the
    store, so the whole set is returned and ``half.retrieval`` bounds it by
    salience and annotates the truncation. Id order here is an arbitrary but
    stable read order, not a ranking.
    """
    try:
        rows = conn.execute(
            "SELECT id, claim, prefix, data, NULL AS score FROM beliefs"
            # The backstop is the *other* half of the door, and it is the half
            # that matters more: a query matching no term ranks everything, so
            # without this every message the main ever sent would arrive in the
            # candidate set of every topic switch (CAP-5, story 15a).
            " WHERE underived = 0 ORDER BY id"
        ).fetchall()
    except sqlite3.Error as exc:
        raise StoreError(f"belief scan failed: {exc}") from exc
    return _decode([dict(row) for row in rows])


def read_loops(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """The loop projection alone, without folding the whole belief set."""
    try:
        rows = conn.execute("SELECT id, data FROM loops ORDER BY id").fetchall()
    except sqlite3.Error as exc:
        raise StoreError(f"loop read failed: {exc}") from exc
    return {row["id"]: json.loads(row["data"]) for row in rows}


def _match_expression(query: str) -> str:
    """A main's own words as an FTS5 MATCH expression, or ``""``.

    **Phrases inside a word, OR between words.** Each term is quoted, and quotes
    make it a *phrase*: FTS5 re-splits it with the same tokenizer it used on the
    indexed text, so however ``unicode61`` shatters a word, the query and the
    index shatter it alike and match. That is what restores precision for every
    combining-mark script — ``"रात"`` is the two-token phrase र-then-त, which
    ``यात्रा`` does not contain, while the earlier OR of the shattered pieces
    matched almost any Devanagari string. The OR stays *between* words, because a
    whole sentence must still retrieve a belief sharing any one of its words;
    quoting the sentence as a single phrase meant a conversational turn matched
    only a belief repeating it verbatim, which is never.

    The same quoting is what makes a word in an unspaced script match as a word:
    ``half.text.phrases`` cuts such a run into the grapheme clusters the index
    stores, and the phrase then matches only where those clusters are adjacent.
    ``転職`` is 転-then-職, which ``退職金の話をした`` does not contain. OR-ing the
    clusters instead — which an earlier version did, along with their 2- and
    3-grams — meant one shared character retrieved anything, and that is the
    ``रात``-matches-travel defect one script over.

    Two further consequences, both wanted:

    * FTS5 operator characters and operator *words* cannot survive quoting, so
      ``NEAR(`` and a bare capitalised ``NOT`` are ordinary input rather than
      syntax. Unquoted, ``NOT sure about the paragliders`` is an fts5 syntax
      error that reaches the main as silence.
    * ``half.text.index_text`` is the join of exactly these phrases, so the two
      sides of the index cannot drift apart.

    Which beliefs contain these words is the store's question; how much each
    match is worth is ranking policy, and that lives in ``half.retrieval``.

    Raises ``TokenGrowthLimitError`` for a query past the tokenizer's ceiling,
    rather than searching on a silently shortened one. ``_search`` translates it
    to a ``QueryTooLargeError`` so that nothing but a typed store fault crosses
    the module boundary — and to one the turn path can tell apart from an index
    that is genuinely unavailable.
    """
    return " OR ".join(f'"{phrase}"' for phrase in phrases(query))


def _search(
    conn: sqlite3.Connection, query: str, limit: int | None, columns: str
) -> list[dict[str, Any]]:
    if limit is not None:
        limit = max(0, int(limit))
        if limit == 0:
            return []
    try:
        expression = _match_expression(query)
    except TokenGrowthLimitError as exc:
        # Typed at the boundary, like every other fault this module can meet.
        # A caller catching StoreError must not additionally have to know that
        # the tokenizer exists.
        raise QueryTooLargeError(
            f"query exceeds the tokenizer budget: {exc}"
        ) from exc
    if not expression:
        return []
    try:
        return _run_search(conn, expression, limit, columns)
    except sqlite3.Error as exc:
        raise StoreError(f"search failed: {exc}") from exc


def _run_search(
    conn: sqlite3.Connection, query: str, limit: int | None, columns: str
) -> list[dict[str, Any]]:
    # ``b.underived = 0`` is **the door** (CAP-5, story 15a). A message the main
    # sent is evidence and not a belief, so it never leaves the store as one:
    # not to retrieval, not to the context builder that is fed from retrieval's
    # result, and not to the ladder that resolves a rung over it. Enforced in the
    # query rather than by a filter each of those applies — story 10's lesson,
    # and the reason it sits on the shared search rather than only on
    # ``search_beliefs``: a second read door that still returned messages is
    # exactly the hole this project keeps finding.
    #
    # The **fold** is untouched, deliberately. ``read_state`` returns every
    # record, because the three subsystems that read a message read it there:
    # the language sample (``half.voice.compose.sample_from``), responsiveness
    # (``half.questions.answered``) and the correction aim's exclusion. What a
    # message stops being is something Half *ranks*, not something Half keeps.
    sql = (
        f"SELECT {columns}, bm25(belief_fts) AS score"
        " FROM belief_fts JOIN beliefs b ON b.rowid = belief_fts.rowid"
        " WHERE belief_fts MATCH ? AND b.underived = 0 ORDER BY score, b.id"
    )
    params: tuple[Any, ...] = (query,)
    if limit is not None:
        sql += " LIMIT ?"
        params += (limit,)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _decode(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace each row's stored JSON with the belief it encodes."""
    for row in rows:
        row["belief"] = json.loads(row.pop("data"))
    return rows


def _prefix_of(
    data: dict[str, Any], ident: str, prefix: PrefixFn | None
) -> str | None:
    """The indexed prefix for one belief, or ``None`` if it cannot be built.

    Degrades rather than raises, and that is the whole point. The prefix is
    an injected callable, it runs inside the rebuild that follows an append,
    and the append has already made the log line durable by then. A builder
    that raises on one belief would therefore abort every rebuild and every
    subsequent append *forever*, with the offending line unremovable — exactly
    the failure ``Store.append``'s pre-append validation exists to prevent,
    reappearing one layer down. Losing a prefix hit is the smaller loss by a
    wide margin.
    """
    if prefix is None:
        return None
    try:
        value = prefix(data)
    except Exception as exc:  # noqa: BLE001 - an index hint is never fatal
        # The belief id only. Never the claim (AD-22).
        logger.warning(
            "prefix builder raised %s for belief %s; indexing claim text only",
            type(exc).__name__, ident,
        )
        return None
    if not isinstance(value, str):
        logger.warning(
            "prefix builder returned %s for belief %s; indexing claim text only",
            type(value).__name__, ident,
        )
        return None
    return value or None


def _terms_of(text: str | None, ident: str, column: str) -> str | None:
    """The indexed term text for one column, or ``None`` if it cannot be built.

    Degrades rather than raises — see ``rebuild``. Never logs the text itself,
    only which belief and which column (AD-22).
    """
    if text is None:
        return None
    try:
        return index_text(text) or None
    except TokenGrowthLimitError as exc:
        logger.warning(
            "belief %s %s exceeds the tokenizer budget (%s); leaving it out of "
            "the term index, still reachable through the backstop",
            ident, column, exc,
        )
        return None


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _require_str(data: dict[str, Any], key: str, ident: str, *, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise StoreError(
            f"belief {ident!r} field {key!r} must be a string, "
            f"got {type(value).__name__}"
        )
    return value


def _require_int(data: dict[str, Any], key: str, ident: str) -> int:
    """Raise a StoreError rather than a bare ValueError.

    Records are validated before append now, so this should be unreachable for
    anything this build wrote — but a log written by another build must still
    fail as a domain error rather than as an uncaught ValueError.
    """
    value = data.get(key, 0)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise StoreError(
            f"belief {ident!r} field {key!r} must be an int, "
            f"got {type(value).__name__}"
        )
    return value
