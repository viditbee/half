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

from half.errors import CorruptLogError, SchemaVersionError, UnknownOpError
from half.loops.states import LOOP_STATES, is_state
from half.loops.timescale import TIMESCALES, is_timescale
from half.store.ops import SCHEMA_VERSION, Op, parse_op
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

#: The open-loop fields, named here for the reason ``QUARANTINED`` is: the
#: append gate, the fold and the ledger all need the spelling, and only one
#: layer may own it. ``half.loops.ledger`` spells them once too and the two
#: agree by test — a second spelling of ``last_movement`` is a loop that is
#: permanently, invisibly, not silent-detectable.
LOOP: Final[str] = "loop"
TIMESCALE: Final[str] = "timescale"
LAST_MOVEMENT: Final[str] = "last_movement"

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
}


def _type_names(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return " or ".join(t.__name__ for t in expected)
    return expected.__name__


def validate_loop_fields(fields: Mapping[str, Any]) -> None:
    """Reject a loop transition the ledger could never read back (CAP-6).

    **Write strict, read tolerant**, and the asymmetry is the whole design. The
    log is append-only and the open-loop ledger is the ranking function for
    everything Half does: a state outside the closed vocabulary, once durable,
    is a wanting that every future fold carries and no build can weigh, and a
    timescale outside its vocabulary is a loop whose silence — and therefore
    whose nagging bound — can never be computed. So both are refused **before
    the record is durable**, with a hard error and never a default. There is no
    branch here that picks a state for the main, and none that lends a period
    from a loop this one is nothing like.

    The other direction is deliberately not enforced anywhere: a log written by
    a *later* build, through the Ask-First path that adds a state, still folds
    and still ranks — degrading to ``salience.UNKNOWN_LOOP_STATE`` — because a
    build that refused to read it would take a main's whole retrieval down over
    a tie-break.

    Neither field is *required*. A loop may be opened with no timescale, which
    ``timescale.silence`` reports honestly as not detectable, and a transition
    may record movement without changing state.
    """
    state = fields.get("state")
    if state is not None and not is_state(state):
        raise ValueError(
            f"field 'state' must be one of {', '.join(sorted(LOOP_STATES))} on a "
            f"{Op.LOOP_TRANSITION.value} record, got {state!r}"
        )
    scale = fields.get(TIMESCALE)
    if scale is not None and not is_timescale(scale):
        raise ValueError(
            f"field {TIMESCALE!r} must be one of {', '.join(sorted(TIMESCALES))}, "
            f"got {scale!r}"
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
    if op is Op.LOOP_TRANSITION:
        validate_loop_fields(fields)
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
