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

**So is the clock.** This adapter is the boundary where wall-clock time enters
the inbound path — a platform timestamp has to be normalised and a latch has to
be asked *now* — but the read itself belongs to ``half.schedule.clock``, which
is the one module in the tree that calls a clock at all (AD-30). Story 9a made
that a property the suite asserts rather than a sentence in a docstring, so the
three reads that used to live here take their instant from the injected
``Clock`` instead. Nothing about the behaviour changed; where the time comes
from did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol
from urllib.parse import quote

from half.channel.port import Inbound, Reachability, SendResult
from half.channel.window import LatchRule, ReachabilityTracker
from half.errors import ForbiddenRecipient, NotReachable, SendFailed
from half.schedule.clock import Clock, SystemClock, clamp, stamp

#: A Telegram username: letters, digits and underscores. Deliberately narrower
#: than the platform's own rule, because this decides where a deep link points
#: and the safe failure is the share sheet rather than a cleverly escaped
#: guess. Anything with a slash, a dot, a query or a fragment in it is not a
#: username — it is a path, and a path retargets the link.
_USERNAME = re.compile(r"[A-Za-z0-9_]{1,64}")

#: Telegram rejects messages over 4096 UTF-16 code units — not characters.
#: Measured with :func:`utf16_len`, because an emoji is one character and two
#: code units, so a code-point measure ships an unsendable message.
MAX_MESSAGE_UNITS = 4096


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
    #: Where "now" comes from. Injected so this adapter is not a second clock
    #: reader, and so a test can drive a window without waiting for one.
    clock: Clock = field(default_factory=SystemClock)

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
            epoch = _epoch(update.get("date"), arrived=self.clock.read().epoch)
            self.reach.note_inbound(main_id, epoch=epoch)
            yield Inbound(
                main_id=main_id,
                address=address,
                text=str(update.get("text", "")),
                external_id=str(update.get("message_id", "")),
                t=stamp(epoch),
            )

    # -- port: send ----------------------------------------------------------

    async def send(self, main_id: str, text: str) -> SendResult:
        """Send to ``main_id``'s own thread, and nowhere else."""
        address = self._address_for(main_id)
        if self.capability_query(main_id) is not Reachability.OPEN:
            raise NotReachable(
                f"{self.name} will not carry an unprompted message to {main_id}"
            )

        if not text.strip():
            # Telegram rejects an empty body; refusing here keeps a
            # self-inflicted 400 from being reported as a transport fault.
            return SendResult(external_id="", parts=0)

        chunks = split(text, MAX_MESSAGE_UNITS)
        last = ""
        for index, chunk in enumerate(chunks):
            try:
                last = await self.transport.send_message(address, chunk)
            except (TypeError, AttributeError, NameError):
                # A programming error, not a transport fault. Classifying it as
                # retryable would retry a bug forever.
                raise
            except Exception as exc:  # noqa: BLE001 - translated at the boundary
                raise SendFailed(
                    f"{exc} (chunk {index + 1} of {len(chunks)})",
                    retryable=_is_retryable(exc),
                ) from exc
        return SendResult(external_id=last, parts=len(chunks))

    # -- port: draft_link ----------------------------------------------------

    def draft_link(self, text: str, *, to: str | None = None) -> str:
        """A link the main taps to send ``text`` themselves.

        The only route to a third party. Half never sends on the main's behalf,
        so the main stays the sender in fact rather than in attribution (AD-25)
        — and on a platform where a bot cannot open a conversation at all, this
        is also the only thing that works.

        Two shapes, because Telegram has two. With a recipient, a deep link to
        that conversation with the message prefilled; without one, the share
        sheet so the main picks. An earlier version put the recipient in the
        share sheet's ``url`` parameter, which is the shared *link* rather than
        an addressee — it neither targeted anyone nor was discarded.

        **The recipient is validated, not merely escaped.** ``quote`` leaves
        ``/`` safe by default, so a stored handle containing a slash or a dot
        segment — ``asha/../someone``, ``asha/joinchat/xxxx`` — built a link
        that opened a *different* conversation while the offer beside it still
        showed the named person's name. That is the worst shape this function
        can take: a door labelled with somebody the main trusts that leads
        somewhere else. A handle that is not a plain Telegram username is not
        escaped into safety — it falls back to the share sheet, where the main
        picks the conversation themselves and cannot be misdirected.

        An all-``@`` handle used to strip to nothing and link to Telegram's
        home page; ``_USERNAME`` refuses it for the same reason.
        """
        target = to.lstrip("@") if to else ""
        if target and _USERNAME.fullmatch(target):
            return f"https://t.me/{quote(target, safe='')}?text={quote(text)}"
        return f"https://t.me/share/url?url=&text={quote(text)}"

    # -- port: capability_query ---------------------------------------------

    def capability_query(self, main_id: str) -> Reachability:
        """May Half send unprompted right now?

        Telegram's rule is a one-way latch: a bot can never message first, and
        once the main has written once it is open permanently. Callers get the
        answer and never the rule.
        """
        return self.reach.reachability(main_id, now=self.clock.read().epoch)

    # -- internals -----------------------------------------------------------

    def _address_for(self, main_id: str) -> str:
        for address, mid in self.mains.items():
            if mid == main_id:
                return address
        raise ForbiddenRecipient(
            f"{main_id!r} is not a registered main; Half sends only to its own main"
        )


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units — the unit Telegram actually counts."""
    return len(text.encode("utf-16-le")) // 2


def split(text: str, limit: int) -> list[str]:
    """Split ``text`` into pieces within ``limit`` UTF-16 code units.

    Prefers a paragraph break, then a line break, then a space, before cutting
    mid-word — a hard slice reads as corruption to the person on the other end.
    Empty pieces are never emitted: the platform rejects an empty body, and a
    whitespace-only reply should produce nothing rather than a bad request.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if utf16_len(text) <= limit:
        return [text] if text.strip() else []

    parts: list[str] = []
    rest = text
    while utf16_len(rest) > limit:
        window = _take(rest, limit)
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut <= 0:
            cut = len(window)
        head, rest = rest[:cut].rstrip(), rest[cut:].lstrip()
        if head:
            parts.append(head)
    if rest.strip():
        parts.append(rest)
    return parts


def _take(text: str, limit: int) -> str:
    """The longest prefix of ``text`` within ``limit`` UTF-16 code units.

    Never splits a surrogate pair: a half-emoji is invalid UTF-8 on the wire.
    """
    if utf16_len(text) <= limit:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if utf16_len(text[:mid]) <= limit:
            low = mid
        else:
            high = mid - 1
    return text[:low]


#: python-telegram-bot raises a typed hierarchy. Matching on type is both
#: correct and cheaper than matching substrings of a human-readable message,
#: which misclassifies anything phrased unexpectedly and anything whose text
#: merely mentions one of the words.
_PERMANENT_TYPES = ("Forbidden", "BadRequest", "InvalidToken", "ChatMigrated")
_RETRYABLE_TYPES = ("TimedOut", "NetworkError", "RetryAfter", "TimeoutError",
                    "ConnectionError")


def _is_retryable(exc: Exception) -> bool:
    """Transient transport faults are worth retrying; refusals are not."""
    for klass in type(exc).__mro__:
        if klass.__name__ in _PERMANENT_TYPES:
            return False
        if klass.__name__ in _RETRYABLE_TYPES:
            return True
    # Unknown shape: treat as permanent. Retrying something we do not
    # understand risks hammering a dead endpoint.
    return False


def _epoch(raw: object, *, arrived: float) -> float:
    """A usable timestamp from whatever the platform sent.

    A malformed date must not kill the receive loop for every main, so anything
    unreadable falls back to ``arrived`` — the instant the caller read, handed
    in rather than fetched, because this module is not the one that reads a
    clock.

    **A non-finite number is malformed, not absurd**, and the distinction is the
    regression review round 1 found: an absurd-but-real date (``1e30``) is kept
    as it is and clamped visibly at render, while ``NaN`` and ``±inf`` are not
    dates at all — one of them used to reach ``fromtimestamp`` and raise
    ``ValueError`` out of the receive loop for every main. They take the
    fallback, along with ``"nan"`` and ``"inf"``, which ``float()`` accepts.

    The value is clamped here as well as at render, so the *reachability latch*
    and the stored stamp are computed from the same number. They were not: a
    ``1e30`` date opened a window until the heat death of the universe while the
    stamp beside it read 2199.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        candidate = float(raw)
    elif isinstance(raw, str):
        try:
            candidate = float(raw)
        except ValueError:
            return arrived
    else:
        return arrived
    if candidate != candidate or candidate in (float("inf"), float("-inf")):
        return arrived
    return clamp(candidate)
