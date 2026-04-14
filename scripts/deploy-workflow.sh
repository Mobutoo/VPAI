#!/usr/bin/env bash
# deploy-workflow.sh — n8n workflow deployment via REST API (LOI OP R11)
#
# Primary method: PUT /api/v1/workflows/:id (updates entity + history simultaneously)
# Caddy prerequisite: /api/v1/* must be routed to javisi_n8n:5678
#   If HTTP 404: add to Caddyfile for the n8n domain —
#     handle /api/v1/* {
#         reverse_proxy javisi_n8n:5678
#     }
#
# Usage:
#   N8N_API_KEY=sk-... ./scripts/deploy-workflow.sh scripts/n8n-workflows/<workflow>.json
#   N8N_BASE_URL=https://mayi.ewutelo.cloud N8N_API_KEY=sk-... ./scripts/deploy-workflow.sh <file>
#
# References: LOI OP R9 (IF v2 check), R10 (workflow_history), R11 (REST API primary)

set -euo pipefail

# ── Parameters ───────────────────────────────────────────────────────────────

WF_FILE="${1:-}"
if [[ -z "$WF_FILE" ]]; then
  echo "Usage: $0 <workflow_json_file>" >&2
  exit 1
fi

if [[ ! -f "$WF_FILE" ]]; then
  echo "Error: file not found: $WF_FILE" >&2
  exit 1
fi

N8N_BASE_URL="${N8N_BASE_URL:-https://mayi.ewutelo.cloud}"
N8N_API_KEY="${N8N_API_KEY:-}"

if [[ -z "$N8N_API_KEY" ]]; then
  echo "Error: N8N_API_KEY not set. Export the variable before calling this script." >&2
  exit 1
fi

# ── Step 1: read workflow ID ──────────────────────────────────────────────────

WF_NAME=$(python3 -c "import json; d=json.load(open('$WF_FILE')); print(d.get('name','?'))")
WF_ID=$(python3 -c "import json,sys; d=json.load(open('$WF_FILE')); v=d.get('id',''); sys.exit(0) if v else sys.exit(1)" 2>/dev/null && \
  python3 -c "import json; print(json.load(open('$WF_FILE'))['id'])" || true)

if [[ -z "$WF_ID" ]]; then
  echo "Error: 'id' field missing in $WF_FILE. Required for PUT." >&2
  exit 1
fi

echo "Workflow: $WF_NAME (id=$WF_ID)"

# ── Step 2: structural validation (Python3) ───────────────────────────────────
# Fallback R1 (MCP validate_workflow remains the semantic reference)

echo "→ Structural validation..."

python3 - <<PYEOF
import json, sys

d = json.load(open("$WF_FILE"))
nodes = {n['name'] for n in d.get('nodes', [])}
conns = set(d.get('connections', {}).keys())
missing = conns - nodes

if missing:
    print(f"ERROR connections: unknown sources: {missing}", file=sys.stderr)
    sys.exit(1)

# R9: IF node v2 check
bad_if = [
    n['name'] for n in d.get('nodes', [])
    if n.get('type') == 'n8n-nodes-base.if' and n.get('typeVersion', 1) >= 2
]
if bad_if:
    print(f"ERROR R9: IF node v2 detected (n8n 2.7.3 bug) — downgrade typeVersion 2→1: {bad_if}", file=sys.stderr)
    sys.exit(1)

print(f"  OK — {len(d['nodes'])} nodes, {len(conns)} connections, 0 IF v2")
PYEOF

# ── Step 3: preflight REST API (detects 404 Caddy) ───────────────────────────

echo "→ Preflight REST API..."

PREFLIGHT_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "${N8N_BASE_URL}/api/v1/workflows")

if [[ "$PREFLIGHT_HTTP" == "404" ]]; then
  cat >&2 <<EOF

ERROR R11 — REST API 404: Caddy is not routing /api/v1/ to javisi_n8n:5678

Add to the Caddyfile block for domain mayi.ewutelo.cloud:

    handle /api/v1/* {
        reverse_proxy javisi_n8n:5678
    }

Then redeploy Caddy:
    make deploy-role ROLE=caddy ENV=prod

Fallback available: CLI procedure (LOI OP R10):
    n8n import:workflow --input=/tmp/<wf>.json
    n8n publish:workflow --id=$WF_ID
    docker restart javisi_n8n && sleep 20 && docker restart javisi_n8n
EOF
  exit 1
fi

if [[ "$PREFLIGHT_HTTP" != "200" ]]; then
  echo "Error preflight: HTTP $PREFLIGHT_HTTP — check N8N_API_KEY and ${N8N_BASE_URL}" >&2
  exit 1
fi

echo "  OK — REST API reachable (HTTP 200)"

# ── Step 4: PUT workflow ──────────────────────────────────────────────────────

echo "→ PUT /api/v1/workflows/$WF_ID..."

# Strip fields rejected by PUT API (id, staticData, meta, pinData)
STRIPPED_PAYLOAD=$(python3 -c "
import json, sys
d = json.load(open('$WF_FILE'))
keep = {k: d[k] for k in ('name', 'nodes', 'connections', 'settings') if k in d}
print(json.dumps(keep))
")

PUT_RESPONSE=$(curl -sS -w "\n%{http_code}" \
  -X PUT "${N8N_BASE_URL}/api/v1/workflows/$WF_ID" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$STRIPPED_PAYLOAD")

PUT_HTTP=$(echo "$PUT_RESPONSE" | tail -1)
PUT_BODY=$(echo "$PUT_RESPONSE" | head -n -1)

if [[ "$PUT_HTTP" != "200" ]]; then
  echo "Error PUT: HTTP $PUT_HTTP" >&2
  echo "$PUT_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('message', d))" 2>/dev/null || echo "$PUT_BODY" >&2
  exit 1
fi

echo "  OK — workflow updated (HTTP 200)"

# ── Step 5: activate workflow ─────────────────────────────────────────────────

echo "→ POST /api/v1/workflows/$WF_ID/activate..."

ACTIVATE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${N8N_BASE_URL}/api/v1/workflows/$WF_ID/activate" \
  -H "X-N8N-API-KEY: $N8N_API_KEY")

if [[ "$ACTIVATE_HTTP" != "200" ]]; then
  echo "Warning: activation HTTP $ACTIVATE_HTTP (workflow may already be active)" >&2
else
  echo "  OK — workflow activated"
fi

# ── Step 6: final verification ────────────────────────────────────────────────

echo "→ Checking status..."

STATUS=$(curl -sS \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "${N8N_BASE_URL}/api/v1/workflows/$WF_ID" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('active' if d.get('active') else 'inactive')")

echo ""
echo "Deploy complete:"
echo "  Name  : $WF_NAME"
echo "  ID    : $WF_ID"
echo "  Status: $STATUS"
echo "  URL   : ${N8N_BASE_URL}/workflow/$WF_ID"
