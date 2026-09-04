"""CAP-5 story 15a: the four admission gates, one case per rule.

CAP-5 ends *"Admission gates (decision-relevance, durability, independence,
falsifiability) are individually testable"*, and until this story none of them
existed. This file is the *individually* half — the pure machinery, over
verdicts, with no provider anywhere.

Three things it refuses to do, because each would let it pass while the product
failed:

**It never asserts a refusal without saying which gate made it.** A case that
checked only *"no claim"* would pass for a gate that refused, a gate that could
not say, a gate that was never asked, and a bench with nobody equipped. Every
case here names the gate, and the two-gate case names both.

**It does not let one gate's case stand in for another's.** The gates share no
label — asserted — so a case that exercised the wrong one could not accidentally
be green.

**Its import-time guards each have a bypass case.** A module that refuses itself
is red everywhere at once and therefore *names* nothing: a reviewer reading that
build learns the tree is broken, not that three of CAP-5's four gates had
stopped being asked. So each guard is also driven under ``monkeypatch``, which
is red **by name** inside an otherwise green tree.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from half.derive import gates as gating
from half.derive.gates import (
    A_REQUEST,
    CAP5_GATES,
    CHECKABLE,
    DECISION_RELEVANCE,
    DURABILITY,
    DURABILITY_UNSURE,
    FALSIFIABILITY,
    FALSIFIABILITY_UNSURE,
    GATE_NAMES,
    GATES,
    INDEPENDENCE,
    INDEPENDENCE_UNSURE,
    LASTS,
    NOT_CHECKABLE,
    ONLY_A_REPLY,
    ONLY_NOW,
    RELEVANCE_UNSURE,
    STANDS_ALONE,
    WOULD_MATTER,
    WOULD_NOT_MATTER,
    Admission,
    admission,
    gate_named,
)
from half.errors import DeriveError


def all_admitting() -> dict[str, bool | None]:
    return {gate.name: True for gate in GATES}


# ═════════════════════════════════════════════════════════════════════════════
# the four gates CAP-5 names
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_admission
def test_cap5_s_four_gates_exist_and_each_one_names_itself():
    """The capability names four criteria and calls them individually testable.

    Asserted by **value** rather than by count, because a build that renamed one
    of them would still have four: what CAP-5 asks for is these four, and a
    ``relevance`` gate beside a ``decision-relevance`` one is two criteria
    nobody can trace back to the capability.
    """
    assert GATE_NAMES == (
        "decision-relevance", "durability", "independence", "falsifiability",
    )
    assert len(GATES) == CAP5_GATES
    for name in GATE_NAMES:
        assert gate_named(name) is not None
    assert gate_named("relevance") is None


@pytest.mark.cap5_admission
def test_a_message_worth_keeping_passes_every_gate():
    """*"I want to move to the farm next year"* — the matrix's first row.

    Admitted only when **all four** say yes, which is the other half of every
    refusing case below: a build that admitted on a majority would pass each of
    those and would still write ``ok`` into a main's ledger.
    """
    assert admission(all_admitting()) == Admission(admitted=True)


@pytest.mark.cap5_admission
def test_ok_is_refused_by_decision_relevance_and_that_gate_names_itself():
    """*"ok"* — the message this whole story is named after.

    The gate is named in the result rather than inferred from the absence of a
    claim, because absence is what a refusal, an unsure gate, an unreachable
    provider and an unequipped deployment all look like.
    """
    verdict = admission({**all_admitting(), DECISION_RELEVANCE.name: False})

    assert verdict.admitted is False
    assert verdict.refused_by == ("decision-relevance",)
    assert DECISION_RELEVANCE.verdict(WOULD_NOT_MATTER) is False


@pytest.mark.cap5_admission
def test_a_mood_is_refused_by_durability_and_that_gate_names_itself():
    """*"I'm tired today"* — AD-26's own line, as an admission gate.

    *"you've seemed down lately"* produced from a bad Tuesday is the failure the
    spine names, and this is where it is refused rather than where it is
    composed.
    """
    verdict = admission({**all_admitting(), DURABILITY.name: False})

    assert verdict.refused_by == ("durability",)
    assert DURABILITY.verdict(ONLY_NOW) is False
    assert DURABILITY.verdict(LASTS) is True


@pytest.mark.cap5_admission
def test_a_bare_reply_is_refused_by_independence_and_that_gate_names_itself():
    """*"yes"* after Half asked something.

    The glossary's *ten mentions of one fact in one thread is one support*, one
    level up: a message that is only an echo of what Half itself put in front of
    the main carries nothing of its own, whatever it appears to say.
    """
    verdict = admission({**all_admitting(), INDEPENDENCE.name: False})

    assert verdict.refused_by == ("independence",)
    assert INDEPENDENCE.verdict(ONLY_A_REPLY) is False
    assert INDEPENDENCE.verdict(STANDS_ALONE) is True


@pytest.mark.cap5_admission
def test_an_aphorism_is_refused_by_falsifiability_and_that_gate_names_itself():
    """*"life is strange"* — nothing would make it false, so it is a sentence
    rather than a claim, and a belief ledger that held it could never correct
    it."""
    verdict = admission({**all_admitting(), FALSIFIABILITY.name: False})

    assert verdict.refused_by == ("falsifiability",)
    assert FALSIFIABILITY.verdict(NOT_CHECKABLE) is False
    assert FALSIFIABILITY.verdict(CHECKABLE) is True


@pytest.mark.cap5_admission
def test_a_message_two_gates_refuse_names_both_and_never_only_the_first():
    """The row that makes the other four testable at all.

    A set of gates that stopped at the first refusal would leave every case
    above passing whether that gate worked or an earlier one refused first —
    and it would hide the fact an operator tuning this actually wants, which is
    that *decision-relevance and falsifiability* is a different message from
    *durability alone*.

    Asserted in CAP-5's own order, so a build that reported the refusals in
    whatever order a dictionary happened to iterate is red as well.
    """
    verdict = admission({
        DECISION_RELEVANCE.name: False,
        DURABILITY.name: True,
        INDEPENDENCE.name: True,
        FALSIFIABILITY.name: False,
    })

    assert verdict.refused_by == ("decision-relevance", "falsifiability")
    assert verdict.unsure == ()
    assert verdict.unanswered == ()


@pytest.mark.cap5_admission
def test_a_gate_that_cannot_say_is_kept_apart_from_one_that_refused():
    """Both leave no claim. They are not the same fact, and a build that folded
    them together would report a model that is honestly unsure as a model that
    said no — which is a measurement of how ambiguous somebody's life is,
    reported as a refusal rate."""
    verdict = admission({**all_admitting(), DURABILITY.name: None})

    assert verdict.admitted is False
    assert verdict.refused_by == ()
    assert verdict.unsure == ("durability",)


@pytest.mark.cap5_admission
def test_a_gate_that_never_answered_is_kept_apart_from_one_that_could_not_say():
    """The third of the three, and the one a suite is most likely to lose.

    A provider that is down and a model that is honestly unsure both produce no
    claim; only the first is an outage. ``unanswered`` is what makes *"the gate
    was never reached"* survive as a fact.
    """
    left_out = {name: True for name in GATE_NAMES if name != INDEPENDENCE.name}
    verdict = admission(left_out)

    assert verdict.admitted is False
    assert verdict.unsure == ()
    assert verdict.unanswered == ("independence",)


@pytest.mark.cap5_admission
def test_a_request_has_a_home_of_its_own_and_it_never_admits():
    """*"what did I say about the farm?"* — the hard case, with a label of its
    own.

    ``half.consolidate.judge``'s argument for ``cannot_both_be_true``, one
    capability over: a message addressed *to* Half is plainly relevant to the
    turn it arrived on and carries nothing worth holding afterwards, so a model
    with nowhere to put it has to answer ``would_not_matter`` to the message
    that feels most relevant — the answer it is least likely to give.

    What it must never do is admit, which is what this asserts.
    """
    assert A_REQUEST in DECISION_RELEVANCE.refuses
    assert DECISION_RELEVANCE.verdict(A_REQUEST) is False
    assert DECISION_RELEVANCE.verdict(WOULD_MATTER) is True
    # And it is the *only* gate with a fourth label, which is stated rather than
    # left as an asymmetry: no other gate has a case with that shape.
    assert [len(gate.refuses) for gate in GATES] == [2, 1, 1, 1]


# ═════════════════════════════════════════════════════════════════════════════
# what a gate may read, and what it may not
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap5_structure
def test_no_two_gates_share_a_label():
    """Four gates answering in one another's words is one wiring mistake away
    from a build where three of them are never asked anything — and a test
    double that answered a single shared triple would be green for all four.

    Asserted over the whole set rather than pairwise, so a fifth gate added
    later is covered by the same case.
    """
    seen: dict[str, str] = {}
    for gate in GATES:
        for label in gate.labels:
            assert label not in seen, (label, seen.get(label), gate.name)
            seen[label] = gate.name
    assert len(seen) == sum(len(gate.labels) for gate in GATES)


@pytest.mark.cap5_structure
def test_a_gate_reads_only_its_own_labels_and_never_guesses():
    """Nothing is coerced. Another gate's label, a stray full stop, a different
    normalisation and a non-string are all *no answer* rather than the nearest
    neighbour.

    The direction of that loss is the safe one: a near miss costs a claim, where
    a guess would write one.
    """
    assert DURABILITY.verdict(WOULD_MATTER) is None      # another gate's admit
    assert DURABILITY.verdict("lasts.") is None          # a stray full stop
    assert DURABILITY.verdict("LASTS") is None           # a different case
    assert DURABILITY.verdict(None) is None
    assert DURABILITY.verdict(7) is None
    assert DURABILITY.verdict(DURABILITY_UNSURE) is None  # its own *cannot say*


@pytest.mark.cap5_structure
def test_every_label_a_model_may_answer_is_defined_in_its_gate_s_instructions():
    """A label the model is never told about is one it can only pick by
    accident, and a label defined in another gate's instructions is one it will
    pick on the wrong question."""
    for gate in GATES:
        for label in gate.labels:
            assert any(label in block for block in gate.instructions), (
                gate.name, label,
            )
        for other in GATES:
            if other is gate:
                continue
            for label in other.labels:
                assert not any(label in block for block in gate.instructions), (
                    gate.name, label,
                )


@pytest.mark.cap5_admission
def test_no_gate_carries_a_rubric_about_how_a_message_is_written():
    """**Worldwide**, and asserted as a property of every gate rather than of
    the one somebody remembered.

    The message arrives in whatever the main writes. Every gate carries the same
    paragraph saying that how a thing is written is not part of its question —
    the objection ``half.context.channels`` records against an English-prose
    rule shipped worldwide — and none of them names a language, a locale or a
    script.
    """
    written = ("wording", "register", "politeness", "fluency")
    for gate in GATES:
        joined = " ".join(gate.instructions)
        assert "any language and in any script" in joined, gate.name
        for word in written:
            assert word in joined, (gate.name, word)
        for forbidden in ("English", "en-US", "locale", "Latin", "ASCII"):
            assert forbidden not in joined, (gate.name, forbidden)


@pytest.mark.cap5_admission
def test_admission_never_raises_on_anything_it_is_handed():
    """It runs on the turn's own path, after the reply has gone. A mapping this
    build cannot read is a message with no claim, never a turn that failed."""
    for odd in (None, {}, {"decision-relevance": "yes"}, {7: True},
                {"decision-relevance": None}):
        verdict = admission(odd)  # type: ignore[arg-type]
        assert isinstance(verdict, Admission)
        assert verdict.admitted is False
    assert admission("not a mapping").unanswered == GATE_NAMES  # type: ignore[arg-type]


# ═════════════════════════════════════════════════════════════════════════════
# the import-time guards, each with a bypass case
# ═════════════════════════════════════════════════════════════════════════════
#
# ``_check_constants`` runs at import, so every mutation of the data it guards
# is red everywhere at once — which *names* nothing. Each guard therefore also
# has a case that mutates the module under ``monkeypatch`` and asks it to accept
# itself, so the failure is red by name inside an otherwise green tree.


@dataclass(frozen=True, slots=True)
class Folding:
    """A gate that reads its own *cannot say* as a refusal.

    A duck rather than a ``replace`` of a real gate, because the mapping is on
    ``Gate.verdict`` and not in its data: a gate whose ``unsure`` label was moved
    into ``refuses`` is refused one guard earlier, for repeating a label, and
    the case would then be green for the wrong reason.
    """

    name: str
    admits: str
    refuses: tuple[str, ...]
    unsure: str
    instructions: tuple[str, ...]

    @property
    def labels(self) -> tuple[str, ...]:
        return (self.admits, *self.refuses, self.unsure)

    def verdict(self, label: object) -> bool | None:
        return label == self.admits


@pytest.mark.cap5_structure
def test_a_gate_with_no_label_that_refuses_refuses_the_module(monkeypatch):
    """A gate that can only ever admit is a network call with a counter
    attached — and every case above would still be green, because they drive
    ``admission`` over verdicts rather than over labels."""
    monkeypatch.setattr(
        gating, "GATES", (replace(DURABILITY, refuses=()), *GATES[1:])
    )
    with pytest.raises(DeriveError, match="durability"):
        gating._check_constants()


@pytest.mark.cap5_structure
def test_a_label_shared_between_two_gates_refuses_the_module(monkeypatch):
    """The wiring mistake ``test_no_two_gates_share_a_label`` describes, refused
    at import so that a build cannot ship with two gates answering one
    another's questions."""
    monkeypatch.setattr(gating, "GATES", (
        DECISION_RELEVANCE,
        replace(DURABILITY, admits=WOULD_MATTER,
                instructions=(*DURABILITY.instructions, WOULD_MATTER)),
        INDEPENDENCE, FALSIFIABILITY,
    ))
    with pytest.raises(DeriveError, match="belongs to both"):
        gating._check_constants()


@pytest.mark.cap5_structure
def test_a_gate_that_folds_its_own_cannot_say_into_a_verdict_refuses_the_module(
    monkeypatch,
):
    """Unsure, refused and never-reached all produce no claim, so folding any
    two of them together makes a case asserting *nothing was written* pass
    either way."""
    monkeypatch.setattr(gating, "GATES", (
        DECISION_RELEVANCE, DURABILITY,
        Folding(name=INDEPENDENCE.name, admits=STANDS_ALONE,
                refuses=(ONLY_A_REPLY,), unsure=INDEPENDENCE_UNSURE,
                instructions=INDEPENDENCE.instructions),
        FALSIFIABILITY,
    ))
    with pytest.raises(DeriveError, match="cannot say"):
        gating._check_constants()


@pytest.mark.cap5_structure
def test_an_admission_that_stops_at_the_first_refusal_refuses_the_module(
    monkeypatch,
):
    """**The guard this module exists for.** CAP-5 calls its gates individually
    testable, and a short-circuiting set cannot be: every case for a later gate
    would pass whether that gate worked or an earlier one refused first.

    The mutation is the natural implementation — the one somebody writes to save
    three model calls on a message that has already been refused — so the guard
    is written against it by name.
    """
    def first_refusal(verdicts):
        for gate in GATES:
            if verdicts.get(gate.name) is False:
                return Admission(refused_by=(gate.name,))
        return Admission(admitted=True)

    monkeypatch.setattr(gating, "admission", first_refusal)
    with pytest.raises(DeriveError, match="individually testable"):
        gating._check_constants()


@pytest.mark.cap5_structure
def test_a_build_with_fewer_than_cap5_s_four_gates_refuses_the_module(
    monkeypatch,
):
    """A gate that is not here does not admit everything — it is a criterion
    nothing ever applies, and no case about the other three would notice."""
    monkeypatch.setattr(gating, "GATES", GATES[:3])
    with pytest.raises(DeriveError, match="four admission gates"):
        gating._check_constants()


@pytest.mark.cap5_structure
def test_the_shipped_module_accepts_itself():
    """The other half of every bypass case above: the guards are reachable and
    the shipped data passes them, so a red one of those is the mutation and not
    the guard."""
    gating._check_constants()
    assert FALSIFIABILITY.verdict(FALSIFIABILITY_UNSURE) is None
    assert RELEVANCE_UNSURE not in DURABILITY.labels
