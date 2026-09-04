# Review — Verification Audit

**Lens:** Was every committed decision web-researched or reality-checked, rather than asserted from training data?
**Target:** `ARCHITECTURE-SPINE.md` (Half v1)
**Verdict:** PASS with three fixes applied.

## Verified — evidence on record

| Claim | How verified | Result |
| --- | --- | --- |
| SQLite FTS5 available in stdlib `sqlite3` | Executed locally: `CREATE VIRTUAL TABLE … USING fts5` | Present, SQLite 3.51.0 |
| `bm25()` ranking available | Executed locally against an FTS5 table | Present — no third-party dep, no build flags |
| python-telegram-bot current stable | Web + PyPI JSON API | 22.8 |
| WhatsApp Cloud API Graph version | Web (Meta developer docs) | v21.0 current, v23.0 in development |
| Webhook 5-second / 5-failure rule | Web (Meta webhooks docs) | Confirmed — drove AD-23 |
| Anthropic model pricing and tiers | `claude-api` skill's cached table | Haiku 4.5 $1/$5, Sonnet 5 $2/$10, Opus 5 $5/$25 per MTok |
| Batch API 50% discount | `claude-api` skill | Confirmed — drove AD-9 |
| hermes-agent license (asserted MIT in AD-6) | Read `hermes-agent/LICENSE` | MIT, © 2025 Nous Research — attribution requirement is real and now specific |
| `anthropic` Python SDK | PyPI JSON API | 1.2.0 |
| `httpx` | PyPI JSON API | 0.28.1 |

## Findings

**F1 — Unpinned Stack rows (HIGH).** Three rows read "current" rather than a version: `anthropic`, `httpx`, `uv`. The Stack table is seed, but "current" is not a pin and defeats the table's purpose.
**Fixed:** pinned `anthropic 1.2.0` and `httpx 0.28.1` from the PyPI JSON API. `uv` is a developer tool rather than a runtime dependency and is stated as such rather than pinned.

**F2 — Batch API turnaround treated as known (MEDIUM).** AD-9 leans on "~11h of slack" against an unstated turnaround SLA. The 8pm-submit / 7am-deliver design is sound, but the margin was reasoned rather than measured.
**Not auto-fixed — recorded as an assumption.** The mitigation already exists in the rule (a missed window sends nothing), so the risk is bounded to a lost morning surface, not a failure.

**F3 — hermes-agent attribution was generic (LOW).** AD-6 said "MIT, carry attribution" without naming the copyright holder.
**Fixed:** AD-6 now names Nous Research, 2025, so the notice can actually be reproduced.

## Not a finding

Object storage is specified as "S3-compatible" behind the `SourceStore` port rather than as a named product — correct at spine altitude; the port is the invariant and the vendor is not.
