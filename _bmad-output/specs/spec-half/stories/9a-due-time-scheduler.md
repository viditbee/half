---
title: 'Story 9a — The due-time scheduler'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: 'ac255b75beb8492f7a1d96b89fcf80562d16c98f'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing in Half is scheduled. Ingestion is constructed and never run, aftercare waits for the main to speak first, and the nightly pass, the morning surface and the nagging bound are all defined against times that no code can reach.

**Approach:** Deliver AD-9 — a due-time queue, not a cron. Each main carries their own `next_pass_at` at local pre-dawn with jitter; a file-locked tick drains what is due under bounded concurrency; a missed window sends nothing. This is the one module allowed to read a clock, and it injects `now` into everything below. The pass itself is a later story; this is the thing that runs it.

## Boundaries & Constraints

**Always:**
- **A due-time queue, never a global cron.** Timezone spread does not save a user base that shares one timezone; the herd is prevented by per-main due times and jitter, not by hoping.
- **This is the only module that reads a clock.** It reads once per tick and injects `now` downward, so everything beneath it stays pure and replayable (AD-30). The guard catches indirection — an alias bound to the function, a default factory, a `getattr` — not three spellings.
- **Timezone is never inferred, and that is guarded.** A module deriving a zone from a phone prefix, an IP, a locale or the host must fail a test. Story 6b built this scan for region; a rule with a matrix row saying *asserted structurally* and no assertion behind it is worse than no rule, because it reads as settled.
- **The loop that makes the tick recur is tested by running it.** A scheduler that ticks once at boot, dies on the first transient error, or drains a backlog on startup must fail — and the missed-window rule is asserted on every path that can run work, not only the one the tests call directly.
- **The shipped numbers are pinned, not only the injected ones.** A bound, a timeout and a grace window that tests always override are unverified in the product that runs them.
- **A durable write that fails stops the pass.** If the next due time cannot be recorded, the work does not run — otherwise the same window repeats every tick for the whole grace period, which is the storm this story exists to prevent.
- **The window is the promise, and it is verified across the whole timezone database.** A local hour that does not exist on a transition day, or occurs twice, must not push a main outside it. One zone's transition does not stand for every zone's.
- **A timestamp that cannot be trusted is clamped to something the rest of the system accepts**, and never escapes as an exception. A stamp outside the range the store will validate is not a clamp.
- **The tick writes through the same per-main mutex a turn does** (AD-1), asserted behaviourally rather than in a docstring.
- **A gate's floor carries margin that is not the guarantee cases.** Deleting the cases a gate exists for must drop it below its floor.
- **A missed window sends nothing.** No catch-up, no backlog drain, no storm after an outage. A pass that did not happen did not happen.
- **The tick is file-locked**, so two processes cannot drain the same queue, and the single-writer-per-main invariant survives a second worker (AD-1).
- **Concurrency is bounded** and the bound is explicit. A thousand due mains must not become a thousand concurrent passes.
- **Timezone is told, never inferred** — no IP, no phone prefix, no locale guess (the rule story 6b set for region). An unknown timezone gets a defined, *recorded* fallback rather than a silent guess.
- **Due times carry jitter** so that mains sharing a timezone do not share an instant.
- **Work is per main and isolated.** One main's pass failing, hanging or raising must not affect another's, and must not stop the tick.
- **Scheduling state is durable.** A restart does not lose when a main is next due, and does not re-run a pass that already ran.
- **Sending nothing is a first-class outcome** (AD-27). A tick with nothing due is normal and silent, not an error.
- Hibernation is a shipped behaviour, not just a cost lever: an idle main costs nothing.

**Ask First:**
- Any runtime dependency beyond the standard library and pinned SDKs.
- Any change to the concurrency bound or the jitter window.
- Any catch-up behaviour for a missed window.

**Never:**
- No consolidation, no promotion, no salience decay, no tension minting — the later story.
- No model call and no Batch API submission — the model port is its own story.
- No unprompted message to a main — that is story 10, and this story must not be the place that decides to contact someone.
- No second clock reader anywhere in the tree.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Nothing due | A tick with no main due | Nothing runs; not an error | Silent and normal |
| One due | A main past their due time | That main's work runs once | N/A |
| Many due | More due mains than the bound | Bounded concurrency; all eventually run | Never all at once |
| Same timezone | Many mains in one timezone | Due times spread by jitter | Never one instant |
| Missed window | The process was down across a due time | Nothing is sent; the next due time is computed forward | No catch-up |
| Long outage | Many windows missed | Still nothing sent, and no backlog | Never a storm |
| Two workers | A second process ticks concurrently | The lock admits one; the other does nothing | Never two writers for a main |
| Stale lock | A worker died holding the lock | The lock is recoverable without manual action | Never a permanent stall |
| Restart | The process restarts | Due times survive; a completed pass does not re-run | Durable |
| Told timezone | The main has told Half their zone | Due time is their local pre-dawn | N/A |
| Unknown timezone | Nothing told | A recorded fallback is used, and it is visible as a fallback | Never inferred |
| Inferred zone | An IP, phone prefix or locale is available | Ignored | Asserted structurally |
| One main raises | A main's work raises | Logged without content; the tick continues | Never stops the tick |
| One main hangs | A main's work does not return | Bounded; the tick is not held for ever | Never an unbounded wait |
| Hibernating main | An idle main | Costs nothing | N/A |
| Clock readers, any spelling | An alias, a default factory, a `getattr`, a new module | A test fails | Not three spellings |
| Zone inference | A module mapping a prefix, IP or locale to a zone | A test fails | The rule has a guard |
| The recurring loop | Ticks once, dies on error, or catches up at startup | A test fails in each case | Run it, do not read it |
| Advance fails | The next due time cannot be recorded | The pass does not run | Never a repeating storm |
| Every zone | The whole timezone database, across transitions | Every due time inside the window | One zone proves nothing |
| Untrusted stamp | NaN, infinity, negative, absurd | Clamped into the range the store accepts | Never raises |
| Tick and turn | A tick while a turn holds the main's mutex | The tick waits | AD-1, behaviourally |
| Shipped constants | The scheduler the product builds | Its bound, timeout and grace are asserted | Not only injected ones |
| Purity below | Everything the tick calls | Receives an injected `now` | No ambient time |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. AD-1, 9, 26, 27, 30 govern; AD-19 and AD-20 are deliberately out of scope.

**Reference (extraction manifest — row marked ✅ 2026-09-01):** `hermes-agent/cron/scheduler.py` — the file-locked `tick()` pattern. Its `gateway/scale_to_zero.py` note is also relevant and already recorded: a proxy judging idle on *inbound* connections cannot see an in-flight pass and will suspend mid-job.

**Existing, reused:** `half/civil.py` (the validated clockless arithmetic — the scheduler supplies the instant, `civil` does the maths), `half/actor/registry.py` (per-main actors, the mutex, `_reached`), `half/store/store.py` (durable state lives in the log, not beside it), `half/errors.py`, `half/__main__.py` (the composition root, which currently constructs ingestion and never runs it).

**To create:**
- `half/schedule/clock.py` — the one clock reader, and the injected-`now` boundary.
- `half/schedule/due.py` — `next_pass_at`, local pre-dawn, jitter; pure, given an instant and a zone.
- `half/schedule/tick.py` — the file-locked drain under bounded concurrency.
- `half/tests/test_schedule.py`.

**To change:** `half/__main__.py` (run the tick, so the scheduler is reachable in the shipped product), `.github/workflows/ci.yml` (an AD-9 gate and a one-clock-reader gate, each with a real margin).

## Tasks & Acceptance

**Execution:**
- [x] `half/schedule/clock.py` -- the single clock reader; everything below takes an injected `now` -- AD-30
- [x] `half/schedule/due.py` -- local pre-dawn with jitter from a told zone; a recorded fallback when none -- AD-9
- [x] `half/schedule/tick.py` -- file-locked drain, bounded concurrency, per-main isolation -- AD-1, AD-9
- [x] `half/schedule/tick.py` -- a missed window computes forward and sends nothing -- AD-9
- [x] `half/__main__.py` -- the tick runs in the shipped composition, not only in tests -- reachable
- [x] `.github/workflows/ci.yml` -- an AD-9 gate and a one-clock-reader gate, floors with margin -- gates must not pass vacuously
- [x] `half/tests/test_schedule.py` -- one case per matrix row -- I/O matrix

**Acceptance Criteria:**
- Given the repository, when the suite runs, then exactly one module reads a clock and everything it calls takes an injected `now`.
- Given a process that was down across one or many due times, when it starts, then nothing is sent and the next due time is in the future.
- Given more due mains than the concurrency bound, when a tick runs, then no more than the bound run at once and every one eventually runs.
- Given two workers ticking at the same moment, when both run, then one drains and the other does nothing, and no main has two writers.
- Given a worker that died holding the lock, when a later tick runs, then it recovers without manual intervention.
- Given many mains in one timezone, when their due times are computed, then they are spread rather than identical.
- Given a main with no told timezone, when a due time is computed, then a recorded fallback is used and no signal is consulted to guess.
- Given one main whose work raises or hangs, when the tick runs, then other mains still run and the tick still completes.
- Given a restart, when the scheduler resumes, then due times survive and a completed pass does not run twice.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Spec Change Log

- **Review round 1 — the rules held on the paths the tests call, and nowhere else.** `run_forever` is executed by no test: replacing `while True` with a single iteration, re-raising on error, and adding a startup `_catch_up()` that drains every missed main each left all 2002 tests passing, because every missed-window case calls `tick()` directly. `serve` starting the ticker is pinned by a source-string grep, so `ticker.cancel()` inserted after `create_task` is green. Verified defects: eighteen Eastern European zones land at 05:57 local on the spring transition, outside the promised window, while the only DST test walks `America/New_York`, which transitions at 02:00 and cannot catch it; `_advance` swallows every exception and the pass runs anyway, so a failed durable write repeats the same window every tick for the whole grace hour; `stamp()` lets NaN escape as a `ValueError` and clamps to 1969 and 9999, both outside the range the store validates; and the removed `_iso` helper's `OverflowError`/`OSError` guards did not come with it, so a hostile platform date now aborts inbound processing. Unpinned by mutation: `GRACE_SECONDS` at four days, `DEFAULT_BOUND` at 10,000, `DEFAULT_TIMEOUT` at 1e9, `note_pass` bypassing the per-main mutex, `zone_projection` returning the whole ledger record, `DERIVED_VERSION` reverted (which rewrites every main's due time in one tick on upgrade — the herd), the fold's fatal branch for a missing due time, and `_is_contention` returning True (a healthy-looking held tick for ever under descriptor exhaustion). Both new CI floors are sized so that deleting exactly the guarantee cases lands on the floor. **KEEP:** the missed-window rule, the file lock, the bounded concurrency and the per-main isolation all held under properly-anchored mutation — the logic is right and the verification around it was not.

## Design Notes

**Why one clock reader.** Every module built so far takes an injected `now`, which is what makes the fold replayable and the tests deterministic. A scheduler necessarily breaks that — it is the thing that knows what time it is. Confining that to one module keeps the property true everywhere else and makes "who reads a clock" a question with one answer rather than a convention.

**Why a missed window sends nothing.** The natural implementation of a scheduler that was down is to catch up, and for a product whose output is unprompted messages to a person, catching up means a queue of yesterday's thoughts arriving at once. AD-9 makes silence the correct behaviour; this is the story that has to resist implementing the helpful version.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_schedule.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest tests/test_purity.py tests/test_replay.py -q` -- expected: the fold is still pure and replay exact
- `cd half && uv run --extra dev pytest -m cap6 -m cap12 -q` -- expected: loops and crisis intact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — the one place that knows what time it is**

- The single clock reader, and the clamp that lands inside the range the store accepts.
  [`clock.py:1`](../../../../half/schedule/clock.py#L1)

**Each main's own pre-dawn**

- The window resolved in the zone at both edges, checked against its own answer before returning.
  [`due.py:1`](../../../../half/schedule/due.py#L1)

**The drain**

- File-locked, bounded, isolated; a failed durable write stops the pass rather than repeating it.
  [`tick.py:1`](../../../../half/schedule/tick.py#L1)

**Tests that carry the design**

- The tzdb sweep: every zone in the window, and no local day skipped — the second half is what stops a defensive check hiding the bug.
  [`test_schedule.py:1`](../../../../half/tests/test_schedule.py#L1)
