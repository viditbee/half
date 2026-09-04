---
title: 'Story 15a — What a message is worth keeping'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: '98f077b'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `half/actor/runtime.py` writes **every inbound message verbatim as a stated belief**. So `"ok"`, `"thanks"` and `"hello?"` are beliefs in a main's ledger — ranked by retrieval, quotable once promoted, eligible for a tension against the revealed side, and the thing a correction aims at. CAP-5 says every belief passes four admission gates — decision-relevance, durability, independence, falsifiability — and names them individually testable. None exists. Story 3 deferred derivation as needing the model port; the port, the consultation shape and a judge pattern all exist now.

**Approach:** Separate the two things the turn conflates. **A message is evidence; a claim is a belief.** The message record stays exactly where it is and keeps carrying everything that reads it, but is marked as underived — so the belief-consuming paths stop treating it as a claim. Derivation then reads a message and produces a claim, or nothing, gated by the four admission tests.

**Not in this story:** the revealed ledger. Source receipts to claims is 15b, and it reuses the gates this story builds.

## Boundaries & Constraints

**Always:**
- **The message record keeps its readers.** Three subsystems read what the turn writes today — the language sample (`half/voice/compose.py`), responsiveness to a question (`half/questions/answered.py`), and the aim's exclusion (`half/correction/apply.py`). All three must still work, and each must be asserted still working by a case that fails if it stops.
- **A message is not a belief.** Retrieval, the context builder, the tension minter and the ladder see derived claims and never the raw message. Enforced by what those paths are *handed*, not by a filter each applies — story 10's lesson, and the one that has held.
- **Four gates, individually testable**, as CAP-5 requires: decision-relevance, durability, independence, falsifiability. Each has its own name, its own reason for refusing, and its own case; a claim refused by two gates reports both rather than the first.
- **Nothing derived is admitted above the floor.** A derived claim enters at the weakest rung through `ladder.admitted()`, exactly as today. Derivation decides *whether* there is a claim, never what Half may do with it.
- **The claim cites its evidence** (CAP-5): a derived claim carries the message it came from in its support set, so *every belief cites its evidence* stays true of the stated ledger and not only the revealed one.
- **The judgement is bounded** on `half/model/consult.py`'s shape — a fourth caller, not a fourth copy — with its own policy, the cheap tier (`SPEC.md:124`), and a per-turn bound that never costs the main their reply.
- **Nothing derived is durable until it passes.** A refused message leaves no claim, no partial record and no marker beyond what the turn already writes.
- **Worldwide.** Messages arrive in any script; no English rubric, no locale, and no assumption a claim is in the same language as the message.

**Ask First:**
- **Adding an op to the closed vocabulary.** My reading is that this needs a *field* marking a record as underived, not a new op — story 1's Ask First covers the vocabulary and the record shape, and a field is the smaller change that makes the distinction explicit. If a field cannot carry it, surface that.
- Any change to what the three existing readers consume.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- No fifth copy of the consultation machinery.
- No claim admitted above `behave`, and no promotion here — that is the ladder's and story 11's.
- No derived claim without a support set naming its message.
- No message text in a log line, and no derived claim text in one (AD-22).
- Do not build the revealed side, do not touch the crisis path, and do not change what a turn replies.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| A claim worth keeping | *"I want to move to the farm next year"* | One derived claim, `behave`, citing the message | N/A |
| Not decision-relevant | *"ok"* | No claim; the gate names itself | Never a belief |
| Not durable | *"I'm tired today"* | No claim | Never a belief |
| Not falsifiable | *"life is strange"* | No claim | Never a belief |
| Two gates refuse | A message failing more than one | Both named, not the first | N/A |
| The message still reads | Any turn | The language sample, responsiveness and the aim all still work | Asserted per reader |
| Not a belief | Any raw message | Absent from retrieval, the context, the minter and the ladder | By what they are handed |
| Cites its evidence | Any derived claim | Support names the message it came from | CAP-5 |
| The floor | Any derived claim | Enters at the weakest rung, never above | AD-28, the ladder |
| Judge absent | No provider wired | No claim derived; the turn is unaffected | Never fatal |
| Judge slow | Past the bound | No claim; the reply is never delayed | Never costs the reply |
| Judge raises | The call throws | No claim; the turn completes | Never costs the reply |
| Over the cap | Per-call or per-turn cost exceeded | Refuses rather than overspending | Bounded |
| Crisis | The mode is open | Nothing derived; the crisis path owns the turn | CAP-12 |
| Any script | A message in any writing system | Judged, with no English rubric on the path | Worldwide |
| Two languages | A claim derived from a message in another script | Permitted; neither is assumed to be the other's | Never locale-defaulted |
| Nothing durable | A refused message | No claim, no partial record, no marker | N/A |
| Replay | A log of messages and derived claims | Folds identically; derivation is not in the fold | AD-4, AD-30 |
| Nothing logged | Any derivation | No message text and no claim text in any log line | AD-22 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-3, CAP-5, CAP-12, AD-3, AD-19, AD-20, AD-22, AD-28, AD-30 govern this story.

**Reference (extracted from the manifest):** check for rows this story consumes. The **honcho** conclusion-levels row (`explicit` session-scoped vs deductive/inductive cross-session) is already marked extracted and is the vocabulary this story works in; re-read it rather than re-deriving it.

**Existing, reused:** `half/model/consult.py` (the shape), `half/consolidate/judge.py` (the *pattern* for a bounded classifier with a closed label set and a contradiction given its own home — read it, do not copy it), `half/governance/ladder.py` (`admitted`), `half/store/records.py`, `half/actor/runtime.py`.

**To create:**
- `half/derive/gates.py` — the four admission tests, each named, each refusing for its own reason. Pure where it can be.
- `half/derive/claim.py` — the derivation itself, on `consult`'s shape, with its policy and its labels.
- `tests/test_derive.py`, `tests/test_gates.py`.

**To change:**
- `half/store/records.py` — the field marking a record underived, per the Ask First above.
- `half/actor/runtime.py` — the message is written as evidence; derivation runs after the reply and never in front of it.
- `half/retrieval/`, `half/context/build.py`, `half/consolidate/candidates.py` — handed derived claims, never raw messages.
- `half/__main__.py` — wire the deriver, its provider, the pinned tier and its budget.

## Tasks & Acceptance

**Execution:**
- [ ] `half/derive/gates.py` -- four gates, individually testable, each naming itself -- CAP-5
- [ ] `half/derive/claim.py` -- derivation on `consult`'s shape, cheap tier, bounded -- AD-19, SPEC:124
- [ ] `half/store/records.py` -- the underived marker -- Ask First resolved
- [ ] `half/actor/runtime.py` -- evidence written, derivation after the reply -- never costs a reply
- [ ] the three readers -- language sample, responsiveness, the aim -- each asserted still working
- [ ] the belief-consuming paths -- handed claims, never messages -- by what they receive
- [ ] `tests/` -- every matrix row, across scripts -- I/O matrix
- [ ] `.github/workflows/ci.yml` -- a CAP-5 admission gate, per-case marks, margin stated -- the floor lesson

**Acceptance Criteria:**
- Given `"ok"`, `"thanks"` or `"hello?"`, when the turn completes, then no belief exists for it — and each of the three refusing gates is named by its own case.
- Given a message worth keeping, when it is derived, then one claim exists at the weakest rung, citing that message in its support set.
- Given any turn, when the language sample, responsiveness and the correction aim are exercised, then each still works — asserted by a case per reader that fails if it stops.
- Given a raw message, when retrieval, the context builder, the tension minter and the ladder run, then none of them can see it — asserted by what they are handed, not by a filter.
- Given a provider that is absent, slow, failing or over budget, when a main writes, then they get their reply and no claim is derived.
- Given messages in any script, when they are judged, then no English rubric and no locale appears on the path.
- Given any derivation, when every log line is scanned, then neither the message nor the claim appears.
- Given the repository, when it is scanned, then the consultation shape appears once and this story added no copy.
- Given the full suite, when it runs, then it passes offline with the provider stubbed.

## Design Notes

**Why this is the story's spine and not a detail.** Three subsystems read what the turn writes today, and each was built assuming every message becomes a stated belief: the language sample takes the newest one, responsiveness looks for one after an ask, and the correction aim excludes the newest so it does not target the main's own words. Changing what the turn writes without carrying all three is the individually-correct-changes-compose failure this project has shipped twice. Hence the shape: the record stays and gains a mark, rather than being replaced.

**Why a message is evidence.** Story 1 separated sources from claims, and story 3 built that separation for mail — a receipt is evidence, a claim is what Half concluded. The turn path never got the same treatment, so a message is currently both. Making it evidence is not a new idea in this codebase; it is the existing idea applied where it was skipped.

**Why the gates report all their refusals.** CAP-5 calls them individually testable, and a gate that stops at the first refusal cannot be. It also hides the interesting case: a message refused by decision-relevance *and* falsifiability is a different thing from one refused by durability alone, and an operator tuning this will want to know which.

**Derivation runs after the reply.** A main waiting on a model call to find out whether their message was worth keeping is the latency failure story 13b spent a review round on. The reply goes first; the claim, if any, follows.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_derive.py tests/test_gates.py -q` -- expected: the derivation path passes
- `cd half && uv run --extra dev pytest -m "cap8_voice or cap4_bought or cap11" -q` -- expected: the three readers unbroken
- `cd half && uv run --extra dev pytest -m "cap7 or cap12" -q` -- expected: the minter and the crisis path untouched
- `cd half && git status --porcelain` -- expected: clean tree after commit
