# NAV job-feed experiment (Phase 4B)

Measurement only. NAV is not part of the batch command.

| Item | Value |
|---|---|
| Date | 2026-10-03, 03:48–04:05 UTC |
| Token | `NAV_TOKEN_MODE=public_experiment`. Fetched at runtime from `https://pam-stilling-feed.nav.no/api/publicToken` (unauthenticated, documented by NAV "for experiments", rotates irregularly). Held in process memory only; never written, printed or committed. Archive scanned for JWT strings: none. **Not** claimed suitable for the final Builderr submission. |
| Sample | Phase 4A sample, unchanged: `out/experiments/sample.jsonl`, sha256 `80eb79e6…7677`, 100 companies |
| Main command (as specified) | `uv run python scripts/instrument_source_experiments.py --organisations out/experiments/sample.jsonl --skip activity,filings,discovery --out out/experiments-nav` |
| Companion (measurement only) | `uv run python scripts/measure_nav_feed.py --e3 out/experiments-nav/e3-nav-jobs.json --profiles out/experiments-nav/baseline-profiles.jsonl --out out/experiments-nav/nav-feed-measure.json --full-index` |
| Code | `2b12448` for the run (`eda0f73` adds the companion script). See "Deviations" below. |
| Raw outputs | `measurements/phase4b-nav-2026-10-03/` |

## Deviations from the frozen experiment code (found by probing the live API before the run)

1. **Token parser.** The live response is a label line plus the JWT on the next line ("Current public
   token for Nav Job Vacancy Feed:"). The frozen parser returned `None`, which would have reported NAV
   as UNMEASURED without reading the feed. Fixed to accept a JWT-shaped line.
2. **Page size.** `next_url` carries no `pageSize`. Without it NAV falls back to 1,000 items per page
   (measured: 1,000 items / 474 KB vs 10,000 / 4.8 MB). The frozen loop requested 10,000 only on page 1,
   so it would have made ~10× the requests and possibly hit its 300-page cap. Fixed to keep `pageSize`.
3. **Job evidence.** Accepted jobs now keep employer name, source URL, retrieval time and content hash
   (previously only the first three samples, without evidence fields).

None of these touches the research pipeline. Tests: 167 pass.

## Two matching strategies measured

Both obey the same rule: a job belongs to the company only if `employer.orgnr` equals the company's
organisation number or one of its registered subunits. Names are never sufficient.

- **S1, name prefilter (frozen design):** scan the feed. Fetch detail only for ads whose header
  `businessName` equals the legal or a subunit name, then verify the org number.
- **S2, full org-number index:** scan the feed, fetch the detail of **every** active ad and match on
  org number only. This is the only strategy that sees ads posted under a brand name.

## Results (n = 100)

| # | Metric | S1 name prefilter | S2 full orgnr index |
|---|---|---|---|
| 1 | Token acquisition | GET `/api/publicToken`, 477 ms | same |
| 2 | Feed startup latency (first page) | 4,765 ms | same scan |
| 3 | Feed download time (39 pages) | 65.2 s (companion); 67.7 s in the main run | same |
| 4 | Bytes | 184.1 MB feed + 6.7 KB detail | 184.1 MB feed + 61.0 MB details = **245.1 MB** |
| 5 | Feed entries / unique ads processed | 374,300 entries / 92,916 ads (6 months) | same |
| 6 | Open (ACTIVE) ads | 9,724 | 9,724 (45 more were past `expires` and were dropped) |
| 7 | Active ads with employer orgnr | not observable (header has none) | **9,397 / 9,724 (96.6%)**; fixed-seed 300-ad sample: 97.0% |
| 8 | Ads matched to target companies | 1 | **2** |
| 9 | Companies with ≥1 verified job | **1** | **2** |
| 10 | Jobs / company | 0.01 (1.0 per covered company) | 0.02 (1.0 per covered company) |
| 11 | Branch vs parent | 1 via subunit orgnr, 0 via entity | **2 via subunit orgnr, 0 via entity** |
| 12 | Ambiguous employer matches | 0 | 0 |
| 13 | Rejected matches (name matched, orgnr did not) | 0 | n/a (no name step) |
| 14 | HTTP requests | 41 (1 token + 39 pages + 1 detail) | 9,764 (1 + 39 + 9,724) |
| 15 | Attempts / retries | 41 / 0 | 9,764 / 0 |
| 16 | Memory | scan peak 122 MB Python heap (tracemalloc); main-run process peak RSS 325.6 MB (includes the baseline) | companion process peak RSS 336.2 MB |
| 17 | Incremental runtime over baseline (baseline 74.3 s) | **+67.9 s (+91%)** | **+65.2 s scan + 688.9 s details (4 workers, 415 ms each) ≈ +754 s (+1,015%)** |

Accepted jobs (full evidence in `nav-feed-measure.json`):

| Company | Employer orgnr (scope) | Employer name on ad | Published | Expires | Found by |
|---|---|---|---|---|---|
| 975387011 STIFTELSEN CRUX | 973112406 (subunit) | Stiftelsen CRUX | 2026-09-24 | 2026-10-12 | S1 and S2 |
| 928590445 KARMØY BÅTUTSTYR AS | 928609987 (subunit) | Maritim Båtutstyr Karmøy | 2026-08-13 | 2026-10-31 | **S2 only**: the brand name differs from the legal name |

### Derived (A–G)

| | S1 | S2 |
|---|---|---|
| A. Companies with ≥1 verified hiring fact | 1 | 2 |
| B. Incremental company coverage (baseline confirmed hiring = 0) | **+1 pp** | **+2 pp** |
| C. Verified hiring facts | 1 | 2 |
| D. Facts / company | 0.01 | 0.02 |
| E. Requests / company | 0.41 | 97.6 |
| F. Seconds / company (incremental wall ÷ 100) | 0.68 | 7.54 |
| G. Bytes / company | 1.84 MB | 2.45 MB |

### Website candidates from NAV

`employer.homepage` was empty on both accepted ads. Companies gaining a website candidate: **0**.
Verified: **0**. Rejected by the gate: **0**. Nothing was published.

## Cost at batch scale

The feed cost does not depend on how many companies are researched: every run scans the same six
months of feed. In S2 the detail cost also does not depend on batch size (one fetch per active ad).
Only the S1 detail fetch grows with the number of companies.

| Batch | S1 requests | S1 data | S1 time | S2 requests | S2 data | S2 time |
|---|---|---|---|---|---|---|
| 100 (measured) | 41 | 184.1 MB | 68 s | 9,764 | 245.1 MB | ≈ 754 s |
| 1,000 (**estimate**) | ≈ 50 | ≈ 184 MB | ≈ 68 s | ≈ 9,764 | ≈ 245 MB | ≈ 754 s at 4 workers |
| 1,200 (**estimate**) | ≈ 52 | ≈ 184 MB | ≈ 68 s | ≈ 9,764 | ≈ 245 MB | ≈ 754 s at 4 workers |

The estimates assume the measured feed size (374,300 entries, 9,724 active ads) and the measured S1
candidate rate (0.01 per company). Expected companies covered at 1,000: S1 ≈ 10, S2 ≈ 20, if the
measured 1% and 2% rates hold. With 1 and 2 hits in 100, both rates are very uncertain. These are not
official Builderr runtimes.

## Operational viability

- **The feed scan (S1) is viable in time and memory:** about 68 s, 184 MB download and 122 MB heap,
  fixed per run. On a 100-company run it nearly doubles wall time for +1 company.
- **The full org-number index (S2) is not viable per run:** 9,724 extra requests to NAV and about 11.5 min
  (4 workers) per run for +2 companies. It is only reasonable as a persistent, incrementally refreshed
  index, which would turn the one-run cost into a small `If-Modified-Since` delta. That is a design change
  and is not built.
- **Credential:** the only evaluator-reachable credential is the public experiment token. A private
  token cannot be committed and would have to be injected by Builderr.
- **Precision:** 0 wrong employers. Every hit came through a **subunit** org number, so mapping registered
  branches is essential; parent-only matching would have found 0.

## Classification: **OPTIONAL**

The measured gain is +1 to +2 percentage points of hiring coverage on a sample whose confirmed hiring
coverage is 0. That is real but small. S1 costs +91% wall time per 100-company run, S2 costs +1,015%, and
the credential is documented for experiments only. Precision is excellent. The gain does not meet
"material company-coverage gain with a viable execution cost", so NAV stays OPTIONAL: off by default,
outside the batch command, enabled only with an explicitly provided token.
