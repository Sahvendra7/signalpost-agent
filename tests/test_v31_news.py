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
from norway_company_agent.attribution.news import (POLICIES, ContentAssessment, assess_content, company_names, mentions_company, strip_boilerplate,  # noqa: E402
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
        self.assertEqual(kind("Hvorfor matjournal kan være det viktigste verktøyet du ikke bruker"), "advice",
                         "a 'Hvorfor …' explainer title (V3.1, found on eval200)")
        self.assertNotEqual(kind("Hvorfor vi flytter til Bergen"), "advice", "the company explaining its own decision")
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


class FoundAfterEval200(unittest.TestCase):
    """Failures found on eval200 (scored once on 8223a37, then used for development) and in the 8223a37 live run."""

    def test_feed_boilerplate_does_not_name_the_company(self):
        # 966732024 Lugn: "The post Hei, verden! appeared first on Lugn Hytter." made a default post company_named
        body = "Velkommen til WordPress. Dette er ditt første innlegg. The post Hei, verden! appeared first on Lugn Hytter ."
        self.assertNotIn(kind("Hei, verden!", body, names=["lugn", "lugn hytter"]), ("company_named", "development"))
        self.assertEqual(strip_boilerplate("A. Innlegget X dukket først opp på Proba Samfunnsanalyse . B").split(), ["A.", "B"])

    def test_product_and_rental_pages_are_not_news(self):
        # 912158845 Steinkjer Liftutleie: ten lift pages in the feed, "Pris på forespørsel … Ring oss"
        self.assertEqual(kind("12m – Diesel – Snorkel S3370RT", "Pris på forespørsel Ta kontakt for tilgjengelighet. Ring oss: 918 84 233"), "product")

    def test_job_advertisements_in_more_phrasings(self):
        for title, body in [("Vi søker tilkallingsvikarer!", ""), ("Er du Vårtuns nye rektor?", ""),
                            ("Systemutvecklare sökes!", "Vi på Logscom söker efter en systemutvecklare. Sök senast 8 januari."),
                            ("Software developer", "Logscom is now hiring a software developer.")]:
            self.assertEqual(kind(title, body), "recruitment", title)
        self.assertNotEqual(kind("Vi søker å bli bedre", "Vi søker å forbedre tjenestene våre hver dag."), "recruitment")

    def test_a_development_must_be_attributed_to_the_company(self):
        # 996217647 / 899115562: event nouns in marketing text ("investering", "leveranse", "utvidet garanti")
        self.assertNotEqual(kind("TSC Etikettskrivere", "Investering i riktig teknologi gir effektivitet for alle bedrifter."), "development")
        self.assertEqual(kind("Ny avtale", "Proba har inngått avtale med KS.", names=["proba"]), "development")
        self.assertEqual(kind("5 gode grunner til å velge en Tesla leiebil"), "advice", "a listicle with an adjective")

    def test_sentences_do_not_break_at_abbreviations(self):
        text = "Barna leser våre bøker. «Detektivbyrå nr. 2» oversettes nå til 18 språk."
        self.assertIsNotNone(voiced_development(text))

    def test_strict_policy(self):
        voice = ContentAssessment("company_voice", "x")
        self.assertEqual(news_policy_decision("strict", tier="post", content=voice, names_company=False).code, "no_attributed_development")
        self.assertIsNone(news_policy_decision("strict", tier="newsroom", content=voice, names_company=False))
        self.assertIsNone(news_policy_decision("strict", tier="blog", content=ContentAssessment("development", "x"), names_company=False))


class SiteChrome(unittest.TestCase):
    def test_a_footer_byline_repeated_on_every_page_is_not_the_item_naming_the_company(self):
        # 990892687 BE Kraftsalg, live run of 8223a37: the article page's footer "BE Kraftsalg AS · Org.nr. 990 892 687"
        # made every Bodø Energi story "name" the company on its group-brand site.
        from norway_company_agent.site_facts import CapturedPage, item_names_entity, item_page_text, site_chrome
        footer = '<div class="byline"><span>© 2026 Bodø Energi Kraftsalg · BE Kraftsalg AS · Org.nr. 990 892 687</span></div>'
        def page(url, body):
            raw = f"<html><body><main>{body}</main>{footer}</body></html>".encode()
            return CapturedPage(url, raw, "x", "2026-11-02T08:00:00Z")
        home = page("https://bodoenergi.no/", "<h1>Strøm til folk i nord</h1>")
        article = page("https://bodoenergi.no/aktuelt/gaven", "<h1>Bodø Bunkermuseum får Bodø Energi-gaven</h1><p>Museet mottok gaven.</p>")
        chrome = site_chrome([home, article])
        self.assertNotIn("990 892 687", item_page_text(article, chrome))
        item = {"title": "Bodø Bunkermuseum får Bodø Energi-gaven", "url": article.url, "page_url": article.url}
        profile = {"organisation_number": "990892687", "name": "BE KRAFTSALG AS"}
        self.assertIsNone(item_names_entity(profile, item, {home.url: home, article.url: article}, chrome))
        self.assertIsNotNone(item_names_entity(profile, item, {home.url: home, article.url: article}), "without the chrome rule it would name it")
