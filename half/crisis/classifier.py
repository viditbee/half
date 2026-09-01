"""The second opinion: a model that widens **ask** and can never enter (CAP-12).

Story 6a shipped a phrase table, and a phrase table fires only on what somebody
thought to write down. It returns nothing for ``kms``, ``unalive myself``,
``im sucidal``, ``i've written a note``, ``i'm done.`` and for every phrasing in
a script nobody added a row for — which inverts the companion's asymmetry
argument in the one place a miss is unrecoverable. The ways a person says this
are not enumerable, so the recall instrument cannot be an enumeration.

**The model decides and never writes.** What this module holds is a
``Classifier`` — the port's narrow protocol, whose whole point is the methods it
does not have (AD-19). There is no generation anywhere on this path, and the
constructor refuses a holder that could generate rather than trusting a caller
to hand over the narrow one. Every reply a main receives is still a join of
reviewed template lines assembled by ``half.crisis.respond``, which takes an
``Assessment`` and never a word of text.

**It widens ``ASK``, never ``ENTER``.** Entering carries a durable thirty-day
cap, so a model may not impose one: ``ACTION_FOR_LABEL`` maps every label to
``ASK`` or to nothing at all, and that is checked at import rather than
remembered. What a model can do is make Half ask, which costs a moment of
awkwardness a caring friend also produces and is reversible by the main saying
no. Entering stays where 6a put it — the safe word, an explicit disclosure,
reaching a crisis line, and the main's own affirmative answer to Half's
question. A model widening ``ASK`` therefore reaches the mode only *through the
main's own yes*, which is a table decision on the main's own word.

**Uncertain and unavailable are different, and are handled differently.** Both
are "no answer", and treating them alike picks one harm or the other. A model
that ran and is unsure means **ask** — ``unsure`` is a label, not a failure, and
doubt is cheap. A model that did not run means **fall back to the table**, which
is 6a's behaviour exactly, because asking every main about suicide whenever a
provider is down is its own harm. The rule that separates them is one line: an
answer that is not a label from the closed set is a fallback, whatever shape it
arrived in — a transport fault, a refusal, a budget refusal, a reply past the
bound, prose, or a label from some other build.

**A fallback is counted.** ``Tally`` holds counts and nothing else (AD-22), so
an operator can see the rate. A silent degradation of the recall this module
exists for is the worst outcome available here: it looks exactly like a product
where nobody is ever at risk.

**This is content egress, and it is stated here rather than discovered.** The
main's message text leaves the machine to be classified. Nothing else does: no
ledger, no beliefs, no history, no strand, no contact, no region. ``main_id``
travels on the ``Prompt`` because the tier travels with the main (AD-20) and the
port resolves the model from it — it is read locally and appears in no payload,
which ``tests/test_classifier.py`` asserts against the rendered request rather
than against this sentence.

**Nothing is written about the message.** No belief, no claim, no stored
classification. 6a's rule that a crisis turn records nothing holds, and a
classified turn that turns out to be ordinary records nothing extra either — the
tally is a count in memory, not a row in anybody's log.

**The turn is bounded.** ``BOUND_SECONDS`` is the whole of what a main waits for
this; past it the call is abandoned and the table's answer stands. A hanging
provider costs Half a second opinion and never costs a main their reply.

**Never gated by tier** (CAP-12). Nothing here reads a plan or a payment state,
and a main with no model configured simply has no second opinion — which is
story 6a's behaviour, not a degraded one.

**Detection quality is a clinical-review item.** The label set below and the
instructions the model is given go to the reviewer with the templates, and
``tests/test_crisis_golden.py`` pins both so that changing them after review
fails by name. A green suite is not clinical review, and this module's whole
subject is detection quality.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from half.crisis.signals import Action
from half.errors import CrisisError
from half.model.port import (
    Classifier,
    Classify,
    Decision,
    Failure,
    Prompt,
    Role,
    Turn,
)

#: Structured, and content-free. Every value logged from this module is a
#: closed enum, a count, or a ``main_id`` — never a message, a completion, or a
#: label rationale (AD-22).
logger = logging.getLogger(__name__)


# ── the label set ────────────────────────────────────────────────────────────
#
# Four labels, closed. Changing the set — or what a label permits — is an
# Ask-First change and a clinical-review change, and it fails
# ``tests/test_crisis_golden.py`` by name.

#: The person who sent the message may be at risk. Asks.
MAIN_AT_RISK: Final[str] = "main_at_risk"

#: The model ran and cannot tell. Asks, because doubt is cheap and a wrong
#: question costs one awkward moment while a wrong silence costs the only
#: chance to ask.
UNSURE: Final[str] = "unsure"

#: The risk is about somebody other than the main. Nothing happens: 6a decides
#: the third-party path from the table, on the main's own words, and a reply
#: telling a main that somebody they love is in danger is not a thing to say on
#: a model's inference. Its value here is that the model has somewhere to put
#: such a message other than ``main_at_risk`` — without it, a message about a
#: frightened friend produces a gentle question aimed at the wrong person.
ANOTHER_AT_RISK: Final[str] = "another_at_risk"

#: An ordinary message. Nothing happens.
NO_RISK: Final[str] = "no_risk"

#: The whole of what may come back. Carried on the request, so the port can
#: constrain the reply's *shape* to this set rather than to an instruction
#: somebody could reword (AD-19).
LABELS: Final[tuple[str, ...]] = (MAIN_AT_RISK, UNSURE, ANOTHER_AT_RISK, NO_RISK)

#: The one place a label becomes a decision. **No value here is ``ENTER``**, and
#: ``_check_labels`` refuses the module rather than trusting that sentence.
ACTION_FOR_LABEL: Final[dict[str, Action]] = {
    MAIN_AT_RISK: Action.ASK,
    UNSURE: Action.ASK,
    ANOTHER_AT_RISK: Action.NONE,
    NO_RISK: Action.NONE,
}

#: What the model is told. Reviewed data, like the templates — and, like them,
#: pinned by a digest so that a wording change after clinical review fails
#: rather than ships.
#:
#: It describes the labels and nothing else. It does not ask for prose, a
#: rationale, a score or a confidence: the reply's shape is constrained to one
#: label by the port, so there is no channel for any of those to arrive in and
#: no instruction here that could open one.
INSTRUCTIONS: Final[tuple[str, ...]] = (
    "You are a safety classifier inside a personal messaging assistant. You "
    "will be shown one message that a person sent to that assistant. Choose "
    "exactly one label for it. You are not in a conversation, nothing you "
    "write is shown to anyone, and the only thing read from your reply is the "
    "label itself.",

    "main_at_risk: the person who sent this message may be at risk of suicide "
    "or self-harm. This covers plain statements, indirect and hedged wording, "
    "slang and abbreviations, deliberately obscured or misspelled words, "
    "hopelessness about being alive, preparatory acts such as writing a note, "
    "giving belongings away or putting affairs in order, and goodbyes. It "
    "covers every language and every script, and a message written in one you "
    "handle poorly is a reason to answer unsure rather than no_risk.",

    "another_at_risk: the message is about somebody other than the sender — a "
    "friend, a relative, a public figure, a character in a film or a book. "
    "Use this even when the risk described is severe. If the sender is also "
    "describing themselves, the label is main_at_risk.",

    "unsure: you cannot tell. Use it freely. It is the right answer for an "
    "ambiguous message, an unfamiliar idiom, a fragment with no context, and "
    "anything you would want to read twice.",

    "no_risk: an ordinary message with nothing in it that suggests risk to "
    "anyone.",

    "Answer unsure rather than no_risk whenever you are not confident. The two "
    "mistakes do not cost the same: a wrong unsure costs one gentle question "
    "that is easy to answer no to, and a wrong no_risk costs the only chance "
    "anyone had to ask.",
)

#: How long a main waits for a second opinion, in seconds. Past it the call is
#: abandoned and the table's answer stands, counted as a bound rather than as a
#: judgement. Deliberately short: this sits in front of a reply somebody is
#: waiting for, and the thing being protected is the reply.
BOUND_SECONDS: Final[float] = 5.0

#: Ceilings for one classification and for one process's worth of them, in
#: millionths of a dollar.
#:
#: **The per-call figure is the one that binds**, and it is deliberately loose:
#: the port's estimate charges the full output ceiling in advance, so a short
#: message prices at about six thousand on the cheap tier and twenty-eight
#: thousand on the frontier one, against a settled cost a fraction of either.
#: Ten cents admits every message a person actually sends on both tiers and
#: refuses a pathological one — and it has to admit both, because CAP-12 is
#: never gated by tier and a ceiling that refused every paid main's turns would
#: be a tier gate wearing a budget's clothes.
#:
#: **The per-pass figure is a runaway stop and not a cost target.** Spending
#: here is bounded by construction rather than by this number: at most one
#: classification per inbound message, and no loop, schedule or retry can make
#: a second. It is set far above any conversational total precisely so that it
#: never becomes the thing that silently removes the recall this module exists
#: for — that is what the per-call ceiling and the counted fallback are for.
PER_CALL_MICRO_USD: Final[int] = 100_000
PER_PASS_MICRO_USD: Final[int] = 500_000_000

#: How often the running counts are written out, in consultations. **The rate
#: has to be visible, not merely reachable.** Every fallback already logs its
#: own line, but a line per event tells an operator that one call failed, not
#: that a fifth of them are failing — and a silent degradation of the recall
#: this module exists for looks exactly like a product where nobody is ever at
#: risk. Counts only, per AD-22, and per hundred rather than per call so the
#: line is a summary rather than a second log of the same thing.
REPORT_EVERY: Final[int] = 100

#: Methods a holder must not have. The port's ``Classifier`` is narrow by
#: construction; this refuses a *wider* object being passed where the narrow
#: one belongs — an ``AnthropicProvider``, say, which can generate, batch and
#: reach a provider that would. "The model never writes" is then a property of
#: what this object is allowed to hold rather than of who remembered to call
#: ``provider.classifier()``.
FORBIDDEN_METHODS: Final[frozenset[str]] = frozenset({
    "generate", "submit", "collect", "complete", "message", "stream",
})


@dataclass(frozen=True, slots=True)
class Verdict:
    """What a second opinion came to. Never text, and never ``ENTER``.

    ``label`` is ``None`` unless the model answered with one of ``LABELS``.
    ``fell_back`` says the model did not answer at all, which is a different
    thing from answering ``unsure`` and is handled differently: the first
    leaves the table's assessment untouched, the second asks.
    """

    action: Action
    label: str | None = None
    fell_back: bool = False

    @property
    def asks(self) -> bool:
        return self.action is Action.ASK


#: No model was consulted — this main has none configured, or there was nothing
#: to classify. Story 6a's behaviour exactly, and deliberately *not* a fallback:
#: a rate that counted every turn of a build with no classifier wired would say
#: nothing about a classifier that is failing.
NOT_CONSULTED: Final[Verdict] = Verdict(Action.NONE)

#: The model was consulted and did not answer. The table's answer stands.
FELL_BACK: Final[Verdict] = Verdict(Action.NONE, fell_back=True)


@dataclass(slots=True)
class Tally:
    """What the classifier has been doing, as counts (AD-22).

    Counts and nothing else: no message, no completion, no rationale. The keys
    are label names from the closed set above and ``kind/reason`` pairs from the
    port's two closed enums, so there is no field here that a main's words could
    travel in.

    Held in memory and never written to a main's log — a classified turn
    records nothing about the main, and that includes the fact that it was
    classified.
    """

    #: Calls attempted, which is the denominator of every rate below.
    consulted: int = 0
    #: label -> how many times it came back.
    labels: dict[str, int] = field(default_factory=dict)
    #: ``"kind/reason"`` -> how many times the port reported it.
    failures: dict[str, int] = field(default_factory=dict)
    #: Calls abandoned at ``BOUND_SECONDS``. Its own counter rather than a
    #: transport fault, because "the classifier is slow" and "the provider is
    #: unreachable" want different things done about them and the port's closed
    #: reason set has no room to say which.
    bound_exceeded: int = 0
    #: Calls that raised instead of returning one of the four failures. A
    #: build mistake — an unknown tier, a budget that admits nothing — kept
    #: apart from a provider fault for the same reason.
    raised: int = 0

    @property
    def fell_back(self) -> int:
        """Consultations that produced no label at all."""
        return sum(self.failures.values()) + self.bound_exceeded + self.raised

    @property
    def answered(self) -> int:
        return sum(self.labels.values())

    @property
    def asked(self) -> int:
        """Consultations whose label widened the turn to a question."""
        return sum(
            count for label, count in self.labels.items()
            if ACTION_FOR_LABEL.get(label) is Action.ASK
        )

    @property
    def fallback_rate(self) -> float:
        """The number an operator watches. Zero consultations reads as zero
        rather than as an error, because a build with no classifier wired is a
        supported deployment and not a fault."""
        return self.fell_back / self.consulted if self.consulted else 0.0

    def count_label(self, label: str) -> None:
        self.labels[label] = self.labels.get(label, 0) + 1

    def count_failure(self, failure: Failure) -> None:
        key = f"{failure.kind}/{failure.because}"
        self.failures[key] = self.failures.get(key, 0) + 1


class SecondOpinion:
    """A model's opinion on a message the phrase table found nothing in.

    Holds one narrow ``Classifier`` per main — narrow because the port's
    protocol has no method that returns text, and per main because the model
    tier travels with the main (AD-20) and a self-hoster's key is stored under
    their own id (AD-11). A main with no holder gets ``NOT_CONSULTED``: no call,
    no count, and story 6a's behaviour unchanged.

    Everything is private. The holders, the bound and the ledger behind them are
    not reachable through this object, for the reason the port's own holders
    keep theirs private: a narrow *output* is only half of a narrow holder, and
    an attribute is authority. The tally is the one thing readable, and it is
    counts.
    """

    __slots__ = ("_holders", "_bound", "_tally")

    def __init__(
        self,
        holders: Mapping[str, Classifier] | None = None,
        *,
        bound_seconds: float = BOUND_SECONDS,
        tally: Tally | None = None,
    ) -> None:
        holders = dict(holders or {})
        for main_id, holder in holders.items():
            _check_holder(main_id, holder)
        if not isinstance(bound_seconds, (int, float)) or bound_seconds <= 0:
            raise CrisisError(
                f"a bound of {bound_seconds!r} is not a bound. A classification "
                "that may run for ever is a main waiting for a reply for ever, "
                "which is the omission failure with a spinner on it"
            )
        self._holders: Mapping[str, Classifier] = holders
        self._bound = float(bound_seconds)
        self._tally = tally if tally is not None else Tally()

    @property
    def tally(self) -> Tally:
        """The counts. Readable so an operator can see the fallback rate."""
        return self._tally

    def holds(self, main_id: str) -> bool:
        """Whether this main has a second opinion available at all."""
        return main_id in self._holders

    async def consult(self, text: str, *, main_id: str) -> Verdict:
        """One classification, bounded. Never raises, and never returns text.

        The only argument that leaves this machine is ``text``. ``main_id``
        resolves the tier inside the port and appears in no payload.

        Every path out is a ``Verdict`` whose action is ``ASK`` or nothing:
        there is no branch here that could produce ``ENTER``, and no exception
        that could reach the gate and cost a main their reply.
        """
        holder = self._holders.get(main_id)
        if holder is None or not text.strip():
            # Nothing configured, or nothing to classify. Not a fallback: no
            # call was attempted, so counting one would make the rate a
            # measurement of how quiet the main has been.
            return NOT_CONSULTED

        work = Classify(prompt=prompt_for(text, main_id=main_id), labels=LABELS)
        self._tally.consulted += 1
        verdict = FELL_BACK
        try:
            async with asyncio.timeout(self._bound):
                answered = await holder.classify(work)
        except TimeoutError:
            # Past the bound. An unavailability, never a crisis, and never a
            # held reply.
            self._tally.bound_exceeded += 1
            logger.warning(
                "the crisis classifier passed its bound for main=%s; the "
                "phrase table's answer stands", main_id
            )
        except Exception:
            # The port answers a provider fault with a value; a raise here is a
            # build mistake — an unknown tier, a budget admitting nothing — and
            # a build mistake must not cost the recall this module exists for.
            # No content, no completion, no message text (AD-22).
            self._tally.raised += 1
            logger.exception(
                "the crisis classifier could not run for main=%s; the phrase "
                "table's answer stands", main_id
            )
        else:
            verdict = self._verdict(answered, main_id=main_id)
        # On every path out, and that ordering is the point: a summary reached
        # only from the success path would go quiet exactly when the classifier
        # started failing.
        self._report()
        return verdict

    def _report(self) -> None:
        """Write the running counts out, every so often. Counts only (AD-22).

        Deliberately not a rate in the message: a percentage of a small number
        reads as a crisis of its own, and the two integers say the same thing
        without the arithmetic. ``Tally.fallback_rate`` is there for whatever
        reads this object.
        """
        if self._tally.consulted % REPORT_EVERY:
            return
        logger.info(
            "crisis classifier: %d consulted, %d answered, %d fell back "
            "(%d past the bound)",
            self._tally.consulted, self._tally.answered,
            self._tally.fell_back, self._tally.bound_exceeded,
        )

    def _verdict(self, answered: object, *, main_id: str) -> Verdict:
        """One outcome, as an action. Pure.

        **One rule, and it is the whole mapping:** an answer that is not a label
        from the closed set is a fallback. A transport fault, a refusal, a
        budget refusal, a truncated reply, prose, a label from another build and
        anything a future port returns all land there together, because none of
        them is a judgement about a person and treating any of them as one would
        be reading a decision out of a failure.
        """
        if not isinstance(answered, Decision):
            if isinstance(answered, Failure):
                self._tally.count_failure(answered)
                # Two closed enums and a main_id. Nothing else exists to log.
                logger.warning(
                    "the crisis classifier did not answer for main=%s: %s/%s",
                    main_id, answered.kind, answered.because,
                )
            else:
                self._tally.raised += 1
                logger.error(
                    "the crisis classifier returned something this build "
                    "cannot read for main=%s", main_id
                )
            return FELL_BACK

        action = ACTION_FOR_LABEL.get(answered.label)
        if action is None:
            # Unreachable through the port, which refuses a label outside the
            # request's own set. Kept because "unreachable" is a claim about
            # today's implementation and this is the one place where being
            # wrong about it would turn an unknown word into an action.
            self._tally.raised += 1
            logger.error(
                "the crisis classifier answered outside its own label set for "
                "main=%s", main_id
            )
            return FELL_BACK

        self._tally.count_label(answered.label)
        return Verdict(action, label=answered.label)


def prompt_for(text: str, *, main_id: str) -> Prompt:
    """The whole of what a classification is made of.

    One user turn carrying the main's message, and the reviewed instructions in
    front of it. Nothing from the ledger, the strands, the phone book, the
    loops or the main's history is here, and there is no parameter through which
    any of it could arrive.

    **No cache breakpoint is stated.** The instructions are stable and would
    look like a prefix worth caching, but they are far under the cheap tier's
    four-thousand-token minimum, and the port refuses a breakpoint the provider
    would silently ignore rather than placing one that does nothing (AD-19).
    Stating none is the honest answer: this call caches nothing and its cost
    says so.

    The message is sent whole and is never truncated. A message long enough to
    cost more than ``PER_CALL_MICRO_USD`` is refused by the budget and counted
    as a fallback — which is a thing an operator can see, where a quietly
    clipped message would be a classification of half a sentence reported as a
    classification.
    """
    return Prompt(
        main_id=main_id,
        system=INSTRUCTIONS,
        turns=(Turn(role=Role.USER, text=text),),
    )


def _check_holder(main_id: str, holder: object) -> None:
    """Refuse anything that could write, at the boundary rather than in review.

    A ``Classifier`` is narrow because of the methods it lacks. That guarantee
    is worth exactly as much as the check that the object handed over really is
    one, so this is the check.
    """
    if not isinstance(holder, Classifier):
        raise CrisisError(
            f"the holder for main {main_id!r} cannot classify; the crisis path "
            "takes the port's narrow classifier and nothing else (AD-19)"
        )
    wider = sorted(
        name for name in FORBIDDEN_METHODS if callable(getattr(holder, name, None))
    )
    if wider:
        raise CrisisError(
            f"the holder for main {main_id!r} can also {', '.join(wider)}. The "
            "crisis path holds an object with no way to produce text — that is "
            "the guarantee, and passing a wider one quietly removes it. Hand "
            "over the narrow classifier, not the provider that owns it"
        )


def _check_labels() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee that ``python -O`` removes is not a guarantee, and the one this
    module exists to keep — *a model may make Half ask and may never make it
    enter* — is exactly the kind an optimisation flag would take away while the
    module still imported cleanly.
    """
    if not LABELS:
        raise CrisisError("a classification with no labels has no decision to make")
    if len(set(LABELS)) != len(LABELS):
        raise CrisisError(f"the label set repeats a label: {LABELS}")
    if any(not isinstance(label, str) or not label.strip() for label in LABELS):
        raise CrisisError(f"a label must be non-empty text: {LABELS}")
    if set(ACTION_FOR_LABEL) != set(LABELS):
        raise CrisisError(
            "every label needs an action and no others: "
            f"{sorted(set(ACTION_FOR_LABEL) ^ set(LABELS))}"
        )
    permitted = {Action.ASK, Action.NONE}
    over = sorted(
        label for label, action in ACTION_FOR_LABEL.items() if action not in permitted
    )
    if over:
        raise CrisisError(
            f"{over} would let a model do more than make Half ask. Entering "
            "carries a durable thirty-day cap and a model may not impose one; "
            "surfacing is a sentence about somebody else and a model may not "
            "author one either. The cheap, reversible action is the whole of "
            "what this widens"
        )
    if not any(action is Action.ASK for action in ACTION_FOR_LABEL.values()):
        raise CrisisError(
            "no label asks, so this classifier widens nothing and is a network "
            "call with a counter attached"
        )
    if not INSTRUCTIONS or any(not block.strip() for block in INSTRUCTIONS):
        raise CrisisError("the reviewed instructions must not be empty")
    for label in LABELS:
        if not any(label in block for block in INSTRUCTIONS):
            raise CrisisError(
                f"{label!r} is in the label set and is defined nowhere in the "
                "instructions. A label the model is never told about is a label "
                "it can only pick by accident"
            )


_check_labels()
