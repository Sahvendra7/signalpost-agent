"""Static, self-contained HTML viewer for a batch of envelopes.

One HTML file, no framework, no network: data is embedded as JSON, rendered with vanilla JS through
textContent (never innerHTML), so text captured from the web cannot inject markup. Links are only
emitted for http(s) source URLs. Every fact shows FACT -> SOURCE -> DATE.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .synthesis import ACCOUNT_TYPES, LEGAL_FORMS_EN, latest_financials

VALUE_LIMIT = 400
SPAN_LIMIT = 160

# Rows of the side-by-side comparison: (id, label). Each cell is [text, evidence row or -1].
COMPARE_ROWS = (
    ("legal_form", "Legal form"), ("registry_status", "Registry status"), ("founded", "Founded"), ("place", "Business address"),
    ("industry", "Industry (NACE)"), ("employees", "Employees (registry)"), ("accounts", "Most recent accounts"),
    ("revenue", "Revenue"), ("operating_result", "Operating result"), ("net_result", "Net result"), ("equity", "Equity"),
    ("ceo", "Chief executive"), ("board_chair", "Board chair"), ("website", "Verified website"), ("profiles", "Linked profiles"),
    ("news", "Dated website items"), ("jobs", "Job postings"), ("unknowns", "Unknown or unconfirmed"),
)


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, dict) and "name" in value and isinstance(value.get("name"), (str, list)):
        name = value["name"] if isinstance(value["name"], str) else " ".join(map(str, value["name"]))
        extra = value.get("role") or ""
        text = f"{name}" + (f" — {extra}" if extra else "") + (f" (org. {value['organisation_number']})" if value.get("organisation_number") else "")
    elif isinstance(value, dict) and value.get("lines") is not None:
        text = ", ".join([", ".join(map(str, value.get("lines") or [])), " ".join(str(part) for part in (value.get("postal_code"), value.get("city")) if part)])
    elif isinstance(value, dict) and "children" in value:
        text = f"group top entity {value.get('navn')} ({value.get('organisasjonsnummer')}), {len(value.get('children') or [])} related companies"
    elif isinstance(value, dict) and set(value) == {"code", "description"}:
        text = f"{value.get('code')} {value.get('description') or ''}".strip()
    elif isinstance(value, dict) and value.get("url") and value.get("platform"):
        text = f"{value['platform']}: {value['url']}"
    elif isinstance(value, dict) and value.get("title"):
        stated = value.get("publication_date") or value.get("date_posted")
        details = [str(value[key]) for key in ("location",) if value.get(key)]
        if value.get("application_deadline"):
            details.append(f"deadline {value['application_deadline']}")
        text = (f"{str(stated)[:10]} — " if stated else "") + str(value["title"]) + (f" ({', '.join(details)})" if details else "") + (f" — {value['url']}" if value.get("url") else "")
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text if len(text) <= VALUE_LIMIT else text[:VALUE_LIMIT] + "…"


def _period(claim: dict[str, Any]) -> str:
    period = claim.get("period")
    parts = []
    if isinstance(period, dict) and period.get("from"):
        parts.append(f"{period.get('from')}–{period.get('to')}")
    for key in ("account_type", "currency"):
        if claim.get(key):
            parts.append(str(claim[key]))
    return " ".join(parts)


def _compare_cells(envelope: dict[str, Any], identity: dict[str, Any], evidence_row: dict[str, int]) -> list[list[Any]]:
    """One comparison column for this company, aligned with COMPARE_ROWS. Values come from available claims only; a
    missing value says why (unknown is not zero, not checked is not none)."""
    claims = envelope.get("claims") or []
    available = [claim for claim in claims if claim.get("availability") == "available"]
    first = lambda field: next((claim for claim in available if claim.get("field") == field), None)  # noqa: E731
    state = lambda field: next((claim.get("availability") for claim in claims if claim.get("field") == field), None)  # noqa: E731
    ref = lambda claim: evidence_row.get(((claim or {}).get("evidence_ids") or [""])[0], -1)  # noqa: E731

    def cell(claim: dict[str, Any] | None, text: str | None = None, missing: str = "—") -> list[Any]:
        return [text if text is not None else _value_text(claim["value"]), ref(claim)] if claim else [missing, -1]

    def absent(field: str) -> str:
        return {"not_available": "none found", "ambiguous": "found, not confirmed", "failed": "not checked (source failed)",
                "blocked": "not checked (blocked)", "not_applicable": "not attributed"}.get(str(state(field)), "not checked")

    cells: dict[str, list[Any]] = {}
    form = first("legal_form")
    cells["legal_form"] = cell(form, f"{form['value']} ({LEGAL_FORMS_EN[form['value']]})" if form and form["value"] in LEGAL_FORMS_EN else None)
    cells["registry_status"] = [str(identity.get("registry_status") or "unknown").replace("_", " "), evidence_row.get(str(identity.get("evidence_id")), -1)]
    cells["founded"] = cell(first("founded_date"))
    address = first("business_address")
    cells["place"] = cell(address, _value_text(address["value"]) if address else None)
    cells["industry"] = cell(first("industry"))
    employees = first("registry_employee_count")
    cells["employees"] = cell(employees, missing="unknown (not published; not zero)" if state("registry_employee_count") == "not_available" else "not checked")
    latest = latest_financials(claims)
    if latest:
        account_type, period, fields = latest
        anchor = next(iter(fields.values()))
        cells["accounts"] = [f"{period[0]} to {period[1]} ({ACCOUNT_TYPES.get(account_type, account_type.lower() or 'accounts')})", ref(anchor)]
        for field in ("revenue", "operating_result", "net_result", "equity"):
            claim = fields.get(field)
            cells[field] = cell(claim, f"{claim.get('currency') or ''} {claim['value']:,.0f}".strip() if claim and isinstance(claim["value"], (int, float)) else None)
    else:
        for field in ("accounts", "revenue", "operating_result", "net_result", "equity"):
            cells[field] = [absent("annual_accounts") if state("annual_accounts") else "no figures", -1]
    for field in ("ceo", "board_chair"):
        holders = [claim for claim in available if claim.get("field") == field]
        cells[field] = cell(holders[0] if holders else None, "; ".join(_value_text(claim["value"]).split(" — ")[0] for claim in holders) if holders else None, missing="none registered")
    cells["website"] = cell(first("official_website"), missing=absent("official_website"))
    profiles = [claim for claim in available if claim.get("field") == "social_profile"]
    cells["profiles"] = cell(profiles[0] if profiles else None, ", ".join(sorted({str(claim.get("platform") or "profile") for claim in profiles})) + f" ({len(profiles)})" if profiles else None, missing=absent("social_profile"))
    news = sorted((claim for claim in available if claim.get("field") in ("news_item", "site_activity")), key=lambda claim: str((claim.get("value") or {}).get("publication_date") or ""), reverse=True)
    cells["news"] = cell(news[0] if news else None, f"{len(news)}, most recent {str(news[0]['value'].get('publication_date') or '')[:10]}" if news else None, missing=absent("news_item"))
    jobs = [claim for claim in available if claim.get("field") == "job_posting"]
    cells["jobs"] = cell(jobs[0] if jobs else None, str(len(jobs)) if jobs else None, missing=absent("job_posting"))
    unknown = sorted({claim["field"] for claim in claims if claim.get("availability") != "available"} - {claim["field"] for claim in available})
    cells["unknowns"] = [f"{len(unknown)}: {', '.join(field.replace('_', ' ') for field in unknown)}" if unknown else "none", -1]
    return [cells[key] for key, _ in COMPARE_ROWS]


def _identity(envelope: dict[str, Any]) -> dict[str, Any]:
    if isinstance(envelope.get("identity"), dict):
        return envelope["identity"]
    fields = {claim["field"]: claim.get("value") for claim in envelope.get("claims") or [] if claim.get("category") == "identity" and claim.get("availability") == "available"}
    return {"organisation_number": envelope.get("organisation_number"), "legal_name": fields.get("legal_name"), "legal_form": fields.get("legal_form")}


def project(envelope: dict[str, Any]) -> dict[str, Any]:
    """The subset of one envelope the viewer needs, in a compact form the page re-hydrates.

    Evidence is split into a per-company source table (`src`: url, class, retrieved_at, sha256; one row per
    captured document) and evidence rows (`ev`: source index, claim span). Claims and summary statements
    reference evidence rows by index. This keeps a 1,200-company viewer to a few MB."""
    identity = _identity(envelope)
    summary = envelope.get("company_summary") or {}
    sources: dict[tuple, int] = {}
    evidence_rows: list[list[Any]] = []
    index: dict[str, int] = {}
    for item in envelope.get("evidence") or []:
        source = (item.get("source_url"), item.get("source_class"), item.get("retrieved_at"), item.get("content_sha256"))
        position = sources.setdefault(source, len(sources))
        index[item["id"]] = len(evidence_rows)
        evidence_rows.append([position, str(item.get("claim_span") or "")[:SPAN_LIMIT]])
    refs = lambda ids: [index[eid] for eid in ids or [] if eid in index]  # noqa: E731
    return {
        "org": envelope.get("organisation_number"),
        "input": envelope.get("input_organisation_number"),
        "pos": envelope.get("input_position"),
        "status": (envelope.get("run") or {}).get("terminal_status"),
        "company_status": (envelope.get("company_status") or {}).get("state"),
        "status_reasons": (envelope.get("company_status") or {}).get("reasons") or [],
        "identity": identity,
        "overview": summary.get("overview"),
        "sparse": summary.get("sparse"),
        "src": [list(source) for source in sources],
        "ev": evidence_rows,
        "sections": [[section.get("title"), [[item.get("text"), refs(item.get("evidence_ids")), 1 if item.get("carried_forward") else 0] for item in section.get("statements") or []]] for section in summary.get("sections") or []],
        "claims": [[
            claim.get("category"), claim.get("field"), claim.get("availability"), _value_text(claim.get("value")), refs(claim.get("evidence_ids")),
            _period(claim), 1 if claim.get("carried_forward") else 0, claim.get("reason") or "", _claim_notes(claim),
        ] for claim in envelope.get("claims") or []],
        "changes": [{key: (_value_text(value) if key in {"old_value", "new_value"} else value) for key, value in item.items() if key not in {"previous_evidence", "evidence"}} | {"source_at": (item.get("evidence") or {}).get("retrieved_at"), "previous_at": (item.get("previous_evidence") or {}).get("retrieved_at")} for item in envelope.get("changes") or []],
        "errors": envelope.get("errors") or [],
        "modules": {name: [state.get("state"), state.get("note")] for name, state in (envelope.get("modules") or {}).items()},
        "refresh": envelope.get("refresh") or {},
        "areas": [area for area, present in (envelope.get("area_coverage") or {}).items() if present],
        "cmp": _compare_cells(envelope, identity, index),
    }


def _claim_notes(claim: dict[str, Any]) -> dict[str, Any] | int:
    """V3: why a fact is attributed, when it was first seen, and whether it is new; 0 when there is nothing to say."""
    def mapping(key: str) -> dict[str, Any]:  # e.g. financial claims carry "currency": "NOK", a string
        value = claim.get(key)
        return value if isinstance(value, dict) else {}

    notes: dict[str, Any] = {}
    basis = mapping("attribution").get("basis") or claim.get("identity_basis")
    if basis:
        notes["basis"] = str(basis)[:300]
    if mapping("currency").get("basis"):
        notes["currency"] = str(mapping("currency")["basis"])[:200]
    for key in ("first_seen_at", "site_role"):
        if isinstance(claim.get(key), str) and claim[key]:
            notes[key] = claim[key]
    if claim.get("is_new"):
        notes["new"] = 1
    if mapping("operated_by").get("organisation_number"):
        notes["operated_by"] = mapping("operated_by")["organisation_number"]
    return notes or 0


TRUST = {  # how each category is checked: shown in the viewer's trust panel (V3 §B10)
    "official_website": "Taken from the company's own registry record, or found by name and confirmed by its organisation number or registered address on the site.",
    "social_profile": "Linked from the verified website, and the profile name is the company's legal name (or its own website's name on a site no other company runs). Profiles of a parent, group, sister company or platform are not attributed.",
    "news_item": "A dated article on the verified website (news section, dated address, its own post feed or article markup) that is about this company. Product, service, project and contact pages, listings, imported or demo posts, advice content and other companies' news are left out.",
    "job_posting": "A single advertisement naming this company as employer (or listed on its own careers page), with an open deadline or posted within 45 days. Expired, undated, third-party and general recruitment pages are left out.",
    "careers_page": "A page of the verified website about working at the company (careers path or heading); service pages and recruiters' client job boards are left out.",
}


def render_viewer(envelopes: list[dict[str, Any]], report: dict[str, Any] | None = None, *, title: str = "Signalpost results", app: dict[str, str] | None = None) -> str:
    audit = (report or {}).get("manual_audit") or {"state": "not_audited"}
    code = (report or {}).get("code_version") or {}
    data = {
        "title": title,
        "app": app or None,
        "trust": {"how": TRUST, "audit": audit, "checks": ((report or {}).get("checks") or {}).get("withheld") or {}},
        "code": {"commit": (code.get("git_commit") or "")[:12], "source": (code.get("source_sha256") or "")[:12]} if code else None,
        "baseline": ((report or {}).get("baseline") or {}).get("source"),
        "run": {key: (report or {}).get(key) for key in ("run_id", "started_at", "input_rows", "runtime_ms") if (report or {}).get(key) is not None},
        "compare_rows": [label for _, label in COMPARE_ROWS],
        "companies": [project(envelope) for envelope in envelopes],
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    # Safe inside <script type="application/json">: "<" only occurs inside JSON strings, and as \u003c it can
    # never close the script element or open an HTML comment. JSON.parse restores it.
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return TEMPLATE.replace("__TITLE__", _html_escape(title)).replace("__DATA__", payload)


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_viewer(path: Path, envelopes: list[dict[str, Any]], report: dict[str, Any] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(render_viewer(envelopes, report), encoding="utf-8")
    temporary.replace(path)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:">
<meta name="referrer" content="no-referrer">
<title>__TITLE__</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--muted:#5f5f5a;--line:#deded8;--accent:#1f5f8b;--ok:#2d7a3e;--warn:#8a5f00;--bad:#b3261e;--chip:#eeeeea}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--panel:#1d1d1c;--ink:#ecece8;--muted:#a3a39c;--line:#353532;--accent:#7cb4dc;--ok:#7cc48a;--warn:#e0b450;--bad:#f08b84;--chip:#2a2a28}}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.skip{position:absolute;left:-9999px}.skip:focus{left:8px;top:8px;z-index:9;background:var(--panel);padding:6px 10px;border-radius:6px}
header{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{font-size:16px;margin:0}header .meta{color:var(--muted);font-size:12px}
main{display:grid;grid-template-columns:minmax(260px,340px) minmax(0,1fr);height:calc(100% - 46px)}
#side{border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0;background:var(--panel)}
#controls{padding:10px;display:flex;flex-direction:column;gap:8px;border-bottom:1px solid var(--line)}
input[type=search],select{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);font:inherit}
label.sr{position:absolute;left:-9999px}
.row{display:flex;gap:6px}.row select{flex:1;min-width:0}
#count{color:var(--muted);font-size:12px}
.btn{padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink);font:inherit;cursor:pointer}
.btn[disabled]{opacity:.5;cursor:default}.btn.primary{border-color:var(--accent);color:var(--accent)}
#list{overflow:auto;flex:1;margin:0;padding:0;list-style:none}
#list li{padding:8px 12px;border-bottom:1px solid var(--line);cursor:pointer;display:flex;gap:8px;align-items:flex-start}
#list li>div{flex:1;min-width:0}
#list li:hover,#list li:focus{background:var(--chip);outline:none}#list li[aria-selected=true]{background:var(--chip);box-shadow:inset 3px 0 var(--accent)}
#list input[type=checkbox]{margin-top:3px;width:18px;height:18px}
.name{font-weight:600;overflow-wrap:anywhere}.sub{color:var(--muted);font-size:12px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.badge{display:inline-block;padding:0 6px;border-radius:9px;font-size:11px;background:var(--chip);color:var(--muted)}
.badge.ok{color:var(--ok)}.badge.bad{color:var(--bad)}.badge.warn{color:var(--warn)}
#detail{overflow:auto;padding:16px 20px;min-width:0}
#detail h2{margin:0 0 4px;font-size:20px;overflow-wrap:anywhere}
.nav{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 10px}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:12px 0;min-width:0}
section h3{margin:0 0 8px;font-size:14px}
section h4{margin:10px 0 4px;font-size:13px;color:var(--muted)}
.stmt{margin:4px 0;padding-left:12px;border-left:2px solid var(--line);overflow-wrap:anywhere}
.stmt button{all:unset;cursor:pointer;color:var(--accent);font-size:12px;margin-left:6px}.stmt button:focus-visible{outline:2px solid var(--accent)}
.src{font-size:12px;color:var(--muted);margin:4px 0 6px 0;padding:6px 8px;background:var(--bg);border-radius:6px;overflow-wrap:anywhere}
.wrap{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;vertical-align:top;padding:5px 6px;border-bottom:1px solid var(--line);overflow-wrap:anywhere;word-break:normal}
th{color:var(--muted);font-weight:500;font-size:12px}
td small,.cell small{display:block;color:var(--muted);font-size:11px}
table.cmp th[scope=row]{position:sticky;left:0;background:var(--panel);min-width:120px}table.cmp td{min-width:150px}
.overview{padding:8px 10px;border-radius:6px;background:var(--chip)}
.empty{color:var(--muted);padding:30px 0;text-align:center}
.back{display:none}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px}.kv dt{color:var(--muted)}.kv dd{margin:0;overflow-wrap:anywhere}
header .actions{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
dialog{max-width:min(680px,94vw);width:100%;border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--ink);padding:0}
dialog::backdrop{background:rgba(0,0,0,.45)}
.dhead{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line)}
.dbody{padding:10px 14px;overflow-wrap:anywhere}.dbody .kv{gap:6px 12px}
.badge.new{color:var(--accent);border:1px solid var(--accent)}
.cards{display:flex;flex-direction:column;gap:10px}.card{border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:var(--panel)}
.card h4{margin:0 0 4px;font-size:13px;color:var(--muted)}.cell{display:grid;grid-template-columns:28px minmax(0,1fr);gap:6px;padding:5px 0;border-top:1px solid var(--line);overflow-wrap:anywhere}
.chip{display:inline-block;width:22px;height:22px;border-radius:11px;color:#fff;font-size:11px;text-align:center;line-height:22px;font-weight:600}
.tray{position:sticky;top:0;z-index:2;background:var(--bg);padding:6px 0;display:flex;gap:6px;flex-wrap:wrap}
.linkbtn{all:unset;cursor:pointer;color:var(--accent);text-decoration:underline;font-size:12px;white-space:nowrap}.linkbtn:focus-visible{outline:2px solid var(--accent)}
@media (max-width:760px){
 main{grid-template-columns:minmax(0,1fr);height:auto}
 #side{border-right:0}#list{overflow:visible}
 body.showing #side{display:none}body.showing .back{display:inline-block}
 body:not(.showing) #detail{display:none}
 #detail{padding:12px 16px}
 table.facts thead{display:none}table.facts tr{display:block;border-bottom:1px solid var(--line);padding:4px 0}table.facts td{display:block;border:0;padding:2px 0}
}
</style>
</head>
<body>
<a class="skip" href="#detail">Skip to company details</a>
<header><h1 id="title"></h1><span class="meta" id="runmeta"></span><nav class="actions" aria-label="Views"><a id="searchlink" class="btn" hidden>← Search</a><button id="newbtn" class="btn" type="button">What's new</button><button id="trustbtn" class="btn" type="button">How reliable is this?</button></nav></header>
<dialog id="inspect" aria-labelledby="inspect-title"><div class="dhead"><strong id="inspect-title">Where this fact comes from</strong><button class="btn" id="inspect-close" type="button">Close</button></div><div class="dbody" id="inspect-body"></div></dialog>
<main>
<div id="side">
 <div id="controls" role="search">
  <label class="sr" for="q">Search companies</label>
  <input id="q" type="search" placeholder="Search name or organisation number" aria-label="Search">
  <div class="row">
   <label class="sr" for="fstatus">Status filter</label>
   <select id="fstatus" aria-label="Status filter"><option value="">All statuses</option><option value="complete">All sources checked</option><option value="partial">Some sources failed</option><option value="not_researched">Not researched (time limit)</option><option value="identity_unresolved">Not found in the register</option><option value="invalid_input">Invalid organisation number</option><option value="failed">Research failed</option></select>
   <label class="sr" for="fflag">Flag filter</label>
   <select id="fflag" aria-label="Flag filter"><option value="">All companies</option><option value="website">Verified website</option><option value="footprint">Profiles or dated activity</option><option value="changes">With changes</option><option value="new">With new items</option><option value="failures">Source failures</option><option value="errors">With errors</option><option value="sparse">Registry only (sparse)</option><option value="carried">Values retained (outage)</option></select>
  </div>
  <div class="row">
   <label class="sr" for="sort">Sort</label>
   <select id="sort" aria-label="Sort"><option value="input">Input order</option><option value="name">Name A–Z</option><option value="revenue">Revenue, highest first</option><option value="facts">Most facts first</option></select>
   <button id="cmpbtn" class="btn primary" type="button" disabled>Compare (0)</button>
  </div>
  <div id="count" aria-live="polite"></div>
 </div>
 <ul id="list" role="listbox" aria-label="Companies"></ul>
</div>
<div id="detail" tabindex="-1"><div class="empty">Select a company, or tick up to four and press Compare.</div></div>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
for (const c of DATA.companies) {  // re-hydrate the compact projection (see viewer.project)
  c.evidence = c.ev.map(([s, span]) => ({url: c.src[s][0], class: c.src[s][1], at: c.src[s][2], sha: c.src[s][3], span}));
  c.sections = c.sections.map(([title, statements]) => ({title, statements: statements.map(([text, ev, carried]) => ({text, ev, carried: !!carried}))}));
  c.claims = c.claims.map(([cat, field, state, value, ev, period, carried, reason, notes]) => ({cat, field, state, value, ev, period, carried: !!carried, reason, notes: notes || {}}));
  c.modules = Object.fromEntries(Object.entries(c.modules).map(([k, [state, note]]) => [k, {state, note}]));
  c.areas = Object.fromEntries(c.areas.map((a) => [a, true]));
  c.revenue = c.cmp[7][1] >= 0 ? Number(c.cmp[7][0].replace(/[^0-9.-]/g, "")) : -Infinity;  // compare row 7: most recent revenue
  c.factCount = c.claims.filter((x) => x.state === "available").length;
}
const MAX_COMPARE = 4;
const GROUPS = [
  ["Identity and description", ["identity", "description", "relationships"]],
  ["Financials", ["filings"]],
  ["Leadership", ["leadership", "registry_activity"]],
  ["Locations", ["locations"]],
  ["Website and public activity", ["websites", "public_activity", "hiring"]],
];
const $ = (id) => document.getElementById(id);
function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) { if (v === null || v === undefined || v === false) continue; if (k === "class") node.className = v; else node.setAttribute(k, v); }
  for (const kid of kids.flat(Infinity)) { if (kid === null || kid === undefined || kid === false) continue; node.append(kid instanceof Node ? kid : document.createTextNode(String(kid))); }
  return node;
}
const safeUrl = (u) => typeof u === "string" && /^https?:\/\//i.test(u) ? u : null;
const host = (u) => { try { return new URL(u).hostname; } catch (e) { return u || "?"; } };
const day = (t) => t ? String(t).slice(0, 10) : "date unknown";
const name = (c) => (c.identity && c.identity.legal_name) || "(identity not resolved)";
const STATUS = {completed: "Research finished", failed: "Research failed"};
const COMPANY = {complete: "All sources checked", partial: "Some sources failed", not_researched: "Not researched (time limit)", identity_unresolved: "Not found in the register", invalid_input: "Invalid organisation number"};
const STATE = {available: "Found", not_available: "Checked — none found", ambiguous: "Not attributed (may belong to another company)", not_applicable: "Not attributed to this company", failed: "Could not check (source failed)", blocked: "Could not check (blocked)"};
const CHANGE = {added: "New since last run", removed: "No longer on the source", changed: "Changed", retracted: "Withdrawn by our checks", not_rechecked: "Not re-checked this run", first_observed: "First seen (website not read last time)", unverified: "Website no longer confirmed", unavailable: "Source unavailable — last value kept"};
const CATEGORY = {official_website: "Website", social_profile: "Social profiles", news_item: "News", job_posting: "Job advertisements", careers_page: "Careers page"};
const CHIPS = ["#1f5f8b", "#8a3b8f", "#2d7a3e", "#a0522d"];
const label = (map, v) => map[v] || String(v || "unknown").replace(/_/g, " ");
const statusBadge = (c) => el("span", {class: "badge " + (c.status === "completed" ? "ok" : "bad")}, label(STATUS, c.status));
const companyBadge = (c) => c.company_status ? el("span", {class: "badge " + (c.company_status === "complete" ? "ok" : c.company_status === "partial" ? "warn" : "bad")}, label(COMPANY, c.company_status)) : null;
const setHash = (hash) => { try { history.replaceState(null, "", hash); } catch (e) { /* file:// may refuse; navigation still works */ } };
const narrow = () => window.matchMedia("(max-width: 760px)").matches;
const failedSources = (c) => Object.entries(c.modules).filter(([, v]) => v.state === "failed" || v.state === "blocked").map(([k]) => k);

$("title").textContent = DATA.title;
$("runmeta").textContent = [DATA.run.run_id && ("run " + DATA.run.run_id), DATA.run.started_at && ("started " + day(DATA.run.started_at)), DATA.companies.length + " companies",
  DATA.code && (DATA.code.commit ? "code " + DATA.code.commit : "source " + DATA.code.source), (() => { const n = DATA.companies.filter((c) => c.refresh && c.refresh.compared).length; return n ? n + " compared with their previous run" : "no previous run"; })(),
  "every fact links to its source and retrieval date"].filter(Boolean).join(" · ");
if (DATA.app && DATA.app.search) { $("searchlink").href = DATA.app.search; $("searchlink").hidden = false; }

const flags = {
  errors: (c) => c.errors.length > 0,
  changes: (c) => c.changes.some((x) => x.change_type !== "unavailable"),
  website: (c) => !!c.areas.websites,
  footprint: (c) => !!c.areas.public_footprint,
  failures: (c) => failedSources(c).length > 0,
  sparse: (c) => !!c.sparse,
  carried: (c) => c.claims.some((x) => x.carried),
  new: (c) => c.claims.some((x) => x.notes.new) || c.changes.some((x) => x.change_type === "retracted"),
};
let selected = null, shownOrder = [];
const compare = [];
function visible() {
  const q = $("q").value.trim().toLowerCase();
  const st = $("fstatus").value, fl = $("fflag").value, sort = $("sort").value;
  const rows = [];
  DATA.companies.forEach((c, index) => {
    if (st && c.company_status !== st && c.status !== st) return;
    if (fl && !flags[fl](c)) return;
    if (q && !(name(c).toLowerCase().includes(q) || String(c.org || c.input || "").includes(q.replace(/\s/g, "")))) return;
    rows.push(index);
  });
  const by = {name: (a, b) => name(DATA.companies[a]).localeCompare(name(DATA.companies[b]), "nb"), revenue: (a, b) => DATA.companies[b].revenue - DATA.companies[a].revenue, facts: (a, b) => DATA.companies[b].factCount - DATA.companies[a].factCount}[sort];
  return by ? rows.sort((a, b) => by(a, b) || a - b) : rows;
}
function render() {
  const list = $("list"); list.replaceChildren();
  shownOrder = visible();
  for (const index of shownOrder) {
    const c = DATA.companies[index];
    const box = el("input", {type: "checkbox", "aria-label": "Compare " + name(c), checked: compare.includes(index) ? "checked" : null});
    box.addEventListener("click", (e) => { e.stopPropagation(); toggleCompare(index, box.checked); });
    const li = el("li", {role: "option", tabindex: "0", "aria-selected": String(index === selected), "data-index": String(index)}, box, el("div", {},
      el("div", {class: "name"}, name(c)),
      el("div", {class: "sub"}, String(c.org || c.input || "no number"), statusBadge(c), companyBadge(c), c.errors.length ? el("span", {class: "badge warn"}, c.errors.length + " error" + (c.errors.length > 1 ? "s" : "")) : null, failedSources(c).length ? el("span", {class: "badge warn"}, "source failed") : null, c.sparse ? el("span", {class: "badge"}, "registry only") : null)));
    li.addEventListener("click", () => select(index));
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(index); }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); const next = e.key === "ArrowDown" ? li.nextElementSibling : li.previousElementSibling; if (next) next.focus(); }
    });
    list.append(li);
  }
  $("count").textContent = shownOrder.length + " of " + DATA.companies.length + " shown";
  $("cmpbtn").textContent = "Compare (" + compare.length + ")";
  $("cmpbtn").disabled = compare.length < 2;
}
function toggleCompare(index, on) {
  const at = compare.indexOf(index);
  if (on && at < 0) { if (compare.length >= MAX_COMPARE) { render(); $("count").textContent = "At most " + MAX_COMPARE + " companies can be compared."; return; } compare.push(index); }
  if (!on && at >= 0) compare.splice(at, 1);
  render();
}
function sources(c, ids) {
  return el("div", {class: "src"}, ids.map((id) => {
    const ev = c.evidence[id];
    if (!ev) return el("div", {}, "evidence " + id + " (not in envelope)");
    const url = safeUrl(ev.url);
    return el("div", {}, "SOURCE: ", url ? el("a", {href: url, target: "_blank", rel: "noopener noreferrer"}, ev.url) : (ev.url || "?"),
      " · ", ev.class || "", " · DATE: retrieved ", day(ev.at), " · sha256 ", (ev.sha || "").slice(0, 12), ev.span ? el("div", {}, "span: " + ev.span) : null);
  }));
}
function sourceLink(c, id) {
  const ev = c.evidence[id];
  if (!ev) return null;
  const url = safeUrl(ev.url);
  return el("small", {}, url ? el("a", {href: url, target: "_blank", rel: "noopener noreferrer", title: ev.url + (ev.span ? " — " + ev.span : "")}, host(ev.url)) : (ev.url || ""), " · retrieved " + day(ev.at));
}
function statement(c, s) {
  const box = el("div", {class: "stmt"}, s.text, s.carried ? el("span", {class: "badge warn"}, "retained from earlier run") : null);
  if (s.ev.length) {
    let open = null;
    const btn = el("button", {type: "button", "aria-expanded": "false"}, "sources (" + s.ev.length + ")");
    btn.addEventListener("click", () => { if (open) { open.remove(); open = null; btn.setAttribute("aria-expanded", "false"); } else { open = sources(c, s.ev); box.append(open); btn.setAttribute("aria-expanded", "true"); } });
    box.append(btn);
  }
  return box;
}
function inspect(c, x) {
  const body = $("inspect-body"); body.replaceChildren();
  const rows = [["Fact", x.field.replace(/_/g, " ")], ["Value", x.value || "—"], ["State", label(STATE, x.state)]];
  if (x.period) rows.push(["Period", x.period]);
  if (x.notes.basis) rows.push(["How it relates to this company", x.notes.basis]);
  if (x.notes.currency) rows.push(["Why it is current", x.notes.currency]);
  if (x.notes.site_role) rows.push(["Website role", x.notes.site_role.replace(/_/g, " ") + (x.notes.operated_by ? " (organisation number " + x.notes.operated_by + ")" : "")]);
  if (x.notes.first_seen_at) rows.push(["First seen", day(x.notes.first_seen_at) + (x.notes.new ? " — new since the previous run" : "")]);
  if (x.carried) rows.push(["Note", "Retained from an earlier run: the source failed in this run."]);
  if (x.reason) rows.push(["Reason", x.reason]);
  body.append(el("dl", {class: "kv"}, rows.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])));
  for (const id of x.ev) {
    const ev = c.evidence[id]; if (!ev) continue;
    const url = safeUrl(ev.url);
    const snap = DATA.app && DATA.app.snapshots && /^[0-9a-f]{64}$/.test(ev.sha || "") ? DATA.app.snapshots + ev.sha : null;
    body.append(el("section", {}, el("h4", {}, "Source"), el("dl", {class: "kv"},
      el("dt", {}, "Address"), el("dd", {}, url ? el("a", {href: url, target: "_blank", rel: "noopener noreferrer"}, ev.url) : (ev.url || "?")),
      el("dt", {}, "Source type"), el("dd", {}, (ev.class || "").replace(/_/g, " ")),
      el("dt", {}, "Retrieved"), el("dd", {}, ev.at || "unknown"),
      el("dt", {}, "Content hash"), el("dd", {}, el("code", {}, ev.sha || "—")),
      el("dt", {}, "Quoted span"), el("dd", {}, ev.span || "—"),
      snap ? [el("dt", {}, "Captured copy"), el("dd", {}, el("a", {href: snap, rel: "noopener noreferrer"}, "Download the exact bytes we read (text)"))] : null)));
  }
  if (!x.ev.length) body.append(el("p", {class: "sub"}, "No source: this is a statement about what is not known."));
  const dialog = $("inspect");
  if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
}
$("inspect-close").addEventListener("click", () => { const d = $("inspect"); if (d.close) d.close(); else d.removeAttribute("open"); });
let showAllNews = false;
function table(headers, rows, cls) {
  return el("div", {class: "wrap"}, el("table", {class: cls || null}, el("thead", {}, el("tr", {}, headers.map((h) => el("th", {scope: "col"}, h)))), el("tbody", {}, rows.map((r) => el("tr", {}, r.map((v, i) => el("td", {"data-label": headers[i]}, v)))))));
}
function navButtons(index) {
  const at = shownOrder.indexOf(index);
  const back = el("button", {id: "back", class: "btn back", type: "button"}, "← Companies");
  back.addEventListener("click", () => { document.body.classList.remove("showing"); setHash(location.pathname + location.search); const item = document.querySelector('#list li[data-index="' + index + '"]'); if (item) item.focus(); });
  const prev = el("button", {class: "btn", type: "button", disabled: at <= 0 ? "disabled" : null}, "‹ Previous");
  const next = el("button", {class: "btn", type: "button", disabled: at < 0 || at >= shownOrder.length - 1 ? "disabled" : null}, "Next ›");
  prev.addEventListener("click", () => select(shownOrder[at - 1]));
  next.addEventListener("click", () => select(shownOrder[at + 1]));
  const pick = el("button", {class: "btn", type: "button", "aria-pressed": String(compare.includes(index))}, compare.includes(index) ? "Remove from comparison" : "Add to comparison");
  pick.addEventListener("click", () => { toggleCompare(index, !compare.includes(index)); select(index); });
  return el("div", {class: "nav"}, back, prev, next, pick);
}
function select(index, fromHash) {
  if (index === undefined || !DATA.companies[index]) return;
  const fromList = document.activeElement && document.activeElement.closest && document.activeElement.closest("#list");
  selected = index;
  const c = DATA.companies[index];
  const d = $("detail");
  d.replaceChildren();
  d.append(navButtons(index));
  d.append(el("h2", {id: "company-name"}, name(c)));
  d.append(el("div", {class: "sub"}, "Organisation number " + (c.org || c.input || "?"), statusBadge(c), companyBadge(c), "input row " + c.pos));
  if (c.overview) d.append(el("p", {class: "overview"}, c.overview));
  for (const sec of c.sections) d.append(el("section", {}, el("h3", {}, sec.title), sec.statements.map((s) => statement(c, s))));
  const id = c.identity || {};
  d.append(el("section", {}, el("h3", {}, "Identity anchor (registry record)"), el("dl", {class: "kv"},
    Object.entries(id).filter(([, v]) => v !== null && v !== undefined && typeof v !== "object").map(([k, v]) => [el("dt", {}, k.replace(/_/g, " ")), el("dd", {}, String(v))])),
    c.status_reasons.length ? el("div", {class: "sub"}, "Status reasons: " + c.status_reasons.join("; ")) : null));
  const facts = c.claims.filter((x) => x.state === "available");
  const grouped = GROUPS.map(([title, cats]) => [title, facts.filter((x) => cats.includes(x.cat))]).filter(([, items]) => items.length);
  d.append(el("section", {}, el("h3", {}, "Facts (" + facts.length + ") — FACT → SOURCE → DATE"), el("p", {class: "sub"}, "Press Inspect on any fact to see exactly where it came from and why it is attributed to this company."),
    grouped.map(([title, items]) => {
      const news = items.filter((x) => x.field === "news_item").sort((a, b) => String(b.value).localeCompare(String(a.value)));
      const shown = showAllNews || news.length <= 10 ? items : items.filter((x) => x.field !== "news_item").concat(news.slice(0, 10));
      const more = shown.length < items.length ? el("button", {class: "btn", type: "button"}, "Show all " + news.length + " news items") : null;
      if (more) more.addEventListener("click", () => { showAllNews = true; select(index, true); });
      return [el("h4", {}, title + " (" + items.length + ")"),
        table(["Field", "Value", "Period", "Source", "Retrieved", ""], shown.map((x) => {
          const ev = c.evidence[x.ev[0]] || {}; const url = safeUrl(ev.url);
          const btn = el("button", {class: "linkbtn", type: "button", "aria-label": "Inspect " + x.field.replace(/_/g, " ")}, "Inspect");
          btn.addEventListener("click", () => inspect(c, x));
          return [el("span", {}, x.field.replace(/_/g, " ") + (x.carried ? " (retained)" : ""), x.notes.new ? el("span", {class: "badge new"}, "new") : null), x.value, x.period,
            url ? el("a", {href: url, target: "_blank", rel: "noopener noreferrer", title: url}, host(url) + " · " + (ev.class || "source").replace(/_/g, " ")) : (ev.class || ""), day(ev.at), btn];
        }), "facts"), more];
    })));
  const unknown = c.claims.filter((x) => x.state !== "available");
  const held = unknown.filter((x) => x.state === "ambiguous" || x.state === "not_applicable");
  const rest = unknown.filter((x) => !held.includes(x));
  if (held.length) d.append(el("section", {}, el("h3", {}, "Seen but not attributed to this company (" + held.length + ")"), el("p", {class: "sub"}, "Found on the website but held back, for example because it belongs to a parent, sister or group company, or the website is run by another company. Not counted as facts."),
    table(["Field", "State", "Why"], held.map((x) => [x.field.replace(/_/g, " "), label(STATE, x.state), x.reason || ""]), "facts")));
  if (rest.length) d.append(el("section", {}, el("h3", {}, "Not known (" + rest.length + ")"), el("p", {class: "sub"}, "Unknown means unknown — never zero."), table(["Category", "Field", "State", "Reason"], rest.map((x) => [x.cat.replace(/_/g, " "), x.field.replace(/_/g, " "), label(STATE, x.state), x.reason || ""]), "facts")));
  d.append(el("section", {}, el("h3", {}, "Changes since previous run"), c.refresh && c.refresh.compared ? (c.changes.length ? table(["What happened", "Field / source", "Before", "Now", "Why", "Dates"], c.changes.map((x) => [label(CHANGE, x.change_type), (x.field || x.module || "").replace(/_/g, " "), x.old_value || (x.fields_retained ? "retained: " + x.fields_retained.join(", ") : ""), x.new_value || "", x.basis || (x.period ? x.period.from + "–" + x.period.to : ""), [x.previous_at && ("was " + day(x.previous_at)), x.source_at && ("now " + day(x.source_at)), x.last_verified_at && ("last verified " + day(x.last_verified_at))].filter(Boolean).join(" · ")]), "facts") : el("div", {}, "No changes.")) : el("div", {}, (c.refresh && c.refresh.reason) || "Not compared: no previous run.")));
  if (c.errors.length) d.append(el("section", {}, el("h3", {}, "Errors (" + c.errors.length + ")"), table(["Code", "Stage", "Message"], c.errors.map((x) => [x.code, x.stage || "", x.message || ""]), "facts")));
  d.append(el("section", {}, el("h3", {}, "Sources consulted"), table(["Source", "State", "Note"], Object.entries(c.modules).map(([k, v]) => [k.replace(/_/g, " "), el("span", {class: "badge " + (v.state === "failed" || v.state === "blocked" ? "bad" : "ok")}, label(STATE, v.state) || ""), v.note || ""]), "facts")));
  document.body.classList.add("showing");
  if (!fromHash && c.org) setHash("#org=" + c.org);
  d.scrollTop = 0;
  render();
  const item = document.querySelector('#list li[data-index="' + index + '"]');
  if (narrow() && !fromHash) d.focus({preventScroll: true});
  else if (fromList && item) item.focus();  // keyboard users keep their place in the list
}
function showCompare(fromHash) {
  if (compare.length < 2) return;
  selected = null;
  const d = $("detail");
  d.replaceChildren();
  const back = el("button", {id: "back", class: "btn back", type: "button"}, "← Companies");
  back.addEventListener("click", () => { document.body.classList.remove("showing"); setHash(location.pathname + location.search); });
  const clear = el("button", {class: "btn", type: "button"}, "Clear comparison");
  clear.addEventListener("click", () => { compare.splice(0, compare.length); setHash(location.pathname + location.search); d.replaceChildren(el("div", {class: "empty"}, "Comparison cleared.")); document.body.classList.remove("showing"); render(); });
  d.append(el("div", {class: "nav"}, back, clear), el("h2", {id: "company-name"}, "Comparing " + compare.length + " companies"),
    el("p", {class: "sub"}, "Each value is the company's own cited fact; the link under it opens the source, with its retrieval date. A dash or a reason means the fact is not known — not zero."));
  const cols = compare.map((i) => DATA.companies[i]);
  const head = el("tr", {}, el("th", {scope: "col"}, "Field"), cols.map((c, n) => {
    const open = el("button", {class: "btn", type: "button"}, name(c));
    open.addEventListener("click", () => select(compare[n]));
    return el("th", {scope: "col"}, open, el("small", {}, String(c.org || "")));
  }));
  if (narrow()) {  // phones: one card per field, one row per company, no sideways scrolling
    d.append(el("div", {class: "tray", "aria-label": "Companies compared"}, cols.map((c, n) => el("span", {class: "sub"}, el("span", {class: "chip", style: "background:" + CHIPS[n]}, String(n + 1)), name(c)))));
    d.append(el("div", {class: "cards"}, DATA.compare_rows.map((rowLabel, r) => el("div", {class: "card"}, el("h4", {}, rowLabel),
      cols.map((c, n) => { const [text, ev] = c.cmp[r]; return el("div", {class: "cell"}, el("span", {class: "chip", style: "background:" + CHIPS[n], "aria-label": name(c)}, String(n + 1)), el("div", {}, text, ev >= 0 ? sourceLink(c, ev) : null)); })))));
  } else {
    const body = DATA.compare_rows.map((rowLabel, r) => el("tr", {}, el("th", {scope: "row"}, rowLabel), cols.map((c) => { const [text, ev] = c.cmp[r]; return el("td", {}, text, ev >= 0 ? sourceLink(c, ev) : null); })));
    d.append(el("section", {}, el("div", {class: "wrap"}, el("table", {class: "cmp"}, el("thead", {}, head), el("tbody", {}, body)))));
  }
  document.body.classList.add("showing");
  const orgs = cols.map((c) => c.org).filter(Boolean);
  if (!fromHash) setHash("#compare=" + orgs.join(","));
  d.scrollTop = 0;
  render();
}
function viewShell(title) {
  selected = null;
  const d = $("detail"); d.replaceChildren();
  const back = el("button", {id: "back", class: "btn back", type: "button"}, "← Companies");
  back.addEventListener("click", () => { document.body.classList.remove("showing"); setHash(location.pathname + location.search); });
  d.append(el("div", {class: "nav"}, back), el("h2", {id: "company-name"}, title));
  document.body.classList.add("showing");
  return d;
}
function companyLink(index) {
  const b = el("button", {class: "linkbtn", type: "button"}, name(DATA.companies[index]));
  b.addEventListener("click", () => select(index));
  return b;
}
function showWhatsNew(fromHash) {
  const d = viewShell("What's new since the previous run");
  const compared = DATA.companies.filter((c) => c.refresh && c.refresh.compared).length;
  if (!compared) { d.append(el("p", {class: "empty"}, "No previous run to compare with — everything here is a first observation. Run the same companies again later to see what is new.")); if (!fromHash) setHash("#new"); render(); return; }
  const filter = el("select", {"aria-label": "Category"}, el("option", {value: ""}, "All categories"), Object.entries(CATEGORY).map(([k, v]) => el("option", {value: k}, v)));
  const out = el("div", {});
  const draw = () => {
    const rows = [];
    DATA.companies.forEach((c, index) => {
      for (const x of c.claims) if (x.notes.new && (!filter.value || filter.value === x.field)) rows.push([companyLink(index), label(CATEGORY, x.field), el("span", {class: "badge new"}, "new"), x.value]);
      for (const x of c.changes) if (["retracted", "removed", "changed", "added"].includes(x.change_type) && (!filter.value || filter.value === x.field) && !(x.change_type === "added" && c.claims.some((y) => y.notes.new && y.field === x.field)))
        rows.push([companyLink(index), label(CATEGORY, x.field), label(CHANGE, x.change_type), [x.old_value || x.new_value || "", x.basis ? el("small", {}, x.basis) : null]]);
    });
    out.replaceChildren(rows.length ? table(["Company", "Category", "What happened", "Details"], rows, "facts") : el("p", {class: "empty"}, "Nothing new in this category."));
  };
  filter.addEventListener("input", draw);
  d.append(el("p", {class: "sub"}, compared + " of " + DATA.companies.length + " companies were compared with their previous run. New social profiles, news and job advertisements, and facts our checks withdrew."), filter, out);
  draw();
  if (!fromHash) setHash("#new");
  render();
}
function showTrust(fromHash) {
  const d = viewShell("How reliable is this?");
  const audit = DATA.trust.audit || {state: "not_audited"};
  const arm = audit.arms ? (audit.arms.v3 || audit.arms[Object.keys(audit.arms).slice(-1)[0]]) : null;
  d.append(el("p", {class: "sub"}, "Each category is checked by fixed rules. A manual audit, when supplied, shows how often published items were correct in a labelled sample — a local measurement, not an official score."));
  for (const [cat, how] of Object.entries(DATA.trust.how)) {
    const row = arm && arm[cat];
    const measured = row && row.precision !== null && row.precision !== undefined ? (Math.round(row.precision * 1000) / 10) + "% correct (" + row.correct + " of " + (row.correct + row.incorrect) + "; 95% interval " + Math.round(row.ci95[0] * 100) + "–" + Math.round(row.ci95[1] * 100) + "%)" : "Not audited";
    d.append(el("section", {}, el("h3", {}, label(CATEGORY, cat)), el("p", {}, how), el("div", {class: "sub"}, "Manual audit: " + measured)));
  }
  if (audit.state === "audited") d.append(el("p", {class: "sub"}, "Audit labelled by " + (audit.labeller || "?") + " (" + String(audit.labeller_kind || "").replace(/_/g, " ") + "); " + (audit.note || "")));
  const checks = Object.entries(DATA.trust.checks || {});
  if (checks.length) d.append(el("section", {}, el("h3", {}, "Held back by our checks in this run"), el("p", {class: "sub"}, "Automatic checks, not an accuracy measurement."), table(["Reason", "Items"], checks.sort((a, b) => b[1] - a[1]).slice(0, 25).map(([k, v]) => [k.replace(/[:_]/g, " "), String(v)]), "facts")));
  if (!fromHash) setHash("#trust");
  render();
}
$("newbtn").addEventListener("click", () => showWhatsNew());
$("trustbtn").addEventListener("click", () => showTrust());
$("cmpbtn").addEventListener("click", () => showCompare());
for (const id of ["q", "fstatus", "fflag", "sort"]) $(id).addEventListener("input", render);
const byOrg = new Map(DATA.companies.map((c, i) => [String(c.org), i]));
function fromHash() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash.startsWith("org=") && byOrg.has(hash.slice(4))) { select(byOrg.get(hash.slice(4)), true); return true; }
  if (hash === "new") { showWhatsNew(true); return true; }
  if (hash === "trust") { showTrust(true); return true; }
  if (hash.startsWith("compare=")) {
    compare.splice(0, compare.length, ...hash.slice(8).split(",").filter((o) => byOrg.has(o)).map((o) => byOrg.get(o)).slice(0, MAX_COMPARE));
    if (compare.length >= 2) { showCompare(true); return true; }
  }
  return false;
}
window.addEventListener("hashchange", fromHash);
render();
if (!location.hash && DATA.app && /^(org=\d{9}|compare=[\d,]{19,39}|new|trust)$/.test(DATA.app.open || "")) history.replaceState(null, "", "#" + DATA.app.open);  // app documents open on their view
if (!fromHash() && DATA.companies.length && !narrow()) select(0, true);
</script>
</body>
</html>
"""
