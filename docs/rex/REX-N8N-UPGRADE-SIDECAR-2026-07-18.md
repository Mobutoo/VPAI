# REX — Upgrade n8n prod 2.7.3 → 2.30.7 via Sidecar enterprise (2026-07-18)

## Contexte

Upgrade n8n prod sur Sese-AI (OVH VPS, amd64, `100.64.0.14`). Conteneur `javisi_n8n` :
`ghcr.io/mobutoo/n8n-enterprise:2.7.3` (image custom buildée) → `n8nio/n8n:2.30.7`
(image officielle) + patch enterprise appliqué au **runtime** via un init-container
Sidecar one-shot `n8n-init` qui copie l'arbre `node_modules/n8n` dans
`/opt/javisi/data/n8n-patched/2.30.7`, le patche, et que le service `n8n` monte en
overlay `:ro`.

Runbook suivi : `docs/runbooks/RUNBOOK-N8N-UPGRADE-SIDECAR.md`.
`n8n-mcp` était déjà passé à 2.65.1 (chantier antérieur).

---

## Déroulé

Orchestration multi-agents, 3 passes.

**§2 — Pré-flight lecture seule.** Baselines conformes à l'inventaire R4 : 125
workflows / 57 actifs, 79 IF v2 / 24 v1, 142 migrations. Vérification de la clé API
`claude-code-deploy` : scopes `workflow:read` + `workflow:update` + `workflow:activate`
+ `workflow:list`.

**§3 — Backup.** `pg_dump` STAMP=`20260718-145100` : dump custom-format 7.5M
(sha256 `0ac9fb24…`), tar data 85M. Copie off-host conservée sur Seko-VPN.

**§4 — Staging isolé** sur Sese lui-même (amd64 représentatif) : stack
`stg_n8n`/`stg_n8n_pg` sur réseau dédié `stg_n8n_net`, port 5679.

---

## Incident staging (run 2)

La neutralisation des side-effects par `UPDATE workflow_entity SET active=false`
(faite AVANT le boot) a été **contournée** par les migrations n8n 2.30.7, qui dérivent
l'état publié/actif de la colonne `workflow_entity.activeVersionId` et des tables de
publication (`CreateWorkflowPublicationOutboxTable` / `TriggerStatusTable`), pas du
seul champ `active` (cf R10).

Résultat : ~57 workflows réactivés au boot du staging — qui utilisait la clé de
chiffrement **prod réelle** (récupérée pour déchiffrer les credentials restaurés).
3 exécutions trigger réelles ont eu lieu :

- `hawktrade-killswitch` (id `kqnXEqeOK52xevbz`) a envoyé une **fausse alerte
  Telegram** « profit/status unreachable » au chat `6619155988`. Les appels HTTP vers
  freqtrade ont échoué en `EAI_AGAIN` (DNS interne absent sur staging), mais le node
  Telegram d'alerte a quand même émis un message (`message_id` présent).
- `Sprint Activator (NocoDB → GitHub)` (id `NDERC7jhw8UE014e`) a échoué 2× en 401
  (sans effet).

**Containment** : stack staging stoppée.

**Correction (run 3)** :
1. Clé `N8N_ENCRYPTION_KEY` jetable (`openssl rand -hex 24`, jamais la clé prod) →
   aucun credential réel déchiffrable.
2. Neutralisation double avant boot : `active=false` **ET** `activeVersionId=NULL`.
3. Contrôle continu : zéro exécution `mode=trigger` tolérée.

**Run 3 : GO.** Marqueur `2.30.7:48f350b1…`, overlay `--version 2.30.7`, migrations
142→219 sans erreur, bannière non-prod absente prouvée via `GET /rest/settings`
authentifié, 13 flags enterprise=true, test `$env` probe = 200
`{"probe":"staging-ok"}`, R9 = fixed.

---

## 2 bugs de code

Chemin Sidecar jamais exécuté en réel avant cette session — la garde
`n8n_upgrade_confirm` bloquait tous les essais antérieurs ; les 2 bugs n'ont donc été
découverts qu'au cutover prod.

### 1. Handler `block:` non résolu (`roles/n8n/handlers/main.yml`)

Le handler « Stop n8n before Sidecar re-patch (race guard, finding HIGH 3) » était un
`block:`. Ansible ne résout pas un handler block par son nom → erreur
« handler not found », playbook stoppé juste après la copie des scripts init
(conteneur n8n jamais touché, prod restée saine sur 2.7.3).

**Fix (commit `1c4bee5`)** : aplati en 2 handlers plats reliés par
`listen: Stop n8n before Sidecar re-patch` (check exists → stop), l'ordre suivant la
définition du fichier.

### 2. Faux MISSING_SERVICES sur service one-shot (`roles/docker-stack/tasks/main.yml`)

La tâche « Verify Phase B — detect missing containers » comparait
`docker compose config --services` (tous les services, dont `n8n-init`) au
sous-ensemble `--status running`. `n8n-init` est one-shot (`restart:no`) et sort en 0
→ jamais « running » → compté à tort `MISSING_SERVICES:n8n-init` → faux échec du
playbook alors que `javisi_n8n` 2.30.7 tournait déjà healthy.

**Fix (commit `8a6d342`)** : un service est sain s'il est running OU exited(0) ;
parsing de `docker compose ps -a --format json` (champs `State`/`ExitCode`).

---

## Découvertes 2.30.7

Utiles pour le prochain upgrade, vs versions antérieures :

- Colonne `user.role` renommée `user.roleSlug` (FK vers table `role`, valeur
  `global:owner`).
- `workflow_entity.id` (varchar 36) n'a plus de défaut DB → `n8n import:workflow`
  exige un champ `id` explicite dans le JSON (sinon
  « null value in column id … violates not-null constraint »).
- `showNonProdBanner` n'est plus au top-level de `/rest/settings` ni exposé au GET
  public — niché sous `data.enterprise.showNonProdBanner`, GET authentifié requis pour
  le vérifier.
- Count migrations 142→219 (+77).

---

## Résultat

Cutover réussi. `javisi_n8n` = `n8nio/n8n:2.30.7`, healthy en ~5s, HTTP 200 via
`https://mayi.ewutelo.cloud/rest/settings` (Caddy/Tailscale), migrations 142→219
appliquées sans erreur, credentials déchiffrés avec la vraie clé prod (zéro erreur
decrypt dans les logs), 57/125 workflows actifs (== baseline).

Re-run playbook idempotent : `ok=41 changed=0 failed=0`.

Backup rollback conservé off-host (Seko). Staging entièrement démantelé (le volume pg
contenait une copie complète des données prod).

Commande §5 corrigée : depuis waza il faut ajouter `-e prod_ip=100.64.0.14` (sinon
timeout port 804 sur l'IP publique `vault_prod_ip`, R7).

Disque prod post-upgrade : 81% (19G libres) — overlay Sidecar +1.8G, entrée en zone
80-90% à surveiller (disk-guard).

**Point latent (pré-existant, pas causé par l'upgrade)** : conflits de path webhook —
les workflows « Instagram Comment Reply », « Instagram DM Reply », « OpenCut Control
(Start/Stop) », « Meta Webhook/DM Webhook » échouent à s'activer (« The URL path … is
already taken ») : des workflows dupliqués partagent le même path webhook. Déjà présent
dans la DB prod (observé aussi au staging restauré depuis le dump). À investiguer
séparément.

---

## Follow-ups

(§6 runbook, séparés)

1. Ré-ingérer les docs n8n 2.x dans le RAG (les docs locales sont pré-2.0).
2. n8n-mcp natif de l'instance (`N8N_MCP_MANAGED_BY_ENV=true` +
   `N8N_MCP_ACCESS_ENABLED=true`, dispo dès 2.30.7 Community) devient activable.
3. Investiguer les conflits de path webhook (point latent ci-dessus).
