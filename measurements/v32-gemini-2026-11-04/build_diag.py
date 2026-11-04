"""Build the diagnostic datasets (eval200, eval200b) for the V3.2 Gemini experiments.

These sets were used to tune V3.1 and are DIAGNOSTIC ONLY here (prompt and model development); no result on them is
reported as independent. Their original snapshots no longer exist, so:
  * source text = the excerpt the labeller saw (aid.md), i.e. the label basis;
  * article text = the item page captured now (2026-11-04) by the deterministic capture (llm_experiments.capture).

    uv run python measurements/v32-gemini-2026-11-04/build_diag.py
Writes datasets/<set>.items.jsonl (labels) and datasets/<set>.packets.jsonl.gz (model input; no labels).
"""
import gzip, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.llm_experiments.capture import CaptureStore, Fetcher, capture_many, norm_url  # noqa: E402
from norway_company_agent.llm_experiments.datasets import labelled_news_items, org_context, packet_for, read_envelopes  # noqa: E402

HERE = Path(__file__).resolve().parent
V31 = ROOT / "measurements/v31-2026-11-01"
SETS = {"eval200b": (V31 / "audits/eval200b", V31 / "replay/rbase-eval200b/envelopes.jsonl.gz"),
        "eval200": (V31 / "audits/eval200", V31 / "replay/rbase-eval200/envelopes.jsonl.gz")}
store = CaptureStore(ROOT / "out/v32/captures")
fetcher = Fetcher(store, delay_s=1.0)
(HERE / "datasets").mkdir(exist_ok=True)
for name, (audit, env_path) in SETS.items():
    envs = read_envelopes(env_path)
    ctxs = {org: org_context(env) for org, env in envs.items()}
    items = labelled_news_items(audit, envs, name)
    jobs = set()
    for it in items:
        site = ctxs.get(it["org"], {}).get("site_url")
        if not site:
            continue
        jobs.add((site, site))
        if it["url"] and norm_url(it["url"]) != norm_url(it["source_url"]):
            jobs.add((it["url"], site))
    print(name, len(items), "items;", len(jobs), "pages to capture", flush=True)
    rows = capture_many(fetcher, sorted(jobs), workers=8)
    print(name, "captured ok:", sum(bool(r.get("sha256")) for r in rows), "errors:", sum(not r.get("sha256") for r in rows), flush=True)
    with (HERE / f"datasets/{name}.items.jsonl").open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    with gzip.open(HERE / f"datasets/{name}.packets.jsonl.gz", "wt", encoding="utf-8") as fh:
        for it in items:
            ctx = ctxs.get(it["org"]) or {"legal_name": it["company"], "site_url": None}
            fh.write(json.dumps(packet_for(it, ctx, store), ensure_ascii=False) + "\n")
