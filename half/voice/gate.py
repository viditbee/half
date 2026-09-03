"""The gate: generate, judge cheaply, regenerate a bounded number of times, or
say nothing (CAP-8, AD-19, AD-27).

**The shape is gbrain's voice gate; the fallback and the rubric are not.** Their
gate takes a generator, asks a cheap model whether the candidate sounds
conversational rather than academic, regenerates twice, and then falls back to a
hand-written string. Two of those three are wrong here.

*The rubric.* Theirs is per-surface English-prose style rules. Shipped
worldwide that is one language's idea of good writing applied to everybody's —
the objection ``half.context.channels`` already records against a written
template, one rung stronger, because a template at least admits which language
it is in. So the judge below asks **no question about register at all**. It asks
four things that are true or false in every script: is there anything here, is
it one message rather than an essay, does it carry Half's own scaffolding, and
does it ask more than one question. Everything else is the model's business and
the instructions' (``half.voice.compose.INSTRUCTIONS``).

*The fallback.* Theirs must render something, so it renders a template. Half
must not: AD-27 makes sending nothing first-class, story 10 already ships a
morning that is silent most days, and a template is the one thing this product
cannot ship worldwide. **Silence is the fallback**, and it costs the main a
quiet day rather than a sentence written for somebody else.

*What survives, and it is the whole reason the row was worth consuming:* the
loop is bounded and its outcome is deterministic. Generate, judge, regenerate at
most ``ATTEMPTS`` times, then stop. And their two arguments, which transfer
whole: that silently suppressing the surface is never an option — every outcome
here is counted, with its reason, and an operator can read the rate — and that
tuning belongs in one rubric rather than in forked gate implementations, which
is why story 13b's turn reply will use this judge and not a second one.

**Bounded, capped, breakered and counted as story 6d bounds its consultation.**
A wall-clock bound per attempt, a per-call and per-pass ceiling enforced by the
port's budget *before the transport is touched*, a breaker that stands a main
down after a run of failures, and a tally an operator can read. The numbers
differ from the crisis path's because the situation does: nobody is waiting for
a morning, so the bound is generous where a turn's must be short; and a morning
happens once a day, so the breaker counts mornings rather than turns.

**The tripwire is not one of the judge's rules**, and that separation is
deliberate. A judge rejection means *try again*; a leak means **stop**. A leak
that triggered a regeneration would be a redaction with extra steps — the model
would eventually produce something clean and the send would succeed, leaving the
broken construction rule underneath it invisible. See ``half.voice.leak``.

**Nothing generated is ever durable, logged, or counted as text** (AD-22). The
tally holds integers and keys from two closed sets; there is no field on it, and
no argument to any logging call in this module, that a completion could travel
in.

**No crisis reply is ever generated here** (CAP-12). The morning surface refuses
the mode before it reaches this module, and nothing under ``half/crisis`` can
reach this package at all — a crisis reply stays a join of reviewed template
lines assembled by ``half.crisis.respond``, which takes an ``Assessment`` and
never a word of text.

**Why this repeats the consultation shape a third time, and what should happen
about it.** The bound, the ``Tally``, the breaker, the holder allowlist and the
report/alarm cadence below are the same shape as ``half.crisis.classifier`` and
``half.correction.candidate``. That module's own docstring records the cost
honestly at two consumers; this is the third, and the arithmetic has changed
enough to say so plainly: roughly two hundred lines of the same machinery now
exist in three places, and a fix to one of them — story 6d's review corrected
the holder check from a denylist to an allowlist, and separated ``raised`` from
``unreadable`` — has to be made three times or it is made once and forgotten
twice.

The obstacle ``candidate.py`` names still stands: ``half.crisis`` is the entry
gate and is depended upon by no domain module, so the shared code cannot live
there. But the two differences it gives as reasons *not* to share are both
policy rather than shape, and both are injectable. What differs between the
three is the **outcome type** (a ``Verdict`` carrying an action; a ``Verdict``
carrying an action; a ``Composed`` carrying prose or a reason), the **label or
judge policy**, and the **numbers**. What is identical is the bounded call, the
counted fallback, the per-holder breaker and the allowlisted narrow holder.

So the recommendation is unchanged and stronger: a ``half/model/consult.py``
holding the bounded, counted, breaker-guarded call over a narrow holder, with
the policy injected — and with two conditions that are not negotiable. Crisis
behaviour must come out byte-identical, asserted rather than reviewed, because
``tests/test_crisis_golden.py`` pins that module's label set and instructions by
digest as clinical-review material. And the extraction must not let anything
else acquire that status by inheritance: the shared module holds *no* labels,
*no* instructions and *no* numbers, or the pin becomes a pin on a base class and
means nothing.

It is not done here because the crisis path is Ask-First for this story and a
refactor across it is not something to slip into a story about prose. Recorded
rather than done quietly, which is the same choice ``candidate.py`` made and the
last time it will be the right one.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from half.context.channels import Context, render_line
from half.errors import VoiceError
from half.model.port import (
    Completion,
    Failure,
    Generate,
    Generator,
    Reason,
)
from half.voice import leak
from half.voice.compose import (
    ASK_ABOUT,
    BE_MINDFUL_OF,
    LANGUAGE_SAMPLE,
    MAY_BE_SAID,
    RETRY,
    Sample,
    prompt_for,
)

#: Structured, and content-free. Every value logged from this module is a closed
#: enum, a count, an exception's class name, or a ``main_id`` — never a prompt,
#: a completion, a claim or a main's own words (AD-22).
logger = logging.getLogger(__name__)

__all__ = [
    "ALARM_AFTER", "ALARM_RATE", "ALLOWED_METHODS", "ATTEMPTS",
    "BOUND_SECONDS", "BREAK_AFTER", "BREAK_FOR", "Composed", "EMPTY",
    "JUDGED", "LEAKED", "MAX_CHARS", "MAX_OUTPUT_TOKENS", "NOTHING_TO_SAY",
    "NO_LANGUAGE", "NO_MODEL", "OVER_BUDGET", "PAST_THE_BOUND",
    "PER_CALL_MICRO_USD", "PER_PASS_MICRO_USD", "QUESTION_MARKS", "RAISED",
    "REFUSALS", "REFUSED", "REPORT_EVERY", "SCAFFOLDING", "SILENCES",
    "STANDING_DOWN", "Spoken", "TOO_LONG", "TWO_QUESTIONS", "Tally",
    "Unspoken", "Voice", "judge", "scaffolding",
]


# ── the bounds ───────────────────────────────────────────────────────────────

#: How long one attempt may run, in seconds.
#:
#: **Generous where the crisis and correction bounds are tight, and the
#: difference is the situation rather than a preference.** ``BOUND_SECONDS``
#: there is two seconds because it is a pause in front of somebody who has just
#: written and is waiting for an answer, inside AD-23's five-second
#: acknowledgement window. A morning is unprompted: nobody is waiting, nothing
#: is holding a webhook open, and the whole pass runs on the due-time queue
#: under its own concurrency bound. What this number protects is the *tick* — a
#: hung provider must not hold a scheduler slot — so it is sized to leave room
#: for every attempt inside one main's share of a pass.
BOUND_SECONDS: Final[float] = 20.0

#: How many times a candidate is generated before Half gives up and says
#: nothing. One generation and two regenerations — gbrain's number, and their
#: argument for it holds: past two, a judge that keeps refusing is telling you
#: something about the material rather than about the draft.
#:
#: The loop is bounded by this count and by ``BOUND_SECONDS`` per attempt, so
#: the worst case is arithmetic rather than a hope: three attempts, sixty
#: seconds, one morning.
ATTEMPTS: Final[int] = 3

#: The most characters a morning may be.
#:
#: A bound on the *message*, not on the writing. CAP-8 says at most one thing,
#: and this is the loosest ceiling that still refuses an essay: roughly a
#: hundred words of Latin prose, about the same of Devanagari or Thai, and
#: rather more of Han — so the inequality runs toward *more* room for the
#: scripts that need it least, and no script's ordinary one-thing morning comes
#: near it. It is counted in characters rather than words because a word count
#: is not a thing every script has.
MAX_CHARS: Final[int] = 600

#: The output ceiling handed to the port, in tokens.
#:
#: **Derived from ``MAX_CHARS`` at the worst measured tokens-per-character, so
#: no script is truncated where another is not.** ``half.model.budget`` measured
#: 1,600 Japanese characters against 2,400 real tokens — three tokens for every
#: two characters — which is the top of the band for CJK, Thai and the Indic
#: scripts. Six hundred characters at that rate is nine hundred tokens, and this
#: sits above it. A ceiling sized on English prose would have cut a Thai morning
#: off mid-sentence while an English one of the same length fitted, which is the
#: shape of failure this tree has shipped before.
MAX_OUTPUT_TOKENS: Final[int] = 1_024

#: Ceilings for one generation and for one process's worth of them, in
#: millionths of a dollar.
#:
#: **The per-call figure is the one that binds**, and the port checks it against
#: an estimate *before the transport is touched*. The estimate charges the full
#: output ceiling in advance, so an ordinary morning prices well under this on
#: either tier and a pathological prompt is refused rather than sent.
#:
#: **The per-pass figure is a runaway stop, not a cost target.** Spending is
#: bounded by construction — at most ``ATTEMPTS`` generations per main per day,
#: with no loop, retry or schedule that could make a fourth.
PER_CALL_MICRO_USD: Final[int] = 100_000
PER_PASS_MICRO_USD: Final[int] = 500_000_000

#: How often the running counts are written out, in composed mornings, and the
#: silent-morning rate at which they are written out as an error instead. The
#: rate has to be *visible*, not merely reachable: a line per event tells an
#: operator that one morning was quiet, not that a third of them are failing.
REPORT_EVERY: Final[int] = 100
ALARM_RATE: Final[float] = 0.5
#: Below this many mornings a rate is arithmetic rather than evidence.
ALARM_AFTER: Final[int] = 10

#: Consecutive silent mornings that stand this main's composer down, and how
#: many mornings it stays down for. **Counted in mornings, not turns or
#: seconds**, because nothing here reads a clock (AD-30) and because a morning
#: is this path's natural unit — five is most of a week, which is the right
#: order for a provider outage and the wrong order for a per-turn breaker.
BREAK_AFTER: Final[int] = 5
BREAK_FOR: Final[int] = 20

#: The only public method a holder may have. An **allowlist**, inherited whole
#: from story 6d's review round: a denylist of names lets an object through that
#: can ``generate`` and also ``classify``, ``chat``, ``invoke`` or be called
#: directly. What this package needs is the port's narrow ``Generator``; what it
#: must not be handed is the provider that owns it, whose ledger it could reset
#: and whose batcher it could reach.
ALLOWED_METHODS: Final[frozenset[str]] = frozenset({"generate"})


# ── the judge's closed vocabulary ────────────────────────────────────────────

#: Nothing came back, or nothing but whitespace.
EMPTY: Final[str] = "empty"
#: Past ``MAX_CHARS``. One thing, not an essay.
TOO_LONG: Final[str] = "too-long"
#: The candidate carries Half's own internal serialization — a belief id, a
#: channel label, the context's stamp, or one of the prompt's block labels.
SCAFFOLDING: Final[str] = "scaffolding"
#: Two or more questions. CAP-4's *exactly one question* is the rule; this is
#: the half of it that is decidable in every script — see ``judge``.
TWO_QUESTIONS: Final[str] = "two-questions"

#: Every reason the judge may refuse a candidate. Closed, so a regeneration
#: carries a token from this set and never a sentence, and so a counter counts
#: constants rather than prose (AD-22).
REFUSALS: Final[frozenset[str]] = frozenset(
    {EMPTY, TOO_LONG, SCAFFOLDING, TWO_QUESTIONS}
)


#: Every question mark, in every script that has one.
#:
#: **Derived from a Unicode property, not from a list somebody wrote down.** The
#: entries are exactly the characters whose Unicode name contains ``QUESTION
#: MARK`` and whose category is ``Po`` — ordinary punctuation — which excludes
#: the mathematical operators, the emoji ornaments and the tag character that
#: share the phrase and are not sentence punctuation. ``tests/test_voice.py``
#: re-derives the set from ``unicodedata`` over the whole of Unicode and asserts
#: this constant equals it, so the constant is pinned to the *property* rather
#: than to whoever last edited it. The sweep lives in the test because it is a
#: million ``unicodedata.name`` lookups and this is an import.
#:
#: A denylist of ``?`` alone is exactly the defect this project has shipped
#: three times: it works in Latin and silently does nothing for a main writing
#: Arabic (``؟``), Greek (``;``), Armenian (``՞``), Amharic (``፧``) or Chinese
#: (``？``).
QUESTION_MARKS: Final[frozenset[str]] = frozenset(
    "?¿;՞؟፧᥅⁇⁉⳺⳻"
    "⸮⹔꘏꛷︖﹖？\U00011143\U0001e95f"
)


# ── what a composition comes to ──────────────────────────────────────────────

#: The context had nothing to say from. Ordinary: story 10 already answers this
#: before reaching here, and it is checked again because a caller that did not
#: is a caller paying a provider to write about nothing.
NOTHING_TO_SAY: Final[str] = "nothing-to-say"
#: No sample of the main's own language. Silence, never a default language.
NO_LANGUAGE: Final[str] = "no-language"
#: This main has no generator configured. A supported deployment, not a fault.
NO_MODEL: Final[str] = "no-model"
#: The breaker declined to try. Counted apart from the failures that tripped it.
STANDING_DOWN: Final[str] = "standing-down"
#: An attempt ran past ``BOUND_SECONDS``. Terminal: a provider that is slow now
#: is slow for the next attempt too, and a morning is not worth three bounds.
PAST_THE_BOUND: Final[str] = "past-the-bound"
#: The port refused on cost, before the transport was touched. Terminal for the
#: same reason — the second call costs exactly what the first one did.
OVER_BUDGET: Final[str] = "over-budget"
#: Every attempt came back as one of the port's failures.
REFUSED: Final[str] = "refused"
#: Every attempt was generated and refused by the judge.
JUDGED: Final[str] = "judged"
#: The holder raised instead of answering. A build mistake, not a provider
#: fault — the port answers a provider fault with a value.
RAISED: Final[str] = "raised"
#: The tripwire fired. Terminal, loud, and nothing is cleaned up.
LEAKED: Final[str] = leak.LEAKED

#: Every way a morning ends in silence. Closed, so ``half.surface.morning``
#: counts a constant and never a string a main's own ledger produced (AD-22).
SILENCES: Final[frozenset[str]] = frozenset(
    {
        NOTHING_TO_SAY, NO_LANGUAGE, NO_MODEL, STANDING_DOWN, PAST_THE_BOUND,
        OVER_BUDGET, REFUSED, JUDGED, RAISED, LEAKED,
    }
)


@dataclass(frozen=True, slots=True)
class Spoken:
    """A morning that has words. The text, and nothing else.

    It carries no reason, no attempt count and no usage, because every one of
    those would be a field beside a generated string in a value the caller might
    log. What an operator needs is on ``Tally``, in integers.
    """

    text: str


@dataclass(frozen=True, slots=True)
class Unspoken:
    """A morning with no words, and why (AD-27, AD-32).

    A typed outcome rather than an empty string, for AD-32's reason: one unit
    returning ``""`` for silence and another returning a reason leaves the
    metrics path with nothing to count. The reason is required and comes from
    ``SILENCES``.

    **Not a failure.** Most of these are ordinary — a deployment with no key, a
    quiet judge, a main with no sample yet. Two are not, and they are the ones
    the tally alarms on.
    """

    reason: str

    def __post_init__(self) -> None:
        if self.reason not in SILENCES:
            raise VoiceError(
                f"{self.reason!r} is not one of the reasons a morning can be "
                "silent. The set is closed so that a counter counts constants "
                "and never a message (AD-22)"
            )


Composed = Spoken | Unspoken


# ── the judge ────────────────────────────────────────────────────────────────


def scaffolding(context: Context) -> frozenset[str]:
    """Every internal token the wire must never carry, read off the context.

    **Derived from the serialization rather than from a list of expected
    strings**, which is this story's acceptance criterion word for word: *no
    label, belief id, or channel scaffolding — asserted against the
    serialization, not against a fixture's expected string.* A renamed channel
    label or a new item type changes ``render_line`` and changes this set with
    it; a hand-written list would go on passing while the thing it was written
    about had moved.

    Three kinds of token:

    * every item's **belief id**, which is what a main actually saw on the wire
      before this story — ``content[b_1]: has not walked that plot since March``;
    * every item's **rendered label**, up to and including the closing bracket,
      so ``content[b_1]`` is refused as a unit as well as ``b_1`` alone;
    * the context's own **stamp**, which is the ``now:`` line's whole payload.

    The prompt's four block labels join them, imported from
    ``half.voice.compose`` rather than respelled, so renaming one there cannot
    leave this scan looking for a word that no longer exists.
    """
    found: set[str] = {LANGUAGE_SAMPLE, MAY_BE_SAID, BE_MINDFUL_OF, ASK_ABOUT,
                       RETRY}
    if not isinstance(context, Context):
        return frozenset(found)
    if context.now:
        found.add(context.now)
    for item in context:
        if item.id:
            found.add(item.id)
        head, bracket, _ = render_line(item).partition("]")
        if bracket:
            found.add(head + bracket)
    return frozenset(token for token in found if token)


def judge(text: object, *, context: Context) -> str | None:
    """Whether this candidate may be sent, and if not, which rule refused it.

    ``None`` means accepted. Anything else is a token from ``REFUSALS`` — never
    a sentence, so a regeneration carries a reason without carrying prose and a
    counter counts a constant.

    **Four rules, and each of them is true or false in every script.** There is
    deliberately no rule about register, tone, warmth, sentence length or word
    choice: that is gbrain's rubric, it is written in English about English, and
    a product that ships worldwide cannot judge somebody's own language by it.
    The register instruction is given to the model once
    (``half.voice.compose.INSTRUCTIONS``) and is not adjudicated here.

    **Why there is no *"it must contain a question"* rule.** CAP-4's rule is
    *exactly one question*, and only one half of that is decidable across
    scripts. Two question marks are two questions in any script that has one.
    But *zero* question marks is not zero questions: written Japanese asks with
    か and a full stop, Thai with ไหม and no mark at all, and a great deal of
    spoken-register Chinese likewise. A rule requiring a mark would have
    rejected every correctly-composed Japanese and Thai morning while passing
    the English ones — which is story 12's negative-recognition defect exactly,
    reappearing on the other side of the same product. So the positive half is
    left to the instruction and the negative half is enforced here.
    """
    if not isinstance(text, str) or not text.strip():
        return EMPTY
    if len(text) > MAX_CHARS:
        return TOO_LONG
    if any(token in text for token in scaffolding(context)):
        return SCAFFOLDING
    if sum(1 for char in text if char in QUESTION_MARKS) > 1:
        return TWO_QUESTIONS
    return None


# ── the counts ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Tally:
    """What the voice has been doing, as counts (AD-22).

    Counts and nothing else. The keys are refusal names from ``REFUSALS``,
    silence reasons from ``SILENCES``, and ``kind/reason`` pairs from the port's
    two closed enums — so there is no field here a generated string, a claim or
    a main's own words could travel in. Held in memory, owned by the composition
    root, and never written to a main's log: the log records that a morning was
    sent, never what it said.
    """

    #: Mornings that reached a holder. The denominator of every rate below.
    composed: int = 0
    #: Generations actually attempted. Larger than ``composed`` when the judge
    #: sends one back, which is the number that says whether the judge is
    #: costing money.
    attempts: int = 0
    #: Mornings that came out with words.
    spoken: int = 0
    #: reason -> how many mornings ended silent that way. Keys from
    #: ``SILENCES``.
    silences: dict[str, int] = field(default_factory=dict)
    #: refusal -> how many *attempts* the judge sent back. Keys from
    #: ``REFUSALS``. Apart from ``silences`` because a refused attempt is not a
    #: silent morning: two of three may be refused and the morning still speaks.
    refusals: dict[str, int] = field(default_factory=dict)
    #: ``"kind/reason"`` -> how many times the port reported it.
    failures: dict[str, int] = field(default_factory=dict)
    #: Attempts abandoned at ``BOUND_SECONDS``. Its own counter rather than a
    #: transport fault, because *"the provider is slow"* and *"the provider is
    #: unreachable"* want different things done about them and the port's closed
    #: reason set has no room to say which.
    bound_exceeded: int = 0
    #: Attempts where the holder raised instead of returning one of the four
    #: failures. A build mistake — an unknown tier, a budget admitting nothing.
    raised: int = 0
    #: Answers this build could not read: neither a completion nor a failure.
    #: Kept apart from ``raised`` for story 6d's reason — a holder that threw
    #: and a provider that broke its own contract want different responses.
    unreadable: int = 0
    #: Mornings the breaker declined to compose. Outside every rate below: the
    #: breaker's whole job is to stop making calls, and counting its silence as
    #: failure would double-count one outage.
    skipped: int = 0

    @property
    def silent(self) -> int:
        return sum(self.silences.values())

    @property
    def silent_rate(self) -> float:
        """The number an operator watches. Zero composed mornings reads as zero
        rather than as an error, because a deployment with no key wired is a
        supported shape and not a fault."""
        return self.silent / self.composed if self.composed else 0.0

    @property
    def leaked(self) -> int:
        """Mornings the tripwire refused. The one count that is never ordinary:
        above zero it means either that a model echoed a withheld wording or
        that AD-18 has stopped being enforced at construction."""
        return self.silences.get(LEAKED, 0)

    def count_silence(self, reason: str) -> None:
        self.silences[reason] = self.silences.get(reason, 0) + 1

    def count_refusal(self, refusal: str) -> None:
        self.refusals[refusal] = self.refusals.get(refusal, 0) + 1

    def count_failure(self, failure: Failure) -> None:
        key = f"{failure.kind}/{failure.because}"
        self.failures[key] = self.failures.get(key, 0) + 1


# ── the voice ────────────────────────────────────────────────────────────────


class Voice:
    """The morning's words, or nothing.

    Holds one narrow ``Generator`` per main — narrow because the port's protocol
    has one method and no way to reach a ledger, a batch or a classifier, and
    per main because a self-hoster's key is stored under their own id (AD-11). A
    main with no holder gets ``Unspoken(NO_MODEL)``: no call, no count, and no
    message, which is the honest outcome for a deployment that has not equipped
    them. It is emphatically not a template.

    **Sealed after construction.** The holders are a read-only mapping and no
    attribute can be rebound, so the check that every holder is the narrow one
    cannot be walked around by assigning a wider one afterwards.
    """

    __slots__ = (
        "_holders", "_bound", "_attempts", "_tally", "_consecutive", "_quiet",
        "_sealed",
    )

    def __init__(
        self,
        holders: Mapping[str, Generator] | None = None,
        *,
        bound_seconds: float = BOUND_SECONDS,
        attempts: int = ATTEMPTS,
        tally: Tally | None = None,
    ) -> None:
        given = dict(holders or {})
        for main_id, holder in given.items():
            _check_holder(main_id, holder)
        if isinstance(bound_seconds, bool) or not isinstance(
            bound_seconds, (int, float)
        ) or bound_seconds <= 0:
            raise VoiceError(
                f"a bound of {bound_seconds!r} is not a bound. A generation "
                "that may run for ever is a scheduler slot held for ever, and "
                "the main whose morning it is never finds out"
            )
        if isinstance(attempts, bool) or not isinstance(attempts, int) or (
            attempts < 1
        ):
            raise VoiceError(
                f"{attempts!r} attempts composes nothing. The regenerations are "
                "bounded, not optional: a gate that never generates is a "
                "permanently silent Half wearing a budget's clothes"
            )
        self._holders: Mapping[str, Generator] = MappingProxyType(given)
        self._bound = float(bound_seconds)
        self._attempts = attempts
        self._tally = tally if tally is not None else Tally()
        #: main -> consecutive silent mornings, and main -> mornings to skip.
        self._consecutive: dict[str, int] = {}
        self._quiet: dict[str, int] = {}
        self._sealed = True

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise VoiceError(
                f"a voice is sealed after construction; rebinding {name!r} "
                f"would put a holder past the check that it can generate and "
                "do nothing else"
            )
        super().__setattr__(name, value)

    @property
    def tally(self) -> Tally:
        """The counts. Readable so an operator can see the silent rate."""
        return self._tally

    def holds(self, main_id: str) -> bool:
        """Whether this main has a voice available at all."""
        return main_id in self._holders

    async def compose(
        self,
        context: Context,
        *,
        main_id: str,
        sample: Sample,
        withheld: frozenset[str] | set[str] = frozenset(),
    ) -> Composed:
        """One morning's words, or a reason there are none. Never raises.

        ``context`` is what the builder already split under this main's ceiling;
        ``sample`` is their most recent words, for language only; ``withheld``
        is ``half.context.build.withheld`` over the same material, for the
        tripwire.

        The only things that leave this machine are the context's own quotable
        claims, its directives' structured topics, and the sample. Nothing else
        from the ledger reaches a payload, and ``main_id`` resolves the tier
        inside the port and appears in none.

        Every path out is a ``Composed``: there is no exception here that could
        reach the scheduler, and no branch that could return a template.

        ``CancelledError`` is deliberately not caught — it is a
        ``BaseException`` and shutdown is not a failed morning.
        """
        if not isinstance(context, Context) or not (
            context.content or context.question
        ):
            # Nothing quotable and nothing bought. Story 10 answers this before
            # reaching here; checked again because a caller that did not would
            # be paying a provider to write about nothing.
            return self._silent(main_id, NOTHING_TO_SAY, counted=False)
        if not isinstance(sample, Sample) or not sample.present:
            # No language to answer in. Silence rather than a default: choosing
            # one would be the locale inference this product does not do.
            return self._silent(main_id, NO_LANGUAGE, counted=False)
        holder = self._holders.get(main_id)
        if holder is None:
            return self._silent(main_id, NO_MODEL, counted=False)
        if self._breaking(main_id):
            return self._silent(main_id, STANDING_DOWN, counted=False)

        self._tally.composed += 1
        outcome = await self._attempt_all(
            context, holder=holder, main_id=main_id, sample=sample,
            withheld=withheld,
        )
        self._note(main_id, outcome)
        # On every path out, and that ordering is the point: a summary reached
        # only from the success path goes quiet exactly when the voice starts
        # failing, which looks identical to a product with nothing to say.
        self._report()
        return outcome

    async def _attempt_all(
        self,
        context: Context,
        *,
        holder: Generator,
        main_id: str,
        sample: Sample,
        withheld: frozenset[str] | set[str],
    ) -> Composed:
        """Generate, judge, regenerate, stop. The bounded loop.

        The judge's reason travels into the next attempt as a token from
        ``REFUSALS`` (``half.voice.compose.RETRY``), which is what makes a
        regeneration a *re*-generation rather than the same call made three
        times against a provider that is behaving deterministically. A sentence
        explaining what was wrong would be the English rubric this package is
        built without; a closed token is not one.
        """
        because = ""
        for _ in range(self._attempts):
            self._tally.attempts += 1
            work = Generate(
                prompt=prompt_for(
                    context, sample=sample, main_id=main_id, because=because
                ),
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            try:
                async with asyncio.timeout(self._bound):
                    answered = await holder.generate(work)
            except TimeoutError:
                # Past the bound. Terminal: a provider that is slow now is slow
                # for the next attempt too, and nobody is owed three bounds.
                self._tally.bound_exceeded += 1
                logger.warning(
                    "the morning composer passed its bound for main=%s; "
                    "nothing is sent", main_id,
                )
                return self._silent(main_id, PAST_THE_BOUND)
            except Exception as exc:
                # The port answers a provider fault with a value; a raise here
                # is a build mistake — an unknown tier, a budget admitting
                # nothing. **The class, and never the exception's own text**
                # (AD-22): a provider quotes the request it rejected, and the
                # request carries this main's claims and their own words.
                self._tally.raised += 1
                logger.warning(
                    "the morning composer could not run for main=%s (%s); "
                    "nothing is sent", main_id, type(exc).__name__,
                )
                return self._silent(main_id, RAISED)

            if isinstance(answered, Failure):
                self._tally.count_failure(answered)
                logger.warning(
                    "the morning composer did not answer for main=%s: %s/%s",
                    main_id, answered.kind, answered.because,
                )
                if answered.because in (
                    Reason.PER_CALL_BUDGET, Reason.PER_PASS_BUDGET
                ):
                    # Refused before the transport was touched, and the next
                    # call costs exactly what this one did.
                    return self._silent(main_id, OVER_BUDGET)
                because = ""
                continue
            if not isinstance(answered, Completion):
                self._tally.unreadable += 1
                logger.warning(
                    "the morning composer returned something this build cannot "
                    "read for main=%s", main_id,
                )
                because = ""
                continue

            refusal = judge(answered.text, context=context)
            if refusal is not None:
                self._tally.count_refusal(refusal)
                logger.debug(
                    "the morning composed for main=%s was refused: %s",
                    main_id, refusal,
                )
                because = refusal
                continue

            # The tripwire, and it is **not** a judge rule: a leak stops the
            # send rather than buying another attempt. Regenerating past one
            # would be a redaction with extra steps — the model would eventually
            # produce something clean, the send would succeed, and the broken
            # construction rule underneath it would stay invisible.
            if not leak.check(answered.text, withheld, main_id=main_id):
                return self._silent(main_id, LEAKED)

            self._tally.spoken += 1
            return Spoken(answered.text)

        return self._silent(main_id, JUDGED if because else REFUSED)

    def _silent(
        self, main_id: str, reason: str, *, counted: bool = True
    ) -> Unspoken:
        """One silent morning, counted.

        ``counted`` is false for the four answers reached *before* a holder was
        consulted — no material, no language, no model, standing down. Counting
        those in ``silences`` would make the rate a measurement of how many
        mains a deployment has equipped rather than of whether the composer is
        working, which is exactly the number an operator must not be given.
        ``skipped`` counts the breaker's own separately.
        """
        if reason == STANDING_DOWN:
            self._tally.skipped += 1
        elif counted:
            self._tally.count_silence(reason)
        return Unspoken(reason)

    # -- the breaker ---------------------------------------------------------

    def _breaking(self, main_id: str) -> bool:
        """Whether this main's composer is standing down. Counted, per main.

        During an outage every morning would otherwise pay three bounds and
        issue three doomed requests. After a run of silent mornings it stops
        asking for a while and then tries again — per main, because one main's
        provider being down says nothing about another's, and in mornings,
        because nothing here reads a clock (AD-30).
        """
        left = self._quiet.get(main_id, 0)
        if left <= 0:
            return False
        self._quiet[main_id] = left - 1
        return True

    def _note(self, main_id: str, outcome: Composed) -> None:
        """Record whether that morning spoke, and trip or clear the breaker."""
        if isinstance(outcome, Spoken):
            self._consecutive[main_id] = 0
            return
        run = self._consecutive.get(main_id, 0) + 1
        self._consecutive[main_id] = run
        if run < BREAK_AFTER:
            return
        self._consecutive[main_id] = 0
        self._quiet[main_id] = BREAK_FOR
        logger.error(
            "the morning composer produced nothing %d times running for "
            "main=%s and is standing down for %d mornings; that main gets no "
            "unprompted message until then", BREAK_AFTER, main_id, BREAK_FOR,
        )

    # -- what an operator sees ------------------------------------------------

    def _report(self) -> None:
        """Write the running counts out, every so often. Counts only (AD-22)."""
        if self._tally.composed % REPORT_EVERY == 0:
            self.flush()
        elif (
            self._tally.composed >= ALARM_AFTER
            and self._tally.silent_rate >= ALARM_RATE
            and self._tally.composed % ALARM_AFTER == 0
        ):
            self.flush(alarming=True)

    @property
    def quiet(self) -> bool:
        """Whether nothing has happened worth writing out.

        A deployment with no key is not an event, and a line of zeros at every
        shutdown is the noise that trains an operator to ignore the one line
        that matters.
        """
        return not (self._tally.composed or self._tally.skipped)

    def flush(self, *, alarming: bool = False) -> None:
        """Write the counts out now — periodically, above the alarm rate, and
        once at shutdown, so a wholly failing composer cannot be silent for as
        long as it takes to reach a round number.

        The two calls are spelled out rather than routed through a shared format
        string, because the guard that proves no log line here can carry content
        reads the **arguments of a logging call**: a message in a variable and a
        receiver in a local are both invisible to it, and an invisible log call
        is how content gets logged.
        """
        if self.quiet:
            return
        if alarming:
            logger.error(
                "morning voice: %d composed, %d attempts, %d spoken, %d silent "
                "(%d past the bound, %d unreadable, %d raised, %d leaked), "
                "%d skipped, by_reason=%s, refused=%s",
                self._tally.composed, self._tally.attempts, self._tally.spoken,
                self._tally.silent, self._tally.bound_exceeded,
                self._tally.unreadable, self._tally.raised, self._tally.leaked,
                self._tally.skipped, dict(sorted(self._tally.silences.items())),
                dict(sorted(self._tally.refusals.items())),
            )
        else:
            logger.info(
                "morning voice: %d composed, %d attempts, %d spoken, %d silent "
                "(%d past the bound, %d unreadable, %d raised, %d leaked), "
                "%d skipped, by_reason=%s, refused=%s",
                self._tally.composed, self._tally.attempts, self._tally.spoken,
                self._tally.silent, self._tally.bound_exceeded,
                self._tally.unreadable, self._tally.raised, self._tally.leaked,
                self._tally.skipped, dict(sorted(self._tally.silences.items())),
                dict(sorted(self._tally.refusals.items())),
            )


def _check_holder(main_id: str, holder: object) -> None:
    """Refuse anything that could do more than generate, at the boundary.

    A ``Generator`` is narrow because of what it lacks — no ledger to reset, no
    batcher to reach, no classifier to borrow. That guarantee is worth exactly
    what the check is that the object handed over really is one, and an
    allowlist is the only version of that check that holds: a denylist of names
    lets an ``AnthropicProvider`` through, and a provider is every method at
    once.
    """
    if not isinstance(holder, Generator):
        raise VoiceError(
            f"the holder for main {main_id!r} cannot generate; the voice takes "
            "the port's narrow generator and nothing else (AD-19)"
        )
    if callable(holder):
        raise VoiceError(
            f"the holder for main {main_id!r} is itself callable, which is a "
            "method by another name. The voice holds an object that can "
            "generate and do nothing else"
        )
    wider = sorted(
        name for name in dir(holder)
        if not name.startswith("_")
        and name not in ALLOWED_METHODS
        and callable(getattr(holder, name, None))
    )
    if wider:
        raise VoiceError(
            f"the holder for main {main_id!r} can also {', '.join(wider)}. The "
            "voice holds an object that can produce text and reach nothing "
            "else — that is the guarantee, and passing the provider that owns "
            "it quietly removes it. Hand over the narrow generator"
        )


def _check_constants() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    A guarantee that ``python -O`` removes is not a guarantee, and the ones this
    module exists to keep — *the loop is bounded*, *the fallback is silence*,
    *the reasons are closed* — are exactly the kind an optimisation flag would
    take away while the module still imported cleanly.
    """
    for name, value in (
        ("BOUND_SECONDS", BOUND_SECONDS), ("ATTEMPTS", ATTEMPTS),
        ("MAX_CHARS", MAX_CHARS), ("MAX_OUTPUT_TOKENS", MAX_OUTPUT_TOKENS),
        ("REPORT_EVERY", REPORT_EVERY), ("ALARM_AFTER", ALARM_AFTER),
        ("BREAK_AFTER", BREAK_AFTER), ("BREAK_FOR", BREAK_FOR),
        ("PER_CALL_MICRO_USD", PER_CALL_MICRO_USD),
    ):
        if value <= 0:
            raise VoiceError(f"{name} must be positive; {value!r} is not")
    if PER_CALL_MICRO_USD > PER_PASS_MICRO_USD:
        raise VoiceError("a per-call ceiling above the per-pass one never binds")
    if not REFUSALS or not SILENCES:
        raise VoiceError(
            "a closed set with nothing in it is not a closed set; it is a "
            "counter with nowhere to put anything"
        )
    if REFUSALS & SILENCES:
        raise VoiceError(
            f"{sorted(REFUSALS & SILENCES)} is both a reason to regenerate and "
            "a reason to give up. Those are different answers and a name that "
            "means both will eventually be read as the wrong one"
        )
    if LEAKED not in SILENCES:
        raise VoiceError(
            "a tripwire whose outcome is not a silence is a tripwire that lets "
            "the send through"
        )
    if "?" not in QUESTION_MARKS:
        raise VoiceError("a question-mark set without '?' in it is empty of use")
    stray = sorted(
        char for char in QUESTION_MARKS
        if unicodedata.category(char) != "Po"
        or "QUESTION MARK" not in unicodedata.name(char, "")
    )
    if stray:
        raise VoiceError(
            f"{stray} is in the question-mark set and is not a question mark by "
            "Unicode's own account. The set is derived from a property so that "
            "it cannot become a list of the marks somebody happened to know"
        )
    # A ceiling sized below the character bound at the worst measured rate would
    # truncate one script's morning and not another's — see MAX_OUTPUT_TOKENS.
    if MAX_OUTPUT_TOKENS * 2 < MAX_CHARS * 3:
        raise VoiceError(
            f"an output ceiling of {MAX_OUTPUT_TOKENS} tokens cannot hold "
            f"{MAX_CHARS} characters at three tokens for every two, which is "
            "what Japanese, Thai and the Indic scripts cost. A ceiling sized "
            "on Latin prose truncates every other script and nothing else"
        )


_check_constants()
