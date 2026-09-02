"""The unasked queue: two gates, in order, and what spending looks like.

CAP-4, CAP-10, AD-3, AD-22, AD-28, AD-30. Clarifying questions Half is holding,
and the rule that decides whether one of them may be asked now.

**Nothing here asks anything.** This module holds questions and decides whether
one *may* be asked; composing a sentence and putting it in front of the main is
story 11, and CAP-4 forbids a questionnaire outright. There is no text on any
value in this file and no channel reachable from it — what a question *says* is
not a fact this layer holds, and it is never durable (AD-22).

**The two gates run in this order and the order is the rule.**

1. **Stakes** — is this question worth its interruption at all? Measured in
   ``half.trust.stakes``, from the period of the wanting the belief sits on
   against the cost of one interruption. A question below the bar is not
   deferred; it is *not worth asking*, and no balance changes that.
2. **The favour** — may it be asked *now*? *"Half never asks without having
   just given"* (glossary), and the favour is spent by the asking, so the same
   favour cannot buy two questions.

Reversed, a large balance buys a worthless question, which is the failure the
glossary names when it says an unspent balance is a defect *rather than
something to spend for its own sake*. The order is structural as well as
written down: ``stakes`` is not given a balance and cannot consult one, and
``considered`` returns before it looks at the currency.

**Two rules run between them, and neither is re-implemented here.** The ladder
decides what may be said at all — a quarantined belief is `behave` and a
question about it is not askable — and AD-28's ceiling caps it, both through
the one call to ``ladder.permitted``. There is no branch in this file for
quarantine and none for aftercare: a main capped at `behave` has every belief
resolve to `behave`, so nothing reaches `ask`, and that is the whole of *"the
ceiling holds, without a special case for the ceiling"*.

**A question is attached lazily**, never raised cold. The constitution's rule
is *"attach the question to the next conversation that already touches the
topic. Never ping to ask."* So the topic gate reads the actor's live strands —
what the conversation is about right now — and a question whose subject nobody
has mentioned is **held**, not discarded. That is not AD-24's excluded
retrieval wearing a different hat: nothing is made unreachable, no belief drops
out of any candidate set, and the question stays in the queue with a reason.
What is withheld is Half's own interruption, which is the thing AD-24 has no
opinion about.

**Held is not refused, and the queue says which.** ``Verdict.held`` is true for
the two reasons that are *not yet* — the topic has not come up, the balance is
spent — and false for the ones that are *not at all*. Queue depth is itself a
signal (glossary), so ``queue`` returns what is being held rather than a count
somebody has to derive.

**Spending is one serialized operation, and it happens before the asking.**
``ActorRegistry.note_ask`` re-reads the balance under the main's own mutex and
appends the spend, exactly as ``claim_day`` re-reads the day marker and appends
the day (story 10). Two overlapping turns therefore cannot both spend one
favour — which a read here followed by an append there would allow, and which
no single-threaded test would ever see. The caller asks only after the spend
lands, which makes the asymmetry the same one story 10 accepted: a question
that fails to reach the main costs one favour, where the alternative costs the
rule.

Nothing in this module writes: the pure half returns values, and ``UnaskedQueue``
reaches the log through the registry's own narrow door (AD-1, AD-3). No clock,
no network, no model — none of the gates is a function of time at all, so a
verdict changes only when the log or the conversation does (AD-30).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields as dataclass_fields
from typing import Any, Final, Protocol

from half.context.build import resolve
from half.governance.ladder import Ceiling, License, height
from half.loops.ledger import Loop
from half.loops.ledger import read as read_loops
from half.retrieval.strands import Strands, strands_of
from half.store.fold import State
from half.trust.balance import Balance
from half.trust.stakes import NO_SUBJECT
from half.trust.stakes import REASONS as STAKE_REASONS
from half.trust.stakes import Stakes, stakes

__all__ = [
    "ASK_CRISIS", "ASK_OUTCOMES", "ASK_RECORDED", "ASK_UNAFFORDABLE", "Ask",
    "HELD", "NOT_PERMITTED", "NO_FAVOUR", "REASONS", "TOPIC_UNRAISED",
    "TrustLedger", "TrustView", "Unasked", "UnaskedQueue", "VISIBLE",
    "Verdict", "asks_at", "considered", "narrowed_for_trust", "on_topic",
    "queue", "view_fields",
]

#: The weakest rung a question may be raised from.
#:
#: `ask` is, by the ladder's own definition, *"Half may raise it as a
#: question"* — so the rung this gate wants is not a policy choice but the name
#: of the thing being asked for. `behave` is where Half acts silently, and a
#: question is the opposite of silent. Derived from the ladder rather than
#: written as a literal, for the reason ``half.surface.morning.SPEAKS_AT`` is.
ASKS_AT: Final[License] = License.ASK

#: The ladder does not permit raising this belief as a question — because it is
#: quarantined, because the main's ceiling caps it, or because its own license
#: sits below `ask`. **Not this story's decision**, and there is no branch here
#: that distinguishes the three: ``ladder.permitted`` answers all of them, and
#: a second opinion about which is a second place for them to disagree.
NOT_PERMITTED: Final[str] = "not-permitted"
#: The main has not touched this question's subject. **Held**, not refused: the
#: question is attached lazily to a conversation that already covers it, and
#: Half never pings to ask.
TOPIC_UNRAISED: Final[str] = "topic-unraised"
#: Half has not given, or has already spent what it was given. **Held**: the
#: question is worth asking and cannot be paid for yet.
NO_FAVOUR: Final[str] = "no-favour"

#: Every reason a question is not asked. **Derived as a union rather than
#: relisted**, so a reason added to the stakes vocabulary is inside this set on
#: the day it is written rather than on the day somebody remembers this file.
#: Closed for the reason ``choose.REASONS`` and ``morning.REASONS`` are: a
#: caller counting refusals counts constants and never a message, because an
#: exception message quotes the value that caused it and here that is a record
#: out of a main's own ledger (AD-22).
REASONS: Final[frozenset[str]] = STAKE_REASONS | frozenset(
    {NOT_PERMITTED, TOPIC_UNRAISED, NO_FAVOUR}
)

#: The reasons that mean *not yet* rather than *not at all*.
#:
#: The distinction the matrix draws between *held* and *not askable*, as a set
#: read by the runtime **and** by the tests rather than as a comparison each
#: writes out. A question below the bar on stakes is not in here: the story is
#: explicit that it *"is not merely deferred, it is not worth asking at all"*,
#: and putting it in a held queue would be exactly the accumulation the
#: glossary calls a defect.
HELD: Final[frozenset[str]] = frozenset({TOPIC_UNRAISED, NO_FAVOUR})

#: What recording a spend came back as. The vocabulary lives here, between the
#: actor and this module, because both sides need it and only one may own the
#: spelling — the same reason ``half.surface.view`` owns ``CLAIM_OUTCOMES``. It
#: is a closed set for the reason that one is: the caller branches on the
#: answer, and a fourth value nobody recognised would fall through as *spent*.
ASK_RECORDED: Final[str] = "asked"
ASK_CRISIS: Final[str] = "crisis"
ASK_UNAFFORDABLE: Final[str] = "unaffordable"
ASK_OUTCOMES: Final[frozenset[str]] = frozenset(
    {ASK_RECORDED, ASK_CRISIS, ASK_UNAFFORDABLE}
)


@dataclass(frozen=True, slots=True)
class Unasked:
    """One clarifying question Half is holding.

    A value, and deliberately a thin one. It carries an opaque ``id`` and the
    belief whose ambiguity it would resolve — **and no text**, no rank, no
    score and no stakes. What it would say is composed at delivery (story 11);
    what it is worth is computed from the log by ``half.trust.stakes``, so that
    two builds reading one log weigh one question identically.

    Named ``Unasked`` rather than ``Question`` on purpose:
    ``half.context.channels.Question`` is a rendered line in a built context,
    which is the one thing this is not.
    """

    id: str
    about: str

    @property
    def nameable(self) -> bool:
        """Whether this question can be recorded at all.

        The predicate, read by the runtime **and** by the tests, rather than a
        pair of emptiness checks each writes out. A question with no id cannot
        be spent against and a question about nothing cannot be weighed, and
        both are refused before either gate runs.
        """
        return bool(
            isinstance(self.id, str) and self.id.strip()
            and isinstance(self.about, str) and self.about.strip()
        )


@dataclass(frozen=True, slots=True)
class Verdict:
    """Whether one question may be asked now, and why not.

    A value. It decides nothing and writes nothing; it is recomputed from the
    fold, the balance and the live conversation every time it is wanted, for
    the reason ``Bound`` and ``Silence`` are recomputed.

    ``reason`` is set exactly when ``askable`` is false and is one of
    ``REASONS``. ``stakes`` is carried whenever it was computed, so a caller
    can show *what* being wrong would have cost rather than restate the verdict.
    """

    question: Unasked
    askable: bool = False
    reason: str | None = None
    stakes: Stakes | None = None

    @property
    def held(self) -> bool:
        """Whether this question stays in the queue rather than leaving it.

        *Not yet* — the topic has not come up, or nothing has been given —
        against *not at all*. Queue depth is a signal, and a queue that also
        accumulated questions nobody will ever ask is not one.
        """
        return self.reason in HELD


@dataclass(frozen=True, slots=True)
class Ask:
    """One question that may be asked now. The unit of the ordering.

    Produced only by ``asks_at``, and only for a question that has passed every
    gate *and* has a favour to pay for it — so holding one of these is holding
    a permission, which is why there is no constructor path to it that skips a
    gate.
    """

    question: Unasked
    stakes: Stakes

    @property
    def order(self) -> tuple[int, str]:
        """The total order two builds must agree on.

        The costlier mistake first — the wanting whose period is longest, so a
        question about farmland outranks one about a weekly swim — then the
        question's own id, which is unique, so the order is total and no tie is
        broken by dict iteration or by a float that happens to land equal.

        Integers, never floats: ``cost_days`` comes out of ``PERIOD_DAYS`` and
        is a whole number of days, so two builds cannot disagree about a
        comparison the way they can about a ratio.
        """
        return (-(self.stakes.cost_days or 0), self.question.id)


# -- what the queue is allowed to see -----------------------------------------


#: The fields of ``State`` the unasked queue may consult. An allowlist, spelled
#: once and read by ``narrowed_for_trust`` **and** by ``tests/test_unasked.py``,
#: so a new field on ``State`` is invisible here until somebody adds it on
#: purpose.
#:
#: **This is story 10's lesson applied a second time.** The morning surface was
#: handed ``State`` entire, and review found that ``if state.aftercare is not
#: None: return Silence(...)`` passed the whole suite while permanently
#: silencing a main — per-feature suppression, one line, invisible to every
#: scan. The same line here would be a main who is never asked anything again.
#: So ``crisis``, ``aftercare``, ``schedule``, ``spoke`` and ``touches`` are not
#: merely unread: they are absent, and reaching for one is an ``AttributeError``.
#:
#: ``crisis`` is absent even though the mode suspends this: ``UnaskedQueue``
#: asks that through its own narrowed door, which answers a boolean, so there
#: is no record to branch on.
VISIBLE: Final[tuple[str, ...]] = ("beliefs", "loops")


@dataclass(frozen=True, slots=True)
class TrustView:
    """One main's state, narrowed to what the unasked queue may consult.

    Frozen, so a caller cannot write into what it was handed and cannot pass a
    mutated copy to the next rule.
    """

    #: The claims a question could be about. Not narrowed by field: the whole
    #: job here is to decide whether a claim may be raised, so narrowing the
    #: claim away would leave nothing to decide.
    beliefs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: The open loops — what a wrong belief would be wrong *about*, and the
    #: only source of the period the stakes rule measures against.
    loops: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: This main's global cap (AD-28). A rung and nothing else: the queue may
    #: know what may be raised, and may not know why. There is deliberately no
    #: field here from which the reason could be inferred.
    ceiling: Ceiling = field(default_factory=Ceiling)
    #: The currency, as the log stands. Recomputed with the view rather than
    #: cached beside it — see ``half.trust.balance``.
    balance: Balance = field(default_factory=Balance)

    def loop_table(self) -> dict[str, Loop]:
        """The folded loops as ``Loop`` values — the same reading
        ``half.surface.choose`` uses, so the two rules that decide whether Half
        opens its mouth read one ledger rather than two parsers."""
        return read_loops(self.loops)


def narrowed_for_trust(
    state: State, ceiling: Ceiling, *, balance: Balance
) -> TrustView:
    """``state`` reduced to what the queue may consult.

    Copies rather than references, so a view handed out cannot change under its
    reader while the actor keeps working.

    ``balance`` is passed in rather than computed here because it is a fold over
    the **log**, not over ``state`` — that is the whole of AD-30 for this story,
    and a version of this function that derived it from ``state`` would be the
    counter this design exists to avoid.
    """
    return TrustView(
        beliefs={k: dict(v) for k, v in state.beliefs.items()},
        loops={k: dict(v) for k, v in state.loops.items()},
        ceiling=ceiling,
        balance=balance,
    )


def view_fields() -> tuple[str, ...]:
    """The view's own field names. Read by the test that pins the allowlist."""
    return tuple(f.name for f in dataclass_fields(TrustView))


# -- the gates ----------------------------------------------------------------


def on_topic(belief: Mapping[str, Any] | None, live: Strands | None) -> bool:
    """Whether the conversation already touches what this question is about.

    *"Attach the question to the next conversation that already touches the
    topic. Never ping to ask."* The strands are the actor's live weights — how
    the main is right now, which is volatile by AD-26 and never in the fold —
    so they are passed in rather than carried on the view.

    ``live=None`` means there is no conversation: the nightly pass, the morning
    surface, a scheduler tick. Nothing is on topic then, and every question is
    held, which is the correct reading of *never ping to ask*.

    **This is not AD-24 exclusion.** Nothing is made unreachable and no belief
    leaves any candidate set; the question stays in the queue with a reason,
    and what is withheld is Half's own interruption.
    """
    if not isinstance(belief, Mapping) or live is None:
        return False
    return live.match(strands_of(belief)) > 0.0


def considered(
    question: Unasked, *, view: TrustView, live: Strands | None
) -> Verdict:
    """Whether ``question`` may be asked now. Pure, total, and never raises.

    The gates, in the order that is the rule:

    1. the question can be named at all, and names a belief the log holds;
    2. **stakes** — worth its interruption, or not worth asking at all;
    3. the **ladder**, under this main's ceiling — quarantine and AD-28, asked
       once, with no branch here for either;
    4. the **topic** — raised by the main, or held;
    5. the **favour** — given and unspent, or held.

    Stakes are asked before the currency, and cannot be asked after it: this
    function returns on a stakes refusal, and ``stakes`` is not given a balance
    to consult. Reversed, a large balance would buy a worthless question.

    Never raises, on the same terms as ``choose.eligible``: the caller is on a
    turn's own path, and losing the main's reply over a malformed loop entry is
    worse than losing one question — and there is a correct answer for *"we
    could not tell"*, which is not to ask.
    """
    if not isinstance(question, Unasked) or not question.nameable:
        # ``NO_SUBJECT`` is the stakes vocabulary's own word for *"there is
        # nothing here to be wrong about"*, imported rather than respelled: a
        # question naming no belief and a question about a belief the log does
        # not hold must give one answer, and two spellings of it is how a
        # caller counting refusals counts two different things.
        return Verdict(question=question, reason=NO_SUBJECT)

    belief = view.beliefs.get(question.about.strip())
    weighed = stakes(belief, loops=view.loop_table())
    if not weighed.worth_asking:
        # Not deferred. A question that is not worth its interruption is not
        # worth asking whatever the balance is, and it does not enter the held
        # queue — see ``HELD``.
        return Verdict(question=question, reason=weighed.reason, stakes=weighed)

    # The ladder, under the ceiling — asked through ``half.context.build.resolve``,
    # which is *the* door and not one of several. Story 4b made that function the
    # single place a license becomes a decision, and ``tests/test_ladder.py``
    # fails the build if any module outside ``half/governance/`` reaches past it
    # into the rule set; calling ``ladder.permitted`` here would have been a
    # second reader of the same field, with AD-28's ceiling capping only one of
    # them. One call answers quarantine, the belief's own rung and the cap
    # together, which is why there is no special case here for any of the three
    # — and why a main capped at `behave` is asked nothing without this module
    # being able to know that they are in aftercare.
    if height(resolve(belief, ceiling=view.ceiling)) < height(ASKS_AT):
        return Verdict(question=question, reason=NOT_PERMITTED, stakes=weighed)

    if not on_topic(belief, live):
        return Verdict(question=question, reason=TOPIC_UNRAISED, stakes=weighed)

    if not view.balance.spendable:
        return Verdict(question=question, reason=NO_FAVOUR, stakes=weighed)

    return Verdict(question=question, askable=True, stakes=weighed)


def queue(
    questions: Iterable[Unasked] | None, *, view: TrustView, live: Strands | None
) -> tuple[Verdict, ...]:
    """Every question that is still being held, with its reason.

    **Queue depth is itself a signal** (glossary), so this returns the held
    verdicts rather than a number: an operator asking *why* is holding the
    answer, and *"eleven questions, all of them waiting on a favour"* and
    *"eleven questions, none of their topics ever raised"* are different
    situations that a count cannot tell apart.

    A question that is askable right now is not *held* — it is ready — so it is
    not in here. Nor is one that failed on stakes or on the ladder: those have
    left the queue, which is what stops it accumulating things nobody will ever
    ask.
    """
    return tuple(
        verdict
        for verdict in (
            considered(question, view=view, live=live)
            for question in questions or ()
        )
        if verdict.held
    )


def asks_at(
    questions: Iterable[Unasked] | None, *, view: TrustView, live: Strands | None
) -> tuple[Ask, ...]:
    """Every question the balance can pay for right now, costliest first.

    **The favour is spent by the asking, so one favour buys one question**, and
    this is where that is true of a *set* rather than of one element: the
    ordered list is cut to what the balance holds. Two questions that both pass
    every gate against one delivered favour produce exactly one ``Ask``.

    The cut is a slice of an ordered list rather than a running counter, which
    is deliberate at the smallest scale this story works at: there is no
    variable here that a second loop could decrement twice.

    The bound is applied here rather than in the caller, so *"the ranking sees
    only what may be asked"* is true of the whole list — the same correction
    ``choose.eligible`` carries. Ranking first and cutting afterwards would
    produce a queue that goes quiet whenever its best question is unaffordable.
    """
    ready = [
        Ask(question=verdict.question, stakes=verdict.stakes)
        for verdict in (
            considered(question, view=view, live=live)
            for question in questions or ()
        )
        if verdict.askable and verdict.stakes is not None
    ]
    ordered = sorted(ready, key=lambda ask: ask.order)
    # Deduplicated on the question's id, so a producer that emitted the same
    # question twice cannot make one favour look like it bought two.
    seen: set[str] = set()
    unique: list[Ask] = []
    for ask in ordered:
        if ask.question.id in seen:
            continue
        seen.add(ask.question.id)
        unique.append(ask)
    return tuple(unique[: view.balance.unspent])


# -- the composition: crisis, the view, and the spend -------------------------


class TrustLedger(Protocol):
    """The three doors the unasked queue needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry`` for the reason
    ``SurfaceLedger`` is one: this is the whole dependency — one narrowed read,
    one boolean, and one serialized check-and-append. Nothing here opens a
    store, because a second path to a main's log is a second writer and the
    single writer is what lets the store skip a journal (AD-1).

    ``trust_view`` is narrowed by construction: it hands back a ``TrustView``
    and not the fold, so the crisis, aftercare and schedule records are
    unreachable rather than merely unread.
    """

    def crisis_open(self, main_id: str) -> bool:
        ...

    async def trust_view(self, main_id: str) -> TrustView:
        ...

    async def note_ask(
        self, main_id: str, *, t: str, question: str, about: str
    ) -> str:
        ...


@dataclass(frozen=True, slots=True)
class UnaskedQueue:
    """One main's held questions: what is waiting, what may be asked, and the
    spend that pays for it.

    **The crisis check lives here rather than in the gates**, and that is the
    same placement ``MorningSurface`` uses. A pure function that took a
    ``crisis: bool`` argument would be a rule every future caller has to
    remember; a class that asks the ledger first is one nobody can forget,
    because the ledger is the only way in.

    **Nothing here asks the main anything.** ``next_ask`` answers *which
    question may be asked*, ``spend`` records that one was, and there is no
    channel on this object to say it with.
    """

    ledger: TrustLedger

    async def waiting(
        self, main_id: str, *, questions: Sequence[Unasked], live: Strands | None
    ) -> tuple[Verdict, ...]:
        """What this main's queue is holding. Empty in crisis.

        The mode suspends Half's ordinary behaviour entirely (CAP-12), and a
        held question is ordinary behaviour: the currency is void in the mode,
        so there is nothing to report and nothing to wait for.
        """
        if self.ledger.crisis_open(main_id):
            return ()
        view = await self.ledger.trust_view(main_id)
        return queue(questions, view=view, live=live)

    async def next_ask(
        self, main_id: str, *, questions: Sequence[Unasked], live: Strands | None
    ) -> Ask | None:
        """The one question that may be asked now, or ``None``.

        ``None`` is the ordinary answer and carries no reason, because there is
        usually nothing to explain: most conversations touch nothing a held
        question is about, and most held questions are waiting on a favour
        nobody has earned yet. Neither is a failure (AD-27).

        **Exactly one, never two.** There is no plural door out of this class
        onto an asking path: a caller that wants to ask asks for one, spends
        for one, and comes back.

        Writes nothing. A question that is considered — and a question that is
        considered and refused — leaves the balance exactly as it was.
        """
        if self.ledger.crisis_open(main_id):
            return None
        view = await self.ledger.trust_view(main_id)
        found = asks_at(questions, view=view, live=live)
        return found[0] if found else None

    async def spend(self, main_id: str, *, t: str, ask: Ask) -> str:
        """Record that ``ask`` is being asked, or refuse. One of ``ASK_OUTCOMES``.

        **Called immediately before the question reaches the main, never
        before it is chosen and never on a refusal.** That ordering is story
        10's, deliberately: the day is claimed and then the message is sent,
        because the alternative — send, then record — lets two overlapping
        runs both find the favour unspent and both ask. The cost of this order
        is the same one story 10 accepted: a question that fails to reach the
        main costs one favour. The cost of the other order is the rule itself.

        The registry re-reads the balance and the mode under this main's own
        mutex, so the check and the append are one serialized operation and a
        favour cannot be spent twice.
        """
        return await self.ledger.note_ask(
            main_id, t=t, question=ask.question.id, about=ask.question.about
        )
