"""Actor registry: serialization, hydration, eviction safety (AD-8, AD-33)."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime, respond
from half.channel.telegram import TelegramChannel
from half.crisis.gate import CrisisGate
from half.errors import StoreError
from half.store.ops import Op
from tests.conftest import FakeTransport, msg


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

    # The reply carries no belief text — not even the main's own words back,
    # which are now a stored claim. Licenses are enforced at context
    # construction (AD-18) and that construction is story 5.
    assert transport.sent == [("123", "noted.")]

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


# ── review findings: the AD-1 eviction window ───────────────────────────────

def test_an_actor_with_a_queued_turn_is_not_evicted_under_pressure(tmp_path):
    """AD-1. ``asyncio.Lock.release()`` clears its flag and only *schedules*
    the next waiter, so ``lock.locked()`` alone reports an actor with a queued
    turn as idle. Evicting there closes the store under a turn about to run,
    and the next acquire hydrates a second Actor with a second lock for the
    same main — two writers on one belief log.
    """
    reg = ActorRegistry(tmp_path / "mains", capacity=1)
    b_in, b_out, a_in, a_out = (asyncio.Event() for _ in range(4))
    observed: dict[str, bool] = {}

    async def scenario() -> None:
        async def hold_b() -> None:
            async with reg.acquire("b"):
                b_in.set()
                await b_out.wait()

        async def hold_a() -> None:
            async with reg.acquire("a") as actor:
                actor.store.conn  # force the connection open
                a_in.set()
                await a_out.wait()

        async def queued() -> None:
            async with reg.acquire("a") as actor:
                observed["store_open"] = actor.store._conn is not None

        tb = asyncio.create_task(hold_b())
        await b_in.wait()
        ta = asyncio.create_task(hold_a())
        await a_in.wait()

        tq = asyncio.create_task(queued())
        for _ in range(3):
            await asyncio.sleep(0)  # park the waiter on a's lock

        a_out.set()
        await ta          # release -> eviction considered in this window
        await tq
        b_out.set()
        await tb

    asyncio.run(scenario())
    assert observed["store_open"], "a queued turn resumed on a closed store"


def test_a_failing_turn_still_lets_the_registry_evict(tmp_path):
    """Eviction lives in a finally. Sitting after the ``async with`` meant a
    raising turn skipped it and the registry grew past capacity forever."""
    reg = ActorRegistry(tmp_path / "mains", capacity=1)

    async def scenario() -> None:
        for main_id in ("a", "b", "c"):
            with contextlib.suppress(RuntimeError):
                async with reg.acquire(main_id):
                    raise RuntimeError("turn failed")

    asyncio.run(scenario())
    assert len(reg.hydrated) <= 1


def test_capacity_must_be_at_least_one(tmp_path):
    with pytest.raises(ValueError):
        ActorRegistry(tmp_path / "mains", capacity=0)


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", ".", "..", "with space", "x" * 65])
def test_an_unsafe_main_id_never_reaches_the_filesystem(tmp_path, bad):
    """main_id becomes a directory name and arrives from configuration."""
    reg = ActorRegistry(tmp_path / "mains")

    async def attempt() -> None:
        async with reg.acquire(bad):
            pass

    with pytest.raises(StoreError):
        asyncio.run(attempt())


def test_close_refuses_while_a_turn_is_running(tmp_path):
    reg = ActorRegistry(tmp_path / "mains")
    entered, release = asyncio.Event(), asyncio.Event()
    failed: list[bool] = []

    async def scenario() -> None:
        async def hold() -> None:
            async with reg.acquire("a"):
                entered.set()
                await release.wait()

        task = asyncio.create_task(hold())
        await entered.wait()
        try:
            reg.close()
            failed.append(False)
        except RuntimeError:
            failed.append(True)
        release.set()
        await task

    asyncio.run(scenario())
    assert failed == [True]


# ── review findings: isolation, retry, idempotency ─────────────────────────

def test_one_failed_send_does_not_stop_the_loop_for_anyone(tmp_path):
    """An uncaught SendFailed used to propagate out of run() and end polling
    for every main — Half stayed up and silently stopped receiving."""
    transport = FakeTransport(
        [msg(text="first", message_id="1"), msg(text="second", message_id="2")],
        fail=RuntimeError("Bad Request: chat not found"),
        fail_times=1,
    )
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    asyncio.run(Runtime(channel=channel, registry=reg).run())

    assert transport.sent == [("123", "noted.")]

    async def read():
        async with reg.acquire("vidit") as actor:
            return sorted(actor.store.state().beliefs)
    assert asyncio.run(read()) == ["b_1", "b_2"]  # both stored
    reg.close()


def test_a_retryable_send_is_retried_and_succeeds(tmp_path, monkeypatch):
    """SendFailed.retryable previously had no reader anywhere."""
    monkeypatch.setattr("half.actor.runtime.RETRY_DELAYS", (0.0, 0.0, 0.0))
    transport = FakeTransport(
        [msg(text="hello")], fail=TimeoutError("timed out"), fail_times=2
    )
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    asyncio.run(Runtime(channel=channel, registry=reg).run())
    assert transport.sent == [("123", "noted.")]
    assert transport.attempts == 3
    reg.close()


def test_a_permanent_send_failure_is_not_retried(tmp_path):
    transport = FakeTransport(
        [msg(text="hello")], fail=RuntimeError("Forbidden: bot was blocked")
    )
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    asyncio.run(Runtime(channel=channel, registry=reg).run())
    assert transport.attempts == 1
    reg.close()


def test_a_redelivered_message_is_not_recorded_twice(tmp_path):
    """At-least-once delivery makes redelivery routine, so the turn is
    idempotent."""
    same = msg(text="i want to fly again", message_id="42")
    transport = FakeTransport([same, dict(same)])
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    asyncio.run(Runtime(channel=channel, registry=reg).run())

    async def read():
        async with reg.acquire("vidit") as actor:
            return list(actor.store.state().beliefs)
    assert asyncio.run(read()) == ["b_42"]
    assert len(transport.sent) == 1  # the duplicate produced no second reply
    reg.close()


def test_a_raising_turn_does_not_end_the_loop(tmp_path):
    """Any handler error is isolated to its message."""
    class Exploding(CrisisGate):
        def __init__(self):
            self.calls = 0
            super().__init__(pipeline=self._boom)

        async def _boom(self, inbound):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("handler blew up")
            return "recovered"

    transport = FakeTransport([msg(message_id="1"), msg(message_id="2")])
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    asyncio.run(Runtime(channel=channel, registry=reg, gate=Exploding()).run())
    assert transport.sent == [("123", "recovered")]
    reg.close()


def test_the_crisis_branch_is_reachable_from_a_test(tmp_path):
    """The gate was constructed inside run(), so no test could supply one that
    reports a crisis — the whole branch was unreachable."""
    class AlwaysCrisis(CrisisGate):
        def _is_crisis(self, inbound):
            return True

        async def _respond_to_crisis(self, inbound):
            return "I'm software. You need a person."

    transport = FakeTransport([msg(text="anything")])
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    reg = ActorRegistry(tmp_path / "mains")
    gate = AlwaysCrisis(pipeline=_never)
    asyncio.run(Runtime(channel=channel, registry=reg, gate=gate).run())
    assert transport.sent == [("123", "I'm software. You need a person.")]
    reg.close()


async def _never(inbound):  # pragma: no cover - must not be reached
    raise AssertionError("the crisis branch must not reach the pipeline")
