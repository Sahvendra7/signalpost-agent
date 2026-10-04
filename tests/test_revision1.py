"""Revision 1: first-party site facts (social, dated news, jobs) become material, evidence-contained claims.

C12 regression cases replay the exact bytes our crawler captured for the named organisations (fixtures under
tests/fixtures/c12/, built by build_fixtures.py from a real run; nothing edited)."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.c12_replay import Fixture  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402
from norway_company_agent.site_facts import CapturedPage, article_links, extract_site_facts, job_listings, listing_items, validate_activity  # noqa: E402

SHA = "a" * 64


def page(url: str, html: str, kind: str = "html") -> CapturedPage:
    raw = html.encode("utf-8")
    return CapturedPage(url, raw, hashlib.sha256(raw).hexdigest(), "2026-10-04T12:00:00Z", kind=kind)


def replay(org: str, snapshot_root: Path | None = None):
    fixture = Fixture(org)
    output = run_batch([InputRow(0, org, org)], run_id="r1", snapshot_root=snapshot_root, **fixture.injected())
    return output["envelopes"][0], fixture


def available(envelope: dict, field: str) -> list[dict]:
    return [claim for claim in envelope["claims"] if claim["field"] == field and claim["availability"] == "available"]


def cited_bytes(envelope: dict, claim: dict, root: Path) -> bytes:
    item = next(entry for entry in envelope["evidence"] if entry["id"] == claim["evidence_ids"][0])
    return (root / item["snapshot_path"]).read_bytes()


class C12RegressionTests(unittest.TestCase):
    def test_811730912_facebook_and_instagram_on_own_site_are_material_social_claims(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope, _ = replay("811730912", root)
            social = available(envelope, "social_profile")
            self.assertEqual(sorted((claim["platform"], claim["value"]) for claim in social), [
                ("facebook", "https://www.facebook.com/MtmSkogservice"),
                ("instagram", "https://www.instagram.com/mtmskogservice/"),
            ])
            for claim in social:
                self.assertEqual(claim["category"], "public_activity", "a typed public-activity claim, not a websites sub-field")
                self.assertIsInstance(claim["value"], str, "the value is the profile URL itself")
                self.assertIn(claim["value"].encode(), cited_bytes(envelope, claim, root), "the URL occurs in the cited captured page")
                self.assertTrue(claim["source_page"].startswith("https://www.mtm-skogservice.no/"))
            self.assertEqual(validate_envelope(envelope, snapshot_root=root), [])
        self.assertFalse([claim for claim in envelope["claims"] if claim["category"] == "websites" and claim["field"] == "social_profile"])
        self.assertNotIn("youtube", {claim["platform"] for claim in social}, "a channel id carries no identity corroboration")
        self.assertEqual(envelope["area_coverage"]["public_footprint"], True)

    def test_838797172_granne_social_and_honest_hiring_and_news_states(self):
        envelope, fixture = replay("838797172")
        self.assertEqual(sorted((claim["platform"], claim["value"]) for claim in available(envelope, "social_profile")), [
            ("facebook", "https://www.facebook.com/granneforsikring"), ("linkedin", "https://www.linkedin.com/company/granneforsikring"),
        ])
        jobs = [claim for claim in envelope["claims"] if claim["field"] == "job_posting"]
        self.assertEqual([claim["availability"] for claim in jobs], ["not_available"], "the captured careers page lists no open position")
        self.assertIn("no positions are open", jobs[0]["reason"])
        self.assertEqual(available(envelope, "careers_page")[0]["value"], "https://www.granne.no/ledige-stillinger")
        news = [claim for claim in envelope["claims"] if claim["field"] == "news_item"]
        self.assertEqual([claim["availability"] for claim in news], ["not_available"], "no captured article states a date")
        articles = [url for url in fixture.calls if "/artikler/" in url]
        self.assertTrue(1 <= len(articles) <= 3, "article pages are followed only from the dateless listing, at most three")


class SocialRules(unittest.TestCase):
    HOME = "https://fjell-data.no/"

    def facts(self, body: str, name: str = "Fjell Data AS"):
        return extract_site_facts({"name": name}, [page(self.HOME, f"<html><body>{body}</body></html>")])

    def test_exact_linked_url_published_and_canonical_only_as_key(self):
        facts = self.facts('<footer><a href="https://www.facebook.com/FjellData/?ref=footer">Facebook</a><a href="https://facebook.com/fjelldata">FB</a></footer>')
        self.assertEqual([item["url"] for item in facts.profiles], ["https://facebook.com/fjelldata"], "one claim per profile; the plainest link")
        self.assertEqual(facts.profiles[0]["canonical_url"], "https://facebook.com/fjelldata")

    def test_partner_and_platform_default_links_are_not_the_company(self):
        facts = self.facts('<a href="https://www.facebook.com/unimicro">Uni Micro</a><a href="http://www.facebook.com/wix">x</a><a href="https://www.facebook.com/policies/cookies/">c</a>'
                           '<a href="https://www.facebook.com/sharer.php?u=x">del</a><a href="https://www.instagram.com/p/Cx1/">post</a>')
        self.assertEqual(facts.profiles, [])

    def test_name_match_alone_on_an_unrelated_page_is_not_enough(self):
        # The extractor never runs on unverified sites; when it runs, the link must be on the captured page.
        facts = extract_site_facts({"name": "Fjell Data AS"}, [])
        self.assertEqual(facts.profiles, [])

    def test_club_cross_links_keep_only_exact_legal_name_handles(self):
        links = "".join(f'<a href="https://www.instagram.com/{handle}/">ig</a>' for handle in ("fjelldata", "fjelldata_jr", "fjelldata_g16", "fjelldata_damer"))
        facts = self.facts(links)
        self.assertEqual([item["url"] for item in facts.profiles], ["https://www.instagram.com/fjelldata/"])

    def test_jsonld_sameas_of_own_organization_is_accepted(self):
        body = '<script type="application/ld+json">{"@type":"Organization","url":"https://fjell-data.no/","sameAs":["https://www.linkedin.com/company/fd-group"]}</script>'
        facts = self.facts(body)
        self.assertEqual([item["url"] for item in facts.profiles], ["https://www.linkedin.com/company/fd-group"])
        agency = '<script type="application/ld+json">{"@type":"Organization","url":"https://webbyraa.no/","name":"Webbyrå AS","sameAs":["https://www.linkedin.com/company/webbyraa"]}</script>'
        self.assertEqual(self.facts(agency).profiles, [])


class NewsRules(unittest.TestCase):
    LISTING = "https://fjell-data.no/aktuelt/"

    def test_visible_listing_dates_with_titles(self):
        html = """<html><body><main><h1>Aktuelt</h1>
        <div class="card"><a href="/aktuelt/ny-avtale-med-kommunen/"><h3>Ny avtale med kommunen</h3></a><span>12. september 2026</span><p>Fjell Data har signert en ny rammeavtale for drift av skolenes nettverk.</p></div>
        <div class="card"><a href="/aktuelt/vi-flytter/"><h3>Vi flytter til nye lokaler</h3></a><span>03.08.2026</span></div>
        </main></body></html>"""
        items = listing_items(page(self.LISTING, html), require_news_link=False)
        self.assertEqual([(item["date"], item["title"], item["url"]) for item in items], [
            ("2026-09-12", "Ny avtale med kommunen", "https://fjell-data.no/aktuelt/ny-avtale-med-kommunen/"),
            ("2026-08-03", "Vi flytter til nye lokaler", "https://fjell-data.no/aktuelt/vi-flytter/"),
        ])

    def test_updated_and_deadline_stamps_and_url_dates_are_never_publication_dates(self):
        html = """<html><body><main>
        <div><a href="/aktuelt/2026/09/12/nyhet/"><h3>Ny avtale med kommunen</h3></a><span>Oppdatert 12.09.2026</span></div>
        <div><a href="/aktuelt/kurs/"><h3>Kurs i nettverkssikkerhet</h3></a><span>Påmeldingsfrist 01.10.2026</span></div>
        </main></body></html>"""
        self.assertEqual(listing_items(page(self.LISTING, html), require_news_link=False), [])

    def test_validator_rejects_values_not_in_the_page(self):
        captured = page(self.LISTING, "<html><body><h3>Ny avtale med kommunen</h3><span>12. september 2026</span></body></html>")
        base = {"title": "Ny avtale med kommunen", "date": "2026-09-12", "date_text": "12. september 2026", "date_kind": "stated_on_page", "method": "listing_visible_date"}
        self.assertIsNone(validate_activity(base, captured))
        self.assertEqual(validate_activity({**base, "title": "Ny avtale med fylket"}, captured), "title_not_in_page")
        self.assertEqual(validate_activity({**base, "date": "2026-09-13", "date_text": "13. september 2026"}, captured), "date_not_stated_in_page")
        self.assertEqual(validate_activity({**base, "date_text": None}, captured), "no_explicit_date")
        self.assertEqual(validate_activity({**base, "date_kind": "updated"}, captured), "updated_timestamp_not_publication_date")

    def test_one_article_is_one_claim(self):
        article = page("https://fjell-data.no/aktuelt/ny-avtale/", """<html><head><meta property="article:published_time" content="2026-09-12T08:00:00+02:00">
        <script type="application/ld+json">{"@type":"NewsArticle","headline":"Ny avtale med kommunen","datePublished":"2026-09-12T08:00:00+02:00"}</script>
        <title>Ny avtale med kommunen</title></head><body><main><h1>Ny avtale med kommunen</h1><p>Publisert 12. september 2026</p></main></body></html>""")
        facts = extract_site_facts({"name": "Fjell Data AS"}, [page("https://fjell-data.no/", "<html><body>Fjell Data AS</body></html>"), article])
        self.assertEqual(len(facts.activities), 1)
        self.assertEqual(facts.activities[0]["method"], "jsonld_datePublished")

    def test_article_links_from_a_dateless_listing(self):
        html = """<html><body><nav><a href="/aktuelt/">Aktuelt</a></nav><main>
        <a href="/artikler/brannovelse-om-bord"><h3>Brannøvelse om bord i Sunderøy</h3></a><a href="/artikler/brannovelse-om-bord">Les mer</a>
        <a href="/vibori/"><h3>Hva gjør et sted til et hjem</h3></a>
        <a href="/aktuelt/side/2">Last inn flere artikler</a>
        <a href="/medlem/aktuelt/scrooge-et-juleeventyr/"><h3>Velkommen til årets juleforestilling</h3></a>
        </main><footer><a href="/aktuelt/personvern/">Personvern</a></footer></body></html>"""
        self.assertEqual(article_links(page("https://fjell-data.no/aktuelt", html), 3), [
            "https://fjell-data.no/artikler/brannovelse-om-bord", "https://fjell-data.no/medlem/aktuelt/scrooge-et-juleeventyr/",
        ])


class JobRules(unittest.TestCase):
    CAREERS = "https://fjell-data.no/ledige-stillinger/"

    def test_listed_positions_become_postings_with_stated_fields_only(self):
        html = """<html><body><main><h1>Ledige stillinger</h1>
        <div><a href="/ledige-stillinger/driftstekniker-oslo/"><h3>Driftstekniker</h3></a><p>Arbeidssted: Oslo</p><p>Søknadsfrist: 15.10.2026</p><p>Fast stilling, 100 %</p></div>
        <div><a href="https://fjelldata.webcruiter.no/Main2/Recruit/Public/123">Prosjektleder infrastruktur</a></div>
        <a href="/ledige-stillinger/">Ledige stillinger</a><a href="/jobb-hos-oss/kultur/">Vår kultur</a>
        </main></body></html>"""
        jobs, reason = job_listings(page(self.CAREERS, html))
        self.assertIsNone(reason)
        self.assertEqual([(job["title"], job.get("location"), job.get("application_deadline")) for job in jobs], [
            ("Driftstekniker", "Oslo", "2026-10-15"), ("Prosjektleder infrastruktur", None, None),
        ])
        self.assertNotIn("date_posted", jobs[0], "no posting date is invented")

    def test_generic_careers_page_is_not_a_posting(self):
        for body in ("<h1>Karriere</h1><p>Vi er alltid på jakt etter flinke folk. Send en åpen søknad.</p><a href='/karriere/apen-soknad/'>Åpen søknad</a>",
                     "<h1>Ledige stillinger</h1><p>Her oppdaterer vi så snart det kommer ledige stillinger i Fjell Data.</p>"):
            with self.subTest(body[:30]):
                jobs, reason = job_listings(page(self.CAREERS, f"<html><body><main>{body}</main></body></html>"))
                self.assertEqual(jobs, [])
                self.assertTrue(reason)

    def test_one_job_page_is_one_posting(self):
        html = """<html><body><main><h1>Ledige stillinger</h1>
        <div><a href="/ledige-stillinger/driftstekniker/"><h3>Driftstekniker</h3></a><a href="/ledige-stillinger/driftstekniker/">Driftstekniker</a><p>Fast stilling</p></div>
        <script type="application/ld+json">{"@type":"JobPosting","title":"Driftstekniker","datePosted":"2026-09-20","url":"https://fjell-data.no/ledige-stillinger/driftstekniker/"}</script>
        </main></body></html>"""
        facts = extract_site_facts({"name": "Fjell Data AS"}, [page("https://fjell-data.no/", "<html><body>Fjell Data</body></html>"), page(self.CAREERS, html)])
        self.assertEqual([(job["title"], job["url"]) for job in facts.jobs], [("Driftstekniker", "https://fjell-data.no/ledige-stillinger/driftstekniker/")])


if __name__ == "__main__":
    unittest.main()
