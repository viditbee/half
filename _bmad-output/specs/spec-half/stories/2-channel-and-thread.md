---
title: 'Story 2 — Channel and thread (Telegram)'
type: 'feature'
created: '2026-08-31'
status: 'done'
baseline_commit: '800cb1c'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The store exists but nothing can reach it. Half has no way to receive a message from its main or answer one, and every later story assumes a live thread.

**Approach:** Deliver CAP-1 for Telegram — one persistent thread per main, one Half behind it — through the narrow `Channel` port (AD-7). Telegram runs on long-polling and needs no public URL, which is why AD-16 makes it the self-host default. `capability_query` answers *"may I send an unprompted message right now?"*, the operation that makes the morning surface and every later nudge legal. WhatsApp arrives later behind the same port.

## Boundaries & Constraints

**Always:**
- The `Channel` port has exactly four operations — `receive`, `send`, `draft_link`, `capability_query` — and the actor never learns which platform it is on (AD-7). Platform contact rules are answered by `capability_query` and nowhere else.
- `half.crisis` owns the inbound entrypoint from this story's first line, though its logic lands in story 6. The pipeline has exactly one caller (AD-10).
- One actor per main — an inbox plus a mutex, not a process. Eviction requires a free mutex (AD-8, AD-33).
- Half sends only to its own main; outbound to anyone else is a draft the main dispatches (AD-25).
- One persistent thread per main, never asked to open a new one. Inbound handling is asynchronous (AD-23).
- **Per-message isolation.** No single message's failure may end the inbound loop for any main.
- **At-least-once delivery.** The transport commits its position only after a turn completes, and the turn is idempotent, so redelivery duplicates nothing.
- A `main_id` is a path segment. It is validated against a safe charset before it ever reaches the filesystem.
- The story ships a composition root: config, transport, channel, registry and runtime wired into something startable.

**Ask First:**
- Any runtime dependency beyond the standard library and the official Telegram SDK.
- Any fifth operation on the `Channel` port.
- Storing message text anywhere other than through the store's existing ops.

**Never:**
- No LLM call anywhere in this story. The responder is a deterministic stub later stories replace.
- No credentials in the store tree; the bot token comes from the environment (AD-11).
- Do not build governance, licensing, retrieval ranking, ingestion, or the crisis logic itself.
- Do not build the WhatsApp adapter — deferred to its own story behind this port.
- Never send to a chat id that is not a registered main's.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Inbound text | Registered main sends a message | Routed to that main's actor; reply sent on the same thread | N/A |
| Unknown sender | Message from an unregistered chat id | Ignored; nothing written to any store | Logged without message content |
| Cold start | Main has never messaged the bot | `capability_query` reports unprompted send disallowed | Never attempts the API call |
| After first inbound | Main has messaged once | Unprompted send reported allowed, permanently | N/A |
| Concurrent inbound | Two messages for one main arrive together | Serialized through that main's mutex; both land in log order | N/A |
| Dormant actor | Message for an evicted main | Actor rehydrated from disk, then handled | N/A |
| Eviction pressure | Cache full while an actor is mid-turn | The busy actor is never evicted | N/A |
| Third-party address | Outbound requested to a non-main chat id | Refused; a draft link is produced instead | Raises rather than sending |
| Send failure | Platform returns an error | Raised as a domain error; the runtime **isolates it to that message and continues** | Retryable is retried with backoff; permanent is dropped. One main's failure never stops the worker |
| Redelivery | The same platform message arrives twice | Handled **at-least-once**: the turn is idempotent, so a redelivered message produces no duplicate belief | The transport commits its offset only after the turn completes |
| Turn raises | Any handler error mid-turn | Logged without message content; the loop continues with the next message | Never terminates the inbound loop |
| Long reply | Reply exceeds the platform limit | Split on that limit, order preserved | N/A |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. AD-1, 7, 8, 10, 16, 17, 25, 33 govern this story; `glossary.md` supplies the vocabulary.

**Reference** — the extraction manifest holds the detail. `hermes-agent/gateway/platforms/base.py` supplied the adapter shape and typing-heartbeat pattern (extracted); its `whatsapp_cloud.py` is recorded there as *not portable*.

**Existing, reused:** `half/half/store/store.py` (the actor owns one `Store` per main) and `half/half/errors.py`.

**To create:**
- `half/half/channel/port.py` — the `Channel` protocol and its four operations.
- `half/half/channel/window.py` — reachability state per chat; the single home of platform contact rules.
- `half/half/channel/telegram.py` — long-polling adapter, no public URL.
- `half/half/actor/registry.py` — inbox, mutex, LRU, hydration, eviction safety.
- `half/half/crisis/gate.py` — owns the entrypoint; pass-through until story 6.
- `half/half/config.py` — registered mains and channel binding from the environment.
- `half/tests/` — `test_channel.py`, `test_actor.py`, `test_entrypoint.py`.

## Tasks & Acceptance

**Execution:**
- [x] `half/half/channel/port.py` -- `Channel` protocol, `Inbound`, `SendResult`, `Reachability` types -- AD-7
- [x] `half/half/channel/window.py` -- reachability per chat; the only place platform contact rules live -- AD-7
- [x] `half/half/channel/telegram.py` -- long-polling adapter; cannot-DM-first encoded in `capability_query` -- AD-16
- [x] `half/half/actor/registry.py` -- one actor per main; mutex, LRU, hydration, eviction never mid-turn -- AD-8, AD-33
- [x] `half/half/crisis/gate.py` -- owns the inbound entrypoint and delegates inward -- AD-10
- [x] `half/half/config.py` -- registered mains and channel binding from env; no secrets stored -- AD-11
- [x] `half/half/errors.py` -- `ChannelError`, `SendFailed`, `UnknownSender`, `NotReachable` -- typed failures
- [x] `half/tests/test_channel.py` -- port behaviour, reachability, splitting, unknown senders, third-party refusal -- I/O matrix
- [x] `half/tests/test_actor.py` -- serialization, hydration, eviction safety -- I/O matrix
- [x] `half/tests/test_entrypoint.py` -- the pipeline has exactly one caller, asserted statically -- AD-10
- [x] `half/.github/workflows/ci.yml` -- widen the AD-2 gate from stdlib-only to an allowlist of stdlib plus pinned deps -- the Telegram SDK pulls httpx

**Acceptance Criteria:**
- Given a registered main sends a message, when it is handled, then a reply is delivered on the same thread and the exchange is recorded in that main's store.
- Given two messages for one main arrive concurrently, when both are handled, then they serialize through one mutex and appear in the log in order.
- Given a main who has never messaged the bot, when an unprompted send is attempted, then `capability_query` reports it disallowed and no API call is made.
- Given an outbound request addressed to anyone other than the main, when it is issued, then it raises and produces a draft link instead.
- Given the repository, when the entrypoint test runs, then the normal pipeline has exactly one caller and it is the crisis gate.
- Given only the standard library plus the pinned Telegram SDK and pytest, when the suite runs, then it passes with no network access.
- Given an unpinned dependency is imported by the runtime, when CI runs, then the AD-2 gate fails naming it.

## Design Notes

**Why the crisis gate exists now.** AD-10 inverts the dependency — crisis owns the entrypoint and calls the pipeline. Building the entrypoint without that shape would force story 6 into exactly the refactor AD-10 warns gets skipped. The gate is a pass-through here; only its position is load-bearing, and a test pins it.

**Reachability is derived, not stored.** Whether Half may contact a main unprompted is a function of the last inbound message, already an event in the store. `window.py` computes it and keeps no second source of truth (AD-3). It is named `Reachability` rather than `Window` because Telegram's rule is a one-way latch and WhatsApp's is a rolling window; the port must express both.

**The dependency gate must widen.** `python-telegram-bot` pulls `httpx`, so CI's AD-2 job — which currently asserts a stdlib-only runtime — turns red on the first import. The spine's Stack table always listed both, so the gate was over-tight rather than the dependency being wrong. It becomes an allowlist of stdlib plus the pinned dependencies, which still catches an *unpinned* one creeping in.

**No model call.** The responder is deterministic, so the suite stays hermetic and offline and later stories replace the stub without touching the channel.

## Verification

**Commands:**
- `cd half && uv run --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_entrypoint.py -q` -- expected: exactly one caller into the pipeline
- `cd half && uv run python -c "import half.channel.telegram"` -- expected: imports clean with no credentials present
- `cd half && git status --porcelain` -- expected: clean tree after commit
