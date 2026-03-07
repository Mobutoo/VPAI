# PRD — Palais v2: Multi-Project Infrastructure Operations Cockpit

> **Version**: 2.0.0
> **Date**: 2026-03-07
> **Status**: Draft — Pending implementation
> **Author**: Mobutoo (generated with Claude Code)
> **Supersedes**: `docs/PRD-PALAIS.md` (v1 — archived)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Problem Statement](#2-problem-statement)
3. [Goals](#3-goals)
4. [Non-Goals](#4-non-goals)
5. [User Stories](#5-user-stories)
6. [Technical Architecture](#6-technical-architecture)
7. [Database Schema](#7-database-schema)
8. [API Design](#8-api-design)
9. [UI/UX Design](#9-uiux-design)
10. [Security](#10-security)
11. [Performance](#11-performance)
12. [Phased Implementation](#12-phased-implementation)
13. [Success Metrics](#13-success-metrics)
14. [Risks & Mitigations](#14-risks--mitigations)

---

## 1. Overview

Palais is a self-hosted, AI-augmented infrastructure operations cockpit built on SvelteKit 5. In v1, it served as a project management and AI operations dashboard. With **Plane** now handling project/task management and **Zimboo** handling personal finance, Palais v2 is reoriented as the **Multi-Project Infrastructure Operations Cockpit** — the single pane of glass for managing servers, containers, deployments, costs, and domains across all self-hosted projects.

Palais v2 is the operator console for a solo founder running multiple SaaS and infrastructure projects on heterogeneous cloud providers (OVH, Hetzner, Ionos). It replaces the need to maintain terminal sessions across multiple servers, juggle provider dashboards, and manually trigger deployments.

The defining feature that distinguishes Palais from generic dashboards is its **Afrofuturist design identity** and its **MCP server integration** — exposing all infrastructure operations as tools callable by Claude Code and OpenClaw agents.

### System Context

```
User (browser over VPN)
       │
       ▼
  Caddy (TLS, VPN-only ACL)
       │
       ▼
  Palais v2 (SvelteKit 5, Node.js 22 Alpine)
  ┌─────────────────────────────────────────┐
  │  9 Modules: Fleet, Workspaces,          │
  │  Services, Deploy, Costs, Domains,      │
  │  Terminal, Waza, Memory+MCP             │
  └─────────────────────────────────────────┘
       │         │          │         │
       ▼         ▼          ▼         ▼
  PostgreSQL   Qdrant    External   SSH
  (palais DB)  (memory)   APIs     Remote
                        (Hetzner,
                         OVH, Namecheap,
                         Headscale, n8n)
```

---

## 2. Problem Statement

### Current Pain Points

**Problem 1 — Multi-server context switching.** Managing infrastructure across 4+ servers (Sese-AI/OVH, Seko-VPN/Ionos, Waza/RPi5, App-Prod/Hetzner) requires opening multiple SSH terminals. There is no unified real-time view of server health, container status, or resource utilization.

**Problem 2 — Deployment friction.** Deploying updates to any project requires: SSH to the correct server, `git pull`, `docker compose up`, manual smoke test verification. No deploy history, no rollback UI, no visual pipeline progress.

**Problem 3 — Cost visibility is fragmented.** Infrastructure costs live in 3+ provider dashboards (OVH, Hetzner, Namecheap) plus LiteLLM budget. There is no unified monthly cost view, no per-project allocation, and no projection for the next billing cycle.

**Problem 4 — DNS management is manual and error-prone.** Adding a subdomain for a new tenant, updating a DNS record after a server migration, or checking certificate status requires logging into registrar UIs or running `curl` against the OVH API.

**Problem 5 — Local services on Waza (RPi5) have no management UI.** Starting ComfyUI for an art session or Remotion for video rendering requires SSH. There is no resource pre-flight check and no way to start a "profile" of related services at once.

**Problem 6 — No unified agent interface for infrastructure operations.** Claude Code and OpenClaw agents cannot query or control infrastructure programmatically. Every infrastructure action requires dropping out of the AI workflow into a terminal.

### Root Cause

Palais v1 solved the wrong problem — it duplicated Plane's project management capabilities while neglecting the core value of an infrastructure cockpit: observability, control, and automation of the self-hosted stack itself.

---

## 3. Goals

### Primary Goals (Must Have)

| ID | Goal | Module |
|----|------|--------|
| G1 | Single real-time view of all servers, containers, and resource utilization | Fleet |
| G2 | One-click deployment and rollback for all projects from a web UI | Deploy |
| G3 | Unified monthly cost view with per-project allocation and projections | Costs |
| G4 | Full DNS record management (read/write) for Namecheap and OVH domains | Domains |
| G5 | Browser-based SSH terminal for any server over VPN | Terminal |
| G6 | One-click start/stop for on-demand local services on Waza | Waza |
| G7 | MCP server exposing all infrastructure operations as Claude-callable tools | Memory+MCP |

### Secondary Goals (Should Have)

| ID | Goal | Module |
|----|------|--------|
| G8 | Per-project workspace with deployment history and metrics | Workspaces |
| G9 | Docker container management (start/stop/restart/logs) across all servers | Services |
| G10 | Cost optimizer recommendations (idle VPS, stale snapshots, LLM model routing) | Costs |
| G11 | Knowledge graph (Qdrant + PostgreSQL) for infrastructure context and AI memory | Memory+MCP |

### Tertiary Goals (Nice to Have)

| ID | Goal | Module |
|----|------|--------|
| G12 | GitOps auto-deploy on Forgejo push via webhook | Deploy |
| G13 | Resource forecast before starting containers | Services |
| G14 | Headscale VPN node status and latency monitoring | Fleet |

---

## 4. Non-Goals

The following are explicitly out of scope for Palais v2:

- **Project and task management** — Delegated to Plane (project boards, sprints, issues).
- **Personal finance tracking** — Delegated to Zimboo + Firefly III (bank transactions, budgets, charts).
- **AI budget management UI** — LiteLLM's own UI handles this; Palais only reads budget status for cost aggregation.
- **Creative tools hosting** — ComfyUI, OpenCut run on Waza; Palais only provides start/stop control.
- **User management / multi-tenancy** — Palais is a single-operator tool. Auth is admin password + API key.
- **Public-facing endpoints** — Palais is VPN-only. No customer-facing dashboards.
- **Log aggregation and alerting** — Delegated to Grafana + Loki + VictoriaMetrics + Alloy (already deployed).
- **Incident management** — Delegated to n8n + Telegram notifications.

---

## 5. User Stories

### Epic 1: Fleet Visibility

**US-1.1** — As an operator, I want to see all servers with their provider, IP, CPU%, RAM%, disk%, and status on a single page, so that I can immediately identify which server is under pressure without opening multiple tabs.

**US-1.2** — As an operator, I want to see all Docker containers per server with their image version, RAM usage vs limit, and health status, so that I can spot an unhealthy container before it becomes an outage.

**US-1.3** — As an operator, I want a totals bar (VPS count, containers running, monthly infra cost) visible at all times, so that I have a constant pulse on the stack without deep-diving.

**US-1.4** — As an operator, I want to receive a Telegram alert when a server goes down or a container becomes unhealthy, so that I am notified proactively and not by a customer complaint.

### Epic 2: Workspaces

**US-2.1** — As an operator, I want each side project (Flash Studio, VPAI, etc.) to have its own workspace card showing the current deployed version, server assignment, domain, and status, so that I can answer "what is running where?" in under 10 seconds.

**US-2.2** — As an operator, I want to trigger a deployment (git pull + docker compose up) for any project from the UI with a single click, so that I can ship updates without opening a terminal.

**US-2.3** — As an operator, I want to see a real-time deploy log stream in the UI when a deployment is running, so that I can monitor progress and catch errors immediately.

**US-2.4** — As an operator, I want to roll back to the previous deployed version with a confirmation modal, so that I can recover from a bad deploy in under 2 minutes.

### Epic 3: Services (Docker Control)

**US-3.1** — As an operator, I want to restart a specific Docker container from the Palais UI without needing to SSH into the server, so that I can resolve a hung service in under 30 seconds.

**US-3.2** — As an operator, I want to view the last 200 log lines for any container with level filtering, so that I can diagnose an error without switching to a terminal.

**US-3.3** — As an operator, I want to see a dependency graph warning when I try to restart a shared service (like PostgreSQL), so that I understand the blast radius before acting.

### Epic 4: Deploy Pipeline

**US-4.1** — As an operator, I want to see a visual step-by-step deploy pipeline (Checkout → Build → Tests → Deploy → Smoke Tests) with real-time progress, so that I know exactly where a deployment is in the process.

**US-4.2** — As an operator, I want the deploy to be triggered automatically when I push to the main branch of a Forgejo repo, so that I do not have to manually initiate deployments.

**US-4.3** — As an operator, I want to cancel a running deployment in progress from the UI, so that I can stop a bad deploy before it completes.

### Epic 5: Costs

**US-5.1** — As an operator, I want to see my total infrastructure cost for the current month broken down by provider (Hetzner, OVH, Namecheap, LiteLLM), so that I can track spending against my budget.

**US-5.2** — As an operator, I want a month-over-month trend and a projected end-of-month total, so that I can anticipate whether I am on track with my infrastructure budget.

**US-5.3** — As an operator, I want the cost optimizer to flag idle servers, stale snapshots, and expensive LLM routing patterns, so that I can act on savings opportunities without hunting through provider dashboards.

### Epic 6: Domains

**US-6.1** — As an operator, I want to see all my domains across registrars with their expiry date and auto-renew status, so that I never accidentally let a domain expire.

**US-6.2** — As an operator, I want to add, edit, or delete DNS records for any domain directly from the Palais UI without logging into the registrar dashboard, so that I can make DNS changes in under 2 minutes.

**US-6.3** — As a SaaS builder, I want to create a new tenant subdomain (e.g., client.jemeforme.ai) via the Palais UI, so that onboarding a new customer takes seconds instead of minutes.

### Epic 7: Terminal

**US-7.1** — As an operator, I want to open a browser-based SSH terminal to any server from the Palais UI over VPN, so that I have an emergency shell without needing a local SSH client.

**US-7.2** — As an operator, I want to have multiple terminal tabs open to different servers simultaneously, so that I can run commands in parallel.

### Epic 8: Waza

**US-8.1** — As an operator, I want to start the "Video Mode" profile (OpenCut + Remotion + ComfyUI) on Waza with a single click and see a RAM warning if resources are insufficient, so that I can start creative sessions quickly.

**US-8.2** — As an operator, I want to stop all on-demand Waza services at once, so that I can reclaim RAM for other tasks without SSH.

### Epic 9: Memory + MCP

**US-9.1** — As an operator using Claude Code, I want to ask "What is the RAM usage on Sese-AI right now?" and get an accurate answer, because Palais exposes fleet data as an MCP tool.

**US-9.2** — As an operator using OpenClaw, I want an agent to trigger a deployment of Flash Studio via Palais's MCP interface, so that I can orchestrate infrastructure changes from within an agent session.

**US-9.3** — As an operator, I want the Qdrant-backed knowledge graph to retain context about past deployments, DNS changes, and cost decisions, so that Claude Code agents have long-term memory about the infrastructure.

---

## 6. Technical Architecture

### 6.1 Stack (Unchanged from v1)

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | SvelteKit 5 (adapter-node) | Runes: `$state`, `$derived`, `$effect`, `$props` |
| ORM | Drizzle ORM | PostgreSQL dialect, migrations via `drizzle-kit` |
| Database | PostgreSQL 18.1 | Shared instance, `palais` database |
| Vector DB | Qdrant v1.16.3 | Collection: `palais_memory` |
| Styling | Tailwind v4 | Custom Afrofuturist theme |
| Components | bits-ui | Headless accessible components |
| Drag & Drop | svelte-dnd-action | For pipeline and workspace ordering |
| Charting | d3-force, d3-scale, d3-time | Memory graph, cost charts, sparklines |
| Terminal | xterm.js + WebSocket | New in v2 |
| WebSocket | ws | Server-side WebSocket for terminal |
| SSE | Native SvelteKit | Deploy logs, container stats streaming |
| Runtime | Node.js 22 Alpine | Container: 256MB RAM, 1.0 CPU |

### 6.2 New External Integrations (v2 Only)

| Integration | Library | Purpose |
|-------------|---------|---------|
| Hetzner Cloud API | `@hetzner-cloud/node` or `hcloud` npm | Fleet, Costs, Workspaces (provision VPS) |
| OVH API | `ovh` npm package | Fleet (VPS status), Costs, Domains (DNS) |
| Headscale REST API | `fetch` (Bearer auth) | Fleet (VPN nodes, latency, last seen) |
| Docker SSH Remote | `node-ssh` | Services (container control), Fleet (stats) |
| Namecheap XML API | Custom client (XML over HTTPS) | Domains (DNS record CRUD, domain list) |
| n8n Webhooks | `fetch` | Deploy triggers, budget alerts |
| LiteLLM REST API | `fetch` | Costs (budget/info endpoint) |
| Forgejo/GitHub API | `fetch` | Workspaces (repo info, webhooks) |
| Telegram Bot API | Via n8n | Alert delivery (no direct integration) |

### 6.3 Data Flow Patterns

**Fleet refresh (polling, 5-minute interval):**
```
Cron (server-side, every 5 min)
  → Hetzner API (server list, volumes, billing)
  → OVH API (VPS status)
  → Headscale API (VPN nodes)
  → SSH Docker stats per server
  → Upsert to `servers` + `server_metrics` tables
  → Invalidate SSE broadcast to connected clients
```

**Deployment trigger (event-driven):**
```
User clicks Deploy / Forgejo webhook arrives
  → POST /api/v2/workspaces/:id/deploy
  → Insert `deployments` row (status: pending)
  → POST to n8n webhook (deploy trigger)
  → n8n → Ansible Runner → callback webhooks per step
  → Palais /api/v2/deploy/callback (HMAC-validated)
  → Update `deployment_steps` rows
  → SSE broadcast to /api/v2/deploy/pipelines/:id/status
  → Client renders real-time step progress
```

**Terminal session (WebSocket):**
```
Client connects to /api/v2/terminal/ws?server=sese-ai
  → Palais backend authenticates (session cookie or API key)
  → node-ssh opens SSH tunnel to target server
  → stdin/stdout piped through WebSocket ↔ xterm.js
  → On disconnect: SSH session closed, resources released
```

**MCP tool call (JSON-RPC 2.0 over SSE):**
```
Claude Code → POST /api/mcp (JSON-RPC request)
  → Palais authenticates via X-Api-Key header
  → Dispatches to tool handler (palais.fleet.getServers, etc.)
  → Handler reads from DB (cached) or calls external API
  → Returns JSON-RPC response
```

### 6.4 Deployment Architecture (Ansible Role)

Palais runs as a Docker container on Sese-AI (OVH VPS):

```yaml
# docker-compose.yml (Phase B — Applications)
palais:
  image: "ghcr.io/mobutoo/palais:{{ palais_version }}"
  container_name: "{{ project_name }}_palais"
  restart: unless-stopped
  networks: [frontend, backend]
  environment:
    DATABASE_URL: "postgresql://palais:{{ postgresql_password }}@postgresql:5432/palais"
    QDRANT_URL: "http://qdrant:6333"
    QDRANT_API_KEY: "{{ qdrant_api_key }}"
    PALAIS_API_KEY: "{{ vault_palais_api_key }}"
    PALAIS_ADMIN_PASSWORD: "{{ vault_palais_admin_password }}"
    HETZNER_API_TOKEN: "{{ vault_hetzner_api_token }}"
    OVH_ENDPOINT: "{{ ovh_endpoint }}"
    OVH_APPLICATION_KEY: "{{ ovh_application_key }}"
    OVH_APPLICATION_SECRET: "{{ ovh_application_secret }}"
    OVH_CONSUMER_KEY: "{{ ovh_consumer_key }}"
    NAMECHEAP_API_USER: "{{ vault_namecheap_api_user }}"
    NAMECHEAP_API_KEY: "{{ vault_namecheap_api_key }}"
    NAMECHEAP_CLIENT_IP: "{{ vault_namecheap_client_ip }}"
    HEADSCALE_URL: "{{ vpn_headscale_url }}"
    HEADSCALE_API_KEY: "{{ vault_headscale_api_key }}"
    DOCKER_SSH_SERVERS: "sese-ai:100.64.0.14:804,app-prod:{{ vault_app_prod_ip }}:22,waza:{{ vault_waza_ip }}:22"
    DOCKER_SSH_KEY_PATH: "/data/ssh/deploy-key"
    FORGEJO_URL: "http://waza.local:3000"
    FORGEJO_TOKEN: "{{ vault_forgejo_token }}"
    LITELLM_API_URL: "http://litellm:4000"
    LITELLM_API_KEY: "{{ litellm_master_key }}"
    N8N_WEBHOOK_BASE_URL: "http://n8n:5678"
    N8N_WEBHOOK_SECRET: "{{ n8n_webhook_secret }}"
    NODE_ENV: "production"
    ORIGIN: "https://{{ palais_subdomain }}.{{ domain_name }}"
  mem_limit: 256m
  cpus: 1.0
  cap_drop: [ALL]
  cap_add: [NET_BIND_SERVICE]
  healthcheck:
    test: ["CMD", "wget", "-qO-", "http://localhost:3000/api/health"]
    interval: 30s
    timeout: 10s
    retries: 3
  volumes:
    - "{{ palais_ssh_key_path }}:/data/ssh/deploy-key:ro"
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
```

Palais is built as a Docker image and pushed to GHCR during CI. The Ansible role pulls the pinned image, manages env_file, and handles zero-downtime restarts using `state: present` + `recreate: always` (consistent with the `env_file` handler pattern documented in CLAUDE.md).

---

## 7. Database Schema

### 7.1 Tables to DROP (from v1)

All project/task management tables are removed. Plane owns this domain.

```sql
DROP TABLE IF EXISTS
  workspaces, projects, columns, tasks, task_dependencies,
  labels, task_labels, comments, activity_log, time_entries,
  task_iterations, deliverables, budget_snapshots, budget_forecasts,
  insights, ideas, idea_versions, idea_links, missions,
  mission_conversations;
```

### 7.2 Tables to KEEP (from v1)

```sql
-- Knowledge graph (Memory module)
memory_nodes       -- Qdrant-linked knowledge entities
memory_edges       -- Relationships between nodes

-- Agent registry (read-only display — management via Plane)
agents             -- OpenClaw agent definitions

-- Health monitoring (extended into Fleet)
health_checks      -- Endpoint health records
backup_status      -- Zerobyte backup status

-- Infrastructure nodes (extended)
nodes              -- Extended with server_id FK
```

### 7.3 New Tables (v2)

#### `projects_registry`
Defines each side project managed by Palais.

```sql
CREATE TABLE projects_registry (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        TEXT NOT NULL UNIQUE,          -- 'flash-studio', 'vpai', 'jemeforme'
  name        TEXT NOT NULL,                 -- Display name
  description TEXT,
  repo_url    TEXT,                          -- Forgejo or GitHub URL
  repo_branch TEXT NOT NULL DEFAULT 'main',
  stack       TEXT,                          -- 'sveltekit+pg', 'nextjs+supabase', etc.
  server_id   UUID REFERENCES servers(id),   -- Primary deployment server
  domain      TEXT,                          -- 'flashstudio.xyz'
  subdomain   TEXT,                          -- null if root domain
  status      TEXT NOT NULL DEFAULT 'active', -- active | paused | archived
  color       TEXT,                          -- Hex color for UI accent
  icon        TEXT,                          -- Lucide icon name
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `servers`
Infrastructure server registry across all providers.

```sql
CREATE TABLE servers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          TEXT NOT NULL UNIQUE,          -- 'sese-ai', 'app-prod', 'waza'
  name          TEXT NOT NULL,
  provider      TEXT NOT NULL,                 -- 'ovh' | 'hetzner' | 'ionos' | 'local'
  provider_id   TEXT,                          -- Provider's internal ID (e.g. Hetzner server ID)
  server_type   TEXT,                          -- 'vps-8gb', 'cx22', 'rpi5'
  public_ip     TEXT,
  tailscale_ip  TEXT,
  ssh_port      INTEGER NOT NULL DEFAULT 22,
  ssh_user      TEXT NOT NULL DEFAULT 'root',
  role          TEXT NOT NULL,                 -- 'prod' | 'preprod' | 'vpn' | 'workstation'
  os            TEXT,                          -- 'debian-13'
  ram_gb        INTEGER,
  cpu_cores     INTEGER,
  disk_gb       INTEGER,
  monthly_cost  NUMERIC(10, 4),               -- EUR, from provider API
  status        TEXT NOT NULL DEFAULT 'unknown', -- online | offline | unknown | maintenance
  last_seen_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `server_metrics`
Time-series snapshots of server resource utilization.

```sql
CREATE TABLE server_metrics (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  server_id    UUID NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
  recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  cpu_pct      NUMERIC(5, 2),
  ram_used_mb  INTEGER,
  ram_total_mb INTEGER,
  disk_used_gb NUMERIC(10, 2),
  disk_total_gb NUMERIC(10, 2),
  network_rx_mb NUMERIC(10, 2),
  network_tx_mb NUMERIC(10, 2),
  container_count INTEGER,
  containers_unhealthy INTEGER DEFAULT 0
);

CREATE INDEX idx_server_metrics_server_time
  ON server_metrics (server_id, recorded_at DESC);
```

#### `deployments`
Deployment history per project workspace.

```sql
CREATE TABLE deployments (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects_registry(id) ON DELETE CASCADE,
  server_id       UUID NOT NULL REFERENCES servers(id),
  trigger         TEXT NOT NULL,              -- 'manual' | 'webhook' | 'scheduled'
  triggered_by    TEXT,                       -- 'user' | 'forgejo-push' | 'n8n'
  strategy        TEXT NOT NULL DEFAULT 'direct', -- 'direct' | 'blue-green' | 'canary'
  git_sha         TEXT,
  git_branch      TEXT NOT NULL DEFAULT 'main',
  git_message     TEXT,
  version_from    TEXT,                       -- Previous version tag
  version_to      TEXT,                       -- Target version tag
  status          TEXT NOT NULL DEFAULT 'pending', -- pending | running | success | failed | cancelled | rolled_back
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  n8n_execution_id TEXT,                      -- n8n execution ID for cross-reference
  error_message   TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_deployments_project_time
  ON deployments (project_id, created_at DESC);
```

#### `deployment_steps`
Individual steps within a deployment pipeline.

```sql
CREATE TABLE deployment_steps (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  deployment_id UUID NOT NULL REFERENCES deployments(id) ON DELETE CASCADE,
  step_index    INTEGER NOT NULL,             -- 0-based ordering
  name          TEXT NOT NULL,               -- 'checkout' | 'build' | 'tests' | 'migrate' | 'deploy' | 'smoke-tests' | 'dns-check'
  status        TEXT NOT NULL DEFAULT 'pending', -- pending | running | success | failed | skipped
  log_output    TEXT,                        -- Captured stdout/stderr
  started_at    TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ,
  duration_ms   INTEGER
);
```

#### `domains`
Domain inventory across all registrars.

```sql
CREATE TABLE domains (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL UNIQUE,       -- 'jemeforme.ai', 'ewutelo.cloud'
  registrar       TEXT NOT NULL,              -- 'namecheap' | 'ovh' | 'other'
  dns_provider    TEXT NOT NULL,              -- 'namecheap' | 'ovh' | 'cloudflare'
  expiry_date     DATE,
  auto_renew      BOOLEAN DEFAULT true,
  whois_privacy   BOOLEAN DEFAULT false,
  status          TEXT NOT NULL DEFAULT 'active', -- active | expired | pending-transfer
  project_id      UUID REFERENCES projects_registry(id),
  notes           TEXT,
  last_checked_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `dns_records`
DNS record cache (synced from registrar APIs).

```sql
CREATE TABLE dns_records (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id   UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  type        TEXT NOT NULL,                  -- 'A' | 'AAAA' | 'CNAME' | 'MX' | 'TXT' | 'CAA'
  name        TEXT NOT NULL,                  -- '@' | 'www' | 'app' | '*'
  value       TEXT NOT NULL,
  ttl         INTEGER NOT NULL DEFAULT 3600,
  priority    INTEGER,                        -- MX priority
  registrar_id TEXT,                          -- Registrar's internal record ID
  synced_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (domain_id, type, name, value)
);
```

#### `cost_snapshots`
Hourly cost snapshots per provider.

```sql
CREATE TABLE cost_snapshots (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider     TEXT NOT NULL,                 -- 'hetzner' | 'ovh' | 'namecheap' | 'litellm' | 'other'
  period_year  INTEGER NOT NULL,
  period_month INTEGER NOT NULL,              -- 1-12
  amount_eur   NUMERIC(10, 4) NOT NULL,
  currency     TEXT NOT NULL DEFAULT 'EUR',
  breakdown    JSONB,                         -- { "servers": 12.50, "s3": 0.80, "traffic": 0.20 }
  recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, period_year, period_month)
);
```

#### `cost_forecasts`
Linear regression forecasts for end-of-month cost projection.

```sql
CREATE TABLE cost_forecasts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  period_year    INTEGER NOT NULL,
  period_month   INTEGER NOT NULL,
  provider       TEXT NOT NULL,
  projected_eur  NUMERIC(10, 4) NOT NULL,
  confidence_pct INTEGER,                     -- 0-100
  model          TEXT NOT NULL DEFAULT 'linear', -- 'linear' | 'moving-avg'
  generated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, period_year, period_month)
);
```

#### `waza_services`
On-demand service registry for Waza (RPi5).

```sql
CREATE TABLE waza_services (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug           TEXT NOT NULL UNIQUE,        -- 'comfyui', 'opencut', 'remotion'
  name           TEXT NOT NULL,
  description    TEXT,
  service_type   TEXT NOT NULL DEFAULT 'docker', -- 'docker' | 'systemd' | 'process'
  docker_image   TEXT,
  docker_compose_service TEXT,               -- Service name in docker-compose.yml
  ram_mb_estimate INTEGER,                   -- Expected RAM usage for pre-flight check
  always_on      BOOLEAN NOT NULL DEFAULT false,
  status         TEXT NOT NULL DEFAULT 'stopped', -- running | stopped | starting | stopping | error
  port           INTEGER,
  url_path       TEXT,                        -- '/comfyui', for link in UI
  profiles       TEXT[],                      -- ['video', 'art', 'dev']
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 7.4 Schema Summary

| Table | Action | Owner Module |
|-------|--------|-------------|
| `memory_nodes` | KEEP | Memory+MCP |
| `memory_edges` | KEEP | Memory+MCP |
| `agents` | KEEP (read-only) | Fleet (display) |
| `health_checks` | KEEP → extend | Fleet |
| `backup_status` | KEEP | Fleet |
| `nodes` | KEEP → extend | Fleet |
| `projects_registry` | NEW | Workspaces |
| `servers` | NEW | Fleet |
| `server_metrics` | NEW | Fleet |
| `deployments` | NEW | Deploy |
| `deployment_steps` | NEW | Deploy |
| `domains` | NEW | Domains |
| `dns_records` | NEW | Domains |
| `cost_snapshots` | NEW | Costs |
| `cost_forecasts` | NEW | Costs |
| `waza_services` | NEW | Waza |
| ~~`workspaces`~~ | DROP | — |
| ~~`projects`~~ | DROP | — |
| ~~`tasks`~~ | DROP | — |
| ~~`budget_snapshots`~~ | DROP | — |
| ~~`ideas`~~ | DROP | — |
| ~~`missions`~~ | DROP | — |
| (12 more v1 tables) | DROP | — |

---

## 8. API Design

All new v2 endpoints are under `/api/v2/`. All v1 MCP and memory endpoints are preserved at `/api/v1/` and `/api/mcp`.

### 8.1 Authentication

Two auth mechanisms, no changes from v1:

- **Cookie (browser sessions):** `POST /api/auth/login` with admin password → `Set-Cookie: palais-session=...` (httpOnly, Secure, SameSite=Strict)
- **API Key (agents, n8n):** `X-Api-Key: <palais_api_key>` header on all requests

### 8.2 Fleet

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/fleet/servers` | List all servers with latest metrics |
| GET | `/api/v2/fleet/servers/:id` | Single server detail + metric history (24h) |
| POST | `/api/v2/fleet/servers` | Register a new server |
| PUT | `/api/v2/fleet/servers/:id` | Update server metadata |
| DELETE | `/api/v2/fleet/servers/:id` | Deregister server |
| GET | `/api/v2/fleet/servers/:id/containers` | Docker containers for server |
| GET | `/api/v2/fleet/servers/:id/metrics` | Time-series metrics (query param: `hours=24`) |
| POST | `/api/v2/fleet/sync` | Force refresh from all provider APIs |
| GET | `/api/v2/fleet/summary` | Totals (VPS count, container count, cost, unhealthy count) |

**Response shape (`GET /api/v2/fleet/servers`):**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "slug": "sese-ai",
      "name": "Sese-AI",
      "provider": "ovh",
      "server_type": "vps-8gb",
      "public_ip": "137.74.114.167",
      "tailscale_ip": "100.64.0.14",
      "status": "online",
      "metrics": {
        "cpu_pct": 23.4,
        "ram_used_mb": 5120,
        "ram_total_mb": 8192,
        "disk_used_gb": 42.1,
        "disk_total_gb": 75,
        "container_count": 14,
        "containers_unhealthy": 0
      },
      "monthly_cost": 22.40
    }
  ],
  "meta": { "total": 4, "synced_at": "2026-03-07T10:00:00Z" }
}
```

### 8.3 Workspaces

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/workspaces` | List all project workspaces |
| GET | `/api/v2/workspaces/:id` | Single workspace detail + deploy history |
| POST | `/api/v2/workspaces` | Create workspace |
| PUT | `/api/v2/workspaces/:id` | Update workspace metadata |
| DELETE | `/api/v2/workspaces/:id` | Archive workspace |
| POST | `/api/v2/workspaces/:id/deploy` | Trigger deployment |
| POST | `/api/v2/workspaces/:id/rollback` | Rollback to previous deployment |

### 8.4 Services

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/services/:serverId` | List containers on server with stats |
| POST | `/api/v2/services/:serverId/:container/start` | Start container |
| POST | `/api/v2/services/:serverId/:container/stop` | Stop container |
| POST | `/api/v2/services/:serverId/:container/restart` | Restart container |
| GET | `/api/v2/services/:serverId/:container/logs` | Last N log lines (query: `n=200&level=error`) |
| GET | `/api/v2/services/:serverId/:container/logs/stream` | SSE log streaming |

### 8.5 Deploy

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/deploy/pipelines` | List recent deployments across all projects |
| GET | `/api/v2/deploy/pipelines/:id` | Deployment detail with steps |
| GET | `/api/v2/deploy/pipelines/:id/status` | SSE stream (step updates) |
| POST | `/api/v2/deploy/pipelines/:id/cancel` | Cancel running deployment |
| POST | `/api/v2/deploy/callback` | n8n callback webhook (HMAC-validated) |
| POST | `/api/v2/deploy/webhook/forgejo` | Forgejo push webhook (GitOps) |

**SSE event format (`/api/v2/deploy/pipelines/:id/status`):**
```
event: step_update
data: {"step":"build","status":"running","started_at":"2026-03-07T10:00:00Z"}

event: step_update
data: {"step":"build","status":"success","duration_ms":42000,"log_output":"..."}

event: deployment_complete
data: {"status":"success","version":"v1.4.2","duration_ms":187000}
```

### 8.6 Costs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/costs/summary` | Current month totals + projection |
| GET | `/api/v2/costs/providers/:provider` | Per-provider detail (history + breakdown) |
| GET | `/api/v2/costs/projects` | Cost allocation per project |
| GET | `/api/v2/costs/recommendations` | Optimizer recommendations |
| POST | `/api/v2/costs/sync` | Force refresh from provider APIs |

**Response shape (`GET /api/v2/costs/summary`):**
```json
{
  "success": true,
  "data": {
    "current_month": {
      "period": "2026-03",
      "total_eur": 42.80,
      "by_provider": {
        "hetzner": 8.40,
        "ovh": 22.40,
        "namecheap": 4.00,
        "litellm": 8.00
      }
    },
    "projection": {
      "end_of_month_eur": 51.20,
      "confidence_pct": 87,
      "trend": "up",
      "mom_delta_pct": 12.3
    },
    "recommendations": [
      {
        "type": "idle_server",
        "message": "app-prod has <5% CPU for 7 days. Consider downgrading.",
        "savings_eur": 4.20
      }
    ]
  }
}
```

### 8.7 Domains

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/domains` | List all domains with expiry status |
| GET | `/api/v2/domains/:domain` | Domain detail + all DNS records |
| POST | `/api/v2/domains/sync` | Sync domains from all registrar APIs |
| GET | `/api/v2/domains/:domain/records` | List DNS records |
| POST | `/api/v2/domains/:domain/records` | Create DNS record |
| PUT | `/api/v2/domains/:domain/records/:id` | Update DNS record |
| DELETE | `/api/v2/domains/:domain/records/:id` | Delete DNS record |

### 8.8 Terminal

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/terminal/ws` | WebSocket upgrade endpoint (server selector: `?server=sese-ai`) |
| GET | `/api/v2/terminal/servers` | List servers available for SSH |

WebSocket protocol: binary frames for terminal data (xterm.js compatible), JSON control frames for resize events (`{"type":"resize","cols":220,"rows":50}`).

### 8.9 Waza

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/waza/services` | List all Waza services with status + RAM |
| POST | `/api/v2/waza/services/:slug/start` | Start service (pre-flight RAM check) |
| POST | `/api/v2/waza/services/:slug/stop` | Stop service |
| POST | `/api/v2/waza/profiles/:profile/start` | Start all services in a profile |
| POST | `/api/v2/waza/profiles/stop` | Stop all on-demand services |
| GET | `/api/v2/waza/ram` | Current RPi5 RAM usage |

### 8.10 Memory + MCP (Preserved from v1, Extended)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/memory/nodes` | List knowledge nodes |
| POST | `/api/v1/memory/nodes` | Create node |
| GET | `/api/v1/memory/search` | Semantic search (Qdrant) |
| POST | `/api/mcp` | MCP JSON-RPC endpoint (SSE transport) |

**New MCP tool domains (added to existing `palais.memory.*`):**

```
palais.fleet.getServers          → Fleet server list with current metrics
palais.fleet.getContainers       → Containers on a specific server
palais.fleet.restartContainer    → Restart a container (requires confirmation)
palais.workspaces.list           → List project workspaces with status
palais.workspaces.deploy         → Trigger a deployment
palais.workspaces.rollback       → Rollback to previous version
palais.services.getLogs          → Get container logs
palais.deploy.getPipelineStatus  → Current deploy pipeline status
palais.costs.getSummary          → Current month cost summary
palais.domains.getRecords        → DNS records for a domain
palais.domains.createRecord      → Create DNS record
palais.waza.startService         → Start a Waza on-demand service
palais.waza.getRamStatus         → Current Waza RAM usage
```

---

## 9. UI/UX Design

### 9.1 Design System (Afrofuturist — Unchanged)

```css
/* Core palette */
--palais-bg:           #0A0A0F;  /* Deep space background */
--palais-surface:      #111118;  /* Panel surface */
--palais-surface-hover:#1A1A24;  /* Hover state */
--palais-border:       #2A2A3A;  /* Subtle borders */

/* Accents */
--palais-gold:         #D4A843;  /* Primary — CTAs, active states */
--palais-gold-glow:    rgba(212, 168, 67, 0.2);
--palais-amber:        #E8833A;  /* Warnings */
--palais-cyan:         #4FC3F7;  /* Data, metrics */
--palais-green:        #4CAF50;  /* Success, online status */
--palais-red:          #E53935;  /* Errors, offline, critical */

/* Fonts */
--font-heading:        'Orbitron', monospace;   /* Module titles */
--font-body:           'Plus Jakarta Sans', sans-serif;
--font-mono:           'JetBrains Mono', monospace; /* Terminal, code */
```

Glassmorphism panels: `backdrop-filter: blur(12px)` + 1px gold border at 30% opacity + subtle inner glow. HUD bracket decorators on section headers. Scan line animation on active panels. Adinkra symbols as navigation icons (SVG sprite, gold fill).

### 9.2 Navigation Structure

```
Sidebar (collapsible, Adinkra icons)
├── FLEET        [server-rack icon]   → /fleet
├── WORKSPACES   [grid icon]          → /workspaces
├── SERVICES     [docker icon]        → /services
├── DEPLOY       [rocket icon]        → /deploy
├── COSTS        [chart icon]         → /costs
├── DOMAINS      [globe icon]         → /domains
├── TERMINAL     [terminal icon]      → /terminal
├── WAZA         [cpu icon]           → /waza
└── MEMORY       [brain icon]         → /memory

Top bar: Search (global), Notifications bell, API key indicator, User avatar
Status bar (always visible): VPS: 4 | Containers: 47 | MTD Cost: €42.80 | Next alarm: —
```

### 9.3 Module Layouts

#### Fleet (`/fleet`)
- **Hero totals bar**: VPS count, containers healthy/unhealthy, current month cost, domains expiring soon
- **Server grid** (responsive 2-4 col): `ServerCard` component — name, provider badge, status LED, CPU/RAM/disk gauges (arc gauge, gold fill), Tailscale IP, container count
- **Container drawer**: Click server → slide-in drawer with container list (name, image, status, RAM usage bar)
- **Sync button**: Manual refresh + "Last synced X minutes ago"

#### Workspaces (`/workspaces`)
- **Project cards**: `WorkspaceCard` — name, stack badge, server badge, current version, status pill, quick actions (Deploy, SSH, Logs)
- **Active deployment banner**: If a deploy is running, gold pulsing banner with progress
- **Project drawer**: Click card → expanded view with deploy history table, metrics sparklines, repo link

#### Deploy (`/deploy`)
- **Pipeline list**: Recent deployments across all projects, grouped by date
- **Pipeline detail**: Click row → `PipelineProgress` component — vertical step list with icons, status colors, duration badge
- **SSE-driven**: Steps animate in real-time without page refresh
- **Log panel**: Click any step → slide-out log viewer with `xterm.js` in read-only mode (consistent font with terminal module)

#### Costs (`/costs`)
- **Summary header**: Total MTD, projected EOM, MoM delta percentage with arrow
- **Provider cards**: `BudgetCard` — provider logo, MTD amount, progress bar (% of expected), sparkline (30-day)
- **Donut chart**: Provider breakdown (d3-scale, gold/amber/cyan/green color assignment)
- **Recommendations panel**: Optimizer tips with estimated savings, dismiss button
- **Linear regression chart**: 30-day cost data + projection line (d3-time, dashed gold)

#### Domains (`/domains`)
- **Domain table**: Registrar, expiry (color-coded: green >60d, amber 30-60d, red <30d), auto-renew toggle, DNS provider badge
- **DNS record table**: Type badge (A=gold, CNAME=cyan, TXT=amber, MX=green), name, value, TTL — inline editing with validation
- **Add record form**: Dropdown type selector, name/value/TTL inputs, save with confirmation
- **Expiry alert strip**: Top of page if any domain expires in <30 days

#### Terminal (`/terminal`)
- **Server selector**: Dropdown top-left, shows server name + status LED
- **Tab bar**: Multiple terminal tabs, gold underline for active, X to close
- **xterm.js canvas**: Full-width, JetBrains Mono, gold cursor, dark background (#0A0A0F)
- **Toolbar**: Copy selection, clear, reconnect, resize fit

#### Waza (`/waza`)
- **RAM gauge**: Large arc gauge showing current/available/maximum, color zones (green/amber/red)
- **Service grid**: `WazaServiceCard` — name, status LED, RAM estimate, start/stop button, last started
- **Profile buttons**: "Video Mode", "Art Mode", "Dev Mode" — one-click start all services in profile
- **Pre-flight modal**: If starting a service would exceed 80% RAM, show warning with current vs projected usage

#### Memory (`/memory`)
- **Knowledge graph**: d3-force directed graph, nodes colored by type, edges as gold lines
- **Search bar**: Semantic search via Qdrant, results as node cards
- **Node detail**: Click node → side panel with metadata, connections, edit/delete
- **MCP status**: Badge showing MCP server status and connected clients

### 9.4 Key UI Components

| Component | Purpose | Key Props |
|-----------|---------|-----------|
| `ServerCard` | Fleet server overview | `server`, `metrics`, `onExpand` |
| `ContainerRow` | Container in list | `container`, `onRestart`, `onLogs` |
| `PipelineProgress` | Deploy step visualization | `steps`, `activeStep` |
| `BudgetCard` | Cost provider card | `provider`, `amount`, `budget`, `sparkline` |
| `DnsTable` | DNS record CRUD table | `records`, `onEdit`, `onDelete`, `onAdd` |
| `TerminalPane` | xterm.js wrapper | `serverId`, `sessionId` |
| `WazaServiceCard` | On-demand service control | `service`, `ramAvailable`, `onStart`, `onStop` |
| `StatBadge` | Metric with trend indicator | `value`, `unit`, `trend`, `color` |
| `StatusLed` | Animated status indicator | `status: 'online'\|'offline'\|'unknown'` |
| `GoldGauge` | Arc progress gauge | `value`, `max`, `thresholds` |

---

## 10. Security

### 10.1 Access Control

- **VPN-only**: Caddy enforces `(vpn_only)` snippet on all Palais routes (Tailscale CIDR + Docker frontend bridge CIDR per the 2-CIDR rule in CLAUDE.md).
- **Session auth**: httpOnly cookie with 24h expiry, admin password validated against bcrypt hash stored in env.
- **API key auth**: `PALAIS_API_KEY` env var, HMAC-256 comparison, rate-limited to 100 req/min per key.
- **No public health check exposure**: `/api/health` returns 200 with minimal data (no server info). Caddy allows this endpoint publicly for Uptime Kuma.

### 10.2 Secrets Management

All provider API keys are stored in Ansible Vault (`inventory/group_vars/all/secrets.yml`) and injected as Docker environment variables. Keys are never written to disk on the container filesystem and never logged.

Required new vault entries:
```yaml
vault_palais_api_key:          <32-byte hex>
vault_palais_admin_password:   <bcrypt hash>
vault_hetzner_api_token:       <hcloud API token>
vault_headscale_api_key:       <headscale API key>
vault_namecheap_api_user:      <namecheap username>
vault_namecheap_api_key:       <namecheap API key>
vault_namecheap_client_ip:     <Sese-AI public IP>
vault_forgejo_token:           <Forgejo personal access token>
vault_app_prod_ip:             <Hetzner app-prod server IP>
vault_waza_ip:                 <RPi5 Tailscale IP>
```

### 10.3 Destructive Action Protection

All destructive actions require a two-step confirmation:

| Action | Confirmation Required |
|--------|----------------------|
| Restart container | Single confirm modal |
| Stop container | Single confirm modal |
| Remove container | Typed name confirmation |
| Trigger deployment | Single confirm modal |
| Rollback | Modal with version diff shown |
| Delete DNS record | Single confirm modal |
| Destroy VPS | Typed server name confirmation + 30-second delay |
| Delete DNS zone | Typed domain name confirmation |

### 10.4 SSH Terminal Security

- Terminal WebSocket is only accessible over VPN (Caddy ACL).
- SSH private key is mounted read-only into the container at `/data/ssh/deploy-key`.
- Sessions are bound to authenticated Palais session cookies; unauthenticated WS connections are immediately closed.
- Maximum 3 concurrent terminal sessions (enforced server-side, returns HTTP 429 on excess).
- All SSH commands are executed as `mobuone` (non-root) on target servers.
- Terminal sessions have a 30-minute inactivity timeout.

### 10.5 n8n Callback Webhook Validation

Deploy callbacks from n8n are validated using HMAC-SHA256 of the request body with `N8N_WEBHOOK_SECRET`. Requests with invalid or missing signatures are rejected with HTTP 401. Replay protection: reject callbacks with a `timestamp` field older than 5 minutes.

### 10.6 Namecheap API IP Whitelist

Namecheap's sandbox and production APIs require the client IP to be whitelisted. `NAMECHEAP_CLIENT_IP` must be set to Sese-AI's current public IP (OVH VPS). IP changes require updating the whitelist in the Namecheap dashboard and the vault variable. Consider using the OVH Anycast IP (static) for this.

---

## 11. Performance

### 11.1 Resource Limits

| Resource | v1 Limit | v2 Limit | Rationale |
|----------|----------|----------|-----------|
| RAM | 192MB | 256MB | WebSocket SSH sessions, larger JS bundle |
| CPU | 0.75 | 1.0 | Docker SSH polling, concurrent API calls |
| WebSocket sessions | 0 | 3 max | Terminal concurrency limit |
| SSE connections | Unbounded | 10 max | Deploy logs + fleet streams |

### 11.2 Polling Intervals

| Data Source | Interval | Rationale |
|-------------|----------|-----------|
| Hetzner Cloud API | 5 minutes | Rate limit: 3,600 req/hour; fleet data isn't real-time critical |
| OVH API | 5 minutes | Same |
| Headscale API | 2 minutes | VPN node last-seen is more time-sensitive |
| Docker stats (SSH) | 30 seconds | Container health is more critical; SSH overhead acceptable |
| Cost data | 1 hour | Billing APIs are slow and low-priority |
| Waza RAM | 15 seconds | Needed for pre-flight checks to be accurate |
| DNS sync | 15 minutes | TTL-bounded, changes are infrequent |

### 11.3 Caching Strategy

- **Fleet data**: DB cache (5-minute TTL). Clients receive cached DB data on page load; background poller refreshes.
- **Cost data**: DB cache (1-hour TTL). No real-time requirement.
- **DNS records**: DB cache. Synced on demand or on 15-minute schedule.
- **Docker container list**: In-memory per-server cache (30-second TTL). Not persisted to DB.
- **Qdrant vector search**: No cache (Qdrant is fast enough for interactive use).

### 11.4 SSE Rolling Buffer

Deploy log SSE connections use a 200-event rolling buffer on the server side. New connections receive the last 200 events immediately (catch-up) then stream new events. Buffer is cleared when deployment reaches a terminal state (success, failed, cancelled).

Keepalive: SSE sends a `comment: keepalive` line every 30 seconds to prevent proxy timeouts.

### 11.5 Database Considerations

- `server_metrics` table grows at ~288 rows/day per server (30s interval × 4 servers × 60min/2). Partition by month after 30 days. Keep only 90 days of per-server metric history.
- `deployment_steps` log output: truncate to 50KB per step to avoid bloating the table.
- Indexes defined in schema cover all common query patterns. Full vacuum scheduled weekly via pg_cron.

---

## 12. Phased Implementation

### Phase A — Foundations & Schema Migration (Week 1)

**Goal:** Clean slate. Drop v1 tables, create v2 schema, keep auth and MCP working.

**Tasks:**
1. Write Drizzle migration: drop v1 project/task/budget tables
2. Write Drizzle migration: create all new v2 tables (`servers`, `projects_registry`, `deployments`, `deployment_steps`, `domains`, `dns_records`, `cost_snapshots`, `cost_forecasts`, `waza_services`)
3. Update SvelteKit layout: replace sidebar links with 9-module navigation
4. Update status bar component to show fleet totals (initially hardcoded)
5. Verify MCP server still works (memory tools preserved)
6. Deploy: bump Palais Docker image version, validate in prod

**Deliverable:** Palais v2.0 running in prod with clean DB schema and updated nav.

---

### Phase B — Fleet Module (Week 2)

**Goal:** Real-time view of all servers and containers.

**Tasks:**
1. Implement Hetzner Cloud API client (`src/lib/server/integrations/hetzner.ts`)
2. Implement OVH API client (`src/lib/server/integrations/ovh.ts`) — reuse existing OVH credentials from vault
3. Implement Headscale REST API client (`src/lib/server/integrations/headscale.ts`)
4. Implement Docker SSH client via `node-ssh` (`src/lib/server/integrations/docker-ssh.ts`)
5. Implement background fleet poller (`src/lib/server/jobs/fleet-poller.ts`) with 5-min interval
6. Implement Fleet API routes (`/api/v2/fleet/*`)
7. Build `ServerCard`, `GoldGauge`, `StatusLed` UI components
8. Build `/fleet` page with server grid and container drawer
9. Build top status bar with live fleet totals
10. Add `palais.fleet.*` MCP tools

**Deliverable:** Fleet page showing live data for all servers. Status bar shows real container count.

---

### Phase C — Services & Terminal Modules (Week 3)

**Goal:** Container control and SSH terminal.

**Tasks:**
1. Implement container control API (`start`, `stop`, `restart`, `logs` endpoints)
2. Build log viewer component (xterm.js read-only mode)
3. Build dependency graph warning (hardcoded adjacency for PostgreSQL/Redis)
4. Implement WebSocket SSH proxy (`src/routes/api/v2/terminal/ws/+server.ts`)
5. Integrate xterm.js with WebSocket transport
6. Build `/terminal` page with server selector and tab bar
7. Add `palais.services.*` and terminal tools to MCP

**Deliverable:** Operators can restart containers and open SSH sessions from the browser.

---

### Phase D — Workspaces & Deploy Modules (Week 4)

**Goal:** Deployment pipeline with real-time progress.

**Tasks:**
1. Create `projects_registry` seed data for existing projects
2. Implement workspace CRUD API
3. Implement deploy trigger API + n8n webhook integration
4. Implement n8n callback webhook with HMAC validation
5. Implement deploy SSE stream (`/api/v2/deploy/pipelines/:id/status`)
6. Build `PipelineProgress` component with SSE consumption
7. Build `/workspaces` page with project cards
8. Build `/deploy` page with pipeline history and real-time progress
9. Implement Forgejo webhook handler (GitOps auto-deploy)
10. Add `palais.workspaces.*` and `palais.deploy.*` MCP tools

**Deliverable:** Full deployment pipeline from UI click (or Forgejo push) to completion, with visual progress.

---

### Phase E — Costs Module (Week 5)

**Goal:** Unified infrastructure cost tracking with projections.

**Tasks:**
1. Implement Hetzner billing API client (server costs, S3, traffic)
2. Implement OVH billing API client (VPS invoices)
3. Implement LiteLLM budget API client (`/budget/info` endpoint)
4. Implement manual domain cost seeding (Namecheap, annual amortized)
5. Implement hourly cost poller + cost_snapshots upsert
6. Implement linear regression forecast (30-day rolling)
7. Implement cost optimizer rules engine (idle VPS detection, snapshot age)
8. Build `BudgetCard`, donut chart, projection chart UI components
9. Build `/costs` page
10. Add `palais.costs.*` MCP tools

**Deliverable:** Accurate monthly cost view per provider with 30-day projection.

---

### Phase F — Domains Module (Week 6)

**Goal:** Full DNS management UI for Namecheap and OVH.

**Tasks:**
1. Implement Namecheap XML API client (`src/lib/server/integrations/namecheap.ts`)
   - `namecheap.domains.getList`
   - `namecheap.domains.dns.getHosts`
   - `namecheap.domains.dns.setHosts`
2. Implement OVH DNS client (reuse existing integration from CI scripts)
3. Implement domain sync job (15-minute interval)
4. Implement DNS record CRUD API
5. Build `DnsTable` component with inline editing and type validation
6. Build `/domains` page with domain list and record management
7. Build expiry alert strip
8. Add `palais.domains.*` MCP tools

**Deliverable:** Operators can list all domains, view/edit DNS records, and create tenant subdomains from the UI.

---

### Phase G — Waza Module (Week 7)

**Goal:** RPi5 on-demand service management.

**Tasks:**
1. Seed `waza_services` table with: ComfyUI, OpenCut, Remotion, Claude Code, OpenCode
2. Implement Waza service control via SSH to Waza IP (Docker start/stop)
3. Implement RAM pre-flight check (current usage + service estimate vs threshold)
4. Implement profile start logic (parallel service starts)
5. Build `WazaServiceCard`, RAM gauge components
6. Build `/waza` page with service grid and profile buttons
7. Add `palais.waza.*` MCP tools

**Deliverable:** Operators can start/stop Waza services and profiles from browser. RAM pre-flight prevents OOM.

---

### Phase H — Polish & Integration (Week 8)

**Goal:** Production hardening, tests, documentation.

**Tasks:**
1. Global search (Cmd+K): servers, containers, deployments, domains
2. Notification drawer: last 20 Telegram-bound alerts also shown in UI
3. Keyboard shortcuts: `F` = Fleet, `D` = Deploy, `T` = Terminal, `R` = Refresh
4. Mobile-responsive layout (tablet: 768px breakpoint, hamburger nav)
5. E2E tests: Playwright for Fleet load, deploy trigger, DNS record add, Terminal connect
6. Integration tests: all API routes with mock external clients
7. Load test: 10 concurrent SSE connections, measure RAM ceiling
8. Ansible role update: new env vars, bump palais_version to v2.0.0
9. Smoke test update: add `/fleet/summary` and `/costs/summary` to CI smoke checks
10. Update RUNBOOK.md with Palais v2 operational procedures

**Deliverable:** Palais v2.0.0 production-ready, tested, deployed.

---

## 13. Success Metrics

### Technical Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Fleet page load time | < 2 seconds (cached data) | Playwright performance timing |
| Fleet sync latency | All servers visible within 30s of page load | Smoke test |
| Deploy trigger to first SSE event | < 5 seconds | Integration test |
| Full deploy pipeline (simple project) | < 10 minutes | Deployment history |
| DNS record propagation (Namecheap → Palais DB) | < 15 minutes | Manual test |
| Cost data accuracy vs provider dashboard | Within €0.50/month | Manual monthly audit |
| Terminal latency (keypress → echo) | < 100ms over VPN | Manual test |
| RAM usage (Palais container) | < 220MB at 3 concurrent terminal sessions | `docker stats` |

### Operational Metrics

| Metric | Target |
|--------|--------|
| Time to deploy a new VPS from Palais UI | < 10 minutes |
| Time to create a new tenant subdomain | < 2 minutes |
| Time to identify and restart an unhealthy container | < 1 minute |
| Mean time to detect a server outage | < 6 minutes (polling interval + alert) |

### Adoption Metrics (30 days post-launch)

| Metric | Target |
|--------|--------|
| Deployments triggered via Palais UI (vs terminal) | > 90% |
| DNS changes via Palais UI (vs registrar dashboard) | > 80% |
| Terminal sessions opened in Palais (vs local SSH) | > 50% |
| MCP tool calls per day (from Claude Code / OpenClaw) | > 10 |

---

## 14. Risks & Mitigations

### R1 — External API Instability

**Risk:** Hetzner, OVH, or Namecheap APIs experience outages or breaking changes.
**Probability:** Medium. **Impact:** High (Fleet and Costs show stale data).
**Mitigation:**
- Serve cached DB data when API fails (never show errors to replace data).
- Distinguish `status: "stale"` vs `status: "live"` in API responses.
- Display "Last synced X minutes ago" in UI with amber color if > 10 minutes old.
- Implement circuit breaker per provider: after 3 consecutive failures, back off for 30 minutes.

### R2 — SSH Tunnel Memory Leak

**Risk:** node-ssh connections are not properly cleaned up, leading to connection exhaustion and memory growth.
**Probability:** Medium. **Impact:** High (container OOM kill).
**Mitigation:**
- Implement explicit connection pool with max 10 connections.
- Connection timeout: 5 seconds to establish, 30 seconds for command execution.
- Audit trail: log all SSH connection open/close events with duration.
- Health endpoint exposes active SSH connection count for monitoring.
- Weekly load test in CI to catch regressions.

### R3 — Namecheap IP Whitelist Breaks DNS Management

**Risk:** OVH VPS IP changes after a reboot/migration, invalidating the Namecheap IP whitelist.
**Probability:** Low (OVH VPS IPs are stable). **Impact:** High (DNS management completely broken).
**Mitigation:**
- OVH VPS has a fixed public IP (verified in inventory: 137.74.114.167).
- Document the IP whitelist update procedure in RUNBOOK.md.
- Domains module shows a clear error when Namecheap API returns an IP mismatch error.
- Fallback: Namecheap DNS can still be managed via registrar UI in emergencies.

### R4 — Deploy Callback Race Condition

**Risk:** n8n sends deploy callbacks out of order or after the deployment is already in a terminal state.
**Probability:** Low. **Impact:** Medium (incorrect step status in UI).
**Mitigation:**
- Callbacks are idempotent: `INSERT ... ON CONFLICT DO UPDATE` only if new status is "later" in the pipeline.
- State machine: `pending → running → success/failed/cancelled` — no backward transitions allowed.
- Timestamp validation: reject callbacks with `timestamp` more than 5 minutes old.

### R5 — WebSocket Terminal Session Hijacking

**Risk:** An attacker intercepts or replays a terminal WebSocket session.
**Probability:** Low (VPN-only). **Impact:** Critical (full server shell access).
**Mitigation:**
- Terminal WS only over VPN (Caddy ACL).
- Session token bound to the authenticated Palais cookie (WS upgrade includes cookie).
- 30-minute inactivity timeout.
- Sessions are logged: server, user, start/end time, command count.

### R6 — Raspberry Pi Waza Unreachable

**Risk:** Waza (RPi5) is offline or not on the Tailscale network when Palais tries to control services.
**Probability:** Medium (Pi can be powered off). **Impact:** Low (graceful degradation).
**Mitigation:**
- Waza module shows "Waza Offline" state with last-seen timestamp when SSH fails.
- All Waza controls are disabled (grayed out) when offline.
- Background Waza health check every 60 seconds; status updates via SSE.

### R7 — v1 to v2 Migration Data Loss

**Risk:** The schema migration drops v1 tables containing valuable data.
**Probability:** Low (most v1 data is ephemeral or migrated to Plane). **Impact:** Medium.
**Mitigation:**
- Export v1 data (tasks, ideas, missions) to a JSON dump before migration.
- Store dump in S3 backup bucket (`vpai-backups/palais-v1-export-2026-XX-XX.json`).
- Migration is a Drizzle migration file (versioned, reversible in dev).
- Test migration on preprod before prod.

### R8 — 256MB RAM Ceiling Hit Early

**Risk:** 3 concurrent terminal sessions + Fleet polling + SSE streams + SvelteKit exceed 256MB.
**Probability:** Medium. **Impact:** High (OOM kill).
**Mitigation:**
- Load test in Phase H before production deployment.
- Implement graceful degradation: reduce polling frequency when memory pressure is detected.
- Add `mem_limit: 256m` with `memswap_limit: 512m` (swap as safety valve).
- Memory monitoring: Palais exports a `/metrics` Prometheus endpoint; Alloy scrapes it; Grafana alerts at 80%.
- If 256MB proves insufficient, bump to 384MB (still within VPS resource budget).

---

*End of PRD — Palais v2*
