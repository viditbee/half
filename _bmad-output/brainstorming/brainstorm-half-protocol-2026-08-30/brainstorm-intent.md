# The Half Protocol — Intent

**Source:** deep-dive #3 from the Half session, 30–31 Aug 2026 (20 entries). Full record: `.memlog.md`.
**Parent:** `../brainstorm-half-2026-08-27/brainstorm-intent.md`
**Status:** converged on the spine. **v2 — deliberately not in v1.**

> The design decides which future happens. *"All Halves connected"* is both the brochure line and the dystopia headline, one architectural choice apart.

---

## The value

**Multi-party constraint satisfaction with private constraints.** Group coordination fails because the real constraints are unsayable out loud — *"I can't actually afford it," "I don't want to share a room with him," "I have therapy on Tuesdays."* So group chats produce politeness, drift, and the loudest person's preference. Halves negotiate; **only the answer surfaces**; nobody says the humiliating thing and the group gets an honest outcome.

Same primitive serves scheduling, destination choice, task division, compatibility, hiring, co-founder fit, and "who in this hall should I talk to."

## The core asymmetry

> **Half reasons over everything. Half discloses almost nothing.**

A questionnaire matches on what people are willing to *state*, which is why every dating product matches curated self-presentations. **Half can match on what neither person would ever put in a profile, and disclose only the verdict.** Nothing else can do this — and every guard below exists to keep that asymmetry from leaking.

---

## The spine

### Rule 0 — Peer whitelist
No Half responds to any external request — another Half, an API, anything — unless it originates from a Half whose connection its main explicitly approved. Whitelist of **peers** first, whitelist of **questions** within each.

### Rule 1 — No push channel
A Half never volunteers anything. It answers a typed question under a mandate. **Half never "shares information"** — it answers bounded questions. You cannot leak what you were never asked.

### Rule 2 — Scope by question, not by data or by intent

This is the central decision. Data-scoping (*"you may share my calendar"*) is unauditable; intent-scoping (*"for planning a trip"*) is infinitely stretchable; per-question approval is unusable UX.

**The protocol defines a closed set of typed questions with typed answers.** A mandate authorises *which question types* a peer may ask, and for how long.

The property that makes it safe: **a typed Q/A has a provable leakage ceiling.** *"Can you do the 14th?"* → `yes` / `no` / `costly` is under two bits. That is auditable. A sentence is not.

**Corollary — reject free-form Half-to-Half negotiation.** Two LLMs conversing freely is exactly where prompt injection, social engineering and drift produce leaks nobody can detect afterwards. A protocol whose safety depends on both agents behaving well is a *convention*, not a protocol. A closed vocabulary means a badly built or hostile Half **cannot express** the leak.

### Rule 3 — Answer in the coarsest form that resolves the question
Never *"no, therapy."* Never *"no, and here's why."* The wire format must be incapable of carrying a reason. **Make the leak unexpressible, not merely forbidden.**

### Rule 4 — Mandates are symmetric by default
**You may only ask what you are willing to be asked.** Self-limiting, obviously fair, and it makes over-asking socially expensive with zero enforcement machinery.

### Rule 5 — Halves never initiate to each other; Halves initiate to their own mains
Absence of conversation stalls a great many human things — two people who'd both like to meet and neither starts. Half A notices and messages **its own main**: *"you two keep almost making this happen — want me to draft something?"* One-tap draft, main sends, human to human. The no-push rule holds at the protocol boundary; initiation lands in the human layer where it belongs.

---

## Question types

The vocabulary **is** the protocol. Versioned, extensible only by spec revision — never by agents inventing questions (the SMTP-verb / HTTP-method / DNS-record-type pattern), which is also what lets non-Half agents speak it.

Grouped into **3–4 human-legible bundles**, not thirty toggles. The mandate renders as one sentence — *"Priya's Half can ask about your availability for the next three months"* — and the first connection defaults to the **narrowest** bundle, widened later, in context, once.

**The mutual-willingness probe** — among the most valuable in the spec:

> *"Would your main welcome an invitation from mine?"* → `yes` / `no` / `not now`

What stops people initiating is not effort, it's the **risk of unwanted contact**. Critical property: **when the answer is `no`, neither main is ever told a question was asked.** Half A simply doesn't nudge. Nobody was rejected, because nobody knew they were asked. *"Only the answer surfaces"*, applied to social risk.

## Derived answers (compatibility, fit, resonance)

A few typed yes/no answers can't find meaningful links for *"how well would I resonate with a life partner."* These answers are **derived** from everything a Half knows — which means the answer itself carries information about its inputs. Three guards:

1. **Coarse, rate-limited, non-repeatable.** Buckets, never numbers (*"strong / mixed / difficult on money"*, never `73.4%`). A second ask with variations must be **unexpressible**, or variation-triangulation recovers the private inputs.
2. **Symmetric simultaneous delivery.** Both mains receive the same answer at the same moment. **You cannot mine someone without paying the identical disclosure.** Structural — needs no enforcement.
3. **The answer's subject is the dyad, never a person.** *"You two would struggle on money"* is expressible. *"He's financially reckless"* is not — the type cannot form it, whatever the Half concluded privately.

**Every derived answer states what Half could not see.** Not a footer disclaimer — part of the answer: *"I don't know what you two have already talked about."* Half is probably unaware of most conversations between two people, and the worry may already be resolved between them. Naming the blind spot hands interpretation back to the only people holding the missing data.

**Half is explicitly non-authoritative** — a stated property of the spec, not a matter of tone. It can be wrong. The mains own their lives.

### Actionable, never predictive

> *"You break at month eight"* — a prophecy. Unfalsifiable, potentially self-fulfilling, useless to act on.
> *"Money is the thing you two haven't talked about"* — an invitation to a conversation.

Same finding. And this is the tension framing law from person-epistemics applied at the boundary: **name the gap, never render the verdict.**

It also kills the dystopia at the root. *"The compatibility score nobody asked for"* required a score. A topic-not-discussed cannot be aggregated into a rating about a person; a percentage can. **The protocol never emits a score — the type does not exist.**

## Inherited laws (non-negotiable)

- Only **derived judgments** cross. Never raw memory.
- **Constraints, never verdicts** about a third party. *"I'd prefer a smaller group"* yes; *"nobody likes Rohit"* never.
- Halves **propose**, mains **commit**.
- Only a person's **own** Half may tell them how they land on others.

## Why it is v2, not v1

It needs a network that doesn't exist, a protocol nobody has written, and the third-party law enforced perfectly on day one. It cannot be tested below three real Halves. **Build the thing that makes one Half worth having first.** H2H is what v2 is *for*.

## Open questions

1. **The vocabulary itself** — the actual list of question types per bundle. This is the remaining spec work.
2. Transport, identity and revocation — how a Half proves it is who it claims, and how a mandate is revoked in flight.
3. The adversarial Half — an agent built solely to extract signal. The closed vocabulary is the main defence; is it sufficient?
4. Group topology — three-plus parties, and whether pairwise mandates compose safely into a group negotiation.
5. Expunge across the boundary — a belief deleted after a derived judgment already crossed.
6. Non-Half participants — how a plain human or a foreign agent joins a negotiation.
