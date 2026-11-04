"""V3 regression suite on captured bytes (tests/fixtures/v3/, captured 2026-11-01 from the baseline ff3b515).

Each defect test pins one reproduced Builderr-class error; each control test pins legitimate output that V3 must keep.
Fixtures replay the exact captured bytes through the real pipeline (tests/helpers/c12_replay.Fixture); no network."""
from __future__ import annotations

import sys
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.c12_replay import Fixture  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402

V3 = ROOT / "tests" / "fixtures" / "v3"


@lru_cache(maxsize=None)
def replay(org: str) -> dict:
    fixture = Fixture(org, base=V3)
    envelope = run_batch([InputRow(0, org, org)], run_id="v3-regression", **fixture.injected())["envelopes"][0]
    assert validate_envelope(envelope) == [], validate_envelope(envelope)
    return envelope


def available(org: str, field: str) -> list[dict]:
    return [claim for claim in replay(org)["claims"] if claim["field"] == field and claim["availability"] == "available"]


def profiles(org: str) -> set[str]:
    return {claim["value"] for claim in available(org, "social_profile")}


def news_urls(org: str) -> list[str]:
    return [claim["value"].get("url") for claim in available(org, "news_item")]


def news_titles(org: str) -> list[str]:
    return [claim["value"].get("title") for claim in available(org, "news_item")]


def careers(org: str) -> list[str]:
    return [claim["value"] for claim in available(org, "careers_page")]


class SocialAttribution(unittest.TestCase):
    def test_tyin_alpint_sister_company_profiles_are_not_published(self):
        """TYIN ALPINT AS (983181732): registry website tyinfilefjell.no states Tyin Filefjell AS 930182451 and
        Filefjellstuene AS 930182478, never 983181732. Baseline published Tyin Filefjell's LinkedIn/Facebook/Instagram."""
        self.assertEqual(profiles("983181732"), set())
        site = available("983181732", "official_website")
        self.assertEqual([claim["value"] for claim in site], ["https://www.tyinfilefjell.no/"], "the registry-linked website itself stays")
        self.assertEqual((site[0].get("operated_by") or {}).get("organisation_number"), "930182451")

    def test_bergknapp_keeps_its_own_profiles_but_not_grasrota(self):
        self.assertEqual(profiles("995596970"), {"https://www.facebook.com/bergknapp.no", "https://www.instagram.com/bergknapp.no/", "https://www.linkedin.com/company/bergknapp-as"})

    def test_bartec_group_profiles_are_not_the_norwegian_subsidiary(self):
        self.assertEqual(profiles("980932834"), set())

    def test_biomar_group_channel_held_norway_profiles_kept(self):
        found = profiles("937843860")
        self.assertNotIn("https://www.youtube.com/@BioMarGroup", found)
        self.assertEqual(found, {"https://www.facebook.com/BiomarNorge/", "https://www.instagram.com/biomarnorge/", "https://www.linkedin.com/company/biomar-norge/"})

    def test_a_handle_spelling_another_legal_name_is_held(self):
        self.assertEqual(profiles("980995151"), {"http://www.facebook.com/bdtviken"})

    def test_asak_does_not_take_the_profiles_of_asak_miljostein(self):
        """ASAK AS (961592097) and ASAK MILJØSTEIN AS (980281310) share asak.no; the site names "Asak Miljøstein AS"."""
        self.assertEqual(profiles("961592097"), set())
        held = [claim for claim in replay("961592097")["claims"] if claim["field"] == "social_profile"]
        self.assertEqual([claim["availability"] for claim in held], ["ambiguous"])
        self.assertEqual(profiles("980281310"), {"https://www.facebook.com/asakmiljostein", "https://www.instagram.com/asak_miljostein/"},
                         "the profiles stay attributed to the company they name")

    def test_ashtead_norwegian_as_does_not_take_the_global_linkedin(self):
        """ASHTEAD TECHNOLOGY AS (995284766): the registry website is a page of the global group's ashtead-technology.com."""
        self.assertEqual(profiles("995284766"), set())

    def test_controls_keep_their_profiles(self):
        self.assertEqual(profiles("919378875"), {"http://www.facebook.com/gronsand", "https://instagram.com/gronsandgjestagard"})
        self.assertEqual(profiles("936269044"), {"https://www.facebook.com/Birralee/", "https://www.instagram.com/birralee_internationalschool/"})
        # Remediation pass: @beredtinkludering is BEREDT INKLUDERING AS (934470222), a separate registered company that
        # beredt.no itself names ("Beredt AS og Beredt Inkludering AS – to selskaper"). It was labelled "own sub-brand" in
        # the dev audit; that label was wrong and is corrected in measurements/v3-remediation-2026-11-01/.
        self.assertEqual(profiles("916303122"), {"https://www.facebook.com/BeredtAS", "https://www.linkedin.com/company/beredt/"})
        self.assertEqual(len(profiles("975387011")), 2)
        self.assertEqual(profiles("984560443"), {"https://www.facebook.com/Bjelland-As-359873177420058/"})
        self.assertEqual(len(profiles("993231150")), 2)
        self.assertEqual(len(profiles("995159406")), 2)
        self.assertEqual(len(profiles("995726742")), 2)


class NewsClassification(unittest.TestCase):
    def test_bulk_imported_project_posts_are_not_news(self):
        self.assertEqual(news_urls("995159406"), [], "BK Bygg: 10 reference projects posted within 3 minutes")
        self.assertEqual(news_urls("993231150"), [], "Bergen Rørteknikk: project posts, building-type category, one burst")

    def test_default_cms_post_is_not_news(self):
        self.assertEqual(news_urls("980995151"), [])
        self.assertEqual(news_urls("933164896"), [])

    def test_contact_page_and_image_file_are_not_news(self):
        urls = news_urls("975387011")
        self.assertFalse([url for url in urls if url.endswith(".jpg") or "pressekontakter" in url], urls)

    def test_portfolio_project_and_archive_urls_are_not_news_items(self):
        for url in news_urls("984560443") + news_urls("995596970"):
            self.assertNotRegex(url, r"/(portfolio-item|prosjekter|category)/")
        self.assertEqual(news_urls("995596970"), [])

    def test_group_magazine_is_not_the_subsidiary_s_news(self):
        self.assertEqual(news_urls("980932834"), [])

    def test_sister_regional_companies_news_is_not_published(self):
        titles = news_titles("996605833")
        self.assertLessEqual(len(titles), 1)
        for title in titles:
            self.assertIn("Forskningsparken", title, "only the item the group feed tags 'Betonmast Oslo'")

    def test_a_news_listing_page_is_not_an_item(self):
        self.assertNotIn("Siste nytt · Beredt AS", news_titles("916303122"))

    def test_controls_keep_their_news(self):
        """V3.1 counts. Every published item must now be anchored to the company by its own words (it names the company,
        speaks in its voice or states a company development; docs/v31-news-analysis.md §6). Items whose captured text
        does neither are withheld as not_anchored_to_the_company, and these controls lose exactly those:
        Birralee 20 -> 18 ("From Seeds to Science…", "Stage, Story and Study…": class reports that never name the school
        or say "we"), Grønsand 15 -> 14 ("Julaften alene sammen": a two-sentence teaser), Beredt 6 -> 5 ("Når kan
        Ekspertbistand være aktuelt?": an explainer of a public scheme). Kilis keeps all 10 plain-slug WordPress posts."""
        self.assertEqual(len(news_urls("875606662")), 10, "Kilis Hockey plain-slug WordPress posts")
        self.assertEqual(len(news_urls("936269044")), 18, "Birralee posts")
        self.assertEqual(len(news_urls("919378875")), 14, "Grønsand posts")
        self.assertEqual(len(news_urls("916303122")), 5, "Beredt's own articles")
        self.assertIn("“Hopp i det” - gir ungdom en ny sjanse.", news_titles("916303122"), "names the company in the genitive (Beredts)")
        self.assertIn("Verdensdagen for psykisk helse", news_titles("875606662"), "addresses the reader but reports the club's own event (inviterer vi)")
        for org in ("875606662", "936269044", "919378875", "916303122"):
            for claim in available(org, "news_item"):
                self.assertTrue((claim.get("attribution") or {}).get("basis"), f"{org}: every published item states why it qualifies")

    def test_withheld_news_is_never_reported_as_none_found(self):
        reason = next(claim["reason"] for claim in replay("980932834")["claims"] if claim["field"] == "news_item")
        self.assertIn("dated candidate entries were withheld", reason)
        self.assertIn("item not about entity on group or brand site: 31", reason)

    def test_911771098_blog_control(self):
        """The WordPress case (C300 fixture, captured 2026-10-17): 20 posts at ff3b515. "Du store verden" was lost to the
        blanket second-person title rule (6efd3cd), kept by the context-aware rule (remediation R6), and under V3.1 is kept
        because its own text reports a development in the author's voice ("…oversettes…"). V3.1 withholds the four
        homepage cards whose captured text is only a book title and an excerpt ("Navnebringeren", "Operasjon Radius",
        "Operasjon Mumie", "Skisser og ferdige sider til «Operasjon Plastpose»"): nothing in it says they are the
        company's news, so they are withheld rather than guessed."""
        from helpers.c12_replay import C300_FIXTURES
        envelope = run_batch([InputRow(0, "911771098", "911771098")], run_id="v3-regression", **Fixture("911771098", base=C300_FIXTURES).injected())["envelopes"][0]
        titles = [claim["value"].get("title") for claim in envelope["claims"] if claim["field"] == "news_item" and claim["availability"] == "available"]
        self.assertEqual(len(titles), 16)
        self.assertIn("Du store verden", titles)
        du = next(claim for claim in envelope["claims"] if claim["field"] == "news_item" and (claim.get("value") or {}).get("title") == "Du store verden")
        self.assertEqual(du["attribution"]["code"], "development")
        for title in ("Navnebringeren", "Operasjon Radius", "Operasjon Mumie"):
            self.assertNotIn(title, titles)


class V31NewsContent(unittest.TestCase):
    """V3.1: the eval120 independent news errors (docs/v31-news-analysis.md §1), replayed from the bytes captured by
    the baseline ff3b515 on 2026-11-01. Each was published by V3 candidate 2; each is now withheld by what its own
    text says, or by whose site it is on."""

    def withheld(self, org: str) -> str:
        return next(claim.get("reason") or "" for claim in replay(org)["claims"] if claim["field"] == "news_item" and claim["availability"] != "available") \
            if not available(org, "news_item") else ""

    def test_property_and_plot_listings_are_not_news(self):
        """911711664 Huspro: blog posts presenting plots and houses for sale (category A1)."""
        titles = news_titles("911711664")
        for title in ("Fra oven, Holaker", "Holaker, Maura - flott eneboligtomt", "Hurdal, Brustadsletta", "Storslått Villa!",
                      "Enebolig med fokus på bærekraft og miljø sentralt i Maura"):
            self.assertNotIn(title, titles)
        self.assertEqual(news_titles("998355389"), [], "998355389 Kystsnekker'n: a completed job shown as a reference")
        self.assertIn("content listing", self.withheld("998355389"))

    def test_reader_advice_and_listicles_are_not_news(self):
        """921774087 Oslo PT (opts), 985095779 Nordic Solutions, 924782544 Takstmannen, 998263743 Sjokoladesmaking (A2, D)."""
        titles = news_titles("921774087")
        for title in ("Bekymrer du deg mer nå enn før du ble gravid?", "Hvorfor matjournal kan være det viktigste verktøyet du ikke bruker",
                      "Markløft: Den ultimative øvelsen for styrke og funksjonalitet", "Treningsdagbok er forskjellen på å trene og faktisk få resultater"):
            self.assertNotIn(title, titles)
        self.assertEqual(news_titles("985095779"), [])
        self.assertIn("content advice: 3", self.withheld("985095779"))
        self.assertNotIn("Avhendingsloven - tryggere bolighandel", news_titles("924782544"))
        self.assertNotIn("Ikke tygg sjokoladen", news_titles("998263743"))
        self.assertIn("Vi legger ned nettbutikken", news_titles("998263743"), "the company's own announcement stays")

    def test_service_pages_in_a_blog_are_not_news(self):
        """848720712 SOBBL: "Melde skade?" and "Bli Medlem" are standing service pages (A4)."""
        self.assertEqual(news_titles("848720712"), [])
        self.assertIn("content service", self.withheld("848720712"))

    def test_promotional_posts_that_never_anchor_to_the_company_are_withheld(self):
        """927176963 Day of Week: thought-leadership posts that neither name the company nor speak in its voice (A3)."""
        self.assertEqual(news_titles("927176963"), [])
        self.assertIn("not anchored to the company", self.withheld("927176963"))

    def test_cms_course_page_in_the_feed_is_not_news(self):
        """974683296 FFOR: "Akvakurs 2026" is a course booking page carried by the feed (C)."""
        self.assertNotIn("Akvakurs 2026", news_titles("974683296"))

    def test_job_advertisement_in_the_feed_is_careers_content(self):
        """996902161 Sabi Sushi (diag80): a job ad in the WordPress feed is not news; the restaurant openings stay."""
        titles = news_titles("996902161")
        self.assertNotIn("Restaurantsjef | Sabi Sushi Bodø", titles)
        self.assertIn("Sabi Sushi åpner på Kokstad i 2026", titles)

    def test_site_named_after_the_registry_parent(self):
        """990892687 BE KRAFTSALG AS: bodoenergi.no states BE Kraftsalg's own org. number but carries the name of its
        registry parent BODØ ENERGI AS (890892612). Stories and profiles under "Bodø Energi" may be either company's:
        none names BE Kraftsalg, so none is attributed (5 news errors and 3 social errors in eval120, category B)."""
        self.assertEqual(news_titles("990892687"), [])
        self.assertIn("item not about entity on group or brand site", self.withheld("990892687"))
        self.assertEqual(profiles("990892687"), set())
        self.assertEqual([claim["value"] for claim in available("990892687", "official_website")], ["https://bodoenergi.no/"],
                         "the website itself is still the company's")

    def test_every_published_item_says_why_it_qualifies(self):
        for org in ("911711664", "921774087", "974683296", "996902161", "998263743"):
            for claim in available(org, "news_item"):
                attribution = claim.get("attribution") or {}
                self.assertIn(attribution.get("code"), ("development", "company_named", "company_voice"), (org, claim["value"]))
                self.assertTrue(attribution.get("basis") and attribution.get("source_tier"), (org, claim["value"]))


V31LIVE = ROOT / "tests" / "fixtures" / "v31live"


class V31AfterEval200(unittest.TestCase):
    """Failures found after the first V3.1 freeze (8223a37): on eval200 (scored once on 8223a37, then used for
    development) and in its live release run. Captured bytes: eval200 through the baseline ff3b515 (2026-11-01);
    BE Kraftsalg through 8223a37 live (2026-11-02). Each published on 8223a37; the controls must keep their news."""

    def test_product_and_rental_item_pages_are_not_news(self):
        """912158845 Steinkjer Liftutleie: ten lift pages in the WordPress feed ("Pris på forespørsel … Ring oss")."""
        self.assertEqual(news_titles("912158845"), [])
        self.assertIn("content product", V31NewsContent.withheld(self, "912158845"))

    def test_job_advertisements_in_more_phrasings(self):
        """889169672 Vårtun ("Vi søker tilkallingsvikarer!", "Er du Vårtuns nye rektor?"); 830872752 Logscom (Swedish)."""
        self.assertEqual(news_titles("889169672"), [])
        self.assertEqual(news_titles("830872752"), [])

    def test_feed_boilerplate_does_not_name_the_company(self):
        """966732024 Lugn: "Hei, verden!" named the company only in "The post … appeared first on Lugn Hytter"."""
        self.assertEqual(news_titles("966732024"), [])

    def test_marketing_and_advice_in_the_company_s_voice(self):
        """996217647 Frankeringsrekvisita (product marketing), 913441206 Sola Hundesenter and 899115562 Provendo (advice)."""
        self.assertLessEqual(len(news_titles("996217647")), 1)
        self.assertEqual(news_titles("913441206"), [])
        titles = news_titles("899115562")
        for title in ("Hvorfor ny PC?", "Hvorfor digitalt vedlikehold av PC er viktig"):
            self.assertNotIn(title, titles)
        self.assertIn("Provendo lanserer blogg", titles, "the company's own announcement stays")

    def test_site_wide_footer_does_not_name_the_company(self):
        """990892687 BE Kraftsalg, live run of 8223a37: each article page's footer "BE Kraftsalg AS · Org.nr. 990 892 687"
        made the Bodø Energi stories "name" the company on its group-brand site ("Bodø Bunkermuseum får Bodø
        Energi-gaven", "Stafett for livet på Fauske mottok Bodø Energi-gaven")."""
        envelope = run_batch([InputRow(0, "990892687", "990892687")], run_id="v3-regression", **Fixture("990892687", base=V31LIVE).injected())["envelopes"][0]
        titles = [claim["value"].get("title") for claim in envelope["claims"] if claim["field"] == "news_item" and claim["availability"] == "available"]
        self.assertNotIn("Bodø Bunkermuseum får Bodø Energi-gaven", titles)
        self.assertFalse([title for title in titles if "Bodø Energi-gaven" in title], titles)

    def test_eval200_controls_keep_their_news(self):
        """Organisations whose eval200 news was labelled correct keep it (on 8223a37 Jentene på Tunet also published
        "Vertinnegaven som blir lagt merke til …", gift advice labelled incorrect, which is now withheld)."""
        self.assertEqual(len(news_urls("994642340")), 9, "Proba: new projects, reports, a new employee")
        self.assertEqual(len(news_urls("971348496")), 10, "IKA Hordaland: conferences, governance meetings, a new collaboration")
        self.assertEqual(len(news_urls("976756118")), 8, "Steinerskolen i Ås: the weekly newsletter")
        self.assertEqual(len(news_urls("920546919")), 8, "Jentene på Tunet: awards, nominations, festival anniversary")


@lru_cache(maxsize=None)
def site_research(org: str) -> dict:
    fixture = Fixture(org, base=V3)
    profile = run_batch([InputRow(0, org, org)], run_id="v3-regression", **fixture.injected())["profiles"][0]
    return ((profile.get("evidence") or {}).get("site_research") or {}).get("value") or {}


def held_social(org: str) -> dict[str, str]:
    return {entry["key"]: entry["code"] for entry in site_research(org).get("rejected_keys") or [] if entry["family"] == "social"}


class SharedNameAcrossBorders(unittest.TestCase):
    """Separately registered companies that share a name (eval200, fixtures captured 2026-11-01 through ff3b515).

    LOGSCOM AS (830872752, Lillehammer, 2022) sells "det svenske morselskapets produkter". Its registry website
    logscom.com is Logscom AB's site ("We make logs communicate - Logscom AB", contact "Logscom AB Blåviksvägen 11
    SE-91931 Åsele Sweden") and never names Logscom AS or 830872752; Brreg has no group record for a foreign parent.
    0e4c426 judged the site the company's own (no contrary signal) and published facebook.com/logscom and
    instagram.com/logscom_ab as the Norwegian company's profiles (both labelled incorrect in the eval200 audit)."""

    def test_logscom_as_does_not_take_the_swedish_logscom_ab_profiles(self):
        self.assertEqual(profiles("830872752"), set())
        operator = site_research("830872752")["operator"]
        self.assertEqual((operator["kind"], operator["code"]), ("group_or_brand", "site_of_a_foreign_namesake"))
        held = held_social("830872752")
        self.assertEqual(held.get("https://facebook.com/logscom"), "group_name_handle_on_group_or_brand_site", "the bare shared name")
        self.assertEqual(held.get("https://instagram.com/logscom_ab"), "handle_names_other_entity", "'ab' is the Swedish company's legal form")
        site = available("830872752", "official_website")
        self.assertEqual([claim["value"] for claim in site], ["https://logscom.com/"], "the registry-linked website itself stays")
        self.assertEqual(site[0].get("site_role"), "group_or_brand_site")
        self.assertEqual(news_titles("830872752"), [])

    def test_a_nuf_keeps_the_profiles_of_its_own_name(self):
        """KAMEO INVESTMENT PLATFORM AB NUF (932468352, eval200): the Norwegian branch of the Swedish AB. Its site states
        its own organisation number; kameo-norge / kameo.norge / KameoNorge were labelled correct."""
        self.assertEqual(site_research("932468352")["operator"]["kind"], "self")
        self.assertEqual(profiles("932468352"), {"https://www.facebook.com/KameoNorge", "https://www.instagram.com/kameo.norge/?hl=en",
                                                 "https://www.linkedin.com/company/kameo-norge"})

    def test_alpha_solutions_norge_keeps_its_earlier_decision(self):
        """ALPHA SOLUTIONS NORGE AS (921147325, eval200b): the registry website redirects into the international group's
        site, which links the US company's profiles (alpha-solutions-usa, alpha_solutions_us: labelled incorrect).
        The namesake rule does not apply (no foreign legal form follows the name) and nothing changes."""
        operator = site_research("921147325")["operator"]
        self.assertEqual((operator["kind"], operator["code"]), ("group_or_brand", "registry_website_redirects_to_other_domain"))
        self.assertEqual(profiles("921147325"), set())
        held = held_social("921147325")
        self.assertIn("https://linkedin.com/company/alpha-solutions-usa", held)


class CareersPages(unittest.TestCase):
    def test_service_pages_are_not_careers_pages(self):
        self.assertEqual(careers("933164896"), [], "/for-bedrifter/ is a staffing agency's service page")
        self.assertEqual(careers("916303122"), [], "/arbeidsgivere/unge-i-praksis/ is a service page for employers")

    def test_careers_page_of_a_site_run_by_another_company_is_held(self):
        self.assertEqual(careers("983181732"), [])

    def test_controls_keep_their_careers_pages(self):
        self.assertEqual(careers("936269044"), ["https://www.birralee.no/careers"])
        self.assertEqual(careers("984560443"), ["https://www.bjelland-as.no/jobbe-hos-oss/"])
        # Phase 4 dev audit: a recruiter's vacancies page lists its clients' jobs, not working at the recruiter.
        self.assertEqual(careers("995726742"), [])


if __name__ == "__main__":
    unittest.main()
