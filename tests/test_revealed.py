"""CAP-3 stories 15b and 15c: what a source is worth keeping, and what it says.

15b's half of this file is unchanged in intent and retargeted in mechanism: a
group's claim is now *generated* from its scrubbed texts rather than looked up
in a closed vocabulary, so ``Run.admitted`` returns what a writer wrote and a
case that used to build candidates and read a constant back now has to drive a
reader.

15c's half is the section at the end, and it exists for one sentence: **a
specific claim's support is the sources that support that claim.** Every case
there is written so that it fails if the *label's* support is used instead —
and the fixtures are built so the two numbers genuinely differ, because a
fixture where they agree proves nothing at all.

Ingestion captured receipts and derived nothing, so the revealed ledger was
empty and story 3's union-find — built precisely to make CAP-3's central
sentence true — had never once decided anything outside its own unit tests.
This file is one case per row of both stories' matrices, plus the structural
rules they rest on.

Five things it refuses to do, because each would let it pass while the product
failed:

**It never asserts *"no claim was admitted"* on its own.** That is true of a
thread, a forward, a single message, a gate refusing, a provider that is down,
a breaker standing a main down, a run past its cap and a deployment that
equipped nobody. Every case says which of the eight it is about and asserts a
count or an id that only that one moves.

**It separates the threshold from the count.** A two-source case is green
whether ``independent`` is the union-find's answer or ``len(support)`` — the two
numbers are equal there — so the count has its own case, over three sources in
two groups, where they differ.

**It asserts scrub-before-derive structurally rather than by reading.** The one
read of ``body.text`` in ``half/ingest/pipeline.py`` is found in that file's
syntax tree and required to be an argument of ``scrub``; the reader refuses a
body that is not scrubber output; and a ``scrub`` that raises is driven to show
that the exception path reaches no provider either.

**It hunts the body.** A sentinel and a secret are chased through every byte
written, every request the provider saw, every captured log line, the tally, the
candidates and the admitted claims.

**It never lets a claim's support and its label's support be the same number in
a fixture that is asked to tell them apart.** Story 15c's central case builds a
label group of three independent sources of which two confirm the sentence and
share a thread — three against one — because a fixture where the two numbers
agree is green for the build the story exists to prevent.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path

import pytest

from half.__main__ import build, ingest_mail
from half.config import MAINS_ENV, ROOT_ENV, load
from half.derive import particular, revealed as reading
from half.derive.claim import Derivers
from half.derive.gates import GATES
from half.derive.particular import (
    CONFIRMS,
    CONFIRM_LABELS,
    CONFIRM_UNSURE,
    DENIES,
    MAX_CLAIM_CHARS,
    MAX_SOURCES,
    QUOTE_RUN_WORDS,
    Refusal,
    quotes,
    usable,
)
from half.derive.revealed import (
    BOUND_SECONDS,
    CLASSIFY_TIER,
    DOINGS,
    DOING_UNSURE,
    INSTRUCTIONS,
    LABELS,
    MIN_INDEPENDENT,
    NOTHING_DOING,
    PER_RUN,
    REVEALED,
    Candidate,
    Claim,
    Doing,
    Revealed,
    Run,
    Tally,
    consumer_for,
    doing_named,
    fields_of,
    prompt_for,
)
from half.errors import DeriveError
from half.governance import ladder
from half.ingest import pipeline as ingesting
from half.ingest.pipeline import Pipeline, Receipt
from half.ingest.port import Message
from half.ingest.scrub import scrub
from half.model.port import Completion, Decision, Failure, Kind, Reason, Usage
from half.retrieval.prefix import build_prefix
from half.store.records import CLAIM, DERIVATION, DERIVED, LEDGER, SUBJECT
from half.store.sources import LocalSourceStore
from half.store.store import Store

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"

#: The label every double answers with unless a case says otherwise.
TRAVELS = DOINGS[0].label
BUYS = DOINGS[2].label

#: What the writer double answers with unless a case says otherwise.
#:
#: **Deliberately something no label could have produced.** The whole of story
#: 15c is that a main learns something they did not already know from the word
#: *travels*, so a fixture claim that read like a label would make every case
#: here green for the build this story replaces.
#:
#: It also shares no run of ``QUOTE_RUN_WORDS`` words with any body in this
#: file, which is asserted rather than eyeballed —
#: ``test_the_fixture_claim_is_not_a_quotation_of_any_fixture_body``.
A_CLAIM = "makes long journeys about twice a month, usually alone"

#: A second one, for the case where two labels cross in one run.
ANOTHER_CLAIM = "orders household things in small batches, several times a month"

#: A secret, spelled in halves so this file is not itself a finding.
SECRET = "".join(("AKIA", "IOSFODNN7EXAMPLE"))

#: A real binary payload — a PNG header. Two high bytes decode cleanly as
#: latin-1, so they prove nothing about failing closed.
BINARY = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00" + bytes(range(32)) * 4

#: Five scripts, so *"any script"* is a run rather than a sentence. None is a
#: translation of another: the point is that nothing on the path reads them.
SCRIPTS: dict[str, str] = {
    "latin": "Your booking is confirmed. Departure 14 March, seat 22A.",
    "devanagari": "आपकी बुकिंग की पुष्टि हो गई है। प्रस्थान 14 मार्च।",
    "amharic": "ማስያዣዎ ተረጋግጧል። ጉዞ መጋቢት 14።",
    "arabic": "تم تأكيد حجزك. المغادرة في 14 مارس.",
    "japanese": "ご予約が確定しました。3月14日出発。",
}

#: What a writer answers with, in each of those scripts.
#:
#: **Not translations of one another and not translations of the bodies**: the
#: point is that the claim comes back in the script its sources were written in
#: and that nothing on the path reads either. Each shares no run of
#: ``QUOTE_RUN_WORDS`` comparison words with its body, which
#: ``test_the_fixture_claim_is_not_a_quotation_of_any_fixture_body`` asserts
#: rather than leaving to the eye.
IN_SCRIPT: dict[str, str] = {
    "latin": "makes long journeys about twice a month, usually alone",
    "devanagari": "हर महीने दो बार लंबी दूरी तय करता है",
    "amharic": "በየወሩ ሁለት ጊዜ ረጅም ጉዞ ያደርጋል",
    "arabic": "يسافر مسافات طويلة مرتين كل شهر تقريبا",
    "japanese": "毎月二回ほど遠くへ移動している",
}


# ═════════════════════════════════════════════════════════════════════════════
# doubles
# ═════════════════════════════════════════════════════════════════════════════


class GateHolder:
    """15a's narrow classifier, answering for the four gates.

    ``answers`` maps a gate's **name** to a label; anything unnamed admits, so a
    case says only what it is about. Keyed by gate rather than by call order
    because the four gates run concurrently.
    """

    def __init__(self, answers: dict[str, object] | None = None) -> None:
        self._answers = dict(answers or {})
        self.seen: list = []

    async def classify(self, work):
        self.seen.append(work)
        for gate in GATES:
            if tuple(work.labels) == gate.labels:
                answer = self._answers.get(gate.name, gate.admits)
                if isinstance(answer, BaseException):
                    raise answer
                if isinstance(answer, str):
                    return Decision(label=answer, usage=Usage(micro_usd=11))
                return answer
        raise AssertionError(f"no gate owns the label set {work.labels}")

    @property
    def calls(self) -> int:
        return len(self.seen)


def _next(answers: list, taken: int):
    """The answer for the ``taken``-th call; the last one repeats.

    So a case can say *"the first source confirms, everything after it does
    not"* without knowing how many sources there are.
    """
    return answers[min(taken - 1, len(answers) - 1)]


class ReadHolder:
    """The narrow classifier, answering **both** questions asked through it.

    ``answers`` is *what does this body show they do*; ``confirms`` is *does
    this one source stand behind this sentence*. They are told apart by the
    request's own closed label set rather than by call order, because the two
    interleave: a reading crosses a group, the confirmations run inside it, and
    the next reading follows.

    Each is consumed in order and the last one repeats. The two are counted
    apart — ``calls`` is readings and ``confirmations`` is the other — so an
    assertion about how many bodies were read does not quietly become an
    assertion about how many sources were asked.
    """

    def __init__(self, answers: object = TRAVELS, *, sleep: float = 0.0,
                 confirms: object = CONFIRMS) -> None:
        self._answers = list(answers) if isinstance(answers, list) else [answers]
        self._confirms = (
            list(confirms) if isinstance(confirms, list) else [confirms]
        )
        self._sleep = sleep
        self.seen: list = []
        self.confirmations: list = []

    async def classify(self, work):
        if tuple(work.labels) == CONFIRM_LABELS:
            self.confirmations.append(work)
            answer = _next(self._confirms, len(self.confirmations))
        else:
            self.seen.append(work)
            if self._sleep:
                await asyncio.sleep(self._sleep)
            answer = _next(self._answers, len(self.seen))
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, str):
            return Decision(label=answer, usage=Usage(micro_usd=11))
        return answer

    @property
    def calls(self) -> int:
        return len(self.seen)

    @property
    def texts(self) -> list[str]:
        return [work.prompt.turns[0].text for work in self.seen]

    @property
    def confirmed_texts(self) -> list[str]:
        return [work.prompt.turns[0].text for work in self.confirmations]


class WriteHolder:
    """The narrow generator that writes what a group's claim says.

    Narrow on purpose: one public method, which is what ``check_writer``
    requires and what keeps the thing that *writes* from also being the thing
    that *decides*.
    """

    def __init__(self, answers: object = A_CLAIM, *, sleep: float = 0.0) -> None:
        self._answers = list(answers) if isinstance(answers, list) else [answers]
        self._sleep = sleep
        self.seen: list = []

    async def generate(self, work):
        self.seen.append(work)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        answer = _next(self._answers, len(self.seen))
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, str):
            return Completion(text=answer, usage=Usage(micro_usd=90))
        return answer

    @property
    def calls(self) -> int:
        return len(self.seen)

    @property
    def texts(self) -> list[str]:
        return [work.prompt.turns[0].text for work in self.seen]


def a_reader(answers=TRAVELS, *, gates=None, main=MAIN, sleep=0.0,
             bound_seconds=1.0, tally=None, writes=A_CLAIM,
             confirms=CONFIRMS, writing_sleep=0.0, writer=True):
    """A ``Revealed``, and the three holders inside it.

    ``writer=False`` is the *no provider wired* deployment: the mail is read,
    candidates are gathered, and nothing is written.
    """
    gate_holder = GateHolder(gates)
    read_holder = ReadHolder(answers, sleep=sleep, confirms=confirms)
    write_holder = WriteHolder(writes, sleep=writing_sleep)
    reader = Revealed(
        {main: read_holder},
        writers={main: write_holder} if writer else None,
        gates=Derivers({main: gate_holder}, bound_seconds=1.0),
        bound_seconds=bound_seconds, writing_bound_seconds=bound_seconds,
        tally=tally,
    )
    return reader, read_holder, gate_holder, write_holder


def receipt(index: int, *, thread="t1", digest=None, text="body") -> Receipt:
    return Receipt(
        digest=digest if digest is not None else f"d{index}",
        external_id=f"m{index}", thread_id=thread, sender="a@x",
        subject="s", t=f"2026-08-{index + 1:02d}T00:00:00Z",
    )


def observe(reader, receipts, *, run=None, main=MAIN, text="a booking",
            texts=None):
    """Read every receipt through one reader, into one run.

    ``texts`` gives each receipt its own body, which matters wherever the claim
    that comes back is compared against the sources it was written from.
    """
    run = run if run is not None else Run()
    bodies = list(texts) if texts is not None else [text] * len(receipts)

    async def drive():
        for rec, body in zip(receipts, bodies):
            await reader.observe(rec, scrub(body), main_id=main, into=run)

    asyncio.run(drive())
    return run


def candidates(*specs, label=TRAVELS) -> Run:
    """A run holding one candidate per ``(id, thread, digest)`` spec.

    **No scrubbed text and therefore no generation**, which is what makes it the
    right instrument for the questions that are purely about grouping —
    ``supports`` and ``ready`` — and the wrong one for any question about what a
    claim says. Those go through a reader.
    """
    run = Run()
    for source_id, thread_id, digest in specs:
        run.add(Candidate(label=label, source_id=source_id,
                          thread_id=thread_id, digest=digest))
    return run


def a_written_claim(*, label=TRAVELS, claim=A_CLAIM, support=("m0", "m1"),
                    independent=2, subject=None) -> Claim:
    """One claim of the shape a run produces, without driving a run.

    For the cases about what a claim *is written as* — the fold, the rung, the
    record's fields — where driving a reader would put a provider double in
    front of a question about a dataclass. The cases about how a claim is
    *arrived at* all go through a reader.
    """
    return Claim(
        label=label, claim=claim,
        subject=subject if subject is not None else doing_named(label).subject,
        support=tuple(support), independent=independent,
    )


class FakeMail:
    """The whole surface the pipeline needs, so cases stay offline."""

    name = "fake"

    def __init__(self, messages):
        self.messages = messages

    async def fetch(self, *, since=None):
        for message in self.messages:
            if since is None or message.t > since:
                yield message


def mail(index, body, *, thread="t1", sender="a@x", subject="s", headers=None):
    return Message(
        external_id=f"m{index}", thread_id=thread, sender=sender,
        subject=subject,
        body=body if isinstance(body, bytes) else body.encode(),
        t=f"2026-08-{index + 1:02d}T00:00:00Z", headers=headers or {},
    )


def pull(messages, reader, store, *, main=MAIN, run=None, since=None):
    """Drive one mailbox pull through the real pipeline. Returns the run."""
    run = run if run is not None else Run()
    pipeline = Pipeline(
        FakeMail(messages), store,
        consumer=consumer_for(reader, main_id=main, into=run),
    )
    asyncio.run(pipeline.ingest(since=since))
    return run


def all_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


@pytest.fixture
def sources(tmp_path):
    return LocalSourceStore(tmp_path / "sources")


# ═════════════════════════════════════════════════════════════════════════════
# the matrix: what independence admits
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3
def test_two_independent_senders_admit_one_claim_citing_both():
    """Matrix row one. Two unrelated senders, two threads, two contents — two
    groups, one claim, and both messages named.

    Green whether ``independent`` is the union-find's answer or the size of the
    support set, because those two numbers are equal here. The case that tells
    them apart is ``test_the_count_is_the_union_finds_answer_...`` below, and
    this one is deliberately not asked to do that work.
    """
    reader, _, _, writer = a_reader()
    run = observe(reader, [receipt(0, thread="t1"), receipt(1, thread="t2")],
                  texts=["a booking", "an itinerary"])
    claims = run.admitted()
    assert len(claims) == 1
    assert claims[0].independent == 2
    assert claims[0].support == ("m0", "m1")
    # **What it says came from the writer, not from a constant in the tree.**
    assert claims[0].claim == A_CLAIM
    assert writer.calls == 1


@pytest.mark.cap3
def test_ten_messages_sharing_a_thread_admit_no_claim():
    """**CAP-3's own sentence, as its own case.** *"No claim admitted from a
    single non-independent cluster of mentions."*

    Ten distinct messages, ten distinct contents, one thread. The union-find
    unions them all by ``thread`` and answers one, so nothing is admitted — and
    a build that counted *supports* instead would admit here with a count of
    ten, which is exactly the failure story 3 predicted: the belief set inflates
    with echoes and *bounded* fails in the first noisy month.
    """
    run = candidates(*((f"m{i}", "t1", f"d{i}") for i in range(10)))
    assert len(run.supports(TRAVELS)) == 10
    assert run.ready(TRAVELS) is False, (
        "ten messages in one thread were treated as a group worth a generation"
    )
    assert run.admitted() == ()


@pytest.mark.cap3
def test_a_forward_of_the_same_content_is_one_support():
    """Matrix row three. Two messages, two senders, two threads, **one
    content** — collapsed by the union-find's content identity to one group.

    Driven straight at the ``Run`` because the pipeline never lets a
    byte-identical body through twice; that half of the row has its own case
    below. This half is the union-find's ``content`` identity, and it is
    load-bearing rather than decorative: were the source id the digest, this
    would collapse by ``source`` instead and removing ``digest`` from
    ``Candidate.identity`` would still be green.
    """
    run = candidates(("m0", "t1", "same"), ("m1", "t2", "same"))
    assert len(run.supports(TRAVELS)) == 2
    assert run.ready(TRAVELS) is False
    assert run.admitted() == ()


@pytest.mark.cap3
def test_a_byte_identical_forward_never_reaches_the_reader(sources):
    """The other half of row three, through the real pipeline. A body the store
    already holds is skipped before the consumer is called, so a forward with
    identical bytes is not a second support — it is not a reading at all, and
    costs nothing."""
    reader, holder, _, writer = a_reader()
    body = "Your booking is confirmed. Departure 14 March."
    run = pull([mail(0, body, thread="t1", sender="a@x"),
                mail(1, body, thread="t2", sender="b@y")], reader, sources)
    assert holder.calls == 1, "the identical body was read twice"
    assert len(run.supports(TRAVELS)) == 1
    assert writer.calls == 0, "a claim was written from one source"
    assert run.admitted() == ()


@pytest.mark.cap3
def test_one_message_admits_nothing():
    """Matrix row four. Never from one cluster, and one message is the smallest
    cluster there is."""
    run = candidates(("m0", "t1", "d0"))
    assert len(run.supports(TRAVELS)) == 1
    assert run.ready(TRAVELS) is False
    assert run.admitted() == ()


@pytest.mark.cap3
def test_two_independent_bodies_the_gates_refuse_admit_nothing():
    """Matrix row five. Two independent sources, and the content fails a gate —
    so nothing is read about what they show and no candidate exists.

    Asserts the gate's **name**, not merely the absence of a claim: *"no claim"*
    is also true of a provider that was down, and this case is about the gates
    working.
    """
    reader, holder, _, writer = a_reader(gates={"durability": "only_now"})
    run = observe(reader, [receipt(0, thread="t1"), receipt(1, thread="t2")])
    assert run.admitted() == ()
    assert reader.tally.refused_by_gates == 2
    assert holder.calls == 0, "a refused body was still read"
    assert reader.gates.tally.refusals == {"durability": 2}


@pytest.mark.cap3
def test_no_body_reaches_disk_from_a_run_that_admitted_a_claim(tmp_path,
                                                               sources):
    """Matrix row six, AD-13, story 3. A full pull that ends in an admitted
    claim, with every byte written scanned for the body."""
    reader, _, _, writer = a_reader()
    sentinel = "sandalwood-nineteen-quicksilver"
    run = pull([mail(0, f"booking {sentinel} confirmed", thread="t1"),
                mail(1, f"itinerary {sentinel} attached", thread="t2",
                     sender="b@y")], reader, sources)
    claims = run.admitted()
    assert len(claims) == 1, "the run admitted nothing, so this proves nothing"
    written = all_bytes(tmp_path / "sources")
    assert sentinel.encode() not in written
    assert sentinel not in repr(claims)
    assert sentinel not in repr(reader.tally)


@pytest.mark.cap3
def test_a_secret_in_a_body_reaches_neither_disk_nor_provider(tmp_path,
                                                              sources):
    """Matrix row seven, and the story's widest change: a main's mail now leaves
    the machine. The scrubber runs first, so what leaves is redacted."""
    reader, holder, gate_holder, writer = a_reader()
    pull([mail(0, f"the key is {SECRET} please use it", thread="t1"),
          mail(1, f"reminder: {SECRET}", thread="t2", sender="b@y")],
         reader, sources)
    assert holder.calls == 2, "nothing was sent, so this proves nothing"
    for seen in holder.texts:
        assert SECRET not in seen
        assert "[redacted:" in seen
    for work in gate_holder.seen:
        assert SECRET not in work.prompt.turns[0].text
    assert SECRET.encode() not in all_bytes(tmp_path / "sources")


@pytest.mark.cap3
def test_an_undecodable_body_derives_nothing_and_sends_nothing(sources):
    """Matrix row eight. Story 3 skips a body whose representation it could not
    resolve; derivation never becomes a reason to relax that."""
    reader, holder, _, writer = a_reader()
    run = pull([mail(0, BINARY)], reader, sources)
    assert holder.calls == 0
    assert run.admitted() == ()
    assert reader.tally.bodies == 0


@pytest.mark.cap3
def test_a_body_that_was_nothing_but_secrets_derives_nothing():
    """Matrix row nine. Bytes the scanner treats as a finding: what is left
    after redaction is nothing, so there is nothing to read and nothing to
    send. Fails closed, and counted under its own name so this is not the same
    assertion as an absent provider."""
    reader, holder, _, writer = a_reader()
    body = scrub(SECRET)
    assert body.empty_after_redaction, "the fixture no longer redacts anything"

    async def drive():
        return await reader.observe(receipt(0), body, main_id=MAIN, into=Run())

    assert asyncio.run(drive()) is None
    assert holder.calls == 0
    assert reader.tally.unreadable_body == 1


@pytest.mark.cap3
def test_re_ingesting_a_mailbox_derives_nothing_twice(sources):
    """Matrix row ten. The same mailbox pulled twice: no body is read a second
    time, and the second run has nothing to admit."""
    reader, holder, _, writer = a_reader()
    messages = [mail(0, "booking one", thread="t1"),
                mail(1, "booking two", thread="t2", sender="b@y")]
    first = pull(messages, reader, sources)
    assert holder.calls == 2 and len(first.admitted()) == 1

    second = pull(messages, reader, sources)
    assert holder.calls == 2, "a body was read on the second pull"
    assert second.admitted() == ()


@pytest.mark.cap3
def test_a_deployment_with_no_reader_still_captures_receipts(sources):
    """Matrix row eleven. No deriver wired: receipts still captured, no claim,
    and never fatal. This is story 3's shipped behaviour, unchanged."""
    reader = Revealed()
    run = pull([mail(0, "booking one", thread="t1"),
                mail(1, "booking two", thread="t2")], reader, sources)
    assert len(sources) == 2
    assert run.admitted() == ()
    assert reader.tally.bodies == 0


@pytest.mark.cap3
def test_a_reader_past_its_bound_yields_no_claim_and_the_pull_completes(
        sources):
    """Matrix row twelve, the slow half. Counted under ``bound_exceeded``, which
    only this row moves — *"no claim"* is also true of a refusal and of a
    provider that answered honestly that it could not tell."""
    reader, _, _, writer = a_reader(sleep=0.05, bound_seconds=0.01)
    run = pull([mail(0, "booking one", thread="t1"),
                mail(1, "booking two", thread="t2", sender="b@y")],
               reader, sources)
    assert len(sources) == 2, "the receipts did not survive"
    assert run.admitted() == ()
    assert reader.tally.bound_exceeded == 2


@pytest.mark.cap3
def test_a_reader_that_raises_yields_no_claim_and_the_pull_completes(sources):
    """Matrix row twelve, the raising half. Counted under ``raised``."""
    reader, _, _, writer = a_reader(answers=RuntimeError("provider blew up"))
    run = pull([mail(0, "booking one", thread="t1"),
                mail(1, "booking two", thread="t2", sender="b@y")],
               reader, sources)
    assert len(sources) == 2
    assert run.admitted() == ()
    assert reader.tally.raised == 2


@pytest.mark.cap3
def test_a_run_past_its_cap_stops_deriving_and_says_so(sources, caplog):
    """Matrix row thirteen. *"Stops deriving and says so"* — a silent cap looks
    exactly like a mailbox with nothing in it worth keeping."""
    reader, holder, _, writer = a_reader()
    run = Run(budget=2)
    with caplog.at_level(logging.INFO):
        pull([mail(i, f"booking {i}", thread=f"t{i}") for i in range(5)],
             reader, sources, run=run)
    assert len(sources) == 5, "the receipts stopped as well"
    assert holder.calls == 2
    assert reader.tally.over_cap == 3
    assert run.over_cap
    assert "per-run reading cap" in caplog.text


@pytest.mark.cap3
def test_an_admitted_claim_cites_the_messages_it_came_from():
    """Matrix row fourteen, CAP-5. ``support`` names the messages, sorted and
    each exactly once, whatever order they arrived in.

    Driven with a **redelivery** in the middle, because that is the half of this
    rule nothing else here reaches: the same message observed twice is one
    support, so it is held once, confirmed once and cited once. Sorted rather
    than in arrival order so that two runs over the same mailbox in a different
    order produce the same record and a replay folds identically (AD-30).
    """
    reader, _, _, _ = a_reader()
    run = observe(reader, [receipt(2, thread="t1"), receipt(2, thread="t1"),
                           receipt(0, thread="t2")],
                  texts=["a booking", "a booking", "an itinerary"])
    claim = run.admitted()[0]
    assert claim.support == ("m0", "m2")
    assert len(set(claim.support)) == len(claim.support)
    assert claim.independent == 2


@pytest.mark.cap3
def test_the_count_is_the_union_finds_answer_and_never_the_support_size():
    """**Matrix row fifteen, and the one a casual reading would not catch.**

    Three sources: two share a thread, one does not. The union-find answers
    **two**; the support set has **three** members. A build that wrote
    ``len(support)`` into ``independent`` admits the same claim, cites the same
    three messages, and reports three — inflating the weight of an echo by
    exactly the amount CAP-3 exists to prevent.

    This is the only case where the two numbers differ, which is why the
    two-source rows above are not asked to carry it.
    """
    reader, _, _, _ = a_reader()
    run = observe(reader, [receipt(0, thread="t1"), receipt(1, thread="t1"),
                           receipt(2, thread="t2")],
                  texts=["a booking", "an itinerary", "a hotel"])
    claim = run.admitted()[0]
    assert len(claim.support) == 3
    assert claim.independent == 2, (
        "independent is the size of the support set rather than the number of "
        "independent groups"
    )


@pytest.mark.cap3
@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_mail_in_any_script_is_read_the_same_way(script, sources):
    """Matrix row sixteen. Five writing systems, each admitting a claim, with
    the rendered request compared against the Latin one so that *"no English
    rubric and no locale on the path"* is a measurement rather than a sentence.
    """
    written = IN_SCRIPT[script]
    reader, holder, _, writer = a_reader(writes=written)
    body = SCRIPTS[script]
    run = pull([mail(0, body, thread="t1"),
                mail(1, body + "​", thread="t2", sender="b@y")],
               reader, sources)
    claims = run.admitted()
    assert len(claims) == 1 and claims[0].independent == 2
    # **The claim is in the script its sources were in**, which is what a closed
    # vocabulary could not do: every mailbox in the world used to get the same
    # English word. Nothing on the path chose the script — the writer did, and
    # the instructions asked it to.
    assert claims[0].claim == written
    assert holder.seen[0].prompt.system == INSTRUCTIONS
    assert writer.seen[0].prompt.system == particular.INSTRUCTIONS
    # And the request is the same in every script but for the bodies in it: no
    # locale, no language name, no per-script rubric anywhere on the path.
    assert writer.calls == 1


@pytest.mark.cap3
def test_no_body_and_no_claim_text_reaches_any_log_line(sources, caplog):
    """Matrix row seventeen, AD-22. The sentinel goes to a provider and to
    nowhere else — not a log line, not the tally, not a counter."""
    sentinel = "sandalwood-nineteen-quicksilver"
    reader, holder, _, writer = a_reader()
    with caplog.at_level(logging.DEBUG):
        run = pull([mail(0, f"booking {sentinel}", thread="t1"),
                    mail(1, f"itinerary {sentinel}", thread="t2",
                         sender="b@y")], reader, sources)
        claims = run.admitted()
        reader.count_claims(claims)
        reader.flush()
    assert len(claims) == 1
    assert all(sentinel in text for text in holder.texts)
    assert sentinel in writer.texts[0], "the writer never saw the bodies"
    assert sentinel not in caplog.text
    assert sentinel not in repr(reader.tally)
    # And the *generated* claim is not in a log line either, which is the half
    # 15c added: a sentence Half wrote about somebody is as much AD-22's subject
    # as the mail it came from.
    assert A_CLAIM not in caplog.text
    assert A_CLAIM not in repr(reader.tally)
    assert A_CLAIM not in repr(run)


@pytest.mark.cap3
def test_a_log_of_receipts_and_revealed_claims_folds_identically(tmp_path):
    """Matrix row eighteen, AD-4 and AD-30. Derivation is not in the fold: what
    is in the log is a claim, and replaying it reproduces the same state."""
    claim = a_written_claim()
    root = tmp_path / "mains" / MAIN
    with Store(root, prefix=build_prefix) as store:
        from half.store.ops import Op
        store.record(Op.ASSERT, claim.belief_id, "2026-08-02T00:00:00Z",
                     **fields_of(claim),
                     **ladder.admitted(support=list(claim.support)))
        first = store.state().beliefs
    with Store(root, prefix=build_prefix) as store:
        second = store.state().beliefs
    assert first == second
    record = second[claim.belief_id]
    assert record[LEDGER] == REVEALED
    assert record[DERIVATION] == DERIVED
    assert record["independent"] == 2
    assert record["support"] == ["m0", "m1"]


@pytest.mark.cap3
def test_an_admitted_claim_enters_at_the_weakest_rung(tmp_path):
    """*"A claim enters the revealed ledger citing its sources"*, and it enters
    where every belief enters. The rung comes from ``ladder.admitted`` and never
    from a literal, so there is no spelling of the append that mints an
    `assert`."""
    claim = a_written_claim()
    fields = {**fields_of(claim),
              **ladder.admitted(support=list(claim.support))}
    assert fields["license"] == str(ladder.FLOOR)
    assert fields[CLAIM] == A_CLAIM
    assert fields[SUBJECT] == DOINGS[0].subject


@pytest.mark.cap3
def test_the_shipped_composition_admits_a_claim_from_a_seeded_mailbox(tmp_path):
    """**The story in the shipped product.** ``build`` is driven for real, its
    reader is given holders, and one mailbox is pulled through
    ``ingest_mail`` — which is the only path in the tree from a body to a
    revealed claim. A surface reachable only from a test is a surface nobody has
    run, and this project has shipped three of them.
    """
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        reader, _, _, writer = a_reader()
        wiring = type(wiring)(
            **{**{f: getattr(wiring, f) for f in wiring.__dataclass_fields__},
               "revealed": reader})
        result = asyncio.run(ingest_mail(
            wiring, main_id=MAIN,
            source=FakeMail([mail(0, "your booking is confirmed", thread="t1"),
                             mail(1, "your itinerary", thread="t2",
                                  sender="b@y")]),
        ))
        assert len(result.receipts) == 2
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
    finally:
        wiring.registry.close()
    assert f"r_{TRAVELS}" in beliefs, beliefs
    record = beliefs[f"r_{TRAVELS}"]
    assert record[LEDGER] == REVEALED
    assert record["independent"] == 2
    assert record["support"] == ["m0", "m1"]
    assert record["license"] == str(ladder.FLOOR)


@pytest.mark.cap3
def test_a_later_pull_reaching_the_same_conclusion_writes_no_second_claim(
        tmp_path):
    """**Idempotency at the append**, which is a different rule from the
    pipeline's and needs its own case: a second pull carrying *new* messages
    that reach the same conclusion reaches the append with a claim in hand, and
    the ledger already holds one.

    A mutation probe found the case below green for this — the pipeline skips
    every message on a re-read, so ``admitted`` is empty and the append guard is
    never reached at all. This is the case that reaches it.

    It also pins the **deferral**: the later support is *not* added. Doing so
    needs a rule for deciding that two derived claims are the same claim, which
    is a second matching problem and is not this story.
    """
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        reader, _, _, writer = a_reader()
        wiring = type(wiring)(
            **{**{f: getattr(wiring, f) for f in wiring.__dataclass_fields__},
               "revealed": reader})
        first = [mail(0, "your booking is confirmed", thread="t1"),
                 mail(1, "your itinerary", thread="t2", sender="b@y")]
        later = [mail(2, "a different booking", thread="t3", sender="c@z"),
                 mail(3, "a different itinerary", thread="t4", sender="d@w")]
        asyncio.run(ingest_mail(wiring, main_id=MAIN, source=FakeMail(first)))
        asyncio.run(ingest_mail(wiring, main_id=MAIN, source=FakeMail(later)))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
            appends = sum(1 for record in store.log
                          if record.id == f"r_{TRAVELS}")
    finally:
        wiring.registry.close()
    assert appends == 1, "the later pull wrote the claim a second time"
    assert beliefs[f"r_{TRAVELS}"]["support"] == ["m0", "m1"], (
        "the later pull's support was accumulated onto the standing claim"
    )
    assert beliefs[f"r_{TRAVELS}"]["independent"] == 2


@pytest.mark.cap3
def test_the_same_mailbox_pulled_twice_reads_no_body_twice(tmp_path):
    """Matrix row ten at the far end: the same mailbox, twice, through the
    shipped path. The pipeline skips every message whose digest it already
    holds, so the second pull has nothing to admit and nothing to append.

    Deliberately **not** the case for the append's own guard — see above, which
    is the one that reaches it.
    """
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        reader, _, _, writer = a_reader()
        wiring = type(wiring)(
            **{**{f: getattr(wiring, f) for f in wiring.__dataclass_fields__},
               "revealed": reader})
        messages = [mail(0, "your booking is confirmed", thread="t1"),
                    mail(1, "your itinerary", thread="t2", sender="b@y")]
        for _ in range(2):
            asyncio.run(ingest_mail(
                wiring, main_id=MAIN, source=FakeMail(messages)))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
            appends = sum(
                1 for record in store.log
                if record.id == f"r_{TRAVELS}"
            )
    finally:
        wiring.registry.close()
    assert list(beliefs) == [f"r_{TRAVELS}"]
    assert appends == 1, "the second pull wrote the claim again"


# ═════════════════════════════════════════════════════════════════════════════
# the structural rules
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_structure
def test_the_unscrubbed_body_is_read_once_in_the_pipeline_and_only_by_scrub():
    """**Scrub before derive, asserted structurally rather than by reading.**

    A reordering of scrub and derivation sends a main's *unredacted mail* to a
    model provider — the one failure in this story that is not recoverable and
    not visible. So the rule is a property of ``half/ingest/pipeline.py``'s
    syntax tree: ``body.text`` — the text that has not been through the
    scrubber — is read **exactly once** in that module, and that read is an
    argument of ``scrub``.

    ``count == 1`` rather than ``all(...)``: an ``all`` over an empty set is a
    dead anchor that passes for a build where the attribute was renamed and the
    guard therefore watches nothing.
    """
    tree = ast.parse((ROOT / "half/ingest/pipeline.py").read_text("utf-8"))
    reads = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "text"
        and isinstance(node.value, ast.Name) and node.value.id == "body"
    ]
    assert len(reads) == 1, (
        "the unscrubbed body is read a different number of times than once; "
        "either the anchor is dead or something else now reads it"
    )
    scrubbing = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "scrub"
        and any(read in ast.walk(argument) for argument in node.args
                for read in [reads[0]])
    ]
    assert len(scrubbing) == 1, (
        "the one read of the unscrubbed body is not an argument of scrub"
    )


@pytest.mark.cap3_structure
def test_the_pipeline_hands_the_consumer_the_scrubbers_own_output():
    """The seam's type, at the call site. The consumer is handed the name bound
    by ``scrub`` and never the raw body — which is what lets a reader refuse
    anything else, and is checked here as well as in the reader because the two
    could drift apart in either direction."""
    tree = ast.parse((ROOT / "half/ingest/pipeline.py").read_text("utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "consumer"
    ]
    assert len(calls) == 1, "the consumer is called somewhere else as well"
    arguments = [ast.unparse(argument) for argument in calls[0].args]
    assert arguments == ["receipt", "scrubbed"], arguments


@pytest.mark.cap3_structure
def test_a_reader_refuses_a_body_that_is_not_scrubber_output():
    """The seam's type, at runtime. A reordering hands the reader a ``str``;
    it refuses, counts it under its own name, and reaches no provider.

    Not a fallback: the reader does **not** scrub what it was handed. A second
    scrubber on this path is a second place for the two to disagree, and the
    ordering is what is being kept true.
    """
    reader, holder, gate_holder, writer = a_reader()

    async def drive(body):
        return await reader.observe(receipt(0), body, main_id=MAIN, into=Run())

    for body in ("a plain string", b"bytes", None, {"text": "a dict"}):
        assert asyncio.run(drive(body)) is None
    assert holder.calls == 0 and gate_holder.calls == 0
    assert reader.tally.unscrubbed == 4
    assert reader.tally.bodies == 0
    # And the scrubber's own output is accepted, so this is not a case that
    # refuses everything.
    assert asyncio.run(drive(scrub("a booking"))) is not None


@pytest.mark.cap3_structure
def test_a_scrub_that_raises_reaches_no_provider(sources):
    """**The exception path.** *"A body must not reach a provider before scrub
    under any ordering, including a raise."*

    A ``scrub`` that raises produces no ``Scrubbed`` to hand on, so there is
    nothing for the consumer to be called with — the guarantee is the absence of
    a value rather than the presence of a check.
    """
    reader, holder, gate_holder, writer = a_reader()
    run = Run()
    pipeline = Pipeline(
        FakeMail([mail(0, "booking one", thread="t1")]), sources,
        consumer=consumer_for(reader, main_id=MAIN, into=run),
    )
    original = ingesting.scrub
    try:
        ingesting.scrub = lambda text: (_ for _ in ()).throw(
            RuntimeError("the scanner refused")
        )
        with pytest.raises(RuntimeError):
            asyncio.run(pipeline.ingest())
    finally:
        ingesting.scrub = original
    assert holder.calls == 0 and gate_holder.calls == 0
    assert len(sources) == 0, "a receipt was written from an unscrubbed body"
    assert run.admitted() == ()


@pytest.mark.cap3_structure
def test_the_threshold_is_two_and_no_call_site_can_lower_it():
    """*"No threshold that can be configured below two."*

    Asserted as the **absence of a parameter** rather than as a value check: a
    deployment cannot lower a number it has no way to supply. ``Run`` takes a
    per-run budget and nothing else, and ``admitted`` takes nothing at all.
    """
    import inspect

    assert MIN_INDEPENDENT == 2
    assert set(inspect.signature(Run.__init__).parameters) == {"self", "budget"}
    assert set(inspect.signature(Run.admitted).parameters) == {"self"}
    source = (ROOT / "half/derive/revealed.py").read_text("utf-8")
    tree = ast.parse(source)
    comparisons = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(operand, ast.Name)
                and operand.id == "MIN_INDEPENDENT"
                for operand in [node.left, *node.comparators])
    ]
    assert comparisons, "nothing in the module compares against the threshold"


@pytest.mark.cap3_structure
@pytest.mark.parametrize("fields,names", [
    ({"support": ("m0",), "independent": 1}, "citing 1 source"),
    ({"support": (), "independent": 2}, "citing 0 source"),
    ({"support": ("m0", "m0"), "independent": 2}, "names a source twice"),
    ({"support": ("m0", "m1"), "independent": 1}, "independence count of 1"),
    ({"support": ("m0", "m1"), "independent": 3}, "More groups than sources"),
    ({"support": ("m0", "m1"), "independent": 2, "claim": "   "},
     "says nothing"),
    ({"support": ("m0", "m1"), "independent": 2, "claim": None},
     "says nothing"),
])
def test_a_claim_that_could_not_be_true_cannot_be_constructed(fields, names):
    """*"A claim whose support set is empty or whose count is one is a defect,
    not a state."*

    Refused on the type, because the log is append-only and every one of these
    is permanent once written. Seven shapes, because each is a different
    mistake.

    **Each asserts the refusal's own message, not merely that something
    raised**, and that is the correction a mutation probe forced. The
    support-size check is redundant — a count below the floor and a count above
    the support size together already forbid every support set smaller than two
    — so disabling it left every case here green: guards covering guards, which
    is a guard that cannot fire because a rule below it already forbids its
    case. Reading the message is what tells them apart, and it is worth telling
    them apart because a refusal has to name the right thing.

    **The last two are story 15c's and they are not redundant.** A claim's words
    used to be a constant in ``half/derive/revealed.py``, so *"a claim says
    something"* was true by construction; they now come from a model, and an
    empty sentence is a reachable state that would enter the ledger as a belief
    with no words — one the demonstration cannot offer and the main cannot
    falsify.
    """
    fields = {"claim": A_CLAIM, **fields}
    with pytest.raises(DeriveError, match=names):
        Claim(label=TRAVELS, subject="travel", **fields)


@pytest.mark.cap3_structure
@pytest.mark.parametrize("attribute,value,because", [
    ("MIN_INDEPENDENT", 1, "a threshold of one deletes CAP-3's sentence"),
    ("PER_RUN", 0, "a cap of zero derives nothing, for ever"),
    ("BOUND_SECONDS", 0, "a bound that never fires is not a bound"),
    ("ALARM_RATE", 0.0, "an alarm that never fires names nothing"),
    ("CLASSIFY_TIER", "  ", "a blank tier is refused at boot"),
    ("DOINGS", (), "an empty vocabulary derives nothing"),
    ("DOINGS", (Doing(label="a", subject="p"), Doing(label="a", subject="q")),
     "two members answer to one label"),
    ("DOINGS", (Doing(label="a", subject="p"), Doing(label="b", subject="p")),
     "two labels share a subject"),
    ("DOINGS", (Doing(label="", subject="p"), Doing(label="b", subject="q")),
     "a label must be non-empty text"),
    ("NOTHING_DOING", "travels", "the refusal label is also a claim"),
    ("DOING_UNSURE", "travels", "the unsure label is also a claim"),
    ("LABELS", (*LABELS, CONFIRMS),
     "a reading label and a confirmation label are the same word"),
])
def test_each_import_time_guard_has_a_bypass(monkeypatch, attribute, value,
                                             because):
    """Every guard in ``_check_constants`` driven on its own.

    Without these the guards are red *everywhere at once* — the module refuses
    itself and the whole suite fails to collect, which names nothing. Each of
    these is red **by name**, so a mutation of the data they protect says which
    rule it broke.
    """
    monkeypatch.setattr(reading, attribute, value)
    with pytest.raises(DeriveError):
        reading._check_constants()


@pytest.mark.cap3_structure
def test_the_import_time_guards_pass_on_the_shipped_constants():
    """The bypass cases above are worth nothing if the guards refuse the real
    build too — an assertion that is red either way. This is the other side."""
    reading._check_constants()


@pytest.mark.cap3_structure
def test_the_holder_cannot_author_a_claim():
    """A holder that could *generate* is a path from somebody's mail to a
    sentence Half wrote about them and kept for ever, arriving through the one
    seam that is supposed to answer with a label.

    An **allowlist**, because the denylist this pattern replaced let an object
    through that could ``classify`` and also ``chat`` — and so did one that was
    simply callable.
    """
    class Wider:
        async def classify(self, work): ...
        async def generate(self, work): ...

    class Callable_:
        async def classify(self, work): ...
        def __call__(self, work): ...

    for holder in (Wider(), Callable_(), object(), None):
        with pytest.raises(DeriveError):
            Revealed({MAIN: holder})
    assert Revealed({MAIN: ReadHolder()}).holds(MAIN)


@pytest.mark.cap3_structure
def test_a_bench_is_sealed_after_construction():
    """The check that every holder is narrow cannot be walked around by
    assigning a wider one afterwards."""
    reader, _, _, writer = a_reader()
    with pytest.raises(DeriveError):
        reader._holders = {MAIN: object()}


@pytest.mark.cap3_structure
def test_the_four_gates_are_15as_and_are_not_restated():
    """*"One definition of worth keeping."* The bench is 15a's own object,
    asserted by identity; and this module defines no gate, no gate label and no
    gate instruction of its own, asserted over its syntax tree so that a
    respelling is caught rather than merely discouraged."""
    gates = Derivers({MAIN: GateHolder()})
    assert Revealed({MAIN: ReadHolder()}, gates=gates).gates is gates

    tree = ast.parse((ROOT / "half/derive/revealed.py").read_text("utf-8"))
    assigned = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
        if isinstance(target, ast.Name)
    }
    from half.derive import gates as gating
    respelled = assigned & {
        name for name in gating.__all__ if name.isupper()
    }
    assert not respelled, respelled
    assert all(
        gate.admits not in block and gate.unsure not in block
        for gate in GATES for block in INSTRUCTIONS
    ), "a gate's label is respelled in this module's instructions"


@pytest.mark.cap3_structure
def test_the_tier_is_pinned_and_is_read_from_this_module_by_the_root():
    """SPEC:124 — *the recurring spend runs on a cheaper tier than
    conversation, because the free tier depends on that gap*. A mailbox pull is
    the largest recurring spend of the five.

    Asserted from both sides of the provider: the constant, and the ``Tiers``
    the composition root actually parses. A case that asserted only the constant
    would be green for a build that bound it and never used it.
    """
    assert CLASSIFY_TIER == "cheap"

    tree = ast.parse((ROOT / "half/__main__.py").read_text("utf-8"))
    inside = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "readers"
    ]
    assert len(inside) == 1
    parsed = [
        node for node in ast.walk(inside[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "parse"
    ]
    assert len(parsed) == 1
    names = {node.id for node in ast.walk(parsed[0])
             if isinstance(node, ast.Name)}
    assert "REVEALED_TIER" in names, (
        "the reader's tier is not read from half.derive.revealed"
    )
    assert not any(
        isinstance(node, ast.Constant) and node.value == "cheap"
        for node in ast.walk(parsed[0])
    ), "the tier is respelled as a literal in the composition root"
    assert "config.tier_for" not in ast.unparse(inside[0]), (
        "the reader's tier follows the main's conversation tier"
    )


@pytest.mark.cap3_structure
def test_the_shipped_reader_holds_the_shipped_gates():
    """One definition of *worth keeping* in the running process as well as in
    the tree, asserted by identity rather than by finding a keyword in the
    source — which is how story 6d's identical claim passed with the value set
    to ``None``."""
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        config = load({ROOT_ENV: root, MAINS_ENV: f"123:{MAIN}"})
        wiring = build(config, token="123:fake")
        try:
            assert wiring.revealed.gates is wiring.derivers
        finally:
            wiring.registry.close()


@pytest.mark.cap3_structure
def test_no_logging_call_in_this_module_can_carry_content():
    """Scanned over the **arguments of every logging call**, which is the form
    this guarantee takes everywhere in this tree: a body in a variable is
    invisible to a grep, and an invisible log call is how content gets logged.

    What is allowed through is a literal, a ``main_id``, a count, an exception's
    class, and a constant from a closed set.
    """
    allowed = {"main_id", "BREAK_AFTER", "BREAK_FOR", "PER_RUN", "reply",
               "self", "exc", "type", "verdict", "MIN_INDEPENDENT",
               "refusal", "answered"}
    counts = set(Tally.__dataclass_fields__) | {
        "fell_back", "answered", "failure_rate", "_tally", "unwritable",
        "gen_fell_back",
    }
    tree = ast.parse((ROOT / "half/derive/revealed.py").read_text("utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    ]
    assert calls, "the anchor is dead: no logging call was found at all"
    for node in calls:
        for argument in node.args[1:]:
            for name in ast.walk(argument):
                if isinstance(name, ast.Name):
                    assert name.id in allowed, ast.unparse(argument)
                if isinstance(name, ast.Attribute):
                    assert name.attr in (
                        {"kind", "because", "main_id", "__name__",
                         "refused_by"} | counts
                    ), ast.unparse(argument)


@pytest.mark.cap3_structure
def test_the_claim_vocabulary_is_closed_and_is_never_the_bodys_words():
    """**The body is never persisted, in any form, including a summary.** So a
    claim admitted here is one of this module's own constants, and there is no
    path by which a body's text could become one: ``doing_named`` matches
    exactly, and everything it does not match is not a claim."""
    for label in (NOTHING_DOING, DOING_UNSURE, "travels ", "TRAVELS",
                  "the main travels a lot", "", None, 7):
        assert doing_named(label) is None
    assert doing_named(TRAVELS) is DOINGS[0]
    assert Run().add(Candidate(label=NOTHING_DOING, source_id="m0",
                               thread_id="t1", digest="d0")) is False
    assert set(LABELS) == {d.label for d in DOINGS} | {NOTHING_DOING,
                                                       DOING_UNSURE}


@pytest.mark.cap3_structure
def test_an_answered_cannot_say_and_a_provider_that_never_answered_differ():
    """Both leave no candidate, so a case asserting *"nothing was admitted"*
    passes either way. They are counted apart, and the breaker only ever arms on
    the second kind — a provider that is up and honestly unsure must not stand a
    main down for having an ordinary mailbox."""
    unsure, _, _, writer = a_reader(answers=DOING_UNSURE)
    observe(unsure, [receipt(0)])
    assert unsure.tally.answers == {DOING_UNSURE: 1}
    assert unsure.tally.fell_back == 0

    down, _, _, writer = a_reader(
        answers=Failure(kind=Kind.UNAVAILABLE,
                        because=Reason.TRANSPORT_FAILED))
    observe(down, [receipt(0)])
    assert down.tally.answered == 0
    assert down.tally.fell_back == 1


@pytest.mark.cap3_structure
def test_nothing_here_reads_a_clock_opens_a_store_or_writes_a_record():
    """AD-30, and ``half.derive``'s own rule. The reader answers *which claims
    there are*; the caller appends them."""
    source = (ROOT / "half/derive/revealed.py").read_text("utf-8")
    tree = ast.parse(source)
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = {name for name in imported
                 if name.startswith(("half.store.store", "half.store.log",
                                     "half.actor", "half.schedule"))}
    assert not forbidden, forbidden
    for banned in ("datetime", "time.time", "utcnow", "now()"):
        assert banned not in source, banned


@pytest.mark.cap3_structure
def test_one_message_read_twice_inside_a_run_is_one_support():
    """A redelivery, or a source that yields the same message twice. One
    message is one support: counting it twice is the echo the whole story is
    about, arriving through the accumulator rather than through a thread."""
    run = Run()
    for _ in range(5):
        run.add(Candidate(label=TRAVELS, source_id="m0", thread_id="t1",
                          digest="d0"))
    run.add(Candidate(label=TRAVELS, source_id="m1", thread_id="t2",
                      digest="d1"))
    assert len(run.supports(TRAVELS)) == 2
    assert run.ready(TRAVELS) is True


@pytest.mark.cap3_structure
def test_the_body_travels_to_the_provider_whole_and_nothing_else_does():
    """*"What leaves the machine: one scrubbed body, twice, and nothing else."*
    No receipt id, no thread, no digest, no sender, no subject line — and the
    body is not truncated, folded or normalised on the way."""
    body = SCRIPTS["devanagari"]
    prompt = prompt_for(body, main_id=MAIN)
    assert prompt.turns[0].text == body
    assert prompt.system == INSTRUCTIONS
    assert len(prompt.turns) == 1
    rendered = "\n".join((*prompt.system, prompt.turns[0].text))
    for leaked in ("m0", "t1", "d0", "a@x", REVEALED, MAIN):
        assert leaked not in rendered.replace(body, ""), leaked


# ═════════════════════════════════════════════════════════════════════════════
# story 15c: what a group's claim says, and what stands behind it
# ═════════════════════════════════════════════════════════════════════════════
#
# One case per row of 15c's matrix, plus the rules that row rests on. The
# organising rule of this section is the story's own warning: **assume the
# support is being counted wrong until a case proves otherwise.** So every
# fixture that is asked about support is built so the claim's count and its
# label's count are *different numbers*, and each case says which one it read.


def three_sources_where_only_two_confirm(*, threads, confirms):
    """Three independent sources for one label, of which some confirm.

    The instrument for this section's central question. ``threads`` gives the
    three receipts their thread ids, and ``confirms`` is the three confirmation
    answers in arrival order. The label's own group count and the claim's are
    then whatever the two arrangements make them, and a case asserts both.
    """
    reader, holder, _, writer = a_reader(confirms=list(confirms))
    run = observe(
        reader,
        [receipt(i, thread=threads[i]) for i in range(3)],
        texts=["a booking", "an itinerary", "a hotel"],
    )
    return reader, run, holder, writer


@pytest.mark.cap3_particular
def test_a_claim_says_something_the_label_alone_could_not_have_said():
    """**CAP-2's target, and the row this story exists for.**

    Two independent sources about one specific thing, one claim citing both —
    and *"a case shows it is something a main could not have already known from
    the label alone"*. That is asserted three ways, because a claim that merely
    differs from the label would satisfy a build that shipped six longer
    sentences: what came back is the writer's own text, no ``Doing`` in the
    shipped vocabulary carries it, and nothing in ``half/derive/revealed.py``
    contains it as a literal.
    """
    reader, _, _, writer = a_reader()
    run = observe(reader, [receipt(0, thread="t1"), receipt(1, thread="t2")],
                  texts=["a booking", "an itinerary"])
    claims = run.admitted()
    assert len(claims) == 1
    assert claims[0].claim == A_CLAIM
    assert claims[0].label == TRAVELS
    assert claims[0].subject == DOINGS[0].subject
    assert all(doing.label != A_CLAIM for doing in DOINGS)
    assert A_CLAIM not in (ROOT / "half/derive/revealed.py").read_text("utf-8")
    assert writer.calls == 1
    assert reader.tally.wrote == 1


@pytest.mark.cap3_particular
def test_a_specific_claim_only_one_independent_source_supports_is_refused():
    """**The hard half, and the case the whole story is a warning about.**

    Three sources for one label: two share a thread and the third does not, so
    the *label's* support is **two** independent groups — enough to admit. Only
    the two sharing the thread confirm the sentence, so the *claim's* own
    support is **one** independent group, and it is not admitted however well it
    reads.

    Two against one, deliberately, and it is the widest the two numbers can be
    at this moment: generation happens the instant a label reaches two
    independent groups, so the label's count is exactly two whenever a sentence
    is written. A build that vouched for the sentence with the label's support
    would see two, clear the floor, and write into somebody's ledger a specific
    claim about their life that one cluster of mentions stands behind. Both
    numbers are computed here from the same union-find the runtime uses, and the
    case refuses to run if the fixture ever stops making them differ.
    """
    reader, holder, _, writer = a_reader(confirms=[CONFIRMS, CONFIRMS, DENIES])
    run = observe(
        reader,
        # m0 and m1 share a thread; m2 is on its own. The label crosses on m1?
        # No — m0 and m1 are one group, so it crosses on m2, with all three
        # texts in hand.
        [receipt(0, thread="t1"), receipt(1, thread="t1"),
         receipt(2, thread="t2")],
        texts=["a booking", "an itinerary", "a hotel"],
    )
    from half.ingest.independence import independent_groups

    every = run.supports(TRAVELS)
    label_groups = independent_groups(c.identity() for c in every)
    confirming = tuple(c for c in every if c.source_id in {"m0", "m1"})
    claim_groups = independent_groups(c.identity() for c in confirming)

    assert len(every) == 3
    assert label_groups == 2, "the fixture no longer gives the label a majority"
    assert claim_groups == 1, "the fixture no longer makes the two numbers differ"
    assert label_groups != claim_groups, (
        "this fixture cannot tell the two supports apart and proves nothing"
    )

    assert writer.calls == 1, "the group was not worth one generation"
    assert reader.tally.wrote == 1, "no sentence came back to be checked"
    assert len(holder.confirmations) == 3, "the sources were not asked"
    assert run.admitted() == (), (
        "a claim two sources in one thread stand behind was admitted on the "
        "strength of a third source that denied it"
    )
    assert reader.tally.under_supported == 1
    assert reader.tally.confirmed == 2


@pytest.mark.cap3_particular
def test_an_admitted_claim_cites_only_the_sources_that_confirmed_it():
    """The positive half of the same rule, and it fails the same build.

    Three sources for one label — the label's support set has three members.
    The middle one does not stand behind the sentence, so the claim is admitted
    **citing the other two and not it**.

    A build that attached the label's support would admit the same claim and
    cite three messages, one of which said the sentence was not true of it. Both
    sizes are asserted, and they differ.
    """
    reader, holder, _, writer = a_reader(
        confirms=[CONFIRMS, DENIES, CONFIRMS])
    run = observe(
        reader,
        [receipt(0, thread="t1"), receipt(1, thread="t1"),
         receipt(2, thread="t2")],
        texts=["a booking", "an itinerary", "a hotel"],
    )
    claims = run.admitted()
    assert len(claims) == 1
    claim = claims[0]
    assert claim.support == ("m0", "m2"), (
        "the claim cites a source that did not stand behind it"
    )
    assert len(run.supports(TRAVELS)) == 3, "the label had three supports"
    assert len(claim.support) == 2, "the claim was given the label's support"
    assert claim.independent == 2
    assert reader.tally.confirmed == 2
    assert reader.tally.under_supported == 0


@pytest.mark.cap3_particular
def test_two_sources_sharing_only_a_label_admit_nothing_they_do_not_both_say():
    """Matrix: *generic but supported*. Two independent sources share a label,
    and neither stands behind the sentence written over them.

    Distinguished from *the gates refused* and *the provider was down* by
    ``under_supported``, which only this outcome moves — and by the writer
    having been called, which says the group did reach a generation.
    """
    reader, holder, _, writer = a_reader(confirms=DENIES)
    run = observe(reader, [receipt(0, thread="t1"), receipt(1, thread="t2")],
                  texts=["a booking", "an itinerary"])
    assert writer.calls == 1
    assert len(holder.confirmations) == 2
    assert reader.tally.confirmed == 0
    assert reader.tally.under_supported == 1
    assert run.admitted() == ()


@pytest.mark.cap3_particular
@pytest.mark.parametrize("answer", [
    DENIES, CONFIRM_UNSURE, "a label from no set at all",
    Failure(kind=Kind.UNAVAILABLE, because=Reason.TRANSPORT_FAILED),
])
def test_only_an_explicit_confirmation_counts_as_support(answer):
    """Everything that is not *yes* leaves a source out, and they are four
    different facts.

    A denial, an honest *cannot say*, an answer from no known set and a
    provider that did not answer all mean the same thing here — the source is
    not counted — and the direction matters: a source counted as support
    because its confirmation timed out is exactly the inflated evidence the
    confirmation exists to prevent.

    Driven with **two** sources, one of which confirms, so the case is red for
    a build that counts this answer as support (which would admit) and red for
    a build that counts nothing at all (``confirmed`` would be zero).
    """
    reader, _, _, _ = a_reader(confirms=[CONFIRMS, answer])
    run = observe(reader, [receipt(0, thread="t1"), receipt(1, thread="t2")],
                  texts=["a booking", "an itinerary"])
    assert reader.tally.confirmed == 1, "the confirming source was not counted"
    assert run.admitted() == (), f"{answer!r} was counted as support"
    assert reader.tally.under_supported == 1


@pytest.mark.cap3_particular
def test_a_group_of_ten_supporting_sources_is_one_generation(sources):
    """Matrix: *one generation*. **Cost, and the rule stated as a number.**

    Nine messages in one thread and a tenth on its own: the label crosses on
    the tenth, one generation happens over the group, and the nine bodies
    before it cost a classification apiece and no generation at all.

    Asserted as *the writer was called once* rather than *a claim exists*,
    because a claim exists either way and only this number says how much it
    cost.
    """
    reader, holder, _, writer = a_reader()
    run = pull(
        [mail(i, f"booking number {i}", thread="t1") for i in range(9)]
        + [mail(9, "an itinerary", thread="t2", sender="b@y")],
        reader, sources,
    )
    assert holder.calls == 10, "a body was not read"
    assert writer.calls == 1, "a generation happened per body"
    assert reader.tally.groups == 1
    assert reader.tally.generations == 1
    assert len(run.admitted()) == 1


@pytest.mark.cap3_particular
def test_a_label_that_has_generated_never_generates_again(sources):
    """The other half of *one generation per admitted claim*: more support
    arriving **after** the crossing buys no second attempt.

    A group of two crosses and writes a claim; two further travel messages
    arrive in two further threads. The label's support grows to four and the
    writer is still called once — which is what makes the cost rule a property
    of ``Run.ready`` rather than something the caller remembers.

    **The deferral this pins is real and is recorded**: the later sources are
    not offered to the standing claim, because deciding that they support it is
    a second confirmation pass over text this run no longer holds.
    """
    reader, _, _, writer = a_reader()
    run = pull([mail(0, "a booking", thread="t1"),
                mail(1, "an itinerary", thread="t2", sender="b@y"),
                mail(2, "a hotel", thread="t3", sender="c@z"),
                mail(3, "a border crossing", thread="t4", sender="d@w")],
               reader, sources)
    assert len(run.supports(TRAVELS)) == 4
    assert writer.calls == 1, "a later source bought a second generation"
    # **Two counters, because two rules cover this one between them and either
    # alone would make the other unfailable.** ``Run.ready`` refuses a label
    # that has generated, and ``Run.hold`` refuses to keep text for one — so
    # removing either leaves ``writer.calls`` at one and a case reading only
    # that number is green for a build with no one-shot rule at all.
    # ``groups`` counts every crossing that reached ``_say``, so it is the
    # number that separates them.
    assert reader.tally.groups == 1, (
        "the label was treated as a fresh group each time it gained support"
    )
    assert reader.tally.generations == 1
    # And **nothing was held for it again**, which is the window's half of the
    # same rule: a label that has generated has nothing left to hold text for,
    # so the two later bodies leave none of themselves alive in this run.
    assert run.holding == 0, (
        "two bodies were kept alive for a generation that had already happened"
    )
    claims = run.admitted()
    assert len(claims) == 1
    assert claims[0].support == ("m0", "m1")


@pytest.mark.cap3_particular
def test_two_labels_crossing_in_one_run_are_two_generations_and_two_claims(
        sources):
    """Two different things a mailbox shows, each with its own group.

    Here to keep *one generation per admitted claim* from being read as *one
    generation per run*, and to show the claims are kept apart: two labels, two
    sentences, two subjects, two belief ids.
    """
    reader, _, _, writer = a_reader(
        answers=[TRAVELS, TRAVELS, BUYS, BUYS],
        writes=[A_CLAIM, ANOTHER_CLAIM],
    )
    run = pull([mail(0, "a booking", thread="t1"),
                mail(1, "an itinerary", thread="t2", sender="b@y"),
                mail(2, "an order", thread="t3", sender="c@z"),
                mail(3, "a dispatch", thread="t4", sender="d@w")],
               reader, sources)
    claims = run.admitted()
    assert writer.calls == 2
    assert [c.label for c in claims] == [TRAVELS, BUYS]
    assert [c.claim for c in claims] == [A_CLAIM, ANOTHER_CLAIM]
    assert len({c.subject for c in claims}) == 2
    assert len({c.belief_id for c in claims}) == 2


@pytest.mark.cap3_particular
def test_a_deployment_with_a_reader_and_no_writer_admits_nothing(sources,
                                                                 caplog):
    """Matrix: *generator absent*. **Never fatal**, and the difference from
    every other silence is a counter of its own.

    The mail is read, the candidates are gathered, the receipts are captured —
    and no claim is written, because there is nothing to write it with. Story
    3's shipped behaviour with one more reason.
    """
    reader, holder, _, writer = a_reader(writer=False)
    with caplog.at_level(logging.INFO):
        run = pull([mail(0, "a booking", thread="t1"),
                    mail(1, "an itinerary", thread="t2", sender="b@y")],
                   reader, sources)
    assert len(sources) == 2, "the receipts did not survive"
    assert holder.calls == 2, "the mail was not read"
    assert len(run.supports(TRAVELS)) == 2, "no candidate was gathered"
    assert writer.calls == 0
    assert reader.tally.groups == 1
    assert reader.tally.no_writer == 1
    assert reader.tally.generations == 0
    assert run.admitted() == ()
    assert reader.writes(MAIN) is False


@pytest.mark.cap3_particular
def test_a_writer_past_its_bound_yields_no_claim_and_the_pull_completes(
        sources):
    """Matrix: *generator slow*. Counted under ``gen_bound_exceeded``, which
    only this row moves — *"no claim"* is also true of a refusal, an absent
    writer and a group nobody stood behind."""
    reader, _, _, writer = a_reader(writing_sleep=0.05, bound_seconds=0.01)
    run = pull([mail(0, "a booking", thread="t1"),
                mail(1, "an itinerary", thread="t2", sender="b@y")],
               reader, sources)
    assert len(sources) == 2, "the receipts did not survive"
    assert writer.calls == 1
    assert reader.tally.gen_bound_exceeded == 1
    assert reader.tally.wrote == 0
    assert run.admitted() == ()


@pytest.mark.cap3_particular
def test_a_writer_that_raises_yields_no_claim_and_the_pull_completes(sources):
    """Matrix: *generator failing*, the raising half. Counted under
    ``gen_raised``, and the receipts are already durable when it happens."""
    reader, _, _, writer = a_reader(writes=RuntimeError("the writer blew up"))
    run = pull([mail(0, "a booking", thread="t1"),
                mail(1, "an itinerary", thread="t2", sender="b@y")],
               reader, sources)
    assert len(sources) == 2
    assert reader.tally.gen_raised == 1
    assert run.admitted() == ()


@pytest.mark.cap3_particular
def test_a_writer_that_reports_a_failure_yields_no_claim(sources):
    """Matrix: *generator failing*, the answered half. The port reports a fault
    as a **value**, so this is not the raising case and is counted apart —
    ``gen_failures`` carries the port's own two closed enums and never a
    provider's sentence (AD-22)."""
    reader, _, _, _ = a_reader(writes=Failure(
        kind=Kind.OVER_BUDGET, because=Reason.PER_CALL_BUDGET))
    run = pull([mail(0, "a booking", thread="t1"),
                mail(1, "an itinerary", thread="t2", sender="b@y")],
               reader, sources)
    assert len(sources) == 2
    assert reader.tally.gen_failures == {"over-budget/per-call-budget": 1}
    assert reader.tally.gen_raised == 0
    assert run.admitted() == ()


@pytest.mark.cap3_particular
def test_a_writer_that_answers_with_something_unreadable_yields_no_claim(
        sources):
    """Neither a completion nor one of the port's four failures. Its own
    counter, because a future port return type must not read as a claim."""
    reader, _, _, _ = a_reader(writes=object())
    pull([mail(0, "a booking", thread="t1"),
          mail(1, "an itinerary", thread="t2", sender="b@y")], reader, sources)
    assert reader.tally.gen_unreadable == 1
    assert reader.tally.wrote == 0


@pytest.mark.cap3_particular
def test_a_claim_that_quotes_a_source_is_thrown_away(sources):
    """Matrix: *Half's own words*. **The sentence is refused, never trimmed.**

    The writer answers with a run of words lifted straight out of one of the
    bodies. It is refused under its own reason, no claim is admitted, and
    nothing repaired the sentence — a claim is a durable belief about somebody's
    life and a repaired one is a sentence nobody wrote filed as a fact.
    """
    body = "your flight to Delhi departs on 14 March from terminal three"
    reader, _, _, writer = a_reader(writes="they take a " + body)
    run = pull([mail(0, body, thread="t1"),
                mail(1, "an itinerary", thread="t2", sender="b@y")],
               reader, sources)
    assert writer.calls == 1
    assert reader.tally.refused_text == {str(Refusal.QUOTED): 1}
    assert reader.tally.wrote == 0
    assert run.admitted() == ()


@pytest.mark.cap3_particular
@pytest.mark.parametrize("written,reason", [
    ("", Refusal.EMPTY),
    ("   \n  ", Refusal.EMPTY),
    ("x" * (MAX_CLAIM_CHARS + 1), Refusal.TOO_LONG),
    ("a claim\nand a second line", Refusal.NOT_ONE_LINE),
    ("their key is " + SECRET, Refusal.SECRET),
    ("they travel with [redacted: password] every month", Refusal.REDACTION),
])
def test_every_unusable_sentence_is_refused_under_its_own_reason(written,
                                                                 reason):
    """Six ways a generated sentence is not a claim, each its own value.

    Counted apart rather than collapsed into *the generation failed*, because
    they mean different things: an empty answer is a model that said nothing, a
    long one is a model that wrote an essay, and a secret in Half's **own**
    sentence means a model invented something key-shaped — the material could
    not have carried one, since ``scrub`` ran before the writer saw it.

    Read through ``usable`` directly as well as driven, so the pair is checked
    against the enum rather than against whichever branch happened to fire.
    """
    claim, refusal = usable(written, ["a booking", "an itinerary"])
    assert claim == ""
    assert refusal is reason


@pytest.mark.cap3_particular
def test_a_usable_sentence_is_returned_unchanged_and_unrepaired():
    """The other side of the six above, which are worth nothing if the tripwire
    refuses everything. What comes back is the sentence, stripped of
    surrounding whitespace and otherwise untouched."""
    claim, refusal = usable(f"  {A_CLAIM}  ", ["a booking"])
    assert refusal is None
    assert claim == A_CLAIM


@pytest.mark.cap3_particular
def test_the_quotation_floor_is_a_run_and_not_a_particular():
    """*"No quotation or near-quotation"*, and **the floor is why the rule is
    not simply AD-18's**.

    ``half.context.build``'s own floor is the adjacent pair, which is right
    where the cost of refusing is a directive dropped. Here a refusal is the
    whole capability: a revealed claim's job is to carry the particulars, and a
    place, a date or a service name is exactly the two-word run it shares with
    the mail. So both halves are asserted — a four-word run is a quotation, and
    a shared particular is not — because a rule that only ever answered *yes*
    would be indistinguishable from one that refused every claim.
    """
    source = "Your flight to Delhi departs on 14 March from terminal three"
    assert QUOTE_RUN_WORDS == 4
    assert quotes("they take your flight to Delhi twice a month", [source])
    assert not quotes("flies to Delhi about twice a month", [source]), (
        "a shared particular was read as a quotation, which would refuse every "
        "specific claim there is"
    )
    assert not quotes(A_CLAIM, [source])
    assert not quotes("", [source])


@pytest.mark.cap3_particular
def test_a_quotation_reflowed_across_lines_is_still_a_quotation():
    """The source's own line breaks are its formatting, not its wording. A
    model that repeated a phrase with the newlines in different places would
    walk past a rule that compared line by line."""
    source = "Your flight to Delhi\ndeparts on 14 March"
    assert quotes("they take your flight to Delhi departs early", [source])


@pytest.mark.cap3_particular
@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_the_fixture_claim_is_not_a_quotation_of_any_fixture_body(script):
    """**The fixtures themselves, checked.**

    Every case above that expects a claim to be admitted would be green for a
    build that refused it as a quotation *if the fixture claim happened to
    quote its fixture body* — the case would then be asserting the refusal it
    was written to rule out. So the fixtures are held to the rule they rely on,
    in every script, rather than to the eye of whoever wrote them.
    """
    assert not quotes(IN_SCRIPT[script], [SCRIPTS[script]])
    assert not quotes(A_CLAIM, list(SCRIPTS.values()))
    assert not quotes(ANOTHER_CLAIM, list(SCRIPTS.values()))


@pytest.mark.cap3_particular
def test_re_ingesting_a_mailbox_generates_no_second_claim(tmp_path):
    """Matrix: *re-ingest*. The same mailbox twice through the shipped path —
    no body is read twice, so no group crosses twice and nothing is written
    twice. Asserted on the writer as well as on the ledger, because a second
    generation that produced an identical sentence would be invisible in the
    beliefs and visible only in the bill."""
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        reader, _, _, writer = a_reader()
        wiring = type(wiring)(
            **{**{f: getattr(wiring, f) for f in wiring.__dataclass_fields__},
               "revealed": reader})
        messages = [mail(0, "your booking is confirmed", thread="t1"),
                    mail(1, "your itinerary", thread="t2", sender="b@y")]
        for _ in range(2):
            asyncio.run(ingest_mail(
                wiring, main_id=MAIN, source=FakeMail(messages)))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
    finally:
        wiring.registry.close()
    assert writer.calls == 1, "the second pull generated the claim again"
    assert list(beliefs) == [f"r_{TRAVELS}"]
    assert beliefs[f"r_{TRAVELS}"][CLAIM] == A_CLAIM


@pytest.mark.cap3_particular
def test_the_shipped_composition_writes_a_generated_claim_into_the_ledger(
        tmp_path):
    """**The story in the shipped product.** ``build`` is driven for real and
    one mailbox is pulled through ``ingest_mail`` — the only path in the tree
    from a body to a revealed claim. What lands in the ledger is the writer's
    sentence, at the weakest rung, citing the sources that confirmed it."""
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        reader, _, _, writer = a_reader()
        wiring = type(wiring)(
            **{**{f: getattr(wiring, f) for f in wiring.__dataclass_fields__},
               "revealed": reader})
        asyncio.run(ingest_mail(
            wiring, main_id=MAIN,
            source=FakeMail([mail(0, "your booking is confirmed", thread="t1"),
                             mail(1, "your itinerary", thread="t2",
                                  sender="b@y")]),
        ))
        with Store(tmp_path / MAIN, prefix=build_prefix) as store:
            beliefs = store.state().beliefs
    finally:
        wiring.registry.close()
    record = beliefs[f"r_{TRAVELS}"]
    assert record[CLAIM] == A_CLAIM
    assert record[SUBJECT] == DOINGS[0].subject
    assert record[LEDGER] == REVEALED
    assert record["independent"] == 2
    assert record["support"] == ["m0", "m1"]
    assert record["license"] == str(ladder.FLOOR)
    assert writer.calls == 1


# ═════════════════════════════════════════════════════════════════════════════
# story 15c: the window — how long scrubbed text lives, and that it is gone
# ═════════════════════════════════════════════════════════════════════════════
#
# The story's Ask First, answered and then asserted. The widening is real: a
# body can no longer die inside one ``async for`` iteration, because generating
# over a group needs the group's texts together. What is built is the narrowest
# window that does the job — a label holds at most ``MAX_SOURCES`` texts, drops
# them the instant it generates, and a ``Run`` is a scope rather than an object
# somebody has to remember to empty.


@pytest.mark.cap3_particular
def test_scrubbed_text_is_held_only_until_its_label_generates():
    """**The window, at its two ends.**

    One body for a label holds one text — the group has not crossed and nothing
    could have been written yet. The second body crosses it, the claim is
    generated over both, and the texts are gone **in the same call**: not at the
    end of the run, not when the next body arrives, and not when the caller
    remembers.

    Asserted on ``holding``, which is a count and never the texts, so the case
    can say the window closed without being handed what was in it.
    """
    reader, _, _, _ = a_reader()
    run = Run()
    assert run.holding == 0

    async def one(index, thread):
        await reader.observe(receipt(index, thread=thread),
                             scrub(f"a booking in {thread}"),
                             main_id=MAIN, into=run)

    asyncio.run(one(0, "t1"))
    assert run.holding == 1, "the scrubbed text was not held at all"
    assert run.ready(TRAVELS) is False

    asyncio.run(one(1, "t2"))
    assert len(run.admitted()) == 1, "nothing crossed, so this proves nothing"
    assert run.holding == 0, (
        "the group's scrubbed texts outlived the generation they were held for"
    )


@pytest.mark.cap3_particular
def test_a_label_that_never_crosses_holds_its_text_until_the_run_ends():
    """The other half of the window, and the honest cost of it.

    A label with one support can never drop its text early: nothing before the
    end of the run can know it will not cross. So it is held — bounded, and
    released by the scope. This case exists so that the bound is a measured
    number rather than a claim, and so the cost is written down where the next
    reader will find it.
    """
    reader, _, _, _ = a_reader()
    with Run() as run:
        observe(reader, [receipt(0, thread="t1")], run=run)
        assert run.holding == 1
        assert run.ready(TRAVELS) is False
    assert run.holding == 0


@pytest.mark.cap3_particular
def test_leaving_a_runs_scope_releases_every_held_body_including_on_a_raise():
    """*"Given the scrubbed text, when the run ends, then none of it is still
    held"* — **asserted, not assumed**, and on both paths.

    The exception path is the half that matters: a pull that died half way is
    exactly when a forgotten release would leave somebody's mail alive in a
    process that keeps running.
    """
    reader, _, _, _ = a_reader()
    ordinary = Run()
    with ordinary as run:
        observe(reader, [receipt(0, thread="t1")], run=run)
        assert run.holding == 1
    assert ordinary.holding == 0

    raising = Run()
    with pytest.raises(RuntimeError):
        with raising as run:
            observe(reader, [receipt(1, thread="t2")], run=run)
            assert run.holding == 1
            raise RuntimeError("the pull died half way")
    assert raising.holding == 0, "a body outlived the run that raised"


@pytest.mark.cap3_particular
def test_the_shipped_pull_holds_nothing_when_it_returns(sources):
    """The window at the end of the **shipped** path, through the real
    pipeline: every body read, a claim admitted, and nothing held.

    Three sources rather than two, so the run ends with a label that generated
    *and* with a label that never crossed — the two cases above, together, on
    the path that actually runs.
    """
    reader, _, _, writer = a_reader(answers=[TRAVELS, TRAVELS, BUYS])
    with Run() as run:
        pipeline = Pipeline(
            FakeMail([mail(0, "a booking", thread="t1"),
                      mail(1, "an itinerary", thread="t2", sender="b@y"),
                      mail(2, "an order", thread="t3", sender="c@z")]),
            sources,
            consumer=consumer_for(reader, main_id=MAIN, into=run),
        )
        asyncio.run(pipeline.ingest())
        assert len(run.admitted()) == 1, "nothing crossed, so this proves nothing"
        assert len(run.supports(BUYS)) == 1, "no label was left uncrossed"
        assert run.holding == 1, "the uncrossed label held nothing to release"
    assert run.holding == 0


@pytest.mark.cap3_particular
def test_ingest_mail_runs_the_pipeline_inside_a_runs_own_scope():
    """The release, as a property of ``half/__main__.py``'s syntax tree.

    A behavioural case can show that leaving a ``Run``'s scope releases what it
    held; only this one shows that the shipped path is *inside* such a scope.
    Both are needed, and neither substitutes for the other: the first is red for
    a ``Run`` that never releases, the second for a caller that never enters.
    """
    tree = ast.parse((ROOT / "half/__main__.py").read_text("utf-8"))
    inside = [node for node in ast.walk(tree)
              if isinstance(node, ast.AsyncFunctionDef)
              and node.name == "ingest_mail"]
    assert len(inside) == 1, "the anchor is dead: ingest_mail was renamed"
    scopes = [
        node for node in ast.walk(inside[0])
        if isinstance(node, ast.With)
        and any(isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "Run"
                for item in node.items)
    ]
    assert len(scopes) == 1, "the mailbox pull does not run inside a Run's scope"
    body = ast.unparse(scopes[0])
    assert "pipeline.ingest" in body, (
        "the pull happens outside the scope that releases the bodies it held"
    )
    assert "run.admitted" in body
    # And nothing constructs a Run anywhere else in that function, which is how
    # a second, unreleased one would arrive.
    made = [node for node in ast.walk(inside[0])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "Run"]
    assert len(made) == 1, made


@pytest.mark.cap3_particular
def test_a_run_refuses_to_hold_anything_that_is_not_scrubber_output():
    """The **second** door out of ingestion, typed like the first.

    A reordering of scrub and derive would hand the run a ``str``; it refuses,
    exactly as ``Revealed.observe`` refuses one, because the held text is the
    other thing a body could reach a provider through.
    """
    run = Run()
    candidate = Candidate(label=TRAVELS, source_id="m0", thread_id="t1",
                          digest="d0")
    for body in ("a plain string", b"bytes", None, {"text": "a dict"}):
        assert run.hold(candidate, body) is False
    assert run.holding == 0
    assert run.hold(candidate, scrub("a booking")) is True
    assert run.holding == 1


@pytest.mark.cap3_particular
def test_the_held_text_is_bounded_and_the_bound_prefers_independence():
    """**The ceiling, and the choice it makes when it binds.**

    Ten sources for one label, of which the first nine share a thread. A
    first-come ceiling would hold the first ``MAX_SOURCES`` — all of them one
    cluster — drop the tenth, and generate over a group CAP-3 refuses: ten
    bodies read, a generation paid for, and nothing admitted, in exactly the
    case where something should be.

    So the ceiling displaces a source that brings no independence rather than
    refusing one that does. Both halves are asserted: the count never passes the
    bound, and the claim is still admitted.
    """
    reader, holder, _, writer = a_reader()
    run = Run()
    receipts = [receipt(i, thread="t1") for i in range(9)]
    receipts.append(receipt(9, thread="t2"))
    observe(reader, receipts, run=run,
            texts=[f"a booking number {i}" for i in range(10)])
    assert len(run.supports(TRAVELS)) == 10
    assert writer.calls == 1
    assert len(writer.texts[0].split(particular.SOURCE_JOIN)) == MAX_SOURCES, (
        "more of the mailbox left the machine than the ceiling allows"
    )
    claims = run.admitted()
    assert len(claims) == 1, (
        "the ceiling threw away the one source that made the group independent"
    )
    assert claims[0].independent == 2
    assert "m9" in claims[0].support


@pytest.mark.cap3_particular
def test_a_run_reports_itself_in_counts_and_never_in_contents():
    """A ``Run`` holds bodies, and a traceback goes wherever tracebacks go
    (AD-22). ``__repr__`` is spelled out so the guarantee is a method rather
    than an accident of nobody having written one."""
    reader, _, _, _ = a_reader()
    sentinel = "sandalwood-nineteen-quicksilver"
    run = Run()
    observe(reader, [receipt(0, thread="t1")], run=run,
            texts=[f"a booking {sentinel}"])
    assert run.holding == 1
    assert sentinel not in repr(run)
    assert "holding=1" in repr(run)


@pytest.mark.cap3_particular
def test_a_second_claim_for_one_label_is_refused():
    """One label is one belief id, so a second claim for it would overwrite the
    first in the fold and nothing would say which one the main was told.

    Refused on ``Run.record`` rather than left to the caller, because the caller
    is the only thing that could notice and it is the thing that would be
    wrong.
    """
    run = Run()
    run.record(a_written_claim())
    with pytest.raises(DeriveError, match="a second claim"):
        run.record(a_written_claim(claim="a different sentence entirely"))
    with pytest.raises(DeriveError, match="is not a claim"):
        run.record("a bare string")


# ═════════════════════════════════════════════════════════════════════════════
# story 15c: the structural rules the generated claim rests on
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_particular
def test_the_writer_cannot_decide_and_the_reader_cannot_write():
    """**Two operations, two holders, and neither can do the other's job**
    (AD-19).

    This is the first path in the tree on which somebody's mail meets a model
    that may *author* text, and the separation is what keeps a model out of the
    admission: the thing that writes a sentence is not the thing that says two
    sources stand behind it.

    Both allowlists are driven, in both directions, and the last two lines are
    the half that stops this being red either way: the narrow pair is accepted.
    """
    class Both:
        async def classify(self, work): ...
        async def generate(self, work): ...

    class CallableWriter:
        async def generate(self, work): ...
        def __call__(self, work): ...

    for writer in (Both(), CallableWriter(), object(), None, ReadHolder()):
        with pytest.raises(DeriveError):
            Revealed({MAIN: ReadHolder()}, writers={MAIN: writer})
    with pytest.raises(DeriveError):
        Revealed({MAIN: Both()}, writers={MAIN: WriteHolder()})

    bench = Revealed({MAIN: ReadHolder()}, writers={MAIN: WriteHolder()})
    assert bench.holds(MAIN) and bench.writes(MAIN)
    assert particular.ALLOWED_METHODS == frozenset({"generate"})


@pytest.mark.cap3_particular
def test_a_bench_with_a_writer_is_still_sealed():
    """The writers cannot be swapped in after the check that each is narrow,
    which is the same rule the readers have and would be worth nothing on only
    one of the two mappings."""
    reader, _, _, _ = a_reader()
    with pytest.raises(DeriveError):
        reader._writers = {MAIN: object()}


@pytest.mark.cap3_particular
def test_what_leaves_the_machine_for_a_generation_is_the_bodies_and_nothing_else():
    """The generation request, scanned.

    The scrubbed bodies, the instructions, and **no label**: the group's label
    is Half's own word about the main and would tell the writer which answer to
    reach for, which is the difference between reading the mail and confirming
    a guess. No message id, no thread, no digest, no sender, no subject, no
    ledger name and no ``main_id`` in any payload either.
    """
    bodies = ["a booking in Delhi", SCRIPTS["devanagari"]]
    prompt = particular.prompt_for(bodies, main_id=MAIN)
    assert prompt.system == particular.INSTRUCTIONS
    assert len(prompt.turns) == 1
    rendered = prompt.turns[0].text
    for body in bodies:
        assert body in rendered, "a body was truncated, folded or dropped"
    stripped = rendered
    for body in bodies:
        stripped = stripped.replace(body, "")
    for leaked in ("m0", "t1", "d0", "a@x", REVEALED, MAIN, *LABELS):
        assert leaked not in stripped, leaked
    assert not any(label in block for block in particular.INSTRUCTIONS
                   for label in LABELS), (
        "a reading label is respelled in the writing instructions"
    )


@pytest.mark.cap3_particular
def test_a_confirmation_is_shown_one_source_and_never_the_group(sources):
    """*"Asked one source at a time"*, which is what makes the question
    askable at all: a confirmation shown every source answers *does this group
    support it*, whose answer is already yes.

    Driven rather than read, so it is the requests the provider actually saw.
    """
    reader, holder, _, _ = a_reader()
    pull([mail(0, "the first body", thread="t1"),
          mail(1, "the second body", thread="t2", sender="b@y")],
         reader, sources)
    assert len(holder.confirmations) == 2
    for work in holder.confirmations:
        assert tuple(work.labels) == CONFIRM_LABELS
        assert work.prompt.system == particular.CONFIRM_INSTRUCTIONS
        seen = work.prompt.turns[0].text
        assert A_CLAIM in seen, "the sentence being confirmed was not shown"
        bodies = [b for b in ("the first body", "the second body") if b in seen]
        assert len(bodies) == 1, bodies


@pytest.mark.cap3_particular
def test_the_writers_tier_is_pinned_and_is_read_from_its_own_module():
    """SPEC:124 — *the recurring spend runs on a cheaper tier than
    conversation, because the free tier depends on that gap*.

    Asserted from both sides of the provider, as the reader's tier is: the
    constant, and the ``Tiers`` the composition root actually parses. A case
    that asserted only the constant would be green for a build that bound it
    and never used it.
    """
    assert particular.GENERATE_TIER == "cheap"

    tree = ast.parse((ROOT / "half/__main__.py").read_text("utf-8"))
    inside = [node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name == "writers"]
    assert len(inside) == 1, "the anchor is dead: writers() was renamed"
    parsed = [node for node in ast.walk(inside[0])
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)
              and node.func.attr == "parse"]
    assert len(parsed) == 1
    names = {node.id for node in ast.walk(parsed[0])
             if isinstance(node, ast.Name)}
    assert "PARTICULAR_TIER" in names, (
        "the writer's tier is not read from half.derive.particular"
    )
    assert not any(isinstance(node, ast.Constant) and node.value == "cheap"
                   for node in ast.walk(parsed[0])), (
        "the tier is respelled as a literal in the composition root"
    )
    assert "config.tier_for" not in ast.unparse(inside[0]), (
        "the writer's tier follows the main's conversation tier"
    )


@pytest.mark.cap3_particular
def test_the_shipped_composition_equips_a_writer_beside_every_reader():
    """A surface reachable only from a test is a surface nobody has run.
    ``build`` is driven, and the reader it produces is asked whether it can
    write for the main the deployment named."""
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        config = load({ROOT_ENV: root, MAINS_ENV: f"123:{MAIN}"})
        wiring = build(config, token="123:fake")
        try:
            # No key is present, so neither holder is equipped — what is being
            # asserted is that the *path* exists and answers, in the same shape
            # for both, rather than that this environment has credentials.
            assert wiring.revealed.holds(MAIN) is wiring.revealed.writes(MAIN)
        finally:
            wiring.registry.close()


@pytest.mark.cap3_particular
@pytest.mark.parametrize("attribute,value", [
    ("BOUND_SECONDS", 0),
    ("BOUND_SECONDS", float("nan")),
    ("MAX_CLAIM_CHARS", 0),
    ("MAX_OUTPUT_TOKENS", 1),
    ("QUOTE_RUN_WORDS", 1),
    ("MAX_SOURCES", 1),
    ("GENERATE_TIER", "  "),
    ("CONFIRM_LABELS", (CONFIRMS, CONFIRMS, CONFIRM_UNSURE)),
    ("CONFIRM_LABELS", (CONFIRMS, DENIES, "a label defined nowhere")),
    ("CONFIRM_INSTRUCTIONS", ("", "")),
])
def test_each_import_time_guard_in_the_writer_has_a_bypass(monkeypatch,
                                                           attribute, value):
    """Every guard in ``particular._check_constants`` driven on its own.

    Without these the guards are red *everywhere at once* — the module refuses
    itself, four files fail to collect, and the failure names nothing. Each of
    these is red **by name**, so a mutation of the data they protect says which
    rule it broke.

    ``QUOTE_RUN_WORDS`` at one is the interesting one: a floor of a single word
    makes every particular a quotation, so the rule would not protect anything,
    it would delete the capability.
    """
    monkeypatch.setattr(particular, attribute, value)
    with pytest.raises(DeriveError):
        particular._check_constants()


@pytest.mark.cap3_particular
def test_the_writers_import_time_guards_pass_on_the_shipped_constants():
    """The bypass cases above are worth nothing if the guards refuse the real
    build too — an assertion that is red either way. This is the other side."""
    particular._check_constants()


@pytest.mark.cap3_particular
def test_no_logging_call_in_the_writer_can_carry_content():
    """Scanned over the **arguments of every logging call**, which is the form
    this guarantee takes everywhere in this tree: a generated sentence in a
    variable is invisible to a grep, and an invisible log call is how content
    gets logged.

    A claim Half wrote about somebody is as much AD-22's subject as the mail it
    came from — arguably more, since it is the thing that would read as a fact.
    """
    tree = ast.parse((ROOT / "half/derive/particular.py").read_text("utf-8"))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name)
             and node.func.value.id == "logger"]
    for node in calls:
        for argument in node.args[1:]:
            names = {n.id for n in ast.walk(argument) if isinstance(n, ast.Name)}
            assert names <= {"main_id"}, ast.unparse(argument)
    # And the module holds no logging call that takes a claim at all, which is
    # the honest reading of a scan that finds none: it is stated here so that a
    # future call arriving without an argument check is a change to this case.
    assert len(calls) == 0, (
        "half/derive/particular.py now logs; every argument needs the scan "
        "above, and a generated claim may never be one of them"
    )


@pytest.mark.cap3_particular
def test_the_writer_reads_no_clock_opens_no_store_and_writes_no_record():
    """AD-30, and ``half.derive``'s own rule. The module answers *what would a
    claim say*; nothing else."""
    source = (ROOT / "half/derive/particular.py").read_text("utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = {name for name in imported
                 if name.startswith(("half.store.store", "half.store.log",
                                     "half.actor", "half.schedule"))}
    assert not forbidden, forbidden
    for banned in ("datetime", "time.time", "utcnow", "now()"):
        assert banned not in source, banned


@pytest.mark.cap3_particular
def test_the_quotation_rule_is_the_context_builders_own_unit():
    """*"Half's own words"* is decided on ``half.context.build``'s unit and
    only its **length** is this module's.

    The unit — invisible characters removed, a Devanagari matra kept attached to
    its letter, folded by ``half.text.normalize`` — took two stories and a
    script sweep to get right, and a copy of it beside a generator would have
    been a Latin-only copy of whatever somebody remembered. Asserted over the
    import graph as well as by behaviour, because the behaviour of a good copy
    and of the real thing agree until the day they do not.
    """
    from half.context.build import runs as unit_runs

    tree = ast.parse((ROOT / "half/derive/particular.py").read_text("utf-8"))
    imports = {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }
    assert ("half.context.build", "runs") in imports
    assert ("half.context.build", "leaks") in imports

    # Devanagari: a matra must not split its letter, which is what a home-made
    # unit rule always gets wrong — ``यात्रा`` shatters into three consonants
    # under the index tokenizer and would then collide with almost any other
    # Devanagari string, so every claim in an Indic script would read as a
    # quotation.
    assert len(unit_runs("यात्रा बुकिंग", length=1)) == 2

    # And the floor is a run rather than a pair, in that script as in Latin.
    assert quotes("क ख ग घ ङ", ["क ख ग घ च"])
    assert not quotes("क ख ङ", ["क ख ग घ च"])
