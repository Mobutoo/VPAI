# ARCHITECTURE — System Diagrams

> **Project**: VPAI — Self-Hosted AI Infrastructure Stack

---

## 0. Infrastructure Réelle — État Opérationnel (2026-02-20)

### Serveurs

| Serveur | Provider | IP LAN / VPN | SSH | Rôle |
|---|---|---|---|---|
| **Sese-AI** | OVH VPS 8GB | 137.74.114.167 / 100.64.0.14 | port 804, user `mobuone` | Cerveau IA (Docker stack) |
| **Seko-VPN** | Ionos VPS | 87.106.30.160 | port 22, user `mobuone` | Hub VPN Headscale + monitoring externe |
| **Workstation Pi** | RPi5 16GB local | 192.168.1.8 / 100.64.0.1 | port 22, user `mobuone` | Mission Control + Dev |

**SSH Key** : `~/.ssh/seko-vpn-deploy` (Linux/WSL) ou `/c/Users/mmomb/.ssh/seko-vpn-deploy` (Git Bash Windows)

### DNS (domaine : `ewutelo.cloud`)

| Subdomain | IP | Cible | Accès |
|---|---|---|---|
| `javisi.ewutelo.cloud` | 100.64.0.14 | VPS Sese-AI (Tailscale) | VPN uniquement |
| `tala.ewutelo.cloud` | 100.64.0.14 | VPS Sese-AI (Tailscale) | VPN uniquement |
| `mayi.ewutelo.cloud` | 100.64.0.14 | VPS Sese-AI (Tailscale) | VPN uniquement |
| `llm.ewutelo.cloud` | 100.64.0.14 | VPS Sese-AI (Tailscale) | VPN uniquement |
| `qd.ewutelo.cloud` | 100.64.0.14 | VPS Sese-AI (Tailscale) | VPN uniquement |
| `mc.ewutelo.cloud` | 100.64.0.1 | Workstation Pi (Tailscale) | VPN uniquement |
| `oc.ewutelo.cloud` | 100.64.0.1 | Workstation Pi (Tailscale) | VPN uniquement |
| `singa.ewutelo.cloud` | 87.106.30.160 | Seko-VPN | Public (Headscale control plane) |

> Tous les records ci-dessus sont définis dans `extra_records` de la config Headscale sur Seko-VPN :
> `/opt/services/headscale/config/config.yaml`

### Headscale — Mesh VPN

```
Seko-VPN (87.106.30.160)
  └─ headscale/headscale:0.26.0 (Docker Compose)
       URL : https://singa.ewutelo.cloud
       Config : /opt/services/headscale/config/config.yaml
       Nodes :
         100.64.0.1  workstation-pi  (RPi5 Ubuntu)
         100.64.0.2  ewutelo         (PC Windows)
         100.64.0.14 sese            (VPS OVH Debian)
```

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
            OpenClaw["OpenClaw<br/>:18789"]
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
        WebhookRelay["Webhook Relay\n(Caddy apt)"]
    end

    subgraph S3["Hetzner Object Storage (4.99 EUR/month)"]
        BackupBucket["vpai-backups<br/>(Restic encrypted)"]
        SharedBucket["vpai-shared<br/>(raw files)"]
    end

    subgraph Preprod["Preprod (Hetzner CX23 — 3.49 EUR/month)"]
        PreprodStack["VPAI Mirror<br/>(seeded from S3)"]
    end

    Internet -->|":443 HTTPS (public: health + webhooks relay)"| Caddy
    VPNClient["Client VPN\n(Tailscale)"] -->|"Tailscale mesh\n(100.64.x.x)"| Caddy
    Caddy -->|"reverse proxy\n(VPN-only ACL)"| n8n
    Caddy -->|"reverse proxy\n(VPN-only ACL)"| LiteLLM
    Caddy -->|"reverse proxy\n(VPN-only ACL)"| OpenClaw
    Caddy -->|"reverse proxy\n(VPN-only ACL)"| Grafana
    Caddy -->|"reverse proxy\n(VPN-only ACL)"| Qdrant

    n8n --> PostgreSQL
    LiteLLM --> PostgreSQL
    LiteLLM --> Redis
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

## 1.5. Workstation Pi — Architecture Locale

```
Raspberry Pi 5 (16GB RAM, SSD 256Go, Ubuntu Server 24.04 LTS ARM64)
IP LAN : 192.168.1.8  |  IP Tailscale : 100.64.0.1

┌─────────────────────────────────────────────────────────────────┐
│                    Workstation Pi                               │
│                                                                 │
│  ┌──────────────────┐     ┌──────────────────┐                 │
│  │  Mission Control │     │    OpenCode       │                 │
│  │  (Next.js 14)    │     │  (v1.2.8 headless)│                 │
│  │  Port 4000       │     │  Port 3456        │                 │
│  │  v1.1.0          │     │  → LiteLLM API   │                 │
│  └────────┬─────────┘     └──────────────────┘                 │
│           │ WSS                                                 │
│           ▼                                                     │
│  ┌──────────────────┐     ┌──────────────────┐                 │
│  │     Caddy        │     │  Claude Code CLI │                 │
│  │  v2.10.2+OVH    │     │  v2.1.49         │                 │
│  │  :80 :443        │     │  OAuth Max Plan  │                 │
│  │  DNS-01 TLS      │     │  ~/.claude/      │                 │
│  └──────────────────┘     └──────────────────┘                 │
│                                                                 │
│  ┌──────────────────┐                                           │
│  │   Tailscale      │  ←──── Headscale (singa.ewutelo.cloud)   │
│  │  100.64.0.1      │                                           │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Chemins importants sur le Pi

| Chemin | Contenu |
|---|---|
| `/opt/workstation/configs/caddy/Caddyfile` | Config Caddy (mc + oc reverse proxy) |
| `/opt/workstation/configs/opencode/opencode.json` | Config OpenCode (provider LiteLLM) |
| `/opt/workstation/mission-control/.env` | Config MC (OPENCLAW_GATEWAY_URL, etc.) |
| `/opt/workstation/data/mission-control/mission-control.db` | SQLite Mission Control |
| `/home/mobuone/.claude/` | Tokens OAuth Claude Code CLI |
| `/usr/bin/caddy` | Caddy buildé via xcaddy (avec OVH DNS module) |
| `/usr/bin/opencode` | OpenCode CLI (npm global NodeSource) |
| `/usr/bin/claude` | Claude Code CLI (npm global NodeSource) |
| `/usr/local/go/` | Go 1.24.2 (installé manuellement — Ubuntu 24.04 fournit 1.22) |
| `/root/go/bin/xcaddy` | xcaddy v0.4.5 |

### Services systemd sur le Pi

```bash
systemctl status caddy-workstation    # Caddy :80/:443 TLS OVH DNS-01
systemctl status mission-control       # Next.js :4000
systemctl status opencode              # OpenCode :3456 → LiteLLM
tailscale status                       # VPN mesh (sudo requis)
```

### Flux Mission Control ↔ OpenClaw

```
Browser (VPN) ──HTTPS──► mc.ewutelo.cloud ──► Caddy Pi :443
                                                    │
                                              reverse_proxy :4000
                                                    │
                                          Mission Control (Next.js)
                                                    │
                                    WSS wss://javisi.ewutelo.cloud
                                                    │
                          ◄──────── Tailscale mesh ─────────►
                                                    │
                                            OpenClaw (VPS)
                                                    │
                                              LiteLLM :4000
                                                    │
                                          Anthropic / OpenRouter
```

### Auth et Billing IA

| Outil | Auth | Billing |
|---|---|---|
| **Claude Code CLI** (`claude`) | OAuth Max Plan (`~/.claude/`) | Quota abonnement — gratuit |
| **OpenCode** | `LITELLM_API_KEY` env var | Via LiteLLM → budget $5/jour |
| **OpenClaw** | `openclaw_api_key` | Via LiteLLM → budget $5/jour |
| **n8n** | `litellm_master_key` | Via LiteLLM → budget $5/jour |

> **Claude Code OAuth** : auth manuelle une seule fois via `claude` en SSH (lien URL affiché dans le terminal,
> à ouvrir dans le navigateur). Tokens dans `~/.claude/`, auto-renouvelés. Ne PAS mettre `ANTHROPIC_API_KEY`
> dans l'environnement — ça court-circuiterait OAuth.

---

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

## 2.5 VPN Access Control — Split DNS

```
Client Windows (Tailscale connecté)
    │
    ├─ DNS query: mayi.ewutelo.cloud
    │   └─ DNS Tailscale (100.100.100.100) → extra_records Headscale
    │       └─ Répond: 100.64.0.14 (IP Tailscale du VPS)
    │
    └─ HTTPS → 100.64.0.14:443 → Docker DNAT → Caddy
        └─ client_ip = 172.20.1.1 (gateway bridge Docker, HTTP/3 QUIC/UDP)
        └─ 172.20.1.0/24 autorisé dans snippet vpn_only → Accès OK
```

Sans Split DNS (ou `override_local_dns: false`) :
```
Client → DNS public → 137.74.114.167 (IP publique VPS)
    └─ HTTPS → IP publique → Caddy
        └─ client_ip = IP publique client → NOT IN 100.64.0.0/10 → 403 Forbidden
```

## 3. Service Matrix

| Service | Frontend | Backend | Monitoring | Egress | Ports | Subdomain |
|---------|:--------:|:-------:|:----------:|:------:|-------|-----------|
| Caddy | X | X | | | 80, 443 | `domain` (root) |
| PostgreSQL | | X | | | 5432 | — (internal) |
| Redis | | X | | | 6379 | — (internal) |
| Qdrant | | X | | | 6333 | `qdrant_subdomain` |
| n8n | | X | | X | 5678 | `n8n_subdomain` |
| LiteLLM | | X | | X | 4000 | `litellm_subdomain` |
| OpenClaw | | X | | X | 18789 | `admin_subdomain` |
| VictoriaMetrics | | | X | | 8428 | — (internal) |
| Loki | | | X | | 3100 | — (internal) |
| Alloy | | X | X | | 12345 | — (internal) |
| Grafana | X | | X | | 3000 | `grafana_subdomain` |
| DIUN | | | | | — | — |

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
    RD["Redis"] --> LL
    QD["Qdrant"]
    LL --> OC["OpenClaw"]
    N8N --> CDY["Caddy"]
    LL --> CDY
    OC --> CDY
    QD --> CDY
    GF["Grafana"] --> CDY

    VM["VictoriaMetrics"] --> ALY["Alloy"]
    LK["Loki"] --> ALY
    VM --> GF
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

> **Note** : OpenClaw est un agent IA Gateway WebSocket (port 18789), file-based.
> Il ne depend PAS de PostgreSQL, Redis ou Qdrant. Il utilise LiteLLM comme proxy LLM.
