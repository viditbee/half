"""One actor per main: an inbox plus a mutex (AD-8).

An actor is not a process and not a task. It is a lock and a hydrated store,
keyed by ``main_id``. One worker holds many; a dormant one is a dict entry
costing nothing, and hibernation is simply eviction from the LRU.

Two invariants the registry exists to hold:

*Single writer* (AD-1). Every mutation for a main passes through that main's
mutex, so an append never races another. This is the decision that lets the
store skip a journal, precondition hashes and rollback.

*Eviction never interrupts a turn* (AD-33). Eviction requires a free mutex.
Dropping an actor mid-turn would lose an in-flight reply, or worse, evict
between a model call and its log append and lose work already paid for.
"""

from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from collections.abc import Mapping
from pathlib import Path
from typing import Any, AsyncIterator

from half.errors import StoreError
from half.governance.ladder import TOP, Ceiling, License, ceiling_fields
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import RetrievalSwitch
from half.retrieval.strands import Strands
from half.store.ops import CRISIS_ENTERED, CRISIS_REVERSED, Op
from half.store.store import Store

#: A main_id becomes a directory name, so it is validated before it can reach
#: the filesystem. It arrives from configuration, which is operator input, and
#: an unvalidated '..' walks the store tree straight out of its root.
_SAFE_MAIN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def validate_main_id(main_id: str) -> str:
    if not _SAFE_MAIN_ID.fullmatch(main_id):
        raise StoreError(
            f"unsafe main_id {main_id!r}: letters, digits, dash and underscore only"
        )
    return main_id

def mode_is_open(record: Mapping[str, Any] | None) -> bool:
    """Whether a folded ``crisis`` record leaves the mode open.

    The one reader of that field's shape, so the fold, the registry and the
    gate cannot disagree about what "in the mode" means. Named apart from
    ``ActorRegistry.crisis_open`` on purpose: that one reaches a main's store,
    this one reads a record somebody already has. Fail-closed on
    anything unreadable: a record this build cannot parse is treated as an
    *open* mode, because the cost of reading an open mode as closed is
    answering a main in crisis through the ordinary pipeline.
    """
    if record is None:
        return False
    if not isinstance(record, Mapping):
        return True
    return record.get("state") != CRISIS_REVERSED


#: How many hydrated actors a worker holds before evicting the least recent.
DEFAULT_CAPACITY = 256


@dataclass(slots=True)
class Actor:
    """One main's hydrated state."""

    main_id: str
    store: Store
    #: What this main's conversation is currently about, as weights (CAP-1).
    #: Volatile by AD-26: never logged, never projected, and gone when the
    #: actor is evicted — which is correct, because how the main is right now
    #: is not a belief. A restart begins with no strand weighted, and the
    #: floor in ``strand_weight`` means that costs reach, not results.
    strands: Strands = field(default_factory=Strands)
    #: Whether ledger retrieval is permitted for *this main* (CAP-12). One
    #: switch per actor, not per worker: a single shared switch meant one
    #: main's crisis disabled retrieval for every other main the process was
    #: serving, which is a silent, total memory outage for uninvolved people.
    #:
    #: **Hydrated, not defaulted.** The switch used to be born enabled on every
    #: hydration, so an eviction under memory pressure re-enabled the retrieval
    #: a crisis had "hard-disabled" — the same defect the ceiling had before it
    #: was moved into the log, one field over. It is now read from the crisis
    #: record at hydration, which is what makes *hard* mean hard.
    retrieval: RetrievalSwitch = field(default_factory=RetrievalSwitch)
    #: The one global license cap for *this main* (AD-28). Beside ``strands``
    #: and ``retrieval`` for the same reason both are here: it is per main, so
    #: one main's aftercare cannot cap another's, and it belongs to the actor
    #: that owns them rather than to the worker that happens to host both.
    #:
    #: **Unlike those two, it is not volatile.** ``strands`` and ``retrieval``
    #: are how the main is right now and may be lost on eviction (AD-26); a
    #: ceiling is a governance decision that runs for thirty days, and eviction
    #: is routine at any real capacity. So this field is *hydrated from the
    #: store*, and every change to it goes through ``ActorRegistry`` and into
    #: the log. Assigning it directly would neither persist nor survive the next
    #: rehydration, which is why nothing outside the registry does.
    ceiling: Ceiling = field(default_factory=Ceiling)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: Turns holding *or waiting for* the lock. Incremented before the acquire
    #: and decremented after the release, so it is never zero while any turn
    #: still needs this actor.
    claims: int = 0

    @property
    def busy(self) -> bool:
        """True while any turn holds or awaits this actor.

        ``lock.locked()`` alone is not enough, and the gap is not theoretical:
        ``asyncio.Lock.release()`` clears its flag and merely *schedules* the
        next waiter, which sets it again only when it resumes. An actor evicted
        in that window has its store closed under a turn that is about to run,
        and the next acquire hydrates a second Actor with a second lock for the
        same main — two writers on one belief log, which is the exact race the
        store skips a journal and rollback for (AD-1).
        """
        return self.claims > 0 or self.lock.locked()


class ActorRegistry:
    """Hydrates, serializes and evicts actors."""

    def __init__(self, root: Path | str, *, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.root = Path(root)
        self.capacity = capacity
        self._actors: "OrderedDict[str, Actor]" = OrderedDict()

    # -- lifecycle -----------------------------------------------------------

    def _hydrate(self, main_id: str) -> Actor:
        """Open a main's store. Cheap — SQLite open plus a snapshot read, which
        the work that follows dwarfs.

        The ceiling is read here, from the store, and that is what makes AD-28
        survive eviction: an actor dropped under memory pressure and rehydrated
        five minutes later comes back capped, because the cap was never in
        memory in the first place. A ``Ceiling`` parses its own value
        fail-closed, so a rung this build cannot read caps at `behave` rather
        than reading as absent.

        That read makes hydration eager where it used to be lazy — a corrupt
        log now surfaces here rather than at the first turn. Deliberate, and
        the cheaper of the two: it is one snapshot read that the turn was going
        to do anyway, and it happens inside the per-message isolation in
        ``Runtime.run``, so the failure domain is unchanged. Deferring it would
        mean a window in which a capped main reads as uncapped.
        """
        validate_main_id(main_id)
        # The prefix builder is handed to the store here rather than imported
        # by it: ``half.store`` may not depend on ``half.retrieval``. Wiring it
        # at hydration is what makes prefix hits work in the running product
        # and not only where a test remembers to pass it.
        store = Store(self.root / main_id, prefix=build_prefix)
        state = store.state()
        actor = Actor(
            main_id=main_id,
            store=store,
            ceiling=Ceiling(state.ceiling),
            # Both durable halves of a crisis suspension come back together
            # (CAP-12). A main in the mode rehydrates with retrieval already
            # off, so there is no window — not one turn, not one line — in
            # which an evicted main reads as uncapped or as retrievable.
            retrieval=RetrievalSwitch(enabled=not mode_is_open(state.crisis)),
        )
        self._actors[main_id] = actor
        return actor

    def _reached(self, main_id: str) -> Actor:
        """This main's actor, hydrating it and marking it recently used.

        Every door into the registry goes through here. An accessor that
        hydrates without touching the LRU leaves an actor looking cold the
        moment it was needed — and one that skips the capacity check lets the
        registry grow past it for as long as nobody takes a turn.
        """
        actor = self._actors.get(main_id)
        if actor is None:
            actor = self._hydrate(main_id)
        self._actors.move_to_end(main_id)
        return actor

    def _evict_if_needed(self) -> None:
        """Drop least-recently-used actors that no turn holds or awaits.

        A busy actor is skipped rather than waited on: eviction is an
        optimisation, and blocking on it would turn memory pressure into a
        stall on the very actor doing work.
        """
        while len(self._actors) > self.capacity:
            for main_id, actor in list(self._actors.items()):
                if not actor.busy:
                    self._actors.pop(main_id, None)
                    actor.store.close()
                    break
            else:
                return  # every actor is claimed; try again after one finishes

    @asynccontextmanager
    async def acquire(self, main_id: str) -> AsyncIterator[Actor]:
        """Hold ``main_id``'s actor exclusively for the duration of the block."""
        actor = self._reached(main_id)

        # Claimed before awaiting the lock, so this actor cannot be evicted
        # while this turn is merely queued behind another.
        actor.claims += 1
        try:
            async with actor.lock:
                yield actor
        finally:
            actor.claims -= 1
            # Eviction is considered only once nothing holds or awaits the
            # actor, so a turn is never interrupted (AD-33). In a finally so a
            # failing turn cannot let the registry grow past capacity forever.
            self._evict_if_needed()

    # -- introspection -------------------------------------------------------

    def retrieval_switch(self, main_id: str) -> RetrievalSwitch:
        """This main's retrieval switch, hydrating the actor if needed.

        The crisis gate runs before the mutex is taken, so it needs a way to
        reach one main's switch without holding that main's actor. This does not
        block, and does not write to the log.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return actor.retrieval

    # -- the ceiling (AD-28) -------------------------------------------------
    #
    # Story 5a built the cap and said, accurately then, that nothing in
    # ``half/`` lowered one. That is no longer true: ``half.crisis.gate`` drops
    # it to `behave` on entry, and the operator reversal path raises it again.
    # Both go through ``suspend_for_crisis`` and ``reverse_crisis`` below
    # rather than through the two sync methods, and the difference is the
    # mutex.
    #
    # **AD-1, and where the mutex is taken.** ``lower_ceiling`` and
    # ``release_ceiling`` append *without* holding the actor's mutex. That is
    # safe only for a caller that already holds it, or that is otherwise
    # serialized against every other writer for this main — which is an
    # assumption, so it is stated at both ends rather than left implicit at
    # one. Neither has a caller in ``half/``; they are 5a's surface and its
    # tests. Everything the crisis path does goes through the two async
    # methods, which take the mutex themselves, so a supervisor running many
    # actors concurrently cannot interleave a crisis append with an ordinary
    # turn's.

    def license_ceiling(self, main_id: str) -> Ceiling:
        """This main's license ceiling, hydrating the actor if needed.

        The same door ``retrieval_switch`` opens, for the same caller: crisis
        runs before the mutex is taken (AD-10) and aftercare sets the ceiling
        (AD-28). The returned ``Ceiling`` is frozen — reading one cannot change
        one, and there is no setter on it to reach.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return actor.ceiling

    def lower_ceiling(
        self, main_id: str, to: License, *, t: str, because: str
    ) -> Ceiling:
        """Lower this main's cap, durably. Only ever lowers.

        Appended to the log before the in-memory value moves, so a crash between
        the two leaves a main *more* capped than the process thought rather than
        less. ``t`` is supplied by the caller — nothing in this path reads a
        clock (AD-30).
        """
        actor = self._reached(main_id)
        lowered = actor.ceiling.lowered_to(to)
        self._record_ceiling(actor, lowered, t=t, because=because)
        return lowered

    def release_ceiling(
        self, main_id: str, *, t: str, because: str, to: License = TOP
    ) -> Ceiling:
        """Raise this main's cap — aftercare ending, and nothing else.

        Named, reasoned and durable, because raising a ceiling ends a
        suppression something deliberate put in place. No belief moves: a cap is
        a minimum against each belief's own license.
        """
        actor = self._reached(main_id)
        released = actor.ceiling.released(to=to, because=because)
        self._record_ceiling(actor, released, t=t, because=because)
        return released

    def _record_ceiling(
        self, actor: Actor, ceiling: Ceiling, *, t: str, because: str
    ) -> None:
        if ceiling == actor.ceiling:
            return  # nothing moved; an append would say something happened
        actor.store.record(
            Op.CEILING,
            f"c_{actor.main_id}_{t}",
            t,
            **ceiling_fields(ceiling, because=because),
        )
        actor.ceiling = ceiling

    # -- the crisis mode (CAP-12) ---------------------------------------------

    def crisis_open(self, main_id: str) -> bool:
        """Whether this main is in crisis mode, per the log.

        The authority is the ``crisis`` record, not a set in memory. A mode
        that ended at the next eviction would answer the main's following
        message through the ordinary pipeline — a mode exit that nobody
        decided and nothing recorded, which CAP-12 forbids outright.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return mode_is_open(actor.store.state().crisis)

    def crisis_record(self, main_id: str) -> dict[str, Any] | None:
        """The last crisis record for this main, or ``None``.

        Content-free by construction (AD-22): tier, signal count, state and
        time. It exists because the clinical reviewer's first question is how
        often the mode fires and on what, and nothing else in the log answers
        it — a ceiling append says a cap exists, never what put it there.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        record = actor.store.state().crisis
        return dict(record) if record is not None else None

    async def suspend_for_crisis(
        self, main_id: str, *, t: str, tier: str, score: int
    ) -> None:
        """Enter the mode for this main, durably and under the mutex (CAP-12).

        One call does the whole suspension because its three parts must not be
        separable: the crisis record, the ceiling drop, and the retrieval
        disable. A build where two of the three landed is a build where a main
        is capped but retrievable, or in the mode but uncapped.

        Ordered so that a crash never leaves the main *less* suspended than the
        process believes: the appends go first and the in-memory switch last.

        Idempotent. A held main re-enters on every turn of a long conversation,
        and one record per message would be a log full of the same fact.
        """
        async with self.acquire(main_id) as actor:
            if not mode_is_open(actor.store.state().crisis):
                actor.store.record(
                    Op.CRISIS,
                    f"cr_{main_id}_{t}",
                    t,
                    state=CRISIS_ENTERED,
                    tier=tier,
                    score=score,
                )
            self._record_ceiling(
                actor,
                actor.ceiling.lowered_to(License.BEHAVE),
                t=t,
                because="crisis mode entered (CAP-12)",
            )
            actor.retrieval.disable()

    async def reverse_crisis(
        self, main_id: str, *, t: str, because: str
    ) -> None:
        """Undo a crisis entry — the operator path, and the only way back.

        **This is not a mode exit policy.** Nothing in Half decides that a
        crisis is over: the companion leaves *who decides it is over*
        unresolved, and a timeout, a keyword or a quiet expiry would each be
        answering a clinical question in code review. This is the separate
        thing a durable cap needs to be a safety feature rather than a trap —
        a deliberate, recorded, human act that undoes a false entry, with a
        reason that outlives whoever typed it.

        Reverses all three parts of the suspension together, for the reason
        ``suspend_for_crisis`` applies them together.
        """
        if not isinstance(because, str) or not because.strip():
            raise StoreError(
                "reverse_crisis: reversing a crisis entry requires a stated "
                "reason; it undoes a suspension something deliberate applied"
            )
        async with self.acquire(main_id) as actor:
            actor.store.record(
                Op.CRISIS,
                f"cr_{main_id}_{t}",
                t,
                state=CRISIS_REVERSED,
                because=because.strip(),
            )
            self._record_ceiling(
                actor, actor.ceiling.released(to=TOP, because=because),
                t=t, because=because,
            )
            actor.retrieval.enable()

    @property
    def hydrated(self) -> list[str]:
        return list(self._actors)

    def is_hydrated(self, main_id: str) -> bool:
        return main_id in self._actors

    def close(self) -> None:
        """Close every store. Refuses while any turn is still running, rather
        than pulling a store out from under an in-flight append."""
        busy = [a.main_id for a in self._actors.values() if a.busy]
        if busy:
            raise RuntimeError(f"actors still mid-turn: {sorted(busy)}")
        for actor in self._actors.values():
            actor.store.close()
        self._actors.clear()
