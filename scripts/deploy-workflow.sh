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
#
# NOTE R9: ce script DÉPLOIE des workflows existants; il tolère les IF v2 déjà présents
# (prod 2.7.3 en exécute 79, dont 36 actifs, sans crash — R4). R9 reste un garde-fou
# d'AUTORING (ne pas ÉCRIRE de nouveaux IF v2) tant que la revalidation staging n'a pas
# statué (RUNBOOK-N8N-UPGRADE-SIDECAR.md §R9).

set -euo pipefail

# rex-capture (livrable 2, harness autoring) — best-effort, jamais bloquant,
# n'affecte jamais le code de sortie de ce script. Opt-out: REX_CAPTURE=0.
REX_CAPTURE_SCRIPT="$(dirname "$0")/n8n-authoring/rex-capture.sh"
rex_capture_on_fail() {
  local wf_ref="$1" step="$2" err="$3"
  if [[ -x "$REX_CAPTURE_SCRIPT" ]]; then
    "$REX_CAPTURE_SCRIPT" "$wf_ref" "$step" "$err" || true
  fi
}

# ── Parameters ───────────────────────────────────────────────────────────────

WF_FILE="${1:-}"
if [[ -z "$WF_FILE" ]]; then
  echo "Usage: $0 <workflow_json_file>" >&2
  rex_capture_on_fail "<argument manquant>" "deploy-usage" "usage: $0 <workflow_json_file>"
  exit 1
fi

if [[ ! -f "$WF_FILE" ]]; then
  echo "Error: file not found: $WF_FILE" >&2
  rex_capture_on_fail "$WF_FILE" "deploy-file-missing" "file not found: $WF_FILE"
  exit 1
fi

N8N_BASE_URL="${N8N_BASE_URL:-https://mayi.ewutelo.cloud}"
N8N_API_KEY="${N8N_API_KEY:-}"

if [[ -z "$N8N_API_KEY" ]]; then
  echo "Error: N8N_API_KEY not set. Export the variable before calling this script." >&2
  rex_capture_on_fail "$WF_FILE" "deploy-missing-api-key" "N8N_API_KEY not set"
  exit 1
fi

# --id <ID> ou env WF_ID override l'id du fichier (workflow sans id embarqué, ou re-ciblage)
WF_ID_OVERRIDE="${WF_ID:-}"
if [[ "${2:-}" == "--id" && -n "${3:-}" ]]; then WF_ID_OVERRIDE="$3"; fi

# ── Step 1: read workflow ID ──────────────────────────────────────────────────

WF_NAME=$(python3 -c "import json; d=json.load(open('$WF_FILE')); print(d.get('name','?'))")
WF_ID=$(python3 -c "import json; d=json.load(open('$WF_FILE')); print(d.get('id',''))" 2>/dev/null || true)

if [[ -n "$WF_ID_OVERRIDE" ]]; then WF_ID="$WF_ID_OVERRIDE"; fi

if [[ -z "$WF_ID" ]]; then
  echo "Error: 'id' absent du JSON et --id non fourni." >&2
  rex_capture_on_fail "$WF_FILE" "deploy-missing-id" "'id' absent du JSON et --id non fourni"
  exit 1
fi

echo "Workflow: $WF_NAME (id=$WF_ID)"

# ── Step 2: structural validation (delegated to fallback CLI validator) ───────
# Fallback R1 (MCP validate_workflow remains the semantic reference)

echo "→ Structural validation (fallback CLI)..."
# exit≠0 => set -e stoppe le deploy. n8n-validate-fallback.sh appelle DÉJÀ
# rex-capture.sh sur son propre échec (pas de double capture ici).
"$(dirname "$0")/n8n-validate-fallback.sh" "$WF_FILE"

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
  rex_capture_on_fail "$WF_ID" "deploy-preflight-404" "REST API 404 — Caddy ne route pas /api/v1/ vers javisi_n8n:5678"
  exit 1
fi

if [[ "$PREFLIGHT_HTTP" != "200" ]]; then
  echo "Error preflight: HTTP $PREFLIGHT_HTTP — check N8N_API_KEY and ${N8N_BASE_URL}" >&2
  rex_capture_on_fail "$WF_ID" "deploy-preflight" "HTTP $PREFLIGHT_HTTP sur GET ${N8N_BASE_URL}/api/v1/workflows"
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
  PUT_MSG=$(echo "$PUT_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('message', d))" 2>/dev/null || echo "$PUT_BODY")
  echo "$PUT_MSG" >&2
  echo "AVERTISSEMENT (GOTCHAS-N8N-2.30.md): un PUT en échec HTTP n'est pas garanti atomique sur 2.30.7 — relire activeVersionId même sur erreur avant de retenter." >&2
  rex_capture_on_fail "$WF_ID" "deploy-put" "HTTP $PUT_HTTP — $PUT_MSG"
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
