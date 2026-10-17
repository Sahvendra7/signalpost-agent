"""Substantive V1 -> R1 differences in site-derived claims (representation changes folded away)."""
import json, re, sys
from pathlib import Path
def load(run):
    return {e["organisation_number"]: e for e in (json.loads(l) for l in Path(run, "envelopes.jsonl").read_text().split("\n") if l.strip())}
def key(c):
    v = c["value"]; f = c["field"]
    if f == "social_profile":
        u = v if isinstance(v, str) else v.get("url", "")
        u = re.sub(r"^https?://(www\.|m\.|nb-no\.)?", "", u.split("?")[0]).rstrip("/").lower()
        return ("social", u)
    if f in ("news_item", "site_activity"):
        return ("news", (v.get("title") or "").strip().lower()[:80], str(v.get("publication_date") or v.get("date") or "")[:10])
    if f == "job_posting":
        return ("job", v.get("title"), v.get("url"))
    if f in ("official_website", "careers_page"):
        return (f, str(v).rstrip("/").lower())
def items(env):
    out = {}
    for c in env["claims"]:
        if c["availability"] == "available":
            k = key(c)
            if k:
                out[k] = c
    return out
base, new = load(sys.argv[1]), load(sys.argv[2])
for org, env in new.items():
    a, b = items(base.get(org, {"claims": []})), items(env)
    plus, minus = set(b) - set(a), set(a) - set(b)
    if not plus and not minus:
        continue
    web = next((c for c in env["claims"] if c["field"] == "official_website" and c["availability"] == "available"), None)
    name = next((c["value"] for c in env["claims"] if c["field"] in ("legal_name", "name") and c["availability"] == "available"), "")
    print(f"\n=== {org} {name} | site={web and web['value']} {web and web.get('identity_class')} {web and (web.get('operated_by') or {}).get('name') or ''}")
    for k in sorted(plus, key=str):
        c = b[k]; v = c["value"]
        print("  +", k[0], "::", (v if isinstance(v, str) else json.dumps({x: v.get(x) for x in ("title", "url", "publication_date") if v.get(x)}, ensure_ascii=False))[:230], "::", c.get("source_page") or "", c.get("subject_basis") or "")
    for k in sorted(minus, key=str):
        print("  -", k)
