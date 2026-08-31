"""Strand weighting, the live-turn wiring, and the boundary no belief crosses.

Four properties, all of which the spec calls disqualifying if they fail:

**A topic switch reorders and never empties.** Half must never be able to say
*"I don't have access to that"* (AD-24), and the way that sentence gets built is
a scope filter that seemed reasonable at the time.

**Retrieval actually runs on the live turn.** Asserted by watching the ranking
happen, not by grepping the source for `Retriever(`. The grep version could not
tell a wired pipeline from an unwired one, because the substrings it looked for
live inside the very function whose call site had been deleted.

**One main's crisis is one main's crisis.** The switch is per actor. A single
switch per worker made a crisis for one person a silent, total memory outage for
every other person that process was serving.

**No `behave` claim text reaches an outbound message.** No longer the global
invariant story 4 wrote — `assert` text may now be quoted — but the same
assertion over the same seeded store, which carries no license field and so
resolves to `behave` at every rung. The licensed version, including the rung
whose text *may* be said, lives in ``tests/test_context.py``.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime, respond
from half.channel.telegram import TelegramChannel
from half.crisis.gate import CrisisGate
from half.errors import RetrievalDisabled, StoreError
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import Retriever
from half.retrieval.strands import (
    STRAND_FLOOR,
    Strands,
    known_strands,
    strand_weight,
    strands_of,
)
from half.store.ops import Op
from half.store.store import Store
from tests.conftest import FakeTransport, msg

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-31T09:00:00Z"

#: Claims distinctive enough that any leak into a reply is unmistakable. The
#: identifiers are chosen so the score tie-break would order them b_afly,
#: b_mmother, b_zfarm — the opposite of what strand weight should produce.
CLAIMS = {
    "b_zfarm": "has been reading about smallholdings in the western ghats",
    "b_afly": "has not flown a paraglider in three years",
    "b_mmother": "replies to his mother within three minutes",
}
LOOPS = {"b_zfarm": "buy-farmland", "b_afly": "fly-again", "b_mmother": "call-mother"}


def seed(store):
    """Three beliefs identical in every ranking input except their strand."""
    for ident, claim in CLAIMS.items():
        store.record(Op.ASSERT, ident, "2026-06-01T00:00:00Z", subject="self",
                     claim=claim, ledger="revealed", loop=LOOPS[ident],
                     independent=2)
    return store


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "main", prefix=build_prefix) as s:
        yield seed(s)


def live(store, text):
    state = store.state()
    strands = Strands()
    strands.observe(text, known_strands(state.beliefs.values(), state.loops))
    return strands


def inbound(text: str, **kw):
    from half.channel.port import Inbound

    return Inbound(main_id=kw.get("main_id", "vidit"), address="123", text=text,
                   external_id=kw.get("external_id", "1"), t=NOW)


class Recording:
    """A reranker that changes nothing and remembers what it was shown.

    The only way to prove the live turn ranked anything: it sees the candidate
    set from inside the pipeline, so deleting the call site empties it.
    """

    def __init__(self) -> None:
        self.seen: list[tuple[str, ...]] = []

    def rerank(self, query, candidates):
        self.seen.append(tuple(c.id for c in candidates))
        return candidates

    @property
    def every_id(self) -> set[str]:
        return {ident for batch in self.seen for ident in batch}


# -- reordering, never filtering ---------------------------------------------

@pytest.mark.ad24
def test_strand_weight_never_reaches_zero():
    """The whole never-excludes guarantee is this floor. If it can return 0,
    a topic switch can empty the candidate set."""
    assert STRAND_FLOOR > 0.0
    assert strand_weight(frozenset(), None) == STRAND_FLOOR
    assert strand_weight(frozenset(), Strands()) == STRAND_FLOOR
    elsewhere = Strands({"loop:something-else": 1.0})
    assert strand_weight({"loop:nobody-mentioned-this"}, elsewhere) == STRAND_FLOOR


@pytest.mark.ad24
@pytest.mark.parametrize(
    "attention, expected",
    [("farmland", "b_zfarm"), ("mother", "b_mmother")],
)
def test_strand_weight_alone_decides_the_order(store, attention, expected):
    """Every other ranking input is identical across the three beliefs, and the
    tie-break would put ``b_afly`` first in both cases — so replacing the strand
    multiplier with 1.0 must fail here."""
    # A query whose words appear in no claim and no prefix, so bm25 is uniform.
    result = Retriever(store=store).retrieve(
        "xyzzy plugh", now=NOW, strands=live(store, attention)
    )
    assert set(result.ids) == set(CLAIMS)
    assert result.ids[0] == expected


@pytest.mark.ad24
def test_a_topic_switch_moves_the_order_rather_than_the_membership(store):
    retriever = Retriever(store=store)
    on_farmland = retriever.retrieve("xyzzy plugh", now=NOW,
                                     strands=live(store, "farmland"))
    on_mother = retriever.retrieve("xyzzy plugh", now=NOW,
                                   strands=live(store, "mother"))

    assert set(on_farmland.ids) == set(on_mother.ids) == set(CLAIMS)
    assert on_farmland.ids != on_mother.ids, "the switch must move the order"


@pytest.mark.ad24
def test_a_strand_with_no_live_weight_never_empties_the_set(store):
    """The matrix's topic-switch row: a query on a strand nothing has weighted."""
    result = Retriever(store=store).retrieve(
        "quantum horticulture", now=NOW, strands=live(store, "quantum horticulture")
    )
    assert set(result.ids) == set(CLAIMS)


@pytest.mark.ad24
def test_no_weighting_can_shrink_the_candidate_set(store):
    """Property-style: whatever the weights, the set is invariant."""
    retriever = Retriever(store=store)
    baseline = set(retriever.retrieve("xyzzy plugh", now=NOW).ids)
    for text in ("farmland", "mother", "paraglider", "", "self", "nothing relevant"):
        result = retriever.retrieve("xyzzy plugh", now=NOW,
                                    strands=live(store, text))
        assert set(result.ids) == baseline, f"{text!r} removed a belief"


def test_attention_decays_so_a_switch_takes_effect(store):
    strands = Strands()
    state = store.state()
    known = known_strands(state.beliefs.values(), state.loops)
    strands.observe("farmland", known)
    first = strands.weights["loop:buy-farmland"]
    strands.observe("fly again", known)
    assert strands.weights["loop:fly-again"] > strands.weights["loop:buy-farmland"]
    assert strands.weights["loop:buy-farmland"] < first


def test_strands_are_matched_on_exact_tokens_not_on_nearest_neighbour():
    """HippoRAG's ``difflib.get_close_matches(..., cutoff=0.0)`` always returns
    something. A strand sharing no token with the message must score nothing."""
    strands = Strands()
    strands.observe("paragliding", {"loop:buy-farmland", "person:asha"})
    assert strands.weights == {}


def test_strands_are_read_off_the_belief_the_log_wrote(store):
    assert strands_of(store.state().beliefs["b_zfarm"]) == {
        "loop:buy-farmland", "subject:self",
    }
    assert strands_of({}) == frozenset()


def test_known_strands_include_loops_no_belief_references_yet(store):
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-02T00:00:00Z",
                 loop="learn-tabla", state="advancing", timescale="months")
    state = store.state()
    assert "loop:learn-tabla" in known_strands(state.beliefs.values(), state.loops)


def test_a_strand_named_in_a_non_latin_script_can_become_live():
    """``[a-z0-9]+`` found no tokens on either side, so a person or loop named
    in Devanagari could never be weighted at all, in any of the scripts most of
    the world writes in."""
    strands = Strands()
    strands.observe("आशा से बात हुई", {"person:आशा", "loop:buy-farmland"})
    assert strands.weights.get("person:आशा", 0.0) > 0.0
    assert "loop:buy-farmland" not in strands.weights


def test_strand_matching_folds_case_and_accents():
    strands = Strands()
    strands.observe("thinking about the Café plans", {"loop:cafe-plans"})
    assert strands.weights.get("loop:cafe-plans", 0.0) > 0.0


# -- the live turn actually retrieves ---------------------------------------

def run_turns(root, texts, *, reranker=None, mains=None, registry=None):
    """Drive Runtime.run over ``texts`` and return the transport."""
    mains = mains or {"123": "vidit"}
    transport = FakeTransport([
        msg(text=text, message_id=str(i + 1), chat_id=chat)
        for i, (chat, text) in enumerate(texts)
    ])
    channel = TelegramChannel(transport=transport, mains=mains)
    reg = registry or ActorRegistry(root)
    asyncio.run(Runtime(channel=channel, registry=reg, reranker=reranker).run())
    return transport, reg


def test_retrieval_actually_runs_on_the_live_turn(tmp_path):
    """Replacing the call in _pipeline with ``return respond(inbound)`` must
    fail here. The source-grep version it replaced could not tell the
    difference, because ``Retriever(`` and ``.retrieve(`` both appear inside
    ``_retrieve`` itself and survive deleting every call to it."""
    root = tmp_path / "mains"
    with Store(root / "vidit", prefix=build_prefix) as s:
        seed(s)

    recorder = Recording()
    transport, reg = run_turns(root, [("123", "thinking about the farmland")],
                               reranker=recorder)
    reg.close()

    assert transport.sent, "the turn produced no reply at all"
    assert recorder.seen, "the live turn never ranked anything"
    # The query's words match b_zfarm through its indexed loop prefix, and only
    # that one — reachable means findable by a matching query, not present in
    # every candidate set.
    assert recorder.every_id == {"b_zfarm"}


def test_strand_attention_survives_from_one_turn_to_the_next(tmp_path):
    """Per-actor strands, not a fresh Strands() per turn — which passes every
    single-turn assertion while making attention meaningless."""
    root = tmp_path / "mains"
    with Store(root / "vidit", prefix=build_prefix) as s:
        seed(s)

    reg = ActorRegistry(root)
    run_turns(root, [("123", "farmland"), ("123", "xyzzy plugh")], registry=reg)

    async def read():
        async with reg.acquire("vidit") as actor:
            return dict(actor.strands.weights)

    weights = asyncio.run(read())
    reg.close()
    assert weights.get("loop:buy-farmland", 0.0) > 0.0, (
        "turn 1's topic was forgotten by turn 2"
    )


# -- the switch is per main, and the turn survives it ------------------------

def test_the_default_gate_disables_the_registrys_switch_for_that_main(
    tmp_path, monkeypatch
):
    """The runtime must hand its default gate the registry's per-main resolver.

    Giving the gate a private switch instead passes every test that builds its
    own gate, because those prove the gate honours a switch it is *given*, not
    that the runtime gives it the right one.
    """
    monkeypatch.setattr(CrisisGate, "_is_crisis", lambda self, inb: True)
    root = tmp_path / "mains"
    reg = ActorRegistry(root)
    assert reg.retrieval_switch("vidit").enabled

    # _respond_to_crisis is story 6 and raises; run()'s per-message isolation
    # absorbs that, but the disable happened before it.
    run_turns(root, [("123", "safe word")], registry=reg)
    assert not reg.retrieval_switch("vidit").enabled
    reg.close()


def test_one_mains_crisis_does_not_disable_another_mains_retrieval(tmp_path):
    """Reproduced against a single shared switch: main B lost its whole memory
    because main A was in crisis, silently and with no way back."""
    root = tmp_path / "mains"
    for main_id, prefix_id in (("vidit", "b_v"), ("asha", "b_a")):
        with Store(root / main_id, prefix=build_prefix) as s:
            s.record(Op.ASSERT, f"{prefix_id}_1", "2026-06-01T00:00:00Z",
                     subject="self", claim="keeps a garden", ledger="revealed")

    reg = ActorRegistry(root)
    reg.retrieval_switch("vidit").disable()  # as the crisis gate would

    recorder = Recording()
    transport, _ = run_turns(
        root, [("123", "how is the garden"), ("456", "how is the garden")],
        reranker=recorder, mains={"123": "vidit", "456": "asha"}, registry=reg,
    )
    reg.close()

    assert len(transport.sent) == 2, "both mains must be answered"
    assert recorder.every_id == {"b_a_1"}, (
        "asha's retrieval must be untouched, and vidit's must be off"
    )


def test_a_turn_after_a_disable_still_replies_and_keeps_the_message(tmp_path):
    """A disable degrades what Half knows, never whether Half replies."""
    root = tmp_path / "mains"
    with Store(root / "vidit", prefix=build_prefix) as s:
        seed(s)

    reg = ActorRegistry(root)
    reg.retrieval_switch("vidit").disable()
    transport, _ = run_turns(root, [("123", "still here?")], registry=reg)

    assert transport.sent, "a disabled ledger must not cost the main a reply"

    async def read():
        async with reg.acquire("vidit") as actor:
            return set(actor.store.state().beliefs)

    stored = asyncio.run(read())
    reg.close()
    assert "b_1" in stored, "the main's message was dropped"


def test_the_raise_itself_is_kept_so_a_disable_is_never_an_empty_ledger(tmp_path):
    """The pipeline catches it; the retriever still raises. A disable that
    returned an empty set would be indistinguishable from a main with nothing."""
    from half.retrieval.rank import RetrievalSwitch

    off = RetrievalSwitch()
    off.disable()
    with Store(tmp_path / "main", prefix=build_prefix) as s:
        seed(s)
        with pytest.raises(RetrievalDisabled):
            Retriever(store=s, switch=off).retrieve("anything", now=NOW)


def test_a_failing_turn_never_swallows_the_mains_message(tmp_path, monkeypatch):
    """The belief is recorded last. Recording it first meant a turn that failed
    afterwards left the message durable, unanswered, and permanently
    unredeliverable — the idempotency check turned every retry into a no-op."""
    root = tmp_path / "mains"
    with Store(root / "vidit", prefix=build_prefix) as s:
        seed(s)

    def boom(*args, **kwargs):
        raise StoreError("the index is unavailable")

    monkeypatch.setattr(Retriever, "retrieve", boom)
    reg = ActorRegistry(root)
    failed, _ = run_turns(root, [("123", "please remember this")], registry=reg)
    assert failed.sent == [], "the turn should have failed"

    async def read():
        async with reg.acquire("vidit") as actor:
            return set(actor.store.state().beliefs)

    assert "b_1" not in asyncio.run(read()), (
        "a failed turn recorded the message, so the redelivery will be ignored"
    )

    monkeypatch.undo()
    retried, _ = run_turns(root, [("123", "please remember this")], registry=reg)
    reg.close()
    assert retried.sent, "the redelivery must be answered"


# -- no behave belief text may leave -----------------------------------------

@pytest.mark.ad18
def test_a_turn_that_retrieved_behave_beliefs_says_none_of_them(tmp_path):
    """Byte-wise on the wire, over a store seeded with distinctive claims.

    ``seed`` writes no license field, so every one of these resolves to
    `behave` — which is the rung under test, not an accident of the fixture."""
    root = tmp_path / "mains"
    with Store(root / "vidit", prefix=build_prefix) as s:
        seed(s)

    # A message whose words match no claim and no prefix, so the backstop puts
    # all three distinctive claims in front of the responder.
    recorder = Recording()
    transport, reg = run_turns(root, [("123", "xyzzy plugh")], reranker=recorder)
    reg.close()

    assert recorder.every_id >= set(CLAIMS), "the turn had beliefs to retrieve"
    assert transport.sent, "the turn must actually have produced a reply"
    sent = "".join(text for _, text in transport.sent).encode("utf-8")
    for claim in CLAIMS.values():
        assert claim.encode("utf-8") not in sent
        for word in claim.split():
            if len(word) > 6:  # a distinctive fragment, not "the" or "about"
                assert word.encode("utf-8") not in sent, word


@pytest.mark.ad18
def test_the_responder_is_given_a_behave_belief_and_quotes_none_of_it():
    ranked = _ranked_with(CLAIMS["b_afly"])
    reply = respond(inbound("hello"), ranked, ceiling=None)
    assert reply is not None
    for word in CLAIMS["b_afly"].split():
        if len(word) > 6:
            assert word not in reply


@pytest.mark.ad18
def test_the_runtime_never_reads_claim_text_off_a_candidate():
    """A behavioural test can only cover the claims it happened to seed. This
    covers every one: the reply path has no access to a candidate's text.

    Kept unchanged now that the reply *may* quote content, and it is a stronger
    statement for it. The runtime reaches belief text only through
    ``half.context``, so there is no route from a candidate to an outbound
    message that skips the license split (AD-18)."""
    tree = ast.parse((ROOT / "half/actor/runtime.py").read_text(encoding="utf-8"))
    reads = [
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"claim", "prefix", "belief"}
    ]
    assert not reads, f"runtime reads belief text off a candidate: {reads}"


def _ranked_with(claim: str):
    """One `behave` belief, licensed explicitly.

    The license was previously left off, so the candidate carried an empty
    belief record and the test passed on the *default* rung rather than on the
    rule. Stating it means the assertion still means something if the default
    ever changes — and if it changes, this is one of the tests that should
    fail."""
    from half.retrieval.port import Candidate, Ranked, RerankSource

    return Ranked(
        beliefs=(
            Candidate(id="b_afly", claim=claim, prefix="", bm25=-1.0,
                      belief={"claim": claim, "license": "behave"}),
        ),
        rerank=RerankSource.ABSENT,
    )
