---
phase: 07-orchestration
plan: "04"
subsystem: infra
tags: [n8n, ansible, plane, kitsu, content-factory, workflows]

# Dependency graph
requires:
  - phase: 07-01
    provides: n8n webhook infrastructure (cf-read-content, cf-update-content, cf-scene, cf-create-content)
  - phase: 07-02
    provides: Wave 1 generation workflows (cf-brief-to-concept, cf-generate-assets, cf-rough-cut)
  - phase: 07-03
    provides: Feedback loop workflows (cf-invalidation-engine, cf-kitsu-sync, cf-kitsu-inbound)
provides:
  - cf-calendar-sync.json: NocoDB-to-Plane editorial calendar sync (create_work_item, create_cycle, add_to_cycle, sync_content)
  - All 8 CF workflows registered in n8n-provision Ansible deploy loops (copy, checksum, store, cleanup)
  - Template task for cf-kitsu-sync.json.j2 in n8n-provision tasks
  - Kitsu credentials (KITSU_BOT_EMAIL, KITSU_BOT_PASSWORD, KITSU_API_URL) in n8n.env.j2
  - Plane calendar credentials (PLANE_API_KEY, PLANE_WORKSPACE_SLUG, PLANE_CF_PROJECT_ID, PLANE_CF_MODULE_ID) in n8n.env.j2
affects: [Phase 07 deploy, n8n-provision role, n8n env config, editorial calendar workflow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Plane API via X-API-Key header with $env.* for all workspace/project IDs (no hardcoding)"
    - "vault-guarded env vars: {% if vault_xxx is defined and vault_xxx | length > 0 %} pattern"
    - "Switch node routing for multi-action webhooks (create_work_item/create_cycle/add_to_cycle/sync_content)"

key-files:
  created:
    - roles/n8n-provision/files/workflows/cf-calendar-sync.json
    - .planning/phases/07-orchestration/07-04-SUMMARY.md
  modified:
    - roles/n8n-provision/tasks/main.yml
    - roles/n8n/templates/n8n.env.j2

key-decisions:
  - "cf-kitsu-sync uses template task (not copy loop) — Jinja2 vars require ansible.builtin.template, not ansible.builtin.copy"
  - "Loop 1 (copy) has 7 CF workflows (no cf-kitsu-sync); Loops 2/3/4 have all 8 (cf-kitsu-sync included)"
  - "Plane IDs (workspace slug, project, module) use Ansible variables with | default('') — not hardcoded"
  - "All vault variables guarded with {% if defined %} to prevent UndefinedError on fresh deploys"

patterns-established:
  - "Template task pattern: ansible.builtin.template for .j2 workflow files, placed before Copy loop"
  - "Switch node multi-action routing: 4 outputs (create_work_item, create_cycle, add_to_cycle, sync_content)"

requirements-completed: [CAL-01, CAL-02, CAL-03]

# Metrics
duration: 5min
completed: 2026-03-17
---

# Phase 7 Plan 4: CF Calendar Sync + Ansible Registration Summary

**Plane editorial calendar sync workflow (4-action webhook) and all 8 CF workflows registered in n8n-provision Ansible deploy loops with Kitsu/Plane env vars in n8n.env.j2**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-17T22:32:36Z
- **Completed:** 2026-03-17T22:37:00Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- Created cf-calendar-sync.json with 4 actions: create_work_item (CAL-01), create_cycle (CAL-02), add_to_cycle, sync_content from NocoDB (CAL-03)
- All 8 CF workflows registered in all 4 n8n-provision Ansible deploy loops (copy, checksum, store, cleanup)
- Template task added for cf-kitsu-sync.json.j2 following creative-pipeline.json.j2 pattern
- n8n.env.j2 updated with Kitsu credentials (BOT_EMAIL, BOT_PASSWORD, API_URL) and Plane calendar IDs

## Task Commits

Each task was committed atomically:

1. **Task 1: Create cf-calendar-sync workflow** - `70ad74f` (feat)
2. **Task 2: Register all CF workflows in Ansible + add env vars** - `9bded94` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `roles/n8n-provision/files/workflows/cf-calendar-sync.json` - n8n workflow: Plane editorial calendar sync, 4 actions via webhook, 8 nodes (Trigger, Validate, Switch, CreateWorkItem, CreateCycle, AddToCycle, SyncContent, Response)
- `roles/n8n-provision/tasks/main.yml` - Added template task for cf-kitsu-sync, 7 static CF workflows to Loop 1 (copy), 8 CF workflows to Loops 2/3/4 (checksum/store/cleanup)
- `roles/n8n/templates/n8n.env.j2` - Added KITSU_BOT_EMAIL, KITSU_BOT_PASSWORD, KITSU_API_URL, PLANE_API_KEY, PLANE_WORKSPACE_SLUG, PLANE_CF_PROJECT_ID, PLANE_CF_MODULE_ID

## Decisions Made

- cf-kitsu-sync uses `ansible.builtin.template` task (not in copy loop) because it is a .j2 file requiring variable substitution. Consistent with creative-pipeline.json.j2 pattern already established.
- Loop 1 (copy loop) has 7 static CF workflows, not cf-kitsu-sync. Loops 2/3/4 (checksum/store/cleanup) include all 8 — cf-kitsu-sync generates to /tmp via template task so the checksum/cleanup tasks still apply.
- Plane workspace slug defaults to `ewutelo` (known from research). CF project ID and module ID use `| default('')` to avoid UndefinedError on deploys where group_vars don't yet define them.
- All vault variables (KITSU_BOT_EMAIL, KITSU_BOT_PASSWORD, PLANE_API_KEY) guarded with `{% if vault_xxx is defined and vault_xxx | length > 0 %}` to support fresh deploys without these secrets yet in secrets.yml.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

The following Ansible variables must be added to `inventory/group_vars/all/secrets.yml` (vault) before deploying:
- `vault_kitsu_bot_email` — Kitsu bot email (javisi.bot@gmail.com)
- `vault_kitsu_bot_password` — Kitsu bot password
- `vault_plane_api_key` — Plane API key for calendar sync

The following Ansible variables should be added to `inventory/group_vars/all/main.yml` when known:
- `plane_cf_project_id` — Content Factory project ID in Plane (from research: `e0cb95f0-0ea5-41b8-a3e3-aec45e8cc37e`)
- `plane_cf_module_id` — Content Factory module ID in Plane (from research: `c04ac29e-9842-4eec-8ff6-6923e9fe75d7`)

## Next Phase Readiness

- All 8 CF workflows ready for deployment via `make deploy-role ROLE=n8n-provision ENV=prod`
- cf-calendar-sync.json implements all 3 CAL requirements (create work items, create cycles, sync from NocoDB)
- Phase 7 orchestration is now complete — all workflows created and wired into Ansible deploy pipeline

---
*Phase: 07-orchestration*
*Completed: 2026-03-17*
