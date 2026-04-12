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

## Les 12 règles absolues

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

**R1-bis — MCP session TTL : réinitialiser si `Session not found or expired`**

Le serveur n8n-docs maintient une session HTTP en `/tmp/n8n-mcp-session`. Elle expire après quelques minutes d'inactivité (erreur `-32000: Session not found or expired` sur ~80% des appels en session longue).

**Procédure de réinitialisation :**
```bash
TOK=$(grep -A5 '"n8n-docs"' ~/.claude/mcp.json | grep -oP '"N8N_BEARER_TOKEN"\s*:\s*"\K[^"]+' | head -1)
curl -sD /tmp/hdr.txt -X POST http://localhost:3001/mcp \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOK" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"claude-cli","version":"1.0"}}}'
SID=$(grep -i mcp-session-id /tmp/hdr.txt | awk '{print $2}' | tr -d '\r')
echo "New session: $SID"
```

**Fallback Python3** (validation structurelle uniquement — ne remplace **pas** R1) :
```python
import json
d = json.load(open('scripts/n8n-workflows/<workflow>.json'))
nodes = {n['name'] for n in d['nodes']}
conns = set(d['connections'].keys())
missing = conns - nodes  # doit être vide
```

**Cause mesurée :** REX 2026-04-11 P6 + REX 2026-04-12 P5 (~80% d'échec en session longue).

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
4. Deploy via REST API (R11 — méthode primaire) OU CLI fallback :
   CLI: n8n import:workflow --input=/tmp/<file>.json
        n8n publish:workflow --id=<id>   ← met à jour workflow_history (R10)
5. Double restart n8n (pré-import + post-activate) pour flusher le cache runtime
6. Vérifier workflow_entity.nodes ET workflow_history.nodes en DB correspondent au JSON
```

**Interdit :**
- Ouvrir l'éditeur visuel n8n → cliquer → sauver (cause P3 "nœud fantôme Render & Load")
- `n8n update:workflow` sans restart derrière (cache non flushé, warning CLI explicite)
- `n8n update:workflow --active=true` : déprécié depuis n8n 1.x — utiliser `publish:workflow`

**R3-bis — `n8n import:workflow` strip les champs non-standard**

La CLI `n8n import:workflow` supprime silencieusement les champs non-standard des nodes JSON : `webhookId`, `onError`, etc. Pour ces champs critiques, utiliser SQL direct sur **deux tables simultanément** :

```bash
# Extraire nodes depuis le JSON source
python3 -c "import json; nodes=json.load(open('scripts/n8n-workflows/<wf>.json'))['nodes']; json.dump(nodes, open('/tmp/nodes.json','w'))"

# Appliquer aux deux tables (workflow_entity = draft, workflow_history = version active)
docker exec -i -e PGPASSWORD=<vault> javisi_postgresql psql -U n8n -d n8n <<SQL
UPDATE workflow_entity SET nodes = \$wfnodes\$$(cat /tmp/nodes.json)\$wfnodes\$::json WHERE id = '<workflow_id>';
UPDATE workflow_history SET nodes = \$wfnodes\$$(cat /tmp/nodes.json)\$wfnodes\$::json WHERE "versionId" = '<activeVersionId>';
SQL
```

**Cause mesurée :** REX 2026-04-12b section F — `webhookId` supprimé → path corrompu `workflowId/webhook/path`.

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

### R9 — IF node v2 : utiliser typeVersion 1 (bug n8n 2.7.3)

**Déclencheur :** écriture ou révision d'un workflow n8n contenant des nœuds `n8n-nodes-base.if`.

**Bug systémique n8n 2.7.3 :** `filter-parameter.js` ligne 198 — `const ignoreCase = !filterOptions.caseSensitive` crashe quand `filterOptions` est `undefined`. Affecte **toutes** les conditions (boolean ET string) dans les IF nodes `typeVersion: 2`.

**Règle :** utiliser `typeVersion: 1` avec le schéma `fixedCollection` jusqu'à montée en version n8n.

**Schémas IF v1 corrects :**
```json
{
  "type": "n8n-nodes-base.if",
  "typeVersion": 1,
  "parameters": {
    "conditions": {
      "boolean": [{ "value1": "={{ $json.ok }}", "operation": "equal", "value2": true }],
      "string":  [{ "value1": "={{ $json.status }}", "operation": "isNotEmpty" }]
    }
  }
}
```

**Détection rapide dans un workflow existant :**
```bash
python3 -c "
import json, sys
d = json.load(open('scripts/n8n-workflows/<wf>.json'))
bad = [n['name'] for n in d['nodes'] if n.get('type')=='n8n-nodes-base.if' and n.get('typeVersion',1)>=2]
print('IF v2 nodes:', bad if bad else 'aucun')
"
```

**Cause mesurée :** REX 2026-04-12b — 4 nodes corrigés `typeVersion 2→1`, commit `527f0e4`.

---

### R10 — `workflow_history` est la source de vérité d'exécution n8n

**Architecture interne n8n :**

| Table | Rôle | Mis à jour par |
|---|---|---|
| `workflow_entity` | Draft (UI + CLI) | `import:workflow`, sauvegarde UI |
| `workflow_history[activeVersionId]` | **Version exécutée** | `publish:workflow`, REST API PUT |

n8n exécute depuis `workflow_history[activeVersionId].nodes`. Si `workflow_history` n'est pas mis à jour, les anciens nodes s'exécutent même si `workflow_entity` est correct.

**Règle :** tout déploiement doit garantir la cohérence des deux tables. Après `import:workflow` CLI, toujours enchaîner avec `n8n publish:workflow --id=<id>` (dépréciation de `update:workflow --active=true`).

**Vérification en DB :**
```bash
docker exec -i -e PGPASSWORD=<vault> javisi_postgresql psql -U n8n -d n8n -c \
  "SELECT we.id, we.name, wh.\"versionId\", wh.\"createdAt\"
   FROM workflow_entity we
   LEFT JOIN workflow_history wh ON wh.\"workflowId\"::text = we.id::text
   WHERE we.id = '<workflow_id>'
   ORDER BY wh.\"createdAt\" DESC LIMIT 3;"
```

**Cause mesurée :** REX 2026-04-11 P11 + REX 2026-04-12b section 3.

---

### R11 — REST API PUT comme méthode primaire de déploiement

**Prérequis bloquant :** Caddy doit router `/api/v1/*` → `javisi_n8n:5678`. Sans cette règle Caddyfile, tous les appels `PUT /api/v1/workflows/:id` retournent HTTP 404.

**Directive Caddyfile à ajouter si absente :**
```caddy
handle /api/v1/* {
    reverse_proxy javisi_n8n:5678
}
```

**Vérification préflight :**
```bash
curl -sf -H "X-N8N-API-KEY: $N8N_API_KEY" \
  https://mayi.ewutelo.cloud/api/v1/workflows \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK — {len(d[\"data\"])} workflows')"
# HTTP 404 = Caddy ne route pas /api/v1/ → déployer le patch Caddy avant toute chose
```

**Déploiement workflow via REST API (méthode primaire R3 step 4) :**
```bash
WF_ID=$(python3 -c "import json; print(json.load(open('scripts/n8n-workflows/$WF_FILE'))['id'])")
# PUT — met à jour nodes, connections, settings (entity + history simultanément)
curl -sS -X PUT "https://mayi.ewutelo.cloud/api/v1/workflows/$WF_ID" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d @scripts/n8n-workflows/$WF_FILE
# Activer
curl -sS -X POST "https://mayi.ewutelo.cloud/api/v1/workflows/$WF_ID/activate" \
  -H "X-N8N-API-KEY: $N8N_API_KEY"
```

**Avantage vs CLI :** `PUT /api/v1/workflows/:id` met à jour TOUS les stores internes (entity + history) et préserve les champs non-standard (`webhookId`, `onError`) — contrairement à `import:workflow` (voir R3-bis).

**Fallback si 404 (Caddy non patché) :** utiliser `scripts/deploy-workflow.sh` (détecte le 404 + affiche directive Caddy), ou procédure CLI R10.

**Cause mesurée :** REX 2026-04-12b section C — HTTP 404 depuis waza, depuis serveur, depuis container.

---

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

- `docs/audits/2026-04-11-mop-generator-execution-audit.md` — audit source (806 Bash, 0 MCP)
- `docs/rex/REX-SESSION-2026-04-11.md` — 10 problèmes P1→P10 (MCP rate-limit, session TTL, ghost workflow, publish:workflow)
- `docs/rex/REX-SESSION-2026-04-12.md` — P1→P9 (binary filesystem-v2, Gotenberg, LiteLLM clés isolées)
- `docs/rex/REX-SESSION-2026-04-12b.md` — IF v2 bug root cause, workflow_history source of vérité, REST API 404 Caddy
- `docs/superpowers/plans/2026-04-11-mop-workflow-n8n-multistep.md` — plan focalisé qui applique déjà R1-R8
- `~/.claude/hooks/loi-op-enforcer.js` — hook qui injecte des rappels automatiques (R0-R11)
- `scripts/deploy-workflow.sh` — script de déploiement REST API (R11)
