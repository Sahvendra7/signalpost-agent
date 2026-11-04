"""Build the independent final-evaluation set evalg250 (drawn 2026-11-04 before any prompt existed).

Census of every news unit published by either arm:
  * base = live capture through the permissive baseline ff3b515 (the candidate pool);
  * v31  = replay of those exact bytes through a clean worktree of the release code 334a085, with every withheld
           candidate's reason logged (replay_with_reasons.py).
Packets use the captured source page (feed entry / listing card) from the snapshots, and the item's own page from the
snapshots when the baseline fetched it, otherwise a deterministic live capture made the same day.

    uv run python measurements/v32-gemini-2026-11-04/build_evalg250.py BASE_DIR V31_DIR
Writes datasets/evalg250.items.jsonl (arms, V3.1 status/reason; label empty), datasets/evalg250.packets.jsonl.gz, and
audits/evalg250/sheet.md (the blind labelling sheet: captured text only, no arm, no reason, no model output).
"""
import gzip, hashlib, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.llm_experiments.capture import CaptureStore, Fetcher, capture_many, norm_url  # noqa: E402
from norway_company_agent.llm_experiments.datasets import item_key, news_claims, org_context, packet_for, read_envelopes, section_of  # noqa: E402
from norway_company_agent.replay import entries_from_profile  # noqa: E402

HERE = Path(__file__).resolve().parent
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


def v31_reason(org, value):
    url, date, title = norm_url(value.get("url")), str(value.get("publication_date") or "")[:10], (value.get("title") or "").strip().casefold()
    for r in reasons.get(org, []):
        if (norm_url(r.get("url")) == url or (r.get("title") or "").strip().casefold() == title) and str(r.get("date") or "")[:10] == date:
            return r["reason"]
    for r in reasons.get(org, []):
        if (r.get("title") or "").strip().casefold() == title:
            return r["reason"]
    return None


items = {}
for org in base:
    for arm, envs in (("base", base), ("v31", v31)):
        for c in news_claims(envs.get(org) or {}):
            v = c["value"]
            key = item_key(org, v)
            row = items.setdefault(key, {"dataset": "evalg250", "org": org, "company": (envs[org].get("identity") or {}).get("legal_name"),
                                         "title": v.get("title"), "url": v.get("url"), "date": str(v.get("publication_date") or "")[:10],
                                         "source_url": c.get("source_page") or v.get("url"), "method": c.get("method"),
                                         "date_text": v.get("date_text"), "summary": v.get("summary"), "arms": []})
            row["arms"].append(arm)
for key, row in items.items():
    row["item_id"] = f"{row['org']}|news_item|{norm_url(row['url'])}|{row['date']}|{hashlib.sha1(key.encode()).hexdigest()[:8]}"
    if "v31" in row["arms"]:
        row["v31_status"], row["v31_reason"] = "published", None
    else:
        reason = v31_reason(row["org"], {"url": row["url"], "publication_date": row["date"], "title": row["title"]})
        row["v31_status"] = "withheld" if reason else "absent"
        row["v31_reason"] = reason
    row["v31_hard_reject"] = row["v31_reason"] in HARD
    row["label"], row["label_note"] = None, None

store = CaptureStore(ROOT / "out/v32/captures")
ctxs = {org: org_context(env) for org, env in v31.items()}
# seed the capture store with the baseline's own snapshots (same bytes the pipeline judged)
for org, entries in snap.items():
    for url, e in entries.items():
        if e.get("path") and e["kind"] == "site" and store.get(url) is None:
            raw = Path(e["path"]).read_bytes()
            store.put({"url": url, "site_url": ctxs.get(org, {}).get("site_url"), "status": 200, "error": None, "sha256": hashlib.sha256(raw).hexdigest(),
                       "retrieved_at": e["retrieved_at"], "origin": "baseline_snapshot", "bytes": len(raw)}, raw)
jobs = set()
for row in items.values():
    site = ctxs.get(row["org"], {}).get("site_url")
    if site:
        jobs.add((site, site))
        if row["url"] and norm_url(row["url"]) != norm_url(row["source_url"]):
            jobs.add((row["url"], site))
fetched = capture_many(Fetcher(store, delay_s=1.0), sorted(jobs), workers=8)
print("pages:", len(jobs), "ok:", sum(bool(r.get("sha256")) for r in fetched))

ordered = sorted(items.values(), key=lambda r: (r["org"], r["date"], r["title"] or ""))
(HERE / "datasets").mkdir(exist_ok=True)
(HERE / "audits/evalg250").mkdir(parents=True, exist_ok=True)
with (HERE / "datasets/evalg250.items.jsonl").open("w", encoding="utf-8") as fh:
    for row in ordered:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
packets = []
with gzip.open(HERE / "datasets/evalg250.packets.jsonl.gz", "wt", encoding="utf-8") as fh:
    for row in ordered:
        src = snap.get(row["org"], {}).get(row["source_url"]) or {}
        raw = Path(src["path"]).read_bytes() if src.get("path") else None
        pk = packet_for(row, ctxs[row["org"]], store, source_raw=raw)
        packets.append(pk)
        fh.write(json.dumps(pk, ensure_ascii=False) + "\n")
with (HERE / "audits/evalg250/sheet.md").open("w", encoding="utf-8") as fh:
    for n, (row, pk) in enumerate(zip(ordered, packets), 1):
        tc = pk["target_company"]
        rel = "; ".join(f"{r['relation']}: {r['name']}" for r in tc["known_relationships"][:4])
        fh.write(f"## {n}. {tc['legal_name']} ({tc['organisation_number']}) site {pk['website']['url']}{' | ' + rel if rel else ''}\n"
                 f"title: {row['title']}\ndate: {row['date']} ({row['method']}; '{row['date_text']}')  url: {row['url']}  src: {row['source_url']}\n"
                 f"source[{pk['source_text_kind']}]: {(pk['source_text'] or '-')[:700]}\n"
                 f"article: {(pk['article_text'] or '-')[:1400]}\n\n")
from collections import Counter
print(len(ordered), "units;", Counter(tuple(r["arms"]) for r in ordered), Counter(r["v31_status"] for r in ordered),
      Counter(r["v31_reason"] for r in ordered if r["v31_reason"]).most_common(), "article text:", sum(bool(p["article_text"]) for p in packets),
      "source text:", sum(bool(p["source_text"]) for p in packets))
