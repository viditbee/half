"""The ``ModelProvider`` port — four operations, and two of them held apart
(AD-19).

**Classify and generate are different operations, and that is the load-bearing
decision in this file.** A single ``call()`` with a mode flag would make *"a
model never authors a word a main in crisis reads"* something every caller has
to remember. Two protocols make it something a caller cannot do: the crisis
path holds a ``Classifier``, which has no method that returns text — the same
reason ``Assessment`` carries no text one package over.

**A classification returns a decision and never prose.** ``Decision`` carries a
label drawn from the request's own closed set, and ``Failure`` carries two
closed enums. There is no free-text field anywhere on either, so *"no prose in
any field"* is a property of the types rather than a rule about the parser.

**The four failures are values, not exceptions.** Crisis fails toward entering,
consolidation fails toward skipping, a reply fails toward silence. One default
would be wrong for two of the three, so the port reports what happened and
never decides what it means. ``half.errors.ModelError`` and its subclasses are
for the other thing entirely — a build or operator mistake, where a value
nobody has to check is exactly how the mistake ships.

**Cache breakpoints are first-class and never hidden** (AD-19). The caller says
where the stable prefix ends; the port places the marker exactly there and
refuses anything it cannot place, rather than sliding it to the nearest legal
position. A caller that states none gets no caching and pays for it — never a
guess.

**Batch is a shape, not a wrapper.** ``submit`` and ``collect`` are separate
operations, a ``Submission`` is a value that serializes to a string and back,
and a collection that is not ready yet is a normal answer rather than an error.

The port stays narrow for the reason ``half.retrieval.port`` gives: gbrain's own
docs record a storage interface that absorbed embedding and chunking, grew past
a hundred methods, and stopped being something anyone could reason about. A
fifth operation needs human sign-off, not a commit.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from half.errors import BreakpointError

#: Ceiling on how many blocks a caller may put in front of a breakpoint. The
#: API allows four ``cache_control`` markers per request and the port places
#: exactly one, so this is a sanity bound on the prompt itself rather than a
#: protocol limit — a breakpoint at block nine hundred is a caller mistake.
MAX_SYSTEM_BLOCKS = 64


class Role(StrEnum):
    """Who said a turn.

    Two values, and no ``system``: a system instruction is a *block*, not a
    turn, because that is what decides whether it lands in the cached prefix.
    Mixing the two is how a stable instruction ends up after the breakpoint and
    the free tier's cost model quietly stops working.
    """

    USER = "user"
    ASSISTANT = "assistant"


class CacheTTL(StrEnum):
    """How long a written cache entry lives.

    Both are offered because the economics differ and the caller is the only
    one who knows which applies: a five-minute entry costs 1.25x to write and
    breaks even on the second read, an hour costs 2x and needs a third. A
    conversation keeps itself warm; a nightly pass does not.
    """

    FIVE_MINUTES = "5m"
    ONE_HOUR = "1h"


class Kind(StrEnum):
    """The four ways a call fails, reported distinctly (AD-19).

    Distinct because the callers are: an ``UNAVAILABLE`` may be tried again, a
    ``REFUSED`` may not, an ``OVER_BUDGET`` spent nothing and a ``MALFORMED``
    spent everything. A port that collapsed them into one "it didn't work"
    would leave every caller guessing which of the four it was looking at.
    """

    #: The transport could not reach the provider at all.
    UNAVAILABLE = "unavailable"
    #: The provider answered, and the answer was a refusal.
    REFUSED = "refused"
    #: The call would have exceeded a budget. Nothing was sent, nothing spent.
    OVER_BUDGET = "over-budget"
    #: The provider answered with something this build cannot use.
    MALFORMED = "malformed"


class Reason(StrEnum):
    """Why a call failed, from a closed set.

    **A closed set rather than a message, and that is not tidiness.** A free-
    text reason is the shortest path from a completion to a log line: the
    obvious implementation interpolates what came back, and AD-22 forbids
    exactly that. With an enum there is no field a prompt, a completion or a
    main's words could travel in, which makes *"no content in logs or errors"*
    assertable byte-wise instead of reviewable by eye.
    """

    #: Network, timeout, or a provider-side fault.
    TRANSPORT_FAILED = "transport-failed"
    #: The provider declined the request on its own terms.
    PROVIDER_REFUSED = "provider-refused"
    #: Credentials were rejected.
    NOT_AUTHORISED = "not-authorised"
    #: This one call costs more than the per-call ceiling allows.
    PER_CALL_BUDGET = "per-call-budget"
    #: This pass has spent what it was given.
    PER_PASS_BUDGET = "per-pass-budget"
    #: A reply with no usable content block.
    NO_CONTENT = "no-content"
    #: A reply that ran out of output tokens mid-answer.
    TRUNCATED = "truncated"
    #: A classification whose answer is not one of the labels asked for.
    NOT_A_LABEL = "not-a-label"
    #: A reply this build could not parse at all.
    UNREADABLE = "unreadable"
    #: A batch the provider does not have, or will not return.
    NO_SUCH_BATCH = "no-such-batch"


@dataclass(frozen=True, slots=True)
class Turn:
    """One turn of conversation, normalized away from any provider."""

    role: Role
    text: str


@dataclass(frozen=True, slots=True)
class Breakpoint:
    """Where the caller says the stable prefix ends (AD-19).

    ``after_blocks`` counts *system blocks*, one-based: ``1`` caches the first
    block, ``len(system)`` caches all of them. It is a count and not an index
    on purpose — an off-by-one in a cache marker is invisible in every
    response and shows up only as a cost.

    Nothing here is a hint. The port places the marker on exactly this block,
    and refuses a value it cannot place rather than clamping to the nearest
    legal one.
    """

    after_blocks: int
    ttl: CacheTTL = CacheTTL.FIVE_MINUTES

    def __post_init__(self) -> None:
        if not isinstance(self.after_blocks, int) or isinstance(
            self.after_blocks, bool
        ):
            raise BreakpointError(
                f"a breakpoint is a count of system blocks, not "
                f"{type(self.after_blocks).__name__}"
            )
        if self.after_blocks < 1:
            raise BreakpointError(
                f"a breakpoint after {self.after_blocks} blocks caches nothing; "
                "state no breakpoint instead of one that marks an empty prefix"
            )
        if self.after_blocks > MAX_SYSTEM_BLOCKS:
            raise BreakpointError(
                f"a breakpoint after {self.after_blocks} blocks is past the "
                f"{MAX_SYSTEM_BLOCKS}-block bound on a prompt"
            )


@dataclass(frozen=True, slots=True)
class Prompt:
    """Everything a call is made of, and where its stable prefix ends.

    ``system`` is ordered stable-first, because caching is a prefix match and a
    volatile block in front of a stable one makes every marker behind it
    worthless. The port does not reorder: a caller that puts the day's date in
    ``system[0]`` has decided to cache nothing, and finding that out from a
    cost line is better than having the port silently rearrange what was asked
    for.

    ``main_id`` travels with every prompt because the tier travels with the
    main (AD-20) — the model is resolved per call from who it is for, and there
    is no request shape that could name a model instead.
    """

    main_id: str
    system: tuple[str, ...] = ()
    turns: tuple[Turn, ...] = ()
    #: ``None`` means the caller states no breakpoint: nothing is cached, and
    #: the estimated cost says so. Never guessed.
    cache: Breakpoint | None = None

    def __post_init__(self) -> None:
        if len(self.system) > MAX_SYSTEM_BLOCKS:
            raise BreakpointError(
                f"{len(self.system)} system blocks is past the "
                f"{MAX_SYSTEM_BLOCKS}-block bound on a prompt"
            )
        if self.cache is None:
            return
        if self.cache.after_blocks > len(self.system):
            raise BreakpointError(
                f"the breakpoint ends the stable prefix after "
                f"{self.cache.after_blocks} system blocks, and this prompt has "
                f"{len(self.system)}. The port does not move a breakpoint to "
                "where it would fit — the free tier's cost model rests on it "
                "being where the caller put it (AD-19)"
            )

    @property
    def cached_blocks(self) -> tuple[str, ...]:
        """The blocks inside the stable prefix, as the caller drew it."""
        if self.cache is None:
            return ()
        return self.system[: self.cache.after_blocks]

    @property
    def uncached_blocks(self) -> tuple[str, ...]:
        """The system blocks the breakpoint leaves outside the prefix."""
        if self.cache is None:
            return self.system
        return self.system[self.cache.after_blocks :]


@dataclass(frozen=True, slots=True)
class Classify:
    """A classification: a prompt, and the closed set of answers allowed.

    ``labels`` is the whole of what may come back. It is carried on the request
    rather than configured on the provider so that two callers classifying
    different things cannot be handed each other's vocabulary, and so that
    *"never prose"* is checkable against the request that asked.
    """

    prompt: Prompt
    labels: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.labels:
            raise ValueError(
                "a classification with no labels has no decision to return; "
                "the closed set is what makes the answer not prose"
            )
        if len(set(self.labels)) != len(self.labels):
            raise ValueError(f"duplicate labels: {self.labels}")
        if any(not isinstance(label, str) or not label.strip()
               for label in self.labels):
            raise ValueError(f"a label must be non-empty text: {self.labels}")


@dataclass(frozen=True, slots=True)
class Generate:
    """A generation: a prompt, and a ceiling on what comes back.

    ``max_tokens`` of ``None`` means the tier's own ceiling. There is no
    setting here that names a model, because AD-20 puts that on the main.
    """

    prompt: Prompt
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError(f"max_tokens must be at least 1: {self.max_tokens}")


@dataclass(frozen=True, slots=True)
class Usage:
    """What a call actually consumed. Counts and a cost — never content.

    ``cache_read`` and ``cache_write`` are separate fields rather than one
    "cached" number because they are priced in opposite directions: a read is
    a tenth of the input price, a write is a quarter more than it. A single
    field would make the one number the free tier depends on unmeasurable.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    #: Millionths of a US dollar. Integer, so that a budget comparison is exact
    #: and two builds adding the same calls in a different order agree.
    micro_usd: int = 0


@dataclass(frozen=True, slots=True)
class Decision:
    """What a classification answers with: a label, and nothing else.

    Every field is closed or numeric. There is no field on this type that a
    completion could travel in, which is what makes *"a model never authors a
    word a main in crisis reads"* a property of the return type rather than a
    promise about the parser.
    """

    label: str
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class Completion:
    """What a generation answers with."""

    text: str
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class Failure:
    """A call that did not produce an answer, and which of the four it was.

    Two closed enums and nothing else. A failure carries no message, no
    provider payload and no excerpt of what was sent — see ``Reason``.
    """

    kind: Kind
    because: Reason

    @property
    def spent(self) -> bool:
        """Whether this failure may have cost money.

        An over-budget refusal happens before anything is sent and an
        unavailable never reached the provider; a refusal and a malformed reply
        both mean tokens were processed. Callers that meter need to tell those
        apart, and *"it failed"* does not.
        """
        return self.kind in (Kind.REFUSED, Kind.MALFORMED)


#: What ``classify`` answers with: a decision, or one of the four failures.
Classified = Decision | Failure
#: What ``generate`` answers with.
Generated = Completion | Failure
#: One item's outcome inside a collected batch.
ItemOutcome = Decision | Completion | Failure


@dataclass(frozen=True, slots=True)
class BatchItem:
    """One piece of work in a batch, under the caller's own reference.

    ``ref`` is the caller's, not the port's: results come back in any order, so
    a caller that keyed on position would silently mis-attribute every outcome
    the first time the provider reordered them.
    """

    ref: str
    work: Classify | Generate


@dataclass(frozen=True, slots=True)
class Submitted:
    """One item as it was sent, remembered by its reference.

    Two facts travel with the ref, and each is here because a collection three
    hours later cannot recover it:

    ``labels`` is what makes a classification still a classification when it
    comes back. Without it a collected batch would have to answer every item
    with text — and a classify-only caller that submitted work would collect
    prose, which is the exact thing the two protocols exist to prevent.

    ``tier`` is what the item actually ran on, not what its main is on now. A
    main who moved tier between the submission and the collection would
    otherwise have last night's batch priced at this morning's rates.
    """

    ref: str
    tier: str
    #: Empty for a generation; the closed set for a classification.
    labels: tuple[str, ...] = ()

    @property
    def classifying(self) -> bool:
        return bool(self.labels)


@dataclass(frozen=True, slots=True)
class Submission:
    """A submitted batch — an identifier that outlives the process that made it.

    Strings and nothing else. There is no live handle, no open connection and
    no reference to the provider that made it, so a submission survives being
    written to a log, read back by a different process on a different day, and
    collected there. ``to_json``/``from_json`` are the whole of that promise,
    and they round-trip exactly.

    The items travel with the identifier because a partial collection has to be
    reportable as partial: without the set that was asked for, *"three came
    back"* cannot be told from *"three were sent"*.
    """

    batch_id: str
    items: tuple[Submitted, ...] = ()

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(item.ref for item in self.items)

    def item(self, ref: str) -> Submitted | None:
        return next((i for i in self.items if i.ref == ref), None)

    def to_json(self) -> str:
        """A durable string. Sorted keys, so the same submission is the same
        bytes and a caller may key on it."""
        return json.dumps(
            {
                "batch_id": self.batch_id,
                "items": [
                    {
                        "ref": i.ref,
                        "tier": i.tier,
                        "labels": list(i.labels),
                    }
                    for i in self.items
                ],
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Submission":
        data = json.loads(raw)
        if not isinstance(data, Mapping):
            raise ValueError("a submission is a JSON object")
        batch_id = data.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id:
            raise ValueError("a submission carries a batch identifier")
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("a submission's items are a list")
        items: list[Submitted] = []
        for entry in raw_items:
            if not isinstance(entry, Mapping):
                raise ValueError("a submitted item is a JSON object")
            ref, tier = entry.get("ref"), entry.get("tier")
            labels = entry.get("labels", [])
            if not isinstance(ref, str) or not isinstance(tier, str):
                raise ValueError("a submitted item carries a ref and a tier")
            if not isinstance(labels, list) or any(
                not isinstance(label, str) for label in labels
            ):
                raise ValueError("a submitted item's labels are text")
            items.append(Submitted(ref=ref, tier=tier, labels=tuple(labels)))
        return cls(batch_id=batch_id, items=tuple(items))


@dataclass(frozen=True, slots=True)
class Collected:
    """What ``collect`` answers with.

    **Not-ready is a normal answer, not an error.** A batch takes up to a day,
    so a scheduler asking early is the ordinary case and an exception there
    would make the ordinary case look like a fault — the same shape AD-27 gives
    silence one package over.

    ``outcomes`` is per item, so a batch where some succeeded and some failed
    reports both rather than collapsing to one verdict. A caller that only ever
    reads the whole batch's success would drop the nine results it got because
    the tenth expired.
    """

    ready: bool
    outcomes: Mapping[str, ItemOutcome] = field(default_factory=dict)

    @property
    def failures(self) -> Mapping[str, Failure]:
        return {
            ref: out
            for ref, out in self.outcomes.items()
            if isinstance(out, Failure)
        }

    def missing(self, submission: Submission) -> tuple[str, ...]:
        """Refs that were submitted and are not in this collection.

        A ready batch that is missing an item is a real shape — an expired or
        cancelled request returns nothing at all — and a caller that assumed
        every ref came back would wait for it forever.
        """
        return tuple(r for r in submission.refs if r not in self.outcomes)

    def __len__(self) -> int:
        return len(self.outcomes)

    def __iter__(self) -> Iterator[str]:
        return iter(self.outcomes)


@runtime_checkable
class Classifier(Protocol):
    """Classification, and nothing else.

    **The whole point of this protocol is what it does not have.** A caller
    holding one cannot generate text, cannot submit a batch of generations and
    cannot reach a provider that could — which is what makes the crisis rule
    structural rather than remembered.
    """

    async def classify(self, work: Classify) -> Classified:
        """Decide, or report which of the four failures happened.

        Never raises for a provider fault: the four outcomes are values (see
        this module's docstring). Raises ``ModelError`` only for a build
        mistake — an unknown tier, a budget that admits nothing.
        """
        ...


@runtime_checkable
class Generator(Protocol):
    """Generation. Held only by callers that may author text."""

    async def generate(self, work: Generate) -> Generated: ...


@runtime_checkable
class Batcher(Protocol):
    """Submission and collection, as two operations rather than one wait."""

    async def submit(self, items: Sequence[BatchItem]) -> Submission | Failure: ...

    async def collect(self, submission: Submission) -> Collected | Failure: ...


@runtime_checkable
class ModelProvider(Classifier, Generator, Batcher, Protocol):
    """AD-19's one port, all four operations.

    Nothing on a call path holds this. It exists so that *one* implementation
    has a name to satisfy, while every caller takes the narrow protocol it
    needs — which is how ``Classifier`` stays a promise about what a holder
    cannot do.
    """


@runtime_checkable
class Transport(Protocol):
    """The whole network surface the implementation needs.

    Injected, exactly as ``half.channel.telegram`` takes its transport (story
    2), and for the same reason: it is the seam that keeps the suite offline.
    Everything worth testing lives above it — the breakpoint placement, the
    budget, the tier resolution, the four failures — and this is the thin edge
    that turns a rendered payload into HTTP.

    Speaks plain mappings rather than provider types, so that nothing above it
    imports an SDK and a fake is four methods long.

    An implementation raises ``ModelUnavailable`` or ``ModelRefused`` and never
    a provider's own exception class; the conventions forbid a transport type
    leaking inward.
    """

    async def message(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """One Messages request, returned as a plain mapping."""
        ...

    async def batch_create(
        self, requests: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        """Submit a batch. The mapping carries at least an ``id``."""
        ...

    async def batch_status(self, batch_id: str) -> Mapping[str, Any]:
        """The batch's state. The mapping carries a ``processing_status``."""
        ...

    def batch_results(self, batch_id: str) -> AsyncIterator[Mapping[str, Any]]:
        """Each finished item, in whatever order the provider returns them."""
        ...
