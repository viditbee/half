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
SCHEMA_VERSION: Final[int] = 1


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
