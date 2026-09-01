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
civil-date computation below is written out: it is the price of a subsystem
that cannot contain a hidden clock read, and it is worth paying once.

**Every stamp is validated as a real instant, not merely parsed.** An
impossible date, an out-of-range field, a missing zone or an implausible year
each *shortens the floor*, which is the one direction that matters:
``2026-02-31`` folded to the third of March and lost three days, ``2026-02-29``
parsed in a year that has no such day, ``10:00:99`` parsed a minute that has no
such second, a stamp with no zone was read as UTC while the convention promises
``Z``, and a year-one record was thirty days past its floor on the day it was
written. All refused, and a refusal restores nothing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from half.store.ops import CRISIS_ENTERED

#: Seconds in a day. Named because every constant here is written in days and
#: compared in seconds, and a literal 86400 three lines down is how a floor
#: silently becomes an hour long.
DAY: Final[int] = 86_400

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

#: The bounds a stored stamp must fall inside to be a real instant. Not a
#: guess at the product's lifetime — a refusal of the values that are obviously
#: not one: a year-one record is thirty days past its floor on the day it is
#: written, and a year-9999 record never reaches one.
MIN_YEAR: Final[int] = 2000
MAX_YEAR: Final[int] = 2200

#: A stored stamp, per the spine's convention: UTC ISO-8601 with ``Z``, seconds
#: optional. The zone is **required** — the docstring convention promises it,
#: and a stamp without one is a value from somewhere that does not follow the
#: convention, which is exactly the value not to guess about.
_STAMP: Final[re.Pattern[str]] = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?[Zz]$"
)

_MONTH_LENGTHS: Final[tuple[int, ...]] = (
    31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31,
)


def is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def month_length(year: int, month: int) -> int:
    """How many days that month actually has. ``2026-02-29`` is not a date."""
    if month == 2 and is_leap(year):
        return 29
    return _MONTH_LENGTHS[month - 1]


def _days_from_civil(year: int, month: int, day: int) -> int:
    """Days from 1970-01-01 to a civil date. Exact, integral, and clockless.

    Howard Hinnant's algorithm, which is what the standard libraries use. It is
    written out because no module under ``half/crisis`` may import
    ``datetime`` — a rule that exists so the one subsystem where a hidden clock
    read would be unrecoverable cannot contain one.

    It is total over *every* triple, including impossible ones — ``2026-02-31``
    folds to the third of March — which is precisely why ``instant`` validates
    the date before calling it rather than after.
    """
    year -= month <= 2
    era = (year if year >= 0 else year - 399) // 400
    year_of_era = year - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146_097 + day_of_era - 719_468


def instant(stamp: object) -> int | None:
    """``stamp`` as whole seconds, or ``None`` if it is not a real instant.

    Never raises and never guesses. A value this build cannot read produces
    ``None``, every comparison against ``None`` declines to restore, and the
    main stays capped — the only safe direction, because each way a stamp can
    be wrong shortens the floor rather than lengthening it.
    """
    if not isinstance(stamp, str):
        return None
    found = _STAMP.match(stamp.strip())
    if found is None:
        return None
    year, month, day, hour, minute = (int(part) for part in found.groups()[:5])
    second = int(found.group(6) or 0)
    if not MIN_YEAR <= year <= MAX_YEAR:
        return None
    if not 1 <= month <= 12:
        return None
    if not 1 <= day <= month_length(year, month):
        return None
    if hour > 23 or minute > 59 or second > 59:
        # Leap seconds are the one value this refuses that a calendar allows.
        # A stored stamp is produced by ``datetime`` at the adapter and never
        # carries one, so refusing is the safe reading of a value that should
        # not exist.
        return None
    return _days_from_civil(year, month, day) * DAY + hour * 3600 + minute * 60 + second


def elapsed(since: object, now: object) -> int | None:
    """Seconds between two stamps, or ``None`` if either is not a real instant.

    A negative result — ``now`` before ``since``, which is a clock that ran
    backwards or a record written in the future — comes back as it is, and
    every floor below fails on it. A floor a negative number satisfies is not a
    floor, and a *future* record must not suppress a question either: callers
    ask ``at_least`` rather than comparing by hand.
    """
    start, end = instant(since), instant(now)
    if start is None or end is None:
        return None
    return end - start


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
