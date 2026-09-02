"""CAP-11: the three states, and that none of them is inferred (story 12).

The whole of this file is one rule: *the attribution is never guessed*. Three
things could break it and each is covered from both sides —

**Reading the op instead of the stamp.** A bare ``retract`` is *not yet known*,
and an implementation that fell back to the op would answer *the main changed*
for it. Every case that reads an attribution is swept over **every correction
op crossed with every stamp combination**, including the ones the append gate
refuses, so the answer has to come from the stamps or the sweep fails. That
crossing is the boundary: without it a fixture where the op and the stamp always
agree would pass on an implementation that read either.

**Writing a stamp nobody asked for.** ``fields_for`` is asserted to produce an
*empty* mapping for the unknown state, and the end-to-end case in
``tests/test_correction.py`` asserts the log line carries neither field. A test
that only checked "the right stamp is present" would pass on a build that wrote
both.

**Letting a record say two things at once.** The append gate refuses both stamps
together, a stamp on an op that contradicts it, a stamp on an erasure, and a
stamp nothing can parse — each with its own case, because the log is
append-only and every one of them would be permanent.

The fourth thing this file pins is what was *not* taken from graphiti:
``created_at`` and ``valid_at`` are not fields of any record, and a build that
added one would fail here rather than in review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from half.correction.attribute import (
    CAUSE_FOR_STAMP,
    OP_FOR_ATTRIBUTION,
    Attribution,
    attribution_for,
    attribution_of,
    fields_for,
    op_for,
)
from half.errors import CorrectionError
from half.store.ops import Op
from half.store.records import (
    CORRECTIONS,
    EXPIRED_AT,
    INVALID_AT,
    STAMP_FOR_OP,
    TARGET,
    make,
)

pytestmark = pytest.mark.cap11

ROOT = Path(__file__).resolve().parents[1]

NOW = "2026-09-01T12:00:00Z"
LATER = "2026-09-02T09:00:00Z"


def raw(op: Op, *, target="b_1", **fields):
    """A record's data as the log holds it, built without the append gate.

    Deliberately not through ``make``: half the crossings below are records the
    gate refuses, and the reading side has to answer for them anyway — a log
    written by another build reaches ``attribution_of`` exactly like this.
    """
    return {"t": NOW, "op": op.value, "id": "co_1", TARGET: target, **fields}


# ═════════════════════════════════════════════════════════════════════════════
# the three states, read off the stamps and never off the op
# ═════════════════════════════════════════════════════════════════════════════


#: Every correction op crossed with every stamp combination, and the answer the
#: **stamps** give. Written out here rather than computed from the module under
#: test, so an inverted mapping cannot satisfy it.
CROSSING = [
    (op, stamps, expected)
    for op in (Op.RETRACT, Op.REVISE, Op.EXPUNGE)
    for stamps, expected in (
        ({}, Attribution.NOT_YET_KNOWN),
        ({EXPIRED_AT: NOW}, Attribution.HALF_WAS_WRONG),
        ({INVALID_AT: NOW}, Attribution.MAIN_CHANGED),
        ({EXPIRED_AT: NOW, INVALID_AT: NOW}, Attribution.NOT_YET_KNOWN),
    )
]


@pytest.mark.parametrize(
    "op, stamps, expected", CROSSING,
    ids=[f"{op.value}-{'+'.join(sorted(s)) or 'bare'}" for op, s, _ in CROSSING],
)
def test_the_attribution_is_read_off_the_stamps_and_never_off_the_op(
    op, stamps, expected
):
    """Matrix: *the three states*, swept across the boundary that matters.

    Twelve crossings, and four of them are the whole point: a **bare** record of
    each op reads as *not yet known*, where reading the op would answer *the
    main changed* for ``retract`` and *Half was wrong* for ``revise``. The
    remaining eight prove the answer does not change when the op does.

    The both-stamps rows read as *not yet known* rather than as either cause: a
    record that answers both questions has answered neither, and choosing one
    here would be inventing a precedence rule for a state the append gate makes
    unreachable anyway.
    """
    assert attribution_of(raw(op, **stamps)) is expected


@pytest.mark.parametrize("value", ["yesterday", "2026-02-31", "2026-09-01", 5,
                                   None, True, ""],
                         ids=["prose", "no-such-day", "date-only", "number",
                              "none", "bool", "empty"])
def test_a_stamp_this_build_cannot_read_is_not_an_attribution(value):
    """A cause that reads as present and answers nothing is worse than an absent
    one: *not yet known* is a real state with a real consequence — Half may ask
    — and an unparseable stamp would silently take it away.

    The append gate refuses each of these before it is durable; this is the read
    side, which has to answer for a log written by something else.
    """
    assert attribution_of(raw(Op.REVISE, **{EXPIRED_AT: value})) is (
        Attribution.NOT_YET_KNOWN
    )
    assert attribution_of(raw(Op.RETRACT, **{INVALID_AT: value})) is (
        Attribution.NOT_YET_KNOWN
    )


@pytest.mark.parametrize("value", [None, 5, "not a record", [], object()],
                         ids=["none", "number", "string", "list", "object"])
def test_reading_a_non_record_is_the_unknown_state_rather_than_a_raise(value):
    """Never raises. This runs on the turn's own path, and an exception there
    would cost the main their reply over a value nothing wrote."""
    assert attribution_of(value) is Attribution.NOT_YET_KNOWN


def test_the_unknown_state_writes_no_field_at_all():
    """Matrix: *wrong, cause unstated*. **The case that fails if either cause is
    written.**

    Asserted as an equality against the empty mapping rather than as two
    absences, so a build that wrote both stamps — the shape a well-meaning
    "record everything we know" produces — fails here as loudly as one that
    picked a side.
    """
    assert fields_for(Attribution.NOT_YET_KNOWN, t=NOW) == {}


@pytest.mark.parametrize(
    "attribution, stamp",
    [(Attribution.HALF_WAS_WRONG, EXPIRED_AT),
     (Attribution.MAIN_CHANGED, INVALID_AT)],
    ids=["half-was-wrong", "main-changed"],
)
def test_a_known_cause_writes_exactly_its_own_stamp(attribution, stamp):
    """One field, the caller's instant, and nothing else. The round trip is
    asserted too: what ``fields_for`` writes is what ``attribution_of`` reads,
    so the two halves cannot drift to different spellings."""
    written = fields_for(attribution, t=NOW)
    assert written == {stamp: NOW}
    assert attribution_of({**raw(op_for(attribution)), **written}) is attribution


def test_the_unknown_state_is_appended_as_a_retract_and_owes_no_apology():
    """**The Ask-First resolution, pinned.**

    The three states needed a home and it is the timestamps, which leaves the op
    vocabulary untouched. So the unknown state has to be spelled as one of the
    three existing ops, and it is ``retract`` — the one that owes no apology
    (glossary) — carrying no stamp, so nothing in the record attributes the
    removal to anything.

    ``revise`` would be worse in the one direction that matters: it owes an
    apology, and apologising for something the main simply changed is the
    falsehood the design notes name.
    """
    assert OP_FOR_ATTRIBUTION[Attribution.NOT_YET_KNOWN] is Op.RETRACT
    assert OP_FOR_ATTRIBUTION[Attribution.HALF_WAS_WRONG] is Op.REVISE
    assert OP_FOR_ATTRIBUTION[Attribution.MAIN_CHANGED] is Op.RETRACT
    # And the op alone does not carry the cause: the two retracts differ only by
    # the stamp, which is exactly why the stamp is where the cause lives.
    assert fields_for(Attribution.NOT_YET_KNOWN, t=NOW) != fields_for(
        Attribution.MAIN_CHANGED, t=NOW
    )


def test_every_attribution_has_an_op_and_every_stamp_has_a_cause():
    """The two tables are total and agree with the store's own. A cause with no
    op is a state nothing can append; a stamp with no cause is a field the
    append gate allows and no reader understands."""
    assert set(OP_FOR_ATTRIBUTION) == set(Attribution)
    assert set(CAUSE_FOR_STAMP) == {EXPIRED_AT, INVALID_AT}
    assert set(CAUSE_FOR_STAMP.values()) == {
        Attribution.HALF_WAS_WRONG, Attribution.MAIN_CHANGED
    }
    # And the store agrees about which op may carry which stamp.
    assert STAMP_FOR_OP == {
        Op.REVISE: EXPIRED_AT, Op.RETRACT: INVALID_AT, Op.EXPUNGE: None,
    }
    assert set(STAMP_FOR_OP) == CORRECTIONS


# ═════════════════════════════════════════════════════════════════════════════
# matrix: attribution arrives later
# ═════════════════════════════════════════════════════════════════════════════


def test_a_later_message_settles_a_cause_the_first_one_did_not():
    """Matrix: *attribution arrives later*.

    The main says *"that's wrong"* — removed, cause unknown — and a follow-up
    says which it was. Both records stand in the log and the fold over them now
    carries the cause.
    """
    log = [raw(Op.RETRACT), raw(Op.REVISE, **{EXPIRED_AT: LATER})]
    assert attribution_for("b_1", [log[0]]) is Attribution.NOT_YET_KNOWN
    assert attribution_for("b_1", log) is Attribution.HALF_WAS_WRONG


def test_a_later_causeless_correction_does_not_unsettle_an_earlier_cause():
    """Saying nothing is not saying *unknown*.

    A second removal of an already-removed belief carries no stamp, and a fold
    that took the last record unconditionally would read it as the main
    withdrawing the cause they gave. The rule is *the last correction naming a
    cause wins*, which is a different sentence and is the one that is true.
    """
    log = [raw(Op.REVISE, **{EXPIRED_AT: NOW}), raw(Op.RETRACT)]
    assert attribution_for("b_1", log) is Attribution.HALF_WAS_WRONG


def test_a_reversal_appends_and_both_causes_survive_in_order():
    """Matrix: *reversal*. The main corrects the correction, and the later cause
    is the one that stands — while both records remain, because an append-only
    log keeps what a person once said about themselves."""
    log = [
        raw(Op.RETRACT, **{INVALID_AT: NOW}),
        raw(Op.REVISE, **{EXPIRED_AT: LATER}),
    ]
    assert attribution_for("b_1", log) is Attribution.HALF_WAS_WRONG
    assert attribution_for("b_1", list(reversed(log))) is Attribution.MAIN_CHANGED
    assert len(log) == 2


def test_a_cause_on_another_belief_is_not_this_beliefs_cause():
    """The fold is per target. Without this, one main's every correction would
    share whichever cause was recorded last anywhere in their log."""
    log = [raw(Op.REVISE, target="b_other", **{EXPIRED_AT: NOW})]
    assert attribution_for("b_1", log) is Attribution.NOT_YET_KNOWN
    assert attribution_for("b_other", log) is Attribution.HALF_WAS_WRONG


def test_a_stamp_on_a_record_that_is_not_a_correction_is_ignored():
    """An ``assert`` carrying an ``expired_at`` — which nothing writes, and
    which an unknown-field-preserving log can therefore hold — is not a cause.
    Only the three removing ops attribute anything."""
    log = [{"t": NOW, "op": Op.ASSERT.value, "id": "b_1", TARGET: "b_1",
            EXPIRED_AT: NOW}]
    assert attribution_for("b_1", log) is Attribution.NOT_YET_KNOWN


def test_folding_over_junk_answers_the_unknown_state_rather_than_raising():
    """Never raises: this reads a main's whole log on a turn's own path."""
    assert attribution_for("b_1", [None, 5, "x", {}, object()]) is (
        Attribution.NOT_YET_KNOWN
    )


# ═════════════════════════════════════════════════════════════════════════════
# the append gate: what may never become durable
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("op", sorted(CORRECTIONS, key=lambda o: o.value),
                         ids=lambda o: o.value)
def test_a_correction_may_not_carry_both_stamps(op):
    """Both at once says the belief stopped being true *and* was never true. The
    log is append-only, so it would say both for ever — and no reader could
    choose between them without inventing a precedence rule."""
    with pytest.raises(CorrectionError):
        make(op, "co_1", NOW, target="b_1",
             **{EXPIRED_AT: NOW, INVALID_AT: NOW})


@pytest.mark.parametrize(
    "op, stamp",
    [(Op.RETRACT, EXPIRED_AT), (Op.REVISE, INVALID_AT),
     (Op.EXPUNGE, EXPIRED_AT), (Op.EXPUNGE, INVALID_AT)],
    ids=["retract-carries-half-was-wrong", "revise-carries-main-changed",
         "expunge-carries-half-was-wrong", "expunge-carries-main-changed"],
)
def test_the_op_and_the_stamp_may_never_disagree(op, stamp):
    """A ``revise`` means Half was wrong and a ``retract`` means it did not, so
    the wrong stamp on either is a record whose two halves attribute the removal
    to different causes. An ``expunge`` attributes nothing at all: its body is
    tombstoned, and there is no claim left to have been wrong about."""
    with pytest.raises(CorrectionError):
        make(op, "co_1", NOW, target="b_1", **{stamp: NOW})


@pytest.mark.parametrize("value", ["yesterday", "2026-02-31", "2026-09-01"],
                         ids=["prose", "no-such-day", "date-only"])
def test_a_stamp_nothing_can_parse_is_refused_before_it_is_durable(value):
    """The same values ``attribution_of`` reads as *not yet known* are refused
    on the way in. Write strict, read tolerant: the gate stops this build
    writing one, and the reader costs one correction its cause rather than a
    main their whole store."""
    with pytest.raises(CorrectionError):
        make(Op.REVISE, "co_1", NOW, target="b_1", **{EXPIRED_AT: value})


@pytest.mark.parametrize("op", sorted(CORRECTIONS, key=lambda o: o.value),
                         ids=lambda o: o.value)
def test_a_correction_with_no_stamp_is_perfectly_valid(op):
    """The other half of the gate, and the one an over-strict version would
    break: *not yet known* is a state, not a missing value, so a bare correction
    is exactly as valid as an attributed one. Without this case, a gate that
    required a stamp would look like rigour."""
    record = make(op, "co_1", NOW, target="b_1")
    assert EXPIRED_AT not in record.data
    assert INVALID_AT not in record.data
    assert attribution_of(record.data) is Attribution.NOT_YET_KNOWN


@pytest.mark.parametrize(
    "op, stamp", [(Op.REVISE, EXPIRED_AT), (Op.RETRACT, INVALID_AT)],
    ids=["revise", "retract"],
)
def test_the_right_stamp_on_the_right_op_goes_through(op, stamp):
    """A gate that refused everything would pass every case above."""
    record = make(op, "co_1", NOW, target="b_1", **{stamp: NOW})
    assert record.data[stamp] == NOW


# ═════════════════════════════════════════════════════════════════════════════
# what was not taken from graphiti
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap11_structure
def test_the_other_two_graphiti_timestamps_are_not_fields_of_any_record():
    """``created_at`` is already every record's ``t``, and a second field for it
    is a second place for the log's own ordering to disagree with itself.
    ``valid_at`` — when a claim *became* true — is a fact nobody in this system
    supplies, and a field that would be empty on every record is a field that
    invites being filled with a guess.

    Asserted over the two packages that **define record shapes** — the store
    and the correction path — rather than over the whole tree. A tree-wide ban
    on two ordinary strings has no exemption route, and the first provider SDK
    or transport response carrying a ``created_at`` key would trip it, which is
    a guard that fails for a reason that has nothing to do with its rule.
    """
    for name in ("created_at", "valid_at"):
        for path in sorted(
            [*(ROOT / "half/store").rglob("*.py"),
             *(ROOT / "half/correction").rglob("*.py")]
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            found = [
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value == name
            ]
            assert not found, f"{path.name} names {name!r} as a record field"


@pytest.mark.cap11_structure
def test_the_attribution_reader_never_names_an_op_inside_its_own_body():
    """The rule, as a property of the code rather than of the twelve crossings
    above.

    ``attribution_of`` is the one function that answers *why did this belief
    leave*, and it may look at the two stamps and nothing else. An AST scan of
    its body rather than of the module, because ``attribution_for`` legitimately
    reads an op — it is deciding *which records are corrections at all*, which
    is a different question with a different answer for every op.
    """
    tree = ast.parse(
        (ROOT / "half/correction/attribute.py").read_text(encoding="utf-8")
    )
    body = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "attribution_of"
    )
    named = {
        node.attr for node in ast.walk(body) if isinstance(node, ast.Attribute)
    } | {
        node.id for node in ast.walk(body) if isinstance(node, ast.Name)
    } | {
        node.value for node in ast.walk(body)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not named & {"Op", "op", "RETRACT", "REVISE", "EXPUNGE",
                        "OP_FOR_ATTRIBUTION", "STAMP_FOR_OP"}, sorted(named)


@pytest.mark.cap11_structure
def test_the_op_scan_catches_the_line_it_exists_for(tmp_path):
    """A guard nobody has run against the mutation it forbids is a guard nobody
    knows the reach of.

    The mutation is the plausible one: fall back to the op when no stamp is
    there. This proves the scan above sees it — the same AST walk over a
    synthetic body that does exactly that.
    """
    bypass = tmp_path / "bypass.py"
    bypass.write_text(
        "def attribution_of(record):\n"
        "    if record.get('expired_at'):\n"
        "        return 'half_was_wrong'\n"
        "    return 'main_changed' if record['op'] == 'retract' else 'unknown'\n",
        encoding="utf-8",
    )
    tree = ast.parse(bypass.read_text(encoding="utf-8"))
    body = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "attribution_of"
    )
    named = {
        node.value for node in ast.walk(body)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert named & {"op", "retract"}, "the scan would not see the fallback"
