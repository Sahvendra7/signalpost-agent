#!/usr/bin/env python3
"""Build the C12 regression fixtures from a real run's captured evidence (no new requests, nothing edited).

    uv run python tests/fixtures/c12/build_fixtures.py RUN_PROFILES.jsonl SNAPSHOT_DIR ORG [ORG ...]

For each organisation the fixture holds the exact bytes the crawler captured (gzip), keyed by URL, with the
SHA-256 and retrieval time of the capture: the Brreg responses (roles already have birth dates removed by
privacy.redacting_fetcher before capture), every company-site page and feed, and the v1 website-module
record (whose own pages are not snapshotted). Nothing is rewritten; a page whose bytes were not captured is
recorded with its status only.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    profiles_path, snapshot_dir, *orgs = sys.argv[1:]
    snapshots = Path(snapshot_dir)
    profiles = {json.loads(line)["organisation_number"]: json.loads(line) for line in Path(profiles_path).read_text(encoding="utf-8").splitlines()}
    for org in orgs:
        profile = profiles[org]
        target = HERE / org
        target.mkdir(parents=True, exist_ok=True)
        entries: dict[str, dict] = {}

        def add(url: str | None, sha: str | None, retrieved_at: str | None, kind: str, status: int = 200) -> None:
            if not url or url in entries:
                return
            path = snapshots / (sha or "")[:2] / f"{sha}.bin" if sha else None
            if path is None or not path.exists():
                entries[url] = {"kind": kind, "status": status, "file": None, "content_sha256": None, "retrieved_at": retrieved_at}
                return
            raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == sha, url
            name = f"{sha[:16]}.{ 'json' if kind == 'brreg' else 'xml' if kind == 'feed' else 'html'}.gz"
            (target / name).write_bytes(gzip.compress(raw, mtime=0))
            entries[url] = {"kind": kind, "status": status, "file": name, "content_sha256": sha, "retrieved_at": retrieved_at}

        evidence = profile["evidence"]
        for module in ("registry_live", "financials", "roles", "group", "locations", "financial_history"):
            record = evidence.get(module) or {}
            status = 200 if record.get("status") == "available" else 404 if record.get("status") == "not_found" else int(str(record.get("note") or "").removeprefix("HTTP ") or 0) if str(record.get("note") or "").startswith("HTTP ") else 0
            add(record.get("source_url"), record.get("content_sha256"), record.get("retrieved_at"), "brreg", status)
        site = (evidence.get("site_research") or {}).get("value") or {}
        for page in site.get("pages") or []:
            add(page.get("url"), page.get("content_sha256"), page.get("retrieved_at"), "site", page.get("status") or 200)
        for item in site.get("activities") or []:
            if item.get("method") == "site_feed":
                add(item.get("page_url"), item.get("content_sha256"), item.get("retrieved_at"), "feed")
        manifest = {
            "organisation_number": org,
            "name": profile.get("name"),
            "captured_by": "scripts/run_competition_batch.py (Revision 1 working tree) with --snapshot-dir",
            "note": "Exact captured bytes. Robots.txt answers are not captured: the replay serves 'Allow: /'.",
            "website_record": evidence.get("website"),
            "entries": entries,
        }
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(org, len(entries), "entries")


if __name__ == "__main__":
    main()
