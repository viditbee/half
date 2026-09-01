"""CAP-6 story 8: the open-loop ledger — one case per row of the I/O matrix.

Three things this file insists on.

**The firewall is asserted structurally as well as behaviourally.** *"Evidence of
non-action never refutes a wanting"* is easy to agree with and easy to violate
by accident — the natural implementation of a nightly pass that sees no movement
is to lower confidence in the belief that the loop exists. A behavioural test
only covers the paths somebody thought of, so the correction cases in
``half/store/fold.py`` are also read as an AST and asserted to contain no
reference to the loop table at all. Adding one has to be a deliberate edit that
fails a named test, not a plausible-looking line.

**Nothing here reads a clock.** Every ``now`` is computed by the test and handed
in. The same log and the same stamp must give the same loops and the same
silence for ever (AD-30), and a suite that used the real clock would pass today
and be irreproducible tomorrow.

**The vocabulary is checked for agreement, not just for content.** The four
state names live in one module now; the salience weights, the append gate and
the ledger all read them from there. Cases below assert those readers cover the
vocabulary exactly, so a fifth state added through the Ask-First path fails
loudly at each place that has to decide what it means.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from half.errors import LoopError
from half.loops import ledger
from half.loops.ledger import AbandonmentCandidate, Loop
from half.loops.states import LOOP_STATES, LoopState, is_state, parse_state
from half.loops.timescale import (
    NO_MOVEMENT,
    NO_TIMESCALE,
    PERIOD_DAYS,
    TIMESCALES,
    UNKNOWN_TIMESCALE,
    UNREADABLE_MOVEMENT,
    Timescale,
    silence,
)
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import Retriever
from half.retrieval.salience import LOOP_STATES as LOOP_WEIGHTS
from half.retrieval.salience import UNKNOWN_LOOP_STATE
from half.store.fold import fold
from half.store.ops import SCHEMA_VERSION, Op
from half.store.records import Record, make
from half.store.store import Store

pytestmark = pytest.mark.cap6

ROOT = Path(__file__).resolve().parents[1]

#: Every stamp in this file is derived from these two. Injected, never read.
NOW = "2026-09-01T09:00:00Z"
LONG_AGO = "2025-03-12"


@pytest.fixture
def loops(tmp_path):
    """A store wired the way the running product wires it: prefixes indexed."""
    with Store(tmp_path / "main", prefix=build_prefix) as store:
        yield store


def open_loop(store, ident, loop_id, **kw):
    t = kw.pop("t", "2026-08-01T00:00Z")
    store.record(Op.LOOP_TRANSITION, ident, t, **ledger.opened(loop_id, **kw))
    return ledger.read(store.state().loops)[loop_id]


def later_build_line(store, ident, t, **fields):
    """A log line this build's append gate would have refused.

    Constructed as a ``Record`` and appended to the log directly, because
    ``records.make`` is the gate: the only way to have a log carrying a state
    from a later build is to write one the way that build would have. Which is
    the point — the append gate refuses it, and the read path must still fold it.
    """
    data = {"t": t, "op": Op.LOOP_TRANSITION.value, "id": ident,
            "v": SCHEMA_VERSION, **fields}
    store.log.append(Record(op=Op.LOOP_TRANSITION, id=ident, t=t, data=data))


def belief(store, ident, claim, **fields):
    fields.setdefault("subject", "self")
    fields.setdefault("ledger", "revealed")
    fields.setdefault("independent", 0)
    t = fields.pop("t", "2026-08-01T00:00:00Z")
    store.record(Op.ASSERT, ident, t, claim=claim, **fields)


# =============================================================================
# matrix: open a loop
# =============================================================================

def test_a_loop_opened_with_a_state_and_a_timescale_is_readable_from_the_fold(loops):
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="years", last_movement=LONG_AGO)

    assert found == Loop(id="buy-farmland", state="stalled", timescale="years",
                         last_movement=LONG_AGO)
    assert loops.state().loops["buy-farmland"]["state"] == "stalled"


def test_a_loop_is_opened_moved_and_closed_by_appends_and_never_edited(loops):
    """AD-3: no state is edited in place. Three appends, three lines."""
    open_loop(loops, "l_1", "swim-weekly", state="advancing", timescale="weeks",
              last_movement="2026-08-01T06:00Z")
    loops.record(Op.LOOP_TRANSITION, "l_2", "2026-08-09T00:00Z",
                 **ledger.move("swim-weekly", at="2026-08-08T06:00Z"))
    loops.record(Op.LOOP_TRANSITION, "l_3", "2026-08-20T00:00Z",
                 **ledger.move("swim-weekly", at="2026-08-19T06:00Z",
                               state="achieved"))

    shard = (loops.log.root / "2026-08.jsonl").read_text(encoding="utf-8")
    assert shard.count("\n") == 3, "a transition rewrote a line instead of appending"

    found = ledger.read(loops.state().loops)["swim-weekly"]
    assert found.state == "achieved"
    assert found.last_movement == "2026-08-19T06:00Z"
    assert found.timescale == "weeks", "movement dropped the loop's own period"


def test_moving_a_loop_does_not_disturb_another(loops):
    open_loop(loops, "l_1", "swim-weekly", state="advancing", timescale="weeks")
    open_loop(loops, "l_2", "buy-farmland", state="stalled", timescale="years",
              last_movement=LONG_AGO)
    loops.record(Op.LOOP_TRANSITION, "l_3", "2026-08-09T00:00Z",
                 **ledger.move("swim-weekly", at="2026-08-08T06:00Z"))

    farmland = ledger.read(loops.state().loops)["buy-farmland"]
    assert farmland.last_movement == LONG_AGO


# =============================================================================
# matrix: unknown state — refused at the append, never defaulted
# =============================================================================

@pytest.mark.parametrize(
    "state",
    ["stale", "advancing ", "ADVANCING", "abandoned", "fresh", "widening",
     "entered", "asked", "", "true", "false", "refuted"],
)
def test_a_state_outside_the_vocabulary_is_refused_at_the_append(loops, state):
    """Refused *before the record is durable*. The log is append-only, so a
    state nothing recognises would be carried by every future fold for ever."""
    with pytest.raises(ValueError):
        loops.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                     loop="buy-farmland", state=state)

    assert loops.state().loops == {}, "a refused state reached the fold"
    assert not (loops.log.root / "2026-08.jsonl").exists(), "it reached the log"


@pytest.mark.parametrize("state", [1, True, ["advancing"], {"s": "advancing"}])
def test_a_state_that_is_not_even_a_string_is_refused(loops, state):
    with pytest.raises(ValueError):
        loops.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                     loop="buy-farmland", state=state)


def test_an_unknown_state_is_never_defaulted_to_a_known_one(loops):
    """The failure this rules out is silent, not loud: a gate that folded an
    unreadable state to `stalled` would put a word in the main's mouth about
    their own wanting and then make it permanent."""
    with pytest.raises(ValueError):
        loops.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                     loop="buy-farmland", state="stale")
    with pytest.raises(LoopError):
        ledger.opened("buy-farmland", state="stale")


@pytest.mark.parametrize("state", sorted(LOOP_STATES))
def test_every_state_in_the_vocabulary_is_accepted(loops, state):
    """Non-vacuity for the row above: a gate that refused everything would
    pass every case there and ship a ledger nothing could write to."""
    open_loop(loops, f"l_{state}", f"loop-{state}", state=state)
    assert ledger.read(loops.state().loops)[f"loop-{state}"].state == state


def test_the_vocabulary_is_exactly_the_four_the_glossary_names():
    assert LOOP_STATES == {
        "advancing", "stalled", "abandoned-but-unadmitted", "achieved",
    }, "a fifth state, or a renamed one, is an Ask-First change"


def test_no_state_in_the_vocabulary_means_false():
    """A wanting is neither true nor false, so no state may read as a verdict
    on whether the main really wanted it."""
    for forbidden in ("false", "refuted", "disproven", "untrue", "wrong",
                      "unsupported", "retracted"):
        assert forbidden not in LOOP_STATES


def test_parse_state_raises_and_is_state_does_not():
    assert is_state("advancing") and not is_state("stale")
    assert parse_state("achieved") is LoopState.ACHIEVED
    with pytest.raises(ValueError):
        parse_state("stale")


# =============================================================================
# matrix: missing timescale — recorded, but reported as not detectable
# =============================================================================

def test_a_loop_with_no_timescale_is_recorded(loops):
    found = open_loop(loops, "l_1", "learn-tabla", state="advancing")

    assert found.state == "advancing"
    assert found.timescale is None
    assert "learn-tabla" in loops.state().loops


def test_a_loop_with_no_timescale_reports_as_not_silent_detectable(loops):
    found = open_loop(loops, "l_1", "learn-tabla", state="advancing",
                      last_movement=LONG_AGO)
    quiet = found.silence(now=NOW)

    assert not quiet.detectable
    assert not quiet.silent, "undetectable must never read as silent"
    assert quiet.reason == NO_TIMESCALE
    assert quiet.period_days is None, "a missing period was filled in from somewhere"


def test_a_loop_with_no_timescale_never_borrows_one_from_another_loop(loops):
    """The failure a default hides: a farmland loop nagged monthly reads as
    Half not understanding the main at all."""
    open_loop(loops, "l_1", "swim-weekly", state="advancing", timescale="days",
              last_movement=LONG_AGO)
    found = open_loop(loops, "l_2", "buy-farmland", state="stalled",
                      last_movement=LONG_AGO)

    assert found.silence(now=NOW).period_days is None
    assert not found.silence(now=NOW).silent


def test_a_loop_that_has_never_moved_is_not_detectable_either(loops):
    found = open_loop(loops, "l_1", "buy-farmland", state="advancing",
                      timescale="years")
    quiet = found.silence(now=NOW)

    assert not quiet.detectable and not quiet.silent
    assert quiet.reason == NO_MOVEMENT
    assert quiet.period_days == 365, "the period is known even when the date is not"


def test_no_module_in_the_tree_supplies_a_default_timescale():
    """A default of any kind is an Ask-First change, so nothing may sneak one
    in as a fallback. Scanned rather than reasoned about: the natural place for
    one is a ``get('timescale', 'months')`` nobody reviews."""
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name not in {"get", "setdefault", "getattr"} or len(node.args) < 2:
                continue
            key, fallback = node.args[0], node.args[1]
            if not (isinstance(key, ast.Constant) and key.value == "timescale"):
                continue
            if isinstance(fallback, ast.Constant) and fallback.value is None:
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, f"a default timescale appeared at {offenders}"


def test_an_unreadable_timescale_from_a_later_build_degrades_rather_than_guesses():
    quiet = silence({"timescale": "decades", "last_movement": LONG_AGO}, now=NOW)
    assert not quiet.detectable and not quiet.silent
    assert quiet.reason == UNKNOWN_TIMESCALE
    assert quiet.period_days is None


@pytest.mark.parametrize("moved", ["not-a-date", "2026-02-31", "0001-01-01",
                                   "2026-13-01", 17, None])
def test_a_movement_stamp_that_is_not_an_instant_is_not_detectable(moved):
    quiet = silence({"timescale": "years", "last_movement": moved}, now=NOW)
    assert not quiet.detectable and not quiet.silent
    assert quiet.reason in {UNREADABLE_MOVEMENT, NO_MOVEMENT}


def test_a_movement_date_that_is_not_a_date_is_refused_at_the_ledger():
    for bad in ("yesterday", "2026-02-31", "", 3, None):
        with pytest.raises(LoopError):
            ledger.move("buy-farmland", at=bad)


# =============================================================================
# matrix: silent past its period / within its period / different timescales
# =============================================================================

def test_a_loop_silent_past_its_own_period_is_detectable_as_silent():
    quiet = silence({"timescale": "months", "last_movement": "2026-01-04"},
                    now=NOW)
    assert quiet.detectable and quiet.silent
    assert quiet.period_days == 30
    assert quiet.periods is not None and quiet.periods > 1.0


def test_a_loop_inside_its_own_period_is_not_silent():
    quiet = silence({"timescale": "months", "last_movement": "2026-08-20"},
                    now=NOW)
    assert quiet.detectable and not quiet.silent


def test_a_days_loop_and_a_years_loop_with_the_same_movement_differ():
    """The row the whole design exists for. One ``last_movement``, two answers,
    because each loop is measured against its own period and nothing else."""
    moved = "2026-06-01"
    days = silence({"timescale": "days", "last_movement": moved}, now=NOW)
    years = silence({"timescale": "years", "last_movement": moved}, now=NOW)

    assert days.detectable and days.silent
    assert years.detectable and not years.silent


@pytest.mark.parametrize("scale", sorted(TIMESCALES))
def test_every_timescale_can_be_both_silent_and_not(scale):
    """Non-vacuity: a period that no elapsed time could ever cross would make
    the row above pass while detecting nothing."""
    period = PERIOD_DAYS[Timescale(scale)]
    fresh = silence({"timescale": scale, "last_movement": "2026-09-01T00:00Z"},
                    now=NOW)
    assert fresh.detectable and not fresh.silent, scale

    long_ago = silence({"timescale": scale, "last_movement": "2000-01-01"},
                       now=NOW)
    assert long_ago.detectable and long_ago.silent, scale
    assert long_ago.elapsed_days is not None and long_ago.elapsed_days > period


def test_the_periods_are_ordered_and_none_of_them_is_shared():
    ordered = [PERIOD_DAYS[Timescale(s)]
               for s in ("days", "weeks", "months", "years")]
    assert ordered == sorted(ordered)
    assert len(set(ordered)) == len(ordered), "two scales share a period"


def test_movement_dated_in_the_future_does_not_buy_a_loop_negative_age():
    quiet = silence({"timescale": "days", "last_movement": "2027-01-01"}, now=NOW)
    assert quiet.detectable and not quiet.silent
    assert quiet.elapsed_days == 0.0


def test_silence_lists_only_the_loops_it_can_actually_tell_about(loops):
    open_loop(loops, "l_1", "buy-farmland", state="stalled", timescale="years",
              last_movement="2020-01-01")
    open_loop(loops, "l_2", "swim-weekly", state="advancing", timescale="weeks",
              last_movement="2026-08-30T06:00Z")
    open_loop(loops, "l_3", "learn-tabla", state="advancing",
              last_movement="2020-01-01")

    quiet = ledger.silent(ledger.read(loops.state().loops), now=NOW)
    assert set(quiet) == {"buy-farmland"}, (
        "a loop with no timescale was counted as silent, which is a guess"
    )


# =============================================================================
# matrix: the refutation firewall — nothing demotes a wanting
# =============================================================================

@pytest.mark.cap6_firewall
def test_a_loop_stands_when_its_only_supporting_belief_is_retracted(loops):
    belief(loops, "b_1", "wants to buy farmland", loop="buy-farmland")
    before = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                       timescale="years", last_movement=LONG_AGO)

    loops.record(Op.RETRACT, "c_1", "2026-08-02T00:00Z", target="b_1")

    assert "b_1" not in loops.state().beliefs, "the belief must actually go"
    assert ledger.read(loops.state().loops)["buy-farmland"] == before


@pytest.mark.cap6_firewall
def test_a_loop_stands_when_a_belief_on_it_is_revised(loops):
    belief(loops, "b_1", "wants to buy farmland", loop="buy-farmland")
    before = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                       timescale="years", last_movement=LONG_AGO)

    loops.record(Op.REVISE, "c_1", "2026-08-02T00:00Z", target="b_1")

    assert "b_1" not in loops.state().beliefs
    assert ledger.read(loops.state().loops)["buy-farmland"] == before


@pytest.mark.cap6_firewall
def test_a_loop_survives_when_a_supporting_belief_is_expunged(loops):
    belief(loops, "b_1", "wants to buy farmland", loop="buy-farmland")
    before = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                       timescale="years", last_movement=LONG_AGO)

    loops.expunge("b_1", t="2026-08-02T00:00Z")

    assert "b_1" not in loops.state().beliefs
    assert "b_1" in loops.state().expunged, "the belief must actually go"
    assert ledger.read(loops.state().loops)["buy-farmland"] == before


@pytest.mark.cap6_firewall
@pytest.mark.parametrize("op", [Op.RETRACT, Op.REVISE, Op.EXPUNGE])
def test_a_correction_naming_the_loop_id_itself_still_leaves_the_loop(loops, op):
    """The collision case, which is the one an accident actually looks like.

    ``target`` reaches beliefs and tensions. It takes a second, explicit
    ``loop`` field to reach a wanting, so even a correction that happens to name
    the loop's own identifier cannot demote it.
    """
    before = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                       timescale="years", last_movement=LONG_AGO)

    loops.record(op, "c_1", "2026-08-02T00:00Z", target="buy-farmland")

    assert ledger.read(loops.state().loops)["buy-farmland"] == before


@pytest.mark.cap6_firewall
def test_a_tombstoned_record_sharing_a_loops_identifier_leaves_the_loop(loops):
    """A tombstone erases one record's body and is keyed on that record's own
    id. Before the firewall it also popped the loop table, so a belief that
    happened to share a loop's slug deleted a wanting."""
    before = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                       timescale="years", last_movement=LONG_AGO)
    loops.log.append(make(Op.ASSERT, "buy-farmland", "2026-08-02T00:00Z",
                          tombstone=True))

    assert ledger.read(loops.rebuild().loops)["buy-farmland"] == before


@pytest.mark.cap6_firewall
def test_no_evidence_for_a_year_leaves_the_wanting_true_and_only_stalled(loops):
    """Matrix: nothing supports the wanting and nothing contradicts it.

    The state may be `stalled`. There is no code path from that to *"this
    wanting is not real"* — which is asserted as an absence: after a year of
    nothing, the loop is present, in the vocabulary, and no op in the log claims
    otherwise.
    """
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="years", last_movement="2025-08-01")

    assert found.silence(now=NOW).silent
    assert found.state == "stalled"
    assert is_state(found.state)
    assert "buy-farmland" not in loops.state().expunged
    assert ledger.read(loops.state().loops)["buy-farmland"] == found


@pytest.mark.cap6_firewall
def test_the_correction_cases_in_the_fold_cannot_name_the_loop_table():
    """The structural half, and the reason this file exists in this shape.

    A behavioural test only covers the paths somebody thought of. This reads
    ``fold`` as an AST and asserts that the branches which remove a belief
    contain no reference to loops at all — so demoting a wanting from the
    correction path takes a deliberate edit that fails a named test.
    """
    tree = ast.parse((ROOT / "half/store/fold.py").read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fold"
    )
    match_node = next(
        node for node in ast.walk(function) if isinstance(node, ast.Match)
    )

    guarded = {"Op.RETRACT", "Op.REVISE"}
    seen: set[str] = set()
    for case in match_node.cases:
        pattern = {ast.unparse(node.value) for node in ast.walk(case.pattern)
                   if isinstance(node, ast.MatchValue)}
        if not (pattern & guarded):
            continue
        seen |= pattern & guarded
        body = "\n".join(ast.unparse(statement) for statement in case.body)
        assert "loops" not in body, (
            f"the correction case {sorted(pattern)} reaches the loop table; a "
            "wanting is not a fact and nothing may refute one (CAP-6)"
        )
    assert seen == guarded, (
        f"the fold no longer has a case for {sorted(guarded - seen)}; this gate "
        "would have passed by finding nothing to check"
    )


@pytest.mark.cap6_firewall
def test_the_tombstone_branch_cannot_name_the_loop_table():
    """The same assertion for the branch above the match, which is the one that
    actually held the defect: it popped ``state.loops`` by record id."""
    source = (ROOT / "half/store/fold.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fold"
    )
    loop_body = next(
        node for node in function.body if isinstance(node, ast.For)
    )
    tombstone = next(
        node for node in loop_body.body
        if isinstance(node, ast.If) and "tombstone" in ast.unparse(node.test)
    )
    body = "\n".join(ast.unparse(statement) for statement in tombstone.body)
    assert "loops" not in body


@pytest.mark.cap6_firewall
def test_the_ledger_offers_no_way_to_refute_or_demote_a_loop():
    """There is no ``refute``, no ``demote``, no ``decay`` — and no argument
    anywhere through which belief evidence reaches a loop's state."""
    tree = ast.parse((ROOT / "half/loops/ledger.py").read_text(encoding="utf-8"))
    names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not names & {"refute", "demote", "decay", "disprove", "invalidate"}

    for function in (ledger.opened, ledger.move, ledger.abandon,
                     ledger.abandonment_candidate):
        arguments = function.__code__.co_varnames[: function.__code__.co_argcount
                                                  + function.__code__.co_kwonlyargcount]
        assert not {"belief", "beliefs", "support", "evidence"} & set(arguments), (
            f"{function.__name__} takes belief evidence as an input"
        )


# =============================================================================
# matrix: abandonment — a candidate is produced, nothing is recorded
# =============================================================================

def test_inference_produces_a_candidate_and_records_nothing(loops):
    open_loop(loops, "l_1", "buy-farmland", state="stalled", timescale="months",
              last_movement="2024-01-01")
    before = loops.state().canonical_json()

    found = ledger.read(loops.state().loops)["buy-farmland"]
    candidate = ledger.abandonment_candidate(found, now=NOW)

    assert isinstance(candidate, AbandonmentCandidate)
    assert candidate.loop_id == "buy-farmland"
    assert candidate.reason
    assert loops.state().canonical_json() == before, "detection wrote something"
    assert ledger.read(loops.state().loops)["buy-farmland"].state == "stalled"


def test_a_candidate_alone_never_becomes_a_transition(loops):
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(found, now=NOW)

    with pytest.raises(LoopError):
        ledger.abandon(found, candidate=candidate, answered=False)
    with pytest.raises(TypeError):
        ledger.abandon(found, candidate=candidate)  # the answer has no default
    with pytest.raises(TypeError):
        ledger.abandon(found, answered=True)  # neither has the candidate


def test_the_answer_is_what_records_abandonment(loops):
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(found, now=NOW)

    loops.record(Op.LOOP_TRANSITION, "l_2", "2026-09-01T09:00Z",
                 **ledger.abandon(found, candidate=candidate, answered=True))

    after = ledger.read(loops.state().loops)["buy-farmland"]
    assert after.state == "abandoned-but-unadmitted"
    assert after.last_movement == "2024-01-01", (
        "admitting a wanting is over is not the wanting moving"
    )


def test_a_candidate_for_one_loop_cannot_abandon_another(loops):
    one = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                    timescale="months", last_movement="2024-01-01")
    other = open_loop(loops, "l_2", "learn-tabla", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(one, now=NOW)

    with pytest.raises(LoopError):
        ledger.abandon(other, candidate=candidate, answered=True)


def test_move_refuses_to_apply_abandonment_dressed_as_movement(loops):
    """The side door: ``move(..., state="abandoned-but-unadmitted")`` looks like
    ordinary movement and would apply on inference alone."""
    with pytest.raises(LoopError):
        ledger.move("buy-farmland", at="2026-08-01",
                    state="abandoned-but-unadmitted")


def test_no_candidate_where_the_answer_would_be_a_guess(loops):
    """Every case in which silence is not detectable, and the two states that
    are not live. There is no path from *"we cannot tell"* to *"given up"*."""
    cases = {
        "no-timescale": Loop(id="a", state="stalled", last_movement="2020-01-01"),
        "never-moved": Loop(id="b", state="stalled", timescale="months"),
        "unreadable": Loop(id="c", state="stalled", timescale="months",
                           last_movement="whenever"),
        "later-build": Loop(id="d", state="wandering", timescale="months",
                            last_movement="2020-01-01"),
        "achieved": Loop(id="e", state="achieved", timescale="months",
                         last_movement="2020-01-01"),
        "already": Loop(id="f", state="abandoned-but-unadmitted",
                        timescale="months", last_movement="2020-01-01"),
        "no-state": Loop(id="g", timescale="months", last_movement="2020-01-01"),
    }
    for name, loop in cases.items():
        assert ledger.abandonment_candidate(loop, now=NOW) is None, name


def test_a_loop_inside_the_abandonment_threshold_raises_nothing():
    """Non-vacuity from the other side: the threshold is crossable and it is
    counted in the loop's *own* periods."""
    inside = Loop(id="a", state="stalled", timescale="months",
                  last_movement="2026-03-01")
    past = Loop(id="a", state="stalled", timescale="months",
                last_movement="2024-01-01")

    assert ledger.abandonment_candidate(inside, now=NOW) is None
    assert ledger.abandonment_candidate(past, now=NOW) is not None


def test_the_threshold_means_twelve_of_each_loops_own_periods():
    """gbrain's ``abandoned_threads`` counts twelve months for everything. Half
    counts twelve of *this* loop's periods, so twelve months is right for a
    months-loop and twelve years is right for a farmland one."""
    moved = "2025-08-01"  # thirteen months before NOW
    months = Loop(id="a", state="stalled", timescale="months", last_movement=moved)
    years = Loop(id="b", state="stalled", timescale="years", last_movement=moved)

    assert ledger.abandonment_candidate(months, now=NOW) is not None
    assert ledger.abandonment_candidate(years, now=NOW) is None


# =============================================================================
# matrix: loop expunged
# =============================================================================

def test_an_expunged_loop_is_gone_from_the_fold(loops):
    open_loop(loops, "l_1", "buy-farmland", state="stalled", timescale="years",
              last_movement=LONG_AGO)

    loops.record(Op.EXPUNGE, "x_1", "2026-08-02T00:00Z",
                 **ledger.expunged("buy-farmland"))

    assert "buy-farmland" not in loops.state().loops
    assert "buy-farmland" in loops.state().expunged


def test_an_expunged_loop_is_not_resurrected_by_a_later_transition(loops):
    open_loop(loops, "l_1", "buy-farmland", state="stalled", timescale="years")
    loops.record(Op.EXPUNGE, "x_1", "2026-08-02T00:00Z",
                 **ledger.expunged("buy-farmland"))
    loops.record(Op.LOOP_TRANSITION, "l_2", "2026-08-03T00:00Z",
                 **ledger.move("buy-farmland", at="2026-08-03"))

    assert "buy-farmland" not in loops.state().loops


def test_expunging_a_loop_leaves_every_other_loop(loops):
    open_loop(loops, "l_1", "buy-farmland", state="stalled", timescale="years")
    open_loop(loops, "l_2", "learn-tabla", state="advancing", timescale="weeks")
    loops.record(Op.EXPUNGE, "x_1", "2026-08-02T00:00Z",
                 **ledger.expunged("buy-farmland"))

    assert set(loops.state().loops) == {"learn-tabla"}


# =============================================================================
# matrix: ranking — story 4's behaviour holds
# =============================================================================

def test_a_belief_on_an_advancing_loop_outranks_an_equal_one(loops):
    """Story 4's ordering, restated here because story 8 is what makes the four
    state names mean something. The tie-break points the other way, so a build
    that stopped weighting loops would give the opposite answer."""
    belief(loops, "b_zzz", "thinks about it often", loop="fly-again")
    belief(loops, "b_aaa", "thinks about it often", loop="learn-tabla")
    open_loop(loops, "l_1", "fly-again", state="advancing", timescale="months")

    ranked = Retriever(store=loops).retrieve("thinks", now=NOW)
    assert ranked.ids == ("b_zzz", "b_aaa")


def test_an_achieved_loop_ranks_lower_and_is_not_deleted(loops):
    belief(loops, "b_zzz", "thinks about it often", loop="learn-tabla")
    belief(loops, "b_aaa", "thinks about it often", loop="fly-again")
    open_loop(loops, "l_1", "fly-again", state="achieved", timescale="months",
              last_movement="2026-08-20")
    open_loop(loops, "l_2", "learn-tabla", state="advancing", timescale="months")

    ranked = Retriever(store=loops).retrieve("thinks", now=NOW)
    assert ranked.ids == ("b_zzz", "b_aaa"), "an achieved loop outranked a live one"
    assert "fly-again" in loops.state().loops, "history was deleted"
    assert LOOP_WEIGHTS[LoopState.ACHIEVED] > 0.0, "achieved must still be reachable"


def test_every_state_carries_a_weight_and_none_of_them_is_zero():
    """AD-24 as arithmetic, over the vocabulary rather than over four strings
    typed into the ranking module."""
    assert set(LOOP_WEIGHTS) == LOOP_STATES, (
        "the ranking weights and the vocabulary have drifted apart"
    )
    assert all(weight > 0.0 for weight in LOOP_WEIGHTS.values())


def test_the_states_are_ordered_advancing_first_and_achieved_last():
    assert (LOOP_WEIGHTS[LoopState.ADVANCING]
            > LOOP_WEIGHTS[LoopState.STALLED]
            > LOOP_WEIGHTS[LoopState.ABANDONED_BUT_UNADMITTED]
            > LOOP_WEIGHTS[LoopState.ACHIEVED])


# =============================================================================
# matrix: unknown state at read — read tolerant, write strict
# =============================================================================

def test_a_state_from_a_later_build_folds_and_ranks_rather_than_raising(loops):
    """A log this build did not write must still fold. The append gate is where
    an unknown state is refused; the read path degrades to the unknown weight
    rather than taking a main's whole ranking down (AD-24)."""
    belief(loops, "b_1", "thinks about it often", loop="fly-again")
    later_build_line(loops, "l_1", "2026-08-02T00:00Z",
                     loop="fly-again", state="wandering")

    state = loops.rebuild()
    assert state.loops["fly-again"]["state"] == "wandering"

    found = ledger.read(state.loops)["fly-again"]
    assert not found.known_state
    assert Retriever(store=loops).retrieve("thinks", now=NOW).ids == ("b_1",)


def test_the_unknown_weight_sits_between_a_loop_and_no_loop():
    """Being on a loop at all is information, so an unrecognised state must not
    score below having no loop — and must not outrank a state we can read."""
    from half.retrieval.salience import NO_LOOP

    assert NO_LOOP < UNKNOWN_LOOP_STATE < LOOP_WEIGHTS[LoopState.ADVANCING]


def test_the_append_gate_still_refuses_what_the_read_path_tolerates(loops):
    later_build_line(loops, "l_1", "2026-08-02T00:00Z",
                     loop="fly-again", state="wandering")
    assert loops.rebuild().loops["fly-again"]["state"] == "wandering"

    with pytest.raises(ValueError):
        loops.record(Op.LOOP_TRANSITION, "l_2", "2026-08-03T00:00Z",
                     loop="fly-again", state="wandering")


def test_the_read_path_never_raises_on_a_malformed_entry():
    """One bad entry costs that loop a tie-break, not the main's ranking."""
    found = ledger.read({
        "buy-farmland": {"state": 7, "timescale": ["years"], "last_movement": None},
        "learn-tabla": "not even a mapping",
        7: {"state": "advancing"},
    })
    assert set(found) == {"buy-farmland", "learn-tabla"}
    assert found["buy-farmland"] == Loop(id="buy-farmland")
    assert not found["buy-farmland"].silence(now=NOW).detectable


# =============================================================================
# matrix: purity and replay
# =============================================================================

def test_the_same_log_and_the_same_now_give_identical_loops(loops):
    open_loop(loops, "l_1", "buy-farmland", state="stalled", timescale="years",
              last_movement=LONG_AGO)
    open_loop(loops, "l_2", "swim-weekly", state="advancing", timescale="weeks",
              last_movement="2026-08-30T06:00Z")

    first = ledger.read(fold(loops.log).loops)
    second = ledger.read(fold(loops.log).loops)
    assert first == second

    quiet = [ledger.silent(first, now=NOW) for _ in range(5)]
    assert all(one == quiet[0] for one in quiet)


def test_silence_moves_only_when_the_injected_now_moves(loops):
    found = open_loop(loops, "l_1", "swim-weekly", state="advancing",
                      timescale="weeks", last_movement="2026-08-30T06:00Z")

    assert not found.silence(now="2026-09-02T06:00:00Z").silent
    assert found.silence(now="2026-10-02T06:00:00Z").silent


def test_no_module_under_loops_reads_a_clock():
    """Asserted here as well as in ``tests/test_purity.py``, because the module
    list there is a list somebody has to remember to extend and this globs."""
    forbidden = {"time", "datetime", "random", "os", "sys", "sqlite3", "asyncio"}
    for path in sorted((ROOT / "half/loops").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        assert not roots & forbidden, f"{path.relative_to(ROOT)} imports a clock"


def test_loops_are_identical_after_a_rebuild(tier_change_log):
    """The fixture carries opens, moves, an achieved close, a loop with no
    timescale and a loop the main expunged."""
    store = tier_change_log
    before = ledger.read(store.state().loops)
    assert len(before) >= 3, "the fixture stopped covering loops"

    store.close()
    store.db_path.unlink()

    assert ledger.read(store.rebuild().loops) == before


def test_a_loop_with_no_timescale_still_has_none_after_a_rebuild(tier_change_log):
    """The one a default would hide: a rebuild that filled the gap in would
    look like a successful replay and be a different ranking function."""
    store = tier_change_log
    store.close()
    store.db_path.unlink()

    found = ledger.read(store.rebuild().loops)["learn-tabla"]
    assert found.timescale is None
    assert found.silence(now=NOW).reason == NO_TIMESCALE


def test_an_expunged_loop_stays_expunged_after_a_rebuild(tier_change_log):
    store = tier_change_log
    store.close()
    store.db_path.unlink()

    assert "sell-the-flat" not in store.rebuild().loops


# =============================================================================
# structure: one vocabulary, one spelling, movement is not contact
# =============================================================================

def test_the_field_names_agree_between_the_ledger_and_the_append_gate():
    """Two spellings of ``last_movement`` is a loop that is permanently and
    invisibly not silent-detectable."""
    from half.store import records

    assert ledger.LOOP == records.LOOP == "loop"
    assert ledger.TIMESCALE == records.TIMESCALE == "timescale"
    assert ledger.LAST_MOVEMENT == records.LAST_MOVEMENT == "last_movement"


def test_the_fold_carries_exactly_the_fields_the_ledger_writes():
    source = (ROOT / "half/store/fold.py").read_text(encoding="utf-8")
    assert '("state", "timescale", "last_movement")' in source, (
        "the fold and the ledger disagree about what a transition carries"
    )


def test_nothing_under_loops_records_half_touching_a_loop():
    """Loop movement and Half touching a loop are different facts. What Half
    raised, and how recently, is story 5c's nagging bound and must not be
    conflated here — a touch recorded as movement would make Half's own nudge
    look like the main's progress."""
    for path in sorted((ROOT / "half/loops").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in {
                    "last_touched", "touched", "last_raised", "nagged",
                    "last_nagged", "last_surfaced",
                }, f"{path.relative_to(ROOT)} records contact, not movement"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert not any(
                    word in node.name for word in ("touch", "nag", "surface")
                ), f"{path.relative_to(ROOT)}:{node.name} is 5c's, not this story's"


def test_the_ledger_writes_nothing_itself():
    """Every function returns append *fields*; the one writer is the actor's
    store (AD-1). A ledger that opened a file would be a second writer."""
    tree = ast.parse((ROOT / "half/loops/ledger.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else node.func.id if isinstance(node.func, ast.Name) else "")
            assert name not in {"open", "write", "append", "record", "execute"}, (
                f"the ledger writes at line {node.lineno}"
            )


def test_the_loop_id_must_be_a_slug():
    for bad in ("", " ", "buy farmland", "buy-farmland\n", " buy-farmland", 7, None):
        with pytest.raises(LoopError):
            ledger.opened(bad, state="advancing")
    assert ledger.opened("buy-farmland", state="advancing")["loop"] == "buy-farmland"
    assert ledger.opened("आशा-project", state="advancing")["loop"] == "आशा-project"


def test_the_vocabulary_carries_a_version():
    from half.loops import states, timescale as scale

    assert isinstance(states.VOCABULARY_VERSION, int)
    assert states.VOCABULARY_VERSION >= 1
    assert isinstance(scale.VOCABULARY_VERSION, int)
