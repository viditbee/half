"""Assembling a crisis reply from templates (CAP-12).

**The never-list is a property of this assembly, not a filter over it.** A
filter is a classifier standing between a generator and a main, and it fails
the way classifiers fail: quietly, on the phrasing nobody thought of, in the
one conversation where being wrong is unrecoverable. So instead:

* ``reply_for`` takes an ``Assessment`` — a tier, an action and a count — and
  **never the main's text**. The main's words are not an argument to this
  function, so no phrasing of a request can carry anything into the reply. That
  is what makes *"no method or means content, in any phrasing"* structural
  rather than aspirational: there is no channel for it, not a weak one.
* The reply is a join of ``Line.text`` values from ``half.crisis.templates``
  and nothing else, **and every reply is checked against that closed set on the
  way out**. ``is_templated`` is not a test helper: it runs on the production
  path, so a version of it that answered ``True`` unconditionally would stop
  guarding a real reply rather than only a test's.
* Every plan is checked **at import** against the companion's do-list and
  against the machine statement — with raises rather than bare ``assert``,
  because ``python -O`` strips an assert and leaves the module importing
  cleanly. A guarantee an optimisation flag removes is not one.

**Two plans for two costs.** An entering plan is the moment: present, thankful,
unhurried, plainly a machine, pointing at a human, and staying. The asking plan
is one question and a way out of it. Collapsing them was the defect that made
inference-level suspicion cost a main thirty days.

**No plan is empty, and every action that reaches here produces one.** Going
quiet is one of the two documented catastrophic failures — *"Half didn't
respond when it was most required"* — so silence is not representable: there is
no path through ``reply_for`` that returns an empty string or ``None``.

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
    ASK_CLOSE,
    ASK_OPEN,
    EMPATHY,
    HUMAN,
    MACHINE,
    MACHINE_HELD,
    MACHINE_LINES,
    OPEN_CONFIRMATION,
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
    THANKS_LINES,
    Line,
)
from half.errors import CrisisError

#: What paragraphs are joined by. Named so a test can take a reply apart and
#: check every paragraph against the template set.
SEPARATOR: Final[str] = "\n\n"


#: One plan per tier that produces a reply. The entering plans are ordered as
#: the moment is: be present, thank them, acknowledge the difficulty, say
#: plainly what Half is, point at a human, and stay.
PLANS: Final[dict[Tier, tuple[Line, ...]]] = {
    Tier.SAFE_WORD: (OPEN_SAFE_WORD, THANKS, EMPATHY, MACHINE, HUMAN, STAY),
    Tier.DISCLOSURE: (OPEN_DISCLOSURE, THANKS, EMPATHY, MACHINE, HUMAN, STAY),
    Tier.CONFIRMATION: (OPEN_CONFIRMATION, THANKS, EMPATHY, MACHINE, HUMAN, STAY),
    Tier.SEEKING_HELP: (OPEN_SEEKING_HELP, THANKS, EMPATHY, MACHINE, HUMAN, STAY),
    # The mode is already open. Nothing in this story exits it, so this is what
    # every later turn resolves to — including a turn that would otherwise have
    # been assessed as ordinary, and including one trying to talk Half out of
    # the mode. Its wording is deliberately constant: varying it would be
    # improvising in the one place the companion says not to. Whether verbatim
    # repetition eventually reads as absence rather than presence is a clinical
    # question and is on the review list, not settled here.
    Tier.HELD: (OPEN_HELD, THANKS_HELD, EMPATHY, MACHINE_HELD, HUMAN, STAY),
    # The asking plan: three short paragraphs, one of them a question, one of
    # them the way out. No cap, no mode, and nothing durable follows it.
    Tier.INFERENCE: (ASK_OPEN, ASK, ASK_CLOSE),
    # Somebody other than the main. A resource the main can share, and it
    # stops: no assessment, no contact, and nothing recorded about that person.
    Tier.THIRD_PARTY_AT_RISK: (
        OTHER_OPEN, OTHER_LIMIT, MACHINE, OTHER_RESOURCE, OTHER_CLOSE,
    ),
}


def reply_for(assessment: Assessment) -> str:
    """The reply for ``assessment``. Never empty, never generated.

    Takes the assessment and not the message: see the module docstring. A tier
    that does not produce a reply — nothing found — is a caller error and says
    so, rather than returning an empty string that would read downstream as
    silence.

    The closed-set check runs here, on the way out, rather than only in the
    suite. It cannot fail in a released build — every plan is validated at
    import — and it is on this path so that neutering it breaks production
    rather than only a test.
    """
    plan = PLANS.get(assessment.tier)
    if plan is None:
        raise CrisisError(
            f"{assessment.tier} produces no reply; the gate runs the ordinary "
            "pipeline for it. Going quiet inside the mode is the failure, and "
            "an empty reply is how it would arrive"
        )
    reply = SEPARATOR.join(line.text for line in plan)
    if not is_templated(reply):
        raise CrisisError(
            f"the reply assembled for {assessment.tier} is not made of "
            "reviewed template lines; nothing outside that set may reach a "
            "main in crisis"
        )
    return reply


def paragraphs(reply: str) -> list[str]:
    """``reply`` back into the paragraphs it was assembled from."""
    return [part for part in reply.split(SEPARATOR) if part]


def is_templated(reply: str) -> bool:
    """Whether every paragraph of ``reply`` is a known template line.

    The check ``reply_for`` runs before returning, and the one the red-team
    suite runs at every escalation step. It is stronger than scanning for
    forbidden words, because it closes the set: a reply is made of lines a
    clinician has read, or it is not a reply Half sends.
    """
    parts = paragraphs(reply)
    return bool(parts) and all(part in templates.TEXTS for part in parts)


def _check_plans() -> None:
    """Import-time invariants, as raises rather than bare ``assert``.

    Checked here rather than only in the suite, so a plan that stopped
    honouring the companion cannot be imported, let alone shipped, while
    somebody argues about whether the test was too strict — and written as
    raises so ``python -O`` cannot delete the argument.
    """
    responding = {
        tier for tier, action in ACTION_FOR.items()
        if action in (Action.ENTER, Action.ASK, Action.SURFACE)
    }
    if set(PLANS) != responding:
        raise CrisisError(
            "every tier that replies needs a plan and no others: "
            f"{sorted(responding ^ set(PLANS))}"
        )
    for tier, plan in PLANS.items():
        if not plan:
            raise CrisisError(f"{tier} has an empty plan; going quiet is the failure")
        for line in plan:
            if line not in templates.LINES:
                raise CrisisError(
                    f"{tier} uses a line that is not in the reviewed set: {line.id}"
                )
        if ACTION_FOR[tier] is Action.ASK:
            # The asking plan carries the question and nothing heavier. It is
            # deliberately exempt from the machine statement and the do-list:
            # see the templates module for why breaking character on an
            # inference is itself a harm.
            if ASK not in plan:
                raise CrisisError(f"{tier} asks nothing; the question is the plan")
            if any(line in MACHINE_LINES for line in plan):
                raise CrisisError(
                    f"{tier} breaks character on an inference; the machine "
                    "statement belongs to the moment, not to the question"
                )
            continue
        if not any(line in MACHINE_LINES for line in plan):
            raise CrisisError(
                f"{tier} omits the machine statement; Half states plainly that "
                "it is software on every turn inside the mode"
            )
        if ACTION_FOR[tier] is not Action.ENTER:
            # The third-party plan is deliberately not held to the do-list:
            # that reply is *about* somebody else, its own lines carry the
            # presence and the limit, and offering to stay with the main about
            # someone else's crisis would be the assessment the companion
            # forbids.
            continue
        if not any(line in THANKS_LINES for line in plan):
            raise CrisisError(f"{tier}: nothing thanks the main for telling Half")
        if EMPATHY not in plan:
            raise CrisisError(f"{tier}: no empathy")
        if STAY not in plan:
            raise CrisisError(f"{tier}: does not stay")
        if HUMAN not in plan:
            raise CrisisError(f"{tier}: does not point at a human")


_check_plans()
