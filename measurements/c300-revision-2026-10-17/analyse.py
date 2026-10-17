#!/usr/bin/env python3
"""Analyse every run directory under WORK/out (run_all.sh, run_final.sh; docs/c300-revision.md): contract and hash validation, summary support, hosts,
viewer, and the Revision 1 vs C300-revision difference in site-derived claims.

    uv run python measurements/c300-revision-2026-10-17/analyse.py WORK/out > measurements/c300-revision-2026-10-17/analysis.json
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.summary_check import unsupported_statements  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.website import restricted_platform  # noqa: E402

SITE_FIELDS = ("official_website", "social_profile", "news_item", "job_posting", "careers_page")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def site_facts(envelope: dict) -> set[tuple[str, str]]:
    out = set()
    for claim in envelope["claims"]:
        if claim["availability"] == "available" and claim["field"] in SITE_FIELDS:
            value = claim["value"]
            out.add((claim["field"], value if isinstance(value, str) else json.dumps({key: value.get(key) for key in ("title", "url", "publication_date")}, ensure_ascii=False, sort_keys=True)))
    return out


def run_summary(directory: Path) -> dict:
    envelopes = load(directory / "envelopes.jsonl")
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    snapshots = directory / "snapshots"
    findings = sum(len(validate_envelope(envelope, snapshot_root=snapshots)) for envelope in envelopes)
    hashed = sum(1 for envelope in envelopes for item in envelope["evidence"] if item.get("snapshot_path"))
    hosts = sorted({line.split("\t", 1)[1].strip() for line in (directory / "hosts.tsv").read_text(encoding="utf-8").splitlines() if "\t" in line})
    problems = [problem for envelope in envelopes for problem in unsupported_statements(envelope)]
    texts = [(envelope.get("company_summary") or {}).get("text") or "" for envelope in envelopes]
    viewer = report.get("viewer")
    viewer_file = Path(viewer["path"]) if viewer and viewer.get("path") else None
    return {
        "commit": (directory / "commit.txt").read_text().strip(),
        "started": (directory / "started.txt").read_text().strip(),
        "envelopes": len(envelopes), "input_rows": report["input_rows"],
        "terminal_status": dict(collections.Counter(envelope["run"]["terminal_status"] for envelope in envelopes)),
        "company_status": dict(collections.Counter((envelope.get("company_status") or {}).get("state") for envelope in envelopes)),
        "input_order_preserved": [envelope["input_position"] for envelope in envelopes] == list(range(len(envelopes))),
        "validation_passed": report["validation"]["passed"],
        "contract_findings_with_snapshot_hash_check": findings, "evidence_entries_hash_checked": hashed,
        "runtime_s": round(report["runtime_ms"] / 1000, 1), "requests": report["operations"]["requests"],
        "third_party_cost_usd": report["operations"]["third_party_cost_usd"],
        "area_coverage": report["area_coverage"],
        "changes_total": report["claims"]["changes_total"],
        "change_types": dict(collections.Counter(change.get("change_type") for envelope in envelopes for change in envelope["changes"])),
        "summary_method": sorted({(envelope.get("company_summary") or {}).get("method") for envelope in envelopes}),
        "summary_statements": sum(len(section["statements"]) for envelope in envelopes for section in (envelope.get("company_summary") or {}).get("sections") or []),
        "summary_unsupported_statements": len(problems), "summary_unsupported_examples": problems[:5],
        "summary_with_period_comparison": sum("Compared with the preceding reporting period" in text for text in texts),
        "summary_periods_not_compared": sum("so no change is inferred" in text for text in texts),
        "summary_employee_count_unknown": sum("Employee count: unknown" in text for text in texts),
        "summary_zero_employee_statements": sum("Employees reported to the registry: 0." in text for text in texts),
        "platform_hosts_contacted": [host for host in hosts if restricted_platform(host)],
        "wordpress_com_contacted": any(host in ("wordpress.com", "www.wordpress.com") for host in hosts),
        "brave_or_nav_hosts": [host for host in hosts if "brave" in host or host.endswith("nav.no")],
        "viewer": viewer, "viewer_file_exists": bool(viewer_file and viewer_file.is_file()),
        "errors": dict(collections.Counter(error["code"] for envelope in envelopes for error in envelope["errors"])),
    }


def main() -> None:
    out = Path(sys.argv[1])
    result = {path.parent.name: run_summary(path.parent) for path in sorted(out.glob("*/report.json"))}
    candidate = "final-100" if (out / "final-100").is_dir() else "new-100"
    old = {envelope["organisation_number"]: site_facts(envelope) for envelope in load(out / "r1-100" / "envelopes.jsonl")}
    new = {envelope["organisation_number"]: site_facts(envelope) for envelope in load(out / candidate / "envelopes.jsonl")}
    result["r1_vs_new_site_facts"] = {
        "runs": ["r1-100", candidate],
        "companies_with_any_difference": sorted(org for org in old if old[org] != new.get(org)),
        "only_in_r1": {org: sorted(old[org] - new.get(org, set())) for org in old if old[org] - new.get(org, set())},
        "only_in_new": {org: sorted(new.get(org, set()) - old[org]) for org in old if new.get(org, set()) - old[org]},
    }
    hjs_run = next((name for name in ("final-911771098", "new-911771098") if (out / name / "envelopes.jsonl").exists()), None)
    hjs = load(out / hjs_run / "envelopes.jsonl")[0] if hjs_run else None
    if hjs:
        result["911771098"] = {
            "run": hjs_run,
            "official_website": [claim["value"] for claim in hjs["claims"] if claim["field"] == "official_website" and claim["availability"] == "available"],
            "social_profile": [(claim["availability"], claim["value"], claim.get("reason")) for claim in hjs["claims"] if claim["field"] == "social_profile"],
            "news_items": sum(1 for claim in hjs["claims"] if claim["field"] == "news_item" and claim["availability"] == "available"),
            "wordpress_profile_urls_in_envelope": [url for url in ("linkedin.com/company/wordpress", "facebook.com/WordPresscom", "instagram.com/wordpressdotcom") if url in json.dumps(hjs, ensure_ascii=False)],
        }
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
