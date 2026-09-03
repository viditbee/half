"""CAP-7 story 9c: tension states — one case per row of the I/O matrix.

Four things this file insists on.

**A correction resolves a tension, and the tension is still there afterwards.**
This is story 8's loop rule turned exactly around, and both halves of the
sentence are asserted separately on purpose. Story 8's firewall passed its own
AST check while a demotion travelled through ``state.expunged`` instead of
``state.loops`` — a loop that stood in the fold, which every firewall case
asserted, and could never move again. The inverse hole here is a correction that
resolves a tension *and also* drops it, which is indistinguishable from correct
behaviour to any case that only reads the state afterwards. So every resolution
case below asserts the tension is present **by id**, keeps its pair and its
license, is absent from the expunged set, and comes back from a rebuild.

**Nothing ranks the two sides, and that has to fail when a ranking is added.**
A guard that passes because no ranking exists is a guard resting on nothing. So
there are four, each aimed at a different way one arrives: the append gate
refuses a ranked field outright (behaviour, and it runs against every spelling);
the drift computation is asserted symmetric under swapping the pair, over the
whole matrix of states and accumulation patterns; no expression in the tension
surface may index the pair positionally, or sort, max or min over it; and no
name, argument, attribute or dict key anywhere in that surface may come from
the vocabulary of ranking. Each carries its own synthetic bypass.

**Nothing here reads a clock.** Every ``now`` is computed by the test and handed
in. The same log and the same stamp must give the same tensions for ever
(AD-30), and a suite that used the real clock would pass today and be
irreproducible tomorrow.

**Salience is not touched.** Story 4 made salience computed, with a ninety-day
half-life, and this story deliberately builds no decay. The way that regresses
is a counter stored on a tension for the pass to mutate — the exact AD-30
violation story 4 avoided — so the pass's whole append vocabulary is pinned to
one field and the tension surface is scanned for any mention of salience at all.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from half.civil import DAY, instant
from half.errors import HalfError, StoreError, TensionError
from half.governance import ladder
from half.governance.ladder import License
from half.store.fold import fold
from half.store.ops import SCHEMA_VERSION, Op
from half.store.records import (
    HISTORY_VISIBLE,
    RESERVED as RESERVED_KEYS,
    Record,
    TENSION_FIELDS,
    history_projection,
    make,
    validate_tension_fields,
)
from half.schedule.clock import stamp
from half.store.store import Store
from half.tensions import ledger, widening
from half.tensions.ledger import Plan, Tension
from half.tensions.states import (
    LIVE_STATES,
    STATE,
    TENSION_STATES,
    VOCABULARY_VERSION,
    TensionState,
    is_state,
    parse_state,
)
from half.tensions.widening import (
    BETWEEN,
    NO_PAIR,
    RECORDED_IN_FUTURE,
    REASONS,
    PERSISTENCE_DAYS,
    RANKED_FIELDS,
    RANKING_WORDS,
    RESOLVED_ALREADY,
    SIDES,
    UNKNOWN_STATE,
    UNREADABLE_NOW,
    UNREADABLE_RECORDED_AT,
    UNREADABLE_SIDE,
    Drift,
    Evidence,
    drift,
    by_entry,
    evidence,
    pair_of,
    ranked_names,
    ranks_a_side,
    supports,
    words_in,
)

from tests.conftest import seed_belief

pytestmark = pytest.mark.cap7

ROOT = Path(__file__).resolve().parents[1]

#: Every stamp in this file is derived from these. Injected, never read.
MINTED = "2026-08-02T00:00:00Z"
NOW = "2026-08-04T00:00:00Z"

#: The tension surface: every module that may name, compose or move a tension.
#: Globbed rather than listed, so a module written next year is covered — which
#: is how a whole new ``half/loops/decay.py`` slipped past story 8's first
#: guard.
SURFACE = ("half/tensions", "half/consolidate")

#: Tension code that lives **outside** those two packages, named function by
#: function.
#:
#: Every neutrality and resolution guard used to scan ``SURFACE`` alone, and
#: this story wrote tension code into three modules that are not in it: the
#: fold resolves tensions, the append gate validates them, and the registry
#: reads and moves them. Review confirmed the hole by injecting
#: ``held["winner"] = pair[0]`` into the fold's own merge branch and watching
#: the whole suite pass — a ranking written where no guard was looking, in the
#: one place that is not even reached by the append gate. That is story 8's
#: hole exactly: *the guard passed because the violation travelled through a
#: module it did not cover.*
#:
#: Named functions rather than whole files, because these modules do many other
#: things: ``ActorRegistry`` has a ``close``, which the resolution scan
#: forbids, and neither that nor the crisis mode's ``score`` has anything to do
#: with a tension. ``_guarded_trees`` asserts each name still exists, so a
#: rename drops coverage loudly rather than silently.
#: ``mint_view`` and ``note_mint`` are here because story 9d added two doors
#: and registered neither, so none of the four neutrality scans, the resolution
#: scan or the clock scan read the one function that creates every tension
#: record. Review sorted the pair inside ``note_mint`` and the whole suite
#: stayed green, while the identical line in ``note_transition`` — its sibling,
#: one entry up this dict — was caught.
OUTPOSTS: dict[str, tuple[str, ...]] = {
    "half/store/fold.py": ("fold", "_resolve_tensions"),
    # ``mint_projection`` is the third door story 9d left unscanned, and the
    # strengthened coverage assertion below is what found it: it is the
    # narrowing every belief passes through on its way into the minter, so a
    # field added to it is a field the minter can rank on.
    "half/store/records.py": ("validate_tension_fields", "mint_projection"),
    "half/actor/registry.py": (
        "tension_table", "belief_history", "tension_view", "note_transition",
        "mint_view", "note_mint",
    ),
}

#: How a *new* tension function in an outpost file is found before a reviewer
#: has to notice it. Any function whose name says it is about a tension or a
#: mint must be registered above; the coverage case turns this into the
#: assertion the old subset one could not make.
TENSION_WORDS = ("tension", "mint")


def _tension_functions(relative: str) -> set[str]:
    """Every function in ``relative`` whose *name* says it handles a tension.

    Read off the file rather than listed, so a door added next year is a red
    test on the day it is written rather than a hole a reviewer finds later.
    """
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"),
                     filename=relative)
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(word in node.name.lower() for word in TENSION_WORDS)
    }

#: The vocabulary of the guard itself. ``half/tensions/widening.py`` owns the
#: denylist and is exempt from the name scan for that reason; a *caller*
#: applying it — ``validate_tension_fields`` asking ``ranked_names(fields)`` —
#: is the rule being enforced rather than a ranking being written, and these
#: are the only names that get that reading.
GUARD_NAMES = {"RANKED_FIELDS", "RANKING_WORDS", "ranked_names", "ranks_a_side"}


def _guarded_trees(*, skip_denylist_owner: bool = False):
    """Every tree the neutrality and resolution guards read, labelled.

    The two packages whole, plus each named function of each outpost. The label
    is what a failure names, so ``half/store/fold.py:fold`` says which function
    the offending line is in and not merely which file.
    """
    found: list[tuple[str, ast.AST]] = []
    for area in SURFACE:
        for path in sorted((ROOT / area).rglob("*.py")):
            relative = str(path.relative_to(ROOT))
            if skip_denylist_owner and relative == "half/tensions/widening.py":
                continue
            found.append((relative, ast.parse(path.read_text(encoding="utf-8"),
                                              filename=str(path))))
    for relative, names in sorted(OUTPOSTS.items()):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"),
                         filename=relative)
        defined = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in names:
            assert name in defined, (
                f"{relative} no longer defines {name!r}; the guards have lost "
                f"their subject, which is how coverage disappears quietly"
            )
            found.append((f"{relative}:{name}", defined[name]))
    return found


# ── helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tensions(tmp_path):
    with Store(tmp_path / "main") as store:
        yield store


def at_days(days: float, *, since: str = NOW) -> str:
    """A stamp exactly ``days`` before ``since``, to the second.

    Boundary cases need arithmetic rather than eyeballed dates: *"exactly the
    persistence window"* is only an assertion if the stamp really is exactly
    that. Rendered by ``half.schedule.clock.stamp``, which is pure and reads no
    clock — the seam the whole product injects at — and checked round-trip
    against ``half.civil.instant`` below, so the two agree about what an
    instant is.
    """
    base = instant(since)
    assert base is not None
    return stamp(base - days * DAY)


def at_hours(hours: float, *, since: str) -> str:
    """A stamp ``hours`` **after** ``since``. The same arithmetic, forward."""
    base = instant(since)
    assert base is not None
    return stamp(base + hours * 3600)


def entry(store, ident, t, *, support, claim="something about the main"):
    """One ledger entry, admitted through the ladder like every other belief."""
    return seed_belief(store, ident, t, subject="self", claim=claim,
                       support=list(support))


def mint(store, ident, t, *, between, state=TensionState.FRESH):
    """A tension, as story 9d will mint one: a pair, a state, and a license.

    Through ``ladder.admitted`` rather than by spelling ``license="behave"``,
    for the reason ``seed_belief`` exists: the ladder is the only sanctioned
    writer of a license field, and a test that spells one is doing what story
    5a says nobody may do.
    """
    store.record(Op.TENSION, ident, t, between=list(between),
                 **{STATE: str(state)}, **ladder.admitted())
    return store.state().tensions[ident]


def history(store):
    """The main's belief history, narrowed the way the pass sees it."""
    return tuple(
        history_projection(record.data)
        for record in store.log
        if record.op is Op.ASSERT and record.data.get("tombstone") is not True
    )


def past_the_gate(store, ident, t, **fields):
    """Write a tension record the *append gate refuses*, straight to the log.

    **Write strict, read tolerant** is the rule this story shares with story 8,
    and the read half needs cases: a log written by an older build — before the
    store required a mint to name its pair — or by a later one through the
    Ask-First path that adds a state, still has to fold. ``Store.append`` is
    where strictness lives, so exercising tolerance means going around it, and
    that is the only thing this helper is for.
    """
    store.log.append(
        Record(op=Op.TENSION, id=ident, t=t,
               data={"t": t, "op": str(Op.TENSION), "id": ident,
                     "v": SCHEMA_VERSION, **fields})
    )
    store.rebuild()
    return store.state().tensions[ident]


def read_one(store, ident) -> Tension:
    return ledger.read(store.state().tensions)[ident]


def sides_of(store, ident):
    return ledger.sides(read_one(store, ident), history=history(store))


def widening_log(store, *, minted=MINTED, moves=("b_1",)):
    """Two entries, a tension over them, and evidence added to ``moves``.

    The scenario the whole story turns on. ``moves`` names which entries
    accumulate a second source after the tension was recorded — one of them is
    widening, both is closing, neither is standing still.

    Both entries are seeded a day *before* the tension and any accumulation an
    hour *after* it, derived from ``minted`` rather than pinned, so that a case
    backdating the mint still produces a baseline. A tension recorded before
    the entries it names has none, which ``drift`` correctly reports as not
    computable — and which would otherwise be the answer to every threshold
    case in this file, silently.
    """
    entry(store, "b_1", at_days(1, since=minted), support=["s_1"],
          claim="says the mornings are for writing")
    entry(store, "b_2", at_days(1, since=minted), support=["s_2"],
          claim="has sent no draft since May")
    mint(store, "x_1", minted, between=["b_1", "b_2"])
    for ident in moves:
        entry(store, ident, at_hours(1, since=minted),
              support=["s_1" if ident == "b_1" else "s_2", f"s_new_{ident}"])
    return store


# ═════════════════════════════════════════════════════════════════════════════
# matrix: a minted tension — recorded `fresh`, readable from the fold
# ═════════════════════════════════════════════════════════════════════════════


def test_a_minted_tension_is_recorded_fresh_and_readable_from_the_fold(tensions):
    entry(tensions, "b_1", "2026-08-01T00:00:00Z", support=["s_1"])
    entry(tensions, "b_2", "2026-08-01T00:00:00Z", support=["s_2"])
    mint(tensions, "x_1", MINTED, between=["b_1", "b_2"])

    found = read_one(tensions, "x_1")
    assert found.state == TensionState.FRESH.value
    assert found.known_state and found.paired
    assert found.state in LIVE_STATES
    assert set(found.between) == {"b_1", "b_2"}
    assert found.at == MINTED


def test_the_fold_reads_a_tension_back_as_the_log_wrote_it(tensions):
    widening_log(tensions)
    record = tensions.state().tensions["x_1"]
    assert record[BETWEEN] == ["b_1", "b_2"]
    assert record[STATE] == "fresh"
    assert record["id"] == "x_1"


def test_reading_a_malformed_tension_never_raises():
    """The read path is on the nightly pass, and one unreadable record must
    cost that tension its evaluation rather than the whole pass."""
    for hostile in (None, "not a mapping", 5, {"x_1": None}, {"x_1": "text"},
                    {"x_1": {BETWEEN: "b_1"}}, {"x_1": {STATE: 7}},
                    {"": {}}, {5: {}}):
        found = ledger.read(hostile)
        assert isinstance(found, dict)
        for tension in found.values():
            assert isinstance(tension, Tension)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: unknown state — refused at the append, hard error, never defaulted
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "state",
    ["widenning", "open", "closed", "settled", "true", "false", "refuted",
     "advancing", "stalled", "achieved", "entered", "asked", "agreed",
     "FRESH", " fresh", "fresh "],
)
def test_a_state_outside_the_vocabulary_is_refused_at_the_append(tensions, state):
    with pytest.raises(TensionError):
        tensions.record(Op.TENSION, "x_1", MINTED,
                        between=["b_1", "b_2"], **{STATE: state})
    assert "x_1" not in tensions.state().tensions


@pytest.mark.parametrize("state", [1, 0, True, [], {}, ("fresh",), 3.5])
def test_a_state_that_is_not_even_a_string_is_refused(tensions, state):
    with pytest.raises(TensionError):
        tensions.record(Op.TENSION, "x_1", MINTED, **{STATE: state})


def test_an_unknown_state_is_never_defaulted_to_a_known_one(tensions):
    """The refusal is the point: a default would put a shape on a disagreement
    about the main's own life and then make it permanent."""
    with pytest.raises(TensionError):
        tensions.record(Op.TENSION, "x_1", MINTED,
                        between=["b_1", "b_2"], **{STATE: "widenning"})
    assert tensions.state().tensions == {}
    assert list(tensions.log) == []


@pytest.mark.parametrize("state", sorted(LIVE_STATES))
def test_every_state_a_record_may_be_written_in_is_accepted_by_the_append_gate(
    tensions, state
):
    """Every state but `resolved`, which is the fold's answer to a correction
    and which nothing may write — see the terminality cases below."""
    tensions.record(Op.TENSION, f"x_{state}", MINTED,
                    between=["b_1", "b_2"], **{STATE: state})
    assert tensions.state().tensions[f"x_{state}"][STATE] == state


def test_the_gate_refuses_a_hand_built_record_through_the_append_path(tensions):
    """Not only the ledger's door. A record assembled by hand and handed to
    ``Store.append`` meets the same gate, because that is where durability
    happens."""
    record = Record(op=Op.TENSION, id="x_1", t=MINTED,
                    data={"t": MINTED, "op": "tension", "id": "x_1",
                          "v": SCHEMA_VERSION, STATE: "widenning"})
    with pytest.raises(TensionError):
        tensions.append(record)


def test_the_append_gate_refuses_with_a_typed_domain_error(tensions):
    """``TensionError`` is both a ``HalfError`` and a ``ValueError``, so a
    caller wrapping the write path in either name catches every refusal."""
    with pytest.raises(HalfError):
        make(Op.TENSION, "x_1", MINTED, **{STATE: "nope"})
    with pytest.raises(ValueError):
        make(Op.TENSION, "x_1", MINTED, **{STATE: "nope"})


def test_a_state_word_from_another_vocabulary_is_refused_on_a_tension(tensions):
    """``state`` names four closed vocabularies — tension, loop, crisis and
    aftercare — and the op-aware gate is what keeps them apart."""
    for foreign in ("stalled", "advancing", "entered", "reversed", "asked"):
        with pytest.raises(TensionError):
            tensions.record(Op.TENSION, "x_1", MINTED, **{STATE: foreign})


def test_the_other_vocabularies_still_accept_their_own_words(tensions):
    tensions.record(Op.LOOP_TRANSITION, "l_1", MINTED,
                    loop="buy-farmland", **{STATE: "stalled"})
    tensions.record(Op.CRISIS, "cr_1", MINTED, **{STATE: "entered"},
                    tier="disclosure", score=1)
    tensions.record(Op.AFTERCARE, "ac_1", MINTED, **{STATE: "asked"})
    tensions.record(Op.TENSION, "x_1", MINTED, between=["b_1", "b_2"],
                    **{STATE: "widening"})
    assert tensions.state().tensions["x_1"][STATE] == "widening"


def test_the_vocabulary_is_exactly_the_five_the_glossary_names():
    assert TENSION_STATES == {
        "fresh", "persistent", "widening", "closing", "resolved"
    }
    assert LIVE_STATES == TENSION_STATES - {"resolved"}


def test_no_state_in_the_vocabulary_reads_as_a_verdict():
    """*"For a person neither is wrong"* — so no state may name one of them as
    the mistaken one. A sixth state is an Ask-First change; a sixth state that
    means `refuted` is not available through that path either."""
    banned = {"wrong", "false", "refuted", "disproven", "mistaken", "correct",
              "true", "lost", "won", "settled"}
    assert not {state.lower() for state in TENSION_STATES} & banned


def test_parse_state_raises_and_is_state_does_not():
    assert parse_state("widening") is TensionState.WIDENING
    with pytest.raises(ValueError):
        parse_state("widenning")
    assert is_state("widening") and not is_state("widenning")
    assert not is_state(None) and not is_state(7)


def test_the_vocabulary_carries_a_version():
    assert isinstance(VOCABULARY_VERSION, int) and VOCABULARY_VERSION >= 1


def test_the_state_field_is_spelled_the_same_in_both_vocabularies():
    """Two packages own the spelling of their own record shape, and both flow
    into the same field of the same record. A drift here is a tension state the
    loop gate validates, or the reverse."""
    from half.loops.states import STATE as LOOP_STATE_FIELD

    assert STATE == LOOP_STATE_FIELD == "state"


def test_the_support_field_is_spelled_the_same_as_the_ladder_writes_it():
    """The ladder writes it, this package counts it. A rename in one place
    would make every tension incomputable in the other, silently."""
    assert widening.SUPPORT == ladder.SUPPORT == "support"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: `between` — a tension is a record about exactly two entries
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "pair",
    [["b_1"], ["b_1", "b_2", "b_3"], [], ["b_1", "b_1"], ["b_1", ""],
     ["b_1", 7], "b_1", ("b_1",), [None, "b_2"]],
)
def test_a_between_that_is_not_two_distinct_entries_is_refused(tensions, pair):
    with pytest.raises(TensionError):
        tensions.record(Op.TENSION, "x_1", MINTED, between=pair,
                        **{STATE: "fresh"})
    assert tensions.state().tensions == {}


def test_a_transition_carries_no_pair_and_is_still_accepted(tensions):
    """``between`` is optional because a transition does not restate the pair —
    demanding it on every record would make a transition a re-mint."""
    validate_tension_fields({STATE: "widening"})
    widening_log(tensions)
    tensions.record(Op.TENSION, "x_1", NOW, **{STATE: "widening"})
    assert read_one(tensions, "x_1").paired


def test_a_tension_that_names_no_pair_is_never_evaluated(tensions):
    """A pairless tension can no longer be *written* — ``Store.append`` refuses
    a mint that names no pair — but a log an older build wrote still folds, and
    this is what the pass does with one."""
    past_the_gate(tensions, "x_1", MINTED, **{STATE: "fresh"})
    found = ledger.evaluate(read_one(tensions, "x_1"), history=(), now=NOW)
    assert not found.computable and found.reason == NO_PAIR
    assert found.state is None


def test_two_sides_is_the_definition_and_it_is_pinned():
    assert SIDES == 2


# ═════════════════════════════════════════════════════════════════════════════
# matrix: widening — evidence accumulates on one side only, from the log alone
# ═════════════════════════════════════════════════════════════════════════════


def test_evidence_on_one_side_alone_computes_as_widening(tensions):
    widening_log(tensions, moves=("b_1",))
    found = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert found.computable
    assert found.state == TensionState.WIDENING.value


def test_evidence_on_both_sides_computes_as_closing(tensions):
    widening_log(tensions, moves=("b_1", "b_2"))
    found = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert found.state == TensionState.CLOSING.value


def test_widening_is_computed_from_the_log_and_nothing_else(tensions):
    """The acceptance criterion: two builds reading one log agree.

    Asserted by computing the same answer from a log read alone, with the store
    closed and the derived view deleted — no SQLite, no fold cache, no clock.
    """
    widening_log(tensions, moves=("b_1",))
    expected = ledger.evaluate(read_one(tensions, "x_1"),
                               history=history(tensions), now=NOW)
    tensions.close()
    tensions.db_path.unlink()

    replayed = fold(tensions.log)
    again = ledger.evaluate(
        ledger.read(replayed.tensions)["x_1"],
        history=tuple(history_projection(r.data) for r in tensions.log),
        now=NOW,
    )
    assert again == expected
    assert again.state == TensionState.WIDENING.value


def test_a_license_promotion_is_not_evidence(tensions):
    """A promotion appends a record and adds no support. Counting records
    rather than sources would report drift every time Half earned the right to
    speak."""
    widening_log(tensions, moves=())
    seed_belief(tensions, "b_1", "2026-08-03T00:00:00Z", rung=License.ASK,
                support=["s_1"], subject="self", claim="restated")
    found = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert found.computable
    assert found.state == TensionState.FRESH.value, "a promotion moved a tension"


def test_repeating_one_source_is_not_accumulation(tensions):
    """Ten mentions of one fact in one thread is one support (glossary)."""
    entry(tensions, "b_1", "2026-08-01T00:00:00Z", support=["s_1"])
    entry(tensions, "b_2", "2026-08-01T00:00:00Z", support=["s_2"])
    mint(tensions, "x_1", MINTED, between=["b_1", "b_2"])
    entry(tensions, "b_1", "2026-08-03T00:00:00Z",
          support=["s_1", "s_1", "s_1", "s_1"])
    found = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert found.state == TensionState.FRESH.value


def test_support_that_shrank_is_not_accumulation():
    """A revision citing fewer sources is Half tidying its own receipts, not
    the main's life moving."""
    assert not Evidence(id="b_1", before=3, now=1).accumulated
    assert not Evidence(id="b_1", before=2, now=2).accumulated
    assert Evidence(id="b_1", before=2, now=3).accumulated


@pytest.mark.parametrize(
    "cited,expected",
    [(None, 0), ([], 0), (["s_1"], 1), (["s_1", "s_2"], 2),
     (["s_1", "s_1"], 1), ("s_1", 1), ("  ", 0), (["s_1", "", None, 7], 1),
     (7, None), ({}, None)],
)
def test_support_is_counted_deduplicated_and_never_guessed(cited, expected):
    assert supports({"support": cited} if cited is not None else {}) == expected


def test_supports_refuses_a_record_that_is_not_a_mapping():
    assert supports(None) is None and supports("text") is None


# ═════════════════════════════════════════════════════════════════════════════
# matrix: fresh to persistent — time passes with both sides unmoved
# ═════════════════════════════════════════════════════════════════════════════


def test_both_sides_unmoved_past_the_window_computes_as_persistent(tensions):
    old = at_days(PERSISTENCE_DAYS + 1)
    widening_log(tensions, minted=old, moves=())
    found = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert found.state == TensionState.PERSISTENT.value
    assert found.age_days == pytest.approx(PERSISTENCE_DAYS + 1)


def test_both_sides_unmoved_inside_the_window_stays_where_it_is(tensions):
    widening_log(tensions, minted=at_days(PERSISTENCE_DAYS - 1), moves=())
    found = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert found.computable
    assert found.state == TensionState.FRESH.value


def test_exactly_the_window_is_not_yet_persistent_and_a_second_later_is(tensions):
    """The boundary is pinned. ``>=`` would reclassify every tension the
    instant it reached its own window, which is a fortnight of Half calling
    something new and then a step it did not take."""
    widening_log(tensions, minted=at_days(PERSISTENCE_DAYS), moves=())
    exact = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert exact.state == TensionState.FRESH.value

    later = ledger.evaluate(
        read_one(tensions, "x_1"), history=history(tensions),
        now=at_days(-1 / DAY),
    )
    assert later.state == TensionState.PERSISTENT.value


def test_the_boundary_helper_is_exact():
    assert instant(NOW) - instant(at_days(14)) == 14 * DAY
    assert instant(NOW) - instant(at_days(0)) == 0


def test_the_persistence_window_is_pinned_to_fourteen_days():
    """Pinned rather than eyeballed, and both sides asserted above: a threshold
    nobody can be wrong about is a threshold nobody chose."""
    assert PERSISTENCE_DAYS == 14.0


def test_no_threshold_decides_widening(tensions):
    """The Ask-First rule. Widening is *one side moved and the other did not* —
    a fact about the log — so it fires the day the evidence lands, whatever the
    tension's age."""
    for age in (0.0, 1.0, PERSISTENCE_DAYS, PERSISTENCE_DAYS * 100):
        with Store(tensions.root.parent / f"m{age}") as store:
            widening_log(store, minted=at_days(age), moves=("b_1",))
            found = ledger.evaluate(read_one(store, "x_1"),
                                    history=history(store), now=NOW)
            assert found.state == TensionState.WIDENING.value, age


def test_a_tension_recorded_in_the_future_is_reported_rather_than_clamped(
    tensions
):
    """A baseline ahead of ``now`` is not a baseline.

    This used to clamp the age to zero and report the tension as `fresh` with
    nothing to do — but with the baseline in the future, *every* record for both
    sides is at or before it, so both counts read as unmoved and the tension
    could not widen however much evidence arrived. That is a gap, and it says
    so. It also heals itself: the same tension evaluated after ``now`` passes
    the stamp computes normally.
    """
    widening_log(tensions, minted="2026-09-01T00:00:00Z", moves=("b_1",))
    found = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now=NOW)
    assert not found.computable
    assert found.reason == RECORDED_IN_FUTURE
    assert found.state is None and found.age_days is None

    later = ledger.evaluate(read_one(tensions, "x_1"),
                            history=history(tensions), now="2026-09-03T00:00:00Z")
    assert later.computable and later.state == TensionState.WIDENING.value


# ═════════════════════════════════════════════════════════════════════════════
# matrix: not computable — reported as such, state unchanged, never a guess
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "state,recorded_at,sides,reason",
    [
        ("widenning", MINTED, None, UNKNOWN_STATE),
        (None, MINTED, None, UNKNOWN_STATE),
        ("resolved", MINTED, None, RESOLVED_ALREADY),
        ("fresh", MINTED, [], NO_PAIR),
        ("fresh", MINTED, [Evidence("b_1", 1, 1)], NO_PAIR),
        ("fresh", MINTED,
         [Evidence("b_1", 1, 1), Evidence("b_1", 1, 1)], NO_PAIR),
        ("fresh", "yesterday",
         [Evidence("b_1", 1, 1), Evidence("b_2", 1, 1)], UNREADABLE_RECORDED_AT),
        ("fresh", MINTED,
         [Evidence("b_1", 1, 1), Evidence("b_2", 1, 1)], UNREADABLE_NOW),
        ("fresh", MINTED,
         [Evidence("b_1", None, None), Evidence("b_2", 1, 1)], UNREADABLE_SIDE),
    ],
    ids=["unknown-state", "no-state", "resolved", "no-sides", "one-side",
         "same-side-twice", "unreadable-stamp", "unreadable-now",
         "unreadable-side"],
)
def test_every_way_the_answer_would_be_a_guess_reports_instead(
    state, recorded_at, sides, reason
):
    now = "not a stamp" if reason is UNREADABLE_NOW else NOW
    found = drift(state=state, recorded_at=recorded_at, sides=sides, now=now)
    assert not found.computable
    assert found.reason == reason
    assert found.state is None, "a guess escaped as a state"
    assert found.age_days is None


def test_a_tension_that_cannot_be_evaluated_keeps_the_state_it_has(tensions):
    """Matrix: *not computable*. The pass leaves it alone; the state is the
    state the log recorded and nothing overwrote it."""
    past_the_gate(tensions, "x_1", MINTED, **{STATE: "widening"})
    before = tensions.state().tensions["x_1"]
    found = ledger.plan(ledger.read(tensions.state().tensions),
                        history=history(tensions), now=NOW)
    assert found.transitions == {}
    assert found.incomputable == {"x_1": NO_PAIR}
    assert tensions.state().tensions["x_1"] == before


def test_a_side_with_no_record_at_all_is_unreadable_not_zero(tensions):
    """*"We cannot tell"* is not *"it cited nothing"*. Reading it as zero would
    make a missing entry look like one that had just gained its first source."""
    found = evidence((), side="b_9", at=MINTED)
    assert found.before is None and found.now is None
    assert not found.readable and not found.accumulated


def test_a_side_older_than_the_tension_has_no_baseline(tensions):
    """A tension recorded before the entry it names has nothing to compare
    against, and inventing a zero would report accumulation immediately."""
    rows = ({"id": "b_1", "t": "2026-08-03T00:00:00Z", "support": ["s_1"]},)
    found = evidence(rows, side="b_1", at=MINTED)
    assert found.before is None and found.now == 1
    assert not found.readable


def test_an_unreadable_stamp_on_any_record_refuses_the_whole_entry():
    """Skipping the record is the guess: it would move the baseline without
    anyone seeing it."""
    rows = (
        {"id": "b_1", "t": "2026-08-01T00:00:00Z", "support": ["s_1"]},
        {"id": "b_1", "t": "yesterday", "support": ["s_1", "s_2"]},
    )
    assert not evidence(rows, side="b_1", at=MINTED).readable


def test_evidence_refuses_a_side_or_a_baseline_it_cannot_read():
    for side in (None, "", "   ", 7, []):
        assert not evidence((), side=side, at=MINTED).readable
    for bad in ("yesterday", None, "2026-02-31T00:00:00Z", 7):
        assert not evidence((), side="b_1", at=bad).readable


def test_evidence_reads_the_log_in_stamp_order_not_append_order():
    """The log is ordered by *append*, and its stamps need not be monotonic —
    ``half.schedule.tick``'s own notes say a backward clock jump leaves them out
    of order, and nothing downstream was supposed to depend on it.

    ``evidence`` does: it takes the baseline from the last row at or before the
    tension's stamp and the current count from the last row of all. Read in
    append order, both come off the wrong records, and a tension reports
    accumulation that did not happen — or, as here, misses one that did.
    """
    rows = (
        {"id": "b_1", "t": "2026-08-01T00:00:00Z", "support": ["s_1"]},
        {"id": "b_1", "t": "2026-08-05T00:00:00Z",
         "support": ["s_1", "s_2", "s_3"]},
        {"id": "b_1", "t": "2026-08-03T00:00:00Z", "support": ["s_1", "s_2"]},
    )
    found = evidence(rows, side="b_1", at="2026-08-04T00:00:00Z")
    assert found.before == 2, "the baseline came off the wrong record"
    assert found.now == 3, "the current count came off the wrong record"
    assert found.accumulated


def test_the_index_and_the_bare_rows_answer_identically():
    """``by_entry`` exists so a pass walks a main's log once instead of twice
    per tension. It must not be a second reading of it."""
    rows = tuple(
        {"id": ident, "t": stamp_at, "support": cited}
        for ident, stamp_at, cited in (
            ("b_1", "2026-08-01T00:00:00Z", ["s_1"]),
            ("b_2", "2026-08-01T00:00:00Z", ["s_2"]),
            ("b_1", "2026-08-03T00:00:00Z", ["s_1", "s_9"]),
            ("b_3", "not a stamp", ["s_3"]),
        )
    )
    indexed = by_entry(rows)
    for side in ("b_1", "b_2", "b_3", "b_9"):
        assert evidence(rows, side=side, at=MINTED) == evidence(
            indexed, side=side, at=MINTED
        ), side


def test_an_erased_body_cannot_be_read_as_citing_nothing():
    """A tombstone is not a record that cited no sources — it is a record with
    no body. Counted as a zero it lowers the entry's *current* count, and the
    next honest append then reads as accumulation."""
    assert supports({"id": "b_1", "t": MINTED, "tombstone": True}) is None
    assert supports({"id": "b_1", "t": MINTED}) == 0, (
        "a belief admitted with no receipt genuinely cites nothing, and its "
        "first source arriving is real accumulation"
    )


def test_a_reason_is_never_a_state_and_a_state_is_never_a_reason():
    assert not {NO_PAIR, UNKNOWN_STATE, UNREADABLE_NOW, UNREADABLE_SIDE,
                UNREADABLE_RECORDED_AT} & TENSION_STATES


# ═════════════════════════════════════════════════════════════════════════════
# matrix: one side retracted / revised / expunged — the tension RESOLVES,
#         and it is still there. The inverse of story 8's firewall.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_resolution
@pytest.mark.parametrize("verb", [Op.RETRACT, Op.REVISE])
@pytest.mark.parametrize("side", ["b_1", "b_2"])
def test_a_correction_to_either_side_resolves_the_tension_and_keeps_it(
    tensions, verb, side
):
    """The acceptance criterion, and **both halves of it**.

    Story 8's firewall passed its own AST check while a demotion travelled
    through a different attribute, leaving a loop that stood in the fold and
    could never move again. The inverse hole here is a correction that resolves
    a tension *and also* drops it — indistinguishable from correct behaviour to
    a case that only reads the state. So this asserts presence by id, the pair,
    the license, absence from the expunged set, and survival of a rebuild.
    """
    widening_log(tensions, moves=())
    minted = dict(tensions.state().tensions["x_1"])

    tensions.record(verb, "c_1", "2026-08-03T09:00:00Z", target=side)

    found = tensions.state().tensions
    assert "x_1" in found, "the correction deleted the tension"
    assert found["x_1"][STATE] == TensionState.RESOLVED.value
    assert found["x_1"][BETWEEN] == minted[BETWEEN], "the pair was lost"
    assert found["x_1"]["license"] == minted["license"], "the license was lost"
    assert "x_1" not in tensions.state().expunged
    assert set(found["x_1"]) == set(minted), "resolution added or dropped a field"

    rebuilt = tensions.rebuild().tensions
    assert rebuilt["x_1"] == found["x_1"]


@pytest.mark.cap7_resolution
@pytest.mark.parametrize("side", ["b_1", "b_2"])
def test_expunging_one_side_resolves_the_tension_and_keeps_it(tensions, side):
    """Matrix: *one side expunged*. Same answer as a correction — resolves,
    survives as a record, never erased silently."""
    widening_log(tensions, moves=())
    minted = dict(tensions.state().tensions["x_1"])

    tensions.expunge(side, t="2026-08-03T09:00:00Z")

    found = tensions.state().tensions
    assert "x_1" in found, "expunging a side deleted the tension"
    assert found["x_1"][STATE] == TensionState.RESOLVED.value
    assert found["x_1"][BETWEEN] == minted[BETWEEN]
    assert "x_1" not in tensions.state().expunged
    assert side in tensions.state().expunged
    assert tensions.rebuild().tensions["x_1"] == found["x_1"]


@pytest.mark.cap7_resolution
def test_the_resolution_is_the_deliberate_inverse_of_the_loop_firewall(tensions):
    """The contrast, in one case, because each rule applied to the other's
    object is a plausible-looking line.

    The same correction, in the same log: the *loop* stands untouched and can
    still move, and the *tension* resolves. A build that treated them alike is
    wrong in one direction or the other whichever way it chose.
    """
    from half.loops import ledger as loops

    widening_log(tensions, moves=())
    tensions.record(Op.LOOP_TRANSITION, "l_1", "2026-08-02T01:00:00Z",
                    **loops.opened("write-more", state="advancing",
                                   timescale="weeks",
                                   last_movement="2026-08-01",
                                   loops=tensions.state().loops))

    tensions.record(Op.RETRACT, "c_1", "2026-08-03T09:00:00Z", target="b_1")

    state = tensions.state()
    assert state.tensions["x_1"][STATE] == TensionState.RESOLVED.value
    assert state.loops["write-more"][STATE] == "advancing", (
        "a correction demoted a wanting — story 8's firewall"
    )
    # And the wanting can still move, which is what "standing" has to mean.
    tensions.record(Op.LOOP_TRANSITION, "l_2", "2026-08-04T01:00:00Z",
                    **loops.move("write-more", at="2026-08-04"))
    assert tensions.state().loops["write-more"]["last_movement"] == "2026-08-04"


@pytest.mark.cap7_resolution
def test_retract_and_revise_resolve_a_tension_identically(tensions):
    """*"You changed"* and *"Half was wrong about you"* are a real distinction
    and it lives on the correction record, not on the tension. Which of two
    claims about a person was the mistaken one is not a question a tension
    answers."""
    outcomes = []
    for index, verb in enumerate((Op.RETRACT, Op.REVISE)):
        with Store(tensions.root.parent / f"m{index}") as store:
            widening_log(store, moves=())
            store.record(verb, "c_1", "2026-08-03T09:00:00Z", target="b_1")
            outcomes.append(store.state().tensions["x_1"])
    assert outcomes[0] == outcomes[1]


@pytest.mark.cap7_resolution
def test_a_correction_to_an_unrelated_entry_leaves_the_tension_alone(tensions):
    widening_log(tensions, moves=())
    entry(tensions, "b_9", "2026-08-01T00:00:00Z", support=["s_9"])
    before = dict(tensions.state().tensions["x_1"])
    tensions.record(Op.RETRACT, "c_1", "2026-08-03T09:00:00Z", target="b_9")
    assert tensions.state().tensions["x_1"] == before


@pytest.mark.cap7_resolution
def test_resolution_is_idempotent_over_a_second_correction_and_a_replay(
    tensions
):
    widening_log(tensions, moves=())
    tensions.record(Op.RETRACT, "c_1", "2026-08-03T09:00:00Z", target="b_1")
    once = tensions.state().canonical_json()
    tensions.record(Op.REVISE, "c_2", "2026-08-04T09:00:00Z", target="b_2")
    twice = tensions.state().tensions["x_1"]
    assert twice[STATE] == TensionState.RESOLVED.value
    assert tensions.fold().canonical_json() == tensions.state().canonical_json()
    assert once != ""


@pytest.mark.cap7_resolution
def test_a_resolved_tension_is_never_re_evaluated(tensions):
    """Terminal, and reported rather than skipped silently: *"there were four
    we did not look at"* is a fact the pass should be able to state."""
    widening_log(tensions, moves=("b_1",))
    tensions.record(Op.RETRACT, "c_1", "2026-08-03T09:00:00Z", target="b_1")
    found = ledger.plan(ledger.read(tensions.state().tensions),
                        history=history(tensions), now=NOW)
    assert found.transitions == {}
    assert found.incomputable == {"x_1": RESOLVED_ALREADY}


@pytest.mark.cap7_resolution
def test_nothing_can_move_a_tension_to_resolved_by_hand(tensions):
    """A second writer of `resolved` would be a second place for the log and
    the fold to disagree. The state stays in the vocabulary — a later build may
    need it, and the append gate is write-strict about the *word*, not about
    who may reach it — but the ledger refuses to compose one."""
    widening_log(tensions, moves=())
    with pytest.raises(TensionError, match="resolution"):
        ledger.transition(read_one(tensions, "x_1"),
                          to=TensionState.RESOLVED)


@pytest.mark.cap7_resolution
def test_no_module_in_the_tension_surface_offers_a_way_to_resolve_one():
    """Globbed over the packages rather than read off one filename, which is
    how a whole new ``half/loops/decay.py`` slipped past story 8's first
    guard."""
    banned = {"resolve", "resolved", "close", "settle", "invalidate", "delete",
              "remove", "drop", "expunge"}
    offenders: list[str] = []
    for label, tree in _guarded_trees():
        for node in ast.walk(tree):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name.lstrip("_") in banned):
                offenders.append(f"{label}:{node.name}")
    assert not offenders, (
        f"the tension surface offers {offenders}; resolution is the fold's "
        f"answer to a correction and nothing else records it"
    )


# ═════════════════════════════════════════════════════════════════════════════
# matrix: append after resolution — `resolved` is terminal by every route
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_resolution
@pytest.mark.parametrize("later", sorted(LIVE_STATES))
def test_a_later_append_cannot_move_a_resolved_tension_out_of_it(tensions, later):
    """Matrix: *append after resolution*. The defect, reproduced and closed.

    Mint `fresh`, retract a side, read `resolved` from the fold — then append a
    ``tension`` record carrying any live state at all. The fold merged it
    straight over its own answer to the correction, and replay reproduced the
    move faithfully, while ``half.tensions.states`` said in prose that *"there
    is no path from `resolved` back to any other state"*. The expunge branch
    had a guard and a case for exactly this shape; this one had neither.

    Asserted through all three readings, because they are three different
    programs: the SQLite view, a rebuild of it, and a fold in memory.
    """
    widening_log(tensions, moves=())
    tensions.record(Op.RETRACT, "c_1", "2026-08-03T09:00:00Z", target="b_1")
    assert tensions.state().tensions["x_1"][STATE] == TensionState.RESOLVED.value

    tensions.record(Op.TENSION, "x_1", NOW, **{STATE: later})

    assert tensions.state().tensions["x_1"][STATE] == TensionState.RESOLVED.value
    assert tensions.rebuild().tensions["x_1"][STATE] == TensionState.RESOLVED.value
    assert tensions.fold().tensions["x_1"][STATE] == TensionState.RESOLVED.value


@pytest.mark.cap7_resolution
def test_terminality_pins_the_state_and_not_the_whole_record(tensions):
    """Non-vacuity for the guard above: it must not be *"a resolved tension
    ignores later records"*, which would also drop the stamp and the tier. What
    is terminal is the state."""
    widening_log(tensions, moves=())
    tensions.record(Op.RETRACT, "c_1", "2026-08-03T09:00:00Z", target="b_1")
    tensions.record(Op.TENSION, "x_1", NOW, model_tier="frontier",
                    **{STATE: "widening"})

    held = tensions.state().tensions["x_1"]
    assert held[STATE] == TensionState.RESOLVED.value
    assert held["model_tier"] == "frontier"
    assert held["t"] == NOW


@pytest.mark.cap7_resolution
def test_a_resolved_state_is_refused_before_the_record_is_durable(tensions):
    """``TensionError``'s own docstring said this gate *"refuses the same values
    one layer down where they would become durable"*. It did not: only
    ``ledger.transition`` refused `resolved`, so any caller building the record
    itself wrote one. Resolution is what the log already means the moment a
    correction lands, and a second writer of it is a second place for the log
    and the fold to disagree."""
    widening_log(tensions, moves=())
    with pytest.raises(TensionError, match="the fold computes"):
        tensions.record(Op.TENSION, "x_1", NOW, **{STATE: "resolved"})
    with pytest.raises(TensionError):
        make(Op.TENSION, "x_9", MINTED, between=["b_1", "b_2"],
             **{STATE: "resolved"})
    assert tensions.state().tensions["x_1"][STATE] == TensionState.FRESH.value


@pytest.mark.cap7_resolution
def test_a_resolved_state_read_off_the_log_is_terminal_too(tensions):
    """The route the *already-gone-side* rule does not cover, and the reason
    the state is pinned as well.

    When the fold resolved a tension, both sides being gone is what re-resolves
    it on every later record — so a guard that only re-pinned the state would
    look redundant. It is not: a `resolved` that arrived *from the log* — an
    older build's, written before the append gate refused one — sits on a
    tension whose two entries are both alive, and nothing but the pin keeps a
    later append off it. Terminality is *by every route*, and this is a route.
    """
    widening_log(tensions, moves=())
    past_the_gate(tensions, "x_2", MINTED, between=["b_1", "b_2"],
                  **{STATE: "resolved"})
    assert set(tensions.state().beliefs) >= {"b_1", "b_2"}, "both sides stand"

    tensions.record(Op.TENSION, "x_2", NOW, **{STATE: "widening"})

    assert tensions.state().tensions["x_2"][STATE] == "resolved"
    assert tensions.rebuild().tensions["x_2"][STATE] == "resolved"


@pytest.mark.cap7_resolution
def test_a_log_that_already_carries_resolved_still_folds(tensions):
    """Write strict, read tolerant. The word stays in the vocabulary because
    the *fold* has to produce it, and a log written before the append gate
    refused one must not take a main's whole store down."""
    widening_log(tensions, moves=())
    past_the_gate(tensions, "x_2", MINTED, between=["b_1", "b_2"],
                  **{STATE: "resolved"})
    assert tensions.state().tensions["x_2"][STATE] == "resolved"
    assert is_state("resolved") and "resolved" in TENSION_STATES


# ═════════════════════════════════════════════════════════════════════════════
# matrix: minted over a gone side — not live, and never drift over nothing
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_resolution
@pytest.mark.parametrize("verb", [Op.RETRACT, Op.REVISE])
@pytest.mark.parametrize("side", ["b_1", "b_2"])
def test_a_tension_minted_over_a_gone_side_is_not_live(tensions, verb, side):
    """Matrix: *minted over a gone side*.

    ``_resolve_tensions`` fires while folding a correction, so a tension minted
    *after* that correction was never seen by it: it folded `fresh`, with one
    of its two entries absent from the ledger, and nothing would ever look
    again. The pass then computed drift across an entry that does not exist.
    """
    entry(tensions, "b_1", at_days(2), support=["s_1"])
    entry(tensions, "b_2", at_days(2), support=["s_2"])
    tensions.record(verb, "c_1", at_days(1), target=side)

    mint(tensions, "x_1", MINTED, between=["b_1", "b_2"])

    held = tensions.state().tensions["x_1"]
    assert held[STATE] == TensionState.RESOLVED.value
    assert held[BETWEEN] == ["b_1", "b_2"], "the pair was lost"
    assert "x_1" in tensions.state().tensions, "the mint was deleted"
    assert side not in tensions.state().beliefs
    assert tensions.rebuild().tensions["x_1"] == held


@pytest.mark.cap7_resolution
def test_a_tension_minted_over_an_expunged_side_is_not_live(tensions):
    entry(tensions, "b_1", at_days(2), support=["s_1"])
    entry(tensions, "b_2", at_days(2), support=["s_2"])
    tensions.expunge("b_1", t=at_days(1))

    mint(tensions, "x_1", MINTED, between=["b_1", "b_2"])
    assert tensions.state().tensions["x_1"][STATE] == TensionState.RESOLVED.value


@pytest.mark.cap7_resolution
def test_an_entry_that_never_existed_is_not_an_entry_that_left(tensions):
    """Non-vacuity, and the distinction the rule turns on.

    *"Resolve whenever a side is absent from the fold"* would have caught this
    too, and it would be wrong: a tension over an id the log has never seen is
    not a disagreement that ended, it is one whose evidence cannot be read.
    Declaring it over is a guess, and the pass already has an honest answer for
    it.
    """
    mint(tensions, "x_1", MINTED, between=["b_1", "b_2"])
    assert tensions.state().tensions["x_1"][STATE] == TensionState.FRESH.value

    found = ledger.plan(ledger.read(tensions.state().tensions),
                        history=history(tensions), now=NOW)
    assert found.transitions == {}
    assert found.incomputable == {"x_1": UNREADABLE_SIDE}


@pytest.mark.cap7_resolution
def test_the_pass_never_computes_drift_across_an_entry_that_is_gone(tensions):
    """The whole reason the rule exists, asserted as the pass's own behaviour:
    evidence keeps arriving on the surviving side, and nothing is computed from
    it."""
    widening_log(tensions, moves=())
    tensions.record(Op.RETRACT, "c_1", "2026-08-03T00:00:00Z", target="b_1")
    entry(tensions, "b_2", "2026-08-03T12:00:00Z", support=["s_2", "s_more"])

    found = ledger.plan(ledger.read(tensions.state().tensions),
                        history=history(tensions), now=NOW)
    assert found.transitions == {}
    assert found.incomputable == {"x_1": RESOLVED_ALREADY}


# ═════════════════════════════════════════════════════════════════════════════
# a tension has a pair, and it says so before it is durable (9d's obligation)
# ═════════════════════════════════════════════════════════════════════════════


def test_a_tensions_first_record_must_name_the_two_entries_it_links(tensions):
    """*"A tension is the record of two entries that disagree"* (glossary) was
    the one part of the definition nothing enforced.

    ``validate_tension_fields`` cannot enforce it — it sees fields and not the
    log, so it cannot tell a mint from a transition and has to treat ``between``
    as optional on every record. The result was durable from both ends: a mint
    that simply left it off, and a transition naming an id that was never
    minted, each producing a tension that is permanently pairless, permanently
    not computable, and counted by every pass for ever. The store knows both the
    fields and which ids the fold holds, so the rule lives there. This is the
    invariant story 9d mints against.
    """
    with pytest.raises(TensionError, match="two entries"):
        tensions.record(Op.TENSION, "x_1", MINTED, **{STATE: "fresh"})
    with pytest.raises(TensionError, match="two entries"):
        tensions.record(Op.TENSION, "never_minted", NOW, **{STATE: "widening"})
    assert tensions.state().tensions == {}


def test_a_transition_over_a_tension_the_log_holds_still_needs_no_pair(tensions):
    """The other half: the rule is about a *first* record, so the ordinary
    nightly transition — a state and nothing else — is unaffected."""
    widening_log(tensions, moves=("b_1",))
    tensions.record(Op.TENSION, "x_1", NOW, **{STATE: "widening"})
    assert tensions.state().tensions["x_1"][BETWEEN] == ["b_1", "b_2"]


def test_an_erased_tension_is_still_a_tension_the_log_has_seen(tensions):
    """An expunge has to stay an erasure rather than becoming a validation
    error: a later record for an erased tension is refused by the *fold*, which
    is where erasure is enforced, and not by the pair gate."""
    widening_log(tensions, moves=())
    tensions.expunge("x_1", t="2026-08-03T09:00:00Z")
    tensions.record(Op.TENSION, "x_1", NOW, **{STATE: "widening"})
    assert "x_1" not in tensions.state().tensions


# ═════════════════════════════════════════════════════════════════════════════
# matrix: expunged tension — the tension itself is erased, and it is gone
# ═════════════════════════════════════════════════════════════════════════════


def test_expunging_the_tension_itself_removes_it_from_the_fold(tensions):
    widening_log(tensions, moves=())
    tensions.expunge("x_1", t="2026-08-03T09:00:00Z")
    assert "x_1" not in tensions.state().tensions
    assert "x_1" in tensions.state().expunged
    assert tensions.rebuild().tensions == {}


def test_an_expunged_tension_is_not_resurrected_by_a_later_transition(tensions):
    widening_log(tensions, moves=())
    tensions.expunge("x_1", t="2026-08-03T09:00:00Z")
    tensions.record(Op.TENSION, "x_1", NOW, **{STATE: "widening"})
    assert "x_1" not in tensions.state().tensions


def test_expunging_a_tension_leaves_its_two_entries_standing(tensions):
    """An erasure of the *record of a disagreement* is not an erasure of either
    thing that disagreed."""
    widening_log(tensions, moves=())
    tensions.expunge("x_1", t="2026-08-03T09:00:00Z")
    assert set(tensions.state().beliefs) >= {"b_1", "b_2"}


def test_the_erased_tension_leaves_no_text_behind(tensions):
    widening_log(tensions, moves=())
    tensions.expunge("x_1", t="2026-08-03T09:00:00Z")
    written = (tensions.log.root / "2026-08.jsonl").read_text(encoding="utf-8")
    assert '"between"' not in written or "x_1" not in written.split("tombstone")[0]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: both sides stand — no transition is appended; and the re-run
# ═════════════════════════════════════════════════════════════════════════════


def test_nothing_changed_appends_nothing(tensions):
    widening_log(tensions, moves=())
    before = tensions.state().canonical_json()
    found = ledger.plan(ledger.read(tensions.state().tensions),
                        history=history(tensions), now=NOW)
    assert found.transitions == {} and found.unchanged == ("x_1",)
    assert tensions.state().canonical_json() == before


def test_a_transition_to_the_state_already_held_is_refused(tensions):
    """The same refusal ``loops.ledger.rescale`` makes: a record that changes
    nothing is a record that says something happened, and this runs nightly."""
    widening_log(tensions, moves=())
    with pytest.raises(TensionError, match="already"):
        ledger.transition(read_one(tensions, "x_1"), to=TensionState.FRESH)


def test_the_same_log_and_the_same_now_give_an_identical_plan(tensions):
    widening_log(tensions, moves=("b_1",))
    read = ledger.read(tensions.state().tensions)
    first = ledger.plan(read, history=history(tensions), now=NOW)
    second = ledger.plan(read, history=history(tensions), now=NOW)
    assert first == second


def test_a_plan_moves_only_when_the_injected_now_moves(tensions):
    widening_log(tensions, minted=at_days(PERSISTENCE_DAYS - 1), moves=())
    read = ledger.read(tensions.state().tensions)
    inside = ledger.plan(read, history=history(tensions), now=NOW)
    outside = ledger.plan(read, history=history(tensions),
                          now=at_days(-2))
    assert inside.transitions == {}
    assert outside.transitions == {"x_1": {STATE: "persistent"}}


def test_the_plan_is_a_value_and_computing_it_writes_nothing(tensions):
    widening_log(tensions, moves=("b_1",))
    before = {p: p.read_bytes() for p in tensions.log.shards()}
    state = tensions.state().canonical_json()
    ledger.plan(ledger.read(tensions.state().tensions),
                history=history(tensions), now=NOW)
    assert {p: p.read_bytes() for p in tensions.log.shards()} == before
    assert tensions.state().canonical_json() == state


def test_plan_never_raises_on_a_hostile_table():
    for hostile in (None, "text", 7, {"x_1": "not a tension"}, {"x_1": None}):
        found = ledger.plan(hostile, history=(), now=NOW)
        assert isinstance(found, Plan)
        assert found.transitions == {}


# ═════════════════════════════════════════════════════════════════════════════
# a tension goes on moving — every transition the vocabulary allows, twice
# ═════════════════════════════════════════════════════════════════════════════

#: Which entries have to accumulate evidence for the log to compute each state.
#: `fresh` is absent because nothing computes it: every tension is born there
#: and the pass never puts one back.
_ACCUMULATE = {"widening": ("b_1",), "closing": ("b_1", "b_2"), "persistent": ()}

#: Every ordered pair of states a tension may move between.
_ORDERED_MOVES = [
    (first, second)
    for first in ("fresh", "widening", "closing", "persistent")
    for second in sorted(_ACCUMULATE)
    if first != second
]


def _push(store, *, to, since, cited):
    """Make the log say ``to`` about ``x_1``, and return the plan and its
    instant.

    ``cited`` tracks how many sources each entry has cited so far, because
    accumulation is *strictly more than at the baseline* — a belief re-stated
    with the same sources has not moved, which is the point of counting the
    support set rather than the records.
    """
    moving = _ACCUMULATE[to]
    for ident in moving:
        cited[ident] += 1
        entry(store, ident, at_hours(1, since=since),
              support=[f"s_{ident}_{n}" for n in range(cited[ident])])
    forward = 1.0 if moving else PERSISTENCE_DAYS + 1.0
    at = at_days(-forward, since=since)
    found = ledger.plan(ledger.read(store.state().tensions),
                        history=history(store), now=at)
    return found, at


@pytest.mark.parametrize("first,second", _ORDERED_MOVES,
                         ids=lambda pair: pair if isinstance(pair, str) else str(pair))
def test_a_tension_goes_on_moving_after_its_first_transition(
    tensions, first, second
):
    """A tension that moved once must be able to move again — every ordered
    pair, driven through real appends.

    Review froze one with two mutations that left the whole suite green:
    ``if state != fresh: target = state`` in ``widening.drift``, and the
    narrower *"a widening tension never closes"*. Nothing caught either,
    because every case that drove a state change started from a `fresh`
    tension — ``widening_log`` writes `fresh`, ``seed_tension`` writes `fresh`,
    and the only non-`fresh` holders either asserted symmetry without reading
    the value or called ``ledger.transition`` directly instead of ``drift``.
    The idempotence cases cannot help: their second run legitimately expects no
    move.

    A build where tensions freeze on their first transition reports a life
    permanently widening that never closes — with *drift is tension velocity*
    and *loop advancement is tensions closing* both counted off it.
    """
    base = MINTED
    minted = at_days(-1.0, since=base)
    entry(tensions, "b_1", base, support=["s_b_1_0"])
    entry(tensions, "b_2", base, support=["s_b_2_0"])
    mint(tensions, "x_1", minted, between=["b_1", "b_2"])
    cited = {"b_1": 1, "b_2": 1}
    at = minted

    if first != "fresh":
        found, at = _push(tensions, to=first, since=at, cited=cited)
        assert found.transitions == {"x_1": {STATE: first}}, "the first move"
        tensions.record(Op.TENSION, "x_1", at, **found.transitions["x_1"])
        assert tensions.state().tensions["x_1"][STATE] == first

    found, at = _push(tensions, to=second, since=at, cited=cited)
    assert found.transitions == {"x_1": {STATE: second}}, (
        f"a tension in {first!r} could not move to {second!r}"
    )
    tensions.record(Op.TENSION, "x_1", at, **found.transitions["x_1"])
    assert tensions.state().tensions["x_1"][STATE] == second
    assert tensions.rebuild().tensions["x_1"][STATE] == second


def test_no_threshold_decides_widening_at_the_layer_that_writes(tensions):
    """The Ask-First rule, asserted where the append is *composed* and not only
    where the drift is computed.

    ``test_no_threshold_decides_widening`` calls ``ledger.evaluate``, so review
    inserted the Ask-First-listed change one layer above it — a young-tension
    suppression in ``ledger.plan`` — and the suite stayed green: the plan-level
    widening cases are ``for fields in found.transitions.values()`` loops, which
    pass vacuously over an empty mapping, and every pass-level case uses a
    tension about three weeks old.

    So this asserts the mapping itself, over the same age sweep.
    """
    for age in (0.0, 0.5, 1.0, 3.0, 7.0, PERSISTENCE_DAYS, PERSISTENCE_DAYS * 100):
        with Store(tensions.root.parent / f"p{age}") as store:
            widening_log(store, minted=at_days(age), moves=("b_1",))
            found = ledger.plan(ledger.read(store.state().tensions),
                                history=history(store), now=NOW)
            assert found.transitions == {"x_1": {STATE: "widening"}}, age
            assert found.unchanged == () and found.incomputable == {}


def test_every_reason_a_plan_gives_is_one_of_a_closed_set():
    """``Plan.incomputable`` is documented and logged as a closed set of
    constants, and ``str(exc)`` was reaching it — a free-form message, from an
    exception kind that routinely quotes the value that caused it, into a
    mapping the pass writes to a log line (AD-22)."""
    hostile = {
        "a": Tension(id="a"),
        "b": Tension(id="b", state="fresh"),
        "c": Tension(id="c", state="resolved", between=("b_1", "b_2"), at=MINTED),
        "d": "not a tension at all",
        "e": Tension(id="e", state="fresh", between=("b_1", "b_2"), at="yesterday"),
        "f": Tension(id="f", state="fresh", between=("b_1", "b_2"),
                     at="2099-01-01T00:00:00Z"),
        "g": Tension(id="g", state="widenning", between=("b_1", "b_2"), at=MINTED),
    }
    found = ledger.plan(hostile, history=(), now=NOW)
    assert set(found.incomputable) == set(hostile)
    assert set(found.incomputable.values()) <= REASONS
    assert found.transitions == {}
    # And no reason is a sentence: a reason is a token somebody can group by.
    assert all(" " not in reason for reason in found.incomputable.values())


def test_a_table_with_keys_of_two_kinds_costs_one_tension_and_not_the_pass():
    """``plan`` sorted the mapping directly, so a single non-string key raised a
    ``TypeError`` out of the sort — before any tension was looked at — and cost
    a main every tension they own."""
    found = ledger.plan(
        {7: Tension(id="7"), "x_1": Tension(id="x_1"), (): None},
        history=(), now=NOW,
    )
    assert isinstance(found, Plan)
    assert set(found.incomputable) == {"7", "x_1", "()"}


# ═════════════════════════════════════════════════════════════════════════════
# matrix: neither side wrong — nothing ranks the two entries
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_neutrality
@pytest.mark.parametrize("ranked", sorted(RANKED_FIELDS))
def test_a_tension_record_naming_a_ranked_side_is_refused_at_the_append(
    tensions, ranked
):
    """The strongest of the four guards, because it is behaviour rather than a
    scan: adding a ranking is a hard error where records become durable.

    The natural way to break the rule is not malice — it is a helpful line
    recording which entry the evidence went against so a message can be phrased
    better. That line fails here.
    """
    with pytest.raises(TensionError, match="neither side"):
        tensions.record(Op.TENSION, "x_1", MINTED, between=["b_1", "b_2"],
                        **{STATE: "widening"}, **{ranked: "b_1"})
    assert tensions.state().tensions == {}


@pytest.mark.cap7_neutrality
def test_the_ranked_field_gate_covers_every_way_a_record_is_built(tensions):
    """Through ``make``, through ``Store.record`` and through ``Store.append``
    with a hand-built record — the gate is at the append, so all three meet it.
    """
    with pytest.raises(TensionError):
        make(Op.TENSION, "x_1", MINTED, winner="b_1")
    with pytest.raises(TensionError):
        tensions.record(Op.TENSION, "x_1", MINTED, winner="b_1")
    hand = Record(op=Op.TENSION, id="x_1", t=MINTED,
                  data={"t": MINTED, "op": "tension", "id": "x_1",
                        "v": SCHEMA_VERSION, "mistaken": "b_2"})
    with pytest.raises(TensionError):
        tensions.append(hand)


@pytest.mark.cap7_neutrality
def test_a_ranked_field_is_only_refused_on_a_tension(tensions):
    """Non-vacuity in the other direction: the gate is op-aware, so it does not
    quietly forbid the word everywhere and pass by accident."""
    tensions.record(Op.LOOP_TRANSITION, "l_1", MINTED,
                    loop="win-the-race", **{STATE: "advancing"})
    assert "win-the-race" in tensions.state().loops


@pytest.mark.cap7_neutrality
@pytest.mark.parametrize("state", sorted(LIVE_STATES))
@pytest.mark.parametrize(
    "pattern", list(itertools.product((0, 1, 2), repeat=2)),
    ids=lambda p: f"{p[0]}-{p[1]}",
)
def test_the_computation_is_symmetric_under_swapping_the_two_sides(
    state, pattern
):
    """Every state, every accumulation pattern, both orders — identical.

    The property a ranking cannot survive: if any rule ever preferred a side,
    reversing the pair would change the answer. Asserted over the whole matrix
    rather than one example, because an asymmetry introduced for one state is
    exactly the one an example would miss.
    """
    left, right = pattern
    forward = [Evidence("b_1", 1, 1 + left), Evidence("b_2", 1, 1 + right)]
    backward = list(reversed(forward))

    one = drift(state=state, recorded_at=MINTED, sides=forward, now=NOW)
    other = drift(state=state, recorded_at=MINTED, sides=backward, now=NOW)
    assert one == other, "the pair has an order"
    assert one.accumulated == other.accumulated


@pytest.mark.cap7_neutrality
def test_the_symmetry_check_catches_a_computation_that_prefers_a_side():
    """Non-vacuity. A guard nobody has tried to defeat is a guard resting on
    nothing, so the asymmetric implementation is run against the comparison the
    case above makes."""

    def biased(sides):
        # "the first side is the stated one, so its evidence counts double" —
        # the plausible line.
        return "widening" if sides[0].accumulated else "closing"

    forward = [Evidence("b_1", 1, 2), Evidence("b_2", 1, 1)]
    assert biased(forward) != biased(list(reversed(forward))), (
        "the symmetry comparison would not notice a preferred side"
    )


@pytest.mark.cap7_neutrality
def test_a_transition_carries_exactly_one_field_and_it_is_the_state(tensions):
    """The pass's entire append vocabulary. Anything else — which side moved,
    how much, a score — is either a ranking or a stored counter, and both are
    forbidden for different reasons."""
    widening_log(tensions, moves=("b_1",))
    found = read_one(tensions, "x_1")
    for target in sorted(LIVE_STATES - {found.state}):
        fields = ledger.transition(found, to=target)
        assert set(fields) == {STATE}
        assert fields[STATE] == target


@pytest.mark.cap7_neutrality
def test_nothing_the_pass_appends_names_a_side(tensions):
    """The whole plan, over a widening tension, checked field by field."""
    widening_log(tensions, moves=("b_1",))
    found = ledger.plan(ledger.read(tensions.state().tensions),
                        history=history(tensions), now=NOW)
    for fields in found.transitions.values():
        assert set(fields) == {STATE}
        assert not RANKED_FIELDS & fields.keys()
        assert "b_1" not in fields.values() and "b_2" not in fields.values()


@pytest.mark.cap7_neutrality
@pytest.mark.parametrize(
    "spelling",
    ["winner_id", "winning_side", "is_winner", "side_that_won",
     "more_credible", "truer_side", "moved_side", "which_moved",
     "winnerId", "movedSide", "the_stronger_entry", "loser_side",
     "entry_that_prevailed", "side_which_moved", "was_mistaken"],
)
def test_a_ranked_side_is_refused_under_any_spelling(tensions, spelling):
    """Matrix: *ranked field, any spelling* — and every one of the first eight
    was verified **accepted and durable** against the exact-string gate this
    replaced.

    ``moved_side`` is the one that matters most, because it is the line
    ``half.tensions.widening`` itself names as the likely breach: *a helpful
    line recording which entry the evidence went against, so the morning
    surface can phrase it better*. It passed a denylist containing ``winner``,
    ``loser`` and twenty-seven other exact spellings, which is what a denylist
    of exact spellings is worth.
    """
    with pytest.raises(TensionError, match="neither side"):
        tensions.record(Op.TENSION, "x_1", MINTED, between=["b_1", "b_2"],
                        **{STATE: "widening"}, **{spelling: "b_1"})
    assert tensions.state().tensions == {}


@pytest.mark.cap7_neutrality
def test_every_exact_spelling_in_the_denylist_still_fails_the_predicate():
    """The seed set and the rule cannot drift apart: ``RANKED_FIELDS`` is what
    the suite drives ``ranks_a_side`` over, so a name in it that the predicate
    lets through is a case passing while the gate does not hold."""
    escaped = sorted(name for name in RANKED_FIELDS if not ranks_a_side(name))
    assert not escaped, escaped


@pytest.mark.cap7_neutrality
def test_the_ranking_predicate_leaves_the_honest_names_alone():
    """Non-vacuity in the other direction, and it is not a formality: a
    predicate that refused every name would forbid the pass's own ``moved``
    count and the symmetric computation's own ``sides``, and the only way to
    ship it would be to stop applying it."""
    for honest in ("state", "between", "sides", "pair", "paired", "moved",
                   "moves", "accumulated", "entry_id", "unchanged", "history",
                   "incomputable", "transition", "tension_id", "readable",
                   "computable", "support", "license", "model_tier"):
        assert not ranks_a_side(honest), honest


@pytest.mark.cap7_neutrality
def test_a_name_is_read_as_words_in_both_house_styles():
    assert words_in("winner_id") == ("winner", "id")
    assert words_in("winnerId") == ("winner", "id")
    assert words_in("SIDE_THAT_WON") == ("side", "that", "won")
    assert ranked_names({"state": 1, "moved_side": 2, "between": 3}) == ("moved_side",)


@pytest.mark.cap7_neutrality
def test_the_ranking_vocabulary_is_pinned_by_value():
    """The neutrality gate's whole margin was the case that expands over
    ``RANKED_FIELDS`` one for one, and nothing pinned the set — so deleting
    twelve entries landed the gate on exactly its floor, green, with ``loser``
    and ``ranked`` both appending cleanly and folding.

    Pinned by value, the way ``PERSISTENCE_DAYS`` is, so shrinking the
    vocabulary is a red test rather than a smaller collection.
    """
    assert RANKED_FIELDS == frozenset({
        "winner", "loser", "won", "lost", "beats",
        "stronger", "weaker", "outranks", "rank", "ranking", "ranked",
        "primary", "secondary", "dominant", "prevailing", "prevails",
        "preferred", "favoured", "favored", "favours", "favors",
        "correct_side", "wrong_side", "right_side",
        "mistaken", "discredited", "refuted", "disproven", "verdict",
    })
    assert {"winner", "winning", "won", "loser", "lost", "stronger", "weaker",
            "mistaken", "verdict", "truer", "credible", "superseded"} <= RANKING_WORDS
    assert len(RANKING_WORDS) >= 60


@pytest.mark.cap7_neutrality
@pytest.mark.parametrize(
    "stray,value",
    [("claim", "he never writes"), ("subject", "self"), ("independent", 3),
     ("ledger", "revealed"), ("target", "b_1"), ("note", "a summary"),
     ("contact", "Asha"), ("plan", ["a line"])],
)
def test_a_tension_record_may_carry_nothing_a_tension_is_not(tensions, stray, value):
    """The allowlist, and the reason a denylist could not do this job.

    A transition would append whatever it was handed: a ``claim`` or an
    ``independent`` count beside the state validated and became durable, which
    is belief content written into a tension record — permanently, since no
    correction to either entry can take a field off a tension (AD-22). A tension
    is a state, the pair it links and the license the ladder admitted.
    """
    widening_log(tensions, moves=())
    before = dict(tensions.state().tensions["x_1"])
    with pytest.raises(TensionError, match="state, the pair"):
        tensions.record(Op.TENSION, "x_1", NOW,
                        **{STATE: "widening", stray: value})
    assert tensions.state().tensions["x_1"] == before


@pytest.mark.cap7_neutrality
def test_the_allowlist_still_admits_everything_a_tension_is(tensions):
    """Non-vacuity: a gate that refused every field would refuse the mint."""
    entry(tensions, "b_1", at_days(1), support=["s_1"])
    entry(tensions, "b_2", at_days(1), support=["s_2"])
    tensions.record(Op.TENSION, "x_1", MINTED, between=["b_1", "b_2"],
                    model_tier="frontier", **{STATE: "fresh"},
                    **ladder.admitted(support=["s_1"]))
    held = tensions.state().tensions["x_1"]
    assert held[BETWEEN] == ["b_1", "b_2"] and held["license"] == str(ladder.FLOOR)
    assert set(held) - set(RESERVED_KEYS) <= TENSION_FIELDS


@pytest.mark.cap7_neutrality
def test_the_guards_cover_the_tension_code_outside_the_two_packages():
    """Matrix: *guard coverage*.

    Every neutrality and resolution scan read ``half/tensions`` and
    ``half/consolidate`` and nothing else, while this story wrote tension code
    into the fold, the append gate and the registry. Review confirmed it by
    injecting ``held["winner"] = pair[0]`` into the fold's own merge branch —
    the one route into the tension table the append gate never sees — and
    watching the whole suite pass.

    **The assertion used to be a subset, and a subset is not coverage.** Story
    9d added ``mint_view`` and ``note_mint`` to the registry, registered
    neither, and this case stayed green — because ``<=`` asks whether the
    listed names are covered and never whether anything unlisted is not.
    Review sorted the pair inside ``note_mint``, the one function that creates
    every tension record, and the whole suite passed; the identical line in
    ``note_transition`` was caught. So the rule is now the other way round:
    every function in an outpost file whose *name* says it handles a tension or
    a mint must be registered, which is red on the day such a function is
    written rather than on the day somebody notices.
    """
    labels = {label for label, _ in _guarded_trees()}
    assert {
        "half/store/fold.py:fold",
        "half/store/fold.py:_resolve_tensions",
        "half/store/records.py:validate_tension_fields",
        "half/actor/registry.py:tension_view",
        "half/actor/registry.py:note_transition",
        "half/actor/registry.py:mint_view",
        "half/actor/registry.py:note_mint",
    } <= labels
    assert any(label.startswith("half/tensions/") for label in labels)
    assert any(label.startswith("half/consolidate/") for label in labels)

    unregistered: list[str] = []
    for relative, registered in sorted(OUTPOSTS.items()):
        for name in sorted(_tension_functions(relative) - set(registered)):
            unregistered.append(f"{relative}:{name}")
    assert not unregistered, (
        f"tension code the guards never read: {unregistered}. Add each to "
        f"OUTPOSTS — a scan that does not parse a function cannot fail on it, "
        f"and this is how story 9d's two doors went unscanned"
    )


@pytest.mark.cap7_neutrality
def test_the_scans_catch_a_ranking_written_into_the_fold():
    """Non-vacuity for the coverage above, and it is the exact mutation review
    ran against a green suite."""
    injected = ast.parse(
        "def fold(records):\n"
        "    for record in records:\n"
        "        held['winner'] = between[0]\n"
        "        held['mistaken'] = between[1]\n"
    )
    assert _ranking_identifiers(injected)
    assert _ranks_the_pair(injected)


@pytest.mark.cap7_neutrality
def test_the_name_scan_catches_a_ranked_function_the_package_merely_offers():
    """*"The guard covers what a record carries, not what a module offers."*

    ``def stronger_side(tension)`` added to ``half/tensions/ledger.py`` left the
    whole suite green, because the record gate matched exact strings and the
    module scan matched the same exact strings — ``stronger`` was in the set,
    ``stronger_side`` was not. One vocabulary now, read as words.
    """
    for offered in ("def stronger_side(tension):\n    return tension\n",
                    "def which_moved(sides):\n    return sides\n",
                    "class TruerSide:\n    pass\n"):
        assert _ranking_identifiers(ast.parse(offered)), offered


#: Names that hold a tension's pair. Any positional read of one is a first and
#: a second, which is one short step from a winner and a loser.
#:
#: ``both`` and ``names`` are here because story 9d gave the pair two new names
#: and did not tell the guard. ``half.consolidate.candidates.Couple`` travels
#: as ``both`` and offers ``names``, so every line in the minting half was
#: outside this vocabulary: review replaced ``filter.weight``'s body with
#: ``return surprisal(couple.both[0], ...)`` — the pair read positionally, one
#: side ranked over the other, in the function the budget's ordering runs
#: through — and the whole suite stayed green. That is the guard-catches-a-
#: spelling shape, in the story that introduced the spelling.
_PAIR_NAMES = {"between", "sides", "pair", "ids", "entries", "both", "names"}

#: Ways one of two things is chosen over the other.
_CHOOSERS = {"sorted", "max", "min", "sort", "nlargest", "nsmallest"}


def _holds_the_pair(node: ast.AST) -> bool:
    """Whether ``node`` is an expression that evaluates to a tension's pair.

    Three spellings, and the third was found by probing this guard rather than
    by reading it: ``between``, ``couple.both`` — and ``fields["between"]``,
    which the registry's doors and the append gate reach the pair through and
    which named no pair at all as far as the scan was concerned.
    ``sorted(fields["between"])`` inside ``note_mint`` passed a green suite.
    """
    if isinstance(node, ast.Name):
        return node.id in _PAIR_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _PAIR_NAMES
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        # ``fields["between"]`` and ``fields[BETWEEN]`` alike: the key is the
        # name, whether it was spelled or came through a constant.
        return str(node.slice.value) in _PAIR_NAMES
    return False


def _ranks_the_pair(tree: ast.AST) -> list[int]:
    """Line numbers where ``tree`` reads the pair positionally or orders it."""
    found: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if (_holds_the_pair(node.value)
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, int)):
                found.append(node.lineno)
        if isinstance(node, ast.Call):
            callee = (node.func.id if isinstance(node.func, ast.Name)
                      else node.func.attr if isinstance(node.func, ast.Attribute)
                      else "")
            if callee not in _CHOOSERS:
                continue
            for argument in node.args:
                if any(_holds_the_pair(inner) for inner in ast.walk(argument)):
                    found.append(node.lineno)
    return found


@pytest.mark.cap7_neutrality
def test_nothing_in_the_tension_surface_reads_the_pair_positionally():
    offenders: list[str] = []
    for label, tree in _guarded_trees():
        offenders += [f"{label}:{line}" for line in _ranks_the_pair(tree)]
    assert not offenders, (
        f"the pair is read positionally or ordered at {offenders}. Its order "
        f"is the log's, and it means nothing: a first and a second is one step "
        f"from a winner and a loser"
    )


@pytest.mark.cap7_neutrality
@pytest.mark.parametrize(
    "bypass",
    ["def f(between):\n    return between[0]\n",
     "def f(sides):\n    return sides[1].id\n",
     "def f(self):\n    return self.between[0]\n",
     "def f(sides):\n    return sorted(sides, key=lambda s: s.now)\n",
     "def f(sides):\n    return max(sides, key=lambda s: s.now)\n",
     "def f(pair):\n    return min(pair)\n",
     # The exact mutation review ran against a green suite: the couple's own
     # spelling of its pair, read positionally, in the function the budget's
     # ordering runs through.
     "def weight(couple):\n    return surprisal(couple.both[0])\n",
     "def f(couple):\n    return couple.names[1]\n",
     "def f(both):\n    return sorted(both, key=lambda s: s.at)\n",
     # Found by probing this guard: the pair reached through the field name,
     # which is how every door in the registry and the append gate holds it.
     "def f(fields):\n    return sorted(fields['between'])\n",
     "def f(fields):\n    return fields['sides'][0]\n"],
    ids=["index-0", "index-1", "attribute-index", "sorted", "max", "min",
         "couple-both-index", "couple-names-index", "both-sorted",
         "field-key-sorted", "field-key-index"],
)
def test_the_positional_scan_catches_every_way_a_side_is_chosen(bypass):
    """Non-vacuity, one shape at a time. A scan that knew only the subscript
    is one somebody walks around with a ``max``."""
    assert _ranks_the_pair(ast.parse(bypass)), bypass


def _ranking_identifiers(tree: ast.AST) -> set[str]:
    """Every *name* in ``tree`` — never a docstring — that ranks a side.

    Read with ``half.tensions.widening.ranks_a_side``, the same predicate the
    append gate refuses record fields with. It used to be an exact-string
    membership test against ``RANKED_FIELDS``, which meant the *record* gate
    and the *module* scan had drifted into two different rules: review added
    ``def stronger_side(tension)`` to ``half/tensions/ledger.py`` and the whole
    suite stayed green, because ``stronger`` was in the set and
    ``stronger_side`` was not. One vocabulary now, read two ways — what a
    record carries, and what a module offers.

    Docstrings are excluded deliberately — this file's own module docstring
    says "winner" four times, and so does the ledger's, because saying what is
    forbidden is how the rule survives.
    """
    found: set[str] = set()

    def note(word: object) -> None:
        if isinstance(word, str) and word not in GUARD_NAMES and ranks_a_side(word):
            found.add(word)

    docstrings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            note(node.name)
        elif isinstance(node, ast.arg):
            note(node.arg)
        elif isinstance(node, ast.Name):
            note(node.id)
        elif isinstance(node, ast.Attribute):
            note(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            note(node.arg)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant):
                    note(key.value)
        elif (isinstance(node, ast.Constant) and node not in docstrings
              and isinstance(node.value, str) and node.value.isidentifier()):
            # A bare literal used as a key or a value. Kept because
            # ``fields["winner"] = ...`` is a Subscript, not a Dict.
            #
            # Identifiers only. The rule reads a *name*, and every refusal
            # message in this surface is a sentence saying which names are
            # forbidden and why — *"neither side of a tension is wrong"* — so
            # reading prose as a name makes the guard fire on the code that
            # enforces it.
            note(node.value)
    return found


@pytest.mark.cap7_neutrality
def test_no_name_in_the_tension_surface_comes_from_the_ranking_vocabulary():
    """The fourth guard, aimed at the shape story 6c's no-authoring rule
    missed: forbidding three spellings of *writing* a field while the content
    was composed elsewhere and handed to the blessed writer.

    So this reads names rather than writes — a function, an argument, an
    attribute, a keyword or a dict key called ``winner`` fails here whether or
    not it ever reaches a record. The one file allowed to say the words is the
    module that *defines the denylist*, because a denylist has to name what it
    forbids.
    """
    offenders: list[str] = []
    for label, tree in _guarded_trees(skip_denylist_owner=True):
        for word in sorted(_ranking_identifiers(tree)):
            offenders.append(f"{label}:{word}")
    assert not offenders, (
        f"the tension surface names {offenders}. Neither side of a tension is "
        f"wrong; for a person both entries can be true at once, which is the "
        f"whole reason the object exists"
    )


@pytest.mark.cap7_neutrality
@pytest.mark.parametrize(
    "bypass",
    ['def winner(sides):\n    return sides\n',
     'def f(sides, winner=None):\n    return winner\n',
     'def f(s):\n    return {"winner": s}\n',
     'def f(s):\n    return s.winner\n',
     'def f(s):\n    return note(mistaken=s)\n',
     'def f(s):\n    stronger = s\n    return stronger\n'],
    ids=["function", "argument", "dict-key", "attribute", "keyword", "local"],
)
def test_the_ranking_name_scan_catches_every_way_one_arrives(bypass):
    """Non-vacuity, one shape at a time — including the one that matters most:
    a value composed under an innocent name and handed to a blessed writer is
    caught by the *dict key*, and one composed under a ranked local by the
    local."""
    assert _ranking_identifiers(ast.parse(bypass)), bypass


@pytest.mark.cap7_neutrality
def test_no_function_in_the_tension_surface_returns_one_of_the_two_sides():
    """A helper that hands back *a* side is a winner however it is named.

    Asserted by signature and by return annotation over the ledger's public
    surface: nothing returns a bare entry id, and ``names`` — the one question
    asked about the pair — is a membership test rather than an accessor.
    """
    import inspect

    for name, function in vars(ledger).items():
        if name.startswith("_") or not inspect.isfunction(function):
            continue
        arguments = set(inspect.signature(function).parameters)
        assert not any(ranks_a_side(argument) for argument in arguments), (
            f"ledger.{name} takes a ranking"
        )
        assert not ranks_a_side(name), f"ledger offers {name!r}"
    assert inspect.signature(Tension.names).return_annotation == "bool"


@pytest.mark.cap7_neutrality
def test_the_resolution_records_nothing_about_which_side_went(tensions):
    """The fold's own half of the rule, asserted on the record rather than on
    the code: a resolved tension differs from the minted one in exactly one
    key, and its value is a state."""
    widening_log(tensions, moves=())
    minted = dict(tensions.state().tensions["x_1"])
    tensions.record(Op.REVISE, "c_1", "2026-08-03T09:00:00Z", target="b_1")
    resolved = dict(tensions.state().tensions["x_1"])

    differing = {k for k in set(minted) | set(resolved)
                 if minted.get(k) != resolved.get(k)}
    assert differing == {STATE}
    assert resolved[STATE] in TENSION_STATES


# ═════════════════════════════════════════════════════════════════════════════
# matrix: license — `behave`, and nothing here promotes it
# ═════════════════════════════════════════════════════════════════════════════


def test_a_minted_tension_carries_behave(tensions):
    widening_log(tensions, moves=())
    assert tensions.state().tensions["x_1"]["license"] == str(ladder.FLOOR)


def test_a_transition_neither_writes_nor_lifts_a_license(tensions):
    widening_log(tensions, moves=("b_1",))
    before = tensions.state().tensions["x_1"]["license"]
    tensions.record(Op.TENSION, "x_1", NOW,
                    **ledger.transition(read_one(tensions, "x_1"),
                                        to=TensionState.WIDENING))
    assert tensions.state().tensions["x_1"]["license"] == before


def test_no_module_in_the_tension_surface_writes_a_license_field():
    """The ladder's writer gate, one object over: `assert` must not become a
    field anybody can set, at the price of three fields instead of one."""
    gated = {"license", "known_to_main", "quarantined", "rung"}
    offenders: list[str] = []
    # ``SURFACE`` rather than the outposts, and deliberately: this asks who
    # *composes* a license, and the fold and the append gate compose nothing —
    # they carry and check records they are handed, and both legitimately name
    # ``rung`` on a ceiling record that has nothing to do with a tension. What
    # a tension record may carry is ``records.TENSION_FIELDS``, asserted as
    # behaviour above.
    for label, tree in (
        (str(path.relative_to(ROOT)),
         ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for area in SURFACE
        for path in sorted((ROOT / area).rglob("*.py"))
    ):
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and key.value in gated:
                        offenders.append(f"{label}:{key.lineno}")
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value in gated):
                offenders.append(f"{label}:{node.lineno}")
    assert not offenders, f"a license field is written outside the ladder: {offenders}"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: purity, replay, and salience left alone
# ═════════════════════════════════════════════════════════════════════════════


def test_the_ledger_writes_nothing_itself(tensions):
    """Every writing entry point returns *fields*; the caller appends them
    under the main's own mutex (AD-1)."""
    widening_log(tensions, moves=("b_1",))
    before = {p: p.read_bytes() for p in tensions.log.shards()}
    ledger.transition(read_one(tensions, "x_1"), to=TensionState.WIDENING)
    ledger.sides(read_one(tensions, "x_1"), history=history(tensions))
    ledger.evaluate(read_one(tensions, "x_1"), history=history(tensions), now=NOW)
    assert {p: p.read_bytes() for p in tensions.log.shards()} == before


def test_no_module_in_the_tension_surface_reads_a_clock():
    """AD-30. ``now`` is injected or the answer is not computed.

    Three scans rather than one, because each catches what the others cannot:
    the **call** scan sees ``time.time()`` and ``datetime.now()``; the
    **import** scan sees the module arriving at all, which is what a call scan
    misses until somebody uses it; and the **clock** scan sees a real ``Clock``
    being constructed or read, which is neither an ambient import nor an
    ambient call — ``half.schedule.clock`` is the one sanctioned reader, and
    the pass is allowed to hold its ``Now`` type without ever asking it the
    time.
    """
    ambient = {"now", "utcnow", "today", "time", "monotonic", "perf_counter",
               "random", "getenv", "urandom", "uuid4"}
    forbidden_roots = {"time", "datetime", "random", "secrets", "uuid",
                       "calendar", "sched"}
    for area in SURFACE:
        for path in sorted((ROOT / area).rglob("*.py")):
            relative = path.relative_to(ROOT)
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))

            called = {
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else ""
                for node in ast.walk(tree) if isinstance(node, ast.Call)
            }
            assert not called & ambient, f"{relative} calls a clock"

            roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".")[0])
            assert not roots & forbidden_roots, (
                f"{relative} imports {sorted(roots & forbidden_roots)} — "
                f"a clock reaching the nightly pass would make drift a number "
                f"two builds reading one log disagree about"
            )

            assert "SystemClock" not in source, f"{relative} builds a clock"
            assert "__import__" not in source, f"{relative} imports dynamically"
            assert ".read()" not in source, f"{relative} reads a clock"


def test_tensions_are_identical_after_a_rebuild(tier_change_log):
    """Matrix: *replay*. A log of mints and transitions rebuilds identically."""
    store = tier_change_log
    before = dict(store.state().tensions)
    store.close()
    store.db_path.unlink()
    assert store.rebuild().tensions == before


def test_a_transition_survives_a_rebuild_with_its_pair_and_license(
    tier_change_log
):
    """The specific loss a replacing fold would produce: a tension that moved
    and came back with no sides — incomputable for ever, silently."""
    moved = tier_change_log.state().tensions["x_1"]
    assert moved[STATE] == "persistent"
    assert moved[BETWEEN] == ["b_1", "b_2"]
    assert moved["license"] == str(ladder.FLOOR)
    tier_change_log.close()
    tier_change_log.db_path.unlink()
    assert tier_change_log.rebuild().tensions["x_1"] == moved


def test_a_resolved_tension_survives_a_rebuild(tier_change_log):
    resolved = tier_change_log.state().tensions["x_3"]
    assert resolved[STATE] == "resolved"
    assert resolved[BETWEEN] == ["b_4", "b_5"]
    tier_change_log.close()
    tier_change_log.db_path.unlink()
    assert tier_change_log.rebuild().tensions["x_3"] == resolved


def test_nothing_in_the_tension_surface_stores_a_counter_for_a_pass_to_mutate():
    """Story 4 made salience *computed*, with a ninety-day half-life, and this
    story deliberately builds no decay. The way that regresses is a counter
    written onto a tension for the pass to increment — which is the AD-30
    violation story 4 avoided, arriving one object over.

    So: nothing in the surface names salience at all, and no record field it
    composes is a count.
    """
    counters = {"salience", "decay", "score", "weight", "count", "counter",
                "seen", "hits", "velocity", "drift_score"}
    offenders: list[str] = []
    for label, tree in _guarded_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if (isinstance(key, ast.Constant)
                            and str(key.value) in counters):
                        offenders.append(f"{label}:{key.lineno}")
    assert not offenders, f"a stored counter reached a tension record: {offenders}"

    imported = set()
    for area in SURFACE:
        for path in sorted((ROOT / area).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                elif isinstance(node, ast.Import):
                    imported.update(a.name for a in node.names)
    assert not {m for m in imported if "salience" in m}, (
        "the tension surface reaches salience; decay is story 4's and is "
        "already computed"
    )


def test_salience_is_still_computed_and_still_decays():
    """The other half: the thing this story must not have touched still works.

    Pinned by value, because *"we did not change it"* is not something a diff
    proves a year later.
    """
    from half.retrieval import salience as sal

    assert sal.CORROBORATION_HALF_LIFE_DAYS == 90.0
    now = sal.parse_time("2026-08-01T00:00:00Z")
    fresh = sal.corroboration_weight("2026-08-01T00:00:00Z", now)
    half = sal.corroboration_weight("2026-05-03T00:00:00Z", now)
    assert half < fresh
    assert half == pytest.approx(fresh / 2, rel=0.05)


def test_no_tension_field_this_story_writes_is_ever_a_number(tensions):
    """Every value the pass can put in the log, checked as a value rather than
    as a name. A counter is a number, and there is exactly one field."""
    widening_log(tensions, moves=("b_1",))
    found = ledger.plan(ledger.read(tensions.state().tensions),
                        history=history(tensions), now=NOW)
    for fields in found.transitions.values():
        for value in fields.values():
            assert isinstance(value, str)


def test_the_pass_sees_no_claim_text(tensions):
    """The narrowing. A log read is every claim Half holds about the main, and
    what decides whether a disagreement is widening is how many *sources* an
    entry cites."""
    widening_log(tensions, moves=("b_1",))
    for row in history(tensions):
        assert set(row) <= set(HISTORY_VISIBLE)
        assert "claim" not in row and "subject" not in row
    text = repr(history(tensions))
    assert "mornings are for writing" not in text
    assert "no draft since May" not in text


# ═════════════════════════════════════════════════════════════════════════════
# matrix: metrics — velocity and closings are derivable, and not surfaced here
# ═════════════════════════════════════════════════════════════════════════════


def test_drift_and_loop_advancement_are_derivable_from_what_is_recorded(
    tensions
):
    """*Drift is tension velocity*; *loop advancement is tensions closing*
    (glossary). Neither surface is built here — this asserts the arithmetic is
    available from the fold alone, which is what the story owes story 10."""
    widening_log(tensions, moves=("b_1",))
    tensions.record(Op.TENSION, "x_1", NOW, **{STATE: "widening"})
    entry(tensions, "b_3", "2026-08-01T00:00:00Z", support=["s_3"])
    mint(tensions, "x_2", MINTED, between=["b_2", "b_3"])
    tensions.record(Op.TENSION, "x_2", NOW, **{STATE: "closing"})

    found = ledger.read(tensions.state().tensions)
    widening_now = [t for t in found.values() if t.state == "widening"]
    closing_now = [t for t in found.values() if t.state == "closing"]
    assert len(widening_now) == 1 and len(closing_now) == 1

    # And the *velocity*: the log carries a stamp per transition, so how fast
    # tensions are widening is countable over any window without a new field.
    moves = [r for r in tensions.log
             if r.op is Op.TENSION and r.data.get(STATE) == "widening"]
    assert [r.t for r in moves] == [NOW]


def test_when_a_tension_resolved_is_derivable_from_the_log(tensions):
    """The metric the story owes story 10, on the half that is not a
    transition.

    No `resolved` record is ever appended: the fold computes it the moment a
    correction lands, and a second writer of it would be a second place for the
    log and the fold to disagree. So *when* a tension resolved is recovered the
    same way *whether* is — the first correction or expunge naming either side —
    which is arithmetic over the log with no new field. This is the case the
    existing derivability check does not make: it hand-writes its transitions
    and resolves nothing.
    """
    widening_log(tensions, moves=())
    entry(tensions, "b_3", at_days(3), support=["s_3"])
    mint(tensions, "x_2", MINTED, between=["b_2", "b_3"])
    tensions.record(Op.RETRACT, "c_1", "2026-08-03T09:00:00Z", target="b_1")

    found = ledger.read(tensions.state().tensions)
    assert found["x_1"].state == "resolved" and found["x_2"].state == "fresh"

    closed = {
        ident: min(
            record.t for record in tensions.log
            if record.op in (Op.RETRACT, Op.REVISE, Op.EXPUNGE)
            and tension.names(record.data.get("target"))
        )
        for ident, tension in found.items()
        if tension.state == "resolved"
    }
    assert closed == {"x_1": "2026-08-03T09:00:00Z"}


def test_velocity_counts_the_shape_changes_the_pass_actually_appends(tensions):
    """*Drift is tension velocity*, over records the pass wrote rather than
    records a test wrote — and the trade stated rather than assumed.

    A tension that keeps widening appends **one** ``widening`` record, not one a
    night: ``transition`` refuses a move to the state already held, because a
    record that changes nothing is a record that says something happened and
    this runs every night for years. So what the log supports is *how often a
    disagreement changed shape*, over any window — which is what a velocity is.
    *How long it has been widening* is a question about the state, and the state
    answers it.
    """
    widening_log(tensions, moves=("b_1",))
    work = ledger.read(tensions.state().tensions)
    first = ledger.plan(work, history=history(tensions), now=NOW)
    assert first.transitions == {"x_1": {STATE: "widening"}}
    tensions.record(Op.TENSION, "x_1", NOW, **first.transitions["x_1"])

    # More evidence on the same side, a week later: still widening, and the log
    # says so once.
    entry(tensions, "b_1", at_days(-6, since=NOW),
          support=["s_1", "s_new_b_1", "s_newer"])
    later = at_days(-7, since=NOW)
    second = ledger.plan(ledger.read(tensions.state().tensions),
                         history=history(tensions), now=later)
    assert second.transitions == {} and second.unchanged == ("x_1",)

    changes = [r.t for r in tensions.log
               if r.op is Op.TENSION and r.data.get(STATE) == "widening"]
    assert changes == [NOW], "one shape change, one record"


def test_the_corrective_path_for_a_wrong_mint_is_erase_and_mint_again(tensions):
    """The trade the merge buys, written down as a case.

    Merging rather than replacing is what keeps a transition from dropping the
    pair and the license the mint recorded — a tension that lost its two sides
    the first night the pass moved it, with replay reproducing the loss. The
    price is that no append can ever take a field *off* a tension. The
    corrective path is the one the main already has, and it is the one an
    append-only log has: erase the record and state it again.
    """
    entry(tensions, "b_1", at_days(2), support=["s_1"])
    entry(tensions, "b_2", at_days(2), support=["s_2"])
    entry(tensions, "b_3", at_days(2), support=["s_3"])
    mint(tensions, "x_1", MINTED, between=["b_1", "b_2"])

    # A later record can overwrite a field. It cannot remove one.
    tensions.record(Op.TENSION, "x_1", NOW, model_tier="frontier")
    assert tensions.state().tensions["x_1"]["model_tier"] == "frontier"
    tensions.record(Op.TENSION, "x_1", NOW, **{STATE: "widening"})
    assert "model_tier" in tensions.state().tensions["x_1"]

    tensions.expunge("x_1", t=at_days(-1, since=NOW))
    mint(tensions, "x_2", at_days(-2, since=NOW), between=["b_1", "b_3"])

    found = tensions.state().tensions
    assert "x_1" not in found
    assert found["x_2"][BETWEEN] == ["b_1", "b_3"]
    assert "model_tier" not in found["x_2"]


def test_nothing_in_the_tension_surface_reports_to_the_main():
    """No metric surface, no unprompted message — story 10's, and a pass that
    sent anything would be doing it at three in the morning."""
    banned = {"send", "notify", "surface", "message", "draft_link", "reply"}
    offenders: list[str] = []
    for label, tree in _guarded_trees():
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in banned):
                offenders.append(f"{label}:{node.lineno}")
    assert not offenders, f"the nightly pass contacts somebody: {offenders}"


# ═════════════════════════════════════════════════════════════════════════════
# the cases a collection floor cannot protect, named one by one
# ═════════════════════════════════════════════════════════════════════════════


def _cases_defined_here() -> set[str]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


@pytest.mark.cap7_resolution
def test_every_resolution_case_this_story_rests_on_still_exists():
    required = {
        "test_a_correction_to_either_side_resolves_the_tension_and_keeps_it",
        "test_expunging_one_side_resolves_the_tension_and_keeps_it",
        "test_the_resolution_is_the_deliberate_inverse_of_the_loop_firewall",
        "test_retract_and_revise_resolve_a_tension_identically",
        "test_a_resolved_tension_is_never_re_evaluated",
        "test_nothing_can_move_a_tension_to_resolved_by_hand",
        "test_no_module_in_the_tension_surface_offers_a_way_to_resolve_one",
        "test_a_later_append_cannot_move_a_resolved_tension_out_of_it",
        "test_terminality_pins_the_state_and_not_the_whole_record",
        "test_a_resolved_state_is_refused_before_the_record_is_durable",
        "test_a_log_that_already_carries_resolved_still_folds",
        "test_a_resolved_state_read_off_the_log_is_terminal_too",
        "test_a_tension_minted_over_a_gone_side_is_not_live",
        "test_a_tension_minted_over_an_expunged_side_is_not_live",
        "test_an_entry_that_never_existed_is_not_an_entry_that_left",
        "test_the_pass_never_computes_drift_across_an_entry_that_is_gone",
    }
    missing = required - _cases_defined_here()
    assert not missing, (
        f"a resolution case was deleted: {sorted(missing)}. A floor on the "
        f"suite cannot protect these — each carries a whole property"
    )


@pytest.mark.cap7_neutrality
def test_every_neutrality_guard_this_story_rests_on_still_exists():
    required = {
        "test_a_tension_record_naming_a_ranked_side_is_refused_at_the_append",
        "test_the_ranked_field_gate_covers_every_way_a_record_is_built",
        "test_the_computation_is_symmetric_under_swapping_the_two_sides",
        "test_the_symmetry_check_catches_a_computation_that_prefers_a_side",
        "test_nothing_in_the_tension_surface_reads_the_pair_positionally",
        "test_the_positional_scan_catches_every_way_a_side_is_chosen",
        "test_no_name_in_the_tension_surface_comes_from_the_ranking_vocabulary",
        "test_the_ranking_name_scan_catches_every_way_one_arrives",
        "test_no_function_in_the_tension_surface_returns_one_of_the_two_sides",
        "test_the_resolution_records_nothing_about_which_side_went",
        "test_a_transition_carries_exactly_one_field_and_it_is_the_state",
        "test_nothing_in_the_tension_surface_stores_a_counter_for_a_pass_to_mutate",
        "test_salience_is_still_computed_and_still_decays",
        "test_a_ranked_side_is_refused_under_any_spelling",
        "test_every_exact_spelling_in_the_denylist_still_fails_the_predicate",
        "test_the_ranking_predicate_leaves_the_honest_names_alone",
        "test_the_ranking_vocabulary_is_pinned_by_value",
        "test_a_tension_record_may_carry_nothing_a_tension_is_not",
        "test_the_allowlist_still_admits_everything_a_tension_is",
        "test_the_guards_cover_the_tension_code_outside_the_two_packages",
        "test_the_scans_catch_a_ranking_written_into_the_fold",
        "test_the_name_scan_catches_a_ranked_function_the_package_merely_offers",
    }
    missing = required - _cases_defined_here()
    assert not missing, f"a neutrality guard was deleted: {sorted(missing)}"


def test_every_movement_case_this_story_rests_on_still_exists():
    """The cases review's mutations were red against, named one by one.

    Each carries a whole property that no arithmetic on a collection count can
    protect: that a tension which moved once can move again, that no threshold
    decides widening *at the layer that writes*, that a tension names its pair
    before it is durable, that a reason is a constant, and that the two metrics
    the story owes story 10 come out of what it records.
    """
    required = {
        "test_a_tension_goes_on_moving_after_its_first_transition",
        "test_no_threshold_decides_widening",
        "test_no_threshold_decides_widening_at_the_layer_that_writes",
        "test_a_tensions_first_record_must_name_the_two_entries_it_links",
        "test_every_reason_a_plan_gives_is_one_of_a_closed_set",
        "test_evidence_reads_the_log_in_stamp_order_not_append_order",
        "test_when_a_tension_resolved_is_derivable_from_the_log",
        "test_velocity_counts_the_shape_changes_the_pass_actually_appends",
        "test_the_corrective_path_for_a_wrong_mint_is_erase_and_mint_again",
        "test_a_tension_recorded_in_the_future_is_reported_rather_than_clamped",
    }
    missing = required - _cases_defined_here()
    assert not missing, (
        f"a movement case was deleted: {sorted(missing)}. Each was red against "
        f"a mutation that left the rest of the suite green"
    )
