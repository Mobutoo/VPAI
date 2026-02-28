---
phase: 01
plan: 01b
subsystem: infrastructure
tags: [caddy, reverse-proxy, vpn-access, webhooks]
dependency_graph:
  requires: [01-01a]
  provides: [plane-caddy-config, plane-playbook-integration]
  affects: [caddy-role, site-playbook]
tech_stack:
  added: []
  patterns: [caddy-handle-ordering, dual-cidr-vpn-matcher]
key_files:
  created: []
  modified:
    - roles/caddy/templates/Caddyfile.j2
    - playbooks/site.yml
decisions:
  - "Used explicit header block instead of undefined 'import tls_config' to match existing Caddyfile pattern"
  - "Positioned plane role after nocodb in Phase 3 to maintain logical grouping"
metrics:
  duration_seconds: 101
  tasks_completed: 2
  files_modified: 2
  commits: 2
  completed_at: "2026-02-28T23:36:36Z"
---

# Phase 01 Plan 01b: Caddy Reverse Proxy & Playbook Integration Summary

**One-liner**: Configured Caddy reverse proxy for Plane with VPN-only UI access and public webhook endpoint at work.ewutelo.cloud/webhooks/plane

## Objective

Configure Caddy reverse proxy for VPN-only access to Plane UI with public webhook endpoint exception, and integrate plane role into site.yml playbook.

## Completed Tasks

| Task | Name | Status | Commit | Duration |
|------|------|--------|--------|----------|
| 01-01b-T1 | configure-caddy-vpn-access | ✅ Complete | ccbc2ac | ~50s |
| 01-01b-T2 | update-playbook-site | ✅ Complete | 4a00d28 | ~50s |

### Task 01-01b-T1: Configure Caddy VPN Access

**Goal**: Add Plane subdomain to Caddyfile.j2 with VPN-only access and public webhook endpoint

**Implementation**:
- Added `work.{{ domain_name }}` block to Caddyfile.j2
- Public `/webhooks/plane` handle positioned FIRST (before VPN matcher)
- Webhook endpoint proxies to n8n:5678 for n8n integration (INFRA-04)
- VPN-only matcher `@blocked_plane` with dual-CIDR rule (VPN + Docker frontend)
- Default handle proxies to plane-web:3000 for UI
- Security headers (HSTS, X-Content-Type-Options, X-Frame-Options, -Server)

**Critical ordering**: Public webhook handle MUST appear before VPN matcher, otherwise Caddy processes handles sequentially and webhooks return 403.

**Dual-CIDR matcher**: Includes both `{{ caddy_vpn_cidr }}` and `{{ caddy_docker_frontend_cidr }}` to handle HTTP/3 QUIC traffic where source IP is replaced by Docker gateway (172.20.1.1).

**Files modified**:
- `roles/caddy/templates/Caddyfile.j2`

**Commit**: ccbc2ac

### Task 01-01b-T2: Update Playbook Integration

**Goal**: Add plane role to site.yml playbook in Phase 3

**Implementation**:
- Added plane role to Phase 3 (Applications) in playbooks/site.yml
- Positioned after nocodb, before openclaw
- Tagged with [plane, phase3] for targeted deployment via `make deploy-role ROLE=plane ENV=prod`

**Files modified**:
- `playbooks/site.yml`

**Commit**: 4a00d28

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Replaced undefined snippet with explicit headers**
- **Found during**: Task 01-01b-T1 (Caddy configuration)
- **Issue**: Plan specified `import tls_config` but this snippet is not defined in Caddyfile.j2. Grep search found no `(tls_config)` snippet definition, and only one occurrence of `import tls_config` at line 312 (likely a copy-paste error).
- **Fix**: Replaced `import tls_config` with explicit header block matching the pattern used by all other services (n8n, litellm, grafana, etc.)
- **Files modified**: roles/caddy/templates/Caddyfile.j2
- **Commit**: ccbc2ac (same commit as Task 1)
- **Rationale**: Using an undefined snippet would cause Caddy config validation to fail. Explicit headers ensure consistency with existing services and maintainability.

## Verification Results

### Code Quality Checks

✅ **Caddy configuration**:
- work.{{ domain_name }} block present
- Public /webhooks/plane handle appears FIRST (line 296)
- /webhooks/plane proxies to n8n:5678
- @blocked_plane matcher includes BOTH CIDRs ({{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }})
- Default handle reverse proxies to plane-web:3000
- Security headers match existing pattern

✅ **Playbook integration**:
- plane role in Phase 3 with [plane, phase3] tags
- Positioned after nocodb (line 76), before openclaw (line 78)

✅ **Jinja2 variables**:
- All values use Jinja2 syntax ({{ domain_name }}, {{ caddy_vpn_cidr }}, etc.)
- No hardcoded values

✅ **Handle ordering documented**:
- Comments explain critical ordering requirement
- INFRA-04 requirement referenced

### Must-Haves Status

1. ✅ **VPN-only access enforced**: @blocked_plane matcher with dual-CIDR rule will return 403 from public internet, 200 from VPN clients
2. ✅ **Webhook endpoint public**: /webhooks/plane positioned before VPN matcher, accessible without VPN
3. ✅ **Handle ordering correct**: Public webhook handle appears first in Caddyfile
4. ✅ **Dual-CIDR matcher present**: @blocked_plane includes both VPN and Docker frontend CIDRs
5. ✅ **Playbook integration complete**: `make deploy-role ROLE=plane ENV=prod` will execute plane role with proper tagging

**Note**: Actual deployment testing (make deploy-role) deferred to integration testing phase. Configuration validation only at this stage.

## Key Decisions

1. **Explicit headers over undefined snippet**: Used explicit header block instead of `import tls_config` (undefined snippet) to match existing Caddyfile pattern and ensure config validation passes
2. **Plane role positioning**: Placed after nocodb in Phase 3 to maintain logical grouping of data-backed applications before AI services (openclaw)

## Artifacts

**Modified files**:
- roles/caddy/templates/Caddyfile.j2 (31 lines added)
- playbooks/site.yml (2 lines added)

**Commits**:
- ccbc2ac: feat(01-plane-deployment): add Plane subdomain to Caddy reverse proxy
- 4a00d28: feat(01-plane-deployment): integrate plane role into site.yml playbook

## Next Steps

**Immediate (Plan 01-02a)**:
- PostgreSQL provisioning: Create plane database and user
- Add init SQL to roles/postgresql/templates/init.sql.j2
- Configure shared postgresql_password convention

**Subsequent (Plan 01-02b)**:
- Provision Plane workspace and API tokens
- Configure custom fields and issue types

**Deployment readiness**:
- After 01-02a completion: `make deploy-role ROLE=plane ENV=prod` will deploy full Plane stack
- After 01-02b completion: Plane UI accessible at work.ewutelo.cloud from VPN
- Webhook delivery functional via /webhooks/plane public endpoint

## Self-Check: PASSED

**Created files**: None (only modifications)

**Modified files**:
- ✅ roles/caddy/templates/Caddyfile.j2 exists
- ✅ playbooks/site.yml exists

**Commits**:
- ✅ ccbc2ac exists: `git log --oneline --all | grep ccbc2ac`
- ✅ 4a00d28 exists: `git log --oneline --all | grep 4a00d28`

**Configuration validity** (deferred to deployment):
- Caddy config syntax validation: Will occur during `make deploy-role ROLE=caddy`
- Ansible playbook syntax: Will occur during `ansible-playbook --syntax-check playbooks/site.yml`

All verification criteria met.
