---
title: 'Story 14 — One consultation, three policies'
type: 'refactor'
created: '2026-09-04'
status: 'done'
baseline_commit: '95d9709'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The bounded, capped, breaker-guarded, counted consultation exists in **three copies** — `half/crisis/classifier.py`, `half/correction/candidate.py` and `half/voice/gate.py`, roughly two hundred lines each. One bug already lives in all three: `_report`'s mutually-exclusive branches suppress the alarm at every hundredth consultation, and story 13a fixed exactly one of them. Story 6d's own corrections — denylist to allowlist, `raised` split from `unreadable` — would now have to be made three times. Story 9e needs a fourth.

**Approach:** Extract `half/model/consult.py` holding the *shape* and nothing else, with each caller supplying its *policy*. Then fix the alarm bug once and demonstrate that fixing it once fixed it everywhere — which is the whole argument for doing this, made checkable.

**This is a refactor.** No capability changes, nothing new reaches a main, and the strongest evidence of success is that assertions do not move.

## Boundaries & Constraints

**Always:**
- **Crisis behaviour is byte-identical, asserted rather than reviewed.** Every digest in `tests/test_crisis_golden.py` is unchanged, and none of its renderings may be re-pinned.
- **The shared module holds no labels and no instructions.** Those are each caller's, and for crisis they are clinical-review material. Verified before writing this spec: the golden file digests templates, plans, the tier-to-action table, the label set, and `signals.*` detection constants — none of the consultation machinery — so the shape may move and that material may not.
- **Shared numbers move; policy numbers stay.** Measured across the three copies: `BREAK_AFTER` (5), `REPORT_EVERY` (100), `ALARM_AFTER` (10), `PER_CALL_MICRO_USD` (100_000) and `PER_PASS_MICRO_USD` (500_000_000) are identical in all three and belong to the shape. `BOUND_SECONDS` (2.0 / 2.0 / 20.0), `BREAK_FOR` (50 / 50 / 20) and `ALARM_RATE` (0.2 / 0.2 / 0.5) differ, and differ *for reasons* — a waiting main against a nightly pass, how long a main stands down, what failure rate is worth an alarm. Those are injected.
- **The label policy is injected, and crisis's asymmetry survives it.** `ACTION_FOR_LABEL` maps every crisis label to `ASK` or to nothing, so a model may widen the question and never enter the mode; that rule is checked at import today and must still be, in `half/crisis`, not in the shared module.
- **The holder allowlist stays an allowlist.** Story 13a's review found a denylist replacement passing because one double happened to carry `classify`; the shared version is swept over method names no denylist would contain.
- **No assertion moves.** Import lines may change; what a test asserts may not. A refactor whose tests had to be rewritten to pass is not a refactor.

**Ask First:**
- Any behaviour change at all, in any of the three callers.
- Any change to a digest in `tests/test_crisis_golden.py`.
- Any change to the crisis label set, the templates, the plans, the tier table, or `signals.*`.

**Never:**
- No new capability, no new surface, no new record, no new op.
- No model call added or removed; no provider rewired.
- Nothing in the shared module may know what a crisis, a correction or a morning is.
- Do not extract `half/consolidate`'s port — 9d deliberately ships no judge, and 9e is where that lands.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| The digests | The whole golden file | Every digest unchanged, none re-pinned | Clinical review intact |
| Crisis, end to end | The escalating-risk suite | Byte-identical replies | Asserted, not eyeballed |
| The label asymmetry | Any crisis label | Maps to `ask` or to nothing; never `enter` | Checked at import, in `half/crisis` |
| Shared numbers | The five identical constants | One definition, three readers | N/A |
| Policy numbers | The three that differ | Injected; each caller keeps its own | Never defaulted in the shape |
| A caller's bound | Each of the three | Unchanged: 2.0, 2.0, 20.0 | N/A |
| The breaker | Consecutive failures at each caller | Stands down and recovers exactly as before | N/A |
| The alarm bug | A wholly failing consultation at the hundredth call | Reported at `error`, in **all three** | The payoff, demonstrated |
| The allowlist | A holder carrying a wider method | Refused, over names no denylist would list | Story 13a's finding |
| The tally | Each caller's counters | Same fields, same values, same flush | N/A |
| Voice's leak rule | A composed morning | Unchanged; the tripwire is the voice's, not the shape's | AD-18 |
| Correction's candidate | An inferred correction | Unchanged; still never acts alone | CAP-10 |
| Assertions | The whole suite | No assertion rewritten to make the refactor pass | The test of a refactor |
| Purity | The shared module | Reads no clock, opens no store, names no domain | AD-30 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. AD-19, AD-20, AD-22, AD-30, CAP-12 govern this story; CAP-12 most of all, because the crisis path is clinically reviewed and this story must not disturb it.

**Reference (extracted from the manifest):** none. This story consumes no clone; it pays down debt three stories created.

**Existing, reused:** `half/model/port.py`, `half/model/budget.py`, `half/model/tier.py`.

**To create:**
- `half/model/consult.py` — the bound, the caps, the breaker, the tally, the holder allowlist, the report and the flush. Policy injected. Knows no domain.

**To change:**
- `half/crisis/classifier.py` — keeps its labels, its instructions, `ACTION_FOR_LABEL` and its three policy numbers; loses the shape.
- `half/correction/candidate.py` — the same.
- `half/voice/gate.py` — the same, keeping its tripwire, its judge and its regeneration loop, which are the voice's and not the shape's.
- `.github/workflows/ci.yml` — the affected floors move with their counts, and no gate's margin grows.

## Tasks & Acceptance

**Execution:**
- [ ] `half/model/consult.py` -- the shape, policy injected, no domain vocabulary -- AD-19
- [ ] `half/crisis/classifier.py` -- policy kept, shape removed, digests untouched -- CAP-12
- [ ] `half/correction/candidate.py` -- policy kept, shape removed -- CAP-10
- [ ] `half/voice/gate.py` -- policy kept, shape removed, tripwire and judge unmoved -- AD-18
- [ ] the alarm fix -- once, in the shape, demonstrated to reach all three -- the payoff
- [ ] `tests/` -- an equivalence case per caller, plus the shared module's own -- I/O matrix
- [ ] `.github/workflows/ci.yml` -- floors moved, margins not grown -- the floor lesson

**Acceptance Criteria:**
- Given `tests/test_crisis_golden.py`, when the suite runs, then every digest is the one that was there before this story, and none was re-pinned.
- Given each of the three callers, when its bound, breaker, caps, tally and allowlist are exercised, then each behaves exactly as it did at `95d9709` — asserted per caller, not inferred from a green suite.
- Given a wholly failing consultation reaching its hundredth call, when the report fires, then it is at `error` for **all three** callers — and a test proves it was one fix, not three.
- Given the shared module, when it is scanned, then it names no crisis label, no correction meaning, no morning, and no instruction text.
- Given the whole diff, when it is read, then no assertion was changed to make the refactor pass — only imports and construction.
- Given the full suite, when it runs, then it passes offline with no network.

## Design Notes

**Why the digest question had to be settled first.** The deferred entry recording this work set a condition: the shared module must hold no labels, no instructions and no numbers, or `test_crisis_golden.py`'s pin becomes a pin on a base class and means nothing. Checking what the golden file actually digests relaxes one third of that: it pins templates, plans, the tier-to-action table, the label set and `signals.*` — the clinical content — and none of the consultation machinery. So the labels and instructions must stay put, and the five identical operational numbers may move without weakening anything the clinician signed.

**Why the payoff is a test and not a diff.** The argument for this refactor is that a correction made once should reach every caller, and that argument is worth nothing as prose. The alarm bug is the demonstration: it exists identically in three places, one was fixed in story 13a, and after this story fixing it in the shape must fix it in all three — with a case per caller proving the report fires at `error`, so the claim is checkable by whoever reads this next.

**The one thing this story could break and no test would notice.** A refactor is uniquely dangerous when its own tests are rewritten to fit it. The rule is that assertions do not move; if one has to, that is a behaviour change wearing a refactor's clothes, and it is Ask First rather than a judgement call.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_crisis_golden.py -q` -- expected: every digest unchanged
- `cd half && uv run --extra dev pytest -m cap12 -q` -- expected: the crisis path unmoved
- `cd half && git diff 95d9709 -- tests/ | grep -E '^[-+] *assert'` -- expected: empty
- `cd half && git status --porcelain` -- expected: clean tree after commit
