"""Story 9b — the model port (AD-19, AD-20, AD-22, AD-30, CAP-7).

One case per row of the story's I/O matrix, plus the structural assertions the
matrix marks *asserted, not documented* — the ones a behavioural test cannot
reach, because a port that grew a ``generate`` on its classifier, a model name
in a call site, or a completion in a log line would keep every other case in
this file green.

The suite is hermetic by construction rather than by discipline: the transport
is injected, every case here hands the provider a ``FakeTransport``, and
``tests/test_model_offline.py`` asserts at the socket that the whole suite —
this file included — reaches nothing.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import typing
from pathlib import Path

import pytest

from half.errors import (
    BreakpointError,
    BudgetError,
    ModelBatchNotFound,
    ModelError,
    ModelMisconfigured,
    ModelNotAuthorised,
    ModelRefused,
    ModelRequestInvalid,
    ModelUnavailable,
    TransportFault,
    UnknownTier,
)
from half.model import budget as budget_mod
from half.model.anthropic import (
    CLASSIFY_EFFORT,
    CLASSIFY_MAX_TOKENS,
    AnthropicBatcher,
    AnthropicClassifier,
    AnthropicGenerator,
    AnthropicProvider,
    classify_ceiling,
    render_classify,
    render_generate,
    render_prompt,
)
from half.model.anthropic_transport import MODEL_KEY, SDKTransport, _translate
from half.model.budget import (
    Budget,
    Estimate,
    Ledger,
    Reservation,
    Spend,
    charged,
    estimate,
    tokens_in,
)
from half.model.port import (
    BatchItem,
    Batcher,
    Breakpoint,
    CacheTTL,
    Classifier,
    Classify,
    Collected,
    Completion,
    Decision,
    Failure,
    Generate,
    Generator,
    Kind,
    ModelProvider,
    Prompt,
    Reason,
    Role,
    Submission,
    Submitted,
    Transport,
    Turn,
    Usage,
)
from half.governance import ladder
from half.store.ops import Op
from half.model.tier import (
    CACHE_WRITE_BASIS_1H,
    CACHE_WRITE_BASIS_5M,
    DEFAULT_MODELS,
    ModelSpec,
    Tier,
    Tiers,
)

pytestmark = pytest.mark.ad19

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "half" / "model"

#: Two mains on two different tiers, which is the shape AD-20 exists for.
VIDIT = "vidit"
ASHA = "asha"

#: A key that is the right *shape* and is built at runtime rather than written
#: down, so that this file does not itself trip the AD-11 secret gate that
#: scans every tracked file in the tree.
FAKE_KEY = "sk-" + "ant-" + "A" * 40


# ── the fake transport: the whole network surface, four methods ──────────────


class FakeTransport:
    """Everything the implementation needs from a network, and no network.

    The same shape ``tests/conftest.py`` uses for Telegram, for the same
    reason: the seam is what keeps the suite offline, and a fake that is four
    methods long is the evidence that the port stayed narrow.
    """

    def __init__(
        self,
        *,
        reply=None,
        replies=None,
        raises=None,
        batch=None,
        status=None,
        results=(),
    ):
        self.reply = reply
        self.replies = list(replies) if replies is not None else None
        self.raises = raises
        self.batch = batch if batch is not None else {"id": "msgbatch_01"}
        self.status = status if status is not None else {"processing_status": "ended"}
        self.results = list(results)
        self.sent: list[dict] = []
        self.submitted: list[list[dict]] = []
        self.asked: list[str] = []

    async def message(self, payload):
        self.sent.append(dict(payload))
        if self.raises is not None:
            raise self.raises
        if self.replies is not None:
            return self.replies.pop(0)
        return self.reply if self.reply is not None else text_reply("ok")

    async def batch_create(self, requests):
        self.submitted.append([dict(r) for r in requests])
        if self.raises is not None:
            raise self.raises
        return self.batch

    async def batch_status(self, batch_id):
        self.asked.append(batch_id)
        if self.raises is not None:
            raise self.raises
        return self.status

    async def batch_results(self, batch_id):
        for entry in self.results:
            yield entry


def text_reply(text, *, usage=None, stop="end_turn"):
    """A minimal Messages reply, in the shape the provider returns one."""
    return {
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5},
    }


def label_reply(label, **kw):
    return text_reply(json.dumps({"label": label}), **kw)


LABELS = ("crisis", "ordinary")


def tiers():
    return Tiers.parse({VIDIT: "cheap", ASHA: "frontier"})


def budget(*, per_call=10_000_000, per_pass=100_000_000):
    return Budget(per_call_micro_usd=per_call, per_pass_micro_usd=per_pass)


def provider(transport, *, tiers_=None, per_call=10_000_000, per_pass=100_000_000):
    return AnthropicProvider(
        transport,
        tiers=tiers_ or tiers(),
        budget=budget(per_call=per_call, per_pass=per_pass),
    )


def long_block(spec=None, *, times=2):
    """A system block comfortably over a tier's own cache minimum.

    Needed because the port now refuses a breakpoint the provider would ignore:
    under ``cache_min_tokens`` the marker caches nothing, silently, and placing
    it anyway is the hidden breakpoint AD-19 forbids. Sized from the spec so a
    minimum that moves does not turn these into vacuous cases.
    """
    spec = spec or DEFAULT_MODELS[Tier.FRONTIER]
    return "cacheable prose. " * (spec.cache_min_tokens * times)


def prompt(main_id=VIDIT, *, system=("stable",), turns=("hello",), cache=None):
    return Prompt(
        main_id=main_id,
        system=tuple(system),
        turns=tuple(Turn(Role.USER, t) for t in turns),
        cache=cache,
    )


def classify(**kw):
    return Classify(prompt=prompt(**kw), labels=LABELS)


def generate(**kw):
    return Generate(prompt=prompt(**kw))


# ── matrix: classify ─────────────────────────────────────────────────────────


def test_a_classification_returns_a_decision():
    """Matrix: *classify*."""
    out = asyncio.run(provider(FakeTransport(reply=label_reply("crisis"))).classify(
        classify()
    ))
    assert isinstance(out, Decision)
    assert out.label == "crisis"


@pytest.mark.ad19_guarantee
def test_a_decision_carries_no_free_text_in_any_field():
    """Matrix: *classify*, the half that is a property of the type.

    Not "the parser strips it" — there is no field on ``Decision`` or on
    ``Failure`` that a completion could travel in. A label is drawn from the
    request's own closed set and everything else is a count or an enum, which
    is what makes *"no prose in any field"* checkable rather than reviewable.
    """
    out = asyncio.run(provider(FakeTransport(reply=label_reply("crisis"))).classify(
        classify()
    ))
    assert isinstance(out, Decision)
    assert out.label in LABELS
    assert set(Decision.__dataclass_fields__) == {"label", "usage"}
    assert all(
        isinstance(getattr(out.usage, f), int) for f in Usage.__dataclass_fields__
    )


@pytest.mark.ad19_guarantee
def test_prose_is_never_coerced_into_a_decision():
    """Matrix: *malformed reply*. Never coerced.

    The tempting implementation matches the nearest label, or the one the
    sentence contains. Both are a classifier that guesses — and the path this
    port was shaped for is the one where a guess is a main in crisis read by
    something that decided they were fine.
    """
    out = asyncio.run(provider(
        FakeTransport(reply=text_reply("I think this person may be in crisis."))
    ).classify(classify()))
    assert out == Failure(Kind.MALFORMED, Reason.NOT_A_LABEL)


@pytest.mark.ad19_guarantee
def test_a_label_outside_the_requested_set_is_malformed():
    out = asyncio.run(provider(
        FakeTransport(reply=label_reply("something-else"))
    ).classify(classify()))
    assert out == Failure(Kind.MALFORMED, Reason.NOT_A_LABEL)


def test_a_classification_asks_for_a_reply_that_can_only_be_a_label():
    """The closed set is imposed on the *reply shape*, not by prompt text.

    This story writes no prompts — they belong to their consumers — so an
    instruction saying "answer with one word" is not available to it, and would
    be rewordable by the consumer anyway.
    """
    payload = render_classify(classify(main_id=ASHA), DEFAULT_MODELS[Tier.FRONTIER])
    schema = payload["output_config"]["format"]["schema"]
    assert schema["properties"]["label"]["enum"] == list(LABELS)
    assert schema["additionalProperties"] is False


def test_a_classification_does_not_ask_for_deep_reasoning():
    payload = render_classify(classify(main_id=ASHA), DEFAULT_MODELS[Tier.FRONTIER])
    assert payload["output_config"]["effort"] == "low"
    assert payload["max_tokens"] == CLASSIFY_MAX_TOKENS


def test_a_classification_with_no_labels_is_refused_at_construction():
    with pytest.raises(ValueError):
        Classify(prompt=prompt(), labels=())


def test_duplicate_labels_are_refused():
    with pytest.raises(ValueError):
        Classify(prompt=prompt(), labels=("a", "a"))


# ── matrix: a classifier cannot generate ─────────────────────────────────────


#: Every name a caller could reach text through. Deliberately wider than the
#: port's own vocabulary: the failure this guards against is somebody adding a
#: convenience method, and a convenience method is rarely called ``generate``.
TEXT_PRODUCING = {
    "generate", "complete", "completion", "create", "message", "messages",
    "submit", "collect", "text", "say", "reply", "respond", "write", "call",
    "run", "prompt",
}


@pytest.mark.ad19_guarantee
def test_a_classify_only_holder_has_no_public_way_to_produce_text():
    """Matrix: *classifier cannot generate*. Asserted, not documented.

    The acceptance criterion, over the object a crisis caller actually holds.
    A single ``call()`` with a mode flag would make this something the caller
    must remember; two protocols make it something the caller cannot do.

    Python cannot make it a proof — a determined caller reaches ``_transport``
    — so this is the strongest available guarantee, exactly as AD-10 says of
    the crisis entrypoint. What it does catch is the change that would actually
    be made: a method added to the holder, or a public attribute that exposes
    one.
    """
    holder = provider(FakeTransport()).classifier()

    public = {n for n in dir(holder) if not n.startswith("_")}
    callables = {n for n in public if callable(getattr(holder, n))}
    assert callables == {"classify"}, (
        f"a classify-only holder has {sorted(callables)}; the crisis path holds "
        "one of these, and every name but `classify` is a way to author text"
    )

    for name in public:
        attribute = getattr(holder, name)
        reachable = {
            n for n in dir(attribute) if not n.startswith("_")
        } & TEXT_PRODUCING
        assert not reachable, (
            f"`{name}` on a classify-only holder exposes {sorted(reachable)}"
        )


@pytest.mark.ad19_guarantee
def test_the_classifier_surface_scan_sees_a_generate_being_added():
    """Non-vacuity: the scan above must fail when the thing it forbids is done.

    A structural gate nobody has tried to defeat is a gate resting on nothing —
    the lesson ``tests/test_crisis.py`` records and story 9a repeats twice.
    """

    class Widened(AnthropicClassifier):
        async def generate(self, work):  # pragma: no cover - never awaited
            return Completion(text="")

    holder = Widened(FakeTransport(), tiers=tiers(), budget=budget())
    callables = {
        n for n in dir(holder)
        if not n.startswith("_") and callable(getattr(holder, n))
    }
    assert callables != {"classify"}, "the surface scan would not see this"
    assert "generate" in callables


@pytest.mark.ad19_guarantee
def test_the_classifier_class_body_defines_exactly_one_method():
    """The same rule one level down, over the source rather than the object.

    An attribute scan sees what a constructed holder exposes; this sees what
    the class was written to have, so a method added behind a property or a
    conditional still fails by name.
    """
    tree = ast.parse((MODEL_DIR / "anthropic.py").read_text(encoding="utf-8"))
    bodies = {
        node.name: [
            child.name
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    assert bodies["AnthropicClassifier"] == ["classify"]


def test_the_narrow_protocols_are_what_the_holders_satisfy():
    p = provider(FakeTransport())
    assert isinstance(p.classifier(), Classifier)
    assert isinstance(p.generator(), Generator)
    assert isinstance(p.batcher(), Batcher)
    assert isinstance(p, ModelProvider)
    assert not isinstance(p.classifier(), Generator)


def test_a_narrowed_provider_is_a_different_object():
    """A provider narrowed by convention is not narrowed."""
    p = provider(FakeTransport())
    assert p.classifier() is not p
    assert isinstance(p.classifier(), AnthropicClassifier)


# ── matrix: generate ─────────────────────────────────────────────────────────


def test_a_generation_returns_text():
    """Matrix: *generate*."""
    out = asyncio.run(provider(FakeTransport(reply=text_reply("a sentence"))).generate(
        generate()
    ))
    assert isinstance(out, Completion)
    assert out.text == "a sentence"


def test_text_is_read_from_text_blocks_and_not_from_the_first_one():
    """A tier that thinks opens its reply with a thinking block.

    Reading ``content[0]`` would return an empty string on every such reply and
    report a perfectly good answer as empty.
    """
    reply = {
        "content": [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": "the answer"},
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    out = asyncio.run(provider(FakeTransport(reply=reply)).generate(generate()))
    assert isinstance(out, Completion) and out.text == "the answer"


# ── matrix: the four failures, reported distinctly ───────────────────────────


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "make, expected",
    [
        (
            lambda: provider(FakeTransport(raises=ModelUnavailable("down"))),
            Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
        ),
        (
            lambda: provider(FakeTransport(raises=ModelRefused("no"))),
            Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED),
        ),
        (
            lambda: provider(FakeTransport(), per_call=1, per_pass=1),
            Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET),
        ),
        (
            lambda: provider(FakeTransport(
                reply={"content": [], "stop_reason": "end_turn", "usage": {}}
            )),
            Failure(Kind.MALFORMED, Reason.NO_CONTENT),
        ),
    ],
    ids=["unavailable", "refused", "over-budget", "malformed"],
)
def test_the_four_failures_are_reported_distinctly(make, expected):
    """Matrix: *unavailable*, *refused*, *over budget*, *malformed*.

    The acceptance criterion: four different things happen, four different
    answers come back, and none of them is a substituted plausible answer.
    """
    out = asyncio.run(make().generate(generate()))
    assert out == expected
    assert isinstance(out, Failure)


@pytest.mark.ad19_guarantee
def test_the_four_failures_are_four_distinct_kinds():
    """A port that collapsed two of them would still pass each case above."""
    kinds = {
        Kind.UNAVAILABLE, Kind.REFUSED, Kind.OVER_BUDGET, Kind.MALFORMED,
    }
    assert len(kinds) == 4
    assert set(Kind) == kinds


@pytest.mark.ad19_guarantee
def test_no_failure_ever_carries_a_substituted_answer():
    """Never a plausible answer. There is no text field to put one in."""
    for kind in Kind:
        failure = Failure(kind, Reason.TRANSPORT_FAILED)
        assert set(Failure.__dataclass_fields__) == {"kind", "because"}
        assert isinstance(failure.kind, Kind)
        assert isinstance(failure.because, Reason)


def test_a_refusal_arriving_as_a_successful_reply_is_still_a_refusal():
    """A policy decline is HTTP 200 with ``stop_reason: refusal``.

    Checking the status code alone reads it as an answer and hands a refusal's
    empty content to the main.
    """
    reply = {"content": [], "stop_reason": "refusal", "usage": {}}
    out = asyncio.run(provider(FakeTransport(reply=reply)).generate(generate()))
    assert out == Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED)


def test_a_truncated_reply_is_malformed_and_not_a_short_answer():
    reply = text_reply("half a sente", stop="max_tokens")
    out = asyncio.run(provider(FakeTransport(reply=reply)).generate(generate()))
    assert out == Failure(Kind.MALFORMED, Reason.TRUNCATED)


def test_an_unreadable_classification_reply_is_malformed():
    out = asyncio.run(provider(FakeTransport(reply=text_reply("{not json"))).classify(
        classify()
    ))
    assert out == Failure(Kind.MALFORMED, Reason.UNREADABLE)


def test_a_failure_says_whether_it_may_have_cost_anything():
    """The four are metered differently, and *"it failed"* does not say how."""
    assert not Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET).spent
    assert not Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED).spent
    assert Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED).spent
    assert Failure(Kind.MALFORMED, Reason.TRUNCATED).spent


@pytest.mark.ad19_guarantee
def test_a_provider_fault_is_a_value_and_never_an_exception():
    """What a failure *means* is the caller's to decide.

    Crisis fails toward entering, consolidation toward skipping, a reply toward
    silence. An exception would make the port pick one default for all three,
    and two of the three would be wrong.
    """
    out = asyncio.run(provider(FakeTransport(raises=ModelUnavailable("x"))).classify(
        classify()
    ))
    assert isinstance(out, Failure)  # returned, not raised


def test_a_transport_never_leaks_a_provider_exception_type_inward():
    """The conventions forbid it, and the port only catches its own two."""
    tree = ast.parse((MODEL_DIR / "anthropic.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        names = {
            n.id for n in ast.walk(node.type) if isinstance(n, ast.Name)
        }
        if names <= {"Exception"}:
            continue  # the SDK edge, which translates and re-raises
        assert names <= {"TransportFault", "BaseException", "ValueError",
                         "ModuleNotFoundError"}, names


# ── matrix: over budget ──────────────────────────────────────────────────────


@pytest.mark.ad19_guarantee
def test_an_over_budget_call_is_refused_before_anything_is_sent():
    """Matrix: *over budget*. Never a partial spend.

    The acceptance criterion, and the reason the estimate exists at all: a
    ceiling checked on the way out is an accounting entry, and the money is
    already gone.
    """
    transport = FakeTransport()
    out = asyncio.run(
        provider(transport, per_call=1, per_pass=1).generate(generate())
    )
    assert out == Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET)
    assert transport.sent == [], "the call was sent despite being over budget"


def test_the_per_pass_ceiling_stops_a_run_of_affordable_calls():
    """One runaway prompt is not the shape CAP-7 is actually about.

    A thousand small comparisons is, which is why there are two ceilings and
    not one.
    """
    spec = DEFAULT_MODELS[Tier.CHEAP]
    # Each call is cheap to *estimate* and expensive to *charge*, which is the
    # real shape: the pass total is what the calls actually cost, not a running
    # sum of worst cases.
    a_million_input_tokens = {"input_tokens": 1_000_000, "output_tokens": 0}
    transport = FakeTransport(reply=text_reply("ok", usage=a_million_input_tokens))
    each = spec.input_micro_usd_per_mtok
    one = budget_mod.estimate(
        spec,
        uncached_text=("stable", "hello"),
        max_output_tokens=spec.default_max_tokens,
    ).micro_usd
    p = provider(transport, per_call=one, per_pass=each * 2)

    assert isinstance(asyncio.run(p.generate(generate())), Completion)
    assert isinstance(asyncio.run(p.generate(generate())), Completion)
    assert p.ledger().spent_micro_usd == each * 2
    third = asyncio.run(p.generate(generate()))
    assert third == Failure(Kind.OVER_BUDGET, Reason.PER_PASS_BUDGET)
    assert len(transport.sent) == 2


@pytest.mark.ad19_guarantee
def test_one_ledger_is_shared_by_every_holder_a_provider_hands_out():
    """A per-object ledger makes the per-pass ceiling mean *per holder*.

    Three holders, three times the budget, and CAP-7's bound quietly becomes
    something else.
    """
    p = provider(FakeTransport())
    # Reached through the private attribute on purpose: the narrow holders no
    # longer expose the ledger at all, which is the point of the case below.
    assert p.classifier()._spend is p._spend
    assert p.generator()._spend is p._spend
    assert p.batcher()._spend is p._spend


def test_a_budget_that_admits_nothing_is_refused_at_construction():
    """A nightly pass that silently does nothing looks exactly like a nightly
    pass with nothing to say."""
    with pytest.raises(BudgetError):
        Budget(per_call_micro_usd=0, per_pass_micro_usd=10)
    with pytest.raises(BudgetError):
        Budget(per_call_micro_usd=100, per_pass_micro_usd=10)
    with pytest.raises(BudgetError):
        Budget(per_call_micro_usd=True, per_pass_micro_usd=10)


def test_a_holder_with_neither_a_budget_nor_a_ledger_is_refused():
    with pytest.raises(BudgetError):
        AnthropicGenerator(FakeTransport(), tiers=tiers())


def test_the_estimate_is_pessimistic_rather_than_optimistic():
    """Erring high refuses a call that would have fit; erring low spends money
    the budget said was not there. Only one of those is recoverable."""
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    priced = estimate(spec, uncached_text=("x" * 300,), max_output_tokens=100)
    assert priced.input_tokens >= 100
    assert priced.output_tokens == 100
    assert priced.micro_usd > 0


def test_a_charge_records_what_a_call_actually_cost():
    spec = DEFAULT_MODELS[Tier.CHEAP]
    usage = charged(spec, {"input_tokens": 1_000_000, "output_tokens": 0})
    assert usage.micro_usd == spec.input_micro_usd_per_mtok
    assert usage.input_tokens == 1_000_000


def test_an_unreadable_usage_block_does_not_turn_a_good_reply_into_a_failure():
    """A reply that arrived and was used must not be lost to an accounting
    field."""
    reply = text_reply("fine", usage={"input_tokens": "lots"})
    out = asyncio.run(provider(FakeTransport(reply=reply)).generate(generate()))
    assert isinstance(out, Completion)
    assert out.usage.input_tokens == 0


def test_a_pass_ledger_resets_without_reading_a_clock():
    spend = Spend(budget())
    reservation = spend.admit(Estimate(micro_usd=500))
    spend.settle(reservation, Usage(micro_usd=500))
    assert spend.spent_micro_usd == 500
    spend.reset()
    assert spend.spent_micro_usd == 0 and spend.calls == 0


def test_a_batched_call_is_priced_at_half():
    spec = DEFAULT_MODELS[Tier.CHEAP]
    plain = estimate(spec, uncached_text=("x" * 3_000,), max_output_tokens=1_000)
    batched = estimate(
        spec, uncached_text=("x" * 3_000,), max_output_tokens=1_000, batched=True
    )
    assert batched.micro_usd <= plain.micro_usd // 2 + 1


# ── matrix: cache breakpoints (AD-19) ────────────────────────────────────────


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize("after", [1, 2, 3])
def test_the_breakpoint_is_exactly_where_the_caller_put_it(after):
    """Matrix: *cache breakpoint*. Never moved silently.

    The acceptance criterion. One block earlier and the stable content behind
    it is re-read at full price on every call; one block later and every
    request writes an entry nothing ever reads. The free tier's cost model is
    this placement.
    """
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    blocks = tuple(long_block(spec) for _ in range(3))
    payload = render_generate(
        Generate(prompt=prompt(main_id=ASHA, system=blocks, cache=Breakpoint(after))),
        spec,
    )
    marked = [
        i for i, block in enumerate(payload["system"], start=1)
        if "cache_control" in block
    ]
    assert marked == [after]


@pytest.mark.ad19_guarantee
def test_a_caller_that_states_no_breakpoint_gets_no_caching_and_no_guess():
    """Matrix: *no breakpoint*. Never guessed.

    The tempting implementation caches "the system prompt, obviously". A port
    that guessed would be right most of the time and would silently write an
    entry per request whenever it was not.
    """
    payload = render_generate(
        Generate(prompt=prompt(system=("a", "b"))), DEFAULT_MODELS[Tier.CHEAP]
    )
    assert all("cache_control" not in block for block in payload["system"])

    priced = estimate(
        DEFAULT_MODELS[Tier.CHEAP],
        uncached_text=("a", "b"),
        max_output_tokens=100,
    )
    assert not priced.caching, "cost claimed caching nobody asked for"


def test_the_breakpoint_marker_is_the_shape_the_provider_documents():
    """``cache_control`` is ``{"type": "ephemeral"}``, with an explicit TTL only
    for the hour-long entry."""
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    stable = (long_block(spec),)
    five = render_generate(
        Generate(prompt=prompt(main_id=ASHA, system=stable, cache=Breakpoint(1))), spec
    )
    assert five["system"][0]["cache_control"] == {"type": "ephemeral"}

    hour = render_generate(
        Generate(prompt=prompt(main_id=ASHA, system=stable,
                               cache=Breakpoint(1, ttl=CacheTTL.ONE_HOUR))),
        spec,
    )
    assert hour["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


@pytest.mark.ad19_guarantee
def test_a_breakpoint_past_the_prompt_is_refused_and_never_clamped():
    """The clamp is the bug. A port that slid the marker to the nearest legal
    position would produce a request that works, costs more, and says nothing
    about it."""
    with pytest.raises(BreakpointError):
        Prompt(main_id=VIDIT, system=("a",), cache=Breakpoint(2))


@pytest.mark.parametrize("bad", [0, -1, True])
def test_a_breakpoint_that_marks_nothing_is_refused(bad):
    with pytest.raises(BreakpointError):
        Breakpoint(bad)


def test_the_prefix_the_caller_drew_is_the_prefix_that_is_priced():
    p = prompt(system=("a", "b", "c"), cache=Breakpoint(2))
    assert p.cached_blocks == ("a", "b")
    assert p.uncached_blocks == ("c",)


def test_a_prefix_under_the_models_own_minimum_is_priced_as_uncached():
    """Below the minimum the marker caches nothing — silently, with no error
    and no cache-creation tokens. Pricing it as cached would make the one
    number the free tier depends on optimistic exactly where it is wrong."""
    spec = DEFAULT_MODELS[Tier.CHEAP]  # 4096-token minimum
    priced = estimate(spec, cached_text=("short",), max_output_tokens=10)
    assert priced.cache_write_tokens == 0
    assert priced.input_tokens > 0


def test_the_two_tiers_do_not_share_a_cache_minimum():
    """Not monotonic across generations, which is why it is per tier: a prompt
    that caches on one silently does not on the other."""
    assert (
        DEFAULT_MODELS[Tier.FRONTIER].cache_min_tokens
        < DEFAULT_MODELS[Tier.CHEAP].cache_min_tokens
    )


def test_the_turns_are_priced_with_what_is_outside_the_prefix():
    """A budget that could not see the half of the prompt that grows is not a
    budget."""
    spec = DEFAULT_MODELS[Tier.CHEAP]
    transport = FakeTransport(reply=text_reply("ok"))
    long_turn = Prompt(
        main_id=VIDIT,
        system=("stable",),
        turns=(Turn(Role.USER, "x" * 9_000),),
    )
    one = estimate(
        spec, uncached_text=("stable",), max_output_tokens=spec.default_max_tokens
    ).micro_usd
    # A ceiling that the system block alone fits under, and the turn does not.
    out = asyncio.run(
        AnthropicProvider(
            transport,
            tiers=tiers(),
            budget=Budget(per_call_micro_usd=one, per_pass_micro_usd=one * 100),
        ).generate(Generate(prompt=long_turn))
    )
    assert out == Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET)
    assert transport.sent == []


# ── matrix: the tier travels with the main (AD-20) ───────────────────────────


@pytest.mark.ad19_guarantee
def test_two_mains_on_different_tiers_each_use_their_own():
    """Matrix: *tier from the main*. Never a global default.

    The acceptance criterion, and the reason ``Prompt`` carries a ``main_id``
    and no model field: there is no request shape that could name a model.
    """
    transport = FakeTransport(reply=text_reply("ok"))
    p = provider(transport)
    asyncio.run(p.generate(generate(main_id=VIDIT)))
    asyncio.run(p.generate(generate(main_id=ASHA)))
    used = [call["model"] for call in transport.sent]
    assert used == [
        DEFAULT_MODELS[Tier.CHEAP].model,
        DEFAULT_MODELS[Tier.FRONTIER].model,
    ]
    assert used[0] != used[1]


@pytest.mark.ad19_guarantee
def test_no_module_outside_the_tier_table_names_a_model():
    """The acceptance criterion's second half: *no call names a model directly*.

    This is the change that passes review — it works, it is one line, and it is
    the line that makes the tier stop travelling. So it fails by name instead.
    """
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        if path.name == "tier.py" and path.parent.name == "model":
            continue
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith("claude-")
            ):
                offenders.append(f"{path.relative_to(ROOT)}: {node.value}")
    assert not offenders, (
        f"a model is named outside the tier table: {offenders}. The tier "
        "travels with the main (AD-20); a call site that names a model has "
        "taken that decision away from configuration"
    )


def test_the_model_name_scan_sees_a_model_written_into_a_call_site(tmp_path):
    """Non-vacuity for the scan above."""
    path = tmp_path / "bypass.py"
    path.write_text('def f():\n    return {"model": "claude-opus-5"}\n', "utf-8")
    found = [
        node.value
        for node in ast.walk(ast.parse(path.read_text("utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("claude-")
    ]
    assert found == ["claude-opus-5"]


@pytest.mark.ad19_guarantee
def test_an_unknown_tier_is_refused_and_never_falls_back():
    """Matrix: *unknown tier*. Never a silent fallback."""
    with pytest.raises(UnknownTier):
        Tiers.parse({VIDIT: "platinum"})


def test_a_main_with_no_tier_at_all_is_refused_before_anything_is_sent():
    """There is no global default, in either direction."""
    transport = FakeTransport()
    p = AnthropicProvider(transport, tiers=Tiers.parse({}), budget=budget())
    with pytest.raises(UnknownTier):
        asyncio.run(p.generate(generate()))
    assert transport.sent == []


def test_a_tier_assignment_is_refused_at_load_and_not_at_the_first_call():
    """A typo caught at startup is a failed boot; a typo caught at the first
    call is a main whose nightly pass silently never ran."""
    with pytest.raises(UnknownTier):
        Tiers.parse("vidit:cheep")
    assert Tiers.parse("vidit:cheap,asha:frontier").of(ASHA) is Tier.FRONTIER


def test_a_tier_with_no_model_in_this_build_is_refused_at_construction():
    with pytest.raises(UnknownTier):
        Tiers(mains={VIDIT: Tier.FRONTIER}, models={Tier.CHEAP: DEFAULT_MODELS[Tier.CHEAP]})


@pytest.mark.parametrize("raw", ["vidit", "vidit:", ":cheap", "a:cheap,a:frontier"])
def test_a_malformed_tier_assignment_is_refused(raw):
    with pytest.raises(UnknownTier):
        Tiers.parse(raw)


def test_a_tier_table_is_frozen_and_returns_a_new_one_when_a_main_moves():
    table = tiers()
    moved = table.with_main(VIDIT, Tier.FRONTIER)
    assert table.of(VIDIT) is Tier.CHEAP
    assert moved.of(VIDIT) is Tier.FRONTIER


def test_the_tier_vocabulary_matches_what_the_log_already_carries():
    """The belief log has carried ``model_tier`` since story 1; the enum and
    the fixture must not disagree about what a tier is called."""
    assert {t.value for t in Tier} == {"cheap", "frontier"}


# ── the request shapes, pinned ───────────────────────────────────────────────


@pytest.mark.ad19_guarantee
def test_no_request_ever_carries_a_fixed_thinking_budget():
    """The shape that is now a 400 rather than a degradation.

    It is not sent on either tier, in any form. A renderer that kept it for
    "the cheap model, which still takes it" would be one model rename away from
    failing every frontier call.
    """
    for tier, spec in DEFAULT_MODELS.items():
        for payload in (
            render_generate(generate(), spec),
            render_classify(classify(), spec),
        ):
            assert "budget_tokens" not in json.dumps(payload), tier


def test_a_tier_without_adaptive_thinking_is_sent_no_thinking_parameter():
    payload = render_generate(generate(), DEFAULT_MODELS[Tier.CHEAP])
    assert "thinking" not in payload
    frontier = render_generate(generate(main_id=ASHA), DEFAULT_MODELS[Tier.FRONTIER])
    assert frontier["thinking"] == {"type": "adaptive"}


def test_a_tier_without_an_effort_setting_is_sent_none():
    """An effort setting is an error, not an ignored field, where it does not
    exist."""
    payload = render_generate(generate(), DEFAULT_MODELS[Tier.CHEAP])
    assert "output_config" not in payload or "effort" not in payload["output_config"]


@pytest.mark.ad19_guarantee
def test_a_prompt_ending_in_an_assistant_turn_is_refused_at_construction():
    """A last-assistant-turn prefill is refused on every current model.

    The first version of this case *pinned the pass-through* — it asserted the
    renderer faithfully emitted the trailing assistant turn, so the port
    rendered a request its own docstring says is rejected, and a test agreed
    with it. Refused where every other build mistake in this port is refused.
    """
    with pytest.raises(BreakpointError):
        Prompt(
            main_id=VIDIT,
            turns=(Turn(Role.USER, "hi"), Turn(Role.ASSISTANT, "there")),
        )
    # An assistant turn *inside* a conversation is ordinary and still renders.
    payload = render_generate(
        Generate(prompt=Prompt(
            main_id=VIDIT,
            turns=(Turn(Role.USER, "hi"), Turn(Role.ASSISTANT, "there"),
                   Turn(Role.USER, "and?")),
        )),
        DEFAULT_MODELS[Tier.CHEAP],
    )
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant", "user"]


def test_every_request_names_a_model_and_an_output_ceiling():
    for spec in DEFAULT_MODELS.values():
        payload = render_generate(generate(), spec)
        assert payload["model"] == spec.model
        assert payload["max_tokens"] == spec.default_max_tokens


def test_an_output_ceiling_past_the_models_own_is_refused_before_the_wire():
    spec = DEFAULT_MODELS[Tier.CHEAP]
    with pytest.raises(BudgetError):
        render_generate(
            Generate(prompt=prompt(), max_tokens=spec.max_output_tokens + 1), spec
        )


def test_a_prompt_with_no_system_blocks_sends_no_system_field():
    payload = render_generate(
        Generate(prompt=Prompt(main_id=VIDIT, turns=(Turn(Role.USER, "hi"),))),
        DEFAULT_MODELS[Tier.CHEAP],
    )
    assert "system" not in payload


# ── matrix: batch (AD-9, AD-19) ──────────────────────────────────────────────


def batch_items():
    return [
        BatchItem(ref="one", work=classify()),
        BatchItem(ref="two", work=generate(main_id=ASHA)),
    ]


def test_a_batch_submission_returns_an_identifier():
    """Matrix: *batch submit*."""
    transport = FakeTransport(batch={"id": "msgbatch_abc"})
    out = asyncio.run(provider(transport).submit(batch_items()))
    assert isinstance(out, Submission)
    assert out.batch_id == "msgbatch_abc"
    assert out.refs == ("one", "two")


def test_a_batch_request_carries_a_reference_and_the_whole_request():
    transport = FakeTransport()
    asyncio.run(provider(transport).submit(batch_items()))
    sent = transport.submitted[0]
    assert [r["custom_id"] for r in sent] == ["one", "two"]
    assert sent[0]["params"]["model"] == DEFAULT_MODELS[Tier.CHEAP].model
    assert sent[1]["params"]["model"] == DEFAULT_MODELS[Tier.FRONTIER].model


def test_a_batch_request_never_asks_for_a_stream():
    transport = FakeTransport()
    asyncio.run(provider(transport).submit(batch_items()))
    assert all("stream" not in r["params"] for r in transport.submitted[0])


@pytest.mark.ad19_guarantee
def test_a_submission_survives_the_process_that_made_it():
    """Matrix: *batch submit*, durable. The acceptance criterion.

    The evening's pass submits and the morning's collects (AD-9), so the
    process that submitted is routinely gone. A submission is strings: no live
    handle, no open connection, no reference to the provider that made it.
    """
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))
    assert isinstance(made, Submission)

    written = made.to_json()
    assert json.loads(written)  # plain JSON, storable in a log line
    read_back = Submission.from_json(written)
    assert read_back == made

    # A *different* provider, standing in for a different process, collects it.
    fresh = provider(
        FakeTransport(
            status={"processing_status": "ended"},
            results=[
                {
                    "custom_id": "one",
                    "result": {"type": "succeeded", "message": label_reply("crisis")},
                }
            ],
        )
    )
    collected = asyncio.run(fresh.collect(read_back))
    assert isinstance(collected, Collected)
    assert isinstance(collected.outcomes["one"], Decision)


def test_a_submission_round_trips_to_the_same_bytes():
    made = Submission(
        batch_id="b_1",
        items=(Submitted(ref="one", tier="cheap", labels=("a", "b")),),
    )
    assert Submission.from_json(made.to_json()).to_json() == made.to_json()


@pytest.mark.parametrize(
    "raw", ['[]', '{}', '{"batch_id": ""}', '{"batch_id": "b", "items": 3}',
            '{"batch_id": "b", "items": [{"ref": 1, "tier": "cheap"}]}']
)
def test_an_unreadable_submission_is_refused_rather_than_half_read(raw):
    with pytest.raises(ValueError):
        Submission.from_json(raw)


@pytest.mark.ad19_guarantee
def test_a_batch_collected_early_is_a_normal_answer_and_not_an_error():
    """Matrix: *batch not ready*. Not an error.

    A batch may take a day, so asking early is the ordinary case. Raising there
    would make the ordinary case indistinguishable from a fault — the shape
    AD-27 gives silence one package over.
    """
    transport = FakeTransport(status={"processing_status": "in_progress"})
    submission = Submission(batch_id="b_1", items=())
    out = asyncio.run(provider(transport).collect(submission))
    assert out == Collected(ready=False)
    assert not out.ready
    assert not isinstance(out, Failure)


@pytest.mark.ad19_guarantee
def test_a_partly_failed_batch_returns_per_item_outcomes():
    """Matrix: *batch partial*. Never all-or-nothing.

    The acceptance criterion. A caller told only that *the batch* failed throws
    away the nine results it got because the tenth expired.
    """
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))
    transport = FakeTransport(
        status={"processing_status": "ended"},
        results=[
            {
                "custom_id": "one",
                "result": {"type": "succeeded", "message": label_reply("ordinary")},
            },
            {"custom_id": "two", "result": {"type": "expired"}},
        ],
    )
    out = asyncio.run(provider(transport).collect(made))
    assert isinstance(out, Collected) and out.ready
    assert isinstance(out.outcomes["one"], Decision)
    assert out.outcomes["two"] == Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)
    assert set(out.failures) == {"two"}


def test_a_cancelled_item_is_a_refusal_and_an_expired_one_is_not():
    """Resubmitting an expiry is right; resubmitting a refusal is a spend
    nobody asked for."""
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))
    transport = FakeTransport(
        results=[
            {"custom_id": "one", "result": {"type": "canceled"}},
            {"custom_id": "two", "result": {"type": "expired"}},
        ]
    )
    out = asyncio.run(provider(transport).collect(made))
    assert out.outcomes["one"].kind is Kind.REFUSED
    assert out.outcomes["two"].kind is Kind.UNAVAILABLE


def test_a_classification_submitted_in_a_batch_comes_back_as_a_decision():
    """The property the submission's remembered labels exist for.

    Without them a collected batch would answer every item with text — and a
    classify-only caller that submitted work would collect prose.
    """
    made = asyncio.run(provider(FakeTransport()).submit(
        [BatchItem(ref="one", work=classify())]
    ))
    transport = FakeTransport(
        results=[{
            "custom_id": "one",
            "result": {"type": "succeeded", "message": text_reply("a whole sentence")},
        }]
    )
    out = asyncio.run(provider(transport).collect(made))
    assert out.outcomes["one"] == Failure(Kind.MALFORMED, Reason.NOT_A_LABEL)


def test_a_ref_that_never_came_back_is_reported_as_missing():
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))
    transport = FakeTransport(
        results=[{
            "custom_id": "one",
            "result": {"type": "succeeded", "message": label_reply("crisis")},
        }]
    )
    out = asyncio.run(provider(transport).collect(made))
    assert out.missing(made) == ("two",)


def test_a_result_row_for_an_unknown_ref_is_dropped_rather_than_guessed_at():
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))
    transport = FakeTransport(
        results=[{"custom_id": "ghost", "result": {"type": "succeeded"}}]
    )
    out = asyncio.run(provider(transport).collect(made))
    assert "ghost" not in out.outcomes


@pytest.mark.ad19_guarantee
def test_an_over_budget_batch_is_refused_whole_and_never_in_part():
    """A batch where the budget stopped halfway is a partial spend with no
    record of which half went."""
    transport = FakeTransport()
    out = asyncio.run(
        provider(transport, per_call=1, per_pass=1).submit(batch_items())
    )
    assert out == Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET)
    assert transport.submitted == []


def test_a_batch_whose_total_passes_the_pass_ceiling_is_refused_whole():
    spec = DEFAULT_MODELS[Tier.CHEAP]
    one = estimate(
        spec,
        uncached_text=("stable", "hello"),
        max_output_tokens=CLASSIFY_MAX_TOKENS,
        batched=True,
    ).micro_usd
    transport = FakeTransport()
    p = provider(transport, per_call=one, per_pass=one * 2)
    out = asyncio.run(p.submit([
        BatchItem(ref="one", work=classify()),
        BatchItem(ref="two", work=classify()),
        BatchItem(ref="three", work=classify()),
    ]))
    assert out == Failure(Kind.OVER_BUDGET, Reason.PER_PASS_BUDGET)
    assert transport.submitted == []


def test_a_submitted_batch_is_charged_at_submission():
    """A batch is committed the moment the provider accepts it, and the process
    that collects it hours later is routinely not this one."""
    p = provider(FakeTransport())
    assert p.ledger().spent_micro_usd == 0
    made = asyncio.run(p.submit(batch_items()))
    assert p.ledger().spent_micro_usd > 0
    assert made.committed_micro_usd == p.ledger().spent_micro_usd


def test_two_items_sharing_a_reference_are_refused():
    """Results come back in any order, so a repeated ref makes two outcomes
    indistinguishable."""
    with pytest.raises(ValueError):
        asyncio.run(provider(FakeTransport()).submit([
            BatchItem(ref="one", work=classify()),
            BatchItem(ref="one", work=classify()),
        ]))


def test_an_empty_batch_is_refused():
    with pytest.raises(ValueError):
        asyncio.run(provider(FakeTransport()).submit([]))


def test_a_batch_transport_fault_is_reported_as_one_of_the_four():
    out = asyncio.run(provider(
        FakeTransport(raises=ModelUnavailable("down"))
    ).submit(batch_items()))
    assert out == Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)


def test_a_batch_with_no_identifier_is_malformed():
    out = asyncio.run(provider(FakeTransport(batch={})).submit(batch_items()))
    assert out == Failure(Kind.MALFORMED, Reason.UNREADABLE)


# ── matrix: no model call inside a fold (AD-30) ──────────────────────────────


def _module_of(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _imports_of(path: Path) -> set[str]:
    """Every module ``path`` imports, **including relatively**.

    Round 2's finding: the scan collected ``ast.ImportFrom`` only at
    ``node.level == 0``, so ``from ..model.port import Prompt`` in
    ``half/store/fold.py`` passed both AD-30 scans and all 2,316 tests. The
    non-vacuity case used an absolute import, so it shared the assumption it
    existed to test — which is the failure this file's own log-scan docstring
    warns about, one gate over.

    A relative import is resolved against the file's own package, so the two
    spellings produce the same answer and the scan cannot be walked past by
    choosing one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = path.relative_to(ROOT).with_suffix("").parts[:-1]
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                # `.` is this package, `..` its parent, and so on.
                base = package[: len(package) - (node.level - 1)]
                module = ".".join([*base, module] if module else list(base))
            if not module:
                continue
            out.add(module)
            out.update(f"{module}.{alias.name}" for alias in node.names)
    return out


@pytest.mark.ad19_guarantee
def test_no_model_call_is_reachable_from_a_fold():
    """Matrix: *inside a fold*. AD-30, asserted.

    The acceptance criterion. *"Just re-derive it"* is the natural way to write
    a fold, and it silently breaks the replay invariant the first time a main
    changes model tier — which is exactly why ``tests/conftest.py``'s replay
    fixture has a tier change in the middle of it.

    Transitive, not one hop: a fold that imported a helper that imported the
    port would pass a direct-import check while being every bit as impure.
    """
    edges = {
        _module_of(p): _imports_of(p) for p in (ROOT / "half").rglob("*.py")
    }

    def reaches(start: str, seen: set[str] | None = None) -> set[str]:
        seen = seen if seen is not None else set()
        for target in edges.get(start, ()):
            if not target.startswith("half"):
                continue
            module = target if target in edges else target.rsplit(".", 1)[0]
            if module in seen:
                continue
            seen.add(module)
            reaches(module, seen)
        return seen

    for pure in ("half.store.fold", "half.store.ops", "half.store.records"):
        touched = {m for m in reaches(pure) if m.startswith("half.model")}
        assert not touched, (
            f"{pure} reaches {sorted(touched)} — replay never calls a model "
            "(AD-30), and a fold that re-derives is not reproducible"
        )


@pytest.mark.ad19_guarantee
def test_nothing_under_the_store_imports_the_model_port_at_all():
    """The same rule, stated the direct way as well.

    Two assertions rather than one because they fail differently: the
    transitive one names the path, and this one names the file, which is what a
    reviewer reading a diff needs.
    """
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "half" / "store").rglob("*.py")
        if any(i.startswith("half.model") for i in _imports_of(path))
    ]
    assert not offenders, f"the store reaches the model port: {offenders}"


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "spelling",
    [
        "from half.model.port import Prompt",
        "import half.model.port",
        "import half.model.anthropic as m",
        "from ..model.port import Prompt",
        "from ..model import port",
        "from ...half.model.port import Prompt",
    ],
    ids=["absolute-from", "absolute-import", "aliased", "relative",
         "relative-module", "relative-through-the-root"],
)
def test_the_fold_reachability_scan_sees_each_spelling_of_the_import(
    spelling, tmp_path
):
    """Non-vacuity, one *spelling* at a time.

    The first version had a single case and it wrote an **absolute** import —
    the one spelling the scan already handled. A relative import of the port
    into ``half/store/fold.py`` passed every test in the tree.

    Written at the real path so the relative spellings resolve the way they
    would in the tree, rather than against a temporary directory that is not a
    package.
    """
    store = tmp_path / "half" / "store"
    store.mkdir(parents=True)
    path = store / "bypass.py"
    path.write_text(spelling + "\n", encoding="utf-8")

    package = path.relative_to(tmp_path).with_suffix("").parts[:-1]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                module = ".".join([*base, module] if module else list(base))
            if module:
                found.add(module)
                found.update(f"{module}.{a.name}" for a in node.names)
    assert any(i.startswith("half.model") for i in found), (
        f"the scan does not see: {spelling}"
    )


# ── matrix: secrets and content (AD-11, AD-22) ───────────────────────────────


@pytest.mark.ad19_guarantee
def test_no_key_material_reaches_the_store_tree_logs_or_errors(tmp_path, caplog):
    """Matrix: *secrets*. Asserted byte-wise.

    The acceptance criterion, over the three places a key actually escapes to:
    a store tree that is exportable and replayable (AD-11), a log line, and the
    text of an error somebody prints.

    **Driven through the real ``FileSecretStore`` and a real store write**,
    which is review round 1's correction: the first version created an empty
    directory, wrote nothing to it, and asserted it was empty — a case that
    could not have failed however the key was handled.
    """
    from half.secrets import FileSecretStore
    from half.store.export import scan_for_secrets
    from half.store.store import Store

    caplog.set_level(logging.DEBUG)
    mains_root = tmp_path / "mains"
    (mains_root / "vidit").mkdir(parents=True)

    # The key goes where AD-11 says a key may go: a sibling of the store tree.
    secrets = FileSecretStore.beside(mains_root)
    secrets.put(VIDIT, MODEL_KEY, FAKE_KEY)

    transport = SDKTransport.from_secrets(secrets, VIDIT)
    p = AnthropicProvider(transport, tiers=tiers(), budget=budget())

    # A real store write, of the kind a consumer would make around a call.
    with Store(mains_root / "vidit") as store:
        store.record(
            Op.ASSERT, "b_1", "2026-09-01T09:00Z", claim="uses a model",
            **ladder.admitted(),
        )

    surfaces = [repr(transport), repr(p), repr(p.ledger()), repr(p.classifier())]
    for name in dir(transport):
        if not name.startswith("_"):
            surfaces.append(repr(getattr(transport, name, None)))

    for raises in (
        lambda: SDKTransport(""),
        lambda: SDKTransport.from_secrets(secrets, "nobody"),
        lambda: asyncio.run(p.generate(generate(main_id="nobody"))),
    ):
        with pytest.raises(ModelError) as caught:
            raises()
        surfaces.append(f"{caught.value!r} {caught.value}")

    surfaces.append(caplog.text)
    for path in mains_root.rglob("*"):
        if path.is_file():
            surfaces.append(path.read_bytes().decode("utf-8", errors="replace"))

    leaked = [s for s in surfaces if FAKE_KEY in s or FAKE_KEY[8:] in s]
    assert not leaked, "key material appeared where it must never appear (AD-11)"

    # And the store tree itself is clean by the scanner the export gate uses,
    # which knows the shape of an Anthropic key by name.
    assert scan_for_secrets(mains_root) == []
    # The key is really there, in the place it is allowed to be — otherwise the
    # assertions above are about a key nobody stored.
    assert secrets.get(VIDIT, MODEL_KEY) == FAKE_KEY
    assert not Path(secrets.root).resolve().is_relative_to(mains_root.resolve())


def test_a_missing_key_is_misconfiguration_and_never_a_refusal():
    """``half/errors.py`` promises a refusal is never raised out of the port.

    Raising ``ModelRefused`` for a key nobody supplied contradicted that, and
    the first test caught the base class so the wrong subclass passed. Nothing
    was asked of a provider and nothing declined.
    """
    with pytest.raises(ModelMisconfigured):
        SDKTransport("")
    assert not issubclass(ModelMisconfigured, TransportFault)


#: The methods a logger is called through. Matched on the *method* rather than
#: on a receiver spelled ``logger``, because renaming the module-level logger
#: was one of the three ways past the first version of this scan.
LOG_METHODS = frozenset({
    "debug", "info", "warning", "error", "exception", "critical", "log",
})

#: The two closed enums. **Any** member of either is content-free by
#: construction — that is what makes them closed — so an expression rooted in
#: one needs no further inspection.
CLOSED_ENUMS = frozenset({"Kind", "Reason"})

#: Fields on a ``Failure`` that hold one of those enums, and nothing else. An
#: **allowlist**, which is review round 1's correction and the whole shape of
#: the fix: the first version listed forbidden names, so ``logger.info("%s",
#: x)`` with a completion in ``x`` passed, and so did an f-string, because it
#: never looked at argument zero at all. Now every argument must be *provably*
#: content-free rather than merely not-obviously-content.
ALLOWED_LOG_ATTRS = frozenset({"kind", "because", "value"})


def _root_name(node: ast.expr) -> str | None:
    """The leftmost name of a dotted expression: ``Kind.REFUSED`` -> ``Kind``."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _log_calls(tree: ast.AST):
    """Every logging call in a module, however the logger is spelled."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
            and not isinstance(node.func.value, ast.Constant)
        ):
            yield node


def content_free(argument: ast.expr) -> bool:
    """Whether one log argument provably cannot carry content.

    An f-string is never content-free: it interpolates whatever it names, and
    it is how a completion actually reaches a log. A ``len(...)`` is always
    content-free — a count is a count whatever it counts (AD-22 permits
    counts). Everything else must resolve entirely to the two closed enums.
    """
    if isinstance(argument, ast.JoinedStr):
        return False
    if isinstance(argument, ast.Constant):
        return isinstance(argument.value, (str, int, float, bool)) or (
            argument.value is None
        )
    if (
        isinstance(argument, ast.Call)
        and isinstance(argument.func, ast.Name)
        and argument.func.id == "len"
    ):
        return True
    if isinstance(argument, ast.Attribute):
        # A member of a closed enum — every one of them is safe by definition.
        if _root_name(argument) in CLOSED_ENUMS:
            return True
        # A field that holds one. The receiver is unconstrained on purpose:
        # ``failure.kind`` is a ``Kind`` whatever the local is called.
        return argument.attr in ALLOWED_LOG_ATTRS and isinstance(
            argument.value, (ast.Name, ast.Attribute)
        )
    return False


@pytest.mark.ad19_guarantee
def test_no_log_call_in_the_model_package_can_carry_content():
    """Matrix: *content in logs, any spelling*. AD-22.

    Structural, because a behavioural test cannot cover it: a log line carrying
    a completion breaks nothing, passes every other case in this file, and
    hands the most intimate dataset a person owns to an observability side
    channel.

    **Every argument, argument zero included.** The first version inspected
    ``node.args[1:]``, so the format string — the one argument an f-string
    lives in — was invisible, and ``logger.info(f"got {reply}")`` passed all
    122 cases of this gate.
    """
    offenders: list[str] = []
    for path in sorted(MODEL_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in _log_calls(tree):
            arguments = list(node.args) + [k.value for k in node.keywords]
            for argument in arguments:
                if not content_free(argument):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} "
                        f"{ast.dump(argument)[:60]}"
                    )
    assert not offenders, f"a log line could carry content (AD-22): {offenders}"


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "bypass",
    [
        'logger.info(f"got {reply}")',
        'logger.info("got %s", reply)',
        'logger.info("got %s", x)',
        'log.info("got %s", reply.text)',
        'self._log.warning(f"{prompt}")',
        'logging.getLogger(__name__).info("%s", completion)',
        'logger.log(20, f"{turn.text}")',
        'logger.info("got " + reply)',
        'logger.info("got %s", failure.kind, extra=reply)',
    ],
    ids=["f-string", "percent-arg", "opaque-name", "renamed-logger",
         "attribute-logger", "inline-logger", "log-level-call", "concatenated",
         "keyword"],
)
def test_the_log_content_scan_sees_each_way_a_completion_reaches_a_log(bypass, tmp_path):
    """Non-vacuity, one *way* at a time.

    The first version had exactly one case and it reproduced the scan's own
    blind spot — it asserted the scan caught ``logger.info('got %s',
    reply.text)``, which was the single shape the scan was written against. A
    non-vacuity case that shares the gate's assumption proves nothing, and this
    is the second story running where review has had to say so.
    """
    path = tmp_path / "bypass.py"
    path.write_text(f"def f(reply, x, prompt, completion, turn):\n    {bypass}\n",
                    encoding="utf-8")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = list(_log_calls(tree))
    assert calls, f"the scan does not even see the call in {bypass!r}"
    arguments = [a for c in calls for a in list(c.args) + [k.value for k in c.keywords]]
    assert any(not content_free(a) for a in arguments), (
        f"the scan does not see {bypass!r}"
    )


@pytest.mark.parametrize(
    "allowed",
    [
        'logger.warning("model call failed: %s/%s", failure.kind, failure.because)',
        'logger.info("batch collected: %d", len(outcomes))',
        'logger.warning("refused: %s/%s", Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET)',
    ],
    ids=["closed-enums", "a-count", "enum-members"],
)
def test_the_log_content_scan_does_not_fire_on_a_count_or_a_closed_enum(
    allowed, tmp_path
):
    """The false positives that matter. AD-22 permits counts and timings, and a
    scan that forbade them would push people to stop logging rather than to
    stop logging content."""
    path = tmp_path / "fine.py"
    path.write_text(f"def f(failure, outcomes):\n    {allowed}\n", encoding="utf-8")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _log_calls(tree):
        for argument in list(call.args) + [k.value for k in call.keywords]:
            assert content_free(argument), ast.dump(argument)


@pytest.mark.ad19_guarantee
def test_a_failing_call_logs_a_reason_and_never_the_prompt(caplog):
    """The scan above over the source, and this over a real run."""
    caplog.set_level(logging.DEBUG)
    secret = "the main said something private"
    asyncio.run(provider(FakeTransport(raises=ModelUnavailable("x"))).generate(
        Generate(prompt=Prompt(main_id=VIDIT, turns=(Turn(Role.USER, secret),)))
    ))
    assert secret not in caplog.text
    assert Reason.TRANSPORT_FAILED.value in caplog.text


def test_a_failure_reason_is_a_closed_set_and_not_a_message():
    """A free-text reason is the shortest path from a completion to a log
    line."""
    assert all(isinstance(r, str) for r in Reason)
    assert Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED).because is (
        Reason.TRANSPORT_FAILED
    )


# ── matrix: offline construction ─────────────────────────────────────────────


def test_the_implementation_constructs_with_no_key_and_no_environment(monkeypatch):
    """Matrix: *offline construction*.

    Half of the acceptance criterion; the socket-level half is in
    ``tests/test_model_offline.py``.
    """
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    p = AnthropicProvider(FakeTransport(), tiers=tiers(), budget=budget())
    assert isinstance(p, ModelProvider)


def test_a_fake_four_methods_long_satisfies_the_whole_transport():
    """The port stayed narrow, and this is the evidence."""
    assert isinstance(FakeTransport(), Transport)
    methods = {
        n for n in dir(Transport) if not n.startswith("_")
    }
    assert methods == {"message", "batch_create", "batch_status", "batch_results"}


def test_the_sdk_is_not_imported_at_module_scope():
    """A top-level SDK import would build nothing but would make the offline
    gate depend on the SDK's own import being inert."""
    tree = ast.parse((MODEL_DIR / "anthropic.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(a.name != "anthropic" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "anthropic"


def test_the_port_and_the_tier_table_import_no_sdk_at_all():
    for name in ("port.py", "tier.py", "budget.py"):
        text = (MODEL_DIR / name).read_text(encoding="utf-8")
        assert "anthropic" not in text, f"{name} reaches the SDK"


# ── the exception boundary ───────────────────────────────────────────────────


def test_a_model_error_is_a_build_mistake_and_not_a_provider_answer():
    """The distinction the whole failure design rests on."""
    assert issubclass(UnknownTier, ModelError)
    assert issubclass(BreakpointError, ModelError)
    assert issubclass(BudgetError, ModelError)
    assert issubclass(ModelUnavailable, ModelError)
    assert issubclass(ModelRefused, ModelError)


def test_the_port_makes_exactly_one_attempt_and_never_retries_a_refusal():
    """No retry that turns a refusal into a spend."""
    transport = FakeTransport(raises=ModelRefused("no"))
    asyncio.run(provider(transport).generate(generate()))
    assert len(transport.sent) == 1


def test_the_estimate_and_the_charge_round_the_same_way():
    """Two copies with different rounding is how the two come to disagree about
    the same call."""
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    assert spec.input_micro_usd(1) == 5
    assert spec.output_micro_usd(1) == 25
    assert spec.cache_read_micro_usd(1_000_000) == spec.input_micro_usd_per_mtok // 10


def test_an_estimate_reports_whether_it_claimed_any_caching():
    assert not Estimate().caching
    assert Estimate(cache_write_tokens=10).caching


# ═══════════════════════════════════════════════════════════════════════════
# Review round 1. Each section below is a matrix row the spec gained after
# three reviewers put the first version under mutation.
# ═══════════════════════════════════════════════════════════════════════════


# ── matrix: concurrent spend (CAP-7) ─────────────────────────────────────────


class SlowTransport(FakeTransport):
    """A transport that takes long enough for calls to actually overlap.

    Without the await, eight ``asyncio.gather``-ed calls run to completion one
    after another and the defect this exists for does not appear.
    """

    async def message(self, payload):
        self.sent.append(dict(payload))
        await asyncio.sleep(0.01)
        return self.reply if self.reply is not None else text_reply("ok")


@pytest.mark.ad19_guarantee
def test_the_pass_ceiling_binds_when_calls_overlap():
    """Matrix: *concurrent spend*. Admission reserves.

    The defect, at the concurrency the product actually ships with. Verified
    before the fix: eight calls at ``half.schedule.tick.DEFAULT_BOUND``, a
    ceiling of three calls' worth, **eight admitted and none refused** — because
    ``admit`` checked ``spent + estimate`` and returned, while ``spent`` only
    moved after the round trip, so every overlapping call was measured against
    the same figure.

    A ledger that only advances after a round trip does not bind when calls
    overlap, and *"a refusal rather than a spend"* was then neither.
    """
    from half.schedule.tick import DEFAULT_BOUND

    spec = DEFAULT_MODELS[Tier.CHEAP]
    work = Generate(prompt=prompt(system=("s",), turns=("hi",)), max_tokens=8)
    each = estimate(
        spec, uncached_text=("s", "hi"), max_output_tokens=8
    ).micro_usd
    ceiling = each * 3

    transport = SlowTransport(reply=text_reply("ok"))
    p = provider(transport, per_call=each, per_pass=ceiling)

    async def eight():
        return await asyncio.gather(
            *(p.generate(work) for _ in range(DEFAULT_BOUND))
        )

    outcomes = asyncio.run(eight())
    admitted = [o for o in outcomes if isinstance(o, Completion)]
    refused = [
        o for o in outcomes
        if isinstance(o, Failure) and o.kind is Kind.OVER_BUDGET
    ]
    assert len(admitted) == 3, f"{len(admitted)} admitted against a 3-call ceiling"
    assert len(refused) == DEFAULT_BOUND - 3
    assert len(transport.sent) == 3, "a refused call was sent anyway"
    assert p.ledger().spent_micro_usd <= ceiling


@pytest.mark.ad19_guarantee
def test_a_reservation_is_counted_the_moment_it_is_taken():
    """The mechanism, without the concurrency, so a failure names the cause.

    ``committed`` is what admission is decided against, and it has to include
    calls that are still in flight — that is the whole of the fix.
    """
    spend = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    first = spend.admit(Estimate(micro_usd=60))
    assert isinstance(first, Reservation)
    assert spend.committed_micro_usd == 60 and spend.spent_micro_usd == 0
    assert spend.admit(Estimate(micro_usd=60)) is Reason.PER_PASS_BUDGET


def test_a_released_reservation_is_given_back_and_never_leaks():
    """The mirror-image bug: a leaked reservation shrinks the pass for ever."""
    spend = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    held = spend.admit(Estimate(micro_usd=100))
    assert spend.remaining_micro_usd == 0
    spend.release(held)
    assert spend.remaining_micro_usd == 100 and spend.spent_micro_usd == 0


def test_a_transport_fault_gives_the_reservation_back():
    transport = FakeTransport(raises=ModelUnavailable("down"))
    p = provider(transport)
    asyncio.run(p.generate(generate()))
    assert p.ledger().spent_micro_usd == 0
    assert p._spend.reserved_micro_usd == 0, "an unavailable call leaked its hold"


def test_a_raised_build_mistake_gives_the_reservation_back():
    """``ModelRequestInvalid`` is raised out of the port, not swallowed — and
    the reservation still has to come back."""

    class Broken(FakeTransport):
        async def message(self, payload):
            raise ModelRequestInvalid("bad shape")

    p = provider(Broken())
    with pytest.raises(ModelRequestInvalid):
        asyncio.run(p.generate(generate()))
    assert p._spend.reserved_micro_usd == 0


def test_settling_something_this_ledger_did_not_issue_is_refused():
    spend = Spend(budget())
    with pytest.raises(BudgetError):
        spend.settle("not a reservation", Usage())


# ── matrix: non-Latin estimate (CAP-7, and story 4c's reach) ─────────────────


#: One word of real text per script, with the number of characters that matters.
#: Latin is here as the control: it is the script the old constant was tuned on
#: and the only one it was right for.
SCRIPTS = {
    "latin": "the quick brown fox jumps over the lazy dog. ",
    "japanese": "転職を考えている。",
    "chinese": "我在考虑换工作。",
    "korean": "이직을 생각하고 있다。",
    "thai": "เปลี่ยนงาน",
    "devanagari": "यात्रा की योजना बना रहा हूँ।",
    "khmer": "ភាសាខ្មែរ",
    "arabic": "أفكر في تغيير وظيفتي.",
}


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize("script", sorted(set(SCRIPTS) - {"latin"}))
def test_a_non_latin_estimate_is_at_least_one_token_per_character(script):
    """Matrix: *non-Latin estimate*. Never under.

    Verified before the fix: 300 CJK characters estimated to 108 tokens,
    identical to 300 Latin ones, against a real cost near 300 — and 1,600
    Japanese characters at 542 estimated against 1,600 to 2,400 real.

    One token per character is the documented floor for these scripts, so an
    estimate below it is under-charging by construction. ``half/text.py`` is in
    this tree because the same one-constant-fits-every-script assumption was
    wrong one layer over, where it made non-Latin beliefs unretrievable. Here
    it spends money the budget said was not there, for exactly the mains the
    reach requirement is about.
    """
    text = SCRIPTS[script] * 40
    assert tokens_in(text) >= _real_floor(text), (
        f"{script}: estimated {tokens_in(text)} tokens against a floor of "
        f"{_real_floor(text)} — under the real cost"
    )


def _real_floor(text: str) -> int:
    """The lowest number of tokens this text can honestly cost.

    Composed per character rather than taken over the non-ASCII subset, which
    is round 2's correction: the floor used to be the non-ASCII *count*, so a
    mixed string satisfied a bound named "one token per character" while being
    under it — ``tokens_in("a私" * 300)`` is 558 for 600 characters. A
    code-switching main is exactly the reach case these cases are named for.

    Non-ASCII is one token per character; ASCII is four characters per token,
    which is the friendliest ratio English prose reaches.
    """
    non_ascii = sum(1 for character in text if not character.isascii())
    return non_ascii + -(-(len(text) - non_ascii) // 4)


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "mixed",
    ["a私", "meeting at 3pm 転職について話した ", "план на यात्रा ", "ok ตกลง "],
    ids=["alternating", "english-japanese", "russian-hindi", "english-thai"],
)
def test_a_code_switching_main_is_estimated_at_or_above_the_real_cost(mixed):
    """The gap the per-subset floor left open.

    A main who writes half a sentence in one script and half in another is the
    ordinary case for the people this product is for, and it is the case a
    floor computed over one subset cannot see.
    """
    text = mixed * 300
    assert tokens_in(text) >= _real_floor(text)


def test_the_worst_measurement_on_the_table_is_covered():
    """1,600 Japanese characters against 1,600–2,400 real tokens."""
    assert tokens_in("私" * 1_600) >= 2_400


def test_latin_prose_is_still_estimated_high_rather_than_exactly():
    """The control. English runs nearer four characters per token, so three
    leaves headroom — erring high is the safe direction in every script."""
    text = SCRIPTS["latin"] * 40
    assert tokens_in(text) > len(text) / 4


@pytest.mark.ad19_guarantee
def test_the_same_text_in_two_scripts_is_not_priced_the_same():
    """The defect stated as a property.

    A constant tuned on Latin prose gives an identical answer for 300 Latin and
    300 CJK characters. Nothing but a per-script rule can fail this.
    """
    assert tokens_in("私" * 300) > tokens_in("a" * 300) * 2


def test_a_budget_refuses_a_japanese_prompt_it_could_not_afford():
    """The end-to-end consequence, through the port rather than the helper."""
    spec = DEFAULT_MODELS[Tier.CHEAP]
    latin = Generate(prompt=prompt(system=("s",), turns=("a" * 900,)), max_tokens=8)
    japanese = Generate(prompt=prompt(system=("s",), turns=("私" * 900,)), max_tokens=8)
    ceiling = estimate(
        spec, uncached_text=("s", "a" * 900), max_output_tokens=8
    ).micro_usd

    transport = FakeTransport(reply=text_reply("ok"))
    p = provider(transport, per_call=ceiling, per_pass=ceiling * 10)
    assert isinstance(asyncio.run(p.generate(latin)), Completion)
    assert asyncio.run(p.generate(japanese)) == Failure(
        Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET
    )


# ── matrix: cache write TTL ──────────────────────────────────────────────────


@pytest.mark.ad19_guarantee
def test_a_one_hour_cache_write_is_charged_at_the_one_hour_basis():
    """Matrix: *cache write TTL*. Not the five-minute one.

    Verified before the fix: a one-million-token hour-long write recorded
    6,250,000 against a real 10,000,000 — a 37.5% under-charge, on the write
    the nightly pass is the reason to use. The comment that justified it said
    the estimate had already charged the right basis; the estimate charges
    nothing, and only the settlement moves a total.
    """
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    reported = {"cache_creation_input_tokens": 1_000_000}
    hour = charged(spec, reported, ttl_basis=CACHE_WRITE_BASIS_1H).micro_usd
    five = charged(spec, reported, ttl_basis=CACHE_WRITE_BASIS_5M).micro_usd
    assert hour == spec.cache_write_micro_usd(
        1_000_000, ttl_basis=CACHE_WRITE_BASIS_1H
    )
    assert hour > five, "the hour-long write is priced as the cheap one"
    assert hour == five * 8 // 5


@pytest.mark.ad19_guarantee
def test_the_ttl_a_request_asked_for_is_the_ttl_it_is_charged_at():
    """The reply does not say which TTL wrote an entry, so the basis has to
    travel in from the request. Driven through the port, not the helper."""
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    stable = long_block(spec)
    reply = text_reply("ok", usage={"cache_creation_input_tokens": 100_000})

    spends = {}
    for ttl in (CacheTTL.FIVE_MINUTES, CacheTTL.ONE_HOUR):
        p = provider(FakeTransport(reply=reply))
        asyncio.run(p.generate(Generate(prompt=prompt(
            main_id=ASHA, system=(stable,), cache=Breakpoint(1, ttl=ttl)
        ))))
        spends[ttl] = p.ledger().spent_micro_usd
    assert spends[CacheTTL.ONE_HOUR] > spends[CacheTTL.FIVE_MINUTES]


def test_an_hour_long_write_is_estimated_at_the_hour_basis_too():
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    stable = (long_block(spec),)
    hour = estimate(spec, cached_text=stable, max_output_tokens=1,
                    ttl_basis=CACHE_WRITE_BASIS_1H).micro_usd
    five = estimate(spec, cached_text=stable, max_output_tokens=1,
                    ttl_basis=CACHE_WRITE_BASIS_5M).micro_usd
    assert hour > five


def test_a_caller_that_says_the_prefix_is_warm_is_priced_as_a_read():
    """``warm`` was never passed by the port, so every call was priced as a
    cold write and a warm nightly pass could be refused calls it could
    afford."""
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    stable = long_block(spec)
    cold = Generate(prompt=prompt(main_id=ASHA, system=(stable,),
                                  cache=Breakpoint(1)))
    warm = Generate(prompt=prompt(main_id=ASHA, system=(stable,),
                                  cache=Breakpoint(1, expect_warm=True)))
    p = provider(FakeTransport())
    assert p._estimate(warm.prompt, spec, max_output_tokens=1).micro_usd < (
        p._estimate(cold.prompt, spec, max_output_tokens=1).micro_usd
    )
    assert p._estimate(warm.prompt, spec, max_output_tokens=1).cache_read_tokens > 0


def test_a_prefix_is_priced_cold_unless_the_caller_says_otherwise():
    """The default is the expensive answer: on the first call of a pass nothing
    has paid for the entry yet."""
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    priced = estimate(spec, cached_text=(long_block(spec),), max_output_tokens=1)
    assert priced.cache_write_tokens > 0 and priced.cache_read_tokens == 0


# ── matrix: rejected credential ──────────────────────────────────────────────


@pytest.mark.ad19_guarantee
def test_a_rejected_key_is_not_authorised_and_is_not_a_content_refusal():
    """Matrix: *rejected credential*. Never a content refusal.

    The distinction the crisis caller diverges on: it fails toward *entering*
    when a provider declines the content, and must not when a key expired at
    three in the morning. ``Reason.NOT_AUTHORISED`` was declared and produced
    by nothing, so the two were indistinguishable.
    """
    out = asyncio.run(provider(
        FakeTransport(raises=ModelNotAuthorised("bad key"))
    ).generate(generate()))
    assert out == Failure(Kind.REFUSED, Reason.NOT_AUTHORISED)
    assert out != Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED)


@pytest.mark.ad19_guarantee
def test_a_rejected_key_reports_that_it_spent_nothing():
    """Matrix: *rejected credential*, and *what a failure cost*.

    ``Failure.spent`` read off ``Kind.REFUSED`` and said ``True`` for a request
    the provider threw away before billing a token — the one property that
    exists to let a metering caller tell a spend from a non-spend, telling it
    the opposite of the truth.
    """
    assert not Failure(Kind.REFUSED, Reason.NOT_AUTHORISED).spent
    assert Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED).spent


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "because, billed",
    [
        (Reason.TRANSPORT_FAILED, False),
        (Reason.NOT_AUTHORISED, False),
        (Reason.PER_CALL_BUDGET, False),
        (Reason.PER_PASS_BUDGET, False),
        (Reason.NO_SUCH_BATCH, False),
        (Reason.DUPLICATE_RESULT, False),
        (Reason.PROVIDER_REFUSED, True),
        (Reason.TRUNCATED, True),
        (Reason.NOT_A_LABEL, True),
        (Reason.NO_CONTENT, True),
        (Reason.INCOMPLETE, True),
        (Reason.UNREADABLE, True),
    ],
)
def test_every_reason_says_truthfully_whether_it_cost_anything(because, billed):
    """One row per reason, so a reason added later has to be classified rather
    than inheriting whichever answer its kind happens to give."""
    assert Failure(Kind.REFUSED, because).spent is billed


@pytest.mark.ad19_guarantee
def test_every_declared_reason_is_produced_by_some_path():
    """A closed set whose members are unreachable is decoration.

    ``NOT_AUTHORISED`` and ``NO_SUCH_BATCH`` were each declared and named
    exactly once in ``half/`` — at their own definition. This scans the package
    for a use of every member outside ``port.py``, so a reason that stops being
    produced fails by name.
    """
    produced: set[str] = set()
    for path in sorted(MODEL_DIR.rglob("*.py")):
        if path.name == "port.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "Reason"
            ):
                produced.add(node.attr)
    unreachable = sorted({r.name for r in Reason} - produced)
    assert not unreachable, (
        f"declared and produced by nothing: {unreachable}. A closed set whose "
        "members are unreachable is decoration, and two of these are the "
        "difference between a bad key and a content refusal"
    )


# ── matrix: unusable batch ───────────────────────────────────────────────────


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "status",
    [{}, {"processing_status": None}, {"processing_status": "vanished"},
     {"processing_status": 3}],
    ids=["missing", "null", "unknown", "not-text"],
)
def test_a_batch_state_this_build_cannot_read_stops_the_polling(status):
    """Matrix: *unusable batch*. Never forever-early.

    Anything that was not ``ended`` used to be reported as not-ready, so a lost
    or malformed submission was polled for ever with no way to express *this
    will not become ready*.
    """
    out = asyncio.run(provider(FakeTransport(status=status)).collect(
        Submission(batch_id="b_1")
    ))
    assert out == Failure(Kind.REFUSED, Reason.NO_SUCH_BATCH)
    assert not isinstance(out, Collected)


@pytest.mark.ad19_guarantee
def test_a_batch_the_provider_does_not_have_is_a_distinct_answer():
    out = asyncio.run(provider(
        FakeTransport(raises=ModelBatchNotFound("gone"))
    ).collect(Submission(batch_id="b_1")))
    assert out == Failure(Kind.REFUSED, Reason.NO_SUCH_BATCH)


@pytest.mark.parametrize("state", ["in_progress", "canceling"])
def test_a_batch_still_working_is_merely_early(state):
    """``canceling`` still ends, so it is not-ready rather than never-ready.
    Both states come from the provider's own vocabulary."""
    out = asyncio.run(provider(
        FakeTransport(status={"processing_status": state})
    ).collect(Submission(batch_id="b_1")))
    assert out == Collected(ready=False)


@pytest.mark.ad19_guarantee
def test_a_ready_but_empty_batch_does_not_read_as_not_ready():
    """``__len__`` made a completed empty batch falsy, so ``if collected:`` read
    it as early — the exact confusion the not-ready-is-an-answer design exists
    to prevent."""
    collected = Collected(ready=True)
    assert bool(collected) is True
    assert collected.ready and collected.count == 0


@pytest.mark.ad19_guarantee
def test_a_mid_stream_failure_keeps_the_rows_already_read():
    """Partial success was reported as total failure.

    A batch is the one operation where losing eight good results to the ninth
    row's fault is a whole nightly pass thrown away.
    """
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))

    class Interrupted(FakeTransport):
        async def batch_results(self, batch_id):
            yield {
                "custom_id": "one",
                "result": {"type": "succeeded", "message": label_reply("crisis")},
            }
            raise ModelUnavailable("the stream died")

    out = asyncio.run(provider(Interrupted()).collect(made))
    assert isinstance(out, Collected) and out.ready
    assert isinstance(out.outcomes["one"], Decision)
    assert out.missing(made) == ("two",)


def test_a_mid_stream_failure_before_any_row_is_still_a_failure():
    """Nothing was read, so there is nothing partial to report."""
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))

    class Dead(FakeTransport):
        async def batch_results(self, batch_id):
            raise ModelUnavailable("gone")
            yield  # pragma: no cover

    out = asyncio.run(provider(Dead()).collect(made))
    assert out == Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)


@pytest.mark.ad19_guarantee
def test_two_rows_claiming_one_reference_are_not_silently_merged():
    """Whichever arrived last used to win, losing one item's true outcome with
    nothing anywhere saying so."""
    made = asyncio.run(provider(FakeTransport()).submit(batch_items()))
    transport = FakeTransport(results=[
        {"custom_id": "one",
         "result": {"type": "succeeded", "message": label_reply("crisis")}},
        {"custom_id": "one",
         "result": {"type": "succeeded", "message": label_reply("ordinary")}},
    ])
    out = asyncio.run(provider(transport).collect(made))
    assert out.outcomes["one"] == Failure(Kind.MALFORMED, Reason.DUPLICATE_RESULT)


def test_a_batch_reference_is_validated_where_everything_else_is():
    for bad in ("", "   ", "x" * 65):
        with pytest.raises(ValueError):
            BatchItem(ref=bad, work=classify())


@pytest.mark.parametrize("bound", ["MAX_BATCH_ITEMS", "MAX_BATCH_BYTES"])
def test_a_batch_past_the_providers_own_limits_is_refused_before_the_wire(
    bound, monkeypatch
):
    """Nothing bounded a batch but cost, so the provider's own per-batch
    request-count and payload-size limits were met at the wire — after a whole
    nightly pass had been built. Inconsistent with ``_output_ceiling``, which
    refuses an over-long output "here rather than at the wire".

    The constants are lowered rather than the batch grown: a hundred thousand
    items is the number to *assert*, not the number to allocate.
    """
    from half.model import anthropic as implementation

    monkeypatch.setattr(implementation, bound, 1)
    transport = FakeTransport()
    items = [BatchItem(ref=f"r{i}", work=classify()) for i in range(2)]
    with pytest.raises(ValueError):
        asyncio.run(provider(transport).submit(items))
    assert transport.submitted == [], "an over-large batch was sent anyway"


def test_the_batch_bounds_are_the_providers_own():
    """Pinned to their values, both sides, so a bound that drifts fails."""
    from half.model.anthropic import MAX_BATCH_BYTES, MAX_BATCH_ITEMS

    assert MAX_BATCH_ITEMS == 100_000
    assert MAX_BATCH_BYTES == 256 * 1024 * 1024


def test_a_submission_lookup_is_indexed_rather_than_scanned():
    """Collection is called once per row; a linear scan made it quadratic in
    exactly the batch size the nightly pass is designed to produce."""
    made = Submission(
        batch_id="b",
        items=tuple(Submitted(ref=f"r{i}", tier="cheap") for i in range(500)),
    )
    assert made.item("r499").ref == "r499"
    assert made.item("nobody") is None


# ── matrix: narrow authority ─────────────────────────────────────────────────


@pytest.mark.ad19_guarantee
def test_the_classify_only_holder_has_no_public_attribute_at_all():
    """Matrix: *narrow authority*. Not only text.

    Verified before the fix: the object the crisis path holds exposed ``spend``
    and ``tiers``, so it could call ``spend.reset()`` and clear the whole
    pass's CAP-7 accounting, or read and re-key the tier table. Being unable to
    produce text is half of a narrow holder; the other half is authority, and
    an attribute *is* authority.
    """
    holder = provider(FakeTransport()).classifier()
    public = {name for name in dir(holder) if not name.startswith("_")}
    assert public == {"classify"}, (
        f"a classify-only holder exposes {sorted(public - {'classify'})}; the "
        "crisis path holds one of these"
    )


@pytest.mark.ad19_guarantee
def test_the_narrow_holders_cannot_reach_the_ledger_or_the_tiers():
    """The two specific reaches, named, so a rename does not quietly restore
    them."""
    for holder in (
        provider(FakeTransport()).classifier(),
        provider(FakeTransport()).generator(),
    ):
        assert not hasattr(holder, "spend")
        assert not hasattr(holder, "tiers")
        assert not hasattr(holder, "budget")


@pytest.mark.ad19_guarantee
def test_the_provider_hands_out_a_ledger_that_cannot_be_moved():
    """A caller still has to be able to meter and persist a pass. It gets a
    snapshot — a frozen value — rather than the ``Spend`` that can reset it."""
    p = provider(FakeTransport())
    snapshot = p.ledger()
    assert isinstance(snapshot, Ledger)
    with pytest.raises(Exception):
        snapshot.spent_micro_usd = 0  # frozen
    assert not hasattr(snapshot, "reset")


def test_the_authority_scan_would_see_an_attribute_being_added():
    """Non-vacuity for the surface case above."""

    class Widened(AnthropicClassifier):
        __slots__ = ()

        @property
        def spend(self):  # pragma: no cover - never read
            return self._spend

    holder = Widened(FakeTransport(), tiers=tiers(), budget=budget())
    assert {n for n in dir(holder) if not n.startswith("_")} != {"classify"}


# ── matrix: ledger across restart ────────────────────────────────────────────


@pytest.mark.ad19_guarantee
def test_the_pass_total_survives_a_restart_the_way_the_submission_does():
    """Matrix: *ledger across restart*. Not a fresh budget.

    ``Submission`` is deliberately durable so the evening's batch is collected
    in the morning (AD-9). A ledger that resets on restart while the batch it
    paid for survives is not a ceiling: a crash between submission and dawn
    handed the next pass a full budget with committed work unaccounted.
    """
    first = provider(FakeTransport())
    made = asyncio.run(first.submit(batch_items()))
    assert isinstance(made, Submission)
    assert made.committed_micro_usd > 0

    # The two values a caller persists together.
    saved_ledger = first.ledger().to_json()
    saved_batch = made.to_json()
    del first

    # A different process.
    restored = Spend.restored(Ledger.from_json(saved_ledger))
    assert restored.spent_micro_usd == made.committed_micro_usd

    second = AnthropicProvider(
        FakeTransport(), tiers=tiers(), spend=restored
    )
    assert second.ledger().spent_micro_usd == made.committed_micro_usd
    assert Submission.from_json(saved_batch).committed_micro_usd == (
        made.committed_micro_usd
    )


def test_a_restored_ledger_still_refuses_what_the_pass_can_no_longer_afford():
    """The point of restoring it."""
    spec = DEFAULT_MODELS[Tier.CHEAP]
    one = estimate(
        spec, uncached_text=("stable", "hello"),
        max_output_tokens=spec.default_max_tokens,
    ).micro_usd
    spent = Ledger(
        per_call_micro_usd=one, per_pass_micro_usd=one, spent_micro_usd=one, calls=1
    )
    p = AnthropicProvider(
        FakeTransport(), tiers=tiers(), spend=Spend.restored(spent)
    )
    assert asyncio.run(p.generate(generate())) == Failure(
        Kind.OVER_BUDGET, Reason.PER_PASS_BUDGET
    )


def test_a_ledger_round_trips_to_the_same_bytes():
    ledger = Ledger(
        per_call_micro_usd=10, per_pass_micro_usd=100, spent_micro_usd=7, calls=2
    )
    assert Ledger.from_json(ledger.to_json()) == ledger


@pytest.mark.parametrize(
    "raw", ['[]', '{}', '{"per_call_micro_usd": -1}',
            '{"per_call_micro_usd": 1, "per_pass_micro_usd": 1, '
            '"spent_micro_usd": 1, "calls": "two"}'],
)
def test_an_unreadable_ledger_is_refused_rather_than_half_read(raw):
    with pytest.raises(ValueError):
        Ledger.from_json(raw)


def test_a_snapshot_does_not_count_a_call_that_never_finished():
    """A reservation held when the process died is work nobody received."""
    spend = Spend(budget())
    spend.admit(Estimate(micro_usd=500))
    assert spend.snapshot().spent_micro_usd == 0


# ── matrix: wire shape, against the documented contract ──────────────────────
#
# Every assertion in this section reads the SDK's own typed parameters rather
# than the payload the renderer just produced. Reading back what the renderer
# wrote proves the renderer is self-consistent and nothing about whether the
# request is valid — and the Code Map made loading the provider documentation
# a precondition of writing this port, which has to reach the tests too.


def _literals(typed_dict, field) -> set[str]:
    """The string members of a TypedDict field's ``Literal``, resolved."""
    hints = typing.get_type_hints(typed_dict)
    found: set[str] = set()

    def walk(annotation):
        for argument in typing.get_args(annotation):
            if isinstance(argument, str):
                found.add(argument)
            else:
                walk(argument)

    walk(hints[field])
    return found


@pytest.mark.ad19_guarantee
def test_every_key_a_rendered_request_carries_is_one_the_sdk_declares():
    """Matrix: *wire shape*. Not against the renderer.

    A key the provider does not accept is a 400, and a 400 is not a
    degradation — it fails the call. This is the assertion that would have
    caught one.
    """
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    declared = set(MessageCreateParamsNonStreaming.__annotations__)
    for spec in DEFAULT_MODELS.values():
        for payload in (
            render_generate(generate(main_id=_a_main_on(spec)), spec),
            render_classify(classify(main_id=_a_main_on(spec)), spec),
        ):
            undeclared = set(payload) - declared
            assert not undeclared, f"{spec.model}: {sorted(undeclared)}"


def _a_main_on(spec) -> str:
    return VIDIT if spec is DEFAULT_MODELS[Tier.CHEAP] else ASHA


@pytest.mark.ad19_guarantee
def test_the_cache_marker_matches_the_sdk_s_own_cache_control_type():
    """The shape AD-19's whole cost model rides on, checked against the type
    the SDK declares for it rather than against what we wrote."""
    from anthropic.types import CacheControlEphemeralParam

    declared = set(CacheControlEphemeralParam.__annotations__)
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    stable = (long_block(spec),)
    for ttl in (CacheTTL.FIVE_MINUTES, CacheTTL.ONE_HOUR):
        payload = render_generate(
            Generate(prompt=prompt(main_id=ASHA, system=stable,
                                   cache=Breakpoint(1, ttl=ttl))),
            spec,
        )
        marker = payload["system"][0]["cache_control"]
        assert set(marker) <= declared, sorted(set(marker) - declared)
        assert marker["type"] in _literals(CacheControlEphemeralParam, "type")
        if "ttl" in marker:
            assert marker["ttl"] in _literals(CacheControlEphemeralParam, "ttl")


@pytest.mark.ad19_guarantee
def test_every_ttl_this_port_offers_is_one_the_sdk_accepts():
    """The enum on our side and the Literal on theirs, compared directly."""
    from anthropic.types import CacheControlEphemeralParam

    assert {ttl.value for ttl in CacheTTL} <= _literals(
        CacheControlEphemeralParam, "ttl"
    )


@pytest.mark.ad19_guarantee
def test_the_thinking_parameter_matches_the_adaptive_config_the_sdk_declares():
    """The parameter that is a 400 in its old shape.

    Asserted against ``ThinkingConfigAdaptiveParam`` — which is also where
    ``budget_tokens`` provably is not.
    """
    from anthropic.types import ThinkingConfigAdaptiveParam

    declared = set(ThinkingConfigAdaptiveParam.__annotations__)
    assert "budget_tokens" not in declared
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    thinking = render_generate(generate(main_id=ASHA), spec)["thinking"]
    assert set(thinking) <= declared
    assert thinking["type"] in _literals(ThinkingConfigAdaptiveParam, "type")


@pytest.mark.ad19_guarantee
def test_every_effort_this_port_sends_is_one_the_sdk_accepts():
    from anthropic.types import OutputConfigParam
    from half.model.tier import EFFORTS

    accepted = _literals(OutputConfigParam, "effort")
    assert set(EFFORTS) == accepted, "the port's effort levels have drifted"
    assert CLASSIFY_EFFORT in accepted
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    for payload in (
        render_generate(generate(main_id=ASHA), spec),
        render_classify(classify(main_id=ASHA), spec),
    ):
        assert payload["output_config"]["effort"] in accepted
        assert set(payload["output_config"]) <= set(
            OutputConfigParam.__annotations__
        )


@pytest.mark.ad19_guarantee
def test_the_label_schema_matches_the_json_output_format_the_sdk_declares():
    from anthropic.types import JSONOutputFormatParam

    spec = DEFAULT_MODELS[Tier.FRONTIER]
    fmt = render_classify(classify(main_id=ASHA), spec)["output_config"]["format"]
    assert set(fmt) <= set(JSONOutputFormatParam.__annotations__)
    assert fmt["type"] in _literals(JSONOutputFormatParam, "type")


@pytest.mark.ad19_guarantee
def test_the_batch_request_vocabulary_is_the_sdk_s_own():
    from anthropic.types.messages.batch_create_params import Request

    transport = FakeTransport()
    asyncio.run(provider(transport).submit(batch_items()))
    declared = set(Request.__annotations__)
    for request in transport.submitted[0]:
        assert set(request) == declared, sorted(set(request) ^ declared)


@pytest.mark.ad19_guarantee
def test_the_batch_states_this_build_knows_are_the_sdk_s_own():
    """Every state the provider can report is classified. A state added to the
    SDK that this build silently treated as *early* is a caller polling for
    ever."""
    import typing as _typing

    from anthropic.types.messages import MessageBatch
    from half.model.anthropic import BATCH_ENDED, BATCH_PENDING

    declared = set(
        _typing.get_args(MessageBatch.model_fields["processing_status"].annotation)
    )
    assert BATCH_PENDING | {BATCH_ENDED} == declared, (
        f"unclassified batch states: {sorted(declared ^ (BATCH_PENDING | {BATCH_ENDED}))}"
    )


@pytest.mark.ad19_guarantee
def test_every_stop_reason_the_sdk_declares_is_handled():
    """The whitelist, against the provider's own list.

    ``pause_turn``, ``tool_use`` and ``model_context_window_exceeded`` were all
    treated as complete answers, so a paused turn reached a main looking like
    the whole of what Half had to say.
    """
    from anthropic.types import StopReason
    from half.model.anthropic import COMPLETE_STOPS

    declared = {a for a in typing.get_args(StopReason) if isinstance(a, str)}
    assert COMPLETE_STOPS <= declared
    for stop in declared - COMPLETE_STOPS:
        out = asyncio.run(provider(
            FakeTransport(reply=text_reply("something", stop=stop))
        ).generate(generate()))
        assert isinstance(out, Failure), f"{stop} was treated as a finished reply"


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "stop", ["pause_turn", "tool_use", "model_context_window_exceeded",
             None, 3, "a_reason_from_next_year"],
    ids=["paused", "tool-use", "context-exceeded", "null", "not-text", "future"],
)
def test_an_unfinished_reply_is_never_delivered_as_a_whole_answer(stop):
    reply = {
        "content": [{"type": "text", "text": "half of a thought"}],
        "stop_reason": stop,
        "usage": {},
    }
    out = asyncio.run(provider(FakeTransport(reply=reply)).generate(generate()))
    assert out == Failure(Kind.MALFORMED, Reason.INCOMPLETE)


def test_a_finished_reply_on_either_ending_is_delivered():
    for stop in ("end_turn", "stop_sequence"):
        out = asyncio.run(provider(
            FakeTransport(reply=text_reply("done", stop=stop))
        ).generate(generate()))
        assert isinstance(out, Completion)


@pytest.mark.ad19_guarantee
def test_every_model_this_build_names_is_one_the_sdk_knows():
    """The tier table, against the SDK's own model list.

    A typo in a model id is a 404 on the first real call and nothing before it.
    """
    from anthropic.types import Model

    known: set[str] = set()

    def walk(annotation):
        for argument in typing.get_args(annotation):
            if isinstance(argument, str):
                known.add(argument)
            else:
                walk(argument)

    walk(Model)
    for tier, spec in DEFAULT_MODELS.items():
        assert spec.model in known, f"{tier}: {spec.model} is not a model the SDK knows"


@pytest.mark.ad19_guarantee
def test_the_shipped_model_table_is_pinned_to_its_values():
    """Absolute, not relational.

    The first version asserted only ``frontier < cheap`` for the cache minimum,
    so a wrong absolute value could not fail — while the README claims every
    threshold in this tree is pinned to its value. These are the numbers the
    free tier's cost model is computed from, and each is silently wrong in a
    direction nobody sees: a cache minimum too low means a marker that never
    caches, and a price too low means a budget that does not bind.
    """
    cheap = DEFAULT_MODELS[Tier.CHEAP]
    assert cheap.model == "claude-haiku-4-5"
    assert cheap.input_micro_usd_per_mtok == 1_000_000       # $1.00 / MTok
    assert cheap.output_micro_usd_per_mtok == 5_000_000      # $5.00 / MTok
    assert cheap.cache_min_tokens == 4_096
    assert cheap.max_output_tokens == 64_000
    assert cheap.adaptive_thinking is False and cheap.effort is False

    frontier = DEFAULT_MODELS[Tier.FRONTIER]
    assert frontier.model == "claude-opus-5"
    assert frontier.input_micro_usd_per_mtok == 5_000_000    # $5.00 / MTok
    assert frontier.output_micro_usd_per_mtok == 25_000_000  # $25.00 / MTok
    assert frontier.cache_min_tokens == 512
    assert frontier.max_output_tokens == 128_000
    assert frontier.adaptive_thinking is True and frontier.effort is True

    # The cache minimum is **not monotonic across generations**, which is the
    # whole reason it is per tier: the newer model's is eight times smaller.
    assert frontier.cache_min_tokens * 8 == cheap.cache_min_tokens


def test_the_cache_economics_are_pinned_to_their_bases():
    from half.model.tier import (
        BATCH_BASIS, CACHE_READ_BASIS, CACHE_WRITE_BASIS_1H, CACHE_WRITE_BASIS_5M,
    )

    assert CACHE_READ_BASIS == 1_000       # 0.10x input
    assert CACHE_WRITE_BASIS_5M == 12_500  # 1.25x input
    assert CACHE_WRITE_BASIS_1H == 20_000  # 2.00x input
    assert BATCH_BASIS == 5_000            # half price


# ── the transport, and the translation nothing tested ────────────────────────


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "raised, expected",
    [
        ("APIConnectionError", ModelUnavailable),
        ("RateLimitError", ModelUnavailable),
        ("InternalServerError", ModelUnavailable),
        ("AuthenticationError", ModelNotAuthorised),
        ("PermissionDeniedError", ModelNotAuthorised),
        ("BadRequestError", ModelRequestInvalid),
    ],
)
def test_each_provider_exception_becomes_the_right_one_of_halfs_own(raised, expected):
    """``_translate`` had no tests at all, and the four-distinct-failures
    guarantee rested on it.

    Constructed exceptions and no key needed — the reason there was no excuse.
    """
    assert isinstance(_translate(_sdk_error(raised)), expected)


def _sdk_error(name: str) -> Exception:
    """One SDK exception of the named class, constructed offline."""
    import anthropic
    import httpx2

    cls = getattr(anthropic, name)
    request = httpx2.Request("POST", "https://example.invalid/v1/messages")
    if name == "APIConnectionError":
        return cls(request=request)
    status = {
        "RateLimitError": 429, "InternalServerError": 500,
        "AuthenticationError": 401, "PermissionDeniedError": 403,
        "BadRequestError": 400, "NotFoundError": 404,
    }[name]
    response = httpx2.Response(status, request=request)
    return cls("boom", response=response, body=None)


@pytest.mark.ad19_guarantee
def test_a_wrong_payload_key_is_a_build_mistake_and_not_a_transient_outage():
    """The defect that made a permanently broken request retryable for ever.

    The SDK raises ``TypeError`` for a keyword it does not accept, and the old
    fallback mapped anything unrecognised to ``ModelUnavailable``.
    """
    assert isinstance(_translate(TypeError("unexpected keyword")), ModelRequestInvalid)
    assert isinstance(_translate(ValueError("bad value")), ModelRequestInvalid)
    assert not isinstance(
        _translate(TypeError("unexpected keyword")), ModelUnavailable
    )


def test_a_not_found_is_a_missing_batch_on_a_batch_route_and_a_bad_model_elsewhere():
    assert isinstance(_translate(_sdk_error("NotFoundError"), batch=True),
                      ModelBatchNotFound)
    assert isinstance(_translate(_sdk_error("NotFoundError")), ModelRequestInvalid)


def test_a_translated_fault_carries_no_message_from_the_provider():
    """A provider's error text can quote the request that caused it (AD-22)."""
    quoted = "the main said: I want to stop"
    for name in ("BadRequestError", "AuthenticationError", "RateLimitError"):
        error = _sdk_error(name)
        error.args = (quoted,)
        assert quoted not in str(_translate(error))


@pytest.mark.ad19_guarantee
def test_the_transport_speaks_the_sdk_and_returns_plain_mappings():
    """``SDKTransport`` had no tests either. A fake client needs no key and no
    network, and it is what proves the four methods call what they claim to."""

    class FakeMessage:
        def __init__(self, data):
            self._data = data

        def to_dict(self):
            return self._data

    class FakeBatches:
        def __init__(self):
            self.created = None

        async def create(self, *, requests):
            self.created = requests
            return FakeMessage({"id": "msgbatch_x"})

        async def retrieve(self, batch_id):
            return FakeMessage({"processing_status": "ended", "id": batch_id})

        async def results(self, batch_id):
            async def rows():
                yield FakeMessage({"custom_id": "one"})

            return rows()

    class FakeMessages:
        def __init__(self):
            self.batches = FakeBatches()
            self.seen = None

        async def create(self, **payload):
            self.seen = payload
            return FakeMessage({"content": [], "stop_reason": "end_turn"})

    transport = SDKTransport(FAKE_KEY)
    fake = FakeMessages()
    transport._client = type("C", (), {"messages": fake})()

    assert asyncio.run(transport.message({"model": "m", "max_tokens": 1})) == {
        "content": [], "stop_reason": "end_turn",
    }
    assert fake.seen == {"model": "m", "max_tokens": 1}
    assert asyncio.run(transport.batch_create([{"custom_id": "one"}]))["id"] == (
        "msgbatch_x"
    )
    assert asyncio.run(transport.batch_status("b"))["processing_status"] == "ended"

    async def drain():
        return [row async for row in transport.batch_results("b")]

    assert asyncio.run(drain()) == [{"custom_id": "one"}]


def test_the_transport_translates_rather_than_leaking_the_sdk_s_own_type():
    class Exploding:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**payload):
                raise _sdk_error("RateLimitError")

    transport = SDKTransport(FAKE_KEY)
    transport._client = Exploding()
    with pytest.raises(ModelUnavailable):
        asyncio.run(transport.message({}))


# ── classify, which is the operation the crisis caller holds ─────────────────
#
# The four failures were proven distinct only on `generate`. That is the wrong
# operation to prove them on: the one a crisis caller holds is `classify`.


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "make, expected",
    [
        (
            lambda: provider(FakeTransport(raises=ModelUnavailable("down"))),
            Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
        ),
        (
            lambda: provider(FakeTransport(raises=ModelRefused("no"))),
            Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED),
        ),
        (
            lambda: provider(FakeTransport(raises=ModelNotAuthorised("key"))),
            Failure(Kind.REFUSED, Reason.NOT_AUTHORISED),
        ),
        (
            lambda: provider(FakeTransport(), per_call=1, per_pass=1),
            Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET),
        ),
        (
            lambda: provider(FakeTransport(
                reply={"content": [], "stop_reason": "end_turn", "usage": {}}
            )),
            Failure(Kind.MALFORMED, Reason.NO_CONTENT),
        ),
    ],
    ids=["unavailable", "refused", "not-authorised", "over-budget", "malformed"],
)
def test_every_failure_is_reported_distinctly_on_the_classify_path_too(make, expected):
    out = asyncio.run(make().classify(classify()))
    assert out == expected


def test_an_over_budget_classification_sends_nothing():
    transport = FakeTransport()
    out = asyncio.run(
        provider(transport, per_call=1, per_pass=1).classify(classify())
    )
    assert out == Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET)
    assert transport.sent == []


# ── the remaining cost-correctness repairs ───────────────────────────────────


@pytest.mark.ad19_guarantee
def test_a_completed_call_never_advances_the_ledger_by_nothing():
    """``charged`` yielded zero when a reply omitted or mis-typed its usage, so
    completed calls advanced the pass total by nothing and the ceiling never
    bound."""
    p = provider(FakeTransport(reply={
        "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
    }))
    out = asyncio.run(p.generate(generate()))
    assert isinstance(out, Completion)
    assert p.ledger().spent_micro_usd > 0, "a completed call cost nothing"


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "usage",
    [{}, None, {"input_tokens": "lots"}, {"input_tokens": -5},
     {"input_tokens": 10 ** 18}, {"output_tokens": True}],
    ids=["missing", "null", "not-a-number", "negative", "absurd", "bool"],
)
def test_an_unbelievable_usage_block_charges_the_reservation_and_not_itself(usage):
    """A provider-reported absurd count used to charge without bound, so one
    reply could silently refuse the rest of a pass."""
    spec = DEFAULT_MODELS[Tier.CHEAP]
    charged_usage = charged(spec, usage or {}, floor_micro_usd=777)
    assert charged_usage.micro_usd == 777


def test_a_believable_usage_block_is_charged_as_reported():
    spec = DEFAULT_MODELS[Tier.CHEAP]
    usage = charged(spec, {"input_tokens": 1_000_000, "output_tokens": 0},
                    floor_micro_usd=1)
    assert usage.micro_usd == spec.input_micro_usd_per_mtok


def test_a_negative_price_is_refused_where_a_deployment_writes_it():
    """An unvalidated deployment table produced negative estimates, and every
    budget admits a negative estimate."""
    with pytest.raises(BudgetError):
        ModelSpec(
            model="claude-opus-5",
            input_micro_usd_per_mtok=-1,
            output_micro_usd_per_mtok=1,
            default_max_tokens=1,
            max_output_tokens=1,
            cache_min_tokens=1,
            adaptive_thinking=True,
            effort=True,
            structured_output=True,
        )


@pytest.mark.ad19_guarantee
def test_the_batch_path_uses_the_same_admission_as_a_single_call():
    """Two copies of the ceiling comparison is the drift this module's own
    ``ceil_div`` docstring warns about.

    Asserted structurally: nothing in the batch path compares against a budget
    field itself; every admission goes through ``Spend.admit``.
    """
    tree = ast.parse((MODEL_DIR / "anthropic.py").read_text(encoding="utf-8"))
    reached: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in (
            "per_call_micro_usd", "per_pass_micro_usd",
        ):
            reached.append(f"anthropic.py:{node.lineno} {node.attr}")
    assert not reached, (
        f"the implementation compares against a budget field directly: "
        f"{reached}. Admission belongs to Spend.admit, once"
    )


# ── the model-name scan, widened ─────────────────────────────────────────────


def _names_a_model(tree: ast.AST) -> list[str]:
    """Every place this module writes a model down, in any spelling.

    Stated as *"the ``model`` key may only ever be an attribute of a spec"*
    rather than as a list of forbidden strings — that covers spellings nobody
    has invented yet, including the non-Anthropic name the second
    implementation AD-19 defers will arrive with.

    Four routes, and the fourth is round 2's: a **call**.
    ``payload.setdefault("model", …)`` is the idiom used two lines from the
    renderer, and ``create(model=…)`` is what an SDK call site reaches for.
    Neither is a ``Dict`` or an ``Assign``, and none of the seven spellings the
    first version was tested against was a call.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        # `payload["model"] = <anything but spec.model>`
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "model"
                    and not _is_spec_model(node.value)
                ):
                    found.append(f"line {node.lineno}: assigned")
        # `{"model": <anything but spec.model>}`
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "model"
                    and not _is_spec_model(value)
                ):
                    found.append(f"line {node.lineno}: literal")
        if isinstance(node, ast.Call):
            # `p.setdefault("model", x)`, `p.__setitem__("model", x)`
            for position, argument in enumerate(node.args):
                if (
                    isinstance(argument, ast.Constant)
                    and argument.value == "model"
                    and not all(
                        _is_spec_model(rest) for rest in node.args[position + 1:]
                    )
                ):
                    found.append(f"line {node.lineno}: call argument")
            # `create(model=x)`
            for keyword in node.keywords:
                if keyword.arg == "model" and not _is_spec_model(keyword.value):
                    found.append(f"line {node.lineno}: keyword")
        # any string that looks like a vendor's model id
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _looks_like_a_model(node.value):
                found.append(f"line {node.lineno}: {node.value}")
    return found


@pytest.mark.ad19_guarantee
def test_no_call_site_names_a_model_in_any_spelling():
    """The scan matched ``claude-`` prefixed literals only, so a concatenation,
    an environment lookup, a vendor prefix or any non-Anthropic name passed —
    and a non-Anthropic name is exactly what the second implementation brings.
    Round 2 added the call route.
    """
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        if path.name == "tier.py" and path.parent.name == "model":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.relative_to(ROOT)} {where}" for where in _names_a_model(tree)
        ]
    assert not offenders, (
        f"a model is named outside the tier table: {offenders}. The tier "
        "travels with the main (AD-20)"
    )


#: Vendor prefixes a model identifier is built from. Deliberately not only
#: Anthropic's: the second implementation AD-19 defers arrives with somebody
#: else's name, and a guard that only knows this vendor would not see it.
MODEL_PREFIXES = (
    "claude-", "gpt-", "gemini-", "llama-", "mistral-", "command-",
    "us.anthropic.", "anthropic.claude",
)


def _looks_like_a_model(value: str) -> bool:
    return any(value.startswith(prefix) for prefix in MODEL_PREFIXES)


def _is_spec_model(node: ast.expr) -> bool:
    """``spec.model`` and nothing else."""
    return isinstance(node, ast.Attribute) and node.attr == "model"


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "bypass",
    [
        'def f(): return {"model": "claude-opus-5"}',
        'def f(): return {"model": "gpt-5"}',
        'def f(): return {"model": "us.anthropic.claude-opus-5"}',
        'def f(p): p["model"] = "claude-haiku-4-5"',
        'def f(os): return {"model": os.environ["MODEL"]}',
        'def f(): return {"model": "claude-" + "opus-5"}',
        'MODEL = "gemini-3-pro"',
    ],
    ids=["literal", "other-vendor", "bedrock-prefix", "assigned", "from-env",
         "concatenated", "module-constant"],
)
def test_the_model_name_scan_sees_each_spelling(bypass, tmp_path):
    """Non-vacuity, one spelling at a time. Four of these walked past the first
    version of this scan, and the call route walked past the second."""
    path = tmp_path / "bypass.py"
    path.write_text(bypass + "\n", encoding="utf-8")
    assert _names_a_model(ast.parse(path.read_text(encoding="utf-8"))), (
        f"the scan does not see:\n{bypass}"
    )


def test_the_model_name_scan_does_not_fire_on_the_renderer_itself(tmp_path):
    """The false positive that matters: ``payload["model"] = spec.model`` is
    the one way a model may reach a request, and a scan that forbade it would
    have nowhere left to put the tier table's answer."""
    path = tmp_path / "fine.py"
    path.write_text(
        'def f(payload, spec):\n'
        '    payload["model"] = spec.model\n'
        '    payload.setdefault("model", spec.model)\n'
        '    return {"model": spec.model}\n',
        encoding="utf-8",
    )
    assert not _names_a_model(ast.parse(path.read_text(encoding="utf-8")))


# ── the wiring that used to be prose (AD-11, AD-20) ──────────────────────────


@pytest.mark.ad19_guarantee
def test_the_key_comes_from_the_secret_store_as_a_code_path(tmp_path):
    """``half/model/`` never imported ``half.secrets``; ``SecretStore`` appeared
    only in docstrings, so AD-11 was a claim rather than a path.

    One name for the key, in one place, so the five consumer stories cannot
    each invent a different one.
    """
    from half.secrets import FileSecretStore

    mains_root = tmp_path / "mains"
    (mains_root / VIDIT).mkdir(parents=True)
    secrets = FileSecretStore.beside(mains_root)
    secrets.put(VIDIT, MODEL_KEY, FAKE_KEY)

    assert isinstance(SDKTransport.from_secrets(secrets, VIDIT), SDKTransport)
    with pytest.raises(ModelMisconfigured):
        SDKTransport.from_secrets(secrets, ASHA)

    imports = _imports_of(MODEL_DIR / "anthropic_transport.py")
    assert any(i.startswith("half.secrets") for i in imports)


@pytest.mark.ad19_guarantee
def test_a_tier_reaches_the_port_from_configuration(tmp_path):
    """``half/config.py`` gained no tier field, so AD-20 stopped at the port's
    own door: nothing said where a deployment writes a main's tier down."""
    from half.config import TIERS_ENV, load

    config = load({
        "HALF_MAINS": f"111:{VIDIT},222:{ASHA}",
        TIERS_ENV: f"{VIDIT}:cheap,{ASHA}:frontier",
        "HALF_ROOT": str(tmp_path),
    })
    table = Tiers.parse(config.tiers)
    assert table.spec_for(VIDIT).model == DEFAULT_MODELS[Tier.CHEAP].model
    assert table.spec_for(ASHA).model == DEFAULT_MODELS[Tier.FRONTIER].model


def test_a_tier_for_somebody_who_is_not_a_main_is_refused(tmp_path):
    """A tier for nobody is a typo, and the quiet version of it is the real
    main still having no tier at all."""
    from half.config import TIERS_ENV, load

    with pytest.raises(ValueError):
        load({"HALF_MAINS": f"111:{VIDIT}", TIERS_ENV: "ghost:cheap"})


@pytest.mark.ad19_guarantee
def test_one_parser_reads_both_halves_of_the_configuration():
    """``tier.py`` had a copy of ``half.config``'s parser that had lost
    ``validate_main_id`` and the duplicate check, so a tier table accepted main
    ids the rest of the config refuses."""
    from half.config import parse_pairs

    with pytest.raises(UnknownTier):
        Tiers.parse("../escape:cheap")
    assert parse_pairs("a:b", what="X") == {"a": "b"}

    source = (MODEL_DIR / "tier.py").read_text(encoding="utf-8")
    assert "parse_pairs" in source, "the tier table has its own parser again"
    assert "def _split" not in source


# ═══════════════════════════════════════════════════════════════════════════
# Review round 2. The round-1 fixes interacted to make a new leak, and three
# guards were checked only where they already agreed with themselves.
# ═══════════════════════════════════════════════════════════════════════════


# ── a reservation is released on every path out ──────────────────────────────


def _under_the_minimum(main_id=VIDIT, *, spec=None):
    """A prompt whose stable prefix the tier will silently refuse to cache."""
    return Prompt(
        main_id=main_id,
        system=("short",),
        turns=(Turn(Role.USER, "hello"),),
        cache=Breakpoint(1),
    )


@pytest.mark.ad19_guarantee
def test_a_raise_before_the_request_is_built_does_not_leak_a_reservation():
    """Three round-1 fixes combining into a fourth defect.

    The cache-minimum refusal raises from the renderer; the renderer was called
    *after* ``admit`` reserved and outside any handler; and the ledger had just
    been made durable. Verified before the fix, and monotonic: reserved 524,
    then 1,048, then 1,572, with ``remaining`` never recovering. A caller
    retrying a mis-stated breakpoint drains the pass to zero, after which every
    honest call is refused ``PER_PASS_BUDGET`` with nothing sent.

    A ceiling that binds against money nobody spent is the same defect as one
    that does not bind, pointing the other way.
    """
    p = provider(FakeTransport())
    start = p._spend.remaining_micro_usd

    for _ in range(5):
        with pytest.raises(BreakpointError):
            asyncio.run(p.generate(Generate(prompt=_under_the_minimum())))

    assert p._spend.reserved_micro_usd == 0, "a raise held on to its reservation"
    assert p._spend.remaining_micro_usd == start, "the pass budget shrank"
    assert p.ledger().spent_micro_usd == 0

    # And the pass still works afterwards, which is what the leak destroyed.
    assert isinstance(asyncio.run(p.generate(generate())), Completion)


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "make",
    [
        lambda: ("generate", Generate(prompt=_under_the_minimum())),
        lambda: ("classify", Classify(prompt=_under_the_minimum(), labels=LABELS)),
        lambda: ("generate", Generate(prompt=prompt(main_id="nobody"))),
        lambda: ("generate", Generate(prompt=prompt(), max_tokens=10 ** 9)),
    ],
    ids=["cache-minimum-generate", "cache-minimum-classify", "unknown-tier",
         "output-ceiling"],
)
def test_no_raising_path_between_the_call_and_the_send_leaks(make):
    """Every other round-1 refusal that raises, checked for the same hole.

    The interaction is the lesson, not the single line: any refusal that raises
    after admission and before the send leaks, and round 1 added three of them.
    """
    operation, work = make()
    p = provider(FakeTransport())
    start = p._spend.remaining_micro_usd
    with pytest.raises(ModelError):
        asyncio.run(getattr(p, operation)(work))
    assert p._spend.reserved_micro_usd == 0
    assert p._spend.remaining_micro_usd == start


@pytest.mark.ad19_guarantee
def test_a_raise_partway_through_a_batch_releases_every_earlier_item():
    """``submit`` was the path that *did* release — and it did so by hand.

    Now all three hold, so the release is the control structure's rather than
    something each site has to remember. This is the case that fails if the
    ``ExitStack`` is unwound.
    """
    p = provider(FakeTransport())
    start = p._spend.remaining_micro_usd
    with pytest.raises(BreakpointError):
        asyncio.run(p.submit([
            BatchItem(ref="fine", work=classify()),
            BatchItem(ref="broken", work=Generate(prompt=_under_the_minimum())),
        ]))
    assert p._spend.reserved_micro_usd == 0
    assert p._spend.remaining_micro_usd == start


@pytest.mark.ad19_guarantee
def test_the_hold_gives_a_reservation_back_on_any_exit():
    """The mechanism, in one place, so a failure names the cause.

    A handler fixes the sites it is written at; a control structure fixes the
    class. This is the class.
    """
    spend = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))

    with pytest.raises(RuntimeError):
        with spend.hold(Estimate(micro_usd=50)) as admitted:
            assert isinstance(admitted, Reservation)
            assert spend.reserved_micro_usd == 50
            raise RuntimeError("anything at all")
    assert spend.reserved_micro_usd == 0 and spend.spent_micro_usd == 0

    # An early return releases too.
    def returns_early():
        with spend.hold(Estimate(micro_usd=50)) as held:
            return held

    returns_early()
    assert spend.reserved_micro_usd == 0

    # A settle inside the block is *not* undone on the way out.
    with spend.hold(Estimate(micro_usd=50)) as held:
        spend.settle(held, Usage(micro_usd=40))
    assert spend.spent_micro_usd == 40 and spend.reserved_micro_usd == 0


@pytest.mark.ad19_guarantee
def test_the_single_call_paths_reserve_nothing_until_the_request_is_built():
    """Structural: in both single-call paths the renderer is called *before*
    the admission, so the class of bug has nothing left to catch there.

    Read off the syntax tree rather than trusted, because the ordering is
    invisible in every behavioural test that does not raise.
    """
    tree = ast.parse((MODEL_DIR / "anthropic.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name not in ("classify", "generate"):
            continue
        lines = {}
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                if inner.func.id.startswith("render_"):
                    lines["render"] = inner.lineno
            if isinstance(inner, ast.Attribute) and inner.attr == "hold":
                lines["hold"] = inner.lineno
        if "render" in lines and "hold" in lines:
            assert lines["render"] < lines["hold"], (
                f"{node.name} reserves before it builds the request"
            )


# ── a reservation is exchangeable exactly once, by its issuer ────────────────


@pytest.mark.ad19_guarantee
def test_settling_one_reservation_twice_is_refused():
    """Measured before the fix on a 100/100 budget: spent 120, calls 2, for one
    call — and it persisted through ``snapshot()``.

    ``serial`` was documented as making a double settle detectable and was read
    nowhere in ``half/``; ``_release`` checked the type and clamped the
    subtraction at zero, which turned every misuse into a silently wrong pass
    total rather than a loud one.
    """
    spend = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    held = spend.admit(Estimate(micro_usd=50))
    spend.settle(held, Usage(micro_usd=60))
    with pytest.raises(BudgetError):
        spend.settle(held, Usage(micro_usd=60))
    assert spend.spent_micro_usd == 60 and spend.calls == 1


@pytest.mark.ad19_guarantee
def test_releasing_one_reservation_twice_is_refused():
    spend = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    held = spend.admit(Estimate(micro_usd=50))
    spend.release(held)
    with pytest.raises(BudgetError):
        spend.release(held)
    assert spend.reserved_micro_usd == 0


@pytest.mark.ad19_guarantee
def test_a_reservation_from_another_ledger_is_refused():
    """It settled clean before — one pass's accounting moved by another's."""
    mine = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    theirs = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    foreign = theirs.admit(Estimate(micro_usd=50))
    with pytest.raises(BudgetError):
        mine.settle(foreign, Usage(micro_usd=50))
    assert mine.spent_micro_usd == 0 and mine.calls == 0


@pytest.mark.ad19_guarantee
def test_a_hand_constructed_reservation_cannot_free_the_ledger():
    """The worst of the four: ``max(0, …)`` drove the outstanding total to zero
    and the ledger then admitted 180 committed against a 100 ceiling."""
    spend = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    spend.admit(Estimate(micro_usd=90))
    with pytest.raises(BudgetError):
        spend.release(Reservation(micro_usd=10 ** 9, serial=999))
    assert spend.reserved_micro_usd == 90
    assert spend.admit(Estimate(micro_usd=90)) is Reason.PER_PASS_BUDGET


@pytest.mark.ad19_guarantee
def test_a_reservation_whose_amount_was_altered_is_refused():
    """The serial is right and the figure is not — a mutated value object. The
    ledger's own record is the authority."""
    spend = Spend(Budget(per_call_micro_usd=100, per_pass_micro_usd=100))
    held = spend.admit(Estimate(micro_usd=50))
    forged = Reservation(micro_usd=1, serial=held.serial)
    with pytest.raises(BudgetError):
        spend.settle(forged, Usage(micro_usd=1))
    assert spend.reserved_micro_usd == 50, "the real reservation was dropped"


def test_the_issuance_record_is_what_reports_the_outstanding_total():
    spend = Spend(budget())
    first = spend.admit(Estimate(micro_usd=10))
    second = spend.admit(Estimate(micro_usd=20))
    assert spend.reserved_micro_usd == 30
    spend.release(first)
    assert spend.reserved_micro_usd == 20
    spend.settle(second, Usage(micro_usd=5))
    assert spend.reserved_micro_usd == 0 and spend.spent_micro_usd == 5


# ── the cache-minimum refusal, which nothing verified ────────────────────────


@pytest.mark.ad19_guarantee
def test_a_prefix_under_the_tiers_minimum_is_refused_at_the_renderer():
    """Round 1's own fix, unverified until now.

    ``if False:`` on the condition passed all 2,316 tests, because no test
    called ``render_prompt`` and every rendering case built its prefix from a
    helper that is always over the minimum. On the cheap tier that means any
    prefix under about four thousand tokens is billed at full input price on
    every call, with no error — the hidden breakpoint AD-19 forbids, wearing
    the clothes of an honoured one.
    """
    cheap = DEFAULT_MODELS[Tier.CHEAP]
    with pytest.raises(BreakpointError):
        render_prompt(_under_the_minimum(), cheap)


@pytest.mark.ad19_guarantee
def test_the_same_prefix_caches_on_one_tier_and_is_refused_on_the_other():
    """The per-tier property the whole design argues for.

    The minimum is **not monotonic across generations** — 512 on the frontier
    model against 4,096 on the cheap one — so a prompt that caches on one tier
    silently does not on the other with no code change at all. This is the case
    that pins it: one prefix, two tiers, two answers.
    """
    cheap = DEFAULT_MODELS[Tier.CHEAP]
    frontier = DEFAULT_MODELS[Tier.FRONTIER]

    # Sized between the two minimums, so it is the *tier* that decides.
    between = "cacheable prose. " * 500
    assert frontier.cache_min_tokens <= tokens_in(between) < cheap.cache_min_tokens

    middling = Prompt(
        main_id=VIDIT, system=(between,), turns=(Turn(Role.USER, "hi"),),
        cache=Breakpoint(1),
    )
    rendered = render_prompt(middling, frontier)
    assert "cache_control" in rendered["system"][0]
    with pytest.raises(BreakpointError):
        render_prompt(middling, cheap)


@pytest.mark.ad19_guarantee
def test_the_refusal_reaches_the_caller_through_the_port_as_well():
    """Through the operation, not only the helper — and it must not be turned
    into one of the four outcomes on the way. A breakpoint the provider would
    ignore is a build mistake, and those raise."""
    transport = FakeTransport()
    p = provider(transport)
    for operation, work in (
        ("generate", Generate(prompt=_under_the_minimum())),
        ("classify", Classify(prompt=_under_the_minimum(), labels=LABELS)),
    ):
        with pytest.raises(BreakpointError):
            asyncio.run(getattr(p, operation)(work))
    assert transport.sent == [], "an unplaceable breakpoint still sent a request"


def test_a_prefix_over_the_minimum_renders_the_marker():
    """The other side of the boundary, so the case above cannot pass by
    refusing everything."""
    frontier = DEFAULT_MODELS[Tier.FRONTIER]
    rendered = render_prompt(
        Prompt(main_id=ASHA, system=(long_block(frontier),),
               turns=(Turn(Role.USER, "hi"),), cache=Breakpoint(1)),
        frontier,
    )
    assert rendered["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_a_prompt_with_no_breakpoint_is_never_refused_for_being_short():
    """Nothing is claimed, so nothing is under a minimum."""
    cheap = DEFAULT_MODELS[Tier.CHEAP]
    rendered = render_prompt(
        Prompt(main_id=VIDIT, system=("short",), turns=(Turn(Role.USER, "hi"),)),
        cheap,
    )
    assert all("cache_control" not in block for block in rendered["system"])


# ── the wire shape, at the keys that carry the prompt ────────────────────────


@pytest.mark.ad19_guarantee
def test_every_message_matches_the_message_param_the_sdk_declares():
    """Matrix: *wire shape*, at the key the prompt actually travels in.

    Verified: renaming ``content`` to ``contents`` — a guaranteed 400 on every
    call the port makes — passed all 2,316 tests, because the scan compared
    ``set(payload)`` against the top-level parameters and nothing reached
    ``messages[i]``. The section's own premise is that reading back what the
    renderer wrote proves nothing about validity; it held precisely where it
    mattered most.
    """
    from anthropic.types import MessageParam

    declared = set(MessageParam.__annotations__)
    roles = _literals(MessageParam, "role")
    for spec in DEFAULT_MODELS.values():
        for payload in (
            render_generate(generate(main_id=_a_main_on(spec)), spec),
            render_classify(classify(main_id=_a_main_on(spec)), spec),
        ):
            for message in payload["messages"]:
                undeclared = set(message) - declared
                assert not undeclared, f"{spec.model}: {sorted(undeclared)}"
                assert {"role", "content"} <= set(message), sorted(message)
                assert message["role"] in roles
                assert isinstance(message["content"], str)


@pytest.mark.ad19_guarantee
def test_every_system_block_matches_the_text_block_param_the_sdk_declares():
    """The other guaranteed 400: ``{"type": "text", "text": …}`` renamed to
    ``{"type": "plaintext", "body": …}`` also passed all 2,316 tests.

    This is the block the cached prefix lives in, so a wrong key here is both a
    rejected call and the end of the free tier's cost model.
    """
    from anthropic.types import TextBlockParam

    declared = set(TextBlockParam.__annotations__)
    types = _literals(TextBlockParam, "type")
    spec = DEFAULT_MODELS[Tier.FRONTIER]
    payload = render_generate(
        Generate(prompt=prompt(main_id=ASHA, system=(long_block(spec), "volatile"),
                               cache=Breakpoint(1))),
        spec,
    )
    for block in payload["system"]:
        undeclared = set(block) - declared
        assert not undeclared, sorted(undeclared)
        assert {"type", "text"} <= set(block), sorted(block)
        assert block["type"] in types
        assert isinstance(block["text"], str)


@pytest.mark.ad19_guarantee
def test_a_batch_items_params_are_checked_as_deeply_as_an_inline_request():
    """A batch carries the same nested shapes, and a nightly pass is where a
    wrong key costs a whole night rather than one call."""
    from anthropic.types import MessageParam, TextBlockParam
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    transport = FakeTransport()
    asyncio.run(provider(transport).submit(batch_items()))
    for request in transport.submitted[0]:
        params = request["params"]
        assert set(params) <= set(MessageCreateParamsNonStreaming.__annotations__)
        for message in params["messages"]:
            assert set(message) <= set(MessageParam.__annotations__)
            assert {"role", "content"} <= set(message)
        for block in params.get("system", []):
            assert set(block) <= set(TextBlockParam.__annotations__)
            assert {"type", "text"} <= set(block)


# ── the model-name scan, at the call route ───────────────────────────────────


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "bypass",
    [
        'def f(p, spec): p.setdefault("model", "claude-opus-5")',
        'def f(p): p.update({"model": "gpt-5"})',
        'def f(c): c.messages.create(model="claude-opus-5", max_tokens=1)',
        'def f(p): p.__setitem__("model", "gemini-3-pro")',
    ],
    ids=["setdefault", "update", "keyword", "dunder-setitem"],
)
def test_the_model_name_scan_sees_the_call_route(bypass, tmp_path):
    """``payload.setdefault("model", …)`` is the idiom used two lines from the
    renderer, and none of the seven spellings the scan was tested against was a
    call. A keyword argument is the other one an SDK call site reaches for."""
    path = tmp_path / "bypass.py"
    path.write_text(bypass + "\n", encoding="utf-8")
    assert _names_a_model(ast.parse(path.read_text(encoding="utf-8"))), (
        f"the scan does not see:\n{bypass}"
    )


# ── the gate's own floor, which a floor cannot protect ───────────────────────


#: The cases every guarantee in this story rests on, by name.
#:
#: **A floor is the weakest of the three protections, and round 2 measured it.**
#: The `ad19_guarantee` gate collected 142 against a floor of 110 — and *every*
#: case it selects is a guarantee case, so the 32-case slack could only ever be
#: absorbed by deleting guarantees. Dropping the concurrency-binding case, the
#: reservation-counted case, both AD-30 fold cases, the narrow-authority
#: surface case, the seven-case non-Latin floor and the ledger-restart case
#: left guarantee at 129 and `ad19` at 245, both comfortably green. The step's
#: own reasoning only covered deleting all 142 at once.
#:
#: So the flagship cases are named here, the way `tests/test_loops.py` names
#: the guards its firewall rests on. Deleting one now fails *by name* rather
#: than by arithmetic, which is the protection a count cannot give.
GUARANTEES = (
    # The four the spec's change log says held under mutation and must keep
    # holding.
    "test_a_classify_only_holder_has_no_public_way_to_produce_text",
    "test_the_classifier_surface_scan_sees_a_generate_being_added",
    "test_no_failure_ever_carries_a_substituted_answer",
    "test_the_breakpoint_is_exactly_where_the_caller_put_it",
    "test_a_breakpoint_past_the_prompt_is_refused_and_never_clamped",
    # Round 1.
    "test_the_pass_ceiling_binds_when_calls_overlap",
    "test_a_reservation_is_counted_the_moment_it_is_taken",
    "test_a_non_latin_estimate_is_at_least_one_token_per_character",
    "test_no_log_call_in_the_model_package_can_carry_content",
    "test_the_log_content_scan_sees_each_way_a_completion_reaches_a_log",
    "test_the_classify_only_holder_has_no_public_attribute_at_all",
    "test_a_one_hour_cache_write_is_charged_at_the_one_hour_basis",
    "test_a_rejected_key_is_not_authorised_and_is_not_a_content_refusal",
    "test_every_declared_reason_is_produced_by_some_path",
    "test_every_reason_says_truthfully_whether_it_cost_anything",
    "test_a_batch_state_this_build_cannot_read_stops_the_polling",
    "test_the_pass_total_survives_a_restart_the_way_the_submission_does",
    "test_no_model_call_is_reachable_from_a_fold",
    "test_nothing_under_the_store_imports_the_model_port_at_all",
    "test_no_module_outside_the_tier_table_names_a_model",
    "test_every_stop_reason_the_sdk_declares_is_handled",
    "test_the_shipped_model_table_is_pinned_to_its_values",
    # Round 2.
    "test_a_raise_before_the_request_is_built_does_not_leak_a_reservation",
    "test_no_raising_path_between_the_call_and_the_send_leaks",
    "test_the_hold_gives_a_reservation_back_on_any_exit",
    "test_settling_one_reservation_twice_is_refused",
    "test_a_reservation_from_another_ledger_is_refused",
    "test_a_hand_constructed_reservation_cannot_free_the_ledger",
    "test_a_prefix_under_the_tiers_minimum_is_refused_at_the_renderer",
    "test_the_same_prefix_caches_on_one_tier_and_is_refused_on_the_other",
    "test_every_message_matches_the_message_param_the_sdk_declares",
    "test_every_system_block_matches_the_text_block_param_the_sdk_declares",
    "test_the_fold_reachability_scan_sees_each_spelling_of_the_import",
    "test_the_model_name_scan_sees_the_call_route",
    "test_a_code_switching_main_is_estimated_at_or_above_the_real_cost",
)


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize("name", GUARANTEES)
def test_every_guarantee_this_story_rests_on_still_exists(name):
    """Each named case is present, and still carries the guarantee marker.

    Two assertions, because the cheap way to lose one is not deletion: it is
    quietly unmarking it, which drops it out of the gate while leaving the
    function where a reviewer reading the diff would see it.
    """
    defined = {
        node.name: node
        for node in ast.walk(
            ast.parse(Path(__file__).read_text(encoding="utf-8"))
        )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert name in defined, (
        f"{name} is gone. It is one of the cases this story's guarantees rest "
        "on; if it genuinely belongs somewhere else, move the name too"
    )
    marks = {
        decorator.attr
        for decorator in ast.walk(defined[name])
        if isinstance(decorator, ast.Attribute)
    }
    assert "ad19_guarantee" in marks, f"{name} no longer carries the gate's marker"


def test_the_named_guarantees_are_the_gate_and_not_a_subset_of_a_subset():
    """The list must not itself become decoration.

    Every name in it has to be a real case in this file — a stale name is a
    guard that passes because nobody noticed it stopped pointing at anything.
    Asserted by the case above, one name at a time; this one pins that the list
    is big enough to be worth having and that it has no duplicates.
    """
    assert len(set(GUARANTEES)) == len(GUARANTEES)
    assert len(GUARANTEES) >= 30
