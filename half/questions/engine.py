"""The composition: mint, bound the re-ask, gate through 5b, spend (CAP-4).

This is the production caller story 5b did not have. It puts the pieces in one
order and adds no rule of its own beyond the re-ask bound:

1. **Mint.** One ``Unasked`` per belief the caller offers, its id derived from
   the belief id (``half.questions.mint``).
2. **Bound the re-ask.** Drop the questions that were already put and are inside
   one of their own wanting's periods, and the ones the main responded to
   (``half.questions.answered``). This is a filter on *which questions exist for
   this turn*, applied before any gate — not a sixth gate, not a reordering of
   the five, and nothing in ``half.trust`` is touched by it.
3. **Gate.** Every gate 5b established, in 5b's order, through 5b's own door:
   ``UnaskedQueue.next_ask`` runs the stakes bar, the ladder under this main's
   ceiling, the topic, and the favour, and returns **one** question — the
   costliest mistake — or none.
4. **Spend.** ``UnaskedQueue.spend`` re-runs every gate against a view read now
   and the registry re-asserts the mode, the balance and the ladder under this
   main's own mutex. A question that no longer passes is refused rather than
   paid for.

**Exactly one question leaves this module, ever.** ``offer`` returns an ``Ask``
or nothing and there is no plural door out of this class onto an asking path;
what a caller may hand the context builder is one belief id, because that is all
``half.context.build.build`` will take (CAP-4 forbids a questionnaire outright).

**Nothing here composes a sentence and nothing here sends.** There is no text on
any value in this module, no template in any language, and no channel reachable
from it. What a question *says* is composed at delivery and is never durable
(AD-22).

**Nothing here opens a store.** Five narrow doors, injected — 5b's three, plus
the live conversation and the ask history — because a second path to a main's
log is a second writer (AD-1). ``live_strands`` and ``ask_history`` are doors on
*this* protocol rather than additions to ``TrustLedger``: 5b's door is unchanged
and still has exactly the three methods it was reviewed with.

**Why the engine reads the conversation and the surface does not.** The topic
gate is 5b's — *"attach the question to the next conversation that already
touches the topic; never ping to ask"* — and it reads the actor's live strands,
which are volatile (AD-26) and never in the fold. The morning surface must not
hold them: it is handed a ``SurfaceView`` precisely so that a field it should not
consult is an ``AttributeError`` rather than a line a scan has to be clever
enough to see. So the surface holds an *engine* and the engine holds the door,
and the strands never reach the module that decides what to say.

Pure of clocks and of the network: ``now`` and ``t`` are stamps the caller was
handed, no gate here is a function of time except the re-ask bound, and that one
takes its instant as an argument (AD-30).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from half.questions.answered import Answer, Reask, reaskable
from half.questions.mint import minted
from half.retrieval.strands import Strands
from half.trust.stakes import Stakes, stakes
from half.trust.unasked import (
    ASK_OUTCOMES,
    ASK_RECORDED,
    ASK_REFUSED,
    Ask,
    TrustLedger,
    TrustView,
    Unasked,
    UnaskedQueue,
)

__all__ = [
    "ASK_OUTCOMES", "Bought", "NOTHING_OFFERED", "Purchase", "QuestionEngine",
    "QuestionLedger", "offered",
]

#: What ``buy`` reports when it was handed nothing to buy. Inside
#: ``ASK_OUTCOMES``? Deliberately **not** — that set is what a *spend* came back
#: as, and no spend was attempted here. A caller branching on the two sets
#: together would read *"there was no question"* as a refusal by the gates,
#: which are different facts with different remedies (and only one of them is
#: worth a log line).
NOTHING_OFFERED: Final[str] = "nothing-offered"


@dataclass(frozen=True, slots=True)
class Bought:
    """One question a favour has actually been spent on.

    The value a caller hands the context builder, and it exists so that *"a
    question reaches the context only by being handed in"* has something to hand
    in that cannot be confused with a proposal. An ``Ask`` is a proposal — 5b
    says so, and review built one by hand and watched it burn a favour — and the
    difference between the two types is the spend that happened between them.

    Carries no text, for the reason ``Unasked`` carries none.
    """

    question: Unasked
    stakes: Stakes

    @property
    def about(self) -> str:
        """The belief id the favour paid for. What ``build`` is handed."""
        return self.question.about


@dataclass(frozen=True, slots=True)
class Purchase:
    """What trying to buy a question came back as.

    ``outcome`` is one of ``ASK_OUTCOMES`` when a spend was attempted, and
    ``NOTHING_OFFERED`` when there was nothing to attempt. ``bought`` is set
    exactly when ``outcome`` is ``ASK_RECORDED``, so a caller cannot reach a
    question id on a path where no favour was spent.
    """

    outcome: str = NOTHING_OFFERED
    bought: Bought | None = None

    @property
    def about(self) -> str:
        """The belief a favour paid for, or ``""``. Safe on every path."""
        return self.bought.about if self.bought is not None else ""

    @property
    def spent(self) -> bool:
        return self.outcome == ASK_RECORDED and self.bought is not None


class QuestionLedger(TrustLedger, Protocol):
    """The five doors this composition needs into one main's state.

    ``TrustLedger``'s three, **unchanged and not re-declared** — the mode, the
    narrowed trust view, and the serialized spend — plus two of this story's
    own. Extending by inheritance rather than by editing 5b's protocol is
    deliberate: 5b's door stays exactly the three methods it was reviewed with,
    and ``half.trust`` neither knows nor can reach what is added here.

    ``live_strands`` is the conversation as it stands right now — volatile
    (AD-26), never in the fold, and the only input the topic gate has. It is
    synchronous and returns a value or ``None``; ``None`` is a caller with no
    conversation to attach a question to, and every question is then correctly
    held.

    ``ask_history`` is folded from the log by ``half.questions.answered`` and
    holds no stored state: the registry reads the records under this main's own
    mutex and folds them, exactly as it folds the balance.
    """

    def live_strands(self, main_id: str) -> Strands | None:
        ...

    async def ask_history(self, main_id: str) -> Mapping[str, Answer]:
        ...


def offered(
    beliefs: Iterable[object] | None,
    *,
    view: TrustView,
    answers: Mapping[str, Answer] | None,
    now: object,
) -> tuple[Unasked, ...]:
    """The questions that are not inside their own wanting's period. Pure.

    The re-ask bound, applied to a whole candidate set and nothing else. It runs
    **before** 5b's gates rather than among them, because it answers a different
    question: 5b decides whether a question may be asked *at all* and *now*, and
    this decides whether asking it again would be a nag. Folding it into
    ``considered`` would be a sixth gate, which this story does not add.

    The period is each belief's own wanting's, taken from the ``Stakes`` value —
    ``cost_days``, which is ``PERIOD_DAYS`` subscripted by that loop's timescale.
    Read from there rather than derived a second time: ``stakes`` is pure, so
    calling it here and again inside ``considered`` is one function giving one
    answer, where a second derivation would be a second place for two builds to
    disagree about one loop.

    Total and never raises: a question this build cannot weigh keeps whatever
    ``reaskable`` says about it, and a malformed value is refused by the gates
    below rather than by an exception on a turn's own path.
    """
    loops = view.loop_table() if isinstance(view, TrustView) else {}
    table: Mapping[str, Answer] = answers if isinstance(answers, Mapping) else {}
    kept: list[Unasked] = []
    for question in minted(beliefs):
        belief = view.beliefs.get(question.about) if isinstance(view, TrustView) else None
        weighed = stakes(belief, loops=loops)
        bound: Reask = reaskable(
            table.get(question.id), period_days=weighed.cost_days, now=now
        )
        if bound.may_ask:
            kept.append(question)
    return tuple(kept)


@dataclass(frozen=True, slots=True)
class QuestionEngine:
    """One main, at most one question, and the favour that paid for it.

    Holds the ledger and nothing else. The queue is built from it rather than
    stored beside it so there is one object that can reach a main's log and it
    is the injected one.
    """

    ledger: QuestionLedger

    @property
    def queue(self) -> UnaskedQueue:
        """5b's own composition, over 5b's own door. Not re-implemented."""
        return UnaskedQueue(ledger=self.ledger)

    async def offer(
        self, main_id: str, *, beliefs: Sequence[object], now: str
    ) -> Ask | None:
        """The one question worth asking about ``beliefs``, or ``None``.

        ``None`` is the ordinary answer and carries no reason, because there is
        usually nothing to explain: most mornings touch no belief the ladder
        raises to `ask`, most such beliefs are below the stakes bar, and most of
        the rest are waiting on a topic nobody raised or a favour nobody earned.
        None of that is a failure (AD-27).

        **Writes nothing.** A question that is offered — and one that is offered
        and then refused at the spend — leaves the balance exactly as it was.

        ``beliefs`` is the set the caller is going to speak from, so a question
        can only ever be about something already in the ranked material the
        context is built from. A question about a belief the context does not
        carry could not reach a channel anyway, and offering one would be a
        favour spent on nothing.
        """
        view = await self.ledger.trust_view(main_id)
        answers = await self.ledger.ask_history(main_id)
        fresh = offered(beliefs, view=view, answers=answers, now=now)
        if not fresh:
            return None
        return await self.queue.next_ask(
            main_id, questions=fresh, live=self.ledger.live_strands(main_id)
        )

    async def buy(self, main_id: str, *, t: str, ask: Ask | None) -> Purchase:
        """Spend one favour on ``ask``, or report why not. Never raises.

        **Called immediately before the question reaches the main, and after the
        day is claimed** — 5b's spend contract and story 10's claim-then-send
        order. The alternative, sending and then recording, lets two overlapping
        runs both find the favour unspent and both ask. The cost of this order is
        story 10's own accepted asymmetry: a question that fails to reach the
        main costs one favour.

        Every gate runs again inside ``spend``, against a view read at this
        moment, and the registry re-asserts the mode, the balance and the ladder
        under this main's mutex. An ``Ask`` carries no authority — a caller can
        build one — so nothing here trusts the value it is handed.

        Never raises, because the caller is on a path where the day has already
        been claimed: losing the whole morning over a question is strictly worse
        than sending it without one. A failure is reported as a refusal, which
        is what it is from the main's side — nothing was asked.
        """
        if not isinstance(ask, Ask) or not isinstance(ask.question, Unasked):
            return Purchase()
        try:
            outcome = await self.queue.spend(
                main_id, t=t, ask=ask, live=self.ledger.live_strands(main_id)
            )
        except Exception:  # noqa: BLE001 - the question, never the morning
            # The *type* is not even logged here: the caller owns this main's
            # log line and an exception message quotes the value that caused it,
            # which here is a record out of a main's own ledger (AD-22).
            return Purchase(outcome=ASK_REFUSED)
        if outcome != ASK_RECORDED:
            return Purchase(outcome=outcome)
        return Purchase(
            outcome=outcome,
            bought=Bought(question=ask.question, stakes=ask.stakes),
        )
