#!/bin/bash
# Clean-slate deploy of mop-generator-v1 to Sese-AI via Tailscale.
#
# Protocol (file-first, never UI):
#   1. Copy canonical JSON to n8n container
#   2. Deactivate + delete all executions for workflow id
#   3. Restart n8n (flush runtime cache, wave 1)
#   4. import:workflow --input=... (upsert by id)
#   5. update:workflow --active=true
#   6. Restart n8n (flush runtime cache, wave 2 — n8n CLI emits
#      "Please restart n8n for changes to take effect" after update)
#   7. Wait for /healthz
#   8. Verify workflow_entity active + webhook_entity rows present
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
WF_NAME="mop-generator-v1"
LOCAL_JSON="scripts/n8n-workflows/mop-generator-v1.json"

echo "== [1/8] Copy canonical JSON to remote tmp =="
$SCP "$LOCAL_JSON" "$REMOTE:/tmp/mop-generator-v1.json"

echo "== [2/8] Deactivate + wipe executions =="
$SSH bash <<REMOTE_SCRIPT
set -euo pipefail
PG=\$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
PSQL="docker exec -i -e PGPASSWORD=\$PG javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n"
\$PSQL -c "UPDATE workflow_entity SET active=false WHERE id='${WF_ID}';" || true
\$PSQL -c "DELETE FROM execution_data WHERE \"executionId\" IN (SELECT id FROM execution_entity WHERE \"workflowId\"='${WF_ID}');"
\$PSQL -c "DELETE FROM execution_entity WHERE \"workflowId\"='${WF_ID}';"
REMOTE_SCRIPT

echo "== [3/8] Restart n8n (wave 1 — flush runtime cache pre-import) =="
$SSH 'docker restart javisi_n8n >/dev/null'
sleep 12

echo "== [4/8] Wait for /healthz =="
$SSH bash <<'REMOTE_SCRIPT'
for i in $(seq 1 20); do
  if docker exec javisi_n8n wget -qO- http://127.0.0.1:5678/healthz 2>/dev/null | grep -q ok; then
    echo "  ready after ${i}s"; exit 0
  fi
  sleep 2
done
echo "TIMEOUT waiting for /healthz"; exit 1
REMOTE_SCRIPT

echo "== [5/8] Copy JSON into container and import =="
$SSH 'docker cp /tmp/mop-generator-v1.json javisi_n8n:/tmp/mop-generator-v1.json'
$SSH 'docker exec javisi_n8n n8n import:workflow --input=/tmp/mop-generator-v1.json 2>&1 | tail -10'

echo "== [6/8] Activate workflow via CLI =="
$SSH "docker exec javisi_n8n n8n update:workflow --id=${WF_ID} --active=true 2>&1 | tail -5"

echo "== [7/8] Restart n8n (wave 2 — CLI warns 'restart required for changes to take effect') =="
$SSH 'docker restart javisi_n8n >/dev/null'
sleep 12
$SSH bash <<'REMOTE_SCRIPT'
for i in $(seq 1 20); do
  if docker exec javisi_n8n wget -qO- http://127.0.0.1:5678/healthz 2>/dev/null | grep -q ok; then
    echo "  ready after ${i}s"; exit 0
  fi
  sleep 2
done
echo "TIMEOUT waiting for /healthz"; exit 1
REMOTE_SCRIPT

echo "== [8/8] Verify workflow_entity + webhook_entity =="
$SSH bash <<REMOTE_SCRIPT
set -euo pipefail
PG=\$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
PSQL="docker exec -i -e PGPASSWORD=\$PG javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n"
echo "-- workflow_entity:"
\$PSQL -c "SELECT id, name, active, \"updatedAt\" FROM workflow_entity WHERE id='${WF_ID}';"
echo "-- webhook_entity (GET+POST for 'mop-generator'):"
\$PSQL -c "SELECT method, \"webhookPath\", \"workflowId\" FROM webhook_entity WHERE \"webhookPath\" LIKE '%mop-generator%';"
REMOTE_SCRIPT

echo
echo "== DEPLOY OK =="
echo "Form URL: https://mayi.ewutelo.cloud/form/mop-generator"
