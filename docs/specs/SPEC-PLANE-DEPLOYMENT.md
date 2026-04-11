# SPEC — Déploiement Plane (Mission Control)

> **Version** : 1.0.0
> **Date** : 2026-02-28
> **Auteur** : Claude Sonnet 4.6
> **Statut** : ⚠️ DRAFT — En attente de validation humaine

---

## 🎯 Objectif

Déployer **Plane v1.2.2** (self-hosted) comme outil de gestion de projet pour l'équipe Javisi, avec intégration agents OpenClaw.

---

## 📋 Informations Projet (Source Unique de Vérité)

### Identité

```yaml
project_name: "javisi"
project_display_name: "Javisi"
domain_name: "ewutelo.cloud"  # Depuis vault
```

### Infrastructure

```yaml
# VPS Production (Sese-AI)
prod_hostname: "sese"
prod_ip: "137.74.114.167"
prod_ssh_port: 804
prod_user: "mobuone"
prod_os: "debian-13"
prod_ram_gb: 8
prod_cpu_cores: 4

# VPN
vpn_network_cidr: "100.64.0.0/10"
caddy_vpn_enforce: true  # VPN-only par défaut
```

### Domaine & Sous-domaines

```yaml
domain_name: "ewutelo.cloud"
plane_subdomain: "work"     # → work.ewutelo.cloud
plane_api_subdomain: "work-api"  # → work-api.ewutelo.cloud (interne)
```

### Base de Données

```yaml
database: "PostgreSQL 18.1" (partagé)
db_name: "plane"
db_user: "plane"
db_password: "{{ postgresql_password }}"  # Password unique partagé (REX critique)
redis_db: 4  # Redis DB 4 pour Plane (0=default, 1=LiteLLM, 2=n8n, 3=plane-api)
```

---

## 🏗️ Architecture Technique

### Stack Plane

```yaml
Version: "v1.2.2" (latest release 2026-02-23)
Licence: AGPL-3.0
Tech Stack:
  - Frontend: Next.js (React)
  - Backend: Django REST Framework
  - Worker: Celery
  - Database: PostgreSQL 18.1
  - Cache: Redis 8.0
```

### Containers Docker

| Container | Image | Port | Réseaux | Rôle |
|---|---|---|---|---|
| `javisi_plane_web` | `makeplane/plane-frontend:v1.2.2` | 3000 | frontend, backend | UI Next.js |
| `javisi_plane_api` | `makeplane/plane-backend:v1.2.2` | 8000 | backend | API Django REST |
| `javisi_plane_worker` | `makeplane/plane-backend:v1.2.2` | - | backend, egress | Celery worker |

### Réseaux Docker (Existants)

```yaml
frontend: 172.20.1.0/24      # Caddy, Plane Web
backend: 172.20.2.0/24       # Plane API, PostgreSQL, Redis (internal)
egress: 172.20.4.0/24        # Plane Worker (webhooks externes)
```

### Volumes

```yaml
# Plane ne nécessite PAS de volumes persistants (tout en DB)
# Les uploads sont stockés en DB ou S3 (si configuré)
```

---

## 🔐 Sécurité & Conventions

### REX Critiques Applicables

**Depuis `docs/TROUBLESHOOTING.md` et `docs/REX-PALAIS-DEPLOIEMENT-PHASE1.md`** :

1. **PostgreSQL Password Unique** (REX #41)
   ```yaml
   # ✅ TOUS les users DB utilisent postgresql_password
   # ❌ NE JAMAIS créer postgresql_plane_password séparé
   postgresql_password: "{{ vault_postgresql_password }}"
   ```

2. **Handlers env_file** (REX Palais 1.4)
   ```yaml
   # ✅ state: present + recreate: always + build: always
   # ❌ state: restarted (ne recharge PAS env_file)
   ```

3. **Docker Capabilities** (Convention Docker)
   ```yaml
   cap_drop: [ALL]
   cap_add: [CHOWN, SETGID, SETUID]  # Plane Web
   cap_add: [DAC_OVERRIDE, FOWNER]   # Plane API (si write volumes)
   ```

4. **Healthchecks** (REX TECHNICAL-SPEC 8)
   ```yaml
   # Plane API healthcheck
   test: ["CMD", "curl", "-f", "http://localhost:8000/api/health/"]
   interval: 30s
   timeout: 10s
   retries: 3
   ```

5. **Limites Ressources** (TECHNICAL-SPEC 2.5)
   ```yaml
   plane_web:
     mem_limit: 512M
     cpus: 0.5
   plane_api:
     mem_limit: 1G
     cpus: 1.0
   plane_worker:
     mem_limit: 512M
     cpus: 0.5
   ```

6. **VPN-Only Access** (REX Caddy VPN)
   ```caddyfile
   https://plane.{{ domain_name }} {
       import vpn_only  # 2 CIDRs : caddy_vpn_cidr + caddy_docker_frontend_cidr
       reverse_proxy plane-web:3000
   }
   ```

7. **Split DNS** (REX Session 8)
   ```yaml
   # Ajouter plane.ewutelo.cloud dans vpn-dns/defaults/main.yml
   # Format : {name: "plane.{{ domain_name }}", type: "A", value: _vpn_dns_vps_ts_ip}
   ```

8. **Images Pinnées** (Convention Docker)
   ```yaml
   # ❌ :latest, :stable
   # ✅ :v1.2.2 (version exacte dans versions.yml)
   ```

9. **FQCN Ansible** (Convention Ansible)
   ```yaml
   # ✅ ansible.builtin.copy, community.docker.docker_compose_v2
   # ❌ copy, docker_compose
   ```

10. **Idempotence** (Convention Ansible)
    ```yaml
    # 0 changed à la 2ème exécution
    # changed_when / failed_when explicites sur command/shell
    ```

---

## 👥 Utilisateurs Plane

### Humain Admin

```yaml
email: "mobuone@ewutelo.cloud"  # Ou email réel utilisateur
role: "Admin"
first_name: "Mobuone"
display_name: "Mobuone (Human)"
```

### Agents IA (10 users)

| Agent ID | Email | Display Name | Role | Avatar |
|---|---|---|---|---|
| `concierge` | `concierge@agents.javisi.local` | Mobutoo (Concierge AI) | **Admin** | 👔 |
| `builder` | `builder@agents.javisi.local` | Imhotep (Builder AI) | Member | 🏗️ |
| `writer` | `writer@agents.javisi.local` | Thot (Writer AI) | Member | ✍️ |
| `artist` | `artist@agents.javisi.local` | Basquiat (Artist AI) | Member | 🎨 |
| `explorer` | `explorer@agents.javisi.local` | R2D2 (Explorer AI) | Member | 🔍 |
| `tutor` | `tutor@agents.javisi.local` | Piccolo (Tutor AI) | Member | 🎓 |
| `marketer` | `marketer@agents.javisi.local` | Marketer (Marketing AI) | Member | 📢 |
| `cfo` | `cfo@agents.javisi.local` | CFO (Finance AI) | Member | 💰 |
| `maintainer` | `maintainer@agents.javisi.local` | Maintainer (DevOps AI) | Member | ⚙️ |
| `messenger` | `messenger@agents.javisi.local` | Hermes (Messenger AI) | Member | 📨 |

**Règle** : Concierge = Admin (crée projets et majorité des issues après discussion avec humain)

---

## 🔑 Authentification

### API Tokens

**Option retenue** : Token individuel par agent (validation utilisateur)

```yaml
# Stockage dans Ansible Vault
plane_admin_token: "{{ vault_plane_admin_token }}"  # Concierge
plane_agent_tokens:
  concierge: "{{ vault_plane_concierge_token }}"
  builder: "{{ vault_plane_builder_token }}"
  writer: "{{ vault_plane_writer_token }}"
  artist: "{{ vault_plane_artist_token }}"
  explorer: "{{ vault_plane_explorer_token }}"
  tutor: "{{ vault_plane_tutor_token }}"
  marketer: "{{ vault_plane_marketer_token }}"
  cfo: "{{ vault_plane_cfo_token }}"
  maintainer: "{{ vault_plane_maintainer_token }}"
  messenger: "{{ vault_plane_messenger_token }}"
```

**Génération** : Via UI Plane après création des users (Settings → API Tokens)

---

## 📦 Variables Ansible

### `inventory/group_vars/all/main.yml`

```yaml
# === PLANE (Mission Control) ===
plane_subdomain: "plane"
plane_enabled: true
plane_vpn_enforce: true  # VPN-only (production)
plane_admin_email: "mobuone@ewutelo.cloud"
plane_admin_name: "Mobuone"

# Agents IA (10 users)
plane_agents:
  - id: "concierge"
    email: "concierge@agents.javisi.local"
    display_name: "Mobutoo (Concierge AI)"
    role: "Admin"
    avatar: "👔"
  - id: "builder"
    email: "builder@agents.javisi.local"
    display_name: "Imhotep (Builder AI)"
    role: "Member"
    avatar: "🏗️"
  # ... 8 autres agents
```

### `inventory/group_vars/all/versions.yml`

```yaml
# Plane (Mission Control)
plane_frontend_version: "v1.2.2"
plane_backend_version: "v1.2.2"
```

### `inventory/group_vars/all/secrets.yml` (Vault)

```yaml
# Plane
vault_plane_secret_key: "<GÉNÉRER: openssl rand -hex 32>"
vault_plane_admin_token: "<GÉNÉRER VIA UI APRÈS DEPLOY>"
vault_plane_concierge_token: "<GÉNÉRER VIA UI>"
vault_plane_builder_token: "<GÉNÉRER VIA UI>"
# ... tokens pour 8 autres agents
```

---

## 🗂️ Structure Rôle Ansible

```
roles/plane/
├── tasks/
│   └── main.yml              # Déploiement Plane
├── handlers/
│   └── main.yml              # Restart containers (recreate: always)
├── templates/
│   ├── docker-compose.yml.j2 # 3 services : web, api, worker
│   ├── .env.j2               # Variables d'environnement Plane
│   └── Caddyfile-plane.j2    # Reverse proxy VPN-only
├── files/
│   └── provision-plane-users.sh  # Script création users + API tokens
└── defaults/
    └── main.yml              # Variables par défaut
```

---

## 🚀 Étapes de Déploiement (Checklist)

### Phase 0.1 : Préparation Ansible

- [ ] Créer `roles/plane/` (structure complète)
- [ ] Ajouter variables dans `main.yml`, `versions.yml`, `secrets.yml`
- [ ] Créer templates : `docker-compose.yml.j2`, `.env.j2`, `Caddyfile-plane.j2`
- [ ] Script provisioning : `provision-plane-users.sh`

### Phase 0.2 : Base de Données

- [ ] Créer DB PostgreSQL `plane` (via role `postgresql`)
- [ ] Créer user `plane` avec `{{ postgresql_password }}`
- [ ] Tester connexion : `psql -U plane -d plane -c 'SELECT 1;'`

### Phase 0.3 : Docker Compose

- [ ] Template `docker-compose.yml.j2` avec 3 services
- [ ] Template `.env.j2` avec toutes les variables
- [ ] Healthcheck sur `plane-api`
- [ ] Limites ressources configurées
- [ ] Capabilities minimales (cap_drop + cap_add)

### Phase 0.4 : Caddy Reverse Proxy

- [ ] Template `Caddyfile-plane.j2` avec snippet `vpn_only`
- [ ] 2 CIDRs configurés (VPN + Docker frontend)
- [ ] Vérifier aucun snippet inexistant importé (REX Palais 1.8)
- [ ] Ajouter `plane.{{ domain_name }}` dans `roles/caddy/templates/Caddyfile.j2`

### Phase 0.5 : Split DNS

- [ ] Ajouter `plane.{{ domain_name }}` dans `roles/vpn-dns/defaults/main.yml`
- [ ] Format : `{name: "plane.{{ domain_name }}", type: "A", value: _vpn_dns_vps_ts_ip}`
- [ ] Vérifier pattern conditionnel : `if (plane_subdomain | default('')) | length > 0`

### Phase 0.6 : Playbook

- [ ] Ajouter role `plane` dans `playbooks/site.yml`
- [ ] Tag : `plane`
- [ ] Dépendances : `postgresql`, `redis`, `caddy`

### Phase 0.7 : Linting & Dry Run

- [ ] `make lint` (yamllint + ansible-lint) → 0 erreur
- [ ] `ansible-playbook playbooks/site.yml --check --diff --tags plane` → pas d'erreur inattendue
- [ ] Review sécurité : vérifier caps, healthchecks, limites ressources

### Phase 0.8 : Déploiement Production

- [ ] `make deploy-role ROLE=plane ENV=prod`
- [ ] Vérifier containers : `ssh sese 'docker ps | grep plane'`
- [ ] Vérifier env_file chargé : `ssh sese 'docker exec javisi_plane_api env | grep SECRET_KEY'`
- [ ] Tester healthcheck : `curl -s https://plane.ewutelo.cloud/api/health/` (VPN requis)

### Phase 0.9 : Provisioning Users

- [ ] Premier login via UI : créer admin humain
- [ ] Exécuter script : `provision-plane-users.sh` (création 10 agents IA)
- [ ] Générer API tokens pour chaque agent (UI Plane → Settings → API)
- [ ] Stocker tokens dans `secrets.yml` (Ansible Vault)
- [ ] Commit + push : `git add . && git commit -m "feat(plane): deploy v1.2.2 with 10 AI agents"`

### Phase 0.10 : Tests Fonctionnels

- [ ] Login humain admin → 200 OK
- [ ] Créer projet test "VPAI"
- [ ] Créer issue test assignée à agent "builder"
- [ ] Vérifier issue visible dans UI
- [ ] Test API : `curl -H "Authorization: Bearer <token>" https://plane.ewutelo.cloud/api/v1/issues`

---

## ⚠️ Pièges à Éviter (REX)

### 1. PostgreSQL Password

❌ **Ne PAS créer** `postgresql_plane_password` séparé
✅ **Utiliser** `{{ postgresql_password }}` (variable partagée)

### 2. Handlers Docker

❌ `state: restarted` (ne recharge pas env_file)
✅ `state: present` + `recreate: always` + `build: always`

### 3. Vérification env_file

```bash
# Après déploiement, toujours vérifier
docker exec javisi_plane_api env | grep -E "DATABASE_URL|SECRET_KEY|REDIS"
```

### 4. Caddy VPN ACL

❌ Un seul CIDR dans `not client_ip`
✅ **2 CIDRs** : `{{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}`

### 5. Split DNS

❌ Oublier d'ajouter le sous-domaine dans `vpn-dns/defaults/main.yml`
✅ Tester : `nslookup plane.ewutelo.cloud` depuis machine VPN

### 6. Images Docker

❌ `:latest`, `:stable`
✅ `:v1.2.2` (version exacte)

### 7. Healthcheck Timing

❌ Interval trop court (< 30s) → spam logs
✅ `interval: 30s`, `timeout: 10s`, `retries: 3`

### 8. Fail2ban Ban

❌ 15+ connexions SSH en rafale
✅ Grouper commandes : `ssh ... 'cmd1 && cmd2 && cmd3'`

---

## 📊 Critères de Validation (DoD)

### Code

- [ ] `npm run lint` passe (si code custom ajouté)
- [ ] FQCN Ansible sur tous les modules
- [ ] `changed_when` / `failed_when` sur `command` / `shell`
- [ ] Aucune valeur hardcodée (tout en variables Jinja2)

### Base de Données

- [ ] DB `plane` créée et accessible
- [ ] User `plane` avec password correct
- [ ] Tables créées automatiquement au premier démarrage

### Docker

- [ ] 3 containers tournent : `docker ps | grep plane` → 3 lignes
- [ ] Healthcheck `plane-api` → healthy (pas starting)
- [ ] Logs sans erreur : `docker compose logs plane-api --tail=50`

### Déploiement Ansible

- [ ] `make lint` → 0 erreur
- [ ] Ansible `--check` → pas d'erreur inattendue
- [ ] Déploiement réussi : `changed=X, failed=0`
- [ ] Handler triggered : container recreated

### Réseau

- [ ] `curl -I https://plane.ewutelo.cloud` → 200 (depuis VPN)
- [ ] `curl -I https://plane.ewutelo.cloud` → 403 (depuis hors VPN)
- [ ] Split DNS : `nslookup plane.ewutelo.cloud` → IP Tailscale Sese-AI

### Sécurité

- [ ] VPN-only enforced (`caddy_vpn_enforce: true`)
- [ ] Capabilities minimales (ALL dropped)
- [ ] Limites ressources configurées
- [ ] Secrets dans Vault (jamais en clair)

### Fonctionnel

- [ ] Login admin humain OK
- [ ] Création projet OK
- [ ] Création issue OK
- [ ] API accessible avec token
- [ ] 10 agents IA visibles comme membres

### Git

- [ ] Tous changements commités
- [ ] Message commit descriptif
- [ ] Tag `plane-v1.2.2` créé
- [ ] Push sur `main`

---

## 🔄 Rollback Plan

Si problème critique :

1. **Stopper Plane** : `ssh sese 'cd /opt/javisi && docker compose stop plane-web plane-api plane-worker'`
2. **Analyser logs** : `docker compose logs plane-api --tail=100`
3. **Rollback code** : `git revert <commit-plane>`
4. **Redéployer** : `make deploy-role ROLE=plane ENV=prod`
5. **REX** : Documenter dans `docs/REX-PLANE-DEPLOYMENT.md`

---

## 📝 Documentation Post-Déploiement

Créer `docs/REX-PLANE-DEPLOYMENT.md` avec :

- [ ] Bugs critiques rencontrés
- [ ] Solutions appliquées
- [ ] DoD updated
- [ ] Checklist pré-déploiement
- [ ] Commandes de diagnostic

---

## ✅ Validation Humaine Requise

**Avant de commencer Phase 0.1, valider :**

1. ✅ Nom de domaine : `ewutelo.cloud` ✓
2. ✅ Sous-domaine : `work.ewutelo.cloud` ✓
3. ✅ VPN-only : `true` (ou `false` pour test initial ?)
4. ✅ Version Plane : `v1.2.2` (latest 2026-02-23, OK ?)
5. ✅ Email admin humain : `mobuone@ewutelo.cloud` (ou autre ?)
6. ✅ Concierge = Admin : confirmé
7. ✅ Tokens individuels : confirmé
8. ✅ Password PostgreSQL : partagé (pas de password séparé)
9. ✅ REX strictement appliqués : confirmé
10. ✅ Review sécurité : obligatoire avant merge

---

**Statut** : ⏸️ EN ATTENTE VALIDATION HUMAINE

**Prochaine étape après validation** : Utiliser `/gsd:plan-phase` pour créer le plan d'exécution détaillé

---

**Auteur** : Claude Sonnet 4.6
**Date** : 2026-02-28
**Version** : 1.0.0
