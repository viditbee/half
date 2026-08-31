"""Normalise, scan, hand on, discard (CAP-3, CAP-13, AD-13).

**The body is never persisted.** It is normalised into one canonical text
form, scanned, handed to a consumer, and dropped when the frame exits. What
reaches disk is a *receipt*: a digest, provenance, and the record of what was
redacted — every string of which is scrubbed.

That is a deliberate trade. Redaction is a denylist over a representation Half
does not fully control, the store is immutable and content-addressed, and so
every miss would be permanent. Not keeping the body is the only version of
CAP-13 that does not depend on having thought of every secret in advance. The
cost is that a better model cannot revisit old mail; AD-13 records it.

Ordering is the safety property: normalise, scrub, *then* persist. Anything
that reaches the store has passed the gate — enforced by
``test_every_receipt_field_is_scrubber_output`` rather than by the current
shape of one function.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from half.ingest.normalize import normalize
from half.ingest.port import MailSource, Message
from half.ingest.scrub import Scrubbed, scrub
from half.store.sources import SourceStore, digest

logger = logging.getLogger(__name__)

#: A consumer receives the scrubbed text exactly once, in memory, and returns
#: whatever should be kept. Claim derivation registers one; with none
#: registered nothing beyond the receipt is retained.
Consumer = Callable[["Receipt", str], Awaitable[None]]

#: Every receipt field that carries free text and must therefore be scrubbed.
SCRUBBED_FIELDS = ("subject", "sender")


@dataclass(frozen=True, slots=True)
class Receipt:
    """What persists. Carries no body and no secret value."""

    digest: str
    external_id: str
    thread_id: str
    sender: str
    subject: str
    t: str
    redactions: dict[str, int] = field(default_factory=dict)

    def as_payload(self) -> bytes:
        return json.dumps(
            {
                "digest": self.digest,
                "external_id": self.external_id,
                "thread_id": self.thread_id,
                "sender": self.sender,
                "subject": self.subject,
                "t": self.t,
                "redactions": self.redactions,
            },
            sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class Ingested:
    receipts: list[Receipt]
    already_seen: int = 0
    skipped_unreadable: int = 0
    #: Advances even when nothing was captured, so a window of skipped
    #: messages cannot be re-fetched forever.
    cursor: str | None = None


class Pipeline:
    def __init__(
        self, source: MailSource, store: SourceStore, *, consumer: Consumer | None = None
    ) -> None:
        self.source = source
        self.store = store
        self.consumer = consumer

    async def ingest(self, *, since: str | None = None) -> Ingested:
        receipts: list[Receipt] = []
        seen = 0
        unreadable = 0
        newest: str | None = since

        async for message in self.source.fetch(since=since):
            newest = max(newest or message.t, message.t)

            body = normalize(
                message.body,
                encoding=message.headers.get("content-transfer-encoding"),
                charset=_charset_of(message.headers.get("content-type")),
                mime_type=message.headers.get("content-type", "text/plain"),
            )
            if not body.decodable:
                # Representation unresolved. Scanning bytes nobody could read
                # is indistinguishable from not scanning, so it is not kept.
                unreadable += 1
                logger.info("skipped unreadable message %s: %s",
                            message.external_id, body.reason)
                continue

            scrubbed = scrub(body.text)
            receipt = self._receipt(message, scrubbed)

            if self.store.has(receipt.digest):
                seen += 1
                continue
            self.store.put(receipt.as_payload(), address=receipt.digest)
            receipts.append(receipt)

            if self.consumer is not None:
                # The one place the text is handed on. It is not stored, and
                # goes out of scope when this iteration ends.
                await self.consumer(receipt, scrubbed.text)

        return Ingested(
            receipts=receipts, already_seen=seen,
            skipped_unreadable=unreadable, cursor=newest,
        )

    def _receipt(self, message: Message, body: Scrubbed) -> Receipt:
        """Build the receipt. Every free-text field goes through the scrubber.

        The subject is scrubbed because it is where an OTP most often lives —
        the single most common secret arriving by email — and an earlier
        version wrote it verbatim while reporting the message clean.
        """
        fields = {"subject": scrub(message.subject), "sender": scrub(message.sender)}
        redactions = dict(body.labels)
        for scrubbed in fields.values():
            for label, count in scrubbed.labels.items():
                redactions[label] = redactions.get(label, 0) + count

        if redactions:
            logger.info("redacted %s from message %s",
                        sorted(redactions), message.external_id)

        return Receipt(
            digest=digest(body.text.encode("utf-8")),
            external_id=message.external_id,
            thread_id=message.thread_id,
            sender=fields["sender"].text,
            subject=fields["subject"].text,
            t=message.t,
            redactions=redactions,
        )


def _charset_of(content_type: str | None) -> str | None:
    if not content_type:
        return None
    for part in content_type.split(";"):
        key, _, value = part.partition("=")
        if key.strip().lower() == "charset":
            return value.strip().strip('"')
    return None
