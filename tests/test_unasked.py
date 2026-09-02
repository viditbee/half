"""CAP-4 story 5b: the unasked queue — two gates, in order, and what is held.

``tests/test_trust.py`` carries the currency and the stakes rule; this file
carries the queue that spends one and weighs with the other.

**Every gate is asserted alone, and every pair of them in both orders.** The
last two stories here each had their central rule broken in an ordering nobody
had written a case for — a marker stamped ahead of now, a tension resolved and
then merged back live — and both had suites that exercised only the sequence
the implementation already handled. So the sweep below runs the five refusals
against each other pairwise, both ways round, and asserts the *outcome* is
independent of the order while only the *reason* is not.

**The one ordering that is not symmetric is the story's own rule.** Stakes come
before the favour: a question below the bar is not askable at *any* balance,
and a question that is worth asking with nothing given is *held*. Reversed, a
large balance buys a worthless question. That asymmetry is asserted here and
made structural in ``tests/test_trust.py``.

**Nothing here reads a clock.** None of the gates is a function of time at all,
which is itself asserted: a verdict changes when the log or the conversation
changes and at no other moment.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import inspect
from itertools import combinations
from pathlib import Path
from typing import Final

import pytest

from half.actor.registry import ActorRegistry
from half.governance import ladder
from half.governance.ladder import RUNGS, Ceiling, License
from half.loops import ledger as loops
from half.loops.states import LoopState
from half.loops.timescale import Timescale
from half.retrieval.strands import Strands, known_strands
from half.store.fold import State
from half.store.records import make
from half.store.ops import TOUCH_TENSION, Op
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.touch import Origin
from half.trust.balance import Balance, balance
from half.trust.stakes import (
    BELOW_THE_BAR,
    FINISHED,
    NO_PERIOD,
    NO_SUBJECT,
    NO_WANTING,
    Stakes,
)
from half.questions.engine import QuestionLedger
from half.trust.unasked import (
    ASKS_AT,
    ASK_CRISIS,
    ASK_OUTCOMES,
    ASK_RECORDED,
    ASK_REFUSED,
    ON_TOPIC_FLOOR,
    TrustLedger,
    HELD,
    NOT_PERMITTED,
    NO_FAVOUR,
    REASONS,
    TOPIC_UNRAISED,
    VISIBLE,
    Ask,
    TrustView,
    Unasked,
    verdicts,
    UnaskedQueue,
    Verdict,
    asks_at,
    considered,
    narrowed_for_trust,
    on_topic,
    queue,
    view_fields,
)

from tests.conftest import (
    CLOSED,
    UNREACHABLE,
    door_of,
    ledger_calls,
    reaches,
    resolved_imports,
)

pytestmark = [pytest.mark.cap4]

ROOT = Path(__file__).resolve().parents[1]

ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")

#: A wanting whose period outlasts one interruption, so stakes pass.
FARMLAND = "buy-farmland"
#: A wanting that moves in days, so stakes do not.
ROUTINE = "swim-daily"


# ── helpers ──────────────────────────────────────────────────────────────────


def a_view(
    *,
    rung=License.ASK,
    loop=FARMLAND,
    timescale=Timescale.YEARS,
    state=LoopState.STALLED,
    ceiling=None,
    earned=1,
    spent=0,
    quarantined=False,
    beliefs=None,
):
    """A ``TrustView`` with one belief on one wanting, and a balance."""
    belief = {
        "id": "b_1",
        "claim": "wants to buy farmland",
        "license": str(rung),
        "topics": ["farmland"],
    }
    if loop is not None:
        belief["loop"] = loop
    if rung is License.ASSERT:
        belief["support"] = ["s_1"]
        belief["known_to_main"] = True
    if quarantined:
        belief["quarantined"] = True
    table = {"b_1": belief} if beliefs is None else beliefs
    return TrustView(
        beliefs=table,
        loops={
            loop: {
                "loop": loop,
                "state": None if state is None else str(state),
                "timescale": None if timescale is None else str(timescale),
                "last_movement": "2026-01-04",
            }
        } if loop is not None else {},
        ceiling=Ceiling(License.ASSERT if ceiling is None else ceiling),
        balance=Balance(earned=earned, spent=spent),
    )


def a_question(ident="q_1", about="b_1"):
    return Unasked(id=ident, about=about)


def talking_about(*words, view=None):
    """Live strands after a message using ``words``.

    Built through the real ``Strands`` rather than by writing weights in by
    hand, so the topic gate is asserted against the same matcher CAP-1 uses.
    """
    live = Strands()
    known = known_strands(
        (view.beliefs.values() if view is not None else ()),
        view.loops if view is not None else {},
    )
    live.observe(" ".join(words), known)
    return live


ON_TOPIC = "the farmland thing again"
OFF_TOPIC = "how was the concert"


def a_favour(store, *, t, day):
    store.record(
        Op.TOUCH, f"tc_{t}", t,
        **touch_module.spoke(day=day, origin=ORIGIN, loops=()),
    )


def seed_a_main(root, *, main_id="vidit", favours=1, beliefs=("b_1",)):
    """One main with a farmland loop, `ask`-rung beliefs on it, and favours.

    Seeded through the ladder rather than by spelling a license field, exactly
    as ``conftest.seed_belief`` does: `ask` is a rung a belief earns.
    """
    with Store(root / main_id) as store:
        store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                     **loops.opened(FARMLAND, state="stalled", timescale="years",
                                    last_movement="2026-01-04",
                                    loops=store.state().loops))
        for ident in beliefs:
            store.record(Op.ASSERT, ident, "2026-08-01T00:00Z",
                         claim=f"wants to buy farmland ({ident})",
                         loop=FARMLAND, topics=["farmland"], **ladder.admitted())
            record = store.state().beliefs[ident]
            store.record(Op.ASSERT, ident, "2026-08-01T00:00Z",
                         **ladder.promote(record, to=License.ASK,
                                          acknowledged=True))
        for day in range(1, favours + 1):
            a_favour(store, t=f"2026-08-{10 + day:02d}T03:00Z",
                     day=f"2026-08-{10 + day:02d}")


class Ledger:
    """The three doors, in memory. The protocol and nothing else."""

    def __init__(self, view, *, crisis=False):
        self.view = view
        self.crisis = crisis
        self.spends: list[tuple[str, str]] = []

    def crisis_open(self, main_id):
        return self.crisis

    async def trust_view(self, main_id):
        return self.view

    async def note_ask(self, main_id, *, t, question, about):
        if self.crisis:
            return ASK_CRISIS
        self.spends.append((question, about))
        return ASK_RECORDED


# ═════════════════════════════════════════════════════════════════════════════
# matrix: favour given / no favour yet / same favour twice
# ═════════════════════════════════════════════════════════════════════════════


def test_a_high_stakes_question_with_a_favour_delivered_is_askable():
    """Matrix: *favour given*."""
    view = a_view(earned=1, spent=0)
    verdict = considered(a_question(), view=view, live=talking_about(ON_TOPIC, view=view))
    assert verdict.askable is True and verdict.reason is None
    assert verdict.stakes.worth_asking is True


@pytest.mark.cap4_favour
def test_a_high_stakes_question_with_nothing_given_is_not_askable():
    """Matrix: *no favour yet*. **The favour rule.**

    Half never asks without having just given, and the question is *held*
    rather than discarded: it is worth asking and cannot be paid for yet.
    """
    view = a_view(earned=0, spent=0)
    verdict = considered(a_question(), view=view, live=talking_about(ON_TOPIC, view=view))
    assert verdict.askable is False
    assert verdict.reason == NO_FAVOUR
    assert verdict.held is True


@pytest.mark.cap4_favour
def test_a_favour_already_spent_buys_nothing():
    """One favour, one question already asked against it: the balance is not
    spendable, and the next question is held."""
    view = a_view(earned=1, spent=1)
    verdict = considered(a_question(), view=view, live=talking_about(ON_TOPIC, view=view))
    assert verdict.reason == NO_FAVOUR


@pytest.mark.cap4_favour
def test_one_favour_makes_exactly_one_of_two_good_questions_askable():
    """Matrix: *same favour twice*. **The rule the whole currency exists for.**

    Two questions that both pass every gate, against one delivered favour.
    Exactly one becomes askable — the favour is spent by the asking, so the same
    favour cannot buy two.
    """
    view = a_view(earned=1, spent=0, beliefs={
        "b_1": {"id": "b_1", "claim": "wants to buy farmland",
                "license": str(License.ASK), "loop": FARMLAND,
                "topics": ["farmland"]},
        "b_2": {"id": "b_2", "claim": "has not walked the plot since March",
                "license": str(License.ASK), "loop": FARMLAND,
                "topics": ["farmland"]},
    })
    live = talking_about(ON_TOPIC, view=view)
    found = asks_at(
        [a_question("q_1", "b_1"), a_question("q_2", "b_2")], view=view, live=live
    )
    assert len(found) == 1
    assert {v.reason for v in queue(
        [a_question("q_1", "b_1"), a_question("q_2", "b_2")], view=view, live=live
    )} <= HELD


@pytest.mark.cap4_favour
def test_two_favours_pay_for_two_questions():
    """The other side of the same rule, so the cut is a budget rather than a
    hard-coded one."""
    view = a_view(earned=2, spent=0, beliefs={
        "b_1": {"id": "b_1", "claim": "wants to buy farmland",
                "license": str(License.ASK), "loop": FARMLAND,
                "topics": ["farmland"]},
        "b_2": {"id": "b_2", "claim": "has not walked the plot since March",
                "license": str(License.ASK), "loop": FARMLAND,
                "topics": ["farmland"]},
    })
    live = talking_about(ON_TOPIC, view=view)
    assert len(asks_at(
        [a_question("q_1", "b_1"), a_question("q_2", "b_2")], view=view, live=live
    )) == 2


@pytest.mark.cap4_favour
def test_the_same_question_emitted_twice_does_not_look_like_two_spends():
    """A producer that yielded one question twice must not make one favour look
    like it bought two — the deduplication ``choose.eligible`` also carries."""
    view = a_view(earned=2, spent=0)
    live = talking_about(ON_TOPIC, view=view)
    found = asks_at([a_question("q_1"), a_question("q_1")], view=view, live=live)
    assert [ask.question.id for ask in found] == ["q_1"]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: low stakes — the first gate, and the order of the two
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_stakes
@pytest.mark.parametrize("earned", [0, 1, 5, 100], ids=lambda n: f"balance-{n}")
def test_a_low_stakes_question_is_not_askable_at_any_balance(earned):
    """Matrix: *low stakes*. **Stakes first, and no balance overrides them.**

    Swept across the balance rather than asserted at one value, because the
    failure this guards is a gate order, and a single-balance case would pass
    with the gates reversed for every balance below the one it happened to pick.
    """
    view = a_view(loop=ROUTINE, timescale=Timescale.DAYS, earned=earned)
    verdict = considered(a_question(), view=view, live=talking_about(ON_TOPIC, view=view))
    assert verdict.askable is False
    assert verdict.reason == BELOW_THE_BAR


@pytest.mark.cap4_stakes
def test_a_question_below_the_bar_is_not_even_held():
    """*"A question that fails on stakes is not merely deferred, it is not worth
    asking at all."* Putting it in the held queue would be exactly the
    accumulation the glossary calls a defect."""
    view = a_view(loop=ROUTINE, timescale=Timescale.DAYS, earned=5)
    live = talking_about(ON_TOPIC, view=view)
    assert considered(a_question(), view=view, live=live).held is False
    assert queue([a_question()], view=view, live=live) == ()


@pytest.mark.cap4_stakes
def test_stakes_are_asked_before_the_favour_and_not_after():
    """**The order, asserted as a difference in the answer.**

    One question below the bar with nothing given, and one above it with
    nothing given. Both are unaskable, and the *reasons differ*: the first
    failed on stakes, the second is held on the favour. With the gates reversed
    both would read ``no-favour``, and the second — which is genuinely worth
    asking — would be indistinguishable from the first, which is not.
    """
    poor = a_view(loop=ROUTINE, timescale=Timescale.DAYS, earned=0)
    rich = a_view(earned=0)
    assert considered(a_question(), view=poor,
                      live=talking_about(ON_TOPIC, view=poor)).reason == BELOW_THE_BAR
    assert considered(a_question(), view=rich,
                      live=talking_about(ON_TOPIC, view=rich)).reason == NO_FAVOUR


@pytest.mark.cap4_stakes
def test_the_costlier_mistake_is_offered_first():
    """The ordering is total and deterministic: the wanting whose period is
    longest first, then the question's own id. Two builds reading one log offer
    the same question or offer none."""
    view = a_view(earned=1, spent=0, beliefs={
        "b_cheap": {"id": "b_cheap", "claim": "swims weekly",
                    "license": str(License.ASK), "loop": "swim-weekly",
                    "topics": ["farmland"]},
        "b_dear": {"id": "b_dear", "claim": "wants to buy farmland",
                   "license": str(License.ASK), "loop": FARMLAND,
                   "topics": ["farmland"]},
    })
    view = dataclasses.replace(view, loops={
        FARMLAND: {"loop": FARMLAND, "state": "stalled", "timescale": "years",
                   "last_movement": "2026-01-04"},
        "swim-weekly": {"loop": "swim-weekly", "state": "advancing",
                        "timescale": "weeks", "last_movement": "2026-08-01"},
    })
    live = talking_about(ON_TOPIC, view=view)
    found = asks_at(
        [a_question("q_a", "b_cheap"), a_question("q_b", "b_dear")],
        view=view, live=live,
    )
    assert [ask.question.about for ask in found] == ["b_dear"]


@pytest.mark.cap4_stakes
def test_the_order_is_total_and_never_broken_by_dict_iteration():
    """Equal cost, so the id breaks the tie — deterministically, in both input
    orders."""
    view = a_view(earned=2, spent=0, beliefs={
        "b_1": {"id": "b_1", "claim": "one", "license": str(License.ASK),
                "loop": FARMLAND, "topics": ["farmland"]},
        "b_2": {"id": "b_2", "claim": "two", "license": str(License.ASK),
                "loop": FARMLAND, "topics": ["farmland"]},
    })
    live = talking_about(ON_TOPIC, view=view)
    forwards = asks_at([a_question("q_1", "b_1"), a_question("q_2", "b_2")],
                       view=view, live=live)
    backwards = asks_at([a_question("q_2", "b_2"), a_question("q_1", "b_1")],
                        view=view, live=live)
    assert [a.question.id for a in forwards] == [a.question.id for a in backwards]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: topic not raised / topic raised
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_gates
def test_a_question_whose_topic_the_main_has_not_raised_is_held():
    """Matrix: *topic not raised*. **Attached lazily, never raised cold.**

    Held rather than discarded: the question is worth asking and paid for, and
    it waits for the conversation to come to it. Half never pings to ask.
    """
    view = a_view()
    verdict = considered(a_question(), view=view,
                         live=talking_about(OFF_TOPIC, view=view))
    assert verdict.askable is False
    assert verdict.reason == TOPIC_UNRAISED
    assert verdict.held is True


@pytest.mark.cap4_gates
def test_a_question_becomes_eligible_when_the_main_touches_its_topic():
    """Matrix: *topic raised*. The same view, one message later."""
    view = a_view()
    assert considered(a_question(), view=view,
                      live=talking_about(OFF_TOPIC, view=view)).askable is False
    assert considered(a_question(), view=view,
                      live=talking_about(ON_TOPIC, view=view)).askable is True


@pytest.mark.cap4_gates
def test_no_conversation_at_all_holds_every_question():
    """The nightly pass, the morning surface, a scheduler tick. ``live=None`` is
    *there is no conversation*, and *"never ping to ask"* is what that must
    mean."""
    view = a_view()
    assert on_topic(view.beliefs["b_1"], None) is False
    assert considered(a_question(), view=view, live=None).reason == TOPIC_UNRAISED


@pytest.mark.cap4_gates
def test_the_topic_floor_is_the_strand_decay_and_not_anything_above_zero():
    """**The one number in this story that was inherited rather than derived.**

    ``on_topic`` was ``match(...) > 0.0``, which is not a decision: it takes its
    effective boundary from ``Strands``' own ``EPSILON`` housekeeping value, so
    a topic mentioned once stayed "already raised" through roughly eight further
    turns of unrelated conversation. That is a retrieval artefact governing a
    governance rule.

    The floor is ``DECAY``, imported rather than typed, and it means a topic is
    live for the turn it was raised in and the one immediately after — which is
    where a reply actually lands.
    """
    from half.retrieval.strands import DECAY

    assert ON_TOPIC_FLOOR == DECAY

    view = a_view()
    belief = view.beliefs["b_1"]
    known = known_strands(view.beliefs.values(), view.loops)

    live = Strands()
    live.observe(ON_TOPIC, known)
    assert live.match({"topic:farmland"}) == 1.0
    assert on_topic(belief, live) is True

    # One turn of unrelated talk: still on topic, at exactly the floor.
    live.observe(OFF_TOPIC, known)
    assert live.match({"topic:farmland"}) == pytest.approx(ON_TOPIC_FLOOR)
    assert on_topic(belief, live) is True, "the boundary is inclusive"

    # Two turns: below the floor, and the question goes back to being held.
    live.observe(OFF_TOPIC, known)
    assert live.match({"topic:farmland"}) < ON_TOPIC_FLOOR
    assert on_topic(belief, live) is False
    assert considered(a_question(), view=view, live=live).reason == TOPIC_UNRAISED


@pytest.mark.cap4_gates
def test_a_partial_mention_at_exactly_the_floor_raises_the_topic():
    """``>=`` rather than ``>``: a message using half the tokens of a two-word
    strand did raise the topic. ``loop:buy-farmland`` against *"the farmland
    thing again"* is exactly ``ON_TOPIC_FLOOR``."""
    view = a_view(beliefs={"b_1": {"id": "b_1", "claim": "wants farmland",
                                   "license": str(License.ASK),
                                   "loop": FARMLAND}})
    live = Strands()
    live.observe(ON_TOPIC, known_strands(view.beliefs.values(), view.loops))
    assert live.match({f"loop:{FARMLAND}"}) == pytest.approx(ON_TOPIC_FLOOR)
    assert on_topic(view.beliefs["b_1"], live) is True


def test_holding_on_the_topic_is_not_an_exclusion():
    """AD-24 says retrieval *weights* and never excludes, and this is not that:
    nothing is made unreachable, the belief stays in the view, and the question
    stays in the queue with a reason. What is withheld is Half's own
    interruption."""
    view = a_view()
    live = talking_about(OFF_TOPIC, view=view)
    assert "b_1" in view.beliefs
    assert queue([a_question()], view=view, live=live)[0].question.id == "q_1"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: quarantined subject / ceiling at behave
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.ad28
@pytest.mark.cap4_gates
def test_a_question_about_a_quarantined_belief_is_not_askable():
    """Matrix: *quarantined subject*. **5a decides, not this story.**

    A pinned belief is `behave` however good its evidence, and there is no
    branch here that reads the pin: one call through the context builder's door
    answers it.
    """
    view = a_view(quarantined=True, earned=5)
    verdict = considered(a_question(), view=view,
                         live=talking_about(ON_TOPIC, view=view))
    assert verdict.reason == NOT_PERMITTED
    assert verdict.held is False


@pytest.mark.ad28
@pytest.mark.cap4_gates
@pytest.mark.parametrize("rung", RUNGS, ids=[str(r) for r in RUNGS])
def test_a_main_capped_at_behave_is_asked_nothing_at_every_rung(rung):
    """Matrix: *ceiling at `behave`*. **Without a special case for the ceiling.**

    Swept over the whole ladder, so a belief the main has fully acknowledged is
    refused for the same reason a bare one is: the cap is applied where licenses
    are resolved, not where a question is composed (AD-28). There is no
    ``if in_aftercare`` here and no field on the view from which one could be
    written.
    """
    view = a_view(rung=rung, ceiling=License.BEHAVE, earned=5)
    verdict = considered(a_question(), view=view,
                         live=talking_about(ON_TOPIC, view=view))
    assert verdict.askable is False
    assert verdict.reason == NOT_PERMITTED


@pytest.mark.ad28
@pytest.mark.cap4_gates
def test_a_belief_that_may_only_be_behaved_on_is_not_a_question():
    """`behave` is the rung at which Half acts silently. A question is the
    opposite of silent, and the rung it needs is the ladder's own word for what
    it is asking for."""
    assert ASKS_AT is License.ASK
    view = a_view(rung=License.BEHAVE, earned=5)
    assert considered(a_question(), view=view,
                      live=talking_about(ON_TOPIC, view=view)).reason == NOT_PERMITTED


@pytest.mark.cap4_gates
def test_a_question_about_a_belief_the_log_does_not_hold_is_not_askable():
    """Nothing to be wrong about, so nothing to weigh — and the reason is the
    stakes vocabulary's own word rather than a second spelling of it."""
    view = a_view()
    assert considered(a_question("q_1", "b_missing"), view=view,
                      live=talking_about(ON_TOPIC, view=view)).reason == NO_SUBJECT


@pytest.mark.parametrize(
    "question",
    [Unasked(id="", about="b_1"), Unasked(id="q_1", about=""),
     Unasked(id="  ", about="b_1"), None, "q_1"],
    ids=["no-id", "no-about", "blank-id", "none", "a-string"],
)
def test_a_question_that_cannot_be_named_is_refused_before_either_gate(question):
    """A question with no id cannot be spent against and one about nothing
    cannot be weighed. ``nameable`` is the predicate both the runtime and this
    case read.

    **And the verdict is readable whatever was passed.** ``considered`` stored
    the raw value as ``Verdict.question``, so a caller reading
    ``verdict.question.id`` after handing it a ``None`` got an
    ``AttributeError`` on the turn's own path — which this module's *"never
    raises"* contract forbids. Every verdict now carries a real ``Unasked``.
    """
    view = a_view()
    verdict = considered(question, view=view,
                         live=talking_about(ON_TOPIC, view=view))
    assert verdict.askable is False and verdict.reason == NO_SUBJECT
    assert isinstance(verdict.question, Unasked)
    assert verdict.question.id == "" or verdict.question.id == "q_1"
    assert verdict.held is False


def test_a_junk_value_travels_through_the_whole_queue_without_raising():
    """The contract end to end: a producer that emitted rubbish costs one
    question, never the main's reply."""
    view = a_view()
    live = talking_about(ON_TOPIC, view=view)
    rubbish = [None, "q_1", 7, object(), Unasked(id="", about="")]
    assert queue(rubbish, view=view, live=live) == ()
    assert asks_at(rubbish, view=view, live=live) == ()
    for verdict in verdicts(rubbish, view=view, live=live):
        assert verdict.question.id == ""
        assert verdict.reason == NO_SUBJECT


# ═════════════════════════════════════════════════════════════════════════════
# every gate alone, and every pair of them in both orders
# ═════════════════════════════════════════════════════════════════════════════


#: The six ways one question is refused, each as the smallest change that
#: produces it. Named so a sweep reports which gate broke rather than an index.
#:
#: **Three axes, not one.** An earlier version expressed every gate as
#: ``a_view`` keyword arguments, which meant two gates on disjoint keywords
#: composed to an *identical* view — so the "both orders" sweep built the same
#: object twice and asserted conjunction while claiming to assert ordering. A
#: gate can live on the view, on the question, or on the conversation, and
#: ``TOPIC_UNRAISED`` and ``NO_SUBJECT`` were missing entirely because neither
#: lives on the view.
GATES: dict[str, dict[str, object]] = {
    BELOW_THE_BAR: {"view": dict(loop=ROUTINE, timescale=Timescale.DAYS)},
    NO_WANTING: {"view": dict(loop=None)},
    NOT_PERMITTED: {"view": dict(ceiling=License.BEHAVE)},
    NO_FAVOUR: {"view": dict(earned=0)},
    TOPIC_UNRAISED: {"topic": False},
    NO_SUBJECT: {"question": Unasked(id="q_1", about="b_missing")},
}


def apply_gates(*reasons):
    """The view, question and conversation that ``reasons`` together produce.

    Merged in the order given, so a caller can compose the same pair both ways
    round and get two genuinely different constructions where the gates share an
    axis.
    """
    view_kwargs: dict[str, object] = {}
    question = a_question()
    topic = True
    for reason in reasons:
        spec = GATES[reason]
        view_kwargs.update(spec.get("view", {}))
        question = spec.get("question", question)
        topic = topic and spec.get("topic", True)
    view = a_view(**view_kwargs)
    live = talking_about(ON_TOPIC if topic else OFF_TOPIC, view=view)
    return view, question, live


@pytest.mark.cap4_gates
@pytest.mark.parametrize("reason", sorted(GATES), ids=sorted(GATES))
def test_each_gate_alone_makes_a_question_unaskable(reason):
    """Every gate, on its own, against an otherwise perfect question — and each
    one reports *its own* reason, so a gate that silently stopped firing would
    surface as another gate's answer rather than as a pass."""
    view, question, live = apply_gates(reason)
    verdict = considered(question, view=view, live=live)
    assert verdict.askable is False
    assert verdict.reason == reason


@pytest.mark.cap4_gates
@pytest.mark.parametrize(
    "pair",
    sorted(combinations(sorted(GATES), 2)),
    ids=lambda pair: f"{pair[0]}+{pair[1]}",
)
def test_every_pair_of_gates_together_still_refuses(pair):
    """**Conjunction, and the name says so.**

    Two gates that both fire must still refuse, whichever way round the fixture
    is composed — and the reason must stay inside the closed set rather than
    becoming ``None``, which is what a gate swallowing another's refusal looks
    like. Every pair is built both ways, so gates that share an axis genuinely
    differ between the two constructions.

    It does **not** test gate *ordering*, and an earlier name claimed it did:
    with each gate on its own keyword the two orders built an identical view.
    The order this story actually cares about — stakes before the favour — is
    protected by ``test_stakes_are_asked_before_the_favour_and_not_after``,
    by the balance sweep in ``test_a_low_stakes_question_is_not_askable_at_any_balance``,
    and structurally by the AST rule that ``stakes.py`` cannot see a balance.

    There are no self-pairs: ``combinations`` produces none, where the earlier
    product-with-a-skip counted six cases that asserted nothing while sitting
    inside the ``cap4`` floor.
    """
    first, second = pair
    for order in ((first, second), (second, first)):
        view, question, live = apply_gates(*order)
        verdict = considered(question, view=view, live=live)
        assert verdict.askable is False, f"{order} let a question through"
        assert verdict.reason in REASONS, f"{order} gave {verdict.reason!r}"


#: Every gate except the one this sweep varies. Crossing the topic gate with
#: itself would assert the opposite of what it means — a raised topic *does*
#: rescue a question held only on the topic, which is the whole of lazy
#: attachment.
OTHER_GATES = sorted(set(GATES) - {TOPIC_UNRAISED})


@pytest.mark.cap4_gates
@pytest.mark.parametrize("reason", OTHER_GATES, ids=OTHER_GATES)
def test_every_gate_survives_the_topic_being_raised_or_not(reason):
    """The topic axis crossed with every other gate: a raised topic must not
    rescue a question another gate refused, and no conversation at all must not
    turn a permanent refusal into a held one."""
    view, question, _ = apply_gates(reason)
    for live in (talking_about(ON_TOPIC, view=view),
                 talking_about(OFF_TOPIC, view=view), None):
        assert considered(question, view=view, live=live).askable is False


@pytest.mark.cap4_gates
def test_every_reason_the_queue_gives_is_one_of_the_closed_set():
    """A caller counting refusals counts constants, never a message (AD-22).

    The set is a *union* with the stakes vocabulary rather than a second list,
    so a reason added there is inside this one the day it is written — and
    every member is reachable, which is what stops the union growing a name
    nothing can produce.
    """
    seen = set()
    for reason in GATES:
        view, question, live = apply_gates(reason)
        seen.add(considered(question, view=view, live=live).reason)
    assert seen == set(GATES), sorted(seen ^ set(GATES))
    assert seen <= REASONS
    assert HELD < REASONS and BELOW_THE_BAR not in HELD
    # Every reason the closed set names is produced by some gate above, except
    # the two stakes refusals that need a malformed ledger rather than a view.
    assert REASONS - seen == {FINISHED, NO_PERIOD}


def test_the_same_view_and_the_same_conversation_answer_identically_twice():
    """Pure (AD-30). And not a function of time at all: no clock is injected on
    any path here, so a verdict moves when the log or the conversation moves
    and at no other moment."""
    view = a_view()
    live = talking_about(ON_TOPIC, view=view)
    answers = {considered(a_question(), view=view, live=live) for _ in range(20)}
    assert len(answers) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: queue depth — inspectable, because it is a signal
# ═════════════════════════════════════════════════════════════════════════════


def test_several_questions_held_are_inspectable_with_their_reasons():
    """Matrix: *queue depth*. Reasons rather than a count: *"eleven questions,
    all waiting on a favour"* and *"eleven questions, none of their topics ever
    raised"* are different situations a number cannot tell apart."""
    view = a_view(earned=0, beliefs={
        f"b_{n}": {"id": f"b_{n}", "claim": f"claim {n}",
                   "license": str(License.ASK), "loop": FARMLAND,
                   "topics": ["farmland"]}
        for n in range(1, 6)
    })
    live = talking_about(ON_TOPIC, view=view)
    held = queue([a_question(f"q_{n}", f"b_{n}") for n in range(1, 6)],
                 view=view, live=live)
    assert len(held) == 5
    assert {v.reason for v in held} == {NO_FAVOUR}


@pytest.mark.cap4_favour
def test_a_question_that_lost_the_budget_is_held_on_the_favour_not_dropped():
    """Matrix: *queue depth* — and the discrimination it exists for.

    Three questions pass every gate; one favour pays for one. Before review the
    other two appeared in **neither** list: ``asks_at`` sliced them off and
    ``queue`` computed askability separately, so a question that passed every
    gate and could not be paid for vanished. That is exactly the case depth is
    supposed to make visible — *"eleven waiting on a favour"* against *"eleven
    whose topic was never raised"*.
    """
    view = a_view(earned=1, spent=0, beliefs={
        f"b_{n}": {"id": f"b_{n}", "claim": f"claim {n}",
                   "license": str(License.ASK), "loop": FARMLAND,
                   "topics": ["farmland"]}
        for n in range(1, 4)
    })
    live = talking_about(ON_TOPIC, view=view)
    questions = [a_question(f"q_{n}", f"b_{n}") for n in range(1, 4)]

    offered = asks_at(questions, view=view, live=live)
    held = queue(questions, view=view, live=live)
    assert len(offered) == 1
    assert len(held) == 2 and {v.reason for v in held} == {NO_FAVOUR}
    # Nothing falls between the two lists.
    assert len(verdicts(questions, view=view, live=live)) == 3
    assert {v.question.id for v in held} | {a.question.id for a in offered} == {
        "q_1", "q_2", "q_3"
    }


@pytest.mark.cap4_favour
def test_the_budget_is_the_unspent_balance_and_not_what_was_ever_earned():
    """``earned > spent > 0``, which no depth case produced before review.

    Every fixture defaulted ``spent=0``, so ``unspent == earned`` everywhere and
    the slice was never crossed: replacing ``view.balance.unspent`` with
    ``view.balance.earned`` left the whole suite green.
    """
    view = a_view(earned=3, spent=2, beliefs={
        f"b_{n}": {"id": f"b_{n}", "claim": f"claim {n}",
                   "license": str(License.ASK), "loop": FARMLAND,
                   "topics": ["farmland"]}
        for n in range(1, 4)
    })
    live = talking_about(ON_TOPIC, view=view)
    questions = [a_question(f"q_{n}", f"b_{n}") for n in range(1, 4)]
    assert view.balance.unspent == 1 and view.balance.earned == 3
    assert len(asks_at(questions, view=view, live=live)) == 1
    assert len(queue(questions, view=view, live=live)) == 2


@pytest.mark.cap4_favour
def test_the_one_question_offered_is_the_costliest_mistake(tmp_path):
    """``next_ask`` returns the **first** of the ordering, and every case
    through that door used to pass a single-element list — so returning
    ``found[-1]`` was indistinguishable from returning ``found[0]``.

    Two questions, two favours, different periods: the farmland loop outranks
    the weekly swim, and being wrong about it for a year is why.
    """
    view = a_view(earned=2, spent=0, beliefs={
        "b_cheap": {"id": "b_cheap", "claim": "swims weekly",
                    "license": str(License.ASK), "loop": "swim-weekly",
                    "topics": ["farmland"]},
        "b_dear": {"id": "b_dear", "claim": "wants to buy farmland",
                   "license": str(License.ASK), "loop": FARMLAND,
                   "topics": ["farmland"]},
    })
    view = dataclasses.replace(view, loops={
        FARMLAND: {"loop": FARMLAND, "state": "stalled", "timescale": "years",
                   "last_movement": "2026-01-04"},
        "swim-weekly": {"loop": "swim-weekly", "state": "advancing",
                        "timescale": "weeks", "last_movement": "2026-08-01"},
    })
    live = talking_about(ON_TOPIC, view=view)
    questions = [a_question("q_a", "b_cheap"), a_question("q_b", "b_dear")]
    assert len(asks_at(questions, view=view, live=live)) == 2

    held = UnaskedQueue(ledger=Ledger(view))
    chosen = asyncio.run(held.next_ask("vidit", questions=questions, live=live))
    assert chosen is not None and chosen.question.about == "b_dear"
    assert chosen.stakes.cost_days == 365


def test_an_askable_question_is_ready_rather_than_held():
    """A question that may be asked right now is not waiting for anything, so
    it is not in the held queue — otherwise depth would count readiness."""
    view = a_view(earned=1)
    live = talking_about(ON_TOPIC, view=view)
    assert queue([a_question()], view=view, live=live) == ()
    assert len(asks_at([a_question()], view=view, live=live)) == 1


def test_a_refused_question_leaves_the_queue_rather_than_accumulating():
    """Stakes and the ladder are permanent refusals, so they do not build up a
    backlog nobody will ever ask."""
    view = a_view(loop=ROUTINE, timescale=Timescale.DAYS, earned=1)
    assert queue([a_question()], view=view,
                 live=talking_about(ON_TOPIC, view=view)) == ()


def test_nothing_at_all_produces_an_empty_queue_and_no_asks():
    view = a_view()
    live = talking_about(ON_TOPIC, view=view)
    assert queue(None, view=view, live=live) == ()
    assert asks_at(None, view=view, live=live) == ()
    assert asks_at([], view=view, live=live) == ()


# ═════════════════════════════════════════════════════════════════════════════
# matrix: crisis — the mode suspends the currency
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap12
@pytest.mark.cap4_gates
def test_a_main_in_crisis_is_asked_nothing():
    """Matrix: *crisis*. The mode suspends Half's ordinary behaviour entirely
    and the trust currency is void inside it (constitution)."""
    view = a_view(earned=5)
    live = talking_about(ON_TOPIC, view=view)
    held = UnaskedQueue(ledger=Ledger(view, crisis=True))
    assert asyncio.run(held.next_ask("vidit", questions=[a_question()],
                                     live=live)) is None
    assert asyncio.run(held.waiting("vidit", questions=[a_question()],
                                    live=live)) == ()


@pytest.mark.cap12
@pytest.mark.cap4_gates
def test_the_same_main_out_of_crisis_is_asked():
    """The mode is the difference, and nothing else about the fixture is."""
    view = a_view(earned=5)
    live = talking_about(ON_TOPIC, view=view)
    held = UnaskedQueue(ledger=Ledger(view, crisis=False))
    assert asyncio.run(held.next_ask("vidit", questions=[a_question()],
                                     live=live)) is not None


@pytest.mark.cap12
@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_main_who_enters_crisis_between_the_choice_and_the_spend_is_not_asked(
    tmp_path,
):
    """**The last point at which the mode is still assertable**, and the
    ordering nobody would write a single-threaded case for.

    A question is chosen, the main enters crisis, and the spend is attempted.
    ``note_ask`` re-asserts the mode under the main's own mutex — exactly as
    ``claim_day`` does — so nothing is recorded and nothing is asked.
    """
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
        assert asyncio.run(registry.trust_view("vidit")).balance.spendable
        asyncio.run(registry.suspend_for_crisis(
            "vidit", t="2026-09-01T09:00Z", tier="disclosure", score=2))
        outcome = asyncio.run(registry.note_ask(
            "vidit", t="2026-09-01T10:00Z", question="q_1", about="b_1"))
        assert outcome == ASK_CRISIS
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []


# ═════════════════════════════════════════════════════════════════════════════
# the door: narrowed, and the spend that goes through it
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_structure
def test_the_queue_is_handed_a_projection_and_not_the_fold():
    """**Story 10's lesson, applied a second time.**

    The morning surface was handed ``State`` entire, and review found that
    ``if state.aftercare is not None: return Silence(...)`` passed the whole
    suite while permanently silencing a main. The same line here is a main who
    is never asked anything again. So the fields are *absent*: reaching for one
    is an ``AttributeError``, which no wording gets around.

    The allowlist is read from the module rather than copied here, so a field
    added to ``VISIBLE`` on purpose is covered and one added by accident is not.
    """
    assert set(view_fields()) == set(VISIBLE) | {"ceiling", "balance"}
    for absent in ("crisis", "aftercare", "schedule", "spoke", "touches"):
        assert absent not in view_fields()
        assert absent in {f.name for f in dataclasses.fields(State)}, (
            f"{absent} left State; this case no longer asserts anything"
        )
    view = a_view()
    for absent in ("crisis", "aftercare", "schedule", "spoke", "touches"):
        with pytest.raises(AttributeError):
            getattr(view, absent)


@pytest.mark.cap4_structure
def test_the_allowlist_is_what_the_projection_is_built_from():
    """``narrowed_for_trust`` hard-coded ``beliefs=`` and ``loops=``, so
    ``VISIBLE`` was documentation rather than an allowlist — it could have
    listed anything and changed nothing.

    Asserted by construction: a state field is copied **because** it is named in
    the constant, so removing a name removes the field.
    """
    state = State()
    state.beliefs["b_1"] = {"id": "b_1"}
    state.loops[FARMLAND] = {"loop": FARMLAND}
    view = narrowed_for_trust(state, Ceiling(), balance=Balance())
    for name in VISIBLE:
        assert getattr(view, name), f"{name} is on the allowlist and was dropped"

    narrowed = ast.parse(
        (ROOT / "half/trust/unasked.py").read_text(encoding="utf-8")
    )
    body = next(
        node for node in ast.walk(narrowed)
        if isinstance(node, ast.FunctionDef) and node.name == "narrowed_for_trust"
    )
    names = {n.id for n in ast.walk(body) if isinstance(n, ast.Name)}
    assert "VISIBLE" in names, "the projection does not read its own allowlist"
    passed = {
        kw.arg
        for node in ast.walk(body)
        if isinstance(node, ast.Call) for kw in node.keywords
    }
    assert not passed & set(VISIBLE), (
        "a visible field is passed by name, so the allowlist is decorative"
    )


@pytest.mark.cap4_structure
def test_the_registry_actually_satisfies_the_narrow_door():
    """``TrustLedger`` is a protocol, and nothing bound the real registry to it:
    a keyword-only parameter renamed on one side drifts them apart with every
    structural case green.

    ``runtime_checkable`` checks the names; the signatures are compared here,
    because *that* is the half that drifts.
    """
    assert isinstance(ActorRegistry, type)
    registry = ActorRegistry.__new__(ActorRegistry)
    assert isinstance(registry, TrustLedger)
    for name in ("crisis_open", "trust_view", "note_ask"):
        promised = inspect.signature(getattr(TrustLedger, name))
        actual = inspect.signature(getattr(ActorRegistry, name))
        assert list(promised.parameters) == list(actual.parameters), name
        for arg, expected in promised.parameters.items():
            assert actual.parameters[arg].kind == expected.kind, f"{name}.{arg}"


@pytest.mark.cap4_structure
def test_the_vocabulary_a_verdict_is_read_against_is_importable_beside_it():
    """``Verdict.reason`` and the spend outcomes are documented as closed sets.
    A closed set whose members are not importable from the package is one every
    consumer re-spells — which is how two spellings of one word start."""
    import half.trust as package

    for name in (*REASONS, *ASK_OUTCOMES):
        constant = next(
            (n for n in package.__all__ if getattr(package, n, None) == name),
            None,
        )
        assert constant is not None, f"{name!r} has no importable name"
    for name in ("ASKS_AT", "HELD", "REASONS", "VISIBLE", "ON_TOPIC_FLOOR",
                 "on_topic", "may_be_raised", "verdicts", "tombstoned"):
        assert name in package.__all__ and hasattr(package, name), name
    # And nothing in ``__all__`` shadows a submodule, which is how
    # ``half.trust.balance`` became a function for anyone who imported the
    # package first.
    assert not {"balance", "stakes", "unasked"} & set(package.__all__)


@pytest.mark.cap4_structure
def test_the_narrowing_copies_rather_than_references():
    """A view handed out cannot change under its reader while the actor keeps
    working."""
    state = State()
    state.beliefs["b_1"] = {"id": "b_1", "claim": "one"}
    state.loops[FARMLAND] = {"loop": FARMLAND, "state": "stalled"}
    view = narrowed_for_trust(state, Ceiling(), balance=Balance(earned=1))
    state.beliefs["b_1"]["claim"] = "mutated"
    state.beliefs["b_2"] = {"id": "b_2"}
    assert view.beliefs["b_1"]["claim"] == "one"
    assert "b_2" not in view.beliefs


@pytest.mark.cap4_structure
def test_the_balance_is_handed_in_rather_than_derived_from_the_fold():
    """The whole of AD-30 for this story, as a signature. ``narrowed_for_trust``
    takes the balance keyword-only and undefaulted, so a caller that derived one
    from ``state`` would have to write it out — and there is nothing on
    ``State`` to derive it from."""
    with pytest.raises(TypeError):
        narrowed_for_trust(State(), Ceiling())


def test_the_registry_door_narrows_and_carries_the_balance(tmp_path):
    """The real door, not the fake one: the registry folds the log once, reads
    the balance off the same records, and hands back a ``TrustView``."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
            seeded.record(Op.LOOP_TRANSITION, "l_1", "2026-09-01T00:00Z",
                          **loops.opened(FARMLAND, state="stalled",
                                         timescale="years",
                                         last_movement="2026-01-04",
                                         loops=seeded.state().loops))
        view = asyncio.run(registry.trust_view("vidit"))
        assert isinstance(view, TrustView)
        assert view.balance == Balance(earned=1, spent=0)
        assert FARMLAND in view.loops
        assert view.ceiling.rung is License.ASSERT
    finally:
        registry.close()


def test_the_registry_door_carries_the_ceiling_the_log_set(tmp_path):
    """A cap read from a stale derived view is a capped main reading as
    uncapped, which is the one window AD-28 exists to close. It comes out of
    the same fold the beliefs do."""
    registry = ActorRegistry(tmp_path)
    try:
        asyncio.run(registry.suspend_for_crisis(
            "vidit", t="2026-09-01T09:00Z", tier="disclosure", score=2))
        assert asyncio.run(
            registry.trust_view("vidit")
        ).ceiling.rung is License.BEHAVE
    finally:
        registry.close()


@pytest.mark.cap4_structure
@pytest.mark.ad28
def test_the_door_reads_a_cap_the_derived_view_has_not_seen_yet(tmp_path):
    """**The window ``trust_view`` folds the log to close**, reproduced.

    ``Store.append`` writes the line and *then* rebuilds, so a crash between the
    two leaves the derived view behind the log — and a cap read from there is a
    capped main reading as uncapped. Switching ``trust_view`` to
    ``actor.store.state()`` left the whole suite green before this case, because
    every other fixture rebuilt.

    Here the ``ceiling`` record goes straight onto the log with no rebuild, so
    SQLite still says uncapped. The view must come back capped.
    """
    registry = ActorRegistry(tmp_path)
    try:
        seed_a_main(tmp_path)
        assert asyncio.run(
            registry.trust_view("vidit")).ceiling.rung is License.ASSERT

        async def cap_behind_the_view():
            async with registry.acquire("vidit") as actor:
                actor.store.log.append(make(
                    Op.CEILING, "c_1", "2026-09-01T09:00Z",
                    **ladder.ceiling_fields(Ceiling(License.BEHAVE),
                                            because="aftercare (CAP-12)"),
                ))
                assert actor.store.state().ceiling is None, (
                    "the derived view already saw it; this case asserts nothing"
                )
            return await registry.trust_view("vidit")

        assert asyncio.run(cap_behind_the_view()).ceiling.rung is License.BEHAVE
    finally:
        registry.close()


@pytest.mark.cap4_favour
def test_the_composition_spends_only_through_the_registrys_door(tmp_path):
    """``UnaskedQueue.spend`` reaches the log through the one narrow door, so
    a second writer is not merely absent — there is no path to one.

    **The ``Ask`` is obtained the legitimate way**, from ``next_ask``. An
    earlier version of this case built one by hand, which meant the suite
    *demonstrated* the forgery route rather than closing it — see
    ``test_a_hand_built_ask_that_passed_no_gate_is_refused``.
    """
    registry = ActorRegistry(tmp_path)
    try:
        seed_a_main(tmp_path)
        held = UnaskedQueue(ledger=registry)
        view = asyncio.run(registry.trust_view("vidit"))
        live = talking_about(ON_TOPIC, view=view)
        ask = asyncio.run(held.next_ask("vidit", questions=[a_question()],
                                        live=live))
        assert ask is not None and ask.question.id == "q_1"
        outcome = asyncio.run(held.spend("vidit", t="2026-09-01T10:00Z",
                                         ask=ask, live=live))
        assert outcome == ASK_RECORDED
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 1
    finally:
        registry.close()


@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_hand_built_ask_that_passed_no_gate_is_refused(tmp_path):
    """**The central defect review found, closed at the queue as well.**

    ``Ask`` is a plain frozen dataclass and its docstring once claimed *"there
    is no constructor path to it that skips a gate"*. There is: review built one
    for a question about a belief that does not exist, with ``worth_asking``
    false, and watched ``spend`` record it and burn a favour.

    The type still cannot enforce anything — so nothing trusts it. ``spend``
    re-runs every gate against a freshly read view, and the registry re-derives
    the permission under the mutex (``tests/test_trust.py``). Refused twice
    over, and the balance does not move.
    """
    registry = ActorRegistry(tmp_path)
    try:
        seed_a_main(tmp_path)
        held = UnaskedQueue(ledger=registry)
        view = asyncio.run(registry.trust_view("vidit"))
        live = talking_about(ON_TOPIC, view=view)
        forged = Ask(
            question=Unasked(id="q_junk", about="nonexistent"),
            stakes=Stakes(worth_asking=False, reason=BELOW_THE_BAR, cost_days=1),
        )
        assert asyncio.run(held.spend("vidit", t="2026-09-01T10:00Z",
                                      ask=forged, live=live)) == ASK_REFUSED
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 0
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []


@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_topic_that_went_cold_between_the_choice_and_the_spend_refuses_it(tmp_path):
    """The ordinary staleness route, which is the forged-permission route seen
    from the other side: the conversation moves on between choosing a question
    and paying for it, and a question is attached to the conversation that
    *already touches* its topic — not to one that used to."""
    registry = ActorRegistry(tmp_path)
    try:
        seed_a_main(tmp_path)
        held = UnaskedQueue(ledger=registry)
        view = asyncio.run(registry.trust_view("vidit"))
        ask = asyncio.run(held.next_ask(
            "vidit", questions=[a_question()],
            live=talking_about(ON_TOPIC, view=view)))
        assert ask is not None
        assert asyncio.run(held.spend(
            "vidit", t="2026-09-01T10:00Z", ask=ask,
            live=talking_about(OFF_TOPIC, OFF_TOPIC, view=view),
        )) == ASK_REFUSED
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 0
    finally:
        registry.close()


@pytest.mark.cap4_favour
def test_choosing_and_holding_a_question_writes_nothing(tmp_path):
    """**Never a silent spend.** ``next_ask`` and ``waiting`` answer and write
    nothing; only ``spend`` appends."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
            seeded.record(Op.LOOP_TRANSITION, "l_1", "2026-09-01T00:00Z",
                          **loops.opened(FARMLAND, state="stalled",
                                         timescale="years",
                                         last_movement="2026-01-04",
                                         loops=seeded.state().loops))
            seeded.record(Op.ASSERT, "b_1", "2026-09-01T04:00Z",
                          claim="wants to buy farmland", loop=FARMLAND,
                          topics=["farmland"], **ladder.admitted())
            record = seeded.state().beliefs["b_1"]
            seeded.record(Op.ASSERT, "b_1", "2026-09-01T04:01Z",
                          **ladder.promote(record, to=License.ASK,
                                           acknowledged=True))
        view = asyncio.run(registry.trust_view("vidit"))
        held = UnaskedQueue(ledger=registry)
        live = talking_about(ON_TOPIC, view=view)
        for _ in range(3):
            assert asyncio.run(held.next_ask(
                "vidit", questions=[a_question()], live=live)) is not None
            asyncio.run(held.waiting("vidit", questions=[a_question()], live=live))
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 0
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []


# ═════════════════════════════════════════════════════════════════════════════
# structure: nothing here asks, and nothing here holds a word of what it would
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_structure
def test_nothing_in_the_queue_holds_a_word_of_a_question(store):
    """AD-22 at the layer where it becomes permanent. ``Unasked`` carries two
    ids and no text, and an ``asked`` record carries the same two — so what Half
    asked is nowhere in the log, in the fold, or on any value here."""
    fields = {f.name for f in dataclasses.fields(Unasked)}
    assert fields == {"id", "about"}
    assert not fields & {"text", "claim", "wording", "answer", "prompt"}


@pytest.mark.cap4_structure
def test_nothing_in_the_trust_package_can_reach_a_channel():
    """*Nothing here asks anything.* The engine that composes and delivers a
    question is story 11, and the guarantee is that this package has no name
    for a channel, a send or a draft."""
    for path in sorted((ROOT / "half/trust").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        reached = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        } | {
            alias.name.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".")[-1]
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert not reached & {"channel", "send", "draft_link", "capability_query",
                              "Channel", "model", "ModelProvider"}, (
            f"{path.name} can reach a channel; this story decides whether a "
            f"question may be asked and never asks one"
        )


#: Every package that reaches a main's log through an injected door, with the
#: door it is allowed. **Both are swept by one rule**, which is the correction
#: story 11's review forced: its first build copied this guard into its own file
#: as a string-prefix denylist, and both of 5b's known bypasses walked straight
#: past the copy. A predicate worth having twice is worth having once.
GUARDED: Final[tuple[tuple[str, object], ...]] = (
    ("half/trust", TrustLedger),
    ("half/questions", QuestionLedger),
)


@pytest.mark.cap4_structure
@pytest.mark.parametrize(
    "package, protocol", GUARDED, ids=[name for name, _ in GUARDED]
)
def test_the_package_reaches_a_log_only_through_the_narrow_door(package, protocol):
    """One writer, one door. A second path to a main's log is a second writer,
    and the single writer is what lets the store skip a journal (AD-1).

    Two halves. The package may not open a store at all — no ``Store``, no
    ``BeliefLog``, no path to a main's directory — and what it asks of the
    ledger it *is* given must be inside that package's own protocol. Reaching
    for one method more is how a narrow door becomes ``State`` again, which is
    the failure story 10's review found.

    **``half/questions`` is swept here rather than in its own file**, because a
    copy of this rule is a weaker copy of this rule: story 11 shipped one, and
    ``from half.store import store as _second`` and ``self.ledger.acquire(...)``
    both passed it.
    """
    door = door_of(protocol)
    assert {"crisis_open", "trust_view", "note_ask"} <= door, sorted(door)

    for path in sorted((ROOT / package).rglob("*.py")):
        offending = reaches(path, CLOSED)
        assert not offending, (
            f"{path.name} opens a store of its own: {offending}"
        )
        asked = ledger_calls(path)
        assert asked <= door, (
            f"{path.name} asks the ledger for {sorted(asked - door)}, which is "
            f"outside the narrow door"
        )


@pytest.mark.cap4_structure
@pytest.mark.parametrize(
    "package", [name for name, _ in GUARDED], ids=[name for name, _ in GUARDED]
)
def test_no_package_that_decides_whether_to_ask_can_reach_outward(package):
    """*"No model call, no generated prose"*, and no channel to say it on.

    Asserted structurally, because *"it does not call a model today"* decays the
    first time somebody reaches for one — and the reach would be invisible: a
    question composed by a model still looks like a question. Written against
    resolved dotted roots for the reason the store rule is: story 11's first
    version compared string prefixes, which ``from half import model`` walks
    past.
    """
    for path in sorted((ROOT / package).rglob("*.py")):
        offending = reaches(path, UNREACHABLE)
        assert not offending, f"{path.name} can reach outward: {offending}"


@pytest.mark.cap4_structure
def test_the_door_scan_catches_the_line_it_exists_for(tmp_path):
    """A guard nobody has run against the mutation it forbids is a guard nobody
    knows the reach of — and this one replaced a word list that reported
    ``list.append`` as a log write."""
    reaching = tmp_path / "reaching.py"
    reaching.write_text(
        "class Q:\n"
        "    async def go(self, main_id):\n"
        "        held = []\n"
        "        held.append(1)\n"
        "        return await self.ledger.whole_fold(main_id)\n",
        encoding="utf-8",
    )
    assert ledger_calls(reaching) == {"whole_fold"}


@pytest.mark.cap4_structure
@pytest.mark.parametrize(
    "line",
    [
        "from half.store import store as _second",
        "import half.store.store",
        "from half.store.store import Store",
        "from half.store import log",
        "import half.actor.registry as _r",
        "from half.actor import ActorRegistry",
    ],
    ids=["aliased-package", "dotted", "direct", "log", "aliased-actor",
         "package-attr"],
)
def test_the_import_scan_catches_every_spelling_of_a_second_store(tmp_path, line):
    """**The bypass review actually wrote, and the five neighbours of it.**

    ``from half.store import store as _second`` has ``ImportFrom.module ==
    "half.store"``, which the earlier four-string denylist did not contain — so
    a real second writer inside the trust package left the whole suite green.
    Each of these resolves to something under a closed root now.
    """
    bypass = tmp_path / "bypass.py"
    bypass.write_text(f"{line}\n", encoding="utf-8")
    reached = resolved_imports(bypass)
    assert any(
        name == root or name.startswith(f"{root}.")
        for name in reached for root in CLOSED
    ), f"the scan does not see: {line}"


@pytest.mark.cap4_structure
def test_the_import_scan_passes_the_imports_the_package_legitimately_makes():
    """The other half: a scan that fired on everything would be as useless as
    one that fired on nothing. ``half.store.records`` and ``half.store.fold``
    are read for their shapes and carry no writer."""
    legitimate = {"half.store.records.QUESTION", "half.store.fold.State",
                  "half.store.ops.Op", "half.governance.ladder.Ceiling"}
    assert not any(
        name == root or name.startswith(f"{root}.")
        for name in legitimate for root in CLOSED
    )


@pytest.mark.cap4_structure
def test_the_queue_reads_no_clock_and_no_ambient_state():
    """None of the gates is a function of time, so a clock here would be a
    verdict that changed while nothing did (AD-30)."""
    from tests.test_purity import AMBIENT_CALLS

    for path in sorted((ROOT / "half/trust").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else
            node.func.id if isinstance(node.func, ast.Name) else ""
            for node in ast.walk(tree) if isinstance(node, ast.Call)
        }
        assert not called & AMBIENT_CALLS, (
            f"{path.name} calls {sorted(called & AMBIENT_CALLS)}"
        )


@pytest.mark.cap4_structure
def test_the_rung_is_decided_through_the_one_door():
    """AD-28. ``half/trust/unasked.py`` asks ``half.context.build.resolve`` —
    *the* place a license becomes a decision — rather than reaching past it into
    the ladder's rule set, which would be a second reader with the ceiling
    capping only one of them."""
    tree = ast.parse((ROOT / "half/trust/unasked.py").read_text(encoding="utf-8"))
    imported = {
        f"{node.module}.{alias.name}"
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "half.context.build.resolve" in imported
    assert not imported & {
        "half.governance.ladder.permitted", "half.governance.ladder.own_rung",
        "half.governance.ladder.rung_of", "half.governance.ladder.quarantined",
    }


@pytest.mark.cap4_structure
def test_a_verdict_carries_a_reason_exactly_when_it_refuses():
    """AD-32's shape: a refusal that carries no reason leaves the metrics path
    with nothing to count, and a permission that carries one is a caller about
    to log a refusal that did not happen."""
    view = a_view()
    live = talking_about(ON_TOPIC, view=view)
    allowed = considered(a_question(), view=view, live=live)
    assert allowed.askable and allowed.reason is None
    refused = considered(a_question(), view=a_view(earned=0), live=live)
    assert not refused.askable and refused.reason is not None
    assert Verdict(question=a_question()).held is False
