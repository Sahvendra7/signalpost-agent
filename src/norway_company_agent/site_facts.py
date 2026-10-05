"""First-party facts from pages of an already VERIFIED company website (Revision 1). Pure functions, no I/O.

    verified company website -> linked/internal page (already captured) -> extract -> validate -> publish

Three families, each read only from bytes the site stage already captured, so this adds no request:

  * social profiles: Facebook, Instagram, LinkedIn and YouTube links on the verified site. The published value is
    the URL exactly as the page links it; a canonical form is kept only as the de-duplication key. Platforms are
    never fetched. A link is accepted only with corroboration beyond "the site links it": the legal name or the
    verified domain name in the handle, or the site's own Organization structured data listing it (`sameAs`).
  * dated activity: items on the site's news/blog pages (and news links on the homepage) that state a calendar
    date next to a title, plus schema.org/meta/<time>/feed dates. No date is ever inferred from a URL or taken
    from an "updated" stamp.
  * job postings: schema.org JobPosting, and open positions listed on the site's careers page (a link to a
    posting with a job title). A careers page that lists no position yields no posting.

Every candidate passes `validate` (evidence_text.py) before it is kept: URL in the captured bytes, title in the
page text, date stated verbatim in the page. A failing candidate is counted with a reason, never repaired.
Company identity is never established here: it is inherited from the site identity gate that ran before.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import cached_property
from typing import Any

from bs4 import BeautifulSoup

from .evidence_text import content_words, date_matches, fold, span_in_text, url_in_source, words
from .identity import _tokens, assess_social_identity
from .website import _registered_domain, normalize_social_url

SOCIAL_PLATFORMS = ("facebook", "instagram", "linkedin", "youtube")
ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "Report", "PressRelease"}
ORGANISATION_TYPES = {"Organization", "Corporation", "LocalBusiness", "Store", "Restaurant", "ProfessionalService", "HomeAndConstructionBusiness", "AutomotiveBusiness", "MedicalBusiness", "FinancialService", "InsuranceAgency", "LegalService", "RealEstateAgent", "SportsClub", "EducationalOrganization", "NGO"}
MAX_ITEMS_PER_PAGE = 30
MAX_JOBS_PER_PAGE = 50

NEWS_WORDS = ("nyheter", "nyhet", "aktuelt", "news", "blogg", "blog", "artikler", "artikkel", "article", "articles", "presse", "press",
              "pressemeldinger", "pressemelding", "post", "posts", "innlegg", "magasin", "nyhetsarkiv")
NEWS_PATH = re.compile(r"(?:^|[/_-])(?:" + "|".join(NEWS_WORDS) + r")(?:$|[/_.-])")
CAREER_PATH = re.compile(r"(?:^|/)(?:[\w-]*-)?(?:ledige-stillinger|stillinger|stilling|karriere|career|careers|jobs|jobb|jobbe|vacancies|vacancy|open-positions|rekruttering|join-us|work-with-us)(?:$|[/_.-])")
CAREER_HEADINGS = ("ledige stillinger", "stillinger", "karriere", "careers", "career", "jobs", "vacancies", "jobb hos", "jobbe hos", "open positions")
STRONG_JOB_PATH = re.compile(r"(?:^|[/_-])(?:stilling|stillinger|stillingsannonse|jobs?|vacanc(?:y|ies)|positions?|utlysning)(?:[/_-][^/]{3,})")
ATS_DOMAINS = {
    "webcruiter.no", "webcruiter.com", "jobbnorge.no", "reachmee.com", "teamtailor.com", "hrmanager.no", "recman.no",
    "easycruit.com", "jobylon.com", "varbi.com", "simployer.com", "talentech.com", "lever.co", "greenhouse.io",
    "smartrecruiters.com", "workable.com", "recruitee.com", "personio.de", "personio.com", "emply.com", "hr-manager.net",
}
UPDATED_CUES = ("oppdatert", "updated", "sist endret", "endret", "modified", "last changed")
DEADLINE_CUES = ("frist", "deadline", "apply by", "gyldig til", "valid until", "utløper", "påmelding")
PUBLISHED_CUES = ("publisert", "published", "posted", "postet", "dato:")
GENERIC_TITLES = {
    "les mer", "read more", "se mer", "se alle", "se alle nyheter", "alle nyheter", "flere nyheter", "flere saker", "vis mer", "vis alle",
    "nyheter", "aktuelt", "news", "blogg", "blog", "presse", "artikler", "siste nytt", "mer", "more", "neste", "forrige", "next", "previous",
    "ledige stillinger", "stillinger", "se alle stillinger", "alle stillinger", "se stillingen", "les mer og søk", "søk", "søk her", "søk nå",
    "søk på stillingen", "søk stilling", "apply", "apply now", "apply here", "jobb hos oss", "jobbe hos oss", "karriere", "career", "careers",
    "jobs", "open positions", "åpen søknad", "open application", "generell søknad", "spontansøknad", "send åpen søknad", "kontakt oss",
}
NOT_A_POSTING_WORDS = {
    "kultur", "culture", "verdier", "values", "fordeler", "benefits", "goder", "hvorfor", "arbeidsmiljø", "medarbeiderhistorier", "historier",
    "stories", "personvern", "privacy", "rekrutteringsprosess", "prosess", "åpen", "spontan", "generell", "nyhetsbrev", "newsletter",
}
NO_OPENINGS = re.compile(
    r"ingen ledige stillinger|ingen stillinger|ingen utlyste|ingen aktuelle stillinger|ingen åpne stillinger|har for tiden ingen|for øyeblikket ingen"
    r"|så snart det kommer ledige stillinger|no open positions|no current openings|no vacancies|no positions available|currently no",
    re.I,
)
JOB_CUES = re.compile(
    r"søknadsfrist|stillingsprosent|heltid|deltid|fast stilling|fast ansettelse|vikariat|engasjement|sommerjobb|sommervikar|\d{2,3}\s?%"
    r"|arbeidssted|lokasjon|location|full[- ]time|part[- ]time|permanent|apply by|deadline",
    re.I,
)
GENERIC_JOB_TITLE = re.compile(
    r"^(?:registrer|send|lever|last opp|søk|apply|submit|upload|register)\b"
    r"|^(?:careers?|karriere|jobs?|jobb(?:e)? (?:hos|i)|ledige stillinger|stillinger|vacancies|open positions)\b"
    r"|åpen søknad|open application|generell søknad|spontan",
)
AUTHOR_PATH = re.compile(r"/(?:ansatte|ansatt|person|personer|people|author|authors|forfatter|forfattere|medarbeidere|employees|staff|profil|profile|team)(?:/|$)")
LOCATION_LABEL = re.compile(r"^(?:arbeidssted|sted|lokasjon|location|kontorsted|kontor)\s*:?\s*(.*)$", re.I)
_DROP_TAGS = ("script", "style", "noscript", "template", "svg")
_CHROME_TAGS = ("header", "nav", "footer")


# ---------- captured pages ----------

@dataclass(frozen=True)
class CapturedPage:
    """One captured response: the exact bytes behind `content_sha256`, fetched at `retrieved_at`."""

    url: str
    raw: bytes
    content_sha256: str
    retrieved_at: str
    kind: str = "html"  # html | feed

    @cached_property
    def html(self) -> str:
        return self.raw.decode("utf-8", errors="replace")

    @cached_property
    def unescaped(self) -> str:
        """Source with HTML entities and JSON \\uXXXX / \\/ escapes resolved: where structured-data titles live."""
        text = html_lib.unescape(self.html).replace("\\/", "/")
        return re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), text)

    @cached_property
    def text(self) -> str:
        if self.kind == "feed":
            return " ".join(BeautifulSoup(self.raw, "xml").get_text(" ").split())
        soup = BeautifulSoup(self.html, "lxml")
        for node in soup(list(_DROP_TAGS)):
            node.decompose()
        return " ".join(soup.get_text(" ").split())

    def soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.html, "lxml")

    def contains(self, value: Any) -> bool:
        """`value` occurs (folded) in the page's visible text or, for structured data, in its unescaped source."""
        return bool(value) and (span_in_text(value, self.text) or span_in_text(value, self.unescaped))


HOME_SEGMENTS = {"no", "nb", "nn", "en", "sv", "se", "da", "dk", "de", "index.html", "index.htm", "index.php", "hjem", "home", "forside", "start", "default.aspx"}


def is_shared_site_section(url: str) -> bool:
    """The verified website is a section of a larger domain (a federation's region page, a chain's branch page),
    not a homepage: two or more path segments, or one that is not a language or index page."""
    segments = [part for part in urllib.parse.urlsplit(url).path.split("/") if part]
    return len(segments) >= 2 or (len(segments) == 1 and segments[0].casefold() not in HOME_SEGMENTS)


def is_news_page(url: str) -> bool:
    return bool(NEWS_PATH.search(urllib.parse.urlsplit(url).path.casefold()))


def is_article_path(url: str) -> bool:
    """A single article under a news section (/artikkel/<slug>, /aktuelt/<slug>), as opposed to the section's listing
    page, where the news word is the last path segment (/om-oss/nyheter, /aktuelt)."""
    segments = [part.casefold() for part in urllib.parse.urlsplit(url).path.split("/") if part]
    news_at = [index for index, part in enumerate(segments) if NEWS_PATH.search("/" + part)]
    return bool(news_at) and news_at[-1] < len(segments) - 1


def is_careers_page(page: CapturedPage) -> bool:
    if CAREER_PATH.search(urllib.parse.unquote(urllib.parse.urlsplit(page.url).path).casefold()):
        return True
    soup = page.soup()
    heading = soup.find("h1")
    return bool(heading and fold(heading.get_text(" ", strip=True)) in CAREER_HEADINGS)


# ---------- dates and structured extraction (moved from site_research, unchanged apart from date_text) ----------

def parse_date(value: Any) -> str | None:
    """ISO-8601 UTC for an unambiguous source date; a bare YYYY-MM-DD stays a date. Never guesses."""
    text = str(value or "").strip()
    if not text:
        return None
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
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text if "1995-01-01" <= text <= (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d") else None
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
        kind, date_text = "published", published.get_text(strip=True) if published else None
        if not date and updated:
            date, kind, date_text = parse_date(updated.get_text(strip=True)), "updated", updated.get_text(strip=True)
        summary = node.find(["description", "summary"])
        snippet = BeautifulSoup(summary.get_text(" ", strip=True), "lxml").get_text(" ", strip=True)[:240] if summary else None
        items.append({"title": title.get_text(" ", strip=True)[:200] if title else None, "url": href, "date": date, "date_kind": kind if date else None, "date_text": date_text if date else None, "summary": snippet, "method": "site_feed"})
    return items


def _jsonld_nodes(soup: BeautifulSoup):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                yield node
                stack.extend(value for value in node.values() if isinstance(value, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)


def _types(node: dict) -> set[str]:
    kinds = node.get("@type")
    return {str(kind) for kind in (kinds if isinstance(kinds, list) else [kinds]) if kind}


def html_items(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    own_domain = _registered_domain(base_url)
    items: list[dict[str, Any]] = []
    for node in _jsonld_nodes(soup):
        if _types(node) & ARTICLE_TYPES:
            date = parse_date(node.get("datePublished"))
            raw_url = node.get("url") or node.get("mainEntityOfPage")
            url = urllib.parse.urljoin(base_url, raw_url) if isinstance(raw_url, str) else base_url
            if date:
                items.append({"title": str(node.get("headline") or node.get("name") or "")[:200] or None, "url": url if _registered_domain(url) == own_domain else base_url, "date": date, "date_kind": "published", "date_text": str(node.get("datePublished")), "summary": str(node.get("description") or "")[:240] or None, "method": "jsonld_datePublished"})
    meta = soup.select_one('meta[property="article:published_time"]')
    if meta and parse_date(meta.get("content")):
        items.append({"title": soup.title.get_text(" ", strip=True)[:200] if soup.title else None, "url": base_url, "date": parse_date(meta.get("content")), "date_kind": "published", "date_text": str(meta.get("content")), "summary": None, "method": "meta_article_published_time"})
    for article in soup.select("article")[:30]:
        node = article.select_one("time[datetime]")
        date = parse_date(node.get("datetime")) if node else None
        if not date:
            continue
        own = [urllib.parse.urljoin(base_url, anchor["href"]) for anchor in article.select("a[href]")]
        own = [url for url in own if url.startswith(("http://", "https://")) and _registered_domain(url) == own_domain]
        heading = article.select_one("h1, h2, h3, h4")
        items.append({"title": heading.get_text(" ", strip=True)[:200] if heading else None, "url": own[0] if own else base_url, "date": date, "date_kind": "published", "date_text": str(node.get("datetime")), "summary": None, "method": "article_time_datetime"})
    return items


def job_postings(html: str, base_url: str) -> list[dict[str, Any]]:
    """schema.org JobPosting published on the company's own site (hiring facts with source dates)."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for node in _jsonld_nodes(soup):
        if "JobPosting" not in _types(node):
            continue
        title = str(node.get("title") or "").strip()
        if not title:
            continue
        valid = parse_date(node.get("validThrough"))
        jobs.append({"title": title[:200], "date_posted": parse_date(node.get("datePosted")), "valid_through": valid, "url": node.get("url") if isinstance(node.get("url"), str) else base_url, "method": "jsonld_JobPosting"})
    return jobs


# ---------- social profiles ----------

def _compact(text: str) -> str:
    folded = unicodedata.normalize("NFKD", urllib.parse.unquote(text)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", folded)


def _organisation_owns(node: dict, site_domain: str, legal_core: list[str]) -> bool:
    """A JSON-LD Organization node describes the company itself: its url is the verified domain, or its name
    carries every legal-name token. A web agency or partner node (other url, other name) does not."""
    url = node.get("url") or node.get("@id")
    if isinstance(url, str) and url.startswith(("http://", "https://")) and _registered_domain(url) == site_domain:
        return True
    name = node.get("name") or node.get("legalName")
    return bool(legal_core) and isinstance(name, str) and set(legal_core) <= set(_tokens(name))


def social_occurrences(page: CapturedPage, page_index: int, site_domain: str, legal_core: list[str]) -> list[dict[str, Any]]:
    """Every allowed-platform profile link on one captured page, exactly as linked, in document order."""
    soup = page.soup()
    out: list[dict[str, Any]] = []
    for order, node in enumerate(soup.select("a[href], [data-href], iframe[src]")):
        attribute = "href" if node.name == "a" and node.get("href") else "src" if node.name == "iframe" and node.get("src") else "data-href"
        linked_as = str(node.get(attribute) or "").strip()
        if not linked_as:
            continue
        target = urllib.parse.urljoin(page.url, linked_as)
        parsed = urllib.parse.urlparse(target)
        via = {"href": "a_href", "src": "iframe_src", "data-href": "data_href"}[attribute]
        if (parsed.hostname or "").casefold().removeprefix("www.") == "facebook.com" and parsed.path.startswith("/plugins/"):
            embedded = urllib.parse.parse_qs(parsed.query).get("href", [])
            if not embedded:
                continue
            target, linked_as, via = embedded[0], embedded[0], "facebook_plugin_href"
        normalized = normalize_social_url(target)
        if not normalized or normalized["platform"] not in SOCIAL_PLATFORMS:
            continue
        out.append({
            "platform": normalized["platform"], "url": target, "canonical_url": normalized["url"], "linked_as": linked_as, "via": via,
            "link_text": " ".join(node.get_text(" ", strip=True).split())[:120], "in_site_chrome": bool(node.find_parent(list(_CHROME_TAGS))),
            "page_index": page_index, "order": order, "page": page,
        })
    for node in _jsonld_nodes(soup):
        if not (_types(node) & ORGANISATION_TYPES):
            continue
        same_as = node.get("sameAs")
        owner = _organisation_owns(node, site_domain, legal_core)
        for raw in same_as if isinstance(same_as, list) else [same_as]:
            if not isinstance(raw, str):
                continue
            normalized = normalize_social_url(raw.strip())
            if normalized and normalized["platform"] in SOCIAL_PLATFORMS:
                out.append({
                    "platform": normalized["platform"], "url": raw.strip(), "canonical_url": normalized["url"], "linked_as": raw.strip(),
                    "via": "jsonld_sameas", "jsonld_owner": owner, "link_text": "", "in_site_chrome": False,
                    "page_index": page_index, "order": 10_000, "page": page,
                })
    return out


def _handle(item: dict[str, Any]) -> str:
    path = urllib.parse.urlparse(item["canonical_url"]).path
    return _compact(path.split("/company/", 1)[-1] if item["platform"] == "linkedin" else path)


def social_identity(profile: dict[str, Any], occurrence: dict[str, Any], site_domain: str, *, shared_site: bool = False) -> tuple[float | None, str]:
    """(score, reason) when the linked profile is corroborated as the company's own; (None, reason) otherwise.
    Being linked from the verified site is necessary, never sufficient on its own.

    `shared_site`: the verified website is a section of a larger organisation's domain (a club's or a chain's
    subpage). The site's own links then belong to the domain owner, so only the legal-name gate can accept a
    profile there; the domain-name rule and the owner's structured data are not used."""
    if occurrence["via"] == "jsonld_sameas" and occurrence.get("jsonld_owner") and not shared_site:
        return 0.95, "listed in sameAs of the verified site's own Organization structured data"
    gate = assess_social_identity(profile, {"url": occurrence["canonical_url"]})
    if gate["publishable"]:
        return float(gate["identity_score"]), str(gate["reason"])
    if shared_site:
        return None, "verified site is a section of a shared domain; the handle does not carry the legal name"
    label = _compact(site_domain.split(".", 1)[0]) if site_domain else ""
    handle = _handle(occurrence)
    if label and (handle == label or len(label) >= 6 and (handle.startswith(label) or handle.endswith(label))):
        return 0.95, "verified website's domain name begins or ends the social handle"
    return None, str(gate["reason"])


def _profile_key(occurrence: dict[str, Any]) -> str:
    """De-duplication key for one profile: the canonical URL, case-folded where the platform's handles are
    case-insensitive (Facebook, Instagram, LinkedIn, YouTube @handles; not YouTube channel ids)."""
    canonical = occurrence["canonical_url"]
    if occurrence["platform"] == "youtube" and "/@" not in canonical:
        return canonical
    return canonical.casefold()


def _representative(group: list[dict[str, Any]]) -> dict[str, Any]:
    """The plainest occurrence of one profile: no query/fragment, earliest page, fewest path segments, first in page."""
    def rank(item: dict[str, Any]) -> tuple:
        parsed = urllib.parse.urlparse(item["url"])
        return (item["via"] == "jsonld_sameas", bool(parsed.query or parsed.fragment), item["page_index"], len([part for part in parsed.path.split("/") if part]), item["order"])
    return sorted(group, key=rank)[0]


# ---------- dated activity on news pages ----------

def _drop(soup: BeautifulSoup, chrome: bool) -> None:
    for node in soup(list(_DROP_TAGS) + (list(_CHROME_TAGS) if chrome else [])):
        node.decompose()


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _generic(title: str) -> bool:
    folded = fold(title).strip(" .:!?»>›→")
    return not folded or folded in GENERIC_TITLES


def _good_title(text: str) -> bool:
    text = _clean(text)
    return 2 <= len(content_words(text)) and len(words(text)) <= 30 and len(text) <= 200 and not _generic(text) and not date_matches(text)


def _internal_links(node: Any, page_url: str, own_domain: str) -> list[tuple[Any, str]]:
    links = []
    page = page_url.split("#")[0].rstrip("/")
    for anchor in node.select("a[href]"):
        target = urllib.parse.urljoin(page_url, str(anchor.get("href") or "").strip()).split("#")[0]
        if target.startswith(("http://", "https://")) and _registered_domain(target) == own_domain and target.rstrip("/") != page:
            links.append((anchor, target))
    return links


def listing_items(page: CapturedPage, *, require_news_link: bool) -> list[dict[str, Any]]:
    """Items on a news/blog page with a calendar date stated next to their title (no <time datetime> needed).
    The card is the smallest element around the date that holds a title and no other date."""
    soup = page.soup()
    _drop(soup, chrome=True)
    body = soup.body or soup
    own_domain = _registered_domain(page.url)
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for string in body.find_all(string=True):
        text = str(string)
        if not text.strip() or string.parent is None:
            continue
        for iso, matched, start, _end in date_matches(text):
            prefix = fold(text[max(0, start - 30):start])
            if any(cue in prefix for cue in UPDATED_CUES + DEADLINE_CUES):
                continue
            item = _card_item(string.parent, iso, page, own_domain, require_news_link)
            if item is None:
                continue
            key = (iso, fold(item["title"]))
            if key in seen:
                continue
            seen.add(key)
            item.update({"date": iso, "date_text": matched, "date_kind": "published" if any(cue in prefix for cue in PUBLISHED_CUES) else "stated_on_page", "method": "listing_visible_date"})
            items.append(item)
            if len(items) >= MAX_ITEMS_PER_PAGE:
                return items
    return items


def _card_item(start: Any, iso: str, page: CapturedPage, own_domain: str, require_news_link: bool) -> dict[str, Any] | None:
    node = start
    for _ in range(6):
        if node is None or node.name in ("body", "html", "[document]"):
            return None
        card_dates = {item[0] for item in date_matches(node.get_text(" "))}
        if card_dates - {iso}:
            return None  # climbed past this item into a list of items
        headings = [heading for heading in node.select("h1, h2, h3, h4, h5") if _good_title(heading.get_text(" ", strip=True))]
        links = [(anchor, target) for anchor, target in _internal_links(node, page.url, own_domain) if not AUTHOR_PATH.search(urllib.parse.urlsplit(target).path.casefold()) and (_good_title(anchor.get_text(" ", strip=True)) or anchor.find(["h1", "h2", "h3", "h4", "h5"]))]
        if node.name == "a" and node.get("href"):
            target = urllib.parse.urljoin(page.url, str(node["href"]).strip()).split("#")[0]
            if _registered_domain(target) == own_domain and not AUTHOR_PATH.search(urllib.parse.urlsplit(target).path.casefold()):
                links.insert(0, (node, target))
        if headings or links:
            title = _clean(headings[0].get_text(" ", strip=True)) if headings else _clean(links[0][0].get_text(" ", strip=True))
            if not _good_title(title):
                return None
            linked = next((target for anchor, target in links if fold(title) in fold(anchor.get_text(" ", strip=True)) or anchor.find_parent(["h1", "h2", "h3", "h4", "h5"]) is not None and fold(anchor.get_text(" ", strip=True)) == fold(title)), None)
            url = linked or next((target for _, target in links if is_news_page(target)), None) or (links[0][1] if links else page.url)
            if require_news_link and not (links and is_news_page(url)):
                return None  # homepage: only items that link to the site's own news pages
            summary = None
            for paragraph in node.select("p"):
                candidate = _clean(paragraph.get_text(" ", strip=True))
                if len(candidate) >= 40 and fold(title) not in fold(candidate) and not date_matches(candidate):
                    summary = candidate[:240].rsplit(" ", 1)[0] if len(candidate) > 240 else candidate
                    break
            return {"title": title, "url": url, "summary": summary}
        node = node.parent
    return None


PAGINATION = re.compile(r"(?:^|/)(?:side|page|sida|p)/\d+/?$|[?&](?:page|side|p)=\d+", re.I)


def article_links(page: CapturedPage, limit: int) -> list[str]:
    """Article pages linked from a news listing that states no dates: internal links outside the site chrome,
    titled by a heading or a real title, under a news path or below the listing. Document order, at most `limit`.
    Used only to fetch pages of the same verified site; nothing is published from this list itself."""
    soup = page.soup()
    _drop(soup, chrome=True)
    own_domain = _registered_domain(page.url)
    listing = urllib.parse.urlsplit(page.url).path.rstrip("/")
    found: list[str] = []
    for anchor, target in _internal_links(soup.body or soup, page.url, own_domain):
        path = urllib.parse.urlsplit(target).path.rstrip("/")
        if PAGINATION.search(target) or path == listing:
            continue
        if not (is_news_page(target) and path.count("/") >= 2 or listing and path.startswith(listing + "/")):
            continue
        heading = anchor.find(["h1", "h2", "h3", "h4", "h5"])
        if not (heading and _good_title(heading.get_text(" ", strip=True)) or _good_title(anchor.get_text(" ", strip=True))):
            continue
        if target not in found:
            found.append(target)
        if len(found) >= limit:
            break
    return found


# ---------- job postings on the careers page ----------

def _is_ats(url: str) -> bool:
    return _registered_domain(url) in ATS_DOMAINS or "finn.no/job" in url


def _segments(node: Any) -> list[str]:
    return [segment.strip() for segment in node.get_text(" | ", strip=True).split(" | ") if segment.strip()]


def _labelled_date(segments: list[str], cues: tuple[str, ...], *, allow_future: bool = False) -> tuple[str | None, str | None]:
    for index, segment in enumerate(segments):
        if any(cue in fold(segment) for cue in cues):
            for candidate in (segment, segments[index + 1] if index + 1 < len(segments) else ""):
                found = date_matches(candidate, allow_future=allow_future)
                if found:
                    return found[0][0], found[0][1]
    return None, None


def _location(segments: list[str]) -> str | None:
    for index, segment in enumerate(segments):
        match = LOCATION_LABEL.match(segment)
        if match:
            value = match.group(1).strip(" :-") or (segments[index + 1] if index + 1 < len(segments) else "")
            value = _clean(value)
            if 2 <= len(value) <= 60 and not date_matches(value):
                return value
    return None


def job_listings(page: CapturedPage) -> tuple[list[dict[str, Any]], str | None]:
    """(open positions listed on a careers page, reason when none). A posting is a link to a job page (a deeper
    page under the careers path, a job-shaped URL, or an applicant-tracking host) whose text is a job title."""
    soup = page.soup()
    _drop(soup, chrome=True)
    body = soup.body or soup
    text = _clean(body.get_text(" "))
    if NO_OPENINGS.search(text):
        return [], "careers page states that no positions are open"
    own_domain = _registered_domain(page.url)
    careers_path = urllib.parse.urlsplit(page.url).path.rstrip("/")
    candidates: list[tuple[Any, str, bool]] = []
    for anchor in body.select("a[href]"):
        target = urllib.parse.urljoin(page.url, str(anchor.get("href") or "").strip()).split("#")[0]
        if not target.startswith(("http://", "https://")):
            continue
        ats = _is_ats(target)
        if not ats:
            if _registered_domain(target) != own_domain:
                continue
            path = urllib.parse.urlsplit(target).path.rstrip("/")
            deeper = bool(careers_path) and path.startswith(careers_path + "/") and len(path) - len(careers_path) > 3
            if path == careers_path or not (deeper or STRONG_JOB_PATH.search(path.casefold())):
                continue
        candidates.append((anchor, target, ats))
    jobs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for anchor, target, ats in candidates:
        card = _job_card(anchor, target, candidates)
        title = _clean(anchor.get_text(" ", strip=True))
        if _generic(title) or not title:
            heading = card.find(["h2", "h3", "h4", "h5"]) if card is not anchor else None
            title = _clean(heading.get_text(" ", strip=True)) if heading else ""
        if not title or _generic(title) or GENERIC_JOB_TITLE.search(fold(title)) or len(title) > 120 or len(words(title)) > 14 or date_matches(title) or not re.search(r"[^\W\d_]{3,}", title):
            continue
        card_text = _clean(card.get_text(" "))
        strong = ats or bool(STRONG_JOB_PATH.search(urllib.parse.urlsplit(target).path.casefold()))
        cue = bool(JOB_CUES.search(card_text))
        if set(words(title)) & NOT_A_POSTING_WORDS and not cue:
            continue
        if not (strong or cue):
            continue
        key = (fold(title), target)
        if key in seen:
            continue
        seen.add(key)
        segments = _segments(card) if card is not anchor else []
        deadline, deadline_text = _labelled_date(segments, ("søknadsfrist", "frist", "deadline", "apply by"), allow_future=True)
        posted, posted_text = _labelled_date(segments, ("publisert", "published", "posted", "lagt ut"))
        job = {"title": title, "url": target, "date_posted": posted, "date_posted_text": posted_text, "application_deadline": deadline,
               "application_deadline_text": deadline_text, "location": _location(segments), "method": "careers_page_listing"}
        jobs.append({key: value for key, value in job.items() if value is not None})
        if len(jobs) >= MAX_JOBS_PER_PAGE:
            break
    return jobs, None if jobs else "careers page lists no linked position"


def _job_card(anchor: Any, target: str, candidates: list[tuple[Any, str, bool]]) -> Any:
    """The largest element around one posting link (at most six levels up) that holds no other posting."""
    card = anchor
    for _ in range(6):
        parent = card.parent
        if parent is None or parent.name in ("body", "html", "[document]", "main"):
            break
        inside = {other_target for other, other_target, _ in candidates if other is parent or any(node is parent for node in other.parents)}
        if inside - {target}:
            break
        card = parent
    return card


# ---------- validation and assembly ----------

@dataclass
class SiteFacts:
    profiles: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_profiles: list[dict[str, Any]] = field(default_factory=list)
    activities: list[dict[str, Any]] = field(default_factory=list)
    jobs: list[dict[str, Any]] = field(default_factory=list)
    rejections: dict[str, int] = field(default_factory=dict)
    rejected_examples: list[dict[str, Any]] = field(default_factory=list)
    careers_checked: list[dict[str, Any]] = field(default_factory=list)

    def reject(self, kind: str, reason: str, item: dict[str, Any], page: CapturedPage | None) -> None:
        key = f"{kind}:{reason}"
        self.rejections[key] = self.rejections.get(key, 0) + 1
        if len(self.rejected_examples) < 20:
            shown = {name: value for name, value in item.items() if name in ("title", "url", "date", "date_text", "platform")}
            self.rejected_examples.append({"kind": kind, "reason": reason, "source_url": page.url if page else None, **shown})


def _provenance(page: CapturedPage) -> dict[str, Any]:
    return {"page_url": page.url, "content_sha256": page.content_sha256, "retrieved_at": page.retrieved_at}


def validate_activity(item: dict[str, Any], page: CapturedPage) -> str | None:
    """None when the item is contained in the captured page, else the rejection reason."""
    title = _clean(item.get("title") or "")
    if not title:
        return "no_title"
    if _generic(title):
        return "generic_title"
    if not page.contains(title):
        return "title_not_in_page"
    if not item.get("date") or not item.get("date_text"):
        return "no_explicit_date"
    if item.get("date_kind") == "updated":
        return "updated_timestamp_not_publication_date"
    if item["method"] == "listing_visible_date":
        if not span_in_text(item["date_text"], page.text) or str(item["date"])[:10] not in {match[0] for match in date_matches(item["date_text"])}:
            return "date_not_stated_in_page"
    elif not (str(item["date_text"]) in page.html or str(item["date_text"]) in page.unescaped or page.contains(item["date_text"])):
        return "date_not_stated_in_page"
    return None


def validate_job(job: dict[str, Any], page: CapturedPage) -> str | None:
    if not page.contains(job.get("title")):
        return "title_not_in_page"
    for key in ("date_posted_text", "application_deadline_text", "location"):
        if job.get(key) and not page.contains(job[key]):
            return f"{key}_not_in_page"
    return None


def extract_site_facts(profile: dict[str, Any], pages: list[CapturedPage], feeds: list[CapturedPage] | None = None) -> SiteFacts:
    """Facts from pages of a VERIFIED company site. `pages[0]` is the homepage; `profile` carries the legal name."""
    out = SiteFacts()
    if not pages:
        return out
    site_domain = _registered_domain(pages[0].url)
    legal_core = _tokens(profile.get("name"))
    shared_site = is_shared_site_section(pages[0].url)

    # Social profiles: one claim per (platform, canonical profile), the plainest link as the value.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for index, page in enumerate(pages):
        if page.kind != "html":
            continue
        for occurrence in social_occurrences(page, index, site_domain, legal_core):
            groups.setdefault((occurrence["platform"], _profile_key(occurrence)), []).append(occurrence)
    accepted: list[dict[str, Any]] = []
    for (platform, canonical), group in sorted(groups.items()):
        chosen = _representative(group)
        page = chosen["page"]
        if not (url_in_source(chosen["url"], page.html) or url_in_source(chosen["linked_as"], page.html)):
            out.reject("social", "url_not_in_page", chosen, page)
            continue
        score, reason = None, "no corroboration"
        for occurrence in sorted(group, key=lambda item: item["via"] != "jsonld_sameas"):
            score, reason = social_identity(profile, occurrence, site_domain, shared_site=shared_site)
            if score is not None:
                break
        record = {
            "platform": platform, "url": chosen["url"], "canonical_url": canonical, "evidence_span": chosen["linked_as"],
            "link_text": chosen["link_text"], "via": chosen["via"], "found_on": page.url, "content_sha256": page.content_sha256,
            "retrieved_at": page.retrieved_at, "identity_score": score, "identity_reason": reason,
            "via_jsonld_sameas": any(item["via"] == "jsonld_sameas" for item in group), "linked_on_pages": len({item["page"].url for item in group}),
        }
        if score is None:
            record["identity_score"] = 0.3
            out.ambiguous_profiles.append(record)
            out.reject("social", "handle_not_corroborated", record, page)
        else:
            accepted.append(record)
    # Cross-links: a site that links several profiles on one platform (club teams, group companies, partners)
    # keeps only the exact handles there (handle == legal name or verified domain name); the rest stay
    # ambiguous. With no exact handle, only those scored >= 0.98 survive.
    labels = {_compact("".join(legal_core)), _compact(site_domain.split(".", 1)[0]) if site_domain else ""} - {""}
    for platform in SOCIAL_PLATFORMS:
        same = [item for item in accepted if item["platform"] == platform]
        if len(same) > 2:
            exact = [item for item in same if _handle(item) in labels]
            for item in same:
                if (item not in exact if exact else float(item["identity_score"]) < 0.98) and not item["via_jsonld_sameas"]:
                    accepted.remove(item)
                    out.ambiguous_profiles.append({**item, "identity_reason": "several profiles on one platform; only exact legal-name handles are kept"})
                    out.reject("social", "several_profiles_on_platform", item, None)
    out.profiles = accepted

    # Dated activity: structured dates on every page, visible listing dates on news pages and homepage news links.
    candidates: list[tuple[dict[str, Any], CapturedPage]] = []
    for feed in feeds or []:
        candidates.extend((item, feed) for item in feed_items(feed.raw))
    for index, page in enumerate(pages):
        if page.kind != "html":
            continue
        items = html_items(page.html, page.url)
        if index == 0:
            # A homepage's own published_time / WebPage date describes the page, not a news item.
            home = page.url.split("#")[0].rstrip("/")
            items = [item for item in items if item.get("method") == "article_time_datetime" or str(item.get("url") or "").split("#")[0].rstrip("/") != home]
        if index > 0:
            # Page-level dates (JSON-LD, article:published_time) count only on news pages: CMSs stamp every page
            # (contact, careers, "about") with them, which does not make those pages news.
            for item in items:
                if item.get("method") in ("jsonld_datePublished", "meta_article_published_time") and not (is_news_page(page.url) or is_news_page(str(item.get("url") or ""))):
                    out.reject("activity", "page_date_on_non_news_page", item, page)
            items = [item for item in items if item.get("method") not in ("jsonld_datePublished", "meta_article_published_time") or is_news_page(page.url) or is_news_page(str(item.get("url") or ""))]
        candidates.extend((item, page) for item in items)
        own_article = is_article_path(page.url) and any(item.get("method") in ("jsonld_datePublished", "meta_article_published_time") for item in items)
        if (is_news_page(page.url) or index == 0) and not own_article:
            # Listing pages only: an article page's own dates (lists of milestones, related links) are not items.
            candidates.extend((item, page) for item in listing_items(page, require_news_link=not is_news_page(page.url)))
    priority = {"jsonld_datePublished": 0, "meta_article_published_time": 1, "article_time_datetime": 2, "site_feed": 3, "listing_visible_date": 4}
    kept: dict[tuple[str, str], dict[str, Any]] = {}
    kept_urls: set[tuple[str, str]] = set()
    for item, page in sorted(candidates, key=lambda pair: priority.get(pair[0].get("method"), 9)):
        reason = validate_activity(item, page)
        if reason:
            out.reject("activity", reason, item, page)
            continue
        key = (str(item["date"])[:10], fold(item["title"]))
        # One article is one claim: the same article URL and date under another title form (JSON-LD headline vs
        # the page <title> with a site-name suffix) is the same item. A listing page's own URL is not a key.
        url = str(item.get("url") or "").split("#")[0].rstrip("/")
        is_listing_self = item.get("method") == "listing_visible_date" and url == page.url.split("#")[0].rstrip("/")
        url_key = (url, str(item["date"])[:10]) if url and not is_listing_self else None
        if key in kept or (url_key and url_key in kept_urls):
            continue
        if url_key:
            kept_urls.add(url_key)
        summary = item.get("summary")
        if summary and not page.contains(summary) and not content_words(summary) <= set(words(page.text)):
            summary = None
        kept[key] = {**{name: value for name, value in item.items() if name != "summary"}, "summary": summary, **_provenance(page)}
    out.activities = list(kept.values())

    # Jobs: schema.org JobPosting anywhere, listed positions on careers pages.
    seen_jobs: set[tuple[str, str]] = set()
    for page in pages:
        if page.kind != "html":
            continue
        found = [(job, page) for job in job_postings(page.html, page.url)]
        if is_careers_page(page):
            listed, why = job_listings(page)
            out.careers_checked.append({"url": page.url, "positions": len(listed), "reason": why})
            found.extend((job, page) for job in listed)
        for job, source in found:
            reason = validate_job(job, source)
            if reason:
                out.reject("job", reason, job, source)
                continue
            key = (fold(job["title"]), str(job.get("url") or source.url))
            if key in seen_jobs:
                continue
            seen_jobs.add(key)
            out.jobs.append({**job, **_provenance(source)})
    return out
