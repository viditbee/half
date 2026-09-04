---
title: 'Story 9b — The model port'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: 'fd5d06d178fe7c9ddb3bdbbd83a653df47a34274'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/constitution.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Five stories have deferred work to a model port that does not exist — claim derivation, crisis classification, consolidation, tension minting and the reply itself. Each deferred rather than design against a shape nobody had fixed.

**Approach:** Deliver AD-19: one `ModelProvider` port with one implementation. Classification and generation are **separate operations**, cache breakpoints are **first-class**, submission is available in **batch** as well as inline, and the tier travels with the main. The suite stays hermetic: the transport is injected, as story 2 did for Telegram.

## Boundaries & Constraints

**Always:**
- **Classify and generate are different operations.** A caller that may only classify holds something with no way to produce text. This is what makes *"a model never authors a word a main in crisis reads"* a property rather than a rule, and it is the reason the port is shaped this way at all.
- **A classification returns a decision and never prose.** No free text comes back on that path, in any field.
- **Failure is explicit and never a silent default.** The port reports unavailable, refused, over-budget and malformed distinctly; it never substitutes a plausible answer. What a failure *means* is the caller's to decide — the crisis caller fails toward entering, and the port must not decide that for it.
- **Cache breakpoints are first-class and never hidden** (AD-19). The caller states where the stable prefix ends; the port does not guess and does not silently move it. The free tier's cost model rests on this.
- **The tier travels with the main** (AD-20) and is configuration, not code. No model name is hardcoded in a call site.
- **Batch is a first-class shape, not a wrapper.** Submit and collect are distinct, a submission survives the process that made it, and a collection that is not ready yet is a normal answer.
- **A reservation is released on every path out, including a raise before the request is built.** A ceiling that binds against money nobody spent is the same defect as one that does not bind, pointing the other way — and a durable ledger makes it permanent.
- **A reservation is exchangeable exactly once, by the ledger that issued it.** Type-checking the object is a spelling; issuance and outstanding-ness are the property, and clamping a mismatch to zero turns a corrupted total into a silent one.
- **A wire-shape check reaches the keys that carry the prompt**, not only the top level. The nested message and system-block shapes are where a wrong key is a guaranteed rejection on every call.
- **An import scan resolves relative imports**, and its non-vacuity case uses a spelling the scan does not already assume.
- **A cost budget is enforced by the port**, per call and per pass, and exceeding it is a refusal rather than a spend — **including under concurrency**. Admission reserves; a ledger that only advances after a round trip does not bind when calls overlap, which is the shape the scheduler ships with.
- **The estimate errs high in every script.** A characters-per-token constant tuned on Latin prose under-charges Chinese, Japanese, Thai and Devanagari by a multiple, and under-charging spends money the budget said was not there — for exactly the mains story 4c exists for.
- **Every declared failure reason is produced by some path.** A closed set whose members are unreachable is decoration, and a rejected credential must be distinguishable from a content refusal, because callers fail in different directions on each.
- **What a failure cost is reported truthfully.** A request rejected before any token was billed did not spend.
- **A batch that cannot become ready says so.** Not-ready is an answer; not-ever is a different answer, and a caller must be able to stop polling.
- **A narrow holder has narrow authority, not merely narrow output.** The object a crisis caller holds must not be able to move shared cost accounting or reconfigure tiers — being unable to produce text is half of the guarantee.
- **The per-pass ledger is as durable as the submission it prices.** A budget that resets on restart while a committed batch survives is not a ceiling.
- **Wire shapes are checked against the provider's documented contract, not against themselves.** A test that reads back what the renderer just wrote proves the renderer is self-consistent and nothing about whether the request is valid.
- **A guard over logging covers the whole call**, format string included. An f-string is how a completion actually reaches a log.
- **The suite is hermetic.** The implementation imports and constructs with no network, no key, and no environment; the transport is injected. No test reaches the network.
- **Credentials never enter the store tree** (AD-11) and never appear in logs or errors (AD-22). No prompt content, no completion text and no main's words are logged.
- **No model call inside a fold, ever** (AD-30). Replay stays pure.

**Ask First:**
- Any runtime dependency beyond the standard library and pinned SDKs.
- A second implementation — AD-19 says build it when a self-hoster arrives with a non-Anthropic key, not before.
- Any operation beyond classify, generate, submit and collect.

**Never:**
- No claim derivation, no crisis classifier, no consolidation, no reply generation — those are the consumers, each its own story.
- No prompt content in this story beyond what the port needs to be exercised; prompts belong to their consumers.
- No wiring into the live turn. **This port ships with no production caller, deliberately** — see Design Notes.
- No retry that turns a refusal into a spend, and no fallback tier chosen by the port.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Classify | A classification request | A decision; no prose in any field | N/A |
| Classifier cannot generate | A classify-only holder | No method produces text — structurally | Asserted, not documented |
| Generate | A generation request | Text | N/A |
| Unavailable | The transport fails | Reported distinctly | Never a substituted answer |
| Refused | The provider refuses | Reported distinctly from unavailable | Caller decides meaning |
| Over budget | A call exceeding the budget | Refused before spending | Never a partial spend |
| Malformed reply | The provider returns something unusable | Reported distinctly | Never coerced into a decision |
| Cache breakpoint | A stable prefix and a variable suffix | The breakpoint is where the caller put it | Never moved silently |
| No breakpoint | A caller that states none | No caching claimed; cost reflects it | Never guessed |
| Tier from the main | Two mains on different tiers | Each call uses that main's tier | Never a global default |
| Unknown tier | A tier the build does not know | Refused | Never a silent fallback |
| Batch submit | A batch of requests | An identifier that outlives the process | Durable |
| Batch not ready | Collection before completion | A normal not-ready answer | Not an error |
| Batch partial | Some succeeded, some failed | Per-item outcomes | Never all-or-nothing |
| Offline construction | No key, no network, no environment | Imports and constructs | Never reaches out |
| Secrets | A key is configured | Absent from the store tree, logs and errors | Asserted byte-wise |
| Content in logs, any spelling | An f-string, a `%s` argument, a renamed logger | A test fails | The format string is arg 0 |
| Concurrent spend | Calls overlapping at the scheduler's bound | The pass ceiling still binds | Admission reserves |
| Non-Latin estimate | CJK, Thai, Devanagari text | Estimated at or above its real cost | Never under |
| Cache write TTL | A one-hour write | Charged at the one-hour basis | Not the five-minute one |
| Rejected credential | A bad key | Reported as not-authorised, and as unspent | Never a content refusal |
| Unusable batch | A submission that can never complete | A distinct answer; polling stops | Never forever-early |
| Narrow authority | The classify-only holder | Cannot move the ledger or the tiers | Not only text |
| Ledger across restart | Submit, crash, restart | The pass total survives | Not a fresh budget |
| Wire shape | Every rendered request | Checked against the documented contract | Not against the renderer |
| Inside a fold | A fold running | No model call is reachable from it | AD-30, asserted |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding. AD-9, 11, 19, 20, 22, 30 govern.

**Load the `claude-api` skill before writing any provider code** — it carries the current model identifiers, the prompt-caching `cache_control` shape, the Message Batches endpoints and the extended-thinking parameters, several of which changed in 2025–2026. Do not write SDK usage from memory.

**Existing, reused:** `half/channel/telegram_transport.py` (the injected-transport pattern that keeps the suite offline — follow it), `half/secrets.py` (`SecretStore`, where a key belongs; AD-11), `half/actor/registry.py` (`Actor`, where the tier travels), `half/config.py`, `half/errors.py`, `half/retrieval/port.py` (the one-method `Reranker` port — the narrowness to imitate; gbrain's hundred-method interface is the lesson).

**To create:**
- `half/model/port.py` — the protocols: classify, generate, submit, collect; the request and outcome types; the cache breakpoint.
- `half/model/tier.py` — tiers as configuration, resolved per main.
- `half/model/budget.py` — per-call and per-pass cost limits and their refusals.
- `half/model/anthropic.py` — the one implementation, transport injected.
- `half/tests/test_model.py`, `half/tests/test_model_offline.py`.

**To change:** `.github/workflows/ci.yml` (an AD-19 gate and an offline gate, floors with margin), `pyproject.toml` (the pinned SDK, if one is used).

## Tasks & Acceptance

**Execution:**
- [x] `half/model/port.py` -- classify and generate as separate protocols; a classifier cannot produce text -- crisis constraint
- [x] `half/model/port.py` -- explicit outcomes: unavailable, refused, over-budget, malformed -- never a silent default
- [x] `half/model/port.py` -- cache breakpoints first-class; batch submit and collect -- AD-19, AD-9
- [x] `half/model/tier.py` -- tier as config, resolved from the main; unknown tier refused -- AD-20
- [x] `half/model/budget.py` -- per-call and per-pass limits; over-budget refuses before spending -- CAP-7
- [x] `half/model/anthropic.py` -- one implementation, transport injected, constructs offline -- hermetic suite
- [x] `.github/workflows/ci.yml` -- AD-19 and offline gates with real margin -- gates must not pass vacuously
- [x] `half/tests/test_model.py` -- one case per matrix row -- I/O matrix
- [x] `half/tests/test_model_offline.py` -- the whole suite reaches no network, asserted at the socket -- hermetic

**Acceptance Criteria:**
- Given a classify-only holder, when the repository is scanned, then no path from it produces text, and adding one fails a test.
- Given a transport failure, a provider refusal, an over-budget call and a malformed reply, when each occurs, then the four are reported distinctly and none yields a substituted answer.
- Given a caller that states a cache breakpoint, when the request is built, then the breakpoint is exactly where the caller put it.
- Given two mains on different tiers, when each makes a call, then each uses their own tier and no call names a model directly.
- Given a call that would exceed the budget, when it is made, then it is refused before any spend.
- Given a submitted batch, when the process restarts, then the submission is still collectable.
- Given a batch where some items failed, when it is collected, then per-item outcomes are returned rather than one verdict.
- Given no key, no network and no environment, when the implementation is imported and constructed, then it succeeds and reaches nothing.
- Given a configured key, when the store tree, logs and errors are scanned, then no key material and no prompt or completion text appears.
- Given the repository, when the suite runs, then no model call is reachable from a fold, and the whole suite reaches no network.

## Spec Change Log

- **Review round 1 — the budget does not bind, and two guarantees were half-checked.** Verified: eight concurrent calls at the scheduler's own `DEFAULT_BOUND` spent 48,000 against a 7,000 per-pass ceiling, because `admit` checks without reserving and the ledger only advances after the round trip. 300 CJK characters estimate to 108 tokens, identical to 300 Latin — a three-fold under-charge in exactly the scripts story 4c exists for. `logger.info(f"got {reply}")` passes the AD-22 scan, which inspects `args[1:]` and never the format string, and the non-vacuity test reproduces the same blind spot. The classify-only holder cannot produce text — that held — but exposes `spend` and `tiers`, so the crisis path's narrow object can reset the pass ledger. Also: one-hour cache writes are charged at the five-minute basis (a 37.5% under-charge); `Failure.spent` reports `True` for credential rejections that were never billed; `_translate`'s fallback turns a wrong payload key into a retryable `unavailable`, so a permanently broken request shape is retried for ever; `Reason.NOT_AUTHORISED` and `Reason.NO_SUCH_BATCH` are declared and never produced; a batch that can never complete is indistinguishable from one that is merely early; the per-pass ledger is in-memory while submissions are durable; the secrets test creates an empty directory and asserts it is empty; and no wire shape is checked against anything but the renderer that produced it. **KEEP:** classify and generate as separate protocols, `Failure` carrying only closed enums with no free-text field, the socket-level offline gate, and the cache breakpoint being where the caller put it — all four held under mutation.

## Spec Change Log

- **Review round 2 — the round-1 fixes interacted to make a new leak, and it is durable.** Verified: the cache-minimum refusal added in round 1 raises from the renderer, which is after `admit` reserves and outside any handler in `classify` and `generate` — so every such raise leaks the reservation (524, then 1,048, then 1,572, with `remaining` never recovering), and round 1's durable `Ledger` carries the corruption across a restart. Three round-1 fixes combining into a fourth defect. Also verified: that same cache-minimum refusal is entirely unverified — `if False:` on the condition passes all 2,316 tests, because no test calls `render_prompt` at all; two guaranteed-400 mutations on the nested message and system-block keys (`content` → `contents`, `type: text` → `type: plaintext`) both pass, because the wire-shape scan reads only `set(payload)`; a relative import of the model port into `half/store/fold.py` passes both AD-30 scans, whose non-vacuity case uses an absolute import and so shares the assumption it should be testing; `_release` checks the type rather than issuance, so a double settle records 120 against a 100 ceiling and a foreign reservation settles clean; and the `ad19_guarantee` floor's 32-case margin is entirely guarantee cases, including the flagship concurrency fix.

## Design Notes

**Why this ships with no production caller.** Every previous story has been held to *reachable from shipped code*, and this one asks for an exception. The reason is that its five consumers are each their own story with their own risk — claim derivation touches the secret path, the crisis classifier touches the clinical protocol, consolidation touches cost. Wiring one of them here would put the port's design and that consumer's risk in a single review. The port's own correctness is a story's worth of verification on its own, and the exception is stated here rather than discovered by a reviewer.

**Why classify and generate are separate.** A single `call()` with a mode flag makes *"never authors a word a main in crisis reads"* something a caller must remember. Two protocols make it something a caller cannot do — the crisis path holds an object with no generate method, which is the same reason `Assessment` carries no text.

**Why failure is not the port's to interpret.** Crisis fails toward entering; consolidation fails toward skipping; a reply fails toward silence. One default would be wrong for two of the three, and a port that guesses removes the caller's ability to be right.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network
- `cd half && uv run --extra dev pytest tests/test_model_offline.py -q` -- expected: no socket is opened anywhere in the suite
- `cd half && uv run --extra dev pytest tests/test_purity.py tests/test_replay.py -q` -- expected: the fold is still pure
- `cd half && uv run --extra dev pytest -m cap12 -m ad9 -q` -- expected: crisis and the scheduler intact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — why the shape is the guarantee**

- Classify and generate as separate protocols; `Failure` carrying only closed enums.
  [`port.py:1`](../../../../half/model/port.py#L1)

**The ledger**

- Admission reserves; `hold` gives it back however the block exits — a control structure, not a handler at each site.
  [`budget.py:1`](../../../../half/model/budget.py#L1)

**The wire**

- The request is built before anything is reserved, so a refusal that needs no network costs nothing.
  [`anthropic.py:1`](../../../../half/model/anthropic.py#L1)

- The SDK edge, separate for the reason the Telegram transport is.
  [`anthropic_transport.py:1`](../../../../half/model/anthropic_transport.py#L1)

**Tests that carry the design**

- Wire shapes checked against the SDK's typed params, nested keys included; guarantees named so deleting one fails by name.
  [`test_model.py:1`](../../../../half/tests/test_model.py#L1)
