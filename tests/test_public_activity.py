"""Offline tests for gate v2, public-activity extraction and search-result classification."""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.experiments import public_activity, search  # noqa: E402
from norway_company_agent.experiments.identity_v2 import classify_site, decode_cfemail  # noqa: E402
from norway_company_agent.http import ByteFetch  # noqa: E402

NOW = "2026-10-03T06:00:00Z"


def cf(email: str, key: int = 0x2A) -> str:
    return f"{key:02x}" + "".join(f"{ord(ch) ^ key:02x}" for ch in email)


STADIUM = {"organisation_number": "976744667", "name": "ÅRÅSEN STADION AS", "business_address": {"adresse": ["Stadionvegen 1"], "postnummer": "2004"}}
# Signals observed live on arasenstadion.no on 2026-10-03 (reduced to the decisive parts).
FAN_HTML = f"""<html><head><title>Åråsen Stadion Fansite - Hjemmet til Lillestrøm Sportsklubb</title></head><body>
<h1>Åråsen Stadion</h1><p>Stadionvegen 1, 2004 Lillestrøm</p>
<footer>Kontakt stadion 63 80 56 60 <a href="/cdn-cgi/l/email-protection#{cf('lsk@lsk.no')}">[email&#160;protected]</a> lsk.no/om-stadion/</footer></body></html>"""
FAN_HTML_NO_MARKER = FAN_HTML.replace("Fansite - ", "")


class GateV2Tests(unittest.TestCase):
    def test_cfemail_decoding(self):
        self.assertEqual(decode_cfemail(cf("lsk@lsk.no")), "lsk@lsk.no")

    def test_observed_false_positive_is_rejected_as_fan_site(self):
        verdict = classify_site(STADIUM, "arasenstadion.no", [FAN_HTML])
        self.assertEqual(verdict["class"], "FAN_COMMUNITY")
        self.assertFalse(verdict["publishable"])

    def test_without_marker_delegated_contact_still_rejects(self):
        verdict = classify_site(STADIUM, "arasenstadion.no", [FAN_HTML_NO_MARKER])
        self.assertEqual(verdict["class"], "THIRD_PARTY")
        self.assertIn("lsk.no", verdict["reasons"][0])

    def test_name_and_address_without_control_is_ambiguous(self):
        html = FAN_HTML_NO_MARKER.replace('<a href="/cdn-cgi', '<span data-x="').replace("[email&#160;protected]</a>", "</span>")
        self.assertEqual(classify_site(STADIUM, "arasenstadion.no", [html])["class"], "AMBIGUOUS")

    def test_name_address_plus_own_mailbox_is_first_party(self):
        company = {"organisation_number": "986757368", "name": "ANNEN VRI AS", "business_address": {"adresse": ["Øvre Smebyveg 4"], "postnummer": "2870"}}
        html = "<html><head><title>Annen Vri – Frisørsalong</title></head><body><footer>E-post: post@annenvri.no Adresse: Øvre Smebyveg 4, 2870 DOKKA</footer></body></html>"
        verdict = classify_site(company, "annenvri.no", [html])
        self.assertEqual(verdict["class"], "FIRST_PARTY")
        self.assertTrue(verdict["reasons"][0].startswith("C2"))

    def test_org_number_in_footer_is_first_party(self):
        company = {"organisation_number": "920772099", "name": "SPIREN DESIGN AS"}
        html = "<html><head><title>Spiren Design AS</title></head><body><footer>Spiren Design AS Org.nr: 920 772 099</footer></body></html>"
        self.assertEqual(classify_site(company, "spirendesign.no", [html])["class"], "FIRST_PARTY")

    def test_directory_listing_many_org_numbers_is_rejected(self):
        company = {"organisation_number": "920772099", "name": "SPIREN DESIGN AS"}
        rows = "".join(f"<li>Firma {i} AS {910000000 + i * 7}</li>" for i in range(5))
        html = f"<html><head><title>Spiren Design AS</title></head><body><ul>{rows}</ul><footer>Org.nr 920772099</footer></body></html>"
        self.assertEqual(classify_site(company, "x.no", [html])["class"], "DIRECTORY")

    def test_registry_phone_alone_never_verifies(self):
        company = {"organisation_number": "976744667", "name": "ÅRÅSEN STADION AS", "telefon": "63805660"}
        html = "<html><head><title>Åråsen Stadion</title></head><body>Ring 63 80 56 60</body></html>"
        self.assertFalse(classify_site(company, "arasen.no", [html])["publishable"])


class DateAndFeedTests(unittest.TestCase):
    def test_dates_are_never_invented(self):
        self.assertEqual(public_activity.parse_date("Tue, 01 Sep 2026 10:00:00 +0200"), "2026-09-01T08:00:00Z")
        self.assertEqual(public_activity.parse_date("2026-09-01"), "2026-09-01")
        self.assertIsNone(public_activity.parse_date("last week"))
        self.assertIsNone(public_activity.parse_date("2099-01-01T00:00:00Z"), "future dates are rejected")
        self.assertIsNone(public_activity.parse_date(""))

    def test_rss_and_atom_items(self):
        rss = b"<rss><channel><item><title>Ny butikk</title><link>https://x.no/ny</link><pubDate>Tue, 01 Sep 2026 10:00:00 +0200</pubDate></item><item><title>Udatert</title><link>https://x.no/u</link></item></channel></rss>"
        items = public_activity.feed_items(rss)
        self.assertEqual(items[0]["date"], "2026-09-01T08:00:00Z")
        self.assertIsNone(items[1]["date"])
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Oppdatert</title><link href="https://x.no/a"/><updated>2026-08-01T00:00:00Z</updated></entry></feed>'
        self.assertEqual(public_activity.feed_items(atom)[0]["date_kind"], "updated")

    def test_html_jsonld_and_time(self):
        html = """<html><head><script type="application/ld+json">{"@type":"NewsArticle","headline":"Vi ansetter","datePublished":"2026-07-01T09:00:00+02:00","url":"/nyheter/vi-ansetter"}</script></head>
        <body><article><h2>Sommerstengt</h2><a href="/nyheter/sommer">Les</a><time datetime="2026-06-20">20. juni</time></article><article><h2>Uten dato</h2></article></body></html>"""
        items = public_activity.html_items(html, "https://x.no/nyheter/")
        self.assertEqual({item["date"] for item in items}, {"2026-07-01T07:00:00Z", "2026-06-20"})
        self.assertIn("https://x.no/nyheter/vi-ansetter", {item["url"] for item in items})


def byte_result(url, status, raw=b"", content_type="text/html"):
    return ByteFetch(url, status, 3, raw, content_type, {}, hashlib.sha256(raw).hexdigest(), NOW, 1)


class RunCompanyTests(unittest.TestCase):
    def test_site_linked_profiles_and_feed_activity_with_robots(self):
        home = b"""<html><head><link rel="alternate" type="application/rss+xml" href="/feed/"></head><body>
        <a href="https://www.facebook.com/fjordtestprogramvare">Facebook</a><a href="https://www.linkedin.com/company/webbyraa-x">Laget av</a>
        <a href="https://www.facebook.com/sharer.php?u=x">Del</a><a href="/nyheter/">Nyheter</a><a href="/privat/">Privat</a></body></html>"""
        feed = b"<rss><channel><item><title>Ny avdeling</title><link>https://fjordtest.no/ny</link><pubDate>Tue, 01 Sep 2026 10:00:00 +0200</pubDate></item></channel></rss>"
        robots = b"User-agent: *\nDisallow: /nyheter/\n"
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return {"https://fjordtest.no/robots.txt": byte_result(url, 200, robots, "text/plain"), "https://fjordtest.no/": byte_result(url, 200, home), "https://fjordtest.no/feed/": byte_result(url, 200, feed, "application/rss+xml")}.get(url, byte_result(url, 404))

        profile = {"organisation_number": "923609016", "name": "Fjordtest Programvare AS"}
        row = public_activity.run_company(profile, "https://fjordtest.no/", "REGISTRY_LINKED", fetcher=fetch)
        self.assertEqual([item["url"] for item in row["profiles_accepted"]], ["https://facebook.com/fjordtestprogramvare"])
        self.assertEqual([item["url"] for item in row["profiles_ambiguous"]], ["https://linkedin.com/company/webbyraa-x"], "a web agency's profile linked from the site is not the company's")
        self.assertEqual(row["activities_dated"][0]["date"], "2026-09-01T08:00:00Z")
        self.assertEqual(row["activities_dated"][0]["content_sha256"], hashlib.sha256(feed).hexdigest())
        self.assertNotIn("https://fjordtest.no/nyheter/", calls, "robots-disallowed news page must not be fetched")
        self.assertIn("https://fjordtest.no/nyheter/", row["robots_blocked"])
        self.assertTrue(all("facebook.com/" not in url or "fjordtest.no" in url for url in calls), "platform pages are never fetched")


class SearchClassificationTests(unittest.TestCase):
    def test_classes(self):
        linked = {"https://facebook.com/fjordtest"}
        self.assertEqual(search.classify_search_result("https://www.facebook.com/fjordtest", linked), "OFFICIALLY_LINKED")
        self.assertEqual(search.classify_search_result("https://www.facebook.com/fjordtest-fans", linked), "AMBIGUOUS")
        self.assertEqual(search.classify_search_result("https://www.proff.no/selskap/fjordtest", linked), "DIRECTORY")
        self.assertEqual(search.classify_search_result("https://fjordtest.no/om", linked), "WEBSITE_CANDIDATE")

    def test_query_families(self):
        profile = {"organisation_number": "923609016", "name": "Fjordtest Programvare AS"}
        self.assertEqual(search.strategy_queries(profile, "Q1_name_orgnr"), ['"Fjordtest Programvare AS" "923609016"'])
        self.assertEqual(search.strategy_queries(profile, "Q6_orgnr"), ['"923609016"'])
        self.assertEqual(len(search.QUERY_FAMILIES), 6)


if __name__ == "__main__":
    unittest.main()
