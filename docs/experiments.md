# Experiments log

No official Builderr score has been received. "Coverage" below is this repository's own
`category_available_rate` (share of companies with ≥1 evidence-backed available claim per category),
not the evaluator's pooled recall.

## E0 — Baseline (starter, commit 1797c4b)

See `docs/baseline.md`. Live coverage unmeasurable from the dev container (Brreg and the open web denied).

## E1 — V1 execution contract (no new sources)

- **Hypothesis**: emitting `OUTPUT_CONTRACT.md` envelopes with fact-level claims, and making the batch
  unable to drop or abort, protects every scoring dimension at near-zero recall cost.
- **Change**: `contract.py` (states, evidence entries, validator mirroring Builderr's citation rules),
  `claims.py` (deterministic per-fact extraction), `pipeline.py` (tolerant input, per-company and
  per-source isolation, live-registry fallback, snapshot store), outage-safe/order-insensitive refresh,
  `normalize_entity` keeps purpose/activity/dates already returned by Brreg, retries counted as requests,
  history rate limiter no longer bypassable by fetcher wrapping.
- **Test population**: 23 contract tests + 9 adversarial identity tests (offline fakes); 100-company CLI
  smoke with a synthetic bulk file (80 present, 20 absent) and all network sources denied.
- **Before** (starter on the same 100-company input):
  any absent-from-bulk org → `ValueError`, **0 envelopes**; all-sources-failed reported `complete`.
- **After**: 100/100 envelopes, contract-valid, input order preserved; 80 `completed` (bulk identity,
  address, filed-year claims), 20 `failed` + `identity_unresolved`; 0 false changes.
- **Runtime impact**: worst case (every source failing) 108.9 s wall for 100 companies with 8 workers;
  per-company p50 8.2 s / p95 9.5 s, all retry backoff (3 attempts × 6 endpoints). Healthy-source runtime
  not measurable here.
- **Cost impact**: $0, 0 LLM calls.
- **Failure impact**: one source failing now costs only that source's claims (previously could cost the
  company or the batch).
- **Decision**: keep.

### Next highest-value change (pending network access)

Measure real coverage on a 100-company sample from the public universe with Brreg reachable, then add
registry update/announcement history (dated activity for ~all companies) and filing-year history.

## E2 — Source-expansion experiments (built, not yet measured)

- **Hypothesis**: zero-cost, org-number-keyed official sources raise company coverage in the activity and
  filings areas more per request than search does in the websites area.
- **Change**: `src/norway_company_agent/experiments/` (Brreg update feed, accounts/PDF probe, NAV feed with
  orgnr verification, non-search discovery, optional search provider interface) and
  `scripts/run_source_experiments.py`; strict gate for discovered (non-registry) sites. In the main path:
  footer/address identity text is now captured by `fetch_website` (it was only captured by the Scrapy
  path, so org numbers in footers were invisible to the batch gate), and subunit `hjemmeside` is kept.
- **Test population**: 20 offline tests with provider-shaped fakes. Live 100-company run **blocked**: the
  container denies all target hosts; the harness ran end-to-end and reported every source `UNMEASURED`.
- **Before/after metrics**: pending network access. See `docs/source-expansion-results.md`.
- **Documented findings that already change the plan**: annual-account copies are image-only scans
  (Brreg `tiffToPdf`), so PDF text extraction is not a path to multi-year figures. The open accounts API
  is latest-year only. NAV's public token is for experiments and the feed has no employer filter.
- **Decision**: keep the footer fix (0 requests, increases org-number-based verification); hold all
  source integrations until measured.

## E3 — Phase 4 live measurement gate (blocked)

- Frozen code `461bdbf`; 167 tests pass (`docs/measurement-freeze.md`).
- Network re-checked twice on 2026-10-02, the second time after the owner reported the settings changed
  (23:33 UTC). The proxy still rejected every target host. No live run was possible; nothing was estimated.
- Outputs: `docs/live-source-expansion-results.md` (all UNMEASURED) and `docs/category-source-map.md`
  (registry_activity → public activity UNCONFIRMED).
- Decision: no source integrated; search and NAV stay optional and outside the batch command.
