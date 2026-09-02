"""The ``Store`` façade: one main, one directory, one writer (AD-1).

Layout, per main:

    <root>/
      beliefs/YYYY-MM.jsonl   append-only — the only source of truth
      half.db                 SQLite: materialized fold + FTS5 index (disposable)

Credentials are deliberately absent: they live outside every layer the main can
export or replay (AD-11). Nothing in this module reads or writes a secret.

Single-writer is an in-process invariant here — this instance owns the append
path. Cross-process exclusion belongs to the supervisor that decides which node
owns a main, not to the store. (A lock file would need human sign-off per the
story's Ask First rule, and would duplicate an exclusion the actor model
already provides.)

Layer 1 lives in ``half.store.sources`` and holds receipts rather than message
bodies (AD-13). The projection renderer (AD-31) is still deferred.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Self

from half.errors import TensionError
from half.loops import ledger
from half.store import db
from half.store.fold import State, fold
from half.store.log import BeliefLog
from half.store.ops import Op
from half.store.records import (
    BETWEEN,
    RESERVED,
    TARGET,
    Record,
    make,
    validate_fields,
)

BELIEFS_DIR = "beliefs"
DB_NAME = "half.db"


class Store:
    """Owns one main's directory."""

    def __init__(self, root: Path | str, *, prefix: db.PrefixFn | None = None) -> None:
        self.root = Path(root)
        # 0700: the tree holds every claim Half has about one person.
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.log = BeliefLog(self.root / BELIEFS_DIR)
        # Injected, never imported: the contextual prefix is retrieval's idea
        # and ``half.store`` may not depend on ``half.retrieval``. A store built
        # without one indexes claim text only — correct, minus prefix hits.
        self._prefix = prefix
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def db_path(self) -> Path:
        return self.root / DB_NAME

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = db.connect(self.db_path)
            if db.is_empty(self._conn):
                # Either a first open, where this costs nothing, or a derived
                # view this build's schema discarded. Replaying is the whole
                # point of the log being the authority (AD-3, AD-4) — an
                # upgrade must not leave a main with an empty index and no
                # signal that anything happened.
                self.rebuild()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- write ---------------------------------------------------------------

    def append(self, record: Record) -> None:
        """Append one record and refresh the derived view.

        Validated first. The log is append-only, so a record the derived view
        cannot materialize would otherwise be durable, and every later rebuild
        would raise forever with no path back.

        The op travels with the fields because some of them mean different
        things under different ops: ``state`` names one of four closed
        vocabularies depending on whether the record is a tension, a crisis
        entry, an aftercare answer or a loop transition, and a check that did
        not know which would have to accept the union of all four (CAP-6).
        """
        validate_fields(
            {k: v for k, v in record.data.items() if k not in RESERVED},
            op=record.op,
        )
        if record.op is Op.TENSION:
            self._require_pair(record)
        self.log.append(record)
        self.rebuild()

    def _require_pair(self, record: Record) -> None:
        """A tension's **first** record must name the two entries it links.

        *"A tension is the record of two entries that disagree"* (glossary) was
        the one part of the definition nothing enforced.
        ``validate_tension_fields`` cannot: it sees fields and not the log, so
        it cannot tell a mint from a transition, and it therefore has to treat
        ``between`` as optional on every record. Review found the consequence
        from both ends — a mint whose ``between`` was simply left off, and a
        transition naming an id that was never minted — each producing a
        tension that is permanently pairless, permanently not computable, and
        counted by every pass for ever.

        Here, because this is the layer that knows both: the fields *and* which
        tensions the log already holds. A record whose id the fold has already
        seen is a transition and carries whatever it carries; a record for a new
        id is a mint and must say what it is about.

        An id in ``expunged`` counts as seen. The main erased that tension, and
        a later record for it is refused by the fold rather than by this — the
        erasure has to stay an erasure and not become a validation error.
        """
        if BETWEEN in record.data:
            return
        current = self.state()
        if record.id in current.tensions or record.id in current.expunged:
            return
        raise TensionError(
            f"the first {Op.TENSION.value} record for {record.id!r} must name "
            f"the two entries it links: a tension is the record of two entries "
            f"that disagree, and one that names neither is a disagreement "
            f"nothing can ever evaluate and nothing will ever resolve"
        )

    def record(self, op: Op, ident: str, t: str, **fields: Any) -> Record:
        """Append a new record built from ``op``/``ident``/``t``.

        ``t`` is always supplied by the caller. Nothing under ``store`` reads a
        clock, so that fold and replay stay pure (AD-30).
        """
        rec = make(op, ident, t, **fields)
        self.append(rec)
        return rec

    def expunge(self, target: str, *, t: str) -> None:
        """Erase ``target`` genuinely: append the op, then tombstone its bodies.

        Rare and main-initiated. Without the tombstoning pass an expunged
        belief's text would survive in the log — unacceptable for an erasure
        request and for the secrets rule.

        **Erases whatever ``target`` names, including a loop (CAP-6).** The
        façade looks the name up in the current fold: it is the main's own
        *"erase this"*, and requiring them — or the surface above them — to know
        whether a name is a belief id or a loop slug is how an erasure becomes a
        silent no-op. Before this it was exactly that: ``expunge`` wrote a
        ``target``-only record, which the firewall correctly refuses to let
        reach a loop, so the loop stayed in the fold, survived replay, and kept
        its slug and every movement date in the log verbatim.

        This is **not** a hole in the refutation firewall, and the difference is
        the record shape. A correction (``retract``, ``revise``) and a bare
        ``expunge`` op never carry the ``loop`` field, so they can never take a
        wanting with them whatever identifier they name. Only this path — the
        main deliberately erasing something they named — builds the wider
        record, and only for a loop the fold can actually show.
        """
        current = self.fold()
        loops = {target} & set(current.loops)
        also_an_object = target in current.beliefs or target in current.tensions
        # Tombstone bodies first, then append the op. A crash between the two
        # then leaves text already gone with no op yet — the fold still sees
        # the tombstone, so state is correct — rather than an op claiming
        # erasure while the text is still on disk.
        #
        # Transitions are tombstoned by the loop they name rather than by their
        # own record id, because a transition's id is the append's, not the
        # loop's — matching on the id alone erased nothing at all.
        self.log.expunge_bodies({target}, loops=loops)
        # A name that is only a loop produces a loop-only record; a name that is
        # only a belief produces the record it always did; a name that is
        # somehow both erases both. What is never written is a loop's slug into
        # the belief namespace, or the reverse.
        fields: dict[str, Any] = {}
        if loops:
            fields.update(ledger.expunged(target))
        if also_an_object or not loops:
            fields[TARGET] = target
        self.log.append(make(Op.EXPUNGE, f"x_{target}_{t}", t, **fields))
        self.rebuild()

    # -- read ----------------------------------------------------------------

    def fold(self) -> State:
        """Fold the log in memory. Pure; never touches SQLite."""
        return fold(self.log)

    def state(self) -> State:
        """The current derived view, read back from SQLite."""
        return db.read_state(self.conn)

    def rebuild(self) -> State:
        """Rebuild the derived view from the log. Safe at any time; the only
        way SQLite is ever written."""
        state = self.fold()
        db.rebuild(self.conn, state, prefix=self._prefix)
        return state

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """BM25-ranked search over claims and their prefixes (AD-5)."""
        return db.search(self.conn, query, limit)

    # -- read: the retrieval layer's door ------------------------------------
    #
    # Three accessors rather than a handle on the connection, so that ranking
    # policy stays outside ``half/store/`` while retrieval still gets what it
    # needs in one query each. None of them orders by anything but bm25 or id.

    def candidates(self, query: str) -> list[dict[str, Any]]:
        """Term-matched beliefs with their bm25 score, prefix and record.

        Unbounded for the same reason ``all_candidates`` is: a ``LIMIT`` here
        would be a silent cap ordered by bm25, and only retrieval can bound the
        set by salience and say in its result that it did."""
        return db.search_beliefs(self.conn, query)

    def all_candidates(self) -> list[dict[str, Any]]:
        """Every belief, id-ordered, unscored — the backstop behind a query that
        matches no term. Unbounded: bounding it is retrieval's job, because only
        retrieval knows which beliefs are worth keeping (salience) and how to say
        in its result that it dropped some."""
        return db.all_beliefs(self.conn)

    def loops(self) -> dict[str, dict[str, Any]]:
        """The loop projection: the ranking function for everything Half does."""
        return db.read_loops(self.conn)
