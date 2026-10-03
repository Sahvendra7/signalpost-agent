"""Top-level identity block and the overall company-level status of an envelope.

Both are derived deterministically from the envelope's own claims, errors and module states (never by an
LLM). Module statuses stay in `modules`; `company_status` summarises them for the row.
"""
from __future__ import annotations

from typing import Any

INPUT_ERROR_CODES = {"invalid_organisation_number", "missing_organisation_number", "conflicting_identifiers", "malformed_input_row", "not_researched"}
DEADLINE_CODES = {"deadline_exceeded", "deadline_degraded", "interrupted"}
ANSWERED_STATES = {"complete", "not_found", "not_applicable"}
IDENTITY_FIELDS = ("organisation_number", "legal_name", "legal_form")


def identity_block(envelope: dict[str, Any]) -> dict[str, Any]:
    claims = {claim["field"]: claim for claim in envelope.get("claims") or [] if claim.get("category") == "identity" and claim.get("availability") == "available"}
    evidence = {item["id"]: item for item in envelope.get("evidence") or []}
    anchor = claims.get("legal_name") or claims.get("organisation_number")
    source = evidence.get((anchor or {}).get("evidence_ids", [None])[0]) or {}
    bankrupt = (claims.get("bankrupt") or {}).get("value")
    liquidating = (claims.get("under_liquidation") or {}).get("value")
    if bankrupt is True:
        registry_status = "bankrupt"
    elif liquidating is True:
        registry_status = "under_liquidation"
    elif bankrupt is False and liquidating is False:
        registry_status = "registered"
    else:
        registry_status = "unknown"
    anchored = anchor is not None and (claims.get("organisation_number") or {}).get("value") in (None, envelope.get("organisation_number"))
    return {
        "organisation_number": envelope.get("organisation_number") if anchored else None,
        "input_organisation_number": envelope.get("input_organisation_number"),
        "anchored": anchored,
        "method": "exact organisation-number match in Enhetsregisteret" if anchored else None,
        "legal_name": (claims.get("legal_name") or {}).get("value"),
        "legal_form": (claims.get("legal_form") or {}).get("value"),
        "registry_status": registry_status,
        "source_class": source.get("source_class"),
        "source_url": source.get("source_url"),
        "retrieved_at": source.get("retrieved_at"),
        "content_sha256": source.get("content_sha256"),
        "evidence_id": source.get("id"),
        "carried_forward": bool((anchor or {}).get("carried_forward")),
    }


def company_status(envelope: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    """complete | partial | identity_unresolved | invalid_input, with the reasons behind it."""
    codes = {error.get("code") for error in envelope.get("errors") or []}
    modules = envelope.get("modules") or {}
    if codes & INPUT_ERROR_CODES and not identity["anchored"]:
        return {"state": "invalid_input", "reasons": sorted(codes & INPUT_ERROR_CODES)}
    if not identity["anchored"]:
        return {"state": "identity_unresolved", "reasons": ["the registry returned no record for this organisation number"]}
    reasons = [f"{name}: {state['state']}" for name, state in sorted(modules.items()) if name != "registry" and state.get("state") not in ANSWERED_STATES]
    reasons += sorted(codes & DEADLINE_CODES)
    return {"state": "partial" if reasons else "complete", "reasons": reasons}
