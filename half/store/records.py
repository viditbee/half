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
from half.store.ops import SCHEMA_VERSION, Op, parse_op

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

#: Values the derived view must be able to materialize. Validated before the
#: append, because the log is append-only: a value SQLite cannot coerce would
#: otherwise be durable, and every future rebuild would raise forever.
_TYPED_FIELDS: Final[dict[str, type | tuple[type, ...]]] = {
    "subject": str,
    "claim": str,
    "ledger": str,
    "license": str,
    "independent": int,
}


def validate_fields(fields: dict[str, Any]) -> None:
    """Reject a record the derived view could not materialize."""
    for name, expected in _TYPED_FIELDS.items():
        if name not in fields or fields[name] is None:
            continue
        value = fields[name]
        if expected is int and isinstance(value, bool):
            raise ValueError(f"field {name!r} must be an int, got bool")
        if not isinstance(value, expected):
            raise ValueError(
                f"field {name!r} must be {expected.__name__}, "
                f"got {type(value).__name__}"
            )


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
    validate_fields(fields)
    data: dict[str, Any] = {"t": t, "op": op.value, "id": ident, "v": SCHEMA_VERSION}
    data.update(fields)
    return Record(op=op, id=ident, t=t, data=data)
