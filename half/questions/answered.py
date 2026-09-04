"""Was the question answered? Folded from the log, never stored (AD-3, AD-30).

**This module recognizes responsiveness, not answering.** State it plainly
because the difference is real and it is the price of the whole design: an
``asked`` record followed by an inbound message from the main reads here as
engagement, whatever that message was about. A main who replies about something
else entirely reads as having answered. Interpreting the reply's *content* is
claim derivation, deferred with the model port since story 3, and buying the
stronger version means buying that.

**But an inbound message does not retire a question on its own**, and the first
build let it: ``responsive`` matched any stated-ledger belief, ``history``
marked *every* outstanding question answered on the first one, and there was no
time bound at all. For a main who messages daily that is *"never ask twice,
whatever happened"* — precisely what this module's own docstring says story 5b
was right to refuse — arrived through the back door. Two conditions now bound it,
and both are read off the log:

* **One reply retires one question**, and it is the most recently put one. Half
  holds at most one or two open questions by construction (CAP-4 delivers one per
  send, and the favour rule pays for one at a time), which is what the spec's
  *"reply attribution at the edges"* note leans on. Retiring the whole set on one
  message is the thing that could never be right.
* **A reply retires a question only inside the interruption that question cost.**
  The window is ``half.trust.stakes.INTERRUPTION_DAYS`` — imported, never typed —
  which is ``PERIOD_DAYS[Timescale.DAYS]``: *"a question asked inside a
  conversation is felt for the main's day and is then over"*, which is the same
  sentence that priced the interruption in the first place. A message a week
  later is a new conversation, not an answer, and the question falls back to
  being *ignored* — where the wanting's own period decides when it may be put
  again.

**Known limit, stated rather than hidden.** An ``asked`` record is written
immediately *before* the reply carrying it is sent (5b's spend contract, and the
one ordering that stops two runs both spending one favour). If that send then
fails, the main never saw the question, and an unrelated message from them inside
the same day still retires it. Closing that needs the log to record whether a
message was *delivered*, which is a new field on a closed op and therefore
Ask-First; what is here instead is the bound, which turns "silenced for ever by
any later message" into "silenced for one day by a message sent that day". The
failure is logged where it happens, without content.

The deterministic bound is the honest one, and it errs toward asking **less** —
which is the correct direction for a rule whose failure mode is a nag.

**Why this is derived at all, when story 5b said it could not be.** 5b declined
a sixth gate against re-asking on exactly the right reasoning: the log records
that a question was *put* and never that it was *answered*, so a gate on the
``asked`` records alone would not mean *"do not nag"* — it would mean *"never
ask twice, whatever happened"*, permanently silencing a question the main merely
did not reply to. That reasoning stands; its conclusion turns out to be
avoidable, because ``half.actor.runtime`` already writes every inbound message
as a stated-ledger belief. *Responsiveness* is therefore in the log with a
timestamp, and no new op, no answered flag and no counter is needed.

**Nothing is recorded and nothing materializes.** There is no ``answered`` field
on ``State``, no asked-count anywhere, and no place for one: ``history`` is a
pure function of a sequence of log records, exactly as ``half.trust.balance`` is,
and for the same reason. A stored flag would be a fact about the moment it was
written; worse, it would replay perfectly and therefore be only ever *wrong*,
never *inconsistent*, so no round-trip assertion in the suite would see it
(AD-4, AD-30).

**The bound on re-asking is one of the wanting's own periods**, and it is a
number this module is *given* rather than one it picks. The caller reads it off
the ``Stakes`` value the gates already computed — which is
``half.loops.timescale.PERIOD_DAYS`` subscripted by the loop's own timescale, the
same table ``timescale.silence`` and ``choose.touchable`` read. There is no
default here, no fallback and no borrowed cadence: gbrain's one global fourteen
days nags a workout routine and never once reaches a farmland loop, which is why
story 10 refused it for ``touchable``.

**The boundary is strict, and it is the ledger's own.** A question may be put
again when *more* than one of its wanting's periods has passed; at exactly one
period it may not. That is ``Silence.silent = days > period`` and ``touchable``'s
bound rather than a second convention for the same comparison, and it errs
toward the quiet side.

Pure and clockless: ``now`` is the stamp the caller was handed, the arithmetic is
``half.civil``'s, and the same log with the same instant gives the same answer
for ever.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Final

from half.civil import DAY
from half.loops.timescale import moment
from half.trust.stakes import INTERRUPTION_DAYS
from half.store.ops import Op
from half.store.records import LEDGER, QUESTION, STATED, Record, derived_claim

__all__ = [
    "ANSWERED", "ANSWERS_WITHIN_DAYS", "Answer", "NEVER_ASKED", "NO_PERIOD",
    "REASONS", "Reask", "TOO_SOON", "UNREADABLE_ASK", "UNREADABLE_NOW",
    "history", "reaskable", "responsive", "spend_of",
]

#: How long after a question is put a message from the main still reads as an
#: answer to it, in days.
#:
#: **Derived, not chosen.** It is ``half.trust.stakes.INTERRUPTION_DAYS``,
#: imported rather than typed, and that import is what fixes its meaning: the
#: interruption a question costs is one of the main's days, because *"a question
#: attached to a conversation is over when that conversation is"*. A question is
#: therefore live for exactly as long as it was priced at, and one sentence
#: answers both.
#:
#: The alternative was no bound at all, which is what the first build shipped:
#: any later message closed every open question for ever, so a main who writes
#: daily was never asked twice about anything. That is not a threshold somebody
#: picked badly — it is the absence of one.
ANSWERS_WITHIN_DAYS: Final[int] = INTERRUPTION_DAYS

#: The question was put and the main has said something since. Never put again.
#: **Responsiveness, not answering** — see the module docstring.
ANSWERED: Final[str] = "answered"
#: The question was put, nothing came back, and less than one of its wanting's
#: own periods has passed. Held; the ordinary refusal, and the one the nag rule
#: exists for.
TOO_SOON: Final[str] = "too-soon"
#: The wanting has no period this build can read, so *"one of its own periods"*
#: has no value. A question already put is not put again — there is no cadence
#: to hold it to, and nothing here borrows one from a wanting it is nothing
#: like. It errs toward asking less, which is this module's one direction.
NO_PERIOD: Final[str] = "no-period"
#: The caller's own stamp is not an instant this build can read. Reported apart
#: from the log's, exactly as ``timescale.silence`` and ``touchable`` do,
#: because the fix is a different one.
UNREADABLE_NOW: Final[str] = "unreadable-now"
#: The ``asked`` record's own stamp cannot be read, so the interval cannot be
#: measured. **Not a refusal** — see ``reaskable``.
UNREADABLE_ASK: Final[str] = "unreadable-ask"
#: Half has never put this question. Not a refusal either; it is carried so that
#: a caller can tell *"never asked"* from *"asked and long enough ago"*, which a
#: bare ``True`` cannot.
NEVER_ASKED: Final[str] = "never-asked"

#: The closed set. Every value this module puts in a ``Reask`` is one of these,
#: so a caller logging a reason logs a constant and never a message — an
#: exception message quotes the value that caused it, and here that is a record
#: out of a main's own ledger (AD-22).
REASONS: Final[frozenset[str]] = frozenset(
    {ANSWERED, TOO_SOON, NO_PERIOD, UNREADABLE_NOW, UNREADABLE_ASK, NEVER_ASKED}
)


@dataclass(frozen=True, slots=True)
class Answer:
    """What the log says happened to one question. Recomputed, never stored.

    A value. It decides nothing and writes nothing, for the reason ``Balance``,
    ``Silence`` and ``Bound`` are recomputed: a stored *"answered"* flag is a
    fact about the moment it was written, and keeping it current means writing
    on a read.

    ``asked_at`` is the stamp of the **latest** ``asked`` record for this
    question, because that is the one the next interval is measured from. A
    question put twice is bounded from the second putting, not the first.
    """

    #: Whether Half has ever put this question.
    asked: bool = False
    #: Whether the main said anything at all after it was last put.
    #: **Responsiveness, not answering.**
    answered: bool = False
    #: When it was last put. ``None`` exactly when ``asked`` is false.
    asked_at: str | None = None
    #: When the main next said something. ``None`` unless ``answered``.
    replied_at: str | None = None


@dataclass(frozen=True, slots=True)
class Reask:
    """Whether one question may be put again, and why not.

    A value, recomputed from the log, the wanting's period and an injected
    ``now``. ``may_ask`` is true with a ``reason`` set in exactly two cases —
    ``NEVER_ASKED``, where there is no interval because there was no first ask,
    and ``UNREADABLE_ASK``, where the measure is gone and the question is
    treated as never put. ``degraded`` says which, so a caller can count it
    rather than discover it a year later.
    """

    may_ask: bool = False
    #: Set whenever the bound has something to report, which is every case
    #: except *"put once, ignored, and long enough ago"*. One of ``REASONS``.
    reason: str | None = None
    #: True when ``may_ask`` was reached without a measurement.
    degraded: bool = False
    #: The wanting's own period in days — never a borrowed default.
    period_days: int | None = None
    #: Days since the question was last put. ``None`` when it never was, or when
    #: the interval could not be measured.
    since_days: float | None = None


def spend_of(record: Record | None) -> str:
    """The question id an ``asked`` record paid for, or ``""``. Never raises.

    An erased spend answers ``""``: ``BeliefLog.expunge_bodies`` removes the
    body and leaves the op, so the record still says *a question was asked* —
    which is why ``half.trust.balance.spent`` still counts it against the
    balance — and no longer says *which*. It therefore stops bounding a re-ask,
    and that is stated rather than hidden: the currency still charges for it, so
    what is lost is the period, not the payment.
    """
    if not isinstance(record, Record) or record.op is not Op.ASKED:
        return ""
    data = record.data
    if not isinstance(data, Mapping):
        return ""
    found = data.get(QUESTION)
    return found.strip() if isinstance(found, str) else ""


def responsive(record: Record | None) -> bool:
    """Whether ``record`` is the main saying something. Never raises.

    One predicate, read by the runtime **and** by the tests, rather than a shape
    each of them checks separately — the same discipline
    ``half.trust.balance.delivered`` follows on the earning side.

    The mark is the stated ledger. ``half.actor.runtime`` writes every inbound
    message as an ``Op.ASSERT`` on it (``ledger="stated"``), which is the same
    fact ``half.channel.window`` reads to rebuild a platform's send window — one
    spelling, imported from the module that owns record shapes.

    Read strictly, and an erased body therefore answers ``False``: a tombstone
    removes the ledger field, so nothing about the record is readable as the
    main having spoken. That direction lets a question be put again after its
    wanting's own period rather than never, which is the bounded mistake; the
    opposite reading would silence a question for ever on an erasure.

    **A claim Half derived is not the main speaking**, which is story 15a's one
    change here and it is a correction rather than an addition. Since that story
    a message that passes CAP-5's admission gates produces a *second* record on
    the same turn — an ``assert`` on the same stated ledger, carrying the same
    words — and without this line one reply would retire two questions: the
    message, and then the claim derived from it. That is precisely the *"one
    reply retires one question"* rule this module's docstring says the first
    build got wrong, arriving back through a door nobody had opened yet.

    Only a record that says in as many words that it is Half's own conclusion is
    excluded (``records.derived_claim``). Every belief in every log written
    before that story is unmarked and still reads as the main having spoken,
    which is what those logs already meant.
    """
    if not isinstance(record, Record) or record.op is not Op.ASSERT:
        return False
    data = record.data
    if not isinstance(data, Mapping) or data.get(LEDGER) != STATED:
        return False
    return not derived_claim(data)


def history(records: Iterable[Record] | None) -> dict[str, Answer]:
    """What the log says about every question Half has put. Pure and total.

    ``records`` is the belief log — ``Store.log`` iterates it — and never the
    derived view, for the reason ``half.trust.balance`` says so: the log is the
    only authority (AD-3) and it is the only one of the two that cannot be
    behind an append. There is no derived copy of this anywhere, because there
    is no copy.

    **Folded in log order**, which is append order and is what replay
    reproduces, rather than by comparing stamps: two records the same second
    apart have an order in the log and may have none in their stamps, and a fold
    that sorted would be a fold whose answer depended on a tie-break. Stamps are
    read only to *measure* the window, never to order anything.

    **One reply retires one question, and only inside its own window.** The
    outstanding questions are kept in the order they were put, and a message
    from the main is offered to the most recent of them — the only one it could
    plausibly be about — and retires it only if it arrived within
    ``ANSWERS_WITHIN_DAYS``. A message outside every window retires nothing and
    leaves each question *ignored*, which is a different state with a different
    consequence: the wanting's own period decides when it may be put again.

    A later ``asked`` for a question that was already answered starts the
    question over — asked again, unanswered again — because that is what the log
    says happened. Nothing here decides whether that ask should have been made;
    ``reaskable`` is where that question is asked, before the fact.

    One pass, and linear in the log: the outstanding list is a stack, so a log
    with a thousand asks costs a thousand steps rather than a million.

    Total, and never raises: a record this build cannot make sense of
    contributes nothing rather than aborting, because the caller is on a turn's
    own path and there is a correct outcome for *"we could not tell"*.
    """
    found: dict[str, Answer] = {}
    #: The questions still outstanding, oldest first. A question re-asked moves
    #: to the end, because the interval that matters is from the *latest* time
    #: it was put.
    waiting: list[str] = []
    for record in records or ():
        if not isinstance(record, Record):
            continue
        spent = spend_of(record)
        if spent:
            found[spent] = Answer(asked=True, asked_at=record.t)
            if spent in waiting:
                waiting.remove(spent)
            waiting.append(spent)
            continue
        if responsive(record) and waiting:
            newest = waiting[-1]
            if _within_the_window(found[newest].asked_at, record.t):
                found[newest] = replace(
                    found[newest], answered=True, replied_at=record.t
                )
                waiting.pop()
    return found


def _within_the_window(asked_at: object, replied_at: object) -> bool:
    """Whether a message at ``replied_at`` still reads as an answer. Pure.

    Both stamps come out of the log and either may be unreadable — the log
    preserves what this build cannot parse. An unmeasurable interval answers
    ``False``, which leaves the question *ignored* rather than answered: the
    direction that keeps a question askable is the one an unreadable record must
    resolve in here, because the alternative is silencing an uncertainty for ever
    on a stamp nobody could read.

    Not clamped and not absolute: a reply stamped *before* the ask is not an
    answer to it, and reading it as one would let a skewed clock retire a
    question the main never saw.
    """
    put = moment(asked_at)
    said = moment(replied_at)
    if put is None or said is None:
        return False
    return 0.0 <= (said - put) / DAY <= ANSWERS_WITHIN_DAYS


def reaskable(
    answer: Answer | None, *, period_days: int | None, now: object
) -> Reask:
    """Whether this question may be put again at ``now``. Pure and total.

    The rule, and it is three sentences:

    * a question never put may be put;
    * a question the main **responded to** is never put again;
    * a question the main ignored may be put again once **more than one of its
      wanting's own periods** has passed, and not before.

    ``period_days`` is the wanting's own period, handed in rather than looked up
    — the caller has it already, on the ``Stakes`` value the gates computed, and
    a second derivation here would be a second place for the two to disagree
    about one loop. ``None`` means the period could not be read: a question
    already put is then held, because *"one of its own periods"* has no value and
    nothing here substitutes somebody else's.

    **The unreadable ask is treated as no ask**, and that is ``touchable``'s own
    correction rather than a fresh decision. Refusing would be the safe-looking
    direction, and it weighs one extra question against *permanent* silence on
    one uncertainty: the record is replaced only by a later ask, a later ask
    happens only when the question is chosen, and refusing here is what would
    stop it being chosen. The cost is at most one extra question, after which a
    readable record exists — and the favour still has to pay for it.
    """
    held = answer if isinstance(answer, Answer) else Answer()
    period = period_days if isinstance(period_days, int) and not isinstance(
        period_days, bool
    ) else None

    if not held.asked:
        return Reask(may_ask=True, reason=NEVER_ASKED, period_days=period)
    if held.answered:
        return Reask(reason=ANSWERED, period_days=period)
    if period is None:
        return Reask(reason=NO_PERIOD)

    at = moment(now)
    if at is None:
        # The caller's own stamp, not the log's — reported separately because
        # the fix is a different one, exactly as ``timescale.silence`` does.
        return Reask(reason=UNREADABLE_NOW, period_days=period)
    put = moment(held.asked_at)
    if put is None:
        return Reask(
            may_ask=True, reason=UNREADABLE_ASK, degraded=True, period_days=period
        )

    # Clamped, so a question stamped in the future cannot buy itself a negative
    # age and be asked again immediately. The same clamp ``silence`` and
    # ``touchable`` apply, for the same reason.
    days = max(0.0, (at - put) / DAY)
    if days > period:
        return Reask(may_ask=True, period_days=period, since_days=days)
    return Reask(reason=TOO_SOON, period_days=period, since_days=days)
