"""The disagreement judgement, as a seam. One method (CAP-7, AD-19).

**What this story does not build, and why the not-building is the design.** A
tension is minted when two entries *disagree where neither is wrong*, which is
a semantic call. CAP-7's success criterion is almost entirely about the *bound*
— what is compared, against what, filtered how, inside which budget — and every
clause of it is testable offline, which is what the rest of this package is.
The judgement is the one part that needs a provider, and with it a cost cap, a
breaker and a tally: machinery that already exists in three copies in this tree
with one bug living in all three, recorded in the manifest as needing
extraction. A fourth copy, written inside the story whose whole subject is *not
spending*, is the bundling this project has got wrong before. So the seam ships
and the judge does not; 9e or the extraction supplies one.

**Narrow by construction, not by intention.** One method, two entries in, a
verdict out. It cannot generate, cannot store, cannot read a clock and cannot
be handed a whole main: everything it receives is two ``Entry`` values built
from ``records.mint_projection``, so what a judge can see is decided at the
store's door rather than by whatever a judge asks for.

**The verdict has three values and they are not the same fact.** ``True`` is a
disagreement, ``False`` is *no*, and ``None`` is *cannot say* — a judge that is
degraded, unsure, or declining. Nothing is minted from any of the three but the
first, which makes it tempting to collapse the last two into one; the reason
they stay apart is that a suite asserting *"nothing was minted"* over both would
pass whether the port answered or was never reached at all, and that is exactly
the shape of assertion this project has already shipped once and had to take
back. ``half.consolidate.mint`` counts them separately, so each has a case that
fails for its own reason.

**A judge that raises costs its couple and nothing else.** ``mint`` catches, and
that is deliberate rather than defensive: a provider that fell over on one pair
must not cost a main the other twenty, and CAP-7's *"the pass completes"* is a
promise about the night rather than about the port.

**Story 9e supplies the implementation, in exactly one module, and the sweep
that used to say *none* now says *that one*.** ``tests/test_minting.py`` swept
``half/consolidate`` for any path to ``half.model``, to a channel, or to the
network; the model half of that sweep is now the rule two other packages already
hold — ``half/consolidate/judge.py`` may name the model and no other file here
may, what it reaches under ``half.model`` may itself reach nothing but the port,
and the channel and the network stay closed to the whole package. Everything
this module says about the judgement is unchanged by that: it is still one
method, still three values, still unable to generate, store, read a clock or be
handed a whole main.

The deterministic judges the suite runs the *minting* against are still doubles
in the tests, where a double belongs. What ``half/consolidate/judge.py`` adds is
the thing a double cannot be: labels, instructions, a bound, a breaker and a
tally, none of which a test can assert about an object it wrote itself.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from half.consolidate.candidates import Entry


@runtime_checkable
class Disagreement(Protocol):
    """Whether two entries disagree where neither of them is wrong.

    ``runtime_checkable`` so a composition root can refuse a holder that does
    not answer this question, rather than discovering it at three in the
    morning. Structural checking only sees the *name*, which is why the door is
    asserted by ``tests/test_minting.py`` as well.
    """

    async def disagree(self, one: Entry, other: Entry) -> bool | None:
        """``True`` to mint, ``False`` for no, ``None`` for cannot say.

        The two arguments are two entries and **their order carries no
        meaning**. A judge that answered differently depending on which arrived
        first would be ranking the sides, which is the one thing a tension may
        never record — ``tests/test_minting.py`` asserts the mint is unchanged
        under swapping them.

        ``async`` because the implementation this seam exists for is a model
        call and everything above it already is. Nothing in this story awaits
        anything real.
        """
        ...


__all__ = ["Disagreement"]
