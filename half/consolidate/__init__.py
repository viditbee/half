"""The nightly pass: what Half does while the main sleeps (CAP-7, AD-9).

The scheduler built in story 9a drains what is due and runs a ``Pass``. Until
this package existed the pass it ran was ``Nothing`` — a first-class outcome
(AD-27), and a deliberate placeholder for the thing that runs. This is that
thing.

What it does today is two jobs. It **mints** the tensions CAP-7's bound
produced — new or changed entries against the loop set and against beliefs
sharing a subject, through a cheap relevance filter, inside a fixed per-main
budget, never all-pairs (story 9d) — and it **re-evaluates** every tension
against what the log holds and an injected ``now``, appending the transitions
that follow (story 9c). Promoting episodic material to durable claims is story
3's other half and the morning surface is story 10; neither is here, and the
pass sends nothing to anybody.

**It still costs nothing, and that is now a fact about a seam rather than about
an absence.** The disagreement judgement — *do these two entries disagree where
neither is wrong* — is a semantic call, and it lives behind
``half.consolidate.port`` with no implementation in this build and none wired
into the composition root. So every transition and every candidate pair is
arithmetic over the log, the budget the pass runs under is zero, and the
scheduler's timeout is not approached. What story 9e adds is a judge behind that
port and nothing else: the bound, the filter and the budget that decide how
often it may be asked are already here and already under test.

**This package deliberately re-exports nothing**, following ``half.loops``,
``half.tensions`` and ``half.schedule``. The reason given here used to be that
``half.consolidate.pass_`` reaches the actor registry — it does not, and the
``Ledger`` protocol it defines instead exists precisely so that it never has to.
The real reason is the one the other three packages give: an ``__init__`` that
imports a module makes importing the package cost that module, and a consumer
that names what it wants can be read for what it depends on. Every consumer
names the module it wants.
"""
