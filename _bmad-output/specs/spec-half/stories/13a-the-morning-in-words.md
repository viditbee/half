---
title: 'Story 13a — The morning, in words'
type: 'feature'
created: '2026-09-03'
status: 'done'
baseline_commit: '05ffa01'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Half does not speak. The morning surface sends `Context.render()` straight to the wire, so a main receives `content[b_1]: has not walked that plot since March` — the internal serialization, complete with its label and belief id. This is a launch blocker, and it is the last one that can be closed by building something.

**Approach:** Compose the morning's message through the model port (AD-19) from the `Context` the builder already split, judge the result cheaply, regenerate a bounded number of times, and **fall back to silence rather than to a template** — AD-27 makes sending nothing a first-class outcome, and a hand-written template shipped worldwide is the objection `half/context/channels.py` already records.

**Not in this story:** the turn reply, the question line and the correction line. Each of those must produce *something* — a main who spoke is owed an answer, and CAP-11 requires showing what was removed — so they need a mandatory fallback and a latency budget in front of a waiting main. That is story 13b.

## Boundaries & Constraints

**Always:**
- **AD-18 is enforced at construction, never by filtering generated text.** The generator is *handed* the quotable channel and the directive channel separately: content is what may be said, directives shape how and are never quoted. There is no branch that could re-admit a `behave` claim, because it never enters the prompt as quotable material.
- A verbatim leak check may exist **as a tripwire that fails loudly and sends nothing** — never as a silent redaction. A redaction that quietly cleans the output is how the construction rule rots without anyone noticing.
- **The fallback is silence.** When the judge rejects every attempt, or the provider is absent, slow, failing or over its cap, Half sends nothing and the day is not claimed. Text is composed before the day is claimed, so a failure costs no day and nothing is retried (AD-27, story 10's order).
- **The language is the language the main last wrote in.** Their most recent inbound text is handed to the generator **for language only** and may never enter the quotable channel — asserted structurally, not by convention. This is answering in kind, not inferring a region: no locale, country, timezone or crisis line is derived from it. A main who has never written receives no unprompted message at all (story 2's `capability_query`), so the signal always exists where a morning is possible.
- **Exactly one question, still.** If the context carries a bought question it is composed into the prose as one question; the prose never carries two, and never becomes an interview (CAP-4).
- Bounded and capped as story 6d bounds its consultation: a wall-clock bound, a per-call and per-pass cost cap, a breaker that stands a main down after consecutive failures, and counters an operator can read.
- **No generated text is ever durable** (AD-22). The log records that a morning was sent, never what it said.
- Nothing here runs inside a fold, reads a clock outside the one clock reader, or touches the crisis path.

**Ask First:**
- **Consolidating the consultation machinery.** `half/correction/candidate.py` is already a 51% copy of `half/crisis/classifier.py`, and this story is the third consumer. My reading is that the shape — bound, caps, breaker, tally, holder allowlist — belongs in `half/model/` with the label policy injected. The crisis label set is clinical-review material pinned by digest: it must not acquire that status by inheritance, and any extraction must leave crisis behaviour byte-identical, asserted. Surface this rather than refactoring the crisis path quietly.
- Any runtime dependency beyond the standard library and pinned SDKs.
- Any change to the `Context` shape or to what the builder puts in a channel.

**Never:**
- **No crisis reply is ever generated.** Crisis replies stay joins of reviewed template lines; generating one would void the clinical review that is itself a launch blocker.
- No template in any language as a fallback, and no locale, script or language treated as the default.
- No generated text written to the log, a projection, a cache, a debug artifact or an error message.
- No `behave` or `ask` claim text in the prompt as quotable material.
- Do not build the turn reply, the question line or the correction line — those are 13b.
- Do not change what the morning *chooses*; story 10 owns that. This story changes only how it is said.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| The ordinary morning | Context with quotable content, judge accepts | Prose on the wire; no label, no belief id, no scaffolding | N/A |
| Judge rejects once | First attempt fails the judge | Regenerated within the bound | N/A |
| Judge rejects every attempt | All attempts fail | **Silence**; the day is not claimed | Never a template |
| Provider absent | No model configured for this main | Silence; the day is not claimed | Logged without content |
| Provider slow | Past the wall-clock bound | Silence | Never blocks past the bound |
| Over the cap | Per-call or per-pass cost exceeded | Silence | Refuses rather than overspending |
| Breaker | Consecutive failures past the threshold | That main stands down; counted | Recovers after the interval |
| A `behave` claim leaks | Generated text contains a directive's claim verbatim | **Nothing is sent**, and it is loud | Never silently redacted |
| Quoting | Generated text quotes a claim | Permitted only from the quotable channel | N/A |
| Language | The main last wrote in Thai | The morning is in Thai | Never a default language |
| Language, never quoted | The main's last message is in the prompt | It sets the language and cannot reach the quotable channel | Structural |
| One question | Context carries a bought question | Composed as exactly one question inside the prose | Never two, never a list |
| No question | Context carries none | Prose with no question | N/A |
| Empty content | Nothing quotable and nothing bought | Silence, as story 10 already leaves it | N/A |
| Crisis | The mode is open | No generation at all; the crisis path owns the turn | Structural |
| Durability | Any morning, sent or not | No generated string in the log, projections or errors | AD-22 |
| Replay | A log of sent mornings | Folds identically; no generated text materializes | AD-4, AD-30 |
| Purity | The whole suite | Passes offline with the provider stubbed | AD-2 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-8, CAP-10, AD-18, AD-19, AD-22, AD-27, AD-28, AD-30 govern this story.

**Reference (extracted from the manifest):** the gbrain **voice gate** row — `src/core/calibration/voice-gate.ts`, `DESIGN.md`. Re-targeted three times and finally consumed here. Take the *shape*: generate, judge cheaply, bounded regenerations, then a deterministic outcome rather than an unbounded loop. Take its two arguments: that silently suppressing the surface is never an option, and that mode-specific tuning belongs in the rubric rather than in forked gate implementations. **Reject its per-surface English-prose rubrics** — that is the worldwide objection `channels.py` records — and reject its template fallback, because AD-27 gives Half a better one. Mark the row extracted and record both rejections.

**Existing, reused:** `half/model/port.py` (`Generate`, `Prompt`, `Breakpoint`, `Failure`), `half/model/budget.py`, `half/model/tier.py`, `half/crisis/classifier.py` (the bound/cap/breaker/tally shape), `half/context/channels.py` (`Context`, `quotable()`, `directives`), `half/surface/morning.py`, `half/store/records.py`.

**To create:**
- `half/voice/compose.py` — the generator: a `Context` and a language sample in, one candidate out. No store, no door.
- `half/voice/gate.py` — the judge, the bounded regenerations, and the silence.
- `half/voice/leak.py` — the loud tripwire.
- `half/tests/` — `test_voice.py`, `test_morning_words.py`.

**To change:**
- `half/surface/morning.py` — `_speech` composes instead of rendering. The choice is untouched.
- `half/__main__.py` — wire the composer, its provider and its budget.

## Tasks & Acceptance

**Execution:**
- [ ] `half/voice/compose.py` -- two-channel prompt; directives shape and are never quotable -- AD-18
- [ ] `half/voice/gate.py` -- judge, bounded regenerations, silence -- AD-27
- [ ] `half/voice/leak.py` -- verbatim tripwire that fails loudly -- defence in depth, never enforcement
- [ ] `half/surface/morning.py` -- compose before the day is claimed -- a failure costs no day
- [ ] `half/__main__.py` -- provider, budget, counters, shutdown flush -- operable
- [ ] `tests/test_voice.py` -- the gate, the bound, the caps, the breaker, the leak -- I/O matrix
- [ ] `tests/test_morning_words.py` -- language, one question, silence, no durable text -- I/O matrix
- [ ] `.github/workflows/ci.yml` -- a CAP-8 wire-text gate, margin sized to the subset it protects -- the floor lesson

**Acceptance Criteria:**
- Given an ordinary morning, when it is sent, then the wire carries prose and no label, belief id, or channel scaffolding — asserted against the serialization, not against a fixture's expected string.
- Given a judge that rejects every attempt, when the morning runs, then nothing is sent and the day is not claimed.
- Given a provider that is absent, slow, failing, or over its cap, when the morning runs, then nothing is sent and no exception reaches the scheduler.
- Given generated text containing a `behave` claim verbatim, when it is checked, then nothing is sent and the failure is loud — asserted by a test that fails if the text is silently cleaned instead.
- Given a main whose last message was in any script, when the morning is composed, then the language sample reaches the generator and cannot reach the quotable channel — asserted structurally.
- Given a context carrying a bought question, when the prose is composed, then it contains exactly one question.
- Given any morning, sent or silent, when the log and every projection are scanned, then no generated string appears.
- Given the full suite, when it runs, then it passes offline with the provider stubbed and no network.

## Design Notes

**Why the fallback is silence and not a template.** gbrain's gate falls back to a hand-written string because its surfaces must always render. Half's must not: AD-27 makes sending nothing first-class, and story 10 already ships a morning that is silent most days. A template is also the one thing this product cannot ship worldwide — `channels.py` records the objection to English prose rules, and it applies with more force to the sentence itself than to a rubric. Silence is honest, already modelled, and costs the main nothing but a quiet day.

**Why the leak check must be loud.** AD-18 says enforcement happens at construction, not by filtering generated text, and that is the rule. A verbatim check is therefore not enforcement — it is a smoke alarm on the rule. If it ever silently redacted, the construction guarantee could decay for months while the output looked clean, which is exactly how story 8's firewall and story 6b's send scan shipped broken. It fails the send and says so.

**Why the language sample is not inference.** The standing rule is that Half is told its main's locale and never infers it, because inferring a region from a name or a script is how a product gets someone's crisis line, calendar or holidays wrong. Answering someone in the language they wrote to you in is a different act: it uses no model of who they are, only of what they just said. The rule that keeps the two apart is structural — the sample reaches the generator and can never reach the quotable channel — so a later change cannot quietly turn a language signal into content.

**Compose before claiming.** Story 10 builds the text, then checks reachability, then claims the day, then sends. That order is already correct for this story and must not be reversed: a generation that fails then costs no day, and the main simply gets a quiet morning rather than a spent one. Story 11's review found the mirror-image bug — a spend that happened before the thing it paid for existed — so this ordering deserves a test, not just a comment.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_voice.py tests/test_morning_words.py -q` -- expected: the wire-text path passes
- `cd half && uv run --extra dev pytest -m "cap8 or ad18" -q` -- expected: story 10 and AD-18 unbroken
- `cd half && uv run --extra dev pytest -m cap12 -q` -- expected: the crisis path untouched
- `cd half && git status --porcelain` -- expected: clean tree after commit
