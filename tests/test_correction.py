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
import logging
import unicodedata
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.context.channels import Content, sanitize
from half.correction import apply as correction
from half.correction.apply import Removal, Source
from half.voice.compose import ASK_ABOUT
from half.voice.gate import Voice
from half.correction.attribute import Attribution, attribution_for
from half.correction.candidate import (
    ACTION_FOR_LABEL,
    BREAK_AFTER,
    BREAK_FOR,
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
from half.retrieval.strands import STRAND_FLOOR
from half.schedule.clock import stamp
from half.store.ops import TOUCH_TENSION, Op
from half.store.records import EXPIRED_AT, INVALID_AT, TARGET, make
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.touch import Origin
from half.trust.balance import balance
from tests.conftest import (
    FakeTransport,
    a_voice,
    msg,
    outward,
    reaches,
    seed_belief,
)

pytestmark = pytest.mark.cap11

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"
#: 2026-09-01T12:00:00Z — the instant every turn in this file builds from,
#: carried in on the inbound stamp, which is the only clock a turn has.
NOON = 1_788_264_000.0
NOW = stamp(NOON)
DAY = 86_400.0

LOOP = "buy-farmland"
NOW = "2026-09-01T12:00:00Z"
BELIEF = "b_land"
#: The seeded claim, asserted **byte for byte** on the wire. Distinctive enough
#: that its presence in a reply cannot be an accident, and sharing no word with
#: any correction phrase, so a table row can never match the claim itself.
CLAIM = "has not walked that plot since March"

#: One claim Half may **state**, for the cases that assert a reply still goes
#: out (story 13b). It shares a word with the messages those cases send, so
#: retrieval finds it, and no adjacent pair with ``CLAIM``, so it is admitted.
SAYABLE = "walks the boundary of that field every autumn"

ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")

#: A message that raises the belief's own strand, and therefore the message a
#: correction has to follow.
#:
#: **This is the relevance floor made visible in the fixtures.** A correction
#: aims at a belief the live conversation touches, read off the strand weight
#: retrieval already computes — so a bare *"that's wrong"* into a fresh
#: conversation aims at nothing, which is correct, because *that* has no
#: antecedent. Every removal case below therefore has a turn in front of it,
#: which is also how a correction actually arrives.
ON_TOPIC = "farmland again please"


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
        if callable(self._answer):
            # Private, because ``Widening`` refuses a holder with any public
            # callable but ``classify`` — so an answer that is a lambda has to
            # live behind an underscore, exactly as the real thing's does.
            return self._answer(work)
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


#: The fragment that marks the one message in a fixture the classifier is meant
#: to read as a correction.
INFERRED = "these days"


def widening(answer: object = None, *, on: str = INFERRED, **kw) -> Widening:
    """A widening for ``MAIN`` alone that answers ``answer`` for **one** message.

    ``on`` is the fragment that identifies it; every other message is answered
    ``no_correction``. A stub that answered the same thing to everything would
    put a candidate up on the on-topic turn every correction now follows, and
    then the case would be about the stub rather than about the product.

    ``None``, a failure, a raise or prose all mean *no readable label* for that
    one message, which is a fallback — the table's answer stands.
    """
    def reads(work: Classify):
        if on and on not in work.prompt.turns[0].text:
            return labelled(NO_CORRECTION)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    return Widening({MAIN: Holder(reads, **kw)}, bound_seconds=0.2)


# ── the harness ──────────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


#: A belief on a strand the correction fixtures never raise. It is what makes
#: the relevance floor a real comparison rather than a tie of one.
OTHER = "b_bee"
OTHER_CLAIM = "keeps bees in the garden"


def seed(
    root,
    *,
    main_id=MAIN,
    beliefs=((BELIEF, CLAIM),),
    rung=License.BEHAVE,
    loop=LOOP,
    favours=0,
    sayable=None,
):
    """One main, one wanting, and beliefs on it, seeded through the ladder.

    A rung is earned by a promotion involving the main and never spelled into a
    record, exactly as ``conftest.seed_belief`` does, so nothing here can mint a
    permission the product cannot.

    ``favours`` are delivered morning messages — the only thing that earns —
    dated before the turn. They exist so the *no favour spent* row is a real
    comparison: a turn with nothing to spend proves nothing about spending.

    ``sayable`` seeds one `assert`-rung claim, and it exists because of story
    13b: a turn whose material is all `behave` has nothing quotable and — with
    no template in any language — nothing to say at all. A case whose point is
    *"the main still gets their reply"* has to have a reply for that to be
    about. It shares no adjacent pair with ``CLAIM``, so the builder admits it.
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
        if sayable is not None:
            seed_belief(store, "b_sayable", "2026-08-01T00:00Z", subject="self",
                        claim=sayable, ledger="revealed",
                        rung=License.ASSERT, support=["s_sayable"])
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
    tag="m",
    voice=None,
):
    """Real inbound turns, through the real runtime and the real crisis gate.

    ``texts`` is a sequence because half the matrix is about what the *second*
    message does — a confirmation, a decline, a follow-up that settles a cause.
    Each gets its own external id, so the redelivery check never suppresses one
    — and ``tag`` distinguishes two *calls*, because at-least-once delivery
    makes a repeated external id a redelivery and the second turn would be
    dropped rather than answered.
    """
    transport = FakeTransport([
        msg(text=text, message_id=f"{tag}{index}", chat_id="123",
            date=int(at + index))
        for index, text in enumerate(texts)
    ])
    channel = TelegramChannel(transport=transport, mains={"123": main_id})
    runtime = Runtime(
        channel=channel, registry=registry, corrections=corrections,
        questions=QuestionEngine(ledger=registry) if engine else None,
        # **No composer by default, and that is deliberate.** With none, every
        # turn here takes story 13b's fallback rung — the claim alone — which is
        # exactly what CAP-11 asks a removal to show, so these cases assert the
        # bytes a main sees rather than a stub's sentence. The two cases that
        # are about the *bought question* pass a real one, because a question
        # exists only in composed prose.
        voice=Voice() if voice is None else voice,
    )
    asyncio.run(runtime.run())
    return transport


def corrects(registry, *later, **kw):
    """``ON_TOPIC``, then the correction. The ordinary shape of a correction.

    Separate from ``a_turn`` so that a case which deliberately corrects into a
    *fresh* conversation — where the aim must find nothing — has to say so by
    calling ``a_turn`` directly.
    """
    return a_turn(registry, texts=(ON_TOPIC, *later), **kw)


def sent(transport):
    return "\n".join(text for _, text in transport.sent)


def last(transport):
    """Only the final reply. The turn a case is actually about."""
    return transport.sent[-1][1] if transport.sent else ""


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

    **Story 13b moved where the distinction lives.** It used to be on the wire,
    as ``revise[b_land]: ...`` against ``retract[b_land]: ...``, which is the
    internal serialization reaching a person. It is now in the log — the op
    itself and the attribution stamps, both asserted above — and the wire
    carries the claim and no op name at all, because an op name is not a word in
    anybody's language.
    """
    seed(tmp_path)

    transport = corrects(registry, "you were wrong about that")

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.REVISE]
    assert recorded[0].data[TARGET] == BELIEF
    assert recorded[0].data[EXPIRED_AT] == stamp(NOON + 1)
    assert INVALID_AT not in recorded[0].data
    assert BELIEF not in beliefs_of(tmp_path)
    assert attribution_for(BELIEF, [r.data for r in log_of(tmp_path)]) is (
        Attribution.HALF_WAS_WRONG
    )
    body = sent(transport)
    assert CLAIM in body
    assert Op.REVISE.value not in body and Op.RETRACT.value not in body
    assert BELIEF not in body


def test_the_main_changed_appends_a_retract_and_owes_no_apology(
    registry, tmp_path
):
    """Matrix: *the main changed*.

    A ``retract``, the world-changed stamp, and — the half that is easy to lose
    — **no ``revise`` anywhere**. The distinction CAP-11 asks to preserve is
    only preserved if the wrong one is absent, and since story 13b the place it
    is preserved is the log: the wire carries the claim and neither op name,
    because neither is a word a main can read.
    """
    seed(tmp_path)

    transport = corrects(registry, "that has changed")

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.RETRACT]
    assert recorded[0].data[INVALID_AT] == stamp(NOON + 1)
    assert EXPIRED_AT not in recorded[0].data
    assert attribution_for(BELIEF, [r.data for r in log_of(tmp_path)]) is (
        Attribution.MAIN_CHANGED
    )
    body = sent(transport)
    assert CLAIM in body
    assert Op.REVISE.value not in body and Op.RETRACT.value not in body


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

    corrects(registry, "thats wrong")

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
    corrects(registry, "thats wrong")

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
    corrects(registry, "that has changed")
    with Store(tmp_path / MAIN) as store:
        store.record(Op.REVISE, "co_later", "2026-09-02T09:00:00Z",
                     target=BELIEF, **{EXPIRED_AT: "2026-09-02T09:00:00Z"})

    recorded = corrections_in(tmp_path)
    assert [(r.op, r.data.get(INVALID_AT), r.data.get(EXPIRED_AT))
            for r in recorded] == [
        (Op.RETRACT, stamp(NOON + 1), None),
        (Op.REVISE, None, "2026-09-02T09:00:00Z"),
    ]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: erase, no such belief, already corrected
# ═════════════════════════════════════════════════════════════════════════════


def test_an_erasure_tombstones_the_body_and_says_something_different(
    registry, tmp_path
):
    """Matrix: *erase it*. Story 1's validate-then-erase, reached from the
    inbound path for the first time — **and only after the main has answered.**

    That last part is a deliberate tightening past the story's own matrix. Every
    other correction is recoverable, because the claim stays in the log and the
    main can correct the correction; an erasure tombstones the body, so a
    mis-aimed one leaves nothing to reverse and nothing to show. CAP-10's rule
    is *never act on inference alone*; this is the same rule one step further.

    So two turns: Half shows what it would erase, and the erasure happens on the
    yes. Three things then hold at once: the op is ``expunge``, the claim is
    **gone from the log on disk**, and the reply on the confirming turn
    **carries the claim** — read off the fold before ``Store.expunge``
    tombstones the body.

    **That last one reverses story 12, on story 13b's frozen matrix** (*the
    claim is shown before the body is gone*). An erasure is the only removal
    that cannot be undone by correcting the correction, so the confirmation turn
    is the last moment a mis-aimed one can be caught — and under story 12 that
    moment carried no words at all, so a main destroyed a belief they were never
    shown.
    """
    seed(tmp_path)

    transport = corrects(registry, "delete that", "yes")

    recorded = corrections_in(tmp_path)
    assert [r.op for r in recorded] == [Op.EXPUNGE]
    assert BELIEF not in beliefs_of(tmp_path)
    shard = (tmp_path / MAIN / "beliefs").glob("*.jsonl")
    on_disk = "".join(path.read_text(encoding="utf-8") for path in shard)
    assert CLAIM not in on_disk
    assert f"{Op.EXPUNGE.value}?[{BELIEF}]" in sent(transport), "Half asked first"
    confirming = last(transport)
    assert CLAIM in confirming, "the claim is shown before the body is gone"
    assert Op.EXPUNGE.value not in confirming
    assert BELIEF not in confirming


def test_a_correction_naming_nothing_half_holds_removes_nothing_and_says_so_gently(
    registry, tmp_path
):
    """Matrix: *no such belief*. Nothing removed, nothing appended, and **the
    main is not shown an error** — being told *"I have no record of that"* in
    answer to *"that's wrong"* is Half arguing."""
    seed(tmp_path, beliefs=(), loop=None, sayable=SAYABLE)

    transport = a_turn(registry, texts=("thats wrong",))

    assert corrections_in(tmp_path) == []
    assert last(transport).strip() == SAYABLE


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
    seed(tmp_path, sayable=SAYABLE)
    transport = FakeTransport([
        msg(text=ON_TOPIC, message_id="m0", chat_id="123", date=int(NOON)),
        msg(text="thats wrong", message_id="m1", chat_id="123", date=int(NOON) + 1),
        msg(text="thats wrong", message_id="m1", chat_id="123", date=int(NOON) + 1),
    ])
    channel = TelegramChannel(transport=transport, mains={"123": MAIN})
    asyncio.run(Runtime(channel=channel, registry=registry).run())

    assert len(corrections_in(tmp_path)) == 1
    # **One send, and it is the removal.** The first turn has nothing quotable
    # — the fixture's material is all `behave` — so since story 13b it is
    # silent; the redelivery is silent too, because the idempotency check
    # answers before anything is composed. What must not happen is the claim
    # being shown twice, which is what a second correction would look like.
    assert [text for _, text in transport.sent] == [CLAIM]


# ═════════════════════════════════════════════════════════════════════════════
# the aim: what a correction is about
# ═════════════════════════════════════════════════════════════════════════════


def test_a_correction_about_nothing_the_conversation_touched_removes_nothing(
    registry, tmp_path
):
    """**The defect the relevance floor exists for.**

    A message about email, then *"that's wrong"*. With no term match the
    backstop supplies every belief the main has, in an order that says nothing
    about this turn — so taking the top of the ranked set expunged *"keeps bees
    in the garden"*.

    The floor is ``half.retrieval``'s own ``STRAND_FLOOR``, which is exactly the
    weight of a belief on no strand the live conversation touches. Nothing here
    is on one, so nothing is aimed at.
    """
    seed(tmp_path, beliefs=((BELIEF, CLAIM),), loop=LOOP)
    with Store(tmp_path / MAIN, prefix=build_prefix) as store:
        store.record(Op.ASSERT, OTHER, "2026-08-01T00:02Z", claim=OTHER_CLAIM,
                     subject="self", topics=["bees"],
                     **ladder.admitted(support=["s_bee"]))

    a_turn(registry, texts=("did you see my email about the invoice",
                            "thats wrong"))

    assert corrections_in(tmp_path) == []
    assert {BELIEF, OTHER} <= set(beliefs_of(tmp_path))


def test_a_correction_with_no_antecedent_removes_nothing(registry, tmp_path):
    """A bare *"that's wrong"* opening a conversation aims at nothing.

    *That* has no antecedent, and Half inventing one is how a correction lands
    on a belief the main never questioned. The strand weight of every belief is
    exactly the floor here, which is what makes this the boundary case: a floor
    written ``<`` rather than ``<=`` admits all of them.
    """
    seed(tmp_path, sayable=SAYABLE)

    transport = a_turn(registry, texts=("thats wrong",))

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    assert last(transport).strip() == SAYABLE


def test_the_aim_ignores_the_message_that_carried_the_correction():
    """Every inbound message is recorded as a belief on the stated ledger, so
    the second *"that's wrong"* in a conversation retracted the belief holding
    the text *"that's wrong"*.

    Asserted directly on ``aim`` over synthetic candidates, because the two
    filters are ordered and the outer one hides the inner: a message belief
    carries no topic and no loop, so **today** it never clears the floor anyway.
    That is why this case exists at all — the exclusion is the filter that has
    to keep working when a later story gives an inbound record a topic, and a
    behavioural case would be asserting the floor twice.
    """
    from half.retrieval.port import Candidate

    def belief(ident, ledger=None, t="2026-09-01T00:00Z"):
        record = {"t": t}
        if ledger:
            record["ledger"] = ledger
        return Candidate(id=ident, claim="", prefix="", bm25=-1.0,
                         belief=record, score=1.0,
                         weights={"strand": STRAND_FLOOR + 0.1})

    live = [belief("b_said", "stated", "2026-09-01T00:02Z"),
            belief("b_older", "stated", "2026-09-01T00:01Z"),
            belief("b_real")]
    # The newest stated record is the previous turn's message. It is skipped
    # even though it ranks first.
    assert correction.aim(live) == "b_older"
    # And this turn's own id is skipped by the caller, whatever it ranks.
    assert correction.aim(live, exclude=("b_older",)) == "b_real"


def test_the_aim_needs_a_weight_it_can_read():
    """Never raises, and never guesses. A candidate whose strand weight is
    missing or unreadable is one the correction does not aim at — the safe
    direction, because the cost of aiming wrongly is a belief removed."""
    from half.retrieval.port import Candidate

    odd = [
        Candidate(id="b_no_weights", claim="", prefix="", bm25=None,
                  belief={}, score=1.0, weights={}),
        Candidate(id="b_bad_weight", claim="", prefix="", bm25=None,
                  belief={}, score=1.0, weights={"strand": "high"}),
        Candidate(id="b_bool", claim="", prefix="", bm25=None,
                  belief={}, score=1.0, weights={"strand": True}),
    ]
    assert correction.aim(odd) == ""
    assert correction.aim([]) == ""
    assert correction.aim(None) == ""


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the candidate — inferred, declined, confirmed
# ═════════════════════════════════════════════════════════════════════════════


def test_a_proposal_turn_carries_the_composed_prose_and_not_only_the_line(
    registry, tmp_path
):
    """The prose on a proposal turn, which nothing asserted.

    The prose carries no question mark: a proposal turn bought no favour, so
    the judge's question budget is zero and a question would be refused. That
    is the currency working, and it is why this case's fixture is a statement.

    ``_pipeline`` returns ``f"{turned.text}\n{asked}"`` on a proposal, and every
    case here looked only for the ``retract?[...]`` line — so ``return asked``
    left the suite green while the main received the internal serialization
    alone, which is the launch blocker story 13b exists to close.

    The proposal line itself is deliberately still a serialization and is
    recorded as deferred in ``half.correction.apply.proposed``; what this case
    pins is that it never arrives *alone*.
    """
    seed(tmp_path)
    voice, holder = a_voice("that field has been on your mind.")

    transport = corrects(
        registry, "hm, i dont think that is me these days",
        corrections=widening(labelled(CORRECTION)), voice=voice,
    )

    body = last(transport)
    assert holder.calls, "the composer was never reached on a proposal turn"
    assert "that field has been on your mind." in body, body
    assert f"{Op.RETRACT.value}?[{BELIEF}]" in body, body
    # The prose comes first and the line is the tail, so a main reads a
    # sentence rather than an identifier.
    assert body.index("that field has") < body.index(f"{Op.RETRACT.value}?")
    # And the proposal still withholds the claim (AD-18).
    assert CLAIM not in body


def test_an_inferred_correction_asks_and_appends_nothing(registry, tmp_path):
    """Matrix: *inferred, not explicit*. **The story's central rule.**

    A message the table returns nothing for, which the classifier reads as a
    correction. Half shows what it *would* remove and asks; the log carries no
    correction and the belief is still there.
    """
    seed(tmp_path)
    assert recognize("hm, i dont think that is me these days") is None

    transport = corrects(
        registry, "hm, i dont think that is me these days",
        corrections=widening(labelled(CORRECTION)),
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    body = sent(transport)
    assert f"{Op.RETRACT.value}?[{BELIEF}]" in body
    # **And no claim.** A proposal is Half asking, on a turn where nothing was
    # removed and the main may have said nothing corrective at all; the id is
    # enough to ask about. See the AD-18 bound case below.
    assert CLAIM not in body


def test_a_declined_candidate_removes_nothing(registry, tmp_path):
    """Matrix: *candidate declined*. Nothing removed; nothing appended beyond
    the exchange — and the exchange is the main's own two messages, which the
    stated ledger records as it records every message."""
    seed(tmp_path)

    transport = corrects(
        registry, "hm, i dont think that is me these days", "no, leave it",
        corrections=widening(labelled(CORRECTION)),
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    # The proposal was made once and is not repeated on the answering turn.
    assert sent(transport).count(f"{Op.RETRACT.value}?[") == 1


def test_a_declined_candidate_does_not_catch_a_later_yes(registry, tmp_path):
    """**A candidate is over either way, and a mutation found this missing.**

    Leaving a declined candidate standing looked harmless — nothing is appended
    on the declining turn — and is not: the next thing the main says *yes* to,
    about anything at all, would land on a proposal they already refused. Half
    would delete a belief in answer to a question it asked two turns ago and was
    told no about.

    Three messages: the proposal, the refusal, and a plain yes about something
    else. Nothing is removed, and the third turn is an ordinary one.
    """
    seed(tmp_path)
    # Only the first message reads as a correction. A stub that answered
    # *correction* to everything would put a fresh candidate up on the third
    # turn and hide whether the first one was ever cleared.
    wide = widening(
        lambda work: labelled(
            CORRECTION if "these days" in work.prompt.turns[0].text
            else NO_CORRECTION
        )
    )

    corrects(
        registry, "hm, i dont think that is me these days", "no, leave it",
        "yes", corrections=wide,
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    assert wide.standing(MAIN) is None


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

    corrects(
        registry, "hm, i dont think that is me these days", answer,
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

    corrects(
        registry, "hm, i dont think that is me these days", "maybe, i am not sure",
        corrections=widening(labelled(CORRECTION)),
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)


def test_a_candidate_does_not_survive_a_turn_the_gate_answered_itself(
    registry, tmp_path
):
    """**The worst place this failure could live, and it lived there.**

    A candidate whose life was bounded only by the turn path outlived every turn
    the crisis gate answers *itself* — a disclosure, its own standing question,
    a third-party mention — because none of those reach the pipeline. The
    third-party reply ends with *"And if any of this is closer to you than you
    have said, tell me. I am here for that too."*, and the natural answer to
    that is a bare "yes". A candidate proposed two turns earlier would have read
    it as consent to delete a belief.

    Three real turns through the real gate: the proposal, a third-party
    disclosure the gate answers on its own, and the yes. Nothing is removed.

    The candidate's life is bound in ``Runtime._handle``, which every inbound
    message crosses — there is no route into Half that avoids it, which is the
    property the fix rests on rather than a list of the gate's own branches.
    """
    seed(tmp_path)
    wide = widening(labelled(CORRECTION))

    transport = corrects(
        registry,
        "hm, i dont think that is me these days",
        "my friend wants to kill herself",
        "yes",
        corrections=wide,
    )

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    assert wide.standing(MAIN) is None
    # The gate really did answer the middle turn itself: the pipeline never ran,
    # so that message was never recorded as a belief.
    assert not any(
        r.op is Op.ASSERT and "friend" in str(r.data.get("claim", ""))
        for r in log_of(tmp_path)
    )


def test_a_candidate_stands_for_exactly_one_turn(registry, tmp_path):
    """The bound stated as itself, so the rule is not *"until something else
    happens"*.

    An answer two turns later is not an answer. Without this the case above
    could pass on a build that expired candidates only on crisis turns, which is
    a list of the gate's branches rather than a property of the path.
    """
    seed(tmp_path)
    wide = widening(labelled(CORRECTION))

    corrects(
        registry, "hm, i dont think that is me these days",
        "what is the weather like", "yes", corrections=wide,
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

    corrects(
        registry, "hm, i dont think that is me these days", "that has changed",
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

    corrects(registry, "thats wrong", corrections=Widening({MAIN: Exploding()}))

    assert [r.op for r in corrections_in(tmp_path)] == [Op.RETRACT]


def test_the_widening_is_not_consulted_while_a_candidate_is_standing(
    registry, tmp_path
):
    """The main's answer is what moves next. Asking a model to read a message
    the main sent *while already being asked about it* would propose a second
    removal underneath the first."""
    seed(tmp_path)
    wide = widening(labelled(CORRECTION))
    corrects(registry, "hm, i dont think that is me these days",
             corrections=wide)
    consulted = wide.tally.consulted

    # The **immediately** next turn, because a candidate stands for exactly one:
    # a later one would find it already expired and consult, which is right, and
    # would make this case vacuous.
    a_turn(registry, texts=("hm, i dont think that is me these days",
                            "what is the weather like"),
           corrections=wide, at=NOON + 100, tag="w")

    # Two turns went by; the second had a candidate standing and must not have
    # consulted. The first re-proposed, which is one consult and no more.
    assert wide.tally.consulted == consulted + 1


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
    seed(tmp_path, sayable=SAYABLE)

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
    seed(tmp_path, sayable=SAYABLE)

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

    corrects(registry, "thats wrong", corrections=wide)

    assert [r.op for r in corrections_in(tmp_path)] == [Op.RETRACT]
    assert wide.tally.consulted == 0


def test_a_runtime_with_no_widening_still_corrects(registry, tmp_path):
    """The same sentence one layer up: correction is not a model feature."""
    seed(tmp_path)

    corrects(registry, "you were wrong about that", corrections=None)

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

    corrects(registry, *([text, "yes"] if text == "delete that" else [text]))

    assert BELIEF not in beliefs_of(tmp_path)
    standing = loops_of(tmp_path)
    assert LOOP in standing, "a correction demoted a wanting"
    assert standing[LOOP]["state"] == "stalled"
    assert standing[LOOP]["timescale"] == "years"


def test_a_correction_inside_the_mode_is_not_processed(registry, tmp_path):
    """Matrix: *in crisis*. The crisis path owns the turn.

    Structural rather than agreed: the gate never calls the turn path while the
    mode is open (``tests/test_entrypoint.py``, ``tests/test_crisis.py``), so
    there is no branch here to forget. The belief stays, which is the right
    outcome — a correction made inside the mode is a thing to handle when the
    mode is over, not a thing to lose.

    **Asserted on what the log gains, not only on what it does not remove**, and
    that is a mutation finding. *"No correction record"* survived a gate that
    called the turn path anyway, because crisis also hard-disables retrieval, so
    the correction aimed at nothing and removed nothing. Two mechanisms
    delivering one outcome is good; a test that cannot tell which one is
    working is not. Recording the main's message is the *first* thing the turn
    path does that the mode forbids, so its absence is what says the path was
    never entered.

    The companion assertion is the second half: the same message outside the
    mode removes the belief, so this case is not passing on a build where
    nothing is ever corrected.
    """
    seed(tmp_path)

    a_turn(registry, texts=(SAFE_WORD, "you were wrong about that"),
           corrections=Widening({MAIN: Exploding()}))

    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    # Nothing at all was recorded for either turn: no correction, and no belief
    # carrying the main's own message, which the turn path writes on every
    # ordinary turn and which is therefore the trace of it having run.
    assert [r.id for r in log_of(tmp_path) if r.op is Op.ASSERT] == [BELIEF]


def test_the_same_correction_outside_the_mode_does_remove(registry, tmp_path):
    """The other half of the crisis case, and without it that one passes on a
    build where no correction ever works."""
    seed(tmp_path)

    corrects(registry, "you were wrong about that")

    assert [r.op for r in corrections_in(tmp_path)] == [Op.REVISE]


#: A correction that raises the belief's own topic **in the same message**, so
#: the bought question is genuinely on offer on the turn the correction lands.
#:
#: Without this the case was vacuous in two ways at once: a correction into a
#: fresh conversation aims at nothing, and a correction on a *second* turn is
#: inside the re-ask bound of the question the first turn already bought. Both
#: produce a turn with no question available, which any rule would pass.
@pytest.mark.parametrize(
    "text",
    ["farmland: thats wrong", "farmland: delete that",
     "farmland: hm, i dont think that is me these days"],
    ids=["removal", "erasure", "candidate"],
)
def test_a_correction_turn_spends_no_favour_and_asks_no_bought_question(
    registry, tmp_path, text
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
        registry, texts=(text,), engine=True,
        corrections=widening(labelled(CORRECTION)),
    )

    assert transport.sent, "the main is still answered"
    with Store(tmp_path / MAIN) as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []
        assert balance(store.log).spent == 0
    assert "question[" not in sent(transport)


def test_the_same_main_still_gets_a_bought_question_on_an_ordinary_turn(
    registry, tmp_path
):
    """The other half of the seam, and without it the case above passes on a
    build where nobody is ever asked anything.

    Same fixture, same engine, same favour, same **single turn**, and a message
    that raises the same topic and corrects nothing — and the question arrives.
    The only difference between this case and the three above is the clause that
    makes them corrections.
    """
    seed(tmp_path, rung=License.ASK, favours=1)
    voice, holder = a_voice()

    a_turn(registry, texts=("farmland: any news",), engine=True, voice=voice)

    # **The question is in the prose now**, so the signal is the ``ask-about``
    # block the generator was handed rather than a line on the wire (13b).
    assert any(
        ASK_ABOUT in work.prompt.turns[0].text for work in holder.requests
    ), "no question reached the generator on an ordinary turn"


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
    odd = "sagt \u2014 \u0926\u093f\u0932\u094d\u0932\u0940 \u092e\u0947\u0902 \u0930\u0939\u0924\u093e \u0939\u0948, since 2019"
    seed(tmp_path, beliefs=((BELIEF, odd),))

    transport = corrects(registry, "thats wrong")

    assert odd in sent(transport)


def test_a_claim_carrying_a_line_break_is_shown_whole_and_on_one_line(
    registry, tmp_path
):
    """A claim is **attacker-influenced**: it comes from the main's own messages
    and, from story 3 on, from ingested sources.

    Story 12 folded its line breaks because the claim travelled after a marker
    — ``retract[b_x]: ...`` — and a newline forged a second marker line. Story
    13b took the marker off the wire, so there is nothing left to forge; the
    folding stays for two other reasons and both are load-bearing.

    A removal is **one message**, and a claim occupying two lines is a reply
    that reads as two. And the fold is
    ``half.context.channels.sanitize``, shared rather than approximated, so that
    ``shown`` is a fixed point of the function a ``Content`` applies at
    construction — without which the inclusion check would look for a string the
    composed reply can never contain and every correction would fall back for
    ever, with nothing failing.
    """
    forged = f"line one\n{Op.RETRACT.value}[b_fake]: totally made up"
    seed(tmp_path, beliefs=((BELIEF, forged),))

    transport = corrects(registry, "thats wrong")

    body = last(transport)
    assert "b_fake" in body, "the claim itself is still shown whole"
    assert sanitize(forged) in body
    assert body.splitlines()[-1] == sanitize(forged), "one claim, one line"


def test_a_behave_claim_reaches_the_wire_on_a_correction_turn_and_no_other(
    registry, tmp_path
):
    """**The bound on the one route this story opens through AD-18.**

    ``seed`` writes no license field, so the claim below is `behave` — the rung
    under test, not an accident of the fixture — and story 4's rule is that a
    `behave` claim's text never reaches a main. CAP-11 requires the opposite of
    exactly one turn: *"Half shows what it removed"*, and it has to be the claim
    rather than a description, because a correction is aimed by ranking and
    seeing the words is what lets the main catch a mis-aimed one.

    That is not AD-18 loosened, and the difference is what this case pins.
    AD-18 governs what enters a **constructed context** — the material a model
    is handed and may quote from — and nothing on the correction path
    constructs one. So the exception is bounded to the turn that **removes**
    something, and three halves are asserted here rather than two:

    * an ordinary turn that retrieved the belief says none of it;
    * **a turn the classifier read as a correction says none of it either.**
      This is the half the first version structurally could not see: it ran its
      negative with no classifier at all, so the proposal route — which renders
      through the same function — was excluded from the assertion. With a
      classifier answering ``correction`` on an ordinary message, a proposal
      that carried the claim would put `behave` text on the wire on a turn where
      nothing was removed and the main said nothing corrective;
    * and the removal itself does carry it.
    """
    seed(tmp_path)
    distinctive = [word for word in CLAIM.split() if len(word) > 5]
    assert distinctive, "the fixture claim must have words worth searching for"

    # A message that is not a correction, with a classifier that says it is.
    proposing = corrects(
        registry, "what did you do last weekend",
        corrections=widening(labelled(CORRECTION), on="weekend"), tag="p",
    )
    body = last(proposing)
    assert f"{Op.RETRACT.value}?[{BELIEF}]" in body, "the proposal route ran"
    assert CLAIM not in body
    for word in distinctive:
        assert word not in body, word

    # An ordinary turn that retrieved the belief and was read as nothing.
    ordinary = a_turn(registry, texts=(ON_TOPIC,), tag="o", at=NOON + 50)  # noqa: E501
    assert CLAIM not in last(ordinary)
    for word in distinctive:
        assert word not in last(ordinary), word

    # The removal, and only here.
    corrected = corrects(registry, "thats wrong", at=NOON + 100, tag="c")
    assert CLAIM in last(corrected)


def test_a_proposal_holds_no_claim_at_all_and_a_removal_holds_it_only_then(
    registry, tmp_path
):
    """The same bound, one layer in from the wire: the **candidate** carries no
    claim either.

    The case above pins what a proposal *renders*. What it cannot see is what a
    proposal *holds*: a standing candidate lives in ``Widening._standing`` in
    memory until the main answers, and until this commit it carried the belief's
    own text — a `behave` claim, half the time a proposal to destroy the body it
    was copied from, held across turns with nothing reading it. Story 12 emptied
    it and story 13b dropped the emptying while making ``plan``'s erasure carry
    the claim, which is a different function and a requirement of the matrix.

    That made the AD-18 bound one call from breaking: ``shown`` on a candidate
    would have rendered it, and ``proposed`` not doing so is a fact about one
    function rather than about the value.

    **Both halves, so the case cannot pass by nothing carrying a claim
    anywhere**: the removal the main's answer produces reads it off the fold and
    does carry it, which is what CAP-11 asks and what the erasure ordering
    exists for.
    """
    seed(tmp_path)
    belief = {"claim": CLAIM, "subject": "self"}

    offered = correction.proposal(BELIEF, belief, meaning=Meaning.ERASE)
    assert offered is not None, "the fixture proposed nothing"
    assert offered.claim == ""
    assert correction.shown(offered) == "", "a candidate can still be rendered"
    assert BELIEF in correction.proposed(offered), "and asking still works"

    removed = correction.plan(
        Meaning.ERASE, target=BELIEF, belief=belief, confirmed=True
    )
    assert correction.shown(removed) == CLAIM, (
        "the removal must show it, or this case proves nothing about the "
        "candidate"
    )

    # And through the real turn path: the candidate a proposal leaves standing
    # holds none of the main's words, while the fold still does.
    wide = widening(labelled(CORRECTION))
    corrects(registry, "hm, i dont think that is me these days",
             corrections=wide)
    standing = wide.standing(MAIN)
    assert standing is not None, "no candidate was left standing"
    assert standing.claim == ""
    assert beliefs_of(tmp_path)[BELIEF]["claim"] == CLAIM


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


#: One correction per script, from five continents, each with the meaning its
#: table gives it. The removal path is swept over all of them, so **no fixture
#: in this file makes one language the default**: every behavioural claim about
#: removal is made in eight scripts or it is not made.
#:
#: Nothing here is sliced out of a parametrization. An earlier version carried a
#: fourteenth row annotated ``None`` and excluded it from both sweeps — an
#: expectation that was never run and was also wrong.
WORLDWIDE: Final[tuple[tuple[str, Meaning], ...]] = (
    ("thats wrong", Meaning.WRONG),
    ("eso está mal", Meaning.WRONG),
    ("это неправда", Meaning.WRONG),
    ("यह गलत है", Meaning.WRONG),
    ("你说的不对", Meaning.WRONG),
    ("それは間違いです", Meaning.WRONG),
    ("هذا خطأ", Meaning.WRONG),
    ("hiyo si kweli", Meaning.WRONG),
    ("그건 틀렸어", Meaning.WRONG),
    ("ไม่ถูกต้อง", Meaning.WRONG),
    ("das war nie wahr", Meaning.NEVER_TRUE),
    ("我从来没这么说过", Meaning.NEVER_TRUE),
    ("已经不是了", Meaning.CHANGED),
    ("अब ऐसा नहीं है", Meaning.CHANGED),
    ("그거 삭제해줘", Meaning.ERASE),
)


@pytest.mark.parametrize(
    "text, expected", WORLDWIDE,
    ids=[t.replace(" ", "-") for t, _ in WORLDWIDE],
)
def test_the_table_recognises_a_correction_in_every_script_it_carries(
    text, expected
):
    """Every entry means what its table says it means, in the script it is
    written in — including the ones an unspaced-script matcher has to find
    inside a longer run."""
    assert recognize(text) is expected


@pytest.mark.parametrize(
    "text, expected", WORLDWIDE,
    ids=[t.replace(" ", "-") for t, _ in WORLDWIDE],
)
def test_a_removal_happens_in_every_script_and_none_is_the_default(
    registry, tmp_path, text, expected
):
    """The behavioural sweep. Ten scripts, one belief, one removal each.

    **The op is asserted per row**, not merely that *some* removing op was
    appended: a build that mapped every non-English correction to ``expunge``
    would otherwise pass, which is the one mistake in this area that destroys
    data. An erasure needs the main's answer, so those rows send the yes.
    """
    seed(tmp_path)
    erasing = expected is Meaning.ERASE

    corrects(registry, *((text, "yes") if erasing else (text,)))

    wanted = {
        Meaning.WRONG: Op.RETRACT,
        Meaning.CHANGED: Op.RETRACT,
        Meaning.NEVER_TRUE: Op.REVISE,
        Meaning.ERASE: Op.EXPUNGE,
    }[expected]
    assert [r.op for r in corrections_in(tmp_path)] == [wanted]
    assert BELIEF not in beliefs_of(tmp_path)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("我觉得你说的不对", Meaning.WRONG),
        ("それは間違いですよ", Meaning.WRONG),
        ("ข้อมูลไม่ถูกต้องครับ", Meaning.WRONG),
        ("我从来没这么说过啊", Meaning.NEVER_TRUE),
        ("这已经变了呢", Meaning.CHANGED),
        ("그건 틀렸어요", Meaning.WRONG),
    ],
    ids=["chinese", "japanese", "thai", "chinese-never", "chinese-changed",
         "korean"],
)
def test_a_correction_inside_an_unspaced_run_is_recognised(text, expected):
    """**The case a mutation found missing, and the reason there are two
    matchers rather than one.**

    A script that puts no spaces where words end has no clause-internal boundary
    to anchor on, so a correction written in one arrives with a word in front of
    it and a particle behind. Containment is the only matcher that can see it —
    and containment is exactly what must *not* be used on a spaced script, where
    it read *"the article says delete that button from the form"* as an erasure.

    The discipline containment costs is paid in the **rows**: one written in an
    unspaced script has to be long enough that containment is safe, which is
    what the negative sweep below enforces.
    """
    assert recognize(text) is expected


def test_a_message_past_the_tokenizers_ceiling_is_still_recognised():
    """The growth ceilings exist to bound an index, not to decide that a very
    long message cannot be a correction.

    Past them the split falls back to whole words — the crisis table's own
    behaviour, and worse only for unspaced scripts, which is a degradation
    stated rather than discovered.
    """
    from half.text import MAX_INPUT_CHARS

    long = "x" * (MAX_INPUT_CHARS + 10) + ". thats wrong"
    assert recognize(long) is Meaning.WRONG


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
    transport = corrects(
        registry, unseen,
        corrections=widening(labelled(CORRECTION), on="rangt"),
    )

    assert f"{Op.RETRACT.value}?[{BELIEF}]" in last(transport)


#: Ordinary messages, in every script the tables carry. **None of them may fire
#: on any table**, and the sweep's own coverage is asserted below, so a row
#: cannot be added in a script the negatives do not reach.
#:
#: The English-only version of this sweep was the hole. It had ten Latin
#: fixtures, so it could not see that ``"the article says delete that button
#: from the form"`` erased a belief, and adding ``ですか`` — the ordinary
#: Japanese question particle — to the *wrong* table would have left it green
#: while every Japanese question in the world removed a belief.
#:
#: Several of these are exactly the sentence a row was narrowed for, and they
#: are here so the narrowing cannot be undone quietly: ``不对称`` and ``不对劲``
#: are ordinary words, ``サイズが違います`` is a size complaint, ``ราคาไม่ถูก``
#: is *"the price isn't cheap"*, and ``그거 삭제해도 돼요`` is asking permission.
ORDINARY: Final[tuple[str, ...]] = (
    # Latin — English, and the three sentences containment used to break on
    "hi", "i finally booked the flights", "please remember this",
    "farmland again please", "i went running today", "how are you",
    "can you remind me tomorrow", "that plot of the novel was good",
    "the weather is not great today", "i am not going to the shop",
    "the article says delete that button from the form",
    "he told me thats wrong but i disagreed",
    "that is not any more expensive than the other one",
    "i used to live there and i still do",
    # Latin — Romance, Germanic, Nordic, Dutch, Turkish, Indonesian, Vietnamese
    "el precio no está mal para lo que es", "o preço não é ruim",
    "ce livre est vraiment bien écrit", "das Wetter ist heute nicht gut",
    "det stämmer bra med planen", "dat klopt met de afspraak",
    "bu yanlışlıkla oldu galiba", "harga itu salah satu yang bagus",
    "giá không đúng lắm", "habari ya asubuhi", "magandang umaga po",
    # Cyrillic, Greek, Hebrew
    "это неправдоподобно длинная история", "to nie jest takie proste",
    "αυτό είναι λάθος βιβλίο για μένα", "זה ספר טוב",
    # Arabic, Persian
    "هذا خطأ مطبعي بسيط", "این کتاب خوب است",
    # South Asia
    "यह गलत रास्ता है क्या", "এটা ভুল রাস্তা", "இது தவறான வழி",
    "ਇਹ ਚੰਗੀ ਕਿਤਾਬ ਹੈ", "ఇది మంచి పుస్తకం", "ಇದು ಒಳ್ಳೆಯ ಪುಸ್ತಕ",
    "ഇത് നല്ല പുസ്തകമാണ്",
    # Han
    "我觉得这不对称", "价格不对劲", "我从来没说过谎", "事情不是这样简单",
    "这是错的答案吗",
    # Kana
    "サイズが違います", "元気ですか", "それは違う色です", "それは間違いない",
    # Hangul
    "그건 틀린 색이야", "그거 삭제해도 돼요",
    # Thai
    "ราคาไม่ถูก",
)


@pytest.mark.parametrize("text", ORDINARY, ids=lambda t: t.replace(" ", "-")[:28])
def test_the_table_fires_on_no_ordinary_message(text):
    """The other half of a phrase table's honesty, in every script it carries.

    Every row is *acted on* with no confirmation, so a table that fired on an
    ordinary sentence removes a belief the main never questioned — and a table
    whose negatives are all English cannot see that it does so in the scripts
    this product exists to reach.
    """
    assert recognize(text) is None


def test_the_negative_sweep_reaches_every_script_the_tables_carry():
    """**A row cannot be added in a script the negatives do not reach.**

    Without this the sweep is a list somebody remembered to extend. With it,
    adding the first row in a new script fails here until an ordinary sentence
    in that script is added beside it — which is the only way the sweep can
    catch what that row breaks.
    """
    carried: set[str] = set()
    for name, _ in MEANING_FOR_TABLE:
        for row in VOCABULARY[name]:
            carried |= _scripts(row)
    reached = set().union(*(_scripts(text) for text in ORDINARY))
    assert carried <= reached, sorted(carried - reached)
    assert len(carried) >= 8, sorted(carried)


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
# the branches that only run when something is wrong
# ═════════════════════════════════════════════════════════════════════════════


def test_a_correction_that_raises_costs_the_correction_and_not_the_reply(
    registry, tmp_path, monkeypatch
):
    """**The fail-open handler, run against the fault it exists for.**

    A branch nobody has ever run is a branch nobody knows is open. Without the
    handler the exception leaves the turn path, the per-message isolation
    swallows it, and the main gets **nothing** — and their message is never
    recorded either, because the ``assert`` happens after the correction, so the
    redelivery is not suppressed but the reply is already lost.

    With it: the reply goes out, the message is recorded, and nothing is
    removed.
    """
    seed(tmp_path, sayable=SAYABLE)
    monkeypatch.setattr(
        Runtime, "_removal",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    transport = corrects(registry, "thats wrong")

    assert last(transport).strip() == SAYABLE
    assert corrections_in(tmp_path) == []
    assert BELIEF in beliefs_of(tmp_path)
    # The main's own message is recorded, which is what says the turn completed.
    assert any(
        r.op is Op.ASSERT and r.data.get("claim") == "thats wrong"
        for r in log_of(tmp_path)
    )


def test_a_run_of_failures_stands_the_widening_down(registry, tmp_path):
    """**The breaker, and the cost it exists to stop.**

    During an outage every turn would otherwise pay the whole bound and issue
    another doomed request. After ``BREAK_AFTER`` consecutive fallbacks this
    main's widening goes quiet for ``BREAK_FOR`` turns.

    Asserted on **calls the holder actually received**, not on a counter: the
    failure this prevents is latency and spend, and both are a function of the
    call happening.
    """
    calls: list[Classify] = []

    class Counting:
        async def classify(self, work: Classify):
            calls.append(work)
            return Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)

    wide = Widening({MAIN: Counting()}, bound_seconds=0.2)
    for _ in range(BREAK_AFTER + 7):
        asyncio.run(wide.consult("hm, is that me these days", main_id=MAIN))

    assert len(calls) == BREAK_AFTER, len(calls)
    assert wide.tally.skipped == 7
    assert wide.tally.fell_back == BREAK_AFTER
    # The breaker's silence is outside every rate: counting it as failure would
    # double-count one outage.
    assert wide.tally.consulted == BREAK_AFTER


def test_the_breaker_is_per_main(registry, tmp_path):
    """One main's provider being down says nothing about another's.

    **Interleaved, and one short of the trip.** A breaker keyed on the run
    across *all* mains — the natural way to write it wrongly — is invisible if
    the first main has already tripped and reset: the shared counter is back to
    zero and the second main goes through. So the first main stops one failure
    below the threshold, and the second must then be able to fail that many
    times itself. Under a shared counter it trips on its first.
    """
    calls: list[str] = []

    class Counting:
        async def classify(self, work: Classify):
            calls.append(work.prompt.main_id)
            return Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)

    wide = Widening({MAIN: Counting(), "other": Counting()}, bound_seconds=0.2)
    for _ in range(BREAK_AFTER - 1):
        asyncio.run(wide.consult("hm, is that me", main_id=MAIN))
    for _ in range(BREAK_AFTER - 1):
        asyncio.run(wide.consult("hm, is that me", main_id="other"))

    assert calls.count(MAIN) == BREAK_AFTER - 1
    assert calls.count("other") == BREAK_AFTER - 1
    assert wide.tally.skipped == 0


def test_a_good_answer_clears_the_run(registry, tmp_path):
    """The other half of the breaker: four failures and a success do not trip
    it, so a flaky provider is not treated as an outage."""
    answers = [Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)] * (
        BREAK_AFTER - 1
    ) + [labelled(NO_CORRECTION)] + [
        Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)
    ] * (BREAK_AFTER - 1)
    calls: list[object] = []

    class Scripted:
        async def classify(self, work: Classify):
            calls.append(work)
            return answers[len(calls) - 1]

    wide = Widening({MAIN: Scripted()}, bound_seconds=0.2)
    for _ in range(len(answers)):
        asyncio.run(wide.consult("hm, is that me", main_id=MAIN))

    assert len(calls) == len(answers), "the run was cleared by the good answer"
    assert wide.tally.skipped == 0


def test_what_was_proposed_and_what_was_confirmed_are_counted(
    registry, tmp_path
):
    """**The pair an operator watches, and since the proposal path is now the
    gate on `behave` text egress it is the only instrument there is.**

    A widening that proposes on every turn and is confirmed on none is a
    classifier reading corrections into ordinary conversation. Counts only —
    no message, no claim, no id (AD-22).
    """
    seed(tmp_path)
    wide = widening(labelled(CORRECTION))

    corrects(registry, "hm, i dont think that is me these days", "yes",
             corrections=wide)

    assert wide.tally.proposed == 1
    assert wide.tally.confirmed == 1


def test_a_confirmation_of_a_belief_already_gone_is_not_counted_as_a_deletion(
    registry, tmp_path
):
    """The idempotent row, arriving through the candidate path.

    If the belief left the fold between the proposal and the answer there is
    nothing to remove. Booking that as a confirmed deletion would tell an
    operator the main deleted something they did not — and the number is the
    one thing standing between a mis-reading classifier and nobody noticing.
    """
    seed(tmp_path)
    wide = widening(labelled(CORRECTION))
    transport = corrects(registry, "hm, i dont think that is me these days",
                         corrections=wide)
    assert wide.standing(MAIN) is not None

    with Store(tmp_path / MAIN) as store:
        store.record(Op.RETRACT, "co_out_of_band", "2026-09-01T13:00:00Z",
                     target=BELIEF)

    a_turn(registry, texts=("yes",), corrections=wide, at=NOON + 50, tag="z")

    assert wide.tally.proposed == 1
    assert wide.tally.confirmed == 0


def test_the_counts_are_written_out_and_carry_no_content(caplog):
    """A wholly failing widening must not be silent for as long as it takes to
    reach a round number, so the counts are flushed at shutdown as well.

    Counts and nothing else: the assertion is that the line carries numbers and
    that no claim, message or id could be in it (AD-22).
    """
    wide = widening(labelled(CORRECTION))
    wide.tally.consulted = 7
    wide.tally.proposed = 3
    with caplog.at_level(logging.INFO, logger="half.correction.candidate"):
        wide.flush()
    written = [r.getMessage() for r in caplog.records]
    assert written and "7 consulted" in written[0]
    assert "3 proposed" in written[0]
    assert CLAIM not in written[0] and BELIEF not in written[0]


def test_serve_writes_the_counts_out_on_the_way_out(tmp_path, monkeypatch, caplog):
    """A process that ran for a week proposing a deletion on every turn and
    having none confirmed would otherwise end with nothing anywhere saying so.

    Asserted through ``serve`` rather than by finding a call in the source,
    because that is how story 6d's identical claim passed with the value set to
    ``None``.
    """
    import half.__main__ as entrypoint
    from half.config import MAINS_ENV, ROOT_ENV, load

    class Recording:
        def __init__(self, **kw):
            pass

        async def run(self):
            return None

    real_build = entrypoint.build

    def build_and_count(config, token):
        wiring = real_build(config, token)
        wiring.corrections.tally.proposed = 4
        return wiring

    monkeypatch.setattr(entrypoint, "build", build_and_count)
    monkeypatch.setattr(entrypoint, "Runtime", Recording)
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    with caplog.at_level(logging.INFO, logger="half.correction.candidate"):
        asyncio.run(entrypoint.serve(config, "123:fake"))

    assert any("4 proposed" in r.getMessage() for r in caplog.records)


def test_a_widening_that_did_nothing_at_all_writes_no_line(caplog):
    """The other half: a deployment with no classifier and no candidate is not
    an event, and a line of zeros every shutdown is noise that trains an
    operator to ignore the one that matters."""
    wide = Widening()
    with caplog.at_level(logging.INFO, logger="half.correction.candidate"):
        wide.flush()
    assert not caplog.records


def test_holds_says_whether_this_main_has_a_model_at_all():
    """Read on the turn path before a consultation is built, so a main with no
    key costs nothing rather than costing a ``Verdict``."""
    wide = widening(labelled(CORRECTION))
    assert wide.holds(MAIN)
    assert not wide.holds("somebody-else")
    assert not Widening().holds(MAIN)


def test_a_main_with_no_key_is_left_unequipped_and_the_boot_survives(
    tmp_path, monkeypatch
):
    """``widening()``'s own promise, and it is the one the crisis wiring had to
    learn twice: a boot must not die here.

    A main with no credential file raises inside the provider construction, and
    the loop catches it, logs the class, and leaves that main to the offline
    table — which for correction costs almost nothing, because the table acts
    alone and only the widening needs a key.
    """
    from half import __main__ as entrypoint
    from half.config import MAINS_ENV, ROOT_ENV, load
    from half.secrets import FileSecretStore

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wide = entrypoint.widening(config, FileSecretStore.beside(config.root))

    assert isinstance(wide, Widening)
    assert not wide.holds(MAIN)


def test_a_declined_candidate_does_not_swallow_the_turn(registry, tmp_path):
    """A proposal must not cost the main the question they asked next.

    Any non-confirming message after a proposal is a decline, and a decline is
    *also* an ordinary turn: the main said something, and whatever that turn was
    going to do it still does. Before review the decline owned the turn — no
    bought question, no widening, no line — so an unrelated question landing
    right after a proposal was swallowed.
    """
    seed(tmp_path, rung=License.ASK, favours=1)
    voice, holder = a_voice()

    transport = a_turn(
        registry,
        texts=("farmland: hm, i dont think that is me these days",
               "farmland: any news"),
        engine=True, corrections=widening(labelled(CORRECTION)), voice=voice,
    )

    assert corrections_in(tmp_path) == []
    assert f"{Op.RETRACT.value}?[" in transport.sent[0][1], "the proposal ran"
    # The declining turn still asks — in the prose, so the signal is the block
    # the generator was handed rather than a line on the wire (story 13b).
    assert any(
        ASK_ABOUT in work.prompt.turns[0].text for work in holder.requests
    ), "the declining turn still asks"


def test_a_removal_is_shown_and_is_the_whole_of_what_the_turn_says(
    registry, tmp_path
):
    """CAP-11's success criterion does not depend on there being anything else
    to say — and it is not diluted by there being something else either.

    Two halves, and the second is story 13b's. The turn's material carries a
    claim Half is licensed to state, quite unrelated to the correction; the
    reply is the **removed** claim and not that one. A correction turn is about
    the belief that left, and a reply that answered *"that's wrong"* with an
    unrelated statement would be Half changing the subject at the one moment the
    main is checking its work.

    Before review the ordering was inverted: returning early on an empty reply
    left the belief gone durably, the candidate consumed, and *"Half shows what
    it removed"* silently not happening.
    """
    seed(tmp_path, sayable=SAYABLE)

    transport = corrects(registry, "thats wrong")

    assert [r.op for r in corrections_in(tmp_path)] == [Op.RETRACT]
    assert last(transport) == CLAIM
    assert SAYABLE not in last(transport), (
        "a correction turn is about the belief that left"
    )


def test_two_corrections_inside_one_second_are_two_records(registry, tmp_path):
    """The append's id carries the target as well as the stamp.

    Two messages can arrive with the same transport timestamp — they routinely
    do — and without the discriminator the two corrections shared an id and were
    appended silently. Every neighbouring id in the tree carries one.
    """
    seed(tmp_path)
    with Store(tmp_path / MAIN, prefix=build_prefix) as store:
        store.record(Op.ASSERT, OTHER, "2026-08-01T00:02Z", claim=OTHER_CLAIM,
                     subject="self", topics=["bees"],
                     **ladder.admitted(support=["s_bee"]))

    # Each message raises its own topic in its own clause, so each turn aims at
    # its own belief — and both carry the same transport timestamp.
    at = int(NOON)
    transport = FakeTransport([
        msg(text="farmland: thats wrong", message_id="m1", chat_id="123",
            date=at),
        msg(text="bees: thats wrong", message_id="m2", chat_id="123", date=at),
    ])
    channel = TelegramChannel(transport=transport, mains={"123": MAIN})
    asyncio.run(Runtime(channel=channel, registry=registry).run())

    recorded = corrections_in(tmp_path)
    assert len(recorded) == 2, [r.id for r in recorded]
    assert len({r.id for r in recorded}) == 2, [r.id for r in recorded]
    assert {r.data[TARGET] for r in recorded} == {BELIEF, OTHER}


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
def test_an_erasure_cannot_be_planned_without_an_answer_however_it_was_read():
    """**The second refusal, at the same function, and it is not the first one
    in disguise.**

    An erasure recognised by the **offline table** carries ``Source.TABLE``, so
    the inference refusal does not apply to it — and every other meaning from
    the table is applied directly. This is the one that is not, because an
    erasure tombstones the body: the recovery argument that makes a mis-aimed
    removal survivable is false for exactly this meaning.
    """
    with pytest.raises(CorrectionError):
        correction.plan(
            Meaning.ERASE, target=BELIEF, belief={"claim": CLAIM},
            source=Source.TABLE,
        )
    assert correction.NEEDS_ANSWER == frozenset({Meaning.ERASE})
    # The other three from the table go through untouched.
    for meaning in set(Meaning) - correction.NEEDS_ANSWER:
        assert correction.plan(
            meaning, target=BELIEF, belief={"claim": CLAIM},
            source=Source.TABLE,
        ) is not None


@pytest.mark.parametrize("stamp_name", [EXPIRED_AT, INVALID_AT],
                         ids=["expired-at", "invalid-at"])
@pytest.mark.parametrize("op", [Op.ASSERT, Op.LOOP_TRANSITION, Op.CEILING,
                                Op.CRISIS],
                         ids=lambda o: o.value)
def test_a_cause_may_not_be_written_on_an_op_that_removes_nothing(op, stamp_name):
    """The two stamps are the whole of why a belief **left**, so an op that
    removes nothing has no cause to record.

    Before review an ``expired_at`` on an ``assert`` passed every gate: durable,
    on an append-only log, carrying an attribution nothing had checked, and
    skipped by the reader — a field that reads as an answer and is consulted by
    nothing.

    The four ops here are the ones with no field allowlist of their own.
    ``tension``, ``touch`` and ``asked`` already refuse every stray field,
    including these two, and refuse it as their own error — which is the right
    error for them and is asserted where those allowlists are.
    """
    fields: dict[str, object] = {}
    if op is Op.LOOP_TRANSITION:
        fields = {"loop": LOOP}
    elif op is Op.CEILING:
        fields = {"rung": "behave"}
    elif op is Op.CRISIS:
        fields = {"state": "entered"}
    with pytest.raises(CorrectionError):
        make(op, "x_1", NOW, **fields, **{stamp_name: NOW})


@pytest.mark.cap11_structure
def test_the_table_registry_cannot_desync(monkeypatch):
    """A table defined and never consulted fires on nothing and reads in review
    as coverage; one renamed in a single place raises ``KeyError`` **on the turn
    path**, which is a main losing their reply to a dictionary key.

    Run against both mutations, because a guard nobody has run against the thing
    it forbids is a guard nobody knows the reach of.
    """
    from half.correction import signals as table

    monkeypatch.setitem(table.VOCABULARY, "orphan", ("never consulted",))
    with pytest.raises(CorrectionError):
        table._check_tables()
    monkeypatch.undo()

    monkeypatch.setattr(
        table, "MEANING_FOR_TABLE",
        (*table.MEANING_FOR_TABLE, ("renamed", Meaning.WRONG)),
    )
    with pytest.raises(CorrectionError):
        table._check_tables()


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
def test_what_half_shows_is_made_of_the_claim_and_nothing_this_module_wrote():
    """*"No generated prose"* as a property of the module, not of its output.

    Every string constant in ``apply.py`` outside a docstring and outside a
    ``raise`` is either punctuation, a field name, or an enum value — there is
    no word here a main could read that Half composed. Since story 13b a
    removal is the claim alone, so even the op's own name no longer reaches a
    main; what is left is the proposal's brackets and the record-field names.

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
    # Punctuation, the two enum values, and the record-field names ``aim``
    # reads off a ranked candidate. Not one of them is a word a main could read.
    #
    # **Tightened by story 13b rather than left where it was.** The join and the
    # line-break table are gone with the marker they served, and an ``allowed``
    # set kept wider than the module needs is room for a word to arrive in
    # without anything failing.
    allowed = {"[", "]", "?", "", "_", "co_", "table", "inferred",
               "claim", "belief", "weights", "strand", "id", "t"}
    assert set(literals) <= allowed, sorted(set(literals) - allowed)


@pytest.mark.cap11_structure
def test_the_removal_is_the_claim_alone_and_the_proposal_names_no_claim():
    """The two renderings, and what each of them may carry (13b).

    A **removal** is the claim and nothing else: no op name, no id, no bracket,
    no framing word, in any language. Until story 13b it was
    ``retract[b_land]: ...`` and that string went to a person.

    A **proposal** is still the op with a question mark and the id, and
    deliberately not the claim — a proposal is Half asking about a belief it may
    not be licensed to quote. That line is the one piece of the serialization
    story 13b leaves on the wire, and ``half.correction.apply.proposed`` records
    why: there is nothing to compose prose from and dropping it would silence
    the question that stands between an inference and a destroyed body.
    """
    removal = Removal(target=BELIEF, op=Op.RETRACT,
                      attribution=Attribution.NOT_YET_KNOWN, claim=CLAIM)
    assert correction.shown(removal) == CLAIM
    assert BELIEF not in correction.shown(removal)
    assert Op.RETRACT.value not in correction.shown(removal)
    assert correction.proposed(removal) == f"retract?[{BELIEF}]"
    assert CLAIM not in correction.proposed(removal)


@pytest.mark.cap11_structure
def test_the_inclusion_check_is_defined_over_the_fallback_it_falls_back_to():
    """The property that stops CAP-11's check becoming a permanent silence.

    ``shows`` is defined over ``shown``'s own output, so the fallback satisfies
    it **by construction**: there is no claim for which the check refuses
    everything the turn is able to send. A check and a fallback that could
    disagree is a check that silences a main every time it fires.

    Swept over claims a second normalization would damage — a line break, a
    control character, leading space, a Devanagari matra, a Khmer dependent
    vowel — because a check that folded or trimmed before comparing would hold
    for Latin prose and fail for the scripts this product exists to reach.
    """
    for claim in (
        CLAIM,
        "line one\nline two",
        "  padded  ",
        "\u0645\u0627\u0631\u0633 \u0645\u0646\u0630 \u0627\u0644\u0623\u0631\u0636 \u062a\u0644\u0643 \u064a\u0632\u0631 \u0644\u0645",
        "\u092e\u093e\u0930\u094d\u091a \u0938\u0947 \u0909\u0938 \u0916\u0947\u0924 \u092a\u0930 \u0928\u0939\u0940\u0902 \u0917\u092f\u093e",
        "\u1798\u17b7\u1793\u1794\u17b6\u1793\u1791\u17c5\u1785\u1798\u17d2\u1780\u17b6\u179a\u1793\u17c4\u17c7",
        "one\x07two",
    ):
        removal = Removal(target=BELIEF, op=Op.RETRACT,
                          attribution=Attribution.NOT_YET_KNOWN, claim=claim)
        spare = correction.shown(removal)
        assert spare, claim
        assert correction.shows(spare, removal), claim
        # And the fixed point the check rests on: what a ``Content`` does to the
        # claim on its way to the model is what ``shown`` already did.
        assert Content(id=BELIEF, claim=spare).claim == spare, claim
        assert not correction.shows("nothing of the sort", removal), claim
        # **Verbatim means verbatim.** A check that folded case, or stripped
        # punctuation, or normalized before comparing would accept prose that
        # does not carry the main's own words — which is the whole thing being
        # checked, and it would pass every Latin case while silently accepting
        # a re-cased Cyrillic or Greek claim.
        if spare.lower() != spare:
            assert not correction.shows(spare.lower(), removal), claim
        if spare.upper() != spare:
            assert not correction.shows(spare.upper(), removal), claim


@pytest.mark.cap11_structure
def test_a_removal_with_no_readable_claim_shows_nothing_and_refuses_nothing():
    """The one case where a waiting main is answered with silence.

    A record whose claim this build cannot read removes nothing anybody can be
    shown. ``shown`` answers ``""``, which the turn reads as *no claim to fall
    back to*; ``shows`` answers ``True``, because refusing every possible reply
    would answer a main's correction with nothing at all on top of it.
    """
    for claim in ("", None, 7):
        removal = Removal(target=BELIEF, op=Op.RETRACT,
                          attribution=Attribution.NOT_YET_KNOWN, claim=claim)
        assert correction.shown(removal) == ""
        assert correction.shows("anything", removal)
    assert correction.shown(None) == ""
    assert correction.shows("anything", None)


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
    from tests.conftest import LIFTED, UNREACHABLE

    # **The exemption table is pinned to its documented entries**, beside the
    # rules they exempt. Adding a line — ``"half/questions": ("half.model",)`` —
    # plus a model import in that package left the whole suite green, which
    # means the rule story 11 fixed could be undone by a one-line edit in a test
    # helper. The lift is also recomputed here rather than read from the table,
    # so this case says what it means with or without it.
    #
    # Story 13a adds the second entry, deliberately: ``half/voice`` composes the
    # morning's sentence through the port, so a model there is the subject
    # rather than a leak. It pays for its lift with the same kind of stricter
    # rule this case is — a narrow *generator* refused at construction unless
    # ``generate`` is its only public method — and ``tests/test_voice.py``
    # asserts this same mapping from its own side, so neither entry can be added
    # by editing one file.
    assert LIFTED == {
        "half/correction": ("half.model",),
        "half/voice": ("half.model",),
    }, LIFTED
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


@pytest.mark.cap11_structure
def test_serve_hands_the_runtime_the_widening_build_made(tmp_path, monkeypatch):
    """The other half, and the half a wiring test alone does not give.

    ``build`` making one proves nothing if ``serve`` does not pass it. Asserted
    by **identity**, off the object the runtime was actually given, because a
    check that a keyword appeared in the call passes with the value set to
    ``None`` — which is how story 6d's identical claim once passed.
    """
    import half.__main__ as entrypoint
    from half.config import MAINS_ENV, ROOT_ENV, load

    captured: dict[str, object] = {}
    made: dict[str, object] = {}

    class Recording:
        def __init__(self, *, channel, registry, second=None, questions=None,
                     corrections=None, voice=None):
            captured["corrections"] = corrections

        async def run(self):
            return None

    real_build = entrypoint.build

    def build_and_remember(config, token):
        wiring = real_build(config, token)
        made["wiring"] = wiring
        return wiring

    monkeypatch.setattr(entrypoint, "build", build_and_remember)
    monkeypatch.setattr(entrypoint, "Runtime", Recording)

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    asyncio.run(entrypoint.serve(config, "123:fake"))

    assert isinstance(captured["corrections"], Widening)
    assert captured["corrections"] is made["wiring"].corrections
