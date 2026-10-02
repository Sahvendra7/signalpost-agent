# Live source-expansion results (Phase 4)

**Status: UNMEASURED.** Frozen code `461bdbf` (see `docs/measurement-freeze.md`). On 2026-10-02 at
23:33 UTC, after the network settings were reported changed, the egress proxy still rejected every
target host (`connect_rejected`): data.brreg.no, pam-stilling-feed.nav.no, builderr.ai, all tested
company websites and api.search.brave.com. No Brave API key is configured. No sample could be drawn,
because the Builderr universe file is on builderr.ai.

Per the measurement rules, no cell below is estimated. All experiments share one sample: the first
live run draws 100 companies with `--seed 20261002` and writes `out/experiments/sample.jsonl`, which
every later run reuses.

| Strategy | Companies Covered | Incremental Companies | Facts | Requests | Runtime | Cost | Wrong Matches |
|----------|-------------------|-----------------------|-------|----------|---------|------|---------------|
| Baseline (V1 pipeline) | UNMEASURED | — | UNMEASURED | UNMEASURED | UNMEASURED | $0 (no paid API in code path) | UNMEASURED |
| + Brreg update feed (`registry_activity`) | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | $0 | UNMEASURED |
| + Full open-accounts fields | UNMEASURED | UNMEASURED | UNMEASURED | +0 by design (same response) | UNMEASURED | $0 | UNMEASURED |
| + Filing years / PDF copy | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | $0 | UNMEASURED |
| + NAV job feed (token: none obtained) | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | $0 | UNMEASURED |
| + Free website discovery | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | $0 | UNMEASURED |
| + Brave strategy A–E | UNMEASURED (not run: no key, no network) | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |

Derived ratios (coverage per request, per second, per dollar; facts per request, per dollar): **UNMEASURED**.
None can be computed without the counts above.

## Decisions under the stop condition

None of the known-before-proceeding items (baseline coverage, Brreg and filing increments, NAV and
discovery coverage, Brave coverage, overheads, cost, wrong-company rate) is known, so no evidence-based
architecture decision is possible. The defaults below change nothing in the batch command.

| Decision | Outcome | Basis |
|---|---|---|
| Search (Step 10) | **B. Optional**, off unless `BRAVE_SEARCH_API_KEY` is set; not wired into the batch command | No measurement. Default preserves $0 cost and the current precision. |
| NAV (Step 11) | **OPTIONAL** (experiment only) | The brief's stated default. Additionally, the evaluator-compatible credential model is unresolved: the public token is documented "for experiments". |
| Brreg activity | Not integrated; label stays `registry_activity` | Coverage unmeasured; scoring mapping UNCONFIRMED (see `docs/category-source-map.md`). |
| Open-accounts fields | Not integrated | 0 extra requests by design, but the depth gain is unmeasured. |

## To fill this table

Network access must allow the hosts above *for this session's container*. Then:

```bash
uv sync
curl -L https://builderr.ai/signalpost-company-universe-2025.jsonl.gz -o signalpost-universe.jsonl.gz
uv run python scripts/run_source_experiments.py --universe signalpost-universe.jsonl.gz --count 100 --seed 20261002 --out out/experiments
# only with a key, same sample:
uv run python scripts/run_source_experiments.py --organisations out/experiments/sample.jsonl --skip activity,filings,nav --search --out out/experiments-search
```
