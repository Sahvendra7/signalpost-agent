"""V3.2 secondary experiments: grounded company synthesis and What's New explanations (gemini-3.5-flash-lite).

Companies come from eval200b (diagnostic; not from the independent evalg250 set). Change events are real
deterministic refresh events except case `correction_synthetic`, a controlled perturbation (one filing value edited
for the same reporting period) that is labelled synthetic everywhere.

    uv run python measurements/v32-gemini-2026-11-04/run_synthesis.py [--live --max-calls N]
"""
import argparse, copy, gzip, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.llm.gemini import GeminiConfig, GeminiProvider  # noqa: E402
from norway_company_agent.llm_experiments.news_contract import canonical, sha  # noqa: E402
from norway_company_agent.llm_experiments.prompts import PromptVersion  # noqa: E402
from norway_company_agent.llm_experiments.runner import Budget, RateLimiter, ResponseCache, _call, paid_cost  # noqa: E402
from norway_company_agent.llm_experiments.synthesis import (CHANGE_SCHEMA, CHANGE_SYSTEM, SYNTH_SCHEMA, SYNTH_SYSTEM, render_events,  # noqa: E402
                                                            synthesis_input, validate_explanations, validate_statements)
from norway_company_agent.refresh import claim_changes  # noqa: E402

HERE = Path(__file__).resolve().parent
MODEL = "gemini-3.5-flash-lite"
SYNTH = PromptVersion("synth-v1", "grounded brief, derived arithmetic", SYNTH_SYSTEM, thinking_level="MINIMAL")
CHANGE = PromptVersion("whatsnew-v1", "explain deterministic events", CHANGE_SYSTEM, thinking_level="MINIMAL")
SYNTH_ORGS = ["988185701", "993973645", "984047320", "922582270", "996569071", "927293056", "963706820", "911814684"]
STABLE = {"identity", "filings", "leadership", "locations", "relationships", "registry_activity"}


def load(path):
    return {json.loads(l)["organisation_number"]: json.loads(l) for l in gzip.open(ROOT / path, "rt", encoding="utf-8")}


def events_between(a, b, categories):
    ca = [c for c in a["claims"] if c.get("category") in categories]
    cb = [c for c in b["claims"] if c.get("category") in categories]
    return claim_changes(ca, a["evidence"], cb, b["evidence"], carried=[], unverified=[])[0]


def change_cases():
    oct17, nov2 = load("measurements/c300-revision-2026-10-17/final-100/envelopes.jsonl.gz"), load("measurements/v31-2026-11-01/release-0e4c426/live-100.envelopes.jsonl.gz")
    refresh = load("measurements/v31-2026-11-01/release-0e4c426/live-100-refresh.envelopes.jsonl.gz")
    base, f2 = load("measurements/v31-2026-11-01/replay/rbase-eval200b/envelopes.jsonl.gz"), load("measurements/v31-2026-11-01/replay/f2-eval200b/envelopes.jsonl.gz")
    cases = []
    changed = [o for o in sorted(set(oct17) & set(nov2)) if events_between(oct17[o], nov2[o], STABLE)]
    unchanged = [o for o in sorted(set(oct17) & set(nov2)) if not events_between(oct17[o], nov2[o], STABLE)]
    for o in changed:
        cases.append(("real_registry_change", o, nov2[o], events_between(oct17[o], nov2[o], STABLE)))
    for o in unchanged[:3]:
        cases.append(("real_no_change", o, nov2[o], []))
    for o, env in sorted(refresh.items()):
        outage = [c for c in env.get("changes") or [] if c.get("change_type") == "unavailable"]
        if outage:
            cases.append(("real_source_outage", o, env, outage))
    for o in ("911814684", "993973645"):
        ev = events_between(base[o], f2[o], {"public_activity"})[:6]
        cases.append(("real_retraction_policy", o, f2[o], ev))
    a = f2["988185701"]; b = copy.deepcopy(a)
    rev = [c for c in b["claims"] if c["field"] == "revenue" and c["availability"] == "available"]
    latest = max(rev, key=lambda c: str((c.get("period") or {}).get("to")))
    latest["value"] = float(latest["value"]) + 125000.0
    cases.append(("correction_synthetic", "988185701", b, events_between(a, b, {"filings"})))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--max-calls", type=int, default=0)
    a = ap.parse_args()
    provider = None
    if a.live:
        cfg = GeminiConfig.from_env(os.environ, model=MODEL, _force_enabled=True)
        provider = GeminiProvider(cfg)
    cache, limiter, budget = ResponseCache(HERE / "cache"), RateLimiter(10), Budget(a.max_calls)
    out = {"synthesis": [], "whats_new": []}
    f2 = load("measurements/v31-2026-11-01/replay/f2-eval200b/envelopes.jsonl.gz")
    for org in SYNTH_ORGS:
        env = f2[org]
        facts, user = synthesis_input(env)
        r = _call(provider, cache, limiter, budget, model=MODEL, prompt=SYNTH, system=SYNTH.system, user=user, schema=SYNTH_SCHEMA,
                  packet_sha=sha(user), stage="synthesis", max_output_tokens=2048)
        name = env["identity"]["legal_name"]
        v = validate_statements(r.get("data") if r.get("ok") else None, facts, name)
        det = sum(len(s["statements"]) for s in env["company_summary"]["sections"])
        out["synthesis"].append({"org": org, "company": name, "ok": r.get("ok"), "error": r.get("error"), "facts": len(facts),
                                 "derived_facts": sum(f["fact_id"].startswith("d") for f in facts), "deterministic_statements": det,
                                 "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"), "latency_ms": r.get("latency_ms"),
                                 "paid_equivalent_cost_usd": paid_cost(MODEL, r.get("input_tokens"), r.get("output_tokens"), r.get("thoughts_tokens")),
                                 "model_version": r.get("model_version"), **v})
    for kind, org, env, events in change_cases():
        rendered = render_events(events)
        user = json.dumps({"company": env["identity"]["legal_name"], "events": rendered}, ensure_ascii=False)
        r = _call(provider, cache, limiter, budget, model=MODEL, prompt=CHANGE, system=CHANGE.system, user=user, schema=CHANGE_SCHEMA,
                  packet_sha=sha(user), stage="whatsnew", max_output_tokens=1500)
        v = validate_explanations(r.get("data") if r.get("ok") else None, rendered, env["identity"]["legal_name"])
        out["whats_new"].append({"case": kind, "synthetic": kind.endswith("synthetic"), "org": org, "company": env["identity"]["legal_name"],
                                 "ok": r.get("ok"), "error": r.get("error"), "events_input": rendered, "input_tokens": r.get("input_tokens"),
                                 "output_tokens": r.get("output_tokens"), "latency_ms": r.get("latency_ms"), **v})
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/synthesis_whatsnew.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for s in out["synthesis"]:
        print(f"SYN {s['company'][:30]:30} ok={s['ok']} facts={s['facts']} acc={len(s['accepted'])} rej={len(s['rejected'])} {[x['reason'] for x in s['rejected']]}")
    for w in out["whats_new"]:
        print(f"NEW {w['case']:24} {w['company'][:24]:24} ok={w['ok']} events={w['events']} explained={w['events_explained']} acc={len(w['accepted'])} rej={[x['reason'] for x in w['rejected']]}")


if __name__ == "__main__":
    main()
