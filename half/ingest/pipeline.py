"""Fetch, scrub, capture — in that order, and never another (CAP-3, CAP-13).

The ordering is the whole safety property. Scrubbing happens on the in-memory
body before the `SourceStore` is touched, because sources are immutable and
content-addressed: capturing first would make the secret permanent and address
the source by the digest of its unredacted bytes.

Idempotent by digest, so re-reading a mailbox captures nothing twice.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from half.errors import HalfError
from half.ingest.port import MailSource, Message
from half.ingest.scrub import Scrubbed, scrub_bytes
from half.store.sources import SourceStore, digest

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Captured:
    """What one message became. Carries no body and no secret value."""

    address: str
    external_id: str
    thread_id: str
    sender: str
    t: str
    redactions: dict[str, int]
    already_present: bool


@dataclass(frozen=True, slots=True)
class Ingested:
    captured: list[Captured]
    skipped_secret_only: int = 0
    skipped_undecodable: int = 0

    @property
    def cursor(self) -> str | None:
        """The newest timestamp seen, for resuming."""
        return max((c.t for c in self.captured), default=None)


class Pipeline:
    """Reads a mailbox into a main's sources."""

    def __init__(self, source: MailSource, store: SourceStore) -> None:
        self.source = source
        self.store = store

    async def ingest(self, *, since: str | None = None) -> Ingested:
        captured: list[Captured] = []
        secret_only = 0
        undecodable = 0

        async for message in self.source.fetch(since=since):
            scrubbed = scrub_bytes(message.body)

            if scrubbed.empty_after_redaction:
                # Nothing left worth keeping, or content nobody could scan.
                # Either way it is not written.
                if "undecodable content" in scrubbed.labels:
                    undecodable += 1
                else:
                    secret_only += 1
                continue

            captured.append(self._capture(message, scrubbed))

        return Ingested(
            captured=captured,
            skipped_secret_only=secret_only,
            skipped_undecodable=undecodable,
        )

    def _capture(self, message: Message, scrubbed: Scrubbed) -> Captured:
        """Write the redacted source. The only place bytes reach the store."""
        payload = _envelope(message, scrubbed.text)
        address = digest(payload)
        already = self.store.has(address)
        if not already:
            self.store.put(payload)
        if scrubbed.found_any:
            # Kinds and counts only — never a value (AD-22).
            logger.info(
                "redacted %s from message %s", sorted(scrubbed.labels), message.external_id
            )
        return Captured(
            address=address,
            external_id=message.external_id,
            thread_id=message.thread_id,
            sender=message.sender,
            t=message.t,
            redactions=dict(scrubbed.labels),
            already_present=already,
        )


def _envelope(message: Message, text: str) -> bytes:
    """The stored form: routing metadata plus the redacted body.

    Canonical JSON so identical messages address identically and re-ingestion
    is genuinely a no-op.
    """
    return json.dumps(
        {
            "external_id": message.external_id,
            "thread_id": message.thread_id,
            "sender": message.sender,
            "subject": text and message.subject,
            "t": message.t,
            "body": text,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
