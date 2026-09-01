"""Cost ceilings, and the refusal that happens before the spend (CAP-7).

CAP-7 says the nightly pass runs *within a fixed per-user cost budget*. That is
only true if three things hold, and review round 1 found that only the first
one did.

**The budget is checked before the call.** A ceiling enforced on the way out is
an accounting entry, and the money is already gone. So this module estimates
first, and the estimate is what admission is decided on.

**Admission reserves.** Checking a ceiling and then leaving the total unchanged
until the reply comes back does not bind when calls overlap: every one of them
is admitted against the same figure. Verified at the concurrency the scheduler
actually ships with — eight calls at ``half.schedule.tick.DEFAULT_BOUND``, a
seven-thousand ceiling, forty-eight thousand spent and nothing refused. So
``admit`` returns a ``Reservation`` that is *already counted*, and ``settle``
exchanges it for what the call really cost. Reserving high and settling low is
the safe direction; the reverse is the bug that was there.

**The estimate errs high in every script.** A characters-per-token constant
tuned on Latin prose under-charges Chinese, Japanese, Thai and Devanagari by a
multiple — 300 CJK characters estimated to the same 108 tokens as 300 Latin
ones, against a real cost near 300. ``half/text.py`` exists in this tree
because exactly this assumption was wrong one layer over, where it made
non-Latin beliefs unretrievable; here it spends money the budget said was not
there, for exactly the mains the reach requirement is about.

**Estimating is not charging.** After a call returns, ``settle`` records what it
actually cost from the provider's own usage numbers, so the pass total is real
rather than a running sum of worst cases. Where those numbers are missing,
mistyped or absurd the reservation stands as the charge — a completed call must
never advance the ledger by nothing, which is a ceiling that cannot bind, and
must never advance it by a number a provider made up, which is a pass that
refuses everything after one reply.

Nothing here reads a clock, a key or the environment. A budget is arithmetic
over what it is given.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
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

#: Characters per token for **ASCII** text, where "characters per token" is a
#: meaningful thing to say at all. English prose runs nearer four; three is used
#: so the estimate leans high, which is the safe direction.
ASCII_CHARS_PER_TOKEN = 3

#: Tokens per **non-ASCII** character, as a fraction. Chinese, Japanese and
#: Korean run at roughly one token per character and Thai and the Indic scripts
#: at one or more; the worst measurement on the table was 1,600 Japanese
#: characters against 2,400 real tokens, which is where 3/2 comes from. It is
#: deliberately the top of the measured band and not the middle: erring high
#: refuses a call that would have fit, and erring low spends money the budget
#: said was not there. Only one of those is recoverable.
NON_ASCII_TOKENS_NUMERATOR = 3
NON_ASCII_TOKENS_DENOMINATOR = 2

#: Tokens added per block and per turn for the structure around the text —
#: role markers, block delimiters, the schema on a constrained reply. Small and
#: fixed; it exists so that a prompt of many tiny blocks is not estimated at
#: nearly zero.
TOKENS_PER_BLOCK = 8

#: The most tokens a single reported usage field is believed. A provider that
#: reports 10^18 input tokens is not describing a request that was made, and
#: charging it would silently refuse the rest of a pass on one reply. Set far
#: above any real request — the largest context window in the table is a
#: million — so a true count is never clipped, and an absurd one is treated as
#: unreadable rather than as a bill.
MAX_REPORTED_TOKENS = 10_000_000


def tokens_in(text: str) -> int:
    """A deliberately generous token estimate for one block of text.

    Not a tokenizer and not pretending to be one. The provider's own counter
    needs a network call, and this module has to be able to refuse a call on a
    machine with no key and no route to anything.

    **Counted per script, because one constant is wrong somewhere.** The
    boundary is ASCII, which is coarse and is meant to be: everything outside
    it is charged at the top of the measured band, so Devanagari, Thai, kana,
    Han and Hangul are all estimated at or above their real cost rather than at
    a third of it. Being wrong high for Cyrillic is a refusal somebody can
    argue with; being wrong low for Japanese is a bill nobody sees.
    """
    ascii_chars = sum(1 for character in text if character.isascii())
    other = len(text) - ascii_chars
    return (
        ceil_div(ascii_chars, ASCII_CHARS_PER_TOKEN)
        + ceil_div(other * NON_ASCII_TOKENS_NUMERATOR, NON_ASCII_TOKENS_DENOMINATOR)
        + TOKENS_PER_BLOCK
    )


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
    A caller that knows better says so on its own ``Breakpoint``, which is the
    only place the claim can be made honestly.

    **A prefix under the model's own minimum is priced as uncached**, because
    that is what the provider will do: a marker under the minimum caches
    nothing, silently, with no error and no cache-creation tokens. The renderer
    refuses such a breakpoint outright (AD-19, *never hidden*); this keeps the
    arithmetic honest for a caller pricing a prompt before it builds one.
    """
    cached_tokens = sum(tokens_in(block) for block in cached_text)
    plain_tokens = sum(tokens_in(block) for block in uncached_text)

    if cached_tokens and cached_tokens < spec.cache_min_tokens:
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
    spec: ModelSpec,
    reported: Mapping[str, Any],
    *,
    ttl_basis: int = CACHE_WRITE_BASIS_5M,
    batched: bool = False,
    floor_micro_usd: int = 0,
) -> Usage:
    """What a call actually cost, from the provider's own usage numbers.

    ``ttl_basis`` is the TTL the *request* asked for, carried in by the caller.
    The reply does not say which TTL wrote an entry, so reading the creation
    count and pricing it at the cheaper of the two under-charged every
    hour-long write by three eighths — and the comment that justified it was
    wrong twice over: the estimate charges nothing, only this does.

    ``floor_micro_usd`` is the reservation this call was admitted on. Where the
    usage block is missing, mistyped or absurd, that floor is what the ledger
    records — a completed call must not advance the pass total by nothing,
    which is how a ceiling stops binding, and must not advance it by a number a
    provider invented, which is how one reply refuses the rest of a pass.
    """
    counts = [
        _count(reported, name)
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
    ]
    if any(count is None for count in counts):
        # Unreadable in whole or in part. Charging the part that parsed would
        # be a number nobody can defend, so the reservation stands.
        return Usage(micro_usd=max(0, floor_micro_usd))

    input_tokens, output_tokens, read, write = counts
    micro = (
        spec.input_micro_usd(input_tokens)
        + spec.cache_read_micro_usd(read)
        + spec.cache_write_micro_usd(write, ttl_basis=ttl_basis)
        + spec.output_micro_usd(output_tokens)
    )
    if batched:
        micro = ceil_div(micro * BATCH_BASIS, BASIS)

    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=read,
        cache_write_tokens=write,
        micro_usd=max(micro, max(0, floor_micro_usd)),
    )


def _count(reported: Mapping[str, Any], name: str) -> int | None:
    """One usage field, or ``None`` if it is not a count this build believes.

    A missing field is zero — the provider omits what it did not use. A field
    of the wrong type, a negative one, or one past ``MAX_REPORTED_TOKENS`` is
    ``None``, which makes the whole usage block unreadable and falls back to
    the reservation.
    """
    if not isinstance(reported, Mapping):
        return None
    value = reported.get(name)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > MAX_REPORTED_TOKENS:
        return None
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


@dataclass(frozen=True, slots=True)
class Reservation:
    """An admitted call's claim on the pass budget, already counted.

    Held by the caller between ``admit`` and ``settle``. It exists so that the
    figure a *concurrent* call is admitted against includes this one — the
    whole of what review round 1 found missing.

    ``serial`` is what makes a reservation *this ledger's*, and it is read:
    ``Spend`` keeps the outstanding serials and refuses anything it did not
    issue or has already exchanged. Round 1 documented that intent and never
    implemented it — ``_release`` checked the type and then clamped the
    subtraction at zero, so settling one reservation twice recorded 120 against
    a 100 ceiling, a reservation from a *different* ledger settled clean, and a
    hand-constructed one drove the outstanding total to zero through the clamp
    and let the pass admit past its own ceiling. A value object is not a
    capability; the issuing ledger's record of it is.
    """

    micro_usd: int
    serial: int


@dataclass(frozen=True, slots=True)
class Ledger:
    """A pass's spending, as a value that survives the process that spent it.

    ``Submission`` is deliberately durable so that the evening's pass can be
    collected in the morning (AD-9). A ledger that resets on restart while the
    batch it paid for survives is not a ceiling — a crash between submission
    and dawn hands the next pass a fresh full budget with the committed work
    unaccounted. So the pass total serializes the same way the submission does,
    and a caller persists the two together.
    """

    per_call_micro_usd: int
    per_pass_micro_usd: int
    spent_micro_usd: int
    calls: int

    def to_json(self) -> str:
        return json.dumps(
            {
                "per_call_micro_usd": self.per_call_micro_usd,
                "per_pass_micro_usd": self.per_pass_micro_usd,
                "spent_micro_usd": self.spent_micro_usd,
                "calls": self.calls,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Ledger":
        data = json.loads(raw)
        if not isinstance(data, Mapping):
            raise ValueError("a ledger is a JSON object")
        values: dict[str, int] = {}
        for name in (
            "per_call_micro_usd", "per_pass_micro_usd", "spent_micro_usd", "calls",
        ):
            value = data.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"a ledger's {name} is a whole number")
            values[name] = value
        return cls(**values)


class Spend:
    """One pass's running total, and the gate every call goes through.

    Mutable and shared on purpose: the classifier, the generator and the
    batcher a provider hands out all charge the *same* ledger, or the per-pass
    ceiling is a per-object ceiling and CAP-7's bound is three times what it
    says.

    **Admission reserves, and settlement exchanges the reservation for the
    truth.** ``admit`` returns a ``Reservation`` when the call may proceed and
    a ``Reason`` when it may not. It never raises and never spends — reserving
    is not spending, and a released reservation costs nothing.

    **Atomic under asyncio, which is the concurrency this port has.** ``admit``
    and ``settle`` contain no ``await``, so an overlapping call cannot be
    scheduled between the check and the reservation. That is the whole
    argument; if a caller ever runs a ``Spend`` across threads it needs a lock,
    and this docstring is where that would be said.
    """

    __slots__ = ("budget", "_spent", "_outstanding", "_calls", "_serial")

    def __init__(self, budget: Budget, *, spent: int = 0, calls: int = 0) -> None:
        self.budget = budget
        self._spent = max(0, spent)
        #: serial -> the amount that serial is holding. The *record of
        #: issuance*, which is what makes a reservation exchangeable exactly
        #: once and only by this ledger.
        self._outstanding: dict[int, int] = {}
        self._calls = max(0, calls)
        self._serial = 0

    @classmethod
    def restored(cls, ledger: Ledger) -> "Spend":
        """A pass picked up where a previous process left it."""
        return cls(
            Budget(
                per_call_micro_usd=ledger.per_call_micro_usd,
                per_pass_micro_usd=ledger.per_pass_micro_usd,
            ),
            spent=ledger.spent_micro_usd,
            calls=ledger.calls,
        )

    def snapshot(self) -> Ledger:
        """The durable form. Outstanding reservations are deliberately absent:
        a call in flight when the process died did not complete, and recording
        it as spent would charge a pass for work nobody received."""
        return Ledger(
            per_call_micro_usd=self.budget.per_call_micro_usd,
            per_pass_micro_usd=self.budget.per_pass_micro_usd,
            spent_micro_usd=self._spent,
            calls=self._calls,
        )

    @property
    def spent_micro_usd(self) -> int:
        return self._spent

    @property
    def reserved_micro_usd(self) -> int:
        return sum(self._outstanding.values())

    @property
    def committed_micro_usd(self) -> int:
        """Spent plus reserved — the figure admission is decided against."""
        return self._spent + self.reserved_micro_usd

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def remaining_micro_usd(self) -> int:
        return max(0, self.budget.per_pass_micro_usd - self.committed_micro_usd)

    def admit(self, estimate: Estimate) -> Reservation | Reason:
        """Whether this call may be made, reserving it if so.

        Checked per call *and* against the pass total, in that order, so the
        reason a caller is told is the tighter of the two rather than whichever
        happened to be evaluated first.
        """
        if estimate.micro_usd > self.budget.per_call_micro_usd:
            return Reason.PER_CALL_BUDGET
        if self.committed_micro_usd + estimate.micro_usd > (
            self.budget.per_pass_micro_usd
        ):
            return Reason.PER_PASS_BUDGET
        self._serial += 1
        self._outstanding[self._serial] = estimate.micro_usd
        return Reservation(micro_usd=estimate.micro_usd, serial=self._serial)

    @contextmanager
    def hold(self, estimate: Estimate) -> Iterator["Reservation | Reason"]:
        """Admit, and give the reservation back on **every** path out.

        This exists because review round 2 found the class of bug the round-1
        fix left open. Three round-1 changes combined into a fourth defect: the
        cache-minimum refusal raises from the renderer, the renderer was called
        after ``admit`` and outside any handler, and the ledger had just been
        made durable — so a caller retrying a mis-stated breakpoint drained the
        pass to zero and every honest call after it was refused with nothing
        sent. A ceiling that binds against money nobody spent is the same
        defect as one that does not bind, pointing the other way.

        A handler at each call site would have fixed those two sites. The
        control structure fixes the class: the reservation is released when the
        block exits unless it was settled inside it, however it exits.
        """
        outcome = self.admit(estimate)
        try:
            yield outcome
        finally:
            if isinstance(outcome, Reservation) and outcome.serial in (
                self._outstanding
            ):
                self.release(outcome)

    def settle(self, reservation: Reservation, usage: Usage) -> None:
        """Exchange a reservation for what the call actually cost.

        A settled call may cost more than it reserved — a provider's real usage
        is not this module's to bound — and the pass total may therefore end
        slightly over its ceiling. That is unavoidable: money already spent
        cannot be un-spent, and the ceiling's job is to stop the *next* call.
        """
        self._take(reservation)
        self._spent += max(0, usage.micro_usd)
        self._calls += 1

    def release(self, reservation: Reservation) -> None:
        """Give back a reservation for a call that never happened."""
        self._take(reservation)

    def _take(self, reservation: Reservation) -> None:
        """Remove one outstanding reservation, or refuse loudly.

        **Issuance, not type.** Round 1 checked ``isinstance`` and then clamped
        the subtraction at zero, which turned every misuse into a silent
        corruption of the one number CAP-7 rests on. Each of these is a
        programming mistake with no honest outcome, so each is an exception:
        a total that is quietly wrong is worse than a call that fails.
        """
        if not isinstance(reservation, Reservation):
            raise BudgetError(
                f"{type(reservation).__name__} is not a reservation; only this "
                "ledger's own can be exchanged"
            )
        held = self._outstanding.pop(reservation.serial, None)
        if held is None:
            raise BudgetError(
                "this reservation is not outstanding on this ledger — it was "
                "issued by another, already exchanged, or constructed by hand. "
                "Clamping the difference to zero is what made each of those a "
                "silently wrong pass total rather than a loud one"
            )
        if held != reservation.micro_usd:
            # The serial matched but the amount does not: a forged or mutated
            # value object. The ledger's own record is the authority.
            self._outstanding[reservation.serial] = held
            raise BudgetError(
                "this reservation's amount does not match what the ledger "
                "issued under that serial"
            )

    def reset(self) -> None:
        """Begin a new pass.

        Explicit, and there is no clock here that could do it: a ledger that
        rolled over at midnight would need to know what midnight is, and
        exactly one module in this tree reads a clock (AD-30).
        """
        self._spent = 0
        self._outstanding.clear()
        self._calls = 0
