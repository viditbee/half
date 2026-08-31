"""A thin Gmail `MailSource` — the only module here that touches the network.

Deliberately thin, following `telegram_transport.py`: every rule that matters
lives in the pipeline and the scrubber and is exercised offline, while this is
the edge that turns those decisions into HTTP.

The token is **supplied**, not acquired. The interactive OAuth consent flow is
deferred: it needs a Google Cloud project and a verified consent screen before
it can be exercised at all, and bundling it would put an unrunnable dependency
in the middle of the safety-critical path.

The credential is held by whatever constructs the transport; nothing in this
module reads or stores one, and no token appears in any exception raised from
here — transport errors are translated at the boundary so a URL carrying an
access token cannot reach a log (AD-11, AD-22).
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
from typing import Any, AsyncIterator, Protocol

from half.errors import ChannelError
from half.ingest.port import Message

#: A page count no real mailbox walk exceeds. A provider echoing the same
#: nextPageToken would otherwise spin forever.
MAX_PAGES = 10_000

#: Multipart nesting deeper than this is malformed, not merely unusual.
MAX_PART_DEPTH = 20


class GmailTransport(Protocol):
    """The network surface. Injected so the suite stays offline."""

    async def list_messages(self, *, query: str, page_token: str | None) -> dict:
        ...

    async def get_message(self, message_id: str) -> dict:
        ...


class GmailSource:
    """Walks a mailbox forward, oldest first."""

    name = "gmail"

    def __init__(self, transport: GmailTransport) -> None:
        self.transport = transport

    async def fetch(self, *, since: str | None = None) -> AsyncIterator[Message]:
        query = _query_for(since)
        page_token: str | None = None
        seen_tokens: set[str] = set()

        for _ in range(MAX_PAGES):
            page = await self._call(
                self.transport.list_messages(query=query, page_token=page_token)
            ) or {}
            for stub in page.get("messages") or []:
                message_id = (stub or {}).get("id")
                if not message_id:
                    continue
                raw = await self._call(self.transport.get_message(message_id))
                message = normalize(raw or {})
                if message is not None:
                    yield message

            page_token = page.get("nextPageToken")
            if not page_token or page_token in seen_tokens:
                return
            seen_tokens.add(page_token)

    async def _call(self, awaitable):
        """Translate transport faults at the boundary.

        The original exception is dropped rather than chained: a Gmail HTTP
        error carries the request URL, which carries the access token.
        """
        try:
            return await awaitable
        except Exception as exc:  # noqa: BLE001 - translated deliberately
            raise ChannelError(f"gmail request failed: {type(exc).__name__}") from None


def normalize(raw: dict[str, Any]) -> Message | None:
    """One Gmail API message to the port's `Message`, or None to skip.

    Module-level and pure, so the contract between this file and the pipeline
    is testable without a network — the failure mode story 2 taught: renaming a
    key here would otherwise leave every test green while Half silently
    ingested nothing.
    """
    payload = raw.get("payload") or {}
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in payload.get("headers", [])
    }
    body = _body_bytes(payload)
    if not body:
        return None

    stamp = _iso_from_internal_date(raw.get("internalDate"))
    if stamp is None:
        # Stamping "now" would drag the cursor forward to the present and
        # filter out every genuinely older message forever.
        return None

    return Message(
        external_id=str(raw.get("id", "")),
        thread_id=str(raw.get("threadId", "")),
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        body=body,
        t=stamp,
        headers=headers,
    )


def _decode_b64(data: str) -> bytes:
    """Pad to a multiple of four and validate.

    Without ``validate=True`` the decoder silently drops characters outside
    the alphabet, so malformed data yields plausible-looking bytes rather than
    an error — and a corrupt part would be scanned as if it were text.
    """
    # urlsafe_b64decode has no validate flag, so translate the alphabet and
    # use the strict decoder.
    standard = data.translate(str.maketrans("-_", "+/"))
    return base64.b64decode(standard + "=" * (-len(standard) % 4), validate=True)


def _query_for(since: str | None) -> str:
    """Gmail's `after:` takes YYYY/MM/DD. A malformed cursor must not silently
    widen or narrow the window."""
    if not since:
        return ""
    head = since[:10]
    if len(head) != 10 or head[4] != "-" or head[7] != "-":
        raise ChannelError(f"cursor is not an ISO-8601 date: {since!r}")
    return f"after:{head.replace('-', '/')}"


def _body_bytes(payload: dict[str, Any], depth: int = 0) -> bytes:
    """The first readable text part, walking multipart recursively.

    Returns raw bytes rather than text: whether it decodes is the scrubber's
    question, and a part that will not decode must be treated as a finding
    rather than dropped here.
    """
    if depth > MAX_PART_DEPTH:
        return b""
    mime = str(payload.get("mimeType", ""))
    data = (payload.get("body") or {}).get("data")
    if data and mime.startswith("text/"):
        try:
            return _decode_b64(str(data))
        except (binascii.Error, ValueError):
            # Malformed base64 is one bad message, not a reason to abort the
            # whole run.
            return b""
    for part in payload.get("parts") or []:
        found = _body_bytes(part or {}, depth + 1)
        if found:
            return found
    return b""


def _iso_from_internal_date(value: Any) -> str | None:
    """Gmail's internalDate is epoch milliseconds as a string, or None.

    Returns None rather than falling back to the clock: the caller advances a
    cursor from these timestamps, so a fabricated "now" permanently skips
    every older message. It would also break the port's stated invariant that
    nothing downstream reads a clock.
    """
    try:
        stamp = _dt.datetime.fromtimestamp(int(value) / 1000, _dt.UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
