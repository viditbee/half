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

Stories 1–2 of 12: the store, and the Telegram channel. Half can hold a
conversation and remember it. It cannot yet ingest your mail, retrieve
meaningfully, govern what it says, or handle a crisis — the responder is a
deterministic stub that later stories replace.

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

## Architecture

Thirty-three numbered decisions govern this code; module docstrings cite them
by number (AD-1, AD-30, and so on). The spine lives outside this repository in
the planning artifacts, alongside the specification and the constitution.

## Licence

MIT. Portions study or adapt work from
[hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT, © 2025 Nous
Research).
