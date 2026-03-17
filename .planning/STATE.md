---
gsd_state_version: 1.0
milestone: v2026.3
milestone_name: Content Factory
status: planning
stopped_at: "07-05 Task 1 complete, stopped at Task 2 checkpoint:human-verify — awaiting human confirmation of deployed workflows"
last_updated: "2026-03-17T22:02:00Z"
last_activity: 2026-03-17 — 8 CF workflows deployed to Sese-AI n8n, env vars loaded
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 11
  completed_plans: 10
  percent: 83
---

# Project State

## Current Position

Phase: 7 of 7 (Orchestration) — PLANNING
Plan: 0 of ? in current phase
Status: Starting Phase 7 planning
Last activity: 2026-03-17 — Phase 6 complete, Plane synced

Progress: [████████░░] 83% (overall)

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-17)

**Core value:** Produire du contenu de qualite studio avec un workflow professionnel (14 etapes, 4 gates) pilotable depuis Telegram, avec invalidation ciblee par scene.
**Current focus:** Phase 7 — Orchestration (n8n workflows, Kitsu webhooks, editorial calendar)

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 4min
- Total execution time: 22min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 05 | 3 | 15min | 5min |
| 06 | 3 | 7min | 2.3min |
| Phase 07-orchestration P02 | 8 | 2 tasks | 2 files |
| Phase 07-orchestration P01 | 2 | 2 tasks | 2 files |
| Phase 07 P03 | 4 | 3 tasks | 7 files |
| Phase 07-orchestration P04 | 5 | 2 tasks | 3 files |

## Accumulated Context

| Phase 05 P01 | 4min | 2 tasks | 15 files |
| Phase 05 P02 | 6min | 2 tasks | 6 files |
| Phase 05 P03 | 5min | 2 tasks | 6 files + API provisioning |
| Phase 06 P01 | 4min | 2 tasks | 8 files |
| Phase 06 P02 | 3min | 2 tasks | 2 files |
| Phase 06 P03 | 9min | 1 task | 1 file + deploy |

### Decisions

- PRD complete: `docs/PRD-CONTENT-FACTORY.md` (4 phases, 14 steps, Kitsu mapping, provider costs)
- Plane project created with 3 modules and 16 work items
- Fal.ai API key added to Ansible vault
- Kitsu subdomain `boss` added to main.yml
- Brand: Paul Taff (Flash Studio), sarcastic tone, Instagram first
- Telegram topic 7 for content-director skill
- ElevenLabs skipped Phase 1
- [Phase 05]: Kitsu role created: supervisord override disables internal PG/Redis, shared postgresql_password for zou user
- [Phase 05]: Docker healthcheck uses shallow /api/health; deep DB check via zou upgrade-db in provision
- [Phase 05]: Added nocodb to backup dump loop (was missing from original pre-backup.sh)
- [Phase 05]: NocoDB FK fields as SingleLineText (API v2 limitation, FK deferred to UI/Phase 7)
- [Phase 05]: Qdrant vector_size/distance parameterized via role defaults, not hardcoded
- [Phase 05]: LiteLLM internal endpoint (http://litellm:4000) for on-server embedding generation
- [Phase 05]: Admin user is seko.mobutoo@gmail.com (pre-existing), bot "Mobotoo" (javisi.bot@gmail.com) created for API automation
- [Phase 05]: Zou default VFX task types coexist with 14 CF custom types — can be archived later
- [Phase 05]: Custom status "Generating" added for AI pipeline steps
- [Phase 06]: All NocoDB/Kitsu CRUD delegated to n8n webhooks (agent sandbox has no direct API secrets)
- [Phase 06]: 5 CF webhooks defined: cf-create-content, cf-update-content, cf-read-content, cf-scene, cf-kitsu-sync
- [Phase 06]: Contenu topic routes to marketer agent (topic 7)
- [Phase 06]: All Reel compositions use uniform ReelProps interface (scenes[], brand, audio?) for n8n integration
- [Phase 06]: Default durationInFrames overridable via inputProps at render time
- [Phase 06]: Pre-existing tsc errors in Root.tsx/server/render-queue left untouched (out of scope)
- [Phase 06]: Tailscale VPN IP (100.64.0.14) used for Sese-AI deploy (public IP unreachable)
- [Phase 06]: Remotion handler fixed: state: restarted -> state: present + recreate: always (was not picking up new images)
- [Phase 07-02]: Sequential dispatch with 2s delay in cf-generate-assets to protect local ComfyUI/Remotion from concurrent overload
- [Phase 07-02]: Motion keyword detection drives provider routing per scene (remotion for animation, comfyui for static, seedream as fallback)
- [Phase 07-02]: cf-rough-cut validates ALL scenes ready before Remotion render to avoid partial renders
- [Phase 07-orchestration]: gpt-4o-mini for creative steps (concept+hook, script writing); deepseek-v3 for all research/metadata steps
- [Phase 07-orchestration]: Non-blocking try/catch on NocoDB/Kitsu sync steps — pipeline must not abort if storage fails
- [Phase 07]: cf-kitsu-sync uses internal Docker URL http://kitsu:80 to avoid VPN/Caddy layer
- [Phase 07]: Zou event handler re-authenticates every call (no token caching) per research Pitfall 2
- [Phase 07]: event_handler.py uses stdlib only (urllib) -- no pip dependencies needed in Zou environment
- [Phase 07-orchestration]: cf-kitsu-sync uses template task (not copy loop) — Jinja2 vars require ansible.builtin.template, not ansible.builtin.copy
- [Phase 07-orchestration]: Plane IDs in n8n.env.j2 use Ansible variables with | default('') — not hardcoded (plane_cf_project_id, plane_cf_module_id)

### Kitsu IDs (downstream reference)

| Entity | ID |
|--------|-----|
| Production | `19b9faf4-f7c4-4829-9739-cbf7c3181941` |
| Episode "Drop 1" | `e5deb971-7b45-4cde-9f79-b1de84303a72` |
| Seq Pre-production | `afd7480d-5571-4b31-96e3-2248cc3a165a` |
| Seq Ecriture | `933f8e43-d5d3-4652-9645-ee4585093411` |
| Seq Production | `17d5a100-d6ac-4ca7-a476-7381b75966d6` |
| Seq Post-production | `682662ad-fd17-46c5-b8b6-5240b3b061b5` |
| Bot Mobotoo | `7a7e6854-7b12-4650-906a-e6c3f9da82e2` |

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-17T21:56:03.665Z
Stopped at: Completed 07-04-PLAN.md — calendar sync workflow + Ansible registration of all 8 CF workflows
Resume file: None
