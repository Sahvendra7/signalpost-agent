"""V3.2 secondary experiment: social identity resolution (diagnostic only; eval200/eval200b social units).

Set: every labelled error (8), every 'unsure' (5, reported separately) and 12 random correct profiles (seed 7).
No platform page is fetched; homepage text comes from the deterministic capture store (out/v32/captures).

    uv run python measurements/v32-gemini-2026-11-04/run_social.py [--live --max-calls N]
"""
import argparse, csv, json, os, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from bs4 import BeautifulSoup  # noqa: E402
from norway_company_agent.llm.gemini import GeminiConfig, GeminiProvider  # noqa: E402
from norway_company_agent.llm_experiments import social  # noqa: E402
from norway_company_agent.llm_experiments.capture import CaptureStore  # noqa: E402
from norway_company_agent.llm_experiments.datasets import org_context, read_envelopes  # noqa: E402
from norway_company_agent.llm_experiments.news_contract import sha  # noqa: E402
from norway_company_agent.llm_experiments.prompts import PromptVersion  # noqa: E402
from norway_company_agent.llm_experiments.runner import Budget, RateLimiter, ResponseCache, _call, paid_cost  # noqa: E402

HERE = Path(__file__).resolve().parent
V31 = ROOT / "measurements/v31-2026-11-01"
MODEL = "gemini-3.5-flash-lite"
PROMPT = PromptVersion("social-v1", "captured-evidence ownership", social.SYSTEM, thinking_level="MINIMAL")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true"); ap.add_argument("--max-calls", type=int, default=0)
    a = ap.parse_args()
    store = CaptureStore(ROOT / "out/v32/captures")
    rows = []
    for s in ("eval200b", "eval200"):
        envs = read_envelopes(V31 / f"replay/rbase-{s}/envelopes.jsonl.gz")
        for r in csv.DictReader(open(V31 / f"audits/{s}/items.labelled.csv", encoding="utf-8")):
            if r["category"] == "social_profile":
                rows.append({**r, "set": s, "env": envs.get(r["org"])})
    errors = [r for r in rows if r["verdict"] == "incorrect"]
    unsure = [r for r in rows if r["verdict"] == "unsure"]
    correct = random.Random(7).sample([r for r in rows if r["verdict"] == "correct"], 12)
    provider = GeminiProvider(GeminiConfig.from_env(os.environ, model=MODEL, _force_enabled=True)) if a.live else None
    cache, limiter, budget = ResponseCache(HERE / "cache"), RateLimiter(10), Budget(a.max_calls)
    results = []
    for r in errors + unsure + correct:
        ctx = org_context(r["env"]) if r["env"] else {"legal_name": r["company"], "site_url": None, "relationships": []}
        others = sorted({x["value"] for x in rows if x["org"] == r["org"] and x["source_url"] == r["source_url"] and x["value"] != r["value"]})
        page = store.page(ctx.get("site_url") or "") if ctx.get("site_url") else None
        text = " ".join(BeautifulSoup(page.html, "lxml").get_text(" ").split())[:3500] if page else None
        packet = {"target_company": {"legal_name": ctx["legal_name"], "organisation_number": r["org"], "legal_form": ctx.get("legal_form"),
                                     "known_relationships": ctx.get("relationships")},
                  "website": {"url": ctx.get("site_url"), "operator_assessment": ctx.get("operator_assessment")},
                  "profile": {"url": r["value"], "linked_from": r["source_url"], "other_profiles_on_page": others}, "page_text": text}
        user = social.render(packet)
        res = _call(provider, cache, limiter, budget, model=MODEL, prompt=PROMPT, system=PROMPT.system, user=user, schema=social.SCHEMA,
                    packet_sha=sha(user), stage="social", max_output_tokens=1024)
        v = social.validate(res.get("data") if res.get("ok") else None, packet)
        results.append({"set": r["set"], "org": r["org"], "company": r["company"], "profile": r["value"], "label": r["verdict"], "note": r["note"],
                        "ok": res.get("ok"), "error": res.get("error"), "latency_ms": res.get("latency_ms"), "input_tokens": res.get("input_tokens"),
                        "output_tokens": res.get("output_tokens"), "paid_equivalent_cost_usd": paid_cost(MODEL, res.get("input_tokens"), res.get("output_tokens"), res.get("thoughts_tokens")),
                        "page_text_captured": bool(text), **v})
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/social.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    for x in results:
        print(f"{x['label'][:5]:5} -> {x['final_decision']:9} {str(x['relation'])[:22]:22} {x['company'][:24]:24} {x['profile'][:55]}")


if __name__ == "__main__":
    main()
