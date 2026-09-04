# Review — Rubric Walker

**Lens:** the good-spine checklist.
**Target:** `ARCHITECTURE-SPINE.md` (Half v1), after the reconcile pass and the adversarial fixes.
**Verdict:** PASS.

| Criterion | Judgement |
| --- | --- |
| Fixes the real divergence points for the level below, missing none | **Pass.** 33 ADs against 12 stories. The reconcile pass caught five spec requirements the draft dropped (AD-24…AD-28); the adversarial pass caught five constructible divergences (AD-29…AD-33). |
| Every Rule is enforceable and prevents its stated divergence | **Pass with one honest exception.** AD-10 states plainly that Python cannot structurally forbid a direct import, and claims only the strongest available guarantee. Naming the limit is better than a Rule that pretends. AD-4, AD-18, and AD-29 are all machine-checkable. |
| Nothing under Deferred could let two units diverge | **Pass.** Every deferred item is either an unbuilt second implementation behind an existing port (multi-provider, reranking), an operational procedure (shard rebalancing, the drain-and-move runbook), a product call that does not touch structure (variable latency), or a spec non-goal whose arrival seam is named (the Channel port and the log format). |
| Named technology is verified-current | **Pass.** See `review-verification-audit.md` — FTS5 and `bm25()` verified by execution, the rest via PyPI and vendor docs, three unpinned rows fixed. |
| Ratifies rather than contradicts an existing codebase | **N/A.** Greenfield; no `project-context.md` anywhere in the tree. Where prior art exists it is cited as ported (hermes-agent) or as a rejected alternative with the reason recorded. |
| Covers the driving spec's capabilities | **Pass.** All 14 capabilities appear in the Capability → Architecture Map with a component and governing ADs. |
| No new AD weakens an inherited one | **N/A.** No parent spine. The spec's constraints are treated as binding and were re-checked in the reconcile pass. |
| Every dimension the altitude owns is decided, deferred, or open | **Pass.** Paradigm, storage, retrieval, gateway, model access, secrets, scheduling, deployment and environments, sharding, backup and restore, observability and telemetry, and failure/outage behaviour are each covered. The operational envelope — the dimension a domain-focused draft usually skips — is carried by AD-9, AD-12, AD-13, AD-14, AD-15, AD-16, and AD-23. |

## Notes

**Strongest part.** AD-18 (two-channel context) does real architectural work: it makes the license ladder enforceable by construction rather than by classifier, and it resolves a genuine design conflict — filtering `behave` material out entirely would leave Half either blunt or silent. It is also the AD most likely to be flattened during implementation, and it carries its own test.

**Weakest part.** AD-9 leans on a Batch API turnaround margin that was reasoned rather than measured. Consequence is bounded (a missed morning surface, and the rule already says send nothing), but it is the one place a number is doing work without evidence behind it. Carried as an assumption.

**Watch item for build.** AD-30 (replay is pure) is the invariant most likely to be violated accidentally, because "just re-derive it" is the natural implementation of a fold. The CI replay test of AD-4 only catches it if the fixture spans a tier change — the test needs to be written with that case in it deliberately.
