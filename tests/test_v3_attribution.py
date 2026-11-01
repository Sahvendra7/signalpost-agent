"""V3 §B3–B5: handle relations, site operator and social decisions (pure functions)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.attribution.names import LegalName, handle_relation  # noqa: E402
from norway_company_agent.attribution.operator import assess_operator, sibling_names, stated_org_numbers  # noqa: E402
from norway_company_agent.attribution.social import decide_profile  # noqa: E402

TYIN = "983181732"


class HandleRelations(unittest.TestCase):
    CASES = [
        # (legal name, platform, url, expected kind) — every handle seen in the 2026-11-01 diagnosis plus edge cases
        ("TYIN ALPINT AS", "linkedin", "https://no.linkedin.com/company/tyin-filefjell-as", "OTHER_ENTITY"),
        ("TYIN ALPINT AS", "facebook", "https://www.facebook.com/tyinfilefjell", "EXTENDS"),
        ("TYIN ALPINT AS", "linkedin", "https://www.linkedin.com/company/tyin-alpint-as", "EXACT"),
        ("BERGKNAPP AS", "facebook", "https://www.facebook.com/bergknapp.no", "EXACT_NEUTRAL"),
        ("BERGKNAPP AS", "linkedin", "https://www.linkedin.com/company/bergknapp-as", "EXACT"),
        ("BERGKNAPP AS", "linkedin", "https://www.linkedin.com/company/grasrota-as", "OTHER_ENTITY"),
        ("BERGKNAPP AS", "facebook", "https://www.facebook.com/grasrota.net/", "UNRELATED"),
        ("BARTEC AS", "facebook", "https://www.facebook.com/bartecgroup1975", "OTHER_ENTITY"),
        ("BARTEC AS", "youtube", "https://www.youtube.com/@BARTECglobal", "OTHER_ENTITY"),
        ("BARTEC AS", "linkedin", "https://www.linkedin.com/company/bartec-company-1975/", "OTHER_ENTITY"),
        ("BARTEC AS", "instagram", "https://www.instagram.com/bartec.one/", "EXTENDS"),
        ("BIOMAR A.S.", "youtube", "https://www.youtube.com/@BioMarGroup", "OTHER_ENTITY"),
        ("BIOMAR A.S.", "instagram", "https://www.instagram.com/biomarnorge/", "EXACT_NEUTRAL"),
        ("BIOMAR A.S.", "linkedin", "https://www.linkedin.com/company/biomar-norge/", "EXACT_NEUTRAL"),
        ("BDT VIKEN AS", "linkedin", "https://www.linkedin.com/company/bdt-viken-revisjon-as", "OTHER_ENTITY"),
        ("BDT VIKEN AS", "facebook", "http://www.facebook.com/bdtviken", "EXACT"),
        ("BJELLAND AS", "facebook", "https://www.facebook.com/Bjelland-As-359873177420058/", "EXACT"),
        ("STIFTELSEN CRUX", "facebook", "https://www.facebook.com/stiftelsencrux/", "EXACT"),
        ("STIFTELSEN CRUX", "linkedin", "https://www.linkedin.com/company/stiftelsen-crux-hovedkontor/?follow", "EXACT_NEUTRAL"),
        ("GRØNSAND GJESTEGÅRD AS", "facebook", "http://www.facebook.com/gronsand", "BRAND"),
        ("GRØNSAND GJESTEGÅRD AS", "instagram", "https://instagram.com/gronsandgjestagard", "EXTENDS"),
        ("BIRRALEE INTERNATIONAL SCHOOL TRONDHEIM AS", "facebook", "https://www.facebook.com/Birralee/", "BRAND"),
        ("BIRRALEE INTERNATIONAL SCHOOL TRONDHEIM AS", "instagram", "https://www.instagram.com/birralee_internationalschool/", "BRAND"),
        ("BIRI TRAV AS", "facebook", "https://www.facebook.com/Biritravbane", "EXTENDS"),
        ("HANS JØRGEN SANDNES AS", "linkedin", "https://www.linkedin.com/company/wordpress", "UNRELATED"),
        ("HANSEN & SØNN AS", "linkedin", "https://www.linkedin.com/company/hansen-og-sonn-as", "EXACT"),
        ("BK BYGG AS", "instagram", "https://www.instagram.com/bk_bygg/", "EXACT"),
        ("SPIREN DESIGN AS", "youtube", "https://www.youtube.com/@spirendesignas4987", "EXACT_NEUTRAL"),
        ("EKSEMPEL AS", "youtube", "https://www.youtube.com/channel/UC7s9csuogbbixk5asknijyg", "UNRELATED"),
        ("BETONMAST OSLO AS", "facebook", "https://www.facebook.com/betonmast", "BRAND"),
        ("BETONMAST OSLO AS", "linkedin", "https://www.linkedin.com/company/betonmast-oslo-as", "EXACT"),
        # Phase 4 held-out audit: names that start with "AS", and acronym suffixes
        ("AS JACO", "facebook", "http://facebook.com/asjaco", "EXACT"),
        ("AS SOLREGN", "linkedin", "https://www.linkedin.com/company/as-solregn/", "EXACT"),
        ("AS BYGGANALYSE", "linkedin", "https://no.linkedin.com/company/as-bygganalyse", "EXACT"),
        ("AS INSTITUTT FOR PSYKOLOGISK RÅDGIVNING", "facebook", "https://www.facebook.com/Institutt-for-Psykologisk-R%C3%A5dgivning-IPR-279534205481478/", "EXACT_NEUTRAL"),
        ("ASAK AS", "facebook", "https://www.facebook.com/asakmiljostein", "EXTENDS"),
        # Phase 4 held-out 2: percent-encoded letters and single-letter initials
        ("GLOMMEN MJØSEN SKOG SA", "youtube", "https://www.youtube.com/@GlommenMj%C3%B8senSkog", "EXACT"),
        ("GRØNN JOBB AS", "linkedin", "https://no.linkedin.com/company/gr%C3%B8nn-jobb-as", "EXACT"),
        ("Alf I. Larsen A/S", "instagram", "https://www.instagram.com/alf.i.larsen.as/", "EXACT"),
        ("Alf I. Larsen A/S", "facebook", "https://www.facebook.com/Alf.I.Larsen.AS", "EXACT"),
    ]

    def test_relation_table(self):
        for name, platform, url, expected in self.CASES:
            with self.subTest(name=name, url=url):
                self.assertEqual(handle_relation(LegalName(name, "OSLO" if "OSLO" in name else None), platform, url).kind, expected)

    def test_domain_named(self):
        self.assertTrue(LegalName("GRØNSAND GJESTEGÅRD AS").domain_named("gronsand"))
        self.assertTrue(LegalName("BJELLAND AS").domain_named("bjelland-as"))
        self.assertTrue(LegalName("BDT VIKEN AS").domain_named("bdtviken"))
        self.assertFalse(LegalName("TYIN ALPINT AS").domain_named("tyinfilefjell"))
        self.assertTrue(LegalName("TYIN ALPINT AS").domain_related("tyinfilefjell"), "shares a distinctive token, so not 'unrelated'")
        self.assertTrue(LegalName("KONGSVINGER IL ISHOCKEY").domain_related("kilishockey"))


class SiteOperatorTests(unittest.TestCase):
    PROFILE = {"organisation_number": TYIN, "name": "TYIN ALPINT AS", "evidence": {"registry_live": {"value": {"business_address": {"kommune": "VANG", "poststed": "TYINKRYSSET"}}}}}

    def test_org_numbers_are_read_from_imprints_with_grouping_and_mod11(self):
        text = "Selskapsinformasjon Tyin Filefjell AS – org.nr. 930 182 451 Filefjellstuene AS – org.nr. 930 182 478 Telefon 61 36 80 00 NO 930182451MVA"
        self.assertEqual([number for number, _ in stated_org_numbers(text)], ["930182451", "930182478"])
        self.assertEqual(stated_org_numbers("Ring 930 182 452 for booking"), [], "no imprint cue, invalid checksum")
        self.assertEqual(stated_org_numbers("org.nr. 930 182 452"), [], "mod11 must pass")

    def test_other_entity_when_the_site_states_other_numbers_and_never_ours(self):
        op = assess_operator(self.PROFILE, "https://www.tyinfilefjell.no/", page_texts=[("https://www.tyinfilefjell.no/kontakt", "Tyin Filefjell AS – org.nr. 930 182 451")])
        self.assertEqual((op.kind, op.operator_org), ("other_entity", "930182451"))

    def test_a_holding_company_in_the_footer_does_not_override_our_own_number(self):
        text = "Eksempel Drift AS org.nr. 983 181 732 · eies av Eksempel Holding AS org.nr. 930 182 451"
        self.assertEqual(assess_operator(self.PROFILE, "https://eksempel.no/", page_texts=[("https://eksempel.no/", text)]).kind, "self")

    def test_redirect_to_another_domain_is_a_group_or_brand_site(self):
        profile = {"organisation_number": "980932834", "name": "BARTEC AS"}
        op = assess_operator(profile, "https://bartec.com/", page_texts=[("https://bartec.com/", "BARTEC worldwide")],
                             website_value={"requested_url": "https://www.bartec-technor.no/", "final_url": "https://bartec.com/"})
        self.assertEqual((op.kind, op.code), ("group_or_brand", "registry_website_redirects_to_other_domain"))

    def test_sibling_units_in_the_site_taxonomy(self):
        legal = LegalName("BETONMAST OSLO AS", "OSLO", "OSLO")
        self.assertEqual(sibling_names(legal, ["Betonmast Oslo", "Betonmast Trøndelag", "Betonmast Buskerud-Vestfold", "Boligbygg"]), {"betonmasttrondelag", "betonmastbuskerudvestfold"})
        self.assertEqual(sibling_names(LegalName("SPIREN DESIGN AS"), ["Spiren Nyheter", "Spiren Prosjekter"]), set(), "only BRAND + place names have siblings")

    def test_dealer_lists_and_vat_lookalikes_are_not_imprints(self):
        self.assertEqual(stated_org_numbers("Forhandler: NO AS 918512616 Agder Bil"), [], "'NO' counts only in the VAT form NO 123 456 789 MVA")
        self.assertEqual([n for n, _ in stated_org_numbers("Faktura: NO 930 182 451 MVA")], ["930182451"])
        profile = {"organisation_number": "911629283", "name": "AS FINANCIERING"}
        listing = "Org.nr. 918 512 616 · Org.nr. 917 692 491 · Org.nr. 921 221 568"
        op = assess_operator(profile, "https://www.financiering.no/", page_texts=[("https://www.financiering.no/kontakt-oss/forhandlere/", listing)])
        self.assertEqual(op.kind, "self", "a list of three or more companies is a directory, not who runs the site")

    def test_a_rename_to_another_norwegian_domain_is_not_a_group_site(self):
        profile = {"organisation_number": "911111111", "name": "AS STALHEIM HOTEL"}
        op = assess_operator(profile, "https://www.stalheimhotel.no/", page_texts=[("https://www.stalheimhotel.no/", "Stalheim Hotel")],
                             website_value={"requested_url": "https://www.stalheim.com/", "final_url": "https://www.stalheimhotel.no/"})
        self.assertEqual(op.kind, "self")

    def test_a_new_top_level_domain_is_not_another_company(self):
        profile = {"organisation_number": "912227111", "name": "AS HADELAND"}
        op = assess_operator(profile, "https://www.hadeland.no/", page_texts=[("https://www.hadeland.no/", "Avisen Hadeland")],
                             website_value={"requested_url": "https://www.hadeland.net/", "final_url": "https://www.hadeland.no/"})
        self.assertEqual(op.kind, "self")

    def test_plain_company_site_is_self(self):
        profile = {"organisation_number": "875606662", "name": "KONGSVINGER IL ISHOCKEY"}
        op = assess_operator(profile, "https://kilishockey.no/", page_texts=[("https://kilishockey.no/", "Velkommen til KIL Hockey")])
        self.assertEqual(op.kind, "self")

    def test_manager_and_platform_keep_their_earlier_rules(self):
        self.assertEqual(assess_operator(self.PROFILE, "https://x.no/", page_texts=[], identity_class="MANAGER_DESIGNATED").kind, "manager")
        self.assertEqual(assess_operator(self.PROFILE, "https://a.wordpress.com/", page_texts=[], shared_kind="platform").kind, "platform")


class SocialDecisions(unittest.TestCase):
    def decide(self, name, url, operator, **flags):
        legal = LegalName(name)
        platform = "linkedin" if "linkedin" in url else "facebook"
        defaults = {"domain_named": False, "handle_starts_with_domain": False, "org_sameas": False}
        return decide_profile(handle_relation(legal, platform, url), operator, **{**defaults, **flags})[0]

    def test_handle_equal_to_the_own_domain_name_on_a_self_run_site(self):
        relation = handle_relation(LegalName("AS RINGERIKES BLAD"), "facebook", "https://www.facebook.com/ringblad")
        self.assertTrue(decide_profile(relation, "self", domain_named=False, handle_starts_with_domain=True, org_sameas=False, handle_is_domain=True)[0].accepted)
        self.assertFalse(decide_profile(relation, "other_entity", domain_named=False, handle_starts_with_domain=True, org_sameas=False, handle_is_domain=True)[0].accepted)
        self.assertFalse(decide_profile(relation, "group_or_brand", domain_named=False, handle_starts_with_domain=True, org_sameas=False, handle_is_domain=True)[0].accepted)

    def test_decision_table(self):
        self.assertTrue(self.decide("BERGKNAPP AS", "https://linkedin.com/company/bergknapp-as", "group_or_brand").accepted)
        self.assertFalse(self.decide("BERGKNAPP AS", "https://linkedin.com/company/bergknapp-as", "other_entity").accepted)
        self.assertFalse(self.decide("BERGKNAPP AS", "https://facebook.com/grasrota.net", "self", domain_named=True, org_sameas=True).accepted, "sameAs never accepts an unrelated handle")
        self.assertTrue(self.decide("GRØNSAND GJESTEGÅRD AS", "https://facebook.com/gronsand", "self", domain_named=True).accepted)
        self.assertFalse(self.decide("GRØNSAND GJESTEGÅRD AS", "https://facebook.com/gronsand", "self").accepted, "a brand needs the company's own named domain")
        self.assertFalse(self.decide("BETONMAST OSLO AS", "https://facebook.com/betonmast", "group_or_brand", domain_named=True).accepted)
        self.assertFalse(self.decide("BIOMAR A.S.", "https://facebook.com/biomargroup", "self", domain_named=True, handle_starts_with_domain=True).accepted)
        self.assertTrue(self.decide("BIRI TRAV AS", "https://facebook.com/Biritravbane", "self", domain_named=True, handle_starts_with_domain=True).accepted)
        self.assertFalse(self.decide("BIRI TRAV AS", "https://facebook.com/Biritravbane", "section", domain_named=True, handle_starts_with_domain=True).accepted)


if __name__ == "__main__":
    unittest.main()



class SlugifiedLegalForm(unittest.TestCase):
    def test_a_slugified_a_s_is_a_legal_form(self):
        from norway_company_agent.attribution.names import LegalName, handle_relation
        legal = LegalName("BOARD COMPANY NORGE AS")
        self.assertEqual(handle_relation(legal, "linkedin", "https://www.linkedin.com/company/board-assure-a-s/").kind, "OTHER_ENTITY")
        self.assertEqual(handle_relation(LegalName("BOARD ASSURE AS"), "linkedin", "https://www.linkedin.com/company/board-assure-a-s/").kind, "EXACT")
