---
phase: 06-building-blocks
plan: 02
subsystem: ai-agent
tags: [openclaw, skill, telegram, content-factory, n8n, jinja2]

requires:
  - phase: 05-foundation
    provides: NocoDB tables, Kitsu project structure, Qdrant brand-voice collection
provides:
  - Content-director SKILL.md.j2 template with 9 Telegram commands
  - Skill registered in openclaw_skills list
  - Topic 7 (contenu) routing to marketer agent
affects: [07-n8n-workflows, openclaw-deploy]

tech-stack:
  added: []
  patterns: [n8n-webhook-delegation, gate-based-pipeline, invalidation-matrix]

key-files:
  created:
    - roles/openclaw/templates/skills/content-director/SKILL.md.j2
  modified:
    - roles/openclaw/defaults/main.yml

key-decisions:
  - "All NocoDB/Kitsu CRUD delegated to n8n webhooks (agent sandbox has no direct API secrets)"
  - "5 dedicated CF webhooks: cf-create-content, cf-update-content, cf-read-content, cf-scene, cf-kitsu-sync"
  - "Contenu topic routes to marketer agent (not concierge)"

patterns-established:
  - "CF webhook naming: cf-<action> prefix for Content Factory n8n endpoints"
  - "Gate-based pipeline: sequential gate locks with prerequisite validation"
  - "Invalidation matrix: targeted rollback preserving unaffected scenes"

requirements-completed: [SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, SKILL-06, SKILL-07, SKILL-08, SKILL-09]

duration: 3min
completed: 2026-03-17
---

# Phase 6 Plan 02: Content Director Skill Summary

**OpenClaw content-director skill template (405 lines) with 9 Telegram commands, gate-based pipeline, invalidation matrix, and n8n webhook delegation for NocoDB/Kitsu**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-17T18:50:50Z
- **Completed:** 2026-03-17T18:53:42Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created SKILL.md.j2 Jinja2 template (405 lines) documenting the full 14-step Content Factory pipeline
- Defined 9 Telegram commands: /content, /ok, /adjust, /back, /preview, /impact + 5 gate commands
- All NocoDB and Kitsu operations delegated to n8n via 5 dedicated webhooks (no secrets in agent sandbox)
- Registered content-director in openclaw_skills (18 total) and contenu topic routing to marketer agent

## Task Commits

Each task was committed atomically:

1. **Task 1: Create content-director SKILL.md.j2 template** - `cb5b633` (feat)
2. **Task 2: Register skill and topic routing in Ansible defaults** - `8260f53` (feat)

## Files Created/Modified
- `roles/openclaw/templates/skills/content-director/SKILL.md.j2` - Full content-director skill template with commands, APIs, invalidation matrix, rules
- `roles/openclaw/defaults/main.yml` - Added content-director to skills list and contenu topic to telegram routing

## Decisions Made
- All NocoDB/Kitsu CRUD delegated to n8n webhooks (secrets not in sandbox)
- 5 dedicated CF webhooks defined (cf-create-content, cf-update-content, cf-read-content, cf-scene, cf-kitsu-sync)
- Contenu topic routes to marketer agent (topic 7)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Skill template ready for deployment via existing Ansible task loop
- n8n CF webhooks (cf-create-content, etc.) need to be created in Phase 7
- Vault needs `telegram_openclaw_topic_ids.contenu` entry when topic is created in Telegram

---
*Phase: 06-building-blocks*
*Completed: 2026-03-17*
