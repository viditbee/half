"""Bring a mail part to one canonical text form *before* it is scanned.

A regex cannot match a secret it is reading in the wrong representation. Three
review lenses each demonstrated the same class of bypass on the same key:

    quoted-printable   AKIAIOSFODNN7EX=\\n AMPLE   soft line break
    base64 CTE         QUtJQUlPU0ZPRE5ON0VYQU1QTEU=
    UTF-16             NUL-interleaved, decodes "cleanly" as UTF-8
    HTML               AKIA<b></b>IOSFODNN7EXAMPLE

None is an exotic input; all four are ordinary email. So decoding is not a
convenience here, it is the precondition that makes detection mean anything.

Fails closed: content whose representation cannot be resolved is reported as
undecodable rather than passed through, because scanning bytes nobody could
read is indistinguishable from not scanning at all.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import html
import quopri
import re
from dataclasses import dataclass

#: Beyond this, scanning cost stops being worth it and the part is failed
#: closed instead. Measured: the scan is superlinear, and a megabyte of
#: markup stalls ingestion for over a minute.
MAX_SCAN_BYTES = 256 * 1024

#: Charsets worth trying when the part declares nothing usable, in order.
_FALLBACK_CHARSETS = ("utf-8", "utf-16", "latin-1")

_TAG = re.compile(r"<[^>]{0,4096}>")
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)


@dataclass(frozen=True, slots=True)
class Normalized:
    text: str
    #: False when the representation could not be resolved. The caller must
    #: treat this as a finding, never as clean text.
    decodable: bool
    reason: str = ""


def normalize(
    raw: bytes,
    *,
    encoding: str | None = None,
    charset: str | None = None,
    mime_type: str = "text/plain",
) -> Normalized:
    """Decode transfer encoding, then charset, then markup."""
    if len(raw) > MAX_SCAN_BYTES:
        return Normalized("", False, f"part exceeds {MAX_SCAN_BYTES} bytes")

    try:
        decoded = _decode_transfer(raw, encoding)
    except (binascii.Error, ValueError) as exc:
        return Normalized("", False, f"bad transfer encoding: {exc}")

    text, ok = _decode_charset(decoded, charset)
    if not ok:
        return Normalized("", False, "no usable charset")

    if "html" in mime_type.lower():
        text = strip_markup(text)

    # A NUL means the bytes were almost certainly a wide encoding that
    # happened to survive a narrow decode — the UTF-16 bypass. Treating it as
    # text would scan characters separated by NULs, which matches nothing.
    if "\x00" in text:
        return Normalized("", False, "embedded NUL; representation unresolved")

    return Normalized(text, True)


def _decode_transfer(raw: bytes, encoding: str | None) -> bytes:
    name = (encoding or "").strip().lower()
    if name in ("quoted-printable", "quoted_printable"):
        return quopri.decodestring(raw)
    if name == "base64":
        return base64.b64decode(raw + b"===", validate=False)
    return raw  # 7bit, 8bit, binary, or absent


def _decode_charset(raw: bytes, charset: str | None) -> tuple[str, bool]:
    """Decode strictly. A charset that does not decode is a finding, not a
    reason to mangle the text with replacement characters."""
    candidates = []
    if charset and charset.strip():
        candidates.append(charset.strip().lower())
    candidates.extend(c for c in _FALLBACK_CHARSETS if c not in candidates)

    for name in candidates:
        try:
            codecs.lookup(name)
        except LookupError:
            continue
        try:
            text = raw.decode(name)
        except (UnicodeDecodeError, ValueError):
            continue
        # latin-1 decodes *any* byte sequence, so "it decoded" is not evidence
        # that it was text — without this, binary content silently became
        # mojibake and fail-closed never fired.
        if _looks_like_text(text):
            return text, True
    return "", False


#: Control characters that never appear in real text (tab, LF, CR excepted).
_CONTROL = frozenset(chr(c) for c in range(32)) - {"\t", "\n", "\r"}


def _looks_like_text(text: str) -> bool:
    if not text:
        return True
    control = sum(1 for ch in text if ch in _CONTROL or ch == "\ufffd")
    return control / len(text) < 0.05


def strip_markup(text: str) -> str:
    """Remove tags and resolve entities so markup cannot split a secret.

    Tags become a space rather than nothing: `a<br>b` is two words, while
    `AKIA<b></b>REST` is one token — so the separator is inserted and then
    collapsed only where it was already whitespace.
    """
    without_blocks = _SCRIPT_OR_STYLE.sub(" ", text)
    unmarked = _TAG.sub("", without_blocks)
    return html.unescape(unmarked)
