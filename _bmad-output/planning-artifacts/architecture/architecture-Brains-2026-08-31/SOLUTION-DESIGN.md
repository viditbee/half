# Half v1 — Solution Design

Companion to `ARCHITECTURE-SPINE.md`. The spine fixes the invariants; this explains the system to a person who has to work on it. Where the two disagree, **the spine wins** — it is the contract, this is the guide.

**Audience:** anyone joining the build, or Vidit in three months.

---

## 1. What is being built

Half is a second self that lives in a messaging thread. It reads what its main's life leaves behind (email first), asks about what no source can contain (plans, ambitions, what they're trying to become), and holds the gap between those two as the product.

The thing that makes it hard is not memory. It is **restraint** — knowing something true and deciding not to say it. Nearly every architectural decision below exists to make restraint structural rather than a matter of the model's good behaviour.

The system serves one person per instance of itself. There is no shared state between mains anywhere in v1.

---

## 2. The shape in one paragraph

Every main has a directory. That directory contains an append-only log of everything Half has come to believe about them, plus a set of readable markdown pages folded out of that log, plus a SQLite file holding a materialized copy of the current state and a full-text index. One writer owns that directory. Messages arrive through a channel adapter, pass through a crisis gate that owns the door, and land in that writer's inbox. Overnight, the same writer re-reads the day, decides what has become durable, and looks for new contradictions between what the main says and what they do.

Self-hosting runs one of these. The hosted service runs many, pinned to nodes. It is the same program.

---

## 3. The store

### Why the log is the truth

The alternative — a database as the source of truth with files as an export — was rejected deliberately. It makes export a serializer that has to be kept correct forever, it makes the authoritative representation unreadable to the person it describes, and it dissolves the reason the file format could ever become a standard other tools implement.

So: **`beliefs/YYYY-MM.jsonl` is the only authority.** Everything else can be deleted and rebuilt.

```
~/.half/<main_id>/
  sources/            content-addressed, immutable, never edited
  beliefs/2026-08.jsonl   append-only. THE TRUTH.
  loops/*.md          projections — markdown + YAML frontmatter
  people/*.md         projections
  half.db             SQLite: materialized fold + FTS5 index
```

Credentials are **not in this tree.** See §8.

### Why JSONL and not one file per belief

Beliefs are events, and there will be tens of thousands. One file each makes a hostile git repository and a slow filesystem, and nobody ever opens one alone. Loops and people are different — dozens of them, durable, each worth reading — so those get a file.

The rule: *one file per thing you would want to open; log lines for things you would never open alone.*

### Why an append never needs a lock

There is exactly one writer per main (AD-1). Under a single writer an `O_APPEND` write is atomic and free. This is the decision that lets us skip the transaction machinery claude-obsidian had to build — their vault is written by parallel agents, ours is not. If you ever add a second writer you have to build that layer, so don't.

### Replay

`half.db` is disposable. Delete it, replay the log, and you must get byte-identical state (AD-4, tested in CI).

For that to be true, **replay must be pure** (AD-30). The log stores the *outcome* of anything non-deterministic — a model call, a clock read, a network fetch — never a promise to redo it. This is the invariant most likely to be broken by accident, because "just re-derive it" is the natural way to write a fold. It's also why the CI fixture must deliberately span a model-tier change; a fixture that doesn't won't catch the regression.

---

## 4. Retrieval

Retrieval never touches the corpus. It runs over the **belief set** — the claims Half holds about this person — which is bounded by how much is true about one life rather than by how much they have written. Ten thousand emails produce perhaps forty durable beliefs. This is why retrieval quality does not decay as the source pile grows.

The hot path is **SQLite FTS5 with `bm25()`**, verified present in the standard library. No vector service, no reranker required, no GPU. That is not an optimisation — it is what lets the same code run on a self-hoster's cheap box, which is what the mission requires.

Focus comes from weighting, never partitioning. Each message is scored against existing strands (loops, people, topics); retrieval weight is `strand match × recency × salience`. **Nothing is ever excluded** (AD-24) — Half must never be able to say *"I don't have access to that,"* because a person has no access boundaries inside themselves.

---

## 5. The context builder — the most important component

This is where the product's central claim becomes code.

Every belief and tension carries a **license**: `behave`, `ask`, or `assert`, defaulting to `behave`. The naive implementation retrieves everything, puts it all in the prompt, and adds an instruction to be careful with the sensitive parts. **That version passes every test you would naturally write and fails the only one that matters**, because it relies on the model's restraint for a guarantee the architecture is supposed to provide.

Instead, context is built on **two channels** (AD-18):

- **`assert`-licensed material enters as content.** Facts the model may state.
- **`behave`-licensed material enters as directives.** *"Be gentle if travel comes up."* Transformed, never quoted. The sentence *"his father is ill"* never appears in the context.

The model cannot leak what it was never given. It received only the instruction.

This also resolves a real conflict: filtering `behave` material out entirely would leave Half either blunt or silent — unable to be gentle about the thing it may not name, which is most of what it knows.

**Test it explicitly:** assert that a `behave`-licensed belief's literal text never appears in a constructed context. Cheap test, exact regression.

---

## 6. Delivery governance

Knowing what is true is the easy half. The system also decides *whether to say it*.

- **Trust balance.** Questions cost; delivered favours earn. An unspent balance is a defect, not a virtue — a Half hoarding trust is being cowardly. Track the disagreement rate: no contradiction in ninety days means Half has stopped being a half.
- **The unsaid queue.** Insights above the current license, held with release conditions.
- **The unasked queue.** Clarifying questions, paid for by *stakes* rather than favours, attached lazily to a conversation already touching the topic.
- **Interrupt only on irreversibility.** Break through when waiting *destroys an option*, not when something is merely important.
- **Nagging is arithmetic.** Touching an open loop faster than that loop's own timescale is nagging, by definition.
- **Silence is a return value** (AD-27, AD-32) — a typed outcome carrying its reason, not an error, a timeout, or an absence of code path.
- **One global ceiling** (AD-28) caps every license regardless of individual value. Crisis aftercare sets it to `behave`. It is applied where licenses resolve, so a new surface cannot forget it.

Outbound to anyone other than the main is **never sent by Half** (AD-25). It is produced as a prefilled draft and dispatched by the main's own action. This holds in crisis, where it matters most.

---

## 7. The actor

An actor is **an inbox plus a mutex keyed by `main_id`** — not a process, not a task. One worker holds thousands; a dormant one is a dict entry. Hydration opens SQLite and reads the fold snapshot in single-digit milliseconds, which the model call dwarfs.

Hibernation is eviction from the LRU. Eviction requires a free mutex (AD-33) — an actor mid-turn is never evicted, and the log append closing a turn happens before the mutex releases.

---

## 8. Secrets

**The export boundary and the secret boundary must not overlap** (AD-11).

Per-main OAuth tokens live entirely outside the four layers — not in the log, not in a projection, not in a replay, not in an export. Self-host uses the OS keyring or an env-keyed encrypted file; hosted uses envelope encryption.

Two different problems share one word. CAP-13's first clause is about secrets Half *finds while reading* — those are discarded at ingestion and never written. This is about the secrets Half was *given*. The second was the one about to ship inside the download button.

---

## 9. Crisis

Crisis is not a branch inside the pipeline. **It owns the entrypoint and delegates inward** (AD-10) — the normal pipeline is something crisis calls, with no other caller, enforced by an architecture test.

The inversion matters because a crisis *check* is a function call, and function calls get refactored around at 2am by someone chasing an unrelated bug. Python cannot structurally forbid a direct import; this is the strongest available guarantee, and the spine says so rather than pretending otherwise.

Inside the mode every other rule suspends: trust currency void, queues bypassed, ledger retrieval hard-disabled, licenses ceilinged. Half states plainly that it is a machine, never produces method or plan content, and offers a prefilled draft to a human the main chooses. Implementation follows the crisis-protocol companion **verbatim** — the response language is not to be paraphrased.

---

## 10. The nightly pass

The expensive interpretation happens while the main sleeps, which is what keeps query time cheap.

Scheduling is a **due-time queue, never a global cron** (AD-9). Each main carries `next_pass_at` at their local pre-dawn with jitter; a scheduler drains what is due under bounded concurrency. Timezone spread does not save you when the first hundred users share one timezone.

Passes go to the **Batch API** — no latency requirement, enormous volume, half price. Submitted around 8pm local for a 7am delivery, roughly eleven hours of slack. If a batch misses, Half sends nothing, which is already permitted. *(The margin is reasoned, not measured — see the assumption in the memlog.)*

The pass mints **tensions**: linked pairs of entries that disagree and cannot be resolved, because for a person neither is wrong. A widening tension is drift. A closing one is a loop advancing.

---

## 11. Deployment

**Self-host.** One process, one actor, Telegram long-polling, everything on local disk, the main's own API keys in env. No public URL required. WhatsApp needs a public host and is documented as such (AD-16).

**Hosted.** The same process type with many actors, plus a router and the scheduler, **sharded and pinned** — each node owns a set of mains. Per-main directories make actors sticky; you cannot autoscale them onto arbitrary nodes. Object-storage-as-home was rejected because it converts an atomic `O_APPEND` into a read-modify-write against an eventually-consistent store, reintroducing exactly the transaction layer the design avoids.

Only layer 1 (sources) moves to object storage — big, immutable, read only during ingestion or rebuild.

Backup is **log-segment shipping**: incremental for free, with point-in-time restore falling out of replay. A node lost with unshipped segments loses the tail; `fsync` on append plus frequent shipping shrinks that window without closing it.

**Half knows when it was gone** (AD-15). Pinned shards mean an outage removes a *named group of humans* rather than degrading a percentage of requests, so downtime is recorded in the main's own log and named before anything else on the next contact.

---

## 12. Model access

One `ModelProvider` port, one implementation. Build the second when a self-hoster actually turns up with a non-Anthropic key — a port you don't cross is a day's work later; a speculative multi-provider abstraction is a permanent tax.

**Prompt cache breakpoints are first-class in the interface** (AD-19). The free tier's economics rest on caching the stable prefix — system prompt, constitution, belief fold. A tidy `complete(messages)` abstraction that hides breakpoints would not lose an optimisation; it would delete the free tier.

Tier travels with the main (AD-20): cheap for free conversation and the batched nightly pass, higher for paid conversation.

---

## 13. Observability

**Counts and timings. Never content. Ever.** Self-host defaults to no telemetry at all — off, not opt-out. Metrics compute locally into the main's own SQLite; a hosted operator aggregates numbers.

Three product metrics, because each alone is gameable: **endorsed-at-30-days** (approval), **disagreement rate** (friction), **loop advancement** (behaviour). Endorsement is sampled at roughly 5% and asked in Half's own register — *"did that thing I said about your brother land, or was I off?"* — because asking spends the trust the product runs on, and a census would degrade what it measures.

Three cost variables instrumented from first release: messages per active day, cached input fraction, dormancy curve. The free tier's viability is currently a model, not a measurement.

---

## 14. What we deliberately did not build

Half-to-Half. The first-party app, the wall, strands. Sensors. Family plans. Any compatibility score. A therapist. A global clinician directory. Multi-provider model support. Reranking and embeddings. Automated shard rebalancing.

Each is either a spec non-goal with its arrival seam named, or a second implementation behind a port that already exists.

---

## 15. The five things most likely to go wrong

1. **The context builder gets flattened** into "retrieve everything, add a warning." Passes normal tests, fails the product. Guard: the literal-text test.
2. **Replay stops being pure** because re-deriving is the natural way to write a fold. Guard: a CI fixture that spans a model-tier change.
3. **A second writer appears** — a maintenance script, a migration, a background job — and the atomicity that made the file store cheap silently disappears.
4. **A credential leaks into the log** through a well-meant "let's record what we connected."
5. **Silence gets handled away as an error** by someone who assumes every turn produces a message.
