---
title: 'Story 7 — The demonstration'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: '7a65dbf'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-2 asks for one OAuth, no forms, and one true, specific, falsifiable statement about the main inside ninety seconds. Every piece exists — ingestion, derivation, independence, the ladder, the voice — and none of them is joined to the next. There is no first run.

**The conflict this story resolves, which is real and load-bearing.** A derived claim is born `behave`; only `assert` is quotable; and `assert` requires a receipt **and** `known_to_main`, which is written only by a promotion the main took part in. So on day one Half can state nothing it derived. CAP-2 resolves it in its own success criterion — *"the statement is **confirmed as true**"* — and that confirmation **is** the ladder's acknowledgement event. The demonstration is therefore **offered for confirmation, not asserted**, and the main's answer is what promotes it. The two capabilities were built to fit; nobody had joined them.

**The consequence, and the story's sharpest risk.** To confirm a claim the main must see its words, and its words are not quotable yet. This needs a **second bounded exception to AD-18**, on the same argument as story 12's correction reply: the main is being asked to verify, and verification requires the wording. The first such exception shipped **unbounded** and 13b's review found it — a proposal route put a `behave` claim on the wire on a turn where nothing had been removed. This one is bounded in both directions from the start, with the negative half wired rather than structurally excluded.

## Boundaries & Constraints

**Always:**
- **Offered, never asserted.** The demonstration presents one derived claim for confirmation. It is not a statement Half is licensed to make, and nothing about it promotes anything until the main answers.
- **The confirmation is the acknowledgement.** A main who confirms causes `promote(..., acknowledged=True)` through the ladder's own door; a main who denies causes a correction through story 12's, not a silent discard. Neither path invents a new way to move a rung.
- **The AD-18 exception is bounded in both directions.** The claim's wording reaches the wire on the demonstration turn and on no other, and the negative half of that assertion runs **with the demonstration wired** — 13b's review found the first exception's negative half was tested with the feature switched off, which excluded the route it was meant to bound.
- **One claim, not a digest.** Exactly one is offered. A list is a form, and CAP-4 forbids forms.
- **Falsifiable or nothing.** The claim must be one the main can check today. 15a's gates already refuse the unfalsifiable; a demonstration that cannot be wrong fails CAP-2 even when it reads well, and silence is better than a pleasantry.
- **No forms, no interview, no questionnaire** (CAP-4). One OAuth is the only thing asked for.
- **Ninety seconds is a budget, and it is measured.** Ingestion, four gate calls per message, independence and composition all cost; the story asserts the path fits rather than assuming it, and says what it does when it does not.
- **The main is told their messages leave the machine**, plainly, before the source is connected — not in a footer. This is the moment that sentence exists for.
- Crisis owns the inbound path here as everywhere (AD-10), and a main in the mode is not demonstrated to.

**Ask First:**
- Any third exception to AD-18, or any widening of this one.
- Any change to the ladder, to `promote`, or to what the gates admit.
- Any runtime dependency beyond the standard library and pinned SDKs.

**Never:**
- No statement of a derived claim as fact before the main has confirmed it.
- No form, no questionnaire, no interview, no list of claims.
- No unfalsifiable claim offered, and no pleasantry substituted when there is nothing to offer.
- No promotion by any path but the ladder's, and no correction by any path but story 12's.
- Do not change the ladder, the gates, or the crisis path.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| The demonstration | One OAuth, a mailbox with independent support | One claim offered for confirmation, in prose | CAP-2 |
| Confirmed | The main says yes | Promoted through the ladder's door, `acknowledged=True` | CAP-2's own criterion |
| Denied | The main says no | A correction through story 12's door | Never a silent discard |
| No answer | The main says nothing | Nothing promoted, nothing corrected | Silence is not consent |
| Nothing to offer | No claim clears the gates and independence | Half says so plainly; no pleasantry | Better than a lie |
| Only one cluster | Support from a single thread | No claim — 15b's rule, unchanged | CAP-3 |
| Unfalsifiable | A claim that could not be wrong | Refused by 15a's gate; not offered | CAP-2 |
| One, not many | Several claims qualify | Exactly one is offered | A list is a form |
| The wording | The demonstration turn | The claim's words reach the wire | The bounded exception |
| No other turn | Any turn that is not the demonstration | That wording does not reach the wire | Asserted **with the feature wired** |
| Told first | Before the source is connected | The main is told their messages leave the machine | Plainly, not in a footer |
| Ninety seconds | The whole path | Measured and asserted, not assumed | Says what it does when it does not |
| In crisis | The mode is open | No demonstration; the crisis path owns the turn | CAP-12, AD-10 |
| Provider absent | No deriver or composer wired | No demonstration, no crash | Never fatal |
| Re-run | Onboarding twice | Idempotent; no second promotion, no duplicate claim | N/A |
| Any script | A mailbox in any language | Demonstrated; no English rubric, no locale | Worldwide |
| Nothing durable | Any demonstration | No body persisted, no generated text logged | AD-22, story 3 |
| Replay | The onboarding log | Folds identically | AD-4, AD-30 |

</frozen-after-approval>

## Code Map

**Contract** — the three files in frontmatter `context` are binding. CAP-2, CAP-3, CAP-4, CAP-5, CAP-10, CAP-12, CAP-13, AD-10, AD-11, AD-18, AD-20, AD-22, AD-30 govern this story.

**Reference (extracted from the manifest):** check for a row naming story 7 or onboarding. Story 3 deferred the interactive OAuth consent flow to this story — read what it recorded.

**Existing, reused:** `half/ingest/` (the pipeline, scrub, independence), `half/derive/` (15a's gates, 15b's revealed derivation), `half/governance/ladder.py` (`promote`), `half/correction/` (story 12's door), `half/voice/` (the composer), `half/crisis/gate.py`, `half/channel/`, `half/config.py`.

**To create:**
- `half/onboard/flow.py` — the demonstration: connect, ingest, derive, offer one, and route the answer.
- `half/onboard/consent.py` — what the main is told, and when, before a source is connected.
- `tests/test_onboard.py`.

**To change:**
- `half/context/build.py` — the second bounded AD-18 exception, bounded in both directions.
- `half/__main__.py` — the onboarding entry point.
- `.github/workflows/ci.yml` — a CAP-2 gate, per-case marks, margin stated.

## Tasks & Acceptance

**Execution:**
- [x] `half/onboard/consent.py` -- told before connected, plainly -- the launch blocker's own moment
- [x] `half/onboard/flow.py` -- one OAuth, ingest, derive, offer exactly one -- CAP-2
- [x] the confirmation routes to `promote`; the denial to story 12 -- no new rung-movers
- [x] `half/context/build.py` -- the bounded exception, negative half wired -- AD-18, 13b's lesson
- [x] the ninety seconds -- measured and asserted -- CAP-2
- [x] `tests/test_onboard.py` -- every matrix row -- I/O matrix
- [x] `.github/workflows/ci.yml` -- the gate, per-case marks -- the floor lesson

**Acceptance Criteria:**
- Given one OAuth and a mailbox with independent support, when onboarding runs, then exactly one falsifiable claim is offered for confirmation, in prose, with no form anywhere on the path.
- Given the main confirms, when the turn completes, then the claim is promoted through the ladder's own door with `acknowledged=True` and by no other path.
- Given the main denies, when the turn completes, then a correction is appended through story 12's door and nothing is silently discarded.
- Given nothing clears the gates and independence, when onboarding runs, then Half says so plainly and offers no pleasantry.
- Given any turn that is not the demonstration, when the wire is read, then the claim's wording is absent — **asserted with the demonstration wired**, so the route is inside the assertion.
- Given the whole path, when it is timed, then it fits ninety seconds — measured, with the number recorded and the behaviour stated for when it does not.
- Given a main before their source is connected, when the flow runs, then they have been told plainly that their messages leave the machine.
- Given onboarding run twice, when the log is read, then nothing is promoted twice and no claim is duplicated.
- Given the full suite, when it runs, then it passes offline with the provider stubbed and no network.

## Design Notes

**Why this was blocked and is not.** Reading the ladder, CAP-2 looks impossible: nothing derived is quotable on day one, and the promotion that would make it so needs the main. Reading CAP-2's success criterion resolves it — *confirmed as true* is the acknowledgement, and the demonstration is the event that earns it. That is the ladder working as designed rather than an exception to it: `behave` is where a derived claim starts, and the main's own answer is the only thing that has ever been allowed to raise it.

**Why the second AD-18 exception is the risk.** The first one — story 12's correction reply — shipped with its negative half tested against a runtime that had **no classifier wired**, which structurally excluded the route the assertion claimed to bound. 13b's review found it. The same mistake here would put derived claims about a stranger's mail on the wire on turns that have nothing to do with onboarding. So: the negative half runs with the demonstration wired, and the bound is a property of what the builder is handed rather than a branch it takes.

**Why ninety seconds is a real constraint and not a slogan.** One OAuth triggers a mailbox pull, four gate classifications per message, an independence pass and a composition. 15a already records that four calls per message is the second recurring spend in the product, and neither it nor 15b has a batch seam. Ninety seconds may not fit, and the honest outcomes are to measure it, say what it does when it does not, and record the gap — not to quietly demonstrate on three messages and call it onboarding.

**What a reviewer should be hardest on.** The negative half of the AD-18 bound, wired; and that a denial reaches story 12's door rather than a local discard, since a discard would lose the one correction a main is most likely to make.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all tests pass, no network
- `cd half && uv run --extra dev pytest tests/test_onboard.py -q` -- expected: the demonstration passes
- `cd half && uv run --extra dev pytest -m ad18 -q` -- expected: the two-channel split unbroken
- `cd half && uv run --extra dev pytest -m cap12 -q` -- expected: the crisis path untouched
- `cd half && uv run --extra dev pytest tests/test_scrub.py tests/test_ingest.py -q` -- expected: story 3 unmoved
- `cd half && git status --porcelain` -- expected: clean tree after commit
