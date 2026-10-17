"""Optional LLM enrichment of one researched company. Bounded, gated, and never fatal.

Runs after the deterministic pipeline has finished a company, on content that pipeline already captured:

  verified website (deterministic identity gate) -> deterministic extraction (already done)
  -> call 1, only when extraction_triggers() finds something the parsers could not extract
  -> call 2, synthesis of verified facts, only when configured and there are facts to present

At most `max_calls_per_company` (<= 2) calls per company and `max_calls_per_run` per run. Pages come from
the run's SiteSession cache and are re-hashed against the recorded content_sha256: the layer makes no
web requests. Any failure (disabled, budget, timeout, HTTP error, bad JSON, exception) leaves the
deterministic profile exactly as it was and is recorded under profile["llm"].
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import Counter
from typing import Any, Mapping

from ..site_research import NEWS_HINTS
from .provider import DisabledProvider, LLMConfig, LLMProvider, Transport, provider_from_config
from .tasks import (
    EXTRACTION_SYSTEM, SYNTHESIS_SYSTEM, PageContent, extraction_prompt, extraction_triggers, prepare_page,
    synthesis_facts, synthesis_prompt, validate_extraction, validate_synthesis,
)

MAX_EXTRACTION_PAGES = 3
MIN_SYNTHESIS_FACTS = 3


class LLMLayer:
    def __init__(self, provider: LLMProvider | None = None, config: LLMConfig | None = None):
        self.provider = provider or DisabledProvider()
        self.config = config or LLMConfig()
        self.enabled = bool(self.provider.enabled)
        self._lock = threading.Lock()
        self._run_calls = 0
        self._counters: Counter[str] = Counter()
        self._rejections: Counter[str] = Counter()
        self._failures: Counter[str] = Counter()
        self._latencies: list[int] = []
        self._completeness: list[float] = []

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, transport: Transport | None = None) -> "LLMLayer":
        config = LLMConfig.from_env(env)
        return cls(provider_from_config(config, transport=transport), config)

    # ---------- budget ----------

    def _reserve_call(self, record: dict[str, Any], deadline: float) -> float | None:
        """Seconds available for the next call, or None (and the reason recorded) when the budget is spent."""
        if record["calls"] >= self.config.max_calls_per_company:
            record["budget_stops"].append("max_calls_per_company")
            return None
        remaining = deadline - time.monotonic()
        if remaining < 1.0:
            record["budget_stops"].append("company_time_budget")
            return None
        with self._lock:
            if self._run_calls >= self.config.max_calls_per_run:
                record["budget_stops"].append("max_calls_per_run")
                self._counters["run_budget_stops"] += 1
                return None
            self._run_calls += 1
        record["calls"] += 1
        return remaining

    def _call(self, record: dict[str, Any], task: str, system: str, user: str, deadline: float) -> dict[str, Any] | None:
        remaining = self._reserve_call(record, deadline)
        if remaining is None:
            return None
        response = self.provider.complete_json(system=system, user=user, max_output_tokens=self.config.max_output_tokens, timeout_s=remaining)
        record["attempts"] += response.attempts
        record["latency_ms"] += response.latency_ms
        for key, value in (("input_tokens", response.input_tokens), ("output_tokens", response.output_tokens)):
            if isinstance(value, int):
                record[key] = (record[key] or 0) + value
        with self._lock:
            self._counters[f"calls_{task}"] += 1
            self._counters["attempts"] += response.attempts
            self._counters["retries"] += max(0, response.attempts - 1)
            self._latencies.append(response.latency_ms)
            for key, value in (("input_tokens", response.input_tokens), ("output_tokens", response.output_tokens)):
                if isinstance(value, int):
                    self._counters[key] += value
                    self._counters[f"{key}_reported_calls"] += 1
            if not response.ok:
                self._failures[f"{task}:{response.error}"] += 1
        if not response.ok:
            record["failures"].append({"stage": task, "error": response.error, "attempts": response.attempts})
            return None
        return response.data

    # ---------- pages ----------

    def _pages(self, site: dict[str, Any], session: Any, record: dict[str, Any]) -> list[PageContent]:
        pages = []
        recorded = [page for page in site.get("pages") or [] if page.get("url") and page.get("content_sha256")]
        # Homepage first, then news-like pages (where undated-by-markup activity lives), then the rest.
        chosen = recorded[:1] + sorted(recorded[1:], key=lambda page: not any(hint in page["url"].casefold() for hint in NEWS_HINTS))
        for page in chosen[:MAX_EXTRACTION_PAGES]:
            cached = session.cached(page.get("url") or "") if session is not None and hasattr(session, "cached") else None
            raw = getattr(cached, "raw", None)
            if not raw or getattr(cached, "status", 0) != 200:
                continue
            # Provenance: the text sent to the model must be the exact bytes the evidence hash names.
            if hashlib.sha256(raw).hexdigest() != page.get("content_sha256"):
                record["failures"].append({"stage": "pages", "error": "content_hash_mismatch", "url": page.get("url")})
                continue
            pages.append(prepare_page(page["url"], raw, retrieved_at=page.get("retrieved_at") or getattr(cached, "retrieved_at", ""), content_sha256=page["content_sha256"]))
        return pages

    # ---------- per company ----------

    def enrich_company(self, profile: dict[str, Any], session: Any = None) -> None:
        """Attach profile["llm"]. Never raises; never touches deterministic evidence or claims."""
        if not self.enabled:
            return
        record: dict[str, Any] = {
            "provider": self.provider.name, "model": self.provider.model, "status": "skipped", "skip_reasons": [],
            "calls": 0, "attempts": 0, "latency_ms": 0, "input_tokens": None, "output_tokens": None,
            "budget_stops": [], "failures": [], "extraction": None, "synthesis": None,
        }
        profile["llm"] = record
        deadline = time.monotonic() + self.config.company_budget_s
        with self._lock:
            self._counters["companies_considered"] += 1
        site_record = (profile.get("evidence") or {}).get("site_research") or {}
        site = site_record.get("value") or {}
        verified = site_record.get("status") == "available" and site.get("status") == "verified"
        try:
            if verified:
                self._extract(profile, site, session, record, deadline)
            else:
                record["skip_reasons"].append("no_verified_website")
        except Exception as exc:  # the layer is optional: an exception discards its output, not the company
            record["extraction"] = None
            record["failures"].append({"stage": "extraction", "error": f"exception_{type(exc).__name__}"})
            with self._lock:
                self._failures[f"extraction:exception_{type(exc).__name__}"] += 1
        try:
            if self.config.synthesis == "all" or (self.config.synthesis == "verified_site" and verified):
                self._synthesise(profile, record, deadline)
            else:
                record["skip_reasons"].append(f"synthesis_mode_{self.config.synthesis}")
        except Exception as exc:
            record["synthesis"] = None
            record["failures"].append({"stage": "synthesis", "error": f"exception_{type(exc).__name__}"})
            with self._lock:
                self._failures[f"synthesis:exception_{type(exc).__name__}"] += 1
        added = bool(record["extraction"] and any(record["extraction"][key] for key in ("facts", "profiles", "activities")))
        record["status"] = "enriched" if added or record["synthesis"] else ("fallback" if record["failures"] else "skipped")
        with self._lock:
            self._counters[f"companies_{record['status']}"] += 1
            if record["calls"]:
                self._counters["companies_called"] += 1

    def _extract(self, profile: dict[str, Any], site: dict[str, Any], session: Any, record: dict[str, Any], deadline: float) -> None:
        from ..claims import claims_from_profile  # late import: claims imports nothing from here

        pages = self._pages(site, session, record)
        if not pages:
            record["skip_reasons"].append("no_captured_pages")
            return
        claims = claims_from_profile({key: value for key, value in profile.items() if key != "llm"}).claims
        has_description = any(claim["availability"] == "available" and claim["field"] == "website_description" for claim in claims)
        triggers = extraction_triggers(site, pages, has_description=has_description)
        if not triggers:
            record["skip_reasons"].append("deterministic_extraction_sufficient")
            return
        data = self._call(record, "extraction", EXTRACTION_SYSTEM, extraction_prompt(profile, pages, self.config.max_input_chars), deadline)
        if data is None:
            return
        known_urls = {item.get("canonical_url") or item.get("url") for item in (site.get("profiles") or []) + (site.get("ambiguous_profiles") or []) if item.get("url")}
        result = validate_extraction(data, pages, profile, known_profile_urls=known_urls, known_activities=site.get("activities") or [])
        profiles, ambiguous = self._gate_profiles(profile, result.profiles)
        record["extraction"] = {
            "triggers": triggers,
            "pages": [{"source_url": page.source_url, "content_sha256": page.content_sha256, "retrieved_at": page.retrieved_at} for page in pages],
            "classifications": result.classifications,
            "classification_disagreements": [item for item in result.classifications if item["classification"] != "FIRST_PARTY"],
            "facts": result.facts, "profiles": profiles, "ambiguous_profiles": ambiguous, "activities": result.activities,
            "rejected": result.rejected, "duplicates": result.duplicates, "dates_dropped": result.dates_dropped,
            "normalizations": result.normalizations,
        }
        with self._lock:
            self._counters["facts_accepted"] += len(result.facts)
            self._counters["profiles_accepted"] += len(profiles)
            self._counters["profiles_identity_ambiguous"] += len(ambiguous)
            self._counters["activities_accepted"] += len(result.activities)
            self._counters["duplicates_of_deterministic_or_each_other"] += result.duplicates
            self._counters["dates_dropped_not_explicit"] += result.dates_dropped
            self._counters["classification_disagreements"] += len(record["extraction"]["classification_disagreements"])
            for item in result.rejected:
                self._rejections[f"{item['kind']}:{item['reason']}"] += 1

    def _gate_profiles(self, profile: dict[str, Any], profiles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Same deterministic handle check the V2 site stage applies; the model never decides identity."""
        from ..identity import assess_social_identity

        publishable, ambiguous = [], []
        for item in profiles:
            gate = assess_social_identity(profile, {"platform": item["platform"], "url": item["profile_url"]})
            entry = {**item, "identity_score": gate["identity_score"], "identity_reason": gate["reason"]}
            (publishable if gate["publishable"] else ambiguous).append(entry)
        return publishable, ambiguous

    def _synthesise(self, profile: dict[str, Any], record: dict[str, Any], deadline: float) -> None:
        from ..claims import claims_from_profile

        facts = synthesis_facts(claims_from_profile(profile).claims)
        if len(facts) < MIN_SYNTHESIS_FACTS:
            record["skip_reasons"].append("too_few_verified_facts_for_synthesis")
            return
        data = self._call(record, "synthesis", SYNTHESIS_SYSTEM, synthesis_prompt(profile, facts), deadline)
        if data is None:
            return
        result = validate_synthesis(data, facts, profile)
        if not result.sections:
            record["failures"].append({"stage": "synthesis", "error": "no_grounded_section", "rejected": result.rejected[:10]})
            with self._lock:
                self._failures["synthesis:no_grounded_section"] += 1
                for item in result.rejected:
                    self._rejections[f"synthesis_{item['kind']}:{item['reason']}"] += 1
            return
        record["synthesis"] = {
            "presentation_only": True, "model": self.provider.model, "sections": result.sections,
            "uncertainties": result.uncertainties, "expected_headings": result.expected_headings,
            "completeness": result.completeness, "rejected": result.rejected,
        }
        with self._lock:
            self._counters["syntheses_accepted"] += 1
            if result.completeness is not None:
                self._completeness.append(result.completeness)
            for item in result.rejected:
                self._rejections[f"synthesis_{item['kind']}:{item['reason']}"] += 1

    # ---------- run report ----------

    def report(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            calls = sum(value for key, value in counters.items() if key.startswith("calls_"))
            latencies = sorted(self._latencies)
            return {
                "config": self.config.public(),
                "provider": self.provider.name,
                "calls": calls,
                "calls_by_task": {key[6:]: value for key, value in counters.items() if key.startswith("calls_")},
                "attempts": counters.get("attempts", 0),
                "retries": counters.get("retries", 0),
                "input_tokens": counters.get("input_tokens") if counters.get("input_tokens_reported_calls") else None,
                "output_tokens": counters.get("output_tokens") if counters.get("output_tokens_reported_calls") else None,
                "latency_ms_p50": latencies[len(latencies) // 2] if latencies else None,
                "latency_ms_max": latencies[-1] if latencies else None,
                "companies": {key[10:]: value for key, value in counters.items() if key.startswith("companies_")},
                "accepted": {key: counters.get(key, 0) for key in ("facts_accepted", "profiles_accepted", "activities_accepted", "syntheses_accepted")},
                "profiles_identity_ambiguous": counters.get("profiles_identity_ambiguous", 0),
                "duplicates": counters.get("duplicates_of_deterministic_or_each_other", 0),
                "dates_dropped_not_explicit": counters.get("dates_dropped_not_explicit", 0),
                "classification_disagreements": counters.get("classification_disagreements", 0),
                "rejected_total": sum(self._rejections.values()),
                "rejected_by_reason": dict(sorted(self._rejections.items())),
                "failures_by_reason": dict(sorted(self._failures.items())),
                "run_budget_stops": counters.get("run_budget_stops", 0),
                "synthesis_completeness_mean": round(sum(self._completeness) / len(self._completeness), 3) if self._completeness else None,
            }
