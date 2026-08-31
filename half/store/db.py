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

from half.errors import StoreError
from half.store.fold import State
from half.text import index_text, terms

logger = logging.getLogger(__name__)

#: Builds the indexed contextual prefix for one belief. Injected rather than
#: imported: the prefix is retrieval's idea, and ``half.store`` may not depend
#: on ``half.retrieval`` — the arrow runs the other way and reversing it would
#: close a cycle between the two.
PrefixFn = Callable[[Mapping[str, Any]], str]

#: Shape of the derived view. Bumped whenever a column or an FTS table changes.
#: SQLite here is derived and disposable (AD-3), so a mismatch is resolved by
#: discarding it and replaying the log — never by an in-place migration, which
#: would be a second way for derived state to exist that the log does not
#: describe.
DERIVED_VERSION: Final[int] = 3

#: Every object this module owns, in an order safe to drop: the FTS table
#: references ``beliefs`` as its external content.
_TABLES: Final[tuple[str, ...]] = (
    "belief_fts", "beliefs", "tensions", "loops", "expunged",
)

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
    license      TEXT NOT NULL DEFAULT 'behave',
    independent  INTEGER NOT NULL DEFAULT 0,
    data         TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS tensions (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS loops    (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS expunged (id TEXT PRIMARY KEY) STRICT;

-- Indexes the *terms* columns rather than the raw text, because a script
-- written without word spaces arrives as one unicode61 token and is then
-- findable only by the whole sentence. ``half.text.index_text`` expands such a
-- run into its n-grams, and the query builder below expands a query the same
-- way — an index n-grammed on one side only is worse than the defect it
-- replaces. The raw ``claim`` and ``prefix`` columns stay beside them: a caller
-- reads a belief's own words from those, never from what the index holds.
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
    for table in ("beliefs", "tensions", "loops", "expunged"):
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
    unspaced sentence finds it. Text past the tokenizer's growth ceiling raises
    ``TokenGrowthLimitError`` rather than being indexed in part — which is why
    ``Store.append`` refuses such a record before it reaches the log, so this
    build can never write a line it would then be unable to rebuild.
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
        for table in ("beliefs", "tensions", "loops", "expunged"):
            conn.execute(f"DELETE FROM {table}")

        for ident, data in state.beliefs.items():
            claim = _text_or_none(data.get("claim"))
            belief_prefix = _prefix_of(data, ident, prefix)
            conn.execute(
                "INSERT INTO beliefs (id, t, subject, claim, prefix,"
                " claim_terms, prefix_terms, ledger,"
                " license, independent, data) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    _require_str(data, "t", ident, default=""),
                    _text_or_none(data.get("subject")),
                    claim,
                    belief_prefix,
                    index_text(claim) or None,
                    index_text(belief_prefix) or None,
                    _text_or_none(data.get("ledger")),
                    _require_str(data, "license", ident, default="behave"),
                    _require_int(data, "independent", ident),
                    json.dumps(data, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False),
                ),
            )
        for ident, data in state.tensions.items():
            conn.execute("INSERT INTO tensions (id, data) VALUES (?,?)",
                         (ident, _dump(data)))
        for ident, data in state.loops.items():
            conn.execute("INSERT INTO loops (id, data) VALUES (?,?)",
                         (ident, _dump(data)))
        for ident in sorted(state.expunged):
            conn.execute("INSERT INTO expunged (id) VALUES (?)", (ident,))

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
    for row in conn.execute("SELECT id FROM expunged ORDER BY id"):
        state.expunged.add(row["id"])
    return state


def search(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """BM25-ranked search over claim text and contextual prefix.

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
            "SELECT id, claim, prefix, data, NULL AS score FROM beliefs ORDER BY id"
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

    Two further consequences, both wanted:

    * FTS5 operator characters cannot survive tokenization, so ``NEAR(`` and an
      unbalanced quote are ordinary input rather than syntax.
    * ``half.text.terms`` is the same expansion applied to what goes *into* the
      index, so an unspaced run is n-grammed identically on both sides and the
      two cannot drift apart.

    Which beliefs contain these words is the store's question; how much each
    match is worth is ranking policy, and that lives in ``half.retrieval``.

    Raises ``TokenGrowthLimitError`` for a query past the tokenizer's ceiling,
    rather than searching on a silently shortened one.
    """
    return " OR ".join(f'"{term}"' for term in terms(query))


def _search(
    conn: sqlite3.Connection, query: str, limit: int | None, columns: str
) -> list[dict[str, Any]]:
    if limit is not None:
        limit = max(0, int(limit))
        if limit == 0:
            return []
    expression = _match_expression(query)
    if not expression:
        return []
    try:
        return _run_search(conn, expression, limit, columns)
    except sqlite3.Error as exc:
        raise StoreError(f"search failed: {exc}") from exc


def _run_search(
    conn: sqlite3.Connection, query: str, limit: int | None, columns: str
) -> list[dict[str, Any]]:
    sql = (
        f"SELECT {columns}, bm25(belief_fts) AS score"
        " FROM belief_fts JOIN beliefs b ON b.rowid = belief_fts.rowid"
        " WHERE belief_fts MATCH ? ORDER BY score, b.id"
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
