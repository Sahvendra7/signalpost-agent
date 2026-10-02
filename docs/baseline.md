# Baseline: the starter as shipped

Recorded 2026-10-02 at commit `1797c4b`, before any behaviour change.

## Environment

| Item | Value |
|---|---|
| Install | `uv sync` (uv 0.8.17) — resolved from `uv.lock`, 1.9 s with warm cache |
| Python | 3.13.14 selected by uv (`requires-python >=3.12`) |
| Dependencies | beautifulsoup4, extruct, lxml, pydantic, pypdf, tldextract, trafilatura (+ optional scrapy/playwright, torch/transformers) — ranges in `pyproject.toml`, exact versions in `uv.lock` |
| Network | Container egress allows package indexes only. `builderr.ai`, `data.brreg.no` and arbitrary company sites are **denied** (proxy 403). |

## Tests

`uv run --with pytest pytest -q` → **104 passed, 5 subtests passed** in 3.1 s (matches the README's
clean-room claim).

## Offline refresh sample

```
uv run python scripts/run_refresh_replay.py --manifest tests/fixtures/refresh-snapshots.json --output out/refresh-demo.json
```
0.13 s; 2 expected / 2 observed changes, precision 1.0, recall 1.0, evidence complete, idempotent;
4 snapshot reads (no network).

## Live batch (one company)

Sample input: `923609016` (Equinor ASA) with a one-row synthetic bulk file.

```
uv run python scripts/run_competition_batch.py --organisations one.txt --bulk bulk.csv.gz \
  --profiles-output out/b-profiles.jsonl --output out/b-env.jsonl --report out/b-report.json \
  --run-id baseline-1 --expected-count 1
```

| Metric | Value |
|---|---|
| Runtime | 10.9 s wall for one company (all sources failing: 3 attempts × backoff per Brreg endpoint) |
| Requests reported | 9 (counts *results*, not attempts: 6 Brreg endpoints were each tried 3×) |
| Envelopes | 1 for 1 input |
| Entity state | `complete` — although **every live source** returned `source_error` |
| Module states | registry/accounting_obligation `complete` (offline); registry_live, financials, roles, group, locations, website `source_error` |
| `retry_count` | 0 everywhere (attempts are not recorded) |
| Validation | `passed: true` |

Because this container cannot reach Brreg, **live source coverage could not be measured here**; it
must be measured from an environment with access to `data.brreg.no` and the open web.

A plain (non-gzip) CSV passed as `--bulk` crashes with `BadGzipFile`. The README's
`curl -L .../lastned/csv -o brreg-enheter.csv` works only because Brreg serves that endpoint
gzip-compressed despite the `.csv` file name.

## Current evidence format

Per module a record `{field, status, source_type, source_class, source_url, retrieved_at, value, as_of,
note, content_sha256, source_row_key, effective_at}` nested inside `profile.evidence`. No evidence IDs,
no claims, no claim spans. The accounting-obligation hash is the hash of a ruleset *string*; the
bulk-registry hash is the hash of the entire CSV.

## Current source coverage (by design, not measured)

registry bulk, accounting-obligation rule, live entity, normalised latest accounts (up to 3 records),
roles, group structure, subunits, registry-linked homepage + up to 4 same-host priority pages (social
links, JSON-LD organisations). `financial_history` exists but is not in the default module list.
External connectors (Brave, LinkedIn guest, Google News RSS, YouTube, Google Maps, Fagfolkguiden) are
separate experimental scripts outside the batch command.

## Current failure behaviour (pinned in `tests/test_starter_characterization.py`)

| Situation | Starter behaviour |
|---|---|
| Duplicate org number in input | `ValueError` — **whole batch aborted, zero envelopes** |
| Malformed org number | `ValueError` — whole batch aborted |
| Org number absent from bulk file | `ValueError` — whole batch aborted |
| `--expected-count` ≠ input size | `SystemExit` before any work |
| Exception inside one worker | propagates from `future.result()` — batch aborted |
| All sources fail | envelope `state: complete`, validation passes |
| Source outage at refresh | diffed as a value change (false change) |
| List order change at refresh | diffed as a change |
| Envelope shape | legacy `run_id/state/modules/profile`; not `OUTPUT_CONTRACT.md` |
