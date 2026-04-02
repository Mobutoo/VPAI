#!/usr/bin/env bash
set -euo pipefail

# af-notify-phase.sh — Notify n8n af-phase-complete webhook
# Usage: ./scripts/af-notify-phase.sh --project <name> --phase <N> --name <phase_name> --summary <text> [--duration <min>] [--files <count>]

usage() {
  cat <<EOF
Usage: $0 --project <name> --phase <N> --name <phase_name> --summary <text> [--duration <min>] [--files <count>]

Required:
  --project   Project name (must match NocoDB exactly, case-sensitive)
  --phase     Phase number (integer)
  --name      Phase name (e.g. "Database Foundation & Auth")
  --summary   Phase summary text

Optional:
  --duration  Duration in minutes (default: 0)
  --files     Files changed count (default: 0)

Environment:
  AF_WEBHOOK_SECRET   Required. The webhook secret for authentication.
  N8N_WEBHOOK_URL     Optional. Default: https://mayi.ewutelo.cloud/webhook/af-phase-complete
EOF
  exit 1
}

# Defaults
PROJECT="" PHASE="" NAME="" SUMMARY="" DURATION=0 FILES=0

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)  PROJECT="$2"; shift 2 ;;
    --phase)    PHASE="$2"; shift 2 ;;
    --name)     NAME="$2"; shift 2 ;;
    --summary)  SUMMARY="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --files)    FILES="$2"; shift 2 ;;
    -h|--help)  usage ;;
    *)          echo "Unknown arg: $1"; usage ;;
  esac
done

# Validate required
[[ -z "$PROJECT" ]] && { echo "Error: --project is required"; usage; }
[[ -z "$PHASE" ]]   && { echo "Error: --phase is required"; usage; }
[[ -z "$NAME" ]]    && { echo "Error: --name is required"; usage; }
[[ -z "$SUMMARY" ]] && { echo "Error: --summary is required"; usage; }
[[ -z "${AF_WEBHOOK_SECRET:-}" ]] && { echo "Error: AF_WEBHOOK_SECRET env var is required"; exit 1; }

WEBHOOK_URL="${N8N_WEBHOOK_URL:-https://mayi.ewutelo.cloud/webhook/af-phase-complete}"

PAYLOAD=$(jq -n \
  --arg project_name "$PROJECT" \
  --argjson phase_number "$PHASE" \
  --arg phase_name "$NAME" \
  --arg summary "$SUMMARY" \
  --argjson duration_min "$DURATION" \
  --argjson files_changed "$FILES" \
  '{
    project_name: $project_name,
    phase_number: $phase_number,
    phase_name: $phase_name,
    summary: $summary,
    duration_min: $duration_min,
    files_changed: $files_changed,
    decisions: []
  }')

HTTP_CODE=$(curl -s -o /tmp/af-phase-response.json -w "%{http_code}" \
  -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-AF-Secret: $AF_WEBHOOK_SECRET" \
  -d "$PAYLOAD")

RESPONSE=$(cat /tmp/af-phase-response.json)

if [[ "$HTTP_CODE" == "200" ]]; then
  echo "OK: Phase $PHASE ($NAME) logged for $PROJECT"
  echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
  exit 0
else
  echo "FAIL: HTTP $HTTP_CODE"
  echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
  exit 1
fi
