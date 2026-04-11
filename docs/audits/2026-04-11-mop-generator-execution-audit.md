# RAPPORT D'AUDIT — Projet MOP Generator

**Période analysée :** 2026-04-10 → 2026-04-11
**Règle :** uniquement des données mesurées (NE SUPPOSE PAS)
**Auteur :** Claude Code (session post-debug)

---

## 1. Chronologie

| Phase | Session | Début (UTC) | Fin | Durée | Sortie |
|---|---|---|---|---|---|
| Brainstorm + spec | `33a6d711` | 2026-04-10 ~20:00 | 2026-04-11 04:31 | ~8h | Spec + plan parent (commit `34fc314`) |
| Déploiement infra n8n/Gotenberg | `26aed3d9` | 2026-04-11 04:31 | ~00:30 | ~6h | Webhook sibling `mop-render` fonctionnel (7 PDFs générés) |
| **Debug workflow form multi-step** | `840f3397` | 2026-04-11 **00:35** | **11:41** | **~11h05** | Échec E2E, "tu tournes en rond" |
| Audit + replanification | session courante | 2026-04-11 12:00 | 13:34 | ~1h30 | Plan focalisé `2026-04-11-mop-workflow-n8n-multistep.md` (`5004699`) + workflow JSON (`292d415`) |

**31 commits sur le 2026-04-11** entre 04:31 et 13:34. Le projet n'est pas terminé : E2E multi-step jamais validé en prod.

---

## 2. Métriques d'outils — Session debug `840f3397` (11h)

| Outil | Appels |
|---|---|
| Bash | **806** |
| Read | 125 |
| Edit | 96 |
| Write | 32 |
| Agent (general-purpose uniquement) | 23 |
| ToolSearch | 16 |
| Skill | 4 |
| **MCP (tous serveurs confondus)** | **0** |
| Auto-compacts | **23** |
| Erreurs outils | 54 (32 exit_1, 12 exit_2, 6 autres, 3 no_file, 1 conn_refused) |
| Messages assistant | 1934 |
| Messages utilisateur | 63 |

**Comparaison session `26aed3d9` (déploiement qui a marché) :** 396 Bash + **17 `mcp__n8n-docs__get_node`**. La session qui a réussi a utilisé le MCP ; celle qui s'est enlisée non.

**Skills invoquées toutes sessions confondues :** brainstorming ×18, writing-plans ×13, subagent-driven-development ×7, gsd:plan-phase ×4, **systematic-debugging ×1**, verification-before-completion ×0.

---

## 3. Erreurs & pièges rencontrés

### Problèmes techniques (REX-SESSION-2026-04-11, P1→P10)

| # | Symptôme | Cause racine mesurée |
|---|---|---|
| P1 | E2E simulateur ne finalisait jamais le form | Protocole HTTP multi-step mal lu — `responseMode=onReceived` impose polling côté client ; script ne gérait pas `form-waiting` comme état terminal sur le dernier POST |
| P2 | `Done (PDF)` → "No binary data with field data found" | Mismatch `dataPropertyName` ↔ `inputDataFieldName` |
| P3 | Nœud fantôme "Render & Load" dans `execution_data` | Édition UI → cache runtime divergeait de `workflow_entity.nodes` |
| P4 | Devinette du nom d'outil MCP | `validate_workflow` existait mais n'a pas été cherché via `tools_documentation` |
| P5 | Rate-limit MCP après bursts | Pas de pacing |
| P6 | Session MCP expirée | TTL non respecté |
| P7 | Ciblage `localhost:5678` au lieu de `mayi.ewutelo.cloud` | Port 5678 bindé `127.0.0.1`, pas sur Tailscale |
| P8 | IP publique au lieu de Tailscale | Violation règle standing |
| P9 | `$CP5gJrn1e2zZbPxh` expansé en shell | Heredoc non quoté |
| P10 | Research doc incomplète | Manquait : protocole HTTP, `field-N` naming, `responseMode=onReceived` |

### Erreurs d'approche (mesurables dans le transcript)

1. **0 appel MCP en 11h** alors que `n8n-docs` (v2.40.5) était up à `http://localhost:3001/mcp` avec `validate_workflow` annoté *"Essential before deploy"*.
2. **806 Bash + 125 Read** au lieu de déléguer à des subagents → 23 auto-compacts (perte de contexte répétée).
3. **23 Agents `general-purpose`** — aucun `Explore`, `Plan`, ou spécialisé.
4. **`systematic-debugging` invoqué 1 seule fois** en 11h de debug.
5. **Édition UI workflow** alors que la règle file-first était établie.
6. **Pas de test du webhook sibling (`mop-render`) avant** de coder le form multi-step — le sibling marchait déjà (7 PDFs en `/data/mop/pdf/`).

### Citation utilisateur (09:34:24)

> *"tu tournes en rond, utllise les skill n8n et planifie avant de coder. Ce que j'aurais dû faire dès le départ (et que tu m'as demandé) : Lire Form.node.js / FormTrigger.node.js / Code.node.js dans le conteneur AVANT d'écrire le JSON."*

---

## 4. Inventaire skills & MCPs disponibles (mesuré)

### Superpowers 5.0.4 — skills pertinentes non-utilisées en debug

- `systematic-debugging` — utilisée 1× / 11h
- `verification-before-completion` — **jamais utilisée**
- `test-driven-development` — jamais invoquée sur le workflow
- `subagent-driven-development` — utilisée en brainstorm/plan, pas en debug
- `dispatching-parallel-agents` — jamais utilisée

### MCP servers actifs (confirmés via config + connexion)

| MCP | Outils clés | Utilisation mesurée en debug |
|---|---|---|
| **n8n-docs** (v2.40.5, localhost:3001) | `validate_workflow` *"Essential before deploy"*, `validate_node`, `get_node`, `search_nodes`, `search_templates`, `tools_documentation` | **0 call** |
| **sequential-thinking** | `sequentialthinking` | 0 |
| **playwright** | `browser_navigate`, `browser_fill_form`, `browser_snapshot`, `browser_network_requests` | 0 (243 calls dans d'autres sessions) |
| **qdrant** | `qdrant-find`, `qdrant-store` | 0 |
| **docker** | `deploy-compose`, `get-logs`, `list-containers` | 0 (tout fait via `docker exec` en Bash) |
| context7, comfyui-studio, canva-connect, plane, remotion-documentation, stitch, rough-cut | — | N/A |

### Mémoire AI persistante (`memory_v1` via `search_memory.py`)

Inventoriée mais **jamais interrogée en debug** pour chercher des patterns n8n similaires passés.

---

## 5. Recette optimale pour rerun from zero

**Hypothèse :** même PRD (MOP generator form multi-step → Gotenberg PDF), même infra existante.

### Phase 0 — Préparation (15 min)

1. `search_memory.py --query "n8n form multi-step binary PDF" --limit 10` — capitaliser l'historique.
2. **Invoquer `n8n-docs` MCP `tools_documentation`** pour lister les outils exacts (évite P4).
3. Lire `docs/REX-SESSION-2026-04-11.md` P1→P10.

### Phase 1 — Recherche docs-first (30 min, 1 subagent `Explore`)

Subagent `Explore` "very thorough" avec mission précise :
- Extraire `formCompletion.respondWith=returnBinary` contract dans `n8n-nodes-base/nodes/Form/Form.node.ts`
- Extraire `readWriteFile.dataPropertyName` chain
- Extraire comportement `responseMode=onReceived` (FormTrigger)
- Extraire protocole HTTP multi-step (form-waiting/success/error polling)

Output : `docs/research/n8n-form-binary-contract.md`. **Pas de code avant ce doc.**

### Phase 2 — Écriture JSON canonique (20 min)

1. Écrire `scripts/n8n-workflows/mop-generator-v1.json` (file-first, pas de UI).
2. **Appeler `mcp__n8n-docs__validate_workflow`** sur le fichier. Zero erreur = prêt.
3. Commit.

### Phase 3 — Deploy propre (10 min)

Script `deploy-mop-generator.sh` :
```
wipe executions → restart n8n → n8n import:workflow CLI → activate → restart n8n (2e fois) → verify workflow_entity + webhook_entity
```
Pas d'édition UI. Jamais.

### Phase 4 — E2E via Playwright MCP (15 min)

**Au lieu d'un script `node` custom** (source de P1) : `mcp__playwright__browser_navigate` → `browser_fill_form` → `browser_click` page par page → `browser_snapshot` final → vérifier PDF téléchargé. Le navigateur gère `form-waiting` / polling nativement — le bug d'état terminal disparaît.

### Phase 5 — Branche erreur (10 min)

`mcp__docker__get-logs` sur `javisi_gotenberg` en live + `docker stop javisi_gotenberg` → rerun E2E → vérifier `lastNodeExecuted=Done (Error)` → `docker start`.

### Phase 6 — REX + capitalisation (10 min)

Append `docs/REX-*.md` + `qdrant-store` des patterns validés.

**Total estimé : ~1h50 vs ~11h mesurées.** Gain : ~9h10 (facteur 6).

### Règles absolues dérivées des données mesurées

1. **`validate_workflow` MCP AVANT tout `import:workflow`.** Non négociable.
2. **Playwright MCP pour tout E2E form web**, jamais `curl`/`node` fait main.
3. **File-first total** — interdiction d'éditer dans l'UI n8n tant que le plan est en cours (cause directe de P3).
4. **Tester le sibling existant en premier** (`mop-render` était fonctionnel) — validation fondation avant construction.
5. **Déléguer les investigations > 5 min à un subagent** avec contexte focalisé — évite les 23 auto-compacts.
6. **`systematic-debugging` dès le premier symptôme inexpliqué**, pas après 3h de thrashing.
7. **`sequential-thinking` MCP** pour toute hypothèse de root cause multi-couches (shell → workflow → execution_data → cache n8n).
8. **Tailscale only** — ajouter en préflight : `dig mayi.ewutelo.cloud` doit renvoyer `100.64.0.14`.

---

## 6. Métriques résumé

| Dimension | Mesuré | Cible rerun |
|---|---|---|
| Durée debug | ~11h | ~1h50 |
| Bash calls | 806 | < 100 |
| MCP calls | 0 | ≥ 15 (validate_workflow + playwright E2E + sequential-thinking) |
| Auto-compacts | 23 | 0-2 |
| Éditions UI n8n | ≥ 4 | 0 |
| Erreurs outils | 54 | < 10 |
| Problèmes REX | 10 (P1-P10) | 0 |

---

## Conclusion

La cause racine unique et mesurable est **la non-utilisation des MCP disponibles** (`n8n-docs.validate_workflow`, `playwright.browser_*`, `sequential-thinking`). Les 10 problèmes P1→P10 du REX sont tous des symptômes dérivés de ce choix initial : coder avant valider, scripter avant browser-automatiser, deviner avant interroger la doc live. Le rerun optimal n'est pas une question de nouvelle compétence — c'est l'application stricte d'outils déjà installés et documentés sur ce poste.
