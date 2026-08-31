"""Actor registry: serialization, hydration, eviction safety (AD-8, AD-33)."""

from __future__ import annotations

import asyncio

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime, respond
from half.channel.telegram import TelegramChannel
from half.store.ops import Op
from tests.test_channel import FakeTransport, msg


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path / "mains", capacity=2)
    yield reg
    reg.close()


# -- one writer per main -----------------------------------------------------

def test_concurrent_turns_for_one_main_serialize(registry):
    order: list[str] = []

    async def turn(tag: str) -> None:
        async with registry.acquire("vidit"):
            order.append(f"enter-{tag}")
            await asyncio.sleep(0.01)
            order.append(f"exit-{tag}")

    asyncio.run(_gather(turn("a"), turn("b")))
    assert order == ["enter-a", "exit-a", "enter-b", "exit-b"]


def test_different_mains_do_not_block_each_other(registry):
    order: list[str] = []

    async def turn(main_id: str) -> None:
        async with registry.acquire(main_id):
            order.append(f"enter-{main_id}")
            await asyncio.sleep(0.01)
            order.append(f"exit-{main_id}")

    asyncio.run(_gather(turn("a"), turn("b")))
    assert order[:2] == ["enter-a", "enter-b"]  # interleaved, not serialized


def test_appends_from_concurrent_turns_land_in_log_order(registry):
    async def turn(index: int) -> None:
        async with registry.acquire("vidit") as actor:
            actor.store.record(
                Op.ASSERT, f"b_{index}", f"2026-08-0{index+1}T00:00:00Z",
                subject="self", claim=f"message {index}",
            )

    asyncio.run(_gather(*(turn(i) for i in range(3))))
    async def read():
        async with registry.acquire("vidit") as actor:
            return sorted(actor.store.state().beliefs)
    assert asyncio.run(read()) == ["b_0", "b_1", "b_2"]


# -- hydration and eviction --------------------------------------------------

def test_an_actor_is_hydrated_on_first_use(registry):
    assert not registry.is_hydrated("vidit")
    asyncio.run(_touch(registry, "vidit"))
    assert registry.is_hydrated("vidit")


def test_the_least_recently_used_actor_is_evicted_past_capacity(registry):
    for main_id in ("a", "b", "c"):
        asyncio.run(_touch(registry, main_id))
    assert registry.hydrated == ["b", "c"]


def test_an_evicted_main_is_rehydrated_with_its_state_intact(registry):
    async def write():
        async with registry.acquire("a") as actor:
            actor.store.record(Op.ASSERT, "b_1", "2026-08-01T00:00:00Z",
                               subject="self", claim="remembered")
    asyncio.run(write())
    for main_id in ("b", "c"):
        asyncio.run(_touch(registry, main_id))
    assert not registry.is_hydrated("a")

    async def read():
        async with registry.acquire("a") as actor:
            return [b["claim"] for b in actor.store.rebuild().beliefs.values()]
    assert asyncio.run(read()) == ["remembered"]


def test_a_busy_actor_is_never_evicted(registry):
    """AD-33: eviction requires a free mutex. Dropping an actor mid-turn loses
    an in-flight reply, or work already paid for."""
    seen: list[bool] = []

    async def scenario() -> None:
        async def hold() -> None:
            async with registry.acquire("busy"):
                await asyncio.sleep(0.05)
                seen.append(registry.is_hydrated("busy"))

        async def pressure() -> None:
            await asyncio.sleep(0.01)
            for main_id in ("x", "y", "z"):
                async with registry.acquire(main_id):
                    pass

        await asyncio.gather(hold(), pressure())

    asyncio.run(scenario())
    assert seen == [True]


# -- the wired runtime -------------------------------------------------------

def test_the_runtime_never_imports_the_network_transport(tmp_path):
    """The adapter holds every rule and is exercised offline; the transport is
    the thin network edge. Nothing in the wiring should reach it directly."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "half/actor/runtime.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    reached = {
        n.module for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module
    }
    assert not any("transport" in (m or "") for m in reached)


def test_an_inbound_message_is_stored_and_answered(tmp_path):
    transport = FakeTransport([msg(text="i want to fly again")])
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    asyncio.run(Runtime(channel=channel, registry=reg).run())

    assert transport.sent == [("123", "noted: i want to fly again")]

    async def read():
        async with reg.acquire("vidit") as actor:
            return [b["claim"] for b in actor.store.state().beliefs.values()]
    assert asyncio.run(read()) == ["i want to fly again"]
    reg.close()


def test_silence_sends_nothing_and_is_not_an_error(tmp_path):
    """AD-27: staying silent is an outcome, not a failure."""
    transport = FakeTransport([msg(text="   ")])
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    asyncio.run(Runtime(channel=channel, registry=reg).run())
    assert transport.sent == []
    assert respond(_inbound("   ")) is None
    reg.close()


def _inbound(text: str):
    from half.channel.port import Inbound
    return Inbound(main_id="vidit", address="123", text=text,
                   external_id="1", t="2026-08-01T00:00:00Z")


async def _touch(registry: ActorRegistry, main_id: str) -> None:
    async with registry.acquire(main_id):
        pass


async def _gather(*coros) -> None:
    await asyncio.gather(*coros)
