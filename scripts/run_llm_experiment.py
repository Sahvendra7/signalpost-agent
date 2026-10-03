#!/usr/bin/env python3
"""Experiment-only batch run with the optional LLM layer explicitly on or off (one A/B arm).

  # arm A: exactly the V2 batch (no LLM, whatever the environment says)
  uv run python scripts/run_llm_experiment.py --llm-disabled --organisations sample.jsonl --out out/llm-ab/s1/disabled

  # arm B: same companies, LLM layer on; needs LLM_ENABLED=true, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
  uv run python scripts/run_llm_experiment.py --llm-enabled --organisations sample.jsonl --out out/llm-ab/s1/enabled

The evaluator-facing command (scripts/run_competition_batch.py) never enables the LLM. `--llm-enabled`
refuses to run without complete credentials rather than silently producing a disabled arm. Writes
envelopes.jsonl, profiles.jsonl, report.json and llm-audit.jsonl (every LLM-derived claim, for the
manual precision audit) under --out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.llm import LLMLayer  # noqa: E402
from norway_company_agent.pipeline import DEFAULT_MODULES, read_input_rows, run_batch  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def audit_rows(envelopes: list[dict]) -> list[dict]:
    rows = []
    for envelope in envelopes:
        evidence = {item["id"]: item for item in envelope.get("evidence", [])}
        for claim in envelope.get("claims", []):
            if claim.get("derivation") != "llm_extraction":
                continue
            cited = evidence.get((claim.get("evidence_ids") or [None])[0], {})
            rows.append({
                "organisation_number": envelope.get("organisation_number"),
                "legal_name": next((item["value"] for item in envelope["claims"] if item["field"] == "legal_name" and item["availability"] == "available"), None),
                "official_website": next((item["value"] for item in envelope["claims"] if item["field"] == "official_website" and item["availability"] == "available"), None),
                "field": claim["field"], "value": claim["value"], "evidence_span": claim.get("evidence_span"),
                "source_url": cited.get("source_url"), "content_sha256": cited.get("content_sha256"), "retrieved_at": cited.get("retrieved_at"),
                "snapshot_path": cited.get("snapshot_path"), "audit_verdict": None,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="One arm of the LLM A/B experiment (never the official batch command)")
    arm = parser.add_mutually_exclusive_group(required=True)
    arm.add_argument("--llm-enabled", action="store_true", help="Use the LLM layer configured by LLM_* environment variables")
    arm.add_argument("--llm-disabled", action="store_true", help="Deterministic V2 only (ignores LLM_* variables)")
    parser.add_argument("--organisations", required=True)
    parser.add_argument("--out", required=True, help="Output directory for this arm")
    parser.add_argument("--bulk")
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--modules", default=",".join(DEFAULT_MODULES))
    parser.add_argument("--no-snapshots", action="store_true", help="Skip storing captured bytes (the audit then cannot re-hash)")
    args = parser.parse_args()

    layer = None
    if args.llm_enabled:
        layer = LLMLayer.from_env()
        if not layer.enabled:
            parser.error(f"--llm-enabled needs a complete LLM configuration: {layer.config.disabled_reason}")
    out = Path(args.out)
    snapshots = None if args.no_snapshots else out / "snapshots"
    if snapshots:
        snapshots.mkdir(parents=True, exist_ok=True)
    rows = read_input_rows(args.organisations)
    label = "llm-enabled" if args.llm_enabled else "llm-disabled"
    result = run_batch(
        rows, run_id=args.run_id or f"{label}-{Path(args.organisations).stem}", bulk_path=args.bulk,
        modules=[item.strip() for item in args.modules.split(",") if item.strip()], workers=args.workers,
        snapshot_root=snapshots, llm_layer=layer,
    )
    report = result["report"]
    report["experiment_arm"] = label
    write_jsonl(out / "envelopes.jsonl", result["envelopes"])
    write_jsonl(out / "profiles.jsonl", result["profiles"])
    write_jsonl(out / "llm-audit.jsonl", audit_rows(result["envelopes"]))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"arm": label, "input_rows": report["input_rows"], "validation_passed": report["validation"]["passed"], "runtime_ms": report["runtime_ms"], "llm_calls": report["operations"]["llm_calls"]}
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if report["validation"]["passed"] else 1)


if __name__ == "__main__":
    main()
