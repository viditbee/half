"""CAP-2 story 7: the demonstration — the first thing Half ever says.

One case per row of the story's matrix, plus the structural rules the story
rests on and the two numbers it is accountable for.

Five things this file refuses to do, because each would let it pass while the
product failed:

**It never asserts *"nothing was offered"* on its own.** That is true of a main
in crisis, a deployment with no notice, a deployment with no composer, a
mailbox with one thread in it, a mailbox with nothing falsifiable in it, a
budget that ran out and a platform that would not carry a message. Every case
below says which of the seven it is about and asserts a ``Reason`` that only
that one produces.

**The negative half of the AD-18 bound runs with the demonstration wired.** The
first exception (story 12's correction reply) had its negative tested against a
runtime with no classifier, which removed the very route the assertion claimed
to bound; 13b's review found it. So the case here runs the demonstration for
real, leaves an offer standing, and *then* drives an ordinary turn through the
real runtime with that same claim in the ranked set — and the composing double
is ``conftest.echo``, which puts on the wire whatever the may-be-said block
licensed. A fixed-string double would satisfy every *"the claim did not reach
the wire"* assertion in this file whether the exception was bounded or not.

**It separates *the wording was quoted* from *the rung moved*.** A claim
offered for confirmation is quoted and is still `behave`; a claim the main
confirmed is `assert` and carries ``known_to_main``. A case that only looked at
the wire would pass with the ladder bypassed, and one that only looked at the
ledger would pass with the main never shown a word.

**It asserts the ninety seconds twice, because the two answers are different
questions.** The wall clock says what the offline path costs; the arithmetic
over the shipped bounds says how many messages fit in the worst case, and that
number is small. The second is the one that matters and the one nobody had
computed.

**It hunts a pleasantry.** Where nothing clears the gates, no claim, no
composed sentence and no word of Half's own reaches the wire — asserted against
the provider's call count, not only against the text.

Offline throughout: every holder is the port's narrow ``Generator`` or
``Classifier``, stubbed, and nothing here opens a socket.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import time
import unicodedata
from pathlib import Path
from typing import Final

import pytest

from half.__main__ import (
    CONSENT_ENV,
    NOTHING_YET_ENV,
    Bounded,
    build,
    ingest_mail,
    notices,
    onboard,
)
from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.port import Reachability, SendResult
from half.channel.telegram import TelegramChannel
from half.config import MAINS_ENV, ROOT_ENV, load
import half.context as context_package  # noqa: E402 - the package, not
# the function: ``half.context.__init__`` re-exports ``build``, which
# shadows the submodule of the same name, so ``from half.context import
# build`` binds a function. The first version of the case below did
# exactly that and asserted `not hasattr(<function>, "split")`, which is
# true of every function there has ever been — a probe that added the
# re-export walked straight past it.
from half.context.build import build as build_context
from half.context.build import offered_claim, split, withheld as withheld_wordings
from half.correction.attribute import EXPIRED_AT, INVALID_AT
from half.correction.signals import (
    ANSWERS,
    CONFIRM,
    DECLINE,
    DECLINE_SOURCE,
    MEANING_FOR_TABLE,
    VOCABULARY,
    Meaning,
    is_confirmation,
    is_decline,
    recognize,
)
from half.derive.claim import BOUND_SECONDS as GATE_BOUND
from half.derive.gates import (
    FALSIFIABILITY,
    GATES,
    NOT_CHECKABLE,
)
from half.derive.revealed import (
    BOUND_SECONDS as READ_BOUND,
    DOINGS,
    MIN_INDEPENDENT,
    PER_RUN,
    REVEALED,
    Revealed,
)
from half.derive.claim import Derivers
from half.errors import LadderError, OnboardError
from half.governance import ladder
from half.governance.ladder import Ceiling, License
from half.ingest.port import Message
from half.model.port import Decision, Usage
from half.onboard import consent as consenting
from half.onboard.consent import (
    JOIN,
    LEAVES_THE_MACHINE,
    NOTHING_TOLD,
    NOTICES,
    Consent,
)
from half.onboard.flow import (
    BUDGET_SECONDS,
    COMPOSE_SECONDS,
    Answer,
    Demonstration,
    Offer,
    Outcome,
    Reason,
    answered,
    chosen,
    demonstrate,
    meaning_of,
    messages_that_fit,
    offerable,
    reading,
)
from half.retrieval.port import Candidate, Ranked
from half.retrieval.prefix import build_prefix
from half.store.ops import Op
from half.store.records import CLAIM, LEDGER, SUBJECT
from half.store.store import Store
from half.voice.compose import MAY_BE_SAID, WORD_FOR_WORD
from half.voice.gate import Voice

from tests.conftest import (
    FakeTransport,
    NeverGenerates,
    a_voice,
    block_of,
    msg,
    seed_belief,
    stub_voice,
)

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"
NOW = "2026-09-04T09:00:00Z"

#: The label every mailbox double answers with unless a case says otherwise,
#: and the claim and belief id 15b writes for it.
TRAVELS: Final[str] = DOINGS[0].label
TRAVEL_CLAIM: Final[str] = DOINGS[0].claim
TRAVEL_ID: Final[str] = f"r_{TRAVELS}"

#: A second label, so *"exactly one is offered"* has something to be exactly one
#: of, and so the choice can be shown to be a choice.
BUYS: Final[str] = DOINGS[2].label
BUYS_CLAIM: Final[str] = DOINGS[2].claim
BUYS_ID: Final[str] = f"r_{BUYS}"

#: The deployment's own sentence, in the main's own language. **Half ships
#: none**, so this file supplies one — and supplies it in several scripts,
#: because a fixture with one language in it is a product with one language in
#: it, arriving through the test suite.
NOTICE: Final[str] = "your messages are read by a machine that is not on this device"

#: The same sentence, elsewhere. None is a translation checked by anybody; the
#: point is that no rule anywhere on this path reads them.
NOTICES_IN: Final[dict[str, str]] = {
    "latin": NOTICE,
    "devanagari": "आपके संदेश इस डिवाइस से बाहर जाते हैं",
    "arabic": "رسائلك تغادر هذا الجهاز",
    "japanese": "あなたのメッセージはこの端末の外に出ます",
    "amharic": "መልእክቶችዎ ከዚህ መሣሪያ ይወጣሉ",
    "thai": "ข้อความของคุณออกจากเครื่องนี้",
}

#: What Half says when a pull found nothing. Deployment copy for the notice's
#: reason, and empty is silence.
NOTHING_YET: Final[str] = "nothing yet that I could check with you"

TOLD: Final[Consent] = Consent({LEAVES_THE_MACHINE: NOTICE})


# ═════════════════════════════════════════════════════════════════════════════
# doubles
# ═════════════════════════════════════════════════════════════════════════════


class Wire:
    """The whole ``Channel`` surface the demonstration touches.

    ``sent`` is public and is deliberately not a callable: a case that needs to
    assert nothing reached a main has to be able to ask, and *"an exception was
    raised somewhere"* is not that question — ``demonstrate`` catches a send
    fault by design.
    """

    name = "wire"

    def __init__(self, *, reach=Reachability.OPEN, parts=1, fail=None) -> None:
        self.reach = reach
        self.parts = parts
        self.fail = fail
        self.sent: list[str] = []

    async def send(self, main_id: str, text: str) -> SendResult:
        if self.fail is not None:
            raise self.fail
        self.sent.append(text)
        return SendResult(external_id=f"m{len(self.sent)}", parts=self.parts)

    def capability_query(self, main_id: str) -> Reachability:
        return self.reach

    @property
    def wire(self) -> str:
        return "\n".join(self.sent)


class FakeMail:
    """The whole surface the pipeline needs, so cases stay offline."""

    name = "fake"

    def __init__(self, messages, *, sleep: float = 0.0) -> None:
        self.messages = messages
        self.sleep = sleep

    async def fetch(self, *, since=None):
        for message in self.messages:
            if self.sleep:
                await asyncio.sleep(self.sleep)
            if since is None or message.t > since:
                yield message


def mail(index, body, *, thread="t1", sender="a@x", subject="s"):
    return Message(
        external_id=f"m{index}", thread_id=thread, sender=sender,
        subject=subject, body=body.encode(),
        t=f"2026-08-{index + 1:02d}T00:00:00Z", headers={},
    )


#: Two messages that share nothing — two senders, two threads, two bodies — so
#: the union-find finds two independent groups and one claim is admitted.
INDEPENDENT: Final[tuple] = (
    mail(0, "your booking is confirmed", thread="t1", sender="a@x"),
    mail(1, "your itinerary", thread="t2", sender="b@y"),
)

#: The same content, one thread. **One** independent group, so nothing is
#: admitted — 15b's rule, unchanged, reached through the demonstration.
ONE_CLUSTER: Final[tuple] = (
    mail(0, "your booking is confirmed", thread="t1", sender="a@x"),
    mail(1, "re: your booking is confirmed", thread="t1", sender="a@x"),
)


class GateHolder:
    """15a's narrow classifier, answering for the four gates.

    ``answers`` maps a gate's **name** to a label; anything unnamed admits.
    Keyed by gate rather than by call order because the four gates run
    concurrently.
    """

    def __init__(self, answers=None) -> None:
        self._answers = dict(answers or {})
        self.seen: list = []

    async def classify(self, work):
        self.seen.append(work)
        for gate in GATES:
            if tuple(work.labels) == gate.labels:
                answer = self._answers.get(gate.name, gate.admits)
                return Decision(label=answer, usage=Usage(micro_usd=11))
        raise AssertionError(f"no gate owns the label set {work.labels}")

    @property
    def calls(self) -> int:
        return len(self.seen)


class ReadHolder:
    """The narrow classifier that answers *what does this show they do*."""

    def __init__(self, answers=TRAVELS) -> None:
        self._answers = list(answers) if isinstance(answers, list) else [answers]
        self.seen: list = []

    async def classify(self, work):
        self.seen.append(work)
        answer = self._answers[min(len(self.seen) - 1, len(self._answers) - 1)]
        return Decision(label=answer, usage=Usage(micro_usd=11))

    @property
    def calls(self) -> int:
        return len(self.seen)


def a_reader(answers=TRAVELS, *, gates=None, main=MAIN):
    """A ``Revealed``, and the two holders inside it."""
    gate_holder = GateHolder(gates)
    read_holder = ReadHolder(answers)
    reader = Revealed(
        {main: read_holder},
        gates=Derivers({main: gate_holder}, bound_seconds=1.0),
        bound_seconds=1.0,
    )
    return reader, read_holder, gate_holder


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path / "mains")
    yield reg
    reg.close()


def a_claim(root, *, main_id=MAIN, ident=TRAVEL_ID, claim=TRAVEL_CLAIM,
            support=("m0", "m1"), independent=MIN_INDEPENDENT,
            confirmed=False):
    """One admitted revealed claim, written the way ``ingest_mail`` writes it.

    Through ``ladder.admitted`` and never by spelling a license field, which is
    story 5a's writer rule and ``conftest.seed_belief``'s reason for existing.
    """
    with Store(root / main_id, prefix=build_prefix) as store:
        seed_belief(
            store, ident, "2026-09-04T08:00:00Z",
            claim=claim, subject="self", ledger=REVEALED, derivation="derived",
            independent=independent, support=list(support),
            rung=License.ASSERT if confirmed else License.BEHAVE,
        )
        return store.state().beliefs[ident]


def a_demonstration(registry, *, consent=TOLD, wire=None, voice=None,
                    pull=None, plainly="", budget=BUDGET_SECONDS,
                    main_id=MAIN, t=NOW):
    """Run one demonstration and hand back what it produced and the wire."""
    channel = wire if wire is not None else Wire()
    return asyncio.run(demonstrate(
        main_id=main_id, consent=consent, channel=channel, registry=registry,
        pull=pull, voice=stub_voice(mains=(main_id,)) if voice is None else voice,
        t=t, plainly=plainly, budget_seconds=budget,
    )), channel


def a_pull(wiring, source, *, main_id=MAIN):
    """The mailbox pull the shipped composition hands the demonstration."""
    async def pull():
        return await ingest_mail(wiring, main_id=main_id, source=source)

    return pull


def a_wiring(tmp_path, *, reader=None, voice=None, consent=TOLD,
             nothing_yet="", channel=None, main_id=MAIN):
    """The real ``Wiring``, with the doubles this file needs swapped in.

    Built through ``half.__main__.build`` rather than assembled here, so what a
    case drives is the shipped object graph and not a nearby one.
    """
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{main_id}"})
    wiring = build(config, token="123:fake")
    swaps = {"consent": consent, "nothing_yet": nothing_yet}
    if reader is not None:
        swaps["revealed"] = reader
    if voice is not None:
        swaps["voice"] = voice
    if channel is not None:
        swaps["channel"] = channel
    return type(wiring)(**{
        **{f: getattr(wiring, f) for f in wiring.__dataclass_fields__},
        **swaps,
    })


def candidate_of(belief, ident=TRAVEL_ID):
    return Candidate(id=ident, claim=belief[CLAIM], prefix="", bm25=None,
                     belief=belief)


def _scripts(text: str) -> set[str]:
    found = set()
    for char in text:
        if not char.isalpha():
            continue
        name = unicodedata.name(char, "")
        if name:
            found.add(name.split()[0])
    return found


# ═════════════════════════════════════════════════════════════════════════════
# matrix: told first — before the source is connected
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
def test_the_notice_reaches_the_main_before_a_single_message_is_read(registry):
    """Matrix: *told first*. **The launch blocker's own moment.**

    Not *"a notice exists"* and not *"a notice was sent"* — the **ordering**,
    asserted by a pull that records when it ran against a wire that records when
    it was written to. Half reads somebody's mail and hands the bodies to a
    model provider; the sentence saying so has to arrive before any of that,
    or the main consented to something that had already happened.
    """
    order: list[str] = []
    channel = Wire()

    class Recording(Wire):
        async def send(self, main_id, text):
            order.append("told")
            return await Wire.send(self, main_id, text)

    channel = Recording()

    async def pull():
        order.append("read")

    result, _ = a_demonstration(registry, wire=channel, pull=pull)

    assert order[:2] == ["told", "read"], order
    assert channel.sent[0] == NOTICE, "the notice is not what was sent first"
    assert result.reason is Reason.NO_CLAIM


@pytest.mark.cap2
def test_the_notice_is_its_own_message_and_never_a_footer(registry, tmp_path):
    """Matrix: *told first* — *"plainly, not in a footer"*.

    The whole content of the rule is that the sentence is not carried under
    something more interesting. Asserted as **two sends**, with the notice
    complete in the first and absent from the second, rather than as a
    substring of one message — a footer satisfies a substring check exactly.
    """
    a_claim(tmp_path / "mains")

    async def pull():
        return None

    result, channel = a_demonstration(registry, pull=pull)

    assert result.reason is Reason.DEMONSTRATED, result
    assert len(channel.sent) == 2, channel.sent
    assert channel.sent[0] == NOTICE
    assert NOTICE not in channel.sent[1], "the notice arrived as a footer"


@pytest.mark.cap2
def test_a_deployment_with_no_notice_connects_no_mailbox(registry):
    """Matrix: *told first*, the fail-closed half.

    ``told`` is false, so nothing is connected and nothing is read — asserted
    against a pull that would record having run. The alternative direction is
    reading somebody's mail on the strength of a sentence they never saw, which
    is the harm the sentence exists to prevent.
    """
    ran: list[int] = []

    async def pull():
        ran.append(1)

    result, channel = a_demonstration(registry, consent=NOTHING_TOLD, pull=pull)

    assert result.reason is Reason.NOT_TOLD
    assert ran == [], "a mailbox was read for a main who was told nothing"
    assert channel.sent == [], "something was said to a main with no notice"


@pytest.mark.cap2
def test_a_notice_the_platform_did_not_carry_connects_no_mailbox(registry):
    """Matrix: *told first* — **attempted is not told.**

    ``SendResult.parts`` of zero is the contract ``half.channel.port`` states
    for a body the platform would not carry, and an adapter may answer it
    instead of raising. A demonstration that read that as *told* would connect
    a mailbox for a main who saw nothing.
    """
    ran: list[int] = []

    async def pull():
        ran.append(1)

    result, _ = a_demonstration(registry, wire=Wire(parts=0), pull=pull)

    assert result.reason is Reason.NOTICE_NOT_SENT
    assert ran == []


@pytest.mark.cap2
@pytest.mark.parametrize("script", sorted(NOTICES_IN), ids=sorted(NOTICES_IN))
def test_the_notice_is_the_deployments_own_sentence_in_any_script(
    script, registry, tmp_path
):
    """Matrix: *any script*, at the one place Half must speak before it knows
    anything about the main.

    The notice is also the **language sample** the first composition is written
    from — it is the only text of the main's language Half holds before they
    have written a word — so a rule anywhere on this path that only noticed
    Latin would show here.
    """
    said = NOTICES_IN[script]
    a_claim(tmp_path / "mains")
    voice, holder = a_voice(main=MAIN)

    async def pull():
        return None

    result, channel = a_demonstration(
        registry, consent=Consent({LEAVES_THE_MACHINE: said}),
        voice=voice, pull=pull,
    )

    assert result.reason is Reason.DEMONSTRATED, result
    assert channel.sent[0] == said
    from half.voice.compose import LANGUAGE_SAMPLE
    assert block_of(holder.requests[0], LANGUAGE_SAMPLE) == said


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the demonstration
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
def test_one_oauth_and_a_mailbox_yield_one_claim_offered_in_prose(tmp_path):
    """Matrix: *the demonstration*. **The story, end to end, in the shipped
    composition.**

    ``build`` is driven for real and one mailbox with two independent supports
    is pulled through ``half.__main__.onboard`` — the only path in the tree from
    an OAuth to a statement. A surface reachable only from a test is a surface
    nobody has run, and this project has shipped three of them.

    What is asserted is all four halves of CAP-2's sentence: exactly one claim
    is offered, its words are on the wire, the belief is **still `behave`**
    because nothing has been confirmed yet, and no form, list or label went out
    with it.
    """
    voice, holder = a_voice()
    reader, _, _ = a_reader()
    wire = Wire()
    wiring = a_wiring(tmp_path, reader=reader, voice=voice, channel=wire)
    try:
        result = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(INDEPENDENT)), t=NOW,
        ))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
    finally:
        wiring.registry.close()

    assert result.reason is Reason.DEMONSTRATED, result
    assert result.offer == Offer(belief_id=TRAVEL_ID, claim=TRAVEL_CLAIM)
    assert TRAVEL_CLAIM in wire.sent[1], wire.sent
    # Still `behave`. Nothing has been confirmed, so nothing has moved.
    assert beliefs[TRAVEL_ID]["license"] == str(ladder.FLOOR)
    assert ladder.known_to_main(beliefs[TRAVEL_ID]) is False
    # No form: no label, no belief id, no channel scaffolding on the wire.
    assert TRAVEL_ID not in wire.wire
    assert MAY_BE_SAID not in wire.wire and WORD_FOR_WORD not in wire.wire


@pytest.mark.cap2
def test_the_offer_carries_the_claim_verbatim_or_nothing_is_sent(registry, tmp_path):
    """Matrix: *the demonstration*, at the point that makes it checkable.

    The main can only confirm words they were shown, so the composed message
    must contain the claim character for character. That is
    ``half.correction.apply.shows``, reached through ``half.voice.turn.words``'
    own inclusion check — **called and not restated**, which is 13b's lesson: an
    inline comparison and the function every case is written against agreed only
    by coincidence.

    Both halves, so the case cannot pass by nothing ever being sent: prose that
    carries the claim goes out, and prose that paraphrases it does not.
    """
    a_claim(tmp_path / "mains")

    faithful, _ = a_demonstration(
        registry, voice=stub_voice(f"here is a thing: {TRAVEL_CLAIM}"))
    assert faithful.reason is Reason.DEMONSTRATED

    paraphrase, channel = a_demonstration(
        registry, voice=stub_voice("you seem to get about a fair bit"))
    assert paraphrase.reason is Reason.NOT_COMPOSED
    assert paraphrase.offer is None, "an offer stands for a message never sent"
    assert channel.sent == [NOTICE], channel.sent


@pytest.mark.cap2
def test_a_failed_generation_says_nothing_rather_than_the_bare_claim(
    registry, tmp_path
):
    """Matrix: *the demonstration* — **and the second half of the AD-18 bound.**

    ``half.voice.turn.words`` falls back to the claim alone on a turn, because
    a main who has just written is waiting and silence reads as broken. Here
    that fallback would put a `behave` claim on the wire **unframed**, which
    reads as a statement Half has made rather than one it is asking about — so
    the demonstration refuses it. The wording reaches a main only inside prose
    that passed the judge, the tripwire and the inclusion check.

    Asserted against a holder that *counts*, because ``Voice`` turns a raised
    ``AssertionError`` into an ordinary silence: a double whose only signal is a
    raise passes whether or not the fallback fired.
    """
    a_claim(tmp_path / "mains")
    dead = Voice({MAIN: NeverGenerates()}, bound_seconds=1.0)

    result, channel = a_demonstration(registry, voice=dead)

    assert result.reason is Reason.NOT_COMPOSED
    assert channel.sent == [NOTICE]
    assert TRAVEL_CLAIM not in channel.wire, (
        "the bare claim went out as a statement Half had not earned"
    )


@pytest.mark.cap2
def test_exactly_one_claim_is_offered_where_several_qualify(registry, tmp_path):
    """Matrix: *one, not many*. **A list is a form** (CAP-4).

    Two claims are admitted and one is offered — asserted by the *other* one's
    words being absent from the wire, not merely by ``offer`` being singular,
    which it is by type and would be true of a message carrying both.

    The choice is the better-corroborated one, which is the union-find's answer
    and is arithmetic rather than a judgement about words — so it is the same
    choice in every script and on every replay.
    """
    root = tmp_path / "mains"
    # **The two orderings are made to disagree.** ``r_buys_things`` sorts before
    # ``r_travels``, so a build that took the first id it saw would choose the
    # same claim as one that took the best-corroborated — and a mutation probe
    # found exactly that: replacing the independence count with a constant left
    # this case green. The better-supported claim is therefore the one the id
    # order would *not* pick.
    assert BUYS_ID < TRAVEL_ID, "the two orderings no longer disagree here"
    a_claim(root, ident=TRAVEL_ID, claim=TRAVEL_CLAIM, independent=3,
            support=("m0", "m1", "m2"))
    a_claim(root, ident=BUYS_ID, claim=BUYS_CLAIM, independent=2,
            support=("m3", "m4"))

    result, channel = a_demonstration(registry)

    assert result.offer == Offer(belief_id=TRAVEL_ID, claim=TRAVEL_CLAIM), result
    assert TRAVEL_CLAIM in channel.sent[1]
    assert BUYS_CLAIM not in channel.sent[1], "two claims went out as a digest"


@pytest.mark.cap2
def test_the_choice_is_the_same_on_every_run_for_equally_supported_claims():
    """*One, not many*, where the counts cannot break the tie.

    Two claims with the same independence count must still produce one choice,
    the same one every time — a demonstration whose subject depended on
    dictionary ordering would differ between runs of the same log, which is
    AD-30's determinism failing at the one surface a main sees first.
    """
    beliefs = {
        ident: {CLAIM: claim, SUBJECT: "self", LEDGER: REVEALED,
                "derivation": "derived", "independent": 2}
        for ident, claim in ((BUYS_ID, BUYS_CLAIM), (TRAVEL_ID, TRAVEL_CLAIM))
    }
    first = chosen(beliefs)
    reversed_order = chosen(dict(reversed(list(beliefs.items()))))
    assert first == reversed_order == Offer(BUYS_ID, BUYS_CLAIM)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: nothing to offer, one cluster, unfalsifiable
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
def test_a_mailbox_with_one_cluster_behind_it_offers_nothing(tmp_path):
    """Matrix: *only one cluster*. **15b's rule, unchanged, through this path.**

    Two messages in one thread with the same content are one independent group,
    and CAP-3 refuses a claim from a single cluster of mentions. The
    demonstration does not re-decide that and could not: nothing here builds a
    ``Claim``, so what it can offer is whatever ``Run.admitted`` admitted.

    Asserted as *the ledger is empty* as well as *nothing was offered*, because
    the second is true of six other states and only the first says which.
    """
    reader, read_holder, _ = a_reader()
    wire = Wire()
    wiring = a_wiring(tmp_path, reader=reader, channel=wire,
                      nothing_yet=NOTHING_YET)
    try:
        result = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(ONE_CLUSTER)), t=NOW,
        ))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
    finally:
        wiring.registry.close()

    assert read_holder.calls == 2, "both bodies were read"
    assert beliefs == {}, beliefs
    assert result.reason is Reason.NO_CLAIM
    assert result.offer is None


@pytest.mark.cap2
def test_a_claim_the_falsifiability_gate_refuses_is_never_offered(tmp_path):
    """Matrix: *unfalsifiable*. **15a's gate, and no second opinion about it.**

    The falsifiability gate refuses both bodies, so no candidate is gathered, so
    nothing is admitted and nothing is offered. The demonstration never asks the
    question itself — asserted below as a structural rule too, because a second
    falsifiability check here would be a second answer that could disagree with
    15a's.
    """
    reader, read_holder, gate_holder = a_reader(
        gates={FALSIFIABILITY.name: NOT_CHECKABLE})
    wire = Wire()
    wiring = a_wiring(tmp_path, reader=reader, channel=wire)
    try:
        result = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(INDEPENDENT)), t=NOW,
        ))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
    finally:
        wiring.registry.close()

    assert gate_holder.calls == 2 * len(GATES), "all four gates ran on both"
    assert read_holder.calls == 0, "a body refused by a gate was still read"
    assert beliefs == {}
    assert result.reason is Reason.NO_CLAIM


@pytest.mark.cap2
def test_nothing_to_offer_says_so_plainly_and_composes_no_pleasantry(registry):
    """Matrix: *nothing to offer*. **Better than a lie.**

    Where nothing cleared the gates and the independence rule, the deployment's
    own sentence goes out and **no model is consulted at all** — asserted
    against a counting holder, because a composed *"lovely to meet you"* would
    be a pleasantry substituted for a demonstration, which the story forbids in
    as many words.

    The sentence is the deployment's rather than Half's for the notice's own
    reason: there is no template this product can ship worldwide, and a
    generated message with nothing to say is the pleasantry.
    """
    holder = NeverGenerates()
    result, channel = a_demonstration(
        registry, voice=Voice({MAIN: holder}, bound_seconds=1.0),
        plainly=NOTHING_YET,
    )

    assert result.reason is Reason.NO_CLAIM
    assert result.offer is None
    assert holder.calls == 0, "a model was asked to fill the silence"
    assert channel.sent == [NOTICE, NOTHING_YET], channel.sent


@pytest.mark.cap2
def test_nothing_to_offer_and_no_wording_is_silence_rather_than_something_made_up(
    registry,
):
    """*Nothing to offer*, fail-closed. Silence is a first-class outcome
    (AD-27), and a deployment that wrote no sentence gets it rather than one
    Half invented — which would be a template in one language, shipped to
    everybody."""
    result, channel = a_demonstration(registry, plainly="")

    assert result.reason is Reason.NO_CLAIM
    assert channel.sent == [NOTICE], channel.sent


# ═════════════════════════════════════════════════════════════════════════════
# matrix: confirmed, denied, no answer
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
def test_a_confirmation_promotes_through_the_ladders_own_door(registry, tmp_path):
    """Matrix: *confirmed*. **CAP-2's own success criterion.**

    *"The statement is confirmed as true"* is the ladder's acknowledgement
    event, so the main's *yes* produces ``promote(..., acknowledged=True)`` and
    the record now carries ``known_to_main``. Both halves are asserted: the rung
    moved, and the field that only an `assert`-level promotion writes is there.

    ``known_to_main`` is the whole point. Without it a promotion could be
    manufactured from a corroboration count, which is the one thing story 5a
    exists to make impossible.
    """
    a_claim(tmp_path / "mains")

    outcome = asyncio.run(answered(
        Offer(TRAVEL_ID, TRAVEL_CLAIM), "yes",
        main_id=MAIN, registry=registry, t=NOW,
    ))

    assert outcome.answer is Answer.CONFIRMED
    assert outcome.removal is None
    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        record = store.state().beliefs[TRAVEL_ID]
    assert record["license"] == str(License.ASSERT)
    assert record["known_to_main"] is True
    assert record[CLAIM] == TRAVEL_CLAIM, "the promotion dropped the claim"
    assert record["support"] == ["m0", "m1"], "the receipt did not travel"


@pytest.mark.cap2
def test_a_promotion_without_the_mains_answer_is_refused_by_the_ladder():
    """*Confirmed*, from the other side: there is no argument to ``promote``
    that a corroboration count could satisfy.

    Asserted directly against the ladder rather than through the flow, because
    what it pins is that the demonstration has not been handed a second way to
    move a rung — the only call is the one the main's answer produces.
    """
    belief = {"claim": TRAVEL_CLAIM, "license": str(ladder.FLOOR),
              "support": ["m0", "m1"], "independent": 9}
    with pytest.raises(LadderError, match="event involving the main"):
        ladder.promote(belief, to=License.ASSERT, acknowledged=False)


@pytest.mark.cap2
def test_a_denial_appends_a_correction_through_story_twelves_door(
    registry, tmp_path
):
    """Matrix: *denied*. **Never a silent discard.**

    A discard would lose the one correction a main is most likely to make, on
    the first thing Half ever said to them, and leave a claim they explicitly
    denied sitting in the fold shaping every context it enters.

    All three halves: the belief leaves the fold, the append is one of story
    12's own ops, and the attribution is **not yet known** — neither
    ``expired_at`` nor ``invalid_at`` is written, because the reply said the
    statement is wrong and said nothing about which.
    """
    a_claim(tmp_path / "mains")

    outcome = asyncio.run(answered(
        Offer(TRAVEL_ID, TRAVEL_CLAIM), "no",
        main_id=MAIN, registry=registry, t=NOW,
    ))

    assert outcome.answer is Answer.DENIED
    assert outcome.promoted is None
    assert outcome.removal is not None and outcome.removal.op is Op.RETRACT
    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        assert TRAVEL_ID not in store.state().beliefs
        appended = [r for r in store.log if r.op is Op.RETRACT]
    assert len(appended) == 1, appended
    assert appended[0].data["target"] == TRAVEL_ID
    assert EXPIRED_AT not in appended[0].data
    assert INVALID_AT not in appended[0].data


@pytest.mark.cap2
@pytest.mark.parametrize(
    "reply, stamp",
    [("that was never true", EXPIRED_AT), ("not any more", INVALID_AT)],
    ids=["half-was-wrong", "the-main-changed"],
)
def test_a_denial_that_says_which_records_which(reply, stamp, registry, tmp_path):
    """*Denied*, where the reply settles the cause.

    Story 12's ``recognize`` is what reads it, so *"that was never true"* and
    *"not any more"* stay different facts with different consequences — the
    demonstration adds no reading of its own and could not, because
    ``meaning_of`` returns ``recognize``'s answer wherever there is one.
    """
    a_claim(tmp_path / "mains")

    outcome = asyncio.run(answered(
        Offer(TRAVEL_ID, TRAVEL_CLAIM), reply,
        main_id=MAIN, registry=registry, t=NOW,
    ))

    assert outcome.answer is Answer.DENIED
    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        record = [r for r in store.log if r.data.get("target") == TRAVEL_ID][0]
    assert record.data[stamp] == NOW


@pytest.mark.cap2
def test_a_denial_asking_for_erasure_removes_without_erasing(registry, tmp_path):
    """*Denied*, at the one meaning this path may not act on.

    An erasure cannot be taken back, and story 12 requires one to be confirmed
    before it is applied. Answering a demonstration is not that confirmation, so
    *"delete that"* removes the belief as an ordinary correction and the body is
    **not** tombstoned — the main asks again on an ordinary turn, where story
    12's asking step is intact. Nothing is lost: the claim still leaves the
    fold on this reply.
    """
    a_claim(tmp_path / "mains")
    assert recognize("delete that") is Meaning.ERASE, "the fixture proves nothing"

    outcome = asyncio.run(answered(
        Offer(TRAVEL_ID, TRAVEL_CLAIM), "delete that",
        main_id=MAIN, registry=registry, t=NOW,
    ))

    assert outcome.removal is not None
    assert outcome.removal.op is not Op.EXPUNGE
    assert outcome.removal.erases is False
    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        assert TRAVEL_ID not in store.state().beliefs
        assert not [r for r in store.log if r.op is Op.EXPUNGE]


@pytest.mark.cap2
@pytest.mark.parametrize(
    "reply",
    ["", "   ", "maybe", "i think so", "what is this", "hm"],
    ids=["empty", "blank", "maybe", "hedge", "question", "noise"],
)
def test_silence_and_a_hedge_promote_nothing_and_correct_nothing(
    reply, registry, tmp_path
):
    """Matrix: *no answer*. **Silence is not consent, and it is not refusal.**

    Kept apart from a denial deliberately: the two do opposite things, and a
    build that folded a hedge into either one would promote a claim on a *maybe*
    or delete one on a shrug. Asserted against the log, so the case cannot pass
    by nothing having been written for some other reason.
    """
    a_claim(tmp_path / "mains")

    outcome = asyncio.run(answered(
        Offer(TRAVEL_ID, TRAVEL_CLAIM), reply,
        main_id=MAIN, registry=registry, t=NOW,
    ))

    assert outcome.answer is Answer.NONE
    assert outcome.promoted is None and outcome.removal is None
    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        record = store.state().beliefs[TRAVEL_ID]
        appends = len(list(store.log))
    assert record["license"] == str(ladder.FLOOR)
    assert appends == 1, "an answer that said nothing wrote something"


@pytest.mark.cap2
def test_an_answer_to_a_belief_that_has_gone_removes_nothing_twice(
    registry, tmp_path
):
    """*No answer*'s neighbour: the belief left the fold before the reply came.

    Story 12's own idempotency, reached from here: *gone* and *never held* are
    the same question asked of the current fold, and neither is an error the
    main is shown.
    """
    result = asyncio.run(answered(
        Offer(TRAVEL_ID, TRAVEL_CLAIM), "no",
        main_id=MAIN, registry=registry, t=NOW,
    ))
    assert result.answer is Answer.DENIED
    assert result.removal is None
    with Store(tmp_path / "mains" / MAIN, prefix=build_prefix) as store:
        assert list(store.log) == []


@pytest.mark.cap2
@pytest.mark.parametrize(
    "reply, expected",
    [
        *((row, Answer.CONFIRMED) for row in VOCABULARY[CONFIRM][:6]),
        *((row, Answer.DENIED) for row in VOCABULARY[DECLINE][:6]),
        *((row, Answer.DENIED) for row in ("thats wrong", "das stimmt nicht")),
        *((row, Answer.NONE) for row in ("maybe", "not really", "i went there")),
    ],
    ids=lambda value: str(value).replace(" ", "-"),
)
def test_every_reading_of_an_answer_is_story_twelves_own(reply, expected):
    """The three readings, swept. **One recogniser, not a second one.**

    A confirmation is ``is_confirmation``; a denial is ``recognize`` or
    ``is_decline``; everything else is nothing. Nothing in ``half.onboard``
    tokenises, folds, splits or matches anything — asserted structurally below
    as well, because a second reading of the same reply is two products
    disagreeing about what a main said.
    """
    assert reading(reply) is expected


@pytest.mark.cap2
@pytest.mark.parametrize(
    "reply, meaning",
    [
        ("that was never true", Meaning.NEVER_TRUE),
        ("not any more", Meaning.CHANGED),
        ("thats wrong", Meaning.WRONG),
        ("no", Meaning.WRONG),
        ("delete that", Meaning.WRONG),
    ],
    ids=["half-was-wrong", "the-main-changed", "wrong-cause-unstated",
         "a-bare-no", "an-erasure-is-clamped"],
)
def test_what_a_denial_means_is_never_guessed(reply, meaning):
    """*Denied*, at the function that decides which correction it is.

    Three of the five are ``recognize``'s own answer, unchanged. The bare *no*
    is *wrong, cause unknown* — the main said the statement is wrong and said
    nothing about whether Half was wrong or they have changed, and only they
    know which; a default in either direction writes a falsehood into the one
    ledger whose purpose is to be honest.

    The fifth is the **clamp**: ``recognize`` reads *"delete that"* as an
    erasure, and an erasure cannot be taken back, so story 12 requires one to be
    confirmed before it is applied. Answering a demonstration is not that
    confirmation. Asserted here as well as through the store, because this is
    the function the rule lives in and the store case would pass if the clamp
    moved somewhere a later caller could miss.
    """
    assert meaning_of(reply) is meaning


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the wording — the second bounded exception to AD-18
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
@pytest.mark.ad18
def test_the_offered_claims_wording_reaches_the_prompt_and_the_wire(
    registry, tmp_path
):
    """Matrix: *the wording*. **The positive half of the exception.**

    A `behave` claim's text reaches the may-be-said block and the wire on the
    demonstration turn. Asserted through the prompt the composer actually
    handed the port — ``conftest.echo`` puts on the wire whatever that block
    licensed, so a fixed-string double could not tell this case from its
    negative.

    The rung is asserted here too: the claim is quoted **while still `behave`**,
    which is the exception, rather than because something quietly promoted it,
    which would be the ladder bypassed.
    """
    record = a_claim(tmp_path / "mains")
    assert ladder.own_rung(record) is License.BEHAVE, "the fixture is not behave"
    voice, holder = a_voice()

    result, channel = a_demonstration(registry, voice=voice)

    assert result.reason is Reason.DEMONSTRATED
    assert block_of(holder.requests[0], MAY_BE_SAID) == TRAVEL_CLAIM
    assert TRAVEL_CLAIM in channel.sent[1]


@pytest.mark.cap2
@pytest.mark.ad18
def test_that_wording_reaches_no_other_turn_with_the_demonstration_wired(
    registry, tmp_path
):
    """Matrix: *no other turn*. **The negative half, and the whole risk.**

    Story 12's exception shipped with its negative tested against a runtime that
    had **no classifier wired**, which structurally excluded the very route the
    assertion claimed to bound; 13b's review found it. So here the route is
    live in the assertion rather than switched off around it:

    * the demonstration is run for real, against this main, and it **does** put
      the claim on the wire — asserted, or this case proves nothing;
    * an offer is left standing, so the state that licensed the quotation is
      still in hand;
    * and then an **ordinary turn** goes through the real ``Runtime``, the real
      crisis gate, the real retrieval and the real context builder, with that
      same claim in the ranked set and the same composing double — and carries
      none of its wording.

    The double is ``conftest.echo``, which repeats whatever the may-be-said
    block licensed. A double answering a fixed sentence would satisfy the
    negative whether the exception was bounded or wide open.
    """
    root = tmp_path / "mains"
    a_claim(root)
    voice, _ = a_voice()

    # The demonstration, live, and it does quote the claim.
    shown, channel = a_demonstration(registry, voice=voice)
    assert shown.reason is Reason.DEMONSTRATED, shown
    assert shown.offer is not None, "no offer stands, so nothing is bounded"
    assert TRAVEL_CLAIM in channel.sent[1], "the positive half did not happen"

    # An ordinary turn, on the same main, with the offer still standing.
    transport = FakeTransport([
        msg(text="what have you got on me", message_id="o1", chat_id="123",
            date=1_788_264_000)
    ])
    telegram = TelegramChannel(transport=transport, mains={"123": MAIN})
    asyncio.run(Runtime(
        channel=telegram, registry=registry, voice=voice,
    ).run())
    said = "".join(text for _, text in transport.sent)

    assert said, "the ordinary turn said nothing, so it bounds nothing"
    assert TRAVEL_CLAIM not in said, said
    for word in [w for w in TRAVEL_CLAIM.split() if len(w) > 3]:
        assert word not in said, word


@pytest.mark.cap2
@pytest.mark.ad18
def test_the_ordinary_door_has_no_parameter_an_offer_could_arrive_through():
    """*No other turn*, as a property of the signature rather than a branch.

    ``split`` takes ``offered``; ``build`` — the door the runtime, the morning
    surface and the interrupt gate all use — does not. So an ordinary turn
    cannot quote a `behave` claim however its ranked set is arranged, and the
    bound is a fact somebody would have to *change the signature* to break
    rather than one they could forget to keep.

    Both halves, so the case cannot pass by ``offered`` not existing at all.
    """
    assert "offered" in inspect.signature(split).parameters
    assert "offered" not in inspect.signature(build_context).parameters
    assert "offered" not in inspect.signature(withheld_wordings).parameters

    # **And no other door into the package takes one**, swept rather than
    # named: ``half.context`` re-exports what other packages import, and a
    # later story adding a second entry point that forwarded an offer would be
    # a second exception nobody voted for.
    assert context_package.__all__, "the package exports nothing, so this "\
        "sweep is vacuous"
    for name in context_package.__all__:
        member = getattr(context_package, name, None)
        if not inspect.isfunction(member):
            continue
        assert "offered" not in inspect.signature(member).parameters, name
    # **On the module namespace, not on ``__all__``.** ``from half.context
    # import split`` works whether or not the name is in ``__all__``, so a
    # check on the list is a check on documentation. A probe that added the
    # re-export and left ``__all__`` alone walked straight past the first
    # version of this line.
    assert not hasattr(context_package, "split"), (
        "the offered door is reachable from `half.context`, so a surface that "
        "imports the package can quote a `behave` claim without meaning to. "
        "The two callers that need it import `half.context.build` by name."
    )


@pytest.mark.cap2
@pytest.mark.ad18
@pytest.mark.parametrize(
    "offered, quoted",
    [(TRAVEL_ID, True), (None, False), ("", False), ("   ", False),
     (BUYS_ID, False), (f" {TRAVEL_ID} ", True), (0, False), (object(), False)],
    ids=["the-one-offered", "none", "empty", "blank", "another", "padded",
         "not-a-string", "not-a-value"],
)
def test_only_the_claim_that_was_handed_in_is_quoted(offered, quoted):
    """The exception, swept exhaustively against an independently written
    expectation — which is what a predicate buys and a syntax scan cannot.

    Both channels are read, because the exception has two halves and either one
    alone would be a leak: the claim reaches the **content** channel, and its
    wording leaves the **withheld** set so the leak tripwire does not refuse the
    message carrying it.
    """
    belief = {CLAIM: TRAVEL_CLAIM, SUBJECT: "self", "support": ["m0"]}
    context, hidden = split(
        Ranked(beliefs=(candidate_of(belief),)),
        now=NOW, ceiling=None, offered=offered,
    )
    assert (TRAVEL_CLAIM in context.quotable()) is quoted
    assert (not any(TRAVEL_CLAIM.startswith(f.split()[0]) for f in hidden)
            ) is quoted or not hidden
    assert offered_claim(TRAVEL_ID, offered=offered) is quoted


@pytest.mark.cap2
@pytest.mark.ad18
def test_an_offered_claim_leaves_every_other_wording_withheld():
    """The exception is **one claim**, not a switch that opens the channel.

    A second `behave` belief in the same ranked set stays withheld and stays out
    of the content channel — so a demonstration cannot become a digest of
    everything Half worked out by way of the exception, and the tripwire is
    still armed for everything else on that build.
    """
    offered = {CLAIM: TRAVEL_CLAIM, SUBJECT: "self"}
    other_text = "keeps bees in the garden"
    other = {CLAIM: other_text, SUBJECT: "self"}
    context, hidden = split(
        Ranked(beliefs=(
            candidate_of(offered),
            Candidate(id="b_bees", claim=other_text, prefix="", bm25=None,
                      belief=other),
        )),
        now=NOW, ceiling=None, offered=TRAVEL_ID,
    )
    assert context.quotable() == (TRAVEL_CLAIM,)
    assert other_text not in context.render()
    assert any("keeps" in fragment for fragment in hidden), hidden


@pytest.mark.cap2
@pytest.mark.ad18
def test_the_public_withheld_set_never_takes_an_offer_into_account():
    """``half.context.build.withheld`` is what ``half.voice.leak`` runs its
    tripwire from on every other path, and it withholds the offered claim like
    any other `behave` claim — because on those paths nothing was offered.

    Without this the exception would travel: one function that could be told to
    stop withholding, read by a surface that never offers anything.
    """
    belief = {CLAIM: TRAVEL_CLAIM, SUBJECT: "self"}
    hidden = withheld_wordings(
        Ranked(beliefs=(candidate_of(belief),)), ceiling=None)
    assert hidden, "nothing is withheld, so this asserts nothing"


@pytest.mark.cap2
@pytest.mark.ad18
def test_a_ceiling_still_caps_what_the_demonstration_may_quote():
    """AD-28 is not suspended by the exception, and the case that matters is a
    main in crisis aftercare — every license capped at `behave` for thirty days.

    The offered claim is quoted under the cap, which is correct: it is quoted
    *because it was offered*, not because of the rung it resolved to, so a
    ceiling changes nothing about it. What the ceiling still does is hold every
    **other** belief down, which is asserted here so that lowering it cannot
    leak a claim sideways through the exception.
    """
    offered = {CLAIM: TRAVEL_CLAIM, SUBJECT: "self", "support": ["s"],
               "license": str(License.ASSERT), "known_to_main": True}
    other = {CLAIM: "walks the long way home", SUBJECT: "self",
             "support": ["s"], "license": str(License.ASSERT),
             "known_to_main": True}
    ranked = Ranked(beliefs=(
        candidate_of(offered),
        Candidate(id="b_walk", claim=other[CLAIM], prefix="", bm25=None,
                  belief=other),
    ))
    capped, hidden = split(ranked, now=NOW, ceiling=Ceiling(License.BEHAVE),
                           offered=TRAVEL_ID)
    assert capped.quotable() == (TRAVEL_CLAIM,)
    assert any("walks" in fragment for fragment in hidden), hidden


# ═════════════════════════════════════════════════════════════════════════════
# matrix: crisis, provider absent, unreachable
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
@pytest.mark.cap12
def test_a_main_in_the_crisis_mode_is_not_demonstrated_to(registry, tmp_path):
    """Matrix: *in crisis* (CAP-12, AD-10). **The mode owns the turn.**

    Not merely *"nothing was offered"*: nothing at all happens. The notice is
    not sent, the mailbox is not read, and the composer is not consulted — a
    main in the mode is not told about mail and not spoken to from here.

    Driven through the registry's own crisis record rather than a flag, so the
    case reads the same state the crisis gate reads.
    """
    a_claim(tmp_path / "mains")
    asyncio.run(registry.suspend_for_crisis(
        MAIN, t=NOW, tier="high", score=1))
    assert registry.crisis_open(MAIN) is True, "the fixture is not in the mode"

    ran: list[int] = []

    async def pull():
        ran.append(1)

    holder = NeverGenerates()
    result, channel = a_demonstration(
        registry, pull=pull, voice=Voice({MAIN: holder}, bound_seconds=1.0))

    assert result.reason is Reason.IN_CRISIS
    assert channel.sent == [], "a main in the mode was written to"
    assert ran == [], "a main in the mode had their mailbox read"
    assert holder.calls == 0


@pytest.mark.cap2
def test_a_registry_that_cannot_answer_about_the_mode_demonstrates_nothing(
    registry,
):
    """*In crisis*, fail-closed. The cost of demonstrating to somebody in the
    mode is not symmetric with the cost of not demonstrating to somebody who is
    fine, so an unreadable answer is treated as the mode being open."""

    class Raises:
        def crisis_open(self, main_id):
            raise RuntimeError("no")

    class Silent:
        """A registry with no ``crisis_open`` at all — a shape a later refactor
        can produce, and the branch a raising double never reaches."""

    for broken in (Raises(), Silent()):
        result, channel = a_demonstration(broken)
        assert result.reason is Reason.IN_CRISIS, type(broken).__name__
        assert channel.sent == []


@pytest.mark.cap2
def test_a_deployment_with_no_composer_says_nothing_and_does_not_crash(
    registry, tmp_path
):
    """Matrix: *provider absent*. **Never fatal** (AD-27).

    A ``Voice`` with no holders is a supported deployment, not a broken one, and
    what it costs is the demonstration rather than the process. The notice still
    goes out and the mailbox is still read, because both are true whatever the
    composer can do — the claim is in the ledger for a later run.
    """
    a_claim(tmp_path / "mains")
    read: list[int] = []

    async def pull():
        read.append(1)

    result, channel = a_demonstration(
        registry, voice=Voice(), pull=pull)

    assert result.reason is Reason.NO_VOICE
    assert read == [1], "the mailbox was not read"
    assert channel.sent == [NOTICE]


@pytest.mark.cap2
def test_no_deriver_wired_leaves_the_ledger_empty_and_says_so(tmp_path):
    """*Provider absent*, at the other end of the path: a ``Revealed`` with no
    holders derives nothing, which is exactly the state story 3 shipped.

    Receipts are still captured — asserted, because *"nothing was offered"* is
    also true of a mailbox that was never read, and only the receipts say which.
    """
    wire = Wire()
    wiring = a_wiring(tmp_path, reader=Revealed(), channel=wire)
    try:
        result = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(INDEPENDENT)), t=NOW))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
        captured = list((tmp_path / MAIN / "sources").rglob("*"))
    finally:
        wiring.registry.close()

    assert beliefs == {}
    assert [p for p in captured if p.is_file()], "no receipt was written"
    assert result.reason is Reason.NO_CLAIM


@pytest.mark.cap2
def test_a_platform_that_forbids_first_contact_is_not_written_to(registry):
    """*Unreachable* (AD-7). Telegram bots cannot open a conversation, and the
    rule lives on the port: the demonstration branches on the answer and never
    learns it. Nothing is sent and nothing is connected."""
    ran: list[int] = []

    async def pull():
        ran.append(1)

    result, channel = a_demonstration(
        registry, wire=Wire(reach=Reachability.NEVER_CONTACTED), pull=pull)

    assert result.reason is Reason.UNREACHABLE
    assert channel.sent == [] and ran == []


@pytest.mark.cap2
def test_a_send_that_raises_costs_the_demonstration_and_never_the_process(
    registry, tmp_path
):
    """*Provider absent*'s neighbour on the outbound side. A transport fault is
    a value on this path, not an exception out of it, and no claim is promoted
    on the strength of a message nobody received."""
    a_claim(tmp_path / "mains")

    result, _ = a_demonstration(registry, wire=Wire(fail=RuntimeError("down")))

    assert result.reason is Reason.NOTICE_NOT_SENT
    assert result.offer is None


# ═════════════════════════════════════════════════════════════════════════════
# matrix: re-run, replay, nothing durable
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
def test_onboarding_twice_promotes_nothing_twice_and_duplicates_no_claim(
    tmp_path,
):
    """Matrix: *re-run*. **Idempotent on both ends.**

    Two pulls of the same mailbox and two confirmations of the same offer. The
    pipeline skips a message whose digest it already holds, ``ingest_mail``
    leaves a claim already in the ledger alone, and ``answered`` refuses a
    second promotion because ``known_to_main`` is already written.

    Asserted by counting **appends**, not by reading the fold: the fold looks
    identical whether the second run wrote nothing or wrote the same thing
    again, which is a state a mutation walked straight through.
    """
    reader, _, _ = a_reader()
    voice, _ = a_voice()
    wire = Wire()
    wiring = a_wiring(tmp_path, reader=reader, voice=voice, channel=wire)
    try:
        first = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(INDEPENDENT)), t=NOW))
        assert first.offer is not None, first
        asyncio.run(answered(first.offer, "yes", main_id=MAIN,
                             registry=wiring.registry, t=NOW))

        # The same mailbox, again, and the same *yes* again.
        second = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(INDEPENDENT)), t=NOW))
        again = asyncio.run(answered(first.offer, "yes", main_id=MAIN,
                                     registry=wiring.registry, t=NOW))

        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            appends = [r for r in store.log if r.id == TRAVEL_ID]
            record = store.state().beliefs[TRAVEL_ID]
    finally:
        wiring.registry.close()

    # Nothing to offer the second time: the main has already answered about the
    # only claim there is, and Half does not ask a question it has the answer
    # to.
    assert second.reason is Reason.NO_CLAIM, second
    assert second.offer is None
    # And the repeated *yes* moved nothing: `promote` would have refused it, so
    # the refusal is never reached rather than caught.
    assert again.answer is Answer.CONFIRMED and again.promoted is None
    # One admission and one promotion, and nothing from either repeat.
    assert len(appends) == 2, [r.data for r in appends]
    assert record["license"] == str(License.ASSERT)
    assert record["known_to_main"] is True


@pytest.mark.cap2
def test_a_confirmed_claim_is_never_offered_again(tmp_path, registry):
    """*Re-run*, at the choosing rather than at the append.

    A claim the main has already answered about is not offered a second time —
    Half asking a question it has the answer to. The same predicate answers
    both, so the two cannot drift.
    """
    a_claim(tmp_path / "mains", confirmed=True)

    result, channel = a_demonstration(registry)

    assert result.reason is Reason.NO_CLAIM
    assert channel.sent == [NOTICE]


@pytest.mark.cap2
def test_the_demonstration_and_its_answer_fold_identically_on_a_rebuild(
    tmp_path,
):
    """Matrix: *replay* (AD-4, AD-30). The promotion is an append like any
    other, so discarding the derived view and folding the log again reproduces
    it — the acknowledgement is *recorded*, never re-derived, which is what
    makes AD-4 true rather than aspirational."""
    reader, _, _ = a_reader()
    voice, _ = a_voice()
    wiring = a_wiring(tmp_path, reader=reader, voice=voice, channel=Wire())
    try:
        result = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(INDEPENDENT)), t=NOW))
        asyncio.run(answered(result.offer, "yes", main_id=MAIN,
                             registry=wiring.registry, t=NOW))
    finally:
        wiring.registry.close()

    with Store(tmp_path / MAIN, prefix=build_prefix) as store:
        before = store.state().beliefs
        after = store.rebuild().beliefs
    assert before == after
    assert after[TRAVEL_ID]["known_to_main"] is True


@pytest.mark.cap2
def test_no_body_and_no_generated_text_is_written_anywhere(tmp_path, caplog):
    """Matrix: *nothing durable* (AD-22, AD-13, story 3).

    A sentinel is chased through every byte written under the main's tree and
    through every captured log line: the mail body is never persisted, and the
    composed message is not either — it is returned to the caller and sent.
    """
    sentinel = "wintergreen-particular-9134"
    reader, _, _ = a_reader()
    voice, _ = a_voice(f"{sentinel} — {TRAVEL_CLAIM}")
    wire = Wire()
    wiring = a_wiring(tmp_path, reader=reader, voice=voice, channel=wire)
    with caplog.at_level(logging.DEBUG):
        try:
            result = asyncio.run(onboard(
                wiring, main_id=MAIN, t=NOW,
                source=FakeMail([
                    mail(0, f"your booking is confirmed {sentinel}",
                         thread="t1", sender="a@x"),
                    mail(1, f"your itinerary {sentinel}", thread="t2",
                         sender="b@y"),
                ]),
            ))
        finally:
            wiring.registry.close()

    assert result.reason is Reason.DEMONSTRATED
    assert sentinel in wire.sent[1], "the fixture never put the sentinel anywhere"
    written = b"".join(
        p.read_bytes() for p in (tmp_path / MAIN).rglob("*") if p.is_file()
    )
    assert sentinel.encode() not in written, "a body or a completion persisted"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel not in logged, logged


# ═════════════════════════════════════════════════════════════════════════════
# the ninety seconds — measured, and the gap recorded
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2
def test_the_whole_offline_path_is_timed_and_fits_the_budget(tmp_path):
    """Matrix: *ninety seconds*, on the wall clock.

    The whole path — one OAuth's worth of mailbox, four gate calls per message,
    the reading, the independence pass, the append and the composition — timed
    end to end with the provider stubbed. Offline this is milliseconds and the
    number is not the interesting one; what this case pins is that the path
    **carries** its own measurement out, so nobody can claim ninety seconds
    about a run nobody timed.

    The interesting number is the case below.
    """
    reader, _, _ = a_reader()
    voice, _ = a_voice()
    wiring = a_wiring(tmp_path, reader=reader, voice=voice, channel=Wire())
    started = time.monotonic()
    try:
        result = asyncio.run(onboard(
            wiring, main_id=MAIN, source=FakeMail(list(INDEPENDENT)), t=NOW))
    finally:
        wiring.registry.close()
    elapsed = time.monotonic() - started

    assert result.reason is Reason.DEMONSTRATED
    assert result.seconds > 0, "the path reported no measurement at all"
    assert result.fitted is True
    assert result.seconds <= elapsed + 0.5, (result.seconds, elapsed)
    assert elapsed < BUDGET_SECONDS


@pytest.mark.cap2
def test_the_budget_fits_only_a_handful_of_messages_in_the_worst_case():
    """Matrix: *ninety seconds* — **and this is the gap, stated rather than
    papered over.**

    One body costs 15a's four gates (concurrent, one bound) and then 15b's
    reading (a second bound), and bodies are read **in series** because
    ``half.ingest.pipeline`` awaits its consumer inside the ``async for`` and
    neither derivation story has a batch seam. So the worst case is the sum of
    the two bounds per message, and at the shipped numbers that is a handful of
    messages inside the whole budget — while ``PER_RUN`` allows two hundred.

    The budget binds long before the per-run cap does. A first mailbox pull that
    must find **two independent groups behind one label** inside a handful of
    messages will often find nothing, which is why *nothing to offer* is a
    first-class row of this story's matrix rather than an edge case. The fix is
    a batch seam in ``half.model``, and it is not a number that can be tuned
    here — asserted so that a future story cannot quietly widen the budget and
    call the problem solved.
    """
    # **Pinned to a number, not restated as the formula.** ``messages_that_fit
    # () == int(PULL_SECONDS // (GATE_BOUND + READ_BOUND))`` is the
    # implementation written twice: it is green for every value of every
    # constant, which is the assertion-identical-either-way shape this project
    # has shipped twice. So the four inputs are pinned and the answer is a
    # literal, and moving any bound fails here until somebody re-derives it and
    # says what it now costs.
    assert (BUDGET_SECONDS, COMPOSE_SECONDS, GATE_BOUND, READ_BOUND) == (
        90.0, 20.0, 5.0, 8.0
    ), "a bound moved; re-derive the number below rather than relaxing it"
    assert messages_that_fit() == 5
    assert messages_that_fit() < 10, (
        "the worst case now fits ten messages or more; if a batch seam landed, "
        "this case should be rewritten around it rather than relaxed"
    )
    assert messages_that_fit() < PER_RUN, (
        "the ninety seconds no longer binds before the per-run cap, which is "
        "the whole shape of this cost"
    )
    assert messages_that_fit() >= 1, "no message fits at all"
    # And it moves with the bounds rather than being a number of its own.
    assert messages_that_fit(BUDGET_SECONDS * 10) > messages_that_fit()
    assert messages_that_fit(COMPOSE_SECONDS) == 0


@pytest.mark.cap2
def test_a_pull_past_the_deadline_is_cut_and_what_it_gathered_still_counts():
    """Matrix: *ninety seconds* — **what it does when it does not fit.**

    The pull stops rather than running on, and it stops by the *source* ceasing
    to yield rather than by a cancellation — so the pipeline's ``async for``
    ends normally and every receipt written and every candidate gathered
    survives. A cancelled pull would have lost the run with the local and
    admitted nothing from receipts already on disk.
    """
    source = FakeMail([mail(i, f"body {i}", thread=f"t{i}", sender=f"{i}@x")
                       for i in range(5)], sleep=0.02)
    bounded = Bounded(source, seconds=0.03)

    async def drain():
        return [m async for m in bounded.fetch()]

    seen = asyncio.run(drain())

    assert bounded.stopped_early is True
    assert 0 < len(seen) < 5, len(seen)
    assert [m.external_id for m in seen] == [f"m{i}" for i in range(len(seen))]


@pytest.mark.cap2
def test_a_budget_gone_before_the_composition_says_so_and_offers_nothing(
    registry, tmp_path
):
    """*Ninety seconds*, at the other end: the pull spent everything.

    The claim is in the ledger and nothing was said, which is the honest
    outcome — a demonstration composed past the budget is a demonstration that
    missed CAP-2's own requirement, and a build that shipped it anyway would
    make the ninety seconds a decoration.
    """
    a_claim(tmp_path / "mains")
    holder = NeverGenerates()

    async def pull():
        await asyncio.sleep(0.05)

    result, channel = a_demonstration(
        registry, pull=pull, budget=0.02,
        voice=Voice({MAIN: holder}, bound_seconds=1.0),
    )

    assert result.reason is Reason.OUT_OF_TIME
    assert result.fitted is False, result.seconds
    assert holder.calls == 0, "a composition ran past the budget"
    assert channel.sent == [NOTICE]


@pytest.mark.cap2
@pytest.mark.parametrize(
    "budget", [0, -1, 0.0, None, "90", True, float("nan")],
    ids=["zero", "negative", "zero-float", "none", "string", "bool", "nan"],
)
def test_a_budget_that_is_not_a_budget_is_a_build_mistake(budget, registry):
    """A demonstration that may run for ever is a main waiting for ever, and
    nothing would say so. Refused loudly at the top, before anything is sent —
    a build mistake rather than a ``Reason``, because it is a deployment nobody
    would want to keep running."""
    with pytest.raises(OnboardError):
        asyncio.run(demonstrate(
            main_id=MAIN, consent=TOLD, channel=Wire(), registry=registry,
            pull=None, voice=Voice(), t=NOW, budget_seconds=budget,
        ))


# ═════════════════════════════════════════════════════════════════════════════
# the structural rules
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap2_structure
def test_the_consent_module_ships_no_sentence_in_any_language():
    """**Half ships no wording for the notice**, asserted over the file's own
    syntax tree rather than by reading it.

    A privacy notice written in one language and shown to everybody is a notice
    most of the world cannot read, which is a notice they were not given. The
    shape of a sentence is a space; the shape of a machine word is not — so
    every module-level string constant in that file must be spaceless, and the
    first English default anybody adds fails here.

    Docstrings are excluded because they are documentation, not what is sent.
    ``JOIN`` is excluded by name: it is whitespace itself, and it is the only
    constant in the module whose *value* is a separator rather than a word.
    """
    path = ROOT / "half" / "onboard" / "consent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        names = (
            [t.id for t in node.targets if isinstance(t, ast.Name)]
            if isinstance(node, ast.Assign)
            else ([node.target.id] if isinstance(node.target, ast.Name) else [])
        )
        if "JOIN" in names:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                if any(ch.isspace() for ch in child.value):
                    offenders.append(f"{names}: {child.value!r}")
    assert not offenders, (
        f"half/onboard/consent.py ships wording: {offenders}. The sentence is "
        "the deployment's, in the main's own language"
    )
    # Non-vacuity: the scan sees a sentence when there is one.
    seeded = ast.parse('X = "your messages leave this device"\n')
    assert any(
        isinstance(c, ast.Constant) and isinstance(c.value, str)
        and any(ch.isspace() for ch in c.value)
        for node in seeded.body for c in ast.walk(node)
    )


@pytest.mark.cap2_structure
def test_nothing_in_the_onboard_package_writes_a_license_field():
    """Story 5a's writer rule, applied to a new package.

    ``license``, ``known_to_main``, ``support`` and the quarantine flag reach
    the log through ``half.governance.ladder`` and nowhere else. Read-side
    enforcement alone would leave `assert` a field anybody can set — it would
    merely raise the price from one field to three — so this scans for the
    *spellings* in the package's own source.
    """
    gated = {"license", "known_to_main", "quarantined"}
    offenders: list[str] = []
    for path in (ROOT / "half" / "onboard").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg in gated:
                offenders.append(f"{path.name}:{node.lineno} {node.arg}=")
            if isinstance(node, ast.Constant) and node.value in gated:
                offenders.append(f"{path.name}:{node.lineno} {node.value!r}")
    assert not offenders, (
        f"a license field is spelled outside the ladder: {offenders}"
    )


@pytest.mark.cap2_structure
def test_the_flow_derives_nothing_and_admits_nothing_of_its_own():
    """**Falsifiability, durability, relevance and independence are decided
    once**, before a record this module can read exists.

    ``half.onboard.flow`` constructs no ``Claim``, calls nothing on a ``Run``,
    and reaches no admission gate — so *"no unfalsifiable claim is offered"* is
    a property of where the material comes from rather than a second check that
    could disagree with 15a's.
    """
    source = (ROOT / "half" / "onboard" / "flow.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    #: Names that build a claim or decide whether one is admitted. ``Candidate``
    #: is deliberately absent: the flow builds one, but a ``Candidate`` is a
    #: *retrieval* value carrying a belief the fold already holds, not an
    #: admission decision.
    deciding = {"Claim", "Run", "admitted", "admission", "independent_groups",
                "spend", "supports"}
    reached: list[str] = []
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None)
        elif isinstance(node, ast.Attribute):
            name = node.attr
        if name in deciding:
            reached.append(f"{node.lineno} {name}")
    assert not reached, f"the flow decides admission for itself: {reached}"
    for name in ("half.derive.gates", "half.ingest.independence",
                 "half.ingest.pipeline"):
        assert f"from {name}" not in source, name
    # Non-vacuity: the scan sees one of those names when it is there.
    seeded = ast.parse("x = run.admitted()\n")
    assert any(getattr(n, "attr", None) in deciding for n in ast.walk(seeded))


@pytest.mark.cap2_structure
def test_the_flow_recognises_an_answer_only_through_story_twelves_tables():
    """**One recogniser, not a second one.**

    Nothing under ``half/onboard/`` tokenises, folds, splits or matches text.
    A second reading of the same reply is two products disagreeing about what a
    main said, and this project has already paid for that once — story 12's
    ``shows`` was written inline beside the function every case was written
    against, and the two agreed only by coincidence.
    """
    folding = {"normalize", "terms", "clusters", "casefold", "lower", "fold"}
    offenders: list[str] = []
    read_from_signals: set[str] = set()
    for path in (ROOT / "half" / "onboard").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "half.text":
                    offenders.append(f"{path.name}: imports half.text")
                if node.module == "half.correction.signals":
                    read_from_signals |= {a.name for a in node.names}
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(
                    node.func, "id", None)
                if name in folding:
                    offenders.append(f"{path.name}:{node.lineno} {name}")
    assert not offenders, offenders
    # And what it *does* read is story 12's own three readings and the meaning
    # they carry — nothing wider, so there is no second table and no second
    # tokenizer anywhere on this path.
    assert read_from_signals == {
        "Meaning", "is_confirmation", "is_decline", "recognize"
    }, sorted(read_from_signals)


@pytest.mark.cap2_structure
def test_the_decline_table_is_worldwide_and_no_language_is_the_default():
    """The new table is held to story 12's own coverage rule.

    ``tests/test_correction.py`` sweeps ``MEANING_FOR_TABLE``, which the answer
    tables are deliberately not part of — so without this case a table could be
    added in English alone and nothing would say so.
    """
    assert DECLINE in VOCABULARY and DECLINE in ANSWERS
    assert DECLINE not in {name for name, _ in MEANING_FOR_TABLE}
    scripts = set().union(*(_scripts(row) for row in DECLINE_SOURCE))
    assert len(scripts) >= 6, sorted(scripts)
    latin = [row for row in DECLINE_SOURCE if _scripts(row) <= {"LATIN"}]
    assert len(latin) < len(DECLINE_SOURCE)
    assert len(set(DECLINE_SOURCE)) == len(DECLINE_SOURCE)


@pytest.mark.cap2_structure
def test_the_decline_table_is_never_consulted_by_the_unprompted_path():
    """A bare ``no`` is safe as an **answer** and reckless as a correction.

    ``recognize`` — the reader every ordinary inbound message goes through —
    must not fire on any decline row that story 12's own tables do not already
    carry. Without this, adding a one-word row here would silently remove a
    belief from anybody who typed it in the middle of a conversation.
    """
    fired = [row for row in DECLINE_SOURCE if recognize(row) is not None]
    assert fired == [], fired
    assert is_decline("no") and not is_confirmation("no")
    # And a decline inside a longer sentence is not an answer to anything.
    assert not is_decline("no i went to the shop and it was closed")


@pytest.mark.cap2_structure
def test_an_outcome_can_carry_a_promotion_or_a_correction_but_never_both():
    """One reply cannot be both a confirmation and a correction, and a build
    that could produce both would have two rung movers. Refused at
    construction, where a caller cannot forget to check it."""
    with pytest.raises(OnboardError):
        Outcome(answer=Answer.CONFIRMED, promoted={"license": "assert"},
                removal=object())


@pytest.mark.cap2_structure
@pytest.mark.parametrize(
    "reason", [r for r in Reason if r is not Reason.DEMONSTRATED],
    ids=lambda r: str(r),
)
def test_only_a_demonstration_the_main_saw_leaves_an_offer_standing(reason):
    """An outcome carrying an offer nobody was shown would let a later *yes*
    promote a claim the main never read — CAP-2's criterion inverted. Refused
    at construction, in both directions."""
    with pytest.raises(OnboardError):
        Demonstration(reason=reason, offer=Offer(TRAVEL_ID, TRAVEL_CLAIM))
    with pytest.raises(OnboardError):
        Demonstration(reason=Reason.DEMONSTRATED)


@pytest.mark.cap2_structure
@pytest.mark.parametrize(
    "belief_id, claim",
    [("", TRAVEL_CLAIM), ("   ", TRAVEL_CLAIM), (None, TRAVEL_CLAIM),
     (TRAVEL_ID, ""), (TRAVEL_ID, "  "), (TRAVEL_ID, None)],
    ids=["no-id", "blank-id", "id-not-a-string", "no-claim", "blank-claim",
         "claim-not-a-string"],
)
def test_an_offer_with_no_words_or_no_target_is_refused(belief_id, claim):
    """Both fields are load-bearing and neither is optional: without an id
    there is nothing an answer could promote, and without the words there is
    nothing the main can check — which is the whole of CAP-2."""
    with pytest.raises(OnboardError):
        Offer(belief_id=belief_id, claim=claim)


@pytest.mark.cap2_structure
@pytest.mark.parametrize(
    "belief, offerable_",
    [
        ({CLAIM: TRAVEL_CLAIM, LEDGER: REVEALED, "derivation": "derived"}, True),
        ({CLAIM: TRAVEL_CLAIM, LEDGER: REVEALED, "derivation": "underived"},
         False),
        ({CLAIM: TRAVEL_CLAIM, LEDGER: "stated", "derivation": "derived"},
         False),
        ({CLAIM: "", LEDGER: REVEALED, "derivation": "derived"}, False),
        ({LEDGER: REVEALED, "derivation": "derived"}, False),
        ({CLAIM: TRAVEL_CLAIM, LEDGER: REVEALED, "derivation": "derived",
          "known_to_main": True}, False),
        ("not a record", False),
        (None, False),
    ],
    ids=["a-revealed-claim", "a-message", "the-stated-ledger", "no-claim-text",
         "no-claim-field", "already-confirmed", "not-a-mapping", "none"],
)
def test_what_the_demonstration_may_offer_is_a_predicate_both_sides_read(
    belief, offerable_
):
    """Four conditions, each of them a rule some other story owns, swept
    exhaustively — which is what a predicate buys.

    *A message is not a claim* is 15a's mark, read through
    ``half.store.records.derived_claim`` rather than by comparing a string here;
    *revealed rather than stated* is the glossary's own split; and *not already
    confirmed* is the ladder's ``known_to_main``.
    """
    assert offerable(belief) is offerable_


@pytest.mark.cap2_structure
def test_the_shipped_composition_carries_the_notice_by_value(monkeypatch):
    """*"A deployment with no notice connects no mailbox"* is asserted from the
    constructed ``Wiring`` rather than by finding a keyword in the composition
    root — which is how story 6d's identical claim passed with the value set to
    ``None``.

    Both halves: set, and unset.
    """
    told, plainly = notices({CONSENT_ENV: NOTICE, NOTHING_YET_ENV: NOTHING_YET})
    assert consenting.told(told) is True
    assert consenting.notice(told) == NOTICE
    assert plainly == NOTHING_YET

    empty, nothing = notices({})
    assert consenting.told(empty) is False
    assert consenting.notice(empty) == ""
    assert nothing == ""


@pytest.mark.cap2_structure
def test_the_shipped_wiring_holds_whatever_the_environment_said(tmp_path,
                                                                monkeypatch):
    """The same claim, through ``build`` itself, so the value a running Half
    holds is the one this file has been asserting about."""
    monkeypatch.setenv(CONSENT_ENV, NOTICE)
    monkeypatch.setenv(NOTHING_YET_ENV, NOTHING_YET)
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        assert consenting.notice(wiring.consent) == NOTICE
        assert wiring.nothing_yet == NOTHING_YET
    finally:
        wiring.registry.close()


@pytest.mark.cap2_structure
@pytest.mark.parametrize(
    "wording, told_",
    [({LEAVES_THE_MACHINE: NOTICE}, True), ({}, False),
     ({LEAVES_THE_MACHINE: ""}, False), ({LEAVES_THE_MACHINE: "   "}, False),
     ({LEAVES_THE_MACHINE: None}, False), ({LEAVES_THE_MACHINE: 7}, False),
     ({"something_else": NOTICE}, False)],
    ids=["said", "empty", "blank", "whitespace", "none", "not-a-string",
         "wrong-notice"],
)
def test_told_is_a_predicate_with_a_bypass_case(wording, told_):
    """``told`` is what the flow reads before it connects anything and what this
    file reads to say whether it should have. One function rather than a
    condition written out in each — this project has twice shipped a guard the
    tests approximated with a scan for a spelling."""
    consent = Consent(wording)
    assert consenting.told(consent) is told_
    assert (consenting.missing(consent) == ()) is told_
    assert (consenting.notice(consent) != "") is told_


@pytest.mark.cap2_structure
def test_a_notice_cannot_forge_a_line_into_what_it_is_sent_beside():
    """Every body on the wire goes through ``half.context.channels.sanitize``,
    and the notice is one — otherwise a deployment's own sentence could carry a
    line break and read as two messages, or forge a block boundary into the
    prompt it becomes the language sample for."""
    consent = Consent({LEAVES_THE_MACHINE: "first line\nsecond line"})
    assert "\n" not in consenting.notice(consent)
    assert "first line" in consenting.notice(consent)


@pytest.mark.cap2_structure
def test_the_notice_set_is_closed_and_carries_machine_names_only():
    """Adding a second thing the main must be told is one edit in one place and
    is picked up by ``missing``, ``told`` and every case that sweeps the set —
    rather than a second ``if`` in the flow that the next surface forgets."""
    assert NOTICES == (LEAVES_THE_MACHINE,)
    for name in NOTICES:
        assert name and not any(ch.isspace() for ch in name), name
    assert JOIN.strip() == "", "the join is a separator, not a word"
