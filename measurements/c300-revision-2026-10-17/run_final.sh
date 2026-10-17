#!/bin/bash
# The same runs on the final candidate code (6487205, which differs from 7492f32 only in the CLI writing the report
# before the viewer): the 100-company smoke set, its refresh, and 911771098. Run after run_all.sh (uses its hjs.jsonl).
#
#   WORK=/some/dir  FINAL=<worktree at the candidate>  ./run_final.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
IN100=$HERE/../submission-smoke-2026-10-03/input-companies.jsonl
run() { # name tree input count [extra args]
  local out=$WORK/out/$1; mkdir -p "$out"; cd "$2"
  git rev-parse HEAD > "$out/commit.txt"; date -u +%FT%TZ > "$out/started.txt"
  rm -rf ~/.cache/python-tldextract
  uv run --locked python measurements/final-validation-2026-10-03/host_audit.py "$out/hosts.tsv" -- \
    --organisations "$3" --output "$out/envelopes.jsonl" --profiles-output "$out/profiles.jsonl" \
    --report "$out/report.json" --snapshot-dir "$out/snapshots" --run-id "c300-$1" --expected-count "$4" "${@:5}" \
    > "$out/stdout.txt" 2> "$out/stderr.txt"
  echo "exit $?" >> "$out/stdout.txt"; date -u +%FT%TZ > "$out/finished.txt"
}
run final-100 "$FINAL" "$IN100" 100
run final-100-refresh "$FINAL" "$IN100" 100 --previous-profiles "$WORK/out/final-100/profiles.jsonl"
run final-911771098 "$FINAL" "$WORK/hjs.jsonl" 1
# Then: uv run python measurements/c300-revision-2026-10-17/analyse.py $WORK/out
