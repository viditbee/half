"""CAP-7 story 9e: the disagreement judge — one case per row of the matrix.

Four things this file refuses to do, because each would let it pass while the
product failed:

**It proves the distinction the whole story turns on.** A tension is two entries
that *disagree where neither is wrong*; a plain contradiction is a different
object with a different home (story 12). A judge that minted contradictions
would look exactly like a judge that worked, so the contradiction row is driven
end to end — the judge answers ``False``, the pass mints nothing, and the tally
counts it apart from an ordinary *no* so that an operator can see a model
answering the wrong one.

**It keeps the three values apart, and *cannot say* apart from *no answer*.**
Both come back as ``None`` and both mint nothing, which is exactly the shape a
suite asserting *"nothing was minted"* cannot tell apart. Every case here says
which of the three it is testing and asserts a count that only that one moves.

**It asserts what leaves the machine, against the rendered request.** *"Two
claims and nothing else"* is checked against the payload the real provider would
send, with a seeded ledger on disk — not against a docstring — and the sentinel
that reaches the provider is then hunted through the log file, the projections,
the tally, the result and every captured log line.

**It does not read either claim, and neither does the judge.** The cases run in
five scripts, in mixed pairs, and assert that the request is byte-identical
apart from the claims themselves — which is the only form *"no English rubric
and no locale"* can take for a module whose whole job is to forward two
sentences it must not interpret.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import math
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.consolidate import judge as judging
from half.consolidate.candidates import Couple, Entry, key_of
from half.consolidate.judge import (
    ALARM_AFTER,
    ALARM_RATE,
    ALLOWED_METHODS,
    ANSWER_FOR_LABEL,
    BOUND_SECONDS,
    CLASSIFY_TIER,
    BREAK_AFTER,
    BREAK_FOR,
    CANNOT_BOTH_BE_TRUE,
    CANNOT_SAY,
    INSTRUCTIONS,
    LABELS,
    NO_TENSION,
    PER_CALL_MICRO_USD,
    PER_PASS_MICRO_USD,
    REPORT_EVERY,
    SEPARATOR,
    SEPARATOR_MARK,
    SHARE_OF_TICK,
    TENSION,
    Judge,
    Judges,
    Tally,
    claims_of,
    prompt_for,
)
from half.consolidate.mint import JUDGEMENTS
from half.consolidate.pass_ import TensionPass
from half.consolidate.port import Disagreement
from half.errors import JudgeError
from half.model import consult
from half.model.budget import Budget
from half.model.port import (
    Classify,
    Decision,
    Failure,
    Kind,
    Reason,
    Role,
    Usage,
)
from half.schedule.clock import moment, stamp
from half.schedule.tick import DEFAULT_TIMEOUT
from half.store.records import NEXT_PASS_AT, PASS_RAN, TOLD_ZONE, ZONE
from half.store.store import Store
from half.tensions.states import STATE

from tests.conftest import door_of, seed_belief

ROOT = Path(__file__).resolve().parents[1]

MAIN = "vidit"
OTHER_MAIN = "asha"

#: 2026-09-01T12:00:00Z — the instant ``tests/test_minting.py``,
#: ``tests/test_pass.py`` and ``tests/test_schedule.py`` all build from.
NOON = 1_788_264_000.0
NOW = moment(NOON)
LAST_PASS = NOON - 86_400
SETTLED = stamp(NOON - 172_800)
STIRRED = stamp(NOON - 3_600)

#: The canonical tension, in the spec's own words.
SAID = "means to buy the farmland this year"
DID = "has not opened a listing since March"

#: Five scripts, so that *"any script"* is a run rather than a sentence. None of
#: them is a translation of another: the point is that the judge does not care.
SCRIPTS: dict[str, tuple[str, str]] = {
    "latin": (SAID, DID),
    "devanagari": ("इस साल खेत खरीदने का इरादा है",
                   "मार्च से कोई सूची नहीं खोली"),
    "amharic": ("በዚህ ዓመት እርሻውን ለመግዛት አስቧል",
                "ከመጋቢት ጀምሮ ዝርዝር አልከፈተም"),
    "arabic": ("ينوي شراء المزرعة هذا العام",
               "لم يفتح أي قائمة منذ آذار"),
    "han": ("打算今年买下那块农田", "自三月起未曾挂牌"),
}

#: A pair whose two halves are in two *different* scripts, which is the row the
#: spec singles out: the revealed side can come out of ingested mail while the
#: stated side is the main's own words.
MIXED: tuple[str, str] = (SCRIPTS["devanagari"][0], SCRIPTS["amharic"][1])


# ── the doubles ──────────────────────────────────────────────────────────────


class Holder:
    """The port's narrow classifier, and nothing wider.

    ``answers`` are used in order and the last repeats. ``calls`` is public and
    is deliberately a count rather than a raise: every *"the model was never
    consulted"* row asserts ``holder.calls == 0``, because a double that raised
    would be caught by the judge's own fail-open handler and the case would pass
    whether or not the call was made.
    """

    def __init__(self, *answers: object, sleep: float = 0.0) -> None:
        # Private, because ``Judges`` refuses a holder with any public callable
        # but ``classify`` — and an ``answers`` list of lambdas is a public
        # callable. The double is held to the shape of the real thing.
        self._answers = list(answers) or [None]
        self._sleep = sleep
        self.seen: list[Classify] = []

    async def classify(self, work: Classify) -> object:
        self.seen.append(work)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        index = min(len(self.seen), len(self._answers)) - 1
        answer = self._answers[index]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    @property
    def calls(self) -> int:
        return len(self.seen)


class Counting:
    """A transport that counts, so *refused before the transport is touched* is
    asserted at the wire rather than from below.

    It answers rather than raising: a raise would be swallowed into a ``None``
    and the case would pass whether or not the call was made.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.payloads: list[dict] = []

    async def message(self, payload):
        self.calls += 1
        self.payloads.append(dict(payload))
        return {
            "content": [{"type": "text", "text": '{"label": "no_tension"}'}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 5},
        }

    async def batch_create(self, requests): ...
    async def batch_status(self, batch_id): ...
    def batch_results(self, batch_id): ...


def labelled(label: str) -> Decision:
    return Decision(label=label, usage=Usage(input_tokens=120, micro_usd=900))


def bench(
    *answers: object,
    main: str = MAIN,
    sleep: float = 0.0,
    bound_seconds: float = 0.5,
) -> tuple[Judges, Holder]:
    holder = Holder(*answers, sleep=sleep)
    return Judges({main: holder}, bound_seconds=bound_seconds), holder


def asked(
    one: Judges, said: str = SAID, did: str = DID, main: str = MAIN
) -> bool | None:
    """One judgement, through the seam the pass actually uses."""
    seat = one.for_main(main)
    assert seat is not None, "the bench handed out no judge"
    return asyncio.run(seat.disagree(entry_of("b_said", said),
                                     entry_of("b_did", did)))


def entry_of(ident: str, claim: str, **kw) -> Entry:
    return Entry(id=ident, at=STIRRED, claim=claim, **kw)


# ── a real main, a real log, a real pass ─────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def seeded(registry, tmp_path, main_id=MAIN, pair=(SAID, DID)):
    """The canonical couple in a real log: one stated entry changed since the
    last pass, one revealed entry sharing its subject."""
    with Store(Path(tmp_path) / main_id) as store:
        seed_belief(store, "b_said", STIRRED, subject="farmland",
                    ledger="stated", claim=pair[0])
        seed_belief(store, "b_did", SETTLED, subject="farmland",
                    ledger="revealed", claim=pair[1])
    asyncio.run(registry.note_pass(
        main_id, t=stamp(LAST_PASS),
        fields={NEXT_PASS_AT: stamp(NOON), ZONE: "UTC", TOLD_ZONE: False,
                PASS_RAN: True},
    ))
    return main_id


def run_pass(registry, main_id, *, seat, now=NOW):
    return asyncio.run(
        TensionPass(ledger=registry, bench=seat).evaluate(main_id, now)
    )


# ═════════════════════════════════════════════════════════════════════════════
# the semantic core: the gap, never the truth
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_canonical_tension_is_minted(registry, tmp_path):
    """Matrix: *the canonical tension*. Both true, pulling apart.

    Driven through a real log and the shipped pass so the answer is worth
    something: the judge says yes, the mint lands, and the record links the two.
    """
    seeded(registry, tmp_path)
    seat, holder = bench(labelled(TENSION))
    result = run_pass(registry, MAIN, seat=seat)

    assert holder.calls == 1
    assert result.minted.minted == (key_of("b_said", "b_did"),)
    held = registry.tension_table(MAIN)[key_of("b_said", "b_did")]
    assert set(held["between"]) == {"b_said", "b_did"}
    assert held[STATE] == "fresh"
    assert seat.tally.minted == 1


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_plain_contradiction_answers_no_and_is_never_minted(
    registry, tmp_path
):
    """Matrix: *a plain contradiction*. **The case this story exists for.**

    Two entries that cannot both be true are story 12's object: the main said
    something false, Half asks, and a belief is removed. Minting a permanent
    link between them instead would be a worse story 12 wearing CAP-7's
    clothes — and it would mint steadily and plausibly, which is why the
    failure is the one this story most plausibly ships.

    Driven end to end, and the tally is asserted as well as the log: *nothing
    was minted* is true of a contradiction answered correctly **and** of a judge
    that was never reached, which is the shape this project has shipped and
    taken back twice. ``contradictions`` is the number that only the first
    moves.
    """
    seeded(registry, tmp_path, pair=("sold the farmland in April",
                                     "still owns the farmland"))
    seat, holder = bench(labelled(CANNOT_BOTH_BE_TRUE))
    result = run_pass(registry, MAIN, seat=seat)

    assert holder.calls == 1, "the judge was never asked"
    assert result.minted.minted == ()
    assert result.minted.passed == (key_of("b_said", "b_did"),)
    assert registry.tension_table(MAIN) == {}
    # The two facts a *"nothing was minted"* assertion cannot tell apart.
    assert seat.tally.contradictions == 1
    assert seat.tally.answers.get(NO_TENSION, 0) == 0
    assert seat.tally.minted == 0
    assert seat.tally.fell_back == 0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_contradiction_has_a_home_that_is_not_the_minting_label():
    """Why the label set has four members and not three.

    *Disagree* is the word a model reads as *contradict*, because that is what
    it means nearly everywhere else. With three labels a plain contradiction has
    to be answered ``no_tension`` — the answer a model is least likely to give
    about the pair that feels most like a disagreement. The fourth label is the
    argument ``half.crisis.classifier`` already makes for ``another_at_risk``:
    the value of a label that acts on nothing is that the reading has somewhere
    to go other than the one that acts.

    Asserted on the *shape* of the mapping rather than on a model's behaviour,
    which no test can pin: a home exists, it is distinct from every other label,
    it answers no, and the instructions say in as many words that it is not a
    tension.
    """
    assert CANNOT_BOTH_BE_TRUE in LABELS
    assert CANNOT_BOTH_BE_TRUE != NO_TENSION != TENSION
    assert ANSWER_FOR_LABEL[CANNOT_BOTH_BE_TRUE] is False
    block = next(b for b in INSTRUCTIONS if b.startswith(CANNOT_BOTH_BE_TRUE))
    assert "not a tension" in block
    assert "never tension" in block
    assert "handled elsewhere" in block


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_label_set_that_minted_a_contradiction_refuses_the_module(
    monkeypatch
):
    """The bypass case for the rule above. A guard nobody has tried to defeat is
    a guard resting on nothing, so the mapping is mutated the way a careless
    edit would mutate it and the module is asked to accept itself."""
    monkeypatch.setattr(
        judging, "ANSWER_FOR_LABEL",
        {**ANSWER_FOR_LABEL, CANNOT_BOTH_BE_TRUE: True},
    )
    with pytest.raises(JudgeError, match="cannot both be true"):
        judging._check_constants()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_second_minting_label_refuses_the_module(monkeypatch):
    """Exactly one label records anything. A second way to reach that record is
    a second meaning it can have, and nothing downstream could tell them
    apart."""
    monkeypatch.setattr(
        judging, "ANSWER_FOR_LABEL",
        {**ANSWER_FOR_LABEL, NO_TENSION: True},
    )
    with pytest.raises(JudgeError, match="exactly one label"):
        judging._check_constants()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_label_set_with_no_home_for_a_contradiction_refuses_the_module(
    monkeypatch
):
    """Deleting the label is the other way to lose the distinction, and it is
    the one that looks like tidying: three labels carry the three values, so a
    reader who has not read this module's first paragraph will see a redundant
    fourth.

    It refuses by name rather than by ``KeyError``, which is what the check
    beneath it used to do — and a ``KeyError`` out of an import-time guard says
    *this build is broken* where what a reader needs is *why this label is
    there*.
    """
    monkeypatch.setattr(
        judging, "ANSWER_FOR_LABEL",
        {label: answer for label, answer in ANSWER_FOR_LABEL.items()
         if label != CANNOT_BOTH_BE_TRUE},
    )
    monkeypatch.setattr(
        judging, "LABELS",
        tuple(label for label in LABELS if label != CANNOT_BOTH_BE_TRUE),
    )
    with pytest.raises(JudgeError, match="no home for a contradiction"):
        judging._check_constants()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_label_set_with_nowhere_to_put_doubt_refuses_the_module(monkeypatch):
    """The third value's own bypass case, and it was missing until a mutation
    said so.

    Collapsing ``cannot_say`` into ``no`` refuses this module at import — which
    is red, and is red everywhere at once, and therefore names nothing. This is
    the case that says *what* was wrong: a judge with nowhere to put doubt makes
    a model that is unsure answer *no*, and then a suite asserting *"nothing was
    minted"* passes whether the judge answered or was never reached at all.
    """
    monkeypatch.setattr(
        judging, "ANSWER_FOR_LABEL", {**ANSWER_FOR_LABEL, CANNOT_SAY: False},
    )
    with pytest.raises(JudgeError, match="cannot say"):
        judging._check_constants()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize("label", [NO_TENSION, CANNOT_BOTH_BE_TRUE])
def test_agreement_and_the_unrelated_pair_answer_no(label, registry, tmp_path):
    """Matrix: *agreement* and *unrelated*. Both are ``no_tension`` to the
    model and both are ``False`` here; the contradiction is parametrised beside
    them so that a build collapsing the two labels fails on one row and not the
    other."""
    seeded(registry, tmp_path)
    seat, holder = bench(labelled(label))
    result = run_pass(registry, MAIN, seat=seat)

    assert holder.calls == 1
    assert result.minted.minted == ()
    assert result.minted.passed == (key_of("b_said", "b_did"),)
    assert result.minted.unsaid == (), "a *no* was booked as a *cannot say*"
    assert seat.tally.refused == 1
    assert seat.tally.answers[label] == 1


# ═════════════════════════════════════════════════════════════════════════════
# the third value, which cannot collapse into the second
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_model_that_cannot_say_answers_none_and_is_not_a_failure():
    """Matrix: *cannot say*. The model **ran** and is unsure.

    ``None``, never ``False`` — and not a failure either, which is the half a
    fallback-shaped implementation gets wrong: the provider is up and answering,
    so this must not arm the breaker and must not enter the rate an operator
    watches for an outage.
    """
    seat, holder = bench(labelled(CANNOT_SAY))
    assert asked(seat) is None
    assert holder.calls == 1
    assert seat.tally.unsure == 1
    assert seat.tally.fell_back == 0
    assert seat.tally.failure_rate == 0.0
    assert seat.tally.answered == 1


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_an_answered_cannot_say_never_arms_the_breaker():
    """The bypass for the sentence above: driven past ``BREAK_AFTER`` and two
    more, with a call actually made every single time.

    A build that treated *cannot say* as a fallback would stand the main down
    after five ambiguous couples and mint nothing for the rest of the night, for
    a provider that was working perfectly.
    """
    seat, holder = bench(labelled(CANNOT_SAY))
    for _ in range(BREAK_AFTER + 2):
        assert asked(seat) is None
    assert holder.calls == BREAK_AFTER + 2, "the breaker silenced a live model"
    assert seat.tally.skipped == 0
    assert seat.tally.unsure == BREAK_AFTER + 2


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize(
    "failure",
    [
        Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
        Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED),
        Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET),
        Failure(Kind.MALFORMED, Reason.TRUNCATED),
    ],
    ids=lambda f: f.because.value,
)
def test_a_degraded_or_declining_provider_answers_none_and_never_no(failure):
    """Matrix: *provider degraded, declining, over budget*. Every one of the
    port's four kinds, so a build that special-cased one of them fails on the
    others.

    ``None`` rather than ``False``, because *the judge said no* and *the judge
    could not say* are different facts and only one of them is about the two
    entries. And counted **apart from an answered** ``cannot_say``: both come
    back ``None``, and the tally is where they stop being the same thing.
    """
    seat, holder = bench(failure)
    assert asked(seat) is None
    assert holder.calls == 1
    assert seat.tally.unsure == 0, "a provider fault was booked as an answer"
    assert seat.tally.fell_back == 1
    assert seat.tally.failures == {f"{failure.kind}/{failure.because}": 1}
    assert seat.tally.failure_rate == 1.0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_two_kinds_of_none_are_two_numbers_in_one_tally():
    """The counting-apart rule, stated as the arithmetic it has to be.

    One judgement that answered *cannot say* and one that never answered look
    identical to the pass — two ``None``s, nothing minted, two entries in
    ``MintResult.unsaid``. This is the only place the difference survives, so
    it is asserted as a difference rather than as two separate facts.
    """
    seat, _ = bench(labelled(CANNOT_SAY),
                    Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED))
    assert asked(seat) is None
    assert asked(seat) is None
    assert seat.tally.consulted == 2
    assert (seat.tally.unsure, seat.tally.fell_back) == (1, 1)
    assert seat.tally.answered == 1
    assert seat.tally.failure_rate == 0.5


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize(
    "reply",
    [
        Decision(label="yes"),
        Decision(label="Tension"),
        Decision(label="tension."),
        Decision(label=object()),
        "tension",
        True,
        None,
        object(),
    ],
    ids=["other-set", "cased", "punctuated", "not-text", "prose", "bare-true",
         "nothing", "opaque"],
)
def test_an_unreadable_answer_is_none_and_is_never_guessed(reply):
    """Matrix: *unreadable answer*. A reply the label set does not contain.

    **Nothing is coerced.** ``Tension`` and ``tension.`` are booked unreadable
    rather than matched to their nearest neighbour, which is the reviewed rule
    both classification paths already apply: a judge that guesses which label a
    sentence probably meant is one that will eventually guess ``tension`` for
    ``cannot_both_be_true``. The direction of the loss is safe — a near miss
    costs a counted failure and an unminted couple, never a wrong mint.
    """
    seat, _ = bench(reply)
    assert asked(seat) is None
    assert seat.tally.unreadable == 1
    assert seat.tally.answers == {}
    assert seat.tally.minted == 0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_nothing_is_minted_from_false_or_from_none(registry, tmp_path):
    """The two verdicts that record nothing, driven through the log rather than
    through the judge, and kept apart on the result: ``passed`` is *the judge
    said no* and ``unsaid`` is *the judge could not say*."""
    for label, field in ((NO_TENSION, "passed"), (CANNOT_SAY, "unsaid")):
        with Store(Path(tmp_path) / f"m_{label}") as _:
            pass
        main = seeded(registry, tmp_path, main_id=f"m_{label}")
        seat, _ = bench(labelled(label), main=main)
        result = run_pass(registry, main, seat=seat)
        assert result.minted.minted == ()
        assert getattr(result.minted, field) == (key_of("b_said", "b_did"),)
        assert registry.tension_table(main) == {}


# ═════════════════════════════════════════════════════════════════════════════
# the bound, and the arithmetic that makes it fit
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_full_budget_of_judgements_fits_inside_the_ticks_per_main_timeout():
    """Matrix: *the bound fits*. **Asserted as a relation, not written in a
    comment** — story 13a shipped exactly this kind of cross-constant claim in
    a comment with nothing pinning it.

    ``JUDGEMENTS`` is the most one main's pass may buy, ``BOUND_SECONDS`` is the
    most one of them may take, and ``DEFAULT_TIMEOUT`` is the whole of what the
    tick gives that main. The worst case has to leave room for the
    re-evaluation and the appends, which is what ``SHARE_OF_TICK`` names: the
    judgements may have half the slot, and the half that is left is not slack —
    ``Store.append`` re-folds the log and rebuilds the view once per transition.

    Pinned by value as well as by relation, so that widening the share is a red
    test and a deliberate edit rather than a quiet way to buy a longer bound.
    """
    assert (JUDGEMENTS, BOUND_SECONDS, SHARE_OF_TICK) == (24, 5.0, 0.5)
    assert DEFAULT_TIMEOUT == 300.0
    assert JUDGEMENTS * BOUND_SECONDS == 120.0
    assert JUDGEMENTS * BOUND_SECONDS <= SHARE_OF_TICK * DEFAULT_TIMEOUT
    # And there is real room: the worst case leaves three minutes.
    assert DEFAULT_TIMEOUT - JUDGEMENTS * BOUND_SECONDS >= 180.0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize("bound", [7.0, 20.0, 300.0])
def test_a_bound_that_would_not_fit_the_tick_refuses_the_module(
    bound, monkeypatch
):
    """The bypass case. The relation above is worth what the refusal is worth,
    and the refusal is at **import**, as a raise rather than a bare ``assert``:
    a guarantee ``python -O`` removes is not a guarantee.

    ``7.0`` is the interesting row — it is barely more than the shipped number
    and it is already too much, which is what makes this a bound rather than a
    gesture. ``20.0`` is the morning composer's bound, which is the number
    somebody copying the nearest consultation would reach for.
    """
    monkeypatch.setattr(judging, "BOUND_SECONDS", bound)
    with pytest.raises(JudgeError, match="per-main timeout"):
        judging._check_constants()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_share_of_the_whole_tick_is_not_room_to_spare(monkeypatch):
    """The other half of the same guard: a share of one lets the judgements
    consume the entire slot, and a pass cancelled there has bought every
    judgement and written nothing."""
    monkeypatch.setattr(judging, "SHARE_OF_TICK", 1.0)
    with pytest.raises(JudgeError, match="room to spare"):
        judging._check_constants()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_provider_past_the_bound_answers_none_and_the_pass_continues(
    registry, tmp_path
):
    """Matrix: *provider slow*. ``None`` for that couple, and the pass runs to
    the end and reports the main as run."""
    seeded(registry, tmp_path)
    holder = Holder(labelled(TENSION), sleep=0.5)
    seat = Judges({MAIN: holder}, bound_seconds=0.01)
    result = run_pass(registry, MAIN, seat=seat)

    assert holder.calls == 1
    assert result.minted.unsaid == (key_of("b_said", "b_did"),)
    assert result.minted.minted == ()
    assert seat.tally.bound_exceeded == 1
    assert seat.tally.answers == {}
    # The pass itself completed, which is the promise CAP-7 makes about the
    # night rather than about the port.
    assert result.seen == 0 and result.unrecorded == ()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize(
    "bad", [0, -1, -0.5, None, "5", True, False, object(),
            float("nan"), float("inf")],
)
def test_a_bound_that_is_not_a_bound_is_refused_at_construction(bad):
    """**The stricter of the shape's two predicates**, and deliberately so.

    ``consult.refuses_as_a_bound`` — what the three older constructors apply —
    admits ``NaN`` and infinity, and its own docstring says so and says why it
    was not closed there: a behaviour change in three constructors inside a
    refactor. This constructor is new, so it takes ``a_bound``. Every comparison
    against a NaN is ``False``, ``asyncio.timeout(nan)`` never fires, and a
    judgement that never returns is a scheduler slot held until the tick
    cancels the whole pass.
    """
    with pytest.raises(JudgeError, match="not a bound"):
        Judges({MAIN: Holder()}, bound_seconds=bad)


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_stricter_predicate_is_the_one_this_constructor_uses():
    """Non-vacuity for the row above: the two predicates genuinely differ, and
    the difference is the value this constructor refuses and the other three
    accept."""
    assert consult.refuses_as_a_bound(math.inf) is False
    assert consult.a_bound(math.inf) is False
    assert consult.a_bound(BOUND_SECONDS) is True


# ═════════════════════════════════════════════════════════════════════════════
# what one judgement may cost
# ═════════════════════════════════════════════════════════════════════════════


def _real_classifier(transport, tier=CLASSIFY_TIER):
    from half.model.anthropic import AnthropicProvider
    from half.model.tier import Tiers

    return AnthropicProvider(
        transport, tiers=Tiers.parse({MAIN: tier}),
        budget=Budget(per_call_micro_usd=PER_CALL_MICRO_USD,
                      per_pass_micro_usd=PER_PASS_MICRO_USD),
    ).classifier()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_pair_past_the_ceiling_is_refused_before_the_transport():
    """Matrix: *over the cap*. Refused rather than overspent, and refused
    **before the transport is touched** — asserted at the wire with a counting
    transport rather than from below, because a ceiling pinned only from below
    can be loosened five thousand-fold with the suite green."""
    transport = Counting()
    seat = Judges({MAIN: _real_classifier(transport)})
    assert asked(seat, "मैं " * 400_000, DID) is None

    assert transport.calls == 0, "an oversized pair reached the provider"
    assert seat.tally.failures == {"over-budget/per-call-budget": 1}
    assert seat.tally.failure_rate == 1.0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_an_ordinary_pair_does_reach_the_transport():
    """Non-vacuity for the row above: a ceiling that refused everything would
    pass it while removing the judgement entirely."""
    transport = Counting()
    seat = Judges({MAIN: _real_classifier(transport)})
    assert asked(seat) is False
    assert transport.calls == 1, "an ordinary pair never reached the provider"
    assert seat.tally.answers == {NO_TENSION: 1}


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_ceilings_are_the_shared_ones_and_the_per_call_one_binds():
    """The two numbers that were byte-identical in three consultations before
    story 14 and are one definition now. They answer the same question — *what
    is an absurd amount to spend on one call, and on one process* — and this
    caller has no reason to answer it differently."""
    assert (PER_CALL_MICRO_USD, PER_PASS_MICRO_USD) == (100_000, 500_000_000)
    assert (PER_CALL_MICRO_USD, PER_PASS_MICRO_USD) == (
        consult.PER_CALL_MICRO_USD, consult.PER_PASS_MICRO_USD
    )
    assert PER_CALL_MICRO_USD <= PER_PASS_MICRO_USD


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_pass_never_buys_more_judgements_than_the_budget(registry, tmp_path):
    """9d's budget, exercised through a real judge rather than a double.

    The bound is the couples a pass may *buy*, and it is spent before it is
    exceeded — so a main with far more survivors than the budget consults
    exactly ``JUDGEMENTS`` holders and no more, whatever the model answers.
    """
    with Store(Path(tmp_path) / MAIN) as store:
        for index in range(12):
            seed_belief(store, f"b_said_{index}", STIRRED, subject="farmland",
                        ledger="stated", claim=f"intends to {index} the field")
            seed_belief(store, f"b_did_{index}", SETTLED, subject="farmland",
                        ledger="revealed", claim=f"paid {index} to the broker")
    asyncio.run(registry.note_pass(
        MAIN, t=stamp(LAST_PASS),
        fields={NEXT_PASS_AT: stamp(NOON), ZONE: "UTC", TOLD_ZONE: False,
                PASS_RAN: True},
    ))
    seat, holder = bench(labelled(NO_TENSION))
    result = run_pass(registry, MAIN, seat=seat)

    assert result.minted.unbudgeted > 0, "the fixture did not reach the bound"
    assert holder.calls == JUDGEMENTS
    assert seat.tally.consulted == JUDGEMENTS
    assert result.minted.consulted == JUDGEMENTS


# ═════════════════════════════════════════════════════════════════════════════
# the breaker
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_run_of_failures_stands_that_main_down_and_it_recovers():
    """Matrix: *the breaker*. Consecutive failures past the threshold stand this
    main down, the skips are counted **outside** every rate, and it recovers.

    The stand-down is asserted by the holder's own call count rather than by the
    verdict, because every one of these answers ``None`` either way: a build
    with no breaker at all would produce an identical sequence of verdicts while
    paying the bound and issuing a doomed request twenty-four more times.
    """
    fault = Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)
    seat, holder = bench(fault)

    for _ in range(BREAK_AFTER):
        assert asked(seat) is None
    assert holder.calls == BREAK_AFTER

    for _ in range(BREAK_FOR):
        assert asked(seat) is None
    assert holder.calls == BREAK_AFTER, "the stand-down bought nothing"
    assert seat.tally.skipped == BREAK_FOR
    assert seat.tally.consulted == BREAK_AFTER, "a skip entered the rate"

    # And it closes again rather than staying shut.
    assert asked(seat) is None
    assert holder.calls == BREAK_AFTER + 1


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_stand_down_is_one_mains_and_not_the_deployments():
    """One main's provider being down says nothing about another's, and a
    self-hoster's key is their own (AD-11)."""
    fault = Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED)
    down, up = Holder(fault), Holder(labelled(TENSION))
    seat = Judges({MAIN: down, OTHER_MAIN: up}, bound_seconds=0.5)

    for _ in range(BREAK_AFTER + 2):
        assert asked(seat) is None
    assert down.calls == BREAK_AFTER

    assert asked(seat, main=OTHER_MAIN) is True
    assert up.calls == 1


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_stand_down_is_logged_once_when_it_trips_and_carries_no_claim(
    caplog
):
    """A degradation nobody can see is the worst outcome available here: it
    looks exactly like a main whose life never pulls in two directions."""
    seat, _ = bench(Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED))
    with caplog.at_level(logging.DEBUG, logger="half.consolidate.judge"):
        for _ in range(BREAK_AFTER):
            asked(seat)
    tripped = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(tripped) == 1
    assert "standing down" in tripped[0].getMessage()
    assert SAID not in caplog.text and DID not in caplog.text


# ═════════════════════════════════════════════════════════════════════════════
# worldwide: any script, two scripts, no rubric, no locale
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize("script", sorted(SCRIPTS), ids=sorted(SCRIPTS))
def test_a_pair_in_any_script_is_judged_and_neither_half_is_changed(script):
    """Matrix: *any script*. Judged, with no English rubric on the path.

    The claims are asserted **inside the turn that reaches the provider**, byte
    for byte: not normalised, not case-folded, not transliterated, not
    truncated. Every one of those is a rule written about one language being
    applied to all of them.
    """
    said, did = SCRIPTS[script]
    seat, holder = bench(labelled(TENSION))
    assert asked(seat, said, did) is True

    turn = holder.seen[0].prompt.turns[0]
    assert turn.role is Role.USER
    assert turn.text == f"{said}{SEPARATOR}{did}"
    assert said in turn.text and did in turn.text


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_two_claims_may_be_in_two_different_scripts():
    """Matrix: *two languages*. The revealed side can come out of ingested mail
    while the stated side is the main's own words, so the pair is not assumed to
    share a language and neither half is assumed to be the other's
    translation."""
    said, did = MIXED
    seat, holder = bench(labelled(TENSION))
    assert asked(seat, said, did) is True
    assert holder.seen[0].prompt.turns[0].text == f"{said}{SEPARATOR}{did}"
    # And the model is told, in the instructions, that this is a shape it will
    # see — a rule the judge cannot enforce and must therefore state.
    assert any("two different ones" in block for block in INSTRUCTIONS)


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_request_differs_between_scripts_only_in_the_claims():
    """*No English rubric and no locale anywhere on the path*, as the only thing
    that sentence can mean for a module that forwards two sentences.

    Every request is rendered for real and compared: same system blocks, same
    label set, same model, same ceiling. Nothing about the request is a function
    of what script the claims are in, because nothing on this path looks.
    """
    from half.model.anthropic import render_classify
    from half.model.tier import DEFAULT_MODELS, Tier

    spec = DEFAULT_MODELS[Tier.CHEAP]
    rendered = []
    for said, did in [*SCRIPTS.values(), MIXED]:
        seat, holder = bench(labelled(NO_TENSION))
        asked(seat, said, did)
        payload = render_classify(holder.seen[0], spec)
        rendered.append(payload)

    first = rendered[0]
    for payload in rendered[1:]:
        assert payload["system"] == first["system"]
        assert payload["model"] == first["model"]
        assert payload["max_tokens"] == first["max_tokens"]
        assert payload.keys() == first.keys()
        assert len(payload["messages"]) == len(first["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"
        # The one thing that differs is the one thing that is the main's.
        assert payload["messages"][0]["content"] != first["messages"][0]["content"]


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_nothing_on_this_path_reads_measures_or_folds_a_claim():
    """The structural half of *worldwide*: the judge does not look at either
    claim, so there is nowhere for a locale, a script assumption or a rule about
    one language's prose to live.

    Read off the module rather than off a docstring. A case-fold, a
    normalisation, a length threshold, a regular expression or a character-class
    lookup would each be a rubric — and each is the exact defect this codebase
    has shipped three times, most recently as a question-mark denylist that
    worked in Latin and did nothing in Arabic, Greek, Armenian, Amharic or
    Chinese.
    """
    source = (ROOT / "half/consolidate/judge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for module in ("locale", "unicodedata", "re", "difflib", "gettext",
                   "encodings", "codecs"):
        assert module not in imported, module

    called = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for name in ("lower", "upper", "casefold", "normalize", "translate",
                 "encode", "decode", "startswith", "endswith", "split",
                 "partition", "find", "replace"):
        assert name not in called, name

    # ``strip`` is used, and only to answer *is there anything here at all*.
    # Everything else a claim could be subjected to is absent above.
    assert "strip" in called
    # And nothing measures a claim: the only ``len`` in the module is over the
    # label set and the couple, never over text a main wrote.
    assert claims_of(entry_of("a", "x" * 10_000), entry_of("b", "y")) == (
        "x" * 10_000, "y"
    )


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_instructions_carry_no_rule_about_how_anything_is_written():
    """The judge asks about meaning and never about prose. gbrain's voice gate
    is per-surface English-prose style rules, and shipped worldwide that is one
    language's idea of good writing applied to everybody's — the objection
    ``half.context.channels`` already records against a written template."""
    said = next(b for b in INSTRUCTIONS if "any language" in b)
    assert "never how they are written" in said
    for word in ("register", "length", "politeness", "fluency"):
        assert word in said, word
    assert "any script" in said


# ═════════════════════════════════════════════════════════════════════════════
# AD-22: two claims to the provider, and nothing anywhere else
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_claim_reaches_the_provider_and_no_other_place_at_all(
    registry, tmp_path, caplog
):
    """Matrix: *nothing durable*. The sentinel is hunted rather than assumed.

    A whole pass runs over a real log with two distinctive claims, and the
    sentinel is then looked for in: the payload (where it must be), the main's
    own log file (where it already was, so the assertion is that nothing *new*
    carries it), the folded tension table, the tally, the result the pass hands
    back, and every log line the run emitted.
    """
    said = "zzqx intends to buy the orchard before the rains"
    did = "zzqx has opened no listing since the equinox"
    seeded(registry, tmp_path, pair=(said, did))
    seat, holder = bench(labelled(TENSION))

    with caplog.at_level(logging.DEBUG):
        result = run_pass(registry, MAIN, seat=seat)

    # It reached the provider, which is the whole of what may leave.
    assert said in holder.seen[0].prompt.turns[0].text

    # And nowhere else. The tension the pass minted is a pair, a state and a
    # license — the claims stay on the two beliefs they were always on.
    minted = registry.tension_table(MAIN)[key_of("b_said", "b_did")]
    assert "zzqx" not in repr(minted)
    assert "zzqx" not in repr(result.minted)
    assert "zzqx" not in repr(seat.tally)
    assert "zzqx" not in caplog.text
    seat.flush()
    assert "zzqx" not in caplog.text


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_no_log_line_in_the_judgement_can_carry_content():
    """AD-22, asserted over the arguments of every logging call in the module
    rather than over the lines a run happened to emit.

    A message in a variable and a receiver in a local are both invisible to a
    scan like this, which is why the two ``flush`` calls are spelled out rather
    than routed through a shared format string: an invisible log call is how
    content gets logged.
    """
    path = ROOT / "half/consolidate/judge.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"):
            continue
        seen += 1
        rendered = [ast.unparse(argument) for argument in node.args]
        assert all("f'" not in text and 'f"' not in text for text in rendered), (
            f"an f-string reached a log call at line {node.lineno}"
        )
        assert not node.keywords, f"exc_info at line {node.lineno}"
        for text in rendered[1:]:
            assert any(
                marker in text
                for marker in ("main_id", "type(", "self._tally", "reply.kind",
                               "reply.because", "BREAK_AFTER", "BREAK_FOR")
            ), f"line {node.lineno} may carry content: {text!r}"
    assert seen >= 6, "the log-line scan found almost nothing to read"


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_tally_holds_counts_and_closed_keys_and_nothing_else():
    """There is no field on this type a main's own words could travel in, which
    is what makes *"no claim survives a judgement"* a property of the type
    rather than a promise about its callers."""
    seat, _ = bench(labelled(TENSION), labelled(CANNOT_SAY),
                    Failure(Kind.REFUSED, Reason.PROVIDER_REFUSED))
    for _ in range(3):
        asked(seat)

    tally = seat.tally
    assert set(tally.answers) <= set(LABELS)
    for key in tally.failures:
        kind, _, because = key.partition("/")
        assert kind in {str(k) for k in Kind}
        assert because in {str(r) for r in Reason}
    for name in Tally.__dataclass_fields__:
        value = getattr(tally, name)
        assert isinstance(value, (int, dict)), name
        if isinstance(value, dict):
            assert all(isinstance(v, int) for v in value.values()), name


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_an_exception_reaches_the_log_as_a_class_and_never_as_its_own_text(
    caplog
):
    """A provider quotes the request it rejected — ``400 ... 'ينوي شراء
    المزرعة'`` — so nothing here calls ``logger.exception`` or passes
    ``exc_info``. The class of a fault is the whole of what may cross."""
    said, did = SCRIPTS["arabic"]
    seat, _ = bench(RuntimeError(f"400 rejected: {said!r}"))
    with caplog.at_level(logging.DEBUG, logger="half.consolidate.judge"):
        assert asked(seat, said, did) is None

    assert seat.tally.raised == 1
    assert "RuntimeError" in caplog.text
    assert said not in caplog.text
    assert "400 rejected" not in caplog.text


# ═════════════════════════════════════════════════════════════════════════════
# a judgement never costs the pass
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_provider_that_raises_never_costs_the_pass(registry, tmp_path):
    """Matrix: *provider raises*. That couple is not minted and it was billed;
    the pass completes and the tick reports the main as run.

    **This judge catches**, so ``MintResult.skipped`` — 9d's counter for a judge
    that threw — stays empty and the failure is counted here instead, apart from
    an answered *cannot say*. That is more information rather than less: 9d's
    catch is still the guarantee for any judge, and this one does not lean on a
    fail-open handler to make its own promise true.
    """
    seeded(registry, tmp_path)
    seat, holder = bench(RuntimeError("a build mistake"))
    result = run_pass(registry, MAIN, seat=seat)

    assert holder.calls == 1
    assert result.minted.consulted == 1, "a raised judgement was not billed"
    assert result.minted.unsaid == (key_of("b_said", "b_did"),)
    assert result.minted.skipped == ()
    assert seat.tally.raised == 1
    assert seat.tally.unsure == 0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize(
    "answer",
    [
        RuntimeError("a build mistake"),
        Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
        Failure(Kind.OVER_BUDGET, Reason.PER_CALL_BUDGET),
        Decision(label="something else entirely"),
    ],
    ids=["raises", "unreachable", "over-budget", "unreadable"],
)
def test_a_failing_judge_leaves_the_tick_reporting_the_main_as_run(
    answer, registry, tmp_path
):
    """Matrix, at the level the sentence is actually about: *the pass completes
    and the tick reports the main as run.*

    Every case above this one asserts the promise at the ``evaluate`` boundary,
    which is one rung below where CAP-7 makes it. This drives a real
    ``Scheduler.tick`` — the file lock, the due-time read, the bounded
    concurrency, the per-main timeout and the per-main exception handler — so
    that *"a judgement never costs the pass"* is measured where an operator
    would read it: in ``TickResult.ran`` rather than in ``TickResult.failed`` or
    ``timed_out``.

    Parametrised over four of the five ways a judgement fails, because a build
    that special-cased one of them would pass on that row and fail on the rest.
    """
    from half.schedule.clock import FrozenClock
    from half.schedule.tick import Scheduler

    seeded(registry, tmp_path)
    asyncio.run(registry.note_pass(
        MAIN, t=stamp(LAST_PASS + 1),
        fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC", TOLD_ZONE: False,
                PASS_RAN: True},
    ))
    seat, holder = bench(answer)
    scheduler = Scheduler(
        registry=registry, mains=(MAIN,), root=Path(tmp_path),
        clock=FrozenClock(at=NOON),
        work=TensionPass(ledger=registry, bench=seat),
    )
    result = asyncio.run(scheduler.tick())

    assert result.ran == (MAIN,), result
    assert result.failed == () and result.timed_out == ()
    assert holder.calls == 1, "the judge was never reached, so nothing was proved"
    assert registry.tension_table(MAIN) == {}


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_deployment_that_equipped_nobody_completes_the_pass_and_mints_nothing(
    registry, tmp_path
):
    """Matrix: *provider absent*. 9d's behaviour, unchanged — and the bound, the
    filter and the budget still run, which is what keeps CAP-7's cost rule under
    test on a deployment with no key anywhere."""
    seeded(registry, tmp_path)
    seat = Judges()
    assert seat.for_main(MAIN) is None
    result = run_pass(registry, MAIN, seat=seat)

    assert result.minted.unwired is True
    assert result.minted.considered == 1, "the bound stopped being exercised"
    assert result.minted.minted == () and result.minted.consulted == 0
    assert registry.tension_table(MAIN) == {}
    assert seat.tally.consulted == 0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_bench_that_raises_costs_the_minting_and_never_the_pass(
    registry, tmp_path
):
    """The bench is resolved inside the isolation the read already has, so a
    build that wired something broken costs this main their minting rather than
    their night."""
    class Broken:
        def for_main(self, main_id):
            raise RuntimeError("a build mistake")

    seeded(registry, tmp_path)
    result = run_pass(registry, MAIN, seat=Broken())
    assert result.minted.minted == ()
    assert result.minted.considered == 0
    assert result.unrecorded == ()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_couple_with_nothing_to_judge_is_counted_and_never_consulted():
    """The cheap filter refuses a couple with an unreadable claim on either side
    two steps earlier, so reaching the judge means the filter stopped working.

    Counted rather than guessed at, and **never consulted about**: a judge handed
    one claim can only guess, and a pass that paid for that guess would have
    spent budget on the one comparison nothing could answer.
    """
    seat, holder = bench(labelled(TENSION))
    seat_one = seat.for_main(MAIN)
    for one, other in (
        (entry_of("b_a", ""), entry_of("b_b", DID)),
        (entry_of("b_a", "   "), entry_of("b_b", DID)),
        (entry_of("b_a", SAID), Entry(id="b_b")),
        ("not an entry", entry_of("b_b", DID)),
    ):
        assert asyncio.run(seat_one.disagree(one, other)) is None
    assert holder.calls == 0, "a couple with one claim was paid for"
    assert seat.tally.unjudgeable == 4
    assert seat.tally.consulted == 0


# ═════════════════════════════════════════════════════════════════════════════
# the seam, the bench, and the narrow holder
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_judge_offers_exactly_one_method_and_satisfies_the_port():
    """Narrow by construction. A judge that grew a second method would be a
    judge that could store through, generate through or read a clock through."""
    seat, _ = bench(labelled(TENSION))
    one = seat.for_main(MAIN)
    assert isinstance(one, Disagreement)
    assert door_of(Disagreement) == {"disagree"}
    assert [n for n in dir(one) if not n.startswith("_")] == ["disagree"]
    assert not callable(one)


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_order_of_the_two_entries_is_never_used_for_anything():
    """A judge that answered differently depending on which arrived first would
    be ranking the sides, which is the one thing a tension may never record.

    Asserted twice: the object holds no accessor for either half, and the two
    calls differ only in which claim lands on which side of the separator —
    nothing is sorted, and no side is named.
    """
    seat, holder = bench(labelled(TENSION))
    one = seat.for_main(MAIN)
    asyncio.run(one.disagree(entry_of("b_a", SAID), entry_of("b_b", DID)))
    asyncio.run(one.disagree(entry_of("b_b", DID), entry_of("b_a", SAID)))

    assert holder.seen[0].prompt.turns[0].text == f"{SAID}{SEPARATOR}{DID}"
    assert holder.seen[1].prompt.turns[0].text == f"{DID}{SEPARATOR}{SAID}"
    assert Couple(both=(entry_of("b_a", SAID), entry_of("b_b", DID))).id == (
        Couple(both=(entry_of("b_b", DID), entry_of("b_a", SAID))).id
    )
    # And nothing in the two functions that build a judgement orders, indexes
    # or chooses between the two: no sort, no ``min``/``max``, no subscript.
    # The ``sorted`` calls elsewhere in the module are over the *label set* and
    # over a holder's method names, and neither is a side of a couple.
    tree = ast.parse(
        (ROOT / "half/consolidate/judge.py").read_text(encoding="utf-8")
    )
    for name in ("claims_of", "prompt_for"):
        body = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == name)
        # The statements only — an annotation such as ``tuple[str, ...]`` is a
        # subscript and is not a positional read of anybody's couple.
        inside = [n for stmt in body.body for n in ast.walk(stmt)]
        called = {
            ast.unparse(node.func) for node in inside
            if isinstance(node, ast.Call)
        }
        assert not called & {"sorted", "min", "max", "list.sort"}, called
        assert not [n for n in inside if isinstance(n, ast.Subscript)], name


@pytest.mark.cap7
@pytest.mark.cap7_judgement
@pytest.mark.parametrize(
    "method", ["generate", "submit", "collect", "chat", "invoke", "run",
               "spend", "reset"],
)
def test_a_holder_that_can_do_more_than_classify_is_refused(method):
    """An **allowlist**, which is the only version of this check that holds: a
    denylist of six names let an object through that could ``classify`` and also
    ``chat``, and every denylist this codebase has shipped was walked around."""
    holder = Holder(labelled(TENSION))
    setattr(holder, method, lambda *a, **k: None)
    with pytest.raises(JudgeError, match=method):
        Judges({MAIN: holder})


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_an_object_that_cannot_classify_and_one_that_is_callable_are_refused():
    class CannotClassify:
        async def generate(self, work): ...

    class Callable_:
        async def classify(self, work): ...
        def __call__(self): ...

    with pytest.raises(JudgeError, match="cannot classify"):
        Judges({MAIN: CannotClassify()})
    with pytest.raises(JudgeError, match="itself callable"):
        Judges({MAIN: Callable_()})
    assert ALLOWED_METHODS == {"classify"}


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_bench_is_sealed_after_construction():
    """A narrow output is half of a narrow holder; the other half is narrow
    authority. Rebinding an attribute would put a wider holder past the check
    that it cannot produce text."""
    seat, _ = bench(labelled(TENSION))
    with pytest.raises(JudgeError, match="sealed"):
        seat._holders = {}
    with pytest.raises(JudgeError, match="sealed"):
        seat._bound = 999.0


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_bench_hands_each_main_their_own_holder_and_nobody_elses():
    """Per main, because a self-hoster's key is stored under their own id
    (AD-11) and the tier travels with the main (AD-20)."""
    mine, theirs = Holder(labelled(TENSION)), Holder(labelled(NO_TENSION))
    seat = Judges({MAIN: mine, OTHER_MAIN: theirs}, bound_seconds=0.5)

    assert seat.holds(MAIN) and seat.holds(OTHER_MAIN)
    assert seat.for_main("stranger") is None
    assert asked(seat) is True
    assert asked(seat, main=OTHER_MAIN) is False
    assert (mine.calls, theirs.calls) == (1, 1)
    assert seat.for_main(MAIN).__class__ is Judge


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_prompt_carries_two_claims_the_instructions_and_no_third_thing():
    """*What leaves the machine* as a property of the constructed prompt.

    No belief id, no stamp, no subject, no ledger name, no loop — and the ledger
    name in particular, because *stated* against *revealed* is exactly the hint
    that would look helpful in a prompt and would be Half telling a model which
    side to doubt. ``main_id`` is on the prompt because the port resolves a tier
    from it, and it reaches no payload.
    """
    one = Entry(id="b_said", at=STIRRED, claim=SAID, subject="qqsubject",
                ledger="stated", loop="qqloop")
    other = Entry(id="b_did", at=SETTLED, claim=DID, subject="qqsubject",
                  ledger="revealed", loop="qqloop")
    seat, holder = bench(labelled(TENSION))
    asyncio.run(seat.for_main(MAIN).disagree(one, other))

    work = holder.seen[0]
    assert work.labels == LABELS
    assert work.prompt.main_id == MAIN
    assert work.prompt.system == INSTRUCTIONS
    assert work.prompt.cache is None, "a breakpoint the provider would ignore"
    body = work.prompt.turns[0].text
    assert body == f"{SAID}{SEPARATOR}{DID}"
    for leaked in ("b_said", "b_did", "qqsubject", "stated", "revealed",
                   "qqloop", STIRRED, SETTLED, MAIN):
        assert leaked not in body, leaked


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_separator_is_told_to_the_model_and_is_not_inside_a_label():
    """A separator the model is never told about turns two entries into one
    run-on entry with a stray character in it, and every judgement is then about
    something Half never recorded."""
    assert SEPARATOR_MARK in SEPARATOR
    assert any(SEPARATOR_MARK in block for block in INSTRUCTIONS)
    assert SEPARATOR_MARK not in "".join(LABELS)
    assert prompt_for((SAID, DID), main_id=MAIN).turns[0].text.count(
        SEPARATOR_MARK
    ) == 1


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_separator_the_model_is_never_told_about_refuses_the_module(
    monkeypatch
):
    """The bypass for the row above."""
    monkeypatch.setattr(judging, "SEPARATOR_MARK", "‖‖")
    with pytest.raises(JudgeError, match="never told about"):
        judging._check_constants()


# ═════════════════════════════════════════════════════════════════════════════
# the shape is shared and the policy is this caller's
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_shared_numbers_are_shared_and_this_paths_policy_is_its_own():
    """Which numbers moved and which did not, pinned rather than reviewed.

    The five that were byte-identical in three consultations before story 14 are
    one definition with four readers now. The three that differ differ *for
    reasons*, and these are the reasons: nobody is waiting for a judgement so
    the bound is not the crisis path's two seconds, but twenty-four of them
    happen in series inside one scheduler slot so it is not the morning's twenty
    either; a stand-down is counted in judgements because a judgement is the
    unit ``disagree`` is called in; and the alarm rate is a fifth rather than
    the morning's half because *cannot say* is an answer, so nothing in this
    rate's numerator is ordinary.
    """
    assert (BOUND_SECONDS, BREAK_FOR, ALARM_RATE) == (5.0, 24, 0.2)
    for name in ("BOUND_SECONDS", "BREAK_FOR", "ALARM_RATE", "SHARE_OF_TICK"):
        assert not hasattr(consult, name), name
    assert (BREAK_AFTER, REPORT_EVERY, ALARM_AFTER) == (5, 100, 10)
    assert (
        BREAK_AFTER, REPORT_EVERY, ALARM_AFTER,
        PER_CALL_MICRO_USD, PER_PASS_MICRO_USD,
    ) == (
        consult.BREAK_AFTER, consult.REPORT_EVERY, consult.ALARM_AFTER,
        consult.PER_CALL_MICRO_USD, consult.PER_PASS_MICRO_USD,
    )
    for name in ("ALARM_AFTER", "BREAK_AFTER", "PER_CALL_MICRO_USD",
                 "PER_PASS_MICRO_USD", "REPORT_EVERY"):
        assert name in judging.__all__, name
        assert getattr(judging, name) == getattr(consult, name)


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_this_story_added_no_fourth_copy_of_the_consultation():
    """*"The consultation shape appears once and this story added no copy."*

    Both halves: the shared decisions are reached by name, and the arithmetic
    they would have replaced is absent from this file. A caller that kept its
    own copy beside the shared one is a fourth copy with an import at the top.
    """
    source = (ROOT / "half/consolidate/judge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    reached = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert {
        "Breaker", "due", "rate", "count_one", "failure_key", "wider_than",
        "a_bound",
    } <= reached
    assert "% REPORT_EVERY" not in source
    assert "% ALARM_AFTER" not in source
    assert "_consecutive" not in source and "_quiet" not in source
    # And the shape still knows nothing about this domain, which was the
    # non-negotiable condition of the extraction.
    for token in (*LABELS, "tension", "disagree", "couple", "claim"):
        assert not hasattr(consult, token), token
    shape = (ROOT / "half/model/consult.py").read_text(encoding="utf-8")
    for label in LABELS:
        assert label not in shape, label


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_wholly_failing_judge_alarms_at_error_and_is_not_hidden_by_a_round_number(
    caplog
):
    """The one branch three callers had wrong and story 13a fixed in one of
    them, reaching the fourth caller through the shared shape.

    With the periodic question asked first and the alarm on an ``elif``, the two
    are exclusive: at the hundredth judgement a wholly failing judge reports at
    ``info`` instead of ``error`` — exactly the number an operator would look
    at.
    """
    seat, _ = bench(Failure(Kind.UNAVAILABLE, Reason.TRANSPORT_FAILED),
                    bound_seconds=0.5)
    with caplog.at_level(logging.DEBUG, logger="half.consolidate.judge"):
        for _ in range(REPORT_EVERY + BREAK_AFTER * 4):
            asked(seat)

    summaries = [r for r in caplog.records
                 if r.getMessage().startswith("disagreement judge:")]
    assert summaries, "a failing judge wrote no summary at all"
    assert all(r.levelno == logging.ERROR for r in summaries), (
        "a wholly failing judge reported at info"
    )
    assert seat.tally.failure_rate >= ALARM_RATE


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_deployment_that_did_nothing_writes_no_line_at_shutdown(caplog):
    """A line of zeros at every shutdown is the noise that trains an operator to
    ignore the one line that matters."""
    with caplog.at_level(logging.DEBUG, logger="half.consolidate.judge"):
        Judges().flush()
    assert not caplog.records


# ═════════════════════════════════════════════════════════════════════════════
# the shipped composition
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_main_with_a_key_is_equipped_in_the_shipped_wiring(tmp_path):
    """*"Wire the judge, its provider, its tier and its budget."* Run, not
    grepped: the object graph the product builds, with a real credential file.

    **A key equips a main, and a tier does not** — the deployment here sets
    ``HALF_MAINS`` and no ``HALF_MODEL_TIERS`` at all, and the judge is there.
    """
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load
    from half.secrets import FileSecretStore

    root = tmp_path / "mains"
    root.mkdir()
    FileSecretStore.beside(root).put(MAIN, "model_api_key", "sk-fine")
    config = load({ROOT_ENV: str(root), MAINS_ENV: f"123:{MAIN}"})
    assert config.tier_for(MAIN) is None, "the fixture configured a tier"
    wiring = build(config, token="123:fake")
    try:
        assert wiring.judges.holds(MAIN)
        seat = wiring.judges.for_main(MAIN)
        assert isinstance(seat, Disagreement)
        assert wiring.scheduler.work.consolidate.bench is wiring.judges
    finally:
        wiring.registry.close()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_every_main_is_judged_on_the_pinned_tier_and_never_their_own(
    tmp_path, monkeypatch
):
    """**SPEC's constraint, not a preference**: *the nightly pass runs on a
    cheaper model tier than conversation, batched, since cost is dominated by it
    and the free tier depends on that gap.*

    The pass is the only recurring spend in the product — every night, whether
    or not anybody writes, ``JUDGEMENTS`` times per main — so a tier that
    followed the main would make the one cost the free tier is sized against
    follow what a deployment pays for **conversation**, which is that gap
    closed. And there is nothing here for a better tier to buy on a main's
    behalf: a judgement is one label from a closed set and nobody reads it.

    Asserted from **both sides of the provider**, because either one alone is
    satisfiable by the mutation the other catches: a tier followed inside the
    wiring passes any check on the rendered payload of a separately-built
    classifier, and a tier pinned in the wiring and then resolved from the main
    inside the provider passes any check on what the wiring handed over. So the
    ``Tiers`` the composition root actually constructs is captured, and the
    model a real request actually names is read off the payload.

    Driven with one main a deployment put on the **frontier** tier and one with
    no tier at all: both are equipped, and neither resolves to anything but
    ``CLASSIFY_TIER``.
    """
    from half.config import MAINS_ENV, ROOT_ENV, TIERS_ENV, load
    from half.model.tier import DEFAULT_MODELS, Tier
    from half.secrets import FileSecretStore

    assert CLASSIFY_TIER == "cheap"
    assert CLASSIFY_TIER in {str(tier) for tier in Tier}
    assert CLASSIFY_TIER != str(Tier.FRONTIER)

    root = tmp_path / "mains"
    root.mkdir()
    secrets = FileSecretStore.beside(root)
    for main in (MAIN, OTHER_MAIN):
        secrets.put(main, "model_api_key", "sk-fine")
    config = load({ROOT_ENV: str(root),
                   MAINS_ENV: f"123:{MAIN}, 456:{OTHER_MAIN}",
                   TIERS_ENV: f"{MAIN}:frontier"})
    assert config.tier_for(MAIN) == "frontier", "the fixture pays for nothing"
    assert config.tier_for(OTHER_MAIN) is None

    # Side one: what the composition root hands the provider. The production
    # function is called directly rather than through ``build``, because
    # ``build`` equips four subsystems through the same constructor and three of
    # them are somebody else's rule.
    import half.__main__ as entrypoint

    given: list[tuple[object, object]] = []
    real = entrypoint.AnthropicProvider

    def watched(transport, *, tiers, budget):
        given.append((tiers, budget))
        return real(transport, tiers=tiers, budget=budget)

    monkeypatch.setattr(entrypoint, "AnthropicProvider", watched)
    seat = entrypoint.judges(config, secrets)

    assert seat.holds(MAIN) and seat.holds(OTHER_MAIN), "a key equips a main"
    assert len(given) == 2, given
    for tiers, budget in given:
        (main,) = tiers.mains
        assert tiers.of(main) is Tier.CHEAP, (main, dict(tiers.mains))
        assert budget.per_call_micro_usd == PER_CALL_MICRO_USD

    # Side two: the model a real request actually names, end to end.
    transport = Counting()
    elsewhere = Judges({MAIN: _real_classifier(transport)})
    assert asked(elsewhere) is False
    assert transport.payloads[0]["model"] == DEFAULT_MODELS[Tier.CHEAP].model
    assert transport.payloads[0]["model"] != DEFAULT_MODELS[Tier.FRONTIER].model

    # And the composition root **reads** this module's constant rather than
    # spelling a tier name of its own, so the two cannot drift apart. Read off
    # the source, because the binding existing proves nothing: a mutation that
    # replaced the reference with the literal ``"cheap"`` left every assertion
    # above this one green while putting the tier in two places.
    assert entrypoint.JUDGE_TIER is CLASSIFY_TIER
    wiring = next(
        node for node in ast.walk(
            ast.parse((ROOT / "half/__main__.py").read_text(encoding="utf-8"))
        )
        if isinstance(node, ast.FunctionDef) and node.name == "judges"
    )
    parsed = [
        node for node in ast.walk(wiring)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "Tiers.parse"
    ]
    assert len(parsed) == 1, [ast.unparse(n) for n in parsed]
    assert ast.unparse(parsed[0]) == "Tiers.parse({main_id: JUDGE_TIER})", (
        ast.unparse(parsed[0])
    )


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_a_deployment_with_no_credentials_still_boots(tmp_path):
    """Nothing in the wiring may fail a boot. No key, an unreadable credential
    file, an unknown tier, a missing SDK — each is a deployment that has not
    equipped that main for a nightly judgement, and none is a reason to hold up
    a Half that still answers everything they say.

    **This is also the skip that survived the tier being pinned**: a main with no
    credential gets no judge and nothing is minted for them, which is story 9d's
    shipped behaviour exactly.
    """
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    root = tmp_path / "mains"
    root.mkdir()
    config = load({ROOT_ENV: str(root), MAINS_ENV: f"123:{MAIN}"})
    wiring = build(config, token="123:fake")
    try:
        assert not wiring.judges.holds(MAIN)
        assert wiring.judges.for_main(MAIN) is None
    finally:
        wiring.registry.close()


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_serve_flushes_the_counts_on_the_way_out(tmp_path, monkeypatch):
    """A process that ran for a week with a wholly failing judge must not end
    with nothing anywhere saying so — which looks exactly like a week in which
    nobody's life pulled in two directions."""
    import half.__main__ as entrypoint

    source = (ROOT / "half/__main__.py").read_text(encoding="utf-8")
    assert "wiring.judges.flush()" in source
    tree = ast.parse(source)
    serve = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "serve")
    flushed = {
        ast.unparse(node.func) for node in ast.walk(serve)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "flush"
    }
    assert "wiring.judges.flush" in flushed
    assert callable(entrypoint.judges)


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_the_module_says_plainly_that_two_claims_leave_the_machine():
    """*Telling a main their messages leave the machine* is an open launch
    blocker, and this widens what that sentence has to cover: from *what you
    write* to *what Half has written down about you, including what it derived
    from your mail*.

    Asserted rather than reviewed, because the sentence is the deliverable: a
    module that quietly acquired an egress and said nothing is exactly how the
    blocker gets wider without anybody noticing.
    """
    doc = " ".join((judging.__doc__ or "").split())
    assert "two claims, per judgement, to a provider" in doc
    assert "leave the machine" in doc
    assert "open launch blocker" in doc
    assert "derived from your mail" in doc


# ═════════════════════════════════════════════════════════════════════════════
# the guarantees, by name
# ═════════════════════════════════════════════════════════════════════════════


def _cases_defined_here() -> set[str]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


@pytest.mark.cap7
@pytest.mark.cap7_judgement
def test_every_judgement_guarantee_this_story_rests_on_still_exists():
    """A floor on a gate cannot protect a *named* case, and each of these
    carries a whole rule. Deleting one fails here by name rather than by
    arithmetic — which is the lesson review round 1 of story 9d recorded after
    two one-line mutations passed all 2950 cases."""
    required = {
        "test_a_plain_contradiction_answers_no_and_is_never_minted",
        "test_the_contradiction_has_a_home_that_is_not_the_minting_label",
        "test_a_label_set_that_minted_a_contradiction_refuses_the_module",
        "test_a_second_minting_label_refuses_the_module",
        "test_a_label_set_with_nowhere_to_put_doubt_refuses_the_module",
        "test_a_label_set_with_no_home_for_a_contradiction_refuses_the_module",
        "test_a_model_that_cannot_say_answers_none_and_is_not_a_failure",
        "test_an_answered_cannot_say_never_arms_the_breaker",
        "test_a_degraded_or_declining_provider_answers_none_and_never_no",
        "test_the_two_kinds_of_none_are_two_numbers_in_one_tally",
        "test_an_unreadable_answer_is_none_and_is_never_guessed",
        "test_a_full_budget_of_judgements_fits_inside_the_ticks_per_main_timeout",
        "test_a_bound_that_would_not_fit_the_tick_refuses_the_module",
        "test_a_share_of_the_whole_tick_is_not_room_to_spare",
        "test_a_bound_that_is_not_a_bound_is_refused_at_construction",
        "test_a_pair_past_the_ceiling_is_refused_before_the_transport",
        "test_an_ordinary_pair_does_reach_the_transport",
        "test_a_pass_never_buys_more_judgements_than_the_budget",
        "test_a_run_of_failures_stands_that_main_down_and_it_recovers",
        "test_a_stand_down_is_one_mains_and_not_the_deployments",
        "test_the_two_claims_may_be_in_two_different_scripts",
        "test_the_request_differs_between_scripts_only_in_the_claims",
        "test_nothing_on_this_path_reads_measures_or_folds_a_claim",
        "test_a_claim_reaches_the_provider_and_no_other_place_at_all",
        "test_no_log_line_in_the_judgement_can_carry_content",
        "test_an_exception_reaches_the_log_as_a_class_and_never_as_its_own_text",
        "test_a_provider_that_raises_never_costs_the_pass",
        "test_a_failing_judge_leaves_the_tick_reporting_the_main_as_run",
        "test_a_couple_with_nothing_to_judge_is_counted_and_never_consulted",
        "test_the_order_of_the_two_entries_is_never_used_for_anything",
        "test_the_prompt_carries_two_claims_the_instructions_and_no_third_thing",
        "test_this_story_added_no_fourth_copy_of_the_consultation",
        "test_every_main_is_judged_on_the_pinned_tier_and_never_their_own",
        "test_a_deployment_with_no_credentials_still_boots",
        "test_the_module_says_plainly_that_two_claims_leave_the_machine",
    }
    missing = required - _cases_defined_here()
    assert not missing, (
        f"a judgement guarantee was deleted: {sorted(missing)}. A floor on the "
        f"suite cannot protect these — each carries a whole property"
    )
