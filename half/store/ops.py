"""The closed op vocabulary (AD-29).

The set of ops is enumerated here and nowhere else, and carries a schema
version. Adding an op is a deliberate versioned change, never an incidental
one: a second module inventing its own op name would produce records that
another module's replay silently skips, while each one's replay test passes in
isolation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

#: Bumped when the record shape or the op set changes in a way older builds
#: cannot faithfully fold.
#:
#: v2 added ``ceiling`` (story 5a). A build that predates it would meet the op,
#: raise ``UnknownOpError`` and refuse to fold — which is the correct outcome
#: and the reason the bump is not optional: an older build silently folding a
#: log whose ceiling records it cannot see would resolve every license
#: uncapped, and a main mid-aftercare would be un-suppressed by a rollback.
#:
#: v3 added ``crisis`` (story 6a), for the same reason one rung stronger. A
#: build that could not see a crisis record would fold a main in the mode to a
#: main who is not, and answer their next message through the ordinary
#: pipeline — a silent mode exit, which CAP-12 forbids outright.
SCHEMA_VERSION: Final[int] = 3


class Op(StrEnum):
    """Every op that may appear in a belief log."""

    #: A new durable claim about the main.
    ASSERT = "assert"
    #: The main changed. History preserved, no apology owed.
    RETRACT = "retract"
    #: Half was wrong about the main. History preserved, apology owed.
    REVISE = "revise"
    #: Genuine removal, tombstoned. Rare, main-initiated only.
    EXPUNGE = "expunge"
    #: A linked pair of entries that disagree and cannot be resolved.
    TENSION = "tension"
    #: An open loop moved between states.
    LOOP_TRANSITION = "loop_transition"
    #: The main's global license ceiling moved (AD-28).
    #:
    #: In the log rather than in memory, because a ceiling has to survive both
    #: actor eviction — routine at any real capacity, not exceptional — and a
    #: process restart. A crisis aftercare cap runs for thirty days; a cap that
    #: lifts itself when a worker gets busy is worse than no cap, because it
    #: reads as protection. AD-26 keeps *volatile* state out of the log, and a
    #: thirty-day governance decision is not volatile.
    CEILING = "ceiling"
    #: The main entered crisis mode, or an operator reversed that entry
    #: (CAP-12).
    #:
    #: In the log for the reason the ceiling is, and one degree more urgently.
    #: A mode held only in memory ends at the next eviction or restart, and the
    #: main's following message is answered by ordinary Half — which is a mode
    #: exit that nobody decided and nobody can see. It is also the only record
    #: that the mode ever opened: the ceiling append says a cap exists, not what
    #: put it there, and the clinical reviewer's first question is how often
    #: this fires and on what.
    #:
    #: **Content-free** (AD-22). The record carries the tier, a signal count and
    #: the state — never the message, never a phrase, never a claim.
    CRISIS = "crisis"


#: The two states a ``crisis`` record may carry. Named here, beside the op, so
#: the fold that validates them and the registry that writes them cannot drift
#: to two different spellings of the same word.
CRISIS_ENTERED: Final[str] = "entered"
CRISIS_REVERSED: Final[str] = "reversed"
CRISIS_STATES: Final[frozenset[str]] = frozenset({CRISIS_ENTERED, CRISIS_REVERSED})


#: Frozen membership test. Kept separate from the enum so a lookup never
#: constructs an Op for input that is not one.
OP_NAMES: Final[frozenset[str]] = frozenset(op.value for op in Op)


def parse_op(value: object) -> Op:
    """Return the Op for ``value``.

    Raises ``ValueError`` for anything outside the vocabulary; callers with
    log position context convert that to ``UnknownOpError``.
    """
    if not isinstance(value, str) or value not in OP_NAMES:
        raise ValueError(str(value))
    return Op(value)
