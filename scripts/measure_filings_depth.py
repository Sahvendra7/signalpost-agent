#!/usr/bin/env python3
"""Corrected filings-depth measurement (Phase 4A, measurement only; frozen code is not modified).

Why: the frozen E2 experiment (experiments/filings.py) has two measurement defects observed live:
  1. it reads the FIRST element of /regnskap/{org}, which the API orders oldest-first, so it measures
     the oldest returned period instead of the latest;
  2. it requests the copy PDF with `Accept: application/pdf`, which the endpoint answers with HTTP 406,
     while `Accept: */*` returns the PDF.
This script re-measures on the same sample, read-only, using the same endpoints:
  - every numeric field in every period of the same /regnskap/{org} response the baseline already
    fetches, split into fields the baseline already publishes vs additional fields;
  - optionally the filed-year list and latest copy PDF (paced 2.1 s like the starter).

  uv run python scripts/measure_filings_depth.py --sample out/experiments/sample.jsonl \
      --baseline out/experiments/baseline-envelopes.jsonl --out out/experiments/e2b-filings-depth.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.experiments.filings import pdf_inspection  # noqa: E402
from norway_company_agent.http import fetch_bytes  # noqa: E402

ACCOUNTS = "https://data.brreg.no/regnskapsregisteret/regnskap/{org}"
YEARS = "https://data.brreg.no/regnskapsregisteret/regnskap/aarsregnskap/kopi/{org}/aar"
COPY = "https://data.brreg.no/regnskapsregisteret/regnskap/aarsregnskap/kopi/{org}/{year}"
# Leaves the V1 pipeline already publishes (claims.py starter set), keyed by API path.
PUBLISHED = {
    "/resultatregnskapResultat/driftsresultat/driftsinntekter/sumDriftsinntekter": "revenue",
    "/resultatregnskapResultat/driftsresultat/driftsresultat": "operating_result",
    "/resultatregnskapResultat/ordinaertResultatFoerSkattekostnad": "profit_before_tax",
    "/resultatregnskapResultat/aarsresultat": "net_result",
    "/eiendeler/sumEiendeler": "total_assets",
    "/egenkapitalGjeld/egenkapital/sumEgenkapital": "equity",
    "/egenkapitalGjeld/gjeldOversikt/sumGjeld": "total_debt",
}
SKIP = {"/id", "/journalnr"}
METADATA = ("/regnskapstype", "/valuta", "/oppstillingsplan", "/revisjon/ikkeRevidertAarsregnskap", "/revisjon/fravalgRevisjon", "/avviklingsregnskap", "/regnkapsprinsipper/smaaForetak")


def leaves(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from leaves(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from leaves(value, f"{path}/{index}")
    else:
        yield path, node


def numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def measure(org: str, with_pdf: bool) -> dict:
    started = time.monotonic()
    out: dict = {"organisation_number": org, "requests": 0, "attempts": 0, "bytes": 0}

    def get(url, **kwargs):
        result = fetch_bytes(url, **kwargs)
        out["requests"] += 1
        out["attempts"] += result.attempts
        out["bytes"] += len(result.raw or b"")
        return result

    response = get(ACCOUNTS.format(org=org), headers={"Accept": "application/json"})
    out["accounts_status"] = response.status
    out["accounts_retrieved_at"] = response.retrieved_at
    out["accounts_sha256"] = response.content_sha256
    periods = []
    parse_failures = 0
    if response.status == 200:
        try:
            body = response.json()
        except ValueError:
            body = None
            parse_failures += 1
        for item in body if isinstance(body, list) else []:
            if not isinstance(item, dict):
                parse_failures += 1
                continue
            flat = dict(leaves(item))
            record_org = str(flat.get("/virksomhet/organisasjonsnummer") or "")
            period_to = str(flat.get("/regnskapsperiode/tilDato") or "")
            numbers = {path: value for path, value in flat.items() if numeric(value) and path not in SKIP and not path.startswith("/virksomhet")}
            periods.append({
                "period_from": flat.get("/regnskapsperiode/fraDato"), "period_to": period_to or None,
                "account_type": flat.get("/regnskapstype"), "org_matches": record_org == org, "record_org": record_org,
                "numeric_fields": len(numbers),
                "published_fields": sorted(PUBLISHED[path] for path in numbers if path in PUBLISHED),
                "additional_fields": sorted(path for path in numbers if path not in PUBLISHED),
                "metadata": {path: flat.get(path) for path in METADATA if path in flat},
            })
    out["parse_failures"] = parse_failures
    out["periods"] = periods
    if with_pdf:
        time.sleep(2.1)
        years_response = get(YEARS.format(org=org))
        years = []
        if years_response.status == 200:
            try:
                years = sorted({str(item) for item in years_response.json() if str(item).isdigit()})
            except (ValueError, TypeError):
                out["parse_failures"] += 1
        out["copy_years_status"], out["copy_years"] = years_response.status, years
        if years:
            time.sleep(2.1)
            pdf = get(COPY.format(org=org, year=years[-1]), headers={"Accept": "*/*"}, timeout=60)
            inspection = pdf_inspection(pdf.raw or b"") if pdf.status == 200 else {"is_pdf": False}
            inspection.update({"year": years[-1], "status": pdf.status, "content_type": pdf.content_type, "sha256": pdf.content_sha256, "retrieved_at": pdf.retrieved_at})
            out["pdf"] = inspection
    out["runtime_ms"] = int((time.monotonic() - started) * 1000)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()
    orgs = [json.loads(line)["organisation_number"] for line in Path(args.sample).read_text().splitlines() if line.strip()]
    filed = {}
    published_claims = Counter()
    for line in Path(args.baseline).read_text().splitlines():
        envelope = json.loads(line)
        for claim in envelope["claims"]:
            if claim["category"] == "filings" and claim["availability"] == "available":
                if claim["field"] == "latest_filed_accounts_year":
                    filed[envelope["organisation_number"]] = str(claim["value"])
                else:
                    published_claims[envelope["organisation_number"]] += 1
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda org: measure(org, not args.no_pdf), orgs))
    wall = time.monotonic() - started
    for row in rows:
        org = row["organisation_number"]
        row["filed_year_registry"] = filed.get(org)
        row["baseline_published_financial_claims"] = published_claims.get(org, 0)
        valid = [period for period in row["periods"] if period["org_matches"] and period["period_to"]]
        row["latest_period_to"] = max((period["period_to"] for period in valid), default=None)
        row["latest_period_matches_filed_year"] = bool(row["latest_period_to"] and filed.get(org) and row["latest_period_to"][:4] == filed[org])
        row["structured_fields_total"] = sum(period["numeric_fields"] for period in valid)
        row["additional_fields_total"] = sum(len(period["additional_fields"]) for period in valid)
        row["identity_rejections"] = sum(1 for period in row["periods"] if not period["org_matches"])
    n = len(rows)
    covered_base = sum(1 for row in rows if row["baseline_published_financial_claims"] > 0)
    gain = [row for row in rows if row["additional_fields_total"] > 0]
    summary = {
        "companies": n,
        "wall_s": round(wall, 1),
        "requests": sum(row["requests"] for row in rows), "attempts": sum(row["attempts"] for row in rows), "bytes": sum(row["bytes"] for row in rows),
        "accounts_status": dict(Counter(str(row["accounts_status"]) for row in rows)),
        "parse_failures": sum(row["parse_failures"] for row in rows),
        "identity_rejections": sum(row["identity_rejections"] for row in rows),
        "periods_per_company": dict(Counter(len(row["periods"]) for row in rows)),
        "period_years": dict(sorted(Counter(period["period_to"][:4] for row in rows for period in row["periods"] if period["period_to"]).items())),
        "account_types": dict(Counter(period["account_type"] for row in rows for period in row["periods"])),
        "latest_period_matches_filed_year": sum(1 for row in rows if row["latest_period_matches_filed_year"]),
        "baseline_companies_with_financial_values": covered_base,
        "baseline_published_financial_values": sum(row["baseline_published_financial_claims"] for row in rows),
        "structured_numeric_fields_total": sum(row["structured_fields_total"] for row in rows),
        "additional_numeric_fields_total": sum(row["additional_fields_total"] for row in rows),
        "companies_gaining_additional_fields": len(gain),
        "companies_gaining_additional_fields_without_baseline_financials": sum(1 for row in gain if row["baseline_published_financial_claims"] == 0),
        "additional_field_frequency": dict(Counter(path for row in rows for period in row["periods"] if period["org_matches"] for path in period["additional_fields"]).most_common()),
        "metadata_seen": dict(Counter(path for row in rows for period in row["periods"] for path in period["metadata"])),
    }
    if not args.no_pdf:
        pdfs = [row.get("pdf") or {} for row in rows]
        summary["pdf"] = {
            "copy_years_status": dict(Counter(str(row.get("copy_years_status")) for row in rows)),
            "copy_years_latest": dict(Counter((row.get("copy_years") or ["none"])[-1] for row in rows)),
            "pdf_status": dict(Counter(str(item.get("status")) for item in pdfs)),
            "pdf_retrieved": sum(1 for item in pdfs if item.get("is_pdf")),
            "pdf_text_parsed": sum(1 for item in pdfs if item.get("is_pdf") and (item.get("text_chars") or 0) >= 200),
            "pdf_image_only": sum(1 for item in pdfs if item.get("is_pdf") and (item.get("text_chars") or 0) < 200 and (item.get("image_pages") or 0) > 0),
            "pdf_parse_errors": sum(1 for item in pdfs if item.get("parse_error")),
            "pdf_year_equals_filed_year": sum(1 for row in rows if (row.get("pdf") or {}).get("is_pdf") and row["pdf"].get("year") == row.get("filed_year_registry")),
        }
    summary["runtime_ms_per_company_mean"] = round(sum(row["runtime_ms"] for row in rows) / (n or 1))
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
