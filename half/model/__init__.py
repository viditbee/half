"""The model port: one ``ModelProvider``, one implementation (AD-19, AD-20).

Four modules, and the split is the whole point:

* ``port`` — the protocols and the values. Classification and generation are
  **separate protocols**, so a caller that may only classify holds an object
  with no way to produce text. The four failures are **values**, not
  exceptions, because what a failure means is the caller's to decide.
* ``tier`` — which model a main's calls run on, as configuration (AD-20). The
  only place in the tree where a model identifier is written down.
* ``budget`` — per-call and per-pass cost ceilings, and the refusal that
  happens *before* the spend (CAP-7).
* ``anthropic`` — the one implementation, with its transport injected, exactly
  as ``half.channel.telegram`` takes its transport (story 2).

**This package ships with no production caller, deliberately.** Its five
consumers — claim derivation, the crisis classifier, consolidation, tension
minting and the reply itself — are each their own story with their own risk,
and wiring one of them here would put the port's design and that consumer's
risk into a single review. The exception is stated rather than discovered.

**Nothing here is reachable from a fold (AD-30).** Replay never calls a model:
``half.store`` depends on domain types alone, and no module under ``half/store``
imports this package, which ``tests/test_model.py`` asserts over the whole tree
rather than over the two files that happen to matter today.

**This package deliberately re-exports nothing**, following ``half.loops`` and
``half.schedule``. Every consumer names the module it wants, so that importing
the port's value types never drags in the SDK edge.
"""
