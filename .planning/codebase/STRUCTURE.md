# Codebase Structure

**Analysis Date:** 2026-02-28

## Directory Layout

```
/home/mobuone/VPAI/
├── .github/
│   └── workflows/              # CI/CD pipelines
│       ├── ci.yml              # Lint + Molecule tests on PR
│       ├── deploy-preprod.yml  # Auto-deploy to Hetzner ephemeral
│       └── deploy-prod.yml     # Manual prod deployment
│
├── .planning/
│   └── codebase/               # GSD codebase analysis docs (this directory)
│
├── inventory/
│   ├── hosts.yml               # Multi-target inventory (prod, preprod, vpn, workstation, app_prod)
│   └── group_vars/
│       ├── all/
│       │   ├── main.yml        # Wizard-generated variables (portable configuration)
│       │   ├── secrets.yml     # Ansible Vault encrypted (passwords, API keys)
│       │   ├── versions.yml    # Pinned Docker image tags
│       │   ├── docker.yml      # Docker daemon config (networks, limits, log rotation)
│       │   ├── ssh.yml         # SSH config variables
│       │   └── users.yml       # System user definitions
│       ├── prod/
│       │   └── main.yml        # Production environment overrides
│       └── preprod/
│           └── main.yml        # Pre-production environment overrides
│
├── playbooks/
│   ├── site.yml                # Main deployment playbook (all 6 phases + hardening)
│   ├── workstation.yml         # RPi5 local development tools deployment
│   ├── backup-restore.yml      # DR restore from Zerobyte backups
│   ├── rollback.yml            # Emergency image version rollback
│   ├── seed-preprod.yml        # Clone prod data to ephemeral preprod
│   ├── vpn-toggle.yml          # Toggle VPN-only mode (Caddy ACLs)
│   ├── vpn-dns.yml             # Update Headscale split DNS records
│   ├── safety-check.yml        # Pre-deployment validation
│   ├── provision-hetzner.yml   # Auto-provision Hetzner Cloud CX22 via hcloud API
│   └── obsidian.yml            # Deploy Obsidian Vault collector
│
├── roles/                       # 40+ Ansible roles (Phase 1-6 + utilities)
│   ├── common/                  # OS setup, users, locale, timezone, repos
│   ├── docker/                  # Docker CE installation, daemon config
│   ├── headscale-node/          # Tailscale VPN client setup
│   ├── postgresql/              # PostgreSQL container config, init scripts
│   ├── redis/                   # Redis container config
│   ├── qdrant/                  # Vector database container config
│   ├── caddy/                   # Reverse proxy, TLS, VPN ACLs, webhooks
│   ├── docker-stack/            # Centralized docker-compose orchestration
│   ├── n8n/                     # Workflow engine config and provisioning
│   ├── n8n-provision/           # Post-deploy workflow imports
│   ├── n8n-mcp/                 # n8n MCP documentation server (Workstation Pi)
│   ├── litellm/                 # LLM proxy with budget tracking
│   ├── openclaw/                # AI agent framework with sandbox
│   ├── nocodb/                  # No-code database (replaced Kaneo)
│   ├── palais/                  # Task/project management (replaced Kaneo)
│   ├── sure/                    # Compliance/security audit tool
│   ├── kaneo/                   # Deprecated (replaced by nocodb + palais)
│   ├── monitoring/              # Observability stack (Grafana, VictoriaMetrics, Loki, Alloy, cAdvisor)
│   ├── diun/                    # Docker image update notifier
│   ├── obsidian-collector/      # Obsidian Vault sync (prod)
│   ├── obsidian-collector-pi/   # Obsidian Vault sync (Workstation Pi)
│   ├── obsidian/                # CouchDB backend for Obsidian
│   ├── backup-config/           # Zerobyte backup agent setup
│   ├── uptime-config/           # Uptime monitoring alerting
│   ├── smoke-tests/             # Post-deployment health validation
│   ├── hardening/               # UFW, Fail2ban, CrowdSec (Phase 6 only)
│   ├── workstation-common/      # RPi5 system setup
│   ├── workstation-caddy/       # Local reverse proxy (port 3000)
│   ├── workstation-monitoring/  # Local Prometheus + Grafana
│   ├── opencode/                # OpenCode editor on RPi
│   ├── claude-code/             # Claude Code CLI on RPi
│   ├── codex-cli/               # Codex CLI on RPi
│   ├── gemini-cli/              # Gemini CLI on RPi
│   ├── comfyui/                 # ComfyUI stable diffusion on RPi
│   ├── remotion/                # Remotion video rendering on RPi
│   ├── opencut/                 # Video editing suite on RPi
│   ├── webhook-relay/           # Webhook relay from Seko-VPN
│   └── vpn-dns/                 # Headscale split DNS configuration
│
├── templates/
│   └── docker-compose.yml.j2    # Shared docker-compose template (deprecated—use role templates)
│
├── scripts/
│   ├── wizard.sh                # Interactive config wizard (generates main.yml)
│   ├── init-vault.sh            # Ansible Vault initialization
│   ├── smoke-test.sh            # Manual smoke test runner
│   ├── README-PLANE-DOCS.md     # Plane project import guide
│   ├── index-plane-docs.py      # Python script to index Plane docs
│   └── .env.example             # Environment template for scripts
│
├── docs/
│   ├── GOLDEN-PROMPT.md         # 6-phase dev plan, checklists, REX
│   ├── TROUBLESHOOTING.md       # 44+ known issues, per-service REX
│   ├── GUIDE-CADDY-VPN-ONLY.md  # 4 critical Caddy VPN setup pitfalls
│   ├── GUIDE-NOCODB-TOKEN-AUTOMATION.md  # NocoDB token renewal automation
│   ├── GUIDE-OPENCLAW-UPGRADE.md         # OpenClaw version upgrade checklist
│   ├── RUNBOOK.md               # Operational procedures (deploy, rollback, restore)
│   ├── REX-FIRST-DEPLOY-2026-02-15.md    # First deployment lessons
│   ├── REX-SESSION-2026-02-18.md         # Split DNS, Budget, VPN-only mode
│   ├── REX-SESSION-2026-02-23.md         # Creative stack, OpenCut, error pages
│   ├── REX-SESSION-2026-02-23b.md        # OpenClaw v2026.2.22 breaking changes
│   └── plans/                   # GSD implementation phase plans (generated)
│
├── CLAUDE.md                    # Project-specific Claude Code instructions
├── PRD.md                       # Product Requirements (config wizard, constraints) — in .gitignore
├── PRD.md.example               # PRD template (committed to git)
├── TECHNICAL-SPEC.md            # Architecture spec, networks, container limits, health checks
├── COMMANDES_DEPLOIEMENT.md     # Quick reference for deployment commands
├── README.md                    # Project overview
├── ansible.cfg                  # Ansible configuration (roles path, vault, SSH, fact caching)
├── requirements.yml             # Ansible Galaxy collections (community.docker, community.general, ansible.posix)
├── .yamllint.yml               # YAML linting rules
├── .ansible-lint               # Ansible linting rules
├── Makefile                    # Deployment targets (make deploy-prod, make lint)
├── bootstrap.sh                # Initial server bootstrap script
├── encrypt_vault.sh            # Ansible Vault encryption helper
└── .continue-here.md           # Session notes (current work in progress)
```

## Directory Purposes

**inventory/**
- Purpose: Ansible multi-environment configuration
- Contains: Host definitions, group variables, secrets (Vault)
- Key files:
  - `hosts.yml`: Maps prod/preprod/vpn/workstation/app_prod to IPs and SSH credentials
  - `group_vars/all/main.yml`: Wizard-generated variables (domain_name, prod_ip, etc.)
  - `group_vars/all/secrets.yml`: Encrypted Vault with passwords, API keys, tokens
  - `group_vars/all/versions.yml`: Docker image version pins (e.g., `postgresql_image: "postgres:18.1-alpine"`)

**playbooks/**
- Purpose: Ansible playbook entry points for different deployment scenarios
- Contains: Playbooks with role orchestration, pre/post-tasks, tags
- Execution: `ansible-playbook playbooks/site.yml` or via `make deploy-prod`
- Key patterns:
  - Pre-tasks: Validate Ansible version, anti-lockout SSH checks, display deployment info
  - Roles: Grouped by phase (phase1, phase2, phase3, phase4, phase5, phase6)
  - Tags: Each role has corresponding tag for targeted re-runs
  - Post-tasks: Smoke tests, observability setup, VPN DNS updates

**roles/**
- Purpose: Reusable Ansible role for each service/component
- Contains: For each role: `tasks/main.yml` (execution logic), `defaults/main.yml` (variable defaults), `handlers/main.yml` (service restart logic), `templates/` (Jinja2 configs), `vars/main.yml` (fixed variables), `meta/main.yml` (metadata)
- Pattern: Standard Ansible role structure; most roles deploy service configs to `/opt/{{ project_name }}/configs/`

**templates/**
- Purpose: Shared Jinja2 templates (mostly deprecated — prefer role-specific templates)
- Note: Historical; most service configs live in `roles/SERVICE/templates/`

**scripts/**
- Purpose: Utility scripts for setup and testing
- Contains:
  - `wizard.sh`: Interactive CLI for generating `main.yml` from PRD
  - `init-vault.sh`: One-time Ansible Vault initialization
  - `smoke-test.sh`: Manual validation of all endpoints
  - `index-plane-docs.py`: Python utility for indexing Plane project documentation

**docs/**
- Purpose: Operational and architectural documentation
- Contains:
  - `GOLDEN-PROMPT.md`: Master implementation plan (6 phases, checklists, blockers)
  - `TROUBLESHOOTING.md`: Known issues per service with REX (Return of Experience)
  - `GUIDE-*`: Service-specific setup guides (Caddy VPN, OpenClaw upgrades, etc.)
  - `REX-*.md`: Session-by-session retrospectives with bugs fixed, lessons learned
  - `RUNBOOK.md`: Step-by-step operational procedures (backup, restore, rollback)

## Key File Locations

**Entry Points:**
- `playbooks/site.yml`: Production (Sese-AI) full-stack deployment with all phases
- `playbooks/workstation.yml`: Workstation Pi (RPi5) local dev tools
- `playbooks/backup-restore.yml`: Disaster recovery restore from Zerobyte
- `Makefile`: Human-friendly targets (`make deploy-prod`, `make lint`, `make deploy-role ROLE=caddy`)

**Configuration:**
- `inventory/group_vars/all/main.yml`: Wizard-generated portable config (source of truth)
- `inventory/group_vars/all/secrets.yml`: Vault-encrypted secrets (passwords, API keys, tokens)
- `inventory/group_vars/all/versions.yml`: Pinned Docker image tags (no `:latest`)
- `inventory/group_vars/all/docker.yml`: Docker daemon settings (networks, limits, logging)
- `ansible.cfg`: Ansible runtime config (fact caching, vault identity, SSH timeouts)

**Core Logic:**
- `roles/docker-stack/tasks/main.yml`: Phase A (infra) and Phase B (apps) orchestration with health checks
- `roles/docker-stack/templates/docker-compose-infra.yml.j2`: Data layer (PostgreSQL, Redis, Qdrant, Caddy)
- `roles/docker-stack/templates/docker-compose.yml.j2`: Application layer (n8n, LiteLLM, OpenClaw, monitoring)
- `roles/caddy/templates/Caddyfile.j2`: Reverse proxy rules, TLS, VPN-only ACLs
- `roles/postgresql/templates/provision-postgresql.sh.j2`: Idempotent database/user creation

**Testing:**
- `roles/*/molecule/default/molecule.yml`: Molecule test config (per-role unit tests)
- `roles/*/molecule/default/converge.yml`: Test playbook (runs the role)
- `roles/*/molecule/default/verify.yml`: Test assertions (idempotency, file existence)
- `roles/smoke-tests/tasks/main.yml`: End-to-end health checks (all endpoints HTTP 200)

## Naming Conventions

**Files:**
- `main.yml` in tasks/, handlers/, defaults/, vars/: Standard Ansible role structure
- `*.j2`: Jinja2 templates (config files, scripts, docker-compose)
- `README.md`: Service overview in each role directory
- `.yml`: YAML files (playbooks, inventory, config)
- `*.sh`: Bash scripts (wizard, provisioning, operational)

**Directories:**
- `roles/{{ service_name }}/`: Lowercase with hyphens (e.g., `roles/docker-stack/`, `roles/n8n-provision/`)
- `playbooks/{{ scenario_name }}.yml`: Lowercase with hyphens (e.g., `playbooks/backup-restore.yml`)
- `{{ project_name }}_{{ component }}/`: Container names (e.g., `javisi_postgresql`, `javisi_caddy`)
- `/opt/{{ project_name }}/`: Service home directory on host (e.g., `/opt/javisi/`)

**Variables:**
- `{{ service_name_setting }}`: Lowercase with underscores (e.g., `postgresql_password`, `caddy_vpn_enforce`)
- `{{ service_name_SETTING }}`: Environment variables uppercase (e.g., `POSTGRES_PASSWORD`, `N8N_DB_POSTGRESDB_HOST`)
- `vault_{{ secret_name }}`: Vault-sourced secrets (e.g., `vault_prod_ip`, `vault_postgresql_password`)

## Where to Add New Code

**New Service/Application:**
1. Primary code: Create `roles/{{ new_service }}/` following standard structure
   - `tasks/main.yml`: Create config directories, generate .env file, notify handlers
   - `defaults/main.yml`: Service-specific vars (image, ports, memory limits)
   - `handlers/main.yml`: `Restart {{ new_service }}` handler (often redundant if using docker-stack)
   - `templates/{{ new_service }}.env.j2`: Environment variables
   - `templates/config.yml.j2`: Service-specific config if needed
   - `meta/main.yml`: Dependencies (usually empty; phases declared in playbooks)
   - `molecule/default/`: Unit tests (converge.yml runs the role, verify.yml checks outcomes)

2. Integration: Add role to `playbooks/site.yml` under appropriate phase tag
   ```yaml
   - role: new_service
     tags: [new_service, phase3]  # Choose phase based on layer
   ```

3. Docker composition: Add service block to `roles/docker-stack/templates/docker-compose.yml.j2` or `docker-compose-infra.yml.j2`
   - Include networks (frontend, backend, monitoring, egress, sandbox)
   - Define environment variables (source from {{ new_service_var }})
   - Set healthcheck if applicable
   - Define deploy limits (memory, CPU)
   - Define volumes (read-only configs, read-write data)

4. Documentation: Create `roles/{{ new_service }}/README.md` documenting purpose, config, dependencies

**New Infrastructure Feature:**
1. Primary code: Create `roles/{{ feature_name }}/` or modify existing role
   - Example: VPN-only mode is split across `roles/caddy/`, `roles/docker-stack/` (env vars), and playbooks

2. Variables: Add to `inventory/group_vars/all/main.yml` with sensible defaults
   - Prefix with feature name (e.g., `caddy_vpn_enforce`, `caddy_webhook_relay`)

3. Documentation: Update `docs/GOLDEN-PROMPT.md` section describing feature and any blockers

**New Utility Role (e.g., workstation CLI tool):**
1. Primary code: Create `roles/{{ cli_name }}/` with simplified structure
   - `tasks/main.yml`: Download/install via package manager or source
   - `defaults/main.yml`: Version, download URL, config path
   - `templates/config.toml.j2`: Config file if needed
   - No handlers/meta/molecule unless complex

2. Integration: Add to `playbooks/workstation.yml` or `playbooks/site.yml` depending on target

**New Operational Procedure:**
1. Primary code: Create `playbooks/{{ procedure_name }}.yml`
   - Structure: `hosts:`, `pre_tasks:`, `roles:`, `post_tasks:`
   - Example: `playbooks/vpn-toggle.yml` modifies Caddy ACL state without full redeploy

2. Documentation: Add step-by-step guide to `docs/RUNBOOK.md`

## Special Directories

**`/opt/{{ project_name }}/` (Host runtime)**
- Purpose: Service home directory on deployed host (e.g., `/opt/javisi/`)
- Generated: Yes (created by `roles/docker-stack/tasks/main.yml`)
- Committed: No (runtime data)
- Contains:
  - `docker-compose-infra.yml`: Phase A services (tracked in `/opt/`, not git)
  - `docker-compose.yml`: Phase B services (tracked in `/opt/`, not git)
  - `configs/`: Service-specific configs (Caddyfile, postgresql.conf, n8n.env, etc.)
  - `data/`: Persistent volumes (PostgreSQL, Redis, Qdrant, Caddy TLS certs)
  - `logs/`: Service logs (Caddy HTTP access logs, backup logs)
  - `scripts/`: Operational scripts (provision-postgresql.sh, etc.)
  - `Makefile`: Runtime command menu for operators

**`/tmp/ansible_facts_cache/` (Fact cache)**
- Purpose: Ansible fact caching for performance (configured in `ansible.cfg`)
- Generated: Yes (by Ansible during fact gathering)
- Committed: No (ephemeral)
- TTL: 3600 seconds (cache_valid_time in `ansible.cfg`)

**`.planning/codebase/` (GSD codebase analysis)**
- Purpose: Output directory for GSD `/gsd:map-codebase` analysis
- Generated: Yes (by GSD codebase mapper)
- Committed: Yes (consumed by `/gsd:plan-phase` and `/gsd:execute-phase`)
- Contains: ARCHITECTURE.md, STRUCTURE.md, STACK.md, INTEGRATIONS.md, CONVENTIONS.md, TESTING.md, CONCERNS.md

**`.venv/` (Python virtual environment)**
- Purpose: Isolated Python environment for Ansible, Molecule, scripts
- Generated: Yes (by `python3 -m venv .venv` during bootstrap)
- Committed: No (.gitignore)
- Activation: `source .venv/bin/activate`

**`.github/workflows/` (CI/CD pipelines)**
- Purpose: GitHub Actions automation (lint, Molecule tests, deploy)
- Generated: No (committed)
- Files:
  - `ci.yml`: Runs on PR (yamllint, ansible-lint, molecule)
  - `deploy-preprod.yml`: Auto-deploys to Hetzner ephemeral on main branch
  - `deploy-prod.yml`: Manual prod deployment (requires approval)

---

*Structure analysis: 2026-02-28*
