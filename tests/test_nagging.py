"""CAP-10 story 10: a loop is never touched faster than its own timescale.

The bound, the record it reads, and the two walls around that record.

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test and passed as an argument, which is the point of
the design under test: the bound is arithmetic over a stamp out of the log and
an injected ``now``, so the same log and the same instant give the same answer
for ever (AD-30).

**Both sides of every boundary are asserted.** Review on story 8 found a
threshold that anything between roughly six and thirteen satisfied, which is a
band rather than a number. The bound here is one of the loop's *own* periods,
and both *"at exactly one period"* and *"one second past it"* are pinned at
every timescale.

**The two walls.** A raise is not a *movement* — story 8's rule, asserted by
AST in both directions. And a raise is not a *spent day* — story 10's review
rule: the one-a-day rule used to read *the last raise of any loop*, so CAP-10's
interrupt would have silently eaten the morning budget the day it landed. A
raise now carries a loop and no day; a day marker carries a day; a record may
carry both. Every case below that says *"spends no day"* exists because of that
report.
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
from half.store.records import (
    LOCAL_DAY,
    LOOP,
    ORIGIN_ID,
    ORIGIN_KIND,
    SENT,
    TOUCH_FIELDS,
)
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
from half.surface.view import CLAIMED

pytestmark = [pytest.mark.cap8, pytest.mark.cap8_nagging]

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the instant ``tests/test_pass.py``,
#: ``tests/test_schedule.py`` and ``tests/test_surface.py`` all build from.
NOON = 1_788_264_000.0
NOW = stamp(NOON)
TODAY = "2026-09-01"

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


def raised(slug, *, ago_days=None, at=None, extra=None):
    """A touch table with ``slug`` raised ``ago_days`` before noon."""
    when = at if at is not None else stamp(NOON - (ago_days or 0) * DAY)
    record = {"t": when, LOOP: slug, ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "x_1"}
    record.update(extra or {})
    return {slug: record}


# ═════════════════════════════════════════════════════════════════════════════
# matrix: nagging, years-loop / nagging, days-loop
#
# The two rows are the same scenario with one field changed, which is the whole
# claim: the bound is derived from the loop's *own* period and nothing else.
# ═════════════════════════════════════════════════════════════════════════════


def test_a_years_loop_raised_last_month_is_not_raised_again():
    """Matrix: *nagging, years-loop*."""
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
    assert bound.may_touch and bound.reason is None
    assert bound.period_days == 1


def test_one_interval_answers_differently_for_every_timescale():
    """The bound is *per loop*, and this is the sweep that says so.

    gbrain's ``nudge.ts`` — the reference this is lifted from — carries one
    ``NUDGE_COOLDOWN_DAYS = 14``. At fourteen days that single number would nag
    the days-loop and the weeks-loop and would still be a year short of the
    years-loop; here one interval gives four different answers, each the loop's
    own.
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
    not slower than it. The same boundary ``timescale.silence`` uses for the
    mirror question, read the same way round."""
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
    bound = touchable(a_loop(), touches={}, now=NOW)
    assert bound.may_touch and bound.reason is None and bound.since_days is None


# ═════════════════════════════════════════════════════════════════════════════
# every way the bound cannot be computed
# ═════════════════════════════════════════════════════════════════════════════


def test_a_loop_with_no_timescale_is_not_raised_at_all():
    """A wanting with no period has no clock of its own to be held to.

    Note this holds *even though Half has never raised it*. It is also the case
    that separates a loop with no period from a candidate with **no loop**:
    the second touches no wanting, so there is nothing to pace and the day
    marker paces it instead — see ``tests/test_surface.py``.
    """
    bound = touchable(a_loop(timescale=None), touches={}, now=NOW)
    assert not bound.may_touch and bound.reason == NO_TIMESCALE
    assert bound.period_days is None, "a period was borrowed from somewhere"


def test_a_timescale_this_build_cannot_read_is_not_raised():
    bound = touchable(
        Loop(id="x", state=str(LoopState.ADVANCING), timescale="fortnights",
             last_movement="2026-07-01"),
        touches={}, now=NOW,
    )
    assert not bound.may_touch and bound.reason == UNKNOWN_TIMESCALE


def test_an_unreadable_now_is_reported_as_the_callers_own_fault():
    """Reported separately from an unreadable raise, because the fix differs:
    the log is fine and the caller is not."""
    bound = touchable(a_loop(), touches=raised("swim-weekly", ago_days=1),
                      now="not-an-instant")
    assert not bound.may_touch and bound.reason == UNREADABLE_NOW


def test_a_raise_dated_in_the_future_does_not_buy_an_immediate_re_raise():
    bound = touchable(
        a_loop(), touches=raised("swim-weekly", at=stamp(NOON + 400 * DAY)),
        now=NOW,
    )
    assert not bound.may_touch and bound.reason == NAGGING
    assert bound.since_days == 0.0


def test_an_unreadable_stamp_falls_back_to_the_stored_day():
    """Two independently validated sources, and the second is a real recovery.

    A raise whose ``t`` cannot be read still carries the day it belonged to if
    it was also a day marker, and that day — widened to its start — is a
    conservative measure of when the raise happened.
    """
    table = {
        "swim-weekly": {
            "t": "yesterday", LOOP: "swim-weekly", LOCAL_DAY: "2026-08-30",
            SENT: True, ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "x_1",
        }
    }
    bound = touchable(a_loop(), touches=table, now=NOW)
    assert not bound.may_touch and bound.reason == NAGGING
    assert bound.since_days == pytest.approx(2.5)


def test_a_raise_with_no_readable_time_at_all_is_treated_as_no_raise():
    """The correction review forced, and the reasoning it replaces.

    The first version refused here, on the ground that refusing is the safe
    direction. That weighed one nag against one quiet day; it did not weigh one
    nag against **permanent** silence on a wanting — which is what it bought,
    because the entry is replaced only by a later raise on that loop, a later
    raise happens only when the loop is chosen, and the refusal is exactly what
    stopped it being chosen. There was no recovery, no alert and no counter.

    So an unmeasurable raise is treated as no raise, ``degraded`` says so, and
    the surface logs and counts it (``tests/test_surface.py``). The cost is at
    most one extra raise on one loop; after it a readable record exists.
    """
    bound = touchable(
        a_loop(), touches={"swim-weekly": {"t": "yesterday"}}, now=NOW
    )
    assert bound.may_touch
    assert bound.degraded and bound.reason == UNREADABLE_TOUCH


def test_a_raise_with_no_time_field_at_all_is_treated_as_no_raise():
    bound = touchable(a_loop(), touches={"swim-weekly": {}}, now=NOW)
    assert bound.may_touch and bound.degraded


@pytest.mark.parametrize(
    "state", [LoopState.ACHIEVED, LoopState.ABANDONED_BUT_UNADMITTED]
)
def test_a_finished_or_answered_wanting_is_not_raised(state):
    """``ledger.silent``'s filter, asked here for the same reason."""
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
    # The one case that answers yes while carrying a reason is the degraded
    # one, and it says so.
    assert all(
        case.degraded for case in cases if case.may_touch and case.reason
    )


def test_the_same_loop_and_the_same_now_answer_identically_twice():
    args = dict(touches=raised("swim-weekly", ago_days=3), now=NOW)
    assert touchable(a_loop(), **args) == touchable(a_loop(), **args)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: touch recorded — and the day marker kept apart from the raise
# ═════════════════════════════════════════════════════════════════════════════


def test_a_raise_records_the_loop_and_what_it_cited(store):
    """Matrix: *touch recorded*."""
    store.record(Op.TOUCH, "tc_1", NOW, **touch_module.raised("swim-weekly",
                                                              origin=ORIGIN))
    held = store.fold().touches["swim-weekly"]
    assert held[LOOP] == "swim-weekly"
    assert held[ORIGIN_KIND] == TOUCH_TENSION and held[ORIGIN_ID] == "x_1"
    assert held["t"] == NOW
    assert touch_module.raised_at(held) == NOW
    assert touch_module.origin_of(held) == ORIGIN


def test_a_raise_spends_no_day(store):
    """**Mark which touches count.** The rule that CAP-10's interrupt needs.

    Before review the one-a-day rule read *the last raise of any loop*, so the
    day the interrupt shipped it would have started consuming mornings with no
    change anywhere near the surface. A raise carries no ``local_day``, so it
    bounds the loop and leaves the day alone.
    """
    store.record(Op.TOUCH, "tc_1", NOW, **touch_module.raised("swim-weekly",
                                                              origin=ORIGIN))
    state = store.fold()
    assert "swim-weekly" in state.touches
    assert state.spoke is None, "a raise consumed the main's morning"
    assert touch_module.raises_loop(state.touches["swim-weekly"])
    assert not touch_module.marks_day(state.touches["swim-weekly"])


def test_a_day_marker_with_no_loop_leaves_every_bound_alone(store):
    """The mirror: a message that touched no wanting bounds no wanting."""
    store.record(Op.TOUCH, "tc_1", NOW,
                 **touch_module.spoke(day=TODAY, origin=ORIGIN))
    state = store.fold()
    assert state.touches == {}
    assert touch_module.day_of(state.spoke) == TODAY
    assert state.spoke[SENT] is True


def test_a_repair_marker_spends_the_day_and_says_nothing_was_sent(store):
    """The one path that consumes a day deliberately without speaking.

    It exists so an unreadable marker costs one morning instead of every
    morning after it, and it is honest about what happened: ``sent`` is false,
    and it cites nothing because it surfaced nothing.
    """
    store.record(Op.TOUCH, "tc_1", NOW, **touch_module.repaired(day=TODAY))
    state = store.fold()
    assert touch_module.day_of(state.spoke) == TODAY
    assert state.spoke[SENT] is False
    assert ORIGIN_KIND not in state.spoke and LOOP not in state.spoke
    assert state.touches == {}


def test_one_record_can_do_both_jobs(store):
    """The ordinary morning: a message that spent the day and raised a loop."""
    store.record(Op.TOUCH, "tc_1", NOW, **touch_module.spoke(
        day=TODAY, origin=ORIGIN, loops=("swim-weekly",)))
    state = store.fold()
    assert state.touches["swim-weekly"] is state.spoke
    assert touch_module.raises_loop(state.spoke)
    assert touch_module.marks_day(state.spoke)


def test_a_touch_folds_and_replays(store):
    store.record(Op.TOUCH, "tc_1", NOW, **touch_module.spoke(
        day=TODAY, origin=ORIGIN, loops=("swim-weekly",)))
    assert store.fold().canonical_json() == store.state().canonical_json()


def test_the_day_marker_is_the_newest_one_the_fold_reads(store):
    """A later *raise* does not become the day marker, and a later marker does.

    The pair that would catch the rule sliding back to *"the last touch of
    anything"*.
    """
    store.record(Op.TOUCH, "tc_1", NOW, **touch_module.spoke(
        day=TODAY, origin=ORIGIN, loops=("swim-weekly",)))
    store.record(Op.TOUCH, "tc_2", stamp(NOON + 60),
                 **touch_module.raised("buy-farmland", origin=ORIGIN))
    assert touch_module.day_of(store.fold().spoke) == TODAY

    store.record(Op.TOUCH, "tc_3", stamp(NOON + 120),
                 **touch_module.repaired(day="2026-09-02"))
    assert touch_module.day_of(store.fold().spoke) == "2026-09-02"


def test_a_second_raise_on_one_loop_supersedes_the_first(store):
    store.record(Op.TOUCH, "tc_1", stamp(NOON - 40 * DAY),
                 **touch_module.raised("swim-weekly", origin=ORIGIN))
    store.record(Op.TOUCH, "tc_2", NOW,
                 **touch_module.raised("swim-weekly", origin=ORIGIN))
    touches = store.fold().touches
    assert list(touches) == ["swim-weekly"] and touches["swim-weekly"]["t"] == NOW


def test_a_touch_is_an_append_and_never_an_edit(store):
    """AD-3. Two raises are two lines; nothing is rewritten in place."""
    store.record(Op.TOUCH, "tc_1", stamp(NOON - 40 * DAY),
                 **touch_module.raised("swim-weekly", origin=ORIGIN))
    store.record(Op.TOUCH, "tc_2", NOW,
                 **touch_module.raised("swim-weekly", origin=ORIGIN))
    assert len([r for r in store.log if r.op is Op.TOUCH]) == 2


# ═════════════════════════════════════════════════════════════════════════════
# an erasure erases the raises too
# ═════════════════════════════════════════════════════════════════════════════


def test_erasing_a_loop_erases_every_raise_on_it_and_leaves_no_slug(store):
    """Through the public path, which tombstones the bodies as well."""
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", last_movement="2026-01-04",
                                loops=store.state().loops))
    store.record(Op.TOUCH, "tc_2026-08-02T03:00Z", "2026-08-02T03:00Z",
                 **touch_module.raised("sell-the-flat", origin=ORIGIN))
    store.expunge("sell-the-flat", t="2026-08-03T00:00Z")

    state = store.fold()
    assert state.touches == {} and state.spoke is None
    assert "sell-the-flat" in state.expunged_loops
    bodies = [r.data for r in store.log if r.op is Op.TOUCH]
    assert bodies == [{"id": "tc_2026-08-02T03:00Z", "op": "touch",
                       "t": "2026-08-02T03:00Z", "tombstone": True, "v": 7}]


def test_the_bare_expunge_op_also_erases_the_raises(store):
    """The fold's **own** branch, which had no test.

    Every existing case went through ``Store.expunge``, which also tombstones
    the bodies — so the fold's expunge branch was never asked the question on
    its own, and it kept the erased slug in ``touches`` and wrote it straight
    back into the derived table on the next rebuild.
    """
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", loops=store.state().loops))
    store.record(Op.TOUCH, "tc_1", "2026-08-02T03:00Z", **touch_module.spoke(
        day="2026-08-02", origin=ORIGIN, loops=("sell-the-flat",)))
    assert "sell-the-flat" in store.fold().touches

    store.record(Op.EXPUNGE, "x_1", "2026-08-03T00:00Z",
                 **loops.expunged("sell-the-flat"))

    state = store.fold()
    assert state.touches == {}, "the erased loop kept its raise"
    assert state.spoke is None, "a day marker kept the erased slug"
    assert state.canonical_json() == store.state().canonical_json()
    # The slug survives in ``expunged_loops``, which is what remembers the
    # erasure; what must not survive is the raise or the day marker naming it.
    assert "sell-the-flat" not in str(state.touches)
    assert "sell-the-flat" not in str(state.spoke)


def test_a_tombstoned_touch_does_not_poison_the_belief_namespace(store):
    """A touch's record id is the *append's*, not the loop's — so putting it in
    ``expunged`` would suppress whatever belief happened to share it."""
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", loops=store.state().loops))
    store.record(Op.TOUCH, "tc_x", "2026-08-02T03:00Z",
                 **touch_module.raised("sell-the-flat", origin=ORIGIN))
    store.expunge("sell-the-flat", t="2026-08-03T00:00Z")
    assert "tc_x" not in store.fold().expunged

    store.record(Op.ASSERT, "tc_x", "2026-08-04T00:00Z", claim="unrelated")
    assert store.fold().beliefs["tc_x"]["claim"] == "unrelated"


def test_a_raise_written_after_a_loop_was_erased_does_not_come_back(store):
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", loops=store.state().loops))
    store.expunge("sell-the-flat", t="2026-08-02T00:00Z")
    store.record(Op.TOUCH, "tc_1", "2026-08-03T00:00Z",
                 **touch_module.raised("sell-the-flat", origin=ORIGIN))
    state = store.fold()
    assert state.touches == {} and state.spoke is None


# ═════════════════════════════════════════════════════════════════════════════
# matrix: untouched vs unmoved — the two facts stay separate
# ═════════════════════════════════════════════════════════════════════════════


def test_raising_a_loop_does_not_move_it(store):
    """Matrix: *untouched vs unmoved*. Half's attention is not the main's
    progress."""
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("buy-farmland", state="stalled",
                                timescale="years", last_movement="2020-03-12",
                                loops=store.state().loops))
    before = dict(store.fold().loops["buy-farmland"])
    quiet_before = loops.read(store.fold().loops)["buy-farmland"].silence(now=NOW)

    store.record(Op.TOUCH, "tc_1", NOW,
                 **touch_module.raised("buy-farmland", origin=ORIGIN))

    after = store.fold()
    assert after.loops["buy-farmland"] == before, "a raise moved the loop"
    quiet_after = loops.read(after.loops)["buy-farmland"].silence(now=NOW)
    assert quiet_after == quiet_before and quiet_after.silent
    assert not touchable(
        loops.read(after.loops)["buy-farmland"],
        touches=after.touches, now=NOW,
    ).may_touch


def test_moving_a_loop_does_not_record_a_raise(store):
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                 **loops.opened("swim-weekly", state="advancing",
                                timescale="weeks", last_movement="2026-07-28",
                                loops=store.state().loops))
    store.record(Op.LOOP_TRANSITION, "l_2", "2026-08-09T00:00Z",
                 **loops.move("swim-weekly", at="2026-08-09T06:30Z"))
    assert store.fold().touches == {} and store.fold().spoke is None


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
        # Listing ``tombstone`` in the allowlist let a caller write a live
        # touch the fold skips — durable, and invisible to both the daily rule
        # and the bound. ``expunge_bodies`` builds its stub and appends the
        # line itself, so it never needed the allowance.
        {"tombstone": True},
    ],
    ids=["claim", "state", "last-movement", "timescale", "support", "subject",
         "tombstone"],
)
def test_a_touch_may_not_carry_anything_but_its_own_fields(store, extra):
    with pytest.raises(TouchError):
        store.record(Op.TOUCH, "tc_1", NOW, loop="swim-weekly",
                     origin_kind=TOUCH_TENSION, origin_id="x_1", **extra)


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "x_1"},
        {LOOP: "", ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "x_1"},
        {LOOP: "swim-weekly", ORIGIN_ID: "x_1"},
        {LOOP: "swim-weekly", ORIGIN_KIND: "inferred", ORIGIN_ID: "x_1"},
        {LOOP: "swim-weekly", ORIGIN_KIND: TOUCH_TENSION},
        {LOOP: "swim-weekly", ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "  "},
        {LOCAL_DAY: "yesterday", SENT: False},
        {LOCAL_DAY: "2026-02-31", SENT: False},
        {LOCAL_DAY: TODAY},
        {SENT: True, ORIGIN_KIND: TOUCH_TENSION, ORIGIN_ID: "x_1"},
        {LOCAL_DAY: TODAY, SENT: True},
    ],
    ids=["empty", "no-loop-no-day", "empty-loop", "no-kind",
         "kind-outside-the-set", "no-id", "blank-id", "day-not-a-day",
         "day-not-a-calendar-day", "day-without-sent", "sent-without-day",
         "sent-without-an-origin"],
)
def test_the_append_gate_refuses_a_touch_that_cannot_be_read_back(store, fields):
    """Write strict, read tolerant. The log is append-only, so a raise that
    bounds nothing, a day nothing can read, or a message that cites nothing is
    refused *before* it is durable."""
    with pytest.raises(TouchError):
        store.record(Op.TOUCH, "tc_1", NOW, **fields)


def test_the_gate_and_the_composers_refuse_the_same_things():
    with pytest.raises(TouchError):
        touch_module.raised("", origin=ORIGIN)
    with pytest.raises(TouchError):
        touch_module.raised("swim weekly", origin=ORIGIN)
    with pytest.raises(TouchError):
        touch_module.raised("swim-weekly", origin=Origin(kind="hunch", id="x"))
    with pytest.raises(TouchError):
        touch_module.raised("swim-weekly", origin=Origin(kind=TOUCH_TENSION, id=""))
    with pytest.raises(TouchError):
        touch_module.raised("swim-weekly", origin=None)
    with pytest.raises(TouchError):
        touch_module.spoke(day="yesterday", origin=ORIGIN)
    with pytest.raises(TouchError):
        touch_module.spoke(day="2026-02-31", origin=ORIGIN)
    with pytest.raises(TouchError):
        touch_module.repaired(day=None)


def test_the_composers_produce_exactly_the_allowed_fields():
    assert set(touch_module.raised("swim-weekly", origin=ORIGIN)) == {
        LOOP, ORIGIN_KIND, ORIGIN_ID
    }
    assert set(touch_module.spoke(day=TODAY, origin=ORIGIN)) == {
        LOCAL_DAY, SENT, ORIGIN_KIND, ORIGIN_ID
    }
    assert set(touch_module.spoke(
        day=TODAY, origin=ORIGIN, loops=("a", "b"))) == {
        LOOP, LOCAL_DAY, SENT, ORIGIN_KIND, ORIGIN_ID
    }
    assert set(touch_module.repaired(day=TODAY)) == {LOCAL_DAY, SENT}
    for composed in (
        touch_module.raised("swim-weekly", origin=ORIGIN),
        touch_module.spoke(day=TODAY, origin=ORIGIN, loops=("a",)),
        touch_module.repaired(day=TODAY),
    ):
        assert set(composed) <= TOUCH_FIELDS
    assert "tombstone" not in TOUCH_FIELDS


def test_the_origin_vocabulary_is_closed():
    assert TOUCH_ORIGINS == {"tension", "loop_transition", "ingested"}
    assert all(Origin(kind=kind, id="x_1").traceable for kind in TOUCH_ORIGINS)
    assert not Origin(kind="inferred", id="x_1").traceable
    assert not Origin(kind=TOUCH_TENSION, id="").traceable
    assert not touch_module.traceable(None, "x_1")
    assert not touch_module.traceable(TOUCH_TENSION, None)


# ═════════════════════════════════════════════════════════════════════════════
# the claim: serialized, validated, and the record id carries no slug
# ═════════════════════════════════════════════════════════════════════════════


def test_the_claim_refuses_a_stamp_that_is_not_an_instant(tmp_path):
    """The write side of *"a raise has a readable time"*.

    ``records.make`` checks a stamp's shape and not its calendar, so
    ``2026-02-31T00:00Z`` would otherwise become durable and the bound would
    then have to fall back or degrade. Both of a raise's time sources are
    validated at the append; producing an unreadable one takes a hand edit.
    """
    registry = ActorRegistry(tmp_path)
    try:
        with pytest.raises(TouchError):
            asyncio.run(registry.claim_day(
                "vidit", t="2026-02-31T00:00Z", day=TODAY,
                records=[touch_module.repaired(day=TODAY)],
            ))
    finally:
        registry.close()


def test_the_claim_refuses_a_whole_batch_and_appends_none_of_it(tmp_path):
    """The stray-field check is at the registry **as well as** the append gate,
    and this is what makes it load-bearing rather than a second copy.

    A single malformed record would be refused either way. A *batch* would not:
    the append gate sees one record at a time, so a stray field on the second
    one leaves the first durable — spending the main's day with the loops half
    bound. Every record is checked before any is appended.
    """
    registry = ActorRegistry(tmp_path)
    try:
        with pytest.raises(TouchError):
            asyncio.run(registry.claim_day(
                "vidit", t=NOW, day=TODAY,
                records=[
                    touch_module.spoke(day=TODAY, origin=ORIGIN,
                                       loops=("a-loop",)),
                    {LOOP: "b-loop", ORIGIN_KIND: TOUCH_TENSION,
                     ORIGIN_ID: "x_1", "last_movement": "2026-09-01"},
                ],
            ))
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        state = store.fold()
        assert state.spoke is None, "the first record of a refused batch landed"
        assert state.touches == {}


def test_the_claim_appends_every_record_under_one_acquire(tmp_path):
    """A candidate touching three wantings bounds three wantings and spends one
    morning, and a crash cannot leave one without the other."""
    registry = ActorRegistry(tmp_path)
    try:
        outcome = asyncio.run(registry.claim_day(
            "vidit", t=NOW, day=TODAY,
            records=[
                touch_module.spoke(day=TODAY, origin=ORIGIN,
                                   loops=("a-loop", "b-loop")),
                touch_module.raised("b-loop", origin=ORIGIN),
            ],
        ))
        assert outcome == CLAIMED
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        state = store.fold()
        assert set(state.touches) == {"a-loop", "b-loop"}
        assert touch_module.day_of(state.spoke) == TODAY
        assert len([r for r in store.log if r.op is Op.TOUCH]) == 2


def test_the_touch_record_id_carries_no_loop_slug(tmp_path):
    """``BeliefLog.expunge_bodies`` keeps a tombstoned record's id, so a slug in
    the id would survive the erasure that exists to remove it."""
    registry = ActorRegistry(tmp_path)
    try:
        asyncio.run(registry.claim_day(
            "vidit", t=NOW, day=TODAY,
            records=[touch_module.spoke(day=TODAY, origin=ORIGIN,
                                        loops=("sell-the-flat",))],
        ))
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        ids = [r.id for r in store.log if r.op is Op.TOUCH]
    assert ids == [f"tc_{NOW}"]
    assert not any("sell-the-flat" in ident for ident in ids)


# ═════════════════════════════════════════════════════════════════════════════
# the wall, as a property of the packages rather than of anyone's care
# ═════════════════════════════════════════════════════════════════════════════


def names_read_by(path: Path) -> set[str]:
    """Every identifier, attribute, argument and string literal in ``path``.

    **Lifted verbatim from ``tests/test_schedule.py``**, which lifted it from
    ``tests/test_crisis.py``, and deliberately not rewritten: three spellings
    rather than one, because ``getattr(record, "last_movement", None)`` walks
    past a scan that only looks at ``ast.Name``.
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
#: none of them.
#:
#: ``raised_at`` is deliberately absent: ``AbandonmentCandidate.raised_at``
#: already means *when this candidate was made*, which is a different sense of
#: the same word and predates this story.
RAISE_NAMES = {"touch", "touches", "spoke", "origin_kind", "origin_id",
               "local_day", "nagging"}


@pytest.mark.cap8_structure
def test_the_module_that_writes_a_raise_cannot_write_a_movement():
    """Story 8's rule as a property of the file rather than of its docstring.

    The natural way this breaks is one line recording *"and the loop is
    stalled"* beside the raise, which is Half's own attention written into the
    main's progress — permanently, because the log is append-only.
    """
    seen = names_read_by(ROOT / "half" / "surface" / "touch.py") & MOVEMENT_NAMES
    assert not seen, (
        f"half/surface/touch.py names {sorted(seen)}; a raise is not a "
        f"movement (story 8, CAP-6)"
    )


@pytest.mark.cap8_structure
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


@pytest.mark.cap8_structure
def test_the_separation_scan_catches_the_line_it_exists_for(tmp_path):
    """Non-vacuity, through the same helper the two gates use."""
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


@pytest.mark.cap8_structure
def test_the_fold_never_writes_a_loop_from_a_touch():
    """The wall from the fold's side, asserted by AST.

    ``state.loops`` is unreachable from the ``touch`` case — there is no name
    for it in that branch — so a raise cannot open, move or demote a wanting
    however the record is shaped.
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
    assert "touches" in named and "spoke" in named
