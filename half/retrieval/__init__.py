"""Retrieval over the belief set (CAP-9, AD-5, AD-24).

A layer *above* the store. `half.store` owns BM25 and knows nothing about
ranking; this package fuses that score with strand match, recency and computed
salience, and hands the result to an optional reranker that degrades visibly
when it is absent.

Three rules hold everything here together:

**Weighting, never partitioning (AD-24).** Every multiplier in the fusion has a
strictly positive floor, so no belief can be scored out of reach. A design in
which a topic switch empties the candidate set is what makes Half say *"I don't
have access to that"* — the sentence the spec rejects outright.

**No model, no vectors, no network (AD-5, AD-19).** The contextual prefix is
structural, synthesized from a belief's own fields. Anthropic's contextual
retrieval pays a model per chunk because a chunk is a fragment torn out of a
document; a belief is already a self-contained claim, so its context is
recoverable from the record.

**Nothing here writes (AD-26, AD-30).** Ranking weights are volatile: they never
enter the log, and salience is computed from folded state rather than bumped by
a counter on read. A use-counter makes materialized state a function of read
traffic instead of the log, so two replays of one log disagree.
"""
