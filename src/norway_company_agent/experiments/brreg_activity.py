"""Experiment 1: dated public activity from the Brreg update feeds, keyed by organisation number.

Endpoints (Enhetsregisteret open API, NLOD 2.0):
  /enhetsregisteret/api/oppdateringer/enheter?organisasjonsnummer=..&dato=..&includeChanges=true
  /enhetsregisteret/api/oppdateringer/underenheter?organisasjonsnummer=<subunits>&..
Response: _embedded.oppdaterteEnheter[] {oppdateringsid, dato, organisasjonsnummer, endringstype,
endringer?}; endringstype in Ukjent/Ny/Endring/Sletting/Fjernet. `includeChanges` (added 2025-11-13)
adds the field-level change list.

Identity: every returned row must carry exactly the requested organisation number (or one of the
company's registered subunits); anything else is rejected and counted, never published.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from .common import ByteFetcher, Meter, Timer, evidence_complete
from ..http import fetch_bytes

BASE = "https://data.brreg.no/enhetsregisteret/api/oppdateringer"
HISTORY_START = "1990-01-01T00:00:00.000Z"
KNOWN_TYPES = {"Ny", "Endring", "Sletting", "Fjernet"}


def update_url(kind: str, orgs: list[str], *, page: int = 0, size: int = 100, include_changes: bool = True) -> str:
    query = {"organisasjonsnummer": ",".join(orgs), "dato": HISTORY_START, "size": str(size), "page": str(page)}
    if include_changes:
        query["includeChanges"] = "true"
    return f"{BASE}/{kind}?" + urllib.parse.urlencode(query)


def changed_paths(changes: Any) -> list[str]:
    """Field paths from the change list; tolerant of JSON-Patch lists or plain dicts."""
    paths: list[str] = []
    if isinstance(changes, list):
        for item in changes:
            if isinstance(item, dict):
                path = item.get("path") or item.get("felt") or item.get("field")
                if path:
                    paths.append(str(path))
    elif isinstance(changes, dict):
        paths.extend(str(key) for key in changes)
    return sorted(set(paths))


def parse_updates(body: Any, kind: str) -> tuple[list[dict[str, Any]], int | None]:
    key = "oppdaterteEnheter" if kind == "enheter" else "oppdaterteUnderenheter"
    rows = ((body or {}).get("_embedded") or {}).get(key) or [] if isinstance(body, dict) else []
    total = ((body or {}).get("page") or {}).get("totalElements") if isinstance(body, dict) else None
    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        events.append({
            "update_id": row.get("oppdateringsid"),
            "date": row.get("dato"),
            "organisation_number": str(row.get("organisasjonsnummer") or ""),
            "change_type": row.get("endringstype"),
            "changed_fields": changed_paths(row.get("endringer")),
            "has_change_detail": "endringer" in row,
        })
    return events, total


def run_company(profile: dict[str, Any], fetcher: ByteFetcher = fetch_bytes, *, include_subunits: bool = True, max_pages: int = 5) -> dict[str, Any]:
    org = profile["organisation_number"]
    subunits = [str(item.get("organisation_number")) for item in ((profile.get("evidence", {}).get("locations") or {}).get("value") or {}).get("locations", []) if item.get("organisation_number")]
    meter = Meter(fetcher)
    events: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    rejected = 0
    failure = False
    with Timer() as timer:
        plans = [("enheter", [org])] + ([("underenheter", subunits[:50])] if include_subunits and subunits else [])
        for kind, orgs in plans:
            allowed = set(orgs)
            for page in range(max_pages):
                url = update_url(kind, orgs, page=page)
                response = meter.get(url, headers={"Accept": "application/json"})
                if response.status != 200:
                    failure = failure or response.status == 0 or response.status >= 500
                    break
                try:
                    parsed, total = parse_updates(response.json(), kind)
                except ValueError:
                    failure = True
                    break
                for event in parsed:
                    if event["organisation_number"] not in allowed:
                        rejected += 1
                        continue
                    event["scope"] = "entity" if kind == "enheter" else "subunit"
                    events.append(event)
                    evidence.append({
                        "source_url": url,
                        "content_sha256": response.content_sha256,
                        "retrieved_at": response.retrieved_at,
                        "claim_span": f"oppdateringsid={event['update_id']} dato={event['date']} endringstype={event['change_type']}",
                    })
                if total is None or (page + 1) * 100 >= total or not parsed:
                    break
    dated = [event for event in events if event.get("date")]
    informative = [event for event in dated if event["change_type"] in KNOWN_TYPES or event["changed_fields"]]
    last_365 = [event for event in dated if str(event["date"]) >= _days_ago(365)]
    return {
        "organisation_number": org,
        "requests": meter.requests,
        "runtime_ms": timer.ms,
        "statuses": dict(meter.statuses),
        "transport_failure": failure and not events,
        "unmeasured": failure and not events,
        "events": len(events),
        "dated_events": len(dated),
        "informative_events": len(informative),
        "events_last_365d": len(last_365),
        "events_with_change_detail": sum(1 for event in events if event["has_change_detail"]),
        "covered": bool(dated),
        "covered_informative": bool(informative),
        "covered_recent": bool(last_365),
        "earliest_event": min((str(event["date"]) for event in dated), default=None),
        "latest_event": max((str(event["date"]) for event in dated), default=None),
        "change_types": sorted({str(event["change_type"]) for event in events}),
        "identity_rejections": rejected,
        "published_identity_mismatches": 0,
        "evidence_items": len(evidence),
        "evidence_complete": sum(evidence_complete(item) for item in evidence),
        "sample_events": events[:5],
    }


def _days_ago(days: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
