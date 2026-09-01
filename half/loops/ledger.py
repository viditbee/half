"""Opening, moving and reading open loops (CAP-6, CAP-10, AD-3).

**A loop is opened, moved and closed by appends.** Nothing here edits state in
place and nothing here writes: every function returns the *fields* of a
``loop_transition`` record, exactly as ``half.governance.ladder`` returns the
fields of a belief append, and the caller hands them to ``Store.record`` under
the main's own mutex (AD-1). That keeps the rules pure and testable without a
store, and keeps the one writer where AD-1 put it.

**The refutation firewall, from this side.** A wanting is not a fact, and
nothing may refute one. There is no function in this module that lowers a loop
on the strength of evidence, no argument through which a belief's retraction
could reach a loop's state, and no state that means *false* — see
``half.loops.states``. The other side of the firewall is in ``half.store.fold``,
where a correction op is structurally unable to touch the loop table. Both
sides exist because agreeing with the rule is easy and violating it by accident
is easier: the natural implementation of a nightly pass that sees no movement is
to lower confidence in the belief that the loop exists.

**Evidence of non-action changes state, never truth.** A main who has done
nothing about the farmland for a year has a `stalled` loop. ``move`` is how that
is recorded, and it is the only path — there is no ``refute``, no ``demote``, no
``decay``.

**`abandoned-but-unadmitted` is never applied on inference alone.** Detection
produces an ``AbandonmentCandidate``, which carries no authority and changes
nothing; applying it needs the candidate *and* the main's answer, which
``abandon`` requires as two arguments with no defaults — the rule expressed as a
signature rather than as a check somebody has to remember. This is quarantine's
shape one object over (CAP-10), and the reference implementation
(gbrain's ``abandoned_threads``) is where the *detection* comes from and where
Half deliberately parts company: gbrain reports the count and moves on, Half
must ask before it records anything.

**Movement is not contact.** ``move`` records that the *loop* moved. What Half
has raised, and how recently, is a different fact with a different record, and
it is story 5c's nagging bound. Nothing here reads or writes it.

Pure and clockless: ``now`` is always injected (AD-30).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from enum import StrEnum

from half.errors import LoopError
from half.loops.states import LIVE_STATES, STATE, LoopState, is_state, parse_state
from half.loops.timescale import (
    LAST_MOVEMENT,
    TIMESCALE,
    Silence,
    Timescale,
    is_timescale,
    moment,
    parse_timescale,
)
from half.loops.timescale import silence as silence_of

#: The field a loop-transition record names its loop in. Owned here — the other
#: three are owned beside the things they describe, in ``states`` and
#: ``timescale``, and imported above. One definition per name: two spellings is
#: how an append lands in the log carrying a loop nothing can find.
LOOP: Final[str] = "loop"

#: How many of a loop's **own periods** of silence make abandonment worth
#: asking about. Twelve, which for a months-loop is gbrain's twelve months
#: exactly — the reference this is lifted from — and which for a years-loop is
#: twelve years and for a days-loop twelve days. That is the whole point of
#: counting in periods: one number that means the right thing for a wanting
#: that moves in days and for one that moves in decades, where twelve *months*
#: would nag the first and never reach the second.
#:
#: It is a threshold for *raising a question*, never for recording anything.
#: The value is pinned, and both sides of the boundary are asserted: review
#: found anything between roughly six and thirteen passed the suite, which is a
#: band rather than a number, and a threshold nobody can be wrong about is a
#: threshold nobody chose.
ABANDONMENT_PERIODS: Final[float] = 12.0


class Answer(StrEnum):
    """What the main said when Half asked whether a wanting was over.

    A boolean was not enough, and the gap it left is the one that matters most
    in the product. ``abandon(answered=True)`` recorded only that *an answer
    came back* — so a caller wiring *"no, I still want this"* into the obvious
    place recorded abandonment on the strength of the main denying it. For the
    most delicate state in the ledger the flag has to carry the **sense** of the
    answer, not its arrival.
    """

    #: *"Yes — I've let that go."* The only value that records anything.
    CONFIRMED = "confirmed"
    #: *"No, I still want this."* Records nothing here. What a denial *does*
    #: mean — the loop is alive and Half was wrong about it — is a movement the
    #: main's own turn produces, not something this module infers from a no.
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class Loop:
    """One open loop as the fold holds it. A read-only value.

    The raw fields travel unconverted — ``state`` is whatever string the log
    carries, including one from a later build — because this type is on the read
    path and the read path is tolerant. The append gate is where a state has to
    be one of the four.
    """

    id: str
    state: str | None = None
    timescale: str | None = None
    last_movement: str | None = None

    @property
    def known_state(self) -> bool:
        """Whether this build recognises the state. False for a later build's."""
        return is_state(self.state)

    @property
    def detectable(self) -> bool:
        """Whether silence is computable at all — i.e. whether it has a period."""
        return is_timescale(self.timescale)

    def silence(self, *, now: object) -> Silence:
        """Whether this loop has been quiet past its own period at ``now``."""
        return silence_of(
            {
                TIMESCALE: self.timescale,
                LAST_MOVEMENT: self.last_movement,
            },
            now=now,
        )


@dataclass(frozen=True, slots=True)
class AbandonmentCandidate:
    """A loop inference thinks the main has quietly given up on, and why.

    A candidate is **not** a transition. It carries no authority, changes
    nothing, and is not in the log — it exists so that a loop silent for twelve
    of its own periods has somewhere to land while Half asks about it. The
    asking is story 10; this type is the handoff, and ``abandon`` is the only
    thing that consumes it.
    """

    loop_id: str
    reason: str
    #: How many of the loop's own periods it has been silent. Carried so that
    #: whoever puts the question can say *"a year"* or *"a fortnight"* without
    #: recomputing it against a clock.
    periods: float
    #: The ``now`` the candidate was raised at, and the ``last_movement`` it was
    #: raised **against**. Both exist because a candidate outlives the moment it
    #: was made: Half raises it, asks, and the main answers on some later turn —
    #: possibly after having gone and *done* the thing. Without these, answering
    #: a fortnight-old question recorded abandonment on a loop that had since
    #: advanced, and the staleness was not merely unchecked but undetectable.
    #: ``abandon`` refuses when the loop has moved since.
    raised_at: str
    against_movement: str | None


def read(loops: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Loop]:
    """The folded loop table as ``Loop`` values, id-keyed.

    Takes ``State.loops`` or ``Store.loops()`` — the same shape either way.
    Tolerant: an entry whose fields are the wrong type keeps the loop and drops
    the field, because the open-loop ledger is the ranking function for
    everything Half does and one malformed entry must cost a tie-break, not a
    main's whole ranking (AD-24).
    """
    if not isinstance(loops, Mapping):
        return {}
    found: dict[str, Loop] = {}
    for ident, entry in loops.items():
        if not isinstance(ident, str) or not ident:
            continue
        fields: Mapping[str, Any] = entry if isinstance(entry, Mapping) else {}
        found[ident] = Loop(
            id=ident,
            state=_text(fields.get(STATE)),
            timescale=_text(fields.get(TIMESCALE)),
            last_movement=_text(fields.get(LAST_MOVEMENT)),
        )
    return found


def opened(
    loop_id: str,
    *,
    state: object,
    loops: Mapping[str, Any],
    timescale: object = None,
    last_movement: object = None,
) -> dict[str, Any]:
    """The fields of the append that opens ``loop_id``. Refuses to re-open.

    ``loops`` is the current loop table — ``State.loops`` or ``Store.loops()`` —
    and it is **required**, the way ``ladder.promote`` requires the belief it is
    promoting. Without it ``opened`` and ``move`` were indistinguishable at the
    log: the fold merges by ``setdefault``, so re-opening a live loop silently
    overwrote its state and its timescale, dropped its ``last_movement``, and
    raised nothing. A loop can be opened once. Everything after that is a move.

    ``state`` is required and must be one of the four: a loop opened without one
    is a wanting the ranking function cannot weigh, and a loop opened with a
    fifth is a durable value nothing will ever recognise.
    `abandoned-but-unadmitted` is refused here as it is in ``move`` — the CAP-10
    rule was one function wide, so a loop could be *opened* straight into the
    state that exists to be asked about.

    ``timescale`` is **optional and never defaulted**. Recording a loop with no
    period is honest — ``silence`` reports it as not detectable and says which
    piece is missing — where a default would hide the gap behind a number that
    is right for somebody else's wanting.
    """
    ident = _loop_id(loop_id, "opened")
    if not isinstance(loops, Mapping):
        raise LoopError(
            "opened: the current loop table is required; without it opening and "
            "moving are the same append and a live loop is silently overwritten"
        )
    if ident in loops:
        raise LoopError(
            f"opened: {ident!r} is already open; use move() to record movement "
            f"on it. Re-opening would overwrite its state and its timescale "
            f"with no record that anything was lost"
        )
    fields: dict[str, Any] = {
        LOOP: ident,
        STATE: str(_live_state(state, "opened")),
    }
    if timescale is not None:
        fields[TIMESCALE] = str(_timescale(timescale, "opened"))
    if last_movement is not None:
        fields[LAST_MOVEMENT] = _stamp(last_movement, "opened")
    return fields


def move(loop_id: str, *, at: object, state: object = None) -> dict[str, Any]:
    """The fields of the append that records movement on ``loop_id``.

    ``at`` is when the loop moved, and it is required — movement with no date is
    not computable against a timescale, so it would be a claim nothing could
    ever check. It is the caller's stamp, never a clock read here.

    ``state`` is optional: a loop can move without changing state, and most do.
    Passing `abandoned-but-unadmitted` is refused outright — that state has its
    own path, ``abandon``, which requires the main — and so is passing it here
    dressed as ordinary movement.

    **There is deliberately no ``timescale`` argument.** It used to be here, as
    the way a loop that was opened without a period acquired one, and it meant a
    single ordinary-looking movement append could flip a years-loop to days —
    making it instantly silent, instantly abandonment-eligible, and looking on
    the record exactly like the main having done something. Changing how fast a
    wanting is *supposed* to move is a judgement about the wanting, not a
    movement in it, so it has its own named call: ``rescale``.
    """
    fields: dict[str, Any] = {
        LOOP: _loop_id(loop_id, "move"),
        LAST_MOVEMENT: _stamp(at, "move"),
    }
    if state is not None:
        fields[STATE] = str(_live_state(state, "move"))
    return fields


def rescale(loop_id: str, *, to: object, loops: Mapping[str, Any]) -> dict[str, Any]:
    """The fields of the append that gives ``loop_id`` a period, or a new one.

    Its own operation rather than an argument to ``move``, because it is not
    movement: it is Half's or the main's judgement about how fast this wanting
    is *supposed* to go, and it changes whether every future silence check fires.
    Riding along with a movement append made that invisible.

    Refuses a loop it cannot see, and refuses a no-op, so that a rescale in the
    log is always a real change somebody meant. It carries no ``last_movement``:
    re-scaling a loop is not the loop moving, and writing a date here would
    reset the very silence the new period is there to measure.
    """
    ident = _loop_id(loop_id, "rescale")
    if not isinstance(loops, Mapping) or ident not in loops:
        raise LoopError(
            f"rescale: {ident!r} is not an open loop; a period belongs to a "
            f"wanting that exists"
        )
    target = _timescale(to, "rescale")
    entry = loops[ident]
    current = entry.get(TIMESCALE) if isinstance(entry, Mapping) else None
    if current == str(target):
        raise LoopError(
            f"rescale: {ident!r} is already on {target}; a record that changes "
            f"nothing is a record that says something happened"
        )
    return {LOOP: ident, TIMESCALE: str(target)}


def abandonment_candidate(
    loop: Loop, *, now: object, periods: float = ABANDONMENT_PERIODS
) -> AbandonmentCandidate | None:
    """A candidate for ``loop``, or ``None`` if there is nothing to propose.

    Pure and inert: it reads the loop, returns a value, and records nothing.
    This is the shape lifted from gbrain's ``abandoned_threads`` check — a
    high-conviction item, long past its own horizon, unsuperseded — with the one
    difference that matters: gbrain reports it, and Half must ask before
    anything is written.

    ``None`` for every case where the answer would be a guess:

    * a loop whose silence is not detectable — no timescale, no movement, or a
      stamp that is not a real instant. There is no path from *"we cannot
      tell"* to *"the main has given up"*;
    * a loop inside the threshold;
    * a loop that is `achieved` — finished is not abandoned — or already
      `abandoned-but-unadmitted`, which needs no second candidate;
    * a loop whose state this build does not recognise, which is a later
      build's business and not something to overwrite on inference.
    """
    if not isinstance(loop, Loop):
        return None
    if not _positive(periods):
        # Zero, a negative, or a NaN would each make *every* loop a candidate —
        # NaN because every comparison against it is false, so the threshold
        # below stops rejecting anything. A threshold that cannot say no is not
        # a threshold, and this one guards the most delicate state there is.
        raise LoopError(
            f"abandonment_candidate: {periods!r} is not a number of periods; "
            f"a threshold of zero or less proposes that the main has given up "
            f"on everything"
        )
    if loop.state not in LIVE_STATES:
        return None
    quiet = loop.silence(now=now)
    if not quiet.detectable or quiet.periods is None:
        return None
    if quiet.periods < periods:
        return None
    return AbandonmentCandidate(
        loop_id=loop.id,
        reason=(
            f"silent for {quiet.periods:.1f} of its own periods "
            f"({loop.timescale}); nothing has moved it since "
            f"{loop.last_movement}"
        ),
        periods=quiet.periods,
        raised_at=str(now),
        against_movement=loop.last_movement,
    )


def abandon(
    loop: Loop, *, candidate: AbandonmentCandidate, answered: Answer
) -> dict[str, Any]:
    """The fields of the append that records ``loop`` as abandoned-but-unadmitted.

    Both arguments are required and neither has a default, which is the rule
    *"Half never records abandonment on inference alone"* expressed as a
    signature rather than as a check somebody has to remember: it needs a
    candidate to have been raised **and** the main to have answered. This is
    ``ladder.quarantine``'s shape, deliberately, because it is the same
    governance rule about the same kind of mistake (CAP-10).

    ``answered`` is an ``Answer``, not a boolean, and a bare ``True`` is refused.
    A boolean recorded that *an answer arrived*, so the obvious wiring of
    *"no, I still want this"* recorded abandonment on the strength of the main
    denying it — the worst single mistake available in this module.

    **The candidate must still be current.** A candidate outlives the moment it
    was raised: Half asks, and the main answers on a later turn, possibly having
    gone and done the thing in between. So this refuses when the loop's
    ``last_movement`` is no longer the one the candidate was raised against —
    the loop has moved, the question is about a different loop than the one in
    front of us, and the main's *"yes"* was about the old one.

    Note what this does **not** carry: no ``last_movement``. Admitting that a
    wanting is over is not the wanting moving, and writing a movement date here
    would reset the very silence that raised the question.
    """
    if not isinstance(loop, Loop):
        raise LoopError("abandon: expected a Loop")
    if not isinstance(candidate, AbandonmentCandidate):
        raise LoopError(
            "abandon: inference alone never records abandonment; a candidate "
            "must have been raised and put to the main"
        )
    if candidate.loop_id != loop.id:
        raise LoopError(
            f"abandon: candidate names {candidate.loop_id!r}, not {loop.id!r}"
        )
    if not isinstance(answered, Answer):
        raise LoopError(
            "abandon: the main's answer must be an Answer, not a flag. A "
            "boolean says only that a reply arrived, and 'no, I still want "
            "this' is a reply"
        )
    if answered is not Answer.CONFIRMED:
        raise LoopError(
            f"abandon: the main answered {answered.value!r}; only a confirmed "
            f"'yes, I've let that go' records abandonment"
        )
    if candidate.against_movement != loop.last_movement:
        raise LoopError(
            f"abandon: {loop.id!r} has moved since the candidate was raised "
            f"at {candidate.raised_at} (movement was "
            f"{candidate.against_movement!r}, is now {loop.last_movement!r}); "
            f"raise it again against the loop as it is now"
        )
    return {
        LOOP: loop.id,
        STATE: str(LoopState.ABANDONED_BUT_UNADMITTED),
    }


def expunged(loop_id: str) -> dict[str, Any]:
    """The fields of the ``expunge`` append that removes ``loop_id`` entirely.

    A loop leaves the fold only through an expunge that names it **as a loop**,
    which is the firewall's write side: ``target`` alone removes a belief or a
    tension, and it takes this second, explicit field to reach the loop table.
    An expunge aimed at a belief can therefore never take a wanting with it, no
    matter what its identifier happens to be.

    Rare and main-initiated, like every expunge — and reached through
    ``Store.expunge``, which is the public erase path and which builds this
    record itself when the name the main gave it is a loop the fold can see. A
    caller assembling it by hand is not the normal route; that route also
    tombstones the transition bodies, which an op alone does not.
    """
    ident = _loop_id(loop_id, "expunged")
    # ``loop`` alone, with **no** ``target``. A loop-only erasure that also
    # wrote its slug into ``target`` would land in the belief namespace and
    # suppress every later belief sharing the name — the collision the split
    # ``expunged`` sets exist to prevent, arriving from the other side. The
    # fold accepts an expunge with no target precisely when it names a loop.
    return {LOOP: ident}


def silent(
    loops: Mapping[str, Loop] | None, *, now: object
) -> dict[str, Silence]:
    """Every **live** loop that has been quiet past its own period, id-keyed.

    The ranking input, and the whole reason the ledger exists — which is exactly
    why the filter is not just *detectable and silent*:

    * **Live states only.** An `achieved` loop that has not moved in a year is
      finished, not silent, and an `abandoned-but-unadmitted` one has already
      been asked about and answered. Reporting either as silent would have
      stories 9 and 10 raising a wanting the main already completed, which is
      the single most trust-destroying thing this ranking input could produce.
      A loop whose state this build cannot read is out too: it belongs to a
      later build, and inferring anything about it is a guess.
    * **Undetectable is absent, not false.** *"We cannot tell"* is not *"it is
      fine"*, and a caller that wants the difference asks ``Loop.silence``
      directly and reads the reason.
    """
    if not isinstance(loops, Mapping):
        return {}
    found: dict[str, Silence] = {}
    for ident, loop in loops.items():
        if not isinstance(loop, Loop) or loop.state not in LIVE_STATES:
            continue
        quiet = loop.silence(now=now)
        if quiet.detectable and quiet.silent:
            found[ident] = quiet
    return found


def _text(value: object) -> str | None:
    """A field as a non-empty string, or ``None``. Never raises."""
    if isinstance(value, str) and value.strip():
        return value
    return None


def _loop_id(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise LoopError(
            f"{what}: a loop id is a non-empty slug with no surrounding "
            f"whitespace, got {value!r}"
        )
    if any(character.isspace() for character in value):
        raise LoopError(f"{what}: a loop id carries no whitespace, got {value!r}")
    return value


def _state(value: object, what: str) -> LoopState:
    try:
        return parse_state(value)
    except ValueError as exc:
        raise LoopError(f"{what}: {exc}") from None


def _live_state(value: object, what: str) -> LoopState:
    """A state a caller may set without the main, or a refusal.

    `abandoned-but-unadmitted` is the one state inference may never apply, and
    the check belongs on **every** function that sets a state rather than on the
    one somebody thought of. It used to live only in ``move``, so ``opened``
    could put a loop straight into the state that exists to be asked about —
    the CAP-10 gate was one function wide.
    """
    target = _state(value, what)
    if target is LoopState.ABANDONED_BUT_UNADMITTED:
        raise LoopError(
            f"{what}: abandoned-but-unadmitted is never applied on inference "
            f"alone; raise a candidate and ask the main (see abandon)"
        )
    return target


def _positive(value: object) -> bool:
    """A real, strictly positive number. ``NaN`` answers ``False``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value > 0 and value == value  # noqa: PLR0124 - the NaN test


def _timescale(value: object, what: str) -> Timescale:
    try:
        return parse_timescale(value)
    except ValueError as exc:
        raise LoopError(f"{what}: {exc}") from None


def _stamp(value: object, what: str) -> str:
    """A movement date, refused rather than defaulted if it is not one.

    Refused at the caller rather than at the append for the reason the state is:
    the log is append-only, so a movement date nothing can read is a loop whose
    silence — and therefore whose nagging bound — is uncomputable for ever.
    """
    if not isinstance(value, str) or moment(value) is None:
        raise LoopError(
            f"{what}: {value!r} is not a movement date; a stored stamp is "
            "ISO-8601 UTC (YYYY-MM-DD or YYYY-MM-DDThh:mmZ)"
        )
    return value
