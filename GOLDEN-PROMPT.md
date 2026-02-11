# Golden Prompt — Développement Complet de la Stack AI Self-Hosted

> **Version** : 1.0.0  
> **Date** : 11 février 2026  
> **Usage** : Copier-coller ce prompt dans Claude Code pour lancer le développement.  
> **Workflow** : Claude Code exécute → Opus 4.6 review → itération si nécessaire.

---

## Instructions Générales pour Claude Code

Tu es un ingénieur DevOps/SRE senior. Tu vas développer un projet Ansible complet pour déployer une stack AI/automatisation auto-hébergée sur un VPS unique avec Docker.

### Règles strictes

1. **Lis les fichiers `PRD.md` et `TECHNICAL-SPEC.md`** dans le repository avant de coder quoi que ce soit. Ils contiennent l'architecture, les décisions, et les contraintes validées.
2. **Jamais de `:latest`** sur aucune image Docker. Toutes les versions sont pinnées dans `versions.yml`.
3. **Ansible best practices** : FQCN pour tous les modules, `changed_when`/`failed_when` explicites, `set -euo pipefail` pour tout script shell, pas de `command`/`shell` si un module Ansible existe.
4. **Idempotence** : Chaque rôle doit pouvoir être exécuté 2x sans changement à la 2ème exécution.
5. **Templates Jinja2** : Toutes les valeurs configurables utilisent des variables du wizard (jamais de valeurs hardcodées).
6. **Molecule tests** : Chaque rôle a un test Molecule minimal (converge + verify).
7. **Pas de réseau par défaut Docker** : Utiliser les réseaux nommés définis dans la spec (frontend, backend, monitoring, egress).
8. **Documentation** : Chaque rôle a un `README.md` avec description, variables, dépendances, et exemples.

### Structure cible

Le projet cible est décrit en détail dans `TECHNICAL-SPEC.md` section 1. Le wizard de variables est dans `PRD.md` section 2.

---

## Phase 1 — Fondations (Rôles 1-4)

### Contexte
Créer la base : OS, sécurité, Docker, VPN. Sans cette phase, rien d'autre ne fonctionne.

### Tâches

#### 1.1 Rôle `common`
- Packages : `curl`, `wget`, `jq`, `gnupg`, `ca-certificates`, `python3-pip`, `unzip`, `htop`, `ncdu`, `tmux`
- Locale : `{{ locale }}` via `community.general.locale_gen`
- Timezone : `{{ timezone }}` via `community.general.timezone`
- NTP : systemd-timesyncd configuré
- Hostname : `{{ prod_hostname }}`
- `/etc/hosts` : ajouter mapping Headscale hostname→IP
- Sysctl : `vm.swappiness=10`, `net.core.somaxconn=65535`, `fs.file-max=100000`
- Créer les répertoires : `/opt/{{ project_name }}/{configs,data,backups,logs}`

#### 1.2 Rôle `hardening`
- SSH : port custom `{{ prod_ssh_port }}`, `ListenAddress {{ vpn_headscale_ip }}`, disable root/password auth
- Fail2ban : jail SSH, bantime 3600, maxretry 3
- CrowdSec : install + collections linux/sshd/http-cve
- UFW : deny all incoming, allow 80, 443, `{{ prod_ssh_port }}` from `{{ vpn_network_cidr }}`, 41641/udp
- Unattended-upgrades : security only, auto-reboot disabled, email notification
- Auditd : basic rules pour les commandes sudo

#### 1.3 Rôle `docker`
- Installer Docker CE depuis le repo officiel (pas snap)
- Docker Compose plugin (V2)
- `daemon.json` avec log rotation (10m, 3 fichiers), overlay2, live-restore
- Ajouter `{{ prod_user }}` au groupe docker
- Créer les 4 réseaux Docker : frontend, backend, monitoring, egress (voir TECHNICAL-SPEC section 2.2-2.4)
- Script de cleanup : `docker system prune --volumes -f` en cron hebdomadaire

#### 1.4 Rôle `headscale-node`
- Installer Tailscale client
- Enregistrer le node auprès du serveur Headscale `{{ vpn_headscale_url }}`
- Utiliser `{{ headscale_auth_key }}` pour l'authentification
- Configurer les routes advertise si nécessaire
- Vérifier la connectivité VPN (ping du serveur VPN)
- Sauvegarder l'IP Headscale attribuée dans un fact pour les autres rôles

### Checkpoint Review Phase 1

```
Opus 4.6 — Checklist de review :
- [ ] Chaque rôle a : tasks/, handlers/, defaults/, templates/, meta/, molecule/, README.md
- [ ] Tous les modules utilisent FQCN (ansible.builtin.*, community.general.*)
- [ ] Variables wizard correctement référencées (pas de valeurs hardcodées)
- [ ] SSH bind sur IP Headscale, pas sur 0.0.0.0
- [ ] UFW autorise le réseau VPN ({{ vpn_network_cidr }})
- [ ] daemon.json a log rotation
- [ ] 4 réseaux Docker créés (frontend, backend internal, monitoring internal, egress)
- [ ] Molecule test converge sans erreur pour chaque rôle
- [ ] Idempotence : 2ème run = 0 changed
```

---

## Phase 2 — Données & Reverse Proxy (Rôles 5-8)

### Contexte
La couche données et le point d'entrée réseau. PostgreSQL, Redis, Qdrant stockent tout. Caddy route tout.

### Tâches

#### 2.1 Rôle `caddy`
- Déployer Caddy `{{ caddy_image }}` sur le réseau frontend + backend
- Caddyfile templatisé avec :
  - TLS automatique (Let's Encrypt / ZeroSSL)
  - Security headers (HSTS, X-Content-Type-Options, X-Frame-Options)
  - Snippet `vpn_only` : ACL sur `{{ vpn_network_cidr }}`
  - Rate limiting global : 100 req/min par IP
  - Route publique : `/health` (200 OK), `/litellm/*` (API key auth)
  - Route VPN-only : `admin.{{ domain_name }}` → n8n, Grafana, OpenClaw, Qdrant
- Volume persistant pour les certificats TLS : `/opt/{{ project_name }}/data/caddy/`
- Healthcheck Docker

#### 2.2 Rôle `postgresql`
- Déployer PostgreSQL `{{ postgresql_image }}` sur le réseau backend uniquement
- Init script : créer 3 bases (n8n, openclaw, litellm) + users + extensions (uuid-ossp, vector)
- pg_hba.conf : auth md5, connexions depuis backend network uniquement
- Tuning mémoire (adapté 8GB prod / 4GB preprod) :
  - `shared_buffers` : 256MB (prod) / 128MB (preprod)
  - `effective_cache_size` : 512MB / 256MB
  - `work_mem` : 16MB / 8MB
  - `maintenance_work_mem` : 128MB / 64MB
- Volume persistant : `/opt/{{ project_name }}/data/postgresql/`
- Healthcheck : `pg_isready`
- Limites Docker : voir TECHNICAL-SPEC section 2.5

#### 2.3 Rôle `redis`
- Déployer Redis `{{ redis_image }}` sur le réseau backend uniquement
- Configuration :
  - `requirepass {{ redis_password }}`
  - `maxmemory {{ '384mb' if target_env == 'prod' else '192mb' }}`
  - `maxmemory-policy allkeys-lru`
  - `save 900 1` + `save 300 10` (persistence RDB)
  - `io-threads 2` (Redis 8.0 feature)
- Volume persistant : `/opt/{{ project_name }}/data/redis/`
- Healthcheck : `redis-cli ping`

#### 2.4 Rôle `qdrant`
- Déployer Qdrant `{{ qdrant_image }}` sur le réseau backend uniquement
- Configuration :
  - API key : `{{ qdrant_api_key }}`
  - Storage path : `/opt/{{ project_name }}/data/qdrant/`
  - HNSW index optimisé pour les embeddings (dim 1536 pour text-embedding-3-small)
- Volume persistant
- Healthcheck : `wget -qO- http://localhost:6333/healthz`

### Checkpoint Review Phase 2

```
Opus 4.6 — Checklist de review :
- [ ] Caddy écoute uniquement sur frontend + backend
- [ ] ACL VPN fonctionne (admin.* inaccessible sans VPN)
- [ ] PostgreSQL : 3 bases créées, extensions installées, tuning adapté à l'env
- [ ] PostgreSQL : pg_hba.conf n'autorise que le réseau backend Docker
- [ ] Redis : mot de passe requis, maxmemory configuré, persistence RDB
- [ ] Qdrant : API key configurée, pas exposé publiquement
- [ ] Tous les volumes persistants dans /opt/{{ project_name }}/data/
- [ ] Tous les services sur le réseau backend (internal: true)
- [ ] Healthchecks Docker configurés pour chaque service
- [ ] Ordre de démarrage respecté (données avant apps)
```

---

## Phase 3 — Applications (Rôles 9-11)

### Contexte
Le cœur de la stack : n8n (automatisation), OpenClaw (agents AI), LiteLLM (proxy LLM).

### Tâches

#### 3.1 Rôle `n8n`
- Déployer n8n `{{ n8n_image }}` sur les réseaux backend + egress
- Configuration complète (voir TECHNICAL-SPEC section 4.2) :
  - DB PostgreSQL, encryption key, webhook URL
  - Task runners enabled (v2.0 security)
  - Execution data pruning (7 jours)
  - Basic auth pour l'accès editor
- Volume : `/opt/{{ project_name }}/data/n8n/`
- Dépendances : `postgresql: service_healthy`

#### 3.2 Rôle `litellm`
- Déployer LiteLLM `{{ litellm_image }}` sur les réseaux backend + egress
- Configuration (voir TECHNICAL-SPEC section 4.1) :
  - Routes modèles : Claude Sonnet, Claude Haiku, GPT-4o, GPT-4o-mini
  - Fallback : Claude → GPT-4o
  - Cache Redis
  - Master key auth
  - DB PostgreSQL pour les logs et budgets
  - Alerting webhook
- Variables d'environnement pour les API keys providers (Anthropic, OpenAI)
- Dépendances : `postgresql: service_healthy`, `redis: service_healthy`

#### 3.3 Rôle `openclaw`
- Déployer OpenClaw `{{ openclaw_image }}` sur les réseaux backend + egress
- Configuration (voir TECHNICAL-SPEC section 4.3) :
  - DB PostgreSQL, Redis, Qdrant
  - LiteLLM comme proxy LLM (pas d'appel direct aux providers)
  - Default model : claude-sonnet via LiteLLM
  - API key auth
- Dépendances : `postgresql: service_healthy`, `redis: service_healthy`, `qdrant: service_healthy`

### Checkpoint Review Phase 3

```
Opus 4.6 — Checklist de review :
- [ ] n8n : webhook URL correct, encryption key non vide, basic auth actif
- [ ] n8n : task runners enabled (security v2.0)
- [ ] LiteLLM : toutes les routes modèles définies, fallback configuré
- [ ] LiteLLM : cache Redis connecté, DB PostgreSQL connectée
- [ ] LiteLLM : master key requise pour toute requête API
- [ ] OpenClaw : communique avec LiteLLM (pas directement OpenAI/Anthropic)
- [ ] Les 3 apps sont sur backend + egress (pas frontend)
- [ ] Caddy reverse proxy vers les 3 apps fonctionne
- [ ] API keys providers dans Ansible Vault, jamais en clair
- [ ] Limites mémoire Docker respectées
```

---

## Phase 4 — Observabilité (Rôle 12-13)

### Contexte
Monitoring complet : métriques (VictoriaMetrics), logs (Loki), collection (Alloy), visualisation (Grafana), alertes image (DIUN).

### Tâches

#### 4.1 Rôle `monitoring`
- **VictoriaMetrics** `{{ victoriametrics_image }}` sur réseau monitoring
  - Retention : 30 jours
  - Scrape config via Alloy (pas de config Prometheus directe)

- **Loki** `{{ loki_image }}` sur réseau monitoring
  - Log driver Docker → Alloy → Loki
  - Retention : 14 jours
  - Stockage local (pas S3 pour Day 1)

- **Grafana Alloy** `{{ alloy_image }}` sur réseaux backend + monitoring
  - Scrape métriques de tous les containers (cadvisor, node_exporter intégré)
  - Collect logs Docker de tous les containers
  - Remote write → VictoriaMetrics
  - Push logs → Loki
  - Config Alloy en HCL (pas YAML Prometheus)

- **Grafana** `{{ grafana_image }}` sur réseaux frontend + monitoring
  - Datasources préconfigurées : VictoriaMetrics + Loki
  - Admin password : `{{ grafana_admin_password }}`
  - Dashboards provisionnés (voir TECHNICAL-SPEC section 4.5) :
    - System Overview
    - Docker Containers
    - LiteLLM Proxy (requests, latency, cost)
    - PostgreSQL
    - Logs Explorer
  - Alerting rules :
    - CPU > 80% pendant 5 min
    - RAM > 85% pendant 5 min
    - Disk > 90%
    - Container restart > 3 en 15 min
    - n8n execution errors > 5/min

#### 4.2 Rôle `diun`
- Déployer DIUN `{{ diun_image }}`
- Accès au Docker socket (read-only)
- Watch schedule : toutes les 6 heures
- Watch by default : true (tous les containers)
- Notification : `{{ notification_method }}` webhook
- Labels `diun.include_tags` pour filtrer les patterns de version

### Checkpoint Review Phase 4

```
Opus 4.6 — Checklist de review :
- [ ] VictoriaMetrics reçoit des métriques (vérifier /api/v1/query)
- [ ] Loki reçoit des logs (vérifier /loki/api/v1/query)
- [ ] Alloy config en HCL, scrape tous les containers
- [ ] Grafana : datasources auto-provisionnées (pas de config manuelle)
- [ ] Grafana : au moins 5 dashboards provisionnés en JSON
- [ ] Grafana : alerting rules configurées avec seuils
- [ ] DIUN : Docker socket monté en read-only
- [ ] DIUN : notification webhook fonctionnel
- [ ] Monitoring réseau isolé (internal: true)
- [ ] Alloy bridge correctement backend ↔ monitoring
```

---

## Phase 5 — Backup, Monitoring Externe & Smoke Tests (Rôles 14-16)

### Contexte
La couche résilience : backup via Zerobyte (Seko-VPN), monitoring externe via Uptime Kuma (Seko-VPN), tests de validation.

### Tâches

#### 5.1 Rôle `backup-config`
- **Sur Seko-AI** (production) :
  - Créer `/opt/{{ project_name }}/backups/{pg_dump,redis,qdrant,n8n,grafana}/`
  - Déployer le script `pre-backup.sh` (voir TECHNICAL-SPEC section 5.4)
  - Cron à 02:55 : exécute pre-backup.sh avant le job Zerobyte de 03:00
  - Heartbeat : après succès, ping l'URL push Uptime Kuma

- **Documentation Zerobyte** (config manuelle sur Seko-VPN, documenter dans RUNBOOK.md) :
  - Créer les volumes dans Zerobyte UI (NFS/SSH mounts via VPN)
  - Créer le repository S3 (Hetzner Object Storage)
  - Créer les 6 jobs de backup avec schedules et rétention
  - Tester un backup + restore complet

#### 5.2 Rôle `uptime-config`
- **Documentation Uptime Kuma** (config manuelle sur Seko-VPN, documenter dans RUNBOOK.md) :
  - 6 monitors à créer (voir TECHNICAL-SPEC section 6.1)
  - Notification group liée au webhook
  - Status page optionnelle

#### 5.3 Rôle `smoke-tests`
- Script `smoke-test.sh` (voir TECHNICAL-SPEC section 7.2)
- Vérifications :
  - HTTPS endpoint principal (200)
  - n8n healthz (200)
  - Grafana health (200)
  - LiteLLM health (200) + model list
  - PostgreSQL connectivity (via pg_isready dans le container)
  - Redis connectivity (via redis-cli ping)
  - Qdrant health (200)
  - DNS resolution correcte
  - TLS certificat valide et non expiré
- Playbook Ansible `smoke-tests.yml` qui exécute le script et report les résultats
- Peut être appelé depuis GitHub Actions (CI/CD)

### Checkpoint Review Phase 5

```
Opus 4.6 — Checklist de review :
- [ ] pre-backup.sh : pg_dump, redis save, qdrant snapshot, n8n export
- [ ] pre-backup.sh : set -euo pipefail, gestion erreurs
- [ ] Cron pre-backup à 02:55, avant Zerobyte à 03:00
- [ ] Heartbeat ping Uptime Kuma après backup réussi
- [ ] RUNBOOK.md : procédure complète Zerobyte (volumes, repo S3, jobs)
- [ ] RUNBOOK.md : procédure complète Uptime Kuma (6 monitors)
- [ ] Smoke tests couvrent tous les services critiques
- [ ] Smoke tests avec exit code correct (0 = succès, 1 = échec)
- [ ] GitHub Actions appelle smoke-tests en post-deploy
```

---

## Phase 6 — CI/CD, Documentation & Polish

### Contexte
Finalisation : pipeline GitHub Actions complet, documentation opérationnelle, polish global.

### Tâches

#### 6.1 CI/CD Pipeline
- `.github/workflows/ci.yml` : yamllint + ansible-lint sur chaque push
- `.github/workflows/deploy-preprod.yml` : voir TECHNICAL-SPEC section 7.1
- `.github/workflows/deploy-prod.yml` : déploiement manuel (workflow_dispatch) avec confirmation
- Secrets GitHub à documenter :
  - `ANSIBLE_VAULT_PASSWORD`
  - `HETZNER_CLOUD_TOKEN`
  - `SSH_PRIVATE_KEY`
  - `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY`

#### 6.2 Documentation
- `README.md` : Quick start, architecture overview, wizard instructions
- `docs/RUNBOOK.md` : Procédures opérationnelles
  - Démarrage/arrêt de la stack
  - Mise à jour d'un service
  - Ajout d'un nouveau modèle LiteLLM
  - Restauration depuis backup
  - Rotation des secrets
  - Gestion des incidents
- `docs/ARCHITECTURE.md` : Diagrammes (Mermaid) des réseaux, flux, composants
- `docs/DISASTER-RECOVERY.md` : Plan de reprise d'activité
  - Scénario 1 : Container crash → restart automatique
  - Scénario 2 : VPS down → restore depuis snapshot + S3
  - Scénario 3 : Corruption DB → restore pg_dump depuis Zerobyte
  - Scénario 4 : Compromission → isoler via VPN, rotate tous les secrets, redeploy

#### 6.3 Playbooks Utilitaires
- `playbooks/rollback.yml` : Rollback rapide à la version N-1 (via versions_previous.yml)
- `playbooks/backup-restore.yml` : Restauration complète depuis S3
- `playbooks/rotate-secrets.yml` : Rotation de tous les mots de passe et clés
- `playbooks/update-single.yml` : Mise à jour d'un service unique (ex: `--tags n8n`)

#### 6.4 Polish
- `.yamllint.yml` : Config stricte
- `.ansible-lint` : Config avec skip list minimale
- `ansible.cfg` : Optimisé (pipelining, ControlMaster, forks=10, callback_whitelist=profile_tasks)
- `Makefile` : Raccourcis (`make lint`, `make test`, `make deploy-preprod`, `make deploy-prod`)
- Tags Ansible sur chaque rôle pour déploiement sélectif

### Checkpoint Review Phase 6 — FINAL

```
Opus 4.6 — Checklist de review FINALE :
- [ ] `ansible-playbook site.yml --check` passe sans erreur
- [ ] `ansible-lint` : 0 warnings (ou skip list justifié)
- [ ] `yamllint` : 0 erreurs
- [ ] Molecule tests passent pour les 16 rôles
- [ ] CI pipeline (lint + molecule) vert
- [ ] Toutes les variables wizard dans defaults/main.yml avec valeurs par défaut sensées
- [ ] Aucun secret en clair (tout dans Ansible Vault)
- [ ] Aucune image :latest ou :stable (tout pinné dans versions.yml)
- [ ] README.md à jour avec instructions complètes
- [ ] RUNBOOK.md couvre tous les scénarios opérationnels
- [ ] DISASTER-RECOVERY.md avec 4 scénarios
- [ ] Makefile fonctionnel
- [ ] .github/workflows/ complets (ci + preprod + prod)
- [ ] Smoke tests couvrent tous les services
- [ ] Template portable : `grep -r 'seko\|Seko' .` ne renvoie que des variables
```

---

## Résumé des Phases

| Phase | Rôles | Effort estimé | Checkpoint |
|-------|-------|--------------|------------|
| 1 — Fondations | common, hardening, docker, headscale-node | 4-6h | Security + Docker setup |
| 2 — Données & Proxy | caddy, postgresql, redis, qdrant | 4-6h | Data layer + routing |
| 3 — Applications | n8n, openclaw, litellm | 4-6h | App connectivity |
| 4 — Observabilité | monitoring, diun | 4-6h | Metrics + logs + alerts |
| 5 — Résilience | backup-config, uptime-config, smoke-tests | 3-4h | Backup + monitoring externe |
| 6 — CI/CD & Docs | workflows, docs, polish | 3-4h | **Review finale** |

**Total estimé** : 22-32 heures de développement Claude Code.

---

## Notes pour l'Opérateur

### Avant de lancer Claude Code
1. Créer le repository Git vide
2. Copier `PRD.md` et `TECHNICAL-SPEC.md` à la racine
3. Remplir le wizard dans `PRD.md` section 2 avec vos valeurs
4. Initialiser Ansible Vault : `ansible-vault create inventory/group_vars/all/secrets.yml`

### Workflow de développement
1. Donner ce Golden Prompt à Claude Code avec le contexte du PRD + TECHNICAL-SPEC
2. Claude Code développe une phase complète
3. Copier le résultat dans un chat Opus 4.6 avec la checklist de review correspondante
4. Itérer si nécessaire
5. Passer à la phase suivante

### Après le développement
1. Exécuter `make lint` et `make test` en local
2. Push sur GitHub → CI verte
3. `make deploy-preprod` → Soak 48h
4. `make deploy-prod` → Monitoring 24h
5. Configurer manuellement Zerobyte et Uptime Kuma sur Seko-VPN (suivre RUNBOOK.md)

---

*Fin du Golden Prompt — Prêt pour le développement.*
