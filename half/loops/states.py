"""The closed loop-state vocabulary, and what each state means (CAP-6, AD-29).

**One place, and it is this one.** Before this module the four names existed
twice — as weights in ``half.retrieval.salience`` and as strings in whatever a
caller happened to type — and nothing produced them. Two spellings of the same
word is how a `stalled` loop scores as unknown while every test stays green, so
the vocabulary is enumerated here, carries its own version, and both the append
gate and the ranking weights read it from here.

**A state is not a truth value, and there is no fifth entry that would make it
one.** There is no `false`, no `refuted`, no `disproven`. *"The main has done
nothing about the farmland for a year"* is `stalled` — evidence of non-action,
which changes a loop's **state** and never its truth, because a wanting has
none to change. Nothing in Half may add a state that reads as a verdict on
whether the main really wanted the thing; adding any fifth state at all is an
Ask-First change.

**Unknown is a hard error at the append and a shrug at the read**, and the
asymmetry is the point. The log is append-only: a state this build cannot
recognise, once durable, is a value every future fold has to keep carrying, so
``half.store.records`` refuses it before it lands. But a log written by a *later*
build — one that added a state through the Ask-First path — must still fold and
still rank, degrading to ``salience.UNKNOWN_LOOP_STATE`` rather than taking a
main's retrieval down. Read tolerant, write strict.

Pure and clockless: this module imports nothing from ``half`` at all, which is
what lets ``half.store.records`` validate against it without closing a cycle
back through ``half.governance``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

#: Bumped when a state is added, removed, or changed in meaning — each of which
#: is an Ask-First change. Separate from ``store.SCHEMA_VERSION`` because the
#: two answer different questions: that one says which *ops* a build can fold,
#: this one says which *wantings* it can name. A build could gain an op without
#: gaining a state, and a log carrying a state this build has never heard of is
#: not a log it must refuse to read — it is one whose ranking degrades.
VOCABULARY_VERSION: Final[int] = 1


class LoopState(StrEnum):
    """Every state an open loop may be in. The set is closed."""

    #: Moving. Something happened on this wanting inside its own timescale.
    ADVANCING = "advancing"

    #: Not moving, and still wanted. The main has done nothing about the
    #: farmland for a year — which is a fact about *action*, not about whether
    #: the wanting is real. Nothing may promote this to a refutation.
    STALLED = "stalled"

    #: Over, and not said out loud. The most delicate state in the product:
    #: it is Half noticing that a wanting has quietly died while the main is
    #: still describing it as alive. **Never applied on inference alone**
    #: (CAP-10) — detection produces a candidate and Half asks, exactly as
    #: quarantine does. ``ledger.abandon`` refuses without both.
    ABANDONED_BUT_UNADMITTED = "abandoned-but-unadmitted"

    #: Done. Ranks lower than a live wanting and is never deleted: what the
    #: main finished is part of who they are, and the history is the record of
    #: a loop that actually closed.
    ACHIEVED = "achieved"


#: The vocabulary as a frozen membership test. Kept separate from the enum so a
#: lookup never constructs a ``LoopState`` for input that is not one.
LOOP_STATES: Final[frozenset[str]] = frozenset(state.value for state in LoopState)

#: The states a loop may still move from. Not a rule about what may be
#: appended — a main who un-achieves something is allowed, and the log would
#: record it — but the set the abandonment detector will look at, because an
#: `achieved` loop that has not moved in a year is finished, not abandoned.
LIVE_STATES: Final[frozenset[str]] = frozenset(
    {LoopState.ADVANCING.value, LoopState.STALLED.value}
)


def is_state(value: object) -> bool:
    """Whether ``value`` is a state this build knows. Never raises.

    The read-side question. Anything else is a state from a later build, and
    the caller degrades rather than failing.
    """
    return isinstance(value, str) and value in LOOP_STATES


def parse_state(value: object) -> LoopState:
    """``value`` as a ``LoopState``, or ``ValueError``.

    The write-side question, and it raises: an unknown state is refused before
    the record is durable, never defaulted to `stalled` or to anything else. A
    default here would put a word in the main's mouth about their own wanting
    and then make it permanent.
    """
    if not is_state(value):
        raise ValueError(
            f"{value!r} is not a loop state; the vocabulary is "
            f"{', '.join(sorted(LOOP_STATES))}"
        )
    return LoopState(value)
