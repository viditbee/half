---
title: 'Story 6c — Aftercare: coming back'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: 'e6575c946482ff57d16677c9ef76b1059df569fd'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/brainstorming/brainstorm-crisis-protocol-2026-08-30/brainstorm-intent.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 6a caps a main at `behave` on entering crisis and 6c owns coming back — so today nothing ever does. A main who discloses once is governed silently forever, which is not care, and `release_ceiling` defaults to restoring everything at once, which is what CAP-12 forbids.

**Approach:** Deliver the return. A minimum thirty-day period, licenses restored in stages rather than all at once, and the mirror resuming only when the main says so — never on elapsed time alone and never silently. Plus holding a clinician-authored safety plan that Half can produce instantly and must never write. Caring Contacts need a scheduler and are deferred to after story 9.

## Boundaries & Constraints

**Always:**
- **Thirty days is a floor, not a timer.** Nothing restores before it, and reaching it grants only the first step.
- **Restore is stepwise.** `behave` → `ask` → the mirror, each step with its own dwell. A single jump back to full licence is the failure CAP-12 names.
- **The mirror resumes only on the main's word.** Elapsed time can never be the last condition; Half asks, and a main who does not answer stays where they are. Silence is not consent.
- **Consent is the whole message, and any refusal in it wins.** An affirmation found somewhere inside a sentence is not an answer to a question. *"yes, but please don't"* is a no. A standing question also expires: an affirmative token weeks later is not its answer.
- **The floor is enforced at every path that can raise a cap**, not only inside the pure function. A rule that lives in one function is not an invariant, it is a convention that function follows.
- **A guard must catch the property, not the spelling.** For the safety plan that means showing the *content* originates outside Half — a check that only forbids three ways of writing the field lets Half compose a plan from its own ledger and hand it to the blessed writer.
- **Aftercare terminates, and the question can be stopped.** A main who says *"no, and please stop asking"* is not asked every fortnight for the rest of their life. Declining is not permanent; asking is not perpetual either.
- **A stamp that is not a real instant restores nothing.** An impossible date, an out-of-range field, a missing zone or an implausible year is refused, because every one of them shortens the floor.
- **A plan is never produced on a turn about somebody else**, for the same reason aftercare stays silent there.
- **A CI floor carries a margin that is not the cases it protects.** A floor equal to the count after deleting the property tests proves nothing.
- **Half asks, never announces.** Resuming the mirror without asking is surveillance restarting, which the companion's open question exists to avoid.
- **A decline is not permanent.** Declining leaves the cap in place and Half asks again later; declining once must not mean never being asked again.
- **Re-entering crisis restarts the clock.** The floor runs from the most recent entry, never the first.
- **Aftercare is evaluated on the main's next turn**, not pushed. No scheduler exists and none is built here.
- **Elapsed time is computed from an injected `now`.** No module here reads a clock, so the fold stays pure and replay is exact (AD-30).
- **Half never authors a safety plan** — that is clinical work. It holds one made with a professional, reproduces it verbatim, and invents no step, no wording and no missing section.
- **Never gated by tier, ever**, and it continues unchanged for a lapsed or free main.
- **The operator reversal from 6a still works** and is not replaced by the schedule.
- Nothing here may cost the main their reply.

**Ask First:**
- Any change to the thirty-day floor or a step's dwell.
- Any wording change to an aftercare or safety-plan template.
- Any path that restores a licence without the main's answer.

**Never:**
- No Caring Contacts and no scheduler — deferred until story 9's due-time queue exists.
- No authoring, editing, completing or summarising a safety plan.
- No model call (AD-19); every string here is templated under 6a's never-list.
- No re-deriving whether the main is *better* — Half tracks time and consent, never recovery.
- **A green suite is not clinical review.**

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Inside the floor | Day 3 of aftercare | No restore, by any path | Time alone never restores |
| Floor reached | Day 30 | The first step only — `behave` → `ask` | Never a full restore |
| Step dwell | The step after the first, too soon | No further restore | Each step has its own floor |
| Mirror step | Every dwell satisfied | Half **asks**; the cap holds until answered | Never automatic |
| Main agrees | An affirmative answer | The mirror resumes and the event is recorded | N/A |
| Main declines | A negative answer | Cap holds; Half asks again after a further interval | Never never-again |
| No answer | The main says nothing | Cap holds indefinitely | Silence is not consent |
| Re-entry | A second crisis mid-aftercare | The floor restarts from the later entry | Never from the first |
| Evaluation point | The main sends any message | Aftercare is re-evaluated on that turn | No scheduler |
| Operator reversal | 6a's undo is used | Still works, still recorded | Unchanged |
| Tier | A free or lapsed main | Identical behaviour | Never gated |
| Safety plan held | A plan authored with a professional | Produced verbatim on request | No step invented |
| Safety plan absent | None held | Half says so plainly and offers nothing invented | Never improvised |
| Plan authoring, any spelling | A module composing plan lines from Half's own data and passing them to the writer | A test fails | The property, not the spelling |
| Plan ingestion | A main gives Half a clinician's plan | A production path exists to receive it | Not test-only |
| Plan on a third-party turn | A plan request inside a reply about someone else | Not produced | Same rule as aftercare silence |
| Refusal containing yes | "yes, but please don't" | Read as a refusal | A refusal anywhere wins |
| Affirmation in passing | "yes, I went to the shops" | Not consent | Consent is the whole message |
| Stale question | An affirmative long after the question | Not its answer | Questions expire |
| Stop asking | The main asks not to be asked | The question stops; the cap holds | Never perpetual |
| Impossible stamp | 2026-02-31, 10:00:99, no zone, year 1 | Restores nothing | Every one shortens the floor |
| Floor at the write path | Any caller raising a cap inside the floor | Refused there too | Not only in the pure function |
| Lost ceiling append | In the mode, no ceiling record | The next turn caps them | The self-heal is exercised |
| Upgraded view | A derived view written before aftercare existed | Discarded and replayed; a decline survives | Never silently lost |
| Plan authoring | Any attempt to write or complete a plan | Structurally impossible | Not a filter |
| Purity | Same log, same injected `now` | Identical aftercare state | No clock read |
| Replay | A log spanning entry, steps and consent | Licences identical after rebuild | N/A |
| Reply safety | A store failure while evaluating | The turn still replies | Never silence |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; the companion's aftercare section is normative. AD-9, 19, 22, 27, 28, 30 govern.

**Reference:** the extraction manifest was checked — no row falls due. Stanley–Brown safety planning and the Caring Contacts evidence are cited in the companion.

**Existing, reused:** `half/actor/registry.py` (`crisis_record`, `crisis_open`, `lower_ceiling`, `release_ceiling`, `reverse_crisis` — note `release_ceiling` currently defaults to a full restore to `assert`, which this story must constrain), `half/governance/ladder.py` (`Ceiling`, `License`), `half/store/fold.py::State` (`ceiling`, `crisis`), `half/crisis/templates.py` and `respond.py` (the never-list and the no-locale discipline), `half/crisis/gate.py` (the turn path), `half/crisis/rows.py` (`plain`, for any text reaching a main).

**To create:**
- `half/crisis/aftercare.py` — the floor, the steps, the consent gate; pure, `now` injected.
- `half/crisis/safetyplan.py` — holding and reproducing a plan; no authoring surface.
- `half/tests/test_aftercare.py`, `half/tests/test_safetyplan.py`.

**To change:** `half/crisis/gate.py` (evaluate on the turn, ask when due), `half/actor/registry.py` (stepwise release; constrain the full-restore default), `half/crisis/templates.py` (the ask, the decline, the plan lines), `.github/workflows/ci.yml` (an aftercare gate with its own floor).

## Tasks & Acceptance

**Execution:**
- [x] `half/crisis/aftercare.py` -- floor, steps and dwells computed from an injected `now` -- CAP-12, AD-30
- [x] `half/crisis/aftercare.py` -- the mirror step requires the main's answer; silence holds the cap -- companion
- [x] `half/actor/registry.py` -- stepwise release; no path restores everything at once -- CAP-12
- [x] `half/crisis/gate.py` -- evaluate on the main's turn; ask when due; never announce -- no scheduler
- [x] `half/crisis/safetyplan.py` -- hold and reproduce verbatim; no authoring surface exists -- clinical boundary
- [x] `half/crisis/templates.py` -- the ask, the decline and the plan lines, under 6a's never-list -- reviewable
- [x] `.github/workflows/ci.yml` -- an aftercare gate with a real margin over its floor -- gates must not pass vacuously
- [x] `half/tests/test_aftercare.py` -- one case per matrix row -- I/O matrix
- [x] `half/tests/test_safetyplan.py` -- verbatim reproduction, absence, and the impossibility of authoring -- clinical boundary

**Acceptance Criteria:**
- Given day 29 of aftercare, when any path attempts a restore, then nothing restores.
- Given day 30, when aftercare is evaluated, then only the first step is granted and the mirror is not.
- Given every dwell satisfied, when aftercare is evaluated, then Half asks and the cap holds until the main answers.
- Given a main who never answers, when any number of turns pass, then the cap holds.
- Given a main who declines, when a further interval passes, then Half asks again.
- Given a second crisis during aftercare, when the floor is computed, then it runs from the later entry.
- Given a held safety plan, when it is requested, then it is reproduced verbatim with nothing added.
- Given no plan, when one is requested, then Half says so and invents nothing.
- Given the repository, when the suite runs, then no code path can author or complete a plan.
- Given the same log and the same injected `now`, when aftercare is evaluated twice, then the result is identical and no clock was read.
- Given a free or lapsed main, when aftercare runs, then behaviour is identical.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Spec Change Log

- **Review round 1 — the clinical boundary and the consent gate both leaked.** Verified: a new module composing plan lines from Half's own ledger and passing them to `held_fields` left 1604 tests green, so Half could author a safety plan and read it back framed as a clinician's — the guard checked three spellings of writing the field, never where the content came from. And `reads_as_consent` matched an affirmation at any position, so *"yes, but please don't"* and *"sure, I picked up the milk"* both resumed the mirror; the standing question never expired, so any later affirmative was read as its answer. Also: the thirty-day floor lived only in the pure function while `restore_step` checked one-rung-ness alone, and the CI gate's comment claimed a floor it did not enforce; the calendar parser accepted 2026-02-31, 2026-02-29, `10:00:99`, a missing zone and year 1, each shortening the floor; `hold_ceiling`'s body could be emptied with the suite green, leaving a main whose ceiling append was lost uncapped for ever; both schema bumps could be reverted, silently losing recorded declines on upgrade; and the aftercare CI floor was exactly the count remaining after deleting the twelve property tests it protects. **KEEP:** the three schedule numbers are pinned in both directions by behavioural cases — that held under mutation and must survive; and stale consent from a previous period is correctly discarded on re-entry.

## Design Notes

**Why no scheduler.** Aftercare's restore is a question about a main who is present; evaluating it on their next message means Half asks when they are already in the conversation rather than interrupting to ask permission to interrupt. Caring Contacts are the opposite — their value is arriving when the main has not written — which is why they wait for story 9 rather than being approximated here.

**Why consent gates the last step and not the first.** Coming off `behave` restores Half's ability to ask; resuming the mirror restores its ability to confront. The first is a return to ordinary conversation and can follow time; the second changes what Half will say about the main to their face, and the companion's open question is exactly that it must not feel like surveillance resuming.

**Why Half cannot author a plan.** Steps 3 and 4 of Stanley–Brown are literally Half's data, which makes authoring feel one field away. It is clinical work, and a plan Half wrote would be produced at 3am with the authority of one a clinician made.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_aftercare.py tests/test_safetyplan.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest -m cap12 -m cap12_durable -m cap12_handoff -q` -- expected: 6a and 6b intact
- `cd half && uv run --extra dev pytest tests/test_replay.py tests/test_purity.py -q` -- expected: fold still pure, replay exact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — what the floor permits, and when**

- Pure, `now` injected: the floor, the steps, and the answer that is the only route to the mirror.
  [`aftercare.py:1`](../../../../half/crisis/aftercare.py#L1)

**The two gates that leaked in round one**

- Consent is the whole message, anchored, and any refusal in it wins.
  [`signals.py:1`](../../../../half/crisis/signals.py#L1)

- The floor refuses at the write path too, and an `agreed` needs a question that was actually put.
  [`registry.py:1`](../../../../half/actor/registry.py#L1)

**The clinical boundary**

- Half holds a plan and cannot compose one: the guard checks the argument, not the field name.
  [`safetyplan.py:1`](../../../../half/crisis/safetyplan.py#L1)

**Tests that carry the design**

- The three schedule numbers pinned in both directions, and the plan-authoring bypass that must stay closed.
  [`test_aftercare.py:1`](../../../../half/tests/test_aftercare.py#L1)
