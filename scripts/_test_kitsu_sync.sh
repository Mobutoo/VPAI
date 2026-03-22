#!/bin/bash
set -euo pipefail
URL=http://localhost:8082
KITSU_URL=${KITSU_URL:-https://boss.ewutelo.cloud}
# Get fresh token from Kitsu directly
KITSU_TOKEN=$(curl -sf -X POST "$KITSU_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@admin.com","password":"mysecretpassword"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "  Kitsu token: ${KITSU_TOKEN:0:20}..."

echo "=== TEST KITSU SYNC — Step by Step ==="

# Helper: check Kitsu projects
kitsu_projects() {
  curl -sf "$KITSU_URL/api/data/projects" \
    -H "Authorization: Bearer $KITSU_TOKEN" 2>/dev/null | \
    python3 -c "import sys,json; ps=json.loads(sys.stdin.read()); [print(f'  {p[\"name\"]} (type={p.get(\"production_type\",\"?\")})') for p in ps]; print(f'  Total: {len(ps)} projects')"
}

# Helper: check Kitsu tasks for a project
kitsu_tasks() {
  local proj_id="$1"
  curl -sf "$KITSU_URL/api/data/projects/$proj_id/tasks" \
    -H "Authorization: Bearer $KITSU_TOKEN" 2>/dev/null | \
    python3 -c "
import sys,json
tasks=json.loads(sys.stdin.read())
for t in tasks:
    name = t.get('task_type_name', t.get('name','?'))
    status = t.get('task_status_name', '?')
    print(f'  Task: {name} → {status}')
print(f'  Total: {len(tasks)} tasks')
" 2>/dev/null || echo "  (no tasks)"
}

echo ""
echo "--- BEFORE: Kitsu projects ---"
kitsu_projects

# Step 1: START (creates job + Kitsu project)
echo ""
echo "=== Step 1: START ==="
START=$(curl -sf -X POST "$URL/api/produce/start" \
  -H "Content-Type: application/json" \
  -d '{"title": "Kitsu Sync Test", "camera": "ARRI", "lens": "anamorphic", "style": "cinematic"}')
JOB=$(echo "$START" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "  JOB: $JOB"
echo "  Kitsu project_id: $(echo "$START" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('kitsu_project_id','none'))" 2>/dev/null)"

echo ""
echo "--- AFTER START: Kitsu projects ---"
kitsu_projects

# Step 2: BRIEF
echo ""
echo "=== Step 2: BRIEF ==="
R=$(curl -sf --max-time 30 -X POST "$URL/api/produce/step" \
  -H "Content-Type: application/json" \
  -d "{\"job_id\": \"$JOB\", \"step\": \"brief\", \"params\": {\"description\": \"Test Porsche 911 GT3 neon Tokyo\"}}" 2>&1)
echo "  status: $(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)"
echo "  kitsu: $(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('step_result',{}).get('kitsu','none'))" 2>/dev/null)"

# Step 3: SCRIPT (with Director scene_prompts)
echo ""
echo "=== Step 3: SCRIPT ==="
R=$(curl -sf --max-time 60 -X POST "$URL/api/produce/step" \
  -H "Content-Type: application/json" \
  -d "{\"job_id\": \"$JOB\", \"step\": \"script\", \"params\": {\"scene_prompts\": [{\"scene_index\":0,\"visual_prompt\":\"Black Porsche 911 GT3 parked on wet Tokyo street, neon reflections, rain, night\",\"camera_movement\":\"slow dolly in\",\"mood\":\"dark cinematic\",\"duration_seconds\":5},{\"scene_index\":1,\"visual_prompt\":\"Black Porsche 911 GT3 side profile driving through neon-lit tunnel, rain drops on window\",\"camera_movement\":\"tracking shot\",\"mood\":\"dark cinematic\",\"duration_seconds\":5}]}}" 2>&1)
echo "  status: $(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)"
echo "  kitsu: $(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('step_result',{}).get('kitsu','none'))" 2>/dev/null)"
echo "  scene_prompts: $(echo "$R" | python3 -c "import sys,json; r=json.load(sys.stdin).get('step_result',{}); print(len(r.get('extras',{}).get('scene_prompts',[])),'scenes')" 2>/dev/null)"

# Check Kitsu after script
echo ""
echo "--- AFTER SCRIPT: Kitsu projects ---"
kitsu_projects

echo ""
echo "=== DONE — verify in Kitsu UI ==="
echo "  URL: $KITSU_URL"
echo "  Login: admin@admin.com / mysecretpassword"
