"""Evidence-text checks shared by every extractor that publishes a value read from a captured page.

Pure functions, no I/O. A value is publishable only when it is contained in the captured source:

  * a span or title must occur verbatim (case/whitespace-folded) in the page it cites, and be short;
  * a value's words and digits must all occur in its evidence span;
  * a date is kept only when the source text states that exact calendar date; never inferred;
  * a URL must occur in the captured bytes (literally, HTML-escaped, JSON-escaped or percent-encoded).

Used by the deterministic site extractors (site_facts.py) and by the optional LLM validators (llm/tasks.py).
"""
from __future__ import annotations

import html
import re
import unicodedata
import urllib.parse
from datetime import date, datetime, timezone
from typing import Any

MAX_SPAN_CHARS = 300

MONTHS = {
    "januar": 1, "january": 1, "jan": 1, "februar": 2, "february": 2, "feb": 2, "mars": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "mai": 5, "may": 5, "juni": 6, "june": 6, "jun": 6, "juli": 7, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11, "desember": 12, "december": 12, "des": 12, "dec": 12,
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_PATTERNS = (
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), ("y", "m", "d")),
    (re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)"), ("d", "m", "y")),
    (re.compile(rf"(?<!\d)(\d{{1,2}})\.?\s+({_MONTH})\.?,?\s+(\d{{4}})(?!\d)", re.I), ("d", "M", "y")),
    (re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})(?!\d)", re.I), ("M", "d", "y")),
)


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
    joined = re.sub(r"(?<=\d)[\s  .,](?=\d{3}(?!\d))", "", str(text or ""))
    return re.findall(r"\d+", joined)


def span_in_text(span: Any, text: str) -> bool:
    folded = fold(span)
    return 3 <= len(folded) <= MAX_SPAN_CHARS and folded in fold(text)


def number_set(text: Any) -> set[str]:
    return {run.lstrip("0") or "0" for run in digit_runs(text)}


def supported_by(value: Any, span: str) -> bool:
    """Every content word and every number of `value` occurs in `span` (numbers compared whole, not as substrings)."""
    return content_words(value) <= set(words(span)) and number_set(value) <= number_set(span)


def date_matches(text: str, *, allow_future: bool = False) -> list[tuple[str, str, int, int]]:
    """(iso date, exact matched text, start, end) for every calendar date stated in `text`. No inference:
    an impossible date or a year before 1995 is dropped, and so is a date after today unless `allow_future`
    (an application deadline may lie ahead; a publication date may not)."""
    found = []
    today = date.max if allow_future else datetime.now(timezone.utc).date()
    for pattern, order in DATE_PATTERNS:
        for match in pattern.finditer(text or ""):
            parts = dict(zip(order, match.groups(), strict=True))
            try:
                month = MONTHS[parts["M"].casefold()] if "M" in parts else int(parts["m"])
                value = date(int(parts["y"]), month, int(parts["d"]))
            except (KeyError, ValueError):
                continue
            if 1995 <= value.year and value <= today:
                found.append((value.isoformat(), match.group(0), match.start(), match.end()))
    return sorted(found, key=lambda item: item[2])


def explicit_dates(text: str) -> set[str]:
    """Calendar dates stated in `text` (ISO, d.m.yyyy, '1. september 2026', 'September 1, 2026'). No inference."""
    return {item[0] for item in date_matches(text)}


def url_in_source(url: str, raw: str) -> bool:
    """True when `url` occurs in the captured source as written: literally, HTML-escaped (&amp;), JSON-escaped
    (\\/) or percent-encoded (an embedded plugin's href= parameter). Never true for a URL we rewrote."""
    if not url:
        return False
    variants = {
        url,
        html.escape(url, quote=False),
        html.escape(url, quote=True),
        url.replace("/", "\\/"),
        urllib.parse.quote(url, safe=""),
    }
    return any(variant and variant in raw for variant in variants)
