"""CAP-7 story 9d: minting a tension — the bound, the budget, and the seam.

**Every case here runs offline against no model.** The disagreement judgement is
a port with no implementation in the tree and none wired into the composition
root, so what is under test is the thing CAP-7 actually specifies: *which* pairs
are compared, *against what*, through *which* filter, inside *which* budget. The
judge is a double, and its most important property is that it **counts its
calls** rather than raising when it should not be reached — a double that only
raised would be indistinguishable from one never called, because
``mint.consider`` catches per couple by design and turns a raise into a legal
outcome. That exact shape passed a whole story once in this tree
(``conftest.NeverGenerates`` records it), and it is the reason ``never`` below
is an assertion about a counter.

**The three verdicts are three assertions, not one.** *"Nothing was minted"* is
true when the judge said no, when the judge could not say, when the judge raised
and when there was no judge at all — so a suite that asserted only that would
pass with the port never reached. Each of the four has a case that names its own
field on the result, and one of them asserts the call counter is zero while the
others assert it is not.

**What the growth rule is asserted on here is the *cost*.** ``test_candidates``
asserts that the comparison count does not follow the ledger; this asserts that
the number of judgements *bought* does not either — which is the sentence CAP-7
actually writes, since the comparison is free and the judgement is not.
"""

from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.consolidate import candidates
from half.consolidate import relevance
from half.consolidate import mint as minting
from half.consolidate.candidates import Couple, Entry, MintView, key_of
from half.consolidate.pass_ import TensionPass
from half.consolidate.port import Disagreement
from half.errors import TensionError
from half.governance import ladder
from half.loops import ledger as loop_ledger
from half.schedule.clock import FrozenClock, moment, stamp
from half.schedule.tick import Scheduler
from half.store.ops import Op
from half.store.records import (
    NEXT_PASS_AT,
    PASS_RAN,
    TENSION_FIELDS,
    TOLD_ZONE,
    ZONE,
)
from half.store.store import Store
from half.tensions.states import STATE, TensionState
from half.tensions.widening import BETWEEN, RANKED_FIELDS

from tests.conftest import CLOSED, door_of, outward, reaches, seed_belief

pytestmark = pytest.mark.cap7

ROOT = Path(__file__).resolve().parents[1]

#: 2026-09-01T12:00:00Z — the instant ``tests/test_pass.py`` and
#: ``tests/test_schedule.py`` both build from, so the three files' scenarios
#: line up.
NOON = 1_788_264_000.0
NOW = moment(NOON)

#: A day before the pass: the marker the previous pass wrote.
LAST_PASS = NOON - 86_400
#: Before that: an entry that has not changed since.
SETTLED = stamp(NOON - 172_800)
#: After it: an entry that is new or changed.
STIRRED = stamp(NOON - 3_600)


# ── the judge doubles ────────────────────────────────────────────────────────


class Judge:
    """A deterministic judge that **counts what it was asked**.

    ``answers`` are used in order and the last repeats — ``GeneratorDouble``'s
    contract, one port over. ``True`` mints, ``False`` is *no*, ``None`` is
    *cannot say*, and a ``BaseException`` is raised.

    ``calls`` and ``asked`` are public and deliberately not callable: a case
    that needs to assert the port was never reached has to be able to ask.
    """

    def __init__(self, *answers) -> None:
        self._answers = list(answers) or [True]
        self._seen: list[frozenset[str]] = []

    async def disagree(self, one, other):
        self._seen.append(frozenset({one.id, other.id}))
        index = min(len(self._seen), len(self._answers)) - 1
        answer = self._answers[index]
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            return answer(one, other)
        return answer

    @property
    def calls(self) -> int:
        return len(self._seen)

    @property
    def asked(self) -> list[frozenset[str]]:
        return list(self._seen)


class Never(Judge):
    """A judge that must never be reached, **and counts the times it was**.

    Raising alone is not enough and this package proves it: ``mint.consider``
    catches per couple by design, so an ``AssertionError`` becomes an entry in
    ``skipped`` — a legal outcome — and a case asserting *"nothing was minted"*
    would pass whether or not the port had been paid for. The signal is the
    counter.
    """

    async def disagree(self, one, other):
        await super().disagree(one, other)
        raise AssertionError("a judgement was bought where none may be")


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    reg = ActorRegistry(tmp_path)
    yield reg
    reg.close()


def mark_pass(registry, main_id, at, *, ran=True):
    """A schedule record at ``at`` — the marker a pass writes before it runs.

    ``ran`` is the field that says whether this tick was running the main's
    *pass* or only moving their due time along. Spelled here rather than left
    to a default, because a fixture that wrote the marker without it is a
    fixture asserting the shape the scheduler writes for a **suspended** main
    while calling it the shape it writes for a pass — which is the defect this
    field exists to close, reintroduced in the test data.
    """
    asyncio.run(
        registry.note_pass(
            main_id, t=stamp(at),
            fields={NEXT_PASS_AT: stamp(at + 86_400), ZONE: "UTC",
                    TOLD_ZONE: False, PASS_RAN: ran},
        )
    )


def entry(store, ident, *, at=STIRRED, claim=None, subject="farmland",
          ledger="stated", loop=None):
    fields = {"subject": subject, "claim": claim or f"a claim from {ident}",
              "ledger": ledger}
    if loop is not None:
        fields["loop"] = loop
    return seed_belief(store, ident, at, **fields)


def the_mirror(store):
    """The canonical pair: a changed stated entry and a revealed one sharing
    its subject, sharing no words — which is what a mirror looks like."""
    entry(store, "b_said", at=STIRRED, ledger="stated",
          claim="means to buy the farmland this year")
    entry(store, "b_did", at=SETTLED, ledger="revealed",
          claim="has not opened a listing since March")


def seeded(registry, tmp_path, main_id="vidit", *, seed=the_mirror,
           marked=True):
    with Store(Path(tmp_path) / main_id) as store:
        seed(store)
    if marked:
        mark_pass(registry, main_id, LAST_PASS)
    return main_id


def due_now(registry, main_id):
    """A marker written at the last pass, falling due just before ``NOON``.

    The stamp on the record is what the watermark reads and the ``next_pass_at``
    inside it is what the scheduler reads, and they are deliberately different
    instants: a marker *written* at ``NOON`` would put this pass's own start
    ahead of every belief in the fixture, so nothing would be new and the case
    would pass for the wrong reason.
    """
    asyncio.run(registry.note_pass(
        main_id, t=stamp(LAST_PASS),
        fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC", TOLD_ZONE: False,
                PASS_RAN: True},
    ))


def run_pass(registry, main_id, *, judge, now=NOW):
    return asyncio.run(TensionPass(ledger=registry, judge=judge).evaluate(
        main_id, now
    ))


def tensions_of(registry, main_id):
    return registry.tension_table(main_id)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the ordinary mint
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
def test_a_changed_entry_and_a_revealed_one_that_disagree_become_a_tension(
    registry, tmp_path
):
    """Matrix: *the ordinary mint*. One tension, `fresh`, linking the two."""
    seeded(registry, tmp_path)
    judge = Judge(True)
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 1
    assert judge.asked == [frozenset({"b_said", "b_did"})]
    assert result.minted.minted == (key_of("b_said", "b_did"),)

    held = tensions_of(registry, "vidit")[key_of("b_said", "b_did")]
    assert held[STATE] == TensionState.FRESH.value
    assert set(held[BETWEEN]) == {"b_said", "b_did"}
    assert held["license"] == str(ladder.FLOOR)


@pytest.mark.cap7_minting
def test_a_minted_tension_carries_a_state_a_pair_and_a_license_and_no_more():
    """AD-22: no tension text, and nothing a tension is not. Asserted on the
    fields the mint composes, so a build that started writing a sentence about
    the disagreement fails here before it reaches a store."""
    couple = Couple(both=(Entry(id="b_1"), Entry(id="b_2")))
    fields = minting.fields_for(couple)
    assert set(fields) == {BETWEEN, STATE, "license"}
    assert set(fields) <= TENSION_FIELDS
    assert fields[STATE] == TensionState.FRESH.value
    assert not RANKED_FIELDS & set(fields)


@pytest.mark.cap7_minting
def test_the_mint_is_the_same_record_whichever_way_round_the_couple_is_built():
    """Matrix: *no winner*. ``between`` carries no order and no side is marked,
    and the tension's own id is the same either way — so there is nothing
    downstream that could come to depend on which arrived first."""
    one, other = Entry(id="b_said"), Entry(id="b_did")
    forward = minting.fields_for(Couple(both=(one, other)))
    backward = minting.fields_for(Couple(both=(other, one)))
    assert set(forward[BETWEEN]) == set(backward[BETWEEN])
    assert forward[STATE] == backward[STATE]
    assert Couple(both=(one, other)).id == Couple(both=(other, one)).id


def _mint_rows(*rows):
    """A belief table in the order given — which is the order ``couples``
    builds each pair in, and therefore which half lands in ``both[0]``."""
    return {
        ident: {"t": STIRRED, "claim": claim, "subject": "farmland",
                "ledger": ledger}
        for ident, claim, ledger in rows
    }


#: Four beliefs built so that **no two halves weigh the same**: ``b_said``
#: carries a term nothing else does and ``b_did`` carries only terms the rest
#: of the ledger repeats, so a couple of the two is 1.3219 + 0.3219 and a
#: positional read of it is one number or the other rather than the sum.
_SIDES = (
    ("b_said", "means to buy the farmland this year", "stated"),
    ("b_did", "listing march", "revealed"),
    ("b_flew", "the paraglider listing goes out every march", "stated"),
    ("b_grounded", "no flight plan listing filed in march", "revealed"),
)


@pytest.mark.cap7_minting
@pytest.mark.cap7_neutrality
def test_the_weight_and_the_order_are_the_same_whichever_way_a_couple_is_built():
    """Matrix: *no winner* — the behavioural half of the positional guard.

    The AST scan catches the *spelling*; this catches the *arithmetic*, and the
    two are not the same test. Review replaced ``filter.weight``'s body with
    ``return surprisal(couple.both[0], ...)`` — the pair read positionally, one
    side ranked over the other, in the function the budget's ordering runs
    through — and the whole suite stayed green, because the guard's vocabulary
    did not know the name ``both``.

    So: build the same ledger in two orders, which is the only thing that
    decides which half of a couple arrives first, and assert the weight and the
    whole priority order are identical. The two halves are asserted to have
    *different* surprisals first, because an equality between two numbers that
    were always going to match is the assertion-identical-either-way shape this
    project has shipped once.
    """
    counts, total = relevance.corpus(minting.read(_mint_rows(*_SIDES)))
    one = Entry(id="b_said", claim=_SIDES[0][1], ledger="stated")
    other = Entry(id="b_did", claim=_SIDES[1][1], ledger="revealed")

    # The fixture can fail: the two halves are not interchangeable.
    apart = {relevance.surprisal(item, counts=counts, total=total)
             for item in (one, other)}
    assert len(apart) == 2, "a couple whose halves weigh the same asserts nothing"

    forward = relevance.weight(Couple(both=(one, other)), counts=counts,
                               total=total)
    backward = relevance.weight(Couple(both=(other, one)), counts=counts,
                                total=total)
    assert forward == backward

    # And the order the budget spends in does not move either. The belief table
    # is reversed, so every couple is built the other way round.
    def order(rows):
        view = MintView(beliefs=_mint_rows(*rows))
        return [couple.id for couple in minting.slate(view, now=stamp(NOON)).within]

    assert order(_SIDES) == order(tuple(reversed(_SIDES)))
    assert len(order(_SIDES)) > 1, "one couple cannot have an order"


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the four ways nothing is minted, each asserted apart from the others
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
def test_a_judge_that_says_no_mints_nothing_and_the_pair_is_not_retried(
    registry, tmp_path
):
    """Matrix: *judge says no*. Named in ``passed`` — which is what tells this
    case apart from the three below it."""
    seeded(registry, tmp_path)
    judge = Judge(False)
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 1
    assert result.minted.minted == ()
    assert result.minted.passed == (key_of("b_said", "b_did"),)
    assert result.minted.unsaid == () and result.minted.skipped == ()
    assert tensions_of(registry, "vidit") == {}


@pytest.mark.cap7_minting
def test_a_judge_that_cannot_say_mints_nothing_and_is_counted_apart(
    registry, tmp_path
):
    """Matrix: *judge unavailable*, its wired-but-refusing half.

    ``None`` is *cannot say*. Kept apart from *no* deliberately: folded together
    they would be one assertion that passes whether the port answered or was
    never reached at all, which is the shape this project has shipped once.
    """
    seeded(registry, tmp_path)
    judge = Judge(None)
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 1
    assert result.minted.unsaid == (key_of("b_said", "b_did"),)
    assert result.minted.passed == ()
    assert tensions_of(registry, "vidit") == {}


@pytest.mark.cap7_minting
def test_no_port_wired_completes_the_pass_and_mints_nothing(
    registry, tmp_path
):
    """Matrix: *judge unavailable*, its no-port half — **and the state this
    build ships in**.

    The slate is still computed, so the bound, the filter and the budget run on
    every pass whether or not anybody can answer; nothing is consulted and
    nothing is minted, and the pass is not a failure.
    """
    seeded(registry, tmp_path)
    result = run_pass(registry, "vidit", judge=None)

    # The bound still ran — one couple was produced and the filter admitted it —
    # and nothing was bought and nothing was written. Asserted as three separate
    # numbers rather than as an empty result, because an empty result is also
    # what a build that stopped comparing altogether would hand back.
    assert result.minted.considered == 1
    assert result.minted.turned_away == 0
    assert result.minted.consulted == 0
    assert result.minted.minted == ()
    assert tensions_of(registry, "vidit") == {}

    # **And it says so as its own fact.** An unwired port used to be reported
    # in the budget's vocabulary and to read as ``quiet``, so the state this
    # build actually ships in was indistinguishable from a night with nothing
    # to mint.
    assert result.minted.unwired
    assert not result.minted.quiet
    assert not result.minted.budget_reached


@pytest.mark.cap7_minting
def test_a_judge_that_raises_costs_that_couple_and_never_the_pass(
    registry, tmp_path
):
    """Matrix: *judge raises*. That pair is skipped; the pass continues, and
    the *other* pair is still minted — which is what makes this isolation
    rather than a swallowed error."""
    def seed(store):
        the_mirror(store)
        entry(store, "b_flew", at=STIRRED, subject="flying", ledger="stated",
              claim="says the paraglider goes out every spring")
        entry(store, "b_grounded", at=SETTLED, subject="flying",
              ledger="revealed", claim="has not filed a flight plan in years")

    seeded(registry, tmp_path, seed=seed)
    judge = Judge(RuntimeError("the provider fell over"), True)
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 2
    assert len(result.minted.skipped) == 1
    assert len(result.minted.minted) == 1
    assert set(result.minted.skipped) & set(result.minted.minted) == set()
    assert len(tensions_of(registry, "vidit")) == 1


@pytest.mark.cap7_minting
def test_nothing_changed_since_the_last_pass_reaches_the_judge_at_all(
    registry, tmp_path
):
    """Matrix: *nothing changed*. No candidates, **no judge calls**, no mint.

    The judge is a ``Never``, so this asserts a counter at zero rather than the
    absence of an outcome — the outcome would be identical either way.
    """
    def seed(store):
        entry(store, "b_said", at=SETTLED, ledger="stated", claim="a plan")
        entry(store, "b_did", at=SETTLED, ledger="revealed", claim="a habit")

    seeded(registry, tmp_path, seed=seed)
    judge = Never()
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 0
    assert result.minted == minting.MintResult()
    assert tensions_of(registry, "vidit") == {}


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the cheap filter runs before the port, always
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
@pytest.mark.parametrize(
    "seed,why",
    [
        (
            lambda store: (
                entry(store, "b_said", at=STIRRED, ledger="revealed",
                      claim="rides to the office on a Tuesday"),
                entry(store, "b_did", at=SETTLED, ledger="revealed",
                      claim="has not opened a listing since March"),
            ),
            "same ledger",
        ),
        (
            lambda store: (
                entry(store, "b_said", at=STIRRED, ledger="stated",
                      claim="the mornings are for writing"),
                entry(store, "b_did", at=SETTLED, ledger="revealed",
                      claim="The Mornings Are For Writing"),
            ),
            "restating",
        ),
        (
            lambda store: (
                entry(store, "b_said", at=STIRRED, ledger="stated",
                      claim="means to buy the farmland this year"),
                entry(store, "b_did", at=SETTLED, ledger="revealed", claim=" "),
            ),
            "no claim to judge",
        ),
        (
            lambda store: (
                entry(store, "b_said", at=STIRRED, ledger="stated",
                      claim="means to buy the farmland this year"),
                entry(store, "b_did", at=SETTLED, ledger="revealed",
                      claim="!?.  ,,, --- ;"),
            ),
            "a claim with no words in it",
        ),
    ],
    ids=["same-ledger", "restating", "no-claim", "unreadable-claim"],
)
def test_a_pair_the_cheap_filter_rejects_never_reaches_the_judge(
    registry, tmp_path, seed, why
):
    """Matrix: *filter rejects*. **Asserted by a call counter at zero.**

    Four rules, one case each, and every one of them rejects a pair the
    comparison bound produced — a filter whose rejections were already made
    upstream would read as enforcement and assert nothing.
    """
    seeded(registry, tmp_path, seed=seed)
    judge = Never()
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 0, why
    assert result.minted.considered == 1
    assert result.minted.turned_away == 1
    assert result.minted.minted == ()


@pytest.mark.cap7_minting
def test_the_filter_admits_the_pair_the_capability_exists_for():
    """Non-vacuity: a filter that rejected everything would satisfy every case
    above. The canonical mirror — a stated intention and a revealed behaviour
    sharing no word at all — has to survive it."""
    couple = Couple(both=(
        Entry(id="b_said", claim="means to buy the farmland this year",
              subject="farmland", ledger="stated"),
        Entry(id="b_did", claim="has not opened a listing since March",
              subject="farmland", ledger="revealed"),
    ))
    assert relevance.admits(couple)


@pytest.mark.cap7_minting
def test_the_same_words_in_a_different_order_are_not_a_restatement(
    registry, tmp_path
):
    """Matrix: *filter rejects*, from the other side — and the defect it was
    written for.

    ``restating`` compared token **sets**, so ``"prefers Delhi over Goa"`` and
    ``"prefers Goa over Delhi"`` were one claim written twice and never reached
    the judge. That is not a duplicate: it is a contradiction, and it is the
    exact shape CAP-7 exists to catch, discarded by the cheap filter standing
    in front of the judgement. It is also the mirror image of the
    lexical-overlap trap loop 1 correctly rejected — two claims made of the
    same words are not the same claim.

    Asserted twice: on the filter, and end to end on a pass that mints, because
    a predicate can be right while nothing calls it.
    """
    mirrored = Couple(both=(
        Entry(id="b_said", claim="prefers Delhi over Goa", subject="travel",
              ledger="stated"),
        Entry(id="b_did", claim="prefers Goa over Delhi", subject="travel",
              ledger="revealed"),
    ))
    assert not relevance.restating(mirrored)
    assert relevance.admits(mirrored)

    # And a genuine restatement — the same words in the same order, differing
    # only in case — is still turned away, so this is not the rule deleted.
    repeated = Couple(both=(
        Entry(id="b_1", claim="the mornings are for writing", subject="work",
              ledger="stated"),
        Entry(id="b_2", claim="The Mornings Are For Writing", subject="work",
              ledger="revealed"),
    ))
    assert relevance.restating(repeated)

    def seed(store):
        entry(store, "b_said", at=STIRRED, subject="travel", ledger="stated",
              claim="prefers Delhi over Goa")
        entry(store, "b_did", at=SETTLED, subject="travel", ledger="revealed",
              claim="prefers Goa over Delhi")

    seeded(registry, tmp_path, seed=seed)
    judge = Judge(True)
    result = run_pass(registry, "vidit", judge=judge)
    assert judge.calls == 1
    assert result.minted.turned_away == 0
    assert result.minted.minted == (key_of("b_said", "b_did"),)


@pytest.mark.cap7_minting
def test_a_missing_ledger_on_either_side_is_admitted_rather_than_refused():
    """Unknown is not the same as same. Refusing a pair because Half failed to
    record where half of it came from would make a gap in the log into a gap in
    the mirror."""
    known = Entry(id="b_1", claim="means to buy farmland", ledger="stated")
    unknown = Entry(id="b_2", claim="opened no listing since March")
    assert relevance.crossing(Couple(both=(known, unknown)))
    assert relevance.crossing(Couple(both=(unknown, known)))


# ═════════════════════════════════════════════════════════════════════════════
# matrix: never all-pairs — asserted on what a pass *buys*
# ═════════════════════════════════════════════════════════════════════════════


def a_ledger_of(pad):
    """The canonical mirror, plus ``pad`` beliefs that are neither on a loop nor
    sharing a subject with anything."""
    def seed(store):
        the_mirror(store)
        for index in range(pad):
            entry(store, f"b_pad_{index}", at=STIRRED,
                  subject=f"unrelated-{index}",
                  ledger="revealed" if index % 2 else "stated",
                  claim=f"an unrelated observation number {index}")
    return seed


@pytest.mark.cap7_minting
@pytest.mark.parametrize("pad", [0, 1, 8, 40])
def test_the_judgements_bought_do_not_follow_the_ledger(registry, tmp_path, pad):
    """**The acceptance criterion, on the quantity that costs money.**

    The candidate set and the two comparison sets are held fixed while the
    ledger grows by a factor of twenty, and the number of judgements bought must
    not move — *and must not be zero*, because a pass that bought none satisfies
    every inequality there is. A build comparing all-pairs buys 861 at ``pad``
    of forty and one here.
    """
    seeded(registry, tmp_path, seed=a_ledger_of(pad))
    judge = Judge(False)
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 1 > 0
    assert result.minted.consulted == 1
    assert result.minted.considered == 1


@pytest.mark.cap7_minting
def test_the_growth_case_would_fail_against_an_all_pairs_pass(
    registry, tmp_path
):
    """Non-vacuity for the case above: the number it holds fixed is a number
    all-pairs could not produce at the largest size."""
    seeded(registry, tmp_path, seed=a_ledger_of(40))
    with Store(tmp_path / "vidit") as store:
        total = len(store.state().beliefs)
    assert total == 42
    assert total * (total - 1) // 2 == 861


def a_ledger_production_writes(size):
    """``size`` beliefs on ``subject="self"``, which is what every production
    belief carries and what neither growth fixture above has.

    ``a_ledger_of`` pads with one subject per padding belief — the single shape
    that keeps the subject set from growing — so it asserts a fact about the
    fixture as much as about the bound. This is the same question asked of the
    ledger Half actually writes.
    """
    def seed(store):
        for index in range(size):
            entry(store, f"b_self_{index}", at=STIRRED, subject="self",
                  ledger="revealed" if index % 2 else "stated",
                  claim=f"the {index}th thing this main has said or done")
    return seed


@pytest.mark.cap7_minting
@pytest.mark.parametrize("size", [16, 32, 64])
def test_the_pass_reports_an_upper_bound_on_what_it_compared(
    registry, tmp_path, size
):
    """Matrix: *a first pass on real data*. **Never all-pairs, in fact.**

    Every belief on one subject and no prior pass, which is the shape a real
    main's first pass has. The comparison count here is the complete pair set
    and always was; what is new is that it cannot pass the ceiling however far
    the ledger grows, and that the pass says which of the two bounds it hit.

    Asserted as an upper bound at every size — an equality would be a fact
    about the fixture, which is the defect this case was written for.
    """
    seeded(registry, tmp_path, seed=a_ledger_production_writes(size),
           marked=False)
    result = run_pass(registry, "vidit", judge=Judge(False))

    assert result.minted.considered <= candidates.CEILING
    assert result.minted.considered == min(size * (size - 1) // 2,
                                           candidates.CEILING)
    assert result.minted.consulted <= minting.JUDGEMENTS


@pytest.mark.cap7_minting
def test_the_minting_arithmetic_actually_leaves_the_event_loop(
    registry, tmp_path, monkeypatch
):
    """Matrix: *the loop is not stalled* (AD-9) — asserted by running it.

    ``tests/test_pass.py`` pins the ``to_thread`` call sites by AST, which
    catches the omission but certifies only that a line exists. This catches
    the thing the line is for: ``slate`` tokenises every claim in the ledger
    and sorts what survives — 1.64s of unyielding CPU for eight hundred beliefs
    on the subject shape production writes — and it ran synchronously in the
    coroutine while the re-evaluation beside it was already threaded. A
    coroutine that never yields cannot be cancelled by ``asyncio.wait_for``, so
    the tick's per-main bound looked healthy while the pass ran past it, in
    front of every main's inbound turn.

    So: record the thread ``slate`` ran on and assert it is not the loop's.
    """
    ran_on: list[str] = []
    real = minting.slate

    def watched(view, *, now):
        ran_on.append(threading.current_thread().name)
        return real(view, now=now)

    monkeypatch.setattr(minting, "slate", watched)

    seeded(registry, tmp_path)
    here = threading.current_thread().name
    result = run_pass(registry, "vidit", judge=Judge(True))

    assert len(ran_on) == 1, "the arithmetic ran a number of times other than once"
    assert ran_on[0] != here, (
        f"slate ran on {ran_on[0]!r}, the thread the event loop is on"
    )
    # And the pass still did its work — a threaded call that returned nothing
    # would satisfy the assertion above.
    assert result.minted.minted == (key_of("b_said", "b_did"),)


@pytest.mark.cap7_minting
def test_a_night_with_nothing_admitted_does_not_tokenise_the_whole_ledger(
    registry, tmp_path, monkeypatch
):
    """The other half: ``corpus`` walks every claim in the ledger, which is the
    most expensive thing ``slate`` does, and an ordinary night — nothing
    changed, nothing admitted — paid it in full to rank the empty list."""
    reached: list[object] = []
    real = relevance.corpus

    def watched(known):
        reached.append(known)
        return real(known)

    monkeypatch.setattr(relevance, "corpus", watched)

    def settled(store):
        entry(store, "b_settled", at=SETTLED, subject="farmland",
              ledger="stated")
        entry(store, "b_also", at=SETTLED, subject="farmland",
              ledger="revealed")

    seeded(registry, tmp_path, seed=settled)
    judge = Never()
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 0
    assert result.minted.considered == 0
    assert reached == [], "the whole ledger was tokenised for an empty queue"


@pytest.mark.cap7_minting
def test_a_pass_that_reaches_the_couple_ceiling_says_so(registry, tmp_path):
    """Matrix: *the cost is what is bounded*, and the amended row's *"a pass
    that reaches it says so"*.

    The ceiling is a separate fact from the budget: this pass reaches both, and
    the two are asserted apart, because a build that reported one for the other
    would make an unbounded comparison look like an ordinary full budget.
    """
    seeded(registry, tmp_path, seed=a_ledger_production_writes(80),
           marked=False)
    result = run_pass(registry, "vidit", judge=Judge(False))

    assert 80 * 79 // 2 == 3160 > candidates.CEILING
    assert result.minted.considered == candidates.CEILING
    assert result.minted.ceiling_reached
    assert result.minted.budget_reached
    assert result.minted.consulted == minting.JUDGEMENTS


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the budget — spent before it is exceeded
# ═════════════════════════════════════════════════════════════════════════════


def a_crowd(count):
    """``count`` mirror pairs on one subject, all of them changed. Every stated
    entry crosses with every revealed one, so the survivor count is well past
    any sane budget."""
    def seed(store):
        for index in range(count):
            entry(store, f"b_said_{index}", at=STIRRED, subject="self",
                  ledger="stated", claim=f"intends the {index}th thing")
            entry(store, f"b_did_{index}", at=STIRRED, subject="self",
                  ledger="revealed", claim=f"observed the {index}th habit")
    return seed


@pytest.mark.cap7_minting
def test_a_pass_that_would_exceed_its_bound_stops_minting_and_says_so(
    registry, tmp_path
):
    """Matrix: *budget reached*. **Never overspends**, and the saying-so is a
    field rather than a log line, so a case can assert it."""
    seeded(registry, tmp_path, seed=a_crowd(8))
    judge = Judge(False)
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == minting.JUDGEMENTS
    assert result.minted.consulted == minting.JUDGEMENTS
    assert result.minted.budget_reached
    assert result.minted.unbudgeted > 0

    # Sixteen beliefs, all of them on ``subject="self"`` and all of them
    # changed: 120 couples, which is 16·15/2 — the complete pair set. That was
    # the only assertion on this fixture and ``considered > JUDGEMENTS`` is
    # satisfied by all-pairs, so the shape the ceiling exists for was sitting
    # inside the budget's own case. Both halves now: what the bound produced,
    # and the bound on it.
    assert result.minted.considered == 120 == 16 * 15 // 2
    assert result.minted.considered <= candidates.CEILING
    assert not result.minted.ceiling_reached


@pytest.mark.cap7_minting
def test_the_bound_stops_the_minting_too_and_not_only_the_asking(
    registry, tmp_path
):
    """A budget that capped the consultations and then minted from a slate it
    had not paid for would be a bound on the wrong quantity."""
    seeded(registry, tmp_path, seed=a_crowd(8))
    result = run_pass(registry, "vidit", judge=Judge(True))

    assert len(result.minted.minted) == minting.JUDGEMENTS
    assert len(tensions_of(registry, "vidit")) == minting.JUDGEMENTS


@pytest.mark.cap7_minting
def test_the_couples_beyond_the_bound_are_dropped_and_the_pass_says_dropped(
    registry, tmp_path, caplog
):
    """Matrix: *beyond the budget* — *"reconsidered on a later pass, or
    reported as dropped, never silently discarded"*.

    It said one and did the other. ``mint.py`` logged *"%d couple(s) left for
    the next pass"* and there is no backlog: the next pass's watermark excludes
    the entries that produced them, so nothing reconsiders them ever. Verified
    here — pass one buys its whole budget with couples left over, pass two
    considers none of them, and neither ever will.

    CAP-7's matrix allows either answer and asks only that the pass say which
    one it gave. This build drops, so it says dropped; a backlog would be
    durable state this story does not add.
    """
    seeded(registry, tmp_path, seed=a_crowd(8))

    with caplog.at_level("INFO", logger="half.consolidate.mint"):
        first = run_pass(registry, "vidit", judge=Judge(False))
    assert first.minted.budget_reached and first.minted.unbudgeted > 0
    assert "dropped unjudged and not carried forward" in caplog.text
    assert "left for the next pass" not in caplog.text

    # The second pass, against the same log at a later instant with a marker
    # for the first. Nothing changed since, so nothing is reconsidered — which
    # is the fact the old log line denied.
    mark_pass(registry, "vidit", NOON, ran=True)
    second = run_pass(registry, "vidit", judge=Never(),
                      now=moment(NOON + 3_600))
    assert second.minted.considered == 0
    assert second.minted.unbudgeted == 0


@pytest.mark.cap7_minting
def test_a_judgement_that_raised_was_still_bought_and_is_still_billed(
    registry, tmp_path
):
    """The budget's meter read zero on the one night it mattered.

    ``consulted += 1`` sat after the ``except``/``continue``, so a provider
    failing every call reported ``consulted == 0`` having been asked — and
    billed — a full budget's worth of times. A bound whose own meter cannot see
    the spending is not a bound.

    Asserted on a judge that raises every time and counts its calls, so the
    number the port saw and the number the result reports are two independently
    measured quantities that have to agree.
    """
    seeded(registry, tmp_path, seed=a_crowd(8))
    judge = Judge(RuntimeError("the provider fell over"))
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == minting.JUDGEMENTS
    assert result.minted.consulted == minting.JUDGEMENTS
    assert len(result.minted.skipped) == minting.JUDGEMENTS
    assert result.minted.minted == ()


@pytest.mark.cap7_minting
def test_a_pass_inside_its_bound_does_not_report_the_bound(registry, tmp_path):
    """Non-vacuity: a build that always reported ``budget_reached`` would pass
    the case above."""
    seeded(registry, tmp_path)
    result = run_pass(registry, "vidit", judge=Judge(False))
    assert not result.minted.budget_reached and result.minted.unbudgeted == 0


@pytest.mark.cap7_minting
def test_the_budget_is_pinned_by_value():
    """Pinned the way ``PERSISTENCE_DAYS`` is, and for the same reason: the
    number is the free tier's arithmetic, so raising it is a red test and a
    deliberate edit rather than a quiet doubling of every main's nightly bill."""
    assert minting.JUDGEMENTS == 24


@pytest.mark.cap7_minting
def test_a_full_budget_takes_the_most_surprising_couples_first(registry, tmp_path):
    """honcho's surprisal, from counts and never from a model.

    One anomalous pair among a crowd of ordinary ones, with a budget's worth of
    ordinary pairs ahead of it in the ledger's own order. It has to be bought,
    which it can only be if the survivors were ordered by something other than
    the order they arrived in.
    """
    def seed(store):
        for index in range(minting.JUDGEMENTS):
            entry(store, f"b_said_{index}", at=STIRRED, subject="self",
                  ledger="stated",
                  claim="the ordinary thing everybody here says")
            entry(store, f"b_did_{index}", at=STIRRED, subject="self",
                  ledger="revealed",
                  claim="the ordinary thing everybody here does")
        entry(store, "b_odd_said", at=STIRRED, subject="self", ledger="stated",
              claim="कोंकणी शिकपाचें आसा")
        entry(store, "b_odd_did", at=STIRRED, subject="self", ledger="revealed",
              claim="ভাষা শেখার বই কেনেনি")

    seeded(registry, tmp_path, seed=seed)
    judge = Judge(False)
    run_pass(registry, "vidit", judge=judge)

    assert judge.calls == minting.JUDGEMENTS
    assert frozenset({"b_odd_said", "b_odd_did"}) in judge.asked


@pytest.mark.cap7_minting
def test_the_priority_is_deterministic_over_a_tie(registry, tmp_path):
    """*"The same log twice mints the same set"* has to survive the budget
    cutting the list, and a tie broken by iteration order would mint one tension
    tonight and its neighbour tomorrow from a log that had not changed."""
    seeded(registry, tmp_path, seed=a_crowd(8))
    first = Judge(False)
    run_pass(registry, "vidit", judge=first)
    second = Judge(False)
    run_pass(registry, "vidit", judge=second)
    assert first.asked == second.asked


@pytest.mark.cap7_minting
def test_the_surprisal_needs_no_model_and_is_computed_from_counts():
    """Rejected from the reference: its default tree computes
    ``dim * log(mean kNN distance)`` over embeddings a model produced, which
    would put a model in front of the filter. What was taken is `rptree`'s
    count-based ``-log p``."""
    known = {
        "b_common": Entry(id="b_common", claim="the ordinary thing"),
        "b_also": Entry(id="b_also", claim="the ordinary thing"),
        "b_third": Entry(id="b_third", claim="the ordinary thing"),
        "b_rare": Entry(id="b_rare", claim="a paraglider over Bir"),
    }
    counts, total = relevance.corpus(known)
    assert total == 4
    common = relevance.surprisal(known["b_common"], counts=counts, total=total)
    rare = relevance.surprisal(known["b_rare"], counts=counts, total=total)
    assert rare > common > 0


# ═════════════════════════════════════════════════════════════════════════════
# matrix: nothing is minted twice
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
def test_a_pair_already_carrying_a_live_tension_never_reaches_the_judge(
    registry, tmp_path
):
    """Matrix: *already linked*. Recognised before the filter and two steps
    before the port, so a standing disagreement costs nothing at all — asserted
    on the counter, because *"nothing minted"* is true either way."""
    def seed(store):
        the_mirror(store)
        store.record(Op.TENSION, "x_by_hand", stamp(NOON - 100_000),
                     between=["b_said", "b_did"],
                     **{STATE: TensionState.FRESH.value}, **ladder.admitted())

    seeded(registry, tmp_path, seed=seed)
    judge = Never()
    result = run_pass(registry, "vidit", judge=judge)

    assert judge.calls == 0
    assert result.minted.standing == (key_of("b_said", "b_did"),)
    assert set(tensions_of(registry, "vidit")) == {"x_by_hand"}


@pytest.mark.cap7_minting
def test_the_same_pass_twice_over_one_log_mints_the_same_set_once(
    registry, tmp_path
):
    """Matrix: *twice over one log*. **Replay-safe**, and by recognition rather
    than by a guard: the tension's id is derived from the pair, so the second
    pass reads the first pass's own record."""
    seeded(registry, tmp_path)
    work = TensionPass(ledger=registry, judge=Judge(True))

    first = asyncio.run(work.evaluate("vidit", NOW))
    after_one = dict(tensions_of(registry, "vidit"))
    second = asyncio.run(work.evaluate("vidit", NOW))
    after_two = dict(tensions_of(registry, "vidit"))

    assert first.minted.minted == (key_of("b_said", "b_did"),)
    assert second.minted.minted == ()
    assert second.minted.standing == (key_of("b_said", "b_did"),)
    assert after_two == after_one

    with Store(tmp_path / "vidit") as store:
        assert len([r for r in store.log if r.op is Op.TENSION]) == 1


@pytest.mark.cap7_minting
def test_a_third_and_fourth_pass_still_mint_nothing(registry, tmp_path):
    """The nightly pass runs every night for years. Once is not idempotent."""
    seeded(registry, tmp_path)
    work = TensionPass(ledger=registry, judge=Judge(True))
    for _ in range(4):
        asyncio.run(work.evaluate("vidit", NOW))
    with Store(tmp_path / "vidit") as store:
        assert len([r for r in store.log if r.op is Op.TENSION]) == 1


@pytest.mark.cap7_minting
def test_a_tension_the_main_erased_is_never_minted_again(registry, tmp_path):
    """An erasure has to stay an erasure. Without this the mint would look like
    it had landed — the append gate treats an expunged id as already seen — and
    be an erasure quietly undone."""
    seeded(registry, tmp_path)
    ident = key_of("b_said", "b_did")
    with Store(tmp_path / "vidit") as store:
        store.record(Op.TENSION, ident, stamp(NOON - 100_000),
                     between=["b_said", "b_did"],
                     **{STATE: TensionState.FRESH.value}, **ladder.admitted())
        store.expunge(ident, t=stamp(NOON - 90_000))
        assert ident in store.state().expunged

    judge = Never()
    result = run_pass(registry, "vidit", judge=judge)
    assert judge.calls == 0
    assert result.minted.minted == ()
    assert ident not in tensions_of(registry, "vidit")


@pytest.mark.cap7_minting
def test_the_mint_door_refuses_a_tension_the_log_already_holds(
    registry, tmp_path
):
    """The door's own half of *"nothing is minted twice"*, asserted directly:
    a second record arriving through the mint door would move a tension's stamp
    without moving its state, which is a silent widening reset that no test of
    the transition path could see."""
    seeded(registry, tmp_path)
    ident = key_of("b_said", "b_did")
    fields = minting.fields_for(Couple(both=(Entry(id="b_said"),
                                             Entry(id="b_did"))))
    asyncio.run(registry.note_mint("vidit", tension_id=ident,
                                   t=stamp(NOON), fields=fields))
    with pytest.raises(TensionError, match="already in this log"):
        asyncio.run(registry.note_mint("vidit", tension_id=ident,
                                       t=stamp(NOON + 10), fields=fields))


@pytest.mark.cap7_minting
def test_a_mint_carries_a_pair_a_fresh_state_and_the_ladders_floor(
    registry, tmp_path
):
    """``note_transition``'s sibling guard, which this door did not have.

    ``note_transition`` has refused stray fields since the review that found it
    appending whatever a caller handed it; ``note_mint``, added by the same
    story, refused nothing. Verified accepting ``state=persistent``, an
    arbitrary ``license``, ``known_to_main``, ``support`` and ``tombstone`` —
    every one of them allowed on a tension record by ``TENSION_FIELDS``, none
    of them composed by a mint, and all of them durable where no correction to
    either entry could take them back (AD-22).

    The state and the license are pinned as well as the field set. A mint that
    wrote ``persistent`` would hand 9c a tension whose widening clock had
    already run, and a license composed anywhere but the ladder is the thing
    story 5a says nobody may write.
    """
    seeded(registry, tmp_path)
    ident = key_of("b_said", "b_did")
    fields = minting.fields_for(Couple(both=(Entry(id="b_said"),
                                             Entry(id="b_did"))))
    assert set(fields) == {BETWEEN, STATE, "license"}

    for stray in ({"known_to_main": True}, {"support": ["s_1"]},
                  {"tombstone": True}, {"model_tier": "frontier"},
                  {"quarantined": True}, {"claim": "he never writes"}):
        with pytest.raises(TensionError, match="nothing else"):
            asyncio.run(registry.note_mint(
                "vidit", tension_id=ident, t=stamp(NOON),
                fields={**fields, **stray},
            ))

    for born in ("persistent", "widening", "closing", "resolved"):
        with pytest.raises(TensionError, match="born"):
            asyncio.run(registry.note_mint(
                "vidit", tension_id=ident, t=stamp(NOON),
                fields={**fields, STATE: born},
            ))

    with pytest.raises(TensionError, match="ladder"):
        asyncio.run(registry.note_mint(
            "vidit", tension_id=ident, t=stamp(NOON),
            fields={**fields, "license": "assert"},
        ))

    # Nothing landed, and the fields a mint really composes still do.
    assert tensions_of(registry, "vidit") == {}
    asyncio.run(registry.note_mint("vidit", tension_id=ident, t=stamp(NOON),
                                   fields=fields))
    assert set(tensions_of(registry, "vidit")) == {ident}


@pytest.mark.cap7_minting
def test_a_mint_that_the_store_refuses_costs_that_couple_and_nothing_else(
    registry, tmp_path
):
    """One failed write must not cost this main the rest of the night — and
    nothing was recorded, so the next pass computes the same answer again."""
    def seed(store):
        the_mirror(store)
        entry(store, "b_flew", at=STIRRED, subject="flying", ledger="stated",
              claim="says the paraglider goes out every spring")
        entry(store, "b_grounded", at=SETTLED, subject="flying",
              ledger="revealed", claim="has not filed a flight plan in years")

    seeded(registry, tmp_path, seed=seed)

    class OneWriteFails:
        def __init__(self, inner):
            self.inner = inner
            self.seen = 0

        async def mint_view(self, main_id):
            return await self.inner.mint_view(main_id)

        async def note_mint(self, main_id, **kwargs):
            self.seen += 1
            if self.seen == 1:
                raise OSError("disk full")
            return await self.inner.note_mint(main_id, **kwargs)

        async def tension_view(self, main_id):
            return await self.inner.tension_view(main_id)

        async def note_transition(self, main_id, **kwargs):
            return await self.inner.note_transition(main_id, **kwargs)

    result = asyncio.run(
        TensionPass(ledger=OneWriteFails(registry), judge=Judge(True))
        .evaluate("vidit", NOW)
    )
    assert len(result.minted.unrecorded) == 1
    assert len(result.minted.minted) == 1
    assert len(tensions_of(registry, "vidit")) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: the refutation firewall — the wanting stands (CAP-6)
# ═════════════════════════════════════════════════════════════════════════════


def with_a_loop(store):
    """A loop, the belief it is made of, and a revealed entry that disagrees."""
    store.record(
        Op.LOOP_TRANSITION, "l_1", SETTLED,
        **loop_ledger.opened("buy-farmland", state="advancing",
                             timescale="years", last_movement="2026-03-12",
                             loops=store.state().loops),
    )
    entry(store, "b_wanting", at=SETTLED, subject="farmland", ledger="stated",
          claim="means to buy the farmland this year", loop="buy-farmland")
    entry(store, "b_did", at=STIRRED, subject="farmland", ledger="revealed",
          claim="has not opened a listing since March")


@pytest.mark.cap7_minting
@pytest.mark.cap6_firewall
def test_a_tension_over_a_belief_supporting_a_loop_leaves_the_wanting_standing(
    registry, tmp_path
):
    """Matrix: *the wanting stands*. CAP-6, from the only side this story can
    breach it from.

    The loop is asserted **field by field** rather than by presence: story 8's
    own hole was a demotion that travelled through ``state.expunged`` while the
    loop stayed in the fold, which every case that only checked presence passed.
    """
    seeded(registry, tmp_path, seed=with_a_loop)
    with Store(tmp_path / "vidit") as store:
        before = dict(store.state().loops["buy-farmland"])

    result = run_pass(registry, "vidit", judge=Judge(True))
    assert len(result.minted.minted) == 1

    with Store(tmp_path / "vidit") as store:
        after = store.state()
        assert after.loops["buy-farmland"] == before
        assert "buy-farmland" not in after.expunged_loops
        assert "buy-farmland" not in after.expunged
        assert not [r for r in store.log if r.op is Op.LOOP_TRANSITION
                    and r.t > SETTLED]


@pytest.mark.cap7_minting
@pytest.mark.cap6_firewall
def test_a_changed_entry_is_compared_against_the_loop_set_through_the_pass(
    registry, tmp_path
):
    """Matrix: *loop set*, end to end. Non-vacuity for the case above: a build
    that never compared against a loop's entries would leave every wanting
    standing too."""
    seeded(registry, tmp_path, seed=with_a_loop)
    judge = Judge(True)
    run_pass(registry, "vidit", judge=judge)
    assert judge.asked == [frozenset({"b_wanting", "b_did"})]


@pytest.mark.cap7_minting
@pytest.mark.cap6_firewall
def test_nothing_in_the_consolidate_package_can_move_a_loop():
    """Structural, because absence is what story 8's hole looked like too.

    The only name this package takes from ``half.loops`` is the field a belief
    records its loop in, and no module here names the loop-transition op or any
    state in the loop vocabulary. A minter that acquired a reason to look at a
    loop is one line from acquiring a reason to move it.
    """
    from half.loops.states import LOOP_STATES

    taken: set[str] = set()
    named: list[str] = []
    for path in sorted((ROOT / "half/consolidate").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "half.loops"
            ):
                taken.update(alias.name for alias in node.names)
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name.startswith("half.loops") for alias in node.names
                ), path
            if (isinstance(node, ast.Attribute) and node.attr == "LOOP_TRANSITION"):
                named.append(f"{path.name}:{node.lineno}")
            if (isinstance(node, ast.Constant) and node not in docstrings
                    and node.value in LOOP_STATES):
                named.append(f"{path.name}:{node.lineno}")
    assert taken == {"LOOP"}, taken
    assert not named, named


# ═════════════════════════════════════════════════════════════════════════════
# matrix: crisis — the pass does not mint for a main in the mode
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
@pytest.mark.cap12
def test_a_main_in_crisis_mode_is_never_minted_for(registry, tmp_path):
    """Matrix: *crisis*. CAP-12 suspends Half's ordinary behaviour, and minting
    a tension about the gap between what somebody says and what they do is
    ordinary behaviour at its most ordinary.

    Enforced by the scheduler, which never puts a suspended main into the drain
    — asserted **through a real tick** rather than by a second check inside the
    pass, because a second enforcement path is a second place for the two to
    disagree. The judge counts, so the case fails if a consultation was bought.

    **The two mains carry different entries.** They used to carry the same
    ones, so ``judge.asked == [frozenset({"b_said", "b_did"})]`` — the central
    assertion — was satisfied by a consultation bought for *either* of them,
    including the suspended one. The pair the judge was asked about now names
    which main it belonged to.
    """
    for main_id in ("vidit", "asha"):
        def seed(store, who=main_id):
            entry(store, f"b_said_{who}", at=STIRRED, ledger="stated",
                  claim=f"means to buy the farmland this year, says {who}")
            entry(store, f"b_did_{who}", at=SETTLED, ledger="revealed",
                  claim=f"has not opened a listing since March, {who}")
        seeded(registry, tmp_path, main_id, seed=seed, marked=False)
        due_now(registry, main_id)
    asyncio.run(registry.suspend_for_crisis(
        "vidit", t=stamp(NOON - 100), tier="acute", score=3
    ))

    judge = Judge(True)
    result = asyncio.run(Scheduler(
        registry=registry, mains=("vidit", "asha"), root=Path(tmp_path),
        clock=FrozenClock(at=NOON),
        work=TensionPass(ledger=registry, judge=judge),
    ).tick())

    assert result.suspended == ("vidit",) and result.ran == ("asha",)
    # Named by main, so a consultation bought for the suspended one cannot
    # satisfy this.
    assert judge.asked == [frozenset({"b_said_asha", "b_did_asha"})]
    assert frozenset({"b_said_vidit", "b_did_vidit"}) not in judge.asked
    assert tensions_of(registry, "vidit") == {}
    assert set(tensions_of(registry, "asha")) == {
        key_of("b_said_asha", "b_did_asha")
    }


@pytest.mark.cap7_minting
@pytest.mark.cap12
def test_a_main_who_was_suspended_still_has_everything_they_said_meanwhile(
    registry, tmp_path
):
    """Matrix: *a suspended main resumes*. **Never silently excluded.**

    The scheduler advances the due time of every main whose window has passed
    — the unscheduled, the missed and the **suspended** ones as well as the one
    whose pass is about to run — and it wrote one indistinguishable ``schedule``
    record for all four. So ``watermark`` answered *"when did the scheduler
    last touch this main"*, and a main crisis-suspended for one night resumed
    with everything they had said that night already behind the mark. Not for a
    night: for ever, because the mark only ever moves forward. Verified end to
    end at ``considered == 0``.

    Three markers here, in the shapes the scheduler actually writes: a real
    pass two nights ago, the suspended night's advance last night, and this
    tick. What the main said in between has to survive both of the later two.
    """
    real_pass = NOON - 2 * 86_400
    spoken = stamp(NOON - 100_000)

    def said_between_the_two(store):
        entry(store, "b_said", at=spoken, ledger="stated",
              claim="means to buy the farmland this year")
        entry(store, "b_did", at=spoken, ledger="revealed",
              claim="has not opened a listing since March")

    seeded(registry, tmp_path, seed=said_between_the_two, marked=False)
    # A pass that really ran, before the main said either thing.
    mark_pass(registry, "vidit", real_pass, ran=True)
    # Last night: crisis-suspended, so the scheduler advanced the due time and
    # ran nothing. This is the record that used to become the watermark.
    asyncio.run(registry.note_pass(
        "vidit", t=stamp(NOON - 86_400),
        fields={NEXT_PASS_AT: stamp(NOON - 60), ZONE: "UTC", TOLD_ZONE: False,
                PASS_RAN: False},
    ))

    # The defect, named: read against *every* schedule stamp — which is what
    # the minter used to be handed — nothing this main said is new.
    view = asyncio.run(registry.mint_view("vidit"))
    every_stamp = (stamp(real_pass), stamp(NOON - 86_400))
    poisoned = candidates.watermark(every_stamp, now=NOW.stamp)
    assert poisoned is not None
    assert candidates.fresh(candidates.read(view.beliefs), since=poisoned) == ()

    judge = Judge(True)
    result = asyncio.run(Scheduler(
        registry=registry, mains=("vidit",), root=Path(tmp_path),
        clock=FrozenClock(at=NOON),
        work=TensionPass(ledger=registry, judge=judge),
    ).tick())

    assert result.ran == ("vidit",) and result.suspended == ()
    assert judge.asked == [frozenset({"b_said", "b_did"})]
    assert len(tensions_of(registry, "vidit")) == 1


@pytest.mark.cap7_minting
def test_a_main_whose_first_pass_this_is_still_treats_everything_as_new(
    registry, tmp_path
):
    """The documented ``None`` — *"everything is new, for a main whose first
    pass this is"* — was unreachable, because the tick that finds a main
    unscheduled writes a marker before their first pass ever runs.

    So the first pass read that marker as a previous pass and found nothing
    new: a main who joined and said things had no tension minted for them until
    they said something else, and Half could not tell that from a quiet night.
    """
    seeded(registry, tmp_path, marked=False)
    # The marker an unscheduled tick writes: a due time, and no pass.
    mark_pass(registry, "vidit", LAST_PASS, ran=False)

    view = asyncio.run(registry.mint_view("vidit"))
    assert view.passes == ()
    assert candidates.watermark(view.passes, now=NOW.stamp) is None

    judge = Judge(True)
    result = run_pass(registry, "vidit", judge=judge)
    assert judge.calls == 1
    assert result.minted.considered == 1
    assert len(tensions_of(registry, "vidit")) == 1


# ═════════════════════════════════════════════════════════════════════════════
# matrix: replay, and the clock nothing here reads
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
def test_a_minted_tension_folds_identically_after_a_rebuild(registry, tmp_path):
    """Matrix: *replay* (AD-4, AD-30). A mint that did not survive a rebuild is
    a disagreement Half records and then loses.

    **Anchored on a tension that exists**, the way
    ``test_the_shipped_wiring_runs_a_real_pass_and_mints_nothing`` already is.
    This compared two tension tables without asserting either held anything, so
    it read ``{} == {}`` and passed on a build that minted nothing: review
    replaced the ``note_mint`` call with ``fields_for(couple)``, reddened ten
    cases in this file, and left this one green.
    """
    seeded(registry, tmp_path)
    result = run_pass(registry, "vidit", judge=Judge(True))
    ident = key_of("b_said", "b_did")
    assert result.minted.minted == (ident,)

    with Store(tmp_path / "vidit") as store:
        held = store.state().tensions
        assert set(held) == {ident}
        assert store.rebuild().tensions == held
        assert store.fold().tensions == held


@pytest.mark.cap7_minting
def test_the_mint_stamps_the_instant_the_tick_was_given(registry, tmp_path):
    """AD-30 at the seam that matters: the minter reads no clock, so the record
    carries the instant the tick read once, to the second."""
    seeded(registry, tmp_path)
    chosen = moment(NOON + 12_345)
    run_pass(registry, "vidit", judge=Judge(True), now=chosen)
    held = tensions_of(registry, "vidit")[key_of("b_said", "b_did")]
    assert held["t"] == chosen.stamp


@pytest.mark.cap7_minting
def test_two_mains_with_identical_logs_reach_identical_tensions(
    registry, tmp_path
):
    """The same log and the same ``now`` produce the same tensions, id included
    — which is what makes the derived id a replay property rather than a
    convenience.

    **Anchored on a tension that exists.** This compared two tables without
    asserting either held anything, so it read ``{} == {}`` and passed on a
    build that minted nothing at all.
    """
    for main_id in ("vidit", "asha"):
        seeded(registry, tmp_path, main_id)
    work = TensionPass(ledger=registry, judge=Judge(True))
    one = asyncio.run(work.evaluate("vidit", NOW))
    other = asyncio.run(work.evaluate("asha", NOW))

    ident = key_of("b_said", "b_did")
    assert one.minted.minted == other.minted.minted == (ident,)
    assert set(tensions_of(registry, "vidit")) == {ident}
    assert tensions_of(registry, "vidit") == tensions_of(registry, "asha")


@pytest.mark.cap7_minting
def test_a_minted_tension_is_evaluated_by_the_same_pass_that_minted_it(
    registry, tmp_path
):
    """The order of the two halves: mint first, then re-evaluate, so a tension
    born tonight gets its first state tonight rather than waiting a day.

    A `fresh` tension at zero elapsed time is 9c's ordinary starting case, so it
    is reported *unchanged* rather than moved — which is the assertion that
    proves the re-evaluation saw it at all.
    """
    seeded(registry, tmp_path)
    result = run_pass(registry, "vidit", judge=Judge(True))
    ident = key_of("b_said", "b_did")
    assert result.minted.minted == (ident,)
    assert ident in result.unchanged
    assert result.moved == {}


# ═════════════════════════════════════════════════════════════════════════════
# the seam: narrow by construction, and reaching nothing
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap7_minting
def test_the_judgement_port_offers_exactly_one_method():
    """*"Narrow by construction."* A port that grew a second method would be a
    port a judge could store through, generate through, or read a clock
    through."""
    assert door_of(Disagreement) == {"disagree"}
    assert door_of(minting.Mints) == {"note_mint"}


@pytest.mark.cap7_minting
def test_no_implementation_of_the_judgement_lives_in_the_package():
    """A judge in ``half/`` would be a production judge the moment somebody
    wired it, and it would answer nothing truthfully. The seam ships; 9e or the
    extraction supplies the judgement."""
    offenders: list[str] = []
    for path in sorted((ROOT / "half").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "disagree"
                    and path != ROOT / "half/consolidate/port.py"):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, offenders


@pytest.mark.cap7_minting
def test_the_shipped_wiring_holds_the_pass_and_wires_no_judge(tmp_path):
    """Asserted by value rather than by keyword — story 6d's identical claim was
    satisfied by a case asserting a keyword's *name* appeared in the source,
    which passed with the value set to ``None``."""
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load
    from half.surface.morning import MorningPass

    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    try:
        work = wiring.scheduler.work
        assert isinstance(work, MorningPass)
        assert isinstance(work.consolidate, TensionPass)
        assert work.consolidate.judge is None
    finally:
        wiring.registry.close()


@pytest.mark.cap7_minting
def test_the_shipped_wiring_runs_a_real_pass_and_mints_nothing(tmp_path):
    """Run, not grepped: the object graph the product builds, a real store, a
    real tick, and no tension in a real log.

    **And the fixture is proved mintable afterwards**, which is what stops this
    from being an assertion that is true either way. A store with nothing to
    mint would satisfy *"the log gains no tension"* exactly as well as a wiring
    that declined to mint, so the same log is run again through the same
    registry with a judge in the room and has to produce one.
    """
    from half.__main__ import build
    from half.config import MAINS_ENV, ROOT_ENV, load

    with Store(Path(tmp_path) / "vidit") as store:
        the_mirror(store)
    config = load({ROOT_ENV: str(tmp_path), MAINS_ENV: "123:vidit"})
    wiring = build(config, token="123:fake")
    try:
        due_now(wiring.registry, "vidit")
        wiring.scheduler.clock = FrozenClock(at=NOON)
        result = asyncio.run(wiring.scheduler.tick())
        assert result.ran == ("vidit",)
        assert wiring.registry.tension_table("vidit") == {}

        judge = Judge(True)
        asyncio.run(TensionPass(ledger=wiring.registry, judge=judge)
                    .evaluate("vidit", NOW))
        assert judge.calls == 1
        assert len(wiring.registry.tension_table("vidit")) == 1
    finally:
        wiring.registry.close()


# ═════════════════════════════════════════════════════════════════════════════
# the package boundary — swept by the rule the other four packages are swept by
# ═════════════════════════════════════════════════════════════════════════════


def _modules():
    return sorted((ROOT / "half/consolidate").rglob("*.py"))


@pytest.mark.cap7_minting
def test_nothing_in_the_package_reaches_a_store_or_an_actor():
    """AD-1: the single writer. Every append goes through the injected door, and
    a module here with its own path to a main's log would be a second writer.

    Swept with ``conftest.CLOSED`` — the same dotted-root predicate
    ``half/trust``, ``half/questions``, ``half/correction`` and ``half/voice``
    are swept by — rather than a fifth denylist of import spellings, because
    every denylist this codebase has shipped was walked around.
    """
    offenders = {
        str(path.relative_to(ROOT)): found
        for path in _modules() if (found := reaches(path, CLOSED))
    }
    assert not offenders, offenders


@pytest.mark.cap7_minting
def test_nothing_in_the_package_reaches_a_model_a_channel_or_the_network():
    """*"No model call in this story, and no provider wired."*

    ``outward`` derives what this package may not reach from the one list of
    forbidden roots in the tree, so the exemption two other packages hold is
    visible as an exemption and this one has none.
    """
    forbidden = outward("half/consolidate")
    assert "half.model" in forbidden, "the lift table has grown a fifth entry"
    offenders = {
        str(path.relative_to(ROOT)): found
        for path in _modules() if (found := reaches(path, forbidden))
    }
    assert not offenders, offenders


@pytest.mark.cap7_minting
def test_the_package_reaches_no_model_transitively_either():
    """One hop is not enough: a minter that imported a helper that imported the
    port would pass a direct check while being every bit as expensive."""
    edges = {
        ".".join(path.relative_to(ROOT).with_suffix("").parts):
            {name for name in _imports_of(path)}
        for path in (ROOT / "half").rglob("*.py")
    }

    def walk(start, seen=None):
        seen = seen if seen is not None else set()
        for target in edges.get(start, ()):
            if not target.startswith("half"):
                continue
            module = target if target in edges else target.rsplit(".", 1)[0]
            if module in seen:
                continue
            seen.add(module)
            walk(module, seen)
        return seen

    for path in _modules():
        area = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        touched = {m for m in walk(area) if m.startswith("half.model")}
        assert not touched, f"{area} reaches {sorted(touched)}"


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


@pytest.mark.cap7_minting
def test_no_log_line_in_the_minting_can_carry_content():
    """AD-22: counts and ids only. Every argument to a logging call is a
    literal, a count, a main id, a tension id or an exception *type* — never a
    record, a claim or a field value."""
    for name in ("half/consolidate/mint.py", "half/consolidate/pass_.py"):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "logger"):
                continue
            rendered = [ast.unparse(argument) for argument in node.args]
            assert all("f'" not in text and 'f"' not in text
                       for text in rendered), f"{name}:{node.lineno}"
            for text in rendered[1:]:
                assert any(
                    marker in text
                    for marker in ("main_id", "len(", "type(", "tension_id",
                                   "couple.id", "sorted(set(", "consulted",
                                   "plan.unbudgeted", "plan.considered",
                                   # A pinned module constant, not a value out
                                   # of anybody's log.
                                   "CEILING")
                ), f"{name}:{node.lineno} may carry content: {text!r}"


@pytest.mark.cap7_minting
def test_the_result_carries_counts_and_ids_but_never_a_claim(
    registry, tmp_path
):
    """AD-22 on the value the pass hands back, and the reason the *record* check
    above is not enough: a claim reaches an operator's log through whatever
    formats a result.

    **Anchored on a result that carries something.** ``"farmland" not in
    repr(MintResult())`` is trivially true, so this passed on a build that
    minted nothing — an absence assertion over an empty value asserts nothing.
    The result has to hold the ids and the counts *and* none of the words.
    """
    seeded(registry, tmp_path)
    result = run_pass(registry, "vidit", judge=Judge(True))
    ident = key_of("b_said", "b_did")
    assert result.minted.minted == (ident,)
    assert result.minted.considered == 1 and result.minted.consulted == 1

    rendered = repr(result.minted)
    # The ids and the counts are in it, so the absence below is an absence from
    # something rather than an absence of everything.
    assert ident in rendered
    for word in ("farmland", "listing", "buy", "opened", "March", "means"):
        assert word not in rendered, word


@pytest.mark.cap7_minting
@pytest.mark.parametrize(
    "broken",
    [
        {"beliefs": "not a mapping"},
        {"tensions": "not a mapping"},
        {"loops": 7},
        {"loops": object()},
        {"passes": 7},
        {"gone": 7},
        {"beliefs": {"b_1": "not a mapping"}},
        {"tensions": {"x_1": "not a mapping"}},
    ],
    ids=["beliefs", "tensions", "loops-number", "loops-object", "passes",
         "gone", "belief-row", "tension-row"],
)
def test_the_slate_never_raises_on_a_view_this_build_cannot_read(broken):
    """``slate`` says *"never raises"*, and it was an overclaim.

    ``read`` and ``mint.linked`` guarded their arguments; ``watermark``,
    ``on_a_loop`` and the two ``in`` tests against the tension and erased tables
    did not, so a ``loops`` or a ``passes`` that was not iterable came out of
    the middle of a function whose whole contract is that it does not — and the
    alternative to reporting is a main whose entire night ends on one malformed
    field.

    Every field of the view, one case each, because a guard on one of them is
    what the code already had — and every case carries a **real belief table**
    beside the broken field, so the couple that reaches the tension and erased
    tables is actually built. Breaking one field of an otherwise empty view
    exercises nothing past the first guard, which is how two of these passed
    against the unguarded code.
    """
    whole = {
        "beliefs": _mint_rows(*_SIDES),
        "tensions": {},
        "loops": ("buy-farmland",),
        "passes": (),
        "gone": frozenset(),
    }
    view = MintView(**{**whole, **broken})
    plan = minting.slate(view, now=stamp(NOON))
    assert isinstance(plan.within, tuple)
    assert plan.considered >= 0

    # Non-vacuity: the unbroken view produces couples, so a case above is a
    # broken field surviving real work rather than an empty view surviving
    # nothing.
    assert minting.slate(MintView(**whole), now=stamp(NOON)).considered > 0


@pytest.mark.cap7_minting
def test_the_mint_view_carries_no_license_no_ceiling_and_no_crisis_record(
    registry, tmp_path
):
    """The narrowing at the door, asserted on what came through it rather than
    on what the code asks for. ``surface_view``'s own lesson: a view that
    returned ``State`` entire let a governance branch be written inside the
    surface with no new import and no new door."""
    seeded(registry, tmp_path)
    asyncio.run(registry.suspend_for_crisis(
        "vidit", t=stamp(NOON - 100), tier="acute", score=3
    ))
    view = asyncio.run(registry.mint_view("vidit"))

    assert isinstance(view, MintView)
    assert set(view.__dataclass_fields__) == {
        "beliefs", "tensions", "loops", "passes", "gone"
    }
    for row in view.beliefs.values():
        assert set(row) <= {"id", "t", "claim", "subject", "ledger", "loop"}
        assert "license" not in row and "support" not in row
    assert all(isinstance(item, str) for item in view.passes)
    assert all(isinstance(item, str) for item in view.loops)


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


@pytest.mark.cap7_minting
def test_every_minting_guarantee_this_story_rests_on_still_exists():
    required = {
        "test_a_changed_entry_and_a_revealed_one_that_disagree_become_a_tension",
        "test_a_pair_the_cheap_filter_rejects_never_reaches_the_judge",
        "test_the_filter_admits_the_pair_the_capability_exists_for",
        "test_the_judgements_bought_do_not_follow_the_ledger",
        "test_the_growth_case_would_fail_against_an_all_pairs_pass",
        "test_a_pass_that_would_exceed_its_bound_stops_minting_and_says_so",
        "test_the_bound_stops_the_minting_too_and_not_only_the_asking",
        "test_a_pass_inside_its_bound_does_not_report_the_bound",
        "test_the_budget_is_pinned_by_value",
        "test_a_full_budget_takes_the_most_surprising_couples_first",
        "test_no_port_wired_completes_the_pass_and_mints_nothing",
        "test_a_judge_that_cannot_say_mints_nothing_and_is_counted_apart",
        "test_a_judge_that_raises_costs_that_couple_and_never_the_pass",
        "test_nothing_changed_since_the_last_pass_reaches_the_judge_at_all",
        "test_a_pair_already_carrying_a_live_tension_never_reaches_the_judge",
        "test_the_same_pass_twice_over_one_log_mints_the_same_set_once",
        "test_a_tension_the_main_erased_is_never_minted_again",
        "test_a_tension_over_a_belief_supporting_a_loop_leaves_the_wanting_standing",
        "test_nothing_in_the_consolidate_package_can_move_a_loop",
        "test_a_main_in_crisis_mode_is_never_minted_for",
        "test_a_minted_tension_folds_identically_after_a_rebuild",
        "test_the_judgement_port_offers_exactly_one_method",
        "test_no_implementation_of_the_judgement_lives_in_the_package",
        "test_the_shipped_wiring_holds_the_pass_and_wires_no_judge",
        "test_nothing_in_the_package_reaches_a_model_a_channel_or_the_network",
        "test_the_mint_view_carries_no_license_no_ceiling_and_no_crisis_record",
        "test_a_minted_tension_carries_a_state_a_pair_and_a_license_and_no_more",
        # Review loop 2. Each of these is the only case asserting its rule,
        # and each was written because the rule was silently absent.
        "test_the_weight_and_the_order_are_the_same_whichever_way_a_couple_is_built",
        "test_the_same_words_in_a_different_order_are_not_a_restatement",
        "test_the_pass_reports_an_upper_bound_on_what_it_compared",
        "test_a_pass_that_reaches_the_couple_ceiling_says_so",
        "test_the_minting_arithmetic_actually_leaves_the_event_loop",
        "test_a_night_with_nothing_admitted_does_not_tokenise_the_whole_ledger",
        "test_a_main_who_was_suspended_still_has_everything_they_said_meanwhile",
        "test_a_main_whose_first_pass_this_is_still_treats_everything_as_new",
        "test_the_couples_beyond_the_bound_are_dropped_and_the_pass_says_dropped",
        "test_a_judgement_that_raised_was_still_bought_and_is_still_billed",
        "test_a_mint_carries_a_pair_a_fresh_state_and_the_ladders_floor",
        "test_the_slate_never_raises_on_a_view_this_build_cannot_read",
    }
    missing = required - _cases_defined_here()
    assert not missing, (
        f"a minting guarantee was deleted: {sorted(missing)}. A floor on the "
        f"suite cannot protect these — each carries a whole property"
    )
