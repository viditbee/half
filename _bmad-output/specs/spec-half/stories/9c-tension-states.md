---
title: 'Story 9c — Tension states and the nightly pass'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: 'cc794171a5ccbfc40f2d54cb252f534bfcde6df2'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A tension is the record of the gap between what the main says and what they do — the mirror, made durable. The fold accepts a tension record and copies its fields unchecked: no state vocabulary, no transitions, no way to compute whether a disagreement is widening. And the scheduler built in 9a runs a pass that does nothing.

**Approach:** Give tensions what story 8 gave loops — a closed state vocabulary validated at the append, transitions computed from what the log already holds, and a pass that re-evaluates them against an injected `now`. Minting is 9d; this story makes a minted tension mean something. Salience decay is **not** in scope: story 4 made salience computed, so it already decays.

## Boundaries & Constraints

**Always:**
- **The state vocabulary is closed and versioned** — `fresh`, `persistent`, `widening`, `closing`, `resolved` — enumerated in one place, with an unknown state a hard error at the append and never a silent default.
- **Widening is computed, never judged.** It is a function of what the log holds — evidence accumulating on one side while the other has not moved — and of an injected `now`. If it cannot be computed for a tension, that says so rather than guessing.
- **`resolved` is terminal, by every route.** No later append, no transition, and no ordering of records may move a tension out of it, and replay must agree. A rule stated in prose and guarded on one path only is the shape three earlier stories shipped.
- **A tension is resolved whenever a side is absent, not only while folding the correction.** Minting over an entry that is already gone must not produce a live tension, or the pass computes drift across something that does not exist.
- **The neutrality and resolution guards cover every module that touches a tension**, including the code this story adds to the store and the registry — not only the tension package.
- **A correction changes a tension's state; it never deletes one.** This is the opposite of story 8's loop firewall and the contrast is deliberate: a loop is a *wanting*, which evidence cannot refute, while a tension is a claim *about two entries*, so retracting one of them genuinely resolves the disagreement. History is kept — a resolved tension is not an erased one.
- **Neither side of a tension is wrong.** Nothing here ranks the two entries, picks a winner, or records one as mistaken. For a person, both can be true at once; that is the whole reason the object exists.
- **A tension carries a license and defaults to `behave`** (5a). Nothing here promotes one, and the ladder decides what may be said about it.
- **The pass is idempotent and pure at its core.** Re-running it over the same log with the same `now` produces the same states, and a transition is an append, never an edit (AD-3, AD-30).
- **The pass costs nothing this story.** No model call, no network; the budget it runs under is zero and the scheduler's timeout is not approached.
- **A tension that cannot be evaluated leaves its state alone**, is counted, and never blocks the rest of the pass.
- Drift is tension velocity and loop advancement is tensions closing (glossary) — both must be *computable* from what this story records, though neither metric surface is built here.

**Ask First:**
- Any sixth state, or any change to what a state means.
- Any threshold that decides widening.
- Any path by which the pass writes something other than a transition.

**Never:**
- No minting, no comparison, no relevance filter — story 9d.
- No claim derivation — story 3's other half.
- No salience decay: it is already delivered, and storing a counter for a pass to mutate would reintroduce the AD-30 violation story 4 avoided.
- No model call, no network (AD-19 exists; this story does not need it).
- No metric surface, no reporting to the main, no unprompted message — story 10.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| A minted tension | Two entries that disagree | Recorded `fresh`, readable from the fold | N/A |
| Unknown state | A state outside the vocabulary | Refused at the append | Hard error, never defaulted |
| Fresh to persistent | Time passes with both sides unmoved | Transitions on the pass | Computed, not judged |
| Widening | Evidence accumulates on one side only | Computable as widening | From the log alone |
| Not computable | A tension whose sides cannot be compared | Reported as such; state unchanged | Never a guess |
| One side retracted | A supporting belief is retracted | The tension resolves; it is not deleted | History kept |
| Append after resolution | A later tension record naming a resolved tension | Still resolved | Terminal by every route |
| Minted over a gone side | A tension whose side was already retracted | Not live | Never drift over nothing |
| Ranked field, any spelling | `moved_side`, `winner_id`, `more_credible` | Refused at the append | Not exact-string |
| Guard coverage | Tension code in the store or the registry | Scanned by the same guards | Not only the package |
| One side expunged | A side is expunged | Same — resolves, survives as a record | Never erased silently |
| Both sides stand | Nothing changed | No transition is appended | Idempotent |
| Re-run | The same pass twice with the same `now` | The same states, no duplicate appends | Idempotent |
| Neither side wrong | Any tension | No ranking, no winner, nothing marked mistaken | Structural |
| License | A newly minted tension | `behave`, and nothing here promotes it | 5a decides |
| Pass under the scheduler | A due main | The pass runs, within its budget, and returns | Nothing sent |
| Pass fails for one main | An unreadable record | Counted; other mains unaffected | Never stops the pass |
| Purity | The same log and `now`, twice | Identical states; no clock read below the scheduler | AD-30 |
| Replay | A log of mints and transitions | Tensions identical after rebuild | N/A |
| Expunged tension | The tension itself is expunged | Gone from the fold | N/A |
| Metrics | Any set of tensions | Velocity and closings are derivable | Not surfaced here |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; the glossary's *tension* entry is normative. AD-3, 9, 26, 29, 30 govern.

**Reference:** the extraction manifest's graphiti rows — edge resolution returning `(resolved, invalidated, new)`, and episodic-versus-entity nodes — belong to 9d's minting and are **not** due here. Mark nothing extracted for this story unless it is genuinely used.

**Existing, reused:** `half/loops/states.py` and `half/loops/ledger.py` (the shape to follow: closed vocabulary, append fields returned rather than written, validated before durability), `half/store/fold.py` (the `Op.TENSION` case, which currently copies data unchecked — and story 8's firewall, whose *inverse* applies here), `half/store/records.py::validate_fields` (op-aware since story 8), `half/civil.py` (clockless arithmetic, injected `now`), `half/schedule/tick.py` (`Pass`, the protocol the scheduler runs — currently `Nothing`), `half/governance/ladder.py` (a tension's license).

**To create:**
- `half/tensions/states.py` — the closed vocabulary and what each state means.
- `half/tensions/widening.py` — the computation, from the log and an injected `now`.
- `half/tensions/ledger.py` — reading tensions and producing transition appends.
- `half/consolidate/pass_.py` — the `Pass` the scheduler runs.
- `half/tests/test_tensions.py`, `half/tests/test_pass.py`.

**To change:** `half/store/records.py` (validate the state at the append), `half/store/fold.py` (the resolution rule, and its contrast with the loop firewall), `half/__main__.py` (the scheduler runs this pass, not `Nothing`), `.github/workflows/ci.yml` (a CAP-7 gate whose floor is not the size of its guarantee cases).

## Tasks & Acceptance

**Execution:**
- [x] `half/tensions/states.py` -- the closed, versioned vocabulary; unknown is a hard error -- AD-29
- [x] `half/tensions/widening.py` -- widening computed from the log and an injected `now`; not-computable says so -- CAP-7
- [x] `half/tensions/ledger.py` -- transitions as appends; nothing ranks the two sides -- constitution
- [x] `half/store/fold.py` -- a correction resolves a tension and never deletes it; contrast with the loop firewall stated -- CAP-6/CAP-7
- [x] `half/store/records.py` -- validate the tension state before the append -- the log is permanent
- [x] `half/consolidate/pass_.py` -- the pass the scheduler runs; idempotent, costs nothing, one main's failure isolated -- AD-9
- [x] `half/__main__.py` -- wired so the scheduler runs this pass, asserted by value -- reachable
- [x] `.github/workflows/ci.yml` -- a CAP-7 gate with margin that is not its guarantee cases -- gates must not pass vacuously
- [x] `half/tests/test_tensions.py`, `half/tests/test_pass.py` -- one case per matrix row -- I/O matrix
- [x] `half/store/store.py` -- a tension's first record names its pair -- review round 1
- [x] `half/actor/registry.py` -- one read under the mutex; an append that carries its premise -- review round 1

**Acceptance Criteria:**
- Given a state outside the vocabulary, when it is appended, then it is refused before the record is durable.
- Given a tension whose one side is retracted, revised or expunged, when the fold runs, then the tension resolves and still exists in every case.
- Given evidence accumulating on one side while the other has not moved, when the pass runs, then the tension is computed as widening.
- Given a tension whose sides cannot be compared, when the pass runs, then it is reported as not computable and its state is unchanged.
- Given any tension, when the repository is scanned, then no path ranks its two sides or records one as mistaken.
- Given the same log and the same injected `now`, when the pass runs twice, then the states are identical and no second transition is appended.
- Given a main whose tension record is unreadable, when the pass runs, then it is counted and every other main still runs.
- Given the shipped composition, when it is built, then the scheduler holds this pass and not `Nothing`, asserted by value rather than by keyword.
- Given a log of mints and transitions, when the store is rebuilt, then every tension matches the pre-rebuild state.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Design Notes

**Why a correction resolves a tension but cannot demote a loop.** Story 8 made loops unreachable from the correction path because a wanting is not a fact and evidence of non-action cannot refute one. A tension is the opposite kind of object: it is a claim *about two entries*, so retracting one of them genuinely ends the disagreement. Someone applying story 8's rule here by analogy would leave tensions standing over entries that no longer exist, which is why the contrast is written down rather than left to be inferred.

**Why widening is computed rather than judged.** *Drift is tension velocity* is a metric the product is measured on, and a metric a model decides is a metric that moves when the model changes. The transitions come from what the log holds, so two builds reading one log agree.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_tensions.py tests/test_pass.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest tests/test_replay.py tests/test_purity.py -q` -- expected: replay exact, fold pure
- `cd half && uv run --extra dev pytest -m cap6 -m ad9 -m cap12 -q` -- expected: loops, the scheduler and crisis intact
- `cd half && git status --porcelain` -- expected: clean tree after commit
