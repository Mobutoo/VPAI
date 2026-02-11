# RUNBOOK — Operational Procedures

> **Project**: VPAI — Self-Hosted AI Infrastructure Stack
> **Version**: 1.0.0

---

## Table of Contents

1. [Stack Start / Stop](#1-stack-start--stop)
2. [Service Update](#2-service-update)
3. [Zerobyte Backup Configuration (Seko-VPN)](#3-zerobyte-backup-configuration-seko-vpn)
4. [Uptime Kuma Configuration (Seko-VPN)](#4-uptime-kuma-configuration-seko-vpn)
5. [Adding a New LiteLLM Model](#5-adding-a-new-litellm-model)
6. [Secret Rotation](#6-secret-rotation)
7. [Restore from Backup](#7-restore-from-backup)
8. [Incident Response](#8-incident-response)

---

## 1. Stack Start / Stop

### Start the full stack

```bash
cd /opt/vpai
docker compose up -d
```

### Stop the full stack

```bash
cd /opt/vpai
docker compose down
```

### Restart a single service

```bash
docker compose restart <service_name>
```

### View logs

```bash
# All services
docker compose logs -f --tail 100

# Single service
docker compose logs -f --tail 100 litellm
```

---

## 2. Service Update

### Update a single service via Ansible

1. Update the image version in `inventory/group_vars/all/versions.yml`
2. Run:

```bash
ansible-playbook playbooks/site.yml --tags <service_name> -e "target_env=prod" --diff
```

### Manual Docker update

```bash
cd /opt/vpai
docker compose pull <service_name>
docker compose up -d <service_name>
```

---

## 3. Zerobyte Backup Configuration (Seko-VPN)

> **Location**: Seko-VPN server, Zerobyte UI at port 4096
> **Prerequisite**: VPN connectivity between Seko-AI and Seko-VPN

### 3.1 Create S3 Repository

1. Open Zerobyte UI on Seko-VPN
2. Go to **Repositories** > **Add Repository**
3. Configure:
   - **Name**: `vpai-backups`
   - **Type**: S3
   - **Endpoint**: `fsn1.your-objectstorage.com`
   - **Bucket**: (value from vault `s3_bucket_name`)
   - **Access Key**: (from Hetzner Object Storage)
   - **Secret Key**: (from Hetzner Object Storage)
   - **Region**: `fsn1`
   - **Encryption**: Enable (set a strong password, store in vault)

### 3.2 Create Volumes

Create the following volumes, each mounting a directory from Seko-AI via VPN:

| Volume Name | Type | Source Path (via VPN) |
|-------------|------|-----------------------|
| `vpai-postgres` | Directory | `/opt/vpai/backups/pg_dump/` |
| `vpai-redis` | Directory | `/opt/vpai/data/redis/` |
| `vpai-qdrant` | Directory | `/opt/vpai/backups/qdrant/` |
| `vpai-n8n` | Directory | `/opt/vpai/backups/n8n/` |
| `vpai-configs` | Directory | `/opt/vpai/configs/` |
| `vpai-grafana` | Directory | `/opt/vpai/backups/grafana/` |

### 3.3 Create Backup Jobs

| Job Name | Volume | Schedule | Retention |
|----------|--------|----------|-----------|
| DB Backup | `vpai-postgres` | Daily 03:00 | 7 daily, 4 weekly, 3 monthly |
| Redis Snapshot | `vpai-redis` | Daily 03:05 | 7 daily |
| Qdrant Snapshot | `vpai-qdrant` | Daily 03:10 | 7 daily, 4 weekly |
| n8n Export | `vpai-n8n` | Daily 03:15 | 7 daily, 4 weekly, 3 monthly |
| Config Backup | `vpai-configs` | Daily 03:20 | 7 daily, 4 weekly |
| Grafana Export | `vpai-grafana` | Weekly Sun 03:00 | 4 weekly |

### 3.4 Verify Backup

```bash
# On Seko-AI: trigger a manual pre-backup
/opt/vpai/scripts/pre-backup.sh

# On Seko-VPN: trigger a manual Zerobyte job via UI > Jobs > Run Now
# Verify S3 content via Zerobyte UI > Repository > Browse
```

---

## 4. Uptime Kuma Configuration (Seko-VPN)

> **Location**: Seko-VPN server, Uptime Kuma instance
> **Prerequisite**: VPN connectivity to Seko-AI

### 4.1 Create Notification Group

1. Go to **Settings** > **Notifications** > **Setup Notification**
2. Create a webhook notification matching your configured method
3. Test the notification

### 4.2 Create Monitors

| # | Name | Type | URL/Host | Interval |
|---|------|------|----------|----------|
| 1 | VPAI — HTTPS | HTTP(s) | `https://<domain>/health` | 60s |
| 2 | VPAI — n8n | HTTP(s) | `https://admin.<domain>/n8n/healthz` | 60s |
| 3 | VPAI — Grafana | HTTP(s) | `https://admin.<domain>/grafana/api/health` | 120s |
| 4 | VPAI — PostgreSQL | TCP Port | `<headscale_ip>:5432` | 120s |
| 5 | VPAI — TLS Certificate | HTTP(s) | `https://<domain>` | 86400s |
| 6 | VPAI — Backup Heartbeat | Push | — | 86400s |

**Notes**:
- Monitors 2-4 require VPN access
- Monitor 5: Enable "Certificate Expiry Notification"
- Monitor 6: Copy the push URL and set it as `vault_backup_heartbeat_url`

A rendered reference with actual URLs is deployed at `/opt/vpai/docs/uptime-kuma-monitors.md`.

---

## 5. Adding a New LiteLLM Model

1. Edit `roles/litellm/templates/litellm_config.yaml.j2`
2. Add the model under `model_list`
3. If new provider, add the API key to `secrets.yml`
4. Deploy: `ansible-playbook playbooks/site.yml --tags litellm -e "target_env=prod"`

---

## 6. Secret Rotation

### Secrets to rotate periodically

| Secret | Services Affected | Frequency |
|--------|-------------------|-----------|
| `postgresql_password` | postgresql, n8n, litellm, openclaw | Quarterly |
| `redis_password` | redis, litellm, openclaw | Quarterly |
| `grafana_admin_password` | grafana | Quarterly |
| `litellm_master_key` | litellm, openclaw, caddy | Quarterly |
| `n8n_encryption_key` | n8n | **Never** (breaks encrypted data) |
| `qdrant_api_key` | qdrant, openclaw | Quarterly |

### Procedure

1. `ansible-vault edit inventory/group_vars/all/secrets.yml`
2. Change the secret value
3. Redeploy affected services with `--tags`

---

## 7. Restore from Backup

### 7.1 PostgreSQL Restore

```bash
cp /opt/vpai/backups/pg_dump/<db>-<timestamp>.dump /tmp/restore.dump
docker cp /tmp/restore.dump vpai_postgresql:/tmp/restore.dump
docker exec vpai_postgresql pg_restore -U postgres -d <db> --clean --if-exists /tmp/restore.dump
docker exec vpai_postgresql rm /tmp/restore.dump
```

### 7.2 Redis Restore

```bash
docker compose stop redis
cp /opt/vpai/backups/redis/dump-<timestamp>.rdb /opt/vpai/data/redis/dump.rdb
docker compose start redis
```

### 7.3 Full Stack Restore from S3

1. On Seko-VPN: Restore via Zerobyte UI
2. On Seko-AI: `docker compose down`
3. Restore data from mounted volumes
4. `docker compose up -d`
5. `/opt/vpai/scripts/smoke-test.sh`

---

## 8. Incident Response

### Container Crash

All containers have `restart: unless-stopped`. Check logs:
```bash
docker compose logs --tail 50 <service>
```

### VPS Down

1. Create new VPS from latest snapshot
2. Update DNS
3. Restore from Zerobyte S3
4. Re-run Ansible
5. Smoke tests

### Database Corruption

1. Stop affected service
2. Restore from backup (section 7)
3. Restart and verify

### Security Compromise

1. **Isolate** — disconnect public internet, keep VPN
2. **Assess** — check logs, identify vector
3. **Rotate** — all secrets (section 6)
4. **Redeploy** — full Ansible from clean state
5. **Monitor** — 48h increased vigilance
