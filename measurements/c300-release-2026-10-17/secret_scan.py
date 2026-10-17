"""Secret-pattern scan: patterns of measurements/final-validation-2026-10-03/analyse_run.py plus common token formats.
    python3 secret_scan.py <repo worktree> <output dir>...   (tracked files of the worktree; every file under each output dir)"""
import gzip, re, subprocess, sys
from pathlib import Path
PATTERNS = [re.compile(p) for p in (
    r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", r"\bsk-[A-Za-z0-9]{20,}", r"(?i)api[_-]?key\"?\s*[:=]\s*\"[A-Za-z0-9]{16,}", r"BSA[A-Za-z0-9_-]{20,}",
    r"\bsk-ant-[A-Za-z0-9_-]{20,}", r"\bghp_[A-Za-z0-9]{30,}", r"\bgithub_pat_[A-Za-z0-9_]{30,}", r"\bAKIA[0-9A-Z]{16}\b", r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----")]
def read(path):
    raw = path.read_bytes()
    if path.suffix == ".gz":
        try: raw = gzip.decompress(raw)
        except OSError: pass
    return raw.decode("utf-8", errors="replace")
repo = Path(sys.argv[1])
files = [repo / name for name in subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True).stdout.splitlines()]
for out in sys.argv[2:]:
    files += [p for p in Path(out).rglob("*") if p.is_file()]
hits = 0
for path in files:
    text = read(path)
    for pattern in PATTERNS:
        for match in pattern.finditer(text):
            hits += 1
            print(f"HIT {path}: {pattern.pattern[:30]} ... {match.group(0)[:12]}…")
print(f"scanned {len(files)} files; secret-pattern hits: {hits}")
