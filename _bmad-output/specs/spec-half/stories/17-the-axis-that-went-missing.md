---
title: 'Story 17 — The axis that went missing'
type: 'fix'
created: '2026-09-05'
status: 'done'
baseline_commit: '6acab8d'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The independence machinery has no origin axis. `IDENTITY_FIELDS` is thread, content, declared — so two messages from **one sender** in two threads count as **two independent supports**, and CAP-3 admits at two. A shop's newsletter corroborates itself.

Both upstream sources say otherwise. The extraction manifest records the machinery as collapsing *"sources sharing **origin**, content hash, or **publisher**"*. Story 3's own frozen block says *"union-find over **origin**, content hash, and declared key"*. The implementation substituted *thread* for *origin* and dropped publisher.

**Measured, not argued.** `tools/mailbox_sim.py` over a realistic mailbox: two of five shapes miscounted. `tools/admits_sim.py` end to end: **two of four admitted claims rest on evidence a person would call one source** — a newsletter mailing eight times, and a forward of one notice.

**Why eleven stories missed it.** `tests/test_independence.py`'s `source()` helper takes a `sender`, stores it in the fixture, and `identity_set` never reads it. Every fixture *looks* like it exercises a sender axis. `test_a_forward_from_another_sender_collapses_by_content` varies the sender across ten messages and passes because they share a **thread**. `test_revealed.py`'s `receipt()` hardcodes `sender="a@x"`, so nothing there varies it either.

**Approach:** Give the union-find the axis it was extracted with. The data already exists — `Receipt` carries the sender and `Candidate` drops it.

## Boundaries & Constraints

**Always:**
- **Origin is an identity axis**, alongside content and declared. Two sources sharing an origin are one support, exactly as ten messages in one thread already are.
- **The sender travels from the receipt to the candidate.** `Receipt.sender` exists; `Candidate` must carry it and `identity()` must supply it. No new field is invented and nothing is derived.
- **Normalisation is `_normalize`'s**, unchanged — NFC and casefold, so two spellings of one address match. An address is not parsed, split at `@`, or lowercased by a second rule.
- **A missing or empty origin is not an identity.** `identity_set` already skips absent values, and that behaviour is what stops a source with no sender unioning with every other one. Assert it, because it is the difference between a fix and an outage.
- **The fixtures' dead field becomes live**, and every case that reads as a sender case must be re-read: a case that passed because of the thread now has two reasons, and one of them was never true.
- **The simulations move with it.** `tools/mailbox_sim.py` and `tools/admits_sim.py` are the acceptance evidence, and their output is expected to change — the newsletter and the forward should stop being miscounted.

**Ask First:**
- Any axis beyond origin, content and declared — the three the manifest and story 3 both name.
- Any parsing of an address (domain extraction, plus-addressing, display-name stripping). That is a matching rule, and this story adds an axis rather than a rule.
- Any change to `Receipt`, to `scrub`, or to what a receipt retains.

**Never:**
- No new field on `Receipt`.
- No inference of an origin where a source has none.
- No change to the admission floor of two.
- Do not fix the forwarded-message hole here — a forward from a *different* sender is a different origin, and collapsing it needs content similarity, which is a separate problem with its own story.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| A newsletter | One sender, eight threads | **One** support | The defect, closed |
| Two businesses | Two senders, two threads | Two supports | Unchanged |
| One thread | Ten senders, one thread | One support | Unchanged |
| One sender, one thread | The ordinary reply chain | One support | Unchanged |
| Address spelling | `A@X.com` and `a@x.com` | One support | `_normalize`, unchanged |
| No sender | A source with the field absent or empty | Not an identity; unions with nothing | Never an outage |
| A forward | Same content, different sender | Still two — not this story's | Recorded, deferred |
| Declared key | A source declaring what it matches | Unchanged | Story 3 |
| The simulations | `tools/` over a realistic mailbox | Newsletter and forward counts change; the rest do not | Acceptance evidence |
| Admitted claims | The end-to-end simulation | The newsletter no longer produces a claim | CAP-3 |
| Receipt to candidate | Any ingested message | The sender travels; nothing is derived | N/A |
| Replay | Any log | Folds identically; independence is not in the fold | AD-4, AD-30 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-3, CAP-5, AD-3, AD-30 govern this story.

**Reference (extracted from the manifest):** the **claude-obsidian** union-find row, which is what this story restores. Its wording — *origin, content hash, or publisher* — is the specification the implementation drifted from. Correct the row if it now overstates what was taken.

**Existing, reused:** `half/ingest/independence.py` (`IDENTITY_FIELDS`, `identity_set`, `_normalize`), `half/ingest/pipeline.py` (`Receipt.sender`), `half/derive/revealed.py` (`Candidate`, `identity`).

**To change:**
- `half/ingest/independence.py` — the origin axis.
- `half/derive/revealed.py` — `Candidate` carries the sender and supplies it.
- `tests/test_independence.py` — the dead field becomes live; every sender case re-read.
- `tests/test_revealed.py` — `receipt()`'s hardcoded sender becomes a parameter, and the cases that need it to vary say so.
- `.github/workflows/ci.yml` — gates move with their counts; margins stated.

## Tasks & Acceptance

**Execution:**
- [x] `half/ingest/independence.py` -- origin as an identity axis -- CAP-3, the manifest
- [x] `half/derive/revealed.py` -- the sender travels from receipt to candidate -- no new data
- [x] a source with no origin unions with nothing -- the difference between a fix and an outage
- [x] `tests/test_independence.py` -- the dead field live, every case re-read -- the reason this survived
- [x] `tests/test_revealed.py` -- the sender varies where it matters -- same reason
- [x] `tools/` -- the simulations rerun and their output recorded -- acceptance evidence
- [x] `.github/workflows/ci.yml` -- floors moved, margins unchanged -- the floor lesson

**Acceptance Criteria:**
- Given eight messages from one sender across eight threads, when independence is counted, then the answer is one.
- Given a source whose sender is absent or empty, when independence is counted, then it unions with nothing and no run is emptied — asserted, because the failure mode of this fix is silence.
- Given `tools/mailbox_sim.py`, when it runs, then the newsletter shape is counted correctly and the previously-correct shapes are unchanged.
- Given `tools/admits_sim.py`, when it runs, then the newsletter no longer produces an admitted claim, and the airline-and-hotel shape still does.
- Given `tests/test_independence.py`, when a case names a sender, then it fails if the sender axis is removed — asserted per case, because today none of them would.
- Given the full suite, when it runs, then it passes offline; the counts that change are those that were resting on the missing axis.

## Design Notes

**Why this is a fix and not a feature.** Nothing here is new. The manifest says the extracted machinery collapses on origin; story 3's frozen block says the same; `Receipt` already carries the sender. The axis was lost between the specification and the implementation, and every fixture since has passed a sender that nothing read.

**Why the fixtures are half the work.** A test that supplies a field the implementation ignores is worse than no test: it tells a reader the axis is covered. Making the field live is not enough — every case that currently passes will still pass, some for a new reason and some for the old one, and the ones that were only ever testing the thread must be made to say so. A case that cannot fail when the axis is removed is not evidence.

**Why the forward stays broken.** A forward from a different person genuinely has a different origin, so no axis collapses it. That needs content similarity over scrubbed bodies — a real problem with a real cost, and putting it here would hide a small correct fix inside a large uncertain one.

**What a reviewer should be hardest on.** The empty-origin case. This fix makes things collapse, and the failure mode of a collapsing fix is that everything collapses into one support and Half goes quiet — which looks like restraint and is a bug.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_independence.py tests/test_revealed.py -q` -- expected: the axis and its consumers pass
- `cd half && uv run --extra dev python tools/mailbox_sim.py` -- expected: newsletter counted 1; others unchanged
- `cd half && uv run --extra dev python tools/admits_sim.py` -- expected: the newsletter admits nothing
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Evidence

**Baseline `6acab8d`, 5178 tests green. After: 5209 green.** Purged bytecode
and a re-asserted green baseline on both sides of every probe.

### The first version shipped an outage, and this is the record of it

Commit `716514d` did what this story's intent block, the extraction manifest
and story 3's frozen block all say: the origin added to the identity table
alongside the thread. **Union-find is transitive across axes**, so A shares a
thread with B, B shares a sender with C, and all three are one group. Measured
on the shipped function:

```
  msgs  people  threads   groups
    50      40       45       13   healthy
   200      60      120        7   healthy
   500      80      200        1   COLLAPSED
   500      20      200        1   COLLAPSED
   500      10      400        1   COLLAPSED
```

One is below CAP-3's floor of two, so such a mailbox admits nothing, for ever.
The symptom is silence, not a wrong claim. Story 3's implementation carried a
comment predicting this; the first version deleted it, and the case written to
prevent the collapse was built with one sender per thread — so the chaining
could not occur in it. **A fixture built so the failure it guards against
cannot happen in it** is a twelfth way a check passes for the wrong reason on
this project, and a sibling of the eleventh.

### What ships

Two levels, and nothing chains between them. Union-find over thread, content
and declared key gives *voices*; each voice answers to its single origin if it
has one, stands for itself if it has none, and adds nothing if everyone in it
already wrote separately. The second level is a map decided against a set fixed
before any of it is asked, so no answer can change another.

`tools/percolation_sim.py` carries both rejected rules and sweeps them:

```
  msgs  people  threads   flat  levels   no-3rd
    50      40       45     13      24       28
   200      60      120      7      73       87
   300      60      150      1     104      117   COLLAPSED
   500      80      200      1     154      169   COLLAPSED
   500      20      200      1      47      148   COLLAPSED
   500      10      400      1      10      142   COLLAPSED
  1000     100      400      1     285      341   COLLAPSED
```

The third clause is measured, not tidy: without it, 500 messages from **ten
people** count as 142 supports — over-counting by fourteen times, the mirror of
the percolation and the direction CAP-3 exists to refuse.

**All three rules get every one of the nine hand-built matrix shapes right**,
which the tool prints above the sweep, because that is the lesson: the rules
only disagree at a size no fixture reaches.

### The frozen matrix, re-run rather than reasoned about

Every row holds. Five could not be reasoned about and were checked:

| Row | Why it needed checking |
|---|---|
| One thread, ten senders | The literal *count distinct origins* gives ten. It holds only because a voice with several speakers is clamped to one contribution. |
| Declared key | Depends on it being a **same-moment** axis. At the origin level a single crafted key would merge unrelated voices — the percolation again, through a field the sender controls. |
| A forward | Ambiguous between the real forward (new thread, new digest → **2**) and the byte-identical one (→ **1**). Both checked. |
| No sender | Depends on `adds_a_voice` answering true for a voice with nothing readable. |
| Address spelling | Depends on normalisation happening in `origin_of`, not in the union-find. |

### The two existing simulations

`mailbox_sim`: newsletter 8 → **1**; shapes miscounted 2 of 5 → **1 of 5**.
`admits_sim`: newsletter counted 2 / admitted 1 → **counted 0 / admitted 0**;
airline + hotel unchanged at 2 and 1. The forward is untouched and is now the
only thing either simulation reports.

### Names

`independent_groups` keeps its name: it names the answer, not the mechanism.
What was renamed is everything that implied one flat level, because a table
called *the identity fields* is exactly what invited *just add the origin to
it*: `IDENTITY_FIELDS` → `SAME_MOMENT_FIELDS`, `identity_set` →
`same_moment_set`, `names_the_origin` → `unions_the_origin` with its sense
inverted — the guard now refuses a table that unions the origin, and its
message names the tool that measures why.
