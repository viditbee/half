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

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

from half.consolidate import filter as relevance
from half.consolidate.candidates import (
    BOTH,
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
    unbudgeted: int = 0
    #: Couples already carrying a live tension. Recognised before the filter and
    #: long before the port, so nothing is spent on a disagreement Half has
    #: already recorded.
    standing: tuple[str, ...] = ()
    #: Couples the cheap filter turned away. Counted, because a filter whose
    #: rejections nothing can see is a filter nothing can assert.
    turned_away: int = 0
    #: Couples the bound produced at all — the number *"never all-pairs"* is a
    #: statement about.
    considered: int = 0

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
    #: Judgements actually bought. **Never more than ``JUDGEMENTS``.**
    consulted: int = 0
    #: Couples the filter turned away, before any of them cost anything.
    turned_away: int = 0
    #: Couples the filter admitted that the budget could not reach.
    unbudgeted: int = 0
    #: Couples the comparison bound produced at all.
    considered: int = 0

    @property
    def budget_reached(self) -> bool:
        """Whether this pass stopped minting because it had spent its bound."""
        return self.unbudgeted > 0

    @property
    def quiet(self) -> bool:
        """True when nothing was minted **and nothing failed**."""
        return not (self.minted or self.unrecorded or self.skipped)


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

    1. the **bound** — new or changed against the loop set and the subject set;
    2. **already linked** — recognised here, so a standing disagreement costs
       nothing at all, not even a filter pass;
    3. the **cheap filter** — before any model comparison, always;
    4. the **budget** — most surprising first, cut at ``JUDGEMENTS``.
    """
    known = read(view.beliefs)
    offered = couples(
        known,
        since=watermark(view.passes, now=now),
        loops=view.loops,
    )
    already = linked(view.tensions)
    standing: list[str] = []
    admitted: list[Couple] = []
    turned_away = 0
    for couple in offered:
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
    counts, total = relevance.corpus(known)
    queue = relevance.priority(admitted, counts=counts, total=total)
    return Slate(
        within=queue[:JUDGEMENTS],
        unbudgeted=max(len(queue) - JUDGEMENTS, 0),
        standing=tuple(standing),
        turned_away=turned_away,
        considered=len(offered),
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
    plan = slate(view, now=now)
    minted: list[str] = []
    passed: list[str] = []
    unsaid: list[str] = []
    skipped: list[str] = []
    unrecorded: list[str] = []
    consulted = 0

    for couple in plan.within:
        if judge is None:
            break
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
        consulted += 1
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

    if plan.budget_reached:
        # Said, rather than reported after the fact: the couples beyond the
        # bound were never consulted, so nothing was overspent to learn this.
        logger.info(
            "minting for main=%s stopped at its bound: %d judgement(s) bought, "
            "%d couple(s) left for the next pass",
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
