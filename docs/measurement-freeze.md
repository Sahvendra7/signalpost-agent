# Measurement freeze (Phase 4, Step 1)

Frozen code for all live measurements: **commit `461bdbf0c5518f58455f11c123aa546f3d6ac2af`**
(branch `claude/awesome-sagan-m2lppu`). No research behaviour has changed since.

| Item | Value |
|---|---|
| Python | 3.13.14 (selected by uv; `requires-python >=3.12`) |
| uv | 0.8.17 |
| `uv.lock` sha256 | `42eb4399579a9079b2ff8b237070ec672f14ac9fcf57e97b3ecbfb1e7b423c98` |
| `pyproject.toml` sha256 | `f6fbc564c40ecbd88f066a8222a9dc1468312a48759fd49c6cdd30a414407c70` |
| Key resolved packages | beautifulsoup4 4.15.0, extruct 0.18.0, lxml 6.1.2, pydantic 2.13.4, pypdf 6.16.1, tldextract 5.3.2, trafilatura 2.2.0 |
| Tests | `uv run --with pytest pytest -q` → **167 passed, 5 subtests passed** |
| Measurement command | `uv run python scripts/run_source_experiments.py --universe signalpost-universe.jsonl.gz --count 100 --seed 20261002 --out out/experiments` (add `--search` only when `BRAVE_SEARCH_API_KEY` is set) |
| Environment variables used by the code | `BRAVE_SEARCH_API_KEY` / `BRAVE_API_KEY` (optional, unset), `BRAVE_USD_PER_1000` (optional, default 5). No other variables are read. |
| Secrets in repository | none |

## Network check (2026-10-02, development container)

| Host | Result |
|---|---|
| data.brreg.no | denied (`connect_rejected` by egress proxy) |
| pam-stilling-feed.nav.no | denied |
| builderr.ai | denied |
| company websites (equinor.com, dnb.no, vg.no) | denied |
| api.search.brave.com | denied; no API key configured |
| github.com (git) | allowed |

Result: Steps 2–7 cannot be measured from this container. Every live figure is `UNMEASURED`.

## Network re-check (2026-10-02 23:41 UTC, Phase 4A)

data.brreg.no 200, builderr.ai 200, company websites 200, pam-stilling-feed.nav.no reachable (404 on `/`),
api.search.brave.com reachable (no key). Free-source measurements were run. See
`docs/live-source-expansion-results.md`. Measurement-only additions (frozen code untouched):
`scripts/instrument_source_experiments.py` (wire-level wrapper) and `scripts/measure_filings_depth.py`
(corrected filings re-measurement).
