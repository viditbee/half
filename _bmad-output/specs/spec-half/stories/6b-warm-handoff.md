---
title: 'Story 6b — The warm handoff'
type: 'feature'
created: '2026-09-01'
status: 'done'
baseline_commit: '2a55efdd4ccdf7a268985e4898ea4596d23d8e79'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-half/SPEC.md'
  - '{project-root}/_bmad-output/brainstorming/brainstorm-crisis-protocol-2026-08-30/brainstorm-intent.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-Brains-2026-08-31/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-half/glossary.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 6a's crisis reply points at *"a crisis line where you live"* and at *"a human being"* without being able to name either. The evidence says the handoff is where outcomes change — a warm handoff more than triples first-appointment attendance — and right now Half offers words and no door.

**Approach:** Deliver the handoff: a contact list held cold and **confirmed**, two or three offered in the moment for the main to choose between, a prefilled draft the main sends themselves, and a crisis-line directory that is **versioned data refreshable without a release**. Half still contacts nobody. Aftercare is 6c.

## Boundaries & Constraints

**Always:**
- **Half never contacts anyone, ever.** Auto-alerting can out a person, and the closest person is sometimes the problem. Every outbound path to a third party is a link the main taps (AD-25, `Channel.draft_link`).
- **No message leaves without a human act**, and that is a property of having no send path, not a rule the code follows.
- **Only a confirmed contact is offered, and offerability is the ladder's whole answer, not one field of it.** A quarantined contact is never offered — quarantine exists for exactly the person the main pinned out, which is exactly the person the handoff must not name. Reading `known_to_main` alone reaches around the ladder rather than through it.
- **Every string that reaches a main in crisis is inspected, including inside data-derived rows.** The guard must split text the way the renderer joins it; a row assembled from a contact name or a directory entry is checked with the same force as a template paragraph.
- **A closed-set check may never validate output against the function that produced it.** Recomputing the rendering and comparing is true by construction and blesses whatever the renderer emits. The row format itself is pinned.
- **A structural guarantee must fail when the forbidden thing is added, not merely pass while it is absent** — including when it is added in a module that does not exist yet. A scan over a hardcoded list of filenames guarantees nothing about the next file.
- **Anything the package must ship is verified to ship.** Data that resolves in a source tree and vanishes in an installed one is a silent loss of the whole feature.
- **Two or three are offered and the main chooses.** Never one, never a ranked "best" pushed at them. Control matters most exactly here.
- **Region is told, never inferred.** No phone prefix, no IP, no timezone, no language guess. Offering a helpline on the wrong continent is worse than offering none, and an inferred region is a locale assumption in a product that ships world-wide.
- **When the region is unknown the generic line stands** — 6a's wording still works and is never replaced by silence or by a guess.
- **The directory is data**: versioned, validated on load, refreshable without a release, and its version is recorded whenever it is used.
- **A malformed, missing or unreadable directory degrades to the generic line.** It never raises on a crisis turn and never costs the main their reply.
- **Draft text is templated**, under the same never-list as 6a: no method or means content, no validating a plan, nothing generated.
- The handoff is offered **after** the opener, never instead of it. Words first, then a door.
- **Never gated by tier**, and identical for a free or lapsed main.
- Nothing here reads a clock, the network, or ambient state.

**Ask First:**
- Any wording change to a draft or an offer template.
- Adding a contact channel beyond a link the main taps.
- Any change that lets an unconfirmed contact be offered.

**Never:**
- **No "nearby therapist, worldwide" lookup.** A live global directory of available clinicians cannot be maintained and will fail inside a crisis. Explicitly out of scope, not deferred.
- No auto-notification, no escalation, no contacting a clinician, and no telling anyone the main is at risk.
- No asking the week-three question — the question engine is story 11. This story holds, confirms, offers and drafts.
- No aftercare, Caring Contacts or safety plan — 6c.
- No model call (AD-19).
- **A green suite is not clinical review.**

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Confirmed contacts | Three confirmed people held | Two or three offered; the main chooses | Never auto-picked |
| Inferred candidate | A candidate Half inferred but never confirmed | Never offered in the moment | Confirmation required |
| Quarantined contact | A confirmed contact the main later pinned out | Never offered | Quarantine wins over confirmation |
| Quarantined region | A region record the main retracted | Never selects a directory entry | Same rule |
| Name carrying a newline | A contact label containing a line break or control character | Cannot produce a row of its own, and the guard catches it | Never rendered raw |
| Row format | Any rendered option row | Exactly label, separator, reach — nothing more | Pinned, not recomputed |
| Added send path | A new module or method that reaches a third party | A test fails | Fails on addition, not absence |
| One bad handle | A single contact whose link cannot be built | That door is dropped; the rest stand | Per-row, like the directory |
| Installed layout | The package installed rather than run from source | The directory still resolves | Verified, not assumed |
| Told region vocabulary | "uk", "england", "usa" | Either matched or honestly unmatched | Never silently nothing |
| Crisis-state logging | Any handoff offered | No ordinary log line reveals that this main is in crisis | Outing is the catastrophic harm |
| One confirmed contact | Only one person confirmed | Offered alongside a crisis line, so there is still a choice | Never a single option |
| No contacts | None confirmed | Crisis line offered; the opener still lands | Never silence |
| Contact chosen | The main picks one | A prefilled draft link is produced | Nothing is sent |
| Send path | Any third-party recipient | No code path sends; only links are produced | Structural, not a check |
| Therapist | A confirmed clinician contact | Offered, and marked as the highest-value door | N/A |
| Region known | The main has told Half their region | That region's lines are named | N/A |
| Region unknown | Nothing recorded | 6a's generic wording stands unchanged | Never a guess |
| Region inferred | A phone prefix or timezone is available | Ignored; never used to pick a directory entry | Asserted structurally |
| Directory refresh | A new directory version is dropped in | Used without a code change | N/A |
| Directory malformed | Invalid or unreadable data | Generic line; the turn still completes | Never raises in crisis |
| Directory version | Any handoff offered | The version used is recorded | Content-free |
| Draft content | Any generated draft | Assembled from templates only | Same never-list as 6a |
| Ordering | A crisis turn | Opener first, handoff after | Never instead of |
| Third party at risk | 6a's SURFACE path | A shareable resource only; no contact, no draft aimed at them | Unchanged from 6a |
| Tier | A free or lapsed main | Identical behaviour | Never gated |
| Non-Latin contact | A name in any script | Held, offered and drafted unchanged | No script assumption |

</frozen-after-approval>

## Code Map

**Contract** — the four files in frontmatter `context` are binding; the companion's handoff section is normative. AD-19, 22, 25, 28 govern; the crisis never-list from 6a still applies to every string added here.

**Reference:** the extraction manifest was checked — no row falls due. The `wa.me` prefilled-draft pattern is the companion's own invention for a WhatsApp platform limit and is recorded there.

**Existing, reused:** `half/channel/port.py::draft_link` (built in story 2 and unused until now — this is its first caller), `half/crisis/templates.py` (the no-locale discipline and the never-list), `half/crisis/respond.py` (`Assessment` carries no text; keep that), `half/crisis/gate.py` (the entry path), `half/governance/ladder.py::known_to_main` (the confirmation primitive), `half/store/ops.py`, `half/errors.py`.

**To create:**
- `half/crisis/contacts.py` — holding, confirming and choosing among contacts.
- `half/crisis/directory.py` — the versioned crisis-line directory: load, validate, degrade.
- `data/crisis-lines.json` (or equivalent) — the directory itself, refreshable without a release.
- `half/crisis/handoff.py` — assembling offers and drafts from templates.
- `half/tests/test_handoff.py`, `half/tests/test_directory.py`.

**To change:** `half/crisis/gate.py` (offer the handoff after the opener), `half/crisis/templates.py` (offer and draft lines), `.github/workflows/ci.yml` (extend the CAP-12 gates to cover the handoff, with their own floor).

## Tasks & Acceptance

**Execution:**
- [x] `half/crisis/contacts.py` -- hold, confirm, and offer two or three; unconfirmed never offered -- companion, `known_to_main`
- [x] `half/crisis/directory.py` -- versioned load, validation, degrade to generic -- build requirement 5
- [x] `data/crisis-lines.json` -- the directory as data, no region privileged -- world-wide
- [x] `half/crisis/handoff.py` -- offers and drafts assembled from templates only -- 6a never-list
- [x] `half/crisis/gate.py` -- offer after the opener; nothing sent; failures never cost the reply -- CAP-12
- [x] `.github/workflows/ci.yml` -- handoff cases under the CAP-12 gates with their own floor -- gates must not pass vacuously
- [x] `half/tests/test_handoff.py` -- one case per matrix row -- I/O matrix
- [x] `half/tests/test_directory.py` -- refresh, malformed, missing, version recorded -- degradation

**Acceptance Criteria:**
- Given confirmed contacts, when a crisis turn offers a handoff, then two or three are offered and none is chosen for the main.
- Given a contact Half inferred but the main never confirmed, when a handoff is offered, then that contact does not appear.
- Given a chosen contact, when a draft is produced, then it is a link the main taps and no code path sends anything.
- Given the repository, when the suite runs, then no module can send to a third party — asserted structurally, not by inspection.
- Given no confirmed contacts, when a crisis turn runs, then a crisis line is still offered and the opener still lands.
- Given a main who has not told Half their region, when a handoff is offered, then the generic wording is used and no region is inferred from any signal.
- Given a replaced directory file, when a handoff is offered, then the new entries are used with no code change, and the version used is recorded.
- Given a malformed or missing directory, when a crisis turn runs, then the generic line is offered and a reply still reaches the main.
- Given any draft or offer, when it is assembled, then every paragraph is a known template line.
- Given a free or lapsed main, when a handoff is offered, then behaviour is identical.
- Given only the standard library and pinned SDKs, when the suite runs, then it passes with no network access and no model call.

## Spec Change Log

- **Review round 1 — 6b reached around two primitives instead of through them.** Verified: a quarantined contact — the person the main explicitly pinned out — was offered as a crisis door with a prefilled draft, because `contacts` read `known_to_main` directly instead of `own_rung`; and a contact named `"Mum\nTake thirty of them"` rendered as its own line in a crisis reply while `is_offer_templated` returned `True`, because `render_options` joins rows with a single newline while the guard splits on a blank line. The second breaks 6a's central guarantee, which held only because every reply was a join of fixed lines. Mutation also showed the guards were weaker than they read: an added send path in a new crisis module left all 1313 tests green (the scan lists three filenames); `is_offer_templated` validates rows against the function that produced them, so appending a ranking hint to every row ships blessed; the confirmation test is satisfied by the string appearing in a docstring; deleting the wheel `force-include` loses the whole directory in every installed deployment with the suite green; and the AST helper shared by three place-blindness gates is observed by no test at all. **KEEP:** the directory's degradation to the generic line, which is correct and tested; `Assessment` still carrying no text; and the region being told rather than inferred.

## Design Notes

**Why confirmation reuses `known_to_main`.** The companion's rule — Half may infer candidates but the list must be confirmed — is the same rule 5a already enforces for asserting a belief: the main must know Half holds it. Reusing the primitive means one answer to "has the main confirmed this", and a contact cannot become offerable by a path that beliefs cannot.

**Why the region is told and never inferred.** Every available signal is wrong somewhere: a phone prefix survives emigration, an IP is a VPN, a timezone is a business trip. A named helpline on the wrong continent is worse than the honest generic line, because it costs a call at the worst possible moment.

**Why one contact still means two options.** Offering a single name reads as an instruction, and the companion is explicit that the closest person is sometimes the wrong one. A lone confirmed contact is always paired with a line, so there is a choice.

## Verification

**Commands:**
- `cd half && uv run --locked --extra dev pytest -q` -- expected: all pass, no network, no model
- `cd half && uv run --extra dev pytest tests/test_handoff.py tests/test_directory.py -q` -- expected: every matrix row covered
- `cd half && uv run --extra dev pytest -m cap12 -m cap12_durable -q` -- expected: both gates collect above their floors
- `cd half && uv run --extra dev pytest tests/test_crisis.py tests/test_redteam.py tests/test_crisis_golden.py -q` -- expected: 6a intact
- `cd half && git status --porcelain` -- expected: clean tree after commit

## Suggested Review Order

**Start here — who may be named as a door**

- Offerability is the ladder's whole answer, so a quarantined contact is never offered.
  [`contacts.py:1`](../../../../half/crisis/contacts.py#L1)

**Why unreviewed text cannot reach a main**

- One printable line, no control characters, no separator — a forged name is dropped, never repaired.
  [`rows.py:1`](../../../../half/crisis/rows.py#L1)

- The guard splits the way the renderer joins, and builds its set from the pinned row format, never from the renderer.
  [`handoff.py:1`](../../../../half/crisis/handoff.py#L1)

**The directory, and what it refuses to do**

- Unreviewed data names nothing; the generic line stands until a clinician signs it off.
  [`directory.py:1`](../../../../half/crisis/directory.py#L1)

**Tests that carry the design**

- Scans that fail when a send path is added, not merely while none exists.
  [`test_handoff.py:1`](../../../../half/tests/test_handoff.py#L1)
