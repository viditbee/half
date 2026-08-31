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
import re
from collections.abc import Iterator
from pathlib import Path

from half.errors import StoreError
from half.store.records import Record, decode, encode

#: Shard filenames are ``YYYY-MM.jsonl``. Sharding serves file size and git
#: diffs only — it carries no semantics, and the fold must never depend on it.
SHARD_SUFFIX = ".jsonl"


#: Shard keys must be exactly ``YYYY-MM``. A looser check let ``abcd-ef-99``
#: produce ``abcd-ef.jsonl``, which then sorts lexically among real months and
#: silently reorders the fold — and fold correctness depends on that order.
_SHARD_KEY = re.compile(r"\d{4}-\d{2}")


def _shard_for(timestamp: str) -> str:
    """``2026-08-14T09:12Z`` -> ``2026-08``. Lexical, never a clock read."""
    if not _SHARD_KEY.fullmatch(timestamp[:7]):
        raise StoreError(f"timestamp {timestamp!r} is not ISO-8601 enough to shard")
    return timestamp[:7]


def _fsync_dir(path: Path) -> None:
    """Persist a directory entry. Without this a newly created shard can be
    lost on crash even though the file's own fsync succeeded."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        pass  # not supported on every platform; the file fsync still happened
    finally:
        os.close(fd)


class BeliefLog:
    """Append-only, month-sharded, chronologically iterable."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    # -- write ---------------------------------------------------------------

    def append(self, record: Record) -> None:
        """Append one record durably (AD-1).

        ``os.write`` may write fewer bytes than asked, which would truncate the
        line and make the log permanently unparseable at that position, so the
        write loops. A partial write that then fails is truncated back to the
        pre-write size rather than left as a broken line. The parent directory
        is fsynced when a new shard is created, or the file's directory entry
        can be lost on crash despite the file fsync succeeding.
        """
        path = self.root / f"{_shard_for(record.t)}{SHARD_SUFFIX}"
        is_new = not path.exists()
        payload = (encode(record) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            start = os.lseek(fd, 0, os.SEEK_END)
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view) :]
            except OSError:
                os.ftruncate(fd, start)
                os.fsync(fd)
                raise
            os.fsync(fd)
        finally:
            os.close(fd)
        if is_new:
            _fsync_dir(self.root)

    def expunge_bodies(self, ids: set[str]) -> int:
        """Replace the bodies of ``ids`` with tombstones, in place.

        The one deliberate exception to append-only. An ``expunge`` op alone
        removes an id from the fold but leaves its text on disk, which cannot
        satisfy a genuine erasure request or the secrets rule. The record's
        position, timestamp and id survive so replay still accounts for it.
        """
        # Pass one: decode every shard before mutating any of them. A corrupt
        # or unknown-op line in a later shard must not abort the run after
        # earlier shards were already replaced — that leaves a half-erased log
        # with no repair path, on the one operation where partial failure is
        # least acceptable.
        planned: list[tuple[Path, list[str]]] = []
        removed = 0
        for path in self.shards():
            # split on "\n" only: str.splitlines() also breaks on U+2028,
            # U+2029 and U+0085, which encode() writes raw into claim text,
            # so a belief containing one would be split into two corrupt lines.
            lines = path.read_text(encoding="utf-8").split("\n")
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
                planned.append((path, out))

        # Pass two: nothing below can fail on parsing. Idempotent — a record
        # already tombstoned is skipped above, so a resume after a partial run
        # completes the job.
        for path, out in planned:
            tmp = path.with_suffix(path.suffix + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                payload = ("\n".join(out) + "\n").encode("utf-8")
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view) :]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, path)
            _fsync_dir(self.root)
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
