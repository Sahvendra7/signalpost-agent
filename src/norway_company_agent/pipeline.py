"""Batch orchestration: N input rows -> N terminal contract envelopes, with per-company isolation.

Retrieval is injected (`fetcher`, `website_fetcher`) so the whole pipeline runs offline in tests.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .batch import evidence_terminal_state
from .claims import AREAS, area_coverage, category_coverage, claims_from_profile
from .contract import ClaimSet, build_envelope, snapshot_relative_path, validate_batch
from .evidence import evidence, utc_now
from .http import FetchResult, fetch_bytes, fetch_json
from .identity import apply_website_identity_gate
from .official import accounting_obligation_assessment, fetch_official_modules
from .operations import latency_summary
from .refresh import diff_profile
from .site_research import SiteSession, research_company_site
from .sampling import iter_bulk
from .website import fetch_website

DEFAULT_MODULES = ("registry", "registry_live", "financials", "roles", "group", "locations", "website", "site_research")
V1_MODULES = DEFAULT_MODULES[:-1]
NON_FETCH_MODULES = {"registry", "accounting_obligation", "website", "site_research"}
BULK_URL = "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv"
ORG_WEIGHTS = (3, 2, 7, 6, 5, 4, 3, 2)

Fetcher = Callable[[str], FetchResult]
WebsiteFetcher = Callable[[str | None], tuple[dict[str, Any], dict[str, Any]]]


@dataclass
class InputRow:
    position: int
    raw: Any
    organisation_number: str | None
    errors: list[dict[str, Any]] = field(default_factory=list)
    annotations: dict[str, Any] = field(default_factory=dict)


def mod11_valid(org: str) -> bool:
    if len(org) != 9 or not org.isdigit():
        return False
    remainder = sum(int(digit) * weight for digit, weight in zip(org[:8], ORG_WEIGHTS)) % 11
    check = 0 if remainder == 0 else 11 - remainder
    return check != 10 and check == int(org[8])


def read_input_rows(path: str | Path) -> list[InputRow]:
    """Tolerant reader: every non-blank input line becomes exactly one row, valid or not."""
    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8-sig") as handle:
        text = handle.read()
    stem_suffix = Path(source.stem).suffix if source.suffix == ".gz" else source.suffix
    values: list[Any] = []
    if stem_suffix == ".json":
        body = json.loads(text)
        values = body if isinstance(body, list) else body.get("organisation_numbers", [])
    else:
        for line in text.splitlines():
            if not line.strip():
                continue
            if stem_suffix == ".jsonl" or line.lstrip().startswith(("{", '"')):
                try:
                    values.append(json.loads(line))
                except json.JSONDecodeError:
                    values.append(line.strip())
            else:
                values.append(line.strip())
    rows = []
    first_seen: dict[str, int] = {}
    for position, value in enumerate(values):
        org_value = value.get("organisation_number", value.get("organisasjonsnummer")) if isinstance(value, dict) else value
        digits = "".join(character for character in str(org_value or "") if character.isdigit())
        row = InputRow(position=position, raw=org_value, organisation_number=digits if len(digits) == 9 else None)
        if isinstance(value, dict):
            row.annotations = {key: value[key] for key in ("evaluation_split", "sample_slice") if value.get(key) is not None}
        if row.organisation_number is None:
            row.errors.append({"code": "invalid_organisation_number", "stage": "input", "message": f"Input is not a 9-digit organisation number: {str(org_value)[:40]!r}"})
        else:
            if not mod11_valid(row.organisation_number):
                row.errors.append({"code": "checksum_mismatch", "stage": "input", "message": "Organisation number fails the mod-11 check; researched anyway"})
            if row.organisation_number in first_seen:
                row.errors.append({"code": "duplicate_input", "stage": "input", "message": f"Same organisation number as input row {first_seen[row.organisation_number]}; researched once"})
            else:
                first_seen[row.organisation_number] = position
        rows.append(row)
    return rows


def load_bulk_profiles(path: str | Path | None, wanted: set[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Profiles for `wanted` orgs found in the bulk snapshot. Missing orgs are not an error here."""
    if not path:
        return {}, {"bulk": None}
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    snapshot_sha256 = digest.hexdigest()
    retrieved_at = utc_now()
    found: dict[str, dict[str, Any]] = {}
    scanned = 0
    for profile in iter_bulk(source):
        scanned += 1
        org = profile["organisation_number"]
        if org not in wanted:
            continue
        raw = profile.pop("raw", {})
        profile["evidence"] = {
            "registry": evidence("registry", "available", "official_registry_bulk", BULK_URL, value=raw, retrieved_at=retrieved_at, content_sha256=snapshot_sha256, source_row_key=org),
        }
        found[org] = profile
        if len(found) == len(wanted):
            break
    return found, {"registry_snapshot_sha256": snapshot_sha256, "registry_rows_scanned": scanned, "requested": len(wanted), "found_in_bulk": len(found)}


class SnapshotStore:
    """Content-addressed store of the exact bytes behind every evidence hash."""

    def __init__(self, root: Path | None):
        self.root = root

    def wrap(self, fetcher: Fetcher) -> Fetcher:
        if self.root is None:
            return fetcher

        def capturing(url: str) -> FetchResult:
            result = fetcher(url)
            if result.raw is not None and result.content_sha256:
                path = self.root / snapshot_relative_path(result.content_sha256)
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
                    temporary.write_bytes(result.raw)
                    temporary.replace(path)
            return result

        capturing.live = getattr(fetcher, "live", fetcher is fetch_json)  # type: ignore[attr-defined]
        return capturing

    def wrap_bytes(self, fetcher: Callable[..., Any]) -> Callable[..., Any]:
        """Same content-addressed capture for raw site fetches (ByteFetch)."""
        if self.root is None:
            return fetcher

        def capturing(url: str, **kwargs: Any) -> Any:
            result = fetcher(url, **kwargs)
            if result.raw is not None and result.content_sha256:
                path = self.root / snapshot_relative_path(result.content_sha256)
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
                    temporary.write_bytes(result.raw)
                    temporary.replace(path)
            return result

        return capturing


def _apply_live_identity(profile: dict[str, Any]) -> dict[str, Any] | None:
    """Fill top-level identity from the live registry. A record for another org number is discarded."""
    live = profile.get("evidence", {}).get("registry_live") or {}
    if live.get("status") != "available":
        return None
    value = live.get("value") or {}
    if str(value.get("organisation_number") or "") != profile["organisation_number"]:
        profile["evidence"]["registry_live"] = evidence("registry_live", "source_error", "official_registry_live", live.get("source_url") or BULK_URL, note="Live registry response did not carry the requested organisation number", retrieved_at=live.get("retrieved_at"))
        return {"code": "identity_mismatch", "stage": "identity", "message": "Live registry response was for a different or missing organisation number; discarded"}
    for key in ("name", "legal_form", "employees", "website", "latest_submitted_accounts", "bankrupt", "liquidating"):
        if value.get(key) is not None:
            profile[key] = value[key]
    return None


def research_company(
    org: str,
    base_profile: dict[str, Any] | None,
    modules: list[str],
    *,
    fetcher: Fetcher,
    website_fetcher: WebsiteFetcher,
    site_session: SiteSession | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Research one company. Never raises: failures become explicit module states and errors."""
    started = time.monotonic()
    errors: list[dict[str, Any]] = []
    profile = base_profile or {"organisation_number": org, "evidence": {}}
    profile.setdefault("evidence", {})
    if "registry" in modules and "registry" not in profile["evidence"]:
        profile["evidence"]["registry"] = evidence("registry", "not_found", "official_registry_bulk", BULK_URL, note="Organisation number absent from the supplied bulk snapshot (or no snapshot supplied)")
    metrics: list[FetchResult] = []
    website_metrics = {"requests": 0, "bytes": 0, "latencies_ms": []}
    fetch_modules = set(modules) - NON_FETCH_MODULES
    site_requests = 0
    stage = "official"
    # Identity first, then every other source in isolation: one failing source is not a failed company.
    for module in sorted(fetch_modules, key=lambda name: (name != "registry_live", name)):
        try:
            records, module_metrics = fetch_official_modules(org, {module}, fetcher=fetcher)
            profile["evidence"].update(records)
            metrics.extend(module_metrics)
        except Exception as exc:
            errors.append({"code": "pipeline_exception", "stage": module, "message": f"{type(exc).__name__}: {str(exc)[:200]}"})
            profile["evidence"][module] = evidence(module, "source_error", "pipeline", "https://data.brreg.no/", note=f"Source handling failed: {type(exc).__name__}")
    try:
        stage = "identity"
        mismatch = _apply_live_identity(profile)
        if mismatch:
            errors.append(mismatch)
        if "accounting_obligation" in modules:
            profile["evidence"]["accounting_obligation"] = accounting_obligation_assessment(profile)
        if "website" in modules:
            stage = "website"
            website_record, website_metrics = website_fetcher(profile.get("website"))
            profile["evidence"]["website"] = apply_website_identity_gate(profile, website_record)["website"]
    except Exception as exc:  # isolation boundary: one bad company/source never ends the batch
        errors.append({"code": "pipeline_exception", "stage": stage, "message": f"{type(exc).__name__}: {str(exc)[:200]}", "trace_tail": traceback.format_exc(limit=2)[-400:]})
    if "site_research" in modules and site_session is not None and identity_anchored(profile):
        try:
            site_record, site_requests = _site_research(profile, site_session)
            profile["evidence"]["site_research"] = site_record
        except Exception as exc:  # own boundary: website work never costs the official facts
            errors.append({"code": "pipeline_exception", "stage": "site_research", "message": f"{type(exc).__name__}: {str(exc)[:200]}"})
    for module in modules:
        if module not in profile["evidence"]:
            profile["evidence"][module] = evidence(module, "source_error", "pipeline", "https://data.brreg.no/", note=f"Not completed: {errors[-1]['code'] if errors else 'unknown'}")
    operations = {
        "requests": sum(item.attempts for item in metrics) + int(website_metrics.get("requests", 0)) + site_requests,
        "bytes": sum(item.bytes_received for item in metrics) + int(website_metrics.get("bytes", 0)),
        "latencies_ms": [item.elapsed_ms for item in metrics] + list(website_metrics.get("latencies_ms", [])),
        "runtime_ms": int((time.monotonic() - started) * 1000),
        "third_party_cost_usd": 0,
    }
    profile["run_metrics"] = {key: value for key, value in operations.items() if key != "latencies_ms"}
    return profile, operations, errors


def _site_research(profile: dict[str, Any], session: SiteSession) -> tuple[dict[str, Any], int]:
    website = profile["evidence"].get("website") or {}
    value = website.get("value") or {}
    registry_url = value.get("final_url") if website.get("status") == "available" and (value.get("identity_assessment") or {}).get("publishable") else None
    result = research_company_site(profile, session, registry_verified_url=registry_url)
    body = {key: getattr(result, key) for key in result.__dataclass_fields__}
    if result.status == "verified":
        first = result.pages[0] if result.pages else {}
        record = evidence("site_research", "available", "company_site", result.site_url, value=body, content_sha256=first.get("content_sha256"), retrieved_at=first.get("retrieved_at"))
    elif result.status == "budget_exhausted":
        record = evidence("site_research", "source_error", "company_site", "https://data.brreg.no/enhetsregisteret/api/enheter", value=body, note="budget_exhausted before a website could be verified")
    else:
        tried = ", ".join(f"{item['source']}:{item.get('outcome')}" for item in result.candidates) or "no official pointer or resolvable name domain"
        record = evidence("site_research", "not_found", "company_site", "https://data.brreg.no/enhetsregisteret/api/enheter", value=body, note=f"No verified company website ({tried})")
    return record, result.requests


def identity_anchored(profile: dict[str, Any]) -> bool:
    records = profile.get("evidence", {})
    return any((records.get(key) or {}).get("status") == "available" for key in ("registry_live", "registry"))


def run_batch(
    rows: list[InputRow],
    *,
    run_id: str,
    bulk_path: str | Path | None = None,
    modules: list[str] | None = None,
    workers: int = 8,
    fetcher: Fetcher = fetch_json,
    website_fetcher: WebsiteFetcher = fetch_website,
    previous_profiles: dict[str, dict[str, Any]] | None = None,
    snapshot_root: Path | None = None,
    expected_count: int | None = None,
    reuse_profiles: dict[str, dict[str, Any]] | None = None,
    site_fetcher: Callable[..., Any] = fetch_bytes,
    resolver: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    modules = list(modules or DEFAULT_MODULES)
    batch_started_at = utc_now()
    batch_started = time.monotonic()
    store = SnapshotStore(snapshot_root)
    wrapped = store.wrap(fetcher)
    session = SiteSession(fetcher=store.wrap_bytes(site_fetcher), resolver=resolver) if "site_research" in modules else None
    unique_orgs = list(dict.fromkeys(row.organisation_number for row in rows if row.organisation_number))
    bulk_profiles, registry_metadata = load_bulk_profiles(bulk_path, set(unique_orgs)) if "registry" in modules else ({}, {"bulk": "not requested"})

    results: dict[str, dict[str, Any]] = {}

    def work(org: str) -> tuple[str, dict[str, Any]]:
        company_started_at = utc_now()
        reused = (reuse_profiles or {}).get(org)
        if reused is not None:
            operations = {"requests": 0, "bytes": 0, "latencies_ms": [], "runtime_ms": 0, "third_party_cost_usd": 0, "resumed": True}
            return org, {"profile": reused, "operations": operations, "errors": [], "started_at": company_started_at, "completed_at": utc_now()}
        try:
            profile, operations, errors = research_company(org, bulk_profiles.get(org), modules, fetcher=wrapped, website_fetcher=website_fetcher, site_session=session)
        except Exception as exc:  # second boundary: research_company should not raise, but never trust it
            profile = {"organisation_number": org, "evidence": {}}
            operations = {"requests": 0, "bytes": 0, "latencies_ms": [], "runtime_ms": 0, "third_party_cost_usd": 0}
            errors = [{"code": "pipeline_exception", "stage": "research", "message": f"{type(exc).__name__}: {str(exc)[:200]}"}]
        return org, {"profile": profile, "operations": operations, "errors": errors, "started_at": company_started_at, "completed_at": utc_now()}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for org, result in pool.map(work, unique_orgs):
            results[org] = result

    envelopes = []
    profiles = []
    for row in rows:
        envelopes.append(_envelope_for_row(row, results.get(row.organisation_number or ""), run_id=run_id, modules=modules, previous_profiles=previous_profiles, snapshot_root=snapshot_root))
    for org in unique_orgs:
        profiles.append(results[org]["profile"])

    validation = validate_batch(envelopes, [_input_key(row) for row in rows], snapshot_root=snapshot_root)
    if expected_count is not None:
        validation["checks"]["expected_count_matches_input"] = expected_count == len(rows)
        validation["passed"] = validation["passed"] and expected_count == len(rows)
    report = batch_report(envelopes, results, run_id=run_id, started_at=batch_started_at, runtime_ms=int((time.monotonic() - batch_started) * 1000), modules=modules, registry_metadata=registry_metadata, validation=validation, input_rows=len(rows))
    return {"envelopes": envelopes, "profiles": profiles, "report": report}


def _input_key(row: InputRow) -> str | None:
    return row.organisation_number or (str(row.raw) if row.raw is not None else None)


def _envelope_for_row(
    row: InputRow,
    result: dict[str, Any] | None,
    *,
    run_id: str,
    modules: list[str],
    previous_profiles: dict[str, dict[str, Any]] | None,
    snapshot_root: Path | None,
) -> dict[str, Any]:
    now = utc_now()
    errors = list(row.errors)
    if result is None:
        return build_envelope(
            row.organisation_number,
            run={"run_id": run_id, "started_at": now, "completed_at": now, "terminal_status": "failed"},
            claims=[],
            evidence=[],
            errors=errors or [{"code": "not_researched", "stage": "input", "message": "Row could not be researched"}],
            extra={"input_organisation_number": _input_key(row), "input_position": row.position, "category_coverage": {}},
        )
    profile = result["profile"]
    errors.extend(result["errors"])
    try:
        claim_set = claims_from_profile(profile, snapshot_root=snapshot_root)
    except Exception as exc:  # extraction must never cost the row its terminal envelope
        claim_set = ClaimSet(snapshot_root=snapshot_root)
        errors.append({"code": "extraction_exception", "stage": "claims", "message": f"{type(exc).__name__}: {str(exc)[:200]}"})
    changes: list[dict[str, Any]] = []
    previous = (previous_profiles or {}).get(row.organisation_number or "")
    if previous is not None:
        try:
            changes = diff_profile(previous, profile)
        except Exception as exc:
            errors.append({"code": "refresh_diff_failed", "stage": "refresh", "message": f"{type(exc).__name__}: {str(exc)[:200]}"})
    anchored = identity_anchored(profile)
    if not anchored:
        errors.append({"code": "identity_unresolved", "stage": "identity", "message": "Neither the bulk snapshot nor the live registry returned this organisation number"})
    module_states = {
        module: {
            "state": evidence_terminal_state(profile["evidence"].get(module)),
            "note": (profile["evidence"].get(module) or {}).get("note"),
        }
        for module in modules
    }
    operations = {key: value for key, value in result["operations"].items() if key != "latencies_ms"}
    return build_envelope(
        row.organisation_number,
        run={"run_id": run_id, "started_at": result["started_at"], "completed_at": result["completed_at"], "terminal_status": "completed" if anchored else "failed"},
        claims=claim_set.claims,
        evidence=claim_set.evidence,
        changes=changes,
        errors=errors,
        operations=operations,
        extra={
            "input_organisation_number": _input_key(row),
            "input_position": row.position,
            "category_coverage": category_coverage(claim_set.claims),
            "area_coverage": area_coverage(claim_set.claims),
            "modules": module_states,
        },
    )


def batch_report(
    envelopes: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
    *,
    run_id: str,
    started_at: str,
    runtime_ms: int,
    modules: list[str],
    registry_metadata: dict[str, Any],
    validation: dict[str, Any],
    input_rows: int,
) -> dict[str, Any]:
    from collections import Counter

    statuses = Counter(item["run"]["terminal_status"] for item in envelopes)
    coverage: dict[str, Counter] = {}
    for item in envelopes:
        for category, state in (item.get("category_coverage") or {}).items():
            coverage.setdefault(category, Counter())[state] += 1
    module_states: dict[str, Counter] = {}
    for item in envelopes:
        for module, state in (item.get("modules") or {}).items():
            module_states.setdefault(module, Counter())[state["state"]] += 1
    error_codes = Counter(error["code"] for item in envelopes for error in item.get("errors", []))
    available_claims = [sum(claim["availability"] == "available" for claim in item["claims"]) for item in envelopes]
    latencies = [value for result in results.values() for value in result["operations"].get("latencies_ms", [])]
    company_runtimes = [result["operations"].get("runtime_ms", 0) for result in results.values()]
    count = len(envelopes) or 1
    return {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": utc_now(),
        "runtime_ms": runtime_ms,
        "input_rows": input_rows,
        "emitted_envelopes": len(envelopes),
        "unique_companies_researched": len(results),
        "terminal_status_counts": dict(statuses),
        "modules": modules,
        "registry": registry_metadata,
        "category_coverage": {category: dict(counter) for category, counter in sorted(coverage.items())},
        "category_available_rate": {category: round(counter.get("available", 0) / count, 4) for category, counter in sorted(coverage.items())},
        "area_coverage": {area: sum(1 for item in envelopes if (item.get("area_coverage") or {}).get(area)) for area in AREAS},
        # Builderr's five areas: filings, leadership, locations, websites, hiring & public activity.
        "companies_all_five_areas": sum(1 for item in envelopes if item.get("area_coverage") and all(item["area_coverage"].get(area) for area in ("filings", "leadership", "locations", "websites")) and (item["area_coverage"].get("public_footprint") or item["area_coverage"].get("hiring"))),
        "module_states": {module: dict(counter) for module, counter in sorted(module_states.items())},
        "error_codes": dict(error_codes),
        "claims": {
            "available_total": sum(available_claims),
            "available_per_company_mean": round(sum(available_claims) / count, 2),
            "evidence_total": sum(len(item["evidence"]) for item in envelopes),
            "changes_total": sum(len(item["changes"]) for item in envelopes),
        },
        "operations": {
            "requests": sum(result["operations"].get("requests", 0) for result in results.values()),
            "bytes": sum(result["operations"].get("bytes", 0) for result in results.values()),
            "request_latency": latency_summary(latencies),
            "company_runtime": latency_summary(company_runtimes),
            "third_party_cost_usd": 0,
            "llm_calls": 0,
        },
        "validation": validation,
    }
