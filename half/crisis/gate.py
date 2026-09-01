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
3. *The license ceiling drops to `behave`*, durably. Restoring it is story 6c,
   so a slipped 6c leaves Half quiet rather than loud.
4. *The mode is held* — in the log, not in memory. Nothing here exits it: the
   companion leaves *who decides it is over* an open question, and a build that
   answered it with a timeout, a keyword or a process restart would be
   answering a clinical question by accident.

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
from half.crisis.handoff import Desk
from half.crisis.signals import (
    Action,
    Assessment,
    Tier,
    assess,
    is_affirmative,
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
        self, main_id: str, *, t: str, tier: str, score: int
    ) -> None:
        """Record the entry, drop the ceiling, disable retrieval — atomically
        enough that no two of the three can be observed apart, and under the
        main's own mutex (AD-1)."""
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
        self, main_id: str, *, t: str, tier: str, score: int
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
    ) -> None:
        self._pipeline = pipeline
        self._store: CrisisStore = store if store is not None else VolatileCrisisStore()
        # The handoff. A desk with nothing wired offers nothing, which is the
        # same outcome as a main who has confirmed nobody — so a gate built
        # without one behaves exactly as it did before story 6b rather than
        # failing on the path where failing is the catastrophe.
        self._desk: Desk = desk if desk is not None else Desk()
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
        """
        decision = self._decide(inbound)
        # The override hook is consulted only when the tier table did not
        # already decide, so an ordinary turn costs one assessment and a crisis
        # turn costs one assessment.
        if decision.enters or self._is_crisis(inbound, decision=decision):
            self._asked.pop(inbound.main_id, None)
            await self._suspend(inbound, decision)
            return await self._respond_to_crisis(inbound, decision=decision)

        if decision.action is Action.SURFACE:
            # Somebody other than the main. A resource the main can share, and
            # it stops here: the mode is not entered, no ceiling moves, and the
            # pipeline is not called — so no belief about that person is
            # written to any store.
            self._asked.pop(inbound.main_id, None)
            return respond.reply_for(decision)

        if decision.action is Action.ASK:
            self._asked[inbound.main_id] = inbound.external_id
            return respond.reply_for(decision)

        # Any other resolution answers or abandons a standing question.
        self._asked.pop(inbound.main_id, None)
        return await self._pipeline(inbound)

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

    async def _suspend(self, inbound: Inbound, decision: Assessment) -> None:
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
        try:
            await self._store.suspend_for_crisis(
                inbound.main_id,
                t=inbound.t,
                tier=str(decision.tier),
                score=decision.score,
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
