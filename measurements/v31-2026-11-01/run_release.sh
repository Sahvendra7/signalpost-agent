#!/bin/bash
# V3.1 release validation: the fixed 100 (SHA-256 80eb79e6…), its refresh through the default run history,
# and the eight reproduction companies, each through the outbound-host audit hook. Run from a clean checkout of the
# candidate commit:
#
#   WORK=/some/dir TREE=<clean worktree> ./measurements/v31-2026-11-01/run_release.sh
set -u
ROOT=${TREE:-$(cd "$(dirname "$0")/../.." && pwd)}  # TREE: a clean worktree of the candidate commit
IN100=$ROOT/measurements/submission-smoke-2026-10-03/input-companies.jsonl  # SHA-256 80eb79e6…, identical to measurements/v3-2026-11-01/inputs/smoke100.jsonl
mkdir -p "$WORK"
printf '{"organisation_number": "%s"}\n' 961592097 995284766 983181732 980932834 995596970 995159406 990892687 911771098 > "$WORK/repro8.jsonl"
run() { # name outdir input count [extra args]
  local out=$2; mkdir -p "$out"; cd "$ROOT"
  git rev-parse HEAD > "$out/$1.commit.txt"; git status --porcelain | wc -l > "$out/$1.dirty-files.txt"; date -u +%FT%TZ > "$out/$1.started.txt"
  rm -rf ~/.cache/python-tldextract
  uv run --locked python measurements/final-validation-2026-10-03/host_audit.py "$out/$1.hosts.tsv" -- \
    --organisations "$3" --output "$out/$1.envelopes.jsonl" --profiles-output "$out/$1.profiles.jsonl" \
    --report "$out/$1.report.json" --snapshot-dir "$out/snapshots" --run-id "v31-$1" --expected-count "$4" "${@:5}" \
    > "$out/$1.stdout.txt" 2> "$out/$1.stderr.txt"
  echo "exit $?" >> "$out/$1.stdout.txt"; date -u +%FT%TZ > "$out/$1.finished.txt"
}
run live-100 "$WORK/out/smoke" "$IN100" 100
run live-100-refresh "$WORK/out/smoke" "$IN100" 100   # baseline: the history the first run wrote (published envelopes)
run repro8 "$WORK/out/repro" "$WORK/repro8.jsonl" 8
