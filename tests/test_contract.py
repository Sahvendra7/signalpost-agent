"""Execution-contract tests: INPUT N rows -> OUTPUT N terminal, valid envelopes, offline."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.contract import AVAILABILITY_STATES, ClaimSet, validate_envelope  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.http import ByteFetch, FetchResult  # noqa: E402
from norway_company_agent.pipeline import InputRow, mod11_valid, read_input_rows, run_batch  # noqa: E402
from norway_company_agent.refresh import diff_profile  # noqa: E402

ORG_A, ORG_B, ORG_C = "923609016", "914778271", "985399077"
NOW = "2026-10-01T06:00:00Z"


def entity_body(org: str, name: str, website: str | None = None, employees: int | None = 3) -> dict:
    body = {
        "organisasjonsnummer": org,
        "navn": name,
        "organisasjonsform": {"kode": "AS", "beskrivelse": "Aksjeselskap"},
        "naeringskode1": {"kode": "62.010", "beskrivelse": "Programmeringstjenester"},
        "forretningsadresse": {"adresse": ["Storgata 1"], "postnummer": "0155", "poststed": "OSLO", "kommune": "OSLO", "kommunenummer": "0301", "land": "Norge"},
        "stiftelsesdato": "2015-03-01",
        "registreringsdatoEnhetsregisteret": "2015-03-10",
        "konkurs": False,
        "underAvvikling": False,
        "sisteInnsendteAarsregnskap": "2025",
        "aktivitet": ["Utvikling og salg av programvare"],
    }
    if website:
        body["hjemmeside"] = website
    if employees is not None:
        body["antallAnsatte"] = employees
        body["harRegistrertAntallAnsatte"] = True
    return body


ROLES_BODY = {
    "rollegrupper": [
        {"type": {"kode": "DAGL", "beskrivelse": "Daglig leder"}, "sistEndret": "2024-05-01", "roller": [
            {"type": {"kode": "DAGL", "beskrivelse": "Daglig leder"}, "person": {"navn": {"fornavn": "Kari", "etternavn": "Nordmann"}, "fodselsdato": "1980-01-01"}, "avregistrert": False},
        ]},
        {"type": {"kode": "STYR", "beskrivelse": "Styre"}, "sistEndret": "2023-01-01", "roller": [
            {"type": {"kode": "LEDE", "beskrivelse": "Styrets leder"}, "person": {"navn": {"fornavn": "Ola", "etternavn": "Hansen"}}, "avregistrert": False},
            {"type": {"kode": "MEDL", "beskrivelse": "Styremedlem"}, "person": {"navn": {"fornavn": "Per", "etternavn": "Berg"}}, "avregistrert": True},
        ]},
    ]
}

ACCOUNTS_BODY = [{
    "id": 7, "regnskapstype": "SELSKAP", "valuta": "NOK",
    "regnskapsperiode": {"fraDato": "2025-01-01", "tilDato": "2025-12-31"},
    "resultatregnskapResultat": {"driftsresultat": {"driftsinntekter": {"sumDriftsinntekter": 0}, "driftsresultat": -1200}, "aarsresultat": -1000, "ordinaertResultatFoerSkattekostnad": -1100},
    "eiendeler": {"sumEiendeler": 50000},
    "egenkapitalGjeld": {"egenkapital": {"sumEgenkapital": 30000}, "gjeldOversikt": {"sumGjeld": 20000}},
}]


def result(url: str, status: int, body=None) -> FetchResult:
    raw = json.dumps(body, sort_keys=True).encode() if body is not None else b""
    return FetchResult(url, status, 5, len(raw), body if status == 200 else None, error=None if status == 200 else f"HTTP {status}", content_sha256=hashlib.sha256(raw).hexdigest() if status else None, retrieved_at=NOW, raw=raw if status else None)


class FakeBrreg:
    """URL-routed fake of the Brreg endpoints with per-org overrides and call counting."""

    def __init__(self, entities: dict[str, dict], overrides: dict | None = None):
        self.entities = entities
        self.overrides = overrides or {}
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, url: str) -> FetchResult:
        with self.lock:
            self.calls.append(url)
        org = next((org for org in self.entities if org in url), None)
        for (match_org, fragment), outcome in self.overrides.items():
            if match_org == org and fragment in url:
                if isinstance(outcome, Exception):
                    raise outcome
                status, body = outcome
                return result(url, status, body)
        if org is None:
            return result(url, 404)
        if "/roller" in url:
            return result(url, 200, ROLES_BODY)
        if "konsernstruktur" in url:
            return result(url, 404)
        if "underenheter" in url:
            return result(url, 200, {"_embedded": {"underenheter": [{"organisasjonsnummer": "973000001", "navn": "Avdeling Bergen", "beliggenhetsadresse": {"adresse": ["Bryggen 2"], "postnummer": "5003", "poststed": "BERGEN"}, "antallAnsatte": 2}]}})
        if "regnskapsregisteret" in url:
            return result(url, 200, ACCOUNTS_BODY)
        if "/enheter/" in url:
            return result(url, 200, self.entities[org])
        return result(url, 404)


def offline_network_down(url: str) -> FetchResult:
    return FetchResult(url, 0, 0, 0, error="URLError", retrieved_at=NOW, attempts=3)


def website_record(url: str, *, title: str, text: str, social: list[dict] | None = None, status: str = "available", note: str | None = None):
    if status != "available":
        return evidence("website", status, "registry_linked_company_website", url, note=note, retrieved_at=NOW)
    value = {
        "requested_url": url, "final_url": url, "title": title, "description": f"{title} description",
        "main_text_excerpt": text, "identity_text_excerpt": text, "social_links": social or [],
        "structured_organisations": [], "pages": [], "content_sha256": "c" * 64,
    }
    return evidence("website", "available", "registry_linked_company_website", url, value=value, content_sha256="c" * 64, retrieved_at=NOW)


def make_website_fetcher(pages: dict[str, dict]):
    def fetch(url):
        if not url:
            return evidence("website", "not_found", "registry_linked_company_website", "https://data.brreg.no/enhetsregisteret/api/enheter", note="No valid registry website URL", retrieved_at=NOW), {"requests": 0, "bytes": 0, "latencies_ms": []}
        return copy.deepcopy(pages[url]), {"requests": 2, "bytes": 100, "latencies_ms": [10]}
    return fetch


def rows(*orgs: str) -> list[InputRow]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "orgs.jsonl"
        path.write_text("".join(json.dumps({"organisation_number": org}) + "\n" for org in orgs), encoding="utf-8")
        return read_input_rows(path)


def by_field(envelope: dict, field: str) -> list[dict]:
    return [claim for claim in envelope["claims"] if claim["field"] == field]


def offline_site(url, **kwargs):
    return ByteFetch(url, 404, 0, b"", "text/html", {}, None, NOW, 1, "HTTP 404")


def run(orgs, fetcher, website_fetcher=None, **kwargs):
    kwargs.setdefault("site_fetcher", offline_site)
    kwargs.setdefault("resolver", lambda host: False)
    return run_batch(rows(*orgs), run_id="t", fetcher=fetcher, website_fetcher=website_fetcher or make_website_fetcher({}), workers=4, **kwargs)


class InputTests(unittest.TestCase):
    def test_mod11(self):
        self.assertTrue(mod11_valid("923609016"))
        self.assertFalse(mod11_valid("923609017"))
        self.assertFalse(mod11_valid("12345678"))

    def test_every_line_becomes_a_row_even_when_invalid_or_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orgs.txt"
            path.write_text(f"{ORG_A}\nnot-a-number\n{ORG_A}\n923 609 017\n", encoding="utf-8")
            parsed = read_input_rows(path)
        self.assertEqual(len(parsed), 4)
        self.assertEqual([row.organisation_number for row in parsed], [ORG_A, None, ORG_A, "923609017"])
        self.assertEqual(parsed[1].errors[0]["code"], "invalid_organisation_number")
        self.assertEqual(parsed[2].errors[0]["code"], "duplicate_input")
        self.assertEqual(parsed[3].errors[0]["code"], "checksum_mismatch")


class BatchContractTests(unittest.TestCase):
    def setUp(self):
        self.brreg = FakeBrreg({ORG_A: entity_body(ORG_A, "Fjordtest Programvare AS"), ORG_B: entity_body(ORG_B, "Nordlys Regnskap AS"), ORG_C: entity_body(ORG_C, "Havbris Eiendom AS")})

    def assert_contract(self, output, expected_inputs):
        envelopes = output["envelopes"]
        self.assertEqual(len(envelopes), len(expected_inputs))
        self.assertEqual([item["input_organisation_number"] for item in envelopes], expected_inputs)
        for envelope in envelopes:
            self.assertEqual(validate_envelope(envelope), [], envelope["organisation_number"])
            self.assertIn(envelope["run"]["terminal_status"], {"completed", "failed"})
            for claim in envelope["claims"]:
                self.assertIn(claim["availability"], AVAILABILITY_STATES)
        self.assertTrue(output["report"]["validation"]["passed"], output["report"]["validation"])

    def test_complete_batch_output(self):
        output = run([ORG_A, ORG_B, ORG_C], self.brreg)
        self.assert_contract(output, [ORG_A, ORG_B, ORG_C])
        envelope = output["envelopes"][0]
        self.assertEqual(envelope["organisation_number"], ORG_A)
        self.assertEqual(by_field(envelope, "legal_name")[0]["value"], "Fjordtest Programvare AS")
        self.assertEqual(by_field(envelope, "ceo")[0]["value"]["name"], "Kari Nordmann")
        self.assertEqual(by_field(envelope, "board_chair")[0]["value"]["name"], "Ola Hansen")
        self.assertEqual(by_field(envelope, "board_member"), [], "inactive role holders are not published")
        self.assertEqual(by_field(envelope, "registered_activity")[0]["value"], "Utvikling og salg av programvare")
        self.assertEqual(by_field(envelope, "subunit")[0]["value"]["name"], "Avdeling Bergen")
        self.assertEqual(envelope["run"]["terminal_status"], "completed")
        self.assertNotIn("1980-01-01", json.dumps(envelope), "birth dates are never emitted")

    def test_financial_zero_is_preserved_with_reporting_period(self):
        envelope = run([ORG_A], self.brreg)["envelopes"][0]
        revenue = by_field(envelope, "revenue")[0]
        self.assertEqual(revenue["value"], 0)
        self.assertEqual(revenue["period"], {"from": "2025-01-01", "to": "2025-12-31"})
        self.assertEqual(revenue["currency"], "NOK")
        self.assertEqual(by_field(envelope, "net_result")[0]["value"], -1000)
        evidence_item = next(item for item in envelope["evidence"] if item["id"] == revenue["evidence_ids"][0])
        self.assertIn("regnskapsregisteret", evidence_item["source_url"])
        self.assertIn("2025-01-01", evidence_item["claim_span"])

    def test_empty_result_is_explicit_and_distinct_from_unchecked(self):
        brreg = FakeBrreg({ORG_A: entity_body(ORG_A, "Tomt AS", employees=None)}, {
            (ORG_A, "regnskapsregisteret"): (404, None),
            (ORG_A, "underenheter"): (200, {"page": {"totalElements": 0}}),
            (ORG_A, "/roller"): (200, {"rollegrupper": []}),
        })
        envelope = run([ORG_A], brreg)["envelopes"][0]
        self.assertEqual(by_field(envelope, "subunit_count")[0]["value"], 0)
        self.assertEqual(by_field(envelope, "role_count")[0]["value"], 0)
        self.assertEqual(by_field(envelope, "annual_accounts")[0]["availability"], "not_available")
        self.assertEqual(by_field(envelope, "registry_employee_count")[0]["availability"], "not_available")
        self.assertIsNone(by_field(envelope, "registry_employee_count")[0]["value"], "missing is never a fake zero")
        self.assertEqual(by_field(envelope, "group_structure")[0]["availability"], "not_available")
        self.assertEqual(by_field(envelope, "official_website")[0]["availability"], "not_available")

    def test_empty_counts_are_not_coverage(self):
        brreg = FakeBrreg({ORG_A: entity_body(ORG_A, "Tomt AS")}, {(ORG_A, "/roller"): (200, {"rollegrupper": []})})
        envelope = run([ORG_A], brreg)["envelopes"][0]
        self.assertEqual(envelope["category_coverage"]["leadership"], "not_available")
        self.assertEqual(envelope["category_coverage"]["identity"], "available")

    def test_extraction_exception_still_yields_terminal_envelope(self):
        from unittest.mock import patch
        with patch("norway_company_agent.pipeline.claims_from_profile", side_effect=KeyError("boom")):
            output = run([ORG_A, ORG_B], self.brreg)
        self.assert_contract(output, [ORG_A, ORG_B])
        self.assertEqual(output["envelopes"][0]["errors"][-1]["code"], "extraction_exception")

    def test_concurrent_identical_snapshots_do_not_race(self):
        with tempfile.TemporaryDirectory() as directory:
            output = run_batch(rows(ORG_A, ORG_B, ORG_C), run_id="t", fetcher=FakeBrreg({ORG_A: entity_body(ORG_A, "A AS"), ORG_B: entity_body(ORG_B, "B AS"), ORG_C: entity_body(ORG_C, "C AS")}), website_fetcher=make_website_fetcher({}), workers=8, snapshot_root=Path(directory), site_fetcher=offline_site, resolver=lambda host: False)
            self.assertEqual([error for item in output["envelopes"] for error in item["errors"]], [])
            self.assertFalse(list(Path(directory).rglob("*.tmp")))

    def test_source_blocked(self):
        brreg = FakeBrreg({ORG_A: entity_body(ORG_A, "Fjordtest Programvare AS", website="fjordtest.no")})
        site = make_website_fetcher({"fjordtest.no": website_record("https://fjordtest.no/", title="", text="", status="blocked", note="robots.txt disallows this user agent")})
        envelope = run([ORG_A], brreg, site)["envelopes"][0]
        claim = by_field(envelope, "official_website")[0]
        self.assertEqual(claim["availability"], "blocked")
        self.assertIn("robots", claim["reason"])
        self.assertEqual(envelope["modules"]["website"]["state"], "blocked_robots")
        self.assertEqual(by_field(envelope, "registry_listed_website")[0]["value"], "fjordtest.no")

    def test_ambiguous_entity_publishes_no_site_facts(self):
        brreg = FakeBrreg({ORG_A: entity_body(ORG_A, "Fjordtest Programvare Vest AS", website="fjordgroup.no")})
        page = website_record("https://fjordgroup.no/", title="Fjord Group", text="Fjord Group is a family of companies across Norway with offices in many cities.", social=[{"platform": "linkedin", "url": "https://linkedin.com/company/fjordgroup"}])
        envelope = run([ORG_A], brreg, make_website_fetcher({"fjordgroup.no": page}))["envelopes"][0]
        self.assertEqual(by_field(envelope, "official_website")[0]["availability"], "ambiguous")
        self.assertEqual(by_field(envelope, "social_profile"), [])
        self.assertEqual(by_field(envelope, "website_description"), [])

    def test_exact_site_publishes_site_facts(self):
        brreg = FakeBrreg({ORG_A: entity_body(ORG_A, "Fjordtest Programvare AS", website="fjordtest.no")})
        page = website_record("https://fjordtest.no/", title="Fjordtest Programvare AS", text=f"Fjordtest Programvare AS org.nr {ORG_A[:3]} {ORG_A[3:6]} {ORG_A[6:]}", social=[{"platform": "linkedin", "url": "https://linkedin.com/company/fjordtest-programvare"}])
        envelope = run([ORG_A], brreg, make_website_fetcher({"fjordtest.no": page}))["envelopes"][0]
        website = by_field(envelope, "official_website")[0]
        self.assertEqual(website["availability"], "available")
        self.assertEqual(website["confidence"], 1.0)
        self.assertEqual(by_field(envelope, "social_profile")[0]["value"]["url"], "https://linkedin.com/company/fjordtest-programvare")

    def test_network_failure_keeps_bulk_identity_and_marks_sources_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            bulk = Path(directory) / "bulk.csv.gz"
            with gzip.open(bulk, "wt", encoding="utf-8") as handle:
                handle.write("organisasjonsnummer,navn,organisasjonsform.kode,hjemmeside,sisteInnsendteAarsregnskap,konkurs\n")
                handle.write(f"{ORG_A},Fjordtest Programvare AS,AS,,2025,false\n")
            output = run([ORG_A, ORG_B], offline_network_down, bulk_path=bulk)
        self.assert_contract(output, [ORG_A, ORG_B])
        in_bulk, absent = output["envelopes"]
        self.assertEqual(in_bulk["run"]["terminal_status"], "completed")
        self.assertEqual(by_field(in_bulk, "legal_name")[0]["value"], "Fjordtest Programvare AS")
        self.assertEqual(by_field(in_bulk, "roles")[0]["availability"], "failed")
        self.assertEqual(by_field(in_bulk, "annual_accounts")[0]["availability"], "failed")
        self.assertGreaterEqual(in_bulk["operations"]["requests"], 15, "retries are counted as requests")
        self.assertEqual(absent["run"]["terminal_status"], "failed")
        self.assertIn("identity_unresolved", [error["code"] for error in absent["errors"]])
        self.assertEqual([claim for claim in absent["claims"] if claim["availability"] == "available"], [])

    def test_company_absent_from_bulk_falls_back_to_live_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            bulk = Path(directory) / "bulk.csv.gz"
            with gzip.open(bulk, "wt", encoding="utf-8") as handle:
                handle.write("organisasjonsnummer,navn\n" + f"{ORG_B},Nordlys Regnskap AS\n")
            envelope = run([ORG_A], self.brreg, bulk_path=bulk)["envelopes"][0]
        self.assertEqual(envelope["run"]["terminal_status"], "completed")
        self.assertEqual(by_field(envelope, "legal_name")[0]["value"], "Fjordtest Programvare AS")
        self.assertEqual(envelope["modules"]["registry"]["state"], "not_found")

    def test_malformed_source_is_contained(self):
        brreg = FakeBrreg(dict(self.brreg.entities), {
            (ORG_A, "/roller"): (200, ["not", "a", "dict"]),
            (ORG_A, "regnskapsregisteret"): (200, {"unexpected": True}),
            (ORG_B, "/enheter/" + ORG_B): (200, entity_body(ORG_C, "Someone Else AS")),
        })
        output = run([ORG_A, ORG_B], brreg)
        self.assert_contract(output, [ORG_A, ORG_B])
        malformed, mismatched = output["envelopes"]
        self.assertEqual(by_field(malformed, "role_count")[0]["value"], 0)
        self.assertEqual(by_field(malformed, "annual_accounts")[0]["availability"], "not_available")
        self.assertNotIn("Someone Else AS", json.dumps(mismatched["claims"]), "a registry body for another org number is never attached")
        self.assertIn("identity_mismatch", [error["code"] for error in mismatched["errors"]])

    def test_partial_failure_is_isolated_per_company(self):
        brreg = FakeBrreg(dict(self.brreg.entities), {(ORG_B, "/roller"): RuntimeError("parser exploded")})
        output = run([ORG_A, ORG_B, ORG_C], brreg)
        self.assert_contract(output, [ORG_A, ORG_B, ORG_C])
        a, b, c = output["envelopes"]
        self.assertEqual(a["errors"], [])
        self.assertEqual(c["errors"], [])
        self.assertEqual(b["errors"][0]["code"], "pipeline_exception")
        self.assertEqual(b["run"]["terminal_status"], "completed", "identity was anchored before the failure")

    def test_same_company_twice_researched_once_emitted_twice(self):
        output = run([ORG_A, ORG_B, ORG_A], self.brreg)
        self.assert_contract(output, [ORG_A, ORG_B, ORG_A])
        self.assertEqual(sum(1 for url in self.brreg.calls if url.endswith(f"/enheter/{ORG_A}")), 1)
        first, _, repeat = output["envelopes"]
        self.assertEqual(first["claims"], repeat["claims"])
        self.assertEqual(repeat["errors"][0]["code"], "duplicate_input")
        self.assertEqual(output["report"]["unique_companies_researched"], 2)

    def test_invalid_row_gets_failed_envelope_and_does_not_stop_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orgs.txt"
            path.write_text(f"{ORG_A}\n12345\n{ORG_B}\n", encoding="utf-8")
            parsed = read_input_rows(path)
        output = run_batch(parsed, run_id="t", fetcher=self.brreg, website_fetcher=make_website_fetcher({}), site_fetcher=offline_site, resolver=lambda host: False)
        self.assert_contract(output, [ORG_A, "12345", ORG_B])
        self.assertEqual(output["envelopes"][1]["run"]["terminal_status"], "failed")
        self.assertEqual(output["envelopes"][1]["errors"][0]["code"], "invalid_organisation_number")

    def test_expected_count_mismatch_is_reported_not_fatal(self):
        output = run([ORG_A], self.brreg, expected_count=2)
        self.assertEqual(len(output["envelopes"]), 1)
        self.assertFalse(output["report"]["validation"]["passed"])

    def test_duplicate_source_evidence_is_deduplicated(self):
        claims = ClaimSet()
        record = evidence("roles", "available", "official_roles", "https://x.test/r", content_sha256="a" * 64, retrieved_at=NOW)
        self.assertTrue(claims.add("leadership", "ceo", {"name": "Kari"}, record, "span"))
        self.assertFalse(claims.add("leadership", "ceo", {"name": "Kari"}, record, "span"), "same fact twice is one claim")
        self.assertTrue(claims.add("leadership", "board_chair", {"name": "Kari"}, record, "span"))
        self.assertEqual(len(claims.evidence), 1, "same source and span is one evidence entry")
        envelope = run([ORG_A], self.brreg)["envelopes"][0]
        ids = [item["id"] for item in envelope["evidence"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_claim_without_hash_is_not_published(self):
        claims = ClaimSet()
        unhashed = evidence("roles", "available", "official_roles", "https://x.test/r", retrieved_at=NOW)
        self.assertFalse(claims.add("leadership", "ceo", {"name": "Kari"}, unhashed, "span"))
        self.assertEqual(claims.claims, [])

    def test_snapshot_store_makes_evidence_verifiable_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            envelope = run([ORG_A], self.brreg, snapshot_root=root)["envelopes"][0]
            cited = [item for item in envelope["evidence"] if item.get("snapshot_path")]
            self.assertTrue(cited)
            self.assertEqual(validate_envelope(envelope, snapshot_root=root), [])
            (root / cited[0]["snapshot_path"]).write_bytes(b"tampered")
            codes = {item["code"] for item in validate_envelope(envelope, snapshot_root=root)}
            self.assertIn("snapshot_hash_mismatch", codes)


class RefreshContractTests(unittest.TestCase):
    def setUp(self):
        self.entities = {ORG_A: entity_body(ORG_A, "Fjordtest Programvare AS", employees=3)}

    def test_repeated_refresh_is_idempotent(self):
        first = run([ORG_A], FakeBrreg(self.entities))
        previous = {item["organisation_number"]: item for item in first["profiles"]}
        second = run([ORG_A], FakeBrreg(self.entities), previous_profiles=previous)
        third = run([ORG_A], FakeBrreg(self.entities), previous_profiles={item["organisation_number"]: item for item in second["profiles"]})
        self.assertEqual(second["envelopes"][0]["changes"], [])
        self.assertEqual(third["envelopes"][0]["changes"], [])
        strip = lambda env: [{k: v for k, v in claim.items()} for claim in env["claims"]]  # noqa: E731
        self.assertEqual(strip(first["envelopes"][0]), strip(second["envelopes"][0]))

    def test_real_change_is_detected_with_provenance(self):
        first = run([ORG_A], FakeBrreg(self.entities))
        changed = {ORG_A: entity_body(ORG_A, "Fjordtest Programvare AS", employees=5)}
        second = run([ORG_A], FakeBrreg(changed), previous_profiles={ORG_A: first["profiles"][0]})
        changes = second["envelopes"][0]["changes"]
        self.assertEqual([item["field"] for item in changes], ["registry.employees"])
        self.assertEqual((changes[0]["old_value"], changes[0]["new_value"]), (3, 5))
        self.assertTrue(changes[0]["old_content_sha256"] and changes[0]["new_content_sha256"])

    def test_outage_on_refresh_is_not_a_change(self):
        first = run([ORG_A], FakeBrreg(self.entities))
        second = run([ORG_A], offline_network_down, previous_profiles={ORG_A: first["profiles"][0]})
        self.assertEqual(second["envelopes"][0]["changes"], [])

    def test_reordered_source_list_is_not_a_change(self):
        source = evidence("roles", "available", "official_roles", "https://x.test", content_sha256="a" * 64)
        old = {"organisation_number": ORG_A, "evidence": {"roles": {**source, "value": {"roles": [{"name": "A"}, {"name": "B"}]}}}}
        new = {"organisation_number": ORG_A, "evidence": {"roles": {**source, "value": {"roles": [{"name": "B"}, {"name": "A"}]}}}}
        self.assertEqual(diff_profile(old, new), [])

    def test_source_outage_is_not_a_false_change(self):
        ok = evidence("website", "available", "site", "https://x.test", value={"title": "Example AS"}, content_sha256="a" * 64)
        down = evidence("website", "source_error", "site", "https://x.test", note="URLError")
        old = {"organisation_number": ORG_A, "evidence": {"website": ok}}
        new = {"organisation_number": ORG_A, "evidence": {"website": down}}
        self.assertEqual(diff_profile(old, new), [])


if __name__ == "__main__":
    unittest.main()
