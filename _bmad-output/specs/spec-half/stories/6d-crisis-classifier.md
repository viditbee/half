---
title: 'Story 6d — The crisis classifier'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: '733fbcaf39e263d68416a4b22b9e6025361c8e0a'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/brainstorming/brainstorm-crisis-protocol-2026-08-30/brainstorm-intent.md'
  - '{project-root}/_bmad-output/specs/spec-half/stories/6a-crisis-switch-and-moment.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Crisis detection is an English phrase table. It returns nothing for `kms`, `unalive myself`, `im sucidal`, `i've written a note`, `i'm done.` and every non-English phrasing, because a table fires only on what someone thought to write down and the ways a person says this are not enumerable. That inverts the companion's asymmetry principle in the one place a miss is unrecoverable.

**Approach:** Add a model classifier that widens **ASK** — the cheap, reversible action — while the table keeps **ENTER** so the safe word and an explicit disclosure never depend on a network. The classifier decides and never writes: replies stay entirely templated. Uncertainty asks; unavailability falls back to the table and is counted.

## Boundaries & Constraints

**Always:**
- **The model decides; it never writes.** The classifier holds an object with no way to produce text, and every reply a main receives in the mode remains a join of reviewed template lines (6a).
- **A main asked in their own language can answer in it.** Widening the question in every script while confirmation stays English-only is worse than not asking: Half notices distress, asks repeatedly, and the intervention never arrives for exactly the population this story exists for. Recall and confirmation move together or neither moves.
- **A classification never delays another main's turn.** The bound protects the turn it is on; it must not become every main's latency, and the safe word must be answered without waiting behind anyone else's provider call.
- **A boot cannot fail on anything in this story.** Reading a credential, building a provider, constructing the classifier — every failure leaves that main unequipped and the process running, because a crisis subsystem that refuses to start takes the offline safe word down with it.
- **No path puts the main's words in a log, including an exception's own text.** A provider quotes the request it rejected; carrying the class of a fault is the whole of what may cross.
- **A turn that already carries sensitive content Half asked for does not also leave the machine.** A safety plan is dictated by the main and names people and numbers; classification cannot change what that turn does, so it is not sent.
- **Wiring is asserted by value.** A test that a keyword is present passes when its value is `None`.
- **The safe word and an explicit disclosure never touch the network.** They are decided by the table, offline, with the provider down. The unconditional escape hatch stays unconditional.
- **The classifier widens `ASK`, never `ENTER`.** Entering carries a durable thirty-day cap, so a model may not impose one. What the model can do is make Half ask, which costs a moment of awkwardness and is reversible.
- **Uncertain and unavailable are different, and are handled differently.** A model that ran and is unsure means **ask**. A model that did not run means **fall back to the table**, recorded — because asking every main about suicide during an outage is its own harm.
- **A fallback is counted and visible.** If the classifier is failing, an operator can see the rate; a silent degradation of the recall this story exists for is the worst outcome.
- **This is content egress, on most turns.** The main's message leaves the machine to be classified. Nothing else does: no ledger, no beliefs, no history, no identifiers beyond what the call needs. This is the first such egress in the product and it is stated here, not discovered.
- **Nothing is written about the message.** No belief, no claim, no stored classification — 6a's rule that a crisis turn records nothing holds, and a classified non-crisis turn records nothing extra either.
- **The turn is bounded.** A slow or hanging classifier must not hold a main's reply; the bound is explicit and exceeding it is an unavailability, not a crisis.
- **One classification per turn at most**, inside the model port's budget, and never when the mode is already open.
- **Never gated by tier** (CAP-12), and identical for a free or lapsed main.
- Detection quality is a clinical-review item, not an engineering one — the label set and the prompt go to the reviewer with the templates.

**Ask First:**
- Any change to the label set, or to what a label permits.
- Sending anything beyond the message text to the provider.
- Letting a model decision reach `ENTER`.

**Never:**
- No generation anywhere in this story — the classifier's holder has no generate method (AD-19).
- No prompt content, completion, or main's words in any log (AD-22).
- No belief recorded about the main or about a third party (CAP-12).
- No replacement of the table: it remains the offline floor, and removing a phrase from it is still an Ask-First change.
- **A green suite is not clinical review**, and this story's whole subject is detection quality.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Safe word | The documented phrase | Enters, with no model call made | Offline, always |
| Explicit disclosure | A first-person statement the table knows | Enters, with no model call made | Offline, always |
| Table finds nothing, model sees risk | `kms`, `unalive myself`, `im sucidal` | Half asks | Never enters on a model's word |
| Non-English | Distress in any language the table lacks | Half asks | The gap this story exists for |
| Preparatory | `i've written a note`, `i won't be here tomorrow` | Half asks | N/A |
| Model uncertain | The model ran and is unsure | Half asks | Doubt is cheap |
| Model unavailable | Transport failed, refused, over budget | The table's answer stands, and the fallback is counted | Never asks everyone |
| Model slow | Past the bound | Treated as unavailable | Never holds the reply |
| Slow model, other mains | A hanging provider and a queue | No other main's turn is delayed; a safe word is immediate | Never everyone's latency |
| Answer in any language | The main confirms in the language they were asked in | Recognised | Confirmation follows recall |
| Provider error text | An error quoting the rejected request | The class only reaches the log | Never the main's words |
| Corrupt credential | An unreadable key file at boot | That main is unequipped; the process starts | Never a dead safe word |
| Safety-plan turn | An intake or a request | Not classified, not sent | Already sensitive by design |
| Cancellation | The turn is cancelled mid-call | The loop survives | Never ends the inbound loop |
| Wiring | The shipped composition | The runtime holds the classifier `build` made | By value, not by keyword |
| Oversized message | A message past the per-call ceiling | Refused before the transport is touched | Counted as a fallback |
| Model returns prose | Anything outside the label set | Treated as unavailable | Never parsed as a decision |
| Mode already open | A held main | No classification is made | One call per turn at most |
| Ordinary message | No risk | Nothing happens; nothing is recorded | N/A |
| Third party | Risk about somebody else | 6a's behaviour, unchanged; no belief about them | Unchanged |
| Egress content | Any classified turn | The message text only leaves | No ledger, no beliefs |
| Logs | Any classification | No message text, no completion, no label rationale | AD-22 |
| Records | Any classified turn | No belief is written | CAP-12 |
| Tier | A free or lapsed main | Identical behaviour | Never gated |
| Reply | Any crisis turn | Still a join of reviewed template lines | 6a intact |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; 6a's frozen block still governs the mode, the templates and the never-list. AD-19, 20, 22 and CAP-12 apply.

**Existing, reused:** `half/model/anthropic.py::AnthropicClassifier` (public surface is exactly `classify` — that is the guarantee this story rests on), `half/model/port.py` (`Failure`, its four kinds and ten reasons, all closed enums with no free-text field), `half/model/budget.py` (`Spend.hold`), `half/crisis/signals.py` (`assess`, the tiers, the actions — the offline floor), `half/crisis/gate.py` (the entrypoint; `_decide` is where a second opinion belongs), `half/crisis/respond.py` (`Assessment` carries no text — keep it that way).

**To create:**
- `half/crisis/classifier.py` — the label set, the call, and the mapping from outcome to action.
- `half/tests/test_classifier.py`, and new cases in `half/tests/test_redteam.py`.

**To change:** `half/crisis/gate.py` (consult the classifier when the table finds nothing), `half/__main__.py` (wire it, so it is reachable in the shipped product), `.github/workflows/ci.yml` (extend the CAP-12 gates; the classifier is guarantee surface).

## Tasks & Acceptance

**Execution:**
- [x] `half/crisis/classifier.py` -- the label set and the outcome-to-action mapping -- widens ASK only
- [x] `half/crisis/classifier.py` -- uncertain asks; unavailable falls back to the table and is counted -- the two are different
- [x] `half/crisis/gate.py` -- consulted only when the table finds nothing and the mode is closed -- one call per turn
- [x] `half/crisis/gate.py` -- a bound on the call; exceeding it is unavailability -- never holds a reply
- [x] `half/__main__.py` -- wired into the shipped composition -- reachable, not test-only
- [x] `.github/workflows/ci.yml` -- classifier cases under the CAP-12 gates, floors with margin -- gates must not pass vacuously
- [x] `half/tests/test_classifier.py` -- one case per matrix row -- I/O matrix
- [x] `half/tests/test_redteam.py` -- the escalating suite run with the classifier present and absent -- both paths

**Acceptance Criteria:**
- Given the safe word or an explicit disclosure, when it is handled, then the mode is entered and no model call is made.
- Given a message the table returns nothing for and the model reads as risk, when it is handled, then Half asks and does not enter.
- Given any model outcome whatsoever, when it is handled, then the mode is never entered on the model's word alone.
- Given a model that is unavailable, refused, over budget, slow or returns something outside the label set, when it is handled, then the table's answer stands and a fallback is counted.
- Given a model that ran and is uncertain, when it is handled, then Half asks.
- Given a main already in the mode, when a message arrives, then no classification is made.
- Given any classified turn, when the store is examined, then no belief was written.
- Given any classified turn, when the logs are scanned, then no message text, completion or rationale appears.
- Given the classifier present and absent, when the escalating red-team suite runs, then no step produces method content and the mode never lapses in either configuration.
- Given the repository, when the suite runs, then the classifier's holder has no way to produce text, and it reaches no network in tests.

## Spec Change Log

- **Review round 1 — the story widened noticing and left acting in English.** Verified: `is_affirmative` recognises `yes`/`yeah` and refuses `sí`, `हाँ`, `はい`, `oui`, `是的`, so a non-English main is asked, answers in their own language, is not understood, and is asked again next turn — for ever. They never reach `ENTER`, so the warm handoff, the crisis-line door, the ceiling drop and aftercare never arrive, for exactly the population this story exists to serve. Also verified: a hanging provider makes the inbound loop serial at `BOUND_SECONDS` for everyone — a safe word from a second main was answered ten seconds late, behind another main's classifier waits, which undoes 6a's offline-immediacy guarantee. A provider error quoting the rejected request puts the main's words in a log through `logger.exception`, and neither log guard sees it. A corrupt credential file raises `StoreError`, which `except ModelError` does not catch, killing the boot and the offline safe word with it. `second=None` in `serve` passes the wiring test, which asserts a keyword's name and never its value — the scheduler's grep bug in AST clothing. `PER_CALL_MICRO_USD` can be loosened five-thousand-fold with the suite green, after which a megabyte of a main's text goes to the provider whole. A safety-plan intake — clinician name, contact name, phone number — is classified before `_plan_turn` sees it. `CancelledError` escapes `consult`, which catches `Exception`. And the `cap12_classifier` floor's entire margin is the twelve mutation-guard cases, so they can be deleted together with the import-time check that stops a model entering the mode. **KEEP:** the import-time refusal itself, `SecondOpinion`'s narrow surface, the table deciding `ENTER` offline, and 6a's forbidden-import scan, which was verified byte-identical rather than narrowed.

## Design Notes

**Why the model cannot enter.** The recorded intent said *fail toward entering*, written when entering was the only action Half had. After 6a split asking from entering, entering means a durable thirty-day cap — so a model outage that failed toward it would govern mains for a month at a time, and a false positive would do it for a film. The faithful version of that intent is to fail toward the *responding* side, which is now asking.

**Why unavailable is not uncertain.** Both are "no answer", and treating them alike picks one harm or the other: ask on every outage and Half interrogates everyone about suicide whenever the provider is down; fall back on genuine doubt and the recall this story exists for is lost. They are separated, and the fallback is counted so the difference is visible in production.

**Why the table stays.** It is the offline floor and the only path to entering. A model is a recall instrument here, not an authority — and the safe word documented at onboarding must work when nothing else does.

## Build Notes

**Four labels, not three, and the fourth decides nothing.** The set is
`main_at_risk` · `unsure` · `another_at_risk` · `no_risk`, and only the first
two act — both by asking. `another_at_risk` exists so a message about a
frightened friend has somewhere to go other than `main_at_risk`; its action is
nothing at all, because 6a decides the third-party path from the table on the
main's own words and a sentence telling a main that somebody they love is in
danger is not one to author on a model's inference. **That it acts on nothing
is on the reviewer's list**, not settled here: the companion says a third-party
mention raises vigilance, and 6a recorded vigilance as unimplemented because
nothing consumes it. The set and the instructions are digested in
`test_crisis_golden.py` beside the templates.

**The English phrases the Intent names were already the table's** — confirmed
by the author. `kms`, `unalive myself`, `im sucidal`, `i've written a note`,
`i'm done.` and `s u i c i d a l` all ask today, added in 6a's own review
round. They are pinned here *as asking* so the record stays accurate about what
the model is for. The gap it actually closes — verified as a gap before any case
rests on it — is non-English distress and unlisted preparatory phrasings.

### Review round 1

**Recall and confirmation now move together.** `is_affirmative` held nine
English spellings, so a main asked in their own language answered in it, was
not understood, had the question abandoned, and was asked again next turn — for
ever, never reaching `ENTER`, so the handoff, the door, the ceiling drop and
aftercare never arrived for exactly the population this story serves. The fix is
a **widened table**, 34 phrases to 104, none removed — deliberately not a second
classification. Two reasons: the ways to say *yes* are very nearly enumerable
where the ways to say *I want to die* are not, and confirmation is on the
entering path, which must be decided offline with the provider down. Letting a
model decide it would put a durable thirty-day cap behind an outage and behind a
mislabel, which the Ask-First list names. Four candidates were tried and dropped
because a false yes here is that cap: `जी` is a yes *and* a Hindi honorific, so
*"नहीं जी"* — "no, sir" — read as yes; `так` is Ukrainian yes and Russian "so";
`أجل` is a formal yes and an everyday "for the sake of"; `jo` is a Nordic yes
and an English name. **Two limits are named rather than hidden:** in unspaced
scripts the tokenizer cuts on spaces, so `はい` is recognised and `はい、そうです`
is not — the safe direction, and closing it means giving the crisis tokenizer
the index's cluster logic, which changes every table; and `sim` is the closest
call in the set, kept because Portuguese is too large to drop over a SIM card.
Extending the table is a clinical-review item with a native speaker.

**The inbound loop is now per main.** A hanging provider made the bound
everyone's latency: measured, a second main's **safe word** was answered ten
seconds late behind turns that were not theirs, which is 6a's offline guarantee
holding only for whoever is first in the queue. Turns are dispatched to a FIFO
worker per main; per main it is exactly what it was (one at a time, in order,
through the same mutex), and across mains they no longer touch. **The cost is
stated:** the transport commits its offset when the loop asks for the next
update, so at-least-once now means *accepted for its main* rather than
*finished*, and a hard crash can lose at most `QUEUE_DEPTH` turns per main. The
trade is a guarantee about crashes against a guarantee about the safe word.
`BOUND_SECONDS` also dropped from 5.0 to 2.0, since five was the whole of AD-23's
acknowledgement window.

**A circuit breaker, counted in turns.** After five consecutive fallbacks a
main's classifier stands down for fifty turns, so an outage stops costing every
turn the full bound and another doomed request. Per main, because one main's
provider says nothing about another's, and in turns because nothing under
`half/crisis` may read a clock.

**No traceback is logged anywhere under `half/crisis`.** A provider quotes the
request it rejected, so `logger.exception` put the main's own words in a log
through the traceback — and neither guard saw it, because the AST scan reads
arguments and the behavioural test used a `Failure` value, which never raises.
All nine call sites in the package now log the fault's class and nothing else,
including the three inherited from 6a/6b/6c where the text would have been a
line of a safety plan or a contact's name.

**The boot cannot die here.** `except ModelError` did not catch the `StoreError`
that a corrupt credential file raises, so one bad file exited the process and
took the channel, the gate and the offline safe word with it — for every main.
Everything is inside one broad handler now, per main, plus one around the
assembly itself.

**Detection is identical for every main.** The classification tier is pinned to
`CLASSIFY_TIER` rather than following the main's conversation tier, and a main
is equipped by having a *key* — requiring a `HALF_MODEL_TIERS` entry was a tier
gate on CAP-12 behaviour wearing configuration's clothes. Whether the pinned
tier detects well enough, in every script, is a reviewer-and-eval question that
no arrangement of green cases answers.

**A safety-plan turn is never sent.** `_second_opinion` ran before `_plan_turn`,
so an intake — clinician, contact, phone number, and step six — was classified
and left the machine. The egress test guarded a contact in the *store*; the
route that actually puts one in a payload is the main typing it.

**Guards that passed on the wrong thing, and what replaced them.** The wiring
test asserted a keyword's *name* (so `second=None` passed) and now runs `serve`
and asserts identity with what `build` returned. The per-call ceiling was pinned
only from below (loosening it five-thousand-fold stayed green) and is now driven
through the real provider over a counting transport. The classifier gate's whole
margin *was* its twelve mutation-guard cases, so those now carry
`cap12_classifier_property` and their own floor — 6c's lesson, applied on the day
rather than a story later.

**Smaller corrections.** `_verdict` moved inside the handler, because a holder
breaking the port's contract raised past it and left `consulted` incremented
with nothing counted against it — the one number an operator watches
understating failure on exactly the failing path. `Verdict(ASK, fell_back=True)`
is now unconstructible. The holder check is an allowlist (`classify`, and the
object may not be callable) rather than a six-name denylist. `SecondOpinion` is
sealed and its holders are a read-only mapping. A cancelled turn is isolated by
asking `cancelling()` whose cancellation it is, so a shutdown still propagates
while a turn that cancelled itself costs one turn. `raised` and `unreadable` are
counted apart, for the reason `bound_exceeded` was.

**Disagreed with, and why.** *Coercing near-miss labels* (a stray full stop, an
NFC/NFD difference) is refused: `read_decision`'s reviewed rule is that nothing
is matched to its nearest neighbour, the direction of the loss is safe — a
counted fallback, never a wrong ask — and a second, looser parser in the crisis
package is exactly what that rule exists to prevent. They are counted apart so
the reviewer can see whether a provider produces them at all.

**Left undone, deliberately.** Nothing tells the main their messages now leave
the machine, and there is no opt-out short of removing the key. Any sentence a
main receives is an Ask-First and clinical-review change, so writing one here
would be inventing reviewed wording; it is named as a **launch blocker** instead.
The same asymmetry the affirmative table had still applies to 6c's `stop_asking`
and `plan_request` vocabularies — this story widened risk *noticing* and the
answer to Half's own question, and widening 6c's surfaces changes what 6c does.

**The known cost of egress on most turns.** Every ordinary message is classified,
at roughly a twentieth of a cent settled. For a free main at twenty messages a
day that is a few tens of cents a month against a modelled blended cost of half a
dollar to a dollar and a half — material, and named here rather than discovered
on an invoice.

**AD-23 is load-bearing rather than merely stated.** The gate is the first thing
on the inbound path that waits on a network. Telegram long-polls; a WhatsApp
adapter must acknowledge within five seconds and enqueue before reaching the
gate, and that is written into the gate's own docstring.

## Suggested Review Order

**Start here — what a model is allowed to decide**

- The label set, what each label permits, and the import-time refusal of
  anything above a question.
  [`classifier.py:1`](../../../../half/crisis/classifier.py#L1)

**Uncertain against unavailable, which is the whole design**

- One rule for the mapping: an answer that is not a label from the closed set is
  a fallback, whatever shape it arrived in.
  [`classifier.py`](../../../../half/crisis/classifier.py#L1)

**Where it is consulted, and the three returns that are load-bearing**

- The table decided · the mode is open · a question already stands.
  [`gate.py`](../../../../half/crisis/gate.py#L1)

**Reachable in the shipped product, and only with the narrow holder**

- One provider per main, built from the secret store beside the tree; a main
  with no key gets story 6a exactly.
  [`__main__.py`](../../../../half/__main__.py#L1)

**Tests that carry the design**

- One case per matrix row, plus what leaves the machine asserted against the
  rendered request with a full store behind it.
  [`test_classifier.py:1`](../../../../half/tests/test_classifier.py#L1)

- The escalating suite, run with the classifier present and absent, and pinned
  against itself.
  [`test_redteam.py`](../../../../half/tests/test_redteam.py#L1)

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network
- `cd half && uv run --extra dev pytest tests/test_classifier.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest tests/test_redteam.py -q` -- expected: green with the classifier present and absent
- `cd half && uv run --extra dev pytest -m cap12 -m cap12_durable -m cap12_handoff -m cap12_aftercare -q` -- expected: 6a, 6b and 6c intact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — what a model may and may not do**

- Four labels, none permitting more than a question; a label mapped to `ENTER` makes the module refuse to import.
  [`classifier.py:1`](../../../../half/crisis/classifier.py#L1)

**The offline floor**

- The table decides entering, and confirmation now spans the languages the question is asked in.
  [`signals.py:1`](../../../../half/crisis/signals.py#L1)

**The seam**

- Consulted once, only when the table found nothing, and never on a turn that already carries what the main dictated.
  [`gate.py:1`](../../../../half/crisis/gate.py#L1)

- Per-main dispatch: one main's provider wait is no longer everyone's latency.
  [`runtime.py:1`](../../../../half/actor/runtime.py#L1)

**Tests that carry the design**

- A hanging provider, two mains, and a safe word that must not queue behind either.
  [`test_classifier.py:1`](../../../../half/tests/test_classifier.py#L1)
