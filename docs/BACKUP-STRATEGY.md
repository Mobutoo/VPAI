# Backup Strategy — Data Lifecycle & Tiering

> **Project**: VPAI — Self-Hosted AI Infrastructure Stack
> **Version**: 1.0.0
> **Last updated**: February 2026

---

## 1. Architecture Overview

Zerobyte (on Seko-VPN) is the **central orchestrator** for all backups across the
infrastructure. It does **not store data locally** — all backup data is pushed to
Hetzner S3 Object Storage.

```
Data Sources                  Orchestrator                 Storage Tiers
=============                 ============                 ==============

VPS VPAI (Prod)  --+
                   |
VPS Applicatif   --+--VPN--> Seko-VPN       --S3 API-->  Hetzner S3 (WARM)
(T+6 weeks)        |         Zerobyte                       |
                   |         (orchestrate,                   | rclone sync
Future equipment --+          encrypt,                       | (monthly)
                              deduplicate)                   v
                                                          NAS TrueNAS (COLD)
                                                          (T+6 months)
```

### Design Principles

1. **Zerobyte = orchestrator, not storage** — transit only, no data persisted on VPN
2. **Restic for technical backups** — encrypted, deduplicated, incremental (databases, configs)
3. **Raw files for media/documents** — navigable, streamable, mountable in Nextcloud
4. **Two S3 buckets** — separate concerns (backups vs shared files)
5. **GFS retention** — Grandfather-Father-Son for cost-optimized long-term retention
6. **3-2-1 rule** — 3 copies, 2 media types, 1 offsite

---

## 2. S3 Bucket Strategy

Two separate buckets on Hetzner Object Storage (same base plan at 4.99 EUR/month,
1 TB shared across both):

### Bucket 1: `vpai-backups` (Restic — encrypted, non-browsable)

Purpose: disaster recovery, technical backups.

```
s3://vpai-backups/
  ├── config              (Restic encrypted config)
  ├── data/
  │   ├── 00/ .. ff/      (deduplicated, encrypted chunks)
  ├── index/
  ├── keys/
  ├── locks/
  └── snapshots/
```

Content: PostgreSQL dumps, Redis RDB, Qdrant snapshots, n8n workflow exports,
Grafana dashboard exports, application configs.

**Not human-browsable.** Requires `restic restore` to extract files.

### Bucket 2: `vpai-shared` (raw files — browsable, mountable)

Purpose: shared files, preprod seeding, media archive transit.

```
s3://vpai-shared/
  ├── exports/                       (latest exports for quick access)
  │   ├── n8n-workflows-latest.json
  │   ├── grafana-dashboards/
  │   └── configs/
  ├── seed-data/                     (preprod seeding data)
  │   ├── pg-dumps/
  │   │   ├── n8n-latest.dump
  │   │   ├── openclaw-latest.dump
  │   │   └── litellm-latest.dump
  │   ├── redis/
  │   └── qdrant/
  └── documents/                     (T+6 weeks: shared documents)
      ├── deliverables/
      └── archives/
```

**Human-browsable.** Can be mounted in Nextcloud as External Storage.
Can be accessed via `rclone`, `aws s3` CLI, or any S3-compatible client.

---

## 3. GFS Retention Policy (Grandfather-Father-Son)

### Restic Retention (vpai-backups bucket)

```
restic forget \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 6 \
  --keep-yearly 2 \
  --prune
```

| Level | Retention | Schedule | Type | Estimated size |
|-------|-----------|----------|------|---------------|
| **Daily** (Son) | 7 days | Every night 03:00 | Incremental | ~20-100 MB/day (dedup) |
| **Weekly** (Father) | 4 weeks | Sunday (auto-tagged) | Incremental | ~50-200 MB/week |
| **Monthly** (Grandfather) | 6 months | 1st of month (auto-tagged) | Incremental | ~100-500 MB/month |
| **Yearly** (Archive) | 2 years | January 1st | Full equivalent | ~1-3 GB/year |

**Total estimated S3 usage**: 10-30 GB (with Restic deduplication).

### How GFS Works with Restic

Restic uses Content Defined Chunking (CDC). Every snapshot appears as a full backup
to the user but only stores modified chunks on disk. A daily backup of 200 MB of
PostgreSQL dumps typically consumes only 5-20 MB of new storage if few rows changed.

### Raw Files Retention (vpai-shared bucket)

| Content | Retention on S3 | Then |
|---------|----------------|------|
| Preprod seed data | Always (latest only) | Overwritten each day |
| Recent exports | 30 days | Auto-cleaned by lifecycle policy |
| Documents/deliverables | 3-6 months | Moved to NAS (T+6 months) |
| Media files | Transit only (days) | Moved to NAS ASAP |

---

## 4. Data by Service

### VPS VPAI (production AI stack)

| Service | Data | Method | Raw size/day | Restic dedup |
|---------|------|--------|-------------|-------------|
| PostgreSQL (x3 DBs) | n8n, openclaw, litellm | `pg_dump -Fc` | 50-200 MB | 5-30 MB |
| Redis | Sessions, LLM cache | `BGSAVE` (RDB) | 10-50 MB | 1-5 MB |
| Qdrant | Vector embeddings | Snapshot API | 100-500 MB | 10-50 MB |
| n8n | Workflow definitions | `n8n export:workflow` | 1-5 MB | <1 MB |
| Grafana | Dashboard JSON | API export | 1-5 MB | <1 MB |
| Configs | docker-compose, env, caddy | Direct copy | <1 MB | <1 MB |
| **Total** | | | **~200-800 MB** | **~20-90 MB** |

### VPS Applicatif (T+6 weeks — media, Nextcloud)

| Data type | Method | Destination | Notes |
|-----------|--------|-------------|-------|
| Nextcloud DB | `pg_dump` or `mysqldump` | Restic (vpai-backups) | Same GFS policy |
| Nextcloud files | `rclone sync` | vpai-shared (raw) | Browsable, large files |
| Media (photos, videos) | `rclone sync` | vpai-shared (transit) then NAS | Not encrypted via Restic |
| Deliverables | `rclone sync` | vpai-shared (raw) | Archived to NAS monthly |

### Why NOT Restic for Media/Documents

| Criterion | Restic | Raw S3 |
|-----------|--------|--------|
| Browsable in Nextcloud | No (encrypted chunks) | Yes |
| Video streaming | No | Yes (HTTP Range requests) |
| Photo thumbnails | No | Yes (Nextcloud generates them) |
| Share by link | No | Yes (signed URLs or Nextcloud) |
| Single file restore | Slow (full snapshot context) | Instant (direct download) |
| Deduplication | Excellent | None |
| Encryption | Built-in (AES-256) | SSE at rest (S3 default) |

**Rule**: Use Restic for databases and configs. Use raw S3 for files humans need to browse.

---

## 5. Zerobyte Configuration

### Repositories

| Repository | Type | Endpoint | Bucket | Encryption |
|------------|------|----------|--------|------------|
| `vpai-restic` | Restic + S3 | `fsn1.your-objectstorage.com` | `vpai-backups` | Restic AES-256 |
| `vpai-shared` | rclone + S3 | `fsn1.your-objectstorage.com` | `vpai-shared` | SSE at rest |

### Backup Jobs (VPAI Prod)

| Job | Source (via VPN) | Repository | Schedule | GFS Retention |
|-----|-----------------|------------|----------|---------------|
| DB Full | `/opt/vpai/backups/pg_dump/` | vpai-restic | Daily 03:00 | 7d / 4w / 6m / 2y |
| Redis | `/opt/vpai/data/redis/` | vpai-restic | Daily 03:05 | 7d / 4w |
| Qdrant | `/opt/vpai/backups/qdrant/` | vpai-restic | Daily 03:10 | 7d / 4w / 6m |
| n8n Export | `/opt/vpai/backups/n8n/` | vpai-restic | Daily 03:15 | 7d / 4w / 6m / 2y |
| Configs | `/opt/vpai/configs/` | vpai-restic | Daily 03:20 | 7d / 4w |
| Grafana | `/opt/vpai/backups/grafana/` | vpai-restic | Weekly Sun 03:00 | 4w / 6m |
| Seed Export | `/opt/vpai/backups/` | vpai-shared | Daily 03:30 | Latest only |

### Zerobyte UI Configuration

```
For each Restic job:
  Retention Policy:
    Keep Daily:    7
    Keep Weekly:   4
    Keep Monthly:  6
    Keep Yearly:   2
    Auto-prune:    Yes (after forget)
```

---

## 6. Preprod Data Seeding

The preprod environment needs realistic data for testing. Seed data comes from
the `vpai-shared` S3 bucket (raw, unencrypted dumps).

### Daily Seed Export (automated)

The pre-backup script on prod exports latest dumps to the shared bucket:

```bash
# Added to pre-backup.sh (runs at 02:55, before Zerobyte at 03:00)
# After creating dumps, copy latest to shared bucket for preprod seeding

rclone copy /opt/vpai/backups/pg_dump/ hetzner-s3:vpai-shared/seed-data/pg-dumps/ \
  --include "*-latest.dump"
rclone copy /opt/vpai/data/redis/dump.rdb hetzner-s3:vpai-shared/seed-data/redis/
```

### Seeding Workflow (preprod)

```bash
# 1. Pull seed data from S3
rclone sync hetzner-s3:vpai-shared/seed-data/ /tmp/seed-data/

# 2. Restore PostgreSQL (with anonymization)
for DB in n8n openclaw litellm; do
  docker cp /tmp/seed-data/pg-dumps/${DB}-latest.dump vpai_postgresql:/tmp/
  docker exec vpai_postgresql pg_restore -U postgres -d ${DB} \
    --clean --if-exists /tmp/${DB}-latest.dump
done

# 3. Anonymize sensitive data
docker exec vpai_postgresql psql -U postgres -d n8n -c "
  UPDATE credential_entity SET data = '***REDACTED***';
  UPDATE webhook_entity SET webhook_path = 'test-' || webhook_path;
"

# 4. Restart services
docker compose restart n8n openclaw litellm
```

### Data Anonymization Matrix

| Data | Keep as-is | Anonymize | Skip |
|------|:----------:|:---------:|:----:|
| Workflow structures (n8n) | X | | |
| Credentials (n8n) | | X | |
| Webhooks (n8n) | | X (prefix `test-`) | |
| Prompts/history (OpenClaw) | X | | |
| LiteLLM routing config | X | | |
| LiteLLM API keys | | X | |
| Grafana dashboards | X | | |
| Metrics (VictoriaMetrics) | | | X |
| Logs (Loki) | | | X |

See `playbooks/seed-preprod.yml` for the automated Ansible playbook.

---

## 7. Data Tiering — Hot / Warm / Cold

### Three Temperature Tiers

```
HOT (daily access)       Local NVMe on VPS
  |                       Fast, limited capacity
  |                       Working data, active databases
  |
  | Automated (cron + Zerobyte)
  v
WARM (occasional)        S3 Hetzner Object Storage (4.99 EUR/month)
  |                       API access, moderate latency
  |                       Backups, seed data, recent documents
  |                       Mountable in Nextcloud (External Storage)
  |
  | rclone sync (monthly, or on-demand)
  v
COLD (archive)           NAS TrueNAS (on-premises, T+6 months)
                          10-12 TB, ZFS mirrored
                          Long-term archive, local consultation
                          Accessible via VPN if needed remotely
```

### Lifecycle Rules

| Data type | HOT duration | WARM duration | COLD (NAS) |
|-----------|-------------|---------------|------------|
| Database backups (Restic) | 3 days (local) | Permanent (GFS) | Mirror (monthly sync) |
| Configs | Always (live) | Permanent (GFS) | Mirror |
| Deliverables (active) | While working | 3-6 months | Permanent archive |
| Deliverables (done) | None | Transit (days) | Permanent archive |
| Media (photos/videos) | While editing | Transit (days) | Permanent archive |
| Music | None | None | Permanent (NAS only) |

### S3 Lifecycle Policy (vpai-shared bucket)

```json
{
  "Rules": [
    {
      "ID": "clean-old-exports",
      "Prefix": "exports/",
      "Status": "Enabled",
      "Expiration": { "Days": 30 }
    }
  ]
}
```

Deliverables and media in `documents/` are moved manually or via monthly cron
(`rclone move`) to the NAS once archived.

---

## 8. Infrastructure Timeline

### T0 — Now (VPAI deployment)

```
Components:
  VPS VPAI (OVH)          Production AI stack
  Seko-VPN (Ionos)         Zerobyte orchestrator
  Preprod (Hetzner CX23)   CI/CD testing
  S3 Hetzner               2 buckets (backups + shared)

Backup flow:
  VPAI --> [cron pre-backup] --> [Zerobyte pull via VPN] --> S3

Monthly cost (new):   8.48 EUR (Preprod 3.49 + S3 4.99)
```

### T+6 Weeks — VPS Applicatif

```
New component:
  VPS Applicatif (Hetzner)   Nextcloud, media services
    - Mounts S3 vpai-shared as External Storage in Nextcloud
    - Local NVMe for hot data (active projects)
    - Media processing (photos, videos)

Backup flow (added):
  VPS App --> [Zerobyte pull via VPN] --> S3 (Restic for DB, raw for files)

Nextcloud sees:
  /Projects/        (local NVMe — fast)
  /Archives/         (S3 vpai-shared — browsable, slower)

Monthly cost (added):  ~6-12 EUR (VPS Applicatif)
```

### T+6 Months — NAS TrueNAS

```
New component:
  NAS TrueNAS (on-premises)   10-12 TB, ZFS mirror
    - Connected to VPN mesh (Headscale/Tailscale)
    - Monthly rclone sync from S3 to NAS
    - Local media library (Jellyfin, Plex, or direct access)
    - Long-term archive destination

Data flow (added):
  S3 --> [rclone sync monthly via VPN] --> NAS
  S3 vpai-shared/documents/ --> rclone move --> NAS /archives/
  S3 vpai-backups/ --> rclone sync --> NAS /backups-mirror/

Nextcloud sees:
  /Projects/        (local NVMe — fast)
  /Archives/         (S3 vpai-shared — recent, browsable)
  /NAS/              (TrueNAS via WebDAV/SFTP over VPN — large, cold)

3-2-1 rule achieved:
  3 copies:   VPS (local temp) + S3 (cloud) + NAS (on-premises)
  2 media:    NVMe cloud + HDD local (ZFS mirror)
  1 offsite:  S3 Hetzner (different DC from everything else)

Monthly cost (added):   ~5 EUR electricity
One-time cost:          ~300 EUR hardware
```

### Full Architecture at T+6 Months

```
                            S3 Hetzner (4.99 EUR/month, 1 TB)
                           +-------------------------------------+
                           | vpai-backups/                        |
                           |   Restic encrypted, GFS retention   |
                           |   7d / 4w / 6m / 2y                 |
                           |                                      |
                           | vpai-shared/                         |
                           |   exports/ (latest, 30d lifecycle)  |
                           |   seed-data/ (preprod seeding)      |
                           |   documents/ (transit to NAS)       |
                           +------------------+------------------+
                                              |
            +---------------------------------+----------------------------------+
            |                                 |                                  |
   +--------+--------+              +--------+--------+              +-----------+---------+
   | VPS VPAI (OVH)  |              | Seko-VPN (Ionos)|              | VPS Applicatif      |
   | AI/Automation    |              | Zerobyte        |              | (Hetzner)           |
   |                  |<--VPN pull-->| Orchestrator    |<--VPN pull-->| Nextcloud + Media   |
   | PostgreSQL x3    |              |                 |              |                     |
   | Redis, Qdrant    |              | Uptime Kuma     |              | Local NVMe (hot)    |
   | n8n, LiteLLM     |              |                 |              | S3 mount (warm)     |
   | OpenClaw, Caddy  |              |                 |              | NAS mount (cold)    |
   +--------+---------+              +-----------------+              +----------+----------+
            |                                                                   |
   +--------+--------+                                               +----------+----------+
   | Preprod (Hetzner)|                                              | NAS TrueNAS         |
   | CX23 (3.49 EUR)  |<--seed from S3                              | (On-premises)       |
   | Test environment  |                                              | 10-12 TB ZFS mirror |
   +------------------+                                              | Long-term archive    |
                                                                      | Media library        |
                                                                      | Backup mirror        |
                                                                      +---------------------+
```

---

## 9. Cost Summary

### Monthly Recurring

| Component | Cost (EUR/month) | Status |
|-----------|-----------------|--------|
| VPS VPAI (OVH) | ~14 | Existing |
| Seko-VPN (Ionos) | ~5 | Existing |
| Domain OVH | ~0.67 | Existing |
| **Preprod Hetzner CX23** | **3.49** | New (T0) |
| **S3 Hetzner Object Storage** | **4.99** | New (T0) |
| VPS Applicatif (Hetzner) | ~6-12 | New (T+6 weeks) |
| NAS electricity | ~5 | New (T+6 months) |
| **Total at T0** | **~28** | |
| **Total at T+6 weeks** | **~34-40** | |
| **Total at T+6 months** | **~39-45** | |

### One-Time Costs

| Item | Cost (EUR) | When |
|------|-----------|------|
| NAS hardware (TrueNAS, 2x 6TB HDD) | ~300 | T+6 months |

### S3 Storage Estimate

| Content | Estimated size | At T+6 months |
|---------|---------------|---------------|
| vpai-backups (Restic, 2 years GFS) | 15-30 GB | 30-50 GB |
| vpai-shared (seed + transit) | 10-50 GB | 20-80 GB |
| **Total** | **25-80 GB** | **50-130 GB** |

Well under the 1 TB included in the 4.99 EUR/month plan.

---

## 10. Nextcloud Integration (T+6 weeks)

### External Storage Configuration

Mount `vpai-shared` bucket as a shared folder in Nextcloud:

```
Admin > External Storage > Add Storage
  Type: Amazon S3
  Bucket: vpai-shared
  Hostname: fsn1.your-objectstorage.com
  Port: 443
  Region: fsn1
  Enable SSL: Yes
  Enable Path Style: Yes
  Access Key: (from Vault)
  Secret Key: (from Vault)
  Available for: All users (or specific group)
  Folder name: Archives
```

### Known Limitations with Hetzner S3

- Browsing can be slow (~30-60s for large directories)
- No file versioning (`ListObjectVersions` returns 404)
- Uploads > 80 MB may fail via Nextcloud S3 connector
- File locking conflicts possible (disable Nextcloud transactional locking)

### Recommended Approach

- **Daily work**: local NVMe on VPS Applicatif (fast)
- **Archive browse**: S3 via Nextcloud (acceptable latency for occasional access)
- **Large media**: upload via `rclone` CLI, not Nextcloud web UI
- **NAS access** (T+6 months): mount via WebDAV or SFTP over VPN

---

## 11. NAS TrueNAS Integration (T+6 months)

### Monthly Sync Script

```bash
#!/bin/bash
# /opt/scripts/sync-s3-to-nas.sh
# Run monthly via cron on NAS or VPN server

set -euo pipefail

# Mirror Restic backups to NAS (read-only copy for disaster recovery)
rclone sync hetzner-s3:vpai-backups /mnt/nas/backups-mirror/vpai/ \
  --transfers 4 --checkers 8

# Move archived documents from S3 to NAS (frees S3 space)
rclone move hetzner-s3:vpai-shared/documents/archives/ /mnt/nas/archives/ \
  --min-age 90d --transfers 4

# Sync latest exports for local reference
rclone sync hetzner-s3:vpai-shared/exports/ /mnt/nas/exports/vpai/ \
  --transfers 4

echo "[$(date)] S3 to NAS sync completed"
```

### NAS Directory Structure

```
/mnt/nas/
  ├── backups-mirror/
  │   └── vpai/              (Restic mirror from S3 — disaster recovery)
  ├── archives/
  │   ├── deliverables/      (completed project deliverables)
  │   └── documents/         (old documents moved from S3)
  ├── media/
  │   ├── photos/            (personal/project photos)
  │   ├── videos/            (project videos, recordings)
  │   └── music/             (music library — NAS only, never S3)
  └── exports/
      └── vpai/              (latest config/workflow exports for reference)
```

### 3-2-1 Backup Validation

| Copy | Location | Medium | Offsite |
|------|----------|--------|---------|
| 1 | VPS (local /opt/vpai/backups/) | NVMe SSD | No |
| 2 | S3 Hetzner (Restic encrypted) | Object Storage | Yes (Falkenstein DC) |
| 3 | NAS TrueNAS (Restic mirror) | HDD ZFS mirror | No (but different from VPS) |

> The NAS is not offsite, but the S3 bucket is. If both the VPS and NAS are lost
> simultaneously (extremely unlikely — different locations), S3 still has all data.
