# Person-Epistemics — Intent & Schema

**Source:** deep-dive #1 from the Half session, 30 Aug 2026 (35 entries). Full record: `.memlog.md`.
**Parent:** `../brainstorm-half-2026-08-27/brainstorm-intent.md`
**Status:** converged. Ready for `bmad-spec` / `bmad-architecture`.

---

## The problem

Evidence epistemics (claude-obsidian's source + claim ledgers) works because claims about **the world** have a truth value, independent sources, and a resolution path. Claims about **a person** break all three:

- *"He wants to buy farmland"* has no truth value — only a **strength** and a **validity window**.
- Sources are not independent. They are all the person, people who know the person, or the person's own traces. Corroboration is mostly **echo**.
- There is no better source. If you said you'd run in March and didn't, nothing resolves it — **nothing is wrong**.

Plus a property no epistemic system has had to handle: **the subject reads the ledger, and can change in response to it.** Observation modifies the observed. The schema must be safe to be read by its own subject.

**The inversion that defines the whole design:** gbrain's contradiction probe exists to *eliminate* contradictions. Half's tension object exists because for a person **the contradiction is the product**. Same detection machinery, opposite purpose.

## Four objects

| Object | What it is | Lifecycle |
|---|---|---|
| **State** | How the main is *right now*. Volatile, cheap, overwritten, expires fast. | Never written to the belief ledger. |
| **Belief** | A durable, evidenced claim about the main. | Asserted → decays in salience → retracted / revised / expunged. |
| **Loop** | An unresolved wanting. The core object of the product. | Transitions state: advancing / stalled / abandoned-but-unadmitted / achieved. |
| **Tension** | A linked pair of entries that disagree and cannot be resolved. | fresh → persistent → **widening** → closing → resolved. |

**No confidence score.** *(Resolved downstream in `SPEC-half`, 31 Aug 2026.)* A claim with no truth value cannot carry a confidence figure honestly, and a number invites false precision the moment it is shown to anyone. The information lives in **support count, independence count, last-corroborated date, and license** — the field is removed rather than defined.

**Mood is not a belief.** Promoting volatile state into the ledger produces *"you've seemed down lately"* when someone had a bad Tuesday. Hard separation.

**Beliefs decay; loops transition.** A wanting is never refuted — it goes quiet, and the going-quiet is the signal. Loops must never run through the belief demotion pipeline.

## The license ladder

Every belief and every tension carries what it **licenses**. **Default is `behave`.**

```
behave  →  ask  →  assert
```

- **`behave`** — Half acts on it silently: softens tone, delays a nudge, drops a suggestion, reorders what surfaces, stays quiet. *Most beliefs never leave this rung.*
- **`ask`** — Half may raise it as a question.
- **`assert`** — Half may state it. Rare and expensive.

Modelled on the dog: it knows your mood and **never says so — it acts on it.** A dog is never harmfully wrong because it never asserts.

**Quarantine** = a belief permanently pinned at `behave`. Not an exception list — a field. Half detects quarantine candidates by inference, because the main will never think to declare it — **a name that goes from daily to zero overnight is a wound, not a forgotten topic** — but never applies quarantine on inference alone; it asks. *(Refined downstream in `SPEC-half`.)* (Failure mode named: not hallucination but **autoimmunity** — correct recognition, catastrophic response. Tolerance is an actively maintained mechanism, per the immune system.)

### Promotion to `assert`

> **A belief may be asserted only if the main already knows Half holds it.**

Because **the danger of assertion is not being wrong — it is being unexpected.** The ex-message failure was Half being *correct*; all the harm lived in the main not knowing Half held it.

| Path | Licenses |
|---|---|
| Half asked it, main confirmed | `assert` |
| Verifiable independent sources (revealed ledger only) | `assert` |
| Half's own inference ("gut") | `ask` — **never** `assert`. Gut generates candidates, never warrants. |
| Long consistent use at `behave` without correction | `ask` at most. **Silence is not confirmation.** |

> **Ledger-split rule: the revealed ledger may be asserted on evidence. The stated ledger may be asserted only on the main's confirmation.** No source can confirm a *wanting*.

Independence still applies: an email and an SMS about the same event are **one** confirmation.

### Demotion

Four verbs, three of which append:

- **`retract`** — *"You changed."* History preserved. No apology; that's growth.
- **`revise`** — *"Half was wrong about you."* Apologise, show the belief removed from the fold.
- **`expunge`** — genuine removal, tombstoned. Rare, main-initiated. Required or the secrets rule and right-to-be-forgotten are unenforceable.
- **decay** — salience falls with disuse. No event needed.

> **Trap to catch in code: evidence of non-action must never refute a wanting.** A bank statement showing no farmland purchase does not demote *"wants to buy farmland"* — that is the revealed ledger disagreeing with the stated one, **which is the product**. Get this wrong and Half deletes the main's dreams because they haven't acted yet.

## Tensions

**Tension is a first-class record, not a derived query** — an edge between two entries with its own lifecycle, salience, and license.

Consequence: **the nightly pass mints tensions.** Consolidation is not summarising; it is discovering new gaps between the stated and revealed ledgers.

**Drift becomes computable:** *"am I moving away from what I said I wanted?"* = **which tensions are widening.** And **loop advancement = tensions closing** — which makes the parent session's metric triad measurable.

> **Framing law: a tension is a fact about a situation, never a verdict about a character.** *"You said X and did Y"* is prosecution. The mirror names the gap without assigning blame — or the tension object becomes the cruelty engine.

## Storage — four layers

**Granularity rule: one file per thing you'd want to open. Log lines for things you'd never open alone.**

```
sources/              immutable, content-addressed, never edited
beliefs/2026-08.jsonl append-only event log, one record per line, month-sharded
loops/*.md            markdown + YAML frontmatter, one file per subject
people/*.md           "
.half/index/          BM25 · embeddings · tension graph — derived, gitignored, rebuildable
```

**JSONL for the log**, not one file per belief: appends never rewrite the file, it diffs line-by-line in git, it streams, and event sourcing wants a log rather than a tree. Plain text and greppable, so the human-readable law holds.

```jsonl
{"t":"2026-08-14T09:12Z","op":"assert","id":"b_7f2","subject":"self",
 "claim":"replies to mother within 3 minutes, consistently",
 "ledger":"revealed","support":["s_a91","s_c04"],"independent":2,
 "license":"behave","last_corroborated":"2026-08-14","loop":null}
{"t":"2026-08-29T22:40Z","op":"tension","id":"x_18","between":["b_7f2","b_3d1"],
 "state":"widening","license":"behave"}
```

```yaml
---
loop: buy-farmland
state: stalled
timescale: years
opened: 2024-11
last_movement: 2026-03-12
tensions: [x_04]
license: behave
---
Wants land near Bir. Raised three times, always in the same breath as
paragliding season. No search activity since March.
```

> **The log is the truth. The markdown is the view.**

Projections regenerate from the log — so export is complete by construction and indexes survive embedding-model churn. v1.x affordance: a hand-edit to a projection is captured as a `retract`/`revise` event on next sync (the pattern gbrain already uses).

**The "wall of one's life" is not a feature to build. It is layer 3, rendered.**

## Open questions

1. Projection conflict — what happens when a hand-edited projection disagrees with the log fold.
2. Expunge and the network — once v2 exists, an expunged belief may already have crossed as a derived judgment.

*Resolved downstream in `SPEC-half` (31 Aug 2026): confidence calibration (field removed), quarantine inference (detection produces a candidate and Half asks — never applied on inference alone), and tension minting cost (bounded to new-or-changed entries against loops and same-subject beliefs, gated by a cheap relevance filter before any model comparison).*
