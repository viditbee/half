"""The interruption: the rule that governs speaking out of turn (CAP-10).

CAP-10 promises that *"an unprompted interruption occurs only when waiting
would destroy an option."* Half has exactly one unprompted surface — the
morning — and it fires on a **schedule**. Nothing in the product could say
*this cannot wait until tomorrow*, and, more to the point, nothing could stop
it: the rule that would govern an interruption did not exist, so the first
surface that wanted one would have invented its own.

Two modules, and the split is the story:

* ``port`` — the urgency judgement as a seam. One method, three values, an
  ``Option`` narrow enough that a judge cannot be handed a whole main.
* ``gate`` — the five refusals in order, the interruption's own bound, and the
  one thing that may be said. Nothing here writes a record.

**What this package deliberately ships without.** Half cannot currently know
that an option is closing: a loop carries a timescale and a last movement, a
belief carries a claim and its support, and *nothing anywhere carries a
horizon*. Detecting one means either a record-shape change or a derivation, and
bundling either with the rule that governs restraint is a mistake this project
has made before. So the urgency source is injected and **unwired**, the
composition root builds this gate with ``urgency=None``, and the shipped build
never interrupts anybody — which is the shape story 9d used and 9e completed.

**The restraint is the valuable half.** A product that can interrupt before it
has a rule for interrupting is worse than one that cannot interrupt yet, and
silence is the ordinary outcome here as it is everywhere else in this tree
(AD-27). A build that never interrupts is a correct build, not a broken one.

**This package re-exports nothing**, following ``half.consolidate``,
``half.loops`` and ``half.surface``: an ``__init__`` that imports a module
makes importing the package cost that module, and a consumer that names what it
wants can be read for what it depends on.
"""
