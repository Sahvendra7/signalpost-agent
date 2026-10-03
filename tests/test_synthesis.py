"""Phase 3: the deterministic company summary uses only verified claims and cites them."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.pipeline import InputRow, run_batch  # noqa: E402
from norway_company_agent.synthesis import SECTIONS, company_summary  # noqa: E402

ORG = valid_orgs(1)[0]


def run(brreg, previous=None, org=ORG, **extra):
    output = run_batch([InputRow(0, org, org)], run_id="s", previous_profiles={org: previous} if previous else None, **{**injected(brreg), **extra})
    return output["envelopes"][0], output["profiles"][0]


def section(envelope, key):
    return next(item for item in envelope["company_summary"]["sections"] if item["id"] == key)


def texts(envelope, key):
    return [statement["text"] for statement in section(envelope, key)["statements"]]


class SummaryTests(unittest.TestCase):
    def test_sections_fixed_order_and_every_fact_statement_cites_evidence(self):
        envelope, _ = run(FakeBrreg({ORG: entity(ORG)}))
        summary = envelope["company_summary"]
        self.assertEqual([item["id"] for item in summary["sections"]], [key for key, _ in SECTIONS])
        self.assertFalse(summary["llm_used"])
        evidence_ids = {item["id"] for item in envelope["evidence"]}
        claim_keys = {item["key"] for item in envelope["claims"]}
        for item in summary["sections"][:6]:
            for statement in item["statements"]:
                if statement["evidence_ids"]:
                    self.assertLessEqual(set(statement["evidence_ids"]), evidence_ids)
                    self.assertLessEqual(set(statement["claim_keys"]), claim_keys)
                else:
                    self.assertRegex(statement["text"], r"^(Checked; nothing found|Could not be checked|Candidates were found|Not applicable|Not checked)")

    def test_deterministic_for_the_same_claims(self):
        first, _ = run(FakeBrreg({ORG: entity(ORG)}))
        second, _ = run(FakeBrreg({ORG: entity(ORG)}))
        self.assertEqual(json.dumps(first["company_summary"], sort_keys=True), json.dumps(second["company_summary"], sort_keys=True))
        self.assertEqual(company_summary(first), first["company_summary"])

    def test_facts_and_reporting_period_are_preserved(self):
        envelope, _ = run(FakeBrreg({ORG: entity(ORG, name="Fjell Data AS")}))
        self.assertIn(f"Fjell Data AS (organisation number {ORG}), legal form AS (aksjeselskap).", texts(envelope, "key_company_facts"))
        self.assertIn("Chief executive (daglig leder): Kari Nordmann.", texts(envelope, "leadership"))
        finance = " ".join(texts(envelope, "financial_snapshot"))
        self.assertIn("reporting period 2025-01-01 to 2025-12-31", finance)
        self.assertIn("Revenue NOK 1,000", finance)
        self.assertIn("Latest annual accounts year registered: 2025.", finance)
        self.assertIn("“Utvikling av programvare”", " ".join(texts(envelope, "what_the_company_does")))

    def test_no_value_appears_that_is_not_in_a_claim(self):
        envelope, _ = run(FakeBrreg({ORG: entity(ORG)}))
        text = envelope["company_summary"]["text"]
        self.assertNotIn("1980", text, "birth dates are never claims, so never in the summary")
        for name in ("Kari Nordmann", "Avdeling Bergen"):
            self.assertIn(name, json.dumps([item["value"] for item in envelope["claims"]], ensure_ascii=False))

    def test_registry_only_company_is_sparse(self):
        envelope, _ = run(FakeBrreg({ORG: entity(ORG)}))
        summary = envelope["company_summary"]
        self.assertTrue(summary["sparse"])
        self.assertTrue(summary["overview"].startswith("Public information found was limited to official registry records: registry identity"))
        self.assertTrue(summary["text"].startswith("Public information found was limited to"))

    def test_unknown_is_distinguished_from_absent(self):
        down, _ = run(FakeBrreg({ORG: entity(ORG)}, down={"/roller"}))
        self.assertEqual(texts(down, "leadership"), ["Could not be checked in this run (source failed or blocked); nothing is reported."])
        self.assertTrue(any(text.startswith("Could not be checked in this run:") for text in texts(down, "what_remains_unknown")))
        none_found, _ = run(FakeBrreg({ORG: entity(ORG)}))
        self.assertTrue(any(text.startswith("Checked, nothing found:") and "job posting" in text for text in texts(none_found, "what_remains_unknown")))

    def test_unresolved_identity_reports_nothing(self):
        envelope, _ = run(FakeBrreg({}))
        self.assertTrue(envelope["company_summary"]["overview"].startswith("No verified registry identity"))
        self.assertTrue(all(not statement["evidence_ids"] for item in envelope["company_summary"]["sections"] for statement in item["statements"]))

    def test_what_changed_and_retained_values(self):
        _, prof1 = run(FakeBrreg({ORG: entity(ORG, employees=3)}))
        changed, prof2 = run(FakeBrreg({ORG: entity(ORG, employees=5)}), prof1)
        self.assertIn("Changed: registry employee count from 3 to 5.", texts(changed, "what_changed"))
        outage, _ = run(FakeBrreg({ORG: entity(ORG)}, down={"/roller"}), prof2)
        self.assertTrue(any(text.startswith("Source roles could not be checked in this run") for text in texts(outage, "what_changed")))
        ceo = next(statement for statement in section(outage, "leadership")["statements"] if statement["text"].startswith("Chief executive"))
        self.assertTrue(ceo["carried_forward"])
        self.assertTrue(any("Retained from an earlier run" in text for text in texts(outage, "what_remains_unknown")))
        first, _ = run(FakeBrreg({ORG: entity(ORG)}))
        self.assertEqual(texts(first, "what_changed"), ["Not assessed: no previous run was supplied for this company."])

    def test_live_measured_envelopes_summarise_without_error(self):
        import gzip

        path = ROOT / "measurements/official-audit-2026-10-03/unseen-1200/envelopes.jsonl.gz"
        if not path.exists():
            self.skipTest("measurement archive not present")
        with gzip.open(path, "rt") as handle:
            rows = [json.loads(line) for _, line in zip(range(200), handle)]
        for row in rows:
            summary = company_summary(row)
            ids = {item["id"] for item in row["evidence"]}
            self.assertTrue(all(set(statement["evidence_ids"]) <= ids for item in summary["sections"] for statement in item["statements"]))


if __name__ == "__main__":
    unittest.main()
