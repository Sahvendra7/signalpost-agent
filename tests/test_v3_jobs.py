"""V3 §B7: job currency, employer and single-advertisement rules."""
from __future__ import annotations

import hashlib
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.attribution.jobs import currency, decide_job, employer  # noqa: E402
from norway_company_agent.attribution.names import LegalName  # noqa: E402
from norway_company_agent.site_facts import CapturedPage, extract_site_facts, parse_date, parse_deadline  # noqa: E402

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
RUN = date(2026, 11, 1)
LEGAL = LegalName("FJELL DATA AS")
RECRUITER = {"name": "BEMEX REKRUTTERING AS", "organisation_number": "995726742",
             "evidence": {"registry_live": {"value": {"industry": {"kode": "78.100"}}}}}


def page(url: str, html: str) -> CapturedPage:
    raw = html.encode("utf-8")
    return CapturedPage(url, raw, hashlib.sha256(raw).hexdigest(), "2026-11-01T08:00:00Z")


def posting(**fields) -> str:
    import json
    return f'<script type="application/ld+json">{json.dumps({"@type": "JobPosting", **fields})}</script>'


HOME = page("https://fjell-data.no/", "<html><body>Fjell Data AS</body></html>")


class Dates(unittest.TestCase):
    def test_future_deadlines_parse_and_publication_dates_still_reject_the_future(self):
        future = (datetime.now(timezone.utc) + timedelta(days=60)).strftime("%Y-%m-%d")
        self.assertEqual(parse_deadline(future), future, "a current advertisement's validThrough is kept (it used to be dropped)")
        self.assertIsNone(parse_date(future), "a publication date in the future is still rejected")
        self.assertEqual(parse_deadline("2019-04-01"), "2019-04-01")
        self.assertIsNone(parse_deadline("2099-01-01"), "more than 18 months ahead is not a plausible deadline")

    def test_currency_states(self):
        self.assertEqual(currency({"valid_through": "2026-11-20"}, RUN)[0], "open")
        self.assertEqual(currency({"application_deadline": "2026-11-01"}, RUN)[0], "open", "the deadline day itself is open")
        self.assertEqual(currency({"valid_through": "2019-04-01", "date_posted": "2019-03-01"}, RUN)[0], "expired")
        self.assertEqual(currency({"date_posted": "2026-10-20"}, RUN)[0], "recently_posted")
        self.assertEqual(currency({"date_posted": "2026-08-01"}, RUN)[0], "expired")
        self.assertEqual(currency({}, RUN)[0], "undated")


class Employer(unittest.TestCase):
    def test_named_employers(self):
        self.assertTrue(employer({"hiring_organization": "Fjell Data AS"}, LEGAL, "self", False).accepted)
        self.assertEqual(employer({"hiring_organization": "Helt Annet Firma AS"}, LEGAL, "self", False).code, "other_employer")
        self.assertEqual(employer({"employer_label": "Kunde AS"}, LEGAL, "self", True).code, "other_employer")

    def test_unstated_employer(self):
        self.assertEqual(employer({}, LEGAL, "self", False).code, "employer_presumed_own_careers_page")
        self.assertEqual(employer({}, LEGAL, "self", True).code, "employer_unstated_on_job_board")
        self.assertEqual(employer({}, LEGAL, "group_or_brand", False).code, "employer_unstated_on_shared_site")

    def test_recruiter_keeps_its_own_named_vacancy(self):
        legal = LegalName("BEMEX REKRUTTERING AS")
        decision = decide_job({"title": "Rekrutteringsrådgiver", "hiring_organization": "Bemex Rekruttering AS", "valid_through": "2026-12-01", "method": "jsonld_JobPosting"},
                              legal=legal, operator_kind="self", recruiter=True, run_date=RUN, on_news_page=False)
        self.assertTrue(decision.accepted, decision)

    def test_generic_recruitment_pages(self):
        for title in ("Åpen søknad", "Talentbank", "Sommerjobb", "Registrer CV"):
            with self.subTest(title=title):
                self.assertEqual(decide_job({"title": title, "valid_through": "2026-12-01"}, legal=LEGAL, operator_kind="self", recruiter=False, run_date=RUN, on_news_page=False).code, "generic_recruitment")


class Extraction(unittest.TestCase):
    def facts(self, profile, *pages):
        return extract_site_facts(profile, [HOME, *pages], now=NOW)

    def test_expired_posting_out_and_current_posting_kept_with_its_deadline(self):
        html = "<html><body>" + posting(title="Elektriker", datePosted="2019-03-01", validThrough="2019-04-01") + posting(title="Prosjektleder", datePosted="2026-10-20", validThrough="2026-12-15") + "</body></html>"
        facts = self.facts({"name": "Fjell Data AS"}, page("https://fjell-data.no/jobb/prosjektleder", html))
        self.assertEqual([(job["title"], job.get("valid_through"), job["currency"]["state"]) for job in facts.jobs], [("Prosjektleder", "2026-12-15", "open")])
        self.assertIn("job:expired", facts.rejections)

    def test_another_hiring_organization_is_not_this_company_s_vacancy(self):
        html = "<html><body>" + posting(title="Elektriker", validThrough="2026-12-01", hiringOrganization={"@type": "Organization", "name": "Helt Annet Firma AS"}) + "</body></html>"
        facts = self.facts({"name": "Fjell Data AS"}, page("https://fjell-data.no/jobb/elektriker", html))
        self.assertEqual(facts.jobs, [])
        self.assertIn("job:other_employer", facts.rejections)

    def test_posting_in_a_news_archive_is_not_current(self):
        html = "<html><body>" + posting(title="Elektriker", validThrough="2026-12-01") + "</body></html>"
        facts = self.facts({"name": "Fjell Data AS"}, page("https://fjell-data.no/aktuelt/gammel-annonse", html))
        self.assertEqual(facts.jobs, [])
        self.assertIn("job:job_on_news_page", facts.rejections)

    def test_careers_listing_with_passed_deadline_and_undated_listing(self):
        html = """<html><body><main><h1>Ledige stillinger</h1>
          <div><a href="/ledige-stillinger/montor"><h3>Montør</h3></a><p>Søknadsfrist: 15.09.2026</p><p>Fast stilling</p></div>
          <div><a href="/ledige-stillinger/lagerarbeider"><h3>Lagerarbeider</h3></a><p>Fast stilling</p></div>
          <div><a href="/ledige-stillinger/selger"><h3>Selger</h3></a><p>Søknadsfrist: 30.11.2026</p><p>Fast stilling</p></div></main></body></html>"""
        facts = self.facts({"name": "Fjell Data AS"}, page("https://fjell-data.no/ledige-stillinger/", html))
        self.assertEqual([(job["title"], job["currency"]["state"]) for job in facts.jobs], [("Selger", "open")])
        self.assertIn("job:expired", facts.rejections)
        self.assertIn("job:currency_unknown", facts.rejections)

    def test_recruiter_job_board_without_employer_is_held(self):
        html = """<html><body><main><h1>Ledige stillinger</h1>
          <div><a href="/ledige-stillinger/regnskapsforer"><h3>Regnskapsfører</h3></a><p>Søknadsfrist: 30.11.2026</p><p>Fast stilling</p></div></main></body></html>"""
        facts = self.facts(RECRUITER, page("https://fjell-data.no/ledige-stillinger/", html))
        self.assertEqual(facts.jobs, [])
        self.assertIn("job:employer_unstated_on_job_board", facts.rejections)


if __name__ == "__main__":
    unittest.main()
