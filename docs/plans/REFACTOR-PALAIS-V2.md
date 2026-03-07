# REFACTOR-PALAIS-V2 — Palais v1 → v2 Transformation Plan

**Date:** 2026-03-07
**Scope:** `roles/palais/files/app/` (SvelteKit 5), `roles/palais/` (Ansible role)
**Estimated duration:** 15 working days
**Branch:** `feat/palais-v2`
**Git tag (v1 freeze):** `palais-v1-final`

---

## Executive Summary

Palais v1 is a personal AI command-center with project management, missions, ideas, budget
tracking, and creative tooling built for a solo operator context. Palais v2 pivots to become an
**infrastructure control plane**: fleet management, deployment orchestration, service control, DNS,
cost visibility, and a web terminal — all wrapped in the same Afrofuturist design language.

The MCP server is the most critical dependency and must be the **last thing broken, first thing
restored** in each phase.

---

## Current State Inventory

### Routes to remove (Phase 1 teardown)

| Route | Files | Tables used |
|-------|-------|-------------|
| `/creative` | `src/routes/creative/` | — (external ComfyUI) |
| `/ideas`, `/ideas/[id]` | `src/routes/ideas/` | `ideas`, `idea_versions`, `idea_links` |
| `/missions`, `/missions/[id]`, `/missions/[id]/plan`, `/missions/[id]/warroom`, `/missions/new` | `src/routes/missions/` | `missions`, `mission_conversations` |
| `/projects`, `/projects/[id]`, `/projects/[id]/analytics`, `/projects/[id]/deliverables`, `/projects/[id]/list`, `/projects/[id]/timeline` | `src/routes/projects/` | `workspaces`, `projects`, `columns`, `tasks`, `task_dependencies`, `labels`, `task_labels`, `comments`, `activity_log`, `time_entries`, `task_iterations`, `deliverables` |
| `/budget` | `src/routes/budget/` | `budget_snapshots`, `budget_forecasts` |
| `/insights` | `src/routes/insights/` | `insights` |
| `/agents/[id]/traces/[sid]` | `src/routes/agents/[id]/traces/[sid]/` | — (read-only on existing tables) |

### API routes to remove (Phase 1 teardown)

```
src/routes/api/v1/creative/
src/routes/api/v1/ideas/
src/routes/api/v1/missions/
src/routes/api/v1/projects/
src/routes/api/v1/tasks/
src/routes/api/v1/labels/
src/routes/api/v1/budget/
src/routes/api/v1/insights/
src/routes/api/v1/standup/
```

### MCP tools to remove (Phase 1 teardown)

```
src/lib/server/mcp/tools/tasks.ts
src/lib/server/mcp/tools/projects.ts
src/lib/server/mcp/tools/deliverables.ts
src/lib/server/mcp/tools/insights.ts
src/lib/server/mcp/tools/standup.ts
src/lib/server/mcp/tools/budget.ts  ← keep structure, repurpose to costs in Phase 6
```

### Files and modules to keep (no changes in Phases 1–2)

```
src/lib/server/mcp/router.ts
src/lib/server/mcp/sse.ts
src/lib/server/mcp/types.ts
src/lib/server/mcp/tools/memory.ts   ← NEVER break during teardown
src/lib/server/mcp/tools/agents.ts   ← read-only display, keep
src/lib/server/db/index.ts
src/lib/server/db/schema.ts          ← edit progressively
src/lib/server/health/headscale.ts   ← extend in Phase 3
src/lib/server/llm/client.ts
src/lib/server/memory/              ← entire directory
src/routes/api/v1/memory/           ← entire directory
src/routes/api/mcp/                 ← NEVER remove
src/routes/api/health/
src/routes/api/sse/
src/routes/agents/                  ← keep but simplify
src/routes/health/                  ← keep, extend in Phase 5
src/routes/memory/                  ← keep as-is
src/lib/components/icons/           ← all Adinkra icons kept
src/lib/styles/theme.css
src/app.css
```

### DB tables to keep

| Table | Module | Action |
|-------|--------|--------|
| `agents` | Agents | Keep, remove `currentTaskId` FK dependency after tasks drop |
| `agent_sessions` | Agents | Keep |
| `agent_spans` | Agents | Keep |
| `memory_nodes` | Knowledge Graph | Keep |
| `memory_edges` | Knowledge Graph | Keep |
| `nodes` | Health/Fleet | Keep, migrate data to `servers` in Phase 2 |
| `health_checks` | Health | Keep |
| `backup_status` | Health | Keep |

---

## Phase 0: Backup and Preparation (Day 1)

**Goal:** Freeze v1 state, create safe branch, document MCP contracts.

### 0.1 — Git freeze

- [ ] Verify working tree is clean: `git status`
- [ ] Create annotated tag: `git tag -a palais-v1-final -m "Palais v1 final state before v2 refactor"`
- [ ] Push tag: `git push github-seko palais-v1-final`
- [ ] Create feature branch: `git checkout -b feat/palais-v2`

### 0.2 — Database backup

- [ ] Dump full Palais DB from prod:

  ```bash
  ssh -o IdentitiesOnly=yes -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
    "docker exec javisi_postgresql pg_dump -U palais palais" \
    > /tmp/palais-v1-backup-$(date +%Y%m%d).sql
  ```

- [ ] Verify dump is non-empty and readable
- [ ] Copy dump to safe location: `~/.backups/palais/palais-v1-backup-YYYYMMDD.sql`

### 0.3 — Document live MCP tool contracts

- [ ] Run from Pi: `curl -s -X POST https://palais.seko.work/api/mcp -H "X-API-Key: $PALAIS_API_KEY" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq .result.tools[].name`
- [ ] Save output to `/tmp/palais-v1-mcp-tools.txt` as reference
- [ ] Identify which tools Claude Code agents are actively calling in current sessions
- [ ] Confirm `palais.memory.*` tools are the only active MCP dependencies during the refactor

### 0.4 — Local dev environment check

- [ ] Confirm dev DB is running locally with `palais` DB
- [ ] Run `npm run dev` in `roles/palais/files/app/` and verify app starts at localhost:3300
- [ ] Run `npm run check` — capture all TypeScript errors as baseline

---

## Phase 1: Teardown — Remove Redundant Modules (Day 1–2)

**Goal:** Strip everything that is not being carried into v2. After this phase only Dashboard
(simplified), Agents (read-only), Health, Memory, and the MCP server remain.

**Critical rule:** Remove route directories and lib modules before touching `schema.ts`.
TypeScript will surface all remaining imports that need cleanup.

### 1.1 — Remove Creative module

- [ ] Delete `src/routes/creative/`
- [ ] Delete `src/routes/api/v1/creative/`
- [ ] Delete `src/lib/server/creative/comfyui.ts`
- [ ] Remove `COMFYUI_URL` from env usage (not from `.env.j2` yet — Phase 7)
- [ ] Run `npm run check` after deletion; fix any broken imports

### 1.2 — Remove Insights module

- [ ] Delete `src/routes/insights/`
- [ ] Delete `src/routes/api/v1/insights/`
- [ ] Delete `src/lib/server/insights/detector.ts`
- [ ] Delete `src/lib/server/insights/scheduler.ts`
- [ ] Delete `src/lib/server/mcp/tools/insights.ts`
- [ ] Remove `insightToolDefs` import and registration from `src/lib/server/mcp/tools/registry.ts`
- [ ] Remove `handleInsightsTool` import and case from `src/lib/server/mcp/tools/executor.ts`
- [ ] Remove `InsightBanner` and `StandupCard` usage from `src/routes/+page.svelte` (dashboard)
- [ ] Delete `src/lib/components/dashboard/InsightBanner.svelte`
- [ ] Delete `src/lib/components/dashboard/StandupCard.svelte`
- [ ] Run `npm run check`

### 1.3 — Remove Standup module

- [ ] Delete `src/routes/api/v1/standup/`
- [ ] Delete `src/lib/server/standup/generate.ts`
- [ ] Delete `src/lib/server/standup/scheduler.ts`
- [ ] Delete `src/lib/server/mcp/tools/standup.ts`
- [ ] Remove `standupToolDefs` and `handleStandupTool` from registry and executor
- [ ] Remove `STANDUP_HOUR` env reference from `src/hooks.server.ts` (if scheduler is registered there)
- [ ] Run `npm run check`

### 1.4 — Remove Ideas module

- [ ] Delete `src/routes/ideas/`
- [ ] Delete `src/routes/api/v1/ideas/`
- [ ] Run `npm run check` — note any cross-references to `ideas` table in missions schema

### 1.5 — Remove Missions module

- [ ] Delete `src/routes/missions/`
- [ ] Delete `src/routes/api/v1/missions/`
- [ ] Run `npm run check`

### 1.6 — Remove Projects, Tasks, Labels, Deliverables modules

**Note:** `deliverables` route `src/routes/dl/[token]/` handles file download — keep only if
deliverables table is kept. Since deliverables are being dropped, delete this too.

- [ ] Delete `src/routes/projects/`
- [ ] Delete `src/routes/api/v1/projects/`
- [ ] Delete `src/routes/api/v1/tasks/`
- [ ] Delete `src/routes/api/v1/labels/`
- [ ] Delete `src/routes/dl/`
- [ ] Delete `src/lib/server/mcp/tools/tasks.ts`
- [ ] Delete `src/lib/server/mcp/tools/projects.ts`
- [ ] Delete `src/lib/server/mcp/tools/deliverables.ts`
- [ ] Remove corresponding entries from `registry.ts` and `executor.ts`
- [ ] Delete `src/lib/server/utils/critical-path.ts` (only used by projects)
- [ ] Delete `src/lib/components/kanban/`
- [ ] Delete `src/lib/components/timeline/GanttChart.svelte`
- [ ] Delete `src/lib/components/editor/RichTextEditor.svelte` (used by tasks/ideas)
- [ ] Delete `src/lib/components/ActivityFeed.svelte`
- [ ] Run `npm run check`

### 1.7 — Remove Budget module

- [ ] Delete `src/routes/budget/`
- [ ] Delete `src/routes/api/v1/budget/`
- [ ] Delete `src/lib/server/budget/cron.ts`
- [ ] Delete `src/lib/server/budget/providers.ts`
- [ ] Keep `src/lib/server/budget/litellm.ts` — will be repurposed as costs/litellm.ts in Phase 3
- [ ] Delete `src/lib/server/mcp/tools/budget.ts`
- [ ] Remove `budgetToolDefs` and `handleBudgetTool` from registry and executor
- [ ] Run `npm run check`

### 1.8 — Remove Agents traces sub-route

- [ ] Delete `src/routes/agents/[id]/traces/[sid]/`
- [ ] Simplify `src/routes/agents/[id]/+page.svelte` to remove trace list (show session summary only)
- [ ] Run `npm run check`

### 1.9 — Remove orphaned npm packages

- [ ] Audit `package.json` for packages used exclusively by removed modules:
  - `@tiptap/*` — used by `RichTextEditor.svelte` (now deleted) → remove
  - `svelte-dnd-action` — used by kanban board (now deleted) → remove
  - `d3-force` — used by memory graph visualization → **keep**
  - `d3-scale`, `d3-time` — used by budget chart (now deleted) → remove unless needed in Phase 5
  - `ws` — used by OpenClaw WebSocket → keep (`src/lib/server/ws/openclaw.ts`)
- [ ] Run: `npm uninstall @tiptap/core @tiptap/extension-placeholder @tiptap/pm @tiptap/starter-kit svelte-dnd-action d3-scale d3-time`
- [ ] Run `npm run build` — verify clean build with no errors

### 1.10 — Simplify sidebar and dashboard

- [ ] Update `src/lib/components/layout/Sidebar.svelte`: replace nav array with v2 placeholder
  items (Dashboard, Agents, Health, Memory — the surviving modules). Use `[SOON]` items for
  Fleet, Workspaces, Services, Deploy, Costs, Domains, Terminal, Waza that link to `#`
- [ ] Update `src/routes/+page.svelte`: remove InsightBanner, StandupCard, critical insights
  section. Replace with simple agent grid + system status placeholder
- [ ] Update `src/routes/+page.server.ts`: remove standup and insights queries
- [ ] Run `npm run check` and `npm run build`

**Phase 1 completion gate:** `npm run build` passes with 0 errors. Only 4 active route groups
remain: Dashboard, Agents, Health, Memory. MCP `/api/mcp` and `/api/mcp/sse` still respond.

---

## Phase 2: Database Migration (Day 2)

**Goal:** Drop the now-unreferenced tables, add the v2 schema tables.

### 2.1 — Update `schema.ts` — remove dead table definitions

Remove from `src/lib/server/db/schema.ts`:
- [ ] All Ideas tables: `ideas`, `ideaVersions`, `ideaLinks`
- [ ] All Missions tables: `missions`, `missionConversations`
- [ ] All Projects/Tasks tables: `workspaces`, `projects`, `columns`, `tasks`, `taskDependencies`,
  `labels`, `taskLabels`, `comments`, `activityLog`, `timeEntries`, `taskIterations`
- [ ] Deliverables table: `deliverables`
- [ ] Budget tables: `budgetSnapshots`, `budgetForecasts`
- [ ] Insights table: `insights`
- [ ] All removed enums: `ideaStatusEnum`, `missionStatusEnum`, `insightTypeEnum`,
  `insightSeverityEnum`, `entityTypeEnum`, `timeEntryTypeEnum`, `depTypeEnum`
- [ ] Remove all relations blocks for deleted tables
- [ ] Clean up `agentSessions` relation (remove `missionId` FK reference)
- [ ] Remove `currentTaskId` from `agents` table definition
- [ ] Run `npm run check` — schema.ts is the single source of truth for Drizzle

### 2.2 — Create migration `0002_palais_v2_teardown.sql`

File: `roles/palais/files/app/drizzle/0002_palais_v2_teardown.sql`

```sql
-- Palais v2 teardown — drop modules: ideas, missions, projects/tasks, budget, insights, deliverables
-- Run order matters: child tables first, parent tables last

-- Drop indexes first
DROP INDEX IF EXISTS task_dep_unique;
DROP INDEX IF EXISTS task_label_pk;
DROP INDEX IF EXISTS activity_entity_idx;
DROP INDEX IF EXISTS deliverable_token_idx;

-- Deliverables (references tasks)
DROP TABLE IF EXISTS deliverables CASCADE;

-- Time tracking (references tasks)
DROP TABLE IF EXISTS time_entries CASCADE;
DROP TABLE IF EXISTS task_iterations CASCADE;

-- Task relations
DROP TABLE IF EXISTS task_labels CASCADE;
DROP TABLE IF EXISTS comments CASCADE;
DROP TABLE IF EXISTS task_dependencies CASCADE;
DROP TABLE IF EXISTS activity_log CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS columns CASCADE;
DROP TABLE IF EXISTS labels CASCADE;
DROP TABLE IF EXISTS projects CASCADE;
DROP TABLE IF EXISTS workspaces CASCADE;

-- Missions
DROP TABLE IF EXISTS mission_conversations CASCADE;
DROP TABLE IF EXISTS missions CASCADE;

-- Ideas
DROP TABLE IF EXISTS idea_links CASCADE;
DROP TABLE IF EXISTS idea_versions CASCADE;
DROP TABLE IF EXISTS ideas CASCADE;

-- Budget
DROP TABLE IF EXISTS budget_forecasts CASCADE;
DROP TABLE IF EXISTS budget_snapshots CASCADE;

-- Insights
DROP TABLE IF EXISTS insights CASCADE;

-- Remove dropped columns from kept tables
ALTER TABLE agents DROP COLUMN IF EXISTS current_task_id;
ALTER TABLE agent_sessions DROP COLUMN IF EXISTS mission_id;
ALTER TABLE agent_sessions DROP COLUMN IF EXISTS task_id;

-- Drop unused enums
DROP TYPE IF EXISTS idea_status CASCADE;
DROP TYPE IF EXISTS mission_status CASCADE;
DROP TYPE IF EXISTS insight_type CASCADE;
DROP TYPE IF EXISTS insight_severity CASCADE;
DROP TYPE IF EXISTS entity_type_generic CASCADE;
DROP TYPE IF EXISTS time_entry_type CASCADE;
DROP TYPE IF EXISTS dep_type CASCADE;
DROP TYPE IF EXISTS budget_source CASCADE;
```

### 2.3 — Create migration `0003_palais_v2_new_schema.sql`

File: `roles/palais/files/app/drizzle/0003_palais_v2_new_schema.sql`

```sql
-- Palais v2 new schema — Fleet, Workspaces, Services, Deploy, Costs, Domains, Waza

-- ============ NEW ENUMS ============

CREATE TYPE deploy_status AS ENUM (
    'pending', 'running', 'success', 'failed', 'cancelled', 'rolled_back'
);

CREATE TYPE provider_type AS ENUM ('hetzner', 'ovh', 'ionos', 'local');

CREATE TYPE registrar_type AS ENUM ('namecheap', 'ovh', 'other');

CREATE TYPE server_role AS ENUM ('ai_brain', 'vpn_hub', 'workstation', 'app_prod', 'storage');

-- ============ MODULE: FLEET (servers) ============

CREATE TABLE servers (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    provider        provider_type NOT NULL,
    server_role     server_role NOT NULL DEFAULT 'app_prod',
    location        VARCHAR(50),
    public_ip       VARCHAR(50),
    tailscale_ip    VARCHAR(50),
    status          node_status NOT NULL DEFAULT 'offline',
    cpu_cores       INTEGER,
    ram_mb          INTEGER,
    disk_gb         INTEGER,
    os              VARCHAR(100),
    ssh_port        INTEGER DEFAULT 22,
    ssh_user        VARCHAR(50),
    ssh_key_path    TEXT,
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE server_metrics (
    id              SERIAL PRIMARY KEY,
    server_id       INTEGER NOT NULL REFERENCES servers(id),
    cpu_percent     REAL,
    ram_used_mb     INTEGER,
    ram_total_mb    INTEGER,
    disk_used_gb    REAL,
    disk_total_gb   REAL,
    container_count INTEGER DEFAULT 0,
    load_avg_1m     REAL,
    recorded_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX server_metrics_server_idx ON server_metrics(server_id, recorded_at DESC);

-- ============ MODULE: WORKSPACES (project registry) ============

CREATE TABLE project_registry (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    slug            VARCHAR(200) NOT NULL UNIQUE,
    description     TEXT,
    repo_url        TEXT,
    repo_type       VARCHAR(20) DEFAULT 'github',
    stack           VARCHAR(100),
    playbook_path   TEXT,
    primary_server_id INTEGER REFERENCES servers(id),
    domain_pattern  VARCHAR(200),
    env_template    JSONB DEFAULT '{}'::JSONB,
    healthcheck_url TEXT,
    on_demand       BOOLEAN DEFAULT false,
    compose_file    VARCHAR(200) DEFAULT 'docker-compose.yml',
    min_ram_mb      INTEGER,
    min_cpu_cores   INTEGER,
    min_disk_gb     INTEGER,
    current_version VARCHAR(100),
    latest_version  VARCHAR(100),
    last_deployed_at TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE: DEPLOY ============

CREATE TABLE deployments (
    id              SERIAL PRIMARY KEY,
    workspace_id    INTEGER NOT NULL REFERENCES project_registry(id),
    server_id       INTEGER REFERENCES servers(id),
    version         VARCHAR(100),
    status          deploy_status NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP,
    triggered_by    VARCHAR(50) NOT NULL DEFAULT 'user',
    deploy_type     VARCHAR(30) NOT NULL DEFAULT 'update',
    rollback_of     INTEGER REFERENCES deployments(id),
    n8n_execution_id VARCHAR(100),
    error_summary   TEXT
);

CREATE TABLE deployment_steps (
    id              SERIAL PRIMARY KEY,
    deployment_id   INTEGER NOT NULL REFERENCES deployments(id),
    step_name       VARCHAR(200) NOT NULL,
    status          deploy_status NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    output          TEXT,
    error           TEXT,
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX deploy_workspace_idx ON deployments(workspace_id, started_at DESC);

-- ============ MODULE: COSTS ============

CREATE TABLE cost_entries (
    id              SERIAL PRIMARY KEY,
    provider        VARCHAR(50) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    amount_eur      REAL NOT NULL DEFAULT 0,
    period_start    TIMESTAMP NOT NULL,
    period_end      TIMESTAMP NOT NULL,
    workspace_id    INTEGER REFERENCES project_registry(id),
    description     TEXT,
    raw_data        JSONB DEFAULT '{}'::JSONB,
    recorded_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX cost_entries_period_idx ON cost_entries(period_start DESC, provider);

-- ============ MODULE: DOMAINS ============

CREATE TABLE domains (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(253) NOT NULL UNIQUE,
    registrar       registrar_type NOT NULL DEFAULT 'namecheap',
    api_provider    VARCHAR(50),
    expiry_date     TIMESTAMP,
    auto_renew      BOOLEAN DEFAULT true,
    ssl_status      VARCHAR(30),
    ssl_expiry      TIMESTAMP,
    nameservers     JSONB DEFAULT '[]'::JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE dns_records (
    id              SERIAL PRIMARY KEY,
    domain_id       INTEGER NOT NULL REFERENCES domains(id),
    record_type     VARCHAR(10) NOT NULL,
    host            VARCHAR(253) NOT NULL,
    value           TEXT NOT NULL,
    ttl             INTEGER DEFAULT 1800,
    mx_pref         INTEGER,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============ MODULE: WAZA ============

CREATE TABLE waza_services (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    compose_file    VARCHAR(200),
    always_on       BOOLEAN DEFAULT false,
    ram_limit_mb    INTEGER,
    cpu_limit       REAL,
    status          VARCHAR(20) DEFAULT 'stopped',
    profile         VARCHAR(50),
    started_at      TIMESTAMP,
    last_stopped_at TIMESTAMP
);

-- ============ SEED: initial servers from nodes table ============
-- Migrate existing node data into servers table

INSERT INTO servers (name, slug, provider, server_role, tailscale_ip, public_ip, status,
                     ssh_port, ssh_user, created_at)
SELECT
    name,
    lower(regexp_replace(name, '[^a-z0-9]', '-', 'gi')),
    'ovh'::provider_type,
    'ai_brain'::server_role,
    tailscale_ip,
    local_ip,
    status::text::node_status,
    804,
    'mobuone',
    created_at
FROM nodes
ON CONFLICT (slug) DO NOTHING;
```

### 2.4 — Apply migrations and update Drizzle schema

- [ ] Apply teardown migration on local dev DB:

  ```bash
  cd roles/palais/files/app && source ../../.venv/bin/activate
  # Or directly: psql postgresql://localhost:5432/palais -f drizzle/0002_palais_v2_teardown.sql
  ```

- [ ] Apply new schema migration:

  ```bash
  psql postgresql://localhost:5432/palais -f drizzle/0003_palais_v2_new_schema.sql
  ```

- [ ] Add new tables to `src/lib/server/db/schema.ts` using Drizzle ORM syntax (matching
  the SQL above, using `pgTable`, `pgEnum`, `integer`, `varchar`, `text`, `real`, `boolean`,
  `timestamp`, `jsonb`, `serial`, `index`, `relations`)
- [ ] Add new enums to schema.ts: `deployStatusEnum`, `providerTypeEnum`, `registrarTypeEnum`,
  `serverRoleEnum`
- [ ] Add Drizzle relations for all new tables
- [ ] Run `npm run check` — verify schema types resolve correctly
- [ ] Run `npm run db:generate` to regenerate Drizzle metadata

**Phase 2 completion gate:** `npm run build` passes. DB has no orphaned tables. MCP server still
responds at `/api/mcp` with `palais.memory.*` tools.

---

## Phase 3: Core Infrastructure — API Integrations (Day 3–5)

**Goal:** Build the server-side integration layer. No UI yet. Each client is independently
testable via a small test script.

### 3.1 — Hetzner Cloud Client

File: `src/lib/server/providers/hetzner.ts`

- [ ] Install package: `npm install hcloud-js` (or use raw fetch against Hetzner API v1)
- [ ] Implement class `HetznerClient` with constructor taking `HETZNER_API_TOKEN` from env
- [ ] Methods to implement:
  - `listServers(): Promise<HetznerServer[]>` — GET /servers
  - `getServer(id: number): Promise<HetznerServer>` — GET /servers/{id}
  - `getServerMetrics(id: number, type: 'cpu'|'memory'|'disk', from: Date, to: Date): Promise<HetznerMetrics>` — GET /servers/{id}/metrics
  - `getBillingCurrentMonth(): Promise<{ amount: number; currency: string }>` — GET /invoices/upcoming
- [ ] Add `HETZNER_API_TOKEN` to env type definition (`src/app.d.ts` or separate `src/lib/env.ts`)
- [ ] Write test script `scripts/test-hetzner.ts`: call `listServers()`, print result
- [ ] Run: `tsx scripts/test-hetzner.ts` (requires live API token in `.env.local`)

### 3.2 — OVH Client

File: `src/lib/server/providers/ovh.ts`

- [ ] Install package: `npm install ovh`
- [ ] Implement class `OvhClient` with keys from env: `OVH_APP_KEY`, `OVH_APP_SECRET`, `OVH_CONSUMER_KEY`, `OVH_ENDPOINT`
- [ ] Methods:
  - `getVpsStatus(serviceName: string): Promise<OvhVpsStatus>` — GET /vps/{serviceName}
  - `getVpsBandwidth(serviceName: string): Promise<OvhBandwidth>` — GET /vps/{serviceName}/monitoring
  - `getInvoices(count?: number): Promise<OvhInvoice[]>` — GET /me/bill
- [ ] Write test script `scripts/test-ovh.ts`

### 3.3 — Namecheap DNS Client

File: `src/lib/server/providers/namecheap.ts`

**Note:** Namecheap API uses XML over HTTPS. No official npm package. Implement raw XML client.

- [ ] Implement class `NamecheapClient` with `NAMECHEAP_API_KEY`, `NAMECHEAP_API_USER`,
  `NAMECHEAP_CLIENT_IP` from env
- [ ] Add `fast-xml-parser` package: `npm install fast-xml-parser`
- [ ] Methods:
  - `getDomains(): Promise<NamecheapDomain[]>` — `namecheap.domains.getList`
  - `getDnsHosts(sld: string, tld: string): Promise<DnsHost[]>` — `namecheap.domains.dns.getHosts`
  - `setDnsHosts(sld: string, tld: string, hosts: DnsHost[]): Promise<void>` — `namecheap.domains.dns.setHosts`
  - `addDnsRecord(domain: string, record: DnsRecord): Promise<void>` — wraps getDnsHosts + setDnsHosts
  - `removeDnsRecord(domain: string, recordId: string): Promise<void>` — wraps getDnsHosts + setDnsHosts
- [ ] Implement XML response parser using `fast-xml-parser`
- [ ] Write test script `scripts/test-namecheap.ts`: call `getDomains()`
- [ ] **Important:** Namecheap requires the calling IP to be whitelisted in API settings. Document
  in test script that VPS IP must be whitelisted, or use whitelisted IP for testing

### 3.4 — Docker Remote Client

File: `src/lib/server/providers/docker-remote.ts`

- [ ] Install package: `npm install node-ssh`
- [ ] Implement class `DockerRemoteClient` taking `server: { tailscale_ip, ssh_port, ssh_user, ssh_key_path }`
- [ ] Methods:
  - `listContainers(): Promise<DockerContainer[]>` — runs `docker ps --format json`
  - `getContainerStats(name: string): Promise<DockerStats>` — runs `docker stats --no-stream --format json <name>`
  - `startContainer(name: string): Promise<void>` — `docker start <name>`
  - `stopContainer(name: string): Promise<void>` — `docker stop <name>`
  - `restartContainer(name: string): Promise<void>` — `docker restart <name>`
  - `getLogs(name: string, lines?: number): Promise<string>` — `docker logs --tail <n> <name>`

  **Note:** `docker ps --format "{{.Names}}"` breaks via Jinja2 in Ansible but is safe to use
  directly via SSH exec from Node.js. Use `docker ps --format json` (Docker 23+) or
  `docker ps --format '{"name":"{{.Names}}","status":"{{.Status}}","image":"{{.Image}}"}'`.

- [ ] Write test script `scripts/test-docker-remote.ts`

### 3.5 — Extend Headscale Client

File: `src/lib/server/health/headscale.ts` (extend existing)

- [ ] Add methods:
  - `getNode(name: string): Promise<VPNNode | null>` — filter from listNodes
  - `getRoutes(): Promise<HeadscaleRoute[]>` — GET /api/v1/routes
- [ ] Export `HeadscaleClient` class wrapping current module-level functions

### 3.6 — Ansible Runner / Deploy Trigger

File: `src/lib/server/deploy/ansible-runner.ts`

- [ ] Implement class `AnsibleRunner` taking `N8N_WEBHOOK_BASE` from env
- [ ] Methods:
  - `triggerDeploy(workspaceSlug: string, version: string, extraVars: Record<string, string>): Promise<{ executionId: string }>` — POST to n8n webhook
  - `triggerProvision(serverSlug: string, provider: string): Promise<{ executionId: string }>` — POST to n8n webhook
  - `getDeployStatus(executionId: string): Promise<{ status: string; steps: DeployStep[] }>` — GET n8n execution status
- [ ] Define webhook payload schema: `{ playbook, workspace, version, extra_vars, callback_url }`
- [ ] Define n8n callback payload schema: `{ executionId, status, steps: [{ name, status, output }] }`
- [ ] Create `/api/v2/deploy/callback/+server.ts` that receives n8n webhook POSTs and updates
  `deployment_steps` table, then broadcasts SSE event

### 3.7 — Cost Aggregator

File: `src/lib/server/costs/aggregator.ts`

- [ ] Move `src/lib/server/budget/litellm.ts` → `src/lib/server/costs/litellm.ts`
  (update import paths)
- [ ] Implement `CostAggregator` class with methods:
  - `getHetznerMonthly(): Promise<CostEntry>` — calls HetznerClient.getBillingCurrentMonth()
  - `getOvhMonthly(): Promise<CostEntry>` — calls OvhClient.getInvoices(1)
  - `getLiteLLMDaily(): Promise<CostEntry>` — from existing litellm.ts logic
  - `getManualCosts(period: DateRange): Promise<CostEntry[]>` — queries `cost_entries` table
  - `aggregate(period: DateRange): Promise<AggregatedCosts>` — combines all sources
  - `getForecast(): Promise<CostForecast>` — simple linear projection from last 7 days

**Phase 3 completion gate:** All 6 provider/service clients have test scripts that run without
errors against live APIs (or return graceful errors if env vars missing).

---

## Phase 4: API Routes — v2 Layer (Day 5–7)

**Goal:** Expose all provider integrations as typed API routes. Use `/api/v2/` prefix to avoid
conflict with remaining v1 routes.

### 4.1 — Fleet API

Directory: `src/routes/api/v2/fleet/`

- [ ] `+server.ts` — GET: list all servers from `servers` table with latest metrics joined
- [ ] `[id]/+server.ts` — GET: single server detail; PATCH: update server metadata
- [ ] `[id]/metrics/+server.ts` — GET: metrics history (last 24h, 7d), query param `?range=24h`
- [ ] `[id]/containers/+server.ts` — GET: live container list via `DockerRemoteClient`
- [ ] `[id]/containers/[name]/+server.ts` — POST body `{ action: 'start'|'stop'|'restart' }`
- [ ] `[id]/containers/[name]/logs/+server.ts` — GET with SSE stream option `?stream=true`
- [ ] `sync/+server.ts` — POST: pull fresh metrics from all servers, store in `server_metrics`

### 4.2 — Workspaces (Project Registry) API

Directory: `src/routes/api/v2/workspaces/`

- [ ] `+server.ts` — GET: list all workspaces; POST: create workspace
- [ ] `[slug]/+server.ts` — GET: workspace detail with latest deployment; PATCH: update; DELETE: archive
- [ ] `[slug]/deploy/+server.ts` — POST: trigger deployment via `AnsibleRunner`
- [ ] `[slug]/rollback/+server.ts` — POST body `{ deploymentId: number }`
- [ ] `[slug]/deployments/+server.ts` — GET: deployment history

### 4.3 — Deploy API

Directory: `src/routes/api/v2/deploy/`

- [ ] `+server.ts` — GET: list all recent deployments across workspaces
- [ ] `[id]/+server.ts` — GET: deployment detail with steps
- [ ] `[id]/sse/+server.ts` — GET: SSE stream of real-time step progress (uses `src/lib/stores/sse.ts`)
- [ ] `callback/+server.ts` — POST: receives n8n completion webhook, updates DB + broadcasts SSE

### 4.4 — Services API

Directory: `src/routes/api/v2/services/`

- [ ] `+server.ts` — GET `?serverId=X`: list containers on a given server
- [ ] `[serverId]/[containerName]/+server.ts` — POST: `{ action }`, GET: stats

### 4.5 — Costs API

Directory: `src/routes/api/v2/costs/`

- [ ] `+server.ts` — GET: aggregated costs for current month
- [ ] `providers/+server.ts` — GET: per-provider breakdown
- [ ] `history/+server.ts` — GET `?months=6`: monthly cost history from `cost_entries`
- [ ] `forecast/+server.ts` — GET: next-30-day projection
- [ ] `entries/+server.ts` — POST: manually log a cost entry

### 4.6 — Domains API

Directory: `src/routes/api/v2/domains/`

- [ ] `+server.ts` — GET: list all domains from `domains` table (optionally sync from Namecheap)
- [ ] `sync/+server.ts` — POST: pull domain list from Namecheap, upsert into `domains` table
- [ ] `[name]/+server.ts` — GET: domain detail
- [ ] `[name]/dns/+server.ts` — GET: DNS records; POST: add record
- [ ] `[name]/dns/[id]/+server.ts` — PATCH: update record; DELETE: remove record

### 4.7 — Terminal WebSocket

File: `src/routes/api/v2/terminal/+server.ts`

- [ ] Implement WebSocket upgrade handler (SvelteKit 2 uses `handleWebsocket` in `hooks.server.ts`)
- [ ] On connect: validate `X-API-Key` header; parse `?server=slug` query param
- [ ] Pipe WebSocket messages to SSH shell session via `node-ssh` exec stream
- [ ] On disconnect: close SSH session
- [ ] Enforce timeout: 30-minute idle disconnect

**Note:** SvelteKit 2 WebSocket support is via the `@sveltejs/adapter-node` raw server hook.
Check `src/lib/server/ws/openclaw.ts` for existing pattern to follow.

### 4.8 — Waza API

Directory: `src/routes/api/v2/waza/`

- [ ] `+server.ts` — GET: list all Waza services from `waza_services` table with live status
- [ ] `[slug]/+server.ts` — POST body `{ action: 'start'|'stop' }`: control service via DockerRemoteClient on Pi
- [ ] `[slug]/status/+server.ts` — GET: live status polled from Pi
- [ ] `profiles/+server.ts` — GET: list available profiles; POST `{ profile }`: activate profile
  (start/stop groups of services)

### 4.9 — Shared response format

File: `src/lib/server/api/response.ts`

- [ ] Define typed envelope:

  ```typescript
  export function ok<T>(data: T, meta?: ApiMeta): ApiResponse<T>
  export function err(message: string, code?: number): ApiErrorResponse
  ```

- [ ] Use consistently across all v2 routes

**Phase 4 completion gate:** All API routes return valid JSON. Test with `curl` against running
dev server. SSE endpoint streams events correctly.

---

## Phase 5: Frontend — New Pages and Components (Day 7–12)

**Goal:** Build all v2 UI using the existing Afrofuturist design system. Adinkra icons are already
in `src/lib/components/icons/` — the sidebar simply remaps them.

### 5.1 — Sidebar v2

File: `src/lib/components/layout/Sidebar.svelte` (full replacement)

- [ ] Update nav array:

  ```typescript
  const nav = [
    { href: '/',           label: 'Dashboard',   icon: GyeNyame       },
    { href: '/fleet',      label: 'Fleet',        icon: Aya            },
    { href: '/workspaces', label: 'Workspaces',   icon: AnanseNtontan  },
    { href: '/services',   label: 'Services',     icon: Bese           },
    { href: '/deploy',     label: 'Deploy',       icon: Nkyinkyim      },
    { href: '/costs',      label: 'Costs',        icon: Akoma          },
    { href: '/domains',    label: 'Domains',      icon: Fawohodie      },
    { href: '/terminal',   label: 'Terminal',     icon: Sankofa        },
    { href: '/waza',       label: 'Waza',         icon: Dwennimmen     },
    { href: '/memory',     label: 'Memory',       icon: Nyame          },
  ];
  ```

- [ ] Update version tag at bottom: `v2`
- [ ] Keep all CSS/animation unchanged — design system is preserved exactly

### 5.2 — Dashboard v2

Files: `src/routes/+page.svelte`, `src/routes/+page.server.ts`

**Goal:** Replace agent-centric dashboard with infrastructure overview.

- [ ] `+page.server.ts`: load data from `/api/v2/fleet` (server count, online count), latest
  deployment per workspace, cost summary for current month, active alerts (from `server_metrics`
  where `cpu_percent > 90` or `ram_used_mb / ram_total_mb > 0.9`)

- [ ] `+page.svelte` layout:
  - Header: PALAIS wordmark + live clock (keep unchanged)
  - Row 1: Bento stat cards — Servers Online N/M, Containers Running, Monthly Cost €X, Active Deploys
  - Row 2: Server health mini-grid (small cards, one per server, color-coded by status)
  - Row 3: Recent deployments timeline (last 5)
  - Row 4: Waza quick-controls (on-demand service toggles)

- [ ] New component: `src/lib/components/dashboard/StatCard.svelte` — bento card with metric,
  label, trend indicator, Adinkra icon. Accepts `value`, `label`, `icon`, `trend`, `color` props.

- [ ] New component: `src/lib/components/dashboard/MiniServerCard.svelte` — compact server
  status card with CPU/RAM bars.

- [ ] New component: `src/lib/components/dashboard/DeploymentTimeline.svelte` — vertical
  list of recent deploys with status badge and relative time.

### 5.3 — Fleet page

Files: `src/routes/fleet/+page.svelte`, `src/routes/fleet/+page.server.ts`

- [ ] `+page.server.ts`: fetch all servers with latest metrics from `/api/v2/fleet`
- [ ] Provider filter tabs: All | Hetzner | OVH | Ionos | Local
- [ ] Server card grid: name, provider badge, Tailscale IP, status dot, CPU gauge, RAM gauge, disk %
- [ ] Click on card → open `ServerDetailModal.svelte` (slide-over panel) showing containers list,
  SSH port, last seen, metrics history sparkline
- [ ] "Sync metrics" button calls `POST /api/v2/fleet/sync`

New components:
- [ ] `src/lib/components/fleet/ServerCard.svelte`
- [ ] `src/lib/components/fleet/ServerDetailModal.svelte`
- [ ] `src/lib/components/fleet/ContainerList.svelte` — table with name, status, image, uptime

### 5.4 — Workspaces page

Files: `src/routes/workspaces/`, `src/routes/workspaces/[slug]/`

- [ ] `+page.svelte`: project card grid — name, slug, stack badge, server assigned, last deploy
  status, "Deploy" button
- [ ] `+page.server.ts`: list all from `project_registry` joined with latest deployment
- [ ] `[slug]/+page.svelte`: workspace detail
  - Header: name, repo link, domain, current version
  - "Deploy" button → opens `DeployModal.svelte` (confirm version, extra vars)
  - `DeployProgressPanel.svelte` — SSE-powered step progress (replaces old missions warroom pattern)
  - Deployment history table
- [ ] `[slug]/+page.server.ts`: single workspace + deployment history

New components:
- [ ] `src/lib/components/workspaces/WorkspaceCard.svelte`
- [ ] `src/lib/components/workspaces/DeployModal.svelte`
- [ ] `src/lib/components/workspaces/DeployProgressPanel.svelte` — subscribes to `/api/v2/deploy/[id]/sse`
  Shows steps with scan-line animation between them while running

### 5.5 — Services page

Files: `src/routes/services/`

- [ ] Server selector dropdown (top of page) — persisted in `localStorage`
- [ ] Container table: name, image, status badge (green/red/yellow), CPU %, RAM MB, uptime,
  Start/Stop/Restart action buttons, "Logs" button
- [ ] Log panel (slide-over): streams logs from `/api/v2/services/[serverId]/[name]/logs?stream=true`
- [ ] Resource summary bar: total containers, running count, total RAM used vs limit

New components:
- [ ] `src/lib/components/services/ContainerTable.svelte`
- [ ] `src/lib/components/services/LogPanel.svelte` — SSE log stream with ANSI color support
  (use a minimal ANSI-to-CSS converter, ~50 lines)

### 5.6 — Deploy page

Files: `src/routes/deploy/`, `src/routes/deploy/[id]/`

- [ ] `+page.svelte`: deploy history list across all workspaces — date, workspace, version,
  status badge, duration, triggered by
- [ ] Filter tabs: All | Running | Success | Failed
- [ ] `[id]/+page.svelte`: deploy detail — step-by-step progress with timeline
  - Each step: icon (pending/running/success/fail), name, duration, expand to show output
  - Scan-line animation plays on the currently running step
- [ ] Rollback button (only shown if deploy succeeded and a previous deploy exists)

### 5.7 — Costs page

Files: `src/routes/costs/`

- [ ] Total cost card with €X/month and daily burn rate
- [ ] Budget gauge: current vs configured monthly limit
- [ ] Provider breakdown: horizontal bars — Hetzner N%, OVH N%, AI N%, Other N%
- [ ] Workspace attribution table: which workspaces consume what share (if tagged)
- [ ] Monthly trend: simple SVG bar chart (use d3-scale — reinstall if needed)
- [ ] "Optimizer" recommendation cards (rule-based): e.g. "Hetzner idle server detected",
  "AI budget at 87% with 8 days left"

### 5.8 — Domains page

Files: `src/routes/domains/`, `src/routes/domains/[name]/`

- [ ] Domain table: name, registrar, expiry (color: green > 60d, yellow 30–60d, red < 30d),
  SSL status, SSL expiry, actions
- [ ] "Sync from Namecheap" button → calls `POST /api/v2/domains/sync`
- [ ] `[name]/+page.svelte`: domain detail
  - DNS record table with record type, host, value, TTL
  - Inline edit: click value cell → editable input → save → calls PATCH endpoint
  - "Add record" form (type, host, value, TTL)
  - Delete record button with confirmation

### 5.9 — Terminal page

File: `src/routes/terminal/+page.svelte`

- [ ] Install xterm.js: `npm install @xterm/xterm @xterm/addon-fit`
- [ ] Server tab bar: one tab per server in `servers` table
- [ ] xterm.js instance per tab (lazy init on tab activation)
- [ ] WebSocket connection to `/api/v2/terminal?server=slug` with `X-API-Key` header
- [ ] Theme: dark background (`--palais-bg`), gold cursor (`--palais-gold`), JetBrains Mono font
- [ ] `fit` addon: auto-resize terminal on window resize
- [ ] Disconnect indicator if WebSocket closes (red border, "DISCONNECTED" overlay)
- [ ] Reconnect button

### 5.10 — Waza page

Files: `src/routes/waza/`

- [ ] RAM gauge: donut chart showing Pi RAM used vs total (d3-scale)
- [ ] Service cards: name, status badge, RAM limit, CPU limit, uptime, Start/Stop button
- [ ] Profile quick-switch: button row — "Minimal" / "Development" / "Full" — activates
  a preset group of services
- [ ] Resource warning banner: if RAM > 80% → yellow, > 95% → red with scan-line animation
- [ ] Auto-refresh: poll `/api/v2/waza` every 30s

### 5.11 — Agents page (simplify)

File: `src/routes/agents/+page.svelte` (simplify, keep structure)

- [ ] Remove any references to tasks, missions in the agent detail view
- [ ] Show: agent cards with status, model, sessions count (last 30 days), spend (last 30 days)
- [ ] Agent detail (`/agents/[id]`): session list only — no task references

**Phase 5 completion gate:** All 9 new module pages render without runtime errors. Design
system (glassmorphism, Adinkra icons, gold palette, scan-line animations) is consistent with v1.

---

## Phase 6: MCP Extension (Day 12–13)

**Goal:** Add v2 tool domains to the MCP server, keeping all existing `palais.memory.*` tools
intact and unchanged.

### 6.1 — New tool files

- [ ] `src/lib/server/mcp/tools/fleet.ts` — tools:
  - `palais.fleet.servers` — list all servers with status and resource summary
  - `palais.fleet.server_status` — get a specific server by slug; returns health, metrics, containers
- [ ] `src/lib/server/mcp/tools/workspaces.ts` — tools:
  - `palais.workspaces.list` — list all project workspaces with deploy status
  - `palais.workspaces.deploy` — trigger a deployment, return deployment ID
- [ ] `src/lib/server/mcp/tools/services.ts` — tools:
  - `palais.services.list` — list containers on a given server (param: `server` slug)
  - `palais.services.control` — start/stop/restart a container (params: `server`, `container`, `action`)
- [ ] `src/lib/server/mcp/tools/costs.ts` — tools:
  - `palais.costs.summary` — current month total + per-provider breakdown
- [ ] `src/lib/server/mcp/tools/domains.ts` — tools:
  - `palais.domains.list` — list all domains with expiry and SSL status
  - `palais.domains.dns_records` — get DNS records for a domain (param: `domain`)

### 6.2 — Update registry and executor

File: `src/lib/server/mcp/tools/registry.ts`

- [ ] Add imports and registrations for all 5 new tool files
- [ ] Keep `memoryToolDefs` and `agentToolDefs` unchanged — they come first in the array

File: `src/lib/server/mcp/tools/executor.ts`

- [ ] Add cases for `fleet`, `workspaces`, `services`, `costs`, `domains` domains
- [ ] Keep all existing cases unchanged

### 6.3 — Update MCP server version

File: `src/lib/server/mcp/router.ts`

- [ ] Update `serverInfo.version` from `'1.0.0'` to `'2.0.0'`

### 6.4 — Test all MCP tools

- [ ] Run `tsx scripts/test-mcp.ts` (update script to test new tools)
- [ ] Verify `palais.memory.search` still works (regression check)
- [ ] Verify `palais.fleet.servers` returns server list
- [ ] Verify `palais.workspaces.list` returns project registry
- [ ] Test `palais.services.list` with a valid server slug

**Phase 6 completion gate:** MCP `tools/list` returns 15+ tools. `palais.memory.*` tools pass
regression test. At least one tool from each new domain executes successfully.

---

## Phase 7: Ansible Role Update (Day 13–14)

**Goal:** Make the Ansible role deploy Palais v2 correctly with new environment variables, updated
resource limits, new migration tasks, and SSH key volume mount for terminal access.

### 7.1 — Update `palais.env.j2`

File: `roles/palais/templates/palais.env.j2`

- [ ] Remove: `COMFYUI_URL`, `STANDUP_HOUR`
- [ ] Remove: `OPENAI_API_KEY` direct (costs go through LiteLLM only now)
- [ ] Keep: `DATABASE_URL`, `OPENCLAW_WS_URL`, `LITELLM_URL`, `LITELLM_KEY`, `QDRANT_URL`,
  `QDRANT_COLLECTION`, `PALAIS_API_KEY`, `PALAIS_ADMIN_PASSWORD`, `SESSION_SECRET`,
  `PORT`, `HOST`, `ORIGIN`, `NODE_ENV`, `TZ`, `HEADSCALE_URL`, `HEADSCALE_API_KEY`,
  `N8N_WEBHOOK_BASE`
- [ ] Add new vars:

  ```jinja2
  # Hetzner Cloud
  HETZNER_API_TOKEN={{ hetzner_api_token | default('') }}

  # OVH API
  OVH_ENDPOINT={{ ovh_endpoint | default('ovh-eu') }}
  OVH_APP_KEY={{ ovh_app_key | default('') }}
  OVH_APP_SECRET={{ ovh_app_secret | default('') }}
  OVH_CONSUMER_KEY={{ ovh_consumer_key | default('') }}
  OVH_VPS_SERVICE={{ ovh_vps_service | default('') }}

  # Namecheap DNS
  NAMECHEAP_API_KEY={{ namecheap_api_key | default('') }}
  NAMECHEAP_API_USER={{ namecheap_api_user | default('') }}
  NAMECHEAP_CLIENT_IP={{ namecheap_client_ip | default('') }}

  # Deploy SSH key (for DockerRemoteClient via SSH)
  SSH_DEPLOY_KEY_PATH=/run/secrets/deploy_key

  # n8n Deploy webhooks
  N8N_DEPLOY_WEBHOOK={{ n8n_deploy_webhook | default('') }}
  N8N_PROVISION_WEBHOOK={{ n8n_provision_webhook | default('') }}

  # Monthly budget limits (EUR) for cost gauge
  BUDGET_MONTHLY_LIMIT_EUR={{ palais_budget_monthly_limit | default('50') }}
  ```

### 7.2 — Update `defaults/main.yml`

File: `roles/palais/defaults/main.yml`

- [ ] Update resource limits (v2 requires more RAM for provider API calls and WebSocket sessions):
  ```yaml
  palais_memory_limit: "256M"
  palais_memory_reservation: "192M"
  palais_cpu_limit: "1.0"
  ```
- [ ] Add new defaults:
  ```yaml
  palais_budget_monthly_limit: "50"
  namecheap_client_ip: "{{ prod_ssh_host | default('') }}"
  ovh_endpoint: "ovh-eu"
  ```
- [ ] Remove: `palais_standup_hour`, `palais_comfyui_port`

### 7.3 — Add vault variables for new secrets

File: `inventory/group_vars/all/secrets.yml` (Ansible Vault — edit with `ansible-vault edit`)

- [ ] Add:
  ```yaml
  vault_hetzner_api_token: "..."
  vault_ovh_app_key: "..."
  vault_ovh_app_secret: "..."
  vault_ovh_consumer_key: "..."
  vault_namecheap_api_key: "..."
  vault_namecheap_api_user: "..."
  ```

File: `inventory/group_vars/all/main.yml`

- [ ] Add references:
  ```yaml
  hetzner_api_token: "{{ vault_hetzner_api_token | default('') }}"
  ovh_app_key: "{{ vault_ovh_app_key | default('') }}"
  ovh_app_secret: "{{ vault_ovh_app_secret | default('') }}"
  ovh_consumer_key: "{{ vault_ovh_consumer_key | default('') }}"
  namecheap_api_key: "{{ vault_namecheap_api_key | default('') }}"
  namecheap_api_user: "{{ vault_namecheap_api_user | default('') }}"
  n8n_deploy_webhook: "webhook-deploy-palais-v2"
  n8n_provision_webhook: "webhook-provision"
  ```

### 7.4 — Update `tasks/main.yml`

File: `roles/palais/tasks/main.yml`

- [ ] Add DB migration task for `0002_palais_v2_teardown.sql`:

  ```yaml
  - name: Palais DB migration v2 — teardown v1 tables
    ansible.builtin.command:
      cmd: >-
        docker exec {{ project_name }}_postgresql psql -U {{ palais_db_user }} -d {{ palais_db_name }}
        -f /tmp/0002_palais_v2_teardown.sql
    # Copy file first with ansible.builtin.copy, then execute
    become: true
    changed_when: false
    when:
      - not (common_molecule_mode | default(false))
      - _pg_container_check.rc | default(1) == 0
    tags: [palais, palais-migrate]
  ```

- [ ] Add DB migration task for `0003_palais_v2_new_schema.sql` (same pattern)
- [ ] Add SSH deploy key secret mount task (mount `seko-vpn-deploy` key as Docker secret or
  volume at `/run/secrets/deploy_key` inside the container)
- [ ] Remove: standup-related tasks (none exist currently — just remove any scheduler startup)

### 7.5 — Update `docker-compose.yml.j2` in palais role (if file exists)

- [ ] If `roles/palais/templates/docker-compose.yml.j2` exists (check): update memory limit,
  add SSH key volume mount
- [ ] If palais is defined inline in the main `docker-compose.yml.j2` template (at the Sese-AI
  role level): locate the `palais` service block and update memory/CPU limits

### 7.6 — Update `claude-mcp-config.json.j2`

File: `roles/palais/templates/claude-mcp-config.json.j2`

- [ ] No URL changes needed (MCP endpoint stays at `/api/mcp/sse`)
- [ ] Add `description` field if not present:

  ```json
  {
    "palais": {
      "type": "sse",
      "url": "https://{{ palais_subdomain }}.{{ domain_name }}/api/mcp/sse",
      "headers": {
        "X-API-Key": "{{ palais_api_key }}"
      },
      "description": "Palais v2 — Infrastructure Control Plane (fleet, workspaces, deploy, costs, memory)"
    }
  }
  ```

### 7.7 — n8n webhook workflows

- [ ] Create n8n workflow: `palais-deploy-trigger` — receives POST from `AnsibleRunner`,
  runs `ansible-playbook` via SSH exec, sends step callbacks to `POST /api/v2/deploy/callback`
- [ ] Export workflow JSON and store in `roles/n8n/files/workflows/palais-deploy-trigger.json`
  for reproducible deployment
- [ ] Document webhook URL pattern in `inventory/group_vars/all/main.yml`

### 7.8 — Lint and test

- [ ] Run `make lint` from VPAI root
- [ ] Run Molecule test: `make test-role ROLE=palais` (verifies idempotence)
- [ ] Dry-run: `ansible-playbook playbooks/site.yml --tags palais --check --diff`

**Phase 7 completion gate:** `make lint` passes 0 errors. Dry-run shows expected changes only
(env file update, resource limit update). No tasks show CHANGED on second run (idempotence).

---

## Phase 8: Integration Testing (Day 14–15)

**Goal:** Verify end-to-end functionality of all v2 modules on production.

### 8.1 — Provider API connectivity

- [ ] Hetzner: `GET /api/v2/fleet` returns real server list from Hetzner API
- [ ] OVH: OVH VPS appears in server list with correct provider badge
- [ ] Namecheap: `GET /api/v2/domains` returns real domain list
- [ ] Headscale: nodes appear with Tailscale IPs and online status

### 8.2 — Docker remote control

- [ ] Test `GET /api/v2/fleet/[id]/containers` on each server — returns container list
- [ ] Test `POST /api/v2/fleet/[id]/containers/[name]` with `{ action: "restart" }` on a safe test container
- [ ] Verify container restart visible in Services page within 5 seconds

### 8.3 — Deploy pipeline

- [ ] Trigger a test deployment from Workspaces page (use a non-critical workspace like `zimboo`)
- [ ] Verify SSE stream delivers step events to `DeployProgressPanel`
- [ ] Verify deployment record created in `deployments` table with correct steps
- [ ] Verify n8n callback updates step statuses correctly

### 8.4 — DNS record management

- [ ] `GET /api/v2/domains/seko.work/dns` returns correct DNS records
- [ ] `POST /api/v2/domains/seko.work/dns` with a test TXT record — verify in Namecheap API
- [ ] Delete the test TXT record
- [ ] Verify no side effects on existing records

### 8.5 — WebSocket terminal

- [ ] Open `/terminal`, select Sese-AI server tab
- [ ] WebSocket connects (check browser network tab — status 101)
- [ ] Type `hostname` — verify correct hostname returns
- [ ] Type `docker ps | head -5` — verify output
- [ ] Close tab — verify SSH session closes (check server `who` command shows no lingering sessions)
- [ ] Test 3 concurrent terminal connections to same server

### 8.6 — MCP tools regression

- [ ] From Pi, run: `tsx /home/asus/seko/VPAI/roles/palais/files/app/scripts/test-mcp.ts`
- [ ] Verify `palais.memory.search` with query "ansible" returns results
- [ ] Verify `palais.memory.store` creates new node
- [ ] Verify `palais.fleet.servers` returns server list
- [ ] Verify `palais.workspaces.list` returns project registry
- [ ] Verify `palais.costs.summary` returns monthly total

### 8.7 — Memory/Knowledge Graph

- [ ] Open `/memory` — verify knowledge graph renders
- [ ] Search for "postgresql" — verify semantic search returns relevant nodes
- [ ] Add a new memory node via the UI — verify it appears in graph

### 8.8 — Cost aggregation accuracy

- [ ] Compare Hetzner cost shown in Costs page vs Hetzner Cloud Console — must match within 5%
- [ ] Verify OVH invoice amount matches OVH Manager
- [ ] Verify LiteLLM daily budget shown matches LiteLLM UI → Settings → Budget

### 8.9 — Load test

- [ ] 3 concurrent terminal WebSocket sessions open simultaneously — no server crash
- [ ] SSE deploy stream active + 5 concurrent Fleet page loads — no timeout
- [ ] Verify container stays under 256MB RAM limit: `docker stats javisi_palais --no-stream`

---

## MCP Continuity Protocol

This is the most critical constraint of the entire refactoring.

### MCP tools survival matrix

| Phase | `palais.memory.*` | `palais.agents.*` | `palais.tasks.*` | `palais.fleet.*` |
|-------|:-----------------:|:-----------------:|:----------------:|:----------------:|
| v1 (before) | Active | Active | Active | — |
| After Phase 1 | **Active** | Active | Removed | — |
| After Phase 2 | **Active** | Active | — | — |
| After Phase 6 | **Active** | Active | — | **Active** |
| v2 final | **Active** | Active | — | **Active** |

### If MCP breaks during development

1. Check `/api/mcp` responds with HTTP 200: `curl -s -X POST https://palais.seko.work/api/mcp -H "X-API-Key: $PALAIS_API_KEY" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'`
2. Check SSE endpoint: `curl -N -H "X-API-Key: $PALAIS_API_KEY" https://palais.seko.work/api/mcp/sse`
3. Roll back to last working commit on `feat/palais-v2` branch
4. Fix forward — never delete `src/lib/server/mcp/` directory at any point

---

## npm Package Changes Summary

### Packages to remove (Phase 1)

```bash
npm uninstall \
  @tiptap/core @tiptap/extension-placeholder @tiptap/pm @tiptap/starter-kit \
  svelte-dnd-action \
  @types/d3-force d3-force  # keep if memory graph uses it; otherwise remove
```

**Check before removing d3-force:** Search for usage in `src/routes/memory/+page.svelte`
and `src/lib/server/utils/graph.ts`. If used by memory graph → keep.

### Packages to add (Phases 3–5)

```bash
npm install \
  ovh \
  fast-xml-parser \
  node-ssh \
  @xterm/xterm \
  @xterm/addon-fit
```

**Note on hcloud:** Prefer raw `fetch` calls against `https://api.hetzner.cloud/v1/` rather
than adding an npm package dependency. The Hetzner API is simple REST and a native client
saves 50KB of bundle size.

---

## File Map — Complete v2 Source Tree

After all phases, the `src/` directory will look like:

```
src/
├── app.css                            (unchanged)
├── app.d.ts                           (add new env vars)
├── app.html                           (unchanged)
├── hooks.server.ts                    (remove scheduler init, add WS handler)
├── lib/
│   ├── assets/favicon.svg
│   ├── components/
│   │   ├── agents/AgentCard.svelte    (unchanged)
│   │   ├── dashboard/
│   │   │   ├── StatCard.svelte        (NEW)
│   │   │   ├── MiniServerCard.svelte  (NEW)
│   │   │   └── DeploymentTimeline.svelte (NEW)
│   │   ├── fleet/
│   │   │   ├── ServerCard.svelte      (NEW)
│   │   │   ├── ServerDetailModal.svelte (NEW)
│   │   │   └── ContainerList.svelte   (NEW)
│   │   ├── icons/                     (unchanged — all 10 Adinkra icons)
│   │   ├── layout/
│   │   │   └── Sidebar.svelte         (updated nav items)
│   │   ├── services/
│   │   │   ├── ContainerTable.svelte  (NEW)
│   │   │   └── LogPanel.svelte        (NEW)
│   │   └── workspaces/
│   │       ├── WorkspaceCard.svelte   (NEW)
│   │       ├── DeployModal.svelte     (NEW)
│   │       └── DeployProgressPanel.svelte (NEW)
│   ├── index.ts
│   ├── server/
│   │   ├── api/response.ts            (NEW)
│   │   ├── costs/
│   │   │   ├── aggregator.ts          (NEW)
│   │   │   └── litellm.ts             (moved from budget/)
│   │   ├── db/
│   │   │   ├── index.ts               (unchanged)
│   │   │   └── schema.ts              (updated — v2 tables)
│   │   ├── deploy/
│   │   │   └── ansible-runner.ts      (NEW)
│   │   ├── health/
│   │   │   └── headscale.ts           (extended)
│   │   ├── llm/client.ts              (unchanged)
│   │   ├── mcp/
│   │   │   ├── router.ts              (version bump only)
│   │   │   ├── sse.ts                 (unchanged)
│   │   │   ├── types.ts               (unchanged)
│   │   │   └── tools/
│   │   │       ├── agents.ts          (unchanged)
│   │   │       ├── costs.ts           (NEW)
│   │   │       ├── domains.ts         (NEW)
│   │   │       ├── executor.ts        (add new domains, remove old)
│   │   │       ├── fleet.ts           (NEW)
│   │   │       ├── memory.ts          (unchanged)
│   │   │       ├── registry.ts        (updated)
│   │   │       ├── services.ts        (NEW)
│   │   │       └── workspaces.ts      (NEW)
│   │   ├── memory/                    (unchanged)
│   │   └── providers/
│   │       ├── docker-remote.ts       (NEW)
│   │       ├── hetzner.ts             (NEW)
│   │       ├── namecheap.ts           (NEW)
│   │       └── ovh.ts                 (NEW)
│   ├── stores/sse.ts                  (unchanged)
│   ├── styles/theme.css               (unchanged)
│   ├── types/agent.ts                 (unchanged)
│   └── utils.ts                       (unchanged)
├── routes/
│   ├── +layout.svelte                 (unchanged)
│   ├── +page.server.ts                (updated — infrastructure data)
│   ├── +page.svelte                   (updated — bento dashboard)
│   ├── agents/                        (simplified, keep)
│   ├── api/
│   │   ├── auth/login/                (unchanged)
│   │   ├── health/                    (unchanged)
│   │   ├── mcp/                       (unchanged)
│   │   ├── sse/                       (unchanged)
│   │   └── v1/
│   │       ├── agents/                (unchanged)
│   │       ├── health/                (unchanged)
│   │       └── memory/                (unchanged)
│   │   └── v2/
│   │       ├── costs/                 (NEW)
│   │       ├── deploy/                (NEW)
│   │       ├── domains/               (NEW)
│   │       ├── fleet/                 (NEW)
│   │       ├── services/              (NEW)
│   │       ├── terminal/              (NEW)
│   │       ├── waza/                  (NEW)
│   │       └── workspaces/            (NEW)
│   ├── costs/                         (NEW)
│   ├── deploy/                        (NEW)
│   ├── domains/                       (NEW)
│   ├── fleet/                         (NEW)
│   ├── health/                        (unchanged)
│   ├── login/                         (unchanged)
│   ├── memory/                        (unchanged)
│   ├── services/                      (NEW)
│   ├── terminal/                      (NEW)
│   ├── waza/                          (NEW)
│   └── workspaces/                    (NEW)
└── static/robots.txt
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MCP SSE connection drops during teardown | Medium | High | Never touch `src/routes/api/mcp/` — delete only other routes |
| Namecheap IP whitelist blocks API | Medium | Medium | Whitelist VPS public IP in Namecheap API settings before Phase 3 |
| Hetzner metrics endpoint rate limit | Low | Low | Cache results in `server_metrics` table, max 1 sync per 5 minutes |
| Terminal WebSocket leaks SSH sessions | Medium | Medium | Implement timeout + cleanup on disconnect in `hooks.server.ts` |
| PostgreSQL enum types cannot be dropped while in use | Low | Medium | Migration 0002 uses `CASCADE` — verify no views or triggers reference dropped enums |
| n8n webhook URL changes break deploy trigger | Low | High | Store webhook paths in `inventory/group_vars/all/main.yml` as variables, not hardcoded |
| Docker remote SSH auth fails from container | Medium | High | Test SSH key volume mount in dev before Phase 7 deploy |
| xterm.js WebSocket incompatible with SvelteKit SSR | Low | Medium | Lazy-load xterm.js with `import()` inside `onMount()` to avoid SSR |

---

## Success Criteria

The refactor is complete when all of the following are true:

- [ ] `npm run build` produces a clean build with 0 TypeScript errors and 0 warnings
- [ ] `make lint` passes in the VPAI root
- [ ] Molecule tests pass for the `palais` role (idempotent, changed=0 on second run)
- [ ] MCP tools/list returns at minimum: `palais.memory.search`, `palais.memory.recall`,
  `palais.memory.store`, `palais.agents.list`, `palais.fleet.servers`,
  `palais.workspaces.list`, `palais.workspaces.deploy`, `palais.services.list`,
  `palais.costs.summary`, `palais.domains.list`
- [ ] All 9 module pages render without runtime errors in the browser
- [ ] Provider APIs (Hetzner, OVH, Namecheap) respond correctly in the production environment
- [ ] Docker remote control works on at least 2 servers (Sese-AI + Seko-VPN)
- [ ] Terminal WebSocket connects and streams a live SSH session
- [ ] Deploy pipeline can trigger a Zimboo redeploy end-to-end (Palais → n8n → Ansible → callback → SSE)
- [ ] Container stays under 256MB RAM during steady-state operation
- [ ] `git tag palais-v2-final` applied to final working commit on `feat/palais-v2`
- [ ] PR merged to `main` after passing CI lint checks
