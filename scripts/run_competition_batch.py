#!/usr/bin/env python3
"""Signalpost batch command: one terminal contract envelope (OUTPUT_CONTRACT.md) per input row."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import profile_complete_for_modules  # noqa: E402
from norway_company_agent.pipeline import DEFAULT_MODULES, read_input_rows, run_batch  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def read_profiles(path: str | None) -> dict[str, dict]:
    if not path or not Path(path).exists():
        return {}
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["organisation_number"]: row for row in rows if row.get("organisation_number")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluator-owned Signalpost batch contract")
    parser.add_argument("--organisations", required=True, help="JSONL (or JSON/text) organisation-number list")
    parser.add_argument("--bulk", help="Optional Brreg entity bulk snapshot (gzip CSV); the live registry is used when absent")
    parser.add_argument("--output", required=True, help="Terminal envelope JSONL, one line per input row")
    parser.add_argument("--profiles-output", required=True, help="Internal per-company profiles (also the next run's --previous-profiles)")
    parser.add_argument("--report", required=True, help="Machine-readable run report")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-count", type=int, help="Optional guard; a mismatch is reported, never a reason to drop rows")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--modules", default=",".join(DEFAULT_MODULES))
    parser.add_argument("--previous-profiles", help="Profiles JSONL from an earlier run; material changes are emitted per envelope")
    parser.add_argument("--snapshot-dir", help="Store the exact source bytes behind each evidence hash here")
    parser.add_argument("--resume", action="store_true", help="Reuse profiles in --profiles-output whose modules are all terminal")
    args = parser.parse_args()

    modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    rows = read_input_rows(args.organisations)
    reuse = {}
    if args.resume:
        reuse = {org: row for org, row in read_profiles(args.profiles_output).items() if profile_complete_for_modules(row, modules)}
    snapshot_root = Path(args.snapshot_dir) if args.snapshot_dir else None
    if snapshot_root:
        snapshot_root.mkdir(parents=True, exist_ok=True)
    result = run_batch(
        rows,
        run_id=args.run_id,
        bulk_path=args.bulk,
        modules=modules,
        workers=args.workers,
        previous_profiles=read_profiles(args.previous_profiles),
        snapshot_root=snapshot_root,
        expected_count=args.expected_count,
        reuse_profiles=reuse,
    )
    write_jsonl(Path(args.profiles_output), result["profiles"])
    write_jsonl(Path(args.output), result["envelopes"])
    report = result["report"]
    report["resumed_profiles"] = len(reuse)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: report[key] for key in ("run_id", "input_rows", "emitted_envelopes", "terminal_status_counts", "category_available_rate", "runtime_ms")}
    summary["validation_passed"] = report["validation"]["passed"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["validation"]["passed"] else 1)


if __name__ == "__main__":
    main()
