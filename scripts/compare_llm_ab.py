#!/usr/bin/env python3
"""A/B the optional LLM layer on the same companies: --llm-disabled (A, V2) vs --llm-enabled (B).

  uv run python scripts/compare_llm_ab.py --sample s1=out/v2/sample-s1.jsonl --out out/llm-ab

Each arm runs through scripts/run_llm_experiment.py with a snapshot directory. Measurement only: this
script claims no score change. Metrics per sample (and summed):

  llm_calls, tokens (when the endpoint reports them), runtime per arm, facts added, public-footprint
  companies added, synthesis completeness, rejected LLM facts by reason, and precision checks:
    * llm_grounding_failures   LLM claims whose evidence span is not in the captured page bytes (re-read from
                               the snapshot) -- must be 0
    * llm_identity_changes     companies whose official_website differs between arms -- the LLM must never
                               change identity; a non-zero value can also be live-web drift between the two
                               runs, so each case is listed for inspection
    * wrong_company_llm_claims needs the manual audit of B's llm-audit.jsonl (left null until audited)
Within-arm deltas (B's own LLM claims vs B's deterministic claims) are immune to web drift between arms.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.claims import area_coverage  # noqa: E402
from norway_company_agent.contract import snapshot_relative_path, validate_envelope  # noqa: E402
from norway_company_agent.llm.tasks import prepare_page, span_in_text  # noqa: E402


def run_arm(arm: str, sample: Path, out: Path, workers: int) -> dict:
    command = [sys.executable, str(ROOT / "scripts" / "run_llm_experiment.py"), f"--llm-{arm}", "--organisations", str(sample), "--out", str(out), "--workers", str(workers)]
    started = time.monotonic()
    completed = subprocess.run(command, capture_output=True, text=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stdout.txt").write_text(completed.stdout + completed.stderr)
    if not (out / "report.json").exists():
        raise SystemExit(f"{arm} arm produced no report (exit {completed.returncode}):\n{completed.stderr[-2000:]}")
    return {"exit": completed.returncode, "wall_s": round(time.monotonic() - started, 1)}


def load(out: Path) -> tuple[list[dict], dict]:
    envelopes = [json.loads(line) for line in (out / "envelopes.jsonl").read_text().splitlines() if line.strip()]
    return envelopes, json.loads((out / "report.json").read_text())


def website(envelope: dict) -> str | None:
    return next((claim["value"] for claim in envelope["claims"] if claim["field"] == "official_website" and claim["availability"] == "available"), None)


def grounding_failures(envelopes: list[dict], snapshots: Path) -> list[dict]:
    """Re-read each LLM claim's cited page from the snapshot store and look for its span again."""
    failures = []
    texts: dict[str, str] = {}
    for envelope in envelopes:
        evidence = {item["id"]: item for item in envelope["evidence"]}
        for claim in envelope["claims"]:
            if claim.get("derivation") != "llm_extraction":
                continue
            cited = evidence.get(claim["evidence_ids"][0], {})
            sha = cited.get("content_sha256") or ""
            path = snapshots / snapshot_relative_path(sha)
            if sha not in texts:
                texts[sha] = prepare_page(cited.get("source_url") or "", path.read_bytes(), retrieved_at="", content_sha256=sha, max_chars=10**7).text if path.is_file() else ""
            if not texts[sha] or not span_in_text(claim.get("evidence_span"), texts[sha]):
                failures.append({"organisation_number": envelope["organisation_number"], "field": claim["field"], "span": claim.get("evidence_span"), "snapshot_found": bool(texts[sha])})
    return failures


def compare(label: str, a_dir: Path, b_dir: Path, walls: dict) -> dict:
    a, a_report = load(a_dir)
    b, b_report = load(b_dir)
    by_org_a = {item["organisation_number"]: item for item in a}
    available = lambda envelope: [claim for claim in envelope["claims"] if claim["availability"] == "available"]  # noqa: E731
    footprint = lambda envelope: area_coverage(envelope["claims"])["public_footprint"]  # noqa: E731
    llm_claims = [claim for item in b for claim in available(item) if claim.get("derivation") == "llm_extraction"]
    footprint_only_via_llm = sum(1 for item in b if footprint(item) and not area_coverage([claim for claim in item["claims"] if claim.get("derivation") != "llm_extraction"])["public_footprint"])
    identity_changes = [
        {"organisation_number": org, "disabled": website(by_org_a.get(org, {"claims": []})), "enabled": website(item)}
        for item in b if (org := item["organisation_number"]) and website(by_org_a.get(org, {"claims": []})) != website(item)
    ]
    llm = b_report.get("llm") or {}
    syntheses = [item["company_synthesis"] for item in b if item.get("company_synthesis")]
    completeness = [item["completeness"] for item in syntheses if item.get("completeness") is not None]
    return {
        "sample": label,
        "companies": len(b),
        "valid_envelopes": {"disabled": sum(1 for item in a if not validate_envelope(item, snapshot_root=a_dir / "snapshots")), "enabled": sum(1 for item in b if not validate_envelope(item, snapshot_root=b_dir / "snapshots"))},
        "runtime": {"disabled_wall_s": walls["disabled"]["wall_s"], "enabled_wall_s": walls["enabled"]["wall_s"], "disabled_batch_ms": a_report["runtime_ms"], "enabled_batch_ms": b_report["runtime_ms"]},
        "llm_calls": llm.get("calls", 0),
        "llm_calls_by_task": llm.get("calls_by_task", {}),
        "llm_calls_per_company": round(llm.get("calls", 0) / max(1, len(b)), 3),
        "tokens": {"input": llm.get("input_tokens"), "output": llm.get("output_tokens")},
        "facts": {"disabled_available": sum(len(available(item)) for item in a), "enabled_available": sum(len(available(item)) for item in b), "llm_derived": len(llm_claims), "llm_derived_by_field": dict(Counter(claim["field"] for claim in llm_claims))},
        "public_footprint_companies": {"disabled": sum(1 for item in a if footprint(item)), "enabled": sum(1 for item in b if footprint(item)), "enabled_only_via_llm_claims": footprint_only_via_llm},
        "synthesis": {"companies_with_synthesis": len(syntheses), "completeness_mean": round(sum(completeness) / len(completeness), 3) if completeness else None},
        "rejected_llm_items": {"total": llm.get("rejected_total", 0), "by_reason": llm.get("rejected_by_reason", {})},
        "llm_failures": llm.get("failures_by_reason", {}),
        "precision": {
            "llm_grounding_failures": grounding_failures(b, b_dir / "snapshots"),
            "llm_identity_changes": identity_changes,
            "wrong_company_llm_claims": None,
            "manual_audit_file": str(b_dir / "llm-audit.jsonl"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="append", required=True, help="label=path")
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    results = {}
    for item in args.sample:
        label, path = item.split("=", 1)
        walls = {arm: run_arm(arm, Path(path), Path(args.out) / label / arm, args.workers) for arm in ("disabled", "enabled")}
        results[label] = compare(label, Path(args.out) / label / "disabled", Path(args.out) / label / "enabled", walls)
        summary = {key: value for key, value in results[label].items() if key != "precision"}
        summary["precision"] = {"llm_grounding_failures": len(results[label]["precision"]["llm_grounding_failures"]), "llm_identity_changes": len(results[label]["precision"]["llm_identity_changes"])}
        print(label, json.dumps(summary, ensure_ascii=False), flush=True)
        Path(args.out, "comparison.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
