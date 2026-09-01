"""Reading tensions, and producing the appends that move them (CAP-7, AD-3).

**A tension is moved by appends.** Nothing here edits state in place and nothing
here writes: every function returns the *fields* of a ``tension`` record,
exactly as ``half.loops.ledger`` returns the fields of a transition and
``half.governance.ladder`` the fields of a promotion, and the caller hands them
to ``Store.record`` under the main's own mutex (AD-1). That keeps the rules pure
and testable without a store, and keeps the one writer where AD-1 put it.

**The resolution rule, from this side — and it is story 8's rule inverted.** A
loop is a *wanting*; evidence cannot refute one, so ``half.store.fold`` is
structurally unable to reach the loop table from the correction path. A tension
is a claim *about two entries*; retracting one of them genuinely ends the
disagreement, so the correction path **must** reach the tension table, and it
does — in the fold, where the correction lands. The contrast is written down
rather than left to be inferred because somebody applying the loop rule here by
analogy would leave tensions standing over entries that no longer exist, and
somebody applying *this* rule over there would let a retracted belief demote a
wanting. They are opposite objects and they get opposite rules.

The consequence for this module is a signature: there is no ``resolve`` here,
and ``transition`` refuses `resolved` outright. Resolution is not something the
nightly pass decides — it is what the log already says the moment a correction
is appended, and a second path that could *also* record it would be a second
place for the two to disagree.

**Nothing here ranks the two sides.** No function takes a winner, returns one,
or writes a field naming which entry moved. ``Tension.between`` is a pair the
caller may not read positionally for meaning — ``names`` is the only question
this module answers about it — and the states themselves carry no order.

**A tension carries a license and defaults to `behave` (5a).** Nothing in this
module writes one: a transition append carries a state and nothing else, and the
fold merges it over the tension the mint created, so the license the ladder
admitted travels through untouched. What may be *said* about a tension is the
ladder's question and story 10's.

Pure and clockless: ``now`` is always injected (AD-30).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from half.errors import TensionError
from half.tensions.states import (
    LIVE_STATES,
    STATE,
    TENSION_STATES,
    TensionState,
    is_state,
    parse_state,
)
from half.tensions.widening import (
    BETWEEN,
    SIDES,
    Drift,
    Evidence,
    drift,
    evidence,
)


@dataclass(frozen=True, slots=True)
class Tension:
    """One tension as the fold holds it. A read-only value.

    The raw fields travel unconverted — ``state`` is whatever string the log
    carries, including one from a later build — because this type is on the
    read path and the read path is tolerant. The append gate is where a state
    has to be one of the five.
    """

    id: str
    state: str | None = None
    #: The two entries this tension links. A tuple because the log carries a
    #: list, and **its order carries no meaning**: nothing in Half reads
    #: ``between[0]`` as the first, the stated, the true or the winning side.
    between: tuple[str, ...] = ()
    #: The stamp on the record that set the current state — the baseline every
    #: computation here measures from.
    at: str | None = None

    @property
    def known_state(self) -> bool:
        """Whether this build recognises the state. False for a later build's."""
        return is_state(self.state)

    @property
    def live(self) -> bool:
        """Whether the pass may still move this tension. False once resolved."""
        return self.state in LIVE_STATES

    @property
    def paired(self) -> bool:
        """Whether this tension names two distinct entries — i.e. is a tension.

        A record naming one entry, three, or the same one twice is not a
        disagreement between two entries, and ``drift`` reports it as not
        computable rather than inventing the missing half.
        """
        return len(self.between) == SIDES and len(set(self.between)) == SIDES

    def names(self, entry_id: object) -> bool:
        """Whether ``entry_id`` is one of this tension's two sides.

        The only question this module answers about the pair, and it is
        deliberately a membership test rather than an accessor: *which* side an
        entry is has no meaning here, and an accessor would invite a caller to
        act on it.
        """
        return isinstance(entry_id, str) and entry_id in self.between


@dataclass(frozen=True, slots=True)
class Plan:
    """What a pass would append over one main's tensions, and what it would not.

    A value: computing it writes nothing and touches no store, which is what
    lets the pass be tested without one and lets *"the same log and the same
    ``now`` produce the same states"* be asserted as an equality rather than as
    a re-run.
    """

    #: Tension id -> the fields of the append that moves it. Empty when the log
    #: says nothing has changed, which is the ordinary case and not a failure.
    transitions: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    #: Tension id -> why it could not be evaluated. **Their states are left
    #: exactly as they are**, they are counted, and they never stop the rest.
    incomputable: Mapping[str, str] = field(default_factory=dict)
    #: Tensions the log computed to the state they already hold. Reported
    #: separately from ``incomputable`` because *"nothing changed"* and *"we
    #: cannot tell"* are different facts and only one of them is a gap.
    unchanged: tuple[str, ...] = ()

    @property
    def moves(self) -> int:
        return len(self.transitions)


def read(tensions: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Tension]:
    """The folded tension table as ``Tension`` values, id-keyed.

    Takes ``State.tensions`` — the same shape from a fold or from SQLite.
    Tolerant: an entry whose fields are the wrong type keeps the tension and
    drops the field, because one malformed record must cost that tension its
    evaluation and not the whole pass. Never raises.
    """
    if not isinstance(tensions, Mapping):
        return {}
    found: dict[str, Tension] = {}
    for ident, entry in tensions.items():
        if not isinstance(ident, str) or not ident:
            continue
        fields: Mapping[str, Any] = entry if isinstance(entry, Mapping) else {}
        found[ident] = Tension(
            id=ident,
            state=_text(fields.get(STATE)),
            between=_pair(fields.get(BETWEEN)),
            at=_text(fields.get("t")),
        )
    return found


def sides(
    tension: Tension, *, history: Sequence[Mapping[str, Any]] | None
) -> tuple[Evidence, ...]:
    """What each of ``tension``'s entries cited then and now, from the log.

    Order follows the record, and means nothing — see ``Tension.between``. The
    tuple exists so ``drift`` can count how many sides moved; nothing indexes
    into it.
    """
    if not isinstance(tension, Tension) or not tension.paired:
        return ()
    return tuple(
        evidence(history, side=side, at=tension.at) for side in tension.between
    )


def evaluate(
    tension: Tension, *, history: Sequence[Mapping[str, Any]] | None, now: object
) -> Drift:
    """What the log says about ``tension`` at ``now``.

    The read half of the pass, and pure: the same log, the same tension and the
    same ``now`` give the same answer for ever, which is what makes the pass
    re-runnable without a second transition landing (AD-30).
    """
    if not isinstance(tension, Tension):
        return Drift(reason="not-a-tension")
    return drift(
        state=tension.state,
        recorded_at=tension.at,
        sides=sides(tension, history=history),
        now=now,
    )


def transition(tension: Tension, *, to: object) -> dict[str, Any]:
    """The fields of the append that moves ``tension`` to ``to``.

    Returns fields; writes nothing. The caller appends them **under the
    tension's own id**, so the fold merges the new state over the record the
    mint created and the pair, the license and everything else the tension
    carries travel forward untouched. A transition that re-stated the whole
    tension would be a mint wearing a transition's name.

    Refused, loudly, when:

    * ``to`` is outside the vocabulary — a sixth state, once durable, is a
      disagreement every future fold carries and no build can name;
    * ``to`` is `resolved` — that is the fold's answer to a correction and
      nothing else records it, so a second writer here would be a second place
      for the log and the fold to disagree;
    * ``to`` is the state the tension is already in — a record that changes
      nothing is a record that says something happened, and the nightly pass
      runs every night. The same refusal ``ledger.rescale`` makes, one object
      over, and it is what keeps a re-run from filling the log with the same
      fact.

    There is deliberately **no argument naming a side.** Not a winner, not the
    entry that moved, not the one that stood still. A tension is a fact about a
    situation and never a judgement of either entry (constitution: *name the
    gap, never render the verdict*), and a field here saying which one moved
    would be exactly that judgement made durable.
    """
    if not isinstance(tension, Tension):
        raise TensionError("transition: expected a Tension")
    target = _state(to, "transition")
    if target is TensionState.RESOLVED:
        raise TensionError(
            "transition: a tension is not moved to resolved; resolution is "
            "what a correction to one of its two entries already means, and "
            "the fold records it the moment that correction lands"
        )
    if tension.state == str(target):
        raise TensionError(
            f"transition: {tension.id!r} is already {target}; a record that "
            f"changes nothing is a record that says something happened, and "
            f"this runs every night"
        )
    return {STATE: str(target)}


def plan(
    tensions: Mapping[str, Tension] | None,
    *,
    history: Sequence[Mapping[str, Any]] | None,
    now: object,
) -> Plan:
    """Every append one pass over ``tensions`` would make, and every one it
    would not.

    Pure, total, and it never raises: a tension this build cannot evaluate is
    counted in ``incomputable`` with its reason and **its state is left alone**,
    because the alternative to reporting is guessing and a guess here is Half
    telling a main their life is drifting on the strength of a record it could
    not read.

    A `resolved` tension is counted as incomputable-by-reason rather than
    skipped silently: *"there were four we did not look at"* is a fact the pass
    should be able to state, and a tension quietly absent from every count is
    how a whole state stops being exercised.
    """
    if not isinstance(tensions, Mapping):
        return Plan()
    moves: dict[str, dict[str, Any]] = {}
    gaps: dict[str, str] = {}
    still: list[str] = []
    for ident, tension in sorted(tensions.items()):
        if not isinstance(tension, Tension):
            gaps[str(ident)] = "not-a-tension"
            continue
        found = evaluate(tension, history=history, now=now)
        if not found.computable:
            gaps[ident] = found.reason or "unknown"
            continue
        if found.state == tension.state:
            still.append(ident)
            continue
        try:
            moves[ident] = transition(tension, to=found.state)
        except TensionError as exc:  # pragma: no cover - drift cannot produce one
            # ``drift`` never computes `resolved` and never returns a state
            # outside the vocabulary, so this is unreachable today. It is here
            # because the alternative to catching it is one malformed tension
            # ending the pass for every other one this main has, and AD-9's
            # isolation rule is about mains rather than an excuse to drop it
            # inside one.
            gaps[ident] = str(exc)
    return Plan(transitions=moves, incomputable=gaps, unchanged=tuple(still))


def resolved_by(
    tensions: Mapping[str, Tension] | None, *, entry_id: object
) -> tuple[str, ...]:
    """Every tension ``entry_id`` is a side of, id-ordered.

    The predicate the fold applies when a correction lands, expressed here so
    that *"a correction resolves a tension"* is one rule in one place rather
    than a condition spelled into three branches of a match statement.

    It names no winner and reads no correction verb. A `retract` (*"you
    changed"*) and a `revise` (*"Half was wrong about you"*) resolve a tension
    identically, because the difference between them is what Half owes the main
    and not which of two entries about their life was mistaken — and the log
    keeps that distinction on the correction record, where whoever composes the
    apology reads it.
    """
    if not isinstance(tensions, Mapping) or not isinstance(entry_id, str):
        return ()
    return tuple(
        sorted(
            ident
            for ident, tension in tensions.items()
            if isinstance(tension, Tension) and tension.names(entry_id)
        )
    )


def _text(value: object) -> str | None:
    """A field as a non-empty string, or ``None``. Never raises."""
    if isinstance(value, str) and value.strip():
        return value
    return None


def _pair(value: object) -> tuple[str, ...]:
    """The ``between`` field as a tuple of ids. Tolerant; never raises.

    Order is preserved because the log's order is preserved, not because it
    means anything.
    """
    if isinstance(value, (list, tuple)):
        return tuple(
            item for item in value if isinstance(item, str) and item.strip()
        )
    return ()


def _state(value: object, what: str) -> TensionState:
    try:
        return parse_state(value)
    except ValueError as exc:
        raise TensionError(f"{what}: {exc}") from None


#: Re-exported so a caller holding only this module can still ask the
#: membership question without importing the vocabulary twice.
__all__ = [
    "Plan",
    "Tension",
    "TENSION_STATES",
    "evaluate",
    "plan",
    "read",
    "resolved_by",
    "sides",
    "transition",
]
