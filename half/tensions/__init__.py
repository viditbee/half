"""The tension ledger: the record of the gap between what the main says and
what they do (CAP-7, AD-3, AD-30).

A tension is the mirror made durable — a first-class record linking two entries
that disagree, carrying a state and a license. Minting is story 9d; this package
is what makes a minted tension *mean* something: a closed state vocabulary, a
transition computed from what the log already holds, and no path anywhere that
ranks its two sides.

Three modules, and the split follows ``half.loops`` exactly:

* ``states`` — the closed, versioned vocabulary. One place, and it is that one.
* ``widening`` — the computation. A function of the log and an injected ``now``,
  and of nothing else; when it cannot be computed for a tension it says so.
* ``ledger`` — reading tensions, and producing the *fields* of a transition
  append for a caller to write under the main's own mutex (AD-1).

**Two rules that are easy to get backwards, so they are written down twice.**

*A correction resolves a tension; it never deletes one.* This is the deliberate
**inverse** of story 8's refutation firewall. A loop is a *wanting*, which
evidence cannot refute, so the correction path is structurally unable to reach
the loop table. A tension is a claim *about two entries*, so retracting one of
them genuinely ends the disagreement — and the correction path therefore *must*
reach the tension table. Somebody applying the loop rule here by analogy would
leave tensions standing over entries that no longer exist. History is kept: a
resolved tension is still a record, never an erased one.

*Neither side of a tension is wrong.* Nothing in this package ranks the two
entries, picks a winner, or records one as mistaken. Every computation over the
pair is symmetric in it, every result that names the sides names them by id in a
mapping rather than by position, and no field written to the log says which side
moved. For a person, both entries can be true at once; that is the whole reason
the object exists (constitution: *name the gap, never render the verdict*).

Pure and clockless throughout: ``now`` is always injected (AD-30), nothing here
writes, and this package imports nothing from ``half`` but ``civil`` and
``errors`` — which is what lets ``half.store.records`` validate against it
without closing a cycle.

**This package deliberately re-exports nothing**, following ``half.loops`` and
``half.schedule``. Every consumer names the module it wants.
"""
