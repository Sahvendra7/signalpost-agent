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

    def test_controls_keep_their_profiles(self):
        self.assertEqual(profiles("919378875"), {"http://www.facebook.com/gronsand", "https://instagram.com/gronsandgjestagard"})
        self.assertEqual(profiles("936269044"), {"https://www.facebook.com/Birralee/", "https://www.instagram.com/birralee_internationalschool/"})
        self.assertEqual(profiles("916303122"), {"https://www.facebook.com/BeredtAS", "https://www.instagram.com/beredtinkludering/", "https://www.linkedin.com/company/beredt/"})
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
        self.assertEqual(len(news_urls("875606662")), 10, "Kilis Hockey plain-slug WordPress posts")
        self.assertEqual(len(news_urls("936269044")), 20, "Birralee posts")
        self.assertEqual(len(news_urls("919378875")), 15, "Grønsand posts")
        self.assertGreaterEqual(len(news_urls("916303122")), 6, "Beredt's own articles")

    def test_911771098_blog_control(self):
        """The WordPress case (C300 fixture, captured 2026-10-17): 20 posts at ff3b515. One, "Du store verden", is withheld
        by the second-person title rule added in 6efd3cd (a known, logged false negative: in the labelled audits that
        clause removed 10 incorrect news items and 3 correct ones). Any further loss fails here."""
        from helpers.c12_replay import C300_FIXTURES
        envelope = run_batch([InputRow(0, "911771098", "911771098")], run_id="v3-regression", **Fixture("911771098", base=C300_FIXTURES).injected())["envelopes"][0]
        titles = [claim["value"].get("title") for claim in envelope["claims"] if claim["field"] == "news_item" and claim["availability"] == "available"]
        self.assertEqual(len(titles), 19)
        self.assertNotIn("Du store verden", titles)


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
