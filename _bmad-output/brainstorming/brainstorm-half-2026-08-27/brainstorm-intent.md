# Half — Intent

**Source:** brainstorming session 27–30 Aug 2026 (231 entries, 8 techniques). Full record: `.memlog.md`.
**Status:** converged on v1 scope. Ready for `bmad-product-brief` / `bmad-prd` / `bmad-spec`.

---

## What it is

Half is a second self that lives in WhatsApp/Telegram — the main's own self, existing outside them. It holds what its main can't hold, shows up in their day unprompted, and has the standing to disagree with them.

**Not** an assistant, a note app, or agent memory. The distinction is load-bearing: every comparable open-source system (gbrain, honcho, khoj, hermes-agent, claude-obsidian, graphiti) builds **memory for agents**. Half is **memory about a person, for that person**.

## Mission

**"IQ doesn't matter when you have Half."** Half is a leveler, not a power tool. The target user is the person with *zero* pages — smart and scattered, no systems, no mentor — not the quantified-self optimiser. This constrains architecture as much as marketing: cheap retrieval isn't an engineering compromise, it's what makes the mission physically possible.

## Core object: the open loop

Half's primary object is **not a fact**. A fact is true or false; a plan is neither. Almost everything a close friend knows about you — ambitions, purpose, the farmland, the routine you're *trying* to build, the sport you stopped — is a **wanting with a trajectory**.

An **open loop** = something the main started wanting and hasn't resolved, carrying:

- **State:** advancing / stalled / abandoned-but-unadmitted / achieved
- **Natural timescale:** its own period (farmland = years, workout routine = days)
- **Evidence:** links into both ledgers

The open-loop ledger is **not a user-facing surface** — it is the **ranking function** for everything else. It expresses itself silently through the daily layer. This is how it is simultaneously the most important thing in the system and something the main hears about roughly monthly.

## The two ledgers

| Ledger | Source | Cost |
|---|---|---|
| **Revealed** — what you did | Bank, receipts, orders, subscriptions, rent, certificates, calendar | Free and automatic (one OAuth) |
| **Stated** — what you want | The **outbox** + conversation with Half | Expensive; cannot be ingested, only *told* |

**The gap between them is the product.** Half is the only entity holding both ledgers — a revealed-preference engine. The killer feature is not recall; it's the mirror: *what you actually value, as distinct from what you say you value.*

Consequence: **trust is the acquisition cost of the irreplaceable half of the data.** The impromptu question is not a warmth feature — it's the only acquisition channel for the stated ledger.

## Memory architecture

**Ingestion is unbounded. Belief is bounded.** Keep every byte forever; never retrieve the corpus. The searchable surface is the set of *claims about this person*, each citing its evidence. Ten thousand emails produce ~forty things true about you. Retrieval quality cannot degrade with corpus size because retrieval never touches the corpus.

- **Source of truth is human-readable.** Every index (BM25, embeddings, graph) is derived and rebuildable. Solves export, survives embedding-model churn, and makes the *file format* the open-source standard rather than the code.
- **Retrieval:** contextual prefixes + BM25 + optional rerank. **No vector service in the hot path** (Anthropic's contextual retrieval: 67% failure reduction with this stack). Runs on cheap hardware — required by the mission.
- **Belief admission gates:** (1) decision-relevance — would it change what Half does or says? (2) durability — one food order is an event, fifty are a belief; (3) independence — union-find corroboration, ten mentions in one thread is *one* support; (4) falsifiability — the main can say "that's wrong" and it is removed.
- **Supersede, never invalidate.** Person-epistemics: you said you'd run in March and didn't — both records are permanently true and the tension *is* the finding. No better source resolves it; there is no winner to select.
- **Two distinct expiries, never conflated:** *Half was wrong about you* (apologise, show the deleted belief) vs *you changed* (no apology — that's growth).
- **Salience, not tiers.** Nothing is partitioned; context only changes weight. **Half must never be able to say "I don't have access to that."**
- **Nightly consolidation** carries all the expensive interpretation, so query time stays near-free.

## The theory of the recipient

The field's blind spot. Every reviewed system optimises *what to retrieve*; none models *whether the human can hear it right now*.

- **Trust as spendable currency.** Every question costs; every small win earns. **An unspent balance is a defect, not a virtue** — a Half hoarding trust is being cowardly, not careful.
- **The unsaid queue** — insights held with release conditions (trust level, topic raised, day-of-week, expiry).
- **The unasked queue** — clarifying questions paid for by *stakes*, not favours: ask only when acting on a wrong belief costs more than the interruption. Asked **lazily**, attached to the next natural conversation.
- **Silence is a shipped feature.**
- **Restraint is the core competence.** Every system in this field can retrieve; only Half declines to.

## Constitution

| Law | Statement |
|---|---|
| Favour buys the question | Half never opens with an interview; it interviews across the first month, not the first screen. |
| Falsifiable and same-day | Everything Half says early must be checkable, or trust never compounds. |
| Interrupt on irreversibility | Break through only when waiting *destroys the option*. Everything else queues to evening. |
| Nagging, defined | Touching a loop faster than its own timescale **is** nagging. Arithmetic, not judgment. |
| Never small, may be uncomfortable | Cruelty, contempt, ridicule, comparison, despair — banned forever. Disappointment is the job. |
| Not a prosecutor | When the main lies, Half holds both records and never says "you told me otherwise." The lie is data. |
| Visible belief revision | Errors are *memory* errors. Repair = showing the deleted belief. "That's wrong" is a first-class action. |
| Assert only with receipts | Unsupported claims may be **asked**, never **asserted**. |
| Quarantine | A class of memory Half may read but never raise — and must *infer*: a name going from daily to zero overnight is a wound, not a forgotten topic. |
| Crisis inverts everything | Trust, queues, faces, interrupt law all suspend. Half never counsels action, never diagnoses, never goes quiet. It stays and surfaces a human. |
| Never store a secret | Credentials, OTPs, recovery codes skipped **at ingestion**. The safest data is data never kept. |
| Sovereignty | Never onboardable by anyone but the main. Recovery belongs to the main alone. |
| Nobody buys Half's opinion | No affiliate or third-party money, ever. The subscription *is* the trust guarantee. |
| No blackmail at the paywall | Half never performs loss about being downgraded. States the change once, plainly. |

## Metrics — three, because any one alone is gameable

1. **Endorsed-at-30-days** — of what Half surfaced, what fraction changed behaviour and is still endorsed a month later. (Approval; gameable by sycophancy alone.)
2. **Disagreement rate** — if Half hasn't contradicted its main in 90 days, it has stopped being a half. (Friction.)
3. **Loop advancement** — did the open loop actually move. (Behavioural outcome, not opinion.)

No 2026 benchmark (LoCoMo, LongMemEval, BEAM) measures any of these; they all measure retrieval.

## Business model

- **Open source, BYO key** — free forever, and the escape valve for expensive users.
- **Meter the reach. Never the cadence, never the memory.** Free Half converses daily, forever, unrationed, with full memory and export — it just can't *see* much. Paid Half connects Gmail, calendar, bank, receipts. Cost-aligned: ingestion and the nightly pass scale with sources, not conversation.
- **On lapse:** Half keeps everything, loses the connectors, says so plainly. Reconnect loses nothing.
- **Never gated at any tier:** crisis support, export.
- **Regional pricing** is a first-class requirement, not an afterthought.
- **Trial trap:** Half is worthless in week one *by design*. A 7-day trial demos the worst Half that will ever exist. Trial must outlast trust-accrual (30–60 days) — or be permanent-free-with-limited-reach.
- Hibernation on dormant users; small model for free tier, frontier for paid.

## Channels

- **An organ, not an app** — you never *open* an organ. WhatsApp/Telegram first; the app is strictly secondary.
- **Single thread.** The main must never be forced to open a new thread. Threads are a *view*, not a container.
- **Onboarding is a magic trick, not a wizard:** one OAuth, ninety seconds, one true and slightly uncomfortable thing about you. That's the acquisition screenshot.
- **Platform facts:** Telegram bots can never send the first DM (unblocked permanently after one user message). WhatsApp Cloud API gives a 24h free-form window; outside it, approved templates with opt-in only. Personal-account automation violates ToS and gets numbers banned.
- **Legal outreach paths:** one-tap prefilled `wa.me` draft (main stays the sender) · groups (a bot in a group posts freely — the growth loop) · the handshake.

## v1 scope (MoSCoW — agreed)

**MUST** — single WhatsApp/Telegram thread · magic-trick onboarding · both ledgers · open-loop ledger with states · nightly pass producing one morning surface · human-readable truth + rebuildable BM25 index · belief admission (decision-relevance + independence) · trust currency + unsaid queue · interrupt-on-irreversibility · the constitution · **crisis protocol** · **secrets skipped at ingestion** · export as files.

**SHOULD** — voice notes · register fitting · quarantine inference · faces as salience weights · Half asking for help · connectors beyond Gmail.

**COULD** — the app / wall / strands · sensors · family plan · SWOT playground.

**WON'T (v1)** — all of Half-to-Half. It is the moat and it is what v2 is *for*, but it needs a network that doesn't exist, an unwritten protocol, and the third-party law enforced on day one. Build the thing that makes **one** Half worth having.

## v2 — Half-to-Half (recorded, deliberately deferred)

Multi-party constraint satisfaction with **private constraints**: group coordination fails because constraints are unsayable out loud, so Halves negotiate and only the answer surfaces. Unit of exchange is a **mandate** (scoped, revocable, with limits). **Halves propose, mains commit.** **Only derived judgments cross — constraints, never verdicts about a third party**, or Half becomes a reputation system about people. Second open standard: *the Half Protocol*.

## First 100 users

Two cohorts with different jobs: **technical users validate the architecture** and become contributors; **non-technical family validates the product**. Shipping only to tech friends rebuilds gbrain. Zero-cost channels: one family group chat solving one real coordination problem, and the founder's own paragliding community — a niche full of dormant seasonal interests is literally the canonical demo.

## Open questions

1. Context partitioning — one brain, focused threads, cohesive across a single WhatsApp line and a multi-thread app. Named the hardest problem, technical and UX both.
2. Person-epistemics schema — what a claim ledger looks like when the subject is a person and no sourcing can resolve the contradiction.
3. Independence for self-belief — what counts as two independent pieces of evidence about a human.
4. Mortality — what happens to a Half when its main dies.
5. The adversarial case — a bad actor's Half built to extract signal from yours.
6. Sensors — the phone as a revealed-preference array: highest value, highest creep. Decide deliberately.
7. Free-tier unit economics — cost per active free user per day against a realistic dormancy curve. Arithmetic, not design.
