"""Adversarial entity-resolution cases: the gate must prefer missing over a wrong-company fact."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.identity import apply_website_identity_gate, assess_website_identity  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402


def profile(org: str, name: str, **site) -> dict:
    return {"organisation_number": org, "name": name, "evidence": {"website": {"status": "available", "value": site}}}


class AdversarialIdentityTests(unittest.TestCase):
    def test_similar_name_namesake_is_not_exact(self):
        # "Berg" is a token of the legal name; "Bergen" is a different word on another company's site.
        self.assertFalse(assess_website_identity(profile("923609016", "Berg Bygg AS", title="Bergen Bygg AS - totalentreprenør"))["publishable"])

    def test_brand_name_differing_from_legal_entity_abstains(self):
        self.assertFalse(assess_website_identity(profile("923609016", "Nordic Retail Holding AS", title="Kaffebrenneriet", main_text_excerpt="Kaffe og bakst i Oslo " * 10))["publishable"])

    def test_parent_site_with_parent_org_number_is_not_the_subsidiary(self):
        row = profile("914778271", "Fjordkraft Vest AS", title="Fjordkraft AS", identity_text_excerpt="Fjordkraft AS org.nr 976 944 801")
        self.assertFalse(assess_website_identity(row)["publishable"])

    def test_subsidiary_named_on_parent_contact_page_only_is_not_exact(self):
        row = profile("914778271", "Fjordkraft Vest AS", title="Fjordkraft konsern", pages=[{"title": "Kontakt", "main_text_excerpt": "Fjordkraft Vest AS, avdeling Bergen"}])
        self.assertFalse(assess_website_identity(row)["publishable"])

    def test_historical_name_on_stale_site_abstains(self):
        # The registry name changed; the site still shows only the former name.
        self.assertFalse(assess_website_identity(profile("923609016", "Havbris Eiendom AS", title="Solstrand Utleie AS", main_text_excerpt="Velkommen til Solstrand Utleie " * 5))["publishable"])

    def test_org_number_on_homepage_is_strongest_signal_even_when_brand_differs(self):
        row = profile("923609016", "Nordic Retail Holding AS", title="Kaffebrenneriet", identity_text_excerpt="Kaffebrenneriet drives av Nordic Retail Holding AS, org.nr. 923 609 016")
        assessment = assess_website_identity(row)
        self.assertTrue(assessment["publishable"])
        self.assertEqual(assessment["score"], 1.0)

    def test_parked_or_for_sale_domain_with_org_number_is_still_rejected(self):
        row = profile("923609016", "Berg Bygg AS", title="bergbygg.no is for sale | HugeDomains", identity_text_excerpt="923609016")
        self.assertFalse(assess_website_identity(row)["publishable"])

    def test_social_links_of_ambiguous_site_are_quarantined(self):
        base = {"organisation_number": "914778271", "name": "Fjordkraft Vest AS", "evidence": {}}
        site = evidence("website", "available", "registry_linked_company_website", "https://fjordkraft.no/", value={"title": "Fjordkraft AS", "social_links": [{"platform": "linkedin", "url": "https://linkedin.com/company/fjordkraft-vest"}]})
        gated = apply_website_identity_gate(base, site)
        self.assertEqual(gated["website"]["value"]["social_links"], [])
        self.assertEqual(gated["quarantined_social_links"], 1)

    def test_footer_org_number_is_captured_for_the_batch_gate(self):
        from bs4 import BeautifulSoup
        from norway_company_agent.website import identity_text

        html = "<html><body><main>Vi lager god kaffe.</main><footer>Kaffebrenneriet, org.nr. 923 609 016</footer></body></html>"
        excerpt = identity_text(BeautifulSoup(html, "lxml"))
        self.assertIn("923 609 016", excerpt)
        self.assertTrue(assess_website_identity(profile("923609016", "Nordic Retail Holding AS", title="Kaffebrenneriet", identity_text_excerpt=excerpt))["publishable"])

    def test_decision_registry_listed_site_with_superset_name_is_accepted(self):
        # Recorded decision: for a URL the registry itself lists for this org number, a page title that
        # contains every legal-name token plus extra words ("Service") is accepted. Discovered URLs
        # (not registry-listed) must not reuse this rule; they need the org number on the page.
        self.assertTrue(assess_website_identity(profile("923609016", "Hansen Elektro AS", title="Hansen Elektro Service AS"))["publishable"])


if __name__ == "__main__":
    unittest.main()
