"""Signalpost output contract: availability states, evidence entries, envelopes and validation.

The envelope follows OUTPUT_CONTRACT.md. Validation mirrors the public rules of Builderr's
signalpost-citation-validator (structure and captured bytes only; it never judges truth or identity).
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

AVAILABILITY_STATES = ("available", "not_available", "blocked", "not_applicable", "ambiguous", "failed")
TERMINAL_STATUSES = ("completed", "failed")

# Source-record status (evidence.py) -> contract availability.
STATUS_TO_AVAILABILITY = {
    "available": "available",
    "not_found": "not_available",
    "not_applicable": "not_applicable",
    "blocked": "blocked",
    "source_error": "failed",
    "not_fetched": "failed",
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def availability_for(record: dict[str, Any] | None) -> str:
    return STATUS_TO_AVAILABILITY.get(str((record or {}).get("status")), "failed")


def _digest(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def snapshot_relative_path(content_sha256: str) -> str:
    return f"{content_sha256[:2]}/{content_sha256}.bin"


def evidence_entry(record: dict[str, Any], claim_span: str, *, snapshot_root: Path | None = None) -> dict[str, Any] | None:
    """One citable evidence item: a captured source response plus the span that supports one claim."""
    url = record.get("source_url")
    sha = record.get("content_sha256")
    retrieved_at = record.get("retrieved_at")
    if record.get("status") != "available" or not url or not sha or not retrieved_at:
        return None
    entry = {
        "id": "ev-" + _digest(url, sha, claim_span)[:20],
        "source_url": url,
        "source_class": record.get("source_class") or record.get("source_type"),
        "retrieved_at": retrieved_at,
        "content_sha256": sha,
        "claim_span": claim_span,
    }
    if record.get("effective_at"):
        entry["effective_at"] = record["effective_at"]
    if snapshot_root is not None and (snapshot_root / snapshot_relative_path(sha)).is_file():
        entry["snapshot_path"] = snapshot_relative_path(sha)
    return entry


class ClaimSet:
    """Accumulates claims and de-duplicated evidence for one envelope."""

    def __init__(self, snapshot_root: Path | None = None):
        self.snapshot_root = snapshot_root
        self.claims: list[dict[str, Any]] = []
        self._evidence: dict[str, dict[str, Any]] = {}
        self._keys: set[str] = set()

    def add(
        self,
        category: str,
        field: str,
        value: Any,
        record: dict[str, Any] | None,
        claim_span: str,
        *,
        confidence: float = 0.99,
        method: str = "deterministic_json_field",
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Add an available claim backed by `record`. Returns False (and adds nothing) without valid evidence."""
        entry = evidence_entry(record or {}, claim_span, snapshot_root=self.snapshot_root)
        if entry is None:
            return False
        key = _digest(category, field, json.dumps([value, extra or {}], sort_keys=True, ensure_ascii=False, default=str))
        if key in self._keys:
            return False
        self._keys.add(key)
        self._evidence.setdefault(entry["id"], entry)
        claim = {
            "field": field,
            "category": category,
            "value": value,
            "availability": "available",
            "confidence": confidence,
            "evidence_ids": [entry["id"]],
            "method": method,
            "key": key[:24],
        }
        claim.update(extra or {})
        if (record or {}).get("carried_forward"):
            # The source failed in this run; the value is the last supported one, with its original evidence.
            claim["carried_forward"] = True
            claim["last_verified_at"] = (record or {}).get("retrieved_at")
        self.claims.append(claim)
        return True

    def absent(self, category: str, field: str, availability: str, reason: str | None) -> None:
        """Record an explicit non-available state; never carries a value."""
        if availability not in AVAILABILITY_STATES or availability == "available":
            raise ValueError(f"absent() requires a non-available state, got {availability!r}")
        key = _digest(category, field, "<absent>")
        if key in self._keys:
            return
        self._keys.add(key)
        self.claims.append({
            "field": field,
            "category": category,
            "value": None,
            "availability": availability,
            "confidence": None,
            "evidence_ids": [],
            "reason": reason,
            "key": key[:24],
        })

    @property
    def evidence(self) -> list[dict[str, Any]]:
        return sorted(self._evidence.values(), key=lambda item: item["id"])


def build_envelope(
    organisation_number: str | None,
    *,
    run: dict[str, Any],
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    changes: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    operations: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = {
        "organisation_number": organisation_number,
        "run": run,
        "claims": claims,
        "evidence": evidence,
        "changes": changes or [],
        "errors": errors or [],
        "operations": operations or {"requests": 0, "runtime_ms": 0, "third_party_cost_usd": 0},
    }
    envelope.update(extra or {})
    return envelope


def _iso_with_timezone(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _web_url(value: Any) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.username is None and parsed.password is None


def validate_envelope(envelope: dict[str, Any], *, snapshot_root: Path | None = None) -> list[dict[str, Any]]:
    """Return findings (empty when valid). Codes are stable identifiers for reports and tests."""
    findings: list[dict[str, Any]] = []

    def finding(code: str, claim_index: int | None = None, evidence_id: str | None = None) -> None:
        findings.append({"code": code, "claim_index": claim_index, "evidence_id": evidence_id})

    org = envelope.get("organisation_number")
    if not (isinstance(org, str) and re.fullmatch(r"\d{9}", org)) and (envelope.get("run") or {}).get("terminal_status") != "failed":
        finding("invalid_organisation_number")
    run = envelope.get("run") or {}
    if run.get("terminal_status") not in TERMINAL_STATUSES:
        finding("non_terminal_status")
    for key in ("claims", "evidence", "changes", "errors"):
        if not isinstance(envelope.get(key), list):
            finding(f"missing_{key}")
    evidence_list = envelope.get("evidence") if isinstance(envelope.get("evidence"), list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for item in evidence_list:
        item_id = item.get("id")
        if item_id in by_id:
            finding("duplicate_evidence_id", evidence_id=item_id)
        by_id[item_id] = item
    for index, claim in enumerate(envelope.get("claims") or []):
        availability = claim.get("availability")
        if availability not in AVAILABILITY_STATES:
            finding("invalid_availability", index)
            continue
        ids = claim.get("evidence_ids") or []
        if availability == "available" and not ids:
            finding("available_claim_without_evidence", index)
        if availability != "available" and claim.get("value") is not None:
            finding("value_on_non_available_claim", index)
        for evidence_id in sorted(set(ids)):
            item = by_id.get(evidence_id)
            if item is None:
                finding("missing_evidence_record", index, evidence_id)
                continue
            if not _web_url(item.get("source_url")):
                finding("invalid_source_url", index, evidence_id)
            if not _iso_with_timezone(item.get("retrieved_at")):
                finding("invalid_retrieved_at", index, evidence_id)
            if not _SHA256.match(str(item.get("content_sha256") or "")):
                finding("invalid_content_sha256", index, evidence_id)
            if snapshot_root is not None and item.get("snapshot_path"):
                path = (snapshot_root / item["snapshot_path"]).resolve()
                if not path.is_relative_to(snapshot_root.resolve()) or not path.is_file():
                    finding("snapshot_missing", index, evidence_id)
                elif hashlib.sha256(path.read_bytes()).hexdigest() != item.get("content_sha256"):
                    finding("snapshot_hash_mismatch", index, evidence_id)
    return findings


def validate_batch(envelopes: list[dict[str, Any]], input_rows: Iterable[str | None], *, snapshot_root: Path | None = None) -> dict[str, Any]:
    expected = list(input_rows)
    per_envelope = {}
    for position, envelope in enumerate(envelopes):
        problems = validate_envelope(envelope, snapshot_root=snapshot_root)
        if problems:
            per_envelope[str(position)] = problems
    checks = {
        "one_envelope_per_input_row": len(envelopes) == len(expected),
        "envelopes_follow_input_order": [item.get("input_organisation_number") for item in envelopes] == expected,
        "all_terminal": all((item.get("run") or {}).get("terminal_status") in TERMINAL_STATUSES for item in envelopes),
        "all_envelopes_valid": not per_envelope,
    }
    return {"passed": all(checks.values()), "checks": checks, "findings": per_envelope}
