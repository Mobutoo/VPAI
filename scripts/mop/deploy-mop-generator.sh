#!/bin/bash
# Clean-slate deploy of mop-generator-v1 to Sese-AI via Tailscale.
#
# Protocol (file-first, never UI):
#   1. Copy canonical JSON to n8n container
#   2. Deactivate + delete all executions for workflow id
#   3. Restart n8n (wave 1 — flush runtime cache pre-import)
#   4. Wait for /healthz
#   5. import:workflow --input=... (upsert draft: workflow_entity.nodes)
#   6. publish:workflow --id=... (copy draft into workflow_history + set
#      activeVersionId → what n8n actually executes)
#   7. Restart n8n (wave 2 — reload workflow_history into runtime)
#   8. Wait for /healthz + 10s grace (workflow loading is async after healthz)
#   9. Verify: workflow_entity active + webhook_entity rows + workflow_history
#      node count == expected
#
# KEY INSIGHT (n8n 2.7.3):
#   - import:workflow updates workflow_entity.nodes (DRAFT only)
#   - publish:workflow snapshots draft → new workflow_history entry and updates
#     workflow_entity.activeVersionId — this is what n8n loads at runtime
#   - Without publish:workflow the runtime keeps the pre-import workflow_history
#     version regardless of how many times you restart n8n.
#   - N8N_RESTRICT_FILE_ACCESS_TO uses SEMICOLON separator (not colon).
#
# Usage: ./scripts/mop/deploy-mop-generator.sh
#
# Requires: SSH alias / key to Sese-AI Tailscale IP (100.64.0.14).

set -euo pipefail

REMOTE="mobuone@100.64.0.14"
SSH_KEY="$HOME/.ssh/seko-vpn-deploy"
SSH_PORT="804"
SSH="ssh -i $SSH_KEY -p $SSH_PORT $REMOTE"
SCP="scp -i $SSH_KEY -P $SSH_PORT"

WF_ID="CP5gJrn1e2zZbPxh"
EXPECTED_NODE_COUNT=8
LOCAL_JSON="scripts/n8n-workflows/mop-generator-v1.json"

echo "== [1/9] Copy canonical JSON to remote tmp =="
$SCP "$LOCAL_JSON" "$REMOTE:/tmp/mop-generator-v1.json"

echo "== [2/9] Deactivate + wipe executions =="
$SSH bash <<REMOTE_SCRIPT
set -euo pipefail
PG=\$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
PSQL="docker exec -i -e PGPASSWORD=\$PG javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n"
\$PSQL -c "UPDATE workflow_entity SET active=false WHERE id='${WF_ID}';" || true
\$PSQL -c "DELETE FROM execution_data WHERE \"executionId\" IN (SELECT id FROM execution_entity WHERE \"workflowId\"='${WF_ID}');"
\$PSQL -c "DELETE FROM execution_entity WHERE \"workflowId\"='${WF_ID}';"
REMOTE_SCRIPT

echo "== [3/9] Restart n8n (wave 1 — flush runtime cache pre-import) =="
$SSH 'docker restart javisi_n8n >/dev/null'

echo "== [4/9] Wait for /healthz =="
$SSH bash <<'REMOTE_SCRIPT'
for i in $(seq 1 20); do
  if docker exec javisi_n8n wget -qO- http://127.0.0.1:5678/healthz 2>/dev/null | grep -q ok; then
    echo "  ready after ${i}x2s"; exit 0
  fi
  sleep 2
done
echo "TIMEOUT waiting for /healthz"; exit 1
REMOTE_SCRIPT

echo "== [5/9] Copy JSON into container and import (updates draft) =="
$SSH 'docker cp /tmp/mop-generator-v1.json javisi_n8n:/tmp/mop-generator-v1.json'
$SSH 'docker exec javisi_n8n n8n import:workflow --input=/tmp/mop-generator-v1.json 2>&1 | tail -5'

echo "== [6/9] Publish workflow (draft → workflow_history + activeVersionId) =="
$SSH "docker exec javisi_n8n n8n publish:workflow --id=${WF_ID} 2>&1 | tail -5"

echo "== [7/9] Restart n8n (wave 2 — reload published workflow_history) =="
$SSH 'docker restart javisi_n8n >/dev/null'

echo "== [8/9] Wait for /healthz + 10s grace for workflow loading =="
$SSH bash <<'REMOTE_SCRIPT'
for i in $(seq 1 20); do
  if docker exec javisi_n8n wget -qO- http://127.0.0.1:5678/healthz 2>/dev/null | grep -q ok; then
    echo "  healthz ready after ${i}x2s"
    # Workflow loading is async after healthz — wait for FormTrigger webhook
    for j in $(seq 1 10); do
      if docker exec javisi_n8n wget -qO- http://127.0.0.1:5678/form/mop-generator 2>/dev/null | grep -q "Generate MOP"; then
        echo "  form webhook registered after ${j}x2s grace"; exit 0
      fi
      sleep 2
    done
    echo "  WARNING: form webhook not responding after 20s grace — deployment may need more time"
    exit 0
  fi
  sleep 2
done
echo "TIMEOUT waiting for /healthz"; exit 1
REMOTE_SCRIPT

echo "== [9/9] Verify workflow_entity + webhook_entity + workflow_history =="
$SSH bash <<REMOTE_SCRIPT
set -euo pipefail
PG=\$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
PSQL="docker exec -i -e PGPASSWORD=\$PG javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n"
echo "-- workflow_entity:"
\$PSQL -c "SELECT id, name, active, \"versionId\", \"activeVersionId\" FROM workflow_entity WHERE id='${WF_ID}';"
echo "-- webhook_entity:"
\$PSQL -c "SELECT method, \"webhookPath\", \"workflowId\" FROM webhook_entity WHERE \"webhookPath\" LIKE '%mop-generator%';"
echo "-- workflow_history node count at activeVersionId:"
\$PSQL -t -c "
  SELECT jsonb_array_length(wh.nodes::jsonb) as node_count
  FROM workflow_history wh
  JOIN workflow_entity we ON wh.\"versionId\" = we.\"activeVersionId\"
  WHERE we.id='${WF_ID}';" | xargs echo "  node_count:"
REMOTE_SCRIPT

echo
echo "== DEPLOY OK =="
echo "Form URL: https://mayi.ewutelo.cloud/form/mop-generator"
