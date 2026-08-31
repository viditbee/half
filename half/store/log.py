"""The append-only belief log — the only source of truth (AD-3).

One writer per store instance (AD-1). Under a single writer an ``O_APPEND``
write needs no lock, which is the decision that lets Half skip the journal,
precondition-hash and rollback machinery a multi-writer file store requires.
Cross-process exclusion is the supervisor's concern, not this module's.

Records are never mutated in place. ``expunge`` tombstones by appending; the
tombstoning rewrite is the single deliberate exception and is handled in
``expunge_bodies``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from half.errors import StoreError
from half.store.records import Record, decode, encode

#: Shard filenames are ``YYYY-MM.jsonl``. Sharding serves file size and git
#: diffs only — it carries no semantics, and the fold must never depend on it.
SHARD_SUFFIX = ".jsonl"


def _shard_for(timestamp: str) -> str:
    """``2026-08-14T09:12Z`` -> ``2026-08``. Lexical, never a clock read."""
    if len(timestamp) < 7 or timestamp[4] != "-":
        raise StoreError(f"timestamp {timestamp!r} is not ISO-8601 enough to shard")
    return timestamp[:7]


class BeliefLog:
    """Append-only, month-sharded, chronologically iterable."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- write ---------------------------------------------------------------

    def append(self, record: Record) -> None:
        """Append one record durably. O_APPEND + fsync (AD-1)."""
        path = self.root / f"{_shard_for(record.t)}{SHARD_SUFFIX}"
        payload = (encode(record) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def expunge_bodies(self, ids: set[str]) -> int:
        """Replace the bodies of ``ids`` with tombstones, in place.

        The one deliberate exception to append-only. An ``expunge`` op alone
        removes an id from the fold but leaves its text on disk, which cannot
        satisfy a genuine erasure request or the secrets rule. The record's
        position, timestamp and id survive so replay still accounts for it.
        """
        removed = 0
        for path in self.shards():
            lines = path.read_text(encoding="utf-8").splitlines()
            out: list[str] = []
            changed = False
            for lineno, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                rec = decode(line, path=str(path), lineno=lineno)
                if rec.id in ids and rec.data.get("tombstone") is not True:
                    stub = Record(
                        op=rec.op,
                        id=rec.id,
                        t=rec.t,
                        data={
                            "t": rec.t,
                            "op": str(rec.op),
                            "id": rec.id,
                            "v": rec.data.get("v", 1),
                            "tombstone": True,
                        },
                    )
                    out.append(encode(stub))
                    changed = True
                    removed += 1
                else:
                    out.append(line)
            if changed:
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
                os.replace(tmp, path)
        return removed

    # -- read ----------------------------------------------------------------

    def shards(self) -> list[Path]:
        """Shards in chronological order. Filename sort is chronological because
        ``YYYY-MM`` is zero-padded and fixed width."""
        return sorted(p for p in self.root.glob(f"*{SHARD_SUFFIX}") if p.is_file())

    def __iter__(self) -> Iterator[Record]:
        for path in self.shards():
            with path.open("r", encoding="utf-8") as handle:
                for lineno, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    yield decode(line, path=str(path), lineno=lineno)
