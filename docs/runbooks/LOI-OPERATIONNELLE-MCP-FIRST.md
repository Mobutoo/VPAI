# LOI OPÉRATIONNELLE — MCP-first, file-first, doc-first

> **Origine :** `docs/audits/2026-04-11-mop-generator-execution-audit.md`
> **Statut :** NON-NÉGOCIABLE — prévaut sur les comportements par défaut des skills Superpowers quand elles s'appliquent. Seules les instructions explicites de l'utilisateur ont une priorité supérieure.
> **Applicabilité :** tout travail touchant n8n, webhook, E2E web, workflow JSON, debug multi-couches.

## Pourquoi cette loi existe

**Mesuré le 2026-04-11** sur une session debug de 11h05 du projet MOP generator :

| Métrique | Valeur |
|---|---|
| Durée | ~11h |
| Bash calls | 806 |
| MCP calls | **0** |
| Auto-compacts | 23 |
| Erreurs outils | 54 |
| Problèmes REX | 10 (P1→P10) |
| `systematic-debugging` invoqué | 1× |

Pendant ces 11h, `mcp__n8n-docs__validate_workflow` (annoté *"Essential before deploy"*) était **actif à `http://localhost:3001/mcp`** et n'a jamais été appelé. La session précédente (`26aed3d9`, qui a réussi) avait fait **17 appels MCP**. Conclusion : la non-utilisation des MCP disponibles est la cause racine unique et mesurable de l'échec.

## Les 9 règles absolues

### R0 — Memory search first (Qdrant `memory_v1`)

**Déclencheurs :**
- Démarrage d'une tâche sur un sujet potentiellement déjà rencontré (n8n, webhook, form, Gotenberg, Caddy VPN, LiteLLM, OpenClaw, Kitsu, PostgreSQL shared password, etc.)
- Avant d'écrire un plan, une spec, ou un script non-trivial
- Avant d'invoquer `Explore` / `WebSearch` sur un sujet technique du projet

**Action obligatoire — DEUX voies en parallèle :**

```bash
# Voie A — search_memory.py (worker indexé, source de vérité REX markdown)
set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
/opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/search_memory.py \
  --config /opt/workstation/configs/ai-memory-worker/config.yml \
  --query "<question en langage naturel>" --limit 5
# Filtres: --repo, --doc-kind, --topic
```

Et/ou :

```
mcp__qdrant__qdrant-find avec query = "<description du probleme>"
→ collection par defaut = memory_v1
→ retourne les chunks les plus pertinents + path du doc source
```

**Règle de citation :** si la mémoire retourne un résultat pertinent, citer le **chemin du fichier source** dans la réponse/plan (ex: *"selon `docs/REX-SESSION-2026-04-11.md` P3, éviter..."*). Ne pas inventer si la mémoire ne sait pas — dire "pas trouvé" est plus utile qu'une réponse fabulée (cf. `docs/runbooks/AI-MEMORY-AGENT-PROTOCOL.md`).

**Interdit :**
- Écrire "je pense que…" ou "historiquement on…" sans vérifier la mémoire d'abord
- Relancer un Research subagent sans avoir d'abord interrogé `memory_v1`
- Exploiter un souvenir de session précédente sans le re-vérifier (la mémoire peut être stale)

**Raison mesurée :** la session debug 840f3397 n'a JAMAIS interrogé `memory_v1` malgré la présence de REX et patterns n8n indexés. La mémoire aurait pu remonter `docs/TROUBLESHOOTING.md` section n8n, ou des patterns de workflow similaires déjà debuggés.

### R1 — MCP validate_workflow AVANT tout import n8n

**Déclencheurs :**
- Écriture/édition d'un fichier `scripts/n8n-workflows/*.json`
- Bash `n8n import:workflow`, `n8n update:workflow`, `docker cp *.json javisi_n8n:*`
- POST vers `/rest/workflows` de l'API n8n

**Action obligatoire :**
```
mcp__n8n-docs__validate_workflow avec le contenu du JSON complet
→ zéro erreur bloquante = prêt à importer
→ erreurs = corriger avant import (jamais "je verrai bien")
```

**Si le validateur remonte un champ inconnu** : `mcp__n8n-docs__get_node` + `mcp__n8n-docs__validate_node` pour chaque nœud suspect.

### R2 — Playwright MCP pour tout E2E web

**Déclencheurs :**
- Test d'un form n8n multi-step (path `/form/*`)
- Test d'une completion retournant un binary (PDF, image)
- Toute séquence "naviguer → remplir → soumettre → vérifier téléchargement"

**Action obligatoire :**
```
mcp__playwright__browser_navigate → browser_fill_form → browser_click (page par page)
→ browser_snapshot + browser_network_requests pour vérifier états
→ JAMAIS curl/node custom pour un flux form multi-step (cause P1 audit)
```

**Raison technique mesurée :** n8n Form v2.5 utilise `responseMode=onReceived` + polling `/form-waiting/X` côté client. Le navigateur Playwright gère ce protocole nativement. Un script `node`/`curl` doit reproduire manuellement le state machine et le rater est inévitable (P1 du REX).

### R3 — File-first absolu, zéro édition UI

**Déclencheurs :**
- Modification d'un workflow n8n existant
- Ajout/suppression de nœuds

**Action obligatoire :**
```
1. Éditer le JSON canonique dans scripts/n8n-workflows/
2. mcp__n8n-docs__validate_workflow
3. git commit
4. deploy via CLI : n8n import:workflow --input=/tmp/<file>.json
5. Double restart n8n (pré-import + post-activate) pour flusher le cache runtime
6. Vérifier workflow_entity.nodes en DB correspond au JSON
```

**Interdit :**
- Ouvrir l'éditeur visuel n8n → cliquer → sauver (cause P3 "nœud fantôme Render & Load")
- `n8n update:workflow` sans restart derrière (cache non flushé, warning CLI explicite)

### R4 — Sibling test first

**Règle :** avant de construire une chaîne qui dépend d'un service, valider que le service répond **avec une mesure reproductible**.

**Exemple MOP :** le webhook `mop-render` avait déjà généré 7 PDFs (`/data/mop/pdf/MOP-2026-000{1..7}.pdf`) avant que le form multi-step ne soit commencé. Le tester en isolation (curl avec JSON fixture) aurait pris 30s et évité 3h de debug "où est le PDF".

```bash
# Pattern canonique
curl -sS -X POST https://mayi.ewutelo.cloud/webhook/<sibling> \
  -H 'Content-Type: application/json' \
  -d @tests/fixtures/sample.json
# → vérifier code HTTP + payload + artefact disque/DB
```

### R5 — `systematic-debugging` au 1er symptôme inexpliqué

**Déclencheur :** une erreur dont la cause racine n'est pas identifiée sous 2 tentatives de fix.

**Action :** invoquer `superpowers:systematic-debugging` immédiatement. Pas après 3h de trial-and-error.

**Phases obligatoires avant tout fix (Phase 1 du skill) :**
1. Reproduire fiablement
2. Lire l'erreur complète (stack trace entière)
3. Tracer le data flow backward jusqu'à la source
4. Ajouter de l'instrumentation aux boundaries inter-composants
5. Identifier le composant qui échoue AVANT de toucher du code

**Règle des 3 fixes :** si 3 hypothèses successives ont échoué, l'architecture est probablement fausse. STOP. Discussion utilisateur avant fix #4.

### R6 — Subagent delegation > 5 min investigations

**Déclencheur :** toute investigation qui nécessite >5 lectures de fichiers ou >10 calls Bash.

**Action :** dispatcher un subagent `Explore` (thorough) ou `Plan` avec un prompt auto-suffisant. Lui renvoyer les **chemins**, pas le contenu. Lui demander un rapport < 500 mots.

**Raison mesurée :** la session debug 840f3397 a subi **23 auto-compacts** à cause d'un contexte principal gonflé par 806 Bash + 125 Read. Chaque compact = perte de raisonnement intermédiaire = relance de fils déjà explorés.

### R7 — Tailscale only (jamais IP publique)

**Préflight obligatoire pour tout accès Sese-AI :**

```bash
dig +short mayi.ewutelo.cloud     # doit retourner 100.64.0.14
tailscale ip -4                    # doit retourner une IP 100.64.0.x
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 'hostname'  # doit répondre 'sese'
```

**Interdit :**
- `ssh mobuone@137.74.114.167` (IP publique, violation P8)
- `curl https://mayi.ewutelo.cloud` sans vérifier que la résolution DNS passe par Tailscale
- `localhost:5678` pour n8n depuis waza (port bindé `127.0.0.1` dans Docker, inaccessible via Tailscale — cause P7)

### R8 — Doc-first, preuve > souvenir

**Règle :** avant d'écrire du code qui utilise une feature d'un outil tiers (n8n node, API, CLI), fournir la preuve de son comportement :
- Soit un extrait de la doc officielle citée
- Soit un extrait du code source (Form.node.ts, etc.)
- Soit une sortie de commande reproduite
- Soit un appel MCP `get_node` / `tools_documentation`

**Citation utilisateur mesurée (09:34:24 le 2026-04-11) :**
> *"tu tournes en rond, utllise les skill n8n et planifie avant de coder. Ce que j'aurais dû faire dès le départ (et que tu m'as demandé) : Lire Form.node.js / FormTrigger.node.js / Code.node.js dans le conteneur AVANT d'écrire le JSON."*

## Priorité par rapport aux skills Superpowers

Les skills Superpowers (brainstorming, writing-plans, TDD, etc.) restent les workflows par défaut. Cette LOI **les complète** en imposant :

| Cas | Skill Superpowers | LOI OP ajoute |
|---|---|---|
| Écriture plan n8n | `writing-plans` | Dans chaque tâche "deploy", mentionner explicitement `mcp__n8n-docs__validate_workflow` comme step |
| Debug workflow | `systematic-debugging` | Phase 1 step 4 : TOUJOURS passer par MCP n8n-docs avant de suspecter le code |
| E2E test d'un form | `test-driven-development` | Test = appel Playwright MCP, pas script `curl` fait main |
| Research | `Explore` subagent | Inclure explicitement une lecture du REX 2026-04-11 + inventaire MCP dispo |

**Conflit :** si un skill dit "écris du code d'abord" et la LOI OP dit "valide via MCP d'abord", **la LOI OP prévaut**. Seule une instruction explicite de l'utilisateur ("ignore la LOI OP pour cette tâche") peut lever la contrainte.

## Checklist MCP disponibles (vérifié 2026-04-11)

| MCP | Statut | Outils clés |
|---|---|---|
| `n8n-docs` | ✓ localhost:3001 | `validate_workflow`, `validate_node`, `get_node`, `search_nodes`, `search_templates`, `tools_documentation` |
| `playwright` | ✓ headless chromium | `browser_navigate`, `browser_fill_form`, `browser_click`, `browser_snapshot`, `browser_network_requests`, `browser_take_screenshot` |
| `sequential-thinking` | ✓ | `sequentialthinking` (pour hypothèses root cause multi-couches) |
| `qdrant` | ✓ qd.ewutelo.cloud | `qdrant-find` (interroger `memory_v1`), `qdrant-store` |
| `docker` | ✓ | `list-containers`, `get-logs`, `deploy-compose` |
| `context7` | ✓ | `resolve-library-id`, `get-library-docs` (docs npm/frameworks live) |

## Références

- `docs/audits/2026-04-11-mop-generator-execution-audit.md` — audit source
- `docs/REX-SESSION-2026-04-11.md` — 10 problèmes P1→P10 détaillés
- `docs/superpowers/plans/2026-04-11-mop-workflow-n8n-multistep.md` — plan focalisé qui applique déjà R1-R8
- `~/.claude/hooks/loi-op-enforcer.js` — hook qui injecte des rappels automatiques
