# Signalpost reference agent

This is a runnable starting point for the Signalpost company-research challenge. It is intentionally a solid baseline, not a winning submission.

The public universe contains 411,160 eligible companies. Run the starter on 100 companies before submitting. Larger local tests, including 1,000 or more companies, are encouraged but their precomputed profiles are not submitted or scored.

## What it does

- reads a batch of Norwegian organisation numbers (JSONL, JSON or text) and emits **exactly one terminal
  envelope per input row**, in input order, in the `OUTPUT_CONTRACT.md` shape (`run`, `claims`,
  `evidence`, `changes`, `errors`, `operations`);
- never aborts the batch: malformed or duplicate rows, companies absent from the bulk file, failing
  sources and parser exceptions become explicit claim states and `errors` entries;
- anchors identity by organisation number in the Brønnøysund bulk snapshot or, when absent, the live
  registry; a registry response for any other organisation number is discarded;
- emits fact-level claims (identity, description, filings with reporting periods, leadership, locations,
  website, social profiles, group structure, dated role changes), each citing an evidence entry with
  source URL, retrieval time, SHA-256 of the captured bytes and a claim span;
- publishes registry-linked website facts only when the exact-entity identity gate passes; otherwise
  `ambiguous`;
- optionally stores the exact captured bytes (`--snapshot-dir`) so every hash can be re-verified offline;
- diffs against a previous run (`--previous-profiles`): typed `added`/`removed`/`changed`/`unverified`/`unavailable`
  events; a failed source keeps its last supported value with its original evidence, and reordered lists
  are never changes (`docs/refresh-semantics.md`);
- adds a deterministic, source-cited company summary to every envelope (`docs/company-summary.md`);
- optionally writes a self-contained offline HTML viewer (`--viewer-output`, `docs/viewer.md`);
- writes a run report with category coverage, module states, error codes, requests, latency and cost.

Design and rationale: `docs/architecture.md`, `docs/research.md`, `docs/source-matrix.md`.

An optional, provider-agnostic LLM layer (`src/norway_company_agent/llm/`, `docs/llm-layer.md`) is prepared
but **off**: the batch command never loads it, and it is used only by the A/B experiment scripts
(`scripts/run_llm_experiment.py --llm-enabled|--llm-disabled`, `scripts/compare_llm_ab.py`) once `LLM_*`
credentials are supplied.

## First run: try one saved example

Requires Python 3.12+. Open a terminal inside this extracted folder.

Before downloading company data or running a full crawl, try the bundled public
sample. It uses saved responses: no API key, registry download or live web requests.

```bash
python3 scripts/run_refresh_replay.py \
  --manifest tests/fixtures/refresh-snapshots.json \
  --output out/refresh-demo.json
```

Open `out/refresh-demo.json`. The `events` list shows what changed between two
versions of one company profile and the source evidence for each change. The sample
should find two expected changes, no false changes, and no extra changes when the
same data is checked again.

The report's `qualification_passed` field refers only to this public sample check.
It does not qualify an entry for the competition or prove live information coverage.
The printed request counts are reads from saved responses, not network calls.

## Next: research live companies

Requires Python 3.12+ and `uv`. This step downloads data and makes live requests.
The manifest selector can create a local test batch of any size. Use 100 rows for the recommended smoke test before trying a larger batch.

```bash
uv sync
curl -L 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' -o brreg-enheter.csv
curl -L 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' -o signalpost-universe.jsonl.gz

uv run python select_entry_batch.py \
  --universe signalpost-universe.jsonl.gz \
  --count 100 \
  --output entry-companies.jsonl

# Use the 100-company batch as your smoke test.
cp entry-companies.jsonl smoke-companies.jsonl

uv run python scripts/run_competition_batch.py \
  --organisations smoke-companies.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/smoke-profiles.jsonl \
  --output out/smoke-envelopes.jsonl \
  --report out/smoke-report.json \
  --snapshot-dir out/snapshots \
  --run-id smoke-001 \
  --expected-count 100

# Refresh: re-run later against the previous profiles; material changes appear in each envelope.
uv run python scripts/run_competition_batch.py \
  --organisations smoke-companies.jsonl \
  --bulk brreg-enheter.csv \
  --previous-profiles out/smoke-profiles.jsonl \
  --profiles-output out/smoke-profiles-2.jsonl \
  --output out/smoke-envelopes-2.jsonl \
  --report out/smoke-report-2.json \
  --run-id smoke-002

# You may test at larger scale locally, but Builderr supplies the official batch for scoring.
uv run python scripts/run_competition_batch.py \
  --organisations entry-companies.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/profiles.jsonl \
  --output out/envelopes.jsonl \
  --report out/run-report.json \
  --run-id local-001 \
  --expected-count 1000

uv run --with pytest pytest -q
```

The published archive was clean-room verified on August 24, 2026: 104 tests and 5 subtests passed, followed by a one-company live BRREG smoke run with one terminal envelope, five requests and zero silent drops.

`--bulk` is optional (the live registry is used for identity when it is absent) and `--expected-count` is a
guard that is reported, never a reason to drop rows. The command needs outbound HTTPS to `data.brreg.no`
and to company websites; with no network every envelope is still emitted, with sources marked `failed`.

Increase `--count` and `--expected-count` together for a larger local test. The 100-row smoke test above is practice only; Builderr supplies the companies for every official run.

## The improvement loop

1. Treat the organisation number as the anchor.
2. Generate site/profile candidates from official data, the company site, lawful search providers and named people.
3. Save every candidate and the evidence for or against it.
4. Publish only exact-entity matches. Parent, brand, franchise and similarly named companies are not exact.
5. Crawl static HTML first. Escalate to a browser only when a deterministic completeness check fails.
6. Measure added supported coverage, wrong-company claims, runtime, requests and cost.
7. Promote a strategy only when it improves coverage without weakening the accuracy gates.
8. Freeze strategies and thresholds before the daily evaluation run.

The strongest differentiator is external evidence that remains exact and auditable: official company pages, company-owned profiles, jobs, dated activity, ratings/reviews and permitted public signals. Do not trade accuracy for volume.

## Important source rule

Open-source code does not grant permission to scrape a platform. Follow each source's terms, robots policy, rate limits and licence. LinkedIn, Meta and Indeed are useful identity/discovery targets, but direct automated collection may be restricted. Use permitted APIs, licensed providers, company-owned outbound links, or return `blocked`/`not_available`.

Read `docs/competition-control-loop.md`, `docs/external-connectors.md` and the public source policy before adding connectors.

## Submission contract

Submit a repository with:

- a 100-company smoke-test result or report;
- one documented command that accepts a JSONL batch of organisation numbers;
- exactly one terminal envelope per input;
- pinned dependencies and reproducible setup;
- a previous-snapshot input and material-change output;
- a machine-readable run report with runtime, request count and third-party cost;
- declared models, APIs, licences and source-rights assumptions.

Email the repository URL, run command, models/APIs and expected cost per 100-company run to `submit@builderr.ai`.
