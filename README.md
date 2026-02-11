# VPAI — Self-Hosted AI Infrastructure

**Deploy a complete AI and automation stack on a single VPS in minutes.**

VPAI is a production-ready Ansible project that provisions and configures 12+ Docker services behind a secure reverse proxy, with full observability, automated backups, and CI/CD pipelines.

---

## What It Deploys

```
Internet ──▶ Caddy (TLS auto) ──▶ Backend Network (isolated)
                                      ├── n8n          — Workflow automation
                                      ├── OpenClaw     — AI agent platform
                                      ├── LiteLLM      — Multi-LLM proxy (OpenAI, Anthropic)
                                      ├── PostgreSQL    — Relational database
                                      ├── Redis         — Cache & message broker
                                      └── Qdrant        — Vector search engine

                                   Monitoring Network (isolated)
                                      ├── VictoriaMetrics — Time-series metrics
                                      ├── Loki            — Log aggregation
                                      ├── Alloy           — Metrics & logs collector
                                      └── Grafana         — Dashboards & alerting

                                   System
                                      ├── DIUN         — Docker image update notifier
                                      ├── CrowdSec     — Intrusion prevention
                                      └── Fail2ban     — Brute-force protection
```

## Key Features

| Category | Details |
|----------|---------|
| **Infrastructure as Code** | 16 Ansible roles, fully idempotent, Molecule-tested |
| **Security** | VPN-only admin access, TLS auto, CrowdSec, Fail2ban, UFW hardening |
| **Observability** | 5 Grafana dashboards, alerting rules, centralized logs |
| **Resilience** | Automated pre-backup scripts, S3-compatible storage, disaster recovery playbooks |
| **CI/CD** | GitHub Actions: lint, test, deploy to pre-prod (Hetzner), deploy to prod |
| **Portability** | Template wizard — every value is a Jinja2 variable, zero hardcoded names |

## Quick Start

### Prerequisites

- Python 3.10+ with `pip`
- Ansible 2.16+
- SSH access to a Debian 12+ VPS
- A domain name with DNS configured
- Headscale/Tailscale VPN for secure admin access

### Setup

```bash
# Clone the repository
git clone https://github.com/Mobutoo/VPAI.git
cd VPAI

# Install dependencies
chmod +x bootstrap.sh && ./bootstrap.sh

# Configure your deployment
cp PRD.md.example PRD.md
# Edit PRD.md — fill in your domain, IPs, project name, etc.

# Create and fill the Ansible Vault with your secrets
make vault-init

# Deploy
make deploy-preprod                           # Pre-production first
make smoke-test URL=https://your-domain.com   # Validate
make deploy-prod                              # Production
```

## Project Structure

```
.
├── inventory/              # Hosts, variables, versions, secrets (Vault)
├── roles/                  # 16 Ansible roles (common → smoke-tests)
├── templates/              # Docker Compose Jinja2 template
├── playbooks/              # site.yml + rollback, restore, rotate-secrets
├── scripts/                # Smoke test runner
├── docs/                   # Runbook, architecture, disaster recovery
├── .github/workflows/      # CI (lint + Molecule) + CD (preprod + prod)
├── Makefile                # Developer shortcuts
└── TECHNICAL-SPEC.md       # Full technical specification
```

## Available Commands

```bash
make help                # Show all available commands
make lint                # Run yamllint + ansible-lint (profile: production)
make test                # Molecule tests for all 16 roles
make test-role ROLE=n8n  # Test a specific role
make check               # Dry-run (--check --diff)
make deploy-preprod      # Deploy to pre-production
make deploy-prod         # Deploy to production (with confirmation prompt)
make smoke-test URL=...  # Run smoke tests against a live deployment
make vault-edit          # Edit encrypted secrets
make rollback            # Emergency rollback to previous version
make backup-restore      # Restore from S3 backup
```

## Network Architecture

VPAI uses four isolated Docker networks for defense in depth:

| Network | Type | Purpose |
|---------|------|---------|
| `frontend` | External | Caddy ↔ Grafana (public-facing) |
| `backend` | Internal | App ↔ DB communication (no internet) |
| `monitoring` | Internal | Metrics & logs pipeline |
| `egress` | External | Outbound API calls (OpenAI, Anthropic, webhooks) |

## Documentation

| Document | Description |
|----------|-------------|
| `PRD.md.example` | Configuration template — copy and fill with your values |
| `TECHNICAL-SPEC.md` | Architecture, configs, networks, resource limits |
| `docs/RUNBOOK.md` | Day-to-day operations, troubleshooting, procedures |
| `docs/ARCHITECTURE.md` | Mermaid diagrams: networks, data flow, startup order |
| `docs/DISASTER-RECOVERY.md` | Recovery scenarios: crash, VPS loss, DB corruption, breach |

## Technology Stack

| Layer | Technologies |
|-------|-------------|
| Orchestration | Ansible 2.16+, Docker Compose V2 |
| Reverse Proxy | Caddy (auto TLS, rate limiting, VPN ACL) |
| Applications | n8n, OpenClaw, LiteLLM |
| Databases | PostgreSQL 18.1, Redis 8.0, Qdrant 1.16 |
| Observability | Grafana, VictoriaMetrics, Loki, Alloy |
| Security | CrowdSec, Fail2ban, UFW, Headscale/Tailscale VPN |
| CI/CD | GitHub Actions, Hetzner Cloud (pre-prod) |

## Development

This project was developed with [Claude Code](https://claude.ai/claude-code) following a 6-phase plan with automated quality gates.

**Quality standards:**
- `ansible-lint` profile `production` — 0 failures, 0 warnings
- `yamllint` strict mode with octal-values enforcement
- All 16 roles have Molecule tests (converge + verify)
- All Docker images version-pinned (no `:latest`)
- All secrets encrypted with Ansible Vault

## License

MIT

---

*Built with Ansible, Docker, and a lot of YAML.*
