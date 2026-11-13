#!/bin/bash
# V3.1.1 validation (live, 2026-11-14). Run from a clean worktree of the candidate commit:
#   WORK=/some/dir TREE=<clean worktree> FF=<clean worktree of ff3b515> ./measurements/v311-rescore-2026-11-14/run_validation.sh
# 1. eval-r300 through the candidate (snapshots kept), then ff3b515 live on the same input the same day;
# 2. the fixed smoke100 and its refresh through the run history; 3. the reproduction set (evaluator's example,
#    wrong-company cases found in the audit, positive controls). Each run goes through the outbound-host audit hook.
set -u
ROOT=${TREE:-$(cd "$(dirname "$0")/../.." && pwd)}
IN100=$ROOT/measurements/submission-smoke-2026-10-03/input-companies.jsonl
INR=$ROOT/measurements/v311-rescore-2026-11-14/inputs/eval-r300.jsonl
mkdir -p "$WORK"
printf '{"organisation_number": "%s"}\n' 987832827 961592097 995284766 983181732 980932834 995596970 995159406 990892687 911771098 \
  830872752 937843860 919378875 932383357 929418727 999291988 996926524 996662292 933247813 914823390 984596014 > "$WORK/repro20.jsonl"
run() { # tree name outdir input count
  local tree=$1 name=$2 out=$3; mkdir -p "$out"; cd "$tree"
  git rev-parse HEAD > "$out/$name.commit.txt"; git status --porcelain | wc -l > "$out/$name.dirty-files.txt"; date -u +%FT%TZ > "$out/$name.started.txt"
  rm -rf ~/.cache/python-tldextract
  uv run --locked python "$tree/measurements/final-validation-2026-10-03/host_audit.py" "$out/$name.hosts.tsv" -- \
    --organisations "$4" --output "$out/$name.envelopes.jsonl" --profiles-output "$out/$name.profiles.jsonl" \
    --report "$out/$name.report.json" --snapshot-dir "$out/snapshots" --run-id "v311-$name" --expected-count "$5" \
    > "$out/$name.stdout.txt" 2> "$out/$name.stderr.txt"
  echo "exit $?" >> "$out/$name.stdout.txt"; date -u +%FT%TZ > "$out/$name.finished.txt"
}
run "$ROOT" eval-r300 "$WORK/out/evalr" "$INR" 300
run "$FF" eval-r300-ff3b515 "$WORK/out/evalr-ff" "$INR" 300
run "$ROOT" live-100 "$WORK/out/smoke" "$IN100" 100
run "$ROOT" live-100-refresh "$WORK/out/smoke" "$IN100" 100
run "$ROOT" repro20 "$WORK/out/repro" "$WORK/repro20.jsonl" 20
echo done > "$WORK/ALL_DONE"
