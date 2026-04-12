# PLAN — Option C LOI OPÉRATIONNELLE gate reset

**Objectif :** Rendre le gate R0 `loi-op-enforcer.js` auto-réarmant (multi-scenario) au lieu de
rester levé définitivement après le premier `search_memory`.

**Séquence obligatoire :** Task 1 → Task 2 → Task 3 (3a puis 3b) → Task 4
Les tasks 2 et 3b modifient le même fichier — exécuter dans l'ordre, sans interleave.

---

## Task 1 — SKILL.md : Step 4 active reset + renommage Step 5

**Fichier :** `/home/mobuone/.claude/skills/Mobutoo/SKILL.md`

**Changement :**

Remplacer la section `**Step 4 — Resume work**` actuelle (lignes 36-43) par :

```markdown
**Step 4 — Reset des gates R0**

Execute the following Bash command (not just display — actually run it):

```bash
rm -f /tmp/claude-r0-done*
```

Output confirmation: `[R0-RESET] Markers supprimés — R0 gate ré-armé pour cette session.`

**Step 5 — Resume work**

Append exactly:

```
---
*Source: docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md — resume work normally.*
```
```

Le Step 4 ancien (footer `---\n*Source...*`) devient Step 5.
Le Step 3 (Display MCPs) reste inchangé.

**Critère de succès :** Le fichier contient `**Step 4 — Reset des gates R0**` avec la commande
`rm -f /tmp/claude-r0-done*` dans un bloc bash, et `**Step 5 — Resume work**` pour le footer.
Invoquer `/Mobutoo` depuis une session Claude doit déclencher la suppression des markers.

**Commit :** `feat(loi-op): SKILL.md Step 4 → active R0 reset via rm -f /tmp/claude-r0-done*`

---

## Task 2 — loi-op-enforcer.js : restructure + L2 pre-deploy reset

**Fichier :** `/home/mobuone/.claude/hooks/loi-op-enforcer.js`

**Changement (deux sous-étapes à faire en une seule édition) :**

### 2a — Extraire les variables du bloc R0 GATE vers la portée externe

Actuellement, `haystack`, `topicMatch`, `isStateModifyingBash`, `isWriteEdit` sont déclarés
à l'intérieur de `if (!require('fs').existsSync(MARKER))`. Les déplacer AVANT ce bloc.

Remplacer le bloc actuel (lignes 44-73) par :

```js
// ── Variables partagées R0 / L2 ─────────────────────────────────────────────
const haystack = [cmd, filePath, content.slice(0, 500)].join(' ');
const topicMatch = KNOWN_TOPICS.test(haystack);
const isStateModifyingBash = toolName === 'Bash' && STATE_MODIFYING_BASH.test(cmd);
const isWriteEdit = (toolName === 'Write' || toolName === 'Edit');

// ── L2 PRE-DEPLOY RESET ─────────────────────────────────────────────────────
// Avant tout deploy state-modifying sur un topic connu, supprimer TOUS les
// markers R0 — le prochain appel ré-exigera un memory search.
if (topicMatch && isStateModifyingBash) {
  try {
    require('fs').readdirSync('/tmp')
      .filter(f => f.startsWith('claude-r0-done'))
      .forEach(f => require('fs').unlinkSync('/tmp/' + f));
    advisories.push('[R0-RESET-L2] Markers R0 supprimés avant deploy — R0 sera requis au prochain appel sur ce topic.');
  } catch (_) {}
}
// ── FIN L2 PRE-DEPLOY RESET ─────────────────────────────────────────────────

// ── R0 GATE (BLOCKING) ──────────────────────────────────────────────────────
// Block state-modifying actions on known topics until search_memory has
// been explicitly called this session (marker /tmp/claude-r0-done).
//
// Does NOT block: pure-read Bash (git status, docker ps, ls…)
// DOES block: Write/Edit on topic + state-modifying Bash on topic
if (!require('fs').existsSync(MARKER)) {
  if (topicMatch) {
    // Never block the memory search command itself
    if (MEMORY_CMD.test(cmd)) {
      // pass — PostToolUse r0-marker.js will create the marker
    } else {
      if (isStateModifyingBash || isWriteEdit) {
        const topic = (haystack.match(KNOWN_TOPICS) || [])[1] || 'known topic';
        process.stdout.write(
          `[R0-GATE] BLOQUÉ — topic "${topic}" détecté mais memory search pas encore fait cette session.\n\n` +
          `Faire d'abord :\n` +
          `  set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a\n` +
          `  /opt/workstation/ai-memory-worker/.venv/bin/python \\\n` +
          `    /opt/workstation/ai-memory-worker/search_memory.py \\\n` +
          `    --config /opt/workstation/configs/ai-memory-worker/config.yml \\\n` +
          `    --query "${topic}" --limit 3\n\n` +
          `Puis relancer la commande.\n`
        );
        process.exit(2);
      }
    }
  }
}
// ── FIN R0 GATE ─────────────────────────────────────────────────────────────
```

**Note importante :** Le bloc L2 utilise `advisories.push(...)` mais `advisories` est déclaré
à la ligne 75 du fichier original (après le bloc R0). Déplacer également la déclaration
`const advisories = [];` AVANT le bloc L2 (juste après les variables partagées).

### Ordre final des blocs dans le fichier après edit :

```
1. Subagent skip (inchangé)
2. Constantes : KNOWN_TOPICS, STATE_MODIFYING_BASH, MEMORY_CMD, MARKER (inchangées)
3. Variables partagées : haystack, topicMatch, isStateModifyingBash, isWriteEdit [NOUVEAU]
4. const advisories = []; [déplacé ici depuis ligne 75]
5. Bloc L2 PRE-DEPLOY RESET [NOUVEAU]
6. Bloc R0 GATE (restructuré — utilise les variables, ne les redéclare pas)
7. Advisory R0 doc-creation (inchangé)
8. Advisories R1…R11, V3 (inchangés)
9. Output + exit (inchangé)
```

**Critère de succès :**
- `node /home/mobuone/.claude/hooks/loi-op-enforcer.js` ne lève pas d'erreur de syntaxe
  (`node --check /home/mobuone/.claude/hooks/loi-op-enforcer.js` → exit 0)
- Un input simulé deploy ansible sur topic connu retourne un advisory L2-RESET ET entre dans
  le R0 GATE si le marker n'existe pas

**Commit :** `feat(loi-op): L2 pre-deploy R0 reset — restructure variables + reset markers avant deploy`

---

## Task 3 — L1 markers per-topic (r0-marker.js + loi-op-enforcer.js)

**Dépend de Task 2** (loi-op-enforcer.js doit être restructuré avant 3b).

### 3a — r0-marker.js : écriture du marker per-topic

**Fichier :** `/home/mobuone/.claude/hooks/r0-marker.js`

Après la ligne `fs.writeFileSync(MARKER, new Date().toISOString() + '\n');` (ligne 31),
ajouter :

```js
      // L1 — marker per-topic
      const KNOWN_TOPICS_MARKER = /(n8n|webhook|gotenberg|caddy|litellm|openclaw|kitsu|nocodb|postgres|qdrant|headscale|tailscale|typebot|firefly|plane|molecule|ansible)/i;
      const topicM = cmd.match(KNOWN_TOPICS_MARKER);
      if (topicM) {
        const topicName = topicM[1].toLowerCase();
        fs.writeFileSync(`/tmp/claude-r0-done-${topicName}`, new Date().toISOString() + '\n');
        process.stdout.write(`[R0-MARKER] /tmp/claude-r0-done-${topicName} créé — R0 satisfait pour topic "${topicName}".\n`);
      }
```

Le bloc existant `if (toolName === 'Bash' && MEMORY_CMD.test(cmd))` devient :

```js
    if (toolName === 'Bash' && MEMORY_CMD.test(cmd)) {
      fs.writeFileSync(MARKER, new Date().toISOString() + '\n');
      process.stdout.write('[R0-MARKER] /tmp/claude-r0-done créé — R0 satisfait pour cette session.\n');
      // L1 — marker per-topic
      const KNOWN_TOPICS_MARKER = /(n8n|webhook|gotenberg|caddy|litellm|openclaw|kitsu|nocodb|postgres|qdrant|headscale|tailscale|typebot|firefly|plane|molecule|ansible)/i;
      const topicM = cmd.match(KNOWN_TOPICS_MARKER);
      if (topicM) {
        const topicName = topicM[1].toLowerCase();
        fs.writeFileSync(`/tmp/claude-r0-done-${topicName}`, new Date().toISOString() + '\n');
        process.stdout.write(`[R0-MARKER] /tmp/claude-r0-done-${topicName} créé — R0 satisfait pour topic "${topicName}".\n`);
      }
    }
```

### 3b — loi-op-enforcer.js : OR logic dans le gate R0

**Fichier :** `/home/mobuone/.claude/hooks/loi-op-enforcer.js`

Dans le bloc R0 GATE restructuré par Task 2, remplacer :

```js
if (!require('fs').existsSync(MARKER)) {
```

par :

```js
const topicName = (haystack.match(KNOWN_TOPICS) || [])[1];
const perTopicMarker = topicName ? `/tmp/claude-r0-done-${topicName.toLowerCase()}` : null;
const markerExists = require('fs').existsSync(MARKER) || (perTopicMarker && require('fs').existsSync(perTopicMarker));
if (!markerExists) {
```

**Logique :** le gate est satisfait si le marker générique OU le marker per-topic existe.
Ne jamais exiger les deux.

**Critère de succès (3a + 3b) :**
- `node --check /home/mobuone/.claude/hooks/r0-marker.js` → exit 0
- `node --check /home/mobuone/.claude/hooks/loi-op-enforcer.js` → exit 0
- Simulation : si `/tmp/claude-r0-done-n8n` existe mais pas `/tmp/claude-r0-done`,
  un Write sur un fichier n8n ne doit PAS être bloqué par R0 GATE.

**Commit :** `feat(loi-op): L1 per-topic markers — r0-marker.js écriture + loi-op-enforcer.js OR logic`

---

## Task 4 — error-escalator.js : L3 error cascade reset

**Fichier :** `/home/mobuone/.claude/hooks/error-escalator.js`

**Changement :** À l'intérieur du bloc `if (count >= THRESHOLD)`, après le
`process.stdout.write(...)` de méta-cognition et AVANT le reset du compteur
`fs.writeFileSync(counterFile, '0')`, insérer :

```js
    // L3 — R0 reset sur cascade d'erreurs topic connu
    const tool_input = data.tool_input || {};
    const failedCmd = (tool_input.command || tool_input.file_path || '').toString();
    const KNOWN_TOPICS_L3 = /(n8n|webhook|gotenberg|caddy|litellm|openclaw|kitsu|nocodb|postgres|qdrant|headscale|tailscale|typebot|firefly|plane|molecule|ansible)/i;
    if (KNOWN_TOPICS_L3.test(failedCmd)) {
      try {
        fs.readdirSync('/tmp')
          .filter(f => f.startsWith('claude-r0-done'))
          .forEach(f => fs.unlinkSync('/tmp/' + f));
        process.stdout.write('[R0-RESET-L3] ' + count + ' erreurs consécutives sur topic connu — markers R0 supprimés.\n');
      } catch (_) {}
    }
```

Le bloc `if (count >= THRESHOLD)` final doit ressembler à :

```js
  if (count >= THRESHOLD) {
    process.stdout.write(
      `[error-escalator] ${count} consecutive tool errors.\n` +
      `STOP. Before continuing:\n` +
      `1. State the hypothesis you are testing\n` +
      `2. What evidence would confirm OR deny it\n` +
      `3. Whether this requires human input\n` +
      `If you've had ${THRESHOLD}+ failures on the same approach: change approach, don't retry.\n`
    );
    // L3 — R0 reset sur cascade d'erreurs topic connu
    const tool_input = data.tool_input || {};
    const failedCmd = (tool_input.command || tool_input.file_path || '').toString();
    const KNOWN_TOPICS_L3 = /(n8n|webhook|gotenberg|caddy|litellm|openclaw|kitsu|nocodb|postgres|qdrant|headscale|tailscale|typebot|firefly|plane|molecule|ansible)/i;
    if (KNOWN_TOPICS_L3.test(failedCmd)) {
      try {
        fs.readdirSync('/tmp')
          .filter(f => f.startsWith('claude-r0-done'))
          .forEach(f => fs.unlinkSync('/tmp/' + f));
        process.stdout.write('[R0-RESET-L3] ' + count + ' erreurs consécutives sur topic connu — markers R0 supprimés.\n');
      } catch (_) {}
    }
    // Reset after escalation to avoid infinite escalation loop
    fs.writeFileSync(counterFile, '0');
  }
```

**Critère de succès :**
- `node --check /home/mobuone/.claude/hooks/error-escalator.js` → exit 0
- Le check `tool_input.command || tool_input.file_path` couvre les deux types d'outils
  (Bash → `command`, Write/Edit → `file_path`).
- Jamais d'exit(1) — le `try/catch` garantit la résilience fs.

**Commit :** `feat(loi-op): L3 error cascade reset — R0 markers supprimés après ${THRESHOLD} erreurs sur topic connu`

---

## Contraintes transversales

| Contrainte | Vérification |
|---|---|
| Jamais `exit(1)` dans les hooks | `grep -n 'exit(1)' *.js` → 0 résultats |
| R0 GATE conserve `exit(2)` | Inchangé dans le bloc GATE |
| OR logic L1 | Generic marker OU per-topic suffit — jamais les deux requis |
| Silent catch sur toutes les ops fs | Tous les blocs try/catch ne propagent pas l'erreur |
| L3 check `command \|\| file_path` | Les deux champs inspectés pour Bash et Write/Edit |

## Vérification finale (après les 4 tasks)

```bash
node --check /home/mobuone/.claude/hooks/loi-op-enforcer.js && echo "OK loi-op"
node --check /home/mobuone/.claude/hooks/r0-marker.js && echo "OK r0-marker"
node --check /home/mobuone/.claude/hooks/error-escalator.js && echo "OK error-escalator"
grep -n 'Step 4\|Step 5\|R0-RESET\|rm -f' /home/mobuone/.claude/skills/Mobutoo/SKILL.md
```

Tous les `node --check` doivent sortir 0. Le grep SKILL.md doit retourner les 4 patterns.
