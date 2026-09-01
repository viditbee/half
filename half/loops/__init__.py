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

**Nothing here imports ``half.store``, and that is load-bearing rather than
tidy.** ``half.store.records`` validates a loop's state, timescale and movement
date before the append, and ``half.store.store`` builds the erase record through
``ledger.expunged`` — so the store depends on this package and the arrow must
not run back. The three modules below reach only ``half.errors`` and
``half.civil``, neither of which reaches anything.

**This package deliberately re-exports nothing**, for the same reason: an
``__init__`` that imported all three would make ``import half.loops.states``
from inside the store pull in the whole package, and the next module added here
would only have to import ``half.governance`` — whose own ``__init__`` reaches
back into ``half.store.records`` — to close a cycle that appears the first time
somebody imports the store before the ledger. Every consumer names the module it
wants. The cost is one dotted path.
"""
