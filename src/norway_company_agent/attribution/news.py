"""Is a dated candidate a real article, and is it about this company (design §B6)?

A page's container — a feed, a news listing, an <article> wrapper — is not proof that an item is news. Each item must
(1) pass the rejections below (media files, product/service/project/contact paths, listing pages, default CMS posts,
bulk-entry bursts, project-only taxonomy, cards outside the listing's own section) and (2) show positive article
evidence: a news or dated URL path, the site's own main post feed, a news listing on the site, or an article-typed page.
On sites run by another company or shared by a group, an item must also name this company.
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime
from typing import Any, Callable

from .decision import Decision
from .names import LegalName, compact, fold

MEDIA_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".mp4", ".mp3")
NON_ARTICLE_SEGMENTS = {
    "prosjekt", "prosjekter", "referanse", "referanser", "referanseprosjekter", "portfolio", "portfolio-item", "portfolio-items", "portefolje",
    "produkt", "produkter", "product", "products", "shop", "butikk", "nettbutikk", "tjeneste", "tjenester", "service", "services", "hytter",
    "hyttemodeller", "modeller", "boliger", "til-salgs", "utleie", "booking", "kontakt", "kontakt-oss", "contact", "contact-us", "om-oss", "om",
    "about", "about-us", "personvern", "privacy", "personvernerklaering", "category", "categories", "kategori", "kategorier", "tag", "tags",
    "emne", "emner", "stikkord", "author", "forfatter", "ansatte", "team", "medarbeidere", "kurs", "arrangementer", "events", "event",
}
NEWS_SEGMENT = re.compile(r"^(?:nyheter|nyhet|aktuelt|news|blogg|blog|bloggen|artikler|artikkel|article|articles|presse|press|pressemeldinger|"
                          r"pressemelding|press-releases|post|posts|innlegg|magasin|magazine|nyhetsarkiv|aktueltsaker|aktuelle-saker|nyhetssaker|"
                          r"siste-nytt|nytt|newsroom)$")
DATED_PATH = re.compile(r"/(?:19|20)\d{2}/(?:0?[1-9]|1[0-2])(?:/|$)")
DEFAULT_POSTS = {"hello world", "hello world!", "hei verden", "hei verden!", "sample page", "eksempelside", "uncategorized", "testinnlegg", "test post",
                 "hallo verden", "hallo verden!"}
NEWS_TAXONOMY = {"nyheter", "nyhet", "aktuelt", "news", "blogg", "blog", "presse", "pressemelding", "pressemeldinger"}
PROJECT_TAXONOMY = {"prosjekt", "prosjekter", "referanse", "referanser", "referanseprosjekter", "portfolio", "naeringsbygg", "boligbygg", "bolig",
                    "boliger", "offentlig", "offentlige", "rehabilitering", "nybygg", "produkter", "produkt", "tjenester", "hytter", "industri",
                    "infrastruktur", "anlegg", "kontorbygg", "skolebygg"}
NO_CATEGORY = {"uncategorized", "ukategorisert", "ikkekategorisert", "generelt", "general"}  # a CMS default: says nothing
TITLE_YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
BURST_WINDOW_SECONDS = 15 * 60
BURST_SIZE = 4
SAME_DAY_BURST_SIZE = 5


def segments(url: str) -> list[str]:
    return [urllib.parse.unquote(part).casefold() for part in urllib.parse.urlsplit(url).path.split("/") if part]


def has_news_path(url: str) -> bool:
    return any(NEWS_SEGMENT.match(segment) for segment in segments(url)) or bool(DATED_PATH.search(urllib.parse.urlsplit(url).path))


def _same(a: str, b: str) -> bool:
    return a.split("#")[0].rstrip("/") == b.split("#")[0].rstrip("/")


def classify_item(item: dict[str, Any], page_url: str, *, site_url: str, on_news_page: bool, page_is_listing: bool, article_typed: bool,
                  from_main_feed: bool, outside_listing_section: bool) -> Decision:
    url = str(item.get("url") or page_url)
    path_segments = segments(url)
    method = item.get("method")
    if urllib.parse.urlsplit(url).path.casefold().endswith(MEDIA_EXTENSIONS):
        return Decision(False, "media_file", "The item links to a file (image or document), not an article.")
    bad = [segment for segment in path_segments if segment in NON_ARTICLE_SEGMENTS]
    if bad and not has_news_path(url):
        return Decision(False, "non_article_path", f"The item is a \"{bad[0]}\" page (product, service, project, contact or archive), not an article.")
    if _same(url, site_url):
        if method == "article_time_datetime" and _same(page_url, site_url) and item.get("date_kind") == "published":
            # Revision 1 (985032726): an <article> card on the homepage with its own heading and publication <time> but
            # no link of its own is a dated post shown on the homepage.
            return Decision(True, "homepage_article_card", "The item is a dated post shown on the company's homepage.")
        return Decision(False, "listing_not_item", "The item is the website's homepage, not an article.")
    if page_is_listing and _same(url, page_url) and method in ("jsonld_datePublished", "meta_article_published_time"):
        return Decision(False, "listing_not_item", "The date belongs to the news listing page itself, not to an article on it.")
    if fold(item.get("title")).strip(" .!") in {fold(title).strip(" .!") for title in DEFAULT_POSTS}:
        return Decision(False, "default_cms_post", "The item is the publishing tool's default sample post.")
    categories = [compact(category) for category in item.get("categories") or [] if compact(category) and compact(category) not in NO_CATEGORY]
    if categories and all(any(word in category for word in PROJECT_TAXONOMY) for category in categories) and not any(any(word in category for word in NEWS_TAXONOMY) for category in categories):
        return Decision(False, "project_category", "The site files the item only under project or product categories, not news.")
    published_year = str(item.get("date") or "")[:4]
    later = [year for year in TITLE_YEAR.findall(str(item.get("title") or "")) if published_year.isdigit() and int(year) > int(published_year) + 1]
    if later:
        return Decision(False, "date_contradicts_title", f"The title names {later[0]}, years after the stated date {published_year}; the post was reused, so its date is not its publication date.")
    if outside_listing_section:
        return Decision(False, "outside_news_section", "The news listing links this item to a page outside its own news section (an evergreen page).")
    if has_news_path(url):
        return Decision(True, "article_news_path", "The item's address is in the website's news section or is dated.")
    if method == "site_feed" and from_main_feed:
        return Decision(True, "article_main_feed", "The item is a post in the website's own main feed.")
    if on_news_page and method in ("listing_visible_date", "article_time_datetime") and not _same(url, page_url):
        return Decision(True, "article_on_news_listing", "The item is listed with its date on the website's news page.")
    if article_typed and _same(url, page_url):
        return Decision(True, "article_typed_page", "The item's own page declares itself an article.")
    return Decision(False, "no_article_evidence", "Nothing shows the item is an article: no news or dated address, no news feed, news listing or article markup.")


def _instant(item: dict[str, Any]) -> datetime | None:
    text = str(item.get("date") or "")
    if len(text) <= 10:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def burst_members(items: list[tuple[str, dict[str, Any]]]) -> set[int]:
    """Indexes of items in a bulk-entry burst: from one source, ≥4 timestamps within 15 minutes or ≥5 on one day when only
    dates are known. A burst's dates record when the pages were loaded into the CMS, not when anything was published."""
    by_source: dict[str, list[int]] = {}
    for index, (source, _) in enumerate(items):
        by_source.setdefault(source, []).append(index)
    members: set[int] = set()
    for indexes in by_source.values():
        timed = sorted((instant, index) for index in indexes if (instant := _instant(items[index][1])) is not None)
        start = 0
        for end in range(len(timed)):
            while (timed[end][0] - timed[start][0]).total_seconds() > BURST_WINDOW_SECONDS:
                start += 1
            if end - start + 1 >= BURST_SIZE:
                members.update(index for _, index in timed[start:end + 1])
        days: dict[str, list[int]] = {}
        for index in indexes:
            if _instant(items[index][1]) is None and items[index][1].get("date"):
                days.setdefault(str(items[index][1]["date"])[:10], []).append(index)
        for same_day in days.values():
            if len(same_day) >= SAME_DAY_BURST_SIZE:
                members.update(same_day)
    return members


def subject_of(item: dict[str, Any], legal: LegalName, *, names_entity: Callable[[], str | None], siblings: Callable[[list[str]], set[str]]) -> tuple[str, str]:
    """("THIS" | "SIBLING" | "UNSTATED", basis). THIS: the item names the company (organisation number, full legal name, or
    the site's own category equal to the company's name); SIBLING: the site's categories tag a sibling unit instead."""
    basis = names_entity()
    if basis:
        return "THIS", basis
    categories = [str(category) for category in item.get("categories") or []]
    for category in categories:
        if legal.tokens and compact(category) == legal.compact:
            return "THIS", f"tagged \"{category}\" in the website's own categories"
    sibling = siblings(categories)
    if sibling:
        return "SIBLING", f"tagged as another unit of the group ({', '.join(sorted(sibling))})"
    return "UNSTATED", "the item does not name the company; it is on the company's own website"
