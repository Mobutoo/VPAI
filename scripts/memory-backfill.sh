#!/bin/bash
# memory-backfill.sh — manual full reindex of a repo on Waza.
#
# Thin wrapper around the Ansible-managed run-and-report.sh, forcing
# --mode full and passing through caller args. The deployed wrapper
# always POSTs the JSON report to the n8n memory-run-report webhook,
# so backfill runs show up in memory_runs alongside scheduled runs.
#
# Must be executed on Waza (the memory worker host).
#
# Usage:
#   scripts/memory-backfill.sh --repo VPAI
#   scripts/memory-backfill.sh --repo VPAI --path docs/ --max-files 200
#   scripts/memory-backfill.sh --repo story-engine --dry-run
#
# Exit code: propagated from the memory worker (0 = ok, non-zero = failure).

set -euo pipefail

WRAPPER="/opt/workstation/ai-memory-worker/run-and-report.sh"

if [[ ! -x "${WRAPPER}" ]]; then
  echo "memory-backfill: wrapper not found at ${WRAPPER}" >&2
  echo "memory-backfill: deploy the llamaindex-memory-worker role first:" >&2
  echo "                 make deploy-workstation" >&2
  exit 2
fi

if [[ "$(hostname)" != "waza" ]] && [[ "$(hostname)" != "waza.local" ]]; then
  echo "memory-backfill: WARNING running on host '$(hostname)', expected 'waza'." >&2
fi

exec "${WRAPPER}" --mode full "$@"
