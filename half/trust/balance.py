"""The trust balance: delivered favours minus questions asked (CAP-4, AD-30).

**Computed from the log, never stored as a counter — and this module is where
that is true rather than promised.** There is no field here to increment, no
integer on ``State`` to decrement, and no path by which a number reaches the
derived view: ``balance`` is a pure function of a sequence of log records, and
the only way to get one is to hand it the log.

The tempting implementation is a pair of counters, bumped on delivery and
dropped on an ask. Story 4 refused it for salience and story 9c refused it for
decay, both under AD-30, and the failure is the same one at three different
altitudes: materialized state that is a function of *which code paths ran*
rather than of the log. Here it has a sharper edge than in either of those,
because the derived view is not merely a cache — ``Store.append`` writes the
log line and *then* rebuilds, so a crash between the two leaves a view behind
the log. A balance read out of that view is a favour spent twice, and it would
survive every round-trip assertion in the suite, because a stored counter
replays perfectly. It is only *wrong*; it is never *inconsistent*.

**Two record kinds, and only one of them is new.**

* **Earning** is a ``touch`` that marked one of the main's days and says a
  message was sent — story 10's record, read rather than re-derived. That story
  split *raised* from *sent* precisely so that a raise which marks no day
  cannot be mistaken for a message; this module reads the delivered half and
  invents no second fact about it. A favour is **delivered, not endorsed**:
  whether it landed well is AD-21's sampled question and is not asked here.
* **Spending** is an ``asked`` record — the op story 5b adds, because the
  spend had no record and a currency with only an earning half is not one.

**Every unreadable record resolves in the direction of asking less**, which is
the single rule behind both predicates below and the reason they are not
symmetric. A tombstoned ``touch`` has lost its body, so it is not readable as
delivered and does not earn. A tombstoned ``asked`` record has lost its body
too, and still spends — the op and the record's position are enough to say a
question was asked, and treating it as un-asked would hand Half back a favour
it had already used. Both readings lower the balance. That is the same
direction the ladder resolves every uncertainty in, and it is the direction in
which a mistake costs a question rather than the main's trust.

**An unspent balance is a defect, and that is why the number is a value rather
than a boolean.** ``Balance`` carries what it earned, what it spent and what is
left, so *"Half has been given eleven favours' worth of permission and used
none of it"* is something an operator reads off the object instead of
inferring. There is deliberately no threshold here for *how much* unspent is
too much: any number would be one somebody chose, and the story lists changing
the rule as an Ask-First.

Pure and clockless. Nothing here reads a clock, a model, the network or the
derived view; the same log gives the same balance for ever, which is the whole
of the acceptance criterion that computing it twice is identical (AD-30).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from half.store.ops import Op
from half.store.records import SENT, Record
from half.surface.touch import marks_day

__all__ = ["Balance", "balance", "delivered", "spent", "tombstoned"]


@dataclass(frozen=True, slots=True)
class Balance:
    """What the log says this main's trust currency stands at.

    A value. It decides nothing, writes nothing, and is recomputed from the log
    every time it is wanted — for the reason ``half.loops.timescale.Silence``
    and ``half.surface.choose.Bound`` are recomputed: a stored balance is a
    fact about the moment it was written, and keeping it current means writing
    on a read.
    """

    #: Unprompted messages that reached the main. Never negative.
    earned: int = 0
    #: Clarifying questions Half has asked. Never negative.
    spent: int = 0

    @property
    def unspent(self) -> int:
        """Favours given and not yet used. **The defect, made visible.**

        Clamped at zero so that an overdrawn log cannot present as spendable
        credit. Whether it *is* overdrawn is a separate question with its own
        property, because clamping a number and hiding the fact that it was
        clamped is how an anomaly becomes invisible.
        """
        return max(0, self.earned - self.spent)

    @property
    def spendable(self) -> bool:
        """Whether a question may be paid for at all.

        The favour rule as a predicate — *"Half never asks without having just
        given"* — read by the runtime **and** by the tests, rather than a
        comparison each of them writes out separately. A gate spelled as
        ``balance.unspent > 0`` in one place and ``earned > spent`` in another
        is two rules that agree until an overdrawn log arrives.
        """
        return self.unspent > 0

    @property
    def overdrawn(self) -> bool:
        """More questions asked than favours delivered.

        Not reachable through ``ActorRegistry.note_ask``, which refuses a spend
        it cannot pay for under the main's own mutex. It is reachable from a
        hand-edited log, from a build that wrote spends without this gate, and
        from an erasure that took a delivered favour out from under a question
        already asked. Surfaced rather than clamped away, because a currency
        quietly running a deficit is exactly the state nobody would go looking
        for.
        """
        return self.spent > self.earned


def tombstoned(record: Record) -> bool:
    """Whether this record's body has been erased.

    The same test the fold makes, spelled once here so the two cannot drift:
    an erasure removes the body and leaves the op, the id and the stamp.
    """
    return isinstance(record.data, Mapping) and record.data.get("tombstone") is True


def delivered(record: Record) -> bool:
    """Whether ``record`` is a favour that reached the main. Never raises.

    **A favour is a message that was sent, not one that was composed.** The
    predicate is story 10's own two facts, read through story 10's own reader:
    the record marks one of the main's days (``marks_day``) *and* says a
    message reached them (``sent``). A raise that marks no day is CAP-10's
    interrupt and earns nothing; a repair marker carries ``sent=False`` and
    earns nothing; a day nothing was sent on earns nothing.

    ``sent`` is read strictly — an explicit ``True`` and nothing else — for the
    reason ``ladder.known_to_main`` is read strictly: this field *grants* a
    permission, so anything uninterpretable must not be read as granting it.

    A tombstoned touch answers ``False``: its body is gone, so nothing about it
    is readable as delivered. That lowers the balance, which is the direction
    every uncertainty here resolves in.
    """
    if record.op is not Op.TOUCH or tombstoned(record):
        return False
    fields: Mapping[str, Any] = record.data
    return marks_day(fields) and fields.get(SENT) is True


def spent(record: Record) -> bool:
    """Whether ``record`` is a question Half asked. Never raises.

    The op alone, and a tombstone does **not** undo it. A question that was
    asked was asked: the main heard it, and the body carries only two ids, so
    erasing it removes a trace and not an event. Reading an erased spend as
    un-asked would hand back a favour Half had already used, which is the one
    direction this module does not resolve in.
    """
    return record.op is Op.ASKED


def balance(records: Iterable[Record] | None) -> Balance:
    """This main's trust balance, folded out of ``records``. Pure and total.

    ``records`` is the belief log — ``Store.log`` iterates it — and never the
    derived view. That is not a preference: the log is the only authority
    (AD-3), and it is the only one of the two that cannot be behind an append.

    Total, and never raises. A record this build cannot make sense of is
    counted as neither an earning nor a spend rather than aborting: the caller
    is on a turn's own path, the safe answer to *"how much credit is there"* is
    *less*, and there is a correct outcome for not knowing — ask nothing.

    One pass, no clock, no state. Two calls over one log give one answer, and
    a rebuilt store gives the same answer as a fresh one because neither of
    them is consulted.
    """
    earned = 0
    questions = 0
    for record in records or ():
        if not isinstance(record, Record):
            continue
        if delivered(record):
            earned += 1
        elif spent(record):
            questions += 1
    return Balance(earned=earned, spent=questions)
