"""Telegram adapter — long-polling, no public URL (AD-16).

Telegram is the self-host default because long-polling works from behind NAT.
WhatsApp Cloud API needs a public webhook, which turns a ninety-second install
into a domain and a tunnel; the honest split is in the spine.

The adapter shape follows hermes-agent's ``BasePlatformAdapter`` (MIT, © 2025
Nous Research): a small abstract surface plus declarative capability
attributes, so presentation differences stay inside the adapter instead of
leaking into callers.

**Transport is injected.** ``Transport`` is the whole surface this adapter
needs from the network, so the suite runs offline and hermetically while the
production implementation is a thin `python-telegram-bot` wrapper.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol
from urllib.parse import quote

from half.channel.port import Inbound, Reachability, SendResult
from half.channel.window import LatchRule, ReachabilityTracker
from half.errors import ForbiddenRecipient, NotReachable, SendFailed, UnknownSender

#: Telegram rejects messages over 4096 UTF-16 code units. Split below it.
MAX_MESSAGE_CHARS = 4096


class Transport(Protocol):
    """The network surface the adapter needs. Injected so tests stay offline."""

    async def poll(self) -> "AsyncIterator[dict]":  # type: ignore[name-defined]
        ...

    async def send_message(self, chat_id: str, text: str) -> str:
        ...


@dataclass(slots=True)
class TelegramChannel:
    """Implements the four-operation ``Channel`` port for Telegram."""

    transport: Transport
    #: platform address -> main_id. An address absent here is not a main.
    mains: dict[str, str]
    name: str = "telegram"
    #: Telegram's typing indicator is a native bubble, not a status line.
    supports_status_text: bool = False
    reach: ReachabilityTracker = field(
        default_factory=lambda: ReachabilityTracker(rule=LatchRule())
    )

    # -- port: receive -------------------------------------------------------

    async def receive(self) -> AsyncIterator[Inbound]:
        """Yield inbound messages from registered mains.

        A message from an unregistered address is dropped without its text
        reaching a log line — an unknown sender is not a main, and Half holds
        nothing about people who are not its main.
        """
        async for update in self.transport.poll():
            address = str(update.get("chat_id", ""))
            main_id = self.mains.get(address)
            if main_id is None:
                continue
            epoch = float(update.get("date", time.time()))
            self.reach.note_inbound(main_id, epoch=epoch)
            yield Inbound(
                main_id=main_id,
                address=address,
                text=str(update.get("text", "")),
                external_id=str(update.get("message_id", "")),
                t=_iso(epoch),
            )

    # -- port: send ----------------------------------------------------------

    async def send(self, main_id: str, text: str) -> SendResult:
        """Send to ``main_id``'s own thread, and nowhere else."""
        address = self._address_for(main_id)
        if self.capability_query(main_id) is not Reachability.OPEN:
            raise NotReachable(
                f"{self.name} will not carry an unprompted message to {main_id}"
            )

        chunks = split(text, MAX_MESSAGE_CHARS)
        last = ""
        for chunk in chunks:
            try:
                last = await self.transport.send_message(address, chunk)
            except Exception as exc:  # noqa: BLE001 - translated at the boundary
                raise SendFailed(str(exc), retryable=_is_retryable(exc)) from exc
        return SendResult(external_id=last, parts=len(chunks))

    # -- port: draft_link ----------------------------------------------------

    def draft_link(self, text: str, *, to: str | None = None) -> str:
        """A link the main taps to send ``text`` themselves.

        The only route to a third party. Half never sends on the main's behalf,
        so the main stays the sender in fact rather than in attribution (AD-25)
        — and on a platform where a bot cannot open a conversation at all, this
        is also the only thing that works.
        """
        target = f"@{to}" if to else ""
        return f"https://t.me/share/url?url={quote(target)}&text={quote(text)}"

    # -- port: capability_query ---------------------------------------------

    def capability_query(self, main_id: str) -> Reachability:
        """May Half send unprompted right now?

        Telegram's rule is a one-way latch: a bot can never message first, and
        once the main has written once it is open permanently. Callers get the
        answer and never the rule.
        """
        return self.reach.reachability(main_id, now=time.time())

    # -- internals -----------------------------------------------------------

    def _address_for(self, main_id: str) -> str:
        for address, mid in self.mains.items():
            if mid == main_id:
                return address
        raise ForbiddenRecipient(
            f"{main_id!r} is not a registered main; Half sends only to its own main"
        )


def split(text: str, limit: int) -> list[str]:
    """Split ``text`` into pieces under ``limit``, preserving order.

    Prefers a paragraph break, then a line break, then a space, before cutting
    mid-word — a hard slice at the limit reads as corruption to the person on
    the other end.
    """
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut <= 0:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


def _is_retryable(exc: Exception) -> bool:
    """Transient transport faults are worth retrying; refusals are not."""
    text = f"{type(exc).__name__} {exc}".lower()
    permanent = ("forbidden", "blocked", "not found", "unauthorized", "bad request")
    return not any(token in text for token in permanent)


def _iso(epoch: float) -> str:
    """Epoch seconds to a UTC ISO-8601 stamp.

    The adapter is the boundary where wall-clock time enters. Nothing
    downstream reads a clock, which is what keeps the fold pure (AD-30).
    """
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(epoch, _dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
