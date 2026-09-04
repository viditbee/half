# Review — Adversarial Divergence

**Lens:** Construct two units one level down that each obey every AD to the letter yet still build incompatibly. Every pair found is a hole.
**Target:** `ARCHITECTURE-SPINE.md` (Half v1)
**Verdict:** FAIL on first pass — five constructible divergences, one of them a direct contradiction between two ADs. All five closed.

## D1 — The op vocabulary is open (CRITICAL)

**Attack.** Story 1 builds the store and writes `{"op":"assert"}`. Story 12 builds correction and writes `{"op":"belief_retract"}`. Both obey AD-3 (one JSON object per line, carrying `t`/`op`/`id`) and the log-record convention. Neither is wrong. Replay in either implementation silently skips the other's records — and AD-4's replay test passes in each repo in isolation, because each only replays what it wrote.

**Why the spine allowed it.** AD-3 fixes the *shape* of a record and never fixes the *set* of ops.

**Closed by AD-29:** the op vocabulary is closed, enumerated in one module, and versioned; an unknown op on replay is a hard error, never a skip.

## D2 — Replay can call a model (CRITICAL — AD-4 vs AD-20 contradiction)

**Attack.** AD-20 makes model tier per-actor config. AD-7/AD-9 have consolidation call a model to mint tensions. If the log records *that consolidation ran* and the fold re-derives its output, then replaying a main who upgraded from the cheap tier to the higher tier produces different tensions — and **AD-4's byte-identical guarantee is false**. Two units can each be compliant: one implements the fold as "replay the recorded outcomes," the other as "re-run the derivation." Both read AD-4 as satisfied.

**Why the spine allowed it.** AD-4 asserts byte-identical replay without saying what replay is *permitted to do*.

**Closed by AD-30:** the log records the *outcome* of every non-deterministic operation, never a promise to re-derive it. **Replay never calls a model, never hits the network, and never reads the clock.** This is what makes AD-4 true rather than aspirational.

## D3 — Two writers to one projection (HIGH)

**Attack.** AD-3 says projections are derived from the log. `half.store.projections` renders `loops/*.md`. But `half.consolidate` transitions loop state — so it naturally writes the loop file too. AD-1's single writer is satisfied (one actor, no concurrency), yet two code paths render the same artifact and their formats drift within a release.

**Closed by AD-31:** exactly one renderer owns each projection type; no other module writes a projection file. Modules emit log records and the renderer folds them.

## D4 — Silence has no shape (MEDIUM)

**Attack.** AD-27 makes staying silent a first-class outcome, but doesn't say what it *is*. One unit returns `None`; another returns a `Silence(reason=...)`. The metrics unit (AD-21) and the telemetry unit (AD-22) both need the reason to count anything, and get nothing from the first implementation.

**Closed by AD-32:** silence is a typed outcome carrying its reason; the reason is required, since AD-21 and AD-22 both consume it.

## D5 — Eviction can interrupt a turn (MEDIUM)

**Attack.** AD-8 makes hibernation "eviction from the LRU" and never says eviction respects the mutex. A memory-pressure eviction landing mid-turn drops an in-flight response, or worse, evicts between a model call and its log append — losing the record of work already paid for.

**Closed by AD-33:** eviction requires the mutex to be free; an actor with an in-flight turn is never evicted, and the log append that closes a turn happens before the mutex is released.

## Attempted and did not break

- **AD-18 two-channel context vs AD-5 retrieval.** A `behave` belief's text passes through retrieval before the split. It cannot leak to the model (the builder transforms it) and cannot leak to logs (AD-22 forbids content). No divergence.
- **AD-24 no-exclusion vs AD-18 license filtering.** These look contradictory but are not: AD-24 governs *reachability*, AD-18 governs *representation*. A `behave` belief is always retrievable and never quotable.
- **AD-12 sharding vs AD-11 secrets.** A shard drain-and-move must carry the secret store. Not a divergence between two units — a runbook item. Noted under Deferred rather than made an AD.
