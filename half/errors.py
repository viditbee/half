"""Typed failures for Half. Adapters translate transport errors at the port
boundary; nothing outside this module raises a bare Exception for a domain fault.
"""

from __future__ import annotations


class HalfError(Exception):
    """Base for every Half domain failure."""


class StoreError(HalfError):
    """A fault in the per-main store."""


class UnknownOpError(StoreError):
    """A log record carried an op outside the closed vocabulary (AD-29).

    Never skipped. An unknown op means this build cannot faithfully fold the
    log, and folding on regardless would produce state that silently omits
    whatever the unknown records said.
    """

    def __init__(self, op: str, *, path: str, line: int) -> None:
        self.op = op
        self.path = path
        self.line = line
        super().__init__(f"unknown op {op!r} at {path}:{line}")


class CorruptLogError(StoreError):
    """A log line could not be parsed (AD-3).

    Also raised for ambiguity a lenient parser would swallow: duplicate object
    keys, non-finite numbers.
    """

    def __init__(self, reason: str, *, path: str, line: int) -> None:
        self.reason = reason
        self.path = path
        self.line = line
        super().__init__(f"corrupt log line at {path}:{line}: {reason}")


class SchemaVersionError(StoreError):
    """A record declared a schema version this build cannot read."""


class SecretLeakError(StoreError):
    """Secret material was found somewhere it must never appear (AD-11)."""
