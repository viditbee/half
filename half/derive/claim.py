"""Whether a message is worth keeping (CAP-5, AD-19, AD-22, story 15a).

``half.actor.runtime`` wrote every inbound message into a main's ledger as a
stated belief. ``ok``, ``thanks`` and ``hello?`` were therefore beliefs — ranked
by retrieval, quotable once promoted, eligible for a tension against the
revealed side, and the thing a correction aims at. This is the thing that
decides.

**The shape is ``half.model.consult``'s and the policy is here**, which is the
fourth caller of it and not the fifth copy. The breaker, the ceilings, the
holder allowlist, the report cadence and the alarm branch are that module's;
what is this module's own is what the shape refuses to hold — the gates, the
labels, the instructions, and the three numbers that differ between callers for
reasons.

**One derivation is four consultations, and all four always happen.** CAP-5
calls its gates individually testable, and a set that stopped at the first
refusal could not be: every case for a later gate would pass whether that gate
worked or an earlier one refused first. The four run concurrently, each under
its own bound, so the wall clock is one bound rather than four — and the cost is
four cheap classifications per inbound message, which is stated plainly here
because it is the one number in this story an operator would want back. The
saving available is the batch shape ``half.consolidate.judge`` records the same
deferral for, and taking it needs a seam neither module has.

**Derivation runs after the reply and never in front of it.** A main waiting on
a model call to find out whether their message was worth keeping is the latency
failure story 13b spent a review round on. ``half.actor.runtime`` calls this
once the send has been attempted, so no path here can cost a main their answer:
absent, standing down, slow, refusing, over budget, unreadable or raising all
produce the same thing, which is no claim.

**A claim derived here is an *explicit* conclusion, and that is the vocabulary
rather than a simplification.** honcho separates a conclusion the person stated —
session-scoped, carrying a trustworthy stamp — from a deductive or inductive one
the system reached across sessions, which fails closed
(``src/utils/representation.py``; extraction manifest, marked taken). A message
is the main saying something now, so what a gate admits is the explicit kind:
its words are theirs, its evidence is the message, and its scope is the turn it
arrived on. The cross-session kind is the nightly pass's object and story 15b's,
and it fails closed here by simply not existing — there is no path in this module
that reaches a second record, a second session or a second main.

**The claim is the message's own words, and this module never touches them.** A
derivation decides *whether* there is a claim; it does not reword one, and it
does not hand one back — ``Derived`` has no field for text, so the caller writes
the words it already holds. That is not a shortcut. It is what keeps the reply's
own rule true on this path: the holder is a ``Classifier``, the object with **no
method that returns text**, so nothing here can author a sentence about a main
and put it in their ledger for ever. A claim in words Half chose is a different
object with a different risk, it needs the wider holder, and it is not this
story. What is here instead is the separation CAP-5 actually asks for: the
message is evidence, the claim cites it, and a message that carries no claim
leaves none.

**The tier is pinned, and it is not the main's** (``CLASSIFY_TIER``). SPEC's
constraint is that the recurring spend runs on a cheaper tier than conversation
*because the free tier depends on that gap*, and this is on every inbound
message of every main. A gate's whole output is one label from a closed set that
nobody reads, so there is nothing here for a better tier to buy on a main's
behalf — the same argument ``half.crisis.classifier``,
``half.correction.candidate`` and ``half.consolidate.judge`` make for pinning
theirs. A main is equipped by having a **key**, not by having been assigned a
tier.

**What leaves the machine: one message, four times, to a provider, and nothing
else.** No belief id, no subject, no ledger name, no loop, no stamp, no strand,
no contact; ``main_id`` travels on the ``Prompt`` because the port resolves a
tier from it and appears in no payload. That is not new in kind — the crisis
classifier and the correction widening already send the same message on the same
turn — but it is stated here because *telling a main that their messages leave
the machine* is an open launch blocker and this adds four calls to the count.

**Nothing durable, nothing quoted** (AD-22). The message reaches the provider
and nowhere else: not a log line, not the tally, not an exception message. The
tally's keys are gate names and labels from closed sets and ``kind/reason`` pairs
from the port's two closed enums, so there is no field on it a main's own words
could travel in — and every logging call in this file takes a ``main_id``, a
count, a gate name or an exception's class, never the exception's own text,
because a provider quotes the request it rejected.

**Nothing here reads a clock, opens a store, or writes a record** (AD-30). What
comes back is a value; ``half.actor.runtime`` appends it, at the weakest rung,
through ``half.governance.ladder.admitted``. Derivation decides whether there is
a claim and never what Half may do with it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from half.derive.gates import GATES, Admission, Gate, admission
from half.errors import DeriveError
from half.model import consult
from half.model.consult import (
    ALARM_AFTER,
    BREAK_AFTER,
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    REPORT_EVERY,
)
from half.model.port import (
    Classifier,
    Classify,
    Decision,
    Failure,
    Prompt,
    Role,
    Turn,
)

#: Structured, and content-free. Every value logged from this module is a gate
#: name, a label from a closed set, a count, an exception's class name, or a
#: ``main_id`` — never the message and never a claim (AD-22).
logger = logging.getLogger(__name__)


# ── the numbers that are this caller's ───────────────────────────────────────
#
# The ceilings, how often the counts go out, when a rate becomes evidence and
# how many consecutive failures trip the breaker are ``half.model.consult``'s
# and are re-exported above under the names the other three consultations use.
# The three below differ between callers *for reasons*, which is why the shared
# shape takes them and never supplies one.

#: How long one gate may run, in seconds.
#:
#: **Nobody is waiting for it, and it is still not the morning's twenty.** The
#: reply has already gone by the time this runs, so this is not a pause in front
#: of somebody who has just written — which is why it is not the turn path's two
#: seconds. What it *is* in front of is that main's **next** message: their turns
#: are handled one at a time by their own worker (``half.actor.runtime._Turns``),
#: so a derivation that ran for twenty seconds would sit between two messages of
#: a main typing quickly.
#:
#: So the bound is the whole budget a main already waits for one turn —
#: ``half.actor.runtime.TURN_DEADLINE_SECONDS`` — and the four gates run
#: concurrently, so a derivation costs one of these and not four. The relation is
#: pinned in ``tests/test_derive.py`` rather than at import, for the reason
#: ``half.voice.gate`` pins its own there: this module must not import the
#: runtime that imports it.
BOUND_SECONDS: Final[float] = 5.0

#: Which tier judges a message, for **every** main. Not the main's own
#: conversation tier, and this is the one number here that a constraint decides
#: rather than a preference — see the module docstring, and ``SPEC.md:124``.
#:
#: A **name** rather than an enum member, so this module cannot reach the model
#: package's tier table: the composition root parses it and a name this build
#: does not know is refused at boot. Pinned by value in ``tests/test_derive.py``,
#: so following the main again is a red test and a deliberate edit rather than a
#: quiet multiplication of every main's per-message bill.
CLASSIFY_TIER: Final[str] = "cheap"

#: The failure rate at which the counts are written out as an error instead of
#: at ``info``. **Policy, and this path's.**
#:
#: A fifth, which is the waiting paths' number rather than the morning's half.
#: This rate has no ordinary floor: a gate that produced no label is never
#: ordinary, because *cannot say* is an **answer** and is counted as one, so
#: everything in this numerator is a provider that did not work.
ALARM_RATE: Final[float] = 0.2

#: How many derivations this main's breaker stays open for once it trips.
#:
#: **Counted in derivations, not turns and not seconds** — nothing here reads a
#: clock (AD-30). Roughly a conversation's worth: a provider that fails five
#: times running costs this main their claims for the rest of that exchange and
#: is then tried again. Short, because the unit here is a *message* and a
#: stand-down measured in hundreds would quietly cover a whole day.
BREAK_FOR: Final[int] = 24

#: The only public method a holder may have. An **allowlist**, inherited whole
#: from story 6d's review round and for its reason: a denylist of names lets an
#: object through that can ``classify`` and also ``chat``, ``invoke``, ``run``
#: or be called directly. The port's ``Classifier`` is narrow because of the
#: methods it lacks — and here that is load-bearing rather than tidy, because
#: what this path must never acquire is a way to *author* a claim.
ALLOWED_METHODS: Final[frozenset[str]] = frozenset({"classify"})


# ── what a derivation comes to ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Derived:
    """One message's derivation. A value; it writes nothing and decides nothing
    about what Half may do with what it holds.

    **There is no claim text on this type, and that is deliberate.** A message
    goes out to a provider and what comes back is four labels; the *words* of
    the claim are the message's own, which the caller is already holding. So
    nothing here carries a main's text back across the boundary — there is no
    field on ``Derived`` for it and no parameter through which one could arrive,
    which makes *"a derivation returns a decision and never content"* a property
    of the type rather than a promise about its callers, on exactly the terms
    ``Tally`` holds the same property for the counts.

    ``keeps`` is false on every path but one, and the four ways of getting there
    are kept apart: refused by a gate, answered *cannot say* by one, never
    answered at all, or never consulted because this main has no deriver or
    their breaker is standing them down. Every one of them leaves no claim, so a
    case asserting *"no belief was written"* passes for all four — which is why
    each of them is reported separately and counted separately.
    """

    #: What the four gates said. Empty gates mean nothing was consulted.
    verdict: Admission = field(default_factory=Admission)
    #: Whether a deriver was reached at all. ``False`` for a main with no
    #: holder and for one the breaker is standing down — neither of which is a
    #: judgement about the message.
    consulted: bool = False

    @property
    def keeps(self) -> bool:
        """Whether there is a claim to record: **all four gates admitted**."""
        return self.verdict.admitted

    @property
    def refused_by(self) -> tuple[str, ...]:
        """**Every** gate that refused, in CAP-5's order — never only the
        first."""
        return self.verdict.refused_by


# ── the counts ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Tally:
    """What the deriver has been doing, as counts (AD-22).

    Counts and nothing else: no message, no claim, no belief id, no rationale.
    The keys are gate names and labels from the four closed sets and
    ``kind/reason`` pairs from the port's two closed enums, so there is no field
    here a main's own words could travel in — which makes *"no message survives
    a derivation"* a property of this type rather than a promise about its
    callers.

    Held in memory and never written to a main's log. A message that was judged
    records nothing about the main, and that includes the fact that it was
    judged.
    """

    #: Messages a deriver was asked about. The denominator of ``kept``.
    messages: int = 0
    #: Messages that produced a claim.
    derived: int = 0
    #: Gate consultations attempted, which is the denominator of the failure
    #: rate. Four per message, by construction.
    consulted: int = 0
    #: label -> how many times it came back. **By label rather than by verdict**:
    #: two of decision-relevance's labels refuse for different reasons, and an
    #: answered *cannot say* is a different fact from a provider that never
    #: answered. Collapsing either pair is the assertion-identical-either-way
    #: shape this project has shipped and taken back twice.
    answers: dict[str, int] = field(default_factory=dict)
    #: gate name -> how many messages that gate refused. Counted per gate
    #: because *"refused by decision-relevance and falsifiability"* is a
    #: different fact from *"refused by durability"*, which is the whole reason
    #: the gates do not short-circuit.
    refusals: dict[str, int] = field(default_factory=dict)
    #: ``"kind/reason"`` -> how many times the port reported it.
    failures: dict[str, int] = field(default_factory=dict)
    #: Gate consultations abandoned at ``BOUND_SECONDS``. Its own counter rather
    #: than a transport fault, because *"the gate is slow"* and *"the provider
    #: is unreachable"* want different things done about them.
    bound_exceeded: int = 0
    #: Gate consultations where the holder raised instead of returning one of
    #: the port's failures. A build mistake — an unknown tier, a budget
    #: admitting nothing.
    raised: int = 0
    #: Answers this build could not read: not a decision, not a failure, or a
    #: label from no known set.
    unreadable: int = 0
    #: Messages the breaker declined to derive from. **Not** consultations, so
    #: they sit outside every rate: the breaker's whole job is to stop making
    #: calls, and counting its silence as failure would double-count an outage.
    skipped: int = 0
    #: Messages there was nothing to judge in — blank, or not text.
    unjudgeable: int = 0

    @property
    def fell_back(self) -> int:
        """Gate consultations that produced no label at all. **Never the same
        number as the gates that could not say**, which is an answer."""
        return (
            sum(self.failures.values())
            + self.bound_exceeded + self.raised + self.unreadable
        )

    @property
    def answered(self) -> int:
        return sum(self.answers.values())

    @property
    def refused(self) -> int:
        """Messages at least one gate refused."""
        return sum(self.refusals.values())

    @property
    def failure_rate(self) -> float:
        """The number an operator watches. Zero consultations reads as zero
        rather than as an error, because a build with no deriver wired is a
        supported deployment and not a fault."""
        return consult.rate(self.fell_back, self.consulted)

    def count_answer(self, label: str) -> None:
        consult.count_one(self.answers, label)

    def count_refusal(self, gate_name: str) -> None:
        consult.count_one(self.refusals, gate_name)

    def count_failure(self, failure: Failure) -> None:
        consult.count_one(self.failures, consult.failure_key(failure))


# ── the bench ────────────────────────────────────────────────────────────────


class Derivers:
    """The derivers a deployment has equipped, one per main.

    Holds one narrow ``Classifier`` per main — narrow because the port's
    protocol has no method that returns text, and per main because a
    self-hoster's key is stored under their own id (AD-11).

    **A main with no holder derives nothing**, which is the shipped behaviour
    before this story with one difference that is the whole point: their
    messages are still recorded, still read by the language sample, still read
    by responsiveness, still excluded from the correction aim — and no longer
    ranked, quoted, minted against or resolved for a rung. An unequipped
    deployment loses claims from the turn path, not messages.

    **Sealed after construction.** The holders are a read-only mapping and no
    attribute can be rebound, so the check that every holder is the narrow one
    cannot be walked around by assigning a wider one afterwards. A holder that
    could generate is a path from a message to a sentence Half wrote about a
    main and kept for ever.
    """

    __slots__ = ("_holders", "_bound", "_tally", "_breaker", "_sealed")

    def __init__(
        self,
        holders: Mapping[str, Classifier] | None = None,
        *,
        bound_seconds: float = BOUND_SECONDS,
        tally: Tally | None = None,
    ) -> None:
        given = dict(holders or {})
        for main_id, holder in given.items():
            _check_holder(main_id, holder)
        if not consult.a_bound(bound_seconds):
            raise DeriveError(
                f"a bound of {bound_seconds!r} is not a bound. A gate that may "
                "run for ever sits between one main's message and their next "
                "one, and nothing would ever say so"
            )
        self._holders: Mapping[str, Classifier] = MappingProxyType(given)
        self._bound = float(bound_seconds)
        self._tally = tally if tally is not None else Tally()
        #: main -> consecutive failures, and main -> derivations still to skip,
        #: in the shared shape. Counted in derivations, per main.
        self._breaker = consult.Breaker(break_for=BREAK_FOR)
        self._sealed = True

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise DeriveError(
                f"a bench of derivers is sealed after construction; rebinding "
                f"{name!r} would put a holder past the check that it cannot "
                "produce text"
            )
        super().__setattr__(name, value)

    @property
    def tally(self) -> Tally:
        """The counts. Readable so an operator can see the failure rate."""
        return self._tally

    def holds(self, main_id: str) -> bool:
        """Whether this main has a deriver available at all."""
        return main_id in self._holders

    # -- one derivation -------------------------------------------------------

    async def derive(self, text: object, *, main_id: str) -> Derived:
        """One message, four gates, one answer. **Never raises.**

        The only thing that leaves this machine is the message, once per gate.

        Every path out is a ``Derived``, and everything that is not four gates
        admitting produces no claim: a refusal, an unsure, a provider that did
        not answer, a breaker standing this main down, a deployment that
        equipped nobody. None of them is a reason to write a belief, and none of
        them is a reason for the turn to have gone differently.

        ``CancelledError`` is deliberately not caught — it is a
        ``BaseException`` and a shutdown is not a refused message.
        """
        holder = self._holders.get(main_id)
        if holder is None:
            return Derived()
        if not isinstance(text, str) or not text.strip():
            # A blank message. ``half.actor.runtime`` records one and answers
            # with silence, so there is nothing here to judge and nothing to
            # judge it against.
            self._tally.unjudgeable += 1
            return Derived()
        if self._breaking(main_id):
            return Derived()

        self._tally.messages += 1
        # **Concurrently, and all four whatever any of them says.** The wall
        # clock is one bound rather than four, and there is no ordering here
        # under which one gate's refusal could stop another being asked — which
        # is CAP-5's *individually testable* made structural rather than
        # promised.
        answers = await asyncio.gather(
            *(self._ask(gate, text, main_id=main_id) for gate in GATES)
        )
        verdicts = {
            gate.name: answer
            for gate, answer in zip(GATES, answers, strict=True)
            if answer is not _UNANSWERED
        }
        verdict = admission(verdicts)  # type: ignore[arg-type]
        for name in verdict.refused_by:
            self._tally.count_refusal(name)
        self._note(main_id, failed=not verdicts)
        # On every path out, and that ordering is the point: a summary reached
        # only from the success path would go quiet exactly when the deriver
        # started failing, which looks identical to a product with nothing worth
        # keeping.
        self._report()
        if verdict.admitted:
            self._tally.derived += 1
        return Derived(verdict=verdict, consulted=True)

    async def _ask(
        self, gate: Gate, text: str, *, main_id: str
    ) -> bool | None | object:
        """One gate, bounded. Never raises; ``_UNANSWERED`` for no answer.

        The sentinel is what keeps *"the gate said cannot say"* apart from *"the
        gate never answered"* all the way up to ``Admission``: both produce no
        claim, so a single ``None`` for the two of them would make every case
        about an unsure gate pass against a provider that was simply down.
        """
        work = Classify(
            prompt=prompt_for(
                text, main_id=main_id, instructions=gate.instructions
            ),
            labels=gate.labels,
        )
        self._tally.consulted += 1
        try:
            async with asyncio.timeout(self._bound):
                reply = await holder_of(self._holders, main_id).classify(work)
            # Inside the handler on purpose: reading the answer can raise on a
            # holder that breaks the port's contract — a label that is not even
            # a string — and a raise out here would leave ``consulted``
            # incremented with nothing counted against it, so the one number an
            # operator watches would understate failure on the failing path.
            return self._read(reply, gate, main_id=main_id)
        except TimeoutError:
            # Past the bound. An unavailability, never a verdict.
            self._tally.bound_exceeded += 1
            logger.warning(
                "the %s gate passed its bound for main=%s; nothing is derived "
                "from that message and the turn is unaffected",
                gate.name, main_id,
            )
        except Exception as exc:
            # The port answers a provider fault with a value; a raise here is a
            # build mistake — an unknown tier, a budget admitting nothing.
            #
            # **The class, and never the exception's own text** (AD-22). A
            # provider quotes the request it rejected, and the request carries
            # this main's own message.
            self._tally.raised += 1
            logger.warning(
                "the %s gate could not run for main=%s (%s); nothing is derived "
                "from that message and the turn is unaffected",
                gate.name, main_id, type(exc).__name__,
            )
        return _UNANSWERED

    def _read(
        self, reply: object, gate: Gate, *, main_id: str
    ) -> bool | None | object:
        """One gate's outcome. Pure but for the counters.

        **One rule, and it is the whole mapping:** an answer that is not a label
        from *this gate's* closed set is no answer at all. A transport fault, a
        refusal, a budget refusal, a truncated reply, prose, another gate's
        label and anything a future port returns land there together, because
        none of them is a reading of the message.

        An answered *cannot say* is **not** a failure, which is why it comes
        back as ``None`` rather than as the sentinel: the provider is up and
        answering, and arming the breaker on it would stand a main down for
        having an ambiguous life.
        """
        if not isinstance(reply, Decision):
            if isinstance(reply, Failure):
                self._tally.count_failure(reply)
                # Two closed enums, a gate name and a main_id. Nothing else
                # exists to log.
                logger.warning(
                    "the %s gate did not answer for main=%s: %s/%s",
                    gate.name, main_id, reply.kind, reply.because,
                )
            else:
                self._tally.unreadable += 1
                logger.warning(
                    "the %s gate returned something this build cannot read for "
                    "main=%s", gate.name, main_id,
                )
            return _UNANSWERED
        label = reply.label if isinstance(reply.label, str) else None
        if label not in gate.labels:
            # Unreachable through the port, which refuses a label outside the
            # request's own set. Kept because "unreachable" is a claim about
            # today's implementation, and being wrong about it here would turn
            # an unknown word into a durable belief.
            self._tally.unreadable += 1
            logger.warning(
                "the %s gate answered outside its own label set for main=%s",
                gate.name, main_id,
            )
            return _UNANSWERED
        self._tally.count_answer(label)
        return gate.verdict(label)

    # -- the breaker ----------------------------------------------------------

    def _breaking(self, main_id: str) -> bool:
        """Whether this main's deriver is standing down. Counted, per main.

        During an outage every message would otherwise pay four full bounds and
        then issue four more doomed requests, between one message of a
        conversation and the next.

        The counting is the shared shape's; the *skip* is counted here, because
        a message the breaker declined is not a consultation and must stay
        outside every rate — the breaker's whole job is to stop making calls,
        and counting its silence as failure would double-count one outage.
        """
        if not self._breaker.spend(main_id):
            return False
        self._tally.skipped += 1
        return True

    def _note(self, main_id: str, *, failed: bool) -> None:
        """Record whether that derivation worked, and trip or clear the breaker.

        **Failed means no gate answered at all**, and the alternative — arming
        on any one gate failing — is the shape story 13a found in the voice: one
        flaky gate out of four would stand the whole deriver down while three
        gates were answering perfectly well. A provider that is down fails all
        four; a provider that is up answers at least one.

        The breaker decides; the line is written here, where the scan that
        proves no log call on this path can carry content reads it.
        """
        if not self._breaker.note(main_id, failed=failed):
            return
        logger.error(
            "every admission gate failed %d times running for main=%s and the "
            "deriver is standing down for %d message(s); nothing is derived "
            "for them until then", BREAK_AFTER, main_id, BREAK_FOR,
        )

    # -- what an operator sees ------------------------------------------------

    def _report(self) -> None:
        """Write the running counts out, every so often. Counts only (AD-22).

        **The alarm is asked first**, and the branch that decides it is
        ``half.model.consult.due``'s rather than a fourth copy of the ``elif``
        that made the two mutually exclusive in three modules at once.
        """
        due = consult.due(
            self._tally.consulted, self._tally.failure_rate,
            alarm_rate=ALARM_RATE,
        )
        if due is consult.Due.ALARM:
            self.flush(alarming=True)
        elif due is consult.Due.PERIODIC:
            self.flush()

    @property
    def quiet(self) -> bool:
        """Whether nothing has happened worth writing out.

        A deployment with no key is not an event, and a line of zeros at every
        shutdown is the noise that trains an operator to ignore the one line
        that matters.
        """
        return not (
            self._tally.consulted or self._tally.skipped
            or self._tally.unjudgeable
        )

    def flush(self, *, alarming: bool = False) -> None:
        """Write the counts out now — periodically, above the alarm rate, and
        once at shutdown, so a wholly failing deriver cannot be silent for as
        long as it takes to reach a round number.

        The two calls are spelled out rather than routed through a bound
        ``write`` or a shared format string, because the guard that proves no
        log line here can carry content reads the *arguments of a logging call*:
        a message in a variable and a receiver in a local are both invisible to
        it, and an invisible log call is how content gets logged.
        """
        if self.quiet:
            return
        if alarming:
            logger.error(
                "claim derivation: %d message(s), %d derived, %d refused, "
                "%d gate(s) consulted, %d answered, %d failed (%d past the "
                "bound, %d unreadable, %d raised), %d skipped, %d unjudgeable",
                self._tally.messages, self._tally.derived, self._tally.refused,
                self._tally.consulted, self._tally.answered,
                self._tally.fell_back, self._tally.bound_exceeded,
                self._tally.unreadable, self._tally.raised,
                self._tally.skipped, self._tally.unjudgeable,
            )
        else:
            logger.info(
                "claim derivation: %d message(s), %d derived, %d refused, "
                "%d gate(s) consulted, %d answered, %d failed (%d past the "
                "bound, %d unreadable, %d raised), %d skipped, %d unjudgeable",
                self._tally.messages, self._tally.derived, self._tally.refused,
                self._tally.consulted, self._tally.answered,
                self._tally.fell_back, self._tally.bound_exceeded,
                self._tally.unreadable, self._tally.raised,
                self._tally.skipped, self._tally.unjudgeable,
            )


# ── what a gate consultation is made of ──────────────────────────────────────

#: *This gate produced no answer at all.* A sentinel and not ``None``, because
#: ``None`` is already an **answer** — the model saying it cannot tell — and the
#: two must not fold together: both leave no claim, so one value for the pair
#: would make every case about an unsure gate pass against a provider that was
#: down.
_UNANSWERED: Final[object] = object()


def holder_of(
    holders: Mapping[str, Classifier], main_id: str
) -> Classifier:
    """This main's holder. Raises if there is none, which ``derive`` prevents.

    Read through a function rather than captured, so that a gate coroutine holds
    a ``main_id`` and never a provider — the same reason ``Judge`` holds a bench
    and an id and nothing else.
    """
    holder = holders.get(main_id)
    if holder is None:
        raise DeriveError(
            f"main {main_id!r} has no deriver; the caller checks before asking"
        )
    return holder


def prompt_for(
    text: str, *, main_id: str, instructions: tuple[str, ...]
) -> Prompt:
    """The whole of what one gate consultation is made of.

    One user turn carrying the message, and the gate's instructions in front of
    it. Nothing from the ledger, the strands, the loops, the phone book or the
    main's history is here, and there is no parameter through which any of it
    could arrive — the gate's instructions are supplied by the caller because
    they are the only thing that differs between the four.

    **The message is sent whole and is never truncated, normalised or folded.**
    Not lower-cased, not stripped of marks, not transliterated, not measured: it
    is somebody's own sentence in their own script, and every one of those
    operations is a rule written about one language being applied to all of
    them. A message long enough to cost more than ``PER_CALL_MICRO_USD`` is
    refused by the budget before the transport is touched and counted as a
    failure — which an operator can see, where a quietly clipped message would
    be a gate judging half a sentence and reporting a verdict.

    **No cache breakpoint is stated.** The four instruction blocks are stable
    and look like a prefix worth caching, but they are far under the cheap
    tier's four-thousand-token minimum, and the port refuses a breakpoint the
    provider would silently ignore rather than placing one that does nothing
    (AD-19). Stating none is the honest answer: this call caches nothing and its
    cost says so.
    """
    return Prompt(
        main_id=main_id,
        system=tuple(instructions),
        turns=(Turn(role=Role.USER, text=text),),
    )


def _check_holder(main_id: str, holder: object) -> None:
    """Refuse anything that could do more than classify, at the boundary.

    A ``Classifier`` is narrow because of the methods it lacks, and here that is
    the guarantee the story rests on rather than hygiene: an object that can
    generate is a path from a main's message to a sentence Half composed about
    them and wrote into their ledger for ever, arriving through the one seam
    that was supposed to answer yes or no.

    An **allowlist**, because the denylist this pattern replaced named six
    methods, so an object with ``classify`` and ``chat`` walked straight
    through, and so did one that was simply callable.
    """
    if not isinstance(holder, Classifier):
        raise DeriveError(
            f"the holder for main {main_id!r} cannot classify; a derivation "
            "takes the port's narrow classifier and nothing else (AD-19)"
        )
    if callable(holder):
        raise DeriveError(
            f"the holder for main {main_id!r} is itself callable, which is a "
            "method by another name. A derivation holds an object that can "
            "classify and do nothing else"
        )
    wider = consult.wider_than(holder, ALLOWED_METHODS)
    if wider:
        raise DeriveError(
            f"the holder for main {main_id!r} can also {', '.join(wider)}. A "
            "derivation holds an object with no way to produce text and no way "
            "to reach the provider that owns it — that is what stops a claim "
            "being written in Half's words rather than the main's. Hand over "
            "the narrow classifier"
        )


def _check_constants() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee ``python -O`` removes is not a guarantee.
    """
    for name, value in (
        ("BOUND_SECONDS", BOUND_SECONDS), ("REPORT_EVERY", REPORT_EVERY),
        ("ALARM_AFTER", ALARM_AFTER), ("BREAK_AFTER", BREAK_AFTER),
        ("BREAK_FOR", BREAK_FOR),
        ("PER_CALL_MICRO_USD", PER_CALL_MICRO_USD),
    ):
        if value <= 0:
            raise DeriveError(f"{name} must be positive; {value!r} is not")
    if PER_CALL_MICRO_USD > PER_PASS_MICRO_USD:
        raise DeriveError("a per-call ceiling above the per-pass one never binds")
    if not consult.a_bound(BOUND_SECONDS):
        raise DeriveError(
            f"a bound of {BOUND_SECONDS!r} is not a bound; a timeout that never "
            "fires is a guard that reports success"
        )
    if not 0 < ALARM_RATE <= 1:
        raise DeriveError(
            f"an alarm rate of {ALARM_RATE!r} either never fires or fires on "
            "the first quiet deployment"
        )
    if not isinstance(CLASSIFY_TIER, str) or not CLASSIFY_TIER.strip():
        raise DeriveError(
            f"{CLASSIFY_TIER!r} is not a tier name. The composition root parses "
            "this and a name this build does not know is refused at boot, so an "
            "empty one is a deployment that derives nothing for anybody"
        )


_check_constants()


__all__ = [
    "ALARM_AFTER",
    "ALARM_RATE",
    "ALLOWED_METHODS",
    "BOUND_SECONDS",
    "BREAK_AFTER",
    "BREAK_FOR",
    "CLASSIFY_TIER",
    "PER_CALL_MICRO_USD",
    "PER_PASS_MICRO_USD",
    "REPORT_EVERY",
    "Derived",
    "Derivers",
    "Tally",
    "prompt_for",
]
