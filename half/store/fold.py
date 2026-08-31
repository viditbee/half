"""The pure fold: log -> current state (AD-30).

This module must never call a model, touch the network, or read a clock. A
fold is a pure function of the log, and that is what makes the replay
invariant (AD-4) true rather than aspirational: without purity, a main who
changed model tier would replay to different state.

``tests/test_purity.py`` enforces the rule statically, because "just re-derive
it" is the natural way to write a fold and a behavioural test would not catch it.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from half.errors import CorruptLogError
from half.store.ops import Op
from half.store.records import Record


@dataclass(slots=True)
class State:
    """The materialized current view. Derived and disposable."""

    beliefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    tensions: dict[str, dict[str, Any]] = field(default_factory=dict)
    loops: dict[str, dict[str, Any]] = field(default_factory=dict)
    expunged: set[str] = field(default_factory=set)

    def canonical_json(self) -> str:
        """Deterministic serialization — the unit of the byte-identical
        comparison in the replay test."""
        return json.dumps(
            {
                "beliefs": self.beliefs,
                "tensions": self.tensions,
                "loops": self.loops,
                "expunged": sorted(self.expunged),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def fold(records: Iterable[Record]) -> State:
    """Fold records into current state. Pure: same input, same output, always."""
    state = State()

    for record in records:
        if record.data.get("tombstone") is True:
            state.expunged.add(record.id)
            state.beliefs.pop(record.id, None)
            state.tensions.pop(record.id, None)
            state.loops.pop(record.id, None)
            continue

        match record.op:
            case Op.ASSERT:
                if record.id not in state.expunged:
                    state.beliefs[record.id] = copy.deepcopy(dict(record.data))

            case Op.RETRACT | Op.REVISE:
                # Both remove the belief from the current view. They differ in
                # what Half owes the main, not in what the fold does: RETRACT
                # means "you changed" (no apology), REVISE means "Half was
                # wrong" (apology, and show what was removed). The distinction
                # is preserved in the log for whoever composes that message.
                target = _require_target(record)
                state.beliefs.pop(target, None)

            case Op.EXPUNGE:
                target = _require_target(record)
                state.expunged.add(target)
                state.beliefs.pop(target, None)
                state.tensions.pop(target, None)
                state.loops.pop(target, None)

            case Op.TENSION:
                if record.id not in state.expunged:
                    state.tensions[record.id] = copy.deepcopy(dict(record.data))

            case Op.LOOP_TRANSITION:
                loop_id = record.data.get("loop")
                if not isinstance(loop_id, str) or not loop_id:
                    raise CorruptLogError(
                        f"{record.op} record {record.id!r} has no 'loop'",
                        path="<fold>", line=0,
                    )
                if loop_id in state.expunged:
                    continue
                entry = state.loops.setdefault(loop_id, {"loop": loop_id})
                for key in ("state", "timescale", "last_movement"):
                    if key in record.data:
                        entry[key] = record.data[key]

            case _:  # pragma: no cover - guarded by the closed vocabulary
                # A new Op added to the enum must not fold to nothing. Silently
                # dropping a record is the failure AD-29 exists to prevent,
                # reappearing one level down.
                raise CorruptLogError(
                    f"fold has no case for op {record.op!r}", path="<fold>", line=0
                )

    return state


def _require_target(record: Record) -> str:
    """A correction must name what it corrects.

    Defaulting to the op record's own id let a malformed RETRACT silently
    no-op, leaving the belief in place — the same silent-omission failure
    unknown ops are made fatal to avoid.
    """
    target = record.data.get("target")
    if not isinstance(target, str) or not target:
        raise CorruptLogError(
            f"{record.op} record {record.id!r} has no 'target'", path="<fold>", line=0
        )
    return target
