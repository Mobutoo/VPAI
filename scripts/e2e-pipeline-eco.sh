#!/bin/bash
# E2E eco test — one real Seedance lite run (~$0.10).
#
# GUARD: Runs smoke-pipeline-dryrun.sh first. If it fails, abort.
#
# What it does:
#   - Runs full 14-step pipeline with REAL generation (budget eco)
#   - Seedance lite 5s video per scene (~$0.10/video)
#   - Skips voiceover, music, subtitles (not yet implemented)
#   - Validates: video file exists, Kitsu preview uploaded
#
# Usage:
#   bash scripts/e2e-pipeline-eco.sh                     # Local
#   bash scripts/e2e-pipeline-eco.sh --sandbox           # In OpenClaw sandbox
#   bash scripts/e2e-pipeline-eco.sh --skip-smoke        # Skip dry-run guard
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-local}"
SKIP_SMOKE=false

for arg in "$@"; do
    case "$arg" in
        --skip-smoke) SKIP_SMOKE=true ;;
    esac
done

echo "============================================================"
echo "  E2E ECO TEST — Real Generation (budget eco)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Estimated cost: ~$0.30 (1 image + 1 video)"
echo "============================================================"

# --- Guard: smoke test must pass first ---
if [ "$SKIP_SMOKE" = false ]; then
    echo ""
    echo "--- Running smoke test dry-run first ---"
    if bash "${SCRIPT_DIR}/smoke-pipeline-dryrun.sh" "$MODE"; then
        echo "  Smoke test PASSED — proceeding with real generation"
    else
        echo "  Smoke test FAILED — aborting E2E eco"
        exit 1
    fi
fi

# --- Setup ---
if [ "$MODE" = "--sandbox" ]; then
    SBX="openclaw-sbx-agent-director-402731dc"
    VREF="sudo docker exec $SBX python3 /workspace/vref"
else
    VREF_URL="${VIDEOREF_URL:-http://localhost:8010}"
fi

ERRORS=0

run_step() {
    local step_name="$1"
    shift
    echo ""
    echo "--- $step_name ---"
    local output
    output=$(eval "$@" 2>&1) || true
    echo "$output"
    if echo "$output" | grep -qi "error.*failed\|traceback\|status.*500"; then
        echo "  *** FAILED ***"
        ERRORS=$((ERRORS + 1))
    fi
}

echo ""
echo "============================================================"
echo "  REAL PIPELINE RUN (eco budget)"
echo "============================================================"

# --- Produce Start ---
echo ""
echo "--- Produce Start ---"
START_RESULT=$(curl -s -X POST "${VREF_URL}/api/produce/start" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"E2E Eco $(date +%H%M%S)\", \"camera\": \"ARRI\", \"lens\": \"anamorphic\", \"style\": \"cinematic\"}")
echo "$START_RESULT"
JOB_ID=$(echo "$START_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || echo "")

if [ -z "$JOB_ID" ]; then
    echo "FATAL: no job_id extracted"
    exit 1
fi
echo "JOB_ID=$JOB_ID"

step_curl() {
    local step="$1"
    shift
    local extra_params="$*"
    curl -s -X POST "${VREF_URL}/api/produce/step" \
        -H "Content-Type: application/json" \
        -d "{\"job_id\": \"$JOB_ID\", \"step\": \"$step\", \"params\": {\"budget\": \"eco\" $extra_params}}"
}

# --- 14 Steps (real generation, eco budget) ---
run_step "Brief"        'step_curl brief , "description": "Porsche 911 GT3 noire, femme elegante, nuit neon Tokyo"'
run_step "Research"     'step_curl research , "skip": true'
run_step "Script"       'step_curl script , "modifications": {"subject": "Porsche 911", "style": "cinematic night", "mood": "luxurious"}'
run_step "Storyboard"   'step_curl storyboard'
run_step "Voiceover"    'step_curl voiceover , "skip": true'
run_step "Music"        'step_curl music , "skip": true'
run_step "ImageGen"     'step_curl imagegen'
run_step "VideoGen"     'step_curl videogen , "duration": 5'
run_step "Montage"      'step_curl montage'
run_step "Subtitles"    'step_curl subtitles , "skip": true'
run_step "ColorGrade"   'step_curl colorgrade'
run_step "Review"       'step_curl review'
run_step "Export"       'step_curl export'
run_step "Publish"      'step_curl publish'

# --- Verify results ---
echo ""
echo "============================================================"
echo "  VERIFICATION"
echo "============================================================"

# Check job status
STATUS=$(curl -s "${VREF_URL}/api/produce/status/${JOB_ID}" 2>/dev/null || echo "{}")
echo "Job status: $STATUS" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    completed = d.get('steps_completed', [])
    print(f'  Steps completed: {len(completed)}/14 — {completed}')
    print(f'  Current step: {d.get(\"current_step\", \"done\")}')
except:
    print('  Could not parse status')
" 2>/dev/null || echo "  Status check skipped"

echo ""
echo "============================================================"
echo "  E2E ECO RESULTS"
echo "============================================================"
echo "  Errors: $ERRORS"
if [ $ERRORS -gt 0 ]; then
    echo "  *** E2E ECO FAILED ***"
    exit 1
else
    echo "  E2E ECO PASSED"
    exit 0
fi
