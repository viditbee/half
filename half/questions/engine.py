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

**The question is delivered on the turn path, and that is not a detail** (review
loop 1). 5b's topic gate reads the actor's *live* strands — *"attach the
question to the next conversation that already touches the topic; never ping to
ask"* — and those exist only on a conversation turn. The first build gated on
them and delivered on the unprompted morning, where a dormant actor has none:
gating on a conversation and then broadcasting is a ping however the gate is
worded. So the caller is ``half.actor.runtime``, behind the crisis gate, and the
morning surface does not ask at all.

**A favour must have been delivered before the turn began**, which the turn path
gives structurally rather than by a check: nothing on this path writes a record
``half.trust.balance.delivered`` counts, so the balance this engine reads can
only contain favours that predate the turn. The first build spent *after* the
morning claimed the day — and story 10 claims a day by writing ``sent=True``,
which is exactly what earns — so every morning funded its own question and a
main with zero delivered favours was asked. CAP-4 says *preceded*.

**A favour is spent only when the question actually reaches the main.** This
module will refuse, gate and choose; whether the built text carries a question
line is the caller's own observation, and ``buy`` is called only once that is
true. The rule exists because ``may_be_raised`` permits `ask` **or above** while
the context builder emits a ``Question`` only at exactly `ask` and drops any item
whose topic echoes its claim (AD-18) — so a bought belief can be perfectly
permitted and still produce no line. Spending for it wrote a phantom ``asked``
record, which then suppressed the real question for one of the wanting's own
periods.

**Exactly one question leaves this module, ever.** ``offer`` returns an ``Ask``
or nothing and there is no plural door out of this class onto an asking path;
what a caller may hand the context builder is one belief id, because that is all
``half.context.build.build`` will take (CAP-4 forbids a questionnaire outright).

**Nothing here composes a sentence and nothing here sends.** There is no text on
any value in this module, no template in any language, and no channel reachable
from it. What a question *says* is composed at delivery and is never durable
(AD-22).

**Nothing here opens a store.** Two narrow doors, injected: 5b's own
``TrustLedger`` — **unchanged, still exactly three methods** — plus one read that
folds the trust view and the answer state out of a single pass over one log, so
there is no window between them for an append to land in. The conversation is
passed in by the caller that holds it, so this module needs no door onto volatile
state at all.

Pure of clocks and of the network: ``now`` and ``t`` are stamps the caller was
handed, no gate here is a function of time except the re-ask bound, and that one
takes its instant as an argument (AD-30).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from half.questions.answered import Answer, Reask, reaskable
from half.questions.mint import minted
from half.retrieval.strands import Strands
from half.trust.stakes import stakes
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
    "ASK_OUTCOMES", "NOTHING_OFFERED", "Purchase", "QuestionEngine",
    "QuestionLedger", "QuestionView", "offered",
]

#: What ``buy`` reports when it was handed nothing to buy. Deliberately **not**
#: inside ``ASK_OUTCOMES``: that set is what a *spend* came back as, and no spend
#: was attempted here. A caller branching on the two together would read *"there
#: was no question"* as a refusal by the gates, which are different facts with
#: different remedies — and only one of them is worth a log line.
NOTHING_OFFERED: Final[str] = "nothing-offered"


@dataclass(frozen=True, slots=True)
class QuestionView:
    """One main's state, as one pass over one log leaves it.

    Two folds, one read. They are carried together because they are read
    together and must describe one moment: the balance says whether a question
    can be paid for and the answer state says whether it may be put again, and a
    build that read them under two separate acquires could answer *"affordable"*
    about one instant and *"never asked"* about another.
    """

    trust: TrustView = field(default_factory=TrustView)
    #: What the log says about every question Half has put — folded, never
    #: stored (AD-3, AD-30). See ``half.questions.answered``.
    answers: Mapping[str, Answer] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Purchase:
    """What trying to buy a question came back as.

    ``outcome`` is one of ``ASK_OUTCOMES`` when a spend was attempted, and
    ``NOTHING_OFFERED`` when there was nothing to attempt. ``question`` is set
    exactly when ``outcome`` is ``ASK_RECORDED``, so a caller cannot reach a
    question id on a path where no favour was spent.
    """

    outcome: str = NOTHING_OFFERED
    question: Unasked | None = None

    @property
    def spent(self) -> bool:
        return self.outcome == ASK_RECORDED and self.question is not None


class QuestionLedger(TrustLedger, Protocol):
    """The four doors this composition needs into one main's state.

    ``TrustLedger``'s three, **unchanged and not re-declared** — the mode, the
    narrowed trust view, and the serialized spend — plus one of this story's
    own. Extending by inheritance rather than by editing 5b's protocol is
    deliberate: 5b's door stays exactly the three methods it was reviewed with,
    and ``half.trust`` neither knows nor can reach what is added here.

    ``question_view`` is one read of the log folded two ways. It replaced a pair
    of separate doors after review: reading the trust view under one acquire and
    the answer state under another left a window an append could land in, and
    the two would then describe different moments.

    There is deliberately **no door onto the live conversation.** The strands the
    topic gate reads are volatile (AD-26) and belong to whoever is holding the
    turn; that caller passes them in. A door here would be a second thing that
    could reach a main's in-memory state, and the only caller that has any is the
    one that just moved them.
    """

    async def question_view(self, main_id: str) -> QuestionView:
        ...


def offered(
    beliefs: Iterable[object] | None,
    *,
    view: QuestionView,
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
    held = view if isinstance(view, QuestionView) else QuestionView()
    trust = held.trust if isinstance(held.trust, TrustView) else TrustView()
    loops = trust.loop_table()
    table: Mapping[str, Answer] = (
        held.answers if isinstance(held.answers, Mapping) else {}
    )
    kept: list[Unasked] = []
    for question in minted(beliefs):
        weighed = stakes(trust.beliefs.get(question.about), loops=loops)
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
        self,
        main_id: str,
        *,
        beliefs: Sequence[object],
        live: Strands | None,
        now: str,
    ) -> Ask | None:
        """The one question worth asking about ``beliefs``, or ``None``.

        ``None`` is the ordinary answer and carries no reason, because there is
        usually nothing to explain: most turns touch no belief the ladder raises
        to `ask`, most such beliefs are below the stakes bar, and most of the
        rest are waiting on a topic nobody raised or a favour nobody earned. None
        of that is a failure (AD-27).

        **Writes nothing.** A question that is offered — and one that is offered
        and then refused at the spend — leaves the balance exactly as it was.

        ``beliefs`` is the set the caller is going to speak from, so a question
        can only ever be about something already in the ranked material the
        context is built from. A question about a belief the context does not
        carry could not reach a channel anyway, and offering one would be a
        favour spent on nothing.

        ``live`` is the conversation as the caller holds it, because the strands
        are volatile and this module has no door onto them. ``None`` is a caller
        with no conversation to attach a question to, and every question is then
        correctly held — which is what *"never ping to ask"* means.

        **Two reads, and only one of them is this module's.** The view is one
        pass over one log; the second is ``UnaskedQueue.next_ask``'s own, which
        is 5b's door and re-runs every gate. A window exists between them and is
        harmless: the spend re-checks everything a third time, under the main's
        own mutex, and every gate resolves toward asking less.
        """
        view = await self.ledger.question_view(main_id)
        fresh = offered(beliefs, view=view, now=now)
        if not fresh:
            return None
        return await self.queue.next_ask(main_id, questions=fresh, live=live)

    async def buy(
        self, main_id: str, *, t: str, ask: Ask | None, live: Strands | None
    ) -> Purchase:
        """Spend one favour on ``ask``, or report why not. Never raises.

        **Called only once the caller's built text actually carries the question
        line, and immediately before that text reaches the main.** Both halves
        matter. A question that was bought and never rendered — a belief the
        ladder raised *above* `ask`, or one whose topic echoes its own claim —
        used to spend the favour and write an ``asked`` record for a question
        nobody was asked, which then suppressed the real one for a year. And the
        spend sits before the send because the alternative lets two runs both
        find the favour unspent and both ask; the cost of this order is the
        asymmetry story 10 accepted, where a send that fails still costs the
        favour.

        Every gate runs again inside ``spend``, against a view read at this
        moment, and the registry re-asserts the mode, the balance and the ladder
        under this main's mutex. An ``Ask`` carries no authority — a caller can
        build one — so nothing here trusts the value it is handed.

        Never raises. The caller is composing a reply to the main's own message,
        and losing that reply over a question is strictly worse than sending it
        without one. A failure is reported as a refusal, which is what it is from
        the main's side: nothing was asked.
        """
        if not isinstance(ask, Ask) or not isinstance(ask.question, Unasked):
            return Purchase()
        try:
            outcome = await self.queue.spend(
                main_id, t=t, ask=ask, live=live
            )
        except Exception:  # noqa: BLE001 - the question, never the turn
            # The *type* is not even logged here: the caller owns this main's
            # log line and an exception message quotes the value that caused it,
            # which here is a record out of a main's own ledger (AD-22).
            return Purchase(outcome=ASK_REFUSED)
        if outcome != ASK_RECORDED:
            return Purchase(outcome=outcome)
        return Purchase(outcome=outcome, question=ask.question)
