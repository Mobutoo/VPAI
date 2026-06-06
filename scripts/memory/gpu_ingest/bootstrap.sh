#!/usr/bin/env bash
# bootstrap.sh — bootstrap NON-SUPERVISÉ du pod CPU d'ingestion bulk mémoire.
#
# Exécuté au boot via dockerStartCmd (cf provision_pod.sh). Le pod est jetable :
# tout échec OU la fin de run => self-STOP RunPod (coupe la facturation compute).
#
# Stage-gates DURS (chaque gate échoue -> report + self-stop, jamais de bulk douteux) :
#   G1 deps + Tailscale (TUN sinon userspace+proxy) + /etc/hosts qd->Sese
#   G2 Qdrant joignable (curl healthz via mesh)         [PROBE_ONLY s'arrête ici]
#   G0 sentinelle 'ingest_done' déjà présente ? -> rien à faire, self-stop
#   G3 clone des 7 sources git (PAT read-only) -> /staging/<name>
#   G4 venv 3.12 + requirements.lock + punkt nltk
#   G5 collection memory_v2 existe
#   G6 preflight (counts fichiers sains)
#   G7 self-check node_id (1 fichier/wing) vs reference_nodeids.json -> ABORT si !=
#   G8 bulk ingest
#   G9 sentinelle 'ingest_done' (PUT collection) + report
#   G10 self-stop
#
# Secrets attendus en env (injectés par provision_pod.sh) :
#   GITHUB_PAT HEADSCALE_AUTHKEY HEADSCALE_LOGIN_SERVER QDRANT_URL QDRANT_API_KEY
#   RUNPOD_API_KEY RUNPOD_POD_ID  [SESE_TAILNET_IP=100.64.0.14] [PROBE_ONLY=0] [GIT_OWNER=Mobutoo]
set -uo pipefail

LOG=/var/log/bootstrap.log
exec > >(tee -a "$LOG") 2>&1
say() { echo "[bootstrap $(date -u +%H:%M:%S)] $*"; }

SESE_TAILNET_IP="${SESE_TAILNET_IP:-100.64.0.14}"
GIT_OWNER="${GIT_OWNER:-Mobutoo}"
STAGING="${STAGING:-/staging}"
CODE_DIR="$STAGING/VPAI/scripts/memory"
GPU_DIR="$CODE_DIR/gpu_ingest"
QBASE="${QDRANT_URL%/}"                  # ex https://qd.ewutelo.cloud:443
QHDR=(-H "api-key: ${QDRANT_API_KEY:-}")
CURL=(curl -fsS --max-time 30)

# Filet anti-orphelin (REX FanTrad PROCEDURES.md P1 : trap EXIT => 0 pod orphelin).
# do_stop est idempotent ; le trap EXIT le déclenche sur TOUTE sortie (gate fail,
# erreur non gérée, SIGTERM), pas seulement les chemins explicites.
STOPPED=0
do_stop() {
  [ "$STOPPED" = 1 ] && return 0; STOPPED=1
  say "SELF-STOP ($1)"
  if [ -n "${RUNPOD_API_KEY:-}" ] && [ -n "${RUNPOD_POD_ID:-}" ]; then
    curl -sS -X POST "https://rest.runpod.io/v1/pods/${RUNPOD_POD_ID}/stop" \
      -H "Authorization: Bearer ${RUNPOD_API_KEY}" -w '\n[stop] HTTP %{http_code}\n' || true
  else
    say "WARN: RUNPOD_API_KEY/RUNPOD_POD_ID absent — stop manuel requis"
  fi
}
on_exit() { local rc=$?; do_stop "trap exit rc=$rc"; }
trap on_exit EXIT INT TERM
self_stop() { do_stop "$1"; exit "${2:-0}"; }
fail() { say "GATE FAIL: $*"; exit 1; }   # le trap EXIT self-stoppe

# ---------------------------------------------------------------------------
say "=== G1 deps + Tailscale ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || fail "apt update"
apt-get install -y -qq git curl ca-certificates jq python3-venv iproute2 >/dev/null || fail "apt install"
curl -fsSL https://tailscale.com/install.sh | sh >/dev/null 2>&1 || fail "tailscale install"

if [ -e /dev/net/tun ]; then
  say "TUN dispo -> mode kernel"
  tailscaled --state=/var/lib/tailscale/tailscaled.state >/var/log/tailscaled.log 2>&1 &
else
  say "pas de TUN -> userspace + http proxy :1055"
  tailscaled --tun=userspace-networking --outbound-http-proxy-listen=localhost:1055 \
    --state=mem: >/var/log/tailscaled.log 2>&1 &
  # qdrant-client (httpx) + curl honorent HTTPS_PROXY. Pas de SOCKS (socksio absent du lock).
  export HTTPS_PROXY=http://localhost:1055 HTTP_PROXY=http://localhost:1055
fi
sleep 4
tailscale up --login-server="$HEADSCALE_LOGIN_SERVER" --authkey="$HEADSCALE_AUTHKEY" \
  --hostname=memory-bulk-pod --accept-dns=false >/dev/null 2>&1 || fail "tailscale up"
grep -q "qd.ewutelo.cloud" /etc/hosts || echo "$SESE_TAILNET_IP qd.ewutelo.cloud" >> /etc/hosts
say "tailscale OK : $(tailscale ip -4 2>/dev/null | head -1)"

say "=== G2 Qdrant joignable ==="
"${CURL[@]}" "${QHDR[@]}" "$QBASE/healthz" >/dev/null || fail "qdrant healthz injoignable"
say "qdrant healthz OK"

if [ "${PROBE_ONLY:-0}" = "1" ]; then
  say "PROBE_ONLY=1 -> primitif réseau prouvé (R4). Stop."
  self_stop "probe ok" 0
fi

say "=== G0 sentinelle ==="
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "${QHDR[@]}" "$QBASE/collections/ingest_done" || echo 000)
if [ "$code" = "200" ]; then
  say "sentinelle 'ingest_done' présente -> rien à refaire (anti re-bulk)."
  self_stop "already done" 0
fi
say "pas de sentinelle (code=$code) -> ingestion"

say "=== G3 clone 7 sources git ==="
mkdir -p "$STAGING"
clone() {  # name url
  local dest="$STAGING/$1"
  [ -d "$dest/.git" ] && { say "  $1 déjà"; return; }
  git clone --depth 1 "$2" "$dest" >/dev/null 2>&1 || fail "clone $1"
  say "  cloné $1"
}
PAT_PREFIX="https://x-access-token:${GITHUB_PAT}@github.com/${GIT_OWNER}"
[ -d "$STAGING/VPAI/.git" ] || clone VPAI "$PAT_PREFIX/VPAI.git"   # normalement déjà cloné par dockerStartCmd
clone flash-studio "$PAT_PREFIX/flash-studio.git"
clone story-engine "$PAT_PREFIX/story-engine.git"
clone hawkeye      "$PAT_PREFIX/hawkeye.git"
clone fantrad      "$PAT_PREFIX/FanTrad.git"
clone riposte      "$PAT_PREFIX/riposte.git"
clone typebot-docs "https://github.com/baptisteArno/typebot.io.git"

say "=== G4 venv + deps + punkt ==="
python3 -m venv /opt/ingest || fail "venv"
. /opt/ingest/bin/activate
pip install -q -U pip >/dev/null 2>&1 || true
pip install -q -r "$GPU_DIR/requirements.lock.txt" >/dev/null 2>&1 || fail "pip install lock"
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')" >/dev/null 2>&1 || fail "nltk punkt"
say "venv prêt : $(python --version)"

say "=== G5 memory_v2 existe ==="
"${CURL[@]}" "${QHDR[@]}" "$QBASE/collections/memory_v2" >/dev/null || fail "collection memory_v2 absente"

export QDRANT_URL QDRANT_API_KEY
PI=("$GPU_DIR/pod_ingest.py" --sources "$GPU_DIR/sources.pod.yml")

say "=== G6 preflight ==="
python "${PI[@]}" --preflight || fail "preflight"

say "=== G7 self-check node_id (parité) ==="
REF="$GPU_DIR/reference_nodeids.json"
check_one() {  # key file
  local key="$1" file="$2"
  local got exp
  got=$(python "${PI[@]}" --verify-sample "$file" 2>/dev/null \
    | jq -S '{chunk_count, nodes:[.nodes[]|{node_id,chunk_text_sha256}]}')
  exp=$(jq -S --arg k "$key" '.samples[$k] | {chunk_count, nodes:[.nodes[]|{node_id,chunk_text_sha256}]}' "$REF")
  if [ "$got" != "$exp" ]; then
    say "PARITÉ KO sur $key"; diff <(echo "$exp") <(echo "$got") || true
    return 1
  fi
  say "  parité OK $key"
}
check_one "VPAI/CLAUDE.md"            "$STAGING/VPAI/CLAUDE.md"            || fail "node_id divergent (chunking/pins)"
check_one "story-engine/README.md"    "$STAGING/story-engine/README.md"   || fail "node_id divergent"
check_one "typebot-docs/README.md"    "$STAGING/typebot-docs/README.md"   || fail "node_id divergent"

say "=== G8 bulk ingest ==="
python "${PI[@]}" 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
[ "$rc" = "0" ] || fail "bulk rc=$rc"

say "=== G9 sentinelle + report ==="
curl -sS -X PUT "$QBASE/collections/ingest_done" "${QHDR[@]}" -H 'Content-Type: application/json' \
  -d '{"vectors":{"size":1,"distance":"Cosine"}}' -w '\n[sentinel] HTTP %{http_code}\n' || say "WARN sentinelle PUT"
say "INGESTION TERMINÉE OK"

self_stop "done" 0
