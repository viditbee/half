"""CAP-6 story 8: the open-loop ledger — one case per row of the I/O matrix.

Three things this file insists on.

**The firewall is asserted as a property, over the package.** *"Evidence of
non-action never refutes a wanting"* is easy to agree with and easy to violate
by accident — the natural implementation of a nightly pass that sees no movement
is to lower confidence in the belief that the loop exists. The first version of
this file asserted that two ``fold`` case bodies did not contain the substring
``"loops"``, which is a *spelling*, and three mutations walked straight past it:
a demotion in the ``Op.TENSION`` branch, the same demotion moved into a
module-scope helper, and a new ``half/loops/decay.py`` exporting ``demote``. So
the guards below assert the property instead — that within ``fold`` only the
transition case and the loop-named expunge block may so much as *name* the loop
table, that nothing anywhere under ``half/`` mutates it outside those two
places, and that only the ledger's sanctioned functions can produce a loop
``state`` field at all. Each is checked against a synthetic bypass of its own,
so none can pass having seen nothing.

**And a loop left standing must still move.** Every refutation case below runs a
transition *after* the correction and asserts it lands. Stopping at the fold was
how a shared ``expunged`` set could freeze a wanting for ever — present in the
fold, which every firewall test asserted, and silently unable to advance, be
achieved, or change at all — with the whole suite green.

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

from half.civil import DAY, instant
from half.errors import HalfError, LoopError, StoreError
from half.loops import ledger
from half.loops.ledger import ABANDONMENT_PERIODS, AbandonmentCandidate, Answer, Loop
from half.loops.states import LIVE_STATES, LOOP_STATES, LoopState, is_state, parse_state
from half.loops.timescale import (
    DAY_STARTS_AT,
    NO_MOVEMENT,
    NO_TIMESCALE,
    PERIOD_DAYS,
    TIMESCALES,
    UNKNOWN_TIMESCALE,
    UNREADABLE_MOVEMENT,
    UNREADABLE_NOW,
    Timescale,
    moment,
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

#: When a transition is *written*, as opposed to the movement date it carries.
#: After every open in this file, so fold order follows the story being told.
RECORDED_AT = "2026-08-31T00:00Z"


@pytest.fixture
def loops(tmp_path):
    """A store wired the way the running product wires it: prefixes indexed."""
    with Store(tmp_path / "main", prefix=build_prefix) as store:
        yield store


def open_loop(store, ident, loop_id, **kw):
    t = kw.pop("t", "2026-08-01T00:00Z")
    kw.setdefault("loops", store.state().loops)
    store.record(Op.LOOP_TRANSITION, ident, t, **ledger.opened(loop_id, **kw))
    return ledger.read(store.state().loops)[loop_id]


def move_loop(store, ident, loop_id, at, **kw):
    """Record movement, and hand back the loop as the fold now holds it.

    Every refutation case ends with one of these: a loop that stands but can no
    longer move has been demoted under another name.
    """
    # ``t`` is when the record was *written* and defaults to a stamp after
    # every open in this file — deriving it from ``at`` conflated the two, so a
    # backdated movement folded before the open that created the loop and the
    # open silently won.
    t = kw.pop("t", RECORDED_AT)
    store.record(Op.LOOP_TRANSITION, ident, t, **ledger.move(loop_id, at=at, **kw))
    return ledger.read(store.state().loops).get(loop_id)


def at_days(days: float, *, since: str = "2026-09-01T09:00:00Z") -> str:
    """A stamp exactly ``days`` before ``since``, to the second.

    Exact-boundary cases need arithmetic, not eyeballed dates: *"elapsed exactly
    one period"* is only an assertion if the stamp really is exactly one period
    back. Built with the same civil arithmetic the module under test uses, and
    checked against it in ``test_the_boundary_helper_is_exact``.
    """
    base = instant(since)
    assert base is not None, since
    seconds = base - int(round(days * DAY))
    day, rest = divmod(seconds, DAY)
    hour, rest = divmod(rest, 3600)
    minute, second = divmod(rest, 60)
    # Reverse of civil.days_from_civil, by search over a small window: exact,
    # and it keeps the test from importing a second date library.
    year = 1970
    remaining = day
    while True:
        length = 366 if _leap(year) else 365
        if remaining < length:
            break
        remaining -= length
        year += 1
    month = 1
    lengths = [31, 29 if _leap(year) else 28, 31, 30, 31, 30,
               31, 31, 30, 31, 30, 31]
    for size in lengths:
        if remaining < size:
            break
        remaining -= size
        month += 1
    return (f"{year:04d}-{month:02d}-{remaining + 1:02d}"
            f"T{hour:02d}:{minute:02d}:{second:02d}Z")


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


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
        ledger.opened("buy-farmland", state="stale", loops={})


@pytest.mark.parametrize("state", sorted(LOOP_STATES))
def test_every_state_in_the_vocabulary_is_accepted_by_the_append_gate(loops, state):
    """Non-vacuity for the row above: a gate that refused everything would
    pass every case there and ship a ledger nothing could write to.

    Asserted at the *gate* rather than through ``ledger.opened``, because the
    ledger deliberately refuses one of the four — `abandoned-but-unadmitted`
    has its own path and the main's confirmation (CAP-10). The vocabulary is
    still four wide where the log is concerned.
    """
    loops.record(Op.LOOP_TRANSITION, f"l_{state}", "2026-08-01T00:00Z",
                 loop=f"loop-{state}", state=state)
    assert ledger.read(loops.state().loops)[f"loop-{state}"].state == state


@pytest.mark.parametrize("builder", ["opened", "move"])
def test_no_ledger_function_applies_abandonment_on_inference_alone(builder):
    """CAP-10, and the gate is **every** function that sets a state.

    It used to be one function wide: ``move`` refused
    `abandoned-but-unadmitted` and ``opened`` accepted it, so a loop could be
    opened straight into the state that exists to be asked about.
    """
    call = {
        "opened": lambda: ledger.opened(
            "buy-farmland", state="abandoned-but-unadmitted", loops={}),
        "move": lambda: ledger.move(
            "buy-farmland", at="2026-08-01", state="abandoned-but-unadmitted"),
    }[builder]
    with pytest.raises(LoopError):
        call()


def test_every_function_that_sets_a_state_refuses_abandonment():
    """The property behind the two cases above, so a *third* state-setting
    function added later is covered on the day it is written rather than on the
    day somebody remembers this file exists."""
    import inspect

    setters = []
    for name, function in vars(ledger).items():
        if name.startswith("_") or not inspect.isfunction(function):
            continue
        parameters = inspect.signature(function).parameters
        if "state" in parameters or "to" in parameters:
            setters.append(name)
    assert set(setters) == {"opened", "move", "rescale"}, (
        f"a state-setting function appeared that this gate has not been told "
        f"about: {sorted(setters)}"
    )


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
# matrix: unreadable movement, and the loop a transition must name
# =============================================================================

@pytest.mark.parametrize(
    "moved",
    ["yesterday", "2026-02-31T00:00Z", "2026-02-29T00:00Z", "0001-01-01",
     "9999-01-01", "2026-01-01T00:00:00+05:30", "", 17, ["2026-01-01"]],
)
def test_a_movement_date_the_build_cannot_read_is_refused_at_the_append(
    loops, moved
):
    """Matrix: *unreadable movement — refused at the append, never durable*.

    The gate argued at length that a bad timescale must not become durable and
    then let ``last_movement="yesterday"`` and ``2026-02-31`` straight through.
    The argument is identical: a movement date nothing can read is a loop whose
    silence — and therefore whose nagging bound — can never be computed, for
    ever, with no way to take the record back.
    """
    with pytest.raises(LoopError):
        loops.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                     loop="buy-farmland", state="stalled", last_movement=moved)
    assert loops.state().loops == {}
    assert not (loops.log.root / "2026-08.jsonl").exists()


@pytest.mark.parametrize("moved", ["2026-01-01", "2026-01-01T09:00Z",
                                   "2026-01-01T09:00:00Z"])
def test_a_movement_date_the_build_can_read_is_accepted(loops, moved):
    """Non-vacuity: a gate that refused every shape would pass the row above
    and ship a ledger no movement could be recorded in."""
    open_loop(loops, "l_1", f"loop-{moved}", state="stalled",
              timescale="months", last_movement=moved)
    assert ledger.read(loops.state().loops)[f"loop-{moved}"].last_movement == moved


def test_a_transition_that_names_no_loop_is_refused_at_the_append(loops):
    """It became durable and then bricked every future rebuild.

    The fold raises ``CorruptLogError`` on a transition with no ``loop``, and
    the derived view is rebuilt after every append — so one such record made
    every later rebuild, and therefore every later append, raise for ever, with
    the offending line unremovable. Exactly the failure this gate exists to
    prevent, arriving through the gate's own blind spot.
    """
    for missing in ({}, {"loop": ""}, {"loop": "  "}, {"loop": None},
                    {"loop": 7}):
        with pytest.raises(LoopError):
            loops.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                         state="stalled", **missing)
    assert not (loops.log.root / "2026-08.jsonl").exists()

    # And the store still works afterwards, which is the property that was
    # actually lost: a durable record like this poisoned every later append.
    open_loop(loops, "l_ok", "buy-farmland", state="stalled")
    assert "buy-farmland" in loops.state().loops


def test_the_gate_refuses_a_hand_built_record_through_the_append_path(loops):
    """``Store.append`` and ``records.make`` both validate, and the two were
    each redundant with the other — dropping ``op=`` from either left the suite
    green. This exercises the one no test reached: a ``Record`` assembled
    elsewhere and handed straight to the store."""
    data = {"t": "2026-08-01T00:00Z", "op": Op.LOOP_TRANSITION.value,
            "id": "l_1", "v": SCHEMA_VERSION,
            "loop": "buy-farmland", "state": "widening"}
    hand_built = Record(op=Op.LOOP_TRANSITION, id="l_1", t="2026-08-01T00:00Z",
                        data=data)

    with pytest.raises(LoopError):
        loops.append(hand_built)
    assert not (loops.log.root / "2026-08.jsonl").exists()


def test_the_append_gate_refuses_with_a_typed_domain_error(loops):
    """The conventions say no public store operation raises a non-``HalfError``,
    and these refusals were bare ``ValueError``s — so a caller wrapping the
    write path in ``except LoopError`` missed the gate entirely. They answer to
    both names, because ``validate_fields`` has raised ``ValueError`` for every
    other malformed field since story 1."""
    for fields in ({"loop": "x", "state": "widening"},
                   {"loop": "x", "timescale": "decades"},
                   {"loop": "x", "last_movement": "yesterday"},
                   {"state": "stalled"}):
        for expected in (LoopError, HalfError, ValueError):
            with pytest.raises(expected):
                loops.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                             **fields)


def test_a_state_word_from_another_vocabulary_is_refused_on_a_loop(loops):
    """``state`` names four closed vocabularies — tension, crisis, aftercare
    and loop — so an op-blind check would have to accept the union of all four.
    """
    for foreign in ("fresh", "widening", "closing", "resolved", "entered",
                    "reversed", "asked", "declined", "agreed", "stopped"):
        with pytest.raises(LoopError):
            loops.record(Op.LOOP_TRANSITION, "l_1", "2026-08-01T00:00Z",
                         loop="buy-farmland", state=foreign)


def test_the_other_vocabularies_still_accept_their_own_words(loops):
    """The mirror, so the op-aware gate cannot have been implemented by
    narrowing every op to the loop vocabulary."""
    from half.governance import ladder

    loops.record(Op.TENSION, "x_1", "2026-08-01T00:00Z", state="widening",
                 between=["b_1", "b_2"], **ladder.admitted())
    loops.record(Op.CRISIS, "cr_1", "2026-08-01T00:01Z", state="entered")
    loops.record(Op.AFTERCARE, "ac_1", "2026-08-01T00:02Z", state="asked")

    assert loops.state().tensions["x_1"]["state"] == "widening"
    assert loops.state().crisis["state"] == "entered"


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


@pytest.mark.parametrize(
    "moved", ["not-a-date", "2026-02-31", "0001-01-01", "2026-13-01", 17,
              "2026-01-01T00:00:00+05:30", "yesterday"],
)
def test_a_movement_stamp_that_is_not_an_instant_reports_unreadable(moved):
    """The reason is asserted **exactly**, not as a membership in a pair.

    ``reason in {UNREADABLE_MOVEMENT, NO_MOVEMENT}`` made the two constants
    interchangeable, so a build that reported *"never moved"* for a date it
    simply could not parse passed — and those want opposite fixes.
    """
    quiet = silence({"timescale": "years", "last_movement": moved}, now=NOW)
    assert not quiet.detectable and not quiet.silent
    assert quiet.reason == UNREADABLE_MOVEMENT, moved


@pytest.mark.parametrize("moved", [None, "", "   "])
def test_a_loop_that_never_moved_reports_no_movement_and_not_unreadable(moved):
    quiet = silence({"timescale": "years", "last_movement": moved}, now=NOW)
    assert quiet.reason == NO_MOVEMENT, moved


@pytest.mark.parametrize(
    "bad_now", ["not-a-date", "2026-02-31T00:00Z", "0001-01-01T00:00Z", 17,
               None, "", "2026-09-01T09:00:00+05:30"],
)
def test_an_unreadable_now_is_undetectable_and_never_silent(bad_now):
    """The branch review found referenced by no test at all.

    Replacing it with ``Silence(detectable=True, silent=True, periods=99.0)``
    left the whole suite green — and at ninety-nine periods *every* loop
    becomes an abandonment candidate, so Half proposes that the main has given
    up on everything. That is the one asymmetric failure this module exists to
    make impossible.
    """
    quiet = silence(
        {"timescale": "days", "last_movement": "2020-01-01"}, now=bad_now
    )
    assert not quiet.detectable, bad_now
    assert not quiet.silent, bad_now
    assert quiet.reason == UNREADABLE_NOW, bad_now
    assert quiet.periods is None, bad_now


@pytest.mark.parametrize(
    "bad_now", ["not-a-date", "2026-02-31T00:00Z", 17, None, ""],
)
def test_no_unreadable_now_can_produce_an_abandonment_candidate(bad_now):
    """The consequence, asserted where it lands rather than only at the source."""
    loop = Loop(id="buy-farmland", state="stalled", timescale="days",
                last_movement="2020-01-01")
    assert ledger.abandonment_candidate(loop, now=bad_now) is None, bad_now
    assert ledger.silent({"buy-farmland": loop}, now=bad_now) == {}, bad_now


def test_now_and_last_movement_agree_about_what_a_stamp_is():
    """The two used to disagree: ``last_movement`` widened a bare date and
    ``now`` did not, so a caller working in bare dates got ``unreadable-now``
    for every loop it owned — a silent, total loss of detection."""
    entry = {"timescale": "days", "last_movement": "2026-01-01"}
    bare = silence(entry, now="2026-09-01")
    full = silence(entry, now="2026-09-01T00:00Z")

    assert bare.detectable and bare == full


@pytest.mark.parametrize("shape", ["2026-09-01", "2026-09-01T09:00Z",
                                   "2026-09-01T09:00:00Z"])
def test_every_stamp_shape_the_log_carries_is_readable_on_both_sides(shape):
    assert moment(shape) is not None
    assert silence({"timescale": "days", "last_movement": shape},
                   now=NOW).detectable


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


def test_every_period_is_pinned_to_its_value():
    """**Values, not a band.** Review moved ``days`` from 1 to 6 and ``weeks``
    from 7 to 29 with the whole suite green, which means nobody had chosen
    them: a constant a test cannot see being wrong is a constant nobody owns.

    Written as literals on purpose, in the style of the vocabulary test above.
    A test phrased in terms of the constant it guards cannot see that constant
    move.
    """
    assert dict(PERIOD_DAYS) == {
        Timescale.DAYS: 1,
        Timescale.WEEKS: 7,
        Timescale.MONTHS: 30,
        Timescale.YEARS: 365,
    }
    assert set(PERIOD_DAYS) == set(TIMESCALES), (
        "a timescale with no period, or a period with no timescale"
    )


def test_the_boundary_helper_is_exact():
    """The exact-boundary cases below are only assertions if the stamps they
    are built from really are exact."""
    for days in (0, 1, 7, 12, 30, 365, 0.5):
        built = at_days(days)
        assert moment(NOW) - moment(built) == int(round(days * DAY)), days


@pytest.mark.parametrize("scale", sorted(TIMESCALES))
def test_exactly_one_period_is_not_silent_and_a_second_later_is(scale):
    """**The comparison is ``>``, and the boundary is asserted on both sides.**

    Review flipped it to ``>=`` with the suite green, because no case sat at
    exactly one period. The direction is a real decision: a weekly swim swum
    seven days ago is a loop keeping to its own rhythm, not one that has gone
    quiet, and ``>=`` would put every perfectly-kept loop into the silent set
    for ever.
    """
    period = PERIOD_DAYS[Timescale(scale)]
    entry = {"timescale": scale}

    exact = silence({**entry, "last_movement": at_days(period)}, now=NOW)
    assert exact.detectable and exact.periods == 1.0
    assert not exact.silent, f"exactly one period is not yet silence ({scale})"

    over = silence(
        {**entry, "last_movement": at_days(period + 1 / DAY)}, now=NOW
    )
    assert over.detectable and over.silent, (
        f"one second past its period, a {scale}-loop is silent"
    )


def test_the_periods_are_ordered_and_none_of_them_is_shared():
    ordered = [PERIOD_DAYS[Timescale(s)]
               for s in ("days", "weeks", "months", "years")]
    assert ordered == sorted(ordered)
    assert len(set(ordered)) == len(ordered), "two scales share a period"


def test_a_bare_date_is_widened_to_the_start_of_that_day():
    """Pinned because review moved it to ``T23:59Z`` with the suite green,
    which makes every bare-date loop up to a day fresher than it is — the
    direction that lets Half stay quiet about something it should raise."""
    assert DAY_STARTS_AT == "T00:00Z"
    assert moment("2026-03-12") == instant("2026-03-12T00:00Z")
    assert moment("2026-03-12") != instant("2026-03-12T23:59Z")


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


def test_a_finished_loop_that_has_not_moved_is_not_reported_as_silent(loops):
    """Matrix: *achieved and quiet*. Finished is not silent.

    ``silent()`` is documented as the ranking input and the whole reason the
    ledger exists, so a filter that reported achieved loops would have stories
    9 and 10 raising a wanting the main already completed — the single most
    trust-destroying thing this input could produce. Before this it filtered
    only on detectable-and-silent, with no state filter at all.
    """
    open_loop(loops, "l_1", "swim-weekly", state="advancing", timescale="weeks",
              last_movement="2020-01-01")
    move_loop(loops, "l_2", "swim-weekly", "2020-01-01", state="achieved")
    open_loop(loops, "l_3", "buy-farmland", state="stalled", timescale="years",
              last_movement="2020-01-01")

    found = ledger.read(loops.state().loops)
    assert found["swim-weekly"].silence(now=NOW).silent, (
        "the raw computation is unchanged; it is the ranking input that filters"
    )
    assert set(ledger.silent(found, now=NOW)) == {"buy-farmland"}


@pytest.mark.parametrize(
    "state,reported",
    [("advancing", True), ("stalled", True),
     ("achieved", False), ("abandoned-but-unadmitted", False),
     ("wandering", False), (None, False)],
)
def test_silent_reports_exactly_the_live_states(state, reported):
    """One case per state, including a later build's and none at all, so the
    filter cannot be right by coincidence for the two that matter."""
    loop = Loop(id="a", state=state, timescale="days",
                last_movement="2020-01-01")
    assert bool(ledger.silent({"a": loop}, now=NOW)) is reported, state


def test_the_live_states_are_exactly_the_two_that_can_still_move():
    assert LIVE_STATES == {"advancing", "stalled"}
    assert LIVE_STATES < LOOP_STATES


# =============================================================================
# opening is not moving, and re-scaling is neither
# =============================================================================

def test_a_loop_cannot_be_opened_twice(loops):
    """``opened`` and ``move`` used to be indistinguishable at the log: the fold
    merges by ``setdefault``, so re-opening a live loop silently overwrote its
    state and its timescale, dropped its ``last_movement``, and raised nothing.
    """
    open_loop(loops, "l_1", "swim-weekly", state="advancing", timescale="weeks",
              last_movement="2026-08-20T06:00Z")

    with pytest.raises(LoopError) as raised:
        ledger.opened("swim-weekly", state="stalled", loops=loops.state().loops)
    assert "already open" in str(raised.value)

    still = ledger.read(loops.state().loops)["swim-weekly"]
    assert still.state == "advancing"
    assert still.timescale == "weeks"
    assert still.last_movement == "2026-08-20T06:00Z"


def test_opening_requires_the_current_loop_table():
    """Required, not optional-with-a-default: an optional argument is a check
    the caller can forget, which is the same as no check."""
    with pytest.raises(TypeError):
        ledger.opened("swim-weekly", state="advancing")
    for not_a_table in (None, "loops", 7):
        with pytest.raises(LoopError):
            ledger.opened("swim-weekly", state="advancing", loops=not_a_table)


def test_movement_cannot_change_a_loops_timescale():
    """It could, as a passenger on an ordinary movement append — so one call
    could flip a years-loop to days, making it instantly silent and instantly
    abandonment-eligible while looking on the record like the main having done
    something. Changing how fast a wanting is *supposed* to move is a judgement
    about the wanting, so it has its own named call.
    """
    import inspect

    assert "timescale" not in inspect.signature(ledger.move).parameters
    with pytest.raises(TypeError):
        ledger.move("buy-farmland", at="2026-08-01", timescale="days")


def test_rescale_is_its_own_operation_and_carries_no_movement(loops):
    open_loop(loops, "l_1", "learn-tabla", state="advancing",
              last_movement="2026-08-20T06:00Z")

    fields = ledger.rescale("learn-tabla", to="months", loops=loops.state().loops)
    assert fields == {"loop": "learn-tabla", "timescale": "months"}
    assert "last_movement" not in fields, (
        "re-scaling a loop is not the loop moving; a date here would reset the "
        "very silence the new period is there to measure"
    )

    loops.record(Op.LOOP_TRANSITION, "l_2", "2026-08-21T00:00Z", **fields)
    after = ledger.read(loops.state().loops)["learn-tabla"]
    assert after.timescale == "months"
    assert after.last_movement == "2026-08-20T06:00Z"


def test_rescale_refuses_a_loop_it_cannot_see_and_a_change_that_is_none(loops):
    with pytest.raises(LoopError):
        ledger.rescale("learn-tabla", to="months", loops={})

    open_loop(loops, "l_1", "learn-tabla", state="advancing", timescale="months")
    with pytest.raises(LoopError):
        ledger.rescale("learn-tabla", to="months", loops=loops.state().loops)


# =============================================================================
# matrix: the refutation firewall — nothing demotes a wanting
# =============================================================================

@pytest.mark.cap6_firewall
@pytest.mark.parametrize("correct", ["retract", "revise", "expunge"])
def test_a_loop_stands_and_still_moves_when_its_only_support_is_corrected(
    loops, correct
):
    """The three matrix rows, and the half that was missing from all of them.

    Every one of these used to stop at the fold immediately after the
    correction, asserting that the loop was still *there*. A loop that is there
    and can never move again has been demoted under another name — it can no
    longer advance, be achieved, or change at all — so each case now records
    movement afterwards and asserts it lands.
    """
    belief(loops, "b_1", "wants to buy farmland", loop="buy-farmland")
    before = open_loop(loops, "l_1", "buy-farmland", state="advancing",
                       timescale="years", last_movement=LONG_AGO)

    if correct == "expunge":
        loops.expunge("b_1", t="2026-08-02T00:00Z")
        assert "b_1" in loops.state().expunged, "the belief must actually go"
    else:
        op = Op.RETRACT if correct == "retract" else Op.REVISE
        loops.record(op, "c_1", "2026-08-02T00:00Z", target="b_1")

    assert "b_1" not in loops.state().beliefs, "the belief must actually go"
    assert ledger.read(loops.state().loops)["buy-farmland"] == before

    after = move_loop(loops, "l_2", "buy-farmland", "2026-08-20T09:00Z",
                      state="achieved")
    assert after is not None, "the loop stands but can no longer move"
    assert after.state == "achieved"
    assert after.last_movement == "2026-08-20T09:00Z"


@pytest.mark.cap6_firewall
@pytest.mark.parametrize("op", [Op.RETRACT, Op.REVISE, Op.EXPUNGE])
def test_a_correction_naming_the_loop_id_itself_leaves_it_standing_and_moving(
    loops, op
):
    """The collision case, which is the one an accident actually looks like.

    ``target`` reaches beliefs and tensions; it takes a second, explicit
    ``loop`` field to reach a wanting. But *standing* was never the whole
    property: the transition guard consulted the same ``expunged`` set the
    belief erasure wrote into, so this loop stood in the fold — passing every
    firewall assertion — while every later transition on it was silently
    dropped, for ever, with nothing raised.

    The loop starts `advancing` deliberately. The earlier fixture opened it
    already `stalled`, so a demote-to-stalled would have been invisible.
    """
    before = open_loop(loops, "l_1", "buy-farmland", state="advancing",
                       timescale="years", last_movement=LONG_AGO)

    loops.record(op, "c_1", "2026-08-02T00:00Z", target="buy-farmland")

    assert ledger.read(loops.state().loops)["buy-farmland"] == before

    after = move_loop(loops, "l_2", "buy-farmland", "2026-08-20T09:00Z",
                      state="achieved")
    assert after is not None, (
        "the correction froze the loop: it stands but no transition lands"
    )
    assert after.state == "achieved"


@pytest.mark.cap6_firewall
def test_erasing_a_loop_does_not_suppress_a_belief_sharing_its_name(loops):
    """The poisoning in the other direction, which one shared set also caused."""
    open_loop(loops, "l_1", "buy-farmland", state="advancing", timescale="years")
    loops.expunge("buy-farmland", t="2026-08-02T00:00Z")

    belief(loops, "buy-farmland", "still a claim about the main",
           t="2026-08-03T00:00Z")
    assert "buy-farmland" in loops.state().beliefs, (
        "erasing a loop suppressed a belief that shares its identifier"
    )


@pytest.mark.cap6_firewall
def test_the_two_expunged_namespaces_stay_apart(loops):
    open_loop(loops, "l_1", "buy-farmland", state="advancing", timescale="years")
    belief(loops, "b_1", "a claim")
    loops.expunge("b_1", t="2026-08-02T00:00Z")
    loops.expunge("buy-farmland", t="2026-08-03T00:00Z")

    state = loops.state()
    assert state.expunged == {"b_1"}
    assert state.expunged_loops == {"buy-farmland"}


@pytest.mark.cap6_firewall
def test_a_tombstoned_record_sharing_a_loops_identifier_leaves_the_loop(loops):
    """A tombstone erases one record's body and is keyed on that record's own
    id. Before the firewall it also popped the loop table, so a belief that
    happened to share a loop's slug deleted a wanting."""
    before = open_loop(loops, "l_1", "buy-farmland", state="advancing",
                       timescale="years", last_movement=LONG_AGO)
    loops.log.append(make(Op.ASSERT, "buy-farmland", "2026-08-02T00:00Z",
                          tombstone=True))

    assert ledger.read(loops.rebuild().loops)["buy-farmland"] == before

    after = move_loop(loops, "l_2", "buy-farmland", "2026-08-20T09:00Z")
    assert after is not None and after.last_movement == "2026-08-20T09:00Z"


@pytest.mark.cap6_firewall
def test_no_evidence_for_a_year_leaves_the_wanting_true_and_only_stalled(loops):
    """Matrix: nothing supports the wanting and nothing contradicts it.

    The state may be `stalled`. There is no code path from that to *"this
    wanting is not real"* — which is asserted as an absence: after a year of
    nothing, the loop is present, in the vocabulary, no op in the log claims
    otherwise, and it can still move.
    """
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="years", last_movement="2025-08-01")

    assert found.silence(now=NOW).silent
    assert found.state == "stalled"
    assert is_state(found.state)
    assert "buy-farmland" not in loops.state().expunged_loops
    assert ledger.read(loops.state().loops)["buy-farmland"] == found

    after = move_loop(loops, "l_2", "buy-farmland", "2026-08-30T09:00Z",
                      state="advancing")
    assert after is not None and after.state == "advancing"


# -- the firewall as a property of the fold, not a spelling in two branches ---
#
# Everything below replaces a substring check that three mutations walked past.
# Each guard is run against a synthetic bypass of its own, so none can pass
# having found nothing to look at.


def _fold_function() -> ast.FunctionDef:
    tree = ast.parse((ROOT / "half/store/fold.py").read_text(encoding="utf-8"))
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "fold"
    )


def _sanctioned_regions(function: ast.FunctionDef) -> list[tuple[int, int]]:
    """The two places in ``fold`` allowed to touch the loop table.

    The ``Op.LOOP_TRANSITION`` case, and the ``if`` block inside the
    ``Op.EXPUNGE`` case that is guarded on the record naming a loop. Returned as
    line spans, discovered from the tree rather than listed, so the regions
    move when the code does.
    """
    match_node = next(
        node for node in ast.walk(function) if isinstance(node, ast.Match)
    )
    regions: list[tuple[int, int]] = []
    for case in match_node.cases:
        pattern = {ast.unparse(node.value) for node in ast.walk(case.pattern)
                   if isinstance(node, ast.MatchValue)}
        if "Op.LOOP_TRANSITION" in pattern:
            regions.append((case.body[0].lineno, case.body[-1].end_lineno))
        elif "Op.EXPUNGE" in pattern:
            # The block that removes a loop, found by *what it does* rather
            # than by position: an ``if`` whose test reads the record's loop
            # field and whose body touches the loop table. The case has other
            # ``loop_target`` guards that must not be sanctioned by accident.
            guarded = [
                node for node in case.body
                if isinstance(node, ast.If)
                and "loop_target" in ast.unparse(node.test)
                and _names_the_loop_table(node)
            ]
            assert len(guarded) == 1, (
                "the expunge case no longer has exactly one loop-removal block "
                "guarded on the record naming a loop; the firewall's one door "
                "is unlatched or duplicated"
            )
            regions.append(
                (guarded[0].body[0].lineno, guarded[0].body[-1].end_lineno)
            )
    assert len(regions) == 2, f"expected two sanctioned regions, found {regions}"
    return regions


def _names_the_loop_table(node: ast.AST) -> bool:
    return any(
        isinstance(inner, ast.Attribute) and inner.attr == "loops"
        for inner in ast.walk(node)
    )


@pytest.mark.cap6_structure
def test_only_two_regions_of_the_fold_may_name_the_loop_table():
    """Mention-level, not mutation-level, and inside ``fold`` that is the point.

    A branch that may *read* ``state.loops`` may bind it to a local and mutate
    the local, which no mutation scan sees. So no other branch may name it at
    all: the ``Op.TENSION`` demotion that walked past the old guard —
    ``state.loops[contested]["state"] = "stalled"``, Half lowering a wanting
    because contradicting evidence arrived — fails here on the read.
    """
    function = _fold_function()
    allowed = _sanctioned_regions(function)
    offenders = [
        (node.lineno, ast.unparse(node))
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute) and node.attr == "loops"
        and not any(low <= node.lineno <= high for low, high in allowed)
    ]
    assert not offenders, (
        f"fold names the loop table outside the transition case and the "
        f"loop-named expunge block: {offenders}. A wanting is not a fact and "
        f"nothing may refute one (CAP-6)"
    )


@pytest.mark.cap6_structure
def test_the_fold_guard_catches_a_demotion_in_another_branch():
    """The guard above, run against the exact mutation that beat its
    predecessor. A gate nobody has tried to defeat is a gate nobody has tested.
    """
    source = (ROOT / "half/store/fold.py").read_text(encoding="utf-8")
    poisoned = source.replace(
        "            case Op.TENSION:\n",
        "            case Op.TENSION:\n"
        "                contested = record.data.get('loop')\n"
        "                if contested in state.loops:\n"
        "                    state.loops[contested]['state'] = 'stalled'\n",
        1,
    )
    assert poisoned != source, "the fixture no longer matches the fold's source"

    function = next(
        node for node in ast.walk(ast.parse(poisoned))
        if isinstance(node, ast.FunctionDef) and node.name == "fold"
    )
    allowed = _sanctioned_regions(function)
    offenders = [
        node.lineno for node in ast.walk(function)
        if isinstance(node, ast.Attribute) and node.attr == "loops"
        and not any(low <= node.lineno <= high for low, high in allowed)
    ]
    assert offenders, "the fold guard would not notice a demotion in Op.TENSION"


#: Every way a dict can be changed in place. A helper that reached the loop
#: table through any of them is the mutation the package-wide scan looks for.
_MUTATORS = {"pop", "popitem", "setdefault", "update", "clear",
             "__setitem__", "__delitem__"}

#: The only places under ``half/`` allowed to change a ``State``'s loop table.
#: ``db.read_state`` is a **deserializer**: it materializes rows the fold itself
#: produced, and the replay test compares its output byte-for-byte against a
#: fresh fold, so a demotion there fails ``test_fold_matches_the_database_view``.
_MUTATION_ALLOWLIST = {
    ("half/store/fold.py", "fold"),
    ("half/store/db.py", "read_state"),
}


def _loop_table_mutations(tree: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = []
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in _MUTATORS):
            targets = [node.func.value]
        if any(_names_the_loop_table(target) for target in targets):
            found.append(node)
    return found


@pytest.mark.cap6_structure
def test_nothing_in_the_package_mutates_the_loop_table_outside_the_fold():
    """The package-wide half. Scanning one file was how a demotion moved into a
    module-scope helper — or into a brand new module — and passed."""
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (relative, node.name) in _MUTATION_ALLOWLIST:
                continue
            for mutation in _loop_table_mutations(node):
                offenders.append(f"{relative}:{mutation.lineno}")
    assert not offenders, (
        f"a loop table is changed outside the fold's two sanctioned regions: "
        f"{offenders}"
    )


@pytest.mark.cap6_structure
@pytest.mark.parametrize(
    "bypass",
    ["state.loops.pop(target, None)",
     "state.loops[target]['state'] = 'stalled'",
     "del state.loops[target]",
     "state.loops.update({target: {}})",
     "state.loops.setdefault(target, {})"],
)
def test_the_mutation_scan_catches_every_way_a_dict_is_changed(bypass):
    """Non-vacuity, one shape at a time. A scan that only knew about ``pop``
    would have passed the subscript assignment that beat its predecessor."""
    tree = ast.parse(f"def _helper(state, target):\n    {bypass}\n")
    assert _loop_table_mutations(tree), f"the scan does not see {bypass!r}"


_LOOP_KEYS = {"LOOP", "'loop'", '"loop"'}
_STATE_KEYS = {"STATE", "'state'", '"state"'}


def _composes_a_loop_state(scope: ast.AST) -> list[int]:
    """Line numbers where ``scope`` builds a record carrying a loop *and* a state.

    Both shapes, because a scan that knew only one of them is a scan somebody
    walks around by writing the other:

    * the dict literal — ``{"loop": id, "state": "stalled"}``;
    * the incremental build — ``fields = {}`` then ``fields["loop"] = ...`` and
      ``fields["state"] = ...``, which is exactly how the ledger's own
      ``opened`` and ``move`` are written.
    """
    found: list[int] = []
    for node in ast.walk(scope):
        if isinstance(node, ast.Dict):
            keys = {ast.unparse(key) for key in node.keys if key is not None}
            if _LOOP_KEYS & keys and _STATE_KEYS & keys:
                found.append(node.lineno)

    # Keys accumulated per local name, from both the dict a name is bound to
    # and every later subscript assignment on it. Merging the two is what
    # catches the mixed shape ``ledger.move`` is actually written in — a dict
    # literal carrying the loop, then ``fields[STATE] = ...`` a few lines down.
    assigned: dict[str, set[str]] = {}
    lines: dict[str, int] = {}
    for node in ast.walk(scope):
        if isinstance(node, (ast.AnnAssign, ast.Assign)):
            targets = ([node.target] if isinstance(node, ast.AnnAssign)
                       else list(node.targets))
            for target in targets:
                if (isinstance(target, ast.Name)
                        and isinstance(node.value, ast.Dict)):
                    keys = {ast.unparse(key) for key in node.value.keys
                            if key is not None}
                    assigned.setdefault(target.id, set()).update(keys)
                    lines.setdefault(target.id, node.lineno)
                elif (isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)):
                    assigned.setdefault(target.value.id, set()).add(
                        ast.unparse(target.slice)
                    )
                    lines.setdefault(target.value.id, node.lineno)
    for name, keys in assigned.items():
        if _LOOP_KEYS & keys and _STATE_KEYS & keys:
            found.append(lines[name])
    return found


@pytest.mark.cap6_structure
def test_only_the_ledger_can_produce_a_loop_state_field():
    """The third door, and the one a whole new module walks through.

    A mutation scan sees a fold being changed; it does not see a
    ``half/loops/decay.py`` whose ``demote()`` returns
    ``{"loop": id, "state": "stalled"}`` for somebody to append. So this asserts
    that every expression in the tree composing *both* a loop field and a state
    field lives in the ledger — the way ``test_safetyplan`` asserts that only
    one expression in the tree can write a safety plan.
    """
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno in _composes_a_loop_state(tree):
            offenders.append(f"{relative}:{lineno}")
    assert offenders, "the scan found no loop-state expression at all"
    assert all(o.startswith("half/loops/ledger.py:") for o in offenders), (
        f"a loop state is composed outside the ledger: {offenders}"
    )


@pytest.mark.cap6_structure
@pytest.mark.parametrize(
    "shape",
    ["""def demote(loop_id):
    return {"loop": loop_id, "state": "stalled"}""",
     """def demote(loop_id):
    fields = {}
    fields["loop"] = loop_id
    fields["state"] = "stalled"
    return fields""",
     """def demote(loop_id):
    fields = {LOOP: loop_id}
    fields[STATE] = "stalled"
    return fields"""],
    ids=["dict-literal", "incremental-strings", "incremental-constants"],
)
def test_the_loop_state_scan_catches_both_ways_a_record_is_built(shape):
    """Non-vacuity. A scan that knew only the dict literal is one somebody
    walks around by writing the four lines the ledger itself is written in."""
    assert _composes_a_loop_state(ast.parse(shape)), shape


@pytest.mark.cap6_structure
def test_no_module_under_loops_offers_a_way_to_refute_or_demote_a_loop():
    """Globbed over the package, not read off one filename — which is how a new
    ``half/loops/decay.py`` slipped past. And no function anywhere in the ledger
    takes belief evidence as an input, so there is no argument through which a
    retraction could reach a loop's state."""
    import inspect

    banned = {"refute", "demote", "decay", "disprove", "invalidate", "lower"}
    for path in sorted((ROOT / "half/loops").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert not names & banned, (
            f"{path.relative_to(ROOT)} offers {sorted(names & banned)}"
        )

    for name, function in vars(ledger).items():
        if name.startswith("_") or not inspect.isfunction(function):
            continue
        arguments = set(inspect.signature(function).parameters)
        assert not arguments & {"belief", "beliefs", "support", "evidence"}, (
            f"ledger.{name} takes belief evidence as an input"
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


def test_a_confirmed_answer_is_what_records_abandonment(loops):
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(found, now=NOW)

    loops.record(Op.LOOP_TRANSITION, "l_2", "2026-09-01T09:00Z",
                 **ledger.abandon(found, candidate=candidate,
                                  answered=Answer.CONFIRMED))

    after = ledger.read(loops.state().loops)["buy-farmland"]
    assert after.state == "abandoned-but-unadmitted"
    assert after.last_movement == "2024-01-01", (
        "admitting a wanting is over is not the wanting moving"
    )


def test_a_denial_records_nothing_at_all(loops):
    """The mistake a boolean invited, and the worst one available here.

    ``answered=True`` said only that *a reply arrived*, so the obvious wiring of
    *"no, I still want this"* recorded abandonment on the strength of the main
    denying it.
    """
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(found, now=NOW)
    before = loops.state().canonical_json()

    with pytest.raises(LoopError):
        ledger.abandon(found, candidate=candidate, answered=Answer.DENIED)

    assert loops.state().canonical_json() == before
    assert ledger.read(loops.state().loops)["buy-farmland"].state == "stalled"


@pytest.mark.parametrize("answer", [True, 1, "confirmed", "yes", None])
def test_a_bare_flag_is_not_an_answer(loops, answer):
    """A truthy value must not stand in for the main's word — including the
    string that happens to spell the enum's value."""
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(found, now=NOW)

    with pytest.raises(LoopError):
        ledger.abandon(found, candidate=candidate, answered=answer)


def test_a_candidate_answered_after_the_loop_moved_is_refused(loops):
    """A candidate outlives the moment it was raised: Half asks, and the main
    answers on a later turn — possibly having gone and done the thing."""
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(found, now=NOW)

    moved = move_loop(loops, "l_2", "buy-farmland", "2026-08-30T09:00Z")

    with pytest.raises(LoopError) as raised:
        ledger.abandon(moved, candidate=candidate, answered=Answer.CONFIRMED)
    assert "has moved since" in str(raised.value)
    assert ledger.read(loops.state().loops)["buy-farmland"].state == "stalled"


def test_a_candidate_carries_what_it_was_raised_at_and_against(loops):
    """Staleness has to be *detectable*, not merely checked in one function."""
    found = open_loop(loops, "l_1", "buy-farmland", state="stalled",
                      timescale="months", last_movement="2024-01-01")
    candidate = ledger.abandonment_candidate(found, now=NOW)

    assert candidate.raised_at == NOW
    assert candidate.against_movement == "2024-01-01"


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


def test_the_abandonment_threshold_is_pinned_to_twelve_periods_exactly():
    """**A value, and both sides of it.** Review found anything from roughly
    6.2 to 13.2 passed the suite — a band, not a number. Only 6.0 and 13.5
    failed, which means the twelve was decoration."""
    assert ABANDONMENT_PERIODS == 12.0

    period = PERIOD_DAYS[Timescale.DAYS]
    at_threshold = Loop(id="a", state="stalled", timescale="days",
                        last_movement=at_days(12 * period))
    just_inside = Loop(id="a", state="stalled", timescale="days",
                       last_movement=at_days(12 * period - 1 / DAY))

    assert at_threshold.silence(now=NOW).periods == 12.0
    assert ledger.abandonment_candidate(at_threshold, now=NOW) is not None, (
        "exactly twelve periods raises the question"
    )
    assert ledger.abandonment_candidate(just_inside, now=NOW) is None, (
        "one second inside twelve periods does not"
    )


@pytest.mark.parametrize("periods", [0, 0.0, -1, -0.5, float("nan"), True, "12"])
def test_an_abandonment_threshold_that_cannot_say_no_is_refused(periods):
    """Zero, a negative and a NaN each make *every* loop a candidate — NaN
    because every comparison against it is false — so Half proposes that the
    main has given up on everything."""
    loop = Loop(id="a", state="advancing", timescale="days",
                last_movement="2026-08-31T09:00:00Z")
    with pytest.raises(LoopError):
        ledger.abandonment_candidate(loop, now=NOW, periods=periods)


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

def test_a_loop_named_expunge_op_removes_it_from_the_fold(loops):
    open_loop(loops, "l_1", "buy-farmland", state="stalled", timescale="years",
              last_movement=LONG_AGO)

    loops.record(Op.EXPUNGE, "x_1", "2026-08-02T00:00Z",
                 **ledger.expunged("buy-farmland"))

    assert "buy-farmland" not in loops.state().loops
    assert "buy-farmland" in loops.state().expunged_loops
    assert "buy-farmland" not in loops.state().expunged, (
        "a loop's erasure landed in the belief namespace"
    )


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
# matrix: loop expunged — through the public erase path, text and all
# =============================================================================

def test_the_public_erase_path_removes_a_loop_and_its_text(loops):
    """Matrix: *the loop itself is expunged, through the public erase path*.

    Both halves were broken and both are asserted here. ``Store.expunge`` wrote
    a ``target``-only record, which the firewall correctly refuses to let reach
    a loop — so the loop stayed in the fold and survived replay — and
    ``expunge_bodies`` matched on record ids while a transition is keyed on the
    *append's* id, so nothing was ever tombstoned and the slug, state, timescale
    and every movement date stayed in the log verbatim.
    """
    open_loop(loops, "l_1", "buy-farmland", state="advancing",
              timescale="years", last_movement="2025-03-12")
    move_loop(loops, "l_2", "buy-farmland", "2026-04-01T09:00Z",
              t="2026-08-01T10:00Z")

    loops.expunge("buy-farmland", t="2026-08-02T00:00Z")

    assert "buy-farmland" not in loops.state().loops
    assert "buy-farmland" in loops.state().expunged_loops

    shard = (loops.log.root / "2026-08.jsonl").read_text(encoding="utf-8")
    # Everything the transitions said about the main's life is gone: the slug
    # they named, the state, the period, and both movement dates. A record's
    # own position, id and ``t`` survive by design, so replay still accounts
    # for it — that is the tombstone's contract, not a leak.
    for gone in ("advancing", "years", "2025-03-12", "2026-04-01T09:00Z"):
        assert gone not in shard, f"{gone!r} survived the erasure"
    naming = [line for line in shard.splitlines() if "buy-farmland" in line]
    assert len(naming) == 1 and '"op":"expunge"' in naming[0], (
        "the slug survives somewhere other than the record that erased it"
    )
    # **The one residue, stated rather than hidden.** A loop's identifier *is*
    # human-meaningful text, and the expunge record has to name what it erased
    # or the erasure does not survive replay — the same trade the belief path
    # already makes, where the erased id is in the record's own key. What goes
    # is everything the transitions said: the state, the period, the dates.
    remaining = [
        r for r in loops.log
        if r.op is Op.LOOP_TRANSITION and r.data.get("loop") == "buy-farmland"
    ]
    assert not remaining, f"transition bodies survived the erasure: {remaining}"


def test_an_erased_loop_stays_erased_after_a_replay(loops):
    open_loop(loops, "l_1", "buy-farmland", state="advancing", timescale="years")
    loops.expunge("buy-farmland", t="2026-08-02T00:00Z")

    loops.close()
    loops.db_path.unlink()
    rebuilt = loops.rebuild()
    assert "buy-farmland" not in rebuilt.loops
    assert "buy-farmland" in rebuilt.expunged_loops


def test_erasing_a_belief_does_not_reach_the_loop_table(loops):
    """The façade widens its record only for a name the fold shows as a loop."""
    belief(loops, "b_1", "wants to buy farmland", loop="buy-farmland")
    before = open_loop(loops, "l_1", "buy-farmland", state="advancing",
                       timescale="years", last_movement=LONG_AGO)

    loops.expunge("b_1", t="2026-08-02T00:00Z")

    assert ledger.read(loops.state().loops)["buy-farmland"] == before
    assert loops.state().expunged_loops == set()


def test_erasing_a_name_that_is_both_erases_both(loops):
    """Pinned rather than left to chance, because it is the one case where the
    façade's *"erase what you named"* rule has to choose."""
    belief(loops, "buy-farmland", "a claim that shares the slug")
    open_loop(loops, "l_1", "buy-farmland", state="advancing", timescale="years")

    loops.expunge("buy-farmland", t="2026-08-02T00:00Z")

    state = loops.state()
    assert "buy-farmland" not in state.beliefs
    assert "buy-farmland" not in state.loops
    assert "buy-farmland" in state.expunged
    assert "buy-farmland" in state.expunged_loops


def test_a_loop_stranded_on_an_unrecognised_state_has_a_way_back(loops):
    """The repair path for a log written before this gate existed.

    Story 1 accepted any state, the read path is tolerant, and the append gate
    now refuses the old value — so a stranded loop needs *some* operator route
    or it scores the unknown weight for ever. Two exist, and both are asserted:
    move it to a state this build knows, or erase it.
    """
    later_build_line(loops, "l_1", "2026-08-01T00:00Z",
                     loop="buy-farmland", state="wandering", timescale="years")
    assert not ledger.read(loops.rebuild().loops)["buy-farmland"].known_state

    repaired = move_loop(loops, "l_2", "buy-farmland", "2026-08-20T09:00Z",
                         state="stalled")
    assert repaired is not None and repaired.known_state

    later_build_line(loops, "l_3", "2026-08-21T00:00Z",
                     loop="learn-tabla", state="wandering")
    loops.rebuild()
    loops.expunge("learn-tabla", t="2026-08-22T00:00Z")
    assert "learn-tabla" not in loops.state().loops


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


def test_the_fold_carries_exactly_the_fields_the_ledger_writes(loops):
    """Behavioural, not a grep for a literal.

    The first version asserted a source substring, which was brittle about
    renames and — worse — silent about the one field the layers actually
    disagreed on: ``state`` was a literal in the store and a constant in the
    ledger, and the agreement test did not cover it. This drives every field
    through a real append and asserts the fold materialized each one.
    """
    open_loop(loops, "l_1", "buy-farmland", state="stalled",
              timescale="years", last_movement=LONG_AGO)
    entry = loops.state().loops["buy-farmland"]

    from half.store import fold as fold_module

    assert set(fold_module._TRANSITION_FIELDS) == {
        ledger.STATE, ledger.TIMESCALE, ledger.LAST_MOVEMENT
    }
    for name in fold_module._TRANSITION_FIELDS:
        assert name in entry, f"the fold dropped {name!r}"
    assert entry[ledger.LOOP] == "buy-farmland"


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
            ledger.opened(bad, state="advancing", loops={})
    assert ledger.opened(
        "buy-farmland", state="advancing", loops={})["loop"] == "buy-farmland"
    assert ledger.opened(
        "आशा-project", state="advancing", loops={})["loop"] == "आशा-project"


def test_the_vocabulary_carries_a_version():
    from half.loops import states, timescale as scale

    assert isinstance(states.VOCABULARY_VERSION, int)
    assert states.VOCABULARY_VERSION >= 1
    assert isinstance(scale.VOCABULARY_VERSION, int)


# =============================================================================
# the gates name their own cases
# =============================================================================
#
# A collection floor catches a marker being renamed and catches the suite being
# gutted wholesale. It does **not** catch the two or three cases that carry the
# whole property being deleted while the count stays above the line — which is
# exactly what review found: dropping the two AST guards took the firewall
# marker from 11 to 9 against a floor of 9, and CAP-6 from 92 to 90 against 80.
# Both gates would have stayed green with the firewall unguarded.
#
# So the load-bearing cases are named. Deleting one fails here by name;
# deleting *this* case drops the structure count under its own floor.


def _cases_defined_here() -> set[str]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


@pytest.mark.cap6_structure
def test_every_structural_guard_this_story_rests_on_still_exists():
    required = {
        "test_only_two_regions_of_the_fold_may_name_the_loop_table",
        "test_the_fold_guard_catches_a_demotion_in_another_branch",
        "test_nothing_in_the_package_mutates_the_loop_table_outside_the_fold",
        "test_the_mutation_scan_catches_every_way_a_dict_is_changed",
        "test_only_the_ledger_can_produce_a_loop_state_field",
        "test_the_loop_state_scan_catches_both_ways_a_record_is_built",
        "test_no_module_under_loops_offers_a_way_to_refute_or_demote_a_loop",
        "test_no_module_in_the_tree_supplies_a_default_timescale",
        "test_no_module_under_loops_reads_a_clock",
        "test_nothing_under_loops_records_half_touching_a_loop",
        "test_the_ledger_writes_nothing_itself",
    }
    missing = required - _cases_defined_here()
    assert not missing, (
        f"a structural guard was deleted: {sorted(missing)}. These are the "
        f"cases a collection floor cannot protect — each is one case carrying "
        f"a whole property"
    )


@pytest.mark.cap6_firewall
def test_every_firewall_case_this_story_rests_on_still_exists():
    required = {
        "test_a_loop_stands_and_still_moves_when_its_only_support_is_corrected",
        "test_a_correction_naming_the_loop_id_itself_leaves_it_standing_and_moving",
        "test_erasing_a_loop_does_not_suppress_a_belief_sharing_its_name",
        "test_the_two_expunged_namespaces_stay_apart",
        "test_a_tombstoned_record_sharing_a_loops_identifier_leaves_the_loop",
        "test_no_evidence_for_a_year_leaves_the_wanting_true_and_only_stalled",
    }
    missing = required - _cases_defined_here()
    assert not missing, f"a firewall case was deleted: {sorted(missing)}"
