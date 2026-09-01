"""Civil-calendar arithmetic over stored stamps. Pure, integral, clockless.

Two subsystems need the same answer to *"how much time separates these two
stamps?"* and neither may reach a clock to get it:

* ``half.governance.aftercare`` — the thirty-day floor, which no module under
  ``half/crisis`` may compute with ``datetime`` at all (``tests/test_crisis.py``
  fails the build on the import).
* ``half.loops.timescale`` — whether an open loop has been silent past its own
  natural period, which is a function of ``last_movement``, the timescale and an
  injected ``now`` and of nothing else (CAP-6, AD-30).

Story 6c wrote this out by hand inside the aftercare schedule; story 8 needed
the same arithmetic and re-deriving it would have produced a second, weaker
parser. So it lives here, imports nothing from ``half``, and both callers take
it from one place. ``half.governance.aftercare`` re-exports every name, so the
crisis package still reads as one module.

**Every stamp is validated as a real instant, not merely parsed.** An impossible
date, an out-of-range field, a missing zone or an implausible year each
*shortens* whatever interval is being measured, which is the one direction that
matters for both callers: it would shorten aftercare's floor, and it would make
a loop look freshly moved when nothing had moved. ``2026-02-31`` folds to the
third of March and loses three days, ``2026-02-29`` is a date in a year that has
no such day, ``10:00:99`` is a minute that has no such second, a stamp with no
zone would be read as UTC while the spine's convention promises ``Z``, and a
year-one record is thirty days past every floor on the day it is written. All
refused, and a refusal is a ``None`` that every comparison declines to act on.
"""

from __future__ import annotations

import re
from typing import Final

#: Seconds in a day. Named because every period in Half is written in days and
#: compared in seconds, and a literal 86400 three lines down is how a floor
#: silently becomes an hour long.
DAY: Final[int] = 86_400

#: The bounds a stored stamp must fall inside to be a real instant. Not a guess
#: at the product's lifetime — a refusal of the values that are obviously not
#: one: a year-one record is past every floor on the day it is written, and a
#: year-9999 record never reaches one.
MIN_YEAR: Final[int] = 2000
MAX_YEAR: Final[int] = 2200

#: A stored stamp, per the spine's convention: UTC ISO-8601 with ``Z``, seconds
#: optional. The zone is **required** — the convention promises it, and a stamp
#: without one is a value from somewhere that does not follow the convention,
#: which is exactly the value not to guess about.
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


def days_from_civil(year: int, month: int, day: int) -> int:
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
    ``None``, and every caller treats ``None`` as *"do not act"* — the only safe
    direction, because each way a stamp can be wrong shortens the interval
    rather than lengthening it.
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
    return days_from_civil(year, month, day) * DAY + hour * 3600 + minute * 60 + second


def elapsed(since: object, now: object) -> int | None:
    """Seconds between two stamps, or ``None`` if either is not a real instant.

    A negative result — ``now`` before ``since``, which is a clock that ran
    backwards or a record written in the future — comes back as it is, and every
    floor above fails on it. A floor a negative number satisfies is not a floor,
    and a loop cannot be moved in the future to look freshly moved either.
    """
    start, end = instant(since), instant(now)
    if start is None or end is None:
        return None
    return end - start
