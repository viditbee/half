"""Wiring: channel -> crisis gate -> actor -> store (AD-17).

Two policies here were human decisions, not defaults:

**Per-message isolation.** No single message's failure ends the inbound loop.
An uncaught error used to propagate out of ``run()`` and stop polling for
*every* main — Half stayed up and silently stopped receiving.

**At-least-once delivery.** The transport commits its position only after a
turn completes, so a crash redelivers rather than loses. That makes redelivery
routine, so the turn is idempotent: a message already recorded is not recorded
twice.

The responder is a deterministic stub — no model is called anywhere yet, which
keeps the suite hermetic. Later stories replace ``respond`` without touching
the channel or the registry.

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
* **The question is attached after the reply is composed and the turn is
  recorded**, so nothing about buying one can cost the main their answer. Every
  step of it is fail-open.
* **The favour is spent only once the built text carries the question line**,
  and immediately before that text is sent. A belief the ladder raised above
  `ask`, or one whose topic echoes its claim, produces no line — and used to
  spend a favour and write an ``asked`` record for a question nobody was asked.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from half.actor.registry import Actor, ActorRegistry
from half.channel.port import Channel, Inbound
from half.context.build import build as build_context
from half.context.channels import Context, render_line
from half.correction import apply as correction
from half.correction import signals as correction_signals
from half.correction.apply import Removal, Source
from half.correction.candidate import Widening
from half.crisis.aftercare import Schedule
from half.crisis.classifier import SecondOpinion
from half.crisis.gate import CrisisGate
from half.crisis.handoff import Desk
from half.crisis.safetyplan import Holder
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
from half.store.records import LEDGER, STATED

logger = logging.getLogger(__name__)

#: Backoff between retries of a retryable send, in seconds.
RETRY_DELAYS = (1.0, 4.0, 15.0)

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
    _gate: CrisisGate = field(init=False, repr=False)

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
        reply = await self._gate.handle(inbound)
        if reply is None:
            return  # silence is an outcome, not a failure (AD-27)
        await self._send_with_retry(inbound, reply)

    async def _send_with_retry(self, inbound: Inbound, reply: str) -> None:
        """Send, retrying only what the platform says is worth retrying.

        ``SendFailed.retryable`` exists for this; it previously had no reader.
        """
        for attempt, delay in enumerate((0.0, *RETRY_DELAYS)):
            if delay:
                await asyncio.sleep(delay)
            try:
                await self.channel.send(inbound.main_id, reply)
                return
            except NotReachable:
                # Unreachable right now. Nothing is lost — the exchange is in
                # the log — and a later story decides whether to queue,
                # template, or stay quiet.
                return
            except SendFailed as exc:
                if not exc.retryable or attempt == len(RETRY_DELAYS):
                    logger.warning(
                        "giving up on reply to main=%s: %s", inbound.main_id, exc
                    )
                    return
            except HalfError:
                logger.exception("send failed for main=%s", inbound.main_id)
                return

    async def _pipeline(self, inbound: Inbound) -> str | None:
        """The ordinary turn. Exactly one caller: the crisis gate (AD-10).

        Idempotent, because at-least-once delivery makes redelivery routine.

        **Two phases, and the mutex is held for the first only.** The reply is
        composed and the main's message recorded under this main's own lock, as
        they have been since story 6d; the bought question is attached
        afterwards, outside it, because ``ActorRegistry.acquire`` is not
        reentrant and the spend takes that same lock to make its check and its
        append one serialized operation.

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
        standing = (
            self.corrections.standing(inbound.main_id)
            if self.corrections is not None else None
        )
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
            reply = respond(inbound, ranked, ceiling=ceiling)
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
            said, acted = self._correct(
                actor, inbound, ranked,
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
                **{LEDGER: STATED},
                # The rung comes from the ladder, never from a literal here.
                # A belief is admitted at the weakest rung and can reach any
                # other only through a promotion, which is an event involving
                # the main — so there is no spelling of this call that could
                # mint an `assert`.
                **ladder.admitted(),
            )
        # The mutex is released. Nothing below this line can cost the main their
        # reply: it is already composed, their message is already recorded, and
        # every step of attaching a question is fail-open.
        if reply is None:
            return None
        if acted:
            # A correction acted, or Half put one to the main, or a standing
            # candidate was answered. No question — see this method's docstring
            # for the three reasons, and note that the answer is the same for
            # all three outcomes: the turn is about the correction either way.
            # A decline says nothing and still counts, which is why this branch
            # turns on ``acted`` and not on there being a line.
            return f"{reply}\n{said}" if said else reply
        return await self._attach_question(
            inbound, ranked, ceiling=ceiling, live=live, reply=reply
        )

    async def _attach_question(
        self,
        inbound: Inbound,
        ranked: Ranked,
        *,
        ceiling: Ceiling | None,
        live: Strands | None,
        reply: str,
    ) -> str:
        """``reply`` with one bought question attached, or ``reply`` (CAP-4).

        The whole of story 11's delivery, and it is four steps with a refusal at
        each:

        1. **Offer.** Every gate 5b established, in 5b's order, through 5b's own
           door. Most turns stop here: the material is below `ask`, or below the
           stakes bar, or its topic was never raised, or no favour is unspent.
        2. **Build.** The context is rebuilt with the offered belief handed in as
           bought. Nothing else changes, so the question is the only difference
           between the two renderings.
        3. **Render, then decide.** ``question_line`` is empty whenever the
           builder emitted no ``Question`` — a belief the ladder raised *above*
           `ask`, or one whose only topic echoes its own claim (AD-18). **No
           line, no spend, and no ``asked`` record**: the permission the favour
           buys is to *ask*, and a question nobody was asked costs nothing.
           Before review this spent the favour anyway and wrote a phantom record,
           which then suppressed the real question for one of the wanting's own
           periods.
        4. **Spend, then send.** ``buy`` is the last thing before the caller puts
           this text on the wire (5b's contract). A send that then fails still
           costs the favour — story 10's asymmetry, inherited deliberately — and
           is logged where it happens, without content.

        **Never raises, and never returns nothing.** The main asked something and
        is owed an answer; a bug in the question path must cost the question and
        not the reply. This is the one handler on this path and it is exercised
        by a test that makes the engine raise, because a fail-open branch nothing
        has ever run is a branch nobody knows is open.
        """
        if self.questions is None:
            return reply
        try:
            ask = await self.questions.offer(
                inbound.main_id,
                beliefs=[candidate.id for candidate in (ranked or ())],
                live=live,
                now=inbound.t,
            )
            if ask is None:
                return reply
            line = question_line(
                build_context(
                    ranked, now=inbound.t, ceiling=ceiling,
                    bought=ask.question.about,
                )
            )
            if not line:
                # Bought and unrendered. Nothing is spent, so there is nothing
                # to undo and no record to explain later.
                logger.debug(
                    "main=%s: a question passed every gate and produced no "
                    "line; nothing was spent", inbound.main_id,
                )
                return reply
            purchase = await self.questions.buy(
                inbound.main_id, t=inbound.t, ask=ask, live=live
            )
            if not purchase.spent:
                logger.debug(
                    "main=%s: the spend was refused (%s); the reply goes out "
                    "without a question", inbound.main_id, purchase.outcome,
                )
                return reply
            return f"{reply}\n{line}"
        except Exception as exc:  # noqa: BLE001 - the question, never the reply
            # The *type* and nothing else (AD-22): an exception message
            # routinely quotes the value that caused it, and here that is a
            # record out of a main's own ledger.
            logger.warning(
                "could not attach a question for main=%s (%s); the reply goes "
                "out without one", inbound.main_id, type(exc).__name__,
            )
            return reply

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
        if self.corrections is None:
            return False
        try:
            verdict = await self.corrections.consult(
                inbound.text, main_id=inbound.main_id
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
        meaning: correction_signals.Meaning | None,
        standing: Removal | None,
        confirmed: bool,
        inferred: bool,
    ) -> tuple[str, bool]:
        """Act on this turn's correction, if there is one (CAP-11).

        Returns the line to append to the reply and whether the correction path
        did anything at all. The two are different: a **declined** candidate
        says nothing and still owns the turn, because the main was answering
        Half's question rather than starting a new topic.

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
                actor, inbound, ranked,
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
            return "", False

    def _removal(
        self,
        actor: Actor,
        inbound: Inbound,
        ranked: Ranked,
        *,
        meaning: correction_signals.Meaning | None,
        standing: Removal | None,
        confirmed: bool,
        inferred: bool,
    ) -> tuple[str, bool]:
        """The four outcomes, in the order they can happen on one message.

        An explicit correction acts. A standing candidate the main confirmed
        acts. A standing candidate they did not confirm is over and removes
        nothing. A turn only the classifier read as a correction is put to the
        main and appends nothing.
        """
        if meaning is not None:
            if standing is not None and self.corrections is not None:
                # The main corrected something explicitly instead of answering.
                # The old candidate is over — re-offering it later would be Half
                # asking twice about a topic the main has moved past.
                self.corrections.answered(inbound.main_id, confirmed=False)
            return self._act(actor, inbound, meaning, self._aimed(ranked))

        if standing is not None and self.corrections is not None:
            self.corrections.answered(inbound.main_id, confirmed=confirmed)
            if not confirmed:
                # Declined. Nothing removed, nothing appended beyond the
                # exchange — and *anything that is not a clear yes* is a
                # decline, because silence is not consent and neither is
                # *maybe*.
                return "", True
            return self._act(
                actor, inbound, correction_signals.Meaning.WRONG, standing.target,
                source=Source.INFERRED, confirmed=True,
            )

        if not inferred or self.corrections is None:
            return "", False
        target = self._aimed(ranked)
        offered = correction.proposal(target, self._held(actor, target))
        if offered is None:
            # A model read a correction and there is nothing Half holds for it
            # to be about. Nothing is asked and nothing is recorded: a question
            # naming no belief is a question with no answer.
            return "", False
        self.corrections.propose(inbound.main_id, offered)
        return correction.proposed(offered), True

    def _act(
        self,
        actor: Actor,
        inbound: Inbound,
        meaning: correction_signals.Meaning,
        target: str,
        *,
        source: Source = Source.TABLE,
        confirmed: bool = False,
    ) -> tuple[str, bool]:
        """Append the correction and return what Half shows.

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
            return "", False
        if removal.erases:
            # The store's own validate-then-erase: the op *and* the tombstoning
            # of the bodies, which a bare append would not do. An erasure that
            # left the text on disk is not an erasure.
            actor.store.expunge(removal.target, t=inbound.t)
        else:
            actor.store.record(
                removal.op,
                correction.record_id(removal, t=inbound.t),
                inbound.t,
                **correction.fields(removal, t=inbound.t),
            )
        return correction.shown(removal), True

    @staticmethod
    def _aimed(ranked: Ranked) -> str:
        """Which belief this turn's correction is about, or ``""``.

        The top of the ranked set — see ``_correct`` for why that is the whole
        instrument, and what makes being wrong about it recoverable.
        """
        ids = ranked.ids if ranked is not None else ()
        return ids[0] if ids else ""

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
        mistakable for an empty ledger — but a main whose retrieval is off is
        usually a main in aftercare, and they must still get an answer. A
        disable degrades what Half knows, never whether Half replies.

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


def question_line(context: Context | None) -> str:
    """The one line a bought question contributes to a reply, or ``""``.

    **The single serialization**, shared with ``Context.render`` rather than
    written out beside it: two renderings of one item is how the guard that
    scans one string ends up admitting a different one, which is the argument
    ``half.context.channels.render_line`` already carries.

    The empty string is the answer to *"was a question actually built?"*, and it
    is the same answer for both ways one can fail to be: a bought belief the
    ladder put above `ask`, and one whose only topic echoes its own claim. The
    caller spends a favour exactly when this is non-empty, so *"no question line,
    no spend"* is one comparison rather than a flag somebody has to keep true.
    """
    if not isinstance(context, Context) or context.question is None:
        return ""
    return render_line(context.question)


def respond(
    inbound: Inbound,
    ranked: Ranked | None = None,
    *,
    ceiling: Ceiling | None,
) -> str | None:
    """Build the turn's context and reply from what its licenses permit.

    Still deterministic and still model-free — AD-19's port is unbuilt, so
    nothing here composes prose. What changed from story 4 is the boundary: the
    ranked set is no longer uniformly unsayable. It is split by license
    (AD-18), and the content channel is the one rung Half has the standing to
    state, so its text may reach the main.

    ``now`` is the inbound stamp the adapter read. Nothing below this line
    touches a clock, so one conversation replays to one set of replies.

    Three properties this shape holds that a filter could not:

    * `behave` and `ask` claim text is absent from the reply because it is
      absent from the context — there is no branch here that could re-admit it.
    * The reply still does not echo the main's own words. The belief carrying
      them is recorded after this returns, and it is recorded `behave`.
    * A context with no content still produces a reply. Empty is an ordinary
      outcome — an empty ledger, or retrieval disabled by a crisis — and is
      never phrased as missing access (AD-24, AD-27).

    ``ceiling`` is this main's global cap and is applied inside the context
    build, where licenses are resolved. Nothing here inspects it or subtracts
    anything afterwards: a capped belief simply never reaches the quotable
    channel (AD-28).
    """
    if not inbound.text.strip():
        return None
    quotable = build_context(ranked, now=inbound.t, ceiling=ceiling).quotable()
    if not quotable:
        return "noted."
    return f"noted. {quotable[0]}"
