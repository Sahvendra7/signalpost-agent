#!/usr/bin/env python3
"""Run the evaluator command with a Python audit hook that logs every outbound host (validation only).

    python measurements/final-validation-2026-10-03/host_audit.py HOSTS_FILE -- <run_competition_batch.py args>

Records hosts from `urllib.Request` (full URL), `http.client.connect` and `socket.getaddrinfo` events, one
line per first sighting, appended and flushed immediately (the CLI may exit via os._exit)."""
from __future__ import annotations

import sys
import threading
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
hosts_file = Path(sys.argv[1])
args = sys.argv[sys.argv.index("--") + 1:]
seen: set[tuple[str, str]] = set()
lock = threading.Lock()
handle = hosts_file.open("a", encoding="utf-8")


def record(kind: str, host: str) -> None:
    key = (kind, host)
    if key in seen:
        return
    with lock:
        if key not in seen:
            seen.add(key)
            handle.write(f"{kind}\t{host}\n")
            handle.flush()


def hook(event: str, payload: tuple) -> None:
    try:
        if event == "urllib.Request":
            record("url", urllib.parse.urlsplit(str(payload[0])).hostname or "")
        elif event == "http.client.connect":
            record("connect", str(payload[1]))
        elif event == "socket.getaddrinfo":
            record("dns", str(payload[0]))
    except Exception:
        pass


sys.addaudithook(hook)
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.cli import main  # noqa: E402

main(args)
