---
title: 'Story 12 — Correction'
type: 'feature'
created: '2026-09-02'
status: 'done'
baseline_commit: '1ccc0ff'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A main cannot tell Half it is wrong. Nothing on the inbound path recognizes a correction, so a belief Half holds incorrectly stays held, shapes every context it enters, and can be asserted back at the main. The ops exist — `retract`, `revise` and `expunge` have been in the closed vocabulary since story 1 — and the fold removes a belief for any of them, but nothing appends one and nothing says what was removed.

**Approach:** Deliver CAP-11. Recognize a correction on the inbound path; keep *Half was wrong*, *the main changed* and *erase it entirely* distinct in the record and in what Half says; and show the main what was removed. Recognition is the offline table for explicit corrections, widened by the classifier — which **never acts alone**: a widened candidate is shown and confirmed before anything is appended, the rule CAP-10 already fixes for quarantine.

## Boundaries & Constraints

**Always:**
- **The recall instrument is not an enumeration.** `half/crisis/classifier.py` already argues this for distress and the argument transfers unchanged: a phrase table fires only on what somebody thought to write down, and the ways a person says *"that's wrong"* are not enumerable. The table is the fast, offline, high-confidence path; the classifier widens it.
- **Never acts on inference alone.** An explicit correction the table recognizes is acted on directly. Anything reaching the correction path only through the classifier is a **candidate**: Half shows what it would remove and asks, and the main's answer decides (CAP-10's quarantine rule, applied to the same class of problem).
- **The attribution is never guessed.** *Half was wrong* and *the main changed* are different facts with different consequences, and only the main knows which. Where the utterance settles it, record it. Where it does not, the record must say so rather than pick — a ledger that exists to be honest is the wrong place to infer a cause.
- **Removal does not wait on attribution.** The main has said the belief is wrong; it leaves the current fold on that signal alone. Attribution can arrive later, and corrections are appends, so a later message can settle it.
- `retract`, `revise` and `expunge` stay distinct **in the record and in what Half says** — erasure is not removal, and a correction Half caused is not a correction the world caused.
- **A corrected belief leaves its wanting standing.** The refutation firewall (CAP-6) is already structural in the fold and asserted by AST; nothing here may reach the loop table, even when the corrected belief was a loop's only support.
- What Half shows as removed is **the removed claim itself** — the main's own words as recorded — never composed prose.
- The classifier is bounded and capped as 6d bound it, and a provider that is slow, absent or failing leaves the table's answer standing. It never blocks the main's turn past its bound and never invents a correction.
- Nothing here reads a clock inside a fold; replay stays pure (AD-30).

**Ask First:**
- **Any change to the closed op vocabulary.** The three-state attribution needs a home. My reading is that it belongs on the record's timestamps — graphiti's `invalid_at` (the main changed) against `expired_at` (Half was wrong), both absent meaning not yet known — which leaves `ops.py` untouched. If the implementation finds that unworkable, surface it rather than adding an op.
- Any runtime dependency beyond the standard library and pinned SDKs.
- Any change to the crisis path, the ladder, or the trust currency.

**Never:**
- No correction inferred and acted on in one step. Detection widened by a model produces a candidate, never an append.
- No phrase table standing alone as the recall instrument, and **no locale, language or script treated as the default** — Half ships worldwide.
- No generated prose. Half shows what it removed by quoting the record, not by composing a sentence.
- A correction clarifier is **not** a CAP-4 question: it spends no favour and passes through none of story 5b's gates. Half fixing itself is not Half acquiring the stated ledger.
- No belief mutated in place, ever. Corrections are appends (AD-3).
- Do not touch story 11's question path, the crisis protocol, or the morning surface's choice.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Half was wrong, explicitly | Main says the belief was never true | `revise` appended; belief leaves the fold; attribution recorded as Half's error; Half shows what it removed | N/A |
| The main changed | Main says it used to be true and no longer is | `retract` appended; attribution recorded as the world changing; no apology | N/A |
| Wrong, cause unstated | Main negates the belief without saying which | Belief leaves the fold; attribution recorded as **not yet known**; Half may ask | Never guessed |
| Attribution arrives later | A follow-up settles which it was | Appended; the record now carries the cause | N/A |
| Inferred, not explicit | Only the classifier reads it as a correction | A **candidate**: Half shows what it would remove and asks; nothing appended | Never acts alone |
| Candidate declined | Main says no | Nothing removed; nothing appended beyond the exchange | N/A |
| Erase it | Main asks for it to be gone entirely | `expunge`; bodies tombstoned; distinct from removal in what Half says | Story 1's validate-then-erase |
| No such belief | Correction naming nothing Half holds | Nothing removed; the main is not shown an error | Logged without content |
| Already corrected | The belief has already left the fold | Idempotent; no second removal, no second message | N/A |
| The loop survives | The corrected belief was its loop's only support | The wanting stands (CAP-6) | Structural, by AST |
| Classifier unavailable | Provider absent, failing, or past its bound | The table's answer stands; no correction invented | Never blocks the turn |
| Classifier cost | The pass exceeds its cap | Bounded as 6d bounds it | Refuses rather than overspending |
| In crisis | A correction arrives mid-crisis | The crisis path owns the turn | Correction not processed |
| Reversal | The main corrects the correction | Appended again; both survive in the log | N/A |
| Shown text | Any correction Half reports | The removed claim as recorded — never composed prose | AD-22 |
| No favour | Any correction or clarifier | Nothing spent; story 5b's gates are not consulted | N/A |
| Replay | A log carrying corrections and attributions | Folds identically; attribution survives the rebuild | AD-4 |
| Worldwide | A correction in any language or script | Recognized without depending on a table row for that language | Never locale-defaulted |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-11, CAP-6, CAP-10, CAP-12, AD-3, AD-19, AD-22, AD-29, AD-30 govern this story.

**Reference (extracted from the manifest):** the graphiti row — `graphiti_core/edges.py:271-280`, the four timestamps separating *we were wrong* from *you changed*. The manifest records this as partly extracted: the retract/revise split landed in story 1, and "the four-timestamp model itself is still open for story 12". This story closes it; mark the row extracted and record what was rejected.

**Existing, reused:** `half/store/ops.py` (`RETRACT`, `REVISE`, `EXPUNGE` — already closed and validated), `half/store/fold.py:300` (both ops already remove the belief and the firewall comment already states what this story must preserve), `half/store/log.py::expunge_bodies`, `half/crisis/classifier.py` (the `Classifier` protocol, the bound, the cost caps and the surface — the shape to copy), `half/crisis/gate.py` (the inbound entrypoint, AD-10), `half/actor/runtime.py`.

**To create:**
- `half/correction/signals.py` — the offline table: explicit corrections, and which of the three meanings each carries. No language is the default.
- `half/correction/attribute.py` — the three-state attribution and its record shape. Pure.
- `half/correction/candidate.py` — the classifier's widening, and the candidate that must be confirmed before it acts.
- `half/correction/apply.py` — appending the correction and reporting what was removed.
- `half/tests/` — `test_correction.py`, `test_attribution.py`.

**To change:**
- `half/store/records.py` — the timestamp fields carrying attribution, if the Ask First above resolves that way.
- `half/actor/runtime.py` — recognize a correction on the inbound path, behind the crisis gate.

## Tasks & Acceptance

**Execution:**
- [x] `half/correction/signals.py` -- the offline table, no default language -- worldwide
- [x] `half/correction/attribute.py` -- three states, never guessed -- CAP-11
- [x] `half/correction/candidate.py` -- the classifier widens; a candidate never acts alone -- CAP-10
- [x] `half/correction/apply.py` -- append, and show the removed claim -- CAP-11, AD-22
- [x] `half/store/records.py` -- attribution on the record; op vocabulary untouched -- AD-29
- [x] `half/actor/runtime.py` -- correction recognized behind the crisis gate -- AD-10
- [x] `half/tests/test_correction.py` -- every matrix row -- I/O matrix
- [x] `half/tests/test_attribution.py` -- the three states, and that none is inferred -- CAP-11
- [x] `.github/workflows/ci.yml` -- a CAP-11 gate, margin sized to the subset it protects -- the floor lesson

**Acceptance Criteria:**
- Given a main who says a belief was never true, when the turn completes, then `revise` is appended, the belief is gone from the fold, and Half shows the claim it removed.
- Given a main who says something has changed, when the turn completes, then `retract` is appended and the attribution records the world changing, not Half's error.
- Given a correction whose cause the utterance does not settle, when the turn completes, then the belief is removed and the attribution reads as not yet known — asserted by a test that fails if either cause is written.
- Given a message only the classifier reads as a correction, when the turn completes, then nothing is appended and Half has asked — asserted structurally, so a new inference route cannot bypass it.
- Given a classifier that is absent, failing, or past its bound, when a correction arrives, then the table's answer stands and no correction is invented.
- Given a corrected belief that was its loop's only support, when the fold runs, then the wanting still stands.
- Given a correction in a language no table row covers, when it is recognized, then it is recognized — and no test fixture makes any one language the default.
- Given any correction, when the log is scanned, then no composed prose was written and no belief was mutated in place.
- Given the full suite, when it runs, then it passes offline with no network, the classifier stubbed as 6d stubs it.

## Design Notes

**Why the classifier, and why it cannot act.** The argument for widening past a phrase table is already written in `half/crisis/classifier.py` and transfers without change. The argument for *bounding* it does not: entering crisis carries a durable thirty-day cap, which is why a model may never enter, whereas a correction is an append and is itself correctable. The ceiling here is therefore weaker but must still exist, and CAP-10 already fixes where it sits — *"Quarantine is never applied on inference alone: detection produces a candidate and Half asks whether to leave the topic alone."* Same shape, same reason: acting on an inferred negation deletes something the main actually believes.

**Why attribution has three states.** CAP-11's success criterion is that the distinction between *Half was wrong* and *the main changed* is preserved in the record. Preserved means true, and only the main knows which. A default in either direction writes a falsehood into the one ledger whose whole purpose is to be honest — apologising for something the main simply changed, or telling a main they changed their mind when Half was plainly wrong. Represent the unknown, and let a later message settle it.

**Why removal does not wait for attribution.** The alternative is a Half that answers *"that's wrong"* with a clarifying question before doing anything, which makes the correction path feel like an interrogation and leaves a known-wrong belief shaping contexts while the exchange resolves. The signal to remove and the cause of the removal are different facts arriving at different times; treat them that way.

**Watch the two firewalls.** The fold's `RETRACT | REVISE` branch carries CAP-6's refutation firewall, asserted by AST in `tests/test_loops.py`, and story 8 shipped that firewall broken because the guard scanned for a spelling. Anything added to this path must be checked against the property — that no correction route can reach the loop table — not against the branch's current text. The same discipline applies to the crisis gate: story 6b's send scan caught a name, not a property.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_correction.py tests/test_attribution.py -q` -- expected: the CAP-11 path passes
- `cd half && uv run --extra dev pytest tests/test_loops.py -q` -- expected: the refutation firewall unbroken
- `cd half && uv run --extra dev pytest tests/test_replay.py -q` -- expected: attribution survives a rebuild
- `cd half && git status --porcelain` -- expected: clean tree after commit
