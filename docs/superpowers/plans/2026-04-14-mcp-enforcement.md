# MCP Enforcement — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Forcer l'utilisation des MCP disponibles plutôt que Bash/curl, et bloquer (pas juste logger) les violations LOI critiques R7 et R2.

**Architecture:** 4 correctifs indépendants et ordonnés par impact. Fix 1 et Fix 2 modifient `loi-op-enforcer.js` existant. Fix 3 ajoute un nouveau hook `mcp-intent-guard.js`. Fix 4 enrichit `LOI-OPERATIONNELLE-MCP-FIRST.md` (lu par le skill Mobutoo post-compaction) + `memory-search-start.sh`.

**Tech Stack:** Node.js (hooks Claude Code), Bash (hook startup), CLAUDE.md (instructions contexte)

> **Pré-requis :** Vérifier que `~/.claude` est un dépôt git avant de commencer :
> ```bash
> git -C ~/.claude log --oneline -1 || echo "WARN: ~/.claude n'est pas un dépôt git — les commits Tasks 1/2/3/5 échoueront"
> ```

---

## Contexte — État actuel

| Fichier | Rôle actuel | Problème |
|---------|-------------|----------|
| `~/.claude/hooks/loi-op-enforcer.js` | Advisory LOI R0-R11 | R7 ne bloque pas (exit 0), R2 idem |
| `~/.claude/hooks/memory-search-start.sh` | SessionStart Qdrant search | N'injecte pas de hint MCP schema |
| `~/.claude/settings.json` | Config hooks + permissions | Pas de hook MCP-intent |
| `/home/mobuone/VPAI/CLAUDE.md` | Instructions projet | Pas de table MCP-first exhaustive |

**Constat audit (2026-04-13/14) :**
- R7 violation confirmée session `07e3198a` — hook a loggué mais n'a pas bloqué (exit 0)
- R2/R8 violations Typebot — curl utilisé à la place de Playwright MCP
- MCP schemas sont **deferred** → Claude ne les appelle pas faute de schéma chargé
- Sessions longues → R0 TTL expire → MCP non consulté en milieu de session

---

## Fichiers touchés

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `~/.claude/hooks/loi-op-enforcer.js` | Modify | R7 + R2 → exit(2) bloquant |
| `~/.claude/hooks/mcp-intent-guard.js` | Create | Détection pattern Bash → hint MCP alternatif |
| `~/.claude/settings.json` | Modify | Enregistrer `mcp-intent-guard.js` comme PreToolUse:Bash |
| `/home/mobuone/VPAI/docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` | Modify | Table MCP-first exhaustive (lue par skill Mobutoo) |
| `~/.claude/hooks/memory-search-start.sh` | Modify | Émettre hints ToolSearch MCPs critiques au démarrage |

---

## Task 1 : Bloquer R7 (IP publique) dans loi-op-enforcer.js

**Fichiers :**
- Modify: `~/.claude/hooks/loi-op-enforcer.js:152-157`

Actuellement, R7 ajoute à `advisories[]` puis `process.exit(0)` — la commande passe quand même.
Le correctif : détecter R7 avant la boucle advisories et exit(2) immédiatement comme le fait le R0 gate.

- [ ] **Step 1 : Lire le fichier actuel pour avoir le contexte exact**

```bash
cat -n ~/.claude/hooks/loi-op-enforcer.js | sed -n '150,170p'
```

- [ ] **Step 2 : Remplacer le bloc R7 advisory par un bloc bloquant**

Localiser le bloc (ligne ~152) :
```js
// R7 — public IP Sese-AI instead of Tailscale
if (toolName === 'Bash' && /137\.74\.114\.167/.test(cmd)) {
  advisories.push(
    "LOI OP R7: Sese-AI public IP (137.74.114.167) detected. " +
    "Use Tailscale: mobuone@100.64.0.14. Direct violation of rule R7."
  );
}
```

Remplacer par :
```js
// R7 — public IP Sese-AI → BLOQUANT (exit 2)
if (toolName === 'Bash' && /137\.74\.114\.167/.test(cmd)) {
  process.stderr.write(
    `[R7-GATE] BLOQUÉ — IP publique Sese-AI détectée (137.74.114.167).\n\n` +
    `Utiliser Tailscale uniquement :\n` +
    `  ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14\n\n` +
    `Règle LOI R7 : jamais d'IP directe OVH depuis waza. Voir CLAUDE.md.\n`
  );
  process.exit(2);
}
```

- [ ] **Step 3 : Faire de même pour localhost:5678 (R7 bis)**

Localiser le bloc (ligne ~160) :
```js
// R7 — localhost:5678 from waza
if (toolName === 'Bash' && /localhost:5678|127\.0\.0\.1:5678/.test(cmd) && !/javisi_n8n/.test(cmd)) {
  advisories.push(...)
}
```

Remplacer par :
```js
// R7 — localhost:5678 → BLOQUANT (exit 2)
if (toolName === 'Bash' && /localhost:5678|127\.0\.0\.1:5678/.test(cmd) && !/javisi_n8n/.test(cmd)) {
  process.stderr.write(
    `[R7-GATE] BLOQUÉ — localhost:5678 détecté.\n\n` +
    `Port 5678 non accessible depuis waza (bound 127.0.0.1 Docker).\n` +
    `Utiliser : https://mayi.ewutelo.cloud (via Caddy+Tailscale).\n` +
    `Règle LOI R7. Voir CLAUDE.md.\n`
  );
  process.exit(2);
}
```

- [ ] **Step 4 : Tester — vérifier que exit(2) est bien renvoyé**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ssh mobuone@137.74.114.167 docker ps"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js; echo "exit: $?"
```

Attendu : stderr affiche `[R7-GATE] BLOQUÉ`, exit code = 2

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"curl http://localhost:5678/api/v1/workflows"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js; echo "exit: $?"
```

Attendu : exit code = 2

- [ ] **Step 5 : Tester que les commandes VPN légitimes passent**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 docker ps"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js; echo "exit: $?"
```

Attendu : exit code = 0 (IP 100.64.0.14 = pas de match)

- [ ] **Step 5b : Test négatif localhost:5678 — grep/cat ne doivent pas bloquer**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"grep -r localhost:5678 /home/mobuone/VPAI/docs"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js; echo "exit: $?"
```

Attendu : exit code = 0 (grep = lecture, pas d'appel réseau)

> **Note :** Si exit 2, le regex bloque les commandes de lecture. Restreindre le bloc localhost:5678 à :
> `/(curl|wget|ssh|docker)\b.*localhost:5678/.test(cmd)` pour ne cibler que les appels réseau.

- [ ] **Step 6 : Commit**

```bash
cd ~/.claude
git add hooks/loi-op-enforcer.js
git commit -m "fix(loi-r7): block public IP and localhost:5678 with exit(2) instead of advisory"
```

---

## Task 2 : Bloquer R2 (curl form/E2E → Playwright MCP) dans loi-op-enforcer.js

**Fichiers :**
- Modify: `~/.claude/hooks/loi-op-enforcer.js:128-134`

Même pattern que Task 1 : R2 est actuellement advisory. Les sessions Typebot ont violé R2.

- [ ] **Step 1 : Localiser le bloc R2 form/curl**

```bash
cat -n ~/.claude/hooks/loi-op-enforcer.js | sed -n '125,145p'
```

- [ ] **Step 2 : Passer R2 (curl /form/) en bloquant**

Remplacer :
```js
// R2 — Bash curl/node against n8n form path → use Playwright MCP instead
if (toolName === 'Bash' && /(curl|wget|node\s+.*\.js).*\/form\//.test(cmd) && !/mcp__playwright/.test(cmd)) {
  advisories.push(
    "LOI OP R2: E2E test of n8n form via curl/node detected. ..."
  );
}
```

Par :
```js
// R2 — curl/node sur mayi.ewutelo.cloud/form/ → BLOQUANT (exit 2)
// Restreint au domaine mayi pour éviter faux positifs sur d'autres services
if (toolName === 'Bash' && /(curl|wget|node\s+.*\.js).*mayi\.ewutelo\.cloud\/form\//.test(cmd)) {
  process.stderr.write(
    `[R2-GATE] BLOQUÉ — test E2E form n8n via curl/node détecté.\n\n` +
    `Utiliser Playwright MCP :\n` +
    `  1. ToolSearch("select:mcp__playwright__browser_navigate")\n` +
    `  2. browser_navigate → browser_fill_form → browser_click\n\n` +
    `Règle LOI R2 : curl ne gère pas le polling terminal du form. Voir CLAUDE.md R2.\n`
  );
  process.exit(2);
}
```

- [ ] **Step 3 : Tester**

```bash
# Positif — form sur mayi → doit bloquer
echo '{"tool_name":"Bash","tool_input":{"command":"curl -X POST https://mayi.ewutelo.cloud/form/abc123 -d name=test"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js 2>&1; echo "exit: $?"
```
Attendu : exit 2, message `[R2-GATE] BLOQUÉ`

```bash
# Négatif — webhook (non /form/) → ne doit pas bloquer
echo '{"tool_name":"Bash","tool_input":{"command":"curl -X POST https://mayi.ewutelo.cloud/webhook/test -d {}"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js; echo "exit: $?"
```
Attendu : exit 0

```bash
# Négatif — autre domaine avec /form/ → ne doit pas bloquer
echo '{"tool_name":"Bash","tool_input":{"command":"curl https://typebot.io/form/abc -d x=1"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js; echo "exit: $?"
```
Attendu : exit 0

- [ ] **Step 4 : Commit**

```bash
cd ~/.claude
git add hooks/loi-op-enforcer.js
git commit -m "fix(loi-r2): block curl on /form/ paths with exit(2), force Playwright MCP"
```

---

## Task 3 : Nouveau hook mcp-intent-guard.js — détection pattern Bash → MCP alternatif

**Fichiers :**
- Create: `~/.claude/hooks/mcp-intent-guard.js`
- Modify: `~/.claude/settings.json` (enregistrer le hook)

Ce hook détecte les patterns Bash qui ont un MCP équivalent disponible et injecte un hint ToolSearch. Il ne **bloque pas** (advisory) — son rôle est de rappeler le MCP et charger le schéma via hint.

> **Pré-requis Task 3 :** Vérifier quels MCPs sont réellement configurés dans `~/.claude/mcp.json` :
> ```bash
> python3 -c "import json; mcps=json.load(open('/home/mobuone/.claude/mcp.json')); print(list(mcps.get('mcpServers',{}).keys()))"
> ```
> Les patterns `nocodb`, `postgres`, `github` dans le hook sont inclus mais **ne sont utiles que si le MCP correspondant est configuré**. Si absent de mcp.json → supprimer le pattern du hook pour éviter des hints trompeurs.

- [ ] **Step 1 : Vérifier les MCPs configurés**

```bash
python3 -c "
import json
cfg = json.load(open('/home/mobuone/.claude/mcp.json'))
servers = list(cfg.get('mcpServers', {}).keys())
print('MCPs configurés:', servers)
# Patterns à conserver dans mcp-intent-guard.js uniquement si présents :
for name in ['n8n-docs', 'nocodb', 'postgres', 'github', 'playwright', 'docker']:
    status = 'OK' if any(name in s for s in servers) else 'ABSENT — retirer le pattern du hook'
    print(f'  {name}: {status}')
"
```

- [ ] **Step 2 : Créer mcp-intent-guard.js** (adapter les PATTERNS selon résultat Step 1)

```js
#!/usr/bin/env node
// mcp-intent-guard.js — PreToolUse:Bash hook
// Détecte les patterns Bash ayant un MCP équivalent.
// Advisory uniquement (exit 0) — fournit le nom exact de l'outil MCP + ToolSearch hint.
//
// Patterns couverts :
//   n8n API calls        → mcp__n8n-docs__*
//   NocoDB API calls     → mcp__nocodb__*
//   docker logs/ps       → mcp__docker__*
//   postgres psql        → mcp__postgres__*
//   curl vers typebot    → mcp__playwright__* (si form)
//   GitHub API curl      → mcp__github__*

const PATTERNS = [
  {
    // n8n REST API via curl
    regex: /curl.*mayi\.ewutelo\.cloud\/(api\/v1|webhook|rest)\//,
    mcp: 'mcp__n8n-docs__n8n_list_workflows',
    hint: 'mcp__n8n-docs__* (n8n_list_workflows, n8n_get_workflow, n8n_update_full_workflow, n8n_executions)',
    toolsearch: 'select:mcp__n8n-docs__n8n_list_workflows,mcp__n8n-docs__n8n_get_workflow,mcp__n8n-docs__n8n_update_full_workflow',
    rule: 'R3/R11',
  },
  {
    // NocoDB API via curl
    regex: /curl.*(nocodb|noco\.ewutelo|\/api\/v[12]\/tables)/,
    mcp: 'mcp__nocodb__list_records',
    hint: 'mcp__nocodb__* (list_records, insert_record, update_record, search_records, query)',
    toolsearch: 'select:mcp__nocodb__list_records,mcp__nocodb__insert_record,mcp__nocodb__query',
    rule: 'R8',
  },
  {
    // docker logs via ssh
    regex: /ssh.*docker\s+(logs|ps|inspect|exec)/,
    mcp: 'mcp__docker__get-logs',
    hint: 'mcp__docker__* (get-logs, list-containers) si contexte Docker local disponible',
    toolsearch: 'select:mcp__docker__get-logs,mcp__docker__list-containers',
    rule: 'R6',
  },
  {
    // psql direct via ssh
    regex: /ssh.*psql\s+-U/,
    mcp: 'mcp__postgres__pg_execute_query',
    hint: 'mcp__postgres__* (pg_execute_query, pg_execute_sql, pg_analyze_database)',
    toolsearch: 'select:mcp__postgres__pg_execute_query,mcp__postgres__pg_execute_sql',
    rule: 'R8',
  },
  {
    // GitHub API via curl
    regex: /curl.*api\.github\.com/,
    mcp: 'mcp__github__list_issues',
    hint: 'mcp__github__* (list_issues, list_pull_requests, get_file_contents, search_code)',
    toolsearch: 'select:mcp__github__list_issues,mcp__github__pull_request_read,mcp__github__search_code',
    rule: 'R8',
  },
];

let input = '';
const timer = setTimeout(() => process.exit(0), 3000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => input += c);
process.stdin.on('end', () => {
  clearTimeout(timer);
  try {
    const data = JSON.parse(input || '{}');
    if (data.tool_name !== 'Bash') { process.exit(0); }
    // Skip subagents
    if (data.session_type === 'task') { process.exit(0); }

    const cmd = (data.tool_input?.command || '').toString();
    const hints = [];

    for (const p of PATTERNS) {
      if (p.regex.test(cmd)) {
        hints.push(
          `[MCP-INTENT ${p.rule}] Bash détecté — MCP disponible :\n` +
          `  Outils : ${p.hint}\n` +
          `  Charger le schéma d'abord : ToolSearch("${p.toolsearch}")\n` +
          `  Ensuite appeler directement le MCP au lieu de cette commande Bash.`
        );
      }
    }

    if (hints.length === 0) { process.exit(0); }

    const output = {
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        additionalContext: hints.join('\n\n'),
      }
    };
    process.stdout.write(JSON.stringify(output));
    process.exit(0);
  } catch (_) {
    process.exit(0);
  }
});
```

- [ ] **Step 3 : Rendre le fichier exécutable**

```bash
chmod +x ~/.claude/hooks/mcp-intent-guard.js
```

- [ ] **Step 4 : Tester le hook en isolation**

```bash
# Test n8n — doit afficher le hint MCP
OUT=$(echo '{"tool_name":"Bash","tool_input":{"command":"curl -sS https://mayi.ewutelo.cloud/api/v1/workflows"}}' \
  | node ~/.claude/hooks/mcp-intent-guard.js)
python3 -c "
import json, sys
s = '''$OUT'''
d = json.loads(s) if s.strip() else {}
ctx = d.get('hookSpecificOutput', {}).get('additionalContext', 'NO HINT')
print(ctx)
"
```

Attendu : ligne `[MCP-INTENT R3/R11]` avec hint ToolSearch

```bash
# Test commande innocente — stdout vide, pas de JSONDecodeError
OUT=$(echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' \
  | node ~/.claude/hooks/mcp-intent-guard.js)
python3 -c "
import json
s = '''$OUT'''
d = json.loads(s) if s.strip() else {}
print('OK — no hint emitted' if not d else d.get('hookSpecificOutput',{}).get('additionalContext',''))
"
```

Attendu : `OK — no hint emitted`

- [ ] **Step 5 : Insérer dans le tableau PreToolUse de settings.json**

Utiliser python3 pour insérer proprement (évite erreur de syntaxe JSON manuelle) :

```bash
python3 - << 'EOF'
import json

path = '/home/mobuone/.claude/settings.json'
with open(path) as f:
    cfg = json.load(f)

new_entry = {
    "matcher": "Bash",
    "hooks": [{
        "type": "command",
        "command": "node \"/home/mobuone/.claude/hooks/mcp-intent-guard.js\"",
        "timeout": 3
    }]
}

pre = cfg.setdefault('hooks', {}).setdefault('PreToolUse', [])

# Insérer après loi-op-enforcer, avant gsd-validate-commit
idx = next(
    (i for i, e in enumerate(pre)
     if any('loi-op-enforcer' in h.get('command','') for h in e.get('hooks',[]))),
    len(pre) - 1
)
pre.insert(idx + 1, new_entry)

with open(path, 'w') as f:
    json.dump(cfg, f, indent=2)

print(f"Inserted at index {idx + 1} — total PreToolUse entries: {len(pre)}")
EOF
```

Attendu : `Inserted at index N — total PreToolUse entries: N+1`

- [ ] **Step 6 : Vérifier que settings.json est JSON valide et que l'entrée est présente**

```bash
python3 -c "
import json
cfg = json.load(open('/home/mobuone/.claude/settings.json'))
entries = cfg['hooks']['PreToolUse']
found = any('mcp-intent-guard' in h.get('command','') for e in entries for h in e.get('hooks',[]))
print('OK — mcp-intent-guard registered' if found else 'ERROR — not found')
print(f'Total PreToolUse entries: {len(entries)}')
"
```

Attendu : `OK — mcp-intent-guard registered`

- [ ] **Step 7 : Commit**

```bash
cd ~/.claude
git add hooks/mcp-intent-guard.js settings.json
git commit -m "feat(hooks): add mcp-intent-guard advisory for n8n/nocodb/docker/postgres/github patterns"
```

---

## Task 4 : Enrichir LOI-OPERATIONNELLE-MCP-FIRST.md avec table MCP-first exhaustive

**Fichiers :**
- Modify: `/home/mobuone/VPAI/docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md`

> **Raison (option A) :** la table va dans LOI-OP-MCP-FIRST.md (lu par le skill Mobutoo via Step 1 Read) et non dans CLAUDE.md. CLAUDE.md est toujours chargé au démarrage — la table y serait redondante. Le skill Mobutoo est invoqué post-compaction quand CLAUDE.md peut être hors contexte actif → la table doit être dans la source que le skill lit.

- [ ] **Step 1 : Lire la section `## Checklist MCP disponibles` de LOI-OP**

```bash
grep -n "Checklist MCP\|MCP-First\|INTERDIT\|UTILISER" /home/mobuone/VPAI/docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md | head -10
```

- [ ] **Step 2 : Ajouter la table MCP-First après la section `## Checklist MCP disponibles`**

Localiser la ligne contenant `## Checklist MCP disponibles` et ajouter **en dessous** (après le tableau existant) :

```markdown
## MCP-First Table — INTERDIT → UTILISER À LA PLACE

> Toujours charger le schéma d'abord : `ToolSearch("select:<mcp_tool_name>")`

| INTERDIT | UTILISER À LA PLACE | Règle |
|----------|---------------------|-------|
| `curl *mayi.ewutelo.cloud/api/v1/*` | `mcp__n8n-docs__n8n_list_workflows` / `n8n_get_workflow` / `n8n_update_full_workflow` | R3/R11 |
| `curl *mayi.ewutelo.cloud/webhook/*` | `mcp__n8n-docs__n8n_test_workflow` | R3 |
| `curl *nocodb*/api/v2/tables/*` | `mcp__nocodb__list_records` / `insert_record` / `query` | R8 |
| `ssh * docker logs *` | `mcp__docker__get-logs` | R6 |
| `ssh * docker ps *` | `mcp__docker__list-containers` | R6 |
| `ssh * psql -U *` | `mcp__postgres__pg_execute_query` | R8 |
| `curl *api.github.com*` | `mcp__github__list_issues` / `search_code` / `pull_request_read` | R8 |
| `curl */form/* -d *` | `mcp__playwright__browser_navigate` + `browser_fill_form` | R2 |
```

- [ ] **Step 3 : Vérifier que le fichier est bien formé**

```bash
python3 -c "
with open('/home/mobuone/VPAI/docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md') as f:
    content = f.read()
assert '## MCP-First Table' in content
assert 'mcp__n8n-docs__n8n_list_workflows' in content
print('OK — section présente')
"
```

- [ ] **Step 4 : Commit**

```bash
cd /home/mobuone/VPAI
git add docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md
git commit -m "docs(loi-op): add MCP-First enforcement table — Mobutoo skill picks it up post-compaction"
```

---

## Task 5 : Injecter hint ToolSearch dans le hook de démarrage de session

**Fichiers :**
- Modify: `~/.claude/hooks/memory-search-start.sh`

Au démarrage de session, injecter un bloc de hints rappelant les MCPs disponibles et la procédure ToolSearch. Cela charge le contexte dès le début et évite que Claude "oublie" les MCPs deferred.

- [ ] **Step 1 : Lire la fin du fichier memory-search-start.sh**

```bash
cat -n ~/.claude/hooks/memory-search-start.sh
```

- [ ] **Step 2 : Ajouter le bloc MCP hint en fin de fichier**

À la fin du fichier (après la dernière commande), ajouter :

```bash
# ── MCP Schema Preload Hints ─────────────────────────────────────────────────
# Rappel des MCPs disponibles et procédure de chargement de schéma.
# Les outils MCP sont "deferred" dans Claude Code — leur schéma doit être chargé
# via ToolSearch avant usage.

cat << 'MCPHINTS'
## MCP Schema Loading — Required Before First Use

MCPs available (schemas deferred — load before calling):

**n8n workflows:**
  ToolSearch("select:mcp__n8n-docs__n8n_list_workflows,mcp__n8n-docs__n8n_get_workflow,mcp__n8n-docs__n8n_update_full_workflow,mcp__n8n-docs__validate_workflow")

**NocoDB:**
  ToolSearch("select:mcp__nocodb__list_records,mcp__nocodb__insert_record,mcp__nocodb__query,mcp__nocodb__search_records")

**Docker:**
  ToolSearch("select:mcp__docker__get-logs,mcp__docker__list-containers,mcp__docker__deploy-compose")

**Playwright (E2E forms):**
  ToolSearch("select:mcp__playwright__browser_navigate,mcp__playwright__browser_fill_form,mcp__playwright__browser_click,mcp__playwright__browser_snapshot")

**Qdrant memory:**
  ToolSearch("select:mcp__qdrant__qdrant-find")

Rule: NEVER use curl/Bash for operations covered by these MCPs. See CLAUDE.md MCP-First Table.
MCPHINTS
```

- [ ] **Step 3 : Tester le script en isolation**

```bash
bash ~/.claude/hooks/memory-search-start.sh /home/mobuone/VPAI 2>/dev/null | grep -A 5 "MCP Schema"
```

Attendu : bloc `## MCP Schema Loading` visible dans la sortie

- [ ] **Step 4 : Commit**

```bash
cd ~/.claude
git add hooks/memory-search-start.sh
git commit -m "feat(session-start): inject MCP schema preload hints at session startup"
```

---

## Validation finale — smoke test complet

- [ ] **Test R7 bloquant**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ssh mobuone@137.74.114.167 docker ps"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js 2>&1; echo "Exit: $?"
```
Attendu : `[R7-GATE] BLOQUÉ`, exit 2

- [ ] **Test R2 bloquant**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"curl -X POST https://mayi.ewutelo.cloud/form/test -d name=x"}}' \
  | node ~/.claude/hooks/loi-op-enforcer.js 2>&1; echo "Exit: $?"
```
Attendu : `[R2-GATE] BLOQUÉ`, exit 2

- [ ] **Test MCP-intent-guard (advisory)**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"curl -sS https://mayi.ewutelo.cloud/api/v1/workflows"}}' \
  | node ~/.claude/hooks/mcp-intent-guard.js 2>/dev/null | python3 -m json.tool | grep "MCP-INTENT"
```
Attendu : ligne `[MCP-INTENT R3/R11]`

- [ ] **Test session startup hint**

```bash
bash ~/.claude/hooks/memory-search-start.sh /home/mobuone/VPAI 2>/dev/null | grep "ToolSearch"
```
Attendu : 5+ lignes ToolSearch visibles

- [ ] **Test settings.json valide**

```bash
python3 -c "import json; json.load(open('/home/mobuone/.claude/settings.json')); print('settings.json OK')"
```
Attendu : `settings.json OK`

---

## Résumé des commits attendus

| Task | Commit message |
|------|----------------|
| 1 | `fix(loi-r7): block public IP and localhost:5678 with exit(2)` |
| 2 | `fix(loi-r2): block curl on /form/ paths, force Playwright MCP` |
| 3 | `feat(hooks): add mcp-intent-guard advisory for n8n/nocodb/docker/postgres/github` |
| 4 | `docs(loi-op): add MCP-First enforcement table — Mobutoo skill picks it up post-compaction` |
| 5 | `feat(session-start): inject MCP schema preload hints at startup` |
