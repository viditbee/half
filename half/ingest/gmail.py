"""A thin Gmail `MailSource` — the only module here that touches the network.

Deliberately thin, following `telegram_transport.py`: every rule that matters
lives in the pipeline and the scrubber and is exercised offline, while this is
the edge that turns those decisions into HTTP.

The token is **supplied**, not acquired. The interactive OAuth consent flow is
deferred: it needs a Google Cloud project and a verified consent screen before
it can be exercised at all, and bundling it would put an unrunnable dependency
in the middle of the safety-critical path.

The token is read from the `SecretStore` and never written into a store tree
(AD-11).
"""

from __future__ import annotations

import base64
import json
from typing import Any, AsyncIterator, Protocol

from half.errors import ChannelError, HalfError
from half.ingest.port import Message

#: Gmail's REST surface, minimal.
API = "https://gmail.googleapis.com/gmail/v1/users/me"


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
        query = f"after:{since[:10].replace('-', '/')}" if since else ""
        page_token: str | None = None
        while True:
            page = await self.transport.list_messages(
                query=query, page_token=page_token
            )
            for stub in page.get("messages", []):
                raw = await self.transport.get_message(stub["id"])
                message = normalize(raw)
                if message is not None:
                    yield message
            page_token = page.get("nextPageToken")
            if not page_token:
                return


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

    return Message(
        external_id=str(raw.get("id", "")),
        thread_id=str(raw.get("threadId", "")),
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        body=body,
        t=_iso_from_internal_date(raw.get("internalDate")),
        headers=headers,
    )


def _body_bytes(payload: dict[str, Any]) -> bytes:
    """The first readable text part, walking multipart recursively.

    Returns raw bytes rather than text: whether it decodes is the scrubber's
    question, and a part that will not decode must be treated as a finding
    rather than dropped here.
    """
    mime = payload.get("mimeType", "")
    data = (payload.get("body") or {}).get("data")
    if data and mime.startswith("text/"):
        return base64.urlsafe_b64decode(data + "===")
    for part in payload.get("parts", []) or []:
        found = _body_bytes(part)
        if found:
            return found
    return b""


def _iso_from_internal_date(value: Any) -> str:
    """Gmail's internalDate is epoch milliseconds as a string."""
    import datetime as _dt

    try:
        epoch = int(value) / 1000
        stamp = _dt.datetime.fromtimestamp(epoch, _dt.UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        stamp = _dt.datetime.now(_dt.UTC)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
