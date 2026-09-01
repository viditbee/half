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

**Entering does four things, in this order:**

1. *Ledger retrieval is hard-disabled* for that main. Not discouraged — a
   disabled retriever raises, and never returns an empty set a caller could
   read as *"this main has nothing"*. Nothing true about the main's past is
   safe to surface here.
2. *The license ceiling drops to `behave`, durably.* If entry did not cap, a
   crisis conversation would be followed by ordinary Half — nudges, tensions,
   the mirror. Restoring it is story 6c, so a slipped 6c leaves Half quiet
   rather than loud, which is the safe failure.
3. *The reply is assembled from templates*, from a plan chosen by tier. The
   main's text is not an argument to the assembly, so no phrasing carries
   anything into the reply.
4. *The mode is held.* Nothing here exits it: the companion leaves *who
   decides it is over* an open question, and a build that answered it silently
   would be answering a clinical question with a timeout.

**Nothing is recorded.** The pipeline is not called, so no belief is appended
for a crisis turn — not the main's message, and above all nothing about a third
party. The ceiling record is the single exception, and it is a governance fact
about the main rather than a claim about anybody.

**Never gated by tier.** Nothing on this path reads a plan, a subscription or a
payment state; ``signals.assess`` takes only the message. Free and lapsed mains
get identical behaviour because there is no value to branch on.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from half.channel.port import Inbound
from half.crisis import respond
from half.crisis.signals import ACTION_FOR, Action, Assessment, Tier, assess
from half.errors import CrisisError, HalfError
from half.governance.ladder import Ceiling, License
from half.retrieval.rank import RetrievalSwitch

logger = logging.getLogger(__name__)

#: What the gate delegates to once a turn is judged ordinary.
Pipeline = Callable[[Inbound], Awaitable[str | None]]

#: Resolves one main's retrieval switch. A function rather than a switch,
#: because crisis is a state of one person and not of the worker process.
SwitchFor = Callable[[str], RetrievalSwitch]

#: Lowers one main's license ceiling, durably (AD-28). The registry's
#: ``lower_ceiling``: it appends before it moves the in-memory value, so a
#: crash between the two leaves a main *more* capped than the process thought.
#: ``t`` is the inbound stamp — nothing on this path reads a clock (AD-30).
LowerCeiling = Callable[..., Ceiling]

#: The rung crisis entry caps every license at. One rung, and the weakest.
CRISIS_CEILING: License = License.BEHAVE


class CrisisGate:
    """Every inbound message crosses this before anything else sees it."""

    def __init__(
        self,
        pipeline: Pipeline,
        retrieval: SwitchFor | None = None,
        lower_ceiling: LowerCeiling | None = None,
    ) -> None:
        self._pipeline = pipeline
        # CAP-12 requires ledger retrieval to be hard-disabled in crisis mode,
        # and the gate is the only place that knows the mode has been entered.
        # It is resolved per main: the runtime passes the actor registry's
        # resolver, so the switch this turns off is the one that main's own
        # retriever reads. A gate built without one keeps its own per-main
        # switches rather than a single shared flag, so even the standalone
        # case cannot silence a bystander.
        self._own: dict[str, RetrievalSwitch] = {}
        self._retrieval = retrieval if retrieval is not None else self._mine
        # Same shape, same reason. The runtime hands over the registry's
        # ``lower_ceiling``, which is durable and survives eviction and restart
        # (AD-28). A gate built without one caps in memory only, per main, so a
        # standalone gate still caps — it just cannot promise durability, and
        # says so rather than pretending.
        self._ceilings: dict[str, Ceiling] = {}
        self._lower_ceiling = lower_ceiling
        # Who is in the mode. Volatile by AD-26 and deliberately so: the
        # *durable* half of entry is the ceiling, which is a governance
        # decision recorded in the log. Membership here is how the mode holds
        # across a conversation. A restart therefore re-detects rather than
        # remembering — and a restarted main is still capped at `behave`, which
        # is the quiet failure rather than the loud one.
        self._held: set[str] = set()
        # Raised by a third-party mention or a sudden behaviour change, and by
        # nothing else. Counts only: never content, never a belief (AD-22,
        # AD-26). Neither signal can enter the mode, alone or together — entry
        # reads ``ACTION_FOR`` and this dict is not in that path.
        self._vigilance: dict[str, int] = {}

    def _mine(self, main_id: str) -> RetrievalSwitch:
        return self._own.setdefault(main_id, RetrievalSwitch())

    async def handle(self, inbound: Inbound) -> str | None:
        """Assess, then either respond directly or delegate inward.

        Returns the reply text, or ``None`` for silence — which is a first-class
        outcome for an *ordinary* turn (AD-27) and never one for a crisis turn.
        """
        if self._is_crisis(inbound):
            # Suspended first, so retrieval is off and the cap is down before
            # any reply is composed — and before anything a later story adds
            # between these lines could run against a live ledger.
            self._suspend(inbound)
            reply = await self._respond_to_crisis(inbound)
            # Held last, so the *first* crisis turn is assessed on its own
            # signal and every turn after it resolves to the held plan.
            self._held.add(inbound.main_id)
            return reply

        assessment = self._assess(inbound)
        if assessment.action is Action.SURFACE:
            # Somebody other than the main. A resource the main can share, and
            # it stops here: the mode is not entered, no ceiling moves, and the
            # pipeline is not called — so no belief about that person is
            # written to any store.
            return respond.reply_for(assessment)
        return await self._pipeline(inbound)

    # -- the two seams --------------------------------------------------------

    def _is_crisis(self, inbound: Inbound) -> bool:
        """Whether this turn is handled as crisis.

        True while the mode is held, because nothing exits it, and otherwise
        exactly when the tier table says the signal enters (CAP-12). A
        vigilance-only tier cannot reach this branch: entry is a lookup in
        ``ACTION_FOR``, not a condition spelled out here.
        """
        if inbound.main_id in self._held:
            return True
        return self._assess(inbound).enters

    async def _respond_to_crisis(self, inbound: Inbound) -> str:
        """The reply, assembled from templates (CAP-12).

        The tier chooses a plan; the plan is a tuple of template lines. The
        main's text reaches nothing here — ``respond.reply_for`` takes the
        assessment — so no phrasing of a method request can produce method
        content, and no reply is ever empty.
        """
        return respond.reply_for(self._crisis_tier(inbound))

    # -- entering -------------------------------------------------------------

    def _assess(self, inbound: Inbound) -> Assessment:
        """The tier table's verdict on this message, and nothing else."""
        return assess(inbound.text)

    def _crisis_tier(self, inbound: Inbound) -> Assessment:
        """The assessment the reply is built from.

        A main already in the mode gets the held plan whatever this turn says —
        including a turn that reads as ordinary, and including one arguing that
        the mode should end. Re-running the opening plan every turn would
        thank them for telling Half something they told it an hour ago.
        """
        if inbound.main_id in self._held:
            return Assessment(Tier.HELD, Action.ENTER, scored=False)
        found = self._assess(inbound)
        if found.enters:
            return found
        # Reached when a subclass overrides ``_is_crisis`` — the seam the
        # runtime tests use. Treat it as the mode being open rather than
        # raising: an exception here would cost the main their reply.
        return Assessment(Tier.HELD, Action.ENTER, scored=False)

    def _suspend(self, inbound: Inbound) -> None:
        """Disable this main's retrieval and drop their ceiling to `behave`.

        Idempotent, and ordered: the switch is in memory and cannot fail, so it
        goes first. The ceiling append can fail — a full disk, a corrupt log —
        and a failure to persist a cap must never cost the main their reply,
        which is why it is caught here. The in-memory cap is kept either way,
        so the process stays capped even when the log did not take it.
        """
        self._retrieval(inbound.main_id).disable()
        self._cap(inbound)

    def _cap(self, inbound: Inbound) -> None:
        capped = self._ceilings.get(inbound.main_id, Ceiling()).lowered_to(
            CRISIS_CEILING
        )
        self._ceilings[inbound.main_id] = capped
        if self._lower_ceiling is None:
            return
        try:
            self._lower_ceiling(
                inbound.main_id,
                CRISIS_CEILING,
                t=inbound.t,
                because="crisis mode entered (CAP-12)",
            )
        except HalfError:
            # No content, and no message text (AD-22). Loud in the log because
            # a cap that did not persist is a main who comes back uncapped.
            logger.exception(
                "crisis ceiling did not persist for main=%s; capped in memory "
                "only", inbound.main_id
            )

    # -- vigilance ------------------------------------------------------------

    def raise_vigilance(self, main_id: str, tier: Tier) -> int:
        """Note a signal that raises vigilance and can never enter the mode.

        A third-party mention (a friend's message about the main) and a sudden
        change in pattern. **Never alone**, and here that is structural rather
        than remembered: this refuses any tier the table does not map to
        ``Action.VIGILANCE``, and it does not touch ``_held``, so there is no
        spelling of a call to this method that opens the mode.

        Returns the running count for this main. Counts only — no content, no
        belief, nothing durable (AD-22, AD-26).
        """
        if ACTION_FOR.get(tier) is not Action.VIGILANCE:
            raise CrisisError(
                f"{tier} is not a vigilance signal. A third-party mention and "
                "a behaviour change raise vigilance and never enter the mode; "
                "entering is decided by the tier table on the message itself"
            )
        count = self._vigilance.get(main_id, 0) + 1
        self._vigilance[main_id] = count
        return count

    def vigilance(self, main_id: str) -> int:
        """How many vigilance-raising signals this main has accumulated.

        Read by later stories — 6b's handoff and 6c's aftercare — and by
        nothing in the entry path, which is the point: vigilance informs how
        closely Half is watching, and never whether the mode opens.
        """
        return self._vigilance.get(main_id, 0)

    # -- introspection --------------------------------------------------------

    def in_crisis(self, main_id: str) -> bool:
        """Whether the mode is open for this main.

        There is deliberately no method that closes it. Mode *exit* is the
        companion's first open question — who decides it is over, and how the
        mirror comes back without feeling like surveillance resuming — and
        answering it with a timeout, a keyword or a quiet expiry would be
        answering a clinical question in code review.
        """
        return main_id in self._held
