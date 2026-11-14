"""Compare two runs of the documented command on the same input: published external claims per field family,
company coverage, the official 70/30 coverage formula against the local union, and the claims that differ.

    python measurements/v312-final-2026-11-14/compare_runs.py BASE/envelopes.jsonl CANDIDATE/envelopes.jsonl \
        [--labels LABELS.jsonl] [--diff-out DIFF.jsonl]

What this is and is not:
  * The 70/30 rule (70% share of companies covered, 30% share of individual facts found, per information type) is
    Builderr's published coverage formula. The reference here is the UNION of what the two arms published, optionally
    reduced to claims labelled correct (--labels: {"field","org","value","label"} rows; unlabelled claims count as
    published but are reported separately). Builderr's pool is the verified union over ALL entrants and its own
    crawlers, so these numbers are a relative proxy between two code versions, never a Builderr recall or score.
  * No conversion to the 50 recall points is attempted: the scaling is unpublished ("the top tenth of entries earns
    about 80% of the recall points").
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

FAMILIES = ("official_website", "social_profile", "news_item", "careers_page", "job_posting")


def value_of(claim: dict) -> str:
    value = claim.get("value")
    if isinstance(value, dict):
        return str(value.get("url") or value.get("source_url") or json.dumps(value, sort_keys=True, ensure_ascii=False))
    return str(value)


def published(path: str) -> tuple[dict[tuple[str, str, str], dict], dict[str, dict], int]:
    claims: dict[tuple[str, str, str], dict] = {}
    states: dict[str, dict] = {}
    rows = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        envelope = json.loads(line)
        rows += 1
        org = envelope["organisation_number"]
        evidence = {item["id"]: item for item in envelope.get("evidence", [])}
        for claim in envelope["claims"]:
            if claim["field"] not in FAMILIES:
                continue
            if claim["availability"] == "available":
                first = evidence.get((claim.get("evidence_ids") or [None])[0]) or {}
                claims[(claim["field"], org, value_of(claim))] = {
                    "field": claim["field"], "org": org, "company": (envelope.get("identity") or {}).get("legal_name"), "value": value_of(claim),
                    "title": claim["value"].get("title") if isinstance(claim.get("value"), dict) else None,
                    "date": claim["value"].get("publication_date") if isinstance(claim.get("value"), dict) else None,
                    "source_url": first.get("source_url"), "claim_span": first.get("claim_span"), "confidence": claim.get("confidence"),
                }
            elif claim["field"] == "official_website":
                states[org] = {"availability": claim["availability"], "reason": claim.get("reason")}
    return claims, states, rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return (round(100 * (centre - half), 1), round(100 * (centre + half), 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base")
    parser.add_argument("candidate")
    parser.add_argument("--labels")
    parser.add_argument("--diff-out")
    args = parser.parse_args()
    base, base_states, base_rows = published(args.base)
    cand, cand_states, cand_rows = published(args.candidate)
    labels = {}
    if args.labels:
        for line in Path(args.labels).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                labels[(row["field"], row["org"], row["value"])] = row["label"]
    wrong = {key for key, label in labels.items() if label not in ("correct",)}
    report: dict = {"rows": {"base": base_rows, "candidate": cand_rows}, "families": {}, "reference": "local union of both arms" + (" minus claims labelled other than correct" if labels else "")}
    for family in FAMILIES:
        arms = {}
        union = {key for key in (set(base) | set(cand)) if key[0] == family and key not in wrong}
        union_companies = {key[1] for key in union}
        for name, claims in (("base", base), ("candidate", cand)):
            mine = {key for key in claims if key[0] == family}
            good = mine & union
            companies = {key[1] for key in good}
            company_share = len(companies) / len(union_companies) if union_companies else None
            fact_share = len(good) / len(union) if union else None
            arms[name] = {
                "published": len(mine), "companies_published": len({key[1] for key in mine}),
                "in_reference": len(good), "companies_in_reference": len(companies),
                "company_share": None if company_share is None else round(company_share, 4),
                "fact_share": None if fact_share is None else round(fact_share, 4),
                "weighted_70_30": None if company_share is None else round(0.7 * company_share + 0.3 * fact_share, 4),
            }
        report["families"][family] = {"reference_facts": len(union), "reference_companies": len(union_companies), **arms}
    added = sorted(set(cand) - set(base))
    lost = sorted(set(base) - set(cand))
    report["difference"] = {"added_by_candidate": collections.Counter(key[0] for key in added), "lost_by_candidate": collections.Counter(key[0] for key in lost)}
    if labels:
        report["labels"] = {}
        for name, keys in (("added_by_candidate", added), ("lost_by_candidate", lost), ("candidate_all", sorted(cand)), ("base_all", sorted(base))):
            counted = collections.Counter(labels.get(key, "unlabelled") for key in keys)
            decided = counted["correct"] + sum(count for label, count in counted.items() if label not in ("correct", "unsure", "unlabelled"))
            report["labels"][name] = {"counts": dict(counted), "decided": decided, "correct": counted["correct"],
                                      "precision_of_decided_pct": round(100 * counted["correct"] / decided, 1) if decided else None,
                                      "wilson_95": wilson(counted["correct"], decided) if decided else None}
    transitions = collections.Counter()
    for org in set(base_states) | set(cand_states) | {key[1] for key in set(base) | set(cand) if key[0] == "official_website"}:
        before = "available" if any(key[0] == "official_website" and key[1] == org for key in base) else (base_states.get(org) or {}).get("availability", "none")
        after = "available" if any(key[0] == "official_website" and key[1] == org for key in cand) else (cand_states.get(org) or {}).get("availability", "none")
        if before != after:
            transitions[f"{before} -> {after}"] += 1
    report["official_website_state_changes"] = dict(transitions)
    if args.diff_out:
        with open(args.diff_out, "w", encoding="utf-8") as handle:
            for change, keys, source in (("added", added, cand), ("lost", lost, base)):
                for key in keys:
                    handle.write(json.dumps({"change": change, **source[key]}, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
