#!/bin/bash
# V3.1.2 release validation (live). Run from a clean worktree of the candidate commit:
#   WORK=/some/dir TREE=<clean worktree> ./measurements/v312-final-2026-11-14/run_validation.sh
# 1. the fixed smoke100 (measurements/submission-smoke-2026-10-03/input-companies.jsonl) and its refresh through the
#    run history; 2. the reproduction set of V3.1.1 (evaluator's example, wrong-company cases, positive controls).
# Every run goes through the outbound-host audit hook, as in measurements/v311-rescore-2026-11-14/run_validation.sh.
set -u
ROOT=${TREE:-$(cd "$(dirname "$0")/../.." && pwd)}
IN100=$ROOT/measurements/submission-smoke-2026-10-03/input-companies.jsonl
mkdir -p "$WORK"
printf '{"organisation_number": "%s"}\n' 987832827 961592097 995284766 983181732 980932834 995596970 995159406 990892687 911771098 \
  830872752 937843860 919378875 932383357 929418727 999291988 996926524 996662292 933247813 914823390 984596014 > "$WORK/repro20.jsonl"
run() { # name outdir input count
  local name=$1 out=$2; mkdir -p "$out"; cd "$ROOT"
  git rev-parse HEAD > "$out/$name.commit.txt"; git status --porcelain | wc -l > "$out/$name.dirty-files.txt"; date -u +%FT%TZ > "$out/$name.started.txt"
  rm -rf ~/.cache/python-tldextract
  uv run --locked python "$ROOT/measurements/final-validation-2026-10-03/host_audit.py" "$out/$name.hosts.tsv" -- \
    --organisations "$3" --output "$out/$name.envelopes.jsonl" --profiles-output "$out/$name.profiles.jsonl" \
    --report "$out/$name.report.json" --snapshot-dir "$out/snapshots" --run-id "v312-$name" --expected-count "$4" \
    > "$out/$name.stdout.txt" 2> "$out/$name.stderr.txt"
  echo "exit $?" >> "$out/$name.stdout.txt"; date -u +%FT%TZ > "$out/$name.finished.txt"
}
run live-100 "$WORK/out/smoke" "$IN100" 100
run live-100-refresh "$WORK/out/smoke" "$IN100" 100
run repro20 "$WORK/out/repro" "$WORK/repro20.jsonl" 20
echo done > "$WORK/ALL_DONE"
