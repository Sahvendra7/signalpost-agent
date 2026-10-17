#!/usr/bin/env python3
"""Build the self-contained offline HTML viewer from an envelope JSONL (and optional run report).

    uv run python scripts/build_viewer.py --envelopes out/envelopes.jsonl --report out/run-report.json --output out/viewer.html
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.streaming import read_jsonl_tolerant  # noqa: E402
from norway_company_agent.viewer import write_viewer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelopes", required=True, help="Envelope JSONL (or .jsonl.gz)")
    parser.add_argument("--report", help="Optional run report JSON")
    parser.add_argument("--output", required=True, help="HTML file to write")
    args = parser.parse_args()
    path = Path(args.envelopes)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            envelopes = [json.loads(line) for line in handle if line.strip()]
    else:
        envelopes = read_jsonl_tolerant(path)
    report = json.loads(Path(args.report).read_text(encoding="utf-8")) if args.report else None
    write_viewer(Path(args.output), envelopes, report)
    print(json.dumps({"companies": len(envelopes), "output": args.output, "bytes": Path(args.output).stat().st_size}))


if __name__ == "__main__":
    main()
