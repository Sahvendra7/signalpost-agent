"""Phase 4: static, self-contained offline HTML viewer."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.pipeline import InputRow, run_batch  # noqa: E402
from norway_company_agent.viewer import project, render_viewer  # noqa: E402

ORGS = valid_orgs(3)
EVIL = '</script><script>alert(1)</script><!-- <img src=x onerror=alert(2)>'


def envelopes(name=None):
    brreg = FakeBrreg({org: entity(org, name=name if index == 0 else None) for index, org in enumerate(ORGS)})
    return run_batch([InputRow(index, org, org) for index, org in enumerate(ORGS)], run_id="v", **injected(brreg))["envelopes"]


def embedded(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    return json.loads(match.group(1))


class ViewerTests(unittest.TestCase):
    def test_self_contained_and_offline(self):
        html = render_viewer(envelopes())
        self.assertNotRegex(html, r"<script[^>]+src=")
        self.assertNotRegex(html, r"<link[^>]+href=")
        self.assertNotIn("@import", html)
        self.assertIn("default-src 'none'", html, "CSP forbids any network fetch from the page")
        outside_data = re.sub(r'<script type="application/json" id="data">.*?</script>', "", html, flags=re.S)
        self.assertNotRegex(outside_data, r"https?://", "no external URL outside the embedded data")
        self.assertIn('name="viewport"', html)
        self.assertIn("@media (max-width:760px)", html)

    def test_data_round_trips_and_is_complete(self):
        rows = envelopes()
        data = embedded(render_viewer(rows, {"run_id": "v", "input_rows": 3}))
        self.assertEqual(len(data["companies"]), 3)
        self.assertEqual([item["org"] for item in data["companies"]], ORGS)
        self.assertEqual(data["companies"][0], json.loads(json.dumps(project(rows[0]), default=str)))
        company = data["companies"][0]
        for key in ("status", "identity", "sections", "claims", "src", "ev", "changes", "errors", "modules", "refresh"):
            self.assertIn(key, company)
        source = company["src"][company["ev"][company["claims"][0][4][0]][0]]
        self.assertTrue(source[0].startswith("https://data.brreg.no/"), "FACT -> SOURCE")
        self.assertRegex(source[2], r"^\d{4}-\d\d-\d\dT", "SOURCE -> DATE")
        self.assertEqual(len(source[3]), 64)

    def test_hostile_text_cannot_break_out_of_the_data_block(self):
        rows = envelopes(name=EVIL)
        html = render_viewer(rows)
        self.assertEqual(html.count("</script>"), 2, "only the two real script closers")
        self.assertNotIn("<!-- <img", html)
        self.assertEqual(embedded(html)["companies"][0]["identity"]["legal_name"], EVIL, "the value survives intact as data")
        self.assertNotIn("innerHTML", html)

    def test_cli_writes_viewer(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "in.jsonl").write_text("".join(json.dumps({"organisation_number": org}) + "\n" for org in valid_orgs(4)))
            completed = subprocess.run([sys.executable, str(ROOT / "tests/helpers/cli_with_fakes.py"), "--count", "4", "--", "--organisations", str(directory / "in.jsonl"),
                                        "--output", str(directory / "env.jsonl"), "--profiles-output", str(directory / "prof.jsonl"), "--report", str(directory / "report.json"),
                                        "--run-id", "viewer", "--viewer-output", str(directory / "viewer.html")], capture_output=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode()[-2000:])
            data = embedded((directory / "viewer.html").read_text(encoding="utf-8"))
            self.assertEqual(len(data["companies"]), 4)
            self.assertEqual(data["run"]["run_id"], "viewer")

    def test_renders_in_a_headless_browser(self):
        node = shutil.which("node")
        modules = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        playwright = Path(modules) / "playwright"
        if not node or not playwright.exists():
            self.skipTest("node + playwright not installed")
        with tempfile.TemporaryDirectory() as raw:
            page = Path(raw) / "viewer.html"
            page.write_text(render_viewer(envelopes(name=EVIL)), encoding="utf-8")
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
    page.on("dialog", (d) => { errors.push("dialog " + d.message()); d.dismiss(); });
    page.on("request", (r) => { if (!r.url().startsWith("file://")) external.push(r.url()); });
    await page.goto("file://" + process.argv[2]);
    await page.waitForSelector("#list li");
    await page.click("#list li >> nth=0");
    await page.click("#detail .stmt button");
    const source = await page.textContent("#detail .src");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    if (label === "mobile") await page.click("#back");
    await page.fill("#q", process.argv[3]);
    result[label] = {errors, external, source, overflow, count: await page.textContent("#count"), name: await page.textContent("#list li .name")};
  }
  console.log(JSON.stringify(result));
  await browser.close();
})();
""")
            completed = subprocess.run([node, str(script), str(page), ORGS[1]], capture_output=True, text=True, timeout=120, env={**os.environ, "PWPATH": str(playwright)})
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            result = json.loads(completed.stdout)
            for label, outcome in result.items():
                self.assertEqual(outcome["errors"], [], label)
                self.assertEqual(outcome["external"], [], label)
                self.assertIn("SOURCE: https://data.brreg.no/", outcome["source"])
                self.assertIn("DATE: retrieved", outcome["source"])
                self.assertFalse(outcome["overflow"], f"{label}: no horizontal page scroll")
                self.assertEqual(outcome["count"], "1 of 3 shown")


if __name__ == "__main__":
    unittest.main()
