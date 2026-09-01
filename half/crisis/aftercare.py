"""Coming back: the floor, the steps, and the question (CAP-12, story 6c).

Story 6a caps a main at `behave` on entering the mode and said, accurately
then, that restoring it was this story. Until now nothing did — a main who
disclosed once was governed silently for ever, which is not care.

**The floor is a floor, not a timer.** Nothing restores before thirty days, and
reaching thirty days grants the *first* step and only that. ``release_ceiling``
used to default to putting everything back at once, which is precisely the
failure CAP-12 names when it says licenses are restored *gradually rather than
at once*, so nothing here names a target rung: it asks the ladder what one step
is (``ladder.next_rung``) and takes that.

**The last step is the main's to grant.** Coming off `behave` restores Half's
ability to *ask*; resuming the mirror restores its ability to *confront* — to
say what it notices about the main to their face. The companion's first open
question is how the mirror comes back without feeling like surveillance
resuming, and the answer this story gives is that it comes back when the main
says so, on a question Half put to them, and never on elapsed time alone. A
main who says nothing stays exactly where they are: **silence is not consent**,
and neither is *maybe* — see ``signals.reads_as_consent``, which is the strict
inverse of the generous reading crisis entry uses.

**A decline is not permanent.** Declining leaves the cap in place and Half asks
again after an interval. A build where saying no once meant never being asked
again would make the question a trap.

**Aftercare is evaluated on the main's own turn.** There is no scheduler here
and none is built: the restore is a question about somebody who is *present*,
so asking it when they are already in the conversation beats interrupting them
to ask permission to interrupt. Caring Contacts are the opposite — their value
is arriving when the main has *not* written — which is why they wait for story
9's due-time queue (AD-9) rather than being approximated with a poll here.

**Nothing here reads a clock.** ``now`` is the stamp the channel adapter read,
threaded down from the inbound message, so the same log and the same ``now``
produce the same state for ever and replay is exact (AD-30). That is enforced
structurally rather than by intention: ``tests/test_crisis.py`` fails the build
if any module under ``half/crisis`` imports ``time`` or ``datetime``, which is
why the arithmetic below is a civil-calendar computation over integers rather
than two ``fromisoformat`` calls.

**Every dwell is measured from the entry, not from when a step landed.** A step
lands on the turn a main happens to take, and a main who does not write for a
month has not thereby earned less time. The consequence — a main returning on
day sixty gets the first step and the question in the same turn — is not a jump
back to full licence, because the mirror still waits for an answer that only a
later turn can carry. Measuring from the entry is also what keeps this a pure
function of two stamps, with no third record to fall out of step with the log.

**What this story does not decide: mode exit.** Story 6a deliberately shipped a
mode nothing closes, because *who decides it is over* is the companion's first
open question and a timeout, a keyword or a quiet expiry would each be
answering a clinical question by accident. Nothing here closes it either. So
aftercare runs on elapsed time since the most recent entry whether or not the
acute mode is still open, and in the current build a restored ceiling has no
visible effect until mode exit is decided by somebody qualified to decide it.
That is a real gap and it is stated here rather than papered over: the
alternative was to invent the exit policy two stories have refused to invent.

One consequence goes to the clinical reviewer with the wording, unsettled here.
Because the mode does not close, the mirror question is put *underneath* a held
crisis reply — six reviewed paragraphs about being present, and then Half
asking whether it may start reflecting things back. Not asking would be the
worse failure: the question is the only route out of the cap, and a build that
withheld it while the mode stayed open would leave every main who ever
disclosed governed for ever, which is the defect this story exists to fix. But
whether that is the right place for the question is a clinical judgement, and
picking the alternative — hold it until somebody decides the mode is over —
would be answering the companion's open question sideways.

**Re-entering restarts the clock.** The floor runs from the *most recent*
entry, never the first, and any aftercare record older than that entry belongs
to a period that ended — it is ignored rather than deleted, because the log is
append-only and what Half asked in July is still true about July.

Pure and stdlib-only apart from the store the ``Schedule`` reads: no clock, no
network, no model, no ambient state. Nothing here re-derives whether the main
is *better* — this module knows two things, how much time has passed and what
the main answered, and there is no third input it could consult.
**The floor is enforced at every path that can raise a cap, not only here.**
The numbers and the calendar arithmetic live in ``half.governance.aftercare``
so that ``ActorRegistry.restore_step`` — the write path a future caller reaches
for — refuses inside the floor on its own account. A rule that lives in one
function is a convention that function follows; this one is checked where the
append happens as well as where the decision is made. Every name from that
module is re-exported here, so the crisis package still reads as one module.

**Aftercare ends.** When the main asks for the mirror back and it is restored,
the period is over: nothing further steps, holds or asks, and a cap somebody
sets afterwards for an unrelated reason is nobody's business but theirs. While
a period *is* running, aftercare owns the ceiling in both directions, and the
most it can ever raise a cap to without the main's word is `ask`.

**The question can be stopped.** *"No, and please stop asking"* ends the asking
for this period while the cap holds exactly where it is. Declining is not
permanent; asking is not perpetual either.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, Mapping, Protocol, runtime_checkable

from half.crisis import respond, signals, templates
from half.governance.aftercare import (
    ANSWER_WINDOW_DAYS,
    ASK_AGAIN_DAYS,
    DAY,
    FLOOR_DAYS,
    MIRROR_DWELL_DAYS,
    answered,
    at_least,
    elapsed,
    entered_at,
    expired,
    instant,
)
from half.governance.ladder import FLOOR, Ceiling, License, height, next_rung
from half.store.ops import (
    AFTERCARE_AGREED,
    AFTERCARE_ASKED,
    AFTERCARE_DECLINED,
    AFTERCARE_STOPPED,
)

logger = logging.getLogger(__name__)

#: Re-exported so that ``half.crisis.aftercare`` remains the one name the rest
#: of the crisis package imports, while the rules themselves sit where the
#: actor can enforce them too.
__all__ = [
    "ANSWER_WINDOW_DAYS", "ASK_AGAIN_DAYS", "DAY", "FLOOR_DAYS",
    "MIRROR_DWELL_DAYS", "MIRROR_REASON", "STEP_REASON", "AftercareStore",
    "Schedule", "Standing", "answered", "at_least", "elapsed", "entered_at",
    "evaluate", "expired", "instant", "question",
]

#: How paragraphs are joined. The same separator the opener and the door use,
#: so one turn is one message taken apart the same way.
SEPARATOR: Final[str] = respond.SEPARATOR

#: What a ceiling record says about a step, in the log, for whoever reads it
#: thirty days later. Content-free (AD-22) and specific about *which* rule
#: moved the cap.
STEP_REASON: Final[str] = "aftercare: the floor is past, one step (CAP-12)"
MIRROR_REASON: Final[str] = "aftercare: the main asked for the mirror back (CAP-12)"
HOLD_REASON: Final[str] = "aftercare: the cap the floor permits (CAP-12)"


@dataclass(frozen=True, slots=True)
class Standing:
    """Where one main's aftercare has got to, on one turn.

    A value, computed from two records and a stamp. It decides nothing on its
    own and writes nothing — ``Schedule`` is what acts on it, so the rule and
    the append are separable and the rule is testable without a store.
    """

    #: Whether aftercare is in force at all. ``False`` once the mirror is back:
    #: the period is over, and nothing steps, holds or asks again.
    running: bool = False
    #: The entry the floor runs from.
    began: str | None = None
    #: The strongest rung aftercare permits right now. Never above `ask`
    #: without the main's word.
    rung: License = FLOOR
    #: Whether the mirror question is due to be put on this turn.
    asks: bool = False
    #: Whether a question has been put, is still fresh, and has not been
    #: answered — so that this turn's message may be read as its answer. False
    #: before Half has asked, which is what stops an unprompted "yes" from
    #: restoring anything, and false again once the question has expired, which
    #: is what stops an affirmative weeks later from being read as its answer.
    awaiting: bool = False
    #: Whether the main has asked not to be asked again.
    stopped: bool = False


def evaluate(
    crisis: Mapping[str, Any] | None,
    care: Mapping[str, Any] | None,
    *,
    now: str,
) -> Standing:
    """What aftercare permits for this main at ``now``. Pure.

    ``crisis`` is the folded crisis record and ``care`` the folded aftercare
    record. Two records and a stamp: there is no argument here through which
    recovery, mood, tier, payment state or a clock could reach the answer.
    """
    began = entered_at(crisis)
    if began is None:
        return Standing()

    if not at_least(FLOOR_DAYS, since=began, now=now):
        # Inside the floor, or a stamp that is not a real instant. No restore
        # by any path, and the question is not due either.
        return Standing(running=True, began=began, rung=License.BEHAVE)

    answer, at = answered(care, since=began)
    if answer == AFTERCARE_AGREED:
        # The mirror is back because the main asked for it. Aftercare is over —
        # it does not go on owning the ceiling for the rest of the main's life,
        # and a cap set afterwards for an unrelated reason is not its business.
        return Standing()

    if not at_least(FLOOR_DAYS + MIRROR_DWELL_DAYS, since=began, now=now):
        # The first step, and the second step's dwell is not up. The question
        # is not asked here, so nothing about the mirror can move.
        return Standing(running=True, began=began, rung=License.ASK)

    if answer == AFTERCARE_STOPPED:
        # The main asked not to be asked. The cap holds; the asking ends.
        return Standing(running=True, began=began, rung=License.ASK, stopped=True)

    return Standing(
        running=True,
        began=began,
        rung=License.ASK,
        # Due when Half has never asked in this period, or when the interval
        # since it last said something about the mirror has passed. A decline
        # and a silence are on the same interval: both mean the cap holds and
        # both must be revisited without nagging.
        #
        # ``expired`` rather than ``at_least`` because the failure directions
        # differ. A record stamped in the future, or one whose stamp cannot be
        # read, would make ``at_least`` false for ever and silence the question
        # until a clock caught up — and the question is the only route out of
        # the cap. Asking again costs a paragraph; not asking costs the return.
        asks=answer is None or expired(ASK_AGAIN_DAYS, since=at, now=now),
        # A question is answerable while it is fresh. It expires, because an
        # affirmative typed weeks later is not this question's answer — and an
        # unreadable or future-dated stamp counts as expired, which is the safe
        # direction for the one field that can lift a cap.
        #
        # A **decline** leaves it answerable for the rest of that window rather
        # than closing it. Not because a no is weak — the cap holds either way,
        # and nothing here reads silence or a hedge as consent — but because a
        # main who says no on Tuesday and *"yes please"* on Wednesday has
        # changed their mind, and a build that ignored them for the next
        # fortnight would be holding them to an answer they had withdrawn. The
        # main always wins; the strictness that matters is what counts as a
        # yes, and that is unchanged.
        awaiting=(
            answer in (AFTERCARE_ASKED, AFTERCARE_DECLINED)
            and not expired(ANSWER_WINDOW_DAYS, since=at, now=now)
        ),
    )


def question() -> str:
    """The mirror question, as the three reviewed paragraphs it is."""
    return SEPARATOR.join(line.text for line in templates.AFTERCARE_ASK_LINES)


@runtime_checkable
class AftercareStore(Protocol):
    """The durable half. ``ActorRegistry`` satisfies it.

    Deliberately narrow, and narrow in the same way the handoff's ``Held`` is:
    aftercare may read what time the mode opened, where the conversation about
    coming back got to, and what the cap is. It may not read the ledger, which
    the mode hard-disabled, and there is no method here through which it could.
    """

    def crisis_record(self, main_id: str) -> dict[str, Any] | None: ...

    def aftercare_record(self, main_id: str) -> dict[str, Any] | None: ...

    def license_ceiling(self, main_id: str) -> Ceiling: ...

    async def note_aftercare(self, main_id: str, *, t: str, state: str) -> None:
        """Record that the question was put, or how the main answered it."""
        ...

    async def hold_ceiling(
        self, main_id: str, *, to: License, t: str, because: str
    ) -> Ceiling:
        """Hold the cap down to ``to``. Only lowers."""
        ...

    async def restore_step(
        self, main_id: str, *, t: str, because: str, note: str | None = None
    ) -> Ceiling:
        """Raise the cap by exactly one rung, refusing inside the floor, with
        the record that explains it, under the main's own mutex (AD-1)."""
        ...


@dataclass(slots=True)
class Schedule:
    """Applies what aftercare is due, on one main's turn. Never raises.

    Constructed with nothing at all in a caller that has not wired it, and then
    it does nothing — which is exactly the behaviour before this story, and is
    the failure direction a half-deployed build must have: a main stays capped,
    rather than a main losing their reply to an aftercare bug.
    """

    #: Where the records come from. ``None`` means aftercare does not run.
    store: AftercareStore | None = None

    async def evaluate(
        self, main_id: str, *, now: str, text: str, quiet: bool = False
    ) -> str:
        """Apply what is due and return what to say, or "". Never raises.

        Broad on purpose, and for the reason the gate's suspension is broad: on
        the one path where going quiet is a documented catastrophic failure,
        the set of exceptions worth losing a reply over is empty. A store that
        cannot be read costs a step, never the turn.

        ``quiet`` suppresses the *question* and the reading of an answer, never
        the step. It is set on a turn that is already about something else — a
        main asking for their safety plan, or telling Half about somebody
        else's danger — because putting *"shall I start saying what I notice
        about you again?"* underneath either of those is answering somebody's
        subject with Half's own.
        """
        try:
            return await self._evaluate(main_id, now=now, text=text, quiet=quiet)
        except Exception as exc:
            # No content, no wording, no main-identifying string beyond the id
            # the runtime already logs, and the class of the fault rather than
            # its own text (AD-22, story 6d). The turn still replies.
            logger.warning(
                "aftercare could not be evaluated for main=%s (%s); nothing "
                "restored on this turn", main_id, type(exc).__name__
            )
            return ""

    async def _evaluate(
        self, main_id: str, *, now: str, text: str, quiet: bool
    ) -> str:
        store = self.store
        if store is None:
            return ""
        standing = evaluate(
            store.crisis_record(main_id),
            store.aftercare_record(main_id),
            now=now,
        )
        if not standing.running:
            return ""

        # The step time alone earns, applied before anything is said. Silent by
        # design: coming off `behave` is a return to ordinary conversation, and
        # announcing it would be a status update about Half in a conversation
        # that is not about Half.
        await self._step(main_id, standing.rung, now=now, because=STEP_REASON)

        if quiet:
            return ""

        # A request to stop is honoured whether or not a question is standing.
        # The main always wins, and being asked not to ask is not a thing to
        # make somebody time correctly.
        if not standing.stopped and signals.asks_to_stop(text):
            await store.note_aftercare(main_id, t=now, state=AFTERCARE_STOPPED)
            return self._checked(templates.AFTERCARE_STOPPED.text)

        if standing.awaiting:
            said = await self._answer(main_id, store=store, text=text, now=now)
            if said is not None:
                return said

        if standing.asks and not standing.stopped:
            await store.note_aftercare(main_id, t=now, state=AFTERCARE_ASKED)
            return self._checked(question())
        return ""

    async def _answer(
        self, main_id: str, *, store: AftercareStore, text: str, now: str
    ) -> str | None:
        """Read this turn as the answer to a standing question, or not at all.

        ``None`` means the message was neither a yes nor a no — which leaves
        the cap where it is and the question standing. That is the common case
        and it is the right one: most messages are not answers, and treating
        one as a yes is the restore this story exists to prevent.

        A hedge lands with the refusals. *Maybe* is not consent, and it is not
        nothing either: the main answered, so Half acknowledges it and asks
        again on the ordinary interval rather than sitting on a question they
        have already replied to.
        """
        if signals.reads_as_consent(text):
            await self._step(
                main_id, License.ASSERT, now=now,
                because=MIRROR_REASON, note=AFTERCARE_AGREED,
            )
            return self._checked(templates.AFTERCARE_AGREED.text)
        if signals.reads_as_refusal(text):
            await store.note_aftercare(main_id, t=now, state=AFTERCARE_DECLINED)
            return self._checked(templates.AFTERCARE_DECLINED.text)
        return None

    async def _step(
        self, main_id: str, target: License, *, now: str, because: str,
        note: str | None = None,
    ) -> None:
        """Move the cap toward ``target`` — up by at most one rung, down freely.

        **Aftercare owns the ceiling while a period is running**, and that is
        one rule read in two directions rather than two rules. Upward, the store
        enforces the one-rung limit *and the floor* at the append and this asks
        for a step rather than naming a rung, so there is no arithmetic anywhere
        that could produce a full restore or an early one. Downward, a cap
        sitting *above* what the floor permits is a suspension that did not
        land — a process killed between the entry's two appends — and holding it
        back down is what the crisis path used to do by re-capping on every
        turn, at the price of making every restore last exactly one message.

        The most this can reach without the main's word is `ask`, and once the
        mirror is back the period is over and nothing here runs again — so an
        operator's later cap is not walked back by a schedule that outlived its
        own purpose.
        """
        store = self.store
        if store is None:  # pragma: no cover - guarded by the caller
            return
        current = store.license_ceiling(main_id).rung
        if height(target) < height(current):
            await store.hold_ceiling(
                main_id, to=target, t=now, because=HOLD_REASON,
            )
        if height(target) <= height(current):
            if note is not None:
                # The answer is still recorded even when the cap is already
                # where the answer would put it. What the main said is not a
                # side effect of the ceiling moving.
                await store.note_aftercare(main_id, t=now, state=note)
            return
        if next_rung(current) is None:  # pragma: no cover - unreachable at TOP
            return
        await store.restore_step(main_id, t=now, because=because, note=note)

    def _checked(self, said: str) -> str:
        """``said`` if it is made of reviewed lines, otherwise nothing.

        The closed-set check, on the production path for the reason
        ``respond.reply_for`` runs its own: a version of it that answered
        ``True`` unconditionally must break a real reply rather than only a
        test's. Dropping the sentence is the safe failure — the cap has already
        moved or held on the record, and a paragraph nobody reviewed is the one
        thing that must not reach a main here.
        """
        if respond.is_templated(said):
            return said
        logger.error(
            "an aftercare sentence was not made of reviewed lines; saying "
            "nothing rather than saying it"
        )
        return ""
