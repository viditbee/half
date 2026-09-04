---
title: 'Story 8 — Open loops'
type: 'feature'
created: '2026-09-01'
status: 'complete'
baseline_commit: '44dc525064de79111e47aec7654da729ff35e28e'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The open loop is Half's core object and the ranking function for everything it does — and it does not exist. Story 1 left a `loop_transition` op that accepts any state and any timescale unchecked, story 4 weights four state names nothing produces, and no code can answer *"has this been silent longer than it should be?"*

**Approach:** Deliver CAP-6. Loops as first-class objects with a closed state vocabulary and their own natural timescale, silence computable against that timescale, and the firewall that keeps a wanting from being refuted like a fact. Acting on a silent loop is stories 9 and 10; the nagging bound is 5c. This story makes all three possible.

## Boundaries & Constraints

**Always:**
- **A wanting is not a fact, and nothing may refute one.** Loops are never demoted by the belief-refutation path. A retracted, revised or expunged *belief* leaves its loop standing, even when it was the loop's only support.
- **The firewall is a property of the fold, not of two branches.** `state.loops` is written by the loop-transition case and the loop-named expunge, and by nothing else — asserted over every branch, every helper the fold calls, and every module, not by looking for a substring in two case bodies. A demotion routed through a helper, another op, or a new file must fail.
- **A loop still standing must still move.** Leaving a loop in the fold while silently dropping its future transitions is a demotion wearing another name: the wanting can no longer advance, be achieved, or change at all. Every refutation case is followed by a movement that must land.
- **Erasure reaches the loop and its text.** The public erase path removes the loop and tombstones the transition bodies; a loop slug is human-meaningful and surviving it verbatim is not an erasure.
- **"We cannot tell" never becomes "the main has given up."** An unreadable stamp — movement or `now` — reports undetectable, and no unreadable input may produce silence, abandonment, or a candidate.
- **`silent()` reports only live wantings.** An achieved loop that has not moved is finished, not silent, and a ranking input that says otherwise makes stories 9 and 10 nag about what the main already did.
- **Every stamp is validated where it becomes durable.** A `last_movement` the build cannot read is refused at the append, like the state and the timescale, not tolerated into a permanently undetectable loop.
- **Shared code keeps the guards it had.** Moving arithmetic into a common module must not move it out from under the purity scan that constrained it.
- **Every period, threshold and boundary is pinned to its value**, not to a band that a wrong value still satisfies.
- **Evidence of non-action changes state, never truth.** A main who has done nothing about farmland for a year has a *stalled* loop, not a false one. There is no code path from "no evidence" to "this wanting is not real".
- **The state vocabulary is closed and versioned** — `advancing`, `stalled`, `abandoned-but-unadmitted`, `achieved` — enumerated in one place, and an unknown state is a hard error at the append, never a silent default.
- **Every loop carries its own timescale.** Farmland moves in years and a workout routine in days; a shared default would make one of them permanently wrong. A loop without a timescale is not silent-detectable and says so, rather than borrowing a number.
- **Silence is computed, never stored.** It is a function of `last_movement`, the timescale and an injected `now` — so it cannot go stale, and the fold stays pure (AD-30).
- **`abandoned-but-unadmitted` is never applied on inference alone.** Detection produces a candidate; the transition is recorded only with the main, exactly as quarantine is (CAP-10).
- **Loop movement and Half touching a loop are different facts.** This story records movement. What Half has raised, and how recently, is 5c's nagging bound and must not be conflated here.
- A loop is opened, moved and closed by appends. No state is edited in place (AD-3).
- The open-loop ledger is not a user-facing surface. It is a ranking input.
- Nothing here reads a clock, the network, or ambient state.

**Ask First:**
- Any fifth state, or any change to what a state means.
- A default timescale of any kind.
- Any path by which belief evidence changes a loop's state automatically.

**Never:**
- No nagging bound and no touch record — 5c.
- No nightly pass, no consolidation, no tension minting — story 9.
- No morning surface and no unprompted contact — story 10.
- No model call (AD-19).
- Do not make loops visible as a surface the main browses.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Open a loop | A wanting with a state and a timescale | Recorded; readable from the fold | N/A |
| Unknown state | A state outside the vocabulary | Refused at the append | Hard error, never defaulted |
| Missing timescale | A loop with no timescale | Recorded, but reported as not silent-detectable | Never borrows a default |
| Silent past its period | `last_movement` older than the timescale | Detectable as silent | N/A |
| Within its period | `last_movement` inside the timescale | Not silent | N/A |
| Different timescales | A days-loop and a years-loop, same `last_movement` | The days-loop is silent, the years-loop is not | N/A |
| Support retracted | The loop's only supporting belief is retracted | The loop still stands, unchanged | Never demoted |
| Belief revised | A belief on the loop is corrected | Loop state untouched | Never demoted |
| Belief expunged | A supporting belief is expunged | The loop survives; the belief does not | Never demoted |
| No evidence for a year | Nothing supports the wanting and nothing contradicts it | State may be `stalled`; truth is never in question | No path to refutation |
| Abandonment | Inference suggests abandoned-but-unadmitted | A candidate is produced; nothing is recorded | Never applied silently |
| Loop expunged | The loop itself is expunged, through the public erase path | Gone from the fold, and its text gone from the log | N/A |
| Correction then movement | Any correction op, then a transition on that loop | The transition lands | Standing is not enough |
| Demotion elsewhere | A demotion added in another op, a helper, or a new module | A test fails | The property, not the spelling |
| Unreadable `now` | A stamp this build cannot read | Undetectable; never silent, never a candidate | Never "given up" |
| Unreadable movement | `last_movement` is not an instant | Refused at the append | Never durable |
| Achieved and quiet | A finished loop that has not moved in a year | Not reported as silent | Finished, not abandoned |
| Exact boundary | Elapsed exactly one period, and exactly twelve | The chosen direction, asserted | Never incidental |
| Period values | Each timescale's period | Pinned to its value | Not to a band |
| Ranking | Two equal beliefs, one on an advancing loop | The loop-bearing belief ranks higher | Story 4's behaviour holds |
| Achieved | A loop that is done | Ranks lower, but is not deleted | History is kept |
| Unknown state at read | A log written by a later build | Ranking degrades gracefully; the append gate still refuses | Read tolerant, write strict |
| Purity | Same log, same injected `now` | Identical loop state and identical silence | No clock read |
| Replay | A log of opens, moves and closes | Loops identical after rebuild | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; the glossary's *open loop* and *nagging* entries are normative. AD-3, 26, 29, 30 govern.

**Reference (extraction manifest — mark the row when done):** ✅ `gbrain/skills/conventions/calibration.md` — `abandoned_threads`, high-conviction items older than twelve months and unsuperseded. Take the shape of the detection; note that Half must not apply it silently, which is a difference from the reference. *Extracted as `ledger.abandonment_candidate`; the threshold counts twelve of each loop's own periods rather than twelve months, and detection records nothing.*

**Existing, reused:** `half/store/fold.py` (the `loop_transition` case already writes `state`, `timescale` and `last_movement` unchecked — this story makes them mean something), `half/store/ops.py` (`Op.LOOP_TRANSITION`, `SCHEMA_VERSION`), `half/store/records.py::validate_fields` (where the closed vocabulary is enforced), `half/retrieval/salience.py` (`LOOP_STATES`, `UNKNOWN_LOOP_STATE` — already weights the four names), `half/crisis/aftercare.py` (the pure, injected-`now`, hand-rolled elapsed arithmetic to reuse rather than re-derive).

**To create:**
- `half/loops/states.py` — the closed vocabulary and what each state means.
- `half/loops/timescale.py` — a loop's own period, and silence computed against it.
- `half/loops/ledger.py` — opening, moving and reading loops; the refutation firewall.
- `half/tests/test_loops.py`.

**To change:** `half/store/records.py` (validate state and timescale at the append), `half/store/fold.py` (the firewall: no correction op touches a loop), `.github/workflows/ci.yml` (a CAP-6 gate with a real margin over its floor).

## Tasks & Acceptance

**Execution:**
- [x] `half/loops/states.py` -- the closed, versioned vocabulary; unknown is a hard error -- AD-29
- [x] `half/loops/timescale.py` -- per-loop period; silence from `last_movement` and an injected `now` -- CAP-6, AD-30
- [x] `half/loops/ledger.py` -- open, move, read; `abandoned-but-unadmitted` only with the main -- CAP-6, CAP-10
- [x] `half/store/records.py` -- validate state and timescale before the append -- the log is permanent
- [x] `half/store/fold.py` -- the firewall: no correction op demotes a loop -- CAP-6
- [x] `.github/workflows/ci.yml` -- a CAP-6 gate whose floor is not the size of what it protects -- gates must not pass vacuously
- [x] `half/tests/test_loops.py` -- one case per matrix row, including every refutation path -- I/O matrix

**Review round 1 — what changed, and why:**
- `half/store/fold.py` -- `State.expunged_loops`, a **separate** namespace. One shared set left a belief's erasure freezing a loop that shared its slug: the loop stood in the fold, which every firewall test asserted, while the transition guard silently dropped every later transition on it. Standing still is not standing. It poisoned the other direction too, so a loop's erasure no longer writes into the belief namespace either — a loop-named expunge carries no `target` at all, and the tombstone branch no longer records a transition's *append* id as an erased object.
- `half/store/store.py` -- `Store.expunge` now erases whatever the name refers to. It wrote a `target`-only record, which the firewall correctly refuses to let reach a loop, so erasing a loop was a silent no-op that survived replay. It also tombstones the transition bodies, via `log.expunge_bodies(..., loops=...)`: a transition is keyed on the *append's* id, not the loop's, so matching on ids alone erased nothing and the slug, state, period and every movement date stayed in the log verbatim.
- `half/store/records.py` -- `last_movement` is validated at the append (it accepted `"yesterday"` and `2026-02-31` durably), `loop` is now **required** (a transition without one became durable and then bricked every future rebuild), and the loop check runs first so every refusal is a typed `LoopError` rather than a bare `ValueError`. `LoopError` is now both a `HalfError` and a `ValueError`.
- `half/loops/timescale.py` -- `now` is read with the same widening `last_movement` gets, so a caller working in bare dates no longer loses detection on every loop; `DAY_STARTS_AT` and the `>` comparison are named and pinned.
- `half/loops/ledger.py` -- `opened` requires the current loop table and refuses to re-open (it was indistinguishable from `move` and silently overwrote a live loop); `move` no longer takes a `timescale`, which could flip a years-loop to days as a passenger on a movement append — that is now `rescale`, its own named operation; `abandon` takes an `Answer`, not a flag, because a boolean recorded only that a reply *arrived* and the obvious wiring of *"no, I still want this"* recorded abandonment; the candidate carries `raised_at` and `against_movement` so a stale one is refused rather than undetectable; `silent()` reports only live states, so stories 9 and 10 cannot nag about a wanting the main already finished; and the threshold refuses zero, negative and NaN.
- `half/store/db.py` -- `expunged_loops` table and `DERIVED_VERSION` 6 -> 7. The fold's loop semantics changed, so a stale view surviving the upgrade would have a main's ranking function disagree with their own log.
- `tests/test_purity.py` -- the ambient-call scan moved here from `tests/test_ladder.py`, over `PURE_MODULES` by name rather than over `half/governance/**` by directory. Moving the arithmetic into `half/civil.py` had moved it out from under the guard that constrained it; naming modules means moving one out of a package cannot silently move it out of the gate.
- `.github/workflows/ci.yml` -- a third gate, `cap6_structure`, and the load-bearing cases of all three are now **named inside the suite**, because a collection floor is the weakest of the protections and review proved it: deleting the two AST guards left both floors green with the firewall unguarded.

**Disagreed, with the reproduction:**
- *"`last_movement="2026-01-01"` ACCEPTED, durable"* is correct behaviour, not a defect. A bare date is one of the two stamp shapes the loop projection carries — `moment()` reads it, `silence` computes against it, and the replay fixture has used it since the first commit. The Always bullet refuses a `last_movement` the build **cannot read**; this one it can. Refusing it would reject the honest common case where a date is all anybody knows, and would leave no shape for it at all. `"yesterday"`, `2026-02-31`, `0001-01-01` and an offset zone are all refused, and both sides are asserted.

**Also changed, and why:**
- `half/civil.py` (new) -- the validated, clockless civil-date arithmetic story 6c wrote by hand inside `half/governance/aftercare.py`, moved so that the loop timescales could *reuse* it rather than re-derive it. A second parser would have disagreed with the first about which stamps are real, and the two subsystems it would govern -- a crisis floor and a loop's own period -- are the two where a stamp read too generously fails silently. `half.governance.aftercare` re-exports every name, so the crisis package still reads as one module.
- `half/store/store.py` -- one line: the op travels with the fields into `validate_fields`, because `state` names four closed vocabularies (tension, crisis, aftercare, loop) and an op-blind check would have to accept the union of all four.
- `half/retrieval/salience.py` -- the four state names it spelled out are now keyed off `half.loops.states`, so the vocabulary really does live in one place.
- `half/errors.py` -- `LoopError`, per the conventions' typed-exception rule.
- `tests/conftest.py` -- the replay fixture gained opens, moves, an `achieved` close, a loop with no timescale and an expunged loop, so AD-4 covers CAP-6.
- `tests/test_ops.py` -- the loop-expunge case now names the loop *as a loop*; the narrow form no longer reaches one, which `test_loops.py` asserts.
- `tests/test_purity.py` -- `half/civil.py` and the three loop modules added to the static no-clock scan.

**Acceptance Criteria:**
- Given a loop whose only supporting belief is retracted, revised or expunged, when the fold runs, then the loop stands unchanged in every case.
- Given a wanting with no supporting evidence for a year, when the fold runs, then no code path marks it false.
- Given a state outside the vocabulary, when it is appended, then it is refused before the record is durable.
- Given a days-loop and a years-loop with the same `last_movement`, when silence is computed, then only the days-loop is silent.
- Given a loop with no timescale, when silence is computed, then it reports as not detectable rather than borrowing a default.
- Given inference suggesting a loop is abandoned-but-unadmitted, when it runs, then a candidate is produced and nothing is recorded.
- Given the same log and the same injected `now`, when loops are read twice, then the result is identical and no clock was read.
- Given a log of opens, moves and closes, when the store is rebuilt, then every loop matches the pre-rebuild state.
- Given two equally matching beliefs where one sits on an advancing loop, when retrieval ranks them, then story 4's ordering still holds.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Spec Change Log

- **Review round 1 — the firewall guarded the wrong object.** The structural check asserted that two `fold` case bodies do not contain the substring `"loops"`, which is a spelling, not the property. Three mutations each left all 1836 tests passing: demoting a loop from the `Op.TENSION` branch (Half lowering a wanting because contradicting evidence arrived — the exact CAP-6 violation), moving the same demotion into a module-scope helper so the case body no longer names loops, and adding a new `half/loops/decay.py` exporting `demote`. Worse, a *narrow belief expunge* whose target collides with a loop slug leaves the loop standing — which every firewall test asserts — while silently dropping every later transition, so the wanting can never move again. My own mutation testing missed all of this because I injected a write to `state.loops`, which is precisely what the guard watches. Also found: `Store.expunge` no longer reaches a loop and leaves it present *and* frozen; loop text survives an erasure verbatim; `last_movement` accepts `"yesterday"` and `2026-02-31` durably; an unreadable `now` can be made to report every loop silent and abandoned; `silent()` includes achieved loops; the `days` and `weeks` periods, the abandonment threshold, the silence comparison and the bare-date widening are each unpinned or pinned only to a band; the `cap6_firewall` floor of 9 against 11 collected is exactly the size of the two cases it exists for; and moving the civil-date arithmetic into `half/civil.py` moved it out from under the ambient-call scan that had constrained it in `half/governance/`. **KEEP:** loops surviving belief correction, which is right and behaviourally tested; the per-loop timescale with no default; and `abandonment_candidate` gating on live states.

## Design Notes

**Why the firewall is structural.** "Evidence of non-action never refutes a wanting" is easy to agree with and easy to violate by accident: the natural implementation of a nightly pass that sees no movement is to lower confidence in the belief that the loop exists. Loops must therefore be unreachable from the correction path, so that violating this takes a deliberate new op rather than a plausible-looking line.

**Why a loop without a timescale is honest rather than defaulted.** A default is a number that is right for one kind of wanting and wrong for the rest, and the wrongness is silent — a farmland loop nagged monthly reads as Half not understanding the main at all. Reporting "not detectable" makes the gap visible where a default would hide it.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_loops.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest tests/test_replay.py tests/test_purity.py tests/test_retrieval.py -q` -- expected: replay exact, fold pure, ranking intact
- `cd half && uv run --extra dev pytest -m cap12 -m cap12_aftercare -q` -- expected: the crisis gates intact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — a wanting is not a fact**

- The four states, and why no evidence path reaches them.
  [`states.py:1`](../../../../half/loops/states.py#L1)

**The firewall, as a property rather than a spelling**

- Only the transition case and the loop-named expunge may touch the loop table — asserted over every branch, helper and module.
  [`fold.py:1`](../../../../half/store/fold.py#L1)

- Opening, moving and abandoning; the only place a record carrying a loop and a state is composed.
  [`ledger.py:1`](../../../../half/loops/ledger.py#L1)

**Each loop's own clock**

- Silence against the loop's own period, and the reasons it may be undetectable — none of which becomes "given up".
  [`timescale.py:1`](../../../../half/loops/timescale.py#L1)

- The shared civil-date arithmetic, now under the purity scan it used to sit outside.
  [`civil.py:1`](../../../../half/civil.py#L1)

**Tests that carry the design**

- Every refutation followed by a movement that must land — standing is not the same as working.
  [`test_loops.py:1`](../../../../half/tests/test_loops.py#L1)
