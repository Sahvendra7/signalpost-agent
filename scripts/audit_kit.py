#!/usr/bin/env python3
"""Manual audit kit (V3 design §B9).

Sample (blind to which code produced each item):

    uv run python scripts/audit_kit.py sample --arm base=OUT_A/envelopes.jsonl --arm v3=OUT_B/envelopes.jsonl \
        [--per-stratum 15] --seed 7 --out audit-DIR

  writes audit-DIR/items.csv (to label), audit-DIR/checklist.html (label in a browser, then download the CSV) and
  audit-DIR/arms.json (which arm published each item; kept out of the labelling files).

Score:

    uv run python scripts/audit_kit.py score --labels audit-DIR/items.labelled.csv --arms audit-DIR/arms.json \
        --baseline base --candidate v3 --labeller "Name" --labeller-kind owner --out audit-DIR/audit-results

Labeller kinds: owner, other_person, assistant_blind. Results are local engineering measurements, not Builderr scores.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent import audit  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost manual audit kit")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--arm", action="append", required=True, help="name=envelopes.jsonl[.gz]")
    s.add_argument("--per-stratum", type=int, default=None, help="unchanged units per category (default: all)")
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--out", required=True)
    c = sub.add_parser("score")
    c.add_argument("--labels", required=True)
    c.add_argument("--arms", required=True)
    c.add_argument("--baseline")
    c.add_argument("--candidate")
    c.add_argument("--labeller", required=True)
    c.add_argument("--labeller-kind", required=True, choices=["owner", "other_person", "assistant_blind"])
    c.add_argument("--out", required=True, help="output path without extension (.json and .md are written)")
    args = parser.parse_args()
    if args.command == "sample":
        arms = {}
        for item in args.arm:
            name, _, path = item.partition("=")
            arms[name] = audit.read_envelopes(path)
        units, present = audit.align(arms)
        rows = audit.sample(units, present, per_stratum=args.per_stratum, seed=args.seed)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        audit.write_csv(out / "items.csv", rows)
        (out / "checklist.html").write_text(audit.render_checklist(rows), encoding="utf-8")
        (out / "arms.json").write_text(json.dumps({row["uid"]: present[row["uid"]] for row in rows}, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"{len(rows)} units -> {out}/items.csv, checklist.html, arms.json")
    else:
        present = json.loads(Path(args.arms).read_text(encoding="utf-8"))
        result = audit.score(audit.read_csv(args.labels), present, baseline=args.baseline, candidate=args.candidate,
                             labeller=args.labeller, labeller_kind=args.labeller_kind)
        Path(args.out + ".json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        Path(args.out + ".md").write_text(audit.results_markdown(result), encoding="utf-8")
        print(audit.results_markdown(result))


if __name__ == "__main__":
    main()
