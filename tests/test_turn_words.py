"""Story 13b: the turn, in words — what a main actually receives.

``tests/test_voice.py`` and ``tests/test_morning_words.py`` carry story 13a's
composer and the morning it writes. This file carries the **turn** — the surface
a main uses, where before this story ``respond`` answered ``"noted. has not
walked that plot since March"``, a bought question arrived as
``question[b_1] topic: farmland``, and a correction arrived as
``retract[b_land]: has not walked that plot since March``.

**The fallback ladder is the subject, and it is asserted rung by rung.** A main
who has just written is waiting, so silence reads as broken rather than as
quiet — the asymmetry that makes 13a's answer wrong here. Every rung below is a
separate case: prose when the composer works, the claim alone when it does not,
and silence only when there is no claim.

**The fallback must be reachable with no model call**, so the cases that assert
it use a holder that *counts* rather than one that raises. Story 13a's review
found why: ``Voice._attempt_all`` catches ``Exception`` and turns an
``AssertionError`` into ``Unspoken(RAISED)``, which is a legal outcome — so a
double whose only signal is a raise passes whether or not the provider was
reached. Every *"never called"* and every ordering below is a counter asserted
to be zero, or a call count asserted to be one.

**Nothing here is a fixture string.** *"No label, no belief id, no
scaffolding"* is asserted by rendering the context the turn actually built and
looking for its own output on the wire, exactly as story 13a's file does.

Offline throughout: every holder is the port's narrow ``Generator``, stubbed,
and nothing here opens a socket.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Final

import pytest

from half.context.build import build as build_context
from half.context.build import withheld as withheld_wordings
from half.context.channels import Context, render_line
from half.governance.ladder import Ceiling, License
from half.model.port import Failure, Kind, Reason
from half.retrieval.port import Candidate as RankedBelief
from half.voice.compose import (
    ASK_ABOUT,
    MAY_BE_SAID,
    WORD_FOR_WORD,
    Sample,
)
from half.voice.gate import BOUND_SECONDS, Voice
from half.voice.turn import TURN_BOUND_SECONDS, Turned, fallback, words

from tests.conftest import GeneratorDouble, NeverGenerates

pytestmark = [pytest.mark.cap1_turn]

MAIN = "vidit"
OTHER = "asha"
NOW = "2026-09-03T09:00:00Z"

#: The `assert` claim a turn may state, and the `behave` claim it may not. They
#: share no adjacent word pair, so the builder admits the first — see
#: ``half.context.build``'s withholding rule.
SAYABLE: Final[str] = "has not walked that plot since March"
WITHHELD: Final[str] = "avoids the conversation with his brother"

#: The main's own message, in fourteen writing systems. On a turn the language
#: sample is simply the message in hand, so this is what sets the language — and
#: the rule that reads it must not be a rule that only notices Latin.
SCRIPTS: Final[dict[str, str]] = {
    "latin": "that is not right any more",
    "devanagari": "अब यह सही नहीं है",
    "thai": "ตอนนี้มันไม่ถูกแล้ว",
    "japanese": "それはもう違う",
    "han": "那个现在不对了",
    "hangul": "그건 이제 아니야",
    "arabic": "هذا لم يعد صحيحا",
    "hebrew": "זה כבר לא נכון",
    "cyrillic": "это больше не так",
    "greek": "αυτό δεν ισχύει πια",
    "bengali": "এটা আর ঠিক নেই",
    "tamil": "இது இப்போது சரியில்லை",
    "amharic": "ይህ ከእንግዲህ ትክክል አይደለም",
    "khmer": "នេះលែងត្រូវហើយ",
}

#: A claim in each of the same fourteen, so that *"the fallback is the claim
#: alone, unchanged"* is asserted for a script whose text a naive normalizer
#: would damage — a Devanagari matra, a Khmer dependent vowel, an Arabic
#: presentation form.
CLAIMS: Final[dict[str, str]] = {
    "latin": "has not walked that plot since March",
    "devanagari": "मार्च से उस खेत पर नहीं गया",
    "thai": "ไม่ได้ไปที่ไร่นั้นตั้งแต่เดือนมีนาคม",
    "japanese": "三月からあの畑に行っていない",
    "han": "从三月起就没去过那块地",
    "hangul": "삼월부터 그 밭에 가지 않았다",
    "arabic": "لم يزر تلك الأرض منذ مارس",
    "hebrew": "לא ביקר בחלקה מאז מרץ",
    "cyrillic": "не был на том участке с марта",
    "greek": "δεν πήγε στο χωράφι από τον Μάρτιο",
    "bengali": "মার্চ থেকে সেই জমিতে যাননি",
    "tamil": "மார்ச் முதல் அந்த நிலத்திற்குச் செல்லவில்லை",
    "amharic": "ከመጋቢት ጀምሮ ወደዚያ መሬት አልሄደም",
    "khmer": "មិនបានទៅចម្ការនោះតាំងពីខែមីនា",
}


# ── fixtures over the real builder ───────────────────────────────────────────


def candidate(ident, claim, *, rung=License.ASSERT, **fields):
    belief = {"license": str(rung), "subject": "self", **fields}
    if rung is License.ASSERT:
        belief.setdefault("support", ["s_1"])
        belief.setdefault("known_to_main", True)
    return RankedBelief(id=ident, claim=claim, prefix="", bm25=None,
                        belief=belief)


def material(sayable=SAYABLE):
    return [
        candidate("b_1", sayable),
        candidate("b_2", WITHHELD, rung=License.BEHAVE, topics=["family"]),
    ]


def a_context(*candidates, bought=None) -> Context:
    return build_context(candidates, now=NOW, ceiling=Ceiling(), bought=bought)


def ordinary(sayable=SAYABLE) -> Context:
    return a_context(*material(sayable))


def ordinary_withheld(sayable=SAYABLE) -> frozenset[str]:
    return withheld_wordings(material(sayable), ceiling=Ceiling())


def a_voice(*answers, main=MAIN, sleep=0.0, bound_seconds=0.5, **kw):
    """A ``Voice`` and the holder inside it, so a case can count the calls."""
    holder = GeneratorDouble(*answers, sleep=sleep)
    return Voice({main: holder}, bound_seconds=bound_seconds, **kw), holder


def spoke(
    voice,
    context=None,
    *,
    main=MAIN,
    sample=None,
    withheld=None,
    show="",
) -> Turned:
    return asyncio.run(words(
        voice,
        ordinary() if context is None else context,
        main_id=main,
        sample=Sample(SCRIPTS["latin"]) if sample is None else sample,
        withheld=ordinary_withheld() if withheld is None else withheld,
        show=show,
    ))


# ═════════════════════════════════════════════════════════════════════════════
# the bound: a main is waiting, and waits for the turn's bound and not the
# morning's
# ═════════════════════════════════════════════════════════════════════════════


def test_the_turn_waits_less_than_the_morning_and_it_is_checked_at_import():
    """The one number that differs because somebody is on the other end.

    Asserted as a *relation* rather than against the literal, because the
    literal is allowed to move and the relation is not: a turn has a person
    waiting on it and a morning does not.
    """
    assert 0 < TURN_BOUND_SECONDS < BOUND_SECONDS


def test_a_turn_waits_the_turn_s_bound_even_inside_a_voice_built_for_mornings():
    """The composer is *one* gate, so the turn's bound travels on the call.

    A second ``Voice`` for the turn would be a second tally, a second breaker
    and a second holder check — three ways for the two to drift — so the
    difference is a parameter. This is the case that proves the parameter is
    read: the voice is built with the morning's twenty seconds and the turn
    still gives up at two.
    """
    voice, holder = a_voice(
        "never arrives", sleep=TURN_BOUND_SECONDS + 0.5,
        bound_seconds=BOUND_SECONDS,
    )
    started = time.monotonic()
    turned = spoke(voice)
    elapsed = time.monotonic() - started

    assert turned.text == SAYABLE          # the fallback, not silence
    assert not turned.composed
    assert TURN_BOUND_SECONDS <= elapsed < BOUND_SECONDS
    # One bound, not three: ``PAST_THE_BOUND`` is terminal, so a dead provider
    # costs the waiting main one wait and never ``ATTEMPTS`` of them.
    assert holder.calls == 1


def test_a_bound_a_voice_cannot_use_falls_back_to_the_one_it_was_built_with(
    caplog,
):
    """A bad argument must not cost a main their reply, and must not be silent.

    ``Voice.compose`` never raises; that promise is what a turn's fail-open
    path rests on. So an unusable per-call bound is logged and the construction
    bound stands, rather than raising into a main's turn.
    """
    voice, holder = a_voice("a reply", bound_seconds=0.5)
    with caplog.at_level(logging.WARNING, logger="half.voice.gate"):
        composed = asyncio.run(voice.compose(
            ordinary(), main_id=MAIN, sample=Sample(SCRIPTS["latin"]),
            withheld=ordinary_withheld(), bound_seconds=0,
        ))
    assert composed.text == "a reply"
    assert holder.calls == 1
    assert any("bound it cannot use" in r.message for r in caplog.records)


# ═════════════════════════════════════════════════════════════════════════════
# the fallback: the claim alone, reachable with no model call
# ═════════════════════════════════════════════════════════════════════════════


def test_a_main_with_no_holder_gets_the_claim_and_no_provider_is_reached():
    """The rung the story insists is a branch and not an outcome.

    The signal is a **counter**, not a raise: ``Voice._attempt_all`` converts
    an ``AssertionError`` into ``Unspoken(RAISED)``, a legal reason, so a double
    that only raises would let this case pass with the provider paid.
    """
    never = NeverGenerates()
    voice = Voice({OTHER: never}, bound_seconds=0.5)

    turned = spoke(voice)

    assert turned.text == SAYABLE
    assert not turned.composed
    assert never.calls == 0
    # Nothing was composed for anybody, so no rate an operator reads moved.
    assert voice.tally.composed == 0
    assert voice.tally.attempts == 0


def test_the_fallback_is_the_claim_and_carries_no_part_of_the_serialization():
    """*"No label, belief id or scaffolding — including in the fallback."*

    Derived from the context the turn actually built rather than from a list of
    expected strings, so a renamed channel label or a new item type changes what
    this case looks for.
    """
    context = ordinary()
    voice = Voice({}, bound_seconds=0.5)

    turned = spoke(voice, context)

    assert turned.text == SAYABLE
    for item in context:
        assert item.id not in turned.text
        head, bracket, _ = render_line(item).partition("]")
        assert (head + bracket) not in turned.text
    assert context.now not in turned.text
    for label in (MAY_BE_SAID, ASK_ABOUT, WORD_FOR_WORD):
        assert label not in turned.text


@pytest.mark.parametrize("script", sorted(CLAIMS))
def test_the_fallback_is_the_claim_unchanged_in_every_script(script):
    """The fallback is *the main's own words*, so nothing may touch them.

    Swept over fourteen writing systems because a fallback that trimmed, folded
    or re-cased its claim would be correct in Latin and damage a Devanagari
    matra, a Khmer dependent vowel or an Arabic ligature — the class of input a
    Latin-only case cannot see.
    """
    claim = CLAIMS[script]
    context = a_context(candidate("b_1", claim))
    assert fallback(context) == claim
    assert spoke(Voice({}), context, withheld=frozenset()).text == claim


@pytest.mark.parametrize(
    "answer",
    [
        "",                                                    # judged: empty
        "x" * 5_000,                                           # judged: long
        Failure(kind=Kind.UNAVAILABLE, because=Reason.TRANSPORT_FAILED),
        RuntimeError("the holder is wrong"),                   # raised
        object(),                                              # unreadable
    ],
    ids=["empty", "too-long", "transport", "raised", "unreadable"],
)
def test_every_way_a_generation_can_fail_ends_in_the_claim_and_never_silence(
    answer,
):
    """The matrix's *provider absent or failing* row, one rung down.

    Whatever the gate answers, the main gets the claim: the reply is never lost
    and is never a template. That the *reason* differs is the gate's business
    and is counted there.
    """
    voice, _ = a_voice(answer)
    turned = spoke(voice)
    assert turned.text == SAYABLE
    assert not turned.composed


def test_a_leaked_behave_claim_falls_back_to_the_claim_rather_than_to_silence():
    """The tripwire refuses the send, and the turn still answers.

    On a morning a leak is silence. Here it is the fallback — which is quotable
    by definition, so the refusal costs the generated sentence and not the
    main's reply. Nothing is cleaned: the text that leaked never travels.
    """
    voice, _ = a_voice(f"a thought about how he {WITHHELD} today")
    turned = spoke(voice)
    assert turned.text == SAYABLE
    assert WITHHELD not in turned.text
    assert voice.tally.leaked == 1


def test_no_claim_and_a_failed_generation_is_silence_and_not_scaffolding():
    """The one rung where a waiting main is answered with nothing.

    *"Silence only when there is no claim to send."* A context with no quotable
    content and no bought question is answered before a provider is paid, and
    the answer is nothing at all — never ``noted.``, which is a template in one
    language, and never the serialization.
    """
    never = NeverGenerates()
    voice = Voice({MAIN: never}, bound_seconds=0.5)
    empty = a_context(
        candidate("b_2", WITHHELD, rung=License.BEHAVE, topics=["family"])
    )

    turned = spoke(voice, empty, withheld=ordinary_withheld())

    assert turned.silent
    assert turned.text == ""
    assert never.calls == 0


# ═════════════════════════════════════════════════════════════════════════════
# the composed reply
# ═════════════════════════════════════════════════════════════════════════════


def test_an_ordinary_turn_comes_back_as_prose_and_says_so():
    voice, holder = a_voice("that plot has been waiting for you a while")
    turned = spoke(voice)
    assert turned.text == "that plot has been waiting for you a while"
    assert turned.composed
    assert holder.calls == 1


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_the_message_in_hand_is_what_sets_the_language(script):
    """On a turn the sample is the message in hand — there is no fold to read.

    Swept over fourteen scripts, and the assertion is that the sample reaches
    the generator **under its own label** and that no claim reaches it: the
    structural rule is 13a's and this is the path 13b adds to it.
    """
    voice, holder = a_voice("a reply")
    spoke(voice, sample=Sample(SCRIPTS[script]))

    sent = holder.requests[0].prompt.turns[0].text
    assert SCRIPTS[script] in sent
    said = _block(sent, MAY_BE_SAID)
    assert SCRIPTS[script] not in said
    assert said == SAYABLE


def test_composed_is_true_only_when_the_model_s_own_prose_goes_out():
    """The flag a spend is decided on, asserted on both sides.

    A favour buys a question; if the fallback goes out, the question the favour
    paid for was never asked. So *"was the composed text what was sent"* has to
    be a property of the answer rather than something the caller infers.
    """
    working, _ = a_voice("that plot has been waiting")
    assert spoke(working).composed is True

    failing, _ = a_voice("")
    assert spoke(failing).composed is False
    assert spoke(Voice({})).composed is False


# ═════════════════════════════════════════════════════════════════════════════
# CAP-4: the question is composed in, and a question with nothing to say
# ═════════════════════════════════════════════════════════════════════════════


def test_a_bought_question_reaches_the_prompt_and_is_never_a_line_on_the_wire():
    """The question is composed *into* the prose (CAP-4).

    Two halves: the topic reaches the generator under ``ask-about``, and what
    goes on the wire is the model's one message — never the builder's
    ``question[b_3] topic: farmland``, which is the scaffolding this story
    exists to remove and which reads as a form with one row.
    """
    context = a_context(
        *material(),
        candidate("b_3", "wants to plant the north field",
                  rung=License.ASK, topics=["farmland"]),
        bought="b_3",
    )
    voice, holder = a_voice("the plot is still there — what will go in it?")

    turned = spoke(voice, context, withheld=_withheld_with_ask())

    assert context.question is not None
    assert "farmland" in _block(holder.requests[0].prompt.turns[0].text, ASK_ABOUT)
    assert turned.composed
    assert render_line(context.question) not in turned.text
    assert "b_3" not in turned.text
    assert "\n" not in turned.text


def test_a_question_with_nothing_to_say_is_still_asked():
    """The state 13a left unspecified, specified here.

    A bought question with no quotable content is a legitimate turn: Half has a
    favour to spend and something to ask, and no standing to state anything. The
    prompt must be coherent without a ``may-be-said`` block — before this story
    the instructions called that block the only thing the model may state, with
    no path that reached it empty.
    """
    context = a_context(
        candidate("b_3", "wants to plant the north field",
                  rung=License.ASK, topics=["farmland"]),
        bought="b_3",
    )
    voice, holder = a_voice("what is going in the north field this year?")

    turned = spoke(voice, context, withheld=frozenset())

    sent = holder.requests[0].prompt.turns[0].text
    assert MAY_BE_SAID not in sent
    assert "farmland" in _block(sent, ASK_ABOUT)
    assert turned.composed
    assert turned.text == "what is going in the north field this year?"


def test_the_instructions_say_what_to_do_with_no_may_be_said_block():
    """The other half of the same finding, at the source.

    A block-by-block instruction set that names one block as *the only thing you
    may state* and is then handed a prompt without it is a prompt that
    contradicts itself. The rule is stated once, in the instructions, rather
    than left for each caller to avoid reaching.
    """
    from half.voice.compose import INSTRUCTIONS

    joined = " ".join(INSTRUCTIONS)
    assert "If there is no may-be-said block" in joined


# ═════════════════════════════════════════════════════════════════════════════
# CAP-11: what a correction reply must contain
# ═════════════════════════════════════════════════════════════════════════════


def test_a_composed_reply_that_omits_the_removed_claim_is_not_sent():
    """The story's point, and the case that has to fail if the omission ships.

    Prose that says *"I've taken that out"* without saying *what* sounds better
    than the claim and verifies nothing — and story 12's aim can mis-target, so
    the main is the only one who can catch it. The check is over what is
    **sent**, not over what was generated.
    """
    voice, holder = a_voice("I've taken that out.")
    context = a_context(candidate("b_land", SAYABLE))

    turned = spoke(voice, context, withheld=frozenset(), show=SAYABLE)

    assert holder.calls == 1                 # it was generated
    assert turned.text == SAYABLE            # and it was not sent
    assert not turned.composed
    assert "I've taken that out." not in turned.text


def test_a_composed_reply_that_shows_the_removed_claim_is_sent():
    voice, _ = a_voice(f"{SAYABLE} — that is out of what I hold now.")
    context = a_context(candidate("b_land", SAYABLE))

    turned = spoke(voice, context, withheld=frozenset(), show=SAYABLE)

    assert turned.composed
    assert SAYABLE in turned.text


@pytest.mark.parametrize("script", sorted(CLAIMS))
def test_the_removed_claim_travels_word_for_word_in_every_script(script):
    """The block the model is told about, swept over fourteen writing systems.

    A requirement the model is never told is a requirement the fallback answers
    every time — so the composed correction reply would be dead code, and
    nobody would find out from a green suite. The block carries the claim
    unchanged, which is the same thing the check looks for.
    """
    claim = CLAIMS[script]
    voice, holder = a_voice(f"{claim} — noted and gone.")
    context = a_context(candidate("b_land", claim))

    turned = spoke(voice, context, withheld=frozenset(), show=claim)

    sent = holder.requests[0].prompt.turns[0].text
    assert _block(sent, WORD_FOR_WORD) == claim
    assert turned.composed
    assert claim in turned.text


def test_no_word_for_word_block_reaches_a_prompt_that_is_not_a_correction():
    """Every other turn, and every morning, carries no such block."""
    voice, holder = a_voice("that plot has been waiting")
    spoke(voice)
    assert WORD_FOR_WORD not in holder.requests[0].prompt.turns[0].text


def test_the_inclusion_check_and_the_fallback_cannot_disagree():
    """The property that keeps the check from being a permanent silence.

    The fallback satisfies the check *by construction* — it is the claim — so
    there is no claim for which the check refuses everything the turn can send.
    Swept over the fourteen scripts because a check written with a fold, a trim
    or a case rule in it would hold in Latin and fail elsewhere.
    """
    for claim in CLAIMS.values():
        context = a_context(candidate("b_land", claim))
        assert claim in fallback(context, show=claim)
        turned = spoke(Voice({}), context, withheld=frozenset(), show=claim)
        assert claim in turned.text


def test_a_correction_reply_that_omits_the_claim_is_logged_without_a_word_of_it(
    caplog,
):
    """AD-22: the alarm must not carry the thing it is about.

    Two strings are in play — the claim and the prose that failed to show it —
    and neither may reach a log line, because the log is where the most intimate
    dataset the product holds leaks through an observability side channel.
    """
    voice, _ = a_voice("I've taken that out.")
    context = a_context(candidate("b_land", SAYABLE))
    with caplog.at_level(logging.DEBUG, logger="half.voice.turn"):
        spoke(voice, context, withheld=frozenset(), show=SAYABLE)

    assert caplog.records
    for record in caplog.records:
        rendered = record.getMessage()
        assert SAYABLE not in rendered
        assert "I've taken that out." not in rendered
        for argument in (record.args or ()):
            assert SAYABLE not in str(argument)


# ═════════════════════════════════════════════════════════════════════════════
# one composer, one set of counters
# ═════════════════════════════════════════════════════════════════════════════


def test_a_turn_and_a_morning_count_into_the_same_tally():
    """*"One composer, one gate, one leak check, one set of counters."*

    Two renderings of one thing is how a guard that scans one string ends up
    admitting another, and two tallies is how an operator reads one of them.
    """
    voice, holder = a_voice("a reply")
    spoke(voice)
    asyncio.run(voice.compose(
        ordinary(), main_id=MAIN, sample=Sample(SCRIPTS["latin"]),
        withheld=ordinary_withheld(),
    ))
    assert voice.tally.composed == 2
    assert voice.tally.spoken == 2
    assert holder.calls == 2


def test_a_run_of_failed_turns_stands_that_main_down_and_still_answers():
    """The breaker reaches the turn, and standing down is not silence.

    On a morning a stand-down means no message. Here it means the fallback,
    with no call made at all — which is the right shape for a waiting main
    behind a dead provider: they get what Half knows, immediately, rather than
    a bound each time.
    """
    from half.voice.gate import BREAK_AFTER

    voice, holder = a_voice("")           # judged empty, every time
    for _ in range(BREAK_AFTER):
        assert spoke(voice).text == SAYABLE
    calls_before = holder.calls

    turned = spoke(voice)

    assert turned.text == SAYABLE
    assert not turned.composed
    assert holder.calls == calls_before   # the breaker made no call
    assert voice.tally.skipped == 1


# ═════════════════════════════════════════════════════════════════════════════
# helpers
# ═════════════════════════════════════════════════════════════════════════════


def _block(assembled: str, label: str) -> str:
    for block in assembled.split("\n\n"):
        if block.startswith(label):
            return block[len(label):].strip()
    return ""


def _withheld_with_ask() -> frozenset[str]:
    return withheld_wordings(
        [
            *material(),
            candidate("b_3", "wants to plant the north field",
                      rung=License.ASK, topics=["farmland"]),
        ],
        ceiling=Ceiling(),
    )
