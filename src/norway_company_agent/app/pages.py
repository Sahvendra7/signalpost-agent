"""The search page (V3 design §B11): one static document. Its script and style are constants, so the server sends a
Content-Security-Policy with their SHA-256 hashes instead of 'unsafe-inline'. The per-process token is the only
variable part, placed in a <meta> element. Text from the server is inserted with textContent only."""
from __future__ import annotations

import base64
import hashlib
import html

STYLE = """
:root{--bg:#f6f6f4;--panel:#fff;--ink:#1d1d1b;--muted:#5d5d58;--line:#dedcd6;--accent:#1f5f8b;--ok:#2d6a3e;--warn:#8a5a00;--bad:#a3322a}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}
header{background:var(--panel);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;justify-content:space-between}
h1{font-size:18px;margin:0}main{max-width:960px;margin:0 auto;padding:16px}
form{display:flex;gap:8px}input[type=search]{flex:1;min-width:0;font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.btn{font:inherit;font-size:14px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);cursor:pointer;text-decoration:none;display:inline-block;white-space:nowrap}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}.btn:disabled{opacity:.5;cursor:default}
.btn:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hint{color:var(--muted);font-size:13px;margin:6px 0 0}.msg{padding:10px 12px;border-radius:8px;background:var(--panel);border:1px solid var(--line);margin:12px 0}
.msg.bad{border-color:var(--bad);color:var(--bad)}h2{font-size:15px;margin:20px 0 8px}
ul.results{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.result{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.result .who{flex:1 1 220px;min-width:0}.result .name{font-weight:600;overflow-wrap:anywhere}.result .sub{color:var(--muted);font-size:13px}
.result .acts{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.badge{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;border:1px solid var(--line);color:var(--muted);margin-left:4px}
.badge.ok{color:var(--ok);border-color:var(--ok)}.badge.warn{color:var(--warn);border-color:var(--warn)}.badge.bad{color:var(--bad);border-color:var(--bad)}
.job{flex-basis:100%;font-size:13px;color:var(--muted)}.job.bad{color:var(--bad)}.job.ok{color:var(--ok)}
.tray{position:sticky;bottom:0;background:var(--panel);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.tray[hidden]{display:none}label.pick{display:inline-flex;gap:4px;align-items:center;font-size:13px;color:var(--muted)}
@media (max-width:600px){header{padding:10px 12px}main{padding:12px}.result .acts{flex-basis:100%}}
"""

SCRIPT = r"""
"use strict";
const $ = (id) => document.getElementById(id);
const TOKEN = document.querySelector('meta[name="signalpost-token"]').content;
const el = (tag, attrs, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? "" : String(v));
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined && kid !== false) node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return node;
};
const picked = new Map();
const STATUS = {completed: "Profile ready", partial: "Profile ready — some sources could not be checked", failed: "Research failed", cancelled: "Cancelled"};
function setMessage(text, bad) { $("message").replaceChildren(text ? el("div", {class: "msg" + (bad ? " bad" : ""), role: bad ? "alert" : "status"}, text) : ""); }
function tray() {
  const n = picked.size;
  $("tray").hidden = n === 0;
  $("traytext").textContent = n + " selected (2–4 to compare)";
  $("cmpgo").disabled = n < 2 || n > 4;
}
$("cmpgo").addEventListener("click", () => { location.href = "/compare?orgs=" + [...picked.keys()].join(","); });
$("cmpclear").addEventListener("click", () => { picked.clear(); document.querySelectorAll("input.pickbox").forEach((b) => { b.checked = false; }); tray(); });
async function api(path, options) {
  const response = await fetch(path, options);
  let body = {};
  try { body = await response.json(); } catch (e) { body = {}; }
  if (!response.ok) throw Object.assign(new Error(body.message || ("Request failed (" + response.status + ")")), {status: response.status, code: body.code});
  return body;
}
function localItem(r) {
  const age = r.age_days === null || r.age_days === undefined ? "" : r.age_days === 0 ? "researched today" : "researched " + r.age_days + " days ago";
  const status = r.terminal_status === "completed" ? el("span", {class: "badge ok"}, "profile") : el("span", {class: "badge bad"}, "research failed");
  const box = el("input", {type: "checkbox", class: "pickbox", "aria-label": "Select " + (r.name || r.org) + " for comparison"});
  box.checked = picked.has(r.org);
  box.addEventListener("change", () => { if (box.checked) picked.set(r.org, r.name); else picked.delete(r.org); tray(); });
  const li = el("li", {class: "result", "data-org": r.org},
    el("div", {class: "who"}, el("div", {class: "name"}, r.name || "(name not resolved)"), el("div", {class: "sub"}, r.org, " · ", age, status, r.stale ? el("span", {class: "badge warn"}, "older than 30 days") : null)),
    el("div", {class: "acts"}, el("a", {class: "btn primary", href: "/company/" + r.org}, "Open profile"), r.stale ? researchButton(r.org, "Re-check") : null, el("label", {class: "pick"}, box, "Compare")));
  return li;
}
function registryItem(r) {
  const flags = [r.deleted ? el("span", {class: "badge bad"}, "deleted") : null, r.bankrupt ? el("span", {class: "badge warn"}, "bankrupt") : null, r.liquidating ? el("span", {class: "badge warn"}, "being wound up") : null];
  return el("li", {class: "result", "data-org": r.org},
    el("div", {class: "who"}, el("div", {class: "name"}, r.name || r.org), el("div", {class: "sub"}, r.org, r.form ? " · " + r.form : "", r.municipality ? " · " + r.municipality : "", flags)),
    el("div", {class: "acts"}, r.deleted ? el("span", {class: "sub"}, "Deleted entities cannot be researched") : researchButton(r.org, "Research this company")));
}
function researchButton(org, text) {
  const b = el("button", {class: "btn", type: "button"}, text);
  b.addEventListener("click", () => research(org, b));
  return b;
}
function jobLine(li) {
  let line = li.querySelector(".job");
  if (!line) { line = el("div", {class: "job", role: "status", "aria-live": "polite"}); li.append(line); }
  return line;
}
async function research(org, button) {
  const li = button.closest("li");
  const line = jobLine(li);
  button.disabled = true;
  line.className = "job"; line.replaceChildren("Starting…");
  let job;
  try {
    job = await api("/api/research", {method: "POST", headers: {"Content-Type": "application/json", "X-Signalpost-Token": TOKEN}, body: JSON.stringify({org})});
  } catch (e) { line.className = "job bad"; line.replaceChildren(e.message); button.disabled = false; return; }
  poll(job, li, button);
}
async function poll(job, li, button) {
  const line = jobLine(li);
  for (;;) {
    if (["queued", "running", "cancelling"].includes(job.state)) {
      const cancel = el("button", {class: "btn", type: "button"}, "Cancel");
      cancel.addEventListener("click", async () => { cancel.disabled = true; try { await api("/api/jobs/" + job.id + "/cancel", {method: "POST", headers: {"Content-Type": "application/json", "X-Signalpost-Token": TOKEN}, body: "{}"}); } catch (e) { /* the next poll shows the state */ } });
      line.className = "job";
      line.replaceChildren(job.state === "queued" ? "Waiting for a free research slot… " : job.state === "cancelling" ? "Cancelling… " : job.stage + " — " + Math.round(job.elapsed_s) + " s ", job.state === "cancelling" ? null : cancel);
      await new Promise((r) => setTimeout(r, 1000));
      try { job = await api("/api/jobs/" + job.id); } catch (e) { line.className = "job bad"; line.replaceChildren(e.message); button.disabled = false; return; }
      continue;
    }
    const parts = [STATUS[job.state] || job.state];
    if (job.message) parts.push(" — " + job.message);
    if (job.state === "partial" && job.result && job.result.partial_sources.length) parts.push(" Not checked: " + job.result.partial_sources.map((s) => s.replace(/_/g, " ")).join(", ") + ".");
    line.className = "job " + (job.state === "completed" ? "ok" : job.state === "partial" ? "" : "bad");
    const links = [];
    if (job.state === "completed" || job.state === "partial") links.push(" ", el("a", {class: "btn primary", href: "/company/" + job.org}, "Open profile"));
    if (job.state !== "completed") { const again = researchButton(job.org, "Try again"); links.push(" ", again); }
    line.replaceChildren(...parts, ...links);
    if (!line.contains(button)) button.remove();  // finished: the result line carries "Open profile" / "Try again"
    return;
  }
}
async function search(q) {
  setMessage("Searching…");
  $("local").replaceChildren(); $("registry").replaceChildren(); $("localh").hidden = true; $("registryh").hidden = true;
  let r;
  try { r = await api("/api/search?q=" + encodeURIComponent(q)); }
  catch (e) { setMessage(e.message, true); return; }
  const localOrgs = new Set(r.local.map((x) => x.org));
  const outside = r.registry.results.filter((x) => !localOrgs.has(x.org));
  $("local").replaceChildren(...r.local.map(localItem));
  $("registry").replaceChildren(...outside.map(registryItem));
  $("localh").hidden = !r.local.length; $("registryh").hidden = !outside.length;
  const notes = [];
  if (!r.local.length && !outside.length) notes.push(r.query_kind === "number" ? "No company with this organisation number was found in the dataset or the registry." : "No match. Check the spelling, or search by organisation number.");
  if (r.registry.error) notes.push("The registry could not be searched just now; only companies already researched are shown.");
  setMessage(notes.join(" "), !!r.registry.error && !r.local.length);
}
$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) { setMessage("Type a company name or organisation number.", true); return; }
  history.replaceState(null, "", "/?q=" + encodeURIComponent(q));
  search(q);
});
const initial = new URLSearchParams(location.search).get("q");
if (initial) { $("q").value = initial; search(initial); }
tray();
"""

BODY = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="signalpost-token" content="__TOKEN__"><meta name="referrer" content="no-referrer">
<title>Signalpost search</title><style>__STYLE__</style></head>
<body><header><h1>Signalpost</h1><nav><a class="btn" href="/whats-new">What's new</a></nav></header>
<main>
<form id="form" role="search"><label for="q" class="visually-hidden" hidden>Company name or organisation number</label>
<input id="q" type="search" name="q" maxlength="100" autocomplete="off" placeholder="Company name or organisation number" aria-label="Company name or organisation number" required>
<button class="btn primary" type="submit">Search</button></form>
<p class="hint">Search __COUNT__ researched companies, or find another company in the official registry and research it now (about a minute; free public sources only).</p>
<div id="message"></div>
<h2 id="localh" hidden>In your dataset</h2><ul class="results" id="local"></ul>
<h2 id="registryh" hidden>In the registry — not researched yet</h2><ul class="results" id="registry"></ul>
</main>
<div class="tray" id="tray" hidden><span id="traytext"></span><span><button class="btn" id="cmpclear" type="button">Clear</button> <button class="btn primary" id="cmpgo" type="button">Compare</button></span></div>
<script>__SCRIPT__</script></body></html>"""


def _hash(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


SEARCH_CSP = (f"default-src 'none'; script-src {_hash(SCRIPT)}; style-src {_hash(STYLE)}; connect-src 'self'; img-src data:; "
              "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def search_page(token: str, companies: int) -> str:
    return (BODY.replace("__STYLE__", STYLE).replace("__SCRIPT__", SCRIPT)
            .replace("__TOKEN__", html.escape(token, quote=True)).replace("__COUNT__", f"{companies:,}"))
