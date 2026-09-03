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

import ast
import asyncio
import logging
import time
from pathlib import Path
from typing import Final

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.context.build import build as build_context
from half.context.build import withheld as withheld_wordings
from half.context.channels import Context, render_line
from half.governance.ladder import Ceiling, License
from half.loops import ledger as loops
from half.model.port import Failure, Kind, Reason
from half.retrieval.port import Candidate as RankedBelief
from half.retrieval.prefix import build_prefix
from half.store.ops import TOUCH_TENSION, Op
from half.store.store import Store
from half.surface import touch
from half.voice.compose import (
    ASK_ABOUT,
    MAY_BE_SAID,
    WORD_FOR_WORD,
    Sample,
)
from half.voice.gate import BOUND_SECONDS, QUESTION_MARKS, Voice
from half.voice.turn import TURN_BOUND_SECONDS, Turned, fallback, words

from tests.conftest import (
    FakeTransport,
    GeneratorDouble,
    NeverGenerates,
    msg,
    seed_belief,
)

ROOT = Path(__file__).resolve().parents[1]

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


def test_the_fallback_is_the_top_ranked_claim_and_not_just_any_of_them():
    """Rank order decides which claim goes, as it decides everything else.

    **A live mutation found this.** Reading the *last* quotable claim instead of
    the first left every other case green, because most of them seed one — and
    it would quietly send the least relevant thing Half holds to somebody who
    has just written about the most relevant one.
    """
    first, second = SAYABLE, "reads two books at once"
    context = a_context(candidate("b_1", first), candidate("b_2", second))
    assert context.quotable() == (first, second), "the fixture must have order"
    assert fallback(context) == first
    assert spoke(Voice({}), context, withheld=frozenset()).text == first


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


@pytest.mark.parametrize(
    "label", [ASK_ABOUT, MAY_BE_SAID, WORD_FOR_WORD], ids=["ask", "said", "verbatim"]
)
def test_a_candidate_echoing_a_block_label_is_refused_by_the_judge(label):
    """Every prompt label is scaffolding, including the one 13b adds.

    ``half.voice.gate.scaffolding`` reads the labels from
    ``half.voice.compose`` rather than respelling them, so adding a block
    without adding it there would put ``word-for-word:`` on somebody's wire and
    nothing would say so. The judge refuses the candidate, the attempt is
    regenerated, and the second one is sent.
    """
    voice, holder = a_voice(f"{label} {SAYABLE}", SAYABLE)
    turned = spoke(voice)
    assert turned.text == SAYABLE
    assert holder.calls == 2, "the first candidate was not refused"
    assert voice.tally.refusals.get("scaffolding") == 1


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


# ═════════════════════════════════════════════════════════════════════════════
# end to end: the real runtime, the real store, the real gate
# ═════════════════════════════════════════════════════════════════════════════
#
# The cases above carry ``half.voice.turn`` on its own. These carry it **through
# the turn path** — a real store, a real fold, the real context builder, the
# real crisis gate — which is where the launch blocker lived: ``respond``
# returned ``noted. has not walked that plot since March`` and ``_pipeline``
# joined ``retract[b_land]: ...`` onto it.


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path / "mains")
    yield reg
    reg.close()


def a_main(root, *, main_id=MAIN, sayable=SAYABLE, withheld=WITHHELD,
           loop="buy-farmland"):
    """One main: one claim Half may state, one it may not, on one wanting."""
    with Store(root / main_id, prefix=build_prefix) as store:
        store.record(
            Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00:00Z",
            **loops.opened(loop, state="stalled", timescale="years",
                           last_movement="2026-01-04",
                           loops=store.state().loops),
        )
        if sayable:
            seed_belief(store, "b_say", "2026-08-01T00:00:00Z", subject="self",
                        claim=sayable, ledger="revealed", loop=loop,
                        topics=["farmland"], rung=License.ASSERT,
                        support=["s_1"])
        if withheld:
            # On the same wanting as the sayable one, because the correction
            # cases need it *aimable*: ``half.correction.apply.aim`` takes the
            # top-ranked belief above a relevance floor, and the floor is read
            # off the strand weight the loop slug and the topic fields build.
            seed_belief(store, "b_hold", "2026-08-01T00:00:00Z", subject="self",
                        claim=withheld, ledger="revealed", loop=loop,
                        topics=["farmland"])


def turns(registry, texts, *, main_id=MAIN, voice=None, at=1_788_264_000,
          asks=False, tag="t"):
    """Real inbound turns, through the real runtime and the real crisis gate.

    ``tag`` distinguishes two *calls*: at-least-once delivery makes a repeated
    external id a redelivery, and a second run reusing the first run's ids is
    dropped before anything is composed.
    """
    from half.questions.engine import QuestionEngine

    transport = FakeTransport([
        msg(text=text, message_id=f"{tag}{index}", chat_id="123",
            date=int(at + index))
        for index, text in enumerate(texts)
    ])
    channel = TelegramChannel(transport=transport, mains={"123": main_id})
    asyncio.run(Runtime(
        channel=channel, registry=registry,
        voice=Voice() if voice is None else voice,
        questions=QuestionEngine(ledger=registry) if asks else None,
    ).run())
    return transport


def wire(transport):
    return "".join(text for _, text in transport.sent)


def ranked_of(root, text, *, main_id=MAIN, now=NOW):
    from half.retrieval.rank import Retriever

    with Store(root / main_id, prefix=build_prefix) as store:
        return Retriever(store=store).retrieve(text, now=now)


# ── the ordinary turn ────────────────────────────────────────────────────────


def test_the_wire_carries_prose_and_no_part_of_the_serialization(
    registry, tmp_path
):
    """The acceptance criterion, word for word: *asserted against the
    serialization, not a fixture string.*

    The context the turn built is rebuilt here and rendered, and every token of
    that rendering is looked for on the wire. A renamed channel label or a new
    item type changes ``render_line`` and changes what this case looks for; a
    list of expected strings would go on passing after the thing it described
    had moved.
    """
    root = tmp_path / "mains"
    a_main(root)
    voice, holder = a_voice("that plot has been waiting for you a while")

    transport = turns(registry, ["thinking about the farmland again"],
                      voice=voice)

    body = wire(transport)
    assert body == "that plot has been waiting for you a while"
    context = build_context(
        ranked_of(root, "thinking about the farmland again"),
        now=NOW, ceiling=None,
    )
    assert len(context) >= 1, "the turn must have built a context to compare to"
    for line in context.render().split("\n"):
        assert line not in body
    for item in context:
        assert item.id not in body
        head, bracket, _ = render_line(item).partition("]")
        assert (head + bracket) not in body
    assert "\n" not in body, "one message, not a form"
    assert WITHHELD not in body


def test_a_provider_that_is_absent_costs_the_main_nothing_but_the_prose(
    registry, tmp_path
):
    """Matrix: *provider absent or failing*. The claim alone, and the message
    still recorded."""
    root = tmp_path / "mains"
    a_main(root)

    transport = turns(registry, ["thinking about the farmland again"])

    assert wire(transport) == SAYABLE

    async def recorded():
        async with registry.acquire(MAIN) as actor:
            return {
                record.get("claim") for record in
                actor.store.state().beliefs.values()
            }
    assert "thinking about the farmland again" in asyncio.run(recorded())


def test_a_redelivery_is_answered_once_and_recorded_once(registry, tmp_path):
    """Matrix: *redelivery*. Idempotent, and the second delivery composes
    nothing at all — the check answers before a provider is reached."""
    root = tmp_path / "mains"
    a_main(root)
    voice, holder = a_voice("that plot has been waiting")
    transport = FakeTransport([
        msg(text="farmland again", message_id="same", chat_id="123", date=1),
        msg(text="farmland again", message_id="same", chat_id="123", date=1),
    ])
    channel = TelegramChannel(transport=transport, mains={"123": MAIN})
    asyncio.run(Runtime(channel=channel, registry=registry, voice=voice).run())

    assert len(transport.sent) == 1
    assert holder.calls == 1, "the redelivery paid a provider"


def test_a_blank_message_is_unchanged_and_reaches_no_provider(
    registry, tmp_path
):
    """Matrix: *blank message*. Unchanged from today, and it costs nothing."""
    a_main(tmp_path / "mains")
    never = NeverGenerates()

    transport = turns(registry, ["   "], voice=Voice({MAIN: never}))

    assert transport.sent == []
    assert never.calls == 0


# ── CAP-11 through the turn path ─────────────────────────────────────────────


def test_a_correction_reply_carries_the_removed_claim_and_no_marker(
    registry, tmp_path
):
    """CAP-11 on the wire. Until story 13b this was
    ``retract[b_hold]: avoids the conversation with his brother``.
    """
    root = tmp_path / "mains"
    a_main(root, sayable="")
    voice, holder = a_voice(
        lambda work: f"{WITHHELD} — taken out of what I hold."
    )

    transport = turns(registry, ["farmland again please", "thats wrong"],
                      voice=voice)

    body = transport.sent[-1][1]
    assert WITHHELD in body, "the main must be shown what left"
    assert "retract" not in body and "b_hold" not in body
    assert "[" not in body and "]" not in body
    # **And the prose is what went out, not the fallback.** This is the half a
    # mutation walks through otherwise: the belief a main has just corrected is
    # `behave`, so leaving its wording in the withheld set makes the tripwire
    # refuse every composed correction reply — and the fallback that follows is
    # the claim, so the wire looks identical and only the counter moves. The
    # composed path would be dead, permanently, with this file green.
    assert body != WITHHELD, "the fallback went out, not the composed reply"
    assert voice.tally.leaked == 0, "the removed claim was withheld from itself"
    assert voice.tally.spoken == 1


def test_the_removed_claim_is_the_only_thing_a_correction_reply_may_state(
    registry, tmp_path
):
    """A correction turn is about the belief that left, and about nothing else.

    **A live mutation found this.** Letting the ordinary content channel through
    beside the removed claim leaves every wire assertion green — the removed
    claim is still there, because it is also the fallback — while giving the
    model licence to answer *"that's wrong"* with an unrelated statement, at the
    one moment the main is checking Half's work. So the assertion is on the
    **may-be-said block** the generator was handed, which is the only place the
    difference is visible.
    """
    root = tmp_path / "mains"
    a_main(root)                                  # a sayable claim *and* a
    voice, holder = a_voice(                      # withheld one
        lambda work: f"{_said(work)} — out of what I hold."
    )

    turns(registry, ["farmland again please", "thats wrong"], voice=voice)

    said = [_said(work) for work in holder.requests]
    assert said[-1] == WITHHELD, said
    assert SAYABLE not in said[-1], "the reply may state the removal, and no more"


def _said(work):
    for block in work.prompt.turns[0].text.split("\n\n"):
        if block.startswith(MAY_BE_SAID):
            return block[len(MAY_BE_SAID):].strip()
    return ""


def test_a_composed_correction_reply_that_omits_the_claim_is_not_sent(
    registry, tmp_path
):
    """**The case that fails if the omission ships.**

    The generator writes friendly prose that says a thing was removed and does
    not say what. It is generated — the holder is called — and it does not reach
    the main; the claim does.
    """
    root = tmp_path / "mains"
    a_main(root, sayable="")
    voice, holder = a_voice("I've taken that out for you.")

    transport = turns(registry, ["farmland again please", "thats wrong"],
                      voice=voice)

    body = transport.sent[-1][1]
    assert holder.calls >= 1, "the fixture must have generated something to lose"
    assert "I've taken that out for you." not in body
    assert body == WITHHELD


def test_a_confirmed_erasure_shows_the_claim_before_the_body_is_gone(
    registry, tmp_path
):
    """Matrix: *correction, erasure*. **The ordering, asserted.**

    An erasure is the only removal that cannot be undone by correcting the
    correction, so the confirming turn is the last moment a mis-aimed one can be
    caught. The claim is read off the fold before ``Store.expunge`` tombstones
    the body, so the reply carries words that are no longer anywhere on disk.
    """
    root = tmp_path / "mains"
    a_main(root, sayable="")

    transport = turns(
        registry,
        ["farmland again please", "delete that", "yes"],
    )

    assert transport.sent[-1][1] == WITHHELD, "the claim is shown"
    shard = (root / MAIN / "beliefs").glob("*.jsonl")
    on_disk = "".join(path.read_text(encoding="utf-8") for path in shard)
    assert WITHHELD not in on_disk, "the body is gone"


# ── CAP-4 through the turn path ──────────────────────────────────────────────


def test_a_bought_question_arrives_inside_the_message_and_never_as_a_line(
    registry, tmp_path
):
    """Matrix: *bought question*. One question, composed in, no line."""
    root = tmp_path / "mains"
    a_main(root, sayable="")
    with Store(root / MAIN, prefix=build_prefix) as store:
        seed_belief(store, "b_ask", "2026-08-01T00:00:00Z", subject="self",
                    claim="wants to plant the north field", ledger="stated",
                    loop="buy-farmland", topics=["farmland"],
                    rung=License.ASK, support=["s_2"])
        store.record(
            Op.TOUCH, "tc_2026-08-20T09:00:00Z", "2026-08-20T09:00:00Z",
            **touch.spoke(day="2026-08-20",
                          origin=touch.Origin(kind=TOUCH_TENSION, id="x_1"),
                          loops=("buy-farmland",)),
        )
    voice, holder = a_voice("the plot is still there — what goes in it?")

    transport = turns(
        registry, ["farmland again please"], voice=voice, asks=True,
    )

    body = wire(transport)
    assert "question[" not in body and "b_ask" not in body
    assert "\n" not in body
    assert sum(1 for char in body if char in QUESTION_MARKS) == 1
    asked = [
        block for work in holder.requests
        for block in work.prompt.turns[0].text.split("\n\n")
        if block.startswith(ASK_ABOUT)
    ]
    assert asked, "the favour bought a question that never reached the prompt"


# ── AD-18, AD-22, CAP-12 ─────────────────────────────────────────────────────


def test_a_generated_behave_claim_stops_the_send_and_the_claim_goes_instead(
    registry, tmp_path, caplog
):
    """Matrix: *`behave` leak*. Refused loudly, never cleaned, and the turn is
    still answered — with the claim, which is quotable by definition."""
    root = tmp_path / "mains"
    a_main(root)
    voice, _ = a_voice(f"a thought about how he {WITHHELD} lately")

    with caplog.at_level(logging.ERROR, logger="half.voice.leak"):
        transport = turns(registry, ["thinking about the farmland again"],
                          voice=voice)

    body = wire(transport)
    assert WITHHELD not in body
    assert body == SAYABLE
    assert voice.tally.leaked == 1
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_no_generated_string_is_written_anywhere(registry, tmp_path, script):
    """AD-22, in every script. The log records that a turn happened, never what
    Half said."""
    root = tmp_path / "mains"
    a_main(root)
    # **The message is a statement and not a negation**, which is not a detail:
    # ``half.correction.signals`` recognises *"that is not right any more"* in
    # every one of these scripts, so a fixture built from ``SCRIPTS`` would turn
    # half of these runs into correction turns and this case would silently stop
    # being about an ordinary one.
    composed = f"{CLAIMS[script]} — {SAYABLE}"
    voice, _ = a_voice(composed)

    transport = turns(registry, [f"farmland — {CLAIMS[script]}"], voice=voice)

    assert composed in wire(transport), "the fixture must have sent it"
    for path in sorted((root / MAIN).rglob("*")):
        if path.is_file():
            body = path.read_bytes()
            assert composed.encode("utf-8") not in body, path


def test_a_main_in_crisis_is_never_composed_for(registry, tmp_path):
    """CAP-12: no crisis reply is ever generated. The counter is the signal — a
    double that only raised would be swallowed into ``Unspoken(RAISED)``."""
    a_main(tmp_path / "mains")
    never = NeverGenerates()

    transport = turns(registry, ["i want to kill myself"],
                      voice=Voice({MAIN: never}))

    assert transport.sent, "a crisis turn is always answered"
    assert never.calls == 0, "a crisis reply was composed by a model"


def test_the_turn_and_the_morning_are_one_composer(registry, tmp_path):
    """*"One composer, one gate, one leak check, one set of counters."*

    Asserted through the shipped wiring rather than by reading it: the runtime
    and the morning surface are handed the same object, so an operator reads one
    silent rate and a leak on either path lands in one counter.
    """
    import half.__main__ as entrypoint

    source = (ROOT / "half/__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    built = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "Voice"
    ]
    # Two constructions, both inside ``voices`` — the equipped one and the empty
    # fallback — and no third anywhere. A second ``Voice`` for the turn is the
    # fork this story exists without.
    assert len(built) == 2, [ast.unparse(node) for node in built]
    assert hasattr(entrypoint.Wiring, "__annotations__")
    assert "voice" in entrypoint.Wiring.__annotations__


def test_a_failed_generation_asks_nothing_and_spends_no_favour(
    registry, tmp_path
):
    """Matrix: *the question is dropped*. **A live mutation found this.**

    A favour was unspent, every gate passed, the builder emitted the question —
    and then the generation failed, so what went on the wire was the fallback:
    the claim alone, which asks nothing. Spending the favour there would pay for
    a question the main never saw, which is the mirror of the defect review
    found in story 11, where a spend happened before the thing it paid for
    existed.

    **Both halves are asserted**, because the negative one alone passes on a
    build that never asks anybody anything: the same fixture with a working
    generator spends exactly one favour.
    """
    root = tmp_path / "mains"
    a_main(root, sayable="")
    with Store(root / MAIN, prefix=build_prefix) as store:
        seed_belief(store, "b_ask", "2026-08-01T00:00:00Z", subject="self",
                    claim="wants to plant the north field", ledger="stated",
                    loop="buy-farmland", topics=["farmland"],
                    rung=License.ASK, support=["s_2"])
        store.record(
            Op.TOUCH, "tc_2026-08-20T09:00:00Z", "2026-08-20T09:00:00Z",
            **touch.spoke(day="2026-08-20",
                          origin=touch.Origin(kind=TOUCH_TENSION, id="x_1"),
                          loops=("buy-farmland",)),
        )

    failing, holder = a_voice("")            # judged empty, every attempt
    turns(registry, ["farmland again please"], voice=failing, asks=True)

    assert holder.calls >= 1, "the generation must have been attempted"
    assert _spends(root) == [], (
        "a favour was spent for a question the main never saw"
    )

    working, _ = a_voice("the plot is still there — what goes in it?")
    turns(registry, ["farmland again please"], voice=working, asks=True,
          at=1_788_264_100, tag="u")

    assert len(_spends(root)) == 1, (
        "the positive control must spend, or the case above proves nothing"
    )


def test_the_fallback_is_reached_without_entering_the_gate():
    """*"A branch that never entered the gate"*, asserted structurally.

    **This one is a shape rather than a behaviour, and that is stated rather
    than hidden.** Deleting the ``holds`` guard changes nothing observable
    today: ``Voice.compose`` answers ``NO_MODEL`` before it touches a holder, so
    the wire, the tally and the timings are identical either way — a mutation
    probe over the whole suite survives it. What the guard buys is that the
    fallback cannot *acquire* the gate's latency the first time somebody adds a
    step to ``compose``, and the only instrument that can hold a shape is one
    that reads the shape.

    So: in ``words``, an ``if`` whose test names ``holds`` and whose body
    returns must come before the first ``await``. The mutation fails it because
    the surviving ``isinstance`` test names no such thing.
    """
    import half.voice.turn as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    body = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "words"
    ).body
    guarded = None
    for index, statement in enumerate(body):
        if isinstance(statement, ast.If) and "holds" in ast.unparse(statement.test):
            assert any(isinstance(inner, ast.Return) for inner in statement.body)
            guarded = index
            break
    assert guarded is not None, "nothing in `words` asks whether a model exists"
    before = ast.Module(body=body[:guarded + 1], type_ignores=[])
    assert not [
        node for node in ast.walk(before) if isinstance(node, ast.Await)
    ], "the fallback waits on something before it knows there is a model"


def _spends(root, main_id=MAIN):
    with Store(root / main_id) as store:
        return [record for record in store.log if record.op is Op.ASKED]
