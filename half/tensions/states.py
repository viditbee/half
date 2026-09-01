"""The closed tension-state vocabulary, and what each state means (CAP-7, AD-29).

**One place, and it is this one.** Before this module the five names existed as
strings in a fixture and in whatever a caller happened to type, and nothing
produced them: ``half.store.fold`` copied a tension record's fields unchecked, so
``state="widenning"`` was as durable as ``state="widening"`` and the two ranked
identically — as nothing. The vocabulary is enumerated here, carries its own
version, and the append gate reads it from here.

**A state is a fact about a disagreement, never a verdict on either side of
it.** There is no `refuted`, no `settled`, no `correct`. A tension links two
entries that disagree *and cannot be resolved, because for a person neither is
wrong* (glossary), so nothing in this vocabulary may read as one of them having
lost. `resolved` is the closest, and it deliberately does not mean *"the main
was mistaken"* — it means one of the two entries is no longer in the ledger, so
there is no longer a pair to disagree. Adding any sixth state at all, or
changing what one means, is an Ask-First change.

**Unknown is a hard error at the append and a shrug at the read**, on the same
terms as ``half.loops.states`` and for the same reason. The log is append-only:
a state this build cannot recognise, once durable, is a value every future fold
has to keep carrying, so ``half.store.records`` refuses it before it lands. But
a log written by a *later* build — one that added a state through the Ask-First
path — must still fold, because refusing to read it would take a main's whole
store down over one word. Read tolerant, write strict.

Pure and clockless: this module imports nothing from ``half`` at all.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

#: Bumped when a state is added, removed, or changed in meaning — each of which
#: is an Ask-First change. Separate from ``store.SCHEMA_VERSION`` for the reason
#: ``loops.states.VOCABULARY_VERSION`` is: that one says which *ops* a build can
#: fold, this one says which *disagreements* it can name. A log carrying a state
#: this build has never heard of is not a log it must refuse to read — it is one
#: whose tension it cannot evaluate, which ``widening`` reports rather than
#: guesses at.
VOCABULARY_VERSION: Final[int] = 1

#: The record field a tension's state is stored in.
#:
#: Spelled here rather than imported from ``half.loops.states``, and that is a
#: decision rather than an oversight. ``state`` names **four** closed
#: vocabularies in this log — a tension's, a loop's, a crisis record's and an
#: aftercare answer's — and each package owns the spelling of its own record
#: shape, which is why ``validate_fields`` is op-aware. Importing the loops
#: constant here would make ``half.tensions`` depend on ``half.loops`` for a
#: five-character string and imply the two vocabularies were one.
#:
#: They must nonetheless *agree*, because both flow into the same field of the
#: same record, and ``tests/test_tensions.py`` asserts they do — the way
#: ``tests/test_loops.py`` asserts the ledger and the append gate agree.
STATE: Final[str] = "state"


class TensionState(StrEnum):
    """Every state a tension may be in. The set is closed.

    Ordered as a tension moves, which is a reading convenience and **not** a
    ranking: nothing compares two of these, and there is no `height` function
    here as there is on the license ladder. A tension does not get better or
    worse; it gets differently shaped.
    """

    #: Newly minted, and nothing has happened since. Every tension is born
    #: here (story 9d) and the pass never puts one back.
    FRESH = "fresh"

    #: Still open, and neither side has moved for long enough that the standing
    #: still is itself the fact. Computed from two stamps and an injected
    #: ``now`` — see ``half.tensions.widening.PERSISTENCE_DAYS``.
    PERSISTENT = "persistent"

    #: Evidence is accumulating on one side while the other has not moved.
    #: *Drift is tension velocity* (glossary), and this is the state the metric
    #: is counted from. **Computed, never judged** — it is a function of what
    #: the log holds, so two builds reading one log agree, and it moves when
    #: the main's evidence moves rather than when the model changes.
    WIDENING = "widening"

    #: Both entries have moved since the tension was last recorded. The pair
    #: the tension links is being overtaken on both sides, so the disagreement
    #: as recorded is narrowing. *Loop advancement is tensions closing*
    #: (glossary), and this is the state that metric is counted from.
    CLOSING = "closing"

    #: One of the two entries is no longer in the ledger — retracted, revised
    #: or expunged — so there is no longer a pair to disagree.
    #:
    #: **This is the one state the pass never decides.** It is the fold's
    #: answer to a correction, computed from the log the moment the correction
    #: lands (``half.store.fold``), and ``ledger.transition`` refuses it
    #: outright. It says nothing about which entry went or whether either was
    #: wrong: a `retract` is *"you changed"* and a `revise` is *"Half was wrong
    #: about you"*, and that distinction lives in the correction record where
    #: it belongs, never here.
    RESOLVED = "resolved"


#: The vocabulary as a frozen membership test. Kept separate from the enum so a
#: lookup never constructs a ``TensionState`` for input that is not one.
TENSION_STATES: Final[frozenset[str]] = frozenset(
    state.value for state in TensionState
)

#: The states the nightly pass may still move a tension out of.
#:
#: `resolved` is absent, and that is the whole of *"a resolved tension is a
#: record, not a live disagreement"*: the pass reads it, counts it, and leaves
#: it exactly as it is. There is no path from `resolved` back to any other
#: state — a corrected entry does not come back, and if the main says the thing
#: again that is a new entry and a new tension (story 9d), not this one
#: reopened.
LIVE_STATES: Final[frozenset[str]] = frozenset(
    {
        TensionState.FRESH.value,
        TensionState.PERSISTENT.value,
        TensionState.WIDENING.value,
        TensionState.CLOSING.value,
    }
)


def is_state(value: object) -> bool:
    """Whether ``value`` is a state this build knows. Never raises.

    The read-side question. Anything else is a state from a later build, and
    the caller reports it as not evaluable rather than overwriting it.
    """
    return isinstance(value, str) and value in TENSION_STATES


def parse_state(value: object) -> TensionState:
    """``value`` as a ``TensionState``, or ``ValueError``.

    The write-side question, and it raises: an unknown state is refused before
    the record is durable, never defaulted to `fresh` or to anything else. A
    default here would put a shape on a disagreement about the main's own life
    and then make it permanent.
    """
    if not is_state(value):
        raise ValueError(
            f"{value!r} is not a tension state; the vocabulary is "
            f"{', '.join(sorted(TENSION_STATES))}"
        )
    return TensionState(value)
