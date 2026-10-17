#!/bin/bash
# Same-day live runs for docs/c300-revision.md: Revision 1 then the C300 revision on the committed 100-company
# smoke set, a refresh of the C300 revision against its own profiles, and the reported company 911771098.
# The documented command exactly as in docs/final-submission-manifest.md (no viewer flag), 8 workers, no --bulk,
# snapshots on, host audit.
#
#   WORK=/some/dir  R1=<worktree at 05d7566>  NEW=<worktree at the candidate>  ./run_all.sh
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
echo '{"organisation_number": "911771098"}' > "$WORK/hjs.jsonl"
run r1-100 "$R1" "$IN100" 100
run new-100 "$NEW" "$IN100" 100
run new-100-refresh "$NEW" "$IN100" 100 --previous-profiles "$WORK/out/new-100/profiles.jsonl"
run new-911771098 "$NEW" "$WORK/hjs.jsonl" 1
# Then: uv run python measurements/c300-revision-2026-10-17/analyse.py $WORK/out
