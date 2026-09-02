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
from datetime import datetime

from half.channel.port import Reachability
# The record shape, from the module that owns it (a domain type, which is the
# one thing an adapter may depend on). This file already depended on the
# spelling of both names by reading them out of a record — it simply did so as
# two string literals, which is a dependency nothing could see and a rename
# would have silently turned into *"every main was never contacted"*.
from half.store.records import LEDGER, STATED

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
        # >= closes exactly at expiry, and a future-dated inbound must not
        # hold a window open indefinitely.
        if last_inbound_epoch > now or now - last_inbound_epoch >= self.seconds:
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

    def rebuild_from(self, main_id: str, records) -> None:
        """Restore last-inbound from a main's log.

        Without this the tracker is populated only by live traffic, so a
        restart reported every main as never-contacted and the morning surface
        — the whole reason unprompted contact is modelled — was dead on boot.
        The claim that this is derived and never a second source of truth is
        only true if it can actually be derived.
        """
        latest: float | None = None
        for record in records:
            stamp = record.data.get("t")
            if record.data.get(LEDGER) != STATED or not isinstance(stamp, str):
                continue
            epoch = _epoch_from_iso(stamp)
            if epoch is not None and (latest is None or epoch > latest):
                latest = epoch
        if latest is not None:
            self.note_inbound(main_id, epoch=latest)


def _epoch_from_iso(stamp: str) -> float | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
