"""Build a replay fixture (tests/fixtures/<set>/<org>/) from one live run made with --snapshot-dir.

    uv run python scripts/build_fixture_from_snapshot.py --profiles out/profiles.jsonl --snapshot-dir out/snapshots \
        --org 987832827 --out tests/fixtures/v311 [--note "..."]

Every registry response and every website page the run recorded in the company's profile evidence is copied as its
exact captured bytes (gzip), keyed by URL, with its status, SHA-256 and retrieval time. The replay helper
(tests/helpers/c12_replay.Fixture) serves these bytes; robots.txt is answered with "Allow: /" as for the other sets.
A page whose bytes are missing from the snapshot directory stops the build: a fixture is never partial.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def _records(profile: dict) -> list[tuple[str, str, str, int]]:
    """(url, sha256, retrieved_at, status) for every captured response in the profile evidence."""
    out: dict[str, tuple[str, str, str, int]] = {}
    for key, record in (profile.get("evidence") or {}).items():
        if not isinstance(record, dict) or not record.get("source_url") or key == "registry":
            continue
        sha = record.get("content_sha256")
        status = 200 if record.get("status") == "available" else 404
        if sha:
            out.setdefault(record["source_url"], (record["source_url"], sha, record.get("retrieved_at") or "", status))
        value = record.get("value") if isinstance(record.get("value"), dict) else {}
        for page in value.get("pages") or []:
            if page.get("url") and page.get("content_sha256"):
                out[page["url"]] = (page["url"], page["content_sha256"], page.get("retrieved_at") or record.get("retrieved_at") or "",
                                    int(page.get("status") or 200))
        for feed in value.get("feeds") or []:
            if isinstance(feed, dict) and feed.get("url") and feed.get("content_sha256"):
                out[feed["url"]] = (feed["url"], feed["content_sha256"], feed.get("retrieved_at") or "", int(feed.get("status") or 200))
    return list(out.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--org", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    profile = next(json.loads(line) for line in open(args.profiles, encoding="utf-8") if json.loads(line).get("organisation_number") == args.org)
    target = Path(args.out) / args.org
    target.mkdir(parents=True, exist_ok=True)
    entries = {}
    for url, sha, retrieved_at, status in _records(profile):
        raw = (Path(args.snapshot_dir) / sha[:2] / f"{sha}.bin").read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise SystemExit(f"hash mismatch for {url}")
        name = f"{sha[:16]}.{'json' if 'data.brreg.no' in url else 'html'}.gz"
        (target / name).write_bytes(gzip.compress(raw, mtime=0))
        entries[url] = {"kind": "brreg" if "data.brreg.no" in url else "site", "status": status, "file": name, "content_sha256": sha, "retrieved_at": retrieved_at}
    manifest = {
        "organisation_number": args.org, "name": profile.get("name"),
        "captured_by": "scripts/run_competition_batch.py with --snapshot-dir; scripts/build_fixture_from_snapshot.py",
        "note": args.note or "Exact captured bytes. Robots.txt answers are not captured: the replay serves 'Allow: /'.",
        "website_record": (profile.get("evidence") or {}).get("website"), "entries": entries,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{target}: {len(entries)} entries")


if __name__ == "__main__":
    main()
