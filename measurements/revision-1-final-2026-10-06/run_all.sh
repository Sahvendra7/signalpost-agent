#!/bin/bash
# Back-to-back live runs used for docs/revision-1-final.md: V1 then Revision 1 on the 400 benchmark, then on the
# 1,200 unseen set. Same command and settings for both versions (8 workers, no --bulk, snapshots on, host audit).
#
#   WORK=/some/dir  V1=<worktree at 104c3c4>  R1=<worktree at the candidate>  IN400=<bench400.jsonl>  ./run_all.sh
#
# bench400.jsonl is rebuilt from the public universe (not committed): the fixed sample written by
# scripts/run_source_experiments.py --seed 20261002, then select_entry_batch.py --count 100 with seeds 20261101,
# 20261102 and 20261103, concatenated in that order. Its SHA-256 is in inputs.sha256.
set -u
IN1200=$(cd "$(dirname "$0")/../.." && pwd)/measurements/official-audit-2026-10-03/unseen-1200/input-companies.jsonl
run() { # name tree input count
  local out=$WORK/out/$1; mkdir -p "$out"; cd "$2"
  git rev-parse HEAD > "$out/commit.txt"; date -u +%FT%TZ > "$out/started.txt"
  rm -rf ~/.cache/python-tldextract
  uv run python measurements/final-validation-2026-10-03/host_audit.py "$out/hosts.tsv" -- \
    --organisations "$3" --profiles-output "$out/profiles.jsonl" --output "$out/envelopes.jsonl" \
    --report "$out/report.json" --snapshot-dir "$out/snapshots" --run-id "r1final-$1" --expected-count "$4" --workers 8 \
    > "$out/stdout.txt" 2> "$out/stderr.txt"
  echo "exit $?" >> "$out/stdout.txt"; date -u +%FT%TZ > "$out/finished.txt"
}
run v1-400 "$V1" "$IN400" 400
run r1-400 "$R1" "$IN400" 400
run v1-1200 "$V1" "$IN1200" 1200
run r1-1200 "$R1" "$IN1200" 1200
# Then: uv run python measurements/revision-1-2026-10-04/compare_runs.py $WORK/out/v1-1200 $WORK/out/r1-1200
#       python3 measurements/revision-1-final-2026-10-06/audit_diff.py $WORK/out/v1-1200 $WORK/out/r1-1200
