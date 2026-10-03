# Final validation after validity hardening (2026-10-03)

**Code under test:** `4f827ee7813db166b0c03dabec5c9d61da5b9a99`. Every number below was measured on that commit. Nothing here is an
official score, and no unpublished limit is estimated. Builderr's sample input is not committed: only its
SHA-256 appears, and host lists for its companies are not committed.

**Final submission candidate:** `78d1c2f2be0decbb90311f4827b226752c74f317` (tag `submission-candidate-1`).
`78d1c2f` is code-identical to `4f827ee`. It adds only this directory and the status section of
`docs/official-submission-checklist.md`. No run in this directory was executed on `78d1c2f` itself. See
`docs/final-submission-manifest.md`.

**Smoke test for the final code:** `live-100` below is the 100-company smoke test on `4f827ee`. It has 100 inputs, 100
envelopes and 100 `completed` results, input order is preserved, and validation passed with 0 contract findings.
Runtime was 118.3 s. Peak memory was not recorded in these runs. The last recorded peak RSS figures are 222 MiB for 100
companies (`c5c6a32`, `docs/submission-audit.md`) and 399 MiB for 1,200 companies (`403a9c1`,
`docs/official-submission-checklist.md` §C2). Tests in the clean room on `4f827ee` were 303 passed, 68 subtests passed.
The older smoke test in `measurements/submission-smoke-2026-10-03/` ran on `c5c6a32` and is historical.

**Inputs:**

- **Sample 100:** `out/experiments/sample.jsonl`, SHA-256 `80eb79e6f9beda1d90dfc2fd33ee98c615ffa8adfebcbe87f4bc9d5a08767677`.
- **Unseen 1,200:** `measurements/official-audit-2026-10-03/unseen-1200/input-companies.jsonl`, SHA-256
  `765647dfa755b90f2e1bddc04a0bedf7f894789db887bc7a892a068e1c090850`.

**Command:** `scripts/run_competition_batch.py`, run through `host_audit.py`. The wrapper adds a Python audit
hook that logs every outbound host (`urllib.Request` URLs, `http.client.connect`, `socket.getaddrinfo`).
Settings: 8 workers, no `--bulk` (live registry), `--snapshot-dir` on, `--viewer-output` on. The deadline
was the fail-safe default of 2,700 s, except in the timeout test. All four runs ran back to back on one
machine. `~/.cache/python-tldextract` was deleted first and did not exist afterwards.

**Analysis:** `analyse_run.py` wrote `*/analysis.json`.

## Results

| Check | live-100 | live-1200 | refresh-100 | timeout-100 |
| --- | --- | --- | --- | --- |
| Envelopes / input rows | 100 / 100 | 1,200 / 1,200 | 100 / 100 | 100 / 100 |
| Input order and positions | yes | yes | yes | yes |
| Batch validation, contract findings | passed, 0 | passed, 0 | passed, 0 | passed, 0 |
| `terminal_status` | 100 completed | 1,200 completed | 100 completed | 85 completed, 15 failed |
| `company_status` | 98 complete, 2 partial | 1,162 complete, 38 partial | 97 complete, 3 partial | 7 complete, 78 partial, 15 not_researched |
| Runtime | 118.3 s | 1,117.0 s (18.6 min) | 121.0 s | 38.0 s (deadline 45 s, grace 10 s) |
| Requests (all sources) | 767 | 8,315 | 755 | 440 |
| Duplicate claims | 0 | 0 | 0 | 0 |
| Summaries present / byte-identical on recompute | 100 / 100 | 1,200 / 1,200 | 100 / 100 | 100 / 100 |
| Viewer written | 1.13 MB | 13.4 MB | 1.14 MB | 1.02 MB |
| Birth dates (envelopes, profiles, report, snapshots) | 0 | 0 (6,011 snapshot files) | 0 | 0 |
| Secret-pattern hits | 0 | 0 | 0 | 0 |
| publicsuffix.org / GitHub / Brave / NAV hosts | none | none | none | none |
| LinkedIn / Meta / YouTube / X / TikTok hosts | none | none | none | none |

Area coverage (companies with at least one available fact):

| Area | live-100 | live-1200 | Audit baseline 1,200 (`403a9c1`) |
| --- | --- | --- | --- |
| filings | 100 | 1,200 | 1,200 |
| leadership | 100 | 1,198 | 1,198 |
| locations | 100 | 1,199 | 1,199 |
| websites | 15 | 121 | 121 |
| public footprint | 10 | 77 | 76 |
| hiring | 0 | 1 | 1 |

Coverage is unchanged from the audit baseline. Runtime is 1,117 s against 1,334 s, and requests are 8,315
against 8,773. Live web drift means individual companies differ between runs.

### Refresh (refresh-100 against live-100 profiles)

All 100 companies were compared. Across 3,998 facts, the result was:

| Change type | Count |
| --- | --- |
| added | 0 |
| removed | 0 |
| changed | 0 |
| unverified | 0 |
| unchanged | 3,998 |
| unavailable | 2 |

Both `unavailable` events are one company (929336038), whose site answered with an unreachable robots.txt
(rate limiting) in the second run. Its website and site-research facts were carried forward with their
original evidence and marked `carried_forward`. **There were zero false refresh changes.**

### Timeout (intentional, `--deadline-seconds 45 --grace-seconds 10`)

All 100 rows were emitted in input order, and validation passed. The batch ended after 38.0 s:

- 77 companies were degraded to official-only research (`deadline_degraded`);
- 15 were not started inside the grace window. They are `not_researched`, with terminal status `failed`,
  and the report's `stop_reason` is `grace_window`;
- 0 needed a hard-stop salvage.

Kill safety (SIGKILL early, mid and late; SIGTERM) is covered by real-process tests in
`tests/test_deadline_streaming.py`.

### Clean room

The branch was freshly cloned from GitHub at `4f827ee`, with an empty `UV_CACHE_DIR` and a fresh `HOME`.

- `uv sync --locked`: 111 packages resolved, 40 installed.
- `uv run --with pytest pytest -q`: **303 passed, 68 subtests passed**. This includes the headless-Chromium
  viewer check.
- No tldextract cache was created, and the working tree stayed clean.

## Issues found by this validation and fixed before the final runs

1. **Platform hosts contacted through redirects** (`superseded-round1/`, code `0a4fd39`). The host audit of
   the first live 1,200 run showed requests to www.facebook.com, www.instagram.com and www.linkedin.com.
   Company pages redirected there, and the redirect guard allowed any public host. Fixed in `ca8b87a`:
   platform hosts are refused at every hop.
2. **Crawl-delay cap too strict.** The same run lost 3 verified websites with `Crawl-delay: 20`, because the
   cap was 10 s. The cap is now 30 s, still inside the company budget (`ca8b87a`).
3. **A false "unverified" refresh event** (`superseded-round2/`, code `ca8b87a`). A site verified through
   the registry-website gate was reported `unverified` when that gate was rate-limited (HTTP 429). It is now
   carried forward (`4f827ee`).
4. **Deadline rows mislabelled** (round 2). Rows cut by the deadline were labelled `identity_unresolved`.
   They are now `not_researched`, and `stop_reason` is `grace_window` (`4f827ee`).

The final runs above were repeated after all four fixes.
