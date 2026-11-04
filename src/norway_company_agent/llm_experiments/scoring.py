"""Scoring for the V3.2 news experiments.

Definitions (as in docs/v3-accuracy.md, extended):
  * precision = correct ÷ (correct + incorrect) among published units; "unsure" excluded and reported; Wilson 95% CI,
    plus a company-clustered bootstrap 95% CI (items from one company are not independent);
  * pool coverage = correct published ÷ correct units in the labelled census pool. This is NOT recall: the pool is
    what any arm published, and correct news no arm found is unknown;
  * company coverage = companies with ≥1 correct published ÷ companies with ≥1 correct unit in the pool;
  * baseline retention = correct V3.1-published units still published ÷ correct V3.1-published units;
  * FP = incorrect published; FN = correct pool units not published.
"""
from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from typing import Any, Iterable


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(centre - half, 4), round(centre + half, 4)


def cluster_bootstrap(units: list[tuple[str, bool]], reps: int = 2000, seed: int = 1) -> tuple[float | None, float | None]:
    """95% percentile CI of precision, resampling companies with replacement."""
    by: dict[str, list[bool]] = defaultdict(list)
    for org, ok in units:
        by[org].append(ok)
    orgs = list(by)
    if not orgs:
        return None, None
    rng = random.Random(seed)
    stats = []
    for _ in range(reps):
        k = n = 0
        for org in (rng.choice(orgs) for _ in orgs):
            k += sum(by[org]); n += len(by[org])
        if n:
            stats.append(k / n)
    stats.sort()
    return round(stats[int(0.025 * len(stats))], 4), round(stats[int(0.975 * len(stats)) - 1], 4)


def error_category(note: str | None) -> str:
    n = (note or "").casefold()
    rules = (("job_advertisement", r"job|careers|vacanc|stilling|recruit"),
             ("advice_or_educational", r"advice|guide|listicle|explainer|tips|educat|thought|how-to|innsikt|knowledge"),
             ("opinion_or_promotional_profile", r"opinion|op-ed|appeal|profile|column|debate|kronikk"),
             ("project_or_property_listing", r"reference|project page|listing|property|apartment|portfolio|case"),
             ("product_service_marketing", r"product|marketing|service|blurb|supplier|rental|offer|campaign|promotion|price"),
             ("other_entity_or_unrelated", r"federation|parent|group|sister|another|other entity|publisher|journalism|regulator|law|notice|national|not the company|foreign"),
             ("structural_or_default", r"default|homepage|landing|forside|hei, verden|welcome|static|contact"))
    for name, pattern in rules:
        if re.search(pattern, n):
            return name
    return "other"


def company_type(legal_form: str | None) -> str:
    form = (legal_form or "").upper()
    if form in ("AS", "ASA"):
        return "limited_company"
    if form in ("STI", "FLI", "SA", "BA", "SAM", "BRL", "BBL", "ANNA"):
        return "foundation_association_cooperative"
    if form in ("ENK", "ANS", "DA", "NUF"):
        return "sole_or_partnership_or_foreign"
    return "other"


def score_arm(items: list[dict[str, Any]], published: Iterable[str], *, baseline: Iterable[str] | None = None) -> dict[str, Any]:
    """`items`: the labelled census (item_id, org, label in correct/incorrect/unsure/None, error_category, company_type)."""
    published = set(published)
    by_id = {i["item_id"]: i for i in items}
    pub = [by_id[i] for i in published if i in by_id]
    correct = [i for i in pub if i["label"] == "correct"]
    incorrect = [i for i in pub if i["label"] == "incorrect"]
    unsure = [i for i in pub if i["label"] not in ("correct", "incorrect")]
    decided = len(correct) + len(incorrect)
    pool_correct = [i for i in items if i["label"] == "correct"]
    pool_correct_orgs = {i["org"] for i in pool_correct}
    out: dict[str, Any] = {
        "published": len(pub), "correct": len(correct), "incorrect": len(incorrect), "unsure": len(unsure),
        "precision": round(len(correct) / decided, 4) if decided else None, "precision_wilson95": wilson(len(correct), decided),
        "precision_cluster95": cluster_bootstrap([(i["org"], i["label"] == "correct") for i in correct + incorrect]),
        "false_positives": len(incorrect), "false_negatives": len(pool_correct) - len(correct),
        "pool_coverage": round(len(correct) / len(pool_correct), 4) if pool_correct else None,
        "pool_coverage_wilson95": wilson(len(correct), len(pool_correct)),
        "company_coverage": f"{len({i['org'] for i in correct})}/{len(pool_correct_orgs)}",
        "companies_with_any_published": len({i["org"] for i in pub}),
    }
    if baseline is not None:
        base_correct = [i for i in set(baseline) if by_id.get(i, {}).get("label") == "correct"]
        kept = [i for i in base_correct if i in published]
        out["baseline_retention"] = f"{len(kept)}/{len(base_correct)}"
        out["baseline_retention_rate"] = round(len(kept) / len(base_correct), 4) if base_correct else None
        base_wrong = [i for i in set(baseline) if by_id.get(i, {}).get("label") == "incorrect"]
        out["baseline_errors_removed"] = f"{sum(i not in published for i in base_wrong)}/{len(base_wrong)}"
        out["errors_introduced_vs_baseline"] = sum(1 for i in incorrect if i["item_id"] not in set(baseline))
    out["fp_by_category"] = dict(Counter(i["error_category"] for i in incorrect).most_common())
    pool_wrong = Counter(i["error_category"] for i in items if i["label"] == "incorrect")
    out["errors_removed_by_category"] = {c: f"{pool_wrong[c] - n_fp}/{pool_wrong[c]}" for c, n_fp in
                                         ((c, Counter(i['error_category'] for i in incorrect)[c]) for c in pool_wrong)}
    by_type = {}
    for t in sorted({i["company_type"] for i in items}):
        c = sum(1 for i in correct if i["company_type"] == t)
        w = sum(1 for i in incorrect if i["company_type"] == t)
        pc = sum(1 for i in pool_correct if i["company_type"] == t)
        by_type[t] = {"correct": c, "incorrect": w, "precision": round(c / (c + w), 4) if c + w else None, "pool_coverage": f"{c}/{pc}"}
    out["by_company_type"] = by_type
    return out
