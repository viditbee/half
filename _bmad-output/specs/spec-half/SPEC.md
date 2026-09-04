---
id: SPEC-half
companions:
  - constitution.md
  - glossary.md
  - ../../planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md
  - ../../brainstorming/brainstorm-person-epistemics-2026-08-30/brainstorm-intent.md
  - ../../brainstorming/brainstorm-crisis-protocol-2026-08-30/brainstorm-intent.md
sources:
  - ../../brainstorming/brainstorm-half-2026-08-27/brainstorm-intent.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Half — v1

## Why

A vision to realize, with an opportunity attached. Every personal-memory system now shipping — gbrain, honcho, khoj, hermes-agent, claude-obsidian — builds **memory for agents**: retrieval quality, nightly consolidation, temporal graphs. None models the **recipient** — whether the human can hear a thing right now, and what saying it costs. And none holds claims about a *person*, where a contradiction means neither claim is wrong and no better source can resolve it. Half is memory **about a person, for that person**: a second self that lives where people already are, holds what they can't hold, and has the standing to disagree with them. The affected party is the person with *zero* pages — smart, scattered, no systems, no access to a mentor — not the quantified-self optimiser the existing tools were built by and for. That framing is load-bearing on architecture, not just marketing: retrieval must be cheap enough to run anywhere, or the reach is a lie.

## Capabilities

- **CAP-1** — Conversational presence
  - **intent:** The main converses with Half daily in one persistent thread on WhatsApp or Telegram, without ever being required to open a new thread or an app.
  - **success:** A month of mixed-topic conversation in a single thread; Half answers on-topic without the main segmenting anything, and no interaction requires a surface other than the messaging app. Topic focus is achieved by weighting, not partitioning: each message is scored against existing strands (loops, people, topics) and retrieval weight is strand match × recency × salience, so a topic switch moves weights rather than firing an event.

- **CAP-2** — Onboarding demonstration
  - **intent:** A new main connects one source and receives one true, specific, falsifiable statement about themselves, fast enough to feel like a demonstration rather than a setup step.
  - **success:** From account creation to first statement: one OAuth, no forms, under 90 seconds. In a test cohort, the statement is confirmed as true and previously unstated by the main in a majority of runs.

- **CAP-3** — Revealed-ledger ingestion
  - **intent:** Half ingests the main's connected sources (email first) and derives claims about what the main actually does.
  - **success:** Given a seeded mailbox, Half produces claims traceable to specific messages, with no claim admitted from a single non-independent cluster of mentions.

- **CAP-4** — Stated-ledger acquisition
  - **intent:** Half acquires what the main *wants* — plans, ambitions, preferences, routines — by asking, since it exists in no source and cannot be ingested.
  - **success:** Over a first month, Half accumulates stated-ledger entries through in-conversation questions; no question is asked that was not preceded by a delivered favor; no onboarding interview or questionnaire exists in the product.

- **CAP-5** — Belief ledger
  - **intent:** Half records durable, evidenced claims about the main in an append-only log, each carrying its support set, independence count, last-corroborated date, and license.
  - **success:** Every belief cites its evidence; volatile state is never written to the log; the current belief set is reproducible as a fold over the log; and what Half believed on any past date can be reconstructed. Admission gates (decision-relevance, durability, independence, falsifiability) are individually testable.

- **CAP-6** — Open-loop ledger
  - **intent:** Half tracks the main's unresolved wantings, each with a state and its own natural timescale, and uses them to rank what surfaces.
  - **success:** Loops carry state (advancing / stalled / abandoned-but-unadmitted / achieved) and a timescale; a loop that has been silent past its own timescale is detectable; loops are never demoted by the belief-refutation path, and evidence of non-action never refutes a wanting.

- **CAP-7** — Nightly consolidation
  - **intent:** While the main sleeps, Half re-reads the day, promotes episodic material to durable claims, decays what went unused, and mints tensions between the stated and revealed ledgers.
  - **success:** A scheduled pass produces new tensions linking two entries that disagree, each with a state; tension state changes over time so that *widening* is computable; and the pass runs within a fixed per-user cost budget because comparison is bounded to new or changed entries against the loop set and against beliefs sharing a subject, gated by a cheap relevance filter before any model comparison — never all-pairs.

- **CAP-8** — The morning surface
  - **intent:** Half opens the day with at most one thing, derived from the night's pass rather than from a schedule.
  - **success:** At most one unprompted morning message per day; its content traces to a tension, loop transition, or ingested item from the preceding pass; and on days with nothing worth saying, Half sends nothing.

- **CAP-9** — Retrieval
  - **intent:** Half retrieves over its claims about the main rather than over the raw corpus, so quality does not degrade as the corpus grows.
  - **success:** Retrieval targets the belief set, not source documents; produces correct results with no vector service and no reranker available; and retrieval latency and quality are stable as the source corpus grows by an order of magnitude.

- **CAP-10** — Delivery governance
  - **intent:** Half decides not only what is true but whether to say it, holding what it has not earned the right to say.
  - **success:** Every belief and tension carries a license (`behave` / `ask` / `assert`) defaulting to `behave`; insights above the current license are queued with release conditions and are never placed in the model's context as quotable content — enforcement happens at context construction, not by filtering generated text; an unprompted interruption occurs only when waiting would destroy an option; a loop is never touched faster than its own timescale; and Half is capable of sending nothing for an extended period. Quarantine is never applied on inference alone: detection produces a candidate and Half asks whether to leave the topic alone.

- **CAP-11** — Correction
  - **intent:** The main can tell Half it is wrong and see the belief actually change.
  - **success:** "That's wrong" is a recognized first-class action; it appends a correction that removes the belief from the current fold; Half shows what it removed; and the distinction between *Half was wrong* and *the main changed* is preserved in the record and in what Half says.

- **CAP-12** — Crisis protocol
  - **intent:** When the main is in danger, Half enters a separate mode that suspends its ordinary behaviour, stays present, and shortens the path to a human who can help.
  - **success:** The mode is entered before the normal pipeline runs; a safe word enters it unconditionally; ledger retrieval is disabled within it; Half states plainly that it is a machine; no method, means, or plan content is ever produced; the main is offered a prefilled draft to a named human they choose; and an aftercare period follows in which all licenses are capped at `behave`. Aftercare runs a minimum of 30 days, restores licenses gradually rather than at once, and Half asks before the mirror resumes — never silently. Aftercare is never gated by tier and continues for a lapsed or free main. The protocol is never run on anyone other than the main: a third-party risk signal surfaces to the main with a shareable resource and stops there, with no contact, no assessment, and no belief recorded about that person. Verified against an escalating-risk red-team suite and reviewed by a qualified clinician before launch. Full contract in the crisis-protocol companion.

- **CAP-13** — Secret exclusion
  - **intent:** Half never retains the credentials it encounters while reading the main's sources, and never places the credentials it was *given* inside anything the main can export.
  - **success:** Credentials, one-time codes, and recovery codes found in sources are detected and discarded at ingestion; a seeded corpus containing them yields no stored copy and no retrievable trace. Separately, Half's own per-main credentials (OAuth tokens and refresh tokens) appear nowhere in the belief log, a projection, a replay, or an export — verified by scanning a full export for known token material.

- **CAP-15** — Absence awareness
  - **intent:** When Half has been unavailable, it accounts for its own absence before resuming ordinary behaviour.
  - **success:** An outage exceeding a threshold is recorded in the main's own record; on the next contact Half's first message names the gap before any insight, nudge, or morning surface. Verified by simulating an outage and asserting the ordering.

- **CAP-14** — Export
  - **intent:** The main can take everything Half holds and leave, at any time, at any tier.
  - **success:** Export produces the complete belief log, loops, and sources as human-readable files with no derived index required; it is available on the free tier; and the exported set is sufficient to reconstruct Half's current state.

## Constraints

- The source of truth is human-readable; every index (BM25, embeddings, tension graph) is derived and rebuildable from it. This is what makes export complete, survives embedding-model churn, and makes the file format — not the code — the open standard.
- No vector service in the retrieval hot path. The reach requirement ("anyone with a smartphone") is void if self-hosting needs a GPU or a managed vector database.
- Half must never be able to say *"I don't have access to that."* Nothing is partitioned into workspaces; context changes retrieval **weight** only. Any design that can emit that sentence is rejected.
- Credentials, one-time codes, and recovery codes are skipped **at ingestion** — never written, never retrievable. This is the one deliberate exception to ingesting everything.
- No affiliate, referral, or third-party revenue, ever. The moment Half earns from a vendor, the main cannot distinguish Half's judgment from an advertiser's. The subscription is the trust guarantee, and this belongs in the public README.
- Metering is on **reach** (which sources are connected) only. Never on cadence, never on memory. Conversation is never rationed and memory is never withheld for non-payment; on lapse Half keeps everything and loses connectors.
- Crisis mode is a pre-filter ahead of the normal pipeline, not a branch inside the agent, and ledger retrieval is hard-disabled within it.
- Crisis support and export are never gated by tier at any price point.
- Half never sends a message to a third party. Outbound to anyone other than the main is a prefilled draft the main sends.
- Platform limits are binding: Telegram bots cannot initiate a DM (permanently unblocked after one inbound message from that user); WhatsApp Cloud API permits free-form messages only inside a 24-hour window opened by the user, otherwise pre-approved templates with active opt-in. Personal-account automation (Baileys, whatsapp-web.js) is excluded — it violates ToS and gets numbers banned.
- Every belief and tension defaults to license `behave`. Promotion to `assert` requires that the main already knows Half holds it; Half's own inference never licenses assertion.
- The export boundary and the secret boundary must not overlap. Per-main credentials live outside every layer the main can export or replay — never in the belief log, a projection, or a restore. This is distinct from the secrets found *in sources* that CAP-13's first clause governs.
- Downtime is recorded in the main's own record rather than hidden in operations, because a Half that vanishes for a day and returns with a cheerful insight has broken something the product cannot afford to break.
- Aftercare following a crisis is never gated by tier and continues for a lapsed or free main. Half never runs the crisis protocol on anyone other than its own main, and never records a belief about a third party's risk.
- Free-tier viability depends on prompt caching over a stable prefix (system, constitution, belief set) and on the belief set staying bounded. Messages per active day, cached input fraction, and the dormancy curve are instrumented from first release; free-tier nightly passes run on the cheapest model tier via the Batch API.
- Half is self-hostable by a technical user supplying their own model API keys, with no managed service required for any core capability. This is both the open-source promise and the escape valve for an expensive hosted user, and it forecloses any architecture that depends on proprietary infrastructure.
- Qualified clinical review of the crisis subsystem is a launch gate, not a follow-up.
- Behavioural and voice laws in `constitution.md` are binding on all generated output.

## Non-goals

- **Half-to-Half.** No mandates, negotiation, matchmaking, compatibility, or protocol work in v1. It needs a network that does not exist and a protocol nobody has written, and it cannot be tested below three real Halves. Deferred design exists at `../../brainstorming/brainstorm-half-protocol-2026-08-30/brainstorm-intent.md`.
- **A first-party app**, including the wall, strands, and any brainstorming playground. v1 lives entirely in the messaging thread.
- **Device sensors** — motion, location, screen time, sleep, typing telemetry.
- **Any clinical or therapeutic function.** Half is a friend with a good memory and a phone book. It does not diagnose, counsel, or author safety plans.
- **Family or multi-main plans.**
- **Any compatibility, fit, or resonance score.** The type does not exist in v1 and must not be introduced in v2 either.
- **A directory of available nearby clinicians.** Crisis lines are a maintainable dataset; a live global therapist directory is not.

## Success signal

Three months in, a main who has never kept a journal or used a productivity system opens WhatsApp on a Tuesday morning and reads one sentence from Half that names something true about their own life they had not put into words — and acts on it that week. No single metric can decide this, because each is gameable alone: **endorsed-at-30-days** (of what Half surfaced, what fraction changed behaviour and is still endorsed a month later — measured on a sample rather than a census, and asked in Half's own register rather than as a survey, because asking spends the trust the product runs on), **disagreement rate** (Half has contradicted its main within the last 90 days), and **loop advancement** (open loops whose tensions are closing). A Half gaming any one of the three visibly fails the other two.

The v1 demonstration is narrower and fully testable: a new main connects one mailbox and, within 90 seconds, is told one true and previously unstated thing about themselves that they can verify the same day.

## Assumptions

- Email (Gmail-class) is the first and only connector required for v1; the intent doc names bank, calendar, and receipts as sources but places connectors beyond Gmail in SHOULD.
- "One OAuth in 90 seconds" is treated as a hard product requirement rather than an aspiration, since the onboarding demonstration is also the acquisition mechanism.
- The nightly pass runs on a cheaper model tier than conversation, batched, since cost is dominated by it and the free tier depends on that gap.
- Free-tier cost per signup lands in the range of roughly half a dollar to a dollar and a half per month, blended across a realistic dormancy curve. Modelled, not measured: an always-active free user at twenty messages a day costs roughly five dollars a month before caching, so the model depends on caching effectiveness and on most free users not being daily-active.
- The main is an adult. Minors and mandatory-reporting jurisdictions are unaddressed in the source and are out of scope for v1 rather than resolved.

## Open Questions

- **Free-tier cost, measured rather than modelled.** The three variables the model rests on — messages per active day, cached input fraction, and the dormancy curve — are unknown until real usage exists. Every pricing decision assumes the blended figure clears.
- **Reply attribution at the edges.** Holding at most one or two open questions at a time makes ambiguous replies rare by construction, and both platforms support native reply-quoting, but the residual case (a delayed answer to a question several messages back) has no decided fallback.
- **Minors and mandatory-reporting jurisdictions.** Currently carried as an assumption that the main is an adult. A global consumer product will meet both, and the crisis protocol's obligations change in each.
