---
title: 'Story 19 — The block that never leaves one company'
type: 'fix'
created: '2026-09-05'
status: 'in-progress'
baseline_commit: 'defc730'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 18 closed a real over-claiming hole and left one open. A body
that *is* a block other bodies also contain — a footer-only notice, an
auto-reply, a bounce, a policy line sent on its own — becomes an attractor:
everything containing it adopts its key and the voices merge. Measured through
the shipped path, thirty-one messages become **one** voice when such a message
arrives first. That is CAP-3's gate never opening, which is Half going quiet
everywhere while looking well-behaved.

**Approach:** Ask *who carries the block*, not what it looks like.

A legal footer is stapled by one organisation to its own outgoing mail. A
forwarded original travels between different senders — that is what forwarding
*is*. So a block confined to a single origin is that organisation's furniture
and must not make two messages one voice; a block that crosses origins is the
thing being passed on and must.

**Why the obvious homes and rules are excluded — measured, not assumed.**
`half/ingest/scrub.py` is the wrong home: `scrub(text: str)` sees one message
with no context, and boilerplate is not a property of one message. Story 18's
deferred entry says the fix belongs there; that entry is wrong and this story
corrects it.

Six candidate rules are dead ends, four inherited from story 18 and two
measured for this one. They are recorded so nobody re-derives them:

1. A bound on terms or size added — a forward-plus-footer adds 59 terms at
   5.2x, an attractor adds 61 at 8.6x; the ranges overlap in both directions.
2. Raising `MIN_TERMS` — attractors at 8, 8, 9, 10 distinct terms, realistic
   short originals at 7, 8, 9, 9, 10, 11; fully overlapping.
3. A frequency discount on a block seen often — inverts on a viral forward.
4. Flagging a held body contained in several mutually non-containing bodies —
   a viral forward has that exact shape.
5. **The pairwise remainder** (how much survives removing the block) — a footer
   standing alone and an original standing alone both leave nothing. *Pairwise
   there is no difference between them*, so no pairwise rule can ever work.
6. **The remainder across carriers** — a forward's own wrapper is boilerplate
   too, contributing 13 distinct terms per carrier, so forwards look exactly
   like strangers.

Only origin-crossing separates them, because it is the one signal that is not
in the text.

## Boundaries & Constraints

**Always:**
- **The origin is read, never unioned on.** Story 17 measured a mailbox
  collapsing when the sender became a union-find axis. This story reads the
  origin to *classify a block* and must leave `SAME_MOMENT_FIELDS`,
  `ORIGIN_AXIS` and the two-level structure exactly as they are, with story
  17's percolation margins unmoved.
- **Bounded by the held window.** The comparison sees the `MAX_SOURCES` bodies
  `Run.hold` already holds and nothing wider. Story 9d's "never all-pairs"
  binds; no pass over a mailbox, no new state, no second store.
- **Nothing persisted.** No body, no block, no shingle set, no sketch (AD-13,
  AD-22). Whatever this computes lives for the run and dies with it.
- **Worldwide.** The block is found with `half.text.terms()`, the tokenizer
  story 18 pinned. No locale-specific pattern for a disclaimer, a separator or
  a signature — those exist in every language and matching them is the failure
  this approach is chosen to avoid.
- **The direction of harm must not invert.** Story 18 traded an over-claiming
  defect for an under-claiming one. This story must not hand back the
  over-claim: if a rule cannot decide, it declines and the voices stay merged.

**Ask First:**
- Any change to `SAME_MOMENT_FIELDS`, `ORIGIN_AXIS`, or story 18's containment
  rule itself.
- Any durable state, per-sender history, or learned model of an organisation.
- Any parsing of an origin beyond what `half/ingest/independence.py` already
  does — in particular, deriving a domain is a **new sub-axis**, not a given.

**Never:**
- No pattern list for disclaimers, separators, quote markers or signatures.
- No rule that fires on how the text *looks* rather than on who carries it.
- No weakening of story 18's guards, its pinned limits, or the confound rows.

## I/O & Edge-Case Matrix

| Scenario | State | Expected | Why |
|---|---|---|---|
| A footer alone, then notes carrying it | one origin | Every message its own voice | The defect |
| A footer alone, notes from several people at one company | one origin | Every message its own voice | Furniture, not evidence |
| An original, then forwards of it | many origins | One voice | Story 18 preserved |
| A viral forward, eight carriers | many origins | One voice | The inversion that killed rules 3 and 4 |
| A forward carrying a footer too | many origins | One voice | Both blocks present |
| A forward inside one company | **one origin** | Two voices — **not caught** | Stated limit: indistinguishable from furniture |
| One carrier only | any | Story 18's answer, unchanged | Nothing to classify from |
| An origin that is absent or empty | — | Declines; never a match | Story 17's blank-origin rule |
| Scriptio continua and combining marks | any | Same answers as Latin | Worldwide |
| Story 17's percolation sweep | any density | No collapse, margins unmoved | No regression |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-3,
AD-13, AD-22, AD-30 govern. Anchors verified at `defc730`.

**Existing, reused:** `half/ingest/echo.py` (`declaring`, `inside`, `units`,
`own_key`, `MIN_TERMS` — story 18's rule, extended not replaced),
`half/derive/revealed.py` (`Run.declares`, `Run.hold`, `Candidate.sender`),
`half/ingest/independence.py` (`ORIGIN_AXIS`, `an_identity`, `_normalize` —
read, do not modify), `half/text.py` (`terms`), `tests/mailshapes.py` (the
shared fixtures story 18 consolidated), the three `tools/` simulations.

**The measurement that chose the rule**, reproducible: a company footer carried
by three senders at one domain plus the footer standing alone classifies as
furniture; one notice carried by four senders at four domains classifies as
substance. That is the whole discriminator.

**Where it goes:** `Run.declares` already assembles the held window. The
classification needs each held body's origin, which `Candidate.sender` carries
and `Run._texts` currently does not surface alongside the text.

## Tasks & Acceptance

**Execution:**
- [ ] the origin-crossing classifier, bounded by `MAX_SOURCES` -- CAP-3
- [ ] the held window carries each body's origin -- `Run.declares`
- [ ] story 18's containment rule consulted, not replaced
- [ ] every matrix row tested, the intra-company limit asserted as a limit
- [ ] `tools/percolation_sim.py` -- the footer-only rows stop collapsing
- [ ] story 17's and story 18's guards re-run, margins stated

**Acceptance Criteria:**
- Given a footer-only message and thirty notes carrying it from one origin,
  when the run counts, then there are thirty-one voices — the number story 18
  records as one.
- Given one notice and eight forwards from eight origins, when the run counts,
  then there is one voice, and the same suite must fail if the classifier is
  disabled.
- Given a forward inside one company, when the run counts, then there are two
  voices, asserted as a recorded limit with its direction of harm.
- Given story 17's percolation sweep and story 18's confound rows, when both
  run, then no collapse at any density and every confound still holds.
- Given an absent or empty origin, when a block is classified, then the rule
  declines rather than treating blankness as agreement.

## Design Notes

**The limit this leaves, stated up front.** A forward that never leaves one
organisation looks exactly like that organisation's furniture, because on the
only signal that works it *is* the same shape. Half will count it as two
supports. That is the over-claiming direction — the one story 18 closed — so
it is the more serious residue and must be recorded as such, not buried.

**Why "declines" is the safe default everywhere here.** Story 18 established
that this rule's failures should merge rather than split, because Half saying
less is the conservative failure. That is no longer automatically true: this
story can also cause a *split*, which admits claims. Every branch that cannot
decide must therefore fall back to story 18's answer, not to "independent".

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- all pass
- `cd half && uv run --extra dev python tools/percolation_sim.py` -- no collapse; footer-only rows resolved
- `cd half && uv run --extra dev python tools/mailbox_sim.py` -- 0 of 5 miscounted
- `cd half && uv run --extra dev python tools/admits_sim.py` -- the forward admits nothing
- `cd half && git status --porcelain` -- clean after commit
