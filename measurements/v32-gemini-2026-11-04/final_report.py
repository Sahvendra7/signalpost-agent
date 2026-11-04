"""Final independent evaluation report for evalg250 (scored once, after the labels were committed).

    uv run python measurements/v32-gemini-2026-11-04/final_report.py RUN.jsonl [RUN2.jsonl ...]
Writes results/evalg250-final.json and prints the tables used in docs/v32-gemini-results.md.
"""
import json, statistics, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import load_items  # noqa: E402
from norway_company_agent.llm_experiments.policies import ARMS, arm_members  # noqa: E402
from norway_company_agent.llm_experiments.scoring import score_arm  # noqa: E402

HERE = Path(__file__).resolve().parent
items = load_items("evalg250")
by_id = {i["item_id"]: i for i in items}
n_companies = 250
report = {"dataset": "evalg250", "companies": n_companies, "census_units": len(items),
          "labels": dict(Counter(i["label"] for i in items)), "runs": {}}


def fmt(t):
    return f"{100 * t[0]:.1f}–{100 * t[1]:.1f}" if t and t[0] is not None else "—"


for path in map(Path, sys.argv[1:]):
    recs = {r["item_id"]: r for r in (json.loads(l) for l in open(path, encoding="utf-8"))}
    arms = arm_members(items, recs, v31_arm="v31", has_reasons=True)
    scores = {arm: score_arm(items, arms[arm], baseline=arms["v31"]) for arm in ARMS}
    ok = [r for r in recs.values() if r["ok"]]
    fresh = [r for r in ok if r["api_calls_made"]]
    lat = sorted(r["latency_ms"] for r in fresh)
    cost = sum(r["paid_equivalent_cost_usd"] or 0 for r in ok)
    v31_ids = arms["v31"]
    cost_v31_only = sum((recs[i]["paid_equivalent_cost_usd"] or 0) for i in v31_ids if i in recs and recs[i]["ok"])
    pool_ids = [i["item_id"] for i in items if not i.get("v31_hard_reject") and i.get("v31_status") != "absent"]
    cost_c = sum((recs[i]["paid_equivalent_cost_usd"] or 0) for i in pool_ids if i in recs and recs[i]["ok"])
    ops = {"llm_records": len(recs), "api_failures": len(recs) - len(ok), "api_failure_rate": round((len(recs) - len(ok)) / len(recs), 4),
           "errors": dict(Counter(e for r in recs.values() for e in r["errors"])), "retries": sum(r["retries"] for r in recs.values()),
           "input_tokens": sum(r["input_tokens"] for r in ok), "output_tokens": sum(r["output_tokens"] for r in ok),
           "thoughts_tokens": sum(r["thoughts_tokens"] for r in ok),
           "latency_ms_p50": lat[len(lat) // 2] if lat else None, "latency_ms_p90": lat[int(0.9 * len(lat))] if lat else None,
           "paid_equivalent_cost_usd_all_candidates": round(cost, 4),
           "paid_equivalent_cost_per_100_companies": {"B_all_candidates": round(cost * 100 / n_companies, 4),
                                                       "A_v31_items_only": round(cost_v31_only * 100 / n_companies, 4),
                                                       "C_soft_pool": round(cost_c * 100 / n_companies, 4)},
           "calls_per_100_companies": {"B": round(len(recs) * 100 / n_companies, 1), "A": round(len(v31_ids) * 100 / n_companies, 1),
                                       "C": round(len(pool_ids) * 100 / n_companies, 1)},
           "quotes": f"{sum(r['validated'].get('verified_quotes', 0) for r in ok)}/{sum(r['validated'].get('total_quotes', 0) for r in ok)} verified",
           "quotes_exact": sum(r["validated"].get("exact_quotes", 0) for r in ok),
           "flags": dict(Counter(f for r in ok for f in r["validated"].get("flags", []))),
           "dates": dict(Counter(r["validated"].get("date_status") for r in ok)),
           "injection_detected": sum(bool(r["validated"].get("injection_detected")) for r in ok),
           "model_versions": dict(Counter(r["model_version"] for r in ok)), "prompt": next(iter(recs.values()))["prompt_id"],
           "prompt_sha256": next(iter(recs.values()))["prompt_sha256"], "model": next(iter(recs.values()))["model"]}
    # LLM category vs labelled category on incorrect items; LLM decision on correct items
    conf = Counter((i["label"], (recs.get(i["item_id"]) or {}).get("final_decision")) for i in items)
    cat = Counter((i["error_category"], (recs.get(i["item_id"]) or {}).get("validated", {}).get("content_category")) for i in items if i["label"] == "incorrect")
    examples = {"correct_publish": [], "correct_withhold_error": [], "incorrect_withhold": [], "incorrect_publish_error": []}
    for i in items:
        r = recs.get(i["item_id"])
        if not r or not r["ok"] or i["label"] not in ("correct", "incorrect"):
            continue
        key = ("correct_" if i["label"] == "correct" else "incorrect_") + ("publish" if r["final_decision"] == "publish" else "withhold")
        key = {"correct_withhold": "correct_withhold_error", "incorrect_publish": "incorrect_publish_error"}.get(key, key)
        examples[key].append({"company": i["company"], "title": i["title"], "label_note": i["label_note"], "v31": i.get("v31_status"),
                              "v31_reason": i.get("v31_reason"), "llm_category": r["validated"].get("content_category"),
                              "llm_subject": r["validated"].get("subject_relation"), "llm_decision": r["final_decision"],
                              "reason": r["validated"].get("reason"), "quotes": [q["quote"] for q in r["validated"].get("quotes", [])][:2],
                              "flags": r["validated"].get("flags")})
    report["runs"][path.name] = {"arms": scores, "operations": ops, "label_x_decision": {f"{a}->{b}": n for (a, b), n in conf.items()},
                                 "incorrect_category_x_llm_category": {f"{a}->{b}": n for (a, b), n in cat.items()}, "examples": examples}
    print(f"\n## {path.name}  model {ops['model']} prompt {ops['prompt']}")
    print("| Arm | Published | Correct | Incorrect | Unsure | Precision | Wilson 95% | Company-clustered 95% | Pool coverage | Company coverage | V3.1-correct retention | Errors removed vs V3.1 | Errors added vs V3.1 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        s = scores[arm]
        prec = f"{100 * s['precision']:.1f}%" if s["precision"] is not None else "—"
        print(f"| {arm} | {s['published']} | {s['correct']} | {s['incorrect']} | {s['unsure']} | {prec} | {fmt(s['precision_wilson95'])} | {fmt(s['precision_cluster95'])} | "
              f"{s['correct']}/{s['correct'] + s['false_negatives']} | {s['company_coverage']} | {s.get('baseline_retention')} | {s.get('baseline_errors_removed')} | {s.get('errors_introduced_vs_baseline')} |")
    print("ops:", json.dumps({k: ops[k] for k in ("api_failures", "api_failure_rate", "retries", "latency_ms_p50", "latency_ms_p90", "paid_equivalent_cost_usd_all_candidates", "paid_equivalent_cost_per_100_companies", "quotes", "dates", "injection_detected", "flags")}, ensure_ascii=False))
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results/evalg250-final.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
