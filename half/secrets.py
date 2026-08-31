"""Credentials, kept outside every layer the main can export or replay (AD-11).

Two different problems share one word. Secrets Half *finds while reading* are
scrubbed at ingestion and never written. These are the secrets Half was
*given* — the tokens it needs to read at all — and the danger is different: the
store is exportable and replayable, so a token inside it would be handed to the
main in an archive and resurrected on every replay.

So this store lives beside the main's directory, never inside it. Export copies
the store; it never sees this.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from half.errors import StoreError

#: Where credentials live relative to the store root: a sibling, never a child.
SECRETS_DIRNAME = ".credentials"


@runtime_checkable
class SecretStore(Protocol):
    def put(self, main_id: str, name: str, value: str) -> None: ...
    def get(self, main_id: str, name: str) -> str | None: ...
    def delete(self, main_id: str, name: str) -> None: ...


class FileSecretStore:
    """Self-host implementation: one 0600 file per main, outside the store tree.

    Not encrypted at rest — that would need a key, and a key stored next to the
    ciphertext is decoration. The honest posture is filesystem permissions plus
    a directory the export path cannot reach. Hosted deployments use envelope
    encryption with a master key held elsewhere; that is a different
    implementation of this port, not a flag on this one.
    """

    def __init__(self, root: Path | str, *, store_root: Path | str | None = None) -> None:
        self.root = Path(root).expanduser()
        if store_root is not None:
            # The invariant that matters: credentials must not live inside the
            # tree that export copies and replay rebuilds. A sibling, never a
            # child.
            store = Path(store_root).expanduser().resolve(strict=False)
            if self.root.resolve(strict=False).is_relative_to(store):
                raise StoreError(
                    f"credentials must not live inside the store tree: {self.root}"
                )
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @classmethod
    def beside(cls, store_root: Path | str) -> "FileSecretStore":
        """The conventional location: a sibling of the store root."""
        store = Path(store_root).expanduser()
        return cls(store.parent / SECRETS_DIRNAME, store_root=store)

    def _path(self, main_id: str) -> Path:
        from half.actor.registry import validate_main_id

        return self.root / f"{validate_main_id(main_id)}.json"

    def _read(self, main_id: str) -> dict[str, str]:
        path = self._path(main_id)
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, main_id: str, data: dict[str, str]) -> None:
        path = self._path(main_id)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(data, sort_keys=True).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)

    def put(self, main_id: str, name: str, value: str) -> None:
        data = self._read(main_id)
        data[name] = value
        self._write(main_id, data)

    def get(self, main_id: str, name: str) -> str | None:
        return self._read(main_id).get(name)

    def delete(self, main_id: str, name: str) -> None:
        data = self._read(main_id)
        if data.pop(name, None) is not None:
            self._write(main_id, data)
