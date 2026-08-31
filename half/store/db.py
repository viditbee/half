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
from pathlib import Path
from typing import Any

from half.errors import StoreError
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
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA)
    path.chmod(0o600)  # holds a full copy of every claim
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
                    _require_str(data, "t", ident, default=""),
                    _text_or_none(data.get("subject")),
                    _text_or_none(data.get("claim")),
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
    """BM25-ranked search over claim text. Lower bm25() is a better match.

    The query is a main's own words, so FTS5 operator characters are ordinary
    input rather than syntax. It is quoted as a phrase, and a sqlite error is
    translated to a ``StoreError`` — nothing here leaks a bare sqlite3
    exception to a caller.
    """
    if not query.strip():
        return []
    limit = max(0, int(limit))
    if limit == 0:
        return []
    query = '"' + query.replace('"', '""') + '"'
    try:
        return _run_search(conn, query, limit)
    except sqlite3.Error as exc:
        raise StoreError(f"search failed: {exc}") from exc


def _run_search(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
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
