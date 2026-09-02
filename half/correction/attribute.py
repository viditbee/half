"""The three-state attribution, and the record it lives on (CAP-11, story 12).

**Why three.** CAP-11's success criterion is that *"the distinction between Half
was wrong and the main changed is preserved in the record"*. Preserved means
true, and only the main knows which. A default in either direction writes a
falsehood into the one ledger whose whole purpose is to be honest — apologising
for something the main simply changed, or telling a main they changed their mind
when Half was plainly wrong. So the unknown is represented, and a later message
can settle it.

**Where it lives, and what was taken from graphiti.** ``graphiti_core``'s edges
carry four timestamps (``edges.py:271-280``): ``created_at`` (ingested),
``valid_at`` (became true), ``invalid_at`` (stopped being true) and
``expired_at`` (the system invalidated it). The last two are the split this
story needs — *the world changed* against *we were wrong* — and taking them as
two **optional** stamps buys the third state for nothing: a correction carrying
neither says the cause is not yet known.

Two of the four were deliberately **not** taken. ``created_at`` is already every
record's ``t``, and a second field for it is a second place for the log's own
ordering to disagree with itself. ``valid_at`` — when a claim *became* true — is
a fact nobody in this system supplies: Half's beliefs arrive from conversation
and ingestion without a date the claim started holding, and a field that would
be empty on every record is a field that invites being filled with a guess. The
manifest records both rejections.

**Nothing here reads an op.** ``attribution_of`` looks at the two stamps and at
nothing else, and that is the rule rather than an implementation detail: a bare
``retract`` is the *not yet known* state, and a reader that fell back to the op
would answer *the main changed* for it — the exact guess this module exists to
refuse. The append gate keeps the op and the stamp from ever *disagreeing*
(``records.validate_correction_fields``); this keeps the op from ever *standing
in for* a stamp that is not there.

**Read tolerant, write strict**, on the same terms as every other record shape.
A stamp this build cannot parse is refused before it is durable; here, on the
reading side, it is simply not an attribution — one correction loses its cause
rather than a main losing their store.

Pure. No clock, no store, no model, no network. ``attribution_for`` folds a
sequence of record *mappings* handed in by whoever read the log; there is no
door here onto a main's directory and no import that could open one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any, Final

from half.civil import instant
from half.store.ops import Op
from half.store.records import (
    CORRECTIONS,
    EXPIRED_AT,
    INVALID_AT,
    STAMP_FOR_OP,
    TARGET,
)


class Attribution(StrEnum):
    """Why a belief left the fold. Three values, and one of them is honest doubt.

    ``NOT_YET_KNOWN`` is a **state**, not a missing value. The main said the
    belief is wrong and did not say which of the two happened; the record says
    exactly that, Half may ask, and a later message can settle it. Treating it
    as an absence is how it becomes a default.
    """

    #: The system had it wrong. An apology is owed. ``expired_at``.
    HALF_WAS_WRONG = "half_was_wrong"
    #: It was true and stopped being true. No apology. ``invalid_at``.
    MAIN_CHANGED = "main_changed"
    #: The utterance did not settle it, and nothing here will.
    NOT_YET_KNOWN = "not_yet_known"


#: Which stamp carries which cause. The inverse of ``STAMP_FOR_OP``'s reason for
#: existing: that one says which op a stamp may sit on, this one says what the
#: stamp *means*. Both read the same two names from ``half.store.records``, so
#: there is one spelling of each field in the tree.
CAUSE_FOR_STAMP: Final[dict[str, Attribution]] = {
    EXPIRED_AT: Attribution.HALF_WAS_WRONG,
    INVALID_AT: Attribution.MAIN_CHANGED,
}

#: Which op each attribution is appended as.
#:
#: **``NOT_YET_KNOWN`` is a ``retract``, and that is a deliberate reading of the
#: glossary rather than a default.** The three ops differ in *what Half owes the
#: main*: a ``revise`` owes an apology and a ``retract`` owes none. When the
#: cause is unknown Half must not apologise — it has not established that it was
#: wrong — and must not say the main changed either. ``retract`` with no stamp
#: is exactly that: the belief is gone, no apology is owed, and **nothing in the
#: record attributes the removal to anything**, because the attribution lives on
#: the stamps and there is no stamp.
#:
#: This is what the story's Ask-First resolved: the three states needed a home
#: and it is the timestamps, which leaves ``ops.py`` untouched. Reading the op
#: as the attribution would put them back in conflict — see ``attribution_of``.
OP_FOR_ATTRIBUTION: Final[dict[Attribution, Op]] = {
    Attribution.HALF_WAS_WRONG: Op.REVISE,
    Attribution.MAIN_CHANGED: Op.RETRACT,
    Attribution.NOT_YET_KNOWN: Op.RETRACT,
}


def fields_for(attribution: Attribution, *, t: str) -> dict[str, Any]:
    """The stamp fields a correction carrying ``attribution`` appends.

    Empty for ``NOT_YET_KNOWN``, which is the whole point: the honest record of
    an unsettled cause is a record that says nothing about the cause. There is
    no branch here that supplies one.

    ``t`` is the caller's — the inbound stamp the adapter read. Nothing in this
    package touches a clock (AD-30).
    """
    stamp = _stamp_for(attribution)
    return {stamp: t} if stamp is not None else {}


def _stamp_for(attribution: Attribution) -> str | None:
    for name, cause in CAUSE_FOR_STAMP.items():
        if cause is attribution:
            return name
    return None


def op_for(attribution: Attribution) -> Op:
    """The op a correction carrying ``attribution`` is appended as."""
    return OP_FOR_ATTRIBUTION[attribution]


def attribution_of(record: Mapping[str, Any] | Any) -> Attribution:
    """What one record says about the cause. Never raises, never guesses.

    Reads the two stamps and **nothing else** — not the op, not the claim, not
    the target. That is the rule: an op says what Half owes the main, a stamp
    says what happened, and a reader that substituted one for the other would
    answer *the main changed* for every bare ``retract`` in the log, which is
    the guess CAP-11 forbids.

    A stamp this build cannot parse is not an attribution. The append gate
    refuses one before it is durable; a log written by another build costs that
    one correction its cause rather than taking a main's store down.

    Both stamps at once — also refused at the append — reads as *not yet known*
    rather than as either cause. A record that answers both questions has
    answered neither, and picking one here would be inventing a precedence rule
    for a state that should not exist.
    """
    if not isinstance(record, Mapping):
        return Attribution.NOT_YET_KNOWN
    found = [
        cause
        for name, cause in CAUSE_FOR_STAMP.items()
        if instant(record.get(name)) is not None
    ]
    if len(found) != 1:
        return Attribution.NOT_YET_KNOWN
    return found[0]


def attribution_for(
    target: str, records: Iterable[Mapping[str, Any] | Any]
) -> Attribution:
    """What the log says about why ``target`` left. Never raises.

    **Folded over the log rather than materialized**, which is story 5b's
    answer for the trust balance and is right here for the same reason and one
    of its own. The reason it shares: a derived copy of a fact the log already
    holds is a number that can be read stale, and it would replay perfectly, so
    no round-trip test would ever see the drift. The reason of its own: the
    belief this describes has *left* the fold, so there is no entry in
    ``State.beliefs`` for an attribution to hang on, and inventing a table for
    corrections would be new derived state on the one path that must not grow
    any.

    **The last correction naming a cause wins**, in log order, because that is
    what *"attribution can arrive later"* means: the main says *"that's wrong"*
    and Half removes it with the cause unknown, and a follow-up settling it is
    an append like every other. A later correction that names no cause does not
    erase an earlier one that did — it is a second removal of an already-removed
    belief, and saying nothing is not saying *unknown*.
    """
    found = Attribution.NOT_YET_KNOWN
    for record in records:
        if not isinstance(record, Mapping):
            continue
        if record.get(TARGET) != target:
            continue
        if _op_of(record) not in CORRECTIONS:
            continue
        cause = attribution_of(record)
        if cause is not Attribution.NOT_YET_KNOWN:
            found = cause
    return found


def _op_of(record: Mapping[str, Any]) -> Op | None:
    """``record``'s op, or ``None`` for anything outside the vocabulary.

    Reads the field rather than constructing an ``Op`` for input that is not
    one. This is the **only** place in this module that looks at an op, and it
    is deciding *which records are corrections at all* — a different question
    from what one says about the cause, which ``attribution_of`` answers from
    the stamps and would answer identically for every op there is.
    """
    value = record.get("op")
    for op in STAMP_FOR_OP:
        if value == op.value:
            return op
    return None
