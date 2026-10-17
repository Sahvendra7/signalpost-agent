#!/bin/bash
# one.sh <tree> <label> <test-node> [slowfsync]  -> <label>.out, <label>.err, appends "<label> exit=N verdict" to results.txt
# A run without a pytest summary line is INCOMPLETE and counts as a failure.
R=/tmp/claude-0/-home-user-signalpost-agent/3e43140a-eb25-5545-aa91-a0fabc1c685e/scratchpad/release/stress
cd "$1"
if [ "${4:-}" = slowfsync ]; then export PYTHONPATH=$R; fi
timeout 300 uv run --with pytest pytest -q -p no:cacheprovider --tb=short "$3" > $R/$2.out 2> $R/$2.err
code=$?
summary=$(grep -E '[0-9]+ (passed|failed)' $R/$2.out | tail -1)
if [ -z "$summary" ]; then verdict=INCOMPLETE; elif [ $code -eq 0 ]; then verdict=PASS; else verdict=FAIL; fi
echo "$2 exit=$code $verdict | $summary | $(grep -hE '^E +AssertionError' $R/$2.out | head -1)" >> $R/results.txt
