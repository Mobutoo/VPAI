#!/bin/sh
# n8n-enterprise-init.sh — Sidecar init: produit un arbre n8n patché dans un volume overlay.
# Exécuté en root, restart:no, AVANT le service n8n (depends_on service_completed_successfully).
# Idempotent: skip si le marqueur == (version:hash-du-patch). FAIL LOUD si le patch échoue.
# Voir docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md pour le mécanisme complet.
#
# SÉCURITÉ course ancien-conteneur (finding HIGH #3, revue adversariale 2026-07-18) : le host
# path derrière /patched (= n8n_patched_dir, group_vars/all/main.yml) est scopé PAR VERSION
# (".../n8n-patched/<n8n_upstream_version>"), jamais un chemin fixe réutilisé d'un bump à
# l'autre. Le `rm -rf` ci-dessous ne peut donc jamais viser l'arbre qu'un ancien conteneur n8n
# (autre version) a encore monté pendant sa propre recréation par docker compose.
set -eu

SRC="/usr/local/lib/node_modules/n8n"        # arbre pristine de l'image officielle
DST="/patched"                                # bind persistant monté ici (= n8n_patched_dir, scopé par version)
PATCH="/enterprise/patch-enterprise.sh"       # monté RO
MARKER="$DST/.enterprise-patched"

VER="${N8N_TARGET_VERSION:-$(n8n --version 2>/dev/null || echo unknown)}"
PHASH="$(sha256sum "$PATCH" | cut -d' ' -f1)"
WANT="${VER}:${PHASH}"

if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$WANT" ]; then
  echo "[n8n-init] déjà patché ($WANT) — skip"
  exit 0
fi

echo "[n8n-init] (re)construction de l'arbre patché pour $WANT"
rm -rf "$DST"/..?* "$DST"/.[!.]* "$DST"/* 2>/dev/null || true
cp -a "$SRC"/. "$DST"/
N8N_ROOT="$DST" sh "$PATCH"        # exit≠0 ici (set -e) => init échoue => n8n ne démarre pas (FAIL LOUD)

# garde-fou: refuser un arbre où les cibles critiques ne portent pas la valeur licensed
if ! grep -rq "feat:showNonProdBanner" "$DST"/node_modules/.pnpm/*/node_modules/@n8n/backend-common/dist/license-state.js 2>/dev/null; then
  echo "[n8n-init] ✗ FATAL: license-state.js patché introuvable dans la copie" >&2
  exit 1
fi

printf '%s' "$WANT" > "$MARKER"
echo "[n8n-init] terminé — marqueur=$WANT"
