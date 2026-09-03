"""CAP-7 story 9c: the pass the scheduler runs — one case per matrix row.

**Nothing here waits for real time and nothing here reads a clock.** Every
instant is chosen by the test and handed to a ``FrozenClock`` or passed as a
``Now``, which is the whole point of the design under test: the scheduler is
the one module allowed to know what time it is, and everything it calls takes
that knowledge as an argument (AD-30). A suite that used the real clock would
pass tonight and be irreproducible tomorrow.

**The wiring is asserted by value, not by keyword.** Story 6d's identical claim
— *"the classifier reaches the shipped product"* — was satisfied by a case
asserting a keyword's *name* appeared in the source, which passed with the value
set to ``None``. So this asserts the object ``build`` produced, that it holds
*this* wiring's registry, that it is not ``Nothing``, and then drives a real
tick through the shipped composition and checks a transition landed in a real
log. A surface reachable only from a test is a surface nobody has run.

**Isolation is asserted at both levels.** The tick already isolates mains from
each other (AD-9); this story adds isolation *inside* one main, because a
tension whose record cannot be read is the ordinary case rather than the
exceptional one. One tension's failure costs that tension; one main's costs that
main; neither ends the pass.

**The pass costs nothing.** No model call, no network, no batch submission —
asserted structurally over the package rather than trusted, because *"it does
not call a model today"* is a property that decays the first time somebody
reaches for one.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.civil import instant
from half.consolidate.pass_ import (
    Ledger,
    PassResult,
    TensionPass,
    TensionPassIncomplete,
)
from half.errors import TensionError
from half.governance import ladder
from half.schedule.clock import FrozenClock, Now, moment, stamp
from half.schedule.tick import Nothing, Pass, Scheduler
from half.store.ops import SCHEMA_VERSION, Op
from half.store.records import Record
from half.store.records import NEXT_PASS_AT, TOLD_ZONE, ZONE
from half.store.store import Store
from half.tensions import ledger as tension_ledger
from half.tensions.states import STATE, TensionState
from half.tensions.widening import BETWEEN, NO_PAIR, PERSISTENCE_DAYS, RESOLVED_ALREADY

from tests.conftest import seed_belief

pytestmark = pytest.mark.cap7

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the same fixed instant ``tests/test_schedule.py``
#: builds from, so the two files' scenarios line up.
NOON = 1_788_264_000.0
NOW = moment(NOON)

MINTED = "2026-08-10T00:00:00Z"
SEEDED = "2026-08-09T00:00:00Z"
MOVED = "2026-08-11T00:00:00Z"


# ── helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def set_due(registry, main_id, at):
    """Put ``main_id``'s next due time at the epoch ``at``."""
    asyncio.run(
        registry.note_pass(
            main_id, t=stamp(at - 10),
            fields={NEXT_PASS_AT: stamp(at), ZONE: "UTC", TOLD_ZONE: False},
        )
    )


def seed_tension(store, *, minted=MINTED, moves=("b_1",), ident="x_1",
                 pair=("b_1", "b_2")):
    """Two entries, a tension over them, and evidence added to ``moves``."""
    for index, side in enumerate(pair):
        seed_belief(store, side, SEEDED, subject="self",
                    claim=f"entry number {index}", support=[f"s_{side}"])
    store.record(Op.TENSION, ident, minted, between=list(pair),
                 **{STATE: str(TensionState.FRESH)}, **ladder.admitted())
    for side in moves:
        seed_belief(store, side, MOVED, subject="self", claim="restated",
                    support=[f"s_{side}", f"s_more_{side}"])


def seeded_main(root, main_id, **kwargs):
    with Store(Path(root) / main_id) as store:
        seed_tension(store, **kwargs)


def past_the_gate(store, ident, t, **fields):
    """A tension record the append gate refuses, written straight to the log.

    A mint must name its pair — ``Store.append`` enforces it, because only the
    store knows which ids the fold has already seen — so a *pairless* tension is
    something only an older build's log can contain. The pass still has to read
    one, which is what these cases are for.
    """
    store.log.append(
        Record(op=Op.TENSION, id=ident, t=t,
               data={"t": t, "op": str(Op.TENSION), "id": ident,
                     "v": SCHEMA_VERSION, **fields})
    )
    store.rebuild()


def scheduler(registry, root, mains, *, work, at=NOON, **kwargs):
    return Scheduler(
        registry=registry, mains=tuple(mains), root=Path(root),
        clock=FrozenClock(at=at), work=work, **kwargs,
    )


def tensions_of(registry, main_id):
    return registry.tension_table(main_id)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: widening / persistent / closing — the pass appends the transition
# ═════════════════════════════════════════════════════════════════════════════


def test_evidence_on_one_side_moves_the_tension_to_widening(registry, tmp_path):
    """Matrix: *widening*. Evidence accumulates on one side only; the pass
    computes it and appends the transition."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))

    assert result.moved == {"x_1": TensionState.WIDENING.value}
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "widening"


def test_evidence_on_both_sides_moves_the_tension_to_closing(registry, tmp_path):
    seeded_main(tmp_path, "vidit", moves=("b_1", "b_2"))
    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result.moved == {"x_1": TensionState.CLOSING.value}


def test_both_sides_unmoved_past_the_window_moves_to_persistent(
    registry, tmp_path
):
    """Matrix: *fresh to persistent*. Time passes with both sides unmoved."""
    seeded_main(tmp_path, "vidit", moves=())
    assert instant(NOW.stamp) - instant(MINTED) > PERSISTENCE_DAYS * 86_400
    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result.moved == {"x_1": TensionState.PERSISTENT.value}


def test_the_transition_is_an_append_that_keeps_the_pair_and_the_license(
    registry, tmp_path
):
    """AD-3: a transition is an append, never an edit — and it is appended
    under the tension's own id, so the fold merges it over the mint."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    before = dict(tensions_of(registry, "vidit")["x_1"])
    asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))

    after = tensions_of(registry, "vidit")["x_1"]
    assert after[BETWEEN] == before[BETWEEN]
    assert after["license"] == before["license"] == str(ladder.FLOOR)
    assert after[STATE] != before[STATE]
    assert after["t"] == NOW.stamp

    with Store(tmp_path / "vidit") as store:
        appends = [r for r in store.log if r.op is Op.TENSION]
        assert len(appends) == 2, "the transition replaced rather than appended"


def test_the_pass_records_the_ticks_instant_and_never_reads_a_clock(
    registry, tmp_path
):
    """AD-30 at the seam that matters: the transition's stamp is the instant
    the tick was given, to the second."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    chosen = moment(NOON + 12_345)
    asyncio.run(TensionPass(ledger=registry).evaluate("vidit", chosen))
    assert tensions_of(registry, "vidit")["x_1"]["t"] == chosen.stamp


# ═════════════════════════════════════════════════════════════════════════════
# matrix: both sides stand / re-run — idempotence
# ═════════════════════════════════════════════════════════════════════════════


def test_nothing_changed_appends_nothing(registry, tmp_path):
    """Matrix: *both sides stand*. No transition is appended."""
    seeded_main(tmp_path, "vidit", minted=stamp(NOON - 86_400), moves=())
    with Store(tmp_path / "vidit") as store:
        before = {p: p.read_bytes() for p in store.log.shards()}

    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result.moved == {} and result.unchanged == ("x_1",)
    assert result.quiet

    with Store(tmp_path / "vidit") as store:
        assert {p: p.read_bytes() for p in store.log.shards()} == before


def test_the_same_pass_twice_with_the_same_now_appends_nothing_the_second_time(
    registry, tmp_path
):
    """Matrix: *re-run*. The acceptance criterion — the states are identical
    and no second transition is appended.

    Idempotence is by construction rather than by a guard: the transition moves
    the tension's own stamp to ``now``, so on the second run nothing has
    accumulated since and the computed target is the state already held.
    """
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    work = TensionPass(ledger=registry)

    first = asyncio.run(work.evaluate("vidit", NOW))
    after_one = tensions_of(registry, "vidit")["x_1"]

    second = asyncio.run(work.evaluate("vidit", NOW))
    after_two = tensions_of(registry, "vidit")["x_1"]

    assert first.moved == {"x_1": "widening"}
    assert second.moved == {} and second.unchanged == ("x_1",)
    assert after_two == after_one

    with Store(tmp_path / "vidit") as store:
        assert len([r for r in store.log if r.op is Op.TENSION]) == 2


def test_a_third_and_fourth_run_still_append_nothing(registry, tmp_path):
    """The nightly pass runs every night for years. Once is not idempotent."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    work = TensionPass(ledger=registry)
    for _ in range(4):
        asyncio.run(work.evaluate("vidit", NOW))
    with Store(tmp_path / "vidit") as store:
        assert len([r for r in store.log if r.op is Op.TENSION]) == 2


def test_the_same_log_and_the_same_now_produce_the_same_states(
    registry, tmp_path
):
    """Two mains with byte-identical logs reach byte-identical tensions."""
    for main_id in ("vidit", "asha"):
        seeded_main(tmp_path, main_id, moves=("b_1",))
    work = TensionPass(ledger=registry)
    asyncio.run(work.evaluate("vidit", NOW))
    asyncio.run(work.evaluate("asha", NOW))
    one = tensions_of(registry, "vidit")["x_1"]
    other = tensions_of(registry, "asha")["x_1"]
    assert one == other


# ═════════════════════════════════════════════════════════════════════════════
# matrix: not computable — counted, state unchanged, never blocks the rest
# ═════════════════════════════════════════════════════════════════════════════


def test_a_tension_that_cannot_be_evaluated_is_counted_and_left_alone(
    registry, tmp_path
):
    """Matrix: *not computable*. Reported as such; state unchanged."""
    with Store(tmp_path / "vidit") as store:
        past_the_gate(store, "x_1", MINTED, **{STATE: "widening"})
        before = dict(store.state().tensions["x_1"])

    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result.moved == {}
    assert result.incomputable == {"x_1": NO_PAIR}
    assert tensions_of(registry, "vidit")["x_1"] == before


def test_one_incomputable_tension_never_blocks_the_others(registry, tmp_path):
    """The isolation this story adds *inside* a main. An unreadable record is
    the ordinary case, not the exceptional one."""
    with Store(tmp_path / "vidit") as store:
        seed_tension(store, ident="x_ok", pair=("b_1", "b_2"), moves=("b_1",))
        past_the_gate(store, "x_bad", MINTED, **{STATE: "fresh"})
        past_the_gate(store, "x_later", MINTED, **{STATE: "widening"})

    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result.moved == {"x_ok": "widening"}
    assert set(result.incomputable) == {"x_bad", "x_later"}
    assert result.seen == 3


def test_a_resolved_tension_is_counted_rather_than_skipped_silently(
    registry, tmp_path
):
    """*"There were four we did not look at"* is a fact the pass should be able
    to state; a tension quietly absent from every count is how a whole state
    stops being exercised."""
    with Store(tmp_path / "vidit") as store:
        seed_tension(store, moves=())
        store.record(Op.RETRACT, "c_1", MOVED, target="b_1")
        assert store.state().tensions["x_1"][STATE] == "resolved"

    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result.moved == {}
    assert result.incomputable == {"x_1": RESOLVED_ALREADY}
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "resolved"


def test_a_main_with_no_tensions_at_all_is_a_normal_quiet_pass(
    registry, tmp_path
):
    with Store(tmp_path / "vidit") as store:
        seed_belief(store, "b_1", SEEDED, subject="self", claim="swims")
    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result == PassResult()
    assert result.quiet and result.seen == 0


def test_a_failed_append_costs_that_tension_and_nothing_else(registry, tmp_path):
    """One tension's write failing must not cost this main the other nine —
    and nothing was recorded, so the next pass computes the same answer again."""
    with Store(tmp_path / "vidit") as store:
        seed_tension(store, ident="x_1", pair=("b_1", "b_2"), moves=("b_1",))
        seed_tension(store, ident="x_2", pair=("b_3", "b_4"), moves=("b_3",))

    class OneWriteFails:
        def __init__(self, inner):
            self.inner = inner

        async def tension_view(self, main_id):
            return await self.inner.tension_view(main_id)

        async def note_transition(self, main_id, *, tension_id, t, fields,
                                  was=None):
            if tension_id == "x_1":
                raise OSError("the disk is full")
            await self.inner.note_transition(
                main_id, tension_id=tension_id, t=t, fields=fields, was=was
            )

    result = asyncio.run(
        TensionPass(ledger=OneWriteFails(registry)).evaluate("vidit", NOW)
    )
    assert result.unrecorded == ("x_1",)
    assert result.moved == {"x_2": "widening"}
    assert not result.quiet
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "fresh"
    assert tensions_of(registry, "vidit")["x_2"][STATE] == "widening"


# ═════════════════════════════════════════════════════════════════════════════
# the read is one view, the write carries its premise, and neither is content
# ═════════════════════════════════════════════════════════════════════════════


def test_the_two_reads_are_one_read_under_the_mains_own_mutex(registry, tmp_path):
    """``evaluate``'s docstring claimed *"the reads happen first and together,
    so the plan is computed against one consistent view of the log"*. They were
    two unsynchronised reads of two different authorities — the tension table
    from the SQLite view, the history from the log file — with an inbound turn
    free to land between them.

    Asserted as exclusion rather than as a comment: while a turn holds this
    main's actor, the read does not complete.
    """
    seeded_main(tmp_path, "vidit", moves=("b_1",))

    async def drive():
        async with registry.acquire("vidit"):
            reading = asyncio.ensure_future(registry.tension_view("vidit"))
            await asyncio.sleep(0)
            held = reading.done()
        table, history = await reading
        return held, table, history

    done_while_held, table, history = asyncio.run(drive())
    assert not done_while_held, "the pass read a main's log around their mutex"
    assert set(table) == {"x_1"}
    assert {row["id"] for row in history} == {"b_1", "b_2"}


def test_a_correction_landing_between_the_plan_and_the_append_is_refused(
    registry, tmp_path
):
    """The ordinary-operation route into the terminality hole.

    The plan is computed outside the mutex — it has to be, or a pass would hold
    a main's actor from its first read to its last write — so a correction can
    land in between and resolve a tension the pass is about to move. The append
    carries the state it was planned from and is refused when the log has left
    it, which keeps the *log* honest rather than only the fold.
    """
    seeded_main(tmp_path, "vidit", moves=("b_1",))

    async def drive():
        # planned from `fresh` ...
        await registry.note_transition(
            "vidit", tension_id="x_1", t=MOVED,
            fields={STATE: "widening"}, was="fresh",
        )
        # ... and the same premise a second time, after the state moved.
        with pytest.raises(TensionError, match="planned from"):
            await registry.note_transition(
                "vidit", tension_id="x_1", t=MOVED,
                fields={STATE: "closing"}, was="fresh",
            )

    asyncio.run(drive())
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "widening"


def test_a_correction_that_resolved_a_tension_stops_the_planned_append(
    registry, tmp_path
):
    """The whole point of the premise, end to end: a retract lands after the
    plan was computed, and the transition it planned does not overwrite the
    resolution."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))

    async def drive():
        async with registry.acquire("vidit") as actor:
            actor.store.record(Op.RETRACT, "c_1", MOVED, target="b_1")
        with pytest.raises(TensionError):
            await registry.note_transition(
                "vidit", tension_id="x_1", t=MOVED,
                fields={STATE: "widening"}, was="fresh",
            )

    asyncio.run(drive())
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "resolved"


def test_a_transition_carries_a_state_and_nothing_else(registry, tmp_path):
    """``note_transition`` appended whatever it was handed. A ``claim`` beside
    the state validated and became durable — belief content written into a
    tension record, where no correction to either entry can take it back
    (AD-22)."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    for stray in ({"claim": "he never writes"}, {"independent": 3},
                  {"subject": "self"}, {"between": ["b_1", "b_9"]}):
        with pytest.raises(TensionError, match="nothing else"):
            asyncio.run(registry.note_transition(
                "vidit", tension_id="x_1", t=MOVED,
                fields={STATE: "widening", **stray}, was="fresh",
            ))
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "fresh"


def test_a_transition_naming_a_tension_the_log_does_not_hold_is_refused(
    registry, tmp_path
):
    """A pairless tension minted out of nothing: permanently not computable,
    counted every night, and nothing would ever resolve it."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    with pytest.raises(TensionError, match="no tension"):
        asyncio.run(registry.note_transition(
            "vidit", tension_id="never_minted", t=MOVED,
            fields={STATE: "widening"}, was=None,
        ))
    assert set(tensions_of(registry, "vidit")) == {"x_1"}


def test_the_history_the_pass_reads_is_the_asserts_and_nothing_else(
    registry, tmp_path
):
    """``belief_history`` was documented as *"every belief append this main
    has"* and returned a projection of every record of every op — schedule
    records, crisis records, loop transitions, tombstones and the tension
    records themselves. It also promised behaviour it did not have, about
    correction records letting a retracted side stop accumulating, which cannot
    work: a correction carries its own id and never its target's, and the
    projection drops ``target``.
    """
    with Store(tmp_path / "vidit") as store:
        seed_tension(store, moves=("b_1",))
        store.record(Op.LOOP_TRANSITION, "l_1", MOVED, loop="write-more",
                     state="advancing", timescale="weeks",
                     last_movement="2026-08-11")
        store.expunge("b_2", t=MOVED)
    set_due(registry, "vidit", NOON - 60)

    rows = registry.belief_history("vidit")
    assert {row["id"] for row in rows} == {"b_1"}
    assert all(set(row) <= {"id", "t", "support"} for row in rows)


def test_the_deciding_runs_off_the_event_loop(registry, tmp_path):
    """``half.schedule.tick``'s own notes say a pass that does real CPU work
    stalls the loop it shares with the inbound path and belongs behind
    ``asyncio.to_thread``. It also makes the scheduler's timeout mean
    something: ``asyncio.wait_for`` cannot cancel a coroutine that is not
    yielding."""
    import inspect

    source = inspect.getsource(TensionPass.evaluate)
    assert "asyncio.to_thread" in source
    tree = ast.parse((ROOT / "half/consolidate/pass_.py").read_text())
    threaded = {
        ast.unparse(node.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
        and node.args
    }
    assert threaded == {"_decide"}


def test_a_night_on_which_every_write_failed_is_not_a_quiet_night(
    registry, tmp_path
):
    """``run`` discarded the result, so the tick counted the main under ``ran``
    while ``next_pass_at`` had already advanced past the failures — a night of
    failed writes indistinguishable from a night with nothing to do."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    set_due(registry, "vidit", NOON - 60)

    class EveryWriteFails:
        def __init__(self, inner):
            self.inner = inner

        async def tension_view(self, main_id):
            return await self.inner.tension_view(main_id)

        async def note_transition(self, main_id, *, tension_id, t, fields,
                                  was=None):
            raise OSError("the disk is full")

    work = TensionPass(ledger=EveryWriteFails(registry))
    result = asyncio.run(work.evaluate("vidit", NOW))
    assert result.unrecorded == ("x_1",) and not result.quiet

    with pytest.raises(TensionPassIncomplete):
        asyncio.run(work.run("vidit", NOW))

    outcome = asyncio.run(
        scheduler(registry, tmp_path, ["vidit"], work=work).tick()
    )
    assert outcome.failed == ("vidit",) and outcome.ran == ()
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "fresh"


def test_a_pass_that_moved_nothing_and_failed_at_nothing_is_still_quiet(
    registry, tmp_path
):
    """Non-vacuity: ``run`` must not have become *"raise whenever anything was
    left alone"*. A tension the log cannot answer for is an ordinary thing to
    find, and a main who has one would otherwise never have a quiet night
    again."""
    with Store(tmp_path / "vidit") as store:
        seed_tension(store, minted=stamp(NOON - 86_400), moves=())
        past_the_gate(store, "x_bad", MINTED, **{STATE: "fresh"})

    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert result.incomputable and result.quiet
    assert asyncio.run(TensionPass(ledger=registry).run("vidit", NOW)) is None


# ═════════════════════════════════════════════════════════════════════════════
# matrix: pass under the scheduler — it runs, within its budget, and returns
# ═════════════════════════════════════════════════════════════════════════════


def test_a_due_main_has_their_pass_run_by_the_tick(registry, tmp_path):
    """Matrix: *pass under the scheduler*. A due main; the pass runs and the
    transition lands in that main's real log."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    set_due(registry, "vidit", NOON - 60)

    result = asyncio.run(
        scheduler(registry, tmp_path, ["vidit"], work=TensionPass(ledger=registry)).tick()
    )
    assert result.ran == ("vidit",)
    assert result.failed == () and result.timed_out == ()
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "widening"


def test_the_tick_judges_every_main_against_one_instant(registry, tmp_path):
    """The clock is read once, inside the lock, and handed down — so two mains
    in one tick get identical stamps on their transitions."""
    for main_id in ("vidit", "asha"):
        seeded_main(tmp_path, main_id, moves=("b_1",))
        set_due(registry, main_id, NOON - 60)

    asyncio.run(
        scheduler(registry, tmp_path, ["vidit", "asha"],
                  work=TensionPass(ledger=registry)).tick()
    )
    stamps = {tensions_of(registry, m)["x_1"]["t"] for m in ("vidit", "asha")}
    assert len(stamps) == 1


def test_the_pass_returns_well_inside_the_schedulers_timeout(registry, tmp_path):
    """*"The pass costs nothing this story"* — asserted by running it under a
    timeout two orders of magnitude below the shipped one."""
    for index in range(25):
        with Store(tmp_path / "vidit") as store:
            seed_tension(store, ident=f"x_{index}",
                         pair=(f"b_{index}a", f"b_{index}b"),
                         moves=(f"b_{index}a",))
    set_due(registry, "vidit", NOON - 60)

    result = asyncio.run(
        scheduler(registry, tmp_path, ["vidit"],
                  work=TensionPass(ledger=registry), timeout=5.0).tick()
    )
    assert result.ran == ("vidit",) and result.timed_out == ()
    moved = tensions_of(registry, "vidit")
    assert all(t[STATE] == "widening" for t in moved.values())


def test_a_main_in_crisis_mode_has_no_pass_run(registry, tmp_path):
    """CAP-12: the mode suspends Half's ordinary behaviour, and a nightly pass
    is ordinary behaviour. The branch existed before the work did; this is the
    case that shows it costs something now."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    set_due(registry, "vidit", NOON - 60)
    asyncio.run(registry.suspend_for_crisis(
        "vidit", t=stamp(NOON - 3600), tier="acute", score=3
    ))

    result = asyncio.run(
        scheduler(registry, tmp_path, ["vidit"],
                  work=TensionPass(ledger=registry)).tick()
    )
    assert result.suspended == ("vidit",) and result.ran == ()
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "fresh"


def test_a_missed_window_runs_no_pass_at_all(registry, tmp_path):
    """A window genuinely missed is genuinely missed: no catch-up, nothing
    computed, nothing appended."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    set_due(registry, "vidit", NOON - 100_000)

    result = asyncio.run(
        scheduler(registry, tmp_path, ["vidit"],
                  work=TensionPass(ledger=registry)).tick()
    )
    assert result.missed == ("vidit",) and result.ran == ()
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "fresh"


def test_the_pass_sends_nothing_to_anybody(registry, tmp_path):
    """Matrix: *nothing sent*. A pass produces log records and a count; whether
    any of it is worth saying is story 10's, and silence is first-class."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    set_due(registry, "vidit", NOON - 60)
    asyncio.run(
        scheduler(registry, tmp_path, ["vidit"],
                  work=TensionPass(ledger=registry)).tick()
    )
    with Store(tmp_path / "vidit") as store:
        ops = {record.op for record in store.log}
    assert ops <= {Op.ASSERT, Op.TENSION, Op.SCHEDULE}


# ═════════════════════════════════════════════════════════════════════════════
# matrix: pass fails for one main — counted; every other main still runs
# ═════════════════════════════════════════════════════════════════════════════


def test_a_main_whose_record_is_unreadable_is_counted_and_the_rest_still_run(
    registry, tmp_path
):
    """Matrix: *pass fails for one main*. AD-9's isolation, exercised with a
    real pass rather than a recorder."""
    for main_id in ("broken", "vidit"):
        seeded_main(tmp_path, main_id, moves=("b_1",))
        set_due(registry, main_id, NOON - 60)

    class Unreadable:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        async def tension_view(self, main_id):
            if main_id == "broken":
                raise OSError("this main's store cannot be read")
            return await self.inner.tension_view(main_id)

    result = asyncio.run(
        scheduler(registry, tmp_path, ["broken", "vidit"],
                  work=TensionPass(ledger=Unreadable(registry))).tick()
    )
    assert result.failed == ("broken",)
    assert result.ran == ("vidit",)
    assert tensions_of(registry, "vidit")["x_1"][STATE] == "widening"
    assert tensions_of(registry, "broken")["x_1"][STATE] == "fresh"


def test_one_main_cannot_reach_another_mains_tensions(registry, tmp_path):
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    seeded_main(tmp_path, "asha", moves=())
    asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    assert tensions_of(registry, "asha")["x_1"][STATE] == "fresh"


# ═════════════════════════════════════════════════════════════════════════════
# the shipped composition — asserted by value, and actually run
# ═════════════════════════════════════════════════════════════════════════════


def test_the_scheduler_holds_the_pass_this_wiring_built(tmp_path):
    """*"The scheduler holds this pass and not ``Nothing``, asserted by value
    rather than by keyword."*

    Story 6d's identical claim was satisfied by a case asserting a keyword's
    *name* appeared in the source, which passed with the value set to ``None``.
    So: not ``Nothing``; a ``TensionPass``; and holding *this* wiring's
    registry by identity — an ``isinstance`` check alone would pass for one
    wired to somebody else's registry, or constructed and thrown away.

    Story 10 wraps it: the scheduler's work is a ``MorningPass`` whose
    consolidation half is the pass this case has always asserted. Reached
    through the field rather than compared as a whole, so this case keeps
    asserting the same sentence it always did and story 10's own wiring case
    asserts the wrapper.
    """
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load
    from half.surface.morning import MorningPass

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    try:
        work = wiring.scheduler.work
        assert not isinstance(work, Nothing)
        assert isinstance(work, MorningPass)
        consolidate = work.consolidate
        assert isinstance(consolidate, TensionPass)
        assert consolidate.ledger is wiring.registry
        assert consolidate == TensionPass(ledger=wiring.registry)
    finally:
        wiring.registry.close()


def test_the_shipped_wiring_actually_moves_a_tension(tmp_path):
    """Run, not grepped. The object graph the product builds, a real store, a
    real tick, and a transition in a real log — the failure this asserts
    against is a surface reachable only from a test."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    seeded_main(tmp_path, "vidit", moves=("b_1",))
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    try:
        set_due(wiring.registry, "vidit", NOON - 60)
        # The clock is swapped before the tick so this case does not write real
        # due times off the wall clock.
        wiring.scheduler.clock = FrozenClock(at=NOON)
        result = asyncio.run(wiring.scheduler.tick())
        assert result.ran == ("vidit",)
        assert wiring.registry.tension_table("vidit")["x_1"][STATE] == "widening"
    finally:
        wiring.registry.close()


def test_the_pass_satisfies_the_protocol_the_scheduler_calls():
    """Structural, because ``Pass`` is a protocol and a signature drift would
    be a ``TypeError`` at three in the morning rather than at import."""
    import inspect

    assert "now" in inspect.signature(TensionPass.run).parameters
    assert "main_id" in inspect.signature(TensionPass.run).parameters
    assert set(inspect.signature(Pass.run).parameters) <= set(
        inspect.signature(TensionPass.run).parameters
    )
    assert asyncio.iscoroutinefunction(TensionPass.run)


def test_run_returns_none_so_the_ticks_contract_is_unchanged(registry, tmp_path):
    """The tick reads ``None`` as *ran* and anything else as an outcome to
    handle; a pass that started returning a result would be counted as
    failed."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    assert asyncio.run(TensionPass(ledger=registry).run("vidit", NOW)) is None


# ═════════════════════════════════════════════════════════════════════════════
# matrix: purity — the pass costs nothing, and reaches no model
# ═════════════════════════════════════════════════════════════════════════════


def _imports_of(path: Path) -> set[str]:
    roots: set[str] = set()
    package = path.relative_to(ROOT).with_suffix("").parts[:-1]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                if base:
                    roots.add(".".join(base))
            elif node.module:
                roots.add(node.module)
    return roots


def test_the_pass_reaches_no_model_and_no_network():
    """*"No model call, no network; the budget it runs under is zero."*

    Transitive rather than one hop: a pass that imported a helper that imported
    the port would pass a direct check while being every bit as expensive.
    """
    edges = {
        ".".join(p.relative_to(ROOT).with_suffix("").parts): _imports_of(p)
        for p in (ROOT / "half").rglob("*.py")
    }

    def reaches(start, seen=None):
        seen = seen if seen is not None else set()
        for target in edges.get(start, ()):
            if not target.startswith("half"):
                continue
            module = target if target in edges else target.rsplit(".", 1)[0]
            if module in seen:
                continue
            seen.add(module)
            reaches(module, seen)
        return seen

    for area in ("half.consolidate.pass_", "half.tensions.ledger",
                 "half.tensions.widening", "half.tensions.states"):
        touched = {m for m in reaches(area) if m.startswith("half.model")}
        assert not touched, (
            f"{area} reaches {sorted(touched)} — the nightly pass costs "
            f"nothing this story, and a model call is not nothing"
        )


def test_nothing_in_the_pass_opens_a_socket_or_spawns_a_process():
    forbidden = {"socket", "http", "urllib", "requests", "httpx", "subprocess",
                 "anthropic", "openai", "random", "secrets", "uuid"}
    for area in ("half/consolidate", "half/tensions"):
        for path in sorted((ROOT / area).rglob("*.py")):
            roots = {name.split(".")[0] for name in _imports_of(path)}
            assert not roots & forbidden, (
                f"{path.relative_to(ROOT)} imports {sorted(roots & forbidden)}"
            )


def test_the_pass_body_is_a_pure_function_of_what_it_was_given(
    registry, tmp_path
):
    """The deciding half is ``ledger.plan``, and the same three inputs give the
    same plan for ever. Asserted through the registry's own reads, so a store
    that had started returning something time-dependent would fail here."""
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    table, history = asyncio.run(registry.tension_view("vidit"))
    table = tension_ledger.read(table)
    plans = {
        repr(tension_ledger.plan(table, history=history, now=NOW.stamp))
        for _ in range(5)
    }
    assert len(plans) == 1


def test_the_pass_reads_the_log_and_never_writes_one_by_itself(
    registry, tmp_path
):
    """AD-1: the single writer. Every append goes through the registry's mutex,
    and the pass holds no store of its own."""
    import inspect

    source = inspect.getsource(TensionPass)
    assert "Store(" not in source
    # Story 9d adds the judgement seam and nothing else. Pinned as an equality
    # rather than a superset, because the field that would arrive next is a
    # store, a clock or a provider — each of which is a second writer, a second
    # clock reader or a model on the nightly path.
    assert set(TensionPass.__dataclass_fields__) == {"ledger", "judge"}
    assert TensionPass.__dataclass_fields__["judge"].default is None
    assert set(dir(Ledger)) >= {
        "tension_view", "note_transition", "mint_view", "note_mint",
    }


def test_no_log_line_on_this_path_can_carry_content(registry, tmp_path):
    """AD-22: counts and reasons only. Every argument to a logging call in the
    pass is a literal, a count, a main id, a tension id, an exception *type* or
    a set of reason constants — never a record, a claim or a field value."""
    path = ROOT / "half/consolidate/pass_.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"):
            continue
        rendered = [ast.unparse(argument) for argument in node.args]
        assert all("f'" not in text and 'f"' not in text for text in rendered), (
            f"an f-string reached a log call at line {node.lineno}"
        )
        for text in rendered[1:]:
            assert any(
                marker in text
                for marker in ("main_id", "len(", "type(", "tension_id",
                               "sorted(set(")
            ), f"a log argument may carry content: {text!r} (line {node.lineno})"


def test_the_result_carries_counts_and_ids_but_never_a_record(
    registry, tmp_path
):
    seeded_main(tmp_path, "vidit", moves=("b_1",))
    result = asyncio.run(TensionPass(ledger=registry).evaluate("vidit", NOW))
    rendered = repr(result)
    assert "entry number" not in rendered and "restated" not in rendered
    assert "s_b_1" not in rendered


# ═════════════════════════════════════════════════════════════════════════════
# the cases a collection floor cannot protect
# ═════════════════════════════════════════════════════════════════════════════


def _cases_defined_here() -> set[str]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_every_pass_guarantee_this_story_rests_on_still_exists():
    required = {
        "test_the_same_pass_twice_with_the_same_now_appends_nothing_the_second_time",
        "test_a_third_and_fourth_run_still_append_nothing",
        "test_one_incomputable_tension_never_blocks_the_others",
        "test_a_failed_append_costs_that_tension_and_nothing_else",
        "test_a_main_whose_record_is_unreadable_is_counted_and_the_rest_still_run",
        "test_the_scheduler_holds_the_pass_this_wiring_built",
        "test_the_shipped_wiring_actually_moves_a_tension",
        "test_the_pass_reaches_no_model_and_no_network",
        "test_no_log_line_on_this_path_can_carry_content",
        "test_the_transition_is_an_append_that_keeps_the_pair_and_the_license",
        "test_the_two_reads_are_one_read_under_the_mains_own_mutex",
        "test_a_correction_landing_between_the_plan_and_the_append_is_refused",
        "test_a_correction_that_resolved_a_tension_stops_the_planned_append",
        "test_a_transition_carries_a_state_and_nothing_else",
        "test_a_transition_naming_a_tension_the_log_does_not_hold_is_refused",
        "test_the_history_the_pass_reads_is_the_asserts_and_nothing_else",
        "test_the_deciding_runs_off_the_event_loop",
        "test_a_night_on_which_every_write_failed_is_not_a_quiet_night",
        "test_a_pass_that_moved_nothing_and_failed_at_nothing_is_still_quiet",
    }
    missing = required - _cases_defined_here()
    assert not missing, (
        f"a pass guarantee was deleted: {sorted(missing)}. A floor on the "
        f"suite cannot protect these — each carries a whole property"
    )
