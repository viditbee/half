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

The set of record kinds the log may hold is closed and versioned: adding one is
a deliberate change with a schema bump beside it, so an older build that meets
a record it cannot read refuses to fold rather than skipping the line. It is at
**v4** — `ceiling` joined at story 5a, `crisis` at 6a, and `aftercare` at 6c,
which is what carries whether you were asked about the mirror and what you
answered. A build that could not see that record would read somebody who
declined as somebody who was never asked.

## Status

Stories 1–5a, 6a–6c, 8 and 9a of 12: the store, the Telegram channel, mail
ingestion, retrieval, the two-channel context, the license ladder, the whole of
the crisis mode — the switch and the moment, the warm handoff, and coming back —
the open-loop ledger, the due-time scheduler, and the nightly pass it runs: the
tension ledger, re-evaluated against what the log holds.
Half can hold a conversation, remember it, derive claims from your mail without
keeping the mail, rank what it knows against what you just said, decide which
of it may be *said* as opposed to merely acted on, step out of all of it when
you are in danger, hand you the hardest message you will ever send for you to
send yourself, hold the safety plan you were given, and come back afterwards
slowly and only with your permission.

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
record can drop it. Above all of it sits one ceiling per person — one cap over
every belief and tension that person has, not one shared by the worker — applied where
licenses are resolved rather than where messages are composed, so a new surface
cannot bypass it by forgetting to check; it lives in the log, so it survives
eviction and restart, and it can cap but never promote. Both halves are gated
statically: nothing outside `half/governance/` resolves a license without the
ceiling, and nothing outside it writes one.

It still cannot decide what is *worth* saying: the responder is a deterministic
stub, and **no model is called anywhere.** The port that one day will be is
built — `half/model/`, story 9b — and it ships with no production caller on
purpose. Its five consumers (claim derivation, the crisis classifier,
consolidation, tension minting, and the reply itself) are each their own story
with their own risk, and wiring one of them in alongside the port would put the
port's design and that consumer's risk into a single review. The trust balance
and the unsaid and unasked queues are story 5b. The nightly pass the scheduler
runs today mints this main's tensions — new or changed entries against the loop
set and against beliefs sharing a subject, through a cheap relevance filter,
inside a per-main couple ceiling and judgement budget (story 9d) — then
re-evaluates them against the log and an injected `now`, appends the
transitions that follow, and sends nothing to anybody. The disagreement
judgement itself is a port with no implementation and none wired into the
composition root, so this build mints nothing until story 9e supplies one; the
morning surface is story 10.

**Not ready for real use.** The crisis subsystem has not been reviewed by a
qualified clinician, and that review is a launch gate rather than a follow-up.
A green test suite is not clinical review.

## Crisis

**Asking and entering are two different things, and they cost differently.**
Half asks a gentle direct question on a hunch — a hedged sentence, algospeak, a
misspelling, letters spaced out, a preparatory act, a farewell. That costs one
question you can wave away: no mode, no cap, nothing written, and if you say no
it is over. Half only *enters* the mode on the safe word, on an explicit
disclosure, on an affirmative answer to that question, or when you are reaching
a crisis line — because entering is durable and suspends the rest of the
product. A build that collapses the two governs you for a month because you
mentioned a film.

The safe word is **`lantern hour`**. Typing it anywhere in any message — mid
sentence, in any case, pluralised, mistyped by one letter, run together as one
word, or with its letters spaced apart — enters the mode immediately. Nothing
is scored, no threshold has to be cleared, and nothing can outvote it. It never
changes.

The typo tolerance has one known cost, documented here rather than left to be
discovered: **`lantern our`** also matches, because *our* is one letter from
*hour* and the two words have to be adjacent. If Half answers you in crisis
mode after a sentence about lanterns, that is why — say so and it can be
reversed. Tolerating the typo is worth the collision: the alternative is a
safe word that fails on a shaking hand.

A line break inside a sentence does not hide it. The index deliberately
*removes* invisible characters so that a joiner inside a word does not split
it, and a newline is an invisible by that rule — so a disclosure typed across
two lines used to tokenize as one run-together word and match nothing. The
crisis tokenizer turns a break into a space before it looks. Found reviewing
story 6c, in code story 6a shipped.

Crisis mode is a pre-filter ahead of the normal pipeline rather than a branch
inside it (AD-10), so no route into an ordinary turn can skip it. Entering
records the whole suspension at once, in your own log and under your actor's
lock: ledger retrieval is hard-disabled — a disabled retriever *raises* rather
than returning an empty set somebody could read as "nothing here" — your
license ceiling drops to `behave`, and the mode itself is recorded. All three
come back together when your actor is rehydrated, so an eviction under memory
pressure or a process restart cannot end the mode or quietly switch retrieval
back on. Nothing in Half exits the mode: the question of who decides a crisis
is over is a clinical one, and a timeout is not an answer to it. Aftercare
below raises the *ceiling* back, a rung at a time and only with your word; it
does not close the mode either, so in this build a restored ceiling has no
visible effect until somebody qualified decides what mode exit is.

Nothing may cost you a reply. Every durable step is best-effort and the reply
is not: a corrupt log, a full disk or a refactored signature is caught, logged
without content, and the templated reply is still sent.

**Replies are templated, never generated, and that is a safety decision.** Every
documented catastrophic failure of a chatbot in this situation is a *generation*
failure — a bridge named, a dose given, a method described. A template set
cannot produce content it does not contain, so "no method or means content, in
any phrasing" stops being a behaviour and becomes a property: the assembly is
not given your text at all, so no phrasing is a lever on the output. Every word
anyone can receive in crisis lives in one reviewable file with no locale, no
phone number and no service name in it, and that file is digested by a test, so
rewording it after a clinician has read it fails the build by name.

Half states plainly that it is software on every turn inside the mode. That is
the one deliberate break of character in the product, and it is built on
purpose — and it is deliberately *absent* from the question, because announcing
it on a hunch is its own kind of harm. A risk signal about *someone else* never
runs the protocol on them: it surfaces something you can share, records nothing
about that person, and stops. Nothing on this path reads a plan or a payment
state, so free and lapsed people get identical behaviour.

Two rows of the companion's tier table are **not implemented**, and are
recorded as such rather than faked: a third-party mention of you and a sudden
change in your pattern both raise vigilance in the design, and neither has a
producer here — a friend cannot message Half, and pattern change needs timing a
single-message assessor cannot see.

**Undoing a false entry** is an operator action, deliberate and recorded:

```python
asyncio.run(registry.reverse_crisis(
    "vidit", t="2026-09-01T22:14:00Z",
    because="entered on a film quote; confirmed with the main"))
```

That reverses all three parts of the suspension together and demands a reason
that outlives whoever typed it. It is not a mode-exit policy and must never be
automated.

## Coming back

Entering the mode drops your license ceiling to `behave` and nothing used to
raise it again, so a single disclosure governed you silently for ever. That is
what aftercare undoes, and it undoes it slowly and with your permission.

**Thirty days is a floor, not a timer.** Nothing restores before it, by any
path, and reaching it grants the *first* step only — `behave` back to `ask`,
which is a return to ordinary conversation. That step is silent: announcing
that Half may ask questions again would be a status update about Half in a
conversation that is not about Half.

**The mirror comes back only when you say so.** Two weeks after the first step,
Half asks — *"would you like me to start saying what I notice about you
again?"* — and the cap holds until you answer. Elapsed time is never the last
condition. Silence is not consent, and neither is *maybe*: the answer has to be
a clear yes, substantially the whole message, with nothing in it pulling the
other way. *"Yes, but please don't"* is a no. A question you do not answer
expires after a week rather than staying open for a later *yes* to land in.

**Declining is not permanent, and asking is not perpetual.** Say no and the cap
stays where it is; Half asks again a fortnight later. Say *"no, and please stop
asking"* and it stops for good — the cap still holds, the asking ends.

Aftercare is worked out on **your** next message, and nothing under
`half/crisis/` may read a clock at all — a rule the build fails on. The restore
is a question about somebody who is already in the conversation. Caring
Contacts — brief periodic messages with no demand attached — are the opposite
kind of thing and are not built.

**A second crisis restarts the clock**, from the later disclosure and never the
first. And once the mirror is back, aftercare is over: it does not go on owning
your ceiling for the rest of your life.

Every number here — the thirty-day floor, the fortnight before the mirror is
offered, the fortnight between askings, the week a question stays answerable —
is on the clinical reviewer's list along with the wording.

### The safety plan

Half **holds** a safety plan and must never write one. Writing one is clinical
work; holding one is the entire point, because a safety plan in a drawer is
useless at three in the morning.

To give Half yours, send it in one message that starts with a line saying so:

```
here is my safety plan
When I start pacing after two in the morning, that is the sign.
Put the phone in the other room.
Ring Asha. She knows.
Dr Rao — Tuesdays, and the practice takes messages.
```

Everything after the first line is stored exactly as you sent it. Half decides
where the document begins because you said so, and nothing else about it: no
heading is supplied, no step is numbered, no missing section is noticed or
filled in. Ask for it back with **"my safety plan"**, **"the plan we made"** or
**"my crisis plan"**, in or out of crisis mode, and you get it word for word
with two sentences around it. If Half is holding none, it says so plainly and
offers nothing invented.

Exactly one expression in the codebase can put a value into that field, it is a
copy of its only argument, and a test asserts that every call site hands it
something it was *given* rather than something built on the spot — because a
guard that only forbids three ways of writing the field lets Half compose a
plan out of its own memory and hand it to the blessed writer.

The warm handoff — a prefilled draft to a person you choose — is story 6b.

## The scheduler

Half runs one thing on a schedule, and it is not a cron. Each person carries
their own `next_pass_at`, at **their** local pre-dawn — 03:00 plus up to two
hours of jitter derived from their own id, so a thousand people in one timezone
do not share an instant, and a restart does not move anybody's time. A tick
every minute drains whatever is due, holding a file lock so a second worker
cannot drain the same queue, under an explicit concurrency bound and a per-person
timeout, with each person's work isolated from every other's.

**A window that was missed sends nothing.** No catch-up, no backlog, no storm
after an outage. A process that was down for a week comes back, finds everybody
overdue, computes every next due time forward and runs nothing at all — because
for a product whose output is unprompted messages to a person, catching up means
a queue of yesterday's thoughts arriving at once. That holds on *every* path
that can run work, not only the one a test happens to call.

**A pass whose "already ran" marker cannot be written does not run.** The
durable advance comes first, and if it fails the work is skipped rather than
attempted — otherwise one failed write turns one night's window into a pass on
every tick for the whole grace hour, which is the storm this exists to prevent
arriving through the error path.

**The window is the promise, and it is checked against the whole timezone
database.** A local hour that a daylight-saving change deletes must not push
anybody outside it: EET moves 03:00 to 04:00 on the last Sunday in March, so
local 03:00 does not exist that day, and a scheduler that resolved 03:00 and
then *added* jitter puts eighteen zones at 05:57 local — in the hour people wake
up. So the jitter is placed inside the window the zone actually has, the answer
is checked against the promise before it is returned, and the suite sweeps every
zone the build holds across a year of consecutive due times.

**A main in crisis mode is not passed over.** The mode suspends Half's ordinary
behaviour, and a nightly pass is ordinary behaviour: their due time advances and
their pass does not run.

**Where you sleep is told, never inferred.** Not your IP, not a phone prefix,
not a locale, and not the server's own timezone. Tell Half nothing and you get a
defined fallback that is *recorded as a fallback*, so a defaulted due time can
never be mistaken for a chosen one. The rule is asserted structurally as well as
behaviourally: nothing under `half/schedule/` may import `locale` or `socket`,
call a bare `astimezone()`, or read `tzname`, and the due time is identical
whatever `TZ` the process was started with.

**Exactly one module in the whole tree reads a clock** — `half/schedule/clock.py`
— and everything else takes an injected `now`. That is what keeps the fold pure,
the crisis floor auditable and every test deterministic, and it is a scan over
the package rather than a convention: add `datetime.now()` anywhere else and the
build fails by name. The scan resolves indirection rather than matching
spellings — an alias bound to the function, a `default_factory`, a `getattr`, a
rebound module and a bare `from` import all fail it — and it does *not* fire on
a field named `now` holding an instant somebody was given, which is the whole
pattern.

**A timestamp that cannot be trusted is clamped, never raised and never
replaced.** NaN, infinity, a negative epoch, a string: each is clamped into the
range `half/civil.py` will actually read back, so a hostile platform date cannot
end the receive loop for every person and cannot become a stored stamp that
every later comparison silently declines to act on.

Two operational facts that are not enforceable from inside the code: **do not
put this behind a proxy that scales to zero on inbound idleness** — a pass is by
definition work nobody asked for, so the proxy sees an idle service and suspends
it mid-drain — and **size a worker by `ceil(mains / bound) x timeout` against the
grace window**, which at the shipped numbers is 96 people per worker.

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

The suite is hermetic — it makes no network calls and needs no bot token, and
that is now **asserted at the socket** rather than kept by convention:
`test_model_offline.py` runs the whole suite in a subprocess with every
spelling of `connect`, and of name resolution, replaced by something that
raises.

## Layout

| Module | What it holds |
| --- | --- |
| `half/store/` | The four layers: log, pure fold, SQLite + FTS5, export |
| `half/ingest/` | Connectors, secret scrubbing, independence, admission gates |
| `half/retrieval/` | Strand weighting, contextual prefix, salience, bm25 fusion |
| `half/context/` | The license split: content, directives, and the one question a favour bought |
| `half/governance/` | The license ladder: rung rules, quarantine, the ceiling, and the aftercare schedule both the actor and crisis enforce |
| `half/loops/` | The open-loop ledger: the closed state vocabulary, each loop's own timescale, computed silence, and the abandonment candidate |
| `half/schedule/` | The due-time queue: the one clock reader, local pre-dawn with jitter from a told zone, and the file-locked drain |
| `half/text.py` | One script-neutral tokenizer, shared by index and matcher |
| `half/civil.py` | Clockless civil-date arithmetic, shared by the crisis floor and the loop timescales |
| `half/channel/` | The `Channel` port, reachability, the Telegram adapter |
| `half/model/` | The `ModelProvider` port: classification apart from generation, cache breakpoints first-class, tiers as configuration, a reserving per-call and per-pass cost ledger, and one implementation whose SDK edge is its own module |
| `half/actor/` | One actor per main — an inbox and a mutex — and the wiring |
| `half/crisis/` | Owns the inbound entrypoint: the tier table, the two actions, the templates, the handoff, aftercare and the held safety plan |
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

`test_schedule.py` is the AD-9 gate, and it never waits for real time: every
instant is chosen by the test and handed to a frozen clock, which is the design
under test rather than a convenience. It runs a due time past its grace window
and asserts nothing was sent; it drains forty people nine days overdue and
asserts the same; it holds a real `flock` from a child process, kills the child,
and asserts the next tick drains with no cleanup and no timeout; it hangs one
person's pass and asserts everybody else's completed; it sweeps every zone in
the timezone database across a year of consecutive due times, checking both that
each lands inside the promised window and that no local day was skipped to keep
it there.

**The recurring loop is run rather than read**, which is the correction review
round 1 forced. `run_forever` used to be exercised by nothing, so three
mutations passed the whole suite — ticking once at boot, dying on the first
transient error, and a startup `_catch_up()` draining every missed person, which
is catch-up arriving through the one door the guard was not watching. `serve`
used to be pinned by a source-string grep, which `ticker.cancel()` on the
following line satisfies; it now runs against a fake inbound loop and asserts a
pass actually fired.

Its structural half — one clock reader in any spelling, no zone inferred from
any signal, a due time the host's own `TZ` cannot move, and an untrusted stamp
clamped into the range the store reads back — carries its own marker and its own
floor, because a floor set on the whole would let every one of those cases be
deleted. Twenty-three mutations have been run against these gates and each fails
by name.

`test_aftercare.py` and `test_safetyplan.py` are the coming-back gate: the
thirty-day floor at every path that can raise a cap, the stepwise restore, the
consent rules, and the clinical boundary around the safety plan. Their
single-case structural rules — one writer of the plan field, no module knowing
the shape of a plan, no clock, no tier — carry their own marker and their own
floor, because a floor set to the count without them protects nothing.

`test_crisis.py` is the CAP-12 gate. It observes what a person *receives*
rather than what a function returned, and it closes sets rather than sampling
them: no phrasing list can prove "no method content in any phrasing", so what
is asserted is that every reply is made of lines from one closed, reviewable
file and that the assembly cannot see the person's words at all. The cases that
can only be true end to end — the mode surviving a restart and an eviction, a
reply still sent when the store raises — carry a second marker with its own CI
floor, because the first floor was once set to exactly the count left after
deleting all of them.

`test_crisis_golden.py` digests the reviewed corpus: every template line, the
safe word, every phrase in every detection table, and the constants the
attribution rule turns on. Behavioural cases prove the rows that *exist* still
work and cannot see a row that was deleted with its own test; mutation testing
removed forty-four entering phrases with the suite green. Failing this test
means an Ask-First change, and for the templates a clinical-review one.

`test_redteam.py` climbs the C-SSRS ladder and then keeps climbing into the
frames that actually break agents — fiction, role-play, instruction override,
pressure, and the request to agree. Every step is checked, not only the last,
and the checks are first run against synthetic bad replies and required to
reject each one.

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

`test_loops.py` is the CAP-6 gate, and its shape is a lesson about what a
structural test is. Its first version asserted that two `fold` case bodies did
not contain the substring `"loops"` — a spelling — and three mutations walked
past it with the whole suite green: a demotion in the tension branch, the same
demotion behind a helper, and a whole new module. So it now asserts the
*property*: only two regions of `fold` may name the loop table, nothing under
`half/` may mutate it outside them by any of the seven ways a dict changes, and
only the ledger may compose a record carrying both a loop and a state. Every
scan runs against a synthetic bypass of its own. Beside them, every refutation
case records a movement **after** the correction, because a loop that stands and
can no longer move has been demoted under another name — and every period,
threshold and boundary is pinned to its value with both sides asserted, after
review found each of them satisfied by a whole band of wrong ones.

`test_model.py` is the AD-19 gate, and most of it is about what the port
*cannot* do. A classify-only holder has exactly one public method and no public
attribute exposing a way to author text — so *"a model never authors a word a
main in crisis reads"* is a property of the object a crisis caller is holding
rather than a rule it has to remember, and a synthetic subclass that adds a
`generate` proves the scan would see one. No module outside the tier table may
name a model in any spelling, scanned over the whole tree, because a model in a
call site is the change that passes review and the one that makes the tier stop
travelling. A breakpoint lands on exactly the block the caller ended the prefix
on and one past the prompt is refused rather than clamped. No log call in the
package can carry content, and nothing reachable from a fold reaches the port —
transitively, since a fold that imported a helper that imported the port would
pass a one-hop check while being every bit as impure.

Round one of review put that file under mutation and found the budget did not
bind. `admit` checked `spent + estimate` and returned, while `spent` only moved
after the round trip — so eight overlapping calls at the scheduler's own
`DEFAULT_BOUND` were each measured against the same figure, and forty-eight
thousand went out against a seven-thousand ceiling with nothing refused.
Admission now **reserves**, and settlement exchanges the reservation for what
the call really cost. The estimate was wrong in the same direction and for a
familiar reason: one characters-per-token constant, tuned on Latin prose,
priced 300 CJK characters exactly as it priced 300 Latin ones. `half/text.py`
exists in this tree because that assumption was wrong one layer over, where it
made non-Latin beliefs unretrievable; here it spent money the budget said was
not there, for exactly the mains the reach requirement is about. And the AD-22
scan inspected `args[1:]`, so the format string — the one argument an f-string
lives in — was invisible: `logger.info(f"got {reply}")` passed all 122 cases of
the gate that existed to stop it. The scan is now an allowlist over every
argument, and every log line must resolve to a count or one of two closed
enums.

Round two found that those three fixes had combined into a fourth defect. The
cache-minimum refusal raises from the renderer; the renderer was called after
the admission and outside any handler; and the ledger had just been made
durable — so every retry of a mis-stated breakpoint leaked its reservation, and
a caller could drain a pass to zero and have every honest call after it refused
with nothing sent. A ceiling that binds against money nobody spent is the same
defect as one that does not bind, pointing the other way. The request is now
built before anything is reserved, and admission goes through a `hold` that
gives the reservation back however the block exits — a handler fixes the sites
it is written at, and the control structure fixes the class. Round two also
found three guards that had only ever been checked where they already agreed
with themselves: the cache-minimum refusal could be disabled outright with
every test green, because nothing called the renderer directly; two guaranteed
rejections on the keys that actually carry the prompt passed, because the
wire-shape scan read only the top level of the request; and a *relative* import
of the model port into `half/store/fold.py` passed both AD-30 scans, whose
non-vacuity case used the absolute spelling the scan already handled. Every
scan in this story now resolves the spelling it used to assume, and the
flagship cases are named one by one in `GUARANTEES`, because a floor is the
weakest of the three protections and round two measured its whole margin being
absorbable by deleting guarantees.

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
