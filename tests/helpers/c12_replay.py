"""Replay a C12 fixture (tests/fixtures/c12/<org>/) through the real pipeline: exact captured bytes, no network."""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

from norway_company_agent.http import ByteFetch, FetchResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "c12"
ROBOTS = b"User-agent: *\nAllow: /\n"


class Fixture:
    def __init__(self, org: str):
        self.org = org
        self.manifest = json.loads((FIXTURES / org / "manifest.json").read_text(encoding="utf-8"))
        self.calls: list[str] = []

    def raw(self, url: str) -> bytes | None:
        entry = self.manifest["entries"].get(url)
        if not entry or not entry.get("file"):
            return None
        return gzip.decompress((FIXTURES / self.org / entry["file"]).read_bytes())

    def brreg(self, url: str) -> FetchResult:
        self.calls.append(url)
        entry = self.manifest["entries"].get(url) or {}
        status = int(entry.get("status") or 404)
        raw = self.raw(url) or b""
        body = json.loads(raw) if status == 200 and raw else None
        return FetchResult(url, status, 5, len(raw), body, error=None if status == 200 else f"HTTP {status}",
                           content_sha256=entry.get("content_sha256"), retrieved_at=entry.get("retrieved_at") or "2026-10-04T12:00:00Z", raw=raw)

    def site(self, url: str, **kwargs) -> ByteFetch:
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return ByteFetch(url, 200, 1, ROBOTS, "text/plain", {}, None, "2026-10-04T12:00:00Z", 1)
        entry = self.manifest["entries"].get(url)
        raw = self.raw(url)
        if not entry or raw is None:
            return ByteFetch(url, 404, 1, b"", "text/html", {}, None, "2026-10-04T12:00:00Z", 1, "HTTP 404")
        return ByteFetch(url, int(entry["status"]), 1, raw, "text/html", {}, entry["content_sha256"], entry["retrieved_at"], 1)

    def website(self, url):
        record = copy.deepcopy(self.manifest["website_record"])
        return record, {"requests": 2, "bytes": 0, "latencies_ms": []}

    def injected(self) -> dict:
        return {"fetcher": self.brreg, "site_fetcher": self.site, "website_fetcher": self.website, "resolver": lambda host: True}
