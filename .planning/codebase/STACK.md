# Technology Stack

**Analysis Date:** 2026-02-28

## Languages

**Primary:**
- Python 3.12 - Ansible implementation and scripting

**Secondary:**
- Bash - Shell scripts, deployment utilities
- Jinja2 - Template rendering for all configurations
- YAML - Ansible playbooks, roles, variable definitions

## Runtime

**Environment:**
- Ansible 2.16+ (automation orchestration)
- Docker CE (containerization)
- Docker Compose V2 (multi-container orchestration)

**Package Manager:**
- pip3 - Python package management
- npm - CLI tools (OpenCode, Claude Code, Codex CLI, Gemini CLI)
- docker - Container image distribution

**Lockfile:**
- requirements.yml - Ansible collection versions (community.general, community.docker, community.crypto, ansible.posix, community.postgresql, hetzner.hcloud)
- Pinned Docker images - No `:latest` tags; all images locked in `inventory/group_vars/all/versions.yml`
- Pinned npm versions - OpenCode 1.2.15, Claude Code 2.1.62, Codex CLI 0.106.0, Gemini CLI 0.30.0

## Frameworks

**Core:**
- Ansible 2.16+ - Infrastructure-as-Code orchestration across 4 server types (Sese-AI, Seko-VPN, Waza Pi, Prod Apps)
- Docker Compose - Multi-service orchestration (2-file architecture: docker-compose-infra.yml + docker-compose.yml)

**Testing:**
- Molecule - Container-based role testing (test scenarios in `roles/*/molecule/`)
- yamllint - YAML syntax validation
- ansible-lint - Ansible best practices and security validation

**Build/Dev:**
- Makefile - 30+ targets for setup, deploy, testing, operations
- GitHub Actions - CI/CD pipeline (lint → molecule → deploy preprod → smoke tests)
- xcaddy - Custom Caddy binary build with OVH DNS-01 plugin (workstation)

## Key Dependencies

**Critical:**
- Caddy 2.10.2-alpine - Reverse proxy with automatic HTTPS, VPN ACL enforcement
- PostgreSQL 18.1-bookworm - Relational database (shared across n8n, LiteLLM, NocoDB, Sure)
- Redis 8.0-bookworm - In-memory cache for session and semantic cache layer
- Qdrant v1.16.3 - Vector database (semantic cache, RAG indexing)

**Applications:**
- n8n 2.7.3 - Workflow automation, webhooks, n8n-MCP documentation server
- OpenClaw 2026.2.23 - AI agent framework with sandbox isolation
- LiteLLM v1.81.3-stable - LLM routing proxy (multi-provider, budget management)
- NocoDB 0.301.2 - Low-code database UI (manga production pipeline)
- CouchDB 3.3.3 - Obsidian LiveSync backend (Seko-VPN only)

**Observability:**
- Grafana 12.3.2 - Metrics dashboard (VPN-only access)
- VictoriaMetrics v1.135.0 - Time-series database
- Loki 3.6.5 - Log aggregation
- Grafana Alloy v1.13.0 - Agent for metrics/logs collection
- cAdvisor 0.55.1 - Container metrics collection

**System:**
- DIUN 4.31.0 - Docker image update notifications
- CrowdSec - Threat detection (hardening role)
- Fail2ban - Intrusion prevention
- UFW - Host firewall management

**Backup & VPN:**
- Zerobyte v0.16 - S3 backup orchestration (Hetzner Object Storage fsn1)
- Headscale/Tailscale - Mesh VPN (100.64.0.0/10 network)

**Workstation CLI Tools (RPi native, not containerized):**
- Claude Code 2.1.62 - AI-assisted coding (installed via npm)
- OpenCode 1.2.15 - Code search and navigation
- Codex CLI 0.106.0 - OpenAI Codex integration
- Gemini CLI 0.30.0 - Google Gemini integration

## Configuration

**Environment:**
- Configuration wizard: `scripts/wizard.sh` generates `inventory/group_vars/all/main.yml`
- 70+ variables for multi-environment deployment (prod/preprod/workstation)
- Environment file approach: `env_file` directive for n8n, litellm, openclaw, nocodb, palais

**Key Configs Required:**
- OVH API credentials (DNS-01 ACME) - `inventory/group_vars/all/secrets.yml` (Ansible Vault)
- AI provider API keys (Anthropic, OpenAI, OpenRouter, Google Gemini, BytePlus, Brave Search) - vault
- Hetzner S3 credentials (backup and NocoDB file storage) - vault
- Telegram bot tokens (monitoring alerts) - vault
- PostgreSQL shared password (all DB users) - vault
- Redis password - vault
- Qdrant API key - vault
- All secrets in `inventory/group_vars/all/secrets.yml` encrypted with Ansible Vault

**Build:**
- ansible.cfg - Forks=10, pipelining enabled, fact caching
- .yamllint.yml - YAML linting rules
- .ansible-lint - Ansible best practices rules
- molecule/ - Per-role test configuration

## Platform Requirements

**Development:**
- Python 3.12 venv (isolated virtual environment)
- Ansible 2.16+ with collections installed
- Docker and Docker Compose V2 (for local testing)
- Git with SSH key pair (`~/.ssh/seko-vpn-deploy`)
- SSH access to: Sese-AI (prod VPS 137.74.114.167:804), Seko-VPN (87.106.30.160:22)

**Production:**
- **Sese-AI (OVH VPS, prod):** Debian 13, 8GB RAM, 4 CPUs, 75GB disk, custom SSH port 804
- **Seko-VPN (Ionos, hub):** Existing Headscale server, public IP + Tailscale mesh
- **Waza (Workstation Pi):** RPi5 16GB, ARM64 native, Debian-based, docker + CLI tools
- **Prod Apps (Hetzner CX22):** Ubuntu 24.04, auto-provisioned via hcloud API

**Deployment Target:**
- Docker Compose on CentOS/Debian/Ubuntu hosts
- Headscale mesh for VPN (zero public port exposure after hardening)
- OVH domain with DNS API access (DNS-01 ACME validation)
- Hetzner Object Storage (S3-compatible) for backup and file storage

---

*Stack analysis: 2026-02-28*
