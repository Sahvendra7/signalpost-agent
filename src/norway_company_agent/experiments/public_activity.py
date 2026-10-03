"""Public-activity experiment: verified company site -> officially linked profiles + dated first-party activity.

Policy (Builderr `signalpost-sources.md`): permitted first-party sources include the company's news pages and
"social or video profiles linked by the verified company site, subject to the destination platform's access
terms". LinkedIn/Meta collection is restricted and YouTube's robots.txt disallows /feeds/videos.xml, so
platform pages are NEVER fetched here: a profile is recorded from the company site's own link, and dated
activity comes only from the company's own site (RSS/Atom feeds it declares, JSON-LD article dates,
<time datetime> and article:published_time). A date is recorded only when the source states it.

Internal label: public_activity. SCORING_MAPPING = UNCONFIRMED.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from bs4 import BeautifulSoup

from .common import Meter, Timer
from ..http import ByteFetch, fetch_bytes
from ..identity import assess_social_identity
from ..website import USER_AGENT, _registered_domain, _social_links, structured_social_links

NEWS_HINTS = ("nyheter", "aktuelt", "news", "blogg", "blog", "artikler", "presse", "press", "arkiv")
CAREER_HINTS = ("ledige-stillinger", "ledige stillinger", "jobb-hos", "jobbe-hos", "karriere", "career", "jobs", "stillinger")
ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "Report", "PressRelease"}
MAX_EXTRA_FETCHES = 3


def parse_date(value: Any) -> str | None:
    """Return an ISO-8601 UTC timestamp only for an unambiguous, timezone-resolvable source date."""
    text = str(value or "").strip()
    if not text:
        return None
    parsed = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        if len(text) == 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text  # a date without time is still a source-stated date
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed > datetime.now(timezone.utc) + timedelta(days=1) or parsed.year < 1995:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def feed_items(xml: bytes) -> list[dict[str, Any]]:
    soup = BeautifulSoup(xml, "xml")
    items = []
    for node in soup.find_all(["item", "entry"])[:50]:
        title = node.find("title")
        link = node.find("link")
        href = (link.get("href") or link.get_text(strip=True)) if link else None
        published = node.find(["pubDate", "published", "dc:date", "date"])
        updated = node.find("updated")
        date = parse_date(published.get_text(strip=True)) if published else None
        kind = "published"
        if not date and updated:
            date, kind = parse_date(updated.get_text(strip=True)), "updated"
        items.append({"title": title.get_text(" ", strip=True)[:200] if title else None, "url": href, "date": date, "date_kind": kind if date else None})
    return items


def html_items(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                kinds = node.get("@type")
                kinds = set(kinds if isinstance(kinds, list) else [kinds])
                if kinds & ARTICLE_TYPES:
                    date = parse_date(node.get("datePublished"))
                    if date:
                        items.append({"title": str(node.get("headline") or node.get("name") or "")[:200] or None, "url": urllib.parse.urljoin(base_url, str(node.get("url") or node.get("mainEntityOfPage") or base_url)) if isinstance(node.get("url") or node.get("mainEntityOfPage") or base_url, str) else base_url, "date": date, "date_kind": "published", "method": "jsonld_datePublished"})
                stack.extend(value for value in node.values() if isinstance(value, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)
    meta = soup.select_one('meta[property="article:published_time"]')
    if meta and parse_date(meta.get("content")):
        items.append({"title": (soup.title.get_text(" ", strip=True)[:200] if soup.title else None), "url": base_url, "date": parse_date(meta.get("content")), "date_kind": "published", "method": "meta_article_published_time"})
    for article in soup.select("article")[:30]:
        time_node = article.select_one("time[datetime]")
        date = parse_date(time_node.get("datetime")) if time_node else None
        if not date:
            continue
        anchor = article.select_one("a[href]")
        heading = article.select_one("h1, h2, h3, h4")
        items.append({"title": (heading.get_text(" ", strip=True)[:200] if heading else None), "url": urllib.parse.urljoin(base_url, anchor["href"]) if anchor else base_url, "date": date, "date_kind": "published", "method": "article_time_datetime"})
    return items


class SiteCrawler:
    def __init__(self, fetcher: Callable[..., ByteFetch] = fetch_bytes):
        self.meter = Meter(fetcher)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key not in self._robots:
            response = self.meter.get(key + "/robots.txt", timeout=15, attempts=1)
            if response.status in (401, 403):
                self._robots[key] = None  # treat as disallow-all
            else:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse((response.raw or b"").decode("utf-8", errors="replace").splitlines() if response.status == 200 else [])
                self._robots[key] = parser
        parser = self._robots[key]
        return bool(parser and parser.can_fetch(USER_AGENT, url))

    def get(self, url: str, accept: str = "text/html,application/xhtml+xml") -> ByteFetch | None:
        if not self.allowed(url):
            return None
        return self.meter.get(url, headers={"User-Agent": USER_AGENT, "Accept": accept}, timeout=20, attempts=2)


def run_company(profile: dict[str, Any], site_url: str, site_class: str, *, fetcher: Callable[..., ByteFetch] = fetch_bytes, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    crawler = SiteCrawler(fetcher)
    domain = _registered_domain(site_url)
    profiles: dict[str, dict[str, Any]] = {}
    activities: list[dict[str, Any]] = []
    pages_html: list[str] = []
    other_pages: dict[str, str] = {}
    blocked = []
    with Timer() as timer:
        home = crawler.get(site_url)
        if home is None:
            blocked.append(site_url)
        if home is None or home.status != 200 or not home.raw:
            return _result(profile, site_url, site_class, crawler, timer, profiles, activities, other_pages, blocked, error=f"homepage {'robots-disallowed' if home is None else home.status}")
        home_url = site_url
        html = home.raw.decode("utf-8", errors="replace")
        pages_html.append(html)
        soup = BeautifulSoup(html, "lxml")
        evidence_pages = [(home_url, home)]

        feeds, news = [], []
        for link in soup.select('link[rel~="alternate"][href]'):
            if any(kind in str(link.get("type") or "") for kind in ("rss", "atom")):
                url = urllib.parse.urljoin(home_url, link["href"])
                if _registered_domain(url) == domain and "comments" not in url:
                    feeds.append(url)
        for anchor in soup.select("a[href]"):
            url = urllib.parse.urljoin(home_url, anchor["href"]).split("#")[0]
            if _registered_domain(url) != domain or url.rstrip("/") == home_url.rstrip("/"):
                continue
            label = (urllib.parse.urlsplit(url).path + " " + anchor.get_text(" ", strip=True)).casefold()
            if any(hint in label for hint in NEWS_HINTS):
                news.append(url)
            elif any(hint in label for hint in CAREER_HINTS):
                other_pages.setdefault("careers_page", url)
        budget = MAX_EXTRA_FETCHES
        for url in list(dict.fromkeys(feeds))[:1]:
            response = crawler.get(url, accept="application/rss+xml,application/atom+xml,application/xml,text/xml")
            budget -= 1
            if response is None:
                blocked.append(url)
            elif response.status == 200 and response.raw:
                for item in feed_items(response.raw):
                    item.update(method="site_feed", page_url=url, content_sha256=response.content_sha256, retrieved_at=response.retrieved_at)
                    activities.append(item)
        for url in list(dict.fromkeys(news))[:max(0, budget)]:
            response = crawler.get(url)
            if response is None:
                blocked.append(url)
                continue
            if response.status == 200 and response.raw:
                page_html = response.raw.decode("utf-8", errors="replace")
                pages_html.append(page_html)
                evidence_pages.append((url, response))
        for url, response in evidence_pages:
            page_html = response.raw.decode("utf-8", errors="replace")
            page_soup = BeautifulSoup(page_html, "lxml")
            for item in html_items(page_html, url):
                item.update(page_url=url, content_sha256=response.content_sha256, retrieved_at=response.retrieved_at)
                activities.append(item)
            links = _social_links(url, page_soup)
            try:
                import extruct

                same_as = structured_social_links(extruct.extract(page_html, base_url=url, syntaxes=["json-ld"]))
            except Exception:
                same_as = []
            for link in links + same_as:
                entry = profiles.setdefault(link["url"], {**link, "found_on": url, "page_sha256": response.content_sha256, "retrieved_at": response.retrieved_at, "via_jsonld_sameas": False})
                if link in same_as:
                    entry["via_jsonld_sameas"] = True
    return _result(profile, site_url, site_class, crawler, timer, profiles, activities, other_pages, blocked)


def _result(profile, site_url, site_class, crawler, timer, profiles, activities, other_pages, blocked, error=None) -> dict[str, Any]:
    accepted, ambiguous = [], []
    for link in profiles.values():
        gate = assess_social_identity(profile, link)
        record = {**link, "identity_score": gate["identity_score"], "identity_reason": gate["reason"], "relationship": "verified_company_website -> officially_linked_social_profile"}
        if gate["publishable"] or link.get("via_jsonld_sameas"):
            record["class"] = "OFFICIALLY_LINKED"
            accepted.append(record)
        else:
            record["class"] = "AMBIGUOUS"
            ambiguous.append(record)
    seen = set()
    dated = []
    for item in activities:
        key = (item.get("url"), item.get("date"), item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        if item.get("date") and item.get("content_sha256"):
            item["excerpt"] = item.get("title")
            dated.append(item)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    recent = [item for item in dated if cutoff <= str(item["date"])[:10] <= now]
    return {
        "organisation_number": profile["organisation_number"],
        "site_url": site_url,
        "site_class": site_class,
        "requests": crawler.meter.requests,
        "statuses": dict(crawler.meter.statuses),
        "runtime_ms": getattr(timer, "ms", None) or int((time.monotonic() - timer.started) * 1000),
        "error": error,
        "robots_blocked": blocked,
        "profiles_accepted": accepted,
        "profiles_ambiguous": ambiguous,
        "platforms_accepted": sorted({item["platform"] for item in accepted}),
        "activities_dated": dated,
        "activities_undated": sum(1 for item in activities if not item.get("date")),
        "activities_recent_365d": len(recent),
        "latest_activity": max((str(item["date"]) for item in dated), default=None),
        "other_official_pages": other_pages,
        "platform_activity_collection": "not attempted: LinkedIn/Meta restricted by Builderr source policy; YouTube feeds disallowed by robots.txt",
        "covered_profile": bool(accepted),
        "covered_dated_activity": bool(dated),
        "covered_any": bool(accepted) or bool(dated),
    }
