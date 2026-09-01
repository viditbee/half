"""What the surface is allowed to see (CAP-8, AD-28).

**A projection, not the fold, and that is this module's whole reason to
exist.** The surface used to be handed ``half.store.fold.State`` entire — which
carries the crisis record, the aftercare record and the schedule alongside the
beliefs it actually needs. Review found the consequence and it is the exact
failure AD-28 names: inserting

    if state.aftercare is not None:
        return Silence(NOTHING_MAY_BE_SAID)

into the surface passed the whole suite. No new import, so the import scan saw
nothing; no fifth ledger door, so the protocol scan saw nothing; and the
mutant is *not* behaviour-neutral — a main whose aftercare has finished and
whose ceiling is back at `assert` is silenced by it for ever and receives their
morning without it. Per-feature suppression, written in one line, invisible to
every guard that was supposed to forbid it.

A grep for the word would have caught that one spelling and none of the others.
So the fix is not another scan: it is that **the surface cannot reach the
fields it must not consult**, because they are not in what it is handed. An
`if in_aftercare` branch is now an ``AttributeError``, which no amount of
wording gets around.

**What is here, and why each one.** The beliefs and loops the surface may build
a message from; the raises the nagging bound measures against; the day marker
the one-a-day rule reads; the tensions and expunged set that say whether an
origin is still there to be cited; and the ceiling, which is the *only* thing
the surface may know about governance — a rung, with no way to ask where it
came from.

**What is deliberately not here.** ``crisis`` is absent even though the surface
suspends on the mode: it asks that through its own narrowed door, which answers
a boolean, so there is no record to branch on. ``aftercare`` and ``schedule``
are absent outright. A future field on ``State`` is absent by default — this is
an allowlist, and adding to it is a deliberate edit with a reviewer on it.

Pure and clockless. Nothing here decides anything; ``narrowed`` copies the
fields it is allowed to copy and returns a frozen value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields as dataclass_fields
from typing import Any, Final

from half.governance.ladder import Ceiling
from half.store.fold import State

__all__ = [
    "CLAIMED", "CLAIM_ALREADY", "CLAIM_CRISIS", "CLAIM_OUTCOMES",
    "SurfaceView", "VISIBLE", "narrowed", "view_fields",
]

#: What claiming a main's day for an unprompted message came back as.
#:
#: The vocabulary is here, between the actor and the surface, because both
#: sides need it and only one of them may own the spelling — the same reason
#: ``half.store.ops`` owns the crisis and aftercare states. It is a closed set
#: for the reason those are: the surface branches on the answer, and a fourth
#: value nobody recognised would fall through as *claimed*.
#:
#: **Why claiming is a single serialized operation and not a read followed by a
#: write.** The surface used to read the day marker under the mutex, release
#: it, decide, and re-acquire to append — so two overlapping runs both read
#: yesterday and both sent. The check and the append now happen inside one
#: ``acquire``, which is also where the crisis mode is re-asserted: a main who
#: enters the mode while their morning is being built must not receive it.
CLAIMED: Final[str] = "claimed"
CLAIM_ALREADY: Final[str] = "already"
CLAIM_CRISIS: Final[str] = "crisis"
CLAIM_OUTCOMES: Final[frozenset[str]] = frozenset(
    {CLAIMED, CLAIM_ALREADY, CLAIM_CRISIS}
)

#: The fields of ``State`` a surface may see. An allowlist, spelled once, and
#: read by ``narrowed`` **and** by ``tests/test_surface.py`` — so a new field on
#: ``State`` is invisible to the surface until somebody adds it here on purpose,
#: and the test that says so reads this tuple rather than a copy of it.
VISIBLE: Final[tuple[str, ...]] = (
    "beliefs", "loops", "tensions", "expunged", "expunged_loops", "touches",
    "spoke",
)


@dataclass(frozen=True, slots=True)
class SurfaceView:
    """One main's state, narrowed to what a morning may consult.

    Frozen, so a surface cannot write into what it was handed and cannot pass a
    mutated copy on to the next rule.
    """

    #: What the main believes, as the log folded it. Not narrowed by field: the
    #: surface's whole job is to decide what may be *said* about a claim, so
    #: narrowing the claim away would leave it nothing to decide. What narrows
    #: *within* a belief is the ladder and the context builder, one layer up,
    #: which is where AD-18 puts it.
    beliefs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: The open loops — the ranking function, and what the bound is measured
    #: against.
    loops: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: The tensions the log still holds. Read only to answer *"is the thing
    #: this candidate cites still there?"*, never to compute drift — that is
    #: the pass's, and it has already run.
    tensions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: Ids the main has erased. Beside ``tensions`` for the same question: an
    #: origin the main erased overnight is an origin nothing may cite.
    expunged: frozenset[str] = frozenset()
    expunged_loops: frozenset[str] = frozenset()
    #: The last raise per loop — the nagging bound's input.
    touches: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: The newest day marker, or ``None``. The one-a-day rule's input.
    spoke: Mapping[str, Any] | None = None
    #: This main's global cap (AD-28). A rung and nothing else: the surface may
    #: know *what it may say*, and may not know why. There is deliberately no
    #: field here from which the reason could be inferred.
    ceiling: Ceiling = field(default_factory=Ceiling)


def narrowed(state: State, ceiling: Ceiling) -> SurfaceView:
    """``state`` reduced to what a surface may consult.

    Copies rather than referencing, so that a view handed out cannot change
    under its reader while the actor keeps working — and so that the surface
    holding a mapping is holding one nothing else writes to.
    """
    return SurfaceView(
        beliefs={k: dict(v) for k, v in state.beliefs.items()},
        loops={k: dict(v) for k, v in state.loops.items()},
        tensions={k: dict(v) for k, v in state.tensions.items()},
        expunged=frozenset(state.expunged),
        expunged_loops=frozenset(state.expunged_loops),
        touches={k: dict(v) for k, v in state.touches.items()},
        spoke=dict(state.spoke) if state.spoke is not None else None,
        ceiling=ceiling,
    )


def view_fields() -> tuple[str, ...]:
    """The view's own field names. Read by the test that pins the allowlist."""
    return tuple(f.name for f in dataclass_fields(SurfaceView))
