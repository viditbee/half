---
title: 'Story 15b — What a source is worth keeping'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: '59a2380'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Ingestion captures receipts and derives nothing. CAP-3 says Half *"derives claims about what the main actually does"* and that *"no claim is admitted from a single non-independent cluster of mentions"* — so the revealed ledger is empty, and story 3's union-find, built precisely to make that sentence true, has never once decided anything in production.

**Approach:** Derive at ingest, admit on independence. Story 15a's four gates decide whether a body is worth a claim; the union-find decides whether enough independent sources support it; only then does a claim enter the revealed ledger, citing the sources it came from.

**Why it cannot be a later pass.** A `Receipt` *"carries no body and no secret value"* — story 3's central guarantee. The only moment a body exists is between `scrub` and the receipt being written, in memory, inside `ingest`. Derivation goes there or nowhere.

**The thing this story changes about the product, which is not a detail:** a main's **email bodies now leave the machine**, scrubbed, to a model provider. Message text already does — the crisis classifier, the composer, the deriver — but this is their mail, and it is a wider fact than any of those. Story 3 was scrupulous that a body never persists; this story keeps that and adds that it is *sent*. The open launch blocker *"telling a main their messages leave the machine"* now has to cover their inbox, and that sentence is harder to write than it was.

## Boundaries & Constraints

**Always:**
- **The body is never persisted, and that is unchanged.** What is sent is the scrubbed text, in memory, and what is written is a claim and a receipt. No body reaches the log, a projection, a cache, an error message or a log line (AD-22, story 3).
- **A secret never reaches a provider.** `scrub` runs before derivation, as it runs before the receipt. Derivation reads the scrubbed text and never `body.text`, and that ordering is asserted structurally rather than by reading the code.
- **No claim from a single cluster** (CAP-3). Admission requires the supporting sources to span **at least two independent groups**, counted by `half/ingest/independence.independent_groups` — ten mentions in one thread is one support, and a forward of the same content is one support.
- **The claim cites its sources.** `support` names them and `independent` carries the count, both already in story 1's record shape. A claim whose support set is empty or whose count is one is a defect, not a state.
- **The four gates are 15a's**, imported and not restated. What differs is the ledger and the evidence, not what makes a claim worth keeping.
- **An undecodable or unscannable body yields nothing** and fails closed, exactly as story 3 leaves it. Derivation never becomes a reason to relax a scan.
- **Ingestion stays idempotent.** Re-reading a mailbox derives nothing twice and admits no duplicate claim.
- **Worldwide.** Mail arrives in any script and any encoding; no English rubric, no locale, and no assumption a claim shares its source's language.
- Nothing here runs in a fold, reads a clock inside one, or touches the crisis path.

**Ask First:**
- Any change to `Receipt`, to what `scrub` removes, or to the order of scrub and derive.
- Any change to 15a's gates or to `independent_groups`.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- No body persisted anywhere, in any form. (This is AD-13's rule, and it is the whole of it. **Amended by story 15c**: this line read *"including a summary or an embedding"* until 2026-09-05. See the Spec Change Log below.)
- No unscrubbed text to a provider, ever.
- No claim admitted from one independent group, and no threshold that can be configured below two.
- No fifth copy of the consultation machinery.
- Do not build cross-run accumulation (below), do not touch the stated path, and do not change what a receipt carries.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Two independent senders | The same thing said by two unrelated senders | One claim, `independent: 2`, citing both | N/A |
| One thread, ten mentions | Ten messages sharing a thread id | **No claim** — one support | CAP-3's central case |
| A forward | The same content from a different sender | Collapsed by content hash to one support | No claim |
| One message | A single message, nothing else | No claim | Never from one cluster |
| Gates refuse | Two independent sources, but the content fails a gate | No claim; the gates name themselves | 15a's gates |
| The body is not persisted | Any ingest run | No body in the log, projections, caches or logs | AD-22, story 3 |
| Scrub before derive | A body containing a secret | The secret reaches no provider and no disk | Asserted structurally |
| Undecodable | A body that will not decode | Nothing derived, nothing sent, fails closed | Story 3, unchanged |
| Unscannable | Bytes the scanner refuses | Treated as a finding; nothing derived | Fails closed |
| Re-ingest | The same mailbox twice | No claim derived twice, no duplicate admitted | Idempotent |
| Provider absent | No deriver wired | Receipts still captured; no claim | Never fatal |
| Provider slow or failing | Past the bound, or raising | That message yields no claim; ingestion continues | Never costs the run |
| Over the cap | Per-run cost exceeded | Stops deriving and says so | Bounded |
| Cites its sources | Any admitted claim | `support` names them, `independent` is the count | CAP-5 |
| The count is honest | Any admitted claim | `independent` is what the union-find returned, not the support size | Never inflated |
| Any script | Mail in any writing system or encoding | Derived, with no English rubric on the path | Worldwide |
| Nothing logged | Any derivation | No body and no claim text in any log line | AD-22 |
| Replay | A log of receipts and claims | Folds identically; derivation is not in the fold | AD-4, AD-30 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-3, CAP-5, CAP-13, CAP-14, AD-3, AD-11, AD-13, AD-19, AD-22, AD-30 govern this story.

**Reference (extracted from the manifest):** the **claude-obsidian** union-find row is already marked extracted and is the machinery this story finally exercises — re-read what it says rather than re-deriving it. Check whether any row now names 15b.

**Existing, reused:** `half/derive/gates.py` and `half/derive/claim.py` (15a — imported, not restated), `half/ingest/independence.py` (`identity_set`, `independent_groups`), `half/ingest/pipeline.py`, `half/ingest/scrub.py`, `half/model/consult.py`, `half/governance/ladder.py` (`admitted`).

**To create:**
- `half/derive/revealed.py` — candidate claims from scrubbed bodies, matched within a run, admitted on independence.
- `tests/test_revealed.py`.

**To change:**
- `half/ingest/pipeline.py` — derivation between `scrub` and the receipt; the body still never persists.
- `half/__main__.py` — wire the revealed deriver, the pinned tier and its budget.
- `.github/workflows/ci.yml` — a CAP-3 gate, per-case marks, margin stated.

## Tasks & Acceptance

**Execution:**
- [ ] `half/derive/revealed.py` -- candidates, matching within a run, admission on independence -- CAP-3
- [ ] `half/ingest/pipeline.py` -- derive between scrub and receipt; no body persisted -- story 3, unchanged
- [ ] the independence threshold -- two groups, not configurable below it -- CAP-3
- [ ] 15a's gates imported, not restated -- one definition of worth keeping
- [ ] `half/__main__.py` -- provider, pinned tier, budget, counters -- operable
- [ ] `tests/test_revealed.py` -- every matrix row, across scripts -- I/O matrix
- [ ] `.github/workflows/ci.yml` -- the gate, per-case marks -- the floor lesson

**Acceptance Criteria:**
- Given a seeded mailbox where ten messages share a thread, when it is ingested, then no claim is admitted from them — CAP-3's own sentence, as its own case.
- Given two unrelated senders saying the same thing, when it is ingested, then one claim is admitted with `independent: 2`, citing both sources.
- Given any ingest run, when every byte written and every log line is scanned, then no body appears in any form.
- Given a body containing a secret, when it is ingested, then the secret reaches neither disk nor provider — asserted structurally, so a reordering of scrub and derive fails.
- Given the same mailbox ingested twice, when the second run completes, then no claim is derived twice and none is duplicated.
- Given a provider that is absent, slow, failing or over budget, when a mailbox is ingested, then receipts are still captured and the run completes.
- Given any admitted claim, when its record is read, then `independent` is what the union-find returned and never the size of the support set.
- Given the full suite, when it runs, then it passes offline with the provider stubbed and no network.

## Spec Change Log

- **The Never list said more than AD-13 does, and the extra clause cost a capability. The clause was mine, and story 15c corrects it on the record.** The line read *"No body persisted anywhere, in any form, **including a summary or an embedding**."* The emphasised half is not in AD-13 and is not in CAP-13. AD-13's rule is that *"message bodies are never persisted"* — a body is normalised, scanned, handed to its consumer, and discarded in memory — and its own accepted-cost note is *"rebuild can no longer re-derive claims from original text, so a better model cannot revisit old mail"*, which only makes sense if claims **are** derived from bodies and **are** kept. A claim derived from scrubbed text, in Half's own words, is not a body; a summary is a thing you keep *instead of* the body, and forbidding one forbids the derivation the architecture assumes.

  **What it cost.** The implementer of 15b read the clause as binding — correctly, since a frozen block is — and concluded that a claim could therefore carry no word of what the mail said. What is left when a claim may carry nothing derived from a body is a claim drawn from a vocabulary shipped in the tree, so `half/derive/revealed.py` shipped six of them: *travels*, *buys things*, *pays for a subscription*, *keeps appointments*, *does paid work*, *studies*. Story 7 then built CAP-2's demonstration on top of that vocabulary and found it was the complete set of things Half could say about any mailbox in the world. CAP-2's success criterion is a statement *"confirmed as true **and previously unstated by the main**"* — and nobody learns that they travel. The capability the whole product is acquired through was unreachable, in the shipped build, for two stories, and every test of it was green.

  **How it was found.** Not by a reviewer reading 15b, and not by story 7's author, whose demonstration worked exactly as specified. It was found by an implementer who went back to AD-13 to check what the clause was a restatement of, and found it was a restatement of nothing.

  **What changed.** The clause is removed and the line now states AD-13's rule and stops. Story 15c generates a group's claim from its scrubbed texts and admits it only on the support that claim itself has. Nothing else in this block moves: the body is still never persisted, `scrub` still runs first, the threshold is still two, and cross-run accumulation is still deferred.

  **The lesson worth keeping, since a change log entry is the only place it survives.** A frozen block is read as binding, so a sentence in one that goes further than the architecture is a decision made without a decision. The next person to read this Never list should see that it once said more than AD-13 does, and what two stories of closed vocabulary cost.

## Design Notes

**Why the independence gate is the story.** Everything else here is 15a with a different input. The union-find has existed since story 3, is well tested in isolation, and has never decided anything — and the sentence it exists to make true is the one CAP-3 leads with. A build that derives claims and admits them on a count of *supports* rather than a count of *independent groups* would pass a casual reading and be exactly the failure story 3 predicted: "the belief set inflates with echoes and *bounded* fails in the first noisy month."

**Why matching stays inside one run, and what that defers.** A claim can gain support months later, from a source in another mailbox pull. Making that work needs durable candidates and a way to decide that two derived claims are the same claim — a second matching problem on top of this one. Within a run, two bodies that yield the same claim are two supports and the union-find does the rest, which is enough for CAP-3's stated criterion. **Cross-run accumulation is deferred, deliberately and on the record**, because the alternative is inventing a matching rule inside the story whose subject is a different rule.

**The body's one moment.** `scrub` produces the text and the receipt is written from it; between those two lines is the only place a body exists. Derivation belongs there, which also means the ordering *scrub, then derive* is a safety property rather than a style choice — a reordering sends unredacted mail to a provider. Assert it structurally, not by reading.

**What a reviewer should be hardest on.** Not the gates, which 15a settled, but two things: whether `independent` on a written claim is genuinely the union-find's answer rather than `len(support)`, and whether a body can reach a provider before `scrub` under any ordering, including an exception path.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_revealed.py -q` -- expected: the revealed path passes
- `cd half && uv run --extra dev pytest tests/test_scrub.py tests/test_secrets.py -q` -- expected: the secret path unbroken (NOT a `-m` expression: an unregistered name in one deselects everything and exits 0)
- `cd half && uv run --extra dev pytest tests/test_scrub.py tests/test_ingest.py -q` -- expected: story 3 unmoved
- `cd half && git status --porcelain` -- expected: clean tree after commit
