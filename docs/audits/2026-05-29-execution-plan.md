# Plan d'exécution — Restore Phase B + bumps sûrs + OpenClaw (session 2026-05-29)

**Planifié par** : Opus (session principale). **Exécuté par** : subagents Sonnet, avec gates validés par Opus entre chaque étape.
**Règle d'or** : fail-loud + pré-flight manifest obligatoire (l'incident venait d'un tag mort + `failed_when:false`). Rien ne redémarre avant filet backup vert.

## ⚠️ PRÉREQUIS RÉSOLU — ciblage Ansible via Tailscale (R7)
L'inventaire résout `prod_ip` → **IP publique `137.74.114.167:804` qui TIMEOUT** (hardening VPN-only, by-design). Tout `make` doit forcer l'IP Tailscale. **Vérifié 2026-05-29** : `ansible prod-server -m ping -e prod_ip=100.64.0.14` → **SUCCESS pong**.
→ **Chaque commande `make` de la session porte** : `EXTRA_ARGS='-e prod_ip=100.64.0.14'` (deploy-role) ou `EXTRA_VARS='prod_ip=100.64.0.14'` (deploy-prod). Sans ça, B2/B4 meurent au premier deploy.

---

## Versions retenues pour CE cycle (manifests vérifiés ✅)

| Image | Actuel | Cible | Raison |
|---|---|---|---|
| `plane_minio_image` | `RELEASE.2025-10-15T17-29-55Z` ❌ mort | `RELEASE.2024-11-07T00-52-20Z` | déjà sur disque, 0 migration Plane, débloque Phase B |
| `openclaw_image` | `2026.4.23` | `2026.5.27` | ✅ manifest, via GUIDE-OPENCLAW-UPGRADE (snapshot+validation) |
| `litellm` | `v1.83.7-stable` | `v1.83.14-stable` | patch stable |
| `nocodb` | `2026.04.1` | `2026.05.1` | bump mineur |
| `victoriametrics` | `v1.140.0` | `v1.144.0` | mineur |
| `loki` | `3.7.1` | `3.7.2` | patch sécu |
| `alloy` | `v1.15.1` | `v1.16.1` | mineur |
| `gotenberg` | `8.30.1` | `8.32.0` | mineur (jamais 8.31) |
| `firefly` | `version-6.6.1` | `version-6.6.2` | patch (⚠️ migre la DB au boot, hors dump B2 — non-critique) |
| `plane-admin/backend/frontend` | `v1.3.0` | `v1.3.1` | fix sécu ORM (⚠️ migre la DB au boot, hors dump B2 — non-critique) |

**Retirés du cycle (no-op)** : `mealie` et `grocy` — bump versions.yml inutile, **absents du `docker-compose.yml`** (cf. diagnostic Phase B) → ne changent rien au runtime. Ne pas toucher.

**Inchangés (pin actuel, manifest OK)** : grafana 12.4.3, carbone full-4.26.3, kitsu/cgwire 1.0.24, typebot 3.16.1, redis 8.4.0-bookworm, postgres 18.4, qdrant 1.18.1, caddy 2.11.3, diun 4.31.0, cadvisor 0.56.2, grocy 4.6.0, mailhog 1.0.1.

**Différés (tour 2, hors session)** : grafana v13 (breaking RBAC/GitSync), carbone 5.x (test templates MOP), kitsu 1.0.39 + typebot 3.17.1 (manifest non vérifié — rate-limit), redis 8.4.x (chercher tag valide, 8.4.3-bookworm mort), n8n 2.16.1 / zimboo / grapesjs (rebuild custom), couchdb 3.5.1 (migration Obsidian).

---

## Étapes (chaque B = 1 subagent Sonnet ; ⛔ = gate Opus)

### B1 — Code, aucun runtime (Sonnet)
- [ ] `versions.yml` : appliquer les 11 bumps + fix MinIO ci-dessus.
- [ ] `roles/backup-config/templates/pre-backup.sh.j2` : ajouter `export PGPASSWORD='{{ postgresql_password }}'` avant les `pg_dump`.
- [ ] `roles/docker-stack/tasks/main.yml:~408` : **retirer `failed_when: false`** de « Start Applications stack (Phase B) » → ajouter une task post-up qui compte les conteneurs Phase B attendus vs réels et **FAIL** si manquants.
- [ ] smoke-tests bloquants : `smoke_test_strict: true`.
- [ ] `source .venv/bin/activate && make lint`.
- **⛔ Gate Opus** : revoir le `git diff` complet + lint vert. Aucun secret, aucun tag non listé ci-dessus.

### B2 — Filet données (Sonnet, runtime read+backup)
- [ ] Déployer le fix backup : `make deploy-role ROLE=backup-config ENV=prod EXTRA_ARGS='-e prod_ip=100.64.0.14'`.
- [ ] Lancer un backup manuel + lister les dumps.
- **⛔ Gate Opus** : confirmer les `.dump` **non vides** (n8n, litellm, nocodb, kitsu). Snapshot `tar` `/opt/javisi/data/` fait. Pré-dump `pg-dumpall-pre-18.4.sql.gz` déjà présent (filet additionnel).

### B-OC — Snapshot OpenClaw pré-upgrade (Sonnet, guide §1)
- [ ] `cp openclaw.json openclaw.json.pre-upgrade-20260529` sur sese.
- [ ] Capturer `plugins list`, `channels list`, `agents list`, logs telegram AVANT.

### B3 — ⛔ GATE PRÉ-FLIGHT (Opus, read-only, BLOQUANT)
- [ ] `docker manifest inspect` de **CHAQUE image du compose final** (bumpées + inchangées). **Aucun `up` si un seul KO.** C'est la barrière anti-récidive.

### B4 — Déploiement (Sonnet)
- [ ] **Pré-prune disque** (`/` à 81%, ~19G libre, ~11 images à pull) : `docker image prune -f` sur sese (review d'abord ce qui partirait). Évite le wedge sur l'espace.
- [ ] `make deploy-role ROLE=docker-stack ENV=prod EXTRA_ARGS='-e prod_ip=100.64.0.14'` (rejoue Phase A inchangée + Phase B : MinIO fixé + bumps + OpenClaw 5.27). Le fail-loud (B1) fait échouer bruyamment si un service manque.

### B5 — Validation liveness + DONNÉES (Sonnet, guide §4 pour OpenClaw)
- [ ] Conteneurs Phase B `Up (healthy)`, `mayi/tala/llm/kitsu` → 200, LiteLLM healthy.
- [ ] **Intégrité données** : n8n workflow count > 0, projets Kitsu présents, budget LiteLLM intact, nocodb/plane non vides.
- [ ] **OpenClaw (guide §4)** : `plugins list` = telegram `loaded` (pas `disabled`), `channels list` = configured, logs propres, test message Telegram, `agents list` modèles OK.
- **⛔ Gate Opus** : tout vert. Sinon rollback.

### Rollback (si B5 échoue)
- MinIO/bumps : `git revert` du commit versions.yml + redeploy.
- OpenClaw (guide §6) : `openclaw_image: 2026.4.23` + restaurer `openclaw.json.pre-upgrade-20260529` + redeploy.

---

## RÉSULTAT SESSION (2026-05-29 ~minuit)
- **B1** ✅ (diff validé), **B2** ✅ (backups PG vérifiés non vides ; vrai fix = `docker exec -e PGPASSWORD`), **B-OC** ✅ (snapshot 20260529), **B3** ✅ (préflight GO).
- **B4** : 2 blocages résolus en cours de route — (1) rate-limit Docker Hub → `sudo docker login` root sur sese ; (2) réseau `javisi_sandbox` manquant (rôle `docker` pas rejoué) → créé manuellement (`internal`, 172.20.5.0/24). **⚠️ à pérenniser : rejouer le rôle `docker` un jour pour que le réseau soit idempotent.**
- **Phase B REMONTÉE : 21/26 sains.** mayi(n8n)=200, tala(grafana)=302, work/boss(plane)=200. Données intactes (rien recréé côté DB).
- **3 services KO à finir** :
  - **OpenClaw** : crash-loop — `tools.web.search.provider: brave` rejeté en 5.27 (devenu plugin à activer). `openclaw.json.j2:537-538`. = régression du bump 5.27. **Fix : rollback 4.23 (guide §6) OU activer plugin brave dans le template.**
  - **Kitsu** : gunicorn FATAL exit 1 (image 1.0.24 inchangée → pré-existant probable, à débugger R5).
  - **LiteLLM** : restarts=2, 502, pas d'erreur évidente (bump 1.83.14 ; à débugger R5).
- Warning compose `"Fjda" not set` — variable fantôme, à investiguer (non bloquant).

## ÉTAT FINAL SESSION (2026-05-30 ~00:20) — 23/26, 3 à finir en session fraîche
**Acquis (objectif principal atteint)** : Phase B remontée, 502 généralisé résolu. n8n=200, grafana=302, plane×6, monitoring (VM/loki/alloy/cadvisor/grafana), typebot, firefly, nocodb, carbone, gotenberg, msg2md, palais, zimboo, mailhog = **healthy**.

**3 services NON finis (causes comprises, fixes documentés — ~15-20 min à frais)** :
1. **Kitsu** — fix `;`→`#` dans `gunicorn.py.j2` **APPLIQUÉ ✅**, gunicorn ne crash plus (RUNNING). MAIS healthcheck `ExitCode=1` (FailingStreak 11), HTTP 000. **Reste** : identifier le healthcheck du compose kitsu + pourquoi l'app/endpoint ne répond pas (lire logs zou applicatifs, vérifier nginx interne, endpoint /api).
2. **OpenClaw** — template `openclaw.json.j2` corrigé (web.search conditionné) + task `logs/stability` **APPLIQUÉS ✅** (dossier créé). MAIS conteneur encore restarting + `openclaw.json` déployé semble garder `brave`. **Reste** : confirmer `grep '"provider": "brave"'` exact dans `/opt/javisi/data/openclaw/system/openclaw.json` ; si présent → le `deploy-role openclaw` n'a pas re-rendu (task l.206 doit écraser — vérifier que le tag openclaw exécute bien) → forcer re-template + `up -d --force-recreate openclaw` ; lire logs frais pour confirmer cause.
3. **LiteLLM** — **FIX NON APPLIQUÉ** : logs bouclent `Running prisma migrate deploy` (bug upstream 1.83.14, migration `CREATE INDEX CONCURRENTLY` en transaction). **Reste** : appliquer les 7 migrations SQL (cf. §FIX 1 du diagnostic) **via un fichier .sql copié sur sese** (pas inline — le quoting SSH a fait échouer le subagent) + INSERT `_prisma_migrations` + `docker restart javisi_litellm`. **Alternative plus sûre** : rollback `litellm_image` → version sans le bug (image locale `v1.83.3` présente) dans `versions.yml:18` + recreate.

**Arrêt volontaire** : contexte saturé + prod + 00:20 → ne pas s'acharner (risque d'erreur). Reprise recommandée en session fraîche.

## ✅ CLÔTURE SESSION FRAÎCHE (2026-05-30 ~01:00) — 26/26 sains
Les 3 services restants sont **healthy**. Diagnostic R5 + fixes appliqués (repo = vérité, deployed = patché surgical, **0 drift** : un futur `deploy-role docker-stack` re-rend l'identique).

| Service | Cause réelle confirmée | Fix appliqué | État |
|---|---|---|---|
| **LiteLLM** | boucle `prisma migrate deploy` /38s (bug 1.83.14, `CREATE INDEX CONCURRENTLY` en transaction) | **Voie SIMPLE** : `versions.yml` → `v1.83.3-stable` (image déjà sur disque) + sed tag compose déployé + `up -d --force-recreate litellm`. v1.83.3 → `No pending migrations to apply` | `healthy`, readiness 200, db connected, budget `max_budget 10.0/1d` intact |
| **Kitsu** | gunicorn:5000=200 + nginx:80=200 OK, mais HC tape `/api/health` → **404** (endpoint inexistant en 1.0.24 ; le vrai = `/api/status` → 200) | `docker-compose.yml.j2:671` HC `/api/health`→`/api/status` + sed compose déployé + recreate | `healthy` |
| **OpenClaw** | (1) `provider: brave` rejeté en 5.27 (devenu plugin) = crash boot ; (2) HC `wget --spider /healthz` mais **wget absent de l'image 5.27** (curl présent) → restait `health: starting`→unhealthy | (1) `openclaw.json.j2` : bloc web.search gaté `openclaw_web_search_enabled \| default(false)` → re-render via `deploy-role openclaw` (brave count=0) ; (2) `docker-compose.yml.j2:153` HC `wget --spider`→`curl -sf` + recreate | `healthy`, gateway `ready`, telegram `@WazaBangaBot` polling, 9 plugins |

**Résidu non-bloquant (décision archi différée)** : OpenClaw 5.27 spamme `EROFS: read-only file system` sur `system/openclaw.json.last-good`, `system/logs/config-health.json`, `system/.fs-safe-replace.*` — le mount `system/:ro` (anti-drift idempotence, REX) interdit les écritures self-management que 5.27 a ajoutées (4.23 ne les faisait pas). **Non-fatal** : gateway ready malgré tout. Fix propre = passer `system/` (ou des sous-mounts) en rw → arbitrage `:ro` anti-drift vs self-healing 5.27, à trancher hors prod-nuit. Tracké pour tour 2.

**Fichiers repo modifiés** : `inventory/group_vars/all/versions.yml`, `roles/openclaw/templates/openclaw.json.j2`, `roles/docker-stack/templates/docker-compose.yml.j2`. Lint : 0 erreur introduite (l'`Error 123` préexiste dans `roles/mop-templates/files/mop-wizy-datafields.yml`, WIP hors scope).

**Réactiver web search OpenClaw plus tard** : installer/activer le plugin `brave` dans 5.27 PUIS `openclaw_web_search_enabled: true`.

### Reprise — détail LiteLLM (2 voies)
Prérequis communs : `PG=$(ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 'docker exec javisi_postgresql printenv POSTGRES_PASSWORD')`.

**Voie SIMPLE (recommandée) — rollback à la version sans le bug** :
- `versions.yml` : `litellm_image: "ghcr.io/berriai/litellm:v1.83.3"` (image **déjà sur disque** sese, antérieure aux migrations cassées) — vérifier le manifest/présence d'abord.
- `make deploy-role ROLE=docker-stack ENV=prod EXTRA_ARGS='-e prod_ip=100.64.0.14'` puis `docker compose -f /opt/javisi/docker-compose.yml up -d --force-recreate litellm`.

**Voie FIX-FORWARD — appliquer les 7 migrations Prisma manuellement** (garde 1.83.14). Écrire ce SQL dans un fichier sur sese (`/tmp/litellm_migrate.sql`) et l'exécuter — NE PAS faire en inline SSH (le quoting casse) :
```sql
ALTER TABLE "LiteLLM_VerificationToken" ADD COLUMN IF NOT EXISTS "budget_limits" JSONB;
ALTER TABLE "LiteLLM_TeamTable" ADD COLUMN IF NOT EXISTS "budget_limits" JSONB;
ALTER TABLE "LiteLLM_BudgetTable" ADD COLUMN IF NOT EXISTS "allowed_models" TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "LiteLLM_TeamTable" ADD COLUMN IF NOT EXISTS "default_team_member_models" TEXT[] DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "LiteLLM_MCPServerTable" ADD COLUMN IF NOT EXISTS "instructions" TEXT;
CREATE TABLE IF NOT EXISTS "LiteLLM_AdaptiveRouterState" (router_name TEXT NOT NULL, request_type TEXT NOT NULL, model_name TEXT NOT NULL, alpha DOUBLE PRECISION NOT NULL, beta DOUBLE PRECISION NOT NULL, total_samples INTEGER NOT NULL DEFAULT 0, last_updated_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (router_name, request_type, model_name));
CREATE TABLE IF NOT EXISTS "LiteLLM_AdaptiveRouterSession" (session_id TEXT NOT NULL, router_name TEXT NOT NULL, model_name TEXT NOT NULL, classified_type TEXT NOT NULL, misalignment_count INTEGER NOT NULL DEFAULT 0, stagnation_count INTEGER NOT NULL DEFAULT 0, disengagement_count INTEGER NOT NULL DEFAULT 0, satisfaction_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, loop_count INTEGER NOT NULL DEFAULT 0, exhaustion_count INTEGER NOT NULL DEFAULT 0, last_user_content TEXT, last_assistant_content TEXT, tool_call_history JSONB NOT NULL DEFAULT '[]', pending_tool_calls JSONB NOT NULL DEFAULT '{}', turn_count INTEGER NOT NULL DEFAULT 0, last_processed_turn INTEGER NOT NULL DEFAULT -1, clean_credit_awarded BOOLEAN NOT NULL DEFAULT FALSE, terminal_status INTEGER, last_activity_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (session_id, router_name, model_name));
CREATE INDEX IF NOT EXISTS "idx_adaptive_router_session_activity" ON "LiteLLM_AdaptiveRouterSession" (last_activity_at);
CREATE TABLE IF NOT EXISTS "LiteLLM_MemoryTable" ("memory_id" TEXT NOT NULL, "key" TEXT NOT NULL, "value" TEXT NOT NULL, "metadata" JSONB, "user_id" TEXT, "team_id" TEXT, "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "created_by" TEXT, "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "updated_by" TEXT, CONSTRAINT "LiteLLM_MemoryTable_pkey" PRIMARY KEY ("memory_id"));
CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_MemoryTable_key_key" ON "LiteLLM_MemoryTable"("key");
CREATE INDEX IF NOT EXISTS "LiteLLM_MemoryTable_user_id_idx" ON "LiteLLM_MemoryTable"("user_id");
CREATE INDEX IF NOT EXISTS "LiteLLM_MemoryTable_team_id_idx" ON "LiteLLM_MemoryTable"("team_id");
ALTER TABLE "LiteLLM_TeamMembership" ADD COLUMN IF NOT EXISTS "total_spend" DOUBLE PRECISION NOT NULL DEFAULT 0.0;
INSERT INTO "_prisma_migrations" (id, checksum, finished_at, migration_name, logs, rolled_back_at, started_at, applied_steps_count) VALUES
 (gen_random_uuid()::text,'manual',NOW(),'20260401000000_add_budget_limits',NULL,NULL,NOW(),1),
 (gen_random_uuid()::text,'manual',NOW(),'20260401000000_add_team_member_model_scope',NULL,NULL,NOW(),1),
 (gen_random_uuid()::text,'manual',NOW(),'20260414140000_add_mcp_server_instructions',NULL,NULL,NOW(),1),
 (gen_random_uuid()::text,'manual',NOW(),'20260415120000_health_check_latest_per_model_index',NULL,NULL,NOW(),1),
 (gen_random_uuid()::text,'manual',NOW(),'20260418000000_add_adaptive_router_tables',NULL,NULL,NOW(),1),
 (gen_random_uuid()::text,'manual',NOW(),'20260421120000_add_memory_table',NULL,NULL,NOW(),1),
 (gen_random_uuid()::text,'manual',NOW(),'20260421135425_add_team_membership_total_spend',NULL,NULL,NOW(),1)
 ON CONFLICT (migration_name) DO NOTHING;
```
⚠️ La ligne `CREATE INDEX CONCURRENTLY` (migration 20260415) doit être exécutée **hors transaction** (autocommit, commande séparée), pas dans le bloc `.sql` ci-dessus :
`CREATE INDEX CONCURRENTLY IF NOT EXISTS "LiteLLM_HealthCheckTable_model_id_model_name_checked_at_idx" ON "LiteLLM_HealthCheckTable"("model_id","model_name","checked_at" DESC);`
Puis `docker restart javisi_litellm` + vérifier `health=healthy`.

### Reprise — OpenClaw
Vérifier `ssh ... 'sudo grep -c "\"provider\": \"brave\"" /opt/javisi/data/openclaw/system/openclaw.json'`. Si > 0 malgré le template corrigé → le `deploy-role openclaw` n'a pas écrasé (task l.206 `template` devrait pourtant le faire — vérifier que le tag `openclaw` est bien joué, ou éditer le json directement sur sese pour retirer le bloc `web.search`/`brave`). Puis `docker compose ... up -d --force-recreate openclaw` + checklist guide §4 (plugins/channels telegram).

### Reprise — Kitsu
gunicorn RUNNING (fix `;`→`#` OK). Healthcheck `ExitCode=1` → identifier la commande healthcheck dans le compose kitsu + tester l'endpoint depuis le conteneur (`docker exec javisi_kitsu curl -s localhost:<port>/...`). Vérifier nginx interne + que l'app zou répond (logs `docker logs javisi_kitsu`).

## Garde-fous transverses
- **VPN-only** (R7) : tout SSH via Tailscale `100.64.0.14:804`.
- **R1/R3** : pas de touch n8n workflows ici (déploiement infra only).
- **Commits atomiques** : 1 commit « fix(minio): tag valide + bumps apps + fail-loud Phase B », branche depuis main si demandé.
- **Évacuation secondaires (flash-suite/vps/fantrad/story-engine) + downgrade OVH + NAS** = hors session, cf. `2026-05-29-remediation-plan.md` §6.
