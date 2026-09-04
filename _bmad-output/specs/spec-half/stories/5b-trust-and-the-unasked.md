---
title: 'Story 5b — The trust balance and the unasked queue'
type: 'feature'
created: '2026-09-02'
status: 'done'
baseline_commit: '54a529e58044aa11aa2112019e1e8a802b46d66f'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Half can now say one thing a morning and cannot ask anything. CAP-4 forbids a question that was not preceded by a delivered favour, so the question engine cannot be built until the currency exists — and CAP-4 is also what would promote a belief above `behave`, which is why story 10 can choose something to say and is not permitted to say it.

**Approach:** Build the currency and the queue that spends it. A trust balance **computed from the log**, earned on a delivered favour and spent on a question; an unasked queue of clarifying questions gated twice — by **stakes**, whether acting on a wrong belief would cost more than the interruption, and by **the favour rule**, whether Half has just given. The unsaid queue is its own story.

## Boundaries & Constraints

**Always:**
- **The balance is computed from the log, never stored as a counter.** A counter a path increments makes state depend on something other than the log, which is the AD-30 violation story 4 avoided for salience and 9c avoided for decay.
- **A favour is delivered, not endorsed.** Whether it landed is AD-21's sampled endorsement and is not this story's; earning happens when something reached the main.
- **Half never asks without having just given** (the glossary's rule). The favour is spent by the asking, so the same favour cannot buy two questions.
- **Stakes decide whether a question is worth asking; the favour decides whether it may be asked now.** Both gates, in that order — a question that fails on stakes is not merely deferred, it is not worth asking at all.
- **A question is attached lazily to a conversation already touching its topic**, never raised cold. An interruption to ask is a different mechanism and is not this story's.
- **An unspent balance is a defect, and therefore visible.** A balance that only ever accumulates means Half is hoarding permission it was given to use; the number is inspectable so that can be seen rather than inferred.
- **Nothing here asks anything.** This story holds questions and decides whether one *may* be asked; the engine that composes and delivers them is story 11.
- **A question spends the balance only when it is actually asked**, never when it is queued, considered, or refused.
- Nothing here reads a clock, the network, or a model; `now` is injected and the fold stays pure (AD-30).
- The ladder still decides what may be said (5a) and the ceiling still caps it (AD-28) — a question about a quarantined belief is not askable, and nothing here re-implements that rule.

**Ask First:**
- What counts as a delivered favour, beyond an unprompted message that reached the main.
- Any change to the stakes rule, or any number in it.
- A second path that spends the balance.

**Never:**
- No unsaid queue and no release conditions — its own story.
- No question composition, no delivery, no onboarding interview — story 11, and CAP-4 forbids a questionnaire outright.
- No interrupt on irreversibility — CAP-10's other half.
- No endorsement sampling (AD-21), and no metric surface.
- No model call.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| A favour delivered | An unprompted message reached the main | The balance earns | From the log |
| A favour undelivered | The send failed or nothing was sent | Nothing is earned | Delivery, not intent |
| Balance computed | The same log and `now`, twice | The same balance | Never a stored counter |
| No favour yet | A question with high stakes, nothing given | Not askable | The favour rule |
| Favour given | A question with high stakes, a favour delivered | Askable | N/A |
| Same favour twice | Two questions, one favour | One is askable | A favour buys one question |
| Low stakes | Acting wrongly would cost little | Not askable at any balance | Stakes first |
| Topic not raised | A question whose topic the main has not touched | Held, not asked | Attached lazily |
| Topic raised | The main touches the topic | Becomes eligible | N/A |
| Quarantined subject | A question about a quarantined belief | Not askable | 5a decides, not this story |
| Ceiling at `behave` | A capped main | Nothing is askable | AD-28, no special case |
| Queue depth | Several questions held | Inspectable | It is a signal |
| Unspent balance | Favours delivered, nothing asked | Visible as unspent | A defect, not a virtue |
| Spend on ask | A question is asked | The balance falls once | Never on queueing |
| Refused question | A question considered and refused | The balance is unchanged | Never a silent spend |
| Replay | A log of favours and asks | The same balance after rebuild | N/A |
| Crisis | A main in the mode | Nothing is askable | Suspended |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; the glossary's *trust balance*, *unasked queue* and *the favor buys the question* entries are normative. AD-3, 26, 28, 30 govern; AD-21 is deliberately out of scope.

**Reference (extraction manifest — mark the row when done):** `gbrain/src/core/calibration/voice-gate.ts` and its `DESIGN.md` — the cheap judge rejecting academic tone. Take it only if it genuinely serves the stakes rule; if it does not, mark the row studied rather than extracted, and say why.

**Existing, reused:** `half/surface/touch.py` (a delivered surface carries `sent`, which is what a favour is read from — story 10 separated *raised* from *sent* precisely so a raise that marks no day also earns nothing), `half/governance/ladder.py` (`permitted`, the ceiling), `half/store/fold.py` and `ops.py` (a new op, if one is needed — a spend is an event), `half/civil.py` (injected `now`), `half/actor/registry.py` (the per-main door), `half/crisis/gate.py` (the mode that suspends this).

**To create:**
- `half/trust/balance.py` — the balance, computed from the log.
- `half/trust/stakes.py` — whether a question is worth its interruption.
- `half/trust/unasked.py` — the queue, its two gates, and what spending looks like.
- `half/tests/test_trust.py`, `half/tests/test_unasked.py`.

**To change:** `half/store/ops.py` and `fold.py` (the spend event), `half/actor/registry.py` (the door), `.github/workflows/ci.yml` (a CAP-10 gate whose floor is not the size of its guarantee cases).

## Tasks & Acceptance

**Execution:**
- [x] `half/trust/balance.py` -- earned on a delivered favour, computed from the log -- AD-30
- [x] `half/trust/stakes.py` -- whether acting on a wrong belief costs more than the interruption -- glossary
- [x] `half/trust/unasked.py` -- the queue and its two gates, in order -- CAP-4, CAP-10
- [x] `half/trust/unasked.py` -- a favour buys one question; spending happens on the ask -- the glossary's rule
- [x] `half/store/ops.py`, `half/store/fold.py` -- the spend as an append -- AD-3
- [x] `half/actor/registry.py` -- the per-main door, narrowed to what this needs -- story 10's lesson
- [x] `.github/workflows/ci.yml` -- a gate with margin that is not its guarantee cases -- gates must not pass vacuously
- [x] `tests/test_trust.py`, `tests/test_unasked.py` -- one case per matrix row -- I/O matrix

**Acceptance Criteria:**
- Given the same log and the same injected `now`, when the balance is computed twice, then it is identical and no counter was read.
- Given an unprompted message that reached the main, when the balance is computed, then it earned; and given one that was not sent, then it did not.
- Given one delivered favour and two questions that both pass stakes, when they are considered, then exactly one becomes askable.
- Given a question whose stakes are below the bar, when any balance is available, then it is not askable.
- Given a question whose topic the main has not raised, when it is considered, then it is held rather than asked.
- Given a question that is considered and refused, when the balance is computed, then it is unchanged.
- Given a main whose ceiling is `behave`, when questions are considered, then none is askable, without a special case for the ceiling.
- Given a main in crisis mode, when questions are considered, then none is askable.
- Given favours delivered and nothing asked, when the balance is inspected, then the unspent amount is visible.
- Given a log of favours and asks, when the store is rebuilt, then the balance matches.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Design Notes

**Why the balance is computed rather than counted.** Story 4 made salience computed and 9c refused to build decay as a stored counter, both for AD-30: two builds folding one log must agree. A trust balance is the same kind of quantity, and the tempting implementation — increment on delivery, decrement on ask — is the one that breaks replay the first time a pass runs twice.

**Why stakes come before the favour.** A question that is not worth its interruption should never be asked, whatever the balance; ordering the gates the other way would let a large balance buy a worthless question, and the glossary is explicit that an unspent balance is a defect rather than something to spend for its own sake.

**Why nothing here asks.** CAP-4 forbids an onboarding interview and requires questions to arrive inside a conversation already touching the topic. Composing and placing them is story 11's problem; this story decides only whether one *may* be asked, which is the part the ladder and the currency between them determine.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_trust.py tests/test_unasked.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest tests/test_replay.py tests/test_purity.py -q` -- expected: replay exact, fold pure
- `cd half && uv run --extra dev pytest -m cap8 -m cap12 -m cap6 -q` -- expected: the surface, crisis and loops intact
- `cd half && git status --porcelain` -- expected: clean tree after commit
