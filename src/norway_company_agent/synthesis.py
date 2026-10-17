"""Deterministic company summary, built only from an envelope's verified claims.

No LLM and no free text from a model: every statement comes from a fixed template filled with claim values
and cites the claims (`claim_keys`) and evidence entries (`evidence_ids`) it uses. Source text (registered
activity, website description) is quoted verbatim, not translated or paraphrased. The same claims always give
the same summary (no timestamps, stable ordering).

Unknowns keep the distinction the contract makes: `not_available` = checked, nothing found;
`failed`/`blocked` = could not be checked; `ambiguous` = found, but not confirmed as this company.

Conclusions are limited to what the cited claims support: a missing count is unknown (never zero); "most recent"
means the newest period that has figures, checked against the registry's own last-submitted year; a change is
stated only against a supported earlier observation (a previous run, or the immediately preceding reporting
period when the two are comparable), metric by metric, with both values cited and no trend or growth wording.
"""
from __future__ import annotations

from datetime import date
from typing import Any

SUMMARY_METHOD = "deterministic_template_v2"

SECTIONS = (
    ("at_a_glance", "At a glance"),
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
COMPARED_FIELDS = ("revenue", "operating_result", "net_result", "equity")

# English descriptions of the organisation-form codes (Brønnøysund's own English terms where it has them).
LEGAL_FORMS_EN = {
    "AS": "private limited company", "ASA": "public limited company", "ENK": "sole proprietorship", "NUF": "Norwegian-registered foreign business",
    "DA": "partnership with shared liability", "ANS": "general partnership", "SA": "cooperative", "STI": "foundation", "FLI": "association",
    "BRL": "housing cooperative", "KS": "limited partnership", "SAM": "co-ownership", "ESEK": "condominium (owner-section co-ownership)",
    "IKS": "inter-municipal company", "KF": "municipal enterprise", "SF": "state enterprise", "BA": "company with limited liability",
    "SPA": "savings bank", "GFS": "mutual insurance company", "KOMM": "municipality", "FKF": "county municipal enterprise",
}

# What a non-available field means, in words a reader can act on.
FIELD_LABELS = {
    "official_website": "a verified company website", "social_profile": "social profiles linked from a verified website",
    "news_item": "dated news or activity on a verified website", "job_posting": "job postings", "group_structure": "a registered group structure (konsernstruktur)",
    "annual_accounts": "annual-account figures", "filed_account_years": "the list of filed account years", "roles": "registered roles",
    "subunits": "registered subunits", "legal_name": "the registry identity", "business_address": "a business address",
    "registered_activity": "a registered activity or purpose text", "registry_employee_count": "the employee count (not published in the registry; unknown, not zero)",
}

AREA_LABELS = {
    "filings": "annual accounts", "leadership": "registered roles", "locations": "addresses and subunits",
    "websites": "a verified website", "public_footprint": "public profiles or dated website activity", "hiring": "job postings",
}

MAX_LISTED = 10

SECTION_CATEGORIES = {
    "at_a_glance": {"identity"},
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
    if len(text) <= limit:
        return f"“{text}”"
    return f"“{text[:limit].rsplit(' ', 1)[0].rstrip(',;:')}…”"


def _reason(claim: dict[str, Any]) -> str:
    """The recorded reason of a non-available claim, as a sentence."""
    text = " ".join(str(claim.get("reason") or "").split())
    if not text:
        return ""
    return f"Source note: {text}" + ("" if text.endswith(".") else ".")


def _job(value: dict[str, Any]) -> str:
    details = [f"posted {value['date_posted']}" if value.get("date_posted") else "posting date not stated"]
    if value.get("application_deadline"):
        details.append(f"application deadline {value['application_deadline']}")
    if value.get("location"):
        details.append(str(value["location"]))
    return f"{value.get('title')} ({', '.join(details)})"


def _platform(claim: dict[str, Any]) -> str:
    value = claim.get("value")
    return str(claim.get("platform") or (value.get("platform") if isinstance(value, dict) else "") or "")


def _profile_url(claim: dict[str, Any]) -> str:
    value = claim.get("value")
    return str(value.get("url") if isinstance(value, dict) else value)


def _join(names: list[str]) -> str:
    shown = names[:MAX_LISTED]
    more = len(names) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more else "")


# ---------- reporting periods ----------

def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _period_of(claim: dict[str, Any]) -> tuple[str, str]:
    period = claim.get("period") if isinstance(claim.get("period"), dict) else {}
    return str(period.get("from") or ""), str(period.get("to") or "")


def _full_year(period: tuple[str, str]) -> bool:
    start, end = _day(period[0]), _day(period[1])
    return bool(start and end) and 360 <= (end - start).days + 1 <= 372


def _not_comparable(earlier: tuple[str, str], later: tuple[str, str], currencies: set[str]) -> str | None:
    """Why two reporting periods cannot be compared, or None. Only consecutive twelve-month periods in one
    currency are compared: a short first year, a changed financial year or a gap would make any change an artefact."""
    if len(currencies) != 1:
        return "they are reported in different currencies"
    if not (_full_year(earlier) and _full_year(later)):
        return "they are not both twelve-month periods"
    start, end = _day(later[0]), _day(earlier[1])
    if not (start and end) or (start - end).days != 1:
        return "they are not consecutive"
    return None


def _figures_by_period(claims: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, dict[str, Any]]], list[tuple[tuple[str, str], str]]]:
    """{period: {field: claim}} for one account type, plus (period, field) pairs the register states twice with
    different values: contradictory evidence is reported as unknown, never resolved by picking one."""
    found: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for claim in claims:
        period = _period_of(claim)
        if period[1]:  # a figure without a stated period end is never "most recent"
            found.setdefault(period, {}).setdefault(claim["field"], []).append(claim)
    figures: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    conflicts = []
    for period, fields in found.items():
        figures[period] = {}
        for field, items in fields.items():
            if len({repr(item.get("value")) for item in items}) > 1 or len({str(item.get("currency")) for item in items}) > 1:
                conflicts.append((period, field))
            else:
                figures[period][field] = items[0]
    return figures, conflicts


def _direction(before: Any, after: Any) -> str:
    return "higher" if after > before else "lower" if after < before else "unchanged"


def latest_financials(claims: list[dict[str, Any]]) -> tuple[str, tuple[str, str], dict[str, dict[str, Any]]] | None:
    """(account type, most recent period, {field: claim}) of the primary account type (company accounts first), from
    available figure claims; contradictory figures are left out. The viewer uses the same selection as the summary."""
    figures = [claim for claim in claims if claim.get("availability") == "available" and claim.get("field") in dict(FINANCIAL_FIELDS)]
    for account_type in sorted({str(claim.get("account_type") or "") for claim in figures}, key=lambda kind: (kind != "SELSKAP", kind)):
        by_period, _ = _figures_by_period([claim for claim in figures if str(claim.get("account_type") or "") == account_type])
        periods = sorted((period for period, fields in by_period.items() if fields), key=lambda period: (period[1], period[0]), reverse=True)
        if periods:
            return account_type, periods[0], by_period[periods[0]]
    return None


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
    no_count = next((claim for claim in claims if claim.get("field") == "registry_employee_count" and claim.get("availability") != "available"), None)
    if employees:
        out.say("key_company_facts", f"Employees reported to the registry: {employees['value']}.", [employees])
    elif no_count:
        # Unknown is not zero: the registry publishes no count (and may say none is registered).
        out.say("key_company_facts", f"Employee count: not published. {_reason(no_count)}", [no_count])
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

    # 5. Financial snapshot: the most recent reporting period with figures, per account type, with period and
    # currency; checked against the registry's own last-submitted year so an older year is never called latest.
    latest_year = one("latest_filed_accounts_year")
    figures = [claim for field, _ in FINANCIAL_FIELDS for claim in by_field.get(field) or []]
    snapshots: dict[str, tuple[dict[tuple[str, str], dict[str, dict[str, Any]]], list[tuple[str, str]]]] = {}
    conflicts: list[tuple[str, tuple[str, str], str]] = []
    for account_type in sorted({str(claim.get("account_type") or "") for claim in figures}, key=lambda kind: (kind != "SELSKAP", kind)):
        by_period, contradictory = _figures_by_period([claim for claim in figures if str(claim.get("account_type") or "") == account_type])
        conflicts += [(account_type, period, field) for period, field in contradictory]
        periods = sorted((period for period, fields in by_period.items() if fields), key=lambda period: (period[1], period[0]), reverse=True)
        if periods:
            snapshots[account_type] = (by_period, periods)
    newest_end = max((periods[0][1] for _, periods in snapshots.values()), default="")
    newest = next((next(iter(by_period[periods[0]].values())) for by_period, periods in snapshots.values() if periods[0][1] == newest_end), None)
    if latest_year and newest_end:
        registered, with_figures = str(latest_year["value"]), newest_end[:4]
        if registered == with_figures:
            out.say("financial_snapshot", f"Latest annual accounts: {registered}, the year Enhetsregisteret records as last submitted; the most recent figures below are for that year.", [latest_year])
        elif registered > with_figures:
            out.say("financial_snapshot", f"Enhetsregisteret records annual accounts submitted for {registered}, but the accounts register returned figures only up to the period ending {newest_end}; {registered} figures are not reported here.", [latest_year, newest])
        else:
            out.say("financial_snapshot", f"The registry record still names {registered} as the last submitted accounts year, but the accounts register holds figures for the newer period ending {newest_end}; that newer period is used below.", [latest_year, newest])
    elif latest_year:
        out.say("financial_snapshot", f"Enhetsregisteret records {latest_year['value']} as the last submitted annual accounts year; no figures were returned by the accounts register in this run.", [latest_year])
    comparisons: list[tuple[str, list[dict[str, Any]]]] = []
    for account_type, (by_period, periods) in snapshots.items():
        label = ACCOUNT_TYPES.get(account_type, account_type.lower() or "accounts")
        latest = by_period[periods[0]]
        used = [latest[field] for field, _ in FINANCIAL_FIELDS if field in latest]
        parts = [f"{field_label.lower() if index else field_label} {_amount(latest[field]['value'], latest[field].get('currency'))}"
                 for index, (field, field_label) in enumerate((item for item in FINANCIAL_FIELDS if item[0] in latest))]
        earlier = periods[1:]
        suffix = f" Earlier reporting period{'s' if len(earlier) != 1 else ''} with figures in the accounts register: {'; '.join(f'{start} to {end}' for start, end in earlier)}." if earlier else ""
        # Each earlier period is cited by one of its own figures.
        out.say("financial_snapshot", f"Most recent figures in the accounts register ({label}), reporting period {periods[0][0]} to {periods[0][1]}: {'; '.join(parts)}.{suffix}",
                used + [next(iter(by_period[period].values())) for period in earlier])
        if earlier:
            # A change is stated only against the immediately preceding period, metric by metric, when comparable.
            before = by_period[earlier[0]]
            currencies = {str(claim.get("currency")) for claim in [*before.values(), *latest.values()]}
            why_not = _not_comparable(earlier[0], periods[0], currencies)
            if why_not:
                comparisons.append((f"The {label} for {periods[0][0]} to {periods[0][1]} are not compared with {earlier[0][0]} to {earlier[0][1]}: {why_not}, so no change is inferred.",
                                    [next(iter(latest.values())), next(iter(before.values()))]))
                continue
            moves, cited = [], []
            for field in COMPARED_FIELDS:
                if field in before and field in latest:
                    old, new = before[field]["value"], latest[field]["value"]
                    field_label = dict(FINANCIAL_FIELDS)[field]
                    moves.append(f"{field_label.lower()} {_direction(old, new)} ({_amount(old, before[field].get('currency'))} to {_amount(new, latest[field].get('currency'))})")
                    cited += [before[field], latest[field]]
            if moves:
                comparisons.append((f"Compared with the preceding reporting period ({earlier[0][0]} to {earlier[0][1]}), the {label} for {periods[0][0]} to {periods[0][1]} show: {'; '.join(moves)}.", cited))

    # 6. Website and public footprint
    website = one("official_website")
    if website:
        via = f" ({website['identity_class']})" if website.get("identity_class") else ""
        operator = website.get("operated_by")
        if operator:
            out.say("public_footprint", f"Website named in the registry record and operated by the registered business manager {operator['name']} (organisation number {operator['organisation_number']}): {website['value']}.", [website])
        else:
            out.say("public_footprint", f"Verified company website{via}: {website['value']}.", [website])
    listed_site = one("registry_listed_website")
    if listed_site and not website:
        out.say("public_footprint", f"The registry lists the website {listed_site['value']}; it was not verified as this company's own site.", [listed_site])
    profiles = sorted(by_field.get("social_profile") or [], key=lambda claim: (_platform(claim), _profile_url(claim)))
    if profiles:
        linked = _join([f"{_platform(claim)} {_profile_url(claim)}" for claim in profiles])
        out.say("public_footprint", f"Profiles linked from the verified website: {linked}.", profiles)
    careers = one("careers_page")
    if careers:
        out.say("public_footprint", f"Careers page: {careers['value']}.", [careers])
    activity = sorted((by_field.get("news_item") or []) + (by_field.get("site_activity") or []), key=lambda claim: (str(claim["value"].get("publication_date") or ""), str(claim["value"].get("url") or "")), reverse=True)
    if activity:
        newest = activity[0]["value"]
        out.say("public_footprint", f"{len(activity)} dated item{'s' if len(activity) != 1 else ''} on the verified website; the most recent is dated {str(newest.get('publication_date') or '')[:10]}: {_quote(newest.get('title') or newest.get('url'), 160)}.", activity)
    jobs = sorted(by_field.get("job_posting") or [], key=lambda claim: (str(claim["value"].get("date_posted") or ""), str(claim["value"].get("title") or "")), reverse=True)
    if jobs:
        postings = _join([_job(claim["value"]) for claim in jobs])
        out.say("public_footprint", f"Job postings on the verified website ({len(jobs)}): {postings}.", jobs)

    # 7. What changed: only against a supported earlier observation (a previous run of this agent, the preceding
    # reporting period in the accounts register, or a dated change the registry itself records).
    refresh = envelope.get("refresh") or {}
    changes = envelope.get("changes") or []
    for text, cited in comparisons:
        out.say("what_changed", text, cited)
    roles_changed = one("roles_last_changed")
    if roles_changed:
        out.say("what_changed", f"Enhetsregisteret's roles register records its most recent change to the registered roles on {roles_changed['value']}; it does not say what changed.", [roles_changed])
    if not refresh.get("compared"):
        if comparisons or roles_changed:
            out.say("what_changed", "No previous run was supplied, so changes since an earlier observation by this agent are not assessed.")
        else:
            out.say("what_changed", "Not assessed: no previous run was supplied and the sources hold no earlier observation to compare with, so no change is reported.")
    else:
        counts = refresh.get("counts") or {}
        material = [item for item in changes if item.get("change_type") in {"added", "removed", "changed", "unverified"}]
        if not material:
            out.say("what_changed", f"No changes to verified facts since the previous run ({counts.get('unchanged', 0)} facts unchanged).")
        for item in sorted(material, key=lambda item: (item.get("change_type"), item.get("category"), item.get("field"))):
            # The current fact is cited when it is in this envelope; the earlier one is in the change event's previous_evidence.
            now = (item.get("evidence") or {}).get("evidence_id")
            out.say("what_changed", _change_text(item), [claim for claim in available if now and now in (claim.get("evidence_ids") or []) and claim["field"] == item.get("field")][:1])
        for item in [item for item in changes if item.get("change_type") == "unavailable"]:
            retained = ", ".join(item.get("fields_retained") or []) or "no facts"
            out.say("what_changed", f"Source {item.get('module')} could not be checked in this run ({(item.get('current_attempt') or {}).get('status')}); values last verified {str(item.get('last_verified_at') or '')[:10]} are retained: {retained}.")

    # 8. What remains unknown: every statement cites the non-available claims it reports.
    checked_none, not_checked, unconfirmed, not_applicable = [], [], [], []
    for claim in sorted((claim for claim in claims if claim.get("availability") != "available"), key=lambda claim: (claim["category"], claim["field"])):
        if any(item["category"] == claim["category"] and item["field"] == claim["field"] for item in available):
            continue
        state = claim.get("availability")
        if state == "not_available":
            checked_none.append(claim)
        elif state in {"failed", "blocked"}:
            not_checked.append(claim)
        elif state == "ambiguous":
            unconfirmed.append(claim)
        elif state == "not_applicable":
            not_applicable.append(claim)
    label = lambda claim: FIELD_LABELS.get(claim["field"], claim["field"].replace("_", " "))  # noqa: E731
    if checked_none:
        out.say("what_remains_unknown", f"Checked, nothing found: {', '.join(label(claim) for claim in checked_none)}.", checked_none)
    if not_checked:
        listed = ", ".join(f"{label(claim)} ({claim['availability']})" for claim in not_checked)
        out.say("what_remains_unknown", f"Could not be checked in this run (the source failed or was blocked): {listed}.", not_checked)
    if unconfirmed:
        out.say("what_remains_unknown", f"Found but not confirmed as this company, so not reported: {', '.join(label(claim) for claim in unconfirmed)}.", unconfirmed)
    for claim in not_applicable:
        out.say("what_remains_unknown", f"Not attributed to this company: {label(claim)}. {_reason(claim)}", [claim])
    for account_type, period, field in conflicts:
        out.say("what_remains_unknown", f"The accounts register states two different values for {dict(FINANCIAL_FIELDS)[field].lower()} ({ACCOUNT_TYPES.get(account_type, account_type.lower() or 'accounts')}, {period[0]} to {period[1]}); neither is reported.",
                [claim for claim in figures if claim["field"] == field and _period_of(claim) == period and str(claim.get("account_type") or "") == account_type])
    if latest_year and newest_end and str(latest_year["value"]) > newest_end[:4]:
        out.say("what_remains_unknown", f"Figures for the {latest_year['value']} annual accounts, which Enhetsregisteret records as submitted, were not in the accounts register's response.", [latest_year, newest])
    carried = [claim for claim in available if claim.get("carried_forward")]
    if carried:
        out.say("what_remains_unknown", f"Retained from an earlier run because the source failed now (not re-verified): {', '.join(sorted({claim['field'].replace('_', ' ') for claim in carried}))}.", carried)
    if not out.items["what_remains_unknown"]:
        out.say("what_remains_unknown", "No checked category was left without an answer.")

    # 0. At a glance: the decision-relevant facts above in a few cited sentences (no new facts).
    if legal_name:
        form_code = form["value"] if form else None
        english = LEGAL_FORMS_EN.get(str(form_code))
        kind = f"{'an' if english[0] in 'aeiou' else 'a'} {english} ({form_code})" if english else f"an entity of organisation form {form_code}" if form_code else "an entity"
        address = one("business_address")
        place = (address["value"].get("city") or address["value"].get("municipality")) if address and isinstance(address["value"], dict) else None
        founded = one("founded_date")
        identity_text = f"{legal_name['value']} (organisation number {org['value'] if org else envelope.get('organisation_number')}) is {kind} registered in Enhetsregisteret"
        identity_text += (f", with its business address in {place}" if place else "") + (f", founded {founded['value']}" if founded else "") + "."
        if bankrupt and bankrupt["value"] is True:
            identity_text += " It is registered as bankrupt (konkurs)."
        elif liquidating and liquidating["value"] is True:
            identity_text += " It is registered as under liquidation (under avvikling)."
        out.say("at_a_glance", identity_text, [claim for claim in (legal_name, org, form, address, founded, bankrupt if bankrupt and bankrupt["value"] is True else None, liquidating if liquidating and liquidating["value"] is True else None) if claim])
        activity_claim = one("registered_activity") or one("statutory_purpose")
        if activity_claim or industry:
            parts = []
            if activity_claim:
                parts.append(f"in its registered words, {_quote(activity_claim['value'], 160)}")
            if industry and isinstance(industry["value"], dict):
                parts.append(f"registered industry NACE {industry['value'].get('code')} ({industry['value'].get('description') or 'no label'})")
            out.say("at_a_glance", f"What it does: {'; '.join(parts)}.", [claim for claim in (activity_claim, industry) if claim])
        if snapshots:
            account_type, (by_period, periods) = next(iter(snapshots.items()))
            latest = by_period[periods[0]]
            headline = [f"{dict(FINANCIAL_FIELDS)[field].lower()} {_amount(latest[field]['value'], latest[field].get('currency'))}" for field in ("revenue", "net_result", "equity") if field in latest]
            if headline:
                out.say("at_a_glance", f"Most recent figures ({ACCOUNT_TYPES.get(account_type, account_type.lower() or 'accounts')}, reporting period {periods[0][0]} to {periods[0][1]}): {'; '.join(headline)}.",
                        [latest[field] for field in ("revenue", "net_result", "equity") if field in latest])
        if employees:
            size = (f"Employees reported to the registry: {employees['value']}.", [employees])
        elif no_count:
            size = ("Employee count: unknown (not published in the registry record; not zero).", [no_count])
        else:
            size = None
        if size:
            out.say("at_a_glance", *size)
        if website:
            footprint = [f"verified website {website['value']}"]
            if profiles:
                footprint.append(f"{len(profiles)} linked profile{'s' if len(profiles) != 1 else ''}")
            if activity:
                footprint.append(f"{len(activity)} dated website item{'s' if len(activity) != 1 else ''}, the most recent dated {str(activity[0]['value'].get('publication_date') or '')[:10]}")
            if jobs:
                footprint.append(f"{len(jobs)} job posting{'s' if len(jobs) != 1 else ''}")
            out.say("at_a_glance", f"Public footprint: {'; '.join(footprint)}.", [website, *profiles, *activity[:1], *jobs])
        else:
            unverified = [claim for claim in claims if claim.get("field") == "official_website" and claim.get("availability") != "available"]
            if unverified:
                out.say("at_a_glance", "Public footprint: no company website was verified in this run, so the profile rests on the official registers.", unverified[:1])

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
