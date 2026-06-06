#!/usr/bin/env bash
# provision_pod.sh — pod CPU RunPod on-demand pour l'ingestion bulk mémoire.
#
# Source API (R8, doc officielle 2026-06-06) :
#   POST https://rest.runpod.io/v1/pods   (Authorization: Bearer <key>)
#   requis: imageName, computeType=CPU. clés: name, cloudType, vcpuCount,
#   containerDiskInGb, volumeInGb, ports[], env{}, dataCenterIds[].
#   GET/DELETE https://rest.runpod.io/v1/pods/{id}
#
# Secrets : RUNPOD_API_KEY depuis ~/projects/saas/fantrad/.env (jamais en clair/commit).
# Par défaut : --check (DRY, affiche payload + curl, n'appelle PAS l'API).
#
# Usage :
#   ./provision_pod.sh --check                 # dry-run (défaut) : montre la requête
#   ./provision_pod.sh --create                # crée le pod (gate humain)
#   ./provision_pod.sh --status <podId>
#   ./provision_pod.sh --terminate <podId>     # + révoquer la clé Headscale ensuite
set -euo pipefail

API="https://rest.runpod.io/v1/pods"
ENV_RUNPOD="${ENV_RUNPOD:-/home/mobuone/projects/saas/fantrad/.env}"

# --- Paramètres pod (overridables par env) ---------------------------------
POD_NAME="${POD_NAME:-memory-bulk-ingest}"
# IMAGE : DOIT fournir Python 3.12.x (parité venv worker). python:3.12-bookworm a
# apt (git/rsync/build-essential installables au runtime). Contrôle via terminal web
# RunPod (ou sshd si installé). ⚠️ Si tu préfères une base RunPod, VÉRIFIE sa version Python.
POD_IMAGE="${POD_IMAGE:-python:3.12-bookworm}"
VCPU="${VCPU:-16}"
CLOUD_TYPE="${CLOUD_TYPE:-SECURE}"          # SECURE (fiable) | COMMUNITY (moins cher)
CONTAINER_DISK_GB="${CONTAINER_DISK_GB:-60}"  # deps (torch CPU ~2G) + repos + corpus
VOLUME_GB="${VOLUME_GB:-0}"                  # éphémère : pas de persistance requise
PORTS_JSON="${PORTS_JSON:-[\"22/tcp\"]}"

load_key() {
  if [ -z "${RUNPOD_API_KEY:-}" ]; then
    [ -f "$ENV_RUNPOD" ] || { echo "RUNPOD_API_KEY absent et $ENV_RUNPOD introuvable" >&2; exit 1; }
    set -a; . "$ENV_RUNPOD"; set +a
  fi
  [ -n "${RUNPOD_API_KEY:-}" ] || { echo "RUNPOD_API_KEY vide" >&2; exit 1; }
}

build_payload() {
  jq -n \
    --arg name "$POD_NAME" --arg image "$POD_IMAGE" --arg cloud "$CLOUD_TYPE" \
    --argjson vcpu "$VCPU" --argjson cdisk "$CONTAINER_DISK_GB" --argjson vol "$VOLUME_GB" \
    --argjson ports "$PORTS_JSON" '
    {
      name: $name, imageName: $image, computeType: "CPU", cloudType: $cloud,
      vcpuCount: $vcpu, containerDiskInGb: $cdisk, volumeInGb: $vol, ports: $ports
    }'
}

cmd_check() {
  echo "[check] payload (DRY — aucun appel API) :"
  build_payload
  echo
  echo "[check] commande réelle équivalente :"
  echo "  curl -sS -X POST '$API' -H 'Authorization: Bearer \$RUNPOD_API_KEY' \\"
  echo "    -H 'Content-Type: application/json' -d '<payload ci-dessus>'"
  echo "[check] lancer avec --create pour exécuter (gate humain)."
}

cmd_create() {
  load_key
  local payload; payload="$(build_payload)"
  echo "[create] POST $API …" >&2
  local resp; resp="$(curl -sS -X POST "$API" \
    -H "Authorization: Bearer $RUNPOD_API_KEY" \
    -H "Content-Type: application/json" -d "$payload")"
  echo "$resp" | jq . 2>/dev/null || echo "$resp"
  local id; id="$(echo "$resp" | jq -r '.id // empty' 2>/dev/null)"
  [ -n "$id" ] && echo "[create] POD_ID=$id" >&2 || echo "[create] ⚠️ pas d'id — voir réponse" >&2
}

cmd_status()    { load_key; curl -sS "$API/$1" -H "Authorization: Bearer $RUNPOD_API_KEY" | jq .; }
cmd_terminate() { load_key; curl -sS -X DELETE "$API/$1" -H "Authorization: Bearer $RUNPOD_API_KEY" -w '\nHTTP %{http_code}\n'; }

case "${1:---check}" in
  --check)     cmd_check ;;
  --create)    cmd_create ;;
  --status)    [ -n "${2:-}" ] || { echo "usage: --status <podId>" >&2; exit 2; }; cmd_status "$2" ;;
  --terminate) [ -n "${2:-}" ] || { echo "usage: --terminate <podId>" >&2; exit 2; }; cmd_terminate "$2" ;;
  *) echo "usage: $0 [--check|--create|--status <id>|--terminate <id>]" >&2; exit 2 ;;
esac
