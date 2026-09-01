"""The morning surface: at most one unprompted thing a day, or nothing (CAP-8).

Four modules, and the split is the story:

* ``touch`` — what Half raised, which of the main's days it spent, and what it
  cited. An append, never an edit, and deliberately not the same record as a
  loop *moving* (AD-3, story 8) nor the same field as a day spent (story 10's
  review, so CAP-10's interrupt cannot eat a morning).
* ``view`` — the projection the surface is handed. An allowlist over the fold,
  because the guarantee that a morning cannot suppress itself on aftercare has
  to be that the field is *absent*, not that nobody wrote the line.
* ``choose`` — the candidate set, the per-loop nagging bound derived from each
  loop's own period, and the one choice. Pure and clockless.
* ``morning`` — the surface itself: crisis, one a day, the choice, the ladder,
  reachability, the claim, or silence.

**Silence is the ordinary outcome, not a degraded one** (AD-27). Most days
produce nothing, and every module here is written so that the *easy* path is
the quiet one: a quiet pass produces no candidates, an uncomputable bound
refuses rather than guesses, and every uncertainty resolves toward saying
nothing. The failure this package is written against is a Half that finds
something to say because saying nothing feels like a bug.

**The package straddles two layers, and the split is the reason no arrow is
reversed.** ``touch``, ``view`` and ``choose`` are *domain*: they depend on
``half.store``, ``half.loops`` and ``half.governance`` and on nothing above
them, they are pure and clockless, and ``tests/test_purity.py`` holds them to
it. That is why ``half.consolidate.pass_`` may import ``choose.Candidate`` to
say what a night produced, and why ``half.actor.registry`` may import ``view``
to narrow what it hands out — both are reaching sideways within the domain, not
upward. ``morning`` is the *composition*: it reads the pass, the ladder, the
context builder and the channel, so it sits above all four and nothing in the
domain imports it.
"""
