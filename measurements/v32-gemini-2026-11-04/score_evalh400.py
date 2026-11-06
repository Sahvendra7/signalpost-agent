"""Score the independent evalh400 set (PREREGISTRATION_v2.json) once, with the blind rubric-v2 labels.

    uv run python measurements/v32-gemini-2026-11-04/score_evalh400.py [RUN.jsonl]

Without RUN only the deterministic arms (v31, v31_gate) are scored and the LLM arms are reported as "not run".
With RUN (the pre-registered configuration: gemini-3.1-flash-lite, prompt news-p2-evidence-v2, every evalh400 packet)
all ARMS_V2 arms are scored on identical inputs. Wrong-company errors are reported separately. Cost and latency come
from the run records (paid-equivalent list price; the free tier bills nothing).
Writes results/evalh400-score[-deterministic].json.
"""
import hashlib, json, os, statistics, sys
from collections import Counter
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":  # the company-clustered bootstrap iterates sets: pin hashing so its CI is reproducible
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(HERE))
from evaluate import load_items  # noqa: E402
from norway_company_agent.llm_experiments.policies import ARMS_V2, arm_members_v2  # noqa: E402
from norway_company_agent.llm_experiments.scoring import score_arm  # noqa: E402

PREREG = json.loads((HERE / "PREREGISTRATION_v2.json").read_text(encoding="utf-8"))
WRONG = ("wrong_company", "other_entity_or_unrelated")
run_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None

items = load_items("evalh400")
assert all(i.get("label") for i in items), "evalh400 has unlabelled units"
gate = {i["item_id"]: i["identity_gate"] for i in items}
recs = {}
if run_path:
    frozen = dict(PREREG["implementation_frozen"])
    frozen["src/norway_company_agent/llm_experiments/news_contract.py"] = PREREG["addendum_2026-11-06_minimise_fix"]["news_contract.py_sha256"]
    drift = [f for f, h in frozen.items() if hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h]
    assert not drift, f"implementation changed since pre-registration: {drift}"
    recs = {r["item_id"]: r for r in (json.loads(l) for l in open(run_path, encoding="utf-8"))}
    want = PREREG["configuration"]["model"], PREREG["configuration"]["prompt_id"]
    seen = {(r["model"], r["prompt_id"]) for r in recs.values()}
    assert seen == {want}, f"run is not the pre-registered configuration: {seen} != {want}"
    missing = [i["item_id"] for i in items if i["item_id"] not in recs]
    assert not missing, f"{len(missing)} evalh400 units have no run record"
    failed = [i for i, r in recs.items() if not r.get("ok")]
    if failed:  # a failed call would count as "withhold" and flatter precision: never score a partial run as complete
        sys.exit(f"partial run: {len(recs) - len(failed)}/{len(recs)} items completed, {len(failed)} failed "
                 f"({dict(Counter(e for i in failed for e in (recs[i].get('errors') or ['unknown'])))}); resume the run, do not score")
arms = arm_members_v2(items, recs, gate)
llm_arms = {"A_filter_v2", "C_hybrid_v2", "D_conservative_v2", "B_llm_only"}
report = {"dataset": "evalh400", "units": len(items), "companies": len({i["org"] for i in items}),
          "labels": dict(Counter(i["label"] for i in items)),
          "pool_correct_companies": len({i["org"] for i in items if i["label"] == "correct"}),
          "run": (str(run_path.resolve().relative_to(ROOT)) if run_path.resolve().is_relative_to(ROOT) else str(run_path)) if run_path else None, "arms": {}}
for arm in ARMS_V2:
    if arm in llm_arms and not run_path:
        report["arms"][arm] = "not run (Gemini calls blocked until the exposed keys are rotated; see report)"
        continue
    s = score_arm(items, arms[arm], baseline=arms["v31"])
    s["wrong_company_fp"] = sum(s["fp_by_category"].get(c, 0) for c in WRONG)
    report["arms"][arm] = s
if run_path:
    rs = list(recs.values())
    cost = sum(r.get("paid_equivalent_cost_usd") or 0 for r in rs)
    lat = [r["latency_ms"] for r in rs if r.get("latency_ms") is not None]
    ncomp = report["companies"]
    report["usage"] = {"records": len(rs), "ok": sum(bool(r.get("ok")) for r in rs), "api_calls_made": sum(r.get("api_calls_made", 0) for r in rs),
                       "input_tokens": sum(r.get("input_tokens") or 0 for r in rs), "output_tokens": sum(r.get("output_tokens") or 0 for r in rs),
                       "thoughts_tokens": sum(r.get("thoughts_tokens") or 0 for r in rs), "paid_equivalent_cost_usd": round(cost, 4),
                       "paid_equivalent_cost_per_100_companies_with_candidates_usd": round(100 * cost / ncomp, 4),
                       "paid_equivalent_cost_per_100_sampled_companies_usd": round(100 * cost / PREREG["sample"]["companies"], 4),
                       "latency_ms_p50": statistics.median(lat) if lat else None,
                       "latency_ms_p90": sorted(lat)[int(0.9 * (len(lat) - 1))] if lat else None}
out = HERE / f"results/evalh400-score{'' if run_path else '-deterministic'}.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"evalh400: {report['units']} units, {report['companies']} companies, labels {report['labels']}")
print(f"{'arm':18} {'pub':>4} {'C':>4} {'I':>4} {'U':>3} {'prec':>7} {'wilson95':>13} {'cluster95':>13} {'items':>8} {'cos':>6} {'wrongco':>7}")
for arm, s in report["arms"].items():
    if isinstance(s, str):
        print(f"{arm:18} {s}")
        continue
    p = f"{100 * s['precision']:6.1f}%" if s["precision"] is not None else "    n/a"
    w, c = s["precision_wilson95"], s["precision_cluster95"]
    fmt = lambda ci: f"{100 * ci[0]:5.1f}-{100 * ci[1]:5.1f}%" if ci and ci[0] is not None else "          n/a"
    print(f"{arm:18} {s['published']:4} {s['correct']:4} {s['incorrect']:4} {s['unsure']:3} {p} {fmt(w)} {fmt(c)} "
          f"{s['correct']:3}/{s['correct'] + s['false_negatives']:<4} {s['company_coverage']:>6} {s['wrong_company_fp']:7}")
if run_path:
    print(json.dumps(report["usage"]))
print(f"-> {out.relative_to(ROOT)}")
