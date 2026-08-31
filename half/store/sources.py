"""Layer 1: immutable, content-addressed sources, behind a port (AD-13).

Sources are the big, write-once, rarely-read layer — read during ingestion and
during a rebuild, and never otherwise. That is why they get their own port:
self-host keeps them on local disk, hosted moves them to object storage, and
layers 2-4 stay local to the actor's node either way (AD-12).

Content-addressed, so re-ingesting the same message is a no-op rather than a
duplicate, and so a source's identity is its bytes rather than a name someone
chose.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from half.errors import StoreError

#: A content address is a SHA-256 hex digest and nothing else. Validated
#: because it becomes a path: '../' in an address would escape the shard tree.
_ADDRESS = re.compile(r"[0-9a-f]{64}")


def digest(payload: bytes) -> str:
    """The content address. SHA-256, hex, no prefix."""
    return hashlib.sha256(payload).hexdigest()


@runtime_checkable
class SourceStore(Protocol):
    """Where captured sources live."""

    def put(self, payload: bytes, *, address: str | None = None) -> str:
        """Store ``payload``, optionally at an explicit content address.

        An explicit address lets a caller key a record by the digest of the
        *content it describes* rather than of the record itself — so a receipt
        whose redaction counts change still resolves to one message.
        """
        ...

    def get(self, address: str) -> bytes | None:
        ...

    def has(self, address: str) -> bool:
        ...

    def __len__(self) -> int:
        ...


class LocalSourceStore:
    """Filesystem implementation — the self-host path.

    Sharded two levels by digest prefix, because a single directory holding
    every message a person has ever received is hostile to both the filesystem
    and anyone looking at it.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # mkdir's mode is ignored when the directory already exists, so an
        # inherited 0755 would silently persist.
        self.root.chmod(0o700)

    def _path(self, address: str) -> Path:
        if not _ADDRESS.fullmatch(address):
            raise StoreError(f"not a content address: {address!r}")
        return self.root / address[:2] / address[2:4] / address

    def put(self, payload: bytes, *, address: str | None = None) -> str:
        address = address or digest(payload)
        path = self._path(address)
        if path.exists():
            return address  # identical bytes; nothing to do
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Unique per process and opened O_EXCL at 0600, so the bytes are never
        # briefly world-readable and two writers cannot share a temp file.
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        return address

    def get(self, address: str) -> bytes | None:
        path = self._path(address)
        return path.read_bytes() if path.is_file() else None

    def has(self, address: str) -> bool:
        return self._path(address).is_file()

    def __len__(self) -> int:
        """Stored sources, excluding any orphaned temp file."""
        return sum(
            1 for p in self.root.rglob("*")
            if p.is_file() and not p.name.endswith(".tmp")
        )
