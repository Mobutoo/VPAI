# ARCHITECTURE — System Diagrams

> **Project**: VPAI — Self-Hosted AI Infrastructure Stack

---

## 1. High-Level Architecture

```mermaid
graph TB
    Internet((Internet))

    subgraph VPS["VPS Production (OVH)"]
        subgraph FrontendNet["Frontend Network (172.20.1.0/24)"]
            Caddy["Caddy<br/>:80 :443"]
            Grafana["Grafana<br/>:3000"]
        end

        subgraph BackendNet["Backend Network (172.20.2.0/24) — internal"]
            n8n["n8n<br/>:5678"]
            LiteLLM["LiteLLM<br/>:4000"]
            OpenClaw["OpenClaw<br/>:8080"]
            PostgreSQL["PostgreSQL<br/>:5432"]
            Redis["Redis<br/>:6379"]
            Qdrant["Qdrant<br/>:6333"]
        end

        subgraph MonitoringNet["Monitoring Network (172.20.3.0/24) — internal"]
            VM["VictoriaMetrics<br/>:8428"]
            Loki["Loki<br/>:3100"]
            Alloy["Grafana Alloy<br/>:12345"]
        end

        subgraph EgressNet["Egress Network (172.20.4.0/24)"]
            direction LR
        end

        DIUN["DIUN<br/>(Docker socket)"]
    end

    subgraph VPN["Seko-VPN (IONOS)"]
        Headscale["Headscale"]
        Zerobyte["Zerobyte<br/>:4096"]
        UptimeKuma["Uptime Kuma"]
    end

    subgraph S3["Hetzner Object Storage (4.99 EUR/month)"]
        BackupBucket["vpai-backups<br/>(Restic encrypted)"]
        SharedBucket["vpai-shared<br/>(raw files)"]
    end

    subgraph Preprod["Preprod (Hetzner CX23 — 3.49 EUR/month)"]
        PreprodStack["VPAI Mirror<br/>(seeded from S3)"]
    end

    Internet -->|":443 HTTPS"| Caddy
    Caddy -->|"reverse proxy"| n8n
    Caddy -->|"reverse proxy"| LiteLLM
    Caddy -->|"reverse proxy"| OpenClaw
    Caddy -->|"reverse proxy"| Grafana

    n8n --> PostgreSQL
    LiteLLM --> PostgreSQL
    LiteLLM --> Redis
    OpenClaw --> PostgreSQL
    OpenClaw --> Redis
    OpenClaw --> Qdrant
    OpenClaw -->|"API proxy"| LiteLLM

    n8n -.->|"egress"| Internet
    LiteLLM -.->|"egress (OpenAI/Anthropic)"| Internet
    OpenClaw -.->|"egress"| Internet

    Alloy -->|"scrape metrics"| VM
    Alloy -->|"push logs"| Loki
    Grafana --> VM
    Grafana --> Loki

    VPS <-->|"Headscale VPN"| VPN
    Zerobyte -->|"pull via VPN"| VPS
    Zerobyte -->|"push Restic"| BackupBucket
    Zerobyte -->|"push raw"| SharedBucket
    SharedBucket -->|"seed data"| PreprodStack
    UptimeKuma -->|"monitor via VPN"| VPS
```

## 2. Network Segmentation

```mermaid
graph LR
    subgraph Frontend["Frontend (bridge)"]
        Caddy2["Caddy"]
        Grafana2["Grafana"]
    end

    subgraph Backend["Backend (internal)"]
        PG["PostgreSQL"]
        RD["Redis"]
        QD["Qdrant"]
        N8N2["n8n"]
        LL["LiteLLM"]
        OC["OpenClaw"]
    end

    subgraph Monitoring["Monitoring (internal)"]
        VM2["VictoriaMetrics"]
        LK["Loki"]
    end

    subgraph Egress["Egress (bridge)"]
        direction TB
    end

    Caddy2 --- Backend
    Grafana2 --- Monitoring

    Alloy2["Alloy"] --- Backend
    Alloy2 --- Monitoring

    N8N2 --- Egress
    LL --- Egress
    OC --- Egress

    Egress -.-> ExtAPI((External APIs))
```

## 3. Service Matrix

| Service | Frontend | Backend | Monitoring | Egress | Ports |
|---------|:--------:|:-------:|:----------:|:------:|-------|
| Caddy | X | X | | | 80, 443 |
| PostgreSQL | | X | | | 5432 |
| Redis | | X | | | 6379 |
| Qdrant | | X | | | 6333 |
| n8n | | X | | X | 5678 |
| LiteLLM | | X | | X | 4000 |
| OpenClaw | | X | | X | 8080 |
| VictoriaMetrics | | | X | | 8428 |
| Loki | | | X | | 3100 |
| Alloy | | X | X | | 12345 |
| Grafana | X | | X | | 3000 |
| DIUN | | | | | — |

## 4. Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Caddy
    participant LiteLLM
    participant Provider as OpenAI/Anthropic
    participant Redis
    participant PostgreSQL

    User->>Caddy: HTTPS request
    Caddy->>LiteLLM: Proxy (API key auth)
    LiteLLM->>Redis: Check cache
    alt Cache hit
        Redis-->>LiteLLM: Cached response
    else Cache miss
        LiteLLM->>Provider: API call (egress)
        Provider-->>LiteLLM: Response
        LiteLLM->>Redis: Store in cache
        LiteLLM->>PostgreSQL: Log request + cost
    end
    LiteLLM-->>Caddy: Response
    Caddy-->>User: HTTPS response
```

## 5. Backup & Data Tiering

```mermaid
sequenceDiagram
    participant Cron as Cron (02:55)
    participant Script as pre-backup.sh
    participant Docker as Docker Containers
    participant Local as /opt/vpai/backups/
    participant Zerobyte as Zerobyte (03:00)
    participant S3Back as S3: vpai-backups
    participant S3Share as S3: vpai-shared
    participant UK as Uptime Kuma

    Cron->>Script: Trigger
    Script->>Docker: pg_dump (3 databases)
    Script->>Docker: redis-cli BGSAVE
    Script->>Docker: qdrant snapshot
    Script->>Docker: n8n export:workflow
    Script->>Local: Write dumps
    Script->>S3Share: Copy latest seed-data (for preprod)
    Script->>UK: Heartbeat ping

    Note over Zerobyte: 03:00 — Scheduled jobs (GFS retention)
    Zerobyte->>Local: Pull backup files (via VPN)
    Zerobyte->>S3Back: Push Restic encrypted (7d/4w/6m/2y)
```

### Data Temperature Tiers

| Tier | Location | Access | Content | Lifecycle |
|------|----------|--------|---------|-----------|
| **HOT** | VPS local NVMe | Daily, fast | Active databases, working files | Always |
| **WARM** | S3 Hetzner (4.99 EUR/month) | On-demand, API | Restic backups, seed data, recent docs | GFS retention |
| **COLD** | NAS TrueNAS (T+6 months) | Local/VPN, archive | Long-term archive, media library | Permanent |

### S3 Bucket Separation

| Bucket | Purpose | Format | Browsable |
|--------|---------|--------|:---------:|
| `vpai-backups` | Disaster recovery | Restic encrypted chunks | No |
| `vpai-shared` | Seed data, exports, documents | Raw files | Yes (Nextcloud) |

> Full details: `docs/BACKUP-STRATEGY.md`

## 6. Infrastructure Timeline

| Phase | Components Added | New Monthly Cost |
|-------|-----------------|-----------------|
| **T0 (Now)** | Preprod CX23, S3 Hetzner (2 buckets) | +8.48 EUR |
| **T+6 Weeks** | VPS Applicatif (Nextcloud, media) | +6-12 EUR |
| **T+6 Months** | NAS TrueNAS 10-12 TB (on-premises) | +5 EUR + 300 EUR one-time |

> Full details: `docs/BACKUP-STRATEGY.md` (section 8) and `docs/PREPROD-STRATEGY.md`

## 7. Startup Order

```mermaid
graph TD
    PG["PostgreSQL"] --> N8N["n8n"]
    PG --> LL["LiteLLM"]
    PG --> OC["OpenClaw"]
    RD["Redis"] --> LL
    RD --> OC
    QD["Qdrant"] --> OC
    N8N --> CDY["Caddy"]
    LL --> CDY

    VM["VictoriaMetrics"] --> ALY["Alloy"]
    LK["Loki"] --> ALY
    VM --> GF["Grafana"]
    LK --> GF

    style PG fill:#4DB6AC
    style RD fill:#4DB6AC
    style QD fill:#4DB6AC
    style N8N fill:#7986CB
    style LL fill:#7986CB
    style OC fill:#7986CB
    style CDY fill:#FFB74D
    style VM fill:#90CAF9
    style LK fill:#90CAF9
    style ALY fill:#90CAF9
    style GF fill:#90CAF9
```
