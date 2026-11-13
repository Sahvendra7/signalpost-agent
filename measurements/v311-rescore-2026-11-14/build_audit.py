"""eval-r300 claim-level audit: one version-blind sheet of every published external claim of three arms.

    python measurements/v311-rescore-2026-11-14/build_audit.py OUT_DIR ARM=ENVELOPES.jsonl [ARM=ENVELOPES.jsonl ...]

Unit = (organisation, field, value key). Families: official_website, social_profile, news_item, job_posting,
careers_page. The sheet (units.jsonl) is shuffled with a fixed seed and carries no arm; arms.json maps units to arms.
Registry claims (Brønnøysund records anchored by organisation number) are not audited here.
"""
import json, random, sys, hashlib
from pathlib import Path

FIELDS = ("official_website", "social_profile", "news_item", "job_posting", "careers_page")
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
units, arms = {}, {}
for spec in sys.argv[2:]:
    arm, path = spec.split("=", 1)
    arms[arm] = []
    for line in open(path, encoding="utf-8"):
        e = json.loads(line)
        for c in e["claims"]:
            if c["availability"] != "available" or c["field"] not in FIELDS:
                continue
            v = c["value"]
            if isinstance(v, str):
                key = v
            else:
                key = str(v.get("url") or "") + " | " + str(v.get("title") or "")
            uid = hashlib.sha256(f"{e['organisation_number']}|{c['field']}|{key}".encode()).hexdigest()[:16]
            arms[arm].append(uid)
            ev = {x["id"]: x for x in e["evidence"]}
            src = [ev[i] for i in c.get("evidence_ids", []) if i in ev]
            units.setdefault(uid, {"uid": uid, "org": e["organisation_number"], "company": e["identity"].get("legal_name"),
                                   "legal_form": e["identity"].get("legal_form"), "field": c["field"], "value": v,
                                   "source_url": src[0]["source_url"] if src else None, "claim_span": src[0].get("claim_span") if src else None})
order = sorted(units); random.Random(20261114).shuffle(order)
with open(out / "units.jsonl", "w", encoding="utf-8") as handle:
    for uid in order:
        handle.write(json.dumps(units[uid], ensure_ascii=False) + "\n")
(out / "arms.json").write_text(json.dumps({arm: sorted(set(ids)) for arm, ids in arms.items()}, indent=0))
print(len(units), {arm: len(set(ids)) for arm, ids in arms.items()})
