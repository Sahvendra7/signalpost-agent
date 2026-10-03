#!/usr/bin/env python3
"""Signalpost batch command: one terminal contract envelope (OUTPUT_CONTRACT.md) per input row.

Implementation: norway_company_agent.cli.main (streaming output, batch deadline, refresh)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
