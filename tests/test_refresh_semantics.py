"""Phase 2: a failed refresh keeps the last supported value; typed, idempotent change events."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from helpers.fakeweb import FakeBrreg, entity, injected, valid_orgs  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.pipeline import InputRow, run_batch  # noqa: E402
from norway_company_agent.refresh import carry_forward  # noqa: E402

ORG = valid_orgs(1)[0]


def run(brreg, previous=None, org=ORG, **extra):
    output = run_batch([InputRow(0, org, org)], run_id="r", previous_profiles={org: previous} if previous else None, **{**injected(brreg), **extra})
    return output["envelopes"][0], output["profiles"][0]


def claim(envelope, field):
    return next((item for item in envelope["claims"] if item["field"] == field and item["availability"] == "available"), None)


def types(envelope):
    return sorted(item["change_type"] for item in envelope["changes"])


class RefreshScenarioTests(unittest.TestCase):
    def test_run1_good_run2_outage_run3_change_run4_same(self):
        good = FakeBrreg({ORG: entity(ORG, employees=3)})
        env1, prof1 = run(good)
        self.assertEqual(claim(env1, "registry_employee_count")["value"], 3)
        self.assertFalse(env1["refresh"]["compared"])

        down = FakeBrreg({ORG: entity(ORG)}, down={"/enheter/", "regnskapsregisteret", "/roller", "underenheter", "konsernstruktur"})
        env2, prof2 = run(down, prof1)
        kept = claim(env2, "registry_employee_count")
        self.assertEqual((kept["value"], kept["carried_forward"]), (3, True), "outage keeps value A")
        self.assertEqual(kept["evidence_ids"], claim(env1, "registry_employee_count")["evidence_ids"], "original source, date and hash")
        self.assertEqual(kept["last_verified_at"], next(e for e in env1["evidence"] if e["id"] == kept["evidence_ids"][0])["retrieved_at"])
        self.assertEqual(set(types(env2)), {"unavailable"}, "an outage is never changed/removed")
        self.assertEqual(env2["run"]["terminal_status"], "completed", "carried identity still anchors the company")
        self.assertEqual(env2["modules"]["registry_live"]["state"], "carried_forward")
        self.assertIn("source_unavailable_value_retained", {error["code"] for error in env2["errors"]})
        self.assertEqual(validate_envelope(env2), [])
        self.assertTrue(claim(env2, "revenue") and claim(env2, "ceo"), "accounts and roles carried too")

        changed = FakeBrreg({ORG: entity(ORG, employees=7)})
        env3, prof3 = run(changed, prof2)
        changes = [item for item in env3["changes"] if item["change_type"] == "changed"]
        self.assertEqual([(item["field"], item["old_value"], item["new_value"]) for item in changes], [("registry_employee_count", 3, 7)])
        self.assertIsNone(claim(env3, "registry_employee_count").get("carried_forward"))

        env4, _ = run(FakeBrreg({ORG: entity(ORG, employees=7)}), prof3)
        self.assertEqual(env4["changes"], [], "same source data: no duplicate change")
        self.assertEqual(env4["refresh"]["counts"]["changed"], 0)
        self.assertGreater(env4["refresh"]["counts"]["unchanged"], 10)

    def test_outage_persisting_over_two_runs_keeps_original_evidence_date(self):
        env1, prof1 = run(FakeBrreg({ORG: entity(ORG)}))
        down = FakeBrreg({ORG: entity(ORG)}, down={"/roller"})
        env2, prof2 = run(down, prof1)
        env3, _ = run(down, prof2)
        first = claim(env1, "ceo")
        third = claim(env3, "ceo")
        self.assertEqual(third["value"], first["value"])
        self.assertEqual(third["evidence_ids"], first["evidence_ids"], "same evidence: original retrieval date and hash")
        self.assertEqual(types(env3), ["unavailable"])

    def test_added_and_removed_roles_are_typed(self):
        _, prof1 = run(FakeBrreg({ORG: entity(ORG)}))
        new_roles = {"rollegrupper": [{"type": {"kode": "DAGL"}, "sistEndret": "2026-09-01", "roller": [
            {"type": {"kode": "DAGL", "beskrivelse": "Daglig leder"}, "person": {"navn": {"fornavn": "Ola", "etternavn": "Hansen"}}, "avregistrert": False}]}]}
        env2, _ = run(FakeBrreg({ORG: entity(ORG)}, overrides={(ORG, "/roller"): (200, new_roles)}), prof1)
        ceo_events = {(item["change_type"], (item["old_value"] or item["new_value"])["name"]) for item in env2["changes"] if item["field"] == "ceo"}
        self.assertEqual(ceo_events, {("removed", "Kari Nordmann"), ("added", "Ola Hansen")})

    def test_genuine_404_is_a_removal_not_an_outage(self):
        _, prof1 = run(FakeBrreg({ORG: entity(ORG)}))
        env2, _ = run(FakeBrreg({ORG: entity(ORG)}, overrides={(ORG, "regnskapsregisteret"): (404, None)}), prof1)
        self.assertIn("removed", {item["change_type"] for item in env2["changes"] if item["category"] == "filings"})
        self.assertIsNone(claim(env2, "revenue"))


class WebsiteRefreshTests(unittest.TestCase):
    def test_site_facts_carried_on_outage_then_removed_when_gone(self):
        from test_site_research import ORG as SITE_ORG, FakeWeb, site_pages

        body = entity(SITE_ORG, name="Fjordtest Programvare AS")
        body["epostadresse"] = "post@fjordtest.no"
        brreg = FakeBrreg({SITE_ORG: body})
        common = {"resolver": lambda host: True, "org": SITE_ORG}
        env1, prof1 = run(brreg, site_fetcher=FakeWeb(site_pages()), **common)
        self.assertTrue(claim(env1, "social_profile") and claim(env1, "news_item") and claim(env1, "official_website"))

        env2, prof2 = run(brreg, prof1, site_fetcher=FakeWeb({}), **common)  # every site request fails
        self.assertEqual(claim(env2, "social_profile")["value"], claim(env1, "social_profile")["value"])
        self.assertTrue(claim(env2, "social_profile")["carried_forward"])
        self.assertTrue(claim(env2, "official_website")["carried_forward"])
        self.assertFalse({"removed", "changed"} & set(types(env2)))
        self.assertIn("site_research", env2["refresh"]["carried_forward_modules"])

        pages = site_pages()
        home = pages["https://fjordtest.no/"][1].replace(b'<a href="https://www.linkedin.com/company/fjordtest-programvare">LinkedIn</a>', b"")
        pages["https://fjordtest.no/"] = (200, home)
        env3, _ = run(brreg, prof2, site_fetcher=FakeWeb(pages), **common)
        self.assertIn(("removed", "social_profile"), {(item["change_type"], item.get("field")) for item in env3["changes"]})
        self.assertIsNone(claim(env3, "social_profile"))


class CarryForwardUnitTests(unittest.TestCase):
    def site(self, status, url="https://fjordtest.no/", candidates=None):
        value = {"site_url": url, "candidates": candidates or [], "pages": [{"url": url, "content_sha256": "c" * 64, "retrieved_at": "2026-10-01T00:00:00Z"}], "profiles": [], "activities": [], "jobs": []}
        return evidence("site_research", status, "company_site", url, value=value, content_sha256="c" * 64 if status == "available" else None)

    def test_unreachable_site_is_carried(self):
        previous = {"organisation_number": ORG, "evidence": {"site_research": self.site("available")}}
        current = {"organisation_number": ORG, "evidence": {"site_research": self.site("not_found", candidates=[{"domain": "fjordtest.no", "outcome": "http_0"}])}}
        self.assertEqual(carry_forward(previous, current), {"carried": ["site_research"], "unverified": []})
        self.assertTrue(current["evidence"]["site_research"]["carried_forward"])

    def test_site_failing_identity_is_unverified_not_carried(self):
        previous = {"organisation_number": ORG, "evidence": {"site_research": self.site("available")}}
        current = {"organisation_number": ORG, "evidence": {"site_research": self.site("not_found", candidates=[{"domain": "fjordtest.no", "outcome": "FAN_COMMUNITY"}])}}
        self.assertEqual(carry_forward(previous, current), {"carried": [], "unverified": ["site_research"]})
        self.assertNotIn("carried_forward", current["evidence"]["site_research"])

    def test_registry_linked_site_is_carried_when_the_registry_website_gate_is_down(self):
        # Found in the final live refresh: v1 website got HTTP 429, so site research could not use the registry
        # identity gate and classified the same site AMBIGUOUS. That is an outage, not an identity change.
        old_site = self.site("available")
        old_site["value"]["identity_class"] = "REGISTRY_LINKED"
        old_web = evidence("website", "available", "registry_linked_company_website", "https://fjordtest.no/", value={"identity_assessment": {"publishable": True}}, content_sha256="d" * 64)
        previous = {"organisation_number": ORG, "evidence": {"site_research": old_site, "website": old_web}}
        current = {"organisation_number": ORG, "evidence": {
            "site_research": self.site("not_found", candidates=[{"domain": "fjordtest.no", "outcome": "AMBIGUOUS"}]),
            "website": evidence("website", "source_error", "registry_linked_company_website", "https://fjordtest.no/", note="HTTP 429"),
        }}
        self.assertEqual(carry_forward(previous, current), {"carried": ["website", "site_research"], "unverified": []})
        self.assertTrue(current["evidence"]["site_research"]["carried_forward"])

    def test_registry_linked_site_failing_identity_with_gate_up_is_unverified(self):
        old_site = self.site("available")
        old_site["value"]["identity_class"] = "REGISTRY_LINKED"
        previous = {"organisation_number": ORG, "evidence": {"site_research": old_site}}
        current = {"organisation_number": ORG, "evidence": {"site_research": self.site("not_found", candidates=[{"domain": "fjordtest.no", "outcome": "AMBIGUOUS"}])}}
        self.assertEqual(carry_forward(previous, current), {"carried": [], "unverified": ["site_research"]})

    def test_no_previous_is_a_noop(self):
        current = {"organisation_number": ORG, "evidence": {}}
        self.assertEqual(carry_forward(None, current), {"carried": [], "unverified": []})


if __name__ == "__main__":
    unittest.main()
