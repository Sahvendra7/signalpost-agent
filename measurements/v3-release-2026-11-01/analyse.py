#!/usr/bin/env python3
"""Analyse the V3 release runs written by run_release.sh.

    uv run python measurements/v3-release-2026-11-01/analyse.py WORK/out > measurements/v3-release-2026-11-01/analysis.json

Per run: contract validation with every snapshot hash re-verified, input order, terminal states, unsupported summary
statements, outbound hosts (any social or other restricted platform is a failure), cost, the viewer, the history, and
refresh events by type. For the reproduction companies: the site-derived facts published and held back.
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
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def run_summary(directory: Path, name: str) -> dict:
    envelopes = load(directory / f"{name}.envelopes.jsonl")
    report = json.loads((directory / f"{name}.report.json").read_text(encoding="utf-8"))
    snapshots = directory / "snapshots"
    findings = collections.Counter(item["code"] for envelope in envelopes for item in validate_envelope(envelope, snapshot_root=snapshots))
    hashed = sum(1 for envelope in envelopes for item in envelope["evidence"] if item.get("snapshot_path"))
    hosts = sorted({line.split("\t", 1)[1].strip() for line in (directory / f"{name}.hosts.tsv").read_text(encoding="utf-8").splitlines() if "\t" in line})
    events = collections.Counter(change.get("change_type") for envelope in envelopes for change in envelope.get("changes") or [])
    baseline_kinds = collections.Counter(((envelope.get("refresh") or {}).get("baseline") or {}).get("kind") for envelope in envelopes)
    viewer = report.get("viewer") or {}
    return {
        "commit": (directory / f"{name}.commit.txt").read_text().strip(),
        "dirty_files": int((directory / f"{name}.dirty-files.txt").read_text().strip() or 0),
        "started": (directory / f"{name}.started.txt").read_text().strip(),
        "envelopes": len(envelopes), "input_rows": report["input_rows"],
        "terminal_status": dict(collections.Counter(envelope["run"]["terminal_status"] for envelope in envelopes)),
        "input_order_preserved": [envelope["input_position"] for envelope in envelopes] == list(range(len(envelopes))),
        "validation_passed": report["validation"]["passed"],
        "contract_findings_with_snapshot_hash_check": dict(findings), "evidence_entries_hash_checked": hashed,
        "code_version_in_every_envelope": all((envelope["run"].get("code_version") or {}).get("source_sha256") for envelope in envelopes),
        "unsupported_summary_statements": sum(len(unsupported_statements(envelope)) for envelope in envelopes),
        "runtime_s": round(report["runtime_ms"] / 1000, 1), "requests": report["operations"]["requests"],
        "third_party_cost_usd": report["operations"]["third_party_cost_usd"],
        "llm_in_report": "llm" in report,
        "hosts_contacted": len(hosts), "restricted_platform_hosts": [host for host in hosts if restricted_platform(host)],
        "viewer_written": bool(viewer.get("written")), "viewer_bytes": viewer.get("bytes"),
        "history": report.get("history"), "baseline": report.get("baseline"), "baseline_kinds": dict(baseline_kinds),
        "change_events": dict(events), "new_items": report.get("new_items"), "checks_withheld_total": sum(((report.get("checks") or {}).get("withheld") or {}).values()),
        "published_site_facts": dict(collections.Counter(claim["field"] for envelope in envelopes for claim in envelope["claims"] if claim["availability"] == "available" and claim["field"] in SITE_FIELDS)),
    }


def company_facts(envelope: dict) -> dict:
    out: dict = {"name": next((claim["value"] for claim in envelope["claims"] if claim["field"] == "legal_name" and claim["availability"] == "available"), None)}
    for field in SITE_FIELDS:
        claims = [claim for claim in envelope["claims"] if claim["field"] == field]
        published = [claim["value"] if isinstance(claim["value"], str) else (claim["value"] or {}).get("title") for claim in claims if claim["availability"] == "available"]
        held = [f"{claim['availability']}: {(claim.get('reason') or '')[:140]}" for claim in claims if claim["availability"] != "available"]
        out[field] = {"published": published[:12], "published_count": len(published), "not_published": held[:3]}
    website = next((claim for claim in envelope["claims"] if claim["field"] == "official_website" and claim["availability"] == "available"), {})
    if website.get("site_role"):
        out["site_role"] = website["site_role"]
    return out


def main(out: Path) -> None:
    result = {"smoke": {name: run_summary(out / "smoke", name) for name in ("live-100", "live-100-refresh")},
              "repro5": run_summary(out / "repro", "repro5")}
    result["repro5_companies"] = {envelope["organisation_number"]: company_facts(envelope) for envelope in load(out / "repro" / "repro5.envelopes.jsonl")}
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
