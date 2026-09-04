---
title: 'Story 4c — Script-neutral retrieval'
type: 'bugfix'
created: '2026-09-01'
status: 'done'
baseline_commit: '519b2ae2ad2f819e6b32db8360835bbecc709fd2'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Retrieval returns the wrong beliefs for most of the world's scripts. A Devanagari query is shattered into single letters and OR-joined, so `रात` ("night") retrieves a belief about travel; and because Japanese, Chinese and Thai have no inter-word spaces, an entire sentence becomes one token and `転職` retrieves nothing at all. Half ships world-wide, and story 5 decides what Half may *say* — building that on retrieval this wrong is the wrong order.

**Approach:** Two independent fixes. Quote each source word as a phrase in the FTS query, keeping OR *between* words, which restores precision for every combining-mark script without touching the schema. Separately, n-gram scriptio-continua runs at index and query time so an unspaced sentence is findable by the words inside it — that changes indexed content, so it takes a schema version bump through the existing discard-and-replay path.

## Boundaries & Constraints

**Always:**
- **OR stays between words; phrases apply within a word.** Phrase-quoting a whole conversational turn matched only a belief repeating it verbatim — that was a real story-4 defect and must not return.
- **A word is a word in every script.** Combining marks belong to the letter they modify, so a tokenizer must not split `यात्रा` into consonants.
- **Scriptio-continua runs are n-grammed on both sides.** Indexing and querying must agree, or the fix is worse than the defect.
- **Precision is symmetric across scripts.** Every script that gets a recall case gets a matching precision case: an unrelated word in that script must not retrieve the belief. An n-gram scheme that ORs single characters recreates, for unspaced scripts, exactly the defect this story exists to remove.
- **N-grams are taken over grapheme clusters, never raw codepoints.** Slicing codepoints undoes the mark-preserving fix one layer below it and produces fragments beginning with a bare mark.
- **Script class is derived from the Unicode character database, not enumerated as ranges.** A hardcoded block table is the per-language list this story forbids: it is stale the day it is written and silently wrong for scripts nobody thought of.
- **A tokenizer failure may never cost a main their reply or their store.** It must not escape the turn, and no record that passes validation may make a later rebuild raise — including a prefix assembled from fields that were each legal alone, and including a log written before the ceiling existed.
- **A search result carries the belief's own words, never index text.** The two live in adjacent columns and the wrong one reaching the main is n-gram soup.
- **Anything that changes what retrieval returns is pinned by a retrieval test.** Every entry in a script table, every n-gram size, and every ceiling — a constant no test can move is a constant that will be moved.
- **N-gramming is bounded.** It multiplies term counts, so both input length and emitted term count carry explicit limits and exceeding them is a typed error, never a silent truncation.
- The schema bump goes through the existing `PRAGMA user_version` discard-and-replay path (AD-3). A derived view is disposable; the log is untouched.
- **Latin must not regress.** Every retrieval and strand test passing today still passes.
- `half/text.py` is the one shared tokenizer, so a change moves the query builder, the prefix builder and the strand matcher together. Story 4b's AD-18 drop rule has its own mark-preserving split by design — leave it alone and keep it green.
- Nothing here reads a clock, the network, or ambient state; the fold stays pure (AD-30).
- Every belief stays reachable by a query whose terms match it (AD-24).

**Ask First:**
- Any runtime dependency beyond the standard library and pinned SDKs — in particular, no ICU, no segmentation library.
- Switching the FTS5 tokenizer itself (`trigram` or otherwise) rather than fixing what Half feeds it.
- Any change to the AD-18 fragment guard or its pair floor.

**Never:**
- No vector service, no embedding, no model call (AD-5, AD-19).
- No per-language branching beyond script class — Half does not detect languages, and must not need a language list to work.
- Do not weaken any existing invariant gate to make this pass.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Devanagari precision | Store holds a travel belief; query `रात` ("night") | Not retrieved — the regression is gone | N/A |
| Devanagari recall | Same store; query `यात्रा` | Retrieved | N/A |
| Latin unchanged | Existing story-4 fixtures | Identical results and order | N/A |
| Conversational query | A multi-word turn | Still matches a belief sharing any one word | N/A |
| Japanese | Store holds `転職を考えている`; query `転職` | Retrieved | N/A |
| Two-character CJK | Query `旅行` | Retrieved — the case `trigram` cannot serve | N/A |
| CJK precision | Query `転職` against an unrelated belief about severance | **Not** retrieved | N/A |
| Thai precision | A query against an unrelated Thai belief | **Not** retrieved | N/A |
| One-character query | A single CJK character that appears in a belief | Retrieved | N/A |
| Per-script recall | A word drawn only from one script block — pure kana, pure katakana, Lao, Khmer | Retrieved for each, independently | N/A |
| Grapheme integrity | A Khmer or Thai word with dependent vowels | Its n-grams begin on a grapheme, never a bare mark | N/A |
| Operator words | A turn containing bare `AND`, `OR`, `NOT` in capitals | Searched as ordinary words | Never a syntax error |
| Result text | A belief retrieved through search | Its claim is byte-identical to what was recorded | Never index text |
| Oversized list field | `people` or `topics` past the ceiling | Refused before the append; the log stays empty | Later turns unaffected |
| Legacy log | A log written before the ceiling existed | Opens and indexes what it can | Never permanently unopenable |
| Turn survives | Tokenizer refuses something on the live path | A reply is still sent | Never silence |
| Thai | Unspaced Thai sentence, query on a word inside it | Retrieved | N/A |
| Korean, Cyrillic, Hebrew, Arabic | A belief and a matching query in each | Retrieved | N/A |
| Mixed script | One claim mixing Latin and CJK | Both halves findable | N/A |
| Emoji | Claim or query containing emoji | Treated as ordinary input; never crashes | N/A |
| Term explosion | A very long unspaced run | Refused with a typed error before indexing | Never a silent truncation |
| Older view | A derived view from the previous schema | Discarded and replayed from the log | Never a raw sqlite error |
| Replay | Rebuild after the bump | State still byte-identical from the log | N/A |
| Strand match | A non-Latin person or loop named in a message | Becomes a live strand | N/A |
| Prefix | A non-Latin subject or loop | Present in the index and findable | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. AD-3, 5, 24, 30 govern; AD-2 constrains the dependency answer.

**Reference (extraction manifest — mark the row when done):** `claude-obsidian/scripts/bm25-index.py` — `_is_cjk_character`, `_script_runs`, `_cjk_ngrams`, `_cjk_ngram_count`, and its documented schema-2 "finalized pre-release CJK n-gram tokenizer". Take its growth discipline too: `MAX_TOKEN_TERMS`, `MAX_TOKEN_INPUT_CHARS`, and `TokenGrowthLimitError` raised rather than truncating.

**The verified diagnosis, not to be re-derived:** `half.text.words("यात्रा")` returns `['य','त','र']` because Python's `\w` excludes combining marks; `half/store/db.py::_match_expression` OR-joins those pieces. Raw FTS5 is not at fault — `MATCH '"रात"'` already returns only the night row.

**Existing, reused:** `half/text.py` (`words`, `tokens`, `normalize` — and its module docstring still says "a product aimed at India", which is wrong and must be corrected), `half/store/db.py` (`_match_expression`, `SCHEMA`, `DERIVED_VERSION`, `_discard_if_stale`, `rebuild`), `half/retrieval/prefix.py`, `half/retrieval/strands.py`, `half/errors.py`.

**To create:** `half/tests/test_scripts.py` — one case per script in the matrix.

**To change:** `half/text.py`, `half/store/db.py`, and the README's stale claim about non-Latin support if present.

## Tasks & Acceptance

**Execution:**
- [x] `half/text.py` -- treat combining marks as part of their word; correct the India wording -- the shattering defect
- [x] `half/text.py` -- split scriptio-continua runs and emit bounded n-grams, raising on growth -- CJK, Thai, Lao, Khmer
- [x] `half/store/db.py` -- quote each word as a phrase, OR between words -- the precision regression
- [x] `half/store/db.py` -- n-gram indexed content; bump `DERIVED_VERSION` -- index and query must agree
- [x] `half/tests/test_scripts.py` -- one case per script, plus mixed-script, emoji and the growth bound -- I/O matrix
- [x] `half/tests/` -- assert the existing Latin retrieval and strand expectations are unchanged -- no regression

**Acceptance Criteria:**
- Given a store holding a Devanagari belief about travel, when the unrelated word `रात` is queried, then it is not retrieved, and when `यात्रा` is queried, then it is.
- Given a store holding an unspaced Japanese sentence, when a two-character word inside it is queried, then the belief is retrieved.
- Given a belief and a matching query in Thai, Korean, Cyrillic, Hebrew or Arabic, when retrieval runs, then the belief is retrieved.
- Given a multi-word conversational turn, when it is queried, then a belief sharing any single word still matches.
- Given every retrieval and strand test that passes today, when the suite runs after this change, then all of them still pass.
- Given an unspaced run long enough to explode the term count, when it is indexed, then a typed error is raised rather than terms silently dropped.
- Given a derived view written before this change, when a store is opened, then it is discarded and replayed with no raw sqlite error.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access.

## Spec Change Log

- **Review round 1 — the story reintroduced its own defect for unspaced scripts.** Verified: `search("転職")` returned a belief about severance pay and `search("เปลี่ยนงาน")` returned one about sticky rice, because `NGRAM_SIZES` includes 1 and the match expression ORs terms, so a single shared character matches. `_ngrams` also sliced raw codepoints, stripping Khmer dependent vowels and emitting bigrams that begin mid-grapheme. **The root cause is in this spec:** the matrix carried a negative case for Devanagari (`रात` must not retrieve) but only positive cases for CJK and Thai, and the suite's asymmetry mirrored the matrix's exactly. Mutation testing then showed the constants were unpinned — 11 of 20 script-range rows, both unigrams and trigrams, and both ceilings could each be changed with all 487 tests green. Amended with symmetric precision rows, grapheme-cluster n-gramming, derived script class, and the rule that anything changing retrieval is pinned by a retrieval test. **KEEP:** `words()` treating combining marks as part of their word is the fix that works and must survive re-derivation; Latin behaviour must stay unchanged; the AD-18 drop rule in `half/context/build.py` keeps its own split and stays green.

## Design Notes

**Why not switch to `trigram`.** It is the obvious answer and it fails the common case: `trigram` returns nothing for a two-character query, and two-character words are ordinary in Chinese and Japanese. Verified against SQLite 3.53.1 — `trigram` retrieved Thai correctly and `転職` not at all.

**Why phrases inside, OR outside.** FTS5 splits a quoted phrase with the same tokenizer it used on the indexed text, so a phrase matches whenever the index and the query shatter alike — which is why raw `MATCH '"यात्रा"'` already works today. OR between words is what keeps a conversational turn matching a belief that shares one word.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network
- `cd half && uv run --extra dev pytest tests/test_scripts.py -q` -- expected: every script in the matrix retrieves correctly
- `cd half && uv run --extra dev pytest tests/test_retrieval.py tests/test_strands.py tests/test_context.py tests/test_replay.py -q` -- expected: no regression
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — one mechanism, not two**

- Every word is matched as a phrase; adjacency carries word identity where spaces cannot.
  [`text.py:1`](../../../../half/text.py#L1)

**The two fixes that make scripts equal**

- A word keeps its combining marks — the defect that started this story.
  [`text.py:338`](../../../../half/text.py#L338)

- Script class derived from the Unicode character database, never a range table.
  [`text.py:112`](../../../../half/text.py#L112)

**The index**

- Raw claim and index terms live in adjacent columns; readers take the raw one.
  [`db.py:48`](../../../../half/store/db.py#L48)

- Phrase per word, so a capitalised AND or NOT is a word and not syntax.
  [`db.py:317`](../../../../half/store/db.py#L317)

**Failing without costing the main**

- A term budget degrades the index for one belief; it never makes a store unopenable.
  [`db.py:162`](../../../../half/store/db.py#L162)

**Tests that carry the design**

- Precision and recall per script, in one shared store so collisions are visible.
  [`test_scripts.py:1`](../../../../half/tests/test_scripts.py#L1)
