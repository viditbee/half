"""Wiring: channel -> crisis gate -> actor -> store (AD-17).

The inbound path in one place, so the ordering the spine fixes is legible:
adapter receives, the crisis gate takes the message first, and only then does
an actor hold its mutex and touch a store.

**The responder is a deterministic stub.** No model is called anywhere in this
story, which keeps the suite hermetic and offline; later stories replace
``respond`` without touching the channel or the registry.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from half.actor.registry import ActorRegistry
from half.channel.port import Channel, Inbound, Reachability
from half.crisis.gate import CrisisGate
from half.errors import NotReachable
from half.store.ops import Op


@dataclass(slots=True)
class Runtime:
    channel: Channel
    registry: ActorRegistry

    async def run(self) -> None:
        """Consume inbound messages until cancelled."""
        gate = CrisisGate(pipeline=self._pipeline)
        async for inbound in self.channel.receive():
            await self._handle(gate, inbound)

    async def _handle(self, gate: CrisisGate, inbound: Inbound) -> None:
        reply = await gate.handle(inbound)
        if reply is None:
            return  # silence is an outcome, not a failure (AD-27)
        try:
            await self.channel.send(inbound.main_id, reply)
        except NotReachable:
            # The main is unreachable right now. Nothing is lost: the exchange
            # is already in the log, and a later story decides whether to
            # queue, template or stay quiet.
            return

    async def _pipeline(self, inbound: Inbound) -> str | None:
        """The ordinary turn. Exactly one caller: the crisis gate (AD-10)."""
        async with self.registry.acquire(inbound.main_id) as actor:
            actor.store.record(
                Op.ASSERT,
                f"b_{inbound.external_id}",
                inbound.t,
                subject="self",
                claim=inbound.text,
                ledger="stated",
                license="behave",
            )
            return respond(inbound)


def respond(inbound: Inbound) -> str | None:
    """Deterministic placeholder. Story 5 replaces this with real governance
    and story 4 with real retrieval."""
    if not inbound.text.strip():
        return None
    return f"noted: {inbound.text.strip()}"
