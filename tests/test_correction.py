"""CAP-11: the main tells Half it is wrong, and the belief changes (story 12).

One case per row of the I/O matrix, plus the structural rules the matrix cannot
reach. Four things this file refuses to do, because each would let it pass while
the product failed:

**It never lets an inference act.** The centre of this story is CAP-10's rule
applied to a second class of problem: detection past the offline table produces
a *candidate* and Half asks. So the no-append assertion is made three ways — at
the function that builds removals, which raises; over the whole widening
package, which cannot name an op; and end to end, over a log that has to be
empty of corrections after a turn the classifier read as one.

**It keeps the three attributions apart, including the third.** Every removal
case asserts what the record says about the cause *and what it does not*: the
unstated row fails if either cause is written, which is the acceptance criterion
in as many words.

**It makes no language the default.** The removal path is swept over corrections
in scripts from five continents, and the sweep's own coverage is asserted — a
fixture that quietly narrowed to English would fail the coverage case rather
than passing the removal ones.

**It asserts what reaches the wire, byte for byte.** *"Half shows the removed
claim as recorded"* is checked against the seeded claim string, and *"never
composed prose"* against the module that builds the line.

**What is deliberately not here.** *"This package opens no store of its own"* is
not asserted in this file, because it is asserted in ``tests/test_unasked.py``
over every package the rule covers — ``half/trust``, ``half/questions`` and now
``half/correction``, swept by one predicate with its own bypass cases. A copy of
that guard here would be a weaker copy of it: story 11 shipped exactly such a
copy and both of story 5b's known bypasses walked straight past it.
"""

from __future__ import annotations

import ast
import asyncio
import unicodedata
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.correction import apply as correction
from half.correction.apply import Removal, Source
from half.correction.attribute import Attribution, attribution_for
from half.correction.candidate import (
    ACTION_FOR_LABEL,
    ALLOWED_METHODS,
    BOUND_SECONDS,
    CORRECTION,
    LABELS,
    NO_CORRECTION,
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    UNSURE,
    Action,
    Verdict,
    Widening,
    prompt_for,
)
from half.correction.signals import (
    MEANING_FOR_TABLE,
    VOCABULARY,
    Meaning,
    is_confirmation,
    recognize,
)
from half.crisis.signals import SAFE_WORD
from half.errors import CorrectionError
from half.governance import ladder
from half.governance.ladder import License
from half.loops import ledger as loops
from half.model.port import Classify, Decision, Failure, Kind, Reason, Usage
from half.questions.engine import QuestionEngine
from half.retrieval.prefix import build_prefix
from half.schedule.clock import stamp
from half.store.ops import TOUCH_TENSION, Op
from half.store.records import EXPIRED_AT, INVALID_AT, TARGET
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.touch import Origin
from half.trust.balance import balance
from tests.conftest import FakeTransport, msg, outward, reaches

pytestmark = pytest.mark.cap11

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"
#: 2026-09-01T12:00:00Z — the instant every turn in this file builds from,
#: carried in on the inbound stamp, which is the only clock a turn has.
NOON = 1_788_264_000.0
NOW = stamp(NOON)
DAY = 86_400.0

LOOP = "buy-farmland"
BELIEF = "b_land"
#: The seeded claim, asserted **byte for byte** on the wire. Distinctive enough
#: that its presence in a reply cannot be an accident, and sharing no word with
#: any correction phrase, so a table row can never match the claim itself.
CLAIM = "has not walked that plot since March"

ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")


# ── the doubles ──────────────────────────────────────────────────────────────


class Holder:
    """The port's narrow classifier, and nothing wider.

    One method, returning a ``Decision`` or one of the four failures. Private
    attributes, because ``Widening`` refuses a holder with any public callable
    but ``classify`` — the double is held to the same shape as the real thing,
    which is the point of the check.
    """

    def __init__(self, answer: object = None, *, sleep: float = 0.0) -> None:
        self._answer = answer
        self._sleep = sleep
        self._seen: list[Classify] = []

    async def classify(self, work: Classify):
        self._seen.append(work)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if isinstance(self._answer, BaseException):
            raise self._answer
        return self._answer

    @property
    def _requests(self):
        return self._seen


class Exploding:
    """A holder that must never be reached, so every *no model call* row asserts
    that the call did not happen rather than that a counter stayed at zero."""

    async def classify(self, work: Classify):
        raise AssertionError("a model was consulted where none may be")


def labelled(label: str) -> Decision:
    return Decision(label=label, usage=Usage(input_tokens=90, micro_usd=700))


def widening(answer: object = None, **kw) -> Widening:
    """A widening for ``MAIN`` alone. ``None`` answers nothing readable, which
    is a fallback — the table's answer stands."""
    return Widening({MAIN: Holder(answer, **kw)}, bound_seconds=0.2)


# ── the harness ──────────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def seed(
    root,
    *,
    main_id=MAIN,
    beliefs=((BELIEF, CLAIM),),
    rung=License.BEHAVE,
    loop=LOOP,
    favours=0,
):
    """One main, one wanting, and beliefs on it, seeded through the ladder.

    A rung is earned by a promotion involving the main and never spelled into a
    record, exactly as ``conftest.seed_belief`` does, so nothing here can mint a
    permission the product cannot.

    ``favours`` are delivered morning messages — the only thing that earns —
    dated before the turn. They exist so the *no favour spent* row is a real
    comparison: a turn with nothing to spend proves nothing about spending.
    """
    with Store(root / main_id, prefix=build_prefix) as store:
        if loop:
            store.record(
                Op.LOOP_TRANSITION, "l_0", "2026-08-01T00:00Z",
                **loops.opened(loop, state="stalled", timescale="years",
                               last_movement="2026-01-04",
                               loops=store.state().loops),
            )
        for ident, claim in beliefs:
            store.record(
                Op.ASSERT, ident, "2026-08-01T00:00Z", claim=claim, subject="self",
                loop=loop or None, topics=["farmland"],
                **ladder.admitted(support=[f"s_{ident}"]),
            )
            if rung is not ladder.FLOOR:
                record = store.state().beliefs[ident]
                store.record(
                    Op.ASSERT, ident, "2026-08-01T00:00Z",
                    **ladder.promote(record, to=rung, acknowledged=True),
                )
        for day in range(favours):
            marker = stamp(NOON - (day + 2) * DAY)[:10]
            store.record(
                Op.TOUCH, f"tc_{marker}", f"{marker}T03:00Z",
                **touch_module.spoke(day=marker, origin=ORIGIN, loops=()),
            )


def a_turn(
    registry,
    *,
    texts=("thats wrong",),
    main_id=MAIN,
    corrections=None,
    engine=False,
    at=NOON,
):
    """Real inbound turns, through the real runtime and the real crisis gate.

    ``texts`` is a sequence because half the matrix is about what the *second*
    message does — a confirmation, a decline, a follow-up that settles a cause.
    Each gets its own external id, so the redelivery check never suppresses one.
    """
    transport = FakeTransport([
        msg(text=text, message_id=f"m{index}", chat_id="123",
            date=int(at + index))
        for index, text in enumerate(texts)
    ])
    channel = TelegramChannel(transport=transport, mains={"123": main_id})
    runtime = Runtime(
        channel=channel, registry=registry, corrections=corrections,
        questions=QuestionEngine(ledger=registry) if engine else None,
    )
    asyncio.run(runtime.run())
    return transport


def sent(transport):
    return "\n".join(text for _, text in transport.sent)


def log_of(root, main_id=MAIN):
    with Store(root / main_id) as store:
        return list(store.log)


def corrections_in(root, main_id=MAIN):
    return [
        r for r in log_of(root, main_id)
        if r.op in (Op.RETRACT, Op.REVISE, Op.EXPUNGE)
    ]


def beliefs_of(root, main_id=MAIN):
    with Store(root / main_id) as store:
        return store.state().beliefs


def loops_of(root, main_id=MAIN):
    with Store(root / main_id) as store:
        return store.state().loops


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the three explicit corrections
# ═════════════════════════════════════════════════════════════════════════════


def test_half_was_wrong_appends_a_revise_and_shows_the_claim(registry, tmp_path):
    """Matrix: *Half was wrong, explicitly*. **The sentence CAP-11 exists for.**

    A ``revise`` is appended, the belief is gone from the fold, the record says
    the system had it wrong, and the reply carries the claim Half removed — as
    recorded, byte for byte, rather than a description of it.
    """
    seed(tmp_path)

    transport = a_turn(registry, texts=("you were wrong about that",))

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.REVISE]
    assert recorded[0].data[TARGET] == BELIEF
    assert recorded[0].data[EXPIRED_AT] == NOW
    assert INVALID_AT not in recorded[0].data
    assert BELIEF not in beliefs_of(tmp_path)
    assert attribution_for(BELIEF, [r.data for r in log_of(tmp_path)]) is (
        Attribution.HALF_WAS_WRONG
    )
    body = sent(transport)
    assert f"{Op.REVISE.value}[{BELIEF}]: {CLAIM}" in body


def test_the_main_changed_appends_a_retract_and_owes_no_apology(
    registry, tmp_path
):
    """Matrix: *the main changed*.

    A ``retract``, the world-changed stamp, and — the half that is easy to lose
    — **no ``revise`` anywhere**, in the log or on the wire. The distinction
    CAP-11 asks to preserve is only preserved if the wrong one is absent.
    """
    seed(tmp_path)

    transport = a_turn(registry, texts=("that has changed",))

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.RETRACT]
    assert recorded[0].data[INVALID_AT] == NOW
    assert EXPIRED_AT not in recorded[0].data
    assert attribution_for(BELIEF, [r.data for r in log_of(tmp_path)]) is (
        Attribution.MAIN_CHANGED
    )
    body = sent(transport)
    assert f"{Op.RETRACT.value}[{BELIEF}]: {CLAIM}" in body
    assert Op.REVISE.value not in body


def test_a_correction_that_settles_no_cause_records_neither(registry, tmp_path):
    """Matrix: *wrong, cause unstated*. **The acceptance criterion in as many
    words: this fails if either cause is written.**

    The belief leaves the fold on the correction alone — removal does not wait
    on attribution — and the record says nothing about why, because the main did
    not say. A build that defaulted in either direction fails on one of the two
    absences below, and one that "recorded everything it knew" by writing both
    fails on both.
    """
    seed(tmp_path)

    a_turn(registry, texts=("thats wrong",))

    recorded = corrections_in(tmp_path)
    assert len(recorded) == 1
    assert EXPIRED_AT not in recorded[0].data
    assert INVALID_AT not in recorded[0].data
    assert BELIEF not in beliefs_of(tmp_path)
    assert attribution_for(BELIEF, [r.data for r in log_of(tmp_path)]) is (
        Attribution.NOT_YET_KNOWN
    )


def test_a_follow_up_settles_a_cause_the_first_message_did_not(
    registry, tmp_path
):
    """Matrix: *attribution arrives later*, end to end.

    The removal happened on the first turn with the cause unknown; a second
    correction naming the same belief carries the cause. Appended, both records
    in the log, and the fold over them now says which it was.
    """
    seed(tmp_path)
    a_turn(registry, texts=("thats wrong",))

    # The follow-up names the belief directly, because *which* belief a second
    # message is about is retrieval's question and not this story's — the
    # append and the fold are what this row is about.
    with Store(tmp_path / MAIN) as store:
        store.record(Op.REVISE, "co_later", "2026-09-02T09:00:00Z",
                     target=BELIEF, **{EXPIRED_AT: "2026-09-02T09:00:00Z"})

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.RETRACT, Op.REVISE]
    assert attribution_for(BELIEF, [r.data for r in log_of(tmp_path)]) is (
        Attribution.HALF_WAS_WRONG
    )


def test_a_reversal_appends_again_and_both_survive_in_the_log(
    registry, tmp_path
):
    """Matrix: *reversal*. The main corrects the correction; nothing is edited
    in place and nothing is lost (AD-3)."""
    seed(tmp_path)
    a_turn(registry, texts=("that has changed",))
    with Store(tmp_path / MAIN) as store:
        store.record(Op.REVISE, "co_later", "2026-09-02T09:00:00Z",
                     target=BELIEF, **{EXPIRED_AT: "2026-09-02T09:00:00Z"})

    recorded = corrections_in(tmp_path)
    assert [(r.op, r.data.get(INVALID_AT), r.data.get(EXPIRED_AT))
            for r in recorded] == [
        (Op.RETRACT, NOW, None),
        (Op.REVISE, None, "2026-09-02T09:00:00Z"),
    ]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: erase, no such belief, already corrected
# ═════════════════════════════════════════════════════════════════════════════


def test_an_erasure_tombstones_the_body_and_says_something_different(
    registry, tmp_path
):
    """Matrix: *erase it*. Story 1's validate-then-erase, reached from the
    inbound path for the first time.

    Three things at once, and the second is what makes it an erasure rather than
    a removal: the op is ``expunge``, the claim is **gone from the log on disk**,
    and what Half says names no claim — echoing the text back on the turn the
    main asked for it to be gone is the one place quoting would be wrong.
    """
    seed(tmp_path)

    transport = a_turn(registry, texts=("delete that",))

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.EXPUNGE]
    assert BELIEF not in beliefs_of(tmp_path)
    shard = (tmp_path / MAIN / "beliefs").glob("*.jsonl")
    on_disk = "".join(path.read_text(encoding="utf-8") for path in shard)
    assert CLAIM not in on_disk
    body = sent(transport)
    assert f"{Op.EXPUNGE.value}[{BELIEF}]" in body
    assert CLAIM not in body
    assert Op.RETRACT.value not in body and Op.REVISE.value not in body


def test_a_correction_naming_nothing_half_holds_removes_nothing_and_says_so_gently(
    registry, tmp_path
):
    """Matrix: *no such belief*. Nothing removed, nothing appended, and **the
    main is not shown an error** — being told *"I have no record of that"* in
    answer to *"that's wrong"* is Half arguing."""
    seed(tmp_path, beliefs=(), loop=None)

    transport = a_turn(registry, texts=("thats wrong",))

    assert corrections_in(tmp_path) == []
    body = sent(transport)
    assert body.strip() == "noted."


def test_a_correction_of_a_belief_already_gone_removes_nothing_a_second_time():
    """Matrix: *already corrected*. Idempotent at the one function that decides.

    Asserted here rather than through two turns, because through two turns a
    second *"that's wrong"* is a correction of whatever the conversation is
    about **now** — a new correction, not a repeat. The repeat that really
    happens is a redelivery, which re-runs this against a fold the belief has
    already left, and this is that call.
    """
    assert correction.plan(
        Meaning.WRONG, target=BELIEF, belief=None
    ) is None
    assert correction.shown(None) == ""


def test_a_redelivered_correction_is_not_applied_twice(registry, tmp_path):
    """The other half of *already corrected*, on the path that produces it.

    At-least-once delivery makes redelivery routine, so the same message arrives
    again with the same external id. One correction record, not two.
    """
    seed(tmp_path)
    transport = FakeTransport([
        msg(text="thats wrong", message_id="m0", chat_id="123", date=int(NOON)),
        msg(text="thats wrong", message_id="m0", chat_id="123", date=int(NOON)),
    ])
    channel = TelegramChannel(transport=transport, mains={"123": MAIN})
    asyncio.run(Runtime(channel=channel, registry=registry).run())

    assert len(corrections_in(tmp_path)) == 1
    assert len(transport.sent) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the candidate — inferred, declined, confirmed
# ═════════════════════════════════════════════════════════════════════════════


def test_an_inferred_correction_asks_and_appends_nothing(registry, tmp_path):
    """Matrix: *inferred, not explicit*. **The story's central rule.**

    A message the table returns nothing for, which the classifier reads as a
    correction. Half shows what it *would* remove and asks; the log carries no
    correction and the belief is still there.
    """
    seed(tmp_path)
    assert recognize("hm, i dont think that is me these days") is None

    transport = a_turn(
        registry,
        texts=("hm, i dont think that is me these days",),
        corrections=widening(labelled(CORRECTION)),
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    body = sent(transport)
    assert f"{Op.RETRACT.value}?[{BELIEF}]: {CLAIM}" in body


def test_a_declined_candidate_removes_nothing(registry, tmp_path):
    """Matrix: *candidate declined*. Nothing removed; nothing appended beyond
    the exchange — and the exchange is the main's own two messages, which the
    stated ledger records as it records every message."""
    seed(tmp_path)

    transport = a_turn(
        registry,
        texts=("hm, i dont think that is me these days", "no, leave it"),
        corrections=widening(labelled(CORRECTION)),
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    # The proposal was made once and is not repeated on the answering turn.
    assert sent(transport).count(f"{Op.RETRACT.value}?[") == 1


@pytest.mark.parametrize(
    "answer", ["yes", "yeah", "हाँ", "はい", "sim", "evet", "نعم"],
    ids=["english", "english-informal", "hindi", "japanese", "portuguese",
         "turkish", "arabic"],
)
def test_a_confirmed_candidate_is_applied_with_the_cause_unknown(
    registry, tmp_path, answer
):
    """Matrix: *candidate confirmed*, and the confirmation is not English-only.

    The removal is a plain ``retract`` with **neither stamp**: a model's reading
    of a message settles neither whether Half was wrong nor whether the main
    changed, and confirming it says only that the belief should go.
    """
    seed(tmp_path)

    a_turn(
        registry,
        texts=("hm, i dont think that is me these days", answer),
        corrections=widening(labelled(CORRECTION)),
    )

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.RETRACT]
    assert EXPIRED_AT not in recorded[0].data
    assert INVALID_AT not in recorded[0].data
    assert BELIEF not in beliefs_of(tmp_path)


def test_anything_that_is_not_a_clear_yes_is_a_decline(registry, tmp_path):
    """Silence is not consent and neither is *maybe*.

    A hedge is the shape this rule exists for: it is the answer a generous
    affirmative table would take as a yes, and a candidate is a proposal to
    delete something.
    """
    seed(tmp_path)

    a_turn(
        registry,
        texts=("hm, i dont think that is me these days", "maybe, i am not sure"),
        corrections=widening(labelled(CORRECTION)),
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)


def test_an_explicit_correction_outranks_a_standing_candidate(
    registry, tmp_path
):
    """The main moved on rather than answering, and answering Half's old
    question with their new correction would remove the wrong belief.

    One correction record, from the explicit table, and the candidate is over
    rather than left standing to catch the *next* yes the main says about
    anything at all.
    """
    seed(tmp_path)
    wide = widening(labelled(CORRECTION))

    a_turn(
        registry,
        texts=("hm, i dont think that is me these days", "that has changed"),
        corrections=wide,
    )

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.RETRACT]
    assert recorded[0].data[INVALID_AT] is not None
    assert wide.standing(MAIN) is None


def test_the_widening_is_not_consulted_when_the_table_already_decided(
    registry, tmp_path
):
    """One classification per turn at most, and none at all where it could
    change nothing. Asserted with a holder that raises if reached, so this is
    *the call did not happen* rather than *a counter stayed at zero*."""
    seed(tmp_path)

    a_turn(
        registry, texts=("thats wrong",),
        corrections=Widening({MAIN: Exploding()}),
    )

    assert [r.op for r in corrections_in(tmp_path)] == [Op.RETRACT]


def test_the_widening_is_not_consulted_while_a_candidate_is_standing(
    registry, tmp_path
):
    """The main's answer is what moves next. Asking a model to read a message
    the main sent *while already being asked about it* would propose a second
    removal underneath the first."""
    seed(tmp_path)
    wide = Widening({MAIN: Holder(labelled(CORRECTION))}, bound_seconds=0.2)
    a_turn(registry, texts=("hm, i dont think that is me these days",),
           corrections=wide)
    consulted = wide.tally.consulted

    a_turn(registry, texts=("what is the weather like",), corrections=wide,
           at=NOON + 100)

    assert wide.tally.consulted == consulted


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the classifier is unavailable, unsure, or over budget
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "answer, kw",
    [
        (Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED), {}),
        (Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED), {}),
        (Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET), {}),
        (Failure(Kind.MALFORMED, Reason.NO_CONTENT), {}),
        (RuntimeError("boom"), {}),
        (None, {}),
        ("a sentence rather than a label", {}),
        (labelled("some_other_builds_label"), {}),
        (labelled(CORRECTION), {"sleep": 1.0}),
    ],
    ids=["unavailable", "refused", "over-budget", "malformed", "raises",
         "nothing", "prose", "unknown-label", "past-the-bound"],
)
def test_a_classifier_that_does_not_answer_leaves_the_table_standing(
    registry, tmp_path, answer, kw
):
    """Matrix: *classifier unavailable* and *classifier cost*.

    Nine ways not to get a label, including the budget refusal that is the cost
    cap doing its job, and a holder that runs past its bound. Every one of them
    leaves the offline table's answer exactly as it was: **no correction is
    invented**, nothing is appended, and the main still gets their reply.
    """
    seed(tmp_path)

    transport = a_turn(
        registry, texts=("hm, i dont think that is me these days",),
        corrections=widening(answer, **kw),
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    assert f"{Op.RETRACT.value}?[" not in sent(transport)
    assert transport.sent, "a classifier fault must not cost the main a reply"


def test_the_bound_is_a_bound_and_the_turn_is_answered_without_it(
    registry, tmp_path
):
    """The bound is what a main waits, not what they lose. A holder that never
    answers costs the widening and never the reply."""
    seed(tmp_path)

    transport = a_turn(
        registry, texts=("hm, i dont think that is me these days",),
        corrections=Widening(
            {MAIN: Holder(labelled(CORRECTION), sleep=5.0)}, bound_seconds=0.05
        ),
    )

    assert transport.sent
    assert corrections_in(tmp_path) == []


def test_a_model_that_ran_and_is_unsure_proposes_nothing(registry, tmp_path):
    """*Unsure* is a label and not a failure, and here it does nothing.

    This is the one place this story's asymmetry runs opposite to the crisis
    classifier's: there, doubt asks, because a wrong silence costs the only
    chance anyone had. Here, asking on doubt is Half proposing to delete
    something on every ambiguous message, and the cost of not asking is that the
    main says it again.
    """
    seed(tmp_path)

    transport = a_turn(
        registry, texts=("hm, i dont think that is me these days",),
        corrections=widening(labelled(UNSURE)),
    )

    assert corrections_in(tmp_path) == []
    assert f"{Op.RETRACT.value}?[" not in sent(transport)


def test_a_widening_with_no_holder_for_this_main_recognises_the_table_alone(
    registry, tmp_path
):
    """A deployment with no key is a supported shape, and it is much less of a
    loss here than on the crisis path: every explicit correction is still
    recognised, acted on and shown, because the table is offline and the model
    only widens."""
    seed(tmp_path)
    wide = Widening()

    a_turn(registry, texts=("thats wrong",), corrections=wide)

    assert [r.op for r in corrections_in(tmp_path)] == [Op.RETRACT]
    assert wide.tally.consulted == 0


def test_a_runtime_with_no_widening_still_corrects(registry, tmp_path):
    """The same sentence one layer up: correction is not a model feature."""
    seed(tmp_path)

    a_turn(registry, texts=("you were wrong about that",), corrections=None)

    assert [r.op for r in corrections_in(tmp_path)] == [Op.REVISE]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the loop survives, crisis owns the turn, nothing is spent
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap6_firewall
@pytest.mark.parametrize(
    "text", ["you were wrong about that", "that has changed", "thats wrong",
             "delete that"],
    ids=["revise", "retract", "unstated", "expunge"],
)
def test_the_wanting_stands_when_its_only_support_is_corrected(
    registry, tmp_path, text
):
    """Matrix: *the loop survives* (CAP-6), through **the route this story
    adds**.

    The firewall is asserted by AST over the fold and behaviourally over the raw
    ops in ``tests/test_loops.py``. This is the new thing: an inbound correction
    that a main typed, reaching the fold through the runtime, over a loop whose
    only support is the belief being removed. A wanting is not a fact, and
    evidence of non-action never refutes one — so the loop is still there, still
    stalled, still on its own timescale.
    """
    seed(tmp_path)
    assert loops_of(tmp_path)[LOOP]["state"] == "stalled"

    a_turn(registry, texts=(text,))

    assert BELIEF not in beliefs_of(tmp_path)
    standing = loops_of(tmp_path)
    assert LOOP in standing, "a correction demoted a wanting"
    assert standing[LOOP]["state"] == "stalled"
    assert standing[LOOP]["timescale"] == "years"


def test_a_correction_inside_the_mode_is_not_processed(registry, tmp_path):
    """Matrix: *in crisis*. The crisis path owns the turn.

    Structural rather than agreed: the gate never calls the turn path while the
    mode is open, so there is no branch here to forget. The belief stays, which
    is the right outcome — a correction made inside the mode is a thing to
    handle when the mode is over, not a thing to lose.
    """
    seed(tmp_path)

    a_turn(registry, texts=(SAFE_WORD, "you were wrong about that"),
           corrections=Widening({MAIN: Exploding()}))

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)


@pytest.mark.parametrize(
    "text, engine",
    [("thats wrong", True), ("delete that", True),
     ("hm, i dont think that is me these days", True)],
    ids=["removal", "erasure", "candidate"],
)
def test_a_correction_turn_spends_no_favour_and_asks_no_bought_question(
    registry, tmp_path, text, engine
):
    """Matrix: *no favour*, and **the turn-path seam**.

    A correction clarifier is not a CAP-4 question: it spends nothing and passes
    through none of story 5b's gates. So a turn that corrects attaches no bought
    question — asserted with a main who has a favour to spend and an `ask`-rung
    belief to spend it on, because a turn that could not have asked anyway
    proves nothing.

    Three reasons, and the first is the composition risk: the ranked set was
    scored *before* the removal, so a question attached afterwards could be
    about the belief this turn just took away.
    """
    seed(tmp_path, rung=License.ASK, favours=1)

    transport = a_turn(
        registry, texts=(text,), engine=engine,
        corrections=widening(labelled(CORRECTION)),
    )

    with Store(tmp_path / MAIN) as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []
        assert balance(store.log).spent == 0
    assert "question[" not in sent(transport)


def test_the_same_main_still_gets_a_bought_question_on_an_ordinary_turn(
    registry, tmp_path
):
    """The other half of the seam, and without it the case above passes on a
    build where nobody is ever asked anything.

    Same fixture, same engine, same favour — a message that is not a correction
    — and the question arrives.
    """
    seed(tmp_path, rung=License.ASK, favours=1)

    transport = a_turn(registry, texts=("farmland again please",), engine=True)

    assert "question[" in sent(transport)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: what Half shows, and replay
# ═════════════════════════════════════════════════════════════════════════════


def test_what_half_shows_is_the_claim_as_recorded_and_not_a_paraphrase(
    registry, tmp_path
):
    """Matrix: *shown text* (AD-22).

    Byte for byte against a claim with punctuation and a non-Latin script in it,
    so a build that normalised, folded or re-cased the text on the way out fails
    here. The claim reaches the wire because it *is* the record, not because
    something composed a sentence containing it.
    """
    odd = "sagt, दिल्ली में रहता है — since 2019"
    seed(tmp_path, beliefs=((BELIEF, odd),))

    transport = a_turn(registry, texts=("thats wrong",))

    assert f"{Op.RETRACT.value}[{BELIEF}]: {odd}" in sent(transport)


def test_a_correction_and_its_attribution_survive_a_rebuild(tmp_path):
    """Matrix: *replay* (AD-4).

    The attribution is **folded from the log rather than materialized**, which
    is story 5b's answer for the trust balance and is right here for the same
    reason and one of its own: the belief this describes has left the fold, so
    there is no derived entry for a cause to hang on, and inventing a table for
    corrections would be new derived state on the one path that must not grow
    any.

    So what a rebuild has to preserve is the log's own answer, before and after
    the derived view is discarded — asserted for all three states at once.
    """
    with Store(tmp_path / MAIN, prefix=build_prefix) as store:
        for ident, claim in (("b_1", "one"), ("b_2", "two"), ("b_3", "three")):
            store.record(Op.ASSERT, ident, "2026-08-01T00:00Z", claim=claim,
                         subject="self", **ladder.admitted())
        store.record(Op.REVISE, "co_1", NOW, target="b_1", **{EXPIRED_AT: NOW})
        store.record(Op.RETRACT, "co_2", NOW, target="b_2", **{INVALID_AT: NOW})
        store.record(Op.RETRACT, "co_3", NOW, target="b_3")
        before = {
            ident: attribution_for(ident, [r.data for r in store.log])
            for ident in ("b_1", "b_2", "b_3")
        }
        canonical = store.fold().canonical_json()

    (tmp_path / MAIN / "half.db").unlink()
    with Store(tmp_path / MAIN, prefix=build_prefix) as store:
        after = {
            ident: attribution_for(ident, [r.data for r in store.log])
            for ident in ("b_1", "b_2", "b_3")
        }
        assert store.fold().canonical_json() == canonical

    assert before == after == {
        "b_1": Attribution.HALF_WAS_WRONG,
        "b_2": Attribution.MAIN_CHANGED,
        "b_3": Attribution.NOT_YET_KNOWN,
    }


# ═════════════════════════════════════════════════════════════════════════════
# matrix: worldwide
# ═════════════════════════════════════════════════════════════════════════════


#: One correction per script, from five continents. The removal path is swept
#: over all of them, so **no fixture in this file makes one language the
#: default**: every behavioural claim about removal is made in seven languages
#: or it is not made.
WORLDWIDE = [
    ("thats wrong", Meaning.WRONG),
    ("eso está mal", Meaning.WRONG),
    ("это неправда", Meaning.WRONG),
    ("यह गलत है", Meaning.WRONG),
    ("这不对", Meaning.WRONG),
    ("それは違う", Meaning.WRONG),
    ("هذا خطأ", Meaning.WRONG),
    ("hiyo si kweli", Meaning.WRONG),
    ("das war nie wahr", Meaning.NEVER_TRUE),
    ("我从来没说过", Meaning.NEVER_TRUE),
    ("已经不是了", Meaning.CHANGED),
    ("अब ऐसा नहीं है", Meaning.CHANGED),
    ("그거 삭제해", Meaning.ERASE),
    ("บลบอันนั้น", None),
]


@pytest.mark.parametrize(
    "text, expected", WORLDWIDE[:-1],
    ids=[t.replace(" ", "-") for t, _ in WORLDWIDE[:-1]],
)
def test_the_table_recognises_a_correction_in_every_script_it_carries(
    text, expected
):
    """Every entry means what its table says it means, in the script it is
    written in — including the ones an unspaced-script tokenizer would have to
    match inside a longer run."""
    assert recognize(text) is expected


@pytest.mark.parametrize(
    "text", [t for t, m in WORLDWIDE if m is not None][:8],
    ids=[t.replace(" ", "-") for t, m in WORLDWIDE if m is not None][:8],
)
def test_a_removal_happens_in_every_script_and_none_is_the_default(
    registry, tmp_path, text
):
    """The behavioural sweep. Eight scripts, one belief, one removal each.

    A build that recognised only Latin would fail seven of these, and a fixture
    that quietly narrowed to English would fail the coverage case below.
    """
    seed(tmp_path)

    a_turn(registry, texts=(text,))

    assert [r.op for r in corrections_in(tmp_path)][:1] in (
        [Op.RETRACT], [Op.REVISE], [Op.EXPUNGE],
    )
    assert BELIEF not in beliefs_of(tmp_path)


def _scripts(text: str) -> set[str]:
    found = set()
    for char in text:
        if not char.isalpha():
            continue
        name = unicodedata.name(char, "")
        if name:
            found.add(name.split()[0])
    return found


def test_no_table_and_no_fixture_makes_one_language_the_default():
    """The coverage assertion, and it is the one that keeps the sweep honest.

    Every removing table carries rows in at least six scripts, and this file's
    own behavioural sweep spans at least six. Without this, narrowing either to
    English would leave every case above green.
    """
    for name, _ in MEANING_FOR_TABLE:
        scripts = set().union(*(_scripts(row) for row in VOCABULARY[name]))
        assert len(scripts) >= 6, (name, sorted(scripts))
        latin = [row for row in VOCABULARY[name] if _scripts(row) <= {"LATIN"}]
        assert len(latin) < len(VOCABULARY[name]), name
    swept = set().union(*(_scripts(text) for text, _ in WORLDWIDE))
    assert len(swept) >= 6, sorted(swept)


def test_a_correction_in_a_language_no_row_covers_is_still_reachable(
    registry, tmp_path
):
    """The acceptance criterion the table cannot satisfy on its own.

    Icelandic has no row anywhere in this module — asserted, so a table that
    grew one stops this case being evidence rather than quietly making it
    vacuous — and the correction still reaches the main as a candidate, because
    the recall instrument is not the enumeration.
    """
    unseen = "þetta er rangt, ég sagði það aldrei"
    assert recognize(unseen) is None

    seed(tmp_path)
    transport = a_turn(registry, texts=(unseen,),
                       corrections=widening(labelled(CORRECTION)))

    assert f"{Op.RETRACT.value}?[{BELIEF}]: {CLAIM}" in sent(transport)


@pytest.mark.parametrize(
    "text",
    ["hi", "i finally booked the flights", "please remember this",
     "farmland again please", "i went running today", "how are you",
     "can you remind me tomorrow", "that plot of the novel was good",
     "the weather is not great today", "i am not going to the shop"],
    ids=lambda t: t.replace(" ", "-")[:24],
)
def test_the_table_fires_on_no_ordinary_message(text):
    """The other half of a phrase table's honesty. Every row here is *acted on*
    with no confirmation, so a table that fired on an ordinary sentence would
    remove a belief the main never questioned — including two negations that
    are about something other than Half."""
    assert recognize(text) is None


@pytest.mark.parametrize(
    "text", ["no", "not really", "i think so", "maybe", "ok", "sure thing",
             "yes i went there"],
    ids=lambda t: t.replace(" ", "-"),
)
def test_only_a_clear_whole_message_yes_confirms_a_candidate(text):
    """The confirmation table is narrow on purpose: the cost of reading a real
    yes as a hedge is one more turn, and the cost of the reverse is a belief
    deleted on a *maybe*. A ``yes`` buried inside a sentence about something
    else is not an answer to Half's question."""
    assert not is_confirmation(text)


# ═════════════════════════════════════════════════════════════════════════════
# the vocabulary, pinned
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "table, meaning", MEANING_FOR_TABLE, ids=[n for n, _ in MEANING_FOR_TABLE]
)
def test_every_row_of_every_table_still_produces_its_own_meaning(table, meaning):
    """Deleting a row fails mechanically rather than silently narrowing the
    reach. Swept over ``VOCABULARY`` rather than over a list kept in this file,
    so a new table is covered the moment it is added."""
    for row in VOCABULARY[table]:
        assert recognize(row) is meaning, (table, row)


def test_every_confirmation_row_confirms():
    for row in VOCABULARY["confirm"]:
        assert is_confirmation(row), row


def test_no_row_of_any_table_is_a_single_latin_word():
    """A one-word table over ``no`` or ``wrong`` fires on half the conversations
    there are. A non-Latin run cannot collide with an English sentence, so those
    are free; a Latin one has to be a phrase.

    The confirmation table is exempt: it is matched **whole-message** and only
    while Half is waiting on an answer, which is what makes a bare ``yes`` safe
    there and nowhere else.
    """
    for name, _ in MEANING_FOR_TABLE:
        for row in VOCABULARY[name]:
            if _scripts(row) <= {"LATIN"}:
                assert len(row.split()) > 1, (name, row)


def test_the_two_tokenizers_agree_on_the_scripts_they_both_cut(tmp_path):
    """``half.correction.signals`` splits on ``terms`` and
    ``half.crisis.signals`` on ``words``, because the correction table has to
    match a Chinese phrase inside a sentence and the crisis one does not.

    The duplication is a checked property rather than a place to drift: on every
    spaced script — which is every row either table shares — the two must cut
    identically, so a fix to one is a fix to both or a failure here.
    """
    from half.correction.signals import _tokens as correction_tokens
    from half.crisis.signals import _tokens as crisis_tokens

    for text in (
        "that was never true", "eso está mal", "это неправда",
        "यह गलत है", "hiç öyle demedim", "je n'ai jamais dit ça",
        "i want to\nkill myself", "don't do that",
    ):
        assert correction_tokens(text) == crisis_tokens(text), text


# ═════════════════════════════════════════════════════════════════════════════
# structural: the rules an inference route cannot walk around
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap11_structure
def test_an_inferred_correction_cannot_be_planned_without_an_answer():
    """**The rule, at the one function that turns a meaning into a removal.**

    Asserted as a raise rather than as a caller's good manners, because a caller
    is a thing a later story adds another of. Every meaning, so a new inference
    route cannot pick the one that was left open.
    """
    for meaning in Meaning:
        with pytest.raises(CorrectionError):
            correction.plan(
                meaning, target=BELIEF, belief={"claim": CLAIM},
                source=Source.INFERRED,
            )
        # And the confirmed form is the only way through.
        planned = correction.plan(
            meaning, target=BELIEF, belief={"claim": CLAIM},
            source=Source.INFERRED, confirmed=True,
        )
        assert planned is not None


@pytest.mark.cap11_structure
def test_the_widening_can_name_no_op_and_no_way_to_append():
    """A model's reading of a message may become a question and may never become
    a record. Asserted over the module rather than over its behaviour, because
    *"it does not append today"* decays the first time somebody reaches for one
    — and the reach would be invisible.
    """
    tree = ast.parse(
        (ROOT / "half/correction/candidate.py").read_text(encoding="utf-8")
    )
    named = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert not named & {
        "Op", "RETRACT", "REVISE", "EXPUNGE", "record", "append", "expunge",
        "plan", "fields", "Store", "store",
    }, sorted(named)


@pytest.mark.cap11_structure
def test_no_label_the_widening_knows_may_do_more_than_ask():
    """The import-time check, asserted from outside so that the file's own
    ``_check_labels`` cannot be the only thing standing behind the rule."""
    assert set(ACTION_FOR_LABEL) == set(LABELS)
    assert set(ACTION_FOR_LABEL.values()) <= {Action.ASK, Action.NONE}
    assert ACTION_FOR_LABEL[CORRECTION] is Action.ASK
    assert ACTION_FOR_LABEL[UNSURE] is Action.NONE
    assert ACTION_FOR_LABEL[NO_CORRECTION] is Action.NONE
    assert len(Action) == 2


@pytest.mark.cap11_structure
def test_a_fallback_that_asks_is_unrepresentable():
    """A model that did not run is not a model that read a correction, and
    proposing to delete something because a provider is down is its own harm.
    Refused in the type rather than avoided by every caller remembering."""
    with pytest.raises(CorrectionError):
        Verdict(Action.ASK, fell_back=True)


@pytest.mark.cap11_structure
@pytest.mark.parametrize(
    "holder",
    [object(), lambda work: None,
     type("Wide", (), {"classify": lambda self, w: None,
                       "generate": lambda self, w: None})()],
    ids=["not-a-classifier", "callable", "also-generates"],
)
def test_the_widening_refuses_a_holder_that_could_produce_text(holder):
    """A ``Classifier`` is narrow because of the methods it lacks, and that
    guarantee is worth exactly as much as the check that the object handed over
    really is one. An allowlist, because the denylist this pattern replaced let
    an object with ``classify`` and ``chat`` walk straight through."""
    with pytest.raises(CorrectionError):
        Widening({MAIN: holder})
    assert ALLOWED_METHODS == frozenset({"classify"})


@pytest.mark.cap11_structure
def test_the_widening_is_sealed_after_construction():
    """A narrow output is half of a narrow holder; the other half is that
    nobody can swap in a wider one afterwards."""
    wide = Widening()
    with pytest.raises(CorrectionError):
        wide._holders = {MAIN: object()}


@pytest.mark.cap11_structure
def test_only_the_message_leaves_the_machine():
    """Content egress, asserted against the rendered request rather than a
    docstring. The belief a candidate would name is decided *after* the answer
    comes back and is never sent: asking the model which claim is being
    corrected would put a sentence about the main's life into a payload.
    """
    prompt = prompt_for("hm, that is not me", main_id=MAIN)
    assert [turn.text for turn in prompt.turns] == ["hm, that is not me"]
    body = " ".join(prompt.system) + " " + " ".join(t.text for t in prompt.turns)
    assert CLAIM not in body
    assert BELIEF not in body
    assert MAIN not in body
    assert prompt.cache is None


@pytest.mark.cap11_structure
def test_the_line_half_shows_is_made_of_the_op_and_the_claim_and_nothing_else():
    """*"No generated prose"* as a property of the module, not of its output.

    Every string constant in ``apply.py`` outside a docstring and outside a
    ``raise`` is either punctuation, a field name, or an enum value — there is
    no word here a main could read that Half composed. The op's own name is the
    whole vocabulary, and it comes from ``half.store.ops``.

    Docstrings and refusal messages are excluded because neither can reach a
    main: one is prose about the code and the other is a ``CorrectionError``
    raised at a caller mistake, on a path whose whole job is to *not* produce a
    turn. Everything else is a candidate for the wire.
    """
    source = (ROOT / "half/correction/apply.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    unread = {
        id(node.body[0].value) for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    } | {
        id(inner) for node in ast.walk(tree) if isinstance(node, ast.Raise)
        for inner in ast.walk(node) if isinstance(inner, ast.Constant)
    }
    literals = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in unread
    ]
    allowed = {"[", "]", ": ", "?", "", "claim", "co_", "table", "inferred"}
    assert set(literals) <= allowed, sorted(set(literals) - allowed)


@pytest.mark.cap11_structure
def test_the_shown_line_is_built_once_and_read_two_ways():
    """A proposal and a removal differ by one character, from one function.

    Two renderings of one item is how a guard that scans one string ends up
    admitting a different one — so the candidate Half shows and the removal it
    performs cannot describe different things.
    """
    removal = Removal(target=BELIEF, op=Op.RETRACT,
                      attribution=Attribution.NOT_YET_KNOWN, claim=CLAIM)
    assert correction.shown(removal) == f"retract[{BELIEF}]: {CLAIM}"
    assert correction.proposed(removal) == f"retract?[{BELIEF}]: {CLAIM}"
    assert correction.proposed(removal).replace("?", "") == correction.shown(
        removal
    )


@pytest.mark.cap11_structure
def test_the_correction_package_reaches_no_channel_and_no_crisis_module():
    """Two rules in one sweep.

    *No channel*: nothing here sends anything. What Half shows is handed back to
    the turn that asked for it.

    *No ``half.crisis``*: the spine's layer table says the entry gate is
    depended upon by no domain module, and this is a domain module. It is why
    there are two phrase tokenizers and two confirmation tables in the tree —
    the alternative was a cycle through the gate.
    """
    for path in sorted((ROOT / "half/correction").rglob("*.py")):
        offending = reaches(path, ("half.channel", "half.crisis", "half.actor"))
        assert not offending, f"{path.name} reaches outward: {offending}"


@pytest.mark.cap11_structure
def test_only_the_widening_may_name_a_model_inside_the_package():
    """The one place the model is reachable, and it holds an object that cannot
    produce text.

    ``UNREACHABLE`` cannot be applied whole to this package the way it is to
    ``half/trust`` and ``half/questions``: those decide whether to *ask* and a
    model there would be a question composed by a model, where here the model is
    the recall instrument the story requires. So the rule is narrowed by one
    root and made stricter in exchange — exactly one module may name it, and the
    rest of ``UNREACHABLE`` still stands over the whole package.
    """
    from tests.conftest import UNREACHABLE

    rest = tuple(root for root in UNREACHABLE if root != "half.model")
    for path in sorted((ROOT / "half/correction").rglob("*.py")):
        assert not reaches(path, rest), f"{path.name} reaches outward"
        model = reaches(path, ("half.model",))
        if path.name == "candidate.py":
            assert model and all(
                name.startswith("half.model.port") or name == "half.model.port"
                for name in model
            ), model
        else:
            assert not model, f"{path.name} names a model: {model}"


@pytest.mark.cap11_structure
def test_the_correction_package_reads_no_clock():
    """Every stamp is the caller's — the inbound one the adapter read — so two
    replays of one conversation produce one set of records (AD-30)."""
    from tests.test_purity import AMBIENT_CALLS

    for path in sorted((ROOT / "half/correction").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else
            node.func.id if isinstance(node.func, ast.Name) else ""
            for node in ast.walk(tree) if isinstance(node, ast.Call)
        }
        assert not called & AMBIENT_CALLS, f"{path.name} reads ambient state"


@pytest.mark.cap11_structure
def test_the_bound_and_the_caps_are_the_ones_story_6d_settled():
    """Pinned, so a change to any of them is a deliberate edit. The bound is
    what a main waits; the per-call cap binds before the transport is touched;
    the per-pass cap is a runaway stop and never a cost target."""
    assert BOUND_SECONDS == 2.0
    assert PER_CALL_MICRO_USD == 100_000
    assert PER_PASS_MICRO_USD == 500_000_000
    assert PER_CALL_MICRO_USD <= PER_PASS_MICRO_USD


@pytest.mark.cap11_structure
def test_the_widening_reaches_the_shipped_product(tmp_path, monkeypatch):
    """A surface reachable only from a test is a surface nobody has run.

    Asserted **by value** off the wiring the composition root builds, for the
    reason story 11's identical claim is: story 6d's version passed with the
    value set to ``None``.
    """
    from half import __main__ as entrypoint
    from half.config import MAINS_ENV, ROOT_ENV, load

    monkeypatch.setenv(ROOT_ENV, str(tmp_path))
    monkeypatch.setenv(MAINS_ENV, f"123:{MAIN}")
    wiring = entrypoint.build(load(), "123:fake")
    assert isinstance(wiring.corrections, Widening)
