"""Cost ceilings, and the refusal that happens before the spend (CAP-7).

CAP-7 says the nightly pass runs *within a fixed per-user cost budget*. That is
only true if the budget is checked before the call rather than after it: a
ceiling enforced on the way out is an accounting entry, not a limit, and the
money is already gone.

So this module estimates first. Two ceilings, because one is not enough:

* **per call** — one runaway prompt cannot consume the whole night on its own.
* **per pass** — a thousand small calls cannot either, which is the shape the
  all-pairs comparison CAP-7 forbids would actually arrive in.

**The estimate is deliberately pessimistic.** There is no token counter here
that does not cost a network round trip, and the port must construct and refuse
with no network at all — so tokens are estimated from the text, generously, and
the whole output ceiling is assumed spent. Erring high refuses a call that
would have fit; erring low spends money the budget said was not there. Only one
of those is recoverable.

**Estimating is not charging.** After a call returns, ``charge`` records what it
actually cost from the provider's own usage numbers, so the pass total is real
rather than a running sum of worst cases. An estimate that ran high does not
eat the rest of the night.

Nothing here reads a clock, a key or the environment. A budget is arithmetic
over what it is given.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from half.errors import BudgetError
from half.model.port import Reason, Usage
from half.model.tier import (
    BASIS,
    BATCH_BASIS,
    CACHE_WRITE_BASIS_5M,
    ModelSpec,
    ceil_div,
)

#: Characters per token, for the offline estimate. English prose runs nearer
#: four; three is used so the estimate leans high, which is the safe direction
#: (see the module docstring). It is a constant rather than a setting because a
#: deployment that could tune it could tune the refusal away.
CHARS_PER_TOKEN = 3

#: Tokens added per block and per turn for the structure around the text —
#: role markers, block delimiters, the schema on a constrained reply. Small and
#: fixed; it exists so that a prompt of many tiny blocks is not estimated at
#: nearly zero.
TOKENS_PER_BLOCK = 8


def tokens_in(text: str) -> int:
    """A deliberately generous token estimate for one block of text.

    Not a tokenizer and not pretending to be one. The provider's own counter
    needs a network call, and this module has to be able to refuse a call on a
    machine with no key and no route to anything.
    """
    return ceil_div(len(text), CHARS_PER_TOKEN) + TOKENS_PER_BLOCK


@dataclass(frozen=True, slots=True)
class Estimate:
    """What a call will cost at worst, before it is made.

    Every field is a count except the total, and the total is integer
    millionths of a dollar, so the comparison a budget makes is exact.
    """

    #: Tokens that will be processed at the full input price.
    input_tokens: int = 0
    #: Tokens expected to be served from an existing cache entry.
    cache_read_tokens: int = 0
    #: Tokens expected to be written to the cache this call.
    cache_write_tokens: int = 0
    #: The output ceiling. Assumed spent in full.
    output_tokens: int = 0
    micro_usd: int = 0

    @property
    def caching(self) -> bool:
        """Whether this call claims any caching at all.

        False for a caller that stated no breakpoint — and the cost reflects
        it, which is the point of reporting it rather than hiding it (AD-19).
        """
        return bool(self.cache_read_tokens or self.cache_write_tokens)


def estimate(
    spec: ModelSpec,
    *,
    cached_text: tuple[str, ...] = (),
    uncached_text: tuple[str, ...] = (),
    max_output_tokens: int,
    ttl_basis: int = CACHE_WRITE_BASIS_5M,
    warm: bool = False,
    batched: bool = False,
) -> Estimate:
    """Price a call before it is made.

    ``cached_text`` is the stable prefix the caller marked; ``uncached_text`` is
    everything after the breakpoint. Splitting them is what makes the free
    tier's economics visible at the point of decision instead of on an invoice.

    ``warm`` says whether the prefix is expected to be a cache *read* rather
    than a *write*. It defaults to false, the expensive answer, because a
    budget that assumes a warm cache admits calls on the assumption that
    something else already paid — and on the first call of a pass, nothing has.

    **A prefix under the model's own minimum is priced as uncached**, because
    that is what the provider will do: a marker under the minimum caches
    nothing, silently, with no error and no cache-creation tokens. Pricing it
    as cached would make the one number the free tier depends on optimistic in
    exactly the case where it is wrong.
    """
    cached_tokens = sum(tokens_in(block) for block in cached_text)
    plain_tokens = sum(tokens_in(block) for block in uncached_text)

    if cached_tokens and cached_tokens < spec.cache_min_tokens:
        # Below the model's minimum the marker does nothing. Price the honest
        # thing rather than the requested thing.
        plain_tokens += cached_tokens
        cached_tokens = 0

    read = cached_tokens if warm else 0
    write = 0 if warm else cached_tokens

    micro = (
        spec.input_micro_usd(plain_tokens)
        + spec.cache_read_micro_usd(read)
        + spec.cache_write_micro_usd(write, ttl_basis=ttl_basis)
        + spec.output_micro_usd(max_output_tokens)
    )
    if batched:
        micro = ceil_div(micro * BATCH_BASIS, BASIS)

    return Estimate(
        input_tokens=plain_tokens,
        cache_read_tokens=read,
        cache_write_tokens=write,
        output_tokens=max_output_tokens,
        micro_usd=micro,
    )


def charged(
    spec: ModelSpec, reported: Mapping[str, Any], *, batched: bool = False
) -> Usage:
    """What a call actually cost, from the provider's own usage numbers.

    Reads defensively: a usage block this build cannot parse yields zeros
    rather than an exception, because a reply that arrived and was used must
    not be turned into a failure by an accounting field. An unparsed usage
    under-reports the pass total, which the per-call ceiling still bounds.
    """
    input_tokens = _count(reported, "input_tokens")
    output_tokens = _count(reported, "output_tokens")
    read = _count(reported, "cache_read_input_tokens")
    write = _count(reported, "cache_creation_input_tokens")

    micro = (
        spec.input_micro_usd(input_tokens)
        + spec.cache_read_micro_usd(read)
        # The reported creation count does not say which TTL wrote it, so it is
        # priced at the cheaper of the two. The caller chose the TTL and the
        # estimate already charged the right one; this is reconciliation, and
        # over-charging here would make a pass stop early on arithmetic.
        + spec.cache_write_micro_usd(write, ttl_basis=CACHE_WRITE_BASIS_5M)
        + spec.output_micro_usd(output_tokens)
    )
    if batched:
        micro = ceil_div(micro * BATCH_BASIS, BASIS)

    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=read,
        cache_write_tokens=write,
        micro_usd=micro,
    )


def _count(reported: Mapping[str, Any], name: str) -> int:
    value = reported.get(name) if isinstance(reported, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


@dataclass(frozen=True, slots=True)
class Budget:
    """Two ceilings, in millionths of a dollar.

    A ceiling of zero, or a per-call ceiling above the per-pass one, is a
    misconfiguration rather than a very strict budget: the first refuses every
    call forever and the second means the per-call limit never binds. Both are
    refused loudly at construction, because a nightly pass that silently does
    nothing looks exactly like a nightly pass with nothing to say.
    """

    per_call_micro_usd: int
    per_pass_micro_usd: int

    def __post_init__(self) -> None:
        for name, value in (
            ("per_call_micro_usd", self.per_call_micro_usd),
            ("per_pass_micro_usd", self.per_pass_micro_usd),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise BudgetError(
                    f"{name} must be a positive number of millionths of a "
                    f"dollar; {value!r} admits nothing at all"
                )
        if self.per_call_micro_usd > self.per_pass_micro_usd:
            raise BudgetError(
                f"a per-call ceiling of {self.per_call_micro_usd} above the "
                f"per-pass {self.per_pass_micro_usd} never binds; one of the "
                "two limits is not the one that was meant"
            )


class Spend:
    """One pass's running total, and the gate every call goes through.

    Mutable and shared on purpose: the classifier, the generator and the
    batcher a provider hands out all charge the *same* ledger, or the per-pass
    ceiling is a per-object ceiling and CAP-7's bound is three times what it
    says.

    ``admit`` returns ``None`` when the call may proceed and the ``Reason`` it
    may not otherwise. It never raises and never spends: refusing is the whole
    of what it does.
    """

    __slots__ = ("budget", "_spent", "_calls")

    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self._spent = 0
        self._calls = 0

    @property
    def spent_micro_usd(self) -> int:
        return self._spent

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def remaining_micro_usd(self) -> int:
        return max(0, self.budget.per_pass_micro_usd - self._spent)

    def admit(self, estimate: Estimate) -> Reason | None:
        """Whether this call may be made. ``None`` means yes.

        Checked per call *and* against the pass total, in that order, so the
        reason a caller is told is the tighter of the two rather than whichever
        happened to be evaluated first.
        """
        if estimate.micro_usd > self.budget.per_call_micro_usd:
            return Reason.PER_CALL_BUDGET
        if self._spent + estimate.micro_usd > self.budget.per_pass_micro_usd:
            return Reason.PER_PASS_BUDGET
        return None

    def charge(self, usage: Usage) -> None:
        """Record what a completed call actually cost."""
        self._spent += max(0, usage.micro_usd)
        self._calls += 1

    def reset(self) -> None:
        """Begin a new pass.

        Explicit, and there is no clock here that could do it: a ledger that
        rolled over at midnight would need to know what midnight is, and
        exactly one module in this tree reads a clock (AD-30).
        """
        self._spent = 0
        self._calls = 0
