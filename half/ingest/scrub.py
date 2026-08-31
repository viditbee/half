"""Secret detection and redaction, applied *before* anything is persisted.

The obvious shape is to capture the raw message and redact afterwards. That
writes the secret to disk first — and sources are immutable and
content-addressed, so the write is permanent and the digest is of the
unredacted bytes. Detection therefore runs on the in-memory body, and the
`SourceStore` only ever sees redacted text (CAP-13).

Fails closed. Content that will not decode is treated as a finding rather than
skipped: a credential inside a binary blob is exactly the shape a keyring dump
or a pickled token cache takes, and skipping it would report success while
storing the secret.

`ALL_PATTERNS` is the single set used at both ends of the pipe: ingestion
scrubs with it and `half.store.export` scans with it. They were once different
sets while a docstring claimed otherwise, so four shapes Half refused to ingest
would still have exported clean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from half.store.export import SECRET_PATTERNS

#: What replaces a detected secret. Carries the label so the record says what
#: was removed, and never what it was.
REDACTION = "[redacted: {label}]"

#: Additional shapes that matter on the way in but not on the way out — a
#: one-time code or a recovery code is not a token Half would ever emit, but
#: it is exactly what arrives by email.
INBOUND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Widened after review demonstrated that every one of these real shapes
    # passed clean: an OTP on its own line (the ordinary layout, which the old
    # `[^0-9\n]` refused to cross), a space-separated code, "codes are",
    # digits before the keyword, and a second code after the first match.
    ("one-time code", re.compile(
        r"\b(?:codes?|otp|passcode|pin|verification|one[- ]time)\b[\s\S]{0,40}?"
        r"\b(\d[\d\s-]{3,14}\d)\b", re.I)),
    ("one-time code", re.compile(
        r"\b(\d[\d\s-]{3,14}\d)\b[^.\n]{0,30}\b(?:is your|to (?:sign|log) in)\b", re.I)),
    ("recovery code", re.compile(
        r"\b(?:recovery|backup)\s+codes?\b[\s\S]{0,40}?"
        r"([A-Za-z0-9]{4,}(?:-[A-Za-z0-9]{4,})+)", re.I)),
    # Any opaque high-entropy segment on a login-ish URL, not only `token=`.
    ("magic link", re.compile(
        r"https?://\S*(?:reset|verify|confirm|login|magic|invite|activate)"
        r"\S*?[/=]([A-Za-z0-9_\-]{12,})", re.I)),
    ("credential query parameter", re.compile(
        r"[?&](?:token|auth|key|secret|password|pwd|sig)=[^\s&]{6,}", re.I)),
    ("basic auth in url", re.compile(r"https?://[^/\s:@]+:[^/\s@]+@\S+")),
    ("authorization basic", re.compile(r"\bAuthorization:\s*Basic\s+\S+", re.I)),
    ("plaintext password", re.compile(
        r"\b(?:password|passwd|pwd|passphrase)\b\s*(?:is|:|=)\s*(\S{4,})", re.I)),
    ("slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("stripe key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("private key body", re.compile(r"\bMII[A-Za-z0-9+/=]{40,}")),
)

ALL_PATTERNS = SECRET_PATTERNS + INBOUND_PATTERNS


@dataclass(slots=True)
class Scrubbed:
    """The result of scrubbing one body.

    ``labels`` records *what kind* of secret was removed and how many, never
    the value. Anything holding the value would defeat the point.
    """

    text: str
    labels: dict[str, int] = field(default_factory=dict)
    #: True when the body carried nothing but secrets, so there is nothing
    #: worth capturing.
    empty_after_redaction: bool = False

    @property
    def found_any(self) -> bool:
        return bool(self.labels)


def decode(raw: bytes) -> tuple[str, bool]:
    """Decode for scanning. Returns the text and whether it decoded cleanly.

    Undecodable bytes are replaced rather than skipped, so a single invalid
    byte cannot disable detection for a whole body.
    """
    try:
        return raw.decode("utf-8"), True
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), False


def scrub(text: str) -> Scrubbed:
    """Redact every recognised secret shape from ``text``."""
    labels: dict[str, int] = {}
    result = text
    # Two passes: a redaction can bring a second secret's context within reach
    # of a pattern that the first pass could not match.
    for _ in range(2):
        for label, pattern in ALL_PATTERNS:
            result, count = pattern.subn(REDACTION.format(label=label), result)
            if count:
                labels[label] = labels.get(label, 0) + count

    stripped = result
    for label in labels:
        stripped = stripped.replace(REDACTION.format(label=label), "")
    return Scrubbed(
        text=result,
        labels=labels,
        empty_after_redaction=bool(labels) and not stripped.strip(),
    )


def scrub_bytes(raw: bytes) -> Scrubbed:
    """Scrub raw bytes, failing closed on anything undecodable.

    A body that does not decode cleanly is not passed through: the text it
    yields after replacement is lossy, so storing it would keep bytes nobody
    scanned. Treated as a finding and dropped.
    """
    text, clean = decode(raw)
    result = scrub(text)
    if not clean:
        result.labels["undecodable content"] = result.labels.get("undecodable content", 0) + 1
        result.empty_after_redaction = True
    return result
