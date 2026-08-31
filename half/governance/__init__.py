"""Delivery governance: what Half may say, and whether to say it (CAP-10).

`half.retrieval` answers *which beliefs matter to this main right now*.
`half.context` answers *how the material a rung permits is assembled for a
model*. This package answers the question underneath both: **which rung a
belief may occupy at all**, and it is the only module that decides.

This slice is the ladder — the rung rules, the two `assert` preconditions,
quarantine, promotion and demotion validity, and AD-28's global ceiling. The
trust balance, the unsaid and unasked queues and their release conditions are
story 5b; the interrupt rule and the nagging bound follow story 8.
"""

from half.governance.ladder import (
    FLOOR,
    RUNGS,
    TOP,
    Ceiling,
    License,
    QuarantineCandidate,
    admitted,
    cap,
    ceiling_fields,
    demote,
    has_receipt,
    height,
    known_to_main,
    own_rung,
    permitted,
    promote,
    quarantine,
    quarantine_candidate,
    quarantined,
    rung_of,
    weaker,
)

__all__ = [
    "Ceiling",
    "FLOOR",
    "License",
    "QuarantineCandidate",
    "RUNGS",
    "TOP",
    "admitted",
    "cap",
    "ceiling_fields",
    "demote",
    "has_receipt",
    "height",
    "known_to_main",
    "own_rung",
    "permitted",
    "promote",
    "quarantine",
    "quarantine_candidate",
    "quarantined",
    "rung_of",
    "weaker",
]
