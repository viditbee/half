"""The inbound entrypoint, and the crisis mode behind it (AD-10, CAP-12).

Crisis owns the door and delegates inward. The normal pipeline is something
this module calls, and it has exactly one caller — enforced by
``tests/test_entrypoint.py``.

The inversion matters more than it looks. A crisis *check* that the pipeline
calls is an ordinary function call, and function calls get refactored around
at 2am by someone chasing an unrelated bug. Making crisis the entrypoint means
there is no route into the pipeline that skips it. Python cannot structurally
forbid importing the pipeline directly. This is the strongest available
guarantee, not a proof, and the spine says so.

**Why the two failure headlines are opposite, and why this is a mode.**
*Commission* — Half treated a disclosure as ordinary input, engaged with the
content, agreed, retrieved something true and terrible at the worst moment.
*Omission* — the unsaid queue held, the interrupt law found nothing
irreversible, and Half was being careful while the carefulness was the harm.
Both have one root: Half was still running its normal architecture. So this is
not a special input to the ordinary system. It is a separate mode entered
before any normal machinery touches the message.

**Two actions, with two costs.** Asking is cheap and reversible; entering is
expensive and durable. A build that collapses them governs a main for thirty
days because they mentioned a film, and that is not the asymmetry the companion
argues for.

*Asking* returns one gentle direct question and nothing else. No mode, no cap,
nothing written, nothing durable. If the answer is no, it is over.

*Entering* does four things, in this order:

1. *The suspension is recorded, durably and under the actor's mutex* — the
   crisis record, the ceiling drop and the retrieval disable together, because
   a build where two of the three land is a build where a main is capped but
   retrievable. The crisis record is also the only trace that the mode ever
   opened, and the clinical reviewer's first question is how often it fires and
   on what. It carries a tier and a count, never a word of what was said.
2. *Ledger retrieval is hard-disabled* for that main — and stays disabled
   across eviction and restart, because it is read back from the log at
   hydration. A disabled retriever raises; it never returns an empty set a
   caller could read as *"this main has nothing"*.
3. *The license ceiling drops to `behave`*, durably. Story 6c brings it back,
   a rung at a time and never faster than a floor of thirty days.
4. *The mode is held* — in the log, not in memory. **Nothing exits it, in this
   story or in 6c**: the companion leaves *who decides it is over* an open
   question, and a build that answered it with a timeout, a keyword or a
   process restart would be answering a clinical question by accident.

**Coming back, and where it happens** (story 6c). Aftercare is evaluated on the
main's own turn — there is no scheduler and none is built — and whatever it has
to say is appended to the reply this turn was already producing. It restores
the ceiling one rung at a time from a thirty-day floor, silently for the first
step, and it *asks* before the mirror resumes: elapsed time is never the last
condition, and a main who does not answer stays where they are. A main who
declines is asked again later, because declining once must not mean never being
asked again. The floor runs from the most recent entry, so a fresh disclosure
inside the mode restarts it.

**The plan Half holds, produced the moment it is asked for.** A safety plan in
a drawer is useless at three in the morning, so a request for one is answered
on the turn it arrives, in the mode or out of it, from a document a professional
wrote. Half never authors one — see ``half.crisis.safetyplan``, where the
absence of an authoring surface is a property of the file rather than a rule
about it.

**Reversing a false entry.** A durable cap with no way back is a trap rather
than a safety feature, so there is one documented, deliberate, recorded path:

    from half.actor.registry import ActorRegistry
    registry = ActorRegistry("~/.half")
    asyncio.run(registry.reverse_crisis(
        "vidit", t="2026-09-01T22:14:00Z",
        because="entered on a film quote; confirmed with the main"))

That is an operator action with a stated reason that outlives whoever typed it.
It is not a mode-exit policy and must never be automated — see
``ActorRegistry.reverse_crisis``.

**The opener first, then the door.** Story 6b adds the warm handoff: two or
three ways to reach a human, offered *after* the reply and never instead of it.
Leading with a list of numbers answers a disclosure with logistics, which is
the rushing-to-fix the companion says reads as minimising. The ordering is
structural — ``respond.reply_for`` is called first and its text is the prefix
of what returns — and the handoff is assembled by a desk that never raises, so
a missing directory or an unreadable log costs a tap and never the reply.

When there is no door to offer — nobody confirmed, nowhere told, a file that
would not parse — nothing is appended and 6a's reply is returned byte for byte.
Its wording already points at both a person the main trusts and a crisis line
where they live, so the fallback is the honest generic sentence rather than
silence or a guessed continent.

The door is offered only on a turn that *enters* the mode. Not on the asking
turn — three paragraphs and a question is the whole of the cheap action, and
handing somebody a list of crisis lines because they mentioned a film is the
sensationalising the templates module refuses on the same grounds. And not on
the third-party path, which surfaces a resource the main can share and stops:
no contact, no draft aimed at anyone, unchanged from 6a.

**A second opinion, on the cheap action only** (story 6d). The tier table is a
phrase table, and a phrase table fires only on what somebody thought to write
down: it returns nothing for ``kms``, ``unalive myself``, ``im sucidal`` and for
every phrasing in a script nobody added a row for. So when the table finds
nothing, a model is asked — and what it is allowed to do with the answer is to
make Half *ask*. It cannot enter: entering carries a durable thirty-day cap, and
the mapping in ``half.crisis.classifier`` has no value that could reach one.

The consultation happens once per turn at most, and only where it could change
something: not when the table already decided, not when the mode is open, and
not when a question of Half's is already standing — asking twice in a row is
nagging in the one register where nagging is unforgivable, and the standing
question is already the widest thing this gate can do.

The model that ran and is unsure is not the model that did not run. The first
asks; the second leaves the table's answer exactly as story 6a left it, and is
counted so an operator can see a classifier failing rather than a product where
nobody is ever at risk. Neither costs a main their reply: the consult never
raises, and the gate catches anything it might anyway.

*Where this sits, and AD-23.* The gate is not a webhook handler. It runs on the
turn the adapter has already acknowledged — long-polling today, and a WhatsApp
adapter must acknowledge inside five seconds and enqueue before reaching here,
which is AD-23 and is now load-bearing rather than merely stated: this is the
first thing on the inbound path that waits on a network.

**Nothing may cost the main their reply.** Every durable step is inside one
broad ``except``: a corrupt log, a full disk, a refactored signature, anything.
The suspension is best-effort and the reply is not. An earlier version let a
``StoreError`` out of the switch resolver and the main received nothing at all,
which is the omission headline reproduced exactly.

**Nothing is recorded but the suspension.** The pipeline is not called on a
crisis turn or an asking turn, so no belief is appended — not the main's
message, and above all nothing about a third party.

**Never gated by tier.** Nothing on this path reads a plan, a subscription or a
payment state; ``signals.assess`` takes only the message. Free and lapsed mains
get identical behaviour because there is no value to branch on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol, runtime_checkable

from half.channel.port import Inbound
from half.crisis import handoff
from half.crisis import respond
from half.crisis.aftercare import Schedule
from half.crisis.classifier import SecondOpinion
from half.crisis.handoff import Desk
from half.crisis.safetyplan import Holder
from half.crisis.signals import (
    Action,
    Assessment,
    Tier,
    assess,
    is_affirmative,
    is_plan_intake,
    is_plan_request,
)

logger = logging.getLogger(__name__)

#: What the gate delegates to once a turn is judged ordinary.
Pipeline = Callable[[Inbound], Awaitable[str | None]]


@runtime_checkable
class CrisisStore(Protocol):
    """The durable half of the mode. ``ActorRegistry`` satisfies it.

    Two operations, deliberately: reading whether the mode is open, and
    applying the whole suspension at once. Splitting the second into a switch,
    a ceiling and a record gave three things that could land separately, and
    two of them landing is the state nobody designed.
    """

    def crisis_open(self, main_id: str) -> bool:
        """Whether this main is in the mode, per their log."""
        ...

    async def suspend_for_crisis(
        self, main_id: str, *, t: str, tier: str, score: int, fresh: bool = True
    ) -> None:
        """Record the entry, drop the ceiling, disable retrieval — atomically
        enough that no two of the three can be observed apart, and under the
        main's own mutex (AD-1).

        ``fresh`` says whether this turn detected something new, as against the
        mode simply being open already. A fresh disclosure is a new entry, and
        aftercare's floor runs from the most recent one (story 6c)."""
        ...


@dataclass(slots=True)
class VolatileCrisisStore:
    """A standalone gate's memory of who is in the mode.

    **Not durable, and it says so.** A gate constructed without a real store —
    in a test, or in a caller that has not wired one — still holds the mode for
    the life of the process, still caps nothing, and loses everything on
    restart. The runtime always passes the registry; this exists so that a gate
    with no store fails visibly in one direction only, by forgetting, rather
    than by pretending it wrote something.
    """

    open_for: set[str] = field(default_factory=set)

    def crisis_open(self, main_id: str) -> bool:
        return main_id in self.open_for

    async def suspend_for_crisis(
        self, main_id: str, *, t: str, tier: str, score: int, fresh: bool = True
    ) -> None:
        self.open_for.add(main_id)


class CrisisGate:
    """Every inbound message crosses this before anything else sees it."""

    def __init__(
        self,
        pipeline: Pipeline,
        store: CrisisStore | None = None,
        *,
        desk: Desk | None = None,
        schedule: Schedule | None = None,
        holder: Holder | None = None,
        second: SecondOpinion | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._store: CrisisStore = store if store is not None else VolatileCrisisStore()
        # Aftercare, and the plan Half holds. Both are wired the way the desk
        # is: a gate built without them behaves exactly as it did before this
        # story — nothing restores, and Half says it holds no plan — rather
        # than failing on the path where failing is the catastrophe.
        self._schedule: Schedule = schedule if schedule is not None else Schedule()
        self._holder: Holder = holder if holder is not None else Holder()
        # The handoff. A desk with nothing wired offers nothing, which is the
        # same outcome as a main who has confirmed nobody — so a gate built
        # without one behaves exactly as it did before story 6b rather than
        # failing on the path where failing is the catastrophe.
        self._desk: Desk = desk if desk is not None else Desk()
        # The second opinion (story 6d). Wired the way the desk is: a gate
        # built without one behaves exactly as it did before this story —
        # the phrase table decides alone, offline — rather than failing on the
        # path where failing is the catastrophe. A gate built *with* one holds
        # an object that cannot produce text and cannot enter the mode.
        self._second: SecondOpinion | None = second
        # Mains this process suspended, kept beside the durable record rather
        # than instead of it. If the append failed — a full disk, a corrupt log
        # — the main is still in the mode for as long as this worker lives, and
        # the failure is loud in the log rather than silent in the product.
        self._fallback: set[str] = set()
        # Who has an unanswered question from Half, by the message it was asked
        # on. Volatile by AD-26, and correctly so: this is how the conversation
        # is *right now*, it expires by itself, and losing it costs a
        # confirmation shortcut rather than a mode. It also stops Half asking
        # twice in a row, which would be nagging in the one register where
        # nagging is unforgivable.
        self._asked: dict[str, str] = {}

    # -- the turn -------------------------------------------------------------

    async def handle(self, inbound: Inbound) -> str | None:
        """Assess once, then act on that one assessment.

        Returns the reply text, or ``None`` for silence — which is a first-class
        outcome for an *ordinary* turn (AD-27) and never one for a crisis turn.

        A turn *inside* an open mode is assessed a second time, and only there:
        the reply is the held plan whatever the message says, but a fresh
        disclosure is still an event that restarts aftercare's floor. See
        ``_renewed``.
        """
        decision = self._decide(inbound)
        # The second opinion, where the table found nothing (story 6d). It can
        # turn this turn into a question and can do nothing else — see
        # ``_second_opinion``, and ``half.crisis.classifier`` for why the
        # mapping has no value that reaches the mode.
        decision = await self._second_opinion(inbound, decision)
        # The plan is handled once, before anything else, because whether this
        # turn was about it changes what aftercare may say afterwards. Nothing
        # is read or written unless a phrase matched.
        #
        # Never on a turn about somebody else. A message like *"my friend said
        # she wants to kill herself, should i make her a safety plan"* is both
        # a third-party disclosure and a plan phrase, and answering it with the
        # main's own document would be Half changing the subject to them at the
        # moment they are frightened for somebody else — the same rule that
        # keeps aftercare silent there.
        wanted = (
            "" if decision.action is Action.SURFACE
            else await self._plan_turn(inbound)
        )

        # The override hook is consulted only when the tier table did not
        # already decide, so an ordinary turn costs one assessment and a crisis
        # turn costs one assessment.
        if decision.enters or self._is_crisis(inbound, decision=decision):
            self._asked.pop(inbound.main_id, None)
            await self._suspend(inbound, decision, self._renewed(inbound, decision))
            reply = await self._respond_to_crisis(inbound, decision=decision)
            return await self._and_aftercare(inbound, reply, wanted=wanted)

        if decision.action is Action.SURFACE:
            # Somebody other than the main. A resource the main can share, and
            # it stops here: the mode is not entered, no ceiling moves, and the
            # pipeline is not called — so no belief about that person is
            # written to any store. Aftercare stays quiet on this turn: the
            # subject is somebody else, and Half's own question does not belong
            # underneath it.
            self._asked.pop(inbound.main_id, None)
            return await self._and_aftercare(
                inbound, respond.reply_for(decision), wanted=wanted, quiet=True
            )

        if decision.action is Action.ASK:
            # Half has just asked one direct question. Aftercare stays quiet
            # underneath it: two questions in one message is nagging in the
            # register where nagging is unforgivable, and it would leave the
            # main's next *yes* answering whichever of them the code looked at
            # first.
            self._asked[inbound.main_id] = inbound.external_id
            return await self._and_aftercare(
                inbound, respond.reply_for(decision), wanted=wanted, quiet=True
            )

        # Any other resolution answers or abandons a standing question.
        self._asked.pop(inbound.main_id, None)
        return await self._and_aftercare(
            inbound, await self._pipeline(inbound), wanted=wanted
        )

    # -- the second opinion (story 6d) ----------------------------------------

    async def _second_opinion(
        self, inbound: Inbound, decision: Assessment
    ) -> Assessment:
        """``decision``, possibly widened from nothing to a question. Never raises.

        Consulted **only when the table found nothing**, which is what makes
        *one classification per turn at most* true by construction rather than
        by counting: every other resolution returns before the call is built.
        Three of those returns are load-bearing rather than merely economical.

        *The table decided.* A safe word and an explicit disclosure enter
        offline, with the provider down and the network unplugged — the
        unconditional escape hatch stays unconditional, and it is unconditional
        because nothing on its path can fail. An asking turn is already the
        widest thing this gate does, and a surfacing turn is about somebody
        else.

        *The mode is open.* ``_decide`` short-circuits to ``HELD`` — which
        enters — the moment it is, so an action of ``NONE`` **is** the closed
        mode, read from the same place the reply is. A held main's every turn
        would otherwise be sent to a provider for an answer that could not
        change anything.

        *A question of Half's is standing.* 6a's rule, and it outranks the
        model: more hedging does not ask again, and a model reading risk in a
        message the main sent *while already being asked about it* would ask
        again. The main's answer is what moves next, either way.

        A widened turn is an ordinary ``INFERENCE`` — the same tier, the same
        reviewed question, the same absence of a cap — so nothing downstream
        can tell a model's suspicion from a phrase table's, and there is no
        second, weaker asking path for a later story to find.
        """
        if self._second is None:
            return decision
        if decision.action is not Action.NONE:
            return decision
        if inbound.main_id in self._asked:
            return decision
        try:
            verdict = await self._second.consult(
                inbound.text, main_id=inbound.main_id
            )
        except Exception:
            # ``consult`` answers with a verdict rather than raising, so this
            # is unreachable through it — and broad for the reason ``_suspend``
            # is broad: on the one path where going quiet is a documented
            # catastrophic failure, the set of exceptions worth losing a reply
            # over is empty. No content, no message text (AD-22).
            logger.exception(
                "the second opinion could not be taken for main=%s; the phrase "
                "table's answer stands", inbound.main_id
            )
            return decision
        if not verdict.asks:
            # Either the model saw nothing, or it did not run. The difference
            # is counted inside the classifier and is invisible here on
            # purpose: both leave story 6a's answer exactly as it was.
            return decision
        return Assessment(Tier.INFERENCE, Action.ASK)

    # -- aftercare, and the plan (story 6c) -----------------------------------

    async def _plan_turn(self, inbound: Inbound) -> str:
        """What this turn has to say about the safety plan, or "". Never raises.

        Two things a main does with a plan, in the order they can happen on one
        message: hand one over, or ask for the one Half has. Handing one over
        wins, because a message that is both is a main giving Half a document
        and there is nothing yet to produce.
        """
        try:
            if is_plan_intake(inbound.text):
                return await self._holder.receive(
                    inbound.main_id, inbound.text, t=inbound.t
                )
        except Exception:
            # No content, no plan text, no message text (AD-22).
            logger.exception(
                "a safety plan could not be taken for main=%s; the rest of the "
                "reply stands", inbound.main_id
            )
            return ""
        return self._wants_plan(inbound)

    def _wants_plan(self, inbound: Inbound) -> str:
        """The held safety plan as text to append, or "". Never raises.

        Produced on the turn it is asked for, in the mode or out of it, because
        a safety plan in a drawer is useless at three in the morning. Nothing
        here writes: producing a plan records no belief, moves no ceiling, and
        neither enters nor exits the mode.

        Broad on purpose, for the reason ``_door`` is broad. ``Holder.produce``
        already swallows its own failures and answers with a sentence rather
        than with nothing; this catches the phrase check and the rendering, and
        a failure costs the plan rather than the reply.
        """
        try:
            if not is_plan_request(inbound.text):
                return ""
            return self._holder.produce(inbound.main_id)
        except Exception:
            # No content, no plan text, no message text (AD-22).
            logger.exception(
                "a safety plan could not be produced for main=%s; the rest of "
                "the reply stands", inbound.main_id
            )
            return ""

    async def _and_aftercare(
        self,
        inbound: Inbound,
        reply: str | None,
        *,
        wanted: str = "",
        quiet: bool = False,
    ) -> str | None:
        """This turn's reply, with the plan and whatever aftercare says.

        **Evaluated on the main's own turn, and never pushed.** There is no
        scheduler here and none is built: the restore is a question about
        somebody who is already in the conversation, so it is asked where they
        are rather than by interrupting them to ask permission to interrupt.

        The order is the moment's. Whatever this turn was about comes first,
        then the door if there was one, then the plan if the main asked for it,
        and only then Half's own question — which is not asked at all on a turn
        that was already about something else (``quiet``).

        Silence stays available. An ordinary turn with nothing to say and no
        aftercare due still returns ``None`` (AD-27); it stops being silence
        only when there is something Half owes the main.
        """
        said = await self._schedule.evaluate(
            inbound.main_id,
            now=inbound.t,
            text=inbound.text,
            quiet=quiet or bool(wanted),
        )
        parts = [part for part in (reply, wanted, said) if part]
        if not parts:
            return reply  # ``None`` for silence, "" for an empty ordinary reply
        return respond.SEPARATOR.join(parts)

    # -- the two seams --------------------------------------------------------

    def _is_crisis(
        self, inbound: Inbound, *, decision: Assessment | None = None
    ) -> bool:
        """Whether this turn is handled as crisis.

        True while the mode is open, because nothing exits it, and otherwise
        exactly when the tier table maps the signal to ``Action.ENTER``. Entry
        is a lookup in that table, never a condition spelled out here.
        """
        found = decision if decision is not None else self._decide(inbound)
        return found.enters

    async def _respond_to_crisis(
        self, inbound: Inbound, *, decision: Assessment | None = None
    ) -> str:
        """The reply, assembled from templates, then the door (CAP-12).

        The tier chooses a plan; the plan is a tuple of template lines. The
        main's text reaches nothing here — ``respond.reply_for`` takes the
        assessment — so no phrasing of a method request can produce method
        content, and no reply is ever empty.

        The handoff is appended after that text and never woven into it, which
        is what makes *"opener first, handoff after"* a property of this
        function rather than a convention about the templates. An offer with
        fewer than two doors appends nothing at all, so a main with nobody
        confirmed and nowhere told receives exactly 6a's reply.
        """
        found = decision if decision is not None else self._decide(inbound)
        if not found.enters:
            # Reached when a subclass overrides ``_is_crisis``. Treat it as the
            # mode being open rather than raising: an exception here would cost
            # the main their reply.
            found = Assessment(Tier.HELD, Action.ENTER, scored=False)
        opener = respond.reply_for(found)
        return opener + self._door(inbound.main_id)

    def _door(self, main_id: str) -> str:
        """The handoff, as text to append to the opener, or nothing.

        Never raises. ``Desk.offer`` swallows its own failures, and this
        swallows the rendering's — broad for the reason ``_suspend`` is broad:
        on the one path where going quiet is a documented catastrophic failure,
        the set of exceptions worth losing a reply over is empty. A door is a
        thing to add to a reply, never a thing that can subtract one.

        The closed-set check runs here, on the production path, for the reason
        ``respond.reply_for`` runs its own: a rendering that stopped being made
        of reviewed lines and reconstructible rows must break a real reply
        rather than only a test's. A failed check drops the door and keeps the
        opener, because the generic line is always a safe answer and an
        unreviewed sentence never is.
        """
        try:
            offer = self._desk.offer(main_id)
            if not offer.speaks:
                return ""
            rendered = handoff.render(offer)
            if not handoff.is_offer_templated(rendered, offer):
                logger.error(
                    "the handoff rendering for main=%s was not made of "
                    "reviewed lines and its own options; offering the generic "
                    "line instead", main_id,
                )
                return ""
            return respond.SEPARATOR + rendered
        except Exception:
            # No content, no name, no message text (AD-22). The opener stands.
            logger.exception(
                "the handoff could not be rendered for main=%s; the generic "
                "line stands", main_id
            )
            return ""

    # -- deciding -------------------------------------------------------------

    def _decide(self, inbound: Inbound) -> Assessment:
        """What this turn is. Pure — every side effect belongs to ``handle``.

        An open mode outranks everything: a main already in it gets the held
        plan whatever this turn says, including a turn that reads as ordinary
        and including one arguing that the mode should end.

        A standing question changes how the next message reads, and only the
        next one. *Yes*, *sometimes*, *kind of* and *maybe* all enter — treating
        a hedged yes as a no is the hedge that makes asking pointless. More
        hedging does **not** ask again: the question already stands, and asking
        twice in a row is nagging in the one register where nagging is
        unforgivable.
        """
        if self._open(inbound.main_id):
            return Assessment(Tier.HELD, Action.ENTER, scored=False)

        found = assess(inbound.text)
        if inbound.main_id not in self._asked:
            return found
        if found.action is Action.NONE and is_affirmative(inbound.text):
            return Assessment(Tier.CONFIRMATION, Action.ENTER, scored=False, score=1)
        if found.action is Action.ASK:
            return Assessment(Tier.NONE, Action.NONE, score=found.score)
        return found

    def _open(self, main_id: str) -> bool:
        """Whether the mode is open for this main, durably or in this process.

        A store that cannot be read is not allowed to raise on the reply path,
        and it is not allowed to put every main into the mode either: an
        unreadable store answers *not open*, while the mains this process
        suspended stay suspended regardless.
        """
        if main_id in self._fallback:
            return True
        try:
            return self._store.crisis_open(main_id)
        except Exception:
            # No content, no message text (AD-22). The main still gets a reply.
            logger.exception(
                "could not read crisis state for main=%s; treating the mode as "
                "closed for this turn", main_id
            )
            return False

    def _renewed(self, inbound: Inbound, decision: Assessment) -> Assessment | None:
        """The signal this turn found, if it is a *new* one. Pure.

        ``_decide`` short-circuits to ``HELD`` the moment the mode is open,
        because the mode outranks everything and the reply is the held plan
        whatever the message says. That is still true of the *reply*. It is not
        true of the *record*: a main who discloses again a fortnight into
        aftercare has had a second crisis, and CAP-12's floor runs from the
        most recent entry rather than from the first (story 6c), so the entry
        has to exist in the log with its own stamp.

        So a held turn is assessed a second time, and only a held turn. The
        cost is one pure function over one message; the alternative was a floor
        that could not restart, or a ``HELD`` reply carrying a tier it did not
        act on.

        ``None`` means nothing new was found — the ordinary case inside a long
        conversation in the mode, where one record per message would be a log
        full of the same fact.
        """
        if decision.tier is not Tier.HELD:
            return decision
        found = assess(inbound.text)
        return found if found.enters else None

    async def _suspend(
        self,
        inbound: Inbound,
        decision: Assessment,
        renewed: Assessment | None = None,
    ) -> None:
        """Enter the mode for this main. Never raises.

        Broad on purpose. The narrow version caught ``HalfError`` only, and the
        two failures that actually happened were neither: hydrating the actor
        to reach its retrieval switch opened a store — so a ``StoreError`` came
        out of the *resolver* before the reply was composed — and an
        ``OSError`` from a full disk was never a ``HalfError`` at all. On the
        one path where going quiet is a documented catastrophic failure, the
        set of exceptions worth losing a reply over is empty.

        ``CancelledError`` is not caught: shutdown is not a message failure.
        """
        self._fallback.add(inbound.main_id)
        # A fresh signal is recorded as itself — *disclosure*, not *held* — so
        # the one record a clinical reviewer reads says what fired and when.
        found = renewed if renewed is not None else decision
        try:
            await self._store.suspend_for_crisis(
                inbound.main_id,
                t=inbound.t,
                tier=str(found.tier),
                score=found.score,
                # False only when this turn found nothing new and the mode was
                # simply already open. That difference is what lets aftercare's
                # floor run from the most recent disclosure rather than from
                # the first (story 6c), while a long conversation inside the
                # mode still appends one record rather than one per turn.
                fresh=renewed is not None,
            )
        except Exception:
            # Loud, because a suspension that did not persist is a main who
            # comes back uncapped and out of the mode. Content-free (AD-22).
            logger.exception(
                "crisis suspension did not persist for main=%s; held in memory "
                "only for the life of this process", inbound.main_id
            )

    # -- introspection --------------------------------------------------------

    def in_crisis(self, main_id: str) -> bool:
        """Whether the mode is open for this main.

        There is deliberately no method that closes it. Mode *exit* is the
        companion's first open question — who decides it is over, and how the
        mirror comes back without feeling like surveillance resuming — and
        answering it with a timeout, a keyword or a quiet expiry would be
        answering a clinical question in code review. Undoing a *false* entry
        is a different thing and lives on the registry, where it is deliberate,
        recorded and reasoned.
        """
        return self._open(main_id)

    def awaiting_answer(self, main_id: str) -> bool:
        """Whether a question from Half is standing for this main."""
        return main_id in self._asked
