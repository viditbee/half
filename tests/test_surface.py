"""CAP-8 story 10: the morning surface — one case per matrix row.

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test and handed over as a ``Now`` or a ``FrozenClock``,
which is the design under test: the scheduler is the one module allowed to know
what time it is and everything it calls takes that knowledge as an argument
(AD-30). A suite that used the real clock would pass this morning and be
irreproducible tomorrow — and *"at most one a day"* is a rule about days.

**Silence is asserted as the ordinary outcome, not as an error path.** Most of
the cases below end in nothing being sent, and each of them asserts that
nothing was logged as a failure, nothing was queued and nothing was retried.
The failure this story is written against is a Half that finds something to say
because saying nothing feels like a bug, so *"a quiet night produces silence"*
is a first-class case here and not a footnote to the interesting one.

**The gates are exercised in every ordering, not only in the one the
implementation happens to check first.** Story 9c's central rule was broken in
two orderings nobody had tested while its suite was green, and the same trap is
open here: five independent gates, each of which alone produces silence, and a
suite that only ever presents one at a time cannot tell whether the second
gate is doing anything. So the crisis / already-said / unreachable / nothing-
to-choose / nothing-may-be-said gates are swept pairwise, and the answer must
be silence for every pair in both orders.

**The ceiling is asserted as a property, not as a case.** The rule is *"a main
capped at `behave` receives nothing, without a special case for aftercare"*, so
what is tested is the sweep — every rung a record can be on, against every rung
a ceiling can be at — plus the structural fact that nothing in ``half/surface/``
can even ask whether an aftercare period is running. A single case with a
capped main passes just as happily against an ``if in_aftercare`` branch, which
is the implementation AD-28 exists to forbid.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.channel.port import Reachability
from half.civil import DAY
from half.consolidate.pass_ import TensionPass
from half.context.build import build as build_context
from half.governance import ladder
from half.governance.ladder import RUNGS, License, height, permitted
from half.loops import ledger as loops
from half.retrieval.port import Candidate as RankedBelief
from half.schedule.clock import FrozenClock, moment, stamp
from half.schedule.due import local_day, told
from half.store.ops import TOUCH_LOOP_TRANSITION, TOUCH_TENSION, Op
from half.store.records import NEXT_PASS_AT, TOLD_ZONE, ZONE
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.choose import Candidate, choose, eligible
from half.surface.morning import (
    ALREADY_TODAY,
    CRISIS,
    NOTHING_MAY_BE_SAID,
    NOTHING_TO_SAY,
    REASONS,
    SPEAKS_AT,
    SPOKEN_CHANNELS,
    MorningPass,
    MorningSurface,
    Silence,
    SurfaceLedger,
    Surfaced,
    UNRECORDED,
    UNSENT,
    speech,
)
from half.surface.touch import Origin
from half.tensions.states import STATE, TensionState

from tests.conftest import FakeTransport, seed_belief

pytestmark = pytest.mark.cap8

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the instant ``tests/test_pass.py``,
#: ``tests/test_schedule.py`` and ``tests/test_nagging.py`` all build from.
NOON = 1_788_264_000.0
NOW = moment(NOON)

SEEDED = "2026-08-09T00:00:00Z"
MINTED = "2026-08-10T00:00:00Z"
MOVED = "2026-08-11T00:00:00Z"

TENSION_ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")


# ── helpers ──────────────────────────────────────────────────────────────────


class FakeChannel:
    """The whole ``Channel`` surface the morning needs, so tests stay offline.

    ``capability_query`` is the port's own question and the only thing this
    module may learn about a platform (AD-7): the surface never discovers which
    platform it is on, so neither does this fake.
    """

    name = "fake"

    def __init__(self, reach=Reachability.OPEN, fail=None):
        self.reach = reach
        self.fail = fail
        self.sent: list[tuple[str, str]] = []
        self.queries: list[str] = []

    def capability_query(self, main_id):
        self.queries.append(main_id)
        return self.reach

    async def send(self, main_id, text):
        if self.fail is not None:
            raise self.fail
        self.sent.append((main_id, text))
        return None

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


#: One claim per seeded entry, sharing **no adjacent word pair** with any
#: other and containing no belief id.
#:
#: Both properties are load-bearing rather than decorative. AD-18's withholding
#: guard works on adjacent pairs, so two entries whose claims read *"claim
#: about b_1"* and *"claim about b_2"* share the pair ``claimabout`` — and an
#: `assert` entry beside a `behave` one is then correctly dropped from the
#: content channel, leaving every case below quietly testing an empty context
#: instead of the rule it names. Putting the id in the claim does it a second
#: way: ``b_2`` folds to the pair ``b2``, which the rendering's own
#: ``content[b_2]`` label then contains.
#:
#: A dictionary rather than a formula, so that adding an entry to a fixture
#: fails here by name instead of colliding by arithmetic.
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
    assert ident in CLAIMS, (
        f"add a claim for {ident} that shares no adjacent word pair with the "
        f"others; see CLAIMS"
    )
    return CLAIMS[ident]


def seed_entry(store, ident, *, loop="swim-weekly", rung=License.ASSERT,
               claim=None, t=SEEDED, support=None):
    """One belief on a loop, admitted through the ladder like production does."""
    return seed_belief(
        store, ident, t, subject="self",
        claim=claim if claim is not None else a_claim(ident),
        loop=loop, rung=rung, support=support or [f"s_{ident}"],
        topics=["swimming"],
    )


def seed_tension(store, *, ident="x_1", pair=("b_1", "b_2"), moves=None,
                 loop="swim-weekly", rungs=(License.ASSERT, License.BEHAVE)):
    """Two entries on one loop, a tension over them, evidence added to ``moves``.

    Shaped so the nightly pass computes a real transition: one side acquires a
    second source after the mint, which is what *widening* is.

    ``moves`` defaults to this tension's **own** first side rather than to a
    literal, which is not tidiness: a fixture seeding two tensions with a
    hard-coded ``("b_1",)`` re-states ``b_1`` under the second tension's loop,
    quietly moving that entry to a wanting it was never on.
    """
    moves = (pair[0],) if moves is None else moves
    held = dict(zip(pair, rungs))
    for side, rung in held.items():
        seed_entry(store, side, loop=loop, rung=rung)
    store.record(Op.TENSION, ident, MINTED, between=list(pair),
                 **{STATE: str(TensionState.FRESH)}, **ladder.admitted())
    for side in moves:
        # Re-stated at the rung it was already on. A re-append that dropped the
        # license would silently demote the entry to `behave`, and every case
        # below would then be testing a capped main by accident.
        seed_belief(store, side, MOVED, subject="self",
                    claim=a_claim(side), loop=loop,
                    rung=held.get(side, License.BEHAVE),
                    support=[f"s_{side}", f"s_more_{side}"], topics=["swimming"])


def a_main(root, main_id="vidit", **kwargs):
    """A main with one loop, one tension over two entries on it."""
    with Store(Path(root) / main_id) as store:
        seed_loop(store)
        seed_tension(store, **kwargs)


def run_pass(registry, main_id="vidit", now=NOW):
    return asyncio.run(TensionPass(ledger=registry).evaluate(main_id, now))


def surface(registry, channel, *, main_id="vidit", now=NOW, candidates=None):
    if candidates is None:
        candidates = run_pass(registry, main_id, now).candidates
    return asyncio.run(
        MorningSurface(ledger=registry, channel=channel).surface(
            main_id, now=now, candidates=candidates
        )
    )


def set_ceiling(registry, main_id, rung, *, t="2026-08-20T00:00:00Z"):
    asyncio.run(registry.hold_ceiling(
        main_id, to=rung, t=t, because="a test standing in for aftercare"
    ))


def tell_zone(registry, main_id, zone):
    """Record the zone the main told Half, through the ladder like production."""
    root = registry.root / main_id
    with Store(root) as store:
        fields = told(zone, support=["s_zone"])
        store.record(Op.ASSERT, "b_zone", "2026-08-01T00:00:00Z", **fields)
        record = store.state().beliefs["b_zone"]
        store.record(Op.ASSERT, "b_zone", "2026-08-01T00:00:00Z",
                     **ladder.promote(record, to=License.ASSERT,
                                      acknowledged=True))


def enter_crisis(registry, main_id):
    asyncio.run(registry.suspend_for_crisis(
        main_id, t="2026-08-31T00:00:00Z", tier="disclosure", score=2
    ))


def touches_of(registry, main_id="vidit"):
    state, _ = asyncio.run(registry.surface_view(main_id))
    return state.touches


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
    silence as a fault, which is exactly the reading AD-27 forbids.
    """
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_entry(store, "b_1")
    channel = FakeChannel()

    with caplog.at_level(logging.DEBUG):
        result = run_pass(registry)
        outcome = surface(registry, channel, candidates=result.candidates)

    assert result.quiet and result.candidates == ()
    assert outcome == Silence(NOTHING_TO_SAY)
    assert channel.sent == []
    assert touches_of(registry) == {}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.cap8_silence
def test_a_pass_that_moved_nothing_produces_no_candidates(registry, tmp_path):
    """*Most* days are silent, and this is why: a candidate exists only for a
    tension the pass actually moved, so an unchanged tension — the ordinary
    result of an ordinary night — produces nothing to choose from."""
    a_main(tmp_path, moves=())
    first = run_pass(registry)
    assert first.moved and first.candidates, "fixture moved nothing"
    # Re-run against the same instant: the log now says what it computed to.
    second = run_pass(registry)
    assert second.unchanged and second.candidates == ()
    assert surface(registry, FakeChannel(),
                   candidates=second.candidates) == Silence(NOTHING_TO_SAY)


@pytest.mark.cap8_silence
def test_the_surface_reads_no_ledger_when_there_is_nothing_to_say(
    registry, tmp_path
):
    """A quiet morning asks no platform and writes nothing.

    The mode is checked first — it is the one rule that may never be second-
    guessed — so a store is opened; what must not happen is a platform being
    asked whether Half may speak when there is nothing to say, or a raise being
    recorded for a morning on which nothing was raised.
    """
    a_main(tmp_path)
    channel = FakeChannel()
    with Store(tmp_path / "vidit") as store:
        before = {p: p.read_bytes() for p in store.log.shards()}

    assert surface(registry, channel, candidates=()) == Silence(NOTHING_TO_SAY)
    assert channel.queries == [], "a quiet morning asked the platform anyway"
    assert touches_of(registry) == {}
    with Store(tmp_path / "vidit") as store:
        assert {p: p.read_bytes() for p in store.log.shards()} == before


# ═════════════════════════════════════════════════════════════════════════════
# matrix: one good thing / two good things
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
    assert outcome.loop == "swim-weekly"
    assert len(channel.sent) == 1
    assert channel.sent[0][0] == "vidit"
    assert channel.sent[0][1] == outcome.text


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
    assert len(touches_of(registry)) == 1, "two loops were raised in one morning"


def test_the_choice_is_the_loop_that_has_been_quietest_in_its_own_periods(
    registry, tmp_path
):
    """The ordering, and it is stated in each loop's own unit.

    A months-loop silent for two months and a weeks-loop silent for two weeks
    are both two periods quiet; the months-loop silent for a *year* is twelve.
    Ranking in raw days would put a days-loop that missed a fortnight above a
    farmland loop nobody has touched since 2020.
    """
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "swim-weekly", timescale="weeks",
                  last_movement="2026-08-25", ident="l_1")
        seed_loop(store, "buy-farmland", timescale="years",
                  last_movement="2020-01-01", ident="l_2")
        seed_tension(store, ident="x_1", pair=("b_1", "b_2"), loop="swim-weekly")
        seed_tension(store, ident="x_2", pair=("b_3", "b_4"), loop="buy-farmland")

    outcome = surface(registry, FakeChannel())
    assert isinstance(outcome, Surfaced)
    assert outcome.loop == "buy-farmland"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: already sent today / local day
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_second_trigger_the_same_local_day_sends_nothing(registry, tmp_path):
    """Matrix: *already sent today*. One a day, per main."""
    a_main(tmp_path)
    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)

    later = moment(NOON + 6 * 3600)
    assert surface(registry, channel, now=later,
                   candidates=[Candidate(origin=TENSION_ORIGIN,
                                         entries=("b_1", "b_2"))]) == Silence(
        ALREADY_TODAY
    )
    assert len(channel.sent) == 1


def test_the_next_local_day_may_send_again(registry, tmp_path):
    """The other side: one a day is a bound, not a silencing."""
    a_main(tmp_path)
    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)

    tomorrow = moment(NOON + DAY)
    outcome = surface(
        registry, channel, now=tomorrow,
        candidates=[Candidate(origin=Origin(kind=TOUCH_TENSION, id="x_1"),
                              entries=("b_1", "b_2"))],
    )
    # The weeks-loop was raised yesterday, so the *bound* refuses even though
    # the day has turned — which is the two rules composing correctly.
    assert outcome == Silence(NOTHING_TO_SAY)
    assert len(channel.sent) == 1

    # Past the loop's own period, the day having turned, it sends again.
    next_week = moment(NOON + 8 * DAY)
    again = surface(
        registry, channel, now=next_week,
        candidates=[Candidate(origin=Origin(kind=TOUCH_TENSION, id="x_1"),
                              entries=("b_1", "b_2"))],
    )
    assert isinstance(again, Surfaced)
    assert len(channel.sent) == 2


@pytest.mark.cap8_silence
def test_a_day_is_a_local_civil_day_and_not_twenty_four_hours(
    registry, tmp_path
):
    """Matrix: *local day*, and the case that tells the two readings apart.

    Two sends ten minutes apart across local midnight are two days' worth; two
    sends nearly a day apart *inside* one local day are not. A twenty-four-hour
    window gets both of them wrong, in opposite directions, and a suite that
    only ever tests intervals far from midnight cannot see either.
    """
    a_main(tmp_path)
    tell_zone(registry, "vidit", "Asia/Kolkata")
    channel = FakeChannel()

    # 2026-09-01T18:25Z is 2026-09-01T23:55 in Kolkata (UTC+5:30).
    late = moment(NOON + 6 * 3600 + 25 * 60)
    assert isinstance(surface(registry, channel, now=late), Surfaced)

    # Twenty minutes later, but 2026-09-02 local: a new day.
    just_after = moment(late.epoch + 20 * 60)
    assert surface(
        registry, channel, now=just_after,
        candidates=[Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))],
    ) == Silence(NOTHING_TO_SAY), "the loop's own bound should refuse, not the day"

    # And the reverse: 23 hours later is still 2026-09-02 local, so the
    # one-a-day rule holds even though a rolling window would have lapsed.
    with Store(tmp_path / "vidit") as store:
        store.record(Op.TOUCH, "tc_day2", stamp(just_after.epoch),
                     **touch_module.fields("buy-farmland",
                                           origin=TENSION_ORIGIN))
        seed_loop(store, "buy-farmland", timescale="years",
                  last_movement="2020-01-01", ident="l_9")
    nearly_a_day_later = moment(just_after.epoch + 23 * 3600)
    assert surface(
        registry, channel, now=nearly_a_day_later,
        candidates=[Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))],
    ) == Silence(ALREADY_TODAY)


def test_two_mains_in_different_zones_get_their_own_day_boundary(
    registry, tmp_path
):
    """Matrix: *local day*, two mains. Told, never inferred (AD-9).

    One instant, two mains, two answers — which is only possible if the day
    boundary is each main's own. The window is chosen so that exactly one of
    the two zones has turned over, and the fact that it has is asserted
    directly through the same function the surface uses, so this case cannot
    pass by accident on a day the offsets happen to line up.
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
    # Kiritimati: a new local day, so the one-a-day rule no longer applies and
    # the loop's own bound is what refuses. Niue: the same local day, so the
    # rule applies and nothing else is even asked.
    assert surface(registry, channel, main_id="vidit", now=later,
                   candidates=pair) == Silence(NOTHING_TO_SAY)
    assert surface(registry, channel, main_id="asha", now=later,
                   candidates=pair) == Silence(ALREADY_TODAY)
    assert channel.sent and len(channel.sent) == 2


@pytest.mark.cap8_silence
def test_a_last_touch_whose_stamp_cannot_be_read_fails_closed(
    registry, tmp_path
):
    """The rule is an Always, so an unmeasurable stamp is treated as *today*.

    Reading it as *yesterday* would buy a second unprompted message on a day
    one was already sent, which is the one thing the rule forbids. Reachable
    only from a log somebody edited by hand — the stamp is written from the
    tick's own instant and refused at the append if it is not one.
    """
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        # ISO-8601 in shape and not a real instant: the thirty-first of
        # February. ``half.civil.instant`` refuses it, which is the case under
        # test, and the shard name is still readable, which is what lets it
        # into a log at all.
        store.record(Op.TOUCH, "tc_bad", "2026-02-31T00:00Z",
                     **touch_module.fields("swim-weekly",
                                           origin=TENSION_ORIGIN))
    channel = FakeChannel()
    assert surface(registry, channel) == Silence(ALREADY_TODAY)
    assert channel.sent == []


# ═════════════════════════════════════════════════════════════════════════════
# matrix: no traceable origin
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
    outcome = surface(
        registry, channel,
        candidates=[Candidate(origin=origin, entries=("b_1", "b_2"))],
    )
    assert outcome == Silence(NOTHING_TO_SAY)
    assert channel.sent == []


def test_every_surfaced_thing_names_what_it_came_from(registry, tmp_path):
    """*"Given any surfaced thing, when it is examined, then it cites the
    tension, loop transition or ingested item it came from."*

    On the value, and — because a value is gone at the end of the process — in
    the log, which is where it can still be examined tomorrow.
    """
    a_main(tmp_path)
    outcome = surface(registry, FakeChannel())
    assert isinstance(outcome, Surfaced)
    assert outcome.origin.traceable

    held = touches_of(registry)["swim-weekly"]
    assert touch_module.origin_of(held) == outcome.origin


def test_a_candidate_over_an_entry_the_ledger_no_longer_holds_is_dropped(
    registry, tmp_path
):
    """A correction removed the entry, so there is nothing to cite and nothing
    that could honestly be quoted."""
    a_main(tmp_path)
    with Store(tmp_path / "vidit") as store:
        store.record(Op.RETRACT, "r_1", "2026-08-30T00:00:00Z", target="b_1")
        store.record(Op.RETRACT, "r_2", "2026-08-30T00:00:01Z", target="b_2")
    assert surface(
        registry, FakeChannel(),
        candidates=[Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))],
    ) == Silence(NOTHING_TO_SAY)


def test_a_candidate_whose_entries_sit_on_no_loop_is_not_surfaced(
    registry, tmp_path
):
    """A surface that touches no wanting is bounded by nothing, and unbounded
    is the failure the nagging bound exists to prevent."""
    with Store(tmp_path / "vidit") as store:
        seed_entry(store, "b_1", loop=None)
        seed_entry(store, "b_2", loop=None, rung=License.BEHAVE)
    assert surface(
        registry, FakeChannel(),
        candidates=[Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))],
    ) == Silence(NOTHING_TO_SAY)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: aftercare — the ceiling, swept, with no branch for it anywhere
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_main_capped_at_behave_receives_no_mirror(registry, tmp_path):
    """Matrix: *aftercare*. Silence, through the ladder rather than a branch.

    The set-up is the one aftercare produces — a crisis entry reversed so the
    mode is closed, with the cap left where the entry put it — and the surface
    is not told any of that. It sees a main whose records all resolve to
    `behave` and says nothing.
    """
    a_main(tmp_path)
    set_ceiling(registry, "vidit", License.BEHAVE)
    channel = FakeChannel()

    outcome = surface(registry, channel)
    assert outcome == Silence(NOTHING_MAY_BE_SAID)
    assert channel.sent == []
    assert touches_of(registry) == {}, "a capped main's loop was still raised"


@pytest.mark.cap8_silence
@pytest.mark.parametrize("rung", list(RUNGS), ids=[str(r) for r in RUNGS])
def test_nothing_at_any_rung_survives_a_behave_ceiling(
    registry, tmp_path, rung
):
    """The sweep, and it is what makes the last case a property rather than an
    anecdote.

    Parameterised over ``ladder.RUNGS`` rather than over three literals, so a
    fourth rung added to the ladder is swept the day it exists — and cannot be
    the one rung that walks past the cap.
    """
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
    """The whole ladder against the whole ceiling, and one rule joining them.

    This is the property AD-28 asks for, stated as an equality rather than as a
    list of cases: what a surface does is decided by ``permitted(record,
    ceiling)`` against ``SPEAKS_AT``, and by nothing else. Every ``(own, cap)``
    pair is checked, so there is no rung at which the cap is applied and no
    rung at which it is skipped.
    """
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_tension(store, rungs=(own, own))
    if cap is not ladder.TOP:
        set_ceiling(registry, "vidit", cap)

    channel = FakeChannel()
    outcome = surface(registry, channel)

    state, ceiling = asyncio.run(registry.surface_view("vidit"))
    expected = any(
        height(permitted(state.beliefs[ident], ceiling=ceiling))
        >= height(SPEAKS_AT)
        for ident in ("b_1", "b_2")
    )
    assert isinstance(outcome, Surfaced) is expected
    assert bool(channel.sent) is expected


def test_the_channels_a_surface_speaks_from_are_the_ones_the_builder_fills():
    """``SPEAKS_AT`` and ``speech`` must agree with what ``build`` actually
    does, or the surface speaks from a rung it may not.

    Swept over every rung, through the *real* builder rather than a table
    restating it, so a channel changing hands in ``half.context.build`` fails
    here by name instead of quietly widening what a morning may say.
    """
    for rung in RUNGS:
        belief = {"id": "b_1", "claim": "a claim", "loop": "swim-weekly",
                  "license": str(rung), "support": ["s_1"],
                  "known_to_main": True}
        context = build_context(
            [RankedBelief(id="b_1", claim="a claim", prefix="", bm25=None,
                          belief=belief)],
            now=NOW.stamp, ceiling=None,
        )
        permitted_rung = permitted(belief, ceiling=None)
        assert bool(speech(context)) is (
            height(permitted_rung) >= height(SPEAKS_AT)
        ), f"speech() and SPEAKS_AT disagree at {rung}"

    assert SPOKEN_CHANNELS == ("content", "questions")
    assert SPEAKS_AT is License.ASK


@pytest.mark.cap8_silence
def test_the_surface_package_cannot_ask_whether_aftercare_is_running():
    """AD-28's structural half, and the reason the sweep above is not enough.

    A single behavioural case passes just as happily against an ``if
    in_aftercare: return Silence(...)`` branch — so what is asserted here is
    that no such branch can be *written*: the surface's own ledger protocol has
    four doors and none of them answers a question about aftercare, and nothing
    under ``half/surface/`` imports the module that could.

    This is a property of the import graph and of one protocol rather than a
    list of forbidden spellings: any new branch that wanted to know would have
    to widen one or the other, and both fail by name.
    """
    doors = {
        name for name in dir(SurfaceLedger)
        if not name.startswith("_")
    }
    assert doors == {"crisis_open", "zone_records", "surface_view", "note_touch"}

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
    assert not offenders, (
        f"half/surface/ can reach {offenders}; the ceiling is what makes "
        f"aftercare silent (AD-28), and a surface that can ask about aftercare "
        f"is a surface the next one will forget to teach"
    )


@pytest.mark.cap8_silence
def test_no_license_is_resolved_in_the_surface_without_a_ceiling():
    """Every route to a rung passes a cap, asserted over the package.

    The set of functions that decide a rung is **derived from the ladder
    itself** — every public function whose return annotation is a ``License`` —
    rather than listed here, so a new resolver added to ``half.governance``
    is covered on the day it is written. ``build`` joins them explicitly: it
    does not return a rung but it applies one, and it is the door this package
    actually uses.

    Functions that cannot take a ceiling (``own_rung``, ``rung_of``) therefore
    fail this rule automatically if the surface ever calls one, which is
    correct: an uncapped rung is the bypass AD-28 exists to prevent.
    """
    resolvers = {
        name
        for name, obj in vars(ladder).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and "License" in str(inspect.signature(obj).return_annotation)
    }
    resolvers.add("build")
    assert {"permitted", "own_rung", "rung_of"} <= resolvers, (
        "the resolver set is derived from the ladder and came back too small"
    )

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
    assert not offenders, (
        f"a license is resolved without a ceiling at {offenders} (AD-28)"
    )


@pytest.mark.cap8_silence
def test_the_uncapped_resolver_scan_catches_the_call_it_exists_for(tmp_path):
    """Non-vacuity for the scan above, through the same shape it looks for."""
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        "def surface(candidate):\n"
        "    return build(candidate, now='x')\n",
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
    """Matrix: *behave material*. AD-18, at the one surface that speaks first.

    The `behave` belief is in the context — it is what the withholding guard
    measures every other line against — and none of its wording reaches the
    wire. Asserted on the bytes that were actually sent, which is the only
    place the claim can be checked.
    """
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
    outcome = surface(registry, channel)
    assert isinstance(outcome, Surfaced)

    sent = channel.sent[0][1]
    for fragment in ("avoiding", "brother", "conversation"):
        assert fragment not in sent, (
            f"a behave claim's wording reached the wire: {fragment!r}"
        )
    assert "has swum twice this month" in sent


def test_a_surface_whose_only_material_is_behave_says_nothing(
    registry, tmp_path
):
    """A directive shapes; it is not a message. A context of directives alone
    is silence rather than a note about topics nobody asked about."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store)
        seed_tension(store, rungs=(License.BEHAVE, License.BEHAVE))
    channel = FakeChannel()
    assert surface(registry, channel) == Silence(NOTHING_MAY_BE_SAID)
    assert channel.sent == []


def test_the_wire_carries_no_directive_line(registry, tmp_path):
    """The rendering a surface sends is the sayable channels and nothing else.

    A directive is internal shaping vocabulary aimed at a model; putting it on
    the wire would be Half telling its main what it has decided to be careful
    about.
    """
    a_main(tmp_path)
    channel = FakeChannel()
    assert isinstance(surface(registry, channel), Surfaced)
    assert "directive[" not in channel.sent[0][1]


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
    assert channel.sent == []
    assert channel.queries == [], "a main in the mode was offered to a platform"
    assert touches_of(registry) == {}


@pytest.mark.cap8_silence
def test_the_scheduler_also_refuses_to_run_the_pass_for_a_main_in_the_mode(
    registry, tmp_path
):
    """Two independent refusals, which is what CAP-12 asks for: the mode is
    checked before the pass runs *and* before anything is sent, so removing
    either one still leaves a main in the mode unreachable by this path."""
    from half.schedule.tick import Scheduler

    a_main(tmp_path)
    enter_crisis(registry, "vidit")
    channel = FakeChannel()
    asyncio.run(registry.note_pass(
        "vidit", t=stamp(NOON - 600),
        fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC", TOLD_ZONE: False},
    ))
    scheduler = Scheduler(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=NOON),
        work=MorningPass(
            consolidate=TensionPass(ledger=registry),
            surface=MorningSurface(ledger=registry, channel=channel),
        ),
    )
    result = asyncio.run(scheduler.tick())
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

    Nothing is queued for later either: the touch is not written, so tomorrow's
    surface is free to choose again from tomorrow's pass rather than from a
    backlog of yesterday's thoughts.
    """
    a_main(tmp_path)
    channel = FakeChannel(reach=reach)
    with caplog.at_level(logging.DEBUG):
        outcome = surface(registry, channel)

    assert outcome == Silence(str(reach))
    assert outcome.reason in REASONS
    assert channel.sent == []
    assert touches_of(registry) == {}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ═════════════════════════════════════════════════════════════════════════════
# the gates, in every ordering
# ═════════════════════════════════════════════════════════════════════════════


#: Each gate, as a set-up that alone produces silence. Named so a failure says
#: which pair broke, and swept pairwise below — because a suite that only ever
#: presents one gate at a time cannot tell whether the second one is doing
#: anything. Story 9c's central rule was broken in two orderings nobody had
#: tested while its suite was green.
def _gate_crisis(registry, tmp_path, channel):
    enter_crisis(registry, "vidit")


def _gate_already_today(registry, tmp_path, channel):
    with Store(tmp_path / "vidit") as store:
        store.record(Op.TOUCH, "tc_earlier", stamp(NOON - 3600),
                     **touch_module.fields("learn-tabla",
                                           origin=TENSION_ORIGIN))
        seed_loop(store, "learn-tabla", timescale="months", ident="l_tabla")


def _gate_unreachable(registry, tmp_path, channel):
    channel.reach = Reachability.WINDOW_CLOSED


def _gate_capped(registry, tmp_path, channel):
    set_ceiling(registry, "vidit", License.BEHAVE)


def _gate_nagging(registry, tmp_path, channel):
    with Store(tmp_path / "vidit") as store:
        store.record(Op.TOUCH, "tc_recent", stamp(NOON - 2 * DAY),
                     **touch_module.fields("swim-weekly",
                                           origin=TENSION_ORIGIN))


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

    The *reason* legitimately depends on which gate is asked first — that is
    what a reason is for — so what is asserted is the outcome and the two
    facts that must hold whatever the reason: nothing was sent, and nothing was
    recorded as raised.
    """
    a_main(tmp_path)
    channel = FakeChannel()
    GATES[first](registry, tmp_path, channel)
    if second != first:
        GATES[second](registry, tmp_path, channel)
    # Two of the gates are themselves a raise, so *"nothing was recorded"* is a
    # comparison against what the set-up left, not against emptiness.
    before = touches_of(registry)

    outcome = surface(registry, channel)
    assert isinstance(outcome, Silence), (
        f"{first} + {second} produced a message"
    )
    assert outcome.reason in REASONS
    assert channel.sent == []
    assert touches_of(registry) == before, "a silent morning still raised a loop"


@pytest.mark.cap8_silence
@pytest.mark.parametrize("gate", sorted(GATES))
def test_each_gate_alone_silences_a_morning_that_would_otherwise_speak(
    registry, tmp_path, gate
):
    """The other half of the non-vacuity: without any gate this fixture speaks,
    and with exactly one it does not."""
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
    """Matrix: *missed day*. No catch-up, ever.

    The due time is a week stale, so the tick classifies the main as *missed*,
    advances them forward and runs nothing. What this case adds beyond story
    9a's is that the days that went by leave no backlog: on the next tick that
    *does* run, exactly one message is sent, not seven.
    """
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
    assert channel.sent == []
    assert touches_of(registry) == {}

    # The next window that is actually due sends exactly one thing.
    due_at = registry.schedule_record("vidit")[NEXT_PASS_AT]
    from half.civil import instant

    caught_up = asyncio.run(Scheduler(
        registry=registry, mains=("vidit",), root=tmp_path,
        clock=FrozenClock(at=instant(due_at) + 30), work=work,
    ).tick())
    assert caught_up.ran == ("vidit",)
    assert len(channel.sent) == 1, "a missed week arrived at once"


def test_the_same_log_and_the_same_now_choose_identically(registry, tmp_path):
    """Matrix: *determinism*. Two builds reading one log pick the same thing.

    Asserted on ``choose`` rather than on the whole surface, because the whole
    surface writes — so running it twice is a different question. This is the
    choice itself, over one state and one instant.
    """
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
    state, _ = asyncio.run(registry.surface_view("vidit"))
    args = dict(beliefs=state.beliefs, loops=state.loops,
                touches=state.touches, now=NOW.stamp)

    first = choose(candidates, **args)
    second = choose(list(reversed(candidates)), **args)
    assert first == second, "the choice depended on the order it was handed"
    assert first is not None

    # And the whole ranking, not only its head — a total order or nothing.
    assert (
        [c.loop for c in eligible(candidates, **args)]
        == [c.loop for c in eligible(list(reversed(candidates)), **args)]
    )


def test_the_choice_does_not_depend_on_dict_iteration_order(registry, tmp_path):
    """Two candidates that tie on silence are separated by their ids, never by
    whichever the fold happened to yield first."""
    with Store(tmp_path / "vidit") as store:
        seed_loop(store, "a-loop", timescale="weeks",
                  last_movement="2026-08-01", ident="l_1")
        seed_loop(store, "b-loop", timescale="weeks",
                  last_movement="2026-08-01", ident="l_2")
        seed_tension(store, ident="x_1", pair=("b_1", "b_2"), loop="a-loop")
        seed_tension(store, ident="x_2", pair=("b_3", "b_4"), loop="b-loop")

    state, _ = asyncio.run(registry.surface_view("vidit"))
    candidates = run_pass(registry).candidates
    args = dict(beliefs=state.beliefs, loops=state.loops,
                touches=state.touches, now=NOW.stamp)
    assert choose(candidates, **args).loop == "a-loop"
    assert choose(list(reversed(candidates)), **args).loop == "a-loop"


@pytest.mark.cap8_silence
def test_one_mains_unreadable_record_does_not_stop_the_pass(
    registry, tmp_path, caplog
):
    """Matrix: *one main fails*. Counted; other mains unaffected."""

    class Broken:
        def crisis_open(self, main_id):
            return False

        def zone_records(self, main_id):
            return ()

        async def surface_view(self, main_id):
            raise OSError("the store could not be read")

        async def note_touch(self, main_id, *, t, fields):  # pragma: no cover
            raise AssertionError("nothing should be written")

    channel = FakeChannel()
    broken = MorningSurface(ledger=Broken(), channel=channel)
    with caplog.at_level(logging.ERROR):
        outcome = asyncio.run(broken.surface(
            "vidit", now=NOW,
            candidates=[Candidate(origin=TENSION_ORIGIN, entries=("b_1",))],
        ))
    assert isinstance(outcome, Silence)
    assert channel.sent == []
    # AD-22: the type and nothing else — never the message, which routinely
    # quotes the value that caused it.
    assert all("could not be read" not in r.getMessage()
               for r in caplog.records)


def test_a_surface_that_raises_never_fails_the_tick(registry, tmp_path):
    """The surface is best-effort; the pass's own completeness is not. A main
    whose morning could not be read is a main who was sent nothing, which is a
    first-class outcome and not a tick failure."""
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
# the touch is written before the send, and the day is spent either way
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap8_silence
def test_a_touch_that_cannot_be_recorded_stops_the_send(registry, tmp_path):
    """*"A surface whose 'already said something today' marker could not be
    written has not earned the right to send."*

    The same asymmetry ``Scheduler._advance`` makes for a due time, and for the
    same reason: at-most-once is the only semantics compatible with *"at most
    one unprompted message a day"*.
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

        async def note_touch(self, main_id, *, t, fields):
            raise OSError("no space left on device")

    a_main(tmp_path)
    channel = FakeChannel()
    outcome = asyncio.run(
        MorningSurface(ledger=NoWrite(registry), channel=channel).surface(
            "vidit", now=NOW, candidates=run_pass(registry).candidates
        )
    )
    assert outcome == Silence(UNRECORDED)
    assert channel.sent == []


@pytest.mark.cap8_silence
def test_a_failed_send_spends_the_day_and_is_not_retried(registry, tmp_path):
    """The other side of the ordering. A failed send costs one message; a retry
    loop would cost the one-a-day rule."""
    from half.errors import SendFailed

    a_main(tmp_path)
    channel = FakeChannel(
        fail=SendFailed("the platform said no", retryable=False)
    )
    assert surface(registry, channel) == Silence(UNSENT)
    assert channel.sent == []
    assert "swim-weekly" in touches_of(registry), (
        "the day was not spent, so the same thing can be sent again today"
    )

    working = FakeChannel()
    assert surface(registry, working, candidates=[
        Candidate(origin=TENSION_ORIGIN, entries=("b_1", "b_2"))
    ]) == Silence(ALREADY_TODAY)


# ═════════════════════════════════════════════════════════════════════════════
# the pass and the surface, in that order
# ═════════════════════════════════════════════════════════════════════════════


def test_the_surface_runs_before_the_pass_reports_itself_incomplete(
    registry, tmp_path
):
    """A night with one failed append still moved nine other tensions, and
    those are worth saying.

    Raising first would make one failed write cost the main their morning as
    well as their transition — and the scheduler would count them under
    ``failed`` either way, so nothing is bought by it.
    """
    from half.consolidate.pass_ import PassResult, TensionPassIncomplete

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
    assert len(channel.sent) == 1, "a failed transition cost the main their morning"


def test_a_complete_pass_surfaces_and_returns_none(registry, tmp_path):
    """The ordinary night, through the ``Pass`` protocol the scheduler calls."""
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
    """*"Wired by value, not by keyword."*

    Story 6d's identical claim was satisfied by a case asserting a keyword's
    *name* appeared in the source, which passed with the value set to ``None``.
    So: the object ``build`` produced, holding *this* wiring's registry and
    *this* wiring's channel, by identity.
    """
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
    finally:
        wiring.registry.close()


def test_the_shipped_wiring_actually_sends_one_morning_message(tmp_path):
    """Run, not grepped. The object graph the product builds, a real store, a
    real tick, a real touch in a real log — the failure this asserts against is
    a surface reachable only from a test."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    a_main(tmp_path)
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    # The *transport* is replaced, never the adapter's ``send``: everything
    # this case is asserting — the recipient rule (AD-25), the reachability
    # check (AD-7), the chunking — lives in the adapter, and stubbing the
    # method would test a fake instead of the shipped one.
    transport = FakeTransport()

    try:
        wiring.channel.transport = transport
        wiring.channel.reach.note_inbound("vidit", epoch=NOON - 3600)
        asyncio.run(wiring.registry.note_pass(
            "vidit", t=stamp(NOON - 600),
            fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC",
                    TOLD_ZONE: False},
        ))
        wiring.scheduler.clock = FrozenClock(at=NOON)
        result = asyncio.run(wiring.scheduler.tick())
        assert result.ran == ("vidit",)
        assert len(transport.sent) == 1
        assert transport.sent[0][0] == "123", "sent to something other than the main"
        state, _ = asyncio.run(wiring.registry.surface_view("vidit"))
        assert "swim-weekly" in state.touches
    finally:
        wiring.registry.close()


def test_the_shipped_wiring_says_nothing_to_a_main_who_has_never_written(
    tmp_path
):
    """Telegram cannot open a conversation, and the surface asks rather than
    assuming (AD-7). With no inbound recorded, the morning is silent."""
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
def test_no_model_is_reachable_from_the_surface_package():
    """*"No model call — the model port exists, and composing the sentence is a
    later story."*

    Asserted structurally rather than trusted, because *"it does not call a
    model today"* is a property that decays the first time somebody reaches for
    one — and the reach would be invisible: a morning message composed by a
    model still looks like a morning message.
    """
    imported: set[str] = set()
    for path in sorted((ROOT / "half" / "surface").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
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
def test_the_surface_reaches_no_network_and_no_metric_path():
    """AD-21 and story 5b: no endorsement sampling and no trust-balance spend
    lives here. The surface decides what to say; measuring what it said is a
    different story with a different cost."""
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


def test_a_loop_transition_origin_is_in_the_vocabulary_but_unproduced():
    """The three origin kinds exist so that a later story hanging loop
    transitions or ingested items on the pass changes what fills
    ``PassResult.candidates`` and nothing else. Today the pass produces
    tensions only, and a candidate carrying either of the other two is
    surfaceable — which is what makes the seam real rather than aspirational.
    """
    assert Origin(kind=TOUCH_LOOP_TRANSITION, id="l_1").traceable


def test_a_loop_transition_candidate_surfaces_through_the_same_path(
    registry, tmp_path
):
    a_main(tmp_path)
    channel = FakeChannel()
    outcome = surface(
        registry, channel,
        candidates=[Candidate(origin=Origin(kind=TOUCH_LOOP_TRANSITION,
                                            id="l_1"),
                              entries=("b_1", "b_2"))],
    )
    assert isinstance(outcome, Surfaced)
    assert outcome.origin.kind == TOUCH_LOOP_TRANSITION
    assert touches_of(registry)["swim-weekly"]["origin_kind"] == (
        TOUCH_LOOP_TRANSITION
    )
