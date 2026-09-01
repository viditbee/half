"""CAP-10 story 10: a loop is never touched faster than its own timescale.

The bound, the record it reads, and the wall between the two facts.

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test and passed as an argument, which is the whole
point of the design under test: the bound is arithmetic over a stamp out of the
log and an injected ``now``, so the same log and the same instant give the same
answer for ever (AD-30). A suite that used the real clock would pass tonight
and be irreproducible tomorrow.

**Both sides of every boundary are asserted.** Review on story 8 found a
threshold that anything between roughly six and thirteen satisfied, which is a
band rather than a number and a threshold nobody chose. The bound here is one
of the loop's *own* periods, and both *"at exactly one period"* and *"one
second past it"* are pinned — because the difference between ``>`` and ``>=``
on this comparison is the difference between a perfectly-kept weekly loop being
raised every week for ever and never being raised at all.

**The two facts are kept apart structurally, not by agreement.** A loop
*moving* and Half *raising* it are different records with different ops written
by different modules, and the tests below assert that by AST as well as by
behaviour: the module that writes a raise cannot name a movement date, and the
module that writes a movement cannot name a raise. That is story 8's rule
turned into a property of the two packages, because *"conflating them makes
Half's own attention look like the main's progress"* is exactly the rule
everybody agrees with and then breaks with one helpful line.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.civil import DAY
from half.errors import TouchError
from half.loops import ledger as loops
from half.loops.ledger import Loop
from half.loops.states import LIVE_STATES, LoopState
from half.loops.timescale import (
    NO_TIMESCALE,
    PERIOD_DAYS,
    UNKNOWN_TIMESCALE,
    UNREADABLE_NOW,
    Timescale,
)
from half.schedule.clock import stamp
from half.store.ops import TOUCH_ORIGINS, TOUCH_TENSION, Op
from half.store.records import LOOP, ORIGIN_ID, ORIGIN_KIND, TOUCH_FIELDS
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.choose import (
    NAGGING,
    NOT_LIVE,
    NO_LOOP,
    REASONS,
    UNREADABLE_TOUCH,
    touchable,
)
from half.surface.touch import Origin

pytestmark = [pytest.mark.cap8, pytest.mark.cap8_nagging]

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the same fixed instant ``tests/test_pass.py`` and
#: ``tests/test_schedule.py`` build from, so the three files' scenarios line up.
NOON = 1_788_264_000.0
NOW = stamp(NOON)

ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")


# ── helpers ──────────────────────────────────────────────────────────────────


def a_loop(
    slug="swim-weekly",
    *,
    state=LoopState.ADVANCING,
    timescale=Timescale.WEEKS,
    last_movement="2026-07-01",
):
    """One folded loop entry, as a ``Loop`` value."""
    return Loop(
        id=slug,
        state=None if state is None else str(state),
        timescale=None if timescale is None else str(timescale),
        last_movement=last_movement,
    )


def raised(slug, *, ago_days=None, at=None):
    """A touch table with ``slug`` raised ``ago_days`` before noon."""
    when = at if at is not None else stamp(NOON - (ago_days or 0) * DAY)
    return {slug: {"t": when, LOOP: slug, ORIGIN_KIND: TOUCH_TENSION,
                   ORIGIN_ID: "x_1"}}


# ═════════════════════════════════════════════════════════════════════════════
# matrix: nagging, years-loop / nagging, days-loop
#
# The two rows are the same scenario with one field changed, which is the whole
# claim: the bound is derived from the loop's *own* period and nothing else.
# ═════════════════════════════════════════════════════════════════════════════


def test_a_years_loop_raised_last_month_is_not_raised_again():
    """Matrix: *nagging, years-loop*. A farmland loop raised a month ago is
    inside its own period, so it is not a candidate."""
    bound = touchable(
        a_loop("buy-farmland", timescale=Timescale.YEARS),
        touches=raised("buy-farmland", ago_days=30),
        now=NOW,
    )
    assert not bound.may_touch
    assert bound.reason == NAGGING
    assert bound.period_days == 365
    assert bound.since_days == pytest.approx(30.0)


def test_a_days_loop_raised_last_month_may_be_raised():
    """Matrix: *nagging, days-loop*. The same month of silence, against a
    period of one day, is far past the bound."""
    bound = touchable(
        a_loop("take-medicine", timescale=Timescale.DAYS),
        touches=raised("take-medicine", ago_days=30),
        now=NOW,
    )
    assert bound.may_touch
    assert bound.reason is None
    assert bound.period_days == 1


def test_one_interval_answers_differently_for_every_timescale():
    """The bound is *per loop*, and this is the sweep that says so.

    The reference implementation this is lifted from — gbrain's ``nudge.ts`` —
    carries one ``NUDGE_COOLDOWN_DAYS = 14`` for every pattern it fires on. At
    fourteen days that single number would nag the days-loop and the weeks-loop
    and would still be a year short of the years-loop; here one interval gives
    four different answers, each the loop's own.
    """
    answers = {
        scale: touchable(
            a_loop(f"loop-{scale}", timescale=scale),
            touches=raised(f"loop-{scale}", ago_days=14),
            now=NOW,
        ).may_touch
        for scale in Timescale
    }
    assert answers == {
        Timescale.DAYS: True,
        Timescale.WEEKS: True,
        Timescale.MONTHS: False,
        Timescale.YEARS: False,
    }
    # And the bound each one was measured against is that loop's own period,
    # never a shared number.
    assert {
        scale: touchable(
            a_loop(f"loop-{scale}", timescale=scale),
            touches=raised(f"loop-{scale}", ago_days=14),
            now=NOW,
        ).period_days
        for scale in Timescale
    } == dict(PERIOD_DAYS)


# ═════════════════════════════════════════════════════════════════════════════
# the boundary, pinned on both sides
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("scale", list(Timescale))
def test_exactly_one_period_is_still_nagging(scale):
    """At exactly one period the loop has been raised *at* its own timescale,
    not slower than it. Not raised again.

    The same boundary ``half.loops.timescale.silence`` uses for the mirror
    question (``silent = days > period``), read the same way round, rather than
    a second convention for the same comparison — and it errs quiet, which is
    the correct direction when one nag is felt and one quiet day is not.
    """
    period = PERIOD_DAYS[scale]
    bound = touchable(
        a_loop(timescale=scale), touches=raised("swim-weekly", ago_days=period),
        now=NOW,
    )
    assert not bound.may_touch and bound.reason == NAGGING


@pytest.mark.parametrize("scale", list(Timescale))
def test_one_second_past_one_period_may_be_raised(scale):
    """The other side of the same boundary. Without this pair the bound could
    be ``>=``, ``>`` or a fortnight and the suite would not notice."""
    period = PERIOD_DAYS[scale]
    bound = touchable(
        a_loop(timescale=scale),
        touches=raised("swim-weekly", at=stamp(NOON - period * DAY - 1)),
        now=NOW,
    )
    assert bound.may_touch and bound.reason is None


def test_a_loop_half_has_never_raised_may_be_raised():
    """There is no interval, so there is nothing to be faster than."""
    bound = touchable(a_loop(), touches={}, now=NOW)
    assert bound.may_touch and bound.reason is None
    assert bound.since_days is None


# ═════════════════════════════════════════════════════════════════════════════
# every way the bound cannot be computed — and every one of them refuses
# ═════════════════════════════════════════════════════════════════════════════


def test_a_loop_with_no_timescale_is_not_raised_at_all():
    """A wanting with no period has no clock of its own to be held to.

    The alternative is raising it on a cadence borrowed from a wanting it is
    nothing like, which is exactly what ``half.loops.timescale`` refuses to
    invent — a farmland loop nagged monthly reads, to the main, as Half not
    understanding them at all. Recording a loop without a period is honest;
    raising it anyway is not.

    Note this holds *even though Half has never raised it*, which is the case a
    "no prior touch, so no nagging" reading would let through.
    """
    bound = touchable(a_loop(timescale=None), touches={}, now=NOW)
    assert not bound.may_touch and bound.reason == NO_TIMESCALE
    assert bound.period_days is None, "a period was borrowed from somewhere"


def test_a_timescale_this_build_cannot_read_is_not_raised():
    """A log from a later build degrades to silence rather than to a guess."""
    bound = touchable(
        Loop(id="x", state=str(LoopState.ADVANCING), timescale="fortnights",
             last_movement="2026-07-01"),
        touches={}, now=NOW,
    )
    assert not bound.may_touch and bound.reason == UNKNOWN_TIMESCALE


def test_a_touch_stamp_this_build_cannot_read_refuses_rather_than_assuming():
    """Reading an unmeasurable interval as *long enough* is how a bound stops
    bounding. The safe direction is the quiet one."""
    bound = touchable(
        a_loop(), touches={"swim-weekly": {"t": "yesterday"}}, now=NOW
    )
    assert not bound.may_touch and bound.reason == UNREADABLE_TOUCH


def test_a_touch_with_no_stamp_at_all_refuses():
    bound = touchable(a_loop(), touches={"swim-weekly": {}}, now=NOW)
    assert not bound.may_touch and bound.reason == UNREADABLE_TOUCH


def test_an_unreadable_now_is_reported_as_the_callers_own_fault():
    """Reported separately from an unreadable touch, because the fix differs:
    the log is fine and the caller is not — the same split
    ``timescale.silence`` makes."""
    bound = touchable(a_loop(), touches=raised("swim-weekly", ago_days=1),
                      now="not-an-instant")
    assert not bound.may_touch and bound.reason == UNREADABLE_NOW


def test_a_touch_dated_in_the_future_does_not_buy_an_immediate_re_raise():
    """Clamped at zero, so a skewed stamp cannot make a loop look raised a
    negative number of days ago and therefore raisable again."""
    bound = touchable(
        a_loop(), touches=raised("swim-weekly", at=stamp(NOON + 400 * DAY)),
        now=NOW,
    )
    assert not bound.may_touch and bound.reason == NAGGING
    assert bound.since_days == 0.0


@pytest.mark.parametrize(
    "state", [LoopState.ACHIEVED, LoopState.ABANDONED_BUT_UNADMITTED]
)
def test_a_finished_or_answered_wanting_is_not_raised(state):
    """``ledger.silent``'s filter, asked here for the same reason: an
    `achieved` loop is finished rather than quiet, and an
    `abandoned-but-unadmitted` one has already been asked about and answered.
    Raising either is the single most trust-destroying thing this selection
    could produce."""
    assert str(state) not in LIVE_STATES
    bound = touchable(a_loop(state=state), touches={}, now=NOW)
    assert not bound.may_touch and bound.reason == NOT_LIVE


def test_a_state_this_build_does_not_recognise_is_not_raised():
    bound = touchable(
        Loop(id="x", state="reconsidering", timescale="weeks",
             last_movement="2026-07-01"),
        touches={}, now=NOW,
    )
    assert not bound.may_touch and bound.reason == NOT_LIVE


def test_nothing_at_all_is_not_a_loop():
    assert touchable(None, touches={}, now=NOW).reason == NO_LOOP


def test_every_reason_the_bound_gives_is_one_of_the_closed_set():
    """AD-22: a caller logging a reason logs a constant, never a message."""
    cases = [
        touchable(None, touches={}, now=NOW),
        touchable(a_loop(state=LoopState.ACHIEVED), touches={}, now=NOW),
        touchable(a_loop(timescale=None), touches={}, now=NOW),
        touchable(Loop(id="x", state="advancing", timescale="aeons"),
                  touches={}, now=NOW),
        touchable(a_loop(), touches={"swim-weekly": {"t": "?"}}, now=NOW),
        touchable(a_loop(), touches=raised("swim-weekly", ago_days=1), now="?"),
        touchable(a_loop(), touches=raised("swim-weekly", ago_days=1), now=NOW),
    ]
    assert all(case.reason in REASONS for case in cases if case.reason)
    assert not any(case.may_touch and case.reason for case in cases), (
        "a bound answered 'go ahead' while carrying a reason not to"
    )


def test_the_same_loop_and_the_same_now_answer_identically_twice():
    """AD-30 at the seam that matters: the bound is a pure function."""
    args = dict(touches=raised("swim-weekly", ago_days=3), now=NOW)
    assert touchable(a_loop(), **args) == touchable(a_loop(), **args)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: touch recorded — what Half raised and when
# ═════════════════════════════════════════════════════════════════════════════


def test_a_touch_records_the_loop_and_what_it_cited(store):
    """Matrix: *touch recorded*. Both halves — what was raised, and when."""
    store.record(Op.TOUCH, "tc_1", NOW,
                 **touch_module.fields("swim-weekly", origin=ORIGIN))
    held = store.fold().touches["swim-weekly"]
    assert held[LOOP] == "swim-weekly"
    assert held[ORIGIN_KIND] == TOUCH_TENSION and held[ORIGIN_ID] == "x_1"
    assert held["t"] == NOW
    assert touch_module.raised_at(held) == NOW
    assert touch_module.origin_of(held) == ORIGIN


def test_a_touch_folds_and_replays(store):
    """The op is in the closed vocabulary and the fold materializes it — in
    memory and through SQLite, identically."""
    store.record(Op.TOUCH, "tc_1", NOW,
                 **touch_module.fields("swim-weekly", origin=ORIGIN))
    assert store.fold().canonical_json() == store.state().canonical_json()


def test_the_last_touch_is_the_last_one_the_fold_reads_not_the_latest_stamp(
    store
):
    """*"At most one a day"* is computed from ``last_touch``, and it is the log's
    own order rather than a comparison of stamps.

    Within a shard that is append order, and this pins it: a raise stamped
    *earlier* but appended *later* is the last touch. A max-by-``t`` would say
    the other one, and a clock that stepped backwards would then let an older
    raise win and buy a second message on a day one was already sent.

    (Across a month boundary the log's order is the shard order, which is
    ``t``-ordered — ``BeliefLog`` shards by month. That is the fold's own
    reading of the log and not a second opinion about it, and every stamp this
    op carries is the tick's own instant, so the two only diverge on a clock
    that jumped a month backwards.)
    """
    store.record(Op.TOUCH, "tc_1", stamp(NOON + 3 * DAY),
                 **touch_module.fields("swim-weekly", origin=ORIGIN))
    earlier = stamp(NOON)
    store.record(Op.TOUCH, "tc_2", earlier,
                 **touch_module.fields("buy-farmland", origin=ORIGIN))
    assert store.fold().last_touch["t"] == earlier
    assert store.fold().last_touch[LOOP] == "buy-farmland"


def test_a_second_touch_on_one_loop_supersedes_the_first(store):
    """The bound asks *"when did Half last raise this?"*, so the table holds
    the last raise per loop rather than all of them."""
    store.record(Op.TOUCH, "tc_1", stamp(NOON - 40 * DAY),
                 **touch_module.fields("swim-weekly", origin=ORIGIN))
    store.record(Op.TOUCH, "tc_2", NOW,
                 **touch_module.fields("swim-weekly", origin=ORIGIN))
    touches = store.fold().touches
    assert list(touches) == ["swim-weekly"]
    assert touches["swim-weekly"]["t"] == NOW


def test_a_touch_is_an_append_and_never_an_edit(store):
    """AD-3. Two raises are two lines; nothing is rewritten in place."""
    store.record(Op.TOUCH, "tc_1", stamp(NOON - 40 * DAY),
                 **touch_module.fields("swim-weekly", origin=ORIGIN))
    store.record(Op.TOUCH, "tc_2", NOW,
                 **touch_module.fields("swim-weekly", origin=ORIGIN))
    assert len([r for r in store.log if r.op is Op.TOUCH]) == 2


def test_erasing_a_loop_erases_every_raise_on_it_and_leaves_no_slug(store):
    """A loop slug is a phrase the main chose about their own life, and
    surviving an erasure is not an erasure. The touch is tombstoned by the
    same ``loop``-field match that tombstones a transition, and its record id
    is built from the stamp so the tombstone keeps nothing."""
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", last_movement="2026-01-04",
                                loops=store.state().loops))
    store.record(Op.TOUCH, "tc_2026-08-02T03:00Z", "2026-08-02T03:00Z",
                 **touch_module.fields("sell-the-flat", origin=ORIGIN))
    store.expunge("sell-the-flat", t="2026-08-03T00:00Z")

    state = store.fold()
    assert state.touches == {} and state.last_touch is None
    assert "sell-the-flat" in state.expunged_loops
    bodies = [r.data for r in store.log if r.op is Op.TOUCH]
    assert bodies == [{"id": "tc_2026-08-02T03:00Z", "op": "touch",
                       "t": "2026-08-02T03:00Z", "tombstone": True, "v": 6}]


def test_a_tombstoned_touch_does_not_poison_the_belief_namespace(store):
    """A touch's record id is the *append's*, not the loop's — so putting it in
    ``expunged`` would suppress whatever belief happened to share it, for ever.

    This is the collision the split ``expunged_loops`` set exists for, arriving
    through a second op. It was one comparison against one op before story 10;
    it is a set now, so the next append-keyed op is caught by the same rule.
    """
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", loops=store.state().loops))
    store.record(Op.TOUCH, "tc_x", "2026-08-02T03:00Z",
                 **touch_module.fields("sell-the-flat", origin=ORIGIN))
    store.expunge("sell-the-flat", t="2026-08-03T00:00Z")
    assert "tc_x" not in store.fold().expunged

    store.record(Op.ASSERT, "tc_x", "2026-08-04T00:00Z", claim="unrelated")
    assert store.fold().beliefs["tc_x"]["claim"] == "unrelated", (
        "a tombstoned touch's append id suppressed a belief sharing it"
    )


def test_a_raise_written_after_a_loop_was_erased_does_not_come_back(store):
    """The tombstone pass removes the raises written *before* the erasure; the
    fold's ``expunged_loops`` guard is what stops one written after it."""
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", loops=store.state().loops))
    store.expunge("sell-the-flat", t="2026-08-02T00:00Z")
    store.record(Op.TOUCH, "tc_1", "2026-08-03T00:00Z",
                 **touch_module.fields("sell-the-flat", origin=ORIGIN))
    state = store.fold()
    assert state.touches == {} and state.last_touch is None


# ═════════════════════════════════════════════════════════════════════════════
# matrix: untouched vs unmoved — the two facts stay separate
# ═════════════════════════════════════════════════════════════════════════════


def test_raising_a_loop_does_not_move_it(store):
    """Matrix: *untouched vs unmoved*. Half's attention is not the main's
    progress.

    The loop is silent past its own period, Half raises it, and afterwards it
    is *still* silent by exactly as much: nothing about the raise touched
    ``last_movement``, the state, or the loop table at all.
    """
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("buy-farmland", state="stalled",
                                timescale="years", last_movement="2020-03-12",
                                loops=store.state().loops))
    before = dict(store.fold().loops["buy-farmland"])
    quiet_before = loops.read(store.fold().loops)["buy-farmland"].silence(now=NOW)

    store.record(Op.TOUCH, "tc_1", NOW,
                 **touch_module.fields("buy-farmland", origin=ORIGIN))

    after = store.fold()
    assert after.loops["buy-farmland"] == before, "a raise moved the loop"
    quiet_after = loops.read(after.loops)["buy-farmland"].silence(now=NOW)
    assert quiet_after == quiet_before
    assert quiet_after.silent, "the wanting stopped looking silent because Half spoke"
    # And the other direction: the bound now refuses, while silence does not.
    assert not touchable(
        loops.read(after.loops)["buy-farmland"],
        touches=after.touches, now=NOW,
    ).may_touch


def test_moving_a_loop_does_not_record_a_raise(store):
    """The mirror. A wanting that moves has not been raised by anybody."""
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("swim-weekly", state="advancing",
                                timescale="weeks", last_movement="2026-07-28",
                                loops=store.state().loops))
    store.record(Op.LOOP_TRANSITION, "l_2", "2026-08-09T00:00Z",
                 **loops.move("swim-weekly", at="2026-08-09T06:30Z"))
    assert store.fold().touches == {}
    assert store.fold().last_touch is None


# ── the separation as a property of the two packages, not of anyone's care ──


def names_read_by(path: Path) -> set[str]:
    """Every identifier, attribute, argument and string literal in ``path``.

    **Lifted verbatim from ``tests/test_schedule.py``**, which lifted it from
    ``tests/test_crisis.py``, and deliberately not rewritten: three spellings
    rather than one, because ``getattr(record, "last_movement", None)`` walks
    past a scan that only looks at ``ast.Name``. A second copy would be a
    second, weaker copy.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            seen.add(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seen.update(arg.arg for arg in node.args.args)
            seen.update(arg.arg for arg in node.args.kwonlyargs)
    return {name.casefold() for name in seen}


#: Every spelling of *the loop moved*. The raise-writing module may name none
#: of them: a touch that carried a movement date would reset the very silence
#: it was raised about, and one that carried a state would demote a wanting on
#: the strength of Half having mentioned it.
MOVEMENT_NAMES = {"last_movement", "state", "timescale", "move", "rescale",
                  "abandon", "transition", "loop_transition"}

#: Every spelling of *Half raised it*. The movement-writing modules may name
#: none of them, so a helpful line recording a nudge beside a transition cannot
#: be written without importing something this scan sees.
#:
#: ``raised_at`` is deliberately absent: ``AbandonmentCandidate.raised_at``
#: already means *when this candidate was made*, which is a different sense of
#: the same word and predates this story. What the scan must catch is the
#: record — its op, its fields and the table it folds into — not an English
#: word two objects legitimately share.
RAISE_NAMES = {"touch", "touches", "last_touch", "origin_kind", "origin_id",
               "nagging"}


def test_the_module_that_writes_a_raise_cannot_write_a_movement():
    """Story 8's rule as a property of the file rather than of its docstring.

    The natural way this breaks is not malice. It is one line recording *"and
    the loop is stalled"* beside the raise, which is Half's own attention
    written into the main's progress — and it would then be permanent, because
    the log is append-only.
    """
    seen = names_read_by(ROOT / "half" / "surface" / "touch.py") & MOVEMENT_NAMES
    assert not seen, (
        f"half/surface/touch.py names {sorted(seen)}; a raise is not a "
        f"movement, and writing one as the other makes Half's own attention "
        f"look like the main's progress (story 8, CAP-6)"
    )


@pytest.mark.parametrize(
    "relative", ["half/loops/ledger.py", "half/loops/timescale.py",
                 "half/loops/states.py"]
)
def test_the_modules_that_write_a_movement_cannot_write_a_raise(relative):
    """The mirror, over the whole open-loop package."""
    seen = names_read_by(ROOT / relative) & RAISE_NAMES
    assert not seen, (
        f"{relative} names {sorted(seen)}; whether Half has raised a loop is a "
        f"different fact with a different record (story 8, CAP-8)"
    )


def test_the_separation_scan_catches_the_line_it_exists_for(tmp_path):
    """Non-vacuity, through the same helper the two gates use — the lesson
    ``tests/test_crisis.py`` records: a shared engine no test exercises is a
    gate resting on nothing."""
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        "def fields(loop_id, *, origin, moved):\n"
        "    return {'loop': loop_id, 'last_movement': moved,\n"
        "            'state': getattr(origin, 'state', None)}\n",
        encoding="utf-8",
    )
    seen = names_read_by(bypass)
    assert "last_movement" in seen, "the string-key spelling is unwatched"
    assert "state" in seen, "the getattr-string spelling is unwatched"
    assert seen & MOVEMENT_NAMES


def test_the_fold_never_writes_a_loop_from_a_touch():
    """The wall from the fold's side, asserted by AST.

    ``state.loops`` is unreachable from the ``touch`` case — there is no name
    for it in that branch — so a raise cannot open, move or demote a wanting
    however the record is shaped. That has to be structural rather than agreed,
    because the natural implementation of *"we raised it, so note that"* is to
    write into the entry that is already there.
    """
    tree = ast.parse((ROOT / "half" / "store" / "fold.py").read_text("utf-8"))
    branches = [
        case
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for case in node.cases
        if isinstance(case.pattern, ast.MatchValue)
        and isinstance(case.pattern.value, ast.Attribute)
        and case.pattern.value.attr == "TOUCH"
    ]
    assert branches, "no touch case in the fold; this scan is asserting nothing"
    named = {
        node.attr
        for case in branches
        for node in ast.walk(ast.Module(body=case.body, type_ignores=[]))
        if isinstance(node, ast.Attribute)
    }
    assert "loops" not in named, (
        "the fold's touch case reaches the loop table; a raise is not a move"
    )
    assert "touches" in named


# ═════════════════════════════════════════════════════════════════════════════
# the write gate: what a touch may and may not carry
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "extra",
    [
        {"claim": "you have not swum since May"},
        {"state": "stalled"},
        {"last_movement": "2026-09-01"},
        {"timescale": "weeks"},
        {"support": ["s_1"]},
        {"subject": "self"},
    ],
    ids=["claim", "state", "last-movement", "timescale", "support", "subject"],
)
def test_a_touch_may_not_carry_anything_but_the_loop_and_its_citation(
    store, extra
):
    """An **allowlist**, because every denylist this codebase has shipped was
    walked around. A claim here is belief content made permanent (AD-22); a
    state or a movement date is Half's attention recorded as progress."""
    with pytest.raises(TouchError):
        store.record(Op.TOUCH, "tc_1", NOW, loop="swim-weekly",
                     origin_kind=TOUCH_TENSION, origin_id="x_1", **extra)


@pytest.mark.parametrize(
    "fields",
    [
        {ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "x_1"},
        {LOOP: "", ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "x_1"},
        {LOOP: "swim-weekly", ORIGIN_ID: "x_1"},
        {LOOP: "swim-weekly", ORIGIN_KIND: "inferred", ORIGIN_ID: "x_1"},
        {LOOP: "swim-weekly", ORIGIN_KIND: TOUCH_TENSION},
        {LOOP: "swim-weekly", ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "  "},
    ],
    ids=["no-loop", "empty-loop", "no-kind", "kind-outside-the-set", "no-id",
         "blank-id"],
)
def test_the_append_gate_refuses_a_touch_that_cannot_be_read_back(store, fields):
    """Write strict, read tolerant. The log is append-only, so a raise that
    bounds nothing or cites nothing is refused *before* it is durable."""
    with pytest.raises(TouchError):
        store.record(Op.TOUCH, "tc_1", NOW, **fields)


def test_the_gate_and_the_composer_refuse_the_same_things():
    """``touch.fields`` refuses one layer up, where the caller can still be
    told which value it was — and the two must not disagree about what a
    traceable raise is, or the refusal a caller sees depends on which door they
    used."""
    with pytest.raises(TouchError):
        touch_module.fields("", origin=ORIGIN)
    with pytest.raises(TouchError):
        touch_module.fields("swim weekly", origin=ORIGIN)
    with pytest.raises(TouchError):
        touch_module.fields("swim-weekly", origin=Origin(kind="hunch", id="x"))
    with pytest.raises(TouchError):
        touch_module.fields("swim-weekly", origin=Origin(kind=TOUCH_TENSION, id=""))
    with pytest.raises(TouchError):
        touch_module.fields("swim-weekly", origin=None)


def test_the_composer_produces_exactly_the_allowed_fields():
    """Three keys, and the allowlist the gate enforces is the same set."""
    assert set(touch_module.fields("swim-weekly", origin=ORIGIN)) == {
        LOOP, ORIGIN_KIND, ORIGIN_ID
    }
    assert set(touch_module.fields("swim-weekly", origin=ORIGIN)) < TOUCH_FIELDS


def test_the_origin_vocabulary_is_closed():
    """The traceability rule is a closed set, not a convention. A fourth kind
    is a deliberate versioned change with a reviewer on it, because *"nothing
    is surfaced that cannot say where it came from"* is exactly the rule a
    helpful ``origin_kind="inferred"`` walks around."""
    assert TOUCH_ORIGINS == {"tension", "loop_transition", "ingested"}
    assert all(Origin(kind=kind, id="x_1").traceable for kind in TOUCH_ORIGINS)
    assert not Origin(kind="inferred", id="x_1").traceable
    assert not Origin(kind=TOUCH_TENSION, id="").traceable
    assert not touch_module.traceable(None, "x_1")
    assert not touch_module.traceable(TOUCH_TENSION, None)


def test_the_registry_refuses_a_touch_carrying_anything_else(tmp_path):
    """Refused one layer earlier than the append gate, where the caller can
    still be told which field it was — the shape ``note_transition`` uses."""
    registry = ActorRegistry(tmp_path)
    try:
        with pytest.raises(TouchError):
            asyncio.run(registry.note_touch(
                "vidit", t=NOW,
                fields={LOOP: "swim-weekly", ORIGIN_KIND: TOUCH_TENSION,
                        ORIGIN_ID: "x_1", "last_movement": "2026-09-01"},
            ))
    finally:
        registry.close()


def test_the_touch_record_id_carries_no_loop_slug(tmp_path):
    """``BeliefLog.expunge_bodies`` keeps a tombstoned record's id, so a slug in
    the id would survive the erasure that exists to remove it — the mistake the
    loop transitions' own ids (``l_1``) avoid."""
    registry = ActorRegistry(tmp_path)
    try:
        asyncio.run(registry.note_touch(
            "vidit", t=NOW,
            fields=touch_module.fields("sell-the-flat", origin=ORIGIN),
        ))
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        ids = [r.id for r in store.log if r.op is Op.TOUCH]
    assert ids == [f"tc_{NOW}"]
    assert not any("sell-the-flat" in ident for ident in ids)
