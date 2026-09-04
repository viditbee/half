---
title: 'Story 10 — The morning surface'
type: 'feature'
created: '2026-09-02'
status: 'done'
baseline_commit: 'd63022d55f91fdca440a932bdba32d2725ff0e3b'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Everything Half needs in order to say one useful thing in the morning now exists — loops with their own timescales, tensions with computable states, a scheduler, a ladder deciding what may be said, a context builder splitting content from directives — and nothing says anything. Half has never sent an unprompted message.

**Approach:** Deliver CAP-8: at most one unprompted message a day, traceable to the preceding night's pass, and silence when there is nothing worth saying. This story also brings the **per-loop nagging bound**, because *what is worth saying today* and *what may be touched today* are the same question: without it, a surface that picks the best-ranked loop raises a years-long loop every morning.

## Boundaries & Constraints

**Always:**
- **At most one unprompted message a day**, per main, and a day is the main's own local day (9a's zone rule: told, never inferred).
- **Every surface traces to the preceding pass.** Its content cites a tension, a loop transition, or an ingested item from that pass; nothing is surfaced that cannot say where it came from.
- **Silence is the ordinary outcome, not a failure** (AD-27). A day with nothing worth saying produces no message, no placeholder, and no alert — and *most* days should be silent.
- **A loop is never touched faster than its own timescale.** Touching is recorded — what Half raised and when — which is a different fact from a loop *moving* and is the record story 8 deliberately left to this story.
- **Nagging is computed, never judged**: a bound derived from the loop's own period, so a days-loop and a years-loop are held to their own clocks rather than a shared cadence.
- **The ladder decides what may be said** (5a), and the context builder decides how (4b). A `behave` belief shapes the surface and is never quoted in it; nothing here re-implements either rule.
- **The surface can actually speak.** A candidate must be reachable from what the product itself writes, not only from a fixture. A feature that is structurally silent in production is not a smaller feature; it is an unshipped one.
- **What the surface is handed is narrowed to what it may use.** Handing it the whole folded state makes every rule it must not consult reachable without an import, a door, or a name a scan can see — the guarantee then rests on nobody having written the obvious line.
- **The day marker records that a message was sent**, not that some loop was raised, and it is stored as the local day it belonged to rather than recomputed later under whatever zone is current.
- **A candidate exists only for a transition the log actually holds.** A planned move whose append failed cites nothing.
- **The ranking unit is the loop's own periods**, and a case must exist where own-periods and raw days rank oppositely — otherwise the unit is an assertion nothing tests.
- **The ceiling is honoured, so aftercare is silent.** A main capped at `behave` receives no mirror, which is 6c's whole purpose and must not need a special case here.
- **Reachability is asked, never assumed** (AD-7). If Half may not send unprompted right now, it does not — and that is silence, not an error.
- **Crisis suspends the surface entirely.** A main in the mode gets nothing unprompted from this path.
- **The choice is deterministic given the log and an injected `now`.** Two builds reading one log pick the same thing or pick nothing.
- **No model call** — the model port exists, and composing the sentence is a later story. This story chooses *what* to say and proves it may be said.

**Ask First:**
- Any change to the one-a-day rule, or to the nagging bound's derivation.
- A second unprompted path that does not go through this one.
- Surfacing anything that cannot cite its origin in the pass.

**Never:**
- No interrupt on irreversibility — that is CAP-10's other half and a different mechanism.
- No model call, no generated prose; the surface is assembled from what the ladder and the context builder already permit.
- No metric surface, no endorsement sampling (AD-21), no trust-balance spend — story 5b.
- No catch-up: a day Half was down is a day it said nothing, and it never says two things later.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Nothing worth saying | A quiet night's pass | Silence; nothing sent, nothing logged as failure | The ordinary case |
| One good thing | A tension that widened overnight | One message, citing it | N/A |
| Two good things | Several candidates | Exactly one is sent | Never two |
| Already sent today | A second trigger the same local day | Nothing | One a day, per main |
| Local day | Two mains in different zones | Each gets their own day boundary | Told zone, never inferred |
| No traceable origin | A candidate that cannot cite the pass | Not surfaced | Never untraceable |
| Nagging, years-loop | A farmland loop raised last month | Not raised again | Its own timescale |
| Nagging, days-loop | A routine raised last month | May be raised | Its own timescale |
| Touch recorded | Any surface | What was raised and when is recorded | Distinct from movement |
| Untouched vs unmoved | A loop Half raised but that has not moved | The two facts stay separate | Never conflated |
| Aftercare | A main capped at `behave` | Silence; no mirror | Through the ladder, not a special case |
| Crisis | A main in the mode | Nothing unprompted | Suspended entirely |
| Unreachable | Half may not send unprompted now | Silence | Never an error |
| Missed day | The process was down | Nothing is sent later | No catch-up, ever |
| Determinism | The same log and `now`, twice | The same choice, or the same silence | No clock below the scheduler |
| One main fails | An unreadable record | Counted; other mains unaffected | Never stops the pass |
| Reachable in production | A belief the product itself wrote | Can become a candidate | Not fixture-only |
| Aftercare by any route | A suppression written from the folded state | A test fails | Not only an import scan |
| Future-stamped touch | A day marker ahead of now | Still counts as spoken | Never a second message |
| Zone changed overnight | The main moves west | One message that day | The stored day, not a recomputed one |
| Erased origin | The tension is expunged before morning | Not surfaced | Never cites what is gone |
| Failed append | A transition that raised | No candidate for it | Cites the log, not the plan |
| Ranking unit | Own-periods and raw days disagree | Own-periods wins | A case must exist |
| Unreadable marker | A stamp the build cannot read | Costs one morning, not all of them | Recoverable |
| Behave material | A `behave` belief is the best candidate | It may shape the surface; its text is never quoted | AD-18 |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; the glossary's *morning surface*, *nagging* and *open loop* entries are normative. AD-7, 9, 18, 27, 28, 30 govern.

**Reference (extraction manifest — mark the row when done):** `gbrain/src/core/calibration/nudge.ts` — the fourteen-day per-pattern cooldown and its feedback-loop prevention. Take the cooldown's *shape*; note that Half's bound is per-loop and derived from that loop's own timescale rather than one global number, which is the difference worth writing down.

**Existing, reused:** `half/loops/timescale.py` (`silence`, the per-loop period — the bound derives from the same periods), `half/loops/ledger.py`, `half/tensions/` (states and widening from 9c), `half/consolidate/pass_.py` (the pass whose output this reads), `half/schedule/` (the tick and the told zone), `half/governance/ladder.py` (what may be said, and the ceiling), `half/context/build.py` (content versus directives), `half/channel/port.py` (`capability_query`, `send`), `half/crisis/gate.py` (the mode that suspends this).

**To create:**
- `half/surface/choose.py` — the candidate set, the nagging bound, and the one choice.
- `half/surface/touch.py` — what Half raised and when; the record and its rules.
- `half/surface/morning.py` — the surface itself: reachability, the ladder, one a day, or silence.
- `half/tests/test_surface.py`, `half/tests/test_nagging.py`.

**To change:** `half/store/ops.py` and `half/store/fold.py` (a touch is an append), `half/consolidate/pass_.py` (the pass produces the day's candidate), `half/__main__.py` (wired by value), `.github/workflows/ci.yml` (a CAP-8 gate whose floor is not the size of its guarantee cases).

## Tasks & Acceptance

**Execution:**
- [x] `half/surface/touch.py` -- the touch record; distinct from movement; an append, never an edit -- AD-3
- [x] `half/surface/choose.py` -- the nagging bound from each loop's own period -- CAP-10, glossary
- [x] `half/surface/choose.py` -- one candidate, deterministic, traceable to the pass, or none -- CAP-8
- [x] `half/surface/morning.py` -- reachability, the ladder, the ceiling, one a day, else silence -- AD-7, AD-27, AD-28
- [x] `half/consolidate/pass_.py` -- the pass produces the day's candidate; crisis suspends it -- CAP-12
- [x] `half/__main__.py` -- wired by value, not by keyword -- reachable
- [x] `.github/workflows/ci.yml` -- a CAP-8 gate with margin that is not its guarantee cases -- gates must not pass vacuously
- [x] `half/tests/test_surface.py`, `half/tests/test_nagging.py` -- one case per matrix row -- I/O matrix

**Acceptance Criteria:**
- Given a night's pass with nothing worth saying, when morning comes, then nothing is sent and nothing is recorded as a failure.
- Given several candidates, when the surface runs, then exactly one message is sent.
- Given a message already sent in the main's local day, when another trigger arrives, then nothing is sent.
- Given a loop raised more recently than its own timescale, when candidates are chosen, then it is not among them; and given a days-loop raised the same distance in the past, then it may be.
- Given any surfaced thing, when it is examined, then it cites the tension, loop transition or ingested item it came from.
- Given a main whose ceiling is `behave`, when morning comes, then nothing is surfaced, without a special case for aftercare.
- Given a main in crisis mode, when morning comes, then nothing unprompted is sent.
- Given that Half may not contact a main unprompted, when morning comes, then it does not, and that is not an error.
- Given days on which the process was down, when it returns, then no message is sent for them and none is queued.
- Given the same log and the same injected `now`, when the choice runs twice, then it is identical.
- Given a `behave` belief as the best candidate, when a surface is built, then its text appears nowhere in the message.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Design Notes

**Why the nagging bound lives here.** It was deferred with CAP-10's interrupt rule, but it is not a governance feature — it is this story's selection rule. *What is worth saying today* and *what may be touched today* are one question, and a surface built without the bound is not a smaller story but a wrong one: it would raise a years-long loop every morning, which the glossary names as the failure.

**Why touching and moving are separate records.** Story 8 recorded when a loop last *moved* and refused to record when Half last *raised* it, because conflating them makes Half's own attention look like the main's progress. The bound needs the second; the ranking needs the first.

**Why most days are silent.** The product's value is the one thing worth saying, and a daily message is the shape every other product in this space already takes. Silence being ordinary — not a degraded mode, not an error — is what makes the message mean something when it arrives.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_surface.py tests/test_nagging.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest -m cap6 -m cap7 -m ad9 -m cap12 -q` -- expected: loops, tensions, the scheduler and crisis intact
- `cd half && uv run --extra dev pytest tests/test_replay.py tests/test_purity.py -q` -- expected: replay exact, fold pure
- `cd half && git status --porcelain` -- expected: clean tree after commit
