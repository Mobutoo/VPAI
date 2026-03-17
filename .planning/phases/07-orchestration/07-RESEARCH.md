# Phase 7: Orchestration - Research

**Researched:** 2026-03-17
**Domain:** n8n workflow orchestration, Kitsu webhook integration, Plane editorial calendar
**Confidence:** MEDIUM-HIGH

## Summary

Phase 7 wires together all building blocks from Phases 5-6 into a working end-to-end content production pipeline. The work is primarily n8n workflow JSON authoring (6 workflows), a Kitsu webhook integration script, and a Plane calendar sync workflow. All infrastructure is already deployed -- this phase creates the orchestration logic only.

The existing codebase has a mature pattern for n8n workflow deployment via Ansible (checksum-based idempotent import in `roles/n8n-provision/tasks/main.yml`). New workflows follow this exact pattern: JSON files in `roles/n8n-provision/files/workflows/` or `.j2` templates, registered in the task loop, deployed via `n8n import:workflow`. The creative-pipeline workflow already handles provider dispatch (ComfyUI/Remotion/Seedance/cloud), which `generate-assets` will reuse.

**Primary recommendation:** Build workflows incrementally -- brief-to-concept first (proves NocoDB CRUD + LLM chain), then script-to-storyboard, then generate-assets + rough-cut (reuses creative-pipeline), then invalidation-engine, then kitsu-sync + calendar. Each workflow is an independent n8n JSON file deployed via the existing Ansible provisioning pipeline.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FLOW-01 | n8n workflow `brief-to-concept` orchestrates steps 1-5 | LLM chain via LiteLLM internal endpoint, NocoDB CRUD via existing webhook patterns, Qdrant brand-voice search |
| FLOW-02 | n8n workflow `kitsu-sync` uploads previews and updates task statuses | Zou REST API for task status updates and preview file uploads, auth via JWT token |
| FLOW-03 | n8n workflow `script-to-storyboard` orchestrates steps 6-8 | LLM chain for script generation, scene decomposition into NocoDB scenes table |
| FLOW-04 | n8n workflow `generate-assets` dispatches to correct provider per scene | Reuses creative-pipeline.json.j2 pattern (ComfyUI/Remotion/Fal.ai/Seedance routing) |
| FLOW-05 | n8n workflow `rough-cut` assembles scenes via Remotion | Remotion render-queue API at localhost:3200/render, ReelProps interface with scenes[] |
| FLOW-06 | n8n workflow `invalidation-engine` handles targeted scene invalidation | Invalidation matrix defined in SKILL.md.j2, NocoDB scene status updates via cf-scene webhook |
| FLOW-07 | Kitsu webhooks to n8n integration | Zou events: task:status-changed, comment:new, preview-file:new -- configured via EVENT_HANDLERS_FOLDER or external webhook |
| CAL-01 | Editorial calendar visible in Plane (contents = work items with dates) | Plane API v1 POST /work-items/ with start_date, target_date fields |
| CAL-02 | Drops organized as Plane cycles | Plane API v1 POST /cycles/ with name, start_date, end_date |
| CAL-03 | n8n auto-creates Plane work items from NocoDB content entries | NocoDB webhook on row create -> n8n -> Plane API work item creation |
</phase_requirements>

## Standard Stack

### Core (already deployed)

| Component | Version | Purpose | Integration Point |
|-----------|---------|---------|-------------------|
| n8n | 2.7.3 (custom enterprise) | Workflow orchestration | All CF workflows run here |
| NocoDB | 0.301.2 | Source of truth (contents, scenes) | CRUD via existing cf-* webhooks |
| Kitsu/Zou | cgwire:1.0.17 | Production tracking, previews | REST API + event handlers |
| Remotion | localhost:3200 | Video assembly | render-queue.ts /render endpoint |
| LiteLLM | v1.81.3-stable | LLM proxy (internal) | http://litellm:4000/v1/ |
| Qdrant | v1.16.3 | Brand voice search | http://qdrant:6333/ |
| Plane | v1.2.2 | Editorial calendar | REST API v1 at work.ewutelo.cloud |

### Supporting

| Component | Purpose | When Used |
|-----------|---------|-----------|
| ComfyUI (Waza) | Local image generation | generate-assets for image scenes |
| Fal.ai (cloud) | Cloud video/image generation | generate-assets fallback |
| Seedance (BytePlus) | AI video generation | generate-assets for cinematic scenes |

### No New Dependencies

This phase adds zero new services. All work is n8n workflow JSON files + Ansible registration.

## Architecture Patterns

### Workflow File Structure

```
roles/n8n-provision/
  files/workflows/
    cf-brief-to-concept.json         # FLOW-01 (steps 1-5)
    cf-script-to-storyboard.json     # FLOW-03 (steps 6-8)
    cf-generate-assets.json          # FLOW-04 (per-scene dispatch)
    cf-rough-cut.json                # FLOW-05 (Remotion assembly)
    cf-invalidation-engine.json      # FLOW-06 (targeted invalidation)
    cf-calendar-sync.json            # CAL-01, CAL-02, CAL-03
  templates/workflows/
    cf-kitsu-sync.json.j2            # FLOW-02, FLOW-07 (needs Jinja2 vars for Kitsu URL)
```

### Pattern 1: n8n Workflow JSON Deployment (existing)

**What:** Each workflow is a self-contained JSON file imported via `n8n import:workflow` CLI
**When to use:** All new workflows follow this pattern

Deployment flow (already coded in `roles/n8n-provision/tasks/main.yml`):
1. Copy JSON to server `/tmp/`
2. Checksum comparison against stored `.md5`
3. If changed: delete old -> import new -> publish -> store new checksum
4. Restart n8n if any workflow updated

**Action required:** Add each new workflow to:
- The `copy` loop (line ~264)
- The `checksum comparison` loop (line ~321)
- The `store checksums` loop (line ~508)
- The cleanup loop (line ~566)

### Pattern 2: Webhook-Triggered Workflow

**What:** Workflow starts with n8n Webhook node, receives JSON payload, processes, responds
**When to use:** cf-create-content, cf-update-content, cf-read-content, cf-scene, cf-kitsu-sync (Phase 6 patterns)
**Existing examples:** All 5 CF webhooks defined in Phase 6

New webhooks for Phase 7:
- `cf-brief-to-concept` -- triggered by OpenClaw after /content command creates initial content
- `cf-script-to-storyboard` -- triggered after gate 1 locked
- `cf-generate-assets` -- triggered after gate 2 locked
- `cf-rough-cut` -- triggered after all scene assets generated
- `cf-invalidation-engine` -- triggered by OpenClaw /back or /adjust commands

### Pattern 3: LLM Chain in n8n

**What:** n8n Code node calls LiteLLM internal endpoint for AI text generation
**When to use:** brief-to-concept (steps 1-5), script-to-storyboard (steps 6-8)

```javascript
// In n8n Code node — call LiteLLM for text generation
const response = await $http.request({
  method: 'POST',
  url: 'http://litellm:4000/v1/chat/completions',
  headers: {
    'Authorization': `Bearer ${$env.LITELLM_API_KEY}`,
    'Content-Type': 'application/json'
  },
  body: {
    model: 'gpt-4o-mini',  // or budget model
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt }
    ],
    max_tokens: 2000,
    temperature: 0.7
  }
});
return [{ json: { result: response.choices[0].message.content } }];
```

**Budget note:** Use eco models (qwen3-coder, deepseek-v3) for non-creative steps (research, metadata). Use gpt-4o-mini or claude-sonnet for creative writing (script, concept).

### Pattern 4: Kitsu REST API Integration

**What:** n8n HTTP Request nodes call Zou API for task status updates and preview uploads
**When to use:** kitsu-sync workflow

```
Authentication:
  POST /api/auth/login -> JWT access_token
  Header: Authorization: Bearer <token>

Key endpoints:
  GET  /api/data/tasks?project_id=<id>       # List tasks
  PUT  /api/data/tasks/<task_id>              # Update task
  POST /api/actions/tasks/<task_id>/comment   # Add comment
  POST /api/pictures/preview-files/<task_id>  # Upload preview file
  PUT  /api/data/tasks/<task_id>/status       # Change task status
```

**Important:** Kitsu auth tokens expire. The workflow must re-authenticate per execution or cache token with TTL.

### Pattern 5: Plane API Integration

**What:** n8n HTTP Request nodes call Plane API for work item and cycle management
**When to use:** calendar-sync workflow

```
Authentication:
  Header: X-API-Key: <plane_admin_api_token>

Create work item:
  POST /api/v1/workspaces/{slug}/projects/{project_id}/work-items/
  Body: { "name": "...", "start_date": "YYYY-MM-DD", "target_date": "YYYY-MM-DD", "module": "<module_id>" }

Create cycle (drop):
  POST /api/v1/workspaces/{slug}/projects/{project_id}/cycles/
  Body: { "name": "Drop 1", "owned_by": "<user_id>", "project_id": "<id>", "start_date": "...", "end_date": "..." }

Add work items to cycle:
  POST /api/v1/workspaces/{slug}/projects/{project_id}/cycles/{cycle_id}/cycle-issues/
  Body: { "issues": ["<work_item_id_1>", "<work_item_id_2>"] }
```

**Known IDs from config:**
- Workspace slug: `ewutelo`
- CF project ID: `e0cb95f0-0ea5-41b8-a3e3-aec45e8cc37e`
- CF module ID: `c04ac29e-9842-4eec-8ff6-6923e9fe75d7`

### Anti-Patterns to Avoid

- **Monolithic workflow:** Do NOT build one giant workflow for all 14 steps. Each n8n workflow should handle one logical unit (brief-to-concept, script-to-storyboard, etc.)
- **Polling Kitsu:** Do NOT poll Kitsu for status changes. Use Zou event handlers (EVENT_HANDLERS_FOLDER) that POST to n8n webhooks on events.
- **Hardcoded IDs:** Do NOT hardcode NocoDB table IDs, Kitsu project IDs, or Plane IDs. Use n8n environment variables or Ansible template variables.
- **Synchronous asset generation:** Do NOT wait synchronously for Fal.ai/Seedance. Use async pattern: dispatch -> store pending -> poll/callback for completion.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM text generation | Custom API client | LiteLLM internal endpoint (http://litellm:4000) | Already proxies all providers, handles budget, retries |
| Image/video dispatch | New provider routing | Existing creative-pipeline.json.j2 workflow | Already routes ComfyUI vs cloud, normalizes output |
| NocoDB CRUD | Direct NocoDB API calls | Existing cf-* webhook endpoints | Already handle auth, validation, error handling |
| Scene invalidation logic | Custom invalidation code | Matrix in content-director SKILL.md.j2 | Already defined, agent uses it for /impact |
| n8n workflow deployment | Manual import | Existing n8n-provision Ansible role | Checksum-based idempotent deploy already works |

## Common Pitfalls

### Pitfall 1: n8n Webhook Secret Validation

**What goes wrong:** Workflows accept unauthenticated requests
**Why it happens:** Forgetting to validate `X-Webhook-Secret` header in the webhook trigger
**How to avoid:** Every CF webhook MUST validate `$input.first().json.secret === process.env.N8N_WEBHOOK_SECRET` in the first Code node
**Warning signs:** Workflow triggers from unexpected sources

### Pitfall 2: Kitsu Auth Token Expiry

**What goes wrong:** kitsu-sync fails with 401 after token expires
**Why it happens:** Zou JWT tokens have limited lifetime (default 2 hours)
**How to avoid:** Re-authenticate at the start of each workflow execution, never cache tokens between runs
**Warning signs:** Intermittent 401 errors in kitsu-sync

### Pitfall 3: Async Provider Responses (Seedance/Fal.ai)

**What goes wrong:** generate-assets workflow times out waiting for cloud video generation
**Why it happens:** Seedance video generation takes 60-180 seconds, Fal.ai can be similar
**How to avoid:** Use polling loop pattern: submit job -> wait with exponential backoff -> collect result. Set n8n workflow timeout to 600s for generate-assets.
**Warning signs:** Timeouts on cloud provider HTTP requests

### Pitfall 4: NocoDB FK Fields as SingleLineText

**What goes wrong:** Trying to use relational queries on brand_id or content_id
**Why it happens:** Phase 5 decision: NocoDB API v2 limitation requires FK fields as SingleLineText
**How to avoid:** Always filter by text match, never assume FK resolution. Store IDs as plain strings.
**Warning signs:** Empty results when querying by FK

### Pitfall 5: n8n env_file Reload

**What goes wrong:** New environment variables not picked up after deploy
**Why it happens:** `docker compose restart` does NOT reload env_file (documented in CLAUDE.md)
**How to avoid:** Use `state: present` + `recreate: always` for n8n handler
**Warning signs:** $env.NEW_VAR returns undefined in n8n Code nodes

### Pitfall 6: Remotion Render on ARM64 (Waza)

**What goes wrong:** Remotion render fails or is extremely slow
**Why it happens:** RPi5 has limited resources for Chromium-based rendering
**How to avoid:** Keep Remotion renders lightweight (motion design, not heavy 3D). Use `disableSandbox: true` (already configured). Set render timeout to 300s.
**Warning signs:** OOM kills, render timeouts

### Pitfall 7: Plane v1.2.2 API Compatibility

**What goes wrong:** API endpoints return 404 or unexpected response format
**Why it happens:** Plane API docs are for latest version, self-hosted is v1.2.2
**How to avoid:** Use the same API patterns proven in provision-plane.sh.j2. Test each endpoint manually before building workflow.
**Warning signs:** 404/405 on documented endpoints

## Code Examples

### n8n Workflow JSON Structure (verified from existing codebase)

```json
{
  "name": "CF Brief to Concept",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "cf-brief-to-concept",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "unique-uuid",
      "name": "Webhook Trigger",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [260, 380]
    }
  ],
  "connections": {},
  "settings": {
    "executionOrder": "v1",
    "saveDataSuccessExecution": "all",
    "saveDataErrorExecution": "all"
  },
  "tags": [{ "name": "content-factory" }],
  "triggerCount": 1
}
```

### Kitsu Task Status Update via Zou API

```javascript
// n8n HTTP Request node configuration
// Step 1: Authenticate
const auth = await $http.request({
  method: 'POST',
  url: `http://${kitsuHost}/api/auth/login`,
  body: { email: kitsuEmail, password: kitsuPassword }
});
const token = auth.access_token;

// Step 2: Update task status
await $http.request({
  method: 'PUT',
  url: `http://${kitsuHost}/api/actions/tasks/${taskId}/comment`,
  headers: { 'Authorization': `Bearer ${token}` },
  body: {
    task_status_id: newStatusId,
    comment: 'Status updated by Content Factory pipeline'
  }
});
```

### Plane Work Item Creation

```javascript
// n8n HTTP Request node
const workItem = await $http.request({
  method: 'POST',
  url: `https://work.ewutelo.cloud/api/v1/workspaces/ewutelo/projects/${projectId}/work-items/`,
  headers: {
    'X-API-Key': planeApiToken,
    'Content-Type': 'application/json'
  },
  body: {
    name: contentTitle,
    description_html: `<p>Format: ${format}</p><p>Status: ${status}</p>`,
    start_date: createdDate,
    target_date: publishDate,
    module: moduleId
  }
});
```

### Invalidation Engine Logic

```javascript
// Invalidation matrix (from SKILL.md.j2)
const INVALIDATION_MAP = {
  1: [2,3,4,5,6,7,8,9,10,11,12,13,14],  // Brief -> EVERYTHING
  2: [3,4,6,7,9,10,11],                    // Recherche -> downstream
  3: [4,6,7,9,10,11],                       // Moodboard
  4: [6,7,9,10,11],                          // Concept/Hook
  5: [6,7,9],                                 // Casting -> script dialogues, storyboard, assets with chars
  6: [7,9,10,11],                             // Script
  7: [],                                       // Single scene -> only that scene's assets
  8: [10,11],                                  // Sound design -> montage only
  9: [10,11],                                   // Single asset -> montage portion
};

// For step 7 (storyboard scene change), invalidate only the specific scene
// Not the full storyboard — check scene_number and invalidate matching asset + montage portion
```

## Zou Event Types (verified from source code)

Key events for CF integration (from `zou/app/services/tasks_service.py` and `comments_service.py`):

| Event | Payload | CF Usage |
|-------|---------|----------|
| `task:status-changed` | `{task_id, new_task_status_id, previous_task_status_id, person_id}` | Trigger kitsu-sync when task moves to done/retake |
| `task:new` | `{task_id}` | Sync new task to NocoDB |
| `task:update` | `{task_id}` | Generic task update |
| `comment:new` | `{comment_id, task_id, task_status_id}` | Extract feedback, send to OpenClaw |
| `preview-file:new` | `{preview_file_id, comment_id}` | Notify Telegram with preview link |
| `task:assign` | `{task_id, person_id}` | Not used initially |

**Configuration:** Set `EVENT_HANDLERS_FOLDER=/opt/zou/event_handlers` in Kitsu container env. Create Python handler that POSTs to n8n webhook.

Alternative: Kitsu UI supports webhook configuration (Settings > Webhooks) which is simpler to manage.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| n8n executeWorkflow sub-workflows | Webhook triggers between workflows | n8n 2.x | Each workflow is independently deployable and testable |
| Kitsu polling from n8n | Zou event handlers -> n8n webhooks | Kitsu 1.0+ | Real-time, no wasted API calls |
| Plane issues API | Plane work-items API | Plane v0.23+ | Work items replace issues terminology |

## Open Questions

1. **Kitsu webhook configuration method**
   - What we know: Two options -- EVENT_HANDLERS_FOLDER (Python scripts) or Kitsu UI webhook config
   - What's unclear: Whether the cgwire:1.0.17 Docker image supports UI webhook configuration out of the box
   - Recommendation: Try UI webhooks first (simpler). Fall back to EVENT_HANDLERS_FOLDER Python scripts if UI not available. Either way, the n8n side is the same (webhook trigger).

2. **Plane v1.2.2 cycle API availability**
   - What we know: Plane docs show cycle API, provision script works with v1.2.2
   - What's unclear: Whether cycle endpoints existed in v1.2.2 (cycles may be a later feature)
   - Recommendation: Test `GET /api/v1/workspaces/ewutelo/projects/<id>/cycles/` manually first. If 404, create cycles via Plane UI and only sync work items programmatically.

3. **Fal.ai async response pattern**
   - What we know: Fal.ai and Seedance are async (return task_id, need polling)
   - What's unclear: Exact polling endpoints and response format for each provider
   - Recommendation: Build generate-assets with synchronous providers first (ComfyUI, Remotion). Add async cloud providers in a second pass with polling loop.

## Validation Architecture

> nyquist_validation not explicitly set to false -- including section.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Ansible Molecule + manual smoke tests |
| Config file | roles/n8n-provision/molecule/default/molecule.yml |
| Quick run command | `source .venv/bin/activate && make lint` |
| Full suite command | `source .venv/bin/activate && make lint && ansible-playbook playbooks/site.yml --check --diff` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FLOW-01 | brief-to-concept workflow executes steps 1-5 | smoke | `curl -X POST https://mayi.ewutelo.cloud/webhook/cf-brief-to-concept -H 'Content-Type: application/json' -d '{...}'` | Wave 0 |
| FLOW-02 | kitsu-sync updates task statuses | smoke | `curl -X POST .../webhook/cf-kitsu-sync -d '{...}'` | Wave 0 |
| FLOW-03 | script-to-storyboard generates scenes | smoke | `curl -X POST .../webhook/cf-script-to-storyboard -d '{...}'` | Wave 0 |
| FLOW-04 | generate-assets dispatches per scene | smoke | `curl -X POST .../webhook/cf-generate-assets -d '{...}'` | Wave 0 |
| FLOW-05 | rough-cut assembles via Remotion | smoke | `curl -X POST .../webhook/cf-rough-cut -d '{...}'` | Wave 0 |
| FLOW-06 | invalidation-engine cascades correctly | smoke | `curl -X POST .../webhook/cf-invalidation-engine -d '{...}'` | Wave 0 |
| FLOW-07 | Kitsu webhooks fire to n8n | manual-only | Trigger task status change in Kitsu UI, verify n8n execution | N/A |
| CAL-01 | Calendar visible in Plane | manual-only | Open Plane UI, check work items | N/A |
| CAL-02 | Drops as Plane cycles | manual-only | Open Plane UI, check cycles | N/A |
| CAL-03 | Auto-create Plane work items | smoke | Create content in NocoDB, verify Plane work item appears | Wave 0 |

### Sampling Rate

- **Per task commit:** `make lint`
- **Per wave merge:** `make lint && ansible-playbook playbooks/site.yml --check --diff`
- **Phase gate:** Full deploy + manual smoke test of all workflows

### Wave 0 Gaps

- [ ] All 7 new workflow JSON files (cf-brief-to-concept, cf-script-to-storyboard, cf-generate-assets, cf-rough-cut, cf-invalidation-engine, cf-kitsu-sync, cf-calendar-sync)
- [ ] n8n-provision/tasks/main.yml updates (register new workflows in deploy loops)
- [ ] Kitsu webhook handler setup (EVENT_HANDLERS_FOLDER or UI config)
- [ ] Plane API credentials in n8n environment (if not already present)

## Sources

### Primary (HIGH confidence)

- Zou source code `zou/app/services/tasks_service.py` - All task-related event types (14 events)
- Zou source code `zou/app/services/comments_service.py` - Comment event types (7 events)
- Plane API docs at developers.plane.so - Cycle and work item endpoints
- Existing codebase: `roles/n8n-provision/tasks/main.yml` - Workflow deployment pattern
- Existing codebase: `roles/n8n-provision/templates/workflows/creative-pipeline.json.j2` - Provider dispatch pattern
- Existing codebase: `roles/openclaw/templates/skills/content-director/SKILL.md.j2` - All webhook URLs, invalidation matrix

### Secondary (MEDIUM confidence)

- Zou REST API docs at zou.cg-wire.com - Task status update endpoints
- Plane API v1 docs - Work item creation parameters
- Kitsu dev docs at dev.kitsu.cloud - Webhook configuration

### Tertiary (LOW confidence)

- Kitsu UI webhook configuration - Not verified on cgwire:1.0.17 image
- Plane v1.2.2 cycle API - Not verified locally, docs are for latest

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all services already deployed and proven in Phases 5-6
- Architecture: HIGH - follows exact patterns from existing n8n-provision role
- Workflow logic: MEDIUM - LLM chain prompts and async provider handling need iteration
- Kitsu webhooks: MEDIUM - event types verified from source, configuration method unclear
- Plane calendar: MEDIUM - API documented but v1.2.2 compatibility not tested
- Pitfalls: HIGH - drawn from documented REX and project CLAUDE.md

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (stable services, no version changes expected)
