"""C300 revision: hosting-platform pages are not the company's site, period-correct synthesis, and a viewer the
documented run always writes.

The 911771098 case replays the exact bytes Revision 1 (05d7566) captured live on 2026-10-17
(tests/fixtures/c300/911771098, built by tests/fixtures/c12/build_fixtures.py; nothing edited)."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.c12_replay import C300_FIXTURES, Fixture  # noqa: E402
from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from helpers.summary_check import TREND_WORDS, unsupported_statements  # noqa: E402
from norway_company_agent.claims import ClaimSet, _site_research_claims  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402
from norway_company_agent.site_facts import CapturedPage, extract_site_facts, in_site_scope, owns_registered_domain  # noqa: E402

HJS = "911771098"
BLOG = "https://hjsandnes.wordpress.com/"
PLATFORM_PAGE = "https://wordpress.com/?ref=footer_custom_svg"
WORDPRESS_PROFILES = {"https://www.linkedin.com/company/wordpress", "https://www.facebook.com/WordPresscom/", "https://www.instagram.com/wordpressdotcom/"}


def page(url: str, html: str) -> CapturedPage:
    raw = html.encode("utf-8")
    return CapturedPage(url, raw, hashlib.sha256(raw).hexdigest(), "2026-10-17T05:31:15Z")


def captured(fixture: Fixture, url: str) -> CapturedPage:
    entry = fixture.manifest["entries"][url]
    return CapturedPage(url, fixture.raw(url), entry["content_sha256"], entry["retrieved_at"])


def available(envelope: dict, field: str) -> list[dict]:
    return [claim for claim in envelope["claims"] if claim["field"] == field and claim["availability"] == "available"]


class WordPressLinkedInRegression(unittest.TestCase):
    """Builderr C300: a WordPress LinkedIn page was published as HANS JØRGEN SANDNES AS's profile.

    Trace (Revision 1, live 2026-10-17): registry hjemmeside hjsandnes.wordpress.com -> verified (REGISTRY_LINKED,
    legal name on the homepage) -> the blog's footer link "https://wordpress.com/?ref=footer_custom_svg" was taken
    for a news page because wordpress.com is the blog's registrable domain -> WordPress.com's own Organization JSON-LD
    (url https://wordpress.com/) passed as "the verified site's own Organization structured data" -> its sameAs
    https://www.linkedin.com/company/wordpress (and Facebook/Instagram) became public_activity.social_profile claims."""

    def replay(self, root: Path | None = None):
        fixture = Fixture(HJS, base=C300_FIXTURES)
        output = run_batch([InputRow(0, HJS, HJS)], run_id="c300", snapshot_root=root, **fixture.injected())
        return output["envelopes"][0], fixture

    def test_platform_profiles_are_not_published_and_the_platform_is_not_fetched(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope, fixture = self.replay(root)
            self.assertEqual(validate_envelope(envelope, snapshot_root=root), [])
        values = json.dumps([claim.get("value") for claim in envelope["claims"]], ensure_ascii=False)
        for url in WORDPRESS_PROFILES:
            self.assertNotIn(url, values)
        self.assertEqual(available(envelope, "social_profile"), [])
        social = [claim for claim in envelope["claims"] if claim["field"] == "social_profile"]
        self.assertEqual([claim["availability"] for claim in social], ["ambiguous"], "the blog's own Facebook links stay uncorroborated")
        self.assertNotIn(PLATFORM_PAGE, fixture.calls, "the hosting platform's homepage is not a page of the verified site")
        self.assertFalse([url for url in fixture.calls if url.startswith("https://wordpress.com/")])
        self.assertEqual(available(envelope, "official_website")[0]["value"], BLOG, "the registry-linked blog itself stays verified")
        news = available(envelope, "news_item")
        self.assertTrue(news, "the blog's own dated posts are still published")
        self.assertTrue(all(claim["source_page"].startswith(BLOG) and claim["value"]["url"].startswith(BLOG) for claim in news))
        self.assertNotIn("wordpress.com/company", envelope["company_summary"]["text"].replace("hjsandnes.wordpress.com", ""))

    def test_the_captured_platform_page_contributes_no_fact(self):
        """The exact pages Revision 1 extracted from, platform page included: nothing from wordpress.com is kept."""
        fixture = Fixture(HJS, base=C300_FIXTURES)
        pages = [captured(fixture, url) for url in (BLOG, BLOG + "about/", BLOG + "kontakt/", PLATFORM_PAGE)]
        platform = pages[-1].unescaped
        self.assertTrue('"sameAs"' in platform and "https://www.linkedin.com/company/wordpress" in platform, "the evidence behind the C300 claim")
        facts = extract_site_facts({"name": "HANS JØRGEN SANDNES AS", "organisation_number": HJS}, pages)
        self.assertEqual(facts.profiles, [])
        self.assertEqual(facts.rejections.get("page:outside_verified_site"), 1)
        self.assertTrue(all(item["page_url"].startswith(BLOG) for item in facts.activities))

    def test_stored_records_with_platform_profiles_are_not_republished(self):
        """A Revision 1 profile record (previous run, or carried forward on an outage) cannot republish them."""
        fixture = Fixture(HJS, base=C300_FIXTURES)
        entry = fixture.manifest["entries"][PLATFORM_PAGE]
        stored = [{"platform": platform, "url": url, "canonical_url": url.replace("www.", "").rstrip("/").lower(), "found_on": PLATFORM_PAGE,
                   "content_sha256": entry["content_sha256"], "retrieved_at": entry["retrieved_at"], "evidence_span": url, "identity_score": 0.95,
                   "identity_reason": "listed in sameAs of the verified site's own Organization structured data"}
                  for platform, url in (("linkedin", "https://www.linkedin.com/company/wordpress"), ("facebook", "https://www.facebook.com/WordPresscom/"))]
        home = fixture.manifest["entries"][BLOG]
        record = {"status": "available", "carried_forward": True, "value": {
            "site_url": BLOG, "identity_class": "REGISTRY_LINKED", "identity_reasons": ["registry-listed website verified by the registry identity gate"],
            "pages": [{"url": BLOG, "content_sha256": home["content_sha256"], "retrieved_at": home["retrieved_at"]}], "profiles": stored,
            "activities": [{"title": "Fra plattformen", "date": "2026-07-02", "page_url": PLATFORM_PAGE, "content_sha256": entry["content_sha256"], "retrieved_at": entry["retrieved_at"]}],
        }}
        claims = ClaimSet()
        _site_research_claims(claims, record, v1_site_published=False)
        self.assertEqual([claim["value"] for claim in claims.claims if claim["availability"] == "available" and claim["category"] == "public_activity"], [])
        self.assertEqual([claim["value"] for claim in claims.claims if claim["field"] == "official_website"], [BLOG])


class SiteScopeRules(unittest.TestCase):
    def test_scope_of_apex_and_subdomain_sites(self):
        self.assertTrue(owns_registered_domain("https://www.fjell-data.no/"))
        self.assertTrue(owns_registered_domain("https://fjell-data.no/om-oss"))
        self.assertFalse(owns_registered_domain(BLOG))
        self.assertTrue(in_site_scope("https://blogg.fjell-data.no/nyheter", "https://www.fjell-data.no/"), "a domain's own site keeps its subdomains")
        self.assertTrue(in_site_scope("https://fjell-data.no/kontakt", "https://www.fjell-data.no/"))
        self.assertFalse(in_site_scope("https://example.no/", "https://www.fjell-data.no/"))
        self.assertTrue(in_site_scope(BLOG + "about/", BLOG))
        self.assertFalse(in_site_scope(PLATFORM_PAGE, BLOG), "the platform apex is not the tenant's site")
        self.assertFalse(in_site_scope("https://annen.wordpress.com/", BLOG), "nor is another tenant")

    def test_wordpress_pages_slugs_and_mentions_of_linkedin_are_not_profiles(self):
        body = (f'<a href="{BLOG}linkedin/">LinkedIn</a><a href="{BLOG}2019/01/01/min-linkedin-profil/">Min LinkedIn-profil</a>'
                f'<a href="{BLOG}?share=linkedin">Del på LinkedIn</a><a href="https://www.linkedin.com/shareArticle?mini=true&url={BLOG}">Share</a>'
                '<a href="https://www.linkedin.com/sharing/share-offsite/?url=x">Del</a><p>Følg meg på LinkedIn: Hans Jørgen Sandnes</p>'
                '<a href="https://www.linkedin.com/in/hans-jorgen-sandnes">personal profile</a>')
        facts = extract_site_facts({"name": "HANS JØRGEN SANDNES AS"}, [page(BLOG, f"<html><head><title>LinkedIn</title></head><body>{body}</body></html>")])
        self.assertEqual(facts.profiles, [])
        self.assertEqual(facts.ambiguous_profiles, [], "none of these is a company profile link at all")

    def test_a_tenant_site_does_not_inherit_the_platform_name_or_structured_data(self):
        site = "https://kirkenes.barnehage.no/"
        html = ('<html><body><footer><a href="https://www.facebook.com/barnehage.no">Barnehage.no</a>'
                '<a href="https://www.facebook.com/kirkenesbarnehage">Kirkenes barnehage</a></footer>'
                '<script type="application/ld+json">{"@type":"Organization","url":"https://barnehage.no/","name":"Barnehage.no","sameAs":["https://www.linkedin.com/company/barnehage-no"]}</script></body></html>')
        facts = extract_site_facts({"name": "KIRKENES BARNEHAGE AS"}, [page(site, html)])
        self.assertEqual([item["url"] for item in facts.profiles], ["https://www.facebook.com/kirkenesbarnehage"], "only the legal-name handle")
        apex = extract_site_facts({"name": "BARNEHAGE NO AS"}, [page("https://barnehage.no/", html.replace("kirkenesbarnehage", "x"))])
        self.assertIn("https://www.linkedin.com/company/barnehage-no", [item["url"] for item in apex.profiles], "the platform's own site keeps its structured data")

    def test_an_apex_site_still_reads_its_own_subdomain_pages(self):
        home = page("https://www.fjell-data.no/", '<html><body><a href="https://blogg.fjell-data.no/">Blogg</a></body></html>')
        blog = page("https://blogg.fjell-data.no/", '<html><body><a href="https://www.facebook.com/fjelldata">Facebook</a></body></html>')
        facts = extract_site_facts({"name": "Fjell Data AS"}, [home, blog])
        self.assertEqual([item["url"] for item in facts.profiles], ["https://www.facebook.com/fjelldata"])
        self.assertNotIn("page:outside_verified_site", facts.rejections)


ORG = valid_orgs(1)[0]


def account(start: str, end: str, revenue: float, net: float, *, equity: float = 3000, kind: str = "SELSKAP", currency: str = "NOK", record_id: int = 1) -> dict:
    return {"id": record_id, "regnskapstype": kind, "valuta": currency, "regnskapsperiode": {"fraDato": start, "tilDato": end},
            "resultatregnskapResultat": {"driftsresultat": {"driftsinntekter": {"sumDriftsinntekter": revenue}, "driftsresultat": net}, "aarsresultat": net},
            "eiendeler": {"sumEiendeler": 5000}, "egenkapitalGjeld": {"egenkapital": {"sumEgenkapital": equity}, "gjeldOversikt": {"sumGjeld": 2000}}}


def summarise(body: dict | None = None, accounts: list[dict] | None = None, previous: dict | None = None, **entity_args) -> tuple[dict, dict]:
    overrides = {(ORG, "regnskapsregisteret"): (200, accounts)} if accounts is not None else {}
    output = run_batch([InputRow(0, ORG, ORG)], run_id="s", previous_profiles={ORG: previous} if previous else None,
                       **injected(FakeBrreg({ORG: body or entity(ORG, **entity_args)}, overrides=overrides)))
    return output["envelopes"][0], output["profiles"][0]


def statements(envelope: dict, key: str) -> list[str]:
    return [item["text"] for item in next(section for section in envelope["company_summary"]["sections"] if section["id"] == key)["statements"]]


class SynthesisRegression(unittest.TestCase):
    def assertSupported(self, envelope: dict) -> None:
        self.assertEqual(unsupported_statements(envelope), [])

    def test_null_employee_count_is_unknown_never_zero(self):
        for label, body in (
            ("no count, none registered", {**entity(ORG, employees=None), "harRegistrertAntallAnsatte": False}),
            ("registered but not published", {**entity(ORG, employees=None), "harRegistrertAntallAnsatte": True}),
            ("no flag at all", entity(ORG, employees=None)),
        ):
            with self.subTest(label):
                envelope, _ = summarise(body)
                claim = next(item for item in envelope["claims"] if item["field"] == "registry_employee_count")
                self.assertEqual((claim["availability"], claim["value"]), ("not_available", None))
                self.assertIn("unknown, not zero", claim["reason"])
                text = envelope["company_summary"]["text"]
                self.assertNotRegex(text, r"[Ee]mployees?[^.\n]*:\s*0\b", "a missing count is never shown as zero")
                self.assertIn("Employee count: unknown (not published in the registry record; not zero).", statements(envelope, "at_a_glance"))
                self.assertTrue(any(line.startswith("Employee count: not published.") for line in statements(envelope, "key_company_facts")))
                self.assertSupported(envelope)
        zero, _ = summarise(employees=0)
        self.assertIn("Employees reported to the registry: 0.", statements(zero, "key_company_facts"), "a stated zero stays zero")

    def test_fy2024_versus_fy2025_financials(self):
        envelope, _ = summarise(accounts=[account("2025-01-01", "2025-12-31", 1500, 120, equity=3200), account("2024-01-01", "2024-12-31", 1000, 150, record_id=2)])
        finance = " ".join(statements(envelope, "financial_snapshot"))
        self.assertIn("Most recent figures in the accounts register (company accounts), reporting period 2025-01-01 to 2025-12-31: Revenue NOK 1,500", finance)
        self.assertIn("Earlier reporting period with figures in the accounts register: 2024-01-01 to 2024-12-31.", finance)
        change = next(line for line in statements(envelope, "what_changed") if line.startswith("Compared with"))
        self.assertEqual(change, "Compared with the preceding reporting period (2024-01-01 to 2024-12-31), the company accounts for 2025-01-01 to 2025-12-31 show: "
                                 "revenue higher (NOK 1,000 to NOK 1,500); operating result lower (NOK 150 to NOK 120); net result lower (NOK 150 to NOK 120); equity higher (NOK 3,000 to NOK 3,200).")
        cited = {(claim["field"], claim["period"]["to"]) for section in envelope["company_summary"]["sections"] if section["id"] == "what_changed"
                 for statement in section["statements"] for claim in envelope["claims"] if claim["key"] in statement["claim_keys"] and claim["category"] == "filings"}
        self.assertEqual(cited, {(field, end) for field in ("revenue", "operating_result", "net_result", "equity") for end in ("2024-12-31", "2025-12-31")}, "both periods are cited")
        self.assertSupported(envelope)

    def test_most_recent_period_is_selected_and_an_older_year_is_never_latest(self):
        # Records out of order, a group account only for an older year, and a registry field one year behind the figures.
        body = {**entity(ORG), "sisteInnsendteAarsregnskap": "2024"}
        envelope, _ = summarise(body, accounts=[account("2024-01-01", "2024-12-31", 900, 50, record_id=2), account("2025-01-01", "2025-12-31", 1200, 60),
                                                account("2023-01-01", "2023-12-31", 800, 40, kind="KONSERN", record_id=3)])
        finance = statements(envelope, "financial_snapshot")
        self.assertEqual(finance[0], "The registry record still names 2024 as the last submitted accounts year, but the accounts register holds figures for the newer period ending 2025-12-31; that newer period is used below.")
        self.assertTrue(finance[1].startswith("Most recent figures in the accounts register (company accounts), reporting period 2025-01-01 to 2025-12-31: Revenue NOK 1,200"))
        self.assertTrue(finance[2].startswith("Most recent figures in the accounts register (group accounts), reporting period 2023-01-01 to 2023-12-31"), "each account type keeps its own period")
        self.assertNotIn("Latest annual accounts: 2024", envelope["company_summary"]["text"])
        self.assertIn("reporting period 2025-01-01 to 2025-12-31", statements(envelope, "at_a_glance")[2])
        behind, _ = summarise(accounts=[account("2024-01-01", "2024-12-31", 900, 50)])  # registry says 2025, figures stop at 2024
        self.assertEqual(statements(behind, "financial_snapshot")[0], "Enhetsregisteret records annual accounts submitted for 2025, but the accounts register returned figures only up to the period ending 2024-12-31; 2025 figures are not reported here.")
        self.assertIn("Figures for the 2025 annual accounts, which Enhetsregisteret records as submitted, were not in the accounts register's response.", statements(behind, "what_remains_unknown"))
        self.assertNotRegex(behind["company_summary"]["text"], r"[Ll]atest[^.\n]*2024")
        for item in (envelope, behind):
            self.assertSupported(item)

    def test_contradictory_trend_evidence_is_not_a_trend(self):
        # Revenue up then down over three years while the result moves the other way: only the latest pair is described.
        envelope, _ = summarise(accounts=[account("2023-01-01", "2023-12-31", 100, 10, record_id=3), account("2024-01-01", "2024-12-31", 300, 5, record_id=2), account("2025-01-01", "2025-12-31", 200, 40)])
        text = envelope["company_summary"]["text"]
        self.assertIsNone(TREND_WORDS.search(text.replace("“Utvikling av programvare”", "")), "no growth or trend wording")
        change = next(line for line in statements(envelope, "what_changed") if line.startswith("Compared with"))
        self.assertIn("revenue lower (NOK 300 to NOK 200)", change)
        self.assertIn("net result higher (NOK 5 to NOK 40)", change)
        self.assertNotIn("2023", change, "an older pair is not chained into a multi-year story")
        # Two figures for the same metric and period contradict each other: neither is reported or compared.
        conflict, _ = summarise(accounts=[account("2025-01-01", "2025-12-31", 1200, 60), account("2025-01-01", "2025-12-31", 1300, 60, record_id=9), account("2024-01-01", "2024-12-31", 900, 50, record_id=2)])
        self.assertNotIn("NOK 1,200", conflict["company_summary"]["text"])
        self.assertNotIn("NOK 1,300", conflict["company_summary"]["text"])
        self.assertIn("The accounts register states two different values for revenue (company accounts, 2025-01-01 to 2025-12-31); neither is reported.", statements(conflict, "what_remains_unknown"))
        self.assertNotIn("revenue", next(line for line in statements(conflict, "what_changed") if line.startswith("Compared with")))
        for item in (envelope, conflict):
            self.assertSupported(item)

    def test_no_conclusion_from_incomparable_periods(self):
        cases = {
            "short first year": ([account("2025-01-01", "2025-12-31", 1200, 60), account("2024-06-01", "2024-12-31", 300, 5, record_id=2)], "they are not both twelve-month periods"),
            "gap year": ([account("2025-01-01", "2025-12-31", 1200, 60), account("2023-01-01", "2023-12-31", 300, 5, record_id=2)], "they are not consecutive"),
            "changed currency": ([account("2025-01-01", "2025-12-31", 1200, 60, currency="EUR"), account("2024-01-01", "2024-12-31", 300, 5, record_id=2)], "they are reported in different currencies"),
        }
        for label, (accounts, reason) in cases.items():
            with self.subTest(label):
                envelope, _ = summarise(accounts=accounts)
                changed = " ".join(statements(envelope, "what_changed"))
                self.assertIn(f"{reason}, so no change is inferred", changed)
                self.assertNotRegex(changed, r"\b(?:higher|lower|unchanged)\b")
                self.assertSupported(envelope)

    def test_every_statement_is_supported_by_its_cited_claims(self):
        fixture = Fixture(HJS, base=C300_FIXTURES)
        replayed = run_batch([InputRow(0, HJS, HJS)], run_id="c300", **fixture.injected())["envelopes"][0]
        self.assertSupported(replayed)
        unknown_keys = {item["key"] for item in replayed["claims"] if item["availability"] != "available"}
        for section in replayed["company_summary"]["sections"]:
            if section["id"] in ("what_changed",):
                continue
            for statement in section["statements"]:
                self.assertTrue(statement["claim_keys"] or statement["text"].startswith(("Checked; nothing found", "Could not be checked", "Candidates were found", "Not applicable", "Not checked", "No checked category")),
                                f"{section['id']}: {statement['text']}")
                if not statement["evidence_ids"]:
                    self.assertLessEqual(set(statement["claim_keys"]), unknown_keys)
        # A deliberately unsupported statement is caught by the checker itself.
        broken = json.loads(json.dumps(replayed))
        broken["company_summary"]["sections"][0]["statements"][2]["text"] += " Revenue grew to NOK 9,999,999 by 2026-12-31."
        self.assertTrue(any("9,999,999" in problem for problem in unsupported_statements(broken)))
        self.assertTrue(any("2026-12-31" in problem for problem in unsupported_statements(broken)))
        self.assertTrue(any("trend or growth" in problem for problem in unsupported_statements(broken)))
        measured = ROOT / "measurements/official-audit-2026-10-03/unseen-1200/envelopes.jsonl.gz"
        if measured.exists():
            from norway_company_agent.synthesis import company_summary
            with gzip.open(measured, "rt") as handle:
                for _, line in zip(range(200), handle):
                    row = json.loads(line)
                    row["company_summary"] = company_summary(row)
                    self.assertEqual(unsupported_statements(row), [], row["organisation_number"])

    def test_missing_previous_snapshot(self):
        body = entity(ORG)
        envelope, profile = summarise(body, accounts=[account("2025-01-01", "2025-12-31", 1200, 60)])
        lone = [claim for claim in envelope["claims"] if claim["field"] == "roles_last_changed"]
        self.assertTrue(lone)
        changed = statements(envelope, "what_changed")
        self.assertEqual(changed[-1], "No previous run was supplied, so changes since an earlier observation by this agent are not assessed.")
        self.assertFalse([line for line in changed if line.startswith(("Changed:", "Added:", "No longer", "Compared with"))], "nothing is said to have changed without an earlier observation")
        self.assertEqual(envelope["refresh"]["compared"], False)
        bare = run_batch([InputRow(0, ORG, ORG)], run_id="s", **injected(FakeBrreg({ORG: body}, overrides={(ORG, "regnskapsregisteret"): (200, [account("2025-01-01", "2025-12-31", 1200, 60)]), (ORG, "/roller"): (200, {"rollegrupper": []})})))["envelopes"][0]
        self.assertEqual(statements(bare, "what_changed"), ["Not assessed: no previous run was supplied and the sources hold no earlier observation to compare with, so no change is reported."])
        refreshed, _ = summarise(body, accounts=[account("2025-01-01", "2025-12-31", 1250, 60)], previous=profile)
        self.assertIn("Changed: revenue (2025-01-01 to 2025-12-31) from 1200 to 1250.", statements(refreshed, "what_changed"), "with a previous run, the change is stated against it")
        for item in (envelope, bare, refreshed):
            self.assertSupported(item)


class ViewerExposure(unittest.TestCase):
    """C300 UX: the documented command must leave a usable viewer next to its envelopes, without any extra flag."""

    def run_cli(self, directory: Path, *extra: str) -> tuple[subprocess.CompletedProcess, dict]:
        (directory / "in.jsonl").write_text("".join(json.dumps({"organisation_number": org}) + "\n" for org in valid_orgs(3)))
        command = [sys.executable, str(ROOT / "tests/helpers/cli_with_fakes.py"), "--count", "3", "--", "--organisations", str(directory / "in.jsonl"),
                   "--output", str(directory / "out/envelopes.jsonl"), "--profiles-output", str(directory / "out/profiles.jsonl"),
                   "--report", str(directory / "out/report.json"), "--snapshot-dir", str(directory / "out/snapshots"), "--run-id", "c300", *extra]
        completed = subprocess.run(command, capture_output=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode()[-2000:])
        return completed, json.loads((directory / "out/report.json").read_text(encoding="utf-8"))

    def test_documented_command_writes_the_viewer_by_default(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            completed, report = self.run_cli(directory)
            viewer = directory / "out/envelopes.viewer.html"
            self.assertTrue(viewer.is_file(), "the manifest's command (no viewer flag) writes the viewer next to the envelopes")
            self.assertEqual(report["viewer"]["path"], str(viewer))
            self.assertTrue(report["viewer"]["written"])
            self.assertEqual(report["viewer"]["companies"], 3)
            self.assertEqual(json.loads(completed.stdout.decode())["viewer"], str(viewer))
            html = viewer.read_text(encoding="utf-8")
            self.assertIn("default-src 'none'", html)
            data = json.loads(html.split('<script type="application/json" id="data">', 1)[1].split("</script>", 1)[0])
            self.assertEqual(len(data["companies"]), 3)
            self.assertEqual(len(data["compare_rows"]), len(data["companies"][0]["cmp"]))
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            _, report = self.run_cli(directory, "--no-viewer")
            self.assertFalse((directory / "out/envelopes.viewer.html").exists())
            self.assertEqual(report["viewer"], {"written": False, "path": None, "reason": "disabled (--no-viewer)"})
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "blocked").mkdir()  # a directory where the viewer file should go: rendering cannot be written
            (directory / "blocked" / "keep").write_text("x")
            _, report = self.run_cli(directory, "--viewer-output", str(directory / "blocked"))
            self.assertFalse(report["viewer"]["written"], "a failed viewer never fails the run or loses the report")
            self.assertTrue(report["viewer"]["reason"])
            self.assertTrue(report["validation"]["passed"])

    def test_comparison_cells_cite_sources_and_keep_unknowns_unknown(self):
        from norway_company_agent.viewer import COMPARE_ROWS, project
        envelope, _ = summarise({**entity(ORG, employees=None), "harRegistrertAntallAnsatte": False}, accounts=[account("2025-01-01", "2025-12-31", 1500, 120), account("2024-01-01", "2024-12-31", 1000, 150, record_id=2)])
        projected = json.loads(json.dumps(project(envelope), default=str))
        cells = dict(zip([key for key, _ in COMPARE_ROWS], projected["cmp"]))
        self.assertEqual(cells["employees"], ["unknown (not published; not zero)", -1])
        self.assertEqual(cells["accounts"][0], "2025-01-01 to 2025-12-31 (company accounts)")
        self.assertEqual(cells["revenue"][0], "NOK 1,500", "the most recent period, as in the summary")
        source = projected["src"][projected["ev"][cells["revenue"][1]][0]]
        self.assertTrue(source[0].startswith("https://data.brreg.no/regnskapsregisteret/"))
        self.assertRegex(source[2], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(cells["website"], ["none found", -1])

    def test_compare_search_and_deep_links_in_a_headless_browser(self):
        node = shutil.which("node")
        modules = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        playwright = Path(modules) / "playwright"
        if not node or not playwright.exists():
            self.skipTest("node + playwright not installed")
        from norway_company_agent.viewer import render_viewer
        orgs = valid_orgs(3)
        brreg = FakeBrreg({org: entity(org, name=f"Selskap {index} AS") for index, org in enumerate(orgs)})
        rows = run_batch([InputRow(index, org, org) for index, org in enumerate(orgs)], run_id="v", **injected(brreg))["envelopes"]
        with tempfile.TemporaryDirectory() as raw:
            page = Path(raw) / "viewer.html"
            page.write_text(render_viewer(rows), encoding="utf-8")
            script = Path(raw) / "check.js"
            script.write_text("""
const { chromium } = require(process.env.PWPATH);
(async () => {
  const browser = await chromium.launch();
  const result = {};
  for (const [label, viewport] of [["desktop", {width: 1280, height: 800}], ["mobile", {width: 390, height: 844}]]) {
    const page = await browser.newPage({viewport});
    const errors = [], external = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("request", (r) => { if (!r.url().startsWith("file://")) external.push(r.url()); });
    await page.goto("file://" + process.argv[2] + "#org=" + process.argv[3]);
    await page.waitForSelector("#company-name");
    const deep = await page.textContent("#company-name");
    const groups = await page.$$eval("#detail h4", (nodes) => nodes.map((n) => n.textContent));
    const factOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    if (label === "mobile") await page.click("#back");
    await page.check("#list li >> nth=0 >> input[type=checkbox]");
    await page.check("#list li >> nth=2 >> input[type=checkbox]");
    await page.click("#cmpbtn");
    await page.waitForSelector("table.cmp");
    const header = await page.$$eval("table.cmp thead th", (nodes) => nodes.map((n) => n.textContent));
    const rows = await page.$$eval("table.cmp tbody tr", (nodes) => nodes.map((n) => n.textContent));
    const links = await page.$$eval("table.cmp td a", (nodes) => nodes.map((n) => n.getAttribute("href")));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    const hash = await page.evaluate(() => location.hash);
    if (label === "mobile") await page.click("#back");
    await page.selectOption("#sort", "name");
    result[label] = {errors, external, deep, groups, factOverflow, header, rows, links, overflow, hash, first: await page.textContent("#list li .name")};
  }
  console.log(JSON.stringify(result));
  await browser.close();
})();
""")
            completed = subprocess.run([node, str(script), str(page), orgs[1]], capture_output=True, text=True, timeout=120, env={**os.environ, "PWPATH": str(playwright)})
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            for label, outcome in json.loads(completed.stdout).items():
                with self.subTest(label):
                    self.assertEqual(outcome["errors"], [])
                    self.assertEqual(outcome["external"], [], "no request leaves the page")
                    self.assertEqual(outcome["deep"], "Selskap 1 AS", "a #org= link opens that company")
                    self.assertEqual([text.split(" (")[0] for text in outcome["groups"]], ["Identity and description", "Financials", "Leadership", "Locations"])
                    self.assertFalse(outcome["factOverflow"] or outcome["overflow"], "no horizontal page scroll")
                    self.assertTrue(outcome["header"][1].startswith("Selskap 0 AS") and outcome["header"][2].startswith("Selskap 2 AS"))
                    revenue = next(row for row in outcome["rows"] if row.startswith("Revenue"))
                    self.assertIn("NOK 1,000", revenue)
                    self.assertIn("retrieved 2026-10-03", revenue)
                    self.assertTrue(next(row for row in outcome["rows"] if row.startswith("Employees (registry)")).startswith("Employees (registry)3"))
                    self.assertTrue(outcome["links"] and all(link.startswith("https://data.brreg.no/") for link in outcome["links"]))
                    self.assertEqual(outcome["hash"], f"#compare={orgs[0]},{orgs[2]}")
                    self.assertEqual(outcome["first"], "Selskap 0 AS")


if __name__ == "__main__":
    unittest.main()
