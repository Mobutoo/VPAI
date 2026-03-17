---
phase: 07-orchestration
plan: 05
subsystem: n8n-workflows
tags: [n8n, deploy, kitsu, plane, content-factory]
dependency_graph:
  requires: [07-04]
  provides: [FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, FLOW-06, FLOW-07, CAL-01, CAL-02, CAL-03]
  affects: [n8n, kitsu, plane]
tech_stack:
  added: []
  patterns: [ansible-n8n-provision, tailscale-deploy-ip]
key_files:
  created: []
  modified:
    - inventory/group_vars/all/main.yml
    - inventory/group_vars/all/secrets.yml
decisions:
  - "vault_plane_api_key added as alias for vault_plane_api_token (n8n.env.j2 convention)"
  - "plane_cf_project_id and plane_cf_module_id added to main.yml from config.json values"
  - "Deployment via Tailscale IP 100.64.0.14 (public IP 137.74.114.167 unreachable)"
metrics:
  duration: "~4min"
  completed_date: "2026-03-17"
status: partial — stopped at Task 2 checkpoint
---

# Phase 7 Plan 05: Deploy CF Workflows to Sese-AI Summary

**One-liner:** All 8 CF workflows deployed to Sese-AI n8n with Kitsu/Plane env vars loaded via container recreation.

## Tasks Completed

### Task 1: Deploy n8n-provision to Sese-AI (COMPLETE)

- Ran dry run (`--check --diff`) confirming 4 changes
- Pre-deploy fixes applied (see Deviations section)
- Deployed `n8n-provision` role: all 8 CF workflows imported
- Deployed `n8n` role: container recreated with new env vars
- Verified: 8 CF workflows listed via `n8n list:workflow`
- Verified: KITSU_BOT_EMAIL, KITSU_BOT_PASSWORD, KITSU_API_URL, PLANE_API_KEY, PLANE_CF_PROJECT_ID, PLANE_CF_MODULE_ID all loaded in container

### Task 2: Verify deployed workflows respond (PENDING)

Stopped at `checkpoint:human-verify`. Awaiting human confirmation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Missing vault_plane_api_key in secrets.yml**
- **Found during:** Task 1 pre-deploy check
- **Issue:** n8n.env.j2 references `{{ vault_plane_api_key }}` but vault only had `vault_plane_api_token`. Would result in empty PLANE_API_KEY env var.
- **Fix:** Added `vault_plane_api_key` to vault as alias (same value as `vault_plane_api_token`)
- **Files modified:** `inventory/group_vars/all/secrets.yml`
- **Commit:** 60275a6

**2. [Rule 2 - Missing Config] Missing plane_cf_project_id / plane_cf_module_id in main.yml**
- **Found during:** Task 1 pre-deploy check
- **Issue:** n8n.env.j2 uses `plane_cf_project_id | default('')` and `plane_cf_module_id | default('')` — IDs existed in config.json but not in group_vars, so PLANE_CF_PROJECT_ID would be empty.
- **Fix:** Added both variables to main.yml using IDs from config.json, plus plane_workspace_slug
- **Files modified:** `inventory/group_vars/all/main.yml`
- **Commit:** 60275a6

**3. [Rule 3 - Blocking] Sese-AI public IP unreachable (connection timeout)**
- **Found during:** Task 1 dry run
- **Issue:** `137.74.114.167:804` timed out. Phase 06 decision documents "Tailscale VPN IP (100.64.0.14) used for Sese-AI deploy".
- **Fix:** Added `-e "prod_ip=100.64.0.14"` to all ansible-playbook commands
- **Commit:** N/A (runtime parameter only)

## Deployed Workflows

| Workflow | File | Status |
|----------|------|--------|
| CF Brief to Concept | cf-brief-to-concept.json | Imported |
| CF Script to Storyboard | cf-script-to-storyboard.json | Imported |
| CF Generate Assets | cf-generate-assets.json | Imported |
| CF Rough Cut | cf-rough-cut.json | Imported |
| CF Invalidation Engine | cf-invalidation-engine.json | Imported |
| CF Kitsu Sync | cf-kitsu-sync.json.j2 | Imported (template) |
| CF Calendar Sync | cf-calendar-sync.json | Imported |
| CF Kitsu Inbound | cf-kitsu-inbound.json | Imported |

## Self-Check: PASSED

- [x] 8 CF workflows confirmed via `n8n list:workflow`
- [x] All env vars confirmed via `docker inspect javisi_n8n`
- [x] Commit 60275a6 exists
