#!/usr/bin/env bash
# rex-capture.sh — capture automatique d'échec validate/deploy/verify en entrée REX.
#
# Livrable 2, SPEC .planning/quick/260718-a-harness-autoring-n8n/SPEC.md.
# Appelé par scripts/deploy-workflow.sh et scripts/n8n-validate-fallback.sh sur
# tout échec (validate/deploy/verify). Append une entrée datée dans
# docs/rex/REX-N8N-AUTORING.md : workflow, étape, erreur brute, correction
# éventuelle.
#
# Contrat (best-effort, jamais bloquant) :
#   - N'affecte JAMAIS le code de sortie de l'appelant : l'appelant a déjà
#     décidé de sortir en échec avant de nous appeler ; nous sortons toujours 0
#     nous-mêmes, et l'appelant nous invoque avec `|| true` en défense
#     supplémentaire.
#   - Opt-out : REX_CAPTURE=0 désactive toute écriture (no-op silencieux, exit 0).
#   - Une erreur d'écriture du REX lui-même (disque plein, permissions) est
#     avalée, jamais remontée.
#
# Usage:
#   rex-capture.sh <workflow_ref> <step> <raw_error> [correction]
#
#   workflow_ref : chemin du fichier workflow ou nom/ID (ce qui est disponible
#                  côté appelant au moment de l'échec)
#   step         : étape en échec — "validate", "deploy-preflight",
#                  "deploy-put", "deploy-activate", "verify", etc.
#   raw_error    : message d'erreur brut tel que produit par l'étape en échec
#   correction   : optionnel — correction déjà connue/appliquée pour ce cas
#
# Réf : docs/runbooks/RUNBOOK-N8N-AUTORING.md, docs/runbooks/GOTCHAS-N8N-2.30.md

set -euo pipefail

# Opt-out — vérifié en tout premier, avant toute autre logique.
if [ "${REX_CAPTURE:-1}" = "0" ]; then
  exit 0
fi

WORKFLOW_REF="${1:-<workflow inconnu>}"
STEP="${2:-<étape inconnue>}"
RAW_ERROR="${3:-<message erreur absent>}"
CORRECTION="${4:-}"

# Best-effort total : toute erreur dans ce bloc ne doit jamais faire sortir le
# script en non-zéro (ce qui casserait l'appelant si `|| true` était omis par
# erreur côté appelant).
{
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  REX_FILE="$REPO_ROOT/docs/rex/REX-N8N-AUTORING.md"
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  mkdir -p "$(dirname "$REX_FILE")"

  if [ ! -f "$REX_FILE" ]; then
    cat > "$REX_FILE" <<'HEADER'
# REX — n8n Autoring (capture automatique)

Entrées ajoutées automatiquement par `scripts/n8n-authoring/rex-capture.sh` sur
tout échec `validate`/`deploy`/`verify` détecté par `scripts/n8n-validate-fallback.sh`
ou `scripts/deploy-workflow.sh`. Format : horodatage UTC, workflow, étape, erreur
brute, correction si connue. Opt-out : `REX_CAPTURE=0`. Ne modifie jamais le code
de sortie du script appelant (best-effort).

Doctrine d'usage : `docs/runbooks/RUNBOOK-N8N-AUTORING.md`.
Gotchas curés (build-time) : `docs/runbooks/GOTCHAS-N8N-2.30.md`.

---
HEADER
  fi

  {
    echo ""
    echo "## ${TS} — ${WORKFLOW_REF} — ${STEP}"
    echo ""
    echo "**Erreur brute :**"
    echo '```'
    printf '%s\n' "$RAW_ERROR"
    echo '```'
    if [ -n "$CORRECTION" ]; then
      echo ""
      echo "**Correction :** ${CORRECTION}"
    fi
    echo ""
  } >> "$REX_FILE"
} 2>/dev/null || true

exit 0
