"""The `MailSource` port — the whole surface Half needs from a mailbox.

Narrow on purpose. Half needs to walk a mailbox forward from a cursor and stop;
everything else a mail API offers is not this product's concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
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


@runtime_checkable
class MailSource(Protocol):
    name: str

    def fetch(self, *, since: str | None = None) -> AsyncIterator[Message]:
        """Yield messages newer than ``since``, oldest first.

        Ordered so a cursor can advance monotonically and a failure part-way
        leaves everything before it already captured.
        """
        ...
