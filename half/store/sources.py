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
from pathlib import Path
from typing import Protocol, runtime_checkable


def digest(payload: bytes) -> str:
    """The content address. SHA-256, hex, no prefix."""
    return hashlib.sha256(payload).hexdigest()


@runtime_checkable
class SourceStore(Protocol):
    """Where captured sources live."""

    def put(self, payload: bytes) -> str:
        """Store ``payload`` and return its digest. Idempotent."""
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

    def _path(self, address: str) -> Path:
        return self.root / address[:2] / address[2:4] / address

    def put(self, payload: bytes) -> str:
        address = digest(payload)
        path = self._path(address)
        if path.exists():
            return address  # identical bytes; nothing to do
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(payload)
        tmp.chmod(0o600)
        tmp.replace(path)
        return address

    def get(self, address: str) -> bytes | None:
        path = self._path(address)
        return path.read_bytes() if path.is_file() else None

    def has(self, address: str) -> bool:
        return self._path(address).is_file()

    def __len__(self) -> int:
        return sum(1 for p in self.root.rglob("*") if p.is_file())
