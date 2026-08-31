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

from half.store import db
from half.store.fold import State, fold
from half.store.log import BeliefLog
from half.store.ops import Op
from half.store.records import RESERVED, Record, make, validate_fields

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
        """
        validate_fields({k: v for k, v in record.data.items() if k not in RESERVED})
        self.log.append(record)
        self.rebuild()

    def record(self, op: Op, ident: str, t: str, **fields: Any) -> Record:
        """Append a new record built from ``op``/``ident``/``t``.

        ``t`` is always supplied by the caller. Nothing under ``store`` reads a
        clock, so that fold and replay stay pure (AD-30).
        """
        rec = make(op, ident, t, **fields)
        self.append(rec)
        return rec

    def expunge(self, target: str, *, t: str) -> None:
        """Erase ``target`` genuinely: append the op, then tombstone its body.

        Rare and main-initiated. Without the tombstoning pass an expunged
        belief's text would survive in the log — unacceptable for an erasure
        request and for the secrets rule.
        """
        # Tombstone bodies first, then append the op. A crash between the two
        # then leaves text already gone with no op yet — the fold still sees
        # the tombstone, so state is correct — rather than an op claiming
        # erasure while the text is still on disk.
        self.log.expunge_bodies({target})
        self.log.append(make(Op.EXPUNGE, f"x_{target}_{t}", t, target=target))
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
