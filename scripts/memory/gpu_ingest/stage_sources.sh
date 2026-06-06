#!/usr/bin/env bash
# stage_sources.sh — stage les 9 sources sur le pod à /staging/<name> (parité worker).
#
# Repos git : clonés via github-seko (clé deploy montée sur le pod) ou https (typebot).
# Sources LOCAL-ONLY (DOCS, podpilot) : rsync depuis Waza via le mesh Tailscale —
# voir bloc commenté en bas (à lancer DEPUIS Waza, pas ici).
#
# ⚠️ VÉRIFIER les remotes exacts avant run (org/repo). Placeholders Mobutoo/<name>.
# Aucune double-imbrication : `git clone <url> /staging/<name>` met le contenu À LA racine.
set -euo pipefail

STAGING="${STAGING:-/staging}"
mkdir -p "$STAGING"

# name -> remote git (VÉRIFIER). typebot-docs depuis l'upstream officiel.
clone() {
  local name="$1" url="$2" dest="$STAGING/$1"
  if [ -d "$dest/.git" ]; then
    echo "[stage] $name déjà cloné, pull"; git -C "$dest" pull --ff-only
  else
    echo "[stage] clone $name <- $url"; git clone --depth 1 "$url" "$dest"
  fi
}

# Remotes vérifiés 2026-06-06 depuis l'origin des clones Waza (casse exacte).
clone VPAI         "git@github-seko:Mobutoo/VPAI.git"
clone flash-studio "git@github-seko:Mobutoo/flash-studio.git"
clone story-engine "git@github-seko:Mobutoo/story-engine.git"
clone hawkeye      "git@github-seko:Mobutoo/hawkeye.git"
clone fantrad      "git@github-seko:Mobutoo/FanTrad.git"
clone riposte      "git@github-seko:Mobutoo/riposte.git"
clone typebot-docs "https://github.com/baptisteArno/typebot.io.git"

echo "[stage] git sources OK."
echo "[stage] DOCS + podpilot = LOCAL-ONLY : rsync depuis Waza (voir ci-dessous)."

# ---------------------------------------------------------------------------
# DEPUIS WAZA (mesh Tailscale, pod joint via clé Headscale éphémère) :
#   POD_IP=<ip-tailscale-pod>
#   rsync -az --delete /home/mobuone/DOCS/      mobuone@$POD_IP:/staging/DOCS/
#   rsync -az --delete /home/mobuone/projects/saas/podpilot/ mobuone@$POD_IP:/staging/podpilot/
#   # trailing slash des deux côtés = contenu à la racine (pas de sous-dossier en plus)
# ---------------------------------------------------------------------------
