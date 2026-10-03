"""Static, self-contained HTML viewer for a batch of envelopes.

One HTML file, no framework, no network: data is embedded as JSON, rendered with vanilla JS through
textContent (never innerHTML), so text captured from the web cannot inject markup. Links are only
emitted for http(s) source URLs. Every fact shows FACT -> SOURCE -> DATE.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VALUE_LIMIT = 400
SPAN_LIMIT = 160


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
            _period(claim), 1 if claim.get("carried_forward") else 0, claim.get("reason") or "",
        ] for claim in envelope.get("claims") or []],
        "changes": [{key: (_value_text(value) if key in {"old_value", "new_value"} else value) for key, value in item.items() if key not in {"previous_evidence", "evidence"}} | {"source_at": (item.get("evidence") or {}).get("retrieved_at"), "previous_at": (item.get("previous_evidence") or {}).get("retrieved_at")} for item in envelope.get("changes") or []],
        "errors": envelope.get("errors") or [],
        "modules": {name: [state.get("state"), state.get("note")] for name, state in (envelope.get("modules") or {}).items()},
        "refresh": envelope.get("refresh") or {},
        "areas": [area for area, present in (envelope.get("area_coverage") or {}).items() if present],
    }


def render_viewer(envelopes: list[dict[str, Any]], report: dict[str, Any] | None = None, *, title: str = "Signalpost results") -> str:
    data = {
        "title": title,
        "run": {key: (report or {}).get(key) for key in ("run_id", "started_at", "input_rows", "runtime_ms") if (report or {}).get(key) is not None},
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
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--muted:#5f5f5a;--line:#deded8;--accent:#1f5f8b;--ok:#2d7a3e;--warn:#9a6a00;--bad:#b3261e;--chip:#eeeeea}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--panel:#1d1d1c;--ink:#ecece8;--muted:#a3a39c;--line:#353532;--accent:#7cb4dc;--ok:#7cc48a;--warn:#e0b450;--bad:#f08b84;--chip:#2a2a28}}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{font-size:16px;margin:0}header .meta{color:var(--muted);font-size:12px}
main{display:grid;grid-template-columns:minmax(260px,340px) 1fr;height:calc(100% - 46px)}
#side{border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0;background:var(--panel)}
#controls{padding:10px;display:flex;flex-direction:column;gap:8px;border-bottom:1px solid var(--line)}
input[type=search],select{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);font:inherit}
.row{display:flex;gap:6px}.row select{flex:1}
#count{color:var(--muted);font-size:12px}
#list{overflow:auto;flex:1;margin:0;padding:0;list-style:none}
#list li{padding:8px 12px;border-bottom:1px solid var(--line);cursor:pointer}
#list li:hover,#list li:focus{background:var(--chip);outline:none}#list li[aria-selected=true]{background:var(--chip);box-shadow:inset 3px 0 var(--accent)}
.name{font-weight:600;overflow-wrap:anywhere}.sub{color:var(--muted);font-size:12px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.badge{display:inline-block;padding:0 6px;border-radius:9px;font-size:11px;background:var(--chip);color:var(--muted)}
.badge.ok{color:var(--ok)}.badge.bad{color:var(--bad)}.badge.warn{color:var(--warn)}
#detail{overflow:auto;padding:16px 20px;min-width:0}
#detail h2{margin:0 0 4px;font-size:20px;overflow-wrap:anywhere}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:12px 0}
section h3{margin:0 0 8px;font-size:14px}
.stmt{margin:4px 0;padding-left:12px;border-left:2px solid var(--line)}
.stmt button{all:unset;cursor:pointer;color:var(--accent);font-size:12px;margin-left:6px}
.src{font-size:12px;color:var(--muted);margin:4px 0 6px 0;padding:6px 8px;background:var(--bg);border-radius:6px;overflow-wrap:anywhere}
.src a{color:var(--accent)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;vertical-align:top;padding:5px 6px;border-bottom:1px solid var(--line);overflow-wrap:break-word;word-break:normal}td:last-child,th:last-child{white-space:nowrap}
th{color:var(--muted);font-weight:500;font-size:12px}
.overview{padding:8px 10px;border-radius:6px;background:var(--chip)}
.empty{color:var(--muted);padding:30px 0;text-align:center}
#back{display:none}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px}.kv dt{color:var(--muted)}.kv dd{margin:0;overflow-wrap:anywhere}
@media (max-width:760px){
 main{grid-template-columns:1fr;height:auto}
 #side{border-right:0}#list{overflow:visible}
 body.showing #side{display:none}body.showing #back{display:inline-block}
 body:not(.showing) #detail{display:none}
 #detail{padding:12px 16px}
 table thead{display:none}table tr{display:block;border-bottom:1px solid var(--line);padding:4px 0}table td{display:block;border:0;padding:2px 0}
}
#back{margin-bottom:10px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink);font:inherit}
</style>
</head>
<body>
<header><h1 id="title"></h1><span class="meta" id="runmeta"></span></header>
<main>
<div id="side">
 <div id="controls">
  <input id="q" type="search" placeholder="Search name or organisation number" aria-label="Search">
  <div class="row">
   <select id="fstatus" aria-label="Status filter"><option value="">All statuses</option><option value="complete">Complete</option><option value="partial">Partial</option><option value="identity_unresolved">Identity unresolved</option><option value="invalid_input">Invalid input</option><option value="failed">Run failed</option></select>
   <select id="fflag" aria-label="Flag filter"><option value="">All companies</option><option value="errors">With errors</option><option value="changes">With changes</option><option value="website">Verified website</option><option value="sparse">Registry only (sparse)</option><option value="carried">Values retained (outage)</option></select>
  </div>
  <div id="count"></div>
 </div>
 <ul id="list" role="listbox" aria-label="Companies"></ul>
</div>
<div id="detail"><div class="empty">Select a company.</div></div>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
for (const c of DATA.companies) {  // re-hydrate the compact projection (see viewer.project)
  c.evidence = c.ev.map(([s, span]) => ({url: c.src[s][0], class: c.src[s][1], at: c.src[s][2], sha: c.src[s][3], span}));
  c.sections = c.sections.map(([title, statements]) => ({title, statements: statements.map(([text, ev, carried]) => ({text, ev, carried: !!carried}))}));
  c.claims = c.claims.map(([cat, field, state, value, ev, period, carried, reason]) => ({cat, field, state, value, ev, period, carried: !!carried, reason}));
  c.modules = Object.fromEntries(Object.entries(c.modules).map(([k, [state, note]]) => [k, {state, note}]));
  c.areas = Object.fromEntries(c.areas.map((a) => [a, true]));
}
const $ = (id) => document.getElementById(id);
function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) { if (v === null || v === undefined || v === false) continue; if (k === "class") node.className = v; else node.setAttribute(k, v); }
  for (const kid of kids.flat(Infinity)) { if (kid === null || kid === undefined || kid === false) continue; node.append(kid instanceof Node ? kid : document.createTextNode(String(kid))); }
  return node;
}
const safeUrl = (u) => typeof u === "string" && /^https?:\/\//i.test(u) ? u : null;
const day = (t) => t ? String(t).slice(0, 10) : "date unknown";
const name = (c) => (c.identity && c.identity.legal_name) || "(identity not resolved)";
const statusBadge = (c) => el("span", {class: "badge " + (c.status === "completed" ? "ok" : "bad")}, c.status || "unknown");
const companyBadge = (c) => c.company_status ? el("span", {class: "badge " + (c.company_status === "complete" ? "ok" : c.company_status === "partial" ? "warn" : "bad")}, c.company_status.replace(/_/g, " ")) : null;

$("title").textContent = DATA.title;
$("runmeta").textContent = [DATA.run.run_id && ("run " + DATA.run.run_id), DATA.run.started_at && ("started " + DATA.run.started_at), DATA.companies.length + " rows"].filter(Boolean).join(" · ");

const flags = {
  errors: (c) => c.errors.length > 0,
  changes: (c) => c.changes.some((x) => x.change_type !== "unavailable"),
  website: (c) => !!c.areas.websites,
  sparse: (c) => !!c.sparse,
  carried: (c) => c.claims.some((x) => x.carried),
};
let selected = null;
function render() {
  const q = $("q").value.trim().toLowerCase();
  const st = $("fstatus").value, fl = $("fflag").value;
  const list = $("list"); list.replaceChildren();
  let shown = 0;
  DATA.companies.forEach((c, index) => {
    if (st && c.company_status !== st && c.status !== st) return;
    if (fl && !flags[fl](c)) return;
    if (q && !(name(c).toLowerCase().includes(q) || String(c.org || c.input || "").includes(q.replace(/\s/g, "")))) return;
    shown++;
    const li = el("li", {role: "option", tabindex: "0", "aria-selected": String(index === selected)},
      el("div", {class: "name"}, name(c)),
      el("div", {class: "sub"}, String(c.org || c.input || "no number"), statusBadge(c), companyBadge(c), c.errors.length ? el("span", {class: "badge warn"}, c.errors.length + " error" + (c.errors.length > 1 ? "s" : "")) : null, c.sparse ? el("span", {class: "badge"}, "registry only") : null));
    li.addEventListener("click", () => select(index));
    li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(index); } });
    list.append(li);
  });
  $("count").textContent = shown + " of " + DATA.companies.length + " shown";
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
function table(headers, rows) {
  return el("table", {}, el("thead", {}, el("tr", {}, headers.map((h) => el("th", {}, h)))), el("tbody", {}, rows.map((r) => el("tr", {}, r.map((v, i) => el("td", {"data-label": headers[i]}, v))))));
}
function select(index) {
  selected = index;
  const c = DATA.companies[index];
  const d = $("detail");
  d.replaceChildren();
  const back = el("button", {id: "back", type: "button"}, "← Companies");
  back.addEventListener("click", () => { document.body.classList.remove("showing"); });
  d.append(back);
  d.append(el("h2", {}, name(c)));
  d.append(el("div", {class: "sub"}, "Organisation number " + (c.org || c.input || "?"), statusBadge(c), companyBadge(c), "input row " + c.pos));
  const id = c.identity || {};
  d.append(el("section", {}, el("h3", {}, "Identity"), el("dl", {class: "kv"},
    Object.entries(id).filter(([, v]) => v !== null && v !== undefined && typeof v !== "object").map(([k, v]) => [el("dt", {}, k.replace(/_/g, " ")), el("dd", {}, String(v))])),
    c.status_reasons.length ? el("div", {class: "sub"}, "Status reasons: " + c.status_reasons.join("; ")) : null));
  if (c.overview) d.append(el("p", {class: "overview"}, c.overview));
  for (const sec of c.sections) d.append(el("section", {}, el("h3", {}, sec.title), sec.statements.map((s) => statement(c, s))));
  const facts = c.claims.filter((x) => x.state === "available");
  d.append(el("section", {}, el("h3", {}, "Facts (" + facts.length + ") — FACT → SOURCE → DATE"), table(["Category", "Field", "Value", "Period", "Source", "Retrieved"], facts.map((x) => {
    const ev = c.evidence[x.ev[0]] || {}; const url = safeUrl(ev.url);
    return [x.cat, x.field + (x.carried ? " (retained)" : ""), x.value, x.period, url ? el("a", {href: url, target: "_blank", rel: "noopener noreferrer", title: url}, (ev.class || "source").replace(/_/g, " ")) : (ev.class || ""), day(ev.at)];
  }))));
  const unknown = c.claims.filter((x) => x.state !== "available");
  if (unknown.length) d.append(el("section", {}, el("h3", {}, "Unknowns (" + unknown.length + ")"), table(["Category", "Field", "State", "Reason"], unknown.map((x) => [x.cat, x.field, x.state, x.reason || ""]))));
  d.append(el("section", {}, el("h3", {}, "Changes since previous run"), c.refresh && c.refresh.compared ? (c.changes.length ? table(["Type", "Field / module", "Old", "New", "Period", "Dates"], c.changes.map((x) => [x.change_type, x.field || x.module, x.old_value || (x.fields_retained ? "retained: " + x.fields_retained.join(", ") : ""), x.new_value || "", x.period ? x.period.from + "–" + x.period.to : "", [x.previous_at && ("was " + day(x.previous_at)), x.source_at && ("now " + day(x.source_at)), x.last_verified_at && ("last verified " + day(x.last_verified_at))].filter(Boolean).join(" · ")])) : el("div", {}, "No changes.")) : el("div", {}, (c.refresh && c.refresh.reason) || "Not compared.")));
  if (c.errors.length) d.append(el("section", {}, el("h3", {}, "Errors (" + c.errors.length + ")"), table(["Code", "Stage", "Message"], c.errors.map((x) => [x.code, x.stage || "", x.message || ""]))));
  d.append(el("section", {}, el("h3", {}, "Sources consulted"), table(["Module", "State", "Note"], Object.entries(c.modules).map(([k, v]) => [k, v.state || "", v.note || ""]))));
  document.body.classList.add("showing");
  d.scrollTop = 0;
  render();
}
for (const id of ["q", "fstatus", "fflag"]) $(id).addEventListener("input", render);
render();
if (DATA.companies.length && window.matchMedia("(min-width: 761px)").matches) select(0);
</script>
</body>
</html>
"""
