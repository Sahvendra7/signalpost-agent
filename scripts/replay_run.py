#!/usr/bin/env python3
"""Replay a captured run through this code tree, with no network (V3 measurement methodology, design §B13).

    uv run python scripts/replay_run.py --captured-profiles BASE/profiles.jsonl --captured-snapshots BASE/snapshots \
        --organisations INPUT.jsonl --output OUT/envelopes.jsonl --profiles-output OUT/profiles.jsonl \
        --report OUT/report.json --snapshot-dir OUT/snapshots --run-id RUN_ID [other run_competition_batch flags]

Every flag other than --captured-* is passed to the documented batch command unchanged; the registry, company-site
and website-module fetchers are replaced by `norway_company_agent.replay.ReplayFetchers` over the captured bytes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.cli import main as batch_main  # noqa: E402
from norway_company_agent.replay import ReplayFetchers, load_profiles  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--captured-profiles", required=True)
    parser.add_argument("--captured-snapshots", required=True)
    args, rest = parser.parse_known_args()
    fetchers = ReplayFetchers(load_profiles(args.captured_profiles), args.captured_snapshots)
    batch_main(rest, **fetchers.injected())


if __name__ == "__main__":
    main()
