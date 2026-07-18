#!/usr/bin/env bash
# n8n-validate-fallback.sh — Validateur R1 fallback, INDÉPENDANT de la session MCP.
# Autorité = check structurel Python (R6: yigitkonur rate connexions orphelines + IF v2).
# HTTP n8n-mcp local = best-effort informatif, ne flippe jamais un PASS→FAIL, ne bloque pas.
# Émet le sentinel "[N8N-VALIDATE-CLI] PASS" sur stdout SEULEMENT si succès.
set -euo pipefail
WF="${1:?usage: n8n-validate-fallback.sh <workflow.json>}"

# rex-capture (livrable 2, harness autoring) — best-effort, jamais bloquant,
# n'affecte jamais le code de sortie de ce script. Opt-out: REX_CAPTURE=0.
REX_CAPTURE_SCRIPT="$(dirname "$0")/n8n-authoring/rex-capture.sh"
rex_capture_on_fail() {
  local step="$1" err="$2"
  if [ -x "$REX_CAPTURE_SCRIPT" ]; then
    "$REX_CAPTURE_SCRIPT" "$WF" "$step" "$err" || true
  fi
}

[ -f "$WF" ] || { echo "[N8N-VALIDATE-CLI] FAIL: fichier introuvable: $WF" >&2; rex_capture_on_fail "validate-file-missing" "fichier introuvable: $WF"; exit 1; }

set +e
PY_OUTPUT=$(python3 - "$WF" <<'PY' 2>&1
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"[N8N-VALIDATE-CLI] FAIL: JSON invalide: {e}", file=sys.stderr); sys.exit(1)
names = [n.get('name') for n in d.get('nodes', [])]
nameset = set(names)
errs = []
dupes = sorted({n for n in nameset if names.count(n) > 1})
if dupes: errs.append(f"noms de nodes dupliqués: {dupes}")
missing_src = sorted(set(d.get('connections', {}).keys()) - nameset)
if missing_src: errs.append(f"connexions depuis nodes inconnus: {missing_src}")
for src, outs in d.get('connections', {}).items():
    for branch in (outs.get('main', []) or []):
        for c in (branch or []):
            t = c.get('node')
            if t and t not in nameset:
                errs.append(f"cible de connexion inconnue: {t} (depuis {src})")
ifv2 = [n.get('name') for n in d.get('nodes', [])
        if n.get('type') == 'n8n-nodes-base.if' and n.get('typeVersion', 1) >= 2]
if ifv2:
    # R9 = garde-fou d'AUTORING, pas de déploiement (prod exécute déjà 79 IF v2). NOTE, jamais FAIL.
    print(f"[N8N-VALIDATE-CLI] NOTE: IF v2 présents (R9 authoring guard; déploiement toléré): {ifv2}", file=sys.stderr)
if errs:
    print("[N8N-VALIDATE-CLI] FAIL: " + "; ".join(errs), file=sys.stderr); sys.exit(1)
print(f"  structurel OK — {len(names)} nodes, {len(d.get('connections', {}))} sources de connexion", file=sys.stderr)
PY
)
PY_RC=$?
set -e
echo "$PY_OUTPUT" >&2
if [ "$PY_RC" -ne 0 ]; then
  rex_capture_on_fail "validate-structural" "$PY_OUTPUT"
  exit 1
fi

# best-effort: n8n-mcp local stateless (informatif). N'affecte JAMAIS le code de sortie.
MCP_URL="${N8N_MCP_URL:-http://localhost:3001}"
MCP_TOKEN="${N8N_MCP_AUTH_TOKEN:-}"
if [ -n "$MCP_TOKEN" ]; then
  if timeout 8 curl -sf -o /dev/null "$MCP_URL/health" -H "Authorization: Bearer $MCP_TOKEN" 2>/dev/null; then
    echo "[N8N-VALIDATE-CLI] info: n8n-mcp local joignable ($MCP_URL) — validation sémantique disponible via MCP session" >&2
  else
    echo "[N8N-VALIDATE-CLI] info: n8n-mcp local injoignable — structurel seul (non bloquant)" >&2
  fi
fi

echo "[N8N-VALIDATE-CLI] PASS: $WF"
