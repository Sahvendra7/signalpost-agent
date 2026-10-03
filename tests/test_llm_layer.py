"""Optional LLM layer: offline tests with fixed HTML fixtures and mocked model responses. No API key."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from norway_company_agent.claims import claims_from_profile  # noqa: E402
from norway_company_agent.contract import validate_envelope  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.http import ByteFetch  # noqa: E402
from norway_company_agent.llm import ConfigurableProvider, DisabledProvider, LLMConfig, LLMLayer, LLMProvider, LLMResponse  # noqa: E402
from norway_company_agent.llm.tasks import (  # noqa: E402
    explicit_dates, extraction_triggers, normalize_role, prepare_page, synthesis_facts, validate_extraction, validate_synthesis,
)
from norway_company_agent.site_identity import classify_site  # noqa: E402
from norway_company_agent.website import normalize_social_url  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "llm"
ORG = "923609016"
NAME = "Fjordtest Programvare AS"
NOW = "2026-10-03T12:00:00Z"
BASE = "https://fjordtest.no"
ENABLED_ENV = {"LLM_ENABLED": "true", "LLM_MODEL": "mock-model", "LLM_API_KEY": "sk-test-not-real", "LLM_BASE_URL": "https://llm.invalid/v1"}


def raw(name: str) -> bytes:
    return (FIXTURES / f"{name}.html").read_bytes()


def page(name: str, url: str | None = None):
    body = raw(name)
    return prepare_page(url or f"{BASE}/{name}/", body, retrieved_at=NOW, content_sha256=hashlib.sha256(body).hexdigest())


def registry_profile() -> dict:
    roles = {"roles": [{"name": "Kari Nordmann", "role_code": "DAGL"}, {"name": "Ola Hansen", "role_code": "LEDE"}]}
    return {
        "organisation_number": ORG, "name": NAME,
        "evidence": {"roles": evidence("roles", "available", "official_roles", "https://data.brreg.no/x", value=roles, content_sha256="d" * 64)},
    }


def fp(url: str, span: str) -> dict:
    return {"source_url": url, "classification": "FIRST_PARTY", "evidence_spans": [span]}


def fact(url: str, fact_type: str, value, span: str, **extra) -> dict:
    return {"fact_type": fact_type, "value": value, "evidence_span": span, "source_url": url, "date_if_explicit": None, "confidence": 0.9, **extra}


def reasons(result) -> list[str]:
    return [item["reason"] for item in result.rejected]


# ---------- the nine fixtures ----------

class FixtureExtractionTests(unittest.TestCase):
    def test_genuine_company_page_facts_keep_provenance_and_hallucinations_are_rejected(self):
        home = page("genuine", f"{BASE}/")
        url = home.source_url
        data = {
            "page_classifications": [fp(url, "Org.nr 923 609 016")],
            "facts": [
                fact(url, "business_description", "utvikler regnskapsprogramvare for små bedrifter i Norge", "Fjordtest Programvare AS utvikler regnskapsprogramvare for små bedrifter i Norge."),
                fact(url, "person_role", {"person_name": "Kari Nordmann", "role_title": "Daglig leder", "role_category": "ceo"}, "Daglig leder Kari Nordmann"),
                fact(url, "founded_year", "2009", "Etablert i 2009."),
                fact(url, "contact_email", "post@fjordtest.no", "post@fjordtest.no"),
                fact(url, "contact_phone", "+47 22 33 44 55", "Tlf +47 22 33 44 55"),
                fact(url, "employee_count_statement", "14 ansatte", "Vi er 14 ansatte i Oslo."),
                # hallucinations
                fact(url, "business_description", "markedsleder i Europa", "Fjordtest er markedsleder i Europa"),
                fact(url, "employee_count_statement", "40 ansatte", "Vi er 14 ansatte i Oslo."),
                fact(url, "product_or_service", "lønnssystem og HR-portal", "Vi tilbyr skybasert fakturering og lønnssystem."),
                {"fact_type": "business_description", "value": "regnskapsprogramvare", "source_url": url, "confidence": 0.9},
                fact(url, "revenue", "50 MNOK", "Etablert i 2009."),
                fact("https://elsewhere.example/", "founded_year", "2009", "Etablert i 2009."),
            ],
        }
        result = validate_extraction(data, [home], registry_profile())
        self.assertEqual(sorted(item["fact_type"] for item in result.facts), ["business_description", "contact_email", "contact_phone", "employee_count_statement", "founded_year", "person_role"])
        for item in result.facts:
            self.assertEqual(item["source_url"], url)
            self.assertEqual(item["retrieved_at"], NOW)
            self.assertEqual(item["content_sha256"], hashlib.sha256(raw("genuine")).hexdigest())
            self.assertTrue(item["evidence_span"])
            self.assertLessEqual(item["confidence"], 0.8)
        self.assertCountEqual(reasons(result), ["evidence_span_not_in_page", "value_not_in_evidence_span", "value_not_in_evidence_span", "evidence_span_not_in_page", "unknown_fact_type", "unknown_source_url"])

    def test_fan_page_classified_fan_yields_no_facts(self):
        fan = page("fan")
        data = {
            "page_classifications": [{"source_url": fan.source_url, "classification": "FAN_COMMUNITY", "evidence_spans": ["Dette er en uoffisiell fanside."]}],
            "facts": [fact(fan.source_url, "person_role", {"person_name": "Kari Nordmann", "role_title": "Daglig leder", "role_category": "ceo"}, "Daglig leder er visstnok Kari Nordmann")],
        }
        result = validate_extraction(data, [fan], registry_profile())
        self.assertEqual(result.facts, [])
        self.assertEqual(reasons(result), ["page_not_classified_first_party"])

    def test_fan_and_directory_pages_stay_rejected_by_the_deterministic_gate(self):
        """The gate never sees model output, so an LLM 'FIRST_PARTY' label cannot change its verdict."""
        target = {"organisation_number": ORG, "name": NAME, "business_address": {"adresse": ["Storgata 1"], "postnummer": "0155"}}
        self.assertEqual(classify_site(target, "fjordtest-fans.no", [raw("fan").decode()])["class"], "FAN_COMMUNITY")
        self.assertEqual(classify_site(target, "bedrifter-oslo.no", [raw("directory").decode()])["class"], "DIRECTORY")

    def test_directory_page_classified_directory_yields_no_facts(self):
        listing = page("directory")
        data = {
            "page_classifications": [{"source_url": listing.source_url, "classification": "DIRECTORY", "evidence_spans": ["Bedriftsoversikt"]}],
            "facts": [fact(listing.source_url, "office_location", "Storgata 1, 0155 Oslo", "Fjordtest Programvare AS – org.nr 923 609 016 – Storgata 1, 0155 Oslo")],
        }
        self.assertEqual(validate_extraction(data, [listing], registry_profile()).facts, [])

    def test_ambiguous_page_and_unsupported_classification_yield_no_facts(self):
        reseller = page("ambiguous")
        item = fact(reseller.source_url, "product_or_service", "Regnskapsprogrammer", "Regnskapsprogrammer")
        ambiguous = {"page_classifications": [{"source_url": reseller.source_url, "classification": "AMBIGUOUS", "evidence_spans": ["Vi er forhandler av flere systemer"]}], "facts": [item]}
        self.assertEqual(validate_extraction(ambiguous, [reseller], registry_profile()).facts, [])
        # FIRST_PARTY without an evidence span that exists on the page is not a classification at all.
        unsupported = {"page_classifications": [fp(reseller.source_url, "Fjordtest Programvare AS, org.nr 923 609 016")], "facts": [item]}
        result = validate_extraction(unsupported, [reseller], registry_profile())
        self.assertEqual(result.facts, [])
        self.assertIn("invalid_label_or_no_evidence", reasons(result))

    def test_multilingual_roles_normalise_without_merging_distinct_people(self):
        team = page("multilingual")
        url = team.source_url
        role = lambda name, title, category, span: fact(url, "person_role", {"person_name": name, "role_title": title, "role_category": category}, span)  # noqa: E731
        data = {
            "page_classifications": [fp(url, "Org.nr 923609016")],
            "facts": [
                role("Kari Nordmann", "Daglig leder", "cfo", "Kari Nordmann – Daglig leder"),  # wrong category: the table corrects it
                role("Kari Nordmann", "Chief Executive Officer", "ceo", "Kari Nordmann, Chief Executive Officer"),
                role("Ingrid Berg", "Økonomisjef", "cfo", "Ingrid Berg – Økonomisjef"),
                role("Ingrid Bergström", "Head of Partnerships", "other", "Ingrid Bergström, Head of Partnerships"),
            ],
        }
        result = validate_extraction(data, [team], registry_profile())
        people = sorted((item["value"]["person_name"], item["value"]["role_category"]) for item in result.facts)
        self.assertEqual(people, [("Ingrid Berg", "cfo"), ("Ingrid Bergström", "other"), ("Kari Nordmann", "ceo")])
        kari = next(item for item in result.facts if item["value"]["person_name"] == "Kari Nordmann")
        self.assertEqual(kari["corroborating_spans"][0]["evidence_span"], "Kari Nordmann, Chief Executive Officer")
        self.assertEqual(result.normalizations, {"deterministic_table": 3, "llm": 1})
        self.assertEqual(normalize_role("adm. dir.", None), ("ceo", "deterministic_table"))
        self.assertEqual(normalize_role("Head of Fun", "wizard"), (None, "invalid_category"))

    def test_social_profiles_must_be_linked_from_the_verified_page(self):
        social = page("social", f"{BASE}/")
        url = social.source_url
        profile = lambda platform, link, span: {"profile_url": link, "platform": platform, "source_page": url, "evidence_span": span}  # noqa: E731
        data = {
            "page_classifications": [fp(url, "Org.nr 923 609 016")],
            "profiles": [
                profile("linkedin", "https://www.linkedin.com/company/fjordtest-programvare/", "LinkedIn"),
                profile("facebook", "https://www.facebook.com/fjordtestprogramvare", "Facebook"),
                profile("instagram", "https://www.instagram.com/fjordtestprogramvare/", "Instagram"),
                profile("youtube", "https://www.youtube.com/@fjordtestprogramvare", "YouTube"),
                profile("facebook", "https://www.facebook.com/sharer.php?u=https://fjordtest.no", "Del på Facebook"),
                profile("instagram", "https://www.instagram.com/fjordtest_gammel", "instagram.com/fjordtest_gammel"),
                profile("linkedin", "https://www.linkedin.com/company/fjordtest-invented/", "LinkedIn"),
                profile("x", "https://x.com/fjordtest", "Følg oss i sosiale medier!"),
            ],
        }
        result = validate_extraction(data, [social], registry_profile(), known_profile_urls={normalize_social_url("https://www.youtube.com/@fjordtestprogramvare")["url"]})
        self.assertEqual(sorted(item["platform"] for item in result.profiles), ["facebook", "instagram", "linkedin"])
        self.assertEqual(result.duplicates, 1, "a profile the deterministic parser already found is not re-added")
        for item in result.profiles:
            self.assertTrue(item["first_party_linked"])
            self.assertEqual(item["source_page"], url)
            self.assertTrue(item["evidence_span"])
            self.assertEqual(item["content_sha256"], social.content_sha256)
        self.assertCountEqual(reasons(result), ["not_a_profile_url", "not_linked_from_verified_page", "not_linked_from_verified_page", "platform_not_allowed"])

    def test_dated_news_keeps_only_explicit_dates_and_missing_dates_stay_missing(self):
        news = page("news")
        url = news.source_url
        activity = lambda title, date, span, summary=None: {"title": title, "publication_date": date, "summary": summary, "source_url": url, "evidence_span": span}  # noqa: E731
        data = {
            "page_classifications": [fp(url, "Org.nr 923 609 016")],
            "activities": [
                activity("Ny avdeling i Bergen", "2026-09-12", "Publisert 12. september 2026.", "Fjordtest åpner kontor på Bryggen i Bergen."),
                activity("Lansering av ny lønnsmodul", "2026-08-15", "15.08.2026: Vi lanserer en ny lønnsmodul for små bedrifter.", "Global lansering i 40 land."),
                activity("Vi har fått nytt kundesenter", "2026-09-01", "Kundesenteret vårt er nå åpent lenger hver dag."),  # invented date
                activity("Vi har fått nytt kundesenter", None, "Kundesenteret vårt er nå åpent lenger hver dag."),
                activity("Ny avdeling i Bergen", "2026-09-11", "Publisert 12. september 2026."),  # wrong date
            ],
            "facts": [fact(url, "office_location", "Bryggen i Bergen", "Fjordtest åpner kontor på Bryggen i Bergen.", date_if_explicit="2026-09-12")],
        }
        result = validate_extraction(data, [news], registry_profile())
        self.assertEqual([(item["title"], item["publication_date"]) for item in result.activities], [("Ny avdeling i Bergen", "2026-09-12"), ("Lansering av ny lønnsmodul", "2026-08-15")])
        self.assertIsNone(result.activities[1]["summary"], "an unsupported summary is dropped, not published")
        self.assertEqual(reasons(result), ["no_explicit_date_in_span"] * 3)
        self.assertIsNone(result.facts[0]["date_if_explicit"], "a date absent from the span stays missing")
        self.assertEqual(result.dates_dropped, 3)

    def test_malformed_html_is_read_and_still_validated(self):
        broken = page("malformed")
        self.assertIn("Daglig leder Kari Nordmann", broken.text)
        data = {
            "page_classifications": [fp(broken.source_url, "Org.nr 923 609 016")],
            "facts": [fact(broken.source_url, "person_role", {"person_name": "Kari Nordmann", "role_title": "Daglig leder", "role_category": "ceo"}, "Daglig leder Kari Nordmann"), fact(broken.source_url, "founded_year", "2009", "Etablert i 2009")],
        }
        self.assertEqual(len(validate_extraction(data, [broken], registry_profile()).facts), 2)
        self.assertEqual(prepare_page("https://x.no/", b"\x00\xff<<<>>>", retrieved_at=NOW, content_sha256="0" * 64).links, [])

    def test_conflicting_content_is_rejected_not_resolved_by_guessing(self):
        about = page("conflicting")
        url = about.source_url
        data = {
            "page_classifications": [fp(url, "Org.nr 923 609 016")],
            "facts": [
                fact(url, "founded_year", "2009", "Etablert i 2009 i Oslo."),
                fact(url, "founded_year", "2011", "Siden 2011 har vi levert regnskapsprogramvare."),
                fact(url, "person_role", {"person_name": "Per Hansen", "role_title": "Daglig leder", "role_category": "ceo"}, "Daglig leder Per Hansen"),
            ],
        }
        result = validate_extraction(data, [about], registry_profile())
        self.assertEqual(result.facts, [])
        self.assertCountEqual(reasons(result), ["conflicting_values_on_site", "conflicting_values_on_site", "conflicts_with_registry_role"])


class DateTests(unittest.TestCase):
    def test_explicit_dates_only(self):
        self.assertEqual(explicit_dates("Publisert 12. september 2026"), {"2026-09-12"})
        self.assertEqual(explicit_dates("15.08.2026: ny modul"), {"2026-08-15"})
        self.assertEqual(explicit_dates("September 1, 2026 and 2026-03-04"), {"2026-09-01", "2026-03-04"})
        self.assertEqual(explicit_dates("1 okt 2025"), {"2025-10-01"})
        self.assertEqual(explicit_dates("31.02.2026, 01.01.2999, i fjor høst, 2026"), set())


# ---------- synthesis ----------

class SynthesisTests(unittest.TestCase):
    def facts(self):
        claims = claims_from_profile(enriched_profile()).claims
        return synthesis_facts(claims)

    def test_only_grounded_sections_survive(self):
        facts = self.facts()
        by_field = {item["field"]: item["fact_id"] for item in facts}
        name_id, ceo_id = by_field["legal_name"], by_field["website_named_role"]
        data = {
            "sections": [
                {"heading": "overview", "text": f"{NAME} is a registered company.", "fact_ids": [name_id]},
                {"heading": "leadership", "text": "The website names Kari Nordmann as Daglig leder.", "fact_ids": [ceo_id]},
                {"heading": "financials", "text": "Revenue was 12 000 000 NOK.", "fact_ids": [name_id]},
                {"heading": "business", "text": "It is owned by Equinor.", "fact_ids": [name_id]},
                {"heading": "locations", "text": "It has offices in Oslo.", "fact_ids": []},
                {"heading": "web_presence", "text": "It has a website.", "fact_ids": ["f999"]},
                {"heading": "made_up", "text": "x", "fact_ids": [name_id]},
            ],
            "uncertainties": [{"text": "No dated activity was found.", "fact_ids": []}, {"text": "Revenue is 9 million.", "fact_ids": []}],
        }
        result = validate_synthesis(data, facts, {"name": NAME})
        self.assertEqual([section["heading"] for section in result.sections], ["overview", "leadership"])
        self.assertCountEqual([item["reason"] for item in result.rejected], ["number_not_in_cited_facts", "name_not_in_cited_facts", "missing_or_unknown_fact_ids", "missing_or_unknown_fact_ids", "unknown_or_repeated_heading", "number_not_in_cited_facts"])
        self.assertEqual(len(result.uncertainties), 1)
        self.assertTrue(all(section["claim_keys"] for section in result.sections))
        self.assertGreater(len(result.expected_headings), 2)
        self.assertAlmostEqual(result.completeness, round(2 / len(result.expected_headings), 3))


# ---------- the layer: budgets and fallbacks ----------

class ScriptedProvider(LLMProvider):
    """Mock model: canned JSON per task; counts calls; can fail or raise."""

    name = "scripted"
    enabled = True
    model = "mock-model"

    def __init__(self, extraction=None, synthesis=None, error: str | None = None, raises: bool = False):
        self.extraction, self.synthesis, self.error, self.raises = extraction, synthesis, error, raises
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def complete_json(self, *, system, user, max_output_tokens=None, timeout_s=None):
        task = "extraction" if system.startswith("You extract") else "synthesis"
        with self.lock:
            self.calls.append(task)
        if self.raises:
            raise RuntimeError("provider bug")
        if self.error:
            return LLMResponse(ok=False, error=self.error, attempts=2, latency_ms=5)
        script = self.extraction if task == "extraction" else self.synthesis
        data = script(json.loads(user)) if callable(script) else script
        return LLMResponse(ok=data is not None, data=data, error=None if data is not None else "model_output_not_json_object", attempts=1, latency_ms=3, input_tokens=100, output_tokens=50)


def genuine_extraction(prompt: dict) -> dict:
    url = prompt["pages"][0]["source_url"]
    return {
        "page_classifications": [fp(page["source_url"], "Org.nr") for page in prompt["pages"] if "Org.nr" in page["text"]],
        "facts": [
            fact(url, "person_role", {"person_name": "Kari Nordmann", "role_title": "Daglig leder", "role_category": "ceo"}, "Daglig leder Kari Nordmann"),
            fact(url, "business_description", "utvikler regnskapsprogramvare for små bedrifter i Norge", "Fjordtest Programvare AS utvikler regnskapsprogramvare for små bedrifter i Norge."),
            fact(url, "business_description", "Norges største programvarehus", "Norges største programvarehus"),  # hallucinated
        ],
    }


def name_synthesis(prompt: dict) -> dict:
    name_id = next(item["fact_id"] for item in prompt["facts"] if item["field"] == "legal_name")
    return {"sections": [{"heading": "overview", "text": f"{NAME} is a registered company.", "fact_ids": [name_id]}], "uncertainties": []}


class FakeSession:
    def __init__(self, pages: dict[str, bytes]):
        self.pages = pages

    def cached(self, url):
        body = self.pages.get(url)
        return ByteFetch(url, 200, 1, body, "text/html", {}, hashlib.sha256(body).hexdigest(), NOW, 1) if body is not None else None


def enriched_profile(extraction_pages=("genuine",)) -> dict:
    """A deterministic-V2-shaped profile with a verified site whose pages are the given fixtures."""
    profile = registry_profile()
    live = {"organisation_number": ORG, "name": NAME}
    profile["evidence"]["registry_live"] = evidence("registry_live", "available", "official_registry_live", f"https://data.brreg.no/enhetsregisteret/api/enheter/{ORG}", value=live, content_sha256="a" * 64, retrieved_at=NOW)
    pages = [{"url": f"{BASE}/" if index == 0 else f"{BASE}/{name}/", "content_sha256": hashlib.sha256(raw(name)).hexdigest(), "retrieved_at": NOW, "status": 200} for index, name in enumerate(extraction_pages)]
    site = {"status": "verified", "site_url": f"{BASE}/", "identity_class": "FIRST_PARTY_CONFIRMED", "identity_reasons": ["C1: organisation number in the site's own footer/contact/legal text"], "pages": pages, "profiles": [], "ambiguous_profiles": [], "activities": [], "jobs": []}
    profile["evidence"]["site_research"] = evidence("site_research", "available", "company_site", f"{BASE}/", value=site, content_sha256=pages[0]["content_sha256"], retrieved_at=NOW)
    profile["llm"] = {"model": "mock-model", "extraction": {"facts": [{"fact_type": "person_role", "value": {"person_name": "Kari Nordmann", "role_title": "Daglig leder", "role_category": "ceo"}, "source_url": f"{BASE}/", "retrieved_at": NOW, "content_sha256": pages[0]["content_sha256"], "evidence_span": "Daglig leder Kari Nordmann", "date_if_explicit": None, "confidence": 0.8}]}}
    return profile


def session_for(extraction_pages=("genuine",)) -> FakeSession:
    return FakeSession({(f"{BASE}/" if index == 0 else f"{BASE}/{name}/"): raw(name) for index, name in enumerate(extraction_pages)})


def bare(profile: dict) -> dict:
    copy_ = copy.deepcopy(profile)
    copy_.pop("llm", None)
    return copy_


def layer(provider: LLMProvider, **env) -> LLMLayer:
    return LLMLayer(provider, LLMConfig.from_env({**ENABLED_ENV, **env}))


class LayerTests(unittest.TestCase):
    def test_disabled_layer_is_a_no_op(self):
        profile = bare(enriched_profile())
        before = copy.deepcopy(profile)
        for disabled in (LLMLayer(), LLMLayer.from_env({}), LLMLayer.from_env({"LLM_ENABLED": "true"})):
            self.assertFalse(disabled.enabled)
            disabled.enrich_company(profile, session_for())
        self.assertEqual(profile, before)

    def test_two_calls_at_most_and_hallucinations_never_become_claims(self):
        provider = ScriptedProvider(genuine_extraction, name_synthesis)
        profile = bare(enriched_profile())
        layer(provider).enrich_company(profile, session_for())
        self.assertEqual(provider.calls, ["extraction", "synthesis"])
        record = profile["llm"]
        self.assertEqual(record["status"], "enriched")
        self.assertEqual(len(record["extraction"]["facts"]), 2)
        self.assertEqual([item["reason"] for item in record["extraction"]["rejected"]], ["evidence_span_not_in_page"])
        self.assertEqual(record["synthesis"]["sections"][0]["heading"], "overview")
        claims = [claim for claim in claims_from_profile(profile).claims if claim.get("derivation") == "llm_extraction"]
        self.assertEqual(len(claims), 2)
        self.assertNotIn("Norges største programvarehus", json.dumps(claims, ensure_ascii=False))
        for claim in claims:
            self.assertTrue(claim["evidence_span"])

    def test_call_budgets(self):
        provider = ScriptedProvider(genuine_extraction, name_synthesis)
        layer(provider, LLM_MAX_CALLS_PER_COMPANY="1").enrich_company(bare(enriched_profile()), session_for())
        self.assertEqual(provider.calls, ["extraction"])
        provider = ScriptedProvider(genuine_extraction, name_synthesis)
        shared = layer(provider, LLM_MAX_CALLS_PER_RUN="3")
        for _ in range(3):
            shared.enrich_company(bare(enriched_profile()), session_for())
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual(shared.report()["calls"], 3)
        self.assertGreaterEqual(shared.report()["run_budget_stops"], 1)
        provider = ScriptedProvider(genuine_extraction, name_synthesis)
        layer(provider, LLM_SYNTHESIS="off").enrich_company(bare(enriched_profile()), session_for())
        self.assertEqual(provider.calls, ["extraction"])

    def test_no_call_without_a_verified_site_or_without_a_reason(self):
        provider = ScriptedProvider(genuine_extraction, name_synthesis)
        profile = bare(enriched_profile())
        profile["evidence"]["site_research"]["status"] = "not_found"
        layer(provider).enrich_company(profile, session_for())
        self.assertEqual(provider.calls, [])
        self.assertIn("no_verified_website", profile["llm"]["skip_reasons"])
        site = {"status": "verified", "profiles": [], "activities": []}
        quiet = prepare_page(f"{BASE}/", b"<html><p>Hei.</p></html>", retrieved_at=NOW, content_sha256="0" * 64)
        self.assertEqual(extraction_triggers(site, [quiet], has_description=True), [])

    def test_failures_fall_back_to_the_deterministic_profile(self):
        for provider in (ScriptedProvider(error="http_500"), ScriptedProvider(error="transport_TimeoutError"), ScriptedProvider(extraction=None, synthesis=None), ScriptedProvider(raises=True)):
            profile = bare(enriched_profile())
            deterministic = claims_from_profile(bare(profile)).claims
            layer(provider).enrich_company(profile, session_for())
            self.assertEqual(profile["llm"]["status"], "fallback")
            self.assertIsNone(profile["llm"]["extraction"])
            self.assertEqual(claims_from_profile(profile).claims, deterministic)

    def test_page_whose_bytes_do_not_match_the_evidence_hash_is_not_sent(self):
        provider = ScriptedProvider(genuine_extraction, name_synthesis)
        profile = bare(enriched_profile())
        layer(provider).enrich_company(profile, FakeSession({f"{BASE}/": raw("genuine") + b"tampered"}))
        self.assertNotIn("extraction", provider.calls)
        self.assertEqual(profile["llm"]["failures"][0]["error"], "content_hash_mismatch")


# ---------- the batch pipeline ----------

def _strip_volatile(value):
    if isinstance(value, dict):
        return {key: _strip_volatile(item) for key, item in value.items() if key not in {"started_at", "completed_at", "runtime_ms", "retrieved_at", "final_timestamp", "request_latency", "company_runtime"}}
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def site_web():
    from test_site_research import FakeWeb

    return FakeWeb({f"{BASE}/robots.txt": (200, b"User-agent: *\nAllow: /\n"), f"{BASE}/": (200, raw("genuine")), f"{BASE}/om-oss/": (200, raw("multilingual"))})


def batch(llm_layer=None, web=None):
    from test_contract import FakeBrreg, entity_body, make_website_fetcher, rows
    from norway_company_agent.pipeline import run_batch

    body = entity_body(ORG, NAME)
    body["epostadresse"] = "post@fjordtest.no"
    return run_batch(rows(ORG), run_id="t", fetcher=FakeBrreg({ORG: body}), website_fetcher=make_website_fetcher({}), site_fetcher=web or site_web(), resolver=lambda host: True, llm_layer=llm_layer)


class PipelineTests(unittest.TestCase):
    def test_disabled_layer_reproduces_v2_exactly(self):
        baseline = batch()
        for disabled in (LLMLayer(), LLMLayer.from_env({}), LLMLayer(DisabledProvider())):
            output = batch(disabled)
            self.assertEqual(_strip_volatile(output["envelopes"]), _strip_volatile(baseline["envelopes"]))
            self.assertEqual(_strip_volatile(output["profiles"]), _strip_volatile(baseline["profiles"]))
            self.assertEqual(_strip_volatile(output["report"]), _strip_volatile(baseline["report"]))
        self.assertNotIn("llm", baseline["report"])
        self.assertEqual(baseline["report"]["operations"]["llm_calls"], 0)

    def test_enabled_layer_adds_grounded_claims_and_keeps_every_deterministic_claim(self):
        baseline = batch()["envelopes"][0]
        web = site_web()
        provider = ScriptedProvider(genuine_extraction, name_synthesis)
        output = batch(layer(provider), web)
        envelope = output["envelopes"][0]
        self.assertEqual(validate_envelope(envelope), [])
        self.assertEqual(provider.calls, ["extraction", "synthesis"])
        deterministic = [claim for claim in envelope["claims"] if claim.get("derivation") != "llm_extraction"]
        self.assertEqual(_strip_volatile(deterministic), _strip_volatile(baseline["claims"]))
        llm_claims = [claim for claim in envelope["claims"] if claim.get("derivation") == "llm_extraction"]
        self.assertEqual(sorted(claim["field"] for claim in llm_claims), ["website_business_description", "website_named_role"])
        evidence_by_id = {item["id"]: item for item in envelope["evidence"]}
        for claim in llm_claims:
            cited = evidence_by_id[claim["evidence_ids"][0]]
            self.assertEqual(cited["source_url"], f"{BASE}/")
            self.assertEqual(cited["content_sha256"], hashlib.sha256(raw("genuine")).hexdigest())
            self.assertEqual(cited["claim_span"], claim["evidence_span"])
            self.assertTrue(cited["retrieved_at"])
        self.assertTrue(envelope["company_synthesis"]["presentation_only"])
        self.assertEqual(envelope["llm"]["calls"], 2)
        self.assertEqual(output["report"]["llm"]["calls"], 2)
        self.assertEqual(output["report"]["operations"]["llm_calls"], 2)
        self.assertEqual(len([url for url in web.calls if "llm" in url]), 0, "the layer makes no web requests")

    def test_llm_failure_never_fails_the_company(self):
        baseline = batch()["envelopes"][0]
        for provider in (ScriptedProvider(error="transport_TimeoutError"), ScriptedProvider(raises=True)):
            output = batch(layer(provider))
            envelope = output["envelopes"][0]
            self.assertEqual(envelope["run"]["terminal_status"], "completed")
            self.assertTrue(output["report"]["validation"]["passed"])
            self.assertEqual(_strip_volatile(envelope["claims"]), _strip_volatile(baseline["claims"]))
            self.assertNotIn("company_synthesis", envelope)

    def test_fan_site_gets_no_llm_call_even_if_the_model_would_call_it_first_party(self):
        from test_site_research import FakeWeb

        fan_web = FakeWeb({f"{BASE}/robots.txt": (200, b"User-agent: *\nAllow: /\n"), f"{BASE}/": (200, raw("fan"))})
        always_first_party = ScriptedProvider(lambda prompt: {"page_classifications": [fp(page["source_url"], "Fjordtest") for page in prompt["pages"]], "facts": []}, name_synthesis)
        envelope = batch(layer(always_first_party), fan_web)["envelopes"][0]
        self.assertEqual(always_first_party.calls, [])
        self.assertNotIn(("official_website", "available"), {(claim["field"], claim["availability"]) for claim in envelope["claims"]})
        self.assertFalse(any(claim.get("derivation") for claim in envelope["claims"]))

    def test_ab_comparison_metrics_offline(self):
        import importlib.util
        import tempfile

        spec = importlib.util.spec_from_file_location("compare_llm_ab", ROOT / "scripts" / "compare_llm_ab.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            for arm, llm_layer in (("disabled", None), ("enabled", layer(ScriptedProvider(genuine_extraction, name_synthesis)))):
                from test_contract import FakeBrreg, entity_body, make_website_fetcher, rows
                from norway_company_agent.pipeline import run_batch

                body = entity_body(ORG, NAME)
                body["epostadresse"] = "post@fjordtest.no"
                out = Path(tmp) / arm
                (out / "snapshots").mkdir(parents=True)
                result = run_batch(rows(ORG), run_id=arm, fetcher=FakeBrreg({ORG: body}), website_fetcher=make_website_fetcher({}), site_fetcher=site_web(), resolver=lambda host: True, snapshot_root=out / "snapshots", llm_layer=llm_layer)
                (out / "envelopes.jsonl").write_text("".join(json.dumps(item) + "\n" for item in result["envelopes"]))
                (out / "report.json").write_text(json.dumps(result["report"]))
            walls = {"disabled": {"wall_s": 1.0}, "enabled": {"wall_s": 2.0}}
            metrics = module.compare("s", Path(tmp) / "disabled", Path(tmp) / "enabled", walls)
            self.assertEqual(metrics["llm_calls"], 2)
            self.assertEqual(metrics["facts"]["llm_derived"], 2)
            self.assertEqual(metrics["facts"]["enabled_available"] - metrics["facts"]["disabled_available"], 2)
            self.assertEqual(metrics["precision"]["llm_grounding_failures"], [])
            self.assertEqual(metrics["precision"]["llm_identity_changes"], [])
            self.assertEqual(metrics["rejected_llm_items"]["total"], 1)
            self.assertEqual(metrics["synthesis"]["companies_with_synthesis"], 1)
            self.assertEqual(metrics["valid_envelopes"], {"disabled": 1, "enabled": 1})
            # Tamper with B's snapshot: the span can no longer be found, so it is a grounding failure.
            enabled = Path(tmp) / "enabled"
            envelope = json.loads((enabled / "envelopes.jsonl").read_text())
            envelope["claims"] = [dict(claim, evidence_span="Invented sentence") if claim.get("derivation") else claim for claim in envelope["claims"]]
            (enabled / "envelopes.jsonl").write_text(json.dumps(envelope) + "\n")
            self.assertEqual(len(module.compare("s", Path(tmp) / "disabled", enabled, walls)["precision"]["llm_grounding_failures"]), 2)

    def test_normal_batch_command_does_not_wire_the_llm(self):
        self.assertNotIn("llm", (ROOT / "scripts" / "run_competition_batch.py").read_text().casefold())


# ---------- the configurable provider (fake transport, no network) ----------

def openai_payload(content: str, usage=True) -> bytes:
    body = {"choices": [{"message": {"content": content}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 120, "completion_tokens": 30}
    return json.dumps(body).encode()


class ProviderTests(unittest.TestCase):
    def test_config_defaults_to_disabled_and_hides_the_key(self):
        self.assertFalse(LLMConfig.from_env({}).enabled)
        self.assertEqual(LLMConfig.from_env({"LLM_ENABLED": "true", "LLM_API_KEY": "k", "LLM_BASE_URL": "https://h/v1"}).disabled_reason, "LLM_MODEL is empty")
        self.assertEqual(LLMConfig.from_env({**ENABLED_ENV, "LLM_API_KEY": ""}).disabled_reason, "LLM_API_KEY is empty")
        self.assertEqual(LLMConfig.from_env({**ENABLED_ENV, "LLM_ENABLED": "false"}).disabled_reason, "LLM_ENABLED is not true")
        config = LLMConfig.from_env({**ENABLED_ENV, "LLM_MAX_CALLS_PER_COMPANY": "9"})
        self.assertTrue(config.enabled)
        self.assertEqual(config.max_calls_per_company, 2, "hard ceiling of two calls per company")
        self.assertNotIn("sk-test-not-real", repr(config) + json.dumps(config.public()))
        with self.assertRaises(ValueError):
            ConfigurableProvider(LLMConfig())

    def test_openai_chat_wire_format(self):
        seen = {}

        def transport(url, headers, body, timeout, max_bytes):
            seen.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
            return 200, openai_payload('```json\n{"ok": true}\n```')

        provider = ConfigurableProvider(LLMConfig.from_env(ENABLED_ENV), transport=transport)
        response = provider.complete_json(system="s", user="u", timeout_s=5)
        self.assertTrue(response.ok)
        self.assertEqual(response.data, {"ok": True})
        self.assertEqual((response.input_tokens, response.output_tokens), (120, 30))
        self.assertEqual(seen["url"], "https://llm.invalid/v1/chat/completions")
        self.assertEqual(seen["headers"]["authorization"], "Bearer sk-test-not-real")
        self.assertEqual(seen["body"]["model"], "mock-model")
        self.assertEqual(seen["body"]["temperature"], 0)
        self.assertTrue(4.0 < seen["timeout"] <= 5, "the caller's remaining budget caps the request timeout")

    def test_anthropic_messages_wire_format(self):
        seen = {}

        def transport(url, headers, body, timeout, max_bytes):
            seen.update(url=url, headers=headers, body=json.loads(body))
            return 200, json.dumps({"content": [{"type": "text", "text": '{"a": 1}'}], "usage": {"input_tokens": 7, "output_tokens": 3}}).encode()

        provider = ConfigurableProvider(LLMConfig.from_env({**ENABLED_ENV, "LLM_API_FORMAT": "anthropic_messages"}), transport=transport)
        response = provider.complete_json(system="s", user="u")
        self.assertEqual((response.data, response.input_tokens), ({"a": 1}, 7))
        self.assertEqual(seen["url"], "https://llm.invalid/v1/messages")
        self.assertEqual(seen["headers"]["x-api-key"], "sk-test-not-real")
        self.assertEqual(seen["body"]["system"], "s")

    def test_retry_limit_and_failure_codes(self):
        def scripted(*outcomes):
            queue = list(outcomes)

            def transport(*args):
                outcome = queue.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            return transport

        config = LLMConfig.from_env({**ENABLED_ENV, "LLM_MAX_RETRIES": "2"})
        no_sleep = lambda seconds: None  # noqa: E731
        ok = ConfigurableProvider(config, scripted((500, b""), (429, b""), (200, openai_payload('{"x": 1}'))), sleep=no_sleep).complete_json(system="s", user="u")
        self.assertEqual((ok.ok, ok.attempts), (True, 3))
        bad_request = ConfigurableProvider(config, scripted((400, b"bad")), sleep=no_sleep).complete_json(system="s", user="u")
        self.assertEqual((bad_request.error, bad_request.attempts), ("http_400", 1))
        down = ConfigurableProvider(config, scripted(TimeoutError(), TimeoutError(), TimeoutError()), sleep=no_sleep).complete_json(system="s", user="u")
        self.assertEqual((down.ok, down.error, down.attempts), (False, "transport_TimeoutError", 3))
        prose = ConfigurableProvider(config, scripted((200, openai_payload("Sure! Here are the facts."))), sleep=no_sleep).complete_json(system="s", user="u")
        self.assertEqual(prose.error, "model_output_not_json_object")
        array = ConfigurableProvider(config, scripted((200, openai_payload("[1, 2]"))), sleep=no_sleep).complete_json(system="s", user="u")
        self.assertEqual(array.error, "model_output_not_json_object")
        garbage = ConfigurableProvider(config, scripted((200, b"<html>")), sleep=no_sleep).complete_json(system="s", user="u")
        self.assertEqual(garbage.error, "invalid_envelope_json")

    def test_retries_never_outlive_the_call_deadline(self):
        calls = []

        def slow(url, headers, body, timeout, max_bytes):
            calls.append(timeout)
            time.sleep(0.3)
            return 503, b""

        provider = ConfigurableProvider(LLMConfig.from_env({**ENABLED_ENV, "LLM_MAX_RETRIES": "3"}), slow, sleep=lambda seconds: None)
        response = provider.complete_json(system="s", user="u", timeout_s=1.5)
        self.assertEqual(response.error, "http_503")
        self.assertLess(len(calls), 4, "no retry is started once less than a second of budget remains")
        self.assertTrue(all(timeout <= 1.5 for timeout in calls))

    def test_response_size_limit(self):
        config = LLMConfig.from_env({**ENABLED_ENV, "LLM_MAX_RESPONSE_BYTES": "2048"})
        provider = ConfigurableProvider(config, lambda url, headers, body, timeout, max_bytes: (200, b"x" * (max_bytes + 1)))
        self.assertEqual(provider.complete_json(system="s", user="u").error, "response_too_large")

    def test_bounded_concurrency(self):
        state = {"now": 0, "peak": 0}
        lock = threading.Lock()

        def transport(*args):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.02)
            with lock:
                state["now"] -= 1
            return 200, openai_payload("{}")

        provider = ConfigurableProvider(LLMConfig.from_env({**ENABLED_ENV, "LLM_MAX_CONCURRENCY": "2"}), transport)
        threads = [threading.Thread(target=provider.complete_json, kwargs={"system": "s", "user": "u"}) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertLessEqual(state["peak"], 2)


if __name__ == "__main__":
    unittest.main()
