"""Diagnostic prompt/model comparison on a fixed labelled subset (default: eval200 dev80). Diagnostic only.

    uv run python measurements/v32-gemini-2026-11-04/compare_dev.py [--set eval200] [--subset datasets/eval200.dev80.txt] RUN.jsonl ...
"""
import argparse, json, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.llm_experiments.scoring import wilson  # noqa: E402

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--set", default="eval200")
ap.add_argument("--subset", type=Path, default=HERE / "datasets/eval200.dev80.txt")
ap.add_argument("--json", type=Path)
ap.add_argument("runs", nargs="+", type=Path)
a = ap.parse_args()
items = {json.loads(l)["item_id"]: json.loads(l) for l in open(HERE / f"datasets/{a.set}.items.jsonl", encoding="utf-8")}
subset = [l.strip() for l in open(a.subset, encoding="utf-8") if l.strip()] if a.subset and a.subset.exists() else None
out = {}
print(f"{'run':62} {'n':>3} {'C→pub':>8} {'I→pub':>8} {'prec':>6} {'wilson95':>12} {'unc%':>5} {'fail':>4} {'q ok':>8} {'in tok':>6} {'out':>4} {'p50 s':>5}")
for run in a.runs:
    recs = {r["item_id"]: r for r in (json.loads(l) for l in open(run, encoding="utf-8"))}
    ids = [i for i in (subset or list(recs)) if i in recs and items.get(i, {}).get("label") in ("correct", "incorrect")]
    c = [i for i in ids if items[i]["label"] == "correct"]
    w = [i for i in ids if items[i]["label"] == "incorrect"]
    pc = sum(recs[i]["final_decision"] == "publish" for i in c)
    pw = sum(recs[i]["final_decision"] == "publish" for i in w)
    unc = sum(recs[i]["final_decision"] == "uncertain" for i in ids)
    fail = sum(not recs[i]["ok"] for i in ids)
    qt = sum(recs[i]["validated"].get("total_quotes", 0) for i in ids)
    qv = sum(recs[i]["validated"].get("verified_quotes", 0) for i in ids)
    ok = [recs[i] for i in ids if recs[i]["ok"]]
    lat = [r["latency_ms"] / 1000 for r in ok if r["api_calls_made"]]
    prec = pc / (pc + pw) if pc + pw else None
    row = {"n": len(ids), "correct_published": f"{pc}/{len(c)}", "incorrect_published": f"{pw}/{len(w)}", "precision": prec,
           "precision_wilson95": wilson(pc, pc + pw), "uncertain_rate": round(unc / len(ids), 3) if ids else None, "api_failures": fail,
           "quotes_verified": f"{qv}/{qt}", "input_tokens_median": statistics.median([r["input_tokens"] for r in ok]) if ok else None,
           "output_tokens_median": statistics.median([(r["output_tokens"] or 0) + (r["thoughts_tokens"] or 0) for r in ok]) if ok else None,
           "latency_s_median": round(statistics.median(lat), 1) if lat else None}
    out[run.name] = row
    wl = row["precision_wilson95"]
    print(f"{run.name[:62]:62} {len(ids):3} {row['correct_published']:>8} {row['incorrect_published']:>8} {prec if prec is None else round(prec, 3)!s:>6} "
          f"{(f'{wl[0]:.2f}-{wl[1]:.2f}' if wl[0] is not None else '-'):>12} {100 * (row['uncertain_rate'] or 0):5.1f} {fail:4} {row['quotes_verified']:>8} "
          f"{row['input_tokens_median']!s:>6} {row['output_tokens_median']!s:>4} {row['latency_s_median']!s:>5}")
if a.json:
    a.json.write_text(json.dumps(out, indent=1), encoding="utf-8")
