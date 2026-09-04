"""Wiring: channel -> crisis gate -> actor -> store (AD-17).

Two policies here were human decisions, not defaults:

**Per-message isolation.** No single message's failure ends the inbound loop.
An uncaught error used to propagate out of ``run()`` and stop polling for
*every* main — Half stayed up and silently stopped receiving.

**At-least-once delivery.** The transport commits its position only after a
turn completes, so a crash redelivers rather than loses. That makes redelivery
routine, so the turn is idempotent: a message already recorded is not recorded
twice.

**The reply is prose, composed through the model port** (story 13b). Until this
story ``respond`` was a deterministic stub and a main received
``noted. has not walked that plot since March`` — an English word bolted to a
raw claim — while a bought question arrived as ``question[b_1] topic: farmland``
and a correction as ``retract[b_land]: has not walked that plot since March``.
All three were the internal serialization on the wire.

What replaces them is story 13a's composer, unforked: one gate, one judge, one
tripwire, one tally (``half.voice``). Where generation fails the fallback is
**the claim alone, unscaffolded** — never a template, in any language, and never
silence unless there is no claim, because a main who has just written is waiting
and silence would read as broken. ``half.voice.turn`` holds the ladder and the
argument for it.

**Retrieval runs on the live turn, and what it returns is governed by license.**
Story 4 ranked the belief set under an interim ban: nothing retrieved could be
said, because the thing that decides what Half may *say* did not exist. It does
now. ``respond`` builds a two-channel context (AD-18) and may quote its content
channel — `assert`-licensed claims and nothing else. `behave` and `ask` claim
text cannot reach a reply because it never reaches the context, which is
enforcement by construction rather than by filtering what was generated.

**This module never touches belief text directly.** It reads the ranked set
only through ``half.context``, so there is no path from a `Candidate` to an
outbound message that skips the license split — asserted statically in
``tests/test_strands.py``, byte-wise in ``tests/test_context.py``.

**The bought question is delivered here, and here only** (CAP-4, story 11).
*"The favor buys the question"* means a question is attached to a conversation
that already touches its topic — 5b's topic gate reads the live strands, and the
live strands exist on a turn and nowhere else. The first build of story 11 gated
on them and delivered on the unprompted morning, where a dormant actor has none;
that is a ping however the gate is worded, so delivery moved here and the morning
surface no longer asks at all.

Three orderings on this path are the rule rather than the arrangement:

* **The favour precedes the turn.** Nothing here writes a record the trust
  balance counts as *delivered* — that is the morning's ``touch``, and this path
  writes only the main's own message — so the balance a question is paid from can
  only hold favours older than this turn. CAP-4 says *preceded*.
* **The question is offered after the turn is recorded**, so nothing about
  buying one can cost the main their answer. Every step of it is fail-open.
* **The favour is spent only once the composed prose carrying the question is
  what goes out**, and immediately before it is sent. A belief the ladder raised
  above `ask`, or one whose topic echoes its claim, builds no question — and
  used to spend a favour and write an ``asked`` record for a question nobody was
  asked. Story 13b adds the second half of the same rule: a generation that
  failed sends the fallback, the fallback asks nothing, and a favour spent on it
  would have paid for a question the main never saw.

**A message is evidence; a claim is a belief** (CAP-5, story 15a). Until that
story this module wrote every inbound message into the main's ledger as a stated
belief, so ``ok``, ``thanks`` and ``hello?`` were beliefs — ranked by retrieval,
quotable once promoted, eligible for a tension and aimed at by a correction. The
record still goes exactly where it went and still carries the three subsystems
that read it (the language sample, responsiveness, and the correction aim's
exclusion); what it gains is the mark that says it is **not a claim**, and what
it loses is every belief path. ``_derive`` then asks CAP-5's four admission
gates whether there is a claim in it, and writes one — citing the message — when
all four say yes.

**And it happens after the reply.** A main waiting on a model call to find out
whether their message was worth keeping is the latency failure story 13b spent a
review round on, so ``_handle`` sends first and derives afterwards; every way
derivation can fail costs a claim and never a word.

And one that moved. **The words are composed outside the main's mutex.** The
reply used to be built inside the acquire, which was free while it was a
deterministic stub and is not now: a model call under the lock would hold
eviction and every other operation on that main for the whole bound (AD-33),
which is the same reason correction recognition already runs before the lock.
What the acquire produces is values — the ranked set, the ceiling, the live
strands, the removal — and the append that closes the turn still happens before
the mutex is released.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Final

from half.actor.registry import Actor, ActorRegistry
from half.channel.port import Channel, Inbound
from half.context.build import build as build_context
from half.context.build import fragments
from half.context.build import split as split_context
from half.context.channels import Content, Context
from half.correction import apply as correction
from half.correction import candidate as candidate_module
from half.correction import signals as correction_signals
from half.correction.apply import Removal, Source
from half.correction.candidate import Widening
from half.crisis.aftercare import Schedule
from half.crisis.classifier import SecondOpinion
from half.crisis.gate import CrisisGate
from half.crisis.handoff import Desk
from half.crisis.safetyplan import Holder
from half.derive.claim import Derivers
from half.errors import (
    HalfError,
    NotReachable,
    QueryTooLargeError,
    RetrievalDisabled,
    SendFailed,
    TokenGrowthLimitError,
)
from half.governance import ladder
from half.governance.ladder import Ceiling
from half.questions.engine import QuestionEngine
from half.retrieval.port import Ranked, Reranker
from half.retrieval.strands import Strands
from half.retrieval.rank import Retriever
from half.retrieval.strands import known_strands
from half.store.ops import Op
from half.store.records import DERIVATION, DERIVED, LEDGER, STATED, UNDERIVED
from half.voice import turn as voice_turn
from half.voice.compose import Sample
from half.voice.gate import Voice
from half.voice.turn import Turned

logger = logging.getLogger(__name__)

#: Backoff between retries of a retryable send, in seconds.
RETRY_DELAYS = (1.0, 4.0, 15.0)

#: The whole of one turn's model budget, in seconds — **one deadline, shared**.
#:
#: Three bounded calls can happen on a single inbound message: the crisis
#: classifier (``half.crisis.classifier.BOUND_SECONDS``), the correction
#: widening (``half.correction.candidate.BOUND_SECONDS``) and the composition
#: (``half.voice.turn.TURN_BOUND_SECONDS``). Each is two seconds and each was
#: sized against the *same* five, so a turn that took all three made a waiting
#: main sit through six — every module honouring a bound nobody was keeping.
#:
#: What the modules are each sized against is AD-23's five-second window, and
#: the honest reading of AD-23 is that it governs the webhook acknowledgement,
#: which this design already answers by enqueuing (``_Turns``). What five
#: seconds bounds *here* is the person: it is the number the three bounded
#: callers were each written against, so it is the one they share rather than a
#: fourth opinion invented for this story.
#:
#: The deadline is per turn and starts before the crisis gate, which is the
#: first thing that can spend against it. What each later call receives is the
#: **remainder**, and a remainder of nothing means that call does not happen —
#: never a fourth wait, and never a bound of zero handed to a timeout.
TURN_DEADLINE_SECONDS: Final[float] = 5.0

#: When this turn's budget runs out, on the loop's own monotonic clock.
#:
#: A ``ContextVar`` and not a parameter, because the value has to cross the
#: crisis gate — which owns its own call signature and is Ask-First for this
#: story — to reach the pipeline on the other side. Every turn runs inside one
#: task (``_Turns._work`` awaits one before taking the next), so the value one
#: turn sets is the value that turn reads and no other's.
#:
#: ``None`` is *no deadline*, which is what every direct caller of ``respond``
#: gets: a bound is a promise to somebody who is waiting, and a test or a later
#: surface that calls in without going through ``_handle`` has not made one.
_DEADLINE: Final[ContextVar[float | None]] = ContextVar(
    "half_turn_deadline", default=None
)


#: The belief this turn tombstoned, or ``""``. **An id, never a claim.**
#:
#: Read by ``_handle`` after the send, so that an erasure whose words never
#: reached the main is loud rather than silent. See ``_send_with_retry``.
_ERASED: Final[ContextVar[str]] = ContextVar("half_turn_erased", default="")


#: The message record this turn wrote, or ``""``. **An id, never the text.**
#:
#: Read by ``_handle`` after the send, so that derivation happens **after the
#: reply** and only for a turn that actually recorded a message (CAP-5, story
#: 15a). A ``ContextVar`` and not a return value, for the reason ``_ERASED`` is
#: one: what ``_pipeline`` returns has to cross the crisis gate, which owns its
#: own signature and is Ask-First. Every turn runs inside one task
#: (``_Turns._work`` awaits one before taking the next), so the value one turn
#: sets is the value that turn reads and no other's.
#:
#: **Empty is the whole of the crisis rule and the redelivery rule**, arrived at
#: without a branch for either. The crisis gate answers a disclosure itself and
#: never reaches ``_pipeline``, so nothing sets this and nothing is derived
#: (CAP-12). A redelivery returns at the idempotency check before the record is
#: written, so nothing is set and one message is never derived twice.
_DERIVABLE: Final[ContextVar[str]] = ContextVar("half_turn_message", default="")

#: What a derived claim's id is built from. Two letters and the message's own
#: external id, beside the message's ``b_`` — so the claim and the evidence it
#: cites are one letter apart in the log and neither can land in the other's
#: namespace.
DERIVED_PREFIX: Final[str] = "d_"


def _open_deadline() -> None:
    """Start this turn's shared budget, and clear last turn's erasure and its
    message. Never raises."""
    _DEADLINE.set(asyncio.get_running_loop().time() + TURN_DEADLINE_SECONDS)
    _ERASED.set("")
    _DERIVABLE.set("")


def _left(most: float) -> float:
    """How long the next bounded call may run: ``most``, or what is left of the
    turn's budget if that is less. Never raises, and never a negative.

    With no deadline open the caller's own bound stands unchanged, so nothing
    that reaches a model outside the turn path is shortened by this.
    """
    deadline = _DEADLINE.get()
    if deadline is None:
        return most
    try:
        left = deadline - asyncio.get_running_loop().time()
    except RuntimeError:  # no running loop: nothing is waiting on a clock
        return most
    return max(0.0, min(most, left))

#: Turns one main may have waiting before the inbound loop waits with them.
#: Bounded so a flood costs that main their own backlog rather than the
#: process's memory, and generous enough that an ordinary conversation never
#: reaches it — a main would have to send thirty-two messages faster than Half
#: answers one.
QUEUE_DEPTH = 32


class _Turns:
    """One main's turns, in order, one at a time.

    An inbox and a worker — the actor shape (AD-8) applied to the *inbound*
    path, where until story 6d there was one queue for everybody. It exists so
    that a main whose turn is waiting on a provider is the only main waiting.

    Ordering and serialization per main are exactly what a single loop gave:
    the queue is FIFO and the worker awaits one turn before taking the next, so
    two messages from one person can never overtake each other or reach that
    main's store at once.
    """

    __slots__ = ("_queue", "_task")

    def __init__(self, handle: "Callable[[Inbound], Awaitable[None]]") -> None:
        self._queue: asyncio.Queue[Inbound | None] = asyncio.Queue(QUEUE_DEPTH)
        self._task = asyncio.create_task(self._work(handle))

    @property
    def finished(self) -> bool:
        """Whether this worker has stopped — cancelled, or drained and closed.

        Read before a turn is handed over, so a worker that was cancelled
        mid-call costs that main one turn and not their whole conversation.
        """
        return self._task.done()

    async def accept(self, inbound: Inbound) -> None:
        await self._queue.put(inbound)

    async def _work(self, handle) -> None:
        while True:
            inbound = await self._queue.get()
            if inbound is None:
                return  # everything before the sentinel has been handled
            try:
                await handle(inbound)
            except asyncio.CancelledError:
                # **Whose cancellation is this?** ``cancelling()`` counts the
                # cancel requests made *against this task*, so a shutdown — the
                # drain below, or the task group above — is non-zero and is
                # re-raised, while a ``CancelledError`` that came out of the
                # turn itself is zero and costs one turn.
                #
                # Swallowing both would break shutdown; swallowing neither cost
                # this main every message still queued behind the one that was
                # cancelled, which is the whole backlog of the person Half was
                # in the middle of a conversation with.
                task = asyncio.current_task()
                if task is None or task.cancelling():
                    raise
                logger.error(
                    "a turn was cancelled for main=%s; continuing with the "
                    "rest of their queue", inbound.main_id,
                )

    def close(self) -> None:
        """Ask the worker to stop once its queue is empty."""
        if not self._task.done():
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                # A full queue at shutdown: the backlog is drained by the
                # cancel below rather than by a sentinel nobody can enqueue.
                self._task.cancel()

    async def wait(self) -> None:
        try:
            await self._task
        except asyncio.CancelledError:
            if self._task.cancelled():
                return  # this worker was cancelled, not us
            raise
        except Exception:  # noqa: BLE001 - a worker fault is not a shutdown fault
            logger.error("a turn worker ended unexpectedly")


async def _drain(workers: "dict[str, _Turns]") -> None:
    """Let every worker finish what it has, then let go.

    Called on the way out of ``run`` — including the ordinary way out, when the
    channel's own generator ends, which is how every test and every self-host
    restart gets here. Draining rather than cancelling is what makes a queued
    turn a turn that still happens.
    """
    for worker in workers.values():
        worker.close()
    for worker in workers.values():
        await worker.wait()


@dataclass(slots=True)
class Runtime:
    channel: Channel
    registry: ActorRegistry
    #: Injectable so story 6 can test the crisis branch, and so the branch is
    #: reachable from a test at all.
    gate: CrisisGate | None = None
    #: Optional by AD-5 and unimplemented in v1 by AD-19. When absent, results
    #: come back in bm25-fused order carrying an explicit no-op annotation.
    reranker: Reranker | None = None
    #: The crisis classifier's holder (story 6d). Optional, and absent is a
    #: supported deployment rather than a degraded one: the phrase table
    #: decides alone, offline, exactly as it did in story 6a. Passed to the
    #: gate rather than constructed here, because the key it rests on lives
    #: beside the store tree and is read at the composition root (AD-11).
    second: SecondOpinion | None = None
    #: Who buys the question (CAP-4, story 11). ``None`` is a runtime that never
    #: asks anything — the fail-closed default, and every caller that predates
    #: this story. A question is *attached* to a reply this turn was going to
    #: send anyway; it is never a message of its own, which is what keeps
    #: *"never ping to ask"* true of the path as well as of the gate.
    questions: QuestionEngine | None = None
    #: Who widens correction recognition past the offline table (CAP-11, story
    #: 12). ``None`` is a runtime whose recognition is the table alone —
    #: offline, high-confidence, and exactly what a deployment with no key gets.
    #: It is never a runtime that *cannot* correct: an explicit correction is
    #: recognised and acted on with no model anywhere on the path.
    corrections: Widening | None = None
    #: Who writes the sentence (story 13b). **Defaulted to a voice with no
    #: holders**, which composes for nobody — so a runtime built without one
    #: answers with the claim alone rather than with the internal serialization
    #: this story exists to take off the wire. That is the fail-safe direction
    #: and it is not silence: on a turn a main is waiting, so the fallback is
    #: what Half knows rather than nothing.
    #:
    #: **The same ``Voice`` the morning surface holds**, wired by value at the
    #: composition root. One composer, one gate, one leak check and one tally:
    #: two of each is two renderings of one thing, which is how a guard that
    #: scans one string ends up admitting another.
    voice: Voice = field(default_factory=Voice)
    #: Who decides whether a message was worth keeping (CAP-5, story 15a).
    #: **Defaulted to a bench with no holders**, which derives nothing for
    #: anybody — and that is a supported deployment rather than a degraded one:
    #: the message is still recorded, still read by the language sample, still
    #: read by responsiveness, still excluded from the correction aim. What an
    #: unequipped deployment loses is *claims* from the turn path, never
    #: messages, and it is exactly the state every build before this story
    #: shipped, minus the defect that every message was also a belief.
    derivers: Derivers = field(default_factory=Derivers)
    _gate: CrisisGate = field(init=False, repr=False)
    #: The widening, or an empty one. **A candidate store is not a model
    #: thing**: an erasure has to be confirmed whether or not a deployment has a
    #: key, so the object that remembers what Half offered exists either way and
    #: a runtime built without one still asks before it destroys a body. With no
    #: holders it consults nothing, counts nothing, and proposes only what the
    #: offline table asks it to.
    _corrections: Widening = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # An injected gate owns its own wiring; the default one is handed the
        # registry itself, so a crisis suspension is durable and per main: the
        # switch it turns off is the one that main's own retriever reads — and
        # no one else's — the ceiling it drops is the one in that main's log,
        # and the mode it opens survives eviction and restart (AD-28, CAP-12).
        # A gate built without it holds the mode in memory and writes nothing,
        # which is why the runtime never builds one that way.
        # The handoff desk reads this main's phone book from the registry and
        # turns a chosen contact into a link through the channel's own
        # ``draft_link`` — the only route to a third party there is (AD-25).
        # It is wired here rather than left to a test, because a surface
        # reachable only from a test is a surface nobody has run.
        # Aftercare and the held safety plan read the same registry, for the
        # same reason: both are durable per-main state that has to survive
        # eviction and restart, and both run on the main's own turn rather than
        # on a schedule that does not exist. Wired here rather than left to a
        # test, because a surface reachable only from a test is a surface
        # nobody has run.
        self._corrections = self.corrections or Widening()
        self._gate = self.gate or CrisisGate(
            pipeline=self._pipeline,
            store=self.registry,
            desk=Desk(held=self.registry, drafter=self.channel),
            schedule=Schedule(store=self.registry),
            holder=Holder(held=self.registry),
            # The second opinion (story 6d). It widens the cheap action and
            # nothing else — it cannot enter the mode, cannot write a word a
            # main reads, and cannot be reached at all until a deployment has
            # supplied a key and a tier. Passed through rather than defaulted,
            # so a runtime built without one is story 6a's offline gate.
            second=self.second,
        )

    async def run(self) -> None:
        """Consume inbound messages until cancelled.

        Nothing a single message does can end this loop, and **nothing one main
        does can hold another main up.**

        *Why this stopped being one sequential loop* (story 6d, review round 1).
        The crisis gate now waits on a provider, and a single `await` per
        message made that wait everyone's: measured, a hanging classifier
        answered a second main's **safe word** ten seconds late, behind two
        turns that were not theirs. Story 6a's guarantee is that the safe word
        is decided offline with the provider down — which was true only for the
        message at the head of the queue. A degraded provider throttled the
        whole deployment to one message per bound, for every main, with nothing
        saying so.

        So a turn is dispatched to its own main's worker and the loop goes back
        to polling. Per main it is exactly what it was: one worker, a FIFO
        queue, one turn at a time, in arrival order, through the same actor
        mutex (AD-1). Across mains they no longer touch.

        *The cost, stated rather than discovered.* The transport commits its
        offset when this loop asks for the next update, so at-least-once now
        means *accepted for its main* rather than *finished*. A hard crash can
        lose what is queued — at most ``QUEUE_DEPTH`` turns per main, because
        the queue is bounded and a full one makes this loop wait, which is
        backpressure on that main and not on the others. The alternative was
        keeping a guarantee about crashes at the price of a guarantee about the
        safe word, and the safe word is the one somebody's life is on.

        *A worker that dies does not take the loop with it.* Each turn is
        isolated; a worker cancelled mid-call ends that worker and nothing else,
        and the next message from that main starts a fresh one.
        """
        workers: dict[str, _Turns] = {}
        try:
            async for inbound in self.channel.receive():
                worker = workers.get(inbound.main_id)
                if worker is None or worker.finished:
                    worker = _Turns(self._isolated)
                    workers[inbound.main_id] = worker
                # Bounded: a main who sends faster than Half can answer waits
                # on their own backlog rather than growing memory.
                await worker.accept(inbound)
        finally:
            await _drain(workers)

    async def _isolated(self, inbound: Inbound) -> None:
        """One turn, whatever it does. Never raises to the worker loop."""
        try:
            await self._handle(inbound)
        except asyncio.CancelledError:
            raise  # shutdown is not a message failure
        except Exception as exc:
            # Content is never logged — it is the most intimate data the
            # product holds — and the class of the fault rather than its own
            # text, which can quote a request a provider rejected (AD-22).
            logger.error(
                "turn failed for main=%s message=%s (%s); continuing",
                inbound.main_id,
                inbound.external_id,
                type(exc).__name__,
            )

    async def _handle(self, inbound: Inbound) -> None:
        """One turn, gate first (AD-10), then whatever it produced.

        **Every inbound message crosses this method, and that is why the
        correction candidate's lifetime is bound here** (CAP-11, story 12). The
        turn path is not the only thing that answers a main: the crisis gate
        answers a disclosure itself, answers its own standing question itself,
        and surfaces a third-party resource itself — and none of those reach the
        pipeline. A candidate left standing across one of them was answered by
        the *next* thing the main said, which after a crisis reply that ends
        *"tell me, I am here for that too"* is very often a bare "yes".

        So: a candidate is answerable on the turn after it was put, and on no
        other. The turn path clears it when the main answers; this clears it
        when the turn path never ran. Both are the same rule, and this one
        cannot be skipped because there is no route into Half that avoids it.

        **This is also where the turn's one model deadline opens** (review loop
        1). Three bounded calls can happen below — the classifier inside the
        gate, the widening, and the composition — and each of the three was
        sized against the same five seconds on its own, which added up to six in
        front of somebody who had just written. See ``TURN_DEADLINE_SECONDS``.
        """
        _open_deadline()
        try:
            reply = await self._gate.handle(inbound)
        finally:
            self._expire_candidate(inbound)
        # Silence is an outcome, not a failure (AD-27) — and it is still a turn
        # on which the main said something, so the derivation below happens
        # either way. What must not happen is deriving *first*: see ``_derive``.
        if reply is not None:
            await self._deliver(inbound, reply)
        await self._derive(inbound)

    async def _deliver(self, inbound: Inbound, reply: str) -> None:
        """Send the turn's reply, and alarm on the one failure that cannot be
        shrugged off. Never raises."""
        delivered = await self._send_with_retry(inbound, reply)
        if not delivered and _ERASED.get():
            # **The one send failure that cannot be shrugged off.** Every other
            # reply that does not land costs a message; this one cost the main
            # their only chance to catch a mis-aimed erasure, because the body
            # is already tombstoned and there is nothing left to reverse or to
            # show. The id and never the claim (AD-22) — the claim is the thing
            # that was destroyed, and a log line is not where it goes to
            # survive.
            logger.error(
                "the reply confirming an erasure could not be delivered to "
                "main=%s; belief=%s is tombstoned and its words were never "
                "shown", inbound.main_id, _ERASED.get(),
            )

    async def _derive(self, inbound: Inbound) -> None:
        """Whether this turn's message was worth keeping (CAP-5, story 15a).

        **After the reply, and that is the rule rather than the arrangement.** A
        main waiting on a model call to find out whether what they wrote was
        worth keeping is the latency failure story 13b spent a review round on.
        The send has already been attempted by the time this is reached, so
        every way this can fail — no deriver, a breaker standing this main down,
        a gate past its bound, a provider refusing, a budget refusing, an
        unreadable answer, a raise, a full disk on the append — costs a claim
        and never a word of the main's answer.

        **The cost it does have, stated rather than discovered.** This runs
        inside that main's own turn worker, which takes one turn at a time
        (``_Turns``), so a derivation that ran to its bound sits in front of that
        main's *next* message. That is why ``half.derive.claim.BOUND_SECONDS`` is
        the whole budget a main already waits for one turn rather than the
        morning's twenty, and why the four gates run concurrently — a derivation
        costs one bound and not four. It is not bounded by ``_left``: that is the
        remainder of the budget of somebody who is waiting, and nobody is.

        **Outside the mutex for the model call, inside it for the append**, which
        is the ordering ``_pipeline`` already keeps for the same reason (AD-33):
        a model call under a main's lock holds eviction and every other operation
        on that main for the whole bound. ``ActorRegistry.acquire`` is not
        reentrant and the mutex was released before ``_handle`` sent anything, so
        this takes it again for the one append.

        **The claim enters at the weakest rung and cites the message it came
        from** (CAP-5, AD-28). The rung comes from ``ladder.admitted`` and never
        from a literal here, so there is no spelling of this call that could mint
        an `assert`; the support set names the evidence, so *every belief cites
        its evidence* is true of the stated ledger and not only the revealed one.
        Derivation decides *whether* there is a claim and never what Half may do
        with it.

        Never raises, and nothing here reads content into a log line (AD-22):
        what is logged is a ``main_id``, a gate name from a closed set, and an
        exception's class.
        """
        message_id = _DERIVABLE.get()
        if not message_id:
            # No message was recorded on this turn: a crisis turn, a redelivery,
            # or a turn that failed before the append. Nothing to derive from.
            return
        _DERIVABLE.set("")
        if not self.derivers.holds(inbound.main_id):
            # No deriver for this main. Not a fallback and not a failure: their
            # messages are recorded and read exactly as before, and no claim is
            # derived — which is every build before this story, minus the defect.
            return
        try:
            derived = await self.derivers.derive(
                inbound.text, main_id=inbound.main_id
            )
        except Exception as exc:  # noqa: BLE001 - the claim, never the reply
            # ``derive`` answers with a value rather than raising, so this is
            # unreachable through it. Broad for the reason the question path's
            # handler is broad: a bug here must cost the claim and nothing else.
            # The class only, never the exception's own text (AD-22).
            logger.warning(
                "nothing could be derived from a message for main=%s (%s); the "
                "message is recorded and the turn is unaffected",
                inbound.main_id, type(exc).__name__,
            )
            return
        if not derived.keeps:
            if derived.refused_by:
                # Gate names from a closed set — never the message, and never
                # the claim that was not written (AD-22). **Every** gate that
                # refused, because *"refused by decision-relevance and
                # falsifiability"* is a different fact from *"refused by
                # durability"* for anybody tuning this.
                logger.debug(
                    "main=%s: no claim was derived; refused by %s",
                    inbound.main_id, ", ".join(derived.refused_by),
                )
            return
        try:
            async with self.registry.acquire(inbound.main_id) as actor:
                claim_id = f"{DERIVED_PREFIX}{inbound.external_id}"
                if claim_id in actor.store.state().beliefs:
                    return  # already derived; a redelivery, not a second claim
                actor.store.record(
                    Op.ASSERT,
                    claim_id,
                    inbound.t,
                    subject="self",
                    # **The main's own words, from the message this turn
                    # already holds.** The deriver answered whether there is a
                    # claim and handed nothing back but four verdicts — see
                    # ``half.derive.claim.Derived``, which has no field a main's
                    # text could travel in. So this reads ``inbound`` and never
                    # a candidate, which is also what keeps
                    # ``tests/test_strands.py``'s scan of this file true.
                    claim=inbound.text,
                    **{LEDGER: STATED, DERIVATION: DERIVED},
                    **ladder.admitted(support=[message_id]),
                )
        except Exception as exc:  # noqa: BLE001 - the claim, never the reply
            logger.error(
                "a derived claim could not be recorded for main=%s (%s); the "
                "message is in the log and the turn is unaffected",
                inbound.main_id, type(exc).__name__,
            )

    def _expire_candidate(self, inbound: Inbound) -> None:
        """Drop a standing candidate this turn did not answer. Never raises.

        A candidate proposed *on this very turn* is kept — that is the turn that
        put it — and every other outcome ends it, including a redelivery of some
        other message, a crisis turn, and a turn the gate answered itself.
        """
        try:
            if self._corrections.stale(inbound.main_id, turn=inbound.external_id):
                self._corrections.answered(inbound.main_id, confirmed=False)
        except Exception as exc:  # noqa: BLE001 - never the reply
            logger.warning(
                "could not expire a correction candidate for main=%s (%s)",
                inbound.main_id, type(exc).__name__,
            )

    async def _send_with_retry(self, inbound: Inbound, reply: str) -> bool:
        """Send, retrying only what the platform says is worth retrying.

        ``SendFailed.retryable`` exists for this; it previously had no reader.

        **Answers whether it landed**, which is review loop 1's addition and has
        exactly one reader: an erasure's confirming turn. Every other
        undelivered reply costs a message, and the exchange is still in the log;
        that one cost the main the last moment a mis-aimed, irreversible removal
        could be caught, because the body is already gone. See ``_handle``, and
        ``_act`` for why the ordering is not the thing that moves.
        """
        for attempt, delay in enumerate((0.0, *RETRY_DELAYS)):
            if delay:
                await asyncio.sleep(delay)
            try:
                await self.channel.send(inbound.main_id, reply)
                return True
            except NotReachable:
                # Unreachable right now. Nothing is lost — the exchange is in
                # the log — and a later story decides whether to queue,
                # template, or stay quiet.
                return False
            except SendFailed as exc:
                if not exc.retryable or attempt == len(RETRY_DELAYS):
                    logger.warning(
                        "giving up on reply to main=%s: %s", inbound.main_id, exc
                    )
                    return False
            except HalfError:
                logger.exception("send failed for main=%s", inbound.main_id)
                return False
        return False

    async def _pipeline(self, inbound: Inbound) -> str | None:
        """The ordinary turn. Exactly one caller: the crisis gate (AD-10).

        Idempotent, because at-least-once delivery makes redelivery routine.

        **Two phases, and the mutex is held for the first only.** The main's
        message is recorded and their correction appended under this main's own
        lock; the words and the bought question happen afterwards, outside it,
        because ``ActorRegistry.acquire`` is not reentrant and the spend takes
        that same lock to make its check and its append one serialized
        operation — and because composing is a model call, which may not be made
        under a mutex (AD-33).

        **Why releasing between the two is safe, written out because it rests on
        a fact that could change.** Three things hold it:

        * *Two turns for one main cannot interleave.* Each main has their own
          inbox and worker (``_Turns``), which awaits one turn before taking the
          next, and every mutation goes through that main's own mutex (AD-1,
          AD-8). A turn is never evicted mid-flight and the append that closes it
          happens before the lock is released (AD-33).
        * *Nothing else spends.* Since review loop 1 the turn path is the **only**
          spender: the morning surface has no engine, no field for one, and
          cannot resolve an import into ``half.questions`` at all
          (``tests/test_bought.py``). So there is no second writer to race with
          across the gap.
        * *The spend does not trust the gap anyway.* ``UnaskedQueue.spend``
          re-runs every gate against a view read at that moment, and
          ``ActorRegistry.note_ask`` re-asserts the mode, the balance and the
          ladder inside a single acquire — so a favour cannot be spent twice even
          if the first two facts stopped holding.

        **The second fact is the fragile one.** A future story that lets another
        surface spend a favour — an interrupt, a nudge, a second channel —
        invalidates this argument, and the fix would be to move the spend back
        inside a single serialized operation rather than to widen this one. Say
        so here rather than discovering it from a balance that went negative.

        **What story 13b changed is none of the three: it is the width of the
        gap.** Until this story the offer and the buy were a build and a render
        apart — pure work with no suspension point between them — and now a
        model call sits in the middle, so the window is a whole
        ``half.voice.turn.TURN_BOUND_SECONDS`` wide and contains a real ``await``
        at which the loop runs everything else. That is worth writing down
        precisely because the three facts above are silent about it, and a
        reader could take their silence for coverage.

        It is safe, and for a reason rather than by luck. Two of the facts are
        about *who* may act and not about how long the gap is, so a wider gap
        does not touch them. The third is what now carries the weight: ``spend``
        re-reads the view at the moment it runs, so nothing it decides was
        computed before the wait. And what the wait newly admits is **eviction**
        — the mutex is released and ``Actor.claims`` is back to zero, so this
        main's actor can be dropped under memory pressure mid-turn. That costs
        nothing the spend reads: the balance, the ceiling and the ladder are
        hydrated from the log, and the one volatile input, the live strands, was
        *copied* above and travels as a value rather than being re-read off an
        actor that may be a different object by then (AD-26).

        The turn's own deadline bounds the width (``TURN_DEADLINE_SECONDS``), so
        the gap cannot grow without that number moving. What would invalidate
        this paragraph is not a slower model but a second bounded call added
        between the offer and the buy, or a spend that started reading anything
        it was handed before the wait.

        **The correction path is inside the lock, on purpose** (CAP-11, story
        12). It is an append to this main's log, so it happens under the acquire
        this method already holds — one lock acquisition, not two, which is what
        keeps the three facts above about the *gap* true rather than merely
        still written down. Nothing about a correction spends a favour or takes
        a second acquire, so *"nothing else spends"* is unchanged by this story.

        What runs **before** the lock is recognition: the offline table, which
        is pure, and the widening, which is a bounded network call. Neither may
        hold a main's mutex — a classifier hanging for its whole bound with the
        lock held would block eviction and every other operation on that main
        for two seconds per turn (AD-33).

        *The cost of that ordering, stated rather than discovered.* Recognition
        therefore runs **before** the redelivery check below, so a redelivered
        message pays for one classification that changes nothing. Moving it
        after the check would take a second acquire, which is the composition
        this docstring spends three paragraphs keeping out of the turn path — so
        the redelivery pays instead. It is bounded at one call per delivery, it
        is a crash-recovery path rather than a steady state, and the crisis gate
        already pays the same cost one layer up for the same reason.

        **A correction turn attaches no question, and that is a decision rather
        than an omission.** Three reasons, each sufficient:

        * ``ranked`` is computed *before* the removal, so a question offered
          after it could be about the belief this turn just removed — Half
          asking a clarifying question about a claim the main has, ten lines
          earlier, told it was wrong.
        * A correction clarifier and a bought question in one reply is two
          questions in one message, which is the rule the crisis gate already
          applies to aftercare (``quiet``): the main's next answer would land on
          whichever of them the code looked at first.
        * The clarifier spends no favour and passes through none of 5b's gates
          (the story's Never list). Putting it beside a bought question on one
          wire makes the free one indistinguishable from the paid one, in both
          directions.
        """
        # Recognition, outside the lock. ``meaning`` is the offline table's
        # answer and is never a model's; ``standing`` is a candidate this main
        # has not answered yet.
        meaning = correction_signals.recognize(inbound.text)
        standing = self._corrections.standing(inbound.main_id)
        # An explicit correction outranks a standing candidate: the main moved
        # on, and answering Half's old question with their new correction would
        # remove the wrong belief.
        confirmed = (
            standing is not None
            and meaning is None
            and correction_signals.is_confirmation(inbound.text)
        )
        inferred = (
            meaning is None
            and standing is None
            and await self._widened(inbound)
        )

        belief_id = f"b_{inbound.external_id}"
        async with self.registry.acquire(inbound.main_id) as actor:
            if belief_id in actor.store.state().beliefs:
                return None  # already handled; a redelivery, not a new message

            # The ceiling travels with the actor, so the cap this main is under
            # is applied wherever this turn resolves a license — never assembled
            # into the reply and then subtracted from it (AD-28).
            ranked = self._retrieve(actor, inbound)
            ceiling = actor.ceiling
            # The conversation as *this* turn left it. ``_retrieve`` has just
            # moved the strands against this message, so these are the weights
            # 5b's topic gate must read: a question is attached to the
            # conversation that already touches its subject, and this is that
            # conversation. Copied, so nothing downstream can move a main's
            # attention by writing into what it was handed (AD-26).
            live = actor.strands.copy()

            # The correction, under the same lock and **before** the main's own
            # message is recorded. A redelivery after a correction landed but
            # before the message did re-runs it against a fold the belief has
            # already left, which the plan reads as *already corrected* and
            # answers with nothing — the matrix row, arriving from the direction
            # that actually produces it.
            asked, removal, acted = self._correct(
                actor, inbound, ranked, this_turn=belief_id,
                meaning=meaning, standing=standing, confirmed=confirmed,
                inferred=inferred,
            )

            # Recorded last, and this ordering is load-bearing. Recording first
            # meant that anything failing afterwards — retrieval raising because
            # crisis had disabled it, say — left the belief durable, the turn
            # abandoned by run()'s per-message isolation, and the redelivery
            # suppressed by the idempotency check three lines up. The main's
            # message was answered by nothing and could never arrive again. The
            # append still closes the turn before the mutex is released (AD-33).
            actor.store.record(
                Op.ASSERT,
                belief_id,
                inbound.t,
                subject="self",
                claim=inbound.text,
                # **Evidence, and not a claim** (CAP-5, story 15a). The record
                # stays exactly where it was and keeps every reader it had —
                # the language sample, responsiveness, the correction aim's
                # exclusion — and gains the one fact that was missing. What it
                # stops being is a *belief*: retrieval, the context builder,
                # the tension minter and the ladder are handed claims and never
                # this, enforced by the doors they read through rather than by
                # a filter each of them applies (story 10's lesson).
                **{LEDGER: STATED, DERIVATION: UNDERIVED},
                # The rung comes from the ladder, never from a literal here.
                # A belief is admitted at the weakest rung and can reach any
                # other only through a promotion, which is an event involving
                # the main — so there is no spelling of this call that could
                # mint an `assert`.
                **ladder.admitted(),
            )
            # **Recorded, therefore derivable** — set inside the acquire and
            # after the append, so what ``_handle`` reads is a record that
            # exists. A turn that raised before this line, a redelivery that
            # returned above it, and a crisis turn that never reached this
            # method all leave it empty.
            _DERIVABLE.set(belief_id)
        # The mutex is released. Nothing below this line can cost the main their
        # message, their correction or their removal: all three are already
        # durable, and every step of composing and of attaching a question is
        # fail-open.
        #
        # **The words are composed here rather than inside the acquire**, and
        # that is story 13b's one structural change to this method. Composing
        # takes a model call, and a model call under a main's mutex would hold
        # eviction and every other operation on that main for the whole bound
        # (AD-33) — the same reason recognition already runs before the lock.
        # What the lock produced is *values*: the ranked set, the ceiling, the
        # live strands and the removal, and **nothing below reads the store
        # while composing**. The spend does take this main's mutex again
        # (``_offered`` reads the trust view, ``_bought`` writes the ``asked``
        # record), which is the whole reason the lock is released here rather
        # than held — ``ActorRegistry.acquire`` is not reentrant. What must not
        # happen below is a *model call* under the lock, and none does.
        if acted:
            # A correction acted, or Half put one to the main, or a standing
            # candidate was answered. No question — see this method's docstring
            # for the three reasons, and note that the answer is the same for
            # all three outcomes: the turn is about the correction either way.
            # **The removal is shown even when there is nothing else to say**,
            # which is the ordering review found inverted: returning early on an
            # empty reply left the belief gone durably, the candidate consumed,
            # and CAP-11's own success criterion — *Half shows what it removed*
            # — silently not happening.
            turned = await respond(
                inbound, ranked, ceiling=ceiling, voice=self.voice,
                removal=removal, bound_seconds=_left(voice_turn.TURN_BOUND_SECONDS),
            )
            if asked:
                # A proposal, not a removal: Half is asking. That line is still
                # the internal serialization and story 13b does not fix it —
                # see ``half.correction.apply.proposed``, which records why.
                return f"{turned.text}\n{asked}" if turned.text else asked
            return turned.text or None
        return await self._attach_question(
            inbound, ranked, ceiling=ceiling, live=live
        )

    async def _attach_question(
        self,
        inbound: Inbound,
        ranked: Ranked,
        *,
        ceiling: Ceiling | None,
        live: Strands | None,
    ) -> str | None:
        """The turn's reply, with one bought question **composed into it**
        (CAP-4).

        The whole of story 11's delivery, re-read in story 13b's light, and it
        is four steps with a refusal at each:

        1. **Offer.** Every gate 5b established, in 5b's order, through 5b's own
           door. Most turns stop here: the material is below `ask`, or below the
           stakes bar, or its topic was never raised, or no favour is unspent.
        2. **Build, then decide.** The context is rebuilt with the offered
           belief handed in as bought, and ``Context.question`` is empty
           whenever the builder emitted none — a belief the ladder raised
           *above* `ask`, or one whose only topic echoes its own claim (AD-18).
           **No question, no spend and no ``asked`` record**: the permission the
           favour buys is to *ask*, and a question nobody was asked costs
           nothing. Before review this spent the favour anyway and wrote a
           phantom record, which then suppressed the real question for one of
           the wanting's own periods.
        3. **Compose.** The question goes into the prompt as the ``ask-about``
           block and comes back inside the prose. **It is never appended as a
           line**, which is story 13b's rule and not a preference: a question on
           its own line is a questionnaire with one row, and CAP-4 exists to
           stop Half becoming one.
        4. **Spend, then send.** ``buy`` is the last thing before the caller
           puts this text on the wire (5b's contract). A send that then fails
           still costs the favour — story 10's asymmetry, inherited
           deliberately — and is logged where it happens, without content.

        **The spend now hangs on whether the composed prose is what goes out**,
        which is story 11's *"no line, no spend"* arriving on a path where there
        is no line. If generation failed, the fallback goes out — the claim
        alone, which asks nothing — so the favour would have paid for a question
        the main never saw. That is the mirror of the defect review found in
        story 11, where a spend happened before the thing it paid for existed.

        **There is deliberately no *"does the prose actually ask?"* test**, and
        ``half.voice.turn`` carries the argument: written Japanese asks with か,
        Thai with ไหม and much spoken-register Chinese with no mark at all, so a
        rule reading *no question mark* as *no question* would under-spend for
        exactly those mains and ask them the same thing for ever. What is
        decidable is whether the text carrying the question is the text being
        sent.

        **What that costs, said plainly, because a deletion made it true.**
        Story 11 measured the spend with ``question_line`` — the rendering — so
        *"the favour paid for a question"* and *"the delivered text contains
        one"* were the same assertion, checkable on the bytes. Story 13b takes
        that rendering off the wire, and there is no worldwide replacement for
        it, so the spend now hangs on ``composed`` alone: **the reply is the
        model's own prose, written from a prompt that carried the question**.
        That is a weaker statement than the one it replaces — a model handed an
        ``ask-about`` block and asking nothing spends the favour anyway — and it
        is the strongest one available in every language. The link it does keep
        is held in two places rather than one, and both are asserted: the
        question reaches the *prompt* (``tests/test_bought.py``,
        ``tests/test_turn_words.py``), and the prose built from that prompt is
        what goes out (``composed``). What is not asserted, and cannot be, is
        the middle.

        **A spend refused after the prose was written discards the prose**, and
        sends the claim alone instead. It is rare — the balance would have to
        change between the offer and the buy — and the alternative is worse in
        both directions: sending prose with an unpaid question in it breaks
        CAP-4, and composing a second time makes a waiting main pay a second
        bound for a race.

        **Never raises, and never returns nothing it had.** The main asked
        something and is owed an answer; a bug in the question path must cost
        the question and not the reply. Each step has its own handler, so a
        failure after the prose exists does not throw the prose away.
        """
        ask = await self._offered(inbound, ranked, ceiling=ceiling, live=live)
        turned = await respond(
            inbound, ranked, ceiling=ceiling, voice=self.voice,
            bought=ask.question.about if ask is not None else None,
            bound_seconds=_left(voice_turn.TURN_BOUND_SECONDS),
        )
        if ask is None or not turned.composed:
            if ask is not None:
                logger.debug(
                    "main=%s: the reply went out as the fallback, which asks "
                    "nothing; the favour is unspent", inbound.main_id,
                )
            return turned.text or None
        if await self._bought(inbound, ask, live=live):
            return turned.text or None
        return await self._unasked(inbound, ranked, ceiling=ceiling)

    async def _offered(
        self,
        inbound: Inbound,
        ranked: Ranked,
        *,
        ceiling: Ceiling | None,
        live: Strands | None,
    ):
        """The question this turn may carry, or ``None``. Never raises.

        Steps one and two of ``_attach_question``: every gate 5b established,
        and then the builder's own answer to *"was a question actually built?"*
        Nothing is spent here, so a refusal at either has nothing to undo and
        leaves no record to explain later.
        """
        if self.questions is None:
            return None
        try:
            ask = await self.questions.offer(
                inbound.main_id,
                beliefs=[candidate.id for candidate in (ranked or ())],
                live=live,
                now=inbound.t,
            )
            if ask is None:
                return None
            carried = build_context(
                ranked, now=inbound.t, ceiling=ceiling,
                bought=ask.question.about,
            ).question
            if carried is None:
                # Bought and unbuilt. Nothing is spent, so there is nothing to
                # undo and no record to explain later.
                logger.debug(
                    "main=%s: a question passed every gate and the builder "
                    "emitted none; nothing was spent", inbound.main_id,
                )
                return None
            return ask
        except Exception as exc:  # noqa: BLE001 - the question, never the reply
            # The *type* and nothing else (AD-22): an exception message
            # routinely quotes the value that caused it, and here that is a
            # record out of a main's own ledger.
            logger.warning(
                "could not offer a question for main=%s (%s); the reply goes "
                "out without one", inbound.main_id, type(exc).__name__,
            )
            return None

    async def _bought(self, inbound: Inbound, ask, *, live: Strands | None) -> bool:
        """Spend the favour this question was offered against. Never raises.

        The last thing that happens before the text goes on the wire, which is
        5b's own contract. ``False`` is *the question does not go out*, and the
        caller sends something that asks nothing rather than something the
        favour did not pay for.
        """
        try:
            purchase = await self.questions.buy(
                inbound.main_id, t=inbound.t, ask=ask, live=live
            )
        except Exception as exc:  # noqa: BLE001 - the question, never the reply
            logger.warning(
                "could not spend a favour for main=%s (%s); the reply goes out "
                "without a question", inbound.main_id, type(exc).__name__,
            )
            return False
        if not purchase.spent:
            logger.debug(
                "main=%s: the spend was refused (%s); the reply goes out "
                "without a question", inbound.main_id, purchase.outcome,
            )
        return bool(purchase.spent)

    async def _unasked(
        self, inbound: Inbound, ranked: Ranked, *, ceiling: Ceiling | None
    ) -> str | None:
        """What goes out when a question was composed and not paid for.

        **The claim alone where there is one**, and it asks nothing by
        construction, which is the property that has to hold: the reply must not
        carry a question the favour did not buy.

        **And prose where there is not**, which is review loop 1's correction.
        This used to be the fallback and nothing else, on the argument that a
        race at the spend must not cost a waiting main a second bound. That
        argument holds right up to the turn where the fallback is empty — a
        directives-only turn, which is most turns for a main under an aftercare
        ceiling — and there it produced **total silence** for somebody whose
        working composer had already written them a reply. Weighed against a
        second bound, silence loses; and the second call is bounded by whatever
        is left of the turn's own deadline rather than by a fresh one
        (``TURN_DEADLINE_SECONDS``), so it is not a second wait of the same
        size. It is composed with no bought question at all, so what comes back
        cannot carry the one nobody paid for.

        Never raises: ``respond`` does not, and the fallback is computed from
        values this turn already holds.
        """
        spare = voice_turn.fallback(
            build_context(ranked, now=inbound.t, ceiling=ceiling)
        )
        if spare:
            return spare
        second = await respond(
            inbound, ranked, ceiling=ceiling, voice=self.voice,
            bound_seconds=_left(voice_turn.TURN_BOUND_SECONDS),
        )
        return second.text or None

    async def _widened(self, inbound: Inbound) -> bool:
        """Whether a model reads this turn as a correction. Never raises.

        Consulted **only when the table found nothing and no candidate is
        standing**, which is what makes *one classification per turn at most*
        true by construction rather than by counting: the caller returns before
        this is reached in every other case.

        A ``True`` here is a **candidate and never an append**. What it can
        produce is a line asking the main; ``half.correction.apply.plan``
        refuses to build a removal from it without their answer, so a second
        inference route added later meets the same refusal.
        """
        if not self._corrections.holds(inbound.main_id):
            # No model for this main. Not a fallback and not a failure: the
            # offline table decides alone, which is a supported deployment.
            return False
        left = _left(candidate_module.BOUND_SECONDS)
        if left <= 0:
            # The turn's budget is spent. The table's answer stands, which is
            # the same outcome a timeout would have produced — reached without
            # making the main wait for it.
            logger.debug(
                "no time was left in the turn to widen recognition for "
                "main=%s; the table's answer stands", inbound.main_id,
            )
            return False
        try:
            verdict = await self._corrections.consult(
                inbound.text, main_id=inbound.main_id, bound_seconds=left,
            )
        except Exception as exc:  # noqa: BLE001 - the widening, never the reply
            # ``consult`` answers with a verdict rather than raising, so this is
            # unreachable through it. Broad for the reason the question path's
            # handler is broad: a bug in recognition must cost the recognition
            # and never the main's answer. The class only, never the exception's
            # own text — a provider quotes the request it rejected (AD-22).
            logger.warning(
                "the correction widening could not be taken for main=%s (%s); "
                "the table's answer stands", inbound.main_id, type(exc).__name__,
            )
            return False
        return verdict.asks

    def _correct(
        self,
        actor: Actor,
        inbound: Inbound,
        ranked: Ranked,
        *,
        this_turn: str,
        meaning: correction_signals.Meaning | None,
        standing: Removal | None,
        confirmed: bool,
        inferred: bool,
    ) -> tuple[str, Removal | None, bool]:
        """Act on this turn's correction, if there is one (CAP-11).

        Three answers: the **proposal line** to append when Half is asking, the
        **removal** to compose the reply around when one happened, and whether
        the correction path did anything at all. The last is separate from the
        other two: a **declined** candidate says nothing, removes nothing and
        still owns the turn, because the main was answering Half's question
        rather than starting a new topic.

        **A removal travels as a value rather than as a rendered line**, which
        is story 13b's change here. The reply is prose composed around the
        removed claim, so the caller needs the claim and not a string somebody
        already decided how to present.

        **Never raises.** Every step is inside one broad ``except``, for the
        reason ``CrisisGate._suspend`` is: the main asked something and is owed
        an answer, and a full disk or a refactored signature must cost the
        correction rather than the reply. A failed append is loud and content-
        free; the next delivery of the same message retries it, because a
        redelivery is routine and the removal is idempotent.

        **The target is this turn's top-ranked belief**, and that is the only
        instrument the tree has: v1 has no reply-quoting, so *"which belief did
        they mean"* is answered by what the conversation is about — which is
        exactly what ``_retrieve`` has just scored, with the strands already
        moved against this message. It can be wrong, and the answer to its being
        wrong is the story's own: Half **shows the claim it removed**, so a
        mis-aimed correction is visible on the same turn and the main can
        correct the correction, which appends and leaves both in the log.
        """
        try:
            return self._removal(
                actor, inbound, ranked, this_turn=this_turn,
                meaning=meaning, standing=standing, confirmed=confirmed,
                inferred=inferred,
            )
        except Exception as exc:  # noqa: BLE001 - the correction, never the reply
            # The class and nothing else (AD-22): an exception message routinely
            # quotes the value that caused it, and here that is a claim out of a
            # main's own ledger.
            logger.error(
                "a correction did not land for main=%s (%s); the reply goes "
                "out without it", inbound.main_id, type(exc).__name__,
            )
            return "", None, False

    def _removal(
        self,
        actor: Actor,
        inbound: Inbound,
        ranked: Ranked,
        *,
        this_turn: str,
        meaning: correction_signals.Meaning | None,
        standing: Removal | None,
        confirmed: bool,
        inferred: bool,
    ) -> tuple[str, Removal | None, bool]:
        """The five outcomes, in the order they can happen on one message.

        An explicit correction acts — **unless it is an erasure**, which is put
        to the main like an inferred one, because an erasure destroys the body
        and *"the main can correct the correction"* is not available for it. A
        standing candidate the main confirmed acts, as whatever it was proposed
        as. A standing candidate they did not confirm is over and removes
        nothing — and does **not** own the turn, so the ordinary reply and its
        bought question still happen: a proposal must not swallow the unrelated
        question the main asked next. A turn only the classifier read as a
        correction is put to the main and appends nothing.
        """
        if meaning is not None:
            if standing is not None:
                # The main corrected something explicitly instead of answering.
                # The old candidate is over — re-offering it later would be Half
                # asking twice about a topic the main has moved past.
                self._corrections.answered(inbound.main_id, confirmed=False)
            target = self._aimed(ranked, this_turn=this_turn)
            if meaning in correction.NEEDS_ANSWER:
                return self._propose(actor, inbound, target, meaning=meaning,
                                     source=Source.TABLE)
            return self._act(actor, inbound, meaning, target)

        if standing is not None:
            if not confirmed:
                # Declined. Nothing removed, nothing appended beyond the
                # exchange — and *anything that is not a clear yes* is a
                # decline, because silence is not consent and neither is
                # *maybe*. ``acted`` is False so the turn carries on as the
                # ordinary turn it also is.
                self._corrections.answered(inbound.main_id, confirmed=False)
                return "", None, False
            _, removal, acted = self._act(
                actor, inbound, standing.meaning, standing.target,
                source=standing.source, confirmed=True,
            )
            # **Counted on what happened, not on what was said.** If the belief
            # left the fold between the proposal and the answer there is nothing
            # to remove — the idempotent row — and booking that as a confirmed
            # deletion would tell an operator the main deleted something they
            # did not.
            self._corrections.answered(inbound.main_id, confirmed=acted)
            return "", removal, True

        if not inferred:
            return "", None, False
        return self._propose(
            actor, inbound, self._aimed(ranked, this_turn=this_turn),
            meaning=correction_signals.Meaning.WRONG, source=Source.INFERRED,
        )

    def _propose(
        self,
        actor: Actor,
        inbound: Inbound,
        target: str,
        *,
        meaning: correction_signals.Meaning,
        source: Source,
    ) -> tuple[str, Removal | None, bool]:
        """Show what would be removed and ask. Appends nothing.

        Two routes arrive here and neither may act: a classifier reading, and an
        erasure however it was recognised. The candidate is stamped with this
        turn, so the answer is only read from the turn after it — see
        ``_expire_candidate``.
        """
        offered = correction.proposal(
            target, self._held(actor, target), meaning=meaning, source=source
        )
        if offered is None:
            # There is nothing Half holds for the correction to be about.
            # Nothing is asked and nothing is recorded: a question naming no
            # belief is a question with no answer.
            return "", None, False
        self._corrections.propose(
            inbound.main_id, offered, turn=inbound.external_id
        )
        # **The proposal travels as a line and not as a removal**, and that is
        # the deferral story 13b records rather than hides: a proposal
        # deliberately withholds the claim (AD-18), so there is nothing to
        # compose prose around. See ``half.correction.apply.proposed``.
        return correction.proposed(offered), None, True

    def _act(
        self,
        actor: Actor,
        inbound: Inbound,
        meaning: correction_signals.Meaning,
        target: str,
        *,
        source: Source = Source.TABLE,
        confirmed: bool = False,
    ) -> tuple[str, Removal | None, bool]:
        """Append the correction and hand back the removal it performed.

        ``plan`` answers ``None`` for a correction naming nothing Half holds and
        for one whose belief has already left the fold — two matrix rows, one
        branch, and neither is an error the main is shown.
        """
        removal = correction.plan(
            meaning,
            target=target,
            belief=self._held(actor, target),
            source=source,
            confirmed=confirmed,
        )
        if removal is None:
            return "", None, False
        if removal.erases:
            # The store's own validate-then-erase: the op *and* the tombstoning
            # of the bodies, which a bare append would not do. An erasure that
            # left the text on disk is not an erasure.
            #
            # **The body goes before the send is acknowledged, and that is a
            # choice rather than an oversight** (review loop 1). A permanent
            # send failure therefore leaves the body gone and the words never
            # delivered, which is a real loss — the confirming turn is the last
            # moment a mis-aim is catchable. Both other orderings are worse.
            # *Tombstoning after the send* needs a second acquire on this main's
            # mutex and makes a crash in the gap into a deletion the main asked
            # for, was told about, and did not get: a privacy request silently
            # unfulfilled, which is the failure with the higher floor. *Showing
            # the claim on the asking turn instead* is a licence question about
            # what Half may quote while it is only proposing, which
            # ``correction.proposed`` records as needing its own story. So the
            # ordering stays and the failure is made **loud** instead: the send
            # answers whether it landed and ``_handle`` alarms when it did not.
            _ERASED.set(removal.target)
            actor.store.expunge(removal.target, t=inbound.t)
        else:
            actor.store.record(
                removal.op,
                correction.record_id(removal, t=inbound.t),
                inbound.t,
                **correction.fields(removal, t=inbound.t),
            )
        # **The removal is returned after the append, claim and all.** For an
        # erasure that ordering is the matrix's own row: the claim was read off
        # the fold by ``plan`` *before* ``Store.expunge`` tombstoned the body,
        # so it is still here to be shown and the body is already gone.
        return "", removal, True

    @staticmethod
    def _aimed(ranked: Ranked, *, this_turn: str) -> str:
        """Which belief this turn's correction is about, or ``""``.

        The choosing is ``half.correction.apply.aim``'s, which is where the two
        filters that make it safe live — a relevance floor read off the strand
        weight retrieval already computed, and the exclusion of the message that
        carried the correction. Here because the runtime knows this turn's own
        belief id and nothing under ``half/correction`` does.
        """
        return correction.aim(ranked or (), exclude=(this_turn,))

    @staticmethod
    def _held(actor: Actor, target: str) -> dict | None:
        """The folded belief ``target`` names, or ``None``.

        Read from the fold rather than off the ranked candidate, so that *"the
        claim as recorded"* is the record and not a copy of it that ranking
        happened to carry — and so that a belief which left the fold between
        ranking and here is absent, which is what makes the correction
        idempotent.
        """
        if not target:
            return None
        return actor.store.state().beliefs.get(target)

    def _retrieve(self, actor: Actor, inbound: Inbound) -> Ranked:
        """Rank this main's beliefs against the turn, or rank nothing.

        ``now`` comes from the inbound stamp the adapter read, so nothing below
        this line touches a clock and two replays of one conversation rank
        identically.

        The strand weights are moved before ranking, not after: this message is
        what makes a strand live, and scoring it against last turn's attention
        would rank every topic switch one turn late.

        ``RetrievalDisabled`` is caught here and nowhere else. The raise is kept
        deliberately loud inside the retriever — a disable must never be
        mistakable for an empty ledger — and catching it is what keeps a
        disabled ledger from *raising* the turn.

        **And it keeps the reply, which is this method's whole invariant: a
        degradation changes what Half knows, never whether Half answers.** That
        sentence stopped being true for one commit of story 13b and it is worth
        recording why, because the reasoning was locally correct at every step.
        The fallback ladder is prose, then the claim alone, then silence; a
        disabled ledger has no claim; so the turn completed, recorded the
        message, and sent nothing. The same held wherever the material was all
        `behave`, which is most turns for most mains — and it included every
        main under an aftercare ceiling (AD-28) for at least thirty days, and
        every main whose retrieval a crisis disabled, which comes back on only
        by an explicit operator action. CAP-12 says Half *stays present*;
        ``tests/test_crisis.py::test_a_reply_is_always_sent`` calls going quiet
        *"a failure here, not an outcome"*.

        The rung was never the question. A reply is composed from the language
        the main just wrote in and shaped by whatever the context holds,
        **including nothing** — ``half.voice.turn.words`` composes for an empty
        context rather than refusing it, and the instructions already say what
        to write when there is nothing that may be stated. So a ``Ranked()``
        here costs Half its ranking for that turn and costs the main nothing.

        A tokenizer refusal is caught for the same reason and on the same terms.
        The ceilings in ``half.text`` exist to stop an unbounded expansion, not
        to end a conversation: a message or a stored strand label past them must
        cost Half its ranking for that turn, never the main their reply. Both
        the strand observation and the search can raise it, so both are inside.
        """
        state = actor.store.state()
        retriever = Retriever(
            store=actor.store, reranker=self.reranker, switch=actor.retrieval
        )
        try:
            actor.strands.observe(
                inbound.text, known_strands(state.beliefs.values(), state.loops)
            )
            return retriever.retrieve(inbound.text, now=inbound.t,
                                      strands=actor.strands)
        except RetrievalDisabled:
            # No content, and not even an exception message (AD-22).
            logger.info("retrieval disabled for main=%s; replying without the "
                        "ledger", inbound.main_id)
            return Ranked()
        except (TokenGrowthLimitError, QueryTooLargeError):
            # The type only — never the text that provoked it (AD-22).
            logger.warning(
                "retrieval could not tokenize this turn for main=%s; replying "
                "without the ledger", inbound.main_id
            )
            return Ranked()


def about(
    removal: Removal,
    ranked: Ranked | None,
    *,
    now: str,
    ceiling: Ceiling | None,
) -> tuple[Context, frozenset[str]]:
    """The context a correction reply is composed from, and what it withholds.

    **The removed claim is the one thing this reply may state**, so it is the
    whole of the content channel and nothing else is. A correction turn is about
    the belief that left; letting whatever else this turn's ranking put on top
    into the quotable channel would let the model answer *"that's wrong"* with
    an unrelated statement.

    **And it is not withheld, which is the point.** AD-18 forbids `behave` text
    inside a constructed context, and the belief a main has just corrected is
    almost always `behave` — every belief is admitted there. Left in the
    withheld set, the tripwire would refuse every composed correction reply that
    did what CAP-11 asks, for ever, and Half would fall back on every single
    correction with nothing failing. ``half.correction.apply`` already carries
    the argument for why quoting it is not the AD-18 hole it resembles: CAP-11
    requires it in as many words, the main has just told Half the claim is
    wrong, and it is the one thing that makes a mis-aimed correction visible.

    So the withheld set is computed over **the rest** of the ranked material
    rather than over all of it — an exclusion of one belief by id, not a
    subtraction of one claim's wordings. Every other `behave` claim is withheld
    exactly as it was, so the reply cannot leak a *different* belief sideways.

    **And then the removed claim's own wordings come out of that set**, which is
    review loop 1's finding and the one place the exclusion-by-id is not enough.
    The tripwire's unit is the adjacent word pair, so a removed claim that
    shares two consecutive words with a *different* withheld belief — two
    beliefs about the same plot, the same brother, the same week — puts those
    pairs in ``hidden`` even though the belief they came from is excluded. Every
    composed correction reply then does exactly what CAP-11 asks, trips the
    tripwire for doing it, and falls back; and because the fallback *is* the
    claim, the wire looks identical and only ``Tally.leaked`` moves. The
    composed path would be permanently dead for those claims with nothing
    failing anywhere.

    Subtracting the claim's own pairs is proportionate rather than a hole: a
    pair is two words, the other belief keeps every pair it does not share, and
    what the tripwire exists to catch — a *different* belief's wording arriving
    in the reply — still needs one of those. The alternative, re-running
    ``split``'s leak guard over the injected content, drops the claim and
    answers *"that's wrong"* with nothing at all, which is the failure CAP-11 is
    written against.

    ``Ranked``'s own annotations (``truncated``, ``rerank``) do not travel,
    because the material is filtered to a tuple. Nothing on the composing path
    reads them; the ordinary reply, which does carry them, is built by
    ``respond`` from ``ranked`` itself.

    Pure. No store, no clock, no model.
    """
    others = tuple(
        candidate for candidate in (ranked or ())
        if getattr(candidate, "id", "") != removal.target
    )
    context, hidden = split_context(others, now=now, ceiling=ceiling)
    claim = correction.shown(removal)
    if not claim:
        # A record whose claim this build cannot read. There is nothing to
        # show — and the opening invariant still holds, so there is nothing
        # this reply may state either. The content channel is emptied rather
        # than left as the ordinary turn's, which is what it used to be: a
        # correction turn answering *"that's wrong"* with an unrelated
        # statement, at the one moment the main is checking Half's work. The
        # directives stay, so the reply is still shaped and still happens.
        return replace(context, content=()), hidden
    return replace(
        context, content=(Content(id=removal.target, claim=claim),)
    ), hidden - frozenset(fragments(claim))


async def respond(
    inbound: Inbound,
    ranked: Ranked | None = None,
    *,
    ceiling: Ceiling | None,
    voice: Voice | None = None,
    bought: str | None = None,
    removal: Removal | None = None,
    bound_seconds: float | None = None,
) -> Turned:
    """The turn's words: prose, the claim alone, or nothing (story 13b).

    Until this story it returned ``"noted."``, or ``"noted. "`` bolted to a raw
    claim — an English word on a worldwide product, and the internal
    serialization one join away. What it does now is build the two-channel
    context (AD-18) and hand it to ``half.voice.turn``, which composes through
    the model port, judges the result cheaply, regenerates a bounded number of
    times and **falls back to the claim alone** when it cannot.

    ``now`` is the inbound stamp the adapter read. Nothing below this line
    touches a clock, so one conversation replays to one set of replies.

    Four properties this shape holds that a filter could not:

    * `behave` and `ask` claim text is absent from the reply because it is
      absent from the context — there is no branch here that could re-admit it.
      The one exception is the belief a correction has just removed, which
      CAP-11 requires be shown and which ``about`` admits deliberately and by
      name.
    * The main's own message cannot become **material Half may state**. It
      travels as a ``Sample``, which is a type with no parameter on the quotable
      path it could arrive through, and the belief carrying it is recorded after
      this returns and recorded `behave`.

      *That is the whole of the guarantee, and this bullet used to claim more.*
      It said the reply never echoes the main's own words, which nothing checks
      and nothing could: the model is **told** not to repeat the language sample
      back (``half.voice.compose.INSTRUCTIONS``), and enforcing it would mean
      putting this turn's inbound text into the withheld set — where the
      tripwire's adjacent-word-pair rule would refuse an ordinary reply for
      reusing two consecutive words of a message written in the same language,
      loudly, and fall back on most turns. What is structural is that the
      sample cannot reach the quotable channel; what is asked for is that the
      model not parrot it; and the difference between the two is stated here
      rather than left as a promise the code does not keep.
    * A context with no content produces prose, the fallback, or nothing — never
      a template and never a phrase about missing access (AD-24, AD-27). *No
      content is not a reason for silence*, which is review loop 1's second
      amendment: a disabled ledger changes what Half knows, never whether Half
      answers.
    * The bought question is **composed into** the prose. There is no line to
      append and no branch here that could append one.

    ``ceiling`` is this main's global cap and is applied inside the context
    build, where licenses are resolved. Nothing here inspects it or subtracts
    anything afterwards: a capped belief simply never reaches the quotable
    channel (AD-28).

    Never raises, and **that is a handler rather than an inventory of what
    cannot go wrong**. Every path out is a ``Turned``, and a blank message is
    ``Turned()`` — silence, which is what a blank message has always got. The
    cost of a raise here is not one turn: the main's message is recorded before
    this is reached, so ``Runtime._isolated`` catches it, the idempotency check
    suppresses the redelivery, and that message is answered by nothing for ever.
    ``half.voice.turn.words`` holds the same handler for the same reason, so a
    fault in the composer and a fault in the *build* of what it composes from
    both cost the prose and never the reply.
    """
    if not inbound.text.strip():
        return Turned()
    show = correction.shown(removal) if removal is not None else ""
    try:
        if removal is not None:
            context, hidden = about(
                removal, ranked, now=inbound.t, ceiling=ceiling
            )
        else:
            context, hidden = split_context(
                ranked, now=inbound.t, ceiling=ceiling, bought=bought
            )
    except Exception as exc:  # noqa: BLE001 - the context, never the reply
        # Building the context reads records out of a main's own ledger, folds
        # arbitrary text and resolves a ladder over it. The class only, never
        # the exception's own text (AD-22). What is left is whatever this turn
        # already had in hand — the removed claim on a correction turn, and
        # nothing on any other.
        logger.error(
            "the context for main=%s could not be built (%s); the turn answers "
            "with what it already holds", inbound.main_id, type(exc).__name__,
        )
        return Turned(voice_turn.fallback(None, show=show))
    return await voice_turn.words(
        voice,
        context,
        main_id=inbound.main_id,
        sample=Sample(inbound.text),
        withheld=hidden,
        show=show,
        bound_seconds=bound_seconds,
    )
