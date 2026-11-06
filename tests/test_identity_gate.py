"""Regression tests for the deterministic legal-entity identity gate (V3.2), on captured fixtures.

Fixtures (tests/fixtures/identity_gate/*.json) are trimmed captures of real pages with their sha256 and retrieval time:
  * VALMET AS on valmet.com (a global group site; parent group releases must not become the subsidiary's news);
  * LOGSCOM AS on logscom.com (a foreign namesake's site, "Logscom AB");
  * MATSENTRALEN ØST on matsentralen.no (a regional unit on the national network's domain);
  * positive controls: ROSIM AS (own site with org number), FRAM MARINE AS (exact legal name), ALEXANDER RYBAK AS
    (brand-only own site, no group).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.identity_gate import TargetIdentity, assess_item, assess_site  # noqa: E402

FIXTURES = sorted((ROOT / "tests/fixtures/identity_gate").glob("*.json"))


def load(name):
    fx = json.loads((ROOT / f"tests/fixtures/identity_gate/{name}.json").read_text(encoding="utf-8"))
    t = fx["target"]
    target = TargetIdentity(org=t["org"], legal_name=t["legal_name"], legal_form=t["legal_form"], street=t["street"], postal_code=t["postal_code"],
                            municipality=t["municipality"], parents=tuple(t["parents"]), group_members=tuple(t["group_members"]),
                            registry_website=t["registry_website"])
    return fx, target


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_captured_fixture_site_and_items(path):
    fx, target = load(path.stem)
    site = assess_site(target, fx["site_url"], fx["homepage"]["excerpt"])
    assert site.status == fx["expected_site_status"], site.evidence
    for item in fx["items"]:
        decision = assess_item(target, site, item["text"])
        assert decision.decision == item["expected"], (item["item_id"], decision)


def test_valmet_parent_release_names_other_entity_and_is_withheld():
    fx, target = load("valmet_global_group_site")
    site = assess_site(target, fx["site_url"], fx["homepage"]["excerpt"])
    release = assess_item(target, site, "Valmet Oyj’s stock exchange release on July 24, 2026: Valmet has appointed a new CFO.")
    assert release.decision == "withhold" and release.code == "item_names_other_legal_entity_under_brand"
    assert release.other_entities == ["Valmet Oyj"]
    featured = assess_item(target, site, "Valmet to replace Hansol Paper's legacy quality control systems in Korea.")
    assert featured.decision == "withhold" and featured.code == "group_site_item_does_not_name_exact_target"


def test_group_site_item_naming_the_exact_subsidiary_passes_synthetic_positive_control():
    """Synthetic (not captured): legitimate group-company news that establishes the exact target entity."""
    fx, target = load("valmet_global_group_site")
    site = assess_site(target, fx["site_url"], fx["homepage"]["excerpt"])
    by_name = assess_item(target, site, "Valmet AS i Lierstranda har signert en serviceavtale med en norsk papirfabrikk.")
    by_number = assess_item(target, site, "Our Norwegian company (org. nr. 932 383 357) opened a new service workshop.")
    assert by_name.decision == "pass" and by_name.names_target_exactly
    assert by_number.decision == "pass" and by_number.names_target_exactly
    both = assess_item(target, site, "Valmet Oyj and Valmet AS (932383357) together delivered the upgrade in Norway.")
    assert both.decision == "pass"  # the exact target is named; naming the parent too does not block it


def test_english_word_as_is_not_the_legal_form_and_brand_is_not_identity():
    target = TargetIdentity(org="932383357", legal_name="VALMET AS", legal_form="AS")
    assert not target.names_exactly("Valmet as a partner helps customers")
    assert target.names_exactly("Valmet AS, Lierstranda")
    assert target.brand_in("Valmet as a partner") and not target.names_exactly("Valmet")
    assert target.other_entities_named("Valmet Oyj and Valmet Technologies Oy and valmet as a partner") == ["Valmet Oyj", "Valmet Technologies Oy"]


def test_brand_only_site_without_group_signal_stays_presumed_own():
    target = TargetIdentity(org="999999999", legal_name="NORDLYS BAKERI AS", legal_form="AS")
    site = assess_site(target, "https://nordlysbakeri.no/", "Nordlys Bakeri — ferskt brød hver dag. Kontakt oss.")
    assert site.status == "brand_only"
    assert assess_item(target, site, "Vi åpner nytt bakeri i Tromsø").decision == "pass"


def test_unresolved_identity_is_withheld():
    target = TargetIdentity(org="999999999", legal_name="NORDLYS BAKERI AS", legal_form="AS")
    site = assess_site(target, "https://example-portal.no/", "Velkommen til portalen")
    assert site.status == "unresolved"
    assert assess_item(target, site, "Nyhet").decision == "withhold"


def test_no_company_specific_exceptions_in_gate_source():
    source = (ROOT / "src/norway_company_agent/identity_gate.py").read_text(encoding="utf-8").casefold()
    for name in ("valmet", "logscom", "matsentralen", "rosim", "sulland", "932383357"):
        assert name not in source, name


def test_release_run_path_does_not_import_the_gate():
    code = ("import sys; sys.path.insert(0, 'src'); import norway_company_agent.cli, norway_company_agent.pipeline; "
            "print('norway_company_agent.identity_gate' in sys.modules)")
    assert subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True).stdout.strip() == "False"
