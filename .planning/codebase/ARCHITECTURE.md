# Architecture

**Analysis Date:** 2026-02-28

## Pattern Overview

**Overall:** Orchestrated Infrastructure-as-Code using Ansible with multi-phase, layered Docker composition.

**Key Characteristics:**
- **Multi-target deployment**: Single playbooks deploy to prod (Debian 13 VPS), preprod (ephemeral), workstation (ARM64 RPi5), and VPN hub
- **Phase-based execution**: 6 phases + 1 hardening phase ordered as dependencies (foundations → data → apps → observability → resilience → hardening)
- **Two-stage Docker composition**: Phase A (infra: PostgreSQL, Redis, Qdrant, Caddy) launches independently, then Phase B (applications) connects to Phase A services
- **Jinja2 templating**: All hardcoded values replaced with variables from wizard (`PRD.md`), enabling portable deployments across multiple servers
- **Health-driven provisioning**: Ansible validates individual container health before proceeding, with per-service diagnostic logging
- **Role-based RBAC**: Each role corresponds to a service/function with isolated tasks, handlers, defaults, and templates

## Layers

**Foundation Layer (Phase 1):**
- Purpose: System preparation and Docker engine installation
- Location: `roles/common/`, `roles/docker/`, `roles/headscale-node/`
- Contains: OS hardening, package installation, user creation, Docker daemon config, VPN client setup
- Depends on: None (system-level)
- Used by: All subsequent layers

**Data Layer (Phase 2):**
- Purpose: Stateful data services and reverse proxy orchestration
- Location: `roles/postgresql/`, `roles/redis/`, `roles/qdrant/`, `roles/caddy/`
- Contains: Service-specific config files, TLS certificates, database initialization scripts, network ACL policies
- Depends on: Foundation layer (Docker running)
- Used by: Application layer for data persistence and public routing

**Application Layer (Phase 3):**
- Purpose: Core business logic and integration services
- Location: `roles/n8n/`, `roles/litellm/`, `roles/openclaw/`, `roles/nocodb/`, `roles/palais/`, `roles/sure/`
- Contains: Service-specific env vars, initialization config, feature toggles
- Depends on: Data layer (PG, Redis, Qdrant healthy)
- Used by: Integration Layer and end-users via Caddy

**Docker Composition Layer (Phase 4.5):**
- Purpose: Centralized service orchestration with inter-service networking
- Location: `roles/docker-stack/`
- Contains: Two Docker Compose files with isolated networks and health checks
- Depends on: All role configs (phases 1-3) deployed to disk
- Used by: Ansible docker_compose_v2 module to start services atomically

**Provisioning Layer (Phase 4.6):**
- Purpose: Post-deployment initialization (databases, collections, webhooks)
- Location: `roles/n8n-provision/`
- Contains: n8n workflow imports, database seeding scripts
- Depends on: Docker stack running and healthy
- Used by: Application layer for initial state

**Observability Layer (Phase 4):**
- Purpose: Monitoring, logging, alerting, and container image updates
- Location: `roles/monitoring/`, `roles/diun/`, `roles/obsidian-collector/`
- Contains: Grafana dashboards, Loki pipelines, VictoriaMetrics scrape configs, image update watchers
- Depends on: Data layer and Docker running
- Used by: Operators to observe system health

**Resilience Layer (Phase 5):**
- Purpose: Backup configuration, uptime monitoring, and smoke tests
- Location: `roles/backup-config/`, `roles/uptime-config/`, `roles/smoke-tests/`
- Contains: Backup scripts, monitoring alert rules, health check endpoints
- Depends on: Application layer deployed
- Used by: DR procedures and automated alerting

**Hardening Layer (Phase 6):**
- Purpose: Security reinforcement after validation
- Location: `roles/hardening/`
- Contains: UFW rules, Fail2ban setup, CrowdSec integration, SSH key enforcement
- Depends on: All previous phases validated
- Used by: Production deployments only

## Data Flow

**Deployment Initialization Flow:**

1. Ansible reads `inventory/hosts.yml` to identify target (prod, preprod, workstation, vpn)
2. Variables are loaded from `inventory/group_vars/all/main.yml` (wizard) and `secrets.yml` (Vault)
3. Pre-tasks run sshd and Ansible version validation
4. Phase 1 roles generate `/etc/docker/daemon.json` and configure system
5. Phase 2 roles generate service configs to `/opt/{{ project_name }}/configs/` (PostgreSQL, Redis, Qdrant, Caddy)
6. Phase 3 roles generate `.env` files to `/opt/{{ project_name }}/configs/`
7. Phase 4.5 (docker-stack role) renders `docker-compose-infra.yml.j2` and `docker-compose.yml.j2` to `/opt/{{ project_name }}/`
8. Docker Compose Phase A starts (PostgreSQL, Redis, Qdrant, Caddy on `backend` network)
9. Ansible polls each service's health individually with retries and diagnostic logging
10. PostgreSQL provisioning script creates databases and users (idempotent)
11. Qdrant provisioning script creates semantic_cache and content_index collections
12. Docker Compose Phase B starts applications (n8n, LiteLLM, OpenClaw, NocoDB, Palais, Sure)
13. Post-tasks run provisioning (n8n workflows), observability setup, and smoke tests
14. Final health summary displays all container statuses

**Service Communication Flow:**

```
Internet → Caddy (frontend) → Backend services (internal network 172.20.2.0/24)
         ↓
         PostgreSQL (stateful)
         Redis (cache)
         Qdrant (vector search)

Caddy → n8n → LiteLLM/OpenRouter APIs (egress network 172.20.4.0/24)
        → OpenClaw (sandbox isolation 172.20.5.0/24)
        → NocoDB (S3 storage)

Monitoring → VictoriaMetrics ← Alloy (scrapes backend + containers)
          → Grafana (frontend network for UI)
          → Loki (logs aggregation)
```

**State Management:**

- **Container state**: Managed by Docker Compose with `restart: unless-stopped`
- **Configuration state**: Templated to `/opt/{{ project_name }}/configs/` (version-controlled in templates)
- **Data state**: Persisted in volumes under `/opt/{{ project_name }}/data/` (PostgreSQL, Redis, Qdrant, Caddy TLS)
- **Idempotency**: Provisioning scripts check existence before creating (PostgreSQL users, Qdrant collections)
- **Secret state**: Stored in `ansible-vault` encrypted `secrets.yml` (never in templates)

## Key Abstractions

**Role:**
- Purpose: Encapsulate a single service or infrastructure concern
- Examples: `roles/n8n/`, `roles/caddy/`, `roles/postgresql/`
- Pattern: Standard Ansible role structure (tasks/, handlers/, defaults/, templates/, vars/, meta/, molecule/)
- Dependency: Declared via `dependencies` in meta/main.yml (currently unused — phases declared in playbooks)

**Docker Service:**
- Purpose: Represent a containerized workload (n8n, PostgreSQL, Grafana, etc.)
- Examples: Services defined in `docker-compose-infra.yml.j2` and `docker-compose.yml.j2`
- Pattern: YAML service block with image, env, volumes, networks, healthcheck, deploy limits
- Configuration: Sourced from role defaults + wizard variables + Vault secrets

**Network:**
- Purpose: Isolate traffic between service tiers
- Examples: `frontend` (172.20.1.0/24), `backend` (172.20.2.0/24), `monitoring` (172.20.3.0/24), `egress` (172.20.4.0/24), `sandbox` (172.20.5.0/24)
- Pattern: Named Docker bridge networks with explicit IP ranges and `internal: true` flag for isolated networks
- ACLs: Caddy rules enforce VPN-only access using Tailscale IP CIDR + Docker frontend gateway CIDR

**Config Template:**
- Purpose: Generate service-specific configs from inventory variables
- Examples: `roles/caddy/templates/Caddyfile.j2`, `roles/postgresql/templates/postgresql.conf.j2`, `roles/litellm/templates/config.yml.j2`
- Pattern: Jinja2 with `.j2` extension, sourced by roles/tasks, deployed to `/opt/{{ project_name }}/configs/`
- Override mechanism: Variables in `inventory/group_vars/all/main.yml` (wizard) override role defaults

**Provisioning Script:**
- Purpose: Perform post-deployment initialization (one-time setup, migrations, idempotent upserts)
- Examples: `roles/docker-stack/templates/provision-postgresql.sh.j2`, Qdrant collection provisioning
- Pattern: Bash script with `set -euo pipefail`, health checks, idempotency guards
- Execution: Called after docker-stack role to ensure containers are running

**Playbook:**
- Purpose: Define a deployment scenario (which hosts, which roles, in what order)
- Examples: `playbooks/site.yml` (prod deployment), `playbooks/workstation.yml` (RPi), `playbooks/backup-restore.yml` (DR)
- Pattern: YAML with hosts, pre_tasks, roles with tags and conditional vars, post_tasks
- Execution: `ansible-playbook playbooks/site.yml --tags "phase1,phase2"`

## Entry Points

**Production Deployment (Sese-AI VPS):**
- Location: `playbooks/site.yml`
- Triggers: `make deploy-prod` (Makefile wrapper around ansible-playbook)
- Responsibilities:
  - Deploy all 6 phases to prod inventory
  - Validate Ansible 2.16+, anti-lockout sshd checks
  - Run health checks for each service independently
  - Execute smoke tests
- SSH: Uses `seko-vpn-deploy` key, connects to prod VPS port 804

**Workstation Deployment (RPi5):**
- Location: `playbooks/workstation.yml`
- Triggers: `ansible-playbook playbooks/workstation.yml --tags "opencode,claude-code"`
- Responsibilities:
  - Deploy local development tools (OpenCode, Claude Code, Codex CLI, Gemini CLI, ComfyUI, Remotion, OpenCut)
  - Configure local reverse proxy (workstation-caddy on port 3000)
  - Join Tailscale mesh via Headscale
  - Deploy n8n-mcp server for documentation (port 3001)
  - Generate Windows Claude Code MCP config for Tailscale access
- SSH: Direct LAN access to RPi (192.168.1.8)

**Utility Playbooks:**
- `playbooks/backup-restore.yml`: Restore from Zerobyte backups to new server
- `playbooks/rollback.yml`: Emergency rollback to previous Docker image versions
- `playbooks/seed-preprod.yml`: Clone prod data to preprod (Hetzner ephemeral)
- `playbooks/vpn-toggle.yml`: Enable/disable VPN-only mode for Caddy rules
- `playbooks/vpn-dns.yml`: Update Headscale split DNS records (called from site.yml post_tasks)
- `playbooks/safety-check.yml`: Pre-deployment validation (repo state, Vault access, SSH connectivity)

## Error Handling

**Strategy:** Fail-fast with detailed diagnostics; non-blocking warnings for transient states.

**Patterns:**

- **Container health validation**: Ansible `until` loops with exponential backoff (retries: 20, delay: 5-10s)
  - Example: `roles/docker-stack/tasks/main.yml` lines 80-103 (PostgreSQL health check)
  - Failure: Logs last 30 lines of container stderr, then fails the play
  - Non-blocking: Caddy marked as "may recover when backends are up" (line 293-296)

- **Provisioning idempotency**: Bash scripts check existence before creating
  - Example: PostgreSQL provisioning (line 117-127) compares actual vs required databases
  - Changed: Only when new database created, `changed_when` guards notify handlers

- **Docker Compose recovery**: Phase B apps can start independently; provisioning retries on failure
  - Example: LiteLLM restart (line 373-380) if unhealthy after deployment
  - Failed_when: false — non-fatal; continues to next phase

- **Anti-lockout SSH**: Pre-task validates sshd config before changes (line 34-49)
  - Prevents SSH lockout during role execution
  - Expected failure on first deploy (sshd not yet installed)

- **Vault decryption**: Fails if `.vault_password` file missing or unreadable
  - Configures via `ansible.cfg` line 37
  - Referenced in CLAUDE.md as critical security check

## Cross-Cutting Concerns

**Logging:**
- **Docker**: `json-file` driver with max-size 10m, max-file 3 (daemon.json)
- **Ansible**: Facts cached in `/tmp/ansible_facts_cache/` with 3600s TTL
- **Services**: Application logs written to stdout (captured by Docker), scraped by Alloy → Loki

**Validation:**
- **Pre-deployment**: `ansible-playbook site.yml --check --diff` (Makefile target `make lint`)
- **Health checks**: Every Phase A/B service has `healthcheck` block in docker-compose
- **Smoke tests**: `roles/smoke-tests/tasks/main.yml` validates all public endpoints (HTTP 200)

**Authentication:**
- **SSH**: Key-based only; `~/.ssh/seko-vpn-deploy` for prod; direct LAN for workstation
- **Ansible**: Vault-encrypted secrets in `inventory/group_vars/all/secrets.yml`
- **Services**: Passwords/tokens sourced from Vault variables (postgresql_password, n8n_admin_password, qdrant_api_key)

**VPN Access Control (Caddy):**
- **VPN-only mode**: When `caddy_vpn_enforce: true`, admin UIs (Grafana, n8n, OpenClaw) restricted to Tailscale IPs
- **CIDR whitelists**: Caddy rules check `{{ vpn_network_cidr }}` (100.64.0.0/10 Tailscale range) + `{{ caddy_docker_frontend_cidr }}` (172.20.1.0/24 Docker gateway for HTTP/3 UDP)
- **Public mode**: `caddy_vpn_enforce: false` allows initial validation via public IP before hardening

**Configuration Management:**
- **Single source of truth**: `inventory/group_vars/all/main.yml` (wizard-generated)
- **Overrides**: `inventory/group_vars/prod/main.yml`, `inventory/group_vars/preprod/main.yml` override all-level vars
- **Secrets separation**: `secrets.yml` (Vault) contains passwords, API keys, credentials
- **Version pinning**: `inventory/group_vars/all/versions.yml` pins all Docker image tags (no `:latest`)

---

*Architecture analysis: 2026-02-28*
