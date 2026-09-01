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


class QueryTooLargeError(StoreError):
    """A query could not be tokenized within the bounded retrieval budget.

    A ``StoreError``, because the store promises that only typed store faults
    cross its boundary — and a *distinct* one, because the turn path treats the
    two oppositely. A general ``StoreError`` means the index is unavailable and
    the turn must fail loudly, so the main's message stays undelivered and
    redelivery still works. This one means Half was handed more text than it
    will tokenize: the ranking is lost, the reply is not.
    """


class SchemaVersionError(StoreError):
    """A record declared a schema version this build cannot read."""


class SecretLeakError(StoreError):
    """Secret material was found somewhere it must never appear (AD-11)."""


class LadderError(HalfError):
    """A license change the ladder refuses (CAP-10).

    Raised only by the *writing* half of ``half.governance.ladder`` — promotion,
    demotion, quarantine. The *reading* half never raises: resolving a license
    happens on the turn's reply path, so an exception there would cost the main
    their answer, and the weakest rung is what an unreadable license means.

    A refusal is loud on purpose. Every path this rejects is a path that would
    have let Half assert something it has not earned the right to say, and the
    caller has to notice that rather than discover it in the belief set later.
    """


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


class CrisisError(HalfError):
    """A crisis path was asked for something it must not produce (CAP-12).

    Raised only for a caller mistake — asking the template assembly for a reply
    to a tier that has none, or raising vigilance with a tier that would enter
    the mode. Never raised on the reply path a main is waiting on: going quiet
    in crisis is one of the two documented catastrophic failures, so nothing
    here converts a main's message into silence.
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
