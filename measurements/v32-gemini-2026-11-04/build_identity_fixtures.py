"""Build trimmed, captured fixtures for tests/test_identity_gate.py (registry identity + homepage excerpt + item text).

Excerpts are windows of the captured pages around identity evidence (and the start of the page), with the full page's
sha256 and retrieval time for provenance. Run once; the fixtures are committed.
"""
import gzip, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.identity_gate import target_from_envelope  # noqa: E402
from norway_company_agent.llm_experiments.capture import CaptureStore  # noqa: E402

V = ROOT / "measurements/v32-gemini-2026-11-04"
store = CaptureStore(ROOT / "out/v32/captures")
envs = {}
for path in ("measurements/v32-gemini-2026-11-04/capture-evalg250/v31-evalg250.envelopes.jsonl.gz",
             "measurements/v31-2026-11-01/replay/f2-eval200b/envelopes.jsonl.gz", "measurements/v31-2026-11-01/replay/v31-eval200/envelopes.jsonl.gz"):
    for line in gzip.open(ROOT / path, "rt", encoding="utf-8"):
        e = json.loads(line); envs.setdefault(e["organisation_number"], e)
packets = {}
for name in ("evalg250", "eval200b", "eval200"):
    for line in gzip.open(V / f"datasets/{name}.packets.jsonl.gz", "rt", encoding="utf-8"):
        p = json.loads(line); packets[p["item_id"]] = p


def excerpt(text, patterns, head=1200, window=220):
    parts = [text[:head]]
    for pat in patterns:
        for m in list(re.finditer(pat, text, flags=re.I))[:3]:
            parts.append(text[max(0, m.start() - window): m.end() + window])
    return " … ".join(parts)


def item_text(iid, cap=2500):
    p = packets[iid]
    return "\n".join(filter(None, [p["item"]["title"], (p.get("source_text") or "")[:800], (p.get("article_text") or "")[:cap]]))


def find(org, title_start):
    return next(i for i, p in packets.items() if p["target_company"]["organisation_number"] == org and p["item"]["title"].startswith(title_start))


cases = [  # (fixture id, org, site, [(item title prefix, expected)], expected site status)
    ("valmet_global_group_site", "932383357", "https://www.valmet.com/",
     [("Change in Valmet’s Executive Leadership Team: Pia", "withhold"), ("Valmet to replace Hansol Paper", "withhold")], "group_site"),
    ("logscom_foreign_namesake_site", "830872752", "https://logscom.com/", [], "other_entity"),
    ("matsentralen_ost_network_unit", "915643787", "https://www.matsentralen.no/", [], "group_site"),
    ("rosim_own_site_with_sister_item", "988185701", "https://rosim.no/",
     [("Ny målerigg med NIVUS", "pass"), ("Rammeavtale for vannføringsmåling", "withhold")], "target_operated"),
    ("fram_marine_own_site", "993973645", "https://frammarine.com/", [("10 years with Fram Marine AS", "pass")], "target_operated"),
    ("rybak_brand_only_own_site", "995695987", "https://alexanderrybak.com/", [], "brand_only"),
]
out = []
for fid, org, site, items, expected in cases:
    env = envs.get(org)
    if env is None:
        env = next(e for e in envs.values() if any(c["field"] == "official_website" and c.get("value") == site for c in e["claims"]))
        org = env["organisation_number"]
    t = target_from_envelope(env)
    page = store.page(site)
    pats = [re.escape(org), re.escape(org[:3]) + r"\s?" + re.escape(org[3:6]), r"©", re.escape(t.brand_tokens[0]) + r"\s+(?:Oyj|AB|Oy|AS|ASA)\b" if t.brand_tokens else "x^"]
    if t.street:
        pats.append(re.escape(t.street))
    fx = {"id": fid, "source": "captured", "target": {k: getattr(t, k) for k in ("org", "legal_name", "legal_form", "street", "postal_code", "municipality", "registry_website")} | {"parents": list(t.parents), "group_members": list(t.group_members)},
          "site_url": site, "homepage": {"sha256": page.content_sha256, "retrieved_at": page.retrieved_at, "excerpt": excerpt(page.text, pats)},
          "expected_site_status": expected, "items": []}
    for prefix, exp in items:
        iid = find(org, prefix)
        fx["items"].append({"item_id": iid, "text": item_text(iid), "expected": exp, "provenance": packets[iid]["_provenance"]})
    out.append(fx)
for fx in out:
    if fx["id"] == "logscom_foreign_namesake_site":
        iid = next(i for i, p in packets.items() if p["target_company"]["organisation_number"] == fx["target"]["org"])
        fx["items"].append({"item_id": iid, "text": item_text(iid), "expected": "withhold", "provenance": packets[iid]["_provenance"]})
    if fx["id"] == "matsentralen_ost_network_unit":
        iid = next(i for i, p in packets.items() if p["target_company"]["organisation_number"] == fx["target"]["org"])
        fx["items"].append({"item_id": iid, "text": item_text(iid), "expected": "withhold", "provenance": packets[iid]["_provenance"]})
    if fx["id"] == "rybak_brand_only_own_site":
        iid = next(i for i, p in packets.items() if p["target_company"]["organisation_number"] == fx["target"]["org"] and "Stjernekamp" in p["item"]["title"])
        fx["items"].append({"item_id": iid, "text": item_text(iid), "expected": "pass", "provenance": packets[iid]["_provenance"]})
    (ROOT / f"tests/fixtures/identity_gate/{fx['id']}.json").write_text(json.dumps(fx, ensure_ascii=False, indent=1), encoding="utf-8")
    print(fx["id"], fx["target"]["legal_name"], len(fx["homepage"]["excerpt"]), "chars,", len(fx["items"]), "items")
