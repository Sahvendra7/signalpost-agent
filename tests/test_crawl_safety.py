"""Phase 9: robots.txt semantics (RFC 9309), Crawl-delay, bounded redirects, outbound address policy."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from norway_company_agent import website  # noqa: E402
from norway_company_agent.http import ByteFetch  # noqa: E402
from norway_company_agent.site_research import CompanyBudget, SiteSession, research_company_site  # noqa: E402
from test_site_research import FakeWeb, profile, site_pages  # noqa: E402

NOW = "2026-10-03T12:00:00Z"


class RobotsPolicyTests(unittest.TestCase):
    def test_status_semantics(self):
        cases = {200: "robots_ok", 401: "robots_forbidden", 403: "robots_forbidden", 404: "robots_absent", 410: "robots_absent",
                 429: "robots_unreachable", 500: "robots_unreachable", 503: "robots_unreachable", 0: "robots_unreachable"}
        for status, reason in cases.items():
            with self.subTest(status):
                parser, got = website.robots_policy(status, b"User-agent: *\nAllow: /\n" if status == 200 else b"")
                self.assertEqual(got, reason)
                allowed = parser is not None and parser.can_fetch(website.USER_AGENT, "https://x.no/")
                self.assertEqual(allowed, reason in {"robots_ok", "robots_absent"})

    def test_crawl_delay_parsing(self):
        parser, _ = website.robots_policy(200, b"User-agent: *\nCrawl-delay: 2\nAllow: /\n")
        self.assertEqual(website.crawl_delay(parser), 2.0)
        parser, _ = website.robots_policy(200, b"User-agent: *\nAllow: /\n")
        self.assertEqual(website.crawl_delay(parser), 0.0)
        self.assertEqual(website.crawl_delay(None), 0.0)


class SiteSessionRobotsTests(unittest.TestCase):
    def test_unreachable_robots_means_no_page_fetch(self):
        for status, outcome in ((503, "robots_unreachable"), (0, "robots_unreachable"), (403, "robots_forbidden")):
            with self.subTest(status):
                pages = site_pages()
                pages["https://fjordtest.no/robots.txt"] = (status, b"")
                web = FakeWeb(pages)
                result = research_company_site(profile(email="post@fjordtest.no"), SiteSession(web, resolver=lambda host: True))
                self.assertEqual(result.candidates[0]["outcome"], outcome)
                self.assertNotIn("https://fjordtest.no/", web.calls)

    def test_missing_robots_allows_crawl(self):
        pages = site_pages()
        del pages["https://fjordtest.no/robots.txt"]
        result = research_company_site(profile(email="post@fjordtest.no"), SiteSession(FakeWeb(pages), resolver=lambda host: True))
        self.assertEqual(result.status, "verified")

    def test_crawl_delay_spaces_requests_to_one_origin(self):
        pages = site_pages()
        pages["https://fjordtest.no/robots.txt"] = (200, b"User-agent: *\nCrawl-delay: 0.3\nAllow: /\n")
        stamps = []

        class Timed(FakeWeb):
            def __call__(self, url, **kwargs):
                stamps.append(time.monotonic())
                return super().__call__(url, **kwargs)

        session = SiteSession(Timed(pages), resolver=lambda host: True)
        budget = CompanyBudget(10, 10)
        for path in ("/", "/kontakt/", "/feed/"):
            self.assertEqual(session.get("https://fjordtest.no" + path, budget)[0], "ok")
        gaps = [later - earlier for earlier, later in zip(stamps, stamps[1:])]
        self.assertEqual(len(gaps), 3)
        self.assertTrue(all(gap >= 0.28 for gap in gaps), gaps)

    def test_crawl_delay_beyond_budget_is_skipped_not_violated(self):
        pages = site_pages()
        pages["https://fjordtest.no/robots.txt"] = (200, b"User-agent: *\nCrawl-delay: 30\nAllow: /\n")
        web = FakeWeb(pages)
        session = SiteSession(web, resolver=lambda host: True)
        self.assertEqual(session.get("https://fjordtest.no/", CompanyBudget(10, 10)), ("crawl_delay_exceeds_budget", None))
        pages["https://fjordtest.no/robots.txt"] = (200, b"User-agent: *\nCrawl-delay: 2\nAllow: /\n")
        session = SiteSession(FakeWeb(pages), resolver=lambda host: True)
        budget = CompanyBudget(10, 0.5)
        session.get("https://fjordtest.no/", budget)
        self.assertEqual(session.get("https://fjordtest.no/kontakt/", budget)[0], "crawl_delay_exceeds_budget")
        self.assertEqual(web.calls, ["https://fjordtest.no/robots.txt"])

    def test_requests_use_explicit_timeouts_and_bounded_attempts(self):
        seen = []

        def fetcher(url, **kwargs):
            seen.append(kwargs)
            return ByteFetch(url, 200, 1, b"User-agent: *\nAllow: /\n" if url.endswith("robots.txt") else b"<html>x</html>", "text/html", {}, "c" * 64, NOW, 1)

        SiteSession(fetcher, resolver=lambda host: True).get("https://fjordtest.no/", CompanyBudget(10, 10))
        self.assertTrue(seen)
        for kwargs in seen:
            self.assertEqual((kwargs["timeout"], kwargs["attempts"]), (15, 2))
            self.assertIn("max_bytes", kwargs)


class WebsiteModuleTests(unittest.TestCase):
    def robots(self, status, body=b""):
        return mock.patch("norway_company_agent.http.fetch_bytes", return_value=ByteFetch("https://x.no/robots.txt", status, 1, body, "text/plain", {}, "c" * 64, NOW, 1))

    def test_v1_robots_check(self):
        with mock.patch.object(website, "assert_public_url"):
            for status, body, expected in ((200, b"User-agent: *\nDisallow: /\n", (False, "robots_disallowed")), (503, b"", (False, "robots_unreachable")),
                                           (403, b"", (False, "robots_forbidden")), (404, b"", (True, "robots_absent")), (200, b"User-agent: *\nAllow: /\n", (True, "robots_ok"))):
                with self.subTest(status), self.robots(status, body) as fetch:
                    self.assertEqual(website._robots_check("https://x.no/", 15)[:2], expected)
                    kwargs = fetch.call_args.kwargs
                    self.assertEqual((kwargs["attempts"], kwargs["timeout"], kwargs["opener"]), (1, 15, website.SAFE_OPENER))

    def test_v1_unreachable_robots_blocks_homepage(self):
        with mock.patch.object(website, "assert_public_url"), self.robots(500), mock.patch.object(website.SAFE_OPENER, "open") as opener:
            record, metrics = website.fetch_website("https://x.no/")
        self.assertEqual(record["status"], "blocked")
        self.assertIn("robots.txt unreachable", record["note"])
        opener.assert_not_called()

    def test_v1_excessive_crawl_delay_is_not_fetched(self):
        with mock.patch.object(website, "assert_public_url"), self.robots(200, b"User-agent: *\nCrawl-delay: 60\n"), mock.patch.object(website.SAFE_OPENER, "open") as opener:
            record, _ = website.fetch_website("https://x.no/")
        self.assertEqual(record["status"], "blocked")
        self.assertIn("Crawl-delay", record["note"])
        opener.assert_not_called()


class RedirectAndAddressTests(unittest.TestCase):
    def test_redirects_are_bounded(self):
        handler = website.SafeRedirectHandler()
        self.assertEqual(handler.max_redirections, 5)
        self.assertLessEqual(handler.max_repeats, 5)
        self.assertTrue(any(isinstance(item, website.SafeRedirectHandler) for item in website.SAFE_OPENER.handlers))

    def test_redirect_target_must_be_public(self):
        handler = website.SafeRedirectHandler()
        for target in ("http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://10.1.2.3/", "http://[::1]/", "http://localhost/", "file:///etc/passwd", "ftp://x.no/"):
            with self.subTest(target), self.assertRaises(ValueError):
                handler.redirect_request(None, None, 302, "Found", {}, target)

    def test_public_address_check(self):
        for target in ("http://127.0.0.1/", "http://192.168.1.1/", "http://100.64.0.1/", "http://[fe80::1]/", "http://printer.local/"):
            with self.subTest(target), self.assertRaises(ValueError):
                website.assert_public_url(target)


if __name__ == "__main__":
    unittest.main()


class CrawlDelayGroupTests(unittest.TestCase):
    def test_fractional_and_agent_specific_delays(self):
        def delay(text):
            return website.crawl_delay(website.robots_policy(200, text.encode())[0])

        self.assertEqual(delay("User-agent: *\nCrawl-delay: 0.5\n"), 0.5)
        self.assertEqual(delay("User-agent: googlebot\nCrawl-delay: 9\n\nUser-agent: *\nDisallow: /x\n"), 0.0)
        own = website.USER_AGENT.split("/")[0]
        self.assertEqual(delay(f"User-agent: *\nCrawl-delay: 4\n\nUser-agent: {own}\nCrawl-delay: 1\n"), 1.0)
        self.assertEqual(delay("User-agent: a\nUser-agent: *\nCrawl-delay: 3 # slow\n"), 3.0)


class PlatformHostTests(unittest.TestCase):
    PLATFORMS = ("https://www.facebook.com/x", "https://m.facebook.com/x", "https://www.instagram.com/x/", "https://no.linkedin.com/company/x",
                 "https://www.youtube.com/@x", "https://youtu.be/x", "https://x.com/x", "https://www.tiktok.com/@x")

    def test_platform_hosts_are_refused_before_any_lookup(self):
        with mock.patch("socket.getaddrinfo", side_effect=AssertionError("no DNS lookup for a platform host")):
            for url in self.PLATFORMS:
                with self.subTest(url), self.assertRaisesRegex(ValueError, "Restricted platform"):
                    website.assert_public_url(url)

    def test_redirect_to_a_platform_is_refused(self):
        handler = website.SafeRedirectHandler()
        for url in self.PLATFORMS:
            with self.subTest(url), self.assertRaisesRegex(ValueError, "Restricted platform"):
                handler.redirect_request(None, None, 302, "Found", {}, url)

    def test_lookalike_hosts_are_not_platforms(self):
        for host in ("facebook.com.evil.no", "myfacebook.com", "linkedin-kurs.no", "fjordtest.no"):
            self.assertFalse(website.restricted_platform(host), host)

    def test_site_session_reports_platform_hosts(self):
        web = FakeWeb({})
        session = SiteSession(web, resolver=lambda host: True, url_guard=website.assert_public_url)
        self.assertEqual(session.get("https://www.facebook.com/fjordtest", CompanyBudget(10, 10)), ("blocked_platform_host", None))
        self.assertEqual(web.calls, [])


class FakeResponse:
    def __init__(self, url, body):
        self.url, self.body, self.status = url, body, 200
        self.headers = {"content-type": "text/html; charset=utf-8"}

    def read(self, limit=-1):
        return self.body

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class V1CrawlDelayTests(unittest.TestCase):
    def test_crawl_delay_fetches_homepage_only_after_waiting(self):
        home = b'<html><head><title>Fjordtest</title></head><body><a href="/om-oss">Om oss</a><a href="/kontakt">Kontakt</a> Org.nr 923 609 016</body></html>'
        robots = ByteFetch("https://x.no/robots.txt", 200, 1, b"User-agent: *\nCrawl-delay: 3\n", "text/plain", {}, "c" * 64, NOW, 1)
        with mock.patch.object(website, "assert_public_url"), mock.patch("norway_company_agent.http.fetch_bytes", return_value=robots), \
                mock.patch.object(website.SAFE_OPENER, "open", return_value=FakeResponse("https://x.no/", home)) as opener, mock.patch.object(website.time, "sleep") as sleep:
            record, metrics = website.fetch_website("https://x.no/")
        self.assertEqual(record["status"], "available")
        sleep.assert_called_once_with(3.0)
        self.assertEqual(opener.call_count, 1, "secondary pages are not fetched under a Crawl-delay")
        self.assertTrue(all("Crawl-delay" in item["error"] for item in record["value"]["crawl_errors"]))
