---
title: 'Story 20 — The order that was promised'
type: 'fix'
created: '2026-09-05'
status: 'in-progress'
baseline_commit: 'e218117'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `MailSource.fetch` promises *"messages newer than `since`, oldest
first"*. Its only implementation does not sort, does not buffer, and yields in
whatever order Gmail returns — which is **newest first**. `GmailSource`'s own
class docstring repeats the false claim.

That would be a documentation defect on its own. It is not, because two other
things are true: the pipeline's cursor is `max()` over every timestamp seen, and
`BUDGET_SECONDS` cuts the pull when CAP-2's ninety seconds run out. Together
those make a **permanent loss of history**. Measured with the real `Pipeline`,
a twenty-message mailbox whose pull is cut after five, over six runs:

| Order | Ever ingested | Final cursor |
|---|---|---|
| oldest-first | **20 of 20** | 2026-08-20 |
| newest-first | **5 of 20** | 2026-08-20 |

Both runs finish at the same cursor. Newest-first has lost fifteen messages
that `after:` will exclude for ever. Half's whole corroboration story rests on
CAP-3 finding two independent supports, and it is reading five newest emails.

**What is *not* the problem, measured before assuming it.** The promise names
two reasons and neither is the failure. A cursor advancing monotonically does
not need the order, because `max()` does not care. A failure part-way leaving
its prefix captured does not need the order either, because receipts are stored
per message and deduplicated by digest, so a re-run re-captures nothing. The
order is load-bearing for exactly one thing: **a walk that stops early**.

**Approach:** Keep the promise and make it true, by walking bounded windows
forward instead of the whole mailbox at once. Gmail's query takes `before:` as
well as `after:`, and the transport already accepts an arbitrary query string,
so a window needs no change to the Protocol. Each window is drained fully, and
**the cursor advances only to the end of a window that was drained** — so a cut
mid-window costs nothing but a repeat, and never history.

The second half is the part that makes the first half safe: **the ninety-second
demonstration must not move the history cursor.** A recent read for CAP-2 and a
forward walk for CAP-3 are different questions, and sharing one watermark
between them is what turned a bounded read into permanent loss.

## Boundaries & Constraints

**Always:**
- **The port's promise becomes true rather than being deleted.** `fetch` yields
  oldest first, and the implementation is what changes.
- **Bounded before the first yield.** No reading a whole mailbox into memory to
  sort it: a window is bounded by time, and the walk streams.
- **The cursor advances only over drained ground.** A window cut part-way
  leaves the cursor where it was. Re-fetching a window is free — the digest
  already deduplicates — and losing history is not.
- **A read that does not drain must not advance the shared watermark.** Any
  bounded recent read (CAP-2's demonstration) records its own position, never
  the history cursor.
- **Story 3's failure vocabulary is unchanged** — raised as a domain error,
  pages already captured stay valid, resumable, never partial-and-silent.
- **No provider text crosses the boundary** (AD-22); no body persisted (AD-13).
- **The suite stays offline.** The existing socket guard covers this unchanged.

**Ask First:**
- Any change to `Message`, `Receipt`, or the `MailSource` Protocol's signature.
- Any durable state beyond the cursor the pipeline already returns.
- Any change to `BUDGET_SECONDS` or to what CAP-2 shows in ninety seconds.

**Never:**
- Do not "fix" this by deleting the ordering promise and calling newest-first
  the contract — measured, that is the fifteen-of-twenty loss above.
- Do not buffer an unbounded number of messages to achieve the order.
- No second store, no per-message durable state, no schema change.

## I/O & Edge-Case Matrix

| Scenario | State | Expected | Why |
|---|---|---|---|
| A full walk | Small mailbox | Every message, oldest first | The promise |
| A walk cut mid-window | Budget spent | Cursor unmoved; nothing lost | The defect |
| A walk cut on a window boundary | Budget spent | Cursor at the drained window's end | Progress is kept |
| Resume | A cursor from a cut run | Continues from there, no gap | Monotonic and complete |
| An empty window | No mail that week | Skipped without stalling | Sparse mailboxes must terminate |
| A very dense window | More than one page | Paged within the window | `MAX_PAGES` still holds |
| The demonstration | Ninety seconds | Recent mail; history cursor unmoved | CAP-2 without the loss |
| A malformed cursor | Not ISO-8601 | Story 3's error, unchanged | No silent widening |
| A message with no date | `internalDate` absent | Skipped, as today | Cursor must not jump to now |
| A provider failure mid-window | 5xx | Story 3's vocabulary; cursor unmoved | Resumable |
| Clock skew | A message dated in the future | Cannot strand the cursor beyond real mail | A future stamp must not end the walk |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-2,
CAP-3, AD-13, AD-22 govern. Anchors verified at `e218117`.

**The measurement that defines the defect**, reproducible: the real `Pipeline`
with a fake source yielding in a chosen order, cut after five messages, six
runs — oldest-first ingests 20 of 20, newest-first 5 of 20, both ending at the
same cursor.

**Existing, reused:** `half/ingest/port.py:44-53` (`MailSource.fetch`, the
promise and its two stated reasons), `half/ingest/gmail.py:47` (the false class
docstring), `:54-75` (`fetch`, which never sorts), `:136` (`_query_for`, which
builds `after:` only and validates the cursor), `:30` (`MAX_PAGES = 10_000`),
`half/ingest/pipeline.py:118-121` (`newest = max(...)` — the order-independent
cursor) and `:159-162` (where it is returned), `half/onboard/flow.py:107-125`
(`BUDGET_SECONDS` and the reserve, the deadline that cuts the pull).

**Note the transport needs no change:** `list_messages(*, query, page_token)`
takes an arbitrary query, so `before:` is already expressible.

## Tasks & Acceptance

**Execution:**
- [x] a bounded forward window walk in `GmailSource.fetch` -- the promise made true
- [x] `_query_for` extended to bound a window at both ends
- [x] the cursor advances only over a drained window -- `half/ingest/pipeline.py`
- [x] the demonstration's bounded read stops moving the history cursor -- CAP-2
- [x] `half/ingest/gmail.py:47`'s docstring made true
- [x] every matrix row tested, offline

**Acceptance Criteria:**
- Given a mailbox and a pull cut part-way, when the run repeats until it stops
  making progress, then every message is ingested exactly once — the twenty-of-
  twenty above, asserted as a test with the newest-first behaviour as its
  recorded counterexample.
- Given a walk cut mid-window, when it resumes, then no message is skipped and
  the cursor never moved past undrained ground.
- Given a sparse mailbox with empty windows, when it is walked, then the walk
  terminates without stalling and without unbounded requests.
- Given the ninety-second demonstration, when it runs, then the history cursor
  is unchanged by it.
- Given the whole suite, when it runs, then no socket is opened.

## Design Notes

**Why the window and not a sort.** Sorting means reading every page before the
first yield, which is unbounded work on a real mailbox and cannot live inside a
ninety-second budget. A time window is bounded by construction and streams.

**The window size is a trade to be measured, not guessed.** Too wide and a
window will not drain inside the budget, so the cursor never advances; too
narrow and a sparse mailbox spends its requests on empty weeks. Pick it with a
measurement over realistic densities and record the number.

**The clock-skew row is not hypothetical.** A message stamped in the future is
exactly what a `max()` cursor cannot survive, and it is why that row is in the
matrix rather than in deferred work.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- all pass
- `cd half && uv run --extra dev pytest tests/test_ingest.py tests/test_gmail_transport.py -q` -- story 3's contract unmoved
- `cd half && uv run --extra dev pytest tests/test_onboard.py -q` -- CAP-2 unmoved
- `cd half && uv run --extra dev python tools/mailbox_sim.py` -- 0 of 5 miscounted
- `cd half && git status --porcelain` -- clean after commit

## Spec Change Log

**2026-09-05 — implemented.** The walk, the split watermark, the recent read
and eleven matrix cases are in; the whole suite passes under the socket guard.
Nothing in the frozen block was renegotiated. Three decisions the Intent left
open, with what decided them:

- **The window is seven days**, measured rather than guessed as the Design
  Notes require. `tools/window_sim.py` walks five years of synthetic mailbox at
  four densities and reports requests per message ingested against the size of
  the window that has to drain: a month is marginally cheaper per message and
  asks a firehose to drain 6,543 messages before the cursor may move once; a
  single day drains in a handful and charges a dormant mailbox 6.05 requests
  for every message it holds. The table is recorded beside the constant.
- **Where a walk stops is not where its cursor stops.** The walk goes to the
  newest stamp there is; the cursor is clamped to the third-newest, so one
  message dated in 2099 widens nothing and strands nothing. Collapsing the two
  — which the first implementation did — stalls a mailbox whose three newest
  messages are years apart: the walk stops short of the newest, the cursor
  stops in the same place, and the next run repeats both, for ever. That is
  the clock-skew row's defence rebuilding the clock-skew row's defect, and it
  is now a case.
- **An empty window is jumped, not stepped past.** The Design Notes accept a
  sparse mailbox spending requests on empty weeks; a halving search over the
  same `before:` bound crosses a gap of any width for about fifteen, and the
  same search is what finds where a first walk begins. Stepping up from the
  floor would have cost a first pull thousands of requests before reading
  anything, which under a deadline is a first pull that reads nothing at all.

Two costs, accepted and recorded rather than hidden:

- **A window that will not drain inside a caller's bound never advances the
  cursor.** That is the frozen rule working — a repeat costs an `already_seen`
  and a loss costs history — and the Design Notes name it. Nothing in the
  shipped tree bounds the history walk; the only bounded pull is the
  demonstration, which moves no cursor at all.
- **The cursor lags the newest mail by two messages**, because the horizon is
  corroborated rather than taken from one stamp. Each run re-reads those two
  and the digest deduplicates them.

KEEP, and do not re-derive: the two watermarks (`Ingested.cursor` over drained
ground, `Ingested.read_through` for a bounded read's own position); the
watermark read off the source rather than declared on the Protocol;
`GmailRecent` publishing `None` as a class attribute; the horizon taken from
three stamps; the floor at the Unix epoch rather than Gmail's launch year, so
imported mail older than the service is still walked; the watermark set
*before* the last message of a window rather than after it, because a walk cut
on a boundary is never resumed.
