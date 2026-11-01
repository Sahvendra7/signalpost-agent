"""Replay a captured run through the current code (V3 measurement methodology, design §B13).

A live run with `--snapshot-dir` keeps the exact bytes behind every registry response and every company-site page it
read, and its profiles record which URL each hash came from. `ReplayFetchers` serves those bytes back to the real
pipeline (the same approach as the C12/C300 regression fixtures), so two code versions can be compared on identical
inputs: any difference is caused by the code, not by the web changing between runs.

Limits, stated so results are read correctly:
  * robots.txt is answered with "Allow: /" (robots answers are not captured);
  * a URL the baseline did not fetch is answered 404 (a code version that would fetch other pages sees them missing);
  * the v1 website-module record (registry-linked site identity) is replayed as recorded, so website identity is
    frozen to the baseline's decision.
Nothing here performs network I/O.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .http import ByteFetch, FetchResult

ROBOTS = b"User-agent: *\nAllow: /\n"
OFFICIAL_MODULES = ("registry_live", "financials", "roles", "group", "locations", "financial_history")


def _status(record: dict[str, Any]) -> int:
    if record.get("status") == "available":
        return 200
    if record.get("status") == "not_found":
        return 404
    note = str(record.get("note") or "")
    return int(note.removeprefix("HTTP ")) if note.startswith("HTTP ") and note[5:8].isdigit() else 0


def entries_from_profile(profile: dict[str, Any], snapshot_dir: Path) -> dict[str, dict[str, Any]]:
    """URL -> {kind, status, path, content_sha256, retrieved_at} for every captured response of one company."""
    entries: dict[str, dict[str, Any]] = {}

    def add(url: str | None, sha: str | None, retrieved_at: str | None, kind: str, status: int = 200) -> None:
        if not url or url in entries:
            return
        path = snapshot_dir / sha[:2] / f"{sha}.bin" if sha else None
        entries[url] = {"kind": kind, "status": status if path is not None and path.exists() else (status if status != 200 else 404),
                        "path": str(path) if path is not None and path.exists() else None, "content_sha256": sha, "retrieved_at": retrieved_at}

    evidence = profile.get("evidence") or {}
    for module in OFFICIAL_MODULES:
        record = evidence.get(module) or {}
        add(record.get("source_url"), record.get("content_sha256"), record.get("retrieved_at"), "brreg", _status(record))
    site = (evidence.get("site_research") or {}).get("value") or {}
    for page in site.get("pages") or []:
        add(page.get("url"), page.get("content_sha256"), page.get("retrieved_at"), "site", int(page.get("status") or 200))
    for item in site.get("activities") or []:
        if item.get("method") == "site_feed":
            add(item.get("page_url"), item.get("content_sha256"), item.get("retrieved_at"), "feed")
    for url, sha, at in site.get("feeds_read") or []:  # V3 site records list every feed read
        add(url, sha, at, "feed")
    return entries


class ReplayFetchers:
    """Fetchers for `run_batch`/`cli.main` that answer from captured runs instead of the network."""

    def __init__(self, profiles: list[dict[str, Any]], snapshot_dir: str | Path):
        self.snapshot_dir = Path(snapshot_dir)
        self.entries: dict[str, dict[str, Any]] = {}
        self.websites: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []
        for profile in profiles:
            for url, entry in entries_from_profile(profile, self.snapshot_dir).items():
                self.entries.setdefault(url, entry)
            record = (profile.get("evidence") or {}).get("website")
            if record is not None and profile.get("website"):
                self.websites.setdefault(str(profile["website"]), record)

    def _raw(self, url: str) -> tuple[dict[str, Any] | None, bytes | None]:
        entry = self.entries.get(url)
        if not entry or not entry.get("path"):
            return entry, None
        raw = Path(entry["path"]).read_bytes()
        if entry.get("content_sha256") and hashlib.sha256(raw).hexdigest() != entry["content_sha256"]:
            raise ValueError(f"snapshot hash mismatch for {url}")
        return entry, raw

    def brreg(self, url: str) -> FetchResult:
        self.calls.append(url)
        entry, raw = self._raw(url)
        status = int((entry or {}).get("status") or 404)
        if raw is None and status == 200:
            status = 404
        body = json.loads(raw) if status == 200 and raw else None
        return FetchResult(url, status, 1, len(raw or b""), body, error=None if status == 200 else f"HTTP {status}",
                           content_sha256=(entry or {}).get("content_sha256") if raw else None,
                           retrieved_at=(entry or {}).get("retrieved_at") or "2026-11-01T00:00:00Z", raw=raw or b"")

    def site(self, url: str, **kwargs: Any) -> ByteFetch:
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return ByteFetch(url, 200, 1, ROBOTS, "text/plain", {}, None, "2026-11-01T00:00:00Z", 1)
        entry, raw = self._raw(url)
        if entry is None or raw is None:
            return ByteFetch(url, 404, 1, b"", "text/html", {}, None, "2026-11-01T00:00:00Z", 1, "HTTP 404")
        kind = "application/rss+xml" if entry.get("kind") == "feed" else "text/html"
        return ByteFetch(url, int(entry.get("status") or 200), 1, raw, kind, {}, entry["content_sha256"], entry["retrieved_at"], 1)

    def website(self, url: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        record = self.websites.get(str(url))
        if record is None:
            record = {"field": "website", "status": "not_found", "source_type": "registry_linked_company_website", "source_class": "registry_linked_company_website",
                      "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter", "retrieved_at": "2026-11-01T00:00:00Z", "value": None,
                      "note": "no registry website in the captured run"}
        return copy.deepcopy(record), {"requests": 0, "bytes": 0, "latencies_ms": []}

    def injected(self) -> dict[str, Any]:
        return {"fetcher": self.brreg, "site_fetcher": self.site, "website_fetcher": self.website, "resolver": lambda host: True}


def load_profiles(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
