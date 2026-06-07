# Analyse Sessions 2026-04-13

> Généré le 2026-04-13 — READ-ONLY, aucune modification de code.
> Source: analyse JSONL + LOI-OPERATIONNELLE-MCP-FIRST.md

---

## Résumé exécutif

**5 sessions** ce jour — durée cumulée ~4h (07:35→11:27). Tâche principale : déployer un bot Typebot MOP-NOC multi-actes avec 3 workflows n8n (mop-route, mop-get, mop-generate) + route Caddy /files/*.

**Résultat final : succès** — E2E Playwright confirmé à 11:27 (ACT 1+2 validés, INC créé, SOPs retournées).

**Blocage principal (~90 min, 08:41→09:08)** : l'API REST n8n /api/v1/workflows retournait 404 malgré Caddy correctement configuré. Cause : clé API n8n invalide (ancienne clé désactivée ou sans scope). Résolution via Playwright browser_evaluate sur /rest/ (API interne) au lieu de /api/v1/.

**Problèmes hooks** : loi-op-enforcer.js a généré **48 erreurs** "No stderr output" qui ont annulé 2 appels Bash et fragmenté l'exécution.

---

## Sessions analysées

| Session | Taille | Heure | Tâche | Outils | Blocages |
|---------|--------|-------|-------|--------|---------|
| c4575137 | 132KB | 07:35-08:13 | Init LOI-OP + check MCP status | 7 tools (5 Bash) | Aucun — session courte de setup |
| 3f165a8f | 350KB | 08:14-08:30 | Debug Playwright MCP (chromium ARM64) | 51 tools (47 Bash) | Chromium non trouvé pour ARM64, résolu en modifiant .claude.json |
| eab94b3a | 6.5MB | 08:36-11:27 | Déploiement complet MOP-NOC Typebot | 737 tools | n8n API 404 (90min), hook errors (48x) |
| 6697400c | 155KB | 09:46-10:14 | Vérification indexation DOCS n8n dans Qdrant | 13 tools | DOCS non indexé (attendu) |
| 71ede1f9 | 62KB | 11:21-11:23 | Délégation analyse sessions | 6 tools | Aucun — pivot vers subagent |

---

## Violations LOI OPERATIONNELLE

### Vue globale

| Règle | Session | Violations | Gravité |
|-------|---------|-----------|---------|
| **R0** | 3f165a8f, c4575137, 71ede1f9 | Jamais appelé (0 qdrant-find, 0 search_memory.py) | Haute |
| **R0** (timing) | eab94b3a | R0 appelé à pos 18/718 — APRÈS 7 TaskCreate et 1 Skill | Moyenne |
| **R1** | eab94b3a | Premier make deploy-role à 08:42 (pos 39), premier validate_workflow à 09:08 (pos 173) — ~90min d'écart. NOTE: concerne Caddy, pas un import workflow n8n direct — R1 strictement respecté pour les workflows. | Faible |
| **R3** (browser_evaluate workaround) | eab94b3a | 75 appels browser_evaluate sur /rest/ pour contourner échec API /api/v1/ | Haute |
| **R6** | 3f165a8f | 47 Bash calls pour déboguer Playwright, 0 subagent délégué | Moyenne |
| **R6** | eab94b3a | 325 Bash calls (44.1% des tools) — dépasse seuil >10 Bash sans délégation | Moyenne |
| **R7** | eab94b3a | 7 violations — IP publique 137.74.114.167 et localhost:5678 dans commandes Bash | Haute |

### Détail R0 — timing dans la session principale

```
pos  1-7  : Read (lecture plan)
pos  8    : Skill(executing-plans)  <- travail démarré
pos  9-14 : TaskCreate x 6         <- plan exécuté AVANT R0
pos 15-16 : search_memory.py via Bash  <- R0 enfin déclenché
pos 18    : mcp__qdrant__qdrant-find   <- qdrant appelé
```

L'ordre correct aurait été : R0 → lecture plan → TaskCreate. La session a créé 6 tâches AVANT d'interroger la mémoire.

### Détail R7 — violations nettes à 10:33

```
[10:33:29] Bash: scp -i ~/.ssh/seko-vpn-deploy -P 804 ... mobuone@137.74.114.167:/tmp/...
[10:33:39] Bash: ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 "cat > /tmp/..."
```

Hook loi-op-enforcer.js a détecté et alerté — mais pas bloqué (mode advisory).

### Détail browser_evaluate workaround (post-404)

```javascript
// 75 appels browser_evaluate du type :
async () => {
  const loginRes = await fetch('/rest/login', { method: 'POST', credentials: 'include' });
  const res = await fetch('/rest/workflows/FFIkjYMyxLdHroAN', { credentials: 'include' });
  // PUT workflow via /rest/ interne, pas /api/v1/ externe
}
```

---

## Patterns récurrents

### 1. Hook loi-op-enforcer.js instable (48 erreurs)

loi-op-enforcer.js génère "No stderr output" de façon intermittente. Cela a causé **2 annulations de Bash** (08:41 et 08:42). Cause probable : le hook n'est pas thread-safe pour les appels Bash parallèles — stdin vide sur appels parallélisés.

```
[08:41:23] PreToolUse:Bash hook error: [...loi-op-enforcer.js]: No stderr output
[08:41:24] <tool_use_error>Cancelled: parallel tool call Bash(make deploy...) errored
[08:42:14] PreToolUse:Bash hook error: [...loi-op-enforcer.js]: No stderr output
[08:42:15] <tool_use_error>Cancelled: parallel tool call Bash(make deploy...) errored
```

bash-lint.js : 6 erreurs supplémentaires (08:56, 08:57, 09:55, 10:56, 10:57, 10:57).

### 2. browser_evaluate comme outil universel de débogage n8n (75 appels)

Quand /api/v1/ a retourné 404, pivot vers browser_evaluate sur /rest/ depuis Playwright. Ingénieux mais non documenté dans la LOI-OP. A fonctionné à partir de 10:00. Risque R10 : cette technique court-circuite REST API PUT (R11) — vérifier que workflow_history est bien mis à jour.

### 3. Bash grep au lieu du tool Grep (139 occurrences)

139 Bash calls sur 325 = 42% sont des greps qui auraient pu être des Grep natif. Pas de violation LOI-OP explicite, mais pattern de sur-utilisation Bash.

### 4. R0 absent dans 3 sessions courtes sur 5

Sessions c4575137 (setup), 3f165a8f (debug Playwright), 71ede1f9 (délégation) : zéro qdrant-find, zéro search_memory.py. Pour 3f165a8f surtout, le sujet "Playwright ARM64" pourrait avoir du contexte mémoire non exploité.

### 5. Credentials en clair dans le JSONL (sécurité)

Conformément au fichier security-jsonl-credentials-leak.md (2026-04-12) :
- 17 occurrences clé n8n_api_[REDACTED]
- 17 JWT tokens
- 31 occurrences PGPASSWORD=[REDACTED]
- 35 références vault_*

Scrubber Plan 10-B1 non implémenté — JSONL non protégé.

---

## Hypothèses sur les causes racines

### H1 — R0 tardif : le skill executing-plans écrase l'ordre LOI-OP

Le skill superpowers:executing-plans démarre avec TaskCreate AVANT que l'agent exécute R0. Le skill est chargé en pos 8, R0 arrive en pos 15-18. **Le skill ne lit pas la LOI-OP avant de démarrer.** Solution : injecter un step R0 explicite dans le prompt d'entrée du skill, ou forcer le hook à bloquer TaskCreate avant /tmp/claude-r0-done.

### H2 — R1 non applicable ici (Caddy ≠ workflow n8n)

La LOI-OP R1 cible "import:workflow / POST /rest/workflows". Le deploy Caddy (08:42) n'est pas un import n8n — l'agent ne viole pas R1. Pour mop-route et mop-get, validate_workflow a eu lieu AVANT le deploy REST API — R1 respecté.

### H3 — R7 à 10:33 : pas d'alias Tailscale pour SCP

Le réflexe IP publique pour SCP (vs SSH) révèle que l'alias Tailscale n'est pas configuré pour le protocole SCP. Le hook détecte mais n'est pas en mode blocking.

### H4 — Hook errors : stdin vide sur appels Bash parallèles

"No stderr output" + Bash annulé = le hook reçoit un stdin vide ou malformé sur les Bash parallélisés. Les 2 annulations à 08:41-08:42 correspondent exactement à des Bash lancés en parallèle (JSONL montre "Cancelled: parallel tool call"). loi-op-enforcer.js n'est pas thread-safe.

### H5 — browser_evaluate workaround : n8n API v1 clé expirée

La clé n8n_api_c9aff... était invalide. Le commit récent fe43d92 ("add feat:apiDisabled to isLicensed exclusion list") suggère que ce problème était connu. L'approche Playwright /rest/ a contourné plutôt que résolu.

---

## Statistiques session principale (eab94b3a)

| Métrique | Valeur | Comparaison 2026-04-11 |
|----------|--------|----------------------|
| Durée | ~2h47 | 11h |
| Bash calls | 325 (44.1%) | 806 (audit ref) |
| MCP calls | 199 (27.0%) | 0 |
| Hook errors | 48 | non mesuré |
| R0 calls (qdrant+search_memory) | 20+ | 0 |
| validate_workflow | 2 | 0 |
| Playwright browser_* | ~140 | non applicable |
| Résultat | Succès E2E | Échec |

Progrès significatif vs audit 2026-04-11 : MCP utilisés, R0 respecté dans l'esprit, résultat obtenu en 2h47 vs 11h.

---

## Recommandations prioritaires

| # | Action | Urgence | Règle |
|---|--------|---------|-------|
| 1 | Corriger loi-op-enforcer.js pour gérer appels Bash parallèles (stdin vide) | Haute | Hook infra |
| 2 | Ajouter step R0 explicite dans skill executing-plans avant tout TaskCreate | Haute | R0 |
| 3 | Documenter browser_evaluate /rest/ comme fallback officiel si /api/v1/ 404, vérifier R10 | Moyenne | R11/R10 |
| 4 | Implémenter scrubber credentials dans session-analyst (Plan 10-B1) | Haute | Sécurité |
| 5 | Configurer SSH alias Tailscale pour SCP aussi, pas seulement SSH | Basse | R7 |
