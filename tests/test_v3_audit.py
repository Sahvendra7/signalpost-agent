"""V3 §B9: audit kit arithmetic, blindness and self-contained checklist."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent import audit  # noqa: E402


def env(org: str, *claims: dict) -> dict:
    return {"organisation_number": org, "identity": {"legal_name": f"CO {org}"}, "claims": list(claims),
            "evidence": [{"id": "ev-1", "source_url": "https://example.no/", "retrieved_at": "2026-11-01T00:00:00Z", "claim_span": "span"}]}


def social(url: str) -> dict:
    return {"field": "social_profile", "availability": "available", "value": url, "canonical_url": url.replace("https://www.", "https://"), "evidence_ids": ["ev-1"]}


def news(url: str, date: str, title: str = "T") -> dict:
    return {"field": "news_item", "availability": "available", "value": {"title": title, "url": url, "publication_date": date}, "evidence_ids": ["ev-1"]}


class AuditKitTests(unittest.TestCase):
    def test_wilson_interval_matches_reference_values(self):
        low, high = audit.wilson(9, 10)
        self.assertAlmostEqual(low, 0.5958, places=3)
        self.assertAlmostEqual(high, 0.9821, places=3)
        self.assertIsNone(audit.wilson(0, 0))
        self.assertEqual(audit.wilson(0, 5)[0], 0.0)

    def test_units_align_across_arms_and_the_sample_is_blind(self):
        base = [env("111111111", social("https://www.facebook.com/a"), news("https://a.no/nyheter/x", "2026-01-01"), {"field": "news_item", "availability": "not_available", "value": None})]
        cand = [env("111111111", social("https://www.facebook.com/a"), news("https://a.no/nyheter/y", "2026-02-01"))]
        units, present = audit.align({"base": base, "v3": cand})
        self.assertEqual(len(units), 3)
        rows = audit.sample(units, present, per_stratum=None, seed=3)
        self.assertEqual(len(rows), 3, "every changed unit plus all unchanged units")
        for row in rows:
            self.assertNotIn("base", row.values())
            self.assertNotIn("v3", row.values())
            self.assertEqual(set(row), set(audit.CSV_FIELDS))
        self.assertEqual(rows, audit.sample(units, present, per_stratum=None, seed=3), "deterministic for a seed")

    def test_score_precision_retention_and_unlabelled_rows(self):
        present = {"o|social_profile|a": ["base", "v3"], "o|social_profile|b": ["base"], "o|social_profile|c": ["base"], "o|social_profile|d": ["v3"], "o|social_profile|e": ["base", "v3"]}
        labels = [
            {"uid": "o|social_profile|a", "category": "social_profile", "verdict": "correct"},
            {"uid": "o|social_profile|b", "category": "social_profile", "verdict": "incorrect"},
            {"uid": "o|social_profile|c", "category": "social_profile", "verdict": "correct"},
            {"uid": "o|social_profile|d", "category": "social_profile", "verdict": "correct"},
            {"uid": "o|social_profile|e", "category": "social_profile", "verdict": ""},
        ]
        result = audit.score(labels, present, baseline="base", candidate="v3", labeller="t", labeller_kind="assistant_blind")
        self.assertEqual(result["units_without_verdict"], 1)
        base = result["arms"]["base"]["social_profile"]
        self.assertEqual((base["correct"], base["incorrect"], base["precision"]), (2, 1, round(2 / 3, 4)))
        self.assertEqual(result["arms"]["v3"]["social_profile"]["precision"], 1.0)
        retention = result["retention"]["social_profile"]
        self.assertEqual((retention["baseline_correct"], retention["retained"], retention["errors_removed"]), (2, 1, 1))
        self.assertEqual(retention["lost_correct"], ["o|social_profile|c"])
        self.assertEqual(retention["gained_correct"], ["o|social_profile|d"])
        with self.assertRaises(ValueError):
            audit.score(labels, present, baseline=None, candidate=None, labeller="t", labeller_kind="robot")

    def test_checklist_is_self_contained_and_escapes_data(self):
        page = audit.render_checklist([{"uid": "x", "value": "</script><script>alert(1)</script>", "category": "news_item"}])
        self.assertIn("default-src 'none'", page)
        self.assertNotIn("</script><script>alert(1)", page)
        self.assertNotIn("innerHTML", page)
        self.assertNotIn("http-equiv=\"refresh\"", page)


if __name__ == "__main__":
    unittest.main()
