---
phase: 07-orchestration
plan: 03
subsystem: n8n-workflows
tags: [n8n, kitsu, invalidation, zou, event-handler, content-factory]
dependency_graph:
  requires: [cf-scene, cf-update-content]
  provides: [cf-invalidation-engine, cf-kitsu-sync, cf-kitsu-inbound, zou-event-handler]
  affects: [kitsu-role, docker-stack, n8n-provision]
tech_stack:
  added: []
  patterns:
    - Jinja2 template wrapping for n8n workflow with Ansible variables
    - Zou event handler loaded from EVENT_HANDLERS_FOLDER
    - Internal Docker networking for service-to-service calls (http://kitsu:80)
    - Best-effort forwarding (never crash Zou if n8n is down)
key_files:
  created:
    - roles/n8n-provision/files/workflows/cf-invalidation-engine.json
    - roles/n8n-provision/templates/workflows/cf-kitsu-sync.json.j2
    - roles/n8n-provision/files/workflows/cf-kitsu-inbound.json
    - roles/kitsu/templates/event_handler.py.j2
  modified:
    - roles/kitsu/tasks/main.yml
    - roles/kitsu/templates/kitsu.env.j2
    - roles/docker-stack/templates/docker-compose.yml.j2
decisions:
  - cf-kitsu-sync uses internal Docker URL http://kitsu:80 (not external boss.<domain>) to avoid VPN/Caddy layer
  - Zou event handler re-authenticates on every n8n execution (no token caching per Pitfall 2 from research)
  - event_handler.py.j2 uses urllib only (no dependencies) — works in Zou's Python env without pip install
  - comment:new event logged only in v1 — OpenClaw integration deferred to v2
  - EVENT_HANDLERS_FOLDER volume mount is read-only (:ro) in docker-compose
metrics:
  duration: 4min
  completed_date: "2026-03-17"
  tasks_completed: 3
  files_created: 4
  files_modified: 3
---

# Phase 7 Plan 03: Feedback Loop Workflows Summary

**One-liner:** Targeted scene invalidation engine with full cascade matrix + bidirectional Kitsu sync via Zou event handler

## What Was Built

### Task 1 — cf-invalidation-engine.json
Static n8n workflow (FLOW-06) for targeted scene invalidation:
- Validates X-Webhook-Secret on all requests
- Full INVALIDATION_MAP constant for steps 1-9 (steps 10-14 are terminal/output)
- Single-scene mode: step 7 invalidates only that scene's asset + montage; step 9 invalidates montage only
- Calls `cf-scene` list_scenes to find affected scenes, then invalidate_scene for each
- Updates content `current_step` and `status: reworking` via `cf-update-content`
- Syncs Kitsu retake status for all invalidated steps via `cf-kitsu-sync`
- Response includes `scenes_invalidated` and `scenes_preserved` counts for `/impact` command

### Task 2 — cf-kitsu-sync.json.j2
Jinja2 template workflow (FLOW-02) for bidirectional Kitsu sync:
- 4 action handlers via Switch node: `update_task_status`, `create_shot`, `upload_preview`, `add_comment`
- Re-authenticates with Zou API on every execution (fresh JWT per call)
- Status mapping: wip/done/retake/invalidated/generating -> Kitsu task status names
- `{% raw %}...{% endraw %}` blocks wrap all n8n expressions; `{{ kitsu_subdomain }}` breakout for reference comments
- Uses internal Docker URL `http://kitsu:80` throughout

### Task 3 — cf-kitsu-inbound.json + Zou event handler (FLOW-07)
- `cf-kitsu-inbound.json`: n8n webhook receiver for Zou events
  - Switch routing: task:status-changed, preview-file:new, comment:new
  - status-changed: syncs to NocoDB via cf-update-content
  - preview-file:new: attaches preview URL to content record
  - comment:new: logged (v2 OpenClaw integration planned)
- `event_handler.py.j2`: Python script Zou loads from EVENT_HANDLERS_FOLDER
  - Uses `{{ project_name }}_n8n:5678` internal Docker hostname
  - Uses stdlib only (`json`, `urllib.request`) — no pip dependencies
  - Filters to only forward relevant CF events; ignores all others
- Ansible additions:
  - `kitsu/tasks/main.yml`: creates event_handlers dir, templates event_handler.py
  - `kitsu.env.j2`: adds `EVENT_HANDLERS_FOLDER=/opt/zou/event_handlers`
  - `docker-compose.yml.j2`: mounts event_handlers dir into kitsu container (read-only)

## Verification

All automated checks passed:
- `cf-invalidation-engine.json`: valid JSON, 8 nodes, INVALIDATION_MAP constant present, cf-invalidation-engine webhook path
- `cf-kitsu-sync.json.j2`: valid Jinja2 template (raw/endraw blocks), renders to valid JSON with 9 nodes, cf-kitsu-sync webhook path
- `cf-kitsu-inbound.json`: valid JSON, cf-kitsu-inbound webhook path
- `event_handler.py.j2`: handle_event function + cf-kitsu-inbound URL present
- `source .venv/bin/activate && make lint`: PASSED (0 failures, 0 warnings, 135 files)

## Deviations from Plan

### Auto-added: EVENT_HANDLERS_FOLDER infrastructure

**Found during:** Task 3

**Issue:** Plan specified "Deploy event handler via Ansible" and "Mount the directory as EVENT_HANDLERS_FOLDER in the Kitsu container via docker-compose" but did not explicitly list `kitsu.env.j2` and `docker-compose.yml.j2` in modified files.

**Fix:** Added `EVENT_HANDLERS_FOLDER` env var to `kitsu.env.j2` and added volume mount to `docker-compose.yml.j2` — both required for Zou to actually load the event handler script.

**Rule:** Rule 2 (auto-add missing critical functionality for correct operation)

**Files modified:** `roles/kitsu/templates/kitsu.env.j2`, `roles/docker-stack/templates/docker-compose.yml.j2`

**Commit:** a986a5b

## Commits

| Task | Commit | Files |
|------|--------|-------|
| 1 — cf-invalidation-engine | 663abd3 | roles/n8n-provision/files/workflows/cf-invalidation-engine.json |
| 2 — cf-kitsu-sync template | 507c013 | roles/n8n-provision/templates/workflows/cf-kitsu-sync.json.j2 |
| 3 — cf-kitsu-inbound + event handler | a986a5b | 5 files (workflow + py template + ansible tasks + env + compose) |

## Self-Check: PASSED
