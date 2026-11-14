"""V3.1.2 — coverage of registry-listed websites, without loosening exact-company attribution.

A diagnostic rerun of eval-r200c (200 organisations with a registry-listed website) published 61 websites; 51 reachable
registry-listed sites were held back for identity, and 25 were dropped because robots.txt could not be fetched over
the guessed https scheme. Each test pins one general rule that recovers a site the registry itself links, or one
case that must stay withheld. Names here are made-up shapes of the cases seen, not allowlisted companies; no network."""
from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent import website  # noqa: E402
from norway_company_agent.http import ByteFetch  # noqa: E402
from norway_company_agent.identity import assess_website_identity  # noqa: E402
from norway_company_agent.synthesis import company_summary  # noqa: E402

BODY = "Vi leverer tjenester til kunder i hele landet og har lang erfaring fra bransjen. " * 3
NOW = "2026-11-14T12:00:00Z"


def site(name: str, url: str, *, legal_form: str = "AS", owner: str | None = None, title: str = "Hjem", text: str = BODY, **value) -> dict:
    roles = [{"name": owner, "organisation_number": None, "role_code": "INNH", "inactive": False}] if owner else []
    return {
        "organisation_number": "987654321", "name": name, "legal_form": legal_form,
        "evidence": {
            "roles": {"status": "available", "value": {"roles": roles}},
            "website": {"status": "available", "source_url": url, "value": {"final_url": url, "title": title, "main_text_excerpt": text, **value}},
        },
    }


def publishable(row: dict) -> bool:
    return assess_website_identity(row)["publishable"]


class RegistryListedSiteIdentity(unittest.TestCase):
    def test_trailing_foreign_legal_form_is_not_part_of_the_name(self):
        # Registered "… AKTIEBOLAG", the site writes "… AB".
        row = site("NORDFJELL GEOFYSIK AKTIEBOLAG", "https://www.nordfjell.se/", legal_form="UTLA", title="Home - Nordfjell Geofysik AB")
        assessment = assess_website_identity(row)
        self.assertTrue(assessment["publishable"])
        self.assertIn("legal-form word aside", assessment["reasons"][0])
        self.assertTrue(publishable(site("MIN BESTE BOK APS", "https://www.minbestebok.dk/", legal_form="UTLA", title="Min Beste Bok - personlige barnebøker")))

    def test_trailing_form_rule_needs_the_whole_remaining_name(self):
        self.assertFalse(publishable(site("NORDFJELL GEOFYSIK AKTIEBOLAG", "https://www.geofysik.se/", legal_form="UTLA", title="Geofysik i Norden")))
        # One word left after the form: name similarity alone, not accepted by this rule.
        self.assertFalse(publishable(site("WALDEN INTERNATIONAL AG", "https://www.walden.com/", legal_form="UTLA", title="WALDEN", text="")))

    def test_domain_that_is_the_legal_name_written_together(self):
        assessment = assess_website_identity(site("PARALLELL FILMVERKSTED AS", "https://www.parallellfilmverksted.no/", title="Parallell", text="Hos Parallell filmverksted lager vi film. " + BODY))
        self.assertTrue(assessment["publishable"])
        self.assertIn("written together", assessment["reasons"][0])
        self.assertTrue(publishable(site("TRE GODE NABOER DA", "https://www.tre-gode-naboer.no/", legal_form="DA", title="Velkommen", text="Vi i Tre gode naboer hjelper hverandre. " + BODY)))
        # The page never writes the name: the domain alone is not enough.
        self.assertFalse(publishable(site("PARALLELL FILMVERKSTED AS", "https://www.parallellfilmverksted.no/", title="Parallell")))

    def test_exact_name_domain_needs_content_and_no_placeholder(self):
        url = "https://www.parallellfilmverksted.no/"
        self.assertFalse(publishable(site("PARALLELL FILMVERKSTED AS", url, title="Parallell", text="")))
        self.assertFalse(publishable(site("PARALLELL FILMVERKSTED AS", url, title="parallellfilmverksted.no is parked", text="This domain is parked free of charge. " * 5)))
        self.assertFalse(publishable(site("PARALLELL FILMVERKSTED AS", url, title="Site Maintenance", text="We are performing scheduled site maintenance and will be back soon. " * 3)))

    def test_part_of_the_name_in_the_domain_is_not_enough(self):
        # A holding or sister company pointing at the operating company's site: one name word in the domain.
        self.assertFalse(publishable(site("KJEMITEK CONSULTING AS", "https://www.kjemitek.no/", title="Kjemitek - Hjem")))
        self.assertFalse(publishable(site("T BAKKEN INVEST AS", "https://www.bakken.as/", title="Bakken")))
        self.assertFalse(publishable(site("BUTIKKDRIFT PAULSEN AS", "https://kioskkjeden.no/", title="Kioskkjeden - Forside")))

    def test_sole_proprietorship_trade_name_domain(self):
        row = site("MEDIKUS Ronny Hansen", "https://www.medikus.no/", legal_form="ENK", owner="Alf Ronny Hansen", title="Hjem | Medikus")
        assessment = assess_website_identity(row)
        self.assertTrue(assessment["publishable"])
        self.assertIn("trade name", assessment["reasons"][0])

    def test_sole_proprietorship_trade_name_rule_limits(self):
        # Not a sole proprietorship; no registered owner; an empty page; a profession word that is not the domain.
        self.assertFalse(publishable(site("MEDIKUS Ronny Hansen", "https://www.medikus.no/", legal_form="AS", owner="Alf Ronny Hansen", title="Hjem | Klinikken")))
        self.assertFalse(publishable(site("MEDIKUS Ronny Hansen", "https://www.medikus.no/", legal_form="ENK", title="Hjem | Klinikken")))
        self.assertFalse(publishable(site("FREMOVER CARLSEN", "https://www.fremover.no/", legal_form="ENK", owner="Johnny Carlsen", title="Hjem", text="")))
        self.assertFalse(publishable(site("ADVOKAT NINA LUNDE", "https://www.advokathuset.no/", legal_form="ENK", owner="Nina Lunde", title="Advokathuset",
                                          identity_text_excerpt="Advokathuset ble etablert i 2002. Advokat Per Olsen, advokat Kari Ås")))
        self.assertFalse(publishable(site("KIOSKDRIFT DINCER", "https://kioskkjeden.no/", legal_form="ENK", owner="Ali Dincer", title="Kioskkjeden - Hjem")))

    def test_sole_proprietorship_owner_name_site(self):
        # A portfolio site: the owner's name is the domain and the title; little other text.
        row = site("KARI BERGE KUNST", "https://kariberge.com/", legal_form="ENK", owner="Kari Berge", title="Kari Berge", text="")
        assessment = assess_website_identity(row)
        self.assertTrue(assessment["publishable"])
        self.assertIn("owner's name", assessment["reasons"][0])
        # The legal name carries the surname in the genitive.
        self.assertTrue(publishable(site("ULLA BENGTSSONS KUNSTNERSKAP", "https://www.ulla.no/", legal_form="ENK", owner="Ulla Bengtsson", title="Ulla Bengtsson", text="")))

    def test_owner_name_rule_needs_domain_and_stated_name(self):
        # The owner is only one of several people on a firm's site, whose domain is not the owner's name.
        self.assertFalse(publishable(site("ADVOKAT NINA LUNDE", "https://www.advokathuset.no/", legal_form="ENK", owner="Nina Lunde", title="Advokathuset",
                                          identity_text_excerpt="Våre medarbeidere: Nina Lunde, Per Olsen og Kari Ås")))
        # The domain carries the name but the page never states it (a parked or resold domain).
        self.assertFalse(publishable(site("KARI BERGE KUNST", "https://kariberge.com/", legal_form="ENK", owner="Kari Berge", title="kariberge.com is parked", text="")))
        self.assertFalse(publishable(site("KARI BERGE KUNST", "https://kariberge.com/", legal_form="ENK", owner="Kari Berge", title="Nettbutikk for sko", text=BODY)))

    def test_site_naming_another_company_with_a_shared_name_word_is_that_companys(self):
        # A practitioner's sole proprietorship points at the clinic it works in; the clinic is a limited company.
        clinic = site("NORDVIK FYSIKALSKE-SOLBERG", "https://www.nordvikfysikalske.no/", legal_form="ENK", owner="Bernt Solberg", title="Nordvik Fysikalske Institutt",
                      identity_text_excerpt="Postadresse: Nordvik Fysikalske Institutt AS PB 9024 6023 ÅLESUND")
        self.assertFalse(publishable(clinic))
        # The same site without another company named on it stays accepted (positive control).
        self.assertTrue(publishable(site("NORDVIK FYSIKALSKE-SOLBERG", "https://www.nordvikfysikalske.no/", legal_form="ENK", owner="Bernt Solberg", title="Nordvik Fysikalske")))  # title states the trade name
        # A proprietorship converted into a limited company; an owner-named site of the owner's company; a sister company.
        self.assertFalse(publishable(site("MEDIKUS Ronny Hansen", "https://www.medikus.no/", legal_form="ENK", owner="Alf Ronny Hansen", title="Hjem | Medikus", identity_text_excerpt="© Medikus AS")))
        self.assertFalse(publishable(site("KARI BERGE KUNST", "https://kariberge.com/", legal_form="ENK", owner="Kari Berge", title="Kari Berge", text="", identity_text_excerpt="Kari Berge Design AS, Oslo")))
        self.assertFalse(publishable(site("PARALLELL FILMVERKSTED AS", "https://www.parallellfilmverksted.no/", title="Parallell", identity_text_excerpt="Parallell Media AS")))
        # The entity's own name with its legal form is not another company.
        self.assertTrue(publishable(site("PARALLELL FILMVERKSTED AS", "https://www.parallellfilmverksted.no/", title="Parallell", text="Velkommen til Parallell filmverksted. " + BODY, identity_text_excerpt="Kontakt oss i dag")))

    def test_hosting_placeholder_is_not_a_company_site(self):
        placeholder = site("CON AMORE KOR", "http://www.conamorekor.no/", legal_form="FLI", title="This server is operated by Example Webhosting",
                           text="No website is currently present on this hostname. The site you are trying to reach could be suspended, deleted or DNS could be incorrect. " * 2)
        self.assertFalse(publishable(placeholder))
        self.assertTrue(publishable(site("CON AMORE KOR", "http://www.conamorekor.no/", legal_form="FLI", title="Velkommen", text="Con Amore kor øver hver tirsdag. " + BODY)))

    def test_name_shaped_domain_abroad_needs_the_registered_place(self):
        def row(text, url="https://www.fjordkraftteknologi.com/"):
            item = site("FJORDKRAFT TEKNOLOGI AS", url, title="Fjordkraft | Clean Marine", text="Fjordkraft Teknologi. " + text)
            item["evidence"]["registry_live"] = {"status": "available", "value": {"business_address": {"postnummer": "5003", "poststed": "BERGEN"}}}
            return item

        self.assertFalse(publishable(row("GW-scale compute, powered from thin air. Modular pre-fab data halls built in a factory. " * 3)))
        self.assertTrue(publishable(row("Our Norwegian office is in Bergen. Modular pre-fab data halls built in a factory and assembled on site. " * 3)))
        self.assertTrue(publishable(row("GW-scale compute, powered from thin air. Modular pre-fab data halls built in a factory. " * 3, url="https://www.fjordkraftteknologi.no/")))

    def test_registrar_and_host_pages_are_not_websites_under_any_name_rule(self):
        # Seen live: a registrar's "is parked" page whose title repeats the domain (accepted by the older single-word
        # rule), an expired-domain notice, a web host's page, a crashed installation printing its file path.
        cases = (
            ("REVO AS", "http://www.revo.no/", "AS", None, "www.revo.no is parked", "www.revo.no is registered, but the owner currently does not have an active website here. Other services, such as e-mail, may be actively used by the owner."),
            ("RUD SKYTTERLAG", "https://rud.skytterlag.no/", "FLI", None, "rud.skytterlag.no in parked", "rud.skytterlag.no is parked. rud.skytterlag.no is registered, but the owner has currently no active website here."),
            ("TRUE NORTH RECORDS MARIT KARLSEN", "http://www.truenorthrecords.com/", "ENK", "Marit Karlsen", "NameBright - Domain Expired", "If this is your domain name you must renew it immediately before it is deleted and permanently removed from your account."),
            ("SENTRUM LEGEKONTOR DA", "http://www.sentrumlegekontor.no/", "DA", None, "Site Unavailable", "Site Unavailable. We're sorry, but this website is currently unavailable. If this is your website, please contact your vendor."),
            ("DESIGNPLOMMEN KINE EIDE", "http://www.designplommen.com/", "ENK", "Kine Eide", "Hosted by one.com", "Build your website. Build your dream website fast and easy, without any coding. Find your own domain. This one is taken, but you can find another."),
            ("AUTOKARL Svein Karl Berg", "http://autokarl.no/", "ENK", "Svein Karl Berg", "", "Fatal error: Using $this when not in object context in /home/autokarl/public_html/libraries/joomla/filter/input.php on line 141"),
        )
        for name, url, form, owner, title, text in cases:
            with self.subTest(name):
                row = site(name, url, legal_form=form, owner=owner, title=title, text=text, pages=[{"title": title}])
                assessment = assess_website_identity(row)
                self.assertFalse(assessment["publishable"])
                self.assertIn("placeholder", assessment["reasons"][0])

    def test_thin_page_needs_the_name_in_its_own_text_whatever_the_wording(self):
        # No known placeholder phrase at all: the domain in the title is still not the page stating the name.
        self.assertFalse(publishable(site("REVO AS", "http://www.revo.no/", title="revo.no", text="Denne adressen er reservert av eieren. Ta kontakt med leverandøren for mer informasjon om tjenesten og vilkårene.")))
        self.assertFalse(publishable(site("PARALLELL FILMVERKSTED AS", "https://www.parallellfilmverksted.no/", title="parallellfilmverksted.no", text=BODY)))
        # A small real site: one page, little text, the name written on it (kept).
        self.assertTrue(publishable(site("REVO AS", "https://www.revo.no/", title="Revo - rørlegger i Bodø", text="Revo utfører rørleggerarbeid for private og bedrifter i Bodø og omegn. Ta kontakt for befaring og et uforpliktende tilbud.")))
        # Words such as "under construction" in a real page's news are not a placeholder.
        self.assertTrue(publishable(site("NORDLYS CAMP AS", "https://nordlyscamp.no/en/", title="Nordlys Camp - Home", text="Under Construction: bringing Norway to China - Nordlys Camp China. New product under development for our guests this season.")))

    def test_earlier_rules_are_unchanged(self):
        # Exact name and organisation number still decide first; an unrelated site stays withheld.
        self.assertTrue(publishable(site("BERG BYGG AS", "https://www.bergbygg.no/", title="Berg Bygg AS - totalentreprenør")))
        self.assertFalse(publishable(site("HAVBRIS EIENDOM AS", "https://www.solstrand.no/", title="Solstrand Utleie AS", text="Velkommen til Solstrand Utleie " * 5)))
        parked = site("PARALLELL FILMVERKSTED AS", "https://www.parallellfilmverksted.no/", title="Parallell Filmverksted", text="This domain is for sale " * 8)
        self.assertFalse(publishable(parked))


def robots_answer(status: int, body: bytes = b"", error: str | None = None):
    def fetch(url, **_kwargs):
        return ByteFetch(url, status, 1, body if status else None, "text/plain", {}, "c" * 64 if status else None, NOW, 1, error=error)
    return fetch


class SchemeFallback(unittest.TestCase):
    """The registry lists most websites as a bare host; https is only this agent's guess."""

    def test_no_connection_is_told_apart_from_a_server_error(self):
        with mock.patch.object(website, "assert_public_url"):
            for error, expected in (("URLError", "robots_no_connection"), ("TimeoutError", "robots_no_connection"), ("ConnectionResetError", "robots_no_connection"),
                                    ("HTTP 503", "robots_unreachable"), ("HTTP 429", "robots_unreachable"), ("blocked: Private address", "robots_unreachable")):
                with self.subTest(error), mock.patch("norway_company_agent.http.fetch_bytes", side_effect=robots_answer(0, error=error)):
                    self.assertEqual(website._robots_check("https://x.no/", 15)[:2], (False, expected))

    def test_bare_host_falls_back_to_http_when_https_does_not_answer(self):
        seen = []

        def fetch(url, **kwargs):
            seen.append(url)
            if url.startswith("https://"):
                return robots_answer(0, error="URLError")(url)
            return robots_answer(200, b"User-agent: *\nDisallow: /\n")(url)

        with mock.patch.object(website, "assert_public_url"), mock.patch("norway_company_agent.http.fetch_bytes", side_effect=fetch), mock.patch.object(website.SAFE_OPENER, "open") as opener:
            record, metrics = website.fetch_website("x.no")
        # http was tried, and its own robots.txt (a disallow) was honoured: nothing else was fetched.
        self.assertEqual(seen, ["https://x.no/robots.txt", "http://x.no/robots.txt"])
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(record["source_url"], "http://x.no/")
        self.assertIn("disallows", record["note"])
        self.assertEqual(metrics["requests"], 2)
        opener.assert_not_called()

    def test_http_site_is_read_after_the_fallback(self):
        class Response:
            status = 200
            headers = {"content-type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _n=None):
                return b"<html><head><title>X AS</title></head><body><p>" + BODY.encode() + b"</p></body></html>"

            def geturl(self):
                return "http://x.no/"

        def fetch(url, **kwargs):
            return robots_answer(0, error="URLError")(url) if url.startswith("https://") else robots_answer(404)(url)

        with mock.patch.object(website, "assert_public_url"), mock.patch("norway_company_agent.http.fetch_bytes", side_effect=fetch), mock.patch.object(website.SAFE_OPENER, "open", return_value=Response()):
            record, _ = website.fetch_website("x.no")
        self.assertEqual(record["status"], "available")
        self.assertEqual(record["value"]["final_url"], "http://x.no/")

    def test_no_fallback_for_an_explicit_scheme_a_server_error_or_a_refusal(self):
        for supplied, status, error, note in (("https://x.no/", 0, "URLError", "unreachable"), ("x.no", 0, "HTTP 503", "unreachable"), ("x.no", 403, None, "401/403")):
            seen = []

            def fetch(url, _status=status, _error=error, **kwargs):
                seen.append(url)
                return robots_answer(_status, error=_error)(url)

            with self.subTest(supplied=supplied, error=error), mock.patch.object(website, "assert_public_url"), mock.patch("norway_company_agent.http.fetch_bytes", side_effect=fetch), mock.patch.object(website.SAFE_OPENER, "open") as opener:
                record, _ = website.fetch_website(supplied)
                self.assertEqual(seen, ["https://x.no/robots.txt"])
                self.assertEqual(record["status"], "blocked")
                self.assertIn(note, record["note"])
                opener.assert_not_called()

    def test_both_schemes_dead_stays_blocked(self):
        with mock.patch.object(website, "assert_public_url"), mock.patch("norway_company_agent.http.fetch_bytes", side_effect=robots_answer(0, error="URLError")), mock.patch.object(website.SAFE_OPENER, "open") as opener:
            record, _ = website.fetch_website("x.no")
        self.assertEqual(record["status"], "blocked")
        self.assertIn("robots.txt unreachable", record["note"])
        opener.assert_not_called()


class LeadParagraph(unittest.TestCase):
    def envelope(self, with_site: bool) -> dict:
        def claim(field, category, value, key):
            return {"field": field, "category": category, "value": value, "availability": "available", "confidence": 0.99, "evidence_ids": [f"ev-{key}"], "key": key}

        claims = [claim("legal_name", "identity", "EKSEMPEL AS", "k1"), claim("organisation_number", "identity", "987654321", "k2"), claim("legal_form", "identity", "AS", "k3")]
        if with_site:
            claims.append(claim("official_website", "websites", "https://www.eksempel.no/", "k4"))
        return {"organisation_number": "987654321", "identity": {"legal_name": "EKSEMPEL AS"}, "company_status": {"state": "researched"},
                "claims": claims, "evidence": [], "changes": [], "area_coverage": {"websites": with_site}}

    def test_company_with_a_verified_site_gets_a_cited_lead_paragraph(self):
        summary = company_summary(self.envelope(True))
        self.assertFalse(summary["sparse"])
        glance = next(section for section in summary["sections"] if section["id"] == "at_a_glance")["statements"]
        self.assertTrue(glance)
        self.assertEqual(summary["overview"], " ".join(statement["text"] for statement in glance))
        self.assertIn("https://www.eksempel.no/", summary["overview"])
        self.assertTrue(all(statement["claim_keys"] for statement in glance))
        self.assertTrue(summary["text"].startswith(summary["overview"]))

    def test_registry_only_company_keeps_its_overview(self):
        summary = company_summary(self.envelope(False))
        self.assertTrue(summary["sparse"])
        self.assertTrue(summary["overview"].startswith("Public information found was limited to official registry records"))


if __name__ == "__main__":
    unittest.main()
