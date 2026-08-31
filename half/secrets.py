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

    def __init__(self, root: Path | str, *, store_root: Path | str) -> None:
        """``store_root`` is required.

        It was optional, so the nesting invariant simply went unchecked
        whenever a caller omitted it — a guard that can be skipped by not
        passing an argument is not a guard.
        """
        self.root = Path(root).expanduser()
        store = Path(store_root).expanduser().resolve(strict=False)
        if self.root.resolve(strict=False).is_relative_to(store):
            raise StoreError(
                f"credentials must not live inside the store tree: {self.root}"
            )
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # mkdir's mode is a no-op on an existing directory, so an inherited
        # 0755 credentials directory would stay world-readable.
        self.root.chmod(0o700)

    @classmethod
    def beside(cls, mains_root: Path | str) -> "FileSecretStore":
        """The conventional location: a sibling of the directory holding all mains.

        ``mains_root`` is the parent of every main's store, not one main's own
        directory. Passing a single main's root previously produced a path that
        was a sibling of that main but a *child* of the tree holding all of
        them — and the guard, comparing only against the value passed in,
        approved it.
        """
        root = Path(mains_root).expanduser()
        return cls(root.parent / SECRETS_DIRNAME, store_root=root)

    def _path(self, main_id: str) -> Path:
        from half.actor.registry import validate_main_id

        return self.root / f"{validate_main_id(main_id)}.json"

    def _read(self, main_id: str) -> dict[str, str]:
        path = self._path(main_id)
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise StoreError(f"corrupt credential file {path}: {exc}") from None
        if not isinstance(data, dict):
            raise StoreError(f"corrupt credential file {path}: not an object")
        return data

    def _write(self, main_id: str, data: dict[str, str]) -> None:
        path = self._path(main_id)
        # Unique per process and O_EXCL: a pre-existing temp file previously
        # kept its own mode and was promoted to the credential file by
        # os.replace, which put a live token in a world-readable file.
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.unlink(missing_ok=True)
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                payload = json.dumps(data, sort_keys=True).encode("utf-8")
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, path)
        except OSError:
            # A partial write must not leave plaintext credentials behind.
            tmp.unlink(missing_ok=True)
            raise

    def put(self, main_id: str, name: str, value: str) -> None:
        data = self._read(main_id)
        data[name] = value
        self._write(main_id, data)

    def get(self, main_id: str, name: str) -> str | None:
        return self._read(main_id).get(name)

    def delete(self, main_id: str, name: str) -> None:
        data = self._read(main_id)
        if data.pop(name, None) is None:
            return
        if data:
            self._write(main_id, data)
        else:
            # Nothing left: remove the file rather than leaving an empty
            # object that still says this main had credentials.
            self._path(main_id).unlink(missing_ok=True)
