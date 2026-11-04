"""Draw the V3.2 Gemini final-evaluation sample (evalg250) before any prompt exists.

Universe (as diag80/eval120/eval200/eval200b): Brreg enheter with a registered website, not bankrupt, not under
liquidation; excluding every 9-digit organisation number that occurs anywhere in the repository's measurements,
tests, data and docs (over-exclusion is safe). Seeded; the registry file's SHA-256 is recorded.

    python measurements/v32-gemini-2026-11-04/draw_sample.py REGISTRY.csv.gz OUT.jsonl SEED COUNT
"""
import csv, gzip, hashlib, io, json, random, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
registry, out, seed, count = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])

used = set()
files = subprocess.run(["git", "ls-files", "measurements", "tests", "data", "docs", "scripts"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
for name in files:
    path = ROOT / name
    try:
        raw = gzip.decompress(path.read_bytes()) if name.endswith(".gz") else path.read_bytes()
    except Exception:
        continue
    used.update(re.findall(rb"(?<!\d)([89]\d{8})(?!\d)", raw))
used = {u.decode() for u in used}

eligible = []
with gzip.open(registry, "rt", encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle):
        org = row.get("organisasjonsnummer", "")
        if not org or org in used:
            continue
        if not (row.get("hjemmeside") or "").strip():
            continue
        if (row.get("konkurs") or "").lower() == "true" or (row.get("underAvvikling") or "").lower() == "true":
            continue
        if (row.get("underTvangsavviklingEllerTvangsopplosning") or "").lower() == "true":
            continue
        eligible.append(org)
eligible.sort()
chosen = random.Random(seed).sample(eligible, count)
out.write_text("".join(json.dumps({"organisation_number": o}) + "\n" for o in chosen))
meta = {"seed": seed, "count": count, "eligible": len(eligible), "excluded_repo_org_numbers": len(used),
        "registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(), "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
print(json.dumps(meta))
