"""CAP-8 story 10: the morning surface — one case per matrix row.

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test, which is the design under test: the scheduler is
the one module allowed to know what time it is (AD-30). *At most one a day* is
a rule about days, so a suite that used the real clock would be irreproducible.

**Silence is asserted as the ordinary outcome, not as an error path.** Most of
the cases below end in nothing being sent, and each asserts that nothing was
logged as a failure, nothing was queued and nothing was retried. Exactly three
reasons are faults and are logged as such; the rest are ordinary.

**The gates are exercised in every ordering.** Story 9c's central rule was
broken in two orderings nobody had tested while its suite was green, and the
same trap is open here: independent gates, each of which alone produces
silence, and a suite that only ever presents one at a time cannot tell whether
the second is doing anything.

**The ceiling is asserted as a property and as a *shape*.** Review wrote ``if
state.aftercare is not None: return Silence(...)`` inside the surface and
passed 3182 tests: no new import, no new door, and a mutant that permanently
silences a main whose aftercare has finished. So what is tested is the sweep
over every rung, *plus* that the surface is handed a projection with no
aftercare field in it at all — and, behaviourally, that a main **with** an
aftercare record and a permissive ceiling still gets their morning message.

**The production path is exercised without a fixture writing the link.** The
first version required a candidate to name a loop, and nothing in the product
writes a ``loop`` onto a belief — so every morning was silent for every main
for ever, with the suite green because ``seed_entry`` hand-wrote the
association. ``test_a_belief_the_product_itself_wrote_can_become_a_candidate``
drives the real ``Runtime`` and asserts a candidate comes out of it.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.port import Reachability, SendResult
from half.channel.telegram import TelegramChannel
from half.civil import DAY
from half.consolidate.pass_ import PassResult, TensionPass
from half.context.build import build as build_context
from half.governance import ladder
from half.governance.ladder import RUNGS, Ceiling, License, height, permitted
from half.loops import ledger as loops
from half.retrieval.port import Candidate as RankedBelief
from half.schedule.clock import FrozenClock, moment, stamp
from half.schedule.due import local_day, told
from half.store.fold import State
from half.store.ops import (
    TOUCH_INGESTED,
    TOUCH_LOOP_TRANSITION,
    TOUCH_TENSION,
    Op,
)
from half.store.records import NEXT_PASS_AT, SENT, TOLD_ZONE, ZONE
from half.store.records import make as make_record
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.choose import Candidate, choose, eligible, live_origin
from half.surface.morning import (
    ALREADY_TODAY,
    CRISIS,
    FAULTS,
    NOTHING_MAY_BE_SAID,
    NOTHING_TO_SAY,
    REASONS,
    SPEAKS_AT,
    SPOKEN_CHANNELS,
    UNREADABLE_MARKER,
    UNRECORDED,
    UNSENT,
    MorningPass,
    Mornings,
    MorningSurface,
    Silence,
    SurfaceLedger,
    Surfaced,
    speech,
)
from half.surface.touch import Origin
from half.surface.view import VISIBLE, SurfaceView, narrowed, view_fields
from half.tensions.states import STATE, TensionState

from tests.conftest import FakeTransport, msg, seed_belief

pytestmark = pytest.mark.cap8

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the instant every other file in this suite builds
#: from, so the scenarios line up.
NOON = 1_788_264_000.0
NOW = moment(NOON)
TODAY = "2026-09-01"

SEEDED = "2026-08-09T00:00:00Z"
MINTED = "2026-08-10T00:00:00Z"
MOVED = "2026-08-11T00:00:00Z"

TENSION_ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")

#: One claim per seeded entry, sharing **no adjacent word pair** with any
#: other and containing no belief id. Both properties are load-bearing: AD-18's
#: withholding guard works on adjacent pairs, so two claims reading *"claim
#: about b_1"* and *"claim about b_2"* share ``claimabout`` and the `assert`
#: entry is correctly dropped — leaving every case below quietly testing an
#: empty context instead of the rule it names. A dictionary rather than a
#: formula, so adding an entry fails by name instead of colliding by
#: arithmetic.
CLAIMS = {
    "b_1": "alpha alphawards",
    "b_2": "bravo bravowards",
    "b_3": "charlie charliewards",
    "b_4": "delta deltawards",
    "b_5": "echo echowards",
    "b_6": "foxtrot foxtrotwards",
    "b_7": "golf golfwards",
    "b_8": "hotel hotelwards",
}


def a_claim(ident):
    assert ident in CLAIMS, f"add a claim for {ident}; see CLAIMS"
    return CLAIMS[ident]


# ── helpers ──────────────────────────────────────────────────────────────────


class FakeChannel:
    """The whole ``Channel`` surface the morning needs, so tests stay offline.

    ``capability_query`` is the port's own question and the only thing this
    module may learn about a platform (AD-7).
    """

    name = "fake"

    def __init__(self, reach=Reachability.OPEN, fail=None, parts=1):
        self.reach = reach
        self.fail = fail
        self.parts = parts
        self.sent: list[tuple[str, str]] = []
        self.queries: list[str] = []

    def capability_query(self, main_id):
        self.queries.append(main_id)
        return self.reach

    async def send(self, main_id, text):
        if self.fail is not None:
            raise self.fail
        self.sent.append((main_id, text))
        return SendResult(external_id="mid-1", parts=self.parts)

    def draft_link(self, text, *, to=None):  # pragma: no cover - never used
        raise AssertionError("the morning surface never drafts to a third party")

    async def receive(self):  # pragma: no cover - never used
        raise AssertionError("the morning surface never receives")


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def seed_loop(store, slug="swim-weekly", *, timescale="weeks",
              state="advancing", last_movement="2026-07-01", ident="l_1"):
    store.record(
        Op.LOOP_TRANSITION, ident, "2026-08-01T00:00:00Z",
        **loops.opened(slug, state=state, timescale=timescale,
                       last_movement=last_movement, loops=store.state().loops),
    )


def seed_entry(store, ident, *, loop="swim-weekly", rung=License.ASSERT,
               claim=None, t=SEEDED, support=None):
    """One belief, admitted through the ladder like production does.

    ``loop`` is the association the **product does not write** — see the module
    docstring. Every case that hands it one is testing the loop-bounded path on
    purpose; the production path is exercised without it.
    """
    fields = {"subject": "self", "topics": ["swimming"]}
    if loop is not None:
        fields["loop"] = loop
    return seed_belief(
        store, ident, t, claim=claim if claim is not None else a_claim(ident),
        rung=rung, support=support or [f"s_{ident}"], **fields,
    )


def seed_tension(store, *, ident="x_1", pair=("b_1", "b_2"), moves=None,
                 loop="swim-weekly", rungs=(License.ASSERT, License.BEHAVE)):
    """Two entries, a tension over them, evidence added to ``moves``.

    ``moves`` defaults to this tension's **own** first side rather than to a
    literal: a fixture seeding two tensions with a hard-coded ``("b_1",)``
    re-states ``b_1`` under the second tension's loop, quietly moving that
    entry to a wanting it was never on.
    """
    moves = (pair[0],) if moves is None else moves
    held = dict(zip(pair, rungs))
    for side, rung in held.items():
        seed_entry(store, side, loop=loop, rung=rung)
    store.record(Op.TENSION, ident, MINTED, between=list(pair),
                 **{STATE: str(TensionState.FRESH)}, **ladder.admitted())
    for side in moves:
        fields = {"subject": "self", "topics": ["swimming"]}
        if loop is not None:
            fields["loop"] = loop
        seed_belief(store, side, MOVED, claim=a_claim(side),
                    rung=held.get(side, License.BEHAVE),
                    support=[f"s_{side}", f"s_more_{side}"], **fields)


def a_main(root, main_id="vidit", **kwargs):
    """A main with one loop and one tension over two entries on it."""
    with Store(Path(root) / main_id) as store:
        if kwargs.get("loop", "swim-weekly") is not None:
            seed_loop(store)
        seed_tension(store, **kwargs)


def run_pass(registry, main_id="vidit", now=NOW):
    return asyncio.run(TensionPass(ledger=registry).evaluate(main_id, now))


def surface(registry, channel, *, main_id="vidit", now=NOW, candidates=None,
            mornings=None):
    if candidates is None:
        candidates = run_pass(registry, main_id, now).candidates
    made = MorningSurface(
        ledger=registry, channel=channel, mornings=mornings or Mornings()
    )
    return asyncio.run(made.surface(main_id, now=now, candidates=candidates))


def view_of(registry, main_id="vidit"):
    return asyncio.run(registry.surface_view(main_id))


def set_ceiling(registry, main_id, rung, *, t="2026-08-20T00:00:00Z"):
    asyncio.run(registry.hold_ceiling(
        main_id, to=rung, t=t, because="a test standing in for aftercare"
    ))


def tell_zone(registry, main_id, zone):
    """Record the zone the main told Half, through the ladder like production."""
    with Store(registry.root / main_id) as store:
        store.record(Op.ASSERT, "b_zone", "2026-08-01T00:00:00Z",
                     **told(zone, support=["s_zone"]))
        record = store.state().beliefs["b_zone"]
        store.record(Op.ASSERT, "b_zone", "2026-08-01T00:00:00Z",
                     **ladder.promote(record, to=License.ASSERT,
                                      acknowledged=True))


def enter_crisis(registry, main_id):
    asyncio.run(registry.suspend_for_crisis(
        main_id, t="2026-08-31T00:00:00Z", tier="disclosure", score=2
    ))


def mark_day(registry, main_id, *, day, t=None, loops_=()):
    """Write a day marker directly, as an earlier morning would have."""
    asyncio.run(registry.claim_day(
        main_id, t=t or stamp(NOON - 3600), day=day,
        records=[touch_module.spoke(day=day, origin=TENSION_ORIGIN,
                                    loops=loops_)],
    ))


# ═════════════════════════════════════════════════════════════════════════════
# matrix: reachable in production — the headline
# ═════════════════════════════════════════════════════════════════════════════


def test_a_belief_the_product_itself_wrote_can_become_a_candidate(tmp_path):
    """Matrix: *reachable in production*. Not fixture-only.

    The first version of this story required a candidate to name a loop, and
    nothing anywhere in ``half/`` writes a ``loop`` field onto a belief —
    ``Runtime._pipeline`` does not, and ingestion writes no beliefs at all. Two
    separately defensible decisions composed into a feature that could not fire
    for any main, ever, with 3182 tests agreeing it worked, because every
    fixture hand-wrote the association the product never makes.

    So this case writes **nothing** by hand. The real ``Runtime`` records two
    beliefs from two real inbound messages, exactly as the product does; a
    tension is minted over them through the store, which is the one step story
    9d owns and this story reads; the real pass runs; and a candidate has to
    come out of it and survive the chooser.

    What it deliberately does **not** assert is that a message is sent: a
    belief the product writes is admitted at `behave` (``ladder.admitted``) and
    nothing in this build promotes it, so the ladder correctly refuses to speak
    it. That gap is story 11's question engine, and it is a *governance* gate
    rather than a structural one — the matrix row asks that such a belief *can
    become a candidate*, and that is what is asserted here.
    """
    registry = ActorRegistry(tmp_path)
    transport = FakeTransport(updates=[
        msg(chat_id="123", text="I keep meaning to start swimming again",
            message_id="1", date=NOON - 40 * DAY),
        msg(chat_id="123", text="did not go to the pool this month",
            message_id="2", date=NOON - 39 * DAY),
    ])
    channel = TelegramChannel(transport=transport, mains={"123": "vidit"})
    try:
        asyncio.run(Runtime(channel=channel, registry=registry).run())

        with Store(tmp_path / "vidit") as store:
            written = store.state().beliefs
            assert set(written) == {"b_1", "b_2"}, "the runtime wrote nothing"
            # The point of the whole case: the product writes no loop.
            assert all("loop" not in record for record in written.values())
            # Story 9d mints; this story reads. Seeded here, and nothing else
            # in this fixture is hand-written.
            #
            # The transition the pass computes is `fresh` -> `persistent`,
            # which is the only one reachable from what the product writes: a
            # widening needs one side to *accumulate* support, and the
            # conversational path admits every belief with none
            # (``ladder.admitted``) and never adds any. Ingestion is where
            # support comes from, and it writes no beliefs yet — a second
            # production gap this case documents rather than hides.
            store.record(Op.TENSION, "x_1", stamp(NOON - 30 * DAY),
                         between=["b_1", "b_2"],
                         **{STATE: str(TensionState.FRESH)},
                         **ladder.admitted())

        result = run_pass(registry)
        assert result.moved == {"x_1": str(TensionState.PERSISTENT)}
        assert result.candidates, "the pass produced no candidate"
        candidate = result.candidates[0]
        assert set(candidate.entries) == {"b_1", "b_2"}

        view = view_of(registry)
        chosen = choose(result.candidates, view=view, now=NOW.stamp)
        assert chosen is not None, (
            "a belief the product itself wrote cannot become a candidate; the "
            "surface is structurally silent in production"
        )
        assert chosen.loops == (), "the product wrote a loop after all"
    finally:
        registry.close()


def test_a_candidate_that_names_no_loop_is_bounded_by_the_day_and_the_pass(
    registry, tmp_path
):
    """What holds a loopless candidate, now that the nagging bound cannot.

    Two rules, and both are asserted: it exists only because a transition
    landed in the log, and it spends the day — so a second trigger the same day
    sends nothing.
    """
    with Store(tmp_path / "vidit") as store:
        seed_tension(store, loop=None)
    channel = FakeChannel()
    first = surface(registry, channel)
    assert isinstance(first, Surfaced) and first.loops == ()
    assert view_of(registry).touches == {}, "a loopless message bounded a loop"

    again = surface(registry, channel, candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ])
    assert again == Silence(ALREADY_TODAY)
    assert len(channel.sent) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: nothing worth saying — the ordinary morning
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_quiet_night_sends_nothing_and_records_no_failure(
    registry, tmp_path, caplog
):
    """Matrix: *nothing worth saying*. The ordinary case.

    Nothing is sent, nothing is written, and nothing above ``INFO`` is logged —
    a quiet morning that produced a warning would train an operator to treat
    silence as a fault.
    """
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_entry(store, "b_1")
    channel = FakeChannel()
    mornings = Mornings()

    with caplog.at_level(logging.DEBUG):
        result = run_pass(registry)
        outcome = surface(registry, channel, candidates=result.candidates,
                          mornings=mornings)

    assert result.quiet and result.candidates == ()
    assert outcome == Silence(NOTHING_TO_SAY) and not outcome.fault
    assert channel.sent == []
    assert view_of(registry).touches == {}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert mornings.silences[NOTHING_TO_SAY] == 1 and mornings.faults == 0


@pytest.mark.cap8_silence
def test_a_pass_that_moved_nothing_produces_no_candidates(registry, tmp_path):
    """*Most* days are silent, and this is why: a candidate exists only for a
    tension the pass actually moved."""
    a_main(tmp_path, moves=())
    first = run_pass(registry)
    assert first.moved and first.candidates, "fixture moved nothing"
    second = run_pass(registry)
    assert second.unchanged and second.candidates == ()
    assert surface(registry, FakeChannel(),
                   candidates=second.candidates) == Silence(NOTHING_TO_SAY)


@pytest.mark.cap8_silence
def test_a_quiet_morning_asks_no_platform_and_writes_nothing(
    registry, tmp_path
):
    a_main(tmp_path)
    channel = FakeChannel()
    with Store(tmp_path / "vidit") as store:
        before = {p: p.read_bytes() for p in store.log.shards()}

    assert surface(registry, channel, candidates=()) == Silence(NOTHING_TO_SAY)
    assert channel.queries == [], "a quiet morning asked the platform anyway"
    with Store(tmp_path / "vidit") as store:
        assert {p: p.read_bytes() for p in store.log.shards()} == before


# ═════════════════════════════════════════════════════════════════════════════
# matrix: one good thing / two good things / ranking unit
# ═════════════════════════════════════════════════════════════════════════════


def test_a_tension_that_widened_overnight_produces_one_message_citing_it(
    registry, tmp_path
):
    """Matrix: *one good thing*. One message, and it cites where it came from."""
    a_main(tmp_path)
    channel = FakeChannel()
    outcome = surface(registry, channel)

    assert isinstance(outcome, Surfaced)
    assert outcome.origin == TENSION_ORIGIN
    assert outcome.loops == ("swim-weekly",)
    assert outcome.day == TODAY
    assert len(channel.sent) == 1
    assert channel.sent[0] == ("vidit", outcome.text)


def test_several_candidates_send_exactly_one(registry, tmp_path):
    """Matrix: *two good things*. Never two."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "swim-weekly", ident="l_1")
        seed_loop(store, "learn-tabla", timescale="months", ident="l_2")
        seed_tension(store, ident="x_1", pair=("b_1", "b_2"), loop="swim-weekly")
        seed_tension(store, ident="x_2", pair=("b_3", "b_4"), loop="learn-tabla")

    result = run_pass(registry)
    assert len(result.candidates) == 2, "fixture produced fewer than two"
    channel = FakeChannel()
    outcome = surface(registry, channel, candidates=result.candidates)

    assert isinstance(outcome, Surfaced)
    assert len(channel.sent) == 1
    assert len(view_of(registry).touches) == 1, "two loops were raised at once"


def test_the_ranking_unit_is_own_periods_and_not_raw_days(registry, tmp_path):
    """Matrix: *ranking unit*. The pair where the two units disagree.

    Review found that changing ``_periods`` to return ``elapsed_days`` passed
    the whole suite, because every multi-loop fixture happened to rank
    identically under both — so the unit the module's own docstring is built on
    was asserted by nothing.

    A days-loop thirty days quiet is **thirty** of its own periods. A
    years-loop four hundred days quiet is **1.1** of its own. Raw days ranks
    the farmland loop first; own-periods ranks the routine first, which is the
    whole reason the unit exists.
    """
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "take-medicine", timescale="days",
                  last_movement=stamp(NOON - 30 * DAY)[:10], ident="l_1")
        seed_loop(store, "buy-farmland", timescale="years",
                  last_movement=stamp(NOON - 400 * DAY)[:10], ident="l_2")
        seed_tension(store, ident="x_1", pair=("b_1", "b_2"),
                     loop="take-medicine")
        seed_tension(store, ident="x_2", pair=("b_3", "b_4"),
                     loop="buy-farmland")

    view = view_of(registry)
    ranked = eligible(run_pass(registry).candidates, view=view, now=NOW.stamp)
    assert [c.loops for c in ranked] == [("take-medicine",), ("buy-farmland",)]

    # And the two units really do disagree on this pair, so the case is not
    # passing by accident.
    held = loops.read(view.loops)
    days = {
        slug: held[slug].silence(now=NOW.stamp).elapsed_days
        for slug in ("take-medicine", "buy-farmland")
    }
    assert days["buy-farmland"] > days["take-medicine"], (
        "raw days no longer ranks these the other way; the case is vacuous"
    )


# ═════════════════════════════════════════════════════════════════════════════
# matrix: already sent today / local day / zone changed / future-stamped
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_second_trigger_the_same_local_day_sends_nothing(registry, tmp_path):
    """Matrix: *already sent today*. One a day, per main."""
    a_main(tmp_path)
    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)

    later = moment(NOON + 6 * 3600)
    assert surface(registry, channel, now=later, candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ]) == Silence(ALREADY_TODAY)
    assert len(channel.sent) == 1


def test_the_next_local_day_may_send_again(registry, tmp_path):
    """The other side: one a day is a bound, not a silencing."""
    a_main(tmp_path)
    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)

    pair = [Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))]
    tomorrow = moment(NOON + DAY)
    # The weeks-loop was raised yesterday, so the *bound* refuses even though
    # the day has turned — the two rules composing correctly.
    assert surface(registry, channel, now=tomorrow,
                   candidates=pair) == Silence(NOTHING_TO_SAY)

    next_week = moment(NOON + 8 * DAY)
    assert isinstance(
        surface(registry, channel, now=next_week, candidates=pair), Surfaced
    )
    assert len(channel.sent) == 2


@pytest.mark.cap8_silence
def test_a_day_marker_stamped_ahead_of_now_still_counts_as_spoken(
    registry, tmp_path
):
    """Matrix: *future-stamped touch*. Never a second message.

    A clock that jumped forward and was then corrected leaves a marker for a
    day that has not arrived. An equality test reads that as *not today* and
    sends again — reproduced by review. A day already covered stays covered.
    """
    a_main(tmp_path)
    mark_day(registry, "vidit", day="2026-09-05")
    channel = FakeChannel()
    assert surface(registry, channel) == Silence(ALREADY_TODAY)
    assert channel.sent == []


@pytest.mark.cap8_silence
def test_a_main_who_moves_west_overnight_still_gets_one_message(
    registry, tmp_path
):
    """Matrix: *zone changed overnight*. The stored day, not a recomputed one.

    Yesterday's message was sent at 2026-09-01T02:00Z, which was 2026-09-01 in
    Asia/Kolkata. Recomputing that marker under a new UTC-08:00 zone puts it on
    2026-08-31 — *yesterday* — so the rule sees an unspent day and sends again
    five hours later. Review reproduced exactly that.

    The marker stores the day it belonged to, so moving the main changes what
    *today* is and never what yesterday was.
    """
    a_main(tmp_path)
    tell_zone(registry, "vidit", "Asia/Kolkata")
    early = moment(NOON - 10 * 3600)  # 2026-09-01T02:00Z
    assert local_day(early.epoch, "Asia/Kolkata") == "2026-09-01"
    channel = FakeChannel()
    first = surface(registry, channel, now=early)
    assert isinstance(first, Surfaced) and first.day == "2026-09-01"

    # The main moves. ``tell_zone`` replaces the belief under its own id, so
    # the ladder sees one answer and not two — a main who has told Half two
    # zones has told it nothing it may act on (``due.zone_of``).
    tell_zone(registry, "vidit", "America/Los_Angeles")
    assert local_day(early.epoch, "America/Los_Angeles") == "2026-08-31"

    later = moment(NOON - 5 * 3600)  # still 2026-09-01 in Los Angeles
    assert local_day(later.epoch, "America/Los_Angeles") == "2026-09-01"
    assert surface(registry, channel, now=later, candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ]) == Silence(ALREADY_TODAY)
    assert len(channel.sent) == 1


def test_two_mains_in_different_zones_get_their_own_day_boundary(
    registry, tmp_path
):
    """Matrix: *local day*, two mains. Told, never inferred (AD-9).

    The window is chosen so exactly one of the two zones has turned over, and
    that fact is asserted through the same function the surface uses — so this
    cannot pass by accident on a day the offsets line up.
    """
    a_main(tmp_path, main_id="vidit")
    a_main(tmp_path, main_id="asha")
    tell_zone(registry, "vidit", "Pacific/Kiritimati")   # UTC+14
    tell_zone(registry, "asha", "Pacific/Niue")          # UTC-11

    channel = FakeChannel()
    assert isinstance(surface(registry, channel, main_id="vidit"), Surfaced)
    assert isinstance(surface(registry, channel, main_id="asha"), Surfaced)

    later = moment(NOON + 22 * 3600 + 30 * 60)
    assert local_day(later.epoch, "Pacific/Kiritimati") != local_day(
        NOON, "Pacific/Kiritimati"
    ), "the fixture's window no longer turns Kiritimati's day over"
    assert local_day(later.epoch, "Pacific/Niue") == local_day(
        NOON, "Pacific/Niue"
    ), "the fixture's window now turns Niue's day over too"

    pair = [Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))]
    assert surface(registry, channel, main_id="vidit", now=later,
                   candidates=pair) == Silence(NOTHING_TO_SAY)
    assert surface(registry, channel, main_id="asha", now=later,
                   candidates=pair) == Silence(ALREADY_TODAY)
    assert len(channel.sent) == 2


# ═════════════════════════════════════════════════════════════════════════════
# matrix: unreadable marker — costs one morning, not all of them
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_an_unreadable_day_marker_costs_one_morning_and_then_recovers(
    registry, tmp_path
):
    """Matrix: *unreadable marker*. Recoverable.

    The permanent version was the first one: the marker is replaced only by a
    later marker, a later marker is written only when Half is about to speak,
    and an unreadable one is exactly what blocks that — so a single corrupt
    record silenced a main for ever, with no recovery, no alert and no counter.

    Now the morning is spent on a **repair**: a day marker that says plainly
    that no message was sent, cites nothing because it surfaced nothing, and is
    readable. One morning lost; every morning after it reads cleanly.
    """
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        # ISO in shape and not a real day. ``records.make`` checks the stamp's
        # shape and not its calendar, so this is a log a build can produce.
        store.record(Op.TOUCH, "tc_bad", "2026-02-31T00:00Z",
                     **touch_module.spoke(day="2026-08-30",
                                          origin=TENSION_ORIGIN))
        # ...and then the day itself is corrupted, which takes the hand edit.
        shard = next(p for p in store.log.shards() if "2026-02" in p.name)
        shard.write_text(
            shard.read_text(encoding="utf-8").replace('"2026-08-30"', '"never"'),
            encoding="utf-8",
        )
        store.rebuild()

    channel = FakeChannel()
    mornings = Mornings()
    assert surface(registry, channel, mornings=mornings) == Silence(
        UNREADABLE_MARKER
    )
    assert channel.sent == []
    assert mornings.silences[UNREADABLE_MARKER] == 1

    repaired = view_of(registry).spoke
    assert touch_module.day_of(repaired) == TODAY
    assert repaired[SENT] is False

    # The morning after: nothing is blocked.
    tomorrow = moment(NOON + 8 * DAY)
    assert isinstance(surface(registry, channel, now=tomorrow, candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ]), Surfaced)


@pytest.mark.cap8_silence
def test_an_unreadable_marker_is_warned_as_well_as_counted(
    registry, tmp_path, caplog
):
    """*"No recovery, no alert and no counter"* was review's whole finding.

    The recovery is the repair marker; the counter is ``Mornings``; this is the
    alert. It is a warning rather than an error because nothing failed — the
    morning ends the way a quiet one does — but it is not ordinary either, and
    an operator who cannot see it cannot tell a corrupt log from a quiet life.
    """
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        store.log.append(make_record(
            Op.TOUCH, "tc_bad", stamp(NOON - 3600),
            **touch_module.repaired(day="2026-08-30"),
        ))
        shard = next(p for p in store.log.shards() if "2026-09" in p.name)
        shard.write_text(
            shard.read_text(encoding="utf-8").replace('"2026-08-30"', '"never"'),
            encoding="utf-8",
        )
        store.rebuild()

    with caplog.at_level(logging.WARNING):
        assert surface(registry, FakeChannel()) == Silence(UNREADABLE_MARKER)
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warned, "an unreadable day marker passed without an alert"
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


@pytest.mark.cap8_silence
def test_a_loop_whose_bound_cannot_be_measured_is_warned_and_counted(
    registry, tmp_path
):
    """The per-loop half of the same finding.

    The raise is treated as no raise — otherwise that wanting is silenced for
    ever — so the morning goes ahead. What must not happen is that it goes
    ahead *quietly*: the loop is counted and an operator is told.
    """
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        store.log.append(make_record(
            Op.TOUCH, "tc_bad", stamp(NOON - 3600),
            **touch_module.raised("swim-weekly", origin=TENSION_ORIGIN),
        ))
        shard = next(p for p in store.log.shards() if "2026-09" in p.name)
        shard.write_text(
            shard.read_text(encoding="utf-8").replace(
                f'"t":"{stamp(NOON - 3600)}"', '"t":"2026-02-31T00:00Z"'
            ),
            encoding="utf-8",
        )
        store.rebuild()

    mornings = Mornings()
    outcome = surface(registry, FakeChannel(), mornings=mornings)
    assert isinstance(outcome, Surfaced)
    assert mornings.degraded == 1, "an unmeasurable bound passed uncounted"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: no traceable origin / erased origin
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
@pytest.mark.parametrize(
    "origin",
    [
        Origin(kind="", id="x_1"),
        Origin(kind="inferred", id="x_1"),
        Origin(kind=TOUCH_TENSION, id=""),
        Origin(kind=TOUCH_TENSION, id="   "),
        Origin(kind=None, id="x_1"),
        Origin(kind=TOUCH_TENSION, id=None),
    ],
    ids=["blank-kind", "kind-outside-the-set", "blank-id", "whitespace-id",
         "no-kind", "no-id"],
)
def test_a_candidate_that_cannot_cite_the_pass_is_not_surfaced(
    registry, tmp_path, origin
):
    """Matrix: *no traceable origin*. Never untraceable."""
    a_main(tmp_path)
    channel = FakeChannel()
    assert surface(registry, channel, candidates=[
        Candidate(origin=origin, entries=("b_1", "b_2"))
    ]) == Silence(NOTHING_TO_SAY)
    assert channel.sent == []


@pytest.mark.cap8_silence
def test_a_tension_expunged_before_morning_is_not_surfaced(registry, tmp_path):
    """Matrix: *erased origin*. Never cites what is gone.

    The pass runs at night and the main erases the tension before the surface
    runs. Half would otherwise still speak about it, and the touch would
    permanently cite an id nothing can resolve.
    """
    a_main(tmp_path)
    candidates = run_pass(registry).candidates
    assert candidates
    with Store(tmp_path / "vidit") as store:
        store.expunge("x_1", t="2026-09-01T06:00:00Z")

    channel = FakeChannel()
    assert surface(registry, channel,
                   candidates=candidates) == Silence(NOTHING_TO_SAY)
    assert channel.sent == []
    assert view_of(registry).touches == {}


def test_origin_liveness_is_checked_for_every_kind(registry, tmp_path):
    """Each of the three kinds is checkable, so none is waved through."""
    a_main(tmp_path)
    view = view_of(registry)
    assert live_origin(Origin(kind=TOUCH_TENSION, id="x_1"), view=view)
    assert not live_origin(Origin(kind=TOUCH_TENSION, id="x_9"), view=view)
    assert live_origin(
        Origin(kind=TOUCH_LOOP_TRANSITION, id="swim-weekly"), view=view
    )
    assert not live_origin(
        Origin(kind=TOUCH_LOOP_TRANSITION, id="no-such-loop"), view=view
    )
    assert live_origin(Origin(kind=TOUCH_INGESTED, id="b_1"), view=view)
    assert not live_origin(Origin(kind=TOUCH_INGESTED, id="b_9"), view=view)


def test_every_surfaced_thing_names_what_it_came_from(registry, tmp_path):
    """*"Given any surfaced thing, it cites the tension, loop transition or
    ingested item it came from."* On the value, and in the log."""
    a_main(tmp_path)
    outcome = surface(registry, FakeChannel())
    assert isinstance(outcome, Surfaced) and outcome.origin.traceable
    assert touch_module.origin_of(
        view_of(registry).touches["swim-weekly"]
    ) == outcome.origin


@pytest.mark.cap8_silence
def test_a_candidate_over_an_entry_the_ledger_no_longer_holds_is_dropped(
    registry, tmp_path
):
    """A tension whose side was retracted is not a disagreement any more, and
    the whole candidate goes rather than half of it."""
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        store.record(Op.RETRACT, "r_1", "2026-08-30T00:00:00Z", target="b_2")
    assert surface(registry, FakeChannel(), candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ]) == Silence(NOTHING_TO_SAY)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: failed append — a candidate cites the log, not the plan
# ═════════════════════════════════════════════════════════════════════════════


def test_a_transition_that_could_not_be_appended_produces_no_candidate(
    registry, tmp_path
):
    """Matrix: *failed append*. Cites the log, not the plan.

    Review found that hoisting the mint above the ``try`` passed the whole
    suite — and Half would then send a message citing a tension the log still
    shows as `fresh`, which is the story's own Never. The existing
    failed-append case never read ``result.candidates``.
    """
    a_main(tmp_path)

    class Refusing:
        def __init__(self, inner):
            self.inner = inner

        async def tension_view(self, main_id):
            return await self.inner.tension_view(main_id)

        async def note_transition(self, main_id, **kwargs):
            raise OSError("no space left on device")

    result = asyncio.run(
        TensionPass(ledger=Refusing(registry)).evaluate("vidit", NOW)
    )
    assert result.unrecorded == ("x_1",)
    assert result.moved == {}
    assert result.candidates == (), (
        "a candidate was minted for a transition the log never received"
    )
    with Store(tmp_path / "vidit") as store:
        assert store.state().tensions["x_1"][STATE] == str(TensionState.FRESH)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: aftercare — the ceiling, swept, with no branch and no field for it
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_main_capped_at_behave_receives_no_mirror(registry, tmp_path):
    """Matrix: *aftercare*. Silence, through the ladder rather than a branch."""
    a_main(tmp_path)
    set_ceiling(registry, "vidit", License.BEHAVE)
    channel = FakeChannel()

    assert surface(registry, channel) == Silence(NOTHING_MAY_BE_SAID)
    assert channel.sent == []
    assert view_of(registry).touches == {}


@pytest.mark.cap8_silence
def test_a_main_with_an_aftercare_record_and_a_permissive_ceiling_still_speaks(
    registry, tmp_path
):
    """Matrix: *aftercare by any route*. The case that separates the two rules.

    A main who has been through aftercare, answered, and had their cap restored
    to `assert` has an ``aftercare`` record in their log for ever — aftercare
    records are never deleted. If anything in the surface branched on the
    *record* rather than on the *cap*, this main would be silenced permanently.

    Review's mutant did exactly that and passed 3182 tests. It fails here, and
    it also cannot be written any more: the surface is handed a view with no
    aftercare field in it.
    """
    a_main(tmp_path)
    asyncio.run(registry.suspend_for_crisis(
        "vidit", t="2026-06-01T00:00:00Z", tier="disclosure", score=2
    ))
    asyncio.run(registry.reverse_crisis(
        "vidit", t="2026-06-02T00:00:00Z", because="confirmed with the main"
    ))
    asyncio.run(registry.note_aftercare(
        "vidit", t="2026-07-05T00:00:00Z", state="agreed"
    ))
    with Store(tmp_path / "vidit") as store:
        assert store.state().aftercare is not None, "fixture wrote no record"
        assert Ceiling(store.state().ceiling).rung is License.ASSERT

    channel = FakeChannel()
    outcome = surface(registry, channel)
    assert isinstance(outcome, Surfaced), (
        "a main whose aftercare has finished was silenced by the record of it"
    )
    assert len(channel.sent) == 1


@pytest.mark.cap8_silence
@pytest.mark.parametrize("rung", list(RUNGS), ids=[str(r) for r in RUNGS])
def test_nothing_at_any_rung_survives_a_behave_ceiling(
    registry, tmp_path, rung
):
    """Parameterised over ``ladder.RUNGS`` rather than three literals, so a
    fourth rung is swept the day it exists."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_tension(store, rungs=(rung, rung))
    set_ceiling(registry, "vidit", License.BEHAVE)
    channel = FakeChannel()
    assert surface(registry, channel) == Silence(NOTHING_MAY_BE_SAID)
    assert channel.sent == []


@pytest.mark.cap8_silence
@pytest.mark.parametrize("cap", list(RUNGS), ids=[f"cap-{r}" for r in RUNGS])
@pytest.mark.parametrize("own", list(RUNGS), ids=[f"own-{r}" for r in RUNGS])
def test_a_surface_speaks_exactly_when_the_capped_rung_reaches_speaks_at(
    registry, tmp_path, own, cap
):
    """The whole ladder against the whole ceiling, stated as an equality.

    What a surface does is decided by ``permitted(record, ceiling)`` against
    ``SPEAKS_AT`` and by nothing else, at every ``(own, cap)`` pair — so there
    is no rung at which the cap is applied and none at which it is skipped.
    """
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_tension(store, rungs=(own, own))
    if cap is not ladder.TOP:
        set_ceiling(registry, "vidit", cap)

    channel = FakeChannel()
    outcome = surface(registry, channel)

    view = view_of(registry)
    expected = any(
        height(permitted(view.beliefs[ident], ceiling=view.ceiling))
        >= height(SPEAKS_AT)
        for ident in ("b_1", "b_2")
    )
    assert isinstance(outcome, Surfaced) is expected
    assert bool(channel.sent) is expected


def test_the_channels_a_surface_speaks_from_are_the_ones_the_builder_fills():
    """``SPEAKS_AT`` and ``speech`` must agree with what ``build`` actually
    does, swept over every rung through the *real* builder."""
    for rung in RUNGS:
        belief = {"id": "b_1", "claim": "a claim", "loop": "swim-weekly",
                  "license": str(rung), "support": ["s_1"],
                  "known_to_main": True}
        context = build_context(
            [RankedBelief(id="b_1", claim="a claim", prefix="", bm25=None,
                          belief=belief)],
            now=NOW.stamp, ceiling=None,
        )
        assert bool(speech(context)) is (
            height(permitted(belief, ceiling=None)) >= height(SPEAKS_AT)
        ), f"speech() and SPEAKS_AT disagree at {rung}"

    assert SPOKEN_CHANNELS == ("content", "questions")
    assert SPEAKS_AT is License.ASK


# ── the ceiling as a shape, not only as a behaviour ─────────────────────────


@pytest.mark.cap8_structure
def test_the_surface_is_handed_a_projection_and_not_the_fold():
    """Matrix: *aftercare by any route*, structurally.

    An import scan and a protocol scan both missed ``if state.aftercare is not
    None`` because it needed neither. What forbids it now is that the field is
    not there: ``SurfaceView`` is an allowlist, and every field of ``State``
    that is not on it is unreachable from the surface.

    The allowlist is read from the module rather than copied here, so adding a
    field to ``VISIBLE`` is the deliberate edit and this case moves with it.
    """
    view = view_fields()
    assert set(view) == set(VISIBLE) | {"ceiling"}

    hidden = {f.name for f in __import__("dataclasses").fields(State)} - set(VISIBLE)
    assert {"aftercare", "crisis", "schedule", "ceiling"} <= hidden, (
        "State no longer carries the fields this narrowing exists to hide"
    )
    for name in hidden - {"ceiling"}:
        assert not hasattr(SurfaceView(), name), (
            f"the surface can reach {name!r}; per-feature suppression is one "
            f"line away again (AD-28)"
        )


@pytest.mark.cap8_structure
def test_the_narrowing_drops_what_it_says_it_drops(store):
    """Non-vacuity for the case above, through the real ``narrowed``."""
    store.record(Op.AFTERCARE, "ac_1", "2026-08-01T00:00:00Z", state="asked")
    store.record(Op.CRISIS, "cr_1", "2026-08-01T00:00:00Z",
                 state="entered", tier="disclosure", score=1)
    state = store.fold()
    assert state.aftercare is not None and state.crisis is not None

    view = narrowed(state, Ceiling(None))
    assert not hasattr(view, "aftercare") and not hasattr(view, "crisis")
    assert view.ceiling.rung is License.ASSERT


@pytest.mark.cap8_structure
def test_the_surface_package_cannot_reach_aftercare_at_all():
    """The import graph, kept as a second, independent guard.

    Weaker than the narrowing above — it is a name check — but it is cheap and
    it catches the other direction: a module that reads aftercare out of the
    store itself rather than out of what it was handed.
    """
    doors = {name for name in dir(SurfaceLedger) if not name.startswith("_")}
    assert doors == {"crisis_open", "zone_records", "surface_view", "claim_day"}

    imported: set[str] = set()
    for path in sorted((ROOT / "half" / "surface").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{a.name}" for a in node.names)
    offenders = sorted(
        name for name in imported
        if "aftercare" in name or name.startswith("half.crisis")
    )
    assert not offenders, f"half/surface/ can reach {offenders} (AD-28)"


@pytest.mark.cap8_structure
def test_no_license_is_resolved_in_the_surface_without_a_ceiling():
    """Every route to a rung passes a cap, asserted over the package.

    The set of resolvers is **derived from the ladder itself** — every public
    function returning a ``License`` — rather than listed here, so a new
    resolver is covered on the day it is written. Functions that cannot take a
    ceiling (``own_rung``, ``rung_of``) therefore fail this rule automatically
    if the surface ever calls one.
    """
    resolvers = {
        name
        for name, obj in vars(ladder).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and "License" in str(inspect.signature(obj).return_annotation)
    }
    resolvers.add("build")
    assert {"permitted", "own_rung", "rung_of"} <= resolvers

    offenders: list[str] = []
    for path in sorted((ROOT / "half" / "surface").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else None
            )
            if called in resolvers or called == "build_context":
                if not any(kw.arg == "ceiling" for kw in node.keywords):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} {called}()"
                    )
    assert not offenders, f"a license is resolved without a ceiling at {offenders}"


@pytest.mark.cap8_structure
def test_the_uncapped_resolver_scan_catches_the_call_it_exists_for(tmp_path):
    """Non-vacuity for the scan above."""
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        "def surface(candidate):\n    return build(candidate, now='x')\n",
        encoding="utf-8",
    )
    found = [
        node for node in ast.walk(ast.parse(bypass.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build"
        and not any(kw.arg == "ceiling" for kw in node.keywords)
    ]
    assert found, "the uncapped-resolver scan does not see a bare build()"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: behave material shapes but is never quoted
# ═════════════════════════════════════════════════════════════════════════════


def test_behave_material_shapes_the_surface_and_is_never_quoted(
    registry, tmp_path
):
    """Matrix: *behave material*. AD-18, at the one surface that speaks first."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_entry(store, "b_1", rung=License.ASSERT,
                   claim="has swum twice this month")
        seed_entry(store, "b_2", rung=License.BEHAVE,
                   claim="is avoiding the conversation with his brother")
        store.record(Op.TENSION, "x_1", MINTED, between=["b_1", "b_2"],
                     **{STATE: str(TensionState.FRESH)}, **ladder.admitted())
        seed_belief(store, "b_1", MOVED, subject="self",
                    claim="has swum twice this month", loop="swim-weekly",
                    support=["s_b_1", "s_more"], topics=["swimming"],
                    rung=License.ASSERT)

    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)
    sent = channel.sent[0][1]
    for fragment in ("avoiding", "brother", "conversation"):
        assert fragment not in sent, "a behave claim's wording reached the wire"
    assert "has swum twice this month" in sent


@pytest.mark.cap8_silence
def test_a_surface_whose_only_material_is_behave_says_nothing(
    registry, tmp_path
):
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_tension(store, rungs=(License.BEHAVE, License.BEHAVE))
    channel = FakeChannel()
    assert surface(registry, channel) == Silence(NOTHING_MAY_BE_SAID)
    assert channel.sent == []


def test_the_wire_carries_no_directive_line(registry, tmp_path):
    """A directive is internal shaping vocabulary aimed at a model."""
    a_main(tmp_path)
    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)
    assert "directive[" not in channel.sent[0][1]


def test_a_tension_across_two_loops_is_spoken_with_both_its_entries(
    registry, tmp_path
):
    """A tension **is** the pair, so speaking about one side is not speaking
    about a tension.

    The first version split a candidate per loop and narrowed its entries to
    that loop's, so a tension whose two sides sat on different wantings was
    spoken one-sided. It also meant one raise quietly touched a second wanting
    the bound never saw — so both loops are bounded here too.
    """
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "swim-weekly", ident="l_1")
        seed_loop(store, "learn-tabla", timescale="months", ident="l_2")
        seed_entry(store, "b_1", loop="swim-weekly", rung=License.ASSERT)
        seed_entry(store, "b_2", loop="learn-tabla", rung=License.ASSERT)
        store.record(Op.TENSION, "x_1", MINTED, between=["b_1", "b_2"],
                     **{STATE: str(TensionState.FRESH)}, **ladder.admitted())
        seed_belief(store, "b_1", MOVED, subject="self", claim=a_claim("b_1"),
                    loop="swim-weekly", rung=License.ASSERT,
                    support=["s_b_1", "s_more"], topics=["swimming"])

    channel = FakeChannel()
    outcome = surface(registry, channel)
    assert isinstance(outcome, Surfaced)
    assert set(outcome.entries) == {"b_1", "b_2"}
    assert outcome.loops == ("learn-tabla", "swim-weekly")
    sent = channel.sent[0][1]
    assert a_claim("b_1") in sent and a_claim("b_2") in sent

    # Both wantings are bounded, not just the one the message was filed under.
    assert set(view_of(registry).touches) == {"swim-weekly", "learn-tabla"}


@pytest.mark.cap8_silence
def test_a_candidate_is_refused_when_any_of_its_loops_is_nagging(
    registry, tmp_path
):
    """All or nothing. One raise must not quietly touch a wanting the bound
    would have refused."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "swim-weekly", ident="l_1")
        seed_loop(store, "buy-farmland", timescale="years",
                  last_movement="2020-01-01", ident="l_2")
        seed_entry(store, "b_1", loop="swim-weekly", rung=License.ASSERT)
        seed_entry(store, "b_2", loop="buy-farmland", rung=License.ASSERT)
        store.record(Op.TENSION, "x_1", MINTED, between=["b_1", "b_2"],
                     **{STATE: str(TensionState.FRESH)}, **ladder.admitted())
        seed_belief(store, "b_1", MOVED, subject="self", claim=a_claim("b_1"),
                    loop="swim-weekly", rung=License.ASSERT,
                    support=["s_b_1", "s_more"], topics=["swimming"])
    asyncio.run(registry.claim_day(
        "vidit", t=stamp(NOON - 10 * DAY), day="2026-08-22",
        records=[touch_module.raised("buy-farmland", origin=TENSION_ORIGIN)],
    ))
    assert surface(registry, FakeChannel()) == Silence(NOTHING_TO_SAY)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: crisis / unreachable
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_main_in_crisis_mode_gets_nothing_unprompted(registry, tmp_path):
    """Matrix: *crisis*. Suspended entirely (CAP-12)."""
    a_main(tmp_path)
    result = run_pass(registry)
    enter_crisis(registry, "vidit")
    channel = FakeChannel()

    assert surface(registry, channel,
                   candidates=result.candidates) == Silence(CRISIS)
    assert channel.sent == [] and channel.queries == []
    assert view_of(registry).touches == {}


@pytest.mark.cap8_silence
def test_a_main_who_enters_the_mode_mid_morning_is_still_suspended(
    registry, tmp_path
):
    """The mode is re-asserted inside the mutex that spends the day.

    Everything before the claim happens outside any lock, so a disclosure
    arriving while a morning is being assembled would otherwise be answered by
    an unprompted message a moment later.
    """
    a_main(tmp_path)
    candidates = run_pass(registry).candidates

    class EnteringMidway:
        """A ledger that lets the mode open between the read and the claim."""

        def __init__(self, inner):
            self.inner = inner
            self.opened = False

        def crisis_open(self, main_id):
            return self.inner.crisis_open(main_id) if self.opened else False

        def zone_records(self, main_id):
            return self.inner.zone_records(main_id)

        async def surface_view(self, main_id):
            view = await self.inner.surface_view(main_id)
            await self.inner.suspend_for_crisis(
                main_id, t="2026-08-31T00:00:00Z", tier="disclosure", score=2
            )
            self.opened = True
            return view

        async def claim_day(self, main_id, **kwargs):
            return await self.inner.claim_day(main_id, **kwargs)

    channel = FakeChannel()
    made = MorningSurface(ledger=EnteringMidway(registry), channel=channel)
    outcome = asyncio.run(
        made.surface("vidit", now=NOW, candidates=candidates)
    )
    assert outcome == Silence(CRISIS)
    assert channel.sent == []


@pytest.mark.cap8_silence
def test_the_scheduler_also_refuses_to_run_the_pass_for_a_main_in_the_mode(
    registry, tmp_path
):
    """Two independent refusals, which is what CAP-12 asks for."""
    from half.schedule.tick import Scheduler

    a_main(tmp_path)
    enter_crisis(registry, "vidit")
    channel = FakeChannel()
    asyncio.run(registry.note_pass(
        "vidit", t=stamp(NOON - 600),
        fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC", TOLD_ZONE: False},
    ))
    result = asyncio.run(Scheduler(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=NOON),
        work=MorningPass(
            consolidate=TensionPass(ledger=registry),
            surface=MorningSurface(ledger=registry, channel=channel),
        ),
    ).tick())
    assert result.suspended == ("vidit",) and result.ran == ()
    assert channel.sent == []


@pytest.mark.cap8_silence
@pytest.mark.parametrize(
    "reach", [Reachability.NEVER_CONTACTED, Reachability.WINDOW_CLOSED]
)
def test_an_unreachable_main_is_silence_and_never_an_error(
    registry, tmp_path, caplog, reach
):
    """Matrix: *unreachable*. AD-7: asked, never assumed — and never an error.

    Nothing is queued for later either: no day is claimed, so tomorrow's
    surface chooses from tomorrow's pass rather than from a backlog.
    """
    a_main(tmp_path)
    channel = FakeChannel(reach=reach)
    with caplog.at_level(logging.DEBUG):
        outcome = surface(registry, channel)

    assert outcome == Silence(str(reach))
    assert outcome.reason in REASONS and not outcome.fault
    assert channel.sent == []
    assert view_of(registry).spoke is None, "an unreachable morning spent a day"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.cap8_silence
def test_reachability_is_asked_after_the_choice_not_before(
    registry, tmp_path
):
    """A morning the bound silenced is not reported as an unreachable one.

    Asking first skewed the very reason set ``Silence`` exists to make
    countable: every quiet morning for an unreachable main came back
    ``never_contacted``, so an operator could not see that the loops were
    simply inside their periods.
    """
    a_main(tmp_path)
    mark_day(registry, "vidit", day="2026-08-25",
             t=stamp(NOON - 7 * DAY), loops_=("swim-weekly",))
    channel = FakeChannel(reach=Reachability.NEVER_CONTACTED)
    assert surface(registry, channel) == Silence(NOTHING_TO_SAY)
    assert channel.queries == [], "the platform was asked before the choice"


# ═════════════════════════════════════════════════════════════════════════════
# the gates, in every ordering
# ═════════════════════════════════════════════════════════════════════════════


def _gate_crisis(registry, tmp_path, channel):
    enter_crisis(registry, "vidit")


def _gate_already_today(registry, tmp_path, channel):
    mark_day(registry, "vidit", day=TODAY)


def _gate_unreachable(registry, tmp_path, channel):
    channel.reach = Reachability.WINDOW_CLOSED


def _gate_capped(registry, tmp_path, channel):
    set_ceiling(registry, "vidit", License.BEHAVE)


def _gate_nagging(registry, tmp_path, channel):
    asyncio.run(registry.claim_day(
        "vidit", t=stamp(NOON - 2 * DAY), day="2026-08-30",
        records=[touch_module.raised("swim-weekly", origin=TENSION_ORIGIN)],
    ))


GATES = {
    "crisis": _gate_crisis,
    "already-today": _gate_already_today,
    "unreachable": _gate_unreachable,
    "capped": _gate_capped,
    "nagging": _gate_nagging,
}


@pytest.mark.cap8_silence
@pytest.mark.parametrize("first", sorted(GATES))
@pytest.mark.parametrize("second", sorted(GATES))
def test_any_two_gates_in_any_order_still_produce_silence(
    registry, tmp_path, first, second
):
    """Every pair, both ways round. The outcome must be silence for all of them.

    The *reason* legitimately depends on which gate is asked first, so what is
    asserted is the outcome and the two facts that hold whatever the reason:
    nothing was sent, and nothing new was recorded.
    """
    a_main(tmp_path)
    channel = FakeChannel()
    GATES[first](registry, tmp_path, channel)
    if second != first:
        GATES[second](registry, tmp_path, channel)
    before = view_of(registry)

    outcome = surface(registry, channel)
    assert isinstance(outcome, Silence), f"{first} + {second} produced a message"
    assert outcome.reason in REASONS
    assert channel.sent == []
    after = view_of(registry)
    assert after.touches == before.touches, "a silent morning raised a loop"


@pytest.mark.cap8_silence
@pytest.mark.parametrize("gate", sorted(GATES))
def test_each_gate_alone_silences_a_morning_that_would_otherwise_speak(
    registry, tmp_path, gate
):
    """Non-vacuity for the sweep: without any gate this fixture speaks."""
    a_main(tmp_path)
    channel = FakeChannel()
    GATES[gate](registry, tmp_path, channel)
    assert isinstance(surface(registry, channel), Silence)


@pytest.mark.cap8_silence
def test_the_same_fixture_with_no_gate_at_all_does_speak(registry, tmp_path):
    a_main(tmp_path)
    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: missed day / determinism / one main fails
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_missed_window_sends_nothing_and_queues_nothing(registry, tmp_path):
    """Matrix: *missed day*. No catch-up, ever — and no backlog either."""
    from half.civil import instant
    from half.schedule.tick import Scheduler

    a_main(tmp_path)
    channel = FakeChannel()
    asyncio.run(registry.note_pass(
        "vidit", t=stamp(NOON - 8 * DAY),
        fields={NEXT_PASS_AT: stamp(NOON - 7 * DAY), ZONE: "UTC",
                TOLD_ZONE: False},
    ))
    work = MorningPass(
        consolidate=TensionPass(ledger=registry),
        surface=MorningSurface(ledger=registry, channel=channel),
    )
    missed = asyncio.run(Scheduler(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=NOON), work=work,
    ).tick())
    assert missed.missed == ("vidit",) and missed.ran == ()
    assert channel.sent == [] and view_of(registry).spoke is None

    due_at = registry.schedule_record("vidit")[NEXT_PASS_AT]
    caught_up = asyncio.run(Scheduler(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=instant(due_at) + 30), work=work,
    ).tick())
    assert caught_up.ran == ("vidit",)
    assert len(channel.sent) == 1, "a missed week arrived at once"


def test_the_same_log_and_the_same_now_choose_identically(registry, tmp_path):
    """Matrix: *determinism*."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "swim-weekly", ident="l_1")
        seed_loop(store, "learn-tabla", timescale="months", ident="l_2")
        seed_loop(store, "buy-farmland", timescale="years",
                  last_movement="2020-01-01", ident="l_3")
        seed_tension(store, ident="x_1", pair=("b_1", "b_2"), loop="swim-weekly")
        seed_tension(store, ident="x_2", pair=("b_3", "b_4"), loop="learn-tabla")
        seed_tension(store, ident="x_3", pair=("b_5", "b_6"),
                     loop="buy-farmland")

    candidates = run_pass(registry).candidates
    view = view_of(registry)

    first = choose(candidates, view=view, now=NOW.stamp)
    second = choose(list(reversed(candidates)), view=view, now=NOW.stamp)
    assert first == second and first is not None
    assert (
        [c.loops for c in eligible(candidates, view=view, now=NOW.stamp)]
        == [c.loops for c in eligible(list(reversed(candidates)), view=view,
                                      now=NOW.stamp)]
    )


def test_the_choice_does_not_depend_on_dict_iteration_order(registry, tmp_path):
    """Two candidates that tie on silence are separated by their loops."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "a-loop", timescale="weeks",
                  last_movement="2026-08-01", ident="l_1")
        seed_loop(store, "b-loop", timescale="weeks",
                  last_movement="2026-08-01", ident="l_2")
        seed_tension(store, ident="x_1", pair=("b_1", "b_2"), loop="a-loop")
        seed_tension(store, ident="x_2", pair=("b_3", "b_4"), loop="b-loop")

    view = view_of(registry)
    candidates = run_pass(registry).candidates
    assert choose(candidates, view=view, now=NOW.stamp).loops == ("a-loop",)
    assert choose(list(reversed(candidates)), view=view,
                  now=NOW.stamp).loops == ("a-loop",)


@pytest.mark.cap8_silence
def test_one_mains_unreadable_record_is_counted_and_stops_nobody(
    registry, tmp_path, caplog
):
    """Matrix: *one main fails*. **Counted**; other mains unaffected.

    The counting half was satisfied by nothing before review: every outcome was
    discarded, so a main who had been silent for a month looked exactly like a
    main with a quiet life.
    """

    class Broken:
        def crisis_open(self, main_id):
            return False

        def zone_records(self, main_id):
            return ()

        async def surface_view(self, main_id):
            raise OSError("the store could not be read")

        async def claim_day(self, main_id, **kwargs):  # pragma: no cover
            raise AssertionError("nothing should be written")

    channel = FakeChannel()
    mornings = Mornings()
    broken = MorningSurface(ledger=Broken(), channel=channel,
                            mornings=mornings)
    with caplog.at_level(logging.ERROR):
        outcome = asyncio.run(broken.surface(
            "vidit", now=NOW,
            candidates=[Candidate(origin=TENSION_ORIGIN, entries=("b_1",))],
        ))
    assert isinstance(outcome, Silence) and outcome.fault
    assert channel.sent == []
    assert mornings.faults == 1 and mornings.sent == 0
    # AD-22: the type and nothing else.
    assert all("could not be read" not in r.getMessage() for r in caplog.records)


def test_the_counter_holds_counts_and_never_content(registry, tmp_path):
    """AD-22 as a property of the type: there is nowhere here to put a claim."""
    a_main(tmp_path)
    mornings = Mornings()
    assert isinstance(surface(registry, FakeChannel(), mornings=mornings),
                      Surfaced)
    surface(registry, FakeChannel(), mornings=mornings, candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ])
    assert mornings.sent == 1
    assert mornings.silences == {ALREADY_TODAY: 1}
    assert set(mornings.silences) <= REASONS
    fields = {f.name for f in __import__("dataclasses").fields(Mornings)}
    assert fields == {"sent", "silences", "degraded"}


@pytest.mark.cap8_silence
def test_only_a_fault_is_logged_as_an_error(registry, tmp_path, caplog):
    """The module's own sentence, made true.

    An earlier docstring said *nothing here logs a silent day as a failure*
    while three reasons did. The rule is that an **ordinary** silence never
    does, and that the three that are not ordinary always do.
    """
    a_main(tmp_path)
    with caplog.at_level(logging.DEBUG):
        for gate in sorted(GATES):
            channel = FakeChannel()
            GATES[gate](registry, tmp_path, channel)
            outcome = surface(registry, channel)
            assert isinstance(outcome, Silence) and not outcome.fault
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert FAULTS == {"unreadable", "unrecorded", "unsent"}


def test_a_surface_that_raises_never_fails_the_tick(registry, tmp_path):
    from half.schedule.tick import Scheduler

    class Exploding(FakeChannel):
        def capability_query(self, main_id):
            raise RuntimeError("boom")

    a_main(tmp_path)
    asyncio.run(registry.note_pass(
        "vidit", t=stamp(NOON - 600),
        fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC", TOLD_ZONE: False},
    ))
    result = asyncio.run(Scheduler(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=NOON),
        work=MorningPass(
            consolidate=TensionPass(ledger=registry),
            surface=MorningSurface(ledger=registry, channel=Exploding()),
        ),
    ).tick())
    assert result.ran == ("vidit",) and result.failed == ()


# ═════════════════════════════════════════════════════════════════════════════
# claiming the day: serialized, and the send is what may fail after it
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_two_overlapping_mornings_send_once(registry, tmp_path):
    """The check and the append are one serialized operation.

    The first version read the marker under the mutex, released it, decided,
    and re-acquired to append — so two runs both read yesterday and both sent.

    **The gap is forced open**, because it will not open on its own here:
    ``asyncio.Lock.acquire`` takes a fast path when the lock is free and does
    not yield, so two ``gather``-ed mornings run one after the other and the
    race a real second worker produces never happens in a test. The wrapper
    below yields exactly where the real gap is — between reading the view and
    claiming the day — which is the shape an in-process ticker and an
    operator's manual run actually have.
    """

    class Interleaving:
        def __init__(self, inner):
            self.inner = inner

        def crisis_open(self, main_id):
            return self.inner.crisis_open(main_id)

        def zone_records(self, main_id):
            return self.inner.zone_records(main_id)

        async def surface_view(self, main_id):
            view = await self.inner.surface_view(main_id)
            await asyncio.sleep(0)  # the window a second worker lands in
            return view

        async def claim_day(self, main_id, **kwargs):
            return await self.inner.claim_day(main_id, **kwargs)

    a_main(tmp_path)
    channel = FakeChannel()
    candidates = run_pass(registry).candidates

    async def both():
        made = MorningSurface(ledger=Interleaving(registry), channel=channel)
        return await asyncio.gather(
            made.surface("vidit", now=NOW, candidates=candidates),
            made.surface("vidit", now=NOW, candidates=candidates),
        )

    outcomes = asyncio.run(both())
    assert sum(isinstance(o, Surfaced) for o in outcomes) == 1, (
        "two overlapping mornings both sent"
    )
    assert [o for o in outcomes if isinstance(o, Silence)] == [
        Silence(ALREADY_TODAY)
    ]
    assert len(channel.sent) == 1


@pytest.mark.cap8_silence
def test_a_day_that_cannot_be_claimed_stops_the_send(registry, tmp_path):
    """*"A surface whose marker could not be written has not earned the right
    to send."* The same asymmetry ``Scheduler._advance`` makes for a due time.
    """

    class NoWrite:
        def __init__(self, inner):
            self.inner = inner

        def crisis_open(self, main_id):
            return self.inner.crisis_open(main_id)

        def zone_records(self, main_id):
            return self.inner.zone_records(main_id)

        async def surface_view(self, main_id):
            return await self.inner.surface_view(main_id)

        async def claim_day(self, main_id, **kwargs):
            raise OSError("no space left on device")

    a_main(tmp_path)
    channel = FakeChannel()
    outcome = asyncio.run(
        MorningSurface(ledger=NoWrite(registry), channel=channel).surface(
            "vidit", now=NOW, candidates=run_pass(registry).candidates
        )
    )
    assert outcome == Silence(UNRECORDED) and channel.sent == []


def test_a_claim_whose_rebuild_failed_is_still_a_claim(registry, tmp_path):
    """``Store.append`` writes the line and *then* rebuilds the derived view.

    A failure in the rebuild leaves the record durable, so treating it as a
    failed claim would spend the day and report that nothing was written —
    costing the main a message that was already paid for. The claim is re-read
    against the log before the failure is believed.
    """
    a_main(tmp_path)
    day_marker = touch_module.spoke(day=TODAY, origin=TENSION_ORIGIN,
                                    loops=("swim-weekly",))

    from half.store import db as db_module

    real_rebuild = db_module.rebuild
    calls = {"n": 0}

    def flaky(conn, state, *, prefix=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("the derived view could not be rebuilt")
        return real_rebuild(conn, state, prefix=prefix)

    db_module.rebuild = flaky
    try:
        outcome = asyncio.run(registry.claim_day(
            "vidit", t=NOW.stamp, day=TODAY, records=[day_marker]
        ))
    finally:
        db_module.rebuild = real_rebuild
    assert outcome == "claimed"
    with Store(tmp_path / "vidit") as store:
        assert touch_module.day_of(store.fold().spoke) == TODAY


@pytest.mark.cap8_silence
def test_a_derived_view_behind_the_log_does_not_lose_the_day(
    registry, tmp_path
):
    """A crash between the append and the rebuild leaves SQLite behind.

    ``Store.append`` writes the line and *then* rebuilds, so the window is
    real. Both rules that read the view — the day marker and the nagging bound
    — would answer *never*, and Half would send a second message. The surface
    reads the log, which is the authority (AD-3).

    The view is left **stale rather than empty**: ``Store.conn`` rebuilds an
    empty database on open, which is a repair the log makes for free, so
    deleting the file proves nothing about this rule.
    """
    a_main(tmp_path)
    channel = FakeChannel()

    # The append lands; the rebuild does not.
    with Store(tmp_path / "vidit") as store:
        store.log.append(make_record(
            Op.TOUCH, f"tc_{stamp(NOON - 3600)}", stamp(NOON - 3600),
            **touch_module.spoke(day=TODAY, origin=TENSION_ORIGIN,
                                 loops=("swim-weekly",)),
        ))
        assert store.state().spoke is None, "the derived view is not stale"
        assert touch_module.day_of(store.fold().spoke) == TODAY

    registry.close()
    fresh = ActorRegistry(tmp_path)
    try:
        outcome = asyncio.run(
            MorningSurface(ledger=fresh, channel=channel).surface(
                "vidit", now=NOW,
                candidates=[Candidate(origin=TENSION_ORIGIN,
                                      entries=("b_1", "b_2"))],
            )
        )
    finally:
        fresh.close()
    assert outcome == Silence(ALREADY_TODAY), (
        "a derived view behind the log bought a second message"
    )
    assert channel.sent == []


@pytest.mark.cap8_silence
def test_a_ceiling_the_derived_view_has_not_caught_up_to_still_caps(
    registry, tmp_path
):
    """The sharper half of *read the log, not the view* (AD-3, AD-28).

    The day marker is protected twice — the claim re-reads the log — so a stale
    view costs nothing there. The **ceiling** is read once, and a cap that
    landed in the log but not yet in SQLite would let a capped main be spoken
    to: the window AD-28 exists to close, reopened by the derived store rather
    than by the log.
    """
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        store.log.append(make_record(
            Op.CEILING, "c_1", stamp(NOON - 60), rung=str(License.BEHAVE),
            because="a crisis entry whose rebuild had not landed",
        ))
        assert store.state().ceiling is None, "the derived view is not stale"
        assert store.fold().ceiling == str(License.BEHAVE)

    registry.close()
    fresh = ActorRegistry(tmp_path)
    channel = FakeChannel()
    try:
        outcome = asyncio.run(
            MorningSurface(ledger=fresh, channel=channel).surface(
                "vidit", now=NOW,
                candidates=[Candidate(origin=TENSION_ORIGIN,
                                      entries=("b_1", "b_2"))],
            )
        )
    finally:
        fresh.close()
    assert outcome == Silence(NOTHING_MAY_BE_SAID), (
        "a cap the derived view had not caught up to was ignored"
    )
    assert channel.sent == []


@pytest.mark.cap8_silence
def test_a_raise_the_derived_view_has_not_caught_up_to_still_bounds(
    registry, tmp_path
):
    """And the bound, for the same reason.

    A raise in the log but not yet in the view reads as *never raised*, so the
    loop is nagged — the day is claimed either way, so nothing else notices.
    """
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        store.log.append(make_record(
            Op.TOUCH, "tc_earlier", stamp(NOON - 2 * DAY),
            **touch_module.raised("swim-weekly", origin=TENSION_ORIGIN),
        ))
        assert store.state().touches == {}, "the derived view is not stale"

    registry.close()
    fresh = ActorRegistry(tmp_path)
    channel = FakeChannel()
    try:
        outcome = asyncio.run(
            MorningSurface(ledger=fresh, channel=channel).surface(
                "vidit", now=NOW,
                candidates=[Candidate(origin=TENSION_ORIGIN,
                                      entries=("b_1", "b_2"))],
            )
        )
    finally:
        fresh.close()
    assert outcome == Silence(NOTHING_TO_SAY), "a stale view nagged a loop"
    assert channel.sent == []


@pytest.mark.cap8_silence
def test_a_failed_send_spends_the_day_and_is_not_retried(registry, tmp_path):
    from half.errors import SendFailed

    a_main(tmp_path)
    channel = FakeChannel(fail=SendFailed("the platform said no",
                                          retryable=False))
    assert surface(registry, channel) == Silence(UNSENT)
    assert channel.sent == []
    assert touch_module.day_of(view_of(registry).spoke) == TODAY

    assert surface(registry, FakeChannel(), candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ]) == Silence(ALREADY_TODAY)


@pytest.mark.cap8_silence
def test_a_channel_that_carried_nothing_is_not_a_message(registry, tmp_path):
    """An adapter may report non-delivery by return value rather than by
    raising — ``TelegramChannel.send`` answers ``parts=0`` for a body the
    platform would reject. Discarding the result recorded that as a message
    sent and spent the day for it."""
    a_main(tmp_path)
    channel = FakeChannel(parts=0)
    assert surface(registry, channel) == Silence(UNSENT)


# ═════════════════════════════════════════════════════════════════════════════
# the pass and the surface, in that order
# ═════════════════════════════════════════════════════════════════════════════


def test_the_surface_runs_before_the_pass_reports_itself_incomplete(
    registry, tmp_path
):
    """A night with one failed append still moved nine other tensions."""
    from half.consolidate.pass_ import TensionPassIncomplete

    class Incomplete:
        async def evaluate(self, main_id, now):
            return PassResult(
                unrecorded=("x_9",),
                candidates=(Candidate(origin=TENSION_ORIGIN,
                                      entries=("b_1", "b_2")),),
            )

    a_main(tmp_path)
    channel = FakeChannel()
    work = MorningPass(
        consolidate=Incomplete(),
        surface=MorningSurface(ledger=registry, channel=channel),
    )
    with pytest.raises(TensionPassIncomplete):
        asyncio.run(work.run("vidit", NOW))
    assert len(channel.sent) == 1


def test_a_complete_pass_surfaces_and_returns_none(registry, tmp_path):
    a_main(tmp_path)
    channel = FakeChannel()
    work = MorningPass(
        consolidate=TensionPass(ledger=registry),
        surface=MorningSurface(ledger=registry, channel=channel),
    )
    assert asyncio.run(work.run("vidit", NOW)) is None
    assert len(channel.sent) == 1


# ═════════════════════════════════════════════════════════════════════════════
# the shipped composition
# ═════════════════════════════════════════════════════════════════════════════


def test_the_surface_is_wired_into_the_shipped_composition_by_value(tmp_path):
    """*"Wired by value, not by keyword."*"""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    try:
        work = wiring.scheduler.work
        assert isinstance(work, MorningPass)
        assert isinstance(work.surface, MorningSurface)
        assert work.surface.ledger is wiring.registry
        assert work.surface.channel is wiring.channel
        # The counter is the process's, so every morning has somewhere to go.
        assert work.surface.mornings is wiring.mornings
    finally:
        wiring.registry.close()


def test_the_shipped_wiring_actually_sends_one_morning_message(tmp_path):
    """Run, not grepped: the object graph the product builds, a real store, a
    real tick, a real touch in a real log."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    a_main(tmp_path)
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    transport = FakeTransport()
    try:
        # The *transport* is replaced, never the adapter's ``send``: the
        # recipient rule (AD-25), the reachability check (AD-7) and the
        # chunking all live in the adapter.
        wiring.channel.transport = transport
        wiring.channel.reach.note_inbound("vidit", epoch=NOON - 3600)
        asyncio.run(wiring.registry.note_pass(
            "vidit", t=stamp(NOON - 600),
            fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC",
                    TOLD_ZONE: False},
        ))
        wiring.scheduler.clock = FrozenClock(at=NOON)
        assert asyncio.run(wiring.scheduler.tick()).ran == ("vidit",)
        assert len(transport.sent) == 1
        assert transport.sent[0][0] == "123", "sent somewhere that is not the main"
        view = view_of(wiring.registry)
        assert "swim-weekly" in view.touches
        assert touch_module.day_of(view.spoke) == TODAY
        assert wiring.mornings.sent == 1
    finally:
        wiring.registry.close()


def test_the_shipped_wiring_says_nothing_to_a_main_who_has_never_written(
    tmp_path
):
    """Telegram cannot open a conversation, and the surface asks (AD-7)."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    a_main(tmp_path)
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    transport = FakeTransport()
    try:
        wiring.channel.transport = transport
        assert wiring.channel.capability_query("vidit") is (
            Reachability.NEVER_CONTACTED
        )
        asyncio.run(wiring.registry.note_pass(
            "vidit", t=stamp(NOON - 600),
            fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC",
                    TOLD_ZONE: False},
        ))
        wiring.scheduler.clock = FrozenClock(at=NOON)
        assert asyncio.run(wiring.scheduler.tick()).ran == ("vidit",)
        assert transport.sent == []
    finally:
        wiring.registry.close()


# ═════════════════════════════════════════════════════════════════════════════
# what this story does not build
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.offline
@pytest.mark.cap8_structure
def test_no_model_is_reachable_from_the_surface_package():
    """*"No model call — composing the sentence is a later story."*

    Asserted structurally, because *"it does not call a model today"* decays
    the first time somebody reaches for one — and the reach would be invisible:
    a morning message composed by a model still looks like a morning message.
    """
    imported: set[str] = set()
    for path in sorted((ROOT / "half" / "surface").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    offenders = sorted(
        name for name in imported
        if name.startswith("half.model") or name in {"anthropic", "httpx"}
    )
    assert not offenders, f"the surface package can reach a model: {offenders}"


@pytest.mark.offline
@pytest.mark.cap8_structure
def test_the_surface_reaches_no_network_and_no_metric_path():
    """AD-21 and story 5b: no endorsement sampling and no trust-balance spend."""
    imported: set[str] = set()
    for path in sorted((ROOT / "half" / "surface").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
    assert not (imported & {"socket", "http", "urllib", "requests", "httpx",
                            "subprocess", "random"})
    assert "half.metrics" not in imported


def test_a_loop_transition_candidate_surfaces_through_the_same_path(
    registry, tmp_path
):
    """The other origin kinds are a real seam, not an aspiration."""
    a_main(tmp_path)
    channel = FakeChannel()
    outcome = surface(registry, channel, candidates=[
        Candidate(origin=Origin(kind=TOUCH_LOOP_TRANSITION, id="swim-weekly"),
                  entries=("b_1", "b_2"))
    ])
    assert isinstance(outcome, Surfaced)
    assert outcome.origin.kind == TOUCH_LOOP_TRANSITION
    assert view_of(registry).touches["swim-weekly"]["origin_kind"] == (
        TOUCH_LOOP_TRANSITION
    )
