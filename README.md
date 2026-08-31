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

Story 1 of 12: the store. The messaging channel, ingestion, retrieval ranking,
delivery governance and the crisis protocol are not built yet.

## Running it

Runtime is the Python standard library — no dependencies. `pytest` is the only
development dependency.

```bash
uv sync --extra dev
uv run --extra dev pytest -q
```

## Using the store

```python
from half.store.store import Store
from half.store.ops import Op

with Store("~/.half/me") as store:
    store.record(Op.ASSERT, "b_1", "2026-08-14T09:12Z",
                 subject="self", claim="replies to mother within three minutes",
                 ledger="revealed", license="behave", independent=2)

    store.search("mother")          # BM25-ranked
    store.state().beliefs           # the current derived view
    store.rebuild()                 # re-fold from the log at any time
```

Timestamps are always supplied by the caller. Nothing under `store` reads a
clock, so folding a log is a pure function of that log.

## The two tests that carry the design

`tests/test_replay.py` deletes the SQLite file, replays the log, and asserts
byte-identical state — across a fixture that deliberately spans a model-tier
change.

`tests/test_purity.py` statically forbids the fold from reaching a clock, the
network, a model, or ambient process state. A behavioural test cannot catch a
fold that re-derives instead of replaying until the tier actually changes.

## Architecture

Thirty-three numbered decisions govern this code; module docstrings cite them
by number (AD-1, AD-30, and so on). The spine lives outside this repository in
the planning artifacts, alongside the specification and the constitution.

## Licence

MIT. Portions study or adapt work from
[hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT, © 2025 Nous
Research); see the extraction manifest in the planning artifacts.
