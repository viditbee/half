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

**A candidate may touch no loop at all, and that is what lets the feature
speak.** The first version required one, and composed with a second true fact —
that nothing in the product writes a ``loop`` onto a belief — into a surface
that was silent for every main for ever, with a green suite, because the
fixtures hand-wrote the association the product never makes. A candidate whose
entries sit on no wanting is bounded by the *other* two rules instead: it exists
only because a transition landed in the log, and it spends the main's one
unprompted message for the day. A loop with no *timescale* is a different case
and is still refused — there the wanting exists and its cadence does not, so
raising it would be raising it on a borrowed clock.

**A candidate touches every loop its entries name, all or nothing.** Splitting a
candidate per loop and narrowing its entries to that loop's — which the first
version did — made Half speak about a tension while showing one of the two
entries that disagree, and a tension *is* the pair. So the whole candidate
stands or falls: every loop it names must pass the bound, and a raise is
recorded for each.

**Silence is the ordinary outcome, and every branch here is written for it**
(AD-27). There is no fallback period and no default timescale. Most nights
produce no candidates at all, which is not a degraded pass; it is what a quiet
night is.

**Every candidate cites something the log still holds** (CAP-8). A candidate
carries an ``Origin`` — a kind out of a closed set and an id — and one whose
origin is not ``traceable``, or whose origin the main erased overnight, is
dropped before it is ranked. Nothing here invents a provenance, and there is no
branch that surfaces something because it looked important.

**The choice is deterministic given the log and an injected ``now``.** The
ordering is total: how many of its *own periods* the quietest loop it touches
has been silent, then the loops it names, then the origin's kind and id.
Nothing is ordered by dict iteration, by a float that could tie, or by a
collation — so two builds reading one log pick the same thing or pick nothing.

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
from half.store.ops import TOUCH_INGESTED, TOUCH_LOOP_TRANSITION, TOUCH_TENSION
from half.surface.touch import Origin, raised_at
from half.surface.view import SurfaceView

__all__ = [
    "Bound", "Candidate", "Choice", "NAGGING", "NOT_LIVE", "NO_LOOP",
    "NO_TIMESCALE", "ORIGIN_GONE", "REASONS", "UNKNOWN_TIMESCALE",
    "UNREADABLE_NOW", "UNREADABLE_TOUCH", "choices_for", "choose", "eligible",
    "live_origin", "touchable",
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
#: The raise on this loop carries neither a readable stamp nor a readable day,
#: so the interval cannot be measured. **Not a refusal** — see ``touchable``.
UNREADABLE_TOUCH: Final[str] = "unreadable-touch"
#: The candidate names a loop the ledger does not hold.
NO_LOOP: Final[str] = "no-loop"
#: The loop is `achieved`, `abandoned-but-unadmitted`, or in a state this build
#: does not recognise. Finished is not silent, and answered is not unasked.
NOT_LIVE: Final[str] = "not-live"
#: The candidate could not say where in the preceding pass it came from.
NO_ORIGIN: Final[str] = "no-origin"
#: The thing it cited is no longer in the log — the main erased it between the
#: night's pass and the morning.
ORIGIN_GONE: Final[str] = "origin-gone"

#: The closed set. Every value this module puts in a ``Bound`` is one of these,
#: so that a caller logging a reason logs a constant and never a message — an
#: exception message quotes the value that caused it, and here that is a record
#: out of a main's own ledger (AD-22).
REASONS: Final[frozenset[str]] = frozenset(
    {
        NAGGING, UNREADABLE_TOUCH, NO_LOOP, NOT_LIVE, NO_ORIGIN, ORIGIN_GONE,
        NO_TIMESCALE, UNKNOWN_TIMESCALE, UNREADABLE_NOW,
    }
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One thing the preceding pass produced that might be worth saying.

    A value, and deliberately a thin one. It carries **what it came from** and
    **which entries it would be built from** — and no loop, no rank, no score
    and no text. The loops are attached here, from the main's own belief
    records, rather than by the pass: the pass reads a projection of the log
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

    ``may_touch`` is true with ``reason`` set in exactly one case —
    ``UNREADABLE_TOUCH``, where the measure is gone and the loop is treated as
    never raised rather than as raised a moment ago. ``degraded`` says so, so a
    caller can count and log it instead of discovering it a year later.
    """

    may_touch: bool = False
    #: Set whenever the bound has something to report. One of ``REASONS``.
    reason: str | None = None
    #: True when ``may_touch`` was reached without a measurement.
    degraded: bool = False
    #: The loop's own period in days — never a borrowed default.
    period_days: int | None = None
    #: Days since Half last raised this loop. ``None`` when it never has, or
    #: when the interval could not be measured.
    since_days: float | None = None


@dataclass(frozen=True, slots=True)
class Choice:
    """One candidate with the loops it would touch. The unit of ranking.

    ``entries`` is the candidate's **whole** entry set, never narrowed to one
    loop's: a tension is a record of two entries that disagree, and speaking
    about it while showing one of them is not speaking about a tension.

    ``loops`` may be empty. A candidate built from beliefs that sit on no
    wanting raises nothing, is bounded by the day marker and by the transition
    rule, and is the shape a belief the product itself writes actually takes.
    """

    candidate: Candidate
    loops: tuple[str, ...]
    entries: tuple[str, ...]
    #: How many of its own periods the **quietest** loop this touches has been
    #: silent, or ``None`` when there is no loop or that is not detectable.
    periods: float | None = None
    #: Loops whose bound could not be measured and were treated as never
    #: raised. Carried so the surface can log and count it (see ``Bound``).
    degraded: tuple[str, ...] = ()

    @property
    def origin(self) -> Origin:
        return self.candidate.origin

    @property
    def order(self) -> tuple[float, str, str, str]:
        """The total order two builds must agree on.

        Silence in the loops' **own periods** first, quietest first: that is
        the unit ``half.loops.timescale`` exists to provide, so *"quieter"*
        means the same thing for a routine and for a farmland loop, and one
        comparison can mean the right thing for both. Raw days would rank a
        days-loop thirty days quiet — thirty of its own periods — below a
        farmland loop four hundred days quiet, which is barely one of its own,
        and ``tests/test_surface.py`` pins exactly that pair so the unit cannot
        revert without a case failing.

        Then the loops it names, then the origin's kind and id — strings that
        are unique together, so the order is total and no tie is broken by dict
        iteration or by a float comparison that happens to land equal.

        A candidate with no loop, or one whose silence is not detectable, sorts
        as zero: it is the least anchored thing that could be said, so it goes
        last rather than being refused.
        """
        return (
            -(self.periods or 0.0),
            " ".join(self.loops),
            self.origin.kind,
            self.origin.id,
        )


def live_origin(origin: Origin, *, view: SurfaceView) -> bool:
    """Whether the thing ``origin`` cites is still in the log.

    *"Nothing is surfaced that cannot say where it came from"* has a second
    half review had to point out: the thing cited must still be **there**. A
    tension expunged between the night's pass and the morning left a candidate
    that Half would still speak, and a touch that permanently cited an id
    nothing can resolve.

    Checked per kind, and every kind is checkable, which is why there is no
    default branch: a fourth kind added to ``TOUCH_ORIGINS`` fails here rather
    than passing unchecked.

    * a **tension** must still be in the tension table;
    * a **loop transition** must name a loop the ledger still holds;
    * an **ingested item** must still be the belief it was admitted as.

    An id in ``expunged`` is gone whatever else says: an erasure is an erasure.
    """
    if not isinstance(origin, Origin) or not origin.traceable:
        return False
    if origin.id in view.expunged:
        return False
    if origin.kind == TOUCH_TENSION:
        return origin.id in view.tensions
    if origin.kind == TOUCH_LOOP_TRANSITION:
        return origin.id not in view.expunged_loops and origin.id in view.loops
    if origin.kind == TOUCH_INGESTED:
        return origin.id in view.beliefs
    return False


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
    which is the correct direction here, because one nag is felt and one quiet
    day is not.

    Refused where the answer would have to be guessed:

    * a loop that is `achieved`, `abandoned-but-unadmitted`, or in a state this
      build does not recognise — finished is not silent, an answered question
      is not an unasked one, and a later build's state is not something to act
      on. This is ``ledger.silent``'s filter, asked here for the same reason;
    * a loop with no timescale, or one this build cannot read. **A loop with no
      period is not raised at all**, even the first time: the bound is *"never
      faster than its own timescale"*, and a wanting with no timescale has no
      own clock to be held to. (A candidate that names **no loop** is a
      different thing and is allowed — it touches no wanting, so there is
      nothing to pace, and the day marker paces it instead.)
    * a ``now`` that is not a real instant.

    **One case answers *yes* without a measurement, and it is a correction.**
    A raise whose stamp *and* stored day are both unreadable used to refuse —
    on the reasoning that refusing is the safe direction. That reasoning
    weighed one nag against one quiet day; it did not weigh one nag against
    *permanent* silence on a wanting, which is what it actually bought: the
    entry is replaced only by a later raise on that loop, a later raise happens
    only when the loop is chosen, and this branch is what stopped it being
    chosen. So an unmeasurable raise is treated as **no raise**, ``degraded``
    says so, and the surface logs and counts it. The cost is at most one extra
    raise on one loop, after which a readable record exists; and both sources
    are validated at the append, so producing the situation takes a hand edit.
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

    at = moment(now)
    if at is None:
        # The caller's own stamp, not the log's — reported separately because
        # the fix is a different one, exactly as ``timescale.silence`` does.
        return Bound(reason=UNREADABLE_NOW, period_days=period)

    table = touches if isinstance(touches, Mapping) else {}
    last = table.get(loop.id)
    if last is None:
        # Half has never raised this wanting. There is no interval, so there is
        # nothing to be faster than.
        return Bound(may_touch=True, period_days=period)
    raised = moment(raised_at(last))
    if raised is None:
        return Bound(
            may_touch=True, reason=UNREADABLE_TOUCH, degraded=True,
            period_days=period,
        )

    # Clamped, so a raise dated in the future cannot buy a loop a negative age
    # and let it be raised again immediately. The same clamp ``silence``
    # applies, for the same reason.
    days = max(0.0, (at - raised) / DAY)
    if days > period:
        return Bound(may_touch=True, period_days=period, since_days=days)
    return Bound(reason=NAGGING, period_days=period, since_days=days)


def choices_for(
    candidate: Candidate,
    *,
    view: SurfaceView,
    loops: Mapping[str, Loop],
    now: object,
) -> Choice | None:
    """``candidate`` as the one choice it is, or ``None``.

    ``None`` for every candidate that must not be surfaced, and the refusal is
    the enforcement:

    * an origin that cannot say where it came from, or one the log no longer
      holds — see ``live_origin``;
    * entries the fold no longer holds. A candidate over an entry a correction
      removed is a candidate about something that is not there any more, and
      quoting it would be quoting a claim the main has already taken back. **A
      candidate loses none of its entries and keeps going**: if one of a
      tension's two sides is gone, the tension is not a disagreement any more
      and the whole candidate goes;
    * any loop its entries name that the bound refuses. All or nothing: a raise
      that quietly touched a second wanting the bound never saw is a second
      wanting nagged with no record of it.

    A candidate whose entries name **no** loop is kept. It raises nothing, so
    there is nothing for the nagging bound to say about it, and the day marker
    plus the transition rule are what hold it.
    """
    if not isinstance(candidate, Candidate):
        return None
    if not live_origin(candidate.origin, view=view):
        return None
    if not candidate.entries:
        return None

    named: list[str] = []
    for entry in candidate.entries:
        record = view.beliefs.get(entry) if isinstance(entry, str) else None
        if not isinstance(record, Mapping):
            return None  # a side that is gone is not a side
        slug = record.get(LOOP)
        if isinstance(slug, str) and slug and slug not in named:
            named.append(slug)

    quietest: float | None = None
    degraded: list[str] = []
    for slug in named:
        bound = touchable(loops.get(slug), touches=view.touches, now=now)
        if not bound.may_touch:
            return None
        if bound.degraded:
            degraded.append(slug)
        held = loops.get(slug)
        periods = _periods(held, now=now) if held is not None else None
        if periods is not None and (quietest is None or periods > quietest):
            quietest = periods

    return Choice(
        candidate=candidate,
        # Sorted so that construction order does not depend on the order the
        # entries happened to arrive in. Everything below this module is
        # deterministic; nothing above it should have to hope so.
        loops=tuple(sorted(named)),
        entries=tuple(candidate.entries),
        periods=quietest,
        degraded=tuple(sorted(degraded)),
    )


def eligible(
    candidates: Iterable[Candidate] | None, *, view: SurfaceView, now: object
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
    held = read_loops(view.loops)
    found: list[Choice] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates or ():
        choice = choices_for(candidate, view=view, loops=held, now=now)
        if choice is None:
            continue
        # Deduplicated on exactly the key the ordering breaks ties with, so a
        # pass that produced the same candidate twice cannot make the order
        # depend on how many times it did.
        key = (choice.order[1], choice.origin.kind, choice.origin.id)
        if key in seen:
            continue
        seen.add(key)
        found.append(choice)
    return tuple(sorted(found, key=lambda choice: choice.order))


def choose(
    candidates: Iterable[Candidate] | None, *, view: SurfaceView, now: object
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
    found = eligible(candidates, view=view, now=now)
    return found[0] if found else None


def _periods(loop: Loop, *, now: object) -> float | None:
    """How many of its own periods ``loop`` has been silent, or ``None``."""
    quiet: Silence = loop.silence(now=now)
    return quiet.periods if quiet.detectable else None
