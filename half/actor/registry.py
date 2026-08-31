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
from pathlib import Path
from typing import AsyncIterator

from half.errors import StoreError
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import RetrievalSwitch
from half.retrieval.strands import Strands
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
    retrieval: RetrievalSwitch = field(default_factory=RetrievalSwitch)
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
        the work that follows dwarfs."""
        validate_main_id(main_id)
        # The prefix builder is handed to the store here rather than imported
        # by it: ``half.store`` may not depend on ``half.retrieval``. Wiring it
        # at hydration is what makes prefix hits work in the running product
        # and not only where a test remembers to pass it.
        actor = Actor(
            main_id=main_id, store=Store(self.root / main_id, prefix=build_prefix)
        )
        self._actors[main_id] = actor
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
        actor = self._actors.get(main_id)
        if actor is None:
            actor = self._hydrate(main_id)
        self._actors.move_to_end(main_id)

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
        reach one main's switch without holding that main's actor. Hydration is
        a dict entry plus a lazily-opened store, and the switch is volatile
        state on the actor — so this neither writes nor blocks.
        """
        actor = self._actors.get(main_id)
        if actor is None:
            actor = self._hydrate(main_id)
        return actor.retrieval

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
