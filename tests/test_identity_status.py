"""Phase 7: top-level identity block and company-level status; module states stay beneath."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.inputs import InputRow  # noqa: E402
from norway_company_agent.pipeline import run_batch  # noqa: E402

ORG, OTHER = valid_orgs(2)


def one(brreg, row=None, **extra):
    output = run_batch([row or InputRow(0, ORG, ORG)], run_id="i", **{**injected(brreg), **extra})
    return output["envelopes"][0]


class IdentityStatusTests(unittest.TestCase):
    def test_identity_leads_the_envelope_and_cites_the_registry(self):
        envelope = one(FakeBrreg({ORG: entity(ORG, name="Fjell Data AS")}))
        self.assertEqual(list(envelope)[:3], ["organisation_number", "identity", "company_status"])
        identity = envelope["identity"]
        self.assertEqual((identity["organisation_number"], identity["legal_name"], identity["legal_form"], identity["anchored"]), (ORG, "Fjell Data AS", "AS", True))
        self.assertEqual(identity["registry_status"], "registered")
        self.assertEqual(identity["source_class"], "official_registry_live")
        self.assertIn(identity["evidence_id"], {item["id"] for item in envelope["evidence"]})
        self.assertEqual(envelope["company_status"], {"state": "complete", "reasons": []})
        self.assertIn("roles", envelope["modules"], "module states stay beneath")
        self.assertEqual(validate_envelope(envelope), [])

    def test_identity_is_exactly_the_registry_claims(self):
        envelope = one(FakeBrreg({ORG: entity(ORG)}))
        claims = {claim["field"]: claim["value"] for claim in envelope["claims"] if claim["category"] == "identity" and claim["availability"] == "available"}
        self.assertEqual(envelope["identity"]["legal_name"], claims["legal_name"])
        self.assertEqual(envelope["identity"]["organisation_number"], claims["organisation_number"])
        self.assertNotIn("llm", envelope)

    def test_partial_when_a_source_fails(self):
        envelope = one(FakeBrreg({ORG: entity(ORG)}, down={"/roller"}))
        self.assertEqual(envelope["company_status"]["state"], "partial")
        self.assertIn("roles: source_error", envelope["company_status"]["reasons"])
        self.assertTrue(envelope["identity"]["anchored"])

    def test_bankrupt_and_liquidating_are_reported(self):
        body = entity(ORG)
        body["konkurs"] = True
        self.assertEqual(one(FakeBrreg({ORG: body}))["identity"]["registry_status"], "bankrupt")
        body = entity(ORG)
        body["underAvvikling"] = True
        self.assertEqual(one(FakeBrreg({ORG: body}))["identity"]["registry_status"], "under_liquidation")

    def test_unresolved_and_invalid_rows(self):
        unresolved = one(FakeBrreg({}))
        self.assertEqual(unresolved["company_status"]["state"], "identity_unresolved")
        self.assertIsNone(unresolved["identity"]["organisation_number"])
        self.assertFalse(unresolved["identity"]["anchored"])
        row = InputRow(0, "12345", None, errors=[{"code": "invalid_organisation_number", "stage": "input", "message": "x"}])
        invalid = one(FakeBrreg({}), row=row)
        self.assertEqual(invalid["company_status"], {"state": "invalid_input", "reasons": ["invalid_organisation_number"]})
        self.assertEqual(invalid["identity"]["input_organisation_number"], "12345")

    def test_rows_cut_by_the_deadline_are_not_researched_not_unresolved(self):
        from norway_company_agent.status import company_status, identity_block
        from norway_company_agent.synthesis import company_summary

        envelope = {"organisation_number": ORG, "claims": [], "evidence": [], "errors": [{"code": "deadline_exceeded", "stage": "deadline", "message": "x"}], "modules": {}}
        identity = identity_block(envelope)
        envelope["company_status"] = company_status(envelope, identity)
        self.assertEqual(envelope["company_status"], {"state": "not_researched", "reasons": ["deadline_exceeded"]})
        self.assertTrue(company_summary(envelope)["overview"].startswith("Not researched: the batch stopped"))

    def test_other_org_record_is_never_the_identity(self):
        brreg = FakeBrreg({ORG: entity(OTHER, name="Feil Selskap AS")})
        envelope = one(brreg)
        self.assertNotEqual(envelope["identity"]["legal_name"], "Feil Selskap AS")
        self.assertFalse(envelope["identity"]["anchored"])


if __name__ == "__main__":
    unittest.main()
