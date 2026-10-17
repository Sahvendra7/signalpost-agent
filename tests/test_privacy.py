"""Phase 10: birth dates from Brreg role responses are never persisted (snapshots, envelopes, profiles)."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import ROLES, FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.http import fetch_json  # noqa: E402
from norway_company_agent.pipeline import InputRow, run_batch  # noqa: E402
from norway_company_agent.privacy import redact_roles_body, redacting_fetcher  # noqa: E402

ORG = valid_orgs(1)[0]
BIRTH_DATE = ROLES["rollegrupper"][0]["roller"][0]["person"]["fodselsdato"]


class BirthDateTests(unittest.TestCase):
    def test_fixture_really_carries_a_birth_date(self):
        self.assertEqual(BIRTH_DATE, "1980-01-02")

    def test_birth_dates_never_reach_snapshots_envelopes_or_profiles(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "snapshots"
            root.mkdir()
            output = run_batch([InputRow(0, ORG, ORG)], run_id="p", snapshot_root=root, **injected(FakeBrreg({ORG: entity(ORG)})))
            persisted = [path.read_bytes() for path in root.rglob("*") if path.is_file()]
            self.assertTrue(any(b"rollegrupper" in blob for blob in persisted), "the roles response itself is snapshotted")
            for blob in persisted:
                self.assertNotIn(b"fodselsdato", blob)
                self.assertNotIn(BIRTH_DATE.encode(), blob)
                self.assertNotIn(b"erDoed", blob)
            text = json.dumps([output["envelopes"], output["profiles"], output["report"]], ensure_ascii=False, default=str)
            self.assertNotIn("fodselsdato", text)
            self.assertNotIn(BIRTH_DATE, text)
            envelope = output["envelopes"][0]
            self.assertEqual(validate_envelope(envelope, snapshot_root=root), [], "hashes still verify against the redacted snapshot")
            ceo = next(claim for claim in envelope["claims"] if claim["field"] == "ceo")
            self.assertEqual(ceo["value"]["name"], "Kari Nordmann", "the role itself is kept")
            roles_evidence = next(item for item in envelope["evidence"] if item["id"] in ceo["evidence_ids"])
            stored = (root / roles_evidence["snapshot_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(stored).hexdigest(), roles_evidence["content_sha256"])

    def test_redaction_is_recursive_and_leaves_other_data(self):
        body = {"rollegrupper": [{"roller": [{"person": {"fodselsdato": "1970-05-05", "erDoed": False, "navn": {"fornavn": "A"}}, "fullmektig": {"person": {"fodselsdato": "1960-01-01"}}}]}]}
        self.assertEqual(redact_roles_body(body), {"rollegrupper": [{"roller": [{"person": {"navn": {"fornavn": "A"}}, "fullmektig": {"person": {}}}]}]})

    def test_only_roles_urls_are_rewritten_and_live_flag_is_kept(self):
        brreg = FakeBrreg({ORG: entity(ORG)})
        wrapped = redacting_fetcher(brreg)
        entity_result = wrapped(f"https://data.brreg.no/enhetsregisteret/api/enheter/{ORG}")
        self.assertEqual(entity_result.raw, brreg(f"https://data.brreg.no/enhetsregisteret/api/enheter/{ORG}").raw)
        self.assertFalse(wrapped.live)
        self.assertTrue(redacting_fetcher(fetch_json).live, "the live Brreg fetcher keeps its pacing flag")


if __name__ == "__main__":
    unittest.main()
