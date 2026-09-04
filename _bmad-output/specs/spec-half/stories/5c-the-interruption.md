---
title: 'Story 5c — The interruption'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: 'ba3a4c3'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-10 promises that *"an unprompted interruption occurs only when waiting would destroy an option."* Half has one unprompted surface — the morning — and it fires on a **schedule**, not on stakes. Nothing in the product can say *this cannot wait until tomorrow*, and nothing stops it either: the rule that would govern an interruption does not exist, so the first surface that wants one will invent its own.

**Approach:** Build the rule, not the detector. An interruption passes five gates — reachable, not in crisis, under the ceiling, not nagging by the loop's own clock, and **judged as closing** — and every one of them can refuse. The judgement itself is injected as a narrow port.

**What this ships without, deliberately.** Half cannot currently know that an option is closing: a loop carries a timescale and a last movement, a belief carries a claim and its support, and **nothing anywhere carries a horizon**. Detecting one means either a record-shape change or derivation, and bundling either with the rule that governs restraint is the mistake this project has made before. So this story ships a gate whose urgency source is injected and unwired — the shape 9d used and 9e completed. The cost is real and named: story 5b shipped a module with no production caller and waited a story to become real. This does the same on purpose, because **the restraint is the valuable half** — a product that can interrupt before it has a rule for interrupting is worse than one that cannot interrupt yet.

## Boundaries & Constraints

**Always:**
- **Five gates, each able to refuse, and the judgement is not the first.** Crisis, reachability, the ceiling, the nagging bound, then urgency. A main who may not be reached is never judged, which keeps the cheap refusals cheap and the model out of turns it has no business in.
- **An interruption is bounded harder than a morning.** A morning is expected and arrives once a day; an interruption is by definition unexpected. Its bound is its own, stricter than the morning's, and a main who has just had one is not interrupted again for it.
- **The nagging bound is the loop's own period**, read from the same `PERIOD_DAYS` table `timescale.silence`, `choose.touchable` and `questions.answered` read. A days-loop and a farmland loop do not get the same answer.
- **Silence is the ordinary outcome** (AD-27). Most days no interruption is warranted, and a build that never interrupts is a correct build, not a broken one.
- **It speaks through the voice** (13a/13b) — composed prose, the same gate, the same tripwire, the same fallback ladder. An interruption is not a place for a template.
- **Crisis refuses before anything else runs.** A main in the mode is not interrupted, and the mode's own path owns them (CAP-12).
- **The judgement is three-valued** — closing, not closing, cannot say — and only the first may interrupt. Cannot-say and not-closing are counted apart, for the reason 9d's port gives: a suite asserting *nothing was sent* would pass whether the port answered or was never reached.
- Nothing here runs in a fold, reads a clock outside the one clock reader, or touches what the morning chooses.

**Ask First:**
- Adding a horizon, a deadline or an expiry to any record shape.
- Any change to `touchable`, to the ceiling, or to what `capability_query` answers.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- **No interruption without a positive urgency verdict.** Absent, unwired, slow, failing or unsure all mean no.
- No interruption that bypasses the ceiling, the crisis gate, or the nagging bound.
- No template in any language, and no scaffolding on the wire.
- No fifth copy of the consultation machinery.
- Do not build the urgency source, do not change the morning, and do not add a horizon to a record.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| The ordinary refusal | Nothing closing | Silence | The common case |
| A closing option | Reachable, uncapped, not nagging, judged closing | One interruption, composed prose | N/A |
| Unreachable | The platform forbids an unprompted send | No interruption; the judge is never called | Asserted by call count |
| In crisis | The mode is open | No interruption; refused before anything else | CAP-12 |
| Capped | Ceiling lowered to `behave` | No interruption | AD-28 |
| Nagging | Inside the loop's own period since the last touch | No interruption | The loop's clock |
| Just interrupted | An interruption already sent for this | Not repeated | Its own bound |
| Judge says no | Reachable and permitted, judged not closing | Silence | N/A |
| Judge cannot say | Unsure, degraded or declining | Silence, counted apart from *no* | Never collapsed |
| Judge absent | No port wired — the shipped build | Silence, always | Never fatal |
| Judge slow | Past the bound | Silence | Never blocks |
| Judge raises | The call throws | Silence; nothing else is affected | Never fatal |
| Over the cap | Per-call or per-pass cost exceeded | Refuses rather than overspending | Bounded |
| Two loops closing | More than one candidate | At most one interruption | Never a digest |
| What it says | Any interruption | Composed prose; no label, no id, no scaffolding | 13a/13b's voice |
| The fallback | Generation fails | The voice's own ladder, unchanged | 13b |
| Nothing durable | Any interruption | No generated text in the log or projections | AD-22 |
| Replay | A log carrying interruptions | Folds identically | AD-4, AD-30 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-10, CAP-8, CAP-12, AD-9, AD-19, AD-22, AD-27, AD-28, AD-30 govern this story.

**Reference (extracted from the manifest):** check for rows naming 5c or the interrupt. The **gbrain** nudge-cooldown row is already extracted and its lesson applies again here — a global cooldown nags a fast loop and never reaches a slow one — so read what that row records rather than re-deriving it.

**Existing, reused:** `half/surface/choose.py` (`touchable`, the nagging bound), `half/governance/ladder.py` (`Ceiling`), `half/crisis/gate.py`, `half/channel/port.py` (`capability_query`), `half/voice/` (the composer, its gate and its fallback), `half/model/consult.py` (the shape), `half/loops/timescale.py` (`PERIOD_DAYS`), `half/schedule/tick.py`.

**To create:**
- `half/interrupt/port.py` — `Urgency`: one method, three-valued, narrow by construction.
- `half/interrupt/gate.py` — the five gates in order, and the bound.
- `tests/test_interrupt.py`.

**To change:**
- `half/__main__.py` — wire the gate with no urgency source; a deployment with none never interrupts.
- `.github/workflows/ci.yml` — a CAP-10 interruption gate, per-case marks, margin stated.

## Tasks & Acceptance

**Execution:**
- [x] `half/interrupt/port.py` -- one method, three values, no store and no clock -- AD-19
- [x] `half/interrupt/gate.py` -- five gates in order, cheap refusals first -- CAP-10
- [x] the interruption's own bound -- stricter than the morning's -- unexpected costs more
- [x] the voice -- composed prose, the existing ladder -- 13a/13b
- [x] `half/__main__.py` -- wired with no source; never interrupts -- honest default
- [x] `tests/test_interrupt.py` -- every matrix row -- I/O matrix
- [x] `.github/workflows/ci.yml` -- the gate, per-case marks -- the floor lesson

**Acceptance Criteria:**
- Given a main the platform forbids an unprompted send to, when the gate runs, then the urgency judge is never called — asserted by a call counter at zero.
- Given a main in crisis, when the gate runs, then nothing is judged and nothing is sent.
- Given a ceiling of `behave`, when the gate runs, then nothing is sent.
- Given a touch inside the loop's own period, when the gate runs, then nothing is sent — and the period is the loop's, asserted across all four timescales.
- Given no urgency source wired — the shipped build — when the gate runs, then nothing is ever sent.
- Given a judge that answers *cannot say*, when the gate runs, then nothing is sent and it is counted apart from *no*.
- Given two loops judged closing, when the gate runs, then at most one interruption is sent.
- Given an interruption, when it reaches the wire, then it is composed prose with no label, no belief id and no scaffolding.
- Given the full suite, when it runs, then it passes offline with the provider stubbed and no network.

## Design Notes

**Why the rule and not the detector.** CAP-10's sentence is a promise of restraint: *only* when waiting would destroy an option. The valuable half is the *only* — the four refusals that run before anything is judged, and the bound that stops a second interruption. A detector without them is a product that interrupts; the refusals without a detector is a product that does not, which is what Half already is and is the safe direction to be wrong in.

**Why urgency is judged last.** Crisis, reachability, the ceiling and the nagging bound are all free and all local. Judging first would spend a model call on turns that were never going to send, and would let a main in crisis be reasoned about — which CAP-12 forbids more strongly than it forbids sending.

**Why an interruption is bounded harder than a morning.** A morning is expected: it arrives once a day and a main learns its shape. An interruption is unexpected by construction, and its cost when wrong is not one message but the main's confidence that Half only speaks when it matters — the thing every other bound in this product exists to protect.

**What a reviewer should be hardest on.** That the judge is never reached for a main who could not be sent to anyway, asserted by counting calls rather than by a raising double — the failure story 13a shipped, where a double that raises is converted into a legal value two frames up.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_interrupt.py -q` -- expected: the interruption path passes
- `cd half && uv run --extra dev pytest -m cap12 -q` -- expected: the crisis path untouched
- `cd half && uv run --extra dev pytest -m cap8 -q` -- expected: the morning unmoved
- `cd half && git status --porcelain` -- expected: clean tree after commit


## Spec Change Log

### 2026-09-04 — the frozen block contradicted itself on the gate order (review loop 1)

**Triggering finding.** Always #1 enumerated *"Reachability, crisis, the ceiling…"* while Always #6 said *"Crisis refuses before anything else runs."* Both cannot hold, and the implementer resolved it rather than picking the nearest reading silently.

**Amended to crisis first**, which is the resolution it chose and the one this spec's own Design Note already argued for: *"would let a main in crisis be reasoned about — which CAP-12 forbids more strongly than it forbids sending."* A main in the mode must not be reasoned about **at all**, the morning already asks the mode before anything else for that reason, and the enumeration's load-bearing claim — that the judgement is not first — survives either ordering. Verified by mutation: moving crisis below reachability fails `test_the_mode_refuses_before_the_platform_is_even_asked`, and the consequence is asserted rather than assumed — a main both in the mode and unreachable is refused as `crisis` with `channel.queries == []`.

**Two other clauses were wrong and are corrected by the implementation rather than by me.** The matrix's *"per-call or per-pass **cost** exceeded"* is not buildable here: a cost cap in micro-USD needs a budget, a breaker and a tally, which this story's Never list forbids as a fifth copy and which belong to a judge it deliberately does not build. What ships is what the gate can honestly promise — a per-pass judgement-count bound, a per-call wall-clock bound, and silence on every refusal shape a capped judge can produce. And *"stricter than the morning's"* supplied no derivation; the implementation makes it demonstrable — the morning's one-a-day is the main's **civil** day from a stored marker, so two mornings twenty minutes apart across local midnight are both legal, while the interruption's is a **rolling** day from the last one, which refuses exactly that pair and spends no morning marker, so it can never be satisfied by one.
