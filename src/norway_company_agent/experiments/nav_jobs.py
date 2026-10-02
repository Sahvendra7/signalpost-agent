"""Experiment 3: current job ads from NAV's public job-vacancy feed (pam-stilling-feed).

Facts from NAV's documentation and source (github.com/navikt/pam-stilling-feed):
- Free for anyone who accepts https://arbeidsplassen.nav.no/vilkar-api; all requests need a bearer JWT.
- /api/publicToken (unauthenticated) returns a token "that can be used for experiments" and rotates at
  irregular intervals. Production consumers register with NAV for a private token.
- No server-side filter by employer. Feed headers carry businessName/municipal/status only; the
  employer org number (employer.orgnr) is only in the per-ad detail.
- An ad is never active for more than 6 months; INACTIVE entries must be dropped by consumers.

Matching: header businessName must equal the legal name or a registered subunit name (legal-form
tokens ignored); the detail's employer.orgnr must then be the company or one of its subunits. A name
match whose orgnr differs is a rejected false employer match.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any

from .common import ByteFetcher, Meter, Timer, evidence_complete
from ..http import fetch_bytes
from ..identity import _tokens

FEED_HOST = "https://pam-stilling-feed.nav.no"


def public_token(meter: Meter) -> str | None:
    response = meter.get(FEED_HOST + "/api/publicToken", headers={"Accept": "text/plain"})
    if response.status != 200 or not response.raw:
        return None
    text = response.raw.decode("utf-8", errors="replace").strip()
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("bearer "):
            return line.split(None, 1)[1]
    return text if "." in text and " " not in text else None


def scan_active_ads(meter: Meter, token: str, *, since_days: int = 183, page_size: int = 10000, max_pages: int = 300) -> dict[str, Any]:
    """Latest header per ad uuid since `since_days`; returns active ads and scan statistics."""
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}", "If-Modified-Since": format_datetime(datetime.now(timezone.utc) - timedelta(days=since_days), usegmt=True)}
    url = f"{FEED_HOST}/api/v1/feed?pageSize={page_size}"
    latest: dict[str, dict[str, Any]] = {}
    pages = 0
    entries = 0
    stop_reason = "max_pages"
    while url and pages < max_pages:
        response = meter.get(url, headers=headers, timeout=90)
        pages += 1
        if response.status != 200:
            stop_reason = f"HTTP {response.status}"
            break
        try:
            body = response.json() or {}
        except ValueError:
            stop_reason = "invalid_json"
            break
        items = body.get("items") or []
        for item in items:
            entry = item.get("_feed_entry") or item.get("feed_entry") or {}
            uuid = entry.get("uuid") or item.get("id")
            if uuid:
                latest[uuid] = {"uuid": uuid, "url": item.get("url"), "title": entry.get("title") or item.get("title"), "businessName": entry.get("businessName"), "municipal": entry.get("municipal"), "status": entry.get("status"), "sistEndret": entry.get("sistEndret") or item.get("date_modified")}
        entries += len(items)
        if not body.get("next_url") or not items:
            stop_reason = "end_of_feed"
            break
        url = FEED_HOST + body["next_url"] if body["next_url"].startswith("/") else body["next_url"]
        headers = {key: value for key, value in headers.items() if key != "If-Modified-Since"}
    active = {uuid: item for uuid, item in latest.items() if item.get("status") == "ACTIVE"}
    return {"active": active, "pages": pages, "entries": entries, "unique_ads": len(latest), "active_ads": len(active), "stop_reason": stop_reason}


def name_key(value: Any) -> tuple[str, ...]:
    return tuple(_tokens(value))


def build_name_index(active: dict[str, dict[str, Any]]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    index: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for item in active.values():
        key = name_key(item.get("businessName"))
        if key:
            index.setdefault(key, []).append(item)
    return index


def company_names_and_orgs(profile: dict[str, Any]) -> tuple[set[tuple[str, ...]], set[str], set[str]]:
    org = profile["organisation_number"]
    subunits = ((profile.get("evidence", {}).get("locations") or {}).get("value") or {}).get("locations", [])
    names = {name_key(profile.get("name"))} | {name_key(item.get("name")) for item in subunits}
    return {name for name in names if name}, {org}, {str(item.get("organisation_number")) for item in subunits if item.get("organisation_number")}


def run_company(profile: dict[str, Any], index: dict[tuple[str, ...], list[dict[str, Any]]], token: str, fetcher: ByteFetcher = fetch_bytes, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    names, main_orgs, subunit_orgs = company_names_and_orgs(profile)
    allowed = main_orgs | subunit_orgs
    meter = Meter(fetcher)
    jobs: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    rejected = 0
    expired = 0
    missing_orgnr = 0
    with Timer() as timer:
        candidates = {item["uuid"]: item for name in names for item in index.get(name, [])}
        for item in candidates.values():
            if not item.get("url"):
                continue
            url = item["url"] if item["url"].startswith("http") else FEED_HOST + item["url"]
            response = meter.get(url, headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
            if response.status != 200:
                continue
            try:
                detail = response.json() or {}
            except ValueError:
                continue
            content = detail.get("ad_content") or detail.get("json") or {}
            employer = content.get("employer") or {}
            orgnr = "".join(ch for ch in str(employer.get("orgnr") or "") if ch.isdigit())
            if not orgnr:
                missing_orgnr += 1
                continue
            if orgnr not in allowed:
                rejected += 1
                continue
            expires = str(content.get("expires") or "")
            if detail.get("status") not in (None, "ACTIVE") or (expires and expires < now.strftime("%Y-%m-%dT%H:%M:%S")):
                expired += 1
                continue
            jobs.append({"uuid": item["uuid"], "title": content.get("title"), "published": content.get("published"), "expires": content.get("expires"), "employer_orgnr": orgnr, "employer_scope": "entity" if orgnr in main_orgs else "subunit", "employer_homepage": employer.get("homepage"), "link": content.get("link")})
            evidence.append({"source_url": url, "content_sha256": response.content_sha256, "retrieved_at": response.retrieved_at, "claim_span": f"employer.orgnr={orgnr} title={str(content.get('title'))[:80]}"})
    return {
        "organisation_number": profile["organisation_number"],
        "requests": meter.requests,
        "runtime_ms": timer.ms,
        "name_candidates": len(candidates),
        "jobs": len(jobs),
        "jobs_via_subunit_orgnr": sum(1 for job in jobs if job["employer_scope"] == "subunit"),
        "covered": bool(jobs),
        "identity_rejections": rejected,
        "candidates_without_orgnr": missing_orgnr,
        "expired_or_inactive": expired,
        "published_identity_mismatches": 0,
        "employer_homepages": sorted({job["employer_homepage"] for job in jobs if job.get("employer_homepage")}),
        "evidence_items": len(evidence),
        "evidence_complete": sum(evidence_complete(item) for item in evidence),
        "sample_jobs": jobs[:3],
    }
