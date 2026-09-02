"""Log records: strict decoding, canonical encoding, unknown fields preserved.

Strict parsing is ported in spirit from claude-obsidian's ledger loader: a
lenient JSON parser silently resolves duplicate object keys and accepts
non-finite numbers, and either would make two builds disagree about what a log
line says while both believe they parsed it.

Unknown fields survive decode and re-encode untouched (AD-29's versioning is
only useful if an older build cannot quietly drop a newer build's data).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Final

from half.civil import instant
from half.errors import (
    CorruptLogError,
    LoopError,
    SchemaVersionError,
    ScheduleError,
    TensionError,
    TouchError,
    TrustError,
    UnknownOpError,
)
from half.loops.ledger import LOOP
from half.loops.states import LOOP_STATES, STATE, is_state
from half.loops.timescale import (
    LAST_MOVEMENT,
    TIMESCALE,
    TIMESCALES,
    is_timescale,
    moment,
)
from half.store.ops import SCHEMA_VERSION, TOUCH_ORIGINS, Op, parse_op
from half.tensions.states import TENSION_STATES
from half.tensions.states import is_state as is_tension_state
from half.tensions.states import TensionState
from half.tensions.widening import BETWEEN, SIDES, ranked_names
from half.text import terms

#: Fields every record must carry.
REQUIRED: Final[tuple[str, ...]] = ("t", "op", "id")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON object key {key!r}")
        seen[key] = value
    return seen


def _reject_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")


def strict_json_loads(value: str) -> Any:
    """Parse JSON, rejecting duplicate keys and non-finite numbers at any depth."""
    return json.loads(
        value,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )


@dataclass(frozen=True, slots=True)
class Record:
    """One line of the belief log.

    ``data`` holds the complete decoded object including fields this build does
    not recognise. ``op`` and ``id`` are lifted out for convenience but remain
    present in ``data`` — there is exactly one copy of the truth.
    """

    op: Op
    id: str
    t: str
    data: Mapping[str, Any] = field(repr=False)


def decode(line: str, *, path: str, lineno: int) -> Record:
    """Decode one log line, or raise with its exact position.

    An unknown op raises ``UnknownOpError`` — never skipped (AD-29).
    """
    try:
        obj = strict_json_loads(line)
    except ValueError as exc:
        raise CorruptLogError(str(exc), path=path, line=lineno) from exc

    if not isinstance(obj, dict):
        raise CorruptLogError("record root must be an object", path=path, line=lineno)

    missing = [k for k in REQUIRED if k not in obj]
    if missing:
        raise CorruptLogError(
            f"missing required field(s): {', '.join(missing)}", path=path, line=lineno
        )

    version = obj.get("v", SCHEMA_VERSION)
    if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= SCHEMA_VERSION:
        raise SchemaVersionError(
            f"record schema v{version} at {path}:{lineno} is newer than this build "
            f"(v{SCHEMA_VERSION}); refusing to fold rather than drop what it says"
        )

    try:
        op = parse_op(obj["op"])
    except ValueError:
        raise UnknownOpError(str(obj["op"]), path=path, line=lineno) from None

    ident = obj["id"]
    stamp = obj["t"]
    if not isinstance(ident, str) or not ident:
        raise CorruptLogError("'id' must be a non-empty string", path=path, line=lineno)
    if not isinstance(stamp, str) or not _ISO_PREFIX.match(stamp):
        raise CorruptLogError(
            "'t' must be an ISO-8601 timestamp starting YYYY-MM", path=path, line=lineno
        )

    return Record(op=op, id=ident, t=stamp, data=obj)


def encode(record: Record) -> str:
    """Canonical single-line JSON for ``record``.

    Keys are sorted so that encode(decode(x)) is idempotent — required for the
    byte-identical comparisons the replay invariant rests on (AD-4). Existing
    log lines are never rewritten; this is for new appends and round-tripping.
    """
    return json.dumps(
        record.data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,  # else encode writes a token its own decoder rejects
    )


#: ``t`` drives shard placement and the fold's ordering, so its shape is
#: validated at decode rather than trusted.
_ISO_PREFIX = re.compile(r"\d{4}-\d{2}")

#: Field names the record structure owns. A caller passing one through
#: ``**fields`` would make ``Record.id`` disagree with ``data["id"]``, and the
#: fold and the derived view would then key on different values.
RESERVED: Final[frozenset[str]] = frozenset({"t", "op", "id", "v"})

#: The field that pins a belief at the weakest rung, named here rather than in
#: ``half.governance`` because two layers need it and only one of them may own
#: it. The fold carries it forward (see ``STICKY``) and the ladder reads it;
#: a second spelling in either place is how the pin and the fold stop agreeing.
QUARANTINED: Final[str] = "quarantined"

#: The fields that make a belief part of the main's *phone book* rather than a
#: claim about the main: a person Half may one day offer as a door, and the
#: place the main told Half they are. Named here for the reason ``QUARANTINED``
#: is — two layers need the spelling and only one of them may own it. The
#: crisis handoff reads them (``half.crisis.contacts``) and the registry
#: narrows a main's records to them (``ActorRegistry.handoff_records``), so
#: that the one thing crisis mode may look up is the phone book and never the
#: ledger it has just hard-disabled.
CONTACT: Final[str] = "contact"
HANDLE: Final[str] = "handle"
IS_CLINICIAN: Final[str] = "clinician"
REGION: Final[str] = "region"

#: The two record kinds the handoff may see. Anything else in a main's log is
#: invisible to it.
HANDOFF_FIELDS: Final[tuple[str, ...]] = (CONTACT, REGION)

#: ``LOOP``, ``STATE``, ``TIMESCALE`` and ``LAST_MOVEMENT`` are **imported**
#: above rather than declared here, and re-exported for ``half.store.fold``.
#: The open-loop package is the lower layer and owns the spelling of its own
#: record shape; this module validates it and the fold materializes it. One
#: definition per name, flowing upward — a second spelling of ``last_movement``
#: is a loop that is permanently, invisibly, not silent-detectable, and the
#: agreement test that was supposed to catch that covered every field *except*
#: ``state``, which was the one spelled as a literal in one layer and a
#: constant in the other.

#: The safety plan a main made **with a professional** and gave Half to hold
#: (CAP-12, story 6c). A list of lines, in the order they were written, kept
#: exactly as they were given.
#:
#: Named here for the reason ``CONTACT`` is: the layer that owns record shapes
#: owns which shapes may leave the store for the crisis path. A safety plan is
#: not a claim Half derived — it is a document somebody else authored — and
#: Half must be structurally unable to write one, which is why nothing in this
#: module composes, completes or reformats the value it carries.
PLAN: Final[str] = "plan"

#: The IANA zone the main **told** Half they sleep in (AD-9, story 9a), and the
#: two fields of the ``schedule`` record that carry the answer forward.
#:
#: Named here for the reason ``CONTACT`` and ``REGION`` are: the layer that
#: owns record shapes owns the spelling, and ``half.schedule`` — which sits
#: above the store, above the ladder and above the actor — imports them rather
#: than declaring a second copy. ``LOOP`` runs the other way because the
#: open-loop package sits *below* this module; this one cannot, because
#: ``half.schedule.due`` reads the ladder and the ladder reads this file.
#:
#: ``ZONE`` is a belief field — where the main is, is an answer they gave, and
#: it takes the same admission path as any other claim about them.
#: ``NEXT_PASS_AT`` and ``TOLD_ZONE`` are scheduler state and appear only on a
#: ``schedule`` record.
ZONE: Final[str] = "zone"
NEXT_PASS_AT: Final[str] = "next_pass_at"
TOLD_ZONE: Final[str] = "told_zone"

#: What a ``touch`` record carries besides the loop it raised (CAP-8, story 10).
#:
#: Named here for the reason ``ZONE`` and ``NEXT_PASS_AT`` are: the layer that
#: owns record shapes owns the spelling, and ``half.surface`` — which sits
#: above the ladder, the context builder and the channel — imports them rather
#: than declaring a second copy. ``LOOP`` runs the other way because the
#: open-loop package sits *below* this module, and a touch names its loop in
#: exactly that field, so that ``BeliefLog.expunge_bodies`` tombstones a touch
#: on an erased loop by the same match that tombstones its transitions.
#:
#: ``ORIGIN_KIND``/``ORIGIN_ID`` are what a surface cites — where in the
#: preceding pass it came from.
#:
#: ``LOCAL_DAY`` is **the day marker**, and it is the record's second, separate
#: job. A touch may raise a loop, may spend a main's one unprompted message for
#: a day, or may do both, and the two facts have to be distinguishable: CAP-10's
#: interrupt is a second thing that will raise a loop, and the day it lands it
#: would silently consume the morning budget if *any* raise counted as one. So a
#: record consumes the day if and only if it carries a ``local_day``, and the
#: interrupt will write a raise without one.
#:
#: It is the **stored** day rather than one recomputed later, which is the other
#: half of the rule. A main who moves west between two mornings would otherwise
#: have yesterday's raise recomputed under today's zone and land on today —
#: reproduced as two messages five hours apart.
ORIGIN_KIND: Final[str] = "origin_kind"
ORIGIN_ID: Final[str] = "origin_id"
LOCAL_DAY: Final[str] = "local_day"

#: Whether a message actually reached the main for that day. Beside
#: ``LOCAL_DAY`` rather than folded into it, because the day is spent by two
#: different events and a metrics path has to tell them apart: an ordinary
#: morning (``True``), and the one case where Half consumes a day deliberately
#: without speaking — a day marker it could not read, repaired by writing a
#: readable one, so that an unreadable marker costs one morning instead of
#: every morning after it (``False``).
SENT: Final[str] = "sent"

#: The civil-date shape a day marker takes: ``2026-09-01``, as the main would
#: read it off a wall clock in the zone they told Half.
_CIVIL_DAY: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}")

#: Everything a touch record may carry, beside the reserved four. An
#: **allowlist**, for the reason ``TENSION_FIELDS`` is one: every denylist this
#: codebase has shipped was walked around, and a touch is the record that sits
#: closest to the thing it must never contain. It says *what Half raised, when,
#: and whether that spent the day*; a ``claim``, a ``state`` or a
#: ``last_movement`` riding in beside it would be, respectively, belief content
#: made permanent (AD-22), a wanting demoted by Half's own attention, and Half's
#: contact recorded as the main's progress — the exact conflation story 8 split
#: this op out to prevent.
#:
#: ``tombstone`` is deliberately **absent**, unlike ``TENSION_FIELDS``. Review
#: found that listing it let a caller write ``tombstone=True`` on a live touch
#: through ``Store.record``: durable, skipped by the fold, and therefore
#: invisible to both the daily rule and the bound. ``BeliefLog.expunge_bodies``
#: does not need the allowance — it builds its stub and appends the line itself,
#: without passing through this gate at all.
TOUCH_FIELDS: Final[frozenset[str]] = frozenset(
    {LOOP, ORIGIN_KIND, ORIGIN_ID, LOCAL_DAY, SENT}
)

#: What an ``asked`` record carries: the question Half spent a favour on, and
#: the belief whose ambiguity it would resolve (CAP-4, story 5b).
#:
#: Named here for the reason ``ORIGIN_KIND`` and ``LOCAL_DAY`` are: the layer
#: that owns record shapes owns the spelling, and ``half.trust`` — which sits
#: above the ladder and the store — imports them rather than declaring a second
#: copy. A second spelling of ``question`` is a spend the balance cannot see,
#: and a spend the balance cannot see is a favour that buys two questions.
#:
#: **Two ids and nothing else.** ``ABOUT`` is required rather than optional for
#: the reason a touch's origin is required: a spend that cannot say what it was
#: about is a permission consumed with no trace of what for, and the log is
#: append-only. Neither field is text a main would recognise — the question's
#: wording is composed at delivery (story 11) and is never durable (AD-22).
QUESTION: Final[str] = "question"
ABOUT: Final[str] = "about"

#: Everything an ``asked`` record may carry, beside the reserved four. An
#: **allowlist**, for the reason ``TOUCH_FIELDS`` and ``TENSION_FIELDS`` are
#: allowlists: every denylist this codebase has shipped was walked around, and
#: this is the record that sits closest to the one thing it must never contain.
#: A ``claim``, a ``text`` or an ``answer`` riding in beside the ids would be
#: the main's own uncertainty made permanent, which is AD-22 at the one layer
#: where it cannot be taken back.
#:
#: ``tombstone`` is deliberately **absent**, exactly as it is from
#: ``TOUCH_FIELDS`` and for the same finding: listing it let a caller write
#: ``tombstone=True`` on a live record through ``Store.record``, producing a
#: durable line the fold skips. ``BeliefLog.expunge_bodies`` builds its stub and
#: appends the line itself, without passing through this gate.
ASKED_FIELDS: Final[frozenset[str]] = frozenset({QUESTION, ABOUT})


def is_civil_day(value: object) -> bool:
    """Whether ``value`` is a day marker this build can read. Never raises.

    Shape **and** calendar: ``2026-02-31`` matches the pattern and is not a
    day, and a marker nothing can read is the failure the day rule fell into
    once already.
    """
    return (
        isinstance(value, str)
        and _CIVIL_DAY.fullmatch(value) is not None
        and moment(value) is not None
    )


#: The one record kind the scheduler may see, and the only fields of it that
#: leave the store. Narrowed by field for the reason ``HANDOFF_VISIBLE`` is: a
#: belief carrying both a zone and a claim about the main is the most ordinary
#: shape there is once *"I'm in Delhi"* has been said in a sentence, and the
#: scheduler has no business holding the claim. What it gets is a zone key and
#: the ladder's own evidence for whether the main actually told Half.
ZONE_VISIBLE: Final[tuple[str, ...]] = (
    "id", ZONE, "license", "support", "known_to_main", QUARANTINED,
)


def zone_record(record: Mapping[str, Any] | Any) -> bool:
    """Whether ``record`` names a timezone the main told Half.

    Beside ``handoff_record`` and ``plan_record``, narrowing the same way and
    for a related reason: the scheduler runs outside any turn and outside the
    crisis gate, so what it can reach has to be decided here rather than by
    whichever module happens to ask.
    """
    if not isinstance(record, Mapping):
        return False
    value = record.get(ZONE)
    return isinstance(value, str) and bool(value.strip())


def zone_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """``record`` reduced to what the scheduler may see."""
    return {name: record[name] for name in ZONE_VISIBLE if name in record}


#: The only fields of a belief record the nightly pass may see (CAP-7, story
#: 9c): its id, when it was written, and what it cites.
#:
#: Narrowed by field for the reason ``ZONE_VISIBLE`` and ``HANDOFF_VISIBLE``
#: are, and here the reason is sharper than either. The pass reads the **log**
#: rather than the fold — it has to, because *"what did this entry cite a week
#: ago"* is a question the fold cannot answer and the alternative is storing a
#: counter for the pass to mutate (AD-30). A log read is every claim Half holds
#: about the main, in full, and the pass has business with none of it: what
#: decides whether a disagreement is widening is how many sources an entry
#: cites, not what it says. So the claim, the subject, the ledger, the contact,
#: the plan and every other field stay behind this line.
HISTORY_VISIBLE: Final[tuple[str, ...]] = ("id", "t", "support")


def history_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """``record`` reduced to what the nightly pass may see."""
    return {name: record[name] for name in HISTORY_VISIBLE if name in record}


def handoff_record(record: Mapping[str, Any] | Any) -> bool:
    """Whether ``record`` is phone-book material.

    The narrowing itself, kept here rather than in the registry so that the
    layer that owns record shapes owns the definition of which shapes the
    crisis path may reach. A record with neither field is a claim about the
    main and stays behind the disabled retriever.
    """
    if not isinstance(record, Mapping):
        return False
    return any(
        isinstance(record.get(name), str) and record[name].strip()
        for name in HANDOFF_FIELDS
    )


#: The only fields of a phone-book record that leave the store for the crisis
#: path: what a door is, and what the ladder needs to decide whether it may be
#: offered at all. ``id`` travels because an offer has to be stable across two
#: identical turns.
HANDOFF_VISIBLE: Final[tuple[str, ...]] = (
    "id", CONTACT, HANDLE, IS_CLINICIAN, REGION,
    "license", "support", "known_to_main", QUARANTINED,
)


def handoff_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """``record`` reduced to what the handoff may see.

    **Whole records were the hole.** A belief carrying a contact field *and* a
    claim about the main — the most ordinary shape there is once a person is
    also a subject — brought that claim into the crisis path, which is the one
    place ledger retrieval is hard-disabled (CAP-12, build requirement 3).
    Narrowing by record was not narrowing; this narrows by field, so what the
    mode can reach is a name, a place, and the ladder's own evidence for
    whether either may be named.
    """
    return {name: record[name] for name in HANDOFF_VISIBLE if name in record}


def plan_record(record: Mapping[str, Any] | Any) -> bool:
    """Whether ``record`` holds a safety plan.

    The narrowing, kept beside ``handoff_record`` and for the same reason:
    crisis mode hard-disables ledger retrieval, and producing a held plan must
    not become the route by which the ledger comes back. A record without a
    non-empty ``plan`` list is a claim about the main and stays behind the
    disabled retriever.
    """
    if not isinstance(record, Mapping):
        return False
    lines = record.get(PLAN)
    return isinstance(lines, (list, tuple)) and bool(lines)


#: The only fields of a plan record that leave the store: the plan itself, its
#: id, and the pin the main can put on it. Nothing else — a belief that carries
#: both a plan and a claim about the main hands over the plan and keeps the
#: claim, which is the narrowing ``handoff_projection`` exists for, one field
#: over.
#: ``t`` travels because "the newest plan wins" has to be a fact about time.
#: Sorting by id alone called itself supersession and was not: ids are opaque,
#: so a replaced document came back as the current one whenever its id happened
#: to sort last.
PLAN_VISIBLE: Final[tuple[str, ...]] = ("id", "t", PLAN, QUARANTINED)


def plan_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """``record`` reduced to what the safety-plan path may see.

    The plan's own lines travel **unchanged** — not stripped, not normalised,
    not re-cased, not re-ordered. Whatever is done to them on the way out is
    done by a renderer that can be read; a projection that tidied them would
    make the verbatim guarantee depend on this function having tidied them the
    same way twice.
    """
    return {name: record[name] for name in PLAN_VISIBLE if name in record}


#: Fields that, once set on a belief, survive every later append for that
#: belief. Quarantine is permanent (CAP-10, glossary), and permanence cannot be
#: the caller's job to remember: an ``assert`` record for a quarantined belief
#: that simply omits the field is the most ordinary operation there is, and
#: without this it would unpin the belief and replay would reproduce it
#: unpinned. Permanence that lasts one record is not permanence.
STICKY: Final[tuple[str, ...]] = (QUARANTINED,)


def pinned(value: object) -> bool:
    """Whether a sticky field's value counts as set.

    Anything other than absent or an explicit ``False``. A quarantine flag this
    build cannot interpret is a quarantine flag: the failure mode of misreading
    it has to be the safe one.
    """
    return value is not None and value is not False


def carried_forward(previous: Mapping[str, Any] | None) -> dict[str, Any]:
    """The sticky fields of ``previous`` that a later record cannot drop."""
    if not previous:
        return {}
    return {
        name: previous[name]
        for name in STICKY
        if name in previous and pinned(previous[name])
    }


#: Values the derived view must be able to materialize. Validated before the
#: append, because the log is append-only: a value SQLite cannot coerce would
#: otherwise be durable, and every future rebuild would raise forever.
#:
#: ``support``, ``known_to_main`` and ``quarantined`` are here for a second
#: reason as well as that one: they gate a *permission*. ``license`` was always
#: worth validating at append time, and since story 5a these three decide the
#: same question — a durable ``known_to_main="yes"`` is a belief whose rung
#: turns on a value nothing ever checked.
_TYPED_FIELDS: Final[dict[str, type | tuple[type, ...]]] = {
    "subject": str,
    "claim": str,
    "ledger": str,
    "license": str,
    "independent": int,
    "support": (list, tuple),
    "known_to_main": bool,
    QUARANTINED: bool,
    "rung": str,
    # The phone book, validated at the append for the reason the four fields
    # above are: the log is append-only, so a durable ``clinician="maybe"`` is
    # a contact whose place in a crisis offer turns on a value nothing ever
    # looked at, and a ``contact`` that is not a string is a name nothing can
    # render.
    CONTACT: str,
    HANDLE: str,
    IS_CLINICIAN: bool,
    REGION: str,
    # The held safety plan, validated at the append for the reason the phone
    # book is: the log is append-only, so a plan stored as a bare string — or
    # as a list with a number in it — is a document Half can never render and
    # can never remove either.
    PLAN: (list, tuple),
    # The open-loop ledger (CAP-6). ``loop`` is the slug a belief sits on and
    # the loop a transition names; ``timescale`` is that loop's own period and
    # ``last_movement`` the date it last moved. All three are validated at the
    # append for the reason every field above is: the log is append-only, so a
    # ``timescale`` stored as a number is a loop whose silence can never be
    # computed and whose record can never be taken back.
    LOOP: str,
    TIMESCALE: str,
    LAST_MOVEMENT: str,
    # The due-time queue (AD-9). ``zone`` is the IANA key the main told Half;
    # ``next_pass_at`` is when they are next due and ``told_zone`` whether the
    # zone it was computed in was an answer or the recorded fallback. Validated
    # at the append for the reason every field above is: the log is append-only,
    # and a ``told_zone`` stored as the string "false" is a fallback that reads
    # as an answer for ever.
    ZONE: str,
    NEXT_PASS_AT: str,
    TOLD_ZONE: bool,
    # The morning surface's touch record (CAP-8). ``origin_kind`` and
    # ``origin_id`` are what a surface cites; validated at the append for the
    # reason every field above is, and here the reason is the story's own
    # Always: *nothing is surfaced that cannot say where it came from*. An
    # origin stored as a number is a raise whose provenance no build can ever
    # read back, permanently.
    ORIGIN_KIND: str,
    ORIGIN_ID: str,
    LOCAL_DAY: str,
    SENT: bool,
    # The spend half of the trust balance (CAP-4, story 5b). Validated at the
    # append for the reason every field above is, and here the reason is the
    # currency's own rule: the balance is *computed from the log*, so a
    # ``question`` stored as a number is a spend no build can ever count, and a
    # spend that cannot be counted is a favour that buys a second question for
    # ever.
    QUESTION: str,
    ABOUT: str,
    # The tension ledger (CAP-7). ``between`` names the two entries that
    # disagree, validated at the append for the reason every field above is:
    # the log is append-only, so a ``between`` stored as a bare string is a
    # tension whose two sides can never be compared and whose record can never
    # be taken back. What a *valid* pair looks like is
    # ``validate_tension_fields``' question; this is the type.
    BETWEEN: (list, tuple),
}


#: Everything a tension record may carry, beside the reserved four. An
#: **allowlist**, and the reason is that every denylist this story shipped was
#: walked around: the ranked-field gate matched exact strings, so ``winner``
#: failed and ``moved_side`` and ``winner_id`` were durable, and nothing at all
#: stopped a ``claim`` or an ``independent`` count riding in beside the state on
#: a transition — belief content written into a tension record, which is AD-22
#: at the one layer where it becomes permanent.
#:
#: A tension is a state, a pair, and the license the ladder admitted. Anything
#: else is a field somebody added; widening this set is a deliberate edit with a
#: reviewer on it, which is exactly what story 9d's minting will need.
TENSION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        STATE, BETWEEN, "license", "support", "known_to_main", QUARANTINED,
        # What produced the record, which the replay fixture pins and no rule
        # reads. It says which build wrote a line, never anything about either
        # entry.
        "model_tier",
        # Written by ``BeliefLog.expunge_bodies``, never by a caller.
        "tombstone",
    }
)


def validate_tension_fields(fields: Mapping[str, Any]) -> None:
    """Reject a tension the ledger could never read back (CAP-7, story 9c).

    **Write strict, read tolerant**, on the same terms as a loop transition and
    for the same reason: the log is append-only, so a value that decides how a
    disagreement is named or whether it can be evaluated at all is refused
    *before the record is durable*, with a hard error and never a default.

    * ``state`` — one of the five, or nothing. A sixth, once durable, is a
      disagreement every future fold carries and no build can name. It is
      **optional** rather than required because a transition append carries a
      state and a license change carries none, and demanding one on every
      record would make promoting a tension impossible without restating it.
    * ``state`` is never `resolved`. Resolution is what the log *already means*
      the moment a correction to one of the two entries lands, computed by
      ``half.store.fold``; a hand-written one is a second writer of the same
      fact and a second place for the log and the fold to disagree.
      ``ledger.transition`` refuses it too — review found that was the only
      refusal, so ``TensionError``'s own docstring, which promised this gate
      *"refuses the same values one layer down where they would become
      durable"*, was describing a check that did not exist. The word stays in
      the vocabulary, because the fold still has to be able to *read* it.
    * **no ranked side, ever**, and not by exact spelling. A field name that
      *reads* as a verdict on one of the two entries —
      ``half.tensions.widening.ranks_a_side`` — is refused outright, because
      *"neither side of a tension is wrong"* is structural and the log is
      append-only. A ranking written once is one every future fold carries and
      no correction takes back, and the natural way to write it is not malice
      but a helpful line recording which entry the evidence went against so a
      message can be phrased better. Review verified eight spellings of exactly
      that line getting past the old exact-string check, ``moved_side`` among
      them — the very example ``widening`` names.
    * **nothing outside ``TENSION_FIELDS``.** The denylist above says what a
      tension may not rank; this says what a tension *is*. A ``claim`` or an
      ``independent`` count arriving beside the state — which is what a
      transition append could carry until review found it — is belief content
      written into a tension record, permanently (AD-22).
    * ``between`` — two **distinct** entry ids, or nothing. A tension is a
      record linking *two* entries that disagree (glossary); one naming a
      single entry, three of them, or the same entry twice is not a
      disagreement, and stored permanently it is a tension whose drift can
      never be computed. Optional **here** because a transition does not
      restate the pair; that a tension's *first* record must carry one is
      ``Store.append``'s rule, because only the store knows which ids the fold
      has already seen.

    There is no branch here that picks a state for the main, none that supplies
    a missing side, and none that puts the two sides in an order.

    The read direction is deliberately looser — see ``half.store.fold`` — so a
    log written by a *later* build, through the Ask-First path that adds a
    state, still folds. A build that refused to read it would take a main's
    whole store down over one word, where carrying it through costs that one
    tension its evaluation and nothing else.
    """
    state = fields.get(STATE)
    if state is not None and not is_tension_state(state):
        raise TensionError(
            f"field {STATE!r} must be one of {', '.join(sorted(TENSION_STATES))} "
            f"on a {Op.TENSION.value} record, got {state!r}"
        )
    if state == TensionState.RESOLVED.value:
        raise TensionError(
            f"a {Op.TENSION.value} record may not be written {state!r}: a "
            f"tension resolves when one of its two entries leaves the ledger, "
            f"which the fold computes the moment that correction lands. A "
            f"second writer of it is a second place for the log and the fold "
            f"to disagree"
        )
    refused = ranked_names(fields)
    if refused:
        # The value is deliberately not quoted back: it names one of the main's
        # own entries, and an exception message reaches a log line through
        # every handler that formats one (AD-22). The field name is enough.
        raise TensionError(
            f"a {Op.TENSION.value} record may not carry {list(refused)}: neither "
            f"side of a tension is wrong. For a person both entries can be true "
            f"at once, which is the whole reason the object exists — a tension "
            f"names the gap and never renders the verdict"
        )
    stray = sorted(fields.keys() - TENSION_FIELDS)
    if stray:
        raise TensionError(
            f"a {Op.TENSION.value} record may not carry {stray}: a tension is a "
            f"state, the pair of entries it links and the license the ladder "
            f"admitted. Everything a tension is about lives on those two "
            f"entries, and a claim written here is one no correction to either "
            f"of them can ever take back"
        )
    pair = fields.get(BETWEEN)
    if pair is None:
        return
    ids = list(pair) if isinstance(pair, (list, tuple)) else []
    if (
        len(ids) != SIDES
        or not all(isinstance(item, str) and item.strip() for item in ids)
        or len(set(ids)) != SIDES
    ):
        raise TensionError(
            f"field {BETWEEN!r} must name exactly {SIDES} distinct entries on a "
            f"{Op.TENSION.value} record; a tension is the record of two entries "
            f"that disagree, and one that names any other number is a "
            f"disagreement nothing can ever evaluate"
        )


def validate_schedule_fields(fields: Mapping[str, Any]) -> None:
    """Reject a ``schedule`` record the scheduler could never read back (AD-9).

    **Write strict, read tolerant**, on the same terms as a loop transition and
    for a sharper version of the same reason.

    * ``next_pass_at`` — **required**, and a stamp ``half.civil`` can actually
      read. A due time nothing can parse folds to a main who has never been
      scheduled, which is not a silent no-op: it makes the next tick schedule
      them afresh, every tick, for ever. Refused before it is durable.
    * ``zone`` — required, because a due time that cannot say what zone it was
      computed in cannot be checked against the main's own answer, and the one
      thing this record exists to make visible is which of the two it was.

    ``told_zone`` is left to the generic type check above: it is a bool or it
    is refused there, and its absence means the same thing false does.

    The read direction is deliberately looser — see ``half.store.fold`` — so a
    due time this build cannot interpret costs one main one pass rather than
    taking their whole store down.
    """
    at = fields.get(NEXT_PASS_AT)
    if not isinstance(at, str) or instant(at) is None:
        raise ScheduleError(
            f"a {Op.SCHEDULE.value} record must carry {NEXT_PASS_AT!r} as a UTC "
            f"stamp this build can read (YYYY-MM-DDThh:mm[:ss]Z), got "
            f"{at!r}; a due time nothing can parse is a main who is never due "
            f"again, or due on every tick for ever, and the record would be "
            f"durable"
        )
    zone = fields.get(ZONE)
    if not isinstance(zone, str) or not zone.strip():
        # The value is deliberately **not** quoted back (AD-22). A zone is
        # where the main lives, and an exception message reaches a log line
        # through every handler that formats one. The type is enough to fix
        # the caller.
        raise ScheduleError(
            f"a {Op.SCHEDULE.value} record must name the zone it was computed "
            f"in as {ZONE!r} — a non-empty string, got "
            f"{type(zone).__name__}; without it a recorded fallback is "
            f"indistinguishable from an answer"
        )


def validate_touch_fields(fields: Mapping[str, Any]) -> None:
    """Reject a touch the surface could never read back (CAP-8, story 10).

    **Write strict, read tolerant**, on the same terms as a loop transition, a
    schedule record and a tension — and here the strictness protects the two
    rules that exist to keep Half quiet.

    A touch does one of two jobs, or both, and it must do at least one:

    * it **raises a loop** — ``loop`` names the wanting, and the per-loop
      nagging bound measures the next raise against this one;
    * it **spends the day** — ``local_day`` is the main's own civil date, and
      the one-a-day rule reads it.

    A record carrying neither says nothing and is refused: the fold raises
    ``CorruptLogError`` on one, and folding it to nothing is the silent
    omission AD-29 exists to prevent.

    The rest:

    * ``local_day`` — the **stored** day, in shape *and* calendar. A marker
      nothing can read is a main silenced on every morning after it, which is
      the failure review reproduced; ``2026-02-31`` matches the shape and is
      not a day, so ``is_civil_day`` checks both. Refused before it is durable.
    * ``sent`` — a bool, and **required with** ``local_day``. A day spent
      without a message is a real and deliberate outcome (see ``SENT``), and a
      marker that cannot say which it was is a metrics path with nothing to
      count.
    * ``sent`` without ``local_day`` is refused: it would claim a message was
      sent on no particular day.
    * ``origin_kind``/``origin_id`` — required of any touch that **surfaced
      something**: one that raised a loop, or one that sent a message. This is
      *"nothing is surfaced that cannot say where it came from"* written as a
      check rather than as a paragraph. A day marker that raised nothing and
      sent nothing cites nothing, because there is nothing to cite.
    * **nothing outside ``TOUCH_FIELDS``.** The allowlist is the point — see
      that constant, including why ``tombstone`` is not in it.

    There is no branch here that supplies a missing origin, picks a loop,
    defaults a kind, or invents a day.

    The read direction is deliberately looser — see ``half.store.fold``, which
    is fatal only on a record that names neither job — so a log written by a
    later build, through the Ask-First path that adds an origin kind, costs one
    loop its bound rather than taking a main's whole store down.
    """
    stray = sorted(fields.keys() - TOUCH_FIELDS)
    if stray:
        raise TouchError(
            f"a {Op.TOUCH.value} record may not carry {stray}: a touch is the "
            f"loop Half raised, the day it spent, and what it cited. A claim "
            f"written here is content no correction can take back, and a state "
            f"or a movement date written here is Half's own attention recorded "
            f"as the main's progress"
        )
    loop = fields.get(LOOP)
    raises = loop is not None
    if raises and (not isinstance(loop, str) or not loop.strip()):
        raise TouchError(
            f"a {Op.TOUCH.value} record that names a loop must name it as a "
            f"non-empty slug in {LOOP!r}; a raise that names no loop bounds no "
            f"loop, and the record would be durable"
        )
    day = fields.get(LOCAL_DAY)
    marks = day is not None
    if not raises and not marks:
        raise TouchError(
            f"a {Op.TOUCH.value} record must either name the loop it raised in "
            f"{LOOP!r} or the day it spent in {LOCAL_DAY!r}; one that does "
            f"neither records nothing, and the fold cannot fold it"
        )
    if marks and not is_civil_day(day):
        raise TouchError(
            f"field {LOCAL_DAY!r} must be the main's own civil day this build "
            f"can read (YYYY-MM-DD), got {day!r}; a day marker nothing can read "
            f"is a main silenced on every morning after it, and the record "
            f"would be durable"
        )
    sent = fields.get(SENT)
    if sent is not None and not marks:
        raise TouchError(
            f"field {SENT!r} says whether a message reached the main for a "
            f"particular day; it may not be carried without {LOCAL_DAY!r}"
        )
    if marks and not isinstance(sent, bool):
        raise TouchError(
            f"a {Op.TOUCH.value} record marking a day must say in {SENT!r} "
            f"whether a message reached the main, got {type(sent).__name__}; a "
            f"day spent without one is a real outcome and has to be countable"
        )
    if not (raises or sent):
        # A day marker that raised nothing and sent nothing — the repair path.
        # It cites nothing because it surfaced nothing.
        return
    kind = fields.get(ORIGIN_KIND)
    if kind not in TOUCH_ORIGINS:
        raise TouchError(
            f"field {ORIGIN_KIND!r} must be one of "
            f"{', '.join(sorted(TOUCH_ORIGINS))} on a {Op.TOUCH.value} record "
            f"that raised a loop or sent a message, got {kind!r}; nothing is "
            f"surfaced that cannot say where it came from, and the log is "
            f"append-only"
        )
    origin = fields.get(ORIGIN_ID)
    if not isinstance(origin, str) or not origin.strip():
        raise TouchError(
            f"field {ORIGIN_ID!r} must name the thing in the preceding pass "
            f"this raise came from; a kind with no id names a category rather "
            f"than a thing, got {type(origin).__name__}"
        )


def validate_asked_fields(fields: Mapping[str, Any]) -> None:
    """Reject a spend the balance could never count back (CAP-4, story 5b).

    **Write strict, read tolerant**, on the same terms as a touch, a loop
    transition, a schedule record and a tension — and here the strictness
    protects the one rule the whole currency rests on: *the favour buys the
    question*, and the same favour cannot buy two.

    * ``question`` — **required**, a non-empty id. The balance is computed from
      the log rather than counted into a field, so a spend nothing can read is
      a question that was asked and never paid for. The log is append-only, so
      that would be permanent.
    * ``about`` — **required**, the belief whose ambiguity this question would
      resolve. Required rather than encouraged for the reason a touch's origin
      is required: a permission consumed with no trace of what it was consumed
      for is exactly the record a later reviewer cannot audit, and there is no
      branch here that supplies a missing one.
    * **nothing outside ``ASKED_FIELDS``.** The allowlist is the point — see
      that constant, including why ``tombstone`` is not in it.

    Neither field's *value* is quoted back in a refusal. A question is about a
    main's own life, and an exception message reaches a log line through every
    handler that formats one (AD-22); the type is enough to fix the caller.

    The read direction is deliberately looser — see ``half.store.fold``, which
    is fatal only on a record naming no question — so a log written by a later
    build costs one spend rather than taking a main's whole store down.
    """
    stray = sorted(fields.keys() - ASKED_FIELDS)
    if stray:
        raise TrustError(
            f"an {Op.ASKED.value} record may not carry {stray}: a spend is the "
            f"question's id and the belief it was about. A claim, a wording or "
            f"an answer written here is the main's own uncertainty made "
            f"permanent, and no correction takes it back"
        )
    question = fields.get(QUESTION)
    if not isinstance(question, str) or not question.strip():
        raise TrustError(
            f"an {Op.ASKED.value} record must name the question it spent a "
            f"favour on in {QUESTION!r} as a non-empty id, got "
            f"{type(question).__name__}; the balance is computed from the log, "
            f"so a spend nothing can read is a question that was never paid for"
        )
    about = fields.get(ABOUT)
    if not isinstance(about, str) or not about.strip():
        raise TrustError(
            f"an {Op.ASKED.value} record must name the belief it was about in "
            f"{ABOUT!r} as a non-empty id, got {type(about).__name__}; a "
            f"permission consumed with no trace of what it was consumed for is "
            f"a spend nobody can audit, and the log is append-only"
        )
    padded = sorted(name for name in (QUESTION, ABOUT) if fields[name].strip() != fields[name])
    if padded:
        # **Normalized before it is durable**, the same rule
        # ``touch._loop_id`` applies to a loop slug. ``half.trust.unasked``
        # strips both ids at ``Unasked``'s boundary, and this is what makes
        # that a property of the log rather than of one caller's care: review
        # found the queue matching on ``about.strip()`` while the spend passed
        # the raw string, so an append-only record could permanently name a
        # belief id that no belief equals.
        raise TrustError(
            f"an {Op.ASKED.value} record carries {padded} with surrounding "
            f"whitespace; the id that was weighed must be the id that is "
            f"written, and the log is append-only"
        )


def _type_names(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return " or ".join(t.__name__ for t in expected)
    return expected.__name__


def validate_loop_fields(fields: Mapping[str, Any]) -> None:
    """Reject a loop transition the ledger could never read back (CAP-6).

    **Write strict, read tolerant**, and the asymmetry is the whole design. The
    log is append-only and the open-loop ledger is the ranking function for
    everything Half does, so every value that decides how a loop is weighed or
    whether it is silent is refused **before the record is durable**, with a
    hard error and never a default:

    * ``loop`` — **required**, because the fold raises ``CorruptLogError`` on a
      transition that names none. Without this check that record was accepted,
      became durable, and then bricked every future rebuild for that main with
      the offending line unremovable: the exact failure this gate exists to
      prevent, arriving through the gate's own blind spot.
    * ``state`` — one of the four, or nothing. A fifth, once durable, is a
      wanting every future fold carries and no build can weigh.
    * ``timescale`` — one of the four, or nothing. An unknown one is a loop
      whose silence, and therefore whose nagging bound, can never be computed.
    * ``last_movement`` — a stamp ``half.civil`` can actually read. This was the
      hole review found: the paragraphs above argued at length that a bad
      timescale must not become durable, and the identical argument applies
      verbatim to the date the timescale is measured *against*. ``"yesterday"``,
      ``2026-02-31`` and a bare ``2026-01-01`` all went in permanently, and a
      loop whose movement date cannot be read is exactly as undetectable as one
      with no period — silently, and for ever.

    There is no branch here that picks a state for the main, and none that lends
    a period or a date from a loop this one is nothing like.

    The read direction is deliberately not enforced anywhere: a log written by a
    *later* build, through the Ask-First path that adds a state, still folds and
    still ranks — degrading to ``salience.UNKNOWN_LOOP_STATE`` — because a build
    that refused to read it would take a main's whole retrieval down over a
    tie-break.

    Only ``loop`` is required. A loop may be opened with no timescale, which
    ``timescale.silence`` reports honestly as not detectable, and a transition
    may record movement without changing state.
    """
    loop = fields.get(LOOP)
    if not isinstance(loop, str) or not loop.strip():
        raise LoopError(
            f"a {Op.LOOP_TRANSITION.value} record must name its loop in "
            f"{LOOP!r}; the fold cannot fold one that does not, and the record "
            f"would be durable"
        )
    state = fields.get(STATE)
    if state is not None and not is_state(state):
        raise LoopError(
            f"field {STATE!r} must be one of {', '.join(sorted(LOOP_STATES))} on "
            f"a {Op.LOOP_TRANSITION.value} record, got {state!r}"
        )
    scale = fields.get(TIMESCALE)
    if scale is not None and not is_timescale(scale):
        raise LoopError(
            f"field {TIMESCALE!r} must be one of {', '.join(sorted(TIMESCALES))}, "
            f"got {scale!r}"
        )
    moved = fields.get(LAST_MOVEMENT)
    if moved is not None and moment(moved) is None:
        raise LoopError(
            f"field {LAST_MOVEMENT!r} must be a stamp this build can read "
            f"(YYYY-MM-DD or YYYY-MM-DDThh:mm[:ss]Z), got {moved!r}; a movement "
            f"date nothing can read is a loop that is silently never "
            f"silent-detectable"
        )


def validate_fields(fields: dict[str, Any], *, op: Op | None = None) -> None:
    """Reject a record the derived view could not materialize.

    ``op`` narrows the check to what that op's fields mean. It is optional
    because most fields mean the same thing under every op — a ``support`` set
    is a list of source ids wherever it appears — but ``state`` does not: it
    names a tension's state, a crisis record's, an aftercare answer's *and* a
    loop's, and those are four closed vocabularies, not one. Validating
    ``state`` op-blind would have to accept the union, which accepts
    ``state="widening"`` on a loop.
    """
    if op is Op.LOOP_TRANSITION:
        # **First**, so that a malformed loop field refuses as a ``LoopError``
        # rather than as the generic type check's bare ``ValueError``. The
        # conventions say no public store operation raises a non-``HalfError``,
        # and a caller wrapping the write path in ``except LoopError`` has to
        # catch every refusal this gate makes — including "that is not a
        # string".
        validate_loop_fields(fields)
    if op is Op.SCHEDULE:
        # First, for the reason the loop gate is first: a malformed due time
        # must refuse as a ``ScheduleError`` rather than as the generic type
        # check's bare ``ValueError``.
        validate_schedule_fields(fields)
    if op is Op.TENSION:
        # First, for the reason the loop and schedule gates are first: a
        # malformed state must refuse as a ``TensionError`` rather than as the
        # generic type check's bare ``ValueError``, so a caller wrapping the
        # write path in ``except TensionError`` catches every refusal this gate
        # makes — including "that is not a list".
        validate_tension_fields(fields)
    if op is Op.TOUCH:
        # First, for the reason the three gates above are first: a touch that
        # cites nothing must refuse as a ``TouchError`` rather than as the
        # generic type check's bare ``ValueError``.
        validate_touch_fields(fields)
    if op is Op.ASKED:
        # First, for the reason the four gates above are first: a spend that
        # names no question must refuse as a ``TrustError`` rather than as the
        # generic type check's bare ``ValueError``.
        validate_asked_fields(fields)
    for name, expected in _TYPED_FIELDS.items():
        if name not in fields or fields[name] is None:
            continue
        value = fields[name]
        if expected is int and isinstance(value, bool):
            raise ValueError(f"field {name!r} must be an int, got bool")
        if expected is not bool and isinstance(value, bool):
            # ``True`` is an int and a truthy everything; a bool arriving where
            # a rung or a support set belongs is a caller error, not a value.
            raise ValueError(f"field {name!r} must be {_type_names(expected)}, got bool")
        if not isinstance(value, expected):
            raise ValueError(
                f"field {name!r} must be {_type_names(expected)}, "
                f"got {type(value).__name__}"
            )
    support = fields.get("support")
    if isinstance(support, (list, tuple)) and not all(
        isinstance(item, str) for item in support
    ):
        raise ValueError("field 'support' must hold source ids as strings")
    lines = fields.get(PLAN)
    if isinstance(lines, (list, tuple)) and not all(
        isinstance(item, str) for item in lines
    ):
        # Refused at the append rather than skipped at the render: a plan is
        # produced whole or not at all, and a line this build cannot show is a
        # section missing from a document a clinician wrote.
        raise ValueError(f"field {PLAN!r} must hold the plan's own lines as strings")
    for value in fields.values():
        _reject_untokenizable(value)


def _reject_untokenizable(value: Any) -> None:
    """Raise ``TokenGrowthLimitError`` for text the index could not hold whole.

    Scriptio-continua runs are n-grammed, so a long unspaced run multiplies into
    more terms than ``half.text`` will emit. That has to be refused *here*,
    before the append: the log is append-only and the derived view is rebuilt
    after every append, so a record the tokenizer refuses would be durable while
    every later rebuild — and therefore every later append — raised forever,
    with the offending line unremovable.

    Nested because a field may be a list of strings (topics, people) and those
    are tokenized too, as strand labels.
    """
    if isinstance(value, str):
        terms(value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_untokenizable(item)
    elif isinstance(value, Mapping):
        for item in value.values():
            _reject_untokenizable(item)


def make(op: Op, ident: str, t: str, **fields: Any) -> Record:
    """Build a record for appending. ``t`` is supplied by the caller, never read
    from a clock here — fold and its neighbours stay clock-free (AD-30)."""
    clashing = RESERVED & fields.keys()
    if clashing:
        raise ValueError(f"reserved field(s) may not be passed: {sorted(clashing)}")
    if not ident:
        raise ValueError("id must be a non-empty string")
    if not _ISO_PREFIX.match(t):
        raise ValueError(f"t must be an ISO-8601 timestamp, got {t!r}")
    validate_fields(fields, op=op)
    data: dict[str, Any] = {"t": t, "op": op.value, "id": ident, "v": SCHEMA_VERSION}
    data.update(fields)
    return Record(op=op, id=ident, t=t, data=data)
