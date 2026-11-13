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
from dataclasses import dataclass
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
PROJECT_TITLE = re.compile(r"^\s*(?:prosjekt|project|referanse|reference|case)\s*[:–—]", re.I)
PRESS_TITLE = re.compile(r"^\s*(?:pressemelding|press release|pressrelease|nyhet|news|kunngjøring|announcement)\s*[:–—-]", re.I)
PRESS_SLUG = re.compile(r"^(?:pressemelding|press-release|nyhet|kunngjoring)-")
DATED_PATH = re.compile(r"/(?:19|20)\d{2}/(?:0?[1-9]|1[0-2])(?:/|$)")
DEFAULT_POSTS = {"hello world", "hello world!", "hei verden", "hei verden!", "sample page", "eksempelside", "uncategorized", "testinnlegg", "test post",
                 "hallo verden", "hallo verden!", "hej verden", "hej verden!", "hej världen", "hej världen!"}  # + Danish/Swedish (remediation R3)
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
    if PROJECT_TITLE.match(str(item.get("title") or "")):
        return Decision(False, "project_title", "The item is titled as a project or reference description, not news.")
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
    if PRESS_TITLE.match(str(item.get("title") or "")) or any(PRESS_SLUG.match(segment) for segment in path_segments):
        return Decision(True, "article_press_release", "The item is a press release or announcement by its title or address.")
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
    stamps: dict[tuple[str, str], list[int]] = {}
    for index, (source, item) in enumerate(items):
        instant = _instant(item)
        if instant is not None and (instant.hour, instant.minute, instant.second) != (0, 0, 0):  # midnight = a date, not a time
            stamps.setdefault((source, str(item.get("date"))), []).append(index)
    for same_second in stamps.values():
        distinct = {(str(items[index][1].get("url") or ""), fold(items[index][1].get("title"))) for index in same_second}
        if len({url for url, _ in distinct}) >= 2 and len({title for _, title in distinct}) >= 2:
            members.update(same_second)  # different posts created in the same second: imported (e.g. a theme's demo content)
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


EVERGREEN_TITLE = re.compile(
    # Remediation R3: an unambiguous advice question also counts after a "Topic:" prefix ("Vindusvask for bedrifter: Hvor
    # ofte bør vinduene vaskes?"); "Slik" or "Hva er" after a colon is often news ("Ny avtale: Slik blir …").
    r"^(?:slik|hvordan|hvor ofte|hva er|hva du|hva bør|tips|råd|guide|how to|how do|what is|what are|why|types of|understanding|introduction to)\b"
    r"|[:–—]\s+(?:hvor ofte|hvordan|how to|how do|how often)\b"
    r"|sjekkliste|checklist|komplett guide|complete guide|\bguide\b|\btips\b|dette bør|regler for|key differences|\bvs\.?\b"
    # V3.1: an advice question with "bør/burde" ("Når bør valpen starte på valpekurs?"), "Hvorfor …" explainers, "råd til …"
    r"|\b(?:bør|burde|should)\b[^?]*\?\s*$|^hvorfor\b(?!\s+(?:vi|we)\b)|\bråd (?:til|for|om)\b", re.I)
# Remediation R6: a second-person word marks marketing or advice only in context — the reader's possessions ("din",
# "ditt", "your"), an offer to the reader ("for deg", "gir deg"), a modal ("du kan", "kan du"), or "slik … dere". A bare
# pronoun is often news ("Her finner du Barneombudet på Arendalsuka", "Få med deg …") or an interjection ("Du store
# verden"). "deres" is left out: it is also "their".
READER_ADDRESS = re.compile(
    r"\b(?:din|ditt|dine|your|yours)\b"
    r"|\b(?:for|til|gir|gi|tilbyr|hjelper|hjelpe|lar)\s+(?:deg|dere|you)\b"
    r"|\b(?:du|dere|you)\s+(?:kan|kunne|må|bør|skal|vil|får|trenger|can|could|should|need|will)\b"
    r"|\b(?:kan|kunne|må|bør|skal|vil|can|could|should)\s+(?:du|dere|you)\b"
    r"|\bslik\b.*\b(?:du|dere)\b|\byou'(?:ll|re|ve)\b", re.I)
PUBLISHER_NACE = ("58.1", "60.", "63.91", "63.12")


def feed_item_outside_news_section(url: str, news_section_items: int) -> bool:
    """Remediation R3: a site's RSS feed often carries every page type. When the site has its own news section (at least
    two items under /nyheter/, /aktuelt/, /blogg/ …), a feed item that sits two or more levels deep in another section
    (/kunnskap-og-forskning/…, /tips-og-rad/…, /min-historie/…, /vestland/<event>/) is not news. Root-level posts
    (/slug/) and dated addresses are left alone."""
    if news_section_items < 2:
        return False
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).casefold()
    segments = [segment for segment in path.split("/") if segment]
    return len(segments) >= 2 and not NEWS_SEGMENT.match(segments[0]) and not DATED_PATH.search(path)


def evergreen_title(title: str) -> bool:
    """Advice, how-to and second-person marketing titles: content a company publishes, not news about it."""
    text = " ".join(str(title or "").split())
    return bool(EVERGREEN_TITLE.search(text) or READER_ADDRESS.search(text))


def is_publisher(profile: dict[str, Any]) -> bool:
    """Newspaper, magazine and other publishers, broadcasters and news agencies (NACE 58.1, 60, 63.91, 63.12): the
    articles on their sites are their product, not news about the company."""
    live = ((profile.get("evidence") or {}).get("registry_live") or {}).get("value") or {}
    return str((live.get("industry") or {}).get("kode") or "").startswith(PUBLISHER_NACE)


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


# ---------- V3.1: source tier, content assessment and the news policy (docs/v31-news-analysis.md) ----------

# A dedicated newsroom or press section. Blogs, magazines, inspiration and tips sections are not newsrooms.
NEWSROOM_SEGMENT = re.compile(r"^(?:nyheter|nyhet|aktuelt|news|presse|press|pressemeldinger|pressemelding|press-releases?|newsroom|"
                              r"nyhetsarkiv|siste-nytt|aktuelle-saker|aktueltsaker|nyhetssaker|nytt|media|mediesenter)$")
BLOG_SEGMENT = re.compile(r"^(?:blogg?|bloggen|blogginnlegg|posts?|innlegg|artikler|artikkel|articles?|magasin|magazine|inspirasjon|"
                          r"tips|fagstoff|fagartikler|kunnskap|guide|guider|tema)$")

# Evidence that an item reports a development of the company: an event in the company's life.
DEVELOPMENT = re.compile(
    r"\b(?:åpner|åpnet|åpning(?:en)?|nyåpn\w*|lanserer|lansert|lansering(?:en)?|ansetter|ansatt|ansettelse|nyansatt\w*|"
    r"ny(?:e|tt)? (?:daglig leder|leder|sjef|medarbeider\w*|kollega\w*|ansatte?|lærling\w*|partner|eier\w*|styreleder|avdeling|butikk|kontor\w*|lokaler|avtale|kontrakt|bygg|anlegg|lager|verksted|produkt\w*|tjeneste\w*|leveranse\w*|prosjekt|samarbeid)|"
    r"har startet|startet opp|er i gang|kommer i gang|arrangerer|arrangerte|arrangert|inviterer|"
    r"tiltrer|begynner hos oss|velkommen til (?:oss|teamet|laget)|ønsker \w+(?: \w+)? velkommen|"
    r"signer(?:er|t|te)|inngå(?:r|tt|tte)|kontrakt(?:en)?|rammeavtale\w*|avtale med|samarbeidsavtale\w*|samarbeid(?:et)? med|"
    r"kjøper|kjøpt|kjøpte|oppkjøp\w*|overtar|overtatt|fusjoner(?:er|t|te)|fusjonen|fusjon med|slår seg sammen|"
    r"vinner|vant|vinn(?:ere|eren)|tildelt|tildeles|mottok|mottar|kåret|nominert|finalist|pris(?:en)? for|"
    r"sertifisert|sertifisering(?:en)?|godkjent som|jubileum|jubilerer|feirer|\d+[- ]års?(?:jubileum|dag)|"
    r"flytter|flyttet|nye lokaler|utvider|har utvidet|utvidelse(?:n)? av|etablerer|etablert|starter opp|oppstart(?:en)?|"
    r"ferdigstilt|overlevert|overlevering(?:en)?|byggestart|spadetak|innviet|innvielse|"
    r"rekord\w*|omsetning(?:en)?|årsresultat\w*|resultat(?:et)? for|kvartalsrapport\w*|rapport: q\d|investerer|har investert|"
    r"oversettes|oversatt til|solgt til \d+|utgitt|utgir|gir ut|ny bok|nytt album|premiere|"
    r"sponsoravtale\w*|hovedsponsor|pressemelding|kunngjør|"
    r"opens?|opened|launch(?:es|ed)?|acquir(?:es|ed)|acquisition|merger|appoint(?:s|ed)|hires?|hired|joins|award(?:ed|s)?|wins?|won|"
    r"certified|partnership|partners with|signs?|signed|contract|expands?|expansion|milestone|anniversary|annual results|quarterly)\b", re.I)
# A listing of a property, plot or product for sale, or a completed job shown as a reference.
LISTING = re.compile(r"\b(?:til salgs|for salg|kommer for salg|meld (?:din )?interesse|prisantydning|visning|tomten?|tomter|eneboligtomt|"
                     r"kvm|m²|boligareal|soverom|hustype\w*|byggeklar|selveier\w*|leveres med|levert av \w+|ferdigstiller)\b", re.I)
# A standing service, membership, booking or course offer rather than an article.
SERVICE = re.compile(r"\b(?:bli medlem|meld(?:e)? skade|skademeldingsskjema|skademelding|ta kontakt (?:med \w+(?: \w+)? )?for påmelding|"
                     r"påmelding(?:sskjema)?|bestill (?:time|her|nå)|book (?:time|her|nå)|kontakt oss for (?:tilbud|pris)|pris(?:er)? fra kr)\b", re.I)
# A job advertisement: careers content, reported under job_posting / careers_page, never as news.
RECRUITMENT = re.compile(r"\b(?:send (?:inn )?(?:din |en )?søknad|søknad (?:og|med) cv|cv og søknad|søknadsfrist(?:en)?|søk (?:på )?stillingen|"
                         r"ledige? (?:stillinge?r?|vikariat\w*|jobber?)|vi søker (?:etter )?(?!å\b|om\b|støtte\b)\w+|søker (?:etter )?(?:en|ei|et|nye?) \w+(?:er|ere|ør|ører|ist|ister|leder|sjef|medarbeidere?|kollegaer|vikarer)\b|"
                         r"er du (?:vår|vårt|våre|\w+s) nye|stillingsannonse|tiltredelse etter avtale|"
                         r"vi söker|söker vi|söker (?:nu )?efter|sökes\b|sök senast|ansök\w*|lediga tjänster|vi rekryterar|"
                         r"apply now|application deadline|send (?:us )?your (?:cv|application)|we are hiring|we're hiring|is (?:now )?hiring|now hiring|"
                         r"we are looking for (?:a|an)\b|join our team)", re.I)
# A product or rental-item page: the item presents goods for sale or hire rather than reporting anything.
PRODUCT = re.compile(r"\b(?:pris på forespørsel|legg i (?:handle)?kurv(?:en)?|add to (?:cart|basket)|kjøp nå|buy now|lagerstatus|"
                     r"varenummer|varenr\.?|art\.? ?nr\.?|produktnummer|tekniske data|tekniske spesifikasjoner|technical specifications|datablad)\b", re.I)
# An article written to inform or sell to the reader rather than report: "I denne artikkelen vil vi …", "La oss se på …".
ARTICLE_MARKETING = re.compile(r"\b(?:i denne artikkelen|i dette innlegget|i denne guiden|in this (?:article|post|guide)|la oss se (?:nærmere )?på|"
                               r"her (?:får du|ser vi nærmere på|er (?:noen|fem|tre|ti) (?:tips|råd|grunner))|let's take a (?:closer )?look)\b", re.I)
# A commercial offer to the reader: what the company sells, not something that happened to it.
OFFER = re.compile(r"\b(?:vi tilbyr|tilbyr vi|we offer|i (?:vår|vår egen) nettbutikk|nettbutikken vår|i nettbutikken|kjøp (?:dem|den|det) (?:her|hos oss)|"
                   r"bestill (?:hos oss|i dag)|uforpliktende (?:prat|tilbud|samtale|befaring)|kontakt oss (?:i dag|for (?:en )?(?:prat|tilbud|pris)))\b", re.I)
# The title of a standing page, not of an article ("Forside", "Kontakt", "Om oss", a bare "Velkommen").
STANDING_PAGE_TITLE = re.compile(r"^\s*(?:forside|hjem|home|startside|kontakt(?: oss)?|contact(?: us)?|om oss|about(?: us)?|velkommen|welcome)\s*[!.]?\s*(?:[|–—-].*)?$", re.I)
# Feed boilerplate naming the site: "The post X appeared first on Lugn Hytter." (WordPress, Yoast and their translations).
FEED_BOILERPLATE = re.compile(r"(?:The post|Innlegget|Inlägget|Der Beitrag|Indlægget)\s.{1,300}?\s(?:appeared first on|first appeared on|dukket først opp på|"
                              r"dök först upp på|dukkede først op på|erschien zuerst auf)\s[^.]{1,120}\.?", re.I | re.S)
LISTICLE_TITLE = re.compile(r"\b\d+\s+(?:[a-zæøå]+\s+)?(?:tips|tiltak|råd|steg|måter|grunner|feil|ting|triks|ways|steps|tricks|reasons|mistakes|things)\b", re.I)
SECOND_PERSON = re.compile(r"\b(?:du|deg|din|dine|ditt|dere|you|your|yours)\b", re.I)
# The company speaking: "vi/vår" — and "jeg/min" on the many one-person companies' own sites (an author's or a craftsman's).
COMPANY_VOICE = re.compile(r"\b(?:vi|oss|vår|vårt|våre|we|our|us|jeg|meg|min|mitt|mine|my)\b", re.I)


def source_tier(url: str, page_url: str = "", feed_url: str = "") -> str:
    """newsroom | blog | post. `newsroom`: the item (or the listing it came from) is in a dedicated news or press section.
    `blog`: a blog, magazine, tips or knowledge section, or a blog feed. `post`: anything else (a root-level CMS post, a
    homepage card)."""
    item_segments = segments(url)
    page_segments = segments(page_url) if page_url and not _same(page_url, url) else []
    if any(BLOG_SEGMENT.match(segment) for segment in item_segments + page_segments) or "blog" in feed_url.casefold():
        return "blog"
    if any(NEWSROOM_SEGMENT.match(segment) for segment in item_segments + page_segments):
        return "newsroom"
    return "post"


@dataclass(frozen=True)
class ContentAssessment:
    kind: str  # development | company_named | company_voice | advice | listing | product | service | recruitment | insufficient
    basis: str
    evidence: str = ""


def _quote(match: re.Match[str] | None, text: str) -> str:
    if not match:
        return ""
    start, end = max(0, match.start() - 40), min(len(text), match.end() + 40)
    return " ".join(text[start:end].split())


def company_names(legal: LegalName, site_label: str = "") -> list[str]:
    """Folded name forms that, written in an item on the company's own self-operated site, refer to the company: the
    legal name without its legal form, its leading brand words (at least 4 letters, not generic) and the site's own
    domain name when that is named after the company."""
    from .names import COUNTIES, DISTINGUISHING, GENERIC_BRANDS, LEGAL_FORMS, NEUTRAL, REGIONS
    words = [word for word in re.findall(r"[a-z0-9]+", fold(legal.name).replace("a/s", " as ")) if word not in LEGAL_FORMS]
    vague = GENERIC_BRANDS | COUNTIES | REGIONS | DISTINGUISHING | NEUTRAL | legal.places
    names = {" ".join(words)} if words else set()
    for k in range(1, len(words)):
        brand = " ".join(words[:k])
        if len(brand.replace(" ", "")) >= 4 and brand.replace(" ", "") not in vague:
            names.add(brand)
    if site_label and len(site_label) >= 4 and site_label not in vague:
        names.add(site_label)
    return sorted(name for name in names if name)


def mentions_company(text: str, names: list[str]) -> str | None:
    """The first company name written in the text as whole words; a one-word name (a domain label such as "vikenpark")
    also matches when written as two or three consecutive words ("Viken Park")."""
    # Norwegian genitive adds -s without an apostrophe ("Beredts samarbeid"): read it as the name word
    name_words = {word for name in names for word in name.split()}
    words = [word[:-1] if len(word) > 4 and word.endswith("s") and word[:-1] in name_words else word for word in re.findall(r"[a-z0-9]+", fold(text))]
    folded = " " + " ".join(words) + " "
    joined = {"".join(words[i:i + n]) for n in (2, 3) for i in range(len(words) - n + 1)}
    for name in names:
        if f" {name} " in folded or (" " not in name and name in joined):
            return name
    return None


VOICE_WORD = re.compile(r"\b(?:vi|oss|vår|vårt|våre|we|our|us|jeg|min|mitt|mine|my)\b", re.I)


# A sentence ends at . ! ? before a capital or an opening quote, but not after an abbreviation ("nr. 2", "bl.a. Kina").
SENTENCE_BREAK = re.compile(r"(?<!\bnr\.)(?<!\bca\.)(?<!\bbl\.a\.)(?<!\bf\.eks\.)(?<!\bkl\.)(?<!\bst\.)(?<!\bno\.)(?<!\bdvs\.)(?<!\bosv\.)(?<=[.!?])\s+(?=[A-ZÆØÅ«\"“])")


def _sentences(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in SENTENCE_BREAK.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    return spans + [(start, len(text))]


def voiced_development(text: str) -> re.Match[str] | None:
    """A development the company states about itself: the event word in a sentence that, with its neighbours, is in
    the company's own voice ("Sammen med Bilia inviterer vi til dobbelkamp"; "… leser våre bøker … «Detektivbyrå nr. 2»
    oversettes nå til 18 språk"). Reader-addressing text that also reports what the company itself does is a notice of
    that event, not advice."""
    spans = _sentences(text)
    for match in DEVELOPMENT.finditer(text):
        index = next((i for i, (start, end) in enumerate(spans) if start <= match.start() <= end), 0)
        window = text[spans[max(0, index - 1)][0]:spans[min(len(spans) - 1, index + 1)][1]]
        if VOICE_WORD.search(window):
            return match
    return None


def named_development(text: str, names: list[str]) -> re.Match[str] | None:
    """A development in the same sentence as the company's name ("Proba har fått i oppdrag …")."""
    for start, end in _sentences(text):
        sentence = text[start:end]
        if mentions_company(sentence, names):
            match = DEVELOPMENT.search(sentence)
            if match:
                return match
    return None


def strip_boilerplate(text: str) -> str:
    return FEED_BOILERPLATE.sub(" ", text or "")


def assess_content(title: str, body: str, *, names_company: bool, names: list[str] | None = None) -> ContentAssessment:
    """What the item's own words say (title plus the body text captured with it: feed body, card text, description or
    the article page, each without site boilerplate). A development counts only when the text attributes it to the
    company: stated in the title, in the company's voice, or in a sentence naming the company."""
    title = " ".join(str(title or "").split())
    body = " ".join(strip_boilerplate(str(body or "")).split())
    if title and len(title) >= 6:
        body = body.replace(title, " ")  # cards and feeds repeat the title ("… Leave a comment on <title>"): count it once
    text = f"{title}. {body}" if body.strip() else title
    mentioned = mentions_company(text, names or [])
    names_company = names_company or bool(mentioned)
    words = max(1, len(text.split()))
    second = len(SECOND_PERSON.findall(text))
    voice = len(COMPANY_VOICE.findall(text))
    title_development = DEVELOPMENT.search(title)
    voiced = voiced_development(text)
    named = named_development(text, names or []) if names else None
    development = title_development or voiced or named
    listing = LISTING.search(text)
    product = PRODUCT.search(text)
    service = SERVICE.search(text)
    recruitment = RECRUITMENT.search(text)
    if STANDING_PAGE_TITLE.match(title):
        return ContentAssessment("service", "the title is a standing page's (front page, contact, about, welcome), not an article's", title)
    if recruitment and not title_development:
        return ContentAssessment("recruitment", "a job advertisement (careers content, not news)", _quote(recruitment, text))
    if listing and not title_development:
        return ContentAssessment("listing", "a property, plot, product or completed job is presented for sale or as a reference", _quote(listing, text))
    if product and not title_development:
        return ContentAssessment("product", "a product or rental-item page (price on request, cart, specifications)", _quote(product, text))
    offer = OFFER.search(text)
    marketing = ARTICLE_MARKETING.search(text)
    if service and not development:
        return ContentAssessment("service", "a standing service, membership, booking or course offer, not an article", _quote(service, text))
    if offer and not development:
        return ContentAssessment("service", "a commercial offer to the reader (what the company sells), not a report", _quote(offer, text))
    if marketing and not development:
        return ContentAssessment("advice", "written to inform or sell to the reader (\"i denne artikkelen …\"), not to report", _quote(marketing, text))
    advice_title = evergreen_title(title) or bool(LISTICLE_TITLE.search(title))
    advice_body = second >= 3 and second / words >= 0.025 and second > voice
    if (advice_title or advice_body) and not ((title_development or voiced) and not advice_title):
        reason = "the title is advice or a guide" if advice_title else f"the text addresses the reader ({second} second-person words in {words})"
        return ContentAssessment("advice", reason, _quote(SECOND_PERSON.search(text), text) if not advice_title else title)
    if development:
        who = "in its title" if development is title_development else "in the company's voice" if development is voiced else "naming the company"
        return ContentAssessment("development", f"reports a company development ({development.group(0).lower()}) {who}",
                                 _quote(development, title if development is title_development else text))
    if names_company:
        return ContentAssessment("company_named", f"names the company{f' ({mentioned})' if mentioned else ''} and is neither advice, a listing nor a service page")
    if voice:
        return ContentAssessment("company_voice", "written in the company's own voice (we/our) and is neither advice, a listing nor a service page",
                                 _quote(COMPANY_VOICE.search(text), text))
    return ContentAssessment("insufficient", "neither names the company, speaks in its voice nor states a company development")


# Policies compared in docs/v31-news-analysis.md §6 and §9; site_facts.NEWS_POLICY names the one used.
POLICIES = ("current", "newsroom", "newsroom_item", "newsroom_item_content", "newsroom_item_content_entity", "layered", "anchored", "hybrid", "strict")


def news_policy_decision(policy: str, *, tier: str, content: ContentAssessment, names_company: bool) -> Decision | None:
    """None = publish under this policy; a Decision = withhold, with the reason. Applied after the V3 item gate, the
    entity rules and the subject rules, which every policy keeps."""
    negative = content.kind in ("advice", "listing", "product", "service", "recruitment")
    if policy == "current":
        return None
    if policy.startswith("newsroom") and tier != "newsroom":
        return Decision(False, "not_in_a_newsroom_section", "Only items in a dedicated news or press section are considered.")
    if policy in ("newsroom_item", "newsroom_item_content", "newsroom_item_content_entity", "layered", "anchored", "hybrid", "strict") and negative:
        return Decision(False, f"content_{content.kind}", f"Withheld: {content.basis}.")
    if policy in ("newsroom_item_content", "newsroom_item_content_entity") and content.kind != "development":
        return Decision(False, "no_company_development", "Withheld: no stated company development in the title or the captured text.")
    if policy == "newsroom_item_content_entity" and not names_company:
        return Decision(False, "company_not_named", "Withheld: the item does not name the company.")
    if policy == "hybrid" and content.kind == "insufficient" and tier != "newsroom":
        return Decision(False, "not_anchored_to_the_company", "Withheld: outside a news section, the item neither names the company, speaks in its voice nor states a company development.")
    if policy == "strict" and content.kind != "development" and not (tier == "newsroom" and content.kind in ("company_named", "company_voice")):
        # V3.1 §9: on the company's own site nearly every page names it and says "we"; outside a dedicated news
        # section only a development the text attributes to the company is evidence that the item is news.
        return Decision(False, "no_attributed_development", "Withheld: outside a news section, the item states no company development attributed to the company.")
    if policy == "anchored" and content.kind == "insufficient":
        return Decision(False, "not_anchored_to_the_company", "Withheld: the item neither names the company, speaks in its voice nor states a company development.")
    if policy == "layered" and content.kind != "development":
        # A newsroom item that names the company and is neither advice, a listing nor a service page is the company's
        # own announcement even without an event word; everywhere else a stated development is required.
        if not (tier == "newsroom" and names_company):
            return Decision(False, "no_company_development", "Withheld: no stated company development in the title or the captured text.")
    return None


# ---------- V3.1.1: national units of a group (Builderr rescoring revision) ----------

UNIT_MARKERS = {"norge", "norway", "noreg", "uk", "sverige", "sweden", "danmark", "denmark", "finland", "suomi", "deutschland", "germany", "usa"}


def split_unit_names(legal: LegalName, names: list[str]) -> tuple[list[str], list[str]]:
    """For a national unit of a group ("TEQT NORGE AS", "ELEDA RAIL NORGE AS"): (names that carry the unit's national
    marker, bare brand names without it). Written on the site, a bare brand ("Teqt", "Eleda") is the group's name, so it
    is not evidence that an item is about this unit. For any other company the bare list is empty."""
    from ..attribution.social import national_markers

    if not national_markers(legal.name):
        return names, []
    unit = [name for name in names if set(name.split()) & UNIT_MARKERS or any(marker in name.replace(" ", "") for marker in ("norge", "norway"))]
    bare = [name for name in names if name not in unit]
    return unit, bare


def group_brand_only(text: str, unit: list[str], bare: list[str]) -> str | None:
    """The bare group brand the text names, when it never names the national unit itself."""
    if not bare or mentions_company(text, unit):
        return None
    return mentions_company(text, bare)


# ---------- V3.1.1: the announcement tier (Builderr rescoring revision, docs/v311-rescore-revision.md §4) ----------
# Builderr asked for "a dated item ... linked from the company's own site" and requires 95% correct attribution. On
# every labelled set, V3.1's anchored policy publishes 48-80% correct news; the errors are guides, product pages,
# opinion pieces and other organisations' stories, which no deterministic content rule separated. A headline that
# itself announces an event in the organisation's life (an acquisition, appointment, agreement, opening, award,
# anniversary, launch, certification, annual meeting, new name, grant), on an item that names the organisation, is
# the one subset that did (93-96% on the consumed, labelled sets; diagnostic, not independent). Only that subset is
# published; every V3.1 rule still runs first.
ANNOUNCEMENT = re.compile(
    r"\b(?:"
    r"kjøper|kjøpt(?:e)?(?: opp)?|kjøper opp|oppkjøp\w*|overtar|overtatt|fusjon\w*|slår seg sammen|blir (?:en )?del av|blir deleier|deleier i|"
    r"acquir\w+|acquisition|merger|merges|förvärv\w*|förvärvar|köper|"
    r"ny(?:e|tt)? (?:daglig leder|adm(?:\.|inistrerende)? dir\w*|ceo|styreleder|leder|direktør|partner|medeier|eier|avdelingsleder|salgssjef|markedssjef)|"
    r"ansatt som|ansetter (?:ny|en)|tiltrer|går inn som|appoint\w*|new ceo|joins as|"
    r"signer\w*|inngå\w*|inngått|tildelt (?:kontrakt|oppdrag|prisen)|vinner (?:kontrakt|oppdrag|anbud|prisen)|kontrakt med|avtale med|rammeavtale\w*|samarbeidsavtale\w*|"
    r"signs?|signed|awarded|wins? (?:contract|award)|contract with|partners? with|partnership|mou\b|"
    r"åpner|åpnet|åpning av|nyåpn\w*|innvi\w*|flytter (?:til|inn)|nye lokaler|nytt (?:kontor|lager|anlegg|bygg|verksted)|ny (?:avdeling|butikk|fabrikk)|opens?|opened|"
    r"kåret|vant (?:prisen|pris)|vi vant|tildelt|nominert|award|wins|won|"
    r"feirer|jubilerer|jubileum|\d+[ -]?års?(?:jubileum)?\b|\d+ år\b|anniversary|"
    r"lanserer|lansert|lansering|launch\w*|"
    r"sertifisert|resertifisert|miljøfyrtårn|iso[ -]?\d{4,5}|certified|"
    r"årsmøte|generalforsamling|årsberetning|årsrapport|årsresultat\w*|kvartalsrapport|annual (?:meeting|report|results)|"
    r"investerer|investering|utvider|utvidelse|ekspander\w*|expands?|expansion|etablerer|etablert|startet opp|"
    r"nytt navn|skifter navn|endrer navn|new name|rebrand\w*|"
    r"pressemelding|press release|kunngjør|announce\w*|"
    r"fått (?:støtte|tilskudd|midler)|mottar (?:støtte|tilskudd)|støtte fra|tilskudd fra|"
    r"har flyttet|flyttet til|(?:nytt |inngår |innleder )?samarbeid med|collaboration with|sertifisering|vinner|introduserer|introduces|introduced|"
    r"ny(?:e|tt)? (?:fagarbeider\w*|medarbeider\w*|kollega\w*|ansatte?|lærling\w*|trener|assistent ?trener|rektor|prosjektleder|styremedlem\w*|medlem(?:mer)?)|"
    r"fått i oppdrag|nytt oppdrag|nye oppdrag|ny rapport|new report"
    r")\b", re.I)


def announcement_decision(title: str, body: str, *, names: list[str], names_company: bool) -> Decision | None:
    """None = publish (the item is a dated announcement of this organisation's own development); a Decision = withhold."""
    title = " ".join(str(title or "").split())
    if title.rstrip().endswith("?"):
        return Decision(False, "question_title_not_announcement", "Withheld: a question as the headline is advice or an explainer, not an announcement.")
    match = ANNOUNCEMENT.search(title)
    if not match:
        return Decision(False, "headline_not_an_announcement",
                        "Withheld: the headline does not announce an event in the organisation's life (acquisition, appointment, agreement, "
                        "opening, award, anniversary, launch, certification, annual meeting, new name or grant).")
    if not (names_company or mentions_company(f"{title}. {strip_boilerplate(body)}", names)):
        return Decision(False, "announcement_does_not_name_the_company", "Withheld: the announcement does not name this organisation.")
    return None
