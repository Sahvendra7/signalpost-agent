"""Run the real evaluator CLI (norway_company_agent.cli.main) against the offline fake web.

  python tests/helpers/cli_with_fakes.py --count 40 --delay 0.05 -- <cli arguments>
Used by the kill/timeout tests to exercise streaming, signals and deadlines in a real process."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    split = sys.argv.index("--")
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--write-input")
    options = parser.parse_args(sys.argv[1:split])
    orgs = valid_orgs(options.count)
    if options.write_input:
        Path(options.write_input).write_text("".join(json.dumps({"organisation_number": org}) + "\n" for org in orgs))
    main(sys.argv[split + 1:], **injected(FakeBrreg({org: entity(org) for org in orgs}, delay=options.delay)))
