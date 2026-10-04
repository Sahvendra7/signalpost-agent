"""Zero-cost website discovery and first-party site research (V2).

Stages per company (adaptive; stops early):
  1. candidate domains from official pointers only: registry `hjemmeside` (when the v1 registry gate did
     not verify it), registry `epostadresse` domain, subunit `hjemmeside` and `epostadresse` domains, then
     `<legal-name>.no` guesses that resolve in DNS. No search engine, no paid API.
  2. identity: homepage + up to two contact/about pages -> site_identity.classify_site (policy v2). The first
     FIRST_PARTY_CONFIRMED candidate wins; the rest are not fetched.
  3. enrichment of the verified site: declared RSS/Atom feed, one news page, one careers page, and
     sitemap.xml only when the homepage exposes neither. site_facts.extract_site_facts then reads the captured
     pages for site-linked social profiles, dated activity and job postings (no further requests).
Platform pages (LinkedIn, Facebook, Instagram, YouTube) are never fetched: a profile is recorded from the
verified site's own link. Dates are kept only when the source states them. robots.txt is honoured (RFC 9309:
401/403, 429, 5xx and network failure mean disallow; Crawl-delay is honoured inside the company budget).
Every fetched page keeps url, sha256 and retrieval time for evidence.
"""
from __future__ import annotations

import re
import socket
import threading
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any, Callable

from bs4 import BeautifulSoup

from .http import ByteFetch, fetch_bytes
from .identity import _tokens
from .site_facts import ARTICLE_TYPES, CapturedPage, article_links, extract_site_facts, feed_items, html_items, job_postings, parse_date  # noqa: F401  (re-exported)
from .site_identity import FREE_MAIL, classify_site, manager_designated
from .website import MAX_CRAWL_DELAY_SECONDS, USER_AGENT, _registered_domain, crawl_delay, normalize_homepage, robots_policy

DIRECTORY_HOSTS = {
    "proff.no", "purehelp.no", "1881.no", "gulesider.no", "firmalisten.no", "companywall.no", "firmadatabasen.no",
    "sokfirma.no", "yra.no", "northdata.com", "nor47business.com", "brreg.no", "finn.no", "regnskapstall.no",
    "linkedin.com", "facebook.com", "instagram.com", "youtube.com", "x.com", "twitter.com", "tiktok.com",
}
IDENTITY_HINTS = ("kontakt", "contact", "om-oss", "om oss", "about", "personvern", "privacy")
NEWS_HINTS = ("nyheter", "aktuelt", "news", "blogg", "blog", "artikler", "presse", "press")
CAREER_HINTS = ("ledige-stillinger", "ledige stillinger", "karriere", "career", "jobb-hos", "jobbe-hos", "stillinger", "/jobs", "jobb")
HTML_ACCEPT = "text/html,application/xhtml+xml"
MAX_PAGE_BYTES = 3_000_000
MAX_ARTICLE_FETCHES = 3  # article pages followed from a news listing that states no dates
MANAGER_SITE_MAX_NEWS = 5  # a business manager's site serves many entities: only its most recent dated items


# ---------- fetching with robots, caches and budgets ----------

class CompanyBudget:
    def __init__(self, max_requests: int, max_seconds: float):
        self.max_requests = max_requests
        self.deadline = time.monotonic() + max_seconds
        self.requests = 0
        self.cache_hits = 0
        self.exhausted = False

    def allow(self) -> bool:
        if self.requests >= self.max_requests or time.monotonic() >= self.deadline:
            self.exhausted = True
            return False
        return True


def to_uri(url: str) -> str:
    """IRI -> URI: IDNA host and percent-encoded path/query, so Norwegian letters never reach urllib raw."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    netloc = host + (f":{parts.port}" if parts.port else "")
    path = urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(parts.query, safe="=&%:@!$'()*+,;/?-._~")
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, query, ""))


class SiteSession:
    """Run-wide robots and page caches, so a domain is fetched once per run however many companies point at it."""

    def __init__(self, fetcher: Callable[..., ByteFetch] = fetch_bytes, resolver: Callable[[str], bool] | None = None, url_guard: Callable[[str], None] | None = None):
        self.fetcher = fetcher
        self.resolver = resolver or _resolves
        self.url_guard = url_guard  # raises ValueError for a non-public URL (website.assert_public_url)
        self._public: dict[str, str] = {}
        self._lock = threading.Lock()
        self._robots: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {}
        self._delays: dict[str, float] = {}
        self._last_request: dict[str, float] = {}
        self._origin_locks: dict[str, threading.Lock] = {}
        self._pages: dict[str, ByteFetch] = {}
        self._dns: dict[str, bool] = {}

    def resolves(self, host: str) -> bool:
        with self._lock:
            if host in self._dns:
                return self._dns[host]
        ok = self.resolver(host)
        with self._lock:
            self._dns[host] = ok
        return ok

    def _fetch(self, url: str, budget: CompanyBudget, accept: str) -> ByteFetch | None:
        with self._lock:
            if url in self._pages:
                budget.cache_hits += 1
                return self._pages[url]
        if not budget.allow():
            return None
        result = self.fetcher(url, headers={"User-Agent": USER_AGENT, "Accept": accept}, timeout=15, attempts=2, max_bytes=MAX_PAGE_BYTES)
        budget.requests += result.attempts
        with self._lock:
            self._pages[url] = result
        return result

    def cached(self, url: str) -> ByteFetch | None:
        """A page this run already fetched, or None. Read-only: never fetches, never touches a budget."""
        with self._lock:
            return self._pages.get(to_uri(url))

    def allowed(self, url: str, budget: CompanyBudget) -> bool | None:
        return self.robots(url, budget)[0]

    def robots(self, url: str, budget: CompanyBudget) -> tuple[bool | None, str]:
        """(allowed, reason); allowed is None when the budget ran out before robots.txt could be read.
        Semantics in website.robots_policy (RFC 9309): 401/403, 429, 5xx and network failure disallow."""
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            known = origin in self._robots
            parser, reason = self._robots.get(origin) or (None, "")
        if not known:
            response = self._fetch(origin + "/robots.txt", budget, "text/plain")
            if response is None:
                return None, "budget_exhausted"
            parser, reason = robots_policy(response.status, response.raw)
            with self._lock:
                self._robots[origin] = (parser, reason)
                self._delays[origin] = crawl_delay(parser)
                self._last_request[origin] = time.monotonic()
        if parser is None:
            return False, reason
        if not parser.can_fetch(USER_AGENT, url):
            return False, "robots_disallowed"
        return True, reason

    def pace(self, url: str, budget: CompanyBudget) -> bool:
        """Honour robots.txt Crawl-delay per origin. False when waiting would overrun the company budget."""
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            delay = self._delays.get(origin, 0.0)
            if not delay:
                return True
            origin_lock = self._origin_locks.setdefault(origin, threading.Lock())
        if delay > MAX_CRAWL_DELAY_SECONDS:
            return False
        with origin_lock:  # requests to one origin are serialised while a Crawl-delay applies
            wait = self._last_request.get(origin, 0.0) + delay - time.monotonic()
            if wait > 0:
                if time.monotonic() + wait >= budget.deadline:
                    return False
                time.sleep(wait)
            self._last_request[origin] = time.monotonic()
        return True

    def public(self, url: str) -> str:
        """Outbound URL policy: only hosts resolving to global addresses are fetched (cached per origin).
        Returns "ok", "no_dns" or "blocked_non_public_host"."""
        if self.url_guard is None:
            return "ok"
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            if origin in self._public:
                return self._public[origin]
        try:
            self.url_guard(origin + "/")
            state = "ok"
        except ValueError as exc:
            state = "no_dns" if "did not resolve" in str(exc) else "blocked_platform_host" if "Restricted platform" in str(exc) else "blocked_non_public_host"
        with self._lock:
            self._public[origin] = state
        return state

    def get(self, url: str, budget: CompanyBudget, accept: str = HTML_ACCEPT) -> tuple[str, ByteFetch | None]:
        url = to_uri(url)
        policy = self.public(url)
        if policy != "ok":
            return policy, None
        allowed, reason = self.robots(url, budget)
        if allowed is None:
            return "budget_exhausted", None
        if not allowed:
            return ("robots_disallowed" if reason == "robots_disallowed" else reason), None
        if url not in self._pages and not self.pace(url, budget):
            return "crawl_delay_exceeds_budget", None
        result = self._fetch(url, budget, accept)
        if result is None:
            return "budget_exhausted", None
        if result.status != 200 or not result.raw:
            return f"http_{result.status or 'error'}", result
        return "ok", result


def _resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


# ---------- candidates ----------

def _email_domain(value: Any) -> str | None:
    match = re.search(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", str(value or ""))
    if not match:
        return None
    domain = _registered_domain("https://" + match.group(1).lower().rstrip("."))
    return None if not domain or domain in FREE_MAIL else domain


def name_domain_guesses(name: Any) -> list[str]:
    core = _tokens(name)
    joined = "".join(core)
    if len(joined) < 5:
        return []
    guesses = [f"{joined}.no"]
    if len(core) > 1:
        guesses.append(f"{'-'.join(core)}.no")
    return guesses


def discovery_candidates(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Ordered, de-duplicated candidate homepages from official pointers, then name guesses."""
    live = ((profile.get("evidence", {}).get("registry_live") or {}).get("value") or {})
    subunits = ((profile.get("evidence", {}).get("locations") or {}).get("value") or {}).get("locations", [])
    raw: list[tuple[str, str | None]] = [("registry_hjemmeside", live.get("website") or profile.get("website"))]
    raw.append(("registry_email", _email_domain(live.get("email"))))
    raw.extend(("subunit_hjemmeside", unit.get("website")) for unit in subunits)
    raw.extend(("subunit_email", _email_domain(unit.get("email"))) for unit in subunits)
    raw.extend(("name_domain_guess", guess) for guess in name_domain_guesses(profile.get("name") or live.get("name")))
    seen: set[str] = set()
    candidates = []
    for source, value in raw:
        url = normalize_homepage(value) if value else None
        domain = _registered_domain(url) if url else None
        if not url or not domain or domain in seen or domain in FREE_MAIL or domain in DIRECTORY_HOSTS:
            continue
        seen.add(domain)
        candidates.append({"source": source, "url": url, "domain": domain})
    return candidates


# ---------- research ----------

@dataclass
class SiteResult:
    status: str  # verified | none_verified | budget_exhausted
    site_url: str | None = None
    identity_class: str | None = None
    identity_reasons: list[str] = field(default_factory=list)
    identity_source: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    profiles: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_profiles: list[dict[str, Any]] = field(default_factory=list)
    activities: list[dict[str, Any]] = field(default_factory=list)
    jobs: list[dict[str, Any]] = field(default_factory=list)
    careers_page: str | None = None
    careers_checked: list[dict[str, Any]] = field(default_factory=list)
    articles_fetched: int = 0
    manager: dict[str, Any] | None = None  # MANAGER_DESIGNATED: the registered forretningsfører operating the site
    extraction_rejections: dict[str, int] = field(default_factory=dict)
    rejected_examples: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    cache_hits: int = 0
    runtime_ms: int = 0
    budget_exhausted: bool = False


def _page_record(url: str, response: ByteFetch) -> dict[str, Any]:
    return {"url": url, "content_sha256": response.content_sha256, "retrieved_at": response.retrieved_at, "status": response.status}


def _identity_pages(session: SiteSession, home_url: str, budget: CompanyBudget) -> tuple[str, list[tuple[str, ByteFetch]]]:
    state, home = session.get(home_url, budget)
    if state != "ok":
        return state, []
    pages = [(home_url, home)]
    soup = BeautifulSoup(home.raw.decode("utf-8", errors="replace"), "lxml")
    domain = _registered_domain(home_url)
    extra = []
    for anchor in soup.select("a[href]"):
        target = urllib.parse.urljoin(home_url, anchor["href"]).split("#")[0]
        label = (urllib.parse.urlsplit(target).path + " " + anchor.get_text(" ", strip=True)).casefold()
        if target.startswith("http") and _registered_domain(target) == domain and target.rstrip("/") != home_url.rstrip("/") and any(hint in label for hint in IDENTITY_HINTS):
            extra.append(target)
    for target in list(dict.fromkeys(extra))[:2]:
        sub_state, response = session.get(target, budget)
        if sub_state == "ok":
            pages.append((target, response))
    return "ok", pages


def research_company_site(
    profile: dict[str, Any],
    session: SiteSession,
    *,
    registry_verified_url: str | None = None,
    max_requests: int = 30,
    max_seconds: float = 60.0,
    max_candidates: int = 5,
) -> SiteResult:
    started = time.monotonic()
    budget = CompanyBudget(max_requests, max_seconds)
    live = ((profile.get("evidence", {}).get("registry_live") or {}).get("value") or {})
    target = {**profile, "name": profile.get("name") or live.get("name"), "business_address": live.get("business_address") or {}}
    result = SiteResult(status="none_verified")
    pages: list[tuple[str, ByteFetch]] = []

    if registry_verified_url:
        state, pages = _identity_pages(session, registry_verified_url, budget)
        result.site_url, result.identity_class, result.identity_source = registry_verified_url, "REGISTRY_LINKED", "registry_hjemmeside"
        result.identity_reasons = ["registry-listed website verified by the registry identity gate"]
        result.status = "verified"
        if state != "ok":
            result.candidates.append({"source": "registry_hjemmeside", "url": registry_verified_url, "outcome": state})
    else:
        for candidate in discovery_candidates(profile)[:max_candidates]:
            if not budget.allow():
                break
            host = urllib.parse.urlsplit(candidate["url"]).hostname or ""
            if candidate["source"] == "name_domain_guess" and not session.resolves(host):
                result.candidates.append({**candidate, "outcome": "no_dns"})
                continue
            state, candidate_pages = _identity_pages(session, candidate["url"], budget)
            if state != "ok":
                result.candidates.append({**candidate, "outcome": state})
                continue
            final_domain = _registered_domain(candidate_pages[0][1].url) or candidate["domain"]
            html_pages = [response.raw.decode("utf-8", errors="replace") for _, response in candidate_pages]
            verdict = classify_site(target, candidate["domain"], html_pages, registry_email=live.get("email"))
            manager = manager_designated(target, candidate["domain"], html_pages, verdict, registry_email=live.get("email")) if candidate["source"] == "registry_hjemmeside" else None
            result.candidates.append({**candidate, "outcome": "MANAGER_DESIGNATED" if manager else verdict["class"], "reason": verdict["reasons"][0], "final_domain": final_domain})
            if manager:
                result.status = "verified"
                result.site_url = candidate["url"]
                result.identity_class = "MANAGER_DESIGNATED"
                result.identity_source = candidate["source"]
                result.manager = manager
                result.identity_reasons = [
                    f"website named in the entity's own registry record and operated by its registered forretningsfører {manager['name']} "
                    f"({manager['organisation_number']}), whose organisation number is on the site"
                ]
                pages = candidate_pages
                break
            if verdict["publishable"]:
                result.status = "verified"
                result.site_url = candidate["url"]
                result.identity_class = "REGISTRY_LINKED" if candidate["source"] == "registry_hjemmeside" else "FIRST_PARTY_CONFIRMED"
                result.identity_reasons = verdict["reasons"]
                result.identity_source = candidate["source"]
                pages = candidate_pages
                break

    if result.status == "verified" and pages:
        _enrich(target, session, budget, result, pages)
    else:
        result.pages = [_page_record(url, response) for url, response in pages]
    result.requests, result.cache_hits, result.budget_exhausted = budget.requests, budget.cache_hits, budget.exhausted
    if result.status != "verified" and budget.exhausted:
        result.status = "budget_exhausted"
    result.runtime_ms = int((time.monotonic() - started) * 1000)
    return result


def _enrich(profile: dict[str, Any], session: SiteSession, budget: CompanyBudget, result: SiteResult, pages: list[tuple[str, ByteFetch]]) -> None:
    home_url, home = pages[0]
    domain = _registered_domain(home_url)
    soup = BeautifulSoup(home.raw.decode("utf-8", errors="replace"), "lxml")
    feeds, news, careers = [], [], []
    for link in soup.select('link[rel~="alternate"][href]'):
        if any(kind in str(link.get("type") or "") for kind in ("rss", "atom")):
            url = urllib.parse.urljoin(home_url, link["href"])
            if _registered_domain(url) == domain and "comments" not in url:
                feeds.append(url)
    for anchor in soup.select("a[href]"):
        url = urllib.parse.urljoin(home_url, anchor["href"]).split("#")[0]
        if not url.startswith("http") or _registered_domain(url) != domain or url.rstrip("/") == home_url.rstrip("/"):
            continue
        label = (urllib.parse.urlsplit(url).path + " " + anchor.get_text(" ", strip=True)).casefold()
        if any(hint in label for hint in NEWS_HINTS):
            news.append(url)
        elif any(hint in label for hint in CAREER_HINTS):
            careers.append(url)
    if not feeds and not news and not careers:
        state, sitemap = session.get(urllib.parse.urljoin(home_url, "/sitemap.xml"), budget, accept="application/xml,text/xml")
        if state == "ok":
            for loc in BeautifulSoup(sitemap.raw, "xml").find_all("loc")[:500]:
                url = loc.get_text(strip=True)
                path = urllib.parse.urlsplit(url).path.casefold()
                if _registered_domain(url) != domain:
                    continue
                if any(hint in path for hint in NEWS_HINTS) and path.count("/") <= 2:
                    news.append(url)
                elif any(hint in path for hint in CAREER_HINTS):
                    careers.append(url)
    result.careers_page = careers[0] if careers else None
    fetched: list[tuple[str, ByteFetch]] = list(pages)
    feed_pages: list[CapturedPage] = []
    for url in list(dict.fromkeys(feeds))[:1]:
        state, response = session.get(url, budget, accept="application/rss+xml,application/atom+xml,application/xml,text/xml")
        if state == "ok":
            feed_pages.append(CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at, kind="feed"))
    news_page: CapturedPage | None = None
    for url in list(dict.fromkeys(news))[:1] + list(dict.fromkeys(careers))[:1]:
        state, response = session.get(url, budget)
        if state == "ok":
            fetched.append((url, response))
            if url in news and news_page is None:
                news_page = CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at)
    captured = [CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at) for url, response in fetched]
    facts = extract_site_facts(profile, captured, feed_pages)
    if not facts.activities and news_page is not None:
        # The news listing states no dates: the dates are on the article pages it links (same verified site).
        # Fetch at most MAX_ARTICLE_FETCHES of them through the same budget, robots and Crawl-delay controls.
        for url in article_links(news_page, MAX_ARTICLE_FETCHES):
            state, response = session.get(url, budget)
            if state == "ok":
                fetched.append((url, response))
                result.articles_fetched += 1
        if result.articles_fetched:
            captured = [CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at) for url, response in fetched]
            facts = extract_site_facts(profile, captured, feed_pages)
    apply_site_facts(result, facts)
    result.pages = [_page_record(url, response) for url, response in fetched]


def apply_site_facts(result: SiteResult, facts: Any) -> None:
    """Store the validated first-party facts on the site result (the profile record claims are built from)."""
    relationship = f"{result.identity_class} website -> officially linked profile"
    result.profiles = [{**item, "relationship": relationship} for item in facts.profiles]
    result.ambiguous_profiles = [{**item, "relationship": relationship} for item in facts.ambiguous_profiles]
    result.activities = facts.activities
    result.jobs = facts.jobs
    result.careers_checked = facts.careers_checked
    result.extraction_rejections = dict(facts.rejections)
    result.rejected_examples = facts.rejected_examples
    if result.identity_class == "MANAGER_DESIGNATED":
        # The site belongs to the business manager and serves many entities: only its most recent dated news is
        # published as the designated website's activity; the manager's own profiles, vacancies and careers page
        # are never attributed to the managed entity.
        held = "profile of the business manager's site; not attributed to the managed entity"
        result.ambiguous_profiles += [{**item, "identity_reason": held} for item in result.profiles]
        counts = result.extraction_rejections
        if result.profiles:
            counts["social:manager_site_profile"] = counts.get("social:manager_site_profile", 0) + len(result.profiles)
        if result.jobs:
            counts["job:manager_site_vacancy"] = counts.get("job:manager_site_vacancy", 0) + len(result.jobs)
        result.profiles, result.jobs, result.careers_page, result.careers_checked = [], [], None, []
        result.activities = sorted(result.activities, key=lambda item: str(item.get("date") or ""), reverse=True)[:MANAGER_SITE_MAX_NEWS]
