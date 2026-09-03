"""CAP-8 story 13a: what actually goes on the wire, and what never does.

``tests/test_voice.py`` carries the composer, the judge and the tripwire on
their own. This file carries them **through the surface**, over a real store, a
real fold and the real context builder — which is where the launch blocker
lived: ``half.surface.morning`` sent ``Context.render()``, so a main received
``content[b_1]: has not walked that plot since March``.

**The wire is asserted against the serialization, never against a fixture's
expected string.** Every case that says *"no label, no belief id, no
scaffolding"* derives those tokens by rendering the context the surface actually
built and looking for its own output on the wire. A list of expected strings
would go on passing after the thing it described had moved.

**Three orderings are asserted rather than commented.**

* The words are composed **before** the day is claimed, so a generation that
  fails costs no day — asserted by driving a failing composer and then a working
  one on the same local day and watching the second one send.
* Reachability is asked **before** the composer, so an unreachable main costs
  nothing — asserted by a generator that raises if it is ever reached.
* The day is claimed **before** the send, which story 10 already asserts and
  this file does not re-litigate.

**Every language rule is swept over scripts.** A main who last wrote in Thai
gets a Thai morning, and the rule that decides it must not be a rule that only
notices Latin — which is story 12's ten English fixtures, one story on.

Offline throughout: the provider is the port's narrow generator, stubbed, and
nothing here opens a socket.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.channel.port import Reachability, SendResult
from half.context.build import build as build_context
from half.context.channels import render_line
from half.governance import ladder
from half.governance.ladder import License
from half.loops import ledger as loops
from half.model.port import Completion, Failure, Kind, Reason, Usage
from half.retrieval.port import Candidate as RankedBelief
from half.schedule.clock import FrozenClock, moment, stamp
from half.store.ops import TOUCH_TENSION, Op
from half.store.records import NEXT_PASS_AT, TOLD_ZONE, ZONE
from half.store.store import Store
from half.surface.choose import Candidate
from half.surface.morning import (
    ALREADY_TODAY,
    CRISIS,
    MorningPass,
    Mornings,
    MorningSurface,
    NOTHING_TO_SAY,
    REASONS,
    Silence,
    Surfaced,
)
from half.surface.touch import Origin
from half.voice.compose import (
    ASK_ABOUT,
    BE_MINDFUL_OF,
    LANGUAGE_SAMPLE,
    MAY_BE_SAID,
    Sample,
    sample_from,
)
from half.voice.gate import (
    JUDGED,
    LEAKED,
    MAX_CHARS,
    NO_LANGUAGE,
    NO_MODEL,
    OVER_BUDGET,
    PAST_THE_BOUND,
    RAISED,
    REFUSED,
    Voice,
)

from tests.conftest import COMPOSED, FakeTransport, seed_belief, seed_message

pytestmark = [pytest.mark.cap8, pytest.mark.cap8_voice]

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"
NOON = 1_788_264_000.0
NOW = moment(NOON)
TODAY = "2026-09-01"

SEEDED = "2026-08-09T00:00:00Z"
MINTED = "2026-08-10T00:00:00Z"
TENSION_ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")

#: The `assert` claim a morning may state, and the `behave` claim it may not.
#: They share no adjacent word pair, so the builder admits the first — see
#: ``half.context.build``'s withholding rule, which drops a quotable line that
#: echoes a withheld one.
SAYABLE = "swam twice this month"
WITHHELD = "is avoiding the conversation with his brother"

#: The main's own last message, in fourteen writing systems. The morning is
#: unprompted, so this is what the language is read off — and it is the *record*
#: the turn path writes, not a turn, because there is no turn on this path.
SCRIPTS = {
    "latin": "morning — still turning that over",
    "devanagari": "सुबह हो गई, अब भी वही सोच रहा हूँ",
    "thai": "เช้าแล้ว ยังคิดเรื่องนั้นอยู่",
    "japanese": "おはよう。まだそのことを考えている",
    "han": "早上好，还在想那件事",
    "hangul": "좋은 아침, 아직 그 생각 중이야",
    "arabic": "صباح الخير، ما زلت أفكر في ذلك",
    "hebrew": "בוקר טוב, עדיין חושב על זה",
    "cyrillic": "доброе утро, всё ещё об этом думаю",
    "greek": "καλημέρα, ακόμα το σκέφτομαι",
    "bengali": "সুপ্রভাত, এখনও সেটা নিয়েই ভাবছি",
    "tamil": "காலை வணக்கம், இன்னும் அதைப் பற்றியே யோசிக்கிறேன்",
    "amharic": "እንደምን አደሩ፣ አሁንም ስለዚያ እያሰብኩ ነው",
    "khmer": "អរុណសួស្តី ខ្ញុំនៅតែគិតរឿងនោះ",
}


# ── doubles ──────────────────────────────────────────────────────────────────


class FakeChannel:
    """The whole ``Channel`` surface a morning needs, so tests stay offline."""

    name = "fake"

    def __init__(self, reach=Reachability.OPEN):
        self.reach = reach
        self.sent: list[tuple[str, str]] = []
        self.queries: list[str] = []

    def capability_query(self, main_id):
        self.queries.append(main_id)
        return self.reach

    async def send(self, main_id, text):
        self.sent.append((main_id, text))
        return SendResult(external_id="mid-1", parts=1)

    def draft_link(self, text, *, to=None):  # pragma: no cover - never used
        raise AssertionError("the morning surface never drafts to a third party")

    async def receive(self):  # pragma: no cover - never used
        raise AssertionError("the morning surface never receives")


class Holder:
    """The port's narrow generator. One public method, as ``Voice`` requires."""

    def __init__(self, answer, *, sleep=0.0):
        self._answer = answer
        self._sleep = sleep
        self._seen = []

    async def generate(self, work):
        self._seen.append(work)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        reply = self._answer(work) if callable(self._answer) else self._answer
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, str):
            return Completion(text=reply, usage=Usage(micro_usd=9_000))
        return reply

    @property
    def _requests(self):
        return self._seen


class Exploding:
    """A generator that must never be reached, so every *no model call* case
    asserts the call did not happen rather than that a counter stayed at zero."""

    async def generate(self, work):  # pragma: no cover - never run
        raise AssertionError("a model was consulted where none may be")


def a_voice(answer=COMPOSED, *, main=MAIN, sleep=0.0, bound_seconds=1.0, **kw):
    """A ``Voice`` and the holder inside it, so a case can read the prompt."""
    holder = Holder(answer, sleep=sleep)
    return Voice({main: holder}, bound_seconds=bound_seconds, **kw), holder


# ── fixtures over the real store ─────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def a_main(root, *, main_id=MAIN, message=SCRIPTS["latin"], withheld=True):
    """One loop, one tension over one sayable claim and one withheld one, and
    the main's own last message.

    ``message=None`` is a main who has never written — whom story 2's
    ``capability_query`` forbids Half from contacting unprompted, and for whom
    story 13a therefore has no language.
    """
    with Store(Path(root) / main_id) as store:
        store.record(
            Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00:00Z",
            **loops.opened("swim-weekly", state="advancing", timescale="weeks",
                           last_movement="2026-07-01", loops=store.state().loops),
        )
        seed_belief(store, "b_1", SEEDED, subject="self", claim=SAYABLE,
                    rung=License.ASSERT, support=["s_1"], loop="swim-weekly",
                    topics=["swimming"])
        if withheld:
            seed_belief(store, "b_2", SEEDED, subject="self", claim=WITHHELD,
                        rung=License.BEHAVE, loop="swim-weekly",
                        topics=["family"])
            pair = ["b_1", "b_2"]
        else:
            seed_belief(store, "b_3", SEEDED, subject="self",
                        claim="reads two books at once", rung=License.ASSERT,
                        support=["s_3"], loop="swim-weekly", topics=["reading"])
            pair = ["b_1", "b_3"]
        store.record(Op.TENSION, "x_1", MINTED, between=pair, state="fresh",
                     **ladder.admitted())
        # The movement that makes the tension a candidate this morning.
        seed_belief(store, "b_1", "2026-08-11T00:00:00Z", subject="self",
                    claim=SAYABLE, rung=License.ASSERT,
                    support=["s_1", "s_more"], loop="swim-weekly",
                    topics=["swimming"])
        if message is not None:
            seed_message(store, message)


def candidates(*entries):
    return [Candidate(origin=TENSION_ORIGIN, entries=entries or ("b_1", "b_2"))]


def run(registry, channel, voice, *, main_id=MAIN, now=NOW, cands=None,
        mornings=None):
    made = MorningSurface(
        ledger=registry, channel=channel, voice=voice,
        mornings=mornings or Mornings(),
    )
    return asyncio.run(made.surface(
        main_id, now=now, candidates=cands if cands is not None else candidates()
    ))


def view_of(registry, main_id=MAIN):
    return asyncio.run(registry.surface_view(main_id))


def built_context(registry, *, entries=("b_1", "b_2"), main_id=MAIN):
    """The context the surface itself would build, rebuilt here so a case can
    derive the serialization it must not find on the wire."""
    view = view_of(registry, main_id)
    material = tuple(
        RankedBelief(id=ident, claim=view.beliefs.get(ident, {}).get("claim", ""),
                     prefix="", bm25=None, belief=view.beliefs.get(ident) or {})
        for ident in entries
    )
    return build_context(material, now=NOW.stamp, ceiling=view.ceiling)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the ordinary morning — prose on the wire, and nothing else
# ═════════════════════════════════════════════════════════════════════════════


def test_the_wire_carries_prose_and_no_part_of_the_serialization(
    registry, tmp_path
):
    """The headline. Asserted against the context's own rendering.

    Before this story the wire carried ``Context.render()`` verbatim. Every
    token that rendering is made of is derived here — the ``now:`` line, each
    item's label up to its closing bracket, each belief id — and none of them is
    on the wire.
    """
    a_main(tmp_path)
    channel = FakeChannel()
    voice, _ = a_voice()

    outcome = run(registry, channel, voice)
    assert isinstance(outcome, Surfaced)
    sent = channel.sent[0][1]
    assert sent == COMPOSED

    context = built_context(registry)
    assert context.render() not in sent
    assert context.now not in sent
    for item in context:
        assert item.id not in sent
        assert render_line(item) not in sent
        head, bracket, _ = render_line(item).partition("]")
        assert head + bracket not in sent
    for label in (LANGUAGE_SAMPLE, MAY_BE_SAID, BE_MINDFUL_OF, ASK_ABOUT):
        assert label not in sent


def test_the_sayable_claim_reaches_the_generator_and_the_withheld_one_never_does(
    registry, tmp_path
):
    """AD-18 through the whole path: a real fold, the real ladder, the real
    builder, and the prompt the port would have been handed."""
    a_main(tmp_path)
    voice, holder = a_voice()
    run(registry, FakeChannel(), voice)

    turn = holder._requests[0].prompt.turns[0].text
    assert SAYABLE in turn
    assert WITHHELD not in turn
    assert "avoiding the" not in turn and "his brother" not in turn
    # And the withheld belief still *shapes* the morning, which is AD-18's
    # second named failure staying closed.
    assert "topic: family" in turn


def test_a_morning_carries_no_question_at_all(registry, tmp_path):
    """CAP-4 through the composer. The surface buys nothing and hands the
    builder no bought belief, so there is no ask-about block for a model to
    write a question from — the rule arrives as an empty channel rather than as
    a judge refusing a question after the fact."""
    a_main(tmp_path)
    voice, holder = a_voice()
    run(registry, FakeChannel(), voice)
    assert ASK_ABOUT not in holder._requests[0].prompt.turns[0].text


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the fallback is silence, and the day is not claimed
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "answer, reason",
    [
        (lambda work: "x" * (MAX_CHARS + 1), JUDGED),
        (Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED), REFUSED),
        (Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET), OVER_BUDGET),
        (RuntimeError("a build mistake"), RAISED),
    ],
    ids=["judge-refuses-every-attempt", "provider-failing", "over-the-cap",
         "provider-raises"],
)
def test_a_morning_that_cannot_be_composed_sends_nothing_and_spends_no_day(
    registry, tmp_path, answer, reason
):
    """**The ordering test the design notes ask for, by value.**

    Story 10 composes, checks reachability, claims the day, then sends. Story
    13a inserts a generation into that order, and the whole argument for where
    it goes is that a failed one must cost no day. So each failure is driven and
    then a *working* composer is run on the same local day: if the day had been
    claimed, the second morning would come back ``already-today``, and it does
    not.
    """
    a_main(tmp_path)
    channel = FakeChannel()
    voice, _ = a_voice(answer)

    outcome = run(registry, channel, voice)
    assert outcome == Silence(reason)
    assert channel.sent == []
    assert view_of(registry).spoke is None, "a failed morning spent the day"

    working, _ = a_voice()
    again = run(registry, FakeChannel(), working)
    assert isinstance(again, Surfaced), (
        "the day was spent by a morning that never happened"
    )


def test_a_provider_past_the_bound_is_abandoned_and_the_day_survives(
    registry, tmp_path
):
    """*Never blocks past the bound.* The wall-clock bound is the surface's own
    protection: the tick runs many mains under one concurrency bound, and one
    hung provider must not hold a slot."""
    a_main(tmp_path)
    channel = FakeChannel()
    voice, holder = a_voice("too late", sleep=5.0, bound_seconds=0.05)

    assert run(registry, channel, voice) == Silence(PAST_THE_BOUND)
    assert len(holder._requests) == 1, "a slow provider was asked again"
    assert channel.sent == []
    assert view_of(registry).spoke is None


def test_a_main_with_no_model_gets_no_morning_and_no_template(
    registry, tmp_path, caplog
):
    """Matrix: *provider absent*. **Silence, and never a template.**

    A deployment that has equipped nobody sends nothing at all. Before this
    story it sent ``Context.render()``, which is why silence here is the honest
    outcome and not a regression — and nothing anywhere in the tree can put a
    written sentence in its place (``tests/test_voice.py``).
    """
    a_main(tmp_path)
    channel = FakeChannel()

    with caplog.at_level(logging.DEBUG):
        assert run(registry, channel, Voice()) == Silence(NO_MODEL)
    assert channel.sent == []
    assert view_of(registry).spoke is None
    # Ordinary, so nothing above debug says otherwise: an unequipped deployment
    # is a supported shape and not a fault.
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_main_who_has_never_written_gets_no_morning(registry, tmp_path):
    """Matrix: *language*. **Never a default language.**

    The signal always exists where a morning is possible — story 2's
    ``capability_query`` forbids an unprompted send to a main who has never
    written — so this is the fail-closed corner rather than an ordinary
    morning. It is silence rather than a guess, because guessing a language
    from anything other than what somebody wrote is the locale inference this
    product does not do.
    """
    a_main(tmp_path, message=None)
    channel = FakeChannel()
    voice = Voice({MAIN: Exploding()}, bound_seconds=1.0)

    assert run(registry, channel, voice) == Silence(NO_LANGUAGE)
    assert channel.sent == []
    assert view_of(registry).spoke is None


def test_an_unreachable_main_is_never_composed_for(registry, tmp_path):
    """Asking the platform is free; paying a provider is not. A generator that
    raises on contact is what makes this an assertion about the *order* rather
    than about a counter."""
    a_main(tmp_path)
    channel = FakeChannel(reach=Reachability.WINDOW_CLOSED)
    voice = Voice({MAIN: Exploding()}, bound_seconds=1.0)

    outcome = run(registry, channel, voice)
    assert isinstance(outcome, Silence) and outcome.reason in REASONS
    assert channel.queries == [MAIN]
    assert channel.sent == []


def test_an_empty_morning_is_answered_before_a_provider_is_paid(
    registry, tmp_path
):
    """Matrix: *empty content*. Story 10 already leaves this silent, and the
    composer must not turn it into a call."""
    a_main(tmp_path)
    voice = Voice({MAIN: Exploding()}, bound_seconds=1.0)
    assert run(registry, FakeChannel(), voice, cands=[]) == Silence(NOTHING_TO_SAY)


def test_a_main_in_crisis_is_never_composed_for(registry, tmp_path):
    """Matrix: *crisis*. No generation at all — the crisis path owns the turn,
    and its replies stay joins of reviewed template lines."""
    a_main(tmp_path)
    asyncio.run(registry.suspend_for_crisis(
        MAIN, t="2026-08-31T00:00:00Z", tier="disclosure", score=2
    ))
    channel = FakeChannel()
    voice = Voice({MAIN: Exploding()}, bound_seconds=1.0)

    assert run(registry, channel, voice) == Silence(CRISIS)
    assert channel.sent == [] and channel.queries == []


def test_no_failure_on_this_path_reaches_the_scheduler(registry, tmp_path):
    """*No exception reaches the scheduler.* One main's failing provider costs
    that main their morning and never the pass, and never anybody else's."""
    a_main(tmp_path)
    voice, _ = a_voice(RuntimeError("boom"))
    work = MorningPass(
        consolidate=_Pass(), surface=MorningSurface(
            ledger=registry, channel=FakeChannel(), voice=voice
        ),
    )
    assert asyncio.run(work.run(MAIN, NOW)) is None


class _Pass:
    """A consolidation pass that produces this file's one candidate."""

    async def evaluate(self, main_id, now):
        from half.consolidate.pass_ import PassResult

        return PassResult(candidates=tuple(candidates()))


# ═════════════════════════════════════════════════════════════════════════════
# matrix: a behave claim leaks — nothing is sent, and it is loud
# ═════════════════════════════════════════════════════════════════════════════


def test_a_leaked_behave_claim_stops_the_send_and_is_loud(
    registry, tmp_path, caplog
):
    """**Asserted by what is not sent.**

    A tripwire that quietly stripped the wording would send a plausible message
    and pass any case that inspected it. So this asserts ``channel.sent == []``:
    a redacting implementation fails here, which is the point.

    And it is loud — an ``error``, because a trip means either that a model
    repeated a withheld wording or that AD-18 has stopped being enforced at
    context construction, and the second is a launch-blocking defect that must
    not look like a quiet morning.
    """
    a_main(tmp_path)
    channel = FakeChannel()
    voice, holder = a_voice(f"you {WITHHELD} again")

    with caplog.at_level(logging.DEBUG):
        outcome = run(registry, channel, voice)

    assert outcome == Silence(LEAKED)
    assert channel.sent == [], "the leaked morning was cleaned up and sent"
    assert view_of(registry).spoke is None, "a leaked morning spent the day"
    assert len(holder._requests) == 1, "a leak bought a regeneration"

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "the tripwire fired silently"
    assert any("AD-18" in r.getMessage() for r in errors)
    # And nothing anywhere in the alarm carries what set it off (AD-22).
    for record in caplog.records:
        haystack = record.getMessage() + repr(record.args)
        assert "brother" not in haystack and "avoiding" not in haystack


def test_a_leak_is_counted_as_a_fault_rather_than_as_a_quiet_morning(
    registry, tmp_path
):
    a_main(tmp_path)
    mornings = Mornings()
    voice, _ = a_voice(f"you {WITHHELD} again")
    run(registry, FakeChannel(), voice, mornings=mornings)

    assert mornings.silences == {LEAKED: 1}
    assert mornings.faults == 1
    assert set(mornings.silences) <= REASONS


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the language, in every script, and never as content
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("script", sorted(SCRIPTS), ids=sorted(SCRIPTS))
def test_the_language_the_main_last_wrote_in_reaches_the_generator(
    registry, tmp_path, script
):
    """Matrix: *the main last wrote in Thai → the morning is in Thai*.

    What is assertable offline is that the signal gets there and gets there
    whole: the sample the log holds is in the prompt, under the language label,
    in the script the main used. Whether the model then answers in it is the
    model's, and no arrangement of green cases here is evidence about that.
    """
    words = SCRIPTS[script]
    a_main(tmp_path, message=words)
    voice, holder = a_voice()

    assert isinstance(run(registry, FakeChannel(), voice), Surfaced)
    turn = holder._requests[0].prompt.turns[0].text
    language, _, rest = turn.partition(MAY_BE_SAID)
    assert LANGUAGE_SAMPLE in language
    assert words in language
    assert words not in rest, "the sample reached a channel that is not language"


@pytest.mark.parametrize("script", sorted(SCRIPTS), ids=sorted(SCRIPTS))
def test_the_sample_is_read_off_the_log_and_not_off_a_turn(
    registry, tmp_path, script
):
    """The morning is unprompted, so there is no turn to read a language from.
    ``half.actor.runtime`` records every inbound message as a `stated`-ledger
    belief, and this is what makes the rule work on the one path where nobody
    has just written."""
    words = SCRIPTS[script]
    a_main(tmp_path, message=words)
    assert sample_from(view_of(registry).beliefs) == Sample(words)


@pytest.mark.parametrize("script", sorted(SCRIPTS), ids=sorted(SCRIPTS))
def test_the_sample_cannot_reach_the_quotable_channel_through_the_surface(
    registry, tmp_path, script
):
    """The structural rule, driven end to end.

    The sample belief is `behave`-licensed like every message the turn path
    records, so it is not quotable material and never becomes any. What is
    asserted here is stronger than *it is not quoted*: the quotable block of the
    prompt is byte-identical whatever the main last wrote, so it is a pure
    function of the context and there is no path by which a language signal
    could turn into content.
    """
    a_main(tmp_path, message=SCRIPTS[script])
    voice, holder = a_voice()
    run(registry, FakeChannel(), voice)

    turn = holder._requests[0].prompt.turns[0].text
    said = next(
        block[len(MAY_BE_SAID):].strip()
        for block in turn.split("\n\n") if block.startswith(MAY_BE_SAID)
    )
    assert said == SAYABLE
    assert SCRIPTS[script] not in said


def test_no_locale_country_or_timezone_is_derived_from_the_sample(
    registry, tmp_path
):
    """*Answering in kind, not inferring a region.* The standing rule is that
    Half is told its main's locale and never infers it, because guessing a
    region from a script is how a product gets somebody's crisis line wrong.

    The prompt is the whole of what the composer produces, so this asserts that
    nothing in it names a place, a zone or a country — and the surface's own
    zone, which it *is* told and does use for the day boundary, is not in it
    either.
    """
    a_main(tmp_path, message=SCRIPTS["thai"])
    voice, holder = a_voice()
    run(registry, FakeChannel(), voice)

    prompt = holder._requests[0].prompt
    whole = "\n".join((*prompt.system, *(t.text for t in prompt.turns)))
    for token in ("Asia/", "UTC", "timezone", "country", "locale", "region"):
        assert token not in whole


# ═════════════════════════════════════════════════════════════════════════════
# AD-22: no generated string is durable, anywhere
# ═════════════════════════════════════════════════════════════════════════════


def _tree_bytes(root: Path) -> bytes:
    """Every byte under a main's directory — log, projections and SQLite."""
    return b"".join(
        path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()
    )


def _log_bytes(root: Path) -> bytes:
    """Every byte of the append-only log — **the only authority** (AD-3).

    The derived stores are deliberately not compared: SQLite rewrites its own
    header on any open, so a byte comparison over the whole tree would report a
    difference for a morning that wrote nothing at all. What must not move when
    Half says nothing is the log, and everything else is a fold over it.
    """
    return b"".join(
        path.read_bytes()
        for path in sorted(root.rglob("*.jsonl"))
        if path.is_file()
    )


@pytest.mark.parametrize("script", sorted(SCRIPTS), ids=sorted(SCRIPTS))
def test_no_generated_string_is_written_anywhere(registry, tmp_path, script):
    """Matrix: *durability*. The log records that a morning was sent, never what
    it said (AD-22).

    Swept over scripts because a scan of a tree is a byte comparison and a
    fixture in one script proves one script's encoding.
    """
    words = SCRIPTS[script]
    a_main(tmp_path, message=words)
    composed = f"{COMPOSED} {words}"
    voice, _ = a_voice(composed)
    channel = FakeChannel()

    assert isinstance(run(registry, channel, voice), Surfaced)
    assert channel.sent[0][1] == composed
    registry.close()

    written = _tree_bytes(tmp_path / MAIN)
    assert COMPOSED.encode() not in written, "a generated string reached the tree"
    assert composed.encode() not in written
    # The main's own message *is* in the log — the turn path put it there, and
    # that is the record the language is read off. What must not be there is
    # anything Half composed.
    assert words.encode() in written


@pytest.mark.parametrize("script", sorted(SCRIPTS), ids=sorted(SCRIPTS))
def test_no_log_line_on_the_morning_path_carries_a_word_of_it(
    registry, tmp_path, caplog, script
):
    """AD-22 over the **whole** path, not just the composer's own modules.

    ``tests/test_voice.py`` scans the voice package's logging; this scans the
    surface's, the registry's, the channel's and everything else a morning
    touches — which is a different set, and a gap mutation found: adding
    ``logger.info("morning for main=%s said %s", main_id, text)`` to
    ``half.surface.morning`` survived every case in this file, because nothing
    here had ever read a log record.

    Every outcome is driven — sent, judged, leaked, failed — and both the
    generated text and the main's own words are looked for in each record's
    message *and* in its arguments, which is where an interpolated value
    actually sits. Swept over scripts because a scan written against one proves
    one encoding.
    """
    words = SCRIPTS[script]
    composed = f"{COMPOSED} {words}"

    with caplog.at_level(logging.DEBUG):
        for i, answer in enumerate((
            composed,
            "x" * (MAX_CHARS + 1),
            f"you {WITHHELD} again",
            Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
        )):
            main_id = f"main{i}"
            a_main(tmp_path, main_id=main_id, message=words)
            voice, _ = a_voice(answer, main=main_id)
            run(registry, FakeChannel(), voice, main_id=main_id)

    for record in caplog.records:
        haystack = record.getMessage() + repr(record.args)
        for forbidden in (COMPOSED, composed, words, WITHHELD, SAYABLE):
            assert forbidden not in haystack, (
                f"{record.name} logged content: {record.getMessage()!r}"
            )


def test_a_silent_morning_writes_nothing_at_all(registry, tmp_path):
    a_main(tmp_path)
    before = _log_bytes(tmp_path / MAIN)
    voice, _ = a_voice(Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED))
    run(registry, FakeChannel(), voice)
    registry.close()
    assert _log_bytes(tmp_path / MAIN) == before


def test_the_fold_replays_identically_after_a_morning_was_sent(
    registry, tmp_path
):
    """Matrix: *replay*. A morning is an outcome recorded, never a promise to
    re-derive (AD-30) — so a rebuild must produce the same state, and no
    generated text can materialize because none was ever written."""
    a_main(tmp_path)
    voice, _ = a_voice()
    assert isinstance(run(registry, FakeChannel(), voice), Surfaced)
    registry.close()

    with Store(tmp_path / MAIN) as store:
        before = store.state()
        rebuilt = store.rebuild()
    assert rebuilt == before
    assert COMPOSED.encode() not in _tree_bytes(tmp_path / MAIN)


# ═════════════════════════════════════════════════════════════════════════════
# the shipped composition
# ═════════════════════════════════════════════════════════════════════════════


def test_the_composer_reaches_the_shipped_product_by_value(tmp_path):
    """A surface reachable only from a test is a surface nobody has run. Three
    stories shipped one before the composition root existed; this asserts the
    composer is not the fourth, by identity rather than by finding a keyword in
    the source."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        assert isinstance(wiring.voice, Voice)
        assert wiring.scheduler.work.surface.voice is wiring.voice
    finally:
        wiring.registry.close()


def test_a_main_with_a_tier_and_a_key_is_equipped_to_be_spoken_to(tmp_path):
    """The real provider, built from the real secret store — offline, because
    the SDK builds no client until it is asked to send something."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, TIERS_ENV, load
    from half.model.anthropic_transport import MODEL_KEY
    from half.secrets import FileSecretStore

    root = tmp_path / "mains"
    root.mkdir()
    FileSecretStore.beside(root).put(MAIN, MODEL_KEY, "sk-not-a-real-key")
    config = load({ROOT_ENV: str(root), MAINS_ENV: f"123:{MAIN}",
                   TIERS_ENV: f"{MAIN}:cheap"})
    wiring = build(config, token="123:fake")
    try:
        assert wiring.voice.holds(MAIN)
    finally:
        wiring.registry.close()


def test_a_main_with_no_tier_is_refused_rather_than_defaulted(tmp_path, caplog):
    """AD-20's own rule, and its consequence stated out loud: a deployment that
    sets ``HALF_MAINS`` and not ``HALF_MODEL_TIERS`` sends no unprompted
    mornings. A silent fallback tier is either a bill nobody authorised or a
    quality regression nobody sees; a silent fallback *sentence* is worse."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load
    from half.model.anthropic_transport import MODEL_KEY
    from half.secrets import FileSecretStore

    root = tmp_path / "mains"
    root.mkdir()
    FileSecretStore.beside(root).put(MAIN, MODEL_KEY, "sk-not-a-real-key")
    config = load({ROOT_ENV: str(root), MAINS_ENV: f"123:{MAIN}"})
    with caplog.at_level(logging.WARNING):
        wiring = build(config, token="123:fake")
    try:
        assert not wiring.voice.holds(MAIN)
        assert any("AD-20" in r.getMessage() for r in caplog.records)
    finally:
        wiring.registry.close()


def test_the_holder_the_wiring_hands_over_is_the_narrow_generator(tmp_path):
    """``Voice`` refuses a holder with any public method but ``generate``, so a
    wiring that handed over the provider — which can reset a ledger and reach a
    batcher — would have raised at construction and equipped nobody."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, TIERS_ENV, load
    from half.model.anthropic import AnthropicGenerator
    from half.model.anthropic_transport import MODEL_KEY
    from half.secrets import FileSecretStore

    root = tmp_path / "mains"
    root.mkdir()
    FileSecretStore.beside(root).put(MAIN, MODEL_KEY, "sk-not-a-real-key")
    config = load({ROOT_ENV: str(root), MAINS_ENV: f"123:{MAIN}",
                   TIERS_ENV: f"{MAIN}:frontier"})
    wiring = build(config, token="123:fake")
    try:
        assert wiring.voice.holds(MAIN)
        source = (ROOT / "half" / "__main__.py").read_text(encoding="utf-8")
        assert "provider.generator()" in source
        assert AnthropicGenerator is not None
    finally:
        wiring.registry.close()


def test_the_shipped_tick_sends_one_composed_morning(tmp_path):
    """Run, not grepped: the object graph the product builds, a real store, a
    real tick, a real touch in a real log — with the *provider* stubbed at
    exactly the seam the transport is stubbed at, and everything above it the
    shipped object."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    a_main(tmp_path)
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    transport = FakeTransport()
    voice, holder = a_voice()
    try:
        wiring.channel.transport = transport
        wiring.scheduler.work = replace(
            wiring.scheduler.work,
            surface=replace(wiring.scheduler.work.surface, voice=voice),
        )
        wiring.channel.reach.note_inbound(MAIN, epoch=NOON - 3600)
        asyncio.run(wiring.registry.note_pass(
            MAIN, t=stamp(NOON - 600),
            fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC",
                    TOLD_ZONE: False},
        ))
        wiring.scheduler.clock = FrozenClock(at=NOON)
        assert asyncio.run(wiring.scheduler.tick()).ran == (MAIN,)
        assert len(transport.sent) == 1
        assert transport.sent[0][1] == COMPOSED
        assert SAYABLE in holder._requests[0].prompt.turns[0].text
        assert wiring.mornings.sent == 1
    finally:
        wiring.registry.close()


def test_a_second_morning_the_same_day_is_still_refused(registry, tmp_path):
    """The composer changed what a morning *says* and nothing about how often
    Half says one (CAP-8). Asserted here because a generation that failed and a
    generation that succeeded now take different paths to the claim."""
    a_main(tmp_path)
    voice, _ = a_voice()
    assert isinstance(run(registry, FakeChannel(), voice), Surfaced)
    assert run(registry, FakeChannel(), voice) == Silence(ALREADY_TODAY)
