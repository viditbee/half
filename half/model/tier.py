"""Which model a main's calls run on — configuration, never code (AD-20).

**The tier travels with the main.** A global tier either overpays for every
free main or quietly underserves a paid one, and it does so silently. So the
model is resolved per call from *who the call is for*, and there is no request
shape that could name a model instead: ``Prompt`` carries a ``main_id`` and no
model field at all.

**This is the only module in the tree that writes a model identifier down.**
That is asserted over the whole package rather than reviewed, because a model
name in a call site is exactly the change that passes review — it works, it is
one line, and it is the line that makes the tier stop travelling.

**An unknown tier is refused, and a main with no tier is refused too.** There
is no fallback here in either direction. A fallback tier is a bill nobody
authorised or a quality regression nobody sees, arriving without a log line.

**The numbers in this file are provider pricing and provider limits**, and they
change. They are data, in one table, with the tier as the key — so a price move
is an edit here and nothing else, and ``tests/test_model.py`` pins the shape
rather than the arithmetic being spread across the call path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from half.config import parse_pairs
from half.errors import BudgetError, StoreError, UnknownTier

#: Millionths of a US dollar in one dollar. Prices are integers throughout, so
#: that a budget comparison is exact and two builds that add the same calls in
#: a different order reach the same total (the reason ``Usage`` is integral).
MICRO_USD = 1_000_000

#: Basis points in one whole. A cache read costs a tenth of the input price and
#: a five-minute write costs a quarter more than it; an hour's write costs
#: double. Held as basis points rather than floats for the reason above.
BASIS = 10_000


#: The effort levels the current models accept. A value outside this set is a
#: 400 rather than a rounded-down setting, so a tier table naming one is
#: refused where it is written rather than on the first call.
EFFORTS: Mapping[str, None] | tuple[str, ...] = (
    "low", "medium", "high", "xhigh", "max",
)


class Tier(StrEnum):
    """The two tiers Half runs on.

    Named for what they *are for*, not for a model: ``CHEAP`` is free
    conversation and the batched nightly pass, ``FRONTIER`` is paid
    conversation. That is why a model rename is an edit to ``DEFAULT_MODELS``
    and never a change to a caller.

    The two spellings match the ``model_tier`` field the belief log has carried
    since story 1, so the log, the fixture and this enum cannot disagree about
    what a tier is called.
    """

    CHEAP = "cheap"
    FRONTIER = "frontier"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """What a tier resolves to: an identifier, its prices, and its limits.

    **The capability flags are not decoration.** The request parameters a model
    accepts have moved more than once, and the ways they move are all 400s
    rather than degradations: adaptive thinking replaced a fixed
    ``budget_tokens``, which is now rejected outright on the frontier models;
    an effort setting is accepted on some models and an error on others;
    an assistant prefill is refused everywhere current. Carrying those as data
    per tier is what lets one renderer serve both tiers without a branch on a
    model name — which would be a model name in the renderer.
    """

    #: The wire identifier. The one place in ``half/`` where a model is named.
    model: str
    #: Price per million tokens, in millionths of a dollar.
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int
    #: The output ceiling this tier's calls default to.
    default_max_tokens: int
    #: The provider's own ceiling on ``max_tokens``. A request past it is a
    #: caller mistake, refused here rather than at the wire.
    max_output_tokens: int
    #: Below this many tokens a breakpoint silently does not cache — no error,
    #: no marker, just a cost. **Not monotonic across generations**, which is
    #: why it is per tier and not a constant: it is 512 on the newest frontier
    #: model and 4096 on the cheap one, so a prompt that caches on one tier can
    #: silently fail to cache on the other with no code change at all.
    cache_min_tokens: int
    #: Adaptive thinking, the only on-mode on current frontier models. Where
    #: this is false the port sends **no** thinking parameter: the fixed-budget
    #: form it would otherwise reach for is rejected on the models that matter,
    #: and reaching for it on a model that still accepts it would put a stale
    #: shape in the one renderer both tiers share.
    adaptive_thinking: bool
    #: An effort setting inside ``output_config``. An error on models that do
    #: not have it, so it is a flag rather than a default.
    effort: bool
    #: A schema-constrained reply. This is how a classification is held to its
    #: closed label set **without the port writing any prompt text** — prompts
    #: belong to their consumers, so the constraint has to be structural.
    structured_output: bool
    #: What a generation asks for when the tier supports it. ``low`` is what a
    #: classification asks for, and that is not configurable: a classification
    #: that thinks hard is paying frontier prices to pick from a list.
    generate_effort: str = "high"

    def __post_init__(self) -> None:
        """Validated because a deployment supplies these.

        ``Tiers`` takes a caller's own table so a self-hoster can point a tier
        at whatever they are paying for, which means every number here is
        untrusted input. Review round 1 found none of it checked: a negative
        price produces a negative estimate, and a negative estimate is admitted
        by *every* budget — a ceiling that cannot bind, from a typo.
        """
        if not isinstance(self.model, str) or not self.model.strip():
            raise UnknownTier("a tier must resolve to a model identifier")
        prices = {
            "input_micro_usd_per_mtok": self.input_micro_usd_per_mtok,
            "output_micro_usd_per_mtok": self.output_micro_usd_per_mtok,
        }
        for name, value in prices.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BudgetError(
                    f"{self.model}: {name}={value!r}. A price is a whole number "
                    f"of millionths of a dollar and is never negative — a "
                    f"negative one makes an estimate negative, and a negative "
                    f"estimate is admitted by every budget there is"
                )
        counts = {
            "default_max_tokens": self.default_max_tokens,
            "max_output_tokens": self.max_output_tokens,
            "cache_min_tokens": self.cache_min_tokens,
        }
        for name, value in counts.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise BudgetError(f"{self.model}: {name}={value!r} is not a count")
        if self.default_max_tokens > self.max_output_tokens:
            raise UnknownTier(
                f"{self.model}: a default of {self.default_max_tokens} output "
                f"tokens is past the model's own {self.max_output_tokens}"
            )
        if self.effort and self.generate_effort not in EFFORTS:
            raise UnknownTier(
                f"{self.model}: {self.generate_effort!r} is not an effort level "
                f"({', '.join(EFFORTS)})"
            )

    def input_micro_usd(self, tokens: int) -> int:
        """Cost of ``tokens`` at the full input price, rounded up.

        Up, always. A budget that rounds down admits a call it cannot afford,
        and it does so once per call, which compounds across a pass.
        """
        return ceil_div(tokens * self.input_micro_usd_per_mtok, MICRO_USD)

    def output_micro_usd(self, tokens: int) -> int:
        return ceil_div(tokens * self.output_micro_usd_per_mtok, MICRO_USD)

    def cache_read_micro_usd(self, tokens: int) -> int:
        return ceil_div(
            tokens * self.input_micro_usd_per_mtok * CACHE_READ_BASIS,
            MICRO_USD * BASIS,
        )

    def cache_write_micro_usd(self, tokens: int, *, ttl_basis: int) -> int:
        return ceil_div(
            tokens * self.input_micro_usd_per_mtok * ttl_basis, MICRO_USD * BASIS
        )


def ceil_div(numerator: int, denominator: int) -> int:
    """Integer division that rounds **up**.

    Up, always, and shared rather than written twice. A price that rounds down
    admits a call the budget cannot afford, once per call, compounding across a
    pass — and two copies of this with different rounding is how the estimate
    and the charge come to disagree about the same call.
    """
    return -(-numerator // denominator)


#: A cache read costs a tenth of the input price.
CACHE_READ_BASIS = 1_000
#: A five-minute cache write costs a quarter more than the input price; an
#: hour's costs double. The caller picks the TTL, so the port prices both.
CACHE_WRITE_BASIS_5M = 12_500
CACHE_WRITE_BASIS_1H = 20_000
#: A batched call is half price on every token it uses.
BATCH_BASIS = 5_000


#: What each tier resolves to out of the box. **Data, and replaceable**: a
#: deployment hands ``Tiers`` its own table, and nothing else in the tree has
#: to know that happened.
DEFAULT_MODELS: Mapping[Tier, ModelSpec] = MappingProxyType({
    Tier.CHEAP: ModelSpec(
        model="claude-haiku-4-5",
        input_micro_usd_per_mtok=1_000_000,
        output_micro_usd_per_mtok=5_000_000,
        default_max_tokens=4_096,
        max_output_tokens=64_000,
        cache_min_tokens=4_096,
        adaptive_thinking=False,
        effort=False,
        structured_output=True,
    ),
    Tier.FRONTIER: ModelSpec(
        model="claude-opus-5",
        input_micro_usd_per_mtok=5_000_000,
        output_micro_usd_per_mtok=25_000_000,
        default_max_tokens=16_000,
        max_output_tokens=128_000,
        cache_min_tokens=512,
        adaptive_thinking=True,
        effort=True,
        structured_output=True,
    ),
})


@dataclass(frozen=True, slots=True)
class Tiers:
    """Which tier each main is on, and what each tier resolves to.

    Two mappings rather than one, because they change for different reasons and
    at different rates: which main is paying moves with a subscription, while
    what a tier resolves to moves with the provider's catalogue.

    Neither has a default. ``of`` refuses a main it was not given, which is the
    whole of *"never a global default"* — a main who appears in no table is a
    deployment that has not decided, and deciding for it is what AD-20 forbids.
    """

    mains: Mapping[str, Tier]
    models: Mapping[Tier, ModelSpec] = DEFAULT_MODELS

    def __post_init__(self) -> None:
        missing = sorted({t for t in self.mains.values()} - set(self.models))
        if missing:
            raise UnknownTier(
                f"mains are assigned to {missing}, which this build has no "
                f"model for. A tier with no model is refused here rather than "
                f"falling back at the call, where nothing would say it had"
            )

    @classmethod
    def parse(
        cls,
        assignments: Mapping[str, str] | str,
        *,
        models: Mapping[Tier, ModelSpec] | None = None,
    ) -> "Tiers":
        """Build from configuration, refusing anything this build cannot name.

        Accepts the mapping shape and the ``"vidit:cheap,asha:frontier"`` shape
        that ``half.config`` uses for mains, so a deployment expresses tiers the
        way it already expresses everything else.

        A tier name outside the enum is refused **here**, at load, rather than
        at the first call. The difference matters: a typo caught at startup is
        a failed boot, and a typo caught at the first call is a main whose
        nightly pass silently never ran.
        """
        if isinstance(assignments, str):
            try:
                assignments = parse_pairs(assignments, what="tier assignments")
            except (ValueError, StoreError) as exc:
                raise UnknownTier(str(exc)) from None
        parsed: dict[str, Tier] = {}
        for main_id, name in assignments.items():
            try:
                parsed[main_id] = Tier(name)
            except ValueError:
                raise UnknownTier(
                    f"{name!r} is not a tier this build knows "
                    f"({', '.join(sorted(t.value for t in Tier))}). A tier is "
                    "refused rather than defaulted: a silent fallback is "
                    "either a bill nobody authorised or a quality regression "
                    "nobody sees (AD-20)"
                ) from None
        return cls(mains=parsed, models=models or DEFAULT_MODELS)

    def of(self, main_id: str) -> Tier:
        """This main's tier, or a refusal."""
        tier = self.mains.get(main_id)
        if tier is None:
            raise UnknownTier(
                f"no tier is configured for main {main_id!r}. There is no "
                "global default to fall back to, by design (AD-20)"
            )
        return tier

    def spec_for(self, main_id: str) -> ModelSpec:
        """The model this main's calls run on."""
        tier = self.of(main_id)
        spec = self.models.get(tier)
        if spec is None:  # pragma: no cover - __post_init__ forbids it
            raise UnknownTier(f"this build has no model for tier {tier.value!r}")
        return spec

    def with_main(self, main_id: str, tier: Tier) -> "Tiers":
        """The same table with one main assigned. Frozen, so it returns a new
        one rather than mutating a table other callers are holding."""
        return replace(self, mains={**self.mains, main_id: tier})
