---
title: 'Story 3 — Ingestion and secret exclusion'
type: 'feature'
created: '2026-08-31'
status: 'done'
baseline_commit: '629f89a'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Half can hold a conversation but cannot see anything. The revealed ledger — what the main actually does — comes from their sources, and reading someone's mail is where this product is most capable of harming them.

**Approach:** Deliver CAP-13 in full and CAP-3's ingestion half: the `SourceStore` port (AD-13), a `MailSource` port with a Gmail implementation, immutable content-addressed capture, secret detection that runs *before anything is persisted*, and the union-find independence machinery that keeps corroboration honest. **Claim derivation is deferred** — it needs the model port, which is a separate concern.

## Boundaries & Constraints

**Always:**
- **Message bodies are never persisted.** A body is normalised, scanned, handed to its consumer, and discarded in memory. What is retained is a *receipt* — digest, provenance, and the record of what was redacted (AD-13).
- **Every string in a receipt is scrubbed**, not only the body. Subject, sender, and any metadata that reaches disk goes through the same gate.
- **Normalise before scanning.** Content-transfer-encoding, charset, and markup are decoded first — a regex cannot match a secret it is reading in the wrong representation.
- A secret is never written, even transiently — not to the log, a projection, a debug artifact, a cache, or a temp file. Detection runs before persistence, never after (AD-11, CAP-13).
- Sources are immutable and content-addressed. A captured source is never edited.
- Layer 1 lives behind the `SourceStore` port: local filesystem for self-host, S3-compatible for hosted. Layers 2–4 stay local (AD-13).
- Independence is union-find over origin, content hash, and declared key. **Ten mentions in one thread is one support** — without this the belief set inflates with echoes and "bounded" fails in the first noisy month.
- OAuth tokens live outside every layer the main can export or replay (AD-11). The token is supplied; acquiring it interactively is deferred.
- Ingestion is idempotent: re-reading a mailbox captures nothing twice.
- Nothing here reads a clock, calls a model, or touches the network inside a fold (AD-30).

**Ask First:**
- Any runtime dependency beyond the standard library and pinned SDKs.
- Any change to the secret-pattern set that *removes* a pattern.
- Persisting anything derived from a source other than through the store's ops.

**Never:**
- No model call and no claim derivation — deferred with the model port.
- No interactive OAuth consent flow — deferred; the token arrives already acquired.
- No message bodies in logs, metrics, or error text (AD-22).
- Never ingest from an address that is not a registered main's own account.
- Do not build retrieval ranking, governance, or the crisis logic.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Capture a message | One mail message | A scrubbed **receipt** is stored; the body is discarded in memory | N/A |
| Body on disk | Any ingested message | The body text appears nowhere under the store root | N/A |
| Secret in the subject | Secret in a header field rather than the body | Redacted before the receipt is written | Never persisted |
| Quoted-printable | Secret split by a soft line break | Decoded, then detected | Never persisted |
| Alternate charset | Body in latin-1, UTF-16, or ISO-2022-JP | Decoded via the declared charset, then scanned | Undeclared or undecodable fails closed |
| HTML markup | Secret interrupted by tags or entities | Markup stripped, then detected | Never persisted |
| Re-ingest | The same message twice | Captured once; the second is a no-op | N/A |
| Secret in a body | Message containing a token or recovery code | Redacted before anything is written; the redaction is recorded, the value is not | Never persisted anywhere |
| Secret-only message | Body is nothing but a credential | Not captured at all | N/A |
| Non-UTF-8 part | Attachment or body that will not decode | Scanned as bytes; unscannable content is treated as a finding | Fails closed, never skipped |
| Independence, one thread | Ten messages sharing a thread id | Counts as **one** independent support | N/A |
| Independence, forwarded | Same content, different senders | Collapsed by content hash to one support | N/A |
| Independence, distinct | Two unrelated senders, unrelated threads | Two independent supports | N/A |
| Token storage | A token is supplied for a main | Written outside every store layer, via the SecretStore port | Absent from any export |
| Fetch failure | The provider errors mid-page | Raised as a domain error; captured pages already written stay valid | Resumable, never partial-and-silent |
| Unknown account | A message addressed to a non-main | Not captured | Logged without content |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. AD-3, 11, 13, 22, 26, 30 govern this story.

**Reference (extracted from the manifest):** `claude-obsidian/claude_obsidian/ledgers.py::_independent_group_count` — union-find where each source contributes an identity *set* (id, canonical origin, content hash, declared key) and any shared value unions two sources. Its provenance rules also state the principle: sources sharing an `independence_key` are not independent corroboration.

**Existing, reused:** `half/store/store.py`, `half/store/export.py` (`SECRET_PATTERNS`, already covers the token shapes), `half/errors.py`, `half/config.py`.

**To create:**
- `half/store/sources.py` — the `SourceStore` port and its local implementation (deferred from story 1).
- `half/ingest/port.py` — the `MailSource` port and a normalized `Message`.
- `half/ingest/scrub.py` — secret detection and redaction, applied before persistence.
- `half/ingest/independence.py` — union-find corroboration.
- `half/ingest/pipeline.py` — fetch, scrub, capture; idempotent.
- `half/ingest/gmail.py` — a **thin** Gmail `MailSource`: fetch with a supplied token, transport injected. The interactive OAuth consent flow is deferred.
- `half/secrets.py` — the `SecretStore` port keeping OAuth tokens outside every layer.
- `half/tests/` — `test_scrub.py`, `test_independence.py`, `test_ingest.py`, `test_secrets.py`.

## Tasks & Acceptance

**Execution:**
- [x] `half/store/sources.py` -- `SourceStore` port + content-addressed local store -- AD-13
- [x] `half/secrets.py` -- `SecretStore` port; tokens outside every exportable layer -- AD-11
- [x] `half/ingest/port.py` -- `MailSource` protocol and a normalized `Message` -- port stays narrow
- [x] `half/ingest/scrub.py` -- detect and redact before persistence; fails closed on undecodable bytes -- CAP-13
- [x] `half/ingest/independence.py` -- union-find over origin, content hash, declared key -- CAP-3
- [x] `half/ingest/pipeline.py` -- fetch, scrub, capture; idempotent by digest -- CAP-3
- [x] `half/ingest/gmail.py` -- thin Gmail `MailSource` taking a supplied token; transport injected so tests stay offline -- validates the port with a real implementation
- [x] `half/tests/test_scrub.py` -- one case per secret shape, plus non-UTF-8 and secret-only bodies -- I/O matrix
- [x] `half/tests/test_independence.py` -- thread, forward, and distinct-source cases -- I/O matrix
- [x] `half/tests/test_ingest.py` -- capture, idempotency, resumability, unknown account -- I/O matrix
- [x] `half/tests/test_secrets.py` -- tokens absent from log, projections, replay and export -- AD-11

**Acceptance Criteria:**
- Given a seeded mailbox containing credentials **in bodies, subjects, and headers**, when it is ingested, then no secret value appears anywhere under the store root, verified by scanning every byte written.
- Given any ingested message, when the store root is scanned, then its body text appears nowhere — retention is a receipt, not a copy.
- Given a secret encoded as quoted-printable, base64, latin-1, UTF-16, or interrupted by HTML markup, when it is ingested, then it is detected and never written.
- Given a new field added to the stored receipt, when the suite runs, then a test fails unless that field passes through the scrubber.
- Given the same mailbox ingested twice, when the second run completes, then no source is captured twice and no belief is duplicated.
- Given ten messages sharing one thread id, when independence is computed, then the support count is one.
- Given two unrelated senders on unrelated threads, when independence is computed, then the support count is two.
- Given a stored access token, when a full export is produced, then it contains no token material.
- Given a message body that will not decode as UTF-8, when it is scanned, then it is treated as a finding rather than skipped.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access.

## Design Notes

**Scrub before capture, not after.** The obvious shape — capture the raw message, then redact — writes the secret to disk first. Sources are immutable and content-addressed, so that write is permanent and the digest is of the unredacted bytes. Detection has to run on the in-memory body before anything reaches the `SourceStore`.

**Independence needs a declared key for mail.** The union-find takes an identity set per source; for email the natural members are the thread id, the sender, and the content hash. Ten replies in a thread share a thread id and collapse to one; a forward from a different sender collapses by content hash.

**Why derivation is deferred.** Turning a source into a claim requires the model port (AD-19), which is unbuilt, and its own decisions about prompt shape and cost. Bundling it here would put the safety-critical secret path in the same review as a model integration.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_secrets.py tests/test_scrub.py -q` -- expected: the secret paths pass
- `cd half && uv run --extra dev pytest tests/test_dependencies.py -q` -- expected: no undeclared dependency
- `cd half && git status --porcelain` -- expected: clean tree after commit
