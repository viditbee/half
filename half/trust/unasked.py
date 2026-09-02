"""The unasked queue: two gates, in order, and what spending looks like.

CAP-4, CAP-10, AD-1, AD-3, AD-22, AD-28, AD-30. Clarifying questions Half is
holding, and the rule that decides whether one of them may be asked now.

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
question about it is not askable — and AD-28's ceiling caps it. Both are asked
through ``may_be_raised``, which is the **one predicate the runtime and the
tests read**: ``considered`` calls it here, and ``ActorRegistry.note_ask`` calls
it again under the main's own mutex at the moment of spending. There is no
branch in this file for quarantine and none for aftercare — a main capped at
`behave` has every belief resolve to `behave`, so nothing reaches `ask`, and
that is the whole of *"the ceiling holds, without a special case for the
ceiling"*.

**A question is attached lazily**, never raised cold. The constitution's rule
is *"attach the question to the next conversation that already touches the
topic. Never ping to ask."* So the topic gate reads the actor's live strands —
what the conversation is about right now, against a floor derived from the
strand decay rather than picked (``ON_TOPIC_FLOOR``) — and a question whose
subject nobody has mentioned is **held**, not discarded. That is not AD-24's
excluded retrieval wearing a different hat: nothing is made unreachable, no
belief drops out of any candidate set, and the question stays in the queue with
a reason. What is withheld is Half's own interruption, which is the thing AD-24
has no opinion about.

**Held is not refused, and the queue says which.** ``Verdict.held`` is true for
the two reasons that are *not yet* — the topic has not come up, the balance is
spent — and false for the ones that are *not at all*. Queue depth is itself a
signal (glossary), so ``verdicts`` decides askability over the **whole set** and
the questions the budget could not reach come back as ``NO_FAVOUR`` rather than
being dropped: *"eleven waiting on a favour"* and *"eleven whose topic was never
raised"* are the two situations depth exists to tell apart, and a question that
passed every gate and could not be paid for belongs to the first of them.

**An ``Ask`` is a proposal, and the permission is re-derived where it is spent.**
It carries no authority of its own: it is a plain value, and a caller can build
one. That is why nothing trusts it. ``UnaskedQueue.spend`` re-runs every gate
against a freshly read view before it records anything, and
``ActorRegistry.note_ask`` re-asserts the mode, the balance and the ladder under
the main's own mutex — so a hand-built ``Ask`` for a question that passed no gate
is refused twice over rather than burning a favour. A guarantee carried by a
docstring is not carried.

**Spending is one serialized operation, and it happens before the asking.**
``note_ask`` re-reads the balance under the main's own mutex and appends the
spend, exactly as ``claim_day`` re-reads the day marker and appends the day
(story 10). Two overlapping turns therefore cannot both spend one favour —
which a read here followed by an append there would allow, and which no
single-threaded test would ever see. The caller asks only after the spend
lands, which makes the asymmetry the same one story 10 accepted: a question
that fails to reach the main costs one favour, where the alternative costs the
rule.

**What this module deliberately does not do: remember that a question was
already asked.** An unanswered question stays askable and is offered again when
the next favour lands. That is a known boundary rather than an oversight, and
the evidence is in the log: an ``asked`` record says a question was *put*, and
nothing anywhere records that it was *answered*. A gate on the ``asked``
records alone would therefore not mean *"do not nag"* — it would mean *"never
ask twice, whatever happened"*, permanently silencing a question the main
happened not to reply to. Story 6c had exactly this problem for aftercare and
solved it by recording the **answer** as its own durable state; questions need
the same, and composing and receiving an answer is story 11's. Until then the
balance is what bounds re-asking: each attempt costs a favour.

Nothing in this module writes: the pure half returns values, and
``UnaskedQueue`` reaches the log through the registry's own narrow door — three
methods, and ``tests/test_unasked.py`` measures what it asks that object for
rather than scanning for a forbidden word (AD-1, AD-3). No clock, no network,
no model — none of the gates is a function of time at all, so a verdict changes
only when the log or the conversation does (AD-30).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import (
    dataclass,
    field,
    fields as dataclass_fields,
    replace,
)
from typing import Any, Final, Protocol, runtime_checkable

from half.context.build import resolve
from half.governance.ladder import Ceiling, License, height
from half.loops.ledger import Loop
from half.loops.ledger import read as read_loops
from half.retrieval.strands import DECAY, Strands, strands_of
from half.store.fold import State
from half.trust.balance import Balance
from half.trust.stakes import BELOW_THE_BAR, FINISHED, NO_PERIOD, NO_SUBJECT
from half.trust.stakes import NO_WANTING
from half.trust.stakes import REASONS as STAKE_REASONS
from half.trust.stakes import Stakes, stakes

__all__ = [
    "ASKS_AT", "ASK_CRISIS", "ASK_NOT_PERMITTED", "ASK_OUTCOMES",
    "ASK_RECORDED", "ASK_REFUSED", "ASK_UNAFFORDABLE", "Ask", "BELOW_THE_BAR",
    "FINISHED", "HELD", "NOT_PERMITTED", "NO_FAVOUR", "NO_PERIOD",
    "NO_SUBJECT", "NO_WANTING", "ON_TOPIC_FLOOR", "REASONS", "TOPIC_UNRAISED",
    "TrustLedger", "TrustView", "Unasked", "UnaskedQueue", "VISIBLE",
    "Verdict", "asks_at", "considered", "may_be_raised", "narrowed_for_trust",
    "on_topic", "queue", "verdicts", "view_fields",
]

#: The weakest rung a question may be raised from.
#:
#: `ask` is, by the ladder's own definition, *"Half may raise it as a
#: question"* — so the rung this gate wants is not a policy choice but the name
#: of the thing being asked for. `behave` is where Half acts silently, and a
#: question is the opposite of silent. Derived from the ladder rather than
#: written as a literal, for the reason ``half.surface.morning.SPEAKS_AT`` is.
ASKS_AT: Final[License] = License.ASK

#: How live a question's subject must be for the conversation to count as
#: already touching it.
#:
#: **Derived, not chosen — like every other number in this story.** It is
#: ``half.retrieval.strands.DECAY``, imported rather than typed, and that is
#: what fixes its meaning: a strand loses ``DECAY`` of its weight on every turn
#: that does not mention it, so a floor *of* ``DECAY`` says a topic is live for
#: the turn it was raised in and for the one immediately after — which is where
#: a reply to a question actually lands — and not beyond.
#:
#: The alternative was ``> 0.0``, which is what this gate shipped as before
#: review and which is not a decision at all: it inherits ``Strands``' own
#: ``EPSILON`` housekeeping value, so a topic mentioned once stayed "already
#: raised" through roughly eight further turns of unrelated conversation. That
#: is a retrieval artefact governing a governance rule — the same shape as
#: borrowing a cadence from another loop, which ``choose.touchable`` refuses.
#:
#: Compared with ``>=``, so a *partial* match at exactly the floor counts: a
#: message that used half the tokens of a two-word strand raised the topic.
ON_TOPIC_FLOOR: Final[float] = DECAY

#: The ladder does not permit raising this belief as a question — because it is
#: quarantined, because the main's ceiling caps it, or because its own license
#: sits below `ask`. **Not this story's decision**, and there is no branch here
#: that distinguishes the three: ``may_be_raised`` answers all of them through
#: one call to the context builder's own door, and a second opinion about which
#: is a second place for them to disagree.
NOT_PERMITTED: Final[str] = "not-permitted"
#: The main has not touched this question's subject. **Held**, not refused: the
#: question is attached lazily to a conversation that already covers it, and
#: Half never pings to ask.
TOPIC_UNRAISED: Final[str] = "topic-unraised"
#: Half has not given, has already spent what it was given, or gave less than
#: the number of good questions waiting. **Held**: the question is worth asking
#: and cannot be paid for yet.
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
#: answer, and a value nobody recognised would fall through as *spent*.
#:
#: Five outcomes across two layers, and the split is deliberate.
#: ``ASK_REFUSED`` is this module's: the question no longer passes the gates at
#: the moment of spending, which is also what a hand-built ``Ask`` gets. The
#: other three refusals are the registry's, decided under the main's own mutex
#: where they cannot be stale.
ASK_RECORDED: Final[str] = "asked"
ASK_CRISIS: Final[str] = "crisis"
ASK_UNAFFORDABLE: Final[str] = "unaffordable"
ASK_NOT_PERMITTED: Final[str] = "not-permitted-now"
ASK_REFUSED: Final[str] = "refused"
ASK_OUTCOMES: Final[frozenset[str]] = frozenset(
    {ASK_RECORDED, ASK_CRISIS, ASK_UNAFFORDABLE, ASK_NOT_PERMITTED, ASK_REFUSED}
)


def _trimmed(value: object) -> str:
    """``value`` as a stripped string, or ``""``. Never raises.

    The one normalization in this module, applied at ``Unasked``'s boundary so
    that the id which is weighed is the id which is written — see that class.
    """
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class Unasked:
    """One clarifying question Half is holding.

    A value, and deliberately a thin one. It carries an opaque ``id`` and the
    belief whose ambiguity it would resolve — **and no text**, no rank, no
    score and no stakes. What it would say is composed at delivery (story 11);
    what it is worth is computed from the log by ``half.trust.stakes``, so that
    two builds reading one log weigh one question identically.

    **Normalized once, here, and nowhere else.** Both fields are stripped at
    construction, because the alternative is a value that is looked up one way
    and recorded another: review found ``considered`` matching on
    ``about.strip()`` while the spend passed the raw string to the log, so an
    append-only record could permanently name a belief id that no belief equals.
    One normalization at the boundary means the id that was weighed is the id
    that is written.

    Named ``Unasked`` rather than ``Question`` on purpose:
    ``half.context.channels.Question`` is a rendered line in a built context,
    which is the one thing this is not.
    """

    id: str
    about: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _trimmed(self.id))
        object.__setattr__(self, "about", _trimmed(self.about))

    @property
    def nameable(self) -> bool:
        """Whether this question can be recorded at all.

        The predicate, read by the runtime **and** by the tests, rather than a
        pair of emptiness checks each writes out. A question with no id cannot
        be spent against and a question about nothing cannot be weighed, and
        both are refused before either gate runs.
        """
        return bool(self.id and self.about)


#: What ``considered`` uses in place of a value that is not a question at all.
#: It is ``nameable=False``, so it refuses at the first gate — and it exists so
#: that ``Verdict.question.id`` is safe on every path. Returning the raw object
#: instead, which is what shipped before review, meant a caller reading the
#: verdict of a ``None`` raised an ``AttributeError`` on the turn's own path,
#: which is exactly what this module's *"never raises"* contract forbids.
NOT_A_QUESTION: Final[Unasked] = Unasked(id="", about="")


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
    """One question the gates permitted, and what being wrong would have cost.

    **A proposal, not a permission**, and the docstring says so because the
    type cannot enforce anything else: it is a plain frozen dataclass and a
    caller can build one. Review built one for a question that had passed no
    gate and watched it burn a favour, because ``spend`` trusted it.

    So nothing trusts it now. ``UnaskedQueue.spend`` re-runs every gate against
    a freshly read view before recording, and ``ActorRegistry.note_ask``
    re-asserts the mode, the balance and the ladder under the main's own mutex.
    Both refusals are outcomes rather than exceptions, because the caller's
    correct response is to ask nothing (AD-27).

    ``asks_at`` is still the only thing that *mints* one, and holding one means
    the gates passed at the moment it was made — which is a useful thing to
    hold, and a different claim from *"this may be asked"*, because the log and
    the conversation both move.
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
        cost = self.stakes.cost_days if isinstance(self.stakes, Stakes) else None
        return (-(cost or 0), self.question.id)


# -- what the queue is allowed to see -----------------------------------------


#: The fields of ``State`` the unasked queue may consult. An allowlist, spelled
#: once, **read by ``narrowed_for_trust`` itself** and by
#: ``tests/test_unasked.py`` — so a new field on ``State`` is invisible here
#: until somebody adds it on purpose. Before review the projection hard-coded
#: its two fields and this constant was documentation, which is the shape of an
#: allowlist that does not allow anything.
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

    **Built from ``VISIBLE``**, not from two hard-coded keyword arguments. That
    is what makes the allowlist load-bearing: adding a field to the constant is
    the whole of admitting it, and a field absent from the constant cannot
    arrive here by somebody widening the constructor call.

    ``balance`` is passed in rather than computed here because it is a fold over
    the **log**, not over ``state`` — that is the whole of AD-30 for this story,
    and a version of this function that derived it from ``state`` would be the
    counter this design exists to avoid.
    """
    copied: dict[str, Any] = {
        name: {
            key: dict(value) for key, value in getattr(state, name).items()
        }
        for name in VISIBLE
    }
    return TrustView(ceiling=ceiling, balance=balance, **copied)


def view_fields() -> tuple[str, ...]:
    """The view's own field names. Read by the test that pins the allowlist."""
    return tuple(f.name for f in dataclass_fields(TrustView))


# -- the gates ----------------------------------------------------------------


def may_be_raised(belief: Mapping[str, Any] | None, *, ceiling: Ceiling) -> bool:
    """Whether the ladder permits raising ``belief`` as a question (AD-28).

    **One predicate, two call sites, and that is the point.** ``considered``
    asks it when a question is weighed, and ``ActorRegistry.note_ask`` asks it
    again under the main's own mutex at the moment a favour is spent — because
    a main whose cap drops to `behave` between the two (aftercare, an operator
    cap, a crisis) must not still be asked. A rule spelled out at one of those
    two places and paraphrased at the other is two rules.

    Asked through ``half.context.build.resolve``, which story 4b made *the*
    place a license becomes a decision — reaching past it into the ladder's
    rule set would be a second reader with the ceiling capping only one of
    them, and ``tests/test_ladder.py`` fails the build for it. One call answers
    quarantine, the belief's own rung and the cap together.

    ``ceiling`` is keyword-only and undefaulted for the reason ``resolve``'s is:
    a caller that forgets it gets a ``TypeError`` rather than a question
    resolved as though no cap existed.
    """
    if not isinstance(belief, Mapping):
        return False
    return height(resolve(belief, ceiling=ceiling)) >= height(ASKS_AT)


def on_topic(belief: Mapping[str, Any] | None, live: Strands | None) -> bool:
    """Whether the conversation already touches what this question is about.

    *"Attach the question to the next conversation that already touches the
    topic. Never ping to ask."* The strands are the actor's live weights — how
    the main is right now, which is volatile by AD-26 and never in the fold —
    so they are passed in rather than carried on the view.

    The comparison is against ``ON_TOPIC_FLOOR``, which is the strand decay
    rather than a number chosen here; see that constant for why *"anything
    above zero"* was a retrieval artefact governing a governance rule.

    ``live=None`` means there is no conversation: the nightly pass, the morning
    surface, a scheduler tick. Nothing is on topic then, and every question is
    held, which is the correct reading of *never ping to ask*.

    **This is not AD-24 exclusion.** Nothing is made unreachable and no belief
    leaves any candidate set; the question stays in the queue with a reason,
    and what is withheld is Half's own interruption.
    """
    if not isinstance(belief, Mapping) or not isinstance(live, Strands):
        return False
    return live.match(strands_of(belief)) >= ON_TOPIC_FLOOR


def considered(
    question: Unasked | Any, *, view: TrustView, live: Strands | None
) -> Verdict:
    """Whether ``question`` may be asked now. Pure, total, and never raises.

    The gates, in the order that is the rule:

    1. the question can be named at all, and names a belief the log holds;
    2. **stakes** — worth its interruption, or not worth asking at all;
    3. the **ladder**, under this main's ceiling — quarantine and AD-28, asked
       through ``may_be_raised``, with no branch here for either;
    4. the **topic** — raised by the main, or held;
    5. the **favour** — given and unspent, or held.

    Stakes are asked before the currency, and cannot be asked after it: this
    function returns on a stakes refusal, and ``stakes`` is not given a balance
    to consult. Reversed, a large balance would buy a worthless question.

    **The favour gate here answers for one question in isolation.** Whether the
    balance can reach *this* question when several are competing for it is
    ``verdicts``' answer, because that is a property of the set — see there.

    Never raises, on the same terms as ``choose.eligible``: the caller is on a
    turn's own path, and losing the main's reply over a malformed loop entry is
    worse than losing one question. A value that is not a question at all is
    answered rather than thrown — every verdict carries a real ``Unasked``, so
    a caller reading ``verdict.question.id`` cannot be handed an
    ``AttributeError``.
    """
    named = question if isinstance(question, Unasked) else NOT_A_QUESTION
    if not named.nameable:
        # ``NO_SUBJECT`` is the stakes vocabulary's own word for *"there is
        # nothing here to be wrong about"*, imported rather than respelled: a
        # question naming no belief and a question about a belief the log does
        # not hold must give one answer, and two spellings of it is how a
        # caller counting refusals counts two different things.
        return Verdict(question=named, reason=NO_SUBJECT)

    belief = view.beliefs.get(named.about)
    weighed = stakes(belief, loops=view.loop_table())
    if not weighed.worth_asking:
        # Not deferred. A question that is not worth its interruption is not
        # worth asking whatever the balance is, and it does not enter the held
        # queue — see ``HELD``.
        return Verdict(question=named, reason=weighed.reason, stakes=weighed)

    if not may_be_raised(belief, ceiling=view.ceiling):
        return Verdict(question=named, reason=NOT_PERMITTED, stakes=weighed)

    if not on_topic(belief, live):
        return Verdict(question=named, reason=TOPIC_UNRAISED, stakes=weighed)

    if not view.balance.spendable:
        return Verdict(question=named, reason=NO_FAVOUR, stakes=weighed)

    return Verdict(question=named, askable=True, stakes=weighed)


def verdicts(
    questions: Iterable[Unasked] | None, *, view: TrustView, live: Strands | None
) -> tuple[Verdict, ...]:
    """Every question's verdict, with the balance allocated across the set.

    **The one place askability is decided**, and both ``asks_at`` and ``queue``
    read it, so a question cannot be askable to one of them and absent from the
    other. Before review they computed separately and a question that passed
    every gate but sat beyond the budget appeared in neither list — dropped
    silently, which is exactly the case queue depth exists to make visible.

    The allocation: the questions that passed every gate are ordered by
    ``Ask.order`` — costliest mistake first, then id — and the number the
    balance can actually pay for stay askable. The rest come back as
    ``NO_FAVOUR``, which is what they are: worth asking, unaffordable today.

    A slice of an ordered list rather than a running counter, deliberately at
    the smallest scale this story works at: there is no variable here a second
    loop could decrement twice.

    Deduplicated on the question's id, so a producer that emitted the same
    question twice cannot make one favour look like it bought two.

    Returned in **input order**, so a caller listing a queue sees it in the
    order it handed one over; ``asks_at`` re-sorts by cost for its own purpose.
    """
    found: list[Verdict] = []
    seen: set[str] = set()
    for question in questions or ():
        verdict = considered(question, view=view, live=live)
        key = verdict.question.id
        if key:
            if key in seen:
                continue
            seen.add(key)
        found.append(verdict)

    ready = sorted(
        (index for index, verdict in enumerate(found) if verdict.askable),
        key=lambda index: Ask(
            question=found[index].question, stakes=found[index].stakes
        ).order,
    )
    funded = set(ready[: max(0, view.balance.unspent)])
    return tuple(
        verdict
        if not verdict.askable or index in funded
        else replace(verdict, askable=False, reason=NO_FAVOUR)
        for index, verdict in enumerate(found)
    )


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
    not in here. One that passed every gate and lost the budget to a costlier
    question **is**, as ``NO_FAVOUR``. Nor is one that failed on stakes or on
    the ladder: those have left the queue, which is what stops it accumulating
    things nobody will ever ask.
    """
    return tuple(
        verdict
        for verdict in verdicts(questions, view=view, live=live)
        if verdict.held
    )


def asks_at(
    questions: Iterable[Unasked] | None, *, view: TrustView, live: Strands | None
) -> tuple[Ask, ...]:
    """Every question the balance can pay for right now, costliest first.

    **The favour is spent by the asking, so one favour buys one question**, and
    ``verdicts`` is where that is true of a *set* rather than of one element:
    two questions that both pass every gate against one delivered favour
    produce exactly one ``Ask``, and the other comes back from ``queue`` as
    held on the favour rather than vanishing.

    The bound is applied inside ``verdicts`` rather than here, so *"the ranking
    sees only what may be asked"* is true of the whole list — the same
    correction ``choose.eligible`` carries. Ranking first and cutting afterwards
    would produce a queue that goes quiet whenever its best question is
    unaffordable.
    """
    ready = [
        Ask(question=verdict.question, stakes=verdict.stakes)
        for verdict in verdicts(questions, view=view, live=live)
        if verdict.askable and verdict.stakes is not None
    ]
    return tuple(sorted(ready, key=lambda ask: ask.order))


# -- the composition: crisis, the view, and the spend -------------------------


@runtime_checkable
class TrustLedger(Protocol):
    """The three doors the unasked queue needs into a main's durable state.

    A protocol rather than the concrete ``ActorRegistry`` for the reason
    ``SurfaceLedger`` is one: this is the whole dependency — one narrowed read,
    one boolean, and one serialized check-and-append. Nothing here opens a
    store, because a second path to a main's log is a second writer and the
    single writer is what lets the store skip a journal (AD-1).

    ``runtime_checkable`` so a test can assert the real registry satisfies it.
    That only checks the *names*, which is why ``tests/test_unasked.py`` also
    compares signatures: a keyword-only parameter renamed on one side and not
    the other drifts the two apart with every structural case still green.

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
    question may be asked*, ``spend`` records that one is being, and there is no
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

        **Exactly one, never two**, and the **first** of the ordering rather
        than any other element: the costliest mistake is the one worth an
        interruption. There is no plural door out of this class onto an asking
        path — a caller that wants to ask asks for one, spends for one, and
        comes back.

        Writes nothing. A question that is considered — and a question that is
        considered and refused — leaves the balance exactly as it was.
        """
        if self.ledger.crisis_open(main_id):
            return None
        view = await self.ledger.trust_view(main_id)
        found = asks_at(questions, view=view, live=live)
        return found[0] if found else None

    async def spend(
        self, main_id: str, *, t: str, ask: Ask, live: Strands | None
    ) -> str:
        """Record that ``ask`` is being asked, or refuse. One of ``ASK_OUTCOMES``.

        **Every gate is re-run here, against a view read now.** An ``Ask`` is a
        proposal and carries no authority — review built one by hand for a
        question that had passed nothing and watched it burn a favour, because
        this method trusted the value it was handed. It no longer does: the
        question is put through ``considered`` again, and a verdict that is not
        askable comes back as ``ASK_REFUSED`` with nothing written. That closes
        the forged-permission route *and* the ordinary staleness one, which are
        the same defect seen from two sides — the log and the conversation both
        move between the choice and the spend.

        ``live`` is required for that re-check, because the topic gate reads the
        conversation and the conversation is volatile (AD-26). A caller that
        cannot supply one is a caller with no conversation to attach a question
        to, and passing ``None`` correctly refuses.

        **Called immediately before the question reaches the main, never
        before it is chosen and never on a refusal.** That ordering is story
        10's, deliberately: the day is claimed and then the message is sent,
        because the alternative — send, then record — lets two overlapping
        runs both find the favour unspent and both ask. The cost of this order
        is the same one story 10 accepted: a question that fails to reach the
        main costs one favour. The cost of the other order is the rule itself.

        The registry then re-reads the balance, the mode **and** the ladder
        under this main's own mutex, so the check and the append are one
        serialized operation and a favour cannot be spent twice.
        """
        if not isinstance(ask, Ask) or not isinstance(ask.question, Unasked):
            return ASK_REFUSED
        if self.ledger.crisis_open(main_id):
            return ASK_CRISIS
        view = await self.ledger.trust_view(main_id)
        if not considered(ask.question, view=view, live=live).askable:
            return ASK_REFUSED
        return await self.ledger.note_ask(
            main_id, t=t, question=ask.question.id, about=ask.question.about
        )

