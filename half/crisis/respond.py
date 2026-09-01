"""Assembling a crisis reply from templates (CAP-12).

**The never-list is a property of this assembly, not a filter over it.** A
filter is a classifier standing between a generator and a main, and it fails
the way classifiers fail: quietly, on the phrasing nobody thought of, in the
one conversation where being wrong is unrecoverable. So instead:

* ``reply_for`` takes an ``Assessment`` — a tier and an action — and **never
  the main's text**. The main's words are not an argument to this function, so
  no phrasing of a request can carry anything into the reply. That is what
  makes *"no method or means content, in any phrasing"* structural rather than
  aspirational: there is no channel for it, not a weak one.
* The reply is a join of ``Line.text`` values from ``half.crisis.templates``
  and nothing else. No formatting, no interpolation, no concatenation with
  anything computed — asserted statically in ``tests/test_crisis.py``.
* Every plan is checked **at import** against the companion's do-list and
  against the machine statement. A plan that stopped thanking the main, or
  stopped saying Half is software, fails to import rather than shipping.

**No plan is empty, and every action that reaches here produces one.** Going
quiet is one of the two documented catastrophic failures — *"Half didn't
respond when it was most required"* — so silence is not representable: there
is no path through ``reply_for`` that returns an empty string or ``None``.

**No model call, anywhere** (AD-19). Nothing here is generated, so nothing here
is a generation failure.

Pure and stdlib-only: same assessment, same reply, always.
"""

from __future__ import annotations

from typing import Final

from half.crisis import templates
from half.crisis.signals import ACTION_FOR, Action, Assessment, Tier
from half.crisis.templates import (
    ASK,
    EMPATHY,
    HUMAN,
    MACHINE,
    MACHINE_HELD,
    MACHINE_LINES,
    OPEN_DISCLOSURE,
    OPEN_HELD,
    OPEN_SAFE_WORD,
    OPEN_SEEKING_HELP,
    OTHER_CLOSE,
    OTHER_LIMIT,
    OTHER_OPEN,
    OTHER_RESOURCE,
    STAY,
    THANKS,
    THANKS_HELD,
    THANKS_INFERRED,
    THANKS_LINES,
    Line,
)
from half.errors import CrisisError

#: What paragraphs are joined by. Named so a test can take a reply apart and
#: check every paragraph against the template set.
SEPARATOR: Final[str] = "\n\n"


#: One plan per tier that produces a reply. Ordered as the moment is: be
#: present, thank them, acknowledge the difficulty, say plainly what Half is,
#: point at a human, and stay.
PLANS: Final[dict[Tier, tuple[Line, ...]]] = {
    Tier.SAFE_WORD: (OPEN_SAFE_WORD, THANKS, EMPATHY, MACHINE, HUMAN, STAY),
    Tier.DISCLOSURE: (OPEN_DISCLOSURE, THANKS, EMPATHY, MACHINE, HUMAN, STAY),
    # Inference alone may ask here — and must. The direct question opens the
    # reply rather than trailing it, because a question buried under five
    # paragraphs of comfort is not a question.
    Tier.INFERENCE: (ASK, THANKS_INFERRED, EMPATHY, MACHINE, HUMAN, STAY),
    Tier.SEEKING_HELP: (OPEN_SEEKING_HELP, THANKS, EMPATHY, MACHINE, HUMAN, STAY),
    # The mode is already open. Nothing in this story exits it, so this is what
    # every later turn resolves to — including a turn that would otherwise have
    # been assessed as ordinary, and including one trying to talk Half out of
    # the mode. Its wording is deliberately constant: varying it would be
    # improvising in the one place the companion says not to.
    Tier.HELD: (OPEN_HELD, THANKS_HELD, EMPATHY, MACHINE_HELD, HUMAN, STAY),
    # Somebody other than the main. A resource the main can share, and it
    # stops: no assessment, no contact, and nothing recorded about that person.
    Tier.THIRD_PARTY_AT_RISK: (
        OTHER_OPEN, OTHER_LIMIT, MACHINE, OTHER_RESOURCE, OTHER_CLOSE,
    ),
}


def reply_for(assessment: Assessment) -> str:
    """The reply for ``assessment``. Never empty, never generated.

    Takes the assessment and not the message: see the module docstring. A tier
    that does not produce a reply — vigilance, or nothing found — is a caller
    error and says so, rather than returning an empty string that would read
    downstream as silence.
    """
    plan = PLANS.get(assessment.tier)
    if plan is None:
        raise CrisisError(
            f"{assessment.tier} produces no reply; the gate runs the ordinary "
            "pipeline for it. Going quiet inside the mode is the failure, and "
            "an empty reply is how it would arrive"
        )
    return SEPARATOR.join(line.text for line in plan)


def paragraphs(reply: str) -> list[str]:
    """``reply`` back into the paragraphs it was assembled from."""
    return [part for part in reply.split(SEPARATOR) if part]


def is_templated(reply: str) -> bool:
    """Whether every paragraph of ``reply`` is a known template line.

    The check the red-team suite runs at every escalation step. It is stronger
    than scanning for forbidden words, because it closes the set: a reply is
    made of lines a clinician has read, or it is not a reply Half sends.
    """
    parts = paragraphs(reply)
    return bool(parts) and all(part in templates.TEXTS for part in parts)


# -- import-time invariants ---------------------------------------------------
#
# Checked here rather than only in the suite, so a plan that stopped honouring
# the companion cannot be imported, let alone shipped, while somebody argues
# about whether the test was too strict.

_RESPONDING = {
    tier for tier, action in ACTION_FOR.items()
    if action in (Action.ENTER, Action.SURFACE)
}
assert set(PLANS) == _RESPONDING, (
    f"every entering or surfacing tier needs a plan: {_RESPONDING ^ set(PLANS)}"
)
for _tier, _plan in PLANS.items():
    assert _plan, f"{_tier} has an empty plan; going quiet is the failure"
    assert any(line in MACHINE_LINES for line in _plan), (
        f"{_tier} omits the machine statement; Half states plainly that it is "
        "software on every crisis turn"
    )
# The do-list, per #chatsafe / Orygen: be present, express empathy, acknowledge
# the difficulty, thank them for telling you, stay. Required of the plans that
# enter the mode. The third-party plan is deliberately not one of them — that
# reply is *about* somebody else and its own lines carry the presence and the
# limit, and offering to stay with the main about someone else's crisis would
# be the assessment the companion forbids.
for _tier in _RESPONDING & set(ACTION_FOR):
    if ACTION_FOR[_tier] is not Action.ENTER:
        continue
    _plan = PLANS[_tier]
    assert any(line in THANKS_LINES for line in _plan), f"{_tier}: no thanks"
    assert EMPATHY in _plan, f"{_tier}: no empathy"
    assert STAY in _plan, f"{_tier}: does not stay"
    assert HUMAN in _plan, f"{_tier}: does not point at a human"
assert ASK in PLANS[Tier.INFERENCE], (
    "an inferred entry must carry the direct question: this is the one place "
    "in Half where inference alone may license `ask`, and it is mandatory"
)
