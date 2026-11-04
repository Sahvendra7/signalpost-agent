"""Score LLM runs against a labelled census, per arm (policies.ARMS).

    uv run python measurements/v32-gemini-2026-11-04/evaluate.py --set eval200b --v31-arm f2 RUN.jsonl [RUN2.jsonl ...] [--json OUT]
"""
import argparse, gzip, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.llm_experiments.policies import arm_members  # noqa: E402
from norway_company_agent.llm_experiments.scoring import company_type, error_category, score_arm  # noqa: E402

HERE = Path(__file__).resolve().parent


def load_items(name):
    items = [json.loads(l) for l in open(HERE / f"datasets/{name}.items.jsonl", encoding="utf-8")]
    labels_path = HERE / f"audits/{name}/labels.jsonl"
    if labels_path.exists():  # evalg250: labels kept apart from the census until scoring
        labels = {r["item_id"]: r for r in (json.loads(l) for l in open(labels_path, encoding="utf-8"))}
        for it in items:
            lab = labels.get(it["item_id"], {})
            it["label"], it["label_note"], it["label_category"] = lab.get("label"), lab.get("note"), lab.get("category")
    forms = {}
    with gzip.open(HERE / f"datasets/{name}.packets.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            p = json.loads(line)
            forms[p["item_id"]] = p["target_company"].get("legal_form")
    for it in items:
        it["error_category"] = it.get("label_category") or error_category(it.get("label_note"))
        it["company_type"] = company_type(forms.get(it["item_id"]))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--v31-arm", default="v31")
    ap.add_argument("--json", type=Path)
    ap.add_argument("runs", nargs="+", type=Path)
    a = ap.parse_args()
    items = load_items(a.set)
    has_reasons = any("v31_status" in i for i in items)
    results = {}
    for run in a.runs:
        llm = {r["item_id"]: r for r in (json.loads(l) for l in open(run, encoding="utf-8"))}
        missing = sum(i["item_id"] not in llm for i in items)
        arms = arm_members(items, llm, v31_arm=a.v31_arm, has_reasons=has_reasons)
        base = arms["v31"]
        res = {arm: score_arm(items, members, baseline=base) for arm, members in arms.items()}
        res["_run"] = {"file": run.name, "items_without_llm_record": missing,
                       "api_failures": sum(not r["ok"] for r in llm.values()),
                       "llm_vs_label": {f"{lab}->{dec}": n for (lab, dec), n in __import__("collections").Counter(
                           (i["label"], (llm.get(i["item_id"]) or {}).get("final_decision")) for i in items).items()}}
        results[run.name] = res
        print(f"\n### {run.name}  (missing {missing}, api failures {res['_run']['api_failures']})")
        print(f"{'arm':16} {'pub':>4} {'C':>4} {'I':>4} {'U':>3} {'prec':>6} {'wilson95':>13} {'cluster95':>13} {'poolcov':>7} {'retain':>8} {'cos':>6}")
        for arm in arms:
            s = res[arm]
            w = s["precision_wilson95"]; c = s["precision_cluster95"]
            fmt = lambda t: f"{t[0]:.3f}-{t[1]:.3f}" if t and t[0] is not None else "-"
            print(f"{arm:16} {s['published']:4} {s['correct']:4} {s['incorrect']:4} {s['unsure']:3} {s['precision'] if s['precision'] is not None else '-':>6} "
                  f"{fmt(w):>13} {fmt(c):>13} {s['pool_coverage'] if s['pool_coverage'] is not None else '-':>7} {s.get('baseline_retention', '-'):>8} {s['company_coverage']:>6}")
    if a.json:
        a.json.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
