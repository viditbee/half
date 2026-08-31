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
from dataclasses import dataclass, field
from typing import Any, Final, Mapping

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

    @property
    def subject(self) -> str | None:
        value = self.data.get("subject")
        return value if isinstance(value, str) else None


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
    if not isinstance(version, int) or version > SCHEMA_VERSION:
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
    if not isinstance(ident, str) or not isinstance(stamp, str):
        raise CorruptLogError("'id' and 't' must be strings", path=path, line=lineno)

    return Record(op=op, id=ident, t=stamp, data=obj)


def encode(record: Record) -> str:
    """Canonical single-line JSON for ``record``.

    Keys are sorted so that encode(decode(x)) is idempotent — required for the
    byte-identical comparisons the replay invariant rests on (AD-4). Existing
    log lines are never rewritten; this is for new appends and round-tripping.
    """
    return json.dumps(
        record.data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def make(op: Op, ident: str, t: str, **fields: Any) -> Record:
    """Build a record for appending. ``t`` is supplied by the caller, never read
    from a clock here — fold and its neighbours stay clock-free (AD-30)."""
    data: dict[str, Any] = {"t": t, "op": str(op), "id": ident, "v": SCHEMA_VERSION}
    data.update(fields)
    return Record(op=op, id=ident, t=t, data=data)
