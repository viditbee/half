"""The open-loop ledger: Half's core object (CAP-6).

A fact is true or false; a **wanting** is neither. It has a *state* and a
*natural timescale*, and the ledger of open loops is the ranking function for
everything Half does — not a surface the main browses.

Three modules, and the split is deliberate:

* ``states`` — the closed, versioned vocabulary and what each state means.
* ``timescale`` — a loop's own period, and silence computed against it from
  ``last_movement`` and an injected ``now``.
* ``ledger`` — opening, moving and reading loops, the abandonment candidate,
  and the fields an append carries.

**This package deliberately re-exports nothing.** ``half.store.records`` has to
validate a loop's state and timescale before the append, so it imports
``half.loops.states`` and ``half.loops.timescale`` — and an ``__init__`` that
imported ``ledger`` here would drag ``half.governance`` into that import, whose
own ``__init__`` reaches back into ``half.store.records`` and closes the cycle.
Every consumer names the module it wants. The cost is one dotted path; the
alternative is an import error that appears the first time somebody imports the
store before the ledger.
"""
