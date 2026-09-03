"""The turn, in words: prose, the claim alone, or nothing (CAP-1, CAP-11,
AD-27, AD-33).

Story 13a taught the morning to speak. This is the same composer, the same
judge, the same tripwire and the same counters, pointed at the surface a main
actually uses — and **it is deliberately not a second gate**. What differs
between a morning and a turn is three numbers-and-a-rule, all of them held here
so that ``half.voice.gate`` stays one implementation:

**The bound, because somebody is waiting.** A morning is unprompted and nobody
is holding a webhook open, so ``gate.BOUND_SECONDS`` is twenty and its job is to
protect a scheduler slot. Here the bound protects a *person*, inside AD-23's
five-second acknowledgement window, so it is the two seconds
``half.crisis.classifier`` and ``half.correction.candidate`` already use, for
their reason and not a new one.

**The fallback, because silence reads as broken.** The morning's answer to a
failed generation is silence and that is right there: nobody asked, and a quiet
day costs a main nothing. A main who has just written is waiting, so the same
answer would read as *Half is broken* rather than as *Half had nothing to say*.
The fallback is therefore **the claim alone, unscaffolded** — no label, no
belief id, no framing word, in any language. It is the main's own words, already
in their language, because it came from them; sending it degrades to *Half
echoes what it knows*, which is honest, rather than to *Half emits its
internals*, which is the blocker this story exists to close. A template is the
one thing this product cannot ship worldwide (``half.context.channels`` records
the objection); silence is kept for the case where there is nothing at all.

**And the top rung does not need anything quotable** (review loop 1). The
composer may write a reply shaped by the **directive channel alone**, quoting
none of it — so a turn with no `assert` material is prose rather than the
fallback, and the fallback is what a *failed generation* costs rather than what
a weak ledger costs. The first version of this module ranked those the other way
round and the arithmetic was brutal: `assert` requires a receipt *and* the main's
prior knowledge, so it is rare by design, and a main under a crisis-aftercare
ceiling has every license capped at `behave` for at least thirty days. Half met
them with silence on every message for a month, while CAP-12 says it stays
present. The rung was never the question — a directive shapes what is said and
is never quoted (AD-18), and ``half.voice.leak`` is already the alarm on that.

**The fallback is a branch that never entered the gate.** It is not *"whatever
``Voice.compose`` returns on failure"*: a main whose deployment has equipped
nobody, or whose provider is dead, must not wait for a model call to find out.
``holds`` is asked first, and where it answers no, nothing is awaited at all.

**The inclusion check, because CAP-11 is about verification.** A composed
correction reply must contain the removed claim verbatim, checked before it is
sent. Story 12's aim — the top-ranked belief above a relevance floor — can
mis-target, and the main is the only one who can catch that; they can only catch
it if they are shown the words. Prose that says *"I've taken that out"* without
saying *what* sounds better and verifies nothing. The check is
``half.correction.apply.shows``, and the fallback is
``half.correction.apply.shown`` — the claim alone — which satisfies it by
construction. The two are one function apart on purpose: a check and a fallback
that could disagree is a check that silences a main every time it fires.

**Whether the model's own prose went out is part of the answer** (``Turned``),
and that is story 11's rule arriving on this path. A favour was spent to ask a
question; if the fallback goes out instead, the question the favour paid for was
never asked, and the favour must not be consumed. *"No question line, no
spend"* becomes *"no composed prose, no spend"* — one comparison, not a flag
somebody has to keep true.

**Why there is no *"did the prose actually ask?"* test.** There cannot be one
that works worldwide. ``half.voice.gate.judge`` already refuses two question
marks in every script Unicode has, and deliberately does not require one,
because written Japanese asks with か and a full stop, Thai with ไหม and no mark
at all, and a great deal of spoken-register Chinese likewise. A rule that read
*zero marks* as *no question* would under-spend for exactly those mains and ask
them the same thing for ever — story 12's negative-recognition defect arriving
from the other side. What is decidable is whether the prose that carried the
question is what went on the wire, and that is what is answered here.

Pure over values plus one narrow ``Generator`` per main, exactly as the rest of
this package: no store, no channel, no clock. **No generated string is durable**
(AD-22) — what comes back is returned to the caller and counted, and there is no
field on ``Turned``, and no argument to any logging call here, that a completion
could travel in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from half.context.channels import Context
from half.errors import VoiceError
from half.voice.compose import Sample
from half.voice.gate import Spoken, Voice

#: Structured, and content-free. Every value logged from this module is a
#: ``main_id`` — never the prose, never the claim, never the main's own words.
logger = logging.getLogger(__name__)

__all__ = ["TURN_BOUND_SECONDS", "Turned", "fallback", "words"]


#: How long one attempt may run on a turn, in seconds.
#:
#: **Two, where the morning's is twenty, and the difference is who is waiting.**
#: ``half.voice.gate.BOUND_SECONDS`` protects a scheduler slot on a path where
#: nobody asked for anything. This one protects a person who has just written,
#: inside the five seconds AD-23 gives the inbound handler, so it is the number
#: ``half.crisis.classifier`` and ``half.correction.candidate`` already use on
#: the same turn — the same question answered the same way rather than a third
#: opinion about it.
#:
#: **It bounds the whole wait and not one third of it.** ``PAST_THE_BOUND`` is
#: terminal in the gate — a provider that is slow now is slow for the next
#: attempt too — so a dead provider costs one bound and then the fallback,
#: never three.
TURN_BOUND_SECONDS: Final[float] = 2.0


@dataclass(frozen=True, slots=True)
class Turned:
    """What a turn says, and whether the model is what wrote it.

    ``text`` is what goes on the wire; empty is silence, and silence is a
    first-class outcome (AD-27). ``composed`` is true only when the generator's
    own prose survived the tripwire, the judge and the inclusion check — so a
    caller that spent a favour on a question can tell whether the message
    carrying it is the one being sent.

    Two fields, and no third: no reason, no attempt count, no usage. Every one
    of those would be a field beside a generated string in a value a caller
    might log (AD-22). What an operator needs is on ``half.voice.gate.Tally``,
    in integers.
    """

    text: str = ""
    composed: bool = False

    @property
    def silent(self) -> bool:
        """Whether nothing is sent. Ordinary, and never an error."""
        return not self.text


def fallback(context: Context | None, *, show: str = "") -> str:
    """The claim this turn falls back to, or ``""``. Never raises.

    **The claim alone**: no label, no belief id, no op name, no framing word, in
    any language. ``half.correction.apply.shown`` renders the same thing for a
    removal and is the value ``show`` carries, so there is one spelling of *"the
    claim alone"* in the tree rather than two that could drift.

    ``show`` wins when it is set, because a correction turn is about the belief
    that left rather than about whatever else this turn's ranking put on top.
    Otherwise it is the first claim the context licenses Half to state — the
    same door ``half.voice.compose.quotable_block`` opens, so a claim that could
    not reach the prompt cannot reach the wire this way either.

    ``""`` is the answer when there is nothing quotable and nothing removed, and
    that is the one case where a waiting main is answered with silence.
    """
    if isinstance(show, str) and show:
        return show
    if not isinstance(context, Context):
        return ""
    for claim in context.quotable():
        if claim:
            return claim
    return ""


async def words(
    voice: Voice | None,
    context: Context,
    *,
    main_id: str,
    sample: Sample,
    withheld: frozenset[str] | set[str],
    show: str = "",
) -> Turned:
    """One turn's words. Never raises, and never returns a template.

    The ladder, in order, and each rung is a rule the story states:

    1. **The fallback is computed first, before anything is awaited.** It is a
       pure function of what this turn already holds, so there is no arrangement
       of provider failures that can leave a waiting main with nothing when
       there was a claim to send.
    2. **A main with no holder is answered with no model call at all.** Not
       *"compose and read the reason"*: a deployment that has equipped nobody
       must not put a bound, a breaker tick or an await in front of somebody's
       reply to find out what it already knows.
    3. **Otherwise the gate decides**, with the turn's own bound. Everything
       inside it — the tripwire, the judge, the regenerations, the counters — is
       ``half.voice.gate``'s and is not repeated here.
    4. **A composed correction reply must show what it removed** (CAP-11).
       Failing that, the claim alone goes out, which shows it by construction.

    ``show`` is the removed claim for a correction turn and ``""`` for every
    other. It is both the inclusion requirement and the fallback, deliberately:
    a check and a fallback that could disagree is a check that silences a main
    every time it fires.

    ``sample`` on a turn is simply the message in hand — there is no fold to
    read it off, because the main is right there. It sets the language and
    cannot reach the quotable channel, which is structural rather than
    conventional: ``half.voice.compose.quotable_block`` takes a ``Context`` and
    there is no parameter on it a ``Sample`` could arrive through.
    """
    spare = fallback(context, show=show)
    if not isinstance(voice, Voice) or not voice.holds(main_id):
        # **No model, no wait** — and no ``compose`` call either. The reason is
        # not tidiness: ``compose`` would answer ``NO_MODEL`` without touching a
        # holder, so the two look identical from the outside, and the thing that
        # would not be identical is what a later story does to this branch. A
        # fallback reached only through the gate is a fallback that acquires the
        # gate's latency the first time somebody adds a step to it.
        return Turned(spare)
    composed = await voice.compose(
        context,
        main_id=main_id,
        sample=sample,
        withheld=withheld,
        bound_seconds=TURN_BOUND_SECONDS,
        verbatim=show,
    )
    if not isinstance(composed, Spoken):
        return Turned(spare)
    if show and show not in composed.text:
        # CAP-11's whole point, and the one refusal in this module that is about
        # the *content* of what came back rather than about whether it came
        # back. Prose that says it removed something without saying what sounds
        # better than the claim and verifies nothing. Counted nowhere and logged
        # without a word of either string (AD-22).
        logger.info(
            "the composed reply for main=%s did not show the claim it removed; "
            "the claim alone is sent (CAP-11)", main_id,
        )
        return Turned(spare)
    return Turned(composed.text, composed=True)


def _check_constants() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    ``half.voice.gate`` gives the reason: a guarantee ``python -O`` removes is
    not a guarantee, and *the waiting main's bound is shorter than the
    unprompted one* is exactly the kind an optimisation flag would take away
    while the module still imported cleanly.
    """
    from half.voice.gate import BOUND_SECONDS

    if TURN_BOUND_SECONDS <= 0:
        raise VoiceError(
            f"a turn bound of {TURN_BOUND_SECONDS!r} is not a bound. A "
            "generation that may run for ever is a main waiting for ever, with "
            "a reply already computed that nobody sends"
        )
    if TURN_BOUND_SECONDS > BOUND_SECONDS:
        raise VoiceError(
            f"the turn bound is {TURN_BOUND_SECONDS} seconds and the morning's "
            f"is {BOUND_SECONDS}. A turn has somebody waiting on it and a "
            "morning does not, so the turn's bound is the shorter one or it is "
            "not doing the job it exists for"
        )


_check_constants()
