"""Export: staged, scanned, then moved into place (CAP-14, AD-11).

Export falls out of the log's own format — there is no separate serializer to
keep correct, which is the point of making the log the source of truth.

Two rules earned by review:

*Never destroy anything at the destination.* An earlier version copied into the
destination and removed it on a secret finding, which deleted whatever was
already there. Staging into a temp directory and moving only on success means a
refusal cannot cost the main a single file.

*Fail closed on anything unscannable.* An earlier version skipped files it
could not decode as UTF-8, so a credential inside a binary blob — the exact
shape a keyring dump or a pickled token cache takes — exported clean while the
scan reported success.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Final

from half.errors import SecretLeakError, StoreError
from half.store.store import BELIEFS_DIR, DB_NAME

#: Shapes that must never appear in an export. Deliberately broad: a false
#: positive costs one conversation, a false negative ships a live credential.
SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("google oauth refresh token", re.compile(r"\b1//[0-9A-Za-z_\-]{20,}")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("bearer/access token field", re.compile(r'"(?:access|refresh|id)_token"\s*:\s*"[^"]+"')),
    ("client secret field", re.compile(r'"client_secret"\s*:\s*"[^"]+"')),
    ("authorization header", re.compile(r"\bAuthorization:\s*Bearer\s+\S+", re.I)),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("anthropic api key", re.compile(r"\bsk-ant-[0-9A-Za-z_\-]{20,}")),
)


def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Every shape, ingest and export alike.

    Imported lazily because `half.ingest.scrub` imports SECRET_PATTERNS from
    this module. The two ends of the pipe must ask the same question, or a
    shape refused on the way in exports clean on the way out.
    """
    from half.ingest.scrub import ALL_PATTERNS

    return ALL_PATTERNS


def scan_for_secrets(root: Path) -> list[str]:
    """Return a description of every secret-shaped match under ``root``.

    Reads bytes and decodes with ``errors="replace"`` so a single invalid byte
    cannot disable the scan for a whole file. A file that cannot be read at all
    is itself reported — unscannable is never treated as clean.
    """
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            findings.append(f"symlink (unresolvable, not followed) at {_rel(path, root)}")
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            findings.append(f"unreadable file at {_rel(path, root)}: {exc}")
            continue
        for label, pattern in _patterns():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{label} at {_rel(path, root)}:{line}")
    return findings


def export(store_root: Path | str, destination: Path | str) -> Path:
    """Stage a store copy, scan it, and only then move it to ``destination``.

    Raises ``SecretLeakError`` without creating or touching ``destination``.
    """
    src = Path(store_root).resolve()
    dest = Path(destination)

    if dest.exists() and any(dest.iterdir()):
        raise StoreError(f"refusing to export into a non-empty destination: {dest}")
    if dest.resolve(strict=False).is_relative_to(src):
        raise StoreError("refusing to export into the store being exported")

    staging = Path(tempfile.mkdtemp(prefix="half-export-"))
    try:
        _stage(src, staging)
        findings = scan_for_secrets(staging)
        if findings:
            raise SecretLeakError(
                "refusing to export; secret material found: " + "; ".join(findings)
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.rmdir()  # empty, checked above
        shutil.move(str(staging), str(dest))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return dest


def _stage(src: Path, staging: Path) -> None:
    """Copy the exportable layers into ``staging``.

    Excludes anything whose name starts with the database name — ``half.db``,
    ``half.db-wal``, ``half.db-shm``. The WAL holds uncheckpointed belief text,
    so excluding only the exact filename shipped derived state the export
    documents as excluded. Symlinks are never followed out of the store.
    """
    beliefs = src / BELIEFS_DIR
    if beliefs.is_dir():
        shutil.copytree(beliefs, staging / BELIEFS_DIR, symlinks=True, dirs_exist_ok=True)
    for extra in sorted(src.iterdir()):
        if extra.name == BELIEFS_DIR or extra.name.startswith(DB_NAME):
            continue
        if extra.name.startswith("."):
            continue
        if extra.is_symlink():
            raise StoreError(f"refusing to export symlink {extra.name}")
        if extra.is_dir():
            shutil.copytree(extra, staging / extra.name, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(extra, staging / extra.name)


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
