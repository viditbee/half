"""The reviewed corpus, pinned (CAP-12).

Every word a main can receive in crisis, every phrase that decides which action
Half takes, the safe word, and the constants the attribution rule turns on —
digested, so that changing any of them fails the suite by name.

**Why a digest and not a set of behavioural cases.** Behavioural cases prove
that the rows which *exist* still work; they cannot see a row that was deleted,
because the case for it is deleted with it. Mutation testing removed 44 of 55
entering phrases — the whole self-harm vocabulary among them — with the CAP-12
gate green, and rewrote every template and the safe word with the gate green.
The story's Ask-First rule already forbade both; what it lacked was a test that
fails mechanically when the rule is broken.

**What a failure here means.** Not that you did something wrong — that you did
something that needs sign-off:

* a **template wording change** is an Ask-First change *and* a clinical-review
  change. The corpus a clinician read is the corpus in ``templates.py``; if it
  changes after review, the review no longer covers what ships;
* a **safe word change** breaks a promise made at onboarding to every existing
  main, who learned one phrase and will type that one;
* a **vocabulary change** moves what Half notices. Adding is cheaper than
  removing, and removing a row is the Ask-First case exactly.

**How to update, deliberately.** Get the sign-off, make the change, run
``uv run --extra dev python tests/test_crisis_golden.py`` to print the new
digests, and paste them in *with the reason in the commit message*. Updating
the digest without the sign-off is the failure mode this file exists to make
visible, and no test can prevent it — only make it a thing somebody had to do
on purpose.
"""

from __future__ import annotations

import hashlib

import pytest

from half.crisis import respond, signals, templates
from half.crisis.signals import ACTION_FOR, VOCABULARY

pytestmark = pytest.mark.cap12


def digest(*parts: str) -> str:
    """A stable digest of an ordered rendering. Sorted by the caller where the
    order is not itself meaningful, so a reordering is not a false alarm."""
    joined = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:32]


def vocabulary_digest(name: str) -> str:
    return digest(*sorted(VOCABULARY[name]))


def template_rendering() -> list[str]:
    return [f"{line.id} {line.text}" for line in templates.LINES]


def plan_rendering() -> list[str]:
    return [
        f"{tier} " + ",".join(line.id for line in plan)
        for tier, plan in sorted(respond.PLANS.items())
    ]


def action_rendering() -> list[str]:
    return [f"{tier} {action}" for tier, action in sorted(ACTION_FOR.items())]


def constant_rendering() -> list[str]:
    return [
        f"attribution_window={signals.ATTRIBUTION_WINDOW}",
        f"short_message_words={signals.SHORT_MESSAGE_WORDS}",
        f"max_typo={signals.MAX_TYPO}",
        f"min_fuzzy_length={signals.MIN_FUZZY_LENGTH}",
        f"safe_word_min_fuzzy={signals.SAFE_WORD_MIN_FUZZY}",
    ]


# -- the pins -----------------------------------------------------------------

SAFE_WORD = "lantern hour"
# Re-pinned for story 6b, which *added* seven lines and changed none: the four
# that frame the offer, the two the main sends, and — from review round 1 — the
# one that says out loud that a told region matched nothing, because silently
# nothing reads as Half having decided the main was not worth a line. Every
# earlier line is byte-identical, so the corpus a reviewer read is still in
# here whole; what needs review is the addition. The directory of crisis lines
# is deliberately **not** pinned here: it is data, and build requirement 5 says
# it must be refreshable without a release, which a digest would forbid. Its
# own gate is ``reviewed``, which the shipped file sets to false.
#
# Re-pinned again for story 6c, which added eleven lines and changed none. Six
# are the aftercare question, its two answers, and what Half says when the main
# asks it to stop asking. Five are the frame around a document somebody else
# wrote: the two paragraphs either side of a held plan, the acknowledgement when
# a main hands one over, the sentence for a main who has none, and the sentence
# for a plan Half is holding and cannot show whole. None of the eleven is a plan
# or a step; the plan's own words are data, and no digest here covers them,
# because they are the main's clinician's and not this product's.
#
# **One line was rewritten in review round 1**, and it is the only wording this
# story changes rather than adds. ``plan-open`` said *"the safety plan you made
# with a professional"* over a document Half merely stores and cannot check the
# provenance of. It now says what Half actually knows — that the main gave it
# and that Half changed nothing — because a claim about who wrote a clinical
# document is not a claim to make on somebody's behalf at three in the morning.
#
# Seven vocabulary tables joined across the two rounds. ``consent`` is the
# strict reading of a yes that the aftercare question needs — the inverse of the
# generous reading crisis entry uses, because the two questions fail in opposite
# directions — with ``consent_hedge``, ``consent_refusal`` and
# ``consent_contradiction`` beside it, added in review round 1 after
# *"yes, but please don't"* and *"sure, I picked up the milk"* both resumed the
# mirror. ``stop_asking`` is a main asking not to be asked again.
# ``plan_request`` is how a main asks for the document Half is holding, and
# ``plan_intake`` is how they hand one over.
TEMPLATES = "316a5e2c7817c9676356c383b5ba5ed2"
PLANS = "bff98dbf54f79dde63156fd8aa128fec"
ACTIONS = "82218c538a9a409b87c4a8b72e464f11"
CONSTANTS = "7579d7e37990280768f4e627b2fda8ad"
VOCABULARY_PINS: dict[str, tuple[str, int]] = {
    "affirmative": ("c5b82ac8c4ebea4ca4e7a9ac6ea0ade0", 34),
    "care_target": ("6252167d8554be8ca92d2477b5659794", 9),
    "claiming_explicit": ("8dac8c71fc026355063df1692ad830e3", 12),
    "claiming_loose": ("d6b9d44c72007088967e12334d13584f", 8),
    "consent": ("4b9cd9946c33dc66840592bee5956e7d", 21),
    "consent_contradiction": ("93442c63c010aa6a9d8644b7c1ef9aa9", 11),
    "consent_hedge": ("6324cae8dafc4224c75bc57cf8d8f4ba", 16),
    "consent_refusal": ("796fb1b8e8a1ce2db8a59c30519475fe", 17),
    "contact": ("449763ba124e90caf276a709ae97e3a3", 31),
    "crisis_target": ("1a70534cbd01be0a4a9bfc67fa40b1bb", 11),
    "farewell": ("e9c0ec38bcd2e07cc3c3275cfa96fa70", 13),
    "fuzzy_keywords": ("a198d05c33cde08fe72c7d52f63543c2", 6),
    "hedging": ("816e57814b40534518db818448aea1c8", 41),
    "main_risk": ("3bfd1809d9e226af37edad65f3ee3978", 40),
    "negative": ("275ee23c2c844c00216af9cda189d284", 17),
    "other_markers": ("7a1f2e8c31f223bc8c6fee36fa6a9012", 46),
    "other_risk": ("b99bdad2d31575eb9ef0fa4aa9210f7e", 41),
    "outcome": ("45029138009dad47092fe8cad20a8db3", 12),
    "plan_intake": ("1906935134acebf75690916b9a79ec48", 9),
    "plan_request": ("20f40a21f487405d50986235bca76af9", 10),
    "preparatory": ("936ca54e7c70e48e5d7807b5c8d631ba", 19),
    "request": ("9c2d63a5e3c5864f9ef42ff521fdc800", 16),
    "risk": ("e30b614f0dae30e30fd4e44bdaccbb28", 23),
    "self_markers": ("bd1375c7f37fae93ef4c2dbbc5a82833", 8),
    "short_only": ("8271d06e29b75ad677fb3bbdacab053d", 5),
    "slang": ("aa539795854138b991e6d500bab15aab", 14),
    "stop_asking": ("9e3cb97cc9d7576a3f05ec98328649f4", 11),
    "topic": ("4dee438fb7578bf90535e735aedd312d", 34),
    "trailing_ok": ("7c678f40d155188c833d3c30f2cb8c56", 13),
}


def test_the_safe_word_is_exactly_what_onboarding_documents():
    """It is documented at onboarding and never changes. A main who learned it
    in week one must be able to type it in month nine."""
    assert signals.SAFE_WORD == SAFE_WORD, (
        "the safe word changed. Every main who learned the old one at "
        "onboarding now has a phrase that does nothing, and the safe word is "
        "the one signal that may never fail. This is an Ask-First change."
    )


def test_every_template_line_is_the_one_that_was_reviewed():
    assert digest(*template_rendering()) == TEMPLATES, (
        "a crisis template changed. Every word a main can receive in crisis is "
        "reviewed as a corpus, so an edit after review means what ships is not "
        "what was reviewed. This is an Ask-First change and a clinical-review "
        "change; see the module docstring for how to re-pin it."
    )


def test_every_plan_is_assembled_from_the_lines_it_was_reviewed_with():
    assert digest(*plan_rendering()) == PLANS, (
        "a crisis reply's shape changed — a line added, removed or reordered. "
        "The moment was reviewed as a whole reply, not as a bag of sentences."
    )


def test_the_tier_table_still_maps_every_tier_to_the_action_it_was_given():
    assert digest(*action_rendering()) == ACTIONS, (
        "a tier changed action. Moving a tier from ASK to ENTER makes a cheap, "
        "reversible question into a durable thirty-day cap; moving one the "
        "other way narrows what the mode covers. Both are Ask-First."
    )


def test_the_attribution_constants_are_the_ones_that_were_reasoned_about():
    assert digest(*constant_rendering()) == CONSTANTS, (
        "an attribution or matching constant changed. Widening the window "
        "makes a relative named a sentence ago capture a disclosure made now; "
        "narrowing it makes 'my friend is suicidal' the main's."
    )


@pytest.mark.parametrize("name", sorted(VOCABULARY))
def test_every_vocabulary_table_is_unchanged(name):
    expected, count = VOCABULARY_PINS[name]
    actual = VOCABULARY[name]
    assert len(actual) == count, (
        f"the {name} table has {len(actual)} phrases and was pinned at "
        f"{count}. Removing a signal is the Ask-First case exactly; adding one "
        "is cheaper but still deliberate."
    )
    assert vocabulary_digest(name) == expected, (
        f"the {name} table changed. What Half notices is not something to "
        "adjust while fixing something else."
    )


def test_the_pins_cover_every_table_there_is():
    """A table added later must be pinned on the day it is written, not on the
    day somebody remembers this file exists."""
    assert set(VOCABULARY_PINS) == set(VOCABULARY), (
        f"unpinned tables: {sorted(set(VOCABULARY) - set(VOCABULARY_PINS))}"
    )


if __name__ == "__main__":  # pragma: no cover - the re-pinning helper
    print(f'SAFE_WORD = "{signals.SAFE_WORD}"')
    print(f'TEMPLATES = "{digest(*template_rendering())}"')
    print(f'PLANS = "{digest(*plan_rendering())}"')
    print(f'ACTIONS = "{digest(*action_rendering())}"')
    print(f'CONSTANTS = "{digest(*constant_rendering())}"')
    print("VOCABULARY_PINS: dict[str, tuple[str, int]] = {")
    for table in sorted(VOCABULARY):
        print(f'    "{table}": ("{vocabulary_digest(table)}", {len(VOCABULARY[table])}),')
    print("}")
