"""Export: a directory copy, not a serializer (CAP-14).

Export falls out of the log's own format. There is no separate writer to keep
correct, which is the point of making the log the source of truth rather than
a database with an export button.

The derived SQLite file is excluded deliberately: it is rebuildable from the
log, and shipping it would imply it carries state the log does not.

Every export is scanned for secret material before it is handed over (AD-11).
Credentials should never be in the tree at all — this asserts that rather than
assuming it, because the failure is silent and the blast radius is a live token
in a file the main was told is safe to share.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Final

from half.errors import SecretLeakError
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


def scan_for_secrets(root: Path) -> list[str]:
    """Return a description of every secret-shaped match under ``root``."""
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{label} at {path.relative_to(root)}:{line}")
    return findings


def export(store_root: Path | str, destination: Path | str) -> Path:
    """Copy a store into ``destination`` and assert it carries no secrets.

    Raises ``SecretLeakError`` rather than producing a tainted archive.
    """
    src = Path(store_root)
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)

    beliefs = src / BELIEFS_DIR
    if beliefs.is_dir():
        shutil.copytree(beliefs, dest / BELIEFS_DIR, dirs_exist_ok=True)
    for extra in sorted(src.iterdir()):
        if extra.name in {BELIEFS_DIR, DB_NAME} or extra.name.startswith("."):
            continue
        if extra.is_dir():
            shutil.copytree(extra, dest / extra.name, dirs_exist_ok=True)
        else:
            shutil.copy2(extra, dest / extra.name)

    findings = scan_for_secrets(dest)
    if findings:
        shutil.rmtree(dest, ignore_errors=True)
        raise SecretLeakError(
            "refusing to export; secret material found: " + "; ".join(findings)
        )
    return dest
