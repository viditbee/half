"""The one implementation of the model port, transport injected (AD-19).

One implementation, and the second gets built when a self-hoster arrives with a
non-Anthropic key — not before. The port makes that a day's work instead of a
refactor, which is the whole of what AD-19 buys.

**The transport is injected, exactly as story 2 did for Telegram.** Everything
worth testing lives above the seam — where the cache breakpoint lands, what the
budget refuses, which of the four failures a fault becomes, how a partial batch
is reported — and ``SDKTransport`` at the bottom of this file is the thin edge
that turns a rendered payload into HTTP. That split is what lets this whole
package import and construct with no key, no network and no environment.

**Classification and generation are two objects here, not one with a flag.**
``AnthropicClassifier`` has one public method and it returns a ``Decision``;
there is no method on it, and no public attribute reachable from it, that
returns text. Python cannot make that a proof — a determined caller reaches a
private attribute — so it is the strongest available guarantee rather than a
proof, the same honesty AD-10 states for the crisis entrypoint.

**A classification is held to its labels structurally, not by prompting.**
Prompts belong to their consumers (this story writes none), so the closed set is
imposed with a schema-constrained reply where the tier supports one, and by
refusing anything that is not a label where it does not. A reply that is prose
becomes ``malformed``; it never becomes a decision.

**The transport lives in ``anthropic_transport.py``**, not at the bottom of this
file. That is what lets the offline gate assert that *every* module in this
package is free of the SDK rather than all but the one that matters.

**The request shapes here are current, and several of the obvious ones are 400s
now.** A fixed thinking budget is rejected on the frontier model, an effort
setting is an error on the cheap one, and an assistant prefill is refused on
everything current. None of those degrade — they fail the call — so the
capabilities live as data on ``ModelSpec`` and this file has one renderer with
no branch on a model name.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from half.errors import (
    BreakpointError,
    BudgetError,
    ModelBatchNotFound,
    ModelNotAuthorised,
    ModelRefused,
    ModelUnavailable,
    TransportFault,
)
from half.model.budget import (
    Budget,
    Estimate,
    Reservation,
    Spend,
    charged,
    estimate,
    tokens_in,
)
from half.model.port import (
    BatchItem,
    CacheTTL,
    Classified,
    Classify,
    Collected,
    Completion,
    Decision,
    Failure,
    Generate,
    Generated,
    ItemOutcome,
    Kind,
    Prompt,
    Reason,
    Submission,
    Submitted,
    Transport,
    Usage,
)
from half.model.tier import (
    CACHE_WRITE_BASIS_1H,
    CACHE_WRITE_BASIS_5M,
    ModelSpec,
    Tier,
    Tiers,
)

#: Stop reasons on which a reply is *finished* and its content may be read.
#: A whitelist rather than a blacklist, which is review round 1's correction:
#: ``pause_turn``, ``tool_use``, a null, a non-string and any reason added after
#: this build all used to fall through and be treated as a complete answer —
#: so a paused turn was delivered to a main as though it were the whole of what
#: Half had to say.
COMPLETE_STOPS: frozenset[str] = frozenset({"end_turn", "stop_sequence"})

#: Batch states the provider reports. ``canceling`` still ends, so it is not
#: ready rather than never ready; anything outside this set is a state this
#: build cannot reason about and is reported as such rather than polled for
#: ever.
BATCH_ENDED = "ended"
BATCH_PENDING: frozenset[str] = frozenset({"in_progress", "canceling"})

#: How a transport fault becomes one of the four. One table, so the mapping
#: cannot differ between the message path and the batch path.
_FAULTS: Mapping[type, tuple[Kind, Reason]] = {
    ModelUnavailable: (Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
    ModelRefused: (Kind.REFUSED, Reason.PROVIDER_REFUSED),
    ModelNotAuthorised: (Kind.REFUSED, Reason.NOT_AUTHORISED),
    ModelBatchNotFound: (Kind.REFUSED, Reason.NO_SUCH_BATCH),
}

#: Structured, and content-free. Every value this module logs is a closed enum
#: or a count — no prompt, no completion, no label, no main's words (AD-22).
logger = logging.getLogger(__name__)

#: The output ceiling a classification asks for. Generous rather than tight:
#: reasoning tokens count against it on a tier that thinks, so a ceiling sized
#: for a one-word answer would truncate before the answer was written and every
#: classification would come back malformed.
CLASSIFY_MAX_TOKENS = 1_024

#: What a classification asks for where the tier has an effort setting. Fixed,
#: not configurable: a classification that thinks hard is paying a frontier
#: price to pick from a list somebody already wrote down.
CLASSIFY_EFFORT = "low"

#: The single field a schema-constrained classification answers in.
LABEL_FIELD = "label"

#: The provider's own ceilings on one batch. Modelled here so a nightly pass
#: is refused where it is built rather than after it has been assembled and
#: sent — the same rule ``_output_ceiling`` follows, applied to the operation
#: the nightly pass actually uses.
MAX_BATCH_ITEMS = 100_000
MAX_BATCH_BYTES = 256 * 1024 * 1024

#: How the provider reports each item's fate inside a collected batch, and
#: which of the four failures each one is. A cancellation is a *refusal* and
#: an expiry is an *unavailability*: resubmitting the second is right and
#: resubmitting the first is a spend nobody asked for, so the table keeps them
#: apart rather than reporting both as "the item failed".
_ITEM_FAILURES: Mapping[str, Failure] = {
    "errored": Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
    "canceled": Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED),
    "expired": Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
}


# ── rendering: where the breakpoint goes, and what the model is told ──────────


def render_prompt(prompt: Prompt, spec: ModelSpec) -> dict[str, Any]:
    """The ``system`` and ``messages`` halves of a request.

    **The marker lands on exactly the block the caller ended the prefix on.**
    Caching is a prefix match, so the placement is the whole feature: one block
    earlier and the stable content after it is re-read at full price every
    call; one block later and every request writes a distinct entry that
    nothing ever reads. The port does not adjust it, does not clamp it, and
    refuses a breakpoint it cannot place.

    **A prefix under this model's own minimum is refused**, which is review
    round 1's correction and follows directly from *never hidden*. Under the
    minimum the provider caches nothing: no error, no marker honoured, no
    cache-creation tokens, just a cost. Emitting the marker anyway would be a
    hidden breakpoint wearing the clothes of an honoured one, and the caller
    would never learn. The minimum is per tier and **not monotonic across
    generations** — 512 on the frontier model against 4096 on the cheap one —
    so this is exactly the case a caller cannot be expected to have checked.

    A caller that stated no breakpoint gets no ``cache_control`` at all — not a
    guess at where the stable part probably ends.
    """
    if prompt.cache is not None:
        cached_tokens = sum(tokens_in(block) for block in prompt.cached_blocks)
        if cached_tokens < spec.cache_min_tokens:
            raise BreakpointError(
                f"the stable prefix is about {cached_tokens} tokens and "
                f"{spec.model} caches nothing under {spec.cache_min_tokens}. "
                "The provider would accept this request, ignore the marker and "
                "bill the prefix in full every call, saying nothing — so the "
                "port refuses instead of placing a breakpoint that does not "
                "work (AD-19). State no breakpoint, or lengthen the prefix"
            )

    system: list[dict[str, Any]] = []
    for position, text in enumerate(prompt.system, start=1):
        block: dict[str, Any] = {"type": "text", "text": text}
        if prompt.cache is not None and position == prompt.cache.after_blocks:
            block["cache_control"] = _cache_control(prompt.cache.ttl)
        system.append(block)

    payload: dict[str, Any] = {
        "messages": [
            {"role": turn.role.value, "content": turn.text} for turn in prompt.turns
        ]
    }
    if system:
        payload["system"] = system
    return payload


def _cache_control(ttl: CacheTTL) -> dict[str, str]:
    """The breakpoint marker.

    ``{"type": "ephemeral"}`` is the whole of it, plus an explicit ``ttl`` for
    the hour-long entry. The default five minutes is left implicit rather than
    spelled, because sending the default as a literal is how a shape drifts
    from the one the provider documents.
    """
    marker = {"type": "ephemeral"}
    if ttl is CacheTTL.ONE_HOUR:
        marker["ttl"] = "1h"
    return marker


def _thinking_and_effort(spec: ModelSpec, *, effort: str) -> dict[str, Any]:
    """The reasoning parameters this tier actually accepts.

    Three separate rules, each of which is a 400 rather than a degradation if
    it is got wrong, which is why they are read off the spec rather than
    guessed per call site:

    * A **fixed thinking budget** is gone. It is not sent here in any form, on
      either tier — it is rejected outright on the frontier model, and reaching
      for it on a model that still tolerates it would leave the stale shape in
      the one renderer both tiers share.
    * **Adaptive thinking** is the only on-mode where thinking exists at all.
      Where the tier does not have it, no thinking parameter is sent.
    * **Effort** lives inside ``output_config`` and is an error on a tier
      without it, so it is a capability flag rather than a default.
    """
    out: dict[str, Any] = {}
    if spec.adaptive_thinking:
        out["thinking"] = {"type": "adaptive"}
    if spec.effort:
        out["output_config"] = {"effort": effort}
    return out


def _label_schema(labels: Sequence[str]) -> dict[str, Any]:
    """A reply shape that can only be one of the labels.

    This is how *"a classification returns a decision and never prose"* is
    imposed without the port writing a single word of prompt: the constraint is
    on the *shape of the reply*, not on an instruction somebody could reword.
    Prompts belong to their consumers.
    """
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {LABEL_FIELD: {"type": "string", "enum": list(labels)}},
            "required": [LABEL_FIELD],
            "additionalProperties": False,
        },
    }


def render_classify(work: Classify, spec: ModelSpec) -> dict[str, Any]:
    """One classification, as the provider expects it."""
    payload = render_prompt(work.prompt, spec)
    payload["model"] = spec.model
    payload["max_tokens"] = classify_ceiling(spec)
    payload.update(_thinking_and_effort(spec, effort=CLASSIFY_EFFORT))
    if spec.structured_output:
        output_config = payload.setdefault("output_config", {})
        output_config["format"] = _label_schema(work.labels)
    return payload


def render_generate(work: Generate, spec: ModelSpec) -> dict[str, Any]:
    """One generation, as the provider expects it."""
    payload = render_prompt(work.prompt, spec)
    payload["model"] = spec.model
    payload["max_tokens"] = _output_ceiling(work, spec)
    payload.update(_thinking_and_effort(spec, effort=spec.generate_effort))
    return payload


def classify_ceiling(spec: ModelSpec) -> int:
    return min(CLASSIFY_MAX_TOKENS, spec.max_output_tokens)


def _output_ceiling(work: Generate, spec: ModelSpec) -> int:
    if work.max_tokens is None:
        return spec.default_max_tokens
    if work.max_tokens > spec.max_output_tokens:
        raise BudgetError(
            f"{work.max_tokens} output tokens is past the {spec.max_output_tokens} "
            f"this tier allows. Refused here rather than at the wire, so the "
            f"call site learns it without spending a request to find out"
        )
    return work.max_tokens


# ── reading a reply ──────────────────────────────────────────────────────────


def _text_of(reply: Mapping[str, Any]) -> str | None:
    """The text blocks of a reply, joined, or ``None`` if there are none.

    Blocks are filtered by ``type`` rather than by position: a reply may open
    with a thinking block, and reading ``content[0].text`` would read an empty
    string on every tier that thinks and call it an empty answer.
    """
    content = reply.get("content")
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
        return None
    parts = [
        block.get("text")
        for block in content
        if isinstance(block, Mapping)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "".join(parts) if parts else None


def _stop_failure(reply: Mapping[str, Any]) -> Failure | None:
    """The failure a reply's ``stop_reason`` already decides, if any.

    A refusal arrives as a *successful* HTTP response — checking the status
    code alone would read it as an answer and hand a refusal's empty content
    to a main. So the stop reason is read before the content, always.
    """
    stop = reply.get("stop_reason")
    if stop == "refusal":
        return Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED)
    if stop == "max_tokens":
        # Truncated. Reported as malformed rather than returned as a partial
        # answer: half a sentence delivered to a main is worse than a failure
        # the caller gets to decide the meaning of.
        return Failure(Kind.MALFORMED, Reason.TRUNCATED)
    if stop not in COMPLETE_STOPS:
        # Anything else — a paused turn, a tool call, a null, a reason this
        # build has never heard of — is a reply that has not finished. Treating
        # an unrecognised stop as an ending is how a partial answer reaches a
        # main looking like the whole of it.
        return Failure(Kind.MALFORMED, Reason.INCOMPLETE)
    return None


def read_decision(
    reply: Mapping[str, Any], labels: Sequence[str], usage: Usage
) -> Classified:
    """A reply, as a decision from the closed set — or as a failure.

    **Never coerced.** There is no nearest match, no prefix match and no
    fallback label. A model that answered with a sentence produces
    ``malformed``, because a classifier that guesses which label a sentence
    probably meant is a classifier that will one day guess wrong on the crisis
    path.
    """
    failed = _stop_failure(reply)
    if failed is not None:
        return failed
    text = _text_of(reply)
    if text is None or not text.strip():
        return Failure(Kind.MALFORMED, Reason.NO_CONTENT)

    label = _label_in(text)
    if label is None:
        return Failure(Kind.MALFORMED, Reason.UNREADABLE)
    if label not in labels:
        return Failure(Kind.MALFORMED, Reason.NOT_A_LABEL)
    return Decision(label=label, usage=usage)


def _label_in(text: str) -> str | None:
    """The label a reply carries, in either shape it can arrive in.

    A schema-constrained reply is a JSON object; an unconstrained one on a tier
    without that feature is the bare word. Both are read, and anything else is
    unreadable — including a JSON object whose ``label`` is not text, which is
    the shape a model produces when it decides to explain itself in a list.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError:
            return None
        if not isinstance(data, Mapping):
            return None
        value = data.get(LABEL_FIELD)
        return value if isinstance(value, str) else None
    return stripped


def read_completion(reply: Mapping[str, Any], usage: Usage) -> Generated:
    """A reply, as text — or as a failure."""
    failed = _stop_failure(reply)
    if failed is not None:
        return failed
    text = _text_of(reply)
    if text is None or not text.strip():
        return Failure(Kind.MALFORMED, Reason.NO_CONTENT)
    return Completion(text=text, usage=usage)


def _transport_failure(exc: TransportFault) -> Failure:
    """Which of the four a transport fault is.

    Read off one table, so the message path and the batch path cannot disagree.
    A fault class with no row is an unavailability — the retryable answer,
    which is the safe default for something this build does not recognise.

    Note what is *not* here: ``ModelRequestInvalid``. A request shape the
    provider will never accept is a build mistake, so it is not caught at all
    and is raised out of the port, which is what stops it being retried for
    ever.
    """
    for fault, (kind, because) in _FAULTS.items():
        if isinstance(exc, fault):
            return Failure(kind, because)
    return Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)


# ── the four operations ──────────────────────────────────────────────────────


class _Priced:
    """Shared machinery: resolve the tier, price the call, hold the ledger.

    Not a base class with a ``call()`` on it, deliberately. The point of the
    holders below is that a classify-only caller has no method reaching text,
    and an inherited generic call would put one straight back.

    **Everything here is private, and that is review round 1's correction.**
    The tier table and the ledger used to be public attributes, so the object
    the crisis path holds could call ``spend.reset()`` and clear the whole
    pass's CAP-7 accounting, or read and re-key the tier table. Narrow output
    is half of a narrow holder; the other half is narrow *authority*, and an
    attribute is authority.
    """

    __slots__ = ("_transport", "_tiers", "_spend")

    def __init__(
        self,
        transport: Transport,
        *,
        tiers: Tiers,
        budget: Budget | None = None,
        spend: Spend | None = None,
    ) -> None:
        """Constructs offline. No key is read here, no client is built, and
        nothing is contacted: the transport is whatever it was handed.

        ``spend`` is shared where it is passed in, because a per-object ledger
        would make CAP-7's per-pass ceiling mean *per holder* — three times the
        limit for a provider that hands out three.
        """
        if spend is None:
            if budget is None:
                raise BudgetError(
                    "a model holder needs either a budget or a shared ledger; "
                    "an unlimited one is a nightly pass with no ceiling (CAP-7)"
                )
            spend = Spend(budget)
        self._transport = transport
        self._tiers = tiers
        self._spend = spend

    def _spec(self, main_id: str) -> ModelSpec:
        """This main's model. Raises ``UnknownTier`` rather than defaulting."""
        return self._tiers.spec_for(main_id)

    def _ttl_basis(self, prompt: Prompt) -> int:
        if prompt.cache is not None and prompt.cache.ttl is CacheTTL.ONE_HOUR:
            return CACHE_WRITE_BASIS_1H
        return CACHE_WRITE_BASIS_5M

    def _estimate(
        self,
        prompt: Prompt,
        spec: ModelSpec,
        *,
        max_output_tokens: int,
        batched: bool = False,
    ) -> Estimate:
        return estimate(
            spec,
            cached_text=prompt.cached_blocks,
            # The turns are priced with the blocks outside the prefix, because
            # that is what they are: everything after the breakpoint is read at
            # full price every call. Leaving them out was a budget that could
            # not see the half of the prompt that grows.
            uncached_text=prompt.uncached_blocks
            + tuple(turn.text for turn in prompt.turns),
            max_output_tokens=max_output_tokens,
            ttl_basis=self._ttl_basis(prompt),
            # The caller's own claim about whether this prefix is already warm.
            # Never inferred: the port has no way to know what another process
            # wrote five minutes ago, and guessing warm admits calls on the
            # assumption that somebody else already paid.
            warm=prompt.cache is not None and prompt.cache.expect_warm,
            batched=batched,
        )

    async def _send(
        self, payload: Mapping[str, Any], spec: ModelSpec, *,
        reservation: Reservation, ttl_basis: int,
    ) -> tuple[Mapping[str, Any] | None, Usage, Failure | None]:
        """One request. Never retried here.

        A retry that turns a refusal into a spend is forbidden outright, so
        this makes exactly one attempt and reports what happened.

        The reservation is settled or released on every path out — a leaked
        reservation would shrink the pass budget for ever, which is the
        mirror-image of the bug that made it necessary. ``ModelRequestInvalid``
        is deliberately not caught: it is a build mistake, so the reservation is
        released and the exception is raised out of the port.
        """
        try:
            reply = await self._transport.message(payload)
        except TransportFault as exc:
            self._spend.release(reservation)
            failure = _transport_failure(exc)
            logger.warning("model call failed: %s/%s", failure.kind, failure.because)
            return None, Usage(), failure
        except BaseException:
            self._spend.release(reservation)
            raise

        if not isinstance(reply, Mapping):
            self._spend.settle(reservation, Usage(micro_usd=reservation.micro_usd))
            return None, Usage(), Failure(Kind.MALFORMED, Reason.UNREADABLE)

        usage = charged(
            spec,
            reply.get("usage") or {},
            ttl_basis=ttl_basis,
            floor_micro_usd=reservation.micro_usd,
        )
        self._spend.settle(reservation, usage)
        return reply, usage, None

    def _admit(self, priced: Estimate) -> Reservation | Failure:
        """Reserve, or say which ceiling refused.

        Reserving rather than merely checking is what makes the budget bind
        when calls overlap — verified at eight, the scheduler's own bound.
        """
        outcome = self._spend.admit(priced)
        if isinstance(outcome, Reason):
            failure = Failure(Kind.OVER_BUDGET, outcome)
            # Logged off the constructed failure rather than off the local, so
            # the two fields are provably the closed enums the AD-22 scan
            # requires — a bare name it cannot resolve is exactly the shape
            # that let a completion into a log line before.
            logger.warning("model call refused: %s/%s", failure.kind, failure.because)
            return failure
        return outcome


class AnthropicClassifier(_Priced):
    """Classification, and nothing else.

    **There is exactly one public method here, it returns a ``Decision``, and
    there is no public attribute at all.** That is the crisis constraint made
    structural in both halves: a caller handed one of these cannot generate,
    cannot batch a generation, cannot reach anything that would — and cannot
    move the pass's cost accounting or re-key the tier table either.
    """

    __slots__ = ()

    async def classify(self, work: Classify) -> Classified:
        """Decide, or report which of the four failures happened."""
        spec = self._spec(work.prompt.main_id)
        priced = self._estimate(
            work.prompt, spec, max_output_tokens=classify_ceiling(spec)
        )
        admitted = self._admit(priced)
        if isinstance(admitted, Failure):
            return admitted  # refused before the send; nothing spent

        payload = render_classify(work, spec)
        reply, usage, failure = await self._send(
            payload, spec,
            reservation=admitted, ttl_basis=self._ttl_basis(work.prompt),
        )
        if reply is None:
            return failure or Failure(Kind.MALFORMED, Reason.UNREADABLE)
        return read_decision(reply, work.labels, usage)


class AnthropicGenerator(_Priced):
    """Generation. Held only by a caller that may author text."""

    __slots__ = ()

    async def generate(self, work: Generate) -> Generated:
        spec = self._spec(work.prompt.main_id)
        ceiling = _output_ceiling(work, spec)
        priced = self._estimate(work.prompt, spec, max_output_tokens=ceiling)
        admitted = self._admit(priced)
        if isinstance(admitted, Failure):
            return admitted

        payload = render_generate(work, spec)
        reply, usage, failure = await self._send(
            payload, spec,
            reservation=admitted, ttl_basis=self._ttl_basis(work.prompt),
        )
        if reply is None:
            return failure or Failure(Kind.MALFORMED, Reason.UNREADABLE)
        return read_completion(reply, usage)


class AnthropicBatcher(_Priced):
    """Submit and collect — two operations, not one wait (AD-9, AD-19).

    The nightly pass submits in the evening for a morning delivery, so the
    process that submits is routinely not the process that collects. That is
    why ``Submission`` is a value made of strings, why it carries what it cost,
    and why nothing here holds state between the two calls.
    """

    __slots__ = ()

    async def submit(self, items: Sequence[BatchItem]) -> Submission | Failure:
        """Send a batch, or refuse the whole of it.

        **Whole, or not at all.** A batch where the budget stopped halfway is a
        partial spend with no record of which half went — so every item is
        reserved first, through the same ``Spend.admit`` a single call goes
        through, and any refusal releases every reservation already taken. Two
        copies of the ceiling comparison is what this replaces.
        """
        if not items:
            raise ValueError("an empty batch has nothing to submit")
        if len(items) > MAX_BATCH_ITEMS:
            raise ValueError(
                f"{len(items)} items is past the provider's {MAX_BATCH_ITEMS} "
                "per batch. Refused here rather than at the wire, for the "
                "reason an over-long output ceiling is"
            )
        refs = [item.ref for item in items]
        if len(set(refs)) != len(refs):
            raise ValueError(
                "two items share a reference; results come back in any order, "
                "so a repeated ref makes two outcomes indistinguishable"
            )

        requests: list[dict[str, Any]] = []
        submitted: list[Submitted] = []
        reservations: list[Reservation] = []
        committed = 0
        try:
            for item in items:
                prompt = item.work.prompt
                spec = self._spec(prompt.main_id)
                classifying = isinstance(item.work, Classify)
                ceiling = (
                    classify_ceiling(spec)
                    if classifying
                    else _output_ceiling(item.work, spec)
                )
                priced = self._estimate(
                    prompt, spec, max_output_tokens=ceiling, batched=True
                )
                admitted = self._admit(priced)
                if isinstance(admitted, Failure):
                    for taken in reservations:
                        self._spend.release(taken)
                    return admitted
                reservations.append(admitted)
                committed += priced.micro_usd
                requests.append({
                    "custom_id": item.ref,
                    "params": (
                        render_classify(item.work, spec)
                        if classifying
                        else render_generate(item.work, spec)
                    ),
                })
                submitted.append(Submitted(
                    ref=item.ref,
                    tier=self._tiers.of(prompt.main_id).value,
                    labels=item.work.labels if classifying else (),
                ))

            if _payload_bytes(requests) > MAX_BATCH_BYTES:
                raise ValueError(
                    f"this batch is past the provider's {MAX_BATCH_BYTES}-byte "
                    "limit. Refused here rather than at the wire, so a whole "
                    "nightly pass does not fail after it has been built"
                )

            try:
                created = await self._transport.batch_create(requests)
            except TransportFault as exc:
                for taken in reservations:
                    self._spend.release(taken)
                failure = _transport_failure(exc)
                logger.warning(
                    "batch submit failed: %s/%s", failure.kind, failure.because
                )
                return failure

            batch_id = created.get("id") if isinstance(created, Mapping) else None
            if not isinstance(batch_id, str) or not batch_id:
                for taken in reservations:
                    self._spend.release(taken)
                return Failure(Kind.MALFORMED, Reason.UNREADABLE)
        except BaseException:
            # A refusal returns above; this is the raise path — a bad output
            # ceiling, an unknown tier, an over-long payload. Every reservation
            # already taken is given back, because a leaked reservation shrinks
            # the pass budget for ever.
            for reservation in reservations:
                self._spend.release(reservation)
            raise

        # Settled **here**, at the estimate, and not at collection. A batch is
        # committed the moment the provider accepts it, and the process that
        # collects it hours later is routinely not this one (AD-9) — a ledger
        # that only learned the cost on collection would let one pass submit
        # unlimited batches and then bill the *next* pass for all of them.
        for reservation in reservations:
            self._spend.settle(reservation, Usage(micro_usd=reservation.micro_usd))
        logger.info("batch submitted: %d items", len(submitted))
        return Submission(
            batch_id=batch_id,
            items=tuple(submitted),
            committed_micro_usd=committed,
        )

    async def collect(self, submission: Submission) -> Collected | Failure:
        """Read a batch back, per item.

        **Not ready is an answer, and never-ready is a different answer.** A
        batch may take a day, so a scheduler asking early is the ordinary case;
        raising there would make the ordinary case look like a fault. But a
        batch the provider does not have, or whose state this build cannot
        read, will never become ready, and reporting *that* as merely-early is
        a caller polling for ever with no way to stop.

        **Per item, never one verdict.** Some succeeded and some expired is the
        normal shape of a large batch, and a caller told only that *the batch*
        failed would throw away the results it did get.
        """
        try:
            status = await self._transport.batch_status(submission.batch_id)
        except TransportFault as exc:
            failure = _transport_failure(exc)
            logger.warning("batch status failed: %s/%s", failure.kind, failure.because)
            return failure
        if not isinstance(status, Mapping):
            return Failure(Kind.MALFORMED, Reason.UNREADABLE)

        state = status.get("processing_status")
        if state in BATCH_PENDING:
            return Collected(ready=False)
        if state != BATCH_ENDED:
            # Missing, or a state added after this build. Not "early".
            logger.warning("batch state unreadable: %s/%s", Kind.REFUSED,
                           Reason.NO_SUCH_BATCH)
            return Failure(Kind.REFUSED, Reason.NO_SUCH_BATCH)

        outcomes: dict[str, ItemOutcome] = {}
        try:
            async for entry in self._transport.batch_results(submission.batch_id):
                read = self._read_item(entry, submission)
                if read is None:
                    continue
                ref, outcome = read
                if ref in outcomes:
                    # Two rows claiming one reference. Neither can be trusted to
                    # be the outcome for it, and taking whichever arrived last
                    # loses one item's true result in silence.
                    outcomes[ref] = Failure(Kind.MALFORMED, Reason.DUPLICATE_RESULT)
                    continue
                outcomes[ref] = outcome
        except TransportFault as exc:
            # **What was read is kept.** Discarding it reported partial success
            # as total failure, which is the all-or-nothing shape this whole
            # operation exists to avoid; the rows that never arrived show up as
            # `missing`, which a caller already has to handle.
            failure = _transport_failure(exc)
            logger.warning(
                "batch results interrupted after %d rows: %s/%s",
                len(outcomes), failure.kind, failure.because,
            )
            if not outcomes:
                return failure
        logger.info("batch collected: %d of %d", len(outcomes), len(submission.items))
        return Collected(ready=True, outcomes=outcomes)

    def _read_item(
        self, entry: Any, submission: Submission
    ) -> tuple[str, ItemOutcome] | None:
        """One result row, as this item's own outcome.

        An unrecognised row is dropped rather than guessed at: it shows up as a
        *missing* ref against the submission, which is a shape the caller
        already has to handle, and inventing an outcome for it would be the
        coercion the whole port refuses.
        """
        if not isinstance(entry, Mapping):
            return None
        ref = entry.get("custom_id")
        if not isinstance(ref, str):
            return None
        item = submission.item(ref)
        if item is None:
            return None

        result = entry.get("result")
        if not isinstance(result, Mapping):
            return ref, Failure(Kind.MALFORMED, Reason.UNREADABLE)
        outcome = result.get("type")
        if outcome in _ITEM_FAILURES:
            return ref, _ITEM_FAILURES[outcome]
        if outcome != "succeeded":
            return ref, Failure(Kind.MALFORMED, Reason.UNREADABLE)

        message = result.get("message")
        if not isinstance(message, Mapping):
            return ref, Failure(Kind.MALFORMED, Reason.UNREADABLE)

        spec = self._tiers.models.get(_tier_or_none(item.tier))
        # Reported, never charged. The submission already committed the batch
        # to its own pass's ledger; charging again here would bill tonight's
        # budget for last night's work. A tier this build no longer has leaves
        # the reply readable and its price unknown, which is reported as zero
        # rather than made up.
        usage = (
            Usage()
            if spec is None
            else charged(spec, message.get("usage") or {}, batched=True)
        )

        if item.classifying:
            return ref, read_decision(message, item.labels, usage)
        return ref, read_completion(message, usage)


def _payload_bytes(requests: Sequence[Mapping[str, Any]]) -> int:
    """A batch's size on the wire, near enough to bound it.

    ``separators`` fixed so the figure does not move with a formatting default,
    and the comparison is against the provider's own documented ceiling rather
    than a number this module invented.
    """
    return len(json.dumps(requests, separators=(",", ":")).encode("utf-8"))


def _tier_or_none(name: str) -> Tier | None:
    try:
        return Tier(name)
    except ValueError:
        return None


class AnthropicProvider(_Priced):
    """AD-19's one implementation, all four operations.

    Holds the three narrow objects and shares one ledger with them, so the
    per-pass ceiling is a ceiling on the pass rather than on each holder.

    ``classifier()`` is how a caller that may only classify gets what it is
    allowed to have. It returns a different object rather than ``self``: a
    provider narrowed by convention is not narrowed.

    Unlike the narrow holders, this one *does* expose the ledger — read-only,
    and through a snapshot rather than the live object, so a caller can meter
    and persist a pass without being handed something that can reset it.
    """

    __slots__ = ("_classifier", "_generator", "_batcher")

    def __init__(
        self,
        transport: Transport,
        *,
        tiers: Tiers,
        budget: Budget | None = None,
        spend: Spend | None = None,
    ) -> None:
        super().__init__(transport, tiers=tiers, budget=budget, spend=spend)
        shared = {"tiers": tiers, "spend": self._spend}
        self._classifier = AnthropicClassifier(transport, **shared)
        self._generator = AnthropicGenerator(transport, **shared)
        self._batcher = AnthropicBatcher(transport, **shared)

    def classifier(self) -> AnthropicClassifier:
        """A holder that can decide, cannot write, and cannot spend."""
        return self._classifier

    def generator(self) -> AnthropicGenerator:
        return self._generator

    def batcher(self) -> AnthropicBatcher:
        return self._batcher

    def ledger(self):
        """This pass's spending, as a durable value (CAP-7, AD-9).

        A snapshot rather than the ``Spend`` itself. Persist it beside the
        submission it paid for, and ``Spend.restored`` picks the pass up where
        this process left it — a budget that resets on restart while the batch
        it committed survives is not a ceiling.
        """
        return self._spend.snapshot()

    async def classify(self, work: Classify) -> Classified:
        return await self._classifier.classify(work)

    async def generate(self, work: Generate) -> Generated:
        return await self._generator.generate(work)

    async def submit(self, items: Sequence[BatchItem]) -> Submission | Failure:
        return await self._batcher.submit(items)

    async def collect(self, submission: Submission) -> Collected | Failure:
        return await self._batcher.collect(submission)
