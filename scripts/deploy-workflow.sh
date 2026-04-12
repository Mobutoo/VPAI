#!/usr/bin/env bash
# deploy-workflow.sh — Déploiement workflow n8n via REST API (LOI OP R11)
#
# Méthode primaire : PUT /api/v1/workflows/:id (met à jour entity + history simultanément)
# Prérequis Caddy : /api/v1/* doit être routé vers javisi_n8n:5678
#   Si HTTP 404 : ajouter dans le Caddyfile n8n —
#     handle /api/v1/* {
#         reverse_proxy javisi_n8n:5678
#     }
#
# Usage :
#   N8N_API_KEY=sk-... ./scripts/deploy-workflow.sh scripts/n8n-workflows/<workflow>.json
#   N8N_BASE_URL=https://mayi.ewutelo.cloud N8N_API_KEY=sk-... ./scripts/deploy-workflow.sh <file>
#
# Références : LOI OP R9 (IF v2 check), R10 (workflow_history), R11 (REST API primary)

set -euo pipefail

# ── Paramètres ──────────────────────────────────────────────────────────────

WF_FILE="${1:-}"
if [[ -z "$WF_FILE" ]]; then
  echo "Usage: $0 <workflow_json_file>" >&2
  exit 1
fi

if [[ ! -f "$WF_FILE" ]]; then
  echo "Erreur: fichier introuvable: $WF_FILE" >&2
  exit 1
fi

N8N_BASE_URL="${N8N_BASE_URL:-https://mayi.ewutelo.cloud}"
N8N_API_KEY="${N8N_API_KEY:-}"

if [[ -z "$N8N_API_KEY" ]]; then
  echo "Erreur: N8N_API_KEY non défini. Exporter la variable avant d'appeler ce script." >&2
  exit 1
fi

# ── Étape 1 : lire l'ID du workflow ──────────────────────────────────────────

WF_NAME=$(python3 -c "import json; d=json.load(open('$WF_FILE')); print(d.get('name','?'))")
WF_ID=$(python3 -c "import json,sys; d=json.load(open('$WF_FILE')); v=d.get('id',''); sys.exit(0) if v else sys.exit(1)" 2>/dev/null && \
  python3 -c "import json; print(json.load(open('$WF_FILE'))['id'])" || true)

if [[ -z "$WF_ID" ]]; then
  echo "Erreur: champ 'id' absent dans $WF_FILE. Obligatoire pour PUT." >&2
  exit 1
fi

echo "Workflow : $WF_NAME (id=$WF_ID)"

# ── Étape 2 : validation structurelle Python3 ────────────────────────────────
# Fallback R1 (MCP validate_workflow reste la référence sémantique)

echo "→ Validation structurelle..."

python3 - <<PYEOF
import json, sys

d = json.load(open("$WF_FILE"))
nodes = {n['name'] for n in d.get('nodes', [])}
conns = set(d.get('connections', {}).keys())
missing = conns - nodes

if missing:
    print(f"ERREUR connexions: sources inconnues: {missing}", file=sys.stderr)
    sys.exit(1)

# R9 : IF node v2 check
bad_if = [
    n['name'] for n in d.get('nodes', [])
    if n.get('type') == 'n8n-nodes-base.if' and n.get('typeVersion', 1) >= 2
]
if bad_if:
    print(f"ERREUR R9: IF node v2 détecté (bug n8n 2.7.3) — downgrader typeVersion 2→1 : {bad_if}", file=sys.stderr)
    sys.exit(1)

print(f"  OK — {len(d['nodes'])} nodes, {len(conns)} connexions, 0 IF v2")
PYEOF

# ── Étape 3 : préflight REST API (détecte 404 Caddy) ─────────────────────────

echo "→ Préflight REST API..."

PREFLIGHT_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "${N8N_BASE_URL}/api/v1/workflows")

if [[ "$PREFLIGHT_HTTP" == "404" ]]; then
  cat >&2 <<EOF

ERREUR R11 — REST API 404 : Caddy ne route pas /api/v1/ vers javisi_n8n:5678

Ajouter dans le bloc Caddyfile du domaine mayi.ewutelo.cloud :

    handle /api/v1/* {
        reverse_proxy javisi_n8n:5678
    }

Puis redéployer Caddy :
    make deploy-role ROLE=caddy ENV=prod

Fallback disponible : procédure CLI (LOI OP R10) :
    n8n import:workflow --input=/tmp/<wf>.json
    n8n publish:workflow --id=$WF_ID
    docker restart javisi_n8n && sleep 20 && docker restart javisi_n8n
EOF
  exit 1
fi

if [[ "$PREFLIGHT_HTTP" != "200" ]]; then
  echo "ERREUR préflight: HTTP $PREFLIGHT_HTTP — vérifier N8N_API_KEY et ${N8N_BASE_URL}" >&2
  exit 1
fi

echo "  OK — REST API accessible (HTTP 200)"

# ── Étape 4 : PUT workflow ────────────────────────────────────────────────────

echo "→ PUT /api/v1/workflows/$WF_ID..."

PUT_RESPONSE=$(curl -sS -w "\n%{http_code}" \
  -X PUT "${N8N_BASE_URL}/api/v1/workflows/$WF_ID" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d @"$WF_FILE")

PUT_HTTP=$(echo "$PUT_RESPONSE" | tail -1)
PUT_BODY=$(echo "$PUT_RESPONSE" | head -n -1)

if [[ "$PUT_HTTP" != "200" ]]; then
  echo "ERREUR PUT: HTTP $PUT_HTTP" >&2
  echo "$PUT_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('message', d))" 2>/dev/null || echo "$PUT_BODY" >&2
  exit 1
fi

echo "  OK — workflow mis à jour (HTTP 200)"

# ── Étape 5 : activer le workflow ─────────────────────────────────────────────

echo "→ POST /api/v1/workflows/$WF_ID/activate..."

ACTIVATE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${N8N_BASE_URL}/api/v1/workflows/$WF_ID/activate" \
  -H "X-N8N-API-KEY: $N8N_API_KEY")

if [[ "$ACTIVATE_HTTP" != "200" ]]; then
  echo "Avertissement: activation HTTP $ACTIVATE_HTTP (workflow peut déjà être actif)" >&2
else
  echo "  OK — workflow activé"
fi

# ── Étape 6 : vérification finale ────────────────────────────────────────────

echo "→ Vérification statut..."

STATUS=$(curl -sS \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "${N8N_BASE_URL}/api/v1/workflows/$WF_ID" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('active' if d.get('active') else 'inactive')")

echo ""
echo "Déploiement terminé :"
echo "  Nom   : $WF_NAME"
echo "  ID    : $WF_ID"
echo "  Statut: $STATUS"
echo "  URL   : ${N8N_BASE_URL}/workflow/$WF_ID"
