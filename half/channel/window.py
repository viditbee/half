"""Reachability: whether Half may contact a main unprompted (AD-7).

Derived, never stored. Whether the platform permits contact is a function of
the last inbound message, which is already an event in the main's log — so
this module computes and keeps no second source of truth (AD-3).

The two platforms disagree about the rule, which is why the port exposes an
answer rather than a mechanism:

*Telegram* is a one-way latch. A bot may never open a conversation; once the
user has written once, it is open permanently.

*WhatsApp Cloud API* is a rolling window. Free-form is permitted for 24 hours
after the main's last message; outside it, only pre-approved templates with an
active opt-in.

The reference implementation is no help here. hermes-agent's WhatsApp adapter
never computes a window because every one of its sends answers a user message
directly — it is always inside the window by construction. Half is outside it
by design: the morning surface and every nudge are unprompted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from half.channel.port import Reachability

#: WhatsApp Cloud API's customer service window.
WHATSAPP_WINDOW_SECONDS = 24 * 60 * 60


@dataclass(slots=True)
class LatchRule:
    """Telegram: a bot cannot send first; one inbound opens it forever."""

    def reachability(self, *, last_inbound_epoch: float | None, now: float) -> Reachability:
        if last_inbound_epoch is None:
            return Reachability.NEVER_CONTACTED
        return Reachability.OPEN


@dataclass(slots=True)
class RollingWindowRule:
    """WhatsApp: free-form only within ``seconds`` of the last inbound."""

    seconds: float = WHATSAPP_WINDOW_SECONDS

    def reachability(self, *, last_inbound_epoch: float | None, now: float) -> Reachability:
        if last_inbound_epoch is None:
            return Reachability.NEVER_CONTACTED
        if now - last_inbound_epoch > self.seconds:
            return Reachability.WINDOW_CLOSED
        return Reachability.OPEN


@dataclass(slots=True)
class ReachabilityTracker:
    """Last-inbound bookkeeping for one platform's rule.

    Holds only a cache of what the log already knows, so it can be rebuilt at
    any time and never disagrees with the store about history.
    """

    rule: LatchRule | RollingWindowRule
    _last_inbound: dict[str, float] = field(default_factory=dict)

    def note_inbound(self, main_id: str, *, epoch: float) -> None:
        previous = self._last_inbound.get(main_id)
        if previous is None or epoch > previous:
            self._last_inbound[main_id] = epoch

    def last_inbound(self, main_id: str) -> float | None:
        return self._last_inbound.get(main_id)

    def reachability(self, main_id: str, *, now: float) -> Reachability:
        return self.rule.reachability(
            last_inbound_epoch=self._last_inbound.get(main_id), now=now
        )
