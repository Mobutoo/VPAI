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
key-decisions:
  - "vault_plane_api_key added as alias for vault_plane_api_token (n8n.env.j2 convention)"
  - "plane_cf_project_id and plane_cf_module_id added to main.yml from config.json values"
  - "Deployment via Tailscale IP 100.64.0.14 (public IP 137.74.114.167 unreachable)"
requirements-completed: [FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, FLOW-06, FLOW-07, CAL-01, CAL-02, CAL-03]
metrics:
  duration: "~6min"
  completed_date: "2026-03-17"
---

# Phase 7 Plan 05: Deploy CF Workflows to Sese-AI Summary

**8 CF workflows live on Sese-AI n8n with all webhook endpoints active, Kitsu/Plane env vars loaded, and human-verified deployment confirmed.**

## Performance

- **Duration:** ~6min (including human checkpoint)
- **Started:** 2026-03-17T23:00:00Z
- **Completed:** 2026-03-17T23:10:00Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments

- All 8 Content Factory workflows deployed and active on Sese-AI n8n instance
- Kitsu and Plane env vars loaded in n8n container via recreation
- Human verified all 8 CF workflows active (green toggle) and webhook endpoints responding
- Ansible deployment pipeline confirmed working for future workflow updates

## Task Commits

1. **Task 1: Deploy n8n-provision to Sese-AI** - `60275a6` (feat)
2. **Task 2: Verify deployed workflows respond** - human-approved (no code commit)

**Plan metadata:** `2a45792` (docs: partial summary during checkpoint)

## Files Created/Modified

- `inventory/group_vars/all/main.yml` - Added plane_cf_project_id, plane_cf_module_id, plane_workspace_slug
- `inventory/group_vars/all/secrets.yml` - Added vault_plane_api_key alias

## Tasks Completed

### Task 1: Deploy n8n-provision to Sese-AI (COMPLETE)

- Ran dry run (`--check --diff`) confirming 4 changes
- Pre-deploy fixes applied (see Deviations section)
- Deployed `n8n-provision` role: all 8 CF workflows imported
- Deployed `n8n` role: container recreated with new env vars
- Verified: 8 CF workflows listed via `n8n list:workflow`
- Verified: KITSU_BOT_EMAIL, KITSU_BOT_PASSWORD, KITSU_API_URL, PLANE_API_KEY, PLANE_CF_PROJECT_ID, PLANE_CF_MODULE_ID all loaded in container

### Task 2: Verify deployed workflows respond (COMPLETE)

Human approved deployment. Confirmed:
- All 8 CF workflows visible in n8n UI with active (green) toggles
- Webhook endpoints respond to POST requests (no 404)
- Kitsu authentication works from n8n environment
- Deployment approved by human on 2026-03-17

## Deployed Workflows

| Workflow | File | Status |
|----------|------|--------|
| CF Brief to Concept | cf-brief-to-concept.json | Active |
| CF Script to Storyboard | cf-script-to-storyboard.json | Active |
| CF Generate Assets | cf-generate-assets.json | Active |
| CF Rough Cut | cf-rough-cut.json | Active |
| CF Invalidation Engine | cf-invalidation-engine.json | Active |
| CF Kitsu Sync | cf-kitsu-sync.json.j2 | Active (template) |
| CF Calendar Sync | cf-calendar-sync.json | Active |
| CF Kitsu Inbound | cf-kitsu-inbound.json | Active |

## Decisions Made

- `vault_plane_api_key` added as alias for `vault_plane_api_token` to match n8n.env.j2 convention
- `plane_cf_project_id` and `plane_cf_module_id` promoted from config.json to main.yml for Ansible var scope
- Tailscale IP `100.64.0.14` used for Sese-AI deploy (public IP `137.74.114.167` unreachable via SSH)

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

---

**Total deviations:** 3 auto-fixed (1 bug, 1 missing config, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required beyond what was already deployed.

## Next Phase Readiness

- Phase 7 complete: all 8 CF workflows live and verified on Sese-AI
- Content Factory pipeline ready for end-to-end testing (send brief, observe workflow execution)
- Kitsu production tracking active via cf-kitsu-inbound event handler
- Plane calendar sync available via cf-calendar-sync webhook

---
*Phase: 07-orchestration*
*Completed: 2026-03-17*

## Self-Check: PASSED

- [x] 8 CF workflows confirmed active by human
- [x] Commit 60275a6 exists and contains all workflow registration changes
- [x] Partial summary commit 2a45792 exists
- [x] All requirements from plan frontmatter documented: FLOW-01 through FLOW-07, CAL-01 through CAL-03
