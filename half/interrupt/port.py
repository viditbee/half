"""The urgency judgement, as a seam. One method, three values (CAP-10, AD-19).

**What this story does not build, and why the not-building is the design.** An
interruption is legitimate only when *waiting would destroy an option*, which
is a judgement about a horizon — and nothing Half records carries one. A loop
carries a timescale and a last movement; a belief carries a claim and its
support; a tension carries two entries and a state. There is no field anywhere
that says *this closes on Friday*, so a detector here would have to either
change a record shape or derive a horizon out of prose, and bundling either
with the rule that governs restraint is the bundling this project has already
got wrong.

CAP-10's sentence is a promise of restraint, and the valuable half of it is the
*only*: the four refusals that run before anything is judged, and the bound
that stops a second interruption. Every one of those is testable offline, which
is what ``half.interrupt.gate`` is. The judgement is the one part that needs a
provider — and with it a cost cap, a breaker and a tally, machinery that
already exists in four copies in this tree. A fifth, written inside the story
whose whole subject is *not speaking*, would be the same mistake in a new
package. So the seam ships and the judge does not.

**Narrow by construction, not by intention.** One method, one ``Option`` in, a
verdict out. It cannot generate, cannot store, cannot read a clock, cannot
send, and cannot be handed a whole main: everything it receives is built by
``half.interrupt.gate`` from one live wanting and the claims that sit on it, so
what a judge can see is decided at this door rather than by whatever a judge
asks for. In particular it is never told *which* main it is judging for, so
nothing it returns can depend on one.

**The verdict has three values and they are not the same fact.** ``True`` is
*closing*, ``False`` is *not closing*, and ``None`` is *cannot say* — a judge
that is degraded, unsure, over its cap or declining. Only the first may
interrupt, which makes it tempting to collapse the last two into one; the
reason they stay apart is the one ``half.consolidate.port`` gives, and it
applies harder here because this build wires no judge at all: a suite asserting
*"nothing was sent"* over both would pass whether the port answered, refused,
or was never reached — and *never reached* is exactly the state the shipped
composition is in. ``half.interrupt.gate`` counts them separately, so each has
a case that fails for its own reason.

**A judge that raises, or that is slow, costs its option and nothing else.**
The gate catches and bounds, and that is deliberate rather than defensive: an
interruption is a thing Half may decline to send for any reason at all, so
every failure here has a correct outcome and it is silence (AD-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["Option", "Urgency"]


@dataclass(frozen=True, slots=True)
class Option:
    """One wanting as the urgency judge sees it, and no more of one than that.

    Built by ``half.interrupt.gate.option_for`` out of the folded loop table
    and the beliefs that name that loop — never out of the fold, never out of a
    ``State``, and never out of anything carrying a main's id. A judge holding
    one of these can say something about *this wanting*; it has no route to the
    ledger it came from, to the platform, or to the main.

    Every field but ``loop`` is optional and tolerant, because this is on the
    read path and the read path is tolerant: one belief whose ``claim`` is a
    number must cost that belief its place in the question, never the main
    their pass.

    **There is deliberately no horizon field here.** Adding one is the story
    that supplies a judge, and it is an Ask-First change to a record shape
    (CAP-10's boundaries). What this type says today is exactly what Half
    knows today, which is why no judge can currently answer ``True`` honestly —
    and why none is wired.
    """

    #: The wanting's own id. The only required field, and the only one the
    #: gate uses to say *which* option an answer was about.
    loop: str
    #: The natural period on which this wanting moves — one of
    #: ``half.loops.timescale.Timescale``. ``None`` when the loop carries none,
    #: which the gate refuses long before this type is built.
    timescale: str | None = None
    #: When the wanting last moved, as the log recorded it. ``None`` when it
    #: never has, or when the record cannot be read.
    last_movement: str | None = None
    #: What the main believes that sits on this wanting, claim text only, in
    #: the order the gate's own total order produced. No ids, no licenses, no
    #: support sets: an id would let a judge name a record, and a license would
    #: invite it to have an opinion about one.
    claims: tuple[str, ...] = ()


@runtime_checkable
class Urgency(Protocol):
    """Whether waiting would destroy this option.

    ``runtime_checkable`` so a composition root can refuse a holder that does
    not answer this question, rather than discovering it in front of a main.
    Structural checking only sees the *name*, which is why the door is asserted
    by ``tests/test_interrupt.py`` as well.
    """

    async def closing(self, option: Option) -> bool | None:
        """``True`` to interrupt, ``False`` for no, ``None`` for cannot say.

        **Absent, unwired, slow, failing and unsure all mean no.** Only an
        explicit ``True`` may interrupt, and the gate treats every other
        outcome — including a raise and a timeout — as silence. That asymmetry
        is the whole of CAP-10's *only*.

        ``async`` because the implementation this seam exists for is a model
        call and everything above it already is. Nothing in this story awaits
        anything real.
        """
        ...
