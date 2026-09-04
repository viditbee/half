---
title: 'Story 1 — The store: belief log, pure fold, and index'
type: 'feature'
created: '2026-08-31'
status: 'done'
baseline_commit: 'NO_VCS'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Half has no store. Every later story reads or writes a main's memory, so until the substrate exists with its invariants enforced in code, each will invent its own conventions and diverge.

**Approach:** Build the durable core of the per-main store (CAP-5, CAP-14): a closed op vocabulary, an append-only JSONL belief log that is the sole source of truth, a pure fold over it, and a disposable SQLite file holding the materialized state plus an FTS5 index. Export is a directory operation, not a serializer. Two tests prove the design rather than describe it.

## Boundaries & Constraints

**Always:**
- The JSONL log is the only authority. SQLite is derived and may be deleted at any moment (AD-3).
- Corrections are appends. No log record is mutated or removed in place; `retract`, `revise`, and `expunge` are ops (`expunge` tombstones).
- Replay is pure — a fold is a pure function of the log alone (AD-30). No model call, no network, no clock read, **and no read of ambient process state** (environment, filesystem, config). Folding the same log must produce identical state on any machine, in any process.
- The op vocabulary is closed, enumerated in one module, and carries a schema version. An unknown op on replay raises; it is never skipped (AD-29).
- Exactly one writer per store instance; appends use `O_APPEND` with `fsync`, and durability covers short writes and the parent directory entry (AD-1).
- A record that the derived view cannot materialize must be rejected **before** it is appended. The log is append-only, so a bad line is permanent.
- Volatile state is never written to the log (AD-26).

**Ask First:**
- Adding any runtime dependency beyond the Python standard library.
- Any change to the log record shape or the op vocabulary.
- Introducing a second writer, a lock file, or a background compaction process.

**Never:**
- Never destroy anything at the export destination. Stage, scan, then move.
- Never raise a bare non-`HalfError` from a public store operation.
- No credentials, tokens, or secrets anywhere in the store tree — those live outside all four layers (AD-11).
- No ORM, no migration framework, no vector store, no embedding call.
- No network access and no `datetime.now()` inside fold or replay.
- Do not build the SourceStore port or the projection renderer — both are deferred to their consuming stories. Do not build ingestion, retrieval ranking, governance, or channels.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Append a belief | Empty store, one `assert` record | Line appended to `beliefs/YYYY-MM.jsonl`; fold reflects it | N/A |
| Replay from scratch | Populated store, SQLite deleted | Rebuilt state byte-identical to pre-delete state | N/A |
| Unknown op | Log line with an op outside the vocabulary | Raises `UnknownOpError` naming the op and line number | Hard error, never skipped |
| Corrupt line | Malformed JSON mid-log | Raises `CorruptLogError` with file and line number | Hard error, no partial silent fold |
| Retract then fold | `assert` b_x, later `retract` b_x | b_x absent from the fold; both records still in the log | N/A |
| Expunge | `expunge` b_x | Bodies tombstoned across all shards, then the op appended; fold omits it | Validate every shard first — abort before mutating any. Idempotent, so a resume completes a partial run |
| Expunge, unparseable shard | A later shard holds a corrupt or unknown-op line | Raises before any shard is rewritten | No partial erasure |
| Unknown field | Record carrying a field this version doesn't know | Preserved verbatim through decode and re-encode | N/A |
| Export | Populated store | Directory copy sufficient to reconstruct state; no secret material | N/A |
| Month rollover | Appends spanning a month boundary | Second shard created; replay reads shards in chronological order | N/A |
| FTS query | Beliefs indexed | `bm25()`-ranked results over claim text | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding; AD-1, 3, 4, 5, 11, 26, 29, 30 govern this story, and `glossary.md` supplies the vocabulary to use in code.

**Read-only references (study, never import):**
- `graphiti/graphiti_core/edges.py:271-280` — four timestamps separating *we were wrong* from *you changed*.
- `claude-obsidian/claude_obsidian/ledgers.py` — strict JSON loading rejecting duplicate keys and non-finite values.

**To create:**
- `half/pyproject.toml`, `README.md`, `.gitignore` — new git repo, Python 3.12+, stdlib runtime.
- `half/half/errors.py` — `StoreError`, `UnknownOpError`, `CorruptLogError`.
- `half/half/store/ops.py` — the closed op vocabulary + `SCHEMA_VERSION`.
- `half/half/store/records.py` — record types; decode/encode preserving unknown fields.
- `half/half/store/log.py` — `BeliefLog`: append, ordered iteration, month sharding.
- `half/half/store/fold.py` — pure fold over records → state.
- `half/half/store/db.py` — SQLite schema, FTS5 table, `bm25()` query surface, `rebuild()`.
- `half/half/store/store.py` — `Store` façade owning the directory and the single writer.
- `half/half/store/export.py` — directory export + secret-absence assertion.
- `half/tests/` — see Verification.

## Tasks & Acceptance

**Execution:**
- [x] `half/pyproject.toml` -- init repo; Python 3.12+; pytest the only dev dependency -- stdlib-only runtime
- [x] `half/half/store/ops.py` -- enumerate `assert`, `retract`, `revise`, `expunge`, `tension`, `loop_transition`; `SCHEMA_VERSION` -- AD-29
- [x] `half/half/store/records.py` -- record types; strict decode; unknown fields preserved verbatim -- forward compatibility
- [x] `half/half/store/log.py` -- `O_APPEND` + `fsync` writer, month sharding, chronological iteration -- AD-1, AD-3
- [x] `half/half/store/fold.py` -- pure fold; imports no time, random, network, or model module -- AD-30
- [x] `half/half/store/db.py` -- SQLite schema + FTS5 virtual table with `bm25()`; `rebuild()` from the log -- AD-5
- [x] `half/half/store/store.py` -- `Store` façade; one writer; open / append / rebuild / export -- AD-1
- [x] `half/half/store/export.py` -- export a store directory; assert no secret material -- CAP-14, AD-11
- [x] `half/tests/test_replay.py` -- the replay invariant, with a fixture spanning a model-tier change -- AD-4
- [x] `half/tests/test_ops.py` -- unknown op, corrupt line, retract, expunge, unknown field, month rollover -- I/O matrix
- [x] `half/tests/test_purity.py` -- static assertion that fold imports no clock, network, or model module -- AD-30

**Acceptance Criteria:**
- Given a populated store, when the SQLite file is deleted and replay runs, then the rebuilt state is byte-identical to the state before deletion.
- Given the same log folded twice, when results are compared, then they are identical and no clock, network, or model call occurred.
- Given a log containing an op outside the vocabulary, when replay runs, then it raises naming the op and line number rather than skipping the line.
- Given an exported store directory, when scanned for known token patterns, then no secret material is found.
- Given only the standard library plus pytest, when the suite runs, then it passes.

## Design Notes

**Record shape** (from the person-epistemics companion, minus the removed `confidence` field):

```jsonl
{"t":"2026-08-14T09:12Z","op":"assert","id":"b_7f2","subject":"self",
 "claim":"replies to mother within 3 minutes, consistently",
 "ledger":"revealed","support":["s_a91","s_c04"],"independent":2,
 "license":"behave","last_corroborated":"2026-08-14","loop":null}
```

**Why `test_purity.py` exists.** "Just re-derive it" is the natural way to write a fold, and it silently breaks AD-4 the first time a main changes model tier. A static import check catches a regression that a passing fold test would not.

**Sharding.** `beliefs/YYYY-MM.jsonl`, read in filename order. It serves file size and git diffs only — no semantics, and the fold must never depend on shard boundaries.

## Verification

**Commands:**
- `cd half && uv run pytest -q` -- expected: all tests pass
- `cd half && uv run pytest tests/test_replay.py -q` -- expected: byte-identical rebuild, including across the tier-change fixture
- `cd half && uv run python -c "import sqlite3;sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE t USING fts5(x)')"` -- expected: no error, confirming FTS5 needs no dependency
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — the design intent**

- The four layers, the single writer, and what is authoritative versus disposable.
  [`store.py:1`](../../../../half/store/store.py#L1)

**The truth layer**

- The closed vocabulary. An unknown op is fatal, never skipped — the whole of AD-29.
  [`ops.py:1`](../../../../half/store/ops.py#L1)

- Strict decode: duplicate keys and non-finite numbers rejected, unknown fields preserved.
  [`records.py:63`](../../../../half/store/records.py#L63)

- Fields validated before append, because the log is append-only and a bad line is permanent.
  [`records.py:130`](../../../../half/store/records.py#L130)

- Durable append: looped writes, truncate-on-failure, directory fsync for a new shard.
  [`log.py:47`](../../../../half/store/log.py#L47)

**The pure fold — the invariant everything rests on**

- A pure function of the log alone. No clock, no network, no ambient state.
  [`fold.py:1`](../../../../half/store/fold.py#L1)

- Corrections must name their target; a silent no-op is the failure AD-29 exists to prevent.
  [`fold.py:120`](../../../../half/store/fold.py#L120)

**Erasure — where partial failure is least acceptable**

- Validate every shard before mutating any; idempotent, so a resume completes.
  [`log.py:74`](../../../../half/store/log.py#L74)

- Tombstone bodies first, then append the op, so a crash fails safe.
  [`store.py:95`](../../../../half/store/store.py#L95)

**The derived view**

- Wholesale rebuild, never incremental — how a derived store starts holding orphan state.
  [`db.py:60`](../../../../half/store/db.py#L60)

- BM25 ranking; the query is a main's own words, so operators are input, not syntax.
  [`db.py:120`](../../../../half/store/db.py#L120)

**Export — three guarantees that were false and now are not**

- Stage, scan, move. A refusal cannot cost the main a file.
  [`export.py:78`](../../../../half/store/export.py#L78)

- Reads bytes and fails closed; a single invalid byte used to disable the scan.
  [`export.py:46`](../../../../half/store/export.py#L46)

- Excludes the database by prefix; the WAL held uncheckpointed belief text.
  [`export.py:110`](../../../../half/store/export.py#L110)

**Tests that carry the design**

- Byte-identical rebuild across a fixture spanning a model-tier change.
  [`test_replay.py:1`](../../../../half/tests/test_replay.py#L1)

- Static purity gate; the ambient-state case is the one the first version missed.
  [`test_purity.py:88`](../../../../half/tests/test_purity.py#L88)

- One test per matrix row, plus every hole the three reviewers proved was open.
  [`test_ops.py:230`](../../../../half/tests/test_ops.py#L230)
