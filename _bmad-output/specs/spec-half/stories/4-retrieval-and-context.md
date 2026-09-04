---
title: 'Story 4 — Retrieval and ranking over beliefs'
type: 'feature'
created: '2026-08-31'
status: 'done'
baseline_commit: 'b486c328deaafb3e2ad0e97a77b761ccce1fc88c'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `db.search` ranks claim text by BM25 alone — blind to what the main is talking about, which open loops are live, and how well corroborated a claim is.

**Approach:** Deliver CAP-9 and CAP-1's weighting clause: a retrieval layer *above* the store fusing BM25 with strand match, recency and computed salience, with an optional reranker that degrades visibly when absent. No model call — the contextual prefix is structural. AD-18's context builder is the next story, so **this story ranks beliefs but never puts one in front of the main.**

## Boundaries & Constraints

**Always:**
- **Strand match reorders; it never excludes.** A design in which a topic switch can empty the candidate set is rejected — that is what makes Half say *"I don't have access to that,"* which the spec forbids.
- **Reachable means findable by a matching query, not present in every candidate set.** A turn may bound how many beliefs it scores; a belief must never be unreachable to a query whose terms match it. Any bound is ordered by salience, never by id, and a truncated scan is annotated in the result — a silent cap is the failure, not the cap itself.
- **No retrieved belief text may reach an outbound message.** License enforcement is AD-18's and lands next; until then retrieval ranks and nothing more. A test, not a guideline.
- **Salience is computed from folded state, never a counter a read bumps** — a use-counter makes state depend on read traffic rather than the log, breaking AD-30.
- Retrieval targets the belief set, never the source corpus.
- `now` is injected. Retrieval reads no clock and no ambient state.
- The reranker port has **one** method; its absence degrades to correct BM25 order, annotated in the result, never silently.
- Retrieval is disableable **per main** and the crisis gate is the caller that disables it (CAP-12). A disabled retriever raises; it never quietly returns nothing. **The turn catches that raise and still replies** — a disable degrades retrieval, never the reply, and never costs the main a message.
- Ranking weights are volatile and never enter the log (AD-26).
- Retrieval must be reachable from shipped code, not only from tests.

**Ask First:** any dependency beyond stdlib and pinned SDKs; a second method on the reranker port; any change making strand match filter rather than weight.

**Never:** no model call, embedding, vector service, or reranker implementation (AD-5, AD-19). No context construction or license split — the next story, and nothing here may pre-empt it. No license ladder or queues (story 5); no salience decay or tension minting (story 9). No ranking policy inside `half/store/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Plain query | Beliefs indexed | BM25-ranked, best first | N/A |
| Prefix hit | Query matches subject or loop, not claim text | Still retrieved — the prefix is indexed | N/A |
| Topic switch | Query on a strand with no live weight | Reordered, **never empty**; every belief stays reachable | N/A |
| Live loop | Equal BM25, one belief on an advancing loop | The loop-bearing belief ranks higher | N/A |
| Stale belief | Old `last_corroborated`, same BM25 | Ranks below a freshly corroborated peer | N/A |
| Corroboration | Higher `independent`, same BM25 | Ranks higher | N/A |
| No reranker | None configured | BM25 order, annotated as a no-op fallback | Never raises |
| Reranker fails | Configured reranker raises | BM25 order, annotated | Swallowed, never fatal |
| Outbound | A turn that retrieved beliefs | No retrieved claim text in the reply | Asserted byte-wise |
| Crisis | Retriever disabled | Raises `RetrievalDisabled` | Loud, never empty |
| After a disable | Ordinary turn once retrieval is disabled | A reply is still sent; the message is never dropped | Raise caught in the pipeline |
| Other mains | One main in crisis | Every other main retrieves normally | Switch is per-main |
| Truncated scan | More beliefs than the per-turn bound | Highest-salience kept, result annotated as truncated | Never silent |
| Older schema | A derived view written before the prefix column | Discarded and replayed from the log | Never a raw sqlite error |
| Empty store | No beliefs | Empty result, no error; never phrased as missing access | N/A |
| Corpus growth | Sources 10×, beliefs flat | Results and work identical — sources are never touched | N/A |
| Determinism | Same store and injected `now`, twice | Identical results | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. AD-3, 5, 19, 26, 30 govern this story; AD-18 governs the next and is deliberately not implemented here.

**Reference (extracted from the manifest):**
- `claude-obsidian/scripts/rerank.py::mark_noop` — annotate a fallback without changing BM25 ordering; degradation is recorded in the result, not hidden. Its `contextual-prefix.py` tier 3 (synthetic prefix, no model) is the tier built here.
- `gbrain/docs/ENGINES.md` — embedding and chunking stay **out** of the storage engine and fuse above it; their interface grew past 100 methods, so the port gets one.
- `HippoRAG/src/hipporag/rerank.py::DSPyFilter.rerank` — prune candidates *before* the expensive stage. Its `difflib` cutoff of `0.0` always matches something: a mis-mapping risk not to copy.

**Existing, reused:** `half/store/db.py` (`SCHEMA`, `search`, `rebuild`), `half/store/store.py::search`, `half/store/fold.py::State`, `half/errors.py`, `half/actor/runtime.py` (the stub responder that consumes this), `half/crisis/gate.py` (owns the entrypoint).

**To create:** `half/retrieval/` — `port.py` (`Reranker`, `Candidate`, `Ranked`), `prefix.py`, `salience.py`, `strands.py`, `rank.py`; `half/tests/test_retrieval.py`, `half/tests/test_strands.py`.

**To change:** `half/store/db.py` (index the prefix), `half/actor/runtime.py` and `half/crisis/gate.py` (wire retrieval and the disabled path).

## Tasks & Acceptance

**Execution:**
- [x] `half/retrieval/port.py` -- one-method `Reranker` protocol and result types -- AD-5, gbrain's narrow-port lesson
- [x] `half/retrieval/prefix.py` -- deterministic prefix from subject, loop and ledger -- no model, AD-19
- [x] `half/store/db.py` -- index the prefix as a second FTS column; rebuild regenerates it -- prefix hits
- [x] `half/retrieval/salience.py` -- salience from independence, last-corroborated and loop state -- AD-30
- [x] `half/retrieval/strands.py` -- strand match that reorders, never filters -- CAP-1
- [x] `half/retrieval/rank.py` -- fuse bm25 × strand × recency × salience; annotated no-op reranker; `RetrievalDisabled` -- AD-5, CAP-12
- [x] `half/actor/runtime.py`, `half/crisis/gate.py` -- wire retrieval into the live turn and the crisis disable, no belief text reaching the reply -- reachable from shipped code
- [x] `half/tests/test_retrieval.py` -- ranking, degradation, disabled, empty store, determinism -- I/O matrix
- [x] `half/tests/test_strands.py` -- topic switch never empties the set; no claim text in a reply -- I/O matrix

**Acceptance Criteria:**
- Given a query on a strand with no current weight, when retrieval runs, then results are reordered and every belief stays reachable — the candidate set is never empty by construction.
- Given a turn that retrieved beliefs, when the reply is produced, then no retrieved claim text appears in its bytes.
- Given no reranker, when retrieval runs, then results are correct in BM25 order carrying an explicit no-op annotation.
- Given a reranker that raises, when retrieval runs, then BM25 order is returned annotated and no error escapes.
- Given a source corpus grown tenfold with beliefs unchanged, when retrieval runs, then results and work done are identical.
- Given a disabled retriever, when queried, then it raises rather than returning empty.
- Given the same store and injected `now`, when retrieval runs twice, then results are identical and no clock was read.
- Given only stdlib and pinned SDKs, when the suite runs, then it passes with no network.

## Spec Change Log

- **Review round 1 — two intent gaps in the frozen block, resolved by assumption.** Reviewers demonstrated both by mutation. (1) *Reachability vs scale:* the block demanded "every belief stays reachable" while assuming a bounded scan; the code resolved it by capping at 500 beliefs ordered by id, under a docstring reading "Nothing here is a filter." Amended to the reachable-by-matching-query reading, with salience ordering and mandatory truncation annotation. (2) *Disabled retrieval:* the block specified a loud raise but never said who catches it, so an ordinary turn after a crisis produced no reply and the message was dropped permanently — the belief is recorded before retrieval, so idempotency suppressed the redelivery. Amended so the switch is per-main and the pipeline contains the raise. **These two resolutions were assumptions, not human decisions — the question was put and not answered.** **KEEP:** the loud raise itself (a disable must never be mistakable for an empty ledger), and the no-outbound-belief-text boundary from the split.

- **Split at CHECKPOINT 1.** AD-18's two-channel context builder was carved into its own story, for the token ceiling and to give its byte-wise no-quotation assertion a dedicated review. **KEEP:** the carve created a safety boundary that must survive re-derivation — retrieval is still wired into the live turn, but no retrieved belief text may reach an outbound message until the builder lands. Without it the split would ship ranked beliefs to the main with no license enforcement at all.

## Design Notes

**Why the prefix is structural.** Anthropic's contextual retrieval has a model write a prefix per chunk because a chunk is a fragment torn out of a document. A belief is already a self-contained claim, so its context is recoverable from its own fields. This is claude-obsidian's tier-3 fallback — which loses most of the benefit for chunks and little of it for claims.

**Salience is derived, not counted.** The tempting implementation bumps a counter on retrieval, making materialized state a function of read traffic rather than the log, so two replays of one log disagree — AD-30's exact failure.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network
- `cd half && uv run --extra dev pytest tests/test_retrieval.py tests/test_strands.py -q` -- expected: ranking and the no-outbound-text boundary hold
- `cd half && uv run --extra dev pytest tests/test_purity.py tests/test_replay.py -q` -- expected: fold still pure, replay byte-identical
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — the design intent**

- Retrieval fuses above the store; the store never learns ranking policy.
  [`rank.py:119`](../../../../half/retrieval/rank.py#L119)

**AD-24 — the invariant three reviewers attacked**

- The floor that makes "never excludes" arithmetic rather than promised.
  [`strands.py:43`](../../../../half/retrieval/strands.py#L43)

- Reordering only: no argument returns a value that removes a belief.
  [`strands.py:138`](../../../../half/retrieval/strands.py#L138)

- The bound moved out of SQL into one salience-ordered place that reports truncating.
  [`rank.py:178`](../../../../half/retrieval/rank.py#L178)

**CAP-12 — the crisis disable, now per main**

- One switch per actor, beside its strands; a crisis no longer reaches other mains.
  [`registry.py:154`](../../../../half/actor/registry.py#L154)

- The raise is kept, and caught in exactly one place, so a disable costs no message.
  [`runtime.py:160`](../../../../half/actor/runtime.py#L160)

**Ranking**

- Salience computed from folded state — never a counter a read bumps.
  [`salience.py:1`](../../../../half/retrieval/salience.py#L1)

- The structural prefix: no model, and template words kept out of the index.
  [`prefix.py:1`](../../../../half/retrieval/prefix.py#L1)

- One unicode tokenizer shared by prefix, strands and the query builder.
  [`text.py:1`](../../../../half/text.py#L1)

**Degradation**

- Absent, failing and misbehaving rerankers all yield one order plus an annotation.
  [`port.py:1`](../../../../half/retrieval/port.py#L1)

**Tests that carry the design**

- Every fusion factor pinned by ids arranged so the tie-break gives the wrong answer.
  [`test_retrieval.py:1`](../../../../half/tests/test_retrieval.py#L1)

- Reachability asserted through a real turn, not by grepping source text.
  [`test_strands.py:1`](../../../../half/tests/test_strands.py#L1)
