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

Not yet built, deferred to their consuming stories: the SourceStore port
(AD-13) and the projection renderer (AD-31).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Self

from half.store import db
from half.store.fold import State, fold
from half.store.log import BeliefLog
from half.store.ops import Op
from half.store.records import Record, make

BELIEFS_DIR = "beliefs"
DB_NAME = "half.db"


class Store:
    """Owns one main's directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = BeliefLog(self.root / BELIEFS_DIR)
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
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- write ---------------------------------------------------------------

    def append(self, record: Record) -> None:
        """Append one record and refresh the derived view."""
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
        self.log.append(make(Op.EXPUNGE, f"x_{target}", t, target=target))
        self.log.expunge_bodies({target})
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
        db.rebuild(self.conn, state)
        return state

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """BM25-ranked search over claims (AD-5)."""
        return db.search(self.conn, query, limit)
