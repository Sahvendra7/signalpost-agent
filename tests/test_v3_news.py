"""V3 §B6: item-level news classification, publication time selection, bursts and subject."""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.site_facts import CapturedPage, extract_site_facts, html_items  # noqa: E402

SITE = "https://fjell-data.no/"


def page(url: str, html: str, kind: str = "html") -> CapturedPage:
    raw = html.encode("utf-8")
    return CapturedPage(url, raw, hashlib.sha256(raw).hexdigest(), "2026-11-01T08:00:00Z", kind=kind)


def feed(items: list[tuple[str, str, str, list[str]]]) -> CapturedPage:
    body = "".join(f"<item><title>{title}</title><link>{link}</link><pubDate>{date}</pubDate>{''.join(f'<category>{c}</category>' for c in cats)}</item>"
                   for title, link, date, cats in items)
    return page(SITE + "feed/", f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>", kind="feed")


HOME = page(SITE, "<html><body>Fjell Data AS</body></html>")


def titles(facts) -> list[str]:
    return sorted(item["title"] for item in facts.activities)


class TimeSelection(unittest.TestCase):
    def test_published_time_wins_over_an_earlier_updated_time(self):
        html = ('<article><a href="https://fjell-data.no/blogg/x"><h2>Ny avtale med kommunen</h2></a><time class="updated" datetime="2026-10-30">30. okt</time>'
                '<time class="entry-date published" datetime="2015-01-01">1. jan 2015</time></article>')
        self.assertEqual([(item["date"], item["date_kind"]) for item in html_items(html, SITE + "blogg/")], [("2015-01-01", "published")])

    def test_a_lone_hatom_updated_time_is_a_stated_date_not_a_publication_date(self):
        html = '<article><h2><a href="https://fjell-data.no/x">Ny avtale med kommunen</a></h2><time class="date-container updated" datetime="2025-10-29">29.10.2025</time></article>'
        self.assertEqual([item["date_kind"] for item in html_items(html, SITE + "nyheter/")], ["stated_on_page"])

    def test_conflicting_updated_only_times_give_no_date(self):
        html = '<article><h2>Ny avtale</h2><time class="updated" datetime="2025-10-29">a</time><time itemprop="dateModified" datetime="2025-11-01">b</time></article>'
        self.assertEqual(html_items(html, SITE + "nyheter/"), [])

    def test_archive_links_are_not_the_item_url(self):
        html = ('<article><a href="/category/aktuelt/">Aktuelt</a><h2><a href="/breeam-sertifisering/">BREEAM sertifisering i boks</a></h2>'
                '<time datetime="2025-10-29">29.10.2025</time><a href="/author/linda/">Linda</a></article>')
        self.assertEqual([item["url"] for item in html_items(html, SITE + "nyheter/")], ["https://fjell-data.no/breeam-sertifisering/"])


class ItemGate(unittest.TestCase):
    def test_plain_slug_posts_in_the_main_feed_are_kept(self):
        posts = [(f"Kampreferat runde {n} mot Storhamar", f"https://fjell-data.no/kampreferat-{n}/", f"Mon, 0{n} Sep 2026 12:00:00 +0000", ["Nyheter"]) for n in range(1, 4)]
        self.assertEqual(len(extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)]).activities), 3)

    def test_a_bulk_entry_burst_is_not_news(self):
        posts = [(f"Brl prosjekt nummer {n}", f"https://fjell-data.no/brl-{n}/", f"Tue, 17 Feb 2026 10:5{n}:00 +0000", ["Uncategorized"]) for n in range(5)]
        facts = extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)])
        self.assertEqual(facts.activities, [])
        self.assertTrue(any(key.startswith("activity:") for key in facts.rejections))

    def test_three_posts_in_one_hour_are_not_a_burst(self):
        posts = [(f"Kampreferat runde {n} mot Storhamar", f"https://fjell-data.no/kampreferat-{n}/", f"Mon, 07 Sep 2026 12:{n}0:00 +0000", ["Nyheter"]) for n in range(3)]
        self.assertEqual(len(extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)]).activities), 3)

    def test_project_categories_media_files_and_default_posts(self):
        posts = [("Ortun badeanlegg ferdigstilt", "https://fjell-data.no/ortun/", "Thu, 12 Dec 2024 13:37:11 +0000", ["Næringsbygg / offentlig"]),
                 ("Hello world!", "https://fjell-data.no/hello-world/", "Fri, 03 Jan 2025 10:00:00 +0000", ["Uncategorized"]),
                 ("Brosjyre for våre tjenester", "https://fjell-data.no/media/brosjyre.pdf", "Fri, 07 Mar 2025 10:00:00 +0000", ["Nyheter"]),
                 ("Ny leveranse til Statens vegvesen", "https://fjell-data.no/ny-leveranse/", "Fri, 07 Feb 2025 10:00:00 +0000", ["Nyheter"])]
        facts = extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)])
        self.assertEqual(titles(facts), ["Ny leveranse til Statens vegvesen"])
        for code in ("project_category", "default_cms_post", "media_file"):
            self.assertIn(f"activity:{code}", facts.rejections)

    def test_uncategorized_is_not_a_project_category_and_a_reused_post_date_is_rejected(self):
        # Phase 4 dev audit: "Uncategorized" (the CMS default) lost two correct posts; reused posts kept a 2018 date.
        posts = [("Tildeling av stipender 2026", "https://fjell-data.no/tildeling-2026/", "Thu, 11 Jun 2026 08:59:14 +0000", ["Uncategorized"]),
                 ("Utlysing 2026", "https://fjell-data.no/post-2/", "Mon, 09 Jul 2018 17:09:24 +0000", ["Uncategorized"]),
                 ("17. mai på gården 2018", "https://fjell-data.no/17-mai/", "Thu, 17 May 2018 17:43:05 +0000", ["Uncategorized"])]
        facts = extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)])
        self.assertEqual(titles(facts), ["17. mai på gården 2018", "Tildeling av stipender 2026"])
        self.assertIn("activity:date_contradicts_title", facts.rejections)

    def test_service_cards_outside_the_news_section_are_not_news(self):
        cards = "".join(f'<div><h3><a href="/inspirasjon-artikler/{slug}">{title}</a></h3><p>Publisert {date}</p></div>' for slug, title, date in
                        [("ny-visningshytte", "Ny visningshytte på Hellerud", "21.01.2026"), ("hytta-pa-fjellet", "Odd og Kristin leier ut hytta", "29.03.2023")])
        cards += '<div><h3><a href="/nokkelferdig-hytte">Hvorfor velge en nøkkelferdig hytte?</a></h3><p>Publisert 19.08.2021</p></div>'
        listing = page(SITE + "inspirasjon-artikler", f"<html><body><main>{cards}</main></body></html>")
        facts = extract_site_facts({"name": "Fjell Data AS"}, [HOME, listing])
        self.assertNotIn("Hvorfor velge en nøkkelferdig hytte?", titles(facts))

    def test_product_and_contact_pages_with_page_times_are_not_news(self):
        contact = page(SITE + "om-oss/presserom/pressekontakter", '<html><body><article><h1>Lokale pressekontakter</h1><time datetime="2026-09-17">17.09.2026</time></article></body></html>')
        product = page(SITE + "produkter/hytte-fjellro", '<html><body><article><h1>Hytte Fjellro</h1><time datetime="2026-09-17">17.09.2026</time></article></body></html>')
        self.assertEqual(extract_site_facts({"name": "Fjell Data AS"}, [HOME, contact, product]).activities, [])

    def test_homepage_article_card_without_link_is_kept(self):
        home = page(SITE, '<html><body><article><h3>Revejakta har startet</h3><time datetime="2026-07-24">24. juli 2026</time></article></body></html>')
        self.assertEqual(titles(extract_site_facts({"name": "Fjell Data AS"}, [home])), ["Revejakta har startet"])


class PublishersAndEvergreen(unittest.TestCase):
    def test_a_newspaper_s_journalism_is_not_news_about_the_newspaper(self):
        paper = {"name": "AS GRIMSTAD ADRESSETIDENDE", "organisation_number": "912345679",
                 "evidence": {"registry_live": {"value": {"industry": {"kode": "58.130"}}}}}
        home = page("https://www.gat.no/", "<html><body>Grimstad Adressetidende</body></html>")
        posts = [("Vraker nytt E18-forslag", "https://www.gat.no/nyheter/n/1/e18", "Wed, 28 Oct 2026 07:59:40 +0000", []),
                 ("Grimstad Adressetidende får ny redaktør", "https://www.gat.no/nyheter/n/2/redaktor", "Tue, 20 Oct 2026 07:00:00 +0000", [])]
        feed_page = CapturedPage("https://www.gat.no/rss", feed(posts).raw, "x", "2026-11-01T08:00:00Z", kind="feed")
        facts = extract_site_facts(paper, [home], [feed_page])
        self.assertEqual(titles(facts), [], "neither names the legal entity (AS GRIMSTAD ADRESSETIDENDE) itself")
        self.assertIn("activity:publisher_content_not_about_company", facts.rejections)

    def test_evergreen_advice_is_not_news_unless_it_names_the_company(self):
        posts = [("Hvor ofte bør et kontor rengjøres?", "https://fjell-data.no/blogg/kontor", "Wed, 16 Sep 2026 10:00:00 +0000", ["Blogg"]),
                 ("Slik lager dere en praktisk renholdsplan", "https://fjell-data.no/blogg/plan", "Mon, 19 Oct 2026 10:00:00 +0000", ["Blogg"]),
                 ("Vi har fått ny lønnsspesialist", "https://fjell-data.no/blogg/ny", "Thu, 19 Jun 2025 11:38:48 +0000", ["Blogg"])]
        facts = extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)])
        self.assertEqual(titles(facts), ["Vi har fått ny lønnsspesialist"])
        self.assertIn("activity:evergreen_advice_not_news", facts.rejections)


class ProjectAndDemoPosts(unittest.TestCase):
    def test_project_titled_posts_and_same_second_demo_posts_are_not_news(self):
        posts = [("Prosjekt: Kreativ ungdom i Arendal", "https://fjell-data.no/prosjekt-kreativ/", "Mon, 07 Jul 2025 14:24:33 +0000", ["Blogg"]),
                 ("Keep in touch with site visitors", "https://fjell-data.no/keep-in-touch/", "Tue, 29 Jun 2021 08:21:48 +0000", ["Blogg"]),
                 ("Make the most of the season", "https://fjell-data.no/make-the-most/", "Tue, 29 Jun 2021 08:21:48 +0000", ["Blogg"]),
                 ("Åpen dag på verkstedet", "https://fjell-data.no/apen-dag/", "Fri, 04 Sep 2026 19:54:59 +0000", ["Blogg"])]
        facts = extract_site_facts({"name": "Fjell Data AS"}, [HOME], [feed(posts)])
        self.assertEqual(titles(facts), ["Åpen dag på verkstedet"])
        self.assertIn("activity:project_title", facts.rejections)
        self.assertIn("activity:bulk_entry_burst", facts.rejections)


class Subject(unittest.TestCase):
    def test_sibling_unit_items_are_not_published_and_own_items_are(self):
        legal = {"name": "BETONMAST OSLO AS", "organisation_number": "996605833",
                 "evidence": {"registry_live": {"value": {"business_address": {"kommune": "OSLO", "poststed": "OSLO"}}}}}
        home = page("https://www.betonmast.no/", "<html><body>Betonmast</body></html>")
        posts = [("Betonmast bygger nytt bilanlegg i Kristiansund", "https://www.betonmast.no/2026/09/21/bilanlegg/", "Mon, 21 Sep 2026 07:08:07 +0000", ["Betonmast Røsand", "Næringsbygg"]),
                 ("Betonmast bygger fotballhall for Lier IL", "https://www.betonmast.no/2026/10/06/fotballhall/", "Tue, 06 Oct 2026 12:25:47 +0000", ["Betonmast Asker og Bærum"]),
                 ("Betonmast skal rehabilitere Bygg E i Forskningsparken", "https://www.betonmast.no/2026/10/06/bygg-e/", "Tue, 06 Oct 2026 04:48:18 +0000", ["Betonmast Oslo", "Rehabilitering"])]
        feed_page = CapturedPage("https://www.betonmast.no/feed/", feed(posts).raw, "x", "2026-11-01T08:00:00Z", kind="feed")
        facts = extract_site_facts(legal, [home], [feed_page])
        self.assertEqual(titles(facts), ["Betonmast skal rehabilitere Bygg E i Forskningsparken"])
        self.assertIn("activity:sibling_entity_item", facts.rejections)
        self.assertEqual(facts.operator["kind"], "group_or_brand")


if __name__ == "__main__":
    unittest.main()


class ReaderAddressing(unittest.TestCase):
    """Remediation R6: the ten labelled marketing/advice titles stay excluded; bare pronouns and interjections do not."""

    def test_the_ten_labelled_errors_stay_excluded(self):
        from norway_company_agent.attribution.news import evergreen_title
        for title in ("Extending Your Android Enterprise Mobility Strategy into Zone 2/22",
                      "Høst- og vinterrenhold for bedrifter: Slik holder dere inngang og gulv rene",
                      "Barnehagerenhold: Slik lager dere en praktisk renholdsplan", "Vi er din gode rådgiver og sparringspartner!",
                      "Dalgona kaffe: Enkel iskaffe du kan lage hjemme", "To netter på Stalheim - hva kan du finne på?", "Vi kan ta lønna for deg!",
                      "Vi renser ditt nærmiljø!", "FasterFix gir deg opptil 75% tidsbesparelse på byggeplass!",
                      "Nyhet! GX Mate GX Mate gir deg friheten til å merke hvor du vil på en trygg og sikker måte."):
            self.assertTrue(evergreen_title(title), title)

    def test_bare_pronouns_and_interjections_are_not_advice(self):
        from norway_company_agent.attribution.news import evergreen_title
        for title in ("Du store verden", "Få med deg flere nyhetssaker på Facebook", "Her finner du Barneombudet på Arendalsuka 2026",
                      "Hva gjør du hvis mobil og internett slutter å fungere? Øvelse NØP torsdag 29/11", "Ansatte og deres familier inviteres til sommerfest"):
            self.assertFalse(evergreen_title(title), title)
