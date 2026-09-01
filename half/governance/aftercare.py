"""The aftercare schedule: the floor, the dwells, and what an instant is.

**Here rather than in ``half.crisis`` because two layers have to enforce it.**
Story 6c's first version put the thirty-day floor inside the pure function that
*decides* a step, and left ``ActorRegistry.restore_step`` — the write path that
actually raises a cap — checking only that a step was one rung. Two calls dated
two days after an entry took a main from `behave` to `assert`. A rule that
lives in one function is not an invariant; it is a convention that function
follows. So the numbers and the arithmetic live where both the actor and the
crisis path may import them, and both refuse.

``half.crisis.aftercare`` re-exports every name here, so the crisis package
still reads as one module.

**No clock, and structurally so.** Nothing here calls a clock — enforced by the
governance purity scan in ``tests/test_ladder.py`` — and the crisis package may
not even *import* ``datetime`` (``tests/test_crisis.py``). That is why the
civil-date computation exists at all: it is the price of a subsystem that
cannot contain a hidden clock read, and it is worth paying once.

**Once, and in one place.** The arithmetic itself moved to ``half.civil`` when
story 8 needed the same answer for open-loop silence. Re-deriving it there would
have produced a second parser that disagreed with this one about which stamps
are real, and the two subsystems it would then govern — a crisis floor and a
loop's own timescale — are the two where a stamp read too generously is a
silent failure. Every name is re-exported below, so this module is still the
one the crisis package imports.

**Every stamp is validated as a real instant, not merely parsed** — see
``half.civil``, which refuses an impossible date, an out-of-range field, a
missing zone and an implausible year, each of which *shortens the floor*. A
refusal restores nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from half.civil import (
    DAY,
    MAX_YEAR,
    MIN_YEAR,
    days_from_civil,
    elapsed,
    instant,
    is_leap,
    month_length,
)
from half.store.ops import CRISIS_ENTERED

__all__ = [
    "ANSWER_WINDOW_DAYS", "ASK_AGAIN_DAYS", "DAY", "FLOOR_DAYS", "MAX_YEAR",
    "MIN_YEAR", "MIRROR_DWELL_DAYS", "answered", "at_least", "days_from_civil",
    "elapsed", "entered_at", "expired", "instant", "is_leap", "month_length",
]

#: **The floor.** Nothing restores before this, by any path (CAP-12). Thirty
#: days is the number the capability states; changing it is an Ask-First change
#: and ``tests/test_aftercare.py`` pins it so that changing it fails by name.
FLOOR_DAYS: Final[int] = 30

#: The second step's own floor, measured from the entry like the first. The
#: mirror is not offered the moment the cap first lifts: coming off `behave`
#: has to have been true for a while before Half asks to go further, or
#: "stepwise" is two steps taken in the same breath.
MIRROR_DWELL_DAYS: Final[int] = 14

#: How long Half waits before putting the question again — after a decline, and
#: after a silence. Long enough that asking again is not nagging in the one
#: register where nagging is unforgivable; short enough that declining once is
#: visibly not for ever.
ASK_AGAIN_DAYS: Final[int] = 14

#: How long a question that has been put stays answerable. Shorter than the
#: interval before Half asks again, deliberately: an affirmative typed weeks
#: after the question is not that question's answer, and reading it as one is
#: the restore this whole schedule exists to prevent. Between the two, the cap
#: simply holds — which is the state a main who has not answered is in anyway.
ANSWER_WINDOW_DAYS: Final[int] = 7


def at_least(days: int, *, since: object, now: object) -> bool:
    """Whether at least ``days`` separate the two stamps, forwards.

    The one comparison every floor in this subsystem is written as, so there is
    no second spelling of *"has enough time passed"* to get the sign wrong in.
    Unreadable stamps and backwards time both answer ``False``.
    """
    gap = elapsed(since, now)
    return gap is not None and gap >= days * DAY


def expired(days: int, *, since: object, now: object) -> bool:
    """Whether ``days`` have passed *or* the interval is unreadable.

    The mirror image of ``at_least``, for the one case where the safe answer is
    the other one: a standing question whose age cannot be computed must be
    treated as stale rather than as answerable, because reading an unrelated
    affirmative as consent is the failure and letting a question lapse is not.
    A record stamped in the future is stale on the same terms.
    """
    gap = elapsed(since, now)
    return gap is None or gap < 0 or gap >= days * DAY


def entered_at(crisis: Mapping[str, Any] | None) -> str | None:
    """When the most recent crisis entry happened, or ``None``.

    ``None`` for a main who has never entered the mode, and for one whose entry
    an operator reversed — a reversal says the entry should never have happened
    and puts the ceiling back itself, so there is no floor to run and nothing
    for aftercare to restore.

    Reads the *folded* crisis record, which is the last one written, so the
    floor runs from the most recent entry and never from the first.
    """
    if not isinstance(crisis, Mapping):
        return None
    if crisis.get("state") != CRISIS_ENTERED:
        return None
    stamp = crisis.get("t")
    return stamp if isinstance(stamp, str) and stamp else None


def answered(
    care: Mapping[str, Any] | None, *, since: str
) -> tuple[str | None, str | None]:
    """The aftercare state and stamp, if they belong to the period at ``since``.

    A record written before — or at the same instant as — the most recent entry
    belongs to an aftercare period that a second crisis ended. It is not
    deleted; the log is append-only and what Half asked in July is still true
    about July. It is simply not this period's answer.

    The boundary is ``<=`` rather than ``<`` because stored stamps are
    minute-resolution: a previous period's *agreed* written in the same minute
    as a re-entry would otherwise survive its own period and leave the mirror
    resumed on the strength of an answer about a crisis that has since
    recurred.
    """
    if not isinstance(care, Mapping):
        return None, None
    stamp = care.get("t")
    if not isinstance(stamp, str):
        return None, None
    started, wrote = instant(since), instant(stamp)
    if started is None or wrote is None or wrote <= started:
        return None, None
    state = care.get("state")
    return (state if isinstance(state, str) else None), stamp
