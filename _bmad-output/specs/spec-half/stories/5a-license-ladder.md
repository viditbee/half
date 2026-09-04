---
title: 'Story 5a — The license ladder and the ceiling'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: 'bc4c201ea5463f032c6d52759a4c49629e84c36b'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every belief carries a license, and story 4b enforces it — but nothing decides what a license may *become*. Today a license is whatever was written at append time, so `assert` is a field anyone can set, and the constitution's hardest rule — that Half is structurally incapable of asserting without a receipt — is a sentence in a document rather than a property of the code.

**Approach:** Deliver the first slice of CAP-10: the rules governing which rung a belief may occupy, quarantine as a pinned field rather than an exception list, and AD-28's global ceiling applied where licenses are resolved. The trust balance and the two queues are story 5b; the interrupt and nagging bound follow story 8.

## Boundaries & Constraints

**Always:**
- **`assert` requires two independent things: a receipt and prior knowledge.** A citation into Half's own evidence, *and* the main already knowing Half holds the belief. Being correct is not sufficient — the danger of assertion is being unexpected, not being wrong.
- **Half's own inference never licenses assertion.** No amount of corroboration promotes a belief on its own; promotion is an event involving the main.
- An unsupported claim may be **asked**, never asserted.
- **Quarantine is a pinned field, not an exception list**, and pins a belief at `behave` permanently. Inference may produce a quarantine *candidate*; applying it requires asking. Half never quarantines on inference alone.
- **The ceiling is applied where licenses are resolved, never where messages are composed** (AD-28). One ceiling per actor caps every belief regardless of its own value, so a new surface cannot bypass it by forgetting to check.
- **A ceiling caps; it never promotes.** Raising the ceiling cannot lift a belief above its own license.
- **Demotion is always permitted; promotion never is by default.** The weakest rung is both the default and the failure mode — unknown, missing or malformed licenses resolve to `behave`.
- A license change is an append, never an edit (AD-3). Replay reproduces the same licenses.
- **Only the ladder writes a license field.** Read-side enforcement alone leaves `assert` a field any caller can set — it merely raises the price to three fields. `license`, `support`, `known_to_main` and the quarantine field are written through the ladder and nowhere else, gated statically the way readers are.
- **Quarantine survives every subsequent append.** The fold carries it forward; no ordinary record clears it, and replay reproduces it set. Permanence that lasts one record is not permanence.
- **A ceiling is durable and fails closed.** It must survive actor eviction and process restart — eviction is routine, not exceptional, and a cap that lifts itself is worse than no cap because it reads as protection. Losing the store is the only thing that may lose a ceiling.
- **A ceiling has exactly one way to move, and raising it is a named exception with a precondition** — never an ordinary setter, and never reachable by assigning the field on a handed-out object.
- **An acknowledgement earns only the rung it was given for.** Recording that the main permitted a question must not pre-satisfy the precondition for a statement.
- **One answer to what rung a belief is on.** Promotion, demotion and resolution must agree; a stated rung and an effective rung that disagree is the second opinion this story exists to remove.
- Nothing here reads a clock, the network, or ambient state; the fold stays pure (AD-30).
- Anything that changes what a belief may permit is pinned by a test that observes the permission, not the field.

**Ask First:**
- Any runtime dependency beyond the standard library and pinned SDKs.
- A fourth rung, or any change to what a rung permits.
- Any path that grants `assert` without both preconditions.

**Never:**
- No trust balance, no unsaid or unasked queue, no release conditions — story 5b.
- No interrupt rule and no nagging bound — after story 8.
- No question engine: quarantine and promotion produce candidates; the asking is 5b and story 11.
- No crisis aftercare policy — story 6 sets the ceiling; this story only builds it.
- No model call (AD-19), and no post-generation filtering of any kind (AD-18).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Default | Belief with no license | Resolves `behave` | Never `assert` |
| Malformed | License is unknown, null, or not a string | Resolves `behave` | Never raises |
| Assert, no receipt | Belief licensed `assert` with an empty support set | Refused; resolves below `assert` | Never quotable |
| Assert, unknown to main | Support present, but the main has never been told | Refused | Never quotable |
| Assert, both met | Support present and the main already knows | Resolves `assert` | N/A |
| Inference alone | Corroboration count grows without the main | Never promotes | N/A |
| Promotion event | The main is told and acknowledges | Promotion recorded as an append | Replay reproduces it |
| Quarantined | Belief carrying the quarantine field | Pinned `behave`; promotion refused | Permanent |
| Quarantine candidate | Inference suggests quarantine | A candidate is produced; nothing is pinned | Never applied silently |
| Ceiling at `behave` | Actor ceiling `behave`, belief `assert` | Resolves `behave` | N/A |
| Ceiling raised | Ceiling `assert`, belief `behave` | Resolves `behave` — a ceiling never promotes | N/A |
| Ceiling default | No ceiling configured | Resolves to the belief's own license | Never above it |
| Demotion | `assert` belief demoted to `behave` | Applied immediately | Always permitted |
| Bypass attempt, read | A caller resolves a license outside the ceiling path, by any import spelling | A test fails | Never silently allowed |
| Bypass attempt, write | A module outside the ladder writes `license`, `support`, `known_to_main` or quarantine | A test fails | Never silently allowed |
| Quarantine persists | An ordinary append for a quarantined belief, omitting the field | Still pinned `behave` after the fold and after replay | Never cleared |
| Ceiling survives eviction | Actor capped, evicted under pressure, rehydrated | Still capped | Never lifts itself |
| Ceiling survives restart | Capped, process restarted | Still capped | Never lifts itself |
| Ceiling raised by assignment | A caller assigns the rung on a ceiling it was handed | Refused | Never an ordinary setter |
| Ask acknowledgement | The main permits a question about a belief | Does not satisfy the `assert` precondition | Rungs earned separately |
| Effective vs stated | A belief stated `assert` with no receipt | Promotion and resolution give the same answer | No second opinion |
| Replay | A log containing promotions and demotions | Licenses identical after rebuild | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding. AD-3, 18, 28, 30 govern. The constitution's *"Assert only with receipts"* and *"The danger of assertion is being unexpected, not being wrong"* are the two rules this story makes executable.

**Reference:** the extraction manifest was checked — the two open story-5 rows both belong to later slices. gbrain's `nudge.ts` cooldown goes with the nagging bound after story 8; its `voice-gate.ts` goes with delivery in 5b.

**Existing, reused:** `half/context/build.py::resolve` (the single place a license becomes a decision — the ceiling belongs *inside* it, which story 4b explicitly left open), `half/context/channels.py::License`, `half/store/ops.py` (`revise` already exists; promotion is an append), `half/store/records.py::validate_fields`, `half/store/fold.py::State`, `half/actor/registry.py::Actor` (where a per-main ceiling lives, beside `strands` and `retrieval`), `half/errors.py`.

**To create:**
- `half/governance/ladder.py` — the rung rules, the two `assert` preconditions, quarantine, and promotion/demotion validity.
- `half/tests/test_ladder.py` — one case per matrix row.

**To change:** `half/context/build.py` (resolve consults the ladder and the ceiling), `half/actor/registry.py` (the per-actor ceiling), `.github/workflows/ci.yml` (an AD-28 gate, marker-selected with a collected-count floor like the AD-18 one).

## Tasks & Acceptance

**Execution:**
- [x] `half/governance/ladder.py` -- rung rules; `assert` requires receipt **and** prior knowledge -- constitution
- [x] `half/governance/ladder.py` -- quarantine pins at `behave`; inference yields a candidate only -- CAP-10
- [x] `half/governance/ladder.py` -- the ceiling: caps, never promotes; default is no cap -- AD-28
- [x] `half/context/build.py` -- `resolve` consults ladder and ceiling; no other path resolves a license -- AD-28, AD-18
- [x] `half/actor/registry.py` -- one ceiling per actor, beside `strands` and `retrieval` -- per-main isolation
- [x] `.github/workflows/ci.yml` -- an AD-28 gate with a collected-count floor -- gates must not pass vacuously
- [x] `half/tests/test_ladder.py` -- one case per matrix row, including the bypass and replay cases -- I/O matrix

**Execution — review round 1:**
- [x] `half/governance/ladder.py` -- `admitted()`: a belief is born at the weakest rung and there is no argument that raises it -- writer gate
- [x] `half/tests/test_ladder.py` -- a writer gate symmetric with the reader gate; `tests/conftest.py::seed_belief` is the one sanctioned test writer and is itself pinned -- Always/34
- [x] `half/store/records.py`, `half/store/fold.py` -- quarantine is a sticky field the fold carries forward; no later record drops it -- Always/35
- [x] `half/store/ops.py`, `fold.py`, `db.py`, `half/actor/registry.py` -- the ceiling is a log op, folded state and re-read at hydration; survives eviction and restart -- Always/36
- [x] `half/governance/ladder.py` -- `Ceiling` frozen; `lowered_to` only lowers; `released(because=...)` is the named exception -- Always/37
- [x] `half/governance/ladder.py` -- `known_to_main` written only for an assert-level acknowledgement -- Always/38
- [x] `half/governance/ladder.py` -- promotion and demotion compare against `own_rung`; `db.py` drops the stale `license` column -- Always/39
- [x] `half/context/build.py`, `half/actor/runtime.py` -- `build` and `respond` keyword-required; the bypass gate resolves every import spelling -- Bypass, read
- [x] `half/store/records.py` -- `support`, `known_to_main`, `quarantined`, `rung` validated before they become durable
- [x] `.github/workflows/ci.yml`, `tests/test_purity.py` -- the AD-28 marker is per case with a floor just under it; the ladder joins `PURE_MODULES`

**Acceptance Criteria:**
- Given a belief licensed `assert` whose support set is empty, when its license is resolved, then it is not `assert` and its text is not quotable.
- Given a belief with support that the main has never been told, when its license is resolved, then it is not `assert`.
- Given corroboration accumulating with no involvement of the main, when licenses are resolved, then no belief is ever promoted.
- Given a quarantined belief, when promotion is attempted by any path, then it remains `behave`.
- Given inference that suggests quarantine, when it runs, then a candidate is produced and no belief is pinned.
- Given an actor ceiling of `behave`, when an `assert` belief is resolved, then it resolves `behave`; and given a ceiling of `assert` with a `behave` belief, then it resolves `behave`.
- Given a caller that resolves a license without passing through the ceiling, when the suite runs, then a test fails.
- Given a log containing promotions and demotions, when it is replayed, then every license matches the pre-replay state.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access.

## Spec Change Log

- **Review round 1 — read-side enforcement is not enforcement.** The Intent claimed this story stops `assert` being "a field anyone can set"; it did not. A caller can still append `license="assert"` with `support` and `known_to_main` set by hand, because the ladder gates readers and only offers writers a helper. Amended to require a writer gate symmetric with the reader gate. Also amended: quarantine was cleared by any ordinary append that omitted the field (verified — the belief returned to `assert` and replay reproduced it cleared), so the fold must carry it forward; and the ceiling lifted itself on routine LRU eviction as well as restart, so it must be durable. **KEEP:** `ceiling` being keyword-only with no default on the deciding function — a forgetting caller should get a `TypeError`, not a silent uncapped resolve; `known_to_main` requiring a literal `True`; and quarantine outranking both preconditions.

## Design Notes

**Why the ceiling lives inside `resolve`.** AD-28 exists because aftercare implemented as per-feature suppression is forgotten by the next feature. Story 4b already made `resolve` the single place a license becomes a decision, so the ceiling has exactly one home; anywhere else and AD-28's stated failure returns.

**Why promotion needs an event, not a threshold.** The tempting design promotes on corroboration count. That makes Half assert things the main has never heard it think — correct, unexpected, and trust-destroying in exactly the way the constitution names. Promotion therefore records something that happened *with* the main.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network
- `cd half && uv run --extra dev pytest tests/test_ladder.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest -m ad18 -m ad28 -q` -- expected: both gates collect and pass
- `cd half && uv run --extra dev pytest tests/test_replay.py tests/test_context.py -q` -- expected: no regression
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — the rules, in one place**

- The ladder: two independent `assert` preconditions, quarantine, and the ceiling.
  [`ladder.py:1`](../../../../half/governance/ladder.py#L1)

**Making the thesis true**

- `admitted()` is the only way a belief is born, and no argument to it raises a rung.
  [`ladder.py:1`](../../../../half/governance/ladder.py#L1)

- The single place a license becomes a decision; `ceiling` has no default.
  [`build.py:125`](../../../../half/context/build.py#L125)

**Permanence that actually lasts**

- Quarantine is carried forward by the fold, so an ordinary append cannot clear it.
  [`fold.py:1`](../../../../half/store/fold.py#L1)

- A ceiling is a log record, so it survives eviction and restart; frozen, and lowers only.
  [`registry.py:1`](../../../../half/actor/registry.py#L1)

**Tests that carry the design**

- Reader and writer gates, resolving package re-exports, attribute calls and `**kwargs`.
  [`test_ladder.py:1`](../../../../half/tests/test_ladder.py#L1)
