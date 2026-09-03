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
down after a run of failures, and a tally an operator can read.

*Two of the numbers differ from the crisis path's because the situation does*:
nobody is waiting for a morning, so ``BOUND_SECONDS`` is generous where a turn's
must be short, and a morning happens once a day, so ``BREAK_AFTER`` and
``BREAK_FOR`` count mornings rather than turns. **The two ceilings are
byte-identical to the crisis and correction ones and that is not a coincidence
worth dressing up** — an earlier version of this paragraph claimed all the
numbers differed, which was true of two and false of two. They are the same
because they are answering the same question (*what is an absurd amount to spend
on one call, and on one process*) and nobody has yet had a reason to answer it
differently here. If a reason appears, the number moves; until then the honest
account is that a third module repeats a figure, which is one more argument for
the extraction recorded at the end of this docstring.

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

**What nothing here checks: that the morning is true.**

The judge asks four things and none of them is about provenance. The tripwire
asks one thing and it is about *withheld* wordings — text the ladder said Half
may not say. **Neither asks whether what the model wrote is in the may-be-said
block at all.** A completion that invents a claim the main never made, or that
takes a real claim and states it more strongly than the evidence does, passes
every gate in this package and reaches the wire.

That is named here rather than left to be discovered, because it is in tension
with something the product says about itself. The constitution's *assert only
with receipts* is the reason ``quotable_block`` drops belief ids — a citation is
what makes a statement checkable — and this module is where the citation stops
being enforceable, because a sentence a model wrote has no id on it any more.

It is an accepted cost of composing with a model at all, and the alternatives
were weighed rather than skipped. A groundedness *judge* would be a second model
call per attempt, doubling the cost and the latency of every morning to ask a
question the first model already got wrong. A verbatim-quotation rule — the
morning must contain a quotable claim word for word — would make Half unable to
write a natural sentence in any language whose grammar inflects the claim, which
is most of them, and would land on AD-18's second named failure from a new
direction. An entailment check needs a model too.

**Two things bound the damage, and neither removes it.** The material a morning
is built from is narrow: `assert` claims the ladder admitted, under this main's
ceiling, from the candidates last night's pass produced — so an invention is an
invention *around* one true thing rather than out of nothing. And the outcome is
one message a day to one person who knows their own life, which is the cheapest
possible place for a wrong sentence to land: they can say *that's wrong*, and
CAP-11 exists so that saying it changes what Half holds.

**Deferred, deliberately, and not to be built quietly.** A groundedness check is
a second judge with its own failure modes, its own cost model and its own
worldwide rubric problem, and story 13a's scope is the wire text. When it is
built it belongs with the turn reply (13b), where a main is waiting and the
material is wider, and it needs its own story rather than a commit.

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

from half.context.channels import Context, render_line, sanitize
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
    MAX_CHARS,
    MAX_OUTPUT_TOKENS,
    MAY_BE_SAID,
    RETRY,
    WORD_FOR_WORD,
    Sample,
    prompt_for,
    quotable_block,
)

#: Structured, and content-free. Every value logged from this module is a closed
#: enum, a count, an exception's class name, or a ``main_id`` — never a prompt,
#: a completion, a claim or a main's own words (AD-22).
logger = logging.getLogger(__name__)

__all__ = [
    "ALARM_AFTER", "ALARM_RATE", "ALLOWED_METHODS", "ATTEMPTS",
    "BOUND_SECONDS", "BREAK_AFTER", "BREAK_FOR", "Composed", "EMPTY",
    "FAULTS", "JUDGED", "LEAKED", "MAX_CHARS", "MAX_OUTPUT_TOKENS",
    "NOTHING_QUOTABLE", "NO_LANGUAGE", "NO_MODEL", "OVER_BUDGET",
    "PAST_THE_BOUND",
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

#: ``MAX_CHARS`` and ``MAX_OUTPUT_TOKENS`` are ``half.voice.compose``'s, not
#: this module's, and the move is review round 1's. The judge enforces the
#: character bound and the port is handed the token ceiling, but the *model is
#: told* the character bound — and a constant the instructions interpolate has
#: to live beside the instructions or the two drift, which is how a model that
#: habitually writes seven hundred characters burned all three attempts and
#: silenced a main for ever with nothing anywhere saying why. Re-exported below
#: so every existing reader is unaffected.

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

#: The context had nothing quotable and no bought question. Ordinary: story 10
#: already answers this before reaching here, and it is checked again because a
#: caller that did not is a caller paying a provider to write about nothing.
#:
#: **Spelled differently from ``half.surface.morning.NOTHING_TO_SAY`` on
#: purpose**, which is review round 1's correction: the two carried the same
#: string, so ``Mornings.silences`` merged *"the night's pass produced no
#: candidate"* with *"the composer was handed an empty context"* under one
#: number — and the second is not an ordinary quiet night, it is the surface
#: having built an empty context and paid to find out.
NOTHING_QUOTABLE: Final[str] = "nothing-quotable"
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

#: The two silences that are faults in **this build** rather than a provider
#: being unavailable.
#:
#: **They never arm the breaker**, and review round 1 found why that matters.
#: ``_note`` used to arm on any non-``Spoken`` outcome, so five consecutive
#: leaks stood the main down for twenty mornings — during which ``leak.check``
#: was never reached, no ``error`` was logged and ``Tally.leaked`` stopped
#: rising. A live AD-18 breach would have gone quiet for twenty of every
#: twenty-five mornings: an alarm with a snooze button wired to the alarm.
#:
#: The breaker exists to stop paying a provider that is down. A leak means the
#: provider answered perfectly and *this build* is wrong; a raise means the port
#: was handed something it cannot run. Neither is an outage, neither gets
#: quieter by waiting, and both are logged every single time they happen, which
#: is what an operator needs instead.
#:
#: Read by ``half.surface.morning.FAULTS`` rather than spelled again there, so a
#: reason added here cannot become a fault this build forgets to treat as one.
FAULTS: Final[frozenset[str]] = frozenset({LEAKED, RAISED})

#: Every way a morning ends in silence. Closed, so ``half.surface.morning``
#: counts a constant and never a string a main's own ledger produced (AD-22).
SILENCES: Final[frozenset[str]] = frozenset(
    {
        NOTHING_QUOTABLE, NO_LANGUAGE, NO_MODEL, STANDING_DOWN, PAST_THE_BOUND,
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
            # **The rejected value is deliberately not in the message**, which
            # is review round 1's finding and a hole in the rule this guard
            # exists to keep: a caller that reached here with a string out of a
            # main's own ledger would have had it interpolated into an exception
            # somebody logs. What an operator needs is the closed set, and every
            # member of it is a constant in this module (AD-22).
            raise VoiceError(
                "a morning's silence carries a reason from a closed set, and "
                f"this one is not in it. The set is {sorted(SILENCES)}. The "
                "value is not repeated here: it came from a caller, and a "
                "caller on this path holds a main's own words"
            )


Composed = Spoken | Unspoken


# ── the judge ────────────────────────────────────────────────────────────────


#: The shortest token the scaffolding rule will refuse.
#:
#: Review round 1's finding: a belief id or a stamp fragment short enough to
#: occur in ordinary prose refuses **every** attempt, for ever, for that main —
#: a permanently silent Half with a green suite. Ids are ``b_<hex>``, so three
#: characters is the shortest one this build can mint and the bound costs
#: nothing real; what it buys is that a degenerate one-or-two-character id
#: cannot silence somebody. The trade is named rather than hidden: a token that
#: short is not a scaffolding signal, because it is not distinctive enough to be
#: evidence of anything.
MIN_SCAFFOLDING_CHARS: Final[int] = 3


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

    The prompt's five block labels join them, imported from
    ``half.voice.compose`` rather than respelled, so renaming one there cannot
    leave this scan looking for a word that no longer exists.

    **Two things are then removed, and both are review round 1's.** A token
    shorter than ``MIN_SCAFFOLDING_CHARS`` is dropped, because a token that
    short can occur in prose and would refuse every attempt for ever. And a
    token that appears **inside the quotable block** is dropped, because the
    model was given that text and told it may state it: refusing the candidate
    for repeating something Half handed it is the same permanent silence
    arriving from the other side. Both losses are in the safe direction — the
    thing the rule exists to catch is Half's own serialization, and neither a
    two-character token nor a string the main's own `assert` claim contains is
    evidence of that.
    """
    labels = {
        LANGUAGE_SAMPLE, MAY_BE_SAID, BE_MINDFUL_OF, ASK_ABOUT, WORD_FOR_WORD,
        RETRY,
    }
    if not isinstance(context, Context):
        return frozenset(labels)
    found: set[str] = set(labels)
    if context.now:
        found.add(context.now)
    for item in context:
        if item.id:
            found.add(item.id)
        head, bracket, _ = render_line(item).partition("]")
        if bracket:
            found.add(head + bracket)
    said = quotable_block(context)
    return frozenset(
        token for token in found
        if len(token) >= MIN_SCAFFOLDING_CHARS and token not in said
    )


def question_budget(context: Context) -> int:
    """How many question marks a candidate may carry.

    One — the question CAP-4 permits — **plus however many the model was handed
    in the quotable block**, which is review round 1's correction and a
    permanent-silence route in its own right: an `assert` claim that itself ends
    in a question mark (*"asked whether the fence was ever mended?"*) makes a
    faithful quotation of it look like a second question, every attempt refuses,
    and that main never hears anything again.

    Counting the marks the model was given rather than trying to tell a quoted
    mark from an asked one is deliberate: telling them apart needs to know where
    the quotation ends, which is a parse of somebody's prose in an unknown
    language. Counting what was handed over is arithmetic, and it errs toward
    permitting — which is the right direction here, because the thing being
    guarded against is an *interview*, and one extra mark is not one.
    """
    if not isinstance(context, Context):
        return 1
    return 1 + sum(1 for char in quotable_block(context) if char in QUESTION_MARKS)


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

    **Neither rule can silence a main for ever**, which review round 1 found
    both of them could: see ``question_budget`` and ``scaffolding``.
    """
    if not isinstance(text, str) or not text.strip():
        return EMPTY
    if len(text) > MAX_CHARS:
        return TOO_LONG
    if any(token in text for token in scaffolding(context)):
        return SCAFFOLDING
    marks = sum(1 for char in text if char in QUESTION_MARKS)
    if marks > question_budget(context):
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
        withheld: frozenset[str] | set[str],
        bound_seconds: float | None = None,
        verbatim: str = "",
    ) -> Composed:
        """One send's words, or a reason there are none. Never raises.

        ``context`` is what the builder already split under this main's ceiling;
        ``sample`` is their most recent words, for language only; ``withheld``
        is ``half.context.build.withheld`` over the same material, for the
        tripwire.

        **``withheld`` is required and has no default**, which is review round
        1's correction and the same rule ``half.context.build.resolve`` makes
        about its ``ceiling``: a caller who forgot it got a tripwire that
        answered *"no leak"* on an empty set, so AD-18's smoke alarm could be
        switched off by omission and nothing would say it had been. Forgetting
        it is now a ``TypeError`` at the call site.

        The only things that leave this machine are the context's own quotable
        claims, its directives' structured topics, and the sample. Nothing else
        from the ledger reaches a payload, and ``main_id`` resolves the tier
        inside the port and appears in none.

        Every path out is a ``Composed``: there is no exception here that could
        reach the scheduler, and no branch that could return a template.

        ``bound_seconds`` overrides the construction bound **for this call
        only**, and exists so that story 13b's turn can share this gate rather
        than fork it. A morning has nobody waiting and a turn has somebody
        waiting, which is one number's worth of difference — and the manifest's
        own argument for taking gbrain's row was that *tuning belongs in one
        rubric rather than in forked gate implementations*. A second ``Voice``
        for the turn would be a second tally, a second breaker and a second
        holder check, which is three ways for the two to drift.

        **An unusable value falls back to the construction bound rather than
        raising**, because this method never raises and a main's reply must not
        depend on an argument being well formed. It is logged, so it cannot be
        silent. The only caller that passes one reads a module constant checked
        at import (``half.voice.turn``), so the branch is a guard rather than a
        path.

        ``verbatim`` is the one string the composition must carry unchanged, and
        it is empty everywhere but a correction turn
        (``half.voice.compose.WORD_FOR_WORD``). **It is told to the model and
        not adjudicated here**, which is deliberate and is the same split the
        register instruction gets: a judge rule would make a paraphrase cost
        three attempts and three bounds in front of somebody who is waiting,
        for an outcome — the claim alone — that ``half.voice.turn`` already has
        in hand before the first call. The requirement is checked once, at the
        one place that can act on it, immediately before the send.

        ``CancelledError`` is deliberately not caught — it is a
        ``BaseException`` and shutdown is not a failed send.
        """
        # **The breaker's clock is mornings, and it ticks on every one of
        # them.** Review round 1 found it decremented only on mornings that
        # reached a holder, so a main stood down for twenty mornings and then
        # having a quiet fortnight stayed silent for a month and a half. The
        # countdown runs first; what it means is decided below, so a quiet
        # morning during a stand-down is still reported as the quiet morning it
        # was rather than as a stand-down.
        standing_down = self._tick_breaker(main_id)

        if not isinstance(context, Context) or not (
            context.content or context.question
        ):
            # Nothing quotable and nothing bought. Story 10 answers this before
            # reaching here; checked again because a caller that did not would
            # be paying a provider to write about nothing.
            return self._silent(main_id, NOTHING_QUOTABLE, counted=False)
        if not isinstance(sample, Sample) or not sample.present:
            # No language to answer in. Silence rather than a default: choosing
            # one would be the locale inference this product does not do.
            return self._silent(main_id, NO_LANGUAGE, counted=False)
        holder = self._holders.get(main_id)
        if holder is None:
            return self._silent(main_id, NO_MODEL, counted=False)
        if standing_down:
            self._tally.skipped += 1
            return Unspoken(STANDING_DOWN)

        self._tally.composed += 1
        outcome = await self._attempt_all(
            context, holder=holder, main_id=main_id, sample=sample,
            withheld=withheld, bound=self._bound_for(main_id, bound_seconds),
            verbatim=verbatim,
        )
        self._note(main_id, outcome)
        # On every path out, and that ordering is the point: a summary reached
        # only from the success path goes quiet exactly when the voice starts
        # failing, which looks identical to a product with nothing to say.
        self._report()
        return outcome

    def _bound_for(self, main_id: str, given: float | None) -> float:
        """The wall-clock bound for one call. The construction one unless a
        caller asked for another, and never a value that is not a bound.

        A refusal here would cost a main their reply for a mistake in an
        argument, which is the one thing this class does not do — so an
        unusable value is logged and the construction bound stands. The number
        itself is not repeated in the line: it came from a caller, and the log
        on this path carries counts and ids only (AD-22).
        """
        if given is None:
            return self._bound
        if isinstance(given, bool) or not isinstance(given, (int, float)) or (
            given <= 0
        ):
            logger.warning(
                "the composer was given a bound it cannot use for main=%s; the "
                "one it was built with stands", main_id,
            )
            return self._bound
        return float(given)

    async def _attempt_all(
        self,
        context: Context,
        *,
        holder: Generator,
        main_id: str,
        sample: Sample,
        withheld: frozenset[str] | set[str],
        bound: float,
        verbatim: str = "",
    ) -> Composed:
        """Generate, judge, regenerate, stop. The bounded loop.

        **The whole attempt is inside the handler**, which is review round 1's
        correction to a guarantee this module's docstring stated absolutely and
        held by accident. ``prompt_for`` can raise ``BreakpointError`` from
        ``Prompt.__post_init__``; ``judge`` calls ``render_line`` on every item
        and normalizes arbitrary text; ``leak.check`` folds strings out of a
        main's own ledger. All three ran outside the ``try``, so *"never
        raises"* depended on none of them ever being wrong — and an exception
        out of here reaches ``MorningSurface._counted``, costs the main their
        morning, and is counted as an unreadable record rather than as what it
        is.

        ``because`` is the judge's reason for the previous attempt, and travels
        into the next prompt as a token from ``REFUSALS``
        (``half.voice.compose.RETRY``). That is what makes a regeneration a
        *re*-generation rather than the same call made three times against a
        provider behaving deterministically. A sentence explaining what was
        wrong would be the English rubric this package is built without; a closed
        token is not one.

        ``terminal`` is the reason a *run* of attempts ends on, tracked
        explicitly rather than inferred from whether ``because`` happens to be
        set. Review round 1: deleting ``because = ""`` from the failure branch
        changed a provider outage into a reported judge refusal and no test
        noticed, because the two facts were being carried by one variable.
        """
        because = ""
        terminal = REFUSED
        for _ in range(self._attempts):
            self._tally.attempts += 1
            try:
                work = Generate(
                    prompt=prompt_for(
                        context, sample=sample, main_id=main_id,
                        because=because, verbatim=verbatim,
                    ),
                    max_tokens=MAX_OUTPUT_TOKENS,
                )
                async with asyncio.timeout(bound):
                    answered = await holder.generate(work)

                if isinstance(answered, Failure):
                    self._tally.count_failure(answered)
                    logger.warning(
                        "the composer did not answer for main=%s: %s/%s",
                        main_id, answered.kind, answered.because,
                    )
                    if answered.because in (
                        Reason.PER_CALL_BUDGET, Reason.PER_PASS_BUDGET
                    ):
                        # Refused before the transport was touched, and the next
                        # call costs exactly what this one did.
                        return self._silent(main_id, OVER_BUDGET)
                    because, terminal = "", REFUSED
                    continue
                if not isinstance(answered, Completion):
                    self._tally.unreadable += 1
                    logger.warning(
                        "the composer returned something this build cannot "
                        "read for main=%s", main_id,
                    )
                    because, terminal = "", REFUSED
                    continue

                # **Sanitized with the context's own function**, not a second
                # one. Every item in a constructed context is neutralized at
                # construction so that no text can begin a line or steer a
                # terminal; a completion is the one string on this path that had
                # never been, so control characters and line separators went
                # straight to the channel. Format characters (``Cf`` — ZWJ,
                # ZWNJ, the bidi marks) are deliberately kept, for the reason
                # ``half.context.channels`` gives: they are meaningful inside
                # Indic and Arabic words and stripping them would damage the
                # scripts this product exists to reach. The consequence worth
                # naming is that a morning becomes one paragraph, which is what
                # *at most one thing* already meant.
                text = sanitize(answered.text)

                # **The tripwire runs before the judge**, which is review round
                # 1's correction and not a tidy-up. A draft that both leaked and
                # ran long used to be refused for *length*, regenerated away,
                # and the breach never counted and never logged — the alarm
                # losing to a spelling check. A leak is not a quality problem to
                # be regenerated past, so it is asked first and it is terminal.
                if not leak.check(text, withheld, main_id=main_id):
                    return self._silent(main_id, LEAKED)

                refusal = judge(text, context=context)
                if refusal is not None:
                    self._tally.count_refusal(refusal)
                    logger.debug(
                        "the text composed for main=%s was refused: %s",
                        main_id, refusal,
                    )
                    because, terminal = refusal, JUDGED
                    continue

                self._tally.spoken += 1
                return Spoken(text)
            except TimeoutError:
                # Past the bound. Terminal: a provider that is slow now is slow
                # for the next attempt too, and nobody is owed three bounds.
                self._tally.bound_exceeded += 1
                logger.warning(
                    "the composer passed its bound for main=%s; "
                    "nothing is sent", main_id,
                )
                return self._silent(main_id, PAST_THE_BOUND)
            except Exception as exc:
                # The port answers a provider fault with a value; a raise here
                # is a build mistake — an unknown tier, a budget admitting
                # nothing, a breakpoint past the prompt, a guard this build got
                # wrong. **The class, and never the exception's own text**
                # (AD-22): a provider quotes the request it rejected, and the
                # request carries this main's claims and their own words.
                self._tally.raised += 1
                logger.warning(
                    "the composer could not run for main=%s (%s); "
                    "nothing is sent", main_id, type(exc).__name__,
                )
                return self._silent(main_id, RAISED)

        return self._silent(main_id, terminal)

    def _silent(self, main_id: str, reason: str, *, counted: bool = True) -> Unspoken:
        """One silent morning, counted.

        ``counted`` is false for the three answers reached *before* a holder was
        consulted — no material, no language, no model. Counting those in
        ``silences`` would make the rate a measurement of how many mains a
        deployment has equipped rather than of whether the composer is working,
        which is exactly the number an operator must not be given. The breaker's
        own skip is counted separately, in ``skipped``, and outside every rate.
        """
        if counted:
            self._tally.count_silence(reason)
        return Unspoken(reason)

    # -- the breaker ---------------------------------------------------------

    def _tick_breaker(self, main_id: str) -> bool:
        """Spend one morning of this main's stand-down, and say whether it is on.

        During an outage every morning would otherwise pay three bounds and
        issue three doomed requests. After a run of silent mornings it stops
        asking for a while and then tries again — per main, because one main's
        provider being down says nothing about another's, and in mornings,
        because nothing here reads a clock (AD-30).

        **The tick is separated from the decision**, which is review round 1's
        correction. This used to be called after the material, language and
        holder checks, so the countdown only advanced on mornings that had
        something to say — and a main stood down for twenty mornings who then
        had a quiet fortnight stayed silent for a month and a half. *Mornings*
        is the unit, and every morning is one, including the quiet ones.
        """
        left = self._quiet.get(main_id, 0)
        if left <= 0:
            return False
        self._quiet[main_id] = left - 1
        return True

    def _note(self, main_id: str, outcome: Composed) -> None:
        """Record whether that morning spoke, and trip or clear the breaker.

        **A fault neither arms it nor clears it**, and that is the whole of
        review round 1's first finding: a leak used to arm the breaker, so five
        consecutive AD-18 breaches bought twenty mornings during which the
        tripwire was never reached, nothing was logged at ``error`` and
        ``Tally.leaked`` stopped rising. See ``FAULTS``.

        Neutral rather than clearing, because a leak says nothing about whether
        the provider is up: a run of transport failures interrupted by one leak
        is still a run of transport failures.
        """
        if isinstance(outcome, Unspoken) and outcome.reason in FAULTS:
            return
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
        """Write the running counts out, every so often. Counts only (AD-22).

        **The alarm is asked first**, which is review round 1's correction. With
        the periodic branch first and the alarm on the ``elif``, the two were
        exclusive — so at the hundredth, two hundredth and every hundredth
        morning after, a wholly failing composer reported at ``info`` instead of
        ``error``. The one line an operator is watching for went missing exactly
        at the round numbers they would look at.
        """
        if (
            self._tally.composed >= ALARM_AFTER
            and self._tally.silent_rate >= ALARM_RATE
            and self._tally.composed % ALARM_AFTER == 0
        ):
            self.flush(alarming=True)
        elif self._tally.composed % REPORT_EVERY == 0:
            self.flush()

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
