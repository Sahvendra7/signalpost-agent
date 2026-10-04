from __future__ import annotations

import json
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup
import extruct
import tldextract
import trafilatura

from .evidence import evidence

USER_AGENT = "builderr-signalpost-poc/0.1 (+https://builderr.ai)"
SOCIAL_HOSTS = {
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
}
PRIORITY_TERMS = (
    "om-oss", "om_oss", "about", "kontakt", "contact", "ledelse", "management",
    "team", "people", "locations", "lokasjoner", "avdelinger", "butikker",
    "news", "press", "aktuelt", "nyheter",
)


# Builderr source policy: these platforms are never fetched (a profile is recorded from the verified site's
# own outbound link only). Enforced for initial URLs and for every redirect hop.
RESTRICTED_PLATFORM_DOMAINS = frozenset({
    "linkedin.com", "facebook.com", "fb.com", "fb.me", "instagram.com", "youtube.com", "youtu.be",
    "x.com", "twitter.com", "t.co", "tiktok.com", "threads.net",
})


def restricted_platform(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in RESTRICTED_PLATFORM_DOMAINS)


def assert_public_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Only public HTTP(S) URLs are allowed")
    if restricted_platform(host):
        raise ValueError(f"Restricted platform host is never fetched: {host}")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Local hosts are blocked")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Hostname did not resolve") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Private, loopback, link-local, multicast, and reserved addresses are blocked")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Every redirect target must be a public HTTP(S) URL; at most 5 hops (RFC 9309 asks for at least 5)."""

    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        assert_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


SAFE_OPENER = urllib.request.build_opener(SafeRedirectHandler())


def normalize_homepage(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


# Public suffix list: only the snapshot bundled in the pinned tldextract wheel (docs/dependencies.md).
# No suffix-list URLs and no cache directory, so domain parsing never contacts publicsuffix.org (or
# GitHub) and never writes to ~/.cache. The default `tldextract.extract` would download the live list.
SUFFIX_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, fallback_to_snapshot=True)


def _registered_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    ext = SUFFIX_EXTRACTOR(parsed.hostname or "")
    return ext.top_domain_under_public_suffix


ROBOTS_MAX_BYTES = 512_000  # RFC 9309 2.5: parse at least the first 500 KiB
MAX_CRAWL_DELAY_SECONDS = 30.0  # half the 60 s company budget; a longer Crawl-delay is skipped, never violated


def robots_policy(status: int, body: bytes | None) -> tuple[urllib.robotparser.RobotFileParser | None, str]:
    """robots.txt fetch outcome -> (parser or None for disallow-all, reason). RFC 9309 2.3.1:
    200 parse; 4xx "unavailable" may crawl, except 401/403 which are treated as disallow (as CPython's
    RobotFileParser does); 429, 5xx and network failure "unreachable" -> complete disallow."""
    if status == 200:
        lines = (body or b"")[:ROBOTS_MAX_BYTES].decode("utf-8", errors="replace").splitlines()
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(lines)
        parser.signalpost_crawl_delay = _group_crawl_delay(lines)  # type: ignore[attr-defined]
        return parser, "robots_ok"
    if status in (401, 403):
        return None, "robots_forbidden"
    if 400 <= status < 500 and status != 429:
        parser = urllib.robotparser.RobotFileParser()
        parser.parse([])
        return parser, "robots_absent"
    return None, "robots_unreachable"


def _group_crawl_delay(lines: list[str]) -> float | None:
    """Crawl-delay for our agent group (else the * group). CPython's parser drops non-integer values."""
    token = USER_AGENT.split("/")[0].casefold()
    delays: dict[str, float] = {}
    agents: list[str] = []
    in_rules = False
    for line in lines:
        key, _, value = line.split("#", 1)[0].partition(":")
        key, value = key.strip().casefold(), value.strip()
        if key == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.casefold())
        elif key:
            in_rules = True
            if key == "crawl-delay":
                try:
                    delay = float(value)
                except ValueError:
                    continue
                for agent in agents:
                    if agent == "*" or (agent and agent in token):
                        delays.setdefault("own" if agent != "*" else "*", delay)
    return delays.get("own", delays.get("*"))


def crawl_delay(parser: urllib.robotparser.RobotFileParser | None) -> float:
    if parser is None:
        return 0.0
    value = getattr(parser, "signalpost_crawl_delay", None)
    if value is None:
        try:
            value = parser.crawl_delay(USER_AGENT)
        except (TypeError, ValueError):
            value = None
    try:
        return max(0.0, float(value)) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _robots_check(url: str, timeout: float) -> tuple[bool, str, float]:
    """(allowed, reason, crawl delay seconds) for one URL, one robots.txt request (redirects re-checked)."""
    from .http import fetch_bytes

    assert_public_url(url)
    parsed = urllib.parse.urlparse(url)
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    response = fetch_bytes(robots_url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"}, timeout=timeout, attempts=1, max_bytes=ROBOTS_MAX_BYTES * 4, opener=SAFE_OPENER)
    parser, reason = robots_policy(response.status, response.raw)
    if parser is None:
        return False, reason, 0.0
    if not parser.can_fetch(USER_AGENT, url):
        return False, "robots_disallowed", 0.0
    return True, reason, crawl_delay(parser)


def _robots_allowed(url: str, timeout: float) -> bool:
    return _robots_check(url, timeout)[0]


def _social_links(base_url: str, soup: BeautifulSoup) -> list[dict[str, str]]:
    found: dict[tuple[str, str], dict[str, str]] = {}
    candidates = [str(node.get("href") or "") for node in soup.select("a[href]")]
    candidates.extend(str(node.get("data-href") or "") for node in soup.select("[data-href]"))
    candidates.extend(str(node.get("src") or "") for node in soup.select("iframe[src]"))
    for candidate in candidates:
        url = urllib.parse.urljoin(base_url, candidate)
        parsed_candidate = urllib.parse.urlparse(url)
        if (parsed_candidate.hostname or "").casefold().removeprefix("www.") == "facebook.com" and parsed_candidate.path.startswith("/plugins/"):
            embedded = urllib.parse.parse_qs(parsed_candidate.query).get("href", [])
            if embedded:
                url = embedded[0]
        normalized = normalize_social_url(url)
        if not normalized:
            continue
        found[(normalized["platform"], normalized["url"])] = normalized
    return sorted(found.values(), key=lambda item: (item["platform"], item["url"]))


def structured_social_links(value: Any) -> list[dict[str, str]]:
    found: dict[tuple[str, str], dict[str, str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            same_as = node.get("sameAs")
            urls = same_as if isinstance(same_as, list) else [same_as]
            for raw in urls:
                if not isinstance(raw, str):
                    continue
                normalized = normalize_social_url(raw.strip())
                if normalized:
                    found[(normalized["platform"], normalized["url"])] = normalized
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return sorted(found.values(), key=lambda item: (item["platform"], item["url"]))


def normalize_social_url(url: str) -> dict[str, str] | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    platform = next((label for domain, label in SOCIAL_HOSTS.items() if host == domain or host.endswith("." + domain)), None)
    if not platform:
        return None
    parts = [part.strip() for part in parsed.path.split("/") if part.strip()]
    lowered = [part.casefold() for part in parts]
    rejected_first = {
        "facebook": {"sharer", "sharer.php", "share.php", "dialog", "policy.php", "privacy", "events", "groups", "plugins",
                     "watch", "hashtag", "login", "login.php", "home.php", "photo.php", "story.php", "permalink.php", "media", "help", "legal", "terms"},
        "instagram": {"p", "reel", "reels", "stories", "explore", "accounts", "tv"},
        "x": {"intent", "share", "home", "search", "i"},
    }
    if platform == "facebook" and lowered[:1] == ["pg"]:
        parts, lowered = parts[1:], lowered[1:]  # facebook.com/pg/<page>/about is the same page as facebook.com/<page>
    if not parts or lowered[0] in rejected_first.get(platform, set()):
        return None
    if platform == "facebook" and lowered[0] == "profile.php":
        return None
    if platform == "linkedin" and (lowered[0] != "company" or len(parts) < 2):
        return None
    if platform == "youtube" and lowered[0] not in {"channel", "user", "c"} and not parts[0].startswith("@"):
        return None
    if host == "youtu.be":
        return None
    if platform == "tiktok" and not parts[0].startswith("@"):
        return None
    if platform == "x" and len(parts) != 1:
        return None
    canonical_host = {
        "linkedin": "linkedin.com",
        "facebook": "facebook.com",
        "instagram": "instagram.com",
        "x": "x.com",
        "youtube": "youtube.com",
        "tiktok": "tiktok.com",
    }[platform]
    if platform == "linkedin":
        parts = parts[:2]
    elif platform == "facebook":
        # One page, many sub-paths (/about, /posts/123, /photos): the page is the first segment, except the
        # legacy /pages/<name>/<id> and /people/<name>/<id> forms, which need all three.
        parts = parts[:3] if lowered[0] in {"pages", "people"} else parts[:1]
    elif platform == "instagram":
        parts = parts[:1]
    elif platform == "youtube":
        parts = parts[:1] if parts[0].startswith("@") else parts[:2]
    return {"platform": platform, "url": f"https://{canonical_host}/{'/'.join(parts)}"}


def _priority_links(base_url: str, soup: BeautifulSoup, limit: int = 4) -> list[str]:
    base = urllib.parse.urlparse(base_url)
    candidates: dict[str, int] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != base.netloc.lower():
            continue
        haystack = (parsed.path + " " + anchor.get_text(" ", strip=True)).casefold()
        rank = next((index for index, term in enumerate(PRIORITY_TERMS) if term in haystack), None)
        if rank is None:
            continue
        clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))
        if clean.rstrip("/") == base_url.rstrip("/"):
            continue
        candidates[clean] = min(rank, candidates.get(clean, rank))
    return [url for url, _ in sorted(candidates.items(), key=lambda item: (item[1], item[0]))[:limit]]


def _fetch_secondary_page(url: str, *, homepage_domain: str, timeout: float, max_bytes: int) -> tuple[dict[str, Any] | None, list[dict[str, str]], int, int, int, str | None]:
    if not _robots_allowed(url, timeout):
        return None, [], 1, 0, 0, "robots.txt disallows page"
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with SAFE_OPENER.open(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            elapsed = int((time.monotonic() - started) * 1000)
            final_url = response.geturl()
            if len(raw) > max_bytes or "html" not in response.headers.get("content-type", "").lower():
                return None, [], 2, len(raw), elapsed, "unsupported or oversized page"
            if _registered_domain(final_url) != homepage_domain:
                return None, [], 2, len(raw), elapsed, "redirected outside registered domain"
        page_html = raw.decode("utf-8", errors="replace")
        page_soup = BeautifulSoup(page_html, "lxml")
        page_text = trafilatura.extract(page_html, url=final_url, include_links=False, include_tables=False, favor_precision=True) or ""
        page = {
            "url": final_url,
            "title": page_soup.title.get_text(" ", strip=True)[:500] if page_soup.title else "",
            "main_text_excerpt": page_text[:5000],
            "identity_text_excerpt": identity_text(page_soup),
            "content_sha256": __import__("hashlib").sha256(raw).hexdigest(),
        }
        return page, _social_links(final_url, page_soup), 2, len(raw), elapsed, None
    except Exception as exc:
        return None, [], 2, 0, int((time.monotonic() - started) * 1000), f"{type(exc).__name__}: {str(exc)[:120]}"


IDENTITY_SELECTOR = 'footer, address, [itemprop="legalName"], [itemprop="address"], [itemprop="telephone"], [itemprop="email"]'


def identity_text(soup: BeautifulSoup) -> str:
    """Footer/address text, where Norwegian sites print org.nr; main-text extraction usually drops it."""
    text = " ".join(node.get_text(" ", strip=True) for node in soup.select(IDENTITY_SELECTOR))
    return " ".join(text.split())[:3000]


def _jsonld_organisations(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            kind = value.get("@type")
            kinds = set(kind if isinstance(kind, list) else [kind])
            if kinds & {"Organization", "Corporation", "LocalBusiness", "Store", "Restaurant"}:
                values.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(metadata.get("json-ld", []))
    return values[:20]


def _extraction_state(text: str, soup: BeautifulSoup) -> str:
    return "js_fallback_candidate" if len(text.strip()) < 100 and len(soup.select("script[src]")) >= 2 else "static_complete"


def fetch_website(url: str | None, *, timeout: float = 15.0, max_bytes: int = 2_000_000) -> tuple[dict[str, Any], dict[str, Any]]:
    supplied_url = str(url or "").strip()
    supplied_scheme = bool(re.match(r"^https?://", supplied_url, re.I))
    normalized = normalize_homepage(url)
    if not normalized:
        return evidence("website", "not_found", "registry_linked_company_website", "https://data.brreg.no/enhetsregisteret/api/enheter", note="No valid registry website URL"), {"requests": 0, "bytes": 0, "latencies_ms": []}
    try:
        assert_public_url(normalized)
    except ValueError as exc:
        return evidence("website", "blocked", "registry_linked_company_website", normalized, note=str(exc)), {"requests": 0, "bytes": 0, "latencies_ms": []}
    allowed, robots_reason, delay = _robots_check(normalized, timeout)
    if not allowed:
        notes = {"robots_disallowed": "robots.txt disallows this user agent", "robots_forbidden": "robots.txt returned 401/403 (treated as disallow)", "robots_unreachable": "robots.txt unreachable (5xx/429/network; RFC 9309: assume disallow)"}
        return evidence("website", "blocked", "registry_linked_company_website", normalized, note=notes.get(robots_reason, robots_reason)), {"requests": 1, "bytes": 0, "latencies_ms": []}
    if delay > MAX_CRAWL_DELAY_SECONDS:
        return evidence("website", "blocked", "registry_linked_company_website", normalized, note=f"robots.txt Crawl-delay {delay:g}s exceeds the per-company budget; not fetched"), {"requests": 1, "bytes": 0, "latencies_ms": []}
    if delay:
        time.sleep(delay)  # Crawl-delay between the robots.txt request and the homepage request
    started = time.monotonic()
    request = urllib.request.Request(normalized, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with SAFE_OPENER.open(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read(max_bytes + 1)
            elapsed = int((time.monotonic() - started) * 1000)
            if len(raw) > max_bytes:
                return evidence("website", "blocked", "registry_linked_company_website", normalized, note="Homepage exceeds byte limit"), {"requests": 2, "bytes": len(raw), "latencies_ms": [elapsed]}
            if "html" not in content_type.lower():
                return evidence("website", "source_error", "registry_linked_company_website", normalized, note=f"Unsupported content type: {content_type}"), {"requests": 2, "bytes": len(raw), "latencies_ms": [elapsed]}
            final_url = response.geturl()
            assert_public_url(final_url)
        html = raw.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        structured = extruct.extract(html, base_url=final_url, syntaxes=["json-ld", "microdata", "opengraph"])
        text = trafilatura.extract(html, url=final_url, include_links=False, include_tables=False, favor_precision=True) or ""
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description_tag = soup.select_one('meta[name="description"], meta[property="og:description"]')
        description = str(description_tag.get("content") or "").strip() if description_tag else ""
        value = {
            "requested_url": normalized,
            "final_url": final_url,
            "registered_domain": _registered_domain(final_url),
            "title": title[:500],
            "description": description[:2000],
            "main_text_excerpt": text[:5000],
            "identity_text_excerpt": identity_text(soup),
            "social_links": _social_links(final_url, soup),
            "structured_organisations": _jsonld_organisations(structured),
            "content_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "extraction_state": _extraction_state(text, soup),
        }
        pages = [{"url": final_url, "title": title[:500], "main_text_excerpt": text[:5000], "content_sha256": value["content_sha256"]}]
        social = value["social_links"]
        crawl_errors = []
        requests = 2
        bytes_received = len(raw)
        page_latencies = [elapsed]
        homepage_domain = value["registered_domain"]
        for page_url in _priority_links(final_url, soup):
            if delay:
                # Crawl-delay applies: the homepage only. Deeper pages are left to site research, which paces them.
                crawl_errors.append({"url": page_url, "error": f"skipped: robots.txt Crawl-delay {delay:g}s"})
                continue
            page, page_social, page_requests, page_bytes, page_elapsed, page_error = _fetch_secondary_page(
                page_url,
                homepage_domain=homepage_domain,
                timeout=timeout,
                max_bytes=min(max_bytes, 1_000_000),
            )
            requests += page_requests
            bytes_received += page_bytes
            if page_elapsed:
                page_latencies.append(page_elapsed)
            if page:
                pages.append(page)
                social.extend(page_social)
            elif page_error:
                crawl_errors.append({"url": page_url, "error": page_error})
        value["pages"] = pages
        value["social_links"] = list({(item["platform"], item["url"]): item for item in social}.values())
        value["crawl_errors"] = crawl_errors
        return evidence("website", "available", "registry_linked_company_website", final_url, value=value, note="Company-controlled claim layer; not an official registry fact", content_sha256=value["content_sha256"]), {"requests": requests, "bytes": bytes_received, "latencies_ms": page_latencies}
    except urllib.error.HTTPError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        status = "not_found" if exc.code in {404, 410} else "source_error"
        return evidence("website", status, "registry_linked_company_website", normalized, note=f"HTTP {exc.code}"), {"requests": 2, "bytes": 0, "latencies_ms": [elapsed]}
    except urllib.error.URLError as exc:
        if not supplied_scheme and normalized.startswith("https://"):
            first_elapsed = int((time.monotonic() - started) * 1000)
            record, metrics = fetch_website("http://" + supplied_url, timeout=timeout, max_bytes=max_bytes)
            metrics["requests"] += 2
            metrics["latencies_ms"].insert(0, first_elapsed)
            return record, metrics
        elapsed = int((time.monotonic() - started) * 1000)
        return evidence("website", "source_error", "registry_linked_company_website", normalized, note=f"URLError: {str(exc.reason)[:180]}"), {"requests": 2, "bytes": 0, "latencies_ms": [elapsed]}
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        return evidence("website", "source_error", "registry_linked_company_website", normalized, note=f"{type(exc).__name__}: {str(exc)[:180]}"), {"requests": 2, "bytes": 0, "latencies_ms": [elapsed]}
