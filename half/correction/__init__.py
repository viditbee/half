"""Correction: the main tells Half it is wrong, and the belief changes (CAP-11).

Four modules, and the split is the story's three rules made structural:

``signals``
    The offline table. What an **explicit** correction looks like, and which of
    the three meanings it carries. Pure, stdlib-only, no clock, no store, no
    model. This is the fast, high-confidence path and it is deliberately tight.

``attribute``
    The three states — *Half was wrong*, *the main changed*, *not yet known* —
    read off two optional stamps and never off an op. Pure.

``candidate``
    The classifier's widening. A phrase table fires only on what somebody
    thought to write down, so the table is not the recall instrument on its own
    — but what the model produces is a **candidate**, never an append (CAP-10).

``apply``
    The record a correction becomes, and the line Half shows. Pure, and it
    refuses to plan an inferred correction the main has not confirmed.

**Nothing here opens a store.** There is no ledger, no door, no injected
registry: every module is a pure function over values, and the append happens
in the one place that already holds the main's mutex
(``half.actor.runtime``'s turn path). A second writer is against AD-1, and the
cheapest way to have none is to have nothing here that could be one — asserted
by ``tests/test_unasked.py``'s package sweep, which this package joins with an
**empty** door.

**Nothing here composes prose.** What Half shows as removed is the removed
claim, quoted from the record, behind a marker built out of the op's own name.
The only strings this package writes that a main could read are the ones the
closed op vocabulary already contains.
"""

from __future__ import annotations
