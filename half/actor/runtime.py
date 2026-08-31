"""Wiring: channel -> crisis gate -> actor -> store (AD-17).

Two policies here were human decisions, not defaults:

**Per-message isolation.** No single message's failure ends the inbound loop.
An uncaught error used to propagate out of ``run()`` and stop polling for
*every* main — Half stayed up and silently stopped receiving.

**At-least-once delivery.** The transport commits its position only after a
turn completes, so a crash redelivers rather than loses. That makes redelivery
routine, so the turn is idempotent: a message already recorded is not recorded
twice.

The responder is a deterministic stub — no model is called anywhere in this
story, which keeps the suite hermetic. Later stories replace ``respond``
without touching the channel or the registry.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from half.actor.registry import ActorRegistry
from half.channel.port import Channel, Inbound
from half.crisis.gate import CrisisGate
from half.errors import HalfError, NotReachable, SendFailed
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
    _gate: CrisisGate = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._gate = self.gate or CrisisGate(pipeline=self._pipeline)

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
            actor.store.record(
                Op.ASSERT,
                belief_id,
                inbound.t,
                subject="self",
                claim=inbound.text,
                ledger="stated",
                license="behave",
            )
            return respond(inbound)


def respond(inbound: Inbound) -> str | None:
    """Deterministic placeholder. Story 4 brings retrieval, story 5 governance."""
    if not inbound.text.strip():
        return None
    return f"noted: {inbound.text.strip()}"
