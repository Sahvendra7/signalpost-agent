"""Experiment 5 (optional): search-provider website discovery, isolated behind an interface.

Search output is never evidence. It nominates URLs; each is crawled and must pass the strict
discovered-site gate. With no API key the NoSearchProvider is used and nothing changes.
Brave Search API list price (2026): $5 per 1,000 requests, $5 free credit per month.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .common import Timer
from ..discovery import BLOCKED_DISCOVERY_HOSTS, parse_brave_web_results
from ..identity import assess_discovered_website_identity
from ..website import _registered_domain, fetch_website, normalize_homepage
from .site_discovery import name_domain_guesses

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
BRAVE_USD_PER_REQUEST = float(os.environ.get("BRAVE_USD_PER_1000", "5")) / 1000


@dataclass
class SearchResponse:
    query: str
    results: list[dict[str, Any]]
    requests: int
    cost_usd: float
    latency_ms: int
    error: str | None = None


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, count: int = 5) -> SearchResponse: ...


class NoSearchProvider:
    name = "none"

    def search(self, query: str, *, count: int = 5) -> SearchResponse:
        return SearchResponse(query, [], 0, 0.0, 0, error="search disabled")


@dataclass
class BraveSearchProvider:
    api_key: str
    timeout: float = 15.0
    name: str = "brave"
    min_interval_s: float = 0.05
    _last: float = field(default=0.0, repr=False)

    @classmethod
    def from_env(cls) -> "BraveSearchProvider | None":
        key = os.environ.get("BRAVE_SEARCH_API_KEY") or os.environ.get("BRAVE_API_KEY")
        return cls(key) if key else None

    def search(self, query: str, *, count: int = 5) -> SearchResponse:
        delay = self.min_interval_s - (time.monotonic() - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()
        url = BRAVE_ENDPOINT + "?" + urllib.parse.urlencode({"q": query, "count": count, "country": "no", "search_lang": "nb", "safesearch": "moderate", "spellcheck": "0"})
        request = urllib.request.Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity", "X-Subscription-Token": self.api_key, "User-Agent": "builderr-signalpost-poc/0.1"})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
            return SearchResponse(query, parse_brave_web_results(payload, query=query), 1, BRAVE_USD_PER_REQUEST, int((time.monotonic() - started) * 1000))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return SearchResponse(query, [], 1, BRAVE_USD_PER_REQUEST, int((time.monotonic() - started) * 1000), error=type(exc).__name__)


def default_provider() -> SearchProvider:
    return BraveSearchProvider.from_env() or NoSearchProvider()


def strategy_queries(profile: dict[str, Any], strategy: str) -> list[str]:
    name = " ".join(str(profile.get("name") or "").split())
    org = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    municipality = str(profile.get("municipality") or ((profile.get("evidence", {}).get("registry_live") or {}).get("value") or {}).get("business_address", {}).get("kommune") or "")
    if not name:
        return []
    if strategy == "A_name_norway":
        return [f'"{name}" Norge']
    if strategy == "B_name_orgnr":
        return [f'"{name}" "{org}"']
    if strategy == "C_orgnr":
        return [f'"{org[:3]} {org[3:6]} {org[6:]}" OR "{org}"']
    if strategy == "D_site_guess":
        return [f"site:{guess}" for guess in name_domain_guesses(name)[:1]]
    if strategy == "E_name_municipality":
        return [f'"{name}" {municipality}'.strip()]
    raise ValueError(f"unknown strategy {strategy}")


STRATEGIES = ("A_name_norway", "B_name_orgnr", "C_orgnr", "D_site_guess", "E_name_municipality")


def candidate_domains(results: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    domains: list[str] = []
    for result in results:
        url = normalize_homepage(result.get("url"))
        domain = _registered_domain(url) if url else None
        if not domain or domain in BLOCKED_DISCOVERY_HOSTS or domain in domains:
            continue
        domains.append(domain)
        if len(domains) >= limit:
            break
    return domains


def run_company(
    profile: dict[str, Any],
    provider: SearchProvider,
    strategy: str,
    *,
    website_fetcher: Callable[..., tuple[dict[str, Any], dict[str, Any]]] = fetch_website,
    known_domain: str | None = None,
    crawl_limit: int = 3,
) -> dict[str, Any]:
    """`known_domain` (registry-listed site) turns the run into a labelled precision check."""
    profile = {**profile, "business_address": ((profile.get("evidence", {}).get("registry_live") or {}).get("value") or {}).get("business_address") or {}}
    queries = strategy_queries(profile, strategy)
    searches = [provider.search(query) for query in queries]
    results = [item for response in searches for item in response.results]
    outcomes = []
    crawl_requests = 0
    with Timer() as timer:
        for domain in candidate_domains(results, limit=crawl_limit):
            record, metrics = website_fetcher("https://" + domain + "/")
            crawl_requests += int(metrics.get("requests", 0))
            assessment = assess_discovered_website_identity(profile, record)
            outcomes.append({"domain": domain, "status": assessment["status"], "reason": assessment["reasons"][0]})
            if assessment["publishable"]:
                break
    verified = next((item["domain"] for item in outcomes if item["status"] == "exact"), None)
    labelled = None
    if known_domain:
        # A different verified domain may be a legitimate second domain: flagged for manual audit, not auto-counted.
        labelled = "correct" if verified == known_domain else "other_domain_verified_needs_audit" if verified else ("known_domain_in_candidates" if known_domain in [item["domain"] for item in outcomes] else "missed")
    return {
        "organisation_number": profile["organisation_number"],
        "strategy": strategy,
        "provider": provider.name,
        "queries": len(queries),
        "search_requests": sum(item.requests for item in searches),
        "search_cost_usd": round(sum(item.cost_usd for item in searches), 6),
        "search_latency_ms": sum(item.latency_ms for item in searches),
        "search_errors": [item.error for item in searches if item.error],
        "results": len(results),
        "requests": sum(item.requests for item in searches) + crawl_requests,
        "runtime_ms": timer.ms + sum(item.latency_ms for item in searches),
        "outcome": "verified" if verified else "ambiguous" if any(item["status"] == "ambiguous" for item in outcomes) else "no_result" if not results else "rejected",
        "covered": bool(verified),
        "verified_domain": verified,
        "labelled_outcome": labelled,
        "identity_rejections": sum(1 for item in outcomes if item["status"] in {"ambiguous", "rejected"}),
        "published_identity_mismatches": 0,
        "needs_audit": labelled == "other_domain_verified_needs_audit",
        "evidence_items": 1 if verified else 0,
        "evidence_complete": 1 if verified else 0,
        "candidates": outcomes,
    }
