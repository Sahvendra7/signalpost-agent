#!/usr/bin/env python3
"""Revision 1 measurement: same-day V1 (evaluated code 104c3c4) vs Revision 1 runs on the same input.

    uv run python measurements/revision-1-2026-10-04/compare_runs.py out/r1/v1-400 out/r1/r1-400 > ...json

For each run: website / social / dated-activity / hiring / fifth-area company coverage and claim counts,
requests, runtime, extraction rejections, and an independent evidence-containment re-check of every
published social, news and job value against the exact snapshot bytes its evidence cites."""
from __future__ import annotations

import collections
import html as html_lib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.site_facts import CapturedPage  # noqa: E402

SOCIAL = {("websites", "social_profile"), ("public_activity", "social_profile")}
ACTIVITY = {("public_activity", "site_activity"), ("public_activity", "news_item")}
JOBS = {("hiring", "job_posting")}
PLATFORM_HOSTS = re.compile(r"(^|\.)(linkedin\.com|facebook\.com|instagram\.com|youtube\.com|x\.com|twitter\.com|tiktok\.com)$")


def family(claim: dict) -> str | None:
    key = (claim.get("category"), claim.get("field"))
    return "social" if key in SOCIAL else "activity" if key in ACTIVITY else "jobs" if key in JOBS else None


def contained(claim: dict, evidence: dict, snapshots: Path) -> bool:
    item = evidence.get((claim.get("evidence_ids") or [None])[0]) or {}
    path = snapshots / str(item.get("snapshot_path") or "")
    if not item.get("snapshot_path") or not path.exists():
        return False
    page = CapturedPage(item.get("source_url") or "", path.read_bytes(), "", "", kind="html")
    value = claim.get("value")
    if family(claim) == "social":
        url = value if isinstance(value, str) else (value or {}).get("url")
        return bool(url) and (url in page.html or html_lib.escape(url) in page.html or url.replace("/", "\\/") in page.html)
    title = (value or {}).get("title")
    if not title or not page.contains(title):
        return False
    if family(claim) == "activity":
        stated = (value or {}).get("date_text")
        if not stated:
            return None  # the claim records no stated date text (V1): the title is contained, the date is unverifiable here
        return page.contains(stated) or stated in page.html or stated in page.unescaped
    return True


def analyse(run: Path) -> dict:
    envelopes = [json.loads(line) for line in (run / "envelopes.jsonl").read_text(encoding="utf-8").split("\n") if line.strip()]
    profiles = [json.loads(line) for line in (run / "profiles.jsonl").read_text(encoding="utf-8").split("\n") if line.strip()]
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    snapshots = run / "snapshots"
    out: dict = {"run": run.name, "commit": (run / "commit.txt").read_text().strip() if (run / "commit.txt").exists() else None, "companies": len(envelopes)}
    companies = collections.Counter()
    claims = collections.Counter()
    not_contained = collections.Counter()
    identity_classes = collections.Counter()
    per_company_site: dict[str, set] = {}
    for envelope in envelopes:
        org = envelope["organisation_number"]
        available = [claim for claim in envelope["claims"] if claim.get("availability") == "available"]
        evidence = {item["id"]: item for item in envelope.get("evidence") or []}
        fams = set()
        for claim in available:
            fam = family(claim)
            if fam:
                fams.add(fam)
                claims[fam] += 1
                verdict = contained(claim, evidence, snapshots)
                if verdict is False:
                    not_contained[fam] += 1
                elif verdict is None:
                    not_contained[f"{fam}_date_text_not_recorded"] += 1
        website = next((claim for claim in available if claim["field"] == "official_website"), None)
        if website:
            companies["website"] += 1
            identity_classes[website.get("identity_class") or website.get("method") or "v1_gate"] += 1
        for fam in fams:
            companies[fam] += 1
        if fams:
            companies["fifth_area"] += 1
        per_company_site[org] = fams | ({"website"} if website else set())
        claims["total_available"] += len(available)
    rejections = collections.Counter()
    articles = 0
    for profile in profiles:
        value = ((profile.get("evidence") or {}).get("site_research") or {}).get("value") or {}
        rejections.update(value.get("extraction_rejections") or {})
        articles += int(value.get("articles_fetched") or 0)
    hosts = sorted({line.split("\t")[1] for line in (run / "hosts.tsv").read_text().splitlines() if "\t" in line}) if (run / "hosts.tsv").exists() else []
    out.update({
        "company_coverage": dict(companies),
        "claims": dict(claims),
        "claims_per_covered_company": {fam: round(claims[fam] / companies[fam], 2) if companies[fam] else 0 for fam in ("social", "activity", "jobs")},
        "evidence_not_contained": dict(not_contained),
        "website_identity_classes": dict(identity_classes),
        "extraction_rejections": dict(rejections.most_common()),
        "articles_fetched": articles,
        "requests": report["operations"]["requests"],
        "runtime_ms": report["runtime_ms"],
        "validation_passed": report["validation"]["passed"],
        "terminal": report.get("terminal_status_counts"),
        "platform_hosts_contacted": [host for host in hosts if PLATFORM_HOSTS.search(host)],
    })
    out["_per_company"] = {org: sorted(fams) for org, fams in per_company_site.items()}
    return out


def main() -> None:
    base, new = analyse(Path(sys.argv[1])), analyse(Path(sys.argv[2]))
    gained = {fam: sorted(org for org in new["_per_company"] if fam in new["_per_company"][org] and fam not in base["_per_company"].get(org, ())) for fam in ("website", "social", "activity", "jobs")}
    lost = {fam: sorted(org for org in base["_per_company"] if fam in base["_per_company"][org] and fam not in new["_per_company"].get(org, ())) for fam in ("website", "social", "activity", "jobs")}
    fifth_new = {org for org, fams in new["_per_company"].items() if set(fams) & {"social", "activity", "jobs"}}
    fifth_base = {org for org, fams in base["_per_company"].items() if set(fams) & {"social", "activity", "jobs"}}
    for item in (base, new):
        item.pop("_per_company")
    print(json.dumps({
        "baseline": base, "revision_1": new,
        "companies_gained": {fam: len(orgs) for fam, orgs in gained.items()}, "companies_lost": {fam: len(orgs) for fam, orgs in lost.items()},
        "fifth_area_gained": len(fifth_new - fifth_base), "fifth_area_lost": len(fifth_base - fifth_new),
        "gained_orgs": gained, "lost_orgs": lost,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
