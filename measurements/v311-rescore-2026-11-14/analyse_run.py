"""Release checks for one run directory: completion, contract, evidence hashes, outbound hosts, cost, published facts.

    uv run python measurements/v311-rescore-2026-11-14/analyse_run.py RUN_DIR NAME [--detail]
"""
import hashlib, json, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tests"))
from norway_company_agent.contract import validate_envelope
from helpers.summary_check import unsupported_statements

run, name = Path(sys.argv[1]), sys.argv[2]
envs = [json.loads(l) for l in open(run / f"{name}.envelopes.jsonl", encoding="utf-8")]
report = json.loads((run / f"{name}.report.json").read_text())
findings = [(e["organisation_number"], f) for e in envs for f in validate_envelope(e)]
checked = bad = missing = 0
for e in envs:
    for ev in e["evidence"]:
        sha = ev.get("content_sha256")
        if not sha:
            continue
        path = run / "snapshots" / sha[:2] / f"{sha}.bin"
        if not path.exists():
            missing += 1; continue
        checked += 1
        bad += hashlib.sha256(path.read_bytes()).hexdigest() != sha
hosts = {line.split("\t")[1].strip() for line in open(run / f"{name}.hosts.tsv") if "\t" in line}
platform = sorted(h for h in hosts if any(p in h for p in ("linkedin", "facebook", "instagram", "youtube", "twitter", "x.com", "tiktok")))
fields = ("official_website", "social_profile", "news_item", "job_posting", "careers_page")
pub = collections.Counter(c["field"] for e in envs for c in e["claims"] if c["availability"] == "available" and c["field"] in fields)
unsupported = sum(len(unsupported_statements(e)) for e in envs)
out = {"run": name, "envelopes": len(envs), "terminal": dict(collections.Counter(e["run"]["terminal_status"] for e in envs)),
       "input_order_kept": [e["input_position"] for e in envs] == sorted(e["input_position"] for e in envs),
       "validation_passed": report.get("validation_passed"), "contract_findings": len(findings), "evidence_hashes_checked": checked,
       "evidence_hash_mismatches": bad, "evidence_without_snapshot": missing, "hosts": len(hosts), "social_platform_hosts": platform,
       "third_party_cost_usd": sum(float(e["operations"].get("third_party_cost_usd") or 0) for e in envs),
       "unsupported_summary_statements": unsupported, "published": dict(pub),
       "code_version": envs[0]["run"].get("code_version"), "llm": report.get("llm") or report.get("llm_enabled")}
for key in ("refresh", "baseline", "new_items", "checks"):
    if key in report:
        out[key] = report[key]
print(json.dumps(out, ensure_ascii=False, indent=1, default=str)[:6000])
if "--detail" in sys.argv:
    for e in envs:
        print("==", e["organisation_number"], e["identity"].get("legal_name"))
        for c in e["claims"]:
            if c["field"] in fields and c["availability"] in ("available", "ambiguous"):
                v = c["value"]; v = v if isinstance(v, str) else (v or {}).get("title") or (v or {}).get("url") or v
                why = (c.get("attribution") or {}).get("code") or c.get("reason") or ""
                print(f"   {c['availability'][:5]} {c['field']:16s} {str(v)[:85]} | {str(why)[:70]}")
