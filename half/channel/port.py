"""The ``Channel`` port — exactly four operations (AD-7).

The actor never learns which platform it is on. Every platform difference —
message length limits, whether an unprompted message is permitted right now,
how a draft to a third party is expressed — is answered here or not at all.

The port stays deliberately narrow. gbrain's own docs warn that their storage
engine interface grew past a hundred methods and could no longer be reasoned
about; a port that absorbs every platform capability ends up the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Inbound:
    """One message from a main, normalized away from its platform."""

    main_id: str
    address: str
    text: str
    #: Platform message id, for reply threading and de-duplication.
    external_id: str
    #: Caller-supplied ISO-8601 stamp. Adapters read the clock; nothing
    #: downstream of here does.
    t: str


@dataclass(frozen=True, slots=True)
class SendResult:
    external_id: str
    #: How many physical messages the text became after splitting.
    parts: int


class Reachability(StrEnum):
    """Whether Half may send to this main unprompted, and why not.

    Named for the question rather than the mechanism because the platforms
    disagree about what the mechanism is: Telegram's rule is a one-way latch
    (a bot may never open a conversation, but once the user has written, it is
    open forever), while WhatsApp's is a rolling 24-hour window. A caller only
    ever needs the answer.
    """

    #: An unprompted free-form message is permitted.
    OPEN = "open"
    #: The main has never written, so the platform forbids first contact.
    NEVER_CONTACTED = "never_contacted"
    #: A window has lapsed. Free-form is out; an approved template may apply.
    WINDOW_CLOSED = "window_closed"

    @property
    def may_send_freeform(self) -> bool:
        return self is Reachability.OPEN


@runtime_checkable
class Channel(Protocol):
    """The whole surface between Half and a messaging platform."""

    name: str

    async def receive(self) -> "AsyncIterator[Inbound]":  # type: ignore[name-defined]
        """Yield inbound messages until cancelled."""
        ...

    async def send(self, main_id: str, text: str) -> SendResult:
        """Send to ``main_id``'s own thread.

        Raises ``ForbiddenRecipient`` for any other address (AD-25) and
        ``NotReachable`` when ``capability_query`` would refuse.
        """
        ...

    def draft_link(self, text: str, *, to: str | None = None) -> str:
        """A link the main taps to send ``text`` themselves.

        The only way anything reaches a third party. Half never sends on the
        main's behalf, so the main stays the sender in fact and not merely in
        attribution (AD-25).
        """
        ...

    def capability_query(self, main_id: str) -> Reachability:
        """May Half send an unprompted message to this main right now?

        The single home of every platform contact rule. Callers branch on the
        answer; they never learn the rule.
        """
        ...
