"""Operational summary of every model call made in V3.2 (from the response cache and run records).

    uv run python measurements/v32-gemini-2026-11-04/ops_summary.py
"""
import glob, json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.llm_experiments.runner import PRICES  # noqa: E402

HERE = Path(__file__).resolve().parent
by = defaultdict(list)
for f in glob.glob(str(HERE / "cache/*/*.json")):
    d = json.load(open(f, encoding="utf-8"))
    mv = d.get("model_version") or "?"
    by[mv].append(d)
errors = Counter()
quota = Counter()
attempted = Counter()
for f in glob.glob(str(HERE / "runs/*.jsonl")):
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        if r["api_calls_made"] or r["errors"]:
            attempted[r["model"]] += r["api_calls_made"]
        for e in r["errors"]:
            if not e.startswith("not_called") and e != "cache_miss_offline":
                errors[(r["model"], e)] += 1
        for q in r["quota_ids"]:
            quota[(r["model"], q)] += 1
out = {"successful_cached_responses": {}, "errors_recorded_in_runs": {f"{m}|{e}": n for (m, e), n in errors.items()},
       "quota_ids_seen": {f"{m}|{q}": n for (m, q), n in quota.items()}}
print(f"{'served model version':28} {'ok calls':>8} {'in tok':>9} {'out tok':>8} {'think':>6} {'paid-eq $':>9} {'lat p50 s':>9} {'p90 s':>6}")
for mv, rows in sorted(by.items()):
    lat = sorted(r["latency_ms"] for r in rows)
    model = next((m for m in sorted(PRICES, key=len, reverse=True) if mv.startswith(m) or mv.startswith(m.replace("gemini-", ""))), None)
    i = sum(r.get("input_tokens") or 0 for r in rows); o = sum(r.get("output_tokens") or 0 for r in rows); t = sum(r.get("thoughts_tokens") or 0 for r in rows)
    cost = (i * PRICES[model][0] + (o + t) * PRICES[model][1]) / 1e6 if model else None
    out["successful_cached_responses"][mv] = {"calls": len(rows), "input_tokens": i, "output_tokens": o, "thoughts_tokens": t,
                                              "paid_equivalent_usd": round(cost, 4) if cost is not None else None,
                                              "latency_s_p50": round(lat[len(lat) // 2] / 1000, 1), "latency_s_p90": round(lat[int(0.9 * len(lat))] / 1000, 1)}
    print(f"{mv:28} {len(rows):8} {i:9} {o:8} {t:6} {cost if cost is None else round(cost, 3)!s:>9} {lat[len(lat) // 2] / 1000:9.1f} {lat[int(0.9 * len(lat))] / 1000:6.1f}")
print("errors:", dict(errors))
print("quota ids:", dict(quota))
(HERE / "results/ops_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
