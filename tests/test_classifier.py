"""CAP-12: the crisis classifier — one case per row of the I/O matrix (6d).

Four things this file refuses to do, because each would let it pass while the
product failed:

**It never lets a model decide anything but a question.** The centre of this
story is an asymmetry: a model may widen the cheap, reversible action and may
never impose the durable one. So the mode-never-opens assertion is run over
*every* label, *every* failure kind, *every* reason, a hand-built decision
carrying a label from no known set, and a holder that raises — rather than over
the two outcomes somebody expected.

**It keeps *uncertain* and *unavailable* apart.** They are both "no answer" and
they are handled oppositely, so every case here says which one it is testing and
what the other would have done. A build that collapsed them would pass half of
these and fail the other half, which is the point.

**It asserts what leaves the machine, byte for byte.** *"Only the message text
goes"* is checked against the rendered request with a seeded ledger, a confirmed
contact and a told region in the store — not against a docstring. Everything
Half knows is on disk while the call is made, and none of it is in the payload.

**It closes sets rather than sampling them.** The label set is closed and
checked at import; the reply for a widened turn is the same reviewed template
join the phrase table produces, asserted by equality rather than by inspection.

**A green run here is not clinical review.** The companion's build requirement 6
is a qualified reviewer before launch, and detection quality — the label set,
the instructions, and what each label permits — is exactly what that reviewer is
for. Nothing in this file substitutes for it.
"""

from __future__ import annotations

import ast
import asyncio
import json
import time
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.crisis import classifier as clf
from half.crisis import respond, templates
from half.crisis.classifier import (
    ACTION_FOR_LABEL,
    ALARM_AFTER,
    ALARM_RATE,
    ALLOWED_METHODS,
    ANOTHER_AT_RISK,
    BOUND_SECONDS,
    BREAK_AFTER,
    BREAK_FOR,
    CLASSIFY_TIER,
    INSTRUCTIONS,
    LABELS,
    MAIN_AT_RISK,
    NO_RISK,
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    UNSURE,
    SecondOpinion,
    Tally,
    Verdict,
    prompt_for,
)
from half.crisis.gate import CrisisGate
from half.crisis.signals import SAFE_WORD, Action, Assessment, Tier, assess
from half.errors import CrisisError
from half.governance.ladder import License
from half.model.anthropic import render_classify
from half.model.budget import Budget, estimate
from half.model.port import (
    Classified,
    Classify,
    Decision,
    Failure,
    Kind,
    Reason,
    Role,
    Usage,
)
from half.model.tier import DEFAULT_MODELS, Tier as ModelTier
from half.store.store import Store
from half.__main__ import build
from half.config import MAINS_ENV, ROOT_ENV, load
from tests.conftest import FakeTransport, msg, seed_belief
from tests.test_crisis import MEANS_WORDS, Pipeline, inbound, words_of

pytestmark = [pytest.mark.cap12, pytest.mark.cap12_classifier]

ROOT = Path(__file__).resolve().parents[1]
MAIN = "vidit"
#: Epoch seconds the fake transport stamps a turn with.
AT = 1_788_256_800


class TimedTransport(FakeTransport):
    """``FakeTransport``, plus when each reply actually reached the wire.

    The concurrency row cannot be asserted any other way: *not delayed* is a
    statement about time, and the finding it exists for was a measurement.
    """

    def __init__(self, updates=None):
        super().__init__(updates)
        self.timed: list[tuple[str, str, float]] = []

    async def send_message(self, chat_id: str, text: str) -> str:
        result = await super().send_message(chat_id, text)
        self.timed.append((chat_id, text, time.monotonic()))
        return result

#: Messages the phrase table returns nothing at all for. **Checked, not
#: assumed** — ``test_the_gap_this_story_exists_for_is_real`` asserts the table
#: is silent on every one of them, so a table that grew a row for one stops it
#: being evidence here rather than quietly making a case vacuous.
UNSEEN = (
    "मैं अब और नहीं जी सकता",          # Hindi
    "no puedo más, quiero morir",       # Spanish
    "je ne veux plus être là demain",   # French
    "私はもう生きていたくない",          # Japanese
    "i sorted out who gets the cat",    # preparatory, unlisted phrasing
    "i am tired of waking up every morning",
)

#: An ordinary message the table is also silent on, and which no model should
#: read as risk. The counterweight to ``UNSEEN``: the classifier is consulted
#: on both, and only the label differs.
ORDINARY = "i finally booked the flights"


# =============================================================================
# the doubles
# =============================================================================


class Holder:
    """The port's narrow classifier, and nothing wider.

    One method, returning a ``Decision`` or one of the four failures. It has no
    ``generate`` for the same reason ``AnthropicClassifier`` has none: a caller
    that cannot author text cannot author the wrong text.
    """

    def __init__(self, answer: object = None, *, sleep: float = 0.0) -> None:
        # Private, because ``SecondOpinion`` now refuses a holder with any
        # public callable but ``classify`` — and an ``answer`` that is a lambda
        # is a public callable. The double is held to the same shape as the
        # real thing, which is the point of the check.
        self._answer = answer
        self._sleep = sleep
        self.seen: list[Classify] = []

    async def classify(self, work: Classify) -> Classified:
        self.seen.append(work)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if isinstance(self._answer, BaseException):
            raise self._answer
        if callable(self._answer):
            return self._answer(work)
        return self._answer


class Exploding:
    """A holder that must never be reached. Every *no model call* row uses it,
    so the assertion is that the call did not happen rather than that a counter
    stayed at zero."""

    async def classify(self, work: Classify) -> Classified:
        raise AssertionError("a model was consulted where none may be")


def labelled(label: str) -> Decision:
    return Decision(label=label, usage=Usage(input_tokens=120, micro_usd=900))


def opinion(answer: object = None, **kw) -> tuple[SecondOpinion, Holder]:
    holder = Holder(answer, **kw)
    return SecondOpinion({MAIN: holder}), holder


def gate(answer: object = None, **kw) -> tuple[CrisisGate, Holder, Pipeline]:
    second, holder = opinion(answer, **kw)
    pipeline = Pipeline()
    return CrisisGate(pipeline=pipeline, second=second), holder, pipeline


def handled(one: CrisisGate, text: str, **kw) -> str | None:
    return asyncio.run(one.handle(inbound(text, **kw)))


def consulted(second: SecondOpinion, text: str, main: str = MAIN):
    return asyncio.run(second.consult(text, main_id=main))


# =============================================================================
# matrix: the gap this story exists for
# =============================================================================


def test_the_gap_this_story_exists_for_is_real():
    """Matrix: non-English, and preparatory. Every message in ``UNSEEN`` is one
    the phrase table returns nothing for — no enter, no ask, no surface.

    This case is the load-bearing one in the file: it is what makes every row
    below a test of the classifier rather than a test of the table underneath
    it. A table that grew a row for one of these would fail here, and the fix is
    to find another gap, not to delete the line.
    """
    for text in UNSEEN:
        found = assess(text)
        assert found.action is Action.NONE, (text, found.tier, found.action)


def test_the_phrases_the_story_named_are_already_the_tables():
    """The other half of the same honesty. Story 6d's intent names ``kms``,
    ``unalive myself``, ``im sucidal``, ``i've written a note`` and ``i'm
    done.`` as things the table misses — and story 6a's own review round put all
    five into the asking vocabulary before this story started.

    They are pinned here so the record is accurate about what the model is for:
    it is not a second chance at the English somebody already wrote down, it is
    the phrasings and the scripts nobody will."""
    for text in ("kms", "unalive myself", "im sucidal", "i have written a note",
                 "i won't be here tomorrow", "im done."):
        assert assess(text).asks, text


# =============================================================================
# matrix: the safe word, an explicit disclosure — decided offline
# =============================================================================


@pytest.mark.parametrize(
    "text",
    [SAFE_WORD, f"i can't say it. {SAFE_WORD}", "i want to kill myself",
     "i am going to end my life tonight"],
    ids=["safe-word", "safe-word-mid-sentence", "disclosure", "disclosure-plan"],
)
def test_the_offline_floor_never_reaches_a_model(text):
    """Matrix: safe word, and explicit disclosure. *Enters, with no model call
    made — offline, always.*

    The unconditional escape hatch is unconditional because nothing on its path
    can fail. A holder that raises on contact is the assertion: if entering ever
    consulted a model, this row would fail rather than merely be slower.
    """
    one = CrisisGate(pipeline=Pipeline(), second=SecondOpinion({MAIN: Exploding()}))
    reply = handled(one, text)
    assert one.in_crisis(MAIN)
    assert respond.is_templated(reply)


def test_the_offline_floor_holds_with_every_holder_the_port_can_hand_back():
    """The same row, said structurally: a gate whose classifier is a hole in
    the ground still enters on the safe word, because the tier table resolved
    before anything else was consulted."""
    class Broken:
        async def classify(self, work):
            raise RuntimeError("the provider is on fire")

    one = CrisisGate(pipeline=Pipeline(), second=SecondOpinion({MAIN: Broken()}))
    assert one.in_crisis(MAIN) is False
    handled(one, SAFE_WORD)
    assert one.in_crisis(MAIN)


# =============================================================================
# matrix: the table finds nothing and the model sees risk
# =============================================================================


@pytest.mark.parametrize("text", UNSEEN)
def test_a_message_the_table_misses_and_the_model_reads_as_risk_asks(text):
    """Matrix: table finds nothing, model sees risk · non-English ·
    preparatory. *Half asks* — and never enters on a model's word."""
    one, holder, pipeline = gate(labelled(MAIN_AT_RISK))
    reply = handled(one, text)

    assert one.awaiting_answer(MAIN), text
    assert not one.in_crisis(MAIN), "a model entered the mode"
    assert templates.ASK.text in reply
    assert respond.is_templated(reply)
    assert not pipeline.seen, "a widened turn ran the ordinary pipeline"
    assert len(holder.seen) == 1


def test_the_widened_reply_is_the_tables_own_question_byte_for_byte():
    """The reply a model widened into is the reply the phrase table produces:
    same tier, same reviewed lines, same words. There is no second, weaker
    asking path for a later story to find and no way for a main to tell which
    of the two noticed."""
    one, _, _ = gate(labelled(MAIN_AT_RISK))
    widened = handled(one, UNSEEN[0])
    assert widened == respond.reply_for(Assessment(Tier.INFERENCE, Action.ASK))
    assert widened == handled(CrisisGate(pipeline=Pipeline()), "whats the point",
                              main="other")


def test_a_widened_question_still_reaches_the_mode_through_the_mains_own_yes():
    """The whole design, in one sequence. The model makes Half ask; the *main*
    answers; the table reads the answer and enters on a confirmation. The mode
    is opened by a person's own word every time, and the model's contribution
    is that the question was put at all."""
    one, holder, _ = gate(labelled(MAIN_AT_RISK))
    handled(one, UNSEEN[0], external_id="m0")
    assert not one.in_crisis(MAIN)

    reply = handled(one, "yeah", external_id="m1")
    assert one.in_crisis(MAIN)
    assert respond.is_templated(reply)
    assert len(holder.seen) == 1, "the answering turn was sent to a model too"


def test_the_answer_no_ends_it_with_nothing_durable_left_behind(tmp_path):
    """The cheap action is cheap because it is reversible. A widened question
    the main answers *no* to leaves no mode, no cap, and nothing in the log."""
    root = tmp_path / "mains"
    registry = ActorRegistry(root)
    holder = Holder(labelled(MAIN_AT_RISK))
    drive(registry, SecondOpinion({MAIN: holder}),
          [(UNSEEN[0], 1_788_256_800), ("no, nothing like that", 1_788_256_900)])
    opened = registry.crisis_open(MAIN)
    ceiling = registry.license_ceiling(MAIN)
    registry.close()

    assert not opened
    assert ceiling.rung is not License.BEHAVE
    with Store(root / MAIN) as store:
        assert store.state().ceiling is None


# =============================================================================
# matrix: uncertain, and every label
# =============================================================================


def test_a_model_that_ran_and_is_unsure_asks():
    """Matrix: model uncertain. *Half asks — doubt is cheap.*

    ``unsure`` is a label, not a failure. It is the one row that separates this
    design from the one that treats every non-answer alike, and the cost of
    being wrong here is a question somebody says no to."""
    one, _, _ = gate(labelled(UNSURE))
    assert templates.ASK.text in handled(one, ORDINARY)
    assert one.awaiting_answer(MAIN)
    assert not one.in_crisis(MAIN)


@pytest.mark.parametrize("label", LABELS)
def test_no_label_whatsoever_opens_the_mode(label):
    """Acceptance: *given any model outcome, the mode is never entered on the
    model's word alone.* Run over the closed set rather than over the two
    labels somebody expected to matter."""
    one, _, _ = gate(labelled(label))
    handled(one, ORDINARY)
    assert not one.in_crisis(MAIN), label


@pytest.mark.parametrize("label", LABELS)
def test_a_label_does_exactly_what_the_table_says_and_no_more(label):
    """The mapping is the contract, so it is asserted through the gate rather
    than by reading the dict back."""
    one, _, pipeline = gate(labelled(label))
    reply = handled(one, ORDINARY)
    if ACTION_FOR_LABEL[label] is Action.ASK:
        assert one.awaiting_answer(MAIN) and templates.ASK.text in reply
        assert not pipeline.seen
    else:
        assert not one.awaiting_answer(MAIN)
        assert reply == "ordinary" and pipeline.seen


def test_a_third_party_label_does_not_surface_a_resource_on_its_own():
    """Matrix: third party. *6a's behaviour, unchanged.*

    The third-party reply is a sentence about somebody the main loves, and a
    model may not author one of those any more than it may open the mode: the
    label exists so a message about a frightened friend has somewhere to go
    other than ``main_at_risk``, and its action is nothing at all."""
    one, _, pipeline = gate(labelled(ANOTHER_AT_RISK))
    reply = handled(one, "she has been in a bad way since january")
    assert reply == "ordinary" and pipeline.seen
    assert templates.OTHER_RESOURCE.text not in (reply or "")
    assert not one.in_crisis(MAIN)


def test_the_table_still_owns_the_third_party_path():
    """And where the *table* reads a third party, the model is not consulted at
    all — that reply is decided offline exactly as story 6a decided it."""
    one = CrisisGate(pipeline=Pipeline(), second=SecondOpinion({MAIN: Exploding()}))
    reply = handled(one, "my friend is suicidal and i don't know what to do")
    assert templates.OTHER_RESOURCE.text in reply
    assert not one.in_crisis(MAIN)


# =============================================================================
# matrix: unavailable, refused, over budget, slow, prose
# =============================================================================


#: Every failure the port can report, as the caller receives it. Parametrized
#: over the *product* of the two closed enums rather than over a handful,
#: because "unavailable" is four kinds and ten reasons and a build that fell
#: back on three of them would look identical from the outside.
FAILURES = [
    Failure(kind, reason) for kind in Kind for reason in Reason
]


@pytest.mark.parametrize(
    "failure", FAILURES, ids=[f"{f.kind}-{f.because}" for f in FAILURES]
)
def test_every_failure_falls_back_to_the_table_and_is_counted(failure):
    """Matrix: model unavailable · slow · prose. *The table's answer stands,
    and the fallback is counted. Never asks everyone.*

    The failure the story names — transport, refusal, budget — is three rows of
    this table; the rest are here because a build that handled the three and
    treated a truncated reply as a judgement would pass the three."""
    second, holder = opinion(failure)
    one = CrisisGate(pipeline=Pipeline(), second=second)
    reply = handled(one, UNSEEN[0])

    assert reply == "ordinary", "a failure was read as an answer"
    assert not one.awaiting_answer(MAIN)
    assert not one.in_crisis(MAIN)
    assert second.tally.fell_back == 1
    assert second.tally.answered == 0
    assert second.tally.fallback_rate == 1.0
    assert len(holder.seen) == 1


def test_a_fallback_is_visible_as_a_rate_rather_than_only_as_an_event():
    """*If the classifier is failing, an operator can see the rate.* A silent
    degradation of the recall this story exists for is the worst outcome
    available, so the counter is asserted as a proportion and not as a flag."""
    answers = [
        labelled(NO_RISK),
        Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
        labelled(NO_RISK),
        Failure(Kind.OVER_BUDGET, Reason.PER_PASS_BUDGET),
    ]
    second = SecondOpinion({MAIN: Holder(lambda work: answers.pop(0))})
    for _ in range(4):
        consulted(second, ORDINARY)

    tally = second.tally
    assert tally.consulted == 4
    assert tally.fell_back == 2
    assert tally.fallback_rate == 0.5
    assert tally.failures == {
        "unavailable/transport-failed": 1, "over-budget/per-pass-budget": 1,
    }
    assert tally.labels == {NO_RISK: 2}
    assert tally.asked == 0


def test_a_model_past_the_bound_is_an_unavailability_and_never_holds_the_reply():
    """Matrix: model slow. *Treated as unavailable. Never holds the reply.*

    The bound is asserted by the clock rather than by inspection: a holder that
    sleeps for a hundred times the bound must not add a hundred times the bound
    to the main's wait."""
    second = SecondOpinion({MAIN: Holder(labelled(MAIN_AT_RISK), sleep=5.0)},
                           bound_seconds=0.02)
    one = CrisisGate(pipeline=Pipeline(), second=second)
    started = time.monotonic()
    reply = handled(one, UNSEEN[0])
    elapsed = time.monotonic() - started

    assert reply == "ordinary", "the table's answer did not stand"
    assert elapsed < 1.0, f"the reply waited {elapsed:.2f}s on a hanging model"
    assert second.tally.bound_exceeded == 1
    assert second.tally.fell_back == 1
    assert not one.awaiting_answer(MAIN)


def test_the_bound_is_counted_apart_from_a_transport_fault():
    """*The classifier is slow* and *the provider is unreachable* want
    different things done about them, and the port's closed reason set has no
    room to say which — so the tally keeps its own counter rather than
    reporting a timeout as a network fault."""
    second = SecondOpinion({MAIN: Holder(labelled(UNSURE), sleep=5.0)},
                           bound_seconds=0.02)
    consulted(second, ORDINARY)
    assert second.tally.bound_exceeded == 1
    assert second.tally.failures == {}
    assert second.tally.raised == 0


@pytest.mark.parametrize(
    "answer",
    [
        Decision(label="perhaps the user is sad"),
        Decision(label=""),
        Decision(label="MAIN_AT_RISK"),
        Decision(label="main_at_risk "),
        "main_at_risk",
        {"label": "main_at_risk"},
        None,
        42,
    ],
    ids=["prose", "empty", "wrong-case", "trailing-space", "bare-string",
         "mapping", "none", "number"],
)
def test_anything_that_is_not_a_label_from_the_closed_set_is_a_fallback(answer):
    """Matrix: model returns prose. *Treated as unavailable. Never parsed as a
    decision.*

    The port refuses a label outside the request's own set before this module
    sees it, so most of these are unreachable through it today. They are here
    because *unreachable* is a claim about this build's port, and this is the
    one place where being wrong about it would turn an unknown word into an
    action taken about a person.
    """
    second, _ = opinion(answer)
    verdict = consulted(second, UNSEEN[0])
    assert verdict.fell_back
    assert verdict.action is Action.NONE
    assert verdict.label is None
    assert second.tally.answered == 0
    assert second.tally.fell_back == 1


def test_a_holder_that_raises_falls_back_rather_than_costing_the_reply():
    """The port answers a provider fault with a value, so a raise is a build
    mistake — an unknown tier, a budget that admits nothing. A build mistake
    must not cost the recall this module exists for, and must never cost a main
    their reply."""
    one, _, pipeline = gate(RuntimeError("no tier for this main"))
    assert handled(one, UNSEEN[0]) == "ordinary"
    assert pipeline.seen
    assert not one.in_crisis(MAIN)


def test_a_gate_whose_classifier_is_itself_broken_still_answers():
    """The belt beside the braces. ``consult`` answers rather than raising, so
    this is unreachable through it — and the gate catches anyway, because on
    the one path where going quiet is a documented catastrophic failure the set
    of exceptions worth losing a reply over is empty."""
    class Detonating:
        def holds(self, main_id):
            return True

        async def consult(self, text, *, main_id):
            raise RuntimeError("the second opinion itself is broken")

    one = CrisisGate(pipeline=Pipeline(), second=Detonating())
    assert handled(one, UNSEEN[0]) == "ordinary"


# =============================================================================
# matrix: one call per turn, and never when the mode is open
# =============================================================================


def test_a_main_in_the_mode_is_never_classified():
    """Matrix: mode already open. *No classification is made.*

    Every turn inside the mode resolves to the held plan whatever the message
    says, so a classification could not change anything — and sending a person
    in crisis to a provider on every message they type is egress that buys
    nothing."""
    one, holder, _ = gate(labelled(MAIN_AT_RISK))
    handled(one, "i want to kill myself", external_id="m0")
    assert one.in_crisis(MAIN)
    for index, text in enumerate(("are you still there", "i mean it",
                                  "let me out of this"), start=1):
        handled(one, text, external_id=f"m{index}")
    assert holder.seen == [], "a held main was classified"


def test_a_turn_the_table_already_decided_is_never_classified():
    """*One call per turn at most*, made true by construction: every
    resolution but *nothing found* returns before a request is built."""
    one = CrisisGate(pipeline=Pipeline(), second=SecondOpinion({MAIN: Exploding()}))
    for index, text in enumerate(
        (SAFE_WORD, "i want to kill myself", "whats the point of any of it",
         "my friend is suicidal"), start=0,
    ):
        handled(one, text, main=f"m{index}", external_id=f"e{index}")


def test_an_ordinary_turn_costs_exactly_one_classification():
    one, holder, pipeline = gate(labelled(NO_RISK))
    assert handled(one, ORDINARY) == "ordinary"
    assert len(holder.seen) == 1
    assert pipeline.seen


def test_a_standing_question_is_not_asked_a_second_time_by_a_model():
    """Story 6a's rule, and it outranks the model. More hedging does not ask
    again — the question already stands — and a model reading risk in a message
    the main sent *while being asked about it* would ask again. Two questions
    in a row is nagging in the one register where nagging is unforgivable, and
    it leaves the main's next *yes* answering whichever of them the code looked
    at first.

    **The cost is one turn, and it is written down here rather than left to be
    discovered.** A main who answers Half's question in a script the table
    cannot read has that turn resolved by 6a — the question is abandoned, the
    ordinary pipeline runs — and the model is consulted again on the *next*
    message, where it widens as it would have. Recall is deferred by one turn
    and not lost. The alternative was letting a model re-ask on top of Half's
    own standing question, which 6a's frozen block forbids in as many words.
    """
    one, holder, _ = gate(labelled(MAIN_AT_RISK))
    handled(one, "whats the point of any of it", external_id="m0")
    assert one.awaiting_answer(MAIN)
    assert holder.seen == [], "the asking turn was classified"

    handled(one, UNSEEN[0], external_id="m1")
    assert holder.seen == [], "a model asked on top of a standing question"
    assert not one.awaiting_answer(MAIN), "6a abandons the question on this turn"

    handled(one, UNSEEN[1], external_id="m2")
    assert len(holder.seen) == 1, "the next turn is classified again"
    assert one.awaiting_answer(MAIN)
    assert not one.in_crisis(MAIN)


def test_an_empty_message_is_not_sent_anywhere():
    second, holder = opinion(labelled(MAIN_AT_RISK))
    for text in ("", "   ", "\n\t "):
        assert consulted(second, text) is clf.NOT_CONSULTED
    assert holder.seen == []
    assert second.tally.consulted == 0


def test_a_main_with_no_holder_is_story_6a_exactly():
    """Not a fallback, and the difference is the point: a rate that counted
    every turn of a build with no classifier wired would measure how quiet the
    deployment is rather than how often the classifier fails."""
    second = SecondOpinion({"asha": Holder(labelled(MAIN_AT_RISK))})
    assert consulted(second, UNSEEN[0]) is clf.NOT_CONSULTED
    assert second.tally.consulted == 0
    assert second.tally.fell_back == 0
    assert second.tally.fallback_rate == 0.0
    assert not second.holds(MAIN) and second.holds("asha")


def test_a_gate_with_no_classifier_at_all_behaves_as_it_did_before():
    """The absent path, which the red-team suite also runs end to end. A gate
    built without a second opinion is story 6a's gate: the table decides, and
    a message it has no row for is an ordinary Tuesday."""
    one = CrisisGate(pipeline=Pipeline())
    assert handled(one, UNSEEN[0]) == "ordinary"
    assert not one.awaiting_answer(MAIN)
    assert handled(one, SAFE_WORD, external_id="m2")
    assert one.in_crisis(MAIN)


# =============================================================================
# matrix: egress — what leaves the machine
# =============================================================================


def drive(registry, second, turns, *, mains=None):
    """Drive the real runtime with a second opinion wired, as ``serve`` does.

    One runtime for the whole conversation, which is the shape production has:
    a gate per process rather than a gate per message. A driver that rebuilt the
    runtime each turn would silently lose the standing question — volatile by
    AD-26 and correctly so — and a sequence that enters through a confirmation
    would quietly stop entering while every assertion about it still passed.
    """
    transport = FakeTransport([
        msg(text=text, message_id=f"r{index}", chat_id="123", date=at)
        for index, (text, at) in enumerate(turns)
    ])
    channel = TelegramChannel(transport=transport, mains=mains or {"123": MAIN})
    asyncio.run(Runtime(channel=channel, registry=registry, second=second).run())
    return [sent for _, sent in transport.sent]


#: Everything Half knows about this main, seeded before the call is made. Each
#: string is distinctive enough that finding it in a payload is proof rather
#: than coincidence.
KNOWN = {
    "belief": "replies to his mother within three minutes",
    "loop": "buy-farmland-in-kodaikanal",
    "contact": "आशा",
    "handle": "asha_on_telegram",
}


def test_only_the_message_text_leaves_the_machine(tmp_path):
    """Matrix: egress content. *The message text only leaves — no ledger, no
    beliefs.*

    Asserted against the rendered request with a full store behind it: a
    belief, a loop, a confirmed contact and a told region are all on disk while
    the call is made. The one string in the payload that came from this main is
    the message they just sent.
    """
    root = tmp_path / "mains"
    root.mkdir(parents=True)
    with Store(root / MAIN) as store:
        seed_belief(store, "b_1", "2026-08-01T09:00:00Z", subject="self",
                    claim=KNOWN["belief"], ledger="revealed", independent=2)
        seed_belief(store, "b_2", "2026-08-02T09:00:00Z", rung=License.ASSERT,
                    support=["s_1"], contact=KNOWN["contact"],
                    handle=KNOWN["handle"])
        seed_belief(store, "b_3", "2026-08-03T09:00:00Z", rung=License.ASSERT,
                    support=["s_2"], region="in")

    registry = ActorRegistry(root)
    holder = Holder(labelled(NO_RISK))
    drive(registry, SecondOpinion({MAIN: holder}),
          [(ORDINARY, 1_788_256_800)])
    registry.close()

    assert len(holder.seen) == 1
    payload = json.dumps(
        render_classify(holder.seen[0], DEFAULT_MODELS[ModelTier.CHEAP]),
        ensure_ascii=False,
    )
    assert ORDINARY in payload, "the message itself did not go"
    for name, value in KNOWN.items():
        assert value not in payload, f"the {name} left the machine"
    # The turn is the message and nothing appended to it — no history, no
    # retrieved claim, no name, no address, no id.
    sent = json.loads(payload)["messages"]
    assert [turn["content"] for turn in sent] == [ORDINARY]
    for blocks in json.loads(payload)["system"]:
        assert blocks["text"] in INSTRUCTIONS, "an unreviewed block went out"


def test_the_main_id_resolves_a_tier_and_appears_in_no_payload():
    """``main_id`` is on the ``Prompt`` because the tier travels with the main
    (AD-20). It is read where the model is resolved and is in nothing that goes
    out — *no identifiers beyond what the call needs*, checked against the
    renderer rather than against a sentence about it."""
    work = Classify(prompt=prompt_for("kms", main_id="a-very-distinctive-id"),
                    labels=LABELS)
    payload = json.dumps(render_classify(work, DEFAULT_MODELS[ModelTier.CHEAP]))
    assert "a-very-distinctive-id" not in payload
    assert work.prompt.main_id == "a-very-distinctive-id"


def test_the_request_is_one_user_turn_and_the_reviewed_instructions():
    """Nothing else is representable: there is no history parameter, no
    retrieval, no strand and no place for one to be added quietly — the whole
    prompt is built by one function taking one string."""
    prompt = prompt_for("kms", main_id=MAIN)
    assert prompt.turns == (
        type(prompt.turns[0])(role=Role.USER, text="kms"),
    )
    assert prompt.system == INSTRUCTIONS
    assert prompt.cache is None, "an unplaceable breakpoint would raise on a turn"


def test_the_message_is_never_truncated_before_it_is_sent():
    """A clipped message would be a classification of half a sentence reported
    as a classification. A message too long for the ceiling is refused by the
    budget instead, which is a fallback somebody can see."""
    long = "मैं " * 400
    assert prompt_for(long, main_id=MAIN).turns[0].text == long


@pytest.mark.parametrize("tier", list(ModelTier))
def test_an_ordinary_message_is_admitted_on_every_tier(tier):
    """CAP-12 is never gated by tier, so a per-call ceiling that refused every
    paid main's turns would be a tier gate wearing a budget's clothes. The
    estimate charges the full output ceiling in advance, which is what makes
    the frontier figure four times the cheap one."""
    from half.model.anthropic import classify_ceiling

    spec = DEFAULT_MODELS[tier]
    prompt = prompt_for("i sorted out who gets the cat", main_id=MAIN)
    priced = estimate(
        spec,
        cached_text=prompt.cached_blocks,
        uncached_text=prompt.uncached_blocks + (prompt.turns[0].text,),
        max_output_tokens=classify_ceiling(spec),
    )
    assert priced.micro_usd <= PER_CALL_MICRO_USD, (tier, priced.micro_usd)


def test_the_two_ceilings_are_a_budget_this_build_accepts():
    Budget(per_call_micro_usd=PER_CALL_MICRO_USD,
           per_pass_micro_usd=PER_PASS_MICRO_USD)


# =============================================================================
# matrix: records, logs, tier
# =============================================================================


@pytest.mark.parametrize(
    "label", LABELS, ids=[f"label-{label}" for label in LABELS]
)
def test_a_classified_turn_writes_no_belief_about_the_main(tmp_path, label):
    """Matrix: records. *No belief is written.* Run over every label, because
    the widened path and the ordinary path record different things and only one
    of them is obvious."""
    root = tmp_path / label
    registry = ActorRegistry(root)
    drive(registry, SecondOpinion({MAIN: Holder(labelled(label))}),
          [(UNSEEN[0], 1_788_256_800)])
    registry.close()

    with Store(root / MAIN) as store:
        beliefs = store.state().beliefs
    if ACTION_FOR_LABEL[label] is Action.ASK:
        assert beliefs == {}, "a widened turn recorded something"
    else:
        # The ordinary pipeline ran, which is story 4's behaviour and records
        # the main's own message as a `behave` claim. Nothing about the
        # classification is there: no label, no score, no model.
        for record in beliefs.values():
            for field in ("label", "classification", "risk", "model"):
                assert field not in record, field


def test_no_classification_is_ever_recorded_anywhere(tmp_path):
    """*Nothing is written about the message.* The tally is a count in memory,
    and the log is scanned for the label that produced the question."""
    root = tmp_path / "mains"
    registry = ActorRegistry(root)
    second = SecondOpinion({MAIN: Holder(labelled(MAIN_AT_RISK))})
    drive(registry, second, [(UNSEEN[0], 1_788_256_800)])
    registry.close()

    assert second.tally.labels == {MAIN_AT_RISK: 1}
    for path in sorted((root / MAIN).rglob("*")):
        if path.is_file() and path.suffix in {".jsonl", ".md"}:
            body = path.read_text(encoding="utf-8")
            for label in LABELS:
                assert label not in body, (path.name, label)
            assert UNSEEN[0] not in body, path.name


def test_a_free_or_lapsed_main_is_classified_identically(tmp_path):
    """Matrix: tier. *Identical behaviour, never gated.* Nothing on this path
    reads a plan or a payment state — asserted here behaviourally, and in
    ``tests/test_crisis.py`` structurally over the whole package."""
    answers = {}

    def answer(work):
        answers[work.prompt.main_id] = work
        return labelled(MAIN_AT_RISK)

    second = SecondOpinion({"paid": Holder(answer), "lapsed": Holder(answer)})
    one = CrisisGate(pipeline=Pipeline(), second=second)
    replies = {
        main: handled(one, UNSEEN[0], main=main, external_id=f"m-{main}")
        for main in ("paid", "lapsed")
    }
    assert replies["paid"] == replies["lapsed"]
    assert set(answers) == {"paid", "lapsed"}
    assert answers["paid"].labels == answers["lapsed"].labels


#: How a logger is reached, whatever the module-level name is.
LOG_METHODS = frozenset({
    "debug", "info", "warning", "error", "exception", "critical", "log",
})

#: The only expressions a log argument here may be: a closed enum, a field
#: holding one, a count, or the main's own id — which is the one identifier the
#: rest of this package already logs and the only way a line names who it is
#: about (AD-22, and the conventions' logging rule).
#: Plus the tally's own integer fields, which are counts by construction — the
#: receiver is unconstrained for the reason the model package's own scan gives:
#: ``failure.kind`` is a ``Kind`` whatever the local is called. Each of these is
#: pinned as an integer by ``test_the_tally_holds_counts_and_nothing_else``.
ALLOWED_LOG_NAMES = frozenset({
    "kind", "because", "value", "main_id",
    "consulted", "answered", "fell_back", "asked", "bound_exceeded", "raised",
    "unreadable", "skipped",
})
CLOSED_ENUMS = frozenset({"Kind", "Reason", "Action"})


def _content_free(argument: ast.expr) -> bool:
    if isinstance(argument, ast.JoinedStr):
        return False  # an f-string interpolates whatever it names
    if isinstance(argument, ast.Constant):
        return True
    if isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name):
        return argument.func.id == "len"
    if isinstance(argument, ast.Name):
        if argument.id in ALLOWED_LOG_NAMES:
            return True
        # A module constant that really is a number. Resolved against the
        # module rather than listed here, so adding a name to the source
        # cannot quietly add it to the allowlist — a constant holding a string
        # is refused exactly like a local would be.
        value = getattr(clf, argument.id, None)
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(argument, ast.Attribute):
        # ``type(exc).__name__`` — the class of a fault, and the *only* part of
        # an exception that may cross. This exact expression rather than any
        # ``__name__``: the whole finding was that a provider's error text
        # quotes the request it rejected, so the message is content and the
        # class is not.
        if (
            argument.attr == "__name__"
            and isinstance(argument.value, ast.Call)
            and isinstance(argument.value.func, ast.Name)
            and argument.value.func.id == "type"
        ):
            return True
        root = argument
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in CLOSED_ENUMS:
            return True
        return argument.attr in ALLOWED_LOG_NAMES
    return False


@pytest.mark.cap12_classifier_property
def test_no_log_call_on_this_path_can_carry_content():
    """Matrix: logs. *No message text, no completion, no label rationale.*

    Structural, because a behavioural test cannot cover it: a log line carrying
    a completion breaks nothing and passes every other case in this file. The
    scan is over the two modules this story writes — the classifier and the
    gate that consults it.
    """
    for relative in ("half/crisis/classifier.py", "half/crisis/gate.py"):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in LOG_METHODS
                    and not isinstance(node.func.value, ast.Constant)):
                continue
            for argument in node.args + [kw.value for kw in node.keywords]:
                assert _content_free(argument), (
                    f"{relative}:{node.lineno} logs an argument that could "
                    "carry content"
                )


@pytest.mark.cap12_classifier_property
def test_the_log_scan_catches_the_spellings_it_exists_for(tmp_path):
    """Non-vacuity. Each of these is a way a completion or a message actually
    reaches a log, and each must be rejected."""
    for source in (
        'logger.info(f"classified {text}")',
        'logger.info("classified %s", work.prompt)',
        'logger.warning("%s", answered.label)',
        'log.error("got " + text)',
        'logger.info("%s", verdict)',
    ):
        node = ast.parse(source).body[0].value
        arguments = node.args + [kw.value for kw in node.keywords]
        assert not all(_content_free(a) for a in arguments), source
    for source in (
        'logger.warning("%s/%s", failure.kind, failure.because)',
        'logger.info("main=%s", main_id)',
        'logger.info("classified %d", len(seen))',
    ):
        node = ast.parse(source).body[0].value
        arguments = node.args + [kw.value for kw in node.keywords]
        assert all(_content_free(a) for a in arguments), source


def test_a_real_turn_logs_no_word_of_what_was_said(caplog):
    """The behavioural half, over the failing path, where a build reaches for
    a diagnostic and a message ends up in a log line."""
    import logging

    caplog.set_level(logging.DEBUG)
    one, _, _ = gate(Failure(Kind.MALFORMED, Reason.NOT_A_LABEL))
    handled(one, UNSEEN[0])
    for record in caplog.records:
        rendered = record.getMessage()
        assert UNSEEN[0] not in rendered
        for label in LABELS:
            assert label not in rendered


# =============================================================================
# the guarantees: no generation, no entering, no authority
# =============================================================================


@pytest.mark.cap12_classifier_property
def test_no_label_may_permit_more_than_a_question():
    """The story's centre, as a property of the table rather than of a branch:
    every value is ``ASK`` or ``NONE``. ``ENTER`` carries a durable thirty-day
    cap, and ``SURFACE`` is a sentence about somebody else."""
    assert set(ACTION_FOR_LABEL) == set(LABELS)
    assert set(ACTION_FOR_LABEL.values()) <= {Action.ASK, Action.NONE}
    assert Action.ASK in set(ACTION_FOR_LABEL.values())


@pytest.mark.parametrize(
    "mutation",
    [
        "import half.crisis.classifier as m;"
        " from half.crisis.signals import Action;"
        " m.ACTION_FOR_LABEL[m.UNSURE] = Action.ENTER; m._check_labels()",
        "import half.crisis.classifier as m;"
        " from half.crisis.signals import Action;"
        " m.ACTION_FOR_LABEL[m.NO_RISK] = Action.SURFACE; m._check_labels()",
        "import half.crisis.classifier as m;"
        " from half.crisis.signals import Action;"
        " m.ACTION_FOR_LABEL = {l: Action.NONE for l in m.LABELS};"
        " m._check_labels()",
        "import half.crisis.classifier as m;"
        " m.ACTION_FOR_LABEL['invented'] = m.Action.ASK; m._check_labels()",
        "import half.crisis.classifier as m; m.INSTRUCTIONS = (); m._check_labels()",
        "import half.crisis.classifier as m;"
        " m.INSTRUCTIONS = ('pick one',); m._check_labels()",
    ],
    ids=["enter", "surface", "widens-nothing", "undefined-label",
         "no-instructions", "labels-undescribed"],
)
@pytest.mark.cap12_classifier_property
def test_the_import_time_check_refuses_each_of_these(mutation):
    """The invariants are raises rather than bare asserts, so ``python -O``
    cannot delete them — and each is exercised, because a check nothing runs is
    a comment."""
    import subprocess
    import sys

    for flags in ([], ["-O"]):
        done = subprocess.run(
            [sys.executable, *flags, "-c", mutation],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert done.returncode != 0, f"{mutation} was accepted with {flags}"
        assert "CrisisError" in done.stderr


@pytest.mark.cap12_classifier_property
def test_the_holder_the_crisis_path_takes_cannot_produce_text():
    """Acceptance: *the classifier's holder has no way to produce text.*

    Checked at the boundary rather than by review: a wider object — a provider
    that can generate, batch, and reach something that would — is refused where
    the narrow one belongs. AD-19's narrow protocol is only worth what the
    check that it really is the narrow one is worth.
    """
    class Provider:
        async def classify(self, work): ...
        async def generate(self, work): ...
        async def submit(self, items): ...
        async def collect(self, submission): ...

    with pytest.raises(CrisisError, match="generate"):
        SecondOpinion({MAIN: Provider()})


#: Ways a wider object arrives. The first six were a denylist this build once
#: carried; the rest are what review round 1 walked through it — a holder that
#: classifies *and* chats, invokes, runs, or is simply callable.
WIDENING_METHODS = (
    "generate", "submit", "collect", "complete", "message", "stream",
    "chat", "invoke", "run", "predict", "ask", "__call__",
)


@pytest.mark.cap12_classifier_property
@pytest.mark.parametrize("method", WIDENING_METHODS)
def test_every_widening_method_is_refused_one_at_a_time(method):
    """An **allowlist**, which is the correction: a denylist of six names let
    ``chat``, ``invoke``, ``run`` and a callable object straight through, and
    each of those is a way to produce text."""
    if method == "__call__":
        class Callable_:
            async def classify(self, work): ...
            def __call__(self): ...

        with pytest.raises(CrisisError, match="callable"):
            SecondOpinion({MAIN: Callable_()})
        return
    holder = Holder(labelled(NO_RISK))
    setattr(holder, method, lambda *a, **k: None)
    with pytest.raises(CrisisError, match=method):
        SecondOpinion({MAIN: holder})


@pytest.mark.cap12_classifier_property
def test_the_allowlist_is_the_one_method_the_port_promises():
    assert ALLOWED_METHODS == {"classify"}


@pytest.mark.cap12_classifier_property
def test_an_object_that_cannot_classify_is_refused_too():
    with pytest.raises(CrisisError, match="classify"):
        SecondOpinion({MAIN: object()})


@pytest.mark.cap12_classifier_property
def test_the_real_narrow_classifier_is_accepted():
    """The other direction: what the port actually hands back must pass. A
    guard that refused the shipped holder would be a guard nobody could use."""
    from half.model.anthropic import AnthropicProvider
    from half.model.tier import Tiers

    class Nothing:
        async def message(self, payload): ...
        async def batch_create(self, requests): ...
        async def batch_status(self, batch_id): ...
        def batch_results(self, batch_id): ...

    provider = AnthropicProvider(
        Nothing(), tiers=Tiers.parse({MAIN: "cheap"}),
        budget=Budget(per_call_micro_usd=PER_CALL_MICRO_USD,
                      per_pass_micro_usd=PER_PASS_MICRO_USD),
    )
    second = SecondOpinion({MAIN: provider.classifier()})
    assert second.holds(MAIN)
    with pytest.raises(CrisisError):
        SecondOpinion({MAIN: provider})


@pytest.mark.cap12_classifier_property
def test_the_holder_is_not_reachable_through_the_object_that_holds_it():
    """A narrow output is half of a narrow holder; the other half is narrow
    authority. Nothing public here hands back the classifier, its transport or
    its ledger — which is the same correction the port made to its own holders
    in review round 1."""
    second, holder = opinion(labelled(NO_RISK))
    public = [name for name in dir(second) if not name.startswith("_")]
    assert sorted(public) == ["consult", "flush", "holds", "tally"]
    assert not hasattr(second, "__dict__"), "slots keep the surface closed"
    for name in public:
        assert getattr(second, name) is not holder


@pytest.mark.cap12_classifier_property
def test_a_second_opinion_is_sealed_after_construction():
    """The check that every holder is the narrow one is worth what it costs to
    walk around it. Rebinding the mapping afterwards was that walk-around, and
    the class docstring claimed the holders were not reachable."""
    second, _ = opinion(labelled(NO_RISK))

    class Wide:
        async def classify(self, work): ...
        async def generate(self, work): ...

    for name, value in (("_holders", {MAIN: Wide()}), ("_bound", 900.0),
                        ("_tally", Tally())):
        with pytest.raises(CrisisError, match="sealed"):
            setattr(second, name, value)
    with pytest.raises(TypeError):
        second._holders[MAIN] = Wide()  # the mapping itself is read-only


@pytest.mark.cap12_classifier_property
def test_nothing_in_the_classifier_module_names_the_mode_at_all():
    """Structural, and the strongest form of *the classifier widens ASK, never
    ENTER*: there is no expression in the module that could produce an entering
    action, a tier, or an assessment. It decides a label; the gate maps it."""
    source = (ROOT / "half/crisis/classifier.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    named = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert "ENTER" not in named, "the classifier module can name entering"
    assert "SURFACE" not in named
    assert "Tier" not in named and "Assessment" not in named


@pytest.mark.cap12_classifier_property
def test_the_gate_reads_only_whether_the_verdict_asks():
    """The other side of the same seam. The gate's own second-opinion method
    consults a verdict's ``asks`` and builds an ``INFERENCE`` assessment — there
    is no branch in it that reads a label, and so no label whose *name* could
    grow a meaning here that the mapping does not give it."""
    tree = ast.parse((ROOT / "half/crisis/gate.py").read_text(encoding="utf-8"))
    method = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_second_opinion"
    )
    attributes = {
        node.attr for node in ast.walk(method) if isinstance(node, ast.Attribute)
    }
    assert "asks" in attributes
    assert "label" not in attributes
    assert "ENTER" not in attributes and "enters" not in attributes


@pytest.mark.cap12_classifier_property
def test_the_bound_is_a_number_this_build_will_accept():
    assert 0 < BOUND_SECONDS <= 30
    for bad in (0, -1, None, "5"):
        with pytest.raises(CrisisError):
            SecondOpinion({}, bound_seconds=bad)


def test_the_running_counts_are_written_out_on_the_failing_path_too(caplog):
    """*A fallback is counted and visible.* A line per event says one call
    failed; it does not say a fifth of them are failing. The summary is what
    makes the rate visible — and it is reached from every path out, because a
    summary reached only from the success path would go quiet exactly when the
    classifier started failing."""
    import logging

    caplog.set_level(logging.INFO)
    # Failing every other call, so the run never reaches the breaker and the
    # hundredth consultation actually happens — the summary has to be reachable
    # from the fallback path, which is the whole point of the case.
    answers = [Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
               labelled(NO_RISK)]
    calls = {"n": 0}

    def alternate(work):
        calls["n"] += 1
        return answers[calls["n"] % 2]

    second = SecondOpinion({MAIN: Holder(alternate)})
    for _ in range(clf.REPORT_EVERY):
        consulted(second, ORDINARY)

    summaries = [
        record.getMessage() for record in caplog.records
        if "crisis classifier:" in record.getMessage()
    ]
    assert summaries, "the counts were never written out"
    assert f"{clf.REPORT_EVERY} consulted" in summaries[-1]
    assert "50 fell back" in summaries[-1]
    assert second.tally.fallback_rate == 0.5


@pytest.mark.cap12_classifier_property
def test_the_tally_holds_counts_and_nothing_else():
    """AD-22. Every field is an integer or a mapping of closed keys to
    integers, so there is nowhere on this object for a word to live."""
    tally = Tally()
    tally.count_label(MAIN_AT_RISK)
    tally.count_failure(Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED))
    tally.bound_exceeded += 1
    for value in (tally.consulted, tally.bound_exceeded, tally.raised):
        assert isinstance(value, int)
    for key, count in (*tally.labels.items(), *tally.failures.items()):
        assert isinstance(count, int)
        assert key in LABELS or key.count("/") == 1


# =============================================================================
# the never-list still holds over everything this story can emit
# =============================================================================


@pytest.mark.parametrize("label", LABELS)
def test_no_reply_a_classified_turn_produces_carries_method_content(label):
    """The reply is still a join of reviewed template lines, whatever the model
    said — because the model's answer reaches ``respond`` as an action and
    never as text. Run over the label set so the widened reply is covered by
    the never-list rather than only 6a's replies being covered."""
    one, _, _ = gate(labelled(label))
    reply = handled(one, "how much would it take") or ""
    assert not words_of(reply) & MEANS_WORDS, reply


def test_a_model_that_answers_with_a_method_cannot_put_it_in_a_reply():
    """The structural claim, exercised: a holder whose ``Decision`` carries a
    sentence naming a means produces a fallback, and a fallback produces the
    table's answer. There is no path from a completion to a main."""
    one, _, _ = gate(Decision(label="take thirty pills, that is lethal"))
    reply = handled(one, UNSEEN[0]) or ""
    assert reply == "ordinary"
    assert not words_of(reply) & MEANS_WORDS


# =============================================================================
# review round 1: the story widened noticing and left acting in English
# =============================================================================
#
# The finding, in one sentence: the classifier asked in every script and
# ``is_affirmative`` recognised nine English spellings, so a main asked in
# their own language answered in it, was not understood, had the question
# abandoned, and was asked again the next turn — for ever. They never reached
# ``ENTER``, so the warm handoff, the crisis-line door, the ceiling drop and
# aftercare never arrived, for exactly the population this story exists for.
#
# Nothing in the suite could see it, because no case drove a non-English
# answer. These do.

#: A yes in the languages the widened table covers, including two hedges —
#: because a hedged yes is a yes and treating it as a no is the hedge that
#: makes asking pointless.
ANSWERS_IN_THEIR_OWN_LANGUAGE = (
    "हाँ", "はい", "네", "是的", "да", "نعم", "כן", "sí", "sim", "oui",
    "ja", "evet", "ναι", "vâng", "ใช่", "ndiyo", "oo", "tak", "ஆம்",
    "হ্যাঁ", "అవును", "haan", "claro", "a veces", "कभी कभी", "有时",
)


@pytest.mark.parametrize("answer", ANSWERS_IN_THEIR_OWN_LANGUAGE)
def test_a_main_asked_in_their_own_language_can_answer_in_it(answer):
    """Matrix: answer in any language. *Recognised — confirmation follows
    recall.*

    The whole sequence, because the halves only fail together: the model reads
    a message the table cannot, Half asks, and the main's own word in their own
    script is what enters. The mode is still opened by a person, by the table,
    offline."""
    one, holder, _ = gate(labelled(MAIN_AT_RISK))
    asked = handled(one, UNSEEN[0], external_id="m0")
    assert templates.ASK.text in asked
    assert not one.in_crisis(MAIN)

    entered = handled(one, answer, external_id="m1")
    assert one.in_crisis(MAIN), answer
    assert templates.OPEN_CONFIRMATION.text in entered
    assert respond.is_templated(entered)
    assert len(holder.seen) == 1, "the answer was sent to a model"


@pytest.mark.parametrize("answer", ANSWERS_IN_THEIR_OWN_LANGUAGE)
def test_confirmation_needs_no_network_in_any_language(answer):
    """The half that matters most. Entering is the table's decision in every
    script, so it survives the outage the classifier does not: with the
    provider down at every step, the question is the table's and so is the
    yes."""
    from half.crisis.signals import is_affirmative

    assert is_affirmative(answer), answer

    one, _, _ = gate(Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED))
    handled(one, "whats the point of any of it", external_id="m0")
    handled(one, answer, external_id="m1")
    assert one.in_crisis(MAIN), answer


def test_the_widened_answers_do_not_fire_on_an_ordinary_reply():
    """The other direction, and the reason four candidates were dropped. A yes
    in twenty scripts must not turn an ordinary sentence into a durable
    thirty-day cap: ``जी`` is a yes *and* a Hindi honorific, so ``नहीं जी`` —
    "no, sir" — read as a yes; ``так`` is Ukrainian for yes and Russian for
    "so"; ``أجل`` is a formal yes and an everyday "for the sake of"; ``jo`` is
    a Nordic yes and an English name."""
    from half.crisis.signals import AFFIRMATIVE_SOURCE, is_affirmative

    for absent in ("जी", "так", "أجل", "jo", "da", "ano", "igen", "ewe"):
        assert absent not in AFFIRMATIVE_SOURCE, absent
    for ordinary in ("नहीं जी", "मैं अब और नहीं जी सकता", "так что я не знаю",
                     "من أجل ذلك", "jo said hello", "leonardo da vinci",
                     "again and again", "i finished the report",
                     "what do you mean", "please stop", "why do you ask"):
        assert not is_affirmative(ordinary), ordinary


def test_the_classifier_never_reads_the_answer_to_halfs_own_question():
    """*Letting a model decision reach ENTER* is Ask-First, and this is where
    it would arrive by the back door. The turn that enters the mode is decided
    by the table alone: with a standing question, no message is sent anywhere,
    whatever the model would have said."""
    for answer in ANSWERS_IN_THEIR_OWN_LANGUAGE[:6]:
        one, holder, _ = gate(labelled(MAIN_AT_RISK))
        handled(one, "whats the point of any of it", external_id="a0")
        handled(one, answer, external_id="a1")
        assert one.in_crisis(MAIN), answer
        assert holder.seen == [], answer


# =============================================================================
# matrix: a slow model, and everybody else
# =============================================================================


def test_a_hanging_provider_does_not_delay_another_mains_safe_word(tmp_path):
    """Matrix: slow model, other mains. *No other main's turn is delayed; a
    safe word is immediate.*

    The measurement that found this: a hanging holder, three messages, two
    mains — replies at +5.01s, +10.01s and +10.01s, with a **safe word**
    answered ten seconds late behind two turns that were not that main's.
    Story 6a's guarantee is that the safe word is decided offline with the
    provider down, and one sequential inbound loop made that true only for the
    message at the head of the queue.
    """
    registry = ActorRegistry(tmp_path / "mains")
    second = SecondOpinion({"vidit": Holder(labelled(NO_RISK), sleep=5.0)},
                           bound_seconds=0.5)
    transport = TimedTransport([
        msg(text=ORDINARY, message_id="r0", chat_id="123", date=AT),
        msg(text=ORDINARY, message_id="r1", chat_id="123", date=AT),
        msg(text=SAFE_WORD, message_id="r2", chat_id="456", date=AT),
    ])
    channel = TelegramChannel(
        transport=transport, mains={"123": "vidit", "456": "asha"}
    )
    started = time.monotonic()
    asyncio.run(Runtime(channel=channel, registry=registry, second=second).run())
    asha_open = registry.crisis_open("asha")
    registry.close()

    by_main: dict[str, float] = {}
    for chat, _, at in transport.timed:
        by_main.setdefault(chat, at - started)
    assert set(by_main) == {"123", "456"}, transport.timed
    assert asha_open, "the safe word did not enter the mode"
    assert by_main["456"] < by_main["123"], (
        f"a safe word was answered at {by_main['456']:.2f}s, after the "
        f"classified main's {by_main['123']:.2f}s; the offline floor is only "
        "offline for whoever is first in the queue. Compared against the other "
        "main rather than against a wall-clock threshold: the property is that "
        "the safe word does not wait behind somebody else's provider, and a "
        "loaded runner makes every absolute number wrong without making the "
        "property false."
    )
    assert transport.timed[0][0] == "456", (
        "the main whose turn needed no network was answered second"
    )
    # And the main who *is* being classified still pays their own bound, twice,
    # one turn after the other — per main it is exactly what it was.
    assert transport.timed[-1][2] - started >= 0.9, transport.timed


def test_one_mains_turns_still_happen_one_at_a_time_and_in_order(tmp_path):
    """The half of the sequential loop that had to survive. Per main it is
    unchanged: a FIFO queue and one worker, so two messages from one person
    cannot overtake each other or reach that main's store at once (AD-1)."""
    order: list[str] = []

    class Watching:
        def __init__(self) -> None:
            self.seen: list[Classify] = []
            self.inflight = 0

        async def classify(self, work: Classify) -> Classified:
            self.seen.append(work)
            self.inflight += 1
            order.append(f"start-{len(self.seen)}")
            if self.inflight > 1:
                raise AssertionError("two turns for one main overlapped")
            await asyncio.sleep(0.01)
            self.inflight -= 1
            order.append(f"end-{len(self.seen)}")
            return labelled(NO_RISK)

    registry = ActorRegistry(tmp_path / "mains")
    drive(registry, SecondOpinion({MAIN: Watching()}),
          [(f"message {i}", AT) for i in range(4)])
    registry.close()
    assert order == ["start-1", "end-1", "start-2", "end-2",
                     "start-3", "end-3", "start-4", "end-4"], order


def test_a_cancelled_turn_does_not_end_the_inbound_loop(tmp_path):
    """Matrix: cancellation. *The loop survives — never ends the inbound loop.*

    ``CancelledError`` is a ``BaseException`` and ``consult`` deliberately does
    not catch it: swallowing a cancellation is how a shutdown stops working.
    What keeps one turn's cancellation from ending everybody's conversation is
    that turns are dispatched per main and each worker asks *whose*
    cancellation it is — a shutdown is re-raised, and a turn that cancelled
    itself costs one turn.
    """
    class Cancelling:
        def __init__(self) -> None:
            self.seen: list[Classify] = []

        async def classify(self, work: Classify) -> Classified:
            self.seen.append(work)
            if len(self.seen) == 1:
                raise asyncio.CancelledError()
            return labelled(NO_RISK)

    holder = Cancelling()
    registry = ActorRegistry(tmp_path / "mains")
    replies = drive(registry, SecondOpinion({MAIN: holder}),
                    [(ORDINARY, AT), (ORDINARY, AT), (SAFE_WORD, AT)])
    opened = registry.crisis_open(MAIN)
    registry.close()

    assert len(holder.seen) == 2, "the loop stopped classifying after a cancel"
    assert opened, "the safe word never arrived; the queue died with the turn"
    assert len(replies) >= 2, replies


# =============================================================================
# matrix: a provider's own error text
# =============================================================================


#: What a provider says when it rejects a request: the request, quoted back.
#: This exact shape is why nothing on this path calls ``logger.exception`` —
#: the traceback carries it, and neither log guard saw it, because the AST scan
#: reads the *arguments* and a behavioural test built from a ``Failure`` value
#: never raises at all.
QUOTING_FAULT = "400 bad_request: messages.0.content: 'मैं अब और नहीं जी सकता'"


def test_a_provider_error_that_quotes_the_request_does_not_reach_a_log(caplog):
    """Matrix: provider error text. *The class only reaches the log — never the
    main's words.*"""
    import logging

    caplog.set_level(logging.DEBUG)
    one, _, _ = gate(RuntimeError(QUOTING_FAULT))
    assert handled(one, UNSEEN[0]) == "ordinary"

    emitted = "\n".join(
        record.getMessage() + (record.exc_text or "") for record in caplog.records
    )
    assert "मैं अब और नहीं जी सकता" not in emitted, emitted
    assert QUOTING_FAULT not in emitted
    assert "RuntimeError" in emitted, "the class of the fault must still cross"


def test_the_same_holds_when_the_gate_itself_is_the_one_that_catches(caplog):
    """The gate's own handler, which is the second place a traceback would be
    written. ``consult`` answers rather than raising, so this needs a broken
    second opinion to reach — and it must be as quiet as the first."""
    import logging

    class Detonating:
        def holds(self, main_id):
            return True

        async def consult(self, text, *, main_id):
            raise RuntimeError(QUOTING_FAULT)

    caplog.set_level(logging.DEBUG)
    one = CrisisGate(pipeline=Pipeline(), second=Detonating())
    assert handled(one, UNSEEN[0]) == "ordinary"
    emitted = "\n".join(
        record.getMessage() + (record.exc_text or "") for record in caplog.records
    )
    assert "मैं अब और नहीं जी सकता" not in emitted
    assert "RuntimeError" in emitted


@pytest.mark.cap12_classifier_property
def test_no_crisis_module_logs_a_traceback_at_all():
    """The structural half, over the whole package rather than the two modules
    this story wrote. A traceback is the exception's own text, and on these
    paths that text is a rejected request, a line of a safety plan, or a
    contact's name. So the rule is mechanical: nothing under ``half/crisis``
    calls ``logger.exception`` or passes ``exc_info``, and a caught fault
    contributes its class name and nothing else.
    """
    offenders: list[str] = []
    for path in sorted((ROOT / "half/crisis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr == "exception":
                offenders.append(f"{path.name}:{node.lineno} logger.exception")
            if node.func.attr in LOG_METHODS and any(
                kw.arg == "exc_info" for kw in node.keywords
            ):
                offenders.append(f"{path.name}:{node.lineno} exc_info")
    assert not offenders, offenders


# =============================================================================
# matrix: the safety-plan turn
# =============================================================================


#: A plan the way a main dictates one, carrying exactly what a plan carries:
#: the people they would ring, a clinician, a number, and step six.
PLAN_TURN = (
    "here is my safety plan\n"
    "Ring आशा on 98765 43210, she knows.\n"
    "Dr Rao takes messages on Tuesdays.\n"
    "Give the spare keys and the tablets to my brother."
)


@pytest.mark.parametrize(
    "text",
    [PLAN_TURN, "can you show me my safety plan", "whats my safety plan again"],
    ids=["intake", "request", "request-2"],
)
def test_a_safety_plan_turn_is_not_classified_and_not_sent(text):
    """Matrix: safety-plan turn. *Not classified, not sent — already sensitive
    by design.*

    ``test_only_the_message_text_leaves_the_machine`` proves a contact in the
    *store* does not go. This is the route that would actually put a named
    person and a phone number in a payload: the main typing one. A
    classification could not change what a plan turn does, so it is not made.
    """
    one, holder, _ = gate(labelled(MAIN_AT_RISK))
    handled(one, text)
    assert holder.seen == [], "a safety-plan turn was sent to a provider"


def test_the_plan_turn_still_does_everything_it_did(tmp_path):
    """Skipping the classification changes nothing else about that turn: the
    document is taken, and it comes back whole when it is asked for."""
    root = tmp_path / "mains"
    (root / MAIN).mkdir(parents=True)
    registry = ActorRegistry(root)
    replies = drive(registry, SecondOpinion({MAIN: Holder(labelled(NO_RISK))}),
                    [(PLAN_TURN, AT), ("can you show me my safety plan", AT)])
    registry.close()
    assert "Ring आशा on 98765 43210, she knows." in replies[-1]


# =============================================================================
# matrix: the oversized message
# =============================================================================


class Counting:
    """A transport that counts, so *refused before the transport is touched* is
    asserted at the wire rather than from below.

    It answers rather than raising, because a raise would be swallowed into a
    fallback and the case would pass whether or not the call was made.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def message(self, payload):
        self.calls += 1
        return {
            "content": [{"type": "text", "text": '{"label": "no_risk"}'}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 5},
        }

    async def batch_create(self, requests): ...
    async def batch_status(self, batch_id): ...
    def batch_results(self, batch_id): ...


def _real_classifier(transport):
    from half.model.anthropic import AnthropicProvider
    from half.model.tier import Tiers

    return AnthropicProvider(
        transport, tiers=Tiers.parse({MAIN: CLASSIFY_TIER}),
        budget=Budget(per_call_micro_usd=PER_CALL_MICRO_USD,
                      per_pass_micro_usd=PER_PASS_MICRO_USD),
    ).classifier()


def test_a_message_past_the_ceiling_is_refused_before_the_transport():
    """Matrix: oversized message. *Refused before the transport is touched,
    counted as a fallback.*

    The ceiling was pinned only from below, so it could be loosened five
    thousand-fold with the suite green — after which a megabyte of somebody's
    text goes over the wire whole. This drives the real provider over a
    transport that counts.
    """
    transport = Counting()
    second = SecondOpinion({MAIN: _real_classifier(transport)})
    verdict = consulted(second, "मैं " * 400_000)

    assert transport.calls == 0, "an oversized message reached the provider"
    assert verdict.fell_back and not verdict.asks
    assert second.tally.failures == {"over-budget/per-call-budget": 1}
    assert second.tally.fallback_rate == 1.0


def test_an_ordinary_message_does_reach_the_transport():
    """Non-vacuity for the row above: a ceiling that refused everything would
    pass it while removing the classifier entirely."""
    transport = Counting()
    second = SecondOpinion({MAIN: _real_classifier(transport)})
    verdict = consulted(second, ORDINARY)
    assert transport.calls == 1, "an ordinary message never reached the provider"
    assert not verdict.fell_back and verdict.label == NO_RISK


# =============================================================================
# matrix: the wiring, by value
# =============================================================================


def test_serve_hands_the_runtime_the_classifier_build_made(tmp_path, monkeypatch):
    """Matrix: wiring. *The runtime holds the classifier ``build`` made — by
    value, not by keyword.*

    The previous version asserted that a keyword called ``second`` appeared in
    the call, which passes with ``second=None`` in it. That is
    ``test_schedule.py``'s own documented grep bug in AST clothing, one story
    on. This runs ``serve`` and reads the object the runtime was given.
    """
    import half.__main__ as entrypoint

    captured: dict[str, object] = {}
    made: dict[str, object] = {}

    class Recording:
        def __init__(self, *, channel, registry, second=None, questions=None,
                     corrections=None):
            captured["second"] = second
            # Story 12: and the correction widening, for the same reason.
            captured["corrections"] = corrections
            # Story 11: the runtime is also the only asker, so ``serve`` hands
            # it the engine ``build`` made. Captured here rather than ignored,
            # so a wiring that stopped passing it fails by name.
            captured["questions"] = questions

        async def run(self):
            return None

    real_build = entrypoint.build

    def build_and_remember(config, token):
        wiring = real_build(config, token)
        made["wiring"] = wiring
        return wiring

    monkeypatch.setattr(entrypoint, "build", build_and_remember)
    monkeypatch.setattr(entrypoint, "Runtime", Recording)

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    asyncio.run(entrypoint.serve(config, "123:fake"))

    assert isinstance(captured["second"], SecondOpinion)
    assert captured["second"] is made["wiring"].second
    # Story 11: and the question engine, for the same reason — a surface
    # reachable only from a test is a surface nobody has run.
    assert captured["questions"] is made["wiring"].questions


# =============================================================================
# matrix: the corrupt credential
# =============================================================================


def test_a_corrupt_credential_file_leaves_the_process_running(tmp_path):
    """Matrix: corrupt credential. *That main is unequipped; the process
    starts — never a dead safe word.*

    This is the first read of the secret store at boot. ``FileSecretStore.get``
    raises ``StoreError`` on an unreadable file, which is a ``HalfError`` and
    not a ``ModelError``, so the previous handler let it out: ``build`` raised,
    ``main`` exited 2, and every main in the deployment lost the channel, the
    gate and the offline safe word because of one bad file.
    """
    from half.secrets import FileSecretStore

    root = tmp_path / "mains"
    root.mkdir()
    secrets = FileSecretStore.beside(root)
    secrets.put("vidit", "model_api_key", "sk-fine")
    secrets.put("asha", "model_api_key", "sk-also-fine")
    broken = [p for p in Path(secrets.root).rglob("*asha*") if p.is_file()]
    assert broken, "the credential file was not found to corrupt"
    broken[0].write_text("{not json", encoding="utf-8")

    config = load({ROOT_ENV: str(root), MAINS_ENV: "123:vidit, 456:asha"})
    wiring = build(config, token="123:fake")
    try:
        assert wiring.second.holds("vidit"), "a good main was unequipped too"
        assert not wiring.second.holds("asha")
    finally:
        wiring.registry.close()


def test_a_holder_the_crisis_path_refuses_does_not_kill_the_boot(tmp_path, monkeypatch):
    """The same rule one layer up: if the narrow-holder check ever refused what
    the composition root built, the deployment must still start with the phrase
    table rather than not start at all."""
    import half.__main__ as entrypoint

    class Wide:
        async def classify(self, work): ...
        async def generate(self, work): ...

    class Fake:
        def classifier(self):
            return Wide()

    monkeypatch.setattr(entrypoint, "AnthropicProvider", lambda *a, **k: Fake())
    monkeypatch.setattr(
        entrypoint.SDKTransport, "from_secrets",
        classmethod(lambda cls, secrets, main_id: object()),
    )

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    try:
        assert not wiring.second.holds("vidit")
    finally:
        wiring.registry.close()


def test_every_main_is_classified_on_the_same_tier(tmp_path):
    """CAP-12 is never gated by tier, so detection quality may not follow what
    somebody pays. A main is equipped by having a key; the tier the classifier
    runs on is pinned for everybody, and a main's conversation tier does not
    reach it — requiring a ``HALF_MODEL_TIERS`` entry was the same gate wearing
    configuration's clothes.

    That the pinned tier is the right one — that it detects well enough, in
    every script — is a question for the reviewer and an evaluation set, and no
    arrangement of green cases answers it."""
    from half.config import TIERS_ENV
    from half.model.tier import Tier as ModelTierEnum
    from half.secrets import FileSecretStore

    assert CLASSIFY_TIER in {str(tier) for tier in ModelTierEnum}

    root = tmp_path / "mains"
    root.mkdir()
    store = FileSecretStore.beside(root)
    for main in ("vidit", "asha"):
        store.put(main, "model_api_key", "sk-fine")

    # One main on the frontier tier, one with no tier configured at all.
    config = load({ROOT_ENV: str(root), MAINS_ENV: "123:vidit, 456:asha",
                   TIERS_ENV: "vidit:frontier"})
    wiring = build(config, token="123:fake")
    try:
        assert wiring.second.holds("vidit") and wiring.second.holds("asha")
    finally:
        wiring.registry.close()


# =============================================================================
# the breaker, and what an operator sees
# =============================================================================


def test_a_run_of_failures_stops_the_asking_rather_than_repeating_it():
    """During an outage every turn would otherwise pay the full bound and then
    issue another doomed request — the latency and the spend of asking a
    question nobody is answering. Counted in turns, because nothing under
    ``half/crisis`` reads a clock."""
    second, holder = opinion(Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED))
    for _ in range(BREAK_AFTER):
        consulted(second, ORDINARY)
    assert len(holder.seen) == BREAK_AFTER
    assert second.tally.consulted == BREAK_AFTER

    for _ in range(BREAK_FOR):
        assert consulted(second, ORDINARY).fell_back
    assert len(holder.seen) == BREAK_AFTER, "the breaker kept calling"
    assert second.tally.skipped == BREAK_FOR
    assert second.tally.consulted == BREAK_AFTER, "a skip counted as a call"


def test_the_breaker_tries_again_and_clears_when_it_works():
    """A breaker that never closed again would be an outage that removed the
    classifier permanently — the silent degradation, arriving as a fix."""
    answers = [Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)] * BREAK_AFTER
    answers += [labelled(MAIN_AT_RISK)] * 10
    second = SecondOpinion({MAIN: Holder(lambda work: answers.pop(0))})
    for _ in range(BREAK_AFTER + BREAK_FOR):
        consulted(second, ORDINARY)
    assert consulted(second, UNSEEN[0]).asks, "the breaker never closed"
    assert second.tally.answered >= 1


def test_the_breaker_is_one_mains_and_not_the_deployments():
    """One main's provider being down says nothing about another's, and a
    global breaker would silently take the classifier away from everybody
    because of one bad key."""
    down = Holder(Failure(Kind.REFUSED, Reason.NOT_AUTHORISED))
    up = Holder(labelled(MAIN_AT_RISK))
    second = SecondOpinion({"vidit": down, "asha": up})
    for _ in range(BREAK_AFTER + 3):
        consulted(second, ORDINARY, main="vidit")
    assert consulted(second, UNSEEN[0], main="asha").asks
    assert len(up.seen) == 1


def test_a_failing_classifier_is_loud_before_it_is_round(caplog):
    """*A fallback is counted and visible.* Every hundred consultations is not
    good enough on its own: a wholly failing classifier would be silent until
    it reached a round number. So the counts also go out at error level once
    the rate is evidence rather than arithmetic."""
    import logging

    caplog.set_level(logging.INFO)
    second, _ = opinion(Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED))
    for _ in range(ALARM_AFTER):
        consulted(second, ORDINARY)

    alarms = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert alarms, "a wholly failing classifier said nothing at error level"
    assert second.tally.fallback_rate >= ALARM_RATE


def test_the_counts_can_be_written_out_on_the_way_down(caplog):
    """A process that ran for a week and never reached a round number still has
    to say what it did. ``serve`` calls this in its ``finally``."""
    import logging

    caplog.set_level(logging.INFO)
    second, _ = opinion(labelled(NO_RISK))
    consulted(second, ORDINARY)
    caplog.clear()
    second.flush()
    assert any("crisis classifier:" in r.getMessage() for r in caplog.records)


@pytest.mark.cap12_classifier_property
def test_serve_writes_the_counts_out_on_the_way_down():
    import half.__main__ as entrypoint

    tree = ast.parse(Path(entrypoint.__file__).read_text(encoding="utf-8"))
    serve = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "serve"
    )
    flushes = [
        node for node in ast.walk(serve)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "flush"
    ]
    assert flushes, "serve never writes the classifier's counts out"


# =============================================================================
# the outcomes that were quietly miscounted
# =============================================================================


@pytest.mark.cap12_classifier_property
def test_a_fallback_that_asks_cannot_be_constructed():
    """The outage-asks-everyone failure, made unrepresentable rather than
    avoided by every caller remembering."""
    with pytest.raises(CrisisError, match="fallback cannot ask"):
        Verdict(Action.ASK, fell_back=True)
    with pytest.raises(CrisisError):
        Verdict(Action.ENTER)
    with pytest.raises(CrisisError):
        Verdict(Action.SURFACE)


def test_an_answer_that_breaks_the_ports_contract_is_counted_as_a_fallback():
    """Reproduced in review: ``Decision(label=["main_at_risk"])`` raised inside
    ``_verdict``, which was called from the ``else:`` of the try — outside both
    handlers — so ``consulted`` was incremented and nothing was counted against
    it. The one number an operator watches understated failure on exactly the
    failing path."""
    second, _ = opinion(Decision(label=["main_at_risk"]))
    verdict = consulted(second, UNSEEN[0])
    assert verdict.fell_back
    assert second.tally.consulted == 1
    assert second.tally.fell_back == 1
    assert second.tally.fallback_rate == 1.0


def test_a_broken_contract_is_counted_apart_from_a_holder_that_threw():
    """``bound_exceeded`` was separated from a transport fault because the two
    want different responses. A provider that answers with something unreadable
    and a build that raises want different responses for the same reason."""
    unreadable, _ = opinion(Decision(label="not-a-label-in-any-build"))
    consulted(unreadable, ORDINARY)
    assert unreadable.tally.unreadable == 1 and unreadable.tally.raised == 0

    threw, _ = opinion(RuntimeError("no tier for this main"))
    consulted(threw, ORDINARY)
    assert threw.tally.raised == 1 and threw.tally.unreadable == 0
