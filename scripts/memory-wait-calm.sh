#!/bin/bash
# Wait until Waza is calm enough to start an embedding run.

set -euo pipefail

threshold="${MEMORY_WAIT_LOAD_THRESHOLD:-6.0}"
max_checks="${MEMORY_WAIT_MAX_CHECKS:-60}"
delay_sec="${MEMORY_WAIT_DELAY_SEC:-10}"

echo "memory-wait-calm: waiting for loadavg <= ${threshold}"

for _ in $(seq 1 "${max_checks}"); do
  load="$(cut -d" " -f1 /proc/loadavg)"
  echo "$(date +%H:%M:%S) load=${load}"
  if awk -v load="${load}" -v threshold="${threshold}" 'BEGIN { exit(load <= threshold ? 0 : 1) }'; then
    exit 0
  fi
  sleep "${delay_sec}"
done

echo "memory-wait-calm: timeout waiting for loadavg <= ${threshold}" >&2
exit 1
