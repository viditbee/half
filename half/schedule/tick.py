"""The file-locked drain: what is due runs, bounded, isolated, at most once
(AD-1, AD-9, AD-27).

Ported in shape from hermes-agent's ``cron/scheduler.py`` (MIT, © 2025 Nous
Research): a ``tick()`` guarded by a non-blocking file lock, so an in-process
ticker and a standalone worker cannot drain the same queue. What is *not*
ported is everything hermes needs and Half must not have — a cron expression, a
catch-up path, a retry ladder, a failure-streak nudge back to the operator. Half
has one schedule shape and one answer for a window that was missed.

Four rules, and each of them is one the obvious implementation breaks.

**A missed window sends nothing.** The natural implementation of a scheduler
that was down is to catch up. For a product whose output is unprompted messages
to a person, catching up means a queue of yesterday's thoughts arriving at once
— and after a long outage, a storm. So a due time older than ``GRACE_SECONDS``
is not run: it is computed forward, silently, and the pass that did not happen
did not happen. This is the module that has to resist implementing the helpful
version.

**The tick is file-locked.** Two processes must not drain the same queue, and
the single-writer-per-main invariant has to survive a second worker (AD-1).
``flock`` is the whole mechanism, and it is chosen for the property a lease
table would have to reimplement badly: the kernel releases it when the holder
dies, so a worker killed mid-tick leaves nothing to clean up and no stall for a
human to notice.

**Concurrency is bounded, and one main cannot reach another.** A thousand due
mains must not become a thousand concurrent passes, so the drain runs under a
semaphore. Every main's work is wrapped in its own timeout and its own
exception handler: one main's pass raising, or never returning, costs that main
their pass and nothing else. The tick still completes.

**Nothing here decides to contact anybody.** The pass body is a later story and
arrives as an injected ``Pass``; the default one does nothing at all, because a
tick with nothing to say is normal and silent rather than an error (AD-27).
This module runs the pass — it is not the pass, and it must never become the
place that decides to message a main (story 10).

The single clock read happens once, at the top of ``tick``, and is handed to
everything below as a ``Now`` (AD-30).

**Operational notes, written down because they are not enforceable from here.**

*Do not put this behind a proxy that scales to zero on inbound idleness.* A
scale-to-zero front end judges liveness by connections arriving, and a pass is
by definition work nobody asked for — so the proxy sees an idle service and
suspends the process mid-drain. The visible symptom is the worst one this module
has: a due time already advanced (at-most-once, by design) and a pass that never
ran, indistinguishable from a quiet night. hermes-agent hit this and documented
it in ``gateway/scale_to_zero.py``; it is recorded in the extraction manifest as
a deployment fact rather than a thing to port.

*Size a worker by ``ceil(mains / bound) x timeout`` against ``GRACE_SECONDS``.*
A tick that runs longer than the grace window classifies as *missed* everybody
who came due while it ran, and looks perfectly healthy doing it. At the shipped
numbers that ceiling is 96 mains per worker, which
``tests/test_schedule.py`` asserts so that changing a constant moves the number
deliberately.

*The tick shares an event loop with the inbound path.* Opening and ``flock``ing
the lock file is non-blocking by construction (``LOCK_NB`` never waits), and a
fold read is local disk; the genuinely unbounded wait — a turn holding a main's
mutex — is an ``await`` under a timeout rather than a blocked thread. A pass
that does real CPU work will still stall the loop, and belongs behind
``asyncio.to_thread`` when story 9b writes one.

*A clock that jumps.* A forward jump past the grace window reads as a missed
window, which is the honest answer. A backward jump leaves due times in the
future until the clock catches up, and the stamps written on either side are not
monotonic — the log is ordered by append, not by ``t``, so nothing downstream
depends on that.

*Windows.* The ``msvcrt`` branch is written for parity and is not exercised by
CI, which runs on Linux and macOS.
"""

from __future__ import annotations

import asyncio
import errno
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Protocol

from half import civil
from half.errors import ScheduleError
from half.schedule import due as due_module
from half.schedule.clock import Clock, Now, SystemClock

# ``fcntl`` is POSIX; Windows has ``msvcrt``. One of the two is present on any
# platform this runs on, and the absence of both is fatal rather than degraded:
# a tick that silently ran without a lock is worse than one that refuses.
try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover - platform dependent
    fcntl = None  # type: ignore[assignment]
try:  # pragma: no cover - platform dependent
    import msvcrt
except ImportError:  # pragma: no cover - platform dependent
    msvcrt = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

#: How many mains may be mid-pass at once. **Explicit, and an Ask-First number
#: in story 9a**: it is the difference between a busy worker and a thousand
#: concurrent passes. Small, because a pass is not cheap and because a hosted
#: node owns a named group of humans rather than a percentage of requests
#: (AD-15) — falling behind is recoverable, falling over is not.
DEFAULT_BOUND: Final[int] = 8

#: How long one main's work may take before it is cancelled. The tick must not
#: be held for ever by a pass that does not return, and an unbounded wait is
#: how one main's hang becomes every main's outage.
DEFAULT_TIMEOUT: Final[float] = 300.0

#: How late a due time may be and still run. Wider than the tick interval, so
#: an ordinary tick that lands a few seconds after a due time still runs it;
#: far narrower than a night, so a window genuinely missed is genuinely missed.
#:
#: **This is where "no catch-up" is actually implemented.** Without it, a
#: process down for a week would find every main due and run every one of them
#: on the first tick after it came back.
GRACE_SECONDS: Final[float] = 3_600.0

#: How often ``run_forever`` ticks. Well under ``GRACE_SECONDS``, so a due time
#: cannot fall between two ticks and be read as missed.
TICK_SECONDS: Final[float] = 60.0

#: The lock file, in the root that holds every main. One per tree, because the
#: thing being excluded is *a second drain of this queue*, not a second write to
#: one main — that is the actor's mutex, and it still applies inside the lock.
LOCK_NAME: Final[str] = ".tick.lock"


class Pass(Protocol):
    """One main's scheduled work.

    Takes the tick's injected instant and never reads a clock of its own, which
    is what keeps everything below this module replayable (AD-30).
    """

    async def run(self, main_id: str, now: Now) -> None:
        ...


@dataclass(frozen=True, slots=True)
class Nothing:
    """The default pass: it does nothing, and that is a result (AD-27).

    The consolidation pass is a later story and the model port is another. What
    this story delivers is the thing that *runs* them, wired into the shipped
    composition so it is a surface somebody has actually run rather than one a
    test reaches. Until a pass exists, every tick drains the queue, advances
    every due time, and sends nothing — which is precisely what a day with
    nothing worth saying looks like anyway.
    """

    async def run(self, main_id: str, now: Now) -> None:
        return None


class Registry(Protocol):
    """The three doors the scheduler needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry`` because that is the
    whole dependency: two narrowed reads and one write that goes through the
    per-main mutex. Nothing here opens a store, and that is deliberate — a
    scheduler with its own path to the log would be a second writer, and the
    single writer is what lets the store skip a journal (AD-1).
    """

    def schedule_record(self, main_id: str) -> Mapping[str, Any] | None:
        ...

    def zone_records(self, main_id: str) -> Sequence[Mapping[str, Any]]:
        ...

    def crisis_open(self, main_id: str) -> bool:
        ...

    async def note_pass(
        self, main_id: str, *, t: str, fields: Mapping[str, Any]
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class TickResult:
    """What one tick did. Counts and ids only — never content (AD-22).

    ``held`` is not a failure. A tick that found the lock taken did the right
    thing by doing nothing, and a tick with nothing due is normal and silent.
    """

    #: The instant this tick read, or ``None`` when the lock was held — a tick
    #: that does nothing does not even read a clock.
    at: str | None = None
    #: Mains whose work ran to completion.
    ran: tuple[str, ...] = ()
    #: Mains who had no due time at all and were given one. Nothing was run.
    scheduled: tuple[str, ...] = ()
    #: Mains whose due time was older than the grace window. **Nothing was
    #: sent**; their next due time was computed forward.
    missed: tuple[str, ...] = ()
    #: Mains whose work raised. Logged without content; the tick continued.
    failed: tuple[str, ...] = ()
    #: Mains whose work did not return inside the timeout and was cancelled.
    timed_out: tuple[str, ...] = ()
    #: Mains who were due but are in crisis mode (CAP-12). Their due time was
    #: advanced; **their pass did not run.** The mode suspends Half's ordinary
    #: behaviour, and a nightly pass is ordinary behaviour.
    suspended: tuple[str, ...] = ()
    #: Mains whose next due time could not be recorded. **Their pass did not
    #: run** — see ``_advance``.
    unrecorded: tuple[str, ...] = ()
    #: Mains scheduled in the recorded fallback zone rather than one they told
    #: Half. Surfaced here so that *"visible as a fallback"* is visible to code
    #: and to an operator, and not only to somebody reading raw JSONL.
    on_fallback: tuple[str, ...] = ()
    #: True when another worker held the lock and this tick did nothing.
    held: bool = False

    @property
    def touched(self) -> int:
        return len(self.ran) + len(self.failed) + len(self.timed_out)

    @property
    def quiet(self) -> bool:
        """True when this tick changed nothing at all.

        A permanently stalled queue and a night when nobody is due look
        identical from outside, which is the failure the reference
        implementation shipped: a healthy-looking tick of zero jobs while no job
        ever ran again. ``run_forever`` reads this to decide what to say.
        """
        return not (self.touched or self.scheduled or self.missed
                    or self.suspended or self.unrecorded)


@dataclass(slots=True)
class Scheduler:
    """The due-time queue for one worker's mains.

    ``mains`` is supplied rather than discovered, following ``half.config``:
    who exists is deployment shape, and a scheduler that enumerated directories
    would run a pass for a tree somebody restored into the root by hand.
    """

    registry: Registry
    mains: Sequence[str]
    root: Path
    work: Pass = field(default_factory=Nothing)
    #: The one clock. Injected so that every test in this suite drives real
    #: scheduling decisions at chosen instants instead of patching a module.
    clock: Clock = field(default_factory=SystemClock)
    bound: int = DEFAULT_BOUND
    timeout: float = DEFAULT_TIMEOUT
    grace: float = GRACE_SECONDS

    def __post_init__(self) -> None:
        if self.bound < 1:
            raise ValueError("the concurrency bound must be at least one")
        if self.timeout <= 0:
            raise ValueError("the per-main timeout must be positive")
        if self.grace <= 0:
            # Zero is not "no grace"; it is a queue in which nothing is ever on
            # time, because a due time is only ever reached at or after itself.
            raise ValueError("the grace window must be positive")
        # Deduplicated, order preserved. A repeated id ran one main's pass twice
        # concurrently — two writers on one log by the shortest possible route,
        # a typo in HALF_MAINS.
        self.mains = tuple(dict.fromkeys(self.mains))
        self.root = Path(self.root)

    # -- one tick ------------------------------------------------------------

    async def tick(self) -> TickResult:
        """Drain what is due. Returns what happened; raises for nothing normal.

        Everything about the shape here is about isolation. The clock is read
        once, inside the lock, so every main in this tick is judged against the
        same instant. Each main's decision is taken from their own log. Each
        main's work runs in its own task, under its own timeout, and the
        gather collects exceptions rather than propagating the first one.
        """
        with _lock(self.root / LOCK_NAME) as acquired:
            if not acquired:
                # Not an error, and deliberately not a warning: overlapping
                # ticks are the normal state of a worker whose in-process
                # ticker and an operator's manual run coincide.
                logger.debug("tick skipped: another worker holds %s", LOCK_NAME)
                return TickResult(held=True)

            now = self.clock.read()
            unscheduled: list[str] = []
            missed: list[str] = []
            runnable: list[str] = []
            suspended: list[str] = []

            for main_id in self.mains:
                try:
                    verdict = self._verdict(main_id, now)
                except Exception as exc:
                    # A main whose store cannot be read costs that main their
                    # pass. The tick continues — one main is never allowed to
                    # end the drain for the rest.
                    #
                    # The *type* and nothing else (AD-22). A traceback carries
                    # the frames' locals into the log line on some handlers, and
                    # an exception message routinely quotes the value that
                    # caused it — which here is a record out of a main's own
                    # ledger.
                    logger.error(
                        "scheduling decision failed for main=%s (%s); continuing",
                        main_id, type(exc).__name__,
                    )
                    continue
                if verdict is _DUE:
                    runnable.append(main_id)
                elif verdict is _SUSPENDED:
                    suspended.append(main_id)
                elif verdict is _MISSED:
                    missed.append(main_id)
                elif verdict is _UNSCHEDULED:
                    unscheduled.append(main_id)

            # Every main whose due time has passed gets a new one, whether their
            # pass runs or not. Done before the work, so a crash mid-pass loses
            # that pass rather than repeating it — at-most-once, which is the
            # only semantics compatible with "a missed window sends nothing".
            #
            # Under the same bound as the drain, and concurrently. Sequentially
            # this is the first-boot shape — every main unscheduled at once —
            # and each advance may wait on a turn's mutex up to ``timeout``, so
            # a serial loop is ``n x timeout`` inside the file lock. That is the
            # tick outrunning its own grace window through the path that does
            # no work at all.
            advanced = await self._advance_all(unscheduled + missed + suspended, now)
            fallback = [m for m, due in advanced.items() if due is not None
                        and not due.told]
            unrecorded = [m for m, due in advanced.items() if due is None]

            ran, failed, timed_out, blocked, defaulted = await self._drain(
                runnable, now
            )
            result = TickResult(
                at=now.stamp,
                ran=tuple(ran),
                scheduled=tuple(m for m in unscheduled if m not in unrecorded),
                missed=tuple(m for m in missed if m not in unrecorded),
                failed=tuple(failed),
                timed_out=tuple(timed_out),
                suspended=tuple(m for m in suspended if m not in unrecorded),
                unrecorded=tuple(unrecorded + blocked),
                on_fallback=tuple(fallback + defaulted),
            )
            if result.unrecorded:
                logger.warning(
                    "could not record a next due time for %d main(s); their "
                    "passes did not run", len(result.unrecorded),
                )
            return result

    async def run_forever(self, *, interval: float = TICK_SECONDS) -> None:
        """Tick until cancelled. Nothing one *tick* does can end the loop.

        **A configuration fault is not a tick failure.** ``_lock`` raises
        ``ScheduleError`` when the platform offers no file locking at all, and
        swallowing that turns *"a tick without a lock breaks AD-1"* into an
        infinite loop logging once a minute while nobody is ever scheduled. It
        propagates, and ``serve``'s task group takes the process down with it.

        **A quiet tick is reported.** A stalled queue and a night when nobody is
        due are indistinguishable from outside unless something says so, which
        is the failure the reference implementation shipped: a healthy-looking
        tick of zero jobs while no job ever ran again. Ordinary quiet is a debug
        line; a run of ticks that were all *held* by another worker escalates to
        a warning, because that is what a wedged lock looks like from in here.
        """
        held_in_a_row = 0
        while True:
            try:
                result = await self.tick()
            except asyncio.CancelledError:
                raise  # shutdown is not a tick failure
            except ScheduleError:
                raise  # a queue that cannot be locked must not look healthy
            except Exception as exc:
                logger.error(
                    "tick failed (%s); the scheduler continues",
                    type(exc).__name__,
                )
            else:
                held_in_a_row = held_in_a_row + 1 if result.held else 0
                if held_in_a_row and held_in_a_row % _HELD_RUN_WARNING == 0:
                    logger.warning(
                        "%d consecutive ticks found the lock held; the queue "
                        "may be wedged", held_in_a_row,
                    )
                elif result.quiet:
                    logger.debug("tick at %s: nothing due", result.at)
                else:
                    logger.info(
                        "tick at %s: ran=%d scheduled=%d missed=%d suspended=%d "
                        "failed=%d timed_out=%d unrecorded=%d",
                        result.at, len(result.ran), len(result.scheduled),
                        len(result.missed), len(result.suspended),
                        len(result.failed), len(result.timed_out),
                        len(result.unrecorded),
                    )
            await asyncio.sleep(interval)

    # -- the decision --------------------------------------------------------

    def _verdict(self, main_id: str, now: Now) -> str:
        """What this tick should do about ``main_id``. Pure, given ``now``.

        Five answers, and the four that are not *run* all send nothing:

        * never scheduled (a new main, a restored tree, or a due time this
          build cannot read) — record one, run nothing;
        * due in the future — nothing at all, which is what most mains are on
          most ticks and costs a hydration and a dict lookup;
        * due, but the main is in crisis mode — advance and **do not run**. The
          mode suspends Half's ordinary behaviour (CAP-12) and a nightly pass is
          ordinary behaviour. It costs nothing today, because the pass is
          ``Nothing``; story 9b hangs real work here, and the branch has to
          exist before the work does rather than after;
        * due, within the grace window — run;
        * due, past the grace window — **missed**: compute forward, send
          nothing, and never mind how many windows went by.
        """
        record = self.registry.schedule_record(main_id)
        at = civil.instant(_next_pass_at(record))
        if at is None:
            return _UNSCHEDULED
        if at > now.epoch:
            return _NOT_DUE
        if now.epoch - at > self.grace:
            return _MISSED
        if self.registry.crisis_open(main_id):
            return _SUSPENDED
        return _DUE

    def due_for(self, main_id: str, now: Now) -> due_module.Due:
        """When ``main_id`` is next due after ``now``, in the zone they told.

        The zone is read through the registry's narrowed door and asked of the
        ladder, so an unconfirmed guess cannot select a due time and no signal
        is consulted to make one up. A main who has told Half nothing gets the
        recorded fallback — visible as a fallback in the record this produces,
        and in this tick's result.
        """
        zone = due_module.zone_of(self.registry.zone_records(main_id))
        return due_module.next_pass_at(
            main_id=main_id, after=now.epoch, zone=zone
        )

    async def _advance(self, main_id: str, now: Now) -> due_module.Due | None:
        """Record ``main_id``'s next due time, or ``None`` if it could not be.

        **``None`` stops the pass**, and that is the whole reason this returns
        anything. Swallowing the failure and running the work anyway leaves the
        old due time in the log, so the same window comes back due on the next
        tick, and the next: at a sixty-second interval inside an hour of grace
        that is up to sixty passes for one night — the exact storm the missed
        window rule exists to prevent, arriving through the error path instead
        of the happy one. A pass whose "already ran" marker could not be written
        has not earned the right to run.

        Bounded, because it goes through ``registry.acquire`` and a turn may
        hold that main's mutex. An unbounded wait here would hold a semaphore
        slot, the tick and the file lock for as long as one turn took.
        """
        try:
            due = self.due_for(main_id, now)
            await asyncio.wait_for(
                self.registry.note_pass(
                    main_id, t=now.stamp, fields=due_module.scheduled(due)
                ),
                timeout=self.timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "could not record the next due time for main=%s (%s); its pass "
                "will not run and it will be recomputed on a later tick",
                main_id, type(exc).__name__,
            )
            return None
        return due

    async def _advance_all(
        self, mains: Sequence[str], now: Now
    ) -> dict[str, due_module.Due | None]:
        """Advance every main in ``mains`` under the concurrency bound.

        Order-preserving in the result, so the tick's own report reads in the
        order the mains were configured rather than in completion order.
        """
        if not mains:
            return {}
        gate = asyncio.Semaphore(self.bound)

        async def one(main_id: str) -> due_module.Due | None:
            async with gate:
                return await self._advance(main_id, now)

        outcomes = await asyncio.gather(*(one(main_id) for main_id in mains))
        return dict(zip(mains, outcomes))

    # -- the drain -----------------------------------------------------------

    async def _drain(
        self, runnable: Sequence[str], now: Now
    ) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
        """Run every due main's work under the bound, isolated from each other."""
        if not runnable:
            # A tick with nothing due is normal and silent (AD-27).
            return [], [], [], [], []

        gate = asyncio.Semaphore(self.bound)
        blocked: list[str] = []
        defaulted: list[str] = []

        async def one(main_id: str) -> None:
            async with gate:
                # Advanced inside the gate and before the work, so the durable
                # "already ran" marker exists before anything can fail — and if
                # it could not be written, the work does not run at all.
                due = await self._advance(main_id, now)
                if due is None:
                    blocked.append(main_id)
                    return
                if not due.told:
                    defaulted.append(main_id)
                await asyncio.wait_for(
                    self.work.run(main_id, now), timeout=self.timeout
                )

        outcomes = await asyncio.gather(
            *(one(main_id) for main_id in runnable), return_exceptions=True
        )

        ran: list[str] = []
        failed: list[str] = []
        timed_out: list[str] = []
        for main_id, outcome in zip(runnable, outcomes):
            if main_id in blocked:
                continue
            if outcome is None:
                ran.append(main_id)
            elif isinstance(outcome, asyncio.CancelledError):
                # The whole tick is being torn down; do not swallow it.
                raise outcome
            elif isinstance(outcome, (asyncio.TimeoutError, TimeoutError)):
                timed_out.append(main_id)
                logger.warning(
                    "pass for main=%s did not return within %ss and was "
                    "cancelled; the tick continues", main_id, self.timeout,
                )
            else:
                failed.append(main_id)
                logger.error(
                    "pass for main=%s raised %s; the tick continues",
                    main_id, type(outcome).__name__,
                )
        return ran, failed, timed_out, blocked, defaulted


#: The five verdicts. Strings rather than an enum because they are private to
#: this module and never stored; named rather than inlined so a branch cannot be
#: added by writing a different literal.
_DUE: Final[str] = "due"
_NOT_DUE: Final[str] = "not-due"
_MISSED: Final[str] = "missed"
_UNSCHEDULED: Final[str] = "unscheduled"
_SUSPENDED: Final[str] = "suspended"

#: How many consecutive held ticks before the lock is reported as suspicious.
#: Ten minutes at the default interval: long enough that an overlapping manual
#: run is not noise, short enough that a wedged queue is noticed the same
#: morning.
_HELD_RUN_WARNING: Final[int] = 10


def _next_pass_at(record: Mapping[str, Any] | None) -> object:
    if not isinstance(record, Mapping):
        return None
    return record.get(due_module.NEXT_PASS_AT)


@contextmanager
def _lock(path: Path) -> Iterator[bool]:
    """Hold ``path`` exclusively for the block, or yield ``False``.

    **Contention is the only thing swallowed.** Every other ``OSError`` — most
    importantly the descriptor exhaustion that makes every open fail — is
    raised, because the alternative is the failure hermes hit and documented: a
    scheduler that reported a healthy tick of zero jobs while no job ever ran
    again.

    The lock is an open file description, so the kernel drops it when the
    holder exits by any route, crash included. That is what makes a stale lock
    recoverable with no manual action and no timeout to tune — the failure mode
    a lease row in a table has and this does not.
    """
    if fcntl is None and msvcrt is None:  # pragma: no cover - platform dependent
        raise ScheduleError(
            "no file locking is available on this platform; a tick without a "
            "lock lets two workers drain one queue, which breaks the single "
            "writer per main (AD-1)"
        )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = None
    try:
        handle = open(path, "w", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:  # pragma: no cover - platform dependent
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if handle is not None and _is_contention(exc):
            handle.close()
            yield False
            return
        if handle is not None:
            handle.close()
        raise

    try:
        yield True
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
            else:  # pragma: no cover - platform dependent
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            # The descriptor is about to close, which releases it anyway.
            pass
        handle.close()


#: The errnos that mean *somebody else holds it*, and nothing else. Named
#: rather than caught as a bare ``OSError``, because the difference between "a
#: tick is already running" and "this process is out of file descriptors" is
#: the difference between healthy and silently stalled — and the second one
#: looked exactly like the first in the reference implementation until it was
#: found the hard way.
_CONTENTION: Final[frozenset[int]] = frozenset(
    {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK}
)


def _is_contention(exc: OSError) -> bool:
    return exc.errno in _CONTENTION
