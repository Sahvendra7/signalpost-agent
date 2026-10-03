"""Deterministic company summary, built only from an envelope's verified claims.

No LLM and no free text from a model: every statement comes from a fixed template filled with claim values
and cites the claims (`claim_keys`) and evidence entries (`evidence_ids`) it uses. Source text (registered
activity, website description) is quoted verbatim, not translated or paraphrased. The same claims always give
the same summary (no timestamps, stable ordering).

Unknowns keep the distinction the contract makes: `not_available` = checked, nothing found;
`failed`/`blocked` = could not be checked; `ambiguous` = found, but not confirmed as this company.
"""
from __future__ import annotations

from typing import Any

SUMMARY_METHOD = "deterministic_template_v1"

SECTIONS = (
    ("what_the_company_does", "What the company does"),
    ("key_company_facts", "Key company facts"),
    ("leadership", "Leadership"),
    ("locations", "Locations"),
    ("financial_snapshot", "Financial snapshot"),
    ("public_footprint", "Website and public footprint"),
    ("what_changed", "What changed"),
    ("what_remains_unknown", "What remains unknown"),
)

# Enhetsregisteret organisation-form codes (official labels, Norwegian).
LEGAL_FORMS = {
    "AS": "aksjeselskap", "ASA": "allmennaksjeselskap", "ENK": "enkeltpersonforetak", "NUF": "norskregistrert utenlandsk foretak",
    "DA": "selskap med delt ansvar", "ANS": "ansvarlig selskap", "SA": "samvirkeforetak", "STI": "stiftelse", "FLI": "forening/lag/innretning",
    "BRL": "borettslag", "KS": "kommandittselskap", "SAM": "tingsrettslig sameie", "ESEK": "eierseksjonssameie", "IKS": "interkommunalt selskap",
    "KF": "kommunalt foretak", "SF": "statsforetak", "BA": "selskap med begrenset ansvar", "PRE": "partsrederi", "SPA": "sparebank",
    "GFS": "gjensidig forsikringsselskap", "KOMM": "kommune", "FKF": "fylkeskommunalt foretak", "ORGL": "organisasjonsledd", "UTLA": "utenlandsk enhet",
}

ROLE_LABELS = (
    ("ceo", "Chief executive (daglig leder)"),
    ("board_chair", "Board chair (styrets leder)"),
    ("board_deputy_chair", "Deputy board chair (nestleder)"),
    ("board_member", "Board members (styremedlem)"),
    ("board_deputy_member", "Deputy board members (varamedlem)"),
    ("board_observer", "Board observers (observatør)"),
    ("owner", "Owner (innehaver)"),
    ("partner", "Partners (deltaker)"),
    ("general_partner", "General partner (komplementar)"),
    ("business_manager", "Business manager (forretningsfører)"),
    ("contact_person", "Contact person (kontaktperson)"),
    ("procuration", "Procuration (prokura)"),
    ("signatory", "Signature rights (signatur)"),
    ("auditor", "Auditor (revisor)"),
    ("accountant", "Accountant (regnskapsfører)"),
    ("registered_role", "Other registered roles"),
)

FINANCIAL_FIELDS = (
    ("revenue", "Revenue"), ("operating_result", "Operating result"), ("profit_before_tax", "Profit before tax"),
    ("net_result", "Net result"), ("total_assets", "Total assets"), ("equity", "Equity"), ("total_debt", "Total debt"),
)
ACCOUNT_TYPES = {"SELSKAP": "company accounts", "KONSERN": "group accounts"}

AREA_LABELS = {
    "filings": "annual accounts", "leadership": "registered roles", "locations": "addresses and subunits",
    "websites": "a verified website", "public_footprint": "public profiles or dated website activity", "hiring": "job postings",
}

MAX_LISTED = 10

SECTION_CATEGORIES = {
    "what_the_company_does": {"description"},
    "key_company_facts": {"identity", "relationships"},
    "leadership": {"leadership", "registry_activity"},
    "locations": {"locations"},
    "financial_snapshot": {"filings"},
    "public_footprint": {"websites", "public_activity", "hiring"},
}


def _empty_section_text(claims: list[dict[str, Any]], categories: set[str]) -> str:
    states = {claim.get("availability") for claim in claims if claim.get("category") in categories}
    if states & {"failed", "blocked"}:
        return "Could not be checked in this run (source failed or blocked); nothing is reported."
    if "ambiguous" in states:
        return "Candidates were found but not confirmed as this company; nothing is reported."
    if "not_available" in states:
        return "Checked; nothing found in the sources consulted."
    if "not_applicable" in states:
        return "Not applicable to this company."
    return "Not checked in this run."


class _Sections:
    def __init__(self) -> None:
        self.items: dict[str, list[dict[str, Any]]] = {key: [] for key, _ in SECTIONS}

    def say(self, section: str, text: str, claims: list[dict[str, Any]] | None = None) -> None:
        claims = claims or []
        self.items[section].append({
            "text": text,
            "claim_keys": [claim["key"] for claim in claims if claim.get("key")],
            "evidence_ids": sorted({eid for claim in claims for eid in claim.get("evidence_ids") or []}),
            **({"carried_forward": True} if any(claim.get("carried_forward") for claim in claims) else {}),
        })


def _name(value: Any) -> str:
    name = value.get("name") if isinstance(value, dict) else value
    if isinstance(name, list):
        name = " ".join(str(part) for part in name)
    return str(name or "").strip()


def _address(value: dict[str, Any]) -> str:
    parts = [", ".join(str(line) for line in value.get("lines") or [] if line)]
    parts.append(" ".join(str(part) for part in (value.get("postal_code"), value.get("city")) if part))
    if value.get("municipality") and value.get("municipality") != value.get("city"):
        parts.append(f"{value['municipality']} municipality")
    if value.get("country") and value.get("country") not in {"Norge", "Norway"}:
        parts.append(str(value["country"]))
    return ", ".join(part for part in parts if part)


def _amount(value: Any, currency: str | None) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:,.0f}" if number == int(number) else f"{number:,.2f}"
    return f"{currency or ''} {text}".strip()


def _period(period: Any) -> str:
    if isinstance(period, dict) and period.get("from") and period.get("to"):
        return f"{period['from']} to {period['to']}"
    return "unspecified period"


def _quote(text: Any, limit: int = 400) -> str:
    text = " ".join(str(text).split())
    return f"“{text[:limit]}{'…' if len(text) > limit else ''}”"


def _job(value: dict[str, Any]) -> str:
    return f"{value.get('title')} (posted {value.get('date_posted') or 'undated'})"


def _join(names: list[str]) -> str:
    shown = names[:MAX_LISTED]
    more = len(names) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more else "")


def company_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    claims = envelope.get("claims") or []
    available = [claim for claim in claims if claim.get("availability") == "available"]
    by_field: dict[str, list[dict[str, Any]]] = {}
    for claim in available:
        by_field.setdefault(claim["field"], []).append(claim)
    one = lambda field: (by_field.get(field) or [None])[0]  # noqa: E731
    out = _Sections()

    # 1. What the company does
    for field, label in (("registered_activity", "Registered activity (Enhetsregisteret, verbatim)"), ("statutory_purpose", "Statutory purpose (vedtektsfestet formål, verbatim)")):
        claim = one(field)
        if claim:
            out.say("what_the_company_does", f"{label}: {_quote(claim['value'])}", [claim])
    industry = one("industry")
    if industry and isinstance(industry["value"], dict):
        out.say("what_the_company_does", f"Registered industry code (NACE) {industry['value'].get('code')}: {industry['value'].get('description') or 'no label'}.", [industry])
    site_description = one("website_description")
    if site_description:
        out.say("what_the_company_does", f"The company's verified website describes itself as: {_quote(site_description['value'], 300)}", [site_description])

    # 2. Key company facts
    legal_name, org, form = one("legal_name"), one("organisation_number"), one("legal_form")
    if legal_name or org:
        form_text = f", legal form {form['value']}" + (f" ({LEGAL_FORMS[form['value']]})" if form["value"] in LEGAL_FORMS else "") if form else ""
        out.say("key_company_facts", f"{legal_name['value'] if legal_name else 'Name not available'} (organisation number {org['value'] if org else envelope.get('organisation_number')}){form_text}.", [claim for claim in (legal_name, org, form) if claim])
    for field, label in (("founded_date", "Founded"), ("registry_registration_date", "Registered in Enhetsregisteret")):
        claim = one(field)
        if claim:
            out.say("key_company_facts", f"{label}: {claim['value']}.", [claim])
    employees = one("registry_employee_count")
    if employees:
        out.say("key_company_facts", f"Employees reported to the registry: {employees['value']}.", [employees])
    bankrupt, liquidating = one("bankrupt"), one("under_liquidation")
    if bankrupt and bankrupt["value"] is True:
        out.say("key_company_facts", "Registered as bankrupt (konkurs) in Enhetsregisteret.", [bankrupt])
    if liquidating and liquidating["value"] is True:
        out.say("key_company_facts", "Registered as under liquidation (under avvikling) in Enhetsregisteret.", [liquidating])
    if bankrupt and liquidating and bankrupt["value"] is False and liquidating["value"] is False:
        out.say("key_company_facts", "Not registered as bankrupt or under liquidation in Enhetsregisteret.", [bankrupt, liquidating])
    group = one("group_structure")
    if group and isinstance(group["value"], dict):
        value = group["value"]
        related = len(value.get("children") or [])
        if str(value.get("organisasjonsnummer")) == str(envelope.get("organisation_number")):
            text = f"Registered group structure (konsernstruktur): this company is the top entity, with {related} related companies listed."
        else:
            text = f"Registered group structure (konsernstruktur): part of a group whose top entity is {value.get('navn')} (organisation number {value.get('organisasjonsnummer')}); {related} related companies listed."
        out.say("key_company_facts", text, [group])

    # 3. Leadership
    for field, label in ROLE_LABELS:
        holders = sorted(by_field.get(field) or [], key=lambda claim: _name(claim["value"]))
        if holders:
            names = [_name(claim["value"]) + (f" (organisation number {claim['value']['organisation_number']})" if isinstance(claim["value"], dict) and claim["value"].get("organisation_number") else "") for claim in holders]
            out.say("leadership", f"{label}: {_join(names)}.", holders)
    role_count = one("role_count")
    if role_count and role_count["value"] == 0:
        out.say("leadership", "The roles register (Enhetsregisteret roller) lists no registered roles.", [role_count])
    changed = one("roles_last_changed")
    if changed:
        out.say("leadership", f"Registered roles last changed: {changed['value']}.", [changed])

    # 4. Locations
    for field, label in (("business_address", "Business address"), ("postal_address", "Postal address")):
        claim = one(field)
        if claim and isinstance(claim["value"], dict):
            out.say("locations", f"{label}: {_address(claim['value'])}.", [claim])
    subunits = sorted(by_field.get("subunit") or [], key=lambda claim: str((claim["value"] or {}).get("organisation_number")))
    count = one("subunit_count")
    if subunits:
        listed = [f"{(claim['value'] or {}).get('name')} (organisation number {(claim['value'] or {}).get('organisation_number')})" + (f", {_address(claim['value']['address'])}" if isinstance((claim["value"] or {}).get("address"), dict) else "") for claim in subunits]
        out.say("locations", f"Registered subunits ({len(subunits)}): {_join(listed)}.", subunits + ([count] if count else []))
    elif count and count["value"] == 0:
        out.say("locations", "No registered subunits (underenheter).", [count])

    # 5. Financial snapshot: the latest reporting period per account type, with period and currency.
    latest_year = one("latest_filed_accounts_year")
    if latest_year:
        out.say("financial_snapshot", f"Latest annual accounts year registered: {latest_year['value']}.", [latest_year])
    figures = [claim for field, _ in FINANCIAL_FIELDS for claim in by_field.get(field) or []]
    for account_type in sorted({str(claim.get("account_type") or "") for claim in figures}, key=lambda kind: (kind != "SELSKAP", kind)):
        typed = [claim for claim in figures if str(claim.get("account_type") or "") == account_type]
        periods = sorted({(claim.get("period") or {}).get("to") or "" for claim in typed}, reverse=True)
        latest = [claim for claim in typed if ((claim.get("period") or {}).get("to") or "") == periods[0]]
        label = ACCOUNT_TYPES.get(account_type, account_type.lower() or "accounts")
        parts = []
        used = []
        for field, field_label in FINANCIAL_FIELDS:
            claim = next((item for item in latest if item["field"] == field), None)
            if claim:
                parts.append(f"{field_label.lower() if parts else field_label} {_amount(claim['value'], claim.get('currency'))}")
                used.append(claim)
        if parts:
            earlier = len(periods) - 1
            suffix = f" Figures for {earlier} earlier reporting period{'s' if earlier != 1 else ''} are also in the accounts register." if earlier > 0 else ""
            out.say("financial_snapshot", f"Annual accounts ({label}), reporting period {_period(used[0].get('period'))}: {'; '.join(parts)}.{suffix}", used)

    # 6. Website and public footprint
    website = one("official_website")
    if website:
        via = f" ({website['identity_class']})" if website.get("identity_class") else ""
        out.say("public_footprint", f"Verified company website{via}: {website['value']}.", [website])
    listed_site = one("registry_listed_website")
    if listed_site and not website:
        out.say("public_footprint", f"The registry lists the website {listed_site['value']}; it was not verified as this company's own site.", [listed_site])
    profiles = sorted(by_field.get("social_profile") or [], key=lambda claim: (claim["value"].get("platform"), claim["value"].get("url")))
    if profiles:
        linked = _join([f"{claim['value']['platform']} {claim['value']['url']}" for claim in profiles])
        out.say("public_footprint", f"Profiles linked from the verified website: {linked}.", profiles)
    careers = one("careers_page")
    if careers:
        out.say("public_footprint", f"Careers page: {careers['value']}.", [careers])
    activity = sorted(by_field.get("site_activity") or [], key=lambda claim: (str(claim["value"].get("publication_date") or ""), str(claim["value"].get("url") or "")), reverse=True)
    if activity:
        newest = activity[0]["value"]
        out.say("public_footprint", f"{len(activity)} dated item{'s' if len(activity) != 1 else ''} on the verified website; the most recent is dated {str(newest.get('publication_date') or '')[:10]}: {_quote(newest.get('title') or newest.get('url'), 160)}.", activity)
    jobs = sorted(by_field.get("job_posting") or [], key=lambda claim: (str(claim["value"].get("date_posted") or ""), str(claim["value"].get("title") or "")), reverse=True)
    if jobs:
        postings = _join([_job(claim["value"]) for claim in jobs])
        out.say("public_footprint", f"Job postings on the verified website ({len(jobs)}): {postings}.", jobs)

    # 7. What changed
    refresh = envelope.get("refresh") or {}
    changes = envelope.get("changes") or []
    if not refresh.get("compared"):
        out.say("what_changed", "Not assessed: no previous run was supplied for this company.")
    else:
        counts = refresh.get("counts") or {}
        material = [item for item in changes if item.get("change_type") in {"added", "removed", "changed", "unverified"}]
        if not material:
            out.say("what_changed", f"No changes to verified facts since the previous run ({counts.get('unchanged', 0)} facts unchanged).")
        for item in sorted(material, key=lambda item: (item.get("change_type"), item.get("category"), item.get("field"))):
            out.say("what_changed", _change_text(item))
        for item in [item for item in changes if item.get("change_type") == "unavailable"]:
            retained = ", ".join(item.get("fields_retained") or []) or "no facts"
            out.say("what_changed", f"Source {item.get('module')} could not be checked in this run ({(item.get('current_attempt') or {}).get('status')}); values last verified {str(item.get('last_verified_at') or '')[:10]} are retained: {retained}.")

    # 8. What remains unknown
    checked_none, not_checked, unconfirmed = [], [], []
    for claim in sorted((claim for claim in claims if claim.get("availability") != "available"), key=lambda claim: (claim["category"], claim["field"])):
        if any(item["category"] == claim["category"] and item["field"] == claim["field"] for item in available):
            continue
        label = claim["field"].replace("_", " ")
        state = claim.get("availability")
        if state == "not_available":
            checked_none.append(label)
        elif state in {"failed", "blocked"}:
            not_checked.append(f"{label} ({state})")
        elif state == "ambiguous":
            unconfirmed.append(label)
    if checked_none:
        out.say("what_remains_unknown", f"Checked, nothing found: {', '.join(checked_none)}.")
    if not_checked:
        out.say("what_remains_unknown", f"Could not be checked in this run: {', '.join(not_checked)}.")
    if unconfirmed:
        out.say("what_remains_unknown", f"Found but not confirmed as this company, so not reported: {', '.join(unconfirmed)}.")
    carried = sorted({claim["field"].replace("_", " ") for claim in available if claim.get("carried_forward")})
    if carried:
        out.say("what_remains_unknown", f"Retained from an earlier run because the source failed now (not re-verified): {', '.join(carried)}.")
    if not (checked_none or not_checked or unconfirmed or carried):
        out.say("what_remains_unknown", "No checked category was left without an answer.")

    # Sparse: nothing verified beyond the official registers (no website, public profile, activity or job).
    coverage = envelope.get("area_coverage") or {}
    found = [AREA_LABELS[area] for area in AREA_LABELS if coverage.get(area)]
    sparse = not legal_name or not any(coverage.get(area) for area in ("websites", "public_footprint", "hiring"))
    overview = None
    state = (envelope.get("company_status") or {}).get("state")
    if not legal_name and state == "not_researched":
        overview = "Not researched: the batch stopped (deadline or interruption) before this company's registry record was fetched; nothing is reported about it."
    elif not legal_name and state == "invalid_input":
        overview = "Not researched: the input row has no usable organisation number."
    elif not legal_name:
        overview = "No verified registry identity was found for this organisation number; nothing is reported about it."
    elif sparse:
        overview = "Public information found was limited to official registry records: " + ", ".join(["registry identity"] + found) + "."
    sections = []
    for key, title in SECTIONS:
        statements = out.items[key]
        if not statements and key in SECTION_CATEGORIES:
            statements = [{"text": _empty_section_text(claims, SECTION_CATEGORIES[key]), "claim_keys": [], "evidence_ids": []}]
        sections.append({"id": key, "title": title, "statements": statements})
    text_lines = ([overview, ""] if overview else [])
    for section in sections:
        text_lines.append(section["title"])
        text_lines.extend(f"- {statement['text']}" for statement in section["statements"])
        text_lines.append("")
    return {
        "method": SUMMARY_METHOD,
        "language": "en",
        "llm_used": False,
        "sparse": sparse,
        "overview": overview,
        "sections": sections,
        "text": "\n".join(text_lines).strip() + "\n",
    }


def _change_text(item: dict[str, Any]) -> str:
    field = str(item.get("field") or "").replace("_", " ")
    period = f" ({_period(item['period'])})" if item.get("period") else ""
    render = lambda value: _name(value) if isinstance(value, dict) and "name" in value else value.get("url") if isinstance(value, dict) and value.get("url") else value  # noqa: E731
    kind = item.get("change_type")
    if kind == "changed":
        return f"Changed: {field}{period} from {render(item.get('old_value'))} to {render(item.get('new_value'))}."
    if kind == "added":
        return f"Added: {field}{period}: {render(item.get('new_value'))}."
    if kind == "removed":
        return f"No longer listed: {field}{period}: {render(item.get('old_value'))}."
    return f"No longer verified (website identity not confirmed): {field}: {render(item.get('old_value'))}."
