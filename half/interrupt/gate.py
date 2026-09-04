"""The interruption: five refusals, its own bound, and usually silence (CAP-10).

*"An unprompted interruption occurs only when waiting would destroy an
option."* The valuable half of that sentence is the **only**, and this module
is the only. Five gates run in a fixed order and every one of them can refuse:

1. **the mode** — a main in crisis is not interrupted, and is not reasoned
   about either (CAP-12);
2. **reachability** — the platform is asked whether an unprompted message is
   permitted at all, and is never assumed (AD-7);
3. **the ceiling** — a main capped below the rung an unprompted surface speaks
   from has nothing said to them (AD-28);
4. **the nagging bound** — no wanting is raised faster than its own timescale,
   read from the same ``PERIOD_DAYS`` table ``timescale.silence``,
   ``choose.touchable`` and ``questions.answered`` read;
5. **urgency** — and only an explicit *yes* from a judge may interrupt.

Beside them sits **the interruption's own bound**, which is not one of the
five: a main who has just been interrupted is not interrupted again, whatever
it would be about.

**Why urgency is judged last, and why that ordering is load-bearing rather
than stylistic.** The first four refusals are free and local — a boolean, a
platform query, a comparison of two rungs and arithmetic over the fold — and
judging before them would spend a model call on turns that were never going to
send. Worse, it would let a main *in the mode* be reasoned about, which CAP-12
forbids more strongly than it forbids sending. So the judge is unreachable for
a main who could not have been sent to anyway, and
``tests/test_interrupt.py`` asserts that by **counting calls and asserting
zero** rather than by handing in a double that raises: a raising double is
converted into a legal value two frames up by the very catch this module needs,
so the assertion would pass whether the ordering held or was inverted.

**Nothing here writes a record.** Like ``half.governance.ladder``,
``half.loops.ledger`` and ``half.surface.touch``, the rule is separated from the
append: the bound reads a stamp it is handed and this module has no store, no
mutex and no path to a log. The record an interruption will eventually write is
already built — ``half.surface.touch.raised``, which raises a loop and
deliberately **spends no day**, so an interruption can never eat the morning's
one-a-day budget. Supplying its writer is the story that supplies a judge;
neither is here, and this build sends nothing to anybody.

**Silence is the ordinary outcome** (AD-27). Most passes produce no
interruption, and a build that never produces one is a correct build. There is
no branch here that looks for something to interrupt about because staying
quiet felt like a bug, no retry, no queue and no escalation.

**It speaks through the voice** (13a/13b) — the same composer, the same cheap
judge, the same verbatim tripwire and the same fallback ladder as the morning
and the turn. There is no template on any path out of this module and no
scaffolding on the wire; an interruption is the last place in this product that
should read like a form letter.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from half.channel.port import Channel, Reachability, SendResult
from half.civil import DAY
from half.context.build import split as split_context
from half.governance.ladder import height
from half.interrupt.port import Option, Urgency
from half.loops.ledger import LOOP, Loop
from half.loops.ledger import read as read_loops
from half.loops.timescale import PERIOD_DAYS, Silence, Timescale, moment
from half.retrieval.port import Candidate as RankedBelief
from half.schedule.clock import Now
from half.surface.choose import NAGGING, touchable
from half.surface.morning import (
    CRISIS,
    NOTHING_MAY_BE_SAID,
    SPEAKS_AT,
    UNREADABLE,
    UNSENT,
    speech,
)
from half.surface.view import SurfaceView
from half.voice.compose import sample_from
from half.voice.gate import SILENCES, Spoken, Voice

logger = logging.getLogger(__name__)

__all__ = [
    "BOUND_SECONDS", "CANNOT_SAY", "CAPPED", "CRISIS", "INTERRUPTION_DAYS",
    "JUDGEMENTS", "JUST_INTERRUPTED", "Interrupt", "NAGGING", "NO_JUDGE",
    "NOTHING_CLOSING", "NOTHING_MAY_BE_SAID", "NOTHING_TO_WEIGH", "OwnBound",
    "REASONS", "SPEAKS_AT", "UNREADABLE", "UNREADABLE_LAST", "UNSENT",
    "Weighed", "delivered", "material_for", "option_for", "unspent",
    "weighable",
]


# -- the numbers -------------------------------------------------------------

#: What one interruption costs the main, in days — **the interruption's own
#: bound**, and it is per main rather than per wanting.
#:
#: **Read from the open-loop vocabulary, not typed here.** It is
#: ``PERIOD_DAYS[Timescale.DAYS]``, the shortest period the ledger has a name
#: for, which is the same derivation and the same table
#: ``half.trust.stakes.INTERRUPTION_DAYS`` uses for the same sentence: *an
#: unprompted message is felt for the main's day and is then over.* Writing
#: ``1`` here would be a number nobody could later argue with.
#:
#: **Why it is not the interrupted wanting's own period.** That was the first
#: version, and it is gbrain's global-cooldown failure wearing Half's clothes:
#: an interruption about a farmland loop would have silenced a days-loop for a
#: year. The manifest's nudge-cooldown row records the lesson in the other
#: direction — one global number nags a fast loop and never reaches a slow one
#: — and the answer to both is that the *per-wanting* clock is gate 4's job and
#: this bound is a different fact: what an unexpected message costs the person
#: receiving it, which does not vary with what it was about.
#:
#: **This is where "bounded harder than a morning" is true, and it is
#: demonstrable rather than asserted.** The morning's one-a-day rule is the
#: main's own **civil** day, read from a stored marker (``touch.spoken_on``), so
#: two mornings twenty minutes apart either side of local midnight are legal.
#: This bound is a **rolling** day measured from the last interruption, so the
#: same pair is refused — and an interruption spends no morning marker, so it
#: can never be satisfied by one.
INTERRUPTION_DAYS: Final[int] = PERIOD_DAYS[Timescale.DAYS]

#: How many urgency judgements one main's pass may buy. **Three, and this is
#: the one number in this module a reviewer has to argue about**, exactly as
#: ``half.consolidate.mint.JUDGEMENTS`` says of its twenty-four.
#:
#: A count of *consultations*, because the consultation is the cost: the total
#: order, the four refusals and the bound are arithmetic over a fold that is
#: already in memory. The pass asks about its wantings quietest-first and
#: **stops at the first one judged closing**, so the ordinary shape of a
#: spending pass is one call, and this is the ceiling on a pass that keeps
#: hearing *no*.
#:
#: Three rather than twenty-four because the two budgets buy different things.
#: Minting buys a nightly sweep over a ledger nobody sees; this buys the right
#: to speak out of turn, and a main whose three quietest wantings are all
#: judged *not closing* has told Half something about the day — that nothing is
#: closing — which is worth more than a fourth opinion. It is **pinned by
#: value** in ``tests/test_interrupt.py`` the way ``JUDGEMENTS`` and
#: ``PERSISTENCE_DAYS`` are: raising it is a red test and a deliberate edit,
#: never a quiet multiplication of every main's bill.
JUDGEMENTS: Final[int] = 3

#: How long one urgency judgement may take before the pass gives up on it.
#:
#: Five seconds, the same bound ``half.consolidate.judge`` gives the
#: disagreement judgement, and for the same reason: both are classifications
#: made on an unattended pass with nobody waiting, inside a tick whose own
#: per-main timeout (``half.schedule.tick.DEFAULT_TIMEOUT``) has to cover
#: everything else that pass does as well. The number is spelled here rather
#: than imported from that module because ``half.consolidate.judge`` is a
#: *provider* and this package deliberately has none — importing it would give
#: ``half/interrupt`` a name from a package it must not depend on, for one
#: float.
#:
#: **What it bounds is the gate, not the judge.** A judge with its own bound
#: will have a shorter one; this is the promise that a judge with none — or one
#: that hangs — costs a pass five seconds and a main nothing at all.
BOUND_SECONDS: Final[float] = 5.0


# -- the vocabulary ----------------------------------------------------------
#
# Reasons rather than a bare ``None``, for the reason ``half.surface.morning``
# and ``half.loops.timescale`` give theirs: *"nobody may be reached"*,
# *"nothing is closing"* and *"there is no judge"* are different facts, and a
# caller handed only silence cannot tell any of them apart — which matters more
# here than anywhere else in the product, because **this build ships with no
# judge**, so *never asked* is the state it is actually in.
#
# Four of them are imported rather than respelled. ``CRISIS``,
# ``NOTHING_MAY_BE_SAID``, ``UNSENT`` and ``UNREADABLE`` are the morning's, and
# they mean here exactly what they mean there; a second spelling of *"the mode
# is open"* is a second, weaker copy of the same refusal. ``NAGGING`` is
# ``half.surface.choose``'s, which owns the bound this gate asks.

#: The main's global cap is below the rung an unprompted surface may speak
#: from, so nothing could be said whatever the judge thought (AD-28). Answered
#: **before** the judge, because it is free — see ``Interrupt._consider``.
CAPPED: Final[str] = "capped"
#: The interruption's own bound. Half interrupted this main inside the last
#: ``INTERRUPTION_DAYS``, about anything at all.
JUST_INTERRUPTED: Final[str] = "just-interrupted"
#: The stamp on the last interruption could not be read, and neither could the
#: caller's ``now``. **Not a refusal on its own** — see ``unspent``.
UNREADABLE_LAST: Final[str] = "unreadable-last-interruption"
#: This main holds no wanting at all, so there is no option to be closing. The
#: ordinary state of a new main.
NOTHING_TO_WEIGH: Final[str] = "nothing-to-weigh"
#: Every wanting that got as far as the judge was answered *not closing*,
#: *cannot say*, or not at all. **The ordinary refusal** — most days nothing is
#: closing, and this is what that looks like.
NOTHING_CLOSING: Final[str] = "nothing-closing"
#: No urgency source is wired. **The shipped build**, and a fact of its own
#: rather than a flavour of ``NOTHING_CLOSING``: a pass that asked nobody and a
#: pass that asked three judges and heard *no* three times are different passes,
#: and the first is the one this composition is in for ever.
NO_JUDGE: Final[str] = "no-judge"

#: A judge said it could not say — degraded, unsure, over its cap, declining.
#: **Never collapsed into ``NOTHING_CLOSING``'s count**; see ``Weighed.unsaid``.
#: Present in the set because it is a reason a *judgement* produced nothing, and
#: absent from any ``Weighed.reason`` for the reason ``Weighed`` gives.
CANNOT_SAY: Final[str] = "cannot-say"

#: Every reason an interruption did not happen. Closed, so a caller counting
#: refusals counts constants and never a message — an exception message
#: routinely quotes the value that caused it, and here that value is a record
#: out of a main's own ledger (AD-22).
#:
#: ``Reachability``'s own refusals join them: *"Half may not send unprompted
#: right now"* is the port's answer and the port owns its spelling (AD-7). So do
#: the composer's, whole rather than collapsed into one, for the reason
#: ``half.surface.morning.REASONS`` gives — and read from ``voice.gate.SILENCES``
#: rather than spelled again, so a reason added there cannot become one this
#: module silently fails to count.
REASONS: Final[frozenset[str]] = frozenset(
    {
        CRISIS, CAPPED, JUST_INTERRUPTED, NOTHING_TO_WEIGH, NAGGING,
        NOTHING_CLOSING, NO_JUDGE, NOTHING_MAY_BE_SAID, UNSENT, UNREADABLE,
        *SILENCES,
        *(str(answer) for answer in Reachability if not answer.may_send_freeform),
    }
)


# -- the values --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OwnBound:
    """Whether the interruption's own bound permits one now, and why not.

    A value, recomputed from the stamp it is handed every time it is wanted —
    for the reason ``choose.Bound`` and ``timescale.Silence`` are: a stored
    *"may interrupt"* flag is a fact about the moment it was written, and
    keeping it current means writing on a read (AD-4, AD-30).

    ``may_interrupt`` is true with ``reason`` set in exactly one case —
    ``UNREADABLE_LAST`` — and ``degraded`` says so, for the reason
    ``choose.Bound`` gives: a stamp nothing can read is replaced only by a later
    interruption, a later interruption happens only if this bound permits one,
    and refusing would therefore have silenced this main's interruptions for
    ever over one corrupt value. The cost of the other direction is at most one
    extra interruption — and even that has to get past a judge saying *closing*
    first, which this build has none of.
    """

    may_interrupt: bool = False
    #: One of ``REASONS`` when refusing, or ``UNREADABLE_LAST`` when degraded.
    reason: str | None = None
    #: True when ``may_interrupt`` was reached without a measurement.
    degraded: bool = False
    #: Days since the last interruption. ``None`` when there has never been
    #: one, or when the interval could not be measured.
    since_days: float | None = None
    #: What one interruption costs, for comparison. Carried on the value so a
    #: caller can show the comparison rather than restate half of it — the
    #: choice ``half.trust.stakes.Stakes`` already makes.
    interruption_days: int = INTERRUPTION_DAYS


@dataclass(frozen=True, slots=True)
class Weighed:
    """What one pass over one main's options did. Counts and ids — never
    content in anything durable (AD-22).

    ``text`` is what went on the wire, and it travels **on this value only**:
    nothing in this module writes, there is no field on any record in
    ``half.surface.touch`` a sentence could go in, and a replay of a log
    carrying interruptions folds identically because none of this is in it
    (AD-4, AD-30).

    ``reason`` is set exactly when nothing was sent, and is one of ``REASONS``.

    **The three verdicts are counted apart and no two of them share a field.**
    ``closing`` is a judge saying yes, ``not_closing`` is a judge saying no, and
    ``unsaid`` is a judge saying it cannot say — which is not *no*, and folding
    them together would leave a suite asserting *"nothing was sent"* passing
    whether the port answered or was never reached at all. ``unwired`` is the
    fourth state and is a boolean rather than a count, because *nobody was
    asked* is not a smaller number of the same thing.
    """

    #: The wanting Half interrupted about, or ``None``. **One, never a
    #: tuple**: at most one interruption leaves this module per pass, and there
    #: is no plural door out of it onto the send path, so a digest is not a
    #: thing this shape can express.
    sent: str | None = None
    #: What went on the wire. Composed prose, and never written anywhere.
    text: str = ""
    #: Why nothing was sent. One of ``REASONS``; ``None`` only when ``sent``.
    reason: str | None = None
    #: Wantings the total order produced at all, before the bound saw them.
    considered: int = 0
    #: Wantings the per-loop clock refused — nagging, finished, or with no
    #: period of their own. Counted, because a bound whose refusals nothing can
    #: see is a bound nothing can assert.
    bounded: int = 0
    #: Wantings raised without a measurable last raise — see ``choose.Bound``.
    #: Counted because it is the shape of a corruption nobody would notice.
    degraded: int = 0
    #: Urgency judgements actually bought. **Never more than ``JUDGEMENTS``**,
    #: and counted before the call rather than after it: a judgement that raised
    #: had still been bought, and billing it only on success reports zero for a
    #: provider that failed every time.
    consulted: int = 0
    #: Judgements that answered *closing*. At most one, because the pass stops
    #: at the first.
    closing: int = 0
    #: Judgements that answered *not closing*.
    not_closing: int = 0
    #: Judgements that answered *cannot say*. **Kept apart from
    #: ``not_closing``** — see the class note.
    unsaid: int = 0
    #: Judgements that raised or ran past ``BOUND_SECONDS``. That option is
    #: skipped and the pass goes on to the next.
    failed: int = 0
    #: Whether there was no judge to ask. **A fact of its own**, and the state
    #: this build ships in.
    unwired: bool = False

    @property
    def interrupted(self) -> bool:
        """Whether anything was actually sent. The predicate the runtime and
        the tests read, rather than two spellings of ``sent is not None``."""
        return self.sent is not None


# -- the rules ---------------------------------------------------------------


def unspent(last: object, *, now: object) -> OwnBound:
    """Whether the interruption's own bound permits one at ``now``.

    Pure: the same stamp and the same ``now`` give the same answer for ever.
    Never raises.

    ``last`` is the stamp of the most recent interruption Half sent this main,
    **whatever it was about**, or ``None`` if it never has. It is handed in
    rather than read, exactly as ``choose.touchable`` is handed the touch table:
    the rule is separated from the append, so it is testable without a store and
    the single writer stays where AD-1 put it.

    **Strictly greater, and the boundary is the ledger's own.** A main may be
    interrupted when *more* than ``INTERRUPTION_DAYS`` has passed; at exactly a
    day they may not. That is ``Silence.silent``'s ``days > period`` and
    ``touchable``'s boundary rather than a second convention for the same
    comparison, and it errs toward the quiet side — the correct direction,
    because one unexpected message is felt and one quiet day is not.

    Clamped, so an interruption stamped in the future cannot buy a main a
    negative age and let the next one through immediately — the same clamp
    ``silence`` and ``touchable`` apply, for the same reason.
    """
    at = moment(now)
    if at is None:
        # The caller's own stamp, not the log's. Reported apart because the fix
        # is a different one — exactly as ``timescale.silence`` does.
        return OwnBound(reason=UNREADABLE)
    if last is None:
        # Half has never interrupted this main. There is no interval, so there
        # is nothing to be inside of.
        return OwnBound(may_interrupt=True)
    since = moment(last)
    if since is None:
        return OwnBound(
            may_interrupt=True, reason=UNREADABLE_LAST, degraded=True
        )
    days = max(0.0, (at - since) / DAY)
    if days > INTERRUPTION_DAYS:
        return OwnBound(may_interrupt=True, since_days=days)
    return OwnBound(reason=JUST_INTERRUPTED, since_days=days)


def weighable(view: SurfaceView, *, now: object) -> tuple[Loop, ...]:
    """Every wanting this main holds, in the order the gate weighs them.

    **Nothing is filtered here.** The dead loops, the ones with no timescale and
    the ones this build cannot read are all in the result, and gate 4 refuses
    them through ``choose.touchable`` — one filter, in the module that owns it,
    with its own reasons. A pre-filter here would be a second, weaker copy of
    that rule and would make three of ``touchable``'s four refusals unreachable
    from this path, which is a guard that cannot fire.

    **The order is total and it is the same unit ``choose.Choice.order``
    uses**: how many of its *own* periods each wanting has been silent,
    quietest first, then the loop's id. Raw days would rank a days-loop thirty
    days quiet — thirty of its own periods — below a farmland loop four hundred
    days quiet, which is barely one of its own. A wanting whose silence is not
    detectable sorts as zero and therefore last: it is the least anchored thing
    that could be interrupted about, so it goes to the back rather than being
    refused here.

    Ids are unique, so no tie is broken by dict iteration or by a float
    comparison that happens to land equal: two builds reading one log weigh the
    same wantings in the same order or weigh none.
    """
    held = read_loops(view.loops)
    return tuple(
        sorted(
            held.values(),
            key=lambda loop: (-(_periods(loop, now=now) or 0.0), loop.id),
        )
    )


def option_for(loop: Loop, *, view: SurfaceView) -> Option:
    """``loop`` as the urgency judge sees it, and no more of it than that.

    The narrowing is here rather than in the judge, which is the rule
    ``half.consolidate.port`` states: what a judge can see is decided at the
    door, so a later implementation cannot widen its own input by asking for
    more. Nothing on an ``Option`` names the main, a belief, a license, a
    support set or a platform.
    """
    return Option(
        loop=loop.id,
        timescale=loop.timescale,
        last_movement=loop.last_movement,
        claims=tuple(claim for _, claim in _entries(view, loop.id)),
    )


def material_for(view: SurfaceView, *, loop: str) -> tuple[RankedBelief, ...]:
    """The belief records that sit on ``loop``, as the context builder takes
    them.

    Held as a value rather than built twice because two things are computed from
    it — the context the composer writes from and the withheld set the tripwire
    reads — and a second construction is a second chance for the two to disagree
    about what was in the material, which on this path is two chances for the
    tripwire to watch for the wrong words.
    """
    return tuple(
        RankedBelief(
            id=ident,
            claim=claim,
            prefix="",
            bm25=None,
            belief=view.beliefs.get(ident) or {},
        )
        for ident, claim in _entries(view, loop)
    )


def delivered(result: object) -> bool:
    """Whether the channel says it carried anything.

    ``Channel.send``'s own contract: ``SendResult.parts`` is how many physical
    messages the platform accepted and **zero means nothing was delivered**,
    which an adapter may answer instead of raising. A caller that discards the
    result records a non-delivery as a message sent — which is how the morning
    surface once spent a main's whole day on nothing.

    Tolerant of an adapter that returns nothing at all: an adapter answering
    ``None`` has not said it failed, so only an explicit *no parts* is read as
    non-delivery and a stricter reading cannot silence a working adapter.

    ``tests/test_interrupt.py`` sweeps this against
    ``half.surface.morning``'s own reading of the same contract sentence, so the
    two cannot drift into disagreeing about what the port promised.
    """
    if isinstance(result, SendResult):
        return result.parts > 0
    return True


# -- the gate ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Interrupt:
    """One main, one instant, at most one thing said out of turn.

    ``channel`` is asked whether Half may send unprompted and is then asked to
    send; it is never asked which platform it is (AD-7). ``voice`` writes the
    sentence. ``urgency`` decides whether waiting would destroy an option — and
    **is ``None`` in the shipped composition**, which is why this build never
    interrupts anybody.
    """

    channel: Channel
    #: Who decides whether an option is closing (CAP-10). ``None`` is the
    #: shipped state and is not a degraded one: with no judge the mode, the
    #: platform, the ceiling, the bound and the per-loop clock are all still
    #: exercised on every pass — which is what keeps CAP-10's whole rule under
    #: test with no provider anywhere in the tree — and nothing is ever sent.
    urgency: Urgency | None = None
    #: Who writes the sentence (13a/13b). **Defaulted to a voice with no
    #: holders**, which composes nothing for anybody, so a gate built without
    #: one is silent rather than falling back to a template. That is the
    #: fail-closed direction and the one this product can ship worldwide.
    voice: Voice = field(default_factory=Voice)

    async def consider(
        self,
        view: SurfaceView,
        *,
        main_id: str,
        now: Now,
        in_crisis: bool,
        last_interruption: str | None,
    ) -> Weighed:
        """Interrupt this main about one thing, or say nothing. Never raises.

        **``in_crisis`` and ``last_interruption`` are required and have no
        defaults**, which is the rule ``Voice.compose`` makes about
        ``withheld`` and ``context.build.resolve`` makes about ``ceiling``: a
        caller who forgot either would get a gate that answered *"not in
        crisis"* and *"never interrupted"*, so two of the five refusals could be
        switched off by omission with nothing anywhere saying they had been.
        Forgetting one is now a ``TypeError`` at the call site.
        """
        try:
            return await self._consider(
                view, main_id=main_id, now=now, in_crisis=in_crisis,
                last_interruption=last_interruption,
            )
        except Exception as exc:  # noqa: BLE001 - one main, never the pass
            # The *type* and nothing else (AD-22): an exception message
            # routinely quotes the value that caused it, and here that is a
            # record out of a main's own ledger. Counted as a refusal rather
            # than raised, because one main's unreadable record must not end
            # anybody else's pass — and because there is a correct outcome for
            # *"we could not tell"* and it is saying nothing.
            logger.error(
                "the interruption gate could not run for main=%s (%s); nothing "
                "was sent", main_id, type(exc).__name__,
            )
            return Weighed(reason=UNREADABLE)

    async def _consider(
        self,
        view: SurfaceView,
        *,
        main_id: str,
        now: Now,
        in_crisis: bool,
        last_interruption: str | None,
    ) -> Weighed:
        # 1. **The mode refuses before anything else runs** (CAP-12). Not a
        #    license question and not answerable by one, and it is first rather
        #    than second so that a main in the mode is not *reasoned about*
        #    either — not judged, and not so much as asked about by the
        #    platform. The mode's own path owns them.
        if in_crisis:
            return Weighed(reason=CRISIS)

        # 2. Reachability is asked, never assumed (AD-7). Free and local, and
        #    it is here rather than after the choice — which is the opposite of
        #    where the morning puts it — because there is nothing here to skew:
        #    a morning has a candidate set whose reasons would be hidden by
        #    asking early, and an interruption has a whole main who may not be
        #    spoken to at all.
        reach = self.channel.capability_query(main_id)
        if not reach.may_send_freeform:
            return Weighed(reason=str(reach))

        # 3. The ceiling (AD-28). A main capped below the rung an unprompted
        #    surface speaks from has every record resolve below it, so nothing
        #    could reach ``speech`` whatever a judge said.
        #
        #    **This refuses only where the resolution below would also refuse.**
        #    ``ladder.cap`` is a minimum, so a ceiling at `behave` caps every
        #    belief at `behave` and empties every spoken channel; the check is
        #    that answer hoisted above the spending, never a second opinion
        #    about it. The enforcement is still at context construction, where
        #    AD-18 and AD-28 put it, and ``tests/test_interrupt.py`` sweeps
        #    every rung on the ladder through both so the two cannot disagree.
        if height(view.ceiling.rung) < height(SPEAKS_AT):
            return Weighed(reason=CAPPED)

        # 4. The interruption's own bound, and it is per **main**: a main who
        #    has just been interrupted is not interrupted again, whatever this
        #    one would be about. Free and local, so it runs before anything is
        #    weighed and long before anything is bought.
        own = unspent(last_interruption, now=now.stamp)
        if not own.may_interrupt:
            return Weighed(reason=own.reason or JUST_INTERRUPTED)
        if own.degraded:
            logger.warning(
                "main=%s carries a last interruption this build cannot read; it "
                "is treated as none", main_id,
            )

        # 5. The candidates, in a total order, each held to its **own** clock
        #    (CAP-10's nagging bound). A days-loop is held to a day and a
        #    farmland loop to a year, from the same ``PERIOD_DAYS`` table.
        options = weighable(view, now=now.stamp)
        if not options:
            return Weighed(reason=NOTHING_TO_WEIGH)

        allowed: list[Loop] = []
        refusals: list[str] = []
        degraded = 0
        for loop in options:
            bound = touchable(loop, touches=view.touches, now=now.stamp)
            if not bound.may_touch:
                refusals.append(bound.reason or NAGGING)
                continue
            if bound.degraded:
                degraded += 1
            allowed.append(loop)
        counts: dict[str, Any] = {
            "considered": len(options),
            "bounded": len(refusals),
            "degraded": degraded,
        }
        if degraded:
            logger.warning(
                "main=%s has %d wanting(s) whose last raise could not be "
                "measured; they are treated as never raised", main_id, degraded,
            )
        if not allowed:
            # The first refusal in a total order, so the reason is
            # deterministic given the log and this instant.
            return Weighed(reason=refusals[0], **counts)

        # 6. **Urgency, last.** Everything above is free; this is the only line
        #    in the module that spends anything, and it is unreachable for a
        #    main in the mode, a main the platform will not carry a message to,
        #    a main under the cap, a main just interrupted, and a wanting inside
        #    its own period.
        if self.urgency is None:
            logger.info(
                "no urgency judge is wired for main=%s: %d wanting(s) weighed, "
                "%d inside their own period, nothing interrupted",
                main_id, len(options), len(refusals),
            )
            return Weighed(reason=NO_JUDGE, unwired=True, **counts)

        closing: Loop | None = None
        consulted = not_closing = unsaid = failed = 0
        for loop in allowed[:JUDGEMENTS]:
            # **Billed before the call, not after.** A judgement that raised
            # had still been bought, and incrementing past the ``except``
            # reports zero consultations for a provider that failed every one.
            consulted += 1
            try:
                answer = await asyncio.wait_for(
                    self.urgency.closing(option_for(loop, view=view)),
                    BOUND_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001 - one option, not the pass
                failed += 1
                logger.error(
                    "an urgency judgement failed for main=%s (%s); the pass "
                    "continues", main_id, type(exc).__name__,
                )
                continue
            if answer is None:
                unsaid += 1  # cannot say. Not *no*, and never counted as one.
                continue
            if answer is not True:
                not_closing += 1
                continue
            closing = loop
            break

        counts |= {
            "consulted": consulted, "not_closing": not_closing,
            "unsaid": unsaid, "failed": failed,
        }
        if closing is None:
            # The ordinary refusal. Most days nothing is closing.
            return Weighed(reason=NOTHING_CLOSING, **counts)
        counts["closing"] = 1

        # 7. What may be said, resolved once under this main's ceiling. The
        #    ladder decides and this reads the answer; it never re-decides one.
        context, withheld = split_context(
            material_for(view, loop=closing.id), now=now.stamp,
            ceiling=view.ceiling,
        )
        if not speech(context):
            return Weighed(reason=NOTHING_MAY_BE_SAID, **counts)

        # 8. How it is said. Composed prose through the existing gate, with the
        #    existing tripwire and the existing fallback ladder — no template
        #    and no scaffolding, in any language.
        composed = await self.voice.compose(
            context, main_id=main_id, sample=sample_from(view.beliefs),
            withheld=withheld,
        )
        if not isinstance(composed, Spoken):
            return Weighed(reason=composed.reason, **counts)

        # 8b. **And the platform is asked again.** Composing may take three
        #     attempts at the bound, and WhatsApp's window is a rolling
        #     twenty-four hours that can close inside one — the finding that
        #     cost the morning a day's message in review. The first ask stays
        #     where it is because it does a different job: it stops Half paying
        #     to write at all.
        reach = self.channel.capability_query(main_id)
        if not reach.may_send_freeform:
            return Weighed(reason=str(reach), **counts)

        try:
            result = await self.channel.send(main_id, composed.text)
        except Exception as exc:  # noqa: BLE001 - the message, not the main
            logger.error(
                "the interruption for main=%s could not be sent (%s); it is not "
                "retried and nothing is queued", main_id, type(exc).__name__,
            )
            return Weighed(reason=UNSENT, **counts)
        if not delivered(result):
            logger.error(
                "the channel carried no part of the interruption for main=%s",
                main_id,
            )
            return Weighed(reason=UNSENT, **counts)

        return Weighed(sent=closing.id, text=composed.text, **counts)


# -- the pieces --------------------------------------------------------------


def _entries(view: SurfaceView, loop: str) -> tuple[tuple[str, str], ...]:
    """The ``(id, claim)`` pairs of every belief sitting on ``loop``.

    Sorted by id, so what a judge is shown and what a composer is handed do not
    depend on the order the fold happened to build a dict in. Tolerant: the log
    preserves fields this build does not recognise, and a claim that is not a
    string is one odd value rather than a reason to end a main's pass.
    """
    beliefs = view.beliefs if isinstance(view.beliefs, Mapping) else {}
    found: list[tuple[str, str]] = []
    for ident, record in beliefs.items():
        if not isinstance(ident, str) or not isinstance(record, Mapping):
            continue
        if record.get(LOOP) != loop:
            continue
        claim = record.get("claim")
        found.append((ident, claim if isinstance(claim, str) else ""))
    return tuple(sorted(found))


def _periods(loop: Loop, *, now: object) -> float | None:
    """How many of its own periods ``loop`` has been silent, or ``None``."""
    quiet: Silence = loop.silence(now=now)
    return quiet.periods if quiet.detectable else None


def _check_constants() -> None:
    """Refuse to load on a constant that has been edited into nonsense.

    The pattern ``half.voice.turn._check_constants`` sets: these three numbers
    are the whole of what this module costs and what it promises, and an
    accidental zero in any of them is a gate that buys nothing, never returns,
    or bounds nothing — none of which looks broken from outside.
    """
    if JUDGEMENTS < 1:
        raise ValueError(
            "half.interrupt.gate: JUDGEMENTS is how many urgency judgements a "
            f"pass may buy and must be at least one, got {JUDGEMENTS!r}"
        )
    if not BOUND_SECONDS > 0:
        raise ValueError(
            "half.interrupt.gate: BOUND_SECONDS bounds one judgement and must "
            f"be positive, got {BOUND_SECONDS!r}"
        )
    if INTERRUPTION_DAYS != PERIOD_DAYS[Timescale.DAYS]:
        raise ValueError(
            "half.interrupt.gate: INTERRUPTION_DAYS is read from the open-loop "
            "vocabulary and is not a number typed here"
        )


_check_constants()
