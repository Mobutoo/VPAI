# Requirements: Plane — Operational Intelligence

**Defined:** 2026-02-28
**Core Value:** Le Concierge crée et orchestre les projets via Telegram → Plane, et les agents OpenClaw exécutent et synchronisent automatiquement leur progression.

---

## v1 Requirements

### 1. Infrastructure

- [ ] **INFRA-01**: Plane déployé via Docker Compose
  - Image Plane officielle (version pinnée dans `versions.yml`)
  - 3 containers: `plane-web`, `plane-api`, `plane-worker`
  - Réseaux Docker: `frontend` (Caddy), `backend` (PG/Redis), `egress` (webhooks sortants)

- [ ] **INFRA-02**: PostgreSQL partagé
  - DB `plane_production` créée au provisioning
  - User `plane` avec password `{{ postgresql_password }}` (convention VPAI unique password)
  - Schéma isolé, migrations Plane auto-apply au démarrage

- [ ] **INFRA-03**: Redis partagé avec namespace
  - Namespace `plane:*` pour toutes les clés Plane
  - Queues workers isolées (pas de collision avec n8n/litellm)

- [ ] **INFRA-04**: Caddy reverse proxy
  - `work.ewutelo.cloud` → `plane-web:3000`
  - VPN-only (ACL `@blocked_plane` avec 2 CIDRs: VPN + Docker frontend)
  - Exception `/webhooks/*` publique (authentifiée par secret)

- [ ] **INFRA-05**: Backup Zerobyte
  - DB `plane_production` incluse dans dump PostgreSQL quotidien
  - Assets Plane (uploads) → volume Docker persistant + backup

- [ ] **INFRA-06**: Limites ressources
  - `plane-web`: 256MB RAM, 0.25 CPU
  - `plane-api`: 384MB RAM, 0.5 CPU
  - `plane-worker`: 256MB RAM, 0.25 CPU

### 2. Auth & Access

- [ ] **AUTH-01**: Compte admin Concierge
  - Email: `concierge@javisi.local` (créé au provisioning)
  - Password: généré aléatoire, stocké `secrets.yml`
  - Rôle: Admin workspace

- [ ] **AUTH-02**: Auth humain email/password
  - Compte: `{{ admin_email }}` (variable wizard)
  - Auth native Plane, pas de SSO
  - VPN-only → sécurité suffisante

- [ ] **AUTH-03**: API tokens agents OpenClaw
  - 1 token par agent (Imhotep, Thot, Basquiat, R2D2, Shuri, Piccolo, CFO, Maintainer, Hermes, Concierge)
  - Scope: `read:issues`, `write:issues`, `read:projects`
  - Stockés dans `secrets.yml`, injectés dans OpenClaw skill `plane-bridge`

- [ ] **AUTH-04**: Gestion tokens via UI
  - Concierge peut régénérer tokens agents depuis Plane UI
  - Tokens jamais expirés (services internes VPN)

### 3. OpenClaw Integration

- [ ] **OPENCLAW-01**: Skill `plane-bridge` (remplace `kaneo-bridge`)
  - Fichier: `~/.openclaw/skills/plane-bridge/SKILL.md`
  - Template Ansible: `roles/plane/templates/plane-bridge/SKILL.md.j2`
  - Fonctions exposées: 8 outils MCP
  - Config: API endpoint, token injecté depuis `secrets.yml`

- [ ] **OPENCLAW-02**: Fonction `plane.list_my_tasks`
  - Liste tasks assignées à l'agent appelant (via `agent_id` custom field)
  - Filtres: status `todo|in_progress`, pas `done|cancelled`
  - Retour: JSON array [{id, title, description, status, priority, due_date, project, dependencies}]
  - Utilisé par agents pour polling (cron 5min)

- [ ] **OPENCLAW-03**: Fonction `plane.get_task_details`
  - Récupère détails complets d'une task (ID en param)
  - Inclut: commentaires, historique, custom fields, attachments, time entries
  - Utilisé avant démarrage travail (contexte complet)

- [ ] **OPENCLAW-04**: Fonction `plane.update_task_status`
  - Transitions: `todo` → `in_progress` → `done` (ou `blocked`, `cancelled`)
  - Validation: impossible `done` si dependencies pas `done`
  - Auto-comment: "🤖 {agent_name} a démarré cette tâche" / "✅ Complété par {agent_name}"

- [ ] **OPENCLAW-05**: Fonction `plane.add_comment`
  - Commentaire riche markdown supporté
  - Templates: progression ("⏳ 60% complete - building Docker image"), erreur ("❌ Failed: {error_msg}"), question ("❓ Blocker: need decision on X")
  - Webhook déclenché → notification Telegram si critique

- [ ] **OPENCLAW-06**: Fonction `plane.start_timer` / `plane.stop_timer`
  - Time tracking automatique via Plane API `/api/v1/issues/:id/time-logs/`
  - Agent démarre timer en commençant task, stop en finissant
  - Logged time visible dans Plane UI + analytics

- [ ] **OPENCLAW-07**: Fonction `plane.upload_deliverable`
  - Upload fichier généré (code, doc, image) comme attachment Plane
  - Stockage: Plane internal storage (volume Docker persistant)
  - Lien téléchargement ajouté en commentaire task

- [ ] **OPENCLAW-08**: Fonction `plane.create_task` (Concierge only)
  - Seul le Concierge peut créer tasks (évite chaos multi-agents)
  - Params: title, description, project_id, assignee (agent_id), priority, due_date, dependencies[]
  - Auto-set custom fields: `cost_estimate` (calculé), `confidence_score` (0.8 par défaut)

- [ ] **OPENCLAW-09**: Polling mechanism agents
  - Cron interne OpenClaw: toutes les 5min, chaque agent exécute `plane.list_my_tasks`
  - Si nouvelles tasks détectées → agent décide de démarrer (basé sur priorité + charge actuelle)
  - Agent autonome: pas de dispatch central, self-organization

- [ ] **OPENCLAW-10**: Custom field `agent_id` mapping
  - Format: nom court agent (ex: `imhotep`, `thot`, `basquiat`)
  - Assignation Plane UI → auto-rempli `agent_id` custom field
  - Agents filtrent tasks par ce champ (pas par Plane assignee natif)

- [ ] **OPENCLAW-11**: Custom field `cost_estimate` calcul
  - Concierge estime coût $ (basé sur historique agent + complexité)
  - Affiché dans Plane UI (custom field type `number`)
  - Utilisé pour budget tracking (somme tasks actives vs budget restant)

- [ ] **OPENCLAW-12**: Custom field `confidence_score` usage
  - Agent set score 0.0-1.0 après completion
  - Score bas (<0.7) → trigger review humaine (notification Telegram)
  - Stocké pour analytics qualité agent

- [ ] **OPENCLAW-13**: Custom field `session_id` traçabilité
  - Lien vers session OpenClaw (ID unique)
  - Permet retrouver logs/traces complètes depuis task Plane
  - Format: `openclaw-session-{uuid}`

- [ ] **OPENCLAW-14**: Gestion dépendances tasks
  - Agent check dependencies avant démarrer (via `plane.get_task_details`)
  - Si blocked → wait (recheck au prochain poll 5min)
  - Si dependency failed → mark task `blocked` + comment + alert Concierge

- [ ] **OPENCLAW-15**: Erreur handling & retry
  - Erreur transitoire (network, rate limit) → retry 3x avec backoff exponentiel (1s, 5s, 15s)
  - Erreur permanente (auth, 404) → log + mark task `blocked` + comment erreur
  - Timeout Plane API: 30s par requête

- [ ] **OPENCLAW-16**: Webhook consumption (agent-side)
  - Agents écoutent webhooks Plane via n8n relay (optionnel, complément polling)
  - Event `issue.assigned` → notification immédiate agent (pas attendre 5min poll)
  - Push-based + pull-based = réactivité optimale

- [ ] **OPENCLAW-17**: Concierge orchestration flow
  - Telegram user → Concierge: "Ajoute feature X"
  - Concierge → Plane: `plane.create_project` (si nouveau) + `plane.create_task` (breakdown)
  - Concierge analyse dépendances, assigne agents optimaux (charge + persona)
  - Agents notifiés → détectent tasks → exécutent

- [ ] **OPENCLAW-18**: Task completion criteria
  - Agent marque `done` SEULEMENT si: code committed (si code task), tests passed (si applicable), deliverable uploaded (si requis), commentaire résumé ajouté
  - Validation via confidence_score: <0.7 = review needed

- [ ] **OPENCLAW-19**: Attachments/deliverables handling
  - Agent génère fichier → upload via `plane.upload_deliverable`
  - Types: code (.zip), docs (.md, .pdf), images (.png), logs (.txt)
  - Max 50MB par fichier (limite Plane)

- [ ] **OPENCLAW-20**: Rate limiting respect
  - Plane API: ~100 req/min (self-hosted, configurable)
  - Agents throttle requests: max 1 req/s par agent
  - Polling 5min × 10 agents = 2 req/min (safe)

### 4. Notifications & Webhooks

- [ ] **NOTIF-01**: Plane webhooks configurés pour événements clés
  - Events: `issue.created`, `issue.updated`, `issue.activity.created`, `issue.completed`, `cycle.started`, `cycle.completed`
  - Webhook URL: `https://<domain>/webhooks/plane` (endpoint n8n)
  - Secret partagé pour authentification

- [ ] **NOTIF-02**: Endpoint webhook public `/webhooks/plane`
  - Accessible sans VPN (exception Caddy ACL)
  - Authentification par secret token (header `X-Plane-Signature`)
  - Rate limiting (100 req/min max)

- [ ] **NOTIF-03**: Workflow n8n `plane-notifications`
  - Reçoit webhooks Plane
  - Parse payload (event type, actor, issue, project)
  - Filtre événements pertinents (skip updates mineures)
  - Formate message Telegram contextuel

- [ ] **NOTIF-04**: Messages Telegram riches
  - Format: `[Projet] Agent X a complété "Tâche Y"` avec emoji statut
  - Lien direct vers issue Plane
  - Contexte: temps passé, assigné à qui, blockers si présents

- [ ] **NOTIF-05**: Filtres notifications intelligents
  - Notifier QUE: tâches complétées, blockers critiques, nouveaux projets, cycles démarrés/terminés
  - Skip: commentaires agents (trop verbeux), minor updates

- [ ] **NOTIF-06**: Commandes Telegram bidirectionnelles
  - `/plane status` → résumé projets actifs + tâches en cours
  - `/plane project <nom>` → détails projet spécifique
  - `/plane agent <nom>` → tâches assignées à un agent
  - Via n8n → Plane API → format réponse → Telegram

- [ ] **NOTIF-07**: Notifications temps-réel agents
  - Quand agent OpenClaw update progression → webhook immédiat → Telegram
  - Permet suivi live sans ouvrir Plane UI

- [ ] **NOTIF-08**: Digest quotidien (optionnel v2)
  - Cron n8n 8h → Plane API analytics → Telegram
  - Résumé: tâches complétées hier, blockers actifs, forecast aujourd'hui

### 5. Provisioning

- [ ] **PROV-01**: Workspace initial `javisi`
  - Créé automatiquement au premier démarrage Plane
  - Settings: timezone UTC, language FR

- [ ] **PROV-02**: Premier projet `Onboarding`
  - Projet test avec 3 issues exemples
  - Démo workflow Concierge → agents

- [ ] **PROV-03**: Génération API tokens
  - Script Ansible via `uri` module → Plane API `/api/v1/api-tokens/`
  - Tokens stockés dans `secrets.yml`

- [ ] **PROV-04**: Custom fields création
  - Via Plane API: création champs `cost_estimate`, `confidence_score`, `agent_id`, `session_id`
  - Appliqués au workspace `javisi`

### 6. Monitoring

- [ ] **MONITOR-01**: Healthcheck Plane
  - Endpoint `/api/health` (plane-api)
  - Cadvisor → VictoriaMetrics → Grafana alerting
  - Alert si down >2min

- [ ] **MONITOR-02**: Logs centralisés
  - Logs Plane → stdout → Loki (via Alloy)
  - Rétention 7 jours

- [ ] **MONITOR-03**: Métriques Grafana
  - Dashboard Plane: requests/s, latency P95, queue depth, DB connections
  - Utilisation ressources (CPU/RAM par container)

- [ ] **MONITOR-04**: Alertes critiques
  - Plane API down
  - PostgreSQL connections >80%
  - Redis memory >80%
  - Worker queue backlog >100 jobs

### 7. OpenClaw Upgrade & Security

- [ ] **OPENCLAW-UPG-01**: Version target OpenClaw
  - Upgrade: `2026.2.23` → `2026.2.26` (3 releases, pin exact dans `versions.yml`)
  - Breaking changes: DM allowlist enforcement, onboarding reset scope
  - Security fixes: sandbox path validation, SSRF guards, plugin auth hardening
  - Backup image avant upgrade: `docker tag openclaw:2026.2.23 openclaw:backup-2026-02-28`

- [ ] **OPENCLAW-UPG-02**: Compatibilité Docker volume isolation
  - Volume isolation déjà activé: `openclaw_volume_isolation: true`
  - Structure system/workspace/state déjà conforme
  - Identity mounts déjà résolus (REX-49): path container = path host
  - Validation: aucun changement volume requis pour v2026.2.26

- [ ] **OPENCLAW-UPG-03**: Capabilities minimales pour spawn
  - Capabilities actuelles SUFFISANTES: `CHOWN`, `SETGID`, `SETUID`
  - Pas d'ajout requis pour v2026.2.26
  - `cap_drop: ALL` conservé (sécurité maximale)
  - Validation: test spawn Concierge → Imhotep après upgrade

- [ ] **OPENCLAW-UPG-04**: Seccomp profile validation
  - Profile Docker défaut PEUT bloquer syscalls spawn (`clone`, `fork`, `execve`)
  - Test d'abord sans seccomp custom (peut fonctionner)
  - Si spawn EPERM détecté → Option A: `seccomp=unconfined` (quick fix), Option B: profile custom `.json` (secure)
  - Préférer Option B si possible (whitelist syscalls spawn uniquement)

- [ ] **OPENCLAW-UPG-05**: User/Group mapping spawn
  - OpenClaw run as `user: 1000:1000` (non-root) conservé
  - Agents spawn héritent UID/GID (pas d'escalation)
  - Validation post-upgrade: `docker exec javisi_openclaw ps aux` → tous process UID 1000

- [ ] **OPENCLAW-UPG-06**: Réseau agents spawn
  - Agents spawn sur network `sandbox` (172.20.5.0/24, internal) existant
  - Doivent accéder: Plane API, LiteLLM, PostgreSQL, Qdrant, n8n
  - Network `backend` + `egress` suffisants (pas besoin `host` mode)

- [ ] **OPENCLAW-UPG-07**: Filesystem isolation agents
  - Chaque agent spawn: `/workspace/<agent-id>/<session-id>/`
  - Isolation via subdirectories (pattern actuel inchangé)
  - Cleanup automatique sessions (OpenClaw internal GC)

- [ ] **OPENCLAW-UPG-08**: Testing spawn functionality
  - Test smoke: `docker exec javisi_openclaw openclaw send concierge "Spawn Imhotep pour dire bonjour"`
  - Vérifier logs: `docker logs javisi_openclaw 2>&1 | grep -i 'spawn\|EPERM\|EACCES'`
  - Valider fichiers: `/opt/javisi/data/openclaw/workspace/imhotep/` ownership correct

- [ ] **OPENCLAW-UPG-09**: Rollback strategy
  - Image backup: `openclaw:backup-2026-02-28` (tag pré-upgrade)
  - Variable Ansible: `openclaw_version` overridable pour rollback rapide
  - Playbook: `make deploy-role ROLE=openclaw ENV=prod EXTRA_VARS="openclaw_version=2026.2.23"`

- [ ] **OPENCLAW-UPG-10**: Migration state/skills
  - Skills `~/.openclaw/skills/` persistés dans volume (pas de perte)
  - State agents backward compatible (v2026.2.26 lit v2026.2.23 state)
  - Backup state: `tar -czf /opt/backups/openclaw-state-$(date +%F).tar.gz /opt/javisi/data/openclaw/`

- [ ] **OPENCLAW-UPG-11**: Logs & debugging spawn issues
  - Loki capture stdout/stderr agents spawn (via parent container)
  - Log level `DEBUG` pendant testing (env `LOG_LEVEL=debug`)
  - Grafana dashboard: spawn rate, spawn failures, spawn duration P95

- [ ] **OPENCLAW-UPG-12**: Performance limits spawn
  - Max agents spawn simultanés: 5 (limite mémoire VPS 8GB)
  - Queue interne si >5 spawn demandés
  - Limites par agent spawn: RAM 256MB, CPU 0.25, timeout 30min

- [ ] **OPENCLAW-UPG-13**: plane-bridge skill compatibility
  - Nouveau skill `plane-bridge` (remplace `kaneo-bridge`)
  - Vérifier format SKILL.md compatible v2026.2.26
  - Test chargement: `docker exec javisi_openclaw openclaw list-skills` → voir `plane-bridge`

- [ ] **OPENCLAW-UPG-14**: Breaking changes documentation
  - **DM Allowlist**: vérifier `openclaw.json` config `dmPolicy: 'allowlist'` + `allowFrom` set (évite silent drops Telegram)
  - **Onboarding scope**: `openclaw onboard --reset` défaut = `config+creds+sessions` (workspace préservé)
  - **Secrets workflow**: nouvelle feature `openclaw secrets` (optionnel, pas requis pour migration)
  - Documenter dans `docs/REX-OPENCLAW-UPGRADE-PLANE.md`

- [ ] **OPENCLAW-UPG-15**: Security audit post-upgrade
  - Container scan: `trivy image ghcr.io/openclaw/openclaw:2026.2.26`
  - Vérifier CVEs critiques corrigées vs 2026.2.23
  - Security fixes appliqués: sandbox path validation, SSRF guards, plugin auth
  - DooD pattern sécurisé maintenu (socket read-only, capabilities minimales)

---

## v2 Requirements

(Aucun pour v1 — focus livraison rapide)

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| **Palais custom build** | Plane DEVIENT l'operational intelligence, pas un interim |
| **SSO/OAuth Plane** | Email/password suffit (VPN-only, solo user) |
| **Mobile app Plane** | Web-only pour v1 |
| **Multi-tenancy Plane** | Un seul workspace (javisi) |
| **Custom Plane plugins** | API REST standard uniquement |
| **PostgreSQL dédié Plane** | Instance partagée obligatoire (contrainte infra) |
| **Real-time WebSocket UI** | Polling API suffit agents, SSE humain OK |
| **Plane modules avancés** | Activer uniquement: issues, projects, cycles, modules (pas pages, analytics avancés) |
| **OpenClaw read-only filesystem** | Besoin write `/home/node/.openclaw/` pour spawn agents |
| **Seccomp strict mode** | Profile Docker défaut d'abord, custom SEULEMENT si spawn bloqué |

---

## Traceability

Mapping requirements → phases (sera rempli par roadmap).

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | TBD | Pending |
| INFRA-02 | TBD | Pending |
| ... | ... | ... |

**Coverage:**
- v1 requirements: 61 total
- Mapped to phases: 0 (roadmap à créer)
- Unmapped: 61 ⚠️

---

*Requirements defined: 2026-02-28*
*Last updated: 2026-02-28 after initial definition*
