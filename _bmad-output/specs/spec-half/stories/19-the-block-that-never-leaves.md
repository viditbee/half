---
title: 'Story 19 — The block that never leaves one company'
type: 'fix'
created: '2026-09-05'
status: 'done'
baseline_commit: 'defc730'
review_loop_iteration: 1
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

**A domain is not an organisation, and the first build proved it.** Review
measured what this spec's first version missed: two people at `gmail.com` are
not one company, so an ordinary forward between them was classified as that
"organisation's" furniture, refused to collapse, and became **two supports from
one message** — the over-claiming defect story 18 closed, handed back for what
is plausibly the commonest sender population in a personal mailbox. Measured:
`gmail.com` 2 voices, `outlook.com` 2, one university 2, where the truth is 1.

So a domain that hosts many unrelated people — a webmail provider, an ISP, a
university — is **not** an organisation, and a block carried only there tells us
nothing. Those decline, which is story 18's answer and the merging direction.
A domain not on that list is treated as an organisation, which is what keeps the
footer attractor fixed.

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
  The shared-domain list is **not** an exception to this: it names *origins*,
  never text, and it is data about the world rather than a rule about language.
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
| A forward inside one company | one organisation | Two voices — **not caught** | Stated limit: indistinguishable from furniture |
| A forward between two people on one webmail provider | shared domain | **One voice** | The regression review found; must not return |
| The same, on an ISP or a university | shared domain | One voice | Same shape, same answer |
| A forward on a provider absent from the list | unknown domain | Two voices — **not caught** | The list is incomplete by nature; recorded, with its direction |
| The arriving body's origin, through `observe` | production path | Reaches the classifier | Blanking it must turn cases red |
| Furniture match before a travelling one | window order | The forward still adopts the original | The step-over, currently unpinned |
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
- [x] the origin-crossing classifier, bounded by `MAX_SOURCES` -- CAP-3
      (`echo.travelled`, `echo.carrying`, `echo.organisation`)
- [x] the held window carries each body's origin -- `Run.declares`, from
      `Candidate.sender`; no new state, nothing persisted
- [x] story 18's containment rule consulted, not replaced -- `declaring` still
      answers containment first and narrows *first match* to *first travelling
      match*, so strictly more of story 18's rule reaches its answer
- [x] every matrix row tested, the intra-company limit asserted as a limit
      (`test_a_forward_inside_one_company_is_not_caught`), plus a mutation guard
      that fails the suite with the classifier switched off
- [x] `tools/percolation_sim.py` -- the footer-only rows stop collapsing, with
      the many-company control and the story-18 column beside them
- [x] story 17's and story 18's guards re-run, margins stated below
- [x] **loop 1** — the shared-domain exclusion (`echo.shared`,
      `SHARED_DOMAINS`, `SHARED_HOSTS`, the academic shape), worldwide and
      asserted to be so
- [x] **loop 1** — the arriving origin's production wiring, pinned through
      `Revealed.observe`; blanking it now reddens a case
- [x] **loop 1** — the first-travelling-match step-over, pinned on an ordering
      that puts a furniture match ahead of a travelling one

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
- Given a forward between two addresses at one webmail provider, ISP or
  university, when the run counts, then there is one voice — with a corporate
  domain as the control, so the case cannot pass by declining everything.
- Given the production path, when `origin` is blanked at the `observe` call
  site, then cases go red. The suite currently passes unchanged with story 19
  switched off there, and that must stop being true.
- Given a held window where a furniture match precedes a travelling one, when a
  forward arrives, then it adopts the original's key. Making the loop exit on
  the first match regardless currently leaves the suite green, and that must
  stop being true.

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

**Measured, at `defc730` + this change** — the baseline the frontmatter and the
Code Map both name; the earlier draft of this section said `a8a93bf`, which is
the spec commit rather than the code baseline:

- `pytest -q` — **5293 passed**, from 5260 at `defc730`. CAP-3 gates
  **32 / 63 / 98**, margin zero. Exactly two floors moved, each verified against
  its own gate; the AD-28 floor was moved by accident in a bulk edit and
  restored.
- **Story 17's percolation margins are unmoved.** 50 messages / 40 people /
  45 threads: flat 13, levels 24, no-3rd 28. 1000 / 100 / 400: flat 1, levels
  285, no-3rd 341. The frozen matrix still has all three rules agreeing on 9 of
  9 hand-built shapes.
- **Story 18's numbers are unmoved.** `seq` one key per message at every density
  and unbounded; `set` 475 of 500, 957 of 1000, 269 of 300; `frac` 3 at every
  row.
- **The footer-only rows resolve.** 31 messages with the block arriving first:
  **31** voices where story 18 counted **1**; arriving sixth **31** where it
  counted **5**. The eight-term line: **7** where it counted **1**, and **7**
  where it counted **3**. Same in all nine scripts.
- **The control that makes it a discriminator rather than a switch-off.** The
  same bodies in the same order with every sender at a domain of their own read
  1, 5, 1, 3 — exactly the story-18 column — because the block then crossed
  organisations and is being passed on.
- `tools/mailbox_sim.py` **0 of 5 miscounted**; `tools/admits_sim.py` the
  forward counts 1 and admits nothing.
- **Mutation-checked six ways.** Making `travelled` always answer yes, making
  `organisation` return the whole address, and making a webmail provider resolve
  to an organisation all fail `echo._check_rule` at import, by name. Deleting
  the classification from `declaring` leaves **23** cases in
  `tests/test_echo.py` red. Blanking
  `origin=receipt.sender` at the `Revealed.observe` call site — which left the
  whole suite green before loop 1 — now reddens
  `test_the_arriving_origin_reaches_the_classifier_through_observe`. Replacing
  the step-over `continue` with a `break` — also green before loop 1 — reddens
  `test_a_furniture_match_before_a_travelling_one_is_stepped_over` and the join bound in
  `test_the_comparison_is_bounded_by_the_held_window`, since breaking early
  changes the join count too.

**Loop 1, measured:**

- **The regression closed.** A forward between two addresses at one webmail
  provider, ISP or university is **one** voice, where the first build made it
  **two supports from one message**. Each of the three is a row with the same
  pair at a real company as its in-case control, so the row cannot pass by
  declining everywhere.
- **The list is worldwide by assertion**, not by intention: a provider from each
  of fifteen regions, so deleting a continent's worth fails.
- **Cost.** A window of eight costs eight tokenizations, eight joins and eight
  domain reads per arriving message, plus one join and eight searches per match.
  The first build rebuilt both sides of the search per held body per match — up
  to sixty-four joins — and re-derived every organisation on every call.
- The sweep's control column is **checked and exits non-zero**, not printed; its
  anti-drift probe is a `cap3_structure` case, crosses both classifier branches,
  and reports 0 of 8 disagreements with 2 reaching the furniture branch.

**Residue, recorded in `deferred-work.md` and each pinned by a case:**

- **LAUNCH-RELEVANT, over-claiming** — a forward inside one organisation counts
  as two supports and crosses CAP-3's floor. Stated up front.
- **Over-claiming** — the same, reached through the shared-domain list's
  incompleteness: a forward on a provider it does not know.
- **Over-claiming** — a held body past the tokenizer's ceilings is a carrier
  `carrying` cannot see, which biases towards splitting.
- **Over-claiming** — `normalized` casefolds, so two domains differing only by
  `ß`/`ss` read as one organisation.
- **Merging** — a footer stapled by a shared-domain sender (a university mailing
  its own students) still collapses the messages carrying it; the exclusion
  cannot tell that block from a forward between two people there.
- **Merging** — an IDN's Unicode and `xn--` spellings read as two organisations.

## Spec Change Log

**2026-09-05, loop 1 — the shared-domain exclusion.** Triggered by review
finding that a forward between two `gmail.com` addresses counted as two
supports: my discriminator treated any domain as an organisation, and a webmail
provider is not one. Amended Intent, Never, the matrix and the acceptance
criteria to carry the exclusion, and added the two verification gaps review
demonstrated — the arriving origin's production wiring and the first-travelling-
match step-over — both of which could be disabled with the full suite green.

Known-bad state avoided: shipping a rule that fixes a narrow shape (a
footer-only message) while breaking the common one (an ordinary forward between
two people on one provider).

KEEP, and do not re-derive: the containment rule and every story 18 guard; the
origin read but never unioned on; the merge-on-cannot-decide fallback; the
minimal `@`-tail derivation with no public-suffix list or subdomain folding; the
bounded window; nothing persisted; the six recorded dead ends.

**2026-09-05, loop 1 — implemented.** The exclusion, the two switch-off gaps and
the review's patch list are in. Two findings I did not implement as asked, with
the reason:

- *"Consider whether `normalized`'s casefold is right for a domain."* Considered
  and kept. Casefolding is wrong for a domain in one shape — `ß` folds to `ss`,
  so two companies read as one, which splits. Replacing it means a second
  normalisation idea in `echo`, which is the drift the shared function exists to
  close, and the KEEP list holds the minimal derivation. Recorded with its
  direction and pinned in both directions instead.
- *"Matrix rows are cited by number and rows 3 and 10 have no case."* Row 3 (an
  original and several forwards) now has one and row 10 (the production path)
  is the `observe` case. The numbered citations elsewhere are **story 18's**
  matrix, not this one; they are relabelled `Story 18's matrix row N` rather
  than renamed, because renaming thirteen descriptions I do not have the
  original matrix for would risk describing them wrongly.
