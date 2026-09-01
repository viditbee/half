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


class LoopError(HalfError, ValueError):
    """An open-loop change the ledger or the append gate refuses (CAP-6).

    Raised by the *writing* half of ``half.loops.ledger`` — opening a loop with
    a state outside the vocabulary, moving one to a date that is not a date, or
    recording `abandoned-but-unadmitted` without both a candidate and the main's
    confirmation — and by ``records.validate_loop_fields``, which refuses the
    same values one layer down where they would become durable. The *reading*
    half never raises: reading a loop happens on the turn's ranking path, and an
    exception there would cost the main their reply over a tie-break, so an
    unreadable field degrades instead.

    **Also a ``ValueError``**, and deliberately both. The conventions say no
    public store operation raises a non-``HalfError``, so a caller wrapping the
    write path in ``except HalfError`` has to catch the append gate's refusals —
    which before this were bare ``ValueError``s that slipped straight through.
    But ``validate_fields`` has raised ``ValueError`` for every other malformed
    field since story 1, and callers written against that must not start
    leaking either. Inheriting from both is how one refusal answers to both
    names rather than one of them silently winning.

    A refusal is loud on purpose. The log is append-only, so every path this
    rejects is one that would have put a permanent value into the ledger that
    ranks everything Half does — and the caller has to notice that now, not
    discover it in the loop set later.
    """


class ScheduleError(HalfError, ValueError):
    """A scheduling value the append gate refuses (AD-9, story 9a).

    Raised by ``records.validate_schedule_fields`` for a ``next_pass_at`` this
    build cannot read back, and by ``half.schedule.tick`` when a tick cannot be
    file-locked at all. The log is append-only, so a due time nothing can parse
    is a main who is either never due again or due on every tick for ever, with
    the offending line unremovable.

    **Also a ``ValueError``**, and for the reason ``LoopError`` is both: the
    conventions say no public store operation raises a non-``HalfError``, while
    ``validate_fields`` has raised bare ``ValueError`` for every malformed field
    since story 1. Inheriting from both is how one refusal answers to both names
    rather than one of them silently winning.
    """


class TensionError(HalfError, ValueError):
    """A tension change the ledger or the append gate refuses (CAP-7, story 9c).

    Raised by the *writing* half of ``half.tensions.ledger`` — moving a tension
    to a state outside the vocabulary, or to `resolved`, which is not a state
    anything decides — and by ``records.validate_tension_fields``, which refuses
    the same values one layer down where they would become durable. That second
    half was a claim rather than a check until review: a hand-written
    ``state="resolved"`` validated and folded, so the only refusal was the one
    a caller could route around by building the record itself. It refuses now,
    along with a ranked field under any spelling and any field a tension has no
    business carrying. ``ActorRegistry.note_transition`` raises it too, for a
    transition naming a tension the log does not hold or planned from a state
    the log has since left.

    The *reading* half never raises: reading a tension happens on the nightly
    pass, and one unreadable tension must cost that tension its evaluation
    rather than the whole pass.

    **Also a ``ValueError``**, and for the reason ``LoopError`` and
    ``ScheduleError`` are both: the conventions say no public store operation
    raises a non-``HalfError``, while ``validate_fields`` has raised bare
    ``ValueError`` for every malformed field since story 1. Inheriting from both
    is how one refusal answers to both names rather than one of them silently
    winning.

    A refusal is loud on purpose. The log is append-only, so every path this
    rejects is one that would put a permanent state into the record of a
    disagreement — and a tension in a state no build can name is a mirror
    nothing can read back.
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


class ModelError(HalfError):
    """A fault in the model port (AD-19).

    **Deliberately narrow, and it is worth saying what it is not.** The four
    things the port answers *with* — unavailable, refused, over-budget and
    malformed — are values, not exceptions: what a failure *means* is the
    caller's to decide, and a crisis caller that fails toward entering, a
    consolidation caller that fails toward skipping and a reply that fails
    toward silence cannot share one default. An exception would make the port
    pick one for all three.

    So a ``ModelError`` is a *caller or operator mistake* — a tier this build
    cannot name, a breakpoint pointing past the prompt, a budget that admits
    nothing, a request shape the provider will never accept. Those are faults
    in the build, not answers from a provider, and a value nobody has to check
    is exactly how they get shipped.

    ``TransportFault`` below is the one branch that is *not* raised out of the
    port; it is the vocabulary a transport reports faults in, and the port
    turns each one into a value at its boundary.
    """


class UnknownTier(ModelError):
    """A tier the build does not know, or a main with no tier at all (AD-20).

    Raised rather than defaulted. A global fallback tier is the failure AD-20
    exists to prevent in both directions at once: it either overpays for every
    free main or quietly underserves a paid one, and it does so silently, which
    is what makes it a bug nobody finds.
    """


class BreakpointError(ModelError):
    """A cache breakpoint the port will not place where it was asked (AD-19).

    Never clamped, never moved, and — since review round 1 — never *silently
    ineffective* either. A prefix under the model's own minimum caches nothing
    at the provider, with no error and no cache-creation tokens, so placing the
    marker anyway would be the hidden breakpoint AD-19 forbids wearing the
    clothes of an honoured one. Refusing says so out loud, and the caller's
    remedy is to state no breakpoint.
    """


class BudgetError(ModelError):
    """A cost budget or a price table that could not admit an honest call
    (CAP-7).

    A misconfiguration, not a refusal: a per-call ceiling above the per-pass
    one, a limit of zero, or a negative price in a deployment's own model table
    all mean the ceiling is not the one that was meant. A negative price is the
    worst of the three, because it makes an estimate negative and *every*
    budget admits it.
    """


class ModelMisconfigured(ModelError):
    """The port was wired without something it cannot run without (AD-11).

    A missing key is the case this exists for, and it is deliberately **not** a
    refusal: nothing was asked of a provider and nothing declined. Review round
    1 found it raised as ``ModelRefused``, which contradicted this module's own
    contract that a refusal is never raised out of the port — and the test
    caught the base class, so the wrong subclass passed.
    """


class ModelRequestInvalid(ModelError):
    """The provider will never accept this request's shape.

    A build mistake wearing an HTTP status. It is separated from
    ``ModelUnavailable`` because the two want opposite handling and the default
    was wrong in the expensive direction: a payload key the SDK does not accept
    used to become a transient outage, so a permanently broken request was
    retried for ever.
    """


class TransportFault(ModelError):
    """How a transport reports a fault, and the only vocabulary it may use.

    Every subclass is caught at the port boundary and turned into one of the
    four outcome values; none is ever raised out of an operation. They exist as
    exceptions rather than return values because a transport is the one layer
    that genuinely has nothing to decide.

    The conventions forbid a provider's own exception type crossing the port
    boundary, so an adapter translates into these and carries no message from
    the provider across: a provider's error text can quote the request that
    caused it (AD-22).
    """


class ModelUnavailable(TransportFault):
    """The provider could not be reached, or failed transiently.

    Connection faults, timeouts, rate limits and server errors. Becomes an
    ``unavailable`` outcome, which is the one of the four a caller may retry.
    """


class ModelRefused(TransportFault):
    """The provider declined the request on its own terms.

    Distinct from ``ModelUnavailable`` for the reason ``SendFailed`` carries
    ``retryable``: the two want opposite handling, and a caller that cannot
    tell them apart will either hammer a provider that is answering correctly
    or drop a call that would have succeeded.
    """


class ModelNotAuthorised(TransportFault):
    """The credentials were rejected.

    Its own class, not a refusal, because the callers diverge on exactly this
    distinction: the crisis caller fails toward *entering* on a content
    refusal, and must not on a key that expired at three in the morning. It
    also bills nothing, which the ``refused`` outcome as a whole cannot promise.
    """


class ModelBatchNotFound(TransportFault):
    """The provider has no such batch, and will not grow one.

    Becomes a distinct answer rather than another not-ready, so a caller can
    stop polling. *Not ready* and *never ready* are different sentences.
    """
