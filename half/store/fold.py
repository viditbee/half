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

**The resolution rule (CAP-7) — and it is the firewall's deliberate inverse.**
A correction *does* reach the tension table, and must. A loop is a *wanting*,
which evidence cannot refute; a tension is a claim **about two entries**, so
retracting, revising or expunging one of them genuinely ends the disagreement.
The two rules point in opposite directions because they are about opposite
objects, and both are written down because each one, applied to the other's
object, is a plausible-looking line: the firewall applied to tensions leaves
them standing over entries that no longer exist, and this rule applied to loops
lets a retracted belief demote a wanting.

Resolution is a **state change, never a deletion**. The tension stays in the
fold, keeps its pair and its license, and reads `resolved` — history is kept,
because what a person once held in tension with themselves is part of the
record. And nothing here says *which* of the two entries went, or that either
was wrong: a `retract` and a `revise` resolve a tension identically, and the
difference between *"you changed"* and *"Half was wrong about you"* stays on the
correction record where the apology is composed from it.

**`resolved` is terminal by every route, and two of them arrive here.** The rule
was prose in ``half.tensions.states`` and a guard on one path only, which is the
shape three earlier stories shipped. Review reproduced the hole: a correction
resolved a tension, a later ``tension`` append carrying ``state="persistent"``
merged straight over it, and the tension came back live from a rebuild. So the
merge below re-pins the state, and a tension whose side is *already gone when
the record is folded* — minted over an entry a correction removed earlier in the
log — is resolved on the spot rather than left live until a correction that has
already happened happens again.

**Merged, not replaced — and the trade is that a mint is not editable.** A
transition carries a state and nothing else, so replacing the held record would
drop the pair and the license every time the pass moved a tension. Merging keeps
them, at the price of a wrong ``between`` being permanent: no later append can
take a field off a tension. The corrective path is the one the main already has
— ``Store.expunge`` names the tension itself, which removes it from the fold
entirely, and story 9d mints a new one. That is deliberate rather than missing:
an append-only log corrects by erasing and re-stating, and a mint that could be
edited in place is a mint whose two sides could be swapped after the fact.
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
    LOCAL_DAY,
    LOOP,
    NEXT_PASS_AT,
    QUESTION,
    STATE,
    TIMESCALE,
    Record,
    carried_forward,
)
from half.tensions.states import TensionState
from half.tensions.widening import pair_of

#: The fields a ``loop_transition`` carries forward into the loop table. Read
#: from ``half.store.records`` rather than spelled here, so that the append
#: gate, the fold and ``half.loops.ledger`` cannot drift to three spellings of
#: ``last_movement`` — which would be a loop that is permanently and invisibly
#: not silent-detectable.
_TRANSITION_FIELDS: Final[tuple[str, ...]] = (STATE, TIMESCALE, LAST_MOVEMENT)

#: The state a tension takes when one of its two entries leaves the ledger
#: (CAP-7). Read from ``half.tensions.states`` rather than spelled here, so the
#: vocabulary, the append gate and this branch cannot drift to two spellings of
#: the same word — which would be a tension the pass keeps evaluating over an
#: entry that no longer exists.
_RESOLVED: Final[str] = TensionState.RESOLVED.value

#: Ops whose record id is the **append's**, not the id of the thing the record
#: is about. A tombstone on one of these must not enter ``State.expunged``:
#: that set is the belief namespace, so putting an append id in it suppresses
#: whatever belief happens to share the identifier, for ever.
#:
#: Named rather than spelled as a comparison against one op, because that is
#: what it was — ``record.op is not Op.LOOP_TRANSITION`` — and story 10 added
#: the second member. The next op keyed on its own append is caught by this
#: same rule rather than by somebody remembering the branch.
#: ``Op.ASKED`` joins them in story 5b for exactly the same reason: a spend's
#: record id is built from the stamp (``qa_<t>``) and names no object, so
#: remembering it in ``State.expunged`` would suppress whatever belief happened
#: to share the identifier, for ever.
_APPEND_KEYED: Final[frozenset[Op]] = frozenset(
    {Op.LOOP_TRANSITION, Op.TOUCH, Op.ASKED}
)


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
    #: What Half has raised, and when — the last ``touch`` per loop (CAP-8,
    #: CAP-10, story 10). Keyed by the **loop's** slug rather than by the
    #: record's id, because the question every reader asks is *"when did Half
    #: last raise this wanting?"* and the last raise is the only one that
    #: answers it.
    #:
    #: **A separate table from ``loops``, and that is the whole point.** Story
    #: 8 recorded when a loop last *moved* and refused to record when Half last
    #: *raised* it, because a nudge written into the loop entry is Half's own
    #: attention wearing the main's progress: a farmland loop raised every
    #: morning would read, to every ranking function above this, as a farmland
    #: loop advancing every morning. The bound needs this one; the ranking
    #: needs the other; neither may be computed from the other.
    #:
    #: Here rather than in memory because a raise forgotten at the next
    #: eviction is a raise that never happened — and the rule it feeds says
    #: *never faster than the loop's own timescale*, which for a years-loop
    #: means the memory would have to survive a year.
    touches: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: The last **day marker**: the newest touch carrying a ``local_day``, or
    #: ``None`` if Half has never spent one of this main's days (CAP-8).
    #:
    #: **A day marker, not "the last raise of any loop"**, and the difference
    #: is a rule rather than a nicety. CAP-10's interrupt is a second thing that
    #: will raise a loop, and on the day it lands it would silently consume the
    #: morning budget if every raise counted — with no change anywhere near the
    #: surface to say so. A raise carries a ``loop``; a spent day carries a
    #: ``local_day``; a record may carry either, both, or — for the repair path
    #: — only the day.
    #:
    #: The day is the **stored** one. Recomputing it from the record's stamp
    #: under whatever zone is current is how a main who moves west gets two
    #: messages five hours apart, which review reproduced.
    #:
    #: In log order rather than by comparing days, so that the newest marker is
    #: the one the rule reads. (Within a shard that is append order; across a
    #: month boundary it is the shard order, which is ``t``-ordered, because
    #: ``BeliefLog`` shards by month.)
    spoke: dict[str, Any] | None = None
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
                "touches": self.touches,
                "spoke": self.spoke,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def fold(records: Iterable[Record]) -> State:
    """Fold records into current state. Pure: same input, same output, always."""
    state = State()
    # Entries a correction, an expunge or a tombstone has already taken out of
    # the ledger, in log order. Local rather than a field of ``State``: it is
    # not part of the derived view — nothing downstream asks it — and it is the
    # answer to a question only this pass can ask, *"was this side already gone
    # when that tension record was folded?"*.
    #
    # Deliberately **not** *"absent from ``state.beliefs``"*, which would also
    # catch an entry that never existed. A tension over an id the log has never
    # seen is not a resolved disagreement, it is one whose evidence cannot be
    # read — which ``half.tensions.widening`` already reports as such, rather
    # than declaring a disagreement over.
    gone: set[str] = set()

    for record in records:
        if record.data.get("tombstone") is True:
            gone.add(record.id)
            if record.op not in _APPEND_KEYED:
                # A transition's id — and a touch's — is the *append's*, not
                # the loop's, so remembering it here says nothing about any
                # object and pollutes the belief namespace with it, which then
                # suppresses a later belief that happens to share the id. The
                # loop's own erasure is recorded in ``expunged_loops`` by the
                # expunge op.
                #
                # A touch is tombstoned by exactly the same route a transition
                # is: ``BeliefLog.expunge_bodies`` matches on the ``loop``
                # field, so erasing a loop erases every raise Half made on it
                # along with every movement — which it must, because a loop
                # slug is a phrase about a person's life and surviving an
                # erasure is not an erasure.
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
                gone.add(target)
                # **The resolution rule (CAP-7), and it is the firewall's
                # deliberate inverse.** A tension is a claim about *two
                # entries*, so removing one of them genuinely ends the
                # disagreement — which is precisely what a loop's removal from
                # this branch must never do, because a wanting is not a claim
                # about anything a correction can reach. The tension is not
                # deleted: it keeps its pair, its license and its place in the
                # fold and reads `resolved`, because a tension the main lived
                # inside is part of the record even after it closes. Nothing
                # here records which entry went, or that either was wrong.
                _resolve_tensions(state, target)

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
                    # **And every raise Half made on it** (CAP-8, story 10).
                    # A raise is not a wanting — the firewall still holds and
                    # nothing here demotes anything — but a raise *names* one,
                    # so a loop slug would otherwise survive in the derived view
                    # and be written straight back into the ``touches`` table by
                    # ``db.rebuild``. A slug is a phrase the main chose about
                    # their own life, and surviving an erasure is not an
                    # erasure. ``Store.expunge`` also tombstones the bodies,
                    # which is why this branch had no test until review wrote
                    # one against the bare op.
                    state.touches.pop(loop_target, None)
                    if (
                        isinstance(state.spoke, dict)
                        and state.spoke.get(LOOP) == loop_target
                    ):
                        state.spoke = None
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
                gone.add(target)
                # An expunge that names *the tension itself* removes it: an
                # erasure is an erasure, and this is the main's own deliberate
                # *"erase this"* rather than a correction to one of its sides.
                state.tensions.pop(target, None)
                # An expunge that names one of its **sides** resolves it
                # instead, on the same terms as a retract or a revise (CAP-7).
                # The order matters: a name that is somehow both is erased *and*
                # cannot then be resolved, because it is no longer there.
                _resolve_tensions(state, target)

            case Op.TENSION:
                if record.id not in state.expunged:
                    # **Merged, not replaced**, and that is what makes a
                    # transition an append rather than an edit (AD-3). A
                    # transition carries a state and nothing else, so a
                    # wholesale replace would silently drop the pair the mint
                    # recorded and the license the ladder admitted — a tension
                    # that lost its two sides the first night the pass moved
                    # it, with replay faithfully reproducing the loss. The loop
                    # table has merged since story 8 for the same reason.
                    #
                    # **Read tolerant, write strict.** Nothing here checks the
                    # state against the vocabulary; ``validate_tension_fields``
                    # refuses an unknown one before the record is durable, which
                    # is where the check belongs. Refusing it here as well would
                    # mean a log written by a later build — through the
                    # Ask-First path that adds a state — took a main's whole
                    # fold down rather than costing one tension its evaluation.
                    held = state.tensions.setdefault(record.id, {})
                    # **`resolved` is terminal, and this is the route review
                    # reproduced.** The merge below is a plain ``update``, so a
                    # later record carrying any state at all wrote straight
                    # over the fold's own answer to a correction: retract a
                    # side, append ``state="persistent"``, and the tension came
                    # back live — through a rebuild as faithfully as through a
                    # fold, because replay reproduces the append. The expunge
                    # path had a guard and a case for exactly this shape; the
                    # resolution path had neither, while
                    # ``half.tensions.states`` said in prose that *"there is no
                    # path from `resolved` back to any other state"*.
                    #
                    # Read before the merge and re-pinned after it, so the
                    # record's other fields still travel through: what is
                    # terminal is the *state*, not the record.
                    was_resolved = held.get(STATE) == _RESOLVED
                    held.update(copy.deepcopy(dict(record.data)))
                    if was_resolved:
                        held[STATE] = _RESOLVED
                    # **A tension is resolved whenever a side is already gone,
                    # not only while folding the correction.** Minting over an
                    # entry a correction removed earlier in the log used to
                    # produce a live `fresh` tension nothing would ever revisit
                    # — ``_resolve_tensions`` fires on the correction, and the
                    # correction had already happened — so the nightly pass
                    # computed drift across an entry that does not exist.
                    elif any(side in gone for side in pair_of(held)):
                        held[STATE] = _RESOLVED

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

            case Op.TOUCH:
                # Fatal only when the record does **neither** of the two jobs a
                # touch has — it names no loop and marks no day — because that
                # is a record this build cannot attribute to anything, and
                # folding it to nothing is the silent omission AD-29 exists to
                # prevent: the loop would answer *never raised* on every pass
                # for ever, or the day would answer *never spent*.
                #
                # Tolerant of everything else, deliberately. The origin, the
                # day's shape and the ``sent`` flag are refused before the
                # record is durable (``records.validate_touch_fields``), which
                # is where a closed vocabulary belongs; refusing an unknown one
                # *here* as well would mean a log written by a later build took
                # a main's whole store down over a word.
                loop_id = record.data.get(LOOP)
                day = record.data.get(LOCAL_DAY)
                raises = isinstance(loop_id, str) and bool(loop_id)
                marks = isinstance(day, str) and bool(day)
                if not raises and not marks:
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} names neither "
                        f"{LOOP!r} nor {LOCAL_DAY!r}",
                        path="<fold>", line=0,
                    )
                # ``expunged_loops``, never ``expunged`` — the same split the
                # transition case makes, for the same reason. A raise on a loop
                # the main erased is erased with it: the tombstone pass has
                # already removed the ones written before the erasure, and this
                # is what stops one written after it coming back. The day
                # marker on such a record goes with it, which is the one place
                # an erasure can hand a main a second message in a day — a
                # bounded cost, because it takes a deliberate erasure between
                # two triggers inside one day and the scheduler gives one due
                # time per day (AD-9).
                if raises and loop_id in state.expunged_loops:
                    continue
                touch = copy.deepcopy(dict(record.data))
                if raises:
                    state.touches[loop_id] = touch
                if marks:
                    # The same object in both places when a record does both
                    # jobs: they are one record read two ways, and a copy in
                    # each would be two facts that could drift.
                    state.spoke = touch

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

            case Op.ASKED:
                # **The one op this fold deliberately materializes nothing
                # from, and the omission is the story's central rule.**
                #
                # A spend is half of the trust balance — delivered favours
                # minus questions asked — and the obvious implementation is a
                # pair of integers on ``State`` that this case decrements. That
                # is the counter story 4 refused for salience and story 9c
                # refused for decay, one layer lower down: a number kept in the
                # derived view is a number that can be read *from* the derived
                # view, and the derived view is what a crash between an append
                # and a rebuild leaves behind (``Store.append`` writes the line
                # first). A balance read from a stale view is a favour spent
                # twice, and it would replay correctly every time, so no
                # round-trip test would ever see it.
                #
                # So the balance is computed by folding the **log** — the only
                # authority (AD-3) — in ``half.trust.balance``, which counts
                # ``touch`` records that delivered against ``asked`` records
                # that spent. There is nowhere in ``State`` to keep a stale
                # copy, because there is no copy.
                #
                # This is **not** the silent skip AD-29 exists to prevent. The
                # record is validated here rather than passed over: one naming
                # no question is fatal, on the same terms as a ceiling with no
                # rung, because a spend the balance cannot count is a question
                # that was asked and never paid for. What is absent is a
                # *derived* copy of a fact the log already holds, and every
                # reader of that fact reads the log.
                #
                # Read tolerant on everything else, for the reason every case
                # above is: ``records.validate_asked_fields`` refuses the shape
                # before it is durable, and refusing it again here would mean a
                # log written by a later build took a main's whole store down
                # over a field.
                question = record.data.get(QUESTION)
                if not isinstance(question, str) or not question:
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} has no {QUESTION!r}",
                        path="<fold>", line=0,
                    )

            case _:  # pragma: no cover - guarded by the closed vocabulary
                # A new Op added to the enum must not fold to nothing. Silently
                # dropping a record is the failure AD-29 exists to prevent,
                # reappearing one level down.
                raise CorruptLogError(
                    f"fold has no case for op {record.op!r}", path="<fold>", line=0
                )

    return state


def _resolve_tensions(state: State, entry_id: str) -> None:
    """Resolve every tension ``entry_id`` is one of the two sides of (CAP-7).

    **A correction resolves a tension; it never deletes one.** This is story
    8's loop rule turned exactly around, and the inversion is deliberate: a
    loop is a *wanting*, which evidence cannot refute, so the correction path
    is structurally unable to reach it; a tension is a claim *about two
    entries*, so retracting, revising or expunging one of them genuinely ends
    the disagreement. Leaving the tension standing over an entry that no longer
    exists would have the nightly pass keep computing drift between a live
    claim and a deleted one, and the morning surface reach for it.

    What changes is the **state and nothing else**. The tension keeps its id,
    its pair, its license and its place in the fold, so:

    * history is kept — a resolved tension is not an erased one, and *"these
      two things about you were once in tension"* stays true and readable;
    * nothing records which side went, or that either was wrong. `retract`
      (*"you changed"*) and `revise` (*"Half was wrong about you"*) land here
      identically, because which of two claims about a person was mistaken is
      not a question a tension answers — and the log keeps the two verbs apart
      on the correction record, which is where the apology is composed from.

    Pure, like everything else in this module: it reads the tension table it
    was handed and writes one string.

    The pair is read through ``half.tensions.widening.pair_of``, which is also
    what ``half.tensions.ledger.read`` uses. There were two readings of
    ``between`` — one matching the raw list here, one matching a list already
    filtered to non-empty strings in the ledger — and review found they
    disagreed on hostile input while the ledger's copy had no caller at all.
    """
    for tension in state.tensions.values():
        if entry_id not in pair_of(tension):
            continue
        # Idempotent. A second correction to the other side, or a replay over
        # the same log, must not produce a different fold.
        tension[STATE] = _RESOLVED


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
