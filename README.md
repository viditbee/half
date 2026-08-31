# Half

A second self that lives in your messaging app.

The source of truth for everything Half believes about you is an append-only
JSONL log in a directory on disk. Not a database with an export button — the
log *is* the thing. Everything else is folded from it and can be deleted.

```
~/.half/<main_id>/
  beliefs/YYYY-MM.jsonl   append-only — the only source of truth
  half.db                 SQLite: materialized fold + FTS5 index (disposable)
```

Your credentials are never in this tree.

## Status

Stories 1–4 of 12: the store, the Telegram channel, mail ingestion, and
retrieval. Half can hold a conversation, remember it, derive claims from your
mail without keeping the mail, and rank what it knows against what you just
said.

It cannot yet decide what is worth saying, and by design it says none of what
it retrieves: licenses are enforced when context is *built* (story 5), so until
that lands the responder is a deterministic stub and no belief text is allowed
into a reply. Crisis handling (story 6) is still unimplemented.

**Not ready for real use.** In particular the crisis protocol (story 6) is
unimplemented, and that is a launch gate.

## Running it

```bash
uv sync --extra dev

export TELEGRAM_BOT_TOKEN="<from @BotFather>"
export HALF_MAINS="<your-telegram-chat-id>:<a-name-for-you>"
export HALF_ROOT="$HOME/.half"        # optional, this is the default

uv run half                            # or: uv run python -m half
```

Telegram uses long polling, so **no public URL is needed** — it works from a
laptop behind NAT. WhatsApp needs a public webhook and lands in a later story.

Send the bot a message first: a Telegram bot can never open a conversation, so
Half literally cannot speak until you do.

## Tests

```bash
uv run --extra dev pytest -q
```

The suite is hermetic — it makes no network calls and needs no bot token.

## Layout

| Module | What it holds |
| --- | --- |
| `half/store/` | The four layers: log, pure fold, SQLite + FTS5, export |
| `half/ingest/` | Connectors, secret scrubbing, independence, admission gates |
| `half/retrieval/` | Strand weighting, contextual prefix, salience, bm25 fusion |
| `half/text.py` | One unicode-aware tokenizer, shared by index and matcher |
| `half/channel/` | The `Channel` port, reachability, the Telegram adapter |
| `half/actor/` | One actor per main — an inbox and a mutex — and the wiring |
| `half/crisis/` | Owns the inbound entrypoint; the assessment lands in story 6 |
| `half/config.py` | Who counts as a main, from the environment |
| `half/__main__.py` | The composition root |

## The tests that carry the design

`test_replay.py` deletes the SQLite file, replays the log, and asserts
byte-identical state — across a fixture that spans a model-tier change.

`test_purity.py` statically forbids the fold from reaching a clock, the
network, a model, or ambient process state.

`test_entrypoint.py` asserts the pipeline has exactly one caller, and that it
is the crisis gate.

`test_dependencies.py` enforces that the runtime imports only the standard
library and pinned dependencies.

`test_retrieval.py` varies one ranking factor at a time with the score
tie-break deliberately pointing the other way, so a factor quietly replaced by
a constant fails rather than passing by coincidence. It also rebuilds the
*previous* release's database schema and asserts the upgrade replays.

`test_strands.py` watches the live turn rank through a recording reranker
rather than grepping for a call, asserts one main's crisis cannot disable
another's retrieval, and checks byte-wise that no retrieved claim reaches the
wire.

## Retrieval, in one paragraph

BM25 over FTS5 — no vector service, no embeddings, nothing to self-host beyond
SQLite. Each belief is indexed twice: its claim, and a short *contextual
prefix* built from its own fields, so a query naming a loop finds a belief
whose words never mention it. The bm25 score is then fused with strand match
(what this conversation is about), recency, and salience (independence, last
corroboration, loop state). Every multiplier has a strictly positive floor, so
weighting can reorder the belief set but can never remove anything from it —
Half must never be able to say *"I don't have access to that."* A reranker is
optional, has exactly one method, and when it is missing or misbehaves the
result carries an explicit no-op annotation rather than degrading silently.

## Architecture

Thirty-three numbered decisions govern this code; module docstrings cite them
by number (AD-1, AD-30, and so on). The spine lives outside this repository in
the planning artifacts, alongside the specification and the constitution.

## Licence

MIT. Portions study or adapt work from
[hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT, © 2025 Nous
Research).
