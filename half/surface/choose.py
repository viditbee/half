"""The candidate set, the nagging bound, and the one choice (CAP-8, CAP-10).

**Why the nagging bound lives here.** It was deferred alongside CAP-10's
interrupt rule, but it is not a governance feature — it is this module's
selection rule. *What is worth saying today* and *what may be touched today*
are one question, and a surface built without the bound is not a smaller
feature but a wrong one: ranking the candidate set and taking the best would
raise a years-long loop every single morning, which the glossary names as the
failure by name.

**Nagging is computed, never judged** (glossary). The bound is derived from the
loop's *own* period — a days-loop is held to a day and a years-loop to a year —
so there is no shared cadence anywhere in this file and no number that means
*"about right for most people"*. That is the one deliberate departure from the
reference implementation this is lifted from: gbrain's ``nudge.ts`` carries a
single ``NUDGE_COOLDOWN_DAYS = 14`` per (take, pattern) pair, which is correct
for a surface whose objects all move on one timescale and would be wrong here
in both directions at once — nagging a workout routine and never once reaching
a farmland loop. The *shape* is theirs: a durable record of every fire, keyed on
the thing raised, probed before the next one. The derivation is Half's.

**Silence is the ordinary outcome, and every branch here is written for it**
(AD-27). There is no fallback period, no default timescale, no *"we could not
tell, so raise it anyway"*. A loop whose bound cannot be computed is not a
candidate — because the alternative is holding a wanting to a cadence borrowed
from a wanting it is nothing like, and `half.loops.timescale` refuses to invent
one for exactly that reason. Most nights produce no candidates at all, which is
not a degraded pass; it is what a quiet night is.

**Every candidate cites the pass it came from** (CAP-8). A candidate carries an
``Origin`` — a kind out of a closed set and an id — and one whose origin is not
``traceable`` is dropped before it is ranked. Nothing here invents a
provenance, and there is no branch that surfaces something because it looked
important.

**The choice is deterministic given the log and an injected ``now``.** The
ordering is total: how many of its *own periods* the loop has been silent,
then the loop id, then the origin's kind and id. Nothing is ordered by dict
iteration, by a float that could tie, or by a collation — so two builds reading
one log pick the same thing or pick nothing.

Pure and clockless, like every module it reads from: ``now`` is the stamp the
caller was handed (AD-30).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from half.civil import DAY
from half.loops.ledger import LOOP, Loop
from half.loops.ledger import read as read_loops
from half.loops.states import LIVE_STATES
from half.loops.timescale import (
    NO_TIMESCALE,
    UNKNOWN_TIMESCALE,
    UNREADABLE_NOW,
    Silence,
    moment,
    period_days,
)
from half.surface.touch import Origin, raised_at

__all__ = [
    "Bound", "Candidate", "Choice", "NAGGING", "NOT_LIVE", "NO_LOOP",
    "NO_ORIGIN", "NO_TIMESCALE", "REASONS", "UNKNOWN_TIMESCALE",
    "UNREADABLE_NOW", "UNREADABLE_TOUCH", "candidates_for", "choose",
    "eligible", "touchable",
]

# Why a loop may not be touched now. Reasons rather than a bare ``False``, for
# the reason ``half.loops.timescale`` gives them: *"this loop has no period"*,
# *"Half raised it yesterday"* and *"this wanting is finished"* want different
# answers from whatever asks, and a caller handed only ``False`` cannot tell
# any of them apart.
#
# Three of them — NO_TIMESCALE, UNKNOWN_TIMESCALE and UNREADABLE_NOW — are
# imported rather than respelled: the timescale module owns the vocabulary for
# *"we cannot compute against this loop's period"*, and a second spelling here
# would be a second, weaker copy of the same refusal.

#: Half raised this loop more recently than one of its own periods ago. The
#: bound firing, which is the ordinary reason a good candidate is not surfaced.
NAGGING: Final[str] = "nagging"
#: The touch record's own stamp could not be read, so the interval cannot be
#: measured. Refused rather than assumed fresh — see ``touchable``.
UNREADABLE_TOUCH: Final[str] = "unreadable-touch"
#: The candidate names no loop the ledger holds. A surface that touches no
#: wanting is bounded by nothing.
NO_LOOP: Final[str] = "no-loop"
#: The loop is `achieved`, `abandoned-but-unadmitted`, or in a state this build
#: does not recognise. Finished is not silent, and answered is not unasked.
NOT_LIVE: Final[str] = "not-live"
#: The candidate could not say where in the preceding pass it came from.
NO_ORIGIN: Final[str] = "no-origin"

#: The closed set. Every value this module puts in a ``Bound`` is one of these,
#: so that a caller logging a reason logs a constant and never a message — an
#: exception message quotes the value that caused it, and here that is a record
#: out of a main's own ledger (AD-22).
REASONS: Final[frozenset[str]] = frozenset(
    {
        NAGGING, UNREADABLE_TOUCH, NO_LOOP, NOT_LIVE, NO_ORIGIN,
        NO_TIMESCALE, UNKNOWN_TIMESCALE, UNREADABLE_NOW,
    }
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One thing the preceding pass produced that might be worth saying.

    A value, and deliberately a thin one. It carries **what it came from** and
    **which entries it would be built from** — and no loop, no rank, no score
    and no text. The loop is attached here, from the main's own belief records,
    rather than by the pass: the pass reads a narrowed projection of the log
    that drops every field but the id, the stamp and the support set (AD-22,
    ``records.HISTORY_VISIBLE``), so it cannot see which wanting an entry sits
    on and must not be widened until it can.

    ``entries`` are belief ids. For a tension they are the two it links; for a
    loop transition, the entries that sit on that loop; for an ingested item,
    the entry it was admitted as. What may actually be *said* about any of them
    is the ladder's question and the context builder's, asked in
    ``half.surface.morning`` and not here.
    """

    origin: Origin
    entries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Bound:
    """Whether one loop may be raised at ``now``, and why not.

    A value. It decides nothing, writes nothing, and is recomputed from the
    fold every time it is wanted — for the reason ``Silence`` is: a stored
    *"may raise"* flag would be a fact about the moment it was written, and
    keeping it current means writing on a read (AD-4, AD-30).

    ``may_touch`` is never true while ``reason`` is set. There is no path here
    from *"we cannot tell"* to *"go ahead"*.
    """

    may_touch: bool = False
    #: Set exactly when ``may_touch`` is false. One of ``REASONS``.
    reason: str | None = None
    #: The loop's own period in days — never a borrowed default.
    period_days: int | None = None
    #: Days since Half last raised this loop. ``None`` when it never has, or
    #: when the interval could not be measured.
    since_days: float | None = None


@dataclass(frozen=True, slots=True)
class Choice:
    """One candidate, attached to the loop it would touch. The unit of ranking.

    ``entries`` is narrowed to the entries sitting on **this** loop, which is
    what makes a candidate spanning two loops into two self-contained choices
    rather than one raise that quietly touches a second wanting the bound never
    saw.
    """

    candidate: Candidate
    loop: str
    entries: tuple[str, ...]
    #: How many of its own periods this loop has been silent, or ``None`` when
    #: that is not detectable — which is ordinary for a loop that has a period
    #: but has not moved yet.
    periods: float | None = None

    @property
    def origin(self) -> Origin:
        return self.candidate.origin

    @property
    def order(self) -> tuple[float, str, str, str]:
        """The total order two builds must agree on.

        Silence in the loop's **own periods** first, longest first: that is the
        unit ``half.loops.timescale`` exists to provide, so *"quieter"* means
        the same thing for a routine and for a farmland loop, and one
        comparison can mean the right thing for both. Then the loop id, then
        the origin's kind and id — three strings that are unique together, so
        the order is total and no tie is broken by dict iteration or by a
        float comparison that happens to land equal.

        Undetectable silence sorts as zero rather than being excluded: a loop
        with a period that has simply never moved is a perfectly ordinary
        candidate, and *"we cannot tell how quiet it is"* is a reason to rank
        it last, not a reason to refuse it.
        """
        return (
            -(self.periods or 0.0),
            self.loop,
            self.origin.kind,
            self.origin.id,
        )


def touchable(
    loop: Loop | None, *, touches: Mapping[str, Mapping[str, Any]] | None, now: object
) -> Bound:
    """Whether Half may raise ``loop`` at ``now`` without nagging.

    Pure: the same loop, the same touch table and the same ``now`` give the
    same answer for ever.

    **The bound is one of the loop's own periods.** *"Nagging — touching an
    open loop faster than that loop's own timescale"* (glossary) is the whole
    derivation, and it is deliberately not a fraction of a period, a multiple
    of one, or a number beside one: any of those would be a cadence somebody
    chose, and the glossary defines the condition as computable rather than
    chosen.

    **The boundary is strict, and it is the same boundary
    ``timescale.silence`` uses.** A loop may be raised when *more* than one of
    its own periods has passed; at exactly one period it may not. That matches
    ``Silence.silent = days > period`` rather than inventing a second
    convention for the same comparison, and it errs toward the quiet side —
    which is the correct direction here, because the cost of the two mistakes
    is not symmetric: one nag is felt, one quiet day is not.

    ``None`` for every case where the answer would have to be guessed, and each
    of them is a refusal rather than a permission:

    * a loop that is `achieved`, `abandoned-but-unadmitted`, or in a state this
      build does not recognise — finished is not silent, an answered question
      is not an unasked one, and a later build's state is not something to act
      on. This is ``ledger.silent``'s filter, asked here for the same reason;
    * a loop with no timescale, or one this build cannot read. **A loop with no
      period is not raised at all**, even the first time. The bound is *"never
      faster than its own timescale"*, and a wanting with no timescale has no
      own clock to be held to — raising it would be raising it on a borrowed
      cadence, which is precisely what ``half.loops.timescale`` refuses to
      invent. Recording the loop without a period is honest; raising it anyway
      is not;
    * a touch whose stamp, or a ``now``, that is not a real instant. Refusing
      is the safe direction: reading an unmeasurable interval as *long enough*
      is how a bound stops bounding.
    """
    if not isinstance(loop, Loop):
        return Bound(reason=NO_LOOP)
    if loop.state not in LIVE_STATES:
        return Bound(reason=NOT_LIVE)
    if loop.timescale is None:
        return Bound(reason=NO_TIMESCALE)
    period = period_days(loop.timescale)
    if period is None:
        return Bound(reason=UNKNOWN_TIMESCALE)

    table = touches if isinstance(touches, Mapping) else {}
    last = table.get(loop.id)
    if last is None:
        # Half has never raised this wanting. There is no interval, so there is
        # nothing to be faster than.
        return Bound(may_touch=True, period_days=period)
    raised = moment(raised_at(last))
    if raised is None:
        return Bound(reason=UNREADABLE_TOUCH, period_days=period)
    at = moment(now)
    if at is None:
        # The caller's own stamp, not the log's — reported separately because
        # the fix is a different one, exactly as ``timescale.silence`` does.
        return Bound(reason=UNREADABLE_NOW, period_days=period)

    # Clamped, so a touch dated in the future cannot buy a loop a negative age
    # and let it be raised again immediately. The same clamp ``silence``
    # applies, for the same reason.
    days = max(0.0, (at - raised) / DAY)
    if days > period:
        return Bound(may_touch=True, period_days=period, since_days=days)
    return Bound(reason=NAGGING, period_days=period, since_days=days)


def candidates_for(
    candidate: Candidate,
    *,
    beliefs: Mapping[str, Mapping[str, Any]] | None,
    loops: Mapping[str, Loop],
    now: object,
) -> list[Choice]:
    """``candidate`` split into one ``Choice`` per loop it would touch.

    Empty for every candidate that must not be surfaced, and the emptiness is
    the enforcement:

    * an origin that cannot say where it came from — *"nothing is surfaced that
      cannot say where it came from"* (CAP-8), asked through
      ``Origin.traceable`` so that a new way of failing to cite anything is
      caught by the same predicate as a known one;
    * entries the fold no longer holds. A candidate over an entry a correction
      removed is a candidate about something that is not there any more, and
      quoting it would be quoting a claim the main has already taken back;
    * entries that sit on no loop the ledger holds. A surface that touches no
      wanting is bounded by nothing, and unbounded is the failure this module
      exists to prevent.

    A candidate whose entries sit on **two** loops becomes two choices, each
    narrowed to its own loop's entries. That is deliberate rather than
    convenient: one raise quietly touching a second wanting is a second wanting
    nagged with no record of it, and the bound only protects the loop the touch
    names.
    """
    if not isinstance(candidate, Candidate) or not candidate.origin.traceable:
        return []
    held: Mapping[str, Mapping[str, Any]] = (
        beliefs if isinstance(beliefs, Mapping) else {}
    )
    by_loop: dict[str, list[str]] = {}
    for entry in candidate.entries:
        record = held.get(entry) if isinstance(entry, str) else None
        if not isinstance(record, Mapping):
            continue
        slug = record.get(LOOP)
        if not isinstance(slug, str) or slug not in loops:
            continue
        by_loop.setdefault(slug, []).append(entry)
    return [
        Choice(
            candidate=candidate,
            loop=slug,
            entries=tuple(entries),
            periods=_periods(loops[slug], now=now),
        )
        # Sorted so that the *construction* order does not depend on the order
        # ``entries`` happened to arrive in either. Everything below this
        # module is deterministic; nothing above it should have to hope so.
        for slug, entries in sorted(by_loop.items())
    ]


def eligible(
    candidates: Iterable[Candidate] | None,
    *,
    beliefs: Mapping[str, Mapping[str, Any]] | None,
    loops: Mapping[str, Mapping[str, Any]] | None,
    touches: Mapping[str, Mapping[str, Any]] | None,
    now: object,
) -> tuple[Choice, ...]:
    """Every choice that may be raised at ``now``, best first.

    Total and never raises: a candidate this build cannot make sense of is
    absent from the result rather than an exception, because the alternative to
    dropping one is dropping the main's whole morning — and because there is a
    correct outcome for *"we could not tell"* and it is silence (AD-27).

    The bound is applied here rather than in ``choose``, so *"the ranking sees
    only what may be touched"* is true of the whole list and not merely of the
    element that happened to come first. Ranking first and bounding afterwards
    would produce a surface that goes quiet whenever its best candidate is
    nagging — one that has candidates and says nothing — which is a different
    and worse rule than the one this story states.
    """
    held = read_loops(loops)
    found: list[Choice] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates or ():
        for choice in candidates_for(
            candidate, beliefs=beliefs, loops=held, now=now
        ):
            if not touchable(
                held.get(choice.loop), touches=touches, now=now
            ).may_touch:
                continue
            # Deduplicated on exactly the key the ordering breaks ties with, so
            # a pass that produced the same candidate twice cannot make the
            # order depend on how many times it did.
            key = (choice.loop, choice.origin.kind, choice.origin.id)
            if key in seen:
                continue
            seen.add(key)
            found.append(choice)
    return tuple(sorted(found, key=lambda choice: choice.order))


def choose(
    candidates: Iterable[Candidate] | None,
    *,
    beliefs: Mapping[str, Mapping[str, Any]] | None,
    loops: Mapping[str, Mapping[str, Any]] | None,
    touches: Mapping[str, Mapping[str, Any]] | None,
    now: object,
) -> Choice | None:
    """The one thing worth saying at ``now``, or ``None``.

    ``None`` is the ordinary answer and carries no reason, because there is
    nothing to explain: a night on which the pass moved nothing produces no
    candidates at all, and a night whose candidates are all inside their own
    loops' periods produces none that may be raised. Neither is a failure and
    neither is logged as one (AD-27).

    Exactly one, never two. The matrix row is *"several candidates → exactly
    one is sent"*, and this is where that is true: the caller gets a single
    ``Choice`` and there is no plural door out of this module onto the send
    path.
    """
    found = eligible(
        candidates, beliefs=beliefs, loops=loops, touches=touches, now=now
    )
    return found[0] if found else None


def _periods(loop: Loop, *, now: object) -> float | None:
    """How many of its own periods ``loop`` has been silent, or ``None``."""
    quiet: Silence = loop.silence(now=now)
    return quiet.periods if quiet.detectable else None
