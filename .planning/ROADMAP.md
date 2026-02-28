# Roadmap: Plane — Operational Intelligence

## Overview

Deploy Plane as the central operational hub for the VPAI stack, replacing Kaneo. The journey goes: get Plane running on Sese-AI with full infra integration (Phase 1), upgrade OpenClaw to v2026.2.26 to enable secure agent spawning (Phase 2), build the plane-bridge skill so agents can interact with Plane (Phase 3), then wire up notifications and Telegram commands for real-time orchestration (Phase 4).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Plane Deployment** - Plane running on Sese-AI with PostgreSQL, Redis, Caddy, auth, provisioning, monitoring, and backup
- [ ] **Phase 2: OpenClaw Upgrade** - Upgrade OpenClaw from v2026.2.23 to v2026.2.26 with spawn security validation
- [ ] **Phase 3: Agent Integration** - plane-bridge skill with all 8 MCP tools, polling, custom fields, and agent workflows
- [ ] **Phase 4: Notifications & Orchestration** - Webhooks, n8n workflows, Telegram commands, and Concierge orchestration flow

## Phase Details

### Phase 1: Plane Deployment
**Goal**: Plane is accessible at `work.ewutelo.cloud`, connected to shared PostgreSQL and Redis, with admin accounts provisioned, monitoring active, and backup integrated
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, AUTH-01, AUTH-02, AUTH-03, AUTH-04, PROV-01, PROV-02, PROV-03, PROV-04, MONITOR-01, MONITOR-02, MONITOR-03, MONITOR-04
**Success Criteria** (what must be TRUE):
  1. User can access Plane UI at `work.ewutelo.cloud` via VPN and log in with email/password
  2. Concierge admin account exists and can create projects, issues, and API tokens from the UI
  3. Plane containers (web, api, worker) are running within resource limits, with healthchecks green in Grafana
  4. Plane database `plane_production` is included in the daily Zerobyte PostgreSQL backup
  5. Custom fields (`agent_id`, `cost_estimate`, `confidence_score`, `session_id`) exist on the workspace
**Plans**: TBD

Plans:
- [ ] 01-01: Ansible role `plane` (Docker Compose, env, Caddy, resource limits)
- [ ] 01-02: PostgreSQL/Redis integration, provisioning (workspace, accounts, tokens, custom fields)
- [ ] 01-03: Monitoring, backup, and smoke tests

### Phase 2: OpenClaw Upgrade
**Goal**: OpenClaw is running v2026.2.26 with all agents spawning correctly and security hardened
**Depends on**: Phase 1 (Plane must be running for plane-bridge compatibility test in OPENCLAW-UPG-13)
**Requirements**: OPENCLAW-UPG-01, OPENCLAW-UPG-02, OPENCLAW-UPG-03, OPENCLAW-UPG-04, OPENCLAW-UPG-05, OPENCLAW-UPG-06, OPENCLAW-UPG-07, OPENCLAW-UPG-08, OPENCLAW-UPG-09, OPENCLAW-UPG-10, OPENCLAW-UPG-11, OPENCLAW-UPG-12, OPENCLAW-UPG-13, OPENCLAW-UPG-14, OPENCLAW-UPG-15
**Success Criteria** (what must be TRUE):
  1. OpenClaw v2026.2.26 is running and Concierge can spawn Imhotep successfully (`openclaw send` test passes)
  2. All agent processes run as UID 1000 (no privilege escalation) and filesystem isolation is intact
  3. Rollback to v2026.2.23 is possible in under 2 minutes via `make deploy-role ROLE=openclaw`
  4. Breaking changes (DM allowlist, onboarding scope) are configured and documented in REX
**Plans**: TBD

Plans:
- [ ] 02-01: Upgrade execution (backup, version pin, deploy, spawn validation, security audit)
- [ ] 02-02: Breaking changes config, plane-bridge compatibility, rollback validation, REX documentation

### Phase 3: Agent Integration
**Goal**: OpenClaw agents can discover tasks in Plane, update status/progress, and the Concierge can create and assign work through Plane API
**Depends on**: Phase 1 (Plane API available), Phase 2 (OpenClaw v2026.2.26 with plane-bridge skill loaded)
**Requirements**: OPENCLAW-01, OPENCLAW-02, OPENCLAW-03, OPENCLAW-04, OPENCLAW-05, OPENCLAW-06, OPENCLAW-07, OPENCLAW-08, OPENCLAW-09, OPENCLAW-10, OPENCLAW-11, OPENCLAW-12, OPENCLAW-13, OPENCLAW-14, OPENCLAW-15, OPENCLAW-16, OPENCLAW-17, OPENCLAW-18, OPENCLAW-19, OPENCLAW-20
**Success Criteria** (what must be TRUE):
  1. An agent can poll Plane and see tasks assigned to it via `plane.list_my_tasks` (filtered by `agent_id` custom field)
  2. An agent can transition a task through `todo` -> `in_progress` -> `done` with automatic comments and time tracking logged in Plane
  3. Concierge can create a project with tasks and assign them to specific agents, who detect the work within 5 minutes
  4. Agents respect rate limits (max 1 req/s), handle errors with retry/backoff, and mark tasks `blocked` on permanent failure
  5. `plane-bridge` skill appears in `openclaw list-skills` and all 8 MCP tools are functional
**Plans**: TBD

Plans:
- [ ] 03-01: plane-bridge SKILL.md template, MCP tools (list, get, update, comment, timer, upload, create)
- [ ] 03-02: Polling mechanism, custom fields usage, dependencies, error handling, rate limiting
- [ ] 03-03: Concierge orchestration flow, task completion criteria, end-to-end validation

### Phase 4: Notifications & Orchestration
**Goal**: Plane events flow to Telegram in real-time, and the human can query project status via Telegram commands
**Depends on**: Phase 1 (Plane webhooks), Phase 3 (agents generating events)
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04, NOTIF-05, NOTIF-06, NOTIF-07, NOTIF-08
**Success Criteria** (what must be TRUE):
  1. When an agent completes a task in Plane, a formatted Telegram notification arrives within 30 seconds with project name, task title, and time spent
  2. User can type `/plane status` in Telegram and receive a summary of active projects and in-progress tasks
  3. Webhook endpoint `/webhooks/plane` is accessible without VPN and authenticates via `X-Plane-Signature` header
  4. Minor agent comment updates do NOT trigger Telegram notifications (intelligent filtering active)
**Plans**: TBD

Plans:
- [ ] 04-01: Plane webhooks, Caddy public exception, n8n workflow, Telegram message formatting
- [ ] 04-02: Telegram commands (`/plane status`, `/plane project`, `/plane agent`), notification filtering, agent real-time updates

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Plane Deployment | 0/3 | Not started | - |
| 2. OpenClaw Upgrade | 0/2 | Not started | - |
| 3. Agent Integration | 0/3 | Not started | - |
| 4. Notifications & Orchestration | 0/2 | Not started | - |
