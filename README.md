# 🤖 Self-Hosted AI Infrastructure Stack

> Ansible-based deployment of a complete AI/automation stack on a single VPS with Docker.

## Features

- **12 services** orchestrated with Docker Compose via Ansible
- **Secure by default** : SSH VPN-only, admin UIs VPN-only, TLS auto, CrowdSec
- **Observable** : Grafana + VictoriaMetrics + Loki + Alloy
- **Resilient** : Automated backups via Zerobyte → S3, external monitoring via Uptime Kuma
- **Portable** : Template wizard — redeploy under any name/server in minutes
- **CI/CD** : GitHub Actions pipeline with pre-production on Hetzner Cloud

## Quick Start

```bash
# 1. Clone
git clone <your-repo-url>
cd <project-directory>

# 2. Bootstrap
chmod +x bootstrap.sh
./bootstrap.sh

# 3. Configure
# Edit PRD.md section 2 — fill all <À_REMPLIR> values
# Then create vault:
make vault-init

# 4. Deploy
make deploy-preprod   # Pre-production first
make smoke-test URL=https://preprod.your-domain.com
make deploy-prod      # Production when ready
```

## Architecture

```
Internet → [Caddy :443] → Backend Network (internal)
                              ├── n8n (automation)
                              ├── OpenClaw (AI agents)
                              ├── LiteLLM (LLM proxy)
                              ├── PostgreSQL (data)
                              ├── Redis (cache)
                              └── Qdrant (vectors)
                           Monitoring Network (internal)
                              ├── VictoriaMetrics (metrics)
                              ├── Loki (logs)
                              ├── Alloy (collector)
                              └── Grafana (dashboards)
```

## Documentation

| Document | Description |
|----------|-------------|
| [PRD.md](PRD.md) | Product requirements, wizard, objectives |
| [TECHNICAL-SPEC.md](TECHNICAL-SPEC.md) | Architecture, configs, network, security |
| [GOLDEN-PROMPT.md](GOLDEN-PROMPT.md) | Development plan for Claude Code |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operational procedures |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture diagrams |
| [docs/DISASTER-RECOVERY.md](docs/DISASTER-RECOVERY.md) | Disaster recovery plan |

## Commands

```bash
make help              # Show all commands
make lint              # yamllint + ansible-lint
make test              # Molecule tests (all roles)
make test-role ROLE=n8n  # Test specific role
make check             # Dry-run
make deploy-preprod    # Deploy to pre-production
make deploy-prod       # Deploy to production (with confirmation)
make smoke-test URL=<url>  # Run smoke tests
make vault-edit        # Edit secrets
make rollback          # Emergency rollback
make backup-restore    # Restore from S3 backup
```

## Requirements

- Python 3.10+
- Ansible 2.16+
- Docker CE 24+
- SSH access to target VPS
- Headscale/Tailscale VPN configured

## License

Private — Internal use only.
