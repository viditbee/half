"""The morning surface: the choice, the ladder, one a day, or silence.

CAP-8, AD-7, AD-27, AD-28, AD-32. The first thing in Half that speaks first.

**Silence is the ordinary outcome, not a degraded one** (AD-27). Every gate
below returns a ``Silence`` carrying a reason, and most of those reasons are
normal things to find on a normal morning: nothing worth saying, a loop still
inside its own period, a day already spent. Nothing retries, nothing escalates,
and there is no branch that looks for something to say because saying nothing
felt like a bug. On most days the pass moves nothing, so there are no
candidates and this module answers before it asks a platform anything.

*Three of the reasons are genuine faults and are logged as such* —
``UNREADABLE``, ``UNRECORDED`` and ``UNSENT``. The rule is not *"a silent
morning is never an error"*; it is that **an ordinary silence is never an
error**, and the three that are not ordinary say so at ``error`` while every
other one says nothing above ``debug``. An earlier docstring here claimed the
stronger sentence and the code did not implement it.

**Every outcome is counted** (AD-32, and the matrix's *one main fails →
counted*). ``Silence`` exists because *"one unit returning None for silence and
another returning a reason leaves the metrics path with nothing to count"* —
which was true of this module until review, because ``MorningPass`` discarded
what it was handed. ``Mornings`` is that counter: counts by reason, never
content.

**The ceiling is honoured, so aftercare is silent — and this module cannot ask
about aftercare** (AD-28). A surface speaks only from material the ladder
resolves to `ask` or above *under this main's ceiling*; a main capped at
`behave` therefore has every record resolve to `behave`, nothing reaches
``speech``, and the outcome is ``Silence(NOTHING_MAY_BE_SAID)``. The guarantee
does not rest on nobody writing ``if in_aftercare``: what this module is handed
is a ``SurfaceView``, which has no aftercare field, so the branch is an
``AttributeError`` rather than a line a scan has to be clever enough to see.
See ``half.surface.view``, which exists because review wrote that branch and
passed 3182 tests with it.

**Crisis is a branch, and deliberately unlike aftercare.** *"Crisis suspends
the surface entirely"* is a statement about the mode rather than about
licenses: a main in the mode gets nothing unprompted whatever any record
permits. It is asked twice — once before any work, and again inside the mutex
that spends the day — because a main who enters the mode while their morning is
being assembled must not receive it.

**The ladder decides what may be said; the context builder decides how**
(story 5a, story 4b). Nothing here re-implements either.

**No model call, and no prose.** The wording of a morning message is a later
story; what this one delivers is the choice of *what* to say and the proof that
it may be said. The text is the context builder's own rendering of the channels
a surface may speak from — deterministic, byte-identical for one log and one
``now``, and carrying nothing the ladder did not admit.

**The morning surface does not ask, and that is a rule rather than an
omission** (CAP-4, story 11). A question is bought — no `ask`-rung belief becomes
one without a delivered favour spent on it — and *"the favour buys the question"*
also says **where**: attached to a conversation that already touches its topic,
never pinged. 5b's topic gate reads the actor's live strands, which exist on a
turn and nowhere else; this module runs on a scheduler tick, where a dormant
actor has none. The first build of story 11 gated on those strands and delivered
here anyway, so every morning asked a question and paid for it with the very
message that carried it — a main with zero delivered favours was asked. Delivery
is ``half.actor.runtime``'s now, and this module has no engine, no spend and no
door onto one. ``tests/test_bought.py`` asserts the whole ``half.surface``
package cannot reach ``half.questions`` at all.

The consequence for what a morning says: `ask`-rung material no longer speaks
here. `assert` material still does, and a main whose only material is `ask` gets
silence — which is CAP-4's rule arriving rather than a regression, because the
one thing Half could have done with that material is raise it, and raising it is
what the favour pays for on the turn path.

**The day is claimed before the send, in one serialized operation.** A surface
whose *"already said something today"* marker could not be written has not
earned the right to send — the same asymmetry ``Scheduler._advance`` makes for
a due time. And the check and the append happen inside **one** acquire, because
reading the marker under the mutex and appending under a later one let two
overlapping runs both read yesterday and both send.

**Nothing here raises.** One main's unreadable record costs that main their
morning and never the pass, and never anybody else's.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, Protocol

from half.channel.port import Channel, Reachability, SendResult
from half.consolidate.pass_ import PassResult, completed
from half.context.build import build as build_context
from half.context.channels import Context, Item
from half.context.channels import CHANNELS as CHANNEL_NAMES
from half.governance.ladder import License, height
from half.retrieval.port import Candidate as RankedBelief
from half.schedule.clock import Now
from half.schedule.due import local_day, zone_of
from half.surface import touch as touch_module
from half.surface.choose import Candidate, Choice, choose
from half.surface.touch import Origin, spoken_on
from half.surface.view import (
    CLAIM_ALREADY,
    CLAIM_CRISIS,
    CLAIMED,
    SurfaceView,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ALREADY_TODAY", "CRISIS", "MorningPass", "MorningSurface", "Mornings",
    "NOTHING_MAY_BE_SAID", "NOTHING_TO_SAY", "Outcome", "REASONS", "SPEAKS_AT",
    "SPOKEN_CHANNELS", "Silence", "SurfaceLedger", "Surfaced", "UNREADABLE",
    "UNREADABLE_MARKER", "UNRECORDED", "UNSENT", "speech",
]


#: The weakest rung an **unprompted** message may speak from.
#:
#: `behave` is the rung at which Half *acts* on something silently — softens a
#: tone, delays a nudge, reorders what surfaces (glossary). It is by definition
#: not a rung anything is said from, and an unprompted morning message is the
#: purest case of saying something: nobody asked. `ask` is the first rung that
#: permits Half to raise a thing at all.
SPEAKS_AT: Final[License] = License.ASK

#: A main in crisis mode. The mode suspends Half's ordinary behaviour entirely
#: (CAP-12), and an unprompted message is ordinary behaviour.
CRISIS: Final[str] = "crisis"
#: Half has already spent this main's day.
ALREADY_TODAY: Final[str] = "already-today"
#: The preceding pass produced nothing worth saying, or nothing that may be
#: touched today. **The ordinary case**, on most days, for most mains.
NOTHING_TO_SAY: Final[str] = "nothing-to-say"
#: Something was chosen and the ladder did not permit it to be said. Where a
#: main capped at `behave` lands, without this module knowing why they are
#: capped.
NOTHING_MAY_BE_SAID: Final[str] = "nothing-may-be-said"
#: The day marker could not be read, so the day was spent on a repair rather
#: than on a message. Costs one morning; the next one reads cleanly.
UNREADABLE_MARKER: Final[str] = "unreadable-marker"
#: The day could not be claimed, so nothing was sent — see the module note.
UNRECORDED: Final[str] = "unrecorded"
#: The send itself failed, or the channel reported that nothing was delivered.
#: The day is spent; nothing is retried.
UNSENT: Final[str] = "unsent"
#: A record this build could not read. Counted, never guessed at.
UNREADABLE: Final[str] = "unreadable"

#: The reasons that are **faults** rather than ordinary quiet. Named once and
#: read by the logger, so *"an ordinary silence is never logged as an error"*
#: is a property of one set rather than of three call sites somebody kept in
#: step.
FAULTS: Final[frozenset[str]] = frozenset({UNREADABLE, UNRECORDED, UNSENT})

#: Every reason a morning can be silent, beside the platform's own. Closed, so
#: that a caller counting silences counts constants and never a message — an
#: exception message quotes the value that caused it, and here that is a record
#: out of a main's own ledger (AD-22). ``Reachability``'s own refusals join
#: them: *"Half may not send unprompted right now"* is the port's answer and
#: the port owns its spelling (AD-7).
REASONS: Final[frozenset[str]] = frozenset(
    {
        CRISIS, ALREADY_TODAY, NOTHING_TO_SAY, NOTHING_MAY_BE_SAID,
        UNREADABLE_MARKER, UNRECORDED, UNSENT, UNREADABLE,
        *(str(answer) for answer in Reachability if not answer.may_send_freeform),
    }
)


@dataclass(frozen=True, slots=True)
class Silence:
    """A morning on which Half said nothing, and why (AD-32).

    A typed outcome rather than ``None``, and the reason is required rather
    than optional: one unit returning ``None`` for silence and another
    returning a reason leaves the metrics and telemetry paths with nothing to
    count, which is the failure AD-32 is written against — and which this
    module shipped anyway until ``Mornings`` existed to receive it.

    Silence is **not** a failure, a timeout or an exception. Most of these are
    ordinary; the three in ``FAULTS`` are not, and only those are logged as
    such.
    """

    reason: str

    @property
    def fault(self) -> bool:
        return self.reason in FAULTS


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

    loops: tuple[str, ...]
    origin: Origin
    entries: tuple[str, ...]
    day: str
    text: str


Outcome = Surfaced | Silence


@dataclass(slots=True)
class Mornings:
    """What the mornings did. Counts and reasons only — never content (AD-22).

    The metrics path ``Silence``'s own docstring is written for. Before review
    every outcome was discarded: ``MorningPass`` logged at debug and returned
    ``None``, ``TickResult`` had no field for a morning, and the matrix row
    *one main fails → counted* was satisfied by nothing. A permanently silent
    main was therefore indistinguishable from a main with a quiet life, which
    is the one thing an operator most needs to be able to tell apart.

    Not a telemetry client and not a store: it holds integers in memory, is
    owned by the composition root, and is read by ``flush``. AD-22's *counts,
    never content* is a property of the type — there is nowhere here to put a
    claim, a message or a main's own words. ``main_id`` is deliberately absent
    too: what an operator needs is *how many*, and a per-main breakdown of who
    was silent is a shape of the ledger.
    """

    sent: int = 0
    silences: Counter[str] = field(default_factory=Counter)
    #: Loops raised without a measurable bound — see ``choose.Bound``. Counted
    #: because it is the shape of a corruption nobody would otherwise notice.
    degraded: int = 0

    @property
    def silent(self) -> int:
        return sum(self.silences.values())

    @property
    def faults(self) -> int:
        return sum(n for reason, n in self.silences.items() if reason in FAULTS)

    def note(self, outcome: Outcome) -> None:
        if isinstance(outcome, Surfaced):
            self.sent += 1
            return
        self.silences[outcome.reason] += 1

    def note_degraded(self, loops: Sequence[str]) -> None:
        self.degraded += len(loops)

    def flush(self) -> None:
        """Report what the mornings did, once. Counts only.

        At ``info`` rather than ``debug``, and only when something happened, so
        an operator sees the shape of a week without a line per main per day
        training them to ignore the file.
        """
        if not (self.sent or self.silent or self.degraded):
            return
        logger.info(
            "mornings: sent=%d silent=%d faults=%d degraded=%d by_reason=%s",
            self.sent, self.silent, self.faults, self.degraded,
            dict(sorted(self.silences.items())),
        )


#: Which of a built context's three channels carries which rung, weakest last.
#:
#: A fact about ``half.context.build``, written down here because ``speech``
#: has to turn *"which rung may a surface speak from"* into *"which channels
#: does it read"*, and the two must not be able to drift apart: the sweep in
#: ``tests/test_surface.py`` runs every rung on the ladder through the real
#: builder and asserts this table is what the builder actually does.
#: **A question is in the ``question`` channel only when a favour bought it**
#: (CAP-4, story 11), which is why this table is *not* a statement that an
#: `ask`-rung belief lands there. The builder is handed the belief the spend paid
#: for and emits a question for that one; an unbought `ask` belief becomes a
#: directive, so it still shapes what is said and is never said. This module
#: never buys, so the middle row is never filled *here* — it is kept because
#: ``speech`` has to be a true statement about what ``build`` does, not about
#: what this caller happens to hand it, and ``tests/test_surface.py`` sweeps
#: every rung through the real builder both ways so neither half can drift.
#:
#: **The names are the builder's**, read from ``half.context.channels.CHANNELS``
#: rather than spelled again, so a renamed field is an import error here instead
#: of a channel this module silently stops reading.
_CHANNELS: Final[tuple[tuple[str, License], ...]] = tuple(
    zip(CHANNEL_NAMES, (License.ASSERT, License.BEHAVE, License.ASK))
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
    resolution here would be a second opinion about one question.

    **A question channel that is empty because nothing was bought is silence**,
    and that is the CAP-4 rule arriving here rather than a new gate: a main whose
    only material is `ask`-rung and who has earned no favour has nothing said to
    them, because the one thing Half could have done with that material — raise
    it — is what the favour pays for. Content still speaks; only the question is
    bought.

    ``Context.channel`` is asked for each name rather than ``getattr``, because
    the question channel holds at most one question and is therefore not a tuple
    — see ``half.context.channels.Context.question``.
    """
    if not isinstance(context, Context):
        return ()
    return tuple(
        item for name in SPOKEN_CHANNELS for item in context.channel(name)
    )


class SurfaceLedger(Protocol):
    """The four doors the surface needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry`` because that is the
    whole dependency: two narrowed reads and one serialized claim-and-append.
    Nothing here opens a store — a surface with its own path to the log would
    be a second writer, and the single writer is what lets the store skip a
    journal (AD-1).

    **``surface_view`` is narrowed by construction.** It hands back a
    ``SurfaceView`` and not the fold, so the crisis record, the aftercare
    record and the schedule are not merely unread here — they are unreachable.
    """

    def crisis_open(self, main_id: str) -> bool:
        ...

    def zone_records(self, main_id: str) -> Sequence[Mapping[str, Any]]:
        ...

    async def surface_view(self, main_id: str) -> SurfaceView:
        ...

    async def claim_day(
        self,
        main_id: str,
        *,
        t: str,
        day: str,
        records: Sequence[Mapping[str, Any]],
    ) -> str:
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
    #: Where outcomes are counted. Optional so a caller can drive the surface
    #: without one, and constructed by default so the shipped path always has
    #: somewhere to put them.
    mornings: Mornings = field(default_factory=Mornings)

    async def surface(
        self, main_id: str, *, now: Now, candidates: Sequence[Candidate]
    ) -> Outcome:
        """Say one thing, or say nothing. Never raises, and always counts.

        The gates are independent: each of them, alone, produces silence, so
        the *outcome* does not depend on the order they are asked in — only the
        reason does, and ``tests/test_surface.py`` sweeps every pair of them in
        both orders rather than trusting that.

        Two orderings *are* deliberate. The mode is asked first, because
        *"crisis suspends the surface entirely"* is the one rule here that may
        never be answered by a license. And reachability is asked **after** the
        choice, because asking first made a morning on which the bound rejected
        everything report ``never_contacted`` — skewing the very reason set
        ``Silence`` exists to make countable.
        """
        outcome = await self._counted(main_id, now=now, candidates=candidates)
        self.mornings.note(outcome)
        if isinstance(outcome, Silence) and outcome.fault:
            logger.error(
                "the morning for main=%s ended in %s; nothing was sent",
                main_id, outcome.reason,
            )
        else:
            logger.debug("morning for main=%s: %s", main_id, _label(outcome))
        return outcome

    async def _counted(
        self, main_id: str, *, now: Now, candidates: Sequence[Candidate]
    ) -> Outcome:
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
                "the morning surface could not run for main=%s (%s)",
                main_id, type(exc).__name__,
            )
            return Silence(UNREADABLE)

    async def _surface(
        self, main_id: str, *, now: Now, candidates: Sequence[Candidate]
    ) -> Outcome:
        # 1. The mode suspends everything (CAP-12). Not a license question and
        #    not answerable by one. Asked again inside the claim, below.
        if self.ledger.crisis_open(main_id):
            return Silence(CRISIS)

        # 2. Nothing came out of last night's pass. The ordinary case, on most
        #    mornings, for most mains — answered before the platform is asked
        #    anything and before a word is written.
        if not candidates:
            return Silence(NOTHING_TO_SAY)

        view = await self.ledger.surface_view(main_id)
        zone = zone_of(self.ledger.zone_records(main_id))
        today = local_day(now.epoch, zone)

        # 3. One a day, per main, in the main's **own** local day, read from
        #    the stored marker rather than recomputed under today's zone.
        covered = spoken_on(view.spoke, today)
        if covered is None:
            # The marker is unreadable. Silent today — the rule is an Always
            # and reading an unmeasurable marker as *yesterday* buys a second
            # message on a day one was already sent — but **repaired**, because
            # the marker is replaced only by a later one and a later one is
            # written only when Half is about to speak: without this, a single
            # corrupt record silenced a main for ever.
            return await self._repair(main_id, now=now, day=today)
        if covered:
            return Silence(ALREADY_TODAY)

        # 4. The choice: traceable to something the log still holds, bounded by
        #    each loop's own timescale, and deterministic given this log and
        #    this instant.
        choice = choose(candidates, view=view, now=now.stamp)
        if choice is None:
            return Silence(NOTHING_TO_SAY)
        if choice.degraded:
            self.mornings.note_degraded(choice.degraded)
            logger.warning(
                "main=%s has %d loop(s) whose last raise could not be measured; "
                "they are treated as never raised", main_id,
                len(choice.degraded),
            )

        # 5. What may be said, and how. The ladder resolves each record's rung
        #    under this main's ceiling and the context builder splits content
        #    from directives; this reads the answer and never re-decides it.
        #    **Nothing is bought.** A question is delivered on the turn path
        #    (``half.actor.runtime``), and this call hands the builder no bought
        #    belief, so no morning can carry one.
        text = self._speech(view, choice=choice, now=now)
        if not text:
            return Silence(NOTHING_MAY_BE_SAID)

        # 6. Reachability is asked, never assumed (AD-7) — and asked here, once
        #    there is actually something to send, so a morning the bound
        #    silenced is not reported as an unreachable one.
        reach = self.channel.capability_query(main_id)
        if not reach.may_send_freeform:
            return Silence(str(reach))

        # 7. The day is claimed, then the message is sent. Claiming is one
        #    serialized operation: it re-asserts the mode, re-reads the marker
        #    and appends, all inside one acquire.
        claim = await self._claim(main_id, now=now, day=today, choice=choice)
        if claim == CLAIM_CRISIS:
            return Silence(CRISIS)
        if claim == CLAIM_ALREADY:
            return Silence(ALREADY_TODAY)
        if claim != CLAIMED:
            return Silence(UNRECORDED)

        try:
            result = await self.channel.send(main_id, text)
        except Exception as exc:  # noqa: BLE001 - the day, not the main
            # Nothing is retried and nothing is queued. The day has already
            # been claimed, so it is spent — which is the correct asymmetry: a
            # failed send costs one message, a retry loop costs the one-a-day
            # rule.
            logger.error(
                "the morning surface for main=%s could not be sent (%s); it is "
                "not retried and nothing is queued", main_id,
                type(exc).__name__,
            )
            return Silence(UNSENT)
        if not _delivered(result):
            # An adapter may report non-delivery by return value rather than by
            # raising — ``TelegramChannel.send`` answers ``parts=0`` for a body
            # the platform would reject. Discarding the result recorded that as
            # a message sent and spent the day for it.
            logger.error(
                "the channel carried no part of the morning for main=%s", main_id
            )
            return Silence(UNSENT)

        return Surfaced(
            loops=choice.loops,
            origin=choice.origin,
            entries=choice.entries,
            day=today,
            text=text,
        )

    # -- the pieces ----------------------------------------------------------

    async def _repair(self, main_id: str, *, now: Now, day: str) -> Outcome:
        """Spend the day on a readable marker so tomorrow is not lost too.

        Writes a day marker that says plainly that **no message was sent**
        (``touch.repaired``), which is true, cites nothing because nothing was
        surfaced, and supersedes the record nothing could read. Costs one
        morning; every morning after it reads cleanly.

        **Warned as well as counted.** It is not a fault — nothing failed, and
        the morning ends the way an ordinary quiet one does — but it is not
        ordinary either, and review's whole finding about the permanent version
        was that there was *"no recovery, no alert and no counter"*. There are
        now all three.
        """
        logger.warning(
            "main=%s has a day marker this build cannot read; the day is spent "
            "on a repair and nothing was sent", main_id,
        )
        claim = await self._append(
            main_id, now=now, day=day, records=[touch_module.repaired(day=day)]
        )
        if claim == CLAIM_CRISIS:
            return Silence(CRISIS)
        if claim in (CLAIM_ALREADY, CLAIMED):
            # ``already`` means somebody else repaired it first, which is the
            # same outcome for this morning.
            return Silence(UNREADABLE_MARKER)
        return Silence(UNRECORDED)

    async def _claim(
        self, main_id: str, *, now: Now, day: str, choice: Choice
    ) -> str:
        """Spend the day, and record a raise for every loop this touches.

        One record marks the day and carries the first loop; the rest are
        raises that mark no day, because a candidate touching three wantings
        bounds three wantings and spends one morning. All of them are appended
        inside one acquire, so a crash cannot leave a day spent with the loops
        unbounded or the reverse.
        """
        records: list[Mapping[str, Any]] = [
            touch_module.spoke(day=day, origin=choice.origin, loops=choice.loops)
        ]
        records.extend(
            touch_module.raised(slug, origin=choice.origin)
            for slug in choice.loops[1:]
        )
        return await self._append(main_id, now=now, day=day, records=records)

    async def _append(
        self,
        main_id: str,
        *,
        now: Now,
        day: str,
        records: Sequence[Mapping[str, Any]],
    ) -> str:
        try:
            return await self.ledger.claim_day(
                main_id, t=now.stamp, day=day, records=records
            )
        except Exception as exc:  # noqa: BLE001 - the day, not the main
            logger.error(
                "could not claim the day for main=%s (%s); nothing was sent",
                main_id, type(exc).__name__,
            )
            return UNRECORDED

    def _speech(self, view: SurfaceView, *, choice: Choice, now: Now) -> str:
        """The text this choice licenses, or the empty string.

        The material is the belief records the choice names — **all** of them,
        never narrowed to one loop's — handed to the context builder with this
        main's ceiling. What comes back is split into three channels; a surface
        speaks from two of them and never from the third, so a `behave` belief
        shapes what is said and is never quoted in it.

        The rendering is the builder's own (``Context.render``), over a context
        with the directive channel removed. Rendering the whole context would
        put internal shaping vocabulary on the wire; re-rendering the two
        channels by hand would be a second renderer outside the guard that makes
        AD-18 true. Dropping a channel cannot introduce a leak, because every
        line that survives already passed the guard.

        The empty string is where a main capped at `behave` lands, and where a
        main whose only material is `behave` lands, and this function cannot
        tell them apart. That is the point.
        """
        material = tuple(
            RankedBelief(
                id=ident,
                claim=_claim_of(view.beliefs.get(ident)),
                prefix="",
                bm25=None,
                belief=view.beliefs.get(ident) or {},
            )
            for ident in choice.entries
        )
        # No ``bought`` argument, and that is the rule rather than an omission:
        # the channel is bought by what the builder is *handed*, and this caller
        # hands it nothing, so a morning cannot carry a question however the
        # ladder resolves its material (CAP-4).
        context = build_context(material, now=now.stamp, ceiling=view.ceiling)
        if not speech(context):
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
    the main under ``failed``. Raising first would make one failed write cost
    the main their morning as well as their transition.

    **The surface never raises**, so nothing it does can turn a completed pass
    into a failed one — and its outcome is counted rather than discarded.
    """

    consolidate: ConsolidationPass
    surface: MorningSurface

    async def run(self, main_id: str, now: Now) -> None:
        """The ``Pass`` protocol's method. Returns ``None``; raises only when a
        transition this main's log should be carrying is not in it."""
        result = await self.consolidate.evaluate(main_id, now)
        await self.surface.surface(
            main_id, now=now, candidates=result.candidates
        )
        completed(result, main_id=main_id)


def _label(outcome: Outcome) -> str:
    return "sent" if isinstance(outcome, Surfaced) else outcome.reason


def _delivered(result: object) -> bool:
    """Whether the channel says it carried anything.

    Tolerant of an adapter that returns nothing at all: the port's contract is
    a ``SendResult``, and an adapter that answers ``None`` has not said it
    failed. Only an explicit *no parts* is read as non-delivery, so a stricter
    reading cannot silence a working adapter.
    """
    if isinstance(result, SendResult):
        return result.parts > 0
    return True


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
