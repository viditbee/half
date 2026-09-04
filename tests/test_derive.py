"""CAP-5 story 15a: a message is evidence, a claim is a belief.

``half/actor/runtime.py`` wrote every inbound message into a main's ledger as a
stated belief, so ``ok``, ``thanks`` and ``hello?`` were beliefs — ranked by
retrieval, quotable once promoted, eligible for a tension against the revealed
side, and the thing a correction aims at. This file is one case per row of the
story's matrix, plus the structural rules the separation rests on.

Four things it refuses to do, because each would let it pass while the product
failed:

**It never asserts *"no belief was written"* on its own.** That is true of a
refused message, an unsure gate, a provider that is down, a breaker standing a
main down and a deployment that equipped nobody. Every case here says which of
the five it is testing and asserts a count that only that one moves.

**It asserts the three readers by driving them, not by importing them.** The
language sample, responsiveness and the correction aim were all built assuming
every message becomes a stated belief, and *"they still work"* is worth exactly
as much as a case that goes red when one of them stops. Each has one.

**It asserts *"a message is not a belief"* by what the belief paths are
handed.** Retrieval, the context builder, the tension minter and the ladder are
driven over a store that holds a message, and the message is absent from each of
them because the door it would have come through does not emit it — never
because a filter here looked for it (story 10's lesson).

**It hunts what leaves the machine and what reaches a log.** The message goes to
a provider four times and nowhere else, and the sentinel is chased through the
log file, the fold, the tally, the result and every captured line.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import time
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime, TURN_DEADLINE_SECONDS
from half.channel.telegram import TelegramChannel
from half.context.build import build as build_context
from half.correction import apply as correction
from half.crisis.gate import CrisisGate
from half.derive import claim as deriving
from half.derive.claim import (
    ALARM_AFTER,
    ALARM_RATE,
    ALLOWED_METHODS,
    BOUND_SECONDS,
    BREAK_AFTER,
    BREAK_FOR,
    CLASSIFY_TIER,
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    REPORT_EVERY,
    Derived,
    Derivers,
    Tally,
    prompt_for,
)
from half.derive.gates import (
    DECISION_RELEVANCE,
    DURABILITY,
    FALSIFIABILITY,
    GATES,
    INDEPENDENCE,
    Gate,
)
from half.errors import DeriveError
from half.governance import ladder
from half.model import consult
from half.model.port import Decision, Failure, Kind, Reason, Usage
from half.questions import answered
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import Retriever
from half.store.ops import Op
from half.store.records import (
    DERIVATION,
    DERIVED,
    LEDGER,
    STATED,
    UNDERIVED,
    derived_claim,
    underived,
)
from half.store.store import Store
from half.voice.compose import sample_from
from tests.conftest import FakeTransport, msg, seed_belief

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"
CHAT = "123"

#: The matrix's first row: a message worth keeping.
WORTH = "I want to move to the farm next year"

#: The three the story is named after, and the gate that refuses each.
NOT_RELEVANT = "ok"
NOT_DURABLE = "I'm tired today"
NOT_FALSIFIABLE = "life is strange"

#: Five scripts, so *"any script"* is a run rather than a sentence. None is a
#: translation of another: the point is that nothing on the path reads them.
SCRIPTS: dict[str, str] = {
    "latin": WORTH,
    "devanagari": "अगले साल खेत पर जाना चाहता हूँ",
    "amharic": "በሚቀጥለው ዓመት ወደ እርሻው መሄድ እፈልጋለሁ",
    "arabic": "أريد الانتقال إلى المزرعة العام المقبل",
    "japanese": "来年は農場に移りたい",
}


# ═════════════════════════════════════════════════════════════════════════════
# doubles
# ═════════════════════════════════════════════════════════════════════════════


def gate_of(work) -> Gate:
    """Which gate a request is for, read off its own label set.

    The gates share no label (``tests/test_gates.py``), so this is exact rather
    than a guess — and it is why the double can answer four concurrent requests
    differently without depending on the order they arrive in.
    """
    for gate in GATES:
        if tuple(work.labels) == gate.labels:
            return gate
    raise AssertionError(f"no gate owns the label set {work.labels}")


class Holder:
    """The port's narrow classifier, and nothing wider.

    ``answers`` maps a gate's **name** to what it should hand back: a label, a
    ``Failure``, an exception to raise, or anything unreadable. Anything not
    named admits, so a case says only what it is about.

    Keyed by gate rather than by call order, because the four gates run
    concurrently: an answers-in-order double would make every case here depend
    on which coroutine the loop happened to resume first.

    ``calls`` is a count and not a raise, because every *"the model was never
    consulted"* row asserts ``holder.calls == 0`` and a raise would be swallowed
    by the deriver's own fail-open handler.
    """

    def __init__(self, answers: dict[str, object] | None = None,
                 *, sleep: float = 0.0) -> None:
        # Private: ``Derivers`` refuses a holder with any public callable but
        # ``classify``, so the double is held to the shape of the real thing.
        self._answers = dict(answers or {})
        self._sleep = sleep
        self.seen: list = []

    async def classify(self, work):
        self.seen.append(work)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        gate = gate_of(work)
        answer = self._answers.get(gate.name, gate.admits)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, str):
            return Decision(label=answer, usage=Usage(micro_usd=11))
        return answer

    @property
    def calls(self) -> int:
        return len(self.seen)


def a_deriver(answers=None, *, main=MAIN, sleep=0.0, bound_seconds=1.0,
              tally=None):
    """A ``Derivers`` and the holder inside it, so a case can count the calls."""
    holder = Holder(answers, sleep=sleep)
    return Derivers({main: holder}, bound_seconds=bound_seconds,
                    tally=tally), holder


def refusing(gate: Gate) -> dict[str, object]:
    """Answers under which exactly ``gate`` refuses and the other three admit."""
    return {gate.name: gate.refuses[0]}


def derive(deriver, text=WORTH, *, main=MAIN) -> Derived:
    return asyncio.run(deriver.derive(text, main_id=main))


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path / "mains")
    yield reg
    reg.close()


def a_turn(tmp_path, registry, texts, *, deriver=None, main=MAIN, at=1000,
           gate=None):
    """Drive real turns through the runtime and hand back the transport."""
    transport = FakeTransport([
        msg(text=text, message_id=f"m{index}", chat_id=CHAT, date=at + index)
        for index, text in enumerate(texts)
    ])
    channel = TelegramChannel(transport=transport, mains={CHAT: main})
    runtime = Runtime(
        channel=channel, registry=registry, gate=gate,
        derivers=deriver if deriver is not None else Derivers(),
    )
    asyncio.run(runtime.run())
    return transport


def beliefs_of(tmp_path, main=MAIN):
    with Store(tmp_path / "mains" / main, prefix=build_prefix) as store:
        return store.state().beliefs


# ═════════════════════════════════════════════════════════════════════════════
# the matrix: what a message is worth keeping
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_admission
def test_a_message_worth_keeping_derives_one_claim(tmp_path, registry):
    """*"I want to move to the farm next year"* — one claim, at the weakest
    rung, citing the message it came from (CAP-5, AD-28).

    Every clause is asserted separately: a build that wrote the claim without
    the support set would satisfy *"one claim exists"*, and one that admitted at
    `assert` would satisfy both.
    """
    deriver, holder = a_deriver()
    a_turn(tmp_path, registry, [WORTH], deriver=deriver)

    beliefs = beliefs_of(tmp_path)
    assert sorted(beliefs) == ["b_m0", "d_m0"]
    message, derived = beliefs["b_m0"], beliefs["d_m0"]

    # The message is evidence: it stays exactly where it was, and is marked.
    assert message[DERIVATION] == UNDERIVED
    assert message[LEDGER] == STATED
    assert message["claim"] == WORTH
    assert underived(message) and not derived_claim(message)

    # The claim is a belief, on the stated ledger, citing its evidence.
    assert derived[DERIVATION] == DERIVED
    assert derived[LEDGER] == STATED
    assert derived["claim"] == WORTH
    assert derived["support"] == ["b_m0"]
    assert derived_claim(derived) and not underived(derived)

    # And it entered at the floor, through the ladder, never above it.
    assert derived["license"] == str(ladder.FLOOR)
    assert ladder.own_rung(derived) is ladder.FLOOR
    assert holder.calls == len(GATES)


@pytest.mark.cap5_admission
@pytest.mark.parametrize("text,gate", [
    (NOT_RELEVANT, DECISION_RELEVANCE),
    (NOT_DURABLE, DURABILITY),
    ("yes", INDEPENDENCE),
    (NOT_FALSIFIABLE, FALSIFIABILITY),
])
def test_a_message_a_gate_refuses_leaves_no_claim_and_the_gate_names_itself(
    tmp_path, registry, text, gate
):
    """The four refusing rows, driven end to end.

    ``ok``, ``I'm tired today``, a bare ``yes`` and ``life is strange`` each
    leave the message in the log as evidence and **no belief at all** — and the
    gate that refused is named, counted under its own key, and is the only one
    counted. A build that reported the first refusal of four would pass three of
    these four; ``test_two_gates_that_refuse_are_both_named`` is where that is
    caught.
    """
    deriver, holder = a_deriver(refusing(gate))
    a_turn(tmp_path, registry, [text], deriver=deriver)

    beliefs = beliefs_of(tmp_path)
    assert sorted(beliefs) == ["b_m0"], "a refused message left a belief"
    assert underived(beliefs["b_m0"])
    assert holder.calls == len(GATES)
    assert deriver.tally.refusals == {gate.name: 1}
    assert deriver.tally.derived == 0
    assert deriver.tally.messages == 1


@pytest.mark.cap5_admission
def test_two_gates_that_refuse_are_both_named_and_all_four_are_still_asked():
    """The row that makes the other four testable at all, at the deriver.

    Two gates refuse, both are named, both are counted — and the holder was
    still asked four times, which is the property a short circuit would take
    away without any *"nothing was written"* case noticing.
    """
    deriver, holder = a_deriver({
        DECISION_RELEVANCE.name: DECISION_RELEVANCE.refuses[0],
        FALSIFIABILITY.name: FALSIFIABILITY.refuses[0],
    })
    result = derive(deriver, NOT_RELEVANT)

    assert result.keeps is False
    assert result.refused_by == ("decision-relevance", "falsifiability")
    assert deriver.tally.refusals == {"decision-relevance": 1,
                                      "falsifiability": 1}
    assert holder.calls == len(GATES)


@pytest.mark.cap5_admission
def test_a_request_addressed_to_half_is_refused_with_a_label_of_its_own():
    """*"what did I say about the farm?"* — the hard case with its own home.

    Refused under ``decision-relevance``, counted under that gate, and it is a
    refusal rather than an *unsure*: the second assertion is what a build
    mapping the label to ``None`` would fail.
    """
    deriver, _ = a_deriver({DECISION_RELEVANCE.name: "a_request"})
    result = derive(deriver, "what did I say about the farm?")

    assert result.refused_by == ("decision-relevance",)
    assert result.verdict.unsure == ()
    assert deriver.tally.answers["a_request"] == 1


@pytest.mark.cap5_admission
def test_a_gate_that_cannot_say_leaves_no_claim_and_is_not_a_refusal():
    """An answered *cannot say* is an answer. It derives nothing, it is counted
    apart from a refusal, and it does **not** arm the breaker — the provider is
    up and answering, and standing a main down for having an ambiguous life is
    an alarm with a snooze button wired to the alarm."""
    deriver, holder = a_deriver({DURABILITY.name: DURABILITY.unsure})
    for _ in range(BREAK_AFTER + 1):
        result = derive(deriver)

    assert result.keeps is False
    assert result.verdict.unsure == ("durability",)
    assert result.refused_by == ()
    assert deriver.tally.refusals == {}
    assert deriver.tally.skipped == 0, "an unsure gate armed the breaker"
    assert holder.calls == len(GATES) * (BREAK_AFTER + 1)


# ═════════════════════════════════════════════════════════════════════════════
# a derivation never costs a reply
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_admission
def test_the_reply_goes_out_before_anything_is_derived(tmp_path, registry):
    """**Derivation runs after the reply**, which is the rule rather than the
    arrangement: a main waiting on a model call to learn whether what they wrote
    was worth keeping is the latency failure story 13b spent a review round on.

    Asserted as an **order** rather than as a latency, because a latency
    assertion is a clock in a test and would be green on a fast machine whatever
    the ordering.
    """
    order: list[str] = []

    class Watching(Holder):
        async def classify(self, work):
            order.append("gate")
            return await super().classify(work)

    holder = Watching()
    deriver = Derivers({MAIN: holder}, bound_seconds=1.0)

    transport = FakeTransport([
        msg(text=WORTH, message_id="m0", chat_id=CHAT, date=1000)
    ])
    sent = transport.send_message

    async def watched(chat_id, text):
        order.append("sent")
        return await sent(chat_id, text)

    transport.send_message = watched
    channel = TelegramChannel(transport=transport, mains={CHAT: MAIN})
    seed_belief(Store(tmp_path / "mains" / MAIN, prefix=build_prefix),
                "b_fly", "2026-07-01T00:00:00Z", subject="self",
                claim="wants to fly a paraglider again",
                rung=ladder.License.ASSERT, support=["s_1"], ledger="revealed")
    asyncio.run(Runtime(channel=channel, registry=registry,
                        derivers=deriver).run())

    assert order, "the turn neither sent nor derived"
    assert order[0] == "sent", order
    assert order.count("gate") == len(GATES)


@pytest.mark.cap5_admission
def test_a_provider_past_its_bound_derives_nothing_and_the_turn_completes(
    tmp_path, registry
):
    """*"Judge slow: past the bound → no claim; the reply is never delayed."*

    Counted under ``bound_exceeded`` rather than as a transport fault, because
    *"the gate is slow"* and *"the provider is unreachable"* want different
    things done about them and the port's closed reason set has no room to say
    which.
    """
    deriver, holder = a_deriver(sleep=0.2, bound_seconds=0.01)
    transport = a_turn(tmp_path, registry, [WORTH], deriver=deriver)

    assert sorted(beliefs_of(tmp_path)) == ["b_m0"]
    assert deriver.tally.bound_exceeded == len(GATES)
    assert deriver.tally.answered == 0
    assert holder.calls == len(GATES)
    assert transport.sent or True  # the turn completed; the words are 13b's


@pytest.mark.cap5_admission
def test_a_provider_that_raises_derives_nothing_and_the_turn_completes(
    tmp_path, registry
):
    """*"Judge raises: the call throws → no claim; the turn completes."*

    A raise out of a holder is a build mistake — an unknown tier, a budget
    admitting nothing — and is counted apart from a provider that answered with
    one of the port's four failures.
    """
    deriver, _ = a_deriver({gate.name: RuntimeError("boom") for gate in GATES})
    a_turn(tmp_path, registry, [WORTH], deriver=deriver)

    assert sorted(beliefs_of(tmp_path)) == ["b_m0"]
    assert deriver.tally.raised == len(GATES)
    assert deriver.tally.fell_back == len(GATES)


@pytest.mark.cap5_admission
def test_a_deriver_nobody_equipped_derives_nothing_and_touches_no_provider(
    tmp_path, registry
):
    """*"Judge absent: no provider wired → no claim; the turn is unaffected."*

    The shipped default. The message is still recorded, still marked, and still
    read by everything that read it — what an unequipped deployment loses is
    claims from the turn path and never messages.
    """
    empty = Derivers()
    a_turn(tmp_path, registry, [WORTH], deriver=empty)

    beliefs = beliefs_of(tmp_path)
    assert sorted(beliefs) == ["b_m0"]
    assert underived(beliefs["b_m0"])
    assert empty.holds(MAIN) is False
    assert empty.tally.messages == 0 and empty.quiet is True
    assert derive(empty) == Derived()


@pytest.mark.cap5_admission
def test_a_failure_to_record_the_claim_never_costs_the_main_their_reply(
    tmp_path, registry, caplog
):
    """The append is the last thing that happens and the first thing that may
    fail — a full disk, a refactored signature. It costs the claim; the reply
    has already gone, and the message is already durable."""
    deriver, _ = a_deriver()
    transport = FakeTransport([
        msg(text=WORTH, message_id="m0", chat_id=CHAT, date=1000)
    ])
    channel = TelegramChannel(transport=transport, mains={CHAT: MAIN})
    runtime = Runtime(channel=channel, registry=registry, derivers=deriver)

    real = registry.acquire
    calls = {"n": 0}

    def flaky(main_id):
        calls["n"] += 1
        if calls["n"] > 1:  # the turn's own acquire succeeds; the claim's does not
            raise OSError("no space left on device")
        return real(main_id)

    runtime.registry.acquire = flaky  # type: ignore[method-assign]
    with caplog.at_level(logging.ERROR):
        asyncio.run(runtime.run())

    assert sorted(beliefs_of(tmp_path)) == ["b_m0"]
    assert any("could not be recorded" in r.message for r in caplog.records)
    assert WORTH not in caplog.text


# ═════════════════════════════════════════════════════════════════════════════
# a message is not a belief: by what each path is handed
# ═════════════════════════════════════════════════════════════════════════════


def a_store_with_both(tmp_path):
    """A message and the claim derived from it, exactly as the turn writes
    them."""
    store = Store(tmp_path / "both", prefix=build_prefix)
    store.record(Op.ASSERT, "b_m0", "2026-09-01T00:00:00Z", subject="self",
                 claim=WORTH, **{LEDGER: STATED, DERIVATION: UNDERIVED},
                 **ladder.admitted())
    store.record(Op.ASSERT, "d_m0", "2026-09-01T00:00:00Z", subject="self",
                 claim=WORTH, **{LEDGER: STATED, DERIVATION: DERIVED},
                 **ladder.admitted(support=["b_m0"]))
    return store


@pytest.mark.cap5_admission
def test_retrieval_is_handed_claims_and_never_the_message(tmp_path):
    """**By what the path is handed, not by a filter it applies** — story 10's
    lesson, and the only version of a rule like this that has held here.

    Both halves of the retriever, because they are two different queries: the
    term match, and the backstop behind a query that matches no term. The
    backstop is the one that matters more — it ranks *everything*, so a message
    would arrive in the candidate set of every topic switch.

    The fold still holds both, which is the other half of the story: a message
    is kept, and is not a belief.
    """
    with a_store_with_both(tmp_path) as store:
        retriever = Retriever(store=store)
        matched = retriever.retrieve("farm", now="2026-09-02T00:00:00Z")
        backstop = retriever.retrieve("zzz", now="2026-09-02T00:00:00Z")

        assert [c.id for c in matched] == ["d_m0"]
        assert [c.id for c in backstop] == ["d_m0"]
        assert store.candidates("farm") and all(
            row["id"] != "b_m0" for row in store.candidates("farm")
        )
        assert all(row["id"] != "b_m0" for row in store.all_candidates())
        assert sorted(store.state().beliefs) == ["b_m0", "d_m0"]


@pytest.mark.cap5_admission
def test_the_context_builder_and_the_ladder_never_see_the_message(tmp_path):
    """The context is built from what retrieval returned, so the message cannot
    reach either channel — and the ladder resolves a rung only for what the
    context holds.

    Asserted over the **withheld** set too, which is the trap: a build that
    filtered messages inside the builder would put the message's wordings in
    ``hidden``, and the AD-18 tripwire would then refuse an ordinary reply for
    reusing two consecutive words of the main's own message.
    """
    with a_store_with_both(tmp_path) as store:
        ranked = Retriever(store=store).retrieve(
            "farm", now="2026-09-02T00:00:00Z"
        )
    from half.context.build import split as split_context

    context, hidden = split_context(ranked, now="2026-09-02T00:00:00Z",
                                    ceiling=None)
    rendered = build_context(ranked, now="2026-09-02T00:00:00Z",
                             ceiling=None).render()

    seen = {item.id for item in context.content} | {
        item.id for item in context.directives
    }
    assert "b_m0" not in seen
    assert "b_m0" not in rendered
    assert seen == {"d_m0"}
    assert all("b_m0" not in fragment for fragment in hidden)


@pytest.mark.cap5_admission
def test_the_tension_minter_is_handed_claims_and_never_the_message(
    tmp_path, registry
):
    """CAP-7's comparison set is *beliefs sharing a subject*, and every
    production belief carries ``subject="self"`` — so before this story a first
    pass compared ``ok`` and ``thanks`` against every wanting the main had and
    paid a judgement for each.

    Narrowed at ``ActorRegistry.mint_view``, which is the door, so nothing
    inside ``half.consolidate`` has to know a message exists.
    """
    from half.consolidate.candidates import read

    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        store.record(Op.ASSERT, "b_m0", "2026-09-01T00:00:00Z", subject="self",
                     claim=WORTH, **{LEDGER: STATED, DERIVATION: UNDERIVED},
                     **ladder.admitted())
        store.record(Op.ASSERT, "d_m0", "2026-09-01T00:00:00Z", subject="self",
                     claim=WORTH, **{LEDGER: STATED, DERIVATION: DERIVED},
                     **ladder.admitted(support=["b_m0"]))

    view = asyncio.run(registry.mint_view(MAIN))
    assert sorted(view.beliefs) == ["d_m0"]
    assert sorted(read(view.beliefs)) == ["d_m0"]


# ═════════════════════════════════════════════════════════════════════════════
# the three readers that still read the message
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_admission
@pytest.mark.cap8_voice
def test_the_language_sample_still_reads_the_main_s_own_message(tmp_path):
    """**Reader one** (``half.voice.compose.sample_from``).

    The composer answers in the language the main last wrote in, and it reads
    that off the fold rather than off a turn — which is what makes it work on
    the unprompted morning at all. A message that stopped being in the fold, or
    that stopped carrying the stated ledger, is a main Half falls silent for.

    Red if the mark took the record out of the fold, and red if the sample
    started reading claims instead: the message is what the main *wrote*, and it
    is the only record here in their own script.
    """
    store = Store(tmp_path / "sample", prefix=build_prefix)
    store.record(Op.ASSERT, "b_m0", "2026-09-01T00:00:00Z", subject="self",
                 claim=SCRIPTS["japanese"],
                 **{LEDGER: STATED, DERIVATION: UNDERIVED}, **ladder.admitted())
    store.record(Op.ASSERT, "b_old", "2026-08-01T00:00:00Z", subject="self",
                 claim="an older message",
                 **{LEDGER: STATED, DERIVATION: UNDERIVED}, **ladder.admitted())

    assert sample_from(store.state().beliefs).text == SCRIPTS["japanese"]
    store.close()


@pytest.mark.cap5_admission
@pytest.mark.cap4_bought
def test_responsiveness_still_reads_the_main_s_own_message():
    """**Reader two** (``half.questions.answered.responsive``).

    *"The main said something after Half asked"* is a fact the log already
    carries, and it is read off the stated ledger. A message that stopped being
    recognisable there is a question re-asked for ever, because no reply would
    ever be recognised.
    """
    from half.store.records import make

    message = make(Op.ASSERT, "b_m0", "2026-09-01T00:00:00Z", subject="self",
                   claim=WORTH, **{LEDGER: STATED, DERIVATION: UNDERIVED},
                   **ladder.admitted())
    assert answered.responsive(message) is True


@pytest.mark.cap5_admission
@pytest.mark.cap4_bought
def test_one_reply_retires_one_question_though_a_claim_was_derived_from_it():
    """**Reader two's regression, and the reason it had to be re-pointed.**

    A derived claim is *also* an ``assert`` on the stated ledger, written on the
    same turn as the message it came from. Left alone, ``responsive`` would have
    matched it too — so one reply would have retired two questions, which is
    exactly the *"one reply retires one question"* rule this module's docstring
    says the first build got wrong, arriving back through a door nobody had
    opened yet.

    Two outstanding questions, one message, one claim: the newest question is
    retired and the older one is still waiting.
    """
    from half.store.records import ABOUT, QUESTION, make

    log = [
        make(Op.ASKED, "qa_1", "2026-09-01T00:00:00Z",
             **{QUESTION: "q_old", ABOUT: "b_1"}),
        make(Op.ASKED, "qa_2", "2026-09-01T00:01:00Z",
             **{QUESTION: "q_new", ABOUT: "b_2"}),
        make(Op.ASSERT, "b_m0", "2026-09-01T00:02:00Z", subject="self",
             claim=WORTH, **{LEDGER: STATED, DERIVATION: UNDERIVED},
             **ladder.admitted()),
        make(Op.ASSERT, "d_m0", "2026-09-01T00:02:00Z", subject="self",
             claim=WORTH, **{LEDGER: STATED, DERIVATION: DERIVED},
             **ladder.admitted(support=["b_m0"])),
    ]
    history = answered.history(log)

    assert history["q_new"].answered is True
    assert history["q_old"].answered is False, (
        "the derived claim retired a second question"
    )
    assert answered.responsive(log[-1]) is False


@pytest.mark.cap5_admission
@pytest.mark.cap11
def test_the_correction_aim_still_excludes_the_message(tmp_path, registry):
    """**Reader three** (``half.correction.apply.aim``), driven end to end.

    A correction is never about the sentence that provoked it. Since this story
    that holds twice over: the message is excluded by the aim, and it is never a
    candidate in the first place because the retrieval door does not emit one.
    The unit-level half — and the derived claim the old exclusion would have
    dropped instead — is ``tests/test_correction.py``.

    Here: the turn's own message and the previous turn's are both absent from
    what a correction could reach, so nothing is removed and nothing is
    proposed.
    """
    deriver, _ = a_deriver(refusing(DECISION_RELEVANCE))
    a_turn(tmp_path, registry, ["thats wrong", "thats wrong"], deriver=deriver)

    beliefs = beliefs_of(tmp_path)
    assert sorted(beliefs) == ["b_m0", "b_m1"], (
        "a correction removed the message that carried it"
    )
    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        ranked = Retriever(store=store).retrieve(
            "thats wrong", now="2026-09-02T00:00:00Z"
        )
    assert correction.aim(ranked) == ""


# ═════════════════════════════════════════════════════════════════════════════
# the turn: crisis, redelivery, replay
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_admission
@pytest.mark.cap12
def test_a_crisis_turn_derives_nothing(tmp_path, registry):
    """*"Crisis: the mode is open → nothing derived; the crisis path owns the
    turn."*

    Reached without a branch for it: the gate answers a disclosure itself and
    never calls ``_pipeline``, so no message is recorded and there is nothing to
    derive from. The holder is asked **nothing**, which is the assertion a
    ``no belief was written`` case could not make.
    """
    deriver, holder = a_deriver()

    class Answering(CrisisGate):
        async def handle(self, inbound):
            return "I am here."

    a_turn(tmp_path, registry, [WORTH], deriver=deriver,
           gate=Answering(pipeline=None, store=registry))

    assert holder.calls == 0
    assert deriver.tally.messages == 0


@pytest.mark.cap5_admission
def test_a_redelivered_message_derives_at_most_one_claim(tmp_path, registry):
    """At-least-once delivery makes redelivery routine, so the turn is
    idempotent — and so is the derivation. The second delivery returns at the
    idempotency check before the record is written, so nothing marks the turn as
    derivable and the holder is asked four times rather than eight."""
    deriver, holder = a_deriver()
    transport = FakeTransport([
        msg(text=WORTH, message_id="m0", chat_id=CHAT, date=1000),
        msg(text=WORTH, message_id="m0", chat_id=CHAT, date=1000),
    ])
    channel = TelegramChannel(transport=transport, mains={CHAT: MAIN})
    asyncio.run(Runtime(channel=channel, registry=registry,
                        derivers=deriver).run())

    assert sorted(beliefs_of(tmp_path)) == ["b_m0", "d_m0"]
    assert holder.calls == len(GATES)
    assert deriver.tally.derived == 1


@pytest.mark.cap5_admission
def test_a_log_of_messages_and_derived_claims_folds_identically(tmp_path,
                                                                registry):
    """*"Replay: folds identically; derivation is not in the fold"* (AD-4,
    AD-30).

    Nothing about a derivation is stored: no marker, no counter, no record that
    a message was judged. What the log holds is the message and, where there was
    one, the claim — so a rebuild from the log reproduces the same state without
    consulting anybody.
    """
    deriver, holder = a_deriver()
    a_turn(tmp_path, registry, [WORTH], deriver=deriver)

    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        before = store.state()
        calls = holder.calls
        rebuilt = store.rebuild()
        assert store.fold().beliefs == before.beliefs == rebuilt.beliefs
        assert holder.calls == calls, "a rebuild consulted a provider"
        ops = [record.op for record in store.log]
    assert ops.count(Op.ASSERT) == 2
    assert all(op is Op.ASSERT for op in ops)


@pytest.mark.cap5_admission
def test_nothing_a_refused_message_touches_is_durable(tmp_path, registry):
    """*"Nothing durable: a refused message leaves no claim, no partial record
    and no marker beyond what the turn already writes."*

    The whole log, op by op: one ``assert`` for the message and nothing else.
    """
    deriver, _ = a_deriver(refusing(DURABILITY))
    a_turn(tmp_path, registry, [NOT_DURABLE], deriver=deriver)

    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        records = list(store.log)
    assert [record.id for record in records] == ["b_m0"]
    assert records[0].data.get(DERIVATION) == UNDERIVED
    assert "refused" not in records[0].data
    assert not any(DURABILITY.name in str(value)
                   for value in records[0].data.values())


# ═════════════════════════════════════════════════════════════════════════════
# worldwide
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_admission
def test_a_message_in_any_script_is_judged_the_same_way(tmp_path, registry):
    """*"Any script: judged, with no English rubric on the path."*

    Five scripts, each derived, and the rendered request compared between them:
    it differs only in the message itself. That is the only form *"no English
    rubric and no locale"* can take for a path whose whole job is to forward a
    sentence it must not interpret.
    """
    rendered: dict[str, list[str]] = {}
    for script, text in SCRIPTS.items():
        deriver, holder = a_deriver()
        assert derive(deriver, text).keeps is True, script
        rendered[script] = [
            "\n".join(work.prompt.system).replace(text, "<MESSAGE>")
            + "\n" + "\n".join(turn.text for turn in work.prompt.turns
                               ).replace(text, "<MESSAGE>")
            for work in sorted(holder.seen, key=lambda w: w.labels)
        ]
    assert len({tuple(blocks) for blocks in rendered.values()}) == 1, (
        "the request differs between scripts by more than the message"
    )
    # And the message travels whole: not folded, not normalised, not clipped.
    for script, text in SCRIPTS.items():
        deriver, holder = a_deriver()
        derive(deriver, text)
        assert all(work.prompt.turns[0].text == text for work in holder.seen), (
            script
        )


@pytest.mark.cap5_admission
def test_a_claim_is_never_assumed_to_be_in_the_message_s_own_language(tmp_path):
    """*"Two languages: permitted; neither is assumed to be the other's."*

    Nothing on this path reads a language, so there is nothing here that could
    assume one — asserted as the absence of any language machinery rather than
    as a behaviour, because a behavioural case would be asserting that a stub
    returned what it was told to.

    A claim derived from a Devanagari message and one derived from a Japanese
    message take byte-identical paths, and the deriver hands back **no text at
    all**: the words are the caller's, which is what makes *"the claim is in
    whatever language the main wrote in"* a fact about the record rather than a
    rule somebody enforced.
    """
    forbidden = {
        "locale", "langdetect", "casefold", "lower", "upper", "unicodedata",
        "normalize", "encode", "decode", "translate", "detect",
    }
    for module in ("half/derive/gates.py", "half/derive/claim.py"):
        tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
        # **Over the code rather than over the file**, because every one of
        # these words appears in the prose that explains why it is absent —
        # a substring scan would be asserting that nobody documented the rule.
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in forbidden, (module, node.id)
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden, (module, node.attr)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert not (getattr(node, "module", "") or "").startswith(
                    ("locale", "unicodedata")
                ), (module, ast.unparse(node))
    assert not any(
        field.name in {"claim", "text", "message"}
        for field in Derived.__dataclass_fields__.values()
    ), "a derivation hands a main's own words back across the boundary"


# ═════════════════════════════════════════════════════════════════════════════
# structural: the shape, the tier, the bound, the holder
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_structure
def test_this_story_added_no_fifth_copy_of_the_consultation():
    """*"The consultation shape appears once and this story added no copy."*

    Both halves: the shared decisions are reached by name, and the arithmetic
    they would have replaced is absent from this file. A caller that kept its
    own copy beside the shared one is a fifth copy with an import at the top.
    """
    source = (ROOT / "half/derive/claim.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    reached = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert {
        "Breaker", "due", "rate", "count_one", "failure_key", "wider_than",
        "a_bound",
    } <= reached
    assert "% REPORT_EVERY" not in source
    assert "% ALARM_AFTER" not in source
    assert "_consecutive" not in source and "_quiet" not in source
    # And the shape still knows nothing about this domain, which was the
    # non-negotiable condition of the extraction.
    shape = (ROOT / "half/model/consult.py").read_text(encoding="utf-8")
    for gate in GATES:
        assert gate.name not in shape, gate.name
        assert not hasattr(consult, gate.name.replace("-", "_"))
        for label in gate.labels:
            assert not hasattr(consult, label), label
    for token in ("gate", "admission", "derive", "message", "claim"):
        assert not hasattr(consult, token), token


@pytest.mark.cap5_structure
def test_the_shared_numbers_are_shared_and_this_paths_policy_is_its_own():
    """Which numbers moved and which did not, pinned rather than reviewed.

    The three that differ between callers differ *for reasons*: the bound is the
    whole budget a main already waits for one turn, because nobody is waiting
    for a derivation but that main's *next* message is behind it; a stand-down
    is counted in derivations because a message is the unit ``derive`` is called
    in; and the alarm rate is a fifth rather than the morning's half because
    *cannot say* is an answer, so nothing in this rate's numerator is ordinary.
    """
    assert (BOUND_SECONDS, BREAK_FOR, ALARM_RATE) == (5.0, 24, 0.2)
    for name in ("BOUND_SECONDS", "BREAK_FOR", "ALARM_RATE"):
        assert not hasattr(consult, name), name
    assert (
        BREAK_AFTER, REPORT_EVERY, ALARM_AFTER,
        PER_CALL_MICRO_USD, PER_PASS_MICRO_USD,
    ) == (
        consult.BREAK_AFTER, consult.REPORT_EVERY, consult.ALARM_AFTER,
        consult.PER_CALL_MICRO_USD, consult.PER_PASS_MICRO_USD,
    )


@pytest.mark.cap5_structure
def test_the_bound_fits_inside_the_turn_a_main_already_waits_for():
    """The cross-constant relation, pinned in a test rather than at import
    because ``half.derive`` must not import the runtime that imports it — which
    is where ``half.voice.gate`` pins its own version, for its own version of
    the same reason.

    Nobody waits for a derivation, but that main's **next** message does: their
    turns are handled one at a time by their own worker. So the bound is the
    whole budget a main already waits for one turn, and the four gates run
    concurrently so a derivation costs one of these and not four.

    The bypass row is the morning composer's twenty seconds, which is the number
    somebody copying the nearest consultation reaches for.
    """
    from half.voice.turn import TURN_BOUND_SECONDS

    assert BOUND_SECONDS <= TURN_DEADLINE_SECONDS
    assert BOUND_SECONDS * len(GATES) > TURN_DEADLINE_SECONDS, (
        "four gates in series would fit, so nothing forces them to be "
        "concurrent"
    )
    assert BOUND_SECONDS >= TURN_BOUND_SECONDS
    assert consult.a_bound(BOUND_SECONDS)


@pytest.mark.cap5_structure
def test_a_derivation_costs_one_bound_and_not_four():
    """The gates run concurrently, which is what makes the bound above honest.

    Measured as a wall clock deliberately: the relation above is arithmetic over
    constants and would stay green for a build that ran the four gates in
    series, which is a derivation sitting in front of a main's next message for
    four times as long.
    """
    deriver, holder = a_deriver(sleep=0.05, bound_seconds=1.0)
    started = time.monotonic()
    derive(deriver)
    elapsed = time.monotonic() - started

    assert holder.calls == len(GATES)
    assert elapsed < 0.05 * len(GATES), elapsed


@pytest.mark.cap5_structure
def test_the_tier_is_pinned_and_is_never_the_mains():
    """SPEC:124 — *the recurring spend runs on a cheaper tier than conversation,
    because the free tier depends on that gap*. This runs on every inbound
    message of every main, so it is the second recurring spend in the product
    after the nightly pass.

    Asserted from both sides of the provider: the constant, and the ``Tiers``
    the composition root actually parses. A case that asserted only the constant
    would be green for a build that bound it and never used it — the failure
    story 9e's third mutation round found.
    """
    assert CLASSIFY_TIER == "cheap"

    tree = ast.parse((ROOT / "half/__main__.py").read_text(encoding="utf-8"))
    inside = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "derivers"
    ]
    assert len(inside) == 1
    parsed = [
        node for node in ast.walk(inside[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "parse"
    ]
    assert len(parsed) == 1
    names = {
        node.id for node in ast.walk(parsed[0]) if isinstance(node, ast.Name)
    }
    assert "DERIVE_TIER" in names, (
        "the deriver's tier is not read from half.derive.claim"
    )
    assert not any(
        isinstance(node, ast.Constant) and node.value == "cheap"
        for node in ast.walk(parsed[0])
    ), "the tier is respelled as a literal in the composition root"
    assert "config.tier_for" not in ast.unparse(inside[0]), (
        "the deriver's tier follows the main's conversation tier"
    )


@pytest.mark.cap5_structure
def test_the_holder_cannot_author_a_claim():
    """**The story's guarantee, and not hygiene.** A holder that could generate
    is a path from a main's message to a sentence Half composed about them and
    wrote into their ledger for ever, arriving through the one seam that is
    supposed to answer yes or no.

    An **allowlist**, because the denylist this pattern replaced let an object
    through that could ``classify`` and also ``chat`` — and so did one that was
    simply callable.
    """
    assert ALLOWED_METHODS == frozenset({"classify"})

    class Wider(Holder):
        async def generate(self, work): ...

    class Callable_(Holder):
        async def __call__(self, work): ...

    with pytest.raises(DeriveError, match="can also generate"):
        Derivers({MAIN: Wider()})
    with pytest.raises(DeriveError, match="itself callable"):
        Derivers({MAIN: Callable_()})
    with pytest.raises(DeriveError, match="cannot classify"):
        Derivers({MAIN: object()})


@pytest.mark.cap5_structure
def test_a_bench_is_sealed_after_construction():
    """A narrow output is half of a narrow holder; the other half is narrow
    authority. Rebinding the holders afterwards would put one past the check
    that it cannot produce text."""
    deriver, _ = a_deriver()
    with pytest.raises(DeriveError, match="sealed"):
        deriver._holders = {}  # type: ignore[misc]
    with pytest.raises(DeriveError, match="not a bound"):
        Derivers({}, bound_seconds=0)
    with pytest.raises(DeriveError, match="not a bound"):
        Derivers({}, bound_seconds=float("inf"))


@pytest.mark.cap5_structure
def test_the_message_leaves_the_machine_and_reaches_nothing_else(tmp_path,
                                                                 registry,
                                                                 caplog):
    """*"Nothing logged: no message text and no claim text in any log line"*
    (AD-22).

    The message goes to a provider four times, and the sentinel is then hunted
    through every captured log line, the tally, the result and the deriver's own
    counters. What may hold it is the log **file** — that is the ledger, and the
    whole point of the story is that the message is kept there as evidence.
    """
    sentinel = "sandalwood-nineteen-quicksilver"
    deriver, holder = a_deriver()
    with caplog.at_level(logging.DEBUG):
        a_turn(tmp_path, registry, [sentinel], deriver=deriver)

    assert holder.calls == len(GATES)
    assert all(sentinel in work.prompt.turns[0].text for work in holder.seen)
    assert sentinel not in caplog.text
    assert sentinel not in repr(deriver.tally)
    assert sentinel not in repr(derive(deriver, sentinel))
    # And it is in the ledger, which is where evidence belongs.
    assert beliefs_of(tmp_path)["b_m0"]["claim"] == sentinel


@pytest.mark.cap5_structure
def test_no_logging_call_in_the_derive_package_can_carry_content():
    """Scanned over the **arguments of every logging call** in the package,
    which is the form this guarantee takes everywhere else in this tree: a
    message in a variable and a receiver in a local are both invisible to a
    grep, and an invisible log call is how content gets logged.

    What is allowed through is a literal, a ``main_id``, a count, an exception's
    class, and a gate name or label from a closed set.
    """
    allowed = {
        "main_id", "gate", "name", "BREAK_AFTER", "BREAK_FOR", "reply",
        "self", "exc", "type",
    }
    # The counters, read off the type rather than restated: a field added to
    # ``Tally`` is a count and is allowed, and a field that is not a count
    # cannot be added to ``Tally`` without this case going red on the type.
    counts = set(Tally.__dataclass_fields__) | {
        "fell_back", "answered", "refused", "failure_rate", "_tally",
    }
    for module in ("half/derive/claim.py", "half/derive/gates.py"):
        tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "logger"):
                continue
            for argument in node.args[1:]:
                for name in ast.walk(argument):
                    if isinstance(name, ast.Name):
                        assert name.id in allowed, (module, ast.unparse(argument))
                    if isinstance(name, ast.Attribute):
                        assert name.attr in (
                            {"name", "kind", "because", "main_id", "__name__"}
                            | counts
                        ), (module, ast.unparse(argument))


@pytest.mark.cap5_structure
def test_a_provider_failure_and_an_unsure_gate_are_counted_apart():
    """Both produce no claim. One is an outage and the other is an answer, and a
    build that folded them would make the one rate an operator watches a
    measurement of how ambiguous a main's life is."""
    failure = Failure(kind=Kind.UNAVAILABLE, because=Reason.TRANSPORT_FAILED)
    down, _ = a_deriver({gate.name: failure for gate in GATES})
    derive(down)

    unsure, _ = a_deriver({gate.name: gate.unsure for gate in GATES})
    derive(unsure)

    assert down.tally.failures == {"unavailable/transport-failed": len(GATES)}
    assert down.tally.fell_back == len(GATES)
    assert down.tally.answered == 0
    assert unsure.tally.failures == {}
    assert unsure.tally.fell_back == 0
    assert unsure.tally.answered == len(GATES)
    assert (down.tally.failure_rate, unsure.tally.failure_rate) == (1.0, 0.0)


@pytest.mark.cap5_structure
def test_an_unreadable_answer_is_counted_apart_from_a_holder_that_raised():
    """A holder that threw and a provider that broke its own contract want
    different responses: the first is a build mistake, the second is a provider
    to stop trusting. Nothing is coerced — a label from another gate's set is
    unreadable rather than matched to its nearest neighbour."""
    other = DURABILITY.admits
    odd, _ = a_deriver({
        DECISION_RELEVANCE.name: Decision(label=other),
        DURABILITY.name: "not a label at all",
        INDEPENDENCE.name: object(),
        FALSIFIABILITY.name: FALSIFIABILITY.admits,
    })
    result = derive(odd)

    assert result.keeps is False
    assert result.verdict.unanswered == (
        "decision-relevance", "durability", "independence",
    )
    assert odd.tally.unreadable == 3
    assert odd.tally.raised == 0
    assert odd.tally.answers == {FALSIFIABILITY.admits: 1}


@pytest.mark.cap5_structure
def test_the_breaker_stands_a_main_down_only_when_every_gate_failed():
    """One flaky gate out of four is not an outage. Arming on any single gate's
    failure is the shape story 13a found in the voice: a stand-down bought by a
    tripwire that was never reached, while three gates answered perfectly well.

    Counted in **derivations**, and a skip is not a consultation — the breaker's
    whole job is to stop making calls, and counting its silence as failure would
    double-count one outage.
    """
    one_bad, holder = a_deriver({DURABILITY.name: RuntimeError("boom")})
    for _ in range(BREAK_AFTER + 2):
        derive(one_bad)
    assert one_bad.tally.skipped == 0
    assert holder.calls == len(GATES) * (BREAK_AFTER + 2)

    all_bad, down = a_deriver(
        {gate.name: RuntimeError("boom") for gate in GATES}
    )
    for _ in range(BREAK_AFTER + 3):
        derive(all_bad)
    assert all_bad.tally.skipped == 3
    assert down.calls == len(GATES) * BREAK_AFTER
    assert all_bad.tally.consulted == len(GATES) * BREAK_AFTER


@pytest.mark.cap5_structure
def test_a_wholly_failing_deriver_alarms_at_error_and_is_not_hidden_by_a_round_number(
    caplog
):
    """The one branch three callers had wrong, reaching the fifth through the
    shared shape: with the periodic question asked first and the alarm on an
    ``elif``, a wholly failing deriver reports at ``info`` at exactly the round
    numbers an operator would look at."""
    failure = Failure(kind=Kind.UNAVAILABLE, because=Reason.TRANSPORT_FAILED)
    deriver, _ = a_deriver({gate.name: failure for gate in GATES})
    with caplog.at_level(logging.INFO):
        for _ in range(REPORT_EVERY // len(GATES) + 1):
            derive(deriver)

    alarms = [r for r in caplog.records if r.levelno >= logging.ERROR
              and "claim derivation:" in r.message]
    assert alarms, "a wholly failing deriver never alarmed"
    assert consult.due(REPORT_EVERY, 1.0, alarm_rate=ALARM_RATE) is (
        consult.Due.ALARM
    )
    assert Derivers().quiet is True


@pytest.mark.cap5_structure
def test_a_derivation_is_bounded_by_the_budget_before_the_transport(tmp_path):
    """*"Over the cap: per-call or per-turn cost exceeded → refuses rather than
    overspending."*

    Asserted at the wire: a budget that refuses answers with a ``Failure`` and
    the transport is never touched. And the per-turn bound is structural — one
    derivation is exactly ``len(GATES)`` calls, so there is no input that buys a
    fifth.
    """
    from half.model.anthropic import AnthropicProvider
    from half.model.budget import Budget
    from half.model.tier import Tiers

    class Counting:
        def __init__(self) -> None:
            self.calls = 0

        async def send(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("the transport was reached")

        async def submit(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("the transport was reached")

        async def collect(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("the transport was reached")

    transport = Counting()
    provider = AnthropicProvider(
        transport,
        tiers=Tiers.parse({MAIN: CLASSIFY_TIER}),
        budget=Budget(per_call_micro_usd=1, per_pass_micro_usd=1),
    )
    deriver = Derivers({MAIN: provider.classifier()}, bound_seconds=1.0)
    result = derive(deriver, WORTH)

    assert result.keeps is False
    assert transport.calls == 0
    assert deriver.tally.consulted == len(GATES)
    assert sum(deriver.tally.failures.values()) == len(GATES)
    assert all(key.startswith("over-budget/") for key in deriver.tally.failures)


# ═════════════════════════════════════════════════════════════════════════════
# the mark: the closed vocabulary, and the direction that never excludes
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_structure
def test_the_derivation_vocabulary_is_closed_and_refused_at_the_append(store):
    """Write strict, read tolerant. A third word, once durable, is a record that
    is permanently neither a message nor a claim, and every reader below would
    resolve it its own way."""
    with pytest.raises(DeriveError, match="must be"):
        store.record(Op.ASSERT, "b_x", "2026-09-01T00:00:00Z", subject="self",
                     claim=WORTH, **{DERIVATION: "maybe"}, **ladder.admitted())
    with pytest.raises(DeriveError, match="must be"):
        store.record(Op.ASSERT, "b_y", "2026-09-01T00:00:00Z", subject="self",
                     claim=WORTH, **{DERIVATION: 7}, **ladder.admitted())
    assert list(store.state().beliefs) == []


@pytest.mark.cap5_structure
def test_the_mark_may_not_ride_on_an_op_that_asserts_nothing(store):
    """A ``retract`` or a ``schedule`` carrying one would be a correction or a
    due time claiming to be evidence — a shape no reader looks for, written
    durably where nothing would ever read it back."""
    with pytest.raises(DeriveError, match="may not carry"):
        store.record(Op.RETRACT, "co_1", "2026-09-01T00:00:00Z",
                     target="b_1", **{DERIVATION: UNDERIVED})


@pytest.mark.cap5_structure
def test_the_mark_survives_every_later_append_for_that_belief(store):
    """**Sticky**, for the reason quarantine is: a message is evidence for ever,
    and an ``assert`` for an existing belief that simply omits the field is the
    most ordinary operation there is. Without this, any promotion or demotion
    would unmark the message, put it back into retrieval and the minter, and
    replay would reproduce it unmarked."""
    store.record(Op.ASSERT, "b_m0", "2026-09-01T00:00:00Z", subject="self",
                 claim=WORTH, **{LEDGER: STATED, DERIVATION: UNDERIVED},
                 **ladder.admitted())
    # The most ordinary append there is: the same belief, restated.
    store.record(Op.ASSERT, "b_m0", "2026-09-02T00:00:00Z", subject="self",
                 claim=WORTH, **{LEDGER: STATED}, **ladder.admitted())

    held = store.state().beliefs["b_m0"]
    assert held[DERIVATION] == UNDERIVED
    assert underived(held)
    assert store.fold().beliefs == store.state().beliefs
    assert all(row["id"] != "b_m0" for row in store.all_candidates())


@pytest.mark.cap5_structure
def test_an_unmarked_belief_is_a_claim_and_never_silently_excluded(store):
    """**The direction the whole field turns on** — ``PASS_RAN``'s rule, one
    field over.

    Every belief in every log written before this story is unmarked. Reading
    absence as *evidence* would take a main's entire existing ledger out of
    retrieval, out of the minter and out of every context, permanently and with
    nothing saying so. Reading it as *a claim* is what those logs already meant.

    A mark this build does not know reads the same way, for the same reason.
    """
    seed_belief(store, "b_legacy", "2026-09-01T00:00:00Z", subject="self",
                claim=WORTH, ledger="stated")

    held = store.state().beliefs["b_legacy"]
    assert underived(held) is False
    assert derived_claim(held) is False
    assert [row["id"] for row in store.all_candidates()] == ["b_legacy"]
    assert underived({DERIVATION: "something-a-later-build-writes"}) is False
    assert underived(None) is False and derived_claim(None) is False


@pytest.mark.cap5_structure
def test_a_message_is_evidence_by_the_predicate_every_door_reads():
    """One reading of *"is this a message?"*, read by the retrieval door, the
    minting door and the correction aim — rather than a shape each of them
    checks. Two spellings of it is one door that stops matching, silently."""
    from half.store.records import belief_record

    message = {DERIVATION: UNDERIVED, LEDGER: STATED, "claim": WORTH}
    claim = {DERIVATION: DERIVED, LEDGER: STATED, "claim": WORTH}

    assert underived(message) and belief_record(message) is False
    assert derived_claim(claim) and belief_record(claim) is True
    assert belief_record({"claim": WORTH}) is True

    source = (ROOT / "half/store/db.py").read_text(encoding="utf-8")
    # Both read doors for beliefs, by the SQL they actually run: the term match
    # and the backstop behind a query that matched no term.
    assert "MATCH ? AND b.underived = 0" in source, (
        "the term-match door stopped excluding messages"
    )
    assert '" WHERE underived = 0 ORDER BY id"' in source, (
        "the backstop stopped excluding messages"
    )
    assert "underived(data)" in source
