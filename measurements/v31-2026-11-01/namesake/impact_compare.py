"""Every published unit and every operator decision that the namesake rules change, per captured set, with labels."""
import csv
import glob
import json
import sys
from pathlib import Path

ROOT = Path("/home/user/signalpost-agent")
sys.path.insert(0, str(ROOT / "src"))
from norway_company_agent.audit import read_envelopes, unit_key  # noqa: E402

S = Path("SCRATCH/m")
M = ROOT / "measurements/v31-2026-11-01"
FIELDS = ("social_profile", "news_item", "careers_page", "job_posting", "official_website")
labels = {}
for f in glob.glob(str(ROOT / "measurements/v3-2026-11-01/audits/*/items.labelled.csv")) + [str(S / "audit-diag80/items.labelled.csv"),
        str(ROOT / "measurements/v3-remediation-2026-11-01/audits/eval120/items.labelled.csv"), str(M / "audits/eval200/items.labelled.csv"),
        str(M / "audits/eval200b/items.labelled.csv"), str(S / "dev-corrected.labelled.csv")]:
    if Path(f).exists():
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r.get("verdict"):
                labels[r["uid"]] = r["verdict"]


def units(path):
    found = {}
    for envelope in read_envelopes(path):
        org = str(envelope.get("organisation_number"))
        for claim in envelope.get("claims") or []:
            if claim.get("availability") == "available" and claim.get("field") in FIELDS:
                key = unit_key(claim)
                if key:
                    found[f"{org}|{claim['field']}|{key}"] = envelope.get("company", {}).get("name") or org
    return found


def operators(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            p = json.loads(line)
            site = ((p.get("evidence") or {}).get("site_research") or {}).get("value") or {}
            if site.get("operator"):
                out[p["organisation_number"]] = (site["operator"].get("kind"), site["operator"].get("code"))
    return out


total = {"removed": 0, "added": 0}
for s in ("smoke100", "midsize40", "fresh60", "fresh60b", "diag80", "eval120", "eval200", "eval200b"):
    old_dir = S / ("f2-eval200b" if s == "eval200b" else f"p-anchored-{s}")
    new_dir = S / f"ns-{s}"
    old, new = units(old_dir / "envelopes.jsonl"), units(new_dir / "envelopes.jsonl")
    removed, added = sorted(set(old) - set(new)), sorted(set(new) - set(old))
    oo, no = operators(old_dir / "profiles.jsonl"), operators(new_dir / "profiles.jsonl")
    op_changes = {org: (oo.get(org), no.get(org)) for org in set(oo) | set(no) if oo.get(org) != no.get(org)}
    total["removed"] += len(removed); total["added"] += len(added)
    print(f"== {s}: companies {len(oo)} with a site; units removed {len(removed)}, added {len(added)}; operator changes {len(op_changes)}")
    for org, (a, b) in sorted(op_changes.items()):
        print(f"   operator {org}: {a} -> {b}")
    for uid in removed:
        print(f"   REMOVED [{labels.get(uid, 'unlabelled')}] {uid[:120]}")
    for uid in added:
        print(f"   ADDED   [{labels.get(uid, 'unlabelled')}] {uid[:120]}")
print(total)
