"""Stakes: whether a question is worth its interruption (CAP-4, constitution).

*"Ask only when acting on a wrong belief would cost more than the
interruption. Below that bar, hold the claim as provisional."* That sentence is
a comparison between two costs, and this module is the comparison.

**Both sides are measured in days, and neither number was chosen.** That is the
whole design, and it is lifted in shape from ``half.surface.choose.touchable``,
which derives the nagging bound from each loop's *own* period rather than from
a cadence somebody picked. The same discipline applies here for the same
reason: a threshold like *"ask when independence is below three"* or *"ask
about anything older than a fortnight"* is a number that is right for one main
and wrong for every other, and its wrongness is silent.

* **What being wrong costs** is the period of the wanting the belief sits on.
  The open-loop ledger is the ranking function for everything Half does, so a
  belief on a live loop is one Half will keep acting on — ranking, timing,
  softening — until that loop moves. Being wrong about it is therefore felt for
  one of that loop's own periods: a day for a routine, a year for farmland.
* **What the interruption costs** is one of the main's days. Half gets at most
  one unprompted message a day (CAP-8), and a question attached to a
  conversation is over when that conversation is; a day is the shortest period
  the open-loop vocabulary names, and it is read out of that same table rather
  than typed here, so the two sides of the comparison are one unit from one
  source.

**Strictly greater, and the boundary is the ledger's own.** A question is worth
asking when the cost outlasts the interruption; at exactly one day it is not.
That matches ``timescale.silence``'s ``days > period`` and ``touchable``'s
bound rather than inventing a second convention for the same comparison, and it
errs toward the quiet side — which is the correct direction, because an
unasked question leaves a claim provisional and an unwanted one spends trust.

**Everything that cannot be measured is below the bar**, and never above it.
A belief on no wanting, on a finished one, or on one with no readable period
has no cost this module can show to exceed the interruption, so it is not
asked and the claim is held as provisional — which is exactly what the
constitution says to do below the bar. There is no branch here that borrows a
period from another loop, supplies a default, or treats *"we could not tell"*
as a reason to interrupt somebody.

**Nothing here reads the balance.** Stakes decide whether a question is worth
asking *at all*; the favour decides whether it may be asked *now*. Keeping them
in separate modules is what makes the order in ``half.trust.unasked`` hard to
reverse: this function cannot consult a balance, because it is not given one.

Pure and clockless. It reads a belief record and the folded loop table and
returns a value (AD-30).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from half.loops.ledger import LOOP, Loop
from half.loops.states import LIVE_STATES
from half.loops.timescale import PERIOD_DAYS, Timescale, period_days

__all__ = [
    "BELOW_THE_BAR", "FINISHED", "INTERRUPTION_DAYS", "NO_PERIOD",
    "NO_SUBJECT", "NO_WANTING", "REASONS", "Stakes", "stakes",
]

#: What one interruption costs the main, in days.
#:
#: **Read from the open-loop vocabulary, not typed here.** It is
#: ``PERIOD_DAYS[Timescale.DAYS]`` — the shortest period the ledger has a name
#: for — so that the two sides of this module's comparison are the same unit
#: from the same table. Writing ``1`` would be a number nobody could later
#: argue with; taking it from the table says what it means: a question asked
#: inside a conversation is felt for the main's day and is then over, which is
#: also the granularity CAP-8 gives Half for speaking first at all.
INTERRUPTION_DAYS: Final[int] = PERIOD_DAYS[Timescale.DAYS]

#: The question names something that is not a belief this build holds. Nothing
#: to be wrong about, so nothing to weigh.
NO_SUBJECT: Final[str] = "no-subject"
#: The belief sits on no wanting, or on one the ledger does not hold. There is
#: no period over which being wrong about it is felt, so the cost cannot be
#: shown to exceed one interruption. Held as provisional; not asked.
NO_WANTING: Final[str] = "no-wanting"
#: The wanting is `achieved`, `abandoned-but-unadmitted`, or in a state this
#: build does not recognise. Acting wrongly on a wanting that has stopped
#: running costs nothing that is still running — and a later build's state is
#: not something to interrupt somebody over.
FINISHED: Final[str] = "finished"
#: The wanting has no timescale, or one this build cannot read. The cost has no
#: unit, and nothing here borrows one from a loop it is nothing like.
NO_PERIOD: Final[str] = "no-period"
#: The cost was measured and does not outlast the interruption. **The ordinary
#: refusal**, and the one the constitution names: hold the claim as provisional.
BELOW_THE_BAR: Final[str] = "below-the-bar"

#: The closed set. Every value this module puts in a ``Stakes`` is one of
#: these, so a caller logging a refusal logs a constant and never a message —
#: an exception message quotes the value that caused it, and here that is a
#: record out of a main's own ledger (AD-22).
REASONS: Final[frozenset[str]] = frozenset(
    {NO_SUBJECT, NO_WANTING, FINISHED, NO_PERIOD, BELOW_THE_BAR}
)


@dataclass(frozen=True, slots=True)
class Stakes:
    """What being wrong about one belief would cost, against one interruption.

    A value. It decides nothing, writes nothing, and is recomputed from the
    fold every time it is wanted — for the reason ``Silence`` and ``Bound`` are:
    a stored *"worth asking"* flag is a fact about the moment it was written,
    and keeping it current means writing on a read (AD-4, AD-30).

    ``reason`` is set exactly when ``worth_asking`` is false, and is one of
    ``REASONS``. ``cost_days`` is the wanting's own period and is ``None``
    whenever there was none to read — never a borrowed default.
    """

    worth_asking: bool = False
    #: Why not. One of ``REASONS``; ``None`` only when ``worth_asking``.
    reason: str | None = None
    #: The period over which being wrong is felt: the wanting's own, in days.
    cost_days: int | None = None
    #: What the interruption costs, for comparison. Always the same number, and
    #: carried on the value so a caller can show the comparison rather than
    #: restate one half of it.
    interruption_days: int = INTERRUPTION_DAYS

    @property
    def worth_it(self) -> bool:
        """The comparison itself, so nothing has to re-derive it.

        The predicate the runtime **and** the tests read, rather than a
        ``cost > interruption`` each of them writes out. Two spellings of one
        comparison is how the boundary ends up on different sides in the two
        places that check it — which is precisely the defect review found in
        story 8's threshold.
        """
        return self.cost_days is not None and self.cost_days > self.interruption_days


def stakes(
    belief: Mapping[str, Any] | None, *, loops: Mapping[str, Loop] | None
) -> Stakes:
    """Whether acting wrongly on ``belief`` would cost more than asking.

    Pure and total: the same belief and the same loop table give the same
    answer for ever, and nothing here raises — a caller on a turn's own path
    must not lose the main's reply over a malformed loop entry, and *"we could
    not tell"* has a correct answer here, which is not to ask.

    ``loops`` is ``half.loops.ledger.read`` over the folded loop table — the
    same values ``half.surface.choose`` measures its bound against, so the two
    rules that decide whether Half opens its mouth read one ledger.

    Refused, in this order, where the answer would otherwise have to be
    guessed:

    * nothing that is a belief record — there is nothing to be wrong about;
    * a belief on no wanting, or on one the ledger does not hold;
    * a wanting that has stopped running, or whose state this build does not
      recognise. This is ``ledger.silent``'s and ``touchable``'s own filter,
      asked here for the same reason: finished is not silent, and answered is
      not unasked;
    * a wanting with no period, or one this build cannot read.

    And then the comparison, which is the only place a ``True`` is produced.
    """
    if not isinstance(belief, Mapping):
        return Stakes(reason=NO_SUBJECT)

    slug = belief.get(LOOP)
    if not isinstance(slug, str) or not slug.strip():
        return Stakes(reason=NO_WANTING)
    held = (loops or {}).get(slug.strip())
    if not isinstance(held, Loop):
        # The belief names a wanting the ledger has no transition for. It is on
        # a loop; the ledger has simply never heard from it, so there is no
        # period to measure against and nothing here invents one.
        return Stakes(reason=NO_WANTING)

    if held.state not in LIVE_STATES:
        return Stakes(reason=FINISHED)

    period = period_days(held.timescale)
    if period is None:
        return Stakes(reason=NO_PERIOD)

    weighed = Stakes(cost_days=period)
    if not weighed.worth_it:
        # The ordinary refusal: a routine that moves in days is not worth a
        # day's interruption to be sure about. The claim stays provisional.
        return Stakes(reason=BELOW_THE_BAR, cost_days=period)
    return Stakes(worth_asking=True, cost_days=period)
