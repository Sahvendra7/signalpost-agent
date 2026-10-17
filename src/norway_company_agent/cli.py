"""Signalpost batch command: one terminal contract envelope (OUTPUT_CONTRACT.md) per input row.

`scripts/run_competition_batch.py` is a thin wrapper around `main`."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from .batch import profile_complete_for_modules
from .pipeline import DEFAULT_MODULES, read_input_rows, run_batch
from .streaming import JsonlStream, read_jsonl_tolerant
from .viewer import write_viewer

# Fail-safe default only: Builderr has not published the official time budget. The evaluator (or anyone
# running the command) should set SIGNALPOST_DEADLINE_SECONDS / --deadline-seconds to the real budget minus
# a safety margin. 2,700 s leaves headroom over the measured 1,200-company run (22.3 min at 8 workers).
DEFAULT_DEADLINE_SECONDS = 2700.0
DEFAULT_GRACE_SECONDS = 60.0


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_profiles(path: str | None) -> dict[str, dict]:
    if not path or not Path(path).exists():
        return {}
    rows = read_jsonl_tolerant(Path(path))  # an interrupted run may leave one truncated last line
    return {row["organisation_number"]: row for row in rows if row.get("organisation_number")}


def main(argv: list[str] | None = None, **injected) -> None:
    """The evaluator command. `injected` (fetcher, site_fetcher, website_fetcher, resolver) is for offline tests only."""
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
    parser.add_argument("--deadline-seconds", type=float, default=float(os.environ.get("SIGNALPOST_DEADLINE_SECONDS", DEFAULT_DEADLINE_SECONDS)),
                        help="Batch wall-clock budget (default: $SIGNALPOST_DEADLINE_SECONDS or 2700). 0 disables the deadline.")
    parser.add_argument("--grace-seconds", type=float, default=float(os.environ.get("SIGNALPOST_GRACE_SECONDS", DEFAULT_GRACE_SECONDS)),
                        help="No new company starts inside the last N seconds (default: $SIGNALPOST_GRACE_SECONDS or 60)")
    parser.add_argument("--viewer-output", help="Also write a self-contained offline HTML viewer of the results here")
    args = parser.parse_args(argv)

    modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    rows = read_input_rows(args.organisations)
    reuse = {}
    if args.resume:
        reuse = {org: row for org, row in read_profiles(args.profiles_output).items() if profile_complete_for_modules(row, modules)}
    snapshot_root = Path(args.snapshot_dir) if args.snapshot_dir else None
    if snapshot_root:
        snapshot_root.mkdir(parents=True, exist_ok=True)
    # Results are streamed: each envelope (and profile) is appended and fsynced as soon as its company is
    # terminal, so an interrupted run keeps every completed company. At the end both files are rewritten
    # atomically in input order.
    previous_profiles = read_profiles(args.previous_profiles)  # before the streams truncate any file
    envelope_stream = JsonlStream(Path(args.output))
    profile_stream = JsonlStream(Path(args.profiles_output))
    stop_event = threading.Event()

    def request_stop(signum, frame):  # SIGTERM/SIGINT: stop waiting and emit every remaining row now
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    def on_result(envelopes, profile):
        for envelope in envelopes:
            envelope_stream.append(envelope)
        if profile is not None:
            profile_stream.append(profile)

    result = run_batch(
        rows,
        run_id=args.run_id,
        bulk_path=args.bulk,
        modules=modules,
        workers=args.workers,
        previous_profiles=previous_profiles,
        snapshot_root=snapshot_root,
        expected_count=args.expected_count,
        reuse_profiles=reuse,
        deadline_seconds=args.deadline_seconds or None,
        grace_seconds=args.grace_seconds,
        on_result=on_result,
        stop_event=stop_event,
        **injected,
    )
    envelope_stream.close()
    profile_stream.close()
    write_jsonl(Path(args.profiles_output), result["profiles"])
    write_jsonl(Path(args.output), result["envelopes"])
    report = result["report"]
    report["resumed_profiles"] = len(reuse)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.viewer_output:
        try:
            write_viewer(Path(args.viewer_output), result["envelopes"], report)
        except Exception as exc:  # the viewer is a convenience; it never fails a completed run
            print(f"viewer not written: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    summary = {key: report[key] for key in ("run_id", "input_rows", "emitted_envelopes", "terminal_status_counts", "category_available_rate", "runtime_ms", "deadline")}
    summary["validation_passed"] = report["validation"]["passed"]
    registry = report.get("registry") or {}
    summary["registry_snapshot"] = registry.get("snapshot_status") or registry.get("bulk")
    if registry.get("snapshot_status") == "invalid":
        print(f"warning: registry snapshot not used ({registry.get('reason')}); every company used the live registry", file=sys.stderr, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    code = 0 if report["validation"]["passed"] else 1
    if threading.active_count() > 1:
        # Straggler workers from a hard stop may still be inside a network call; all output is already
        # durable, so exit without waiting for them.
        sys.stderr.flush()
        os._exit(code)
    raise SystemExit(code)


