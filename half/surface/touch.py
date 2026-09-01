"""What Half raised, what day it spent, and what it cited (CAP-8, AD-3).

**A touch is not a movement, and that is the first reason this file exists.**
Story 8 recorded when a loop last *moved* and refused, in writing, to record
when Half last *raised* it: conflating them makes Half's own attention look
like the main's progress, so a farmland loop nudged every morning would read to
every ranking function above as a farmland loop advancing every morning. The
nagging bound needs the second fact; the ranking needs the first; neither may
be computed from the other, and neither path may write the other's field.

That separation is structural rather than agreed. Nothing in this module can
produce a ``state`` or a ``last_movement``: every function builds a fixed
dictionary, ``records.validate_touch_fields`` refuses anything outside
``TOUCH_FIELDS`` before the record is durable, and ``tests/test_nagging.py``
asserts by AST that neither name appears in this file at all. The mirror rule
holds from the other side — ``half.loops.ledger`` has no function that writes a
touch, and says so.

**A raise is not a spent day either, and that is the second.** A touch does one
of two jobs, or both:

* it **raises a loop** (``loop``), which the per-loop bound measures against;
* it **spends the day** (``local_day`` plus ``sent``), which the one-a-day rule
  reads.

Review found why they cannot be one field. The rule used to read *the last
raise of any loop*, so CAP-10's interrupt — explicitly a second thing that will
raise a loop — would have silently consumed the morning budget the day it
landed, with no change anywhere near the surface to say so. The interrupt will
call ``raised``, which marks no day. Only ``spoke`` and ``repaired`` do.

**The day is stored, never recomputed.** A marker recomputed from the record's
stamp under whatever zone is current is how a main who moves west gets two
messages five hours apart, which review reproduced. ``spoke`` takes the day as
an argument and writes it down.

**An append, never an edit** (AD-3). Like ``half.governance.ladder`` and
``half.loops.ledger``, nothing here writes: every function returns the *fields*
of a ``touch`` record and the caller appends them under the main's own mutex
(AD-1). That keeps the rules pure and testable without a store, and keeps the
single writer where AD-1 put it.

**Content-free** (AD-22). A touch carries a loop slug, a civil date, a flag,
and the kind and id of the thing in the preceding pass it came from. It never
carries a claim, a message, a phrase, or a word of what was actually said.

**Every touch that surfaced something cites its origin**, and the citation is
required rather than encouraged: *"nothing is surfaced that cannot say where it
came from"* is one of this story's Always rules. A repair marker — which raised
nothing and sent nothing — cites nothing, because there is nothing to cite.

Pure and clockless: the stamp and the day are the caller's (AD-30).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from half.errors import TouchError
from half.loops.timescale import moment
from half.store.ops import TOUCH_ORIGINS
from half.store.records import (
    LOCAL_DAY,
    LOOP,
    ORIGIN_ID,
    ORIGIN_KIND,
    SENT,
    is_civil_day,
)

__all__ = [
    "LOCAL_DAY", "LOOP", "ORIGIN_ID", "ORIGIN_KIND", "Origin", "SENT",
    "TOUCH_ORIGINS", "day_of", "marks_day", "origin_of", "raised",
    "raised_at", "raises_loop", "repaired", "spoke", "spoken_on",
    "traceable",
]


@dataclass(frozen=True, slots=True)
class Origin:
    """Where a surface came from: a kind out of the closed set, and an id.

    A value. It decides nothing and writes nothing — it exists so that *"this
    came from last night's pass"* is a fact the log holds rather than a claim a
    docstring makes.

    ``kind`` is one of ``half.store.ops.TOUCH_ORIGINS``: a tension, a loop
    transition, or an ingested item. The set is closed for the reason every
    other vocabulary in this codebase is closed — a fourth kind, once durable,
    is a provenance no build can name — and it is *checked* rather than
    documented, because a helpful-looking ``kind="inferred"`` is exactly how a
    surface that cites nothing gets past a rule everybody agrees with.
    """

    kind: str
    id: str

    @property
    def traceable(self) -> bool:
        """Whether this origin actually says where something came from.

        The predicate, read by the runtime **and** by the tests, rather than a
        list of shapes each of them checks separately. A candidate whose origin
        answers ``False`` is not surfaced — see ``half.surface.choose`` — so a
        new way of failing to cite anything is caught by the same rule as a
        known one.
        """
        return traceable(self.kind, self.id)


def traceable(kind: object, origin_id: object) -> bool:
    """Whether ``kind`` and ``origin_id`` name a thing in a pass. Never raises.

    Deliberately a free function as well as a property: the append gate, the
    chooser and the tests all ask the same question about values that have not
    necessarily been wrapped in an ``Origin`` yet, and three spellings of *"is
    this traceable"* is how one of them ends up weaker than the others.
    """
    return (
        isinstance(kind, str)
        and kind in TOUCH_ORIGINS
        and isinstance(origin_id, str)
        and bool(origin_id.strip())
    )


def raised(loop_id: object, *, origin: Origin) -> dict[str, Any]:
    """The fields of a touch that raises ``loop_id`` and **spends no day**.

    The shape CAP-10's interrupt will use. It bounds the loop — the next raise
    on it is measured against this one — and it leaves the main's one
    unprompted morning message untouched, because it carries no ``local_day``.

    That the interrupt gets its own shape rather than reusing the morning's is
    the whole of *"mark which touches count"*: before review, every raise was a
    day marker, so the day the interrupt shipped it would have started eating
    mornings with no edit anywhere near this file.
    """
    return {LOOP: _loop_id(loop_id), **_cited(origin)}


def spoke(
    *, day: object, origin: Origin, loops: object = ()
) -> dict[str, Any]:
    """The fields of the touch that spends ``day`` on a message that was sent.

    ``day`` is the main's **own** civil date, computed once by the caller in
    the zone the main told Half and written down — never recomputed later. A
    marker recomputed under whatever zone is current is how a main who moves
    west gets two messages five hours apart.

    ``loops`` is what the message touched, and it may be empty: a candidate
    built from beliefs that sit on no wanting raises nothing, and is bounded by
    the day marker and by the transition rule instead of by the nagging bound.
    A candidate touching **more than one** loop needs one record per loop —
    each has its own period — so this returns the fields for one of them and
    the caller appends the rest through ``raised``.
    """
    fields: dict[str, Any] = {LOCAL_DAY: _day(day), SENT: True, **_cited(origin)}
    first = _first_loop(loops)
    if first is not None:
        fields[LOOP] = first
    return fields


def repaired(*, day: object) -> dict[str, Any]:
    """The fields of a day marker that spends ``day`` with **no message sent**.

    The one path on which Half consumes a day deliberately without speaking,
    and it exists so that an unreadable day marker costs one morning instead of
    every morning after it. Review found the permanent version: the marker is
    replaced only by a later marker, a later marker is written only when Half
    is about to speak, and that is exactly what an unreadable marker blocks —
    so a single corrupt record silenced a main for ever, with no recovery, no
    alert and no counter.

    It raises nothing and sent nothing, so it cites nothing: there is no origin
    to name, because nothing was surfaced. ``sent`` is ``False``, which is what
    keeps *"a message was sent"* honest and gives the metrics path the two
    outcomes to count separately.
    """
    return {LOCAL_DAY: _day(day), SENT: False}


# -- reading -----------------------------------------------------------------


def raises_loop(touch: Mapping[str, Any] | None) -> bool:
    """Whether this record raised a wanting."""
    return isinstance(touch, Mapping) and bool(_text(touch.get(LOOP)))


def marks_day(touch: Mapping[str, Any] | None) -> bool:
    """Whether this record spent one of the main's days."""
    return isinstance(touch, Mapping) and bool(_text(touch.get(LOCAL_DAY)))


def day_of(touch: Mapping[str, Any] | None) -> str | None:
    """The civil day this marker spent, or ``None`` if it cannot be read.

    Read strictly: a value that is not a real civil date is not a day, because
    the whole point of storing one is that it is compared rather than parsed
    into something else. ``None`` is what the surface's repair path fires on.
    """
    if not isinstance(touch, Mapping):
        return None
    day = touch.get(LOCAL_DAY)
    return day if is_civil_day(day) else None


def raised_at(touch: Mapping[str, Any] | None) -> str | None:
    """When the raise happened, or ``None``.

    Reads the record's own ``t``, which is the stamp the append carried, and
    falls back to the stored day — widened to that day's start by
    ``half.loops.timescale.moment``. The fallback is what makes an unreadable
    stamp cost a loop one period of quiet rather than silencing that wanting
    for ever: two independently validated sources have to fail before the bound
    loses its measure, and the caller then treats the loop as never raised
    rather than as raised a moment ago (see ``half.surface.choose.touchable``).
    """
    if not isinstance(touch, Mapping):
        return None
    stamp = _text(touch.get("t"))
    # **Readable, not merely present.** The first version returned ``t``
    # whenever it was a non-empty string, so ``t="yesterday"`` shadowed a
    # perfectly good stored day and the fallback never fired — the recovery
    # existed in the docstring and not in the code.
    if stamp is not None and moment(stamp) is not None:
        return stamp
    return day_of(touch)


def spoken_on(marker: Mapping[str, Any] | None, day: str) -> bool | None:
    """Whether the day marker already covers ``day``. ``None`` if unreadable.

    **Greater-or-equal, not equal**, and that is the repair review found. A
    marker stamped *ahead* of today — a clock that jumped forward and was then
    corrected — is not equal to today, so an equality test read it as
    not-spoken and sent a second message. A day already covered stays covered.

    The comparison is on the **stored** civil day. Recomputing it from the
    record's stamp under whatever zone is current is how a main who moves west
    gets two messages five hours apart.

    ``None`` — neither the stored day nor the stamp readable — is not an
    answer, and the caller repairs rather than guessing: see
    ``MorningSurface._surface``.
    """
    if marker is None:
        return False
    held = day_of(marker)
    if held is None:
        return None
    return held >= day


def origin_of(touch: Mapping[str, Any] | None) -> Origin | None:
    """The origin a touch cited, or ``None`` if it cited nothing readable."""
    if not isinstance(touch, Mapping):
        return None
    kind, ident = touch.get(ORIGIN_KIND), touch.get(ORIGIN_ID)
    if not traceable(kind, ident):
        return None
    return Origin(kind=str(kind), id=str(ident).strip())


# -- refusals ----------------------------------------------------------------

#: The one place a loop id is checked in this module. Lifted in shape from
#: ``half.loops.ledger._loop_id`` rather than imported, because importing it
#: would give this module a name from the package it must not be able to write
#: to — and the check is three lines. ``tests/test_nagging.py`` pins the two to
#: the same answers.
_WHAT: Final[str] = "touch"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _cited(origin: object) -> dict[str, Any]:
    if not isinstance(origin, Origin) or not origin.traceable:
        raise TouchError(
            f"{_WHAT}: a raise cites where it came from — one of "
            f"{', '.join(sorted(TOUCH_ORIGINS))} with a non-empty id. Nothing "
            f"is surfaced that cannot say where it came from"
        )
    return {ORIGIN_KIND: origin.kind, ORIGIN_ID: origin.id.strip()}


def _day(value: object) -> str:
    if not is_civil_day(value):
        raise TouchError(
            f"{_WHAT}: a day marker is the main's own civil day "
            f"(YYYY-MM-DD), got {value!r}; a marker nothing can read is a main "
            f"silenced on every morning after it"
        )
    return str(value)


def _first_loop(loops: object) -> str | None:
    if isinstance(loops, str):
        return _loop_id(loops)
    if not isinstance(loops, (list, tuple)):
        raise TouchError(f"{_WHAT}: loops must be an ordered collection of slugs")
    return _loop_id(loops[0]) if loops else None


def _loop_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise TouchError(
            f"{_WHAT}: a loop id is a non-empty slug with no surrounding "
            f"whitespace, got {value!r}"
        )
    if any(character.isspace() for character in value):
        raise TouchError(
            f"{_WHAT}: a loop id carries no whitespace, got {value!r}"
        )
    return value
