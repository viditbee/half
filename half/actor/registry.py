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
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from half.store.store import Store

#: How many hydrated actors a worker holds before evicting the least recent.
DEFAULT_CAPACITY = 256


@dataclass(slots=True)
class Actor:
    """One main's hydrated state."""

    main_id: str
    store: Store
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def busy(self) -> bool:
        return self.lock.locked()


class ActorRegistry:
    """Hydrates, serializes and evicts actors."""

    def __init__(self, root: Path | str, *, capacity: int = DEFAULT_CAPACITY) -> None:
        self.root = Path(root)
        self.capacity = capacity
        self._actors: "OrderedDict[str, Actor]" = OrderedDict()

    # -- lifecycle -----------------------------------------------------------

    def _hydrate(self, main_id: str) -> Actor:
        """Open a main's store. Cheap — SQLite open plus a snapshot read, which
        the work that follows dwarfs."""
        actor = Actor(main_id=main_id, store=Store(self.root / main_id))
        self._actors[main_id] = actor
        return actor

    def _evict_if_needed(self) -> None:
        """Drop least-recently-used actors that are not mid-turn.

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
                return  # every actor is busy; try again after one finishes

    @asynccontextmanager
    async def acquire(self, main_id: str) -> AsyncIterator[Actor]:
        """Hold ``main_id``'s actor exclusively for the duration of the block."""
        actor = self._actors.get(main_id)
        if actor is None:
            actor = self._hydrate(main_id)
        self._actors.move_to_end(main_id)

        async with actor.lock:
            try:
                yield actor
            finally:
                # Eviction is considered only once the mutex is released, so a
                # turn is never interrupted (AD-33).
                pass
        self._evict_if_needed()

    # -- introspection -------------------------------------------------------

    @property
    def hydrated(self) -> list[str]:
        return list(self._actors)

    def is_hydrated(self, main_id: str) -> bool:
        return main_id in self._actors

    def close(self) -> None:
        for actor in self._actors.values():
            actor.store.close()
        self._actors.clear()
