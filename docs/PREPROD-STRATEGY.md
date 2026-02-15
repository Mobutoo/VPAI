# Pre-production Strategy — Cost, Operability & Data Seeding

> **Project**: VPAI — Self-Hosted AI Infrastructure Stack
> **Version**: 1.0.0
> **Last updated**: February 2026

---

## 1. Preprod Scenarios Compared

### Scenario A — Ephemeral Only (current CI/CD implementation)

VM created on each push, destroyed after tests.

| Item | Calculation | Cost/month |
|------|------------|------------|
| CX23 VM (ephemeral) | ~45 min/run x 16 runs/month = 12h x 0.0056 EUR/h | ~0.07 EUR |
| Snapshot (~5 GB) | 5 GB x 0.011 EUR/GB | ~0.06 EUR |
| **Total active phase** | 16 runs/month | **~0.13 EUR** |
| **Total cruise** | 4 runs/month | **~0.05 EUR** |

**Pros**: Near-zero cost, always clean environment, no maintenance.
**Cons**: 15-20 min per run, no persistent access, no TLS/domain, no data persistence test.

### Scenario B — Permanent VM (recommended for start)

CX23 runs permanently, CI deploys onto it.

| Item | Calculation | Cost/month |
|------|------------|------------|
| CX23 VM | 24/7 | **3.49 EUR** |
| Subdomain DNS | `preprod.domain.com` to primary IP | 0 EUR |
| **Total** | | **3.49 EUR** |

**Pros**: Fast deploys (~5 min), 24/7 access, TLS possible, realistic tests.
**Cons**: 42 EUR/year even when idle, possible drift.

### Scenario C — Hybrid (best of both)

Permanent VM for dev/demo + ephemeral for clean-install validation.

| Item | Calculation | Cost/month |
|------|------------|------------|
| CX23 permanent | Dev/demo, continuous deploy | 3.49 EUR |
| CX23 ephemeral (CI) | ~3-12h/month | ~0.05-0.07 EUR |
| Snapshot | ~5 GB | ~0.06 EUR |
| **Total** | | **~3.60 EUR** |

### Decision Matrix

| Criterion | Ephemeral (A) | Permanent (B) | Hybrid (C) |
|-----------|:-------------:|:-------------:|:----------:|
| Cost/month | 0.05-0.13 EUR | 3.49 EUR | 3.60 EUR |
| Cost/year | **~1-2 EUR** | ~42 EUR | ~43 EUR |
| Available 24/7 | No | **Yes** | **Yes** |
| TLS/domain | No | **Yes** | **Yes** |
| Clean install test | **Yes** | No | **Yes** |
| Upgrade test | No | **Yes** | **Yes** |
| CI deploy time | ~20 min | **~5 min** | **~5 min** |
| Complexity | Medium | **Simple** | Medium |

### Recommendation

**Start with Scenario B (permanent CX23 at 3.49 EUR/month).**

- 3.49 EUR/month is negligible for a full preprod environment
- Simple setup: one server, one IP, one DNS subdomain
- Fast feedback loop: Ansible only replays changes (~5 min)
- Realistic tests: TLS, VPN access, data persistence
- Available for demos at any time

When the project matures and updates are less frequent, add an ephemeral workflow
for clean-install validation (Scenario C).

---

## 2. Preprod Server Sizing

### Current: CX23 (2 vCPU, 4 GB, 40 GB NVMe)

This is tight for the full stack. Options:

| Approach | Services on preprod | RAM needed | Server |
|----------|-------------------|------------|--------|
| **Full stack (light)** | All 12 services with reduced limits | ~4.7 GB | CX23 barely fits |
| **App only** | Skip monitoring (Grafana, VM, Loki, Alloy) | ~3.2 GB | **CX23 fits** |
| **Full stack** | All services at reduced limits | ~4.7 GB | CX33 (5.49 EUR) |

**Recommendation**: CX23 with monitoring disabled in preprod. The Ansible variable
`target_env=preprod` already reduces memory limits. Add this to preprod overrides:

```yaml
# inventory/group_vars/preprod/main.yml
monitoring_enabled: false    # Skip Grafana, VM, Loki, Alloy in preprod
```

This saves ~1.5 GB RAM and keeps the CX23 comfortable.

---

## 3. Preprod Data Seeding

### Architecture

```
S3 Hetzner (vpai-shared bucket)
  └── seed-data/
      ├── pg-dumps/
      │   ├── n8n-latest.dump
      │   ├── openclaw-latest.dump
      │   └── litellm-latest.dump
      ├── redis/
      │   └── dump.rdb
      └── qdrant/
          └── snapshot-latest.txt

        |
        | playbooks/seed-preprod.yml
        v

Preprod CX23 (Hetzner)
  ├── PostgreSQL (restored, anonymized)
  ├── Redis (restored)
  └── Qdrant (snapshot reference)
```

### Automated Seeding via Ansible

Use `playbooks/seed-preprod.yml` to pull and restore:

```bash
ansible-playbook playbooks/seed-preprod.yml \
  -e "target_env=preprod" \
  --vault-password-file .vault_password
```

The playbook:
1. Downloads latest seed data from S3 (vpai-shared/seed-data/)
2. Stops application services
3. Restores PostgreSQL dumps (n8n, openclaw, litellm)
4. Restores Redis RDB
5. Anonymizes credentials and webhooks
6. Restarts all services
7. Runs smoke tests to verify

### Anonymization Rules

| Data | Action | Reason |
|------|--------|--------|
| n8n credential_entity.data | Replace with `***REDACTED***` | Contains API keys |
| n8n webhook_entity.webhook_path | Prefix with `test-` | Prevent duplicate webhook calls |
| LiteLLM API keys in config | Replace with test keys | Prevent prod API billing |
| OpenClaw prompts/history | Keep as-is | Needed for realistic testing |
| Grafana dashboards | Keep as-is | UI testing |
| VictoriaMetrics data | Skip (not seeded) | Preprod generates its own |
| Loki logs | Skip (not seeded) | Preprod generates its own |

### Seed Data Freshness

The pre-backup script on prod exports latest dumps daily to S3:

```
Prod cron 02:55 --> pre-backup.sh --> dumps to /opt/vpai/backups/
                                  --> latest copies to S3 vpai-shared/seed-data/
```

Preprod always seeds from the latest daily export. Maximum data age: 24 hours.

---

## 4. Preprod Domain & TLS

### DNS Configuration

```
preprod.<domain>       A    <preprod-server-ip>
admin.preprod.<domain> A    <preprod-server-ip>
```

Caddy on preprod automatically obtains TLS certificates via Let's Encrypt
(DNS challenge, same as prod).

### Access

| Service | URL | Access |
|---------|-----|--------|
| Health | `https://preprod.<domain>/health` | Public |
| LiteLLM API | `https://preprod.<domain>/litellm/` | API key auth |
| n8n | `https://admin.preprod.<domain>/n8n/` | VPN only |
| Grafana | `https://admin.preprod.<domain>/grafana/` | VPN only |
| OpenClaw | `https://admin.preprod.<domain>/openclaw/` | VPN only |

---

## 5. CI/CD Integration

### Workflow (deploy-preprod.yml — implemented)

```
Push to main (or manual workflow_dispatch)
  --> Lint (yamllint + ansible-lint)
    --> Deploy to permanent preprod (Ansible diff only, ~5 min)
      --> Smoke tests (CI: public only + SSH: full on-server)
        --> Optional: seed preprod with prod data (workflow_dispatch)
        --> Optional: golden snapshot (workflow_dispatch)
```

The workflow supports two manual options via `workflow_dispatch`:
- **seed_data**: Seed preprod with fresh production data after deploy
- **snapshot**: Create a golden Hetzner snapshot after successful tests

Required GitHub secrets: `SSH_PRIVATE_KEY`, `ANSIBLE_VAULT_PASSWORD`,
`PREPROD_SERVER_IP`, `PREPROD_DOMAIN`, `LITELLM_MASTER_KEY`,
`HETZNER_CLOUD_TOKEN` (for snapshots)

---

## 6. Preprod Maintenance

### Monthly Tasks

| Task | Command | Duration |
|------|---------|----------|
| Seed fresh prod data | `ansible-playbook playbooks/seed-preprod.yml` | ~10 min |
| OS updates | `ansible-playbook playbooks/site.yml --tags common` | ~5 min |
| Verify all services | `make smoke-test URL=https://preprod.<domain>` | ~2 min |

### Cost Control

- **If unused for > 1 month**: snapshot and destroy, recreate when needed
  - Snapshot cost: ~0.06 EUR/month (vs 3.49 EUR/month for running VM)
  - Recreation from snapshot: ~5 minutes
- **If budget-constrained**: switch to ephemeral-only (Scenario A)
