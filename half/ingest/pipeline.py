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

**Since story 15b the same ordering guards a second exit, and a wider one.** A
consumer may now hand the text to a model provider, so *normalise, scrub, then
hand on* is what stands between a main's unredacted mail and somebody else's
machine — and a reordering would send it there with nothing failing. Three
things hold it, none of them a code review:

* the consumer is handed the **``Scrubbed`` object ``scrub`` returned**, not a
  bare ``str``, so the seam through which a body leaves ingestion carries the
  scrubber's own output type and a reader can refuse anything else
  (``half.derive.revealed.Revealed.observe`` does);
* ``body.text`` — the unscrubbed text — is read **exactly once in this module**,
  as the argument of ``scrub``, which ``tests/test_revealed.py`` asserts over
  this file's syntax tree rather than by reading it;
* and a ``scrub`` that *raises* produces no ``Scrubbed`` to hand on, so no
  exception path reaches a consumer with a body either.
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

#: A consumer receives the scrubbed body exactly once, in memory, and returns
#: whatever should be kept. Claim derivation registers one; with none
#: registered nothing beyond the receipt is retained.
#:
#: **It receives the ``Scrubbed`` and not its text**, which is the story 15b
#: change and is a safety property rather than a convenience. A consumer may
#: send what it is given to a model provider; typing the seam with the
#: scrubber's own output type is what lets the consumer refuse a body that has
#: not been through it, so a reordering of scrub and derive fails at the seam
#: instead of arriving at a provider. It also hands the consumer
#: ``empty_after_redaction`` — a body that was nothing but secrets, which must
#: derive nothing at all.
Consumer = Callable[["Receipt", "Scrubbed"], Awaitable[None]]

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
                # **The one place the body is handed on**, and the only moment
                # it exists at all: it is not stored, and it goes out of scope
                # when this iteration ends. What travels is ``scrubbed`` — the
                # object ``scrub`` returned above — and never ``body.text``,
                # which is read exactly once in this module and only there.
                #
                # After the receipt is durable rather than before it, so a
                # provider that is slow, failing or absent cannot cost this
                # message the receipt story 3 promised. A crash between the two
                # loses a claim and never evidence.
                await self.consumer(receipt, scrubbed)

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
