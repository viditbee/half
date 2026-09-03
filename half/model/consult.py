"""The shape of a bounded, capped, breaker-guarded, counted consultation.

Three modules had grown their own copy of this — ``half.crisis.classifier``,
``half.correction.candidate`` and ``half.voice.gate`` — and each copy's own
docstring said so, recorded the cost, and left it. By the third the arithmetic
was plain: a correction to one of them had to be made three times or it was made
once and forgotten twice. It was, twice: story 6d's review turned the holder
check from a denylist into an allowlist and split ``raised`` from ``unreadable``
in one module, and story 13a fixed the report's mutually-exclusive branches in
one module. This is where a fix like that is made once.

**What lives here is the shape, and the policy is the caller's.** Five numbers
were byte-identical in all three copies and are here: how many consecutive
failures stand a holder down, how often the counts go out, how many
consultations make a rate evidence rather than arithmetic, and the two ceilings.
Three numbers differed, and differed *for reasons* — a bound is a waiting main
against a nightly pass, a stand-down is turns against mornings, an alarm rate is
what failure rate is worth waking somebody for — so they are injected and are
never defaulted here.

**Nothing here knows what it is consulting about.** No label, no instruction, no
outcome type, no domain vocabulary: this module cannot name a crisis, a
correction or a morning, and there is no parameter through which one could
arrive. That is not tidiness. ``tests/test_crisis_golden.py`` pins the crisis
label set and its instructions by digest as clinical-review material, and a
shared module that held any of it would turn that pin into a pin on a base class
and mean nothing.

**Nothing here logs, and that is deliberate.** Each caller proves that no log
line it writes can carry content, by scanning *the arguments of the logging
calls in its own files* — ``tests/test_classifier.py`` over ``half/crisis``,
``tests/test_model.py`` over ``half/model``, and the same shape for the voice. A
report routed through a shared ``write`` would move those calls out from under
the scan that is the whole guarantee. So this module decides *whether* the
counts are due and returns which kind; the caller writes the line, in its own
words, where its own guard can see it.

**Nothing here reads a clock, opens a store, or holds state that outlives a
process** (AD-30). The breaker counts in whatever unit its caller counts in —
turns for a main who is waiting, mornings for a pass that runs once a day —
because a clock read here would put one in three modules at once.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Final

from half.model.port import Failure

# ── the numbers that were the same in all three copies ───────────────────────
#
# Measured rather than asserted: each of these was byte-identical in
# ``half/crisis/classifier.py``, ``half/correction/candidate.py`` and
# ``half/voice/gate.py`` before this module existed. The three that differed —
# the bound, how long a stand-down lasts, and the rate worth an alarm — are
# injected and have no default here, so a fourth caller has to answer them
# rather than inherit somebody else's answer by accident.

#: Consecutive failures that stand one holder down. Five, in all three: enough
#: that a single bad reply is not an outage, few enough that an outage is not
#: paid for on every call.
BREAK_AFTER: Final[int] = 5

#: How often the running counts are written out, counted in consultations.
#: **On its own this is not enough**, which is what ``due`` below exists to say:
#: a wholly failing consultation would otherwise be silent until it reached a
#: round number.
REPORT_EVERY: Final[int] = 100

#: Below this many consultations a rate is arithmetic rather than evidence, so
#: the alarm holds its fire. Also the interval it fires on above that.
ALARM_AFTER: Final[int] = 10

#: Ceilings for one call and for one process's worth of them, in millionths of
#: a dollar. Identical in all three, and the third module's docstring said why
#: plainly: they answer the same question — *what is an absurd amount to spend
#: on one call, and on one process* — and nobody has yet had a reason to answer
#: it differently. The per-call figure is the one that binds, and the port's
#: budget checks it before the transport is touched; the per-pass figure is a
#: runaway stop rather than a cost target.
PER_CALL_MICRO_USD: Final[int] = 100_000
PER_PASS_MICRO_USD: Final[int] = 500_000_000


# ── what an operator is owed, and when ───────────────────────────────────────


class Due(StrEnum):
    """Whether the counts should go out now, and at which level.

    A value rather than two booleans, so a caller cannot write the branch that
    was wrong in all three copies: the periodic line and the alarm are not
    independent questions, and treating them as two ``if``s is how they became
    mutually exclusive in the first place.
    """

    #: Not yet.
    NOTHING = "nothing"
    #: The round number. An ordinary line, at ``info``.
    PERIODIC = "periodic"
    #: The rate is evidence. The same counts, at ``error``.
    ALARM = "alarm"


def due(count: int, rate: float, *, alarm_rate: float) -> Due:
    """Whether ``count`` consultations at ``rate`` are worth a line, and which.

    **The alarm is asked first, and that is the fix this module exists to make
    once.** All three copies asked the periodic question first and hung the
    alarm off an ``elif``, so the two were mutually exclusive — and at the
    hundredth consultation, and every hundredth after, a wholly failing
    consultation reported at ``info`` instead of ``error``. The one line an
    operator watches for went missing at exactly the round numbers they would
    look at. Story 13a found it in the voice and fixed it there; the same bug
    was still sitting in the other two, which is the argument for this module
    made checkable rather than asserted.

    ``alarm_rate`` is the caller's, and has no default: what failure rate is
    worth waking somebody for is a policy question, and a fifth of a waiting
    main's turns is not the same number as half of a nightly pass's mornings.

    Pure, and a function of its arguments alone — so the branch that was wrong
    in three places can be exercised directly, at every count, without driving
    a hundred consultations through a provider double.
    """
    if (
        count >= ALARM_AFTER
        and rate >= alarm_rate
        and count % ALARM_AFTER == 0
    ):
        return Due.ALARM
    if count % REPORT_EVERY == 0:
        return Due.PERIODIC
    return Due.NOTHING


# ── the breaker ──────────────────────────────────────────────────────────────


class Breaker:
    """Stop consulting a holder that is not answering, for a while, per holder.

    During an outage every call would otherwise pay the full bound and then
    issue another doomed request — the latency and the spend of asking a
    question nobody is answering. After ``BREAK_AFTER`` consecutive failures
    this holder goes quiet for ``break_for`` units, and then tries again.

    **Per holder, because one main's provider being down says nothing about
    another's.** A global breaker would silently take the consultation away from
    everybody because of one bad key.

    **Counted in whatever unit the caller counts in**, never in seconds: a turn
    for a main who is waiting, a morning for a pass that runs once a day. That
    is what keeps AD-30 true of the three callers — a clock read here would put
    one in all of them at once.

    It decides and it does not speak. ``note`` says *this one tripped it*, and
    the caller writes the line, so the log stays under the scan that proves no
    log line on that path can carry content.
    """

    __slots__ = ("_break_for", "_consecutive", "_quiet")

    def __init__(self, *, break_for: int) -> None:
        self._break_for = break_for
        #: holder -> consecutive failures, and holder -> units still to skip.
        self._consecutive: dict[str, int] = {}
        self._quiet: dict[str, int] = {}

    def spend(self, holder_id: str) -> bool:
        """Spend one unit of this holder's stand-down; say whether it is on.

        **The countdown advances on every unit, including the ones that would
        not have consulted anyway.** Story 13a found the other arrangement in
        the voice: a holder stood down for twenty mornings who then had a quiet
        fortnight stayed silent for a month and a half, because the countdown
        only ran on mornings that reached a holder. The unit is the unit.
        """
        left = self._quiet.get(holder_id, 0)
        if left <= 0:
            return False
        self._quiet[holder_id] = left - 1
        return True

    def note(self, holder_id: str, *, failed: bool) -> bool:
        """Record one outcome. ``True`` when *this* one tripped the breaker.

        A caller with an outcome that is neither a success nor a provider
        failure — the voice's leak and its raise, which say this build is wrong
        rather than that the provider is down — simply does not call this. That
        is deliberate and is story 13a's first finding: arming on those meant
        five consecutive breaches bought twenty mornings during which the
        tripwire was never reached and nothing was logged, which is an alarm
        with a snooze button wired to the alarm.
        """
        if not failed:
            self._consecutive[holder_id] = 0
            return False
        run = self._consecutive.get(holder_id, 0) + 1
        self._consecutive[holder_id] = run
        if run < BREAK_AFTER:
            return False
        self._consecutive[holder_id] = 0
        self._quiet[holder_id] = self._break_for
        return True


# ── the narrow holder ────────────────────────────────────────────────────────


def wider_than(holder: object, allowed: frozenset[str]) -> list[str]:
    """Public methods on ``holder`` outside ``allowed``, sorted.

    **An allowlist, and story 13a's review is the reason it is spelled this
    way.** The check this replaced was a denylist of six method names, so an
    object that could ``classify`` and also ``chat``, ``invoke`` or ``run``
    walked straight through — and the review found a replacement passing only
    because one test double happened to carry ``classify``. The port's
    protocols are narrow *because of the methods they lack*, so what is checked
    is that there are none, over every name the object actually has rather than
    over the names somebody thought to forbid.

    An empty list is a narrow holder. The caller decides what to do about a
    non-empty one, in its own words, because the sentence an operator reads
    ("hand over the narrow classifier, not the provider that owns it") is about
    that caller's own path.

    ``callable(getattr(...))`` rather than ``inspect``: a bound method, a
    ``functools.partial``, a callable attribute and a nested class are all ways
    to reach past the protocol, and all of them are callable.
    """
    return sorted(
        name for name in dir(holder)
        if not name.startswith("_")
        and name not in allowed
        and callable(getattr(holder, name, None))
    )


# ── the bound ────────────────────────────────────────────────────────────────


def refuses_as_a_bound(value: object) -> bool:
    """What all three constructors have always refused: a bool, a non-number,
    or a number at or below zero.

    **``NaN`` passes this, and that is stated rather than quietly fixed.** Every
    comparison against a NaN is ``False``, so ``value <= 0`` admits one — and
    ``asyncio.timeout(nan)`` never fires, which is a main waiting on a hung
    provider through the guard that exists to stop exactly that. ``a_bound``
    below is the predicate that closes it, and it is the one the *per-call*
    override in two of the three callers already uses.

    Closing it here as well would be a behaviour change in three constructors
    inside a refactor, which is the one thing a refactor may not do. It is
    reported instead.
    """
    return (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value <= 0
    )


def a_bound(value: object) -> bool:
    """Whether ``asyncio.timeout`` will actually fire on ``value``.

    Positive, a number, not a bool, and **finite** — which is the half
    ``refuses_as_a_bound`` leaves open. Infinity and NaN are both refused here
    and for the same reason: a timeout that never fires is not a bound, it is a
    guard that reports success.
    """
    return not refuses_as_a_bound(value) and math.isfinite(value)  # type: ignore[arg-type]


# ── the counts ───────────────────────────────────────────────────────────────
#
# The counters themselves stay with their callers: what a consultation counts
# is what it is *about*, and the three tallies genuinely differ — one counts
# labels, one counts proposals and confirmations, one counts attempts, refusals
# and silences. What is shared is how a count is made and how a rate is taken,
# which is where two of the three copies could have drifted apart without any
# test noticing.


def failure_key(failure: Failure) -> str:
    """The key one of the port's failures is counted under.

    Two closed enums and a separator, so a counter holds constants and never a
    provider's own sentence (AD-22). Spelled once because three spellings of it
    are three keys an operator's dashboard would have to know about.
    """
    return f"{failure.kind}/{failure.because}"


def count_one(counter: dict[str, int], key: str) -> None:
    """Add one to ``key``. Counts and nothing else."""
    counter[key] = counter.get(key, 0) + 1


def rate(part: int, whole: int) -> float:
    """``part`` over ``whole``, where no consultations reads as zero.

    **Zero is not an error here**, which is the interesting half: a build with
    no model wired is a supported deployment, so a rate that raised — or that
    reported one — on an empty denominator would alarm on every deployment that
    had not equipped anybody.
    """
    return part / whole if whole else 0.0
