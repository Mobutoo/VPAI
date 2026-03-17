---
phase: 05-foundation
plan: 02
subsystem: infra
tags: [nocodb, qdrant, ansible, provisioning, brand-voice, embeddings]

# Dependency graph
requires:
  - phase: 05-foundation-01
    provides: Kitsu role, infrastructure config, Fal.ai integration
provides:
  - content-factory-provision Ansible role with NocoDB table provisioning
  - NocoDB brands/contents/scenes table schemas via API
  - Paul Taff brand profile seed data
  - Qdrant brand-voice collection creation and seeding via LiteLLM embeddings
affects: [05-foundation-03, 06-building-blocks, 07-orchestration]

# Tech tracking
tech-stack:
  added: []
  patterns: [nocodb-api-provisioning, qdrant-collection-seeding, litellm-embedding-pipeline]

key-files:
  created:
    - roles/content-factory-provision/tasks/main.yml
    - roles/content-factory-provision/defaults/main.yml
    - roles/content-factory-provision/templates/provision-nocodb-tables.sh.j2
    - roles/content-factory-provision/templates/provision-qdrant.sh.j2
    - roles/content-factory-provision/meta/main.yml
  modified:
    - playbooks/site.yml

key-decisions:
  - "NocoDB FK fields as SingleLineText (API v2 limitation for FK at creation time)"
  - "Qdrant collection parameterized via defaults (vector_size, distance) not hardcoded"
  - "LiteLLM internal endpoint (http://litellm:4000) for embedding generation on server"

patterns-established:
  - "NocoDB API provisioning: find-or-create base, check-then-create tables, sentinel file"
  - "Qdrant seeding: collection PUT idempotent, point_count check before seed, LiteLLM embeddings"

requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04, DATA-05]

# Metrics
duration: 6min
completed: 2026-03-17
---

# Phase 5 Plan 2: NocoDB Data Model Provisioning Summary

**Idempotent NocoDB provisioning (brands/contents/scenes tables + Paul Taff brand seed) and Qdrant brand-voice collection with 3 LiteLLM-embedded vectors**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-17T16:24:45Z
- **Completed:** 2026-03-17T16:31:38Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Created content-factory-provision Ansible role following plane-provision pattern
- NocoDB provisioning script creates 3 tables (brands, contents, scenes) with full column definitions and seeds Paul Taff brand profile
- Qdrant provisioning script creates brand-voice collection (1536 dims, Cosine distance) and seeds 3 brand vectors via LiteLLM embeddings
- Role registered in site.yml after plane-provision in Phase 4.6 provisioning block

## Task Commits

Each task was committed atomically:

1. **Task 1: Create content-factory-provision role with NocoDB table provisioning script** - `d337f4e` (feat)
2. **Task 2: Create Qdrant brand-voice collection provisioning script and add role to site.yml** - `4a59569` (feat)

## Files Created/Modified
- `roles/content-factory-provision/tasks/main.yml` - Provisioning tasks (template deploy, shell execute, debug output)
- `roles/content-factory-provision/defaults/main.yml` - Default variables (NocoDB URL, Qdrant URL, collection config, LiteLLM endpoint)
- `roles/content-factory-provision/templates/provision-nocodb-tables.sh.j2` - NocoDB API script (base creation, 3 tables, Paul Taff seed)
- `roles/content-factory-provision/templates/provision-qdrant.sh.j2` - Qdrant API script (collection creation, 3 embedding vectors)
- `roles/content-factory-provision/meta/main.yml` - Role metadata (galaxy_info)
- `playbooks/site.yml` - Added content-factory-provision role after plane-provision

## Decisions Made
- NocoDB FK fields (brand_id, content_id) created as SingleLineText because NocoDB v2 API does not support FK creation in the initial POST /tables call. FK links deferred to NocoDB UI or Phase 7 workflows.
- Qdrant vector_size and distance are parameterized via defaults (not hardcoded in template) for flexibility.
- LiteLLM internal Docker endpoint (http://litellm:4000) used for embedding generation since the script runs on-server via docker exec context.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed meta/main.yml schema validation**
- **Found during:** Task 2 (lint verification)
- **Issue:** meta/main.yml was missing required galaxy_info fields (author, license) and role_name contained hyphens (invalid per schema `^[a-z][a-z0-9_]+$`)
- **Fix:** Added author, namespace, license, min_ansible_version, platforms fields following qdrant role pattern; changed role_name to use underscores
- **Files modified:** roles/content-factory-provision/meta/main.yml
- **Verification:** `make lint` passes with 0 failures
- **Committed in:** 4a59569 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Schema fix necessary for lint compliance. No scope creep.

## Issues Encountered
None beyond the meta/main.yml schema fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- NocoDB tables and Qdrant collection provisioning role is ready for deployment
- Plan 05-03 (Kitsu provisioning with Zou DB init and project structure) can proceed
- All DATA requirements (DATA-01 through DATA-05) are addressed by this role

---
*Phase: 05-foundation*
*Completed: 2026-03-17*
