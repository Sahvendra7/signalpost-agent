"""Build the independent evaluation set evalh400 (PREREGISTRATION_v2.json), before any labelling or model call.

    uv run python measurements/v32-gemini-2026-11-04/build_evalh400.py BASE_DIR V31_DIR
Census of every news unit published by the permissive baseline (ff3b515) or the release (334a085), capped at 12 units
per company (random, seed 20261106, chosen before labelling). Writes:
  datasets/evalh400.items.jsonl       arms, V3.1 status/reason, identity-gate site and item results (not shown to labellers)
  datasets/evalh400.packets.jsonl.gz  packet v2 (model input)
  audits/evalh400/compact.md          the blind labelling sheet (captured text only)
"""
import gzip, hashlib, json, random, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.identity_gate import assess_item, assess_site, target_from_envelope  # noqa: E402
from norway_company_agent.llm_experiments.capture import CaptureStore, Fetcher, article_text, capture_many, feed_or_card_text, norm_url  # noqa: E402
from norway_company_agent.llm_experiments.datasets import item_key, news_claims, org_context, read_envelopes, section_of  # noqa: E402
from norway_company_agent.llm_experiments.news_contract import build_packet_v2  # noqa: E402
from norway_company_agent.replay import entries_from_profile  # noqa: E402

HERE = Path(__file__).resolve().parent
NAME, CAP, SEED = "evalh400", 12, 20261106
base_dir, v31_dir = Path(sys.argv[1]), Path(sys.argv[2])
base, v31 = read_envelopes(base_dir / "envelopes.jsonl"), read_envelopes(v31_dir / "envelopes.jsonl")
profiles = {json.loads(l)["organisation_number"]: json.loads(l) for l in open(base_dir / "profiles.jsonl", encoding="utf-8") if l.strip()}
snap = {org: entries_from_profile(p, base_dir / "snapshots") for org, p in profiles.items()}
reasons = defaultdict(list)
for line in open(v31_dir / "reasons.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r["kind"] == "activity" and r.get("org"):
        reasons[r["org"]].append(r)
HARD = {"outside_site_section", "outside_verified_site", "sibling_entity_item", "item_not_about_entity_on_other_entity_site",
        "item_not_about_entity_on_group_or_brand_site", "publisher_content_not_about_company", "date_contradicts_title", "media_file",
        "default_cms_post", "page_date_on_non_news_page", "bulk_entry_burst", "no_title", "generic_title", "listing_not_item"}


def v31_reason(org, url, date, title):
    for r in reasons.get(org, []):
        if (norm_url(r.get("url")) == norm_url(url) or (r.get("title") or "").strip().casefold() == (title or "").strip().casefold()) and str(r.get("date") or "")[:10] == date:
            return r["reason"]
    for r in reasons.get(org, []):
        if (r.get("title") or "").strip().casefold() == (title or "").strip().casefold():
            return r["reason"]
    return None


items = {}
for org in base:
    for arm, envs in (("base", base), ("v31", v31)):
        for c in news_claims(envs.get(org) or {}):
            v = c["value"]; key = item_key(org, v)
            row = items.setdefault(key, {"dataset": NAME, "org": org, "company": (envs[org].get("identity") or {}).get("legal_name"), "title": v.get("title"),
                                         "url": v.get("url"), "date": str(v.get("publication_date") or "")[:10], "source_url": c.get("source_page") or v.get("url"),
                                         "method": c.get("method"), "date_text": v.get("date_text"), "summary": v.get("summary"), "arms": []})
            row["arms"].append(arm)
census = sorted(items.items(), key=lambda kv: (kv[1]["org"], kv[1]["date"], kv[1]["title"] or "", kv[0]))
by_org = defaultdict(list)
for key, row in census:
    row["item_id"] = f"{row['org']}|news_item|{norm_url(row['url'])}|{row['date']}|{hashlib.sha1(key.encode()).hexdigest()[:8]}"
    by_org[row["org"]].append(row)
rng = random.Random(SEED)
kept, capped_out = [], 0
for org in sorted(by_org):
    rows = by_org[org]
    if len(rows) > CAP:
        capped_out += len(rows) - CAP
        rows = sorted(rng.sample(rows, CAP), key=lambda r: (r["date"], r["title"] or ""))
    kept += rows
for row in kept:
    if "v31" in row["arms"]:
        row["v31_status"], row["v31_reason"] = "published", None
    else:
        reason = v31_reason(row["org"], row["url"], row["date"], row["title"])
        row["v31_status"], row["v31_reason"] = ("withheld" if reason else "absent"), reason
    row["v31_hard_reject"] = row["v31_reason"] in HARD

store = CaptureStore(ROOT / "out/v32/captures")
ctxs = {org: org_context(env) for org, env in v31.items()}
for org, entries in snap.items():
    for url, e in entries.items():
        if e.get("path") and e["kind"] == "site" and store.get(url) is None:
            raw = Path(e["path"]).read_bytes()
            store.put({"url": url, "site_url": ctxs.get(org, {}).get("site_url"), "status": 200, "error": None, "sha256": hashlib.sha256(raw).hexdigest(),
                       "retrieved_at": e["retrieved_at"], "origin": "baseline_snapshot", "bytes": len(raw)}, raw)
jobs = set()
for row in kept:
    site = ctxs.get(row["org"], {}).get("site_url")
    if site:
        jobs.add((site, site))
        if row["url"] and norm_url(row["url"]) != norm_url(row["source_url"]):
            jobs.add((row["url"], site))
fetched = capture_many(Fetcher(store, delay_s=1.0), sorted(jobs), workers=8)

packets, sites = [], {}
for row in kept:
    ctx = ctxs[row["org"]]; site_url = ctx.get("site_url")
    if (row["org"], site_url) not in sites:
        target = target_from_envelope(v31[row["org"]]); home = store.page(site_url) if site_url else None
        sites[(row["org"], site_url)] = (target, assess_site(target, site_url or "", home.text if home else ""))
    target, site = sites[(row["org"], site_url)]
    src = snap.get(row["org"], {}).get(row["source_url"]) or {}
    raw = Path(src["path"]).read_bytes() if src.get("path") else None
    source_text, kind = feed_or_card_text(raw, row["source_url"], row["url"] or "", row["title"]) if raw else (None, None)
    if not source_text and row.get("summary"):
        source_text, kind = row["summary"], "pipeline_summary"
    art, prov = None, {"captured": False, "reason": "item_url_is_source_page"}
    if row["url"] and norm_url(row["url"]) != norm_url(row["source_url"]) and site_url:
        art, prov = article_text(store, row["url"], site_url, cap=6000)
    gate = assess_item(target, site, "\n".join(filter(None, [row["title"], source_text, art])))
    row["identity_site"] = site.to_dict(); row["identity_item"] = gate.to_dict(); row["identity_gate"] = gate.decision
    packets.append(build_packet_v2(item_id=row["item_id"], target=target, site=site, gate=gate, industry=ctx.get("industry"),
                                   relationships=ctx.get("relationships") or [], title=row["title"], item_url=row["url"], source_url=row["source_url"],
                                   section=section_of(row["url"]), extraction_method=row["method"], date_candidate=row["date"], date_text=row["date_text"],
                                   source_text=source_text, source_text_kind=kind, article_text=art, article_provenance=prov, site_url=site_url))
    row["label"] = None
(HERE / "datasets").mkdir(exist_ok=True)
(HERE / f"audits/{NAME}").mkdir(parents=True, exist_ok=True)
with (HERE / f"datasets/{NAME}.items.jsonl").open("w", encoding="utf-8") as fh:
    for row in kept:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
with gzip.open(HERE / f"datasets/{NAME}.packets.jsonl.gz", "wt", encoding="utf-8") as fh:
    for pk in packets:
        fh.write(json.dumps(pk, ensure_ascii=False) + "\n")
lines, prev = [], None
for n, (row, pk) in enumerate(zip(kept, packets), 1):  # blind sheet: captured text only
    tc = pk["target_company"]
    if tc["organisation_number"] != prev:
        rel = "; ".join(f"{r['relation']}: {r['name']}" for r in tc["known_relationships"][:4])
        lines.append(f"=== {tc['legal_name']} ({tc['organisation_number']}) {tc.get('industry') or ''} | site {pk['website']['url']} {('| ' + rel) if rel else ''}")
        prev = tc["organisation_number"]
    lines.append(f"[{n}] {row['title'][:150]} | {row['date']} {row['method']} | {row['url']}\n  S: {(pk['source_text'] or '-').replace(chr(10), ' ')[:300]}\n"
                 f"  A: {(pk['article_text'] or '-').replace(chr(10), ' ')[:650]}")
(HERE / f"audits/{NAME}/compact.md").write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({"census_units": len(census), "kept_after_cap": len(kept), "capped_out": capped_out, "companies_with_units": len(by_org),
                  "arms": Counter("+".join(r["arms"]) for r in kept), "v31_status": Counter(r["v31_status"] for r in kept),
                  "site_status": Counter(s.status for _, s in sites.values()), "gate": Counter(r["identity_gate"] for r in kept),
                  "pages_fetched": len(jobs), "article_text": sum(bool(p["article_text"]) for p in packets)}, default=str))
