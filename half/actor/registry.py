"""One actor per main: an inbox plus a mutex (AD-8).

An actor is not a process and not a task. It is a lock and a hydrated store,
keyed by ``main_id``. One worker holds many; a dormant one is a dict entry
costing nothing, and hibernation is simply eviction from the LRU.

Two invariants the registry exists to hold:

*Single writer* (AD-1). Every mutation for a main passes through that main's
mutex, so an append never races another. This is the decision that lets the
store skip a journal, precondition hashes and rollback.

*Eviction never interrupts a turn* (AD-33). Eviction requires a free mutex.
Dropping an actor mid-turn would lose an in-flight reply, or worse, evict
between a model call and its log append and lose work already paid for.
"""

from __future__ import annotations

import asyncio
import re

from half import civil
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, AsyncIterator

from half.errors import StoreError, TensionError, TouchError, TrustError
from half.governance.aftercare import FLOOR_DAYS, answered, at_least, entered_at
from half.governance.ladder import (
    TOP,
    Ceiling,
    License,
    ceiling_fields,
    height,
    next_rung,
)
from half.retrieval.prefix import build_prefix
from half.retrieval.rank import RetrievalSwitch
from half.retrieval.strands import Strands
from half.store.ops import (
    AFTERCARE_AGREED,
    AFTERCARE_ASKED,
    AFTERCARE_DECLINED,
    AFTERCARE_STATES,
    CRISIS_ENTERED,
    CRISIS_REVERSED,
    Op,
)
from half.store.records import (
    ABOUT,
    ASKED_FIELDS,
    NEXT_PASS_AT,
    PASS_RAN,
    QUESTION,
    TOUCH_FIELDS,
    handoff_projection,
    handoff_record,
    history_projection,
    mint_projection,
    plan_projection,
    plan_record,
    zone_projection,
    zone_record,
)
from half.consolidate.candidates import MintView
from half.store.fold import fold as fold_records
from half.store.store import Store
from half.surface.touch import spoken_on
from half.surface.view import (
    CLAIM_ALREADY,
    CLAIM_CRISIS,
    CLAIMED,
    SurfaceView,
    narrowed,
)
from half.questions.answered import history as ask_history_of
from half.questions.engine import QuestionView
from half.tensions.states import STATE as TENSION_STATE
from half.trust.balance import balance as trust_balance
from half.trust.unasked import (
    ASK_CRISIS,
    ASK_NOT_PERMITTED,
    ASK_RECORDED,
    ASK_UNAFFORDABLE,
    TrustView,
    may_be_raised,
    narrowed_for_trust,
)

def _free_ask_id(t: str, taken: set[str]) -> str:
    """The first spend id at ``t`` that no record already holds (CAP-4).

    ``qa_<t>``, then ``qa_<t>_1``, ``qa_<t>_2`` — the shape ``claim_day`` uses
    for a batch of touches, and content-free for the reason a touch id is: a
    tombstone keeps a record's id, so anything in it survives the erasure that
    exists to remove it.

    It exists because ``qa_<t>`` alone collides. Two questions can be affordable
    in one second now that the queue can offer more than one, and ``Op.ASKED``
    is append-keyed, so two records sharing an id are two bodies a single
    ``expunge_bodies`` erases together.

    Deterministic given the log: the caller computes ``taken`` under the main's
    own mutex, so two turns cannot pick the same suffix.
    """
    ident = f"qa_{t}"
    suffix = 0
    while ident in taken:
        suffix += 1
        ident = f"qa_{t}_{suffix}"
    return ident


#: A main_id becomes a directory name, so it is validated before it can reach
#: the filesystem. It arrives from configuration, which is operator input, and
#: an unvalidated '..' walks the store tree straight out of its root.
_SAFE_MAIN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def validate_main_id(main_id: str) -> str:
    if not _SAFE_MAIN_ID.fullmatch(main_id):
        raise StoreError(
            f"unsafe main_id {main_id!r}: letters, digits, dash and underscore only"
        )
    return main_id

def _note_aftercare(actor: "Actor", *, t: str, state: str) -> None:
    """Append one aftercare record.

    The id carries the state as well as the stamp. Stored stamps are
    minute-resolution, so a question put and answered inside one minute would
    otherwise be two records with one id — and while the fold's last-write-wins
    happens to keep the right one, a log where two different facts share an
    identifier is a log that cannot be read back.
    """
    actor.store.record(Op.AFTERCARE, f"ac_{actor.main_id}_{t}_{state}", t, state=state)


def _stamp_of(record: Mapping[str, Any] | None) -> str | None:
    """The ``t`` a folded record carries, or ``None``."""
    if not isinstance(record, Mapping):
        return None
    stamp = record.get("t")
    return stamp if isinstance(stamp, str) else None


def mode_is_open(record: Mapping[str, Any] | None) -> bool:
    """Whether a folded ``crisis`` record leaves the mode open.

    The one reader of that field's shape, so the fold, the registry and the
    gate cannot disagree about what "in the mode" means. Named apart from
    ``ActorRegistry.crisis_open`` on purpose: that one reaches a main's store,
    this one reads a record somebody already has. Fail-closed on
    anything unreadable: a record this build cannot parse is treated as an
    *open* mode, because the cost of reading an open mode as closed is
    answering a main in crisis through the ordinary pipeline.
    """
    if record is None:
        return False
    if not isinstance(record, Mapping):
        return True
    return record.get("state") != CRISIS_REVERSED


#: How many hydrated actors a worker holds before evicting the least recent.
DEFAULT_CAPACITY = 256


@dataclass(slots=True)
class Actor:
    """One main's hydrated state."""

    main_id: str
    store: Store
    #: What this main's conversation is currently about, as weights (CAP-1).
    #: Volatile by AD-26: never logged, never projected, and gone when the
    #: actor is evicted — which is correct, because how the main is right now
    #: is not a belief. A restart begins with no strand weighted, and the
    #: floor in ``strand_weight`` means that costs reach, not results.
    strands: Strands = field(default_factory=Strands)
    #: Whether ledger retrieval is permitted for *this main* (CAP-12). One
    #: switch per actor, not per worker: a single shared switch meant one
    #: main's crisis disabled retrieval for every other main the process was
    #: serving, which is a silent, total memory outage for uninvolved people.
    #:
    #: **Hydrated, not defaulted.** The switch used to be born enabled on every
    #: hydration, so an eviction under memory pressure re-enabled the retrieval
    #: a crisis had "hard-disabled" — the same defect the ceiling had before it
    #: was moved into the log, one field over. It is now read from the crisis
    #: record at hydration, which is what makes *hard* mean hard.
    retrieval: RetrievalSwitch = field(default_factory=RetrievalSwitch)
    #: The one global license cap for *this main* (AD-28). Beside ``strands``
    #: and ``retrieval`` for the same reason both are here: it is per main, so
    #: one main's aftercare cannot cap another's, and it belongs to the actor
    #: that owns them rather than to the worker that happens to host both.
    #:
    #: **Unlike those two, it is not volatile.** ``strands`` and ``retrieval``
    #: are how the main is right now and may be lost on eviction (AD-26); a
    #: ceiling is a governance decision that runs for thirty days, and eviction
    #: is routine at any real capacity. So this field is *hydrated from the
    #: store*, and every change to it goes through ``ActorRegistry`` and into
    #: the log. Assigning it directly would neither persist nor survive the next
    #: rehydration, which is why nothing outside the registry does.
    ceiling: Ceiling = field(default_factory=Ceiling)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: Turns holding *or waiting for* the lock. Incremented before the acquire
    #: and decremented after the release, so it is never zero while any turn
    #: still needs this actor.
    claims: int = 0

    @property
    def busy(self) -> bool:
        """True while any turn holds or awaits this actor.

        ``lock.locked()`` alone is not enough, and the gap is not theoretical:
        ``asyncio.Lock.release()`` clears its flag and merely *schedules* the
        next waiter, which sets it again only when it resumes. An actor evicted
        in that window has its store closed under a turn that is about to run,
        and the next acquire hydrates a second Actor with a second lock for the
        same main — two writers on one belief log, which is the exact race the
        store skips a journal and rollback for (AD-1).
        """
        return self.claims > 0 or self.lock.locked()


class ActorRegistry:
    """Hydrates, serializes and evicts actors."""

    def __init__(self, root: Path | str, *, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.root = Path(root)
        self.capacity = capacity
        self._actors: "OrderedDict[str, Actor]" = OrderedDict()

    # -- lifecycle -----------------------------------------------------------

    def _hydrate(self, main_id: str) -> Actor:
        """Open a main's store. Cheap — SQLite open plus a snapshot read, which
        the work that follows dwarfs.

        The ceiling is read here, from the store, and that is what makes AD-28
        survive eviction: an actor dropped under memory pressure and rehydrated
        five minutes later comes back capped, because the cap was never in
        memory in the first place. A ``Ceiling`` parses its own value
        fail-closed, so a rung this build cannot read caps at `behave` rather
        than reading as absent.

        That read makes hydration eager where it used to be lazy — a corrupt
        log now surfaces here rather than at the first turn. Deliberate, and
        the cheaper of the two: it is one snapshot read that the turn was going
        to do anyway, and it happens inside the per-message isolation in
        ``Runtime.run``, so the failure domain is unchanged. Deferring it would
        mean a window in which a capped main reads as uncapped.
        """
        validate_main_id(main_id)
        # The prefix builder is handed to the store here rather than imported
        # by it: ``half.store`` may not depend on ``half.retrieval``. Wiring it
        # at hydration is what makes prefix hits work in the running product
        # and not only where a test remembers to pass it.
        store = Store(self.root / main_id, prefix=build_prefix)
        state = store.state()
        actor = Actor(
            main_id=main_id,
            store=store,
            ceiling=Ceiling(state.ceiling),
            # Both durable halves of a crisis suspension come back together
            # (CAP-12). A main in the mode rehydrates with retrieval already
            # off, so there is no window — not one turn, not one line — in
            # which an evicted main reads as uncapped or as retrievable.
            retrieval=RetrievalSwitch(enabled=not mode_is_open(state.crisis)),
        )
        self._actors[main_id] = actor
        return actor

    def _reached(self, main_id: str) -> Actor:
        """This main's actor, hydrating it and marking it recently used.

        Every door into the registry goes through here. An accessor that
        hydrates without touching the LRU leaves an actor looking cold the
        moment it was needed — and one that skips the capacity check lets the
        registry grow past it for as long as nobody takes a turn.
        """
        actor = self._actors.get(main_id)
        if actor is None:
            actor = self._hydrate(main_id)
        self._actors.move_to_end(main_id)
        return actor

    def _evict_if_needed(self) -> None:
        """Drop least-recently-used actors that no turn holds or awaits.

        A busy actor is skipped rather than waited on: eviction is an
        optimisation, and blocking on it would turn memory pressure into a
        stall on the very actor doing work.
        """
        while len(self._actors) > self.capacity:
            for main_id, actor in list(self._actors.items()):
                if not actor.busy:
                    self._actors.pop(main_id, None)
                    actor.store.close()
                    break
            else:
                return  # every actor is claimed; try again after one finishes

    @asynccontextmanager
    async def acquire(self, main_id: str) -> AsyncIterator[Actor]:
        """Hold ``main_id``'s actor exclusively for the duration of the block."""
        actor = self._reached(main_id)

        # Claimed before awaiting the lock, so this actor cannot be evicted
        # while this turn is merely queued behind another.
        actor.claims += 1
        try:
            async with actor.lock:
                yield actor
        finally:
            actor.claims -= 1
            # Eviction is considered only once nothing holds or awaits the
            # actor, so a turn is never interrupted (AD-33). In a finally so a
            # failing turn cannot let the registry grow past capacity forever.
            self._evict_if_needed()

    # -- introspection -------------------------------------------------------

    def retrieval_switch(self, main_id: str) -> RetrievalSwitch:
        """This main's retrieval switch, hydrating the actor if needed.

        The crisis gate runs before the mutex is taken, so it needs a way to
        reach one main's switch without holding that main's actor. This does not
        block, and does not write to the log.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return actor.retrieval

    def handoff_records(self, main_id: str) -> tuple[dict[str, Any], ...]:
        """This main's phone book: people they named, and where they said they
        are (CAP-12, story 6b).

        The same door ``retrieval_switch`` and ``license_ceiling`` open, for
        the same caller and for the same reason: the crisis gate runs before
        the mutex is taken (AD-10). It does not block and does not write.

        **Narrowed by field, not by record.** Crisis mode hard-disables ledger
        retrieval, so the warm handoff must not become the route by which the
        ledger comes back. ``handoff_record`` selects which records are phone
        book at all, and ``handoff_projection`` then keeps only the fields a
        door is made of plus the ones the ladder needs to decide whether it may
        be offered. Returning whole records was not narrowing: a belief
        carrying both a contact field and a claim about the main — the most
        ordinary shape there is once a person is also a subject — handed that
        claim to the crisis path. Both live in ``half.store.records``, because
        the layer that owns record shapes owns which shapes leave this method.

        Ordered by id so the same phone book produces the same offer twice.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        beliefs = actor.store.state().beliefs
        return tuple(
            handoff_projection(record)
            for _, record in sorted(beliefs.items())
            if handoff_record(record)
        )

    def safetyplan_records(self, main_id: str) -> tuple[dict[str, Any], ...]:
        """The safety plans this main is holding (CAP-12, story 6c).

        The same door ``handoff_records`` opens, narrowed the same way and for
        the same reason: the crisis gate runs before the mutex is taken
        (AD-10), and the mode has hard-disabled ledger retrieval, so the one
        thing this path may reach is the document the main was given — never a
        claim about them. ``plan_record`` selects which records are a plan at
        all and ``plan_projection`` then keeps only the plan and its pin, so a
        belief carrying both a plan and a claim hands over the plan and keeps
        the claim.

        Ordered by id so the same store produces the same plan twice.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        beliefs = actor.store.state().beliefs
        return tuple(
            plan_projection(record)
            for _, record in sorted(beliefs.items())
            if plan_record(record)
        )

    async def hold_safetyplan(
        self, main_id: str, *, t: str, fields: Mapping[str, Any]
    ) -> None:
        """Store one safety plan for this main, under the mutex (AD-1).

        **Takes the fields, never the lines.** ``half.crisis.safetyplan``
        composes them and is the only expression in the codebase that puts a
        value into the plan field; this appends what it is handed. That split
        is deliberate: an actor method that took a list and wrote
        ``plan=lines`` would be a second writer, and the whole clinical
        boundary is that there is exactly one.
        """
        async with self.acquire(main_id) as actor:
            actor.store.record(Op.ASSERT, f"p_{main_id}_{t}", t, **dict(fields))

    # -- the ceiling (AD-28) -------------------------------------------------
    #
    # Story 5a built the cap and said, accurately then, that nothing in
    # ``half/`` lowered one. That is no longer true: ``half.crisis.gate`` drops
    # it to `behave` on entry, and the operator reversal path raises it again.
    # Both go through ``suspend_for_crisis`` and ``reverse_crisis`` below
    # rather than through the two sync methods, and the difference is the
    # mutex.
    #
    # **AD-1, and where the mutex is taken.** ``lower_ceiling`` and
    # ``release_ceiling`` append *without* holding the actor's mutex. That is
    # safe only for a caller that already holds it, or that is otherwise
    # serialized against every other writer for this main — which is an
    # assumption, so it is stated at both ends rather than left implicit at
    # one. Neither has a caller in ``half/``; they are 5a's surface and its
    # tests. Everything the crisis path does goes through the two async
    # methods, which take the mutex themselves, so a supervisor running many
    # actors concurrently cannot interleave a crisis append with an ordinary
    # turn's.

    def license_ceiling(self, main_id: str) -> Ceiling:
        """This main's license ceiling, hydrating the actor if needed.

        The same door ``retrieval_switch`` opens, for the same caller: crisis
        runs before the mutex is taken (AD-10) and aftercare sets the ceiling
        (AD-28). The returned ``Ceiling`` is frozen — reading one cannot change
        one, and there is no setter on it to reach.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return actor.ceiling

    def lower_ceiling(
        self, main_id: str, to: License, *, t: str, because: str
    ) -> Ceiling:
        """Lower this main's cap, durably. Only ever lowers.

        Appended to the log before the in-memory value moves, so a crash between
        the two leaves a main *more* capped than the process thought rather than
        less. ``t`` is supplied by the caller — nothing in this path reads a
        clock (AD-30).
        """
        actor = self._reached(main_id)
        lowered = actor.ceiling.lowered_to(to)
        self._record_ceiling(actor, lowered, t=t, because=because)
        return lowered

    def release_ceiling(
        self, main_id: str, *, to: License, t: str, because: str
    ) -> Ceiling:
        """Raise this main's cap by **one rung**, and never further.

        Named, reasoned and durable, because raising a ceiling ends a
        suppression something deliberate put in place. No belief moves: a cap is
        a minimum against each belief's own license.

        **``to`` has no default any more, and that is story 6c's repair.** It
        used to default to `assert` — one call, and a main mid-aftercare was
        back to full licence in a single step, which is the failure CAP-12
        names when it requires licenses restored *gradually rather than at
        once*. A default is not a decision anybody makes, so it is gone, and a
        jump of more than one rung is refused outright rather than left to the
        caller's arithmetic. There is now no expression in this codebase that
        restores everything at once.

        The one deliberate exception is ``reverse_crisis``, which does not come
        through here. That is not a restore: it undoes an entry that should
        never have happened, so there is no ladder to climb back up — see its
        own docstring.
        """
        actor = self._reached(main_id)
        # ``released`` is what parses ``to``: it refuses anything that is not a
        # rung, so there is no second reader of a license value here (story 5a's
        # single-decision rule) and no spelling of a typo that folds silently.
        released = actor.ceiling.released(to=to, because=because)
        target = released.rung
        if height(target) < height(actor.ceiling.rung):
            raise StoreError(
                f"release_ceiling: {actor.ceiling.rung} -> {target} lowers the "
                "cap. Lowering is a safety act with its own path and needs no "
                "reason; this one raises and is refused when it would not"
            )
        if height(target) > height(actor.ceiling.rung) and target is not next_rung(
            actor.ceiling.rung
        ):
            raise StoreError(
                f"release_ceiling: {actor.ceiling.rung} -> {target} restores "
                "more than one rung. Aftercare comes back a step at a time; a "
                "single jump to full licence is what CAP-12 forbids"
            )
        self._record_ceiling(actor, released, t=t, because=because)
        return released

    def _record_ceiling(
        self, actor: Actor, ceiling: Ceiling, *, t: str, because: str
    ) -> None:
        if ceiling == actor.ceiling:
            return  # nothing moved; an append would say something happened
        actor.store.record(
            Op.CEILING,
            f"c_{actor.main_id}_{t}",
            t,
            **ceiling_fields(ceiling, because=because),
        )
        actor.ceiling = ceiling

    # -- the crisis mode (CAP-12) ---------------------------------------------

    def crisis_open(self, main_id: str) -> bool:
        """Whether this main is in crisis mode, per the log.

        The authority is the ``crisis`` record, not a set in memory. A mode
        that ended at the next eviction would answer the main's following
        message through the ordinary pipeline — a mode exit that nobody
        decided and nothing recorded, which CAP-12 forbids outright.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return mode_is_open(actor.store.state().crisis)

    def crisis_record(self, main_id: str) -> dict[str, Any] | None:
        """The last crisis record for this main, or ``None``.

        Content-free by construction (AD-22): tier, signal count, state and
        time. It exists because the clinical reviewer's first question is how
        often the mode fires and on what, and nothing else in the log answers
        it — a ceiling append says a cap exists, never what put it there.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        record = actor.store.state().crisis
        return dict(record) if record is not None else None

    def aftercare_record(self, main_id: str) -> dict[str, Any] | None:
        """The last aftercare record for this main, or ``None`` (story 6c).

        Content-free by construction (AD-22): a state and a time. It is where
        *"has Half asked about the mirror, and what did the main say"* is
        answered, and nothing else in the log answers it — a ceiling append
        says a cap moved, never whether anybody was asked first.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        record = actor.store.state().aftercare
        return dict(record) if record is not None else None

    # -- the due-time queue (AD-9, story 9a) ----------------------------------
    #
    # Three doors, and they follow ``handoff_records`` / ``note_aftercare``
    # exactly: two reads that hydrate without blocking and without writing, and
    # one write that goes through the mutex. The scheduler runs outside any
    # turn, so it needs the same shape the crisis gate needed — and it must not
    # get a second, private route to a main's log, because the single writer is
    # what lets the store skip a journal (AD-1).

    def schedule_record(self, main_id: str) -> dict[str, Any] | None:
        """When this main is next due, as the log last recorded it, or ``None``.

        ``None`` means never scheduled, and the scheduler treats it as *record a
        due time and run nothing* — never as *run now*. That is the whole of
        "a missed window sends nothing" at the boundary where a main first
        appears: a new main, a restored backup and a log this build cannot read
        all land on the same silent branch.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        record = actor.store.state().schedule
        return dict(record) if record is not None else None

    def zone_records(self, main_id: str) -> tuple[dict[str, Any], ...]:
        """The records naming a timezone this main told Half (AD-9).

        Narrowed by field rather than by record, for the reason
        ``handoff_records`` is: *"I'm in Delhi now"* is an ordinary sentence,
        so a belief carrying a zone commonly carries a claim about the main as
        well, and the scheduler has no business holding the claim. What comes
        back is a zone key plus the ladder's own evidence for whether it was an
        answer — which is what ``half.schedule.due.zone_of`` then asks.

        Ordered by id so the same store produces the same zone twice.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        beliefs = actor.store.state().beliefs
        return tuple(
            zone_projection(record)
            for _, record in sorted(beliefs.items())
            if zone_record(record)
        )

    async def note_pass(
        self, main_id: str, *, t: str, fields: Mapping[str, Any]
    ) -> None:
        """Record when this main is next due, under the mutex (AD-1).

        **Takes the fields, never the parts.** ``half.schedule.due.scheduled``
        composes them from a ``Due``, so the zone and the told flag cannot
        drift apart from the instant they describe — the registry does not know
        what pre-dawn is and must not start deciding.

        The append is what makes a due time survive a restart, and what makes a
        completed pass not run twice. It goes through ``acquire`` rather than
        writing directly, so a tick and a turn cannot both be writing this
        main's log: the file lock keeps a second *worker* out, and this keeps
        the tick and the inbound path apart inside one.
        """
        async with self.acquire(main_id) as actor:
            actor.store.record(
                Op.SCHEDULE, f"sc_{fields[NEXT_PASS_AT]}", t, **dict(fields)
            )

    # -- the nightly pass's doors (CAP-7, story 9c) ---------------------------
    #
    # Three more, and they follow ``schedule_record`` / ``zone_records`` /
    # ``note_pass`` exactly: two reads that hydrate without blocking and
    # without writing, and one write that goes through the mutex. The pass runs
    # outside any turn, under the scheduler, so it needs the same shape the
    # crisis gate and the scheduler needed — and it must not get a second,
    # private route to a main's log, because the single writer is what lets the
    # store skip a journal (AD-1).

    def tension_table(self, main_id: str) -> dict[str, dict[str, Any]]:
        """This main's tensions, as the log last folded them (CAP-7).

        The whole table rather than a narrowing, and that is not an oversight:
        a tension record carries a state, a pair of ids and a license, all of
        which the pass needs, and no claim text at all — the text lives on the
        two beliefs the pair names. There is nothing here to narrow away.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return {
            ident: dict(record)
            for ident, record in actor.store.state().tensions.items()
        }

    def belief_history(self, main_id: str) -> tuple[dict[str, Any], ...]:
        """Every ``assert`` this main has, narrowed to id, stamp and support.

        **The log — not the fold**, and that is the one place in Half where a
        read goes to the authority rather than the derived view. It has to:
        *"what did this entry cite when the tension was recorded"* is a question
        about the past, the fold holds only the present, and the alternative is
        writing a counter onto the tension for the pass to mutate — the AD-30
        violation story 4 avoided by making salience computed.

        **Narrowed by field, hard.** A log read is every claim Half holds about
        the main, and the pass has business with none of it: what decides
        whether a disagreement is widening is how many *sources* an entry
        cites. ``history_projection`` keeps the id, the stamp and the support
        set and drops the claim, the subject, the ledger, the phone book and
        the safety plan — see ``records.HISTORY_VISIBLE``.

        **Narrowed by op too**, which review found this claimed and did not do.
        It said *"every belief append"* and returned a projection of every
        record of every op, plus a paragraph about correction and expunge
        records being *"kept, carrying no support, so a side that was retracted
        stops accumulating"* — which was never implemented and could not be: a
        correction record carries its own id and never its target's, and
        ``HISTORY_VISIBLE`` drops ``target``, so nothing downstream could ever
        match one to what it corrects. It was also unnecessary. A side that was
        retracted has already resolved its tension in the fold, and a resolved
        tension is never evaluated. So the rows are the asserts, which is what
        the name says, and every schedule record, crisis record, loop
        transition and tombstone stops being decoded, held and rescanned once
        per tension per night.
        """
        actor = self._reached(main_id)
        self._evict_if_needed()
        return tuple(
            history_projection(record.data)
            for record in actor.store.log
            if record.op is Op.ASSERT and record.data.get("tombstone") is not True
        )

    async def tension_view(self, main_id: str) -> tuple[
        dict[str, dict[str, Any]], tuple[dict[str, Any], ...]
    ]:
        """This main's tensions and their entries' history, read **together**.

        One read under one mutex, and that is a correctness rule rather than a
        convenience. The pass used to call ``tension_table`` and
        ``belief_history`` separately, and the two go to different authorities —
        the first to the SQLite view, the second to the log file — with nothing
        between them. An inbound turn landing in the gap handed the plan a table
        and a history that disagreed, and the pass's own docstring claimed the
        opposite: *"the reads happen first and together, so the plan is computed
        against one consistent view of the log"*. They now do.

        Held only for the read. The append happens afterwards, outside this, and
        carries the premise it was planned against — see ``note_transition`` —
        because a pass that held the mutex from its first read to its last write
        would block the main's own turn for the length of the whole pass.
        """
        async with self.acquire(main_id) as actor:
            state = actor.store.state()
            table = {
                ident: dict(record) for ident, record in state.tensions.items()
            }
            history = tuple(
                history_projection(record.data)
                for record in actor.store.log
                if record.op is Op.ASSERT
                and record.data.get("tombstone") is not True
            )
        return table, history

    async def note_transition(
        self,
        main_id: str,
        *,
        tension_id: str,
        t: str,
        fields: Mapping[str, Any],
        was: object = None,
    ) -> None:
        """Move one tension, under the mutex (AD-1, AD-3).

        **Takes the fields, never the parts.** ``half.tensions.ledger`` composes
        them and refuses the states nothing may write, so the registry does not
        know what `widening` means and must not start deciding.

        Appended under the **tension's own id**, which is what makes the fold
        merge the new state over the pair and the license the mint recorded
        rather than replacing them. A transition is an append and never an edit.

        **A transition carries a state and nothing else.** Review found this
        would append whatever a caller handed it: a ``claim`` or an
        ``independent`` count beside the state validated and became durable,
        writing belief content into a tension record where no correction to
        either entry could take it back (AD-22). The append gate refuses those
        now as well; this refuses them one layer earlier, where the caller can
        still be told which field it was.

        **``was`` is the premise the move was planned against**, and the append
        is refused if it has moved. The plan is computed outside this mutex — it
        has to be, or the pass would hold a main's actor from its first read to
        its last write — so a correction can land in between, resolve the
        tension, and have this write a live state straight back over it. That is
        the ordinary-operation route into the terminality hole the fold now also
        guards; this is the half of it that keeps the *log* honest rather than
        only the fold. It also refuses a transition for a tension the fold has
        never seen, which would otherwise mint a pairless one out of nothing.
        """
        stray = sorted(set(fields) - {TENSION_STATE})
        if stray:
            raise TensionError(
                f"a transition carries {TENSION_STATE!r} and nothing else; "
                f"refusing {stray}"
            )
        async with self.acquire(main_id) as actor:
            held = actor.store.state().tensions.get(tension_id)
            if held is None:
                raise TensionError(
                    f"no tension {tension_id!r} to move: a transition names a "
                    f"tension the log already holds, and one that names nothing "
                    f"would mint a disagreement with no two entries in it"
                )
            if held.get(TENSION_STATE) != was:
                raise TensionError(
                    f"the state {tension_id!r} was planned from is not the state "
                    f"it is in; the log moved under the plan and this pass will "
                    f"compute the answer again"
                )
            actor.store.record(Op.TENSION, tension_id, t, **dict(fields))

    # -- the minter's doors (CAP-7, story 9d) --------------------------------
    #
    # Two more, following ``tension_view`` / ``note_transition`` exactly: one
    # read under the mutex and one write that goes through it. The minter runs
    # inside the same pass and must not get a second, private route to a main's
    # log, because the single writer is what lets the store skip a journal
    # (AD-1).

    async def mint_view(self, main_id: str) -> MintView:
        """This main's state, **narrowed** to what a mint may consult (CAP-7).

        One read under one mutex, for the reason ``tension_view`` is one: the
        belief table, the tension table, the loop slugs and the schedule stamps
        go to two different authorities — the fold and the log file — and an
        inbound turn landing between them would hand the minter a candidate set
        and a tension table that disagreed, which is a duplicate tension.

        **Narrowed, not the fold**, on the same terms as ``surface_view``. It
        would have been one line to return ``State`` and let the minter take
        what it wanted; what that costs is a package in which
        ``if state.aftercare is not None`` can be written with no new import and
        no new door. What passes this line is:

        * **beliefs**, through ``records.mint_projection`` — an id, a stamp, a
          claim, a subject, a ledger and a loop. Not the license: whether a
          tension may be *said* is the governance layer's question, asked at
          delivery. Not the support set: what an entry cites decides *widening*,
          which is story 9c's half and reads its own narrowing.
        * **tensions**, entire — a state, a pair and a license, and no claim
          text anywhere in one. There is nothing here to narrow away, which is
          the same finding ``tension_table`` records.
        * **loop slugs, and nothing else about a loop.** Not the state, not the
          timescale, not the last movement. A tension is a link between two
          entries and never demotes, freezes or refutes a wanting (CAP-6), and
          the way that rule breaks is a minter that could see enough of a loop
          to have an opinion about it.
        * **the stamp of every schedule record whose tick actually ran this
          main's pass** — which is what *"new or changed since this main's last
          pass"* is measured against. Stamps only: a schedule record also
          carries a zone and whether the main told Half one, and neither is any
          of the minter's business (AD-22).

          The filter on ``PASS_RAN`` is the correction. This took *every*
          schedule stamp, and the scheduler writes one for the unscheduled, the
          missed and the **suspended** mains as well as for the one whose pass
          is about to run — so the watermark meant *"when the scheduler last
          touched this main"*. A main crisis-suspended for one night resumed
          with that night's beliefs already behind the mark, permanently:
          ``considered == 0``, for ever. It also made the first-pass case —
          *"no marker means everything is new"* — unreachable, because the
          unscheduled tick had already written one.
        * **the erased set**, so an erasure stays an erasure.
        """
        async with self.acquire(main_id) as actor:
            state = actor.store.state()
            view = MintView(
                beliefs={
                    ident: mint_projection(record)
                    for ident, record in state.beliefs.items()
                },
                tensions={
                    ident: dict(record)
                    for ident, record in state.tensions.items()
                },
                loops=tuple(state.loops),
                passes=tuple(
                    record.t for record in actor.store.log
                    if record.op is Op.SCHEDULE
                    and record.data.get(PASS_RAN) is True
                ),
                gone=frozenset(state.expunged),
            )
        return view

    async def note_mint(
        self,
        main_id: str,
        *,
        tension_id: str,
        t: str,
        fields: Mapping[str, Any],
    ) -> None:
        """Mint one tension, under the mutex (AD-1, AD-3).

        **Takes the fields, never the parts.** ``half.consolidate.mint``
        composes them, so the registry does not know what `fresh` means, does
        not know which entries are being linked, and must not start deciding.

        **A mint is a mint and never a transition.** Refused when the fold
        already holds this tension: story 9c owns every state change and
        computes widening from the stamp on the record that set the current
        state, so a second record arriving through *this* door would move a
        tension's stamp without moving its state — a silent widening reset that
        no test of the transition path could ever see. ``note_transition`` is
        the other door and it refuses the inverse.

        Refused too when the tension id is one the main **erased**. The append
        gate treats an expunged id as already seen and the fold drops the
        record, so without this the mint would look like it had landed and be
        an erasure quietly undone.
        """
        async with self.acquire(main_id) as actor:
            state = actor.store.state()
            if tension_id in state.tensions:
                raise TensionError(
                    f"a tension {tension_id!r} is already in this log: minting "
                    f"is what creates one, and a second mint over the same pair "
                    f"would move its stamp without moving its state"
                )
            if tension_id in state.expunged:
                raise TensionError(
                    f"the tension {tension_id!r} was erased; a mint that landed "
                    f"on it would be an erasure undone"
                )
            actor.store.record(Op.TENSION, tension_id, t, **dict(fields))

    # -- the morning surface's doors (CAP-8, story 10) ------------------------
    #
    # Two more, and they follow ``tension_view`` / ``note_transition`` exactly:
    # one read under the mutex and one write that goes through it. The surface
    # runs outside any turn, under the scheduler, so it needs the shape the
    # crisis gate, the scheduler and the pass all needed — and it must not get
    # a second, private route to a main's log, because the single writer is
    # what lets the store skip a journal (AD-1).

    async def surface_view(self, main_id: str) -> SurfaceView:
        """This main's state, **narrowed** to what a morning may consult.

        Two things about this are corrections review had to make.

        **Narrowed, not the fold.** It used to return ``State`` entire, which
        carries the crisis and aftercare records — so ``if state.aftercare is
        not None: return Silence(...)`` could be written inside the surface
        with no new import and no new door, defeating AD-28 while every scan
        stayed green. ``half.surface.view`` is the allowlist; what is not on it
        is unreachable rather than merely unread.

        **From the log, not from SQLite.** ``Store.append`` writes the line and
        *then* rebuilds the derived view, so a crash between the two leaves the
        view behind the log — and the two rules that read it, the day marker
        and the nagging bound, would both answer *never*. The log is the
        authority (AD-3), and once a day per main is where a fold costs least.
        The ceiling comes out of the same fold for the same reason: a cap read
        from a stale view is a capped main reading as uncapped, which is the
        one window AD-28 exists to close.

        Held only for the read. The day is claimed afterwards, outside this,
        because a surface that held the mutex from its read to its write would
        block the main's own turn for the length of the whole morning — and the
        claim re-reads under its own acquire precisely because this one was
        released.
        """
        async with self.acquire(main_id) as actor:
            state = actor.store.fold()
            return narrowed(state, Ceiling(state.ceiling))

    async def claim_day(
        self,
        main_id: str,
        *,
        t: str,
        day: str,
        records: Sequence[Mapping[str, Any]],
    ) -> str:
        """Spend this main's one unprompted message for ``day``, or refuse.

        **One serialized operation, and that is the point.** The check and the
        append happen inside a single ``acquire``: the surface used to read the
        marker under one mutex and append under a later one, so two overlapping
        runs both read yesterday and both sent. Nothing else in this class had
        that shape, because nothing else in this class had a rule that says
        *at most once per day*.

        **The mode is re-asserted here**, not only at the top of the morning. A
        main who enters crisis while their message is being assembled must not
        receive it, and this is the last point at which that is still true.

        **Read from the log**, for the reason ``surface_view`` reads from the
        log: a derived view that lags a crash would report the day as unspent.

        ``records`` is composed by ``half.surface.touch`` — the day marker
        first, then a raise for every further loop the message touches — so the
        registry does not know what a day marker is and must not start
        deciding. They are appended together, so a crash cannot leave the day
        spent with the loops unbounded or the reverse.

        Returns one of ``CLAIM_OUTCOMES``; raises only when the append genuinely
        did not land. That distinction matters: ``Store.append`` writes the line
        before it rebuilds the derived view, so a rebuild that fails leaves the
        record durable — and treating that as a failure would spend the day and
        report that nothing was written, costing the main a message that was
        already paid for. So a failure is re-read against the log before it is
        believed.
        """
        if civil.instant(t) is None:
            # Refused before the append, on the same terms as a schedule
            # record's due time: a raise whose stamp nothing can read is a loop
            # whose bound has no measure, and the log is append-only.
            raise TouchError(
                f"claim_day: {t!r} is not an instant this build can read; a "
                f"raise with no readable time is a bound with no measure"
            )
        async with self.acquire(main_id) as actor:
            state = actor.store.fold()
            if mode_is_open(state.crisis):
                return CLAIM_CRISIS
            if spoken_on(state.spoke, day) is True:
                return CLAIM_ALREADY
            # Checked over **every** record before any of them is appended,
            # which is what makes this batch atomic. The append gate refuses
            # the same set one layer down, so a single record would be caught
            # either way; a batch would not — a stray field on the second
            # record would leave the first one durable, spending the day with
            # the loops half bound.
            for fields in records:
                stray = sorted(set(fields) - TOUCH_FIELDS)
                if stray:
                    raise TouchError(
                        f"a touch carries the loop Half raised, the day it "
                        f"spent and what it cited; refusing {stray}"
                    )
            for index, fields in enumerate(records):
                ident = f"tc_{t}" if index == 0 else f"tc_{t}_{index}"
                try:
                    actor.store.record(Op.TOUCH, ident, t, **dict(fields))
                except Exception:
                    # Did it land anyway? ``Store.append`` appends the line and
                    # then rebuilds; a failure in the rebuild leaves a durable
                    # record and a stale view, and the log is what says so.
                    if not any(
                        record.id == ident and record.op is Op.TOUCH
                        for record in actor.store.log
                    ):
                        raise
            return CLAIMED

    # -- the unasked queue's doors (CAP-4, story 5b) --------------------------
    #
    # Two more, and they follow ``surface_view`` / ``claim_day`` exactly: one
    # narrowed read under the mutex, and one serialized check-and-append that
    # goes through it. The queue is consulted on the main's own turn, so it
    # needs the shape the surface needed — and it must not get a second,
    # private route to a main's log, because the single writer is what lets the
    # store skip a journal (AD-1).

    async def trust_view(self, main_id: str) -> TrustView:
        """This main's state, **narrowed** to what the unasked queue may see.

        **Narrowed, not the fold** — story 10's lesson, applied a second time.
        Handing back ``State`` would put the crisis, aftercare and schedule
        records inside reach of the queue, and ``if state.aftercare is not
        None: return ()`` is one line, needs no new import, and would leave a
        main who never gets asked anything again with the whole suite green.
        ``half.trust.unasked.VISIBLE`` is the allowlist; what is not on it is
        unreachable rather than merely unread.

        **The balance is folded out of the log, not out of the fold.** Two
        passes over one read: ``fold`` builds the beliefs and loops, and
        ``half.trust.balance`` counts delivered favours against questions
        asked. That is the whole of AD-30 for this story — there is no counter
        on ``State`` to go stale, and none in SQLite either, so a rebuilt store
        and a fresh one give the same number because neither is consulted.

        **From the log rather than from SQLite**, for the reason
        ``surface_view`` reads from the log: ``Store.append`` writes the line
        and *then* rebuilds, so a crash between the two leaves the derived view
        behind — and a balance read from a stale view is a favour spent twice.
        The ceiling comes out of the same records for the same reason: a cap
        read from a stale view is a capped main reading as uncapped, which is
        the one window AD-28 exists to close.

        Held only for the read. The spend is recorded afterwards, under its own
        acquire, which re-reads precisely because this one was released.
        """
        async with self.acquire(main_id) as actor:
            # One read of the log, two folds over it. Materialized rather than
            # streamed twice because the log is read from disk: iterating it
            # twice would be two reads that a concurrent append could land
            # between, and the beliefs and the balance would then describe two
            # different moments.
            records = list(actor.store.log)
            state = fold_records(records)
            return narrowed_for_trust(
                state, Ceiling(state.ceiling), balance=trust_balance(records)
            )

    # -- the question engine's one further door (CAP-4, story 11) ------------
    #
    # Not a change to ``half.trust.unasked.TrustLedger``, which still has
    # exactly the three methods story 5b reviewed. ``half.questions.engine``
    # declares its own protocol extending that one, and this is what satisfies
    # it — so widening what the *question* path may see cannot widen what the
    # *trust* path may see.

    async def question_view(self, main_id: str) -> QuestionView:
        """The trust view and the answer state, from **one** read of the log.

        **One acquire, two folds, one moment.** They were two separate doors
        before review, and reading the balance under one acquire and the answer
        state under another left a window an append could land in: the pair would
        then describe two different instants, and *"affordable"* and *"never
        asked"* would be answers about different logs.

        **Folded from the log, never stored** (AD-3, AD-30), exactly as the
        balance is and for the same reason: an ``answered`` flag on ``State``
        would be materialized state that is a function of which code paths ran
        rather than of the log, and it would replay perfectly — so it would only
        ever be *wrong*, never *inconsistent*, and no round-trip assertion in the
        suite would see it.

        **From the log rather than from SQLite**, for the reason ``trust_view``
        and ``surface_view`` read the log: ``Store.append`` writes the line and
        *then* rebuilds, so a crash between the two leaves the derived view
        behind — and a question read from a stale view as never-asked is a
        question put twice.

        There is deliberately **no door here onto the live conversation.** The
        strands the topic gate reads are volatile (AD-26); the caller holding the
        turn has just moved them and passes them in.

        Held only for the read; nothing here writes.
        """
        async with self.acquire(main_id) as actor:
            records = list(actor.store.log)
            state = fold_records(records)
            return QuestionView(
                trust=narrowed_for_trust(
                    state, Ceiling(state.ceiling), balance=trust_balance(records)
                ),
                answers=ask_history_of(records),
            )

    async def note_ask(
        self, main_id: str, *, t: str, question: str, about: str
    ) -> str:
        """Spend one favour on ``question``, or refuse. One of ``ASK_OUTCOMES``.

        **One serialized operation, and that is the point** — the same shape
        ``claim_day`` has, for the same reason and against the same failure.
        The check and the append happen inside a single ``acquire``: a caller
        that read the balance under one mutex and appended under a later one
        would let two overlapping turns both find the favour unspent and both
        ask, which is *the same favour buying two questions* arriving through
        concurrency rather than through arithmetic. Nothing else in this class
        has that shape, because nothing else in this class spends a currency.

        **Three facts are re-asserted here, and they are the three that can
        move between the choice and the spend.**

        *The mode*, because a main who enters crisis while their question is
        being composed must not receive it, and this is the last point at which
        that is still true — the currency is void in the mode (constitution).

        *The balance*, re-read from the log for the reason ``claim_day``
        re-reads the day marker from the log: a derived view that lags a crash
        would report a favour as unspent.

        *The ceiling and the belief's own rung* — through ``may_be_raised``,
        which is the same predicate ``half.trust.unasked.considered`` asks when
        the question is weighed. Review found this window open while the crisis
        one was closed, on the identical argument: a main whose cap drops to
        `behave` between the choice and the spend — aftercare stepping down, an
        operator capping them, a quarantine landing on the subject — was still
        asked, and ``trust_view``'s own docstring calls a stale cap *"the one
        window AD-28 exists to close"*. One call answers the cap, the pin and
        the rung together, and it is the queue's predicate rather than a
        paraphrase of it.

        **Refused rather than recorded when it cannot be paid for.** The
        alternative — append anyway and let the balance go negative — would
        make *the favour buys the question* a thing the log merely reports on
        rather than a thing that is true. The caller's remedy is to ask
        nothing, which is a first-class outcome (AD-27).

        **The record id cannot collide.** ``qa_{t}`` alone was not enough once
        ``asks_at`` could return more than one ``Ask``: two affordable spends
        inside one second shared an id, and ``Op.ASKED`` is append-keyed, so a
        single ``expunge_bodies`` would erase both bodies. The suffix is the
        first free one at that stamp, computed from the log under this mutex —
        the same shape ``claim_day`` uses for a batch, and content-free.

        **A durable spend is reported as one even when the rebuild fails.**
        ``Store.append`` writes the line and *then* rebuilds, so a failure in
        the rebuild leaves the record durable. Letting the exception out would
        tell the caller nothing was recorded — so it would ask nothing, and the
        main would lose a favour and get no question. The log is re-read before
        a failure is believed, exactly as ``claim_day`` does.
        """
        if civil.instant(t) is None:
            # Refused before the append, on the same terms as a raise whose
            # stamp nothing can read: the log is append-only, and a spend
            # stamped with a value no build can order is one nothing can ever
            # place against the favour that paid for it.
            raise TrustError(
                f"note_ask: {t!r} is not an instant this build can read; a "
                f"spend with no readable time cannot be placed against the "
                f"favour that paid for it"
            )
        # Checked before the mutex is taken, because a caller mistake should
        # not queue behind a main's turn to be told about. The append gate
        # refuses the same values one layer down, where they would become
        # durable; this is the early, cheap half of the same rule.
        fields = {QUESTION: question, ABOUT: about}
        unnamed = sorted(
            name for name in ASKED_FIELDS
            if not isinstance(fields.get(name), str) or not fields[name].strip()
        )
        if unnamed:
            raise TrustError(
                f"note_ask: a spend names the question it paid for and the "
                f"belief it was about; {unnamed} " f"missing or blank"
            )
        async with self.acquire(main_id) as actor:
            records = list(actor.store.log)
            state = fold_records(records)
            if mode_is_open(state.crisis):
                return ASK_CRISIS
            if not may_be_raised(
                state.beliefs.get(about.strip()), ceiling=Ceiling(state.ceiling)
            ):
                return ASK_NOT_PERMITTED
            if not trust_balance(records).spendable:
                return ASK_UNAFFORDABLE
            ident = _free_ask_id(t, {record.id for record in records})
            try:
                actor.store.record(Op.ASKED, ident, t, **fields)
            except Exception:
                # Did it land anyway? A failure in the rebuild leaves a durable
                # record and a stale view, and the log is what says so. Raising
                # here would spend the favour and report that nothing was
                # written — the main pays and is asked nothing.
                if not any(
                    record.id == ident and record.op is Op.ASKED
                    for record in actor.store.log
                ):
                    raise
            return ASK_RECORDED

    async def suspend_for_crisis(
        self, main_id: str, *, t: str, tier: str, score: int, fresh: bool = True
    ) -> None:
        """Enter the mode for this main, durably and under the mutex (CAP-12).

        One call does the whole suspension because its three parts must not be
        separable: the crisis record, the ceiling drop, and the retrieval
        disable. A build where two of the three landed is a build where a main
        is capped but retrievable, or in the mode but uncapped.

        Ordered so that a crash never leaves the main *less* suspended than the
        process believes: the appends go first and the in-memory switch last.

        Idempotent for the *held* state. A main already in the mode re-enters on
        every turn of a long conversation, and one record per message would be a
        log full of the same fact.

        **But a fresh disclosure is a new entry, and story 6c needs it to be.**
        Aftercare's floor runs from the most recent entry and never from the
        first, so a second crisis during aftercare has to be visible as an
        event with its own stamp — otherwise "the clock restarts" is a sentence
        with nothing behind it. ``fresh`` is false only when the tier is the
        *held* state, which is the gate saying this turn detected nothing new;
        every other entering tier is a signal that fired on this message.
        Two entries at the same instant are still one: the same turn cannot
        disclose twice. Stored stamps are minute-resolution, so "the same
        instant" spans a whole minute and two genuine disclosures inside one
        minute collapse to the earlier — accepted, because the cost is a floor
        that starts up to sixty seconds early and the alternative is a log line
        per message in a fast exchange.

        **The ceiling drops on an entry and not on every turn**, which is story
        6c's other repair here. Re-applying the drop on every held turn was
        harmless while nothing ever raised a ceiling; now that aftercare does,
        it made a restore last exactly until the main's next message — thirty
        days of floor, one rung back, and then silently capped again by the
        turn that observed it. So the suspension is what an *entry* does, and a
        turn that enters nothing leaves the cap where the log put it. Retrieval
        is still disabled unconditionally, because that switch lives in memory
        and an eviction is not an entry.

        The self-heal that the unconditional drop used to provide — a crash
        between the two appends leaving a main in the mode and uncapped — moves
        to ``half.crisis.aftercare``, which holds the cap down to what the
        floor permits as well as stepping it up.
        """
        async with self.acquire(main_id) as actor:
            current = actor.store.state().crisis
            entering = not mode_is_open(current) or (
                fresh and _stamp_of(current) != t
            )
            if entering:
                actor.store.record(
                    Op.CRISIS,
                    f"cr_{main_id}_{t}",
                    t,
                    state=CRISIS_ENTERED,
                    tier=tier,
                    score=score,
                )
                self._record_ceiling(
                    actor,
                    actor.ceiling.lowered_to(License.BEHAVE),
                    t=t,
                    because="crisis mode entered (CAP-12)",
                )
            actor.retrieval.disable()

    # -- aftercare (CAP-12, story 6c) -----------------------------------------
    #
    # Two writes, and the split is deliberate. ``note_aftercare`` records what
    # was said and moves nothing; ``restore_step`` moves the cap by one rung
    # and, where the step *is* an answer, records that answer in the same
    # mutex. Neither is a mode exit: the ceiling comes back, the mode does not,
    # and who decides the mode is over remains the companion's open question.

    async def note_aftercare(self, main_id: str, *, t: str, state: str) -> None:
        """Record that the question was put, or that the main declined it.

        Durable, because both facts have to survive an eviction. A question
        held in memory is asked again on the next turn after a restart, which
        is nagging; a decline held in memory disappears, leaving some later
        "yes" free to land on a question the main already refused.

        Moves no ceiling. Being asked restores nothing and declining takes
        nothing away — the cap is exactly where it was either way.
        """
        if state not in AFTERCARE_STATES:
            raise StoreError(
                f"note_aftercare: {state!r} is not an aftercare state; "
                f"expected one of {sorted(AFTERCARE_STATES)}"
            )
        async with self.acquire(main_id) as actor:
            _note_aftercare(actor, t=t, state=state)

    async def hold_ceiling(
        self, main_id: str, *, to: License, t: str, because: str
    ) -> Ceiling:
        """Hold this main's cap down to ``to``, under the mutex. Only lowers.

        ``lower_ceiling``'s durable, serialized twin, and it exists because
        aftercare is the ceiling's owner for as long as an aftercare period is
        running — in both directions. Stepping up is the story; holding down is
        what makes the step-up safe, because it is what notices a cap that is
        higher than the floor permits.

        The case it is for: the entry's two appends are one mutex apart, and a
        process killed between them leaves a main in the mode with no ceiling
        record. That used to heal itself, badly, by re-dropping the cap on
        every held turn — which is exactly what made a restore last until the
        main's next message.
        """
        async with self.acquire(main_id) as actor:
            self._record_ceiling(
                actor, actor.ceiling.lowered_to(to), t=t, because=because
            )
            return actor.ceiling

    async def restore_step(
        self, main_id: str, *, t: str, because: str, note: str | None = None
    ) -> Ceiling:
        """Raise this main's cap by exactly one rung, under the mutex (AD-1).

        The one path aftercare restores through, and it takes no target: the
        step is ``ladder.next_rung`` of wherever the cap is now, so there is no
        argument a caller could pass that would put everything back at once.

        ``note`` is the main's answer where the step *is* one — recorded in the
        same mutex as the ceiling move, because a build where the consent
        landed and the restore did not is a main who was asked, answered, and
        saw nothing happen, and a build with the reverse is a mirror that
        resumed with no record of anybody agreeing to it.
        """
        async with self.acquire(main_id) as actor:
            state = actor.store.state()
            began = entered_at(state.crisis)
            if began is None:
                raise StoreError(
                    "restore_step: there is no crisis entry to come back from. "
                    "Aftercare restores what a crisis capped; anything else "
                    "raising a ceiling is an operator act with its own path"
                )
            if not at_least(FLOOR_DAYS, since=began, now=t):
                raise StoreError(
                    f"restore_step: {t} is inside the {FLOOR_DAYS}-day floor "
                    f"that began at {began}. Nothing restores before it, by "
                    "any path — including this one, which is the path a caller "
                    "who has not read the floor reaches for"
                )
            if note is not None and note not in AFTERCARE_STATES:
                raise StoreError(f"restore_step: {note!r} is not an aftercare state")
            if note == AFTERCARE_AGREED:
                # An agreement has to answer a question that was actually put.
                # ``asked`` is the question standing; ``declined`` is a main
                # who answered it and has since changed their mind — and a
                # decline is only ever written in reply to a standing question,
                # so either state is proof that Half asked. ``stopped`` is not:
                # a main who asked not to be asked is not answering anything,
                # and a consent record after one is not a shape aftercare
                # produces. Nothing at all means the consent answers nothing,
                # which is what the aftercare op exists to make unforgeable.
                put, _ = answered(state.aftercare, since=began)
                if put not in (AFTERCARE_ASKED, AFTERCARE_DECLINED):
                    raise StoreError(
                        "restore_step: an agreement has to answer a question. "
                        "This aftercare period has no record of one being put, "
                        "so this consent answers nothing"
                    )
            step = next_rung(actor.ceiling.rung)
            if step is None:
                return actor.ceiling  # already at the top; nothing to restore
            released = actor.ceiling.released(to=step, because=because)
            # The ceiling first, then the record of the answer. A crash between
            # them then leaves the cap raised with no answer recorded, so the
            # next turn holds it back down and asks again — recoverable. The
            # other order leaves an answer recorded, aftercare finished and the
            # cap never raised, which is a main stuck one rung short for ever.
            self._record_ceiling(actor, released, t=t, because=because)
            if note is not None:
                _note_aftercare(actor, t=t, state=note)
            return released

    async def reverse_crisis(
        self, main_id: str, *, t: str, because: str
    ) -> None:
        """Undo a crisis entry — the operator path, and the only way back.

        **This is not a mode exit policy.** Nothing in Half decides that a
        crisis is over: the companion leaves *who decides it is over*
        unresolved, and a timeout, a keyword or a quiet expiry would each be
        answering a clinical question in code review. This is the separate
        thing a durable cap needs to be a safety feature rather than a trap —
        a deliberate, recorded, human act that undoes a false entry, with a
        reason that outlives whoever typed it.

        Reverses all three parts of the suspension together, for the reason
        ``suspend_for_crisis`` applies them together.

        **This is the one path that puts the ceiling back in a single move, and
        it is not a restore.** Story 6c makes ``release_ceiling`` refuse a jump
        of more than one rung, because aftercare comes back a step at a time.
        A reversal is the other thing entirely: it says the entry should never
        have happened, so there is no aftercare period to come back from and no
        ladder to climb. Making an operator step a falsely-capped main up one
        rung at a time over six weeks would be applying a safety schedule to
        somebody who was never in danger.
        """
        if not isinstance(because, str) or not because.strip():
            raise StoreError(
                "reverse_crisis: reversing a crisis entry requires a stated "
                "reason; it undoes a suspension something deliberate applied"
            )
        async with self.acquire(main_id) as actor:
            actor.store.record(
                Op.CRISIS,
                f"cr_{main_id}_{t}",
                t,
                state=CRISIS_REVERSED,
                because=because.strip(),
            )
            self._record_ceiling(
                actor, actor.ceiling.released(to=TOP, because=because),
                t=t, because=because,
            )
            actor.retrieval.enable()

    @property
    def hydrated(self) -> list[str]:
        return list(self._actors)

    def is_hydrated(self, main_id: str) -> bool:
        return main_id in self._actors

    def close(self) -> None:
        """Close every store. Refuses while any turn is still running, rather
        than pulling a store out from under an in-flight append."""
        busy = [a.main_id for a in self._actors.values() if a.busy]
        if busy:
            raise RuntimeError(f"actors still mid-turn: {sorted(busy)}")
        for actor in self._actors.values():
            actor.store.close()
        self._actors.clear()
