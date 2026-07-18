# GOTCHAS — n8n 2.30.7 (fiche curée build-time)

**Statut** : livrable 1, `.planning/quick/260718-a-harness-autoring-n8n/SPEC.md`.
**Usage** : source unique injectée aux agents d'autoring AVANT d'écrire un workflow
n8n. Chaque entrée cite son REX/doc source — ne pas ajouter d'entrée sans preuve
citée (R8, doc-first). Doctrine d'usage de cette fiche : `RUNBOOK-N8N-AUTORING.md`.

---

## 1. IF node v2 (`n8n-nodes-base.if` typeVersion ≥ 2) — R9, scopé

**Règle d'autoring** : ne pas ÉCRIRE de nouveau IF v2 tant que le cas boolean n'est
pas statué (voir ci-dessous). Le **déploiement** de workflows existants contenant
déjà des IF v2 reste toléré (`scripts/deploy-workflow.sh` NOTE, jamais FAIL).

**État précis (2026-07-18)** :
- **Comparaison string avec résolution d'expression sur `options`** (schéma canonique
  `options: { caseSensitive: true, typeValidation: strict }`) : **`fixed`, prouvé**
  sur staging 2.30.7 (workflow `r9-probe`, 2 exécutions réelles 200/403, aucun crash
  `Cannot read properties of undefined (reading 'caseSensitive')`) — source :
  `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md` §8.
- **Comparaison boolean** (`operator: { type: 'boolean', operation: 'true' }`) :
  **non statué formellement** — la procédure de revalidation isolée du runbook §8
  n'a pas été rejouée (pas de staging disponible ce jour, cf `RUNBOOK-N8N-AUTORING.md`
  §Livrable 4). **Corroboration indirecte, pas une preuve substitutive** : le workflow
  prod `memory-healthcheck` (id `NZZ9Ke6DXJTlkasa`) contient un IF v2 boolean exact
  (`Needs Alert?`, `$json.needs_alert === true`, `operator: {type:'boolean',
  operation:'true', singleValue:true}`) et a exécuté avec succès (`status=success`,
  `mode=trigger`) à 12h, 13h, 14h, 17h et 18h le 2026-07-18 sur prod 2.30.7 (vérifié
  read-only via `execution_entity`, session de ce chantier). Ne pas généraliser : une
  absence de crash en usage réel n'équivaut pas à la revalidation isolée exigée par
  le runbook §8 (schéma exact du REX, environnement contrôlé).
- **Cause historique du bug** (n8n 2.7.3) : `filter-parameter.js:198` —
  `const ignoreCase = !filterOptions.caseSensitive` crashe si `filterOptions` est
  `undefined`, sur TOUTES les conditions (boolean et string) — source :
  `docs/rex/REX-SESSION-2026-04-12b.md`.

## 2. `workflow_history[activeVersionId]` = source de vérité d'exécution — R10

n8n exécute depuis `workflow_history[activeVersionId].nodes`, PAS depuis
`workflow_entity.nodes` seul. Toute mise à jour doit garantir la cohérence des deux
tables (`n8n publish:workflow --id=<id>` après `import:workflow` CLI, ou `PUT
/api/v1/workflows/:id` qui met à jour les deux simultanément). Vérification :

```sql
SELECT we.id, we.name, we."activeVersionId", wh."versionId", wh."createdAt"
FROM workflow_entity we
LEFT JOIN workflow_history wh ON wh."workflowId"::text = we.id::text
WHERE we.id = '<workflow_id>' ORDER BY wh."createdAt" DESC LIMIT 3;
```

Source : `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` R10 ; `docs/rex/REX-SESSION-2026-04-12b.md` §3.

**Piège R10 aggravé (staging 2026-07-18)** : neutraliser un workflow par
`UPDATE workflow_entity SET active=false` seul est **contourné** par les migrations
n8n 2.30.7 — l'état publié/actif dérive aussi de `activeVersionId` et des tables de
publication (`CreateWorkflowPublicationOutboxTable`/`TriggerStatusTable`). Un boot
avec `active=false` mais `activeVersionId` non NULL peut réactiver le trigger et
provoquer une exécution réelle (incident staging : fausse alerte Telegram
`hawktrade-killswitch`). Neutralisation correcte : les DEUX colonnes
(`active=false` **ET** `activeVersionId=NULL`) avant tout boot sur des données
sensibles. Source : `docs/rex/REX-N8N-UPGRADE-SIDECAR-2026-07-18.md` §Incident staging.

**Découverte du jour (2026-07-18, déploiement `memory-telegram-bot`)** : désactiver
un workflow en collision webhook doit passer par `POST
/api/v1/workflows/:id/deactivate` — une mise à jour partielle (PUT/PATCH re-save du
contenu) **re-déclenche** l'enregistrement du webhook et donc la collision de path.
`UPDATE ... SET active=false` seul en SQL est également contourné pour la même
raison que ci-dessus (`activeVersionId`).

## 3. `PUT /api/v1/workflows/:id` en échec HTTP n'est PAS garanti atomique

**Découverte du jour (2026-07-18, déploiement `memory-telegram-bot`)** : sur n8n
2.30.7, un `PUT /api/v1/workflows/:id` qui échoue en HTTP 400 à la re-validation de
publication (ex. « Cannot publish… Missing required credential ») peut **committer
quand même le contenu et avancer `activeVersionId`** — l'échec n'est pas
transactionnel côté n8n. **Toujours relire `activeVersionId` + le graphe publié
après un PUT, même en cas d'erreur**, avant de retenter ou de conclure "rien n'a
changé". `scripts/deploy-workflow.sh` affiche désormais cet avertissement sur tout
échec de PUT (livrable 2, ce chantier).

## 4. Node `n8n-nodes-base.ssh` — `authentication` implicite = `password`

**Découverte du jour (2026-07-18, déploiement `memory-telegram-bot`)** : si le
paramètre `authentication` n'est pas explicité sur un node SSH, il défaut à
`password`. Si le credential réellement attaché au node est de type
`sshPrivateKey`, la publication stricte 2.30.7 refuse le déploiement (mismatch
credential/authentication). Toujours expliciter `"authentication": "privateKey"`
dans les `parameters` quand le credential attaché est une clé privée.

## 5. `n8n import:workflow` CLI strip les champs non-standard — R3-bis

`webhookId`, `onError` et autres champs non-standard des nodes sont **supprimés
silencieusement** par `n8n import:workflow`. Conséquence observée : `webhookPath`
corrompu au format `<workflowId>/webhook/<path>` au lieu de `<path>` simple, cause
`webhookId` absent → n8n préfixe avec l'ID du workflow (source :
`docs/rex/REX-SESSION-2026-04-12b.md` §F, §webhookPath corrompu). Pour ces champs
critiques, utiliser SQL direct sur `workflow_entity` **ET** `workflow_history`
simultanément (voir `LOI-OPERATIONNELLE-MCP-FIRST.md` R3-bis pour la procédure
exacte), ou préférer `PUT /api/v1/workflows/:id` (R11) qui préserve ces champs.

**Provisioning Ansible (2026-07-18, tâche C6)** : `roles/n8n-provision/tasks/main.yml`
route désormais automatiquement tout workflow dont le JSON rendu porte un `id`
top-level vers `PUT /api/v1/workflows/:id` + activate (in-container, même méthode
que `scripts/deploy-workflow.sh`), en contournant le CLI `import:workflow` — évite
la régression webhookId sur re-déploiement pour `creative-pipeline`, `plan-dispatch`,
`asset-register` et 7 autres workflows id-bearing détectés dynamiquement. Les
workflows sans `id` gardent le chemin CLI legacy, inchangé.

## 6. Un seul webhook par (path, méthode) — collisions connues en prod

Plusieurs workflows prod partagent aujourd'hui le même path webhook et échouent à
s'activer (« The URL path … is already taken ») : `Instagram Comment Reply`,
`Instagram DM Reply`, `OpenCut Control (Start/Stop)`, `Meta Webhook`/`DM Webhook`.
Point latent pré-existant, pas causé par l'upgrade 2.30.7, observé aussi sur le
staging restauré depuis le dump prod. Avant d'ajouter un nouveau trigger webhook,
vérifier qu'aucun workflow actif ou inactif n'utilise déjà le même `(path,
httpMethod)`. Source : `docs/rex/REX-N8N-UPGRADE-SIDECAR-2026-07-18.md` §Résultat
(« Point latent »).

## 7. Code node — sandbox task runner, `$env`/`process.env` vides

Le Task Runner interne (`N8N_RUNNERS_MODE=internal`) isole le sandbox du Code node
du process principal n8n :
- `$env.<VAR>` retourne `''` même avec `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` (bug
  `envProviderState`).
- `process` n'est pas défini dans le sandbox VM (`ReferenceError: process is not
  defined`).
- `execSync('printenv <VAR>')` retourne aussi `''` — le subprocess Task Runner
  n'hérite PAS des variables d'environnement custom du process principal (PID 1),
  même si `/proc/1/environ` les contient bien.

**Ne PAS utiliser** un Code node pour lire des secrets/config custom via `$env` tant
que ce bug n'est pas contourné. Alternatives documentées : désactiver le task runner
(`N8N_RUNNERS_ENABLED=false`, régression isolation acceptée pour workflows internes)
ou lire `/proc/1/environ` explicitement (hacky, dépend du layout PID du conteneur).
Source : `docs/rex/REX-MOP-TASKRUNNER-2026-04-11.md`.

**Corollaire d'autoring (R8, `n8n-nodes-base.code` via MCP natif)** : le
`get_node_types` du MCP natif documente lui-même le Code node comme « LAST RESORT »
et rappelle qu'il n'a **aucun accès réseau** (`fetch`/`axios`/`require` HTTP
échouent au runtime) — préférer le node HTTP Request natif, jamais d'appel HTTP
dans un Code node (vérifié via `mcp__n8n-native__search_nodes`, ce chantier).

## 8. Save/Publish — méthode primaire de déploiement (R11)

`PUT /api/v1/workflows/:id` (met à jour entity + history simultanément, préserve les
champs non-standard) **puis** `POST /api/v1/workflows/:id/activate` est la méthode
primaire. Prérequis bloquant : Caddy doit router `/api/v1/*` → `javisi_n8n:5678`
(sinon HTTP 404 systématique). Fallback CLI si 404 : `n8n import:workflow` +
`n8n publish:workflow --id=<id>` (jamais `update:workflow --active=true`, déprécié).
Source : `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` R11 ;
`scripts/deploy-workflow.sh`.

## 9. Divergences comportementales notables vs pré-2.30.7

Observées lors du cutover 2.7.3 → 2.30.7 (source : `docs/rex/REX-N8N-UPGRADE-SIDECAR-2026-07-18.md` §Découvertes 2.30.7) :
- Colonne `user.role` renommée `user.roleSlug` (FK vers table `role`, valeur
  `global:owner`).
- `workflow_entity.id` (varchar 36) n'a plus de défaut DB → `n8n import:workflow`
  exige un `id` explicite dans le JSON, sinon erreur `null value in column id …
  violates not-null constraint`.
- `showNonProdBanner` n'est plus exposé au GET public de `/rest/settings` — niché
  sous `data.enterprise.showNonProdBanner`, GET authentifié requis pour vérifier le
  patch enterprise.
- IF node : le MCP natif de l'instance documente désormais `n8n-nodes-base.if` en
  version courante **2.3** (vérifié via `mcp__n8n-native__get_node_types`, ce
  chantier) — cohérent avec le fait que n8n considère IF v2+ comme le schéma
  standard actuel, indépendamment du statut R9 ci-dessus (le schéma existant n'est
  pas la preuve que l'exécution runtime est saine sur tous les cas, cf §1).

## 10. §7 confirmé en exécution réelle + contournement validé (T4.2, 2026-07-18)

**Confirmation directe (pas une corroboration indirecte)** du bug §7 : la branche
GitHub PR ajoutée au workflow `code-review` (id `TTO6eebHOVboM2MQ`) a levé
`ReferenceError: process is not defined [line N]` (execution `33896`, `@n8n/task-runner`
JsTaskRunner) lors d'un premier appel réel via curl, **alors que**
`roles/n8n/templates/n8n.env.j2` porte `N8N_RUNNERS_ENABLED=false`. Le conteneur
`javisi_n8n` déployé ne reflète donc pas (ou plus) cette valeur du template repo —
dérive non expliquée plus loin (root cause hors scope, aucun accès
inspect/redémarrage conteneur accordé pour ce chantier).

**Contournement qui fonctionne, vérifié en exécution réelle (execution `33899`,
`status: success`)** : ne JAMAIS lire `process.env`/`$env` à l'intérieur du JS d'un
Code node sur cette instance. Déplacer la lecture vers une expression n8n
`{{ $env.VAR }}` évaluée par le moteur principal dans un node **paramétré** en
amont :
- Comparaison de secret → node **IF** (`conditions.string`), pas un `if` JS dans
  le Code node (pattern déjà utilisé par `memory-telegram-bot.json`, node
  "Validate Telegram Secret").
- Valeurs à consommer plus loin dans un Code node (ex. `WORKSTATION_SSH_KEY_PATH`
  avant un `exec()`) → node **Set** (`n8n-nodes-base.set`, typeVersion 3.4,
  `assignments` avec `value: "={{ $env.VAR }}"`, `includeOtherFields: true`) juste
  avant le Code node, qui lit alors `$input.first().json.<champ>` — une donnée
  normale, pas `process.env`.

`require('child_process')` reste utilisable dans ce sandbox (seul le global
`process` est absent) — `exec()` fonctionne toujours une fois la valeur d'env
récupérée via un node Set en amont.

## 11. `WORKSTATION_SSH_KEY_PATH` — défaut jamais concrétisé (T4.2, 2026-07-18)

Le pattern SSH par `exec()` Code node (`WORKSTATION_SSH_KEY_PATH`/`_PI_USER`/`_PI_IP`,
utilisé par 4 workflows : `code-review` branche Palais préexistante,
`launch-claude-code.json`, `github-autofix.json`, + la branche GitHub PR ajoutée
par T4.2) échoue en exécution réelle : `Identity file /home/node/.ssh/id_ed25519
not accessible: No such file or directory` puis `Permission denied
(publickey,password)` (exit 255, execution `33899`). Cause : aucune variable
`workstation_ssh_key_path` n'est définie dans `inventory/group_vars/` → le défaut
Jinja de `n8n.env.j2:184` (`/home/node/.ssh/id_ed25519`) est utilisé tel quel,
mais aucun volume ne monte de clé privée à ce chemin dans le conteneur `javisi_n8n`.
Ces 4 workflows ont 0 exécution historique avant ce chantier — le gap n'avait
jamais été détecté. Non corrigé (gate humain — nécessite un vrai montage de clé +
enregistrement de la clé publique dans `~/.ssh/authorized_keys` sur waza, hors
scope autoring pur).

---

## Références

- `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md` §8 (R9)
- `docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md` (R3-bis, R9, R10, R11)
- `docs/rex/REX-SESSION-2026-04-12b.md` (IF v2 crash, webhookPath corrompu, R3-bis, R10)
- `docs/rex/REX-MOP-TASKRUNNER-2026-04-11.md` (Code node sandbox, `$env` vide)
- `docs/rex/REX-N8N-UPGRADE-SIDECAR-2026-07-18.md` (incident staging, webhook collisions, divergences 2.30.7)
- `docs/rex/REX-N8N-AUTORING.md` (capture automatique des échecs — livrable 2, alimenté par `scripts/n8n-authoring/rex-capture.sh`)
- Session de ce chantier (2026-07-18) : déploiement `memory-telegram-bot`, découvertes PUT non-atomique + node SSH `authentication` + `deactivate` explicite ; vérification read-only `execution_entity` de `memory-healthcheck` (R9 boolean corroboration §1) ; appels `mcp__n8n-native__get_sdk_reference`/`search_nodes`/`get_node_types`/`validate_workflow`.
