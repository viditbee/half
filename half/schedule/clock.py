"""The one clock reader (AD-30).

Every module built so far takes an injected ``now``. That is what makes the
fold replayable, the aftercare floor arithmetic auditable and every test
deterministic. A scheduler necessarily breaks the rule — it is the thing that
knows what time it is — so the break is confined to this file, and *"who reads
a clock"* becomes a question with one answer rather than a convention.

``tests/test_schedule.py`` asserts it over the whole package: exactly one module
under ``half/`` calls anything ambient, and it is this one. That scan is the
reason ``half.channel.telegram`` imports ``moment`` and ``stamp`` from here
rather than calling ``time.time()`` itself — the adapter is still the boundary
where wall-clock time enters the inbound path, but the *read* happens here.

Nothing in this module imports anything from ``half``. It is the bottom of the
tree, so that the modules which need an instant can take one without acquiring
the scheduler, the actor or the store along with it.
"""

from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass
from typing import Final, Protocol

#: The stored-stamp convention, spelled once: UTC ISO-8601, whole seconds, ``Z``
#: (the spine's Time convention, and the shape ``half.civil`` will read back).
#: Sub-second precision is dropped rather than carried: a due time is a civil
#: instant, and ``half.civil.instant`` refuses a stamp it cannot read.
_UTC: Final[_dt.tzinfo] = _dt.UTC

#: The range a stamp may name, and it is **the range the store validates**
#: rather than the range ``datetime`` can render. ``half.civil.instant`` refuses
#: anything outside 2000–2200, and every floor, timescale and due-time
#: comparison in the product is built on it — so clamping to 0001 or 9999, as
#: the first version of this module did, produced a value that renders fine,
#: stores fine, and is then silently unreadable by every consumer. A clamp into
#: a range the rest of the system rejects is not a clamp; it is a slower version
#: of the same failure.
#:
#: Spelled as constants here rather than imported from ``half.civil``, because
#: this module deliberately imports nothing from ``half`` — it sits at the
#: bottom of the tree so that anything needing an instant can take one without
#: acquiring the store. ``tests/test_schedule.py`` asserts the two agree, which
#: is the check that would catch them drifting.
MIN_EPOCH: Final[float] = 946_684_800.0    # 2000-01-01T00:00:00Z
MAX_EPOCH: Final[float] = 7_258_118_399.0  # 2199-12-31T23:59:59Z


@dataclass(frozen=True, slots=True)
class Now:
    """One instant, read once and injected downward.

    Both representations travel together on purpose. ``epoch`` is what
    arithmetic is done in — comparing a due time, measuring a grace window —
    and ``stamp`` is what is *stored*, because the spine's convention is
    ISO-8601 with ``Z`` on every stored timestamp. Deriving one from the other
    at each call site is how a tick ends up comparing against one instant and
    recording another.
    """

    epoch: float
    stamp: str


def clamp(epoch: object) -> float:
    """``epoch`` brought inside the range the store will accept.

    **NaN is handled before the comparison, not by it.** ``min``/``max``
    propagate NaN — ``min(max(nan, lo), hi)`` is ``nan`` — so the obvious clamp
    passes a NaN straight through to ``fromtimestamp``, which raises
    ``ValueError``, out of a receive loop serving every main. Review round 1
    reproduced exactly that. A NaN is not a small number or a large one; it is
    an absent one, and the floor is what absent means here.

    Anything that is not a number at all — a string, ``None``, a dict — is the
    same absence and gets the same answer, because this function's contract is
    that it never raises.
    """
    try:
        value = float(epoch)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return MIN_EPOCH
    if value != value:  # NaN, which compares false against everything
        return MIN_EPOCH
    if value < MIN_EPOCH:
        return MIN_EPOCH
    if value > MAX_EPOCH:
        return MAX_EPOCH
    return value


def stamp(epoch: object) -> str:
    """``epoch`` seconds as a stored UTC stamp. Pure — reads no clock.

    **Clamped rather than raising, and clamped into the range the rest of the
    system accepts.** The two callers are a scheduler tick and an inbound
    adapter, and neither may be taken down by a hostile number: a platform that
    sends ``date: 1e30`` — or ``NaN``, or a string — would otherwise end the
    receive loop for every main. That is what the helper this replaced was for,
    and its ``OverflowError``/``OSError``/``ValueError`` guards did not survive
    the move; they are here instead, one layer lower, where every caller gets
    them.

    A clamped stamp is wrong by a visible margin, which is a failure somebody
    can act on. A stamp of ``0001-01-01`` is wrong *and* unreadable by
    ``half.civil``, which is a failure nobody can see.
    """
    bounded = clamp(epoch)
    try:
        moment_ = _dt.datetime.fromtimestamp(bounded, _UTC)
    except (OverflowError, OSError, ValueError):  # pragma: no cover - platform
        # A platform whose ``fromtimestamp`` refuses a value inside our own
        # bounds. The floor is representable everywhere; never raise from here.
        moment_ = _dt.datetime.fromtimestamp(MIN_EPOCH, _UTC)
    return moment_.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def moment(epoch: object) -> Now:
    """A ``Now`` for a *given* epoch. Pure — the seam every test injects at.

    ``epoch`` is clamped, so the arithmetic half and the stored half of a ``Now``
    always describe the same instant. Deriving one from a raw value and the
    other from a clamped one is how a tick compares against one moment and
    records another.
    """
    bounded = clamp(epoch)
    return Now(epoch=bounded, stamp=stamp(bounded))


class Clock(Protocol):
    """The whole surface anything needs from wall-clock time."""

    def read(self) -> Now:
        ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    """The real clock. **The only ambient read in the tree.**

    One method, one call, and no other behaviour, so that the scan asserting
    there is exactly one clock reader has one small thing to point at.
    """

    def read(self) -> Now:
        return moment(time.time())


@dataclass(frozen=True, slots=True)
class FrozenClock:
    """A clock that returns the instant it was given.

    Production code, not a test helper that happens to live here: it is the
    injection seam that makes *"everything below takes an injected now"* a
    thing a caller can actually do, and the reason no test in this suite needs
    to patch a module attribute to control time.
    """

    at: float

    def read(self) -> Now:
        return moment(self.at)
