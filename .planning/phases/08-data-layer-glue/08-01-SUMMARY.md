---
phase: 08-data-layer-glue
plan: 01
subsystem: api
tags: [nocodb, n8n, webhook, crud, ansible]

requires:
  - phase: 05-infra-base
    provides: NocoDB deployed with API token and base provisioning
  - phase: 06-building-blocks
    provides: n8n webhook pattern established, 5 CF webhook contracts defined
  - phase: 07-orchestration
    provides: 8 CF pipeline workflows that call the 4 CRUD webhooks

provides:
  - cf-create-content webhook workflow (NocoDB content row creation)
  - cf-read-content webhook workflow (content + brand data merge)
  - cf-update-content webhook workflow (dual-secret, field PATCH)
  - cf-scene webhook workflow (4-action CRUD router)
  - NocoDB contents table extended with 14 step-data columns
  - NocoDB table ID env vars in n8n.env.j2

affects: [09-deploy, pipeline-testing, content-factory-e2e]

tech-stack:
  added: []
  patterns:
    - "NocoDB table ID resolution: env var with meta API fallback"
    - "Dual-secret webhook validation: body.secret OR x-webhook-secret header"
    - "Action-routed webhook: single endpoint with action field dispatch"

key-files:
  created:
    - roles/n8n-provision/files/workflows/cf-create-content.json
    - roles/n8n-provision/files/workflows/cf-read-content.json
    - roles/n8n-provision/files/workflows/cf-update-content.json
    - roles/n8n-provision/files/workflows/cf-scene.json
  modified:
    - roles/content-factory-provision/templates/provision-nocodb-tables.sh.j2
    - roles/n8n/templates/n8n.env.j2

key-decisions:
  - "SingleSelect changed to SingleLineText for status/provider fields (Pitfall 5: too many status values for SingleSelect)"
  - "NocoDB table ID resolution uses env vars with runtime meta API fallback"
  - "cf-scene uses route_action extraction before scene field processing to avoid Pitfall 2 field name collision"

patterns-established:
  - "NocoDB CRUD proxy: webhook trigger + validate secret + code node with HTTP + respond"
  - "Table ID env vars: NOCODB_CF_BASE_ID, NOCODB_CONTENTS_TABLE_ID, NOCODB_SCENES_TABLE_ID, NOCODB_BRANDS_TABLE_ID"
  - "Column addition idempotence: check existing columns before POST"

requirements-completed: [DATA-06]

duration: 4min
completed: 2026-03-17
---

# Phase 8 Plan 1: NocoDB CRUD Webhooks Summary

**4 NocoDB CRUD webhook workflows (create, read, update, scene) closing the primary CF pipeline blocker, with 14 step-data columns and table ID env vars**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-17T23:05:13Z
- **Completed:** 2026-03-17T23:09:17Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Created 4 missing webhook workflows that the entire CF pipeline depends on (was returning 404)
- Extended NocoDB contents table provisioning with 14 step-data columns (idempotent addition)
- Changed SingleSelect fields to SingleLineText to avoid 422 errors on unlisted status/provider values
- Added NocoDB table ID env vars to n8n.env.j2 for runtime discovery

## Task Commits

Each task was committed atomically:

1. **Task 1: Add missing NocoDB content columns and table ID env vars** - `4705e7e` (feat)
2. **Task 2: Create cf-create-content.json and cf-read-content.json** - `23890f3` (feat)
3. **Task 3: Create cf-update-content.json and cf-scene.json** - `603dfaa` (feat)

## Files Created/Modified
- `roles/n8n-provision/files/workflows/cf-create-content.json` - Webhook: creates NocoDB content row, returns content_id
- `roles/n8n-provision/files/workflows/cf-read-content.json` - Webhook: reads content row + merges brand data from brands table
- `roles/n8n-provision/files/workflows/cf-update-content.json` - Webhook: PATCH content fields by content_id with dual-secret support
- `roles/n8n-provision/files/workflows/cf-scene.json` - Webhook: 4-action router (create/list/update/invalidate scenes)
- `roles/content-factory-provision/templates/provision-nocodb-tables.sh.j2` - Added 14 columns, changed SingleSelect to SingleLineText, output table IDs
- `roles/n8n/templates/n8n.env.j2` - Added 4 NOCODB table ID env vars

## Decisions Made
- SingleSelect changed to SingleLineText for `status` (contents), `status` (scenes), and `provider` (scenes) to avoid NocoDB 422 errors on unlisted values
- Table ID resolution uses env vars with meta API fallback -- resilient to both fresh installs and reprovisions
- cf-scene extracts routing action before processing scene fields to handle Pitfall 2 (field name collision between route action and scene action description)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 CRUD webhooks ready for deployment to Sese-AI
- n8n-provision Ansible loop will auto-import the new workflow files on next deploy
- NocoDB table IDs need to be populated after first provisioning run (or left empty for meta API fallback)

---
*Phase: 08-data-layer-glue*
*Completed: 2026-03-17*

## Self-Check: PASSED

All 6 files found. All 3 task commits verified.
