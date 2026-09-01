"""What Half raised, and when — the record and its rules (CAP-8, AD-3).

**A touch is not a movement, and that is the whole reason this file exists.**
Story 8 recorded when a loop last *moved* and refused, in writing, to record
when Half last *raised* it: conflating them makes Half's own attention look
like the main's progress, so a farmland loop nudged every morning would read to
every ranking function above as a farmland loop advancing every morning. The
nagging bound needs the second fact; the ranking needs the first; neither may
be computed from the other, and neither path may write the other's field.

That separation is structural rather than agreed. Nothing in this module can
produce a ``state`` or a ``last_movement``: ``fields`` builds a fixed
dictionary of three keys, ``records.validate_touch_fields`` refuses anything
outside ``TOUCH_FIELDS`` before the record is durable, and
``tests/test_nagging.py`` asserts by AST that neither name appears in this file
at all. The mirror rule holds from the other side — ``half.loops.ledger`` has
no function that writes a touch, and says so.

**An append, never an edit** (AD-3). Like ``half.governance.ladder`` and
``half.loops.ledger``, nothing here writes: every function returns the *fields*
of a ``touch`` record and the caller appends them under the main's own mutex
(AD-1). That keeps the rules pure and testable without a store, and keeps the
single writer where AD-1 put it.

**Content-free** (AD-22). A touch carries the loop it raised and the kind and
id of the thing in the preceding pass it came from. It never carries a claim, a
message, a phrase, or a word of what was actually said — what Half said is the
main's, and a log of Half's own attention is not the place for a second copy of
it.

**Every touch cites its origin**, and the citation is required rather than
encouraged: *"nothing is surfaced that cannot say where it came from"* is one
of this story's Always rules, and a rule enforced only where somebody
remembered to enforce it is a convention. So ``fields`` refuses a kind outside
the closed set and refuses an empty id, and the append gate refuses the same
values one layer down where they would become durable.

Pure and clockless: ``t`` is the instant the caller was handed (AD-30).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from half.errors import TouchError
from half.store.ops import TOUCH_ORIGINS
from half.store.records import LOOP, ORIGIN_ID, ORIGIN_KIND

__all__ = [
    "LOOP", "ORIGIN_ID", "ORIGIN_KIND", "Origin", "TOUCH_ORIGINS", "fields",
    "origin_of", "raised_at", "traceable",
]


@dataclass(frozen=True, slots=True)
class Origin:
    """Where a surface came from: a kind out of the closed set, and an id.

    A value. It decides nothing and writes nothing — it is the citation a
    surface carries so that *"this came from last night's pass"* is a fact the
    log holds rather than a claim a docstring makes.

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


def fields(loop_id: object, *, origin: Origin) -> dict[str, Any]:
    """The fields of the append that records Half raising ``loop_id``.

    Returns fields; writes nothing. The caller appends them under an id of the
    *append's* own — never one built from the loop's slug, because
    ``BeliefLog.expunge_bodies`` keeps a tombstoned record's id, and a slug is
    a phrase the main chose about their own life.

    Refused, loudly, when the loop is not a slug or the origin does not cite
    anything. Both refusals are before the record is durable, because the log
    is append-only: a raise that names no loop bounds no loop, so the loop
    would answer *never raised* on every future pass, and a raise that cites
    nothing is a message the log can never trace to the pass that produced it.

    **Three keys, and there is no argument for a fourth.** No ``state``, no
    ``last_movement``, no claim, no text. That is the touch-is-not-a-movement
    rule expressed as a signature rather than as a check somebody has to
    remember, which is ``ladder.quarantine``'s shape and ``ledger.abandon``'s,
    deliberately.
    """
    ident = _loop_id(loop_id)
    if not isinstance(origin, Origin):
        raise TouchError(
            "touch: a raise cites where it came from; pass an Origin naming "
            "the tension, loop transition or ingested item in the preceding "
            "pass"
        )
    if not origin.traceable:
        raise TouchError(
            f"touch: {origin.kind!r} is not one of "
            f"{', '.join(sorted(TOUCH_ORIGINS))} with a non-empty id; nothing "
            f"is surfaced that cannot say where it came from"
        )
    return {
        LOOP: ident,
        ORIGIN_KIND: origin.kind,
        ORIGIN_ID: origin.id.strip(),
    }


def raised_at(touch: Mapping[str, Any] | None) -> str | None:
    """When the touch happened, or ``None``.

    Reads the record's own ``t``, which is the stamp the append carried. A
    touch this build cannot read comes back ``None``, and every caller treats
    ``None`` as *do not act* — for the bound that means *do not raise*, which
    is the safe direction: the failure of guessing here is nagging, and the
    failure of refusing is one quiet day.
    """
    if not isinstance(touch, Mapping):
        return None
    stamp = touch.get("t")
    return stamp if isinstance(stamp, str) and stamp.strip() else None


def origin_of(touch: Mapping[str, Any] | None) -> Origin | None:
    """The origin a touch cited, or ``None`` if it cited nothing readable."""
    if not isinstance(touch, Mapping):
        return None
    kind, ident = touch.get(ORIGIN_KIND), touch.get(ORIGIN_ID)
    if not traceable(kind, ident):
        return None
    return Origin(kind=str(kind), id=str(ident).strip())


#: The one place a loop id is checked in this module. Lifted in shape from
#: ``half.loops.ledger._loop_id`` rather than imported, because importing it
#: would give this module a name from the package it must not be able to write
#: to — and the check is three lines. ``tests/test_nagging.py`` pins the two to
#: the same answers.
_WHAT: Final[str] = "touch"


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
