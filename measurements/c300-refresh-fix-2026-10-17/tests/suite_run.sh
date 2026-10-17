#!/bin/bash
# One full-suite run with captured output: suite_run.sh <repo> <label> [cold]
# cold: remove __pycache__ under src/tests and the tldextract cache first (cold-start conditions).
# A run without a pytest summary line or JUnit file is reported TRUNCATED (never as a pass).
repo=$1; label=$2; out=/tmp/claude-0/-home-user-signalpost-agent/3e43140a-eb25-5545-aa91-a0fabc1c685e/scratchpad/c300r/suite
cd "$repo"
if [ "${3:-}" = cold ]; then find src tests -name __pycache__ -type d -prune -exec rm -rf {} +; rm -rf ~/.cache/python-tldextract; fi
start=$(date +%s.%N)
timeout 900 uv run --with pytest pytest -p no:cacheprovider -rfEs --tb=long --durations=15 --junitxml=$out/$label.xml > $out/$label.log 2>&1
code=$?
end=$(date +%s.%N)
line=$(grep -E '^=+ .*[0-9]+ (passed|failed).* in [0-9.]+s' $out/$label.log | tail -1)
cases=$(python3 -c "import xml.etree.ElementTree as E,sys;r=E.parse(sys.argv[1]).getroot();s=r.find('testsuite') if r.tag=='testsuites' else r;print('junit tests=%s failures=%s errors=%s skipped=%s'%tuple(s.get(k) for k in ('tests','failures','errors','skipped')))" $out/$label.xml 2>/dev/null || echo "junit MISSING")
status=$([ -n "$line" ] && [ "${cases#junit MISSING}" = "$cases" ] && echo ok || echo TRUNCATED)
printf "%s exit=%s secs=%.1f %s | %s | %s\n" "$label" "$code" "$(echo "$end - $start" | bc)" "$status" "$cases" "$line" | tee -a $out/summary.txt
