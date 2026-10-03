# Live source-expansion results (Phase 4A: free sources)

**Status: MEASURED (free sources only).** First live run, 2026-10-02 23:43–23:52 UTC, plus a corrected
filings re-measurement (23:55–00:09 UTC). NAV and Brave are **UNMEASURED** (not run, see below).

| Item | Value |
|---|---|
| Frozen code | `461bdbf` (`src/` and `scripts/run_source_experiments.py` byte-identical; 167 tests pass) |
| Command | `uv run python scripts/instrument_source_experiments.py --universe signalpost-universe.jsonl.gz --count 100 --seed 20261002 --skip nav --out out/experiments` |
| Instrumentation | `scripts/instrument_source_experiments.py` runs the frozen script unchanged and wraps `urllib.request.OpenerDirector.open` to log every wire exchange per phase. It also writes the baseline envelopes to disk, which the frozen script keeps only in memory. It does not change research behaviour. |
| Universe | `signalpost-universe.jsonl.gz` from builderr.ai. Archive SHA-256 `1c89710e…0a5384`; uncompressed SHA-256 `b82d6a3e…c838`; 411,160 rows. All three values match the official evaluation contract (`/docs/signalpost-evaluation-harness.md`) and `data/universe-metadata.json`. |
| Sample | 100 companies, `--seed 20261002`. `sample.jsonl` SHA-256 `80eb79e6…7677`. Identical in an aborted first attempt (see Notes), so the sample is reproducible. |
| Raw outputs | `measurements/phase4a-2026-10-02/` (results, per-company rows, wire log, gzipped envelopes, quality checks) |
| Cost | $0. No paid API in any code path that ran. |

## 1. Same-sample comparison

"Companies covered" means companies with at least one verified fact from that strategy in the
category the strategy feeds. Requests are logical HTTP requests and attempts are wire attempts,
both from the wire log. Runtime is the phase wall clock with 6 workers (3 for filings, 1 for the
corrected filings run).

| Strategy | Companies Covered | Incremental Companies | Verified Facts | Requests | Attempts | Runtime | Cost | Wrong Matches |
|----------|-------------------|-----------------------|----------------|----------|----------|---------|------|---------------|
| Baseline (frozen V1, all 7 modules) | 100 / 100 (≥1 fact) | — | 3,947 | 590 | 590 | 76.5 s | $0 | 0 observed |
| + Brreg update history (`registry_activity`) | 100 | **0 in a confirmed scored category**; +100 in `registry_activity` (unscored label) | 3,562 dated events (2,912 typed; 369 with field detail) | +180 | +180 | +21.2 s | $0 | 0 (0 identity rejections) |
| + Additional open-accounts fields (same response) | 99 | **0** (DEEPER FACT COVERAGE) | +4,463 numeric fields (baseline publishes 1,877) | +0 in production (re-fetch for measurement: 100) | +0 | ≈ +0 s (parse only) | $0 | 0 |
| + Filing copy PDF (latest year) | 100 | **0** (DEEPER: document evidence only) | 100 PDFs retrieved, **0 text-extractable** (all image-only) | +200 | +200 | +829.6 s (1 worker, 2.1 s pacing) | $0 | 0 |
| + Free website discovery (83 companies without a registry URL) | 5 accepted by gate, **4 after manual audit** | **+4 websites** (+5 by gate) | 4 verified official sites (5 by gate) | +206 (+123 DNS lookups) | +206 | +59.5 s | $0 | **1** (third-party fan site accepted) |
| + NAV job feed | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | — | UNMEASURED |
| + Brave search (A–E) | UNMEASURED (no key) | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |

Retries were 0 in every phase. No request returned 5xx. Two website 429s and two 403s in the
baseline were answered on the first attempt; `fetch_bytes` does not retry 4xx.

### Derived ratios

| Strategy | Company coverage % | Facts / company | Requests / company | Seconds / company (wall, phase ÷ companies) |
|---|---|---|---|---|
| Baseline | 100% with ≥1 fact; per category see §2 | 39.47 | 5.90 | 0.77 (per-company p50 3.35 s, p95 11.76 s) |
| Brreg update history | 100% `registry_activity` | 35.62 events | 1.80 | 0.21 (p50 1.33 s, p95 1.61 s) |
| Open-accounts extra fields | 0 new; 99% deeper | 44.63 extra fields | 0 | ≈ 0 |
| Filing PDF | 0 new | 1 document, 0 parsed facts | 2.00 | 8.30 (rate-limited) |
| Website discovery (n = 83) | websites 17% → 22% by gate (21% audited) | 0.05 sites | 2.48 (1.48 excluding the redundant Brreg re-fetch) | 0.72 (p50 0.15 s, p95 17.6 s) |

### Incremental impact vs baseline

| Expansion | Incremental company coverage | Incremental verified facts | Incremental requests | Incremental runtime |
|---|---|---|---|---|
| Brreg update history | 0 in any confirmed scored category. +100 companies only if `registry_activity` is accepted as public activity (UNCONFIRMED). | +3,562 events (+90%) | +180 (+30.5%) | +21.2 s (+27.7%) |
| Open-accounts extra fields | 0 | +4,463 (+113%) | 0 | ≈ 0 |
| Filing PDF | 0 | 0 extracted facts; +100 document hashes | +200 (+33.9%) | +829.6 s (+1,084%) |
| Website discovery | **+4 websites** (+4 pp; 8 → 12 crawled-verified sites, 17 → 21 companies with a website claim) | +4 sites (plus their crawl claims, not counted) | +206 (+34.9%); inherent cost +123 site attempts (+20.8%) | +59.5 s (+77.7%) |

## 2. Baseline (frozen V1)

Totals: 100 companies, 100 terminal envelopes (all `completed`), 3,947 available facts, 3,947
evidence references (39.47 per company), 590 requests and 590 attempts, 0 retries, 9 redirect hops,
16.9 MB downloaded (wire; the pipeline's own counter reports 15.65 MB), 0 errors. Identity
failures: 0 (`registry_live` complete for 100). Companies with ≥1 fact: 100. With 0 facts: 0. Facts
per company ranged from 24 to 88.

Run without `--bulk`, as in the frozen command, so the `registry` (bulk CSV) module reports
`not_found` for all 100 and identity comes from `registry_live`.

| Module | complete | not_found | source_error | blocked_policy |
|---|---|---|---|---|
| registry_live | 100 | | | |
| financials | 99 | 1 | | |
| roles | 100 | | | |
| group | 3 | 97 | | |
| locations | 100 | | | |
| website | 14 | 83 (no registry URL) | 2 (HTTP 429, 403) | 1 (DNS) |
| registry (bulk) | | 100 (not supplied) | | |

### Coverage by requested category

| Category | Companies covered | Facts | What drives it |
|---|---|---|---|
| Filings | 100 (filed-year fact); 99 with financial values | 1,977 | Regnskapsregisteret `/regnskap/{org}`. Latest published period is 2025 for 97 companies, 2024 for 2, none for 1. Periods published: 2023: 596, 2024: 631, 2025: 650 values. |
| Leadership | 100 (CEO: 63; board chair: 99) | 495 | Brreg roles |
| Locations | 100 (business address); 73 with ≥1 subunit | 329 | Brreg entity + subunits |
| Websites | 17 with a registry-listed URL; **8 crawled and identity-verified** (6 ambiguous, 2 HTTP errors, 1 DNS failure); 2 with social profiles | 28 | Registry `hjemmeside` + crawl |
| Hiring | **0** | 0 | No hiring source in V1 |
| Public activity | **0 confirmed.** Raw: 100 companies have `roles_last_changed`, category `activity`, source `official_roles`. | 100 (raw) | Recorded separately. A roles timestamp is not a confirmed public-activity fact. |

Unmapped raw categories: identity 814 facts, description 201 (registered activity 100, statutory
purpose 94, website description 7), relationships 3 (group structure).

The frozen `results.json` reports `hiring_activity` coverage as 100%. That value comes from the
`roles_last_changed` claim alone, not from hiring evidence. It is reported here as raw data, not as
hiring coverage.

## 3. Brreg update history → `registry_activity`

| Metric | Value |
|---|---|
| Companies with ≥1 update | 100 / 100 |
| Companies with ≥1 update in the last 365 days | 100 / 100 (447 events) |
| Events / company | mean 35.6, median 17, min 3, max 614 (975387011, 7 paged requests) |
| Typed events (`Ny` / `Endring` / `Sletting` / `Fjernet`, or with field detail) | 2,912 |
| Events with field-level change detail (`includeChanges`) | 369 (10.4%) |
| Event types observed (companies) | Endring 100, Ukjent 98, Ny 46 |
| Date range | earliest 2018-04-23, latest 2026-09-28 (each company's latest event: 2026-02-14 … 2026-09-28) |
| Requests / attempts | 180 / 180 (1.8 per company: entity feed plus subunit feed when subunits exist) |
| Runtime | 21.2 s wall; per company p50 1.33 s, p95 1.61 s |
| Identity failures | 0 rejections, 0 published mismatches |
| Evidence completeness | 3,562 / 3,562 (100%) with URL, SHA-256, retrieval time and span |

The 100% recent-update rate is probably an artefact of how the universe was selected, not a sign of
business activity. Every universe company filed 2025 accounts in 2026, and `/sisteInnsendteAarsregnskap` is the most common changed
field among the 497 stored sample events (8 of the 21 field mentions; per-event detail beyond the
samples is not persisted by the frozen module). The feed starts in 2018, so
older history is not available. Most events (89.6%) carry no field detail, which only arrives on
updates after the 2025-11-13 `includeChanges` launch. An undetailed `Endring` says only that
something changed.

Mapping: kept as `registry_activity`. The official brief requires "Hiring and dated public activity
from permitted sources" but does not name the Brreg update feed (see `docs/category-source-map.md`).

## 4. Filings / open accounts

### 4a. Frozen E2 experiment, as run: two measurement defects

The frozen E2 module ran on 100 companies (399 requests, 419.9 s, 0 parse failures) but produced
invalid results:

1. **Wrong period.** It reads the first element of `/regnskap/{org}`, which the API returns
   oldest-first. That gave `period_correct_rate` 0.06 and depth figures for 2023 instead of the
   latest year. The baseline pipeline is not affected: it publishes every returned period, with 2025
   as the latest for 97 companies.
2. **PDF 406.** It requests the copy with `Accept: application/pdf`, which the endpoint answers with
   HTTP 406 (100 of 100). Manual probe: the same URL with `Accept: */*`, `application/octet-stream`
   or no Accept header returns `200 application/pdf` (281 kB for 917922896/2025).

Its prior-year probe (`?år=YYYY`) returned 404 for 99 companies. That probe is unnecessary, because
the default response already holds up to six periods.

The frozen code was not changed. `scripts/measure_filings_depth.py` re-measures with the latest
period and `Accept: */*`, read-only, on the same sample.

### 4b. Corrected measurement

| Metric | Value |
|---|---|
| Accounts response | 200 for 99, 404 for 1 (that company has no structured accounts) |
| Periods per company | 3: 83, 2: 7, 1: 6, 4–6: 3, 0: 1. Years: 2025: 100, 2024: 95, 2023: 89. Types: SELSKAP 278, KONSERN 6. |
| Latest period = registry's filed year (2025) | 99 / 99 |
| Fields the baseline publishes | 7 per period: 1,877 values for 99 companies |
| **Additional numeric fields in the same response** | **4,463** (44.6 per company) on 99 companies |
| Most frequent additional fields | sumEgenkapitalGjeld 284, sumOmloepsmidler 284, sumDriftskostnad 283, opptjentEgenkapital 276, sumBankinnskuddOgKontanter 270, innskuttEgenkapital 268, sumAnleggsmidler 267, nettoFinans 261, kortsiktigGjeld 257, sumFordringer 234, finansinntekter 231, langsiktigGjeld 224, finanskostnad 221, skattekostnad 207, loennskostnad 206, annenRentekostnad 172, salgsinntekter 161, sumInvesteringer 126, totalresultat 121, sumVarer 72, rentekostnadSammeKonsern 21, goodwill 16 |
| Non-numeric metadata per period | currency, presentation plan, audit opt-out / unaudited flag, liquidation flag, small-company rules (284 each) |
| Companies gaining ≥1 additional fact | 99, all of which already have baseline financial values → **DEEPER FACT COVERAGE, 0 NEW COMPANY COVERAGE** |
| Reporting periods | 2023–2025 (latest = 2025 for all 99) |
| Request overhead | 0 (same response the baseline already fetches) |
| Runtime overhead | ≈ 0 (parsing only) |
| Parsing failures | 0 |
| Identity rejections | 0 (every period's `virksomhet.organisasjonsnummer` matches) |

### 4c. Filing copy PDF (corrected header)

| Metric | Value |
|---|---|
| Filed-year list | 200 for 100. Latest year listed is 2025 for 100. |
| Latest-year PDF retrieved | 100 / 100 (29.98 MB in total for the run) |
| Text-extractable (≥200 chars) | **0**. All 100 are image-only scans. |
| PDF year = filed year | 100 / 100 |
| Requests / runtime | +200 / +829.6 s sequentially with the starter's 2.1 s pacing (8.3 s per company) |
| Value | **DEEPER only.** Gives a hashed, dated filing-document reference, but no extractable facts without OCR. |

## 5. Non-search website discovery

Population: the 83 companies without a registry website. 80 had at least one candidate, and 31 had at
least one candidate that resolved and was crawled.

| Candidate source | Candidates | No DNS | Unavailable | Ambiguous | Rejected | Accepted |
|---|---|---|---|---|---|---|
| `name_domain_guess` | 145 | 123 | 11 | 6 | 0 | 5 |
| `registry_email` (domain of the registry `epostadresse`) | 9 | 0 | 2 | 7 | 0 | 0 |
| `subunit_website` | 1 | 0 | 1 | 0 | 0 | 0 |
| `nav_employer_site` | not run (NAV skipped) | | | | | |
| **Total** | **155** | 123 | 14 | 13 | 0 | **5** |

Registry contact fields seen in the open entity record: `epostadresse`, `telefon`, `mobil`.

Accepted candidates (gate `discovered_site_strict_v1`) and manual audit:

| Org no. | Legal name | Domain | Gate reason | Manual audit |
|---|---|---|---|---|
| 920772099 | SPIREN DESIGN AS | spirendesign.no | org no. on a captured page | correct (title "Spiren Design AS") |
| 921136501 | LYSE ROM AS | lyserom.no | org no. on a captured page | correct ("Org. nr.: 921136501MVA" on homepage) |
| 927818094 | BLI OPTIMAL AS | blioptimal.no | legal name + postcode + street | correct (Vikelvfaret 4, 7054 Ranheim) |
| 986757368 | ANNEN VRI AS | annenvri.no | legal name + postcode + street | correct (Øvre Smebyveg 4, 2870 Dokka) |
| 976744667 | ÅRÅSEN STADION AS | arasenstadion.no | legal name + postcode + street | **WRONG OWNER.** The title is "Åråsen Stadion Fansite". It is a third-party fan site that lists the stadium's address and points to `lsk.no/om-stadion/` for official contact. |

The 13 ambiguous candidates (`no organisation number and no name-plus-registered-address
corroboration`) include generic or occupied domains: eiendom.no, drage.no, groove.no, auto24.no,
and email domains that redirect to a different brand (minbit.no → vindafjordtomteselskap.no,
kurtsimonsen.no → storbilsenter.no). None was published.

| Metric | Value |
|---|---|
| Candidate websites | 155 (32 resolved and crawled) |
| Verified (gate) / verified (after audit) | 5 / 4 |
| Rejected / ambiguous / unavailable | 0 / 13 / 14 (plus 123 with no DNS) |
| Companies gaining a verified website | 5 by gate, **4 after audit** |
| Companies gaining new website facts | same 4 (5 by gate) |
| Additional requests | 206: 83 Brreg entity re-fetches (redundant with the baseline's `registry_live`) + 123 website attempts. Plus 123 DNS lookups. 24 attempts were transport-level `URLError`. |
| Additional runtime | 59.5 s wall; per company p50 0.15 s, p95 17.6 s |
| Bytes | 5.37 MB |
| Wrong-company matches | **1** wrong owner (an accepted page about the company's asset, owned by a third party) |
| Name-only acceptances | 0. All 5 had an org number or a legal name plus street and postcode. |

## 6. Not run

| Source | Status | Reason |
|---|---|---|
| NAV job feed (`pam-stilling-feed.nav.no`) | **UNMEASURED** | Instructed not to run in Phase 4A. The host is reachable, but no NAV token is configured. |
| Brave search | **UNMEASURED** | No `BRAVE_SEARCH_API_KEY` / `BRAVE_API_KEY` in the environment. Not run, and no substitute provider was used. |

## 7. Quality checks

| Check | Result |
|---|---|
| Exactly 100 input companies | ✅ 100 (100 unique) |
| Exactly 100 terminal envelopes | ✅ 100, all `completed` |
| Input order preserved | ✅ organisation numbers and `input_position` 0–99 match `sample.jsonl` |
| No duplicate terminal envelopes | ✅ 0 |
| No evidence without a source | ✅ 0 of 3,947 baseline evidence items without `source_url`; 0 without SHA-256; 0 dangling refs; 0 available claims without evidence. Experiment evidence: Brreg 3,562/3,562 and E2 1,556/1,556 complete. |
| No source without a retrieval timestamp | ✅ 0 baseline evidence items without `retrieved_at`. Every corrected-filings fetch records `retrieved_at`. |
| No website accepted from name-only matching | ✅ 0. But 1 wrong-owner acceptance passed through the legal-name + address rule (see §5). |
| No false refresh changes | ✅ Offline replay of the same profiles as `previous_profiles`: 100 envelopes, 0 changes, 0 network calls, claim keys identical for 100/100, validation passed (`refresh-replay-check.json`). |
| No unverified company association | ✅ for baseline, Brreg and filings (0 identity rejections or mismatches). ❌ **1** in website discovery (976744667 → arasenstadion.no). It is experiment output only; the batch pipeline did not publish it. |

## Notes

- An earlier start of the same command (23:42–23:43 UTC) was stopped during the baseline, because
  the frozen script does not write the envelopes to disk. Its partial outputs are kept in
  `out/experiments-aborted-1/` and are not used. Its sample was identical.
- The frozen `results.json` folds `registry_activity` and roles timestamps into `hiring_activity`.
  This report does not.
- Request and attempt counts from the wire log match the frozen per-experiment counters exactly
  (baseline 590, Brreg 180, E2 399, discovery 206).
- No experimental metric here is converted into a Builderr score.
