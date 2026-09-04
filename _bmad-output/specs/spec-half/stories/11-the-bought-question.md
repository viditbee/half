---
title: 'Story 11 — The bought question'
type: 'feature'
created: '2026-09-02'
status: 'done'
baseline_commit: 'a72db62'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 5b built the currency, the gates and the spend — and nothing calls them. Today an `ask`-rung belief becomes a `Question(id, topics)` inside `half/context/build.py`, `Context.render()` turns it into a line, and the morning surface puts that line on the wire with no favour spent. CAP-4's central rule is enforced in a package with no production caller, and the questions channel is free.

**Approach:** Make the questions channel *bought*. Mint a question from an `ask`-rung belief, run it through 5b's gates, and let a question reach the context only by being handed in. **The question is delivered on the turn path** — attached to a conversation that already touches its topic — because that is what 5b's topic gate requires and what *"never ping to ask"* means. The morning surface does not ask. Then bound re-asking: derive from the log whether a question was answered, so one the main ignored is not put to them again on the next favour — which is the nag this story exists to prevent.

**Not in this story:** claim derivation (the answer's *content* is not interpreted — story 2's stub already records the reply verbatim as a stated belief) and human prose composition (the rendered wire text is a known launch blocker affecting the content channel equally, and is not a question problem).

## Boundaries & Constraints

**Always:**
- **The questions channel carries only what a favour bought.** Enforced by what `build_context` is *handed*, never by filtering what it emits — story 10's AD-28 lesson, where narrowing the subsystem's input was the only fix that held.
- A question reaches the context **only** through an explicit argument. The argument's default is empty, so every existing caller emits no question and a new caller must opt in. Empty is fail-closed here, which is why a default is permitted at all — unlike `resolve(belief, *, ceiling)`, where a default would fail open.
- **One question per belief**, its id derived from the belief id, so that a re-ask is recognizable rather than a new question each time.
- **The answer state is computed from the log, never stored** (AD-3, AD-30) — the lesson 5b's balance and 9c's decay both carry. No asked-count, no answered flag, no counter on `State`.
- The re-ask bound is **one of the wanting's own periods**, read from the same `PERIOD_DAYS` table `timescale.silence` and `choose.touchable` read, so a days-routine and a farmland loop get different answers from one source.
- **The question is delivered on the turn path, never on the unprompted morning.** Gating on a live conversation and then delivering on a scheduler tick is incoherent, and the tick is where a dormant actor has no strands at all.
- **The favour must have been delivered before this turn began.** A day claimed in the same run may not fund the question it carries — Half never pays for a question with the message that carries it. CAP-4 says *preceded*.
- **A favour is spent only when the question actually reaches the main.** If the built text carries no question line, nothing is spent and no `asked` record is written — the permission is to ask, and an unasked question costs nothing.
- The favour is spent immediately before the question reaches the main, per 5b's `spend` contract.
- Every gate 5b established still runs, in its order, through 5b's own door. This story adds no gate and reorders none.
- Nothing here reads a clock inside a fold; nothing here calls a model or touches the network.

**Ask First:**
- Any change to 5b's gate set, their order, or the `TrustLedger` door.
- Any new op on the store's closed vocabulary.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- **No questionnaire and no interview.** Never more than one question in a single send — not a list, not a follow-up in the same message, not "and also". CAP-4 forbids the surface outright.
- No model call, no generated prose, and **no template strings in any language** — Half ships worldwide, and a hand-written English question is the objection `half/context/channels.py` already records.
- No question text anywhere durable (AD-22). The log holds ids.
- No claim derivation and no interpretation of the answer's content.
- Do not build story 12's correction, do not touch the crisis path, do not alter the ladder or the balance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| The ordinary buy | `ask`-rung belief on a live loop, topic raised, one unspent favour | One question bought; the favour is spent; the question is in the channel | N/A |
| No favour | Same belief, balance zero | No question in the channel; the surface may still send content | Nothing spent |
| Below the bar | Belief on a days-routine, large balance | Never bought, at any balance | Nothing spent |
| Capped | Ceiling lowered to `behave` | No question (AD-28) | Nothing spent |
| Quarantined | The belief is quarantined | No question | Nothing spent |
| Two candidates, one favour | Two `ask`-rung beliefs, balance one | Exactly one bought — the costlier mistake | N/A |
| Never a list | Any state at all | At most one question in a single send | Asserted structurally |
| Answered | Question asked, main replies | Recorded as answered; never asked again | N/A |
| Ignored, inside the period | Asked, no reply, less than one of the loop's periods elapsed | Not asked again; no favour spent | N/A |
| Ignored, a period later | Asked, no reply, one of the loop's periods elapsed | May be asked again, costing another favour | N/A |
| Send fails after the spend | Channel raises after the favour is spent | The favour is spent; the ask is not treated as delivered, so it is not retired by a later unrelated message | Logged without content |
| Crisis between choice and send | Crisis opens after the question is chosen | Nothing asked; the favour is not spent | 5b's re-check refuses |
| Nothing to ask | No `ask`-rung belief | Channel empty; no spend; the turn behaves as it did before | N/A |
| The morning never asks | Any morning, any balance | No question, no spend, no `asked` record — the morning surface is not an asker | Structural |
| Today's own favour | The only delivered favour is this run's own claim | Not askable; a favour must precede the turn | Never self-funded |
| Bought but unrendered | The bought belief resolves above `ask`, or its topic echoes its claim | No question line, therefore no spend and no `asked` record | Never a phantom ask |
| Answered by an unrelated reply | An inbound message on another subject | Does not retire an outstanding question on its own | Never "answered whatever happened" |
| The channel with nothing bought | `build_context` called with no bought question | Emits no `Question` at all | N/A |
| Question text | Any question, ever | Absent from the log, projections, and every durable artifact | AD-22 |
| Replay | A log carrying asks and answers | The answer state folds identically; no counter materializes | AD-4 |
| The belief goes away | A question was answered, then its belief is expunged | The question is gone; no orphan state survives the fold | N/A |
| Worldwide | Any main, any script | No literal question string in any language on any path | Asserted structurally |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-4, CAP-10, AD-3, AD-18, AD-22, AD-27, AD-28, AD-30 govern this story.

**Reference (extracted from the manifest):** none consumed. The gbrain **voice gate** row is targeted at "question composition" and this story composes no text — its generate → judge → bounded-regenerate → deterministic-fallback shape belongs to whichever story solves the wire-text blocker, for the content channel and the question channel together. Re-target that row rather than marking it extracted.

**Existing, reused:** `half/trust/unasked.py` (`Unasked`, `asks_at`, `next_ask`, `UnaskedQueue.spend`), `half/trust/stakes.py`, `half/loops/timescale.py` (`PERIOD_DAYS`), `half/surface/choose.py` (`touchable`'s own-period discipline), `half/context/build.py`, `half/surface/morning.py`, `half/civil.py`.

**To create:**
- `half/questions/mint.py` — an `ask`-rung belief becomes one `Unasked` with a derived id. Pure.
- `half/questions/answered.py` — the answer state, folded from the log: asked, answered, or ignored-and-how-long-ago. Pure, clockless at the fold.
- `half/questions/engine.py` — the composition: mint, gate through 5b, spend, hand the bought question to the context.
- `half/tests/` — `test_questions.py`, `test_bought.py`.

**To change:**
- `half/context/build.py` — a `Question` is emitted only for a belief handed in as bought. This is a behaviour change for existing callers: story 4b's context tests may assert a question appears for an `ask` rung, and they must be re-read rather than mechanically updated.
- `half/actor/runtime.py` — the turn path buys and delivers the question, behind the crisis gate.
- `half/surface/morning.py` — **remove** the buy; the morning surface stops asking.

## Tasks & Acceptance

**Execution:**
- [x] `half/questions/mint.py` -- one question per `ask`-rung belief, id derived from the belief id -- re-asks are recognizable
- [x] `half/questions/answered.py` -- answered / ignored computed from the log; no stored state -- AD-3, AD-30
- [x] `half/questions/engine.py` -- mint, gate through 5b's door, spend, hand over -- CAP-4
- [x] `half/context/build.py` -- `Question` only for a bought belief; empty default, fail-closed -- AD-18, AD-28 shape
- [x] `half/actor/runtime.py` -- the turn offers, builds, renders, then spends immediately before the send -- 5b's spend contract
- [x] `half/surface/morning.py` -- **remove** the buy; the surface cannot reach `half.questions` at all -- review loop 1
- [x] `half/tests/test_questions.py` -- minting, the answer state, the re-ask bound at all four timescales -- I/O matrix
- [x] `half/tests/test_bought.py` -- the channel is bought; never a list; nothing durable -- CAP-4, AD-22
- [x] `.github/workflows/ci.yml` -- a CAP-4 delivery gate, margin sized to the cases it protects -- the floor lesson

**Acceptance Criteria:**
- Given an `ask`-rung belief and no unspent favour, when the surface runs, then no question reaches the main and nothing is spent.
- Given the same belief and one unspent favour, when the surface runs, then exactly one question reaches the main and the favour is spent.
- Given two affordable candidates and one favour, when the surface runs, then exactly one question is sent and it is the costlier mistake.
- Given any state whatsoever, when a send is composed, then it carries at most one question — asserted structurally, not by counting a fixture.
- Given a question that was asked and answered, when a later favour lands, then it is not asked again.
- Given a question that was asked and ignored, when less than one of its wanting's periods has elapsed, then it is not asked again; and when one period has elapsed, then it may be, costing another favour.
- Given a `build_context` call with nothing bought, when the context is built, then it contains no `Question`.
- Given any log, when it is folded, then no asked-count or answered flag materializes on `State`.
- Given the full suite, when it runs, then it passes offline with no model call and no network.
- Given the repository, when it is scanned, then no literal question string in any language exists on the question path.

## Design Notes

**Why the answer state is derived rather than recorded.** Story 5b deferred a sixth gate against re-asking because the log records that a question was *put* and never that it was *answered*, so gating on `asked` alone would permanently silence a question the main merely ignored. That reasoning was right, and its conclusion — that questions need an answer op the way story 6c gave aftercare one — turns out to be avoidable here. `half/actor/runtime.py` already writes every inbound message as a stated-ledger belief, so *responsiveness* is in the log with a timestamp: an `asked` record followed by an inbound assert is engagement, and an `asked` record followed by silence is not.

State this limit plainly in the module: **this recognizes responsiveness, not answering.** A main who replies about something else entirely reads as having answered. That is the honest deterministic bound, it errs toward asking *less*, and buying the stronger version means interpreting the reply — which is claim derivation, deferred with the model port since story 3.

**Why the re-ask bound is the loop's own period.** The nag failure is not "asking twice", it is "asking on a cadence the wanting does not move at". gbrain's nudge cooldown was one global fourteen days, which nags a workout routine and never once reaches a farmland loop; story 10 already rejected that number for `touchable` and read the loop's own period instead. The same table answers here, and the test should sweep one interval across all four timescales and get four different answers — the shape `tests/test_nagging.py` already uses.

**Why `build_context` takes what is bought rather than filtering what it emits.** Story 10 shipped an AD-28 violation because `surface_view` handed the whole `State` to a subsystem and the forbidden branch was writable from data already in hand; the fix that held was narrowing what the subsystem is *given*. The same shape applies: a builder that decides for itself which beliefs deserve a question can always be made to decide wrongly, whereas a builder that can only emit what it was handed cannot. Verify this by mutation — a builder that reads the rung directly must fail a test, not merely look wrong.

**The failed send spends both.** Story 10 claims the day before sending and 5b spends the favour before sending, so a send that raises costs the main both. This is the asymmetry story 10 accepted deliberately (a retry loop costs the one-a-day rule, which is worth more than one message) and 5b inherited. It is already recorded as deferred work; do not fix it here, and do not let a test assert the opposite.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_bought.py tests/test_questions.py -q` -- expected: the CAP-4 path passes
- `cd half && uv run --extra dev pytest -m cap4 -q` -- expected: 5b's gates still pass unchanged
- `cd half && uv run --extra dev pytest tests/test_surface.py tests/test_context.py -q` -- expected: AD-18 and story 10 unbroken
- `cd half && git status --porcelain` -- expected: clean tree after commit


## Spec Change Log

### 2026-09-02 — delivery moved to the turn path (review loop 1)

**Triggering findings.** Three reviewers converged on two defects whose root cause was inside the frozen block, making this an intent gap rather than a patch.

1. *The favour rule was vacuous.* The block froze "spend after the day is claimed". Story 10 claims the day by writing `spoke()`, which sets `sent=True`; 5b's `balance.delivered` counts exactly that. So the spend one step later read a balance including this morning's not-yet-sent message, and a main with **zero** delivered favours was asked a question. Proven directly: with zero favours `note_ask` returns `unaffordable`; after `claim_day` the identical call returns `asked`.
2. *The story gated on a live conversation and delivered on the unprompted broadcast.* 5b's topic gate reads volatile in-process strands, populated only on a conversation turn; the morning surface runs on a scheduler tick where a dormant actor has none. The engine's own docstring quotes *"attach the question to the next conversation that already touches the topic; never ping to ask"*, while the sole asker was the once-a-day unprompted message. Every green test called `talking(registry)` immediately before `run_morning` to manufacture strands a real tick would never have, so the suite could not see it.

**Amended.** Delivery moves to the turn path; the morning surface stops asking. The favour must have been delivered before the turn began. A favour is spent only when the question actually reaches the main. Four matrix rows added, one amended.

**Known-bad state avoided.** A Half that asks every main a question every morning, funded by the morning carrying it, while the rule it quotes forbids exactly that — with a suite that manufactures the one condition production never supplies.

**KEEP.** `half/questions/mint.py`, `answered.py` and `engine.py` survive, as does `build.py`'s `bought` argument and `Context.question` being singular — that last one made "never a questionnaire" a property of the type rather than a fixture count, and must not regress to a tuple. The zero-margin CI gates stay. The mutation-verified guards stay. Story 4b's context cases were re-read individually rather than mechanically updated; keep that work.
