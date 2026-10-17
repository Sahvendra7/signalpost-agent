"""Phase 5-6: input aliases, CSV, malformed rows and conflicting identifiers; registry snapshot fallback."""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.inputs import IDENTIFIER_KEYS, normalise_organisation_number, read_input_rows  # noqa: E402
from norway_company_agent.pipeline import load_bulk_profiles, run_batch  # noqa: E402

A, B, C = valid_orgs(3)


def parse(name: str, text: str | bytes):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / name
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
        return read_input_rows(path)


def codes(row):
    return [error["code"] for error in row.errors]


class InputFormatTests(unittest.TestCase):
    def test_canonical_jsonl(self):
        rows = parse("in.jsonl", "".join(json.dumps({"organisation_number": org}) + "\n" for org in (A, B)))
        self.assertEqual([row.organisation_number for row in rows], [A, B])
        self.assertEqual(rows[0].record, {"organisation_number": A})
        self.assertEqual(rows[0].errors, [])

    def test_every_alias_is_accepted(self):
        for key in IDENTIFIER_KEYS:
            with self.subTest(key):
                rows = parse("in.jsonl", json.dumps({key: A, "name": "X"}) + "\n" + json.dumps({key: int(B)}) + "\n")
                self.assertEqual([row.organisation_number for row in rows], [A, B])
                self.assertEqual(rows[0].record, {key: A, "name": "X"}, "original row preserved")

    def test_orgnr_and_organization_number_spellings(self):
        rows = parse("in.jsonl", f'{{"orgnr": "{A[:3]} {A[3:6]} {A[6:]}"}}\n{{"organization_number": "{B}"}}\n{{"OrgNr": "{C}"}}\n')
        self.assertEqual([row.organisation_number for row in rows], [A, B, C])

    def test_csv_with_header(self):
        for delimiter in (",", ";", "\t"):
            with self.subTest(repr(delimiter)):
                text = delimiter.join(["name", "orgnr", "city"]) + "\n" + delimiter.join(["Fjell AS", A, "Oslo"]) + "\n\n" + delimiter.join(["Hav AS", f"{B[:3]}.{B[3:6]}.{B[6:]}", "Bergen"]) + "\n"
                rows = parse("in.csv", text)
                self.assertEqual([row.organisation_number for row in rows], [A, B])
                self.assertEqual(rows[1].record, {"name": "Hav AS", "orgnr": f"{B[:3]}.{B[3:6]}.{B[6:]}", "city": "Bergen"})

    def test_csv_header_detected_in_a_txt_file_and_bom(self):
        rows = parse("in.txt", "﻿organisation_number,name\n" + f"{A},Fjell AS\n")
        self.assertEqual([row.organisation_number for row in rows], [A])

    def test_csv_without_identifier_column_is_never_guessed(self):
        rows = parse("in.csv", f"id,name\n{A},Fjell AS\n")
        self.assertEqual(len(rows), 2, "no header detected: each line is a row")
        self.assertTrue(all(row.organisation_number is None for row in rows))
        self.assertEqual(codes(rows[1]), ["invalid_organisation_number"])

    def test_other_columns_are_not_reinterpreted(self):
        rows = parse("in.jsonl", json.dumps({"vat": f"NO{A}MVA", "parent_orgnr_hint": A}) + "\n")
        self.assertIsNone(rows[0].organisation_number)
        self.assertEqual(codes(rows[0]), ["missing_organisation_number"])

    def test_duplicates_are_rows_researched_once(self):
        rows = parse("in.jsonl", "".join(json.dumps({"orgnr": org}) + "\n" for org in (A, B, A)))
        self.assertEqual(codes(rows[2]), ["duplicate_input"])
        output = run_batch(rows, run_id="d", **injected(FakeBrreg({A: entity(A), B: entity(B)})))
        self.assertEqual([envelope["input_position"] for envelope in output["envelopes"]], [0, 1, 2])
        self.assertEqual(output["report"]["unique_companies_researched"], 2)

    def test_malformed_rows_get_terminal_error_envelopes_and_never_abort(self):
        text = "\n".join([json.dumps({"orgnr": A}), '{"orgnr": "' + B, "not-a-number", "org 923609016 in prose", "[1, 2]", json.dumps({"orgnr": C})]) + "\n"
        rows = parse("in.jsonl", text)
        self.assertEqual([row.organisation_number for row in rows], [A, None, None, None, None, C])
        self.assertEqual(codes(rows[1]), ["malformed_input_row"])
        self.assertEqual(rows[1].record, '{"orgnr": "' + B)
        self.assertEqual(codes(rows[3]), ["invalid_organisation_number"], "no digit scavenging from free text")
        self.assertEqual(codes(rows[4]), ["malformed_input_row"])
        output = run_batch(rows, run_id="m", **injected(FakeBrreg({A: entity(A), C: entity(C)})))
        self.assertEqual(len(output["envelopes"]), 6)
        self.assertTrue(output["report"]["validation"]["passed"], output["report"]["validation"])
        statuses = [envelope["run"]["terminal_status"] for envelope in output["envelopes"]]
        self.assertEqual(statuses, ["completed", "failed", "failed", "failed", "failed", "completed"])
        self.assertEqual(output["envelopes"][1]["input_record"], '{"orgnr": "' + B)

    def test_conflicting_identifiers_are_never_guessed(self):
        rows = parse("in.jsonl", json.dumps({"orgnr": A, "organisation_number": B}) + "\n" + json.dumps({"orgnr": A, "organisation_number": f"{A[:3]} {A[3:6]} {A[6:]}"}) + "\n" + json.dumps({"orgnr": A, "org_no": ""}) + "\n")
        self.assertIsNone(rows[0].organisation_number)
        self.assertEqual(codes(rows[0]), ["conflicting_identifiers"])
        self.assertEqual(rows[1].organisation_number, A, "the same number written two ways is not a conflict")
        self.assertEqual(rows[2].organisation_number, A, "a blank alias is not a conflict")
        csv_rows = parse("in.csv", f"orgnr,organisation_number\n{A},{B}\n")
        self.assertEqual(codes(csv_rows[0]), ["conflicting_identifiers"])

    def test_broken_json_array_file_falls_back_to_lines(self):
        rows = parse("in.json", f'["{A}", "{B}"\n')
        self.assertEqual(len(rows), 1)
        self.assertEqual(codes(rows[0]), ["malformed_input_row"])
        good = parse("in.json", json.dumps([A, {"orgnr": B}, 123]))
        self.assertEqual([row.organisation_number for row in good], [A, B, None])

    def test_value_normalisation_is_strict(self):
        self.assertEqual(normalise_organisation_number(f"{A[:3]}-{A[3:6]}-{A[6:]}"), A)
        self.assertEqual(normalise_organisation_number(int(A)), A)
        for bad in (f"{A[:3]} {A[3:6]}-{A[6:]}", A + "0", "12345", True, None, 9.2e8, f"NO{A}"):
            self.assertIsNone(normalise_organisation_number(bad), bad)

    def test_gzip_jsonl_input(self):
        rows = parse("in.jsonl.gz", gzip.compress((json.dumps({"orgnr": A}) + "\n").encode()))
        self.assertEqual([row.organisation_number for row in rows], [A])


def bulk_csv(*orgs: str) -> bytes:
    header = "organisasjonsnummer;navn;organisasjonsform.kode;antallAnsatte;konkurs;underAvvikling;forretningsadresse.kommune;forretningsadresse.kommunenummer\n"
    return (header + "".join(f"{org};Bulk {org} AS;AS;4;false;false;OSLO;0301\n" for org in orgs)).encode()


class SnapshotFallbackTests(unittest.TestCase):
    def snapshot(self, directory: Path, name: str, data: bytes | None) -> str:
        path = directory / name
        if data is not None:
            path.write_bytes(data)
        return str(path)

    def test_gzip_snapshot_is_used(self):
        with tempfile.TemporaryDirectory() as raw:
            path = self.snapshot(Path(raw), "enheter.csv.gz", gzip.compress(bulk_csv(A, B)))
            found, meta = load_bulk_profiles(path, {A})
        self.assertEqual(meta["snapshot_status"], "used")
        self.assertEqual(set(found), {A})

    def test_absent_and_invalid_snapshots_fall_back_to_live_without_aborting(self):
        cases = {
            "none": None,
            "missing": ("absent.csv.gz", None),
            "plain_csv": ("enheter.csv", bulk_csv(A)),
            "truncated_gzip": ("enheter.csv.gz", gzip.compress(bulk_csv(A, B) * 50)[:60]),
            "garbage_after_magic": ("enheter.csv.gz", b"\x1f\x8b" + b"not really gzip" * 10),
        }
        for label, spec in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as raw:
                path = None if spec is None else self.snapshot(Path(raw), *spec)
                found, meta = load_bulk_profiles(path, {A})
                self.assertEqual(found, {})
                self.assertEqual(meta["snapshot_status"], "absent" if spec is None else "invalid")
                self.assertEqual(meta["fallback"], "live_registry")
                rows = parse("in.jsonl", json.dumps({"orgnr": A}) + "\n")
                output = run_batch(rows, run_id="snap", bulk_path=path, **injected(FakeBrreg({A: entity(A, name="Live Navn AS")})))
                envelope = output["envelopes"][0]
                self.assertEqual(envelope["run"]["terminal_status"], "completed")
                self.assertEqual(next(claim["value"] for claim in envelope["claims"] if claim["field"] == "legal_name"), "Live Navn AS")
                self.assertEqual(output["report"]["registry"]["snapshot_status"], meta["snapshot_status"])
                if spec is not None:
                    self.assertIn("Registry snapshot invalid", envelope["modules"]["registry"]["note"])


if __name__ == "__main__":
    unittest.main()
