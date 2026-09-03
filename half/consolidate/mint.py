"""Minting a tension: the bound, the three outcomes, and the append (CAP-7).

**One pass over a candidate set, three disjoint outcomes** — the shape taken
from graphiti's `resolve_extracted_edges`
(`graphiti_core/utils/maintenance/edge_operations.py`), whose manifest row has
been open for story 9 since story 4. What that function gets right, and what a
first attempt at this one would not have, is that a pass over candidates does
not produce *a list of creations*: it produces creations, things that already
existed, and things it decided against, and reporting only the first makes the
other two indistinguishable from nothing having happened. ``MintResult`` below
carries all three, and the two failure shapes besides.

Also taken from that file: its **escape hatches before the model**, which are
the reason its cost is bounded and not merely small. It skips the LLM entirely
when a candidate has no related edges (`if len(related_edges) == 0 and
len(existing_edges) == 0`), and short-circuits on an exact normalised match
against an edge it already holds — the idempotence guarantee for re-ingesting
an episode, paid for with zero calls. Both are here: a couple already carrying
a live tension is recognised in ``slate``, which is *before* the filter and
therefore two steps before the port, and a pass with nothing new consults
nobody.

**What is deliberately not taken is graphiti's second outcome, `invalidated`.**
Its resolver expires existing edges that new information contradicts. Half must
not: a tension is a link between two entries, and *evidence of non-action never
refutes a wanting* (CAP-6). There is no invalidation here, no demotion, no
freeze, and nothing in this module can reach the loop table to perform one —
which ``tests/test_minting.py`` asserts by AST rather than by absence, because
absence is what it looked like in story 8 too. Also rejected: its edge-level
*mutation* of timestamps, which has no meaning against an append-only log; and
its index-space handling for a model that names candidates by position, which
this port has no way to express and therefore no way to get wrong.

**There are two bounds and they bound different things.** ``CEILING``
(``half.consolidate.candidates``) is how many couples a pass may *build*;
``JUDGEMENTS`` below is how many it may *buy*. The budget alone bounded the
bill while the memory and the CPU were unbounded — CAP-7's subject set is the
whole stated ledger on the data Half writes, so a first pass built the complete
pair set — and a pass can reach either bound without reaching the other, which
is why each has its own field on the result rather than sharing the budget's
vocabulary.

**The bound is per main and per pass, and it is spent before it is exceeded.**
``JUDGEMENTS`` is a count of *consultations*, because the consultation is the
cost — everything either side of it is arithmetic. A pass with more survivors
than the budget consults the budget's worth, most surprising first, and says so
on the result: ``unbudgeted`` is what it did not reach and ``budget_reached``
is the sentence CAP-7 asks for. It never finishes and then reports, because a
report after the spending is not a bound.

**A minted tension starts `fresh` and stops there.** This module writes one
record, carrying a state, a pair and the license the ladder admits — and no
transition, ever. Story 9c owns every state change and computes widening from
the stamp on the record that set the current state; a minter that also
transitioned would give one field two writers, and the second would be the one
nobody tests.

**Nothing here names a winner.** No argument, no field, no local, and no
ordering: the pair travels as a ``Couple`` that offers no accessor, the id is
derived by exclusive-or, and ``fields_for`` writes exactly ``between``, a state
and a license.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

from half.consolidate import filter as relevance
from half.consolidate.candidates import (
    BOTH,
    CEILING,
    Couple,
    MintView,
    couples,
    read,
    watermark,
)
from half.consolidate.port import Disagreement
from half.governance import ladder
from half.tensions.states import LIVE_STATES, STATE, TensionState
from half.tensions.widening import BETWEEN, pair_of

logger = logging.getLogger(__name__)

#: How many disagreement judgements one main's pass may buy. **The fixed
#: per-user cost budget of CAP-7**, and the only number in this package that a
#: reviewer has to argue about.
#:
#: A count of consultations rather than of tensions, because the consultation
#: is what costs: the candidate bound, the filter and the priority are
#: arithmetic over a table that is already in memory, and the append is the
#: store's price rather than the model's.
#:
#: Twenty-four. A main who has had an ordinary day changes a handful of entries,
#: and the survivors of a cheap filter over a handful is a number in the low
#: tens; twenty-four leaves room for a busy day without leaving room for a
#: pathological one. The value is what makes the free tier's arithmetic hold
#: (SPEC: the nightly pass dominates cost and runs batched on the cheapest
#: tier), so it is **pinned by value** in ``tests/test_minting.py`` the way
#: ``PERSISTENCE_DAYS`` is: raising it is a red test and a deliberate edit,
#: never a quiet doubling of every main's nightly bill.
JUDGEMENTS: Final[int] = 24


class Mints(Protocol):
    """The one door minting needs into a main's durable state.

    A protocol rather than the concrete registry, for the reason
    ``half.consolidate.pass_.Ledger`` is one: one write, through the per-main
    mutex, is the whole dependency. Nothing here opens a store — a minter with
    its own path to the log would be a second writer, and the single writer is
    what lets the store skip a journal (AD-1).
    """

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
class Slate:
    """What one pass would spend, decided before a single judgement is bought.

    A value, computed by a pure function of the view, so *"the bound is a
    function of the changed set and not of the ledger"* can be asserted as
    arithmetic rather than inferred from a count of calls — and so the budget's
    refusal can be seen without a judge in the room.
    """

    #: The couples this pass will consult about, most surprising first, already
    #: cut to the budget.
    within: tuple[Couple, ...] = ()
    #: Couples the filter admitted that the budget could not reach. Non-zero is
    #: exactly *"this pass would have exceeded its bound"*.
    #:
    #: **Dropped, not deferred.** There is no backlog and the next pass's
    #: watermark excludes the entries that produced them, so a couple counted
    #: here is not reconsidered later — which is one of the two answers CAP-7's
    #: matrix allows, and the one this build gives.
    unbudgeted: int = 0
    #: Couples already carrying a live tension. Recognised before the filter and
    #: long before the port, so nothing is spent on a disagreement Half has
    #: already recorded.
    standing: tuple[str, ...] = ()
    #: Couples the cheap filter turned away. Counted, because a filter whose
    #: rejections nothing can see is a filter nothing can assert.
    turned_away: int = 0
    #: Couples the bound produced at all — the number *"never all-pairs"* is a
    #: statement about. **Never more than ``candidates.CEILING``.**
    considered: int = 0
    #: Whether the couple ceiling stopped the bound producing more. A separate
    #: fact from ``budget_reached``: the budget is what a pass may *buy*, the
    #: ceiling is what it may *build*, and a pass can reach either without the
    #: other.
    ceiling_reached: bool = False

    @property
    def budget_reached(self) -> bool:
        return self.unbudgeted > 0


@dataclass(frozen=True, slots=True)
class MintResult:
    """What one main's minting did. Counts and ids only — never content (AD-22).

    The three disjoint outcomes are ``minted``, ``standing`` and ``passed``;
    every other field is a count of something that did not happen, kept apart
    so that no two of them can be satisfied by one assertion.
    """

    #: Tensions this pass created, by id. The only outcome that wrote anything.
    minted: tuple[str, ...] = ()
    #: Couples that already carried a live tension. Nothing minted, nothing
    #: spent, nothing wrong.
    standing: tuple[str, ...] = ()
    #: Couples the judge was asked about and found no disagreement in.
    passed: tuple[str, ...] = ()
    #: Couples the judge could not answer for — degraded, unsure, declining.
    #: **Kept apart from ``passed``**, because *"the judge said no"* and *"the
    #: judge could not say"* are different facts and a suite that folded them
    #: together would pass with the port never reached at all.
    unsaid: tuple[str, ...] = ()
    #: Couples whose judgement raised. That couple is skipped; the pass goes on.
    skipped: tuple[str, ...] = ()
    #: Mints the store would not take. Counted rather than raised, because one
    #: failed write must not cost this main the rest of the night — and nothing
    #: was recorded, so the next pass computes the same answer again.
    unrecorded: tuple[str, ...] = ()
    #: Judgements actually bought. **Never more than ``JUDGEMENTS``**, and
    #: counted before the call rather than after it: a judgement that raised
    #: had still been bought, and billing it only on success reported
    #: ``consulted == 0`` for a provider that failed twenty-four times.
    consulted: int = 0
    #: Couples the filter turned away, before any of them cost anything.
    turned_away: int = 0
    #: Couples the filter admitted that the budget could not reach. **Dropped,
    #: not deferred** — there is no backlog, and the next pass's watermark
    #: excludes the entries that produced them.
    unbudgeted: int = 0
    #: Couples the comparison bound produced at all. **Never more than
    #: ``candidates.CEILING``**, which is what makes *"never all-pairs, in
    #: fact"* true on the ledger production writes rather than only on the one
    #: CAP-7 describes.
    considered: int = 0
    #: Whether the couple ceiling stopped the bound producing more.
    ceiling_reached: bool = False

    @property
    def budget_reached(self) -> bool:
        """Whether this pass stopped minting because it had spent its bound."""
        return self.unbudgeted > 0

    #: Whether there was no judge to ask. **A fact of its own**, because it
    #: used to borrow the budget's: a pass with no port ran the slate, hit the
    #: cut at ``JUDGEMENTS`` and reported ``budget_reached`` with a count of
    #: couples it had supposedly not been able to afford, having bought
    #: nothing. It is also why ``quiet`` reads it — an unwired port and a quiet
    #: night are not the same night, and this build ships unwired until 9e.
    unwired: bool = False

    @property
    def quiet(self) -> bool:
        """True when nothing was minted, **nothing failed, and somebody was
        asked**.

        ``unwired`` is in the test because it was not, and an unwired port was
        therefore indistinguishable from a night with nothing to mint — which
        is the state this build ships in, so the one that most needed telling
        apart.
        """
        return not (self.minted or self.unrecorded or self.skipped
                    or self.unwired)


def linked(tensions: Mapping[str, Mapping[str, Any]] | None) -> set[frozenset[str]]:
    """The pairs this main already carries a **live** tension over.

    Keyed by an unordered set, which is the only reading of ``between`` this
    question has: a tension over the same two entries is the same tension
    whichever order the log happens to have written them in, and a lookup that
    respected the order would mint a duplicate for every pair the fold stored
    the other way round.

    `resolved` tensions are deliberately absent. One of their entries has left
    the ledger, so the pair cannot arise again from a fold that no longer holds
    it — and if the main says the thing afresh that is a new entry, a new pair
    and a new tension (``half.tensions.states``), never this one reopened.
    """
    if not isinstance(tensions, Mapping):
        return set()
    found: set[frozenset[str]] = set()
    for row in tensions.values():
        if not isinstance(row, Mapping):
            continue
        if row.get(STATE) not in LIVE_STATES:
            continue
        names = pair_of(row)
        if len(set(names)) == BOTH:
            found.add(frozenset(names))
    return found


def fields_for(couple: Couple) -> dict[str, Any]:
    """The fields of the append that mints ``couple``. Returns fields; writes
    nothing.

    Three things, and the record may carry nothing else (``TENSION_FIELDS``):
    the two entries it links, the state every tension is born in, and the
    license the ladder admits — which is always the weakest rung, because both
    preconditions for anything stronger are events that happen after a tension
    exists.

    There is no argument here naming a side, no field recording which entry
    moved, and no text about the disagreement (AD-22). What the two entries say
    is on the two entries; a sentence written here would be one no correction to
    either of them could ever take back.
    """
    return {
        BETWEEN: list(couple.names),
        STATE: str(TensionState.FRESH),
        **ladder.admitted(),
    }


def slate(view: MintView, *, now: str) -> Slate:
    """Everything one pass would spend, decided before anything is spent.

    Pure, total and clockless — ``now`` is the instant the tick read once
    (AD-30) and is used only to find the previous pass's watermark. Never
    raises: a view this build cannot read yields an empty slate, because the
    alternative to reporting is a main whose whole night ends on one malformed
    row.

    The order of the four steps is CAP-7's own, and each one narrows what the
    next may see:

    1. the **bound** — new or changed against the loop set and the subject set,
       and never more than ``candidates.CEILING`` couples however wide those
       two sets come out;
    2. **already linked** — recognised here, so a standing disagreement costs
       nothing at all, not even a filter pass;
    3. the **cheap filter** — before any model comparison, always;
    4. the **budget** — most surprising first, cut at ``JUDGEMENTS``.

    Two of those four are bounds and they bound different things. The ceiling
    is what a pass may *build*; the budget is what it may *buy*. A pass can
    reach either without the other, so each has its own field.
    """
    known = read(view.beliefs)
    offered = couples(
        known,
        since=watermark(view.passes, now=now),
        loops=view.loops,
        ceiling=CEILING,
    )
    already = linked(view.tensions)
    standing: list[str] = []
    admitted: list[Couple] = []
    turned_away = 0
    for couple in offered.within:
        if frozenset(couple.names) in already:
            standing.append(couple.id)
            continue
        if couple.id in view.tensions or couple.id in view.gone:
            # A tension the fold already holds under this couple's own derived
            # id — a `resolved` one, or one the main erased. Either way the
            # record exists and a second mint would be a duplicate or an
            # erasure undone.
            standing.append(couple.id)
            continue
        if not relevance.admits(couple):
            turned_away += 1
            continue
        admitted.append(couple)
    # **Only if there is something to rank.** ``corpus`` tokenises every claim
    # in the ledger, which is the most expensive thing this function does and
    # is a cost the ordinary night — nothing changed, nothing admitted — used
    # to pay in full for a ranking of the empty list.
    queue: tuple[Couple, ...] = ()
    if admitted:
        counts, total = relevance.corpus(known)
        queue = relevance.priority(admitted, counts=counts, total=total)
    return Slate(
        within=queue[:JUDGEMENTS],
        unbudgeted=max(len(queue) - JUDGEMENTS, 0),
        standing=tuple(standing),
        turned_away=turned_away,
        considered=len(offered.within),
        ceiling_reached=offered.ceiling_reached,
    )


async def consider(
    view: MintView,
    *,
    judge: Disagreement | None,
    ledger: Mints,
    main_id: str,
    now: str,
) -> MintResult:
    """One main's minting: consult, then append. Never fatal.

    **No judge is an ordinary night, not a failure.** With ``judge`` unwired the
    slate is still computed — so the bound, the filter and the budget are
    exercised on every pass whether or not anybody can answer — and nothing is
    consulted and nothing is minted. That is the state this story ships in, and
    it is why the whole of CAP-7's cost rule is under test with no provider
    anywhere in the tree.

    **A judgement that raises costs its couple.** Caught per couple, counted in
    ``skipped``, and the pass continues — the same isolation
    ``half.consolidate.pass_`` gives one tension's failed append, one rung out.

    **An append that fails costs its couple too**, and nothing was recorded, so
    the next pass computes the same answer again from the same log.
    """
    # **Off the event loop.** ``slate`` tokenises every claim in the ledger and
    # sorts what survives — real CPU work, measured at 1.64s for eight hundred
    # beliefs — and it ran here synchronously while the re-evaluation beside it
    # went through a thread. ``half/schedule/tick.py`` states the rule it broke:
    # ``asyncio.wait_for`` cannot cancel a coroutine that never yields, so a
    # pass doing this on the loop runs past its bound with the tick looking
    # healthy the whole time, in front of every main's inbound turn.
    plan = await asyncio.to_thread(slate, view, now=now)

    if judge is None:
        # **Hoisted, because the budget's vocabulary was lying about it.** The
        # check used to sit inside the loop, so a pass with no port ran the
        # whole slate — including the cut at ``JUDGEMENTS`` — and reported
        # ``budget_reached=True`` with ``unbudgeted=876`` for a night on which
        # nothing could be bought at all. The bound, the filter and the ceiling
        # still run and are still reported, because exercising them on every
        # pass is what keeps CAP-7's cost rule under test with no provider in
        # the tree; what is *not* reported is a budget that was never spent.
        logger.info(
            "minting for main=%s consulted nobody: no disagreement judge is "
            "wired. %d couple(s) considered", main_id, plan.considered,
        )
        return MintResult(
            standing=plan.standing,
            turned_away=plan.turned_away,
            considered=plan.considered,
            ceiling_reached=plan.ceiling_reached,
            unwired=True,
        )

    minted: list[str] = []
    passed: list[str] = []
    unsaid: list[str] = []
    skipped: list[str] = []
    unrecorded: list[str] = []
    consulted = 0

    for couple in plan.within:
        # **Billed before the call, not after.** ``consulted`` used to be
        # incremented past the ``except``, so a provider that failed every call
        # reported ``consulted == 0`` after twenty-four billed consultations —
        # a bound whose own meter read zero on exactly the night it mattered.
        # A judgement that raises has been bought; whether it answered is what
        # ``skipped`` says.
        consulted += 1
        try:
            answer = await judge.disagree(*couple.both)
        except Exception as exc:  # noqa: BLE001 - one couple, not the main
            # The *type* and nothing else (AD-22): an exception message
            # routinely quotes the value that caused it, and here that value is
            # a claim out of the main's own ledger.
            skipped.append(couple.id)
            logger.error(
                "a disagreement judgement failed for main=%s (%s); the pass "
                "continues", main_id, type(exc).__name__,
            )
            continue
        if answer is None:
            unsaid.append(couple.id)
            continue
        if answer is not True:
            passed.append(couple.id)
            continue
        try:
            await ledger.note_mint(
                main_id, tension_id=couple.id, t=now, fields=fields_for(couple)
            )
        except Exception as exc:  # noqa: BLE001 - one couple, not the main
            unrecorded.append(couple.id)
            logger.error(
                "could not record a mint for main=%s tension=%s (%s); the pass "
                "continues", main_id, couple.id, type(exc).__name__,
            )
            continue
        minted.append(couple.id)

    if plan.ceiling_reached:
        # The other bound, and it is not the budget's. Said because CAP-7's
        # amended row asks a pass that reaches the ceiling to say so, and
        # because the ceiling cuts *before* the surprisal ranking: a night that
        # reached it ranked the couples the fold listed first rather than the
        # whole set, and that is worth being able to see in a log.
        logger.info(
            "minting for main=%s reached its couple ceiling of %d; the bound "
            "produced no more pairs this pass", main_id, CEILING,
        )

    if plan.budget_reached:
        # Said, rather than reported after the fact: the couples beyond the
        # bound were never consulted, so nothing was overspent to learn this.
        #
        # **And they were dropped, not deferred.** This line said *"left for
        # the next pass"* and there is no backlog: the next pass's watermark
        # excludes the entries that produced them, so nothing reconsiders them
        # ever. Verified — pass one mints twenty-four with forty unbudgeted,
        # pass two considers none. CAP-7's matrix allows either answer and asks
        # only that the pass say which one it gave, so this says the one it
        # gives. A backlog would be durable state this story does not add.
        logger.info(
            "minting for main=%s stopped at its bound: %d judgement(s) bought, "
            "%d couple(s) dropped unjudged and not carried forward",
            main_id, consulted, plan.unbudgeted,
        )

    return MintResult(
        minted=tuple(minted),
        standing=plan.standing,
        passed=tuple(passed),
        unsaid=tuple(unsaid),
        skipped=tuple(skipped),
        unrecorded=tuple(unrecorded),
        consulted=consulted,
        turned_away=plan.turned_away,
        unbudgeted=plan.unbudgeted,
        considered=plan.considered,
        ceiling_reached=plan.ceiling_reached,
    )


__all__ = [
    "JUDGEMENTS",
    "MintResult",
    "Mints",
    "Slate",
    "consider",
    "fields_for",
    "linked",
    "slate",
]
