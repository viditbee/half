"""CAP-3 story 15b: what a source is worth keeping.

Ingestion captured receipts and derived nothing, so the revealed ledger was
empty and story 3's union-find — built precisely to make CAP-3's central
sentence true — had never once decided anything outside its own unit tests.
This file is one case per row of the story's matrix, plus the structural rules
the story rests on.

Four things it refuses to do, because each would let it pass while the product
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
"""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path

import pytest

from half.__main__ import build, ingest_mail
from half.config import MAINS_ENV, ROOT_ENV, load
from half.derive import revealed as reading
from half.derive.claim import Derivers
from half.derive.gates import GATES, Gate
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
from half.ingest.scrub import Scrubbed, scrub
from half.model.port import Decision, Failure, Kind, Reason, Usage
from half.retrieval.prefix import build_prefix
from half.store.records import CLAIM, DERIVATION, DERIVED, LEDGER, SUBJECT
from half.store.sources import LocalSourceStore
from half.store.store import Store

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"

#: The label every double answers with unless a case says otherwise.
TRAVELS = DOINGS[0].label
BUYS = DOINGS[2].label

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


class ReadHolder:
    """The narrow classifier that answers *what does this show they do*.

    ``answers`` is consumed in order and the last one repeats, so a case can say
    *"the first body travels, everything after it buys"* without knowing how
    many bodies there are.
    """

    def __init__(self, answers: object = TRAVELS, *, sleep: float = 0.0) -> None:
        self._answers = list(answers) if isinstance(answers, list) else [answers]
        self._sleep = sleep
        self.seen: list = []

    async def classify(self, work):
        self.seen.append(work)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        answer = self._answers[min(len(self.seen) - 1, len(self._answers) - 1)]
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


def a_reader(answers=TRAVELS, *, gates=None, main=MAIN, sleep=0.0,
             bound_seconds=1.0, tally=None):
    """A ``Revealed``, the reading holder inside it, and the gate holder."""
    gate_holder = GateHolder(gates)
    read_holder = ReadHolder(answers, sleep=sleep)
    reader = Revealed(
        {main: read_holder},
        gates=Derivers({main: gate_holder}, bound_seconds=1.0),
        bound_seconds=bound_seconds, tally=tally,
    )
    return reader, read_holder, gate_holder


def receipt(index: int, *, thread="t1", digest=None, text="body") -> Receipt:
    return Receipt(
        digest=digest if digest is not None else f"d{index}",
        external_id=f"m{index}", thread_id=thread, sender="a@x",
        subject="s", t=f"2026-08-{index + 1:02d}T00:00:00Z",
    )


def observe(reader, receipts, *, run=None, main=MAIN, text="a booking"):
    """Read every receipt through one reader, into one run."""
    run = run if run is not None else Run()

    async def drive():
        for rec in receipts:
            await reader.observe(rec, scrub(text), main_id=main, into=run)

    asyncio.run(drive())
    return run


def candidates(*specs, label=TRAVELS) -> Run:
    """A run holding one candidate per ``(id, thread, digest)`` spec."""
    run = Run()
    for source_id, thread_id, digest in specs:
        run.add(Candidate(label=label, source_id=source_id,
                          thread_id=thread_id, digest=digest))
    return run


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
    run = candidates(("m0", "t1", "d0"), ("m1", "t2", "d1"))
    claims = run.admitted()
    assert len(claims) == 1
    assert claims[0].independent == 2
    assert claims[0].support == ("m0", "m1")
    assert claims[0].claim == DOINGS[0].claim


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
    assert run.admitted() == ()


@pytest.mark.cap3
def test_a_byte_identical_forward_never_reaches_the_reader(sources):
    """The other half of row three, through the real pipeline. A body the store
    already holds is skipped before the consumer is called, so a forward with
    identical bytes is not a second support — it is not a reading at all, and
    costs nothing."""
    reader, holder, _ = a_reader()
    body = "Your booking is confirmed. Departure 14 March."
    run = pull([mail(0, body, thread="t1", sender="a@x"),
                mail(1, body, thread="t2", sender="b@y")], reader, sources)
    assert holder.calls == 1, "the identical body was read twice"
    assert len(run.supports(TRAVELS)) == 1
    assert run.admitted() == ()


@pytest.mark.cap3
def test_one_message_admits_nothing():
    """Matrix row four. Never from one cluster, and one message is the smallest
    cluster there is."""
    run = candidates(("m0", "t1", "d0"))
    assert len(run.supports(TRAVELS)) == 1
    assert run.admitted() == ()


@pytest.mark.cap3
def test_two_independent_bodies_the_gates_refuse_admit_nothing():
    """Matrix row five. Two independent sources, and the content fails a gate —
    so nothing is read about what they show and no candidate exists.

    Asserts the gate's **name**, not merely the absence of a claim: *"no claim"*
    is also true of a provider that was down, and this case is about the gates
    working.
    """
    reader, holder, _ = a_reader(gates={"durability": "only_now"})
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
    reader, _, _ = a_reader()
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
    reader, holder, gate_holder = a_reader()
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
    reader, holder, _ = a_reader()
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
    reader, holder, _ = a_reader()
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
    reader, holder, _ = a_reader()
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
    reader, _, _ = a_reader(sleep=0.05, bound_seconds=0.01)
    run = pull([mail(0, "booking one", thread="t1"),
                mail(1, "booking two", thread="t2", sender="b@y")],
               reader, sources)
    assert len(sources) == 2, "the receipts did not survive"
    assert run.admitted() == ()
    assert reader.tally.bound_exceeded == 2


@pytest.mark.cap3
def test_a_reader_that_raises_yields_no_claim_and_the_pull_completes(sources):
    """Matrix row twelve, the raising half. Counted under ``raised``."""
    reader, _, _ = a_reader(answers=RuntimeError("provider blew up"))
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
    reader, holder, _ = a_reader()
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
    """Matrix row fourteen, CAP-5. ``support`` names them and ``independent``
    carries the count, and each source appears exactly once."""
    run = candidates(("m2", "t1", "d0"), ("m0", "t2", "d1"), ("m1", "t3", "d2"))
    claim = run.admitted()[0]
    assert claim.support == ("m0", "m1", "m2")
    assert len(set(claim.support)) == len(claim.support)
    assert claim.independent == 3


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
    run = candidates(("m0", "t1", "d0"), ("m1", "t1", "d1"),
                     ("m2", "t2", "d2"))
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
    reader, holder, _ = a_reader()
    body = SCRIPTS[script]
    run = pull([mail(0, body, thread="t1"),
                mail(1, body + "​", thread="t2", sender="b@y")],
               reader, sources)
    claims = run.admitted()
    assert len(claims) == 1 and claims[0].independent == 2
    # The claim is Half's own word from the closed set, so it is the same in
    # every script — which is the one place a closed vocabulary is *better*
    # worldwide than the source's own words.
    assert claims[0].claim == DOINGS[0].claim
    assert holder.seen[0].prompt.system == INSTRUCTIONS


@pytest.mark.cap3
def test_no_body_and_no_claim_text_reaches_any_log_line(sources, caplog):
    """Matrix row seventeen, AD-22. The sentinel goes to a provider and to
    nowhere else — not a log line, not the tally, not a counter."""
    sentinel = "sandalwood-nineteen-quicksilver"
    reader, holder, _ = a_reader()
    with caplog.at_level(logging.DEBUG):
        run = pull([mail(0, f"booking {sentinel}", thread="t1"),
                    mail(1, f"itinerary {sentinel}", thread="t2",
                         sender="b@y")], reader, sources)
        claims = run.admitted()
        reader.count_claims(claims)
        reader.flush()
    assert len(claims) == 1
    assert all(sentinel in text for text in holder.texts)
    assert sentinel not in caplog.text
    assert sentinel not in repr(reader.tally)


@pytest.mark.cap3
def test_a_log_of_receipts_and_revealed_claims_folds_identically(tmp_path):
    """Matrix row eighteen, AD-4 and AD-30. Derivation is not in the fold: what
    is in the log is a claim, and replaying it reproduces the same state."""
    claim = candidates(("m0", "t1", "d0"), ("m1", "t2", "d1")).admitted()[0]
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
    claim = candidates(("m0", "t1", "d0"), ("m1", "t2", "d1")).admitted()[0]
    fields = {**fields_of(claim),
              **ladder.admitted(support=list(claim.support))}
    assert fields["license"] == str(ladder.FLOOR)
    assert fields[CLAIM] == DOINGS[0].claim
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
        reader, _, _ = a_reader()
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
        reader, _, _ = a_reader()
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
        reader, _, _ = a_reader()
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
    reader, holder, gate_holder = a_reader()

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
    reader, holder, gate_holder = a_reader()
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
])
def test_a_claim_that_could_not_be_true_cannot_be_constructed(fields, names):
    """*"A claim whose support set is empty or whose count is one is a defect,
    not a state."*

    Refused on the type, because the log is append-only and every one of these
    is permanent once written. Five shapes, because each is a different mistake.

    **Each asserts the refusal's own message, not merely that something
    raised**, and that is the correction a mutation probe forced. The
    support-size check is redundant — a count below the floor and a count above
    the support size together already forbid every support set smaller than two
    — so disabling it left every case here green: four guards, and three of them
    covering the fourth, which is a guard that cannot fire because a rule below
    it already forbids its case. Reading the message is what tells them apart,
    and it is worth telling them apart because a refusal has to name the right
    thing.
    """
    with pytest.raises(DeriveError, match=names):
        Claim(label=TRAVELS, claim="travels", subject="travel", **fields)


@pytest.mark.cap3_structure
@pytest.mark.parametrize("attribute,value,because", [
    ("MIN_INDEPENDENT", 1, "a threshold of one deletes CAP-3's sentence"),
    ("PER_RUN", 0, "a cap of zero derives nothing, for ever"),
    ("BOUND_SECONDS", 0, "a bound that never fires is not a bound"),
    ("ALARM_RATE", 0.0, "an alarm that never fires names nothing"),
    ("CLASSIFY_TIER", "  ", "a blank tier is refused at boot"),
    ("DOINGS", (), "an empty vocabulary derives nothing"),
    ("DOINGS", (Doing(label="a", claim="x", subject="p"),
                Doing(label="a", claim="y", subject="q")),
     "two members answer to one label"),
    ("DOINGS", (Doing(label="a", claim="x", subject="p"),
                Doing(label="b", claim="x", subject="q")),
     "two labels write one claim"),
    ("DOINGS", (Doing(label="a", claim="x", subject="p"),
                Doing(label="b", claim="y", subject="p")),
     "two claims share a subject"),
    ("NOTHING_DOING", "travels", "the refusal label is also a claim"),
    ("DOING_UNSURE", "travels", "the unsure label is also a claim"),
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
    reader, _, _ = a_reader()
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
               "self", "exc", "type", "verdict"}
    counts = set(Tally.__dataclass_fields__) | {
        "fell_back", "answered", "failure_rate", "_tally",
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
    unsure, _, _ = a_reader(answers=DOING_UNSURE)
    observe(unsure, [receipt(0)])
    assert unsure.tally.answers == {DOING_UNSURE: 1}
    assert unsure.tally.fell_back == 0

    down, _, _ = a_reader(
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
    assert run.admitted()[0].support == ("m0", "m1")


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
