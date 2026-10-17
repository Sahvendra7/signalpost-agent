#!/usr/bin/env python3
"""Verify one validation run directory and write analysis.json (validation only).

    python measurements/final-validation-2026-10-03/analyse_run.py RUN_DIR INPUT_JSONL [--expect-refresh]
"""
from __future__ import annotations

import collections
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.inputs import read_input_rows  # noqa: E402
from norway_company_agent.synthesis import company_summary  # noqa: E402

PLATFORM_HOSTS = re.compile(r"(^|\.)(linkedin\.com|facebook\.com|instagram\.com|youtube\.com|x\.com|twitter\.com|tiktok\.com|fb\.com)$")
FORBIDDEN_HOSTS = re.compile(r"(^|\.)(publicsuffix\.org|raw\.githubusercontent\.com|api\.search\.brave\.com|arbeidsplassen\.nav\.no|pam-stilling-feed\.nav\.no)$")
SECRET_PATTERNS = [re.compile(pattern) for pattern in (r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", r"\bsk-[A-Za-z0-9]{20,}", r"(?i)api[_-]?key\"?\s*[:=]\s*\"[A-Za-z0-9]{16,}", r"BSA[A-Za-z0-9_-]{20,}")]


def main() -> None:
    run = Path(sys.argv[1])
    rows = read_input_rows(sys.argv[2])
    envelopes = [json.loads(line) for line in (run / "envelopes.jsonl").read_text(encoding="utf-8").splitlines()]
    profiles_text = (run / "profiles.jsonl").read_text(encoding="utf-8")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    expected = [row.organisation_number or (str(row.raw) if row.raw is not None else None) for row in rows]
    out: dict = {"run_dir": str(run.relative_to(ROOT)) if run.is_relative_to(ROOT) else str(run), "input_rows": len(rows), "envelopes": len(envelopes)}
    out["one_per_row"] = len(envelopes) == len(rows)
    out["input_order"] = [item.get("input_organisation_number") for item in envelopes] == expected
    out["positions"] = [item.get("input_position") for item in envelopes] == list(range(len(rows)))
    out["validation_passed"] = report["validation"]["passed"]
    out["contract_findings"] = sum(1 for item in envelopes if validate_envelope(item))
    out["terminal_status"] = dict(collections.Counter(item["run"]["terminal_status"] for item in envelopes))
    out["company_status"] = dict(collections.Counter((item.get("company_status") or {}).get("state") for item in envelopes))
    out["partial_reasons"] = dict(collections.Counter(reason.split(":")[0] + (":" + reason.split(":")[1].strip() if ":" in reason else "") for item in envelopes for reason in (item.get("company_status") or {}).get("reasons") or []).most_common(12))
    duplicate_claims = 0
    for item in envelopes:
        keys = [claim["key"] for claim in item["claims"]]
        duplicate_claims += len(keys) - len(set(keys))
    out["duplicate_claims"] = duplicate_claims
    deterministic = 0
    for item in envelopes:
        stripped = {key: value for key, value in item.items() if key != "company_summary"}
        deterministic += company_summary(copy.deepcopy(stripped)) == item.get("company_summary")
    out["summaries_present"] = sum(1 for item in envelopes if item.get("company_summary"))
    out["summaries_deterministic"] = deterministic
    out["summaries_sparse"] = sum(1 for item in envelopes if (item.get("company_summary") or {}).get("sparse"))
    out["area_coverage"] = {area: sum(1 for item in envelopes if (item.get("area_coverage") or {}).get(area)) for area in ("filings", "leadership", "locations", "websites", "public_footprint", "hiring")}
    out["changes"] = dict(collections.Counter(change["change_type"] for item in envelopes for change in item.get("changes") or []))
    out["refresh_compared"] = sum(1 for item in envelopes if (item.get("refresh") or {}).get("compared"))
    out["material_changes"] = [
        {"org": item["organisation_number"], "type": change["change_type"], "field": change.get("field") or change.get("module"), "old": change.get("old_value"), "new": change.get("new_value")}
        for item in envelopes for change in item.get("changes") or [] if change["change_type"] in {"added", "removed", "changed", "unverified"}
    ]
    out["carried_forward_claims"] = sum(1 for item in envelopes for claim in item["claims"] if claim.get("carried_forward"))
    out["deadline"] = report.get("deadline")
    out["runtime_ms"] = report.get("runtime_ms")
    out["requests"] = report.get("requests") or report.get("operations", {}).get("requests")
    out["registry"] = report.get("registry")
    out["viewer_bytes"] = (run / "viewer.html").stat().st_size if (run / "viewer.html").exists() else None
    blobs = [profiles_text, (run / "envelopes.jsonl").read_text(encoding="utf-8"), json.dumps(report)]
    snapshot_files = [path for path in (run / "snapshots").rglob("*") if path.is_file()] if (run / "snapshots").exists() else []
    out["snapshot_files"] = len(snapshot_files)
    out["birth_date_hits"] = {
        "envelopes_profiles_report": sum(blob.count("fodselsdato") for blob in blobs),
        "snapshots": sum(1 for path in snapshot_files if b"fodselsdato" in path.read_bytes()),
    }
    out["secret_pattern_hits"] = sum(len(pattern.findall(blob)) for pattern in SECRET_PATTERNS for blob in blobs)
    hosts_file = run / "hosts.tsv"
    if hosts_file.exists():
        hosts = [line.split("\t") for line in hosts_file.read_text().splitlines() if "\t" in line]
        names = sorted({host for _, host in hosts if host})
        out["hosts_distinct"] = len(names)
        out["hosts_forbidden"] = [host for host in names if FORBIDDEN_HOSTS.search(host)]
        out["hosts_platform"] = [host for host in names if PLATFORM_HOSTS.search(host)]
        out["brreg_hosts"] = [host for host in names if host.endswith("brreg.no")]
    (run / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n")
    print(json.dumps({key: value for key, value in out.items() if key != "material_changes"}, ensure_ascii=False, indent=1, default=str))
    print("material_changes:", len(out["material_changes"]))


if __name__ == "__main__":
    main()
