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

# Balise d'étape : crée une collection 'stage_<x>' (1-dim, jetable) -> témoin de
# progression LISIBLE DEPUIS WAZA (le pod n'a pas de logs via API). Le hang du run
# précédent (points=0 1h40, pas d'EXITED) était indiagnosticable faute de ces balises.
# Teardown : supprimer les collections stage_* (cf handoff). best-effort, jamais bloquant.
beacon() {
  curl -sS -X PUT "$QBASE/collections/stage_$1" "${QHDR[@]}" \
    -H 'Content-Type: application/json' -d '{"vectors":{"size":1,"distance":"Cosine"}}' \
    >/dev/null 2>&1 || true
  say "beacon stage_$1"
}

# report_diag <suffix> <texte> : écrit le texte (tail) en payload d'un point Qdrant
# -> trace d'erreur LISIBLE DEPUIS WAZA (pas de logs pod via API). Termine le devinage.
report_diag() {
  local msg; msg=$(printf '%s' "$2" | tail -c 1500 | jq -Rs . 2>/dev/null || echo '"(jq KO)"')
  curl -sS -X PUT "$QBASE/collections/diag_$1" "${QHDR[@]}" -H 'Content-Type: application/json' \
    -d '{"vectors":{"size":1,"distance":"Cosine"}}' >/dev/null 2>&1 || true
  curl -sS -X PUT "$QBASE/collections/diag_$1/points" "${QHDR[@]}" -H 'Content-Type: application/json' \
    -d "{\"points\":[{\"id\":1,\"vector\":[0.0],\"payload\":{\"msg\":$msg}}]}" >/dev/null 2>&1 || true
  say "diag_$1 écrit (lisible depuis Waza)"
}

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
on_exit() {
  local rc=$?
  # DEBUG : garder le conteneur vivant après sortie pour lire les logs console
  # (RunPod n'expose pas les logs via API ; le conteneur qui exit fait disparaître
  # la trace). Le watchdog dur coupe quand même à WATCHDOG_MAX.
  if [ "${DEBUG_KEEPALIVE:-0}" = "1" ]; then
    say "DEBUG_KEEPALIVE=1 (rc=$rc) — conteneur maintenu 1500s pour lecture logs console. Watchdog stoppe à ${WATCHDOG_MAX}s."
    sleep 1500
  fi
  do_stop "trap exit rc=$rc"
  # RunPod ré-exécute dockerStartCmd si le conteneur SORT (restart-loop observé
  # 2026-06-06 : "already exists" + ré-joins Tailscale en boucle). Après avoir
  # demandé le stop API, on ATTEND le kill externe au lieu de sortir tout de suite
  # (sinon RunPod relance avant que le stop propage). Le watchdog dur reste le filet.
  say "attente du kill externe (anti restart-loop)…"
  sleep 180
}
trap on_exit EXIT INT TERM
self_stop() { do_stop "$1"; exit "${2:-0}"; }
fail() { say "GATE FAIL: $*"; exit 1; }   # le trap EXIT self-stoppe

# Watchdog DUR (filet ultime) : si le bootstrap HANG (ex. tailscale up contre un
# login-server injoignable — incident 2026-06-06), le trap EXIT ne se déclenche pas
# car le script ne sort jamais. Ce watchdog appelle l'API stop après WATCHDOG_MAX,
# quoi qu'il arrive. Process indépendant (pas de partage du flag STOPPED -> stop API
# idempotent côté RunPod).
WATCHDOG_MAX="${WATCHDOG_MAX:-2700}"   # 45 min
if [ -n "${RUNPOD_API_KEY:-}" ] && [ -n "${RUNPOD_POD_ID:-}" ]; then
  ( sleep "$WATCHDOG_MAX"
    curl -sS -X POST "https://rest.runpod.io/v1/pods/${RUNPOD_POD_ID}/stop" \
      -H "Authorization: Bearer ${RUNPOD_API_KEY}" >/dev/null 2>&1 || true
  ) & disown
  say "watchdog armé : self-stop dur dans ${WATCHDOG_MAX}s"
fi

# ---------------------------------------------------------------------------
say "=== G1 deps + Tailscale ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || fail "apt update"
apt-get install -y -qq git curl ca-certificates jq python3-venv iproute2 socat dnsutils >/dev/null || fail "apt install"
curl -fsSL https://tailscale.com/install.sh | sh >/dev/null 2>&1 || fail "tailscale install"

USERSPACE=0
if [ -e /dev/net/tun ]; then
  say "TUN dispo -> mode kernel"
  tailscaled --state=/var/lib/tailscale/tailscaled.state >/var/log/tailscaled.log 2>&1 &
else
  USERSPACE=1
  say "pas de TUN -> userspace + http proxy :1055"
  tailscaled --tun=userspace-networking --outbound-http-proxy-listen=localhost:1055 \
    --state=mem: >/var/log/tailscaled.log 2>&1 &
  # PAS d'export HTTPS_PROXY global : le préambule a prouvé l'egress public DIRECT
  # (apt+git clone sans proxy). github/HF/rest.runpod.io sortent en direct ; seul
  # Qdrant passe par le mesh, via le pont socat ci-dessous (socat dialogue avec le
  # proxy :1055 explicitement, indépendant de l'env). => self-stop direct sans watchdog.
fi
sleep 4
say "tailscaled log:"; tail -8 /var/log/tailscaled.log 2>/dev/null || true
# timeout DUR + capture du motif réel (clé expirée / réseau / daemon). Ne PAS masquer.
# --accept-dns=true OBLIGATOIRE : le pod doit recevoir le split-DNS Headscale
# (qd.ewutelo.cloud -> 100.64.0.14 tailnet). Sinon il résout l'IP PUBLIQUE OVH et
# Caddy renvoie 403 (client_ip hors VPN). Le proxy userspace résout via ce DNS.
ts_out="$(timeout 120 tailscale up --login-server="$HEADSCALE_LOGIN_SERVER" \
  --authkey="$HEADSCALE_AUTHKEY" --hostname=memory-bulk-pod --accept-dns=true 2>&1)"
ts_rc=$?
if [ $ts_rc -ne 0 ]; then
  say "tailscale up rc=$ts_rc — sortie:"; echo "$ts_out"
  say "tailscaled log (tail):"; tail -20 /var/log/tailscaled.log 2>/dev/null || true
  fail "tailscale up (rc=$ts_rc — voir motif ci-dessus : authkey expirée/invalide ? réseau ?)"
fi
say "tailscale OK : $(tailscale ip -4 2>/dev/null | head -1)"

# --- Routage Qdrant via le mesh ---
# qd.ewutelo.cloud N'EST PAS un nom MagicDNS (*.ts.net) : c'est un domaine custom
# avec split-DNS Headscale -> 100.64.0.14 pour les pairs tailnet. En userspace, le
# proxy HTTP :1055 résout pourtant l'IP PUBLIQUE OVH (split-DNS non propagé au proxy ;
# /etc/hosts ignoré sur le CONNECT) -> Caddy `vpn_only` 403 (incident 2026-06-06).
# Fix déterministe SANS DNS : pont socat épinglé sur l'IP tailnet de Sese.
#   socat 127.0.0.1:443 --(CONNECT 100.64.0.14:443 via proxy :1055)--> Caddy mesh
#   /etc/hosts qd.ewutelo.cloud -> 127.0.0.1 => curl ET httpx (qdrant-client) sortent
#   par socat (mesh). HF/github/runpod sortent en DIRECT (pas de proxy global).
#   NO_PROXY=qd... : ceinture+bretelles si un proxy était hérité d'ailleurs (sinon moot).
if [ "$USERSPACE" = 1 ]; then
  say "userspace -> pont socat qd.ewutelo.cloud:443 -> tailnet $SESE_TAILNET_IP via proxy :1055"
  socat TCP4-LISTEN:443,bind=127.0.0.1,reuseaddr,fork \
    "PROXY:127.0.0.1:${SESE_TAILNET_IP}:443,proxyport=1055" >/var/log/socat.log 2>&1 &
  disown
  sleep 2
  sed -i '/qd\.ewutelo\.cloud/d' /etc/hosts
  echo "127.0.0.1 qd.ewutelo.cloud" >> /etc/hosts
  export NO_PROXY="qd.ewutelo.cloud,127.0.0.1,localhost" no_proxy="qd.ewutelo.cloud,127.0.0.1,localhost"
else
  grep -q "qd.ewutelo.cloud" /etc/hosts || echo "$SESE_TAILNET_IP qd.ewutelo.cloud" >> /etc/hosts
fi

say "=== G2 Qdrant joignable ==="
# Dump diagnostic (les logs pod ne sont lisibles que via console UI -> tout d'un coup).
say "diag: getent qd        = $(getent hosts qd.ewutelo.cloud 2>/dev/null | tr '\n' ' ')"
say "diag: tailscale ping    = $(timeout 15 tailscale ping "$SESE_TAILNET_IP" 2>&1 | tail -1)"
[ "$USERSPACE" = 1 ] && say "diag: socat.log         = $(tail -3 /var/log/socat.log 2>/dev/null | tr '\n' '|')"
diag_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "${QHDR[@]}" "$QBASE/healthz" 2>/dev/null || echo 000)
say "diag: healthz HTTP      = $diag_code"
"${CURL[@]}" "${QHDR[@]}" "$QBASE/healthz" >/dev/null || fail "qdrant healthz injoignable (HTTP $diag_code)"
say "qdrant healthz OK"
beacon g2_qdrant_ok

if [ "${PROBE_ONLY:-0}" = "1" ]; then
  # Témoin observable à distance : écrire la collection prouve Tailscale+Qdrant+write
  # (le pod n'a pas de logs lisibles via API REST). Lisible ensuite depuis Waza.
  curl -sS -X PUT "$QBASE/collections/probe_ok" "${QHDR[@]}" -H 'Content-Type: application/json' \
    -d '{"vectors":{"size":1,"distance":"Cosine"}}' -w '\n[probe] PUT HTTP %{http_code}\n' || say "WARN probe_ok PUT"
  say "PROBE_ONLY=1 -> primitif réseau prouvé (R4) + témoin probe_ok écrit. Stop."
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
clone() {  # name url ; timeout DUR (un clone qui hang bloquait tout G3 sans EXITED)
  local dest="$STAGING/$1"
  [ -d "$dest/.git" ] && { say "  $1 déjà"; return; }
  timeout 300 git clone --depth 1 "$2" "$dest" >/dev/null 2>&1 || fail "clone $1 (timeout/erreur 300s)"
  say "  cloné $1"
}
PAT_PREFIX="https://x-access-token:${GITHUB_PAT}@github.com/${GIT_OWNER}"
[ -d "$STAGING/VPAI/.git" ] || clone VPAI "$PAT_PREFIX/VPAI.git"   # normalement déjà cloné par dockerStartCmd
clone flash-studio "$PAT_PREFIX/flash-studio.git"
clone story-engine "$PAT_PREFIX/story-engine.git"
clone hawkeye      "$PAT_PREFIX/hawkeye.git"
clone fantrad      "$PAT_PREFIX/FanTrad.git"
clone riposte      "$PAT_PREFIX/riposte.git"
# typebot.io = gros monorepo public : suspect n°1 du hang G3 (clone long sans logs).
# Filet = timeout 300s dans clone() ci-dessus (un hang -> fail+self-stop, plus 1h40 muet).
clone typebot-docs "https://github.com/baptisteArno/typebot.io.git"
beacon g3_clone_done

say "=== G4 venv + deps + punkt ==="
python3 -m venv /opt/ingest || fail "venv"
. /opt/ingest/bin/activate
pip install -q -U pip >/dev/null 2>&1 || true
timeout 1800 pip install -q -r "$GPU_DIR/requirements.lock.txt" >/dev/null 2>&1 || fail "pip install lock (timeout/erreur 1800s)"
beacon g4_pip_done
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')" >/dev/null 2>&1 || fail "nltk punkt"
say "venv prêt : $(python --version)"

# CACHE TIKTOKEN OFFLINE (root cause hang G7 2026-06-06) : SentenceSplitter (llama-index)
# télécharge cl100k_base depuis openaipublic.blob.core.windows.net au 1er chunk. Ce
# endpoint Azure HANG depuis le pod (alors que github/nltk/HF passent). Le fichier est
# baké dans le repo (clé sha1 déterministe) -> résolution offline, zéro réseau, parité
# tokenizer garantie. Le tokenizer DOIT rester tiktoken (sinon node_id divergent).
export TIKTOKEN_CACHE_DIR="$GPU_DIR/tiktoken_cache"
say "TIKTOKEN_CACHE_DIR=$TIKTOKEN_CACHE_DIR ($(ls "$TIKTOKEN_CACHE_DIR" 2>/dev/null | wc -l) fichier(s))"
# Warm-up chunker : force le 1er usage SentenceSplitter MAINTENANT (beaconé+borné).
# Si tiktoken tentait encore le réseau, ça échoue ici en 60s — plus de hang muet 15min.
timeout 60 python -c "import sys; sys.path.insert(0,'$CODE_DIR'); from pathlib import Path; from memory_core import build_chunks, CHUNK_SIZE, CHUNK_OVERLAP, MAX_CHUNKS_PER_FILE; build_chunks(Path('CLAUDE.md'), open('$STAGING/VPAI/CLAUDE.md').read(), CHUNK_SIZE, CHUNK_OVERLAP, MAX_CHUNKS_PER_FILE); print('chunker warm OK')" || fail "warm-up chunker (tiktoken offline KO ?)"
beacon g4_venv_done

# Warm-up modèle HF MAINTENANT (download 1.2GB gated, borné+beaconé). Seule inconnue
# restante : le download depuis huggingface.co (hôte ≠ Azure/nltk) hang-t-il sur le pod ?
# Si oui, échec localisé ici (pas en plein G8). Si OK -> G8 = embedding pur, modèle en cache.
say "=== G4b warm-up modèle embeddinggemma-300m ==="
mw_out=$(timeout 1200 python -c "import sys; sys.path.insert(0,'$CODE_DIR'); from memory_core import EmbeddingGemmaEncoder; e=EmbeddingGemmaEncoder('google/embeddinggemma-300m', True); print('model warm OK')" 2>&1)
mw_rc=$?
echo "$mw_out"
if [ $mw_rc -ne 0 ]; then
  report_diag model_warm "rc=$mw_rc
$mw_out"
  fail "warm-up modèle HF rc=$mw_rc (trace -> collection diag_model_warm, lisible depuis Waza)"
fi
beacon g4_model_warm

say "=== G5 memory_v2 existe ==="
"${CURL[@]}" "${QHDR[@]}" "$QBASE/collections/memory_v2" >/dev/null || fail "collection memory_v2 absente"

export QDRANT_URL QDRANT_API_KEY
PI=("$GPU_DIR/pod_ingest.py" --sources "$GPU_DIR/sources.pod.yml")

say "=== G6 preflight ==="
timeout 600 python "${PI[@]}" --preflight || fail "preflight (timeout 600s)"
beacon g6_preflight_done

say "=== G7 self-check node_id (parité) ==="
REF="$GPU_DIR/reference_nodeids.json"
check_one() {  # key file
  local key="$1" file="$2"
  local got exp
  got=$(timeout 120 python "${PI[@]}" --verify-sample "$file" 2>/dev/null \
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
beacon g7_parity_ok

say "=== G8 bulk ingest ==="
# Si au prochain run g8_bulk_start est présent mais memory_v2.points reste 0 longtemps,
# le hang est l'embedding (download/charge modèle HF gated, ou débit CPU) — PAS G3/G4.
beacon g8_bulk_start
python "${PI[@]}" 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
[ "$rc" = "0" ] || { report_diag bulk "bulk rc=$rc — $(tail -c 1200 "$LOG")"; fail "bulk rc=$rc (trace -> diag_bulk)"; }

say "=== G9 sentinelle + report ==="
curl -sS -X PUT "$QBASE/collections/ingest_done" "${QHDR[@]}" -H 'Content-Type: application/json' \
  -d '{"vectors":{"size":1,"distance":"Cosine"}}' -w '\n[sentinel] HTTP %{http_code}\n' || say "WARN sentinelle PUT"
say "INGESTION TERMINÉE OK"

self_stop "done" 0
