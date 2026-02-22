# Spécification Technique — Self-Hosted AI Infrastructure Stack

> **Version** : 1.0.0  
> **Date** : 11 février 2026  
> **Réf. PRD** : PRD.md v1.0.0  
> **Statut** : Draft — En attente de validation

---

## 1. Structure du Repository

```
{{ project_name }}/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # Lint + Molecule tests
│       ├── deploy-preprod.yml        # Deploy sur Hetzner éphémère
│       └── deploy-prod.yml           # Deploy prod (manuel)
├── inventory/
│   ├── hosts.yml                     # Inventaire dynamique
│   └── group_vars/
│       ├── all/
│       │   ├── main.yml              # Variables générales (depuis wizard)
│       │   ├── versions.yml          # Images Docker pinnées
│       │   ├── docker.yml            # Config Docker (daemon, limits, networks)
│       │   └── secrets.yml           # Ansible Vault (chiffré)
│       ├── prod/
│       │   └── main.yml              # Overrides production
│       └── preprod/
│           └── main.yml              # Overrides pré-production
├── roles/
│   ├── common/
│   ├── hardening/
│   ├── docker/
│   ├── headscale-node/
│   ├── caddy/
│   ├── postgresql/
│   ├── redis/
│   ├── qdrant/
│   ├── n8n/
│   ├── openclaw/
│   ├── litellm/
│   ├── monitoring/
│   ├── diun/
│   ├── backup-config/
│   ├── uptime-config/
│   └── smoke-tests/
├── playbooks/
│   ├── site.yml                      # Playbook principal (tous les rôles)
│   ├── deploy.yml                    # Déploiement applicatif uniquement
│   ├── backup-restore.yml            # Restauration depuis backup
│   └── rollback.yml                  # Rollback d'urgence
├── scripts/
│   ├── wizard.sh                     # Script interactif de config wizard
│   ├── init-vault.sh                 # Initialisation Ansible Vault
│   └── smoke-test.sh                 # Tests de fumée
├── templates/                         # Templates Jinja2 partagés
│   └── docker-compose.yml.j2
├── docs/
│   ├── RUNBOOK.md                    # Procédures opérationnelles
│   ├── ARCHITECTURE.md               # Diagrammes d'architecture
│   └── DISASTER-RECOVERY.md          # Plan de reprise d'activité
├── molecule/                          # Tests Molecule
│   └── default/
│       ├── molecule.yml
│       ├── converge.yml
│       └── verify.yml
├── ansible.cfg
├── requirements.yml                   # Collections Ansible
└── README.md
```

---

## 2. Configuration Docker

### 2.1 daemon.json

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "live-restore": true,
  "default-address-pools": [
    {
      "base": "172.20.0.0/16",
      "size": 24
    }
  ]
}
```

### 2.2 Réseaux Docker Isolés

```yaml
# docker-compose.yml.j2 — section networks
networks:
  frontend:
    name: "{{ project_name }}_frontend"
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.1.0/24

  backend:
    name: "{{ project_name }}_backend"
    driver: bridge
    internal: true                    # PAS d'accès internet
    ipam:
      config:
        - subnet: 172.20.2.0/24

  monitoring:
    name: "{{ project_name }}_monitoring"
    driver: bridge
    internal: true                    # PAS d'accès internet
    ipam:
      config:
        - subnet: 172.20.3.0/24
```

### 2.3 Matrice des Réseaux par Service

| Service | frontend | backend | monitoring | Justification |
|---------|----------|---------|------------|---------------|
| Caddy | ✅ | ✅ | — | Bridge frontend ↔ backend |
| n8n | — | ✅ | — | Backend uniquement, Caddy en proxy |
| OpenClaw | — | ✅ | — | Backend uniquement |
| LiteLLM | — | ✅ | — | Backend, mais outbound internet nécessaire* |
| PostgreSQL | — | ✅ | — | Données, jamais exposé |
| Redis | — | ✅ | — | Cache, jamais exposé |
| Qdrant | — | ✅ | — | Vector DB, jamais exposé |
| Grafana | ✅ | — | ✅ | Bridge frontend ↔ monitoring |
| VictoriaMetrics | — | — | ✅ | Monitoring interne uniquement |
| Loki | — | — | ✅ | Monitoring interne uniquement |
| Alloy | — | ✅ | ✅ | Bridge backend ↔ monitoring (scrape) |
| DIUN | — | — | — | Host network (Docker socket) |

> *LiteLLM doit pouvoir atteindre les APIs externes (OpenAI, Anthropic). Le réseau `backend` étant `internal: true`, il faut ajouter LiteLLM aussi au réseau `frontend` **ou** utiliser un réseau dédié `egress` non-internal. **Recommandation** : réseau `egress` séparé pour LiteLLM + n8n (pour les webhooks sortants).

### 2.4 Réseau Egress (ajout)

```yaml
  egress:
    name: "{{ project_name }}_egress"
    driver: bridge
    # PAS internal — accès internet autorisé
    ipam:
      config:
        - subnet: 172.20.4.0/24
```

Services sur le réseau egress : `litellm`, `n8n`, `openclaw` (pour la navigation web des agents).

### 2.5 Limites de Ressources Docker

```yaml
# docker-compose.yml.j2 — limites par service
# Adaptées pour VPS 8 GB RAM prod / 4 GB preprod

services:
  postgresql:
    deploy:
      resources:
        limits:
          memory: "{{ '1536M' if target_env == 'prod' else '768M' }}"
          cpus: "{{ '1.5' if target_env == 'prod' else '0.75' }}"
        reservations:
          memory: "{{ '512M' if target_env == 'prod' else '256M' }}"

  redis:
    deploy:
      resources:
        limits:
          memory: "{{ '512M' if target_env == 'prod' else '256M' }}"
          cpus: "0.5"
        reservations:
          memory: "128M"

  n8n:
    deploy:
      resources:
        limits:
          memory: "{{ '1024M' if target_env == 'prod' else '512M' }}"
          cpus: "1.0"
        reservations:
          memory: "256M"

  openclaw:
    deploy:
      resources:
        limits:
          memory: "{{ '1024M' if target_env == 'prod' else '512M' }}"
          cpus: "1.0"
        reservations:
          memory: "256M"

  litellm:
    deploy:
      resources:
        limits:
          memory: "{{ '768M' if target_env == 'prod' else '384M' }}"
          cpus: "0.75"
        reservations:
          memory: "192M"

  qdrant:
    deploy:
      resources:
        limits:
          memory: "{{ '1024M' if target_env == 'prod' else '512M' }}"
          cpus: "0.75"
        reservations:
          memory: "256M"

  grafana:
    deploy:
      resources:
        limits:
          memory: "384M"
          cpus: "0.5"
        reservations:
          memory: "128M"

  victoriametrics:
    deploy:
      resources:
        limits:
          memory: "512M"
          cpus: "0.5"
        reservations:
          memory: "128M"

  loki:
    deploy:
      resources:
        limits:
          memory: "384M"
          cpus: "0.5"
        reservations:
          memory: "128M"

  alloy:
    deploy:
      resources:
        limits:
          memory: "256M"
          cpus: "0.25"
        reservations:
          memory: "64M"

  caddy:
    deploy:
      resources:
        limits:
          memory: "256M"
          cpus: "0.5"
        reservations:
          memory: "64M"

  diun:
    deploy:
      resources:
        limits:
          memory: "128M"
          cpus: "0.25"
        reservations:
          memory: "32M"
```

**Budget RAM total** :
- Prod (limits) : 1536+512+1024+1024+768+1024+384+512+384+256+256+128 = **7808 MB** (~7.6 GB sur 8 GB)
- Preprod (limits) : 768+256+512+512+384+512+384+512+384+256+256+128 = **4864 MB** (~4.7 GB sur 4 GB) — ajustement nécessaire, voir note

> **Note preprod** : Les limites preprod dépassent 4 GB. En preprod, ne pas lancer tous les services simultanément. Option : désactiver monitoring complet (Grafana+VM+Loki+Alloy = -1.5 GB) ou utiliser un CX32 (8 GB).

---

## 3. Sécurité

### 3.1 SSH Hardening

```yaml
# roles/hardening/templates/sshd_config.j2

Port {{ prod_ssh_port }}
ListenAddress {{ vpn_headscale_ip }}     # SSH UNIQUEMENT sur l'IP Headscale
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
AllowUsers {{ prod_user }}
```

### 3.2 UFW Firewall

```yaml
# roles/hardening/tasks/firewall.yml

- name: UFW — Deny all incoming by default
  community.general.ufw:
    default: deny
    direction: incoming

- name: UFW — Allow HTTP
  community.general.ufw:
    rule: allow
    port: "80"
    proto: tcp

- name: UFW — Allow HTTPS
  community.general.ufw:
    rule: allow
    port: "443"
    proto: tcp

- name: UFW — Allow SSH from Headscale only
  community.general.ufw:
    rule: allow
    port: "{{ prod_ssh_port }}"
    proto: tcp
    from_ip: "{{ vpn_network_cidr }}"

- name: UFW — Allow Headscale/Tailscale
  community.general.ufw:
    rule: allow
    port: "41641"
    proto: udp

- name: UFW — Enable
  community.general.ufw:
    state: enabled
```

### 3.3 Fail2ban

```ini
# roles/hardening/templates/jail.local.j2

[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
banaction = ufw

[sshd]
enabled = true
port = {{ prod_ssh_port }}
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
```

### 3.4 CrowdSec

```yaml
# roles/hardening/tasks/crowdsec.yml

- name: Install CrowdSec
  ansible.builtin.apt:
    name:
      - crowdsec
      - crowdsec-firewall-bouncer-iptables
    state: present

- name: Install CrowdSec collections
  ansible.builtin.command:
    cmd: "cscli collections install {{ item }}"
  loop:
    - crowdsecurity/linux
    - crowdsecurity/sshd
    - crowdsecurity/nginx        # Compatible avec les logs Caddy format CLF
    - crowdsecurity/http-cve
  changed_when: false
```

### 3.5 Caddy — Sécurité & ACL

```
# roles/caddy/templates/Caddyfile.j2

{
    email {{ notification_email }}
    servers {
        protocols h1 h2 h3
    }
}

# --- Snippet : ACL VPN uniquement ---
(vpn_only) {
    @blocked not remote_ip {{ vpn_network_cidr }}
    respond @blocked 403
}

# --- Services publics (API) ---
{{ domain_name }} {
    # LiteLLM API — authentifié par API key, pas VPN
    handle /litellm/* {
        uri strip_prefix /litellm
        reverse_proxy litellm:4000
    }

    # Health endpoint public
    handle /health {
        respond "OK" 200
    }

    # Tout le reste → 404
    handle {
        respond "Not Found" 404
    }

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }

    # Rate limiting global
    rate_limit {
        zone global {
            key {remote_host}
            events 100
            window 1m
        }
    }
}

# --- Admin UIs — VPN uniquement ---
admin.{{ domain_name }} {
    import vpn_only

    handle /n8n/* {
        uri strip_prefix /n8n
        reverse_proxy n8n:5678
    }

    handle /grafana/* {
        uri strip_prefix /grafana
        reverse_proxy grafana:3000
    }

    handle /openclaw/* {
        uri strip_prefix /openclaw
        reverse_proxy openclaw:8080
    }

    handle /qdrant/* {
        uri strip_prefix /qdrant
        reverse_proxy qdrant:6333
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
```

---

## 4. Configuration Applicative Day 1

### 4.1 LiteLLM — Routes & Budgets

```yaml
# roles/litellm/templates/litellm_config.yaml.j2

model_list:
  # --- Claude (Anthropic) ---
  - model_name: "claude-sonnet"
    litellm_params:
      model: "anthropic/claude-sonnet-4-20250514"
      api_key: "os.environ/ANTHROPIC_API_KEY"
      max_tokens: 8192
    model_info:
      max_input_tokens: 200000
      max_output_tokens: 8192

  - model_name: "claude-haiku"
    litellm_params:
      model: "anthropic/claude-haiku-4-5-20251001"
      api_key: "os.environ/ANTHROPIC_API_KEY"
      max_tokens: 8192

  # --- GPT (OpenAI) ---
  - model_name: "gpt-4o"
    litellm_params:
      model: "openai/gpt-4o"
      api_key: "os.environ/OPENAI_API_KEY"

  - model_name: "gpt-4o-mini"
    litellm_params:
      model: "openai/gpt-4o-mini"
      api_key: "os.environ/OPENAI_API_KEY"

  # --- Fallback routing ---
  - model_name: "default"
    litellm_params:
      model: "anthropic/claude-sonnet-4-20250514"
      api_key: "os.environ/ANTHROPIC_API_KEY"

litellm_settings:
  drop_params: true
  set_verbose: false
  num_retries: 2
  request_timeout: 120
  fallbacks:
    - model: "claude-sonnet"
      fallback: ["gpt-4o"]
  cache: true
  cache_params:
    type: "redis"
    host: "redis"
    port: 6379
    password: "{{ redis_password }}"

general_settings:
  master_key: "{{ litellm_master_key }}"
  database_url: "postgresql://litellm:{{ postgresql_password }}@postgresql:5432/litellm"
  alerting:
    - "webhook"
  alerting_args:
    webhook_url: "{{ notification_webhook_url }}"
```

### 4.2 n8n — Configuration

```yaml
# roles/n8n/templates/n8n.env.j2

# --- Database ---
DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=postgresql
DB_POSTGRESDB_PORT=5432
DB_POSTGRESDB_DATABASE=n8n
DB_POSTGRESDB_USER=n8n
DB_POSTGRESDB_PASSWORD={{ postgresql_password }}

# --- Encryption ---
N8N_ENCRYPTION_KEY={{ n8n_encryption_key }}

# --- URLs ---
N8N_HOST=0.0.0.0
N8N_PORT=5678
N8N_PROTOCOL=https
WEBHOOK_URL=https://{{ domain_name }}/n8n/
N8N_EDITOR_BASE_URL=https://admin.{{ domain_name }}/n8n/

# --- Security ---
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER={{ n8n_basic_auth_user }}
N8N_BASIC_AUTH_PASSWORD={{ n8n_basic_auth_password }}

# --- Task Runners (v2.0 security) ---
N8N_RUNNERS_ENABLED=true
N8N_RUNNERS_MODE=internal

# --- Timezone ---
GENERIC_TIMEZONE={{ timezone }}
TZ={{ timezone }}

# --- Executions ---
EXECUTIONS_DATA_PRUNE=true
EXECUTIONS_DATA_MAX_AGE=168
```

### 4.3 OpenClaw — Configuration Initiale

```yaml
# roles/openclaw/templates/openclaw.env.j2

# --- Database ---
DATABASE_URL=postgresql://openclaw:{{ postgresql_password }}@postgresql:5432/openclaw

# --- Redis ---
REDIS_URL=redis://:{{ redis_password }}@redis:6379/0

# --- Qdrant ---
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY={{ qdrant_api_key }}

# --- LiteLLM (proxy local) ---
LITELLM_BASE_URL=http://litellm:4000
LITELLM_API_KEY={{ litellm_master_key }}

# --- Defaults ---
DEFAULT_MODEL=claude-sonnet
EMBEDDING_MODEL=text-embedding-3-small

# --- Server ---
HOST=0.0.0.0
PORT=8080
API_KEY={{ openclaw_api_key }}

# --- Timezone ---
TZ={{ timezone }}
```

### 4.4 PostgreSQL — Bases de Données

```sql
-- roles/postgresql/templates/init.sql.j2
-- Exécuté au premier déploiement uniquement

CREATE DATABASE n8n;
CREATE USER n8n WITH ENCRYPTED PASSWORD '{{ postgresql_password }}';
GRANT ALL PRIVILEGES ON DATABASE n8n TO n8n;

CREATE DATABASE openclaw;
CREATE USER openclaw WITH ENCRYPTED PASSWORD '{{ postgresql_password }}';
GRANT ALL PRIVILEGES ON DATABASE openclaw TO openclaw;

CREATE DATABASE litellm;
CREATE USER litellm WITH ENCRYPTED PASSWORD '{{ postgresql_password }}';
GRANT ALL PRIVILEGES ON DATABASE litellm TO litellm;

-- Extensions utiles
\c n8n
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
\c openclaw
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
```

### 4.5 Grafana — Dashboards Day 1

| Dashboard | Source | Métriques clés |
|-----------|--------|---------------|
| System Overview | VictoriaMetrics | CPU, RAM, Disk, Network, Load |
| Docker Containers | VictoriaMetrics + cadvisor | Container CPU/RAM/Network/Restart |
| n8n Workflows | VictoriaMetrics | Executions/min, errors, duration |
| LiteLLM Proxy | VictoriaMetrics | Requests/min, latency, cost, tokens |
| PostgreSQL | VictoriaMetrics | Connections, queries/s, cache hit ratio |
| Logs Explorer | Loki | Tous les logs containers, filtrables |
| Alerting | Grafana Alerting | CPU>80%, RAM>85%, Disk>90%, errors>5/min |

---

## 5. Zerobyte — Backup Architecture & GFS Retention

> **Zerobyte is the central orchestrator** for all backups. It runs on Seko-VPN,
> pulls data via VPN, and pushes to S3. **No backup data is stored on Seko-VPN.**
> Full strategy: `docs/BACKUP-STRATEGY.md`

### 5.1 Architecture Backup

```
Data Sources                  Orchestrator                 Storage
============                  ============                 =======

┌──────────────┐              ┌──────────────┐             ┌──────────────────────┐
│  VPS VPAI    │◄──VPN pull──►│  Seko-VPN    │──S3 API──► │  Hetzner S3          │
│  (prod OVH)  │              │  Zerobyte    │             │                      │
│              │              │  :4096       │             │  vpai-backups/       │
│  Future VPS  │◄──VPN pull──►│              │             │   Restic encrypted   │
│  Applicatif  │              │  Orchestrate │             │   GFS: 7d/4w/6m/2y  │
│              │              │  Encrypt     │             │                      │
│  Future      │◄──VPN pull──►│  Deduplicate │             │  vpai-shared/        │
│  equipment   │              │              │             │   Raw files          │
└──────────────┘              └──────────────┘             │   Seed data, exports │
                                                           └──────────┬───────────┘
                                                                      │ monthly sync
                                                           ┌──────────▼───────────┐
                                                           │  NAS TrueNAS (T+6m)  │
                                                           │  10-12 TB ZFS mirror │
                                                           │  Long-term archive   │
                                                           └──────────────────────┘
```

### 5.2 S3 Buckets

| Bucket | Variable | Purpose | Format |
|--------|----------|---------|--------|
| `{{ s3_bucket_backups }}` | `s3_bucket_backups` | Disaster recovery | Restic encrypted |
| `{{ s3_bucket_shared }}` | `s3_bucket_shared` | Seed data, exports, docs | Raw files |

Both share the same plan (4.99 EUR/month, 1 TB included).

### 5.3 Volumes Zerobyte

| Volume Name | Type | Source (via VPN) | Data |
|-------------|------|-----------------|------|
| `{{ project_name }}-postgres` | Directory (mount VPN) | `/opt/{{ project_name }}/backups/pg_dump/` | pg_dump custom format |
| `{{ project_name }}-redis` | Directory (mount VPN) | `/opt/{{ project_name }}/data/redis/` | RDB dump |
| `{{ project_name }}-qdrant` | Directory (mount VPN) | `/opt/{{ project_name }}/backups/qdrant/` | API snapshots |
| `{{ project_name }}-n8n` | Directory (mount VPN) | `/opt/{{ project_name }}/backups/n8n/` | Workflow exports |
| `{{ project_name }}-configs` | Directory (mount VPN) | `/opt/{{ project_name }}/configs/` | All config files |
| `{{ project_name }}-grafana` | Directory (mount VPN) | `/opt/{{ project_name }}/backups/grafana/` | Dashboard JSON |

### 5.4 Jobs Zerobyte (GFS Retention)

| Job | Schedule | Repository | GFS Retention | Pre-script |
|-----|----------|------------|---------------|------------|
| DB Full | Daily 03:00 | vpai-backups (Restic) | 7d / 4w / 6m / 2y | `pg_dump -Fc` (3 DBs) |
| Redis | Daily 03:05 | vpai-backups (Restic) | 7d / 4w | `redis-cli BGSAVE` |
| Qdrant | Daily 03:10 | vpai-backups (Restic) | 7d / 4w / 6m | Snapshot API |
| n8n Export | Daily 03:15 | vpai-backups (Restic) | 7d / 4w / 6m / 2y | `n8n export:workflow` |
| Configs | Daily 03:20 | vpai-backups (Restic) | 7d / 4w | (direct copy) |
| Grafana | Weekly Sun 03:00 | vpai-backups (Restic) | 4w / 6m | API export |
| Seed Export | Daily 03:30 | vpai-shared (raw) | Latest only | Copy latest dumps |

Restic forget command (applied by Zerobyte after each backup):
```
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --keep-yearly 2 --prune
```

### 5.5 Pre-backup Script

See `roles/backup-config/templates/pre-backup.sh.j2` for the full script.
Runs at 02:55 via cron, before Zerobyte pulls at 03:00.

### 5.6 Data Tiering

| Tier | Location | Retention | Content |
|------|----------|-----------|---------|
| **HOT** | VPS local NVMe | 3 days | Recent dumps |
| **WARM** | S3 vpai-backups (Restic) | GFS: up to 2 years | All technical backups |
| **WARM** | S3 vpai-shared (raw) | Latest + 30 days | Seed data, exports |
| **COLD** | NAS TrueNAS (T+6 months) | Permanent | Restic mirror + archives |

---

## 6. Monitoring — Uptime Kuma (Seko-VPN)

### 6.1 Monitors à Configurer

```yaml
# roles/uptime-config/defaults/main.yml

uptime_kuma_monitors:
  - name: "{{ project_display_name }} — HTTPS"
    type: "http"
    url: "https://{{ domain_name }}/health"
    interval: 60
    retryInterval: 30
    maxretries: 2
    accepted_statuscodes: ["200"]

  - name: "{{ project_display_name }} — n8n"
    type: "http"
    url: "https://admin.{{ domain_name }}/n8n/healthz"
    interval: 60
    retryInterval: 30
    maxretries: 3
    # Via VPN — Uptime Kuma accède via Headscale

  - name: "{{ project_display_name }} — Grafana"
    type: "http"
    url: "https://admin.{{ domain_name }}/grafana/api/health"
    interval: 120
    maxretries: 3

  - name: "{{ project_display_name }} — PostgreSQL"
    type: "port"
    hostname: "{{ vpn_headscale_ip }}"    # IP Headscale du VPS prod
    port: 5432
    interval: 120
    maxretries: 2

  - name: "{{ project_display_name }} — TLS Certificate"
    type: "http"
    url: "https://{{ domain_name }}"
    interval: 86400                        # 1x par jour
    expiryNotification: true
    maxredirects: 0

  - name: "{{ project_display_name }} — Backup Heartbeat"
    type: "push"
    interval: 86400                        # Attend un ping toutes les 24h
    # Le pre-backup script envoie un ping après succès
```

---

## 7. Pré-Production Hetzner

### 7.1 Workflow GitHub Actions — Deploy Preprod

```yaml
# .github/workflows/deploy-preprod.yml

name: Deploy Pre-production
on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - 'roles/**'
      - 'playbooks/**'
      - 'inventory/**'

env:
  HETZNER_TOKEN: ${{ secrets.HETZNER_CLOUD_TOKEN }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: YAML Lint
        run: yamllint -c .yamllint.yml .
      - name: Ansible Lint
        run: ansible-lint playbooks/site.yml

  provision:
    needs: lint
    runs-on: ubuntu-latest
    outputs:
      server_ip: ${{ steps.create.outputs.ip }}
      server_id: ${{ steps.create.outputs.id }}
    steps:
      - uses: actions/checkout@v4

      - name: Create Hetzner Server
        id: create
        run: |
          # Tenter de restaurer depuis snapshot, sinon créer from scratch
          SNAPSHOT_ID=$(hcloud image list --type snapshot \
            --selector project={{ project_name }} \
            --output json | jq -r '.[0].id // empty')

          if [ -n "$SNAPSHOT_ID" ]; then
            echo "Restoring from snapshot $SNAPSHOT_ID"
            SERVER=$(hcloud server create \
              --name {{ project_name }}-preprod \
              --type {{ preprod_server_type }} \
              --location {{ preprod_location }} \
              --image "$SNAPSHOT_ID" \
              --ssh-key deploy \
              --output json)
          else
            echo "Creating from scratch"
            SERVER=$(hcloud server create \
              --name {{ project_name }}-preprod \
              --type {{ preprod_server_type }} \
              --location {{ preprod_location }} \
              --image {{ preprod_os_image }} \
              --ssh-key deploy \
              --output json)
          fi

          echo "ip=$(echo $SERVER | jq -r '.server.public_net.ipv4.ip')" >> $GITHUB_OUTPUT
          echo "id=$(echo $SERVER | jq -r '.server.id')" >> $GITHUB_OUTPUT

      - name: Update OVH DNS
        run: |
          ansible-playbook playbooks/dns-update.yml \
            -e "target_ip=${{ steps.create.outputs.ip }}" \
            -e "target_env=preprod"

      - name: Wait for DNS propagation
        run: |
          for i in $(seq 1 30); do
            RESOLVED=$(dig +short {{ subdomain_preprod }}.{{ domain_name }})
            if [ "$RESOLVED" = "${{ steps.create.outputs.ip }}" ]; then
              echo "DNS resolved correctly"
              exit 0
            fi
            sleep 10
          done
          echo "DNS propagation timeout" && exit 1

  deploy:
    needs: provision
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy via Ansible
        run: |
          ansible-playbook playbooks/site.yml \
            -i inventory/hosts.yml \
            -e "target_env=preprod" \
            -e "target_host=${{ needs.provision.outputs.server_ip }}" \
            --diff

  smoke-tests:
    needs: [provision, deploy]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Smoke Tests
        run: |
          bash scripts/smoke-test.sh \
            "https://{{ subdomain_preprod }}.{{ domain_name }}"

      - name: Create Golden Snapshot
        if: success()
        run: |
          hcloud server create-image \
            --type snapshot \
            --description "Golden $(date +%Y%m%d)" \
            --label project={{ project_name }} \
            ${{ needs.provision.outputs.server_id }}

  cleanup:
    needs: [provision, smoke-tests]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Destroy ephemeral server
        if: github.event_name != 'workflow_dispatch'
        run: |
          hcloud server delete ${{ needs.provision.outputs.server_id }}
```

### 7.2 Smoke Tests

```bash
#!/bin/bash
# scripts/smoke-test.sh
# Usage: ./smoke-test.sh https://preprod.example.com

set -euo pipefail

BASE_URL="${1:?Usage: $0 <base_url>}"
FAILURES=0

check() {
  local name="$1" url="$2" expected="${3:-200}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url")
  if [ "$status" = "$expected" ]; then
    echo "✅ $name — HTTP $status"
  else
    echo "❌ $name — HTTP $status (expected $expected)"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "=== Smoke Tests — $(date) ==="
echo "Target: $BASE_URL"
echo ""

# --- Caddy / TLS ---
check "Caddy HTTPS" "$BASE_URL/health"
check "TLS Valid" "$BASE_URL" "200"

# --- Applications (via admin subdomain ou directement) ---
check "n8n Healthz" "${BASE_URL/preprod/admin.preprod}/n8n/healthz"
check "Grafana Health" "${BASE_URL/preprod/admin.preprod}/grafana/api/health"
check "LiteLLM Health" "$BASE_URL/litellm/health"

# --- API Tests ---
echo ""
echo "=== API Connectivity Tests ==="

# LiteLLM model list
MODELS=$(curl -s -H "Authorization: Bearer ${LITELLM_KEY:-test}" \
  "$BASE_URL/litellm/v1/models" | jq -r '.data | length')
if [ "$MODELS" -gt 0 ]; then
  echo "✅ LiteLLM — $MODELS models available"
else
  echo "❌ LiteLLM — No models found"
  FAILURES=$((FAILURES + 1))
fi

echo ""
echo "=== Results ==="
if [ "$FAILURES" -eq 0 ]; then
  echo "✅ All tests passed"
  exit 0
else
  echo "❌ $FAILURES test(s) failed"
  exit 1
fi
```

---

## 8. Docker Healthchecks

```yaml
# Healthchecks intégrés au docker-compose.yml.j2

services:
  postgresql:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s

  redis:
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "{{ redis_password }}", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  n8n:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:5678/healthz || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  caddy:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:80/health || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3

  litellm:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:4000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 45s

  grafana:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:3000/api/health || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3

  qdrant:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:6333/healthz || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3

  victoriametrics:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8428/health || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3

  loki:
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:3100/ready || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
```

---

## 9. Collections Ansible Requises

```yaml
# requirements.yml

collections:
  - name: community.general
    version: ">=9.0.0"
  - name: community.docker
    version: ">=4.0.0"
  - name: community.crypto
    version: ">=2.0.0"
  - name: ansible.posix
    version: ">=1.5.0"

roles: []
  # Note: Le module synthesio.ovh pour OVH DNS est installé via pip
  # pip install python-ovh
```

---

## 10. Ordre de Démarrage des Services

```yaml
# Dépendances de démarrage (depends_on avec condition)

# Couche 1 — Données (démarrent en premier)
postgresql:   depends_on: []
redis:        depends_on: []

# Couche 2 — Applications (attendent les données)
n8n:          depends_on: { postgresql: { condition: service_healthy } }
litellm:      depends_on: { postgresql: { condition: service_healthy }, redis: { condition: service_healthy } }
openclaw:     depends_on: { postgresql: { condition: service_healthy }, redis: { condition: service_healthy }, qdrant: { condition: service_healthy } }
qdrant:       depends_on: []

# Couche 3 — Reverse Proxy (attend les applications)
caddy:        depends_on: { n8n: { condition: service_healthy }, litellm: { condition: service_healthy } }

# Couche 4 — Monitoring (indépendant)
victoriametrics: depends_on: []
loki:            depends_on: []
alloy:           depends_on: { victoriametrics: { condition: service_healthy }, loki: { condition: service_healthy } }
grafana:         depends_on: { victoriametrics: { condition: service_healthy }, loki: { condition: service_healthy } }

# Couche 5 — Système
diun:         depends_on: []
```

---

## 11. Workstation Pi — AI Creative Studio

> **Ajouté** : v1.6.0 (2026-02-22) — Phases 6.5–14

Le Workstation Pi (RPi5 16 GB) héberge le **AI Creative Studio** : génération d'images (ComfyUI) et rendu vidéo (Remotion), exposés via Caddy workstation avec TLS DNS-01 OVH, accessibles uniquement via VPN.

### 11.1 Services Docker (réseau `workstation_creative`)

| Container | Image | Port interne | Ressources | Subdomain |
|---|---|---|---|---|
| `workstation_comfyui` | `comfyui-local:v0.3.27` | 8188 | 4096M / 3.0 CPU | `studio` |
| `workstation_remotion` | `remotion-local:4.0.259` | 3200 | 512M / 2.0 CPU | `cut` |

**Réseau Docker** :
```yaml
networks:
  creative:
    name: workstation_creative
    driver: bridge
```

### 11.2 Volumes de Données

```
/opt/workstation/data/
├── comfyui/
│   ├── models/           # Modèles IA (checkpoints, LoRAs, VAE…)
│   ├── output/           # Images générées
│   ├── input/            # Images d'entrée
│   └── custom_nodes/     # Extensions ComfyUI
├── remotion/
│   └── output/           # Vidéos rendues (MP4)
└── creative-assets/      # Assets partagés ComfyUI ↔ Remotion (ro pour Remotion)
```

### 11.3 Sécurité Containers

```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
cap_add:
  - CHOWN
  - SETGID
  - SETUID

# Remotion (Chrome headless) : pas de SYS_ADMIN, utilise flag --no-sandbox
environment:
  CHROMIUM_FLAGS: "--no-sandbox --disable-setuid-sandbox"
```

### 11.4 Caddy Workstation — Reverse Proxy

```
# /opt/workstation/configs/caddy/Caddyfile
# TLS DNS-01 OVH, VPN-only ACL (100.64.0.0/10)

studio.{{ domain_name }} {
    import vpn_only
    reverse_proxy 127.0.0.1:8188
}

cut.{{ domain_name }} {
    import vpn_only
    reverse_proxy 127.0.0.1:3200
}

oc.{{ domain_name }} {
    import vpn_only
    reverse_proxy 127.0.0.1:3456
}
```

### 11.5 Healthchecks

```yaml
# ComfyUI
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=8)\" || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 5
  start_period: 120s    # Temps de chargement des modèles

# Remotion
healthcheck:
  test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:3200/health || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 5
  start_period: 60s
```

### 11.6 n8n Creative Pipeline (cross-host)

Le workflow `creative-pipeline` tourne sur n8n (VPS), mais appelle les services sur le Pi via les URLs Caddy (HTTPS, Tailscale mesh) :

```
n8n (VPS, backend network)
    ├── POST https://studio.ewutelo.cloud/prompt      → ComfyUI (image)
    ├── POST https://cut.ewutelo.cloud/render         → Remotion (video-composition)
    └── POST https://api.byteplus.com/v1/video/generate → Seedance (video cloud)
```

**Timeout** : 300 000 ms (5 min) pour ComfyUI et Remotion — les modèles CPU sont lents.

### 11.7 Asset Provenance — PostgreSQL

Le workflow `asset-register` stocke la provenance de chaque asset généré dans PostgreSQL (VPS) :

```sql
-- Table : asset_provenance
CREATE TABLE asset_provenance (
    asset_id     TEXT PRIMARY KEY,
    type         TEXT,           -- image | video
    provider     TEXT,           -- comfyui | litellm-cloud | remotion | seedance
    model        TEXT,
    prompt       TEXT,
    output_name  TEXT,
    result_url   TEXT,
    render_id    TEXT,
    agent_id     TEXT,
    cost_usd     NUMERIC(10,6),
    storage_path TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata     JSONB
);
```

Tous les champs sont **paramétrés** (`$1..$13`) — pas d'interpolation directe dans le SQL.

### 11.8 Kaneo — Project Management (VPS)

Kaneo remplace Mission Control comme outil PM. Il tourne sur le **VPS Sese-AI** (pas sur le Pi).

```yaml
# Container : kaneo (VPS, réseau backend)
ports:
  - "127.0.0.1:1337:1337"   # API
  - "127.0.0.1:3000:3000"   # Web UI
subdomain: hq               # hq.ewutelo.cloud (VPN-only)
database: kaneo (PostgreSQL partagé)
```

---

*Fin de la Spécification Technique — Document de référence pour l'implémentation.*
