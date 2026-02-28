# Codebase Concerns

**Analysis Date:** 2026-02-28

---

## Tech Debt

### Docker Compose Handler — Handler Bypasses env_file Reload

**Issue:** Handler at `roles/docker-stack/handlers/main.yml` uses `state: restarted`, which calls `docker compose restart` internally. This **does not reload environment variables** from `env_file`.

**Files:**
- `roles/docker-stack/handlers/main.yml` (line 5)
- All services with `env_file` references: `roles/docker-stack/templates/docker-compose.yml.j2`

**Impact:** When `env_file` is updated (e.g., `OPENAI_API_KEY` added, `LITELLM_MASTER_KEY` changed), the handler fires but containers restart with **stale environment**. Services fail with `MissingEnvVarError`. This affects: n8n, litellm, openclaw, nocodb, palais.

**Current Workaround:** Manual `docker compose up -d` to force recreation.

**Fix Approach:** Change handler to use `state: present` with `recreate: always` to force full container recreation, which reads env_file. This is idempotent (only on handler trigger, not every deploy).

**Priority:** HIGH — Blocks any mid-deployment env var changes without manual intervention.

---

### Sure Container — Image Unpinned to Nightly

**Issue:** `sure_image: "ghcr.io/we-promise/sure:nightly"` in `inventory/group_vars/all/versions.yml` uses `:nightly` tag instead of fixed SHA digest.

**Files:**
- `inventory/group_vars/all/versions.yml` (line 47)

**Impact:** Container behavior **non-deterministic across deployments**. Nightly builds may have breaking changes. Rollback impossible. CI/CD `check-no-latest` Makefile rule doesn't catch `:nightly`.

**Comment in code:** Line 46 explicitly says `# TODO: Pinner sur SHA digest après premier deploy validé`

**Fix Approach:**
1. Pin to specific digest: `sure_image: "ghcr.io/we-promise/sure:sha-<digest>"`
2. Update comment with deployment date and digest

**Priority:** MEDIUM — Personal finance app is low-criticality, but violates deployment standard.

---

### OpenCut — Unpinned Redis Image (serverless-redis-http:latest)

**Issue:** OpenCut docker-compose has hardcoded `:latest` tag in `roles/opencut/templates/docker-compose-opencut.yml.j2` (line 48).

**Files:**
- `roles/opencut/templates/docker-compose-opencut.yml.j2` (line 48: `image: hiett/serverless-redis-http:latest`)

**Impact:** OpenCut may fail to start if `hiett/serverless-redis-http:latest` changes API or drops support. This breaks OpenCut provision task and any automation using OpenCut.

**Fix Approach:**
1. Find current working digest of `hiett/serverless-redis-http:latest`
2. Replace with explicit version tag (e.g., `hiett/serverless-redis-http:1.0.0`)
3. Add to `versions.yml` if production-critical

**Priority:** MEDIUM — OpenCut is on-demand (not auto-started), but breaks if image changes unexpectedly.

---

## Known Bugs & Fragile Areas

### LiteLLM Health Check Interval Config Mistake Risk

**Issue:** TROUBLESHOOTING.md (Section 10, REX-36) documents that `health_check_interval: 0` disables health checks and saves ~$11.64/day. However, there's a common misplacement: developers may configure this under `router_settings` instead of `general_settings`.

**Files:**
- `roles/litellm/templates/litellm_config.yaml.j2`
- TROUBLESHOOTING.md lines 59-73 (REX-36)

**Evidence:** REX-36 explicitly notes `health_check_interval` belongs to `general_settings`, **NOT** `router_settings` (would cause ValueError crash loop in v1.81.3).

**Impact:** If misplaced, LiteLLM container crashes on startup with `ValueError: health_check_interval in router_settings`. Full service outage. Cost: ~$0.73/hour if fixed elsewhere.

**Safe Modification:** Always verify `health_check_interval` is under `general_settings`, not `router_settings`.

**Priority:** HIGH — Easy misconfiguration, immediate failure, costly.

---

### Headscale DNS Override Not Idempotent

**Issue:** `override_local_dns: true` in Headscale config is critical for Split DNS to work (REX-33), but the config is managed manually on Seko-VPN outside Ansible (TODO noted in REX-SESSION-2026-02-20.md line 125).

**Files:**
- Seko-VPN (external): `/opt/services/headscale/config/config.yaml` (manual editing)
- `docs/REX-SESSION-2026-02-20.md` lines 125-126

**Impact:**
- New Seko-VPN deployments may forget to set `override_local_dns: true` → Split DNS breaks
- Windows clients resolve to public IPs instead of VPN IPs → ACL bypass
- No audit trail of who changed it

**Fix Approach:**
1. Integrate Headscale config YAML management into a dedicated role (partially started in `vpn-dns`)
2. Use slurp/parse/combine/write pattern (seen in vpn-dns/tasks/main.yml) to manage `config.yaml` safely
3. Document in RUNBOOK: "After Seko-VPN setup, verify `override_local_dns: true` with: `grep override_local_dns /opt/services/headscale/config/config.yaml`"

**Priority:** MEDIUM — Manual process, but happens rarely. Split DNS failure is noticeable quickly.

---

### OpenClaw Plugin Enabling Not Versioned (v2026.2.22 Breaking Change)

**Issue:** In OpenClaw v2026.2.22, channel plugins (telegram, discord, whatsapp) are **disabled by default**. Must be explicitly enabled in `openclaw.json` under `plugins.entries.<id>.enabled: true`. REX-45 documents this breaking change.

**Files:**
- `roles/openclaw/templates/openclaw.json.j2` (lines 31-41)
- `docs/REX-SESSION-2026-02-23b.md` lines 11-55

**Impact:**
- Upgrading OpenClaw from v2026.2.15 → v2026.2.22 silently disables Telegram bot if `plugins.entries.telegram.enabled` not present
- Users see container `healthy` but bot unreachable
- No error logs — just silent failure

**Fragile Area:** Every OpenClaw minor version bump may change plugin defaults. No public changelog detailing breaking changes.

**Safe Modification:** After any OpenClaw upgrade:
1. Run `docker exec <project>_openclaw node /app/openclaw.mjs plugins list`
2. Verify expected plugins show `loaded`, not `disabled (bundled by default)`
3. If missing, add to `openclaw.json.j2` and redeploy

**Priority:** MEDIUM — Affects any channel integrations. Upgrade process needs post-deploy verification step.

---

### OpenClaw Sandbox Image Build Not Cached

**Issue:** `roles/openclaw/tasks/main.yml` builds `openclaw-sandbox:bookworm-slim` from embedded Dockerfile on every deploy if image exists check is missing. This extracts the Dockerfile from the main image each time.

**Files:**
- `roles/openclaw/tasks/main.yml` (tasks "Check if openclaw-sandbox image already exists" → skip logic)

**Impact:** Wasted CPU/time on Pi and production servers. If image disappears (e.g., `docker prune`), next deploy rebuilds from scratch (~2-5 minutes).

**Current Implementation:** `Check if openclaw-sandbox image already exists` with `ignore_errors` and `changed_when: false` — but may not fully skip rebuild if image was pruned.

**Safe Modification:** Verify `if not found` path is truly idempotent. Test: `docker rmi openclaw-sandbox:bookworm-slim && make deploy-role ROLE=openclaw ENV=prod` should succeed without warnings.

**Priority:** LOW — Performance issue only, not functional. Rebuilds work correctly.

---

## Security Considerations

### Ansible Vault Secrets Not Rotated

**Issue:** `inventory/group_vars/all/secrets.yml` is encrypted with Ansible Vault but no rotation policy or schedule is documented.

**Files:**
- `inventory/group_vars/all/secrets.yml` (encrypted, never read directly)
- `docs/GOLDEN-PROMPT.md` (no rotation section)

**Current Mitigation:** Secrets are encrypted at rest and only decrypted during ansible-playbook execution (requires vault password). SSH deployment is private key auth (no password auth). Access to GitHub repo is SSH-based (private key).

**Recommendations:**
1. Document secret rotation SOP in RUNBOOK.md (e.g., monthly `postgresql_password` rotation)
2. Implement secret versioning: keep old secrets in comments for rollback
3. Set reminder: rotate `headscale_auth_key` every 30 days (pre-auth keys are expiring by design — REX session 0.7)
4. Audit: `ansible-vault view` history is not logged — consider a wrapper script

**Priority:** MEDIUM — Secrets are well-protected, but no lifecycle management documented.

---

### Docker Socket Access in OpenClaw Not Rate-Limited

**Issue:** OpenClaw container has access to host Docker socket (`/var/run/docker.sock:ro` mounted + group_add docker GID). It can spawn unlimited sandbox containers via `dockerode` SDK.

**Files:**
- `roles/docker-stack/templates/docker-compose.yml.j2` (lines 116, 121)
- `TECHNICAL-SPEC.md` section 2.5 (memory limits documented)

**Current Mitigation:** Memory limits on openclaw container (`{{ openclaw_memory_limit }}`, default ~1024M prod). PID limit: `pids: 512` (line 130). But container can still request 512+ sandboxes before hitting limits.

**Risk:** Malicious or buggy agent spawning 500 sandboxes → resource exhaustion → whole stack goes down.

**Recommendations:**
1. Add cgroup v2 limits on number of child processes spawned via Docker socket
2. Add n8n workflow guard: "Max parallel sandboxes = 5" at workflow level
3. Document in RUNBOOK: "If OpenClaw sandboxes exceed 50, restart openclaw container"

**Priority:** LOW-MEDIUM — By design (sandboxes are the feature), but no guardrails documented.

---

### No Rate Limiting on Admin UIs (n8n, Grafana, NocoDB)

**Issue:** Admin UIs are VPN-only (caddy_vpn_enforce: true), but Caddy does not enforce rate limiting on authentication endpoints.

**Files:**
- `roles/caddy/templates/Caddyfile.j2` (VPN ACL, no rate_limit directive)
- CLAUDME.md section "Caddy VPN ACL — Regles critiques"

**Impact:** Brute force attacks on VPN-only interfaces are theoretically low-risk (inside Headscale mesh), but if VPN node is compromised or credentials leaked, attacker can brute-force n8n/Grafana/NocoDB login without throttling.

**Recommendations:**
1. Add `rate_limit` matcher in Caddyfile for `/api/auth` and `/api/login` endpoints
2. Configure: 10 requests per minute per IP inside VPN mesh

**Priority:** LOW — VPN boundary is strong. Recommendation is defense-in-depth only.

---

## Performance Bottlenecks

### LiteLLM Default Health Checks — $11.64/Day Overhead (RESOLVED in REX-36)

**Issue:** Before REX-36 fix, LiteLLM performed health checks on all 38 configured models every ~38 seconds. With expensive models like Perplexity Sonar Pro (~$0.01/check), cost was $11.64/16 hours.

**Files:**
- `roles/litellm/templates/litellm_config.yaml.j2`
- TROUBLESHOOTING.md lines 59-73 (REX-36)
- REX-SESSION-2026-02-18.md lines 59-72

**Current Status:** ✅ **RESOLVED** — `health_check_interval: 0` disables health checks. Note: health checks are disabled production-wide (no ongoing cost).

**Regression Risk:** If someone re-enables health checks (e.g., `health_check_interval: 3600` for hourly checks), cost resumes (~$0.73/day minimum). Easy to miss in code review.

**Safe Modification:** Before changing `health_check_interval` from 0, calculate daily cost: `# of models * cost_per_call * (86400 / interval)`.

**Priority:** LOW — Currently fixed, but needs awareness in any LiteLLM config changes.

---

### PostgreSQL 18.1 — max_connections Default May Be Too Low for n8n

**Issue:** PostgreSQL 18.1 default `max_connections` is 100. n8n connection pooling may not be tuned.

**Files:**
- `roles/postgresql/templates/postgresql.conf.j2` (not visible in provided context, assume defaults)
- `roles/n8n/templates/n8n.env.j2` (N8N_DB_* variables)
- TECHNICAL-SPEC.md section 2.5

**Impact:** Under load (100+ concurrent n8n executions), connection exhaustion → "too many connections" errors → n8n workflows stall.

**Current Mitigation:** n8n has built-in connection pooling, but min_pool and max_pool not explicitly set in n8n.env.

**Recommendations:**
1. Set in n8n.env: `N8N_DB_CONNECTION_MAX_POOL_SIZE=20` (safe for 100 PostgreSQL max_connections)
2. Monitor: `docker exec <project>_postgresql psql -U postgres -c "SELECT sum(numbackends) FROM pg_stat_database;"`
3. Threshold: Alert if > 80 connections used

**Priority:** MEDIUM — Unlikely under normal usage (10-50 workflows/minute), but possible during batch jobs or migrations.

---

### Qdrant Vector DB — No Explicit Memory Tuning

**Issue:** Qdrant container has memory limit (inherited from TECHNICAL-SPEC.md section 2.5) but no explicit configuration for in-memory index settings.

**Files:**
- `roles/docker-stack/templates/docker-compose.yml.j2` (Qdrant service definition, not visible in provided grep)
- TECHNICAL-SPEC.md (resource limits documented)

**Impact:** Large vector collections (millions of embeddings) may exceed container memory limit → OOM kill → data loss (if persistence not configured).

**Recommendations:**
1. Document Qdrant memory model in TROUBLESHOOTING.md (currently missing)
2. Add healthcheck to verify collection size doesn't exceed threshold
3. Set Qdrant config: `vector_size_limit` to prevent unbounded growth

**Priority:** LOW-MEDIUM — Depends on workload. Not critical until vector collections scale.

---

## Scaling Limits

### VPS 8GB Memory — Three Heavy Containers Contend

**Issue:** Production server (Sese-AI, OVH VPS 8GB) runs PostgreSQL (~1.5GB), OpenClaw (~1GB), n8n (~1GB) simultaneously.

**Files:**
- TECHNICAL-SPEC.md section 2.5 (memory limits per service)
- `inventory/hosts.yml` (Sese-AI specs)

**Current Capacity:**
- PostgreSQL: 1536M limit + 512M reservation
- OpenClaw: 1024M limit + 256M reservation
- n8n: 1024M limit + 256M reservation
- Monitoring stack (Grafana, VictoriaMetrics, Loki, Alloy): ~768M combined
- **Total: ~5GB limits** (leaves 3GB headroom for host OS, Docker daemon)

**Limit:** Under sustained high load (100+ n8n workflows executing, large vector queries on Qdrant, Telegram bot processing), memory pressure rises. Any one service spiking beyond limit triggers OOM → container restart.

**Scaling Path:**
1. **Phase 1 (now):** Monitor with `docker stats` and `free -m`. Set alerting at 80% memory usage.
2. **Phase 2:** Upgrade Sese-AI VPS to 16GB (OVH CX42 equivalent) if sustained usage approaches 7GB.
3. **Phase 3 (future):** Split services: PostgreSQL on one VPS, applications on another (new architecture).

**Priority:** MEDIUM — Current deployment is stable, but monitoring and alerting not explicitly configured.

---

## Dependencies at Risk

### OpenClaw Version Upgrade Path Unclear

**Issue:** OpenClaw releases are versioned `YYYY.M.DD` (e.g., `2026.2.23`). No official changelog or breaking changes document. REX-45 documents plugin disabling in v2026.2.22 — discovered by trial.

**Files:**
- `inventory/group_vars/all/versions.yml` (line 12: `openclaw_image: "ghcr.io/openclaw/openclaw:2026.2.23"`)
- `docs/GUIDE-OPENCLAW-UPGRADE.md` (manual checklist)
- REX documents: REX-45 in SESSION-2026-02-23b.md

**Impact:** Each minor version may have breaking changes (plugin defaults, API schema, env var requirements). Upgrade to v2026.3.XX may silently break Telegram, NocoDB integration, or sandbox spawning.

**Risk:** No automated pre-upgrade validation. Post-upgrade verification requires manual `docker exec` checks.

**Mitigation in Place:** `GUIDE-OPENCLAW-UPGRADE.md` exists but requires human execution.

**Recommendations:**
1. Add automated post-upgrade smoke test to n8n: `POST /n8n-mcp/openai/openai-test-agent` (verify agents can spawn)
2. Document in RUNBOOK: "After OpenClaw upgrade, run `make smoke-test` and verify Telegram bot responds"

**Priority:** MEDIUM — Manual process, but upgrade happens infrequently (every 1-2 months).

---

### LiteLLM Provider Budget — Cost Blowouts

**Issue:** LiteLLM routes across multiple providers (OpenRouter, Anthropic, OpenAI). No individual provider caps, only global budget (`max_budget: 5` per day).

**Files:**
- `roles/litellm/templates/litellm_config.yaml.j2` (provider config)
- `inventory/group_vars/all/main.yml` (budget variables)
- TROUBLESHOOTING.md section 10 (LiteLLM pieges)

**Evidence:** REX-47 notes OpenRouter budget was exhausted, forcing fallback to free models. No per-provider spend warning.

**Current Mitigation:** n8n workflow monitors `LiteLLM budget` endpoint (not explicitly documented) and alerts at 70%/90%. Manual `eco mode` toggle via Telegram.

**Recommendations:**
1. Add per-provider spend caps: `provider_budget_config` in `litellm_config.yaml.j2`
   - OpenRouter: $3/day (65% of $5 budget)
   - Anthropic: $0.75/day (15% of budget)
   - OpenAI: $0.50/day (10% of budget)
2. Document in TROUBLESHOOTING.md: "If a provider exhausts budget, model falls back to next in chain"

**Priority:** MEDIUM — Cost control is working (no surprise bills), but could be more granular.

---

## Test Coverage Gaps

### Docker-in-Docker (DooD) Sandbox Path Mounting — No Automated Test

**Issue:** OpenClaw sandbox spawning via Docker socket requires careful path mounting (REX-49, TROUBLESHOOTING.md 11.23). Host path must equal container path (`/opt/project/data/...:/opt/project/data/...`). If misconfigured, `AGENTS.md` read fails with `ENOENT`.

**Files:**
- `roles/docker-stack/templates/docker-compose.yml.j2` (lines 96-110, volume configuration)
- `TROUBLESHOOTING.md` section 11.23 (manual diagnostic)

**Current Test:** Manual `docker exec openclaw-sbx-agent-messenger-XXXX ls /workspace/AGENTS.md`. Only run by humans during deployment.

**Risk:** Regression if docker-compose template is refactored. CI/CD pipeline has no Molecule test for sandbox spawn.

**Recommendations:**
1. Add Molecule test to `roles/docker-stack/molecule/default/verify.yml`:
   ```yaml
   - name: Test OpenClaw sandbox creation
     shell: |
       docker exec {{ project_name }}_openclaw node /app/openclaw.mjs agents create --name test-agent --type builder
       sleep 5
       docker exec {{ project_name }}_openclaw node /app/openclaw.mjs agents delete --name test-agent
   ```

**Priority:** LOW-MEDIUM — Deployment validation is manual and thorough (humans run smoke tests), but automation would prevent regressions.

---

### Handler Idempotence — env_file Reload Path Not Tested

**Issue:** Handler in `roles/docker-stack/handlers/main.yml` uses `state: restarted` which does NOT reload env_file (documented in TROUBLESHOOTING.md 11.18). This is known but Molecule tests don't verify the fix.

**Files:**
- `roles/docker-stack/handlers/main.yml`
- `roles/docker-stack/molecule/` (tests, if any)

**Current Test:** None visible. Handler is only triggered when tasks change — hard to test idempotence in Molecule.

**Recommendations:**
1. Add integration test in smoke-tests role:
   ```yaml
   - name: Test env_file reload after update
     block:
       - name: Update openclaw.env with new variable
         lineinfile:
           path: /opt/{{ project_name }}/configs/openclaw/openclaw.env
           line: TEST_VAR=newvalue
       - name: Trigger handler (restarted → should fail, present → should succeed)
       - name: Verify container has new env var
         shell: docker exec {{ project_name }}_openclaw env | grep TEST_VAR=newvalue
   ```

**Priority:** LOW — Known issue with documented workaround. Fix requires handler refactor (marked as TODO in code).

---

## Missing Critical Features

### Headscale Config Not Version Controlled

**Issue:** Headscale configuration on Seko-VPN (`/opt/services/headscale/config/config.yaml`) is manually edited and **not tracked in Ansible**. Critical setting `override_local_dns: true` was missing initially (REX-33).

**Files:**
- External (Seko-VPN): `/opt/services/headscale/config/config.yaml` (manual)
- `docs/REX-SESSION-2026-02-20.md` (lines 125-126, TODO noted)

**Impact:**
- No audit trail of config changes
- New Seko-VPN setup requires manual DNS config (easy to forget)
- Impossible to automate Headscale provisioning for failover

**Recommendations:**
1. Create `roles/headscale/` role (separate from main site.yml, deploy on Seko-VPN only)
2. Manage config.yaml via Jinja2 template in `roles/headscale/templates/`
3. Use slurp/parse/combine/write pattern (seen in vpn-dns role) to safely update YAML

**Priority:** MEDIUM — Headscale is critical infrastructure, but failure is slow (DNS works, VPN key management fails).

---

## Audit & Monitoring Gaps

### Container Healthcheck Failures Not Alerted

**Issue:** Docker healthchecks are configured on all services (`interval: 30s, retries: 5`), but no monitoring alerts when a container becomes `unhealthy`.

**Files:**
- `roles/docker-stack/templates/docker-compose.yml.j2` (healthcheck sections throughout)
- `roles/monitoring/templates/` (Grafana/VictoriaMetrics config)

**Current Status:** Manual smoke tests in `roles/smoke-tests/` run after deploy, but no continuous monitoring.

**Impact:** Service degradation may go unnoticed for 10+ minutes (Telegram messages no longer arrive, n8n workflows stall).

**Recommendations:**
1. Add cAdvisor metric: expose Docker healthcheck status
2. Add Grafana alert: `container_health_status == 0` (unhealthy) → Telegram alert
3. SLA: "Detect unhealthy container within 5 minutes"

**Priority:** MEDIUM — Affects incident response time. Recommended for production stability.

---

## Architecture Concerns

### Docker Compose Phase A/B Split — Cleanup Race Condition

**Issue:** Deployment stops Phase B before redeploy (`docker compose down`), but Phase A (infra) continues running. If Phase A is updated (e.g., PostgreSQL config change), Phase B containers may have stale connections.

**Files:**
- `roles/docker-stack/tasks/main.yml` (cleanup logic)
- TECHNICAL-SPEC.md section 2.5 (Phase A/B architecture)

**Mitigation:** Phase A has `depends_on: []` (no explicit ordering), and services have connection pooling + retry logic. Observed to work in practice without issues.

**Recommendations:**
1. Document in RUNBOOK: "If PostgreSQL config is changed, manually restart n8n/OpenClaw after Phase A finishes"
2. Consider adding `stop_grace_period: 30s` to Phase B containers (allow graceful shutdown)

**Priority:** LOW — Works in practice, but worth documenting for future deployments.

---

## Summary Table

| Concern | Severity | Status | File(s) | Mitigation |
|---------|----------|--------|---------|-----------|
| Handler env_file reload | HIGH | Known, workaround | docker-stack handlers | Use `state: present + recreate: always` |
| Sure :nightly image | MEDIUM | Unresolved | versions.yml | Pin to SHA digest |
| OpenCut :latest redis | MEDIUM | Unresolved | opencut docker-compose | Pin version tag |
| LiteLLM config misplacement | HIGH | Documented | litellm config | Verify `general_settings`, not `router_settings` |
| Headscale DNS not idempotent | MEDIUM | Manual TODO | Seko-VPN external | Create role to manage config.yaml |
| OpenClaw plugin breaking changes | MEDIUM | Workaround | openclaw.json.j2 | Post-upgrade verification checklist |
| Docker socket unlimited sandboxes | LOW-MEDIUM | Design | docker-compose.yml | Add guardrails in n8n workflows |
| PostgreSQL connection exhaustion | MEDIUM | Unresolved | postgresql defaults | Tune connection pooling |
| Memory contention on 8GB VPS | MEDIUM | Monitored | TECHNICAL-SPEC | Upgrade VPS if approaching 80% usage |
| OpenClaw changelog missing | MEDIUM | Manual workaround | GUIDE-OPENCLAW-UPGRADE.md | Automated smoke test post-upgrade |
| Container health not alerted | MEDIUM | Gap | monitoring stack | Add Grafana alert for unhealthy containers |

---

*Concerns audit: 2026-02-28*
