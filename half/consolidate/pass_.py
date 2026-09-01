"""The pass the scheduler runs: tensions, re-evaluated (CAP-7, AD-9, AD-27).

One main, one instant, one job. The tick hands this an injected ``now``; it
reads that main's tensions and the support each side of each one cites, asks
``half.tensions.ledger`` what the log computes to, and appends the transitions
that differ from what is already recorded.

**Idempotent, and pure at its core.** The deciding is
``half.tensions.ledger.plan`` — a pure function of the tension table, the
narrowed belief history and ``now`` — so re-running over the same log with the
same instant produces the same plan, and an empty one the second time: each
transition moves the tension's own stamp to ``now``, so nothing has accumulated
since. Everything impure in this module is the reading and the appending, and
neither of them decides anything.

**It costs nothing.** No model call, no network, no batch submission — every
answer is arithmetic over the log. The budget is zero and the scheduler's
timeout is not approached, which is why ``tests/test_pass.py`` asserts the
module reaches no model port at all rather than trusting that it does not.

**A transition is an append, never an edit** (AD-3, AD-30). Appended under the
tension's own id through the registry's mutex, so the fold merges the new state
over the pair and the license the mint recorded, and replay reproduces the
transition rather than re-deriving it.

**One tension's failure costs that tension; one main's costs that main.** The
tick already isolates mains from each other (AD-9); this isolates tensions from
each other inside one, because a tension whose record this build cannot read is
exactly the case ``plan`` reports rather than guessing at, and one of them must
not cost a main the other nine. A tension that cannot be evaluated **keeps the
state it has**, is counted, and never blocks the rest.

**Nothing here contacts anybody.** The pass produces log records and a count.
Deciding whether any of it is worth saying is story 10's, and *sending nothing*
is a first-class outcome (AD-27) rather than this module's failure mode.

**Nothing here ranks the two sides of a tension.** No result carries a winner,
no append names the entry that moved, and the counts below are counts.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from half.schedule.clock import Now
from half.tensions import ledger as tension_ledger
from half.tensions.states import STATE

logger = logging.getLogger(__name__)


class Ledger(Protocol):
    """The three doors the pass needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry`` for the reason
    ``half.schedule.tick.Registry`` is one: two narrowed reads and one write
    that goes through the per-main mutex is the whole dependency. Nothing here
    opens a store, and that is deliberate — a pass with its own path to the log
    would be a second writer, and the single writer is what lets the store skip
    a journal (AD-1).
    """

    def tension_table(self, main_id: str) -> Mapping[str, Mapping[str, Any]]:
        ...

    def belief_history(self, main_id: str) -> Sequence[Mapping[str, Any]]:
        ...

    async def note_transition(
        self, main_id: str, *, tension_id: str, t: str, fields: Mapping[str, Any]
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class PassResult:
    """What one main's pass did. Counts and ids only — never content (AD-22).

    Returned rather than logged-and-forgotten so a caller — a test, an
    operator's manual run, story 10 — can see what a night produced without
    reading the main's log. ``Scheduler`` discards it, which is correct: the
    tick reports whether a pass *ran*, and what it found is not the tick's
    business.
    """

    #: Tensions whose state moved, id-keyed to the state they moved **to**.
    moved: Mapping[str, str] = field(default_factory=dict)
    #: Tensions the log computed to the state they already held. The ordinary
    #: case on an ordinary night, and not a failure.
    unchanged: tuple[str, ...] = ()
    #: Tensions that could not be evaluated, id-keyed to why. **Their states
    #: were left exactly as they were.**
    incomputable: Mapping[str, str] = field(default_factory=dict)
    #: Tensions whose transition could not be appended. Counted here rather
    #: than raised, because one failed write must not cost this main the other
    #: nine tensions — and the next pass will compute the same answer again,
    #: since nothing was recorded.
    unrecorded: tuple[str, ...] = ()

    @property
    def seen(self) -> int:
        return (len(self.moved) + len(self.unchanged) + len(self.incomputable)
                + len(self.unrecorded))

    @property
    def quiet(self) -> bool:
        """True when this pass changed nothing at all — a normal night."""
        return not (self.moved or self.unrecorded)


@dataclass(frozen=True, slots=True)
class TensionPass:
    """Re-evaluate one main's tensions against an injected ``now``.

    Satisfies ``half.schedule.tick.Pass``: ``run(main_id, now)``, and it reads
    no clock of its own — ``now`` is the instant the tick read once, inside its
    file lock, so every main in one tick is judged against the same moment and
    everything below the scheduler stays replayable (AD-30).
    """

    ledger: Ledger

    async def run(self, main_id: str, now: Now) -> None:
        """The ``Pass`` protocol's method. Returns nothing; raises for nothing
        normal.

        ``await``s so the appends go through the per-main mutex, and returns
        ``None`` so that the tick's own contract — a pass that completes is a
        pass that ran — is unchanged. ``evaluate`` is the same work with the
        result handed back.
        """
        await self.evaluate(main_id, now)

    async def evaluate(self, main_id: str, now: Now) -> PassResult:
        """One main's pass, with what it found.

        The reads happen first and together, so the plan is computed against
        one consistent view of the log rather than one that moved underneath
        it; the appends happen after, one at a time, each isolated.
        """
        table = self.ledger.tension_table(main_id)
        history = self.ledger.belief_history(main_id)
        found = tension_ledger.plan(
            tension_ledger.read(table), history=history, now=now.stamp
        )

        if found.incomputable:
            # Counted, never guessed at, and the *reasons* only — a reason is
            # one of a closed set of constants (``half.tensions.widening``) and
            # carries no belief text, no claim and no id of anything but a
            # tension (AD-22).
            logger.info(
                "pass for main=%s left %d tension(s) alone: %s",
                main_id, len(found.incomputable),
                sorted(set(found.incomputable.values())),
            )

        moved: dict[str, str] = {}
        unrecorded: list[str] = []
        for tension_id, fields in found.transitions.items():
            try:
                await self.ledger.note_transition(
                    main_id, tension_id=tension_id, t=now.stamp, fields=fields
                )
            except Exception as exc:  # noqa: BLE001 - one tension, not the main
                # A failed append costs this tension its transition and nothing
                # else. Nothing was recorded, so the next pass computes the
                # same answer again from the same log — which is the whole
                # value of the state being derived rather than accumulated.
                #
                # The *type* and nothing else (AD-22): an exception message
                # routinely quotes the value that caused it, and here that is a
                # record out of a main's own ledger.
                unrecorded.append(tension_id)
                logger.error(
                    "could not record a transition for main=%s tension=%s "
                    "(%s); the pass continues",
                    main_id, tension_id, type(exc).__name__,
                )
                continue
            moved[tension_id] = str(fields.get(STATE))

        return PassResult(
            moved=moved,
            unchanged=found.unchanged,
            incomputable=dict(found.incomputable),
            unrecorded=tuple(unrecorded),
        )
