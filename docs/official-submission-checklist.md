# Official submission checklist (official-contract audit)

Audit date: 2026-10-03. Candidate commit audited: **`403a9c1`** (code identical to `c5c6a32`). `99d09d9` was also
assessed (§E). Source keys and hashes: `docs/official-requirements-matrix.md`. Raw evidence:
`measurements/official-audit-2026-10-03/`.

**Gate result: NOT READY.** No measured row breaks an official-run validity check. One validity row is an
**open risk** that cannot be checked because Builderr does not publish the budget: the run has no deadline and no
partial output (row 12). Three rows are **FAIL** against official text: a failed refresh erases the last supported
value (`HARNESS`), and there is no synthesis and no viewer (12 + 8 scored points). Each is explained below with the
change it needs. Nothing was fixed in this audit, by instruction.

Labels: **PASS** (verified in this audit); **KNOWN/ACCEPTED LIMITATION** (documented, low risk, accepted unless the
user decides otherwise); **OPEN RISK: fix before submission** (cannot be verified against an unpublished limit, and
the failure mode is total); **FAIL: fix before submission** (official text not met, explained, change named).

## A. Checklist

### A1. Official-run validity checks (`BRIEF` "Official-run checks", `EVAL`)

| # | Check | Status | Evidence |
|---|---|---|---|
| 1 | Exactly one terminal envelope for every company in the batch | PASS | Offline: 1,200 unseen, 1,100, 2,000 and dirty batches. Live: 150 and 1,200 unseen (§C). Clean room. |
| 2 | No fabricated financial values | PASS | Values copied from Regnskapsregisteret; no model; `claims.py` never imputes |
| 3 | No material wrong-company publication | PASS (our audits) / KNOWN LIMITATION | 0 found across all manual audits (V2: 27 of 27 new sites correct). Not Builderr-verified. Live page drift can flip a site to `ambiguous` (abstention, never a wrong match). |
| 4 | Claim-level source, retrieval time and reporting period | PASS | Contract validator: 0 findings on every live envelope; all financial claims carry `period` |
| 5 | Honest availability states | PASS (claims) / KNOWN LIMITATION (envelope) | The six states at claim level. The envelope carries `terminal_status` ∈ {completed, failed} as in the `KIT` example. An additive envelope-level state is recommended (matrix B3). |
| 6 | Missing values never converted to zero | PASS | Tests; `_count` = 0 is not coverage; nothing is imputed |
| 7 | Idempotent refresh | PASS | Live, 150 unseen: identical re-run → 0 claim-set differences; refresh with `--previous-profiles` → 0 changes. Replay fixture → 0 false changes. |
| 8 | Prior snapshots / evidence preserved on refresh | KNOWN LIMITATION (fix recommended) | Snapshot bytes persist (content-addressed). Re-running the same command **overwrites** the previous envelopes, profiles and report (observed: the run-1 report was overwritten by run 2). Changes appear only with `--previous-profiles`. See D2. |
| 9 | Reproducible setup, pinned dependencies, one evaluator command | PASS | §B clean-machine test |
| 10 | Declared source rights, server-side secrets, safe URL handling | PASS at `403a9c1` | `docs/official-source-compliance.md`. Public-host and redirect guard since `c5c6a32`. No secrets needed. **FAIL at `99d09d9`.** |
| 11 | 100-company smoke-test result in the public artifact | PASS | Public repository; `measurements/submission-smoke-2026-10-03/report.json` |
| 12 | Finish within the fixed time and resource budget | **OPEN RISK: fix before submission** | The budget is not published. The run has **no deadline** and writes **nothing until the batch ends**; a kill at 25 s left 0 envelopes. A timeout means the batch is not scored, and an entrant-caused miss "scores zero" (`EVAL`). Measured 1,200-company run: §C. Fix: D1. |

### A2. Robustness against the unpublished parts of the contract

| # | Item | Status | Evidence / change |
|---|---|---|---|
| 13 | Unseen companies, any batch size, input order, failure isolation | PASS | §C |
| 14 | No dependency on the public universe or local data | PASS | The clean clone had no universe or bulk file. The run path never opens it. |
| 15 | Input schema tolerance | KNOWN LIMITATION (fix recommended) | Accepted keys are `organisation_number` and `organisasjonsnummer` (as in the `KIT` reader). Keys `orgnr`, `org`, `organization_number` and `organisationNumber` make every row `failed`, and a CSV header adds one extra envelope. Fix: D3. |
| 16 | Builderr's frozen registry snapshot | KNOWN LIMITATION (fix recommended) | The declared command does not take it; identity comes from the live registry. `--bulk` given a non-gzip file aborts the whole run (`BadGzipFile`, outside isolation). Fix: D4. |
| 17 | Undeclared runtime fetch (public-suffix list) | KNOWN LIMITATION (fix recommended) | `tldextract` may download publicsuffix.org data. Pin it to the bundled list. |
| 18 | robots, `Crawl-delay`, Brreg pacing | KNOWN LIMITATION | robots honoured; `Crawl-delay` ignored; no client throttle on Brreg (≈4–5 requests/s). Phase 4A wire log: 0 Brreg retries and 0 5xx; two company websites answered 429. For the 1,200 run, see §C2. |
| 19 | Personal data in stored raw bytes | KNOWN LIMITATION (decision needed) | Raw Brreg roles JSON under `--snapshot-dir` includes birth dates; envelopes do not. |

### A3. Refresh quality (`HARNESS`, `PLAYBOOK`)

| # | Item | Status | Evidence / change |
|---|---|---|---|
| 20 | Failed refresh keeps the last supported value | **FAIL: fix before submission** | `HARNESS` §5: "A failed refresh must not erase the last supported value." Today the failure state replaces the value; only the false change is suppressed. Fix: D2. |
| 21 | Typed, two-sided change records; V2 site facts diffed | KNOWN LIMITATION (fix recommended) | No `change_type` or `materiality` and no previous-side source. Website, profile, activity and job changes are not tracked. Fix: D2. |

### A4. Scored dimensions (not validity checks)

| # | Item | Status | Evidence / change |
|---|---|---|---|
| 22 | Synthesis (12 points) | **FAIL: fix before submission** | No summary is emitted. Fix: D5 (deterministic, claim-cited). |
| 23 | UX (8 points) | **FAIL: fix before submission** | No user-facing view. Fix: D6 (static HTML from envelopes). |
| 24 | External coverage (50 points) | KNOWN LIMITATION | Verified websites 8–15% per 100-sample (10.1% on 1,200 unseen); footprint 5–10% (6.3%); job postings in 1 of 1,200 companies (§C). Only 10.9% of the universe has a registry website. See `official-scoring-model.md` §5. |

### A5. Submission package (`BRIEF` "Submit")

| # | Item | Status | Evidence / change |
|---|---|---|---|
| 25 | Repository URL | PASS | https://github.com/Sahvendra7/signalpost-agent (public) |
| 26 | Exact commit hash reachable | KNOWN LIMITATION (action) | The commit is on `claude/awesome-sagan-m2lppu`, not on the default branch `main`. Tag it or merge it before emailing. |
| 27 | 100-company smoke-test result | PASS | `measurements/submission-smoke-2026-10-03/` (to be re-run on the final commit) |
| 28 | One run command | PASS | §B. Move it to the top of README (action). |
| 29 | Models / APIs / licences | PASS | No models. Brreg APIs (NLOD 2.0 per the `KIT` doc), company websites, 40 pinned open-source packages (`docs/submission-audit.md`). |
| 30 | Expected cost per official batch | PASS | $0 |
| 31 | Agent name and contact for results | Pending (user) | — |
| 32 | LLM disabled; Brave and NAV excluded | PASS (accepted) | The run path never imports them. |

## B. Clean-machine contract test (step 8)

Exactly the sequence in `PLAYBOOK` "It does not install on a clean machine":

| Step | What was done | Result |
|---|---|---|
| Fresh directory | `git clone https://github.com/Sahvendra7/signalpost-agent` into a new scratch folder | OK |
| Pinned commit | `git checkout 403a9c1` | OK |
| Empty environment | No `.venv`; `UV_CACHE_DIR` set to a new empty directory; no universe or Brreg file present; system Python 3.11 (the project needs ≥3.12) | OK |
| Declared install only | `uv sync --locked` (uv 0.8.17) | Exit 0 in 1.9 s; 40 packages from `uv.lock`; uv selected CPython 3.13.14; `uv lock --check` consistent |
| Tests | `uv run --with pytest pytest -q` | 224 passed, 5 subtests passed |
| Single run command | `uv run python scripts/run_competition_batch.py --organisations batch.jsonl --output out/envelopes.jsonl --profiles-output out/profiles.jsonl --report out/report.json --snapshot-dir out/snapshots --run-id <id>` | 150 unseen: exit 0, 150 envelopes, valid. 1,200 unseen: §C. |

Notes: the interpreter is not pinned (no `.python-version`), so uv picks the newest managed CPython. `uv` itself must
exist on the evaluator machine, as declared. Nothing outside `uv.lock` was used.

## C. Official batch handling and resource budget (steps 7 and 9)

### C1. Batch handling ("Your agent picks its own companies")

| Probe | Input | Envelopes | Order | Validation | Notes |
|---|---|---|---|---|---|
| Offline, 1,200 valid org numbers **absent from the public universe** (JSONL) | 1,200 | 1,200 | preserved | passed | Injected faults: parser crash in roles (3%), accounts HTTP 500 (2%), wrong-org registry response (1%), total network failure (1%). Every fault was contained; 42 `failed` envelopes are those with no identity. |
| Offline, 1,100 universe rows in the selector's format | 1,100 | 1,100 | preserved | passed | |
| Offline, 2,000-line plain text | 2,000 | 2,000 | preserved | passed | No batch-size assumption |
| Offline, dirty batch (invalid, duplicate, checksum-fail, spaced digits, alternate key, blank, non-JSON) | 156 rows (1 blank line skipped) | 156 | preserved | passed | |
| Offline, unknown key names | 5 each | 5 each | preserved | passed | **All `failed`** (risk A2-15) |
| Offline, CSV with header | 6 lines | 6 | preserved | passed | **Header becomes an extra envelope** |
| `--bulk` as plain CSV | — | — | — | — | **Raises `BadGzipFile`; whole run would fail** |
| Live, 150 unseen (seed 20261004, 0 overlap with every earlier sample) | 150 | 150 | preserved | passed | §C2 |
| Live, 1,200 unseen (seed 20261005, 0 overlap with every earlier sample; input sha256 `765647df…`) | 1,200 | 1,200 | preserved | passed | §C2. 1,200 `completed`; shape check: 0 defects in 53,537 claims and 47,871 evidence entries |

Peak RSS for the offline harness (all cases in one process): 205 MiB.

### C2. Live measurements on unseen companies (declared command, 8 workers, clean room)

Both runs used a fresh clone at `403a9c1`, `uv sync --locked`, and the declared command with `--snapshot-dir`,
8 workers (default), no `--bulk`, and no API key. Raw outputs are in `measurements/official-audit-2026-10-03/`.

| Metric | 150 unseen | 1,200 unseen |
|---|---|---|
| Wall time (process) | 177.1 s | **1,336.5 s (22.3 min)** |
| Envelopes / validation / input order | 150 / passed / preserved | 1,200 / passed / preserved |
| Terminal status | 150 `completed` | 1,200 `completed` |
| Peak RSS | 189 MiB | **399 MiB** (sampled every 15 s: 133 MiB at start, rising steadily to 390 MiB at the end) |
| CPU | 23.3 s user | 190 s user + 16 s system (≈15% of one core; the run is network-bound) |
| Requests | 1,081 (7.2 per company) | 8,773 (7.31 per company); 62.9 MB received |
| Request latency p50 / p95 / max | 658 / 820 / 2,317 ms | 661 / 855 / 12,368 ms |
| Per-company runtime p50 / p95 / max | 3.6 / 24.6 / 55.4 s | 3.6 / 31.4 / **83.2 s** (mean 8.75, p90 22.7, p99 53.2) |
| Companies slower than 30 / 45 / 60 / 90 s | — | 82 / 34 / 6 / 0 |
| Share of summed runtime in the slowest 10% of companies | — | 43% |
| Brreg source errors | 0 | 4 Regnskapsregisteret HTTP 500 after 3 attempts (0.3%). Brreg returned no 429. |
| Registry-website (V1) errors | — | 29 (26 HTTP 403, 1 HTTP 429, 1 HTTP 500, 1 unsupported content type) |
| Output size | — | envelopes 38.9 MB, profiles 10.3 MB, snapshots 134 MB |
| Verified official website | 12 (8.0%) | 121 (10.1%) |
| Site-linked profile | — | 66 (5.5%) |
| Dated first-party activity | 4 (2.7%) | 23 (1.9%) |
| Footprint (profile or dated activity) | 8 (5.3%) | 76 (6.3%) |
| Job posting | 0 | 1 (0.08%): the first JobPosting found in any measured company |
| All five areas | 8 | 77 |
| Claims: available / not_available / ambiguous / failed / blocked | 5,919 / 699 / 4 / 3 / 2 | 47,942 / 5,510 / 50 / 32 / 3 |
| Wrong-company publications | not manually audited in this audit (the identity gate is unchanged since the audited V2) | not manually audited (same) |

### C3. Can the architecture complete 1,000 / 1,100 / 1,200 companies? (step 9)

**Runtime model (measured, not assumed).** Workers pull companies independently, so

```
batch wall ≈ (sum of per-company runtimes) ÷ workers + end-of-batch straggler
```

| Run | Σ runtime ÷ 8 | Measured wall | Straggler |
|---|---|---|---|
| 100 (fixed sample, V2) | 118.3 s | 160.8 s | 42.5 s |
| 150 unseen | 140.8 s | 175.8 s | 35.0 s |
| 1,200 unseen | 1,312.7 s | 1,334.1 s | 21.4 s |

The straggler term stays under 45 s and does not grow with N. Mean per-company runtime is stable across seven
runs over six distinct samples (7.2–10.3 s; 8.75 s on the 1,200 run). Measured on these samples, wall time is therefore
linear in N at a fixed worker count. This was confirmed directly at N = 1,200, not extrapolated.

| Batch | Expected wall at 8 workers | Range (sample mean 7.2–10.3 s per company) | Basis |
|---|---|---|---|
| 1,000 | ≈ 18.6 min | 15.4–22.2 min | model |
| 1,100 | ≈ 20.4 min | 16.9–24.4 min | model |
| 1,200 | **22.3 min** | 18.4–26.5 min | **measured** (model range shown for day-to-day variation) |

Memory grows roughly linearly, because all envelopes, profiles and the run-wide page cache stay in memory until
the end: ≈0.2 MiB per company, so ≈380 MiB at 1,100 and ≈400 MiB at 1,200 (measured). Disk use is ≈50 MB of outputs
plus ≈134 MB of snapshots per 1,200 companies.

**Tail and worst case.** The observed maximum is 83.2 s per company across 1,850 company runs (1,750 distinct companies). The code's
theoretical ceiling per company is much higher, because no single timer bounds a company: up to 5 Brreg calls ×
(3 attempts × 20 s) ≈ 5 min; the V1 website module ≈ 10 fetches × 15 s (more with the `http://` fallback); site
research 60 s plus one in-flight request (≤ 30.5 s); and DNS lookups, which have no timeout. A whole-batch slowdown is
the realistic danger. If Brreg slowed to 2 s per call, the batch would gain ≈ 1,200 × 5 × 1.4 s ÷ 8 ≈ 17 min. A full
Brreg stall is a "shared-source failure" that `EVAL` voids and reruns, but a partial slowdown would not obviously
be.

**Verdict against the official constraints.** The budget is not published, so no PASS is possible. Under normal
source conditions the current architecture completes 1,000–1,200 companies in about 19–23 minutes, using under
400 MiB and ≈15% of one CPU core. It fits any budget of about 30 minutes or more with margin. Below about 20 minutes it
would time out, and because it writes nothing until the end, it would then return **zero** envelopes. Raising
`--workers` to 16 would roughly halve wall time (estimate, not measured), but it would double the request rate to
Brreg (≈4.5 per second today), whose limit is not published. D1 (deadline plus incremental output) removes the
all-or-nothing failure mode whatever the budget turns out to be.

## D. Changes needed before submission (none made in this audit)

| ID | Change | Why (official basis) | Behaviour risk |
|---|---|---|---|
| D1 | Batch deadline (`--deadline-seconds`, default from env) with graceful degradation: when the remaining time falls below a margin, skip website work for companies not yet started and emit registry-only envelopes with `site_research: failed (deadline)`. Write each envelope as soon as its company finishes, then reorder into input order at the end (atomic). | "fixed time and resource budget"; "A timeout or missing result is not scored" | None for identity; only coverage under time pressure |
| D2 | Refresh-aware single command: auto-use the existing `--profiles-output` as the previous run, archive the previous outputs under `history/<run_id>/`, carry the last supported value forward on a failed source (`carried_forward: true` plus an error), add `change_type`, `materiality` and previous-side source to changes, and diff V2 site facts | `EVAL` "Refresh preserves prior evidence and exposes material changes"; `HARNESS` §5; board "Each scored entry ran twice" | Low; covered by the existing refresh tests plus new ones |
| D3 | Input tolerance: any single 9-digit field or known alias key; skip a leading non-numeric header line | Input schema not published | None |
| D4 | Snapshot tolerance: `--bulk` accepts gzip or plain CSV or JSONL, and any load error falls back to the live registry with a recorded error | "Builderr provides the frozen official registry snapshot" | None |
| D5 | Deterministic synthesis per envelope (`company_synthesis`, claim-cited, with an explicit unknowns list and a changes paragraph) | Synthesis (12) | None (presentation only, no new claims) |
| D6 | Static HTML viewer generated from the envelopes (search, compare, source links, mobile) | UX (8) | None |
| D7 | Additive envelope fields: six-state `availability`, `legal_identity`, `refresh` | `EVAL` envelope contents; `PAGE` "Each result carries one of these states" | None |
| D8 | Pin `tldextract` to the bundled suffix list; add `.python-version`; put the one command at the top of README | Reproducibility | None |
| D9 | Re-run the 100-company smoke test and the clean-machine test on the final commit; tag the commit | `EVAL`, `RULES` | — |

## E. Is `99d09d9` submission-safe?

**No.** `99d09d9` fails official-run check 10 ("safe URL handling"): its V2 site fetcher did not apply the public-host
and redirect guard, so a registered domain resolving to a private or metadata address, or a redirect to one, could
have been fetched. `c5c6a32` fixed this, and `403a9c1` adds only documents and measurements. Every other observation
in this checklist applies to `403a9c1` and `99d09d9` alike.
