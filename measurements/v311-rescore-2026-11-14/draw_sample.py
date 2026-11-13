"""Draw eval-r300, the V3.1.1 post-freeze audit sample, after the V3.1.1 rules were committed (633391e).

Universe as for diag80/eval120/eval200/eval200b/evalg250/evalh400: Brreg enheter with a registered website, not
bankrupt, not under liquidation or forced dissolution; excluding every 9-digit organisation number that occurs in any
file under measurements/, tests/, data/, docs/ or scripts/ on ANY branch of the repository (over-exclusion is safe).

    python measurements/v311-rescore-2026-11-14/draw_sample.py REGISTRY.csv.gz OUT.jsonl SEED COUNT
"""
import csv, gzip, hashlib, json, random, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
registry, out, seed, count = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
git = lambda *args: subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout
used = set()
refs = [ref for ref in git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes").decode().split() if not ref.endswith("/HEAD")]
blobs = set()
for ref in refs:
    for line in git("ls-tree", "-r", ref, "--", "measurements", "tests", "data", "docs", "scripts").decode().splitlines():
        meta, name = line.split("\t", 1)
        blobs.add((meta.split()[2], name))
for sha, name in sorted(blobs):
    raw = git("cat-file", "blob", sha)
    if name.endswith(".gz"):
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    used.update(re.findall(rb"(?<!\d)([89]\d{8})(?!\d)", raw))
used = {u.decode() for u in used}
eligible = []
with gzip.open(registry, "rt", encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle):
        org = row.get("organisasjonsnummer", "")
        if not org or org in used or not (row.get("hjemmeside") or "").strip():
            continue
        if any((row.get(key) or "").lower() == "true" for key in ("konkurs", "underAvvikling", "underTvangsavviklingEllerTvangsopplosning")):
            continue
        eligible.append(org)
eligible.sort()
chosen = random.Random(seed).sample(eligible, count)
out.write_text("".join(json.dumps({"organisation_number": o}) + "\n" for o in chosen))
print(json.dumps({"seed": seed, "count": count, "eligible": len(eligible), "excluded_repo_org_numbers": len(used), "refs_scanned": len(refs),
                  "registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(), "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest()}))
