# Vaultwarden P0 (fondations) + P1a-bis + P1b (classe A → coffre) — Implementation Plan v2

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
> **v2 post-revue** (NEEDS-REWORK → 4 BLOCKER + 6 MAJOR foldés ; revue vérifiée LIVE sur Seko-VPN).

**Goal:** (1) Rendre le Vaultwarden existant (`fongola.ewutelo.cloud`) exploitable : backup offsite **testé par restore réel**, collections + comptes machine, canary. (2) **P1a-bis** : fermer l'angle mort `~/.claude.json` (8 littéraux, détecteur étendu = 8 violations prouvées). (3) Migrer la classe A (MACGYVER/HCLOUD/NAMECHEAP/LITELLM) vers Vaultwarden consommée par `secret-run` (invariant FORT), retirer du store, 🔒 rotation.

**Décisions v2 (issues de revue) :**
- **NOCODB reclassé classe B** (B4) : consommé par le serveur MCP `nocodb` au boot (`~/.claude.json`) → reste au store, PAS migré vers Vaultwarden. Sa rotation = mise à jour du store seul (une fois `~/.claude.json` en `${VAR}`).
- **Backup DB = builtin `/vaultwarden backup`** (B1) : sqlite3 absent du conteneur ET de l'hôte (vérifié live) ; builtin ≥1.32.1, instance=1.35.1. Réf qui marche : `flash-infra/ansible/roles/vaultwarden/templates/vaultwarden-backup.sh.j2` (R5).
- **User séparé (Fable P1.4) = DIFFÉRÉ explicitement** (M4b) : rbw sous `mobuone` ; résiduel « cache rbw lisible same-user » couvert par canary+rotation seulement, réévalué en P4. Gate humain informé.
- **Hazard `~/.claude.json`** : fichier RÉÉCRIT par le CLI → édition avec sessions fermées de préférence, re-vérification post-boot obligatoire.

**Gates humains 🔒 :** T0 export · T2 validation restore (bloquant, pas informatif) · T5b design unlock (P1.3) · T9 rotation.

---

## Phase P0 — Fondations (Seko-VPN ; exécution root/sudo — `mobuone` n'est pas dans le groupe docker, vérifié)

### Task 0: 🔒 GATE — export préalable du coffre
- [ ] Demander l'export chiffré (UI → Settings → Export vault), stocké HORS Seko-VPN. **Ne rien exécuter avant confirmation humaine explicite.**

### Task 1: Backup builtin → restic → offsite
**Files:** Create `Seko-VPN/roles/vaultwarden_backup/{defaults,tasks,handlers}/main.yml`, `templates/vw-backup.sh.j2`, `templates/vw-backup.{service,timer}.j2` ; Modify playbook site + `vault.yml` (creds restic/S3 🔒) + `defaults` (versions pinnées).

- [ ] **Step 1: Dépendances hôte** (M1) : tâches apt `restic` + `sqlite3` (présents dans Debian 13 ; versions apt = OK, noter dans defaults).
- [ ] **Step 2: Script `vw-backup.sh.j2`** (`set -euo pipefail`) :
  1. `docker exec vaultwarden /vaultwarden backup` → produit `/data/db_<ts>.sqlite3` (builtin, dump cohérent) ; récupérer le nom exact (`ls -t /data/db_*.sqlite3 | head -1` via `docker exec sh -c`).
  2. Tar via **shell CONTENEUR** (B2 — jamais de glob côté hôte) :
     `docker run --rm -v vaultwarden_data:/data:ro -v <staging>:/out alpine sh -c 'cd /data && tar czf /out/vw-data.tgz $(ls -d db_*.sqlite3 config.json rsa_key* attachments sends 2>/dev/null)'` — garde d'existence : `attachments`/`sends` absents live (vérifié) → jamais fatal.
  3. `restic backup` (env creds fichier 600 root) ; `restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune`.
  4. Nettoyage : supprimer le dump `db_*.sqlite3` du volume (hygiène, nit revue) ; audit JSON journald.
- [ ] **Step 3: Timer** `OnCalendar=daily` + `RandomizedDelaySec=1h` + `Nice=19`.
- [ ] **Step 4: Déployer + run** → `restic snapshots` = 1 snapshot > 0. Commit Seko-VPN.

### Task 2: 🔒 GATE — restore test RÉEL (anti faux-vert B3)
- [ ] **Step 1:** `restic restore latest --target /tmp/vw-restore` ; **untar** `vw-data.tgz` ; **renommer** `db_<ts>.sqlite3 → db.sqlite3` ; **`rm -f db.sqlite3-wal db.sqlite3-shm`** (résidus interdits après restore d'un dump — wiki) ;
- [ ] **Step 2: Preuve de contenu AVANT boot** : `sqlite3 /tmp/vw-restore/data/db.sqlite3 'select count(*) from users;'` → **≥1** (sqlite3 hôte installé Task 1). Un `/alive` 200 seul ne prouve RIEN (base vide = 200 aussi).
- [ ] **Step 3:** conteneur éphémère (`docker run --rm -p 127.0.0.1:8089:80 -v /tmp/vw-restore/data:/data vaultwarden/server:1.35.1-alpine`) → `/alive` 200. Détruire + purger.
- [ ] **Step 4: 🔒 STOP — confirmation humaine du restore avant Task 3** (même force que T0).

### Task 3: Org, collections, comptes machine (flux sans-SMTP documenté — m1)
- [ ] **Step 1:** Admin panel (`/admin`, ADMIN_TOKEN vault) → inviter `agent-waza@ewutelo.cloud`, `resolver@ewutelo.cloud`. **Sans SMTP (compose n'en a pas)** : pas de mail — l'invité s'inscrit manuellement sur `https://fongola.ewutelo.cloud/#/signup` avec l'email exact invité (l'admin invite « regardless of restrictions », wiki vérifié), mots de passe maîtres générés/stockés 🔒 humain.
- [ ] **Step 2:** Org `javisi-agents` + collections `infra-agents`/`strong-secrets`/`canary` ; côté org : accept + confirm des membres ; ACL `agent-waza` = lecture `infra-agents`+`canary`, **rien** sur `strong-secrets`.
- [ ] **Step 3:** Vérif login `agent-waza` → ne voit pas `strong-secrets`.

### Task 4: rbw waza (pinné) + pinentry + sibling test
- [ ] **Step 1:** rustup minimal + **`cargo install rbw --version 1.15.0 --locked`** (M3 — version épinglée, pas latest) + entrée `versions.yml` VPAI (`rbw_version: "1.15.0"`). Build deps déjà présents (build-essential/pkg-config vérifiés) ; rbw = crypto pure-Rust, pas de libssl-dev.
- [ ] **Step 2:** **`apt install pinentry-tty`** + `rbw config set pinentry pinentry-tty` (M2 — requis runtime, Pi headless) ; `base_url`, `email agent-waza@…`, `lock_timeout 3600`.
- [ ] **Step 3:** Sibling test : item `test-sibling` créé 🔒 → `rbw login && rbw sync && rbw get test-sibling >/dev/null && echo OK`.

### Task 5: Canary
- [ ] Item `canary-apikey` (collection `canary`) = URL webhook n8n `canary-alert` → Telegram (workflow validé `mcp__n8n-docs__validate_workflow` avant import — R1). Test curl → alerte reçue. Documenter « aveugle à l'env-dump ».

### Task 5b: 🔒 GATE — design unlock (Fable P1.3, M4a)
- [ ] Présenter à l'humain et faire valider : `lock_timeout` (3600 = re-unlock SSH toutes les heures ; alternative 28800 = journée) ; comportement headless = **fail-closed** (`secret-run` échoue proprement coffre verrouillé — c'est voulu, classe A = usage commande interactif/semi-interactif) ; jamais de master password sur disque. Décision consignée au runbook.

---

## Phase P1a-bis — Fermer `~/.claude.json` (B4, détecteur déjà étendu = 8 violations prouvées)

### Task 6: Migration `~/.claude.json` → `${VAR}`
**Files:** Modify `~/.claude.json` (hors git) ; Modify `~/.config/claude/secrets.env` (+2 clés) ; backup `~/.claude.json.bak-P1abis-<ts>`.

- [ ] **Step 1:** Backup + **ajouter au store** (extraction scriptée depuis `~/.claude.json`, valeurs jamais affichées, écriture atomique quotée) : `GITHUB_PERSONAL_ACCESS_TOKEN` (c'est ICI que vit le PAT que mcp.json référence sans source), `TREK_AUTHORIZATION`. (qdrant/plane/canva/stitch/n8n-docs/nocodb = déjà au store.)
- [ ] **Step 2:** Édition scriptée JSON : les 8 entrées → refs (`${QDRANT_API_KEY}`, `${PLANE_API_KEY}`, `${CANVA_X_API_KEY}`, `${STITCH_API_KEY}`, `${N8N_DOCS_AUTHORIZATION}`, env `NOCODB_API_TOKEN`→`${NOCODB_TOKEN}`, `${GITHUB_PERSONAL_ACCESS_TOKEN}`, `${TREK_AUTHORIZATION}`). **Hazard clobber** : le CLI réécrit ce fichier → éditer idéalement sessions fermées ; sinon accepter le risque + **re-vérifier le fichier après le prochain boot** (gate détecteur re-run).
- [ ] **Step 3:** `secrets-migration-check.sh` → **0 violation** ; contre-preuve sur backup (`CLAUDEJSON=<bak>`) → 8.
- [ ] **Step 4:** Validation session fraîche (avec celle de P1a) : qdrant/nocodb/github/trek MCP s'authentifient au prochain boot.

---

## Phase P1b — Classe A → coffre + secret-run

### Task 7: `secret-run` TDD (design M5 corrigé, 9 tests M6)
**Files:** Create `VPAI/roles/secret-broker/files/{secret-run,politique.yml,test_secret_run.sh}` + tasks (déploie `/usr/local/bin/` + `/etc/secret-run/`).

- [ ] **Step 1: 9 tests d'abord** (faux rbw en PATH, hermétique) : (1) ref+cmd autorisées → exit 0, valeur dans env enfant, **absente d'argv/`/proc/*/cmdline`** ; (2) valeur dans stdout enfant → `[REDACTED]` ; (3) **valeur dans stderr → `[REDACTED]`** ; (4) ref hors politique → exit 2 ; (5) cmd hors politique → exit 2 ; (6) ref absente du coffre → exit ≠0 message clair ; (7) **coffre verrouillé (faux rbw exit≠0) → fail-closed propre** ; (8) **code de sortie de l'enfant propagé** (enfant exit 7 → secret-run exit 7 — critique : sibling tests = `curl -sf`) ; (9) audit JSON sans valeur.
- [ ] **Step 2:** FAIL 9/9. **Step 3: Implémenter** — design corrigé M5 : `export VAR="$(rbw get …)"` puis **sous-process pipé** (PAS `env VAR=… cmd` — l'assignation serait dans l'argv de `env` ; PAS `exec` — incompatible avec le filtre) ; stdout ET stderr à travers un redacteur **littéral** (python line-buffered, `str.replace`, pas de regex → métacaractères sûrs) ; exit = code enfant (`PIPESTATUS[0]`/`wait`). **Limites documentées en tête de script** : valeur coupée entre chunks/lignes non garantie ; sortie binaire passthrough ; c'est un filet, l'invariant premier = la valeur n'est jamais un argument.
- [ ] **Step 4:** 9/9 PASS. **Step 5:** politique : `MACGYVER_BOT_TOKEN→{curl}`, `HCLOUD_TOKEN→{hcloud,curl}`, `NAMECHEAP_API_KEY→{curl}`, `LITELLM_API_KEY→{curl}` (NOCODB retiré — classe B). **Step 6:** rôle Ansible (tags `[secret_broker, phase4]`, checklist) + commit.

### Task 8: Migration classe A → Vaultwarden (4 refs)
- [ ] **Step 1:** Backup pré-P1b du store (`secrets.env.bak-P1b-<ts>`) — requis pour le self-test (m3). Créer 4 items `infra-agents` : MACGYVER/HCLOUD/NAMECHEAP depuis le store ; **LITELLM depuis `/home/mobuone/work/infra/VPAI/.claude/settings.local.json.bak-P1a-20260716-131851`** (m2 — chemin absolu ; PAS le homonyme `~/.claude/settings.json.bak-*`). Saisie via `rbw` scripté ou humaine 🔒.
- [ ] **Step 2:** Sibling tests : `secret-run MACGYVER_BOT_TOKEN -- curl -sf https://api.telegram.org/bot…/getMe`, HCLOUD `GET /v1/locations`, NAMECHEAP ping, LITELLM `/health` → 4/4 exit 0, transcript sans valeur.
- [ ] **Step 3:** Retirer MACGYVER/HCLOUD/NAMECHEAP du store (NOCODB **reste** — classe B) + **étendre détecteur** : classe A (`MACGYVER_BOT_TOKEN|HCLOUD_TOKEN|NAMECHEAP_API_KEY`) présente dans `secrets.env` = violation, avec **override `STORE=`** pour le self-test (m3). Gate → 0 ; self-test sur `secrets.env.bak-P1b-*` → ≥1.
- [ ] **Step 4:** Commit détecteur + note.

### Task 9: 🔒 GATE — rotation
- [ ] **Step 1:** Rotation par provider (BotFather, Hetzner, Namecheap, LiteLLM virtual keys) → nouvelles valeurs **directement dans Vaultwarden** 🔒. **+ NOCODB** (a vécu en clair) : nouvelle valeur → **store** (consommateurs `${VAR}` suivent au prochain boot).
- [ ] **Step 2:** Re-run 4 sibling tests + boot MCP nocodb OK.

### Task 10: Clôture
- [ ] Runbook `RUNBOOK-COFFRE-AGENTS.md` (unlock/lock_timeout décidé T5b, mode dégradé fail-closed, restore, rotation, canary, **différé : user séparé P1.4 → P4**) ; **MàJ plan P1a** : l'attente « NOCODB/HCLOUD résolvent en shell frais » devient « NOCODB seul » (m4) ; MàJ spec/STATUS/mémoire ; vérif finale : gate 0, `rbw lock && secret-run MACGYVER_BOT_TOKEN -- true` → échec propre ; commits VPAI + Seko-VPN.

---

## Critères de succès
- Restore **prouvé par contenu** (`count(users) ≥1` sur la base restaurée) — pas seulement `/alive`.
- `~/.claude.json` : 0 littéral (détecteur, 8→0) + re-vérifié post-boot (hazard clobber).
- `secret-run` 9/9 ; classe A : 4 refs Vaultwarden (sibling tests), retirées du store ; NOCODB classe B au store.
- Rotation 🔒 faite (4 Vaultwarden + NOCODB store), sibling tests re-passés.

## Rollback
P0 : rôles nouveaux, instance intacte. P1a-bis : `~/.claude.json.bak-P1abis-*`. P1b : `secrets.env.bak-P1b-*` + backups P1a ; secret-run retirable sans dépendant.
