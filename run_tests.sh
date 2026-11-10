#!/bin/bash
# Ruleaza testele agentului (mpv-ul e inlocuit cu unul fals din tests/bin). Iesirea merge in fisiere,
# ca un mpv fals ramas in urma sa nu blocheze scriptul.
cd "$(dirname "$0")/tests" || exit 1
mkdir -p run; for n in "" 6 7 8 9 10 11 12 13 14 16 17; do mkdir -p "cache$n"; done   # foldere de lucru ale testelor (ignorate de git)
fail=0
for t in test*.py; do
  timeout -k 5 280 python3 "$t" > "/tmp/agent-$t.out" 2>&1 < /dev/null; rc=$?
  echo "$t rc=$rc pass=$(grep -c '^PASS' "/tmp/agent-$t.out") fail=$(grep -c '^FAIL\|Traceback' "/tmp/agent-$t.out")"
  [ $rc -ne 0 ] && fail=1
  pkill -f "[t]ests/bin/mpv" 2>/dev/null
  rm -f "/tmp/agent-$t.out"
done
exit $fail
