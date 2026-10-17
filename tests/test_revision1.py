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
from norway_company_agent.site_identity import classify_site, manager_designated  # noqa: E402
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


class ManagerDesignatedTests(unittest.TestCase):
    """A registry-designated website run by the entity's registered business manager (C12 case 813396092)."""

    def test_813396092_bori_site_association_kept_manager_news_not_attributed(self):
        """bori.no is associated with SAMEIE JESSHEIM PARK DRIFT (its registry record names it; BORI BBL is its
        forretningsfører), but bori.no/aktuelt is BORI BBL's own news: none of it names the sameie."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelope, _ = replay("813396092", root)
            website = available(envelope, "official_website")[0]
            self.assertEqual(website["value"], "https://www.bori.no/")
            self.assertEqual(website["identity_class"], "MANAGER_DESIGNATED")
            self.assertEqual(website["operated_by"], {"organisation_number": "989987011", "name": "BORI BBL", "registry_role": "forretningsfører"})
            self.assertLess(website["confidence"], 0.95)
            self.assertEqual(validate_envelope(envelope, snapshot_root=root), [])
        states = {claim["field"]: (claim["availability"], claim.get("reason") or "") for claim in envelope["claims"] if claim["field"] in ("social_profile", "news_item", "job_posting", "careers_page")}
        self.assertEqual({field: state for field, (state, _) in states.items()}, {"social_profile": "not_applicable", "news_item": "not_applicable", "job_posting": "not_applicable"},
                         "the manager's profiles, news and vacancies are not the sameie's")
        self.assertIn("3 dated item(s) on the site, none naming it", states["news_item"][1])

    def manager_result(self, items: list[dict], pages: list[CapturedPage]):
        from norway_company_agent.site_research import SiteResult, apply_site_facts
        from norway_company_agent.site_facts import SiteFacts
        result = SiteResult(status="verified", site_url="https://www.forvalter.no/", identity_class="MANAGER_DESIGNATED",
                            manager={"organisation_number": "989987011", "name": "FORVALTER BBL"})
        facts = SiteFacts()
        facts.activities = items
        facts.jobs = [{"title": "Forvaltningskonsulent", "url": "https://www.forvalter.no/jobb/1", "page_url": "https://www.forvalter.no/jobb"}]
        apply_site_facts(result, facts, self.entity(), pages)
        return result

    def test_manager_news_published_only_when_the_item_names_the_entity(self):
        listing_url = "https://www.forvalter.no/aktuelt"
        article_url = "https://www.forvalter.no/aktuelt/rehabilitering-testgarden"
        listing = page(listing_url, "<html><body><h1>Aktuelt</h1><p>Vi forvalter blant annet Sameiet Testgården.</p></body></html>")
        article = page(article_url, "<html><body><h1>Fasaden rehabiliteres</h1><p>Styret i Sameiet Testgården har vedtatt rehabilitering. Org.nr. 913 396 091.</p></body></html>")
        other = page("https://www.forvalter.no/aktuelt/annet", "<html><body><h1>Testgården borettslag får ny lekeplass</h1></body></html>")
        item = lambda title, url, where, **extra: {"title": title, "url": url, "date": "2026-09-30", "page_url": where.url, **extra}
        result = self.manager_result([
            item("Usbl etablerer Eida Eiendomsmegling", listing_url + "/eida", listing),
            item("Bli medlem: vi spanderer kontingenten", listing_url + "/medlem", listing),
            item("Testgården borettslag får ny lekeplass", other.url, other),
            item("Fasaden rehabiliteres", article_url, article),
            item("Nytt fra Sameiet Testgården", listing_url + "/nytt", listing),
            item("Årsmøte", listing_url + "/arsmote", listing, summary="Innkalling for 913396091."),
            item("Sameiet Testgården II får nye vinduer", listing_url + "/ii", listing),
            item("Dugnad i Sameiet Testgården Drift", listing_url + "/drift", listing),
            item("Sameiet Testgården 2 velger nytt styre", listing_url + "/2", listing),
        ], [listing, article, other])
        kept = {entry["title"]: entry["subject_basis"] for entry in result.activities}
        self.assertEqual(kept, {
            "Fasaden rehabiliteres": "organisation number 913396091 in the item's article page",
            "Nytt fra Sameiet Testgården": "legal name SAMEIET TESTGÅRDEN in the item's title",
            "Årsmøte": "organisation number 913396091 in the item's summary",
        }, "the manager's own news, distinctive words alone, a longer name of another entity and the listing page's text are not attribution")
        self.assertEqual(result.extraction_rejections["activity:manager_news_not_about_entity"], 6)
        self.assertEqual((result.jobs, result.careers_page), ([], None), "the manager's vacancies are never the entity's")

    def test_records_without_subject_basis_are_not_published(self):
        """A stored manager-site record from before the attribution rule (no subject_basis) publishes no news."""
        from norway_company_agent.claims import ClaimSet, _site_research_claims
        claims = ClaimSet()
        record = {"status": "available", "value": {
            "site_url": "https://www.forvalter.no/", "identity_class": "MANAGER_DESIGNATED", "identity_reasons": ["x"],
            "manager": {"organisation_number": "989987011", "name": "FORVALTER BBL"}, "pages": [{"content_sha256": SHA, "retrieved_at": "2026-10-04T12:00:00Z"}],
            "activities": [{"title": "Usbl etablerer Eida Eiendomsmegling", "date": "2026-09-30", "page_url": "https://www.forvalter.no/aktuelt", "content_sha256": SHA, "retrieved_at": "2026-10-04T12:00:00Z"}],
        }}
        _site_research_claims(claims, record, v1_site_published=False)
        news = [claim for claim in claims.claims if claim["field"] == "news_item"]
        self.assertEqual([claim["availability"] for claim in news], ["not_applicable"])

    PAGE = '<html><head><title>Forvalter BBL</title></head><body><p>Kontakt: post@forvalter.no</p>{extra}</body></html>'

    def entity(self, manager_number: str | None = "989987011", role: str = "FFØR") -> dict:
        roles = [{"role_code": role, "name": ["FORVALTER BBL"], "organisation_number": manager_number}] if manager_number else []
        return {"organisation_number": "913396091", "name": "SAMEIET TESTGÅRDEN", "business_address": {},
                "evidence": {"roles": {"value": {"roles": roles}}}}

    def check(self, entity: dict, extra: str, email: str | None = "forvaltning@forvalter.no"):
        html = [self.PAGE.format(extra=extra)]
        verdict = classify_site(entity, "forvalter.no", html, registry_email=email)
        return verdict, manager_designated(entity, "forvalter.no", html, verdict, registry_email=email)

    def test_all_official_links_required(self):
        verdict, manager = self.check(self.entity(), "<footer>Org.nr. 989 987 011</footer>")
        self.assertEqual(verdict["class"], "AMBIGUOUS")
        self.assertEqual(manager["organisation_number"], "989987011")
        self.assertIsNotNone(self.check(self.entity(), '<template><a href="mailto:989987011@forvalter.no">faktura</a></template>')[1], "contact-dialog template counts")

    def test_any_missing_link_rejects(self):
        cases = {
            "manager number not on the site": (self.entity(), "<footer>Org.nr. 999 888 777</footer>", "forvaltning@forvalter.no"),
            "number only inside a script": (self.entity(), "<script>var id=989987011;</script>", "forvaltning@forvalter.no"),
            "not the registered forretningsfører (accountant only)": (self.entity(role="REGN"), "<footer>989 987 011</footer>", "forvaltning@forvalter.no"),
            "no registered manager": (self.entity(None), "<footer>989 987 011</footer>", "forvaltning@forvalter.no"),
        }
        for label, (entity, extra, email) in cases.items():
            with self.subTest(label):
                self.assertIsNone(self.check(entity, extra, email)[1])

    def test_no_control_signal_or_contrary_identity_rejects(self):
        html = ['<html><body><p>Kontakt oss på skjema.</p><footer>989 987 011</footer></body></html>']
        verdict = classify_site(self.entity(), "forvalter.no", html, registry_email="styret@gmail.com")
        self.assertIsNone(manager_designated(self.entity(), "forvalter.no", html, verdict, registry_email="styret@gmail.com"), "no registry e-mail on the site's domain and no own mailbox")
        directory = ['<html><body>' + "".join(f"<p>Org {n} 123 45{i}</p>" for i, n in enumerate(("911", "922", "933", "944"))) + '<p>post@forvalter.no</p><footer>989 987 011</footer></body></html>']
        verdict = classify_site(self.entity(), "forvalter.no", directory, registry_email="forvaltning@forvalter.no")
        self.assertEqual(verdict["class"], "DIRECTORY")
        self.assertIsNone(manager_designated(self.entity(), "forvalter.no", directory, verdict, registry_email="forvaltning@forvalter.no"))


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


class AuditRegressions(unittest.TestCase):
    """Defects found by the manual audit of the same-day 1,200-company measurement; each must stay fixed."""

    def test_section_of_a_shared_domain_does_not_inherit_the_owner_profiles(self):
        # 971531983 NHF REGION INNLANDET: verified site https://www.handball.no/regioner/regioninnlandet/ links the
        # federation's own profiles in its chrome; "handball" occurring in "norgeshandballforbund" is not identity.
        region = page("https://www.handball.no/regioner/regioninnlandet/", """<html><body><footer>
            <a href="https://www.facebook.com/norgeshandballforbund">Facebook</a><a href="https://www.instagram.com/norgeshandballforbund/">Instagram</a>
            <a href="https://www.facebook.com/nhfregioninnlandet">Region Innlandet</a></footer></body></html>""")
        facts = extract_site_facts({"name": "NHF REGION INNLANDET"}, [region])
        self.assertEqual([item["url"] for item in facts.profiles], ["https://www.facebook.com/nhfregioninnlandet"], "only the legal-name handle")

    def test_language_homepage_is_not_a_shared_section(self):
        home = page("https://smarthotel.no/no", '<html><body><a href="https://www.facebook.com/smarthotelnorge">f</a></body></html>')
        self.assertEqual([item["url"] for item in extract_site_facts({"name": "SMARTHOTEL FORUS AS"}, [home]).profiles], ["https://www.facebook.com/smarthotelnorge"])

    def test_domain_name_must_begin_or_end_the_handle(self):
        home = page("https://handball.no/", '<html><body><a href="https://www.facebook.com/norgeshandballforbund">f</a><a href="https://www.instagram.com/handballnorge/">i</a></body></html>')
        # Legal name unrelated to either handle, so only the domain-name rule can apply.
        self.assertEqual([item["url"] for item in extract_site_facts({"name": "BALLSPORT DRIFT AS"}, [home]).profiles], ["https://www.instagram.com/handballnorge/"])

    def test_dated_list_inside_an_article_is_not_a_news_listing(self):
        # 928934977 Altinget: an article listing 30 dated milestones produced one "news item" per milestone.
        article = page("https://altinget.no/artikkel/30-milepaeler", """<html><head><meta property="article:published_time" content="2026-09-07T06:00:00Z"><title>30 milepæler for Altinget i Norge</title></head>
        <body><main><h1>30 milepæler for Altinget i Norge</h1>
        <div><h3>29. Dok 8-forslag, regjeringskrise og landsmøter</h3><span>24.08.2026</span></div>
        <div><h3>1. Med et tastetrykk fra ministeren åpner Altinget</h3><span>03.10.2022</span></div></main></body></html>""")
        facts = extract_site_facts({"name": "ALTINGET AS"}, [page("https://altinget.no/", "<html><body>Altinget</body></html>"), article])
        self.assertEqual([item["title"] for item in facts.activities], ["30 milepæler for Altinget i Norge"])

    def test_cms_page_dates_do_not_make_pages_news_and_listings_still_parse(self):
        # 816945852 (usbl.no): Yoast types every page as a dated Article. The /om-oss/nyheter listing must still be
        # read for its items; its own "Nyheter" headline and a dated careers page are not news items.
        stamp = '<script type="application/ld+json">{{"@type":"Article","headline":"{0}","datePublished":"2019-11-09T10:00:00+01:00"}}</script>'
        listing = page("https://www.usbl.no/om-oss/nyheter", "<html><head>" + stamp.format("Nyheter") + """</head><body><main><h1>Nyheter</h1>
            <div><a href="/om-oss/nyheter/eida"><h3>Usbl etablerer Eida Eiendomsmegling</h3></a><span>10.08.2026</span></div></main></body></html>""")
        careers = page("https://www.usbl.no/om-oss/jobb-hos-oss", "<html><head>" + stamp.format("Bli en del av laget!") + "</head><body><h1>Bli en del av laget!</h1></body></html>")
        facts = extract_site_facts({"name": "BOLIGBYGGELAGET USBL"}, [page("https://www.usbl.no/", "<html><body>Usbl</body></html>"), listing, careers])
        self.assertEqual([item["title"] for item in facts.activities], ["Usbl etablerer Eida Eiendomsmegling"])

    def test_author_and_staff_links_are_never_the_item(self):
        # 980429849 Edge Branding ("Yvonne Aasbø" -> /ansatte/...), 928934977 Altinget (/person/...).
        html = """<html><body><main><h1>Aktuelt</h1>
        <div class="card"><a href="/ansatte/yvonne-aasbo">Yvonne Aasbø</a><span>30.09.2026</span></div>
        <div class="card"><h3>Stønadslandet Norge: store geografiske forskjeller</h3><a href="/person/solveig-ruud">Solveig Ruud</a><a href="/aktuelt/stonadslandet">Les saken</a><span>07.09.2026</span></div>
        </main></body></html>"""
        items = listing_items(page("https://fjell-data.no/aktuelt/", html), require_news_link=False)
        self.assertEqual([(item["title"], item["url"]) for item in items], [("Stønadslandet Norge: store geografiske forskjeller", "https://fjell-data.no/aktuelt/stonadslandet")])

    def test_application_and_careers_links_are_not_job_titles(self):
        # 998549833 Northern Beat ("Registrer din søknad"), 813302632 Arkwright ("Careers in Oslo").
        html = """<html><body><main><h1>Karriere</h1>
        <a href="https://northernbeat.recman.no/job.php?job_id=236687&apply_only">Registrer din søknad</a>
        <a href="https://emp.jobylon.com/jobs/280573-arkwright-consulting-rekruttering/">Careers in Oslo</a>
        <a href="https://fjelldata.webcruiter.no/Main2/Recruit/Public/99">Senior utvikler backend</a></main></body></html>"""
        jobs, _ = job_listings(page("https://fjell-data.no/karriere/", html))
        self.assertEqual([job["title"] for job in jobs], ["Senior utvikler backend"])


class FinalAuditRegressions(unittest.TestCase):
    """Defects found by the manual audit of the final same-day 1,200 and 400 runs (Revision 1 candidate)."""

    def test_a_date_inside_running_text_is_not_a_publication_date(self):
        # 998243432 Orkla Regnskap, 926642510 Aksjefabrikken, 920186114 Devold Møllers stiftelse, 883759702 FDVhuset.
        cards = {
            "orkla": '<a href="/2025/09/18/skattetrekkskontoen/"><h3>Skattetrekkskontoen blir avviklet</h3></a><p>Fra 1. januar 2026 fjernes kravet om at forskuddstrekk skal overføres til en skattetrekkskonto.</p>',
            "aksjefabrikken": '<a href="/elementor-5202/"><h3>Forretningsvilkår for forskuddsbetaling over nett</h3></a><p>Aksjefabrikken AS, org.nr. 926 642 510. Gjeldende fra 1. august 2026.</p>',
            "devold": '<a href="/post-3/"><h3>Stiftelsen etablert</h3></a><p>Stiftelsen ble opprettet 31. januar 2018</p>',
            "fdvhuset": '<a href="/blogg/famac-seminar/"><h3>FAMAC seminar, Sola Strand Hotell</h3></a><p>FAMAC-seminar 26. – 27. september 2024</p>',
        }
        for label, card in cards.items():
            with self.subTest(label):
                self.assertEqual(listing_items(page("https://fjell-data.no/aktuelt/", f"<html><body><main><div>{card}</div></main></body></html>"), require_news_link=False), [])

    def test_date_stamps_with_cues_weekdays_bylines_and_labels_are_kept(self):
        # 925114510 Skan-Kontroll ("fredag 4. september 2026"), 985701547 Wican ("September 25, 2026 • 4 min lesetid").
        stamps = ["fredag 4. september 2026", "September 25, 2026 • 4 min lesetid", "Publisert 12. mars 2026 av Kari Nordmann", "Nyheter | 12.03.2026", "5. mai 2016"]
        for stamp in stamps:
            with self.subTest(stamp):
                html = f'<html><body><main><div><a href="/aktuelt/ny-avtale/"><h3>Ny avtale med kommunen</h3></a><span>{stamp}</span></div></main></body></html>'
                self.assertEqual(len(listing_items(page("https://fjell-data.no/aktuelt/", html), require_news_link=False)), 1)

    def test_one_article_url_is_one_claim_and_the_structured_date_wins(self):
        feed = page("https://fjell-data.no/feed/", """<rss><channel><item><title>Ny avtale med kommunen</title>
            <link>https://fjell-data.no/2025/09/18/ny-avtale/</link><pubDate>Thu, 18 Sep 2025 08:18:56 +0000</pubDate></item></channel></rss>""", kind="feed")
        listing = page("https://fjell-data.no/aktuelt/", """<html><body><main><div><a href="/2025/09/18/ny-avtale/"><h3>Ny avtale med kommunen (oppdatert)</h3></a>
            <span>3. oktober 2025</span></div></main></body></html>""")
        home = page("https://fjell-data.no/", "<html><body><a href='/aktuelt/'>Aktuelt</a></body></html>")
        facts = extract_site_facts({"name": "FJELL DATA AS"}, [home, listing], [feed])
        self.assertEqual([(item["date"][:10], item["method"]) for item in facts.activities], [("2025-09-18", "site_feed")])

    def test_an_article_page_heading_is_the_page_itself(self):
        # 925503215 Vasser (related-article link), 931624032 All Gravy (breadcrumb to /blog) became the item URL.
        html = """<html><body><main><article><a href="/blogg">Blogg</a><h1>CMS i 2026: trenger vi fortsatt et publiseringssystem?</h1>
            <span>17. september 2026</span><p>Les også: <a href="/blogg/hva-er-et-cms">Hva er et CMS?</a></p></article></main></body></html>"""
        items = listing_items(page("https://www.vasser.no/blogg/cms-i-2026", html), require_news_link=False)
        self.assertEqual([(item["title"], item["url"]) for item in items], [("CMS i 2026: trenger vi fortsatt et publiseringssystem?", "https://www.vasser.no/blogg/cms-i-2026")])

    def test_author_and_category_archive_links_are_never_items(self):
        # 917939527 Ålhytta (?author=...), 923143785 Arkitekt Sandmark (/category/byggesak/).
        html = """<html><body><main>
            <div><a href="/inspirasjon-artikler?author=545fb58de4b073a05b4eb41d">Erlend Hagen</a><span>20. desember 2023</span></div>
            <div><a href="/category/byggesak/">Byggesak og regelverk</a><span>22. oktober 2023</span></div>
            </main></body></html>"""
        self.assertEqual(listing_items(page("https://fjell-data.no/aktuelt/", html), require_news_link=False), [])

    def test_section_of_a_shared_domain_does_not_inherit_the_owner_news(self):
        # 930870781 Læringsverkstedet Tveit: verified site /barnehage/tveit; the chain's blog post is not its news.
        section = page("https://laringsverkstedet.no/barnehage/tveit", """<html><body><main>
            <div><a href="https://laringsverkstedet.no/blogg/juridisk-og-baerekraft"><h3>Juridisk og bærekraft</h3></a><span>19. mars 2024</span></div>
            <div><a href="https://laringsverkstedet.no/barnehage/tveit/nyheter/sommerfest"><h3>Sommerfest på Tveit</h3></a><span>12. juni 2026</span></div>
            </main></body></html>""")
        facts = extract_site_facts({"name": "LÆRINGSVERKSTEDET TVEIT BARNEHAGE AS"}, [section])
        self.assertEqual([item["title"] for item in facts.activities], ["Sommerfest på Tveit"])
        self.assertEqual(facts.rejections.get("activity:outside_site_section"), 1)

    def test_a_news_archive_of_job_ads_is_not_a_careers_page(self):
        # 980429849 Edge Branding: /aktuelt/tema/ledig-stilling lists old ads; its careers page lists no position.
        archive = page("https://edgebranding.no/aktuelt/tema/ledig-stilling", """<html><body><main><h1>Aktuelt</h1>
            <div><a href="/aktuelt/ledig-stilling-performance"><h3>Er du vår nye Performance-spesialist?</h3></a><span>Ledig stilling</span></div>
            </main></body></html>""")
        self.assertEqual(extract_site_facts({"name": "EDGE BRANDING AS"}, [page("https://edgebranding.no/", "<html></html>"), archive]).jobs, [])


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

    def test_homepage_page_level_dates_dropped_but_homepage_article_cards_kept(self):
        # Regression found in the 1,200 measurement (985032726): <article><time> cards on the homepage without
        # their own link are news items; the homepage's own article:published_time is not.
        home = page("https://fjell-data.no/", """<html><head><meta property="article:published_time" content="2026-01-02T08:00:00Z"><title>Fjell Data AS</title></head>
        <body><article><h3>Revejakta har startet</h3><time datetime="2026-07-24">24. juli 2026</time></article></body></html>""")
        facts = extract_site_facts({"name": "Fjell Data AS"}, [home])
        self.assertEqual([(item["title"], item["method"]) for item in facts.activities], [("Revejakta har startet", "article_time_datetime")])

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
