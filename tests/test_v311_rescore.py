"""V3.1.1 — Builderr rescoring revision: regression tests for the evaluator's findings on ff3b515.

Builderr (2026-11) checked 86 claims of ff3b515 and found 11 that belonged to other companies; the two it named are
LØWEHJERTE DESIGN AS's Squarespace profiles. Each test pins one confirmed defect class, or one legitimate result that
the stricter rules must keep. Fixtures replay exact captured bytes; no network."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.c12_replay import Fixture  # noqa: E402
from norway_company_agent.attribution.names import LegalName, handle_relation  # noqa: E402
from norway_company_agent.attribution.social import owner_check  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402
from norway_company_agent.site_facts import CapturedPage, extract_site_facts  # noqa: E402

V311 = ROOT / "tests" / "fixtures" / "v311"
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)


@lru_cache(maxsize=None)
def replay(org: str, base: Path = V311) -> dict:
    fixture = Fixture(org, base=base)
    envelope = run_batch([InputRow(0, org, org)], run_id="v311-regression", **fixture.injected())["envelopes"][0]
    assert validate_envelope(envelope) == [], validate_envelope(envelope)
    return envelope


def claims(org: str, field: str, availability: str | None = "available") -> list[dict]:
    return [claim for claim in replay(org)["claims"] if claim["field"] == field and (availability is None or claim["availability"] == availability)]


def page(url: str, html: str) -> CapturedPage:
    raw = html.encode("utf-8")
    return CapturedPage(url, raw, hashlib.sha256(raw).hexdigest(), "2026-11-14T08:00:00Z")


def organisation(name: str, url: str, same_as: list[str]) -> str:
    node = {"@context": "http://schema.org", "@type": "Organization", "name": name, "url": url, "sameAs": same_as}
    return f'<script type="application/ld+json">{json.dumps(node)}</script>'


def profile(name: str, org: str = "987654321", legal_form: str = "AS", group: dict | None = None) -> dict:
    return {"name": name, "organisation_number": org, "legal_form": legal_form,
            "evidence": {"group": {"status": "available", "value": group} if group else {"status": "not_found"}}}


class LowehjerteSquarespace(unittest.TestCase):
    """LØWEHJERTE DESIGN AS (987832827): the evaluator's two confirmed wrong-company claims."""

    SQUARESPACE = {"http://facebook.com/squarespace", "https://www.linkedin.com/company/squarespace/mycompany/verification/"}

    def test_both_squarespace_urls_are_not_published(self):
        self.assertEqual({claim["value"] for claim in claims("987832827", "social_profile")}, set())

    def test_the_withheld_profiles_name_the_rule(self):
        held = replay("987832827")["evidence"]
        record = next(claim for claim in claims("987832827", "social_profile", None))
        self.assertEqual(record["availability"], "ambiguous")
        site = claims("987832827", "official_website")
        self.assertEqual([claim["value"] for claim in site], ["https://www.lowehjerte.no/"], "the company's own website stays")
        self.assertTrue(held)

    def test_extract_site_facts_codes(self):
        fixture = Fixture("987832827", base=V311)
        home = CapturedPage("https://www.lowehjerte.no/", fixture.raw("https://www.lowehjerte.no/"), "x", "2026-11-13T22:03:41Z")
        facts = extract_site_facts(profile("LØWEHJERTE DESIGN AS", "987832827"), [home], now=NOW)
        self.assertEqual(facts.profiles, [])
        codes = {item["url"]: (item.get("attribution") or {}).get("code") for item in facts.ambiguous_profiles}
        self.assertEqual(set(codes), self.SQUARESPACE)
        self.assertEqual(codes["https://www.linkedin.com/company/squarespace/mycompany/verification/"], "not_a_public_profile_url")
        self.assertEqual(codes["http://facebook.com/squarespace"], "platform_provider_account")


class OwnerChecks(unittest.TestCase):
    def check(self, name, url, site, platform=None, **kwargs):
        platform = platform or next(p for p in ("facebook", "instagram", "linkedin", "youtube") if p in url)
        return owner_check(profile(name, **kwargs), LegalName(name), platform, url, site)

    def test_sameas_cannot_override_a_platform_provider(self):
        """The site's own Organization node (url on the verified site, the company's own name) lists the builder's
        accounts next to the company's: sameAs still cannot attribute the builder's accounts."""
        site = "https://www.fjordform.no/"
        html = ("<html><body><h1>Fjordform Design AS</h1>"
                + organisation("Fjordform Design AS", site, ["https://www.facebook.com/squarespace", "https://www.instagram.com/wix/",
                                                              "https://www.facebook.com/fjordformdesign"]) + "</body></html>")
        facts = extract_site_facts(profile("FJORDFORM DESIGN AS"), [page(site, html)], now=NOW)
        self.assertEqual({item["url"] for item in facts.profiles}, {"https://www.facebook.com/fjordformdesign"})
        held = {item["url"]: item["attribution"]["code"] for item in facts.ambiguous_profiles}
        self.assertEqual(held["https://www.facebook.com/squarespace"], "platform_provider_account")
        self.assertEqual(held["https://www.instagram.com/wix/"], "platform_provider_account")

    def test_generic_platform_and_admin_urls_establish_nothing(self):
        for url in ("https://www.linkedin.com/company/fjordform/admin/", "https://www.linkedin.com/company/fjordform/mycompany/verification/",
                    "https://www.facebook.com/fjordform/settings/", "https://www.facebook.com/facebook", "https://www.linkedin.com/company/linkedin/"):
            with self.subTest(url=url):
                self.assertIsNotNone(self.check("FJORDFORM AS", url, "https://www.fjordform.no/"))

    def test_exact_legal_name_is_never_a_platform_provider(self):
        self.assertIsNone(self.check("SQUARESPACE AS", "https://www.facebook.com/squarespace", "https://www.squarespace.no/"))

    def test_group_account_of_a_national_unit(self):
        """The earlier labelled audits: GRUNDFOS NORGE AS -> facebook.com/Grundfos, the global group's account."""
        decision = self.check("GRUNDFOS NORGE AS", "https://www.facebook.com/Grundfos/", "https://www.grundfos.com/no")
        self.assertEqual(decision.code, "group_account_without_national_unit")
        self.assertIsNone(self.check("GRUNDFOS NORGE AS", "https://www.facebook.com/grundfosnorge", "https://www.grundfos.com/no"))
        self.assertEqual(self.check("BECTON DICKINSON U.K. LIMITED", "https://www.instagram.com/becton_dickinson/", "https://www.bd.com/en-uk/",
                                    legal_form="UTLA").code, "group_account_without_national_unit")

    def test_group_account_localised_abroad(self):
        """TEQT NORGE AS (929418727) on teqt.no links se.linkedin.com/company/teqt: the Swedish group's page."""
        self.assertEqual(self.check("TEQT NORGE AS", "https://se.linkedin.com/company/teqt", "https://www.teqt.no/").code,
                         "group_account_without_national_unit")
        self.assertEqual(self.check("INLUMI AS", "https://nl.linkedin.com/company/inlumi", "https://inlumi.com/").code,
                         "account_localised_abroad_on_group_site")

    def test_foreign_parent_in_the_registry(self):
        """VALMET AS (932383357): konsernstruktur names NELES CONTROLS OY (UTLA); valmet.com and linkedin/company/valmet are the group's."""
        group = {"navn": "NELES CONTROLS OY", "organisasjonsnummer": "981128354", "organisasjonsform": {"kode": "UTLA"},
                 "children": [{"navn": "VALMET AS", "organisasjonsnummer": "932383357", "parentOrganisasjonsnummer": "981128354"}]}
        self.assertEqual(self.check("VALMET AS", "https://www.linkedin.com/company/valmet/", "https://www.valmet.com/", org="932383357", group=group).code,
                         "foreign_parent_group_account")
        self.assertIsNone(self.check("VALMET AS", "https://www.linkedin.com/company/valmet-norway/", "https://www.valmet.com/", org="932383357", group=group))

    def test_sister_company_handle_with_its_own_legal_form(self):
        """BIRKELAND AS (996662292) on birkeland.no linked facebook.com/BirkelandTyseBergsprengerAs: another company's legal name."""
        self.assertEqual(handle_relation(LegalName("BIRKELAND AS"), "facebook", "https://www.facebook.com/BirkelandTyseBergsprengerAs").kind, "OTHER_ENTITY")
        self.assertEqual(handle_relation(LegalName("BIRKELAND AS"), "instagram", "https://www.instagram.com/birkeland_as/").kind, "EXACT")
        for name, url in (("NATURSTEIN MONTERING AS", "https://www.facebook.com/NatursteinMonteringAS/"),
                          ("SULLESTAD SUPPORT AS", "https://www.facebook.com/SullestadSupportAs")):
            with self.subTest(name=name):
                self.assertEqual(handle_relation(LegalName(name), "facebook", url).kind, "EXACT", "the company's own CamelCase legal name stays exact")

    def test_legitimate_accounts_stay(self):
        cases = (
            ("STROMMA NORWAY AS", "https://www.facebook.com/strommanorway", "https://www.stromma.com/en-no/norway-all/"),
            ("ELEDA RAIL NORGE AS", "https://www.instagram.com/eleda_rail_norge/", "https://www.eledarail.se/no"),
            ("THREE60 ENERGY NORWAY AS", "https://www.instagram.com/three60energy_norway/", "https://www.three60energy-norway.com/"),
            ("FERAL HYDRAULIC AS", "https://no.linkedin.com/company/feral-hydraulics", "https://feral.no/"),
            ("BODAHL-JOHANSEN AS", "https://www.facebook.com/bodahljohansenas", "https://bodahl.com/"),
            ("TRY NORWAY AS", "https://no.linkedin.com/company/try-norway", "https://www.trynorway.no/"),
            ("ELKJØP NORGE AS", "https://www.facebook.com/elkjop", "https://www.elkjop.no/"),
            ("MESON AB", "https://www.linkedin.com/company/meson-ab/", "https://www.mesongroup.com/"),
        )
        for name, url, site in cases:
            with self.subTest(name=name):
                self.assertIsNone(self.check(name, url, site, legal_form="UTLA" if name.endswith(" AB") else "AS"))


# ---------- news: the announcement tier ----------

SITE = "https://fjell-data.no/"
HOME = page(SITE, "<html><body><h1>Fjell Data AS</h1><p>Org.nr. 987 654 321</p></body></html>")


def feed(items: list[tuple], url: str = SITE + "feed/", channel: str = "") -> CapturedPage:
    """(title, link, date_xml, description)."""
    body = "".join(f"<item><title>{t}</title><link>{link}</link>{date}<description>{desc}</description></item>" for t, link, date, desc in items)
    raw = f"<?xml version='1.0'?><rss><channel>{channel}{body}</channel></rss>".encode()
    return CapturedPage(url, raw, hashlib.sha256(raw).hexdigest(), "2026-11-14T08:00:00Z", kind="feed")


def pub(day: str) -> str:
    return f"<pubDate>{day}</pubDate>"


def titles(facts) -> list[str]:
    return sorted(item["title"] for item in facts.activities)


def rejected(facts, code: str) -> bool:
    return f"activity:{code}" in facts.rejections


class AnnouncementTier(unittest.TestCase):
    FJELL = profile("FJELL DATA AS")

    def test_a_dated_company_announcement_is_published_with_provenance(self):
        article = page(SITE + "nyheter/fjell-data-signerer-avtale-med-bergen-kommune/", """<html><head>
            <script type="application/ld+json">{"@type":"NewsArticle","headline":"Fjell Data signerer avtale med Bergen kommune","datePublished":"2026-10-02T08:00:00+02:00"}</script>
            </head><body><main><h1>Fjell Data signerer avtale med Bergen kommune</h1><p>Publisert 2. oktober 2026</p>
            <p>Fjell Data AS har signert en treårig rammeavtale med Bergen kommune om drift av skolenes nettverk.</p></main></body></html>""")
        facts = extract_site_facts(self.FJELL, [HOME, article], now=NOW)
        self.assertEqual(titles(facts), ["Fjell Data signerer avtale med Bergen kommune"])
        item = facts.activities[0]
        self.assertEqual(item["url"], article.url, "the individual article URL")
        self.assertTrue(item["date"].startswith("2026-10-02"))
        self.assertEqual(item["content_sha256"], article.content_sha256, "provenance: the captured bytes behind the claim")

    def test_plain_slug_wordpress_articles_remain_eligible(self):
        posts = [("Fjell Data åpner nytt kontor i Bergen", SITE + "fjell-data-apner-nytt-kontor-i-bergen/", pub("Mon, 05 Oct 2026 10:00:00 +0000"),
                  "Fjell Data AS åpner nå kontor i Bergen sentrum.")]
        self.assertEqual(titles(extract_site_facts(self.FJELL, [HOME], [feed(posts)], now=NOW)), ["Fjell Data åpner nytt kontor i Bergen"])

    def test_product_service_advice_and_promotional_items_are_not_news(self):
        posts = [("Fjell Data Router X200", SITE + "nyheter/router-x200/", pub("Mon, 05 Oct 2026 10:00:00 +0000"), "Pris på forespørsel. Legg i handlekurven."),
                 ("Fem tips for sikrere passord", SITE + "nyheter/fem-tips/", pub("Tue, 06 Oct 2026 10:00:00 +0000"), "Fjell Data gir deg fem tips."),
                 ("Hva koster en brannmur?", SITE + "nyheter/hva-koster/", pub("Wed, 07 Oct 2026 10:00:00 +0000"), "Fjell Data forklarer prisene."),
                 ("Vi tilbyr nettverksdrift for bedrifter", SITE + "nyheter/nettverksdrift/", pub("Thu, 08 Oct 2026 10:00:00 +0000"), "Fjell Data AS tilbyr drift."),
                 ("Fjell Data søker driftstekniker", SITE + "nyheter/vi-soker/", pub("Fri, 09 Oct 2026 10:00:00 +0000"), "Send søknad og CV innen 1. desember.")]
        self.assertEqual(titles(extract_site_facts(self.FJELL, [HOME], [feed(posts)], now=NOW)), [])

    def test_the_announcement_must_name_the_company(self):
        posts = [("Grimstad finalist til årets maritime kommune", SITE + "nyheter/grimstad/", pub("Mon, 05 Oct 2026 10:00:00 +0000"), "Kommunen er nominert."),
                 ("Bergen kommune signerer avtale med Statens vegvesen", SITE + "nyheter/bk/", pub("Tue, 06 Oct 2026 10:00:00 +0000"), "Kommunen og vegvesenet har signert.")]
        facts = extract_site_facts(self.FJELL, [HOME], [feed(posts)], now=NOW)
        self.assertEqual(titles(facts), [])

    def test_a_foreign_parents_news_is_not_the_subsidiarys(self):
        """VALMET AS on valmet.com: the registry names a foreign parent; group releases never name Valmet AS."""
        group = {"navn": "NELES CONTROLS OY", "organisasjonsnummer": "981128354", "organisasjonsform": {"kode": "UTLA"},
                 "children": [{"navn": "VALMET AS", "organisasjonsnummer": "932383357", "parentOrganisasjonsnummer": "981128354"}]}
        site = "https://www.valmet.com/"
        home = page(site, "<html><body><h1>Valmet</h1><p>Valmet, Keilasatama 5, Espoo, Finland</p></body></html>")
        posts = [("Valmet acquires the process automation business of X", site + "news/valmet-acquires-x/", pub("Mon, 05 Oct 2026 10:00:00 +0000"),
                  "Valmet Oyj has signed an agreement to acquire X.")]
        facts = extract_site_facts(profile("VALMET AS", "932383357", group=group), [home], [feed(posts, site + "feed/")], now=NOW)
        self.assertEqual(titles(facts), [])
        self.assertEqual(facts.operator["kind"], "group_or_brand")
        self.assertEqual(facts.operator["code"], "international_site_of_foreign_parent_group")
        self.assertTrue(rejected(facts, "item_not_about_entity_on_group_or_brand_site"))

    def test_a_group_brand_story_is_not_the_national_units(self):
        """TEQT NORGE AS on teqt.no: "Teqt Group vokser gjennom oppkjøpet av …" is the group's acquisition."""
        site = "https://www.teqt.no/"
        home = page(site, "<html><body><h1>Teqt Norge</h1><p>Org.nr. 929 418 727</p></body></html>")
        posts = [("Teqt Group vokser gjennom oppkjøpet av Profil Montering AS", site + "no/nyheter/profil/", pub("Mon, 05 Oct 2026 10:00:00 +0000"),
                  "Teqt Group har kjøpt Profil Montering AS."),
                 ("Teqt Norge åpner avdeling i Bodø", site + "no/nyheter/bodo/", pub("Tue, 06 Oct 2026 10:00:00 +0000"), "Teqt Norge AS åpner nå i Bodø.")]
        facts = extract_site_facts(profile("TEQT NORGE AS", "929418727"), [home], [feed(posts, site + "feed/")], now=NOW)
        self.assertEqual(titles(facts), ["Teqt Norge åpner avdeling i Bodø"])
        self.assertTrue(rejected(facts, "group_brand_item_not_national_unit"))

    def test_an_international_brand_site_that_never_writes_the_norwegian_entity(self):
        site = "https://inlumi.com/"
        home = page(site, "<html><body><h1>inlumi</h1><p>inlumi is a global EPM consultancy.</p></body></html>")
        posts = [("inlumi announces partnership with Oracle", site + "news/oracle/", pub("Mon, 05 Oct 2026 10:00:00 +0000"), "inlumi announced a partnership.")]
        facts = extract_site_facts(profile("INLUMI AS", "999291988"), [home], [feed(posts, site + "feed/")], now=NOW)
        self.assertEqual(titles(facts), [])
        self.assertTrue(rejected(facts, "item_not_about_entity_on_international_brand_site"))


class NewsDates(unittest.TestCase):
    FJELL = profile("FJELL DATA AS")

    def test_an_application_deadline_in_its_own_element_is_never_a_publication_date(self):
        """The V3.1 defect (fib.no, eval120): "Søknadsfrist: 4. november 2026" became the item's date once it had passed."""
        listing = page(SITE + "nyheter/", """<html><body><main>
            <div class="card"><a href="/nyheter/fjell-data-signerer-avtale/"><h3>Fjell Data signerer avtale med Bergen kommune</h3></a>
            <p><strong>Søknadsfrist:</strong> <span>4. november 2026</span></p></div>
            <div class="card"><a href="/nyheter/fjell-data-feirer-20-ar/"><h3>Fjell Data feirer 20 år</h3></a>
            <p><b>Oppdatert:</b> <span>3. november 2026</span></p></div>
            <div class="card"><a href="/nyheter/fjell-data-apner/"><h3>Fjell Data åpner i Bodø</h3></a>
            <p><em>Påmeldingsfrist</em> <span>1. november 2026</span></p></div>
            </main></body></html>""")
        facts = extract_site_facts(self.FJELL, [HOME, listing], now=NOW)
        self.assertEqual(facts.activities, [])

    def test_a_feed_update_date_never_replaces_a_publication_date(self):
        atom = b"""<?xml version='1.0'?><feed xmlns="http://www.w3.org/2005/Atom"><updated>2026-11-10T10:00:00Z</updated>
            <entry><title>Fjell Data signerer avtale med Bergen kommune</title><link href="https://fjell-data.no/nyheter/avtale/"/>
            <updated>2026-11-09T10:00:00Z</updated><summary>Fjell Data AS har signert avtale.</summary></entry></feed>"""
        rss = feed([("Fjell Data åpner i Bodø", SITE + "nyheter/bodo/", "", "Fjell Data AS åpner i Bodø.")],
                   url=SITE + "feed/rss/", channel="<lastBuildDate>Tue, 10 Nov 2026 10:00:00 +0000</lastBuildDate>")
        atom_page = CapturedPage(SITE + "feed/atom/", atom, hashlib.sha256(atom).hexdigest(), "2026-11-14T08:00:00Z", kind="feed")
        facts = extract_site_facts(self.FJELL, [HOME], [atom_page, rss], now=NOW)
        self.assertEqual(facts.activities, [])
        self.assertTrue(rejected(facts, "updated_timestamp_not_publication_date") or rejected(facts, "no_explicit_date"))

    def test_an_event_date_in_running_text_is_not_a_publication_date(self):
        listing = page(SITE + "nyheter/", """<html><body><main>
            <div class="card"><a href="/nyheter/seminar/"><h3>Fjell Data inviterer til seminar</h3></a>
            <p>Seminaret holdes 26. november 2026 i våre lokaler i Bergen sentrum, med foredrag og lunsj.</p></div></main></body></html>""")
        self.assertEqual(extract_site_facts(self.FJELL, [HOME, listing], now=NOW).activities, [])

    def test_anchored_tier_reproduces_v31(self):
        import os
        from unittest import mock
        posts = [("Kampreferat runde 1 mot Storhamar", SITE + "kampreferat-1/", pub("Mon, 05 Oct 2026 10:00:00 +0000"), "Her er siste nytt fra oss.")]
        self.assertEqual(titles(extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)], now=NOW)), [], "not an announcement: withheld by default")
        with mock.patch.dict(os.environ, {"SIGNALPOST_NEWS_PUBLICATION": "anchored"}):
            self.assertEqual(titles(extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)], now=NOW)), ["Kampreferat runde 1 mot Storhamar"])


# ---------- jobs: individual, current advertisements by this employer ----------

from datetime import date, timedelta  # noqa: E402

from norway_company_agent.attribution.jobs import decide_job, employer_in_title  # noqa: E402

TODAY = datetime.now(timezone.utc).date()
SOON = (TODAY + timedelta(days=21)).strftime("%d.%m.%Y")
PAST = (TODAY - timedelta(days=40)).strftime("%d.%m.%Y")
CAREERS = SITE + "karriere/"


def careers_page(cards: str) -> CapturedPage:
    return page(CAREERS, f"<html><body><main><h1>Ledige stillinger hos Fjell Data</h1>{cards}</main></body></html>")


def card(title: str, href: str, extra: str = "") -> str:
    return f'<div class="job"><a href="{href}"><h3>{title}</h3></a><p>Fast stilling, 100 %</p>{extra}</div>'


class JobAdvertisements(unittest.TestCase):
    FJELL = profile("FJELL DATA AS")

    def facts(self, *pages):
        return extract_site_facts(self.FJELL, [HOME, *pages], now=datetime.now(timezone.utc))

    def test_a_current_individual_advertisement_is_published_dated_by_its_own_page(self):
        detail = page(CAREERS + "driftstekniker/", f"<html><body><h1>Driftstekniker</h1><p>Fjell Data AS søker driftstekniker.</p>"
                                                  f"<p><strong>Søknadsfrist:</strong> {SOON}</p></body></html>")
        facts = self.facts(careers_page(card("Driftstekniker", "/karriere/driftstekniker/")), detail)
        self.assertEqual([(job["title"], job["url"], job["currency"]["state"]) for job in facts.jobs],
                         [("Driftstekniker", CAREERS + "driftstekniker/", "open")])
        self.assertEqual(facts.jobs[0]["detail_page"], detail.url)

    def test_an_expired_advertisement_is_rejected(self):
        facts = self.facts(careers_page(card("Driftstekniker", "/karriere/driftstekniker/", f"<p>Søknadsfrist: {PAST}</p>")))
        self.assertEqual(facts.jobs, [])
        self.assertTrue(rejected_job(facts, "expired"))

    def test_a_generic_careers_page_is_not_a_job_advertisement(self):
        facts = self.facts(page(CAREERS, "<html><body><h1>Karriere</h1><p>Vi har for tiden ingen ledige stillinger. Send gjerne en åpen søknad.</p>"
                                         '<a href="/karriere/apen-soknad/">Åpen søknad</a></body></html>'))
        self.assertEqual(facts.jobs, [])
        undated = self.facts(careers_page(card("Driftstekniker", "/karriere/driftstekniker/")))
        self.assertEqual(undated.jobs, [], "a listed title with no date anywhere: whether it is open is unknown")

    def test_an_advertisement_for_another_employer_is_rejected(self):
        """FUNDRAISING NORGE (evalh400): V3.1 published finn.no ads for Norges Røde Kors and Caritas Norge."""
        cards = (card("Fundraiser, Norges Røde Kors", "https://www.finn.no/job/ad/479282780", f"<p>Søknadsfrist: {SOON}</p>")
                 + card("Innsamlingsansvarlig, Caritas Norge", "https://www.finn.no/job/ad/479635547", f"<p>Søknadsfrist: {SOON}</p>")
                 + card("Rådgiver hos Bergen kommune", "/karriere/radgiver-bergen-kommune/", f"<p>Søknadsfrist: {SOON}</p>"))
        facts = self.facts(careers_page(cards))
        self.assertEqual(facts.jobs, [])
        self.assertTrue(rejected_job(facts, "other_employer"))
        legal = LegalName("FJELL DATA AS")
        self.assertIsNone(employer_in_title("Selger – Oslo", legal), "a place is not an employer")
        self.assertIsNone(employer_in_title("Driftstekniker, Fjell Data AS", legal))

    def test_a_third_party_listing_without_a_verified_employer_is_rejected(self):
        cards = card("Markedsfører", "https://www.finn.no/job/ad/481000001", f"<p>Søknadsfrist: {SOON}</p>")
        facts = self.facts(careers_page(cards))
        self.assertEqual(facts.jobs, [])
        self.assertTrue(rejected_job(facts, "external_ad_employer_unverified"))

    def test_an_applicant_tracking_page_named_for_the_company_qualifies(self):
        cards = card("Markedsfører", "https://fjelldata.teamtailor.com/jobs/123-markedsforer", f"<p>Søknadsfrist: {SOON}</p>")
        self.assertEqual([job["title"] for job in self.facts(careers_page(cards)).jobs], ["Markedsfører"])
        named = card("Markedsfører", "https://www.finn.no/job/ad/481000002", f"<p>Arbeidsgiver: Fjell Data AS</p><p>Søknadsfrist: {SOON}</p>")
        self.assertEqual([job["title"] for job in self.facts(careers_page(named)).jobs], ["Markedsfører"])

    def test_several_unlinked_postings_on_one_page_are_not_individual_advertisements(self):
        import json as _json
        node = lambda title: f'<script type="application/ld+json">{_json.dumps({"@type": "JobPosting", "title": title, "validThrough": (TODAY + timedelta(days=20)).isoformat()})}</script>'
        facts = self.facts(page(SITE + "om-oss/", f"<html><body>{node('Driftstekniker')}{node('Selger')}<p>Driftstekniker Selger</p></body></html>"))
        self.assertEqual(facts.jobs, [])
        self.assertTrue(rejected_job(facts, "no_individual_advertisement_url"))

    def test_a_job_board_for_other_employers_is_not_the_companys_careers_page(self):
        from norway_company_agent.site_research import SiteResult, apply_site_facts
        cards = (card("Fundraiser, Norges Røde Kors", "https://www.finn.no/job/ad/479282780", f"<p>Søknadsfrist: {SOON}</p>")
                 + card("Innsamlingsansvarlig, Caritas Norge", "https://www.finn.no/job/ad/479635547", f"<p>Søknadsfrist: {SOON}</p>"))
        board = careers_page(cards)
        facts = self.facts(board)
        self.assertEqual(facts.careers_checked[0]["other_employer_positions"], 2)
        result = SiteResult(status="verified")
        result.careers_page = board.url
        apply_site_facts(result, facts, self.FJELL, [HOME, board])
        self.assertIsNone(result.careers_page)
        self.assertIn("careers:job_board_for_other_employers", result.extraction_rejections)

    def test_the_crawler_follows_undated_positions_to_their_own_page(self):
        from test_site_research import FakeWeb, ORG, profile as research_profile
        from norway_company_agent.site_research import SiteSession, research_company_site
        base = "https://fjordtest.no"
        home = (f'<html><body><a href="/karriere/">Karriere</a><footer>Fjordtest Programvare AS · Org.nr {ORG[:3]} {ORG[3:6]} {ORG[6:]}</footer></body></html>').encode()
        careers = (f'<html><body><h1>Ledige stillinger</h1>{card("Utvikler", "/karriere/utvikler/")}</body></html>').encode()
        detail = f"<html><body><h1>Utvikler</h1><p>Søknadsfrist: {SOON}</p></body></html>".encode()
        web = FakeWeb({f"{base}/robots.txt": (200, b"User-agent: *\nAllow: /\n"), f"{base}/": (200, home), f"{base}/karriere/": (200, careers),
                       f"{base}/karriere/utvikler/": (200, detail)})
        result = research_company_site(research_profile(email="post@fjordtest.no"), SiteSession(web, resolver=lambda host: True))
        self.assertIn(f"{base}/karriere/utvikler/", web.calls)
        self.assertEqual([(job["title"], job["currency"]["state"]) for job in result.jobs], [("Utvikler", "open")])
        self.assertEqual(result.job_pages_fetched, 1)


def rejected_job(facts, code: str) -> bool:
    return f"job:{code}" in facts.rejections


# ---------- post-audit fixes (eval-r300 audit of the frozen candidate 44d0cd3) ----------

class PostAuditFixes(unittest.TestCase):
    MOELVEN_GROUP = {"navn": "Moelven Industrier ASA", "organisasjonsnummer": "910724008", "organisasjonsform": {"kode": "ASA"},
                     "children": [{"navn": "MOELVEN WOOD AS", "organisasjonsnummer": "941809030", "parentNavn": "Moelven Industrier ASA", "parentOrganisasjonsnummer": "910724008"},
                                  {"navn": "MOELVEN BIOENERGI AS", "organisasjonsnummer": "990041881", "parentNavn": "Moelven Industrier ASA", "parentOrganisasjonsnummer": "910724008"}]}

    def test_a_brand_shared_across_the_registry_group_is_not_one_members_account(self):
        moelven = profile("MOELVEN WOOD AS", "941809030", group=self.MOELVEN_GROUP)
        for url in ("https://www.linkedin.com/company/moelven/", "https://www.instagram.com/moelven/", "https://www.facebook.com/moelven"):
            with self.subTest(url=url):
                platform = next(p for p in ("linkedin", "instagram", "facebook") if p in url)
                self.assertEqual(owner_check(moelven, LegalName("MOELVEN WOOD AS"), platform, url, "https://www.moelven.com/").code, "group_shared_brand_handle")
        self.assertIsNone(owner_check(moelven, LegalName("MOELVEN WOOD AS"), "linkedin", "https://www.linkedin.com/company/moelven-wood/", "https://www.moelven.com/"))
        melbye = profile("MELBYE AS", "941009697", group={"navn": "MELBYE GROUP AS", "organisasjonsnummer": "999999999", "organisasjonsform": {"kode": "AS"},
                                                          "children": [{"navn": "MELBYE AS", "organisasjonsnummer": "941009697"}]})
        self.assertIsNone(owner_check(melbye, LegalName("MELBYE AS"), "linkedin", "https://www.linkedin.com/company/melbye", "https://melbye.no/"),
                          "a handle that is the company's full legal name stays its own")

    def test_a_suppliers_launch_on_a_distributors_site_is_not_the_distributors_news(self):
        posts = [("DPA lanserer 4097 CORE+ Micro Shotgun Microphone", SITE + "dpa-lanserer/", pub("Mon, 05 Oct 2026 10:00:00 +0000"), "Fjell Data er distributør for DPA i Norge."),
                 ("Fjell Data lanserer ny nettbutikk", SITE + "fjell-data-lanserer-nettbutikk/", pub("Tue, 06 Oct 2026 10:00:00 +0000"), "Fjell Data AS lanserer i dag.")]
        facts = extract_site_facts(profile("FJELL DATA AS"), [HOME], [feed(posts)], now=NOW)
        self.assertEqual(titles(facts), ["Fjell Data lanserer ny nettbutikk"])
        self.assertTrue(rejected(facts, "launch_not_by_the_company"))

    def test_an_announcement_without_its_own_article_url_is_not_published(self):
        listing = page(SITE + "nyheter", """<html><body><main>
            <div class="card"><h3>Fjell Data signerer avtale med Bergen kommune</h3><p>Publisert 2. oktober 2026</p>
            <p>Fjell Data AS har signert en treårig rammeavtale med Bergen kommune.</p></div></main></body></html>""")
        facts = extract_site_facts(profile("FJELL DATA AS"), [HOME, listing], now=NOW)
        self.assertEqual(facts.activities, [])
        self.assertTrue(rejected(facts, "no_individual_article_url"))

    def test_an_off_site_ad_whose_title_names_the_company_as_employer_qualifies(self):
        cards = card("Båtmekaniker og tekniker ved Fjell Data", "https://www.jobbnorge.no/ledige-stillinger/stilling/311738/batmekaniker", f"<p>Søknadsfrist: {SOON}</p>")
        facts = extract_site_facts(profile("FJELL DATA AS"), [HOME, careers_page(cards)], now=datetime.now(timezone.utc))
        self.assertEqual([job["title"] for job in facts.jobs], ["Båtmekaniker og tekniker ved Fjell Data"])


if __name__ == "__main__":
    unittest.main()
