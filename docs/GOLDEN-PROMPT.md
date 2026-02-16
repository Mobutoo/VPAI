# Golden Prompt — Développement Complet de la Stack AI Self-Hosted

> **Version** : 2.0.0
> **Date** : 11 février 2026
> **Usage** : Copier-coller ce prompt dans Claude Code pour lancer le développement.
> **Workflow** : Claude Code exécute → Opus 4.6 review → itération si nécessaire.
> **Changelog v2** : Intégration du REX (retour d'expérience) — toutes les erreurs rencontrées lors du premier développement sont documentées et les gardes-fous ajoutés pour un résultat propre en one-shot.

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

### Règles qualité fichiers (REX v2 — CRITIQUES)

> **Ces règles ont été découvertes lors du premier développement. Les ignorer causera des échecs de `make lint`.**

9. **Encodage UTF-8 + LF obligatoire** : Tous les fichiers `.yml`, `.j2`, `.sh` doivent être en UTF-8 avec fins de ligne LF (Unix). Jamais de CRLF (Windows) ni de Windows-1252. Le tiret long `—` (em dash, U+2014) est le piège principal : s'assurer qu'il est bien encodé en UTF-8 (3 bytes: `E2 80 94`) et pas en Windows-1252 (1 byte: `0x97`).
10. **`name[template]` ansible-lint** : Dans le champ `name:` d'un play Ansible, les expressions Jinja2 `{{ }}` doivent être **à la fin** de la chaîne. Écrire `"Deploy Full Stack — {{ project_display_name }}"` et non `"Deploy {{ project_display_name }} — Full Stack"`.
11. **`role_name` dans meta/main.yml** : Doit correspondre au pattern `^[a-z][a-z0-9_]+$`. Utiliser des underscores (`headscale_node`) même si le dossier a un tiret (`headscale-node/`).
12. **Alloy en HCL** : Grafana Alloy utilise le format HCL (HashiCorp Configuration Language), pas YAML. Monter `/proc:/host/proc:ro` et `/sys:/host/sys:ro` pour les métriques node_exporter.
13. **DIUN via fichier config** : Préférer un template `diun.yml.j2` monté dans le container plutôt que des variables d'environnement — plus lisible et flexible.
14. **Makefile lint** : Ne jamais utiliser `yamllint .` directement. Utiliser `find` avec exclusions (`! -name 'secrets.yml'`, `! -path './.venv/*'`) et `xargs`. Grouper les `-o` dans find avec `\( ... \)`.

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

---

## REX — Retour d'Expérience du Premier Développement

> **Objectif** : Documenter chaque erreur rencontrée lors du développement initial pour qu'un redéploiement from scratch produise un résultat propre en one-shot, avec `make lint` vert du premier coup.

### Erreur 1 — Encodage Windows-1252 au lieu de UTF-8

**Symptôme** : `make lint` crash avec `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position 13`

**Cause racine** : 18 fichiers YAML des phases 1-3 (roles redis, openclaw, n8n, postgresql, litellm, qdrant — tasks, defaults, handlers de chacun) contenaient le caractère em dash `—` encodé en Windows-1252 (byte `0x97`) au lieu d'UTF-8 (bytes `E2 80 94`). Cela venait de l'environnement d'édition WSL/Windows.

**Fix** :
```bash
python3 -c "
import glob
for f in glob.glob('roles/*/tasks/main.yml') + glob.glob('roles/*/defaults/main.yml') + glob.glob('roles/*/handlers/main.yml'):
    data = open(f, 'rb').read()
    if b'\x97' in data:
        open(f, 'wb').write(data.decode('windows-1252').encode('utf-8'))
"
```

**Garde-fou** : Après création de chaque fichier, vérifier avec `file <path>` qu'il indique `UTF-8 Unicode text` et pas `ISO-8859` ou `Non-ISO extended-ASCII`.

### Erreur 2 — Fins de ligne CRLF au lieu de LF

**Symptôme** : yamllint signale `wrong new line character: expected \n` sur la ligne 1 de 25+ fichiers

**Cause racine** : Les fichiers créés depuis un environnement Windows/WSL avaient des fins de ligne CRLF (`\r\n`). yamllint n'accepte que LF (`\n`).

**Fix** :
```bash
find roles/ -name '*.yml' -exec sed -i 's/\r$//' {} \;
```

**Garde-fou** : Configurer `.editorconfig` avec `end_of_line = lf` (déjà fait). Lors de l'écriture de fichiers, toujours vérifier l'absence de `\r`.

### Erreur 3 — `playbooks_dir` déprécié dans ansible-lint 26.x

**Symptôme** : `Invalid configuration file .ansible-lint. Additional properties are not allowed ('playbooks_dir' was unexpected)`

**Cause racine** : La propriété `playbooks_dir` a été supprimée dans ansible-lint 26.x. La configuration initiale l'incluait.

**Fix** : Supprimer la ligne `playbooks_dir: playbooks/` de `.ansible-lint`.

**Garde-fou** : Ne pas utiliser `playbooks_dir` dans `.ansible-lint`. Utiliser la section `kinds:` pour le mapping des fichiers.

### Erreur 4 — ansible-lint syntax-check sans inventaire

**Symptôme** : `syntax-check: Error processing keyword 'name': 'project_display_name' is undefined`

**Cause racine** : ansible-lint exécute `ansible-playbook --syntax-check` sans charger l'inventaire. Les variables comme `project_display_name` ne sont pas disponibles.

**Fix** : Ajouter `extra_vars` dans `.ansible-lint` :
```yaml
extra_vars:
  project_display_name: "VPAI"
  target_env: "prod"
```

**Garde-fou** : Toujours inclure les variables utilisées dans les `name:` des plays dans `extra_vars` de `.ansible-lint`.

### Erreur 5 — Galaxy server non configuré

**Symptôme** : `ERROR: Required config 'url' for 'galaxy' galaxy_server plugin not provided`

**Cause racine** : ansible-lint tente d'installer les dépendances Galaxy au démarrage. Sans configuration Galaxy, cela échoue.

**Fix** : Ajouter `offline: true` dans `.ansible-lint`.

**Garde-fou** : Toujours mettre `offline: true` dans `.ansible-lint` pour un développement local sans Galaxy.

### Erreur 6 — name[template] : Jinja2 pas à la fin du name

**Symptôme** : `name[template]: Jinja templates should only be at the end of 'name'`

**Cause racine** : Le play principal avait `name: "Deploy {{ project_display_name }} — Full Stack"`. ansible-lint exige que les templates Jinja2 soient en fin de chaîne.

**Fix** : Inverser → `name: "Deploy Full Stack — {{ project_display_name }}"`.

**Garde-fou** : Toujours placer les `{{ }}` à la fin des champs `name:` des plays et tâches.

### Erreur 7 — schema[meta] : tiret dans role_name

**Symptôme** : `schema[meta]: $.galaxy_info.role_name 'headscale-node' does not match '^[a-z][a-z0-9_]+$'`

**Cause racine** : Le role_name Galaxy n'accepte pas les tirets, seulement les underscores.

**Fix** : Mettre `role_name: headscale_node` dans `meta/main.yml` (le dossier garde `headscale-node/`).

**Garde-fou** : Pour tous les rôles avec tiret dans le nom de dossier (`backup-config`, `smoke-tests`, `uptime-config`, `headscale-node`), utiliser un underscore dans `role_name` du meta.

### Erreur 8 — yamllint octal-values non configuré

**Symptôme** : `WARNING Found incompatible custom yamllint configuration (.yamllint.yml), please either remove the file or edit it to comply with: octal-values.forbid-implicit-octal must be true`

**Cause racine** : ansible-lint exige des règles octal-values dans la config yamllint pour éviter les ambiguïtés YAML (ex: `0777` interprété comme entier octal).

**Fix** : Ajouter dans `.yamllint.yml` :
```yaml
  octal-values:
    forbid-implicit-octal: true
    forbid-explicit-octal: true
```

**Garde-fou** : Toujours inclure cette section dans `.yamllint.yml` dès le départ.

### Erreur 9 — Makefile `yamllint .` sur fichier Vault chiffré

**Symptôme** : `UnicodeDecodeError` sur `secrets.yml` qui est chiffré avec Ansible Vault (header `$ANSIBLE_VAULT;1.1;AES256`)

**Cause racine** : `yamllint .` parcourt tous les fichiers YAML, y compris le vault chiffré qui contient des bytes non-UTF-8. La directive `ignore` de `.yamllint.yml` ne protège pas contre ce crash car yamllint tente de lire le fichier avant de vérifier les ignores.

**Fix** : Remplacer `yamllint .` par un `find` avec `! -name 'secrets.yml'` :
```makefile
find . \( -name '*.yml' -o -name '*.yaml' \) \
  ! -path './.git/*' ! -path './.venv/*' \
  ! -path '*/molecule/*' ! -path '*/collections/*' \
  ! -name 'secrets.yml' -print0 | xargs -0 yamllint -c .yamllint.yml
```

**Garde-fou** : Ne jamais utiliser `yamllint .` ou `yamllint <dir>`. Toujours passer par `find | xargs`.

### Checklist Pré-Lint (à exécuter avant `make lint`)

```bash
# 1. Vérifier encodage UTF-8 (pas de ISO-8859 ni Windows-1252)
find roles/ templates/ playbooks/ inventory/ -name '*.yml' -o -name '*.j2' | \
  xargs file | grep -v 'UTF-8\|ASCII'
# → Doit être VIDE. Si des fichiers apparaissent, les re-encoder.

# 2. Vérifier fins de ligne LF (pas de CRLF)
find roles/ templates/ playbooks/ inventory/ -name '*.yml' -o -name '*.j2' | \
  xargs file | grep 'CRLF'
# → Doit être VIDE. Si des fichiers apparaissent : sed -i 's/\r$//' <file>

# 3. Vérifier absence de :latest
grep -r ':latest\|:stable' inventory/group_vars/all/versions.yml
# → Doit être VIDE.

# 4. Vérifier les role_name dans meta (pas de tirets)
grep -r 'role_name:.*-' roles/*/meta/main.yml
# → Doit être VIDE.

# 5. Vérifier les name[template] (Jinja2 pas au début/milieu)
grep -rn 'name:.*{{.*}}.*[a-zA-Z]' playbooks/*.yml
# → Doit être VIDE (pas de texte APRÈS les {{ }}).
```

---

## Fichiers de Configuration de Référence

### `.ansible-lint` (version validée)

```yaml
---
profile: production
strict: true

enable_list:
  - fqcn
  - no-changed-when
  - no-handler
  - yaml

skip_list:
  - galaxy[no-changelog]

warn_list:
  - experimental
  - role-name[path]

exclude_paths:
  - .github/
  - .venv/
  - collections/
  - molecule/

offline: true

extra_vars:
  project_display_name: "VPAI"
  target_env: "prod"

use_default_rules: true

kinds:
  - playbook: "playbooks/*.yml"
  - tasks: "roles/*/tasks/*.yml"
  - handlers: "roles/*/handlers/*.yml"
  - vars: "roles/*/vars/*.yml"
  - defaults: "roles/*/defaults/*.yml"
  - meta: "roles/*/meta/*.yml"
```

### `.yamllint.yml` (version validée)

```yaml
---
extends: default

rules:
  line-length:
    max: 160
    level: warning
  truthy:
    allowed-values: ['true', 'false', 'yes', 'no']
  comments:
    min-spaces-from-content: 1
  comments-indentation: disable
  document-start: disable
  octal-values:
    forbid-implicit-octal: true
    forbid-explicit-octal: true
  braces:
    max-spaces-inside: 1
  brackets:
    max-spaces-inside: 1
  indentation:
    spaces: 2
    indent-sequences: consistent

ignore: |
  .github/
  molecule/
  .venv/
  collections/
  roles/*/molecule/
  inventory/group_vars/all/secrets.yml
```

---

### Erreur 10 — apt_key deprecie sur Debian 13

**Symptome** : `apt_key` module fonctionne mais genere des warnings sur Debian 13 (Trixie). CrowdSec installe mais le repo n'est pas signe correctement → packages non verifies.

**Cause racine** : Le module `ansible.builtin.apt_key` ajoute les cles dans le trousseau global `/etc/apt/trusted.gpg.d/`, ce qui est deprecie depuis Debian 12 et ignore sur certaines installations Debian 13 minimales.

**Fix** : Remplacer `apt_key` par le pattern `gpg --dearmor` + `signed-by=` :
```bash
# Telecharger et convertir la cle
curl -fsSL <KEY_URL> | gpg --dearmor --yes -o /etc/apt/keyrings/<service>.gpg

# Utiliser signed-by dans le repo
deb [arch=amd64 signed-by=/etc/apt/keyrings/<service>.gpg] <REPO_URL> <SUITE> main
```

**Garde-fou** : `grep -r 'apt_key' roles/` doit renvoyer **rien**. Tous les repos tiers doivent utiliser `/etc/apt/keyrings/` + `signed-by=`.

### Erreur 11 — dash vs bash sur Debian 13

**Symptome** : Les taches `shell` avec `set -o pipefail` echouent avec `set: Illegal option -o pipefail` sur Debian 13.

**Cause racine** : Debian 13 utilise `dash` comme `/bin/sh` par defaut. `dash` ne supporte pas `set -o pipefail` ni certains bashismes. Ansible utilise `/bin/sh` par defaut pour les taches `shell`.

**Fix** : Ajouter `executable: /bin/bash` a toutes les taches `ansible.builtin.shell` qui utilisent des pipes ou `set -o pipefail` :
```yaml
- name: Example task with pipe
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: |
      set -o pipefail
      curl -fsSL url | gpg --dearmor -o /path/to/key.gpg
```

**Garde-fou** : Auditer avec `grep -r 'ansible.builtin.shell' roles/ -A5 | grep -v 'executable'` — toute tache shell avec un pipe doit avoir `executable: /bin/bash`.

### Erreur 12 — Depots Debian 13 incomplets sur images minimales

**Symptome** : `apt install gnupg` echoue avec `Unable to locate package gnupg` sur un VPS Debian 13 fraichement provisionne (IONOS, Hetzner, OVH).

**Cause racine** : Les images minimales de certains hebergeurs n'incluent que le depot `main` sans `contrib` ni `non-free`. Parfois meme le depot `security` est absent.

**Fix** : Ajouter une verification et correction des depots en tete du role `common` :
```yaml
- name: Check Debian repos completeness
  ansible.builtin.command:
    cmd: apt-cache policy gnupg
  changed_when: false
  failed_when: false
  register: common_repo_check

- name: Fix Debian 13 minimal repos if needed
  ansible.builtin.copy:
    dest: /etc/apt/sources.list.d/debian.sources
    content: |
      Types: deb
      URIs: http://deb.debian.org/debian
      Suites: trixie trixie-updates
      Components: main contrib non-free non-free-firmware
      Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
    mode: "0644"
  when: common_repo_check.rc != 0 or 'Candidate: (none)' in common_repo_check.stdout
```

**Garde-fou** : Le role `common` doit toujours verifier les depots AVANT le premier `apt update`.

### Erreur 13 — Paquets obsoletes sur Debian 13

**Symptome** : `apt install apt-transport-https` genere un warning ou echoue car le paquet n'existe plus dans Debian 13.

**Cause racine** : `apt-transport-https` a ete integre dans APT depuis Debian 10 (Buster). De meme, `software-properties-common` n'a pas d'utilite sans PPA Ubuntu.

**Fix** : Retirer ces paquets de la liste d'installation dans `roles/common/defaults/main.yml`. S'assurer que `gnupg` est present (necessaire pour `gpg --dearmor`).

**Garde-fou** : Ne pas inclure `apt-transport-https` ni `software-properties-common` dans les paquets a installer sur Debian 12+.

### Erreur 14 -- PostgreSQL ICU Locale dans Docker

**Symptome** : `initdb: error: invalid locale name "fr_FR.UTF-8"`

**Cause racine** : L'image Docker `postgres:18.1-bookworm` n'a PAS les locales systeme installees (pas de `fr_FR.UTF-8`). Le `POSTGRES_INITDB_ARGS` utilisait `--locale=fr_FR.UTF-8` qui n'existe pas.

**Fix** : Utiliser le provider ICU (independant des locales systeme) :
```yaml
POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale-provider=icu --icu-locale=fr-FR --locale=C"
```

**Garde-fou** : Ne JAMAIS utiliser `--locale=xx_XX.UTF-8` dans les images Docker PostgreSQL. Toujours utiliser `--locale-provider=icu` avec `--icu-locale`.

### Erreur 15 -- PostgreSQL logging_collector dans Docker

**Symptome** : PostgreSQL crash loop avec `logging_collector = on`

**Cause racine** : `logging_collector = on` tente d'ecrire dans `/var/log/postgresql/` qui n'existe pas dans le conteneur Docker. Docker capte deja stdout/stderr.

**Fix** : `logging_collector = off` dans postgresql.conf.j2

**Garde-fou** : Ne JAMAIS activer `logging_collector` dans un conteneur Docker.

### Erreur 16 -- Qdrant PermissionDenied avec cap_drop ALL

**Symptome** : `Failed to remove snapshots temp directory at ./snapshots/tmp: PermissionDenied`

**Cause racine** : `cap_drop: ALL` retire `DAC_OVERRIDE`. Meme si l'UID du conteneur (1000) matche le proprietaire des fichiers, certaines operations de fichier necessitent `DAC_OVERRIDE`.

**Fix** :
```yaml
cap_add:
  - CHOWN
  - SETGID
  - SETUID
  - DAC_OVERRIDE
  - FOWNER
```

**Garde-fou** : Tout conteneur qui ecrit dans des volumes montes avec `cap_drop: ALL` a quasi-certainement besoin de `DAC_OVERRIDE`. Tester systematiquement.

### Erreur 17 -- Qdrant image sans wget/curl

**Symptome** : `exec: "wget": executable file not found in $PATH`

**Cause racine** : L'image Qdrant v1.16.3 est minimale -- ni `wget`, ni `curl`, ni `nc`.

**Fix** : Healthcheck via bash :
```yaml
healthcheck:
  test: ["CMD-SHELL", "bash -c ':> /dev/tcp/localhost/6333' || exit 1"]
```

**Garde-fou** : Avant d'ecrire un healthcheck, verifier les outils disponibles dans l'image avec `docker exec <container> which wget curl nc`.

### Erreur 18 -- Qdrant config path (production.yaml)

**Symptome** : Qdrant utilise la config par defaut malgre le volume mount

**Cause racine** : Config montee comme `/qdrant/config/config.yaml` mais Qdrant attend `/qdrant/config/production.yaml`.

**Fix** : `- .../config.yaml:/qdrant/config/production.yaml:ro`

**Garde-fou** : Verifier la documentation officielle du conteneur pour le chemin exact du fichier de config.

### Erreur 19 -- Redis 8.0 rename-command supprime

**Symptome** : Redis crash au demarrage avec `rename-command`

**Cause racine** : `rename-command` a ete supprime dans Redis 8.0. Etait deprecated depuis 7.x.

**Fix** : Supprimer `rename-command` du redis.conf. Utiliser les ACL Redis a la place.

**Garde-fou** : `grep -r 'rename-command' roles/redis/` doit renvoyer **rien** sur Redis 8.0+.

### Erreur 20 -- Caddy healthcheck localhost vs domain

**Symptome** : Caddy `(unhealthy)` alors que le service tourne correctement

**Cause racine** : Le healthcheck `wget -qO- http://localhost:80/health` echoue car `/health` est defini dans le bloc domain (`{{ caddy_domain }}`). Le Host header `localhost` ne matche aucun site block Caddy. L'admin API `:2019` ne repond pas non plus en Docker.

**Fix** : Utiliser `caddy version` comme healthcheck (verifie que le binaire est fonctionnel) :
```yaml
healthcheck:
  test: ["CMD", "caddy", "version"]
```

**Garde-fou** : Pour Caddy en Docker, utiliser `caddy version` comme healthcheck. Ni les routes applicatives (probleme de Host header) ni l'admin API (ne repond pas) ne fonctionnent de facon fiable.

### Erreur 21 -- Phase B duplique les services Phase A

**Symptome** : Docker Compose tente de recreer des conteneurs deja running

**Cause racine** : `docker-compose.yml` (Phase B) contenait les definitions completes de PG, Redis, Qdrant et Caddy, identiques a celles de `docker-compose-infra.yml` (Phase A).

**Fix** : Phase B ne contient plus que les services applicatifs (n8n, LiteLLM, OpenClaw, monitoring, DIUN). Pas de duplication.

**Garde-fou** : Un service ne doit apparaitre que dans UN SEUL fichier compose. Verifier avec `grep -h 'container_name:' roles/docker-stack/templates/*.j2 | sort | uniq -d` (doit etre vide).

### Erreur 22 -- Makefile EXTRA_VARS

**Symptome** : `make deploy-prod -e ansible_port_override=804` ne transmet pas la variable

**Cause racine** : Le `-e` de make est un flag make (variables d'environnement), pas un flag Ansible. Le Makefile n'avait pas de mecanisme pour passer des extra-vars.

**Fix** : Ajout de `$(if $(EXTRA_VARS),-e "$(EXTRA_VARS)")` dans le Makefile.

**Garde-fou** : Utiliser `make deploy-prod EXTRA_VARS="key=value"` (pas `-e`).

### Erreur 23 -- IPv6 localhost dans les healthchecks Alpine

**Symptome** : Healthcheck VictoriaMetrics echoue, logs montrent `[::1]:8428`

**Cause racine** : Les images Alpine resolvent `localhost` en IPv6 `::1` alors que les services n'ecoutent que sur IPv4 `0.0.0.0`. Le healthcheck `wget http://localhost:8428/...` tente `[::1]:8428` et echoue.

**Fix** : Utiliser `127.0.0.1` au lieu de `localhost` dans TOUS les healthchecks Docker :
```yaml
healthcheck:
  test: ["CMD-SHELL", "wget --spider http://127.0.0.1:8428/-/healthy || exit 1"]
```

**Garde-fou** : `grep -r 'localhost' roles/docker-stack/templates/*.j2` dans les sections healthcheck doit renvoyer **rien**. Toujours `127.0.0.1`.

### Erreur 24 -- Images distroless sans outils (Loki 3.6+, Alloy)

**Symptome** : `"wget": executable file not found in $PATH` puis `"ls": executable file not found in $PATH`

**Cause racine** : `grafana/loki:3.6.0+` a change d'image de base vers distroless. Plus AUCUN outil shell : pas de wget, curl, ls, test, bash, sh. Meme `test -d /path` echoue.

**Fix** : Utiliser les commandes built-in du binaire principal :
```yaml
# Loki 3.6.5+ : commande -health ajoutee (backport PR #20590)
healthcheck:
  test: ["CMD", "/usr/bin/loki", "-health"]

# Alloy / OpenClaw : verifier que le process PID 1 tourne
healthcheck:
  test: ["CMD-SHELL", "kill -0 1 || exit 1"]

# LiteLLM (Python disponible, pas wget) :
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:4000/health')\" || exit 1"]
```

**Garde-fou** : Avant d'ecrire un healthcheck, tester dans le conteneur : `docker exec <c> which wget curl ls test bash`. Si vide -> image distroless, utiliser la commande du binaire principal.

### Erreur 25 -- Loki 3.x "empty ring" en mode monolithique

**Symptome** : `"error getting ingester clients" err="empty ring"` en boucle

**Cause racine** : Bug Loki #19381 -- le module `memberlist-kv` s'initialise meme avec `kvstore.store: inmemory`. L'ingester ne s'enregistre pas dans le ring car memberlist cherche des interfaces reseau.

**Fix** :
1. Ajouter `-target=all` dans la commande Docker Compose
2. Configurer explicitement `ingester.lifecycler.ring.kvstore.store: inmemory`
3. Ajouter `memberlist.join_members: []` pour desactiver le clustering
```yaml
# docker-compose.yml
command: -config.file=/etc/loki/local-config.yaml -target=all

# loki-config.yaml
memberlist:
  join_members: []
ingester:
  lifecycler:
    ring:
      replication_factor: 1
      kvstore:
        store: inmemory
```

**Garde-fou** : En mode monolithique, toujours specifier `-target=all` ET configurer le ring dans `common` ET `ingester.lifecycler`.

### Erreur 26 -- DNS check avec `dig` non installe

**Symptome** : Smoke test DNS echoue malgre le DNS fonctionnel

**Cause racine** : `dig` (paquet `dnsutils`) n'est pas installe sur les images minimales Debian 13.

**Fix** : Utiliser `getent hosts` (fait partie de glibc, toujours disponible) :
```bash
# Avant (necessite dnsutils)
DNS_RESULT=$(dig +short "domain.tld" | head -1)

# Apres (toujours disponible)
DNS_RESULT=$(getent hosts "domain.tld" | awk '{print $1}' | head -1)
```

**Garde-fou** : Ne jamais utiliser `dig`, `nslookup`, ou `host` dans les scripts de smoke test. Utiliser `getent hosts`.

### Erreur 27 -- Grafana redirect 301 sur /login

**Symptome** : Smoke test Grafana echoue avec HTTP 301 au lieu de 200

**Cause racine** : `/grafana/login` redirige vers `/grafana/login/` (trailing slash). curl sans `-L` retourne 301.

**Fix** : Ajouter `-L` (follow redirects) a curl dans la fonction `check_http()`.

**Garde-fou** : Toujours utiliser `curl -sL` (avec `-L`) dans les smoke tests pour suivre les redirections.

### Erreur 28 -- Handlers infra pointent vers le mauvais compose

**Symptome** : `no such service: caddy` lors du handler restart

**Cause racine** : Les handlers de caddy, postgresql, redis, qdrant pointaient vers `docker-compose.yml` (Phase B) mais ces services sont dans `docker-compose-infra.yml` (Phase A).

**Fix** : Mettre a jour les 4 handlers infra pour utiliser `docker-compose-infra.yml`.

**Garde-fou** : Un handler de restart DOIT pointer vers le fichier compose qui contient le service. Verifier la correspondance handler <-> compose file pour chaque role.

---

*Fin du Golden Prompt -- Pret pour le developpement.*
