---
title: 'Story 5d — The unsaid'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: 'a1c2c12'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-10 says *"insights above the current license are queued **with release conditions**"*. The withholding half is built and enforced — 4b splits the context by license, 5a's ladder decides the rung, AD-28's ceiling caps it — but the queue does not exist. Half holds things back correctly and can say nothing about what it is holding, or what would have to change. Silently withheld is not queued.

**Approach:** A computed view over the fold. For every belief Half holds below the rung it would need to speak, name **the precondition its promotion is missing** — and the ladder already enumerates those, so the release condition is read rather than invented. Depth is inspectable, because the glossary says queue depth is itself a signal.

**A view, never a route.** CAP-10's same sentence says these are *"never placed in the model's context as quotable content — enforcement happens at context construction, not by filtering generated text"*. That enforcement exists and this story must not create a second way to the wire. The unsaid queue reports what is held and what would release it; it delivers nothing and promotes nothing.

## Boundaries & Constraints

**Always:**
- **The release condition is the ladder's own refusal**, read from it and never restated. `promote` refuses for enumerable reasons, and `resolve` applies the ceiling — the main has not acknowledged it, an `assert` cites nothing, the belief is quarantined — and the queue names which one applies. A second list of conditions here is two rules that agree until they do not.
- **Quarantine is terminal and says so.** The pin is permanent and no path lifts it, so a quarantined belief is not *waiting* for anything. It must not appear as an item with a condition that could be met.
- **Computed from the log, never stored.** No queue record, no counter, no field — the lesson 5b's balance, 9c's decay and 15a's mark all carry. The only way to get the queue is to fold the log.
- **A view, not a route.** Nothing here composes, sends, promotes, or reaches a channel. Nothing here widens what may enter a context. A test must show that adding this queue did not add a path to the wire.
- **Depth is inspectable and its reasons are separable.** *"Eleven insights waiting on an acknowledgement"* and *"eleven waiting on a receipt"* are different situations, and a number that cannot tell them apart is the failure 5b's `queue` docstring names.
- **The ceiling is applied where licenses are resolved** (AD-28), so an item's rung is the effective one — a main capped at `behave` holds more unsaid, and the queue says so rather than reporting the uncapped answer.
- Pure and clockless where it can be: the same log gives the same queue for ever.

**Ask First:**
- Any release condition not already enumerated by `promote` **or by `resolve`**. The ceiling is a release condition and is `resolve`'s, not `promote`'s — an earlier wording named only `promote` and contradicted the matrix row that requires the ceiling.
- Any change to the ladder, to what a promotion requires, or to what the context builder admits.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- No new route by which a held insight could reach a context, a composer, or a channel.
- No promotion, no acknowledgement written, no record appended.
- No stored queue, count or flag.
- No model call — every condition here is structural.
- Do not build the release *action* (below), do not touch the unasked queue, and do not change the ladder.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Waiting on the main | A belief that would be `assert` but is unacknowledged | Queued, condition names the acknowledgement | N/A |
| Waiting on a receipt | Acknowledged, but cites nothing | Queued, condition names the evidence | N/A |
| Waiting on both | Neither acknowledged nor cited | Both named, not the first | Separable reasons |
| Quarantined | A pinned belief | **Not queued** — nothing would release it | Never a false hope |
| Already sayable | A belief at the rung it needs | Not queued | N/A |
| Capped | The ceiling holds it below its own rung | Queued, and the condition is the ceiling | AD-28 |
| Nothing held | A main with nothing above its license | An empty queue, not an error | The ordinary case |
| Depth | Eleven held for two different reasons | Depth and both reasons readable | The glossary's signal |
| Computed | Any queue | Folded from the log; no record anywhere | AD-3, AD-30 |
| No new route | The whole tree | No path from the queue to a context or a channel | Asserted structurally |
| Nothing promoted | Reading the queue, repeatedly | The log is unchanged | Never a silent write |
| A ceiling lifts | Aftercare restores a rung | The queue shrinks with no write of its own | Derived |
| An acknowledgement lands | The main acknowledges | That item leaves the queue on the next fold | Derived |
| Replay | Any log | The same queue, byte for byte | AD-4 |
| Erased | A belief that was expunged | Absent from the queue | Tombstones respected |
| Worldwide | Claims in any script | Queued the same; no locale on the path | Never defaulted |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-10, CAP-5, AD-3, AD-18, AD-22, AD-28, AD-30 govern this story.

**Reference (extracted from the manifest):** none expected; check for a row naming the unsaid queue or release conditions.

**Existing, reused:** `half/governance/ladder.py` (`promote`'s refusals, `own_rung`, `Ceiling`, `quarantined`), `half/context/build.py` (`resolve` — the one door that answers what rung a belief is effectively on), `half/store/fold.py`.

**To create:**
- `half/governance/unsaid.py` — the queue, computed; one item per held insight, each naming its missing precondition.
- `tests/test_unsaid.py`.

**To change:**
- `half/actor/registry.py` — a read-only door, mirroring the existing narrowed views.
- `.github/workflows/ci.yml` — a CAP-10 unsaid gate, per-case marks, margin stated.

## Tasks & Acceptance

**Execution:**
- [ ] `half/governance/unsaid.py` -- computed queue; conditions read from `promote` -- CAP-10
- [ ] quarantine is terminal and never an item -- no false hope
- [ ] depth and reasons separable -- the glossary's signal
- [ ] `half/actor/registry.py` -- a read-only door, narrowed like its siblings -- AD-1
- [ ] no new route -- asserted structurally -- CAP-10, AD-18
- [ ] `tests/test_unsaid.py` -- every matrix row -- I/O matrix
- [ ] `.github/workflows/ci.yml` -- the gate, per-case marks -- the floor lesson

**Acceptance Criteria:**
- Given a belief that would be `assert` but is unacknowledged, when the queue is read, then it is present and its condition names the acknowledgement.
- Given a belief neither acknowledged nor cited, when the queue is read, then **both** conditions are named rather than the first.
- Given a quarantined belief, when the queue is read, then it is absent — asserted by a case that fails if it appears with any condition.
- Given a main capped by a ceiling, when the queue is read, then the items reflect the effective rung and the ceiling is named as the condition.
- Given the queue read any number of times, when the log is compared before and after, then it is unchanged.
- Given the whole tree, when it is scanned, then no path leads from this queue to a context, a composer or a channel — asserted structurally, not by reading.
- Given any log, when it is folded twice, then the queue is identical.
- Given the full suite, when it runs, then it passes offline with no model call and no network.

## Design Notes

**Why the release condition is read and not written.** `promote` already refuses for exactly three reasons, and each is a precondition a caller could satisfy. Restating them here would produce a second list that agrees with the ladder until somebody edits one — the failure this codebase has caught in a denylist, a marker list and a floor comment. The queue asks the ladder what is missing.

**Why quarantine is not an item.** A quarantined belief is held for ever and no path lifts the pin. Listing it with a condition would suggest something could release it, and the one thing worse than a silent withholding is a queue that lies about what is waiting.

**Why this is a view and nothing more.** CAP-10's sentence puts the enforcement at context construction and says so explicitly, because a queue with a delivery path is a second route to the wire and the first thing a later story would reach for. Building the report without the release action is deliberate: what to *do* when a condition is met is a product question — Half could ask, could wait, could say nothing — and story 11's question engine is the obvious partner, since a question answered is exactly the acknowledgement a promotion needs. That link is worth naming and is not this story's to build.

**What a reviewer should be hardest on.** That reading the queue writes nothing, and that no route exists from it to a wire — both asserted structurally rather than by a fixture, since a fixture only shows the routes somebody thought of.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_unsaid.py -q` -- expected: the queue passes
- `cd half && uv run --extra dev pytest -m ad28 -q` -- expected: the ceiling unbroken
- `cd half && uv run --extra dev pytest -m ad18 -q` -- expected: the two-channel split unbroken
- `cd half && git status --porcelain` -- expected: clean tree after commit


## Spec Change Log

### 2026-09-04 — the Ask First named one door and the matrix required two (review loop 1)

**Triggering finding.** Ask First read *"any release condition not already enumerated by `promote`"*, but `promote` knows nothing about ceilings — AD-28 lives in `resolve`. The matrix nonetheless required "queued, and the condition is the ceiling", and the Always list said the queue "says so". Under a literal reading of the Ask First the implementer should have stopped; it built the ceiling condition, taking the matrix as the more specific instruction, and flagged the contradiction rather than choosing quietly.

**Amended** to name both doors. The ceiling genuinely is a release condition — aftercare lifting a cap releases held insights without any belief changing — and the wording was mine, too narrow, and the second self-contradicting frozen block in two stories.

**Two consequences worth recording rather than fixing here.** The acknowledgement and receipt conditions **cannot arise from a log this build wrote**: `admitted()` births at `behave`, `promote(to=ASSERT)` requires both preconditions and writes `known_to_main` itself, `demote` only lowers, `quarantine` writes `behave`, and the fold carries forward only `STICKY`. A belief at `assert` missing a precondition can therefore only come from a foreign or legacy log — a real operational case `own_rung`'s demotion branch exists for, but it means the only condition reachable through this product's own doors today is the ceiling. And `tests/test_ladder.py::governed_writes` reads explicit keywords only where its neighbour `ceiling_omissions` treats `kw.arg is None` as a failure, so `store.record(Op.ASSERT, "b_1", t, **{"license": "assert"})` walks past the write monopoly — verified; a splat's `kw.arg` is `None`, so a scan looking for a name sees nothing to check.
