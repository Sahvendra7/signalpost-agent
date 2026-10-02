"""Characterization tests: pin the starter's behaviour before the contract is hardened.

These record what the starter's helpers do (including known defects, marked `defect`) so later
changes are deliberate. Defect tests are replaced, not deleted silently, when a fix lands.

Status after V1: the batch command now runs through `pipeline.py`, which does not call the legacy
`read_organisation_inputs`/`profiles_from_bulk`/`terminal_envelope` helpers, so the input and envelope
defects below remain true of those helpers but no longer of the command (see tests/test_contract.py).
The refresh outage defect was fixed in `refresh.py` itself.
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import profiles_from_bulk, read_organisation_inputs, terminal_envelope  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.http import FetchResult  # noqa: E402
from norway_company_agent.official import fetch_official_modules  # noqa: E402
from norway_company_agent.refresh import diff_profile  # noqa: E402

BULK_HEADER = "organisasjonsnummer,navn,organisasjonsform.kode,hjemmeside,sisteInnsendteAarsregnskap\n"


def write_bulk(directory: str, rows: list[str]) -> Path:
    path = Path(directory) / "bulk.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(BULK_HEADER + "".join(row + "\n" for row in rows))
    return path


def failing_fetcher(url: str) -> FetchResult:
    return FetchResult(url, 0, 0, 0, error="URLError", retrieved_at="2026-01-01T00:00:00Z")


class StarterInputCharacterization(unittest.TestCase):
    def test_input_formats_text_json_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            text = Path(directory) / "a.txt"
            text.write_text("923 609 016\n", encoding="utf-8")
            self.assertEqual(read_organisation_inputs(text), [{"organisation_number": "923609016"}])
            body = Path(directory) / "a.json"
            body.write_text(json.dumps({"organisation_numbers": ["923609016"]}), encoding="utf-8")
            self.assertEqual(read_organisation_inputs(body), [{"organisation_number": "923609016"}])

    def test_defect_duplicate_input_aborts_whole_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.txt"
            path.write_text("923609016\n923609016\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_organisation_inputs(path)

    def test_defect_malformed_number_aborts_whole_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.txt"
            path.write_text("923609016\n12345\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_organisation_inputs(path)

    def test_defect_company_absent_from_bulk_aborts_whole_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            bulk = write_bulk(directory, ["923609016,Example AS,AS,,2025"])
            with self.assertRaises(ValueError):
                profiles_from_bulk(bulk, ["923609016", "914778271"])


class StarterEnvelopeCharacterization(unittest.TestCase):
    def test_legacy_envelope_shape_differs_from_output_contract(self):
        profile = {"organisation_number": "923609016", "evidence": {"registry": evidence("registry", "available", "official", "https://x.test")}}
        envelope = terminal_envelope(profile, run_id="r", modules=["registry"], started_at="t0", completed_at="t1")
        self.assertEqual(set(envelope), {"run_id", "organisation_number", "state", "started_at", "completed_at", "modules", "profile"})
        for contract_key in ("run", "claims", "evidence", "changes", "errors", "operations"):
            self.assertNotIn(contract_key, envelope)

    def test_defect_all_sources_failed_still_reports_complete(self):
        records, metrics = fetch_official_modules("923609016", {"registry_live", "financials", "roles"}, fetcher=failing_fetcher)
        self.assertTrue(all(item["status"] == "source_error" for item in records.values()))
        profile = {"organisation_number": "923609016", "evidence": records}
        envelope = terminal_envelope(profile, run_id="r", modules=list(records), started_at="t0", completed_at="t1")
        self.assertEqual(envelope["state"], "complete")
        self.assertEqual(len(metrics), 3)


class StarterRefreshCharacterization(unittest.TestCase):
    def test_fixed_source_outage_is_no_longer_a_change(self):
        ok = evidence("website", "available", "site", "https://x.test", value={"title": "Example AS"}, content_sha256="a" * 64)
        down = evidence("website", "source_error", "site", "https://x.test", note="URLError")
        old = {"organisation_number": "923609016", "evidence": {"website": ok}}
        new = {"organisation_number": "923609016", "evidence": {"website": down}}
        fields = {item["field"] for item in diff_profile(old, new)}
        self.assertNotIn("website.title", fields)


if __name__ == "__main__":
    unittest.main()
