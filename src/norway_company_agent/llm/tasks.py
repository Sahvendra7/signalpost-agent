"""Prompts and deterministic validators for the optional LLM layer. Pure functions, no I/O.

The model only ever reads content the pipeline already captured from a website that the deterministic
identity gate verified. Everything it returns is re-checked here against that same captured text:

  * an evidence span must occur verbatim (case/whitespace-folded) in the page it cites, and be short;
  * a value's words and digits must all occur in its evidence span;
  * a date is kept only when the span states that exact date; otherwise it is dropped, never guessed;
  * a social profile must be an href on the cited verified page, on LinkedIn/Facebook/Instagram/YouTube;
  * conflicting values are rejected together, and a website CEO that disagrees with the registry is rejected;
  * a page the model does not classify FIRST_PARTY yields no LLM facts. This can only remove LLM output;
    the deterministic identity gate stays the sole authority on which website belongs to the company.

Anything that fails a check is rejected with a reason code and counted, never repaired by guessing.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from ..website import normalize_social_url

PAGE_CLASSES = ("FIRST_PARTY", "THIRD_PARTY", "FAN_COMMUNITY", "DIRECTORY", "AMBIGUOUS")
FACT_TYPES = (
    "business_description", "product_or_service", "person_role", "office_location",
    "contact_email", "contact_phone", "founded_year", "employee_count_statement", "certification",
)
ROLE_CATEGORIES = ("ceo", "chair", "board_member", "cfo", "cto", "coo", "founder", "owner", "manager", "other")
PROFILE_PLATFORMS = ("linkedin", "facebook", "instagram", "youtube")
SECTION_HEADINGS = ("overview", "business", "leadership", "locations", "financials", "web_presence", "recent_activity")
MAX_SPAN_CHARS = 300
MAX_ITEMS = 40
MAX_PAGE_CHARS = 6_000
MIN_CONFIDENCE = 0.5
LLM_CONFIDENCE_CAP = 0.8

# Deterministic role vocabulary. When a title is listed here, the table decides the category, not the model.
ROLE_SYNONYMS: dict[str, str] = {
    "ceo": "ceo", "chief executive officer": "ceo", "daglig leder": "ceo", "administrerende direktør": "ceo",
    "adm. dir.": "ceo", "adm dir": "ceo", "adm. direktør": "ceo", "managing director": "ceo", "konsernsjef": "ceo",
    "styreleder": "chair", "styrets leder": "chair", "chairman": "chair", "chair": "chair", "chairman of the board": "chair",
    "styremedlem": "board_member", "board member": "board_member",
    "cfo": "cfo", "chief financial officer": "cfo", "økonomisjef": "cfo", "finansdirektør": "cfo",
    "cto": "cto", "chief technology officer": "cto", "teknisk direktør": "cto",
    "coo": "coo", "chief operating officer": "coo", "driftsdirektør": "coo",
    "gründer": "founder", "grunnlegger": "founder", "founder": "founder", "co-founder": "founder", "medgründer": "founder",
    "eier": "owner", "owner": "owner", "innehaver": "owner",
}
_ROLE_LOOKUP = {" ".join(re.findall(r"[^\W_]+", title)): category for title, category in ROLE_SYNONYMS.items()}
# Registry role codes (claims.ROLE_FIELDS) that name the same office as a website role category.
REGISTRY_ROLE_FOR_CATEGORY = {"ceo": ("DAGL",), "chair": ("LEDE",)}

MONTHS = {
    "januar": 1, "january": 1, "jan": 1, "februar": 2, "february": 2, "feb": 2, "mars": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "mai": 5, "may": 5, "juni": 6, "june": 6, "jun": 6, "juli": 7, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11, "desember": 12, "december": 12, "des": 12, "dec": 12,
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_DATE_PATTERNS = (
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), ("y", "m", "d")),
    (re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)"), ("d", "m", "y")),
    (re.compile(rf"(?<!\d)(\d{{1,2}})\.?\s+({_MONTH})\.?,?\s+(\d{{4}})(?!\d)", re.I), ("d", "M", "y")),
    (re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})(?!\d)", re.I), ("M", "d", "y")),
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_ROLE_CUES = re.compile(r"daglig leder|adm\.? ?dir|administrerende|\bceo\b|chief executive|styreleder|chairman|gründer|grunnlegger|founder|\bcfo\b|\bcto\b|økonomisjef|innehaver", re.I)
_SOCIAL_CUES = {"linkedin": "linkedin.com", "facebook": "facebook.com", "instagram": "instagram.com", "youtube": "youtube.com"}


# ---------- text helpers ----------

def fold(text: Any) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = re.sub(r"[‐-―−]", "-", value)
    value = re.sub(r"[‘’‚‛′]", "'", value)
    value = re.sub(r"[“”„‟″]", '"', value)
    return re.sub(r"\s+", " ", value).strip()


def words(text: Any) -> list[str]:
    return re.findall(r"[^\W_]+", fold(text))


def content_words(text: Any) -> set[str]:
    return {word for word in words(text) if len(word) >= 3 or word.isdigit()}


def digit_runs(text: Any) -> list[str]:
    joined = re.sub(r"(?<=\d)[\s  .,](?=\d{3}(?!\d))", "", str(text or ""))
    return re.findall(r"\d+", joined)


def span_in_text(span: Any, text: str) -> bool:
    folded = fold(span)
    return 3 <= len(folded) <= MAX_SPAN_CHARS and folded in fold(text)


def number_set(text: Any) -> set[str]:
    return {run.lstrip("0") or "0" for run in digit_runs(text)}


def supported_by(value: Any, span: str) -> bool:
    """Every content word and every number of `value` occurs in `span` (numbers compared whole, not as substrings)."""
    return content_words(value) <= set(words(span)) and number_set(value) <= number_set(span)


def explicit_dates(text: str) -> set[str]:
    """Calendar dates stated in `text` (ISO, d.m.yyyy, '1. september 2026', 'September 1, 2026'). No inference."""
    found = set()
    for pattern, order in _DATE_PATTERNS:
        for match in pattern.finditer(text or ""):
            parts = dict(zip(order, match.groups(), strict=True))
            try:
                month = MONTHS[parts["M"].casefold()] if "M" in parts else int(parts["m"])
                value = date(int(parts["y"]), month, int(parts["d"]))
            except (KeyError, ValueError):
                continue
            if 1995 <= value.year and value <= datetime.now(timezone.utc).date():
                found.add(value.isoformat())
    return found


def _as_iso_date(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else None


def normalize_role(title: Any, proposed: Any) -> tuple[str | None, str]:
    """(category, method). The deterministic table wins; the model's category is used only for unlisted titles."""
    key = " ".join(words(title))
    if key in _ROLE_LOOKUP:
        return _ROLE_LOOKUP[key], "deterministic_table"
    category = str(proposed or "").strip().casefold()
    return (category, "llm") if category in ROLE_CATEGORIES else (None, "invalid_category")


# ---------- captured pages ----------

@dataclass
class PageContent:
    source_url: str
    retrieved_at: str
    content_sha256: str
    text: str
    links: list[str] = field(default_factory=list)
    html: str = ""


def prepare_page(source_url: str, raw: bytes, *, retrieved_at: str, content_sha256: str, max_chars: int = MAX_PAGE_CHARS) -> PageContent:
    """Visible text and outbound hrefs of one captured page. Tolerates malformed HTML."""
    html = raw.decode("utf-8", errors="replace")
    try:
        soup = BeautifulSoup(html, "lxml")
        for node in soup(["script", "style", "noscript", "template", "svg"]):
            node.decompose()
        text = soup.get_text(" ", strip=True)
        links = []
        for anchor in soup.select("a[href]"):
            href = urllib.parse.urljoin(source_url, str(anchor.get("href") or "").strip())
            if href.startswith(("http://", "https://")):
                links.append(href)
    except Exception:  # malformed beyond what lxml recovers: fall back to tag stripping
        text, links = re.sub(r"<[^>]+>", " ", html), []
    text = re.sub(r"\s+", " ", text).strip()[:max_chars]
    return PageContent(source_url, retrieved_at, content_sha256, text, list(dict.fromkeys(links))[:150], html)


# ---------- when to call (budget policy) ----------

def extraction_triggers(site: dict[str, Any], pages: list[PageContent], *, has_description: bool) -> list[str]:
    """Why an extraction call could add something the deterministic parsers did not. Empty -> no call."""
    if site.get("status") != "verified" or not pages:
        return []
    text = " ".join(page.text for page in pages)
    html = " ".join(page.html for page in pages).casefold()
    reasons = []
    if not has_description and len(text) >= 300:
        reasons.append("no_deterministic_description")
    if _ROLE_CUES.search(text):
        reasons.append("role_cues_in_text")
    if not site.get("activities") and explicit_dates(text):
        reasons.append("dates_in_text_without_deterministic_activity")
    found = {item.get("platform") for item in (site.get("profiles") or []) + (site.get("ambiguous_profiles") or [])}
    if any(host in html and platform not in found for platform, host in _SOCIAL_CUES.items()):
        reasons.append("social_host_in_html_without_deterministic_profile")
    return reasons


# ---------- extraction prompt ----------

EXTRACTION_SYSTEM = """You extract facts about one company from web pages that were already captured from that company's verified website.
Rules:
- Use ONLY the supplied page text and links. Never use outside knowledge. Never guess.
- Every item must quote a short evidence_span (max 300 characters) copied verbatim from the page it cites.
- Every word and number of a value must appear in its evidence_span.
- Dates: give a date only when that exact calendar date is written in the evidence_span; otherwise null. Never infer a date.
- Profiles: only LinkedIn, Facebook, Instagram or YouTube URLs that appear in the page's links list.
- Do not merge different people. If the page contradicts itself, report both statements.
- Omit anything you are unsure of. Empty lists are fine.
Return one JSON object only, no prose, with exactly these keys:
{"page_classifications":[{"source_url":str,"classification":"FIRST_PARTY|THIRD_PARTY|FAN_COMMUNITY|DIRECTORY|AMBIGUOUS","evidence_spans":[str]}],
 "facts":[{"fact_type":str,"value":str or {"person_name":str,"role_title":str,"role_category":str},"evidence_span":str,"source_url":str,"date_if_explicit":"YYYY-MM-DD" or null,"confidence":0..1}],
 "profiles":[{"profile_url":str,"platform":"linkedin|facebook|instagram|youtube","source_page":str,"evidence_span":str}],
 "activities":[{"title":str,"publication_date":"YYYY-MM-DD" or null,"summary":str or null,"source_url":str,"evidence_span":str}]}
fact_type is one of: """ + ", ".join(FACT_TYPES) + """.
role_category is one of: """ + ", ".join(ROLE_CATEGORIES) + """ (e.g. "Daglig leder", "CEO" and "Chief Executive Officer" are all ceo).
classification: FIRST_PARTY = the company's own page; THIRD_PARTY = another business's page; FAN_COMMUNITY = fan, supporter, wiki or forum page; DIRECTORY = listing of many companies; AMBIGUOUS = cannot tell."""


def extraction_prompt(company: dict[str, Any], pages: list[PageContent], max_input_chars: int) -> str:
    budget = max(1_000, max_input_chars)
    supplied = []
    for page in pages:
        if budget <= 0:
            break
        text = page.text[:budget]
        budget -= len(text)
        supplied.append({"source_url": page.source_url, "text": text, "links": page.links[:60]})
    return json.dumps({"company": {"legal_name": company.get("name"), "organisation_number": company.get("organisation_number")}, "pages": supplied}, ensure_ascii=False)


# ---------- extraction validation ----------

@dataclass
class ExtractionResult:
    classifications: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    profiles: list[dict[str, Any]] = field(default_factory=list)
    activities: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    duplicates: int = 0
    dates_dropped: int = 0
    normalizations: dict[str, int] = field(default_factory=dict)

    def reject(self, kind: str, reason: str, item: Any) -> None:
        self.rejected.append({"kind": kind, "reason": reason, "item": json.dumps(item, ensure_ascii=False, default=str)[:300]})


def _provenance(page: PageContent, span: str) -> dict[str, Any]:
    return {"source_url": page.source_url, "retrieved_at": page.retrieved_at, "content_sha256": page.content_sha256, "evidence_span": re.sub(r"\s+", " ", span).strip()}


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    return value[:MAX_ITEMS] if isinstance(value, list) else []


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def _validate_fact(item: dict[str, Any], page: PageContent, out: ExtractionResult) -> dict[str, Any] | None:
    fact_type = str(item.get("fact_type") or "")
    span = item.get("evidence_span")
    value = item.get("value")
    if fact_type not in FACT_TYPES:
        return out.reject("fact", "unknown_fact_type", item)
    if not isinstance(span, str) or not span_in_text(span, page.text):
        return out.reject("fact", "evidence_span_not_in_page", item)
    confidence = _confidence(item.get("confidence", 0.6))
    if confidence is None or confidence < MIN_CONFIDENCE:
        return out.reject("fact", "low_or_invalid_confidence", item)
    extra: dict[str, Any] = {}
    if fact_type == "person_role":
        if not isinstance(value, dict):
            return out.reject("fact", "person_role_value_not_object", item)
        name, title = str(value.get("person_name") or "").strip(), str(value.get("role_title") or "").strip()
        if len(words(name)) < 2 or not title:
            return out.reject("fact", "person_role_incomplete", item)
        if not supported_by(name, span) or not supported_by(title, span):
            return out.reject("fact", "value_not_in_evidence_span", item)
        category, method = normalize_role(title, value.get("role_category"))
        if category is None:
            return out.reject("fact", "invalid_role_category", item)
        out.normalizations[method] = out.normalizations.get(method, 0) + 1
        value = {"person_name": name, "role_title": title, "role_category": category}
        extra["role_normalization"] = method
    else:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool) or not str(value).strip():
            return out.reject("fact", "value_not_scalar", item)
        value = re.sub(r"\s+", " ", str(value)).strip()[:400]
        if not supported_by(value, span):
            return out.reject("fact", "value_not_in_evidence_span", item)
        if fact_type == "contact_email" and not (_EMAIL.fullmatch(value) and fold(value) in fold(span)):
            return out.reject("fact", "email_not_verbatim", item)
        if fact_type == "contact_phone" and len("".join(digit_runs(value))) < 8:
            return out.reject("fact", "phone_too_short", item)
        if fact_type == "founded_year":
            if not re.fullmatch(r"\d{4}", value) or not 1800 <= int(value) <= datetime.now(timezone.utc).year:
                return out.reject("fact", "founded_year_invalid", item)
    stated = _as_iso_date(item.get("date_if_explicit"))
    if item.get("date_if_explicit") and stated not in explicit_dates(span):
        out.dates_dropped += 1
        stated = None
    return {"fact_type": fact_type, "value": value, **_provenance(page, span), "date_if_explicit": stated, "confidence": round(min(confidence, LLM_CONFIDENCE_CAP), 3), **extra}


def _validate_profile(item: dict[str, Any], page: PageContent, out: ExtractionResult, known: set[str]) -> dict[str, Any] | None:
    platform = str(item.get("platform") or "").casefold()
    if platform not in PROFILE_PLATFORMS:
        return out.reject("profile", "platform_not_allowed", item)
    normalized = normalize_social_url(str(item.get("profile_url") or ""))
    if not normalized or normalized["platform"] != platform:
        return out.reject("profile", "not_a_profile_url", item)
    linked = {entry["url"] for entry in (normalize_social_url(href) for href in page.links) if entry}
    if normalized["url"] not in linked:
        return out.reject("profile", "not_linked_from_verified_page", item)
    span = item.get("evidence_span")
    if not isinstance(span, str) or not (span_in_text(span, page.text) or fold(span) in {fold(href) for href in page.links}):
        return out.reject("profile", "evidence_span_not_in_page", item)
    if normalized["url"] in known:
        out.duplicates += 1
        return None
    known.add(normalized["url"])
    return {"profile_url": normalized["url"], "platform": platform, "source_page": page.source_url, **_provenance(page, span), "first_party_linked": True}


def _validate_activity(item: dict[str, Any], page: PageContent, out: ExtractionResult, known: list[dict[str, Any]]) -> dict[str, Any] | None:
    span = item.get("evidence_span")
    title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()[:200]
    if not isinstance(span, str) or not span_in_text(span, page.text):
        return out.reject("activity", "evidence_span_not_in_page", item)
    if len(content_words(title)) < 2 or not content_words(title) <= set(words(page.text)):
        return out.reject("activity", "title_not_on_page", item)
    stated = _as_iso_date(item.get("publication_date"))
    if not stated or stated not in explicit_dates(span):
        if item.get("publication_date"):
            out.dates_dropped += 1
        return out.reject("activity", "no_explicit_date_in_span", item)
    summary = re.sub(r"\s+", " ", str(item.get("summary") or "")).strip()[:240] or None
    if summary and not content_words(summary) <= set(words(page.text)):
        summary = None  # a summary is optional; an unsupported one is dropped, the dated item stays
    for existing in known:
        if (existing.get("date") or "")[:10] == stated and (fold(title) in fold(existing.get("title")) or fold(existing.get("title")) in fold(title)):
            out.duplicates += 1
            return None
    known.append({"date": stated, "title": title})
    return {"title": title, "publication_date": stated, "summary": summary, **_provenance(page, span)}


def _registry_holders(profile: dict[str, Any], category: str) -> list[str]:
    codes = REGISTRY_ROLE_FOR_CATEGORY.get(category, ())
    roles = (((profile.get("evidence") or {}).get("roles") or {}).get("value") or {}).get("roles") or []
    return [str(role.get("name")) for role in roles if role.get("role_code") in codes and not role.get("inactive") and role.get("name")]


def _resolve_conflicts(profile: dict[str, Any], facts: list[dict[str, Any]], out: ExtractionResult) -> list[dict[str, Any]]:
    # De-duplicate equal statements (keeping every span); never merge different people or values.
    merged: dict[tuple, dict[str, Any]] = {}
    for fact in facts:
        value = fact["value"]
        key = (fact["fact_type"], fold(value["person_name"]), value["role_category"]) if isinstance(value, dict) else (fact["fact_type"], fold(value))
        if key in merged:
            merged[key].setdefault("corroborating_spans", []).append({"source_url": fact["source_url"], "evidence_span": fact["evidence_span"]})
            out.duplicates += 1
        else:
            merged[key] = fact
    kept = list(merged.values())
    # Single-valued facts that disagree are all rejected: the page is uncertain, so are we.
    for fact_type, category in (("founded_year", None), ("person_role", "ceo"), ("person_role", "chair")):
        group = [fact for fact in kept if fact["fact_type"] == fact_type and (category is None or fact["value"]["role_category"] == category)]
        distinct = {fold(fact["value"]["person_name"] if category else fact["value"]) for fact in group}
        if len(distinct) > 1:
            for fact in group:
                out.reject("fact", "conflicting_values_on_site", fact)
            kept = [fact for fact in kept if fact not in group]
    # A website CEO/chair that disagrees with the registry is not published (the registry is authoritative).
    for fact in list(kept):
        value = fact["value"]
        if fact["fact_type"] != "person_role" or value["role_category"] not in REGISTRY_ROLE_FOR_CATEGORY:
            continue
        holders = _registry_holders(profile, value["role_category"])
        if holders and not any(set(words(value["person_name"])) <= set(words(holder)) for holder in holders):
            out.reject("fact", "conflicts_with_registry_role", fact)
            kept.remove(fact)
    return kept


def validate_extraction(
    data: dict[str, Any],
    pages: list[PageContent],
    profile: dict[str, Any],
    *,
    known_profile_urls: set[str] | None = None,
    known_activities: list[dict[str, Any]] | None = None,
) -> ExtractionResult:
    out = ExtractionResult()
    by_url = {page.source_url: page for page in pages}
    first_party: set[str] = set()
    for item in _list(data, "page_classifications"):
        if not isinstance(item, dict) or item.get("source_url") not in by_url:
            out.reject("classification", "unknown_source_url", item)
            continue
        label = str(item.get("classification") or "")
        spans = [span for span in (item.get("evidence_spans") or []) if isinstance(span, str) and span_in_text(span, by_url[item["source_url"]].text)][:3]
        if label not in PAGE_CLASSES or not spans:
            out.reject("classification", "invalid_label_or_no_evidence", item)
            continue
        out.classifications.append({"source_url": item["source_url"], "classification": label, "evidence_spans": spans})
        if label == "FIRST_PARTY":
            first_party.add(item["source_url"])

    def page_for(item: dict[str, Any], key: str, kind: str) -> PageContent | None:
        url = item.get(key)
        if url not in by_url:
            out.reject(kind, "unknown_source_url", item)
            return None
        if url not in first_party:
            out.reject(kind, "page_not_classified_first_party", item)
            return None
        return by_url[url]

    facts = []
    for item in _list(data, "facts"):
        page = page_for(item, "source_url", "fact") if isinstance(item, dict) else out.reject("fact", "not_an_object", item)
        if page and (fact := _validate_fact(item, page, out)):
            facts.append(fact)
    out.facts = _resolve_conflicts(profile, facts, out)
    known_urls = set(known_profile_urls or ())
    for item in _list(data, "profiles"):
        page = page_for(item, "source_page", "profile") if isinstance(item, dict) else out.reject("profile", "not_an_object", item)
        if page and (record := _validate_profile(item, page, out, known_urls)):
            out.profiles.append(record)
    seen = [dict(item) for item in (known_activities or [])]
    for item in _list(data, "activities"):
        page = page_for(item, "source_url", "activity") if isinstance(item, dict) else out.reject("activity", "not_an_object", item)
        if page and (record := _validate_activity(item, page, out, seen)):
            out.activities.append(record)
    return out


# ---------- synthesis ----------

SYNTHESIS_SYSTEM = """You write a short company profile for a reader, using ONLY the verified facts supplied.
Rules:
- Do not invent anything. Do not infer facts that are not stated. Do not add any fact that is absent from the supplied facts.
- Preserve uncertainty: if facts are missing, partial or marked ambiguous, say so plainly instead of filling the gap.
- Omit any section for which no supplied fact exists. Never write a section without citing fact_ids.
- Every number, name, place, e-mail and URL you write must appear in the facts you cite.
- Plain, neutral English; at most 3 sentences per section.
Return one JSON object only, no prose:
{"sections":[{"heading":"overview|business|leadership|locations|financials|web_presence|recent_activity","text":str,"fact_ids":[str]}],"uncertainties":[{"text":str,"fact_ids":[str]}]}"""

CATEGORY_HEADING = {
    "identity": "overview", "relationships": "overview", "registry_activity": "overview", "description": "business",
    "leadership": "leadership", "locations": "locations", "filings": "financials", "websites": "web_presence",
    "public_activity": "recent_activity", "hiring": "recent_activity",
}
_ALLOWED_CAPITALISED = {
    "the", "it", "its", "this", "these", "there", "a", "an", "in", "on", "as", "at", "no", "not", "and", "but", "or",
    "ceo", "cfo", "cto", "coo", "asa", "ans", "da", "enk", "nuf", "sa", "norway", "norwegian", "nok", "eur", "usd",
    "linkedin", "facebook", "instagram", "youtube", "x", "tiktok", "brønnøysund", "brreg", "registry", "website",
    "board", "chair", "chairman", "founder", "owner", "auditor", "accountant", "revenue", "equity", "assets", "debt",
    "profit", "result", "operating", "net", "total", "annual", "accounts", "company", "subunit", "subunits",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "unknown", "registered", "according",
}


def synthesis_facts(claims: list[dict[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    """Verified, available claims as compact facts with short ids (f1..fN), most useful categories first."""
    order = ("identity", "description", "leadership", "locations", "filings", "websites", "public_activity", "hiring", "relationships", "registry_activity")
    available = [claim for claim in claims if claim.get("availability") == "available" and claim.get("category") in order]
    available.sort(key=lambda claim: order.index(claim["category"]))
    facts = []
    for claim in available:
        value = claim.get("value")
        if claim.get("field") == "group_structure":
            continue
        rendered = value if isinstance(value, (str, int, float, bool)) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if isinstance(rendered, str) and len(rendered) > 240:
            rendered = rendered[:240] + "…"
        fact = {"fact_id": f"f{len(facts) + 1}", "category": claim["category"], "field": claim["field"], "value": rendered, "claim_key": claim.get("key")}
        for key in ("period", "currency", "event_date", "derivation"):
            if claim.get(key):
                fact[key] = claim[key]
        facts.append(fact)
        if len(facts) >= limit:
            break
    return facts


def synthesis_prompt(company: dict[str, Any], facts: list[dict[str, Any]]) -> str:
    supplied = [{key: value for key, value in fact.items() if key != "claim_key"} for fact in facts]
    return json.dumps({"company": {"legal_name": company.get("name"), "organisation_number": company.get("organisation_number")}, "facts": supplied}, ensure_ascii=False)


def _grounded_text(text: str, cited: list[dict[str, Any]], company_name: Any) -> str | None:
    """None when `text` is grounded in the cited facts, else the reason it is not."""
    source = " ".join(json.dumps({key: value for key, value in fact.items() if key not in {"fact_id", "claim_key"}}, ensure_ascii=False, default=str) for fact in cited) + " " + str(company_name or "")
    if not number_set(text) <= number_set(source):
        return "number_not_in_cited_facts"
    for token in _EMAIL.findall(text) + re.findall(r"https?://\S+|www\.\S+", text):
        if fold(token).rstrip(".,;)") not in fold(source):
            return "contact_or_url_not_in_cited_facts"
    source_words = set(words(source))
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for token in re.findall(r"[^\W\d_][^\W_]*", sentence)[1:]:
            if token[0].isupper() and fold(token) not in source_words and fold(token) not in _ALLOWED_CAPITALISED:
                return "name_not_in_cited_facts"
    return None


@dataclass
class SynthesisResult:
    sections: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    expected_headings: list[str] = field(default_factory=list)

    @property
    def completeness(self) -> float | None:
        if not self.expected_headings:
            return None
        return round(len({section["heading"] for section in self.sections} & set(self.expected_headings)) / len(self.expected_headings), 3)


def validate_synthesis(data: dict[str, Any], facts: list[dict[str, Any]], company: dict[str, Any]) -> SynthesisResult:
    by_id = {fact["fact_id"]: fact for fact in facts}
    out = SynthesisResult(expected_headings=sorted({CATEGORY_HEADING[fact["category"]] for fact in facts}, key=SECTION_HEADINGS.index))

    def check(item: Any, kind: str) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            out.rejected.append({"kind": kind, "reason": "not_an_object"})
            return None
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        ids = [fact_id for fact_id in (item.get("fact_ids") or []) if isinstance(fact_id, str)]
        reason = None
        if not text or len(text) > 600:
            reason = "empty_or_too_long"
        elif (not ids and kind == "section") or any(fact_id not in by_id for fact_id in ids):
            reason = "missing_or_unknown_fact_ids"
        else:  # an uncertainty may cite nothing (it describes a gap); it is then checked against all facts
            reason = _grounded_text(text, [by_id[fact_id] for fact_id in ids] or facts, company.get("name"))
        if reason:
            out.rejected.append({"kind": kind, "reason": reason, "heading": item.get("heading"), "text": text[:200]})
            return None
        return {"text": text, "fact_ids": ids, "claim_keys": [by_id[fact_id]["claim_key"] for fact_id in ids]}

    seen = set()
    for item in _list(data, "sections"):
        heading = str((item or {}).get("heading") or "") if isinstance(item, dict) else ""
        if heading not in SECTION_HEADINGS or heading in seen:
            out.rejected.append({"kind": "section", "reason": "unknown_or_repeated_heading", "heading": heading})
            continue
        if (checked := check(item, "section")):
            seen.add(heading)
            out.sections.append({"heading": heading, **checked})
    for item in _list(data, "uncertainties")[:5]:
        if (checked := check(item, "uncertainty")):
            out.uncertainties.append(checked)
    out.sections.sort(key=lambda section: SECTION_HEADINGS.index(section["heading"]))
    return out
