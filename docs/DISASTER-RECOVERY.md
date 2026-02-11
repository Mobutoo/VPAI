# DISASTER RECOVERY — Recovery Plan

> **Project**: VPAI — Self-Hosted AI Infrastructure Stack
> **RPO** (Recovery Point Objective): 24 hours (daily backups)
> **RTO** (Recovery Time Objective): 2 hours

---

## Scenario 1: Container Crash

**Trigger**: A single container exits unexpectedly.

**Detection**:
- Uptime Kuma alerts (HTTP checks fail)
- Grafana alert: "Container restarts > 3 in 15 min"
- DIUN notification (if image-related)

**Auto-Recovery**:
All containers have `restart: unless-stopped`. Docker will automatically restart crashed containers.

**Manual Investigation**:
```bash
# Check container status
docker ps -a --filter "name=vpai_"

# Check exit code and logs
docker inspect --format='{{.State.ExitCode}}' vpai_<service>
docker compose logs --tail 100 <service>

# Force restart if needed
docker compose restart <service>
```

**Escalation**: If container keeps crashing (restart loop), proceed to Scenario 3 if database corruption is suspected, or check resource limits with `docker stats`.

---

## Scenario 2: VPS Down — Full Server Loss

**Trigger**: VPS completely unreachable (hardware failure, provider issue, etc.)

**Detection**:
- Uptime Kuma: HTTPS monitor DOWN
- All monitors in alert state

**Recovery Procedure**:

### Step 1: Provision New VPS (15 min)

Option A — From Hetzner Snapshot (fastest):
```bash
# Use the latest golden snapshot from CI/CD pipeline
hcloud server create \
  --name vpai-recovery \
  --type cx23 \
  --location fsn1 \
  --image <snapshot-id> \
  --ssh-key deploy
```

Option B — From scratch + Ansible:
```bash
# Create fresh Debian 13 VPS at OVH or Hetzner
# Then run full Ansible deployment
ansible-playbook playbooks/site.yml -e "target_env=prod" -e "target_host=<new_ip>"
```

### Step 2: Update DNS (5 min)

Update DNS A records to point to the new server IP:
- `<domain>` -> new IP
- `admin.<domain>` -> new IP

### Step 3: Restore Data from S3 (30 min)

On Seko-VPN:
1. Open Zerobyte UI
2. Select the latest successful backup
3. Restore all volumes to the new VPS via VPN mount

On the new VPS:
```bash
# Stop services before restoring data
cd /opt/vpai && docker compose down

# Data is restored via Zerobyte to:
# /opt/vpai/backups/pg_dump/  (PostgreSQL)
# /opt/vpai/data/redis/        (Redis)
# /opt/vpai/backups/qdrant/    (Qdrant)
# /opt/vpai/backups/n8n/       (n8n)

# Restore PostgreSQL
for DB in n8n openclaw litellm; do
  docker cp /opt/vpai/backups/pg_dump/${DB}-latest.dump vpai_postgresql:/tmp/
  docker exec vpai_postgresql pg_restore -U postgres -d ${DB} --clean --if-exists /tmp/${DB}-latest.dump
done

# Redis: already restored via data volume
# Start everything
docker compose up -d
```

### Step 4: Verify (15 min)

```bash
/opt/vpai/scripts/smoke-test.sh
```

### Step 5: Re-register Tailscale (5 min)

```bash
# If Headscale auth key expired, generate a new one on Seko-VPN
tailscale up --login-server=<headscale_url> --authkey=<new_key>
```

**Total estimated RTO**: ~70 minutes

---

## Scenario 3: Database Corruption

**Trigger**: PostgreSQL data corruption, application errors indicating bad data.

**Detection**:
- Application errors in logs (n8n, LiteLLM, OpenClaw)
- PostgreSQL errors in `docker compose logs postgresql`
- Grafana alert: application error rate spike

**Recovery Procedure**:

### Identify affected database

```bash
# Check which database is affected
docker exec vpai_postgresql psql -U postgres -c "\l"

# Check for corruption indicators
docker exec vpai_postgresql psql -U postgres -d <db> -c "SELECT count(*) FROM pg_stat_activity;"
```

### Restore from latest dump

```bash
# Find latest backup
ls -la /opt/vpai/backups/pg_dump/

# Stop affected application
docker compose stop <n8n|openclaw|litellm>

# Restore
docker cp /opt/vpai/backups/pg_dump/<db>-<timestamp>.dump vpai_postgresql:/tmp/restore.dump
docker exec vpai_postgresql pg_restore -U postgres -d <db> --clean --if-exists /tmp/restore.dump
docker exec vpai_postgresql rm /tmp/restore.dump

# Restart application
docker compose start <n8n|openclaw|litellm>
```

### Verify

```bash
/opt/vpai/scripts/smoke-test.sh
docker compose logs --tail 50 <service>
```

**Data Loss**: Up to 24 hours of data (since last backup).

---

## Scenario 4: Security Compromise

**Trigger**: Suspected unauthorized access, malicious activity, or data breach.

**Detection**:
- CrowdSec alerts
- Unexpected container behavior
- Unknown processes or connections
- Fail2ban bans
- Unexplained resource usage

**Response Procedure**:

### Phase 1: Isolate (Immediate — 5 min)

```bash
# Block all public traffic immediately
sudo ufw deny in on eth0

# Keep VPN access for investigation
# Headscale/Tailscale traffic on separate interface

# Stop all application containers
cd /opt/vpai && docker compose stop n8n litellm openclaw caddy
```

### Phase 2: Assess (30 min)

```bash
# Check for unauthorized access
sudo journalctl -u sshd --since "24 hours ago"
sudo cat /var/log/auth.log | grep -i "accepted\|failed"

# Check CrowdSec decisions
sudo cscli decisions list
sudo cscli alerts list

# Check for unexpected containers or processes
docker ps -a
ps auxf

# Check for unauthorized file modifications
find /opt/vpai/configs -mtime -1 -type f

# Check outbound connections
ss -tlnp
ss -tunp | grep ESTABLISHED

# Review application logs for suspicious activity
docker compose logs --since "24h" | grep -i "unauthorized\|forbidden\|injection\|attack"
```

### Phase 3: Rotate ALL Secrets (15 min)

```bash
# Generate new secrets
ansible-playbook playbooks/rotate-secrets.yml -e "target_env=prod"

# Update Ansible Vault with new values
ansible-vault edit inventory/group_vars/all/secrets.yml

# Rotate SSH keys
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
# Update authorized_keys on VPS
```

### Phase 4: Clean Redeploy (45 min)

```bash
# Full teardown
cd /opt/vpai
docker compose down -v  # WARNING: removes volumes
docker system prune -af

# Re-deploy from clean state
ansible-playbook playbooks/site.yml -e "target_env=prod"

# Restore data from LAST KNOWN GOOD backup
ansible-playbook playbooks/backup-restore.yml -e "target_env=prod"
```

### Phase 5: Post-Incident (48h)

1. **Monitor**: Increased vigilance for 48 hours
2. **Audit**: Review all Grafana dashboards for anomalies
3. **Report**: Document the incident, timeline, and remediation
4. **Harden**: Apply additional security measures based on findings
5. **Update**: Patch any vulnerable software identified

---

## Backup Verification Schedule

| Check | Frequency | Responsible |
|-------|-----------|-------------|
| Backup heartbeat in Uptime Kuma | Daily (automatic) | Pre-backup script |
| Manual restore test (single DB) | Monthly | Operator |
| Full disaster recovery drill | Quarterly | Operator |
| Snapshot validity check | Weekly | CI/CD pipeline |

---

## Contact & Escalation

| Severity | Response Time | Action |
|----------|---------------|--------|
| P1 — Full outage | 15 min | Scenario 2 or 4 |
| P2 — Service degraded | 1 hour | Investigate + Scenario 1 or 3 |
| P3 — Non-critical | 4 hours | Investigate at convenience |
| P4 — Cosmetic | Next business day | Planned fix |
