# How Half is built

*The architecture page for people who might build on it, fork it, or check whether the claims hold.*

Half is a second self that lives in your messaging app. It reads what your life leaves behind, asks about what no inbox can contain, and holds the gap between the two.

This page is about the machine. If you want the idea, read the README. If you want to verify a claim, every section below names the file or the test that settles it.

---

## The claim we most want checked

> **We cannot read your data, and you can leave with all of it.**

That sentence is only worth anything if the architecture makes it structurally true rather than promising it. Three decisions do the work:

**Your memory is a text file.** The source of truth for everything Half believes about you is an append-only JSONL log in a directory on disk. Not a database with an export button — the log *is* the thing. Open it in any editor. `grep` it. Put it in git.

**Everything else is disposable.** The SQLite database and the markdown pages are folds over that log. Delete them, replay, and you get byte-identical state back. That's not a design note, it's a test that runs on every commit. If it ever fails, we have quietly started keeping something we can't hand you.

**Telemetry carries counts, never content.** Self-hosted installs default to no telemetry at all — off, not opt-out. When the code is public, "we can't see your data" stops being a promise and becomes something you can check.

---

## The directory

```
~/.half/<main_id>/
  sources/              content-addressed, immutable, never edited
  beliefs/2026-08.jsonl append-only event log — the only source of truth
  loops/*.md            what you're trying to do, as markdown + YAML
  people/*.md           who matters, as markdown + YAML
  half.db               SQLite: materialized state + FTS5 index (disposable)
```

Your credentials are **not in here.** OAuth tokens live in a separate store that is never part of an export, a replay, or a backup of this tree. We nearly got that wrong — the log is exportable, so a token inside it would have been handed to you in a zip file and resurrected on every replay.

## The file format is the standard, not the code

Anyone can write a Half. Only one format holds a life.

We think the durable thing here is the log format and the four-layer layout, not this implementation. If you write a better Half in Rust and it reads this directory, that is a success, not competition. The op vocabulary is enumerated in one module and versioned, and an unknown op on replay is a hard error rather than a silently skipped line — precisely so that another implementation can tell whether it actually understands your file.

---

## Retrieval runs on your laptop

No vector database. No embedding service. No GPU. No API key required for search.

Retrieval is **SQLite FTS5 with `bm25()`**, which ships in Python's standard library. You can verify that in one line:

```python
import sqlite3
sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
```

That isn't frugality for its own sake. Half is meant for people who don't have a Notion system and won't run a Postgres cluster — if the search layer needs infrastructure, the whole premise is a lie. A reranker and embeddings are optional, and results must be correct without them.

**Why it stays fast as your archive grows:** retrieval never touches your corpus. It runs over the *beliefs* — the claims Half holds about you — which are bounded by how much is true about one person, not by how much you've written. Ten thousand emails produce perhaps forty durable beliefs. You ingest a corpus and retrieve a self.

---

## The part we care most about getting right

Half's difficulty isn't remembering. It's **knowing something true and deciding not to say it.**

Every belief carries a license: `behave`, `ask`, or `assert`, defaulting to the weakest. Most of what Half knows never leaves `behave` — it shapes tone, delays a nudge, drops a suggestion, and is never spoken.

The tempting implementation is to retrieve everything, put it in the prompt, and instruct the model to be careful. **That version passes every obvious test and fails the only one that matters**, because it makes a guarantee depend on a model's discretion.

So context is built on two channels:

- **`assert` material enters as content** — facts the model may state.
- **`behave` material enters as directives** — *"be gentle if travel comes up."* Transformed, never quoted.

The sentence *"his father is ill"* never enters the context. The model cannot leak what it was never given.

There is a test that asserts a `behave`-licensed belief's literal text never appears in a constructed context. If you're reviewing a PR here, that's the test to look for.

---

## One writer, always

Each person's directory has exactly one owner — an inbox and a mutex. That single decision is why Half doesn't need a transaction layer: under one writer, an append is atomic and free.

If you fork this and add a second writer — a migration script, a background job, a helpful cron — you have to build the journal, the precondition hashes, and the rollback machinery that this design deliberately avoids. It won't announce itself. It'll just start losing writes under load.

## Replay is pure

The log records the **outcome** of anything non-deterministic — a model call, a clock read, a network fetch — never a promise to redo it. Replay never calls a model, never touches the network, never reads the clock.

This is what makes the byte-identical guarantee real. Without it, someone who changed model tier would replay to different state, and the export you were handed would no longer describe the Half you had.

---

## Deployment

**Self-hosting is the primary artifact, not a port.** The hosted service runs the same program many times.

One process, one person, Telegram long-polling, everything on local disk, your own API keys in env. No public URL needed.

**WhatsApp is the honest exception.** The Cloud API requires a public webhook — there's no polling mode — so self-hosted WhatsApp needs a domain or a tunnel. Telegram doesn't. We'd rather say that than pretend the install is ninety seconds when it isn't.

---

## What we borrowed

Half doesn't depend on an agent runtime, but it learned from several. Where we lifted real code we say so and keep the notice.

| From | What |
| --- | --- |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT, © 2025 Nous Research) | The WhatsApp 24-hour window and template fallback; the platform-adapter shape; the typing-heartbeat pattern |
| [claude-obsidian](https://github.com/) | The source/claim ledger split, independence-checked corroboration, and *"preserve contradictory evidence — do not silently select a winner"* |
| [gbrain](https://github.com/garrytan/gbrain) | Markdown-in-git as truth with derived indexes; keeping embedding and chunking **out** of the storage engine |
| [graphiti](https://github.com/getzep/graphiti) | Four timestamps rather than two — separating *we were wrong* from *you changed* |
| [HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) | Filtering candidates before expensive traversal |

We read honcho, khoj, and letta closely too. The reason Half isn't built on any of them is in the next section.

---

## Why not build on an existing agent memory system

They are good, and they solve a different problem.

Every one of them builds **memory for agents** — retrieval quality, nightly consolidation, temporal graphs, peer representations. Half is **memory about a person, for that person**, and two things follow that none of them need:

**A theory of the recipient.** They all optimise *what to retrieve*. None models *whether the human can hear it right now*. There is no unsaid queue, no earned right to speak, no silence-as-a-feature anywhere in the field.

**Person-epistemics.** Their machinery treats a contradiction as a defect to resolve with better sourcing. For a person, a contradiction often means **neither claim is wrong** — you said you'd start running in March and you didn't, both records are permanently true, and the tension between them *is* the finding. There is no better source. There is no winner to select.

Concretely, hosting Half inside an agent runtime fails on control flow: those interfaces assume memory *decorates* a turn that is going to happen. Half's whole thesis is deciding whether the turn happens at all.

---

## If you want to contribute

The invariants live in `ARCHITECTURE-SPINE.md` — 33 numbered decisions, each with what it binds, the divergence it prevents, and the rule. A PR that contradicts one isn't wrong by default, but it needs to argue with the AD by number.

Two tests are load-bearing and must never be weakened:

- **The replay test** — delete the database, replay the log, assert byte-identical state. The fixture deliberately spans a model-tier change.
- **The context test** — assert that a `behave`-licensed belief's literal text never appears in a constructed context.

If you only read one thing before your first PR, read the constitution. It's the list of things Half must never say, and most of the architecture exists to enforce it.
