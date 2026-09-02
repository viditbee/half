"""Story 9a — the due-time scheduler (AD-1, AD-9, AD-26, AD-27, AD-30).

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test and handed to a ``FrozenClock``, which is the
whole point of the design under test: the scheduler is the one module allowed
to know what time it is, and it takes that knowledge from an injected ``Clock``
so that everything beneath it — and every case below — is a pure function of an
instant somebody supplied. A suite that used the real clock would pass tonight
and fail at 03:30 tomorrow.

**The recurring loop is run, not read.** Review round 1 found that ``tick()``
was exercised everywhere and ``run_forever`` nowhere, so three mutations passed
2002 tests: ticking once at boot, dying on the first transient error, and — the
one that matters — a startup ``_catch_up()`` draining every missed main, which
is catch-up added by the door the guard was not watching. The missed-window rule
is now asserted on *both* paths, and ``serve`` is exercised rather than grepped.

Four markers, four gates, because a floor on a superset cannot protect a subset
and this codebase has learned that three stories running:

* ``ad9`` — the whole due-time queue.
* ``ad9_guarantee`` — the promises inside it: a missed window sends nothing on
  every path, the lock, the bound, per-main isolation, the durable write that
  stops a pass, and the window across the whole timezone database.
* ``one_clock`` — the structural half, with its non-vacuity cases.
* ``one_clock_guarantee`` — the sentences that half exists to make true:
  exactly one module reads a clock in any spelling, no signal is consulted to
  guess a zone, the host's own timezone changes nothing, an untrusted stamp is
  clamped into the range the store accepts, and everything the tick calls takes
  an injected ``now``.
"""

from __future__ import annotations

import ast
import asyncio
import os
import subprocess
import sys
import time as _real_time
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.civil import MAX_YEAR, MIN_YEAR, instant
from half.errors import ScheduleError
from half.governance.ladder import License
from half.schedule import due
from half.schedule.clock import (
    MAX_EPOCH,
    MIN_EPOCH,
    FrozenClock,
    Now,
    SystemClock,
    clamp,
    moment,
    stamp,
)
from half.schedule.tick import (
    DEFAULT_BOUND,
    DEFAULT_TIMEOUT,
    GRACE_SECONDS,
    LOCK_NAME,
    Nothing,
    Scheduler,
    TICK_SECONDS,
    _is_contention,
)
from half.store.ops import SCHEMA_VERSION, Op
from half.store.records import NEXT_PASS_AT, TOLD_ZONE, ZONE, zone_projection
from half.store.store import Store

from tests.conftest import seed_belief

ROOT = Path(__file__).resolve().parents[1]

#: A fixed instant every case builds from: 2026-09-01T12:00:00Z, the middle of
#: a UTC afternoon, so "the next pre-dawn" is unambiguously tomorrow.
NOON = 1_788_264_000.0

pytestmark = pytest.mark.ad9


# ── helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def scheduler(registry, root, mains, *, at=NOON, **kwargs):
    return Scheduler(
        registry=registry,
        mains=tuple(mains),
        root=Path(root),
        clock=FrozenClock(at=at),
        **kwargs,
    )


def tell_zone(root, main_id, zone, *, rung=License.ASSERT):
    """Record that the main told Half where they are.

    Through ``seed_belief``, so a zone takes the same admission path as any
    other claim about the main: born at the weakest rung and *promoted* by an
    event the main was part of. ``rung=BEHAVE`` seeds the unconfirmed case —
    something Half wrote down and nobody confirmed.
    """
    with Store(Path(root) / main_id) as store:
        seed_belief(
            store, f"b_zone_{main_id}", "2026-08-01T09:00Z",
            rung=rung, support=["s_1"], zone=zone,
        )


def set_due(registry, main_id, at):
    """Put ``main_id``'s next due time at the epoch ``at``."""
    asyncio.run(
        registry.note_pass(
            main_id,
            t=stamp(at - 10),
            fields={NEXT_PASS_AT: stamp(at), ZONE: "UTC", TOLD_ZONE: False},
        )
    )


class Recorder:
    """A pass that records who it ran for, and how many ran at once."""

    def __init__(self, *, delay=0.0, raises=None, hangs=()):
        self.ran: list[str] = []
        self.instants: list[Now] = []
        self.depth = 0
        self.peak = 0
        self.delay = delay
        self.raises = raises
        self.hangs = set(hangs)

    async def run(self, main_id, now):
        self.depth += 1
        self.peak = max(self.peak, self.depth)
        try:
            if main_id in self.hangs:
                await asyncio.sleep(3600)
            if self.raises is not None and main_id == self.raises:
                raise RuntimeError("this main's pass exploded")
            if self.delay:
                await asyncio.sleep(self.delay)
            self.ran.append(main_id)
            self.instants.append(now)
        finally:
            self.depth -= 1


class Counting(Scheduler):
    """A ``Scheduler`` whose recurring loop can be *run* and then stopped.

    The whole point of review round 1's first finding: ``run_forever`` was
    verified by nobody. This drives the real loop — the real ``while``, the real
    error handling, the real sleep — and stops it by cancelling from inside
    after a chosen number of attempts, so a loop that ticks once, or dies on the
    first error, fails rather than passes.
    """

    def __init__(self, *args, stop_after=3, fail_first=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.results: list = []
        self.attempts = 0
        self.stop_after = stop_after
        self.fail_first = fail_first

    async def tick(self):
        self.attempts += 1
        if self.attempts <= self.fail_first:
            raise RuntimeError("a transient store error")
        try:
            result = await super().tick()
        finally:
            if self.attempts >= self.stop_after:
                raise asyncio.CancelledError
        self.results.append(result)
        return result


def run_loop(sch, *, interval=0.0):
    """Drive ``sch.run_forever`` until it cancels itself. Returns the ticks."""
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sch.run_forever(interval=interval))
    return sch.results


# ── matrix: nothing due ──────────────────────────────────────────────────────


def test_a_tick_with_nothing_due_runs_nothing_and_is_not_an_error(registry, tmp_path):
    """Matrix: *nothing due*. Silent and normal (AD-27).

    A tick that finds nobody due is the ordinary state of a worker for
    twenty-three hours out of twenty-four. It returns a result rather than
    raising, and it emits nothing.
    """
    set_due(registry, "vidit", NOON + 10_000)
    work = Recorder()
    result = asyncio.run(scheduler(registry, tmp_path, ["vidit"], work=work).tick())
    assert work.ran == []
    assert result.ran == () and result.missed == () and result.scheduled == ()
    assert result.held is False
    assert result.quiet is True


def test_a_main_who_has_never_been_scheduled_is_given_a_time_and_not_run(
    registry, tmp_path
):
    """A new main, a restored tree, and a due time this build cannot read all
    land on the same branch: record one, run nothing.

    The tempting implementation runs them immediately, which on the first boot
    after a deploy would run a pass for every main at once — a herd produced by
    the absence of state rather than by a cron.
    """
    work = Recorder()
    result = asyncio.run(scheduler(registry, tmp_path, ["vidit"], work=work).tick())
    assert work.ran == []
    assert result.scheduled == ("vidit",)
    assert instant(registry.schedule_record("vidit")[NEXT_PASS_AT]) > NOON


# ── matrix: one due ──────────────────────────────────────────────────────────


def test_a_main_past_their_due_time_runs_once(registry, tmp_path):
    """Matrix: *one due*. That main's work runs once."""
    set_due(registry, "vidit", NOON - 60)
    work = Recorder()
    result = asyncio.run(scheduler(registry, tmp_path, ["vidit"], work=work).tick())
    assert work.ran == ["vidit"]
    assert result.ran == ("vidit",)


def test_a_main_who_ran_is_not_due_again_on_the_next_tick(registry, tmp_path):
    """The advance is what makes it *once* rather than *every tick until dawn*."""
    set_due(registry, "vidit", NOON - 60)
    work = Recorder()
    sch = scheduler(registry, tmp_path, ["vidit"], work=work)
    asyncio.run(sch.tick())
    asyncio.run(sch.tick())
    asyncio.run(sch.tick())
    assert work.ran == ["vidit"]


def test_the_pass_receives_the_ticks_own_instant(registry, tmp_path):
    """AD-30 at the seam that matters: the pass is *given* now, never told to
    find out. Every main in one tick is judged against the same instant."""
    for main_id in ("vidit", "asha"):
        set_due(registry, main_id, NOON - 60)
    work = Recorder()
    asyncio.run(scheduler(registry, tmp_path, ["vidit", "asha"], work=work).tick())
    assert {n.epoch for n in work.instants} == {NOON}
    assert {n.stamp for n in work.instants} == {"2026-09-01T12:00:00Z"}


# ── matrix: many due ─────────────────────────────────────────────────────────


@pytest.mark.ad9_guarantee
def test_more_due_mains_than_the_bound_run_bounded_and_all_run(registry, tmp_path):
    """Matrix: *many due*. Bounded concurrency; all eventually run.

    A thousand due mains must not become a thousand concurrent passes. The
    delay is what makes the bound observable: without it every task would
    complete before the next started and a broken bound would look identical
    to a working one.
    """
    mains = [f"main{i}" for i in range(12)]
    for main_id in mains:
        set_due(registry, main_id, NOON - 60)
    work = Recorder(delay=0.01)
    result = asyncio.run(
        scheduler(registry, tmp_path, mains, work=work, bound=3).tick()
    )
    assert sorted(work.ran) == sorted(mains)
    assert sorted(result.ran) == sorted(mains)
    assert work.peak <= 3


@pytest.mark.ad9_guarantee
def test_the_shipped_bound_is_the_one_the_drain_applies(registry, tmp_path):
    """**The shipped number, not an injected one.**

    Every bounded-concurrency case above passes its own ``bound``, so
    ``DEFAULT_BOUND = 10_000`` was green across 2002 tests. This runs more due
    mains than the default with no bound supplied, and watches the peak.
    """
    assert DEFAULT_BOUND <= 32, "the shipped bound is now too large to drive here"
    mains = [f"main{i}" for i in range(DEFAULT_BOUND + 6)]
    for main_id in mains:
        set_due(registry, main_id, NOON - 60)
    work = Recorder(delay=0.01)
    asyncio.run(scheduler(registry, tmp_path, mains, work=work).tick())
    assert sorted(work.ran) == sorted(mains)
    assert work.peak <= DEFAULT_BOUND


def test_the_concurrency_bound_is_explicit_and_refuses_a_nonsense_value(
    registry, tmp_path
):
    """*"Concurrency is bounded and the bound is explicit."* A bound of zero
    would drain nothing for ever while every tick reported success, and a grace
    window of zero is a queue in which nothing is ever on time."""
    with pytest.raises(ValueError):
        scheduler(registry, tmp_path, ["vidit"], bound=0)
    with pytest.raises(ValueError):
        scheduler(registry, tmp_path, ["vidit"], timeout=0)
    with pytest.raises(ValueError):
        scheduler(registry, tmp_path, ["vidit"], grace=0)
    with pytest.raises(ValueError):
        scheduler(registry, tmp_path, ["vidit"], grace=-1)


@pytest.mark.ad9_guarantee
def test_the_shipped_constants_are_pinned_to_their_values():
    """Matrix: *shipped constants*.

    Every behavioural case injects its own bound, timeout and grace, and the
    grace cases express due times in terms of the constant — so
    ``GRACE_SECONDS`` at four days, ``DEFAULT_BOUND`` at ten thousand and
    ``DEFAULT_TIMEOUT`` at 1e9 were all green. Pinned absolutely, so changing
    one is a deliberate edit here as well as there.

    Each number is also *related* to the others, and the relations matter more
    than the values:

    * the tick interval must be well inside the grace window, or a due time
      falling between two ticks reads as missed;
    * one main's timeout must be well inside the grace window, or a single hung
      pass pushes the tick past the point where everybody else is missed;
    * the jitter window must equal the promised window, or a due time lands
      outside the promise.
    """
    assert (due.PRE_DAWN_HOUR, due.WINDOW_HOURS) == (3, 2)
    assert due.JITTER_SECONDS == due.WINDOW_HOURS * 3600
    assert due.FALLBACK_ZONE == "UTC"
    assert (DEFAULT_BOUND, DEFAULT_TIMEOUT) == (8, 300.0)
    assert (GRACE_SECONDS, TICK_SECONDS) == (3600.0, 60.0)
    assert TICK_SECONDS * 10 <= GRACE_SECONDS
    assert DEFAULT_TIMEOUT * 4 <= GRACE_SECONDS


@pytest.mark.ad9_guarantee
def test_a_full_drain_cannot_outrun_the_grace_window_for_a_worker_s_mains():
    """The relation nothing asserted: worst-case tick duration is
    ``ceil(n / bound) x timeout``, and a tick longer than the grace window
    silently classifies as *missed* everybody who became due while it ran —
    while looking perfectly healthy.

    At the shipped numbers a worker may host ninety-six mains before that
    becomes possible. This is the number an operator has to size shards by, so
    it is written down and checked rather than left to be discovered.
    """
    import math

    worst = lambda n: math.ceil(n / DEFAULT_BOUND) * DEFAULT_TIMEOUT  # noqa: E731
    assert worst(DEFAULT_BOUND) <= GRACE_SECONDS
    safe = max(n for n in range(1, 5000) if worst(n) <= GRACE_SECONDS)
    assert safe == 96, (
        f"the shipped numbers now allow {safe} mains per worker before a full "
        f"drain can exceed the grace window; the operator note must move too"
    )


# ── matrix: same timezone, and every zone ────────────────────────────────────


def test_many_mains_in_one_timezone_do_not_share_an_instant(registry, tmp_path):
    """Matrix: *same timezone*. Due times spread by jitter, never one instant.

    Timezone spread does not save a user base that shares one timezone, so the
    spread has to be built. Two hundred mains in Asia/Kolkata, and the test
    asserts both halves: they are spread, and every one of them still lands
    inside the pre-dawn window rather than being spread across the day.
    """
    mains = [f"m{i:03d}" for i in range(200)]
    times = {
        due.next_pass_at(main_id=m, after=NOON, zone="Asia/Kolkata").at
        for m in mains
    }
    assert len(times) > 150, "due times collapsed onto shared instants"
    span = max(times) - min(times)
    assert span <= due.JITTER_SECONDS


def test_jitter_is_derived_from_the_main_and_never_drawn(registry, tmp_path):
    """A restart must not move a main's due time.

    ``random`` would spread beautifully and lose the spread on every boot, so
    the offset is a hash: identical in this process, in the next one, and in a
    second worker. Asserted against a subprocess with a *different*
    ``PYTHONHASHSEED``, because ``hash()`` is the version of this that looks
    right and is randomised per process.
    """
    first = due.jitter("vidit")
    assert first == due.jitter("vidit")
    assert 0 <= first < due.JITTER_SECONDS

    env = dict(os.environ, PYTHONHASHSEED="12345", PYTHONPATH=str(ROOT))
    out = subprocess.run(
        [sys.executable, "-c",
         "from half.schedule.due import jitter; print(jitter('vidit'))"],
        capture_output=True, text=True, env=env, check=True,
    )
    assert int(out.stdout.strip()) == first


@pytest.mark.ad9_guarantee
def test_every_zone_in_the_database_lands_inside_the_window_across_a_year():
    """Matrix: *every zone*. One zone's transition does not stand for every
    zone's — and review round 1 proved it by sweeping.

    The previous version of this walked ``America/New_York``, which springs
    forward at **02:00**, so local 03:00 exists on the transition day and the
    defect was structurally invisible to it. EET moves **03:00 → 04:00**: local
    03:00 does not exist, resolving it lands on 04:00, and nearly two hours of
    jitter carried eighteen zones to **05:57 local** — in the hour people wake
    up, which is the one thing the window exists to avoid. Chatham did the same
    in September, at 02:45.

    So the sweep is the test: every zone the build holds, a year and a bit of
    consecutive due times each, checked against the promise itself.

    **And checked for a skipped day, which is the other way to keep the
    promise and lose the product.** ``next_pass_at`` verifies its own answer and
    walks to the next day when a candidate falls outside the window, so a
    version that jitters wrongly stays *inside* the window by simply not
    scheduling anybody on a transition day — a silent missed night, in eighteen
    zones, twice a year. Consecutive due times are therefore bounded on both
    sides: 22 hours at the tightest (a two-hour spring jump) and 26 at the
    widest (the autumn one), which is one pre-dawn per local day and no more.
    """
    import zoneinfo

    zones = sorted(zoneinfo.available_timezones())
    assert len(zones) > 300, "the tz database looks empty; the sweep proves nothing"
    outside: list[str] = []
    skipped: list[str] = []
    for zone in zones:
        at = due.next_pass_at(
            main_id="vidit", after=1_767_268_800.0, zone=zone  # 2026-01-01T12:00Z
        ).at
        for _ in range(400):
            nxt = due.next_pass_at(main_id="vidit", after=at, zone=zone).at
            if not due.in_window(nxt, zone):
                outside.append(f"{zone} @ {stamp(nxt)}")
                break
            if not 22 * 3600 <= nxt - at <= 26 * 3600:
                skipped.append(f"{zone} @ {stamp(at)} -> {stamp(nxt)}")
                break
            at = nxt
    assert not outside, f"due times outside the promised window: {outside[:8]}"
    assert not skipped, f"a local day had no pre-dawn pass at all: {skipped[:8]}"


@pytest.mark.ad9_guarantee
def test_the_window_sweep_catches_a_jitter_that_ignores_the_transition(
    monkeypatch
):
    """Non-vacuity for the sweep: the *previous* implementation, reinstated.

    ``opens + offset`` assumes the window is two real hours long. On an EET
    transition day it is one, and this is the case that says so — without it,
    the sweep is only as good as the belief that it would have caught something.
    """
    import datetime as dt
    from zoneinfo import ZoneInfo

    zone = "Europe/Athens"
    tz = ZoneInfo(zone)
    day = dt.date(2026, 3, 29)
    opens = int(dt.datetime(day.year, day.month, day.day, 3, tzinfo=tz).timestamp())
    naive = opens + due.jitter("vidit")
    assert not due.in_window(naive, zone), (
        "Europe/Athens no longer demonstrates the defect; pick a zone that "
        "still transitions at 03:00 or this gate has stopped asserting"
    )
    assert due.in_window(
        due.next_pass_at(main_id="vidit", after=opens - 3600, zone=zone).at, zone
    )


def test_a_due_time_lands_in_the_pre_dawn_window_of_the_told_zone():
    """The window is local, and *local* means the main's zone rather than the
    host's. Checked as civil hours in the zone itself."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    for zone in ("Asia/Kolkata", "America/Sao_Paulo", "Pacific/Auckland", "UTC"):
        at = due.next_pass_at(main_id="vidit", after=NOON, zone=zone).at
        local = dt.datetime.fromtimestamp(at, ZoneInfo(zone))
        assert due.PRE_DAWN_HOUR <= local.hour < due.PRE_DAWN_HOUR + due.WINDOW_HOURS


def test_consecutive_due_times_advance_and_never_repeat():
    """A due time that did not move is a main who runs on every tick until the
    grace window closes."""
    at = NOON
    for _ in range(400):
        nxt = due.next_pass_at(main_id="vidit", after=at, zone="Europe/Athens").at
        assert nxt > at
        at = nxt


# ── matrix: missed window, long outage ───────────────────────────────────────


@pytest.mark.ad9_guarantee
def test_a_missed_window_sends_nothing_and_is_computed_forward(registry, tmp_path):
    """Matrix: *missed window*. Nothing is sent; the next due time is forward.

    The natural implementation catches up, and for a product whose output is
    unprompted messages to a person, catching up means a queue of yesterday's
    thoughts arriving at once. This is the case the story exists to resist.
    """
    set_due(registry, "vidit", NOON - GRACE_SECONDS - 60)
    work = Recorder()
    result = asyncio.run(scheduler(registry, tmp_path, ["vidit"], work=work).tick())
    assert work.ran == []
    assert result.missed == ("vidit",) and result.ran == ()
    assert instant(registry.schedule_record("vidit")[NEXT_PASS_AT]) > NOON


@pytest.mark.ad9_guarantee
def test_a_long_outage_produces_no_backlog_and_no_storm(registry, tmp_path):
    """Matrix: *long outage*. Many windows missed, still nothing sent.

    Forty mains, each nine days overdue — the shape of a process that was down
    for a week. One pass each would be a storm; nine each would be the
    catastrophe. The answer is zero.
    """
    mains = [f"m{i}" for i in range(40)]
    for main_id in mains:
        set_due(registry, main_id, NOON - 9 * 86_400)
    work = Recorder()
    result = asyncio.run(scheduler(registry, tmp_path, mains, work=work).tick())
    assert work.ran == []
    assert sorted(result.missed) == sorted(mains)
    for main_id in mains:
        assert instant(registry.schedule_record(main_id)[NEXT_PASS_AT]) > NOON


@pytest.mark.ad9_guarantee
def test_a_missed_window_sends_nothing_through_the_recurring_loop_either(
    registry, tmp_path
):
    """Matrix: *the recurring loop*, crossed with *missed window*.

    **The mutation this exists for**: a startup ``_catch_up()`` draining every
    missed main before the loop begins left all 2002 tests green, because every
    missed-window case called ``tick()`` and no case ever called
    ``run_forever``. Catch-up arriving through the door the guard was not
    watching is still catch-up.
    """
    mains = [f"m{i}" for i in range(6)]
    for main_id in mains:
        set_due(registry, main_id, NOON - 5 * 86_400)
    work = Recorder()
    sch = Counting(
        registry=registry, mains=tuple(mains), root=tmp_path,
        clock=FrozenClock(at=NOON), work=work, stop_after=4,
    )
    results = run_loop(sch)
    assert work.ran == [], "a missed window ran work on the run_forever path"
    assert sorted(results[0].missed) == sorted(mains)
    assert all(r.missed == () for r in results[1:]), "the outage was drained twice"


def test_nothing_is_run_twice_after_a_missed_window(registry, tmp_path):
    """A second tick after the outage must not find the same main due again."""
    set_due(registry, "vidit", NOON - 5 * 86_400)
    work = Recorder()
    sch = scheduler(registry, tmp_path, ["vidit"], work=work)
    asyncio.run(sch.tick())
    assert asyncio.run(sch.tick()).missed == ()
    assert work.ran == []


def test_a_due_time_inside_the_grace_window_still_runs(registry, tmp_path):
    """The grace window is what keeps *no catch-up* from becoming *no passes*:
    a tick that lands a minute after a due time is on time, not late."""
    set_due(registry, "vidit", NOON - GRACE_SECONDS + 60)
    work = Recorder()
    asyncio.run(scheduler(registry, tmp_path, ["vidit"], work=work).tick())
    assert work.ran == ["vidit"]


@pytest.mark.ad9_guarantee
@pytest.mark.parametrize(
    ("lateness", "runs"),
    [(GRACE_SECONDS - 1, True), (GRACE_SECONDS, True), (GRACE_SECONDS + 1, False)],
    ids=["just-inside", "exactly-at-the-edge", "just-outside"],
)
def test_the_grace_boundary_is_pinned_on_both_sides(
    registry, tmp_path, lateness, runs
):
    """``>`` or ``>=`` is a one-character decision that moves the boundary by a
    second, and the earlier cases tested only ±60s around it. A due time
    *exactly* ``GRACE_SECONDS`` late is on time; one second later is not."""
    set_due(registry, "vidit", NOON - lateness)
    work = Recorder()
    asyncio.run(scheduler(registry, tmp_path, ["vidit"], work=work).tick())
    assert bool(work.ran) is runs


def test_the_tick_interval_cannot_step_over_the_grace_window():
    """A grace window narrower than the tick interval would drop passes
    silently: a due time falling between two ticks would read as missed."""
    assert TICK_SECONDS < GRACE_SECONDS


# ── matrix: the recurring loop ───────────────────────────────────────────────


@pytest.mark.ad9_guarantee
def test_the_loop_keeps_ticking_rather_than_ticking_once(registry, tmp_path):
    """Matrix: *the recurring loop* — run it, do not read it.

    A scheduler that ticks at boot and never again is a scheduler that works
    perfectly for one night. Replacing ``while True`` with a single iteration
    was green across 2002 tests, because nothing drove the loop.
    """
    set_due(registry, "vidit", NOON + 86_400)
    sch = Counting(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=NOON), stop_after=5,
    )
    results = run_loop(sch)
    assert sch.attempts == 5
    assert len(results) == 4  # the fifth cancels out of the loop


@pytest.mark.ad9_guarantee
def test_a_tick_that_raises_does_not_end_the_scheduler(registry, tmp_path):
    """Matrix: *the recurring loop* — dies on error.

    A transient store error must cost one tick, not the queue. Replacing the
    loop's ``except Exception`` with ``raise`` was green for the same reason
    the last case was.
    """
    set_due(registry, "vidit", NOON - 60)
    work = Recorder()
    sch = Counting(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=NOON), work=work, fail_first=2, stop_after=4,
    )
    results = run_loop(sch)
    assert sch.attempts == 4, "the loop stopped at the first failure"
    assert len(results) == 1 and results[0].ran == ("vidit",)
    assert work.ran == ["vidit"], "the tick after the failures did no work"


@pytest.mark.ad9_guarantee
def test_a_queue_that_cannot_be_locked_stops_the_scheduler(registry, tmp_path):
    """The one failure the loop must *not* survive.

    ``_lock`` raises ``ScheduleError`` when the platform offers no file locking
    at all, and a tick without a lock breaks the single writer per main (AD-1).
    Swallowing it turns a fatal configuration into an infinite loop logging once
    a minute while nobody is ever scheduled — degraded, and indistinguishable
    from healthy.
    """
    from half.schedule import tick as tick_module

    class Refusing(Scheduler):
        async def tick(self):
            raise ScheduleError("no file locking on this platform")

    sch = Refusing(registry=registry, mains=("vidit",), root=tmp_path,
                   clock=FrozenClock(at=NOON))
    with pytest.raises(ScheduleError):
        asyncio.run(sch.run_forever(interval=0))
    assert tick_module.ScheduleError is ScheduleError


def test_the_loop_sleeps_between_ticks_rather_than_spinning():
    """``run_forever`` awaits between ticks. A loop with no sleep is a busy
    wait that pins a core and starves the inbound path it shares."""
    import inspect

    source = inspect.getsource(Scheduler.run_forever)
    assert "asyncio.sleep(interval)" in source


# ── matrix: advance fails ────────────────────────────────────────────────────


@pytest.mark.ad9_guarantee
def test_a_pass_does_not_run_when_its_next_due_time_cannot_be_recorded(
    registry, tmp_path
):
    """Matrix: *advance fails*. Never a repeating storm.

    Reproduced in review: ``_advance`` swallowed every exception and the work
    ran regardless, so the old due time stayed in the log and the same window
    came back due on the next tick, and the next. At a sixty-second interval
    inside an hour of grace that is up to sixty passes for one night — the exact
    storm the missed-window rule exists to prevent, arriving through the error
    path.
    """

    class WriteFails:
        def __init__(self, real):
            self.real = real
            self.attempts = 0

        def schedule_record(self, main_id):
            return self.real.schedule_record(main_id)

        def zone_records(self, main_id):
            return self.real.zone_records(main_id)

        def crisis_open(self, main_id):
            return self.real.crisis_open(main_id)

        async def note_pass(self, main_id, *, t, fields):
            self.attempts += 1
            raise OSError("the disk is full")

    set_due(registry, "vidit", NOON - 60)
    broken = WriteFails(registry)
    work = Recorder()
    sch = scheduler(broken, tmp_path, ["vidit"], work=work)

    result = asyncio.run(sch.tick())
    assert work.ran == [], "the pass ran without a durable 'already ran' marker"
    assert result.unrecorded == ("vidit",)
    assert result.ran == ()


@pytest.mark.ad9_guarantee
def test_a_failed_advance_does_not_repeat_the_pass_every_tick(registry, tmp_path):
    """The consequence, over a whole grace window's worth of ticks.

    Sixty ticks — one hour at the shipped interval — against a store that
    cannot be written. Without the fix this is sixty passes for one night's
    window.
    """

    class WriteFails:
        def __init__(self, real):
            self.real = real

        def schedule_record(self, main_id):
            return self.real.schedule_record(main_id)

        def zone_records(self, main_id):
            return self.real.zone_records(main_id)

        def crisis_open(self, main_id):
            return self.real.crisis_open(main_id)

        async def note_pass(self, main_id, *, t, fields):
            raise OSError("the disk is full")

    set_due(registry, "vidit", NOON - 60)
    work = Recorder()
    sch = scheduler(WriteFails(registry), tmp_path, ["vidit"], work=work)
    for _ in range(60):
        asyncio.run(sch.tick())
    assert work.ran == [], f"one window produced {len(work.ran)} passes"


def test_an_advance_that_cannot_be_recorded_is_reported_not_hidden(
    registry, tmp_path
):
    """A pass that did not run because a write failed is not the same outcome as
    a pass that was not due, and a result that cannot tell them apart is how a
    stalled queue looks healthy."""

    class WriteFails:
        def __init__(self, real):
            self.real = real

        def schedule_record(self, main_id):
            return None

        def zone_records(self, main_id):
            return ()

        def crisis_open(self, main_id):
            return False

        async def note_pass(self, main_id, *, t, fields):
            raise OSError("the disk is full")

    result = asyncio.run(
        scheduler(WriteFails(registry), tmp_path, ["vidit"]).tick()
    )
    assert result.unrecorded == ("vidit",)
    assert result.scheduled == ()
    assert result.quiet is False


# ── matrix: two workers, stale lock ──────────────────────────────────────────


@pytest.mark.ad9_guarantee
def test_a_second_worker_ticking_concurrently_does_nothing(registry, tmp_path):
    """Matrix: *two workers*. The lock admits one; the other does nothing.

    Held open across the second tick with a real ``flock`` on a second open
    file description — which is what a second process holds — rather than by
    patching anything.
    """
    import fcntl

    set_due(registry, "vidit", NOON - 60)
    work = Recorder()
    sch = scheduler(registry, tmp_path, ["vidit"], work=work)

    with open(tmp_path / LOCK_NAME, "w", encoding="utf-8") as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = asyncio.run(sch.tick())
    assert result.held is True
    assert result.at is None, "a tick that does nothing does not even read a clock"
    assert work.ran == []


@pytest.mark.ad9_guarantee
def test_the_worker_that_holds_the_lock_is_the_only_one_that_writes(
    registry, tmp_path
):
    """AD-1 stated as the thing that would actually go wrong: not two ticks,
    but two writers on one main's log."""
    import fcntl

    work = Recorder()
    sch = scheduler(registry, tmp_path, ["vidit"], work=work)
    with open(tmp_path / LOCK_NAME, "w", encoding="utf-8") as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(sch.tick())
    assert registry.schedule_record("vidit") is None


@pytest.mark.ad9_guarantee
def test_a_lock_held_by_a_dead_worker_recovers_with_no_manual_action(
    registry, tmp_path
):
    """Matrix: *stale lock*. Recoverable without manual action; never a stall.

    A real child process takes the lock and is killed while holding it. Nothing
    cleans up, nothing times out, and the very next tick drains — because the
    kernel drops an open file description when its holder dies, which is the
    property a lease row in a table would have to reimplement and get wrong.
    """
    lock_path = tmp_path / LOCK_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl,sys,time\n"
         "f=open(sys.argv[1],'w')\n"
         "fcntl.flock(f, fcntl.LOCK_EX)\n"
         "print('held', flush=True)\n"
         "time.sleep(60)\n",
         str(lock_path)],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "held"
        set_due(registry, "vidit", NOON - 60)
        work = Recorder()
        sch = scheduler(registry, tmp_path, ["vidit"], work=work)
        assert asyncio.run(sch.tick()).held is True
        child.kill()
        child.wait(timeout=10)
    finally:
        if child.poll() is None:  # pragma: no cover - only on an assert above
            child.kill()
            child.wait(timeout=10)

    assert asyncio.run(sch.tick()).ran == ("vidit",)
    assert work.ran == ["vidit"]


def test_the_lock_is_released_when_a_tick_raises(registry, tmp_path):
    """A tick that blew up must not wedge the queue for the process's life."""

    class Exploding:
        async def run(self, main_id, now):
            raise RuntimeError("boom")

    set_due(registry, "vidit", NOON - 60)
    sch = scheduler(registry, tmp_path, ["vidit"], work=Exploding())
    assert asyncio.run(sch.tick()).failed == ("vidit",)

    import fcntl

    with open(tmp_path / LOCK_NAME, "w", encoding="utf-8") as probe:
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises if still held
        fcntl.flock(probe, fcntl.LOCK_UN)


@pytest.mark.ad9_guarantee
def test_only_lock_contention_is_swallowed_and_never_a_real_fault():
    """The reference implementation's documented failure, pinned.

    ``_is_contention`` returning ``True`` for everything makes descriptor
    exhaustion — every ``open`` failing — look exactly like *another worker is
    ticking*: the process reports a healthy held tick for ever while nothing is
    ever scheduled. Mutating it to ``return True`` was green across 2002 tests.
    """
    import errno

    for code in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES, errno.EDEADLK):
        assert _is_contention(OSError(code, "held"))
    for code in (errno.EMFILE, errno.ENFILE, errno.ENOSPC, errno.EIO,
                 errno.ENOENT, errno.EPERM, errno.EROFS):
        assert not _is_contention(OSError(code, "real")), errno.errorcode[code]


@pytest.mark.ad9_guarantee
def test_descriptor_exhaustion_raises_rather_than_reporting_a_held_tick(
    registry, tmp_path, monkeypatch
):
    """The behavioural half of the case above, driven through ``tick``."""
    import builtins
    import errno

    real_open = builtins.open

    def refuse(path, *args, **kwargs):
        if str(path).endswith(LOCK_NAME):
            raise OSError(errno.EMFILE, "too many open files")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", refuse)
    with pytest.raises(OSError):
        asyncio.run(scheduler(registry, tmp_path, ["vidit"]).tick())


# ── matrix: tick and turn (AD-1) ─────────────────────────────────────────────


@pytest.mark.ad9_guarantee
def test_the_tick_writes_through_the_same_mutex_a_turn_holds(registry, tmp_path):
    """Matrix: *tick and turn*. AD-1, behaviourally.

    The claim used to live only in ``note_pass``'s docstring: replacing its
    ``async with self.acquire(main_id)`` with a direct hydrate-and-record left
    2002 tests green while the tick appended *inside* another writer's turn.
    Pinned the way ``tests/test_actor.py`` pins its sibling — by watching the
    order of two overlapping writers.
    """
    order: list[str] = []

    async def turn() -> None:
        async with registry.acquire("vidit"):
            order.append("turn-start")
            await asyncio.sleep(0.05)
            order.append("turn-end")

    async def note() -> None:
        await asyncio.sleep(0.01)  # start inside the turn
        order.append("note-start")
        await registry.note_pass(
            "vidit", t=stamp(NOON),
            fields={NEXT_PASS_AT: stamp(NOON + 86_400), ZONE: "UTC",
                    TOLD_ZONE: False},
        )
        order.append("note-end")

    async def both() -> None:
        await asyncio.gather(turn(), note())

    asyncio.run(both())
    assert order == ["turn-start", "note-start", "turn-end", "note-end"], (
        "the tick appended inside another writer's turn — AD-1 says every "
        "mutation for a main serializes through that main's single owner"
    )


# ── matrix: restart ──────────────────────────────────────────────────────────


def test_due_times_survive_a_restart_and_a_completed_pass_does_not_re_run(
    tmp_path
):
    """Matrix: *restart*. Durable.

    A whole new ``ActorRegistry`` over the same tree — every actor cold, every
    fold read from the log — which is what a restart is. Held in memory, this
    case is the one that silently fails: nothing raises, the pass simply runs
    a second time.
    """
    first = ActorRegistry(tmp_path)
    set_due(first, "vidit", NOON - 60)
    work = Recorder()
    asyncio.run(scheduler(first, tmp_path, ["vidit"], work=work).tick())
    recorded = first.schedule_record("vidit")[NEXT_PASS_AT]
    first.close()

    second = ActorRegistry(tmp_path)
    try:
        assert second.schedule_record("vidit")[NEXT_PASS_AT] == recorded
        again = Recorder()
        asyncio.run(scheduler(second, tmp_path, ["vidit"], work=again).tick())
        assert again.ran == []
    finally:
        second.close()


def test_the_due_time_is_folded_from_the_log_and_not_from_sqlite(tmp_path):
    """AD-3: the log is the only authority. Deleting the derived view and
    replaying reproduces the schedule."""
    reg = ActorRegistry(tmp_path)
    set_due(reg, "vidit", NOON + 500)
    recorded = reg.schedule_record("vidit")
    reg.close()

    (tmp_path / "vidit" / "half.db").unlink()
    reg = ActorRegistry(tmp_path)
    try:
        assert reg.schedule_record("vidit") == recorded
    finally:
        reg.close()


@pytest.mark.ad9_guarantee
def test_a_derived_view_from_the_previous_shape_is_discarded_not_reused(tmp_path):
    """``DERIVED_VERSION`` reverted to 7 was green across 2002 tests, and the
    consequence is the herd this whole story exists to prevent: a v7 view has no
    schedule row, so on upgrade every main folds to never-scheduled and the
    first tick rewrites the entire population's due times in one go.

    Asserted with the literal version rather than the constant, so bumping the
    constant cannot make this pass by moving with it. Story 9c bumped it to 9
    when the fold's tension semantics changed, and updating the literal here is
    the deliberate acknowledgement that gate is asking for: what it forbids is
    a bump that *nobody noticed*, and the stale view it plants is one version
    behind whatever the current one is. Story 10 bumped it to 10 for the
    ``touches`` table, and its review to 11 when the day marker stopped being
    "the last raise of any loop".
    """
    from half.store import db

    assert db.DERIVED_VERSION == 11

    reg = ActorRegistry(tmp_path)
    set_due(reg, "vidit", NOON + 500)
    recorded = reg.schedule_record("vidit")
    reg.close()

    import sqlite3

    conn = sqlite3.connect(tmp_path / "vidit" / "half.db")
    conn.execute("PRAGMA user_version = 10")
    conn.commit()
    conn.close()

    reg = ActorRegistry(tmp_path)
    try:
        assert reg.schedule_record("vidit") == recorded, (
            "a stale derived view survived the upgrade and lost the due time"
        )
    finally:
        reg.close()


@pytest.mark.ad9_guarantee
def test_the_schema_version_moved_with_the_op(store):
    """AD-29: adding an op is a deliberate versioned change. A build that
    predates ``schedule`` must refuse to fold rather than skip it and read every
    main as never scheduled.

    The literal, because the incidental pin — a ``"v":5`` inside a JSON string
    in another case — is not the deliberate one. It moves when an op is added
    and only then: ``schedule`` took it to 5, ``touch`` to 6, story 10's review
    reshaped ``touch`` to 7, and ``asked`` took it to 8 (story 5b). Each step is
    a line in this test, which is the point of pinning it at all.
    """
    from half.errors import SchemaVersionError
    from half.store.records import decode

    assert SCHEMA_VERSION == 8
    store.record(Op.SCHEDULE, "sc_1", "2026-09-01T12:00Z",
                 next_pass_at="2026-09-02T03:41:00Z", zone="UTC", told_zone=False)
    assert store.fold().schedule["v"] == SCHEMA_VERSION
    with pytest.raises(SchemaVersionError):
        decode('{"t":"2026-09-01T12:00Z","op":"schedule","id":"sc_1",'
               '"next_pass_at":"2026-09-02T03:00:00Z","zone":"UTC","v":%d}'
               % (SCHEMA_VERSION + 1),
               path="t", lineno=1)


def test_a_schedule_record_folds_and_replays(store):
    """The op is in the closed vocabulary and the fold materializes it."""
    store.record(Op.SCHEDULE, "sc_1", "2026-09-01T12:00Z",
                 next_pass_at="2026-09-02T03:41:00Z", zone="UTC", told_zone=False)
    assert store.fold().schedule[NEXT_PASS_AT] == "2026-09-02T03:41:00Z"
    assert store.fold().canonical_json() == store.state().canonical_json()


def test_a_due_time_the_build_cannot_read_is_refused_before_it_is_durable(store):
    """Write strict: the log is append-only, so a due time nothing can parse
    would make this main either never due again or due on every tick, for ever,
    with the offending line unremovable."""
    for bad in ("tomorrow", "2026-02-31T03:00:00Z", "2026-09-02 03:00", ""):
        with pytest.raises(ScheduleError):
            store.record(Op.SCHEDULE, "sc_x", "2026-09-01T12:00Z",
                         next_pass_at=bad, zone="UTC")
    with pytest.raises(ScheduleError):
        store.record(Op.SCHEDULE, "sc_x", "2026-09-01T12:00Z",
                     next_pass_at="2026-09-02T03:00:00Z", zone="")


@pytest.mark.ad9_guarantee
def test_a_schedule_record_with_no_due_time_at_all_is_fatal_to_the_fold(store):
    """AD-29: a record this build cannot recognise must not fold to nothing.

    Deleting the fold's ``raise`` was green: the main reads as never scheduled
    for ever and is rescheduled on every tick, which is a silent omission
    wearing the costume of a fresh start.
    """
    from half.errors import CorruptLogError
    from half.store.records import decode

    store.log.append(decode(
        '{"t":"2026-09-01T12:00Z","op":"schedule","id":"sc_1","zone":"UTC","v":5}',
        path="<another build>", lineno=1,
    ))
    with pytest.raises(CorruptLogError):
        store.fold()


def test_an_unreadable_due_time_costs_one_pass_and_never_the_store(
    registry, tmp_path
):
    """Read tolerant: a record written by another build whose *value* this one
    cannot parse must not take a main's whole store down over a due time. It
    folds, it reads as never-scheduled, and the main is scheduled forward and
    sent nothing."""
    from half.store.records import decode

    written_by_another_build = decode(
        '{"t":"2026-09-01T12:00Z","op":"schedule","id":"sc_1",'
        '"next_pass_at":"whenever","zone":"UTC","v":5}',
        path="<another build>", lineno=1,
    )
    with Store(tmp_path / "vidit") as store:
        store.log.append(written_by_another_build)
    work = Recorder()
    result = asyncio.run(scheduler(registry, tmp_path, ["vidit"], work=work).tick())
    assert work.ran == []
    assert result.scheduled == ("vidit",)


# ── matrix: told timezone, unknown timezone, inferred zone ───────────────────


def test_a_told_zone_puts_the_due_time_at_that_main_s_local_pre_dawn(
    registry, tmp_path
):
    """Matrix: *told timezone*."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    tell_zone(tmp_path, "vidit", "Asia/Kolkata")
    sch = scheduler(registry, tmp_path, ["vidit"])
    result = asyncio.run(sch.tick())
    record = registry.schedule_record("vidit")
    assert record[ZONE] == "Asia/Kolkata"
    assert record[TOLD_ZONE] is True
    assert result.on_fallback == ()
    local = dt.datetime.fromtimestamp(
        instant(record[NEXT_PASS_AT]), ZoneInfo("Asia/Kolkata")
    )
    assert local.hour in (3, 4)


def test_no_told_zone_uses_a_recorded_fallback_that_is_visible_as_one(
    registry, tmp_path
):
    """Matrix: *unknown timezone*. A recorded fallback, never an inference.

    ``told_zone`` false is the requirement: a due time computed in UTC for a
    main who told Half nothing is otherwise indistinguishable from one computed
    in UTC for a main in Reykjavík.

    **And it is read, not merely written.** A flag nothing in ``half/`` reads is
    visible only to somebody with the raw JSONL open, so the tick surfaces it in
    its own result — which is what an operator and story 9b actually see.
    """
    result = asyncio.run(scheduler(registry, tmp_path, ["vidit"]).tick())
    record = registry.schedule_record("vidit")
    assert record[ZONE] == due.FALLBACK_ZONE
    assert record[TOLD_ZONE] is False
    assert result.on_fallback == ("vidit",)


def test_a_main_running_on_a_fallback_is_reported_on_the_running_path_too(
    registry, tmp_path
):
    """The same visibility for a main who is actually due, not only for one
    being scheduled for the first time."""
    set_due(registry, "vidit", NOON - 60)
    result = asyncio.run(scheduler(registry, tmp_path, ["vidit"]).tick())
    assert result.ran == ("vidit",)
    assert result.on_fallback == ("vidit",)


def test_an_unconfirmed_zone_is_not_a_told_zone(registry, tmp_path):
    """A zone Half wrote down and nobody confirmed is not an answer. The gate
    is the ladder's own — the same question story 6b asks about a region."""
    tell_zone(tmp_path, "vidit", "Asia/Kolkata", rung=License.BEHAVE)
    asyncio.run(scheduler(registry, tmp_path, ["vidit"]).tick())
    assert registry.schedule_record("vidit")[TOLD_ZONE] is False


def test_two_different_told_zones_are_no_answer_at_all(tmp_path):
    """A main who has told Half two zones has told it nothing this module may
    act on, and picking one would be the inference the rule forbids."""
    with Store(tmp_path / "vidit") as store:
        seed_belief(store, "b_a", "2026-08-01T09:00Z", rung=License.ASSERT,
                    support=["s_1"], zone="Asia/Kolkata")
        seed_belief(store, "b_b", "2026-08-02T09:00Z", rung=License.ASSERT,
                    support=["s_2"], zone="Europe/Berlin")
        records = list(store.state().beliefs.values())
    assert due.zone_of(records) is None


def test_a_main_who_moves_supersedes_their_zone_through_the_correction_path(
    tmp_path
):
    """The answer to *"a main who moves is stranded on the fallback for ever"*.

    There is no recency rule here on purpose — breaking a tie between two
    confirmed answers is the inference the rule forbids — but there is a
    supersede path, and it is the one the product already has for every other
    belief: the main says Half is wrong, a correction is appended, and the old
    zone leaves the fold. ``retract`` because they changed, not because Half
    was.
    """
    with Store(tmp_path / "vidit") as store:
        seed_belief(store, "b_a", "2026-08-01T09:00Z", rung=License.ASSERT,
                    support=["s_1"], zone="Asia/Kolkata")
        seed_belief(store, "b_b", "2026-09-01T09:00Z", rung=License.ASSERT,
                    support=["s_2"], zone="Europe/Berlin")
        assert due.zone_of(store.state().beliefs.values()) is None

        store.record(Op.RETRACT, "r_1", "2026-09-01T09:05Z", target="b_a")
        assert due.zone_of(store.state().beliefs.values()) == "Europe/Berlin"


def test_a_zone_this_build_does_not_hold_falls_back_and_records_it():
    """Every way a zone can be unusable lands on the same recorded fallback."""
    for bad in (None, "", 42, "Mars/Olympus", "../../etc/passwd", "Etc/Nowhere",
                "/etc/passwd", "x" * 80, True):
        resolved, told = due.resolve(bad)
        assert (resolved, told) == (due.FALLBACK_ZONE, False), bad


def test_the_fallback_zone_works_on_a_host_with_no_timezone_database(monkeypatch):
    """The one path that exists to keep working must not need the thing whose
    absence sent it there.

    A minimal container has no ``/usr/share/zoneinfo``, so every told zone
    resolves to the fallback — and resolving the *fallback* through ``ZoneInfo``
    too would raise on every main at once.
    """
    import zoneinfo

    from half.schedule import due as module

    def no_database(*args, **kwargs):
        raise zoneinfo.ZoneInfoNotFoundError("no time zone found with key")

    monkeypatch.setattr(module, "ZoneInfo", no_database)
    assert module.resolve("Asia/Kolkata") == (due.FALLBACK_ZONE, False)
    result = module.next_pass_at(main_id="vidit", after=NOON, zone="Asia/Kolkata")
    assert result.zone == due.FALLBACK_ZONE and result.told is False
    assert result.at > NOON


def test_the_writer_refuses_a_zone_that_would_silently_fall_back():
    """The write side of *told, never inferred*: storing a key that resolves to
    the fallback would make an answer look like one and behave like neither."""
    assert due.told("Asia/Kolkata", support=["s_1"])[ZONE] == "Asia/Kolkata"
    for bad in ("Mars/Olympus", "IST", "+05:30", ""):
        with pytest.raises(ValueError):
            due.told(bad, support=["s_1"])


def test_the_zone_writer_takes_no_signal_to_infer_from():
    """Transposed from story 6b's region writer: there is no argument here for
    a prefix, an IP, a locale or an offset, so a zone arrives as an answer or it
    does not arrive."""
    import inspect

    assert list(inspect.signature(due.told).parameters) == ["zone", "support"]


def test_the_scheduler_is_handed_a_zone_and_never_a_ledger_record(tmp_path):
    """Transposed from ``handoff_projection``, which got exactly this test a
    round earlier: narrowing by *record* is not narrowing.

    ``zone_projection`` returning the whole record was green across 2002 tests,
    and the shape it leaks is the most ordinary one there is — *"I moved to
    Berlin for the job I hate"* is a zone and a claim in one sentence.
    """
    record = {
        "id": "b_1", ZONE: "Europe/Berlin", "license": "assert",
        "support": ["s_1"], "known_to_main": True,
        "claim": "dreads the job that moved them", "subject": "self",
        "ledger": "revealed", "loop": "the-move",
    }
    visible = zone_projection(record)
    assert visible[ZONE] == "Europe/Berlin"
    assert "claim" not in visible and "subject" not in visible
    assert "ledger" not in visible and "loop" not in visible
    assert set(visible) <= {"id", ZONE, "license", "support", "known_to_main",
                            "quarantined"}


def test_the_registry_narrows_a_real_zone_belief_before_the_scheduler_sees_it(
    registry, tmp_path
):
    """The projection, driven through the door the scheduler actually uses."""
    with Store(tmp_path / "vidit") as store:
        seed_belief(store, "b_1", "2026-08-01T09:00Z", rung=License.ASSERT,
                    support=["s_1"], zone="Europe/Berlin",
                    claim="dreads the job that moved them", subject="self")
    for record in registry.zone_records("vidit"):
        assert "claim" not in record, "the scheduler was handed a claim"


# ── matrix: zone inference, clock readers ────────────────────────────────────


def names_read_by(path: Path) -> set[str]:
    """Every identifier, attribute, argument and string literal in ``path``.

    **Lifted verbatim from ``tests/test_crisis.py``**, which is where story 6b
    put it, and deliberately not rewritten: three spellings rather than one,
    because ``getattr(inbound, "phone_prefix", None)`` walks past a scan that
    only looks at ``ast.Name``. A second copy would be a second, weaker copy.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            seen.add(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seen.update(arg.arg for arg in node.args.args)
            seen.update(arg.arg for arg in node.args.kwonlyargs)
    return {name.casefold() for name in seen}


#: Every signal a zone could be guessed from. Deliberately *not* including
#: ``timezone`` or ``tz``: this story's own modules hold the told zone and say
#: so, exactly as ``half/crisis/contacts.py`` is allowed to hold a region. What
#: is forbidden is the *input to a guess*.
INFERRING = {
    "phone_prefix", "dial_code", "country_code", "calling_code", "msisdn",
    "ip", "ip_address", "remote_addr", "geoip", "geo", "latitude", "longitude",
    "lat", "lon", "coordinates", "accept_language", "language", "lang",
    "locale", "currency", "utc_offset", "offset_hours", "tzname", "tzlocal",
    "getdefaulttimezone", "gettz", "tz_from_ip", "zone_for_number", "area_code",
}


@pytest.mark.one_clock
@pytest.mark.one_clock_guarantee
def test_no_module_anywhere_can_infer_where_the_main_sleeps():
    """Matrix: *zone inference*. The rule has a guard.

    It did not. The matrix row said *asserted structurally* and nothing asserted
    it: ``guess_zone(inbound.phone_prefix)`` in a new module passed 2002 tests.
    A rule that reads as settled and is not is worse than no rule.

    Scanned over the **whole tree**, not just ``half/schedule/``, because the
    reported bypass was a new module — and a guard that only watches the folder
    the rule was written in watches nothing. Story 6b's scan for region is the
    same scan, over the same signals, asking the same question.
    """
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        seen = names_read_by(path) & INFERRING
        if seen:
            offenders.append(f"{path.relative_to(ROOT)}: {sorted(seen)}")
    assert not offenders, (
        f"a zone could be inferred from {offenders}; where the main sleeps is "
        f"told, never inferred (AD-9, the rule story 6b set for region)"
    )


@pytest.mark.one_clock
def test_the_zone_inference_scan_catches_each_bypass_it_exists_for(tmp_path):
    """Non-vacuity, run through the same helper the gate uses — the lesson
    ``tests/test_crisis.py`` records: a shared engine no test exercises is a
    gate resting on nothing."""
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        "def guess_zone(inbound, headers):\n"
        "    country = getattr(inbound, 'country_code', None)\n"
        "    return country or inbound.phone_prefix or headers['locale']\n",
        encoding="utf-8",
    )
    seen = names_read_by(bypass)
    assert "country_code" in seen, "the getattr-string spelling is unwatched"
    assert "phone_prefix" in seen, "the attribute spelling is unwatched"
    assert "locale" in seen, "the string-key spelling is unwatched"
    assert seen & INFERRING


@pytest.mark.one_clock
@pytest.mark.one_clock_guarantee
def test_nothing_anywhere_infers_the_zone_the_host_happens_to_be_in():
    """The other half of *never inferred*, and the one that looks like
    arithmetic.

    ``astimezone()`` with no argument reads the host's zone. So does
    ``fromtimestamp(x)`` with no ``tz``, ``time.localtime()`` and ``tzname``.
    Every one of them is a fact about the server rather than about the person,
    and every one of them is right often enough to be indistinguishable from an
    answer. Scanned over the whole tree, not one folder.
    """
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)):
                continue
            where = f"{path.relative_to(ROOT)}:{node.lineno}"
            if node.func.attr == "astimezone" and not node.args:
                offenders.append(f"{where} astimezone()")
            if node.func.attr == "fromtimestamp" and len(node.args) < 2 \
                    and not node.keywords:
                offenders.append(f"{where} naive fromtimestamp()")
            if node.func.attr in ("localtime", "tzset"):
                offenders.append(f"{where} {node.func.attr}()")
    assert not offenders, f"the host's own zone is being read: {offenders}"


@pytest.mark.one_clock
@pytest.mark.parametrize(
    "bypass",
    ["moment.astimezone()", "dt.datetime.fromtimestamp(x)", "time.localtime()",
     "time.tzset()"],
)
def test_the_host_zone_scan_sees_each_shape_of_the_inference(bypass, tmp_path):
    """Non-vacuity for the scan above, one shape at a time."""
    path = tmp_path / "bypass.py"
    path.write_text(f"def _f(x):\n    return {bypass}\n", encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "astimezone" and not node.args:
                found.append(node)
            if node.func.attr == "fromtimestamp" and len(node.args) < 2 \
                    and not node.keywords:
                found.append(node)
            if node.func.attr in ("localtime", "tzset"):
                found.append(node)
    assert found, f"the host-zone scan does not see {bypass!r}"


@pytest.mark.one_clock
@pytest.mark.one_clock_guarantee
def test_the_due_time_does_not_move_with_the_host_s_timezone():
    """The behavioural half of the two scans above, and the one that would
    actually have caught a host-zone read.

    Run in **subprocesses** rather than by mutating ``os.environ["TZ"]`` and
    calling ``tzset()`` in-process: that is global to the interpreter, so it
    would corrupt any test running beside it under ``-p xdist`` and any test
    that formats a local time. Three zones on three sides of the planet.
    """
    script = (
        "from half.schedule.due import next_pass_at\n"
        "print(next_pass_at(main_id='vidit', after=1788264000.0, zone=None).at)\n"
    )
    answers = set()
    for zone in ("UTC", "Pacific/Kiritimati", "America/Anchorage"):
        env = dict(os.environ, TZ=zone, PYTHONPATH=str(ROOT))
        out = subprocess.run([sys.executable, "-c", script],
                             capture_output=True, text=True, env=env, check=True)
        answers.add(out.stdout.strip())
    assert len(answers) == 1, f"the host's TZ moved the due time: {answers}"


#: Every shape of *what time is it now*. ``sleep`` is deliberately absent: a
#: sleep does not read a clock, and including it would make the gate fire on
#: the retry backoff and the tick interval, which are not clock reads.
AMBIENT = {
    "now", "utcnow", "today", "time", "monotonic", "perf_counter",
    "time_ns", "monotonic_ns", "gmtime", "localtime", "clock_gettime",
    "clock_gettime_ns", "process_time", "process_time_ns", "thread_time",
    "thread_time_ns", "times", "tzset",
}

#: Modules the ambient names live on. A reference is a clock read when it
#: *roots* in one of these, which is what tells ``time.time`` apart from
#: ``self.now`` — a field holding an injected instant, which
#: ``half/context/channels.py`` legitimately has and the first version of this
#: scan would have called a clock read.
IMPURE_MODULES = {"time", "datetime", "os", "calendar"}


def _impure_names(tree: ast.AST) -> set[str]:
    """Names in this module that resolve to something ambient.

    Three binding shapes, then a fixed point over assignments — because review
    round 1 walked past the first version with ``_reader = _t.time`` and
    ``getattr(time, "time")()``, neither of which is a call to a dotted name.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in IMPURE_MODULES:
                    bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] in IMPURE_MODULES:
                bound.update(a.asname or a.name for a in node.names)
    # `m = time` rebinds the module; iterate so `a = time; b = a` is caught too.
    for _ in range(4):
        grew = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if _root_of(node.value) in bound:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in bound:
                        bound.add(target.id)
                        grew = True
        if not grew:
            break
    return bound


def _root_of(node: ast.AST) -> str | None:
    """The leftmost name of a dotted expression: ``dt.datetime.now`` -> ``dt``."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def clock_reads(path: Path) -> set[str]:
    """Every way this module could ask what time it is.

    Not three spellings — *the ways*: a dotted call, an alias bound to the
    module, a bare name imported from it, a reference in any position at all
    (a default factory is not a call), and ``getattr`` with the name as a
    string.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound = _impure_names(tree)
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in AMBIENT:
            if _root_of(node) in bound:
                hits.add(node.attr)
        elif isinstance(node, ast.Name) and node.id in AMBIENT and node.id in bound:
            hits.add(node.id)
        elif (isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name)
              and node.func.id == "getattr"
              and len(node.args) > 1
              and isinstance(node.args[1], ast.Constant)
              and node.args[1].value in AMBIENT):
            hits.add(str(node.args[1].value))
    return hits


@pytest.mark.one_clock
@pytest.mark.one_clock_guarantee
def test_exactly_one_module_in_the_tree_reads_a_clock():
    """Matrix: *clock readers, any spelling*. A test fails otherwise.

    The acceptance criterion, asserted over the whole package rather than over
    the scheduler. Confining the clock to one module is what keeps *"everything
    takes an injected now"* true everywhere else — and it stops being true the
    quiet way: somebody adds ``datetime.now()`` to an adapter, nothing breaks,
    and a year later two subsystems disagree about what "today" is.
    """
    readers = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "half").rglob("*.py")
        if clock_reads(path)
    )
    assert readers == ["half/schedule/clock.py"], (
        f"{len(readers)} modules read a clock: {readers}. Exactly one may "
        f"(AD-30); everything else takes an injected `now`."
    )


@pytest.mark.one_clock
@pytest.mark.parametrize(
    "bypass",
    [
        "import time\ndef f():\n    return time.time()\n",
        "import time as _t\ndef f():\n    return _t.time()\n",
        "import time as _t\n_reader = _t.time\ndef f():\n    return _reader()\n",
        "import time\nfrom dataclasses import field\nx = field(default_factory=time.time)\n",
        "import time\ndef f():\n    return getattr(time, 'time')()\n",
        "from time import monotonic\ndef f():\n    return monotonic()\n",
        "import datetime as dt\ndef f():\n    return dt.datetime.now(dt.UTC)\n",
        "from datetime import datetime\ndef f():\n    return datetime.utcnow()\n",
        "from datetime import date\ndef f():\n    return date.today()\n",
        "import time\n_m = time\ndef f():\n    return _m.perf_counter()\n",
        "import time\n_m = time\n_n = _m\ndef f():\n    return _n.time_ns()\n",
        "import os\ndef f():\n    return os.times()\n",
    ],
    ids=["dotted", "alias", "alias-bound-to-function", "default-factory",
         "getattr", "from-import", "datetime-now", "utcnow", "date-today",
         "module-rebound", "module-rebound-twice", "os-times"],
)
def test_the_clock_scan_sees_each_way_of_asking_the_time(bypass, tmp_path):
    """Non-vacuity, one *way* at a time.

    Review round 1 defeated the first version of this scan twice — with an
    alias bound to the function and with ``getattr`` — because it only looked
    at calls to dotted names. A scan nobody has tried to defeat is a scan
    nobody has tested, and this one is the whole of the guarantee.
    """
    path = tmp_path / "bypass.py"
    path.write_text(bypass, encoding="utf-8")
    assert clock_reads(path), f"the scan does not see:\n{bypass}"


@pytest.mark.one_clock
def test_the_clock_scan_does_not_fire_on_an_injected_now(tmp_path):
    """The false positive that matters, and the reason the scan resolves roots.

    ``half/context/channels.py`` renders ``self.now`` — a field holding the
    instant it was *given*, which is the pattern this whole design is for. A
    scan that called that a clock read would push people to rename the field
    rather than to stop reading clocks.
    """
    path = tmp_path / "injected.py"
    path.write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Channels:\n"
        "    now: str\n"
        "    def render(self):\n"
        "        return f'now: {self.now}'\n",
        encoding="utf-8",
    )
    assert not clock_reads(path)


@pytest.mark.one_clock
@pytest.mark.one_clock_guarantee
def test_everything_the_tick_calls_takes_an_injected_now():
    """Matrix: *purity below*. No ambient time.

    The two modules the tick is built from read nothing, and the ``Pass``
    protocol the tick calls takes ``now`` as an argument — so a pass that
    wanted the time would have to add a second clock reader and fail the case
    above.
    """
    import inspect

    from half.schedule.tick import Pass

    for relative in ("half/schedule/due.py", "half/schedule/tick.py"):
        assert not clock_reads(ROOT / relative), relative

    assert "now" in inspect.signature(Pass.run).parameters
    assert "now" in inspect.signature(Nothing.run).parameters


@pytest.mark.one_clock
def test_the_clock_module_is_the_only_thing_that_needs_a_real_clock():
    """The seam, exercised: a frozen clock is a whole ``Clock``, so nothing in
    this suite patches a module attribute to control time."""
    assert FrozenClock(at=NOON).read() == moment(NOON)
    assert FrozenClock(at=NOON).read().stamp == "2026-09-01T12:00:00Z"
    real = SystemClock().read()
    assert real.stamp.endswith("Z") and real.epoch > 0


# ── matrix: untrusted stamp ──────────────────────────────────────────────────


@pytest.mark.one_clock
@pytest.mark.one_clock_guarantee
@pytest.mark.parametrize(
    "hostile",
    [float("nan"), float("inf"), float("-inf"), -1.0, 0, 10 ** 30, -(10 ** 30),
     "not a number", None, {}, [], True],
    ids=["nan", "inf", "-inf", "negative", "epoch-zero", "huge", "hugely-negative",
         "string", "none", "dict", "list", "bool"],
)
def test_an_untrusted_stamp_is_clamped_and_never_raises(hostile):
    """Matrix: *untrusted stamp*. Clamped into the range the store accepts.

    Two verified defects in one row. ``min``/``max`` propagate NaN, so
    ``stamp(nan)`` escaped as a ``ValueError`` — out of a receive loop serving
    every main. And the clamp's own bounds were ``datetime``'s rather than the
    store's, so ``stamp(-1)`` produced ``1969-12-31Z``: a value that renders,
    stores, and is then silently unreadable by ``half.civil``, which is what
    every floor, timescale and due-time comparison in the product is measured
    with.
    """
    rendered = stamp(hostile)
    assert rendered.endswith("Z")
    assert instant(rendered) is not None, f"{hostile!r} produced {rendered}"


@pytest.mark.one_clock
def test_the_clamp_range_is_the_range_the_store_validates():
    """``half.schedule.clock`` deliberately imports nothing from ``half``, so
    its bounds are written out rather than derived. This is the case that would
    catch them drifting from ``half.civil``'s."""
    assert stamp(MIN_EPOCH).startswith(f"{MIN_YEAR:04d}-")
    assert stamp(MAX_EPOCH).startswith(f"{MAX_YEAR - 1:04d}-")
    assert instant(stamp(MIN_EPOCH)) == int(MIN_EPOCH)
    assert instant(stamp(MAX_EPOCH)) == int(MAX_EPOCH)
    assert clamp(float("nan")) == MIN_EPOCH
    assert clamp(NOON) == NOON


@pytest.mark.one_clock
@pytest.mark.one_clock_guarantee
def test_a_hostile_platform_date_does_not_abort_inbound_processing():
    """The regression this row exists for: the helper that used to guard
    ``fromtimestamp`` with ``OverflowError``/``OSError``/``ValueError`` was
    replaced, and its guards did not come with it. A ``NaN`` date would end the
    receive loop for every main."""
    from half.channel.telegram import TelegramChannel
    from tests.conftest import FakeTransport, msg

    async def collect(channel):
        return [item async for item in channel.receive()]

    for date in (float("nan"), float("inf"), 10 ** 30, "nan", -(10 ** 30)):
        channel = TelegramChannel(
            transport=FakeTransport([msg(date=date)]), mains={"123": "vidit"},
            clock=FrozenClock(at=NOON),
        )
        got = asyncio.run(collect(channel))
        assert len(got) == 1 and instant(got[0].t) is not None, date


@pytest.mark.one_clock
def test_an_unreadable_inbound_date_falls_back_to_the_channel_s_own_clock():
    """``return 0.0`` in place of the fallback was green across 2002 tests, and
    every message with an unreadable date would have been stamped 1970 — or,
    after the clamp, 2000 — with nothing noticing."""
    from half.channel.telegram import TelegramChannel
    from tests.conftest import FakeTransport, msg

    async def collect(channel):
        return [item async for item in channel.receive()]

    channel = TelegramChannel(
        transport=FakeTransport([msg(date="not-a-date")]), mains={"123": "vidit"},
        clock=FrozenClock(at=NOON),
    )
    got = asyncio.run(collect(channel))
    assert got[0].t == FrozenClock(at=NOON).read().stamp


# ── matrix: one main raises, one main hangs, suspended, hibernation ──────────


@pytest.mark.ad9_guarantee
def test_one_main_raising_does_not_stop_the_tick_or_touch_another(
    registry, tmp_path
):
    """Matrix: *one main raises*. Logged without content; the tick continues."""
    mains = ["a", "b", "c"]
    for main_id in mains:
        set_due(registry, main_id, NOON - 60)
    work = Recorder(raises="b")
    result = asyncio.run(scheduler(registry, tmp_path, mains, work=work).tick())
    assert sorted(work.ran) == ["a", "c"]
    assert result.failed == ("b",)
    assert sorted(result.ran) == ["a", "c"]


@pytest.mark.ad9_guarantee
def test_one_main_hanging_is_bounded_and_the_others_still_run(registry, tmp_path):
    """Matrix: *one main hangs*. Never an unbounded wait.

    The hanging pass sleeps for an hour; the tick returns in a fraction of a
    second, having cancelled it, with everybody else's pass complete.
    """
    mains = ["a", "b", "c"]
    for main_id in mains:
        set_due(registry, main_id, NOON - 60)
    work = Recorder(hangs=["b"])
    started = _real_time.monotonic()
    result = asyncio.run(
        scheduler(registry, tmp_path, mains, work=work, timeout=0.05).tick()
    )
    assert _real_time.monotonic() - started < 5.0
    assert result.timed_out == ("b",)
    assert sorted(work.ran) == ["a", "c"]


def test_a_main_whose_pass_failed_is_still_advanced(registry, tmp_path):
    """At most once, and that includes the failures. A pass that raised must
    not be retried at every tick until dawn — no catch-up means no retry."""
    set_due(registry, "vidit", NOON - 60)
    work = Recorder(raises="vidit")
    sch = scheduler(registry, tmp_path, ["vidit"], work=work)
    asyncio.run(sch.tick())
    assert asyncio.run(sch.tick()).failed == ()
    assert instant(registry.schedule_record("vidit")[NEXT_PASS_AT]) > NOON


def test_a_main_whose_store_cannot_be_read_does_not_end_the_drain(
    registry, tmp_path
):
    """One main's decision failing is one main's pass lost, never the tick."""

    class Broken:
        def __init__(self, real):
            self.real = real

        def schedule_record(self, main_id):
            if main_id == "broken":
                raise RuntimeError("this store is on fire")
            return self.real.schedule_record(main_id)

        def zone_records(self, main_id):
            return self.real.zone_records(main_id)

        def crisis_open(self, main_id):
            return self.real.crisis_open(main_id)

        async def note_pass(self, main_id, *, t, fields):
            await self.real.note_pass(main_id, t=t, fields=fields)

    set_due(registry, "ok", NOON - 60)
    work = Recorder()
    result = asyncio.run(
        scheduler(Broken(registry), tmp_path, ["broken", "ok"], work=work).tick()
    )
    assert work.ran == ["ok"]
    assert result.ran == ("ok",)


def test_a_main_in_crisis_mode_is_advanced_but_not_run(registry, tmp_path):
    """CAP-12: the mode suspends Half's ordinary behaviour, and a nightly pass
    is ordinary behaviour.

    It costs nothing today, because the pass is ``Nothing`` — which is exactly
    why the branch has to exist before story 9b hangs real work on it, rather
    than after.
    """
    set_due(registry, "vidit", NOON - 60)
    set_due(registry, "asha", NOON - 60)
    asyncio.run(registry.suspend_for_crisis(
        "vidit", t="2026-09-01T11:00:00Z", tier="acute", score=3
    ))
    work = Recorder()
    result = asyncio.run(
        scheduler(registry, tmp_path, ["vidit", "asha"], work=work).tick()
    )
    assert work.ran == ["asha"]
    assert result.suspended == ("vidit",)
    assert instant(registry.schedule_record("vidit")[NEXT_PASS_AT]) > NOON


def test_a_hibernating_main_costs_one_hydration_and_no_write(registry, tmp_path):
    """Matrix: *hibernating main*. An idle main costs nothing.

    The previous version asserted ``len(hydrated) <= capacity``, which
    ``_evict_if_needed`` guarantees whatever the tick does — a test that could
    not fail. What is actually claimed is that a main who is not due produces no
    append and no work: the cost of being idle is a fold read and a dict lookup,
    which is what makes hibernation a shipped behaviour rather than a hope.
    """
    for main_id in ("vidit", "a", "b"):
        set_due(registry, main_id, NOON + 86_400)
    before = {m: registry.schedule_record(m)[NEXT_PASS_AT] for m in ("vidit", "a", "b")}

    work = Recorder()
    result = asyncio.run(
        scheduler(registry, tmp_path, ["vidit", "a", "b"], work=work).tick()
    )
    assert result.touched == 0 and result.quiet is True
    after = {m: registry.schedule_record(m)[NEXT_PASS_AT] for m in ("vidit", "a", "b")}
    assert after == before, "an idle main was written to"


def test_a_repeated_main_id_does_not_run_one_main_twice(registry, tmp_path):
    """A typo in ``HALF_MAINS`` is two writers on one log by the shortest
    possible route: the same id twice in the list ran that main's pass twice,
    concurrently."""
    set_due(registry, "vidit", NOON - 60)
    work = Recorder()
    sch = scheduler(registry, tmp_path, ["vidit", "vidit", "vidit"], work=work)
    assert tuple(sch.mains) == ("vidit",)
    assert asyncio.run(sch.tick()).ran == ("vidit",)
    assert work.ran == ["vidit"]


# ── acceptance: reachable in the shipped product ─────────────────────────────


def test_the_scheduler_is_wired_into_the_shipped_composition(tmp_path):
    """*"The tick runs in the shipped composition, not only in tests."*

    Three stories shipped a surface reachable only from a test before the
    composition root existed; this is the assertion that says the scheduler is
    not the fourth. **The shipped numbers are checked here**, on the object the
    product actually builds — not on one a test constructed with its own.

    The clock is swapped before the tick so this case does not write real due
    times into a temporary tree off the wall clock, which the module docstring
    forbids and the first version of this did.

    **The pass is asserted by value, not by keyword** (story 9c). Until then
    ``work`` was ``Nothing`` and this case said so; now it must be the
    consolidation pass holding *this* wiring's registry. An ``isinstance``
    check would pass for a ``TensionPass`` wired to somebody else's registry or
    to none at all, and a keyword search of the source would pass for one that
    was constructed and thrown away.
    """
    from half.__main__ import build
    from half.consolidate.pass_ import TensionPass
    from half.config import MAINS_ENV, ROOT_ENV, load

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit,456:asha"})
    wiring = build(config, token="123:fake")
    try:
        assert isinstance(wiring.scheduler, Scheduler)
        assert set(wiring.scheduler.mains) == {"vidit", "asha"}
        assert wiring.scheduler.root == tmp_path
        assert not isinstance(wiring.scheduler.work, Nothing)
        # Story 10: the work is the morning pass, holding *this* wiring's
        # consolidation pass and *this* wiring's surface — which in turn holds
        # this registry and this channel. Compared by value all the way down,
        # because an ``isinstance`` check passes for a surface wired to
        # somebody else's registry, to somebody else's channel, or to neither.
        from half.questions.engine import QuestionEngine
        from half.surface.morning import MorningPass, MorningSurface

        # Story 11: the surface also holds *this* wiring's question engine,
        # compared by value for the reason everything else here is — a surface
        # wired with ``questions=None`` never asks anything, which is exactly
        # the state story 5b shipped in and which this equality now forbids.
        # Story 11, review loop 1: the morning surface is **not** an asker and
        # has no field for an engine. Delivery is the runtime's — the wiring
        # carries the engine on ``Wiring.questions``, asserted below by value.
        assert wiring.scheduler.work == MorningPass(
            consolidate=TensionPass(ledger=wiring.registry),
            surface=MorningSurface(
                ledger=wiring.registry, channel=wiring.channel
            ),
        )
        assert wiring.questions == QuestionEngine(ledger=wiring.registry)
        assert isinstance(wiring.scheduler.clock, SystemClock)
        assert wiring.scheduler.bound == DEFAULT_BOUND
        assert wiring.scheduler.timeout == DEFAULT_TIMEOUT
        assert wiring.scheduler.grace == GRACE_SECONDS

        wiring.scheduler.clock = FrozenClock(at=NOON)
        assert asyncio.run(wiring.scheduler.tick()).scheduled == ("vidit", "asha")
    finally:
        wiring.registry.close()


@pytest.mark.ad9_guarantee
def test_serve_actually_fires_the_tick_beside_the_inbound_loop(monkeypatch, tmp_path):
    """*"The tick runs in the shipped composition"* — **run, not grepped.**

    This was ``assert "scheduler.run_forever" in inspect.getsource(serve)``,
    which is green with ``ticker.cancel()`` inserted on the next line. So the
    real ``serve`` body runs here, against a fake inbound loop that waits for
    the scheduler to do something, and the assertion is that a pass actually
    ran.
    """
    from half import __main__ as entrypoint
    from half.config import MAINS_ENV, ROOT_ENV, load

    fired = asyncio.Event()

    class Fired:
        def __init__(self):
            self.ran: list[str] = []

        async def run(self, main_id, now):
            self.ran.append(main_id)
            fired.set()

    class FakeRuntime:
        def __init__(self, *, channel, registry, second=None, questions=None,
                     corrections=None):
            self.registry = registry
            self.second = second
            self.questions = questions
            self.corrections = corrections

        async def run(self):
            await fired.wait()

    work = Fired()
    real_build = entrypoint.build

    def build(config, token):
        wiring = real_build(config, token)
        wiring.scheduler.clock = FrozenClock(at=NOON)
        wiring.scheduler.work = work
        return wiring

    monkeypatch.setattr(entrypoint, "build", build)
    monkeypatch.setattr(entrypoint, "Runtime", FakeRuntime)

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    # Due already, so the very first tick runs the pass.
    reg = ActorRegistry(tmp_path)
    set_due(reg, "vidit", NOON - 60)
    reg.close()

    asyncio.run(asyncio.wait_for(entrypoint.serve(config, "123:fake"), timeout=10))
    assert work.ran == ["vidit"], "serve never fired a tick"


def test_the_default_pass_sends_nothing(registry, tmp_path):
    """*"No unprompted message to a main"* — this story must not be the place
    that decides to contact someone. What ships today runs ``Nothing``."""
    set_due(registry, "vidit", NOON - 60)
    result = asyncio.run(
        scheduler(registry, tmp_path, ["vidit"], work=Nothing()).tick()
    )
    assert result.ran == ("vidit",) and result.failed == ()


@pytest.mark.one_clock
def test_the_scheduler_cannot_reach_a_model_a_network_or_a_channel():
    """*"Only the standard library and pinned SDKs; no network, no model."*

    ``half.channel`` is in the list for the spec's **Never**: this story must
    not be the place that decides to contact someone. A scheduler that can
    import a channel is one refactor away from being the messaging path, and
    the import is the structural version of the rule.
    """
    forbidden = {"anthropic", "openai", "httpx", "requests", "urllib", "http",
                 "socket", "random", "telegram"}
    for path in sorted((ROOT / "half" / "schedule").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module)
        assert not roots & forbidden, f"{path.name} imports {sorted(roots & forbidden)}"
        reaching = {r for r in roots if r.startswith("half.channel")}
        assert not reaching, (
            f"{path.name} reaches {sorted(reaching)}; story 9a must not be "
            f"where a message to a main is decided (story 10)"
        )
