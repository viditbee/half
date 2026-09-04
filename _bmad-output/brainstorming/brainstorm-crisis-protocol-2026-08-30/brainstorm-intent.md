# Crisis Protocol — Intent

**Source:** deep-dive #2 from the Half session, 30 Aug 2026 (21 entries). Full record: `.memlog.md`.
**Parent:** `../brainstorm-half-2026-08-27/brainstorm-intent.md`
**Status:** converged. v1 MUST — ship-blocking.

> **This subsystem is grounded in published guidance, not invented.** Where this document states clinical practice it cites a source. Anything not covered here must be resolved against real guidance or a qualified reviewer — **not** by design intuition. A qualified clinical review before launch is a requirement, not a nicety.

---

## Why it is different from every other part of Half

The two failure headlines are **opposite**, and every mitigation for one is a mechanism for the other:

- **Commission** — *"Half led him to take this extreme step."* Half treated a crisis disclosure as ordinary input, engaged with content, possibly agreed (the sycophancy gradient points that way), possibly retrieved something true and terrible at the worst moment.
- **Omission** — *"Half didn't respond when it was most required."* The unsaid queue held. The interrupt law found nothing irreversible. Half was being *careful* — the virtue the whole product is built on — and the carefulness was the harm.

**Common root:** in both cases Half was still running its normal architecture. So crisis is **not a special input to the ordinary system.** It is a separate mode entered *before* any normal machinery touches the message.

## Half's actual role

> **Not a counsellor. The warm handoff.**

A **warm handoff** — a personal introduction to a human rather than a phone number — **more than tripled** the odds of someone attending their first appointment ([Pew](https://www.pew.org/en/research-and-analysis/articles/2025/08/28/continuing-care-is-an-essential-part-of-suicide-prevention), [Zero Suicide](https://zerosuicide.edc.org/toolkit/transition/best-practices)). In the reported [NPR case](https://www.npr.org/2026/08/18/nx-s1-5929575/ai-suicide-risks-mental-health), a documented failure was never helping her tell her therapist or her parents.

A generic chatbot can only produce a phone number. **Half knows who your people are.** The intervention with the strongest evidence behind it is exactly the one Half's memory makes possible and nobody else's can.

**Positioning: Half is the shortest path to a human who loves you.**

**Build the friend, not the therapist.** The therapist half is where the documented harms come from. Half can be an extraordinary friend — perfect memory, infinite patience, your phone book — and that is defensible and safe.

---

## 1. The switch

**Threshold is set by asymmetry, not by the trust economy.** A false positive costs a moment of awkwardness that a caring friend also produces. A false negative is unrecoverable. Two facts make erring toward response cheap:

- **Asking directly about suicide does not increase risk** — well established, and the fear that it does is what makes builders ship silence.
- A false positive in Half's voice is *"I might be reading this wrong, and I'd rather ask"* — which is what a good friend does.

**Signals, tiered:**

| Signal | Action |
|---|---|
| Explicit disclosure by the main | Enter mode |
| Main seeking external help (call/SMS/email to a line or clinician) | Enter mode, gently |
| **Safe word** — a phrase the main can type any time ([UNICEF Safer Chatbots](https://www.unicef.org/documents/safer-chatbots)) | Enter mode, no detection required |
| Third-party mention (a friend's message about the main) | Raise vigilance. **Never** trigger alone |
| Sudden behaviour change | Raise vigilance. **Never** trigger alone |

**Exception to the license ladder:** everywhere else in Half, gut licenses `ask` and never `assert`. Here gut licensing `ask` is *mandatory* — Half must be willing to ask on inference alone.

## 2. The moment

**Half breaks character.** Guidance requires the agent to state plainly that it is a machine and redirect toward humans and crisis lines. For a product whose identity is being your other self, this is the one deliberate exception — *"I'm software. You need a person, and I'll help you reach one right now."* Built on purpose, not discovered in production.

**Every other rule inverts:** trust currency void · unsaid queue bypassed · face dissolved · interrupt law suspended (irreversibility is total) · mirror off · loops silent.

**Never:**
- Provide or engage with **method or means** information. Documented chatbot failures include naming the nearest bridge, lethal dosages, and how to tie a noose ([Psychiatric Times](https://www.psychiatrictimes.com/view/making-chatbots-safe-for-suicidal-patients), [Scienceline](https://scienceline.org/2026/04/mental-health-chatbots-struggle-suicide-warning/)).
- **Validate suicidal intent.** Validate the *pain*, never the plan. This is the most common and subtlest failure.
- Diagnose, counsel action, sensationalise, or minimise.
- Retrieve from the ledger. Nothing true about the main's past is safe to surface here.
- Go quiet.

**Do** (per [#chatsafe](https://www.orygen.org.au/chatsafe), Orygen, Delphi consensus, 25 languages): be present and focused · express empathy · acknowledge the difficulty · **thank them for telling you** · stay.

## 3. The handoff

**Half never contacts anyone on its own.** Auto-alerting can out someone or escalate a situation where the "closest person" *is* the problem.

> **The one-tap prefilled `wa.me` draft — invented for a WhatsApp platform limitation — is the warm handoff.** Half writes the hardest message a person will ever send. The main presses send.

No message leaves without a human act; agency stays with the main; the platform constraint is cleared.

**The list is built cold**, months before it is needed, by one ordinary question asked in week three of a normal relationship:

> *"Who's the person you'd call first if something went wrong?"*

Never an "emergency contacts" form — alarming, wrong register, skipped. Half may *infer* candidates (who you reply to in three minutes, who you talk about warmly), but the list must be **confirmed**, per the standing rule that the main must know Half holds it.

**Half offers two or three and the main chooses.** Control matters in crisis, and the closest person is sometimes the wrong one.

**Scope honestly:**
- **Crisis lines** — a maintained directory is achievable. India: **Tele-MANAS 14416**, 24/7, free, English + 20 regional languages, tiered counsellor → psychiatrist ([telemanas.mohfw.gov.in](https://telemanas.mohfw.gov.in/)). Elsewhere: a curated set, refreshed.
- **The main's own therapist** — highest-value contact on the list, because that is precisely the connection documented failures missed. *"Want me to draft something to Dr. X?"*
- **"Nearby therapist, worldwide"** — do **not** attempt. A live global directory of available clinicians cannot be maintained and will fail inside a crisis.

## 4. The aftercare

Continuing care is where outcomes are decided, and Half is the only thing in this person's life that will still be there.

**Caring Contacts** — brief, periodic messages of unconditional care and concern over **1–2 years**, with **no demand attached**. Meta-analysis shows a protective effect against suicide attempts; cost-effective; in multiple clinical guidelines; [SPRING RCT](https://clinicaltrials.gov/study/NCT06128239) (n=849) is testing one-way vs two-way. ([MSRC](https://msrc.fsu.edu/blog/caring-contacts-simple-scalable-intervention-reduce-suicidal-ideation-and-attempts/))

This is Half's native behaviour — but it works **because it carries no agenda**, which collides with everything else Half does. Hence:

> **Aftercare mode = caring contacts, with the mirror switched off.**
> For a defined period, **every license drops globally to `behave`.** No loop nudges, no tensions surfaced, no *"you said you'd…"*. One global license ceiling — implementable because licenses are a schema field (see person-epistemics).

**Safety Planning (Stanley–Brown)** — six steps: warning signs · internal coping strategies · social distractions · social contacts · professionals/agencies · restricting access to lethal means ([scoping review](https://www.tandfonline.com/doi/full/10.1080/13811118.2024.2363226)).

**Half must not author one — that is clinical.** Half **holds** one made with a professional and can produce it instantly, which is the entire point: a safety plan in a drawer is useless at 3am. Steps 3 and 4 are literally Half's data. Helping the main recognise their own warning signs — *"this is the third night this week you've messaged after 2am"* — is within competence and may be the most valuable continuing-care function Half has.

**Tone correction:** rushing to fix reads as **minimising** and is counterproductive. Be present, validate, don't hurry it, stay in contact over time. *Patient*, not *fixing*.

---

## Build requirements

1. Crisis mode is entered **before** the normal pipeline — a pre-filter, not a branch inside the agent.
2. The mode must be **testable in isolation** and covered by a red-team suite (the 2026 study used escalating Columbia-Suicide Severity Rating Scale prompts against 29 agents — use the same shape).
3. Ledger retrieval is **hard-disabled** in the mode, not merely discouraged.
4. Safe word is documented at onboarding and never changes.
5. Referral directory is data, versioned and refreshable **without a release**.
6. **Clinical review before launch.** Non-negotiable.
7. Never gated by tier, ever — free users included.

## Open questions

1. Mode **exit** — who decides it's over, and how does the mirror come back without it feeling like surveillance resuming?
2. Aftercare duration — evidence says 1–2 years; what does that mean for a free user, or one who lapses?
3. Two-way vs one-way caring contacts — SPRING will answer this; track it.
4. Minors, and jurisdictions with mandatory reporting duties.
5. What Half does when the *third party* is the one at risk (a friend's message about someone else).
