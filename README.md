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

Stories 1–5a of 12: the store, the Telegram channel, mail ingestion, retrieval,
the two-channel context, and the license ladder. Half can hold a conversation,
remember it, derive claims from your mail without keeping the mail, rank what
it knows against what you just said, and decide which of it may be *said* as
opposed to merely acted on.

Every belief carries a license, and licenses are enforced when the context is
**built** rather than by filtering what comes out. A claim licensed `assert`
may be quoted to you. A claim licensed `behave` reaches the context only as a
topic — its wording appears nowhere, in any channel, and that is asserted
byte-wise over the rendered context and over the reply. Anything missing,
unknown or malformed is treated as `behave`.

`assert` is not a field anything can set. It requires two independent things:
a citation into Half's own evidence, *and* your already knowing Half holds the
belief — being right is not sufficient, because the danger of assertion is
being unexpected rather than being wrong. No amount of corroboration promotes a
belief on its own; promotion is an event involving you, recorded as an append.
An unsupported claim may be *asked*, never asserted. Quarantine pins a belief
at `behave` permanently, and the fold carries the pin forward so no later
record can drop it. Above all of it sits one ceiling per person, applied where
licenses are resolved rather than where messages are composed, so a new surface
cannot bypass it by forgetting to check; it lives in the log, so it survives
eviction and restart, and it can cap but never promote. Both halves are gated
statically: nothing outside `half/governance/` resolves a license without the
ceiling, and nothing outside it writes one.

It still cannot decide what is *worth* saying: the responder is a deterministic
stub because no model is called anywhere yet. The trust balance and the unsaid
and unasked queues are story 5b, and crisis handling — which is what lowers the
ceiling in production — is story 6.

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
| `half/context/` | The license split: content, directives, question candidates |
| `half/governance/` | The license ladder: rung rules, quarantine, the ceiling |
| `half/text.py` | One script-neutral tokenizer, shared by index and matcher |
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
another's retrieval, and checks byte-wise that no `behave` claim reaches the
wire.

`test_scripts.py` is deliberately **symmetric**: every script that gets a recall
case gets a precision case beside it, in one store holding every script at once,
so a query has every other script's beliefs to wrongly match. Its first version
was not, and the asymmetry hid a live defect — the recall tests passed on noise
from a scheme that matched almost everything. It also pins each script class and
each growth ceiling through what retrieval returns, using literal numbers: a
test written in terms of the constant it guards cannot see that constant being
wrong.

`test_ladder.py` is the AD-28 gate, and it is symmetric on purpose. Read-side
enforcement alone would leave `assert` a field anyone can set at the price of
three fields instead of one, so one static gate proves no caller resolves a
license without the ceiling — resolving every import spelling through the
package re-exports, because a gate whose reach depends on which of two
equivalent import lines you wrote is not a gate — and a second proves no module
outside the ladder writes a license field at all. Both are checked against
synthetic bypasses of their own so neither can pass having seen nothing.

`test_context.py` is the AD-18 gate. It scans the rendered context and the
reply for any *fragment* of a withheld claim — adjacent word pairs,
concatenated, so a language that does not space its words is covered by the
same rule — and it enumerates the fields of every channel item so that a field
added later cannot carry text past a scan that cannot see it.

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

Retrieval works in every script, not only the ones written with spaces, and it
is one mechanism rather than two: **every word is matched as a phrase**. A
combining mark stays attached to the letter it modifies, so a Devanagari word is
one word rather than three consonants, and each word goes to FTS5 quoted, with
the OR kept *between* words. A script with no word spaces — Japanese, Chinese,
Thai, Lao, Khmer, Korean — has its runs cut into grapheme clusters on both sides
of the index, so `転職` is the phrase 転-then-職: findable inside a sentence that
never spaced it, and *not* matching a belief about `退職金` that merely shares a
character. Adjacency is what carries word identity when there are no spaces to
carry it. There is no language detection anywhere and no segmentation library;
the only distinction Half draws is a script class, read off the Unicode
character database rather than a table of codepoint ranges.

## Architecture

Thirty-three numbered decisions govern this code; module docstrings cite them
by number (AD-1, AD-30, and so on). The spine lives outside this repository in
the planning artifacts, alongside the specification and the constitution.

## Licence

MIT. Portions study or adapt work from
[hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT, © 2025 Nous
Research).
