"""Arms compared in the V3.2 news experiments. All are deterministic functions of (census item, validated LLM record).

  v31          the release (334a085) as published: the deterministic baseline.
  A_filter     Experiment A, LLM as a second-stage filter: V3.1's items, kept only if the LLM's validated decision is publish.
  A_lenient    A, but only an explicit LLM "withhold" removes an item ("uncertain" keeps V3.1's decision).
  B_llm_only   Experiment B, LLM as item-level classifier over the whole candidate pool (every dated item the permissive
               baseline extracted from a verified site); published iff the validated decision is publish.
  C_hybrid     Experiment C: deterministic hard gates first (V3.1 withheld it for an identity/section/date/source-integrity
               reason => never published, whatever the LLM says), then the LLM decides content for the rest of the pool.
  D_conservative  Experiment D: C, and additionally the LLM states a genuine company event (is_genuine_company_event=yes,
               event_type≠none) with low uncertainty, ≥1 verified quote, and no date conflict with the pipeline.
  D_filter     D's evidence requirement applied to V3.1's items only (a conservative second-stage filter).

The LLM can never add an item the deterministic extraction did not produce, never assign a date, and never override a
hard gate. A failed or missing LLM call counts as "uncertain" (not published under A/B/C/D), never as publish.
"""
from __future__ import annotations

from typing import Any

ARMS = ("v31", "A_filter", "A_lenient", "B_llm_only", "C_hybrid", "D_conservative", "D_filter")


def llm_publish(rec: dict[str, Any] | None) -> bool:
    return bool(rec) and rec.get("final_decision") == "publish"


def conservative(rec: dict[str, Any] | None) -> bool:
    v = (rec or {}).get("validated") or {}
    return (llm_publish(rec) and v.get("is_genuine_company_event") == "yes" and v.get("event_type") not in (None, "none")
            and v.get("uncertainty") == "low" and (v.get("verified_quotes") or 0) >= 1
            and v.get("date_status") not in ("verified_differs_from_pipeline",))


def arm_members(items: list[dict[str, Any]], llm: dict[str, dict[str, Any]], *, v31_arm: str = "v31", has_reasons: bool = True) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {arm: set() for arm in ARMS}
    for item in items:
        iid = item["item_id"]
        rec = llm.get(iid)
        in_v31 = v31_arm in (item.get("arms") or [])
        hard = bool(item.get("v31_hard_reject")) or (has_reasons and item.get("v31_status") == "absent")
        if in_v31:
            out["v31"].add(iid)
            if llm_publish(rec):
                out["A_filter"].add(iid)
            if not rec or rec.get("final_decision") != "withhold":
                out["A_lenient"].add(iid)
            if conservative(rec):
                out["D_filter"].add(iid)
        if llm_publish(rec):
            out["B_llm_only"].add(iid)
        if has_reasons and not hard and (in_v31 or item.get("v31_status") == "withheld"):
            if llm_publish(rec):
                out["C_hybrid"].add(iid)
            if conservative(rec):
                out["D_conservative"].add(iid)
    if not has_reasons:
        out.pop("C_hybrid"); out.pop("D_conservative")
    return out
