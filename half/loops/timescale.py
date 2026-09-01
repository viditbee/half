"""A loop's own period, and silence computed against it (CAP-6, AD-30).

**Every loop carries its own timescale, and there is no default.** Farmland
moves in years and a workout routine in days. A shared default would be right
for one kind of wanting and wrong for every other, and the wrongness would be
silent: a farmland loop nagged monthly reads, to the main, as Half not
understanding them at all. So a loop with no timescale reports as **not
silent-detectable** and says which piece is missing, rather than borrowing a
number from a loop it is nothing like. Introducing a default of any kind is an
Ask-First change.

**Silence is computed, never stored.** It is a function of ``last_movement``,
the timescale and an injected ``now`` — three values and nothing else. A stored
``silent`` flag would be a fact about the moment it was written, and it would go
stale the instant the main did anything; worse, keeping it current means writing
on a read, which makes materialized state a function of read traffic rather than
of the log and breaks the replay invariant (AD-4, AD-30).

**Nothing here reads a clock.** ``now`` is the stamp the caller was handed. The
arithmetic is ``half.civil`` — the same validated, integral, clockless
computation the crisis floor runs on, imported rather than re-derived, because a
second parser would disagree with the first about which stamps are real and the
disagreement would be invisible.

**What silence is not.** It is *loop movement*, not Half's own contact. Whether
Half has raised this loop recently — and therefore whether raising it again
would be nagging — is a different fact with a different record, and it is story
5c's. Conflating them would make Half's own nudge look like the main's progress.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from half.civil import DAY, instant

#: The record fields this module reads. **Owned here**, because ``half.loops``
#: is the lower layer: ``half.store.records`` imports these to validate an
#: append and ``half.store.fold`` to build the loop entry, and the arrow cannot
#: run the other way without closing a cycle. One definition per name, flowing
#: upward, is what stops ``last_movement`` acquiring a second spelling — which
#: would be a loop that is permanently and invisibly not silent-detectable.
TIMESCALE: Final[str] = "timescale"
LAST_MOVEMENT: Final[str] = "last_movement"

#: Bumped for the reason ``states.VOCABULARY_VERSION`` is: the set of periods a
#: loop may declare is closed, and a build reading a log that names a scale it
#: has never heard of must degrade rather than guess.
VOCABULARY_VERSION: Final[int] = 1


class Timescale(StrEnum):
    """The natural period on which a wanting moves. The set is closed."""

    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


#: What each scale is worth in days: **one unit of the scale it names**. A loop
#: that moves in days has gone quiet after a day without movement; one that
#: moves in years has gone quiet after a year.
#:
#: The month and the year are nominal — thirty days and three hundred and
#: sixty-five — and that is deliberate rather than a rounding error. A
#: timescale is an order of magnitude for how a wanting moves, not a calendar
#: appointment: nothing about a farmland loop changes on the twenty-ninth of
#: February. Making these civil-calendar exact would add a leap-year branch to
#: a number whose whole job is to be approximately right, and would still be
#: wrong about what a "month" means to the main.
PERIOD_DAYS: Final[Mapping[str, int]] = {
    Timescale.DAYS: 1,
    Timescale.WEEKS: 7,
    Timescale.MONTHS: 30,
    Timescale.YEARS: 365,
}

#: The vocabulary as a frozen membership test, for the reason
#: ``states.LOOP_STATES`` is one: a lookup must never construct a ``Timescale``
#: for input that is not one.
TIMESCALES: Final[frozenset[str]] = frozenset(scale.value for scale in Timescale)

#: Why a loop is not silent-detectable. A reason rather than a bare ``False``,
#: because *"this loop has no timescale"* and *"this loop has never moved"* want
#: different answers from whatever asks — and because a caller handed only
#: ``False`` would have no way to tell either of them from *"it moved
#: yesterday"*.
NO_TIMESCALE: Final[str] = "no-timescale"
UNKNOWN_TIMESCALE: Final[str] = "unknown-timescale"
NO_MOVEMENT: Final[str] = "no-last-movement"
UNREADABLE_MOVEMENT: Final[str] = "unreadable-last-movement"
UNREADABLE_NOW: Final[str] = "unreadable-now"

#: The bare-date shape the loop projection carries — ``2026-03-12``. The belief
#: log's other stamps are full instants, and ``half.civil`` requires one; a
#: movement date is often all anybody knows, so it is widened to midnight UTC
#: here rather than by loosening the parser every floor in the product shares.
_DATE_ONLY: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}")

#: What a bare date is widened *to*. Midnight, never end-of-day, and pinned by
#: name so the choice is a decision rather than a literal three lines down: a
#: loop is treated as last moved at the **start** of that day, so the silence
#: computed from it is never shorter than the truth. Widening to ``T23:59Z``
#: instead would make every bare-date loop up to a day fresher than it is, which
#: is the direction that lets Half stay quiet about something it should raise.
DAY_STARTS_AT: Final[str] = "T00:00Z"


@dataclass(frozen=True, slots=True)
class Silence:
    """Whether one loop has been quiet past its own period, and by how much.

    A value. It decides nothing, writes nothing, and is recomputed from the
    fold every time it is wanted.

    ``detectable`` is false whenever the answer would have to be guessed, and
    ``reason`` then names which piece is missing. ``silent`` is never true while
    ``detectable`` is false — there is no path here from *"we cannot tell"* to
    *"the main has abandoned this"*.
    """

    detectable: bool = False
    silent: bool = False
    #: Set only when ``detectable`` is false. One of the module's reason
    #: constants.
    reason: str | None = None
    #: Days since ``last_movement``, clamped at zero. ``None`` when undetectable.
    elapsed_days: float | None = None
    #: The loop's own period in days. ``None`` when the timescale is missing or
    #: unreadable — never a borrowed default.
    period_days: int | None = None
    #: How many of the loop's own periods have passed. The unit every threshold
    #: above this module is written in, so that *"twelve periods"* means twelve
    #: months for a months-loop and twelve years for a years-loop, and one
    #: constant can mean the right thing for both.
    periods: float | None = None


def is_timescale(value: object) -> bool:
    """Whether ``value`` is a timescale this build knows. Never raises."""
    return isinstance(value, str) and value in TIMESCALES


def parse_timescale(value: object) -> Timescale:
    """``value`` as a ``Timescale``, or ``ValueError``.

    Raises for the reason ``states.parse_state`` does: the log is append-only,
    and a scale nothing recognised would be a loop whose silence — and therefore
    whose nagging bound — could never be computed, permanently.
    """
    if not is_timescale(value):
        raise ValueError(
            f"{value!r} is not a timescale; the vocabulary is "
            f"{', '.join(sorted(TIMESCALES))}"
        )
    return Timescale(value)


def period_days(value: object) -> int | None:
    """The period ``value`` names, in days, or ``None`` if it names none.

    ``None`` rather than a fallback. Every caller of this function is deciding
    whether to leave a main alone, and a fallback would decide it on a number
    that belongs to somebody else's wanting.
    """
    if not is_timescale(value):
        return None
    return PERIOD_DAYS[Timescale(value)]


def moment(stamp: object) -> int | None:
    """A movement stamp as whole seconds, or ``None``.

    Accepts both shapes the log carries: a full instant
    (``2026-03-12T09:00:00Z``) and a bare date (``2026-03-12``), which is widened
    to midnight UTC. Widening *down* rather than up is the conservative
    direction — a loop is treated as last moved at the start of that day, so the
    silence computed from it is never shorter than the truth, and Half is never
    the one who decided a loop was fresher than it is.
    """
    if not isinstance(stamp, str):
        return None
    text = stamp.strip()
    if _DATE_ONLY.fullmatch(text):
        text = f"{text}{DAY_STARTS_AT}"
    return instant(text)


def silence(loop: Mapping[str, object] | None, *, now: object) -> Silence:
    """Whether ``loop`` has been silent past its own timescale at ``now``.

    ``loop`` is the folded loop entry — the mapping ``half.store.fold`` keeps,
    carrying ``state``, ``timescale`` and ``last_movement``. Pure: the same
    entry and the same ``now`` give the same answer for ever.

    Every way this can fail to know produces ``detectable=False`` with a reason,
    and never a guess:

    * no timescale — the loop never declared one, and nothing here invents one;
    * an unknown timescale — a log from a later build, which degrades rather
      than taking the main's ranking down;
    * no ``last_movement`` — an opened loop nothing has moved yet has no age;
    * a stamp, on either side, that is not a real instant.
    """
    entry: Mapping[str, object] = loop if isinstance(loop, Mapping) else {}

    scale = entry.get(TIMESCALE)
    if scale is None or (isinstance(scale, str) and not scale.strip()):
        return Silence(reason=NO_TIMESCALE)
    period = period_days(scale)
    if period is None:
        return Silence(reason=UNKNOWN_TIMESCALE)

    moved = entry.get(LAST_MOVEMENT)
    if moved is None or (isinstance(moved, str) and not moved.strip()):
        return Silence(reason=NO_MOVEMENT, period_days=period)
    moved_at = moment(moved)
    if moved_at is None:
        return Silence(reason=UNREADABLE_MOVEMENT, period_days=period)
    # ``moment`` on both sides, not ``instant``. The two used to disagree about
    # what a stamp is — ``last_movement`` widened a bare date and ``now`` did
    # not — so a caller working in bare dates got ``unreadable-now`` for every
    # loop it owned while the same call with a ``T00:00Z`` reported hundreds of
    # periods. One shape rule, read on both sides, or the two drift apart and
    # the drift is a silent, total loss of detection.
    now_at = moment(now)
    if now_at is None:
        # The caller's own stamp, not the log's. Reported separately because
        # the fix is a different one: the log is fine and the caller is not.
        return Silence(reason=UNREADABLE_NOW, period_days=period)

    # Clamped, so a movement dated in the future cannot buy a loop negative
    # age — the same clamp ``salience.days_between`` applies, and for the same
    # reason: a skewed source must not make a loop look permanently fresh.
    days = max(0.0, (now_at - moved_at) / DAY)
    return Silence(
        detectable=True,
        # **Strictly greater, and the boundary is pinned** (see
        # ``tests/test_loops.py``). At exactly one period the loop has moved
        # inside its own rhythm — a weekly swim swum seven days ago is a loop
        # keeping to its period, not one that has gone quiet — so equality is
        # not silence. The direction matters because ``>=`` would put every
        # perfectly-kept loop one tick into the silent set for ever.
        silent=days > period,
        elapsed_days=days,
        period_days=period,
        periods=days / period,
    )
