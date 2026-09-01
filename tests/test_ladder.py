"""CAP-10 and AD-28: the license ladder, and the ceiling that caps it.

Two rules from the constitution are made executable here, and they are the
whole reason this file exists:

* *"Half is structurally incapable of asserting anything about the main without
  a citation into its own evidence."*
* *"The danger of assertion is being unexpected, not being wrong."*

So every case below observes a **permission**, not a field. Asserting that
``belief["license"] == "assert"`` would pass just as well on the build where
`assert` was a string anyone could write; asserting that the claim reaches
``Context.quotable()`` — or the wire — cannot. Where a row is only visible end
to end (an actor's ceiling capping what a turn may say), it is driven through
the real runtime rather than through the ladder alone.

The bypass row is a static gate rather than a behavioural one, for the reason
AD-28 gives: the failure it prevents is a *future* surface forgetting to check,
and no behavioural test can be written against code nobody has written yet. The
gate is checked against a synthetic bypass of its own so that it cannot go
green having asserted nothing.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from half.actor.registry import ActorRegistry
from half.actor.runtime import Runtime
from half.channel.telegram import TelegramChannel
from half.context import License, build, resolve
from half.errors import CorruptLogError, LadderError
from half.governance import ladder
from half.governance.ladder import (
    FLOOR,
    RUNGS,
    TOP,
    Ceiling,
    QuarantineCandidate,
)
from half.retrieval.port import Candidate, Ranked
from half.retrieval.prefix import build_prefix
from half.store.ops import Op
from half.store.records import RESERVED
from half.store.store import Store
from tests.conftest import FakeTransport, msg, seed_belief

#: Deliberately no file-wide ``pytestmark``. The AD-28 marker is applied case
#: by case in the ceiling sections below, so the CI gate's collected count
#: measures the ceiling cases and nothing else — a file-wide marker would let
#: every one of them be deleted while the count stayed comfortably above its
#: floor on the CAP-10 half of the file.

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-31T09:00:00Z"

#: A claim distinctive enough that its arrival — or absence — on the wire is
#: unmistakable.
SAID = "has not flown a paraglider in three years"

#: The two things `assert` requires, together. Named once so that a case
#: removing *one* of them is visibly removing one of two.
RECEIPT = {"support": ["s_mail_1"]}
KNOWN = {"known_to_main": True}


def belief(**fields):
    """A folded belief record, as the log wrote it."""
    return {"id": "b_1", "subject": "self", "claim": SAID, "ledger": "revealed",
            **fields}


def cand(record, claim=SAID, ident=None):
    return Candidate(id=ident or record.get("id", "b_1"), claim=claim, prefix="",
                     bm25=None, belief=record)


def quotable(record, *, ceiling=None):
    """What Half may actually *state* about this belief. The permission, not
    the field: this is the only door out of a context to belief text."""
    return build(Ranked(beliefs=(cand(record),)), now=NOW, ceiling=ceiling).quotable()


# -- the rungs themselves ----------------------------------------------------


def test_the_ladder_has_exactly_three_rungs_weakest_first():
    """A fourth rung, or a reordering, is an Ask First change — so it is pinned
    rather than left to be noticed."""
    assert RUNGS == (License.BEHAVE, License.ASK, License.ASSERT)
    assert FLOOR is License.BEHAVE
    assert TOP is License.ASSERT
    assert [ladder.height(r) for r in RUNGS] == [0, 1, 2]


def test_combining_two_rungs_can_only_ever_lower():
    """There is no operation in the module that returns the stronger of two."""
    for one in RUNGS:
        for other in RUNGS:
            assert ladder.height(ladder.weaker(one, other)) == min(
                ladder.height(one), ladder.height(other)
            )


def test_the_context_layer_and_the_ladder_name_the_same_rungs():
    """``half.context.License`` is re-exported, not redefined — an ``is``
    comparison across the two spellings has to keep holding."""
    assert License is ladder.License


# -- matrix: default, and malformed ------------------------------------------


def test_a_belief_with_no_license_resolves_to_behave_and_is_never_quotable():
    """Matrix: default."""
    record = belief()
    assert resolve(record, ceiling=None) is License.BEHAVE
    assert quotable(record) == ()


@pytest.mark.parametrize(
    "value",
    [None, "", "  ", "shout", "ASSERT", "Assert", "assert!", 3, 3.5, True,
     ["assert"], {"rung": "assert"}, object()],
    ids=["null", "empty", "blank", "unknown", "upper", "title", "stray", "int",
         "float", "bool", "list", "dict", "object"],
)
def test_an_unknown_or_malformed_license_resolves_to_behave_without_raising(value):
    """Matrix: malformed. Never `assert`, and never an exception — ``resolve``
    sits on the reply path ahead of the append that records the main's message,
    so a raise costs them both the answer and the message."""
    record = belief(license=value, **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=None) is License.BEHAVE
    assert quotable(record) == ()


@pytest.mark.parametrize("record", [None, "assert", 42, ["license"], object()],
                         ids=["none", "str", "int", "list", "object"])
def test_a_belief_that_is_not_a_record_resolves_to_behave_without_raising(record):
    assert resolve(record, ceiling=None) is License.BEHAVE
    assert ladder.own_rung(record) is License.BEHAVE


def test_a_license_survives_surrounding_whitespace():
    record = belief(license=" assert ", **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=None) is License.ASSERT


# -- matrix: the two `assert` preconditions ----------------------------------


@pytest.mark.parametrize(
    "support",
    [None, [], (), "", "   ", [""], ["   "], [None], [42], 0, False, {}, {"s": 1}],
    ids=["missing", "empty-list", "empty-tuple", "empty-str", "blank-str",
         "list-of-empty", "list-of-blank", "list-of-none", "list-of-int",
         "zero", "false", "empty-dict", "dict"],
)
def test_an_assert_belief_with_no_receipt_is_refused_and_never_quotable(support):
    """Matrix: assert, no receipt. *"Half is structurally incapable of
    asserting anything about the main without a citation into its own
    evidence."* Refused below `assert`, and its text is not quotable."""
    record = belief(license="assert", support=support, **KNOWN)
    rung = resolve(record, ceiling=None)
    assert rung is not License.ASSERT
    assert quotable(record) == ()


@pytest.mark.parametrize(
    "known",
    [None, False, 0, "", "yes", "true", "2026-06-01", 1, ["told"], {}],
    ids=["missing", "false", "zero", "empty", "yes", "true-str", "date", "one",
         "list", "dict"],
)
def test_an_assert_belief_the_main_does_not_know_about_is_refused(known):
    """Matrix: assert, unknown to main. *"The danger of assertion is being
    unexpected, not being wrong."* Being correct is not sufficient, and a
    permission-granting field is read strictly: only an explicit ``True``."""
    record = belief(license="assert", known_to_main=known, **RECEIPT)
    rung = resolve(record, ceiling=None)
    assert rung is not License.ASSERT
    assert quotable(record) == ()


def test_a_refused_assert_may_still_be_asked():
    """*"An unsupported claim may be asked, never asserted."* The demotion
    costs Half the right to state the claim, not the right to raise it — and
    `ask` material still carries no wording into a context."""
    unsupported = belief(license="assert", loop="fly-again", **KNOWN)
    assert resolve(unsupported, ceiling=None) is License.ASK

    context = build(Ranked(beliefs=(cand(unsupported),)), now=NOW, ceiling=None)
    assert context.quotable() == ()
    assert [q.id for q in context.questions] == ["b_1"]
    assert SAID not in context.render()


def test_a_belief_with_both_preconditions_resolves_to_assert_and_is_quotable():
    """Matrix: assert, both met. The positive control the rest of the file
    depends on — without it every refusal above could be passing for the wrong
    reason."""
    record = belief(license="assert", **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=None) is License.ASSERT
    assert quotable(record) == (SAID,)


def test_a_bare_string_support_is_a_receipt():
    """A log that wrote ``support="s_1"`` cited a source. Refusing to read it
    would not be the safe direction — it is a receipt Half holds and cannot
    see."""
    assert ladder.has_receipt({"support": "s_mail_1"})
    record = belief(license="assert", support="s_mail_1", **KNOWN)
    assert resolve(record, ceiling=None) is License.ASSERT


def test_neither_precondition_alone_is_enough():
    """Two *independent* things, stated separately because they fail
    separately."""
    assert resolve(belief(license="assert"), ceiling=None) is not License.ASSERT
    assert resolve(belief(license="assert", **RECEIPT),
                   ceiling=None) is not License.ASSERT
    assert resolve(belief(license="assert", **KNOWN),
                   ceiling=None) is not License.ASSERT
    assert resolve(belief(license="assert", **RECEIPT, **KNOWN),
                   ceiling=None) is License.ASSERT


# -- matrix: inference alone never promotes ----------------------------------


@pytest.mark.parametrize("independent", [0, 1, 2, 3, 10, 100, 10_000])
def test_corroboration_accumulating_without_the_main_never_promotes(independent):
    """Matrix: inference alone. No threshold exists, so there is no count at
    which a belief promotes itself — *"promotion is an event involving the
    main."*"""
    record = belief(license="behave", independent=independent,
                    last_corroborated="2026-08-30", **RECEIPT)
    assert resolve(record, ceiling=None) is License.BEHAVE
    assert quotable(record) == ()

    asked = belief(license="ask", independent=independent, **RECEIPT)
    assert resolve(asked, ceiling=None) is License.ASK


def test_the_ladder_reads_no_corroboration_field_at_all():
    """The stronger form of the row above: a count cannot influence a rung
    because nothing in the module reads one. A behavioural test can only cover
    the counts it happened to try."""
    source = (ROOT / "half/governance/ladder.py").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    for field in ("independent", "last_corroborated", "salience", "bm25"):
        assert f'"{field}"' not in body and f"'{field}'" not in body, (
            f"the ladder reads {field!r}; Half's own inference never licenses "
            "a higher rung"
        )


def test_promotion_without_an_acknowledgement_is_refused_at_any_count():
    for independent in (0, 1, 5, 1_000):
        record = belief(license="ask", independent=independent, **RECEIPT)
        with pytest.raises(LadderError):
            ladder.promote(record, to=License.ASSERT, acknowledged=False)
        with pytest.raises(LadderError):
            ladder.promote(record, to=License.ASSERT, acknowledged=1)
        with pytest.raises(LadderError):
            ladder.promote(record, to=License.ASSERT, acknowledged="yes")


def test_promotion_to_assert_without_a_receipt_is_refused_even_when_acknowledged():
    record = belief(license="ask", **KNOWN)
    with pytest.raises(LadderError):
        ladder.promote(record, to=License.ASSERT, acknowledged=True)


def test_a_promotion_that_does_not_raise_the_rung_is_refused():
    """A "promotion" that lowers is a caller confused about which it is doing;
    demotion is always permitted and has its own path."""
    record = belief(license="ask", **RECEIPT, **KNOWN)
    for target in (License.ASK, License.BEHAVE):
        with pytest.raises(LadderError):
            ladder.promote(record, to=target, acknowledged=True)


def test_a_rung_that_is_not_a_rung_is_refused_rather_than_folded_downward():
    """``rung_of`` folds an unreadable *stored* license to `behave`. An
    unreadable **argument** is a caller's typo, and folding it would be a
    silent demotion to whichever rung the typo happened to land on."""
    record = belief(license="behave", **RECEIPT)
    for bad in ("bahave", "ASSERT", "", 2, None, ["ask"]):
        with pytest.raises(LadderError):
            ladder.promote(record, to=bad, acknowledged=True)
        with pytest.raises(LadderError):
            ladder.demote(record, to=bad)


# -- matrix: the promotion event, and replay ---------------------------------


def test_a_promotion_carries_every_field_forward_and_records_the_acknowledgement():
    record = belief(license="ask", loop="fly-again", topics=["paragliding"],
                    independent=2, **RECEIPT)
    fields = ladder.promote(record, to=License.ASSERT, acknowledged=True)

    assert fields["license"] == "assert"
    assert fields["known_to_main"] is True
    assert fields["claim"] == SAID
    assert fields["loop"] == "fly-again"
    assert fields["topics"] == ["paragliding"]
    assert fields["support"] == ["s_mail_1"]
    assert not RESERVED & fields.keys(), (
        "the record's own structure belongs to the append, not to the belief"
    )
    # The permission, not the field: the promoted record is now quotable and
    # the one it was built from still is not.
    assert quotable({**record, **fields}) == (SAID,)
    assert quotable(record) == ()


def test_an_acknowledgement_earns_only_the_rung_it_was_given_for():
    """Matrix: ask acknowledgement.

    The main permitting Half to *ask* about something is not the main knowing
    Half *holds* it. Recording an ask-level acknowledgement as ``known_to_main``
    would leave a receipt as the only thing between a question and a statement,
    which collapses two deliberately independent preconditions into one — and a
    receipt is the half Half can give itself.
    """
    record = belief(license="behave", **RECEIPT)
    asked = {**record, **ladder.promote(record, to=License.ASK, acknowledged=True)}

    assert resolve(asked, ceiling=None) is License.ASK
    assert not ladder.known_to_main(asked), (
        "an acknowledgement to ask pre-satisfied the precondition for asserting"
    )
    # The permission, not the field: it is a question candidate, not content,
    # and it stays one however much evidence accumulates behind it.
    assert quotable(asked) == ()
    assert quotable({**asked, "independent": 99}) == ()

    # And the assert-level acknowledgement, which is a different event, does
    # record it — otherwise the precondition could never be satisfied at all.
    stated = {**asked, **ladder.promote(asked, to=License.ASSERT, acknowledged=True)}
    assert ladder.known_to_main(stated)
    assert quotable(stated) == (SAID,)


def test_promoting_to_assert_still_needs_its_own_acknowledgement():
    """The step from `ask` to `assert` is refused without one, so the two
    events cannot be collapsed from the other direction either."""
    record = belief(license="behave", **RECEIPT)
    asked = {**record, **ladder.promote(record, to=License.ASK, acknowledged=True)}
    with pytest.raises(LadderError):
        ladder.promote(asked, to=License.ASSERT, acknowledged=False)


def test_promotion_and_resolution_give_one_answer_about_the_current_rung():
    """Matrix: effective vs stated.

    A belief stating `assert` with no receipt resolves to `ask`. Comparing a
    promotion against the *stated* field made that belief unpromotable — the
    refusal read "assert -> assert is not a promotion", which is both wrong and
    misdirecting, and the only repair was an undocumented demote-then-promote.
    """
    stated_high = belief(license="assert", **KNOWN)  # no receipt
    assert resolve(stated_high, ceiling=None) is License.ASK
    assert ladder.own_rung(stated_high) is License.ASK

    # Refused for the true reason — the missing receipt — not for a rung
    # comparison against a field nobody acts on.
    with pytest.raises(LadderError, match="citation"):
        ladder.promote(stated_high, to=License.ASSERT, acknowledged=True)

    # With the receipt supplied the belief is already on `assert` — the field
    # and the preconditions now agree — so ``promote`` refuses it as *not a
    # promotion*, which is the same answer ``resolve`` gives. That agreement is
    # the point: there is no state in which one of them says `ask` and the
    # other says `assert`.
    supported = {**stated_high, **RECEIPT}
    assert resolve(supported, ceiling=None) is License.ASSERT
    with pytest.raises(LadderError, match="not a promotion"):
        ladder.promote(supported, to=License.ASSERT, acknowledged=True)

    # And a demotion is measured against the same answer: this belief is on
    # `ask`, so demoting it *to* `ask` lowers nothing.
    with pytest.raises(LadderError):
        ladder.demote(stated_high, to=License.ASK)
    assert resolve({**stated_high, **ladder.demote(stated_high, to=License.BEHAVE)},
                   ceiling=None) is License.BEHAVE


def test_a_promotion_is_an_append_and_the_original_record_is_untouched():
    record = belief(license="ask", **RECEIPT)
    before = json.dumps(record, sort_keys=True)
    ladder.promote(record, to=License.ASSERT, acknowledged=True)
    assert json.dumps(record, sort_keys=True) == before, (
        "a license change is an append, never an edit (AD-3)"
    )


def test_a_log_of_promotions_and_demotions_replays_to_identical_licenses(tmp_path):
    """Matrix: replay. Rebuilt from the log alone, every license is what it was
    — so a license is something the log says, not something a derived store
    remembers (AD-3, AD-4, AD-30)."""
    root = tmp_path / "mains"
    store = Store(root / "vidit", prefix=build_prefix)

    t = "2026-06-01T00:00:00Z"
    seed_belief(store, "b_promoted", t, subject="self", claim=SAID,
                ledger="revealed", rung=License.ASK, support=["s_1"],
                loop="fly-again")
    seed_belief(store, "b_demoted", t, subject="self", claim="swims on Tuesdays",
                ledger="revealed", rung=License.ASSERT, support=["s_2"],
                loop="swim")
    seed_belief(store, "b_quiet", t, subject="self", claim="reads before bed",
                ledger="revealed", loop="sleep")

    beliefs = store.state().beliefs
    store.record(Op.ASSERT, "b_promoted", "2026-07-01T00:00:00Z",
                 **ladder.promote(beliefs["b_promoted"], to=License.ASSERT,
                                  acknowledged=True))
    store.record(Op.ASSERT, "b_demoted", "2026-07-02T00:00:00Z",
                 **ladder.demote(beliefs["b_demoted"], to=License.BEHAVE))

    def licenses(state):
        return {i: resolve(b, ceiling=None) for i, b in state.beliefs.items()}

    before_state = store.state()
    before = licenses(before_state)
    assert before == {
        "b_promoted": License.ASSERT,
        "b_demoted": License.BEHAVE,
        "b_quiet": License.BEHAVE,
    }
    canonical = before_state.canonical_json()

    store.close()
    store.db_path.unlink()
    assert not store.db_path.exists()

    after = store.rebuild()
    store.close()
    assert licenses(after) == before
    assert after.canonical_json() == canonical


def test_a_promoted_belief_is_quotable_only_after_the_append(tmp_path):
    """The same row observed as a permission, on the live retrieval path."""
    from half.retrieval.rank import Retriever

    root = tmp_path / "mains"
    with Store(root / "vidit", prefix=build_prefix) as store:
        seed_belief(store, "b_1", "2026-06-01T00:00:00Z", subject="self",
                    claim=SAID, ledger="revealed", rung=License.ASK,
                    support=["s_1"], loop="fly-again")

        def context():
            return build(Retriever(store=store).retrieve("xyzzy", now=NOW),
                         now=NOW, ceiling=None)

        assert context().quotable() == ()

        record = store.state().beliefs["b_1"]
        store.record(Op.ASSERT, "b_1", "2026-07-01T00:00:00Z",
                     **ladder.promote(record, to=License.ASSERT, acknowledged=True))
        assert context().quotable() == (SAID,)


# -- matrix: demotion --------------------------------------------------------


def test_demotion_is_always_permitted_and_applies_immediately():
    """Matrix: demotion. No acknowledgement, no receipt, no precondition of any
    kind — nothing is owed for saying less."""
    record = belief(license="assert", **RECEIPT, **KNOWN)
    assert quotable(record) == (SAID,)

    demoted = {**record, **ladder.demote(record, to=License.BEHAVE)}
    assert resolve(demoted, ceiling=None) is License.BEHAVE
    assert quotable(demoted) == ()

    stepped = {**record, **ladder.demote(record, to=License.ASK)}
    assert resolve(stepped, ceiling=None) is License.ASK
    assert quotable(stepped) == ()


def test_a_demotion_that_does_not_lower_the_rung_is_refused():
    record = belief(license="ask", **RECEIPT, **KNOWN)
    for target in (License.ASK, License.ASSERT):
        with pytest.raises(LadderError):
            ladder.demote(record, to=target)


# -- matrix: quarantine ------------------------------------------------------


@pytest.mark.parametrize(
    "flag", [True, "a wound", 1, ["why"], {"since": "2026-06"}, 0.5],
    ids=["true", "reason", "int", "list", "dict", "float"],
)
def test_a_quarantined_belief_is_pinned_at_behave_whatever_its_license_says(flag):
    """Matrix: quarantined. A quarantine flag this build cannot interpret is a
    quarantine flag — the failure mode of misreading it has to be the safe
    one."""
    record = belief(license="assert", quarantined=flag, **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=None) is License.BEHAVE
    assert quotable(record) == ()


def test_an_explicit_false_is_not_a_quarantine():
    record = belief(license="assert", quarantined=False, **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=None) is License.ASSERT


def test_promotion_of_a_quarantined_belief_is_refused_by_every_path():
    """Matrix: quarantined -> promotion refused. Permanent: the pin is a field,
    and no function in the module clears it."""
    record = belief(license="ask", quarantined=True, **RECEIPT, **KNOWN)
    for target in (License.ASK, License.ASSERT):
        with pytest.raises(LadderError):
            ladder.promote(record, to=target, acknowledged=True)

    # And the reading path agrees, under every ceiling.
    for ceiling in (None, Ceiling(), Ceiling(License.ASSERT), Ceiling(License.ASK)):
        assert resolve(record, ceiling=ceiling) is License.BEHAVE


def test_nothing_in_the_ladder_clears_a_quarantine():
    """Permanence is the absence of a function, so that is what is asserted."""
    exported = set(dir(ladder))
    for name in ("unquarantine", "lift", "clear_quarantine", "unpin"):
        assert name not in exported, f"ladder exposes {name}; the pin is permanent"

    record = belief(license="assert", quarantined=True, **RECEIPT, **KNOWN)
    fields = ladder.quarantine(
        record, candidate=QuarantineCandidate("b_1", "went silent"), answered=True
    )
    assert ladder.quarantined({**record, **fields})


@pytest.mark.ad28
def test_an_ordinary_append_that_omits_the_flag_does_not_unpin(tmp_path):
    """Matrix: quarantine persists.

    The verified defect this replaced: the ladder refused to clear a
    quarantine, but the *fold* replaced the belief wholesale, so re-stating it
    without repeating the flag unpinned it and the belief went back to
    `assert`. Permanence that survives one record is not permanence, and no
    amount of care in the writing half could have supplied it — the enforcement
    has to be where the record is folded.
    """
    root = tmp_path / "mains"
    store = Store(root / "vidit", prefix=build_prefix)
    seed_belief(store, "b_1", "2026-06-01T00:00:00Z", subject="self", claim=SAID,
                ledger="revealed", rung=License.ASSERT, support=["s_1"],
                quarantine="went from daily to zero overnight")
    assert resolve(store.state().beliefs["b_1"], ceiling=None) is License.BEHAVE

    # The most ordinary operation there is: the belief re-stated, correctly,
    # with a fresh corroboration and no mention of the quarantine.
    store.record(Op.ASSERT, "b_1", "2026-08-01T00:00:00Z", subject="self",
                 claim=SAID, ledger="revealed", independent=4,
                 last_corroborated="2026-08-01", **ladder.admitted(support=["s_1"]))

    record = store.state().beliefs["b_1"]
    assert ladder.quarantined(record), "an ordinary append unpinned the belief"
    assert resolve(record, ceiling=None) is License.BEHAVE

    store.close()
    store.db_path.unlink()
    replayed = store.rebuild()
    store.close()
    assert ladder.quarantined(replayed.beliefs["b_1"]), "replay reproduced it cleared"
    assert resolve(replayed.beliefs["b_1"], ceiling=None) is License.BEHAVE


def test_inference_produces_a_candidate_and_pins_nothing():
    """Matrix: quarantine candidate. *"Half may detect a candidate by inference
    but never applies quarantine on inference alone — it asks."*"""
    records = [belief(id=f"b_{i}", license="ask", **RECEIPT) for i in range(3)]
    candidates = [
        ladder.quarantine_candidate(r, reason="daily to zero overnight")
        for r in records
    ]

    assert all(isinstance(c, QuarantineCandidate) for c in candidates)
    assert [c.belief_id for c in candidates] == ["b_0", "b_1", "b_2"]
    for record in records:
        assert "quarantined" not in record, "inference pinned a belief"
        assert not ladder.quarantined(record)
        assert resolve(record, ceiling=None) is License.ASK


def test_a_candidate_for_an_unusable_belief_is_simply_absent():
    assert ladder.quarantine_candidate(belief(id="b_1"), reason="  ") is None
    assert ladder.quarantine_candidate(belief(id=""), reason="why") is None
    assert ladder.quarantine_candidate("not a record", reason="why") is None
    already = belief(id="b_1", quarantined=True)
    assert ladder.quarantine_candidate(already, reason="why") is None


def test_applying_a_quarantine_requires_both_a_candidate_and_an_answer():
    """The rule as a signature rather than as a check somebody has to
    remember: neither argument has a default."""
    record = belief(license="assert", **RECEIPT, **KNOWN)
    candidate = ladder.quarantine_candidate(record, reason="went quiet")

    with pytest.raises(LadderError):
        ladder.quarantine(record, candidate=candidate, answered=False)
    with pytest.raises(LadderError):
        ladder.quarantine(record, candidate=None, answered=True)
    with pytest.raises(LadderError):
        ladder.quarantine(record, candidate=QuarantineCandidate("b_other", "x"),
                          answered=True)
    with pytest.raises(TypeError):
        ladder.quarantine(record)  # neither argument may be omitted


def test_an_applied_quarantine_pins_the_belief_and_survives_a_replay(tmp_path):
    root = tmp_path / "mains"
    store = Store(root / "vidit", prefix=build_prefix)
    seed_belief(store, "b_1", "2026-06-01T00:00:00Z", subject="self",
                claim=SAID, ledger="revealed", rung=License.ASSERT,
                support=["s_1"], loop="fly-again")

    record = store.state().beliefs["b_1"]
    assert resolve(record, ceiling=None) is License.ASSERT

    candidate = ladder.quarantine_candidate(record, reason="went silent")
    store.record(Op.ASSERT, "b_1", "2026-07-01T00:00:00Z",
                 **ladder.quarantine(record, candidate=candidate, answered=True))
    assert resolve(store.state().beliefs["b_1"], ceiling=None) is License.BEHAVE

    store.close()
    store.db_path.unlink()
    replayed = store.rebuild()
    store.close()
    assert resolve(replayed.beliefs["b_1"], ceiling=None) is License.BEHAVE


# -- matrix: the ceiling -----------------------------------------------------
#
# Everything from here to the purity section is AD-28 and carries the marker
# individually. The file's earlier half is CAP-10 — the rungs, the two
# preconditions, quarantine, promotion — and marking it `ad28` too would let
# the CI gate's count stay comfortably above its floor with every ceiling case
# deleted.


@pytest.mark.ad28
def test_a_ceiling_at_behave_caps_an_assert_belief():
    """Matrix: ceiling at `behave`."""
    record = belief(license="assert", loop="fly-again", **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=Ceiling(License.BEHAVE)) is License.BEHAVE
    assert quotable(record, ceiling=Ceiling(License.BEHAVE)) == ()
    # The positive control: the same belief, uncapped, is quotable.
    assert quotable(record) == (SAID,)


@pytest.mark.ad28
def test_a_ceiling_at_ask_caps_an_assert_belief_to_ask():
    record = belief(license="assert", loop="fly-again", **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=Ceiling(License.ASK)) is License.ASK

    context = build(Ranked(beliefs=(cand(record),)), now=NOW,
                    ceiling=Ceiling(License.ASK))
    assert context.quotable() == ()
    assert [q.id for q in context.questions] == ["b_1"]


@pytest.mark.ad28
def test_a_raised_ceiling_never_promotes_a_belief():
    """Matrix: ceiling raised. A ceiling is a minimum taken against the
    belief's own rung, so lifting it can only stop subtracting."""
    quiet = belief(license="behave", loop="fly-again")
    for ceiling in (Ceiling(License.ASSERT), Ceiling(License.ASK), None):
        assert resolve(quiet, ceiling=ceiling) is License.BEHAVE
        assert quotable(quiet, ceiling=ceiling) == ()

    asked = belief(license="ask", loop="fly-again", **RECEIPT)
    assert resolve(asked, ceiling=Ceiling(License.ASSERT)) is License.ASK


@pytest.mark.ad28
def test_no_ceiling_configured_resolves_to_the_belief_s_own_license():
    """Matrix: ceiling default. ``None``, ``Ceiling(None)`` and a
    default-constructed ``Ceiling`` are one statement — this main has no cap.

    ``Ceiling(None)`` matters because that is what hydration builds for a main
    whose log holds no ceiling record: a main who has never been capped must
    not be born capped by the fail-closed parse.
    """
    for record, expected in (
        (belief(license="assert", **RECEIPT, **KNOWN), License.ASSERT),
        (belief(license="ask", **RECEIPT), License.ASK),
        (belief(license="behave"), License.BEHAVE),
        (belief(license="assert", **KNOWN), License.ASK),   # refused, not capped
    ):
        assert resolve(record, ceiling=None) is expected
        assert resolve(record, ceiling=Ceiling()) is expected
        assert resolve(record, ceiling=Ceiling(None)) is expected
    assert not Ceiling().capping
    assert not Ceiling(None).capping
    assert Ceiling(License.BEHAVE).capping


@pytest.mark.ad28
def test_one_ceiling_caps_every_belief_regardless_of_its_own_value():
    """AD-28's wording exactly: *one ceiling per actor caps every belief
    regardless of its own value*."""
    records = (
        belief(id="b_a", license="assert", loop="fly-again", **RECEIPT, **KNOWN),
        belief(id="b_b", license="ask", loop="buy-land", **RECEIPT),
        belief(id="b_c", license="behave", loop="sleep"),
    )
    # Claims disjoint from each other and from every rendered identifier, so
    # that nothing here is dropped by AD-18's echo rule instead of by the
    # ceiling — which is what this case is about.
    claims = ("alpha bravo", "charlie delta", "echo foxtrot")
    ranked = Ranked(
        beliefs=tuple(cand(r, claim=c) for r, c in zip(records, claims))
    )

    context = build(ranked, now=NOW, ceiling=Ceiling(License.BEHAVE))
    assert context.quotable() == ()
    assert not context.questions, "a capped `ask` may not still become a question"
    assert [d.id for d in context.directives] == ["b_a", "b_b", "b_c"]


@pytest.mark.ad28
def test_a_capped_claim_s_wording_cannot_leak_through_another_line():
    """A capped belief is withheld exactly as an ordinary `behave` belief is,
    so lowering the ceiling cannot leak a claim sideways inside somebody
    else's sentence (AD-18)."""
    capped = belief(id="b_1", license="assert", loop="fly-again",
                    **RECEIPT, **KNOWN)
    echo = belief(id="b_2", license="behave", loop="fly-again",
                  topics=["has not flown a paraglider in three years"])
    ranked = Ranked(beliefs=(cand(capped), cand(echo, claim="something else")))

    rendered = build(ranked, now=NOW, ceiling=Ceiling(License.BEHAVE)).render()
    assert SAID not in rendered
    assert "paraglider in three" not in rendered


@pytest.mark.ad28
def test_a_ceiling_only_ever_lowers_and_returns_a_new_one():
    ceiling = Ceiling()
    lowered = ceiling.lowered_to(License.ASK)
    assert lowered.rung is License.ASK
    assert ceiling.rung is TOP, "lowering mutated the ceiling it was called on"
    assert lowered.lowered_to(License.ASSERT).rung is License.ASK, "it raised"
    assert lowered.lowered_to(License.BEHAVE).rung is License.BEHAVE


@pytest.mark.ad28
def test_raising_a_ceiling_is_a_named_exception_that_demands_a_reason():
    """Matrix: a ceiling has one way up, and it is not a setter.

    Lowering is a safety act and needs no justification. Raising ends a
    suppression something deliberate put in place — thirty days of aftercare,
    typically — so it is named, it is reasoned, and the reason reaches the log.
    """
    capped = Ceiling(License.BEHAVE)
    for empty in ("", "   ", None, 0, True):
        with pytest.raises(LadderError):
            capped.released(because=empty)
    with pytest.raises(TypeError):
        capped.released()  # no default reason

    released = capped.released(because="aftercare ended on day 31")
    assert released.rung is TOP
    assert capped.rung is License.BEHAVE, "releasing mutated the original"

    partial = capped.released(because="stepping back up", to=License.ASK)
    assert partial.rung is License.ASK


@pytest.mark.ad28
def test_assigning_the_rung_on_a_handed_out_ceiling_is_refused():
    """Matrix: ceiling raised by assignment.

    ``license_ceiling`` hands a caller the real object. If that object had a
    settable field, every guard above would be one line away from irrelevant.
    """
    ceiling = Ceiling(License.BEHAVE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ceiling.rung = License.ASSERT
    assert ceiling.rung is License.BEHAVE
    assert not hasattr(ceiling, "lower"), "a mutating setter came back"
    assert not hasattr(ceiling, "restore")


@pytest.mark.ad28
@pytest.mark.parametrize("value", ["shout", "", 42, ["assert"]],
                         ids=["unknown", "empty", "int", "list"])
def test_a_ceiling_this_build_cannot_read_caps_everything(value):
    """Fail-closed in the restrictive direction: a ceiling exists to restrict,
    so an unreadable one must not be an absent one. ``None`` is excluded — it
    is the one value that means *never set*, not *unreadable*."""
    ceiling = Ceiling(value)
    assert ceiling.rung is License.BEHAVE
    record = belief(license="assert", **RECEIPT, **KNOWN)
    assert resolve(record, ceiling=ceiling) is License.BEHAVE


# -- matrix: the ceiling, through the actor and onto the wire ----------------


def seeded(root, main="vidit"):
    """One `assert` belief, reachable and quotable, for one main."""
    with Store(root / main, prefix=build_prefix) as store:
        seed_belief(store, "b_say", "2026-06-01T00:00:00Z", subject="self",
                    claim=SAID, ledger="revealed", loop="fly-again",
                    rung=License.ASSERT, support=["s_1"])
    return root


def run_turn(root, text="xyzzy plugh", *, registry=None, main="vidit",
             address="123", message_id="1"):
    """One real turn, end to end, on a registry the caller may pre-configure."""
    transport = FakeTransport([msg(text=text, message_id=message_id,
                                   chat_id=address)])
    channel = TelegramChannel(transport=transport, mains={address: main})
    registry = registry or ActorRegistry(root)
    asyncio.run(Runtime(channel=channel, registry=registry).run())
    registry.close()
    return "".join(sent for _, sent in transport.sent)


@pytest.mark.ad28
def test_an_actor_carries_one_ceiling_beside_its_strands_and_retrieval(tmp_path):
    registry = ActorRegistry(tmp_path / "mains")
    ceiling = registry.license_ceiling("vidit")
    assert isinstance(ceiling, Ceiling)
    assert ceiling.rung is TOP, "a main begins with no cap"
    assert registry.license_ceiling("other").rung is TOP
    registry.close()


@pytest.mark.ad28
def test_only_the_ceiling_decides_whether_the_claim_reaches_the_wire(tmp_path):
    """The end-to-end row, structured so the ceiling is the *only* difference.

    The version this replaced ran two turns against one store, and passed for
    an unrelated reason: turn one recorded the main's own message as a belief,
    which on turn two displaced the seeded belief by exact bm25 match, so
    nothing was quotable whatever the ceiling said. Setting ``ceiling=None`` in
    the runtime — deleting AD-28's whole effect on every real turn — left it
    green. Two fresh roots and one turn each is what makes the assertion mean
    what it says.
    """
    uncapped_root = seeded(tmp_path / "uncapped")
    capped_root = seeded(tmp_path / "capped")

    uncapped = run_turn(uncapped_root)

    registry = ActorRegistry(capped_root)
    registry.lower_ceiling("vidit", License.BEHAVE, t="2026-06-02T00:00:00Z",
                           because="aftercare")
    capped = run_turn(capped_root, registry=registry)

    assert SAID in uncapped, "the positive control must reach the wire"
    assert capped, "a capped ceiling must not cost the main a reply (AD-27)"
    assert SAID not in capped


@pytest.mark.ad28
def test_one_main_s_ceiling_does_not_cap_another_main_s(tmp_path):
    """Per main, not per worker — the failure a single shared switch caused
    once already."""
    root = tmp_path / "mains"
    seeded(root, "vidit")
    seeded(root, "other")

    registry = ActorRegistry(root)
    registry.lower_ceiling("vidit", License.BEHAVE, t="2026-06-02T00:00:00Z",
                           because="aftercare")
    sent = run_turn(root, registry=registry, main="other", address="9")

    assert SAID in sent


# -- matrix: the ceiling is durable ------------------------------------------


@pytest.mark.ad28
def test_a_lowered_ceiling_survives_eviction(tmp_path):
    """Matrix: ceiling survives eviction.

    The verified defect: with the cap held only in memory, serving other mains
    evicted the capped actor and its rehydration came back at `assert`. At the
    default capacity of 256 eviction is routine rather than exceptional, so
    this un-suppressed a main mid-aftercare on nothing more than a busy worker.
    """
    root = tmp_path / "mains"
    for main in ("vidit", "a", "b"):
        seeded(root, main)

    registry = ActorRegistry(root, capacity=1)
    registry.lower_ceiling("vidit", License.BEHAVE, t="2026-06-02T00:00:00Z",
                           because="aftercare")

    # Serving two other mains at capacity 1 evicts vidit's actor entirely.
    registry.retrieval_switch("a")
    registry.retrieval_switch("b")
    assert not registry.is_hydrated("vidit"), (
        "the fixture must actually evict, or this asserts nothing"
    )

    assert registry.license_ceiling("vidit").rung is License.BEHAVE
    registry.close()


@pytest.mark.ad28
def test_a_lowered_ceiling_survives_a_restart(tmp_path):
    """Matrix: ceiling survives restart. A whole new registry over the same
    directory — the process-restart case — still finds the main capped."""
    root = seeded(tmp_path / "mains")

    first = ActorRegistry(root)
    first.lower_ceiling("vidit", License.BEHAVE, t="2026-06-02T00:00:00Z",
                        because="aftercare")
    first.close()

    second = ActorRegistry(root)
    assert second.license_ceiling("vidit").rung is License.BEHAVE
    second.close()

    # And on the wire, not only in the object.
    assert SAID not in run_turn(root, message_id="9")


@pytest.mark.ad28
def test_a_ceiling_replays_from_the_log_after_the_derived_view_is_deleted(
    tmp_path,
):
    """The ceiling is folded state, not a column somebody remembered to write:
    delete the database, replay, and the cap is still there (AD-3, AD-4)."""
    root = seeded(tmp_path / "mains")
    registry = ActorRegistry(root)
    registry.lower_ceiling("vidit", License.BEHAVE, t="2026-06-02T00:00:00Z",
                           because="aftercare")
    registry.close()

    with Store(root / "vidit", prefix=build_prefix) as store:
        before = store.state().canonical_json()
        assert store.state().ceiling == "behave"
    (root / "vidit" / "half.db").unlink()

    with Store(root / "vidit", prefix=build_prefix) as replayed:
        assert replayed.state().ceiling == "behave"
        assert replayed.state().canonical_json() == before


@pytest.mark.ad28
def test_a_ceiling_record_with_no_rung_is_fatal_rather_than_a_no_op(tmp_path):
    """A ceiling record the fold cannot read must not silently do nothing:
    that leaves a main uncapped while the log says they were capped."""
    from half.store.records import make

    root = tmp_path / "mains"
    store = Store(root / "vidit", prefix=build_prefix)
    store.log.append(make(Op.CEILING, "c_1", "2026-06-02T00:00:00Z", because="x"))
    with pytest.raises(CorruptLogError):
        store.fold()
    store.close()


@pytest.mark.ad28
def test_releasing_a_ceiling_is_durable_and_reasoned(tmp_path):
    """Raising is as durable as lowering — a release that lived only in memory
    would silently re-cap the main on the next rehydration."""
    root = seeded(tmp_path / "mains")
    registry = ActorRegistry(root)
    registry.lower_ceiling("vidit", License.BEHAVE, t="2026-06-02T00:00:00Z",
                           because="aftercare")
    # Two calls, because story 6c made a release one rung. A single call that
    # put everything back is the restore CAP-12 forbids, and there is no longer
    # an expression for it here.
    registry.release_ceiling("vidit", to=License.ASK, t="2026-07-05T00:00:00Z",
                             because="aftercare: the floor is past, one step")
    registry.release_ceiling("vidit", to=License.ASSERT, t="2026-07-19T00:00:00Z",
                             because="aftercare: the main asked for the mirror back")
    registry.close()

    assert ActorRegistry(root).license_ceiling("vidit").rung is TOP
    assert SAID in run_turn(root, message_id="9")

    reasons = [
        r.data.get("because") for r in Store(root / "vidit").log
        if r.op is Op.CEILING
    ]
    assert reasons == [
        "aftercare",
        "aftercare: the floor is past, one step",
        "aftercare: the main asked for the mirror back",
    ], "a ceiling outlives whoever set it; the log has to say why"


@pytest.mark.ad28
def test_lowering_to_a_rung_it_is_already_at_records_nothing(tmp_path):
    """An append says something happened. Nothing did."""
    root = seeded(tmp_path / "mains")
    registry = ActorRegistry(root)
    registry.lower_ceiling("vidit", License.BEHAVE, t="2026-06-02T00:00:00Z",
                           because="aftercare")
    registry.lower_ceiling("vidit", License.ASSERT, t="2026-06-03T00:00:00Z",
                           because="this cannot raise it")
    registry.close()

    records = [r for r in Store(root / "vidit").log if r.op is Op.CEILING]
    assert len(records) == 1
    assert ActorRegistry(root).license_ceiling("vidit").rung is License.BEHAVE


@pytest.mark.ad28
def test_reaching_an_actor_by_any_door_marks_it_recently_used(tmp_path):
    """The accessors hydrate; they must also touch the LRU and respect
    capacity, or an actor looks cold the moment it was needed and the registry
    grows past its bound for as long as nobody takes a turn."""
    root = tmp_path / "mains"
    for main in ("a", "b"):
        seeded(root, main)

    registry = ActorRegistry(root, capacity=2)
    registry.license_ceiling("a")
    registry.retrieval_switch("b")
    registry.license_ceiling("a")          # a is now the most recent
    registry.retrieval_switch("c")         # over capacity: the oldest goes
    assert registry.hydrated == ["a", "c"], registry.hydrated
    assert len(registry.hydrated) <= 2
    registry.close()


# -- matrix: the bypass, read side -------------------------------------------
#
# **Names are resolved, not matched.** The first version of this gate compared
# the spelling at the call site, so `from half.context.build import build` was
# caught and `from half.context import build` — the spelling this story's own
# package re-exports made the natural one — was not. A gate whose reach depends
# on which of two equivalent import lines the author wrote is not a gate. So
# every local name is resolved through its import, then through the package
# `__init__` re-exports, to the function it actually reaches.


def module_qualname(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def source_modules() -> list[tuple[str, Path]]:
    return [(module_qualname(p), p) for p in sorted((ROOT / "half").rglob("*.py"))]


def parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def reexports() -> dict[str, str]:
    """``half.context.resolve -> half.context.build.resolve``, and so on.

    Read off every ``__init__.py`` rather than listed, so that the next
    re-export is covered by the gate on the day it is written rather than on
    the day someone remembers this file exists.
    """
    aliases: dict[str, str] = {}
    for module, path in source_modules():
        if path.name != "__init__.py":
            continue
        package = module.removesuffix(".__init__")
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    exported = alias.asname or alias.name
                    aliases[f"{package}.{exported}"] = f"{node.module}.{alias.name}"
    return aliases


def canonical(name: str, aliases: dict[str, str]) -> str:
    """``name`` followed through the re-export chain to what it reaches."""
    seen: set[str] = set()
    while name in aliases and name not in seen:
        seen.add(name)
        name = aliases[name]
    return name


def ceiling_takers(aliases: dict[str, str]) -> set[str]:
    """Every function under ``half/`` declaring a keyword-only ``ceiling``.

    Discovered rather than listed, so the gate covers the next such function
    without anyone remembering to add it here.
    """
    found: set[str] = set()
    for module, path in source_modules():
        for node in ast.walk(parse(path)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                arg.arg == "ceiling" for arg in node.args.kwonlyargs
            ):
                found.add(canonical(f"{module}.{node.name}", aliases))
    return found


def bindings(tree: ast.AST, module: str, aliases: dict[str, str]) -> dict[str, str]:
    """Local name -> the ``half.*`` function or module it actually reaches."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] == "half":
                for alias in node.names:
                    bound[alias.asname or alias.name] = canonical(
                        f"{node.module}.{alias.name}", aliases
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "half":
                    key = alias.asname or alias.name.split(".")[0]
                    bound[key] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.setdefault(node.name, f"{module}.{node.name}")
    return bound


def called_name(node: ast.Call, bound: dict[str, str], aliases: dict[str, str]) -> str:
    """What ``node`` actually calls, or ``""``.

    Resolves an attribute *chain* — ``half.governance.ladder.own_rung`` reached
    through ``import half`` is the same call as ``own_rung`` reached through
    ``from half.governance import own_rung``, and a gate that sees only one of
    them tells the author which spelling to use.
    """
    parts: list[str] = []
    func: ast.expr = node.func
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return ""
    root = bound.get(func.id)
    if root is None:
        return ""
    return canonical(".".join([root, *reversed(parts)]), aliases)


def ceiling_omissions(
    source: str, module: str, takers: set[str], aliases: dict[str, str]
) -> list[str]:
    """Calls in ``source`` that resolve a license without a cap flowing in.

    Three failures, not one:

    * the keyword is absent — the caller forgot;
    * the keyword is a literal ``None`` — inside ``half/`` that is a surface
      declaring itself exempt from AD-28, which is the thing AD-28 forbids;
    * the call forwards ``**kwargs`` — which the first version accepted as
      satisfying the check, so ``resolve(b, **kw)`` passed while asserting
      nothing about whether ``kw`` held a ceiling.

    Returned rather than asserted so the gate can be run against synthetic
    bypasses and proved to catch each one.
    """
    tree = ast.parse(source)
    bound = bindings(tree, module, aliases)
    missed: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = called_name(node, bound, aliases)
        if target not in takers:
            continue
        where = f"{module}:{node.lineno} {target}"
        if any(kw.arg is None for kw in node.keywords):
            missed.append(f"{where} (forwarded **kwargs)")
            continue
        passed = [kw for kw in node.keywords if kw.arg == "ceiling"]
        if not passed:
            missed.append(f"{where} (no ceiling)")
        elif isinstance(passed[0].value, ast.Constant) and passed[0].value.value is None:
            missed.append(f"{where} (ceiling=None)")
    return missed


ALIASES = reexports()
TAKERS = ceiling_takers(ALIASES)


@pytest.mark.ad28
def test_the_bypass_gate_has_functions_to_guard():
    """An empty taker set makes the gate below pass having asserted nothing."""
    assert "half.context.build.resolve" in TAKERS
    assert "half.context.build.build" in TAKERS
    assert "half.governance.ladder.permitted" in TAKERS
    assert "half.actor.runtime.respond" in TAKERS
    assert len(TAKERS) >= 4, sorted(TAKERS)


@pytest.mark.ad28
def test_the_re_export_map_actually_resolves_this_package_s_own_aliases():
    """The gate's reach rests entirely on this map. If it were empty, every
    finding below would still pass and the package spellings would be blind."""
    assert canonical("half.context.build", ALIASES) == "half.context.build.build"
    assert canonical("half.context.resolve", ALIASES) == "half.context.build.resolve"
    assert (
        canonical("half.governance.own_rung", ALIASES)
        == "half.governance.ladder.own_rung"
    )


@pytest.mark.ad28
@pytest.mark.parametrize(
    "source",
    [
        # the spelling the first gate caught
        "from half.context.build import resolve\n"
        "def compose(b):\n    return resolve(b)\n",
        # the spelling this story's own re-exports made natural
        "from half.context import resolve\n"
        "def compose(b):\n    return resolve(b)\n",
        "from half.context import build\n"
        "def compose(r, now):\n    return build(r, now=now)\n",
        # aliased
        "from half.context.build import build as build_context\n"
        "def compose(r, now):\n    return build_context(r, now=now)\n",
        # through a module handle, at two depths
        "from half.governance import ladder\n"
        "def compose(b):\n    return ladder.permitted(b)\n",
        "import half.governance.ladder\n"
        "def compose(b):\n    return half.governance.ladder.permitted(b)\n",
        # keyword present, no cap behind it
        "from half.context import resolve\n"
        "def compose(b):\n    return resolve(b, ceiling=None)\n",
        # forwarded, asserting nothing
        "from half.context import resolve\n"
        "def compose(b, **kw):\n    return resolve(b, **kw)\n",
    ],
    ids=["direct", "reexported", "reexported-build", "aliased", "module-handle",
         "dotted", "literal-none", "forwarded"],
)
def test_the_bypass_gate_catches_every_spelling_of_the_bypass(source):
    """Matrix: bypass attempt, read. Each of these was verified to slip past an
    earlier version of this gate while the whole suite stayed green."""
    assert ceiling_omissions(source, "half.surfaces.new", TAKERS, ALIASES), source


@pytest.mark.ad28
def test_the_bypass_gate_passes_a_caller_that_hands_a_cap_on():
    correct = (
        "from half.context import resolve\n"
        "def compose(b, ceiling):\n    return resolve(b, ceiling=ceiling)\n"
    )
    assert not ceiling_omissions(correct, "half.surfaces.new", TAKERS, ALIASES)


@pytest.mark.ad28
def test_no_runtime_caller_resolves_a_license_outside_the_ceiling_path():
    """AD-28's ceiling is applied where licenses are resolved, so a surface
    that resolves one without it is the failure the invariant exists to
    prevent — and it fails the suite."""
    missed: list[str] = []
    for module, path in source_modules():
        missed += ceiling_omissions(
            path.read_text(encoding="utf-8"), module, TAKERS, ALIASES
        )
    assert not missed, f"license resolved without a ceiling: {missed}"


@pytest.mark.ad28
def test_resolving_without_a_ceiling_is_a_type_error_not_a_default():
    """The structural half, which no scan can be wrong about. ``build`` and
    ``respond`` are undefaulted too: a scan only catches the spellings it
    thought of, and this story's re-exports proved that set was incomplete."""
    record = belief(license="assert", **RECEIPT, **KNOWN)
    with pytest.raises(TypeError):
        resolve(record)
    with pytest.raises(TypeError):
        ladder.permitted(record)
    with pytest.raises(TypeError):
        build(Ranked(), now=NOW)


@pytest.mark.ad28
def test_only_the_context_builder_decides_a_rung():
    """Story 4b made ``resolve`` the single place a license becomes a decision.
    A second reader of the license field would be a second answer, and AD-28's
    ceiling would then cap only one of them.

    Resolved through the same name machinery as the gate above, because this
    test had both of that gate's holes: it read only bare ``ast.Name`` calls
    and only matched a literal ``half.governance.ladder.`` prefix, so
    ``ladder.own_rung(b)`` and ``from half.governance import own_rung`` both
    walked through it.
    """
    deciding = {
        f"half.governance.ladder.{name}"
        for name in ("permitted", "own_rung", "rung_of", "has_receipt",
                     "known_to_main", "quarantined", "cap", "weaker")
    }
    #: ``half/crisis/contacts.py`` reads ``known_to_main`` and nothing else in
    #: that set. It is not deciding a rung — it asks the one question this gate
    #: exists to keep single-answered: *has the main confirmed that Half holds
    #: this?* Story 6b may offer only a confirmed contact, and the alternative
    #: to reusing the primitive is a second reader of the same field with its
    #: own idea of what counts, which is exactly the drift this gate prevents.
    #: Reusing it means a contact cannot become offerable by a path a belief
    #: could not take. Nothing else about a rung is read there, and the writer
    #: gate below still forbids it spelling the field into a record.
    #: ``half/crisis/safetyplan.py`` reads ``quarantined`` and nothing else in
    #: that set, on the same terms. A plan the main pinned is the main saying
    #: leave this alone, and asking the ladder's own predicate is what stops a
    #: second reader of the pin arriving with its own idea of what counts —
    #: which is how a quarantined contact became a crisis door once already.
    #: No rung is decided there: a held document is not a claim Half is
    #: asserting, and the writer gate below still forbids it spelling a license
    #: field into a record.
    allowed = {"half/context/build.py", "half/crisis/contacts.py",
               "half/crisis/safetyplan.py"}
    offenders: list[str] = []
    for module, path in source_modules():
        relative = str(path.relative_to(ROOT))
        if relative.startswith("half/governance/") or relative in allowed:
            continue
        tree = parse(path)
        bound = bindings(tree, module, ALIASES)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = called_name(node, bound, ALIASES)
            if target in deciding:
                offenders.append(f"{relative}:{node.lineno} {target}")
            if isinstance(node.func, ast.Name) and node.func.id == "License" and (
                node.args
            ):
                # Parsing a stored value into a rung is the decision itself.
                offenders.append(f"{relative}:{node.lineno} License(...)")
    assert not offenders, f"a rung is decided outside the one place: {offenders}"


@pytest.mark.ad28
def test_the_rung_decider_gate_catches_a_second_reader():
    """The same non-vacuity proof the ceiling gate gets."""
    source = (
        "from half.governance import ladder\n"
        "def compose(b):\n    return ladder.own_rung(b)\n"
    )
    tree = ast.parse(source)
    bound = bindings(tree, "half.surfaces.new", ALIASES)
    calls = [
        called_name(n, bound, ALIASES)
        for n in ast.walk(tree) if isinstance(n, ast.Call)
    ]
    assert "half.governance.ladder.own_rung" in calls


# -- matrix: the bypass, write side ------------------------------------------
#
# The symmetric half, and the one the first round of this story was missing
# entirely. Gating readers alone leaves `assert` a field anyone can set — it
# raises the price from one field to three, which is not what "structurally
# incapable" means.


#: The fields that decide, or pin, what a belief may permit. Every one of them
#: is written by ``half.governance.ladder`` and by nothing else.
GOVERNED_FIELDS = frozenset({"license", "support", "known_to_main", "quarantined",
                             "rung"})

#: Where a governed field may legitimately be spelled into a record.
#: ``tests/conftest.py`` is the one sanctioned test writer, and it writes by
#: calling the ladder — a test that seeds `assert` by hand is doing exactly what
#: this story forbids, at test scale.
WRITERS_ALLOWED = ("half/governance/", "tests/conftest.py")

#: Functions that put fields into a log record.
RECORD_MAKERS = frozenset({
    "half.store.store.Store.record", "record", "make", "Record",
})


def governed_writes(source: str) -> list[str]:
    """Calls that spell a governed field straight into a record."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr if isinstance(node.func, ast.Attribute)
            else node.func.id if isinstance(node.func, ast.Name) else ""
        )
        if name not in RECORD_MAKERS:
            continue
        for keyword in node.keywords:
            if keyword.arg in GOVERNED_FIELDS:
                found.append(f"{node.lineno} {name}(..., {keyword.arg}=...)")
    return found


@pytest.mark.ad28
def test_the_writer_gate_catches_a_hand_written_assert():
    """The bypass the whole first round of this story permitted, written out.

    ``store.record(Op.ASSERT, ..., license="assert", support=["s_1"],
    known_to_main=True)`` was a legal append from anywhere, so `assert`
    remained a field anyone could set. Non-vacuity first, then the sweep.
    """
    bypass = (
        'store.record(Op.ASSERT, "b_1", t, claim="x", license="assert",\n'
        '             support=["s_1"], known_to_main=True)\n'
    )
    assert len(governed_writes(bypass)) == 3
    assert not governed_writes('store.record(Op.ASSERT, "b_1", t, claim="x")\n')
    assert governed_writes('make(Op.CEILING, "c_1", t, rung="behave")\n')


@pytest.mark.ad28
def test_nothing_outside_the_ladder_writes_a_license_field():
    """Matrix: bypass attempt, write.

    Symmetric with the read gate above and for the same reason: the ladder is
    where the rules are, so it must also be where the fields are written. A
    belief cannot be born at `assert` — ``ladder.admitted`` has no argument
    that would allow it — and cannot reach `assert` except through a promotion,
    which is an event involving the main.
    """
    offenders: list[str] = []
    for path in sorted([*(ROOT / "half").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]):
        relative = str(path.relative_to(ROOT))
        if relative.startswith(WRITERS_ALLOWED):
            continue
        for hit in governed_writes(path.read_text(encoding="utf-8")):
            offenders.append(f"{relative}:{hit}")
    assert not offenders, (
        "a governed field is written outside the ladder — `assert` is a field "
        f"anyone can set again: {offenders}"
    )


@pytest.mark.ad28
@pytest.mark.parametrize(
    "fields",
    [
        {"known_to_main": "yes"},
        {"known_to_main": 1},
        {"known_to_main": "2026-06-01"},
        {"support": 42},
        {"support": "s_1"},
        {"support": [1, 2]},
        {"quarantined": "a wound"},
        {"license": 3},
    ],
    ids=["known-str", "known-int", "known-date", "support-int", "support-str",
         "support-ints", "quarantine-str", "license-int"],
)
def test_a_permission_gating_field_is_validated_before_it_becomes_durable(
    store, fields
):
    """The log is append-only, so an unvalidated value that gates a permission
    is a durable one. ``license`` was always checked here; since story 5a these
    three decide the same question, and ``known_to_main="yes"`` reaching the
    log is a belief whose rung turns on a value nothing ever looked at.

    ``support`` as a bare string is refused *at the append* while
    ``has_receipt`` still reads one: a log written by another build must not
    cost Half a receipt it holds, and a record this build writes must not be
    ambiguous about its shape.
    """
    with pytest.raises(ValueError):
        store.record(Op.ASSERT, "b_1", "2026-06-01T00:00:00Z", claim="x", **fields)
    assert "b_1" not in store.state().beliefs


@pytest.mark.ad28
def test_a_belief_cannot_be_admitted_above_the_weakest_rung():
    """The writer gate is only worth having if the sanctioned path is narrow.
    ``admitted`` takes no rung, so there is no call that mints an `assert`."""
    assert ladder.admitted()["license"] == str(FLOOR)
    assert ladder.admitted(support=["s_1"])["license"] == str(FLOOR)
    assert "known_to_main" not in ladder.admitted(support=["s_1"])
    with pytest.raises(TypeError):
        ladder.admitted(rung=License.ASSERT)
    with pytest.raises(TypeError):
        ladder.admitted(License.ASSERT)


@pytest.mark.ad28
def test_the_one_sanctioned_test_writer_cannot_mint_an_unearned_assert(tmp_path):
    """``tests/conftest.py`` is exempt from the writer gate, so the exemption
    has to be worth granting.

    Without this, the gate is one edit from vacuous: rewriting ``seed_belief``
    to spell the fields in directly would leave every gate green while every
    test in the suite seeded `assert` by hand again. So the helper is pinned by
    the property that matters — it cannot produce a rung the ladder would have
    refused.
    """
    with Store(tmp_path / "vidit", prefix=build_prefix) as store:
        with pytest.raises(LadderError, match="citation"):
            seed_belief(store, "b_1", "2026-06-01T00:00:00Z", claim=SAID,
                        rung=License.ASSERT)  # no support

        earned = seed_belief(store, "b_2", "2026-06-01T00:00:00Z", claim=SAID,
                             rung=License.ASSERT, support=["s_1"])
        assert resolve(earned, ceiling=None) is License.ASSERT

        asked = seed_belief(store, "b_3", "2026-06-01T00:00:00Z", claim=SAID,
                            rung=License.ASK, support=["s_1"])
        assert resolve(asked, ceiling=None) is License.ASK
        assert not ladder.known_to_main(asked), (
            "seeding at `ask` pre-satisfied the precondition for asserting"
        )


@pytest.mark.ad28
def test_a_turn_records_the_main_s_message_at_the_weakest_rung(tmp_path):
    """The one production writer, observed as a permission rather than a
    field: whatever the main types, the belief it becomes is not quotable."""
    root = tmp_path / "mains"
    (root / "vidit").mkdir(parents=True)
    run_turn(root, text=SAID)

    with Store(root / "vidit", prefix=build_prefix) as store:
        recorded = [b for b in store.state().beliefs.values() if b["claim"] == SAID]
        assert recorded, "the turn recorded nothing"
        for record in recorded:
            assert resolve(record, ceiling=None) is License.BEHAVE
            assert quotable(record) == ()


# -- purity ------------------------------------------------------------------


GOVERNANCE_MODULES = sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "half/governance").rglob("*.py")
)

_AMBIENT_CALLS = {
    "now", "utcnow", "today", "time", "monotonic", "perf_counter",
    "random", "getenv", "urandom", "uuid4",
}


def test_the_purity_scans_have_modules_to_scan():
    assert "half/governance/ladder.py" in GOVERNANCE_MODULES, GOVERNANCE_MODULES


@pytest.mark.parametrize("relative", GOVERNANCE_MODULES)
def test_the_ladder_reads_no_clock_and_no_ambient_state(relative):
    """AD-30. A behavioural test cannot catch this: a ladder that read the
    clock would still resolve identically twice inside one second."""
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        node.func.id if isinstance(node.func, ast.Name) else ""
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert not called & _AMBIENT_CALLS, (
        f"{relative} calls {sorted(called & _AMBIENT_CALLS)}"
    )


@pytest.mark.parametrize("relative", GOVERNANCE_MODULES)
def test_the_ladder_calls_no_model_and_writes_nothing(relative):
    """AD-19 and AD-3: the writing half returns the *fields* of an append and
    the caller appends them, so nothing here touches the log or a model."""
    source = (ROOT / relative).read_text(encoding="utf-8")
    for forbidden in ("anthropic", "httpx", "socket", "store.record(",
                      "log.append(", "sqlite3"):
        assert forbidden not in source, f"{relative} reaches {forbidden}"


# Import purity is asserted in ``tests/test_purity.py``, which now lists
# ``half/governance/ladder.py`` among its PURE_MODULES. It is not repeated here:
# the copy that used to live in this file carried its own FORBIDDEN_ROOTS and
# had no alias case, so ``import time as t`` passed the local gate while
# failing the real one — a second copy of a rule is a weaker copy.


def test_resolving_twice_gives_the_same_answer():
    """Pure: same input, same output, always (AD-30)."""
    record = belief(license="assert", **RECEIPT, **KNOWN)
    ceiling = Ceiling(License.ASK)
    assert len({resolve(record, ceiling=ceiling) for _ in range(20)}) == 1
    assert len({resolve(record, ceiling=None) for _ in range(20)}) == 1
