---
title: 'Story 15c — A claim worth hearing'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: '2f1ace2'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Half can say six things about a mailbox — *travels*, *buys things*, *pays for a subscription*, *keeps appointments*, *does paid work*, *studies*. Those six are the complete set. CAP-2 asks for a statement *"confirmed as true **and previously unstated by the main**"*, and nobody learns that they travel.

**Why it was six.** Story 15b's frozen block forbade persisting anything derived from a body *"including a summary or an embedding"*. That clause was **not AD-13's** — AD-13 forbids keeping the *body*, and its own accepted-cost note ("rebuild can no longer re-derive claims from original text") presumes claims are derived from bodies and kept. The clause was written into 15b in error, and the closed vocabulary is its consequence.

**Approach:** A claim derived from *scrubbed* text, in Half's own words, is not a body. Generate the claim instead of choosing it from a list, and let it carry the particulars that make it worth hearing.

## The two things this story is actually about

**Specificity and independence pull against each other, and that is the design problem.** CAP-3 admits nothing supported by fewer than two independent sources. The more specific a claim, the fewer sources genuinely support *it* — "travels" is corroborated by any two travel messages, while "three flights to Delhi since March" may be supported by one. A build that generates a specific claim and then vouches for it with the *label's* support has inflated its evidence, which is the failure story 3 predicted in different words: the belief set filling with things Half cannot actually stand behind. **A specific claim's support is the sources that support that claim, and if that is one, it is not admitted.**

**The bodies must meet, and 15b refused to let them.** `Candidate` carries a label, a source id, a thread id and a digest, with a docstring saying *"No body on this type, and no field one could travel in."* Generating over a group needs the scrubbed texts together. That is a real widening — from a body living inside one `async for` iteration to living for the run — and it is this story's Ask First, not a detail to resolve in passing.

## Boundaries & Constraints

**Always:**
- **Scrubbed text only, still never persisted.** `scrub` runs before anything, as in 15b, and that ordering stays a safety property asserted structurally. What may widen is how long scrubbed text lives in memory; what may not is that it reaches disk.
- **The support is the claim's own.** Independence is counted over the sources that support *this* claim, not over the sources that shared its label. A claim whose real support is one independent group is not admitted, however well it reads.
- **The label keeps doing the matching it already does.** Grouping by a closed label is exact and free; generation happens within a group, so this story does not reopen the cross-body matching problem — it only decides what a group's claim *says*.
- **One generation per admitted claim, not per body.** The classification stays cheap and per-body; the expensive call happens once, for a group that already cleared independence.
- **The claim is Half's own words**, never the body's — no quotation, no near-quotation of a source, and the AD-22 scans stay as they are.
- **15a's four gates still decide worth.** Decision-relevance, durability, independence and falsifiability are unchanged; this story changes what a claim *says*, not whether it is worth keeping.
- **Bounded and capped** on `half/model/consult.py`'s shape, cheap tier (`SPEC.md:124`), as a fifth caller and not a fifth copy.
- **Worldwide.** Bodies arrive in any script; the claim may be in the main's language or the source's, and neither is assumed.

**Ask First:**
- **How long scrubbed text may live.** The widening from one iteration to one run is the story's central request. If a narrower window would do — generating at the moment a group crosses two independent supports, holding only that group's texts — prefer it and say so.
- Any change to `scrub`, to `Receipt`, to 15a's gates, or to `independent_groups`.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- No body persisted, in any form, on any path. (This is AD-13's rule, and it is the whole of it.)
- No claim admitted on support it does not have.
- No quotation of a source's wording in a claim.
- No fifth copy of the consultation machinery.
- Do not change the stated path, the crisis path, or story 7's demonstration.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| A claim worth hearing | Two independent sources about one specific thing | One specific claim, citing both | CAP-2's target |
| Specific but alone | A vivid claim only one source supports | **Not admitted** | Never inflated evidence |
| Generic but supported | Two sources sharing only a label | Admitted only if a claim they both support can be made | Support is the claim's own |
| Ten in a thread | One cluster | No claim | CAP-3, unchanged |
| Gates refuse | Two sources, content fails a gate | No claim | 15a, unchanged |
| Not persisted | Any run | No body on disk, in any form | AD-13 |
| Scrub first | A body with a secret | Never reaches a provider or disk | Asserted structurally |
| The window | Any run | Scrubbed text lives no longer than the story's Ask First permits, and is gone after | Asserted |
| Half's own words | Any claim | No quotation or near-quotation of a source | Asserted |
| One generation | A group of ten supporting sources | One generation, not ten | Cost |
| Generator absent | No provider wired | No claim; receipts still captured | Never fatal |
| Generator slow or failing | Past the bound, or raising | That group yields no claim; the run completes | Never costs the run |
| Over the cap | Per-run cost exceeded | Stops generating and says so | Bounded |
| Re-ingest | The same mailbox twice | No claim derived twice | Idempotent |
| Any script | Mail in any writing system | Generated, with no English rubric on the path | Worldwide |
| Replay | A log of claims | Folds identically | AD-4, AD-30 |
| Nothing logged | Any generation | No body and no claim text in a log line | AD-22 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-2, CAP-3, CAP-5, CAP-13, AD-11, AD-13, AD-19, AD-22, AD-30 govern this story.

**Reference (extracted from the manifest):** none new; the union-find row is 15b's and unchanged.

**Existing, reused:** `half/derive/revealed.py` (the labels, the run, the independence pass — the label keeps its matching job), `half/derive/gates.py` (15a's four), `half/ingest/` (the pipeline, scrub, independence), `half/model/consult.py`, `half/voice/` (the *pattern* for a bounded generator — read it, do not copy it).

**To change:**
- `half/derive/revealed.py` — a group's claim is generated rather than named; support is the claim's own.
- `half/ingest/pipeline.py` — whatever the Ask First resolves about the scrubbed text's lifetime.
- `half/__main__.py` — wire the generator, pinned tier, budget.
- `.github/workflows/ci.yml` — extend the CAP-3 gates; margins stated.

**To amend:** 15b's frozen block — the "including a summary or an embedding" clause, corrected to AD-13's actual rule, with a Spec Change Log entry recording that the clause was mine and what it cost.

## Tasks & Acceptance

**Execution:**
- [x] 15b's clause amended, with the change log entry -- the error on the record
- [x] `half/derive/revealed.py` -- generated claims; support is the claim's own -- CAP-2, CAP-3
- [x] the scrubbed-text window -- as the Ask First resolves, asserted -- AD-13
- [x] one generation per admitted claim -- cost
- [x] `half/__main__.py` -- provider, pinned tier, budget, counters -- operable
- [x] `tests/` -- every matrix row, across scripts -- I/O matrix
- [x] `.github/workflows/ci.yml` -- gates extended, margins stated -- the floor lesson

**Acceptance Criteria:**
- Given two independent sources about one specific thing, when the run completes, then one specific claim exists citing both — and a case shows it is something a main could not have already known from the label alone.
- Given a specific claim only one source supports, when the run completes, then it is not admitted — asserted by a case that fails if the label's support is used instead of the claim's.
- Given any run, when every byte written is scanned, then no body appears in any form.
- Given a body with a secret, when it is ingested, then the secret reaches neither disk nor provider — the ordering asserted structurally, as 15b left it.
- Given a group of ten supporting sources, when the claim is generated, then exactly one generation occurs.
- Given any claim, when it is compared against its sources, then it quotes none of them.
- Given the scrubbed text, when the run ends, then none of it is still held — asserted, not assumed.
- Given the full suite, when it runs, then it passes offline with the provider stubbed and no network.

## Spec Change Log

- **The Ask First, answered: the narrow window, and what it does not reach.** The story asks for the narrowest window that works and names one — *generating at the moment a group crosses two independent supports, holding only that group's texts*. That is what is built, and it works. What has to be said plainly is the half the framing leaves out: **a label's texts must be held from its first candidate, not from its crossing.** The group's texts have to exist together at the crossing, and the crossing is the last of them, so holding "only that group's texts" still means holding them from the moment the label acquires its first support. A label that never crosses therefore holds its texts until the run ends, because nothing earlier can know that it never will. **Implemented as:** a per-label ceiling of `MAX_SOURCES = 8`, so live scrubbed text in a run is bounded by `len(DOINGS) × 8` — forty-eight bodies — rather than by the size of a mailbox; texts dropped in the same call that generates, admitted or refused, since there is no second generation to keep them for; nothing held at all for a label that has already generated; and `Run` made a context manager, so *the run ends* is a scope and the release happens on the exception path too. Nothing reaches disk and `scrub` still runs first, both asserted as before.

- **The quotation floor is four words, not `half.context.build`'s two, and that is a real departure.** The Never list says *"No quotation of a source's wording in a claim"*, and this tree already owns a reviewed, worldwide-correct near-quotation rule: story 4b's adjacent-pair rule, which `half.voice.leak` imports rather than restates. Applied here it deletes the capability. A revealed claim's whole job is to carry the particulars — a place, a date, a service, a number — and those are exactly the two-word runs it shares with the mail: at a floor of two, *"flies to Delhi most months"* quotes any email containing *"to Delhi"*, and no specific claim could ever be admitted. **Implemented as:** `half.context.build.runs(text, *, length)`, a generalisation of the existing `fragments` sharing its `_units` — so the *unit* stays 4b's, matras attached, invisible characters removed, folded by `half.text.normalize` — with only the length this caller's. Four consecutive words in the same order is wording rather than a particular. Both halves are asserted, because a rule that only ever answered *yes* would be indistinguishable from one that refused everything. **This was not put to a human**; if two was meant, this is the line to change, and the cost of changing it is the whole story.

- **`Doing.claim` is removed rather than left as a fallback.** With the sentence generated, the six shipped claim strings had no reader. Keeping them "in case the writer is absent" would have contradicted the matrix — *generator absent → no claim* — and left a closed vocabulary in the tree looking load-bearing, which is the dead-anchor shape this project hunts. What remains closed is the **label** (what a group is matched by) and the **subject** (what the nightly pass bounds its comparison on). One import-time guard went with it, *two labels write one claim*; two took its place, on the empty generated sentence.

- **The `MAX_SOURCES` ceiling chooses on independence, not on arrival.** A first-come ceiling is the obvious implementation and it is wrong in precisely CAP-3's own scenario: nine messages in one thread and a tenth on its own would fill the ceiling with the nine, drop the tenth, and generate over a single cluster of mentions — ten bodies read, a generation paid for, nothing admitted, in exactly the case where something should be. So a source bringing independence the held ones lack displaces one bringing none, using `independent_groups` itself. Found by a test, not by review.

- **A guard in `tests/test_bought.py` forbids an exception message in `half/context/build.py`.** The CAP-4 worldwide scan refuses *any* string constant in that file that reads as a phrase — two word characters with whitespace between them — because a hand-written question on the question path would read like a feature. It does not distinguish a template from a `ValueError` message, so `runs`' own refusal is spelled `f"runs:length={length!r}"` and the sentence lives in the docstring. Recorded rather than worked around silently: the rule is right and its blast radius is wider than its subject.

- **One existing CAP-2 assertion was corrected rather than adapted.** `test_only_the_claim_that_was_handed_in_is_quoted` compared *does the claim start with the first word of any withheld fragment*, which held only because 15b's claims were a single word and inverted the moment a claim became a sentence. It now compares the claim's own fragments against the withheld set, which is what the rule says.


## Design Notes

**Why the error is worth recording rather than quietly fixing.** A clause written into one story's frozen block as if it were the architecture propagated into a vocabulary, and that vocabulary made a capability unreachable two stories later — and nobody noticed until an implementer read AD-13 and found it said something narrower. The change log entry is the point: the next person to read 15b should see that its Never list once said more than AD-13 does, and why that mattered.

**Why the support rule is the hard half.** It is easy to generate a vivid claim and attach the label's support to it, and every test of *"is the claim specific"* would pass. The failure is invisible in the output and visible only in the evidence, which is exactly the shape of the defect story 3 built the union-find to prevent. A reviewer should assume this is wrong until a case proves the claim's own support was counted.

**Why the label keeps its job.** 15b solved cross-body matching for free by making "the same claim" exact equality on a constant. That property is worth keeping: this story changes what a group's claim *says*, not how bodies find each other. Reopening matching here would be two hard problems in one review.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_revealed.py -q` -- expected: the revealed path passes
- `cd half && uv run --extra dev pytest tests/test_scrub.py tests/test_ingest.py -q` -- expected: story 3 unmoved
- `cd half && uv run --extra dev pytest -m cap2 -q` -- expected: story 7's demonstration still works
- `cd half && git status --porcelain` -- expected: clean tree after commit
