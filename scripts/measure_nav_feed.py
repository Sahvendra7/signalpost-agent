#!/usr/bin/env python3
"""Measurement-only companion to the NAV experiment (no research behaviour changes).

Measures what the frozen harness does not record:
  - token acquisition latency, feed startup latency (first page), total scan time, bytes, pages
  - feed entries, unique ads, active ads, peak Python memory of the scan (tracemalloc)
  - employer.orgnr presence on a fixed-seed random sample of active-ad details
  - NAV employer-homepage website candidates for companies with verified jobs, run through the
    strict discovered-site gate (never published)
The token is NAV's public experiment token (NAV_TOKEN_MODE=public_experiment), fetched at runtime and
kept in memory only. It is never written to disk or printed.

  uv run python scripts/measure_nav_feed.py --e3 out/experiments-nav/e3-nav-jobs.json \
      --profiles out/experiments-nav/baseline-profiles.jsonl --out out/experiments-nav/nav-feed-measure.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.experiments import nav_jobs  # noqa: E402
from norway_company_agent.experiments.common import Meter  # noqa: E402
from norway_company_agent.http import fetch_bytes  # noqa: E402
from norway_company_agent.identity import assess_discovered_website_identity  # noqa: E402
from norway_company_agent.website import _registered_domain, fetch_website, normalize_homepage  # noqa: E402


class TimedMeter(Meter):
    """Meter that also records per-request bytes and elapsed time."""

    def __init__(self):
        super().__init__(fetch_bytes)
        self.log: list[dict] = []

    def get(self, url, **kwargs):
        started = time.monotonic()
        result = super().get(url, **kwargs)
        self.log.append({"url": url.split("?")[0][-60:], "status": result.status, "bytes": len(result.raw or b""), "elapsed_ms": int((time.monotonic() - started) * 1000)})
        return result


def full_orgnr_index(active: dict, token: str, profiles_path: str, workers: int) -> dict:
    """Exact org-number matching over every active ad: the strategy with no name prefilter."""
    profiles = [json.loads(line) for line in Path(profiles_path).read_text().splitlines() if line.strip()]
    owner: dict[str, tuple[str, str]] = {}
    for profile in profiles:
        org = profile["organisation_number"]
        owner[org] = (org, "entity")
        for unit in ((profile.get("evidence", {}).get("locations") or {}).get("value") or {}).get("locations", []):
            if unit.get("organisation_number"):
                owner.setdefault(str(unit["organisation_number"]), (org, "subunit"))
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def detail(item):
        result = fetch_bytes(nav_jobs.FEED_HOST + item["url"], headers=headers, timeout=30)
        return item, result

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(detail, active.values()))
    seconds = time.monotonic() - started
    with_orgnr = statuses_ok = inactive = expired = 0
    attempts = 0
    total_bytes = 0
    matches = []
    for item, result in results:
        attempts += result.attempts
        total_bytes += len(result.raw or b"")
        if result.status != 200:
            continue
        statuses_ok += 1
        body = result.json() or {}
        content = body.get("ad_content") or {}
        employer = content.get("employer") or {}
        orgnr = "".join(ch for ch in str(employer.get("orgnr") or "") if ch.isdigit())
        if body.get("status") != "ACTIVE":
            inactive += 1
            continue
        if str(content.get("expires") or "") and str(content.get("expires")) < now:
            expired += 1
            continue
        if not orgnr:
            continue
        with_orgnr += 1
        if orgnr in owner:
            company, scope = owner[orgnr]
            matches.append({
                "organisation_number": company, "employer_orgnr": orgnr, "employer_scope": scope, "employer_name": employer.get("name"),
                "header_business_name": item.get("businessName"), "title": content.get("title"), "published": content.get("published"),
                "expires": content.get("expires"), "source_url": result.url, "retrieved_at": result.retrieved_at, "content_sha256": result.content_sha256,
                "employer_homepage": employer.get("homepage"),
            })
    companies = sorted({item["organisation_number"] for item in matches})
    return {
        "active_ads_fetched": len(results), "http_200": statuses_ok, "attempts": attempts, "retries": attempts - len(results),
        "seconds": round(seconds, 2), "workers": workers, "bytes": total_bytes,
        "inactive_on_detail": inactive, "expired_on_detail": expired, "active_with_employer_orgnr": with_orgnr,
        "target_orgnr_set_size": len(owner), "matched_ads": len(matches), "companies_covered": len(companies), "companies": companies,
        "matches_via_entity_orgnr": sum(1 for item in matches if item["employer_scope"] == "entity"),
        "matches_via_subunit_orgnr": sum(1 for item in matches if item["employer_scope"] == "subunit"),
        "matches": matches,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e3", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--detail-sample", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--full-index", action="store_true", help="Fetch every active ad's detail once and match by employer.orgnr only")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    report: dict = {"nav_token_mode": "public_experiment", "token_source": f"{nav_jobs.FEED_HOST}/api/publicToken (unauthenticated, documented by NAV for experiments)"}

    token_meter = TimedMeter()
    started = time.monotonic()
    token = nav_jobs.public_token(token_meter)
    report["token_acquisition_ms"] = int((time.monotonic() - started) * 1000)
    if not token:
        report["status"] = "UNMEASURED: public token unavailable"
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
        return

    scan_meter = TimedMeter()
    tracemalloc.start()
    started = time.monotonic()
    scan = nav_jobs.scan_active_ads(scan_meter, token)
    scan_s = time.monotonic() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    pages = scan_meter.log
    report["scan"] = {
        "pages": scan["pages"], "entries": scan["entries"], "unique_ads": scan["unique_ads"], "active_ads": scan["active_ads"],
        "stop_reason": scan["stop_reason"], "requests": scan_meter.requests,
        "startup_latency_ms": pages[0]["elapsed_ms"] if pages else None,
        "total_scan_s": round(scan_s, 2), "bytes": sum(item["bytes"] for item in pages),
        "page_ms_p50": sorted(item["elapsed_ms"] for item in pages)[len(pages) // 2] if pages else None,
        "page_bytes_max": max((item["bytes"] for item in pages), default=0),
        "python_peak_memory_mb": round(peak / 1_048_576, 1),
        "statuses": dict(scan_meter.statuses),
    }

    # Employer org-number presence on a random sample of active ads (detail fetch per ad).
    sample_ids = random.Random(args.seed).sample(sorted(scan["active"]), min(args.detail_sample, len(scan["active"])))
    detail_meter = TimedMeter()
    with_orgnr = 0
    inactive_on_detail = 0
    started = time.monotonic()
    for uuid in sample_ids:
        item = scan["active"][uuid]
        response = detail_meter.get(nav_jobs.FEED_HOST + item["url"], headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
        if response.status != 200:
            continue
        body = response.json() or {}
        content = body.get("ad_content") or {}
        if body.get("status") != "ACTIVE":
            inactive_on_detail += 1
        if "".join(ch for ch in str((content.get("employer") or {}).get("orgnr") or "") if ch.isdigit()):
            with_orgnr += 1
    detail_s = time.monotonic() - started
    sampled = len(sample_ids)
    report["detail_sample"] = {
        "seed": args.seed, "sampled_active_ads": sampled, "requests": detail_meter.requests,
        "with_employer_orgnr": with_orgnr, "with_employer_orgnr_rate": round(with_orgnr / sampled, 4) if sampled else None,
        "inactive_when_detail_fetched": inactive_on_detail,
        "seconds": round(detail_s, 2), "ms_per_detail": round(detail_s * 1000 / sampled, 1) if sampled else None,
        "bytes": sum(item["bytes"] for item in detail_meter.log),
        "bytes_per_detail": round(sum(item["bytes"] for item in detail_meter.log) / sampled) if sampled else None,
    }

    if args.full_index:
        report["full_orgnr_index"] = full_orgnr_index(scan["active"], token, args.profiles, args.workers)

    # NAV employer homepages as website candidates (strict gate, never published).
    rows = json.loads(Path(args.e3).read_text())
    profiles = {row["organisation_number"]: row for row in (json.loads(line) for line in Path(args.profiles).read_text().splitlines() if line.strip())}
    candidates = []
    for row in rows:
        profile = profiles[row["organisation_number"]]
        registry_domain = _registered_domain(normalize_homepage(profile.get("website")) or "") if profile.get("website") else None
        for homepage in row.get("employer_homepages") or []:
            url = normalize_homepage(homepage)
            domain = _registered_domain(url) if url else None
            if not url or not domain:
                continue
            record, metrics = fetch_website(url)
            gated = assess_discovered_website_identity({**profile, "business_address": ((profile.get("evidence", {}).get("registry_live") or {}).get("value") or {}).get("business_address") or {}}, record)
            candidates.append({
                "organisation_number": row["organisation_number"], "homepage": homepage, "domain": domain,
                "company_has_registry_website": bool(registry_domain), "same_as_registry_domain": domain == registry_domain,
                "gate_status": gated["status"], "gate_reason": gated["reasons"][0], "requests": metrics.get("requests", 0),
                "content_sha256": record.get("content_sha256"),
            })
    report["nav_website_candidates"] = {
        "companies_with_candidate": len({item["organisation_number"] for item in candidates}),
        "companies_with_candidate_and_no_registry_website": len({item["organisation_number"] for item in candidates if not item["company_has_registry_website"]}),
        "companies_verified": len({item["organisation_number"] for item in candidates if item["gate_status"] == "exact"}),
        "companies_verified_new_website": len({item["organisation_number"] for item in candidates if item["gate_status"] == "exact" and not item["company_has_registry_website"]}),
        "candidates_rejected_or_ambiguous": sum(1 for item in candidates if item["gate_status"] in {"ambiguous", "rejected"}),
        "candidates": candidates,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "nav_website_candidates"} | {"nav_website_candidates": {k: v for k, v in report["nav_website_candidates"].items() if k != "candidates"}}, indent=2))


if __name__ == "__main__":
    main()
