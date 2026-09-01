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

**It costs nothing to *decide*, and it is not free to *write*.** No model call,
no network, no batch submission — every answer is arithmetic over the log, which
is why ``tests/test_pass.py`` asserts the module reaches no model port at all
rather than trusting that it does not. The arithmetic runs behind
``asyncio.to_thread``, because ``half.schedule.tick``'s own notes say a pass
doing real CPU work stalls the loop it shares with the inbound path — and
because ``asyncio.wait_for`` cannot cancel a coroutine that is not yielding, so
the scheduler's timeout only means something once the work yields.

What it does *not* do is make the writes cheap. ``Store.append`` re-folds the
log and rebuilds the SQLite view on every record, so a main whose tensions all
move on one night costs one fold and one rebuild per transition. That is the
store's shape and not this pass's to change — the single writer is what lets the
store skip a journal (AD-1) — and it is bounded rather than unbounded: at most
one transition per tension per night, under the scheduler's per-main timeout,
with ``tests/test_pass.py`` driving twenty-five of them under a timeout two
orders of magnitude below the shipped one. The reads are what this story made
cheap: one narrowed pass over the log per main instead of one per tension per
side, and the asserts only.

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

**Nothing here contacts anybody, and that is still true.** The pass produces
log records, a count, and — since story 10 — the *candidates* a morning surface
may choose from. It does not choose one, does not decide whether any of it is
worth saying, and does not send anything: that is ``half.surface.morning``'s,
and *sending nothing* is a first-class outcome (AD-27) rather than this
module's failure mode.

**A candidate is produced only for a tension that actually moved.** *"Every
surface traces to the preceding pass"* (CAP-8) is a property of this line and
not of a docstring: a tension the pass re-evaluated and left where it was did
not come *from* this pass, and one whose transition could not be appended is
not in the log, so neither is a candidate. On an ordinary night nothing moves,
so the pass produces none — which is what makes silence the ordinary outcome
rather than a mode something has to select.

**Nothing here ranks the two sides of a tension.** No result carries a winner,
no append names the entry that moved, and the counts below are counts.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from half.errors import HalfError
from half.schedule.clock import Now
from half.store.ops import TOUCH_TENSION
from half.surface.choose import Candidate
from half.surface.touch import Origin
from half.tensions import ledger as tension_ledger
from half.tensions.states import STATE

logger = logging.getLogger(__name__)


class Ledger(Protocol):
    """The two doors the pass needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry`` for the reason
    ``half.schedule.tick.Registry`` is one: one narrowed read and one write,
    both through the per-main mutex, is the whole dependency. Nothing here opens
    a store, and that is deliberate — a pass with its own path to the log would
    be a second writer, and the single writer is what lets the store skip a
    journal (AD-1).

    It was three doors, and the reads were two: the tension table came from the
    SQLite view and the history from the log file, unsynchronised, with an
    inbound turn free to land between them. One door now returns both.
    """

    async def tension_view(
        self, main_id: str
    ) -> tuple[Mapping[str, Mapping[str, Any]], Sequence[Mapping[str, Any]]]:
        ...

    async def note_transition(
        self,
        main_id: str,
        *,
        tension_id: str,
        t: str,
        fields: Mapping[str, Any],
        was: object = None,
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
    #: What this pass produced that a morning surface may choose from (CAP-8).
    #:
    #: **Only what moved, and only what was recorded.** A tension that computed
    #: to the state it already held did not come from this pass, and one whose
    #: transition could not be written is not in the log — so neither is
    #: traceable to it, and *"nothing is surfaced that cannot say where it came
    #: from"* would be false the moment either were included.
    #:
    #: Empty on an ordinary night, which is the ordinary night. Nothing here
    #: reaches for something to say when a pass found nothing (AD-27).
    #:
    #: Carries ids only, never content (AD-22): the origin names the tension
    #: and the entries name the two beliefs it links. Which *loop* they sit on
    #: is deliberately not answered here — the pass reads a projection of the
    #: log narrowed to id, stamp and support (``records.HISTORY_VISIBLE``), so
    #: it cannot see a belief's loop and must not be widened until it can.
    #: ``half.surface.choose`` attaches it from the fold.
    candidates: tuple[Candidate, ...] = ()

    @property
    def seen(self) -> int:
        return (len(self.moved) + len(self.unchanged) + len(self.incomputable)
                + len(self.unrecorded))

    @property
    def quiet(self) -> bool:
        """True when nothing moved **and nothing failed** — a normal night.

        Not *"changed nothing at all"*, which is what this used to say and is
        not what it computes: a pass whose every append raised changed nothing
        either, and calling that quiet is how a night of failed writes becomes
        indistinguishable from a night with nothing to do. ``unrecorded`` is in
        the test for that reason. ``incomputable`` is not — a tension the log
        cannot answer for is an ordinary thing to find, and a main who has one
        would otherwise never have a quiet night again.
        """
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
        """The ``Pass`` protocol's method. Returns ``None``; raises when a
        transition this main's log should be carrying is not in it.

        ``await``s so the appends go through the per-main mutex, and returns
        ``None`` so that the tick's own contract — a pass that completes is a
        pass that ran — is unchanged for the ordinary night. ``evaluate`` is the
        same work with the result handed back.

        **A night on which every write failed is not a quiet night.** ``run``
        used to discard the result, so it was one: the tick counted the main
        under ``ran``, ``next_pass_at`` had already advanced past the failures
        by design (at-most-once), and nothing anywhere said the log was missing
        the transitions the log itself computes. Raising puts the main in
        ``TickResult.failed``, which is logged without content and isolates
        nobody else — the counts are still on the result for a caller who wants
        them, and the next pass computes the same answer again from the same
        log, because nothing was recorded.
        """
        completed(await self.evaluate(main_id, now), main_id=main_id)

    async def evaluate(self, main_id: str, now: Now) -> PassResult:
        """One main's pass, with what it found.

        The read happens **once, under the main's own mutex**, so the tension
        table and the belief history are one consistent view rather than two an
        inbound turn could land between; the deciding happens off the event
        loop; the appends happen after, one at a time, each isolated and each
        carrying the state it was planned against.

        **The deciding runs in a thread.** ``half.schedule.tick``'s own notes
        say a pass that does real CPU work stalls the loop it shares with the
        inbound path and belongs behind ``asyncio.to_thread``, and this is that
        pass: ``plan`` walks a main's whole narrowed log. It also makes the
        scheduler's timeout mean something — ``asyncio.wait_for`` cannot cancel
        a coroutine that is not yielding.
        """
        table, history = await self.ledger.tension_view(main_id)
        found, premise, pairs = await asyncio.to_thread(
            _decide, table=table, history=history, at=now.stamp
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
        candidates: list[Candidate] = []
        for tension_id, fields in found.transitions.items():
            try:
                await self.ledger.note_transition(
                    main_id, tension_id=tension_id, t=now.stamp, fields=fields,
                    was=premise.get(tension_id),
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
            # A candidate is minted **after** the append landed, inside the
            # loop, so the two cannot disagree: a transition that raised on the
            # line above is in ``unrecorded`` and reaches no candidate list.
            # *"Every surface traces to the preceding pass"* means the pass as
            # the log will show it, not as it was planned.
            side = pairs.get(tension_id, ())
            if side:
                candidates.append(
                    Candidate(
                        origin=Origin(kind=TOUCH_TENSION, id=tension_id),
                        entries=side,
                    )
                )

        return PassResult(
            moved=moved,
            unchanged=found.unchanged,
            incomputable=dict(found.incomputable),
            unrecorded=tuple(unrecorded),
            candidates=tuple(candidates),
        )


class TensionPassIncomplete(HalfError):
    """A pass computed transitions this main's log did not end up carrying.

    Raised only by ``run``, so the scheduler counts the main under ``failed``
    rather than under ``ran``. It carries a count and a main id and no record,
    no claim and no tension id (AD-22): what could not be written is on the
    ``PassResult`` for a caller who asked for one, and the log line the tick
    writes for a failure names the exception type and nothing else.
    """


def completed(result: PassResult, *, main_id: str) -> PassResult:
    """``result``, or ``TensionPassIncomplete`` if the log is missing writes.

    One spelling of *"a night on which every write failed is not a quiet
    night"*, so that the scheduler's ordinary entry point and the morning
    surface — which needs the same result *before* the raise, because a night
    with one failed transition still has things worth saying — cannot come to
    disagree about when a pass counts as having run.
    """
    if result.unrecorded:
        raise TensionPassIncomplete(
            f"{len(result.unrecorded)} transition(s) for main={main_id} "
            f"could not be recorded"
        )
    return result


def _decide(
    *,
    table: Mapping[str, Mapping[str, Any]],
    history: Sequence[Mapping[str, Any]],
    at: str,
) -> tuple[
    tension_ledger.Plan, dict[str, str | None], dict[str, tuple[str, ...]]
]:
    """The whole deciding half: pure, total, and run off the event loop.

    Returns the plan, the state each tension was in when it was planned — so
    the append can refuse a premise that moved underneath it — and the pair
    each one links, which is what a candidate's ``entries`` are. All three come
    out of one ``read`` of one table, which is what makes them the plan's own
    rather than a second look at a log that may have moved again.

    The pair travels from here rather than being re-read after the append, for
    the same reason the premise does: a correction landing between the two
    reads would hand the surface a pair the plan never saw.
    """
    tensions = tension_ledger.read(table)
    found = tension_ledger.plan(tensions, history=history, now=at)
    return (
        found,
        {ident: item.state for ident, item in tensions.items()},
        {ident: item.between for ident, item in tensions.items()},
    )
