"""The tripwire: a smoke alarm on AD-18, and never the rule (CAP-8).

**AD-18 is enforced at construction.** ``half.context.build`` resolves every
license once, under the main's ceiling, and assembles the material a rung does
not permit into a ``Directive`` that carries structured topics and no claim text
at all. ``half.voice.compose`` then builds the quotable block and the shaping
block from two different fields with two different functions. There is no branch
on that path that could re-admit a `behave` claim as something Half may say,
because the claim never enters the structure the generator is handed.

This module exists to notice if that ever stops being true.

**It fails the send, loudly, and never redacts.** That is the whole design, and
the reason is a pattern this tree has shipped twice: story 8's outbound firewall
and story 6b's send scan both looked healthy for months while the guarantee
underneath them decayed, because their output was clean. A check that quietly
strips a leaked wording and sends the rest produces a passing test, a plausible
message, and no signal at all — and the construction rule it was supposed to be
watching can be broken for a year without anybody finding out. So the outcome of
a trip is: **nothing is sent**, an ``error`` is logged, and the morning is
counted as a leak.

**There is deliberately no redaction function in this module**, not even a
private one, because the presence of one is the whole risk. If a caller wants
the message cleaned, there is nothing here to call.

**The rule is the builder's own, imported rather than restated.**
``half.context.build.withheld`` computes the wordings a context may not carry —
adjacent word pairs over units that keep a Devanagari matra attached to its
letter, folded by ``half.text.normalize``, with invisible characters removed.
Reimplementing that beside the generator would have produced whatever somebody
remembered of it, which in this codebase has always meant a rule that works in
Latin script and silently does nothing anywhere else.

**Nothing is logged but a count and a ``main_id``** (AD-22). A leak's whole
subject is a string that must not travel, so the one thing that must never
appear in the alarm is the thing that set it off.
"""

from __future__ import annotations

import logging
from typing import Final

from half.context.build import leaks

__all__ = ["LEAKED", "check"]

#: Structured, and content-free. Every value logged from this module is a count
#: or a ``main_id`` — never the generated text, never the withheld wording, and
#: never the fragment that matched.
logger = logging.getLogger(__name__)

#: Why the send was refused. A closed constant so a caller counts a value rather
#: than a message, and so nothing a main's own ledger produced can reach a
#: counter (AD-22).
LEAKED: Final[str] = "leaked"


def check(text: str, withheld: frozenset[str] | set[str], *, main_id: str) -> bool:
    """Whether ``text`` may be sent. ``False`` means send nothing.

    **A predicate, not a filter.** It returns a boolean and the caller's only
    options are to send the text it was given or to send nothing — there is no
    third value carrying a cleaned string, which is what makes *"never silently
    redacted"* a property of the signature rather than a promise about the body.

    ``withheld`` is ``half.context.build.withheld`` over the same material the
    context was built from. An empty set is the ordinary case — a morning whose
    material is all `assert` withholds nothing — and it answers ``True`` without
    scanning.

    Scanned line by line, which is what ``leaks`` does to a rendering and is
    right for prose too: it avoids inventing adjacency across a line break that
    the reader will never see.

    A trip is an ``error`` because it is one. Every ordinary silence on this
    path is counted at ``debug``; this one means either that a model repeated a
    withheld wording *or* that AD-18's construction rule has broken, and the
    second is a launch-blocking defect that must not look like a quiet morning.
    """
    if not isinstance(text, str) or not text:
        return True
    if not withheld:
        return True
    if not leaks(text, withheld):
        return True
    logger.error(
        "the morning composed for main=%s repeats wording that may not be "
        "said; nothing is sent and nothing is cleaned up. Either a model "
        "echoed a withheld claim or licenses have stopped being enforced at "
        "context construction (AD-18)",
        main_id,
    )
    return False
