"""V2 zero-cost discovery + site research: offline tests with a fake web."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.http import ByteFetch  # noqa: E402
from norway_company_agent.site_research import CompanyBudget, SiteSession, discovery_candidates, research_company_site  # noqa: E402

NOW = "2026-10-03T12:00:00Z"
ORG = "923609016"


class FakeWeb:
    def __init__(self, pages: dict[str, tuple[int, bytes]]):
        self.pages = pages
        self.calls: list[str] = []

    def __call__(self, url, **kwargs):
        self.calls.append(url)
        status, raw = self.pages.get(url, (404, b""))
        return ByteFetch(url, status, 2, raw, "text/html", {}, hashlib.sha256(raw).hexdigest(), NOW, 1, None if status == 200 else f"HTTP {status}")


def profile(org=ORG, name="Fjordtest Programvare AS", email=None, website=None, subunits=None):
    live = {"organisation_number": org, "name": name, "website": website, "email": email, "business_address": {"adresse": ["Storgata 1"], "postnummer": "0155"}}
    return {
        "organisation_number": org, "name": name, "website": website,
        "evidence": {
            "registry_live": evidence("registry_live", "available", "official_registry_live", f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}", value=live, content_sha256="a" * 64),
            "locations": evidence("locations", "available", "official_subunits", "https://data.brreg.no/x", value={"locations": subunits or []}, content_sha256="b" * 64),
        },
    }


HOME = f"""<html><head><title>Fjordtest</title><link rel="alternate" type="application/rss+xml" href="/feed/"></head><body>
<a href="https://www.linkedin.com/company/fjordtest-programvare">LinkedIn</a><a href="https://www.facebook.com/sharer.php?u=x">Del</a>
<a href="/karriere/">Karriere</a><a href="/kontakt/">Kontakt</a><footer>Fjordtest Programvare AS · Org.nr {ORG[:3]} {ORG[3:6]} {ORG[6:]}</footer></body></html>""".encode()
FEED = b"<rss><channel><item><title>Ny avdeling</title><link>https://fjordtest.no/ny</link><pubDate>Tue, 01 Sep 2026 10:00:00 +0200</pubDate></item></channel></rss>"
CAREERS = b'<html><script type="application/ld+json">{"@type":"JobPosting","title":"Utvikler","datePosted":"2026-09-20","validThrough":"2026-10-31"}</script></html>'
FAN = b"<html><head><title>Fjordtest Programvare AS Fansite</title></head><body>Storgata 1, 0155 Oslo</body></html>"


def site_pages(base="https://fjordtest.no"):
    return {f"{base}/robots.txt": (200, b"User-agent: *\nAllow: /\n"), f"{base}/": (200, HOME), f"{base}/feed/": (200, FEED), f"{base}/karriere/": (200, CAREERS), f"{base}/kontakt/": (200, b"<html>Kontakt</html>")}


class CandidateTests(unittest.TestCase):
    def test_order_dedup_free_mail_and_directories(self):
        subunits = [{"organisation_number": "973000001", "website": "www.fjordtest.no", "email": "post@gmail.com"}, {"organisation_number": "973000002", "email": "x@proff.no"}]
        candidates = discovery_candidates(profile(email="kari@fjordtest.no", website=None, subunits=subunits))
        self.assertEqual([(item["source"], item["domain"]) for item in candidates], [("registry_email", "fjordtest.no"), ("name_domain_guess", "fjordtestprogramvare.no"), ("name_domain_guess", "fjordtest-programvare.no")])


class UriTests(unittest.TestCase):
    def test_norwegian_letters_are_encoded_before_fetching(self):
        from norway_company_agent.site_research import to_uri

        self.assertEqual(to_uri("https://www.bærum-bil.no/om-oss/kontakt-ære?q=å"), "https://" + "www.bærum-bil.no".encode("idna").decode() + "/om-oss/kontakt-%C3%A6re?q=%C3%A5")
        self.assertEqual(to_uri("https://fjordtest.no/kontakt/"), "https://fjordtest.no/kontakt/")
        web = FakeWeb({})
        research_company_site(profile(subunits=[{"organisation_number": "973000001", "website": "www.bærum-bil.no"}]), SiteSession(web, resolver=lambda host: False))
        self.assertTrue(all(url.isascii() for url in web.calls))


class ResearchTests(unittest.TestCase):
    def test_registry_email_domain_verified_and_enriched(self):
        web = FakeWeb(site_pages())
        result = research_company_site(profile(email="post@fjordtest.no"), SiteSession(web, resolver=lambda host: True))
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.identity_class, "FIRST_PARTY_CONFIRMED")
        self.assertEqual(result.identity_source, "registry_email")
        self.assertEqual([item["url"] for item in result.profiles], ["https://www.linkedin.com/company/fjordtest-programvare"], "the URL exactly as the page links it")
        self.assertEqual([item["canonical_url"] for item in result.profiles], ["https://linkedin.com/company/fjordtest-programvare"])
        self.assertEqual(result.activities[0]["date"], "2026-09-01T08:00:00Z")
        self.assertEqual(result.jobs[0]["title"], "Utvikler")
        self.assertEqual(result.careers_page, "https://fjordtest.no/karriere/")
        self.assertFalse(any("linkedin.com" in url or "facebook.com" in url for url in web.calls), "platform pages are never fetched")

    def test_fan_site_rejected_then_next_candidate_tried(self):
        pages = {"https://fjordtestprogramvare.no/robots.txt": (200, b""), "https://fjordtestprogramvare.no/": (200, FAN), **site_pages("https://fjordtest-programvare.no")}
        result = research_company_site(profile(), SiteSession(FakeWeb(pages), resolver=lambda host: True))
        self.assertEqual([item["outcome"] for item in result.candidates], ["FAN_COMMUNITY", "FIRST_PARTY_CONFIRMED"])
        self.assertEqual(result.site_url, "https://fjordtest-programvare.no/")

    def test_arasenstadion_regression_never_verified(self):
        stadium = profile(org="976744667", name="ÅRÅSEN STADION AS")
        html = b"<html><head><title>\xc3\x85r\xc3\xa5sen Stadion Fansite - Hjemmet til Lillestr\xc3\xb8m Sportsklubb</title></head><body>Storgata 1, 0155 <footer>Kontakt <a href='mailto:lsk@lsk.no'>lsk@lsk.no</a></footer></body></html>"
        web = FakeWeb({"https://arasenstadion.no/robots.txt": (200, b""), "https://arasenstadion.no/": (200, html)})
        result = research_company_site(stadium, SiteSession(web, resolver=lambda host: host == "arasenstadion.no"))
        self.assertEqual(result.status, "none_verified")
        self.assertEqual(result.candidates[0]["outcome"], "FAN_COMMUNITY")

    def test_dead_dns_not_fetched_and_shared_domain_fetched_once(self):
        web = FakeWeb(site_pages())
        session = SiteSession(web, resolver=lambda host: False)
        research_company_site(profile(), session)
        self.assertEqual(web.calls, [], "unresolvable name guesses cost no HTTP request")
        research_company_site(profile(email="post@fjordtest.no"), session)
        research_company_site(profile(org="914778271", email="post@fjordtest.no"), session)
        self.assertEqual(web.calls.count("https://fjordtest.no/"), 1)

    def test_robots_disallow_and_budget_exhaustion_are_terminal(self):
        pages = site_pages()
        pages["https://fjordtest.no/robots.txt"] = (200, b"User-agent: *\nDisallow: /\n")
        result = research_company_site(profile(email="post@fjordtest.no"), SiteSession(FakeWeb(pages), resolver=lambda host: True))
        self.assertEqual(result.candidates[0]["outcome"], "robots_disallowed")
        result = research_company_site(profile(email="post@fjordtest.no"), SiteSession(FakeWeb(site_pages()), resolver=lambda host: True), max_requests=1)
        self.assertEqual(result.status, "budget_exhausted")


class OutboundPolicyTests(unittest.TestCase):
    def test_non_public_hosts_are_never_fetched(self):
        def guard(url):
            if "intranet" in url:
                raise ValueError("Private, loopback, link-local, multicast, and reserved addresses are blocked")
            if "gone" in url:
                raise ValueError("Hostname did not resolve")

        web = FakeWeb(site_pages())
        session = SiteSession(web, resolver=lambda host: True, url_guard=guard)
        budget = CompanyBudget(10, 10)
        self.assertEqual(session.get("https://intranet-fjordtest.no/", budget), ("blocked_non_public_host", None))
        self.assertEqual(session.get("https://gone-fjordtest.no/", budget), ("no_dns", None))
        self.assertEqual(session.get("https://fjordtest.no/", budget)[0], "ok")
        self.assertEqual(web.calls, ["https://fjordtest.no/robots.txt", "https://fjordtest.no/"])

    def test_redirect_to_a_private_address_is_refused(self):
        import http.server
        import threading

        from norway_company_agent.http import fetch_bytes
        from norway_company_agent.website import SAFE_OPENER

        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = fetch_bytes(f"http://127.0.0.1:{server.server_port}/", attempts=2, timeout=5, opener=SAFE_OPENER)
        finally:
            server.shutdown()
        self.assertIsNone(result.raw)
        self.assertTrue(result.error.startswith("blocked:"), result.error)
        self.assertEqual(result.attempts, 1, "a refused redirect is not retried")

    def test_live_batch_fetcher_is_guarded(self):
        import inspect

        from norway_company_agent import pipeline

        source = inspect.getsource(pipeline.run_batch)
        self.assertIn("url_guard=assert_public_url if live", source)
        self.assertIn("opener=SAFE_OPENER", source)


class PipelineV2Tests(unittest.TestCase):
    def test_envelope_contains_v2_site_claims_and_stays_valid(self):
        from test_contract import FakeBrreg, entity_body, make_website_fetcher, rows
        from norway_company_agent.pipeline import run_batch

        body = entity_body(ORG, "Fjordtest Programvare AS")
        body["epostadresse"] = "post@fjordtest.no"
        output = run_batch(rows(ORG), run_id="t", fetcher=FakeBrreg({ORG: body}), website_fetcher=make_website_fetcher({}), site_fetcher=FakeWeb(site_pages()), resolver=lambda host: True)
        envelope = output["envelopes"][0]
        self.assertEqual(validate_envelope(envelope), [])
        fields = {(claim["field"], claim["availability"]) for claim in envelope["claims"]}
        self.assertIn(("official_website", "available"), fields)
        self.assertNotIn(("official_website", "not_available"), fields, "no contradictory website state")
        self.assertIn(("social_profile", "available"), fields)
        self.assertIn(("news_item", "available"), fields)
        self.assertIn(("job_posting", "available"), fields)
        website = next(claim for claim in envelope["claims"] if claim["field"] == "official_website")
        self.assertEqual(website["identity_class"], "FIRST_PARTY_CONFIRMED")
        self.assertEqual(envelope["area_coverage"], {"filings": True, "leadership": True, "locations": True, "websites": True, "public_footprint": True, "hiring": True})
        self.assertEqual(output["report"]["companies_all_five_areas"], 1)
        roles = [claim for claim in envelope["claims"] if claim["field"] == "roles_last_changed"]
        self.assertEqual(roles[0]["category"], "registry_activity", "roles timestamps are never public activity")
        json.dumps(envelope)

    def test_v1_modules_still_supported(self):
        from test_contract import FakeBrreg, entity_body, make_website_fetcher, rows
        from norway_company_agent.pipeline import V1_MODULES, run_batch

        output = run_batch(rows(ORG), run_id="t", modules=list(V1_MODULES), fetcher=FakeBrreg({ORG: entity_body(ORG, "X AS")}), website_fetcher=make_website_fetcher({}))
        self.assertNotIn("site_research", output["envelopes"][0]["modules"])
        self.assertTrue(output["report"]["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
