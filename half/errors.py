"""Typed failures for Half. Adapters translate transport errors at the port
boundary; nothing outside this module raises a bare Exception for a domain fault.
"""

from __future__ import annotations


class HalfError(Exception):
    """Base for every Half domain failure."""


class TokenGrowthLimitError(HalfError):
    """Text exceeded the bounded growth budget of the shared tokenizer (CAP-9).

    Scriptio-continua runs are n-grammed, which multiplies term counts, so both
    the input length and the emitted term count carry explicit ceilings. Neither
    is enforced by dropping the tail: a belief indexed by its first half and
    unreachable by its second, with nothing recording that it happened, is the
    silent failure AD-24 exists to prevent. It is raised by ``half.text`` and so
    belongs to no one layer — the store meets it at index time and retrieval
    meets it at query time.
    """


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


class RetrievalError(HalfError):
    """A fault in the retrieval layer (CAP-9)."""


class RetrievalDisabled(RetrievalError):
    """Retrieval was queried while switched off (CAP-12).

    Loud on purpose. Crisis mode hard-disables ledger retrieval, and the
    tempting implementation returns an empty result instead — which is
    indistinguishable from "this main has no beliefs" and reads, one layer up,
    as Half not having access to its own memory. A disabled retriever raises so
    that a caller which forgot to branch fails visibly rather than quietly.
    """


class ChannelError(HalfError):
    """A fault in the messaging channel."""


class SendFailed(ChannelError):
    """A platform refused or failed a send.

    ``retryable`` separates a transient transport fault from a permanent
    refusal, because the two want opposite handling and a caller that cannot
    tell them apart will either hammer a dead endpoint or drop a recoverable
    message.
    """

    def __init__(self, reason: str, *, retryable: bool) -> None:
        self.retryable = retryable
        super().__init__(f"{'transient' if retryable else 'permanent'}: {reason}")


class UnknownSender(ChannelError):
    """Inbound from an address belonging to no registered main."""


class NotReachable(ChannelError):
    """Half may not contact this main unprompted right now (AD-7)."""


class ForbiddenRecipient(ChannelError):
    """An outbound send was addressed to someone other than the main (AD-25)."""
