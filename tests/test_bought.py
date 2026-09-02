"""CAP-4 story 11: the questions channel is bought, or it is empty.

``tests/test_unasked.py`` proves the gates decide correctly. This file proves
**something calls them** — which is the whole of story 11, because story 5b
shipped the currency, the gates and the spend with no production caller at all,
and an `ask`-rung belief reached the wire as a question line with no favour
spent.

Three rules carry the story and each is asserted in the strongest form
available:

* **The channel is bought by what ``build`` is handed, never by what it
  filters.** A builder that reads the rung and decides for itself which beliefs
  deserve a question can be made to decide wrongly; one that can only emit what
  it was handed cannot. Asserted behaviourally (an unbought `ask` belief reaches
  no question channel, off the live store and through the real surface) *and*
  structurally (nothing in the builder may construct a ``Question`` outside a
  branch that names the parameter), with a bypass case run against the exact
  mutation the guard forbids.
* **One question per send, ever.** Not counted off a fixture — which passes for
  whatever the fixture happens to contain — but *structural*: the context field
  is a ``Question | None`` and the builder's parameter is a single id, so a
  second question has nowhere to go. Swept over ranked sets of every size, all
  `ask`-rung, all named as bought.
* **The re-ask bound is the wanting's own period.** The arithmetic lives in
  ``tests/test_questions.py``; what is here is the same bound driven end to end
  through the real registry, the real store and the real surface — asked, then
  ignored inside the period, then asked again a period later at the cost of a
  second favour.

**Nothing here waits for real time and nothing here reads a clock**: every
instant is chosen by the test and passed in, which is the design under test
(AD-30). Nothing here reaches a network or a model.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.channel.port import Reachability, SendResult
from half.civil import DAY
from half.context.build import build as build_context
from half.context.channels import CHANNELS, Context, Question, Topic
from half.errors import ChannelError
from half.governance import ladder
from half.governance.ladder import RUNGS, Ceiling, License, height, permitted
from half.loops import ledger as loops
from half.loops.timescale import PERIOD_DAYS, Timescale
from half.questions.engine import Purchase, QuestionEngine
from half.questions.mint import question_id
from half.retrieval.port import Candidate as RankedBelief
from half.retrieval.strands import known_strands
from half.schedule.clock import stamp
from half.store.ops import TOUCH_TENSION, Op
from half.store.records import ABOUT, ASKED_FIELDS, QUESTION, LEDGER, STATED
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.choose import Candidate
from half.surface.morning import (
    NOTHING_MAY_BE_SAID,
    NOTHING_TO_SAY,
    SPEAKS_AT,
    MorningSurface,
    Silence,
    Surfaced,
    speech,
)
from half.surface.touch import Origin
from half.trust.balance import balance
from half.trust.unasked import ASK_UNAFFORDABLE

pytestmark = [pytest.mark.cap4, pytest.mark.cap4_bought]

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the instant every surface case in this tree builds
#: from.
NOON = 1_788_264_000.0
NOW = stamp(NOON)
TODAY = "2026-09-01"

ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")

#: Two wantings on **different** timescales, so that *"the costlier mistake"* is
#: a real comparison rather than a tie broken by an id. Farmland moves in years
#: and a passport in months, which is the whole point of reading each wanting's
#: own period.
FARMLAND = "buy-farmland"
PASSPORT = "renew-passport"
SCALES = {FARMLAND: Timescale.YEARS, PASSPORT: Timescale.MONTHS}

#: Claims that share **no word** with their own belief's topics or loop slug.
#: AD-18's drop rule is per belief and word-level — a topic echoing the claim
#: kills the whole directive — so a fixture whose claim says "farmland" would
#: produce an empty context and every case below would pass having asserted
#: nothing about the purchase.
CLAIMS = {
    "b_1": ("has not walked that plot since March", FARMLAND, ["farmland"]),
    "b_2": ("left it until six weeks before flying", PASSPORT, ["travel"]),
}

#: A message that raises both topics, so the topic gate is not what refuses.
ON_TOPIC = "farmland and travel"
OFF_TOPIC = "how was the concert"


class Instant:
    """The ``Now`` the scheduler hands a surface: an epoch and a stamp."""

    def __init__(self, epoch=NOON):
        self.epoch = epoch
        self.stamp = stamp(epoch)


class FakeChannel:
    """The whole ``Channel`` surface a morning needs, so tests stay offline."""

    name = "fake"

    def __init__(self, reach=Reachability.OPEN, fail=None, parts=1):
        self.reach = reach
        self.fail = fail
        self.parts = parts
        self.sent: list[tuple[str, str]] = []

    def capability_query(self, main_id):
        return self.reach

    async def send(self, main_id, text):
        if self.fail is not None:
            raise self.fail
        self.sent.append((main_id, text))
        return SendResult(external_id="mid-1", parts=self.parts)

    def draft_link(self, text, *, to=None):  # pragma: no cover - never used
        raise AssertionError("the morning surface never drafts to a third party")

    async def receive(self):  # pragma: no cover - never used
        raise AssertionError("the morning surface never receives")


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
    beliefs=("b_1",),
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
    *and* says a message was sent, which is the only thing that earns.
    """
    scales = dict(SCALES if scales is None else scales)
    with Store(root / main_id) as store:
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
        store.record(Op.TENSION, "x_1", "2026-08-20T00:00Z",
                     between=["b_1", "b_2"], state="fresh", **ladder.admitted())
        for day in range(favours):
            # Real civil days, spread backwards from the seed month, because a
            # day marker is validated at the append and ``2026-08-45`` is not a
            # date. Sweeping the balance up to forty is what makes the stakes
            # bar's independence from the currency assertable.
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
                         claim="a reply about something", **{LEDGER: STATED},
                         **ladder.admitted())


def talking(registry, main_id="vidit", *, about=ON_TOPIC):
    """Put a live conversation in front of the topic gate.

    Through the real ``Strands`` and the real ``known_strands``, so the gate is
    exercised against the same matcher CAP-1 uses rather than against weights
    written in by hand.
    """

    async def observe():
        async with registry.acquire(main_id) as actor:
            state = actor.store.state()
            actor.strands.observe(
                about, known_strands(state.beliefs.values(), state.loops)
            )

    asyncio.run(observe())


def a_surface(registry, channel, *, engine=True):
    return MorningSurface(
        ledger=registry, channel=channel,
        questions=QuestionEngine(ledger=registry) if engine else None,
    )


def run_morning(
    registry, channel, *, main_id="vidit", entries=("b_1",), now=None, engine=True
):
    candidate = Candidate(origin=ORIGIN, entries=tuple(entries))
    return asyncio.run(
        a_surface(registry, channel, engine=engine).surface(
            main_id, now=now or Instant(), candidates=[candidate]
        )
    )


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


@pytest.mark.cap4_favour
def test_the_ordinary_buy_spends_a_favour_and_puts_one_question_on_the_wire(
    registry, tmp_path
):
    """Matrix: *the ordinary buy*. **The sentence story 5b could not say.**

    One `ask`-rung belief on a live wanting, its topic raised, one delivered
    favour unspent — and the question reaches the main having been paid for,
    through the real registry, the real store and the real channel.
    """
    seed(tmp_path, favours=1)
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert isinstance(outcome, Surfaced)
    assert channel.sent, "the morning went nowhere"
    assert "question[b_1]" in channel.sent[0][1]
    recorded = spends(tmp_path)
    assert [r.data[QUESTION] for r in recorded] == [question_id("b_1")]
    assert [r.data[ABOUT] for r in recorded] == ["b_1"]
    assert balance_of(tmp_path).spent == 1


@pytest.mark.cap4_favour
def test_with_nothing_given_no_question_is_asked_and_nothing_is_spent(
    registry, tmp_path
):
    """Matrix: *no favour*. **The favour rule, on the wire.**

    And it pins the ordering that makes the rule true: the day this morning
    claims is itself a delivered favour, so a surface that offered the question
    *after* claiming would let today's message buy today's question and the rule
    would mean nothing. The offer is made before the claim, against the balance
    the log already holds.
    """
    seed(tmp_path, favours=0)
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert outcome == Silence(NOTHING_MAY_BE_SAID)
    assert channel.sent == []
    assert spends(tmp_path) == []
    assert balance_of(tmp_path).spent == 0


@pytest.mark.cap4_favour
def test_with_nothing_given_the_surface_may_still_send_content(registry, tmp_path):
    """Matrix: *no favour* — the second half. The question is what the favour
    buys; `assert` material still speaks on its own."""
    seed(tmp_path, favours=0, extra=(("b_say", "the mornings have been clear"),))
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel, entries=("b_1", "b_say"))

    assert isinstance(outcome, Surfaced)
    assert "content[b_say]" in channel.sent[0][1]
    assert "question[" not in channel.sent[0][1]
    assert spends(tmp_path) == []


@pytest.mark.cap4_favour
def test_two_affordable_questions_and_one_favour_buy_the_costlier_mistake(
    registry, tmp_path
):
    """Matrix: *two candidates, one favour*.

    Both beliefs pass every gate. One favour buys **one** question, and it is
    the one whose wanting has the longer period — farmland over a passport —
    which is ``Ask.order``'s rule reaching the wire. The entries are handed over
    in the *other* order, so a surface taking whatever came first fails here.
    """
    seed(tmp_path, beliefs=("b_1", "b_2"), favours=1)
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel, entries=("b_2", "b_1"))

    assert isinstance(outcome, Surfaced)
    assert [r.data[ABOUT] for r in spends(tmp_path)] == ["b_1"]
    body = channel.sent[0][1]
    assert body.count("question[") == 1
    assert "question[b_1]" in body


@pytest.mark.cap4_favour
def test_two_favours_do_not_buy_two_questions_in_one_send(registry, tmp_path):
    """CAP-4 forbids a questionnaire outright, and a *balance* is not what stops
    one: with two favours unspent, both beliefs are affordable and the send still
    carries one. See the structural cases for why a second has nowhere to go."""
    seed(tmp_path, beliefs=("b_1", "b_2"), favours=2)
    talking(registry)
    channel = FakeChannel()

    run_morning(registry, channel, entries=("b_1", "b_2"))

    assert channel.sent[0][1].count("question[") == 1
    assert len(spends(tmp_path)) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: below the bar / capped / quarantined / nothing to ask
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_gates
@pytest.mark.parametrize("favours", [1, 2, 5, 40], ids=lambda n: f"{n}-favours")
def test_a_days_routine_is_never_bought_at_any_balance(registry, tmp_path, favours):
    """Matrix: *below the bar*. Swept across the balance rather than asserted at
    one value, because a single-balance case would pass with the two gates
    reversed — which is the ordering the whole currency rests on."""
    seed(tmp_path, favours=favours, scales={FARMLAND: Timescale.DAYS})
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert outcome == Silence(NOTHING_MAY_BE_SAID)
    assert spends(tmp_path) == []


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
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert outcome == Silence(NOTHING_MAY_BE_SAID)
    assert spends(tmp_path) == []


@pytest.mark.cap4_gates
def test_a_quarantined_belief_is_never_bought(registry, tmp_path):
    """Matrix: *quarantined*. A quarantined belief is pinned at `behave`, and a
    question about it is not askable however much has been delivered."""
    seed(tmp_path, favours=1, quarantine={"b_1"})
    talking(registry)
    channel = FakeChannel()

    assert run_morning(registry, channel) == Silence(NOTHING_MAY_BE_SAID)
    assert spends(tmp_path) == []


@pytest.mark.cap4_gates
def test_a_topic_nobody_raised_is_held_rather_than_asked(registry, tmp_path):
    """*"Attach the question to the next conversation that already touches the
    topic. Never ping to ask."* The gate is 5b's; what this asserts is that the
    surface actually runs it, against the main's real live strands."""
    seed(tmp_path, favours=1)
    talking(registry, about=OFF_TOPIC)
    channel = FakeChannel()

    assert run_morning(registry, channel) == Silence(NOTHING_MAY_BE_SAID)
    assert spends(tmp_path) == []


def test_a_main_with_no_conversation_open_is_asked_nothing(registry, tmp_path):
    """A dormant actor has no strands, so nothing is on topic — which is the
    correct reading of *never ping to ask* rather than an omission."""
    seed(tmp_path, favours=1)
    channel = FakeChannel()

    assert registry.live_strands("vidit") is None
    assert run_morning(registry, channel) == Silence(NOTHING_MAY_BE_SAID)
    assert spends(tmp_path) == []


def test_with_nothing_to_ask_the_surface_behaves_as_story_10_leaves_it(
    registry, tmp_path
):
    """Matrix: *nothing to ask*. No `ask`-rung belief at all, so the engine has
    nothing to offer and the morning is exactly the one story 10 shipped."""
    seed(tmp_path, favours=1, rung=License.BEHAVE,
         extra=(("b_say", "the mornings have been clear"),))
    talking(registry)
    channel = FakeChannel()

    with_engine = run_morning(registry, channel, entries=("b_1", "b_say"))
    assert isinstance(with_engine, Surfaced)
    assert spends(tmp_path) == []

    # The same morning without an engine at all produces the same text.
    other = FakeChannel()
    seed(tmp_path, main_id="asha", favours=1, rung=License.BEHAVE,
         extra=(("b_say", "the mornings have been clear"),))
    plain = run_morning(registry, other, main_id="asha",
                        entries=("b_1", "b_say"), engine=False)
    assert isinstance(plain, Surfaced)
    assert plain.text == with_engine.text


def test_a_pass_that_produced_nothing_asks_nothing(registry, tmp_path):
    """The ordinary morning. No candidate means no entries, so nothing is even
    minted — the engine is not consulted and no door is opened."""
    seed(tmp_path, favours=1)
    talking(registry)
    channel = FakeChannel()

    outcome = asyncio.run(
        a_surface(registry, channel).surface("vidit", now=Instant(), candidates=[])
    )
    assert outcome == Silence(NOTHING_TO_SAY)
    assert spends(tmp_path) == []


# ═════════════════════════════════════════════════════════════════════════════
# matrix: answered / ignored inside the period / ignored a period later
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_favour
def test_a_question_the_main_replied_to_is_never_put_again(registry, tmp_path):
    """Matrix: *answered*. Recognized from the log — an ``asked`` record
    followed by an inbound stated belief — with no answered flag anywhere."""
    seed(tmp_path, favours=2,
         asks=(("b_1", ago(400)),), replies=(ago(399),))
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert outcome == Silence(NOTHING_MAY_BE_SAID)
    assert len(spends(tmp_path)) == 1, "the old spend only; nothing new"


@pytest.mark.cap4_favour
def test_a_question_ignored_inside_its_wantings_period_is_not_put_again(
    registry, tmp_path
):
    """Matrix: *ignored, inside the period*. Farmland moves in years, so a
    question put a month ago is nowhere near its own period — and a build with a
    single global fourteen-day cooldown would ask again here."""
    seed(tmp_path, favours=2, asks=(("b_1", ago(30)),))
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert outcome == Silence(NOTHING_MAY_BE_SAID)
    assert len(spends(tmp_path)) == 1
    assert balance_of(tmp_path).spent == 1, "nothing further was spent"


@pytest.mark.cap4_favour
def test_a_question_ignored_a_full_period_later_may_be_put_again_for_a_favour(
    registry, tmp_path
):
    """Matrix: *ignored, a period later*. One of the wanting's **own** periods —
    a year for farmland — and it costs a second favour."""
    seed(tmp_path, favours=2,
         asks=(("b_1", ago(PERIOD_DAYS[Timescale.YEARS] + 1)),))
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert isinstance(outcome, Surfaced)
    assert [r.data[ABOUT] for r in spends(tmp_path)] == ["b_1", "b_1"]
    assert balance_of(tmp_path).spent == 2


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
    the same answer as gbrain's fourteen-day cooldown at every scale but one:
    the mutation was caught by exactly one parameter, and deleting that one
    parameter would have left the rule unguarded while the sweep still looked
    like a sweep. That is defect shape three in this project's own list — a test
    exercising only the shape the implementation happens to handle.

    A days-routine is below the stakes bar whatever the interval, so it is never
    asked at all; that is asserted here rather than excused, because *"never
    bought"* and *"not bought yet"* are different answers.
    """
    period = PERIOD_DAYS[scale]
    seed(tmp_path, favours=2, scales={FARMLAND: scale},
         asks=(("b_1", ago(period + (1 if past else 0))),))
    talking(registry)
    channel = FakeChannel()

    run_morning(registry, channel)

    above_the_bar = period > PERIOD_DAYS[Timescale.DAYS]
    expected = 2 if (past and above_the_bar) else 1
    assert len(spends(tmp_path)) == expected, (
        f"a {scale} wanting asked {period + past} days ago"
    )


# ═════════════════════════════════════════════════════════════════════════════
# matrix: crisis between choice and send / send fails after the spend
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap12
@pytest.mark.cap4_gates
def test_a_crisis_opening_after_the_question_is_chosen_spends_nothing(
    registry, tmp_path
):
    """Matrix: *crisis between choice and send*.

    The mode suspends Half's ordinary behaviour entirely, and the currency is
    void inside it. The claim itself refuses first, so nothing is sent — and the
    favour is not spent either, because the spend sits after the claim.
    """
    seed(tmp_path, favours=1)
    talking(registry)
    channel = FakeChannel()

    class Interleaved:
        """The engine, with the mode opening between the choice and the send.

        A single-threaded suite cannot produce this ordering on its own — the
        whole turn completes before anything else runs — so the window is forced
        open, the way ``tests/test_unasked.py`` forces the concurrency one.
        """

        def __init__(self, inner):
            self.inner = inner

        async def offer(self, main_id, **kwargs):
            found = await self.inner.offer(main_id, **kwargs)
            assert found is not None, "the fixture must offer something to lose"
            await registry.suspend_for_crisis(
                main_id, t="2026-09-01T11:00:00Z", tier="disclosure", score=2
            )
            return found

        async def buy(self, main_id, **kwargs):
            return await self.inner.buy(main_id, **kwargs)

    surface = a_surface(registry, channel)
    object.__setattr__(surface, "questions", Interleaved(surface.questions))
    candidate = Candidate(origin=ORIGIN, entries=("b_1",))
    outcome = asyncio.run(
        surface.surface("vidit", now=Instant(), candidates=[candidate])
    )

    assert isinstance(outcome, Silence)
    assert channel.sent == []
    assert spends(tmp_path) == []


@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_spend_the_gates_refuse_takes_the_question_out_of_the_send(
    registry, tmp_path
):
    """**The rule the whole story is: no question without a favour spent.**

    The offer passes every gate; the spend, re-run against a view read at the
    moment of spending, does not. What must then reach the main is the morning
    *without* the question — not the text that was composed when the purchase
    still looked affordable.

    This case exists because a mutation escaped the suite: deleting the two
    lines that fall back to the unbought text left every other case green while
    a refused spend still put the question on the wire, which is CAP-4's central
    rule broken on the one path that matters. The crisis case does not cover it —
    there the *claim* refuses first, so the send never happens at all.
    """
    seed(tmp_path, favours=1, extra=(("b_say", "the mornings have been clear"),))
    talking(registry)
    channel = FakeChannel()

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

    surface = a_surface(registry, channel)
    engine = Refusing(surface.questions)
    object.__setattr__(surface, "questions", engine)
    outcome = asyncio.run(surface.surface(
        "vidit", now=Instant(),
        candidates=[Candidate(origin=ORIGIN, entries=("b_1", "b_say"))],
    ))

    assert engine.attempts == 1, "the spend must have been attempted"
    assert isinstance(outcome, Surfaced)
    assert "question[" not in channel.sent[0][1], (
        "a question reached the main that no favour paid for"
    )
    assert "content[b_say]" in channel.sent[0][1]
    assert spends(tmp_path) == []


@pytest.mark.cap4_favour
def test_a_refused_spend_with_nothing_else_to_say_sends_nothing_at_all(
    registry, tmp_path
):
    """The same refusal when the question *was* the whole morning.

    The day is already claimed, so it is spent — story 10's asymmetry, which
    this story inherits rather than repairs — and the main is sent nothing
    rather than a question nobody paid for.
    """
    seed(tmp_path, favours=1)
    talking(registry)
    channel = FakeChannel()

    class Refusing:
        def __init__(self, inner):
            self.inner = inner

        async def offer(self, main_id, **kwargs):
            return await self.inner.offer(main_id, **kwargs)

        async def buy(self, main_id, **kwargs):
            return Purchase(outcome=ASK_UNAFFORDABLE)

    surface = a_surface(registry, channel)
    object.__setattr__(surface, "questions", Refusing(surface.questions))
    outcome = asyncio.run(surface.surface(
        "vidit", now=Instant(),
        candidates=[Candidate(origin=ORIGIN, entries=("b_1",))],
    ))

    assert outcome == Silence(NOTHING_MAY_BE_SAID)
    assert channel.sent == []
    assert spends(tmp_path) == []
    with Store(tmp_path / "vidit") as store:
        assert any(
            record.op is Op.TOUCH and record.data.get("local_day") == TODAY
            for record in store.log
        ), "the day was claimed before the spend, so it is spent"


@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_quarantine_landing_between_the_choice_and_the_spend_refuses(
    registry, tmp_path
):
    """The same rule through the real gates rather than a stub.

    The subject is quarantined between the offer and the spend, so
    ``ActorRegistry.note_ask`` refuses under the main's own mutex — the window
    story 5b's review found open — and the morning goes out without the
    question.
    """
    seed(tmp_path, favours=1, extra=(("b_say", "the mornings have been clear"),))
    talking(registry)
    channel = FakeChannel()

    class Quarantining:
        def __init__(self, inner):
            self.inner = inner

        async def offer(self, main_id, **kwargs):
            found = await self.inner.offer(main_id, **kwargs)
            assert found is not None
            async with registry.acquire(main_id) as actor:
                record = actor.store.state().beliefs["b_1"]
                candidate = ladder.quarantine_candidate(record, reason="asked")
                actor.store.record(
                    Op.ASSERT, "b_1", "2026-09-01T11:00:00Z",
                    **ladder.quarantine(record, candidate=candidate,
                                        answered=True),
                )
            return found

        async def buy(self, main_id, **kwargs):
            return await self.inner.buy(main_id, **kwargs)

    surface = a_surface(registry, channel)
    object.__setattr__(surface, "questions", Quarantining(surface.questions))
    outcome = asyncio.run(surface.surface(
        "vidit", now=Instant(),
        candidates=[Candidate(origin=ORIGIN, entries=("b_1", "b_say"))],
    ))

    assert isinstance(outcome, Surfaced)
    assert "question[" not in channel.sent[0][1]
    assert spends(tmp_path) == []


@pytest.mark.cap4_favour
def test_a_send_that_fails_after_the_spend_costs_the_favour_and_the_day(
    registry, tmp_path
):
    """Matrix: *send fails after the spend*.

    The asymmetry story 10 accepted and 5b inherited, asserted rather than
    repaired: the day is claimed, the favour is spent, the send raises, and
    nothing is retried or queued. A retry loop would cost the one-a-day rule,
    which is worth more than one message.
    """
    seed(tmp_path, favours=1)
    talking(registry)
    channel = FakeChannel(fail=ChannelError("the platform said no"))

    outcome = run_morning(registry, channel)

    assert isinstance(outcome, Silence)
    assert channel.sent == []
    assert len(spends(tmp_path)) == 1, "the favour was spent and stays spent"
    with Store(tmp_path / "vidit") as store:
        assert any(
            record.op is Op.TOUCH and record.data.get("local_day") == TODAY
            for record in store.log
        ), "the day was claimed and stays claimed"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the belief goes away / replay / nothing durable
# ═════════════════════════════════════════════════════════════════════════════


def test_a_question_whose_belief_was_expunged_leaves_no_orphan(registry, tmp_path):
    """Matrix: *the belief goes away*. The fold already removes the belief, so
    there is no second place to remember the question — and nothing is asked
    about something that is not there any more."""
    seed(tmp_path, favours=2, asks=(("b_1", ago(400)),))
    with Store(tmp_path / "vidit") as store:
        store.expunge("b_1", t="2026-08-31T00:00Z")
    talking(registry)
    channel = FakeChannel()

    outcome = run_morning(registry, channel)

    assert outcome == Silence(NOTHING_TO_SAY), "a side that is gone is not a side"
    assert len(spends(tmp_path)) == 1
    with Store(tmp_path / "vidit") as store:
        assert "b_1" not in store.state().beliefs


def test_the_balance_and_the_answer_state_survive_a_rebuild(registry, tmp_path):
    """Matrix: *replay*. Both quantities are folded from the log, so discarding
    the derived view changes neither — which is what a stored counter would also
    pass, and why the structural case below exists as well."""
    seed(tmp_path, favours=1)
    talking(registry)
    run_morning(registry, FakeChannel())

    before = balance_of(tmp_path)
    history_before = asyncio.run(registry.ask_history("vidit"))
    registry.close()
    (tmp_path / "vidit" / "half.sqlite3").unlink(missing_ok=True)

    again = ActorRegistry(tmp_path)
    try:
        assert balance_of(tmp_path) == before
        assert asyncio.run(again.ask_history("vidit")) == history_before
    finally:
        again.close()


def test_nothing_a_question_says_becomes_durable(registry, tmp_path):
    """Matrix: *question text* (AD-22).

    A spend carries two opaque ids and nothing else — asserted against the
    record's own allowlist rather than against a list written here, so a field
    added to the op is covered on the day it is written.
    """
    seed(tmp_path, favours=1)
    talking(registry)
    channel = FakeChannel()
    run_morning(registry, channel)

    for record in spends(tmp_path):
        carried = set(record.data) - {"t", "op", "id", "v"}
        assert carried == set(ASKED_FIELDS)
        assert record.data[QUESTION] == question_id(record.data[ABOUT])


# ═════════════════════════════════════════════════════════════════════════════
# the three load-bearing rules, structurally
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.ad18
def test_a_context_has_room_for_exactly_one_question(registry, tmp_path):
    """**One question per send, asserted structurally.**

    Not counted off a fixture — which passes for whatever the fixture happens to
    contain — but read off the type: the field is a ``Question | None``, so a
    second question has nowhere to go, and the builder's own parameter is a
    single id, so two cannot be handed in.
    """
    annotations = Context.__annotations__
    assert annotations["question"] == "Question | None"
    assert "question" in CHANNELS and "questions" not in CHANNELS

    parameter = inspect.signature(build_context).parameters["bought"]
    assert parameter.annotation == "str | None"
    assert parameter.default is None, "empty is fail-closed, so it may default"


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


@pytest.mark.ad18
@pytest.mark.parametrize("size", [1, 2, 3, 8], ids=lambda n: f"{n}-beliefs")
def test_no_ranked_set_of_any_size_produces_two_questions(size):
    """Swept over set size, all `ask`-rung, all sharing the bought id, because
    *"one question"* asserted against a one-element fixture is the shape of test
    story 5b's ``next_ask`` cases had — every one of them a single-element list,
    so ``found[0]`` and ``found[-1]`` were indistinguishable."""
    ranked = [
        RankedBelief(
            id="b_1", claim=f"claim number {index}", prefix="", bm25=None,
            belief={"id": "b_1", "license": "ask", "loop": FARMLAND,
                    "topics": ["farmland"], "claim": f"claim number {index}"},
        )
        for index in range(size)
    ]
    context = build_context(ranked, now=NOW, ceiling=None, bought="b_1")

    assert isinstance(context.question, (Question, type(None)))
    assert context.render().count("question[") <= 1


def _question_calls(tree: ast.AST) -> list[set[str]]:
    """Every ``Question(...)`` construction in ``tree``, with the names its
    enclosing ``if`` tests read.

    Walked with the guard set carried down rather than searched for upward, so
    a construction nested three branches deep is covered by the same rule as one
    at the top of the function.
    """
    found: list[set[str]] = []
    stack: list[tuple[ast.AST, frozenset[str]]] = [(tree, frozenset())]
    while stack:
        node, names = stack.pop()
        if isinstance(node, ast.If):
            names = names | {
                child.id for child in ast.walk(node.test)
                if isinstance(child, ast.Name)
            }
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Question"
        ):
            found.append(set(names))
        for child in ast.iter_child_nodes(node):
            stack.append((child, names))
    return found


@pytest.mark.ad18
def test_the_builder_cannot_construct_a_question_outside_the_bought_branch():
    """**The channel is bought by what the builder is handed.**

    Story 10 shipped an AD-28 violation because ``surface_view`` handed a whole
    ``State`` to a subsystem and the forbidden branch was writable from data
    already in hand; narrowing the input was the only fix that held. The same
    shape applies here, and the behavioural half of this rule is
    ``tests/test_context.py::test_an_unbought_ask_belief_becomes_a_directive_and_is_never_quoted``
    — which a builder that read the rung directly would fail.

    This is the structural half: **the parameter name is read off the shipped
    signature** rather than written down here, so renaming it cannot quietly
    turn this guard into a check on a word nothing uses.
    """
    parameter = "bought"
    assert parameter in inspect.signature(build_context).parameters

    source = (ROOT / "half" / "context" / "build.py").read_text(encoding="utf-8")
    guarded = _question_calls(ast.parse(source))
    assert guarded, "no Question is constructed in the builder at all"
    for names in guarded:
        assert parameter in names, (
            "a Question is constructed outside a branch that reads "
            f"{parameter!r}: the channel would be decided by the rung again"
        )


@pytest.mark.ad18
def test_the_bought_branch_guard_catches_the_mutation_it_forbids():
    """The bypass case. A guard nobody has tried to defeat rests on nothing —
    and this project has shipped four of those. This is the exact mutation the
    case above exists to fail on: the builder deciding from the rung alone."""
    mutated = ast.parse(
        "def _item(candidate, license_, *, bought):\n"
        "    if license_ is License.ASK:\n"
        "        return Question(id=candidate.id, topics=())\n"
        "    return None\n"
    )
    found = _question_calls(mutated)
    assert found == [{"license_", "License"}], found
    assert all("bought" not in names for names in found)


# ═════════════════════════════════════════════════════════════════════════════
# the surface: the rung alone no longer speaks
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
@pytest.mark.parametrize("rung", list(RUNGS), ids=[str(r) for r in RUNGS])
def test_a_surface_speaks_at_ask_exactly_when_a_favour_bought_it(
    registry, tmp_path, rung
):
    """The bought half of ``test_surface``'s ladder equality, swept over every
    rung: at `ask` the surface speaks when — and only when — a favour paid for
    the question, and at every other rung the purchase changes nothing."""
    seed(tmp_path, favours=1, rung=rung)
    talking(registry)
    bought = run_morning(registry, FakeChannel())

    seed(tmp_path, main_id="asha", favours=0, rung=rung)
    talking(registry, "asha")
    unbought = run_morning(registry, FakeChannel(), main_id="asha")

    reached = height(permitted(
        asyncio.run(registry.surface_view("vidit")).beliefs["b_1"], ceiling=None
    ))
    assert isinstance(bought, Surfaced) is (reached >= height(SPEAKS_AT))
    assert isinstance(unbought, Surfaced) is (reached > height(SPEAKS_AT))


@pytest.mark.ad18
def test_speech_reads_the_question_channel_through_the_contexts_own_reader():
    """``speech`` names channels, and the question channel is not a tuple. The
    reader exists so the two cannot drift into two shapes of one field."""
    question = Question(id="b_1", topics=(Topic(kind="loop", name="x"),))
    context = Context(now=NOW, question=question)
    assert context.channel("question") == (question,)
    assert context.channel("directives") == ()
    assert context.channel("now") == (), "a name that is not a channel yields none"
    assert speech(context) == (question,)


# ═════════════════════════════════════════════════════════════════════════════
# worldwide: no question text anywhere on the path
# ═════════════════════════════════════════════════════════════════════════════


def _spaced_literals(tree: ast.AST) -> list[str]:
    """Every string constant in ``tree`` that could be a sentence.

    Docstrings are excluded — they are for the reader — and everything else is
    read: a constant, a default, an f-string part, a dict value. What is looked
    for is a **space**, because a question in any language is words with
    something between them, while every legitimate string in this package is one
    identifier, one hyphenated reason constant, or one prefix.
    """
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
        and " " in node.value
    ]


def test_no_literal_question_string_exists_anywhere_on_the_question_path():
    """**Half ships worldwide.** A hand-written English question is the
    objection ``half.context.channels`` already records, and it would be
    invisible: a template reads like a feature.

    Scanned as a *property* — no string constant outside a docstring carries a
    space — rather than as a list of forbidden words, which would only ever
    catch the language somebody thought of.
    """
    offenders: dict[str, list[str]] = {}
    for path in sorted((ROOT / "half" / "questions").rglob("*.py")):
        found = _spaced_literals(ast.parse(path.read_text(encoding="utf-8")))
        if found:
            offenders[path.name] = found
    assert offenders == {}, f"text on the question path: {offenders}"


def test_the_worldwide_scan_catches_the_template_it_forbids():
    """The bypass case: the one line this scan exists to refuse."""
    mutated = ast.parse(
        '"""A docstring with spaces, which is fine."""\n'
        'PROMPT = "Have you walked the plot lately?"\n'
    )
    assert _spaced_literals(mutated) == ["Have you walked the plot lately?"]


def test_no_model_and_no_network_is_reachable_from_the_questions_package():
    """*"No model call, no generated prose."* Asserted structurally, because
    *"it does not call a model today"* decays the first time somebody reaches
    for one — and a question composed by a model still looks like a question."""
    imported: set[str] = set()
    for path in sorted((ROOT / "half" / "questions").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    offenders = sorted(
        name for name in imported
        if name.startswith(("half.model", "half.channel"))
        or name.split(".")[0] in {"anthropic", "httpx", "socket", "urllib", "http"}
    )
    assert not offenders, f"the questions package can reach outward: {offenders}"


def test_the_trust_door_still_has_exactly_the_three_methods_story_5b_reviewed():
    """The engine extends ``TrustLedger`` rather than editing it, and *"any
    change to 5b's door"* is an Ask-First. So the two protocols are compared."""
    from half.questions.engine import QuestionLedger
    from half.trust.unasked import TrustLedger

    def public(protocol):
        return {
            name for name in vars(protocol)
            if not name.startswith("_") and callable(vars(protocol)[name])
        }

    assert public(TrustLedger) == {"crisis_open", "trust_view", "note_ask"}
    assert public(QuestionLedger) == {"live_strands", "ask_history"}
    assert issubclass(QuestionLedger, TrustLedger)


def test_the_registry_satisfies_the_engines_door_signature_for_signature():
    """A structural ``Protocol`` check compares *names* only, so a keyword-only
    parameter renamed on one side drifts the two apart with every behavioural
    case still green — story 5b's own finding, applied to the doors it added."""
    from half.questions.engine import QuestionLedger

    for name in ("live_strands", "ask_history"):
        expected = inspect.signature(getattr(QuestionLedger, name))
        actual = inspect.signature(getattr(ActorRegistry, name))
        assert list(actual.parameters) == list(expected.parameters), name


def test_the_questions_package_writes_through_no_store_of_its_own():
    """A second path to a main's log is a second writer (AD-1), and the single
    writer is what lets the store skip a journal."""
    imported: set[str] = set()
    for path in sorted((ROOT / "half" / "questions").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
    forbidden = sorted(
        name for name in imported
        if name.startswith(("half.store.store", "half.store.log", "half.actor"))
    )
    assert not forbidden, f"the questions package opens a store: {forbidden}"


def test_pathlib_is_not_reachable_from_the_pure_halves():
    """A guard for the two pure modules that ``tests/test_purity.py`` also
    covers, kept here so a reader of this file sees the boundary."""
    assert pathlib is not None  # the import above is the test's own, not half's
    for name in ("mint", "answered"):
        source = (ROOT / "half" / "questions" / f"{name}.py").read_text("utf-8")
        tree = ast.parse(source)
        roots = {
            alias.name.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert roots <= {"__future__", "collections", "dataclasses", "typing",
                         "half"}, f"{name}.py imports {sorted(roots)}"
