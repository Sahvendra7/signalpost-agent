"""Refresh semantics.

`carry_forward` + `claim_changes` implement the product refresh: a source that fails keeps its last
supported value (carried forward with its original evidence), and changes are typed claim-level events.
`diff_profile`/`diff_datasets` are the starter's field-path diff, kept for the replay fixture tool.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from .evidence import utc_now

OUTAGE_STATUSES = {"source_error", "blocked", "not_fetched"}
CARRY_MODULES = ("registry_live", "financials", "roles", "group", "locations", "website", "site_research")
SOURCE_CLASS_MODULE = {
    "official_registry_live": "registry_live",
    "official_registry_bulk": "registry",
    "official_annual_accounts": "financials",
    "official_roles": "roles",
    "official_subunits": "locations",
    "official_group_structure": "group",
    "registry_linked_company_website": "website",
    "company_site": "site_research",
}
NON_PUBLISHABLE_SITE_CLASSES = {"AMBIGUOUS", "THIRD_PARTY", "FAN_COMMUNITY", "DIRECTORY"}
MULTI_VALUE_FIELDS = {"subunit", "social_profile", "site_activity", "news_item", "job_posting", "annual_accounts_copy"}
INFORMATIONAL_FIELDS = {"site_activity", "news_item", "roles_last_changed", "role_count", "subunit_count"}


TRACKED_FIELDS: dict[str, tuple[str, ...]] = {
    "registry.name": ("name",),
    "registry.legal_form": ("legal_form",),
    "registry.employees": ("employees",),
    "registry.municipality": ("municipality",),
    "registry.website": ("website",),
    "registry.latest_submitted_accounts": ("latest_submitted_accounts",),
    "financials.records": ("evidence", "financials", "value", "records"),
    "financial_history.years": ("evidence", "financial_history", "value", "years"),
    "roles.roles": ("evidence", "roles", "value", "roles"),
    "locations.locations": ("evidence", "locations", "value", "locations"),
    "website.title": ("evidence", "website", "value", "title"),
    "website.description": ("evidence", "website", "value", "description"),
    "website.social_links": ("evidence", "website", "value", "social_links"),
}


def _read(value: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _evidence_for(profile: dict[str, Any], field: str) -> dict[str, Any]:
    module = field.split(".", 1)[0]
    records = profile.get("evidence", {})
    if module == "registry":
        live = records.get("registry_live") or {}
        return live if live.get("status") == "available" else records.get("registry") or live
    return records.get(module, {})


def _canonical(value: Any) -> Any:
    """Order-insensitive form so a reordered source list is not reported as a change."""
    if isinstance(value, list):
        return sorted((_canonical(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    return value


def diff_profile(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    old_org = previous.get("organisation_number")
    new_org = current.get("organisation_number")
    if not old_org or old_org != new_org:
        raise ValueError("Refresh comparison requires the same exact organisation number")
    changes = []
    for field, path in TRACKED_FIELDS.items():
        record = _evidence_for(current, field)
        previous_record = _evidence_for(previous, field)
        # An outage, block or unchecked source on either side is not evidence of a business change.
        if record.get("status") != "available" or previous_record.get("status") != "available":
            continue
        old_value = _read(previous, path)
        new_value = _read(current, path)
        if _canonical(old_value) == _canonical(new_value):
            continue
        changes.append({
            "organisation_number": new_org,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "source_url": record.get("source_url"),
            "retrieved_at": record.get("retrieved_at"),
            "effective_at": record.get("effective_at") or record.get("as_of"),
            "source_class": record.get("source_class") or record.get("source_type"),
            "old_content_sha256": previous_record.get("content_sha256"),
            "new_content_sha256": record.get("content_sha256"),
            "status": record.get("status"),
        })
    return changes


def diff_datasets(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old_by_org = {row["organisation_number"]: row for row in previous}
    new_by_org = {row["organisation_number"]: row for row in current}
    if set(old_by_org) != set(new_by_org):
        raise ValueError("Refresh datasets must have identical organisation-number membership")
    return [
        change
        for org in sorted(old_by_org)
        for change in diff_profile(old_by_org[org], new_by_org[org])
    ]


def _registered_domain(url: Any) -> str | None:
    from .website import _registered_domain as registered

    return registered(str(url)) if url else None


def _site_outage(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    """True when this run could not re-check the previously verified site (transport, robots, budget)."""
    if current.get("status") in OUTAGE_STATUSES:
        return True
    previous_domain = _registered_domain((previous.get("value") or {}).get("site_url"))
    for candidate in (current.get("value") or {}).get("candidates") or []:
        if candidate.get("domain") == previous_domain:
            return str(candidate.get("outcome")) not in NON_PUBLISHABLE_SITE_CLASSES
    return True  # the previous site was not re-checked at all (e.g. budget ran out first)


def carry_forward(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, list[str]]:
    """Keep the last supported value of every source that failed in this run. Mutates `current`.

    Returns {"carried": [...], "unverified": [...]}. `unverified`: a website that was reached but no longer
    passes the identity policy; it is not carried, because re-publishing it could attach the wrong company."""
    outcome: dict[str, list[str]] = {"carried": [], "unverified": []}
    if not previous:
        return outcome
    old_records = previous.get("evidence") or {}
    new_records = current.setdefault("evidence", {})
    for module in CARRY_MODULES:
        old = old_records.get(module)
        new = new_records.get(module)
        if not old or old.get("status") != "available":
            continue
        new_status = (new or {}).get("status")
        outage = new is None or new_status in OUTAGE_STATUSES
        if module == "website" and new_status == "available" and not ((new.get("value") or {}).get("identity_assessment") or {}).get("publishable") and ((old.get("value") or {}).get("identity_assessment") or {}).get("publishable"):
            outcome["unverified"].append(module)
            continue
        if module == "site_research" and new_status == "not_found":
            # A REGISTRY_LINKED site was verified through the registry-website identity gate. When that module
            # could not re-check (outage, carried above), discovery alone cannot re-verify it: an outage, not a change.
            registry_gate_down = (old.get("value") or {}).get("identity_class") == "REGISTRY_LINKED" and "website" in outcome["carried"]
            if registry_gate_down or _site_outage(old, new):
                outage = True
            else:
                outcome["unverified"].append(module)
                continue
        if not outage:
            continue
        carried = copy.deepcopy(old)
        if not carried.get("carried_forward"):
            carried["carried_forward"] = True
        carried["carried_at"] = utc_now()
        carried["current_attempt"] = {"status": new_status or "not_fetched", "note": (new or {}).get("note"), "retrieved_at": (new or {}).get("retrieved_at")}
        new_records[module] = carried
        outcome["carried"].append(module)
        if module == "registry_live":
            for key in ("name", "legal_form", "employees", "website", "latest_submitted_accounts", "bankrupt", "liquidating"):
                if (carried.get("value") or {}).get(key) is not None:
                    current[key] = carried["value"][key]
    return outcome


def _identity_value(claim: dict[str, Any]) -> Any:
    """What makes a claim the same fact across runs: a social profile is its canonical profile, so a site that
    re-links the same page with a trailing slash or a tracking parameter is not a change."""
    if claim.get("field") == "social_profile" and claim.get("canonical_url"):
        return claim["canonical_url"]
    return _canonical(claim.get("value"))


def _claim_key(claim: dict[str, Any]) -> str:
    qualifiers = {key: claim.get(key) for key in ("period", "account_type", "currency") if claim.get(key) is not None}
    if claim.get("category") == "leadership" and claim["field"] != "role_count" or claim["field"] in MULTI_VALUE_FIELDS:
        return json.dumps([claim["category"], claim["field"], _identity_value(claim), qualifiers], sort_keys=True, ensure_ascii=False, default=str)
    return json.dumps([claim["category"], claim["field"], qualifiers], sort_keys=True, ensure_ascii=False, default=str)


def _evidence_ref(claim: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    item = evidence.get((claim.get("evidence_ids") or [None])[0]) or {}
    if not item:
        return None
    return {"source_url": item.get("source_url"), "retrieved_at": item.get("retrieved_at"), "content_sha256": item.get("content_sha256"), "evidence_id": item.get("id")}


def _module_of(claim: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> str | None:
    item = evidence.get((claim.get("evidence_ids") or [None])[0]) or {}
    return SOURCE_CLASS_MODULE.get(str(item.get("source_class")))


def claim_changes(
    previous_claims: list[dict[str, Any]],
    previous_evidence: list[dict[str, Any]],
    current_claims: list[dict[str, Any]],
    current_evidence: list[dict[str, Any]],
    *,
    carried: list[str],
    unverified: list[str],
    current_records: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Typed change events between two runs' available claims, plus a summary block.

    added / removed / changed: the source answered in both runs and the fact differs.
    unverified: a previously verified website fact can no longer be confirmed (identity policy).
    unavailable: one event per source that failed in this run; its last supported values are kept.
    unchanged facts are counted, not listed. Re-running on the same source data yields no events."""
    old_evidence = {item["id"]: item for item in previous_evidence}
    new_evidence = {item["id"]: item for item in current_evidence}
    old = {_claim_key(claim): claim for claim in previous_claims if claim.get("availability") == "available"}
    new = {_claim_key(claim): claim for claim in current_claims if claim.get("availability") == "available"}
    events: list[dict[str, Any]] = []
    counts = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0, "unverified": 0, "unavailable": 0}

    def event(change_type: str, claim: dict[str, Any], before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
        counts[change_type] += 1
        body = {
            "change_type": change_type,
            "category": claim["category"],
            "field": claim["field"],
            "old_value": before.get("value") if before else None,
            "new_value": after.get("value") if after else None,
            "previous_evidence": _evidence_ref(before, old_evidence) if before else None,
            "evidence": _evidence_ref(after, new_evidence) if after else None,
            "materiality": "informational" if claim["field"] in INFORMATIONAL_FIELDS else "material",
        }
        for key in ("period", "account_type", "currency"):
            if claim.get(key) is not None:
                body[key] = claim[key]
        events.append(body)

    for key, after in new.items():
        before = old.get(key)
        if before is None:
            if not after.get("carried_forward"):
                event("added", after, None, after)
        elif _identity_value(before) != _identity_value(after) or after.get("field") != "social_profile" and _canonical(before.get("value")) != _canonical(after.get("value")):
            event("changed", after, before, after)
        else:
            counts["unchanged"] += 1
    for key, before in old.items():
        if key in new:
            continue
        module = _module_of(before, old_evidence)
        event("unverified" if module in unverified else "removed", before, before, None)
    for module in carried:
        record = (current_records or {}).get(module) or {}
        attempt = record.get("current_attempt") or {}
        counts["unavailable"] += 1
        events.append({
            "change_type": "unavailable",
            "module": module,
            "fields_retained": sorted({claim["field"] for claim in current_claims if claim.get("carried_forward") and _module_of(claim, new_evidence) == module}),
            "last_verified_at": record.get("retrieved_at"),
            "current_attempt": attempt,
            "materiality": "informational",
        })
    summary = {"compared": True, "counts": counts, "carried_forward_modules": sorted(carried), "unverified_modules": sorted(unverified)}
    return events, summary
