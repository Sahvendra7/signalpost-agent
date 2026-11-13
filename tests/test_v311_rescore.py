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


if __name__ == "__main__":
    unittest.main()
