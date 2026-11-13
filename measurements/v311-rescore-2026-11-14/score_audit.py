"""Score the eval-r300 audit per arm and family (labels: audit/labels.jsonl, assistant, version-blind sheet).

Families other than news are labelled in full for every arm. News is labelled in full for the units V3.1.1 publishes;
the other news units of V3.1 and ff3b515 are estimated from a fixed random sample of 40 each (sample-news-*.json):
estimate = census-correct + sample-rate x non-census count. Unsure units are excluded from precision.
"""
import json, sys, collections
from pathlib import Path
D = Path(__file__).resolve().parent / "audit"
arms_file = Path(sys.argv[1]) if len(sys.argv) > 1 else D / "arms.json"
units = {json.loads(l)["uid"]: json.loads(l) for l in open(D / "units.jsonl")}
labels = {json.loads(l)["uid"]: json.loads(l) for l in open(D / "labels.jsonl")}
arms = json.loads(arms_file.read_text())
census_news = set(arms.get("v311", []))
out = {}
for arm, ids in arms.items():
    row = {}
    for fam in ("official_website", "social_profile", "news_item", "careers_page", "job_posting"):
        fam_ids = [i for i in ids if units[i]["field"] == fam]
        if fam == "news_item" and arm != "v311" and (D / f"sample-news-{arm}.json").exists():
            sample = json.loads((D / f"sample-news-{arm}.json").read_text())
            census = [i for i in fam_ids if i in census_news]
            rest = [i for i in fam_ids if i not in census_news]
            cc = sum(labels[i]["label"] == "correct" for i in census)
            sc = sum(labels[i]["label"] == "correct" for i in sample)
            sw = sum(labels[i].get("category") == "wrong_company" for i in sample)
            row[fam] = {"published": len(fam_ids), "estimated_correct": round(cc + sc / len(sample) * len(rest), 1),
                        "estimated_precision": round((cc + sc / len(sample) * len(rest)) / max(1, len(fam_ids)), 3),
                        "sample": f"{sc}/{len(sample)} correct, {sw} wrong-company", "census_correct": f"{cc}/{len(census)}"}
            continue
        c = collections.Counter(labels[i]["label"] for i in fam_ids)
        wc = sum(labels[i].get("category") in ("wrong_company", "related_not_exact") for i in fam_ids)
        decided = c["correct"] + c["incorrect"]
        row[fam] = {"published": len(fam_ids), "correct": c["correct"], "incorrect": c["incorrect"], "unsure": c["unsure"],
                    "wrong_or_related_company": wc, "precision": round(c["correct"] / decided, 3) if decided else None}
    out[arm] = row
print(json.dumps(out, indent=1, ensure_ascii=False))
