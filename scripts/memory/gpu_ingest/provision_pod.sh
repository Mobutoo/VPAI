#!/usr/bin/env bash
# provision_pod.sh — pod CPU RunPod on-demand, bootstrap NON-SUPERVISÉ.
#
# Crée un pod qui se bootstrappe seul (dockerStartCmd -> clone VPAI -> bootstrap.sh) :
# Tailscale -> Qdrant -> clone 7 repos (PAT) -> venv -> self-check node_id -> bulk ->
# sentinelle -> self-STOP. Aucune connexion/intervention après --create.
#
# Doc API (R8) : POST/GET/DELETE https://rest.runpod.io/v1/pods[/{id}]
#                POST .../{id}/stop  (coupe compute ; volumeInGb=0 => 0 charge stockage)
#
# Secrets chargés (jamais commit) :
#   pod-ingest.env       : HEADSCALE_AUTHKEY, HEADSCALE_LOGIN_SERVER, GITHUB_PAT
#   memory-worker.env    : QDRANT_URL, QDRANT_API_KEY
#   fantrad/.env         : RUNPOD_API_KEY
#
# Usage :
#   ./provision_pod.sh --check          # DRY : payload (secrets masqués), aucun appel
#   ./provision_pod.sh --check-gpu      # DRY : payload GPU (computeType GPU, EXPECT_CUDA=1)
#   ./provision_pod.sh --probe          # crée un pod PROBE_ONLY=1 (R4 : valide Tailscale+Qdrant puis self-stop)
#   ./provision_pod.sh --create         # crée le pod d'ingestion complet (CPU)
#   ./provision_pod.sh --create-gpu     # bulk one-time sur GPU (fail-fast si GPU non utilisé/non-fp32)
#   ./provision_pod.sh --status <id>
#   ./provision_pod.sh --stop <id>      # arrête (compute off) — préféré au teardown
#   ./provision_pod.sh --terminate <id> # DELETE définitif (+ révoquer la clé Headscale)
set -euo pipefail

API="https://rest.runpod.io/v1/pods"
ENV_POD="${ENV_POD:-/opt/workstation/configs/ai-memory-worker/pod-ingest.env}"
ENV_QDRANT="${ENV_QDRANT:-/opt/workstation/configs/ai-memory-worker/memory-worker.env}"
ENV_RUNPOD="${ENV_RUNPOD:-/home/mobuone/work/saas/fantrad/.env}"

POD_NAME="${POD_NAME:-memory-bulk-ingest}"
POD_IMAGE="${POD_IMAGE:-python:3.12-bookworm}"   # DOIT être Python 3.12.x (parité venv worker)
VCPU="${VCPU:-16}"
CLOUD_TYPE="${CLOUD_TYPE:-SECURE}"
CONTAINER_DISK_GB="${CONTAINER_DISK_GB:-60}"
VOLUME_GB="${VOLUME_GB:-0}"
GIT_OWNER="${GIT_OWNER:-Mobutoo}"
SESE_TAILNET_IP="${SESE_TAILNET_IP:-100.64.0.14}"
# Collection cible propagée au pod (contrat v3) : memory_v2 = bulk legacy unnamed,
# memory_v3 = hybrid named (bootstrap gate G5 + prompt v2 + sparse BM25).
# Ex : MEMORY_COLLECTION=memory_v3 ./provision_pod.sh --create-gpu
MEMORY_COLLECTION="${MEMORY_COLLECTION:-memory_v2}"
# Sources cible (mapping staging root -> wing/name, cf sources.pod.yml), DÉCOUPLÉ de
# MEMORY_COLLECTION — sinon `MEMORY_COLLECTION=trading_v1 ./provision_pod.sh --create`
# ingère silencieusement les 7 repos memory DANS trading_v1 (collection changée, source
# inchangée). Défaut INCHANGÉ = sources.pod.yml. CORPUS_REPO_NAME/URL (optionnels) :
# repo supplémentaire à cloner par bootstrap.sh G3 pour un corpus non-memory.
# Ex : MEMORY_COLLECTION=trading_v1 SOURCES_FILE=sources.trading.yml \
#      CORPUS_REPO_NAME=hawktrade CORPUS_REPO_URL=git@github-seko:Mobutoo/hawktrade.git \
#      ./provision_pod.sh --create
SOURCES_FILE="${SOURCES_FILE:-sources.pod.yml}"
CORPUS_REPO_NAME="${CORPUS_REPO_NAME:-}"
CORPUS_REPO_URL="${CORPUS_REPO_URL:-}"

# --- GPU (one-time bulk) ---------------------------------------------------
# computeType=GPU + fail-fast EXPECT_CUDA=1 (warm-up G4b + bench G7b). Le modèle
# fait 1.2GB -> n'importe quel GPU bon marché suffit. gpuTypeIds = liste de repli
# (RunPod prend le 1er disponible). Si le driver hôte est trop ancien pour le torch
# cu13 du lock -> torch.cuda.is_available()=False -> fail-fast (pod self-stop ~3min).
COMPUTE_TYPE="${COMPUTE_TYPE:-CPU}"
GPU_COUNT="${GPU_COUNT:-1}"
# Ada/récent en tête : driver hôte plus probablement ≥580 (requis par torch cu13 du
# lock). Ampère en repli. Tous secure=true (validés via GraphQL gpuTypes 2026-06-06).
GPU_TYPE_IDS="${GPU_TYPE_IDS:-[\"NVIDIA L4\",\"NVIDIA RTX 2000 Ada Generation\",\"NVIDIA RTX 4000 Ada Generation\",\"NVIDIA RTX A4000\",\"NVIDIA RTX A4500\",\"NVIDIA GeForce RTX 4090\"]}"

load_secrets() {
  for f in "$ENV_POD" "$ENV_QDRANT" "$ENV_RUNPOD"; do
    [ -f "$f" ] || { echo "env introuvable: $f" >&2; exit 1; }
    set -a; . "$f"; set +a
  done
  : "${HEADSCALE_AUTHKEY:?absent (pod-ingest.env)}"
  : "${HEADSCALE_LOGIN_SERVER:?absent (pod-ingest.env)}"
  : "${GITHUB_PAT:?absent (pod-ingest.env — PAT read-only)}"
  : "${QDRANT_URL:?absent (memory-worker.env)}"
  : "${QDRANT_API_KEY:?absent (memory-worker.env)}"
  : "${HF_TOKEN:?absent (memory-worker.env — embeddinggemma-300m est gated)}"
  : "${RUNPOD_API_KEY:?absent (fantrad/.env)}"
}

build_env_json() {  # $1 = PROBE_ONLY value
  jq -n \
    --arg authkey "$HEADSCALE_AUTHKEY" --arg login "$HEADSCALE_LOGIN_SERVER" \
    --arg pat "$GITHUB_PAT" --arg qurl "$QDRANT_URL" --arg qkey "$QDRANT_API_KEY" \
    --arg rpkey "$RUNPOD_API_KEY" --arg sese "$SESE_TAILNET_IP" --arg owner "$GIT_OWNER" \
    --arg hf "$HF_TOKEN" --arg probe "$1" --arg keep "${2:-0}" \
    --arg wd "${WATCHDOG_MAX:-14400}" --arg mcoll "$MEMORY_COLLECTION" \
    --arg srcfile "$SOURCES_FILE" --arg crepo "$CORPUS_REPO_NAME" --arg cremoteurl "$CORPUS_REPO_URL" \
    --arg cuda "$([ "$COMPUTE_TYPE" = GPU ] && echo 1 || echo 0)" '{
      HEADSCALE_AUTHKEY:$authkey, HEADSCALE_LOGIN_SERVER:$login, GITHUB_PAT:$pat,
      QDRANT_URL:$qurl, QDRANT_API_KEY:$qkey, RUNPOD_API_KEY:$rpkey,
      HF_TOKEN:$hf, HUGGINGFACE_HUB_TOKEN:$hf,
      SESE_TAILNET_IP:$sese, GIT_OWNER:$owner, PROBE_ONLY:$probe, DEBUG_KEEPALIVE:$keep,
      WATCHDOG_MAX:$wd, EXPECT_CUDA:$cuda, MEMORY_COLLECTION:$mcoll,
      SOURCES_FILE:$srcfile, CORPUS_REPO_NAME:$crepo, CORPUS_REPO_URL:$cremoteurl
    }'
}

# Préambule : verbeux (set -x -> console RunPod), pas de set -e (sinon exit avant
# tout diagnostic). Sur succès -> exec bootstrap.sh (qui prend le relais + son trap).
# Sur échec préambule -> si DEBUG_KEEPALIVE=1 garder vivant pour lire les logs console,
# sinon self-stop (pas d'orphelin). Retry apt (réseau pod parfois pas prêt au boot).
DOCKER_START_CMD='set -x; export DEBIAN_FRONTEND=noninteractive; { for i in 1 2 3; do apt-get update && break; echo "apt retry $i"; sleep 5; done; apt-get install -y git curl && { if [ -d /staging/VPAI/.git ]; then echo "VPAI déjà cloné (restart) -> skip clone"; ok=1; else ok=0; for j in 1 2 3 4 5; do git clone --depth 1 "https://x-access-token:${GITHUB_PAT}@github.com/${GIT_OWNER}/VPAI.git" /staging/VPAI && { ok=1; break; }; echo "git clone retry $j (rc=$?)"; rm -rf /staging/VPAI; sleep 10; done; fi; [ "$ok" = 1 ]; } && exec bash /staging/VPAI/scripts/memory/gpu_ingest/bootstrap.sh; }; rc=$?; echo "=== PREAMBLE FAILED rc=$rc ==="; if [ "${DEBUG_KEEPALIVE:-0}" = "1" ]; then echo "keepalive 1800s — lis Container Logs"; sleep 1800; fi; [ -n "${RUNPOD_API_KEY:-}" ] && curl -s -X POST "https://rest.runpod.io/v1/pods/${RUNPOD_POD_ID}/stop" -H "Authorization: Bearer ${RUNPOD_API_KEY}" >/dev/null 2>&1'

build_payload() {  # $1 = PROBE_ONLY  $2 = DEBUG_KEEPALIVE
  local base
  base=$(jq -n \
    --arg name "$POD_NAME" --arg image "$POD_IMAGE" --arg cloud "$CLOUD_TYPE" \
    --argjson vcpu "$VCPU" --argjson cdisk "$CONTAINER_DISK_GB" --argjson vol "$VOLUME_GB" \
    --argjson envobj "$(build_env_json "$1" "${2:-0}")" --arg startcmd "$DOCKER_START_CMD" \
    --arg ctype "$COMPUTE_TYPE" '
    {
      name: $name, imageName: $image, computeType: $ctype, cloudType: $cloud,
      vcpuCount: $vcpu, containerDiskInGb: $cdisk, volumeInGb: $vol,
      ports: ["22/tcp"],
      dockerEntrypoint: ["/bin/bash"],
      dockerStartCmd: ["-lc", $startcmd],
      env: $envobj
    }')
  if [ "$COMPUTE_TYPE" = GPU ]; then
    # GPU : ajoute gpuCount + gpuTypeIds (liste de repli). vcpuCount ignoré côté GPU.
    echo "$base" | jq --argjson gc "$GPU_COUNT" --argjson gt "$GPU_TYPE_IDS" \
      '. + {gpuCount:$gc, gpuTypeIds:$gt}'
  else
    echo "$base"
  fi
}

mask() { jq '.env |= with_entries(.value |= (if (.|length)>8 then .[0:6]+"…" else "***" end))'; }

cmd_check() {
  load_secrets
  echo "[check] payload (secrets MASQUÉS, aucun appel API) :"
  build_payload "${1:-0}" | mask
  echo "[check] --probe pour R4 (Tailscale+Qdrant puis self-stop), --create pour le run complet."
}

post_create() {  # $1 = PROBE_ONLY  $2 = DEBUG_KEEPALIVE
  load_secrets
  local payload; payload="$(build_payload "$1" "${2:-0}")"
  echo "[create] POST $API (PROBE_ONLY=$1 DEBUG_KEEPALIVE=${2:-0}) …" >&2
  local resp; resp="$(curl -sS -X POST "$API" \
    -H "Authorization: Bearer $RUNPOD_API_KEY" \
    -H "Content-Type: application/json" -d "$payload")"
  echo "$resp" | jq 'del(.env)' 2>/dev/null || echo "$resp"
  local id; id="$(echo "$resp" | jq -r '.id // empty' 2>/dev/null)"
  [ -n "$id" ] && echo "[create] POD_ID=$id" >&2 || echo "[create] ⚠️ pas d'id — voir réponse" >&2
}

# NB : les réponses RunPod incluent .env EN CLAIR -> toujours del(.env) avant affichage.
cmd_status()    { load_secrets; curl -sS "$API/$1" -H "Authorization: Bearer $RUNPOD_API_KEY" | jq 'del(.env)'; }
cmd_stop()      { load_secrets; curl -sS -X POST "$API/$1/stop" -H "Authorization: Bearer $RUNPOD_API_KEY" | jq 'del(.env) | {id, desiredStatus, lastStatusChange}'; }
cmd_terminate() { load_secrets; curl -sS -X DELETE "$API/$1" -H "Authorization: Bearer $RUNPOD_API_KEY" -w 'HTTP %{http_code}\n'; }

case "${1:---check}" in
  --check)        cmd_check 0 ;;
  --check-gpu)    COMPUTE_TYPE=GPU cmd_check 0 ;;
  --probe)        post_create 1 0 ;;
  --debug-probe)  post_create 1 1 ;;   # PROBE_ONLY + keepalive (logs console lisibles)
  --create)       post_create 0 0 ;;
  --create-gpu)   COMPUTE_TYPE=GPU post_create 0 0 ;;   # bulk one-time GPU (EXPECT_CUDA=1, fail-fast)
  --status)    [ -n "${2:-}" ] || { echo "usage: --status <podId>" >&2; exit 2; }; cmd_status "$2" ;;
  --stop)      [ -n "${2:-}" ] || { echo "usage: --stop <podId>" >&2; exit 2; }; cmd_stop "$2" ;;
  --terminate) [ -n "${2:-}" ] || { echo "usage: --terminate <podId>" >&2; exit 2; }; cmd_terminate "$2" ;;
  *) echo "usage: $0 [--check|--check-gpu|--probe|--debug-probe|--create|--create-gpu|--status <id>|--stop <id>|--terminate <id>]" >&2; exit 2 ;;
esac
