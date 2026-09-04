"""Delivery governance: what Half may say, and whether to say it (CAP-10).

`half.retrieval` answers *which beliefs matter to this main right now*.
`half.context` answers *how the material a rung permits is assembled for a
model*. This package answers the question underneath both: **which rung a
belief may occupy at all**, and it is the only module that decides.

This slice is the ladder — the rung rules, the two `assert` preconditions,
quarantine, promotion and demotion validity, and AD-28's global ceiling. The
trust balance and the unasked queue are story 5b; the interrupt rule and the
nagging bound follow story 8.

``half.governance.unsaid`` (story 5d) is the queue CAP-10 asks for: what Half is
holding below the rung it would reach, and which of the ladder's own
preconditions each item is missing. **It is deliberately not re-exported here.**
It asks ``half.context.build.resolve`` — the one door that answers what rung a
belief is effectively on — and ``half.context.build`` imports this package's
ladder, so naming it in this file is an import cycle: importing
``half.context.build`` runs this ``__init__`` first, which would re-enter a
half-initialized ``half.context.build``. Verified, not assumed. Callers import
``half.governance.unsaid`` directly, exactly as the registry imports
``half.trust.unasked`` directly.
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
