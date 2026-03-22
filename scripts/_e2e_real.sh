#!/bin/bash
set -euo pipefail
URL=http://localhost:8082

echo "=== E2E REAL TEST — Porsche 911 GT3 ($(date)) ==="
echo "  Budget: eco (~$0.30)"

# Start
START=$(curl -sf -X POST "$URL/api/produce/start" \
  -H "Content-Type: application/json" \
  -d '{"title": "Porsche 911 GT3 Neon Tokyo", "camera": "ARRI", "lens": "anamorphic", "style": "cinematic"}')
JOB=$(echo "$START" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "JOB: $JOB"

step() {
  local s="$1"; local extra="$2"
  echo "--- $s ---"
  RESULT=$(curl -sf -X POST "$URL/api/produce/step" \
    -H "Content-Type: application/json" \
    -d "{\"job_id\": \"$JOB\", \"step\": \"$s\", \"params\": {$extra}}" 2>&1) || RESULT='{"error":"curl failed"}'
  STATUS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null) || STATUS="FAIL"
  echo "  $s: $STATUS"
  echo "$RESULT" > /tmp/step_${s}.json
}

# Brief
step brief '"description": "Porsche 911 GT3 noire avec femme elegante en robe noire, nuit neon Tokyo"'

# Research (skip — no video ref)
step research '"skip": true'

# Script — Director scene_prompts (no LLM call)
SCENE_PROMPTS='[
  {"scene_index": 0, "visual_prompt": "Black Porsche 911 GT3 parked under neon lights in Tokyo Shibuya crossing at night, rain-wet asphalt reflecting pink and blue neon signs, cinematic wide shot, moody atmosphere", "camera_movement": "dolly in", "mood": "mysterious", "duration_seconds": 5},
  {"scene_index": 1, "visual_prompt": "Elegant Black woman in sleek black dress stepping out of the Porsche 911 GT3, neon reflections on the car body, shallow depth of field, warm golden highlights mixing with cool neon blue", "camera_movement": "tracking", "mood": "glamorous", "duration_seconds": 5}
]'
echo "--- script (Director prompts) ---"
SCRIPT_RESULT=$(curl -sf -X POST "$URL/api/produce/step" \
  -H "Content-Type: application/json" \
  -d "{\"job_id\": \"$JOB\", \"step\": \"script\", \"params\": {\"scene_prompts\": $SCENE_PROMPTS}}")
echo "  script: $(echo "$SCRIPT_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)"

# Storyboard — REAL image gen (eco)
step storyboard '"budget": "eco"'

# Voiceover — auto-narration from scene_prompts (Kokoro local, free)
step voiceover '{}'
# Music — skip (requires CCX33 render server)
step music '"skip": true'

# ImageGen — REAL (eco)
step imagegen '"budget": "eco"'

# VideoGen — REAL Seedance 5s (eco ~$0.10/clip)
echo "--- videogen (REAL Seedance eco) ---"
VG_RESULT=$(curl -sf -X POST "$URL/api/produce/step" \
  -H "Content-Type: application/json" \
  -d "{\"job_id\": \"$JOB\", \"step\": \"videogen\", \"params\": {\"budget\": \"eco\", \"duration\": 5}}" 2>&1)
echo "  videogen: $(echo "$VG_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('step_result',{}); print(d.get('status','?'), f'videos={len(r.get(\"videogen_results\",[]))}')" 2>/dev/null)"
echo "$VG_RESULT" > /tmp/step_videogen.json

# Montage — REAL Remotion render
echo "--- montage (REAL Remotion) ---"
MONTAGE_RESULT=$(curl -sf -X POST "$URL/api/produce/step" \
  -H "Content-Type: application/json" \
  -d "{\"job_id\": \"$JOB\", \"step\": \"montage\", \"params\": {}}" 2>&1)
echo "  montage: $(echo "$MONTAGE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('step_result',{}); print(d.get('status','?'), r.get('render_method','?'), r.get('note','')[:100])" 2>/dev/null)"
echo "$MONTAGE_RESULT" > /tmp/step_montage.json

# Remaining steps
step subtitles '"skip": true'
step colorgrade '"skip": true'
step review '"skip": true'
step export '"skip": true'
step publish '"skip": true'

echo ""
echo "=== E2E COMPLETE ==="
echo "  Check Telegram for video notification!"
echo "  Job: $JOB"
