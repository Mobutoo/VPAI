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

    subgraph S3["Hetzner Object Storage"]
        Bucket["S3 Bucket"]
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
    Zerobyte -->|"push"| Bucket
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

## 5. Backup Flow

```mermaid
sequenceDiagram
    participant Cron as Cron (02:55)
    participant Script as pre-backup.sh
    participant Docker as Docker Containers
    participant VPN as VPN Mount
    participant Zerobyte as Zerobyte (03:00)
    participant S3 as Hetzner S3
    participant UK as Uptime Kuma

    Cron->>Script: Trigger
    Script->>Docker: pg_dump (3 databases)
    Script->>Docker: redis-cli BGSAVE
    Script->>Docker: qdrant snapshot
    Script->>Docker: n8n export:workflow
    Script->>VPN: Write to /opt/vpai/backups/
    Script->>UK: Heartbeat ping

    Note over Zerobyte: 03:00 — Scheduled job
    Zerobyte->>VPN: Pull backup files
    Zerobyte->>S3: Push encrypted backup
```

## 6. Startup Order

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
