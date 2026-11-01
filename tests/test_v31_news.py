"""V3.1 news content layer (docs/v31-news-analysis.md §6): source tier, content assessment, company anchoring, the
policy decision and the registry-group site rule. Each case is a pattern from the 29 eval120 errors or a positive
control that must keep its news."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.attribution.names import LegalName  # noqa: E402
from norway_company_agent.attribution.news import (POLICIES, ContentAssessment, assess_content, company_names, mentions_company,  # noqa: E402
                                                   news_policy_decision, source_tier, voiced_development)
from norway_company_agent.attribution.operator import assess_operator, registry_group_company_named_by, registry_group_names  # noqa: E402


def kind(title: str, body: str = "", names_company: bool = False, names: list[str] | None = None) -> str:
    return assess_content(title, body, names_company=names_company, names=names).kind


class SourceTier(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(source_tier("https://x.no/nyheter/ny-avtale"), "newsroom")
        self.assertEqual(source_tier("https://x.no/ny-avtale", "https://x.no/aktuelt/"), "newsroom")
        self.assertEqual(source_tier("https://x.no/blogg/tips"), "blog")
        self.assertEqual(source_tier("https://x.no/ny-avtale/", "", "https://x.no/blog/feed/"), "blog")
        self.assertEqual(source_tier("https://x.no/ny-avtale/"), "post")


class ContentKinds(unittest.TestCase):
    def test_listing_of_a_plot_or_house_for_sale(self):
        # 911711664 Huspro (A1)
        self.assertEqual(kind("Holaker, Maura - flott eneboligtomt", "Tomten er byggeklar, 850 kvm. Meld interesse."), "listing")

    def test_advice_titles_listicles_and_reader_addressing_bodies(self):
        # 921774087 opts, 985095779 Nordic Solutions (A2)
        self.assertEqual(kind("Hvorfor matjournal kan være det viktigste verktøyet du ikke bruker",
                              "Har du lurt på hvor mange kalorier du spiser? Med en matjournal ser du det svart på hvitt."), "advice")
        self.assertEqual(kind("Hvorfor matjournal kan være det viktigste verktøyet du ikke bruker"), "insufficient",
                         "a title alone is not advice by the title rules, but it is still withheld: nothing anchors it to the company")
        self.assertEqual(kind("Mobilsikkerhet for bedrifter – 8 tiltak"), "advice")
        body = "Har du vondt i ryggen? Da bør du trene. Du kan starte med lette øvelser, og du må huske å strekke ut. Gjør dette hver dag."
        self.assertEqual(kind("Markløft", body), "advice")

    def test_service_pages(self):
        # 848720712 SOBBL (A4)
        self.assertEqual(kind("Melde skade?", "Fyll ut skademeldingsskjema på Min side."), "service")
        self.assertEqual(kind("Bli Medlem", "Bli medlem i dag og få forkjøpsrett."), "service")

    def test_job_advertisement(self):
        # 996902161 Sabi Sushi: "Vi ansetter på personlighet … Send søknad og CV"
        self.assertEqual(kind("Restaurantsjef", "Vi ansetter på personlighet. Er dette deg? Send søknad og CV til oss."), "recruitment")
        self.assertEqual(kind("Vi har ansatt ny daglig leder", "Kari begynner 1. mars. Vi søker også flere selgere."), "development",
                         "a hire stated in the title is news even when the text also recruits")

    def test_development_requires_an_anchor(self):
        self.assertEqual(kind("Ny avtale med Statens vegvesen"), "development", "a development stated in the title")
        self.assertEqual(kind("Sommeravslutning", "Vi arrangerer sommeravslutning for alle kunder fredag."), "development")
        self.assertEqual(kind("Delivery-first development for the agentic era", "Software teams ship faster with agents."), "insufficient")

    def test_company_named_and_company_voice(self):
        self.assertEqual(kind("Sesongkort 26/27", "Kongsvinger IL Ishockey selger sesongkort fra mandag.", names=["kongsvinger il"]), "company_named")
        self.assertEqual(kind("Krypto – Ned i dypet", "Min nye tegneserie kommer i april."), "company_voice")

    def test_a_reader_addressing_notice_of_the_company_s_own_event_is_not_advice(self):
        # 875606662 Kilis "Verdensdagen for psykisk helse": addresses the reader, but "inviterer vi til dobbel-kamp"
        body = ("Du kan ikke spille hockey alene. Du må stole på at noen dekker ryggen din. En som spør hvordan du har det. "
                "Sammen med Bilia Kongsvinger inviterer vi til dobbel-kamp mot Tromsø i helgen! Håper du vil bli med.")
        self.assertEqual(kind("Verdensdagen for psykisk helse", body), "development")
        self.assertIsNotNone(voiced_development("Sammen med Bilia inviterer vi til kamp"))
        self.assertIsNone(voiced_development("Bedrifter inviterer ofte til fest i desember"))

    def test_du_store_verden_is_kept_by_its_own_text(self):
        # 911771098 (remediation R6): the title addresses no one; the text reports a translation of the book
        self.assertEqual(kind("Du store verden", "Jeg er glad for å fortelle at «Det aller beste» oversettes til tysk og koreansk."), "development")

    def test_the_title_repeated_in_the_card_counts_once(self):
        self.assertNotEqual(kind("Du store verden", "Du store verden Lagt ut på 17/08/2018 Leave a comment on Du store verden"), "advice")


class CompanyNames(unittest.TestCase):
    def test_names_exclude_vague_words(self):
        names = company_names(LegalName("VIKEN PARK AS"), "vikenpark")
        self.assertIn("viken park", names)
        self.assertNotIn("viken", names, "a county is not the company's name")

    def test_a_domain_label_written_as_words_and_the_genitive(self):
        self.assertEqual(mentions_company("Velkommen til Viken Park i sommer", ["vikenpark"]), "vikenpark")
        self.assertEqual(mentions_company("«Hopp i det» er Beredts samarbeid med fylket", ["beredt"]), "beredt")
        self.assertIsNone(mentions_company("Beredskap i fylket", ["beredt"]))


class Policy(unittest.TestCase):
    def test_anchored_policy(self):
        dev = ContentAssessment("development", "x")
        self.assertIsNone(news_policy_decision("anchored", tier="post", content=dev, names_company=False))
        for negative in ("advice", "listing", "service", "recruitment"):
            decision = news_policy_decision("anchored", tier="newsroom", content=ContentAssessment(negative, "x"), names_company=True)
            self.assertEqual(decision.code, f"content_{negative}", "a news section never makes advice or a listing news")
        decision = news_policy_decision("anchored", tier="newsroom", content=ContentAssessment("insufficient", "x"), names_company=False)
        self.assertEqual(decision.code, "not_anchored_to_the_company", "a dedicated news section is not enough on its own")

    def test_policy_in_use(self):
        import norway_company_agent.site_facts as site_facts
        self.assertEqual(site_facts.NEWS_POLICY, "anchored")
        self.assertIn(site_facts.NEWS_POLICY, POLICIES)


def be_kraftsalg() -> dict:
    return {"organisation_number": "990892687", "name": "BE KRAFTSALG AS",
            "evidence": {"group": {"status": "available", "value": {"organisasjonsnummer": "890892612", "navn": "BODØ ENERGI AS",
                                                                     "children": [{"organisasjonsnummer": "990892687", "navn": "BE KRAFTSALG AS"},
                                                                                  {"organisasjonsnummer": "912345674", "navn": "BE NETT AS"}]}}}}


class RegistryGroupSite(unittest.TestCase):
    def test_group_members_exclude_the_company_itself(self):
        self.assertEqual(registry_group_names(be_kraftsalg()), [("890892612", "BODØ ENERGI AS"), ("912345674", "BE NETT AS")])

    def test_a_site_named_after_the_parent_is_a_group_or_brand_site_even_with_the_own_org_number(self):
        profile = be_kraftsalg()
        legal = LegalName("BE KRAFTSALG AS")
        self.assertEqual(registry_group_company_named_by("bodoenergi", profile, legal), ("890892612", "BODØ ENERGI AS"))
        operator = assess_operator(profile, "https://bodoenergi.no/", page_texts=[("https://bodoenergi.no/", "BE Kraftsalg AS · Org.nr. 990 892 687")], legal=legal)
        self.assertEqual((operator.kind, operator.code), ("group_or_brand", "site_named_after_registry_group_company"))

    def test_a_site_named_after_the_company_itself_is_unaffected(self):
        profile = be_kraftsalg()
        legal = LegalName("BE KRAFTSALG AS")
        self.assertIsNone(registry_group_company_named_by("bekraftsalg", profile, legal))
        betonmast = {"organisation_number": "996605833", "name": "BETONMAST OSLO AS",
                     "evidence": {"group": {"status": "available", "value": {"organisasjonsnummer": "984504381", "navn": "BETONMAST AS"}}}}
        self.assertIsNone(registry_group_company_named_by("betonmast", betonmast, LegalName("BETONMAST OSLO AS")),
                          "a subsidiary carrying its own brand prefix is named after itself")

    def test_no_group_record_no_effect(self):
        self.assertIsNone(registry_group_company_named_by("bodoenergi", {"organisation_number": "990892687", "evidence": {}}, LegalName("BE KRAFTSALG AS")))


if __name__ == "__main__":
    unittest.main()
