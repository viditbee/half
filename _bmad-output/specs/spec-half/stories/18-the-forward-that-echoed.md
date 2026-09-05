---
title: 'Story 18 — The forward that echoed'
type: 'feature'
created: '2026-09-05'
status: 'done'
baseline_commit: 'a3fa9d0'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Forward an email to yourself and Half counts it twice. The content
axis of the same-moment union-find is a digest — byte equality — and a forward
is never byte-identical: it wraps the original in `FYI` and a separator. So the
original and its forward share no thread, no digest and no sender, and CAP-3's
admission floor of two independent supports is crossed by **one** message that
travelled. That is the precise failure CAP-3 exists to prevent, reached by the
most ordinary thing a person does with mail.

Story 17 restored the origin axis and fixed the newsletter. This is the other
half of the same defect, and the one story 17's own simulation still reports as
the last miscounted shape of five.

**Approach:** Fill the socket story 15b deliberately left. `Candidate.identity`
says `independence_key` is "for a source that can *declare* what it is the same
as; mail cannot, and inventing one here would be a matching rule of exactly the
kind this story defers." This story is that deferred rule, and it plugs into the
existing declared axis rather than adding a fourth one.

The rule is **containment, not similarity**: a forward *contains* the original.
Measured on realistic bodies, a forward and a quoted reply both sit at exactly
100% containment because a superset contains its subset by construction, while
the nearest confound — two short notes sharing one long legal disclaimer — tops
out at 95%. The separation is structural, so the rule is "one body contains the
other", not a tuned threshold.

**Why this may be a union-find axis when the sender could not.** Story 17
measured the sender axis percolating a mailbox into one group, because
union-find is transitive *across* axes and "shares a sender" chaining through
"shares a thread" links strangers. Containment chains only with itself, and a
chain of containments is a genuine chain of derivation: if A is inside B and B
is inside C, A really is inside C. The transitivity that made the sender an
outage is what makes this axis correct. **That argument must be measured, not
trusted** — see Verification.

## Boundaries & Constraints

**Always:**
- **The comparison happens where the body exists and nowhere else.** AD-13
  allows a body to be normalised, scanned, handed to its consumer and discarded.
  `Run.hold` is the one place a body is in hand, so the comparison lives there
  and its output is a key, never a stored text.
- **Bounded, and never all-pairs.** An arriving body is compared against the
  held bodies for its label, which `MAX_SOURCES` caps at 8. Story 9d's rule
  stands: no pass over every candidate, no O(n²) over a mailbox.
- **The output is the existing declared axis.** `independence_key` on the
  candidate, read by `SAME_MOMENT_FIELDS`' `declared` entry. No fourth axis, no
  third level, no change to `ORIGIN_AXIS`.
- **Containment is near-total or it is nothing.** The floor is set so the
  disclaimer confound at 95% is *not* a match; a rule that fires below total
  containment is a similarity rule and is out of scope.
- **Latin is not the case, and the tokenizer decides whether that is true.**
  Half ships worldwide. The comparison tokenizes with `half.text.terms()` —
  story 4c's script-aware tokenizer — and **not** with `half.context.build.runs()`.
  Measured: `runs()` is whitespace-based, so on Japanese, Chinese and Thai a
  forward that contains its original verbatim scores **0%** containment and the
  rule silently does nothing for those scripts. `terms()` scores 100% on all
  seven scripts tested. Scriptio-continua and combining-mark scripts are
  first-class rows, not an afterthought.
- Nothing here reads a clock inside a fold; the fold stays pure (AD-30).

**Ask First:**
- Any change to `SAME_MOMENT_FIELDS`, `ORIGIN_AXIS`, or the two-level structure
  story 17 measured into place.
- Any comparison whose cost is not bounded by `MAX_SOURCES`.
- Any persistence of a body, a sketch of a body, or a shingle set (AD-13, AD-22).

**Never:**
- No body, and no reconstructable fragment of one, in the log, a projection, an
  error, or a test fixture's expected output.
- No similarity rule dressed as containment — no tuned threshold justified by
  making one fixture pass.
- Do not touch the origin level. Story 17's percolation guard stays exactly as
  it is, and this story must leave its margin unchanged.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Why |
|---|---|---|---|
| A forward | The original held, its forward arrives | One voice — the forward declares the original's key | The defect |
| A reply quoting in full | Original held, quoted reply arrives | One voice | Same echo |
| A forward carrying a footer | Original + separator + disclaimer | One voice | Wrapping is still containment |
| Two notes, one disclaimer | Neither contains the other (95%) | **Two voices** | The confound; must not fire |
| Airline and hotel | 0% overlap | Two voices | Genuine corroboration survives |
| A chain | A ⊆ B ⊆ C, all held | One voice | Containment is transitive |
| Beyond the ceiling | The original was never held | Two voices — not caught | Stated limit, not a silent gap |
| A different label | Original held under another label | Two voices — not caught | Stated limit |
| Scriptio continua | Japanese, Chinese, Thai forward | One voice | Worldwide |
| Combining marks | Devanagari, Arabic, Hebrew forward | One voice | Worldwide |
| An empty body | Nothing to compare | Its own voice, never a match | Empty must not match empty |
| A very short body | Two words, coincidentally shared | Its own voice | Below a length the rule declines |
| The origin level | Any of the above | Unchanged from story 17 | No regression |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-3, AD-13,
AD-22, AD-30 govern this story. All anchors below verified at `a3fa9d0`.

**The socket, and why it is open.** `half/derive/revealed.py:463-467` says
`independence_key` is "deliberately not supplied … mail cannot [declare], and
inventing one here would be a matching rule of exactly the kind this story
defers." `tests/test_independence.py:448-452` seconds it, and
`deferred-work.md:323` records story 17 leaving it open on purpose because
"putting content similarity in that story would have hidden a small correct fix
inside a large uncertain one." **This is a deferral, not a rejection** — no
author argued the rule must never exist. That distinction is the whole reason
this story is not a repeat of story 17's mistake, and the implementer should
confirm it rather than take this paragraph's word for it.

**Where the key is set — take the third option, not the obvious two.**
`revealed.py:1234-1250` constructs one `Candidate`, passes that *same instance*
to `into.add(candidate)` and then `into.hold(candidate, body)`. `add` appends to
`_by_label`; `hold` appends to `_texts`; **`ready` and `_groups` read
`_by_label`.** So:
- `dataclasses.replace()` inside `hold` — the tree's usual rebuild pattern
  (`half/context/channels.py:293-298`) — puts the key only in `_texts`, where
  nothing counts it. The rule would be green and inert.
- `object.__setattr__` on the frozen+slots dataclass works (the slot exists),
  but every existing use in this tree is inside `__post_init__`
  (`channels.py:131-181`, `onboard/consent.py:112`, `voice/compose.py:210`);
  from an external caller it would be a new pattern.
- **Preferred:** ask the run for the match *before* the candidate is built, so
  the key is a constructor argument and nothing is mutated. `Candidate`
  (`:415-471`, `frozen=True, slots=True`, all fields required) gains
  `independence_key: str = ""`.

**The empty key is already safe.** `same_moment_set` (`independence.py:218-235`)
gates every field through `an_identity` (`:101-113`): absent and
present-but-empty behave identically and union nothing. `""` is the correct
"no match" sentinel and creates no outage. Values are NFC + strip + casefold
normalised (`:116-118`), so a hex digest is a stable key.

**The tokenizer.** `half/text.py::terms()` — story 4c's script-aware tokenizer.
**Not** `half/context/build.py::runs()`, which is whitespace-based: measured
independently twice, a Japanese, Chinese or Thai forward containing its original
verbatim scores **0%** containment under `runs()` at length 3, because
scriptio-continua collapses to sentence granularity. Match
`particular.py:456`'s precedent of pre-collapsing whitespace and comparing a
source whole rather than line by line (`:446-450`).

**What a body looks like at `hold`.** `scrub()`
(`half/ingest/scrub.py:97-116`) removes **secrets only**; `normalize.py` decodes
transfer encoding, charset and markup. Nothing strips quoted blocks, `>`
prefixes, `---- Forwarded message ----` separators, signatures or legal footers.
The forwarded original arrives intact — which is what makes containment work and
what makes the 96% disclaimer confound real. `hold` refuses a non-`Scrubbed`
body at `:752-753`; that type check is load-bearing.

**The one certain red.** `tests/test_revealed.py:629` (marked `cap3_structure`)
asserts `set(identity) == {"thread_id", "sender", "digest"}` — an exact-set pin.
Supplying a fourth key fails it and the gate at `ci.yml:1642`. Update the
assertion; do not weaken it to a subset check.

**CI floors, all at exactly zero margin** — any case added owes a floor edit,
anchored on its own line and verified to move exactly one number:
`cap3` 31 (`ci.yml:1585`), `cap3_structure` 37 (`:1642`), `cap3_axes` 41
(`:1747`), `cap3_particular` 65 (`:1920`), `offline` 20 (`:3433`).
All four `cap3*` markers are registered; there is no `ad13`/`ad22`/`ad30`
marker, so do not write a `-m` expression using one — it deselects everything
and exits 0.

**A new module in `half/ingest/` must:** import stdlib or `half` only
(`tests/test_dependencies.py:58`), and name no HTTP client
(`tests/test_gmail_transport.py:740-760` asserts `gmail_transport.py` is the
only reaching module). It is exempt from `test_bought.py`'s phrase scan, so
ordinary English error messages are fine.

**The simulations.** `tools/percolation_sim.py` already writes
`independence_key` via its `s(..., declared=)` helper (`:108`) and exercises it
at `:131-133`; the anti-outage case belongs in the density sweep (`:169-172`),
not the frozen matrix. `tools/mailbox_sim.py::counted` (`:127-132`) **synthesises
a digest and never touches the body**, so it cannot see this rule at all —
moving its forward row to `ok` requires it to compute the key from `m.body`.
Change it to exercise the real rule; do not change the expected numbers.
`tools/admits_sim.py` builds real `Receipt`s and runs the real reader, so it
picks the rule up for free once the key is set.

## Tasks & Acceptance

**Execution:**
- [x] `half/ingest/echo.py` -- the containment rule, bounded by `MAX_SOURCES`, worldwide -- CAP-3
- [x] wired at `Run.declares`, asked where `Run.hold` holds -- AD-13
- [x] `Candidate.identity` supplies the declared key; its docstring corrected
- [x] `tests/test_echo.py` -- every matrix row, the two limits asserted as limits
- [x] the percolation guard extended to carry this axis -- and it caught the specified rule
- [x] `tools/mailbox_sim.py` re-run; the forward row moves to ok -- 0 of 5 miscounted

**Acceptance Criteria:**
- Given the original and its forward, when both are held, then the label has one
  independent support and no claim is admitted on them alone.
- Given two short notes sharing one long disclaimer, when both are held, then
  they remain two supports — asserted at the measured 95%, so a floor that
  drifts below it fails.
- Given a mailbox of unrelated mail all carrying one disclaimer, when the rule
  runs, then the number of groups equals the number of messages — the outage
  case, carrying its own counterexample the way story 17's does.
- Given forwards in Japanese, Chinese, Thai, Devanagari, Arabic, Hebrew and
  Korean, when each is held with its original, then each is one voice — and the
  same suite run against `half.context.build.runs()` must fail, so the tokenizer
  choice is pinned by a test rather than by this sentence.
- Given story 17's percolation simulation, when it runs with this axis live,
  then no collapse occurs at any density and the origin margin is unchanged.

## Design Notes

**The tokenizer is the story, not a detail.** The first draft of this spec
named `runs()`, and measurement showed it returns 0% containment for a forward
in Japanese, Chinese or Thai — the rule would have shipped green, passed a
Latin test suite, and been dead for a large share of the world. `terms()` is
already in this tree because story 4c hit the same wall in retrieval. Measured
containment with `terms()`, k as it defines it: every forward and quoted reply
at exactly 100% across Latin, Japanese, Chinese, Thai, Devanagari, Arabic and
Korean; the nearest false positive — two one-line notes sharing one long legal
disclaimer — at 96%; airline-versus-hotel at 44%. A floor of 0.98 sits two
points from both sides. The positives are at exactly 1.0 because a forward is a
superset, which is why this is a structural rule and not a tuned one.

**The measured confounds, as fixture data.** All with `half.text.terms()`,
taken against this tree at `a3fa9d0`. Fires at a floor of 0.98:

| Pair | Overlap | Must fire |
|---|---|---|
| Forward / quoted reply, any of 7 scripts | 100% | yes |
| Forward carrying an added disclaimer | 100% | yes |
| Two identical short bodies | 100% | yes |
| Two 1-line notes, one long disclaimer | 96% | **no** |
| Payment receipts, same template | 83% | **no** |
| Calendar invite and its update | 83% | **no** |
| One-time codes, twice | 80% | **no** |
| Shipping notices, same template | 78% | **no** |
| Thai, two unrelated messages | 78% | **no** |
| Airline and hotel, same trip | 44% | **no** |
| Two empty bodies | 0% | **no** |

The gap between 100% and 96% is the whole rule. A test that asserts only the
100% rows would stay green while a floor drifted into the 96% row, so the
96%, 83% and 0% rows are acceptance criteria, not extra coverage.

**The limit, stated rather than hidden.** This catches a forward whose original
is among the ≤8 held bodies for the same label. A forward whose original fell
outside the ceiling, or landed under a different label, is not caught. Catching
those needs a per-source sketch compared across every candidate, which is
all-pairs over a mailbox and collides with story 9d. The bounded rule is the
only shape consistent with this tree, and the residue belongs in deferred work
with that reasoning attached — not as a TODO.

**Why the confound is in the matrix as a number.** A rule like this is normally
justified by the case it catches. The case that matters is the one it must
*not* catch, and 95% is where it sits. A test that asserts only the forward
would stay green while the floor drifted down into the confound.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass
- `cd half && uv run --extra dev python tools/percolation_sim.py` -- expected: no collapse at any density
- `cd half && uv run --extra dev python tools/mailbox_sim.py` -- expected: 0 of 5 shapes miscounted
- `cd half && uv run --extra dev python tools/admits_sim.py` -- expected: the forward shape admits nothing
- `cd half && git status --porcelain` -- expected: clean after commit

## Evidence

**Baseline `a3fa9d0`, 5209 tests green. After: 5248 green**, offline, with the
suite's socket guard untouched.

### The specified rule shipped an outage, and the sweep is the record of it

The spec named containment scored as **a fraction of the smaller body's
vocabulary, above a floor of 0.98**, with the reasoning that every true positive
sits at exactly 1.00 and the nearest confound at 0.96. Both halves of that are
true on hand-built pairs. It is still the story-17 failure, reached through a
different door — and this story's own Intent says the argument "must be
measured, not trusted".

Measured, on a mailbox where every message carries one long corporate legal
footer and is otherwise a stranger to every other. Truth is one voice per
message:

```
                                   window = MAX_SOURCES      every pair
  rule                              50    200    500      50    200    500
  fraction of vocabulary >= 0.98     3      3      3       3      3      3
  total set containment (== 1.00)   45    189    475      43    177    454
  total sequence containment        50    200    500      50    200    500
```

The fractional rule returns **three** voices for five hundred strangers, at the
shipped window and with every pair compared alike. Below two the gate never
opens, Half finds one support everywhere, admits nothing, and goes quiet — which
is not restraint. The reason is that a long shared footer is most of a short
message's vocabulary, so two unrelated notes under one footer score above 0.98;
the spec's confound table was measured on raw bodies of the author's choosing
rather than on a mailbox. Total *set* containment is far better and still wrong:
it collapses roughly one stranger in twenty.

Total containment on the **term sequence** — the smaller body's whole sequence
sitting contiguously inside the larger one's — returns one voice per message at
every density swept, bounded and unbounded, while still firing on every forward
and every quoted reply in all eight scripts. It is also what the frozen
Boundaries block asks for in words: *"a rule that fires below total containment
is a similarity rule and is out of scope."* Only the number in Design Notes was
wrong. Both rejected rules stay runnable in `tools/percolation_sim.py`, and
`tests/test_echo.py::test_the_fractional_rule_this_one_replaced_fires_on_the_confound`
carries the counterexample by number, so the trade can be overturned with
measurement rather than with an argument.

### The tokenizer, pinned by the scripts it saves

A forward containing its original verbatim, under each tokenizer:

```
  script      half.text.terms   half.context.build.runs(length=3)
  latin              match                    match
  japanese           match                    NO MATCH
  chinese            match                    NO MATCH
  thai               match                    NO MATCH
  devanagari         match                    match
  arabic             match                    match
  hebrew             match                    match
  korean             match                    match
```

`test_the_worldwide_suite_fails_against_the_whitespace_tokenizer` asserts that
set of three exactly, so a build that switched tokenizers would go red rather
than going quiet for three writing systems.

### The simulations

```
  tools/mailbox_sim.py      shapes miscounted: 0 of 5   (was 1 of 5)
  tools/admits_sim.py       every shape ok; the forward admits nothing
  tools/percolation_sim.py  no collapse at any density; the origin margin
                            unchanged (levels == the same mailbox with no
                            declared key at all, on every swept row)
```

### Three fixtures were stubbing what they measured

`tools/admits_sim.py` handed one six-word body to every receipt in every shape,
so no body-derived rule could have been visible to it. `tools/mailbox_sim.py`'s
`counted` synthesised a digest and never read `m.body`. And
`tests/test_revealed.py`'s script case read one body twice with a zero-width
space glued on so the digests differed, calling that two independent supports —
which it was only because the content axis is a *byte* digest, and containment
correctly sees through it. All three now carry real bodies. None was wrong when
written; each became wrong the moment a rule started reading the body.

### CI floors

`cap3` 31 → 32, `cap3_structure` 37 → 49, `cap3_axes` 41 → 67, each edited on
its own line and verified to move exactly one number.
