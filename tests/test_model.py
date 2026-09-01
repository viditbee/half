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
from pathlib import Path

import pytest

from half.errors import (
    BreakpointError,
    BudgetError,
    ModelError,
    ModelRefused,
    ModelUnavailable,
    UnknownTier,
)
from half.model import budget as budget_mod
from half.model.anthropic import (
    CLASSIFY_MAX_TOKENS,
    AnthropicBatcher,
    AnthropicClassifier,
    AnthropicGenerator,
    AnthropicProvider,
    render_classify,
    render_generate,
)
from half.model.budget import Budget, Estimate, Spend, charged, estimate
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
from half.model.tier import DEFAULT_MODELS, Tier, Tiers

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
            lambda: provider(FakeTransport(reply={"content": []})),
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
        assert names <= {"ModelUnavailable", "ModelRefused", "ValueError",
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
    assert p.spend.spent_micro_usd == each * 2
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
    assert p.classifier().spend is p.spend
    assert p.generator().spend is p.spend
    assert p.batcher().spend is p.spend


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
    spend.charge(Usage(micro_usd=500))
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
    payload = render_generate(
        Generate(prompt=prompt(system=("a", "b", "c"), cache=Breakpoint(after))),
        DEFAULT_MODELS[Tier.CHEAP],
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
    five = render_generate(
        Generate(prompt=prompt(cache=Breakpoint(1))), DEFAULT_MODELS[Tier.CHEAP]
    )
    assert five["system"][0]["cache_control"] == {"type": "ephemeral"}

    hour = render_generate(
        Generate(prompt=prompt(cache=Breakpoint(1, ttl=CacheTTL.ONE_HOUR))),
        DEFAULT_MODELS[Tier.CHEAP],
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
def test_no_request_ends_with_an_assistant_prefill():
    """A last-assistant-turn prefill is refused on every current model.

    The port has no shape that produces one — the turns come from the caller —
    so this pins that the renderer does not add one of its own.
    """
    payload = render_generate(
        Generate(
            prompt=Prompt(
                main_id=VIDIT,
                turns=(Turn(Role.USER, "hi"), Turn(Role.ASSISTANT, "there")),
            )
        ),
        DEFAULT_MODELS[Tier.CHEAP],
    )
    assert payload["messages"][-1]["role"] == "assistant"  # the caller's, not ours
    assert len(payload["messages"]) == 2


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
    assert p.spend.spent_micro_usd == 0
    asyncio.run(p.submit(batch_items()))
    assert p.spend.spent_micro_usd > 0


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
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
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


def test_the_fold_reachability_scan_sees_an_import_that_was_added(tmp_path):
    """Non-vacuity: the scan must fail on the thing it forbids."""
    path = tmp_path / "bypass.py"
    path.write_text("from half.model.port import Prompt\n", encoding="utf-8")
    assert any(i.startswith("half.model") for i in _imports_of(path))


# ── matrix: secrets and content (AD-11, AD-22) ───────────────────────────────


@pytest.mark.ad19_guarantee
def test_no_key_material_reaches_the_store_tree_logs_or_errors(tmp_path, caplog):
    """Matrix: *secrets*. Asserted byte-wise.

    The acceptance criterion, over the three places a key actually escapes to:
    a store tree that is exportable and replayable (AD-11), a log line, and the
    text of an error somebody prints.
    """
    from half.model.anthropic import SDKTransport

    caplog.set_level(logging.DEBUG)
    store_root = tmp_path / "main"
    store_root.mkdir()

    transport = SDKTransport(FAKE_KEY)
    p = AnthropicProvider(transport, tiers=tiers(), budget=budget())

    surfaces = [repr(transport), repr(p), repr(p.spend), repr(p.tiers)]
    for name in dir(transport):
        if not name.startswith("_"):
            surfaces.append(repr(getattr(transport, name, None)))

    with pytest.raises(ModelError) as raised:
        SDKTransport("")
    surfaces.append(str(raised.value))

    surfaces.append(caplog.text)
    for path in store_root.rglob("*"):
        if path.is_file():
            surfaces.append(path.read_text(encoding="utf-8", errors="replace"))

    leaked = [s for s in surfaces if FAKE_KEY in s]
    assert not leaked, "key material appeared where it must never appear (AD-11)"
    assert list(store_root.rglob("*")) == []


#: Names a log call must never be handed. Content-free means counts and closed
#: enums; a completion, a prompt or a main's words are none of those.
CONTENT_NAMES = {
    "text", "prompt", "system", "turns", "content", "completion", "payload",
    "reply", "message", "work", "claim", "label", "labels", "request",
}


@pytest.mark.ad19_guarantee
def test_no_log_call_in_the_model_package_can_carry_content():
    """Matrix: *content in logs*. AD-22.

    Structural, because a behavioural test cannot cover it: a log line carrying
    a completion breaks nothing, passes every other case in this file, and
    hands the most intimate dataset a person owns to an observability side
    channel.
    """
    offenders: list[str] = []
    for path in sorted(MODEL_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"
            ):
                continue
            for argument in node.args[1:] + [k.value for k in node.keywords]:
                names = {
                    n.attr if isinstance(n, ast.Attribute) else
                    n.id if isinstance(n, ast.Name) else ""
                    for n in ast.walk(argument)
                }
                bad = names & CONTENT_NAMES
                if bad:
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} {sorted(bad)}"
                    )
    assert not offenders, f"a log line could carry content (AD-22): {offenders}"


def test_the_log_content_scan_sees_a_completion_being_logged(tmp_path):
    """Non-vacuity for the scan above."""
    path = tmp_path / "bypass.py"
    path.write_text(
        "import logging\nlogger = logging.getLogger(__name__)\n"
        "def f(reply):\n    logger.info('got %s', reply.text)\n",
        encoding="utf-8",
    )
    found = set()
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"):
            for argument in node.args[1:]:
                found |= {
                    n.attr for n in ast.walk(argument) if isinstance(n, ast.Attribute)
                }
    assert found & CONTENT_NAMES


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
