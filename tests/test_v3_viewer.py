"""V3 §B10: viewer v2 — trust panel, evidence inspector, What's New, phone comparison cards, plain labels."""
from __future__ import annotations

import copy
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

from helpers.c12_replay import Fixture  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402
from norway_company_agent.viewer import TRUST, project, render_viewer  # noqa: E402

V3 = ROOT / "tests" / "fixtures" / "v3"
TYIN, KILIS = "983181732", "875606662"
OTHERS = ("995596970", "980932834")


def run(org: str, previous: dict | None = None, run_id: str = "v3-now") -> dict:
    return run_batch([InputRow(0, org, org)], run_id=run_id, previous_envelopes={org: previous} if previous else None, **Fixture(org, base=V3).injected())["envelopes"][0]


def refreshed_pair() -> list[dict]:
    """Kilis with one news item new since the baseline; Tyin with three retracted profiles; two plain companies."""
    kilis = run(KILIS)
    baseline = copy.deepcopy(kilis)
    baseline["claims"].remove(next(claim for claim in baseline["claims"] if claim["field"] == "news_item" and claim["availability"] == "available"))
    tyin = run(TYIN)
    tyin_base = copy.deepcopy(tyin)
    tyin_base["run"] = {**tyin_base["run"], "run_id": "old", "code_version": {"source_sha256": "0" * 64, "git_commit": None, "git_dirty": None}}
    home = next(item for item in tyin_base["evidence"] if item["source_url"] == "https://www.tyinfilefjell.no/")
    tyin_base["claims"].append({"field": "social_profile", "category": "public_activity", "value": "https://www.facebook.com/tyinfilefjell", "availability": "available",
                                "canonical_url": "https://facebook.com/tyinfilefjell", "evidence_ids": [home["id"]], "source_page": "https://www.tyinfilefjell.no/", "confidence": 0.95})
    return [run(KILIS, baseline), run(TYIN, tyin_base)] + [run(org) for org in OTHERS]


class Projection(unittest.TestCase):
    def test_notes_never_assume_a_field_is_an_object(self):
        envelope = run(KILIS)
        envelope["claims"].append({"field": "revenue", "category": "financials", "value": 10, "currency": "NOK", "attribution": "x", "operated_by": "y",
                                   "availability": "available", "evidence_ids": [], "key": "k"})
        projected = project(envelope)
        self.assertTrue(projected["claims"])  # no AttributeError on string-valued fields

    def test_new_items_and_attribution_basis_reach_the_page(self):
        envelopes = refreshed_pair()
        kilis = project(envelopes[0])
        notes = [claim[8] for claim in kilis["claims"] if claim[8]]  # (cat, field, state, value, ev, period, carried, reason, notes)
        self.assertEqual(sum(1 for note in notes if note.get("new")), 1)
        data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', render_viewer(envelopes), re.S).group(1))
        self.assertEqual(set(data["trust"]["how"]), set(TRUST))
        self.assertEqual(data["trust"]["audit"]["state"], "not_audited", "never claims an audit that was not supplied")


class PageSafety(unittest.TestCase):
    def test_template_never_parses_markup_and_stays_within_its_size_budget(self):
        envelopes = refreshed_pair()
        html = render_viewer(envelopes)
        script = html.split('<script id="app">')[-1] if '<script id="app">' in html else html
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(forbidden, script.replace("never innerHTML", ""))
        self.assertIn("default-src 'none'", html)
        self.assertLess(len(render_viewer([]).encode()), 80_000, "the empty viewer (template only) stays small")
        self.assertLess(len(html.encode()) / len(envelopes), 60_000, "average page weight per company")


class Browser(unittest.TestCase):
    def test_desktop_and_phone_flows(self):
        node = shutil.which("node")
        modules = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
        playwright = Path(modules) / "playwright"
        if not node or not playwright.exists():
            self.skipTest("node + playwright not installed")
        envelopes = refreshed_pair()
        with tempfile.TemporaryDirectory() as raw:
            page = Path(raw) / "viewer.html"
            page.write_text(render_viewer(envelopes), encoding="utf-8")
            script = Path(raw) / "check.js"
            script.write_text("""
const { chromium } = require(process.env.PWPATH);
(async () => {
  const browser = await chromium.launch();
  const out = {};
  const file = "file://" + process.argv[2];
  for (const [label, viewport] of [["desktop", {width: 1366, height: 820}], ["phone", {width: 390, height: 844}]]) {
    const page = await browser.newPage({viewport});
    const errors = [], external = [], overflow = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("request", (r) => { if (!r.url().startsWith("file://")) external.push(r.url()); });
    const wide = async (where) => { if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) overflow.push(where); };
    const r = {errors, external, overflow};
    await page.goto(file + "#org=" + process.argv[3]);
    await page.waitForSelector("#company-name");
    r.held = await page.$$eval("#detail h3", (n) => n.map((x) => x.textContent).filter((t) => t.startsWith("Seen but not attributed")));
    r.retracted = await page.$$eval("#detail td", (n) => n.map((x) => x.textContent).filter((t) => t === "Withdrawn by our checks").length);
    r.heldText = await page.$$eval("#detail td", (n) => n.map((x) => x.textContent).filter((t) => t.startsWith("Related website, not the entity's own")));
    await wide("company");
    // V3.1.1: Tyin's website is run by another company, so it is held (above); the inspector is checked on Kilis's own website.
    await page.goto(file + "#org=" + process.argv[4]); await page.reload();
    await page.waitForSelector("#company-name");
    await page.click('#detail button[aria-label="Inspect official website"]');
    await page.waitForSelector("#inspect[open]");
    r.inspect = await page.$$eval("#inspect dt", (n) => n.map((x) => x.textContent));
    await wide("inspector");
    await page.click("#inspect-close");
    r.closed = await page.evaluate(() => !document.getElementById("inspect").open);
    await page.goto(file + "#new"); await page.reload();
    await page.waitForSelector("#company-name");
    r.newTitle = await page.textContent("#company-name");
    r.newRows = await page.$$eval("#detail tbody tr", (n) => n.map((x) => x.textContent));
    await wide("whats-new");
    await page.goto(file + "#trust"); await page.reload();
    await page.waitForSelector("#company-name");
    r.trust = await page.$$eval("#detail h3", (n) => n.map((x) => x.textContent));
    r.trustText = await page.textContent("#detail");
    await wide("trust");
    for (const n of [2, 4]) {
      await page.goto(file + "#compare=" + process.argv.slice(4, 4 + n).join(",")); await page.reload();
      await page.waitForSelector("#company-name");
      r["cmp" + n] = label === "phone"
        ? await page.$$eval("div.cards .card", (c) => c.map((x) => x.querySelectorAll(".cell").length))
        : await page.$$eval("table.cmp thead th", (c) => c.length - 1);
      await wide("compare" + n);
    }
    out[label] = r;
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
""")
            orgs = [str(item["organisation_number"]) for item in envelopes]
            completed = subprocess.run([node, str(script), str(page), TYIN, *orgs], capture_output=True, text=True, timeout=180, env={**os.environ, "PWPATH": str(playwright)})
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            for label, r in json.loads(completed.stdout).items():
                with self.subTest(label):
                    self.assertEqual(r["errors"], [])
                    self.assertEqual(r["external"], [], "no request leaves the page")
                    self.assertEqual(r["overflow"], [], "no horizontal page scroll")
                    self.assertTrue(r["held"], "held-back items are shown, separately from facts")
                    self.assertGreaterEqual(r["retracted"], 1)
                    self.assertIn("Source type", r["inspect"], "V3.1.1: inspected on Kilis's own website (Tyin's is held), which has no attribution note")
                    self.assertTrue(any("tyinfilefjell.no" in text for text in r["heldText"]),
                                    "V3.1.1: Tyin's site is run by another company; it is held as a related website, with its URL and the reason")
                    self.assertIn("Content hash", r["inspect"])
                    self.assertTrue(r["closed"])
                    self.assertEqual(r["newTitle"], "What's new since the previous run")
                    self.assertTrue(any("new" in row for row in r["newRows"]))
                    self.assertTrue(any("Withdrawn by our checks" in row for row in r["newRows"]))
                    self.assertTrue({"Website", "Social profiles", "News", "Job advertisements", "Careers page"} <= set(r["trust"]))
                    self.assertIn("Not audited", r["trustText"])
                    if label == "phone":
                        self.assertTrue(r["cmp2"] and all(cells == 2 for cells in r["cmp2"]))
                        self.assertTrue(r["cmp4"] and all(cells == 4 for cells in r["cmp4"]))
                    else:
                        self.assertEqual((r["cmp2"], r["cmp4"]), (2, 4))


if __name__ == "__main__":
    unittest.main()
