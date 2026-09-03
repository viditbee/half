"""``next_pass_at``: local pre-dawn, with jitter, from a zone the main told
Half (AD-9). Pure, given an instant and a zone.

Three rules live here, and each of them is a rule the natural implementation
breaks.

**A due-time queue, never a global cron.** A cron fires one instant for
everybody. Timezone spread is not a defence — a user base that shares one
timezone shares one instant — so the spread has to be built rather than hoped
for. Each main carries their own due time and their own jitter.

**Jitter is derived, never drawn.** ``random`` would spread mains beautifully
and lose the spread on every restart: a main's due time would move each time
the process came up, so *"a restart does not lose when a main is next due"*
would be false in the one place it is easiest not to notice. The offset here is
a hash of the ``main_id`` — stable for ever, identical in every worker, uniform
across a population, and computed rather than stored.

**The zone is told, never inferred.** Not an IP, which is a VPN; not a phone
prefix, which survives emigration; not the host's ``TZ``, which is where the
server is and not where the person is; not a locale. That is the rule story 6b
set for region, applied to the other thing a main can be wrong about. A main
who has told Half nothing gets a **defined fallback that is recorded as a
fallback** — ``FALLBACK_ZONE``, written into the schedule record with
``TOLD_ZONE`` false — because the alternative to a visible fallback is a silent
guess, and a silent guess is indistinguishable from an answer.

Nothing here reads a clock, and nothing here reads ambient process state. The
instant arrives as an argument. ``datetime`` and ``zoneinfo`` are imported for
*conversion* — an epoch and a zone into a civil local time and back — which is
arithmetic over given values, and the scan in ``tests/test_schedule.py`` asserts
that no call in this module reads the time, the host zone or the environment.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from half.governance import ladder
from half.governance.ladder import License
from half.schedule import clock
from half.store.records import NEXT_PASS_AT, PASS_RAN, TOLD_ZONE, ZONE

#: ``ZONE``, ``NEXT_PASS_AT`` and ``TOLD_ZONE`` are **imported** rather than
#: spelled here, and re-exported for this package's own callers. The direction
#: is the one ``CONTACT``, ``REGION`` and ``PLAN`` already follow: the layer
#: that owns record shapes owns the spelling, and the layer above validates
#: nothing twice. (``LOOP`` runs the other way because the open-loop package is
#: *below* the store; this package is above it, and reversing the arrow here
#: would close a cycle through ``half.governance.ladder``, which imports
#: ``half.store.records`` itself.)
__all__ = [
    "Due", "FALLBACK_ZONE", "JITTER_SECONDS", "NEXT_PASS_AT", "PASS_RAN",
    "PRE_DAWN_HOUR", "TOLD_ZONE", "WINDOW_HOURS", "ZONE", "in_window", "jitter",
    "local_day", "next_pass_at", "resolve", "scheduled", "told", "zone_of",
]

#: Local pre-dawn. The pass runs while the main sleeps, so the window sits
#: after the late night and before the earliest plausible waking: from 03:00
#: local, two hours wide, so every due time falls in [03:00, 05:00) **local, as
#: the main would read a clock on their wall** — which is not the same thing as
#: 03:00 plus a number of seconds, and the difference is the whole of
#: ``next_pass_at``.
#:
#: **The window is fixed, and it is the promise.** Changing either number is an
#: Ask-First decision in story 9a: widening walks into somebody's morning and
#: narrowing undoes the spread that stops a thousand mains sharing an instant.
#: ``JITTER_SECONDS`` is *derived* rather than written, because a jitter window
#: wider than the window it jitters within is a due time outside the promise,
#: and two independent constants is how that happens without anybody deciding
#: it.
PRE_DAWN_HOUR: Final[int] = 3
WINDOW_HOURS: Final[int] = 2
JITTER_SECONDS: Final[int] = WINDOW_HOURS * 3_600

#: What a main with no told zone is scheduled in. UTC rather than the host's
#: zone, and that is the point: the host's zone is a fact about the server.
#: A main scheduled here is scheduled somewhere *defined*, and the schedule
#: record says so.
FALLBACK_ZONE: Final[str] = "UTC"

#: The shape an IANA zone key may take. ``ZoneInfo`` does its own key
#: validation, but this value arrives from a log record, so it is checked
#: before it becomes a filesystem lookup: letters, digits and the three
#: punctuation marks the database actually uses, no traversal, bounded length.
_ZONE_KEY: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9_+/-]{0,63}")


@dataclass(frozen=True, slots=True)
class Due:
    """When a main is next due, and on what basis.

    ``told`` travels with ``at`` rather than being recoverable from it, because
    *"a recorded fallback is used, and it is visible as a fallback"* is the
    whole requirement: a due time computed in UTC for a main who told Half
    nothing looks exactly like one computed in UTC for a main in Reykjavík.
    """

    #: Whole epoch seconds. Whole, because it is stored as a civil stamp and
    #: read back by ``half.civil.instant``, which has no sub-second precision —
    #: a due time that does not round-trip is a due time that drifts.
    at: int
    #: The zone the time was actually computed in.
    zone: str
    #: Whether ``zone`` is what the main told Half. False means ``FALLBACK_ZONE``
    #: and means it is recorded as a fallback.
    told: bool


def jitter(main_id: str) -> int:
    """This main's fixed offset into the pre-dawn window, in seconds.

    A hash rather than a draw. Deterministic per main, so the due time survives
    a restart and two workers agree about it; uniform over the window, so a
    thousand mains in one timezone do not share an instant. ``blake2b`` because
    it is in the standard library, is not ``hash()`` (which is randomised per
    process by ``PYTHONHASHSEED`` and would silently make this non-durable), and
    has no security role here beyond spreading well.
    """
    digest = hashlib.blake2b(main_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % JITTER_SECONDS


def _tzinfo(key: str) -> _dt.tzinfo:
    """The ``tzinfo`` for a validated key, without a lookup for the fallback.

    ``ZoneInfo`` needs a timezone database, and a host that has none is exactly
    the host on which every told zone resolves to ``FALLBACK_ZONE`` — so
    resolving the fallback through ``ZoneInfo`` too would raise on the one path
    that exists to keep working. ``FALLBACK_ZONE`` is UTC, and
    ``datetime.UTC`` is the same offset with no filesystem behind it.
    """
    if key == FALLBACK_ZONE:
        return _dt.UTC
    return ZoneInfo(key)


def resolve(zone: object) -> tuple[str, bool]:
    """``zone`` as a usable key plus whether it was told, never inferred.

    Every way a zone can be unusable — absent, not a string, the wrong shape,
    or a key this build's tz database does not hold — lands on the *same*
    recorded fallback. There is deliberately no branch that consults anything
    else: no host zone, no offset arithmetic from the given instant, no locale.
    A guess that is right most of the time is the failure this rule forbids,
    because nothing downstream could tell it from an answer.
    """
    if isinstance(zone, str) and _ZONE_KEY.fullmatch(zone.strip()):
        key = zone.strip()
        try:
            _tzinfo(key)
        except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
            return FALLBACK_ZONE, False
        return key, True
    return FALLBACK_ZONE, False


def in_window(at: float, zone: str) -> bool:
    """Whether ``at`` falls inside the promised local window in ``zone``.

    The predicate the promise is *stated* in, so that ``next_pass_at`` can check
    its own answer rather than assert it in a docstring — and so the tzdb sweep
    in ``tests/test_schedule.py`` asks exactly the same question the production
    code does, rather than a second, weaker rewording of it.
    """
    hour = _dt.datetime.fromtimestamp(at, _tzinfo(zone)).hour
    return PRE_DAWN_HOUR <= hour < PRE_DAWN_HOUR + WINDOW_HOURS


def local_day(at: float, zone: object) -> str:
    """The civil date ``at`` falls on, as the main would read it in ``zone``.

    *"At most one unprompted message a day"* is a promise about the main's own
    day, and a day is where the person is (CAP-8, AD-9). Twenty-four hours is
    not the same thing and gets both edges wrong in the direction that matters:
    a message at 23:50 and another at 00:10 are two messages on two days ten
    minutes apart, and one at 00:10 and one at 23:50 are two messages on **one**
    day, which the rule forbids. Only a civil date in the main's own zone
    answers either.

    Told, never inferred, and it lands on the same recorded fallback every other
    zone question in this module does: ``resolve`` is the one door, so a main
    who has told Half nothing gets ``FALLBACK_ZONE`` here exactly as they get it
    for their due time, and the two can never disagree about what day it is.

    Never raises, and reads no clock: ``at`` is an injected epoch — the tick's
    single read, handed down — and the conversion is arithmetic over given
    values, like ``in_window``'s.
    """
    key, _ = resolve(zone)
    return _dt.datetime.fromtimestamp(at, _tzinfo(key)).date().isoformat()


def _edge(tz: _dt.tzinfo, day: _dt.date, hour: int) -> int:
    """The instant at which ``day``'s local clock reaches ``hour``.

    ``replace(tzinfo=...)`` rather than ``astimezone()``: the latter with no
    argument reads the *host's* zone, which is the inference this module exists
    to refuse. A local time that does not exist — the hour a spring transition
    skips — resolves forward to the transition instant, which is the correct
    reading of *"when does the clock reach three"* on a day where it never
    shows three.
    """
    return int(
        _dt.datetime(day.year, day.month, day.day, hour, tzinfo=tz).timestamp()
    )


def next_pass_at(*, main_id: str, after: float, zone: object) -> Due:
    """The first pre-dawn instant strictly after ``after``, for this main.

    ``after`` is an injected epoch — the tick's single clock read, or a due time
    being advanced. Nothing here asks what time it is.

    **The jitter is placed inside the real window, not added to its start**, and
    that is the repair review round 1 found by sweeping the whole timezone
    database. Adding ``offset`` to a resolved 03:00 assumes the window is two
    real hours long, which is false on a transition day: EET moves 03:00 → 04:00
    on the last Sunday in March, so local 03:00 does not exist, resolving it
    yields 04:00, and nearly two hours of jitter carried eighteen zones out to
    **05:57 local** — outside the promise, in the hour people wake up. Chatham
    did the same in September. So both edges of the window are resolved in the
    zone, the offset is placed within the span they actually enclose, and the
    result is *checked against the promise* before it is returned. A day whose
    window does not exist at all is skipped rather than approximated.

    The search walks forward a civil day at a time rather than adding 86 400
    seconds, for the same family of reasons: across a transition two consecutive
    pre-dawns are 23 or 25 hours apart, and a scheduler that added a fixed day
    would drift an hour twice a year and eventually walk out of the window.
    """
    key, told = resolve(zone)
    tz = _tzinfo(key)
    offset = jitter(main_id)
    local = _dt.datetime.fromtimestamp(after, tz)
    for step in range(8):
        civil_day = (local + _dt.timedelta(days=step)).date()
        opens = _edge(tz, civil_day, PRE_DAWN_HOUR)
        closes = _edge(tz, civil_day, PRE_DAWN_HOUR + WINDOW_HOURS)
        span = closes - opens
        if span <= 0:
            # This local day has no pre-dawn window: a transition swallowed it
            # whole. Skipped rather than approximated — the honest answer is
            # tomorrow, and a due time outside the window is not a due time.
            continue
        at = opens + offset % span
        if at <= after:
            continue
        if not in_window(at, key):
            # Defence in depth against a transition shape nobody anticipated.
            # The promise is checked, never assumed; the sweep in the suite
            # asserts this branch is unreachable across the whole tz database.
            continue
        return Due(at=at, zone=key, told=told)
    # Unreachable for any zone in the database — the sweep proves it — and a
    # raise rather than a fallback because a scheduler that quietly returned a
    # past due time would run that main on every tick for ever.
    raise ValueError(  # pragma: no cover - defensive
        f"no pre-dawn instant after {after!r} in zone {key!r}"
    )


# -- the told zone: a belief, written and read like every other ---------------


def zone_of(records: Iterable[Mapping[str, Any]]) -> str | None:
    """The zone the main has told Half, or ``None``.

    Symmetric with ``half.crisis.contacts.region_of`` in every respect, and
    that is deliberate rather than incidental: it is the same rule — told,
    never inferred — asked with the same predicate.

    Gated on the ladder, so an unconfirmed guess Half wrote down cannot select
    a due time. ``None`` on no answer **and on two different answers**: a main
    who has told Half two zones has told it nothing this module may act on, and
    picking one would be the inference the rule forbids. The fallback is the
    better failure, and it is recorded.
    """
    told = {
        key
        for record in records
        if isinstance(record, Mapping)
        and ladder.own_rung(record) is License.ASSERT
        and (key := _key_of(record.get(ZONE))) is not None
    }
    if len(told) != 1:
        return None
    return told.pop()


def _key_of(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip()
    return key if _ZONE_KEY.fullmatch(key) else None


def told(zone: str, *, support: Any) -> dict[str, Any]:
    """The fields of the append that records the zone the main gave.

    The write side of *told, never inferred*, so that half of the rule is not a
    rule with no path. Born at the weakest rung like every belief, confirmed by
    the same event, read back by the same ladder question — and there is
    deliberately no argument here for an IP, a phone number, a locale or an
    offset observed from a message header.

    **Nothing in this build asks the question yet.** Where the main sleeps has
    no producer, for the same reason the phone book has none: the question
    engine is story 11. This is what its answer is written with, and until it
    exists every main runs on the recorded fallback.
    """
    key = _key_of(zone)
    if key is None:
        raise ValueError(
            "a zone is an IANA key the main told Half — 'Asia/Kolkata', not an "
            "offset, a country guess or a signal"
        )
    resolved, usable = resolve(key)
    if not usable:
        raise ValueError(
            f"this build's timezone database holds no zone {key!r}; refusing to "
            f"store a key that would silently fall back to {resolved}"
        )
    fields: dict[str, Any] = {ZONE: key}
    fields.update(ladder.admitted(support=support))
    return fields


def scheduled(due: Due, *, ran: bool = False) -> dict[str, Any]:
    """The fields of the ``schedule`` append that records ``due``.

    The zone and the told flag travel with the time because a due time alone
    cannot say whether it was chosen or defaulted to, and *"visible as a
    fallback"* is an acceptance criterion rather than a nicety.

    ``ran`` travels with them for the same kind of reason, one story over. The
    scheduler advances the due time of the main whose pass is about to run and
    of the unscheduled, the missed and the suspended ones whose passes are not,
    and it wrote one indistinguishable record for all four — so *"new or
    changed since this main's last pass"* read as *"since the scheduler last
    touched this main"*, and a main suspended for one night lost everything
    they had said that night, permanently. **False is the default** because
    three of the four callers are the ones that did not run anything, and
    because a field that defaults to *"a pass ran"* is one whose absence hides
    the defect it was added to close.
    """
    return {
        NEXT_PASS_AT: clock.stamp(due.at),
        ZONE: due.zone,
        TOLD_ZONE: due.told,
        PASS_RAN: ran,
    }
