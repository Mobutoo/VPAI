#!/bin/bash
set -euo pipefail
URL=http://localhost:8082
ERRORS=0

echo "=== SMOKE DRY-RUN ==="
START=$(curl -sf -X POST "$URL/api/produce/start" \
  -H "Content-Type: application/json" \
  -d '{"title": "Smoke Porsche", "camera": "ARRI", "lens": "anamorphic"}')
JOB=$(echo "$START" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "JOB: $JOB"

step() {
  local s="$1" e="$2"
  R=$(curl -sf -X POST "$URL/api/produce/step" \
    -H "Content-Type: application/json" \
    -d "{\"job_id\": \"$JOB\", \"step\": \"$s\", \"params\": {$e}}" 2>&1) || R='{"error":"fail"}'
  S=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null) || S="FAIL"
  echo "  $s: $S"
  if [ "$S" != "ok" ]; then ERRORS=$((ERRORS + 1)); fi
}

step brief '"dry_run": true, "description": "Porsche 911 GT3 neon Tokyo"'
step research '"dry_run": true, "skip": true'

# Director scene_prompts
echo "  script (Director)..."
curl -sf -X POST "$URL/api/produce/step" \
  -H "Content-Type: application/json" \
  -d "{\"job_id\": \"$JOB\", \"step\": \"script\", \"params\": {\"dry_run\": true, \"scene_prompts\": [{\"scene_index\":0,\"visual_prompt\":\"Black Porsche 911 GT3 neon Tokyo night\",\"camera_movement\":\"dolly in\",\"mood\":\"dark\",\"duration_seconds\":5}]}}" > /dev/null 2>&1 && echo "  script: ok" || echo "  script: FAIL"

step storyboard '"dry_run": true'
step voiceover '"dry_run": true, "skip": true'
step music '"dry_run": true, "skip": true'
step imagegen '"dry_run": true'
step videogen '"dry_run": true'
step montage '"dry_run": true'
step subtitles '"dry_run": true, "skip": true'
step colorgrade '"dry_run": true, "skip": true'
step review '"dry_run": true, "skip": true'
step export '"dry_run": true, "skip": true'
step publish '"dry_run": true, "skip": true'

echo "=== ERRORS: $ERRORS ==="
exit $ERRORS
