"""SQLite: the materialized fold plus the FTS5 index (AD-3, AD-5).

Entirely derived. Delete this file and rebuild it from the log — that is the
replay invariant (AD-4), and it is a test rather than a promise.

Retrieval runs on FTS5 ``bm25()``, which ships in the standard library's
sqlite3. No vector service and no reranker in the hot path (AD-5): the mission
requires this to run on a self-hoster's cheap box.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from half.store.fold import State

SCHEMA = """
CREATE TABLE IF NOT EXISTS beliefs (
    id          TEXT PRIMARY KEY,
    t           TEXT NOT NULL,
    subject     TEXT,
    claim       TEXT,
    ledger      TEXT,
    license     TEXT NOT NULL DEFAULT 'behave',
    independent INTEGER NOT NULL DEFAULT 0,
    data        TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS tensions (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS loops    (id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS expunged (id TEXT PRIMARY KEY) STRICT;

CREATE VIRTUAL TABLE IF NOT EXISTS belief_fts USING fts5(
    claim,
    content = 'beliefs',
    content_rowid = 'rowid'
);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def rebuild(conn: sqlite3.Connection, state: State) -> None:
    """Replace the whole derived view with ``state``.

    Wholesale rather than incremental on purpose: an incremental writer is how
    a derived store starts accumulating rows that exist nowhere in the log.
    """
    with conn:
        conn.execute("DELETE FROM belief_fts")
        for table in ("beliefs", "tensions", "loops", "expunged"):
            conn.execute(f"DELETE FROM {table}")

        for ident, data in state.beliefs.items():
            conn.execute(
                "INSERT INTO beliefs (id, t, subject, claim, ledger, license,"
                " independent, data) VALUES (?,?,?,?,?,?,?,?)",
                (
                    ident,
                    str(data.get("t", "")),
                    _text_or_none(data.get("subject")),
                    _text_or_none(data.get("claim")),
                    _text_or_none(data.get("ledger")),
                    str(data.get("license", "behave")),
                    int(data.get("independent", 0) or 0),
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
            "INSERT INTO belief_fts(rowid, claim) SELECT rowid, claim FROM beliefs"
            " WHERE claim IS NOT NULL"
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
    """BM25-ranked search over claim text. Lower bm25() is a better match."""
    rows = conn.execute(
        "SELECT b.id, b.claim, bm25(belief_fts) AS score"
        " FROM belief_fts JOIN beliefs b ON b.rowid = belief_fts.rowid"
        " WHERE belief_fts MATCH ? ORDER BY score, b.id LIMIT ?",
        (query, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
