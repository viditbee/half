"""The morning surface: reachability, the ladder, one a day, or silence.

CAP-8, AD-7, AD-27, AD-28, AD-32. The first thing in Half that speaks first.

**Silence is the ordinary outcome, not a degraded one** (AD-27). Every gate
below returns a ``Silence`` carrying a reason, and every one of those reasons
is a normal thing to find on a normal morning. Nothing here logs a silent day
as a failure, nothing retries, nothing escalates, and there is no branch that
looks for something to say because saying nothing felt like a bug. On most days
the pass moves nothing, so there are no candidates, and this module returns
``Silence(NOTHING_TO_SAY)`` without reading a ledger at all.

**The ceiling is honoured, so aftercare is silent — and there is no aftercare
branch here** (AD-28). This is the rule the module is shaped around. A surface
speaks only from material the ladder resolves to `ask` or above *under this
main's ceiling*; a main capped at `behave` therefore has every belief and every
tension resolve to `behave`, nothing reaches ``speech``, and the outcome is
``Silence(NOTHING_MAY_BE_SAID)``. Nothing in this file names aftercare, asks
whether it is running, or knows it exists. That is AD-28's stated reason for
existing: aftercare implemented as per-feature suppression is suppression the
*next* feature forgets, so the cap is applied where licenses are resolved and a
new surface cannot be written that bypasses it — ``ladder.permitted`` and
``context.build`` both take ``ceiling`` as a keyword with no default, so
omitting it is a ``TypeError`` and never an uncapped surface.

**Crisis is a branch, and deliberately unlike aftercare.** *"Crisis suspends
the surface entirely"* is a statement about the mode rather than about
licenses: a main in the mode gets nothing unprompted from this path at all,
whatever any record permits. The scheduler already refuses to run a pass for a
main in the mode, so this is the second of two independent refusals, which is
what CAP-12 asks for.

**The ladder decides what may be said; the context builder decides how**
(story 5a, story 4b). Nothing here re-implements either. The material is handed
to ``half.context.build``, which resolves each record's rung under the ceiling
and puts `assert` material in the content channel, `ask` material in the
question channel and `behave` material in the directive channel — where it
shapes the surface and is never quoted in it (AD-18). This module then speaks
from the first two channels and never the third.

**No model call, and no prose.** The wording of a morning message is a later
story; what this one delivers is the choice of *what* to say and the proof that
it may be said. So the text is the context builder's own rendering of the
channels a surface may speak from — deterministic, assembled, byte-identical
for one log and one ``now``, and carrying nothing the ladder did not admit.
Nothing here reaches ``half.model``.

**The touch is recorded before the send, and that ordering is the rule.** A
surface whose *"already said something today"* marker could not be written has
not earned the right to send — the same asymmetry ``Scheduler._advance`` makes
for a due time, and for the same reason: at-most-once is the only semantics
compatible with *"at most one unprompted message a day"*. A send that fails
after the touch landed costs the main that day's message; a touch that fails
after the send landed would cost them a second message.

**Nothing here raises.** One main's unreadable record costs that main their
morning and never the pass, and never anybody else's (AD-9 isolates mains from
each other; this isolates a main's surface from their own pass). Every outcome
is a value.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final, Protocol

from half.channel.port import Channel, Reachability
from half.civil import instant
from half.consolidate.pass_ import PassResult, completed
from half.context.build import build as build_context
from half.context.channels import Context, Item
from half.governance.ladder import Ceiling, License, height
from half.retrieval.port import Candidate as RankedBelief
from half.schedule.clock import Now
from half.schedule.due import local_day, zone_of
from half.store.fold import State
from half.surface import touch as touch_module
from half.surface.choose import Candidate, Choice, choose
from half.surface.touch import Origin

logger = logging.getLogger(__name__)

__all__ = [
    "ALREADY_TODAY", "CRISIS", "MorningSurface", "NOTHING_MAY_BE_SAID",
    "MorningPass", "NOTHING_TO_SAY", "Outcome", "REASONS", "SPEAKS_AT",
    "Silence",
    "SPOKEN_CHANNELS", "SurfaceLedger", "Surfaced", "UNREADABLE",
    "UNRECORDED", "UNSENT", "speech",
]


#: The weakest rung an **unprompted** message may speak from.
#:
#: `behave` is the rung at which Half *acts* on something silently — softens a
#: tone, delays a nudge, reorders what surfaces (glossary). It is by definition
#: not a rung anything is said from, and an unprompted morning message is the
#: purest case of saying something: nobody asked. `ask` is the first rung that
#: permits Half to raise a thing at all.
#:
#: Named once, here, and read by the runtime *and* by the tests, so that a
#: change to what a surface may speak from is one edit and cannot be made
#: accidentally by a new branch spelling a rung inline.
SPEAKS_AT: Final[License] = License.ASK

#: A main in crisis mode. The mode suspends Half's ordinary behaviour entirely
#: (CAP-12), and an unprompted message is ordinary behaviour.
CRISIS: Final[str] = "crisis"
#: Half has already surfaced something in this main's own local day.
ALREADY_TODAY: Final[str] = "already-today"
#: The preceding pass produced nothing worth saying, or nothing that may be
#: touched today. **The ordinary case**, on most days, for most mains.
NOTHING_TO_SAY: Final[str] = "nothing-to-say"
#: Something was chosen and the ladder did not permit it to be said. Where a
#: main capped at `behave` lands, without this module knowing why they are
#: capped.
NOTHING_MAY_BE_SAID: Final[str] = "nothing-may-be-said"
#: The touch could not be recorded, so nothing was sent — see the module note.
UNRECORDED: Final[str] = "unrecorded"
#: The send itself failed. The day is spent; nothing is retried.
UNSENT: Final[str] = "unsent"
#: A record this build could not read. Counted, never guessed at.
UNREADABLE: Final[str] = "unreadable"

#: Every reason a morning can be silent, beside the platform's own. Closed, so
#: that a caller counting silences counts constants and never a message — an
#: exception message quotes the value that caused it, and here that is a record
#: out of a main's own ledger (AD-22). ``Reachability``'s own values join them:
#: *"Half may not send unprompted right now"* is the port's answer and the port
#: owns its spelling (AD-7).
REASONS: Final[frozenset[str]] = frozenset(
    {
        CRISIS, ALREADY_TODAY, NOTHING_TO_SAY, NOTHING_MAY_BE_SAID,
        UNRECORDED, UNSENT, UNREADABLE,
        *(str(answer) for answer in Reachability
          if not answer.may_send_freeform),
    }
)


@dataclass(frozen=True, slots=True)
class Silence:
    """A morning on which Half said nothing, and why (AD-32).

    A typed outcome rather than ``None``, and the reason is required rather
    than optional: one unit returning ``None`` for silence and another
    returning a reason leaves the metrics and telemetry paths with nothing to
    count, which is the failure AD-32 is written against.

    Silence is **not** a failure, a timeout or an exception. Most of these are
    ordinary — ``NOTHING_TO_SAY`` is what a quiet night looks like — and none
    of them is logged as an error.
    """

    reason: str


@dataclass(frozen=True, slots=True)
class Surfaced:
    """The one thing Half said this morning, and what it came from.

    ``origin`` travels on the value as well as into the log, which is the whole
    of *"nothing is surfaced that cannot say where it came from"*: what was said
    can be examined and it names the tension, loop transition or ingested item
    in the preceding pass it was built from.

    ``text`` is the context builder's rendering of the channels a surface may
    speak from. Deliberately not prose: composing the sentence is a later
    story, and a template written here would be one language's phrasing shipped
    to a worldwide product (see ``half.context.channels``).
    """

    loop: str
    origin: Origin
    entries: tuple[str, ...]
    text: str


Outcome = Surfaced | Silence


#: Which of a built context's three channels carries which rung, weakest last.
#:
#: A fact about ``half.context.build``, written down here because ``speech``
#: has to turn *"which rung may a surface speak from"* into *"which channels
#: does it read"*, and the two must not be able to drift apart: the sweep in
#: ``tests/test_surface.py`` runs every rung on the ladder through the real
#: builder and asserts this table is what the builder actually does — so a
#: fourth rung, or a channel that changes hands, fails by name rather than by
#: a surface quietly speaking from a rung it may not.
_CHANNELS: Final[tuple[tuple[str, License], ...]] = (
    ("content", License.ASSERT),
    ("questions", License.ASK),
    ("directives", License.BEHAVE),
)

#: The channels ``SPEAKS_AT`` actually opens. Derived rather than listed, so
#: that lowering ``SPEAKS_AT`` is a single edit with a visible consequence and
#: not a constant that documents a decision made somewhere else.
SPOKEN_CHANNELS: Final[tuple[str, ...]] = tuple(
    name for name, rung in _CHANNELS if height(rung) >= height(SPEAKS_AT)
)


def speech(context: Context) -> tuple[Item, ...]:
    """The items in ``context`` that an unprompted surface may speak from.

    **The predicate, read by the runtime and by the tests**, rather than a
    shape each of them checks separately. Content is `assert` material the
    ladder admitted as quotable; questions are `ask` material Half may raise.
    Directives are `behave` material — they shape what is said and are never
    part of it (AD-18) — so they are absent here, and that absence is what
    turns a context of directives alone into silence rather than into a message
    about topics nobody asked about.

    Asking the *context* rather than re-resolving licenses is deliberate: the
    builder already resolved every rung once, under the ceiling, and a second
    resolution here would be a second opinion about one question — exactly the
    disagreement ``half.store.db`` deleted its ``license`` column to remove.
    """
    if not isinstance(context, Context):
        return ()
    return tuple(
        item
        for name in SPOKEN_CHANNELS
        for item in getattr(context, name, ())
    )


class SurfaceLedger(Protocol):
    """The four doors the surface needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry``, for the reason
    ``half.schedule.tick.Registry`` and ``half.consolidate.pass_.Ledger`` are
    protocols: two narrowed reads, one read under the mutex and one write that
    goes through it, is the whole dependency. Nothing here opens a store — a
    surface with its own path to the log would be a second writer, and the
    single writer is what lets the store skip a journal (AD-1).
    """

    def crisis_open(self, main_id: str) -> bool:
        ...

    def zone_records(self, main_id: str) -> Sequence[Mapping[str, Any]]:
        ...

    async def surface_view(self, main_id: str) -> tuple[State, Ceiling]:
        ...

    async def note_touch(
        self, main_id: str, *, t: str, fields: Mapping[str, Any]
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class MorningSurface:
    """One main, one instant, at most one thing said.

    ``channel`` is asked whether Half may send unprompted and is then asked to
    send; it is never asked which platform it is (AD-7). ``ledger`` is the four
    doors above.
    """

    ledger: SurfaceLedger
    channel: Channel

    async def surface(
        self, main_id: str, *, now: Now, candidates: Sequence[Candidate]
    ) -> Outcome:
        """Say one thing, or say nothing. Never raises.

        The gates below are independent: each of them, alone, produces silence,
        so the *outcome* does not depend on the order they are asked in — only
        the reason does, and ``tests/test_surface.py`` sweeps every pair of
        them in both orders rather than trusting that.

        The order that *is* deliberate is the first one: the mode is asked
        before anything else, because *"crisis suspends the surface entirely"*
        is the one rule here that may never be answered by a license.

        ``candidates`` comes from the preceding pass and is the only source of
        anything that may be surfaced. There is no branch that reaches into the
        ledger for something to say when the pass produced nothing: *"every
        surface traces to the preceding pass"* is a property of this signature,
        not a rule this body follows.
        """
        try:
            return await self._surface(main_id, now=now, candidates=candidates)
        except Exception as exc:  # noqa: BLE001 - one main, never the pass
            # The *type* and nothing else (AD-22): an exception message
            # routinely quotes the value that caused it, and here that is a
            # record out of a main's own ledger. Counted as a silence rather
            # than raised, because one main's unreadable record must not end
            # anybody else's morning — and because there is a correct outcome
            # for "we could not tell" and it is saying nothing.
            logger.error(
                "the morning surface could not run for main=%s (%s); nothing "
                "was sent", main_id, type(exc).__name__,
            )
            return Silence(UNREADABLE)

    async def _surface(
        self, main_id: str, *, now: Now, candidates: Sequence[Candidate]
    ) -> Outcome:
        # 1. The mode suspends everything (CAP-12). Not a license question and
        #    not answerable by one: a main in crisis gets nothing unprompted
        #    from this path whatever any record permits.
        if self.ledger.crisis_open(main_id):
            return Silence(CRISIS)

        # 2. Nothing came out of last night's pass. The ordinary case, on most
        #    mornings, for most mains — and it is answered before the platform
        #    is asked anything and before a word is written, so a quiet morning
        #    costs a fold read and nothing else.
        if not candidates:
            return Silence(NOTHING_TO_SAY)

        # 3. One a day, per main, in the main's **own** local day. Read from
        #    the fold's last touch, which is durable — so a restart cannot buy
        #    a second message, and neither can an eviction.
        state, ceiling = await self.ledger.surface_view(main_id)
        zone = zone_of(self.ledger.zone_records(main_id))
        if self._spoken_today(state, zone=zone, now=now):
            return Silence(ALREADY_TODAY)

        # 4. Reachability is asked, never assumed (AD-7). If the platform will
        #    not carry an unprompted message right now, Half does not send one,
        #    and that is silence rather than an error.
        reach = self.channel.capability_query(main_id)
        if not reach.may_send_freeform:
            return Silence(str(reach))

        # 5. The choice: traceable, bounded by each loop's own timescale, and
        #    deterministic given this log and this instant.
        choice = choose(
            candidates,
            beliefs=state.beliefs,
            loops=state.loops,
            touches=state.touches,
            now=now.stamp,
        )
        if choice is None:
            return Silence(NOTHING_TO_SAY)

        # 6. What may be said, and how. The ladder resolves each record's rung
        #    under this main's ceiling and the context builder splits content
        #    from directives; this reads the answer and never re-decides it.
        text = self._speech(state, choice=choice, ceiling=ceiling, now=now)
        if not text:
            return Silence(NOTHING_MAY_BE_SAID)

        # 7. The touch first, then the send. A surface whose "already said
        #    something today" marker could not be written has not earned the
        #    right to send.
        try:
            await self.ledger.note_touch(
                main_id,
                t=now.stamp,
                fields=touch_module.fields(choice.loop, origin=choice.origin),
            )
        except Exception as exc:  # noqa: BLE001 - the day, not the main
            logger.error(
                "could not record a touch for main=%s (%s); nothing was sent",
                main_id, type(exc).__name__,
            )
            return Silence(UNRECORDED)

        try:
            await self.channel.send(main_id, text)
        except Exception as exc:  # noqa: BLE001 - the day, not the main
            # Nothing is retried and nothing is queued. The touch has already
            # landed, so this main's day is spent — which is the correct
            # asymmetry: a failed send costs one message, a retry loop costs
            # the one-a-day rule.
            logger.error(
                "the morning surface for main=%s could not be sent (%s); it is "
                "not retried and nothing is queued", main_id,
                type(exc).__name__,
            )
            return Silence(UNSENT)

        return Surfaced(
            loop=choice.loop,
            origin=choice.origin,
            entries=choice.entries,
            text=text,
        )

    # -- the two questions this module answers itself ------------------------

    def _spoken_today(
        self, state: State, *, zone: object, now: Now
    ) -> bool:
        """Whether Half has already surfaced something in this main's own day.

        A **local civil day**, not twenty-four hours, and the difference is the
        whole rule: two messages at 23:50 and 00:10 are two days' worth ten
        minutes apart, and two at 00:10 and 23:50 are one day's worth almost a
        day apart. The zone is the one the main told Half, resolved through the
        same door the due-time queue uses, so the two can never disagree about
        what day it is — and a main who has told Half nothing gets the recorded
        fallback rather than a guess (AD-9).

        **Fails closed.** A last touch whose stamp this build cannot read is
        treated as *today*, so the answer is silence. That direction is
        deliberate and it is the asymmetry the rule is written on: reading an
        unmeasurable stamp as *yesterday* buys a second unprompted message on a
        day one was already sent, and reading it as *today* costs one quiet
        morning. One a day is an Always; a quiet morning is the ordinary
        outcome.

        The branch is not unreachable, which is why it is written rather than
        asserted away. ``records.make`` checks a stamp's *shape* and not its
        calendar, so ``2026-02-31T00:00Z`` becomes durable and
        ``half.civil.instant`` then refuses it — a real, if rare, log. Whether
        the append gate should validate every ``t`` as an instant is a change
        to a shared writer for every op, which is an Ask-First edit and not
        this story's.
        """
        last = state.last_touch
        if not isinstance(last, Mapping):
            return False
        stamp = last.get("t")
        if not isinstance(stamp, str) or not stamp.strip():
            return True
        at = instant(stamp)
        if at is None:
            return True
        return local_day(at, zone) == local_day(now.epoch, zone)

    def _speech(
        self, state: State, *, choice: Choice, ceiling: Ceiling | None, now: Now
    ) -> str:
        """The text this choice licenses, or the empty string.

        The material is the belief records the choice names, handed to the
        context builder with this main's ceiling. What comes back is split into
        three channels; a surface speaks from two of them and never from the
        third, so a `behave` belief shapes what is said — it is in the context,
        it is what the withholding guard measures other lines against — and is
        never quoted in it.

        The rendering is the builder's own (``Context.render``), over a context
        with the directive channel removed. Rendering the *whole* context would
        put internal shaping vocabulary on the wire; re-rendering the two
        channels by hand would be a second renderer outside the guard that
        makes AD-18 true. Dropping a channel cannot introduce a leak, because
        every line that survives already passed the guard.

        The empty string is where a main capped at `behave` lands, and where a
        main whose only material is `behave` lands, and this function cannot
        tell them apart. That is the point.
        """
        material = tuple(
            RankedBelief(
                id=ident,
                claim=_claim_of(state.beliefs.get(ident)),
                prefix="",
                bm25=None,
                belief=state.beliefs.get(ident) or {},
            )
            for ident in choice.entries
        )
        context = build_context(material, now=now.stamp, ceiling=ceiling)
        sayable = speech(context)
        if not sayable:
            return ""
        return replace(context, directives=()).render()


class ConsolidationPass(Protocol):
    """The half of a night's work the surface reads. One method.

    A protocol rather than the concrete ``TensionPass`` for the reason every
    other seam in this tree is one: what the surface needs is a night's result,
    and a story that adds loop transitions or ingested items to the pass
    changes what fills ``PassResult.candidates`` without touching this file.
    """

    async def evaluate(self, main_id: str, now: Now) -> PassResult:
        ...


@dataclass(frozen=True, slots=True)
class MorningPass:
    """The scheduler's work: consolidate the night, then surface at most one
    thing from it. Satisfies ``half.schedule.tick.Pass``.

    **Ordered, and the order is the traceability rule.** The pass runs first and
    the surface reads *its* result — there is no path by which a morning message
    is built from anything but the night that just ran (CAP-8). A surface that
    reached into the ledger for something to say would be a surface that says
    something every day.

    **The surface runs even when a transition could not be written.** A night
    with one failed append still moved nine other tensions, and those are worth
    saying; the incompleteness is raised *after*, so the scheduler still counts
    the main under ``failed`` and the log still shows what is missing. Raising
    first would make one failed write cost the main their morning as well as
    their transition.

    **The surface never raises**, so nothing it does can turn a completed pass
    into a failed one. A main whose morning could not be read is a main who was
    sent nothing, which is a first-class outcome (AD-27) and not a tick failure.
    """

    consolidate: ConsolidationPass
    surface: MorningSurface

    async def run(self, main_id: str, now: Now) -> None:
        """The ``Pass`` protocol's method. Returns ``None``; raises only when a
        transition this main's log should be carrying is not in it."""
        result = await self.consolidate.evaluate(main_id, now)
        outcome = await self.surface.surface(
            main_id, now=now, candidates=result.candidates
        )
        # Counts and ids only, never content (AD-22) — and at debug, because a
        # silent morning is the ordinary morning and a log line per main per
        # day saying so is noise that trains an operator to ignore the file.
        logger.debug(
            "morning for main=%s: %s",
            main_id,
            "sent" if isinstance(outcome, Surfaced) else outcome.reason,
        )
        completed(result, main_id=main_id)


def _claim_of(record: Mapping[str, Any] | None) -> str:
    """A belief's claim text, or the empty string. Never raises.

    The log preserves fields this build does not recognise, and a claim that is
    not a string is one odd value rather than a reason to end a main's morning.
    An empty claim contributes nothing to the content channel, which
    ``half.context.build`` already treats as *"nothing to say"* rather than as
    a degraded quotation.
    """
    if not isinstance(record, Mapping):
        return ""
    claim = record.get("claim")
    return claim if isinstance(claim, str) else ""
