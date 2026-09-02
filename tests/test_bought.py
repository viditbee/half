"""CAP-4 story 11: the questions channel is bought, and asked on the turn.

``tests/test_unasked.py`` proves the gates decide correctly and holds the narrow
door for both packages. ``tests/test_questions.py`` holds the minting and the
re-ask arithmetic. This file proves **something calls them, in the one place the
gates make sense** — which is the whole of story 11, because story 5b shipped the
currency, the gates and the spend with no production caller at all, and an
`ask`-rung belief reached the wire as a question line with no favour spent.

**Every case here drives the real ``Runtime``.** That is the correction review
loop 1 forced. The first build delivered on the morning surface and every green
case called a helper that manufactured live strands immediately before the run —
the one condition a scheduler tick never supplies — so the suite could not see
that Half was pinging every main every morning and paying for it with the message
that carried the question. A test that has to arrange the impossible is a test
about something that does not happen.

Three rules carry the story and each is asserted in the strongest form
available:

* **The channel is bought by what ``build`` is handed, never by what it
  filters.** A builder that reads the rung and decides for itself which beliefs
  deserve a question can be made to decide wrongly; one that can only emit what
  it was handed cannot. Asserted behaviourally, off the live store and through
  the real turn, *and* as an exhaustive truth table against an independently
  written expectation — every rung × every ceiling × every way of being bought or
  not — which no inverted guard, ternary or ``match`` can satisfy.
* **One question per send, ever.** Not counted off a fixture — which passes for
  whatever the fixture happens to contain — but *structural*: the context field
  is a ``Question | None`` and the builder's parameter is a single id, so a
  second question has nowhere to go.
* **The favour precedes the question and is spent only when it is asked.** The
  turn path writes nothing the balance counts as delivered, so a question cannot
  be funded by the message that carries it; and no spend happens until the built
  text actually carries a question line.

**Nothing here waits for real time and nothing here reads a clock**: every
instant is chosen by the test and passed in through the inbound stamp, which is
the design under test (AD-30). Nothing here reaches a network or a model.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import typing
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime, question_line, respond
from half.channel.telegram import TelegramChannel
from half.civil import DAY
from half.context.build import build as build_context
from half.context.build import bought_question, resolve
from half.context.channels import CHANNELS, Context, Question, Topic
from half.errors import SendFailed
from half.governance import ladder
from half.governance.ladder import RUNGS, Ceiling, License
from half.loops import ledger as loops
from half.loops.timescale import PERIOD_DAYS, Timescale
from half.questions.engine import (
    NOTHING_OFFERED,
    Purchase,
    QuestionEngine,
    QuestionLedger,
)
from half.questions.mint import question_id
from half.retrieval.port import Candidate as RankedBelief
from half.retrieval.prefix import build_prefix
from half.schedule.clock import stamp
from half.store.ops import TOUCH_TENSION, Op
from half.store.records import ABOUT, ASKED_FIELDS, QUESTION
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.touch import Origin
from half.trust.balance import balance
from half.trust.unasked import ASK_UNAFFORDABLE, TrustLedger
from tests.conftest import FakeTransport, msg, reaches, resolved_imports

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the instant every surface case in this tree builds
#: from. Carried in on the *inbound* stamp, which is the only clock a turn has.
NOON = 1_788_264_000.0
NOW = stamp(NOON)

ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")

#: Two wantings on **different** timescales, so *"the costlier mistake"* is a
#: real comparison rather than a tie broken by an id.
FARMLAND = "buy-farmland"
PASSPORT = "renew-passport"

#: Belief id -> (claim, loop, topics), and every id is chosen so that it can
#: never collide with a turn's own belief (``b_<external_id>``).
#:
#: **The claims share no word with their own topics or loop slug.** AD-18's drop
#: rule is per belief and word-level — a topic echoing the claim kills the whole
#: item — so a fixture whose claim said "farmland" would build an empty context
#: and every case below would pass having asserted nothing about the purchase.
#:
#: ``b_land`` is deliberately the **lower id** and, by default, the **shorter**
#: period, so that a case about the costlier mistake has to make the two
#: disagree rather than letting the id tiebreak pick the same winner.
CLAIMS = {
    "b_land": ("has not walked that plot since March", FARMLAND, ["farmland"]),
    "b_trip": ("left it until six weeks before flying", PASSPORT, ["travel"]),
}

#: A message that raises the farmland topic and retrieves the belief on it. The
#: loop slug is in the FTS prefix (``half.retrieval.prefix``) and is what the
#: strand key is built from, so one word does both.
ON_TOPIC = "farmland again please"
OFF_TOPIC = "the concert last night was good"


# ── the harness ──────────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def ago(days):
    return stamp(NOON - days * DAY)


def seed(
    root,
    *,
    main_id="vidit",
    beliefs=("b_land",),
    rung=License.ASK,
    scales=None,
    favours=1,
    quarantine=None,
    asks=(),
    replies=(),
    extra=(),
):
    """One main, with wantings, `ask`-rung beliefs on them, and favours.

    Seeded **through the ladder**, exactly as ``conftest.seed_belief`` does: a
    rung is earned by a promotion involving the main, never spelled into a
    record, so nothing here can mint a permission the product cannot.

    ``favours`` are delivered morning messages — a ``touch`` that marks a day
    *and* says a message was sent, which is the only thing that earns. They are
    dated **before** the turn, because a favour must precede it.
    """
    scales = dict({FARMLAND: Timescale.YEARS, PASSPORT: Timescale.MONTHS}
                  if scales is None else scales)
    with Store(root / main_id, prefix=build_prefix) as store:
        for index, (slug, scale) in enumerate(scales.items()):
            store.record(
                Op.LOOP_TRANSITION, f"l_{index}", "2026-08-01T00:00Z",
                **loops.opened(slug, state="stalled", timescale=str(scale),
                               last_movement="2026-01-04",
                               loops=store.state().loops),
            )
        for ident in beliefs:
            claim, slug, topics = CLAIMS[ident]
            store.record(
                Op.ASSERT, ident, "2026-08-01T00:00Z", claim=claim, loop=slug,
                topics=topics, subject="self",
                # A receipt, because `assert` requires a citation into Half's
                # own evidence and this fixture is swept over every rung. It
                # changes nothing below `assert`.
                **ladder.admitted(support=[f"s_{ident}"]),
            )
            record = store.state().beliefs[ident]
            if rung is not ladder.FLOOR:
                store.record(
                    Op.ASSERT, ident, "2026-08-01T00:00Z",
                    **ladder.promote(record, to=rung, acknowledged=True),
                )
            if quarantine is not None and ident in quarantine:
                record = store.state().beliefs[ident]
                candidate = ladder.quarantine_candidate(record, reason="asked")
                store.record(Op.ASSERT, ident, "2026-08-01T00:00Z",
                             **ladder.quarantine(record, candidate=candidate,
                                                 answered=True))
        for ident, claim in extra:
            store.record(Op.ASSERT, ident, "2026-08-01T00:00Z", claim=claim,
                         subject="self", topics=["weather"],
                         **ladder.admitted(support=[f"s_{ident}"]))
            record = store.state().beliefs[ident]
            store.record(Op.ASSERT, ident, "2026-08-01T00:00Z",
                         **ladder.promote(record, to=License.ASSERT,
                                          acknowledged=True))
        for day in range(favours):
            marker = stamp(NOON - (day + 2) * DAY)[:10]
            store.record(
                Op.TOUCH, f"tc_{marker}", f"{marker}T03:00Z",
                **touch_module.spoke(day=marker, origin=ORIGIN, loops=()),
            )
        for about, when in asks:
            store.record(Op.ASKED, f"qa_{when}", when,
                         question=question_id(about), about=about)
        for when in replies:
            store.record(Op.ASSERT, f"b_in_{when}", when, subject="self",
                         claim="a reply about something", ledger="stated",
                         **ladder.admitted())


def a_turn(
    registry,
    *,
    text=ON_TOPIC,
    main_id="vidit",
    engine=True,
    at=NOON,
    message_id="m1",
    transport=None,
):
    """One real inbound turn, through the real runtime and the real gate.

    ``engine`` is what makes a runtime an asker. ``None`` is the fail-closed
    default and is what every caller that predates story 11 gets.
    """
    transport = transport or FakeTransport(
        [msg(text=text, message_id=message_id, chat_id="123", date=int(at))]
    )
    channel = TelegramChannel(transport=transport, mains={"123": main_id})
    runtime = Runtime(
        channel=channel, registry=registry,
        questions=QuestionEngine(ledger=registry) if engine else None,
    )
    asyncio.run(runtime.run())
    return transport


def sent(transport):
    return "".join(text for _, text in transport.sent)


def spends(root, main_id="vidit"):
    """Every ``asked`` record in this main's log, in order."""
    with Store(root / main_id) as store:
        return [r for r in store.log if r.op is Op.ASKED]


def balance_of(root, main_id="vidit"):
    with Store(root / main_id) as store:
        return balance(store.log)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the ordinary buy / no favour / two candidates, one favour
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_the_ordinary_buy_spends_a_favour_and_puts_one_question_on_the_wire(
    registry, tmp_path
):
    """Matrix: *the ordinary buy*. **The sentence story 5b could not say.**

    One `ask`-rung belief on a live wanting, its topic raised **by the main's
    own message**, one delivered favour unspent — and the question reaches them
    attached to the reply they were owed anyway, having been paid for.
    """
    seed(tmp_path, favours=1)

    transport = a_turn(registry)

    body = sent(transport)
    assert "question[b_land]" in body
    assert body.count("question[") == 1
    recorded = spends(tmp_path)
    assert [r.data[QUESTION] for r in recorded] == [question_id("b_land")]
    assert [r.data[ABOUT] for r in recorded] == ["b_land"]
    assert balance_of(tmp_path).spent == 1


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_with_nothing_given_no_question_is_asked_and_nothing_is_spent(
    registry, tmp_path
):
    """Matrix: *no favour*. **The favour rule.**

    The reply still goes out — the main asked something — and carries no
    question. Nothing is spent and no record is written.
    """
    seed(tmp_path, favours=0)

    transport = a_turn(registry)

    assert transport.sent, "the main is still owed an answer"
    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []
    assert balance_of(tmp_path).spent == 0


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_a_turn_cannot_fund_its_own_question(registry, tmp_path):
    """Matrix: *today's own favour*. **The defect review loop 1 found.**

    The first build spent after the morning claimed the day, and story 10 claims
    a day by writing ``sent=True`` — which is exactly what earns — so every
    morning funded the question it carried and a main with zero favours was
    asked. On the turn path this is structural rather than checked: **nothing a
    turn writes is a delivered favour.** So a turn against a log with no touch
    at all leaves the balance where it was, and the question is unaffordable
    however many turns the main takes.
    """
    seed(tmp_path, favours=0)
    before = balance_of(tmp_path)
    assert before.earned == 0

    for index in range(3):
        a_turn(registry, message_id=f"m{index}", at=NOON + index)

    after = balance_of(tmp_path)
    assert after.earned == 0, "a turn wrote something the balance counts as given"
    assert after.spent == 0
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_two_affordable_questions_and_one_favour_buy_the_costlier_mistake(
    registry, tmp_path
):
    """Matrix: *two candidates, one favour*.

    **The two orderings are made to disagree**, which the first version of this
    case did not do: ``b_land`` is the lower id *and* was the longer period, so
    the id tiebreak alone picked the same winner and neutralising the cost term
    left the case green. Here ``b_trip`` carries the years-long wanting while
    ``b_land`` sorts first, so only the costlier-mistake rule can pick
    ``b_trip``.
    """
    seed(
        tmp_path, beliefs=("b_land", "b_trip"), favours=1,
        scales={FARMLAND: Timescale.MONTHS, PASSPORT: Timescale.YEARS},
    )

    # A message that both *retrieves* and *raises* each of them: the loop slug
    # is what the FTS prefix indexes and what the strand key is built from, so
    # one word per wanting does both jobs. A message naming only one of them
    # would leave the other out of the ranked set entirely, and this case would
    # then be about a set of one.
    transport = a_turn(registry, text="farmland passport again please")

    assert [r.data[ABOUT] for r in spends(tmp_path)] == ["b_trip"], (
        "the costlier mistake is the years-long wanting, not the lower id"
    )
    body = sent(transport)
    assert body.count("question[") == 1
    assert "question[b_trip]" in body


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_two_favours_do_not_buy_two_questions_in_one_send(registry, tmp_path):
    """CAP-4 forbids a questionnaire outright, and a *balance* is not what stops
    one: with two favours unspent both beliefs are affordable, and the reply
    still carries one."""
    seed(tmp_path, beliefs=("b_land", "b_trip"), favours=2)

    transport = a_turn(registry, text="farmland passport again please")

    assert sent(transport).count("question[") == 1
    assert len(spends(tmp_path)) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: below the bar / capped / quarantined / topic / nothing to ask
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_gates
@pytest.mark.parametrize("favours", [1, 2, 5, 40], ids=lambda n: f"{n}-favours")
def test_a_days_routine_is_never_bought_at_any_balance(registry, tmp_path, favours):
    """Matrix: *below the bar*. Swept across the balance rather than asserted at
    one value, because a single-balance case would pass with the two gates
    reversed — which is the ordering the whole currency rests on."""
    seed(tmp_path, favours=favours, scales={FARMLAND: Timescale.DAYS})

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_gates
@pytest.mark.ad28
def test_a_main_capped_at_behave_buys_nothing(registry, tmp_path):
    """Matrix: *capped* (AD-28). The cap is applied where licenses are resolved,
    so there is no branch anywhere on this path for aftercare."""
    seed(tmp_path, favours=1)
    asyncio.run(registry.hold_ceiling(
        "vidit", to=License.BEHAVE, t="2026-08-25T00:00Z",
        because="a test standing in for aftercare",
    ))

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_gates
def test_a_quarantined_belief_is_never_bought(registry, tmp_path):
    """Matrix: *quarantined*. A quarantined belief is pinned at `behave`, and a
    question about it is not askable however much has been delivered."""
    seed(tmp_path, favours=1, quarantine={"b_land"})

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_gates
def test_a_message_that_raises_no_topic_is_answered_without_a_question(
    registry, tmp_path
):
    """*"Attach the question to the next conversation that already touches the
    topic. Never ping to ask."*

    The gate is 5b's; what this asserts is that the turn actually runs it,
    against the strands **this message** moved. It is also the case the morning
    surface could never have supplied: a scheduler tick has no message.
    """
    seed(tmp_path, favours=1)

    transport = a_turn(registry, text=OFF_TOPIC)

    assert transport.sent, "an off-topic message is still answered"
    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_gates
def test_a_caller_with_no_conversation_at_all_is_offered_nothing(registry, tmp_path):
    """The ``live=None`` branch, driven rather than asserted about.

    ``None`` means *there is no conversation* — the nightly pass, a scheduler
    tick, anything that is not a turn. Every question is then held, which is the
    correct reading of *never ping to ask* and the reason the morning surface is
    not an asker at all.
    """
    seed(tmp_path, favours=1)
    engine = QuestionEngine(ledger=registry)

    offered = asyncio.run(engine.offer(
        "vidit", beliefs=["b_land"], live=None, now=NOW
    ))

    assert offered is None
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_with_nothing_to_ask_the_turn_is_the_one_it_was_before(registry, tmp_path):
    """Matrix: *nothing to ask*. No `ask`-rung belief at all, so the engine has
    nothing to offer and the reply is byte-identical to the one a runtime with no
    engine produces."""
    seed(tmp_path, favours=1, rung=License.BEHAVE,
         extra=(("b_say", "the mornings have been clear"),))
    seed(tmp_path, main_id="asha", favours=1, rung=License.BEHAVE,
         extra=(("b_say", "the mornings have been clear"),))

    with_engine = a_turn(registry)
    without = a_turn(registry, main_id="asha", engine=False)

    assert sent(with_engine) == sent(without)
    assert spends(tmp_path) == []


# ═════════════════════════════════════════════════════════════════════════════
# matrix: bought but unrendered — no line, no spend
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_a_belief_the_ladder_raised_above_ask_is_never_paid_for(
    registry, tmp_path
):
    """Matrix: *bought but unrendered*, first half. **A defect, reproduced.**

    ``may_be_raised`` permits `ask` **or above**, so an `assert`-rung belief
    passes every gate — and the builder emits a ``Question`` only at exactly
    `ask`, because a belief Half may *state* belongs in the content channel. The
    first build spent the favour anyway and wrote an ``asked`` record for a
    question nobody was asked, which then suppressed the real one for one of the
    wanting's own periods.
    """
    seed(tmp_path, favours=1, rung=License.ASSERT)

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert spends(tmp_path) == [], "a phantom ask was recorded"
    assert balance_of(tmp_path).spent == 0


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_a_belief_whose_topic_echoes_its_claim_is_never_paid_for(
    registry, tmp_path
):
    """Matrix: *bought but unrendered*, second half.

    AD-18's drop rule: a topic that echoes the belief's own claim kills the whole
    item rather than being edited out of it, so an `ask`-rung belief that passes
    every gate can still produce no line. No line, no spend.
    """
    seed(tmp_path, favours=1)
    with Store(tmp_path / "vidit", prefix=build_prefix) as store:
        # The claim now contains its own topic word, so ``_topics`` drops the
        # whole belief — through the ladder, so no license field is written here.
        store.record(Op.ASSERT, "b_land", "2026-08-02T00:00Z",
                     claim="the farmland is still unwalked")

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_the_question_line_is_the_one_signal_that_a_question_was_built():
    """``question_line`` is what *"no line, no spend"* is measured with, and it
    is empty in exactly the two ways a bought belief fails to become one."""
    assert question_line(None) == ""
    assert question_line(Context(now=NOW)) == ""
    carried = Context(
        now=NOW, question=Question(id="b_1", topics=(Topic(kind="loop", name="x"),))
    )
    assert question_line(carried) == "question[b_1] loop: x"
    assert question_line(carried) in carried.render()


# ═════════════════════════════════════════════════════════════════════════════
# matrix: answered / ignored inside the period / ignored a period later
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_a_question_the_main_replied_to_is_never_put_again(registry, tmp_path):
    """Matrix: *answered*. Recognized from the log — an ``asked`` record
    followed, **inside its own window**, by an inbound stated belief."""
    seed(tmp_path, favours=2,
         asks=(("b_land", ago(400)),), replies=(ago(399.5),))

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert len(spends(tmp_path)) == 1, "the old spend only; nothing new"


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_a_question_ignored_inside_its_wantings_period_is_not_put_again(
    registry, tmp_path
):
    """Matrix: *ignored, inside the period*. Farmland moves in years, so a
    question put a month ago is nowhere near its own period — and a build with a
    single global fourteen-day cooldown would ask again here."""
    seed(tmp_path, favours=2, asks=(("b_land", ago(30)),))

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert len(spends(tmp_path)) == 1
    assert balance_of(tmp_path).spent == 1, "nothing further was spent"


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_a_question_ignored_a_full_period_later_may_be_put_again_for_a_favour(
    registry, tmp_path
):
    """Matrix: *ignored, a period later*. One of the wanting's **own** periods —
    a year for farmland — and it costs a second favour."""
    seed(tmp_path, favours=2,
         asks=(("b_land", ago(PERIOD_DAYS[Timescale.YEARS] + 1)),))

    transport = a_turn(registry)

    assert "question[b_land]" in sent(transport)
    assert [r.data[ABOUT] for r in spends(tmp_path)] == ["b_land", "b_land"]
    assert balance_of(tmp_path).spent == 2


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_an_unrelated_message_days_later_does_not_retire_the_question(
    registry, tmp_path
):
    """Matrix: *answered by an unrelated reply*. **A defect, reproduced.**

    The first build marked *every* outstanding question answered on the first
    inbound message, with no time bound at all — so for a main who writes daily,
    the next message on any subject closed every open question for ever. That is
    *"never ask twice, whatever happened"*, which this module's own docstring
    says story 5b was right to refuse, arriving through the back door.

    Here the question was put a year and a day ago and the main wrote about
    something else a week later. The question is *ignored*, not answered, so a
    period having passed it may be put again.
    """
    seed(
        tmp_path, favours=2,
        asks=(("b_land", ago(PERIOD_DAYS[Timescale.YEARS] + 1)),),
        replies=(ago(PERIOD_DAYS[Timescale.YEARS] - 6),),
    )

    transport = a_turn(registry)

    assert "question[b_land]" in sent(transport), (
        "an unrelated message retired a question it could not have answered"
    )
    assert len(spends(tmp_path)) == 2


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
@pytest.mark.parametrize("past", [False, True], ids=["at-the-boundary", "past-it"])
@pytest.mark.parametrize("scale", list(Timescale), ids=[str(s) for s in Timescale])
def test_the_re_ask_bound_is_each_wantings_own_period_end_to_end(
    registry, tmp_path, scale, past
):
    """The sweep, driven through the whole product rather than through the pure
    function: **each wanting measured at its own boundary and one day past it.**

    Eight runs, four different boundaries — one day, one week, one month, one
    year — so a build holding every wanting to one shared cadence answers wrongly
    for three of the four and fails by name here.

    **A single interval was not enough, and this case is the second version.**
    The first swept thirty-one days across all four scales, which happens to give
    the same answer as gbrain's fourteen-day cooldown at every scale but one: the
    mutation was caught by exactly one parameter, and deleting that one parameter
    would have left the rule unguarded while the sweep still looked like a sweep.

    A days-routine is below the stakes bar whatever the interval, so it is never
    asked at all; that is asserted here rather than excused, because *"never
    bought"* and *"not bought yet"* are different answers.
    """
    period = PERIOD_DAYS[scale]
    seed(tmp_path, favours=2, scales={FARMLAND: scale},
         asks=(("b_land", ago(period + (1 if past else 0))),))

    a_turn(registry)

    above_the_bar = period > PERIOD_DAYS[Timescale.DAYS]
    expected = 2 if (past and above_the_bar) else 1
    assert len(spends(tmp_path)) == expected, (
        f"a {scale} wanting asked {period + past} days ago"
    )


# ═════════════════════════════════════════════════════════════════════════════
# matrix: crisis / a refused spend / a send that fails
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_gates
@pytest.mark.cap12
def test_a_main_in_crisis_is_asked_nothing(registry, tmp_path):
    """The mode suspends Half's ordinary behaviour entirely (CAP-12), and the
    currency is void inside it. The crisis gate answers the turn before the
    pipeline is reached at all, so no offer is even made."""
    seed(tmp_path, favours=1)
    asyncio.run(registry.suspend_for_crisis(
        "vidit", t="2026-08-31T00:00Z", tier="disclosure", score=2
    ))

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_spend_the_gates_refuse_takes_the_question_out_of_the_reply(
    registry, tmp_path
):
    """**The rule the whole story is: no question without a favour spent.**

    The offer passes every gate; the spend, re-run against a view read at the
    moment of spending, does not. What must then reach the main is the reply
    *without* the question — not the text that was composed while the purchase
    still looked affordable.

    This case exists because a mutation escaped the suite once: deleting the
    fallback left every other case green while a refused spend still put the
    question on the wire.
    """
    seed(tmp_path, favours=1)

    class Refusing:
        """Offers honestly and cannot pay. The two halves of a stale purchase."""

        def __init__(self, inner):
            self.inner = inner
            self.attempts = 0

        async def offer(self, main_id, **kwargs):
            found = await self.inner.offer(main_id, **kwargs)
            assert found is not None, "the fixture must offer something to lose"
            return found

        async def buy(self, main_id, **kwargs):
            self.attempts += 1
            return Purchase(outcome=ASK_UNAFFORDABLE)

    engine = Refusing(QuestionEngine(ledger=registry))
    transport = _turn_with(registry, engine)

    assert engine.attempts == 1, "the spend must have been attempted"
    assert transport.sent, "the main is still owed an answer"
    assert "question[" not in sent(transport), (
        "a question reached the main that no favour paid for"
    )
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_gates
def test_a_quarantine_landing_between_the_offer_and_the_spend_refuses(
    registry, tmp_path
):
    """The same rule through the real gates rather than a stub.

    The subject is quarantined between the offer and the spend, so
    ``ActorRegistry.note_ask`` refuses under the main's own mutex — the window
    story 5b's review found open — and the reply goes out without the question.
    """
    seed(tmp_path, favours=1)

    class Quarantining:
        def __init__(self, inner):
            self.inner = inner

        async def offer(self, main_id, **kwargs):
            found = await self.inner.offer(main_id, **kwargs)
            assert found is not None
            async with registry.acquire(main_id) as actor:
                record = actor.store.state().beliefs["b_land"]
                candidate = ladder.quarantine_candidate(record, reason="asked")
                actor.store.record(
                    Op.ASSERT, "b_land", "2026-09-01T11:00:00Z",
                    **ladder.quarantine(record, candidate=candidate,
                                        answered=True),
                )
            return found

        async def buy(self, main_id, **kwargs):
            return await self.inner.buy(main_id, **kwargs)

    transport = _turn_with(registry, Quarantining(QuestionEngine(ledger=registry)))

    assert transport.sent
    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_favour
def test_a_send_that_fails_after_the_spend_still_costs_the_favour(
    registry, tmp_path
):
    """Matrix: *send fails after the spend*.

    The asymmetry story 10 accepted and 5b inherited, asserted rather than
    repaired: the favour is spent, the send fails, nothing is queued. The design
    note says plainly not to fix it here and not to let a test assert the
    opposite.
    """
    seed(tmp_path, favours=1)
    transport = FakeTransport(
        [msg(text=ON_TOPIC, message_id="m1", chat_id="123", date=int(NOON))],
        fail=SendFailed("the platform said no", retryable=False),
    )

    a_turn(registry, transport=transport)

    assert transport.sent == []
    assert len(spends(tmp_path)) == 1, "the favour was spent and stays spent"


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_an_engine_that_raises_costs_the_question_and_never_the_reply(
    registry, tmp_path
):
    """**The fail-open handler, driven.** Both handlers on this path were argued
    at length in prose and run by no test, so neutralising either flipped a
    working turn to silence with the suite still green.

    The main asked something and is owed an answer; a bug in the question path
    must cost the question and nothing else.
    """
    seed(tmp_path, favours=1)

    class Broken:
        async def offer(self, main_id, **kwargs):
            raise RuntimeError("the engine is broken")

        async def buy(self, main_id, **kwargs):  # pragma: no cover - never reached
            raise AssertionError("nothing may be bought after a failed offer")

    transport = _turn_with(registry, Broken())

    assert transport.sent, "a broken engine cost the main their reply"
    assert "question[" not in sent(transport)
    assert spends(tmp_path) == []


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_a_spend_that_raises_costs_the_question_and_never_the_reply(
    registry, tmp_path
):
    """The second handler, inside ``QuestionEngine.buy`` — driven through the
    real engine against a ledger whose spend raises, so the refusal is the
    engine's own and not the runtime's outer net."""
    seed(tmp_path, favours=1)

    class Exploding:
        """The real registry, with one door that raises."""

        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        async def note_ask(self, main_id, **kwargs):
            raise RuntimeError("the log is on fire")

    engine = QuestionEngine(ledger=Exploding(registry))
    purchase = asyncio.run(engine.buy(
        "vidit", t=NOW,
        ask=asyncio.run(QuestionEngine(ledger=registry).offer(
            "vidit", beliefs=["b_land"], live=_live(registry), now=NOW
        )),
        live=_live(registry),
    ))

    assert purchase.spent is False
    assert purchase.outcome != NOTHING_OFFERED, "an ask was offered and refused"
    assert spends(tmp_path) == []


def _live(registry, main_id="vidit"):
    """The strands a real message would have moved, through the real matcher."""
    from half.retrieval.strands import Strands, known_strands

    async def observe():
        async with registry.acquire(main_id) as actor:
            state = actor.store.state()
            live = Strands()
            live.observe(ON_TOPIC, known_strands(state.beliefs.values(), state.loops))
            return live

    return asyncio.run(observe())


def _turn_with(registry, engine, *, main_id="vidit", text=ON_TOPIC):
    """One real turn against a runtime holding ``engine``.

    ``Runtime`` is a slots dataclass, so the double is passed at construction
    rather than written in afterwards.
    """
    transport = FakeTransport(
        [msg(text=text, message_id="m1", chat_id="123", date=int(NOON))]
    )
    channel = TelegramChannel(transport=transport, mains={"123": main_id})
    asyncio.run(
        Runtime(channel=channel, registry=registry, questions=engine).run()
    )
    return transport


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the belief goes away / replay / nothing durable
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_a_question_whose_belief_was_expunged_leaves_no_orphan(registry, tmp_path):
    """Matrix: *the belief goes away*. The fold already removes the belief, so
    there is no second place to remember the question — and nothing is asked
    about something that is not there any more."""
    seed(tmp_path, favours=2, asks=(("b_land", ago(400)),))
    with Store(tmp_path / "vidit", prefix=build_prefix) as store:
        store.expunge("b_land", t="2026-08-31T00:00Z")

    transport = a_turn(registry)

    assert "question[" not in sent(transport)
    assert len(spends(tmp_path)) == 1
    with Store(tmp_path / "vidit") as store:
        assert "b_land" not in store.state().beliefs


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_the_balance_and_the_answer_state_survive_a_rebuild(registry, tmp_path):
    """Matrix: *replay*. Both quantities are folded from the log, so discarding
    the derived view changes neither — which is what a stored counter would also
    pass, and why the structural case in ``tests/test_questions.py`` exists as
    well."""
    seed(tmp_path, favours=1)
    a_turn(registry)

    before = balance_of(tmp_path)
    view_before = asyncio.run(registry.question_view("vidit"))
    registry.close()
    (tmp_path / "vidit" / "half.sqlite3").unlink(missing_ok=True)

    again = ActorRegistry(tmp_path)
    try:
        assert balance_of(tmp_path) == before
        assert asyncio.run(again.question_view("vidit")).answers == view_before.answers
    finally:
        again.close()


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_nothing_a_question_says_becomes_durable(registry, tmp_path):
    """Matrix: *question text* (AD-22).

    A spend carries two opaque ids and nothing else — asserted against the
    record's own allowlist rather than against a list written here, so a field
    added to the op is covered on the day it is written.
    """
    seed(tmp_path, favours=1)
    a_turn(registry)

    assert spends(tmp_path), "the fixture asked nothing, so this asserts nothing"
    for record in spends(tmp_path):
        carried = set(record.data) - {"t", "op", "id", "v"}
        assert carried == set(ASKED_FIELDS)
        assert record.data[QUESTION] == question_id(record.data[ABOUT])


# ═════════════════════════════════════════════════════════════════════════════
# the three load-bearing rules, structurally
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.ad18
def test_a_context_has_room_for_exactly_one_question():
    """**One question per send, asserted structurally.**

    Not counted off a fixture — which passes for whatever the fixture happens to
    contain — but read off the *resolved* type: the field is an
    ``Optional[Question]``, so a second question has nowhere to go, and the
    builder's own parameter is a single id, so two cannot be handed in.

    ``get_type_hints`` rather than the raw annotation string, which is the
    correction review forced: ``Optional[Question]`` and ``Question | None`` are
    the same type and a string comparison called one of them a regression.
    """
    hints = typing.get_type_hints(Context)
    assert hints["question"] == typing.Optional[Question]
    assert "question" in CHANNELS and "questions" not in CHANNELS

    parameter = inspect.signature(build_context).parameters["bought"]
    assert typing.get_type_hints(build_context)["bought"] == typing.Optional[str]
    assert parameter.default is None, "empty is fail-closed, so it may default"


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.ad18
def test_a_second_question_is_refused_rather_than_appended_or_substituted():
    """The bypass case for the type: a ranked set naming the bought belief twice
    is the ordinary way a second ``Question`` reaches ``plus``."""
    first = Question(id="b_1", topics=(Topic(kind="loop", name="first"),))
    second = Question(id="b_1", topics=(Topic(kind="loop", name="second"),))
    context = Context(now=NOW).plus(first).plus(second)

    assert context.question is first
    assert len(context) == 1
    assert context.render().count("question[") == 1


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.ad18
@pytest.mark.parametrize("size", [1, 2, 3, 8], ids=lambda n: f"{n}-beliefs")
def test_no_ranked_set_of_any_size_produces_two_questions(size):
    """Swept over set size, all `ask`-rung, all sharing the bought id.

    **Exactly one, not at most one.** The first version asserted ``<= 1``, which
    holds at zero — so the sweep could not tell *"never a questionnaire"* from
    *"never a question"*, and a builder that had stopped emitting them entirely
    passed every parameter.
    """
    ranked = [
        RankedBelief(
            id="b_1", claim=f"claim number {index}", prefix="", bm25=None,
            belief={"id": "b_1", "license": "ask", "loop": FARMLAND,
                    "topics": ["farmland"], "claim": f"claim number {index}"},
        )
        for index in range(size)
    ]
    context = build_context(ranked, now=NOW, ceiling=None, bought="b_1")

    assert context.question is not None, "the sweep must actually build one"
    assert context.render().count("question[") == 1


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.ad18
@pytest.mark.ad28
@pytest.mark.parametrize(
    "bought", [None, "", "b_1", "b_other"],
    ids=["nothing", "empty", "this-one", "another-one"],
)
@pytest.mark.parametrize("cap", [None, *RUNGS], ids=["uncapped", *map(str, RUNGS)])
@pytest.mark.parametrize("rung", list(RUNGS), ids=[str(r) for r in RUNGS])
def test_the_question_channel_is_exactly_the_rung_and_the_purchase(rung, cap, bought):
    """**The channel is bought by what the builder is handed** — as a truth
    table, against an expectation written out here rather than read from the
    code.

    This replaced an AST scan that collected the names inside any enclosing
    ``if`` test, which ``if not bought: return Question(...)`` satisfied while
    doing the exact opposite, ``if bought or True:`` satisfied trivially, and a
    ternary or a ``match`` would have made false-fail. A truth table cannot be
    satisfied by an inverted guard, by a different syntax, or by a predicate that
    agrees with a wrong implementation, because the expectation is independent of
    both.

    Both halves are pinned: the shipped predicate ``bought_question`` must agree
    with the expectation, **and** the context the builder actually returns must
    agree with the predicate. A mutation to either one alone breaks this; a
    mutation to both breaks it against the expectation.
    """
    ceiling = None if cap is None else Ceiling(cap)
    belief = {"id": "b_1", "claim": "a claim", "loop": FARMLAND,
              "topics": ["farmland"], "license": str(rung),
              "support": ["s_1"], "known_to_main": True}
    reached = resolve(belief, ceiling=ceiling)
    expected = reached is License.ASK and bought == "b_1"

    assert bought_question("b_1", reached, bought=bought) is expected
    context = build_context(
        [RankedBelief(id="b_1", claim="a claim", prefix="", bm25=None,
                      belief=belief)],
        now=NOW, ceiling=ceiling, bought=bought,
    )
    assert (context.question is not None) is expected
    assert (question_line(context) != "") is expected


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.ad18
def test_exactly_one_expression_in_the_tree_can_construct_a_question():
    """The structural half, and it is about *where* rather than about a branch.

    A second construction site is how a channel acquires a second rule — the
    shape story 6c's no-authoring gate had to be written against — and it is
    checkable without guessing at syntax: count the constructions.
    """
    sites = sorted(
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for path in (ROOT / "half").rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Question"
    )
    assert len(sites) == 1, sites
    assert sites[0].startswith("half/context/build.py:")


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.ad18
def test_the_construction_scan_catches_a_second_site(tmp_path):
    """The bypass case. A guard nobody has tried to defeat rests on nothing."""
    second = tmp_path / "second.py"
    second.write_text(
        "def sneak(candidate):\n"
        "    return Question(id=candidate.id, topics=())\n",
        encoding="utf-8",
    )
    found = [
        node for node in ast.walk(ast.parse(second.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Question"
    ]
    assert len(found) == 1


# ═════════════════════════════════════════════════════════════════════════════
# where the question may and may not be asked
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap8_silence
def test_the_morning_surface_cannot_reach_the_question_package_at_all():
    """Matrix: *the morning never asks*. **Structural, and it has to be.**

    A question is attached to a conversation that already touches its topic, and
    a scheduler tick is not a conversation: the strands 5b's gate reads exist on
    a turn and nowhere else. The first build gated on them and delivered here
    anyway, and every green case manufactured the strands immediately before the
    run. So the rule is not *"the surface does not call buy today"* — it is that
    the surface **cannot**, because nothing under ``half/surface`` can resolve an
    import into ``half.questions`` or ``half.trust``.
    """
    for path in sorted((ROOT / "half" / "surface").rglob("*.py")):
        offending = reaches(path, ("half.questions", "half.trust"))
        assert not offending, (
            f"{path.name} can reach the asking path: {offending} — the morning "
            f"surface is not an asker"
        )


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_the_import_rule_catches_the_line_it_forbids(tmp_path):
    """The bypass case, written in the spelling that walked past story 11's own
    first denylist: a package-attribute import naming neither module."""
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        "from half import questions as _asker\n", encoding="utf-8"
    )
    assert reaches(bypass, ("half.questions", "half.trust")) == ["half.questions"]
    assert "half.questions" in resolved_imports(bypass)


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap8_silence
def test_a_morning_asks_nothing_and_spends_nothing(registry, tmp_path):
    """The behavioural half. A full morning, with an affordable question sitting
    in the log and its topic freshly raised, writes no ``asked`` record.

    The strands are moved first *on purpose*: this is the exact condition the
    first build's suite manufactured to make the morning ask, and it must now
    change nothing.
    """
    from half.surface.choose import Candidate
    from half.surface.morning import MorningSurface

    seed(tmp_path, favours=1)
    a_turn(registry)  # a real turn, which raises the topic and asks once
    before = len(spends(tmp_path))

    class Now:
        epoch = NOON + DAY
        stamp = stamp(NOON + DAY)

    class Channel:
        name = "fake"

        def __init__(self):
            self.sent = []

        def capability_query(self, main_id):
            from half.channel.port import Reachability

            return Reachability.OPEN

        async def send(self, main_id, text):
            from half.channel.port import SendResult

            self.sent.append((main_id, text))
            return SendResult(external_id="mid-1", parts=1)

    channel = Channel()
    surface = MorningSurface(ledger=registry, channel=channel)
    assert not hasattr(surface, "questions"), "the surface has a field for one"
    asyncio.run(surface.surface(
        "vidit", now=Now(),
        candidates=[Candidate(origin=ORIGIN, entries=("b_land",))],
    ))

    assert len(spends(tmp_path)) == before, "the morning surface asked"
    assert all("question[" not in text for _, text in channel.sent)


# ═════════════════════════════════════════════════════════════════════════════
# worldwide: no question text anywhere on the path to the wire
# ═════════════════════════════════════════════════════════════════════════════

#: Every module that builds something a main reads on the question path. It is
#: **not** just ``half/questions``, which was the first version's whole scope and
#: which by design holds no text at all: the words that reach the wire are
#: assembled in ``half.context.channels`` and admitted in ``half.context.build``,
#: and the reply they are attached to is composed in ``half.actor.runtime``.
WIRE_MODULES = (
    "half/questions",
    "half/context/channels.py",
    "half/context/build.py",
)


def _phrases(tree: ast.AST) -> list[str]:
    """Every string constant in ``tree`` that reads as a phrase.

    Docstrings are excluded — they are for the reader — and everything else is
    read: a constant, a default, an f-string part, a dict value. What is looked
    for is **two word characters with whitespace between them**, because a
    question in any language is words with something between them, while every
    legitimate string on this path is one identifier, one hyphenated reason
    constant, or one separator (``"; "``, ``": "``).

    ``\\w`` is Unicode-aware, so this reads a Devanagari or Arabic template
    exactly as it reads an English one — which is the point: a denylist of
    English words would only ever catch the language somebody thought of.
    """
    import re

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and re.search(r"\w\s+\w", node.value)
    ]


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_no_literal_question_string_exists_anywhere_on_the_question_path():
    """**Half ships worldwide.** A hand-written English question is the
    objection ``half.context.channels`` already records, and it would be
    invisible: a template reads like a feature.

    Scanned as a *property* — no string constant outside a docstring is a phrase
    — rather than as a list of forbidden words.
    """
    offenders: dict[str, list[str]] = {}
    for name in WIRE_MODULES:
        target = ROOT / name
        paths = sorted(target.rglob("*.py")) if target.is_dir() else [target]
        for path in paths:
            found = _phrases(ast.parse(path.read_text(encoding="utf-8")))
            if found:
                offenders[str(path.relative_to(ROOT))] = found
    assert offenders == {}, f"text on the question path: {offenders}"


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_the_worldwide_scan_catches_the_template_it_forbids():
    """The bypass case: the one line this scan exists to refuse, in two scripts,
    beside the separators it must keep tolerating."""
    mutated = ast.parse(
        '"""A docstring with spaces, which is fine."""\n'
        'SEPARATOR = "; "\n'
        'LABEL = "question"\n'
        'PROMPT = "Have you walked the plot lately?"\n'
        'हिंदी = "क्या आपने खेत देखा"\n'
    )
    assert _phrases(mutated) == [
        "Have you walked the plot lately?", "क्या आपने खेत देखा"
    ]


@pytest.mark.cap4
@pytest.mark.cap4_bought
def test_the_reply_carries_the_question_only_as_the_builders_own_line(
    registry, tmp_path
):
    """The wire text is the builder's single serialization with the reply in
    front of it — never a sentence composed here. Asserted on the bytes the
    transport actually carried."""
    seed(tmp_path, favours=1)

    transport = a_turn(registry)

    body = sent(transport)
    plain = respond_text(tmp_path)
    assert body == f"{plain}\nquestion[b_land] loop: buy-farmland; topic: farmland"


def respond_text(root, main_id="vidit"):
    """What the reply would have been with no question attached."""
    from half.retrieval.rank import Retriever

    class _Inbound:
        text = ON_TOPIC
        t = NOW

    with Store(root / main_id, prefix=build_prefix) as store:
        ranked = Retriever(store=store).retrieve(ON_TOPIC, now=NOW)
        return respond(_Inbound(), ranked, ceiling=None)


# ═════════════════════════════════════════════════════════════════════════════
# the doors
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_structure
def test_the_trust_door_still_has_exactly_the_three_methods_story_5b_reviewed():
    """The engine extends ``TrustLedger`` rather than editing it, and *"any
    change to 5b's door"* is an Ask-First. So the two protocols are compared."""
    def declared(protocol):
        return {
            name for name in vars(protocol)
            if not name.startswith("_") and callable(vars(protocol)[name])
        }

    assert declared(TrustLedger) == {"crisis_open", "trust_view", "note_ask"}
    assert declared(QuestionLedger) == {"question_view"}
    assert issubclass(QuestionLedger, TrustLedger)


@pytest.mark.cap4
@pytest.mark.cap4_bought
@pytest.mark.cap4_structure
def test_the_registry_satisfies_the_engines_door_signature_for_signature():
    """A structural ``Protocol`` check compares *names* only, so a keyword-only
    parameter renamed on one side drifts the two apart with every behavioural
    case still green — story 5b's own finding, applied to the door it added."""
    expected = inspect.signature(QuestionLedger.question_view)
    actual = inspect.signature(ActorRegistry.question_view)
    assert list(actual.parameters) == list(expected.parameters)
