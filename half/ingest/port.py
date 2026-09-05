"""The `MailSource` port — the whole surface Half needs from a mailbox.

Narrow on purpose. Half needs to walk a mailbox forward from a cursor and stop;
everything else a mail API offers is not this product's concern.

**A source may say more than ``MailSource`` asks, and one thing is read.** A
``Draining`` source publishes ``drained_through`` — how far it has *finished*
handing over, which is not how far it got — and ``half.ingest.pipeline``
advances its cursor to that and to nothing else. It is a protocol of its own
rather than a member of ``MailSource`` because it is not part of the promise:
the *order* is the port's business, while how a particular provider proves it
drained a stretch of mailbox is that adapter's. A source that is not
``Draining`` is taken at the promise's word.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True, repr=False)
class Message:
    """One mail message, normalized away from its provider.

    ``body`` is raw bytes: decoding is the scrubber's job, because a body that
    will not decode must be treated as a finding rather than silently lost.
    """

    external_id: str
    thread_id: str
    sender: str
    subject: str
    body: bytes
    #: ISO-8601, supplied by the provider. Nothing downstream reads a clock.
    t: str
    headers: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        """Never render the body or headers.

        A plain dataclass repr puts the unredacted body into every traceback,
        `logging.exception`, and frame-locals capture — the exact path CAP-13
        forbids. `Captured` was defended by a test and this was not.
        """
        return (
            f"Message(external_id={self.external_id!r}, "
            f"thread_id={self.thread_id!r}, bytes={len(self.body)})"
        )


@runtime_checkable
class Draining(Protocol):
    """A source that also says how far it has **finished**.

    Separate from ``MailSource`` and checked with ``isinstance``, which is what
    makes the pipeline's fallback a decision rather than an accident. Read off
    the object with a bare ``getattr`` it was a silent side channel: misspell
    the attribute in an adapter and every walk quietly reverts to the ``max()``
    cursor story 20 removed — the failure mode being the original defect. Named
    here, ``tests/test_ingest.py`` can assert that the shipped source satisfies
    it, and the misspelling fails a case.
    """

    #: The furthest point behind which this source has left nothing unread, or
    #: ``None`` while it has drained nothing. Never *how far it got*.
    drained_through: str | None


@runtime_checkable
class MailSource(Protocol):
    name: str

    def fetch(self, *, since: str | None = None) -> AsyncIterator[Message]:
        """Yield messages newer than ``since``, oldest first.

        **The order is load-bearing for exactly one thing: a walk that stops
        early.** This docstring used to name two other reasons and story 20
        measured both away. A cursor advances monotonically without the order,
        because it is a ``max()`` and ``max()`` does not care; a failure
        part-way leaves its prefix captured without the order either, because
        receipts are stored per message and deduplicated by digest, so a re-run
        re-captures nothing.

        What the order is for is the case those two hide. A pull is cut — by a
        budget, a deadline, a provider that stops answering — and the mailbox
        is queried next time from a cursor that only moves forward. Yielded
        oldest first, what the cut leaves behind is everything *after* the
        cursor, and the next run reads it. Yielded newest first, what it leaves
        behind is everything *before* the cursor, and no query will ever name
        it again.
        """
        ...
