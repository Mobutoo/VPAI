---
phase: 07-orchestration
plan: 02
subsystem: workflows
tags: [n8n, content-factory, remotion, comfyui, seedream, creative-pipeline]

# Dependency graph
requires:
  - phase: 07-01
    provides: cf-create-content, cf-update-content, cf-read-content, cf-scene, cf-kitsu-sync webhooks
  - phase: 06-03
    provides: creative-pipeline webhook with ComfyUI/Remotion/Seedance provider routing
  - phase: 06-01
    provides: Remotion compositions (ReelMotionText, ReelMemeSkit, ReelFeatureShowcase, ReelTeaser) with ReelProps interface
provides:
  - cf-generate-assets webhook — per-scene provider dispatch to creative-pipeline
  - cf-rough-cut webhook — full Remotion video assembly from completed scene assets
affects: [07-03, 07-04, 07-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sequential dispatch pattern with 2s delay to avoid overwhelming local ComfyUI/Remotion"
    - "Motion keyword detection for provider routing (ComfyUI vs Remotion per scene)"
    - "Non-fatal error handling for NocoDB/Kitsu sync failures (log + continue)"
    - "Pending scene validation guard before Remotion render (fail fast with structured error)"

key-files:
  created:
    - roles/n8n-provision/files/workflows/cf-generate-assets.json
    - roles/n8n-provision/files/workflows/cf-rough-cut.json
  modified: []

key-decisions:
  - "Sequential scene dispatch (not parallel) with 2s delay to protect local ComfyUI and Remotion from overload"
  - "Motion keyword list (animation, motion, zoom, pan, etc.) determines Remotion vs ComfyUI assignment per scene"
  - "Pending scenes validation throws structured JSON error so callers can parse pending_scenes list"
  - "NocoDB/Kitsu sync errors are non-fatal (try/catch with console.error) — pipeline correctness > status accuracy"
  - "rough-cut validates ALL scenes ready before triggering Remotion to avoid partial renders"
  - "executionTimeout 600s on both workflows to handle long Remotion renders"

patterns-established:
  - "Provider assignment: motion keywords -> remotion, explicit comfyui -> comfyui, default -> seedream"
  - "Format-to-composition map: reel-motion-text -> ReelMotionText, reel-meme-skit -> ReelMemeSkit, etc."
  - "ReelProps construction: durationInFrames = duration * 30 (30fps), type from .mp4 extension check"

requirements-completed: [FLOW-04, FLOW-05]

# Metrics
duration: 8min
completed: 2026-03-17
---

# Phase 07 Plan 02: Media Production Workflows Summary

**Two n8n workflows for visual production: per-scene provider dispatch (ComfyUI/Remotion/Seedream) and Remotion rough-cut assembly from completed scene assets**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-17T21:46:43Z
- **Completed:** 2026-03-17T21:54:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- cf-generate-assets: reads scenes from NocoDB, assigns provider per scene via motion keyword detection, dispatches sequentially to creative-pipeline with 2s delay, updates NocoDB + Kitsu step 9
- cf-rough-cut: validates all scenes generated, builds ReelProps (30fps, type from extension), triggers Remotion render via creative-pipeline, stores rough_cut_url, uploads preview to Kitsu step 10
- Both workflows validate X-Webhook-Secret via N8N_WEBHOOK_HMAC_SECRET env var

## Task Commits

Each task was committed atomically:

1. **Task 1: Create cf-generate-assets workflow** - `d68894a` (feat)
2. **Task 2: Create cf-rough-cut workflow** - `ccab6b5` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `roles/n8n-provision/files/workflows/cf-generate-assets.json` - Per-scene asset dispatch: validates secret, loads content+scenes from NocoDB, assigns providers (motion keywords -> Remotion, static -> ComfyUI/Seedream), dispatches sequentially to creative-pipeline, updates NocoDB + Kitsu
- `roles/n8n-provision/files/workflows/cf-rough-cut.json` - Rough-cut assembly: validates all scenes ready, builds ReelProps, triggers Remotion via creative-pipeline, stores URL, uploads Kitsu preview

## Decisions Made

- Sequential dispatch with 2s delay to protect local ComfyUI and Remotion from concurrent overload
- Motion keyword list (animation, motion, zoom, pan, slide, rotate, etc.) drives provider routing per scene
- Pending scenes validation in rough-cut throws structured JSON error with pending_scenes list for caller parsing
- NocoDB/Kitsu sync errors wrapped in try/catch (non-fatal) — production correctness is not blocked by analytics failures
- executionTimeout: 600 on both workflows for long renders

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- cf-generate-assets and cf-rough-cut ready for Ansible deployment via n8n-provision role
- Both workflows delegate provider routing to creative-pipeline (already deployed Phase 06)
- Ready for Phase 07-03: Telegram orchestration and editorial calendar workflows

---
*Phase: 07-orchestration*
*Completed: 2026-03-17*
