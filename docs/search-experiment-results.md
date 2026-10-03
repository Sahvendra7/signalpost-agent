# Search experiment (Brave, optional): results

**Status: UNMEASURED.** On 2026-10-03 `api.search.brave.com` was reachable but no key was configured
(`BRAVE_SEARCH_API_KEY` / `BRAVE_API_KEY` unset; the API answers 422 without a token). No query was sent
and no search yield, precision or latency figure exists. Nothing below is a measured search outcome.

## What is built (experiment only)

- `SearchProvider` interface with `NoSearchProvider` (default) and `BraveSearchProvider` (enabled only by
  the env key). Search is never a dependency of the batch command.
- Query families Q1–Q6 (`experiments/search.py`, `QUERY_FAMILIES`):
  `"<legal name>" "<orgnr>"`, `"<legal name>" LinkedIn`, `"<legal name>" Facebook`,
  `"<legal name>" Instagram`, `"<legal name>" Norway`, `"<orgnr>"`.
- Per result: candidate URL → pre-class (DIRECTORY / OFFICIALLY_LINKED / AMBIGUOUS / website candidate)
  → website candidates crawled and classified by gate v2 (`docs/website-identity-policy-v2.md`) → accepted
  only if FIRST_PARTY or OFFICIALLY_LINKED. Rank is ignored for identity. A company stops searching
  after its first accepted candidate.
- Two modes on the same sample: **adaptive** (only companies whose fifth area is still empty after the
  free path) and **naive** (all 100).

To run once a key is available (same sample):

```bash
BRAVE_SEARCH_API_KEY=... uv run python scripts/run_public_activity_experiment.py \
  --profiles out/experiments/baseline-profiles.jsonl --envelopes out/experiments/baseline-envelopes.jsonl \
  --discovery out/experiments/e4-site-discovery.json --out out/experiments-search --search
```

## Measured inputs to the search decision

| Item | Value | Status |
|---|---|---|
| Companies eligible under the adaptive rule | **91 / 100** (88 with no verified site, 3 with a verified site but no profile or dated activity) | MEASURED |
| Companies the naive strategy searches | 100 / 100 | by design |
| Brave price | $5.00 per 1,000 Search requests; $5 free credit per month (≈ 1,000 requests) | published price, 2026 |

The adaptive rule saves little on this sample (91 vs 100 companies), because the free path covers only 9.

## Query cost (by design: queries × $0.005; yield UNMEASURED)

| Strategy | 100 companies | 1,000 companies | 1,200 companies |
|---|---|---|---|
| Naive, one family | $0.50 (100 queries) | $5.00 | $6.00 |
| Naive, all six families | $3.00 (600 queries) | $30.00 | $36.00 |
| Adaptive, one family (91% eligible) | $0.455 (91 queries) | ≈ $4.55 (**extrapolated** from the 91% eligibility) | ≈ $5.46 (**extrapolated**) |
| Adaptive, all six families, upper bound | $2.73 (546 queries) | ≈ $27.30 (**extrapolated**) | ≈ $32.76 (**extrapolated**) |

The adaptive all-families cost is an upper bound. Stopping after the first accepted candidate lowers it
by an amount that cannot be known without measurement. The $5 monthly credit is account-level, not per
run: it covers about one naive single-family 1,000-company run per month. Crawl requests for each
website candidate (≈ 2–5 per candidate, measured as 4.6 per candidate in gate v2) come on top, at $0.
None of these figures is an official Builderr runtime or score.

## Not known (and not estimated)

Correct sites found, wrong sites, ambiguous sites, no-result rate, downstream profile and activity
yield, search latency, best query family, search false-positive rate, adaptive vs naive coverage.
