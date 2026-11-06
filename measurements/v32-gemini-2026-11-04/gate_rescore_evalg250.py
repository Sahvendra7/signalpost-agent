"""DIAGNOSTIC (evalg250 is consumed): apply the deterministic identity gate to the cached evalg250 Gemini outputs.

No API call. Arms per policies.ARMS_V2. Two label variants: rubric v1 labels as reported, and rubric v2 for the 45 FrP
units (audits/evalg250/labels_rubric_v2_frp.jsonl, provisional until second-person adjudication).
    uv run python measurements/v32-gemini-2026-11-04/gate_rescore_evalg250.py
"""
import gzip, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(HERE))
from evaluate import load_items  # noqa: E402
from norway_company_agent.identity_gate import assess_item, assess_site, target_from_envelope  # noqa: E402
from norway_company_agent.llm_experiments.capture import CaptureStore  # noqa: E402
from norway_company_agent.llm_experiments.policies import ARMS_V2, arm_members_v2  # noqa: E402
from norway_company_agent.llm_experiments.scoring import score_arm  # noqa: E402

store = CaptureStore(ROOT / "out/v32/captures")
envs = {json.loads(l)["organisation_number"]: json.loads(l) for l in gzip.open(HERE / "capture-evalg250/v31-evalg250.envelopes.jsonl.gz", "rt")}
packets = {json.loads(l)["item_id"]: json.loads(l) for l in gzip.open(HERE / "datasets/evalg250.packets.jsonl.gz", "rt")}
gate, sites = {}, {}
for iid, p in packets.items():
    org, site = p["target_company"]["organisation_number"], p["website"]["url"]
    if (org, site) not in sites:
        t = target_from_envelope(envs[org]); page = store.page(site) if site else None
        sites[(org, site)] = (t, assess_site(t, site, page.text) if page else None)
    t, s = sites[(org, site)]
    text = "\n".join(filter(None, [p["item"]["title"], p.get("source_text"), p.get("article_text")]))
    gate[iid] = assess_item(t, s, text).to_dict() if s else {"decision": "withhold", "code": "no_site_capture"}
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results/evalg250-identity-gate.json").write_text(json.dumps(gate, indent=1, ensure_ascii=False), encoding="utf-8")
decisions = {i: g["decision"] for i, g in gate.items()}
recs = {r["item_id"]: r for r in (json.loads(l) for l in open(HERE / "runs/final-evalg250-news-p2-evidence-v1-gemini-3.1-flash-lite.jsonl"))}
frp_v2 = {json.loads(l)["item_id"]: json.loads(l) for l in open(HERE / "audits/evalg250/labels_rubric_v2_frp.jsonl")}
report = {}
for variant in ("rubric_v1_as_reported", "rubric_v2_frp_provisional"):
    items = load_items("evalg250")
    if variant.startswith("rubric_v2"):
        for it in items:
            if it["item_id"] in frp_v2:
                it["label"] = frp_v2[it["item_id"]]["rubric_v2_label"]; it["error_category"] = frp_v2[it["item_id"]]["category"]
    arms = arm_members_v2(items, recs, decisions)
    report[variant] = {arm: score_arm(items, arms[arm], baseline=arms["v31"]) for arm in ARMS_V2}
    print(f"\n### {variant}")
    print(f"{'arm':18} {'pub':>4} {'C':>4} {'I':>4} {'U':>3} {'prec':>7} {'wilson95':>13} {'cluster95':>13} {'cov':>8} {'wrong-co FP':>11}")
    for arm in ARMS_V2:
        s = report[variant][arm]
        w, c = s["precision_wilson95"], s["precision_cluster95"]
        wrong = s["fp_by_category"].get("other_entity_or_unrelated", 0) + s["fp_by_category"].get("wrong_company", 0)
        print(f"{arm:18} {s['published']:4} {s['correct']:4} {s['incorrect']:4} {s['unsure']:3} {100 * s['precision']:6.1f}% "
              f"{100 * w[0]:5.1f}-{100 * w[1]:5.1f}% {100 * c[0]:5.1f}-{100 * c[1]:5.1f}% {s['correct']:3}/{s['correct'] + s['false_negatives']:<4} {wrong:11}")
(HERE / "results/evalg250-gate-rescore-diagnostic.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
