"""Deterministic article capture for the LLM experiments (no model involvement in what is fetched).

Only URLs the deterministic pipeline already emitted as news candidates are fetched, and only when they are inside
the verified website's scope (`site_facts.in_site_scope`). Social-platform and restricted hosts are refused, robots.txt
is honoured, redirects go through the release's `SAFE_OPENER` (public addresses only), one request per host at a time
with a delay. Raw bytes are stored by SHA-256; an index row records url, status, retrieved_at and the hash.

The extracted text given to a model is the item's own text without header/footer/nav/aside and without any line the
site repeats on its homepage (`site_facts.item_page_text` / `site_chrome`, the V3.1 rules), capped in length.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup

from ..http import fetch_bytes
from ..site_facts import CapturedPage, in_site_scope, item_page_text, page_lines, site_chrome
from ..website import SAFE_OPENER, SOCIAL_HOSTS, USER_AGENT, _robots_allowed, assert_public_url, restricted_platform

MAX_BYTES = 3_000_000


def norm_url(url: str | None) -> str:
    url = re.sub(r"[?&]utm_[^&]*", "", (url or "").split("#")[0])
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/?").rstrip("/").lower()


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").casefold().removeprefix("www.")


def refusal(url: str, site_url: str) -> str | None:
    """Why `url` must not be fetched for this site, or None."""
    if not url.startswith(("http://", "https://")):
        return "not_http"
    host = _host(url)
    if any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS) or restricted_platform(host):
        return "social_or_restricted_host"
    if not in_site_scope(url, site_url):
        return "outside_verified_site"
    try:
        assert_public_url(url)
    except Exception:
        return "not_public_address"
    return None


@dataclass
class CaptureStore:
    root: Path

    def __post_init__(self) -> None:
        (self.root / "raw").mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.jsonl"
        self._index: dict[str, dict[str, Any]] = {}
        if self.index_path.exists():
            for line in self.index_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._index[row["url"]] = row
        self._lock = threading.Lock()

    def get(self, url: str) -> dict[str, Any] | None:
        return self._index.get(url)

    def page(self, url: str) -> CapturedPage | None:
        row = self._index.get(url)
        if not row or not row.get("sha256"):
            return None
        raw = gzip.decompress((self.root / "raw" / f"{row['sha256']}.gz").read_bytes())
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            return None  # tampered or corrupt: never used
        return CapturedPage(url=row.get("final_url") or url, raw=raw, content_sha256=row["sha256"], retrieved_at=row["retrieved_at"])

    def put(self, row: dict[str, Any], raw: bytes | None) -> None:
        with self._lock:
            if raw is not None:
                path = self.root / "raw" / f"{row['sha256']}.gz"
                if not path.exists():
                    path.write_bytes(gzip.compress(raw, mtime=0))
            self._index[row["url"]] = row
            with self.index_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class Fetcher:
    def __init__(self, store: CaptureStore, delay_s: float = 1.0, timeout_s: float = 15.0):
        self.store, self.delay_s, self.timeout_s = store, delay_s, timeout_s
        self._host_locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def capture(self, url: str, site_url: str) -> dict[str, Any]:
        cached = self.store.get(url)
        if cached is not None:
            return cached
        why = refusal(url, site_url)
        base = {"url": url, "site_url": site_url}
        if why:
            row = {**base, "status": 0, "error": f"refused:{why}", "sha256": None, "retrieved_at": None}
            self.store.put(row, None)
            return row
        with self._lock(_host(url)):
            if not _robots_allowed(url, self.timeout_s):
                row = {**base, "status": 0, "error": "robots_disallow", "sha256": None, "retrieved_at": None}
            else:
                result = fetch_bytes(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                                     timeout=self.timeout_s, attempts=2, max_bytes=MAX_BYTES, opener=SAFE_OPENER)
                html_ok = result.raw is not None and result.status == 200 and "html" in (result.content_type or "html").lower()
                row = {**base, "status": result.status, "error": result.error if not html_ok else None,
                       "content_type": result.content_type, "sha256": result.content_sha256 if html_ok else None,
                       "retrieved_at": result.retrieved_at, "bytes": len(result.raw or b"")}
                self.store.put(row, result.raw if html_ok else None)
                time.sleep(self.delay_s)
        if row.get("error") == "robots_disallow":
            self.store.put(row, None)
        return row


# ---------- text given to the model ----------

def article_text(store: CaptureStore, item_url: str, site_url: str, cap: int = 6000) -> tuple[str | None, dict[str, Any]]:
    """The item page's own text (V3.1 chrome rules), or None, with provenance."""
    page = store.page(item_url)
    if page is None:
        row = store.get(item_url) or {}
        return None, {"captured": False, "reason": row.get("error") or "not_captured"}
    home = store.page(site_url)
    chrome = site_chrome([home]) if home is not None and norm_url(home.url) != norm_url(item_url) else frozenset()
    text = item_page_text(page, chrome)
    title = ""
    try:
        node = BeautifulSoup(page.html, "lxml").find("title")
        title = " ".join(node.get_text(" ").split()) if node else ""
    except Exception:
        pass
    return (text[:cap] if text else None), {"captured": True, "url": item_url, "sha256": page.content_sha256,
                                            "retrieved_at": page.retrieved_at, "chars": len(text), "truncated": len(text) > cap,
                                            "chrome_lines_removed": len(chrome), "html_title": title[:300]}


def feed_or_card_text(raw: bytes, source_url: str, item_url: str, title: str, cap: int = 1800) -> tuple[str | None, str | None]:
    """The feed entry or listing card for `item_url` on a captured source page (the label aid's logic)."""
    if raw.lstrip()[:200].lower().find(b"<rss") >= 0 or raw.lstrip().startswith(b"<?xml"):
        soup = BeautifulSoup(raw, "xml")
        for node in soup.find_all(["item", "entry"]):
            link = node.find("link")
            href = (link.get("href") or link.get_text(strip=True)) if link else ""
            if norm_url(href) == norm_url(item_url):
                body = node.find(["encoded", "content"]) or node.find(["description", "summary"])
                cats = [c.get_text(strip=True) for c in node.find_all("category")]
                txt = " ".join(BeautifulSoup(body.get_text(" ", strip=True), "lxml").get_text(" ", strip=True).split()) if body else ""
                return (f"[feed categories: {', '.join(cats)}] " if cats else "") + txt[:cap], "feed_entry"
        return None, None
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    card = None
    origin = re.sub(r"^(https?://[^/]+).*", r"\1", source_url)
    for a in soup.find_all("a", href=True):
        href = a["href"] if a["href"].startswith("http") else origin + "/" + a["href"].lstrip("/")
        if norm_url(href) == norm_url(item_url) and norm_url(item_url) != norm_url(source_url):
            card = a
            for _ in range(4):
                if card.parent is not None and len(card.parent.get_text(" ", strip=True)) < 900:
                    card = card.parent
            break
    if card is None and title:
        heading = soup.find(lambda t: t.name in ("h1", "h2", "h3", "h4") and title[:30] in t.get_text(" ", strip=True))
        card = heading.parent if heading is not None else None
    if card is None:
        return None, None
    return " ".join(card.get_text(" ", strip=True).split())[:cap], "listing_card"


def capture_many(fetcher: Fetcher, jobs: Iterable[tuple[str, str]], workers: int = 8) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor
    jobs = list(dict.fromkeys(jobs))
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda job: fetcher.capture(*job), jobs))
