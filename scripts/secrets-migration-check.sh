#!/usr/bin/env bash
# secrets-migration-check.sh — gate de validation de la migration des secrets config.
#
# Remplace le grep §9 v1/v2 (non-fonctionnel : ne matchait ni JSON "K":"v" ni
# valeurs shell quotées → faux-vert sur état 100% en clair, cf revue 2026-07-16).
#
# Principe (allowlist + assertion, pas regex de forme) : pour chaque secret CONNU,
# on vérifie que sa valeur n'est PAS un littéral en clair là où elle ne doit plus
# l'être — soit référence ${VAR} (configs), soit absente (règles allow retirées,
# exports .bashrc/.profile déplacés vers le .env 600).
#
# CONTRÔLE POSITIF (auto-test) : `--self-test` prouve que le détecteur ÉCHOUE sur
# l'état pré-migration (sinon le gate est aveugle, comme le bug bash-lint).
#
# Sortie : liste des VIOLATIONS (fichier:clé), jamais la valeur. exit 1 si ≥1.
set -uo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
MCP="$CLAUDE_HOME/mcp.json"
SETTINGS="$CLAUDE_HOME/settings.json"
SLOCAL="${SETTINGS_LOCAL:-$HOME/work/infra/VPAI/.claude/settings.local.json}"
BASHRC="${BASHRC:-$HOME/.bashrc}"
PROFILE="${PROFILE:-$HOME/.profile}"

# Classe 1-cfg : doivent devenir des refs ${VAR} dans les configs.
CFG_MCP_ENV_KEYS=(QDRANT_API_KEY PLANE_API_KEY STITCH_API_KEY)
CFG_MCP_HEADER_SERVERS=(n8n-docs canva-connect)          # Authorization / x-api-key
CFG_SETTINGS_ENV_KEYS=(TELEGRAM_BOT_TOKEN AF_WEBHOOK_SECRET)  # → à SUPPRIMER du bloc env
# Secrets qui NE doivent plus apparaître en clair NULLE PART (déplacés/ retirés).
SHELL_SECRET_KEYS=(QDRANT_API_KEY TELEGRAM_BOT_TOKEN STITCH_API_KEY NOCODB_TOKEN \
                   MACGYVER_BOT_TOKEN HCLOUD_TOKEN NAMECHEAP_API_KEY)
# Règles allow porteuses de secret qui doivent être retirées.
# 'Telegram-Bot-Api-Secret-Token' = header AF_WEBHOOK (2 règles settings.json,
# discriminant propre — pas de collision SHA git, cf revue n2). 'sk-lm-' = LITELLM.
# Motifs regex (grep -E). postgres = forme AVEC creds user:pw@ (pas une URL nue,
# évite un faux-positif latent si une URL sans creds apparaît un jour, cf revue nit3).
REMOVED_ALLOW_PATTERNS=('postgresql://[^:]*:[^@]*@' 'is_email_verified' 'DJANGO_SUPERUSER' \
                        'sk-lm-' 'Telegram-Bot-Api-Secret-Token')

VIOL=0
viol(){ echo "  VIOLATION: $1"; VIOL=$((VIOL+1)); }

is_varref(){ [[ "$1" =~ ^\$\{[A-Z0-9_]+\}$ || "$1" == *'${'*'}'* ]]; }

check_mcp(){
  [ -f "$MCP" ] || { echo "  (mcp.json absent)"; return; }
  for k in "${CFG_MCP_ENV_KEYS[@]}"; do
    v=$(python3 -c "
import json,sys
d=json.load(open('$MCP'));
for n,c in d.get('mcpServers',{}).items():
    e=(c.get('env') or {})
    if '$k' in e: print(e['$k']); break
" 2>/dev/null)
    [ -z "$v" ] && continue
    is_varref "$v" || viol "mcp.json env.$k = littéral (attendu \${$k})"
  done
  for s in "${CFG_MCP_HEADER_SERVERS[@]}"; do
    bad=$(python3 -c "
import json
d=json.load(open('$MCP'))
c=d.get('mcpServers',{}).get('$s',{})
h=(c.get('headers') or {})
for hk,hv in h.items():
    if isinstance(hv,str) and '\${' not in hv and len(hv)>=16 and any(ch.isdigit() for ch in hv):
        print(hk)
" 2>/dev/null)
    [ -n "$bad" ] && viol "mcp.json headers[$s].$bad = littéral (attendu \${VAR})"
  done
}

check_settings_env(){
  [ -f "$SETTINGS" ] || return
  for k in "${CFG_SETTINGS_ENV_KEYS[@]}"; do
    present=$(python3 -c "import json;print('1' if '$k' in (json.load(open('$SETTINGS')).get('env') or {}) else '0')" 2>/dev/null)
    [ "$present" = "1" ] && viol "settings.json env.$k présent (doit être SUPPRIMÉ — bloc env=littéral only)"
  done
}

check_shell(){
  for f in "$BASHRC" "$PROFILE"; do
    [ -f "$f" ] || continue
    for k in "${SHELL_SECRET_KEYS[@]}"; do
      # export KEY=<qqch de non-vide et non-référence> = littéral en clair
      line=$(grep -nE "^[[:space:]]*export[[:space:]]+$k=" "$f" 2>/dev/null | head -1)
      [ -z "$line" ] && continue
      val=$(printf '%s' "$line" | sed -E "s/^[0-9]+:[[:space:]]*export[[:space:]]+$k=//; s/^[\"']//; s/[\"'][[:space:]]*$//")
      if [ -n "$val" ] && ! is_varref "$val"; then
        viol "$(basename "$f"):$k = export en clair (déplacer vers .env 600)"
      fi
    done
  done
}

check_removed_allow(){
  # Scanne settings.json ET settings.local.json (m2 : le gate ne doit pas être
  # muet sur les règles allow à secret retirées par Task 3 ET Task 4).
  for f in "$SETTINGS" "$SLOCAL"; do
    [ -f "$f" ] || continue
    for p in "${REMOVED_ALLOW_PATTERNS[@]}"; do
      if grep -qE "$p" "$f" 2>/dev/null; then
        viol "$(basename "$f") contient encore une règle allow '$p' (doit être RETIRÉE)"
      fi
    done
  done
}

check_claudejson(){
  # ~/.claude.json (config CLI, RÉÉCRIT par le CLI) porte aussi des mcpServers —
  # angle mort découvert en revue P0/P1b (B4) : mêmes secrets que mcp.json en clair.
  # Générique : toute valeur env secret-like ou header à chiffres len>=16 doit être ${VAR}.
  local cj="${CLAUDEJSON:-$HOME/.claude.json}"
  [ -f "$cj" ] || return
  local bad
  bad=$(python3 - "$cj" <<'PY'
import json,sys,re
d=json.load(open(sys.argv[1]))
DSN=re.compile(r'postgres(ql)?://[^:/@]+:[^@]+@')  # DSN à creds embarqués (MAJOR-1 revue)
for name,c in (d.get('mcpServers',{}) or {}).items():
    for k,v in (c.get('env') or {}).items():
        if not (isinstance(v,str) and '${' not in v): continue
        if (len(v)>=16 and re.search(r'KEY|TOKEN|SECRET|PASSWORD',k,re.I)) or DSN.search(v):
            print(f"{name}:env.{k}")
    for hk,hv in (c.get('headers') or {}).items():
        if isinstance(hv,str) and '${' not in hv and len(hv)>=16 and any(ch.isdigit() for ch in hv):
            print(f"{name}:headers.{hk}")
PY
)
  local line
  while IFS= read -r line; do
    [ -n "$line" ] && viol "~/.claude.json mcpServers[$line] = littéral (attendu \${VAR})"
  done <<< "$bad"
}

run_all(){ VIOL=0; check_mcp; check_settings_env; check_shell; check_removed_allow; check_claudejson; }

if [ "${1:-}" = "--self-test" ]; then
  # Contrôle positif : sur l'état ACTUEL (pré-migration), le détecteur DOIT trouver ≥1 violation.
  run_all
  if [ "$VIOL" -ge 1 ]; then
    echo "SELF-TEST OK : détecteur trouve $VIOL violation(s) sur l'état pré-migration (non-aveugle)."
    exit 0
  else
    echo "SELF-TEST ÉCHOUE : 0 violation sur état pré-migration = détecteur AVEUGLE (bug bash-lint). NE PAS déployer."
    exit 2
  fi
fi

echo "== Gate migration secrets (allowlist + assert \${VAR}) =="
run_all
if [ "$VIOL" -eq 0 ]; then echo "OK : 0 secret en clair résiduel sur les cibles connues."; exit 0
else echo "ÉCHEC : $VIOL violation(s) — migration incomplète."; exit 1; fi
