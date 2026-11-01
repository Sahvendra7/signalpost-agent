#!/usr/bin/env python3
"""Local Signalpost search application (V3 design §B11).

    uv run python scripts/serve.py --data-dir out/app [--envelopes out/envelopes.jsonl ...] [--snapshot-dir out/snapshots ...]
                                   [--bulk brreg-enheter.csv.gz] [--audit-results audit-results.json] [--port 8765]

Then open http://127.0.0.1:8765/ in a browser on this computer. Search by company name or organisation number; open a
cited profile, compare 2–4 companies, see what is new, or research a company that is not in the dataset yet (about
a minute, free public sources only, LLM off). Researched profiles are kept under --data-dir.

Only loopback addresses are served unless --host and --allow-remote are both given (not recommended: the app has no
user accounts).
"""
from __future__ import annotations

import argparse
import functools
import logging
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norway_company_agent.app.registry_search import RegistrySearch  # noqa: E402
from norway_company_agent.app.research import ResearchManager  # noqa: E402
from norway_company_agent.app.server import App, Server  # noqa: E402
from norway_company_agent.app.store import Store  # noqa: E402
from norway_company_agent.cli import _manual_audit  # noqa: E402
from norway_company_agent.http import fetch_json  # noqa: E402


def build(args: argparse.Namespace) -> Server:
    store = Store(args.data_dir, imports=args.envelopes or [], snapshot_dirs=args.snapshot_dir or [])
    registry = RegistrySearch(fetcher=functools.partial(fetch_json, timeout=8.0, attempts=1), bulk=args.bulk)
    research = ResearchManager(store, run_kwargs={"bulk_path": args.bulk} if args.bulk else {}, deadline=args.deadline)
    app = App(store, registry, research, token=secrets.token_urlsafe(32), manual_audit=_manual_audit(args.audit_results))
    return Server(app, args.host, args.port, allow_remote=args.allow_remote)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data-dir", required=True, help="Where researched profiles and their captured sources are kept")
    parser.add_argument("--envelopes", action="append", help="Envelope JSONL (or .jsonl.gz) from a batch run; read-only; repeatable")
    parser.add_argument("--snapshot-dir", action="append", help="--snapshot-dir of that batch run, to show the captured bytes; repeatable")
    parser.add_argument("--bulk", help="Optional Brreg bulk file (gzip CSV): registry search without the network")
    parser.add_argument("--audit-results", help="results.json from scripts/audit_kit.py score, shown in 'How reliable is this?'")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--allow-remote", action="store_true", help="Allow a non-loopback --host (no user accounts: not recommended)")
    parser.add_argument("--deadline", type=float, default=120.0, help="Seconds per on-demand research (default 120)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        server = build(args)
    except ValueError as exc:
        parser.error(str(exc))
    if args.allow_remote and args.host not in ("127.0.0.1", "localhost"):
        print(f"WARNING: serving on {args.host}; anyone who can reach it can start research on your computer.", file=sys.stderr)
    host, port = server.server_address[:2]
    print(f"Signalpost search: http://{'127.0.0.1' if host == '127.0.0.1' else host}:{port}/  ({server.app.store.imported} imported envelopes; Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
