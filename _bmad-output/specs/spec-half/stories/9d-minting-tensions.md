---
title: 'Story 9d — Minting tensions'
type: 'feature'
created: '2026-09-03'
status: 'done'
baseline_commit: 'e176826'
review_loop_iteration: 2
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 9c built the tension state machine and `TensionPass` re-evaluates what exists — but nothing creates a tension. CAP-7's central object is minted nowhere, so *drift is tension velocity* is a sentence about an empty ledger, and the nightly pass has nothing to move.

**Approach:** Build the minter CAP-7 specifies, and specifies precisely: **candidates are new or changed entries**, compared **against the loop set and against beliefs sharing a subject**, gated by **a cheap relevance filter before any model comparison**, inside **a fixed per-user cost budget**, and **never all-pairs**. The disagreement judgement itself is injected as a narrow port and is not implemented here.

**Not in this story:** the model behind that port. A tension is minted when two entries *disagree where neither is wrong*, which is a semantic call — and putting a fourth model integration inside the story whose central rule is a bound is the bundling this project has got wrong before. The port ships with a deterministic implementation for tests and no production judge; 9e supplies one.

## Boundaries & Constraints

**Always:**
- **Never all-pairs.** The candidate set is entries new or changed since this main's last pass. Each is compared against the loop set and against beliefs sharing its subject, and against nothing else. This is CAP-7's success criterion, not an optimisation.
- **The comparison count has a ceiling of its own.** CAP-7's two comparison sets cannot bound it on the data Half writes, because every belief carries one subject — so a ceiling on couples per pass, independent of those sets, is what makes the bound real. It is spent before it is exceeded, like the judgement budget, and a pass that reaches it says so.
- **The arithmetic runs off the event loop.** Minting tokenises every claim and sorts; `half/schedule/tick.py` states the rule — `asyncio.wait_for` cannot cancel a coroutine that never yields, so a pass doing real CPU work runs past its bound with the tick looking healthy. The re-evaluation half is already threaded; the minting half must be too.
- **What is bounded is the cost, not the comparison count.** CAP-7's criterion is that the pass runs inside a fixed per-user budget; the comparison sets are how it gets there, and the filter and the budget are what make it hold. A comparison set that happens to be wide does not break the rule — an unfiltered or unbudgeted pass does.
- **The cheap filter runs before the port, always.** A pair the filter rejects never reaches the judge, so the judge's cost is a function of what survived the filter rather than of the ledger's size.
- **The bound is per main and per pass**, and it is spent before it is exceeded: a pass that would exceed it stops minting and says so, rather than finishing and reporting.
- **A tension links two entries and names no winner.** `between` carries no order — nothing may read `between[0]` as the stated, the true or the first side — and minting must not write a field that reintroduces one.
- **A minted tension starts `fresh`**, and every state change after that is 9c's, through 9c's door. This story adds no state and no transition.
- **The pass reads the clock once, from the tick**, and nothing below the scheduler reads another (AD-30). Minting is a pure function of the log, the injected `now`, and the port's answers.
- **Nothing is minted twice.** A pair already carrying a live tension yields nothing, and a pass that runs twice over the same log mints the same set once.
- **The refutation firewall holds** (CAP-6): a tension is a link between entries and never demotes, freezes or refutes a wanting.

**Ask First:**
- Any change to `TENSION_FIELDS`, the tension record shape, or 9c's state vocabulary.
- Any comparison set beyond the two CAP-7 names.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- **No model call in this story**, and no provider wired into the composition root for it.
- No all-pairs comparison, no full-ledger scan per pass, and no unbounded candidate set.
- No tension text (AD-22): the record carries ids and a state, never a sentence about the disagreement.
- No state transition, no drift computation, no widening — all 9c's, unchanged.
- Do not touch the crisis path, the turn path, or the morning surface.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| The ordinary mint | A changed stated entry, a revealed one sharing its subject, judge says they disagree | One tension, `fresh`, linking the two | N/A |
| Judge says no | The filter admits a pair, the judge finds no disagreement | Nothing minted; the pair is not retried this pass | N/A |
| Filter rejects | A pair the cheap filter finds irrelevant | The judge is never called for it | Asserted by call count |
| Never all-pairs | A ledger of many entries, few changed | Never the product of the ledger with itself: each candidate meets the loop set and the subject set and nothing else | Asserted structurally |
| The cost is what is bounded | A subject set as wide as the ledger | The filter, the couple ceiling and the per-main budget hold the cost flat regardless | CAP-7's own criterion |
| A first pass on real data | No prior pass, every belief on one subject | The couple ceiling holds; the pass never builds the whole pair set | Never all-pairs, in fact |
| The loop is not stalled | A large ledger | The arithmetic runs off the event loop and the tick's bound can cancel it | AD-9 |
| A suspended main resumes | Crisis suspended one or more nights | Everything said meanwhile is still a candidate | Never silently excluded |
| Beyond the budget | More couples than judgements | Reconsidered on a later pass, or reported as dropped — never silently discarded | Says what it did |
| Nothing changed | No new or changed entry since the last pass | No candidates, no judge calls, no mint | N/A |
| Already linked | A pair that already carries a live tension | Nothing minted | Idempotent |
| Twice over one log | The same pass run twice | The same set, minted once | Replay-safe |
| Budget reached | The pass would exceed its per-main bound | Minting stops and the pass says so | Never overspends |
| Judge unavailable | No port wired, or it refuses | The pass completes, minting nothing | Never fatal |
| Judge raises | The port throws | That pair is skipped; the pass continues | Never costs the pass |
| No winner | Any minted tension | `between` carries no order and no side is marked | Structural |
| The wanting stands | A tension over a belief supporting a loop | The loop is untouched (CAP-6) | Structural, by AST |
| Loop set | A changed entry against this main's loops | Compared; a disagreement with a wanting is mintable | N/A |
| Subject set | A changed entry against beliefs sharing its subject | Compared | N/A |
| Anything else | A changed entry against an unrelated belief | Never compared | Never all-pairs |
| Tension text | Any mint | Absent from the log and every projection | AD-22 |
| Replay | A log of minted tensions | Folds identically; the minter reads no clock | AD-4, AD-30 |
| Crisis | A main in the mode | The pass does not mint for them | CAP-12 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-7, CAP-6, CAP-12, AD-3, AD-9, AD-19, AD-22, AD-30 govern this story.

**Reference (extracted from the manifest):** three rows, all targeted at story 9 and all still open.
- **graphiti** `graphiti_core/utils/maintenance/edge_operations.py` — edge resolution returning `(resolved, invalidated, new)`. Take the *shape*: one pass over a candidate set yields three disjoint outcomes rather than a bare list of creations. Note what Half does differently — a tension is not an edge and resolution here never invalidates a wanting (CAP-6).
- **HippoRAG** `src/hipporag/rerank.py` (`DSPyFilter`) — a recognition-memory filter pruning candidates *before* expensive work. This is CAP-7's "cheap relevance filter before any model comparison", and the row has been open since story 4 for exactly this moment.
- **honcho** `src/dreamer/surprisal.py` — surprisal-based sampling to target reasoning at anomalous observations. Study it for how the filter should *rank* what survives when the budget cannot take everything; reject anything requiring a model to compute the surprisal, which would put a model call in front of the filter.

Mark each row with what was taken and what was rejected, in the style of the completed rows.

**Existing, reused:** `half/tensions/ledger.py` (`Tension`, `read`, `sides`, `plan`, `transition`), `half/tensions/states.py`, `half/consolidate/pass_.py` (`TensionPass`), `half/store/records.py` (`TENSION_FIELDS`), `half/schedule/tick.py`, `half/actor/registry.py`.

**To create:**
- `half/consolidate/candidates.py` — new-or-changed selection and the two comparison sets. Pure.
- `half/consolidate/relevance.py` — the cheap relevance filter, and the ranking that decides what a full budget takes first. (Built as `filter.py`; renamed in review loop 2, because it shadowed the builtin and both importers renamed it at the import site.)
- `half/consolidate/port.py` — the `Disagreement` protocol: one method, two entries in, a verdict out. Narrow by construction.
- `half/consolidate/mint.py` — the bound, the three outcomes, and the append.
- `tests/` — `test_minting.py`, `test_candidates.py`.

**To change:**
- `half/consolidate/pass_.py` — the pass mints as well as re-evaluates. 9c's re-evaluation is untouched.

## Tasks & Acceptance

**Execution:**
- [x] `half/consolidate/candidates.py` -- new or changed, against the loop set and the subject set only -- CAP-7
- [x] `half/consolidate/relevance.py` -- cheap, before the port, and ranked for a full budget -- CAP-7, HippoRAG
- [x] `half/consolidate/port.py` -- one method; no generation, no store, no clock -- AD-19
- [x] `half/consolidate/mint.py` -- the per-main bound, three outcomes, idempotent append -- graphiti
- [x] `half/consolidate/pass_.py` -- mint then re-evaluate; 9c's half unchanged -- CAP-7
- [x] `tests/test_candidates.py` -- the two sets, and that nothing else is ever compared -- I/O matrix
- [x] `tests/test_minting.py` -- the bound, idempotence, the firewall, the absent judge -- I/O matrix
- [x] `.github/workflows/ci.yml` -- a CAP-7 minting gate, margin sized to the subset it protects -- the floor lesson

**Acceptance Criteria:**
- Given a ledger of many entries and few changed, when a pass runs, then the number of comparisons is a function of the changed set and not of the ledger — asserted by counting, and by a structural rule rather than by one fixture's arithmetic.
- Given a pair the cheap filter rejects, when the pass runs, then the judge is never called for it — asserted by a call counter at zero.
- Given a pass that would exceed its per-main budget, when it runs, then it stops minting and reports it, and nothing was overspent.
- Given no port wired, or one that refuses or raises, when the pass runs, then it completes, mints nothing from that pair, and is never fatal.
- Given the same log passed twice, when both passes finish, then the same tensions exist and none is duplicated.
- Given a tension over a belief that supports a loop, when the fold runs, then the wanting still stands.
- Given any minted tension, when the record is read, then `between` carries no winner and the log holds no sentence about the disagreement.
- Given the full suite, when it runs, then it passes offline with no model call and no network.

## Design Notes

**Why the judge is a port and not a model.** CAP-7's success criterion is almost entirely about the *bound* — what is compared, against what, filtered how, inside which budget. That is the part with a correctness rule, and it is testable without a model. The judgement is a semantic call that will need a provider, a cost cap, a breaker and a tally — and that machinery already exists in three copies with one bug living in all three, which is recorded as needing extraction. Adding a fourth copy inside this story would bundle a model integration with the story whose whole subject is not spending. The port keeps the seam honest: 9e or the extraction supplies the judge.

**Why "never all-pairs" needs a structural assertion.** A fixture with ten beliefs and two changed will pass whether the code compares 2×N or N². The rule is about *growth*, so assert growth: a ledger that doubles with the same changed set must not double the comparisons. Story 11's review found the mirror of this — a sweep that asserted `<= 1` and passed at zero — and a counting assertion over one fixture size is the same shape.

**Why minting starts at `fresh` and stops there.** 9c owns every transition and computes widening from the stamp on the record that set the current state. A minter that also transitioned would give 9c two writers for one field, and the second would be the one nobody tests. The mint is one record; everything after it is the pass's existing half.

**The order of the two halves.** Mint first, then re-evaluate, so a tension minted this pass is evaluated in the same pass rather than waiting a day for its first state. That means the re-evaluation must tolerate a tension whose stamp is `now` — which 9c already does, since a `fresh` tension at zero elapsed time is its ordinary starting case.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_minting.py tests/test_candidates.py -q` -- expected: the minting path passes
- `cd half && uv run --extra dev pytest -m "cap7 or cap6_firewall" -q` -- expected: 9c and the firewall unbroken
- `cd half && uv run --extra dev pytest -m ad9 -q` -- expected: the scheduler unbroken
- `cd half && git status --porcelain` -- expected: clean tree after commit


## Spec Change Log

### 2026-09-03 — the comparison-count claim was mine and was wrong (review loop 1)

**Triggering finding.** The matrix said *"comparisons scale with the changed set, not the ledger"*. They do not, and cannot, on the data Half actually writes: `half/actor/runtime.py:700` sets `subject="self"` on every inbound belief and is the only production belief-subject writer, so *"beliefs sharing a subject"* is the whole stated ledger. Measured by the implementer: 61 beliefs, one changed, 60 couples. The implementer built CAP-7 as written rather than working around it, because the workaround is a subject-derivation rule and this spec's Ask-First list forbids a third comparison set — which was the correct call.

**Amended.** The row now says what CAP-7 says: never the product of the ledger with itself. A second row states the criterion CAP-7 actually rests on — the cost is held flat by the filter and the per-main budget, which the implementer measured doing exactly that (60 couples → 30 after the filter → 24 judgements at the budget).

**Known-bad state avoided.** A row no implementation could satisfy, which either invites a fixture built to make it look true or invites a third comparison set the Ask-First list exists to prevent.

**KEEP.** The XOR-derived couple id, which makes order-independence arithmetic rather than a guard; the three filter rules; the counts-only surprisal ranking; the three-valued verdict; margin-zero `cap7_minting` with per-case marks.


### 2026-09-04 — the comparison bound needs a ceiling, and the arithmetic needs a thread (review loop 2)

**Triggering findings.** Three reviewers and I measured the same thing independently: on a first pass over the ledger Half actually writes — `since is None`, every belief `subject="self"` — `couples` produces exactly `n(n-1)/2`. Not "scales with the ledger": literally the complete pair set (20 → 190, 40 → 780, 80 → 3160). The code is faithful to CAP-7; CAP-7's second comparison set is degenerate on this data, which is recorded as deferred. Nothing capped `considered`, so the judgement budget bounded the *bill* while memory and CPU were unbounded. And the minting half runs that arithmetic synchronously on the event loop while its sibling re-evaluation is threaded — measured at 1.64s of unyielding CPU for 800 beliefs, in front of every main's inbound turn, past a timeout that cannot fire because `asyncio.wait_for` cannot cancel a coroutine that never yields.

**Amended.** A couple ceiling per pass, independent of the comparison sets, spent before it is exceeded. The arithmetic runs off the event loop. Five matrix rows added, one amended.

**Known-bad state avoided.** A nightly pass that builds the complete pair set for a real main, holds the loop the inbound path shares while it does, and cannot be cancelled by the bound written to cancel it.

**KEEP.** Everything from loop 1's KEEP list, plus: the three filter rules and the counts-only ranking; the three-valued verdict; the per-case marks on `cap7_minting`.

**One boundary crossing, accepted.** Satisfying *"a suspended main resumes … never silently excluded"* required a `pass_ran` field on the **schedule** record, which is another story's shape and outside this story's "To change" list. The implementer flagged it rather than doing it quietly. Accepted: there is no way to know whether a main's pass actually ran without the scheduler saying so — `_advance` writes a marker for unscheduled, missed and suspended mains alike — the change is additive, and absence reads as false, which fails toward *everything is new* rather than toward silence. Verified: `record.data.get(PASS_RAN) is True` filters an unmarked record out of the watermark set, so an older build's records make more entries candidates rather than fewer, bounded by the couple ceiling.
