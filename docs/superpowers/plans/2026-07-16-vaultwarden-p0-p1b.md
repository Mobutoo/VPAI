# Vaultwarden P0 (fondations) + P1b (classe A → coffre) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre le Vaultwarden existant (Seko-VPN, `fongola.ewutelo.cloud`) exploitable comme coffre agents — backup offsite testé, collections + comptes machine, canary — puis migrer la classe A (NOCODB/MACGYVER/HCLOUD/NAMECHEAP du store + LITELLM du backup) vers des refs Vaultwarden consommées par `secret-run` (invariant FORT : valeur jamais en contexte/argv), et retirer la classe A du store local.

**Architecture:** L'instance Vaultwarden tourne déjà (1.35.1-alpine pinné, SIGNUPS_ALLOWED=false, ADMIN_TOKEN en Ansible Vault, volume nommé `vaultwarden_data`, VPN-only). P0 n'y touche pas — il ajoute autour : backup SQLite-safe → restic → offsite, org/collections/comptes machine via admin API, item canary alerté. P1b installe `rbw` (cargo, hors npm — doctrine post-compromission `@bitwarden/cli`) + un wrapper `secret-run` sur waza, migre 5 secrets classe A, puis 🔒 rotation.

**Tech Stack:** Ansible (repo Seko-VPN pour le backup ; VPAI si rôle broker versionné là), restic, sqlite3, rustup/cargo (rbw), bash, API admin Vaultwarden.

**Base:** spec `docs/superpowers/specs/2026-07-16-coffre-agents-unifie-design.md` §6 P0/P1b · plan Fable `docs/plans/PLAN-COFFRE-AGENTS-2026-06-10.md` (corrigé : P0 ne reconstruit pas l'instance).

**Faits d'audit fondants (2026-07-16):** backup offsite ABSENT (zerobyte ne couvre que son volume) ; volume = named volume → dump SQLite à chaud obligatoire (`sqlite3 .backup`) ; `rbw` absent d'apt Ubuntu 24.04 aarch64 + cargo absent → rustup requis ; ADMIN_TOKEN déjà en vault (`vault_vaultwarden_admin_token`).

**Gates humains 🔒:** P0.1 export préalable (hors bande) · P0.6 validation restore · P1b.4 rotation des 5 secrets migrés. Rien d'irréversible sans ton feu vert explicite à ces points.

---

## Phase P0 — Fondations (Seko-VPN)

### Task 0: 🔒 GATE HUMAIN — export préalable du coffre

- [ ] **Step 1: Demander à l'humain un export chiffré du Vaultwarden actuel** (UI web → Settings → Export vault, format `.json chiffré` ou via client Bitwarden), stocké HORS Seko-VPN. **Ne rien exécuter avant confirmation.**
Expected: confirmation humaine explicite « export fait ».

### Task 1: Backup SQLite-safe → restic → offsite

**Files:**
- Create: `~/work/infra/Seko-VPN/roles/vaultwarden_backup/{defaults,tasks,templates,handlers}/main.yml` + `templates/vw-backup.sh.j2` + `templates/vw-backup.{service,timer}.j2`
- Modify: playbook site Seko-VPN (ajout rôle), `inventory/group_vars/all/vault.yml` (creds restic S3 — `ansible-vault edit`)

- [ ] **Step 1: Écrire le script de backup** `vw-backup.sh.j2` : (1) `docker exec vaultwarden /bin/sh -c 'sqlite3 /data/db.sqlite3 ".backup /data/db-backup.sqlite3"'` (dump cohérent à chaud — la copie brute d'un SQLite ouvert est corruptible) ; (2) tar du volume (`docker run --rm -v vaultwarden_data:/data:ro -v <staging>:/out alpine tar czf /out/vw-data.tgz -C /data db-backup.sqlite3 attachments sends config.json rsa_key*`) ; (3) `restic backup` vers repo S3 (creds env depuis fichier 600 root) ; (4) `restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune` ; (5) sortie JSON journald.
- [ ] **Step 2: Timer systemd quotidien** (`OnCalendar=daily`, `RandomizedDelaySec=1h`, `Nice=19`).
- [ ] **Step 3: Vars vault** : `vault_restic_vw_repo`, `vault_restic_vw_password`, `vault_s3_access_key`/`secret` (🔒 fournis par l'humain — Hetzner S3 ou bucket existant).
- [ ] **Step 4: Déployer** (`ansible-playbook` Seko-VPN, molecule lint d'abord — conventions du repo : molecule présent sur chaque rôle).
Run: déploiement + `systemctl start vw-backup.service` + `restic snapshots`
Expected: 1 snapshot listé, taille > 0.
- [ ] **Step 5: Commit repo Seko-VPN.**

### Task 2: 🔒 Restore test sur conteneur éphémère

- [ ] **Step 1:** `restic restore latest --target /tmp/vw-restore` sur Seko-VPN ; lancer un vaultwarden éphémère (`docker run --rm -p 127.0.0.1:8089:80 -v /tmp/vw-restore/...:/data vaultwarden/server:1.35.1-alpine`) ; vérifier `curl 127.0.0.1:8089/alive` + présence des items (compte test).
Expected: `/alive` = 200, données présentes. **Rapporter à l'humain avant Task 3 (gate P0.6).**
- [ ] **Step 2:** détruire l'éphémère + purger `/tmp/vw-restore`.

### Task 3: Organisation, collections, comptes machine

- [ ] **Step 1: Créer via UI/admin (`https://fongola.ewutelo.cloud/admin`, ADMIN_TOKEN du vault)** : org `javisi-agents` ; collections `infra-agents` (Tier 1), `strong-secrets` (Tier 2, vide pour l'instant), `canary`. SIGNUPS_ALLOWED=false → **inviter** les comptes machine : `agent-waza@ewutelo.cloud`, `resolver@ewutelo.cloud` (mots de passe maîtres générés, stockés 🔒 par l'humain ; API keys récupérées post-login).
- [ ] **Step 2: ACL** : `agent-waza` = lecture seule sur `infra-agents` + `canary`, AUCUN accès `strong-secrets`.
Run (vérif): login `agent-waza` (client web) → voit infra-agents/canary, pas strong-secrets.
Expected: ACL confirmée.

### Task 4: rbw sur waza (ARM64) + sibling test

**Files:**
- Modify: `~/.config/rbw/config.json` (généré par `rbw config`)

- [ ] **Step 1: Installer rustup + rbw** (hors npm — doctrine ; absent d'apt 24.04 aarch64, vérifié) :
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
. "$HOME/.cargo/env" && cargo install rbw --locked   # build one-shot Pi5 (~15-25 min)
rbw --version
```
- [ ] **Step 2: Configurer** : `rbw config set base_url https://fongola.ewutelo.cloud`, `rbw config set email agent-waza@ewutelo.cloud`, `rbw config set lock_timeout 3600`.
- [ ] **Step 3: Sibling test (R4)** : l'humain crée un item `test-sibling` (valeur banale) dans `infra-agents` ; `rbw login && rbw sync && rbw get test-sibling >/dev/null && echo OK` (valeur jamais affichée).
Expected: `OK`.

### Task 5: Item canary

- [ ] **Step 1:** créer item `canary-apikey` dans collection `canary` : la « clé » = URL webhook n8n d'alerte (nouveau workflow minimal `canary-alert` → Telegram monitoring, validé `mcp__n8n-docs__validate_workflow` avant import — R1).
- [ ] **Step 2:** test : `curl` de l'URL → message Telegram reçu.
Expected: alerte reçue ; documenter « canary aveugle à l'env-dump » (spec §10.5).

---

## Phase P1b — Classe A → coffre + secret-run

### Task 6: Wrapper `secret-run` + politique

**Files:**
- Create: `~/work/infra/VPAI/roles/secret-broker/files/secret-run` + `files/politique.yml` + tasks (déploie vers `/usr/local/bin/secret-run` + `/etc/secret-run/politique.yml`)
- Test: `~/work/infra/VPAI/roles/secret-broker/files/test_secret_run.sh`

- [ ] **Step 1: Écrire le test d'abord** (`test_secret_run.sh`, hermétique avec faux rbw en PATH) : (1) ref autorisée + cmd autorisée → exit 0, env enfant contient la valeur, **argv/ps ne la contient pas** ; (2) stdout de l'enfant contenant la valeur → filtré `[REDACTED]` ; (3) ref hors politique → exit 2 ; (4) cmd hors politique pour cette ref → exit 2 ; (5) ref absente du coffre → exit ≠ 0 message clair ; (6) audit JSON émis (ts/ref/cmd/exit, jamais la valeur).
- [ ] **Step 2: Run test → FAIL** (secret-run absent).
- [ ] **Step 3: Implémenter `secret-run`** (bash, ~80 l.) : parse `secret-run <ref> -- <cmd...>` ; charge politique (`ref → {cmds autorisées (basename), env_var}`) ; `rbw get <ref>` → var d'env du process enfant uniquement (`env VAR=… "$@"` via exec, jamais dans argv) ; stdout/stderr pipés à travers un filtre de la valeur ; audit → logger journald.
- [ ] **Step 4: Run test → 6/6 PASS.**
- [ ] **Step 5: Politique initiale** : `NOCODB_TOKEN → {curl}`, `HCLOUD_TOKEN → {hcloud, curl}`, `NAMECHEAP_API_KEY → {curl}`, `MACGYVER_BOT_TOKEN → {curl}`, `LITELLM_API_KEY → {curl}`.
- [ ] **Step 6: Déployer (rôle Ansible VPAI, tags `[secret_broker, phase4]`, checklist rôle complète) + commit VPAI.**

### Task 7: Migration classe A → Vaultwarden

- [ ] **Step 1:** créer les 5 items dans `infra-agents` (valeurs depuis : store pour NOCODB/MACGYVER/HCLOUD/NAMECHEAP ; **backup Task 0 P1a** `settings.local.json.bak-P1a-20260716-131851` pour LITELLM — jamais affichées : extraction scriptée → `rbw` via stdin/edit non-interactif ou saisie humaine 🔒 si rbw ne permet pas la création scriptée propre).
- [ ] **Step 2: Sibling test par ref** : `secret-run NOCODB_TOKEN -- curl -sf …/api/v2/meta/bases` (endpoint léger) → 200 ; équivalent pour HCLOUD (`GET /v1/locations`), NAMECHEAP (ping API), MACGYVER (getMe Telegram), LITELLM (`/health` LiteLLM).
Expected: 5/5 exit 0, transcript sans valeur.
- [ ] **Step 3: Retirer la classe A du store** `secrets.env` (sed 4 lignes) + **étendre le détecteur** : nouvelle assertion « classe A absente du store » (`NOCODB_TOKEN|MACGYVER_BOT_TOKEN|HCLOUD_TOKEN|NAMECHEAP_API_KEY` dans `secrets.env` = violation).
Run: `secrets-migration-check.sh` → 0 violation ; `--self-test` sur backup → ≥1.
- [ ] **Step 4: Commit** (détecteur VPAI + note).

### Task 8: 🔒 GATE HUMAIN — rotation des 5 migrés

- [ ] **Step 1:** présenter à l'humain la liste des 5 secrets (noms seuls) ayant vécu en clair → rotation par provider (NocoDB UI, Hetzner console, Namecheap, BotFather, LiteLLM virtual keys), nouvelles valeurs saisies **directement dans Vaultwarden** (jamais par le terminal de l'agent).
- [ ] **Step 2:** re-run des 5 sibling tests post-rotation.
Expected: 5/5 OK avec les nouvelles valeurs.

### Task 9: Clôture

- [ ] **Step 1:** runbook `docs/runbooks/RUNBOOK-COFFRE-AGENTS.md` (unlock rbw au SSH, mode dégradé Seko-down = cache rbw chiffré local, restore backup, rotation, canary) + MàJ spec/STATUS/mémoire.
- [ ] **Step 2:** vérifs finales : gate détecteur 0 ; `rbw lock && secret-run NOCODB_TOKEN -- true` → échec propre (agent verrouillé = fail-closed documenté).
- [ ] **Step 3:** commit final VPAI + Seko-VPN.

---

## Critères de succès
- Backup : snapshot restic offsite quotidien + **restore prouvé** (conteneur éphémère `/alive` 200).
- ACL : `agent-waza` ne voit pas `strong-secrets` (test réel).
- `secret-run` : 6/6 tests (valeur jamais argv/stdout/contexte), politique appliquée.
- Classe A : 5 refs Vaultwarden opérationnelles (sibling tests), **retirées du store**, détecteur étendu = 0 violation / self-test ≥1.
- Rotation 🔒 faite, sibling tests re-passés.

## Rollback
P0 : rôles nouveaux (retrait = stop timer + delete rôle), instance intacte. P1b : classe A re-copiable du backup P1a vers le store (`.bak-P1a-20260716-131851`), `secret-run` retirable sans impact (rien d'autre n'en dépend avant la politique).
