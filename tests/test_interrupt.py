"""CAP-10 story 5c: the interruption — one case per matrix row.

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test, which is the design under test: the scheduler is
the one module allowed to know what time it is (AD-30).

**Silence is asserted as the ordinary outcome, not as an error path.** Almost
every case below ends in nothing being sent, and the shipped composition ends
that way for ever — so the danger is a suite that would pass with the whole
module deleted. Two disciplines guard against it:

*The judge is a counter, never a raising double.* Story 13a shipped a double
that raised where it must not be reached, and the gate above it converted the
raise into a legal value two frames up, so the assertion passed whether the
ordering held or was inverted. ``Judge`` below counts calls and the cases
assert ``calls == 0`` — a fact no ``except Exception`` can launder.

*The three verdicts are asserted by their own counts.* ``nothing was sent`` is
true when a judge says no, when it says it cannot say, when it raises, and when
there is no judge at all. Each of those has a case asserting the field that
only it can move, so no two of them can be satisfied by one assertion.

**The gates are exercised alone and in pairs.** Independent refusals, each of
which alone produces silence, are exactly the shape where a second gate can
stop doing anything with the suite green — story 9c's central rule broke in two
orderings nobody had tested. ``test_every_pair_of_refusals_...`` sweeps them.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

from half.channel.port import Channel, Reachability, SendResult
from half.civil import DAY
from half.context.build import split as split_context
from half.governance.ladder import RUNGS, Ceiling, License, height
from half.interrupt import gate as interrupt
from half.interrupt.gate import (
    BOUND_SECONDS,
    CAPPED,
    CRISIS,
    INTERRUPTION_DAYS,
    JUDGEMENTS,
    JUST_INTERRUPTED,
    NAGGING,
    NO_JUDGE,
    NOTHING_CLOSING,
    NOTHING_MAY_BE_SAID,
    NOTHING_TO_WEIGH,
    REASONS,
    UNREADABLE,
    UNSENT,
    Interrupt,
    Weighed,
    delivered,
    material_for,
    option_for,
    unspent,
    weighable,
)
from half.interrupt.port import Option, Urgency
from half.loops import ledger as loops
from half.loops.timescale import PERIOD_DAYS, Timescale
from half.schedule.clock import moment, stamp
from half.store.ops import TOUCH_TENSION, Op
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.choose import NOT_LIVE
from half.surface.morning import SPEAKS_AT, speech
from half.surface.touch import Origin
from half.surface.view import narrowed
from half.trust.stakes import INTERRUPTION_DAYS as STAKES_INTERRUPTION_DAYS
from half.voice.gate import SILENCES, NO_MODEL

from tests.conftest import (
    COMPOSED,
    GeneratorDouble,
    a_voice,
    door_of,
    resolved_imports,
    seed_belief,
    seed_message,
    stub_voice,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "half" / "interrupt"

#: 2026-09-01T12:00:00Z — the instant the rest of this suite builds from.
NOON = 1_788_264_000.0
NOW = moment(NOON)

SEEDED = "2026-08-09T00:00:00Z"
ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")

#: One claim per seeded entry, sharing **no adjacent word pair** with any
#: other and containing no belief id — both load-bearing for the same reason
#: ``tests/test_surface.CLAIMS`` gives: AD-18's withholding guard works on
#: adjacent pairs, so two claims reading *"claim about b_1"* and *"claim about
#: b_2"* collide and leave every case quietly asserting over an empty context.
CLAIMS = {
    "b_1": "alpha alphawards",
    "b_2": "bravo bravowards",
    "b_3": "charlie charliewards",
    "b_4": "delta deltawards",
    "b_5": "echo echowards",
    "b_6": "foxtrot foxtrotwards",
}


# ── doubles ──────────────────────────────────────────────────────────────────


class Judge:
    """The urgency port, **and it counts**.

    One public method, so a holder is held to the same shape the protocol
    declares. ``answers`` are used in order and the last repeats: ``True`` is
    closing, ``False`` is not, ``None`` is cannot say, and a ``BaseException``
    is raised.

    ``calls`` and ``options`` are public and deliberately not callable. A case
    that needs to assert the judge was never reached has to be able to *ask* —
    the alternative is a double that raises when touched, and the gate's own
    ``except Exception`` turns that into ``failed`` and a legal silence, so the
    assertion would pass whether the ordering held or was inverted. That is the
    exact failure story 13a shipped.
    """

    def __init__(self, *answers, sleep: float = 0.0) -> None:
        self._answers = list(answers) or [None]
        self._sleep = sleep
        self._seen: list[Option] = []

    async def closing(self, option):
        self._seen.append(option)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        answer = self._answers[min(len(self._seen), len(self._answers)) - 1]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    @property
    def calls(self) -> int:
        return len(self._seen)

    @property
    def options(self) -> list[Option]:
        return list(self._seen)


class FakeChannel:
    """The whole ``Channel`` surface the gate needs, so the suite stays offline.

    ``reach`` may be a single answer or a sequence used in order with the last
    repeating, which is how the *asked again after composing* case shuts a
    window mid-composition.
    """

    name = "fake"

    def __init__(self, reach=Reachability.OPEN, fail=None, parts=1):
        self._reach = list(reach) if isinstance(reach, (list, tuple)) else [reach]
        self.fail = fail
        self.parts = parts
        self.sent: list[tuple[str, str]] = []
        self.queries: list[str] = []

    def capability_query(self, main_id):
        self.queries.append(main_id)
        return self._reach[min(len(self.queries), len(self._reach)) - 1]

    async def send(self, main_id, text):
        if self.fail is not None:
            raise self.fail
        self.sent.append((main_id, text))
        return SendResult(external_id="mid-1", parts=self.parts)

    def draft_link(self, text, *, to=None):  # pragma: no cover - never used
        raise AssertionError("the interruption never drafts to a third party")

    async def receive(self):  # pragma: no cover - never used
        raise AssertionError("the interruption never receives")


# ── fixtures ─────────────────────────────────────────────────────────────────


def seed_loop(store, slug, *, timescale="weeks", state="advancing",
              last_movement="2026-07-01", ident=None):
    store.record(
        Op.LOOP_TRANSITION, ident or f"l_{slug}", "2026-08-01T00:00:00Z",
        **loops.opened(slug, state=state, timescale=timescale,
                       last_movement=last_movement, loops=store.state().loops),
    )


def seed_entry(store, ident, *, loop, rung=License.ASSERT, t=SEEDED):
    fields = {"subject": "self", "topics": ["swimming"]}
    if loop is not None:
        fields["loop"] = loop
    return seed_belief(store, ident, t, claim=CLAIMS[ident], rung=rung,
                       support=[f"s_{ident}"], **fields)


def a_view(
    tmp_path,
    *,
    wantings=(("swim-weekly", "weeks", "2026-07-01"),),
    entries=(("b_1", "swim-weekly", License.ASSERT),),
    touches=(),
    ceiling=None,
    message=True,
):
    """One main's narrowed view, built through the real store and ladder.

    ``touches`` are ``(loop, stamp)`` pairs written with the record CAP-10's
    interrupt will use — ``touch.raised``, which raises a wanting and spends no
    day, so a raise here can never be mistaken for a morning.
    """
    with Store(Path(tmp_path) / "vidit") as store:
        for slug, scale, moved in wantings:
            seed_loop(store, slug, timescale=scale, last_movement=moved)
        for ident, loop, rung in entries:
            seed_entry(store, ident, loop=loop, rung=rung)
        if message:
            seed_message(store)
        for index, (slug, at) in enumerate(touches):
            store.record(Op.TOUCH, f"tc_{index}", at,
                         **touch_module.raised(slug, origin=ORIGIN))
        return narrowed(store.state(), ceiling or Ceiling())


def run(gate, view, *, main_id="vidit", now=NOW, in_crisis=False,
        last_interruption=None):
    return asyncio.run(gate.consider(
        view, main_id=main_id, now=now, in_crisis=in_crisis,
        last_interruption=last_interruption,
    ))


def a_gate(*answers, reach=Reachability.OPEN, voice=None, judge=None, **kwargs):
    """A gate, its channel and its judge, so a case can count every call."""
    channel = FakeChannel(reach=reach, **kwargs)
    urgency = judge if judge is not None else Judge(*answers)
    return (
        Interrupt(channel=channel, urgency=urgency,
                  voice=voice if voice is not None else stub_voice()),
        channel,
        urgency,
    )


# ── the five refusals, each alone ────────────────────────────────────────────


@pytest.mark.cap10
@pytest.mark.cap12
def test_a_main_in_crisis_is_not_interrupted_and_is_never_judged(tmp_path):
    """Matrix: *in crisis* → refused before anything else, judge never called."""
    gate, channel, judge = a_gate(True)
    outcome = run(gate, a_view(tmp_path), in_crisis=True)

    assert outcome.reason == CRISIS and not outcome.interrupted
    assert judge.calls == 0, "a main in the mode was reasoned about (CAP-12)"
    assert channel.sent == []


@pytest.mark.cap10
@pytest.mark.cap12
def test_the_mode_refuses_before_the_platform_is_even_asked(tmp_path):
    """The mode is *first*, not merely *before urgency*.

    A main who is both in the mode and unreachable is refused as ``crisis``,
    and the platform is not asked about them at all. This is the case that
    fails if the two are swapped — every other assertion in this file passes
    under either order, because both refusals produce silence.
    """
    gate, channel, judge = a_gate(True, reach=Reachability.NEVER_CONTACTED)
    outcome = run(gate, a_view(tmp_path), in_crisis=True)

    assert outcome.reason == CRISIS
    assert channel.queries == [], "the platform was asked about a main in crisis"
    assert judge.calls == 0


@pytest.mark.cap10
@pytest.mark.parametrize(
    "reach",
    [answer for answer in Reachability if not answer.may_send_freeform],
)
def test_a_main_the_platform_forbids_a_send_to_is_never_judged(tmp_path, reach):
    """Acceptance: *the urgency judge is never called — a counter at zero.*

    Swept over every refusal the port has, so a fourth one added later is
    covered by this rule rather than by a case naming the two that exist.
    """
    gate, channel, judge = a_gate(True, reach=reach)
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == str(reach) and not outcome.interrupted
    assert judge.calls == 0, "a model was paid for a main who cannot be reached"
    assert channel.sent == []


@pytest.mark.cap10
@pytest.mark.ad28
def test_a_ceiling_at_behave_sends_nothing_and_never_judges(tmp_path):
    """Matrix: *capped* → no interruption (AD-28)."""
    view = a_view(tmp_path, ceiling=Ceiling(License.BEHAVE))
    gate, channel, judge = a_gate(True)
    outcome = run(gate, view)

    assert outcome.reason == CAPPED and not outcome.interrupted
    assert judge.calls == 0
    assert channel.sent == []


@pytest.mark.cap10
def test_a_wanting_inside_its_own_period_is_not_interrupted_about(tmp_path):
    """Matrix: *nagging* → refused by the loop's own clock, before the judge."""
    view = a_view(tmp_path, touches=(("swim-weekly", stamp(NOON - 3 * 86_400)),))
    gate, channel, judge = a_gate(True)
    outcome = run(gate, view)

    assert outcome.reason == NAGGING and not outcome.interrupted
    assert outcome.considered == 1 and outcome.bounded == 1
    assert judge.calls == 0
    assert channel.sent == []


# ── the nagging bound is the loop's own period ───────────────────────────────


@pytest.mark.cap10
@pytest.mark.parametrize("scale", list(Timescale))
def test_one_interval_gets_four_answers_one_per_timescale(tmp_path, scale):
    """Acceptance: *the period is the loop's, asserted across all four.*

    One interval — eight days since Half last raised the wanting — swept over
    every timescale the vocabulary names. A days-loop and a weeks-loop may be
    interrupted about; a months-loop and a years-loop may not. A single shared
    cooldown, which is the reference implementation's shape, cannot produce
    this table: it would nag the first two or never reach the last two.
    """
    eight_days_ago = stamp(NOON - 8 * 86_400)
    view = a_view(
        tmp_path,
        wantings=(("swim-weekly", str(scale), "2020-01-01"),),
        touches=(("swim-weekly", eight_days_ago),),
    )
    gate, _, judge = a_gate(False)
    outcome = run(gate, view)

    expected = 8.0 > PERIOD_DAYS[scale]
    assert (judge.calls == 1) is expected, (
        f"a {scale} loop raised eight days ago answered the wrong way"
    )
    assert (outcome.reason == NOTHING_CLOSING) is expected


@pytest.mark.cap10
@pytest.mark.parametrize("scale", list(Timescale))
@pytest.mark.parametrize("side", ["inside", "outside"])
def test_both_sides_of_the_boundary_at_every_timescale(tmp_path, scale, side):
    """The boundary is strict and it is the ledger's own: *more than* one
    period may be interrupted about, exactly one period may not."""
    period = PERIOD_DAYS[scale]
    offset = period * 86_400 if side == "inside" else (period + 1) * 86_400
    view = a_view(
        tmp_path,
        wantings=(("swim-weekly", str(scale), "2020-01-01"),),
        touches=(("swim-weekly", stamp(NOON - offset)),),
    )
    gate, _, judge = a_gate(False)
    run(gate, view)

    assert judge.calls == (0 if side == "inside" else 1)


@pytest.mark.cap10
def test_a_wanting_with_no_period_is_not_interrupted_about_even_once(tmp_path):
    """A wanting with no timescale has no own clock to be held to, so it is
    refused rather than raised on a borrowed one — and it is refused by
    ``touchable``, which owns that rule, rather than by a copy here."""
    view = a_view(tmp_path, wantings=(("swim-weekly", None, "2026-07-01"),))
    gate, _, judge = a_gate(True)
    outcome = run(gate, view)

    assert not outcome.interrupted and outcome.bounded == 1
    assert judge.calls == 0


@pytest.mark.cap10
def test_a_finished_wanting_is_not_interrupted_about(tmp_path):
    """Finished is not silent: an `achieved` wanting has stopped running, so
    nothing about it can be closing — and the reason it refuses with is the
    bound's own (`not-live`), which is why ``choose.REASONS`` is inside this
    module's closed set rather than ``NAGGING`` alone."""
    a_view(tmp_path, wantings=(("swim-weekly", "weeks", "2026-07-01"),))
    with Store(Path(tmp_path) / "vidit") as store:
        store.record(Op.LOOP_TRANSITION, "l_done", "2026-08-20T00:00:00Z",
                     **loops.move("swim-weekly", at="2026-08-20",
                                  state="achieved"))
        view = narrowed(store.state(), Ceiling())
    gate, _, judge = a_gate(True)
    outcome = run(gate, view)

    assert not outcome.interrupted and judge.calls == 0
    assert outcome.bounded == 1
    assert outcome.reason == NOT_LIVE and outcome.reason in REASONS


# ── the interruption's own bound ─────────────────────────────────────────────


@pytest.mark.cap10
def test_a_main_just_interrupted_is_not_interrupted_again(tmp_path):
    """Matrix: *just interrupted* → not repeated, by its own bound."""
    gate, channel, judge = a_gate(True)
    outcome = run(gate, a_view(tmp_path),
                  last_interruption=stamp(NOON - 3_600))

    assert outcome.reason == JUST_INTERRUPTED and not outcome.interrupted
    assert judge.calls == 0
    assert channel.sent == []


@pytest.mark.cap10
def test_the_bound_is_per_main_and_not_the_interrupted_wantings_period(tmp_path):
    """gbrain's lesson, in the direction this story could get it wrong.

    An interruption about a **years** wanting must not silence a **days**
    wanting for a year. The bound is what an unexpected message costs the
    person receiving it — one of their days — and does not vary with what it
    was about; the per-wanting clock is gate 4's job and is asserted separately.
    """
    view = a_view(
        tmp_path,
        wantings=(("farmland", "years", "2020-01-01"),
                  ("stretch", "days", "2026-08-30")),
        entries=(("b_1", "farmland", License.ASSERT),
                 ("b_2", "stretch", License.ASSERT)),
    )
    gate, _, judge = a_gate(True)
    two_days_after_a_farmland_interruption = stamp(NOON - 2 * 86_400)
    outcome = run(gate, view,
                  last_interruption=two_days_after_a_farmland_interruption)

    assert judge.calls >= 1, "a years-loop interruption silenced everything"
    assert outcome.interrupted


@pytest.mark.cap10
def test_the_bound_is_a_rolling_day_and_the_mornings_is_a_civil_one():
    """*Bounded harder than a morning*, demonstrated rather than asserted.

    The morning's one-a-day rule is the main's own **civil** day read from a
    stored marker, so two mornings twenty minutes apart either side of local
    midnight are both legal. The interruption's bound is a **rolling** day from
    the last one, so exactly that pair is refused.
    """
    midnight = 1_788_220_800.0  # 2026-09-01T00:00:00Z
    before, after = midnight - 600, midnight + 600

    # The morning's marker: two civil days, so the second morning is not
    # covered by the first — asserted through the rule that owns it.
    assert touch_module.spoken_on({"local_day": "2026-08-31"}, "2026-09-01") is False

    # The interruption's bound over the same two instants.
    assert unspent(stamp(before), now=stamp(after)).may_interrupt is False


@pytest.mark.cap10
def test_the_bound_lets_one_through_once_more_than_a_day_has_passed(tmp_path):
    gate, channel, judge = a_gate(True)
    outcome = run(gate, a_view(tmp_path),
                  last_interruption=stamp(NOON - 2 * 86_400))

    assert outcome.interrupted and judge.calls == 1
    assert len(channel.sent) == 1


@pytest.mark.cap10
def test_the_bounds_boundary_is_strict(tmp_path):
    """At exactly one day it refuses; a second past it, it does not."""
    assert unspent(stamp(NOON - DAY), now=stamp(NOON)).may_interrupt is False
    assert unspent(stamp(NOON - DAY - 1), now=stamp(NOON)).may_interrupt is True


@pytest.mark.cap10
def test_an_interruption_stamped_in_the_future_buys_no_negative_age():
    """Clamped, so a corrected clock cannot let the next one straight through
    — the same clamp ``silence`` and ``touchable`` apply."""
    ahead = unspent(stamp(NOON + 10 * 86_400), now=stamp(NOON))
    assert ahead.may_interrupt is False and ahead.since_days == 0.0


@pytest.mark.cap10
def test_an_unreadable_last_interruption_is_treated_as_none_and_says_so():
    """The bypass case, and it is the one ``choose.Bound`` already argues for:
    refusing would silence this main's interruptions for ever over one corrupt
    value, because the stamp is replaced only by a later interruption."""
    degraded = unspent("half past four", now=stamp(NOON))
    assert degraded.may_interrupt is True and degraded.degraded is True
    assert degraded.since_days is None


@pytest.mark.cap10
def test_an_unreadable_now_refuses_rather_than_guessing():
    """The caller's own stamp, reported apart because the fix is different."""
    refused = unspent(stamp(NOON), now="soon")
    assert refused.may_interrupt is False and refused.reason == UNREADABLE


@pytest.mark.cap10
def test_a_main_never_interrupted_has_nothing_to_be_inside_of():
    assert unspent(None, now=stamp(NOON)).may_interrupt is True


@pytest.mark.cap10_restraint
def test_the_interruptions_own_bound_is_read_from_the_open_loop_vocabulary():
    """Not a number typed into this module: it is the shortest period the
    ledger has a name for, and it is the same derivation ``half.trust.stakes``
    makes for the same sentence — an unprompted message is felt for the main's
    day and is then over."""
    assert INTERRUPTION_DAYS == PERIOD_DAYS[Timescale.DAYS]
    assert INTERRUPTION_DAYS == STAKES_INTERRUPTION_DAYS


# ── the judgement, and it is last ────────────────────────────────────────────


@pytest.mark.cap10
def test_the_shipped_build_wires_no_judge_and_never_interrupts(tmp_path):
    """Acceptance: *given no urgency source wired, nothing is ever sent.*

    And the four refusals above it still ran: the wantings were ordered, the
    bound was applied, and the counts say so — which is what keeps CAP-10's
    whole rule under test with no provider anywhere in the tree.
    """
    channel = FakeChannel()
    gate = Interrupt(channel=channel, urgency=None, voice=stub_voice())
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == NO_JUDGE and outcome.unwired is True
    assert not outcome.interrupted and channel.sent == []
    assert outcome.considered == 1 and outcome.consulted == 0


@pytest.mark.cap10
def test_no_judge_is_a_fact_of_its_own_and_not_a_flavour_of_nothing_closing(
    tmp_path,
):
    """A pass that asked nobody and a pass that asked and heard *no* are
    different passes, and the first is the one this composition is in for ever.
    A single ``nothing was sent`` assertion cannot tell them apart."""
    view = a_view(tmp_path)
    silent = Interrupt(channel=FakeChannel(), urgency=None, voice=stub_voice())
    asked, _, _ = a_gate(False)

    unwired = run(silent, view)
    refused = run(asked, view)

    assert (unwired.reason, unwired.unwired, unwired.consulted) == (
        NO_JUDGE, True, 0
    )
    assert (refused.reason, refused.unwired, refused.consulted) == (
        NOTHING_CLOSING, False, 1
    )
    assert refused.not_closing == 1 and refused.unsaid == 0


@pytest.mark.cap10
def test_a_judge_that_says_no_sends_nothing(tmp_path):
    gate, channel, judge = a_gate(False)
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == NOTHING_CLOSING and not outcome.interrupted
    assert (outcome.not_closing, outcome.unsaid, outcome.failed) == (1, 0, 0)
    assert channel.sent == []


@pytest.mark.cap10
def test_a_judge_that_cannot_say_is_counted_apart_from_one_that_says_no(
    tmp_path,
):
    """Acceptance: *cannot say is not no.*

    Both are silence, so the outcome cannot tell them apart; the counts can,
    and each moves a field the other cannot.
    """
    view = a_view(tmp_path)
    said_no, _, _ = a_gate(False)
    could_not_say, _, _ = a_gate(None)

    no = run(said_no, view)
    unsure = run(could_not_say, view)

    assert (no.not_closing, no.unsaid) == (1, 0)
    assert (unsure.not_closing, unsure.unsaid) == (0, 1)
    assert no.reason == unsure.reason == NOTHING_CLOSING
    assert not no.interrupted and not unsure.interrupted


@pytest.mark.cap10
def test_a_judgement_that_raises_costs_its_option_and_nothing_else(tmp_path):
    """Matrix: *judge raises* → silence, nothing else affected, never fatal.

    The first wanting's judgement throws; the second is still asked, and the
    pass ends without an exception reaching the caller.
    """
    view = a_view(
        tmp_path,
        wantings=(("swim-weekly", "weeks", "2026-07-01"),
                  ("read-daily", "weeks", "2026-07-01")),
        entries=(("b_1", "swim-weekly", License.ASSERT),
                 ("b_2", "read-daily", License.ASSERT)),
    )
    judge = Judge(RuntimeError("the provider fell over"), False)
    gate, channel, _ = a_gate(judge=judge)
    outcome = run(gate, view)

    assert outcome.failed == 1 and outcome.not_closing == 1
    assert outcome.consulted == 2 and not outcome.interrupted
    assert channel.sent == []


@pytest.mark.cap10
def test_a_judgement_is_billed_before_the_call_and_not_after(tmp_path):
    """A provider that failed every call must not report zero consultations —
    a bound whose meter reads zero on the night it mattered."""
    judge = Judge(RuntimeError("down"))
    gate, _, _ = a_gate(judge=judge)
    outcome = run(gate, _many_wantings(tmp_path, 5))

    assert outcome.consulted == JUDGEMENTS == outcome.failed


@pytest.mark.cap10
def test_a_judge_past_the_bound_is_silence_and_never_blocks(
    tmp_path, monkeypatch
):
    """Matrix: *judge slow* → silence, never blocks."""
    monkeypatch.setattr(interrupt, "BOUND_SECONDS", 0.01)
    judge = Judge(True, sleep=0.5)
    gate, channel, _ = a_gate(judge=judge)
    outcome = run(gate, a_view(tmp_path))

    assert outcome.failed == 1 and not outcome.interrupted
    assert channel.sent == []


@pytest.mark.cap10
def test_a_judge_over_its_cap_refuses_rather_than_overspending(tmp_path):
    """Matrix: *over the cap* → refuses rather than overspending.

    A per-call or per-pass cost cap belongs to a judge — this build has none —
    and what the gate promises is that a judge refusing for that reason, by
    either of the two ways it can, is silence and never a send.
    """
    view = a_view(tmp_path)
    for refusal in (None, RuntimeError("over budget")):
        gate, channel, _ = a_gate(refusal)
        outcome = run(gate, view)
        assert not outcome.interrupted and channel.sent == []


@pytest.mark.cap10
def test_a_pass_buys_no_more_judgements_than_its_bound(tmp_path):
    """The gate's own per-pass bound: a main with five weighable wantings buys
    ``JUDGEMENTS`` opinions and stops."""
    gate, _, judge = a_gate(False)
    outcome = run(gate, _many_wantings(tmp_path, 5))

    assert outcome.considered == 5 and outcome.bounded == 0
    assert judge.calls == JUDGEMENTS == outcome.consulted


@pytest.mark.cap10
def test_the_pass_stops_at_the_first_option_judged_closing(tmp_path):
    """Acceptance: *two loops judged closing → at most one interruption.*

    And it is not one because only one was ever asked: the pass stops, so the
    second judgement is never bought — asserted by the counter, which is the
    only thing that can tell *stopped* from *never started*.
    """
    view = _many_wantings(tmp_path, 3)
    gate, channel, judge = a_gate(True)
    outcome = run(gate, view)

    assert outcome.interrupted and outcome.closing == 1
    assert judge.calls == 1 and outcome.consulted == 1
    assert len(channel.sent) == 1


@pytest.mark.cap10
def test_two_wantings_closing_produce_one_message_and_never_a_digest(tmp_path):
    """Matrix: *two loops closing* → at most one, never a digest."""
    view = _many_wantings(tmp_path, 2)
    gate, channel, _ = a_gate(True)
    outcome = run(gate, view)

    assert isinstance(outcome.sent, str)
    assert len(channel.sent) == 1
    body = channel.sent[0][1]
    others = [slug for slug in ("w_0", "w_1") if slug != outcome.sent]
    for slug in others:
        assert slug not in body


@pytest.mark.cap10
def test_the_order_the_options_are_weighed_in_is_total_and_deterministic(
    tmp_path,
):
    """Quietest in its **own** periods first, then the wanting's id — the unit
    ``choose.Choice.order`` uses, so *quieter* means the same thing for a
    routine and for a farmland loop."""
    view = a_view(
        tmp_path,
        wantings=(("stretch", "days", "2026-08-02"),      # ~30 own periods
                  ("farmland", "years", "2026-08-02")),   # ~0.08 own periods
        entries=(("b_1", "stretch", License.ASSERT),
                 ("b_2", "farmland", License.ASSERT)),
    )
    assert [loop.id for loop in weighable(view, now=NOW.stamp)] == [
        "stretch", "farmland"
    ]


# ── what it says ─────────────────────────────────────────────────────────────


@pytest.mark.cap10
def test_an_interruption_is_composed_prose_with_no_label_or_id(tmp_path):
    """Acceptance: *composed prose, no label, no belief id, no scaffolding.*"""
    view = a_view(tmp_path)
    voice, holder = a_voice()
    gate, channel, _ = a_gate(True, voice=voice)
    outcome = run(gate, view)

    assert outcome.interrupted and len(channel.sent) == 1
    body = channel.sent[0][1]
    assert body == outcome.text and COMPOSED in body
    assert CLAIMS["b_1"] in body, "the `assert` material never reached the wire"
    for scaffolding in ("content[", "question[", "directive[", "b_1", "may-be-said"):
        assert scaffolding not in body
    assert holder.calls == 1


@pytest.mark.cap10
def test_a_deployment_that_has_equipped_nobody_interrupts_nobody(tmp_path):
    """The fail-closed default: a gate built with no composer is silent rather
    than putting its own serialization on the wire."""
    channel = FakeChannel()
    gate = Interrupt(channel=channel, urgency=Judge(True))
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == NO_MODEL and not outcome.interrupted
    assert channel.sent == []


@pytest.mark.cap10
def test_a_failed_generation_falls_back_through_the_voices_own_ladder(tmp_path):
    """Matrix: *the fallback* → the voice's ladder, unchanged.

    The reason comes back out of ``voice.gate.SILENCES`` rather than being
    respelled here, so a reason added there cannot become one this gate fails
    to count.
    """
    voice = interrupt.Voice({"vidit": GeneratorDouble("")}, bound_seconds=1.0)
    gate, channel, _ = a_gate(True, voice=voice)
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason in SILENCES and outcome.reason in REASONS
    assert not outcome.interrupted and channel.sent == []


@pytest.mark.cap10
def test_the_platform_is_asked_again_after_composing(tmp_path):
    """A window that closes while the sentence is being written costs the
    message, not the main's confidence — the finding that cost the morning a
    day's message in review."""
    gate, channel, _ = a_gate(
        True, reach=[Reachability.OPEN, Reachability.WINDOW_CLOSED],
    )
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == str(Reachability.WINDOW_CLOSED)
    assert not outcome.interrupted and channel.sent == []
    assert len(channel.queries) == 2


@pytest.mark.cap10
def test_a_send_that_raises_is_counted_and_never_retried(tmp_path):
    gate, channel, _ = a_gate(True, fail=RuntimeError("the platform"))
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == UNSENT and not outcome.interrupted


@pytest.mark.cap10
def test_a_channel_that_carried_no_part_is_not_a_message_sent(tmp_path):
    """``SendResult.parts == 0`` is the port's own way of saying *nothing was
    delivered*, and a caller that discards it records a non-delivery as a
    send."""
    gate, channel, _ = a_gate(True, parts=0)
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == UNSENT and not outcome.interrupted


@pytest.mark.cap10
@pytest.mark.parametrize(
    "result", [SendResult("m", 1), SendResult("m", 0), None, object()]
)
def test_delivery_is_read_the_same_way_the_morning_reads_it(result):
    """One contract sentence, two readers, and they may not drift: a second,
    weaker reading of *zero parts means nothing was delivered* is how one of
    the two comes to spend a main's day on nothing."""
    from half.surface.morning import _delivered

    assert delivered(result) is _delivered(result)


# ── the ceiling, and where it is enforced ────────────────────────────────────


@pytest.mark.cap10
@pytest.mark.ad28
def test_the_cheap_ceiling_gate_never_refuses_where_resolution_would_speak(
    tmp_path,
):
    """The gate's free refusal may only refuse where the ladder's resolution
    would also refuse — it is that answer hoisted above the spending, never a
    second opinion about it.

    The whole table is pinned rather than the implication alone, because an
    implication over a sweep is satisfied by a build in which nothing can ever
    be said: two of the three rungs would then assert nothing at all, which is
    a case that passes either way.
    """
    spoke, refused = {}, {}
    for rung in RUNGS:
        view = a_view(tmp_path / str(rung), ceiling=Ceiling(rung))
        context, _ = split_context(
            material_for(view, loop="swim-weekly"), now=NOW.stamp,
            ceiling=view.ceiling,
        )
        spoke[rung] = bool(speech(context))
        refused[rung] = height(view.ceiling.rung) < height(SPEAKS_AT)

    assert refused == {
        License.BEHAVE: True, License.ASK: False, License.ASSERT: False,
    }
    # Strictly weaker than resolution, and this is where that is visible: an
    # unbought `assert` belief capped at `ask` becomes a directive, so the
    # ladder refuses a rung the cheap gate lets through. The reverse never
    # happens, which is the property.
    assert spoke == {
        License.BEHAVE: False, License.ASK: False, License.ASSERT: True,
    }
    for rung in RUNGS:
        assert not (refused[rung] and spoke[rung]), (
            f"the cheap ceiling gate refused at {rung} where the ladder spoke"
        )


@pytest.mark.cap10
def test_material_the_ladder_will_not_let_be_said_is_silence(tmp_path):
    """A permissive ceiling and nothing quotable on the wanting: the judgement
    is bought, the ladder still refuses, and nothing is sent."""
    view = a_view(
        tmp_path, entries=(("b_1", "swim-weekly", License.BEHAVE),),
    )
    gate, channel, judge = a_gate(True)
    outcome = run(gate, view)

    assert outcome.reason == NOTHING_MAY_BE_SAID and not outcome.interrupted
    assert judge.calls == 1, "the ladder refused before the judgement, not after"
    assert channel.sent == []


# ── the ordinary outcome ─────────────────────────────────────────────────────


@pytest.mark.cap10
def test_a_main_with_no_wanting_has_nothing_to_weigh(tmp_path):
    view = a_view(tmp_path, wantings=(),
                  entries=(("b_1", None, License.ASSERT),))
    gate, _, judge = a_gate(True)
    outcome = run(gate, view)

    assert outcome.reason == NOTHING_TO_WEIGH and judge.calls == 0


@pytest.mark.cap10
def test_the_ordinary_refusal_is_quiet_and_is_not_a_fault(tmp_path, caplog):
    """Matrix: *the ordinary refusal* → silence, the common case. Nothing is
    logged as an error, nothing is retried and nothing is queued (AD-27)."""
    gate, channel, _ = a_gate(False)
    with caplog.at_level(logging.DEBUG):
        outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == NOTHING_CLOSING and channel.sent == []
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


@pytest.mark.cap10
def test_a_view_this_build_cannot_read_costs_the_interruption_not_the_pass(
    tmp_path,
):
    """Never raises: one main's unreadable record must not end anybody else's
    pass, and *we could not tell* has a correct outcome and it is silence."""
    class Exploding(FakeChannel):
        def capability_query(self, main_id):
            raise RuntimeError("the transport")

    gate = Interrupt(channel=Exploding(), urgency=Judge(True),
                     voice=stub_voice())
    outcome = run(gate, a_view(tmp_path))

    assert outcome.reason == UNREADABLE and not outcome.interrupted


@pytest.mark.cap10
def test_every_reason_this_gate_can_produce_is_in_the_closed_set(tmp_path):
    """A caller counting refusals counts constants and never a message — an
    exception message routinely quotes a record out of a main's own ledger."""
    view = a_view(tmp_path / "one")
    produced = set()
    for kwargs, judge, reach, parts in (
        ({"in_crisis": True}, True, Reachability.OPEN, 1),
        ({}, True, Reachability.NEVER_CONTACTED, 1),
        ({}, True, Reachability.WINDOW_CLOSED, 1),
        ({"last_interruption": stamp(NOON - 60)}, True, Reachability.OPEN, 1),
        ({}, False, Reachability.OPEN, 1),
        ({}, None, Reachability.OPEN, 1),
        ({}, True, Reachability.OPEN, 0),
    ):
        gate, _, _ = a_gate(judge, reach=reach, parts=parts)
        outcome = run(gate, view, **kwargs)
        if outcome.reason is not None:
            produced.add(outcome.reason)

    capped = a_view(tmp_path / "two", ceiling=Ceiling(License.BEHAVE))
    gate, _, _ = a_gate(True)
    produced.add(run(gate, capped).reason)
    silent = Interrupt(channel=FakeChannel(), urgency=None, voice=stub_voice())
    produced.add(run(silent, view).reason)

    assert produced <= REASONS
    assert len(produced) >= 8, "the sweep stopped exercising the refusals"


@pytest.mark.cap10
@pytest.mark.parametrize("first", ["crisis", "unreachable", "capped", "bound"])
@pytest.mark.parametrize("second", ["crisis", "unreachable", "capped", "bound"])
def test_every_pair_of_per_main_refusals_still_refuses(tmp_path, first, second):
    """Independent gates, each of which alone produces silence, are exactly the
    shape where a second one can stop doing anything with the suite green. Every
    pair, in both orders."""
    ceiling = Ceiling(License.BEHAVE) if "capped" in (first, second) else None
    view = a_view(tmp_path, ceiling=ceiling)
    reach = (
        Reachability.NEVER_CONTACTED if "unreachable" in (first, second)
        else Reachability.OPEN
    )
    gate, channel, judge = a_gate(True, reach=reach)
    outcome = run(
        gate, view,
        in_crisis="crisis" in (first, second),
        last_interruption=(
            stamp(NOON - 60) if "bound" in (first, second) else None
        ),
    )

    assert not outcome.interrupted and channel.sent == []
    assert outcome.reason in REASONS
    assert judge.calls == 0


# ── nothing durable, and a replay that does not move ─────────────────────────


@pytest.mark.cap10
def test_an_interruption_writes_nothing_and_the_fold_is_unchanged(tmp_path):
    """Matrix: *nothing durable* (AD-22) and *replay* (AD-4, AD-30).

    Nothing in this package writes, so a log carrying interruptions is a log
    with no interruptions in it: the fold before and after is byte-identical
    and the composed sentence is nowhere in the log.
    """
    with Store(Path(tmp_path) / "vidit") as store:
        seed_loop(store, "swim-weekly")
        seed_entry(store, "b_1", loop="swim-weekly")
        seed_message(store)
        before = store.state()
        lines = sorted((Path(tmp_path) / "vidit").rglob("*.jsonl"))
        bytes_before = {p: p.read_bytes() for p in lines}

        gate, channel, _ = a_gate(True)
        outcome = run(gate, narrowed(before, Ceiling()))
        assert outcome.interrupted

        after = store.state()

    assert after == before
    assert {p: p.read_bytes() for p in lines} == bytes_before
    for body in bytes_before.values():
        assert outcome.text.encode() not in body
        assert COMPOSED.encode() not in body


# ── the structural rules restraint rests on ──────────────────────────────────


@pytest.mark.cap10_restraint
def test_the_urgency_port_is_one_method():
    """Narrow by construction. A port that grew a second method is a port that
    can be handed a main."""
    assert door_of(Urgency) == {"closing"}
    assert isinstance(Judge(), Urgency), (
        "the double is not the port, so every case below asserts a shape "
        "nothing production holds"
    )


@pytest.mark.cap10_restraint
def test_the_channel_double_is_the_whole_port():
    """A double narrower than ``Channel`` would let this suite pass over a
    platform surface the real adapter does not have."""
    assert isinstance(FakeChannel(), Channel)


@pytest.mark.cap10_restraint
def test_an_option_carries_no_horizon():
    """*Do not add a horizon to a record* is this story's Never, and the place
    it would arrive first is the value a judge is handed."""
    names = {f.name for f in dataclass_fields(Option)}
    assert names == {"loop", "timescale", "last_movement", "claims"}
    for name in names:
        assert not any(
            word in name
            for word in ("horizon", "deadline", "expiry", "expires", "due", "by")
        )


@pytest.mark.cap10_restraint
def test_an_option_names_no_main_and_no_belief(tmp_path):
    """What a judge can see is decided at the door, not by what a judge asks
    for: no main id, no belief id, no license, no support set."""
    view = a_view(tmp_path)
    option = option_for(weighable(view, now=NOW.stamp)[0], view=view)

    assert option.claims == (CLAIMS["b_1"],)
    assert "vidit" not in repr(option) and "b_1" not in repr(option)


@pytest.mark.cap10_restraint
def test_the_tree_holds_no_urgency_implementation():
    """The seam ships and the judge does not. Asserted over the whole package
    rather than by absence in one file, so a judge added next year fails here
    rather than passing unnoticed."""
    implementations = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "closing":
                implementations.append(str(path.relative_to(ROOT)))
    assert implementations == ["half/interrupt/port.py"]


@pytest.mark.cap10_restraint
def test_no_module_in_the_package_names_the_model_or_the_network():
    """``half/interrupt`` is a *rule*, and a rule that could reach a provider is
    a rule one refactor away from being the judge it deliberately is not.

    The channel is deliberately **not** on this list: an interruption that
    could not send would not be an interruption. What is forbidden is the model
    and every route to the wire that is not the port.
    """
    forbidden = ("half.model", "anthropic", "httpx", "socket", "urllib",
                 "http", "requests")
    for path in sorted(PACKAGE.rglob("*.py")):
        reached = sorted(
            name for name in resolved_imports(path)
            if any(name == root or name.startswith(f"{root}.")
                   for root in forbidden)
        )
        assert reached == [], f"{path.name} reaches {reached}"


@pytest.mark.cap10_restraint
def test_nothing_in_the_package_can_write_a_record():
    """The rule is separated from the append, as it is in ``ladder``,
    ``loops.ledger`` and ``surface.touch``. This module has no store, no mutex
    and no path to a log — so a build that started writing interruptions would
    have to import one, and this is where that fails."""
    stores = ("half.store", "half.actor")
    for path in sorted(PACKAGE.rglob("*.py")):
        reached = sorted(
            name for name in resolved_imports(path)
            if any(name == root or name.startswith(f"{root}.")
                   for root in stores)
        )
        assert reached == [], f"{path.name} reaches a store: {reached}"


@pytest.mark.cap10_restraint
def test_the_package_does_not_touch_what_the_morning_chooses():
    """It reuses the nagging bound and the rung an unprompted surface speaks
    from; it does not reach the candidate set, the day marker or the choice."""
    taken: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        taken |= {
            name for name in resolved_imports(path)
            if name.startswith("half.surface.")
        }
    assert taken == {
        "half.surface.choose", "half.surface.choose.NAGGING",
        "half.surface.choose.REASONS", "half.surface.choose.touchable",
        "half.surface.morning", "half.surface.morning.CRISIS",
        "half.surface.morning.NOTHING_MAY_BE_SAID",
        "half.surface.morning.SPEAKS_AT", "half.surface.morning.UNREADABLE",
        "half.surface.morning.UNSENT", "half.surface.morning.speech",
        "half.surface.view", "half.surface.view.SurfaceView",
    }


@pytest.mark.cap10_restraint
def test_nothing_in_the_package_reads_a_clock():
    """AD-30: one clock reader, and this is not it. ``now`` is the stamp the
    caller was handed."""
    banned = {"time", "datetime", "utcnow", "now", "monotonic", "today"}
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned, path.name
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "utcnow", "monotonic", "time", "today"
                }, f"{path.name} reads a clock"


@pytest.mark.cap10_restraint
def test_the_result_has_no_plural_door_onto_the_send_path():
    """*At most one interruption, never a digest* is a property of the shape:
    there is nowhere on ``Weighed`` a second wanting could go."""
    annotations = {f.name: f.type for f in dataclass_fields(Weighed)}
    assert annotations["sent"] == "str | None"
    assert not any(
        "tuple" in str(kind) or "list" in str(kind)
        for kind in annotations.values()
    )


@pytest.mark.cap10_restraint
def test_the_per_pass_judgement_bound_is_pinned_by_value():
    """Raising it is a red test and a deliberate edit, never a quiet
    multiplication of every main's bill."""
    assert JUDGEMENTS == 3
    assert BOUND_SECONDS == 5.0


@pytest.mark.cap10_restraint
def test_the_gate_refuses_a_caller_who_forgot_the_mode_or_the_bound():
    """Two of the five refusals could be switched off by omission, and nothing
    would say they had been — the rule ``Voice.compose`` makes about
    ``withheld``. Forgetting one is a ``TypeError`` at the call site."""
    signature = inspect.signature(Interrupt.consider)
    for name in ("in_crisis", "last_interruption"):
        parameter = signature.parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


@pytest.mark.cap10_restraint
def test_the_composition_root_wires_no_urgency_source(tmp_path, monkeypatch):
    """Acceptance and Intent: *a deployment with none never interrupts.*

    Asserted **by value** on the object the shipped composition builds, not by
    finding a keyword in the source — which is how story 6d's identical claim
    passed with the value set to ``None`` for the wrong reason.
    """
    from half import __main__ as entry
    from half.config import Config

    config = Config(root=tmp_path, mains={"1": "vidit"})
    wiring = entry.build(config, token="x" * 40)
    try:
        assert isinstance(wiring.interrupt, Interrupt)
        assert wiring.interrupt.urgency is None
        assert wiring.interrupt.voice is wiring.voice
        assert wiring.interrupt.channel is wiring.channel
    finally:
        wiring.registry.close()


@pytest.mark.cap10_restraint
def test_a_gate_the_root_built_interrupts_nobody(tmp_path):
    """And the consequence, driven rather than argued.

    The wiring's **own** urgency source and its own composer, against a main
    the platform will carry a message to and a wanting nothing has ever raised
    — every gate open, every refusal above the judge passed — and the answer is
    still nothing, because there is nobody to ask. Only the channel is
    substituted, so the suite stays offline; the object under test is otherwise
    the one ``build`` returned.
    """
    from dataclasses import replace

    from half import __main__ as entry
    from half.config import Config

    config = Config(root=tmp_path, mains={"1": "vidit"})
    wiring = entry.build(config, token="x" * 40)
    try:
        shipped = replace(wiring.interrupt, channel=FakeChannel())
        assert shipped.urgency is wiring.interrupt.urgency is None
        outcome = run(shipped, a_view(tmp_path / "seed"))
        assert outcome.unwired is True and not outcome.interrupted
        assert outcome.considered == 1, "the refusals above the judge did not run"
    finally:
        wiring.registry.close()


# ── helpers used by more than one case ───────────────────────────────────────


def _many_wantings(tmp_path, count):
    """A main with ``count`` weighable wantings, none of them ever raised."""
    return a_view(
        tmp_path,
        wantings=tuple(
            (f"w_{i}", "weeks", "2026-07-01") for i in range(count)
        ),
        entries=tuple(
            (f"b_{i + 1}", f"w_{i}", License.ASSERT) for i in range(count)
        ),
    )
