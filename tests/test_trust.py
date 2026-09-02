"""CAP-4 story 5b: the trust currency — earned, spent, and never counted.

The balance and the stakes rule. ``tests/test_unasked.py`` carries the queue
and its two gates; this file carries the two things the queue spends and weighs.

**Nothing here reads a clock and nothing waits for real time.** Every stamp is
chosen by the test, which is the point of what is under test: the balance is a
fold over records and the stakes rule is arithmetic over two periods, so the
same log gives the same answers for ever (AD-30).

**The central case is the one that would still pass with the wrong design.**
An increment-on-delivery, decrement-on-ask counter replays perfectly: it is
never *inconsistent*, only *wrong*, so a round-trip assertion cannot see it.
What sees it is a balance read after the derived view has been discarded, after
a rebuild, and after a pass that runs twice — and the structural case that the
fold has nowhere to keep one.

**Both sides of the stakes boundary are pinned at every timescale.** Review on
story 8 found a threshold that anything between roughly six and thirteen
satisfied, which is a band rather than a number; the bar here is one
interruption, and *at* it and *one day past* it are asserted for all four
scales.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.errors import TrustError
from half.governance import ladder
from half.governance.ladder import License
from half.loops import ledger as loops
from half.loops.ledger import Loop
from half.loops.states import LIVE_STATES, LoopState
from half.loops.timescale import PERIOD_DAYS, Timescale
from half.store.ops import SCHEMA_VERSION, TOUCH_TENSION, Op
from half.store.records import ABOUT, ASKED_FIELDS, QUESTION, SENT, Record
from half.store.store import Store
from half.surface import touch as touch_module
from half.surface.touch import Origin
from half.trust.balance import (
    Balance,
    balance,
    delivered,
    spent,
    tombstoned,
)
from half.trust.stakes import (
    BELOW_THE_BAR,
    FINISHED,
    INTERRUPTION_DAYS,
    NO_PERIOD,
    NO_SUBJECT,
    NO_WANTING,
    REASONS as STAKE_REASONS,
    Stakes,
    stakes,
)
from half.trust.unasked import (
    ASK_CRISIS,
    ASK_NOT_PERMITTED,
    ASK_OUTCOMES,
    ASK_RECORDED,
    ASK_REFUSED,
    ASK_UNAFFORDABLE,
    Unasked,
)

pytestmark = [pytest.mark.cap4]

ROOT = Path(__file__).resolve().parents[1]

ORIGIN = Origin(kind=TOUCH_TENSION, id="x_1")


# ── helpers ──────────────────────────────────────────────────────────────────


ASKABLE_LOOP = "buy-farmland"


def an_askable_belief(store, *, ident="b_1", t="2026-08-01T00:00Z"):
    """A belief a question about would pass the ladder gate at the spend.

    Seeded through the ladder, like ``conftest.seed_belief``: `ask` is a rung a
    belief *earns*, and a test that spells the field by hand is doing exactly
    what story 5a forbids at test scale.
    """
    if ASKABLE_LOOP not in store.state().loops:
        store.record(Op.LOOP_TRANSITION, f"l_{ident}", t,
                     **loops.opened(ASKABLE_LOOP, state="stalled",
                                    timescale="years",
                                    last_movement="2026-01-04",
                                    loops=store.state().loops))
    store.record(Op.ASSERT, ident, t, claim="wants to buy farmland",
                 loop=ASKABLE_LOOP, topics=["farmland"], **ladder.admitted())
    record = store.state().beliefs[ident]
    store.record(Op.ASSERT, ident, t,
                 **ladder.promote(record, to=License.ASK, acknowledged=True))


def a_favour(store, *, t, day, loops_touched=()):
    """One unprompted message that reached the main — story 10's own record."""
    store.record(
        Op.TOUCH, f"tc_{t}", t,
        **touch_module.spoke(day=day, origin=ORIGIN, loops=loops_touched),
    )


def a_raise(store, *, t, loop="swim-weekly"):
    """A raise that marks no day: CAP-10's interrupt shape. Earns nothing."""
    store.record(Op.TOUCH, f"tc_{t}", t, **touch_module.raised(loop, origin=ORIGIN))


def a_repair(store, *, t, day):
    """A day spent with no message sent. Earns nothing."""
    store.record(Op.TOUCH, f"tc_{t}", t, **touch_module.repaired(day=day))


def an_ask(store, *, t, question="q_1", about="b_1"):
    store.record(Op.ASKED, f"qa_{t}", t, question=question, about=about)


def a_loop(
    slug="swim-weekly",
    *,
    state=LoopState.ADVANCING,
    timescale=Timescale.WEEKS,
    last_movement="2026-07-01",
):
    return {
        slug: Loop(
            id=slug,
            state=None if state is None else str(state),
            timescale=None if timescale is None else str(timescale),
            last_movement=last_movement,
        )
    }


def a_belief(loop="swim-weekly", **fields):
    record = {"id": "b_1", "claim": "swims on tuesdays", **fields}
    if loop is not None:
        record["loop"] = loop
    return record


# ═════════════════════════════════════════════════════════════════════════════
# matrix: a favour delivered / a favour undelivered
# ═════════════════════════════════════════════════════════════════════════════


def test_an_unprompted_message_that_reached_the_main_earns(store):
    """Matrix: *a favour delivered*.

    Read off story 10's record rather than from a second fact of this story's
    invention: a ``touch`` that marked one of the main's days and says a
    message was sent.
    """
    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01")
    assert balance(store.log) == Balance(earned=1, spent=0)


def test_a_raise_that_marks_no_day_earns_nothing(store):
    """Matrix: *a favour undelivered* — nothing was sent.

    CAP-10's interrupt raises a loop and spends no day. Story 10 split the two
    facts apart so the morning budget could not be eaten silently; this is the
    same split doing the same work one layer up — an interrupt is not a favour.
    """
    a_raise(store, t="2026-09-01T09:00Z")
    assert balance(store.log).earned == 0


def test_a_day_spent_with_nothing_sent_earns_nothing(store):
    """Matrix: *a favour undelivered* — the repair path.

    A day marker that says ``sent=False`` is a day Half consumed deliberately
    without speaking. Delivery, not intent.
    """
    a_repair(store, t="2026-09-01T03:00Z", day="2026-09-01")
    assert balance(store.log).earned == 0


@pytest.mark.parametrize(
    "value", [False, None, "true", 1, "yes"],
    ids=["false", "absent", "string", "int", "yes"],
)
def test_sent_is_read_strictly_and_only_true_earns(value):
    """A field that *grants* a permission is read strictly, exactly as
    ``ladder.known_to_main`` is: anything that is not an explicit ``True`` is
    not a message that reached the main."""
    fields = {"local_day": "2026-09-01", "origin_kind": TOUCH_TENSION,
              "origin_id": "x_1", "t": "2026-09-01T03:00Z", "op": "touch",
              "id": "tc_1"}
    if value is not None:
        fields[SENT] = value
    record = Record(op=Op.TOUCH, id="tc_1", t="2026-09-01T03:00Z", data=fields)
    assert delivered(record) is False


def test_a_touch_that_says_sent_but_marks_no_day_earns_nothing():
    """Both halves of the predicate, not one.

    ``delivered`` is ``marks_day(...) and sent is True``, and review found that
    keeping the ``marks_day`` call while discarding its result passed the whole
    suite — because every touch in the fixtures that says ``sent=True`` also
    carries a day. This is the record that separates them.

    It takes a hand-built ``Record`` because the append gate refuses ``sent``
    without ``local_day`` (``validate_touch_fields``), which is the right place
    for that rule. What this pins is that the *reader* does not depend on the
    writer having been strict.
    """
    claiming = Record(
        op=Op.TOUCH, id="tc_1", t="2026-09-01T03:00Z",
        data={"t": "2026-09-01T03:00Z", "op": "touch", "id": "tc_1",
              SENT: True, "origin_kind": TOUCH_TENSION, "origin_id": "x_1"},
    )
    assert delivered(claiming) is False


def test_the_tombstone_predicate_is_asserted_on_its_own():
    """``delivered`` refuses a tombstoned touch *twice over* — the body is
    stripped, so ``marks_day`` also fails — which means deleting the tombstone
    clause changes no behaviour any fixture can produce. Review deleted it and
    the suite stayed green, so the predicate itself is pinned here.

    ``spent`` deliberately does **not** consult it: a question that was asked
    was asked, and reading an erasure as un-asked would hand back a favour Half
    had already used.
    """
    body = {"t": "2026-09-01T03:00Z", "op": "touch", "id": "tc_1", "v": 8}
    marker = {"local_day": "2026-09-01", SENT: True,
              "origin_kind": TOUCH_TENSION, "origin_id": "x_1"}
    live = Record(op=Op.TOUCH, id="tc_1", t="2026-09-01T03:00Z",
                  data={**body, **marker})
    stripped = Record(op=Op.TOUCH, id="tc_1", t="2026-09-01T03:00Z",
                      data={**body, "tombstone": True})
    assert tombstoned(live) is False and tombstoned(stripped) is True
    assert delivered(live) is True and delivered(stripped) is False

    # **The record the clause actually exists for**, and the reason the case
    # above is not enough on its own: ``expunge_bodies`` strips the body, so a
    # real tombstone fails ``marks_day`` anyway and deleting the tombstone
    # clause changes nothing any fixture can produce — review deleted it and the
    # suite stayed green. A tombstone is an erasure whatever else survives
    # beside it, so the predicate is asserted against a record that still
    # carries a readable day.
    kept = Record(op=Op.TOUCH, id="tc_1", t="2026-09-01T03:00Z",
                  data={**body, **marker, "tombstone": True})
    assert tombstoned(kept) is True
    assert delivered(kept) is False, (
        "a tombstoned favour still earned; an erasure is an erasure"
    )

    asked = Record(op=Op.ASKED, id="qa_1", t="2026-09-01T10:00Z",
                   data={"t": "2026-09-01T10:00Z", "op": "asked", "id": "qa_1",
                         "v": 8, "tombstone": True})
    assert tombstoned(asked) is True and spent(asked) is True


def test_an_erased_favour_stops_earning_and_an_erased_spend_still_spends(store):
    """**Every unreadable record resolves in the direction of asking less**, and
    the two halves are deliberately not symmetric.

    A tombstoned touch has lost its body, so nothing about it is readable as
    delivered — the balance falls. A tombstoned spend keeps spending: a question
    that was asked was asked, and reading an erasure as un-asked would hand back
    a favour Half had already used, which is the one direction this must not
    resolve in.
    """
    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01",
             loops_touched=("sell-the-flat",))
    an_ask(store, t="2026-09-01T10:00Z")
    store.record(Op.LOOP_TRANSITION, "l_1", "2026-09-01T00:00Z",
                 **loops.opened("sell-the-flat", state="stalled",
                                timescale="months", last_movement="2026-01-04",
                                loops=store.state().loops))
    assert balance(store.log) == Balance(earned=1, spent=1)

    # Both halves are erased **for real**, and by the two routes that actually
    # produce a tombstone: a loop erasure reaches the day marker through its
    # ``loop`` field, and a spend names no loop, so it takes the id. An earlier
    # version of this case erased only the loop and asserted the spend half
    # against a record that had never been tombstoned — which is the shape of a
    # test that passes whatever the code does.
    store.expunge("sell-the-flat", t="2026-09-02T00:00Z")
    store.log.expunge_bodies({"qa_2026-09-01T10:00Z"})
    store.rebuild()
    bodies = {r.op: r.data for r in store.log if r.op in (Op.TOUCH, Op.ASKED)}
    assert bodies[Op.TOUCH].get("tombstone") is True
    assert bodies[Op.ASKED].get("tombstone") is True, "the spend was never erased"

    after = balance(store.log)
    assert after.earned == 0, "an erased favour still earned"
    assert after.spent == 1, "an erased spend stopped spending"
    assert after.overdrawn is True and after.unspent == 0


# ═════════════════════════════════════════════════════════════════════════════
# matrix: balance computed / replay
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_favour
def test_the_same_log_gives_the_same_balance_twice(store):
    """Matrix: *balance computed*. Pure: no clock, no state, no read traffic."""
    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01")
    a_favour(store, t="2026-09-02T03:00Z", day="2026-09-02")
    an_ask(store, t="2026-09-02T10:00Z")
    assert len({balance(store.log) for _ in range(20)}) == 1
    assert balance(store.log) == Balance(earned=2, spent=1)


@pytest.mark.cap4_favour
def test_a_pass_that_runs_twice_does_not_move_the_balance(store):
    """**The case the tempting implementation fails.**

    Increment-on-delivery and decrement-on-ask is the natural design, and it is
    the one that breaks the first time a pass runs twice: the second run bumps
    the counter again over records that have not changed. A balance folded out
    of the log cannot, because folding the same records twice is folding the
    same records.
    """
    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01")
    first = balance(store.log)
    for _ in range(3):
        store.rebuild()
        assert balance(store.log) == first


@pytest.mark.cap4_favour
def test_the_balance_survives_discarding_the_derived_view(store, tmp_path):
    """Matrix: *replay*. AD-4, from the direction that matters here.

    The derived view is deleted and the log replayed. A counter kept in SQLite
    would come back as whatever the last rebuild wrote; a balance read from the
    log comes back because the log is the authority (AD-3).
    """
    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01")
    a_favour(store, t="2026-09-02T03:00Z", day="2026-09-02")
    an_ask(store, t="2026-09-02T10:00Z")
    before = balance(store.log)
    root = store.root
    store.close()

    (root / "half.db").unlink()
    with Store(root) as reopened:
        reopened.rebuild()
        assert balance(reopened.log) == before
        assert reopened.fold().canonical_json() == reopened.state().canonical_json()


@pytest.mark.cap4_favour
def test_the_balance_is_the_same_before_and_after_a_rebuild(store):
    """A rebuild is what a crash between an append and the derived write leaves
    behind. The balance is read from the log, so it cannot be behind one."""
    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01")
    an_ask(store, t="2026-09-01T10:00Z")
    before = balance(store.log)
    store.rebuild()
    assert balance(store.log) == before


def test_a_spend_folds_and_replays(store):
    """The op is in the closed vocabulary, folds without raising, and the fold
    round-trips through SQLite byte-identically."""
    an_ask(store, t="2026-09-01T10:00Z")
    assert store.fold().canonical_json() == store.state().canonical_json()
    assert [r.op for r in store.log] == [Op.ASKED]


def test_the_schema_version_moved_with_the_op(store):
    """AD-29: adding an op is a deliberate versioned change, and this one had a
    reason none of the seven before it had.

    Every other op says something the fold materializes, so an older build
    meeting one drops a field. A spend is half of a quantity computed straight
    from the log, so a build that could not see one would count only the earning
    half — a Half whose balance never falls however many questions it asks.
    """
    from half.errors import SchemaVersionError
    from half.store.records import decode

    assert SCHEMA_VERSION == 8
    an_ask(store, t="2026-09-01T10:00Z")
    assert next(iter(store.log)).data["v"] == SCHEMA_VERSION
    with pytest.raises(SchemaVersionError):
        decode('{"t":"2026-09-01T10:00Z","op":"asked","id":"qa_1",'
               '"question":"q_1","about":"b_1","v":%d}' % (SCHEMA_VERSION + 1),
               path="t", lineno=1)


# ═════════════════════════════════════════════════════════════════════════════
# matrix: unspent balance — a defect, and therefore visible
# ═════════════════════════════════════════════════════════════════════════════


def test_favours_delivered_and_nothing_asked_show_as_unspent(store):
    """Matrix: *unspent balance*.

    The number is inspectable so that hoarding can be *seen* rather than
    inferred: eleven favours given and none used is a Half being cowardly, and
    the glossary calls that a defect rather than a virtue.
    """
    for day in range(1, 12):
        a_favour(store, t=f"2026-09-{day:02d}T03:00Z", day=f"2026-09-{day:02d}")
    held = balance(store.log)
    assert held.earned == 11 and held.spent == 0
    assert held.unspent == 11 and held.spendable is True
    assert held.overdrawn is False


def test_an_overdrawn_log_is_visible_rather_than_clamped_away():
    """``unspent`` clamps at zero so a deficit cannot present as credit — and
    ``overdrawn`` says that it clamped, because an anomaly nobody surfaces is
    one nobody goes looking for."""
    deficit = Balance(earned=1, spent=3)
    assert deficit.unspent == 0
    assert deficit.spendable is False
    assert deficit.overdrawn is True


def test_a_count_of_events_cannot_be_negative():
    """*Never negative* was a docstring beside two fields that could be.

    ``balance`` cannot produce one, but the type is public: a hand-built
    ``Balance(earned=-1)`` made ``unspent`` and ``overdrawn`` disagree about
    the same log. Enforced now, rather than promised — which is the whole shape
    of this review round.
    """
    assert Balance(earned=-3, spent=-1) == Balance(earned=0, spent=0)
    assert Balance(earned=-1, spent=2).overdrawn is True
    # A flag arriving where a count belongs is a caller error, not one favour.
    assert Balance(earned=True, spent=None) == Balance(earned=0, spent=0)


@pytest.mark.parametrize(
    "fields",
    [{"question": "", "about": "b_1"}, {"question": "q_1", "about": "  "},
     {"question": None, "about": "b_1"}, {"question": "q_1", "about": 7}],
    ids=["blank-question", "blank-about", "none-question", "int-about"],
)
def test_a_spend_that_names_nothing_is_refused_before_the_mutex(tmp_path, fields):
    """A caller mistake should not queue behind a main's turn to be told about,
    and the append gate one layer down would refuse the same values — this is
    the early, cheap half of the same rule."""
    registry = ActorRegistry(tmp_path)
    try:
        with pytest.raises(TrustError):
            asyncio.run(registry.note_ask(
                "vidit", t="2026-09-01T10:00Z", **fields))
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []


def test_the_favour_rule_is_one_predicate_both_sides_read():
    """``spendable`` rather than a ``> 0`` written out in each place. Two
    spellings of one comparison agree until an overdrawn log arrives."""
    assert Balance(earned=0, spent=0).spendable is False
    assert Balance(earned=1, spent=0).spendable is True
    assert Balance(earned=1, spent=1).spendable is False
    assert Balance(earned=1, spent=5).spendable is False


# ═════════════════════════════════════════════════════════════════════════════
# matrix: spend on ask / refused question
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_favour
def test_the_balance_falls_once_when_a_question_is_asked(tmp_path):
    """Matrix: *spend on ask*. Once, not twice, and only here."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
            a_favour(seeded, t="2026-09-02T03:00Z", day="2026-09-02")
        before = asyncio.run(registry.trust_view("vidit")).balance
        assert before.unspent == 2

        outcome = asyncio.run(registry.note_ask(
            "vidit", t="2026-09-02T10:00Z", question="q_1", about="b_1"))
        assert outcome == ASK_RECORDED
        after = asyncio.run(registry.trust_view("vidit")).balance
        assert after.unspent == 1 and after.spent == 1
    finally:
        registry.close()


@pytest.mark.cap4_favour
def test_reading_the_queue_and_refusing_a_question_spend_nothing(tmp_path):
    """Matrix: *refused question*. **Never a silent spend.**

    Reading the view, considering every question and having every one of them
    refused must leave the log exactly as it was. The guarantee is structural
    as well as asserted: the pure half of ``half.trust.unasked`` has no store,
    and the only append is ``note_ask``.
    """
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
        for _ in range(5):
            asyncio.run(registry.trust_view("vidit"))
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 0
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert [r.op for r in store.log] == [Op.TOUCH]


@pytest.mark.cap4_favour
def test_a_spend_that_cannot_be_paid_for_is_refused_rather_than_recorded(tmp_path):
    """*The favour buys the question* stays true of the **log**, not only of the
    caller's intentions. Appending anyway and letting the balance run negative
    would make the rule something the log reports on rather than something that
    holds."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
        outcome = asyncio.run(registry.note_ask(
            "vidit", t="2026-09-01T10:00Z", question="q_1", about="b_1"))
        assert outcome == ASK_UNAFFORDABLE
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 0
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []


@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_forged_permission_is_refused_at_the_registry_and_burns_nothing(tmp_path):
    """**The central defect review found, closed at the layer that holds the
    mutex.**

    A hand-built ``Ask`` for a question that passed no stakes gate, no ladder
    gate and no topic gate reached ``spend`` and was recorded — a favour burned
    on a question about a belief that does not exist. ``note_ask`` trusted its
    arguments; it re-derives the permission now, from the fold, under the
    mutex.

    Refused as ``ASK_NOT_PERMITTED`` rather than ``ASK_UNAFFORDABLE``: the
    ladder is asked before the balance on purpose, because *"you cannot afford
    this"* invites a caller to earn a favour and retry a question Half may
    never raise.
    """
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
        assert asyncio.run(registry.trust_view("vidit")).balance.spendable
        outcome = asyncio.run(registry.note_ask(
            "vidit", t="2026-09-01T10:00Z", question="q_junk",
            about="nonexistent"))
        assert outcome == ASK_NOT_PERMITTED
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 0
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert [r for r in store.log if r.op is Op.ASKED] == []


@pytest.mark.cap4_favour
@pytest.mark.cap4_gates
def test_a_cap_that_drops_between_the_choice_and_the_spend_refuses_it(tmp_path):
    """**The AD-28 window that was closed for crisis and open for the ceiling.**

    ``note_ask`` re-read the mode at the spend and did not re-read the cap, so a
    main whose ceiling dropped to `behave` between choosing a question and
    paying for it was still asked. ``trust_view``'s own docstring calls a stale
    cap *"the one window AD-28 exists to close"*.

    The cap is lowered by the ordinary governance path, so the case exercises
    the rule rather than a hand-written record — and no branch in the queue or
    the registry mentions aftercare, which is the whole of AD-28.
    """
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
        assert asyncio.run(registry.trust_view("vidit")).balance.spendable

        asyncio.run(registry.hold_ceiling(
            "vidit", t="2026-09-01T09:00Z", to=License.BEHAVE,
            because="aftercare (CAP-12)"))
        outcome = asyncio.run(registry.note_ask(
            "vidit", t="2026-09-01T10:00Z", question="q_1", about="b_1"))
        assert outcome == ASK_NOT_PERMITTED
        assert asyncio.run(registry.trust_view("vidit")).balance.spent == 0
    finally:
        registry.close()


@pytest.mark.cap4_gates
def test_a_quarantined_subject_is_refused_at_the_spend_too(tmp_path):
    """Quarantine lands by the same route the ceiling does, and is refused at
    the same point — one call to ``may_be_raised``, and no branch for either."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
            record = seeded.state().beliefs["b_1"]
            candidate = ladder.quarantine_candidate(record, reason="a wound")
            seeded.record(Op.ASSERT, "b_1", "2026-09-01T08:00Z",
                          **ladder.quarantine(record, candidate=candidate,
                                              answered=True))
        assert asyncio.run(registry.note_ask(
            "vidit", t="2026-09-01T10:00Z", question="q_1",
            about="b_1")) == ASK_NOT_PERMITTED
    finally:
        registry.close()


@pytest.mark.cap4_favour
def test_two_spends_in_one_second_do_not_share_a_record_id(tmp_path):
    """``qa_{t}`` alone collides, and ``Op.ASKED`` is append-keyed — so two
    records sharing an id are two bodies a single ``expunge_bodies`` erases
    together. Reachable now that the queue can offer more than one ``Ask``."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            an_askable_belief(seeded, ident="b_2")
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
            a_favour(seeded, t="2026-09-02T03:00Z", day="2026-09-02")
        for question, about in (("q_1", "b_1"), ("q_2", "b_2")):
            assert asyncio.run(registry.note_ask(
                "vidit", t="2026-09-03T10:00Z", question=question,
                about=about)) == ASK_RECORDED
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        ids = [r.id for r in store.log if r.op is Op.ASKED]
        assert len(ids) == len(set(ids)) == 2, ids
        assert balance(store.log) == Balance(earned=2, spent=2)


@pytest.mark.cap4_favour
def test_a_spend_that_landed_is_reported_even_when_the_rebuild_fails(tmp_path):
    """``Store.append`` writes the line and *then* rebuilds, so a failure in the
    rebuild leaves the record durable.

    Letting the exception out told the caller nothing was recorded — so it would
    ask nothing, and the main would lose a favour and get no question. The log
    is re-read before a failure is believed, exactly as ``claim_day`` does.
    """
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")

        async def spend_with_a_broken_rebuild():
            async with registry.acquire("vidit") as actor:
                store = actor.store
                original = store.rebuild

                def failing():
                    raise RuntimeError("the derived view is unavailable")

                store.rebuild = failing  # type: ignore[method-assign]
            try:
                return await registry.note_ask(
                    "vidit", t="2026-09-01T10:00Z", question="q_1", about="b_1")
            finally:
                store.rebuild = original  # type: ignore[method-assign]

        assert asyncio.run(spend_with_a_broken_rebuild()) == ASK_RECORDED
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert len([r for r in store.log if r.op is Op.ASKED]) == 1


@pytest.mark.cap4_favour
def test_one_favour_cannot_be_spent_twice_even_by_two_overlapping_turns(tmp_path):
    """**The ordering no single-threaded case would have written.**

    Two turns reach ``note_ask`` for one main against one delivered favour. A
    read here followed by an append there lets both find the favour unspent and
    both ask, which is *the same favour buying two questions* arriving through
    concurrency rather than through arithmetic. The check and the append are
    one serialized operation, so exactly one lands.
    """
    registry = ActorRegistry(tmp_path)

    async def race():
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            an_askable_belief(seeded, ident="b_2")
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
        return await asyncio.gather(
            registry.note_ask("vidit", t="2026-09-02T10:00Z",
                              question="q_1", about="b_1"),
            registry.note_ask("vidit", t="2026-09-02T10:01Z",
                              question="q_2", about="b_2"),
        )

    try:
        outcomes = asyncio.run(race())
    finally:
        registry.close()
    assert sorted(outcomes) == sorted([ASK_RECORDED, ASK_UNAFFORDABLE])
    with Store(tmp_path / "vidit") as store:
        assert len([r for r in store.log if r.op is Op.ASKED]) == 1


@pytest.mark.cap4_favour
def test_a_second_turn_that_read_first_still_cannot_spend_the_same_favour(tmp_path):
    """**The interleaving the gather above cannot actually produce**, and the
    one that matters.

    Two coroutines handed to ``asyncio.gather`` do not interleave unless one of
    them awaits, so a read-then-append implementation completes the first call
    whole and the race never happens — which is precisely how a serialization
    bug survives a suite that looks like it tests for one. This case *forces*
    the window: one turn holds the main's mutex, a second turn is started and
    reaches the door, the first turn appends its spend, and only then is the
    second let through.

    A ``note_ask`` that read the balance before taking the mutex would have
    read *unspent*, waited, and then appended a second spend against one
    favour. Verified against exactly that mutation.
    """
    registry = ActorRegistry(tmp_path)

    async def race():
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            an_askable_belief(seeded, ident="b_2")
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
        second = None
        async with registry.acquire("vidit") as actor:
            second = asyncio.create_task(registry.note_ask(
                "vidit", t="2026-09-02T10:01Z", question="q_2", about="b_2"))
            # Let the second turn run as far as it can. A yield, not a wait:
            # nothing here sleeps on real time.
            for _ in range(4):
                await asyncio.sleep(0)
            assert not second.done(), (
                "the second turn got past the mutex while it was held"
            )
            actor.store.record(Op.ASKED, "qa_2026-09-02T10:00Z",
                               "2026-09-02T10:00Z", question="q_1", about="b_1")
        return await second

    try:
        assert asyncio.run(race()) == ASK_UNAFFORDABLE
    finally:
        registry.close()
    with Store(tmp_path / "vidit") as store:
        assert len([r for r in store.log if r.op is Op.ASKED]) == 1


@pytest.mark.cap4_favour
def test_a_favour_delivered_between_two_asks_pays_for_the_second(tmp_path):
    """The interleaving from the other side: ask, earn, ask. The second spend
    is affordable because a *second* favour arrived, not because the first was
    still there."""
    registry = ActorRegistry(tmp_path)
    try:
        with Store(tmp_path / "vidit") as seeded:
            an_askable_belief(seeded)
            an_askable_belief(seeded, ident="b_2")
            a_favour(seeded, t="2026-09-01T03:00Z", day="2026-09-01")
        assert asyncio.run(registry.note_ask(
            "vidit", t="2026-09-01T10:00Z", question="q_1",
            about="b_1")) == ASK_RECORDED
        assert asyncio.run(registry.note_ask(
            "vidit", t="2026-09-01T11:00Z", question="q_2",
            about="b_2")) == ASK_UNAFFORDABLE

        async def earn_then_ask():
            async with registry.acquire("vidit") as actor:
                a_favour(actor.store, t="2026-09-02T03:00Z", day="2026-09-02")
            return await registry.note_ask(
                "vidit", t="2026-09-02T10:00Z", question="q_2", about="b_2")

        assert asyncio.run(earn_then_ask()) == ASK_RECORDED
        assert asyncio.run(registry.trust_view("vidit")).balance == Balance(
            earned=2, spent=2
        )
    finally:
        registry.close()


def test_a_spend_stamped_with_a_value_nothing_can_read_is_refused(tmp_path):
    """The log is append-only, so a spend nothing can order is one nothing can
    ever place against the favour that paid for it. ``2026-02-31`` matches the
    shape and is not a date."""
    registry = ActorRegistry(tmp_path)
    try:
        with pytest.raises(TrustError):
            asyncio.run(registry.note_ask(
                "vidit", t="2026-02-31T00:00Z", question="q_1", about="b_1"))
    finally:
        registry.close()


@pytest.mark.parametrize(
    "fields",
    [
        {QUESTION: "", ABOUT: "b_1"},
        {QUESTION: "q_1", ABOUT: ""},
        {QUESTION: 7, ABOUT: "b_1"},
        {QUESTION: "q_1", ABOUT: None},
        {ABOUT: "b_1"},
        {QUESTION: "q_1"},
        {QUESTION: "q_1", ABOUT: "b_1", "claim": "you have stopped swimming"},
        {QUESTION: "q_1", ABOUT: "b_1", "tombstone": True},
    ],
    ids=["no-question", "no-about", "question-int", "about-none", "question-absent",
         "about-absent", "a-claim-rode-in", "tombstone"],
)
def test_the_append_gate_refuses_a_spend_the_balance_could_not_count(store, fields):
    """Refused **before it is durable**. The allowlist is the point: every
    denylist this codebase has shipped was walked around, and a ``claim``
    written here is the main's own uncertainty made permanent (AD-22).

    ``tombstone`` is refused for the finding story 10's review made: listing it
    let a caller write one onto a live record, durable and skipped by the fold.
    """
    with pytest.raises((TrustError, ValueError)):
        store.record(Op.ASKED, "qa_1", "2026-09-01T10:00Z", **fields)
    assert [r for r in store.log if r.op is Op.ASKED] == []


@pytest.mark.parametrize(
    "fields",
    [
        {QUESTION: " q_1 ", ABOUT: "b_1"},
        {QUESTION: "q_1", ABOUT: "b_1 "},
        {QUESTION: "\tq_1", ABOUT: "b_1"},
    ],
    ids=["padded-question", "padded-about", "tabbed-question"],
)
def test_an_id_is_normalized_before_it_becomes_durable(store, fields):
    """**The id that was weighed must be the id that is written.**

    ``considered`` matched on ``about.strip()`` while ``spend`` passed the raw
    string through, so an append-only record could permanently name a belief id
    that no belief equals. ``Unasked`` strips both fields at construction, and
    this is what makes that a property of the log rather than of one caller's
    care — the same rule ``touch._loop_id`` applies to a loop slug.
    """
    with pytest.raises(TrustError):
        store.record(Op.ASKED, "qa_1", "2026-09-01T10:00Z", **fields)
    assert [r for r in store.log if r.op is Op.ASKED] == []


def test_a_question_carries_the_id_it_was_given_stripped_once(store):
    """The normalization is at ``Unasked``'s boundary, so the value that reaches
    the log is already the value that was looked up."""
    padded = Unasked(id="  q_1\n", about=" b_1 ")
    assert (padded.id, padded.about) == ("q_1", "b_1")
    assert Unasked(id="q_1", about="b_1") == padded
    assert Unasked(id=None, about=7).nameable is False
    store.record(Op.ASKED, "qa_1", "2026-09-01T10:00Z",
                 question=padded.id, about=padded.about)
    body = next(r.data for r in store.log if r.op is Op.ASKED)
    assert body[QUESTION] == "q_1" and body[ABOUT] == "b_1"


def test_a_spend_carries_exactly_the_allowed_fields(store):
    """And the registry builds its record from ``ASKED_FIELDS`` rather than from
    a second list, so the two cannot drift."""
    an_ask(store, t="2026-09-01T10:00Z", question="q_1", about="b_1")
    body = next(r.data for r in store.log if r.op is Op.ASKED)
    assert set(body) - {"t", "op", "id", "v"} == ASKED_FIELDS
    assert ASKED_FIELDS == {QUESTION, ABOUT}


def test_every_outcome_of_a_spend_is_one_of_the_closed_set():
    """Five outcomes across two layers. ``ASK_REFUSED`` is the queue's — the
    question no longer passes the gates, which is also what a hand-built ``Ask``
    gets — and the other three refusals are the registry's, decided under the
    main's own mutex where they cannot be stale."""
    assert ASK_OUTCOMES == {ASK_RECORDED, ASK_CRISIS, ASK_UNAFFORDABLE,
                            ASK_NOT_PERMITTED, ASK_REFUSED}
    assert len(ASK_OUTCOMES) == 5, "two outcomes share a spelling"


def test_a_spend_record_id_carries_no_question_text(store):
    """``BeliefLog.expunge_bodies`` keeps a tombstoned record's id, so anything
    in it survives an erasure. The id is built from the stamp alone."""
    an_ask(store, t="2026-09-01T10:00Z", question="q_1", about="b_1")
    assert [r.id for r in store.log if r.op is Op.ASKED] == ["qa_2026-09-01T10:00Z"]


def test_a_tombstoned_spend_does_not_poison_the_belief_namespace(store, seed):
    """A spend's record id is the **append's**, not any object's, so putting it
    in ``State.expunged`` would suppress whatever belief happened to share the
    identifier — for ever. The same rule ``touch`` and ``loop_transition``
    carry, and the reason ``Op.ASKED`` is in ``_APPEND_KEYED``."""
    store.record(Op.ASKED, "b_1", "2026-09-01T10:00Z", question="q_1", about="b_1")
    store.log.expunge_bodies({"b_1"})
    seed(store, "b_1", "2026-09-02T08:00Z", claim="swims on tuesdays")
    assert "b_1" in store.fold().beliefs, "a spend's erasure suppressed a belief"


@pytest.mark.parametrize("missing", [QUESTION, ABOUT], ids=[QUESTION, ABOUT])
def test_a_spend_missing_either_required_field_is_fatal_to_the_fold(missing):
    """AD-29: a record this build cannot attribute is never folded to nothing.

    **Both fields, symmetrically.** The append gate calls them equally required,
    and this branch was fatal on ``question`` only — so a record naming a
    question and no subject folded cleanly and counted as a spend, which is a
    favour consumed with no trace of what it was consumed for. A gate strict on
    the way in and lenient on the way out is one the log gets past by having
    been written by anything other than this build.
    """
    from half.errors import CorruptLogError
    from half.store.fold import fold

    data = {"t": "2026-09-01T10:00Z", "op": "asked", "id": "qa_1", "v": 8,
            QUESTION: "q_1", ABOUT: "b_1"}
    del data[missing]
    with pytest.raises(CorruptLogError):
        fold([Record(op=Op.ASKED, id="qa_1", t="2026-09-01T10:00Z", data=data)])


# ═════════════════════════════════════════════════════════════════════════════
# matrix: low stakes — and the boundary, at every timescale
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_stakes
def test_a_wanting_that_moves_in_days_is_not_worth_a_days_interruption():
    """Matrix: *low stakes*. **The ordinary refusal.**

    Being wrong about a routine that moves in days is felt for a day, and so is
    the interruption. Below the bar, the constitution's remedy is to hold the
    claim as provisional rather than to ask.
    """
    weighed = stakes(a_belief(), loops=a_loop(timescale=Timescale.DAYS))
    assert weighed.worth_asking is False
    assert weighed.reason == BELOW_THE_BAR
    assert weighed.cost_days == 1 and weighed.interruption_days == 1


@pytest.mark.cap4_stakes
@pytest.mark.parametrize("scale", list(Timescale), ids=[s.value for s in Timescale])
def test_one_interruption_answers_differently_for_every_timescale(scale):
    """**The bar is derived per wanting, not chosen once.**

    The same question against the same interruption gives four different
    answers, one per scale — which is what makes this a comparison rather than
    a threshold somebody picked. A single global bar would be right for one kind
    of wanting and wrong for every other, silently.
    """
    weighed = stakes(a_belief(), loops=a_loop(timescale=scale))
    assert weighed.cost_days == PERIOD_DAYS[scale]
    assert weighed.worth_asking is (PERIOD_DAYS[scale] > INTERRUPTION_DAYS)


@pytest.mark.cap4_stakes
def test_the_interruption_is_read_from_the_ledgers_own_table():
    """Not a literal. Both sides of the comparison are one unit from one source,
    which is what stops the two halves drifting into different scales."""
    assert INTERRUPTION_DAYS == PERIOD_DAYS[Timescale.DAYS]


@pytest.mark.cap4_stakes
@pytest.mark.cap4_structure
def test_the_interruption_is_derived_in_the_code_and_not_only_in_the_comment():
    """The value check above passes with ``INTERRUPTION_DAYS = 1`` typed as a
    literal, because one *is* what the table holds — review verified that, with
    the CI step's own comment naming the derivation.

    So the derivation is asserted structurally: ``stakes.py`` must subscript
    ``PERIOD_DAYS``. The same shape as the ``marks_day`` case below — assert
    that the borrowed thing is actually reached, not merely that the numbers
    agree today.
    """
    tree = ast.parse((ROOT / "half/trust/stakes.py").read_text(encoding="utf-8"))
    subscripted = {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
    }
    assert "PERIOD_DAYS" in subscripted, (
        "the interruption is typed rather than read from the open-loop table; "
        "both sides of the comparison must be one unit from one source"
    )


@pytest.mark.cap4_stakes
def test_exactly_one_interruption_is_still_below_the_bar():
    """The boundary, pinned on the quiet side — the same ``>`` convention
    ``timescale.silence`` and ``choose.touchable`` use, rather than a second
    convention for the same comparison."""
    assert Stakes(cost_days=INTERRUPTION_DAYS).worth_it is False
    assert Stakes(cost_days=INTERRUPTION_DAYS + 1).worth_it is True


@pytest.mark.cap4_stakes
def test_a_belief_on_no_wanting_is_below_the_bar():
    """There is no period over which being wrong is felt, so the cost cannot be
    shown to exceed one interruption. Held as provisional; nothing borrowed."""
    assert stakes(a_belief(loop=None), loops=a_loop()).reason == NO_WANTING


@pytest.mark.cap4_stakes
def test_a_belief_on_a_wanting_the_ledger_does_not_hold_is_below_the_bar():
    assert stakes(a_belief(loop="unknown-loop"), loops=a_loop()).reason == NO_WANTING


@pytest.mark.cap4_stakes
@pytest.mark.parametrize(
    "state",
    [s for s in LoopState if s not in LIVE_STATES] + ["a-later-builds-state"],
    ids=lambda s: str(s),
)
def test_a_finished_or_unrecognised_wanting_is_below_the_bar(state):
    """``ledger.silent``'s and ``touchable``'s own filter, asked here for the
    same reason: acting wrongly on a wanting that has stopped running costs
    nothing that is still running, and a later build's state is not something
    to interrupt somebody over."""
    assert stakes(a_belief(), loops=a_loop(state=state)).reason == FINISHED


@pytest.mark.cap4_stakes
@pytest.mark.parametrize(
    "timescale", [None, "fortnights"], ids=["none", "unreadable"],
)
def test_a_wanting_with_no_readable_period_is_below_the_bar(timescale):
    """The cost has no unit, and nothing here borrows one from a loop it is
    nothing like — the same refusal ``timescale.period_days`` makes."""
    assert stakes(a_belief(), loops=a_loop(timescale=timescale)).reason == NO_PERIOD


@pytest.mark.cap4_stakes
@pytest.mark.parametrize("subject", [None, "b_1", 7, []], ids=["none", "str", "int", "list"])
def test_something_that_is_not_a_belief_record_has_nothing_to_be_wrong_about(subject):
    assert stakes(subject, loops=a_loop()).reason == NO_SUBJECT


@pytest.mark.cap4_stakes
def test_every_reason_the_stakes_rule_gives_is_one_of_the_closed_set():
    """A caller counting refusals counts constants, never a message — an
    exception message quotes the value that caused it, and here that is a
    record out of a main's own ledger (AD-22)."""
    seen = {
        stakes(subject, loops=table).reason
        for subject in (None, a_belief(loop=None), a_belief(), a_belief(loop="nope"))
        for table in (
            a_loop(), a_loop(timescale=None), a_loop(timescale="fortnights"),
            a_loop(state=LoopState.ACHIEVED), a_loop(timescale=Timescale.YEARS),
        )
    } - {None}
    assert seen and seen <= STAKE_REASONS
    assert STAKE_REASONS == {NO_SUBJECT, NO_WANTING, FINISHED, NO_PERIOD,
                             BELOW_THE_BAR}


@pytest.mark.cap4_stakes
def test_the_same_belief_and_the_same_ledger_answer_identically_twice():
    """Pure: same input, same output, always (AD-30). No clock is involved on
    either side, so the answer is not even a function of time."""
    table = a_loop(timescale=Timescale.YEARS)
    assert len({stakes(a_belief(), loops=table) for _ in range(20)}) == 1


@pytest.mark.cap4_stakes
def test_a_malformed_loop_table_costs_one_question_and_never_raises():
    """The caller is on a turn's own path: losing the main's reply over a
    malformed loop entry is worse than losing one question, and *"we could not
    tell"* has a correct answer here, which is not to ask."""
    for table in (None, {}, {"swim-weekly": None}, {"swim-weekly": "advancing"}):
        assert stakes(a_belief(), loops=table).worth_asking is False


# ═════════════════════════════════════════════════════════════════════════════
# structure: the balance has nowhere to be stored
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap4_structure
def test_the_fold_has_nowhere_to_keep_a_balance(store):
    """**The structural half of AD-30 for this story**, and the one a
    behavioural case cannot give: a stored counter replays perfectly, so no
    round-trip assertion would ever see it. What sees it is that ``State`` has
    no field to put one in.

    A field added here is a deliberate edit with a reviewer on it — and it
    would be the counter story 4 refused for salience and story 9c refused for
    decay, one layer lower down.
    """
    import dataclasses

    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01")
    an_ask(store, t="2026-09-01T10:00Z")
    names = {f.name for f in dataclasses.fields(store.fold())}
    assert names == {"beliefs", "tensions", "loops", "expunged", "expunged_loops",
                     "ceiling", "crisis", "aftercare", "schedule", "touches",
                     "spoke"}


@pytest.mark.cap4_structure
def test_the_derived_view_holds_no_spend_and_no_count(store):
    """A spend leaves nothing in SQLite: not a row, not a governance key, not a
    number. So there is no derived value that could be behind the log, which is
    what a crash between ``Store.append``'s write and its rebuild produces."""
    a_favour(store, t="2026-09-01T03:00Z", day="2026-09-01")
    an_ask(store, t="2026-09-01T10:00Z")
    dumped = store.state().canonical_json()
    assert "asked" not in dumped and "q_1" not in dumped
    assert store.fold().canonical_json() == dumped


def code_names(path: Path) -> set[str]:
    """Every identifier, attribute and string literal the **code** uses.

    Lifted in shape from ``tests/test_nagging.py``'s ``names_read_by``, with
    docstrings removed first — a prose scan over these modules fails on their
    own explanation of the rule, which is the shape a guard takes when it reads
    words instead of code. String literals are kept because
    ``getattr(store, "state")`` walks past a name scan.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            found.add(node.name.split(".")[-1])
            if node.asname:
                found.add(node.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstrings:
                found.add(node.value)
    return found


@pytest.mark.cap4_structure
def test_the_balance_reads_the_log_and_never_the_derived_view():
    """Asserted structurally rather than by behaviour. ``half/trust/balance.py``
    may not name SQLite, a store, a connection or the derived view: a balance
    read from there is a favour spent twice on the one occasion nobody tests
    for, and it would replay correctly every time.

    Read over the **code**, not the prose. This module's own docstring explains
    the failure it is written against — so a scan for the word ``Store`` fires
    on the explanation, which is exactly how a guard ends up matching sentences
    instead of behaviour.
    """
    reached = code_names(ROOT / "half/trust/balance.py")
    forbidden = {"sqlite3", "state", "read_state", "Store", "conn", "rebuild",
                 "db", "cursor", "execute"}
    assert not reached & forbidden, (
        f"half/trust/balance.py reaches {sorted(reached & forbidden)}; the "
        f"balance is a fold over the log, which is the only authority (AD-3)"
    )


@pytest.mark.cap4_structure
def test_the_scan_that_says_so_catches_the_line_it_exists_for(tmp_path):
    """A guard nobody has run against the mutation it forbids is a guard nobody
    knows the reach of. This is that mutation."""
    bypass = tmp_path / "balance.py"
    bypass.write_text(
        '"""Prose may say Store and sqlite3 and rebuild freely."""\n'
        "def balance(store):\n    return store.state().ceiling\n",
        encoding="utf-8",
    )
    assert code_names(bypass) & {"state", "Store", "sqlite3"} == {"state"}


#: Methods that put something into a main's store. Matched as **calls**, never
#: as names: ``balance.py`` has a parameter called ``record``, and a name scan
#: reported reading one as writing one — which is the false positive that makes
#: a guard get deleted rather than fixed.
WRITES = frozenset({"record", "append", "expunge", "expunge_bodies", "rebuild",
                    "execute", "executescript", "claim_day", "note_transition",
                    "note_pass"})


def writing_calls(path: Path) -> set[str]:
    """Every write-shaped method ``path`` actually calls.

    ``opened.record(...)`` is caught wherever ``opened`` came from, which is the
    hole the substring ``store.record(`` left open — review reached a second
    store through ``from half.store import store as _second`` and neither the
    import list nor the substring saw it. ``list.append`` is excluded by name
    because it is not a store write and reporting it is how the previous
    version of this gate went wrong; a log append reaches
    ``BeliefLog.append``, whose *import* is closed separately.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "append" and isinstance(node.func.value, ast.Name):
            # ``unique.append(ask)`` and friends: a local list, not a log.
            continue
        if node.func.attr in WRITES:
            found.add(node.func.attr)
    return found


@pytest.mark.cap4_structure
def test_the_writing_scan_catches_a_store_reached_by_any_name(tmp_path):
    """The bypass review wrote, and the local-list false positive that made the
    earlier gate unusable — both run against the scan that replaced them."""
    bypass = tmp_path / "shadow.py"
    bypass.write_text(
        "from half.store import store as _second\n"
        "def shadow_spend(root, main_id, *, t, question, about):\n"
        "    held = []\n"
        "    held.append(question)\n"
        "    with _second.Store(root / main_id) as opened:\n"
        "        opened.record('asked', f'qa_{t}', t)\n",
        encoding="utf-8",
    )
    assert writing_calls(bypass) == {"record"}


@pytest.mark.cap4_structure
def test_nothing_in_the_trust_package_writes_to_a_log_or_calls_a_model():
    """AD-3 and AD-19. The pure half returns values and the composition reaches
    the log through the registry's own narrow door, so a second writer is not
    merely absent — there is no name for one in the package.

    **Read as resolved imports and as code names, never as file text.** The
    substring version this replaces was walked twice over: ``opened.record(``
    is not the substring ``store.record(``, and the modules' own docstrings
    name the very failures they are written against, so a prose scan is a scan
    that fires on explanations and misses code. ``resolved_imports`` and
    ``code_names`` are the same predicates the door and balance scans use.
    """
    from tests.test_unasked import CLOSED, resolved_imports

    for path in sorted((ROOT / "half/trust").rglob("*.py")):
        reached = resolved_imports(path)
        offending = sorted(
            name for name in reached
            if any(name == root or name.startswith(f"{root}.")
                   for root in (*CLOSED, "anthropic", "httpx", "socket",
                                "sqlite3", "half.model"))
        )
        assert not offending, f"{path.name} imports {offending}"
        assert not writing_calls(path), (
            f"{path.name} writes: {sorted(writing_calls(path))}"
        )


@pytest.mark.cap4_structure
def test_the_stakes_rule_cannot_consult_a_balance():
    """**The order of the two gates, made structural.**

    Stakes decide whether a question is worth asking at all; the favour decides
    whether it may be asked now. Reversed, a large balance buys a worthless
    question. ``half/trust/stakes.py`` is not given a balance and cannot import
    one, so reversing the order takes a new import rather than a moved line.
    """
    tree = ast.parse((ROOT / "half/trust/stakes.py").read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert "half.trust.balance" not in imported
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        arg.arg
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for arg in [*node.args.args, *node.args.kwonlyargs]
    }
    assert not names & {"balance", "Balance", "unspent", "spendable", "earned"}, (
        "the stakes rule can see the currency; a large balance would buy a "
        "worthless question"
    )


@pytest.mark.cap4_structure
def test_the_delivered_fact_is_story_tens_and_not_a_second_one():
    """*A favour is delivered, not endorsed.* ``delivered`` reads story 10's own
    reader and story 10's own field rather than re-deriving either: a second
    reading of *"a message reached the main"* is a second answer, and the two
    would drift on exactly the record that matters."""
    tree = ast.parse((ROOT / "half/trust/balance.py").read_text(encoding="utf-8"))
    imported = {
        f"{node.module}.{alias.name}"
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "half.surface.touch.marks_day" in imported
    assert "half.store.records.SENT" in imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "marks_day" in called, "the reader is imported and not used"
