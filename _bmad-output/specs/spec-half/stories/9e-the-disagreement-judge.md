---
title: 'Story 9e — The disagreement judge'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: '637b74d'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 9d built everything CAP-7 specifies about *not spending* — the candidate bound, the comparison sets, the cheap filter, the couple ceiling, the per-main judgement budget — and shipped the judgement itself as a seam with no implementation. The composition wires `None`, so a nightly pass considers, filters, ranks, and mints nothing. Story 14 removed the reason to wait: the consultation shape is one module now, not a fourth copy.

**Approach:** Supply the judge. A bounded, capped, breaker-guarded consultation built on `half/model/consult.py`, behind `half/consolidate/port.py`'s one method, wired into the composition root with its own policy.

**The semantic core, which is the whole risk:** a tension is two entries that **disagree where neither is wrong**. That is not a contradiction. *"Means to buy the farmland this year"* against *"has not opened a listing since March"* — both true, pulling against each other, and that gap is the thing Half exists to notice. A contradiction is a different object with a different home: the main saying something false is story 12's correction path. A judge that mints contradictions has not built CAP-7, it has built a worse story 12.

## Boundaries & Constraints

**Always:**
- **The judge answers about the gap, never about the truth.** Two entries that cannot both be true are not a tension. The instructions must make that distinction the question, and a case must show a plain contradiction answering *no*.
- **Three values, honestly produced.** `True` disagreement, `False` no, `None` cannot say. A model that is unsure, degraded, or declining answers `None` — never `False`. The port's own docstring gives the reason: a suite asserting *"nothing was minted"* over both would pass whether the port answered or was never reached.
- **The shape is `half/model/consult.py`'s**, not a fourth copy: the breaker, the caps, the allowlist, the cadence and the alarm come from there. This story supplies policy — its bound, its stand-down, its alarm rate — its labels and its instructions, and nothing else.
- **The bound must fit the pass.** `JUDGEMENTS` consultations at this bound must complete inside the scheduler's per-main timeout with room to spare, and that relation is asserted rather than assumed — story 13a shipped a cross-constant claim in a comment with nothing pinning it.
- **Worldwide.** The two claims arrive in whatever language the main writes, in any script, and may be in *different* ones. No English-prose rubric, no locale, and no assumption that both sides share a language.
- **Nothing durable, nothing quoted.** Claim text goes to the provider and nowhere else: not to the log, a projection, a cache, an error message or a tally (AD-22). What survives a judgement is a verdict and a count.
- **A judgement never costs the pass.** Absent, slow, failing, over budget or raising — the pass completes, that couple is skipped, and the tick reports the main as run.
- The judge reads no clock, opens no store, and cannot be handed a whole main — it receives two `Entry` values built at the store's door.

**Ask First:**
- Any change to `half/consolidate/port.py`'s method, its three-valued verdict, or what an `Entry` carries.
- Any change to `JUDGEMENTS`, the couple ceiling, or the cheap filter.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- No fourth copy of the consultation machinery.
- No minting from `False` or `None`, and no collapsing the two.
- No claim text in any durable artifact, and none in a log line.
- No generation: the judge classifies and never writes.
- Do not touch 9d's bound, the filter, the ceiling, the budget, or 9c's state machine.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| The canonical tension | *"means to buy the farmland this year"* / *"has not opened a listing since March"* | `True` — both true, pulling apart | N/A |
| A plain contradiction | Two entries that cannot both be true | `False` — that is story 12's object, not a tension | Never minted |
| Agreement | Two entries saying the same thing differently | `False` | N/A |
| Unrelated | Two entries about different things | `False` | N/A |
| Cannot say | The model is unsure or declines | `None`, distinct from `False` | Counted apart |
| Unreadable answer | A reply the label set does not contain | `None` | Never guessed |
| Provider absent | No judge wired | The pass completes and mints nothing | 9d's behaviour, unchanged |
| Provider slow | Past the bound | `None` for that couple; the pass continues | Never blocks the pass |
| Provider raises | The call throws | That couple is skipped and billed | Never costs the pass |
| Over the cap | Per-call or per-pass cost exceeded | Refuses rather than overspending | Bounded |
| The breaker | Consecutive failures past the threshold | That main stands down; counted | Recovers |
| The bound fits | `JUDGEMENTS` at this bound | Completes inside the scheduler's per-main timeout | Asserted, not assumed |
| Two languages | The two claims in different scripts | Judged; neither is assumed to be the other's | Never locale-defaulted |
| Any script | Claims in any writing system | Judged, with no English rubric on the path | Worldwide |
| Nothing durable | Any judgement | No claim text in the log, projections, or a log line | AD-22 |
| The tally | A pass of judgements | Counts by verdict; carries no claim | AD-22 |
| Replay | A log of minted tensions | Folds identically; the judge is not in the fold | AD-4, AD-30 |
| Crisis | A suspended main | Never reached — the scheduler refuses before the pass | CAP-12 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-7, AD-9, AD-19, AD-20, AD-22, AD-30 govern this story.

**Reference (extracted from the manifest):** none. The three rows story 9 needed were consumed by 9d.

**Existing, reused:** `half/model/consult.py` (story 14 — the shape), `half/model/port.py` (`Classify`), `half/model/budget.py`, `half/model/tier.py`, `half/consolidate/port.py` (the seam), `half/consolidate/mint.py` (the caller), `half/crisis/classifier.py` (the *pattern* for a bounded classifier with an injected label policy — read it, do not copy it).

**To create:**
- `half/consolidate/judge.py` — the labels, the instructions, the policy numbers, and the `Disagreement` implementation on `consult`'s shape.
- `tests/test_judge.py`.

**To change:**
- `half/__main__.py` — wire the judge, its provider, its tier and its budget; a main with no tier is skipped rather than defaulted (AD-20).
- `.github/workflows/ci.yml` — a CAP-7 judgement gate, margin sized to the subset it protects.

## Tasks & Acceptance

**Execution:**
- [ ] `half/consolidate/judge.py` -- labels, instructions, policy; the shape is `consult`'s -- AD-19
- [ ] the gap, not the truth -- a contradiction answers `no` -- CAP-7
- [ ] the third value -- unsure, degraded and declining all answer `None` -- the port's rule
- [ ] `half/__main__.py` -- provider, tier, budget, counters, shutdown flush -- operable
- [ ] `tests/test_judge.py` -- every matrix row, across scripts -- I/O matrix
- [ ] `.github/workflows/ci.yml` -- the gate, per-case marks, margin stated -- the floor lesson

**Acceptance Criteria:**
- Given two entries that cannot both be true, when the judge answers, then it is `False` — asserted with a case, because a judge that mints contradictions is the failure this story most plausibly ships.
- Given a model that is unsure, degraded, or declining, when the judge answers, then it is `None` and not `False`, and the two are counted apart.
- Given `JUDGEMENTS` consultations at this story's bound, when the arithmetic is checked, then they fit inside the scheduler's per-main timeout with room to spare — asserted as a relation between the constants, not written in a comment.
- Given claims in any script, and in two different scripts, when they are judged, then no English rubric and no locale appears anywhere on the path.
- Given any judgement, when the log, projections and every log line are scanned, then no claim text appears.
- Given a provider that is absent, slow, failing, over budget or raising, when the pass runs, then it completes and the tick reports the main as run.
- Given the repository, when it is scanned, then the consultation shape appears once and this story added no copy of it.
- Given the full suite, when it runs, then it passes offline with the provider stubbed and no network.

## Design Notes

**Why the contradiction case is the acceptance criterion and not a nicety.** "Disagree" is the word a model will read as "contradict", because that is what it usually means. Half means something narrower and stranger: two things that are both true and do not sit comfortably together. Every other clause of this story is machinery that already exists; this is the one place where getting the question wrong produces a product that looks like it works and mints the wrong object. The instructions carry it, and a case proves it, and if the case is hard to write the instructions are not yet right.

**Why `None` cannot be folded into `False`.** 9d's port already argues it and 9d's tests already depend on it: a suite asserting *"nothing was minted"* passes whether the judge said no or was never reached, which is the assertion-identical-either-way shape this project has shipped and taken back twice. The counts keep them apart so each failure has its own case.

**The bound is not free here either.** The pass is off the event loop since 9d's review, and the tick bounds each main — so `JUDGEMENTS` calls at this bound must fit that timeout with margin. Story 13a wrote exactly this kind of cross-constant claim into a comment and pinned it nowhere; `half/voice/gate.py`'s `_check_constants` is the shape to copy, and story 14's `consult` is where the shared half of it now lives.

**What leaves the machine.** Two claims per judgement, to a provider, bounded by the budget 9d already enforces. That is not new in kind — the crisis classifier sends a message and the voice sends claims — but it is worth stating plainly in the module, because *telling a main their messages leave the machine* is an open launch blocker and this widens what that sentence has to cover.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_judge.py -q` -- expected: the judgement path passes
- `cd half && uv run --extra dev pytest -m "cap7 or ad19_guarantee" -q` -- expected: 9d and the shape unbroken
- `cd half && uv run --extra dev pytest -m cap12 -q` -- expected: the crisis path untouched
- `cd half && git status --porcelain` -- expected: clean tree after commit
