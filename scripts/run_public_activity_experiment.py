#!/usr/bin/env python3
"""Public-activity experiment on the fixed Phase 4A sample (measurement only; not wired into the batch).

  uv run python scripts/run_public_activity_experiment.py \
      --profiles out/experiments/baseline-profiles.jsonl \
      --envelopes out/experiments/baseline-envelopes.jsonl \
      --discovery out/experiments/e4-site-discovery.json \
      --out out/experiments-public-activity [--search]

Stages: (1) verified sites = registry-gate-verified sites + discovered sites that pass identity gate v2;
(2) site-linked social profiles + dated first-party activity per verified site; (3) optional Brave search,
adaptive (only companies whose fifth category is still empty) and naive (every company), query families Q1–Q6.
Search runs only when BRAVE_SEARCH_API_KEY is set; otherwise it is reported UNMEASURED with by-design cost.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.experiments import public_activity, search  # noqa: E402
from norway_company_agent.experiments.common import Meter  # noqa: E402
from norway_company_agent.experiments.identity_v2 import classify_site  # noqa: E402
from norway_company_agent.website import _registered_domain, normalize_homepage  # noqa: E402

BRAVE_USD_PER_REQUEST = 0.005
BRAVE_FREE_CREDIT_USD_PER_MONTH = 5.0


def jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def business_address(profile: dict) -> dict:
    return ((profile.get("evidence", {}).get("registry_live") or {}).get("value") or {}).get("business_address") or {}


def gate_discovered(profile: dict, url: str) -> dict:
    """Identity gate v2 for a discovered site: homepage + up to two contact/about pages, robots honoured."""
    crawler = public_activity.SiteCrawler()
    meter = Meter()
    entity = meter.get(f"https://data.brreg.no/enhetsregisteret/api/enheter/{profile['organisation_number']}", headers={"Accept": "application/json"})
    registry_email = (entity.json() or {}).get("epostadresse") if entity.status == 200 else None
    started = time.monotonic()
    pages = []
    home = crawler.get(url)
    if home is not None and home.status == 200 and home.raw:
        html = home.raw.decode("utf-8", errors="replace")
        pages.append(html)
        from bs4 import BeautifulSoup
        import urllib.parse

        soup = BeautifulSoup(html, "lxml")
        extra = []
        for anchor in soup.select("a[href]"):
            target = urllib.parse.urljoin(url, anchor["href"]).split("#")[0]
            label = (urllib.parse.urlsplit(target).path + " " + anchor.get_text(" ", strip=True)).casefold()
            if _registered_domain(target) == _registered_domain(url) and any(term in label for term in ("kontakt", "contact", "om-oss", "om oss", "about")):
                extra.append(target)
        for target in list(dict.fromkeys(extra))[:2]:
            response = crawler.get(target)
            if response is not None and response.status == 200 and response.raw:
                pages.append(response.raw.decode("utf-8", errors="replace"))
    verdict = classify_site({**profile, "business_address": business_address(profile)}, _registered_domain(url), pages, registry_email=registry_email)
    return {"organisation_number": profile["organisation_number"], "url": url, "class": verdict["class"], "publishable": verdict["publishable"], "reasons": verdict["reasons"], "signals": verdict["signals"], "requests": crawler.meter.requests + meter.requests, "runtime_ms": int((time.monotonic() - started) * 1000)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--envelopes", required=True)
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--search", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    profiles = {row["organisation_number"]: row for row in jsonl(args.profiles)}
    envelopes = {row["organisation_number"]: row for row in jsonl(args.envelopes)}
    population = list(profiles)

    def has(org: str, field: str) -> bool:
        return any(claim["field"] == field and claim["availability"] == "available" for claim in envelopes[org]["claims"])

    baseline = {
        "verified_website": sorted(org for org in population if has(org, "official_website")),
        "site_linked_profile": sorted(org for org in population if has(org, "social_profile")),
        "confirmed_hiring": [],
        "dated_public_activity": [],
    }

    # Stage 1: verified sites.
    sites: dict[str, dict] = {}
    for org in baseline["verified_website"]:
        value = (profiles[org]["evidence"].get("website") or {}).get("value") or {}
        sites[org] = {"url": value.get("final_url"), "class": "REGISTRY_LINKED", "source": "registry_hjemmeside"}
    discovered = [row for row in json.loads(Path(args.discovery).read_text()) if row.get("covered")]
    t0 = time.monotonic()
    gate_rows = list(ThreadPoolExecutor(args.workers).map(lambda row: gate_discovered(profiles[row["organisation_number"]], row["verified_url"]), discovered))
    gate_seconds = time.monotonic() - t0
    for row in gate_rows:
        if row["publishable"] and row["organisation_number"] not in sites:
            sites[row["organisation_number"]] = {"url": row["url"], "class": row["class"], "source": "non_search_discovery+gate_v2"}
    (out / "gate-v2-discovered.json").write_text(json.dumps(gate_rows, indent=2, ensure_ascii=False) + "\n")

    # Stage 2: site-linked profiles and dated first-party activity.
    t0 = time.monotonic()
    activity_rows = list(ThreadPoolExecutor(args.workers).map(lambda item: public_activity.run_company(profiles[item[0]], item[1]["url"], item[1]["class"]), sites.items()))
    activity_seconds = time.monotonic() - t0
    (out / "public-activity.json").write_text(json.dumps(activity_rows, indent=2, ensure_ascii=False, default=str) + "\n")
    by_org = {row["organisation_number"]: row for row in activity_rows}
    free = {
        "profile": sorted(org for org, row in by_org.items() if row["covered_profile"]),
        "dated": sorted(org for org, row in by_org.items() if row["covered_dated_activity"]),
        "recent": sorted(org for org, row in by_org.items() if row["activities_recent_365d"]),
        "any": sorted(org for org, row in by_org.items() if row["covered_any"]),
    }

    # Stage 3: search eligibility and (optionally) execution.
    eligible_adaptive = sorted(org for org in population if org not in free["any"])
    provider = search.default_provider()
    families = list(search.QUERY_FAMILIES)
    search_result = {
        "provider": provider.name,
        "eligible_adaptive_companies": len(eligible_adaptive),
        "eligible_reason": {"no_verified_site": sum(1 for org in eligible_adaptive if org not in sites), "site_but_no_profile_or_activity": sum(1 for org in eligible_adaptive if org in sites)},
        "by_design_cost_usd": {
            "naive_all_families_100": round(100 * len(families) * BRAVE_USD_PER_REQUEST, 3),
            "naive_one_family_100": round(100 * BRAVE_USD_PER_REQUEST, 3),
            "adaptive_max_all_families": round(len(eligible_adaptive) * len(families) * BRAVE_USD_PER_REQUEST, 3),
            "adaptive_max_one_family": round(len(eligible_adaptive) * BRAVE_USD_PER_REQUEST, 3),
        },
    }
    if not (args.search and provider.name != "none"):
        search_result["status"] = "UNMEASURED: no BRAVE_SEARCH_API_KEY" if provider.name == "none" else "SKIPPED: --search not given"
    else:
        search_result["status"] = "MEASURED"
        search_result["families"] = run_search(eligible_adaptive, population, profiles, by_org, provider, families, out)

    total = {
        "verified_sites": len(sites),
        "fifth_category_footprint_definition": sorted(set(baseline["site_linked_profile"]) | set(free["profile"])),
        "fifth_category_profile_or_dated": sorted(set(baseline["site_linked_profile"]) | set(free["any"])),
    }
    requests_gate = sum(row["requests"] for row in gate_rows)
    requests_activity = sum(row["requests"] for row in activity_rows)
    results = {
        "label": "public_activity", "SCORING_MAPPING": "UNCONFIRMED",
        "population": len(population),
        "baseline": {key: len(value) for key, value in baseline.items()},
        "gate_v2_discovered": {"candidates": len(gate_rows), "accepted": sum(row["publishable"] for row in gate_rows), "classes": {row["url"]: row["class"] for row in gate_rows}, "requests": requests_gate, "seconds": round(gate_seconds, 2)},
        "verified_sites": {"total": len(sites), "registry_linked": sum(1 for item in sites.values() if item["class"] == "REGISTRY_LINKED"), "discovered_first_party": sum(1 for item in sites.values() if item["class"] == "FIRST_PARTY")},
        "free_path": {
            "companies_with_verified_site": len(sites),
            "companies_with_accepted_profile": len(free["profile"]),
            "companies_with_dated_activity": len(free["dated"]),
            "companies_with_recent_activity_365d": len(free["recent"]),
            "companies_with_profile_or_dated": len(free["any"]),
            "profiles_accepted": sum(len(row["profiles_accepted"]) for row in activity_rows),
            "profiles_ambiguous": sum(len(row["profiles_ambiguous"]) for row in activity_rows),
            "profiles_by_platform": {platform: sum(1 for row in activity_rows for item in row["profiles_accepted"] if item["platform"] == platform) for platform in sorted({item["platform"] for row in activity_rows for item in row["profiles_accepted"]})},
            "activities_dated": sum(len(row["activities_dated"]) for row in activity_rows),
            "activities_undated": sum(row["activities_undated"] for row in activity_rows),
            "careers_pages_found": sum(1 for row in activity_rows if row["other_official_pages"].get("careers_page")),
            "requests": requests_activity,
            "seconds": round(activity_seconds, 2),
            "robots_blocked_urls": sum(len(row["robots_blocked"]) for row in activity_rows),
            "errors": {row["organisation_number"]: row["error"] for row in activity_rows if row["error"]},
        },
        "newly_covered_vs_baseline": {
            "footprint_definition_profile": sorted(set(free["profile"]) - set(baseline["site_linked_profile"])),
            "profile_or_dated": sorted(set(free["any"]) - set(baseline["site_linked_profile"])),
        },
        "totals": {key: (value if isinstance(value, int) else len(value)) for key, value in total.items()},
        "search": search_result,
        "wall_seconds": round(time.monotonic() - started, 2),
    }
    (out / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(results, indent=2, ensure_ascii=False))


def run_search(eligible, population, profiles, by_org, provider, families, out: Path) -> dict:
    linked = {item["url"] for row in by_org.values() for item in row["profiles_accepted"]}
    report = {}
    for family in families:
        rows = []
        for mode, orgs in (("adaptive", eligible), ("naive", population)):
            for org in orgs:
                profile = profiles[org]
                queries = search.strategy_queries(profile, family)
                responses = [provider.search(query) for query in queries]
                candidates = []
                for response in responses:
                    for result in response.results[:5]:
                        kind = search.classify_search_result(result["url"], linked)
                        record = {"url": result["url"], "rank": result.get("rank"), "pre_class": kind}
                        if kind == "WEBSITE_CANDIDATE":
                            domain = _registered_domain(normalize_homepage(result["url"]) or "")
                            if org in by_org and _registered_domain(by_org[org]["site_url"]) == domain:
                                record["class"] = "FIRST_PARTY (already verified)"
                            else:
                                gate = gate_discovered(profile, "https://" + domain + "/")
                                record.update({"class": gate["class"], "reasons": gate["reasons"], "gate_requests": gate["requests"]})
                        else:
                            record["class"] = kind
                        candidates.append(record)
                        if record["class"] in {"FIRST_PARTY", "OFFICIALLY_LINKED"}:
                            break
                accepted = [item for item in candidates if item["class"] in {"FIRST_PARTY", "OFFICIALLY_LINKED"}]
                rows.append({"mode": mode, "organisation_number": org, "family": family, "queries": len(queries), "cost_usd": sum(r.cost_usd for r in responses), "latency_ms": sum(r.latency_ms for r in responses), "results": sum(len(r.results) for r in responses), "candidates": candidates, "accepted": accepted})
        (out / f"search-{family}.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
        for mode in ("adaptive", "naive"):
            mode_rows = [row for row in rows if row["mode"] == mode]
            report.setdefault(family, {})[mode] = {
                "companies": len(mode_rows), "queries": sum(row["queries"] for row in mode_rows), "cost_usd": round(sum(row["cost_usd"] for row in mode_rows), 4),
                "latency_ms_total": sum(row["latency_ms"] for row in mode_rows),
                "companies_accepted": sum(1 for row in mode_rows if row["accepted"]),
                "no_result": sum(1 for row in mode_rows if not row["results"]),
                "classes": {cls: sum(1 for row in mode_rows for item in row["candidates"] if item["class"] == cls) for cls in sorted({item["class"] for row in mode_rows for item in row["candidates"]})},
            }
    return report


if __name__ == "__main__":
    main()
