"""CAP-7 story 9d: what a pass compares, and against what.

**The file that has to get *"never all-pairs"* right, and the way to get it
wrong is to count.** A fixture with ten beliefs and two changed produces the
same number whether the code compares 2×N or N², so a case asserting *"only
four comparisons"* over one fixture size asserts nothing about the rule. Story
11's review found this shape's mirror one capability over — a sweep asserting
``<= 1`` that passed at zero — and the lesson is the same: an assertion over one
point on a curve says nothing about the curve.

So the rule is asserted as a **derivative**. Double the ledger with entries that
neither sit on a loop nor share a subject, hold the candidate set and the two
comparison sets fixed, and the comparison count must not move — *and must not be
zero*, because a bound that compares nothing satisfies every inequality there
is. Both halves are in every growth case below.

Nothing here touches a store, a clock, a network or a model: every function
under test is pure, and every instant is a string the case chose.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from half.consolidate.candidates import (
    BOTH,
    CEILING,
    Couple,
    Entry,
    couples,
    fresh,
    key_of,
    on_a_loop,
    read,
    sharing_subject,
    watermark,
)

pytestmark = pytest.mark.cap7

ROOT = Path(__file__).resolve().parents[1]

#: Every stamp in this file is derived from these. Injected, never read.
BEFORE = "2026-08-01T00:00:00Z"
LAST_PASS = "2026-08-05T00:00:00Z"
AFTER = "2026-08-06T00:00:00Z"
NOW = "2026-08-07T00:00:00Z"


# ── helpers ──────────────────────────────────────────────────────────────────


def row(ident, *, at=AFTER, claim=None, subject="self", ledger="stated",
        loop=None):
    """One narrowed belief row, as ``records.mint_projection`` produces one."""
    found = {"id": ident, "t": at, "claim": claim or f"a claim from {ident}"}
    if subject is not None:
        found["subject"] = subject
    if ledger is not None:
        found["ledger"] = ledger
    if loop is not None:
        found["loop"] = loop
    return found


def table(*rows):
    return read({item["id"]: item for item in rows})


def since(*stamps, now=NOW):
    return watermark(stamps, now=now)


def names_of(found):
    """Every couple as an unordered pair of ids, so a case never reads an order."""
    return {frozenset(couple.names) for couple in found}


def filler(count, *, at=BEFORE, prefix="b_pad"):
    """Beliefs that share no subject with anybody and sit on no loop.

    The load-bearing fixture of this file: these are what the ledger is grown
    *with*, and each one carries its own subject so that nothing accidentally
    pairs it with anything. A version of this that left ``subject="self"`` on
    them would grow the subject set as fast as the ledger and every growth case
    below would fail — which is worth stating, because it is also the shape
    production data has today (see ``test_minting.py``).
    """
    return [
        row(f"{prefix}_{index}", at=at, subject=f"unrelated-{index}",
            ledger="revealed")
        for index in range(count)
    ]


def as_production_writes(count, *, at=AFTER, prefix="b_self"):
    """Beliefs shaped the way ``half/actor/runtime.py:700`` shapes them.

    **One subject, ``"self"``, on every one of them** — which is what the only
    production belief-subject writer sets, and therefore the ledger every real
    main has. ``filler`` above gives each padding belief its own subject, which
    is the single shape that keeps the subject set from growing; every growth
    case that pads with it is asserting a fact about the fixture as much as
    about ``couples``, and review found exactly that. So this is the companion:
    the same growth questions asked against the data Half actually writes,
    where the subject set *is* the ledger and only the ceiling bounds anything.

    Stamped ``AFTER`` rather than ``BEFORE``, because on real data these are
    also all candidates — the degenerate case is both comparison sets and the
    candidate set being the same whole ledger at once.
    """
    return [
        row(f"{prefix}_{index}", at=at, subject="self",
            ledger="revealed" if index % 2 else "stated")
        for index in range(count)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: new or changed — the candidate set
# ═════════════════════════════════════════════════════════════════════════════


def test_the_candidate_set_is_what_changed_since_the_last_pass():
    """Matrix: *the ordinary mint*, its first half."""
    known = table(row("b_old", at=BEFORE), row("b_new", at=AFTER))
    assert [item.id for item in fresh(known, since=since(LAST_PASS))] == ["b_new"]


def test_nothing_changed_produces_no_candidates_and_no_couples():
    """Matrix: *nothing changed*. No candidates, and therefore no judge calls
    and no mint — the whole of an ordinary night."""
    known = table(row("b_1", at=BEFORE), row("b_2", at=BEFORE))
    assert fresh(known, since=since(LAST_PASS)) == ()
    assert couples(known, since=since(LAST_PASS), loops=()).within == ()


def test_a_first_pass_with_no_watermark_treats_everything_as_new():
    """A main whose first pass this is has no previous marker, and *"nothing
    is new"* would be a Half that never minted anything for anybody, for ever,
    looking exactly like a quiet night."""
    known = table(row("b_1", at=BEFORE), row("b_2", at=BEFORE))
    assert since() is None
    assert len(fresh(known, since=None)) == 2


def test_the_watermark_is_the_previous_pass_and_not_this_one():
    """The scheduler writes a main's next due time *before* it runs their work,
    so the newest schedule stamp is this pass's own marker. Reading it would
    make every entry look older than the pass that is running."""
    assert since(BEFORE, LAST_PASS, NOW, now=NOW) == watermark(
        [LAST_PASS], now=NOW
    )
    known = table(row("b_1", at=AFTER))
    assert [item.id for item in fresh(known, since=since(BEFORE, LAST_PASS, NOW))] == [
        "b_1"
    ]


def test_an_entry_whose_stamp_cannot_be_read_is_not_a_candidate():
    """Between two wrong-looking answers, the one that stays bounded. Admitting
    it would put it in every pass's candidate set for ever, since nothing about
    it will ever come to parse."""
    known = table(row("b_bad", at="whenever"), row("b_ok", at=AFTER))
    assert [item.id for item in fresh(known, since=since(LAST_PASS))] == ["b_ok"]


def test_a_schedule_stamp_that_cannot_be_read_is_not_a_watermark():
    assert since("whenever", LAST_PASS) == watermark([LAST_PASS], now=NOW)
    assert since("whenever") is None


def test_a_now_this_build_cannot_read_makes_everything_new_and_not_nothing():
    """The failure direction, and it was the wrong one.

    With ``now`` unparseable, ``edge`` was ``None``, the guard that keeps this
    pass from reading *its own* marker was skipped, and the newest stamp of all
    — the marker the tick had just written — became the watermark. Nothing was
    ever new, and nothing said so.

    Between the two wrong answers, the one that re-derives what it already
    knows beats the one that silently mints nothing for ever; the couple
    ceiling is what makes it affordable.
    """
    assert watermark([BEFORE, LAST_PASS, NOW], now="whenever") is None
    assert watermark([BEFORE, LAST_PASS, NOW], now=None) is None
    assert watermark([BEFORE, LAST_PASS, NOW], now=7) is None

    known = table(row("b_1", at=BEFORE), row("b_2", at=LAST_PASS))
    assert len(fresh(known, since=watermark([NOW], now="whenever"))) == 2


def test_the_watermark_never_raises_on_a_view_this_build_cannot_read():
    """``read`` and ``mint.linked`` guard their argument and this did not, so
    a ``passes`` that was not a sequence cost a main their whole night rather
    than that one field."""
    for stamps in (None, 7, object()):
        assert watermark(stamps, now=NOW) is None


def test_an_entry_stamped_in_the_same_second_as_the_marker_is_a_candidate():
    """One second of a main's log, gone silently.

    A stamp carries whole seconds, so an entry written in the same second as
    the previous pass's marker compared equal to it and was never a candidate —
    not on that pass, which had not seen it, and not on any later one, which
    measures against a mark that has moved past it.

    The cost of the inclusive reading is that such an entry may be offered
    twice on two consecutive passes; a couple already carrying a live tension
    is recognised before the filter and before the judge, so that costs a
    filter pass at worst.
    """
    known = table(row("b_edge", at=LAST_PASS), row("b_older", at=BEFORE))
    offered = [item.id for item in fresh(known, since=since(LAST_PASS))]
    assert offered == ["b_edge"]


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the loop set and the subject set — and nothing else
# ═════════════════════════════════════════════════════════════════════════════


def test_a_changed_entry_is_compared_against_this_mains_loops():
    """Matrix: *loop set*. A wanting lives in the log as a belief carrying its
    loop, and a disagreement with one is mintable."""
    known = table(
        row("b_changed", at=AFTER, subject="paragliding"),
        row("b_wanting", at=BEFORE, subject="flying", loop="fly-more"),
    )
    found = couples(known, since=since(LAST_PASS), loops=("fly-more",)).within
    assert names_of(found) == {frozenset({"b_changed", "b_wanting"})}


def test_a_changed_entry_is_compared_against_beliefs_sharing_its_subject():
    """Matrix: *subject set*."""
    known = table(
        row("b_changed", at=AFTER, subject="farmland"),
        row("b_mate", at=BEFORE, subject="farmland"),
    )
    found = couples(known, since=since(LAST_PASS), loops=()).within
    assert names_of(found) == {frozenset({"b_changed", "b_mate"})}


@pytest.mark.cap7_minting
def test_a_changed_entry_is_never_compared_against_anything_else():
    """Matrix: *anything else*. The line that makes the bound a bound.

    One changed entry, one belief on a loop, one sharing its subject, and one
    that is neither. Three comparisons exist and one of them does not, and the
    absent one is named by id so a build that compared everything fails with the
    pair it should not have produced.
    """
    known = table(
        row("b_changed", at=AFTER, subject="farmland", ledger="stated"),
        row("b_loop", at=BEFORE, subject="flying", loop="fly-more"),
        row("b_subject", at=BEFORE, subject="farmland"),
        row("b_other", at=BEFORE, subject="knives"),
    )
    found = names_of(couples(known, since=since(LAST_PASS), loops=("fly-more",)).within)
    assert found == {
        frozenset({"b_changed", "b_loop"}),
        frozenset({"b_changed", "b_subject"}),
    }
    assert frozenset({"b_changed", "b_other"}) not in found


def test_a_loop_slug_this_main_does_not_hold_puts_nobody_in_the_loop_set():
    known = table(row("b_1", at=BEFORE, subject="a", loop="fly-more"))
    assert on_a_loop(known, loops=()) == ()
    assert on_a_loop(known, loops=("sell-the-flat",)) == ()
    assert [item.id for item in on_a_loop(known, loops=("fly-more",))] == ["b_1"]


def test_an_entry_with_no_subject_shares_one_with_nobody():
    """Not even with another entry that also has none. Two claims Half could not
    say what they were about are not two claims about the same thing, and
    treating absence as a shared value would make the subject set the whole
    ledger for every unlabelled belief in it."""
    known = table(
        row("b_1", at=AFTER, subject=None),
        row("b_2", at=BEFORE, subject=None),
    )
    assert sharing_subject(known, subject=None) == ()
    assert couples(known, since=since(LAST_PASS), loops=()).within == ()


def test_a_candidate_is_never_compared_with_itself():
    known = table(row("b_1", at=AFTER, subject="self"))
    assert couples(known, since=None, loops=()).within == ()


def test_one_pair_is_one_couple_however_many_ways_it_is_reached():
    """A pair reached through the loop set *and* the subject set, with both
    halves changed, is produced once. Four routes, one couple."""
    known = table(
        row("b_1", at=AFTER, subject="farmland", loop="buy-farmland"),
        row("b_2", at=AFTER, subject="farmland", loop="buy-farmland"),
    )
    found = couples(known, since=since(LAST_PASS), loops=("buy-farmland",)).within
    assert len(found) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: never all-pairs — asserted as growth, never as one fixture's count
# ═════════════════════════════════════════════════════════════════════════════


def grown(pad, *, loops=("buy-farmland",)):
    """The same candidate set and the same two comparison sets, in a ledger of
    ``pad`` unrelated beliefs on top."""
    known = table(
        row("b_changed", at=AFTER, subject="farmland", ledger="stated"),
        row("b_loop", at=BEFORE, subject="flying", loop="buy-farmland"),
        row("b_subject", at=BEFORE, subject="farmland", ledger="revealed"),
        *filler(pad),
    )
    return couples(known, since=since(LAST_PASS), loops=loops).within


@pytest.mark.cap7_minting
@pytest.mark.parametrize("pad", [0, 1, 8, 64, 256])
def test_doubling_the_ledger_does_not_move_the_comparison_count(pad):
    """**The acceptance criterion, asserted structurally.**

    *"Comparisons scale with the changed set, not the ledger."* The candidate
    set is one entry and the two comparison sets are one entry each at every
    size, so the count is two at every size or the code is comparing something
    it was never given a reason to compare.

    Asserted as an **equality against a fixture with no padding at all**, and
    the padded sizes sweep three orders of magnitude — so a build whose count
    grew with the ledger fails at 1 and a build whose count grew *slowly* fails
    at 256. The non-zero half is asserted too, because a bound that compares
    nothing satisfies every inequality there is.
    """
    assert len(grown(pad)) == len(grown(0)) == 2 > 0


@pytest.mark.cap7_minting
def test_the_growth_case_would_fail_against_an_all_pairs_comparison():
    """Non-vacuity for the case above: the numbers it asserts are numbers
    all-pairs could not produce.

    Without this, *"two at every size"* would be a fact about a fixture that
    happens to be small. At 256 the padded ledger holds 259 beliefs, so
    all-pairs is 33 411 comparisons and the bound produces two — and the case
    above is the difference between those, rather than an arithmetic identity.
    """
    known = table(
        row("b_changed", at=AFTER, subject="farmland"),
        row("b_loop", at=BEFORE, subject="flying", loop="buy-farmland"),
        row("b_subject", at=BEFORE, subject="farmland"),
        *filler(256),
    )
    total = len(known)
    assert total == 259
    assert len(grown(256)) == 2
    assert total * (total - 1) // 2 == 33_411


@pytest.mark.cap7_minting
def test_the_count_grows_with_the_comparison_sets_and_not_with_the_ledger():
    """The other side of the derivative, and the one a build that compared
    *nothing* would fail.

    Growing the **subject set** grows the count one for one — five mates is five
    comparisons — while growing the ledger around it changes nothing. A bound
    that had quietly stopped comparing would pass every case above and fail
    here at the first size.
    """
    for mates in (1, 2, 5):
        known = table(
            row("b_changed", at=AFTER, subject="farmland"),
            *[
                row(f"b_mate_{index}", at=BEFORE, subject="farmland")
                for index in range(mates)
            ],
            *filler(40),
        )
        assert len(couples(known, since=since(LAST_PASS), loops=()).within) == mates


@pytest.mark.cap7_minting
def test_the_count_grows_with_the_candidate_set_and_not_with_the_ledger():
    """And the third variable. Two changed entries against one comparison set
    is two couples; the ledger around them is irrelevant to both."""
    for changed in (1, 2, 4):
        known = table(
            *[
                row(f"b_new_{index}", at=AFTER, subject="farmland",
                    ledger="stated")
                for index in range(changed)
            ],
            row("b_mate", at=BEFORE, subject="farmland", ledger="revealed"),
            *filler(40),
        )
        # Every changed entry against the one mate, plus the changed entries
        # among themselves — which is the candidate set's own size, and never
        # the ledger's.
        found = couples(known, since=since(LAST_PASS), loops=()).within
        assert len(found) == changed + changed * (changed - 1) // 2


# ═════════════════════════════════════════════════════════════════════════════
# matrix: a first pass on real data — the ceiling, on the shape production writes
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
@pytest.mark.parametrize("size", [20, 40, 80, 200])
def test_the_ceiling_bounds_the_count_on_the_shape_production_writes(size):
    """Matrix: *a first pass on real data*. **Never all-pairs, in fact.**

    Every growth case above pads with ``filler``, which gives each padding
    belief its own subject — the one shape that keeps the subject set from
    growing. That makes those cases assertions about the fixture as much as
    about ``couples``, and it hid this: with ``since is None`` and every belief
    on ``subject="self"``, which is what the only production belief-subject
    writer sets, ``couples`` produced exactly ``n(n-1)/2``. Not *"scaling with
    the ledger"* — literally the complete pair set, 20 → 190, 40 → 780,
    80 → 3160, and 398k couples in 8.9s and 79MB at four thousand beliefs.

    So this asserts an **upper bound** rather than an equality, because on this
    shape there is no fixed number to assert: the count may be anything up to
    the ceiling and must never be past it.
    """
    known = table(*as_production_writes(size))
    assert len(known) == size
    found = couples(known, since=None, loops=())

    all_pairs = size * (size - 1) // 2
    assert len(found.within) <= CEILING
    assert len(found.within) == min(all_pairs, CEILING)
    assert found.ceiling_reached is (all_pairs > CEILING)


@pytest.mark.cap7_minting
def test_the_ceiling_case_would_fail_against_the_unbounded_bound():
    """Non-vacuity for the case above: at the largest size the unbounded code
    produced a number the ceiling forbids, so the assertion is a difference
    rather than an arithmetic identity."""
    assert 200 * 199 // 2 == 19_900 > CEILING
    # And the ceiling is not so loose that the sweep never reaches it: the
    # smallest size in it is under the ceiling and the largest is well over.
    assert 20 * 19 // 2 < CEILING < 200 * 199 // 2


@pytest.mark.cap7_minting
def test_the_ceiling_is_spent_before_it_is_exceeded_and_not_trimmed_after():
    """CAP-7's amended row: *spent before it is exceeded, like the judgement
    budget*.

    A build that produced the whole pair set and then sliced it would satisfy
    every count above while holding all 398k couples in memory first — which is
    the cost the ceiling exists to refuse, and the 79MB was held before any
    trimming could have run. Asserted the only way a pure function can be:
    with a ceiling of two over a ledger whose pair set is far larger, the
    couples returned are the first two the bound produced in the belief table's
    own order, which is only true of a build that stopped.
    """
    known = table(*as_production_writes(30))
    stopped = couples(known, since=None, loops=(), ceiling=2)
    whole = couples(known, since=None, loops=(), ceiling=CEILING)

    assert len(stopped.within) == 2 and stopped.ceiling_reached
    assert len(whole.within) == 435 and not whole.ceiling_reached
    assert [item.id for item in stopped.within] == [
        item.id for item in whole.within[:2]
    ]


@pytest.mark.cap7_minting
def test_a_pass_that_does_not_reach_the_ceiling_does_not_report_it():
    """Non-vacuity: a build that always said ``ceiling_reached`` would pass
    every case above. And ``reached`` is not ``exactly full`` — a bound with
    nothing further to offer has not reached anything."""
    known = table(*as_production_writes(4))
    assert not couples(known, since=None, loops=()).ceiling_reached
    # Six couples, a ceiling of six: full, and not reached, because nothing was
    # refused.
    exact = couples(known, since=None, loops=(), ceiling=6)
    assert len(exact.within) == 6 and not exact.ceiling_reached
    assert couples(known, since=None, loops=(), ceiling=5).ceiling_reached


@pytest.mark.cap7_minting
def test_the_ceiling_is_pinned_by_value():
    """Pinned the way ``JUDGEMENTS`` is: the number is a cost bound, so raising
    it is a red test and a deliberate edit rather than a quiet widening of
    every main's nightly arithmetic."""
    assert CEILING == 2048


@pytest.mark.cap7_minting
def test_the_ceiling_does_not_depend_on_either_comparison_set():
    """CAP-7's amended row says *independent of those sets*, and that is what
    makes it a real bound: a later fix to the degenerate subject set, or a
    widening of the loop set, must not be able to move it."""
    known = table(
        *as_production_writes(40),
        *[row(f"b_loop_{index}", at=AFTER, subject=f"own-{index}",
              loop="buy-farmland") for index in range(40)],
    )
    wide = couples(known, since=None, loops=("buy-farmland",), ceiling=100)
    narrow = couples(known, since=None, loops=(), ceiling=100)
    assert len(wide.within) == len(narrow.within) == 100
    assert wide.ceiling_reached and narrow.ceiling_reached


# ═════════════════════════════════════════════════════════════════════════════
# no winner: the couple, its id, and what neither of them offers
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
def test_a_couple_names_the_same_tension_whichever_way_round_it_is_built():
    """Matrix: *no winner*, at the one function every mint runs through.

    The id is derived by exclusive-or over the two digests rather than by
    sorting them, so order-independence is arithmetic. Asserted on ``key_of``
    directly and on a ``Couple`` built both ways, because the second is what the
    minting actually calls.
    """
    assert key_of("b_1", "b_2") == key_of("b_2", "b_1")
    one = Entry(id="b_1", at=AFTER)
    other = Entry(id="b_2", at=AFTER)
    assert Couple(both=(one, other)).id == Couple(both=(other, one)).id


@pytest.mark.cap7_minting
def test_the_derived_id_separates_pairs_and_looks_like_a_tension_id():
    """Distinct pairs get distinct ids, and the id follows the spine's identity
    convention (``x_<hex>``) so nothing downstream has to special-case it."""
    seen = {key_of(f"b_{i}", f"b_{j}")
            for i in range(20) for j in range(20) if i != j}
    assert len(seen) == 190
    for ident in seen:
        assert ident.startswith("x_") and len(ident) == 14
        assert all(char in "0123456789abcdef" for char in ident[2:])


@pytest.mark.cap7_minting
def test_the_couple_offers_no_way_to_ask_which_half_is_first():
    """A first and a second is one short step from a winner and a loser. There
    is no accessor for either half and no positional read anywhere in the
    package — the AST guard in ``tests/test_tensions.py`` covers the second, and
    this covers the surface."""
    public = {
        name for name in dir(Couple)
        if not name.startswith("_")
    }
    assert public == {"both", "id", "names"}
    # By AST rather than by text: this function's own docstring says the word
    # "sorted" four times, because saying what is forbidden is how the rule
    # survives — and a substring check would read the explanation as the
    # offence.
    body = ast.parse(inspect.getsource(key_of))
    chosen = [
        node.func.id for node in ast.walk(body)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert not {"sorted", "max", "min"} & set(chosen), chosen


def test_the_pair_is_two_and_the_module_says_so_once():
    """``BOTH`` and ``half.tensions.widening.SIDES`` are the same number about
    the same object, and two spellings of it is how a tension acquires a third
    side."""
    from half.tensions.widening import SIDES

    assert BOTH == SIDES == 2


# ═════════════════════════════════════════════════════════════════════════════
# the read is tolerant: one malformed record costs that belief, never the pass
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "rows",
    [None, "not a mapping", 7, {"": {"t": AFTER}}, {"  ": {"t": AFTER}}],
    ids=["none", "string", "number", "empty-key", "blank-key"],
)
def test_the_read_never_raises_and_drops_what_it_cannot_use(rows):
    assert read(rows) == {}


def test_a_field_of_the_wrong_type_is_dropped_rather_than_coerced():
    """``subject=7`` is not a subject, and inventing ``"7"`` would put that
    belief in a comparison set with everything else numbered seven."""
    known = read({"b_1": {"t": AFTER, "subject": 7, "claim": None, "loop": []}})
    assert known["b_1"].subject is None
    assert known["b_1"].claim == ""
    assert known["b_1"].loop is None


def test_a_row_that_is_not_a_mapping_keeps_the_belief_and_drops_the_fields():
    known = read({"b_1": "not a mapping"})
    assert known["b_1"] == Entry(id="b_1")


def test_a_non_string_key_is_coerced_rather_than_raising():
    """``half.tensions.ledger.read`` learned this from a table with one
    non-string key costing a main every tension they owned."""
    known = read({7: {"t": AFTER, "subject": "self"}})
    assert set(known) == {"7"}


def test_nothing_in_this_module_reads_a_clock_or_opens_a_store():
    """Pure by AST, because *"it does not today"* is a property that decays."""
    source = (ROOT / "half/consolidate/candidates.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            reached.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            reached.add(node.module)
    assert not {name for name in reached
                if name.split(".")[0] in {"time", "datetime", "random", "os"}}
    assert "Store" not in source
