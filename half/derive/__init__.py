"""Deriving claims from evidence (CAP-5, story 15a).

**A message is evidence; a claim is a belief.** Story 1 separated sources from
claims and story 3 built that separation for mail — a receipt is what arrived, a
claim is what Half concluded. The turn path never got the same treatment, so
until this story every inbound message was both: ``half.actor.runtime`` wrote
``ok``, ``thanks`` and ``hello?`` into a main's ledger as stated beliefs, ranked
by retrieval, eligible for a tension and aimed at by corrections.

Two modules:

* ``half.derive.gates`` — the four admission tests CAP-5 names and calls
  *individually testable*: decision-relevance, durability, independence,
  falsifiability. Each has its own name, its own question, its own labels and
  its own reason for refusing, and **all four always run**, so a message refused
  by two of them reports both rather than the first.
* ``half.derive.claim`` — the derivation, on ``half.model.consult``'s shape.
  The fourth caller of it and not the fourth copy.

**Nothing here reads a clock, opens a store, or writes a record** (AD-30). The
deriver answers *whether there is a claim*; the caller appends it, at the
weakest rung, through ``half.governance.ladder.admitted``. Derivation never
decides what Half may do with a claim.
"""
