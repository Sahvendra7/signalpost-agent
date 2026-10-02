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
