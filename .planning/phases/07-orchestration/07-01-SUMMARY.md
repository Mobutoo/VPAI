---
phase: 07-orchestration
plan: 01
subsystem: api
tags: [n8n, workflow, litellm, nocodb, kitsu, content-factory, llm-chain]

# Dependency graph
requires:
  - phase: 06-building-blocks
    provides: "CF webhooks (cf-update-content, cf-read-content, cf-scene, cf-kitsu-sync)"
  - phase: 05-data-layer
    provides: "NocoDB content table, Kitsu task types"
provides:
  - "cf-brief-to-concept.json: 5-step LLM chain workflow (brief → research → moodboard → concept → casting)"
  - "cf-script-to-storyboard.json: 3-step workflow (script → scene decomposition → sound design)"
affects: ["07-orchestration plans 02+", "n8n-provision role deployment"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "n8n Code node using $http.request() for LiteLLM calls (no native node dependency)"
    - "Eco model (deepseek-v3) for metadata/research, premium model (gpt-4o-mini) for creative writing"
    - "Internal n8n webhook calls via http://localhost:5678/webhook/ prefix"
    - "Non-blocking error handling for storage/sync steps (try/catch, console.error)"

key-files:
  created:
    - roles/n8n-provision/files/workflows/cf-brief-to-concept.json
    - roles/n8n-provision/files/workflows/cf-script-to-storyboard.json
  modified: []

key-decisions:
  - "Step 4 (concept+hook) uses gpt-4o-mini premium model — main creative step requires quality"
  - "Step 6 (script writing) uses gpt-4o-mini with 4000 max_tokens — needs full scene array output"
  - "All other LLM steps use deepseek-v3 (eco) — research, moodboard, casting, sound design are non-creative"
  - "Storage and Kitsu sync steps use try/catch non-blocking — content already generated, sync failures should not abort pipeline"
  - "cf-calendar-sync called in brief-to-concept to auto-create Plane work item (CAL-03 requirement)"
  - "Script output strips markdown code fences before JSON.parse — gpt-4o-mini often wraps JSON in ```json blocks"

patterns-established:
  - "LiteLLM chain: always pass full accumulated context (prior step outputs) to next step"
  - "JSON output from LLM: always strip ``` fences + try/catch fallback to raw string"
  - "Scene creation: sequential for loop in Code node calling cf-scene webhook per scene"

requirements-completed: [FLOW-01, FLOW-03]

# Metrics
duration: 2min
completed: 2026-03-17
---

# Phase 7 Plan 01: LLM Chain Workflows Summary

**Two n8n LLM-chain workflows delivering the creative writing backbone: brief-to-concept (5 steps, deepseek-v3 + gpt-4o-mini) and script-to-storyboard (3 steps with scene decomposition into NocoDB rows)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-17T21:46:27Z
- **Completed:** 2026-03-17T21:48:47Z
- **Tasks:** 2 of 2
- **Files modified:** 2

## Accomplishments
- `cf-brief-to-concept` workflow: 12-node pipeline (webhook + 5 LLM steps + storage + Kitsu + calendar + response) chaining eco and premium models
- `cf-script-to-storyboard` workflow: 8-node pipeline reading locked pre-production content, generating script as JSON scene array, creating NocoDB scene rows via cf-scene, and generating sound design brief
- Both workflows validate X-Webhook-Secret and use $http.request() pattern (no native n8n nodes needed for LiteLLM)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create cf-brief-to-concept workflow** - `5ff81aa` (feat)
2. **Task 2: Create cf-script-to-storyboard workflow** - `2a2ee5c` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `roles/n8n-provision/files/workflows/cf-brief-to-concept.json` - Steps 1-5 LLM chain (brief enhancement, research, moodboard, concept/hook, casting)
- `roles/n8n-provision/files/workflows/cf-script-to-storyboard.json` - Steps 6-8 (script writing, storyboard decomposition, sound design)

## Decisions Made
- gpt-4o-mini used for Step 4 (concept+hook) and Step 6 (script writing) — these are the two main creative steps requiring output quality
- deepseek-v3 (eco) used for all other steps (research, moodboard prompts, casting, sound design)
- Script output from LLM always has markdown code fence stripping before JSON.parse (gpt-4o-mini wraps JSON in ```json blocks)
- Storage and sync steps (cf-update-content, cf-kitsu-sync) are non-blocking — pipeline should not abort if NocoDB/Kitsu is temporarily unreachable

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Workflows will be deployed via Ansible n8n-provision role on next `make deploy-prod`.

## Next Phase Readiness
- Two core LLM workflows ready for deployment via n8n-provision Ansible role
- Both workflows depend on cf-* webhooks from Phase 06 being active
- Ready for 07-02+ plans (generate-assets, rough-cut, calendar sync workflows)

---
*Phase: 07-orchestration*
*Completed: 2026-03-17*
