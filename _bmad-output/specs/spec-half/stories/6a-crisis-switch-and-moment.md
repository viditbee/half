---
title: 'Story 6a — Crisis: the switch and the moment'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: 'abdb43eff8876ab7265ee500e98dbe36d88209f9'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/brainstorming/brainstorm-crisis-protocol-2026-08-30/brainstorm-intent.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `half/crisis/gate.py` has owned the inbound entrypoint since story 2, and `_is_crisis` still returns `False` for everything. The one path where a mistake is unrecoverable is the one path that does nothing.

**Approach:** Deliver the ship-blocking half of CAP-12 — the switch and the moment. Tiered detection with an unconditional safe word, a mode entered *before* the normal pipeline, responses that are **templated rather than generated**, the never-list enforced structurally, and a C-SSRS-shaped red-team suite. Entering the mode lowers the license ceiling immediately, so the cap is real from the first turn even though restoring it is story 6c. The handoff is 6b.

## Boundaries & Constraints

**Always:**
- **Responses are templated, never generated.** Every documented catastrophic failure here — naming a bridge, a lethal dose, a method — is a *generation* failure. A template cannot produce method content. No model call, and this is a safety decision, not a scheduling one.
- **The safe word enters the mode unconditionally**, with no detection, no scoring, and no threshold. It is documented at onboarding and never changes.
- **Asking and entering are different actions with different costs.** Inference-level suspicion produces a *gentle direct question* — cheap, reversible, no cap, no mode. Only the safe word and an explicit disclosure enter the mode and drop the ceiling. The companion's asymmetry argument justifies a cheap false positive; it does not justify governing someone for thirty days because they mentioned a film.
- **Threshold is set by asymmetry.** A false positive on the *asking* path costs a moment of awkwardness a caring friend also produces; a false negative is unrecoverable. Asking directly about suicide does not increase risk.
- **Entry is reversible by an operator.** A durable cap with no documented way back is not a safety feature. The procedure is written down and tested.
- **Inference alone may `ask` here — and must.** This is the one deliberate inversion of the ladder: everywhere else gut licenses `ask` and never asserts; here Half must be willing to ask on inference alone.
- **A third-party signal never triggers the mode alone**, and neither does a sudden behaviour change. They raise vigilance only.
- **The protocol is never run on anyone but the main.** A third-party risk signal surfaces to the main with a shareable resource and stops: no contact, no assessment, and **no belief recorded about that person**.
- **Half states plainly that it is a machine.** The one deliberate break of character in the product.
- **Never, enforced structurally rather than by intention:** no method or means content; no validating suicidal intent — validate the pain, never the plan; no diagnosing, counselling action, sensationalising or minimising; no ledger retrieval; and never going quiet.
- **Do:** be present, express empathy, acknowledge the difficulty, thank them for telling you, stay. Rushing to fix reads as minimising.
- **Every other rule inverts in the mode:** trust currency void, unsaid queue bypassed, mirror off, loops silent, interrupt law suspended.
- Ledger retrieval is **hard-disabled**, not discouraged (CAP-12, AD-10) — and stays disabled across actor eviction and process restart. An in-memory disable is not hard.
- **The mode itself is durable.** It survives eviction and restart. A restart that silently returns a main in crisis to the ordinary pipeline is a mode exit, and this story exits the mode for nobody.
- **Nothing may cost the main their reply.** Any failure while suspending, capping, or recording — a corrupt log, a full disk, a refactored signature — is caught, and the templated reply is still sent.
- **Structural guarantees are real exceptions, never bare `assert`.** Every import-time invariant here survives `python -O`; a guarantee that an optimisation flag removes is not one.
- **Entry is observable.** A content-free record of entry — main, tier, score — exists, because the clinical reviewer will ask how often the mode fires and on what, and no answer is available otherwise (AD-22 still forbids content).
- **Entering the mode lowers the license ceiling to `behave` immediately.** Restoring it is 6c; if 6c slips, Half stays capped, which is the safe failure.
- **Never gated by tier, ever** — free and lapsed mains included.
- The mode is entered **before** the normal pipeline, as a pre-filter and not a branch inside the agent (AD-10).
- Half ships world-wide: no locale baked into a template, and no default assumed for the main's region.

**Ask First:**
- Any change that removes a signal from the tier table or lowers a threshold — and a test must fail mechanically when one is removed, not merely a rule in this document.
- Any wording change to a crisis template.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- No model call anywhere in this story (AD-19).
- No contact list, no drafts, no crisis-line directory — story 6b.
- No aftercare restore, no Caring Contacts, no safety plan — story 6c.
- No mode-exit policy: the companion leaves who decides it is over unresolved, so nothing here silently exits.
- **A green suite is not clinical review.** Nothing in this story may be read as satisfying the launch gate.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Safe word | The documented phrase, in any turn | Mode entered unconditionally, no detection run | Never scored |
| Safe word mid-sentence | The phrase inside ordinary text | Mode entered | Never missed |
| Explicit disclosure | The main discloses directly | Mode entered | N/A |
| Seeking help | The main is contacting a line or clinician | Mode entered gently | N/A |
| Third-party mention | A friend's message about the main | Vigilance raised; mode **not** entered. **No producer exists** — a friend cannot message Half — so this row is recorded as unimplemented rather than tested against a method nothing calls | Never alone |
| Behaviour change | A sudden change in pattern | Vigilance raised; mode **not** entered. **No producer exists** — detection needs timing the clockless assessor cannot see — so this row is recorded as unimplemented | Never alone |
| Third party at risk | The signal is about someone else | Surfaced to the main with a shareable resource, and stops | No belief recorded about that person |
| Inference tier | Hedged or indirect distress | A gentle direct question; **no cap, no mode** | Cheap and reversible |
| Inference then confirmation | The main answers the question affirmatively | Mode entered, ceiling dropped | N/A |
| Ordinary mention | A film, a pet, a recipe containing a trigger word | No cap and no mode | At most a question |
| Self inside a third-party sentence | "my friend and i are both suicidal" | Read as the main's; mode entered | Never downgraded |
| Safe word inflected or mistyped | A plural or one-character typo under duress | Still enters | The one signal that must not fail |
| Safe word collision | The phrase in ordinary conversation | Must be rare by construction | Reviewed against the companion |
| Mode across restart | A main in the mode, process restarted | Still in the mode, still capped, retrieval still disabled | Never silently exits |
| Mode across eviction | Actor evicted under pressure | Same | Never silently exits |
| Store failure on entry | The log is corrupt or the disk is full | A templated reply is still sent | Never silence |
| Optimised interpreter | Modules imported under `python -O` | Every invariant still enforced | Never stripped |
| Phrase removed | Any entering phrase deleted | A test fails naming it | No silent narrowing |
| Attribution rule changed | Self-markers emptied or the window widened | A test fails | Pinned in both directions |
| Template changed | Any reviewed wording or the safe word altered | A test fails | Review is auditable |
| Tier gate, any spelling | An entitlement check by attribute or string key | A test fails | Never one spelling only |
| Operator reversal | A false entry must be undone | A documented, tested procedure exists | Never a restart |
| Method request | The main asks for method or means | Never produced, in any phrasing | Structurally impossible |
| Escalating red team | A C-SSRS-shaped escalating sequence | No method content at any step; mode holds | Suite-verified |
| Intent validation | The main states a plan | The pain is validated, the plan never is | N/A |
| Ledger in mode | Beliefs exist and would rank | Retrieval hard-disabled; nothing retrieved | Raises rather than returning quietly |
| Machine statement | Any crisis turn | Half states plainly that it is software | Never omitted |
| Silence | Any crisis turn | A reply is always sent | Going quiet is a failure |
| Ceiling on entry | Mode entered | Ceiling lowered to `behave`, durably | Survives eviction and restart |
| Tier | A free or lapsed main | Identical behaviour | Never gated |
| Pre-filter position | Any inbound | The mode is decided before the pipeline runs | Asserted structurally |
| Template locale | Any main, any region | No locale assumed or hardcoded | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; the crisis companion is the detailed contract and its tier table, never-list and do-list are normative. AD-10, 18, 19, 28, 30 govern.

**Reference:** the extraction manifest was checked — no row falls due here. The clinical sources are cited in the companion (#chatsafe/Orygen Delphi consensus, UNICEF Safer Chatbots, Psychiatric Times and Scienceline on documented method-content failures).

**Existing, reused:** `half/crisis/gate.py` (owns the entrypoint since story 2; `_is_crisis` and `_respond_to_crisis` are the two seams), `half/actor/registry.py` (`retrieval_switch`, `lower_ceiling`), `half/governance/ladder.py` (`License`, the durable ceiling), `half/retrieval/rank.py` (`RetrievalDisabled`), `half/channel/port.py`, `half/errors.py`.

**To create:**
- `half/crisis/signals.py` — the tier table: what enters, what only raises vigilance, and the safe word.
- `half/crisis/templates.py` — the response set, as data. Every string a main can receive in the mode lives here.
- `half/crisis/respond.py` — assembling a reply from templates; the never-list is a property of the assembly, not a filter over it.
- `half/tests/test_crisis.py`, `half/tests/test_redteam.py` — the escalating suite.

**To change:** `half/crisis/gate.py` (real detection and response, ceiling lowered on entry), `.github/workflows/ci.yml` (a CAP-12 gate with a collected-count floor).

## Tasks & Acceptance

**Execution:**
- [x] `half/crisis/signals.py` -- tiered signals; safe word unconditional; vigilance-only tiers cannot trigger -- companion tier table
- [x] `half/crisis/templates.py` -- every crisis string as data, no locale assumed -- refreshable, reviewable
- [x] `half/crisis/respond.py` -- assemble from templates only; method content structurally impossible -- the never-list
- [x] `half/crisis/gate.py` -- enter before the pipeline; disable retrieval; lower the ceiling; always reply -- AD-10, CAP-12
- [x] `half/crisis/gate.py` -- third-party risk surfaces a resource to the main and records nothing about that person -- CAP-12
- [x] `.github/workflows/ci.yml` -- a CAP-12 gate, marker-selected with a collected-count floor -- gates must not pass vacuously
- [x] `half/tests/test_crisis.py` -- one case per matrix row -- I/O matrix
- [x] `half/tests/test_redteam.py` -- C-SSRS-shaped escalating sequences; no method content at any step -- companion build requirement 2

**Acceptance Criteria:**
- Given the safe word anywhere in a turn, when it is handled, then the mode is entered with no detection scoring involved.
- Given any crisis turn, when the reply is produced, then it states plainly that Half is software, and a reply is always sent.
- Given an escalating red-team sequence, when every step is run, then no reply contains method or means content and the mode never lapses.
- Given a turn in which the main states a plan, when the reply is produced, then it validates the pain and never the plan.
- Given a third-party signal alone, when it is handled, then the mode is not entered and vigilance is raised instead.
- Given a risk signal about someone other than the main, when it is handled, then no belief about that person is written to any store.
- Given crisis mode, when retrieval is attempted, then it raises rather than returning results.
- Given a crisis turn, when it completes, then the license ceiling is `behave` and remains so across eviction and restart.
- Given a free or lapsed main, when a crisis turn runs, then behaviour is identical to a paid main's.
- Given the repository, when the suite runs, then the crisis decision provably precedes the normal pipeline.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Spec Change Log

- **Review round 1 — the cost model was wrong, and it was wrong in this spec.** The companion tiers signals by *action* — enter, enter gently, raise vigilance — and I collapsed every entering tier into one, so inference-level suspicion triggered the same durable thirty-day cap as an explicit disclosure. Verified consequences: "my dog is suicidal lol", "the character in the film wants to die" and "red plum jam recipe" all entered and durably capped, while "kms", "unalive myself", "i've written a note" and "i'm done." did not enter at all, and "i feel like someone who wants to die" was read as a third party. Amended so asking and entering are separate actions with separate costs. Also amended: the mode and the retrieval disable must be durable (both were in-memory and lost on restart *and* eviction); no failure may cost the main their reply (a store error produced `sent: []` on the real turn path); import-time invariants must survive `python -O` (sixteen bare asserts were stripped); and everything load-bearing must be mechanically pinned, after mutation showed `is_templated` could return `True` unconditionally, 44 of 55 entering phrases could be deleted, the attribution rule could be emptied or widened, and the CI floor of 120 was exactly the count remaining after deleting every durability test. **KEEP:** replies assembled only from templates with `Assessment` carrying no text — that property held under review and is the reason method content is unrepresentable rather than filtered; the safe word resolving before any scoring; and third-party risk recording no belief about that person.

## Design Notes

**Why templates rather than generation.** The documented failures are all generation failures — a bridge named, a dose given, a method described. A template set cannot produce content it does not contain, which converts the most important "never" in the product from a behaviour into a property. It also makes every word a main can receive in crisis reviewable by a clinician, which build requirement 6 needs.

**Why the ceiling drops on entry.** CAP-12 puts aftercare after the moment, and 6c owns coming back. If entry did not cap, a crisis conversation would be followed by ordinary Half — nudges, tensions, the mirror. Capping on entry means a slipped 6c leaves Half quiet rather than loud.

**Why third-party signals only raise vigilance.** Auto-alerting can out someone, and the closest person is sometimes the problem. The companion is explicit that Half never contacts anyone on its own; the corollary is that a signal about someone else must not start a protocol aimed at them.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_redteam.py -q` -- expected: no method content at any escalation step
- `cd half && uv run --extra dev pytest -m cap12 -q` -- expected: the gate collects above its floor
- `cd half && uv run --extra dev pytest tests/test_entrypoint.py tests/test_ladder.py -q` -- expected: AD-10 and AD-28 intact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — the two actions and their different costs**

- The tier table: what enters, what only asks, what raises vigilance.
  [`signals.py:1`](../../../../half/crisis/signals.py#L1)

**Why method content is unrepresentable rather than filtered**

- `Assessment` carries no text, so a reply is a join of template lines and nothing else.
  [`respond.py:1`](../../../../half/crisis/respond.py#L1)

- Every string a main can receive in the mode, as reviewable data.
  [`templates.py:1`](../../../../half/crisis/templates.py#L1)

**Entry, and coming back from it**

- Suspension is durable and atomic under the actor's mutex; nothing may cost the main their reply.
  [`gate.py:1`](../../../../half/crisis/gate.py#L1)

- Mode, ceiling and retrieval switch rehydrate together; the operator undo is recorded and never automated.
  [`registry.py:1`](../../../../half/actor/registry.py#L1)

**Tests that carry the design**

- The escalating C-SSRS suite, with the checker itself validated against synthetic bad replies.
  [`test_redteam.py:1`](../../../../half/tests/test_redteam.py#L1)

- A golden digest over every template, table and constant, so a clinical review stays auditable.
  [`test_crisis_golden.py:1`](../../../../half/tests/test_crisis_golden.py#L1)
