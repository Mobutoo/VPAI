#!/bin/bash
set -euo pipefail
JOB=a7c414c0
REMOTION=http://localhost:3200

echo "=== Test Remotion render with existing videos ==="

# Check Remotion health
HEALTH=$(curl -sf "$REMOTION/health" 2>&1) || { echo "Remotion DOWN"; exit 1; }
echo "Health: $HEALTH"

# Check video files exist
docker exec workstation_remotion ls -la /app/creative-assets/$JOB/ 2>/dev/null || { echo "No videos"; exit 1; }

# Submit render (720p to reduce memory)
echo "=== Submit render ==="
RENDER=$(curl -sf -X POST "$REMOTION/renders" \
  -H "Content-Type: application/json" \
  -d "{
    \"compositionId\": \"Montage\",
    \"inputProps\": {
      \"scenes\": [
        {\"type\":\"video\",\"src\":\"http://workstation_remotion:3200/creative-assets/$JOB/${JOB}_s0.mp4\",\"durationInFrames\":120,\"sceneIndex\":0},
        {\"type\":\"video\",\"src\":\"http://workstation_remotion:3200/creative-assets/$JOB/${JOB}_s1.mp4\",\"durationInFrames\":120,\"sceneIndex\":1}
      ],
      \"fps\": 24,
      \"width\": 1280,
      \"height\": 720
    }
  }")
echo "$RENDER"
JOBID=$(echo "$RENDER" | python3 -c "import sys,json; print(json.load(sys.stdin)['jobId'])")
echo "JobID: $JOBID"

# Poll
echo "=== Polling ==="
for i in $(seq 1 120); do
  sleep 5
  STATUS_JSON=$(curl -sf "$REMOTION/renders/$JOBID" 2>/dev/null) || { echo "  poll $i: connection failed"; continue; }
  S=$(echo "$STATUS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"status\",\"?\")} {d.get(\"progress\",0):.0%}')")
  if [ $((i % 6)) -eq 0 ]; then echo "  poll $i: $S"; fi

  DONE=$(echo "$STATUS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('status') in ('completed','failed') else 'no')")
  if [ "$DONE" = "yes" ]; then
    echo "  FINAL poll $i: $S"
    break
  fi
done

# Result
echo "=== Result ==="
FINAL=$(curl -sf "$REMOTION/renders/$JOBID")
echo "$FINAL" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('status:', d.get('status'))
url = d.get('videoUrl','none')
print('videoUrl:', url[:120] if url else 'none')
print('error:', d.get('error','none'))
if d.get('status') == 'completed' and url:
    print('SUCCESS: Remotion render OK')
elif d.get('status') == 'failed':
    print('FAILED:', d.get('error','unknown'))
"
