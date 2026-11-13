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
from .attribution.jobs import is_recruiter
from .attribution.news import is_publisher
from .site_facts import CAREER_PATH, is_careers_page  # noqa: F401
from .site_facts import ARTICLE_TYPES, CapturedPage, article_links, extract_site_facts, feed_items, html_items, in_site_scope, is_shared_site_section, item_names_entity, job_postings, parse_date, site_chrome  # noqa: F401  (re-exported)
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
MAX_JOB_FETCHES = 3  # V3.1.1: advertisement pages followed from the careers page when its cards state no dates
MANAGER_SITE_MAX_NEWS = 5  # a business manager's site serves many entities: at most this many items that name the entity


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
    status: str  # verified | none_verified | budget_exhausted | unreadable (the registry-verified site could not be read)
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
    job_pages_fetched: int = 0
    careers_checked: list[dict[str, Any]] = field(default_factory=list)
    articles_fetched: int = 0
    manager: dict[str, Any] | None = None  # MANAGER_DESIGNATED: the registered forretningsfører operating the site
    operator: dict[str, Any] | None = None  # V3: who runs the verified site (attribution.operator)
    rejected_keys: list[dict[str, Any]] = field(default_factory=list)  # V3 §B8: candidates a rule rejected (for retractions)
    feeds_read: list[list[Any]] = field(default_factory=list)  # [url, sha256, retrieved_at] of every feed read
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
        # A verified site this run could not read (robots.txt, transport, budget) was not checked at all: an outage,
        # not a site without facts.
        result.status = "verified" if state == "ok" else "unreadable"
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
    if result.status == "none_verified" and budget.exhausted:
        result.status = "budget_exhausted"
    result.runtime_ms = int((time.monotonic() - started) * 1000)
    return result


def _enrich(profile: dict[str, Any], session: SiteSession, budget: CompanyBudget, result: SiteResult, pages: list[tuple[str, ByteFetch]]) -> None:
    home_url, home = pages[0]
    soup = BeautifulSoup(home.raw.decode("utf-8", errors="replace"), "lxml")
    # A verified site that is a section of a shared domain (a chain's branch page) reads only pages inside its section,
    # and one on a subdomain (a hosting platform's tenant) only pages on its own host: the domain owner's news, feed
    # and careers pages are not the entity's.
    section = urllib.parse.urlsplit(home_url).path.rstrip("/") + "/" if is_shared_site_section(home_url) else None

    def inside(url: str) -> bool:
        return in_site_scope(url, home_url) and (section is None or (urllib.parse.urlsplit(url).path.rstrip("/") + "/").startswith(section))

    feeds, news, careers = [], [], []
    for link in soup.select('link[rel~="alternate"][href]'):
        if any(kind in str(link.get("type") or "") for kind in ("rss", "atom")):
            url = urllib.parse.urljoin(home_url, link["href"])
            if "comments" not in url and inside(url):
                feeds.append(url)
    for anchor in soup.select("a[href]"):
        url = urllib.parse.urljoin(home_url, anchor["href"]).split("#")[0]
        if not url.startswith("http") or url.rstrip("/") == home_url.rstrip("/") or not inside(url):
            continue
        label = (urllib.parse.urlsplit(url).path + " " + anchor.get_text(" ", strip=True)).casefold()
        if any(hint in label for hint in NEWS_HINTS):
            news.append(url)
        elif career_link(url, anchor.get_text(" ", strip=True)):
            careers.append(url)
    if not feeds and not news and not careers:
        state, sitemap = session.get(urllib.parse.urljoin(home_url, "/sitemap.xml"), budget, accept="application/xml,text/xml")
        if state == "ok":
            for loc in BeautifulSoup(sitemap.raw, "xml").find_all("loc")[:500]:
                url = loc.get_text(strip=True)
                path = urllib.parse.urlsplit(url).path.casefold()
                if not inside(url):
                    continue
                if any(hint in path for hint in NEWS_HINTS) and path.count("/") <= 2:
                    news.append(url)
                elif career_link(url, ""):
                    careers.append(url)
    result.careers_page = careers[0] if careers else None
    fetched: list[tuple[str, ByteFetch]] = list(pages)
    feed_pages: list[CapturedPage] = []
    for url in list(dict.fromkeys(feeds))[:1]:
        state, response = session.get(url, budget, accept="application/rss+xml,application/atom+xml,application/xml,text/xml")
        if state == "ok":
            feed_pages.append(CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at, kind="feed"))
            result.feeds_read.append([url, response.content_sha256, response.retrieved_at])
    news_page: CapturedPage | None = None
    for url in list(dict.fromkeys(news))[:1] + list(dict.fromkeys(careers))[:1]:
        state, response = session.get(url, budget)
        if state == "ok":
            fetched.append((url, response))
            if url in news and news_page is None:
                news_page = CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at)
    captured = [CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at) for url, response in fetched]
    website = (profile.get("evidence") or {}).get("website") or {}
    context = {"identity_class": result.identity_class,
               "website_value": (website.get("value") or {}) if result.identity_class == "REGISTRY_LINKED" and website.get("status") == "available" else None}
    facts = extract_site_facts(profile, captured, feed_pages, **context)
    if not facts.activities and news_page is not None:
        # The news listing states no dates: the dates are on the article pages it links (same verified site).
        # Fetch at most MAX_ARTICLE_FETCHES of them through the same budget, robots and Crawl-delay controls.
        for url in [url for url in article_links(news_page, MAX_ARTICLE_FETCHES * 3) if inside(url)][:MAX_ARTICLE_FETCHES]:
            state, response = session.get(url, budget)
            if state == "ok":
                fetched.append((url, response))
                result.articles_fetched += 1
        if result.articles_fetched:
            captured = [CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at) for url, response in fetched]
            facts = extract_site_facts(profile, captured, feed_pages, **context)
    # V3.1.1: positions the careers page lists without a date are dated only by their own advertisement page. Read at
    # most MAX_JOB_FETCHES of them, on the company's own site, through the same budget, robots and Crawl-delay controls.
    careers_url = result.careers_page
    careers_page = next((page for page in captured if page.url == careers_url), None) if careers_url else None
    if careers_page is not None and is_careers_page(careers_page):
        from .site_facts import job_listings
        listed, _ = job_listings(careers_page)
        undated = [str(job["url"]).split("#")[0] for job in listed
                   if not (job.get("application_deadline") or job.get("date_posted")) and inside(str(job.get("url") or ""))]
        followed = 0
        for url in list(dict.fromkeys(undated)):
            if followed >= MAX_JOB_FETCHES or any(url == known for known, _ in fetched):
                continue
            state, response = session.get(url, budget)
            if state == "ok":
                fetched.append((url, response))
                followed += 1
        if followed:
            result.job_pages_fetched = followed
            captured = [CapturedPage(url, response.raw, response.content_sha256, response.retrieved_at) for url, response in fetched]
            facts = extract_site_facts(profile, captured, feed_pages, **context)
    apply_site_facts(result, facts, profile, captured + feed_pages)
    result.pages = [_page_record(url, response) for url, response in fetched]


CAREER_LABEL = re.compile(r"^(?:ledige stillinger|stillinger|karriere|career|careers|jobs|jobb|vacancies|open positions|work with us|join us|"
                          r"jobb(?:e)? (?:hos|i|med|for) [\w .&-]{1,40}|bli med (?:oss|på laget)|ledig stilling)$", re.I)
OWN_CAREERS = re.compile(r"(?:jobb(?:e)?-(?:hos|i)-|karriere|career|work-(?:with|for)-us|join-us|bli-en-av-oss)")
SERVICE_SEGMENTS = {"for-bedrifter", "bedrift", "bedrifter", "arbeidsgivere", "for-arbeidsgivere", "arbeidsgiver", "tjenester", "kunder", "for-kunder", "services"}


def service_page(url: str) -> bool:
    segments = [segment for segment in urllib.parse.unquote(urllib.parse.urlsplit(url).path).casefold().split("/") if segment]
    if segments and CAREER_PATH.search("/" + segments[-1]):
        return False  # /tjenester/om-kommunen/jobb-i-grane-kommune-ledige-stillinger is the careers page itself
    return any(segment in SERVICE_SEGMENTS for segment in segments)


def career_link(url: str, text: str) -> bool:
    """A link to the careers page: a careers path segment, or a link labelled as one ("Ledige stillinger", "Jobb hos
    oss"). A service page for employers or customers is not one, whatever its label."""
    if service_page(url):
        return False
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).casefold()
    return bool(CAREER_PATH.search(path)) or bool(CAREER_LABEL.match(" ".join(text.split())))


def apply_site_facts(result: SiteResult, facts: Any, profile: dict[str, Any] | None = None, pages: list[CapturedPage] | None = None) -> None:
    """Store the validated first-party facts on the site result (the profile record claims are built from)."""
    relationship = f"{result.identity_class} website -> officially linked profile"
    result.profiles = [{**item, "relationship": relationship} for item in facts.profiles]
    result.ambiguous_profiles = [{**item, "relationship": relationship} for item in facts.ambiguous_profiles]
    result.activities = facts.activities
    result.jobs = facts.jobs
    result.careers_checked = facts.careers_checked
    result.extraction_rejections = dict(facts.rejections)
    result.rejected_examples = facts.rejected_examples
    result.operator = getattr(facts, "operator", None)
    result.rejected_keys = list(getattr(facts, "rejected_keys", []) or [])

    def held(family: str, key_value: Any, code: str, **extra: Any) -> None:
        from .refresh import site_key
        result.rejected_keys.append({"family": family, "code": code, "key": site_key(family, key_value, **extra)})
    if result.careers_page:
        # V3 §B7: the linked page must itself be a careers page (path or heading), not a service page for employers.
        fetched_page = next((page for page in pages or [] if page.url == result.careers_page and page.kind == "html"), None)
        board = profile is not None and (is_recruiter(profile) or is_publisher(profile)) and not OWN_CAREERS.search(urllib.parse.unquote(urllib.parse.urlsplit(result.careers_page).path).casefold())
        if board:
            # A recruiter's vacancies page lists its clients' jobs: it is not a page about working at the recruiter.
            counts = result.extraction_rejections
            counts["careers:recruiter_job_board"] = counts.get("careers:recruiter_job_board", 0) + 1
            held("careers", result.careers_page, "recruiter_job_board")
            result.careers_page, result.careers_checked = None, []
        elif any(item.get("url") == result.careers_page and item.get("other_employer_positions", 0) >= 2 and not item.get("own_positions")
                 and 2 * item.get("other_employer_positions", 0) >= item.get("positions", 0) for item in result.careers_checked):
            # V3.1.1: every position the page lists names another employer (a member organisation's or client's job
            # board, FUNDRAISING NORGE on evalh400): it is not a page about working at this company.
            counts = result.extraction_rejections
            counts["careers:job_board_for_other_employers"] = counts.get("careers:job_board_for_other_employers", 0) + 1
            held("careers", result.careers_page, "job_board_for_other_employers")
            result.careers_page, result.careers_checked = None, []
        elif fetched_page is None or not is_careers_page(fetched_page) or service_page(result.careers_page):
            counts = result.extraction_rejections
            counts["careers:not_a_careers_page"] = counts.get("careers:not_a_careers_page", 0) + 1
            held("careers", result.careers_page, "not_a_careers_page")
            result.careers_page, result.careers_checked = None, [item for item in result.careers_checked if item.get("url") != fetched_page.url] if fetched_page else []
    if getattr(facts, "brand_site", False) and result.careers_page:
        # V3.1.1: an international brand site that never writes the Norwegian company's legal name (INLUMI AS on
        # inlumi.com): its careers page is the brand's.
        counts = result.extraction_rejections
        counts["careers:international_brand_site"] = counts.get("careers:international_brand_site", 0) + 1
        held("careers", result.careers_page, "international_brand_site")
        result.careers_page, result.careers_checked = None, []
    kind = (result.operator or {}).get("kind")
    if kind in ("other_entity", "group_or_brand"):
        # V3 §B5: another company (or a group/brand) runs the site. Its careers page and vacancies are not this
        # company's; profiles were already decided per handle (attribution.social), news per item (attribution.news).
        counts = result.extraction_rejections
        if result.jobs:
            counts[f"job:site_operated_by_{kind}"] = counts.get(f"job:site_operated_by_{kind}", 0) + len(result.jobs)
        for job in result.jobs:
            held("job", job, f"site_operated_by_{kind}", page_url=job.get("page_url"))
        if result.careers_page:
            counts[f"careers:site_operated_by_{kind}"] = counts.get(f"careers:site_operated_by_{kind}", 0) + 1
            held("careers", result.careers_page, f"site_operated_by_{kind}")
        result.jobs, result.careers_page = [], None
    if result.identity_class == "MANAGER_DESIGNATED":
        # The site is associated with the entity (its registry record names it), but it belongs to the business
        # manager and serves many entities. The association is the website claim; the manager's own content is not
        # the entity's: its profiles, vacancies and careers page never, and its news only when an item explicitly
        # names the managed entity (site_facts.item_names_entity).
        held = "profile of the business manager's site; not attributed to the managed entity"
        result.ambiguous_profiles += [{**item, "identity_reason": held} for item in result.profiles]
        counts = result.extraction_rejections
        if result.profiles:
            counts["social:manager_site_profile"] = counts.get("social:manager_site_profile", 0) + len(result.profiles)
        if result.jobs:
            counts["job:manager_site_vacancy"] = counts.get("job:manager_site_vacancy", 0) + len(result.jobs)
        result.profiles, result.jobs, result.careers_page, result.careers_checked = [], [], None, []
        by_url = {page.url: page for page in pages or []}
        chrome = site_chrome(list(pages or []))  # V3.1: a footer naming every entity the manager runs names none of them
        about = []
        for item in result.activities:
            basis = item_names_entity(profile or {}, item, by_url, chrome)
            if basis:
                about.append({**item, "subject_basis": basis})
            else:
                counts["activity:manager_news_not_about_entity"] = counts.get("activity:manager_news_not_about_entity", 0) + 1
        result.activities = sorted(about, key=lambda item: str(item.get("date") or ""), reverse=True)[:MANAGER_SITE_MAX_NEWS]
