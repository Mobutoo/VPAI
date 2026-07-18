# RUNBOOK — Autoring n8n (boucle build → validate → deploy → verify → LEARN)

**Statut** : livrable 3, `.planning/quick/260718-a-harness-autoring-n8n/SPEC.md`.
**Portée** : doctrine d'usage pour agents qui écrivent/modifient un workflow n8n
dans ce repo. Court, actionnable — pour le détail des pièges, voir
`docs/runbooks/GOTCHAS-N8N-2.30.md` (source unique, citée à chaque étape ci-dessous).

---

## 0. Avant tout — mémoire (R0)

`mcp__qdrant__qdrant-find` sur le sujet (nom du workflow, node concerné, symptôme).
Puis lire `docs/runbooks/GOTCHAS-N8N-2.30.md` en entier — c'est plus rapide qu'une
recherche ad hoc et c'est la fiche curée pour exactement ce but.

## 1. Build — MCP natif d'abord, ordre exact

Le MCP natif de l'instance (`mcp__n8n-native__*`, activé depuis 2.30.7 Community,
cf `RUNBOOK-N8N-UPGRADE-SIDECAR.md` §6) est l'**autorité de schéma** — il reflète
l'instance réelle, pas une doc statique potentiellement désynchronisée.

1. `get_sdk_reference` — OBLIGATOIRE avant d'écrire du code SDK. Ne jamais deviner
   la syntaxe `workflow()`/`.add()`/`.to()`/`expr()`.
2. `search_nodes` avec une requête par service/trigger/utilitaire nécessaire
   (ex. `["schedule trigger", "code", "if"]`) — récupère les discriminateurs
   (resource/operation/mode).
3. `get_node_types` avec TOUS les node IDs prévus (+ discriminateurs de l'étape 2)
   — types TypeScript exacts, ne jamais deviner un nom de paramètre.
4. Si un paramètre a une annotation `@searchListMethod`/`@loadOptionsMethod`
   (sélecteurs de credential/canal/etc.) : `explore_node_resources` avec un
   `credentialId` réel via `list_credentials` — ne jamais inventer un ID.
5. Écrire le workflow **file-first** dans `scripts/n8n-workflows/<nom>.json`
   (jamais d'édition UI — R3). Si le SDK code-first est utilisé, `validate_workflow`
   (MCP natif) avant toute création.
6. `mcp__n8n-native__create_workflow_from_code` — **écrit sur l'instance**. Hors
   scope de ce chantier de vérifier cet outil (non appelé — voir note MCP
   ci-dessous). Si utilisé en usage normal : uniquement après (5), jamais en
   contournement du file-first JSON pour un workflow déjà existant en repo.

**Note MCP (vérifié ce chantier, 2026-07-18)** : `get_sdk_reference`, `search_nodes`,
`get_node_types` et `validate_workflow` répondent (read-only, appels de vérification
faits). `get_workflow_details`/`search_executions`/`get_workflow_history` exigent
que le workflow ait le toggle **« MCP access »** activé côté UI (sinon erreur
`Workflow is not available in MCP`) — `search_workflows` (listing) fonctionne sans
ce toggle. Ne pas assumer l'introspection MCP disponible sur un workflow existant
sans l'avoir vérifié.

## 2. Fallback CLI si MCP indisponible (R1-bis)

Session MCP expirée (`-32000`) ou MCP natif injoignable → ne PAS bloquer :

```bash
scripts/n8n-validate-fallback.sh scripts/n8n-workflows/<nom>.json
```

Autorité structurelle (Python : nodes dupliqués, connexions orphelines, détection
IF v2 — NOTE jamais FAIL). Sentinel `[N8N-VALIDATE-CLI] PASS` sur succès. Sur
échec : capture automatique dans `docs/rex/REX-N8N-AUTORING.md` (voir §4).

## 3. Deploy — REST API primaire (R11)

```bash
N8N_API_KEY=<clé> scripts/deploy-workflow.sh scripts/n8n-workflows/<nom>.json [--id <id>]
```

Séquence interne (ne pas réimplémenter à la main) : validate fallback → preflight
GET `/api/v1/workflows` (détecte 404 Caddy) → PUT `/api/v1/workflows/:id` (entity +
history simultanément, R10) → POST `/activate` → vérification finale `active`.

**Sur tout échec de PUT, même HTTP 400** : relire `activeVersionId` avant de
retenter — le PUT n'est pas garanti atomique sur 2.30.7 (`GOTCHAS-N8N-2.30.md` §3).
Le script affiche cet avertissement et capture l'échec en REX automatiquement.

Désactiver un workflow (collision webhook, neutralisation) : `POST
/api/v1/workflows/:id/deactivate` explicitement — jamais un PUT partiel ni un SQL
`active=false` seul (`GOTCHAS-N8N-2.30.md` §2).

## 4. Sur tout échec (validate/deploy/verify) — capture REX automatique

`scripts/deploy-workflow.sh` et `scripts/n8n-validate-fallback.sh` appellent
`scripts/n8n-authoring/rex-capture.sh` sur chacun de leurs points de sortie en
échec — append daté dans `docs/rex/REX-N8N-AUTORING.md` (workflow, étape, erreur
brute, correction si connue). Best-effort : n'affecte jamais le code de sortie.
Opt-out ponctuel : `REX_CAPTURE=0`.

## 5. Verify — exécution réelle

Après deploy, déclencher une exécution réelle (webhook `curl`/Playwright selon R2,
ou trigger manuel) et vérifier le statut `success` — ne jamais conclure "déployé"
sur un simple HTTP 200 de PUT. Pour un workflow à trigger périodique (cron), une
lecture de `execution_entity` (read-only, via SSH+psql documenté dans
`RUNBOOK-N8N-UPGRADE-SIDECAR.md` §2.3, ou `mcp__postgres__*` si connecté) permet de
confirmer la dernière exécution réelle sans en déclencher une nouvelle.

## 6. LEARN

Toute découverte non déjà couverte par `GOTCHAS-N8N-2.30.md` → l'y ajouter (avec
citation de source) avant de clore la tâche. `docs/rex/REX-N8N-AUTORING.md` capture
déjà les échecs bruts automatiquement (§4) ; GOTCHAS reste la fiche **curée**
(synthèse humaine/agent, pas un journal brut).

---

## Statut de validation de ce harness

Preuve E2E (livrable 5, 2026-07-18) : redeploy no-op de `memory-healthcheck`
(id `NZZ9Ke6DXJTlkasa`) via `deploy-workflow.sh` — contenu local confirmé identique
au live avant exécution (idempotence), harness exercé de bout en bout. Détail et
écarts : voir rapport de session (référence `.planning/quick/260718-a-harness-autoring-n8n/SPEC.md`).
Échec simulé (fixture cassée `tests/fixtures/`) → entrée automatique confirmée dans
`docs/rex/REX-N8N-AUTORING.md`.

## Références

- `docs/runbooks/GOTCHAS-N8N-2.30.md` — fiche curée (livrable 1)
- `scripts/n8n-authoring/rex-capture.sh` — capture REX automatique (livrable 2)
- `scripts/n8n-validate-fallback.sh`, `scripts/deploy-workflow.sh` — harness existant (Lane 3, non réécrit)
- `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` — R0-R11
- `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md` §6, §8 — MCP natif, R9
