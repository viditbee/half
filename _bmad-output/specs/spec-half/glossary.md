# Glossary

Companion to `SPEC.md`. This spec carries invented vocabulary; these are the definitions every consumer works from.

**Half** — the product. A second self: the main's own self, existing outside them. Not an assistant and not agent memory.

**Main** — the person a Half belongs to. Always singular; a Half has exactly one.

**The two ledgers** — the split that makes the product possible.
- **Revealed ledger** — what the main actually *does*, derived from transactional sources (email, receipts, bank, calendar, subscriptions). Free and automatic; one OAuth and it flows.
- **Stated ledger** — what the main *wants*: plans, ambitions, preferences, routines. Sourced only from the main's outbox and from conversation with Half. **It cannot be ingested, only told**, which is why trust is the acquisition cost of the irreplaceable half of the data.

**The mirror** — Half's core output: the gap between the two ledgers. What the main actually values, as distinct from what they say they value.

**State** — how the main is *right now*. Volatile, cheap, overwritten, expires fast. **Never written to the belief ledger.** Mood is not a belief.

**Belief** — a durable, evidenced claim about the main, carrying its support set, independence count, last-corroborated date, and license. There is no confidence score: a claim with no truth value cannot carry one honestly, and a number invites false precision.

**Open loop** — Half's core object. Something the main started wanting and has not resolved. A fact is true or false; a wanting is neither — it has a **state** (`advancing` / `stalled` / `abandoned-but-unadmitted` / `achieved`) and a **natural timescale** (farmland moves in years, a workout routine in days). The open-loop ledger is not a user-facing surface; it is the **ranking function** for everything Half does.

**Tension** — a first-class record linking two entries that disagree and cannot be resolved, because for a person neither is wrong. Carries state (`fresh` / `persistent` / `widening` / `closing` / `resolved`) and a license. Minted by the nightly pass. **Drift is tension velocity**; **loop advancement is tensions closing**.

**License ladder** — what a belief or tension permits, defaulting to the weakest.
- `behave` — Half acts on it silently: softens tone, delays a nudge, drops a suggestion, reorders what surfaces. Most beliefs never leave this rung.
- `ask` — Half may raise it as a question.
- `assert` — Half may state it. Rare, and only when the main already knows Half holds it.

**Quarantine** — a belief permanently pinned at `behave`. A schema field, not an exception list. Half may detect a candidate by inference but never applies quarantine on inference alone — it asks.

**Unsaid queue** — insights Half holds because it lacks the license to deliver them, each with a release condition (trust level, topic raised by the main, day of week, expiry). Queue depth is itself a signal.

**Unasked queue** — clarifying questions Half is holding. Paid for by **stakes**, not by favors: asked only when acting on a wrong belief would cost more than the interruption, and attached lazily to a conversation already touching the topic.

**Trust balance** — the spendable currency of the relationship. Questions cost; delivered favors earn. **An unspent balance is a defect**, not a virtue.

**The favor buys the question** — the rule that Half never asks without having just given.

**Interrupt on irreversibility** — Half breaks through unprompted only when waiting would *destroy an option*, not when something is merely important. School pickup qualifies; a 2pm medication that can be taken at 2:35 does not.

**Nagging** — touching an open loop faster than that loop's own timescale. A computable condition, not a judgment call.

**The morning surface** — at most one unprompted message per day, produced by the night's consolidation rather than a schedule.

**Nightly pass / consolidation** — the scheduled run that promotes episodic material to durable claims, decays unused salience, and mints tensions. Carries the expensive interpretation so query time stays cheap.

**The magic trick** — onboarding. One OAuth, ninety seconds, one true and slightly uncomfortable statement about the main. Both the activation moment and the acquisition mechanism.

**Correction verbs** —
- `retract` — *"you changed."* Appends a correction; history preserved; no apology.
- `revise` — *"Half was wrong about you."* Apologise and show the removed belief.
- `expunge` — genuine removal, tombstoned. Rare, main-initiated only.
- *decay* — salience falls with disuse; no event recorded.

**Independence** — corroboration that collapses sources sharing an origin, content hash, or publisher. Ten mentions of one fact in one email thread is **one** support, not ten.

**Endorsed-at-30-days** — of what Half surfaced, the fraction that changed behaviour and is still endorsed a month later. One of three metrics; gameable alone by sycophancy.

**Disagreement rate** — whether Half has contradicted its main recently. The counterweight to endorsement.

**Loop advancement** — whether open loops are actually moving. The behavioural counterweight to both.

**Half-to-Half / the Half Protocol** — the v2 network in which two Halves exchange typed questions under scoped mandates. **Out of scope for v1** and listed under Non-goals; design preserved in the half-protocol intent doc.
