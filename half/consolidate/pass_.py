"""The pass the scheduler runs: tensions, minted and re-evaluated (CAP-7, AD-9).

One main, one instant, two jobs. The tick hands this an injected ``now``; it
mints what CAP-7's bound produced (story 9d), then reads that main's tensions
and the support each side of each one cites, asks ``half.tensions.ledger`` what
the log computes to, and appends the transitions that differ from what is
already recorded.

**Mint first, then re-evaluate**, so a tension minted tonight is evaluated
tonight rather than waiting a day for its first state. The whole of the minting
lives in ``half.consolidate.mint`` and the whole of the judgement lives behind
``half.consolidate.port``, whose implementation this module never names: what
this module adds is the ordering and the isolation, and a minting failure never
costs the re-evaluation.

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
rather than trusting that it does not. **That stays true now that story 9e has
supplied a judge**, and the two protocols above are how: this module names a
``Disagreement`` and a ``Bench``, both structural, and the implementation of
either is somebody else's import. What one costs is bounded before the first
call is made — ``JUDGEMENTS`` judgements per main per night, decided by
``mint.slate`` — and a deployment that has equipped nobody consults nobody while
the bound, the cheap filter and the budget run on every pass regardless. The
arithmetic runs behind
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

from half.consolidate import mint as minting
from half.consolidate.candidates import MintView
from half.consolidate.port import Disagreement
from half.errors import HalfError
from half.schedule.clock import Now
from half.store.ops import TOUCH_TENSION
from half.surface.choose import Candidate
from half.surface.touch import Origin
from half.tensions import ledger as tension_ledger
from half.tensions.states import STATE

logger = logging.getLogger(__name__)


class Bench(Protocol):
    """Where one main's judge comes from, when a deployment has one (story 9e).

    **A second seam rather than a widening of the first**, and the reason is a
    signature that cannot carry what a provider needs.
    ``half.consolidate.port.Disagreement.disagree`` takes two entries and no
    ``main_id`` — deliberately, because a judge that could be handed a main
    could be handed a main's ledger — while the key, the provider and the tier
    are all per main (AD-11, AD-20). So the resolution happens once per pass,
    here, above the seam, and the seam is untouched.

    ``for_main`` answers ``None`` for a main a deployment has not equipped,
    which is what makes ``MintResult.unwired`` mean what it says: an unwired
    port and a quiet night are not the same night.

    A protocol rather than the concrete bench for the reason ``Ledger`` is one,
    with a second reason of its own — the concrete bench lives in
    ``half.consolidate.judge``, which reaches ``half.model``, and importing it
    here would put the nightly pass one hop from a provider. ``tests/
    test_pass.py`` asserts transitively that it is not.
    """

    def for_main(self, main_id: str) -> Disagreement | None:
        ...


class Ledger(Protocol):
    """The four doors the pass needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry`` for the reason
    ``half.schedule.tick.Registry`` is one: two narrowed reads and two writes,
    all through the per-main mutex, is the whole dependency. Nothing here opens
    a store, and that is deliberate — a pass with its own path to the log would
    be a second writer, and the single writer is what lets the store skip a
    journal (AD-1).

    It was three doors, and the reads were two: the tension table came from the
    SQLite view and the history from the log file, unsynchronised, with an
    inbound turn free to land between them. One door now returns both.

    Story 9d adds the second pair, and they are a pair rather than a widening of
    the first for a reason worth stating. The two halves of the pass read
    *different projections of the same records* — the widening half sees an id,
    a stamp and a support set, the minting half sees what an entry is about —
    and one door returning the union would hand each half the other's fields.
    The two writes are separate for the sharper version of the same reason:
    ``note_mint`` refuses a tension the fold already holds and
    ``note_transition`` refuses one it does not, so neither door can do the
    other's job even by accident.
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

    async def mint_view(self, main_id: str) -> MintView:
        ...

    async def note_mint(
        self,
        main_id: str,
        *,
        tension_id: str,
        t: str,
        fields: Mapping[str, Any],
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
    #: What the minting half of this pass did (CAP-7, story 9d). Counts and ids
    #: only, and empty when no judge is wired — which is every pass this build
    #: ships, since the port has no implementation until 9e.
    #:
    #: **Deliberately absent from ``quiet`` and from ``seen``.** Both answer
    #: questions about the *re-evaluation*: ``seen`` is how many tensions were
    #: looked at, and ``quiet`` is *"nothing moved and nothing failed"*, which
    #: story 10 does not read and the tick does not either. A mint is not a
    #: movement — a tension born `fresh` and evaluated to `fresh` in the same
    #: pass has not moved — and folding minting into either would change what
    #: two existing sentences mean rather than add a third.
    minted: minting.MintResult = field(default_factory=minting.MintResult)

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

    **Mint first, then re-evaluate** (story 9d). A tension minted tonight gets
    its first state tonight rather than waiting a day, and the re-evaluation
    tolerates a tension whose stamp is ``now`` because 9c already does: a
    `fresh` tension at zero elapsed time is its ordinary starting case, and
    ``ledger.plan`` computes it to `fresh` and reports it unchanged.

    The order also means the two halves cannot be confused for each other in
    the log. Minting appends a record with a pair and a state; transitioning
    appends a record with a state alone, through a different door that refuses
    a tension the fold has never seen. Neither door can do the other's job.
    """

    ledger: Ledger
    #: Who decides whether two entries disagree, or ``None``.
    #:
    #: **One judge for every main**, which is the shape a test wants and not the
    #: shape a deployment has: a real judge holds a per-main key and a per-main
    #: tier, so the shipped composition passes ``bench`` below instead. Kept,
    #: and kept first, because it is 9d's field and every case that drives the
    #: minting half with a deterministic double uses it.
    judge: Disagreement | None = None
    #: Where one main's judge comes from, or ``None`` (story 9e).
    #:
    #: **``None`` on both is an ordinary night rather than a degraded one**: the
    #: bound, the cheap filter and the budget still run on every pass, nothing
    #: is consulted, and nothing is minted. A pass with no judge completes, is
    #: never fatal, and is not a failure to report.
    #:
    #: ``judge`` wins where both are given, so a case that hands over a double
    #: gets the double whatever else is wired.
    bench: Bench | None = None

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

        **Minting happens first, and its read is its own.** It has to be a
        second read rather than a widening of the first: the mint appends, so a
        re-evaluation computed against a view taken before it would be planning
        over a tension table the log no longer has. Each half gets one
        consistent view, and the second one is taken after the first has
        finished writing.
        """
        minted = await self._mint(main_id, now)

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
            minted=minted,
        )

    async def _mint(self, main_id: str, now: Now) -> minting.MintResult:
        """The minting half: what CAP-7 creates, inside CAP-7's bound.

        **Never fatal, and that is the whole of its error handling.** A view
        this build cannot read, a judge that is not there, one that refuses and
        one that throws are all ordinary nights on which nothing is minted —
        ``mint.consider`` isolates each couple, and this isolates the read. The
        re-evaluation below runs either way, because a main whose minting failed
        still has tensions whose states the log has already computed.

        The failure this catches is the read; every failure inside the minting
        is counted on the result rather than raised, which is why nothing here
        inspects what came back.
        """
        try:
            view = await self.ledger.mint_view(main_id)
            return await minting.consider(
                view,
                judge=self._judge_for(main_id),
                ledger=self.ledger,
                main_id=main_id,
                now=now.stamp,
            )
        except Exception as exc:  # noqa: BLE001 - minting, not the pass
            # The *type* and nothing else (AD-22): an exception message
            # routinely quotes the value that caused it, and here that value is
            # a claim out of the main's own ledger.
            logger.error(
                "minting failed for main=%s (%s); the re-evaluation still runs",
                main_id, type(exc).__name__,
            )
            return minting.MintResult()

    def _judge_for(self, main_id: str) -> Disagreement | None:
        """This main's judge: the injected one, then the bench's, then none.

        **Inside the ``try`` its caller already holds**, so a bench that raised
        would cost this main their minting and not their pass — the same
        isolation the read above it gets, one rung out.

        The order is deliberate and is not a preference: a case that hands over
        a deterministic ``judge`` is asserting something about the minting half
        and must get exactly that object, whatever a composition root happened
        to wire beside it.
        """
        if self.judge is not None:
            return self.judge
        if self.bench is None:
            return None
        return self.bench.for_main(main_id)


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
