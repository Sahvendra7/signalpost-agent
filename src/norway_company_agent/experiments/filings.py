"""Experiment 2: what filing information the permitted official sources expose, per company.

Findings from Brreg's own source (github.com/brreg/regnskapsregister-api):
- /regnskapsregisteret/regnskap/{org} is the OPEN part: key figures from the latest submitted account.
  A closed part with three years of near-complete figures is for public authorities only.
  It accepts `?år=YYYY`; whether the open part returns earlier years is measured here, not assumed.
- /regnskap/aarsregnskap/kopi/{org}/aar lists years with a filed copy (last 15 years).
- /regnskap/aarsregnskap/kopi/{org}/{year} streams the copy: a TIFF scan converted to PDF page images,
  so a text layer is not expected. Both copy endpoints share a per-IP bucket4j rate limit.
"""
from __future__ import annotations

import io
import threading
import time
from typing import Any

from .common import ByteFetcher, Meter, Timer, evidence_complete
from ..http import fetch_bytes

ACCOUNTS = "https://data.brreg.no/regnskapsregisteret/regnskap/{org}"
YEARS = "https://data.brreg.no/regnskapsregisteret/regnskap/aarsregnskap/kopi/{org}/aar"
COPY = "https://data.brreg.no/regnskapsregisteret/regnskap/aarsregnskap/kopi/{org}/{year}"
COPY_INTERVAL_S = 2.1  # starter's observed ~30 request starts/minute

_copy_lock = threading.Lock()
_copy_last = 0.0


def _copy_slot() -> None:
    global _copy_last
    with _copy_lock:
        delay = COPY_INTERVAL_S - (time.monotonic() - _copy_last)
        if delay > 0:
            time.sleep(delay)
        _copy_last = time.monotonic()


def _get(value: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


FIELDS = {
    "revenue": ("resultatregnskapResultat", "driftsresultat", "driftsinntekter", "sumDriftsinntekter"),
    "sales_revenue": ("resultatregnskapResultat", "driftsresultat", "driftsinntekter", "salgsinntekter"),
    "operating_costs": ("resultatregnskapResultat", "driftsresultat", "driftskostnad", "sumDriftskostnad"),
    "wage_costs": ("resultatregnskapResultat", "driftsresultat", "driftskostnad", "loennskostnad"),
    "operating_result": ("resultatregnskapResultat", "driftsresultat", "driftsresultat"),
    "net_financial_items": ("resultatregnskapResultat", "finansresultat", "nettoFinans"),
    "profit_before_tax": ("resultatregnskapResultat", "ordinaertResultatFoerSkattekostnad"),
    "net_result": ("resultatregnskapResultat", "aarsresultat"),
    "total_assets": ("eiendeler", "sumEiendeler"),
    "fixed_assets": ("eiendeler", "anleggsmidler", "sumAnleggsmidler"),
    "current_assets": ("eiendeler", "omloepsmidler", "sumOmloepsmidler"),
    "cash": ("eiendeler", "sumBankinnskuddOgKontanter"),
    "equity": ("egenkapitalGjeld", "egenkapital", "sumEgenkapital"),
    "total_debt": ("egenkapitalGjeld", "gjeldOversikt", "sumGjeld"),
    "short_term_debt": ("egenkapitalGjeld", "gjeldOversikt", "kortsiktigGjeld", "sumKortsiktigGjeld"),
    "long_term_debt": ("egenkapitalGjeld", "gjeldOversikt", "langsiktigGjeld", "sumLangsiktigGjeld"),
}
FLAGS = {
    "audit_opt_out": ("revisjon", "fravalgRevisjon"),
    "not_audited": ("revisjon", "ikkeRevidertAarsregnskap"),
    "small_company_rules": ("regnkapsprinsipper", "smaaForetak"),
    "liquidation_accounts": ("avviklingsregnskap",),
}
BALANCE = ("total_assets", "equity", "total_debt")


def normalize_account(record: dict[str, Any]) -> dict[str, Any]:
    period = record.get("regnskapsperiode") if isinstance(record.get("regnskapsperiode"), dict) else {}
    values = {}
    for name, path in FIELDS.items():
        value = _get(record, *path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values[name] = value
    flags = {name: _get(record, *path) for name, path in FLAGS.items() if isinstance(_get(record, *path), bool)}
    return {
        "record_id": record.get("id"),
        "account_type": record.get("regnskapstype"),
        "currency": record.get("valuta"),
        "period_from": period.get("fraDato"),
        "period_to": period.get("tilDato"),
        "layout": record.get("oppstillingsplan"),
        "parent_company": _get(record, "virksomhet", "morselskap"),
        "values": values,
        "flags": flags,
        "org_in_record": str(_get(record, "virksomhet", "organisasjonsnummer") or ""),
    }


def period_correct(account: dict[str, Any], filed_year: str | None) -> bool | None:
    start, end = str(account.get("period_from") or ""), str(account.get("period_to") or "")
    if not (start and end):
        return False
    if start > end:
        return False
    if not filed_year:
        return None
    return end[:4] == str(filed_year) or start[:4] == str(filed_year)


def pdf_inspection(raw: bytes) -> dict[str, Any]:
    result = {"is_pdf": raw[:5] == b"%PDF-", "pages": None, "text_chars": 0, "image_pages": 0, "parse_error": None}
    if not result["is_pdf"]:
        return result
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        result["pages"] = len(reader.pages)
        chars = 0
        images = 0
        for page in reader.pages[:20]:
            chars += len((page.extract_text() or "").strip())
            resources = page.get("/Resources") or {}
            xobjects = resources.get("/XObject") if hasattr(resources, "get") else None
            if xobjects:
                images += 1
        result["text_chars"] = chars
        result["image_pages"] = images
    except Exception as exc:  # malformed PDF is a measured outcome, not a crash
        result["parse_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return result


def run_company(profile: dict[str, Any], fetcher: ByteFetcher = fetch_bytes, *, fetch_pdf: bool = True, probe_prior_year: bool = True, rate_limit: bool = True) -> dict[str, Any]:
    org = profile["organisation_number"]
    registry = (profile.get("evidence", {}).get("registry_live") or {}).get("value") or {}
    filed_year = str(registry.get("latest_submitted_accounts") or profile.get("latest_submitted_accounts") or "") or None
    meter = Meter(fetcher)
    out: dict[str, Any] = {"organisation_number": org, "filed_year_registry": filed_year}
    evidence: list[dict[str, Any]] = []
    with Timer() as timer:
        latest = meter.get(ACCOUNTS.format(org=org), headers={"Accept": "application/json"})
        accounts = []
        if latest.status == 200:
            try:
                body = latest.json()
                accounts = [normalize_account(item) for item in body if isinstance(item, dict)] if isinstance(body, list) else []
            except ValueError:
                out["accounts_parse_error"] = True
        out["accounts_status"] = latest.status
        mismatched = [item for item in accounts if item["org_in_record"] and item["org_in_record"] != org]
        accounts = [item for item in accounts if item not in mismatched]
        out["identity_rejections"] = len(mismatched)
        company = next((item for item in accounts if item["account_type"] == "SELSKAP"), accounts[0] if accounts else None)
        out["has_latest_filing"] = company is not None
        out["latest_period"] = {"from": company["period_from"], "to": company["period_to"]} if company else None
        out["period_correct"] = period_correct(company, filed_year) if company else None
        out["has_group_accounts"] = any(item["account_type"] == "KONSERN" for item in accounts)
        values = company["values"] if company else {}
        out["has_revenue"] = "revenue" in values
        out["has_operating_result"] = "operating_result" in values
        out["has_balance_sheet"] = all(name in values for name in BALANCE)
        out["has_wage_costs"] = "wage_costs" in values
        out["financial_values"] = len(values)
        out["starter_financial_values"] = sum(1 for name in ("revenue", "operating_result", "profit_before_tax", "net_result", "total_assets", "equity", "total_debt") if name in values)
        if company:
            for name, value in values.items():
                evidence.append({"source_url": latest.url, "content_sha256": latest.content_sha256, "retrieved_at": latest.retrieved_at, "claim_span": f"{name}={value} ({company['period_from']}..{company['period_to']})"})

        prior_values = 0
        if probe_prior_year and company and company["period_to"]:
            prior_year = str(int(company["period_to"][:4]) - 1)
            prior = meter.get(ACCOUNTS.format(org=org) + f"?%C3%A5r={prior_year}", headers={"Accept": "application/json"})
            out["prior_year_status"] = prior.status
            if prior.status == 200:
                try:
                    body = prior.json()
                    prior_accounts = [normalize_account(item) for item in body if isinstance(item, dict)] if isinstance(body, list) else []
                    prior_accounts = [item for item in prior_accounts if str(item["period_to"] or "")[:4] == prior_year and (not item["org_in_record"] or item["org_in_record"] == org)]
                    prior_values = max((len(item["values"]) for item in prior_accounts), default=0)
                except ValueError:
                    pass
        out["prior_year_structured"] = prior_values > 0

        if rate_limit:
            _copy_slot()
        years_response = meter.get(YEARS.format(org=org), headers={"Accept": "application/json"})
        years: list[str] = []
        if years_response.status == 200:
            try:
                body = years_response.json()
                years = sorted({str(item) for item in body if str(item).isdigit()}) if isinstance(body, list) else []
            except ValueError:
                pass
        out["copy_years_status"] = years_response.status
        out["copy_years"] = years
        out["has_multiple_years"] = len(years) >= 2
        if years:
            evidence.append({"source_url": years_response.url, "content_sha256": years_response.content_sha256, "retrieved_at": years_response.retrieved_at, "claim_span": f"aar={years}"})

        out["pdf"] = None
        if fetch_pdf and years:
            if rate_limit:
                _copy_slot()
            pdf = meter.get(COPY.format(org=org, year=years[-1]), headers={"Accept": "application/pdf"}, timeout=60)
            inspection = pdf_inspection(pdf.raw or b"") if pdf.status == 200 else {"is_pdf": False}
            inspection.update({"year": years[-1], "status": pdf.status, "bytes": len(pdf.raw or b""), "content_type": pdf.content_type})
            out["pdf"] = inspection
            if inspection.get("is_pdf"):
                evidence.append({"source_url": pdf.url, "content_sha256": pdf.content_sha256, "retrieved_at": pdf.retrieved_at, "claim_span": f"annual accounts copy {years[-1]}, {inspection.get('pages')} pages"})
    pdf_info = out.get("pdf") or {}
    out.update({
        "requests": meter.requests,
        "runtime_ms": timer.ms,
        "statuses": dict(meter.statuses),
        "transport_failure": latest.status == 0,
        "unmeasured": latest.status == 0,
        "pdf_retrieved": bool(pdf_info.get("is_pdf")),
        "pdf_text_parsed": bool(pdf_info.get("text_chars", 0) >= 200),
        "pdf_image_only": bool(pdf_info.get("is_pdf") and pdf_info.get("text_chars", 0) < 200 and (pdf_info.get("image_pages") or 0) > 0),
        "published_identity_mismatches": 0,
        "evidence_items": len(evidence),
        "evidence_complete": sum(evidence_complete(item) for item in evidence),
        "covered": out.get("has_latest_filing") or bool(years),
    })
    return out
