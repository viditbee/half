---
title: 'Story 4b — The two-channel context (AD-18)'
type: 'feature'
created: '2026-08-31'
status: 'done'
baseline_commit: '66663e9d8ea0c6669a6e7a2de264ef9f10830022'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Retrieval ranks beliefs but nothing may use them. Story 4 shipped with an interim ban on any belief text reaching the main, because the thing that decides what Half may *say* — as opposed to what it may *act on* — did not exist.

**Approach:** Deliver AD-18. A context builder consumes ranked beliefs and splits them by license into three channels: `assert` becomes quotable **content**, `behave` becomes **directives** naming only a topic, `ask` becomes **question candidates**. This lifts story 4's interim ban: `assert` text may now reach the main, and `behave` text still may not — enforced by construction, never by filtering output.

## Boundaries & Constraints

**Always:**
- **A `behave`-licensed belief's claim text never appears in a constructed context, in any channel or rendering.** Asserted byte-wise over the whole context, not per field. This is AD-18's own words: a test, not a guideline.
- **Withholding is by fragment, not by whole claim.** No contiguous run of a withheld claim's words may appear anywhere in a context — a guard that blocks only the exact full claim lets its substance through inside someone else's wording. The comparison is script-neutral: it must hold for languages that do not space their words.
- **The rendering is the single complete serialization, and its completeness is itself asserted.** Every field of every channel item must appear in it, pinned by a field-enumerating test — otherwise a later debug or provenance field carries withheld text past a scan that cannot see it.
- **The rendering is unambiguous.** No item's text may forge a line or a channel label. Claim and topic text is ingested material, and the context is what a model will read.
- **The guard runs in shipped code, not only in tests.** `build` scans its own finished rendering before returning it.
- **Directives are built from structured fields only** — subject, loop, topic — never from claim text. Without a model there is no paraphrase, and a paraphrase built from the claim's own words is a quotation with extra steps.
- A directive that would emit claim wording is **dropped rather than degraded**. Losing a directive costs subtlety; leaking one costs trust.
- **Unknown, missing or malformed licenses are treated as `behave`.** The weakest rung is the default and the failure mode (glossary; CAP-10).
- `ask` material is neither quoted nor silently used. It surfaces as a question candidate, and its claim text is treated exactly as `behave` text.
- Enforcement happens at construction. Nothing downstream may re-admit material the builder excluded.
- Retracted, expunged and quarantined beliefs never reach a context.
- No clock, no network, no ambient state; `now` stays injected. Determinism holds (AD-30).
- Half ships world-wide: no ASCII-only handling, and no locale baked into directive phrasing or ordering.

**Ask First:**
- Any runtime dependency beyond the standard library and pinned SDKs.
- Any fourth channel, or any change to what a rung permits.
- Emitting a directive derived from claim text.

**Never:**
- No model call — AD-19's port stays unbuilt. The context is a data structure this story builds and asserts over, not something sent anywhere.
- No license ladder, promotion, trust balance, or unsaid/unasked queues — story 5.
- No post-generation filtering of any kind. If that appears, AD-18 has been inverted.
- Do not apply quarantine on inference, and do not build the asking that would.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| `assert` belief | License `assert` | Claim enters the content channel verbatim | N/A |
| `behave` belief | License `behave` | A directive naming its topic; claim text absent everywhere | Asserted byte-wise |
| `ask` belief | License `ask` | A question candidate; claim text absent everywhere | Treated as `behave` text |
| Missing license | Field absent | Treated as `behave` | Never as `assert` |
| Unknown license | License `shout` | Treated as `behave` | Never raises, never `assert` |
| Topic echoes the claim | A loop or subject whose words appear in the claim | Directive dropped, not emitted | Drop over degrade |
| No structured topic | `behave` belief with no loop or subject | No directive; the belief still never leaks | Silent omission |
| Mixed set | All three rungs retrieved together | Each lands in exactly one channel | N/A |
| Empty content | Only `behave` material retrieved | Context has directives and nothing quotable | Reply still produced |
| Nothing retrieved | Empty ranked set | Empty context, no error; never phrased as missing access | N/A |
| Crisis | Retrieval disabled for that main | Empty context; a reply is still sent | Never a raised turn |
| Retracted | Belief retracted before the turn | Absent from every channel | N/A |
| Outbound | A turn whose context had content | `assert` text may appear in the reply; no `behave` or `ask` text may | Asserted byte-wise |
| Non-ASCII | Devanagari or accented claims and topics | Handled identically; no channel drops them for script | N/A |
| Fragment | An `assert` claim containing a withheld claim's wording | Dropped from content; the fragment reaches nothing | Asserted byte-wise |
| Unspaced script | Withheld claim spaced differently inside a quotable one | Still caught; comparison ignores spacing | Never quoted |
| Forged line | Claim or topic containing a newline or control character | Cannot produce a second line or a channel label | Escaped or rejected |
| New field | A field added to any channel item | A test fails unless the rendering covers it | Never silently unscanned |
| Malformed belief | `belief` is not a mapping | Resolves to `behave`; the turn still replies | Never raises |
| Determinism | Same ranked set and `now`, built twice | Identical context | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding. AD-18 governs; AD-19, AD-26, AD-30 constrain. Story 4's Spec Change Log carries a KEEP that this story satisfies rather than deletes: the no-outbound-belief-text boundary is *replaced* by the real license assertion, never removed.

**Reference:** the extraction manifest was checked — no row falls due here. The remaining open rows belong to stories 5, 8, 9 and v2.

**Existing, reused:** `half/retrieval/port.py` (`Ranked`, `Candidate` — `Candidate.belief` already carries `license` through the decoded record), `half/retrieval/rank.py`, `half/actor/runtime.py::respond` (the seam, currently taking `ranked` and using none of it), `half/store/fold.py::State`, `half/text.py` (the shared unicode tokenizer), `half/errors.py`.

**To create:**
- `half/context/channels.py` — the `Context` structure, its three channels, and a rendering whose bytes the tests scan.
- `half/context/build.py` — the license split and the structured-field directive builder, including the drop rule.
- `half/tests/` — `test_context.py`, and non-ASCII cases alongside the existing suite.

**To change:** `half/actor/runtime.py` — `respond` consumes the context and may quote content; `.github/workflows/ci.yml` — the AD-18 gate becomes the real assertion.

## Tasks & Acceptance

**Execution:**
- [x] `half/context/channels.py` -- `Context`, three channels, and a byte-scannable rendering -- AD-18
- [x] `half/context/build.py` -- split by license; directives from structured fields only; drop over degrade -- AD-18
- [x] `half/context/build.py` -- unknown, missing and malformed licenses resolve to `behave` -- fail closed
- [x] `half/actor/runtime.py` -- `respond` builds a context and may quote only content -- lifts story 4's interim ban
- [x] `.github/workflows/ci.yml` -- replace the interim AD-18 gate with the real assertion -- never delete a gate
- [x] `half/tests/test_context.py` -- one case per matrix row, including non-ASCII and the drop rule -- I/O matrix

**Acceptance Criteria:**
- Given a `behave`-licensed belief in the retrieved set, when a context is built and rendered, then its claim text appears nowhere in the context bytes, while its topic still influences the directives.
- Given the same belief, when a reply is produced from that context, then its claim text appears nowhere in the reply bytes.
- Given an `assert`-licensed belief, when a reply is produced, then its claim text may appear — the interim ban is lifted only for this rung.
- Given a belief whose license field is absent, unknown or malformed, when the context is built, then it is treated as `behave` and never as quotable content.
- Given a `behave` belief whose topic words also appear in its claim, when the directive is built, then no directive is emitted rather than a degraded one.
- Given a retracted or expunged belief, when a context is built, then it appears in no channel.
- Given retrieval disabled for a main, when a turn runs, then the context is empty and a reply is still sent.
- Given the same ranked set and injected `now`, when a context is built twice, then the two are identical.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access.

## Spec Change Log

- **Quarantine reads as a pin, not an exclusion — an assumption, not a human decision.** The frozen block says *"Retracted, expunged and quarantined beliefs never reach a context."* Retracted and expunged are settled: the fold removes them, so nothing downstream can see them. Quarantine could not be read the same way without contradicting two binding files. The glossary defines quarantine as *"a belief permanently pinned at `behave`. A schema field, not an exception list"*; the constitution says *"quarantined material may inform behaviour and may never be raised"*; and AD-18 names filtering `behave` material out entirely as the second of its two failures — *"leaving Half either blunt or silent, unable to be gentle about what it may not name."* A quarantined belief is exactly the wound AD-18's illustration is about, so excluding it from the directives would invert the invariant this story exists to hold. **Implemented as:** quarantine resolves the license to `behave` regardless of the stated rung, so a quarantined belief's claim text never reaches a context and it can never become a question candidate, while its topic still reaches the directives. Nothing infers a quarantine candidate — the field is read, never derived (CAP-10). **The question was not put to a human; if the exclusion reading was meant, this is the line to change.**

- **The drop rule needed a comparison unit the index tokenizer cannot provide.** `half.text.words` reproduces SQLite `unicode61`'s boundaries, which treat a Devanagari matra as a separator: `यात्रा` tokenizes to three single consonants that collide with almost any other Devanagari string. A drop rule built on that unit emits no directive for any belief written in an Indic script — the matrix's non-ASCII row failing in the direction that matters most for the target market. So `half/context/build.py` carries a private comparison split that keeps marks attached to their letter and folds with the same `half.text.normalize`. The index tokenizer is untouched: its agreement with FTS5 is load-bearing for story 4 and this is a different question, not a second answer to the same one. The underlying `unicode61` limitation for Indic retrieval is unchanged and unaddressed — it belongs to whoever owns a custom tokenizer decision.

- **Content is dropped when it would quote a withheld claim verbatim.** The byte-wise assertion is over the whole rendering and names no channel, so an `assert`-licensed claim that literally contains a `behave` claim's wording would break it. Such an item is dropped from the content channel. The cost is real and deliberate — a claim Half was licensed to state, lost because a different record says the same words at a weaker rung — and it is the fail-closed direction the story asks for everywhere else.

- **Review round 1 — the invariant did not hold, and the fix needed a threshold the frozen block does not name. An assumption, not a human decision.** Three reviewers reproduced the same violation: the guard blocked only a withheld claim *entire*, so `"has been avoiding the conversation with his brother"` was withheld while `"he keeps avoiding the conversation with his brother lately"` was quoted — every word that mattered, said. The amended block now requires that *"no contiguous run of a withheld claim's words may appear anywhere in a context."* Read literally, a run of length one is a run, and that reading cannot be implemented: **a single shared word is exactly what a directive is**, so a one-word floor empties the directives channel and lands on AD-18's own second named failure — Half left blunt, unable to be gentle about what it may not name. **Implemented as:** the floor is the *adjacent pair*. No two consecutive words of a withheld claim may appear consecutively anywhere in the context; pairs are sufficient for runs of every length, because a longer shared run contains a shared pair. One word is a topic and is permitted; two adjacent words are wording and are not. The cost is real, frequent and one-directional: an `assert` claim sharing an incidental pair (`"has been"`) with any withheld claim is dropped from content, so Half says less than it is licensed to. **The question of where the floor belongs was not put to a human.**

- **Comparison ignores spacing, and the invisible characters between words.** Japanese does not space its words, so a spaced comparison misses `転職 を 考えている` sitting whole inside `日記に「転職を考えている」と書いた` — reproduced. Words are therefore concatenated before matching. Format characters (`Cf` — ZWJ, ZWNJ, soft hyphen, bidi marks) are removed rather than treated as boundaries, since either treating them as a boundary *or* leaving them in place lets one be dropped into the middle of a word to slip it past the echo rule in Indic and Arabic scripts. The comparison also over-folds: `half.text.normalize` strips non-spacing marks, so `ज़` and `ज` collide and `ज़मीन` echoes `जमीन`. The direction is safe — it drops directives it need not have dropped and never emits one it should have withheld — and it is now pinned by a test rather than described inaccurately in a docstring.

- **`subject` is a last resort rather than a topic.** Every belief about the main carries `subject="self"` — the actor's turn writes it on every inbound message — so naming it beside a loop tells a model nothing, and, because the drop rule is per belief, any claim containing the word "self" silently killed the whole directive including the loop that *was* worth naming. Subject is now emitted only when the belief has no loop and no topics. This is a relevance decision, not a safety drop: better a weak directive than none, and never a weak one standing in the way of a strong one.

- **"Verbatim" yields to the forged-line row, minimally.** The matrix says an `assert` claim enters the content channel verbatim; the amended block says no item's text may forge a line or a channel label, and the actor's turn records a main's message verbatim, so multi-line claim text is ordinary input rather than an attack. **Implemented as:** one space per control character or line separator (`Cc`, `Zl`, `Zp`), then the ends trimmed — every printable character survives, in order. Ordinary whitespace runs are deliberately *not* collapsed. Channel labels are line-initial and no item's text can begin a line, so a label appearing mid-line is text rather than structure; the rendering is parsed by line and a test pins that every line begins with a known label.

## Design Notes

**Why directives name topics rather than paraphrase.** AD-18's illustration — *"be gentle if travel comes up"* — is a paraphrase, and paraphrase needs a model that AD-19 leaves unbuilt. The deterministic form of the same idea is a directive assembled from the belief's structured fields, which is why the drop rule exists: if the only available topic word is also a claim word, there is no safe directive to emit, and silence is the correct output.

**Why the assertion is byte-wise over the whole rendering.** A per-field check passes while claim text sits in a provenance list, a debug field, or an id. The context is rendered once and scanned whole, which is the same discipline story 3 arrived at for secrets.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network
- `cd half && uv run --extra dev pytest tests/test_context.py -q` -- expected: no `behave` or `ask` text in any context or reply
- `cd half && uv run --extra dev pytest tests/test_retrieval.py tests/test_strands.py tests/test_purity.py tests/test_replay.py -q` -- expected: story 4's invariants intact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — the invariant, and where it is enforced**

- The license split, and the fragment guard that runs before a context is returned.
  [`build.py:1`](../../../../half/context/build.py#L1)

- Three channels and the one rendering everything is scanned through.
  [`channels.py:1`](../../../../half/context/channels.py#L1)

**The two rules that were wrong in round one**

- Withholding by adjacent pair, not whole claim — one word is a topic, two are wording.
  [`build.py:177`](../../../../half/context/build.py#L177)

- Comparison ignores spacing, so unspaced scripts cannot smuggle a claim through.
  [`build.py:198`](../../../../half/context/build.py#L198)

**The seam story 4 left**

- `respond` quotes the content channel and nothing else.
  [`runtime.py:1`](../../../../half/actor/runtime.py#L1)

**Tests that carry the design**

- Field enumeration: a new field on a channel item fails the suite unless the rendering covers it.
  [`test_context.py:1`](../../../../half/tests/test_context.py#L1)
