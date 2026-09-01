"""The nightly pass: what Half does while the main sleeps (CAP-7, AD-9).

The scheduler built in story 9a drains what is due and runs a ``Pass``. Until
this package existed the pass it ran was ``Nothing`` — a first-class outcome
(AD-27), and a deliberate placeholder for the thing that runs. This is that
thing.

What it does today is one job: re-evaluate every tension against what the log
holds and an injected ``now``, and append the transitions that follow (story
9c). Minting new tensions is story 9d, promoting episodic material to durable
claims is story 3's other half, and the morning surface is story 10 — none of
them are here, and the pass sends nothing to anybody.

**It costs nothing.** No model call, no network, no batch submission: every
transition is arithmetic over the log, so the budget the pass runs under is
zero and the scheduler's timeout is not approached. That is a property worth
naming because it will not survive story 9d, and the shape that survives it is
this one — a pass whose expensive half is bounded and whose cheap half is not
allowed to become expensive by accident.

**This package deliberately re-exports nothing**, following ``half.loops``,
``half.tensions`` and ``half.schedule``. The reason given here used to be that
``half.consolidate.pass_`` reaches the actor registry — it does not, and the
``Ledger`` protocol it defines instead exists precisely so that it never has to.
The real reason is the one the other three packages give: an ``__init__`` that
imports a module makes importing the package cost that module, and a consumer
that names what it wants can be read for what it depends on. Every consumer
names the module it wants.
"""
