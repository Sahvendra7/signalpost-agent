"""Offline tests for the source-expansion experiment modules (response shapes from the providers' docs/source)."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.experiments import brreg_activity, filings, nav_jobs, search, site_discovery  # noqa: E402
from norway_company_agent.experiments.common import Meter, summarize  # noqa: E402
from norway_company_agent.http import ByteFetch  # noqa: E402
from norway_company_agent.identity import assess_discovered_website_identity  # noqa: E402

ORG, SUB, OTHER = "923609016", "973000001", "914778271"
NOW = "2026-10-01T06:00:00Z"


def byte_result(url: str, status: int, body=None, raw: bytes | None = None, content_type: str = "application/json") -> ByteFetch:
    if raw is None and body is not None:
        raw = json.dumps(body).encode()
    return ByteFetch(url, status, 3, raw, content_type, {}, hashlib.sha256(raw).hexdigest() if raw is not None else None, NOW, 1, None if status == 200 else f"HTTP {status}")


class Router:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for match, outcome in self.routes:
            if match(url):
                return outcome(url, kwargs) if callable(outcome) else byte_result(url, *outcome)
        return byte_result(url, 404, {})


def profile(**extra):
    base = {
        "organisation_number": ORG,
        "name": "Fjordtest Programvare AS",
        "website": "",
        "evidence": {
            "registry_live": evidence("registry_live", "available", "official", "https://x", value={"organisation_number": ORG, "latest_submitted_accounts": "2025", "business_address": {"adresse": ["Storgata 1"], "postnummer": "0155", "poststed": "OSLO"}}, content_sha256="a" * 64),
            "locations": evidence("locations", "available", "official", "https://x", value={"locations": [{"organisation_number": SUB, "name": "Fjordtest Bergen", "website": "www.fjordtest.no"}]}, content_sha256="b" * 64),
        },
    }
    base.update(extra)
    return base


class BrregActivityTests(unittest.TestCase):
    def updates(self, rows, total=None):
        return {"_embedded": {"oppdaterteEnheter": rows}, "page": {"totalElements": total if total is not None else len(rows)}}

    def test_events_are_dated_typed_and_org_checked(self):
        rows = [
            {"oppdateringsid": 1, "dato": "2019-03-01T10:00:00.000Z", "organisasjonsnummer": ORG, "endringstype": "Ukjent"},
            {"oppdateringsid": 2, "dato": "2026-05-01T10:00:00.000Z", "organisasjonsnummer": ORG, "endringstype": "Endring", "endringer": [{"op": "replace", "path": "/forretningsadresse/adresse", "value": ["Ny gate 2"]}]},
            {"oppdateringsid": 3, "dato": "2026-05-02T10:00:00.000Z", "organisasjonsnummer": OTHER, "endringstype": "Endring"},
        ]
        sub_rows = {"_embedded": {"oppdaterteUnderenheter": [{"oppdateringsid": 9, "dato": "2026-01-01T00:00:00.000Z", "organisasjonsnummer": SUB, "endringstype": "Ny"}]}, "page": {"totalElements": 1}}
        router = Router([(lambda u: "/oppdateringer/enheter" in u, (200, self.updates(rows))), (lambda u: "/oppdateringer/underenheter" in u, (200, sub_rows))])
        result = brreg_activity.run_company(profile(), router)
        self.assertEqual(result["events"], 3)
        self.assertEqual(result["identity_rejections"], 1, "a row for another org number is rejected")
        self.assertEqual(result["informative_events"], 2)
        self.assertTrue(result["covered"] and result["covered_recent"])
        self.assertEqual(result["evidence_complete"], result["evidence_items"])
        query = parse_qs(urlparse(router.calls[0][0]).query)
        self.assertEqual(query["organisasjonsnummer"], [ORG])
        self.assertEqual(query["includeChanges"], ["true"])
        self.assertTrue(query["dato"][0].startswith("1990"), "history must be requested explicitly, not left to the default window")
        self.assertIn("/forretningsadresse/adresse", result["sample_events"][1]["changed_fields"])

    def test_pagination_stops_at_total(self):
        page = lambda url, kw: byte_result(url, 200, self.updates([{"oppdateringsid": int(parse_qs(urlparse(url).query)["page"][0]), "dato": "2020-01-01T00:00:00Z", "organisasjonsnummer": ORG, "endringstype": "Endring"}] * 100, total=150))  # noqa: E731
        router = Router([(lambda u: "/oppdateringer/enheter" in u, page)])
        result = brreg_activity.run_company(profile(evidence={}), router)
        self.assertEqual(sum(1 for url, _ in router.calls if "/enheter" in url), 2)
        self.assertEqual(result["events"], 200)

    def test_transport_failure_is_unmeasured_not_zero(self):
        router = Router([(lambda u: True, (0, None))])
        result = brreg_activity.run_company(profile(), router)
        self.assertTrue(result["unmeasured"])
        self.assertEqual(summarize([result], covered_key="covered")["companies_measured"], 0)


ACCOUNT = {
    "id": 1, "regnskapstype": "SELSKAP", "valuta": "NOK", "oppstillingsplan": "smaa",
    "virksomhet": {"organisasjonsnummer": ORG, "morselskap": False},
    "regnskapsperiode": {"fraDato": "2025-01-01", "tilDato": "2025-12-31"},
    "revisjon": {"fravalgRevisjon": True, "ikkeRevidertAarsregnskap": True},
    "resultatregnskapResultat": {"driftsresultat": {"driftsinntekter": {"sumDriftsinntekter": 0, "salgsinntekter": 0}, "driftskostnad": {"sumDriftskostnad": 1200, "loennskostnad": 0}, "driftsresultat": -1200}, "aarsresultat": -1000, "ordinaertResultatFoerSkattekostnad": -1100, "finansresultat": {"nettoFinans": 100}},
    "eiendeler": {"sumEiendeler": 50000, "sumBankinnskuddOgKontanter": 4000, "anleggsmidler": {"sumAnleggsmidler": 46000}, "omloepsmidler": {"sumOmloepsmidler": 4000}},
    "egenkapitalGjeld": {"egenkapital": {"sumEgenkapital": 30000}, "gjeldOversikt": {"sumGjeld": 20000, "kortsiktigGjeld": {"sumKortsiktigGjeld": 20000}}},
}


def blank_pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class FilingsTests(unittest.TestCase):
    def test_open_api_fields_beyond_starter_and_zero_preserved(self):
        account = filings.normalize_account(ACCOUNT)
        self.assertEqual(account["values"]["revenue"], 0)
        self.assertEqual(account["values"]["wage_costs"], 0)
        self.assertEqual(account["values"]["cash"], 4000)
        self.assertEqual(account["flags"]["audit_opt_out"], True)
        self.assertEqual(len(account["values"]), 15)
        self.assertTrue(filings.period_correct(account, "2025"))
        self.assertFalse(filings.period_correct({**account, "period_from": "2026-01-01"}, "2025"))

    def test_company_run_measures_years_pdf_and_rejects_other_org(self):
        other = {**ACCOUNT, "id": 2, "virksomhet": {"organisasjonsnummer": OTHER}}
        router = Router([
            (lambda u: u.endswith(f"/regnskap/{ORG}"), (200, [ACCOUNT, other])),
            (lambda u: "%C3%A5r=2024" in u, (200, [])),
            (lambda u: u.endswith("/aar"), (200, ["2023", "2024", "2025"])),
            (lambda u: u.endswith(f"/kopi/{ORG}/2025"), lambda url, kw: byte_result(url, 200, raw=blank_pdf(), content_type="application/pdf")),
        ])
        result = filings.run_company(profile(), router, rate_limit=False)
        self.assertTrue(result["has_latest_filing"] and result["has_revenue"] and result["has_balance_sheet"])
        self.assertEqual(result["identity_rejections"], 1)
        self.assertTrue(result["period_correct"])
        self.assertFalse(result["prior_year_structured"])
        self.assertTrue(result["has_multiple_years"])
        self.assertTrue(result["pdf_retrieved"])
        self.assertFalse(result["pdf_text_parsed"])
        self.assertEqual(result["pdf"]["pages"], 1)
        self.assertEqual(result["evidence_complete"], result["evidence_items"])

    def test_non_pdf_bytes_are_not_counted_as_retrieved(self):
        self.assertFalse(filings.pdf_inspection(b"<html>rate limited</html>")["is_pdf"])


class NavJobsTests(unittest.TestCase):
    def feed_item(self, uuid, name, status="ACTIVE"):
        return {"id": uuid, "url": f"/api/v1/feedentry/{uuid}", "title": "Utvikler", "_feed_entry": {"uuid": uuid, "status": status, "title": "Utvikler", "businessName": name, "municipal": "OSLO", "sistEndret": NOW}}

    def detail(self, orgnr, expires="2026-12-01T00:00:00Z", status="ACTIVE"):
        return {"uuid": "u", "status": status, "ad_content": {"title": "Utvikler", "published": "2026-09-01T00:00:00Z", "expires": expires, "employer": {"name": "x", "orgnr": orgnr, "homepage": "https://fjordtest.no"}, "link": "https://arbeidsplassen.nav.no/stillinger/stilling/u"}}

    def test_public_token_parsing(self):
        meter = Meter(Router([(lambda u: True, lambda url, kw: byte_result(url, 200, raw=b"Bearer abc.def.ghi\n", content_type="text/plain"))]))
        self.assertEqual(nav_jobs.public_token(meter), "abc.def.ghi")
        live_shape = b"Current public token for Nav Job Vacancy Feed:\neyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl"
        meter = Meter(Router([(lambda u: True, lambda url, kw: byte_result(url, 200, raw=live_shape, content_type="text/plain"))]))
        self.assertEqual(nav_jobs.public_token(meter), "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl")
        meter = Meter(Router([(lambda u: True, lambda url, kw: byte_result(url, 200, raw=b"Service unavailable", content_type="text/plain"))]))
        self.assertIsNone(nav_jobs.public_token(meter))

    def test_scan_keeps_latest_state_and_follows_pages(self):
        pages = {
            "first": {"items": [self.feed_item("a", "Fjordtest Programvare AS"), self.feed_item("b", "Fjordtest Programvare AS")], "next_url": "/api/v1/feed/p2", "next_id": "p2"},
            "p2": {"items": [self.feed_item("b", "Fjordtest Programvare AS", status="INACTIVE")], "next_url": None, "next_id": None},
        }
        router = Router([(lambda u: "p2" in u, (200, pages["p2"])), (lambda u: "/api/v1/feed" in u, (200, pages["first"]))])
        scan = nav_jobs.scan_active_ads(Meter(router), "tok")
        self.assertEqual(set(scan["active"]), {"a"})
        self.assertEqual(scan["stop_reason"], "end_of_feed")
        self.assertIn("If-Modified-Since", router.calls[0][1]["headers"])
        self.assertTrue(router.calls[0][0].endswith("pageSize=10000"))
        self.assertTrue(router.calls[1][0].endswith("/api/v1/feed/p2?pageSize=10000"), "page size must persist past page 1")

    def test_orgnr_verification_rejects_namesakes_and_accepts_subunits(self):
        active = {
            "a": {"uuid": "a", "url": "/api/v1/feedentry/a", "businessName": "Fjordtest Programvare AS"},
            "b": {"uuid": "b", "url": "/api/v1/feedentry/b", "businessName": "FJORDTEST PROGRAMVARE"},
            "c": {"uuid": "c", "url": "/api/v1/feedentry/c", "businessName": "Fjordtest Bergen"},
            "d": {"uuid": "d", "url": "/api/v1/feedentry/d", "businessName": "Fjordtest Programvare AS"},
        }
        details = {"a": self.detail(ORG), "b": self.detail(OTHER), "c": self.detail(SUB), "d": self.detail(ORG, expires="2026-01-01T00:00:00Z")}
        router = Router([(lambda u: "/feedentry/" in u, lambda url, kw: byte_result(url, 200, details[url.rsplit("/", 1)[1]]))])
        result = nav_jobs.run_company(profile(), nav_jobs.build_name_index(active), "tok", router, now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(result["name_candidates"], 4)
        self.assertEqual(result["jobs"], 2)
        self.assertEqual(result["identity_rejections"], 1, "same name, different org number")
        self.assertEqual(result["jobs_via_subunit_orgnr"], 1)
        self.assertEqual(result["expired_or_inactive"], 1)
        self.assertEqual(router.calls[0][1]["headers"]["Authorization"], "Bearer tok")
        job = result["accepted_jobs"][0]
        for key in ("employer_orgnr", "employer_name", "source_url", "published", "expires", "retrieved_at", "content_sha256"):
            self.assertTrue(job.get(key), key)


def site(title="", text="", identity="", pages=None, status="available"):
    if status != "available":
        return evidence("website", status, "candidate", "https://x.no/")
    return evidence("website", "available", "candidate", "https://x.no/", value={"final_url": "https://x.no/", "title": title, "main_text_excerpt": text, "identity_text_excerpt": identity, "pages": pages or []}, content_sha256="c" * 64)


class DiscoveredSiteGateTests(unittest.TestCase):
    def target(self):
        return {"organisation_number": ORG, "name": "Fjordtest Programvare AS", "business_address": {"adresse": ["Storgata 1"], "postnummer": "0155"}}

    def test_org_number_anywhere_on_captured_pages_verifies(self):
        result = assess_discovered_website_identity(self.target(), site(title="Fjordtest", pages=[{"title": "Kontakt", "identity_text_excerpt": "Org.nr: 923 609 016 MVA"}]))
        self.assertTrue(result["publishable"])

    def test_exact_name_alone_is_not_enough_for_a_discovered_site(self):
        self.assertFalse(assess_discovered_website_identity(self.target(), site(title="Fjordtest Programvare AS"))["publishable"])

    def test_name_plus_registered_address_verifies(self):
        self.assertTrue(assess_discovered_website_identity(self.target(), site(title="Fjordtest Programvare AS", identity="Storgata 1, 0155 Oslo"))["publishable"])

    def test_namesake_in_other_city_is_rejected(self):
        self.assertFalse(assess_discovered_website_identity(self.target(), site(title="Fjordtest Programvare AS", identity="Fjordveien 9, 5003 Bergen"))["publishable"])

    def test_org_number_embedded_in_longer_number_does_not_match(self):
        self.assertFalse(assess_discovered_website_identity(self.target(), site(title="x", identity="Kontonr 19236090161"))["publishable"])

    def test_parked_domain_rejected_even_with_org_number(self):
        self.assertFalse(assess_discovered_website_identity(self.target(), site(title="x.no is for sale | HugeDomains", identity="923609016"))["publishable"])


class SiteDiscoveryTests(unittest.TestCase):
    def test_candidates_from_official_pointers_dedup_and_drop_free_mail(self):
        candidates = site_discovery.candidates_for(profile(), {"epostadresse": "post@gmail.com"}, ["https://www.fjordtest.no/"], include_guesses=True)
        self.assertEqual([item["source"] for item in candidates], ["subunit_website", "name_domain_guess", "name_domain_guess"])
        self.assertEqual(site_discovery.email_domain({"adresse": "kari@fjordtest.no"}), "fjordtest.no")
        self.assertIsNone(site_discovery.email_domain("ola@online.no"))

    def test_run_counts_verified_ambiguous_and_skips_unresolvable_guesses(self):
        pages = {"https://www.fjordtest.no/": site(title="Fjordtest", identity="org.nr 923609016")}
        fetch = lambda url: (pages.get(url) or site(title="Something Else AS"), {"requests": 2})  # noqa: E731
        result = site_discovery.run_company(profile(), None, [], website_fetcher=fetch, resolver=lambda host: host == "fjordtestprogramvare.no")
        self.assertTrue(result["covered"])
        self.assertEqual(result["verified_sources"], ["subunit_website"])
        self.assertEqual(result["by_source"]["name_domain_guess"], ["ambiguous", "no_dns"])


class FakeProvider:
    name = "fake"

    def __init__(self, urls):
        self.urls = urls

    def search(self, query, *, count=5):
        return search.SearchResponse(query, [{"url": url} for url in self.urls], 1, 0.005, 100)


class SearchTests(unittest.TestCase):
    def test_no_provider_is_a_noop(self):
        result = search.run_company(profile(), search.NoSearchProvider(), "B_name_orgnr", website_fetcher=lambda url: self.fail("no crawl without results"))
        self.assertEqual((result["requests"], result["search_cost_usd"], result["covered"], result["outcome"]), (0, 0, False, "no_result"))

    def test_directories_are_skipped_and_only_gate_passing_domains_count(self):
        pages = {"https://fjordtest.no/": site(title="Fjordtest", identity="923 609 016")}
        fetch = lambda url: (pages.get(url) or site(title="Fjordtest Programvare AS"), {"requests": 2})  # noqa: E731
        provider = FakeProvider(["https://www.proff.no/selskap/x", "https://namesake.no/", "https://fjordtest.no/om"])
        result = search.run_company(profile(), provider, "A_name_norway", website_fetcher=fetch, known_domain="fjordtest.no")
        self.assertEqual([item["domain"] for item in result["candidates"]], ["namesake.no", "fjordtest.no"])
        self.assertEqual(result["verified_domain"], "fjordtest.no")
        self.assertEqual(result["labelled_outcome"], "correct")
        self.assertEqual(result["search_cost_usd"], 0.005)

    def test_strategies_build_expected_queries(self):
        self.assertEqual(search.strategy_queries(profile(), "B_name_orgnr"), ['"Fjordtest Programvare AS" "923609016"'])
        self.assertEqual(search.strategy_queries(profile(), "D_site_guess"), ["site:fjordtestprogramvare.no"])
        self.assertIn("923 609 016", search.strategy_queries(profile(), "C_orgnr")[0])


if __name__ == "__main__":
    unittest.main()
