"""Deterministic extraction: source records in a profile -> fact-level contract claims.

Pure functions only. A claim is emitted only when its source record is `available` and carries a
content hash; otherwise the category gets an explicit non-available state. Values are copied from the
source, never imputed: a missing number stays missing and `0`, `false` and `[]` stay real values.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import ClaimSet, availability_for

CATEGORIES = ("identity", "description", "filings", "leadership", "locations", "websites", "public_activity", "hiring", "relationships", "registry_activity")

ROLE_FIELDS = {
    "DAGL": "ceo",
    "LEDE": "board_chair",
    "NEST": "board_deputy_chair",
    "MEDL": "board_member",
    "VARA": "board_deputy_member",
    "OBS": "board_observer",
    "REVI": "auditor",
    "REGN": "accountant",
    "KONT": "contact_person",
    "DTPR": "partner",
    "DTSO": "partner",
    "INNH": "owner",
    "FFØR": "business_manager",
    "KOMP": "general_partner",
    "PROK": "procuration",
    "SIGN": "signatory",
}

FINANCIAL_FIELDS = (
    ("revenue", "revenue"),
    ("operating_result", "operating_result"),
    ("profit_before_tax", "profit_before_tax"),
    ("annual_result", "net_result"),
    ("assets", "total_assets"),
    ("equity", "equity"),
    ("debt", "total_debt"),
)

# Bulk CSV column names -> the live-API normalised keys used below.
_BULK_KEYS = {
    "name": ("navn", "Navn"),
    "legal_form": ("organisasjonsform.kode", "Organisasjonsform.kode"),
    "employees": ("antallAnsatte", "Antall ansatte"),
    "has_registered_employees": ("harRegistrertAntallAnsatte",),
    "industry_code": ("naeringskode1.kode", "Næringskode1.kode"),
    "industry_label": ("naeringskode1.beskrivelse", "Næringskode1.beskrivelse"),
    "website": ("hjemmeside", "Hjemmeside"),
    "latest_submitted_accounts": ("sisteInnsendteAarsregnskap", "Siste innsendte årsregnskap"),
    "bankrupt": ("konkurs", "Konkurs"),
    "liquidating": ("underAvvikling", "Under avvikling"),
    "founded_date": ("stiftelsesdato", "Stiftelsesdato"),
    "registered_date": ("registreringsdatoEnhetsregisteret", "Registreringsdato i Enhetsregisteret"),
    "activity": ("aktivitet", "Aktivitet"),
    "purpose": ("vedtektsfestetFormaal", "Vedtektsfestet formål"),
}


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().casefold() in {"true", "false"}:
        return value.strip().casefold() == "true"
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def normalize_address(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    address = {
        "lines": _text_list(value.get("adresse")),
        "postal_code": value.get("postnummer"),
        "city": value.get("poststed"),
        "municipality": value.get("kommune"),
        "municipality_number": value.get("kommunenummer"),
        "country": value.get("land"),
    }
    address = {key: item for key, item in address.items() if item not in (None, "", [])}
    return address or None


def _bulk_address(raw: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    nested = {
        "adresse": raw.get(f"{prefix}.adresse"),
        "postnummer": raw.get(f"{prefix}.postnummer"),
        "poststed": raw.get(f"{prefix}.poststed"),
        "kommune": raw.get(f"{prefix}.kommune"),
        "kommunenummer": raw.get(f"{prefix}.kommunenummer"),
        "land": raw.get(f"{prefix}.land"),
    }
    return normalize_address(nested)


def identity_view(profile: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
    """Pick the freshest available identity source and expose it with uniform keys."""
    records = profile.get("evidence", {})
    live = records.get("registry_live") or {}
    live_org = str((live.get("value") or {}).get("organisation_number") or "") if isinstance(live.get("value"), dict) else ""
    if live.get("status") == "available" and live_org == str(profile.get("organisation_number")):
        value = dict(live["value"])
        industry = value.get("industry") if isinstance(value.get("industry"), dict) else {}
        value["industry_code"] = industry.get("kode")
        value["industry_label"] = industry.get("beskrivelse")
        value["business_address"] = normalize_address(value.get("business_address"))
        value["postal_address"] = normalize_address(value.get("postal_address"))
        return live, value, "enheter"
    bulk = records.get("registry") or {}
    if bulk.get("status") == "available" and isinstance(bulk.get("value"), dict):
        raw = bulk["value"]
        value = {key: next((raw.get(name) for name in names if _present(raw.get(name))), None) for key, names in _BULK_KEYS.items()}
        value["business_address"] = _bulk_address(raw, "forretningsadresse")
        value["postal_address"] = _bulk_address(raw, "postadresse")
        value["organisation_number"] = raw.get("organisasjonsnummer") or profile.get("organisation_number")
        return bulk, value, "bulk_csv_row"
    return None, {}, ""


def _identity_claims(claims: ClaimSet, profile: dict[str, Any]) -> dict[str, Any]:
    record, view, prefix = identity_view(profile)
    if record is None:
        for category, field in (("identity", "legal_name"), ("locations", "business_address"), ("description", "registered_activity")):
            claims.absent(category, field, "failed", "No registry identity source was available to this run")
        return view
    span = lambda key, value: f"{prefix}.{key}={value}"  # noqa: E731
    if _present(view.get("organisation_number")):
        claims.add("identity", "organisation_number", str(view["organisation_number"]), record, span("organisasjonsnummer", view["organisation_number"]))
    if _present(view.get("name")):
        claims.add("identity", "legal_name", view["name"], record, span("navn", view["name"]))
    else:
        claims.absent("identity", "legal_name", "not_available", "Registry record has no name")
    if _present(view.get("legal_form")):
        claims.add("identity", "legal_form", view["legal_form"], record, span("organisasjonsform.kode", view["legal_form"]))
    if _present(view.get("industry_code")):
        claims.add("identity", "industry", {"code": view["industry_code"], "description": view.get("industry_label")}, record, span("naeringskode1", view["industry_code"]))
    for key, field, source_key in (("bankrupt", "bankrupt", "konkurs"), ("liquidating", "under_liquidation", "underAvvikling")):
        flag = _bool(view.get(key))
        if flag is not None:
            claims.add("identity", field, flag, record, span(source_key, str(flag).lower()))
    employees = _int(view.get("employees"))
    if employees is not None:
        claims.add("identity", "registry_employee_count", employees, record, span("antallAnsatte", employees))
    else:
        claims.absent("identity", "registry_employee_count", "not_available", "The registry record carries no employee count")
    for key, field, source_key in (("founded_date", "founded_date", "stiftelsesdato"), ("registered_date", "registry_registration_date", "registreringsdatoEnhetsregisteret")):
        if _present(view.get(key)):
            claims.add("identity", field, view[key], record, span(source_key, view[key]))
    activity = " ".join(_text_list(view.get("activity")))
    purpose = " ".join(_text_list(view.get("purpose")))
    if activity:
        claims.add("description", "registered_activity", activity, record, span("aktivitet", activity[:200]))
    if purpose:
        claims.add("description", "statutory_purpose", purpose, record, span("vedtektsfestetFormaal", purpose[:200]))
    if not activity and not purpose:
        claims.absent("description", "registered_activity", "not_available", "The registry record carries no activity or purpose text")
    for key, field, source_key in (("business_address", "business_address", "forretningsadresse"), ("postal_address", "postal_address", "postadresse")):
        if view.get(key):
            claims.add("locations", field, view[key], record, span(source_key, ", ".join(view[key].get("lines", []) + [str(view[key].get("postal_code") or ""), str(view[key].get("city") or "")]).strip(", ")))
    if not view.get("business_address"):
        claims.absent("locations", "business_address", "not_available", "The registry record carries no business address")
    if _present(view.get("website")):
        claims.add("websites", "registry_listed_website", view["website"], record, span("hjemmeside", view["website"]))
    if _present(view.get("latest_submitted_accounts")):
        claims.add("filings", "latest_filed_accounts_year", str(view["latest_submitted_accounts"]), record, span("sisteInnsendteAarsregnskap", view["latest_submitted_accounts"]))
    return view


def _module_absent(claims: ClaimSet, category: str, field: str, record: dict[str, Any] | None, reason_if_missing: str) -> None:
    if record is None:
        return  # Module not requested: not checked is not the same as not available.
    state = availability_for(record)
    reason = record.get("note") or reason_if_missing
    claims.absent(category, field, "not_available" if state == "available" else state, reason)


def _financial_claims(claims: ClaimSet, record: dict[str, Any] | None) -> None:
    if record is None:
        return
    rows = ((record.get("value") or {}).get("records") or []) if record.get("status") == "available" else []
    published = 0
    for row in rows:
        period = row.get("period") if isinstance(row.get("period"), dict) else {}
        qualifiers = {
            "period": {"from": period.get("fraDato"), "to": period.get("tilDato")},
            "currency": row.get("currency"),
            "account_type": row.get("account_type"),
        }
        for source_key, field in FINANCIAL_FIELDS:
            value = row.get(source_key)
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            span = f"regnskap[id={row.get('record_id')}].{source_key}={value} ({qualifiers['period']['from']}..{qualifiers['period']['to']}, {row.get('currency')})"
            published += claims.add("filings", field, value, record, span, extra=qualifiers)
    if not published:
        _module_absent(claims, "filings", "annual_accounts", record, "No normalised annual-account record was returned; missing values are not zero")


def _history_claims(claims: ClaimSet, record: dict[str, Any] | None) -> None:
    if record is None:
        return
    value = record.get("value") or {}
    years = value.get("years") if record.get("status") == "available" else None
    if years is None:
        _module_absent(claims, "filings", "filed_account_years", record, "Filing-year list unavailable")
        return
    claims.add("filings", "filed_account_years", list(years), record, f"aarsregnskap/kopi/aar={years}")
    for item in value.get("pdfs") or []:
        claims.add("filings", "annual_accounts_copy", {"year": item.get("year"), "url": item.get("url")}, record, f"aarsregnskap/kopi/{item.get('year')}")


def _role_claims(claims: ClaimSet, record: dict[str, Any] | None) -> None:
    if record is None:
        return
    if record.get("status") != "available":
        _module_absent(claims, "leadership", "roles", record, "Role source unavailable")
        return
    roles = [item for item in (record.get("value") or {}).get("roles", []) if not item.get("inactive")]
    claims.add("leadership", "role_count", len(roles), record, f"roller.active_count={len(roles)}")
    latest_change = None
    for item in roles:
        holder = item.get("name") or item.get("organisation_number")
        if not holder:
            continue
        value = {
            "name": item.get("name"),
            "organisation_number": item.get("organisation_number"),
            "role_code": item.get("role_code"),
            "role": item.get("role"),
            "group": item.get("group"),
            "group_last_changed": item.get("last_changed"),
        }
        value = {key: item_value for key, item_value in value.items() if item_value is not None}
        field = ROLE_FIELDS.get(str(item.get("role_code") or ""), "registered_role")
        claims.add("leadership", field, value, record, f"roller[{item.get('role_code')}]={holder}")
        if item.get("last_changed") and (latest_change is None or item["last_changed"] > latest_change):
            latest_change = item["last_changed"]
    if latest_change:
        claims.add("registry_activity", "roles_last_changed", latest_change, record, f"rollegrupper.sistEndret={latest_change}", extra={"event_date": latest_change})


def _location_claims(claims: ClaimSet, record: dict[str, Any] | None) -> None:
    if record is None:
        return
    if record.get("status") != "available":
        _module_absent(claims, "locations", "subunits", record, "Subunit source unavailable")
        return
    items = (record.get("value") or {}).get("locations", [])
    claims.add("locations", "subunit_count", len(items), record, f"underenheter.count={len(items)}")
    for item in items:
        value = {
            "organisation_number": item.get("organisation_number"),
            "name": item.get("name"),
            "address": normalize_address(item.get("address")),
            "industry": (item.get("industry") or {}).get("kode") if isinstance(item.get("industry"), dict) else item.get("industry"),
            "employees": item.get("employees"),
        }
        value = {key: item_value for key, item_value in value.items() if item_value is not None}
        claims.add("locations", "subunit", value, record, f"underenheter[{item.get('organisation_number')}]={item.get('name')}")


def _group_claims(claims: ClaimSet, record: dict[str, Any] | None) -> None:
    if record is None:
        return
    if record.get("status") == "available" and record.get("value"):
        claims.add("relationships", "group_structure", record["value"], record, "konsernstruktur")
    else:
        _module_absent(claims, "relationships", "group_structure", record, "No official group structure was returned")


def _website_claims(claims: ClaimSet, record: dict[str, Any] | None, view: dict[str, Any], *, site_verified: bool = False) -> None:
    if record is None or (site_verified and record.get("status") != "available"):
        return
    if site_verified and not ((record.get("value") or {}).get("identity_assessment") or {}).get("publishable"):
        return  # a V2-verified site supersedes the v1 ambiguous/unavailable state
    value = record.get("value") or {}
    assessment = value.get("identity_assessment") or {}
    if record.get("status") != "available":
        reason = record.get("note") or "Website unavailable"
        if not _present(view.get("website")):
            reason = "No registry-listed website; website discovery not run"
        _module_absent(claims, "websites", "official_website", record, reason)
        return
    if not assessment.get("publishable"):
        claims.absent("websites", "official_website", "ambiguous", "; ".join(assessment.get("reasons") or ["Exact legal-entity identity not established"]))
        return
    score = float(assessment.get("score") or 0.9)
    method = assessment.get("method") or "identity_gate"
    reasons = "; ".join(assessment.get("reasons") or [])
    claims.add("websites", "official_website", value.get("final_url") or record.get("source_url"), record, f"identity: {reasons}", confidence=score, method=method)
    if value.get("description"):
        claims.add("description", "website_description", value["description"], record, f"meta description: {value['description'][:200]}", confidence=score, method="html_meta_description")
    # Social profiles are published from the site stage (exact linked URL, public_activity), not from this record.


def _page_record(page_url: str, sha: str | None, retrieved_at: str | None, carried: bool = False) -> dict[str, Any]:
    record = {"status": "available", "source_url": page_url, "content_sha256": sha, "retrieved_at": retrieved_at, "source_class": "company_site"}
    if carried:
        record["carried_forward"] = True
    return record


SITE_FAMILIES = (("public_activity", "social_profile"), ("public_activity", "news_item"), ("hiring", "job_posting"))


def _site_research_claims(claims: ClaimSet, record: dict[str, Any] | None, *, v1_site_published: bool) -> bool:
    """Claims from the V2 site stage. Returns True when it verified a website."""
    if record is None:
        return False
    value = record.get("value") or {}
    if record.get("status") != "available":
        reason = record.get("note") or "No verified company website"
        if not v1_site_published:
            for category, field in SITE_FAMILIES:
                claims.absent(category, field, availability_for(record), reason)
        return False
    identity_class = value.get("identity_class")
    reasons = "; ".join(value.get("identity_reasons") or [])
    carried = bool(record.get("carried_forward"))
    first_page = (value.get("pages") or [{}])[0]
    home = _page_record(value.get("site_url"), first_page.get("content_sha256"), first_page.get("retrieved_at"), carried)
    confidence = 1.0 if "organisation number" in reasons else 0.95
    if not v1_site_published:
        claims.add("websites", "official_website", value.get("site_url"), home, f"{identity_class}: {reasons}", confidence=confidence, method="site_identity_v2", extra={"identity_class": identity_class, "identity_source": value.get("identity_source")})
    # Every fact below inherits the identity of the verified site above; its evidence is the captured page it
    # was read from, and its value occurs in that page (site_facts.validate_*).
    profiles = [item for item in value.get("profiles") or [] if item.get("canonical_url")]  # pre-Revision-1 records carry a rewritten URL: not published
    for profile in profiles:
        page = _page_record(profile.get("found_on"), profile.get("content_sha256"), profile.get("retrieved_at"), carried)
        claims.add(
            "public_activity", "social_profile", profile["url"], page, f"outbound link on verified site page {profile.get('found_on')}: {profile.get('evidence_span')}",
            confidence=min(confidence, float(profile.get("identity_score") or confidence)), method="verified_site_outbound_link",
            extra={"platform": profile["platform"], "canonical_url": profile["canonical_url"], "source_page": profile.get("found_on"), "evidence_span": profile.get("evidence_span"), "identity_basis": profile.get("identity_reason")},
        )
    if not profiles:
        ambiguous = value.get("ambiguous_profiles") or []
        if ambiguous:
            claims.absent("public_activity", "social_profile", "ambiguous", f"{len(ambiguous)} profile link(s) on the verified site not corroborated as this company's own")
        else:
            claims.absent("public_activity", "social_profile", "not_available", "Verified website checked; no Facebook, Instagram, LinkedIn or YouTube profile link found")
    if value.get("careers_page"):
        claims.add("websites", "careers_page", value["careers_page"], home, f"careers link on {value.get('site_url')}", confidence=confidence, method="verified_site_link")
    activities = [item for item in value.get("activities") or [] if item.get("title") and item.get("date")]
    for item in activities:
        page = _page_record(item.get("page_url"), item.get("content_sha256"), item.get("retrieved_at"), carried)
        body = {"title": item.get("title"), "url": item.get("url"), "publication_date": item.get("date"), "date_text": item.get("date_text"), "date_kind": item.get("date_kind"), "summary": item.get("summary")}
        span = f"{item.get('method')}: {item.get('date_text') or item.get('date')} {str(item.get('title') or '')[:120]}"
        claims.add("public_activity", "news_item", {key: val for key, val in body.items() if val is not None}, page, span, confidence=confidence, method=str(item.get("method")), extra={"event_date": item.get("date"), "source_page": item.get("page_url")})
    if not activities:
        claims.absent("public_activity", "news_item", "not_available", "Verified website checked; no news or activity item with a date stated on the page found")
    jobs = value.get("jobs") or []
    for job in jobs:
        page = _page_record(job.get("page_url"), job.get("content_sha256"), job.get("retrieved_at"), carried)
        body = {key: job.get(key) for key in ("title", "url", "date_posted", "valid_through", "application_deadline", "location")}
        method = str(job.get("method") or "jsonld_JobPosting")
        span = f"schema.org JobPosting: {job.get('title')}" if method == "jsonld_JobPosting" else f"position listed on careers page {job.get('page_url')}: {job.get('title')}"
        claims.add("hiring", "job_posting", {key: val for key, val in body.items() if val is not None}, page, span, confidence=confidence, method=method, extra={"source_page": job.get("page_url")})
    if not jobs:
        checked = value.get("careers_checked") or []
        reason = f"Verified website checked; careers page {checked[0]['url']}: {checked[0]['reason']}" if checked else "Verified website checked; no job posting found (no schema.org JobPosting, no careers page listing positions)"
        claims.absent("hiring", "job_posting", "not_available", reason)
    return True


# Optional LLM layer (llm/): fact_type -> (category, field). Only present when that layer ran.
LLM_FACT_FIELDS = {
    "business_description": ("description", "website_business_description"),
    "product_or_service": ("description", "website_product_or_service"),
    "certification": ("description", "website_certification"),
    "person_role": ("leadership", "website_named_role"),
    "office_location": ("locations", "website_office_location"),
    "contact_email": ("identity", "website_contact_email"),
    "contact_phone": ("identity", "website_contact_phone"),
    "founded_year": ("identity", "website_founded_year_statement"),
    "employee_count_statement": ("identity", "website_employee_count_statement"),
}


def _llm_claims(claims: ClaimSet, llm: dict[str, Any] | None) -> None:
    """Claims the LLM layer extracted and the validators accepted. The cited source is always the captured
    page (url, retrieval time, sha256) and the span is quoted verbatim from it: the model is never a source."""
    extraction = (llm or {}).get("extraction") or {}
    if not extraction:
        return
    base = {"derivation": "llm_extraction", "llm_model": llm.get("model")}
    for fact in extraction.get("facts") or []:
        category, field = LLM_FACT_FIELDS[fact["fact_type"]]
        extra = {**base, "fact_type": fact["fact_type"], "evidence_span": fact["evidence_span"]}
        for key in ("date_if_explicit", "role_normalization", "corroborating_spans"):
            if fact.get(key):
                extra[key] = fact[key]
        page = _page_record(fact["source_url"], fact["content_sha256"], fact["retrieved_at"])
        claims.add(category, field, fact["value"], page, fact["evidence_span"], confidence=fact["confidence"], method="llm_extraction_validated", extra=extra)
    for item in extraction.get("profiles") or []:
        page = _page_record(item["source_page"], item["content_sha256"], item["retrieved_at"])
        claims.add("public_activity", "social_profile", item["profile_url"], page, item["evidence_span"], confidence=min(0.8, float(item.get("identity_score") or 0.8)), method="llm_extracted_site_link", extra={**base, "platform": item["platform"], "evidence_span": item["evidence_span"]})
    for item in extraction.get("activities") or []:
        page = _page_record(item["source_url"], item["content_sha256"], item["retrieved_at"])
        body = {"title": item["title"], "publication_date": item["publication_date"], "date_kind": "stated_on_page", "summary": item.get("summary")}
        claims.add("public_activity", "news_item", {key: val for key, val in body.items() if val is not None}, page, item["evidence_span"], confidence=0.8, method="llm_extraction_validated", extra={**base, "evidence_span": item["evidence_span"], "event_date": item["publication_date"]})
    # An available LLM claim supersedes the deterministic "checked, nothing found" state for the same field.
    filled = {(item["category"], item["field"]) for item in claims.claims if item.get("derivation") == "llm_extraction"}
    claims.claims = [item for item in claims.claims if item["availability"] == "available" or (item["category"], item["field"]) not in filled]


def claims_from_profile(profile: dict[str, Any], *, snapshot_root: Path | None = None) -> ClaimSet:
    claims = ClaimSet(snapshot_root=snapshot_root)
    records = profile.get("evidence", {})
    view = _identity_claims(claims, profile)
    _financial_claims(claims, records.get("financials"))
    _history_claims(claims, records.get("financial_history"))
    _role_claims(claims, records.get("roles"))
    _location_claims(claims, records.get("locations"))
    _group_claims(claims, records.get("group"))
    website = records.get("website") or {}
    v1_published = website.get("status") == "available" and bool(((website.get("value") or {}).get("identity_assessment") or {}).get("publishable"))
    site_verified = _site_research_claims(claims, records.get("site_research"), v1_site_published=v1_published)
    _website_claims(claims, records.get("website"), view, site_verified=site_verified and not v1_published)
    if profile.get("llm"):
        _llm_claims(claims, profile["llm"])
    return claims


def category_coverage(claims: list[dict[str, Any]]) -> dict[str, str]:
    """Per category: `available` if any substantive fact is available, else the most informative state.

    A checked-and-empty count (`role_count: 0`) is a real claim but is not coverage.
    """
    order = ("available", "ambiguous", "blocked", "failed", "not_available", "not_applicable")
    coverage = {}
    for category in CATEGORIES:
        states = {
            "not_available" if item["field"].endswith("_count") and item.get("value") == 0 else item["availability"]
            for item in claims
            if item.get("category") == category
        }
        coverage[category] = next((state for state in order if state in states), "not_checked")
    return coverage


AREAS = ("filings", "leadership", "locations", "websites", "public_footprint", "hiring")


def area_coverage(claims: list[dict[str, Any]]) -> dict[str, bool]:
    """Builderr's five areas plus hiring split out. public_footprint = site-linked social profile or dated site
    activity, both `public_activity` claims (official sample's footprint logic counts profiles)."""
    available = [item for item in claims if item.get("availability") == "available"]
    has = lambda category, fields=None: any(item.get("category") == category and (fields is None or item["field"] in fields) and not (item["field"].endswith("_count") and item.get("value") == 0) for item in available)  # noqa: E731
    return {
        "filings": has("filings"),
        "leadership": has("leadership"),
        "locations": has("locations"),
        "websites": has("websites", {"official_website"}),
        "public_footprint": has("public_activity"),
        "hiring": has("hiring"),
    }
