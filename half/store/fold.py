"""The pure fold: log -> current state (AD-30).

This module must never call a model, touch the network, or read a clock. A
fold is a pure function of the log, and that is what makes the replay
invariant (AD-4) true rather than aspirational: without purity, a main who
changed model tier would replay to different state.

``tests/test_purity.py`` enforces the rule statically, because "just re-derive
it" is the natural way to write a fold and a behavioural test would not catch it.

**The refutation firewall (CAP-6).** Loops are unreachable from the correction
path. ``retract``, ``revise`` and the tombstone branch cannot name
``state.loops`` at all, and ``expunge`` reaches it only through a second,
explicit ``loop`` field — so a belief's removal can never take a wanting with
it, and violating that takes a deliberate new op rather than a plausible-looking
line. A wanting is not a fact; evidence of non-action changes a loop's *state*
and never its truth, and there is no state in the vocabulary that means false.
``tests/test_loops.py`` asserts the structure as well as the behaviour, because
this is exactly the rule everybody agrees with and then breaks by accident.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Final

from half.errors import CorruptLogError
from half.store.ops import AFTERCARE_STATES, CRISIS_STATES, Op
from half.store.records import (
    LAST_MOVEMENT,
    LOOP,
    NEXT_PASS_AT,
    STATE,
    TIMESCALE,
    Record,
    carried_forward,
)

#: The fields a ``loop_transition`` carries forward into the loop table. Read
#: from ``half.store.records`` rather than spelled here, so that the append
#: gate, the fold and ``half.loops.ledger`` cannot drift to three spellings of
#: ``last_movement`` — which would be a loop that is permanently and invisibly
#: not silent-detectable.
_TRANSITION_FIELDS: Final[tuple[str, ...]] = (STATE, TIMESCALE, LAST_MOVEMENT)


@dataclass(slots=True)
class State:
    """The materialized current view. Derived and disposable."""

    beliefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    tensions: dict[str, dict[str, Any]] = field(default_factory=dict)
    loops: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Beliefs and tensions the main has genuinely erased.
    expunged: set[str] = field(default_factory=set)
    #: Loops the main has genuinely erased — **a separate namespace, and that
    #: is a correctness rule rather than tidiness (CAP-6).**
    #:
    #: One shared set was a demotion wearing another name. Belief ids and loop
    #: slugs live in one id space; expunging a belief whose id collided with a
    #: loop's slug left the loop *standing* — which every firewall test
    #: asserted — while the transition case's ``in state.expunged`` guard
    #: silently dropped every later transition on it. The wanting could then
    #: never advance, never be achieved, never move again, and nothing raised.
    #: Standing still is not standing.
    #:
    #: It poisoned the other direction too: erasing a loop suppressed a belief
    #: that happened to share the slug, from then on.
    expunged_loops: set[str] = field(default_factory=set)
    #: The main's global license ceiling, as the log last set it (AD-28), or
    #: ``None`` when none has ever been set. A raw string: what rung it names is
    #: the ladder's question, and the fold answers no governance questions.
    #: Here rather than in memory so that a cap survives eviction and restart —
    #: losing the store is the only thing that may lose a ceiling.
    ceiling: str | None = None
    #: The last crisis record, or ``None`` if the mode has never opened
    #: (CAP-12). Raw fields: whether the mode is *open* is the crisis module's
    #: question, and the fold answers no clinical ones. Here rather than in
    #: memory because a mode that ends at the next eviction is not a mode — the
    #: main's next message would be answered by the ordinary pipeline, which is
    #: an exit nobody decided.
    crisis: dict[str, Any] | None = None
    #: The last aftercare record, or ``None`` if Half has never put the
    #: question (CAP-12, story 6c). Raw fields, for the reason ``crisis``
    #: holds raw fields: whether a step is *due* is aftercare's question and
    #: the fold answers no clinical ones. The last record is enough because
    #: the states supersede one another — asked, then answered — and because a
    #: record older than the most recent crisis entry belongs to a period that
    #: ended, which ``half.crisis.aftercare`` decides by comparing the two
    #: stamps rather than by the fold throwing anything away.
    aftercare: dict[str, Any] | None = None
    #: The last ``schedule`` record, or ``None`` if this main has never been
    #: scheduled (AD-9, story 9a). Raw fields, for the reason ``crisis`` and
    #: ``aftercare`` hold raw fields: *whether* a main is due is the
    #: scheduler's question, computed from an injected instant, and the fold
    #: answers no scheduling ones — it reads no clock and cannot.
    #:
    #: The last record is enough because each supersedes the one before: a
    #: schedule record says when this main is next due, and the next one says
    #: it again, later.
    #:
    #: Here rather than in memory because a due time that ends at the next
    #: restart is not a schedule. The population would be rescheduled together
    #: on every boot — a herd, which is the one thing AD-9 exists to prevent —
    #: or a pass that already ran would run again.
    schedule: dict[str, Any] | None = None

    def canonical_json(self) -> str:
        """Deterministic serialization — the unit of the byte-identical
        comparison in the replay test."""
        return json.dumps(
            {
                "beliefs": self.beliefs,
                "tensions": self.tensions,
                "loops": self.loops,
                "expunged": sorted(self.expunged),
                "expunged_loops": sorted(self.expunged_loops),
                "ceiling": self.ceiling,
                "crisis": self.crisis,
                "aftercare": self.aftercare,
                "schedule": self.schedule,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def fold(records: Iterable[Record]) -> State:
    """Fold records into current state. Pure: same input, same output, always."""
    state = State()

    for record in records:
        if record.data.get("tombstone") is True:
            if record.op is not Op.LOOP_TRANSITION:
                # A transition's id is the *append's*, not the loop's, so
                # remembering it here says nothing about any object and
                # pollutes the belief namespace with it — which then suppresses
                # a later belief that happens to share the id. The loop's own
                # erasure is recorded in ``expunged_loops`` by the expunge op.
                state.expunged.add(record.id)
            state.beliefs.pop(record.id, None)
            state.tensions.pop(record.id, None)
            # **The refutation firewall, part one (CAP-6).** No loop is removed
            # here. A tombstone erases one *record's body*, and it is keyed on
            # the record's own id — which for a loop transition is the append's
            # id (``l_1``), never the loop's slug. So this line could only ever
            # fire on a collision, and when it fired it would delete a wanting
            # because a belief happened to share its identifier. A loop leaves
            # the fold through an expunge that names it as a loop, below, and
            # through nothing else.
            continue

        match record.op:
            case Op.ASSERT:
                if record.id not in state.expunged:
                    incoming = copy.deepcopy(dict(record.data))
                    # A later record replaces the belief, but it may not drop
                    # what the log pinned. Quarantine is permanent, and the
                    # most ordinary append there is — re-stating a belief
                    # without repeating the flag — would otherwise unpin it,
                    # with replay faithfully reproducing it unpinned. Enforced
                    # here rather than asked of every writer, because "every
                    # writer remembered" is not a property anything can check.
                    incoming.update(carried_forward(state.beliefs.get(record.id)))
                    state.beliefs[record.id] = incoming

            case Op.RETRACT | Op.REVISE:
                # Both remove the belief from the current view. They differ in
                # what Half owes the main, not in what the fold does: RETRACT
                # means "you changed" (no apology), REVISE means "Half was
                # wrong" (apology, and show what was removed). The distinction
                # is preserved in the log for whoever composes that message.
                #
                # **The refutation firewall, part two (CAP-6).** These two lines
                # are the whole correction path, and neither of them can reach
                # ``state.loops`` — there is no name for it in this branch. A
                # wanting is not a fact and nothing may refute one: a retracted,
                # revised or expunged *belief* leaves its loop standing, even
                # when it was the loop's only support. That has to be
                # structural rather than agreed, because the natural
                # implementation of "no evidence supports this any more" is to
                # lower something, and the only honest thing to lower is a
                # belief. ``tests/test_loops.py`` asserts by AST that these
                # cases never mention the loop table.
                target = _require_target(record)
                state.beliefs.pop(target, None)

            case Op.EXPUNGE:
                # **The firewall's one door (CAP-6).** A loop is removed only by
                # an expunge that names it in ``loop`` — ``target`` alone
                # reaches beliefs and tensions, and it takes this second,
                # explicit field to reach a wanting. So an expunge aimed at a
                # belief cannot take a loop with it whatever its identifier
                # happens to be, while the main's own *"erase this loop"* still
                # works and is still recorded (``Store.expunge``).
                loop_target = record.data.get(LOOP)
                if isinstance(loop_target, str) and loop_target:
                    state.expunged_loops.add(loop_target)
                    state.loops.pop(loop_target, None)
                # ``target`` is optional on a record that names a loop, and
                # that is the second half of keeping the namespaces apart. A
                # loop-only erasure writing its slug into ``expunged`` would
                # suppress every later *belief* that happened to share the
                # name — the same collision the split set exists to prevent,
                # arriving from the other side.
                if loop_target and record.data.get("target") is None:
                    continue
                target = _require_target(record)
                state.expunged.add(target)
                state.beliefs.pop(target, None)
                state.tensions.pop(target, None)

            case Op.TENSION:
                if record.id not in state.expunged:
                    state.tensions[record.id] = copy.deepcopy(dict(record.data))

            case Op.LOOP_TRANSITION:
                # The only op that opens or moves a loop, and the only place in
                # this module that writes to ``state.loops`` other than the
                # loop-named expunge above. That is the firewall stated as a
                # property of the code rather than of anyone's intentions.
                #
                # **Read tolerant, write strict.** Nothing here checks the state
                # against the vocabulary. ``records.validate_loop_fields``
                # refuses an unknown one before the record is durable, which is
                # where the check belongs; refusing it *here* as well would mean
                # a log written by a later build — through the Ask-First path
                # that adds a state — took a main's whole fold down rather than
                # costing one loop its ranking weight (AD-24).
                loop_id = record.data.get(LOOP)
                if not isinstance(loop_id, str) or not loop_id:
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} has no {LOOP!r}",
                        path="<fold>", line=0,
                    )
                # ``expunged_loops``, never ``expunged``. A belief's erasure
                # must not be able to freeze a wanting it happens to share an
                # identifier with — see ``State.expunged_loops``.
                if loop_id in state.expunged_loops:
                    continue
                entry = state.loops.setdefault(loop_id, {LOOP: loop_id})
                for key in _TRANSITION_FIELDS:
                    if key in record.data:
                        entry[key] = record.data[key]

            case Op.CEILING:
                rung = record.data.get("rung")
                if not isinstance(rung, str) or not rung:
                    # Fatal, on the same terms as a correction that names no
                    # target: a ceiling record the fold cannot read would
                    # otherwise no-op, leaving a main uncapped while the log
                    # says they were capped.
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} has no 'rung'",
                        path="<fold>", line=0,
                    )
                state.ceiling = rung

            case Op.CRISIS:
                mode = record.data.get("state")
                if mode not in CRISIS_STATES:
                    # Fatal for the reason an unreadable ceiling is: a crisis
                    # record the fold cannot read would no-op, leaving a main
                    # out of the mode while the log says they are in it — and
                    # the next message answered by the ordinary pipeline.
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} has state {mode!r};"
                        f" expected one of {sorted(CRISIS_STATES)}",
                        path="<fold>", line=0,
                    )
                state.crisis = copy.deepcopy(dict(record.data))

            case Op.AFTERCARE:
                answer = record.data.get("state")
                if answer not in AFTERCARE_STATES:
                    # Fatal on the same terms as the two above. An aftercare
                    # record the fold cannot read would no-op, and the state it
                    # would silently drop is the main's own answer: a decline
                    # folding to nothing leaves the next turn free to read a
                    # later yes as consent to a question the main refused.
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} has state {answer!r};"
                        f" expected one of {sorted(AFTERCARE_STATES)}",
                        path="<fold>", line=0,
                    )
                state.aftercare = copy.deepcopy(dict(record.data))

            case Op.SCHEDULE:
                # Fatal on *shape*, tolerant of *value*, and the split is
                # deliberate. A schedule record with no ``next_pass_at`` at all
                # is a record this build cannot recognise, and folding it to
                # nothing is the silent omission AD-29 exists to prevent — the
                # main would read as never scheduled and be rescheduled on
                # every tick for ever.
                #
                # A ``next_pass_at`` that is a string this build cannot *parse*
                # is a different failure and gets the opposite answer, because
                # the two costs are not symmetric: refusing to fold takes a
                # main's entire store down — every belief, every loop, their
                # whole reply path — over a due time, while carrying the value
                # through costs them one pass. ``half.civil.instant`` returns
                # ``None`` for it, ``half.schedule.tick`` treats that as
                # never-scheduled, and the main is scheduled forward and sent
                # nothing. Sending nothing is a first-class outcome (AD-27);
                # bricking a store is not.
                at = record.data.get(NEXT_PASS_AT)
                if not isinstance(at, str) or not at:
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} has no {NEXT_PASS_AT!r}",
                        path="<fold>", line=0,
                    )
                state.schedule = copy.deepcopy(dict(record.data))

            case _:  # pragma: no cover - guarded by the closed vocabulary
                # A new Op added to the enum must not fold to nothing. Silently
                # dropping a record is the failure AD-29 exists to prevent,
                # reappearing one level down.
                raise CorruptLogError(
                    f"fold has no case for op {record.op!r}", path="<fold>", line=0
                )

    return state


def _require_target(record: Record) -> str:
    """A correction must name what it corrects.

    Defaulting to the op record's own id let a malformed RETRACT silently
    no-op, leaving the belief in place — the same silent-omission failure
    unknown ops are made fatal to avoid.
    """
    target = record.data.get("target")
    if not isinstance(target, str) or not target:
        raise CorruptLogError(
            f"{record.op} record {record.id!r} has no 'target'", path="<fold>", line=0
        )
    return target
