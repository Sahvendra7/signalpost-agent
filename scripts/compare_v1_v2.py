#!/usr/bin/env python3
"""Run the batch command as V1 (no site_research) and V2 (default) on the same samples and compare.

  uv run python scripts/compare_v1_v2.py --sample fixed=out/experiments/sample.jsonl \
      --sample s1=out/v2/sample-s1.jsonl --out out/v2

Each run goes through scripts/run_competition_batch.py, the evaluator-facing command, with a snapshot
directory so every evidence hash can be re-verified. Measurement only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.pipeline import V1_MODULES  # noqa: E402

AREAS = ("filings", "leadership", "locations", "websites", "public_footprint", "hiring")


def run(version: str, sample: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(ROOT / "scripts" / "run_competition_batch.py"), "--organisations", str(sample),
               "--profiles-output", str(out / "profiles.jsonl"), "--output", str(out / "envelopes.jsonl"),
               "--report", str(out / "report.json"), "--run-id", f"{version}-{sample.stem}", "--snapshot-dir", str(out / "snapshots")]
    if version == "v1":
        command += ["--modules", ",".join(V1_MODULES)]
    started = time.monotonic()
    completed = subprocess.run(command, capture_output=True, text=True)
    wall = time.monotonic() - started
    (out / "stdout.txt").write_text(completed.stdout + completed.stderr)
    envelopes = [json.loads(line) for line in (out / "envelopes.jsonl").read_text().splitlines() if line.strip()]
    report = json.loads((out / "report.json").read_text())
    from norway_company_agent.claims import area_coverage

    areas = {area: sum(1 for item in envelopes if area_coverage(item["claims"])[area]) for area in AREAS}
    five = sum(1 for item in envelopes if all(area_coverage(item["claims"])[a] for a in ("filings", "leadership", "locations", "websites")) and (area_coverage(item["claims"])["public_footprint"] or area_coverage(item["claims"])["hiring"]))
    invalid = sum(1 for item in envelopes if validate_envelope(item, snapshot_root=out / "snapshots"))
    claims = [claim for item in envelopes for claim in item["claims"] if claim["availability"] == "available"]
    websites = {}
    for item in envelopes:
        for claim in item["claims"]:
            if claim["field"] == "official_website" and claim["availability"] == "available":
                websites[item["organisation_number"]] = {"url": claim["value"], "class": claim.get("identity_class") or "REGISTRY_LINKED (v1 gate)", "source": claim.get("identity_source") or "registry_hjemmeside", "method": claim.get("method"), "evidence": next(ev["claim_span"] for ev in item["evidence"] if ev["id"] == claim["evidence_ids"][0])[:160]}
    return {
        "exit": completed.returncode, "wall_s": round(wall, 1), "runtime_ms": report["runtime_ms"], "inputs": report["input_rows"], "envelopes": report["emitted_envelopes"],
        "validation_passed": report["validation"]["passed"], "envelopes_failing_hash_or_contract": invalid,
        "requests": report["operations"]["requests"], "bytes": report["operations"]["bytes"],
        "areas": areas, "companies_all_five_areas": five,
        "verified_facts": len(claims), "profiles": sum(1 for claim in claims if claim["field"] == "social_profile"),
        "dated_activities": sum(1 for claim in claims if claim["field"] == "site_activity"), "job_postings": sum(1 for claim in claims if claim["field"] == "job_posting"),
        "careers_pages": sum(1 for claim in claims if claim["field"] == "careers_page"),
        "terminal": report["terminal_status_counts"], "error_codes": report["error_codes"], "websites": websites,
        "company_runtime": report["operations"]["company_runtime"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="append", required=True, help="label=path")
    parser.add_argument("--out", required=True)
    parser.add_argument("--versions", default="v1,v2", help="Re-run only these; others are kept from comparison.json")
    args = parser.parse_args()
    previous = Path(args.out, "comparison.json")
    results = json.loads(previous.read_text()) if previous.exists() else {}
    for item in args.sample:
        label, path = item.split("=", 1)
        for version in [item for item in args.versions.split(",") if item]:
            results.setdefault(label, {})[version] = run(version, Path(path), Path(args.out) / label / version)
            print(label, version, json.dumps({k: v for k, v in results[label][version].items() if k != "websites"}), flush=True)
        Path(args.out, "comparison.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
