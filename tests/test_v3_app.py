"""V3 §B11: the local search application end to end, offline (fixture and fake registry fetchers)."""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.app_harness import FakeRegistry, Harness  # noqa: E402
from helpers.c12_replay import Fixture  # noqa: E402
from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402

V3 = ROOT / "tests" / "fixtures" / "v3"
TYIN, KILIS = "983181732", "875606662"
NEW, MISSING, SLOW, OUTSIDE = valid_orgs(4, start=920000000)


def imported_batch(directory: Path) -> tuple[Path, Path]:
    """Envelopes and captured registry bytes for two fixture companies, as a batch run would leave them."""
    snapshots = directory / "batch-snapshots"
    envelopes = []
    for org in (TYIN, KILIS):
        envelopes += run_batch([InputRow(0, org, org)], run_id="batch-1", snapshot_root=snapshots, **Fixture(org, base=V3).injected())["envelopes"]
    path = directory / "envelopes.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for envelope in envelopes:
            handle.write(json.dumps(envelope) + "\n")
    return path, snapshots


class SearchApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.envelopes, cls.snapshots = imported_batch(root)
        cls.brreg = FakeBrreg({NEW: entity(NEW, name="Nyskog Bygg AS"), SLOW: entity(SLOW, name="Treg Handel AS")}, slow_orgs={SLOW: 0.4})
        cls.registry = FakeRegistry({NEW: "NYSKOG BYGG AS", TYIN: "TYIN ALPINT AS", OUTSIDE: "FJELLRO HYTTER AS"})
        cls.h = Harness(root / "app", run_kwargs=injected(cls.brreg), imports=[cls.envelopes], snapshot_dirs=[cls.snapshots], registry=cls.registry)

    @classmethod
    def tearDownClass(cls):
        cls.h.close()
        cls.tmp.cleanup()

    def test_search_page_is_served_with_a_strict_policy_and_the_token(self):
        status, headers, body = self.h.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("script-src 'sha256-", headers["content-security-policy"])
        self.assertNotIn("unsafe-inline", headers["content-security-policy"])
        self.assertIn(b'name="signalpost-token"', body)
        self.assertEqual(headers["x-content-type-options"], "nosniff")

    def test_search_by_name_finds_the_dataset_and_the_registry(self):
        status, answer = self.h.get_json("/api/search?q=tyin")
        self.assertEqual(status, 200)
        self.assertEqual([item["org"] for item in answer["local"]], [TYIN])
        self.assertEqual(answer["local"][0]["name"], "TYIN ALPINT AS")
        status, answer = self.h.get_json("/api/search?q=fjellro")
        self.assertEqual((answer["local"], [item["org"] for item in answer["registry"]["results"]]), ([], [OUTSIDE]))

    def test_search_by_number(self):
        status, answer = self.h.get_json(f"/api/search?q={KILIS[:3]}%20{KILIS[3:]}")
        self.assertEqual((status, answer["query_kind"], [item["org"] for item in answer["local"]]), (200, "number", [KILIS]))

    def test_company_compare_and_whats_new_pages(self):
        status, headers, body = self.h.request("GET", f"/company/{TYIN}")
        self.assertEqual(status, 200)
        self.assertIn(b"TYIN ALPINT AS", body)
        self.assertIn(b'"open": "org=983181732"', body.replace(b'"open":"', b'"open": "'))
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
        status, _, body = self.h.request("GET", f"/compare?orgs={TYIN},{KILIS}")
        self.assertEqual(status, 200)
        self.assertIn(b"KONGSVINGER", body)
        self.assertEqual(self.h.request("GET", f"/compare?orgs={TYIN}")[0], 400)
        self.assertEqual(self.h.request("GET", f"/company/{NEW}")[0], 404, "not researched yet")
        self.assertEqual(self.h.request("GET", "/whats-new")[0], 200)

    def test_captured_bytes_are_served_only_for_indexed_hashes(self):
        envelope = self.h.store.latest(TYIN)
        served = None
        for item in envelope["evidence"]:
            if self.h.store.snapshot_path(item["content_sha256"]):
                served = item["content_sha256"]
                break
        self.assertIsNotNone(served, "the batch's registry bytes are on disk")
        status, headers, body = self.h.request("GET", f"/snapshot/{served}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/plain; charset=utf-8")
        self.assertTrue(headers["content-disposition"].startswith("attachment"))
        self.assertTrue(headers["content-security-policy"].startswith("sandbox"))
        self.assertEqual(self.h.request("GET", "/snapshot/" + "a" * 64)[0], 404)
        self.assertEqual(self.h.request("GET", "/snapshot/xyz")[0], 400)

    def test_research_a_new_company_end_to_end(self):
        status, job = self.h.post("/api/research", {"org": NEW})
        self.assertEqual(status, 202)
        done = self.h.wait(job["id"])
        self.assertEqual(done["state"], "completed", done)
        self.assertEqual(done["result"]["terminal_status"], "completed")
        status, answer = self.h.get_json("/api/search?q=nyskog")
        self.assertEqual([item["org"] for item in answer["local"]], [NEW], "researched companies are searchable at once")
        status, _, body = self.h.request("GET", f"/company/{NEW}")
        self.assertEqual(status, 200)
        stored = list((Path(self.tmp.name) / "app" / "research" / NEW).glob("*/envelope.json"))
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].stat().st_mode & 0o777, 0o600)
        # A re-check compares with the stored run.
        status, again = self.h.post("/api/research", {"org": NEW})
        self.h.wait(again["id"])
        self.assertTrue(self.h.store.latest(NEW)["refresh"]["compared"])

    def test_unknown_organisation_fails_honestly_and_saves_nothing(self):
        status, job = self.h.post("/api/research", {"org": MISSING})
        done = self.h.wait(job["id"])
        self.assertEqual((done["state"], done["error"]), ("failed", "not_in_registry"), done)
        self.assertIsNone(self.h.store.latest(MISSING))

    def test_duplicate_requests_share_a_job_and_cancel_saves_nothing(self):
        status, first = self.h.post("/api/research", {"org": SLOW})
        status2, second = self.h.post("/api/research", {"org": SLOW})
        self.assertEqual((status, status2, first["id"]), (202, 200, second["id"]))
        time.sleep(0.2)
        status, cancelling = self.h.post(f"/api/jobs/{first['id']}/cancel", {})
        self.assertIn(cancelling["state"], ("cancelling", "cancelled"))
        done = self.h.wait(first["id"])
        self.assertEqual(done["state"], "cancelled")
        self.assertIsNone(self.h.store.latest(SLOW))


class PartialResearch(unittest.TestCase):
    def test_a_failed_source_is_partial_and_named(self):
        org = valid_orgs(1, start=930000000)[0]
        brreg = FakeBrreg({org: entity(org, name="Delvis AS")}, down={"/roller"})
        with tempfile.TemporaryDirectory() as raw:
            h = Harness(raw, run_kwargs=injected(brreg))
            try:
                status, job = h.post("/api/research", {"org": org})
                done = h.wait(job["id"])
                self.assertEqual(done["state"], "partial", done)
                self.assertIn("roles", done["result"]["partial_sources"])
                self.assertIsNotNone(h.store.latest(org), "a partial profile is kept, with its failed sources stated")
            finally:
                h.close()


class RecheckOutage(unittest.TestCase):
    def test_a_source_outage_on_re_check_keeps_the_last_value(self):
        org = valid_orgs(1, start=935000000)[0]
        brreg = FakeBrreg({org: entity(org, name="Utfall AS")})
        with tempfile.TemporaryDirectory() as raw:
            h = Harness(raw, run_kwargs=injected(brreg))
            try:
                h.wait(h.post("/api/research", {"org": org})[1]["id"])
                brreg.down = {"/roller"}
                done = h.wait(h.post("/api/research", {"org": org})[1]["id"])
                self.assertEqual(done["state"], "partial")
                envelope = h.store.latest(org)
                kinds = {change["change_type"] for change in envelope["changes"]}
                self.assertNotIn("removed", kinds, envelope["changes"])
                self.assertIn("unavailable", kinds)
                self.assertEqual(envelope["modules"]["roles"]["state"], "carried_forward")
            finally:
                h.close()


class Persistence(unittest.TestCase):
    def test_researched_profiles_survive_a_restart_and_imports_are_read_only(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelopes, snapshots = imported_batch(root)
            before = envelopes.read_bytes()
            org = valid_orgs(1, start=940000000)[0]
            h = Harness(root / "app", run_kwargs=injected(FakeBrreg({org: entity(org, name="Varig AS")})), imports=[envelopes])
            try:
                status, job = h.post("/api/research", {"org": org})
                h.wait(job["id"])
            finally:
                h.close()
            h2 = Harness(root / "app", imports=[envelopes])
            try:
                self.assertIsNotNone(h2.store.latest(org))
                self.assertIsNotNone(h2.store.latest(TYIN))
            finally:
                h2.close()
            self.assertEqual(envelopes.read_bytes(), before)
            self.assertEqual((root / "app").stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()


class BrowserFlow(unittest.TestCase):
    def test_search_research_open_and_compare_on_desktop_and_phone(self):
        import os
        import shutil
        import subprocess
        node = shutil.which("node")
        modules = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        playwright = Path(modules) / "playwright"
        if not node or not playwright.exists():
            self.skipTest("node + playwright not installed")
        fresh = valid_orgs(2, start=960000000)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            envelopes, snapshots = imported_batch(root)
            brreg = FakeBrreg({org: entity(org, name=f"Nordlys Bygg {index} AS") for index, org in enumerate(fresh)}, delay=0.05)
            registry = FakeRegistry({org: f"NORDLYS BYGG {index} AS" for index, org in enumerate(fresh)})
            h = Harness(root / "app", run_kwargs=injected(brreg), imports=[envelopes], snapshot_dirs=[snapshots], registry=registry)
            script = root / "flow.js"
            script.write_text("""
const { chromium } = require(process.env.PWPATH);
(async () => {
  const browser = await chromium.launch();
  const base = process.argv[2], out = {};
  const viewports = [["desktop", {width: 1366, height: 820}, 0], ["phone", {width: 390, height: 844}, 1]];
  for (const [label, viewport, n] of viewports) {
    const page = await browser.newPage({viewport});
    const r = {errors: [], external: [], csp: [], overflow: []};
    page.on("pageerror", (e) => r.errors.push(String(e)));
    page.on("console", (m) => { if (/Content.Security.Policy|Refused/i.test(m.text())) r.csp.push(m.text()); });
    page.on("request", (q) => { if (!q.url().startsWith(base)) r.external.push(q.url()); });
    const wide = async (w) => { if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) r.overflow.push(w); };
    await page.goto(base + "/");
    await page.fill("#q", "https://evil.example");
    await page.click("button[type=submit]");
    await page.waitForSelector(".msg.bad");
    r.urlMessage = await page.textContent(".msg.bad");
    await page.fill("#q", "nordlys bygg " + n);
    await page.click("button[type=submit]");
    await page.waitForSelector("#registry li");
    await wide("results");
    await page.click("#registry li button");
    await page.waitForSelector("#registry li .job a.btn", {timeout: 30000});
    r.jobText = await page.textContent("#registry li .job");
    await page.click("#registry li .job a.btn");
    await page.waitForSelector("#company-name");
    r.profile = await page.textContent("#company-name");
    await wide("profile");
    await page.goto(base + "/?q=a");
    await page.waitForSelector("#local li");
    r.local = await page.$$eval("#local li .name", (x) => x.map((e) => e.textContent));
    await page.check("#local li >> nth=0 >> input.pickbox");
    await page.check("#local li >> nth=1 >> input.pickbox");
    await page.click("#cmpgo");
    await page.waitForSelector("#company-name");
    r.compare = await page.textContent("#company-name");
    await wide("compare");
    await page.screenshot({path: process.argv[3] + "/app-compare-" + label + ".png"});
    out[label] = r;
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
""")
            try:
                completed = subprocess.run([node, str(script), h.origin, raw], capture_output=True, text=True, timeout=180, env={**os.environ, "PWPATH": str(playwright)})
            finally:
                h.close()
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            for label, r in json.loads(completed.stdout).items():
                with self.subTest(label):
                    self.assertEqual((r["errors"], r["external"], r["csp"], r["overflow"]), ([], [], [], []))
                    self.assertIn("company name or organisation number", r["urlMessage"])
                    self.assertTrue(r["jobText"].startswith("Profile ready"), r["jobText"])
                    self.assertTrue(r["profile"].startswith("Nordlys Bygg"), r["profile"])
                    self.assertGreaterEqual(len(r["local"]), 2)
                    self.assertEqual(r["compare"], "Comparing 2 companies")
