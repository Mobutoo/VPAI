#!/bin/bash
# Smoke test dry-run — validates the full 14-step pipeline without generation.
#
# What it validates (REAL):
#   - LLM scene decomposition (eco models via LiteLLM)
#   - Kitsu project/shot/task creation (auto-hosted, free)
#   - ComfyUI workflow graph validation (submit → cancel, no generation)
#   - Pipeline step orchestration (all 14 steps, correct order)
#
# What it mocks (ZERO COST):
#   - fal.ai video generation (mock URLs)
#   - Remotion render (skip ffmpeg + render)
#   - Image download (placeholder paths)
#
# Usage:
#   bash scripts/smoke-pipeline-dryrun.sh                    # Local (VideoRef on localhost:8010)
#   bash scripts/smoke-pipeline-dryrun.sh --sandbox          # In OpenClaw sandbox
#
# Exit codes: 0 = all steps passed, 1 = failure
set -euo pipefail

MODE="${1:-local}"
ERRORS=0
STEPS_OK=0
TOTAL_STEPS=14

if [ "$MODE" = "--sandbox" ]; then
    SBX="openclaw-sbx-agent-director-402731dc"
    VREF="sudo docker exec $SBX python3 /workspace/vref"
else
    VREF="python3 /workspace/vref 2>/dev/null || curl -s"
    # Detect if vref CLI is available or use curl
    if command -v python3 &>/dev/null && [ -f /workspace/vref ]; then
        VREF="python3 /workspace/vref"
    else
        VREF_URL="${VIDEOREF_URL:-http://localhost:8010}"
        VREF="curl -s -X POST ${VREF_URL}"
        USE_CURL=true
    fi
fi

echo "============================================================"
echo "  SMOKE TEST DRY-RUN — Pipeline E2E (zero cost)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

run_step() {
    local step_name="$1"
    shift
    echo ""
    echo "--- $step_name ---"
    local output
    if [ "${USE_CURL:-}" = "true" ]; then
        output=$(eval "$@" 2>&1) || true
    else
        output=$(eval "$@" 2>&1) || true
    fi
    echo "$output"

    if echo "$output" | grep -qi "error\|failed\|traceback"; then
        echo "  *** FAILED ***"
        ERRORS=$((ERRORS + 1))
    else
        STEPS_OK=$((STEPS_OK + 1))
    fi
}

# --- Produce Start ---
echo ""
echo "--- Produce Start ---"
if [ "${USE_CURL:-}" = "true" ]; then
    START_RESULT=$(curl -s -X POST "${VREF_URL}/api/produce/start" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"Smoke DryRun $(date +%H%M%S)\", \"camera\": \"ARRI\", \"lens\": \"anamorphic\"}")
    echo "$START_RESULT"
    SLUG=$(echo "$START_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('slug',''))" 2>/dev/null || echo "")
    JOB_ID=$(echo "$START_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || echo "")
else
    START_OUTPUT=$($VREF produce-start --title "Smoke DryRun $(date +%H%M%S)" --camera ARRI --lens anamorphic 2>&1)
    echo "$START_OUTPUT"
    SLUG=$(echo "$START_OUTPUT" | grep "Slug:" | awk '{print $2}')
    JOB_ID="${SLUG}"
fi

if [ -z "$SLUG" ] && [ -z "$JOB_ID" ]; then
    echo "FATAL: no slug/job_id extracted"
    exit 1
fi
ID="${JOB_ID:-$SLUG}"
echo "ID=$ID"

# --- 14 Steps with --dry-run ---

if [ "${USE_CURL:-}" = "true" ]; then
    step_curl() {
        local step="$1"
        shift
        local extra_params="$*"
        curl -s -X POST "${VREF_URL}/api/produce/step" \
            -H "Content-Type: application/json" \
            -d "{\"job_id\": \"$ID\", \"step\": \"$step\", \"params\": {\"dry_run\": true $extra_params}}"
    }

    run_step "Brief"        'step_curl brief , "description": "Porsche 911 GT3 noire, femme noire elegante, nuit neon"'
    run_step "Research"     'step_curl research , "skip": true'
    run_step "Script"       'step_curl script , "modifications": {"subject": "Porsche 911", "style": "cinematic night"}'
    run_step "Storyboard"   'step_curl storyboard'
    run_step "Voiceover"    'step_curl voiceover , "skip": true'
    run_step "Music"        'step_curl music , "skip": true'
    run_step "ImageGen"     'step_curl imagegen'
    run_step "VideoGen"     'step_curl videogen'
    run_step "Montage"      'step_curl montage'
    run_step "Subtitles"    'step_curl subtitles , "skip": true'
    run_step "ColorGrade"   'step_curl colorgrade'
    run_step "Review"       'step_curl review'
    run_step "Export"       'step_curl export'
    run_step "Publish"      'step_curl publish'
else
    run_step "Brief"        "$VREF produce-step $ID brief --dry-run --description 'Porsche 911 GT3 noire, femme noire elegante, nuit neon'"
    run_step "Research"     "$VREF produce-step $ID research --dry-run --skip"
    run_step "Script"       "$VREF produce-step $ID script --dry-run --modifications 'subject=Porsche 911,style=cinematic night'"
    run_step "Storyboard"   "$VREF produce-step $ID storyboard --dry-run"
    run_step "Voiceover"    "$VREF produce-step $ID voiceover --dry-run --skip"
    run_step "Music"        "$VREF produce-step $ID music --dry-run --skip"
    run_step "ImageGen"     "$VREF produce-step $ID imagegen --dry-run"
    run_step "VideoGen"     "$VREF produce-step $ID videogen --dry-run"
    run_step "Montage"      "$VREF produce-step $ID montage --dry-run"
    run_step "Subtitles"    "$VREF produce-step $ID subtitles --dry-run --skip"
    run_step "ColorGrade"   "$VREF produce-step $ID colorgrade --dry-run"
    run_step "Review"       "$VREF produce-step $ID review --dry-run"
    run_step "Export"       "$VREF produce-step $ID export --dry-run"
    run_step "Publish"      "$VREF produce-step $ID publish --dry-run"
fi

# --- Summary ---
echo ""
echo "============================================================"
echo "  SMOKE TEST RESULTS"
echo "============================================================"
echo "  Steps OK:     $STEPS_OK / $TOTAL_STEPS"
echo "  Errors:       $ERRORS"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo "  *** SMOKE TEST FAILED ***"
    exit 1
else
    echo "  SMOKE TEST PASSED"
    exit 0
fi
