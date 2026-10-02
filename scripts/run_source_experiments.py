#!/usr/bin/env python3
"""Run the source-expansion experiments on one company sample and write measured results.

  uv run python scripts/run_source_experiments.py --organisations sample.jsonl --out out/experiments
  uv run python scripts/run_source_experiments.py --universe signalpost-universe.jsonl.gz --count 100 --out out/experiments

Order: baseline batch -> E1 Brreg activity -> E2 filings/PDF -> E3 NAV jobs -> E4 non-search
discovery -> E5 search (only with BRAVE_SEARCH_API_KEY and --search). A source whose requests all
failed at transport level is reported UNMEASURED, never as zero gain.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.experiments import brreg_activity, filings, nav_jobs, search, site_discovery  # noqa: E402
from norway_company_agent.experiments.common import Meter, summarize  # noqa: E402
from norway_company_agent.pipeline import read_input_rows, run_batch  # noqa: E402
from norway_company_agent.website import _registered_domain, normalize_homepage  # noqa: E402

AREAS = {"filings": "filings", "leadership": "leadership", "locations": "locations", "websites": "websites", "hiring_activity": "activity"}
BRAVE_USD_PER_1000 = 5.0


def write_json(path: Path, body) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def sample_universe(path: str, count: int, seed: int) -> list[dict]:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return random.Random(seed).sample(rows, count)


def pmap(function, items, workers):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(function, items))


def area_sets(envelopes: list[dict]) -> dict[str, set[str]]:
    sets = {area: set() for area in AREAS}
    for envelope in envelopes:
        coverage = envelope.get("category_coverage") or {}
        for area, category in AREAS.items():
            if coverage.get(category) == "available":
                sets[area].add(envelope["organisation_number"])
    return sets


def coverage_view(sets: dict[str, set[str]], population: list[str]) -> dict:
    n = len(population) or 1
    per_area = {area: round(len(members) / n, 4) for area, members in sets.items()}
    all_five = sum(1 for org in population if all(org in members for members in sets.values()))
    return {"per_area": per_area, "mean_area_coverage": round(sum(per_area.values()) / len(per_area), 4), "companies_all_five": all_five, "companies_all_five_rate": round(all_five / n, 4)}


def measured(summary: dict) -> bool:
    return summary.get("companies_measured", 0) > 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organisations")
    parser.add_argument("--universe")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--bulk")
    parser.add_argument("--out", default="out/experiments")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--skip", default="", help="Comma list of experiments to skip: activity,filings,nav,discovery,search")
    parser.add_argument("--search", action="store_true", help="Run E5 when a search API key is configured")
    parser.add_argument("--search-strategies", default=",".join(search.STRATEGIES))
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    skip = {item.strip() for item in args.skip.split(",") if item.strip()}

    if args.universe:
        chosen = sample_universe(args.universe, args.count, args.seed)
        sample_path = out / "sample.jsonl"
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text("".join(json.dumps({"organisation_number": row.get("organisation_number") or row.get("organisasjonsnummer")}) + "\n" for row in chosen), encoding="utf-8")
    elif args.organisations:
        sample_path = Path(args.organisations)
    else:
        raise SystemExit("--organisations or --universe is required")

    rows = read_input_rows(sample_path)
    baseline = run_batch(rows, run_id="experiment-baseline", bulk_path=args.bulk, workers=args.workers)
    write_json(out / "baseline-report.json", baseline["report"])
    profiles = {profile["organisation_number"]: profile for profile in baseline["profiles"]}
    anchored = [profile for profile in profiles.values() if any((profile.get("evidence", {}).get(key) or {}).get("status") == "available" for key in ("registry_live", "registry"))]
    population = [profile["organisation_number"] for profile in profiles.values()]
    base_sets = area_sets(baseline["envelopes"])
    results: dict = {
        "sample": str(sample_path),
        "companies": len(population),
        "identity_anchored": len(anchored),
        "baseline": {"coverage": coverage_view(base_sets, population), "requests": baseline["report"]["operations"]["requests"], "runtime_ms": baseline["report"]["runtime_ms"], "available_claims": baseline["report"]["claims"]["available_total"]},
        "experiments": {},
    }
    if not anchored:
        results["status"] = "UNMEASURED: no company identity could be anchored (registry unreachable?)"

    # E1 Brreg activity
    activity_orgs: set[str] = set()
    if "activity" not in skip:
        rows_e1 = pmap(lambda profile: brreg_activity.run_company(profile), anchored, args.workers)
        summary = summarize(rows_e1, covered_key="covered", count_key="dated_events")
        summary.update({
            "companies_informative": sum(1 for row in rows_e1 if row["covered_informative"]),
            "companies_recent_365d": sum(1 for row in rows_e1 if row["covered_recent"]),
            "events_with_change_detail": sum(row["events_with_change_detail"] for row in rows_e1),
            "change_types": sorted({kind for row in rows_e1 for kind in row["change_types"]}),
            "earliest_event": min((row["earliest_event"] for row in rows_e1 if row["earliest_event"]), default=None),
        })
        activity_orgs = {row["organisation_number"] for row in rows_e1 if row["covered"]}
        results["experiments"]["brreg_activity"] = {"summary": summary, "measured": measured(summary)}
        write_json(out / "e1-brreg-activity.json", rows_e1)

    # E2 filings / PDF
    if "filings" not in skip:
        rows_e2 = pmap(lambda profile: filings.run_company(profile, fetch_pdf=not args.no_pdf), anchored, min(args.workers, 3))
        n = len(rows_e2) or 1
        summary = summarize(rows_e2, covered_key="covered", count_key="financial_values")
        rate = lambda key: round(sum(1 for row in rows_e2 if row.get(key)) / n, 4)  # noqa: E731
        summary.update({
            "latest_filing_rate": rate("has_latest_filing"),
            "multiple_years_rate": rate("has_multiple_years"),
            "prior_year_structured_rate": rate("prior_year_structured"),
            "revenue_rate": rate("has_revenue"),
            "operating_result_rate": rate("has_operating_result"),
            "balance_sheet_rate": rate("has_balance_sheet"),
            "wage_costs_rate": rate("has_wage_costs"),
            "period_correct_rate": round(sum(1 for row in rows_e2 if row.get("period_correct") is True) / max(1, sum(1 for row in rows_e2 if row.get("has_latest_filing"))), 4),
            "pdf_retrieved_rate": rate("pdf_retrieved"),
            "pdf_text_parsed_rate": rate("pdf_text_parsed"),
            "pdf_image_only_rate": rate("pdf_image_only"),
            "starter_values_total": sum(row.get("starter_financial_values", 0) for row in rows_e2),
        })
        envelopes = {item["organisation_number"]: item for item in baseline["envelopes"]}
        summary["registry_employee_rate"] = round(sum(1 for org in population if any(c["field"] == "registry_employee_count" and c["availability"] == "available" for c in envelopes[org]["claims"])) / (len(population) or 1), 4)
        summary["business_description_rate"] = round(sum(1 for org in population if (envelopes[org].get("category_coverage") or {}).get("description") == "available") / (len(population) or 1), 4)
        results["experiments"]["filings"] = {"summary": summary, "measured": measured(summary)}
        write_json(out / "e2-filings.json", rows_e2)

    # E3 NAV jobs
    job_orgs: set[str] = set()
    nav_homepages: dict[str, list[str]] = {}
    if "nav" not in skip:
        meter = Meter()
        token = nav_jobs.public_token(meter)
        if not token:
            results["experiments"]["nav_jobs"] = {"measured": False, "status": "UNMEASURED: public token unavailable", "requests": meter.requests}
        else:
            scan = nav_jobs.scan_active_ads(meter, token)
            index = nav_jobs.build_name_index(scan["active"])
            rows_e3 = pmap(lambda profile: nav_jobs.run_company(profile, index, token), anchored, args.workers)
            summary = summarize(rows_e3, covered_key="covered", count_key="jobs")
            summary.update({
                "feed_pages": scan["pages"], "feed_entries": scan["entries"], "active_ads": scan["active_ads"], "feed_stop_reason": scan["stop_reason"],
                "shared_scan_requests": meter.requests, "name_candidates": sum(row["name_candidates"] for row in rows_e3),
                "false_employer_name_matches_rejected": sum(row["identity_rejections"] for row in rows_e3),
                "candidates_without_orgnr": sum(row["candidates_without_orgnr"] for row in rows_e3),
                "jobs_via_subunit_orgnr": sum(row["jobs_via_subunit_orgnr"] for row in rows_e3),
                "full_orgnr_index_cost_requests": scan["pages"] + scan["active_ads"],
            })
            summary["measured"] = scan["stop_reason"] in {"end_of_feed", "max_pages"} and scan["pages"] > 0
            job_orgs = {row["organisation_number"] for row in rows_e3 if row["covered"]}
            nav_homepages = {row["organisation_number"]: row["employer_homepages"] for row in rows_e3}
            results["experiments"]["nav_jobs"] = {"summary": summary, "measured": summary["measured"]}
            write_json(out / "e3-nav-jobs.json", rows_e3)

    # E4 non-search website discovery for companies without a registry website
    no_site = [profile for profile in anchored if not str(profile.get("website") or "").strip()]
    discovered_orgs: set[str] = set()
    if "discovery" not in skip:
        def discover(profile):
            meter = Meter()
            raw = meter.get(f"https://data.brreg.no/enhetsregisteret/api/enheter/{profile['organisation_number']}", headers={"Accept": "application/json"})
            raw_entity = raw.json() if raw.status == 200 else None
            row = site_discovery.run_company(profile, raw_entity, nav_homepages.get(profile["organisation_number"], []))
            row["requests"] += meter.requests
            row["registry_contact_fields"] = sorted(site_discovery.registry_contact_fields(raw_entity or {}))
            row["unmeasured"] = raw.status == 0
            return row
        rows_e4 = pmap(discover, no_site, args.workers)
        summary = summarize(rows_e4, covered_key="covered")
        sources = sorted({source for row in rows_e4 for source in row["by_source"]})
        summary["by_source"] = {source: {"candidates": sum(len(row["by_source"].get(source, [])) for row in rows_e4), "verified": sum(1 for row in rows_e4 if source in row["verified_sources"]), "ambiguous": sum(row["by_source"].get(source, []).count("ambiguous") for row in rows_e4)} for source in sources}
        summary["registry_contact_fields_seen"] = sorted({field for row in rows_e4 for field in row["registry_contact_fields"]})
        summary["population_without_registry_website"] = len(no_site)
        discovered_orgs = {row["organisation_number"] for row in rows_e4 if row["covered"]}
        results["experiments"]["site_discovery"] = {"summary": summary, "measured": measured(summary)}
        write_json(out / "e4-site-discovery.json", rows_e4)

    # E5 optional search
    if args.search and "search" not in skip:
        provider = search.default_provider()
        if provider.name == "none":
            results["experiments"]["search"] = {"measured": False, "status": "SKIPPED: no BRAVE_SEARCH_API_KEY"}
        else:
            with_site = [profile for profile in anchored if str(profile.get("website") or "").strip()]
            per_strategy = {}
            for strategy in [item for item in args.search_strategies.split(",") if item]:
                target = [profile for profile in no_site if profile["organisation_number"] not in discovered_orgs]
                gain_rows = [search.run_company(profile, provider, strategy) for profile in target]
                label_rows = [search.run_company(profile, provider, strategy, known_domain=_registered_domain(normalize_homepage(profile["website"]) or "")) for profile in with_site]
                gain = sum(1 for row in gain_rows if row["covered"])
                cost = sum(row["search_cost_usd"] for row in gain_rows)
                queries = sum(row["search_requests"] for row in gain_rows)
                labelled = [row["labelled_outcome"] for row in label_rows]
                per_strategy[strategy] = {
                    "target_companies": len(target), "verified_new": gain, "ambiguous": sum(1 for row in gain_rows if row["outcome"] == "ambiguous"),
                    "no_result": sum(1 for row in gain_rows if row["outcome"] == "no_result"), "search_requests": queries, "cost_usd": round(cost, 4),
                    "requests_per_company": round(sum(row["requests"] for row in gain_rows) / (len(target) or 1), 3),
                    "latency_ms_per_company": round(sum(row["runtime_ms"] for row in gain_rows) / (len(target) or 1), 1),
                    "coverage_gain_per_search_request": round(gain / queries, 4) if queries else None,
                    "coverage_gain_per_usd": round(gain / cost, 2) if cost else None,
                    "labelled": {"companies": len(label_rows), **{key: labelled.count(key) for key in sorted(set(labelled))}},
                }
                write_json(out / f"e5-search-{strategy}.json", gain_rows + label_rows)
            results["experiments"]["search"] = {"per_strategy": per_strategy, "measured": True, "usd_per_1000_requests": BRAVE_USD_PER_1000}

    combined = {area: set(members) for area, members in base_sets.items()}
    combined["hiring_activity"] |= activity_orgs | job_orgs
    combined["websites"] |= discovered_orgs
    if "filings" in results["experiments"]:
        combined["filings"] |= {row["organisation_number"] for row in json.loads((out / "e2-filings.json").read_text()) if row.get("covered")}
    results["combined_without_search"] = coverage_view(combined, population)
    n = len(population) or 1
    is_measured = lambda name: bool(results["experiments"].get(name, {}).get("measured"))  # noqa: E731
    gain = lambda name, value: round(value / n, 4) if is_measured(name) else "UNMEASURED"  # noqa: E731
    results["incremental_area_coverage"] = {
        "hiring_activity_from_brreg_activity": gain("brreg_activity", len(activity_orgs - base_sets["hiring_activity"])),
        "hiring_activity_from_nav_jobs": gain("nav_jobs", len(job_orgs - base_sets["hiring_activity"] - activity_orgs)),
        "websites_from_non_search_discovery": gain("site_discovery", len(discovered_orgs - base_sets["websites"])),
    }
    results["combined_without_search"]["unmeasured_sources"] = sorted(name for name in ("brreg_activity", "filings", "nav_jobs", "site_discovery") if not is_measured(name))
    write_json(out / "results.json", results)
    print(json.dumps({key: value for key, value in results.items() if key != "experiments"}, indent=2))
    for name, body in results["experiments"].items():
        print(name, "measured" if body.get("measured") else body.get("status", "UNMEASURED"))


if __name__ == "__main__":
    main()
