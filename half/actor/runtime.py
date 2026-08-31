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
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from half.actor.registry import Actor, ActorRegistry
from half.channel.port import Channel, Inbound
from half.context.build import build as build_context
from half.crisis.gate import CrisisGate
from half.errors import HalfError, NotReachable, RetrievalDisabled, SendFailed
from half.retrieval.port import Ranked, Reranker
from half.retrieval.rank import Retriever
from half.retrieval.strands import known_strands
from half.store.ops import Op

logger = logging.getLogger(__name__)

#: Backoff between retries of a retryable send, in seconds.
RETRY_DELAYS = (1.0, 4.0, 15.0)


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
    _gate: CrisisGate = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # An injected gate owns its own wiring; the default one is handed the
        # registry's per-main resolver, so the switch crisis turns off is the
        # one that main's own retriever reads — and no one else's.
        self._gate = self.gate or CrisisGate(
            pipeline=self._pipeline, retrieval=self.registry.retrieval_switch
        )

    async def run(self) -> None:
        """Consume inbound messages until cancelled.

        Nothing a single message does can end this loop.
        """
        async for inbound in self.channel.receive():
            try:
                await self._handle(inbound)
            except asyncio.CancelledError:
                raise  # shutdown is not a message failure
            except Exception:
                # Content is never logged — it is the most intimate data the
                # product holds (AD-22).
                logger.exception(
                    "turn failed for main=%s message=%s; continuing",
                    inbound.main_id,
                    inbound.external_id,
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
        """
        belief_id = f"b_{inbound.external_id}"
        async with self.registry.acquire(inbound.main_id) as actor:
            if belief_id in actor.store.state().beliefs:
                return None  # already handled; a redelivery, not a new message

            reply = respond(inbound, self._retrieve(actor, inbound))

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
                ledger="stated",
                license="behave",
            )
            return reply

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
        """
        state = actor.store.state()
        actor.strands.observe(
            inbound.text, known_strands(state.beliefs.values(), state.loops)
        )
        retriever = Retriever(
            store=actor.store, reranker=self.reranker, switch=actor.retrieval
        )
        try:
            return retriever.retrieve(inbound.text, now=inbound.t,
                                      strands=actor.strands)
        except RetrievalDisabled:
            # No content, and not even an exception message (AD-22).
            logger.info("retrieval disabled for main=%s; replying without the "
                        "ledger", inbound.main_id)
            return Ranked()


def respond(inbound: Inbound, ranked: Ranked | None = None) -> str | None:
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
    """
    if not inbound.text.strip():
        return None
    quotable = build_context(ranked, now=inbound.t).quotable()
    if not quotable:
        return "noted."
    return f"noted. {quotable[0]}"
