---
title: 'Story 13b — The turn, in words'
type: 'feature'
created: '2026-09-03'
status: 'done'
baseline_commit: '362b57d'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 13a taught the morning to speak. The turn path — the surface a main actually uses — still emits internals. `respond` returns `"noted. has not walked that plot since March"`: an English word bolted to a raw claim. A bought question arrives as `question[b_1] topic: farmland`. A correction arrives as `retract[b_land]: has not walked that plot since March`. All three reach the main on the same wire.

**Approach:** Reuse 13a's composer, gate, leak check and bounds for the turn. Compose the question *into* the prose rather than appending it. Compose the correction reply, and require that it contain the removed claim verbatim — CAP-11's purpose is that the main can **verify** the right thing was removed, not that Half is polite about it. Where generation fails, fall back to **the claim alone, unscaffolded**; silence only when there is no claim to send.

## Boundaries & Constraints

**Always:**
- **13a's machinery is reused, never reimplemented.** One composer, one gate, one leak check, one set of counters. Two renderings of one thing is how a guard that scans one string ends up admitting another.
- **Half may reply without quoting anything, and without holding anything.** Neither an empty quotable channel nor an empty context is a reason to go silent: the composer may produce a reply shaped by the directive channel alone, or by nothing at all, quoting none of it. This is AD-18 working as written — directives shape *how* Half speaks and are never quoted — and the leak tripwire already guards the failure mode. It is what `"noted."` was standing in for.
- **A degraded retrieval never costs the main their reply.** A disabled ledger, a refused query, an unusable strand label and an empty ranked set all degrade *what Half knows*, never *whether Half answers* — `half.actor.runtime._retrieve`'s own invariant, which must hold after this story as before it. This matters most for a main whose retrieval a crisis disabled: it is re-enabled only by an explicit operator action, so a rule that ties the reply to the material would meet exactly that population with unbroken silence.
- **The fallback is the claim alone** — no label, no belief id, no framing word, in any language. It is the main's own words, already in their language, so it needs no template. Silence only when there is nothing at all: no composed reply, no claim, and nothing shaping one.
- **A composed correction reply must contain the removed claim verbatim**, checked before it is sent. Failing that check falls back to the claim alone, which satisfies it trivially. Prose that says *"I've taken that out"* without saying *what* does not show what was removed.
- **The question is composed into the prose, never appended as a line**, and there is still exactly one (CAP-4). A question on its own line is the scaffolding this story exists to remove, and reads as a form.
- **A wall-clock bound protects the waiting main.** Past it, the fallback — which must be reachable with no model call. The turn is never blocked, and no generation failure ever costs the main their reply or their recorded message.
- The main's inbound text sets the language and **may never enter the quotable channel** — the same structural rule 13a establishes, and on a turn the sample is simply the message in hand.
- AD-18 stays enforced at construction; the leak check stays a loud tripwire that refuses, never a silent redaction. On a turn a refusal falls back to the claim, which is quotable by definition.
- **No generated text is durable** (AD-22), and nothing here writes to the log.

**Ask First:**
- Any change to what the turn *chooses*, to what `half.correction` recognizes, or to story 12's rule that a correction turn attaches no bought question.
- Any runtime dependency beyond the standard library and pinned SDKs.
- Any change to the `Context` shape.

**Never:**
- **No crisis reply is ever generated.** Crisis stays a join of reviewed template lines.
- No template in any language, and no locale, script or language as a default.
- No label, belief id, or channel scaffolding on the wire — including in the fallback.
- No generated text in the log, projections, caches, or error messages.
- Do not change the morning surface; 13a owns it.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Ordinary turn | Quotable content, judge accepts | Prose; no label, no id, no scaffolding | N/A |
| Generation fails | Judge rejects every attempt | The quotable claim alone | Never a template |
| Nothing quotable | No quotable content, directives present | A composed reply that quotes nothing | Never silence for a capped main |
| Under an aftercare cap | Every license capped at `behave` for 30+ days | Half stays present on every turn | CAP-12; never silence |
| Retrieval degraded | Disabled ledger, refused query, unusable strand, empty ranked set | A reply is still sent | `_retrieve`'s invariant |
| Crisis-disabled main | Retrieval disabled on crisis entry, not yet re-enabled | A reply on every ordinary turn | CAP-12; never silence |
| Nothing at all | A blank inbound message | Silence | N/A |
| Past the bound | Generation slower than the wall-clock bound | Fallback; the turn is not blocked | Never waits past the bound |
| Provider absent or failing | No provider, or it errors | Fallback | Reply never lost |
| Breaker | Consecutive failures past the threshold | That main stands down to the fallback; counted | Recovers after the interval |
| Correction reply | A belief was removed | Prose containing the removed claim verbatim | N/A |
| Correction prose omits the claim | Generated text lacks the claim | Fails the inclusion check; the claim alone is sent | CAP-11 preserved |
| Correction, erasure | An `expunge` was confirmed | The claim is shown before the body is gone | Ordering asserted |
| Bought question | Context carries one | Composed into the prose as one question | Never two, never a line |
| A question and nothing to say | Context carries a bought question and no quotable content | The question is asked; the prompt is coherent with no may-be-said block | 13a left this state unspecified |
| The question is dropped | A question was bought and the prose asks nothing | The favour is not consumed for a question the main never saw | Never a silent loss |
| Correction turn | A correction acted this turn | No bought question, per story 12 | Unchanged |
| `behave` leak | Generated text carries a directive's claim | Generated text refused, loudly; the claim alone is sent | Never silently redacted |
| Language | The main wrote in any script | The reply is in that language | Never a default |
| Language, never quoted | The inbound text is in the prompt | Sets the language, cannot reach the quotable channel | Structural |
| Crisis | The mode is open | Templated reply; no generation at all | Structural |
| Blank message | Empty inbound | Unchanged from today | N/A |
| Redelivery | The same message twice | Idempotent; one reply, one recorded message | Unchanged |
| Durability | Any turn | No generated string in the log or projections | AD-22 |
| Replay | A log of turns | Folds identically | AD-4, AD-30 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-1, CAP-4, CAP-11, AD-18, AD-19, AD-22, AD-27, AD-30 govern this story.

**Reference (extracted from the manifest):** none new. The gbrain voice-gate row is consumed by 13a; this story reuses what that took and adds nothing from the clones.

**Existing, reused:** `half/voice/` in full (13a), `half/context/channels.py`, `half/model/`, `half/correction/apply.py`, `half/actor/runtime.py`.

**To change:**
- `half/actor/runtime.py` — `respond` composes; `question_line` is absorbed into the composition rather than appended; `_attach_question` and the correction join are re-read in that light.
- `half/correction/apply.py` — `shown()` becomes the **fallback** rather than the primary rendering, and gains the inclusion check its composed replacement must satisfy.
- `half/voice/` — a turn-shaped entry point beside the morning's, sharing the gate, the leak check and the counters.

## Tasks & Acceptance

**Execution:**
- [ ] `half/voice/` -- a turn entry point sharing 13a's gate, leak check, bounds and counters -- one composer
- [ ] `half/actor/runtime.py` -- `respond` composes; the question is composed in, not appended -- CAP-4
- [ ] `half/correction/apply.py` -- the inclusion check; `shown()` demoted to fallback -- CAP-11
- [ ] `half/actor/runtime.py` -- the wall-clock bound and the model-free fallback path -- the waiting main
- [ ] `tests/test_turn_words.py` -- the fallback ladder, the bound, the inclusion check -- I/O matrix
- [ ] `.github/workflows/ci.yml` -- extend the wire-text gate, margin sized to the subset -- the floor lesson

**Acceptance Criteria:**
- Given an ordinary turn, when a reply is sent, then it carries no label, belief id, or scaffolding — asserted against the serialization, not a fixture string.
- Given a provider that is absent, failing, or past the bound, when a main writes, then they receive the claim alone and never lose their reply.
- Given no quotable content and a failed generation, when a main writes, then Half sends nothing rather than scaffolding.
- Given a removal, when the reply is composed, then it contains the removed claim verbatim — and a composed reply that omits it falls back to the claim, asserted by a test that fails if the omission is sent.
- Given a confirmed erasure, when the reply is composed, then the claim is shown before the body is tombstoned.
- Given a context with a bought question, when the reply is composed, then it contains exactly one question and no question line.
- Given generated text carrying a `behave` claim, when it is checked, then it is refused loudly and the claim alone is sent — never silently cleaned.
- Given any turn, when the log and projections are scanned, then no generated string appears.
- Given the full suite, when it runs, then it passes offline with the provider stubbed.

## Design Notes

**Why the correction reply must contain the claim.** CAP-11 exists so the main can see the belief actually change, and story 12's aim — the top-ranked belief above a relevance floor — can still mis-target. The main is the only one who can catch that, and they can only catch it if they are shown the words. Friendly prose that says *"I've taken that out"* is exactly the failure: it sounds better and verifies nothing. The inclusion check makes the requirement a property of what is sent rather than a hope about what was generated, and the fallback satisfies it by construction.

**Why the fallback is the claim rather than silence or a template.** A main who has just written is waiting, so silence reads as broken rather than quiet — the asymmetry that makes 13a's answer wrong here. A template is the one thing this product cannot ship worldwide. The claim is already in the main's own language, because it came from them; sending it unscaffolded degrades to *Half echoes what it knows*, which is honest, rather than to *Half emits its internals*, which is the blocker.

**Why the question is composed rather than appended.** Appending re-creates the scaffolding on the wire and, worse, makes the question read as a form rather than as something said in passing — which is the CAP-4 failure the whole trust currency exists to prevent. A question that arrives as its own labelled line is a questionnaire with one row.

**The state 13a left unspecified.** After story 11's loopback the morning stopped buying questions, so `question_block` is dead on that path and has never been exercised with a real question — and `Voice.compose` admits a context carrying a question with no quotable content, which leaves the prompt with no may-be-said block while the instructions call that block the only thing the model may state. This story is the first caller that reaches it, so it must specify it rather than inherit it. A bought question with nothing to say is a legitimate turn: Half has a favour to spend and something to ask, and no standing to state anything.

**The bound is a different problem here than in 13a.** The morning had no one waiting, so its bound only protected cost. Here it protects a person, and the fallback must be reachable without a model call — so the fallback path is not "what the gate returns on failure" but a branch that never entered the gate at all.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_turn_words.py -q` -- expected: the turn wire-text path passes
- `cd half && uv run --extra dev pytest -m cap11 -q` -- expected: story 12 unbroken
- `cd half && uv run --extra dev pytest -m "cap4 or cap12" -q` -- expected: the currency and the crisis path untouched
- `cd half && git status --porcelain` -- expected: clean tree after commit


## Spec Change Log

### 2026-09-03 — a reply does not depend on quotable material (review loop 1)

**Triggering finding.** The frozen block said *"the fallback is the claim alone; silence only when there is no claim"*, and the fallback is the **quotable** claim. `_QUOTABLE` is `License.ASSERT`, and that rung is rare by design — promotion needs a receipt *and* prior knowledge, so an `assert`-licensed belief under no cap at all still resolves to `ask`. Half therefore went silent on most turns. Worse, CAP-12's aftercare caps every license to `behave` for a minimum of thirty days, so a main who has just been through a crisis would have been met with silence on **every** message, while CAP-12's intent says Half stays present and `tests/test_crisis.py::test_a_reply_is_always_sent` calls going quiet "a failure here, not an outcome". The implementer found this, implemented the block as written rather than working around it, inverted the ladder test that had asserted the opposite, and wrote the conflict into the test, the docstring and the commit.

**Amended.** An empty quotable channel is no longer a reason for silence. The composer may produce a reply shaped by the directive channel alone, quoting none of it — AD-18 unchanged, since directives have always shaped how Half speaks without being quoted, and the leak tripwire already guards the failure. Silence is reserved for a turn with nothing at all. Three matrix rows added, one replaced.

**Known-bad state avoided.** A Half that answers a main in crisis aftercare with a month of silence, and most other mains with silence most of the time, because the only thing it was allowed to say was the one rung it almost never holds.

**Extended, same loop.** The first amendment covered material that exists and may not be quoted; it did not cover material that does not exist. A disabled ledger, a refused query, an unusable strand label or an empty ranked set all produce an empty context, and under the amended rule that was still silence — including for a main whose retrieval a crisis disabled, which is re-enabled only by an explicit operator action. Six safety-net assertions that had read *"a disabled ledger must not cost the main a reply"* were removed during the first build and one was inverted to pin the silence. `_retrieve`'s invariant stands: degradation changes what Half knows, never whether Half answers. Silence on the turn path is now reserved for a blank inbound message.

**KEEP.** The inclusion check and its definition over `shown()`'s own output so the two cannot disagree; the fallback ladder itself; `shown()` reduced to the claim alone; the model-free fallback branch; the 2s turn bound; the counting doubles that assert `calls == 0` rather than raising; the `word-for-word` block and its presence in `scaffolding()`; the erasure ordering (confirmed as a deliberate reversal of story 12 — an erasure is the only removal that cannot be undone, so the confirming turn is the last moment a mis-aim can be caught).
