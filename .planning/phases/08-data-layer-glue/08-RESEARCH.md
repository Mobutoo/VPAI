# Phase 8: Data Layer Glue - Research

**Researched:** 2026-03-17
**Domain:** n8n webhook workflows (NocoDB CRUD proxy) + Kitsu project structure verification
**Confidence:** HIGH

## Summary

Phase 8 closes the most critical blocker identified in the v2026.3 milestone audit: the 4 NocoDB CRUD webhook workflows that every CF workflow calls but that were never implemented. The entire pipeline is dead without them -- `/content` triggers `cf-create-content` which returns 404.

The technical work is well-scoped: create 4 n8n webhook workflows (JSON files) that proxy CRUD operations to NocoDB's REST API v2, register them in the Ansible deploy loop, and deploy. Additionally, DATA-06 (Kitsu project structure) needs formal verification -- the code already exists in `kitsu-provision` role but was never marked complete.

**Primary recommendation:** Build 4 static JSON workflow files in `roles/n8n-provision/files/workflows/`, following the exact same pattern as existing CF workflows (webhook trigger + validate secret + action routing + NocoDB API call + respond). Register in Ansible loops. Deploy and smoke test.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-06 | Kitsu project structure mapped (Production=brand, Episode=drop, Sequence=phase, Shot=content, Task=step) | Already provisioned by `kitsu-provision` role (05-03). Needs formal verification that sentinel file was written and structure exists on Sese-AI. |
</phase_requirements>

## Standard Stack

### Core
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| n8n | 2.7.3 | Workflow engine hosting the webhook endpoints | Already deployed, all CF workflows use internal webhooks |
| NocoDB | 0.301.2 | Data store for brands/contents/scenes tables | Already deployed with API token in n8n env |
| NocoDB API v2 | v2 | REST CRUD on table records | Used by existing provisioning scripts |

### Supporting
| Component | Purpose | When Used |
|-----------|---------|-----------|
| Ansible (n8n-provision role) | Deploy workflow JSON files to n8n | Registration of new workflows in deploy pipeline |
| Zou REST API | Kitsu project structure verification | DATA-06 verification only |

### Alternatives Considered
None -- this is gap closure, not new architecture. The webhook pattern was already chosen in Phase 6.

## Architecture Patterns

### Existing n8n Webhook Pattern (MUST follow)

All 8 existing CF workflows follow the same structure. The 4 new CRUD webhooks MUST follow it identically:

```
Webhook Trigger (POST /webhook/cf-{name})
  -> Validate Secret (Code node: check $env.N8N_WEBHOOK_HMAC_SECRET)
  -> Route by Action (Switch node or Code node)
  -> Execute NocoDB API call (HTTP Request or Code node)
  -> Respond to Webhook (respondToWebhook node)
```

### Recommended Workflow Structure

Each of the 4 workflows is a standalone JSON file:

```
roles/n8n-provision/files/workflows/
  cf-create-content.json    # NEW
  cf-update-content.json    # NEW
  cf-read-content.json      # NEW
  cf-scene.json             # NEW
  cf-brief-to-concept.json  # existing
  cf-script-to-storyboard.json  # existing
  ...
```

### NocoDB API v2 Endpoints (from existing provisioning code)

The provisioning script (`provision-nocodb-tables.sh.j2`) already demonstrates the v2 API pattern:

| Operation | Method | Endpoint | Notes |
|-----------|--------|----------|-------|
| List records | GET | `/api/v2/meta/bases/{baseId}/tables/{tableId}/records` | Supports `where` filter, `limit`, `offset` |
| Create record | POST | `/api/v2/meta/bases/{baseId}/tables/{tableId}/records` | Body: field key-value JSON |
| Read record | GET | `/api/v2/meta/bases/{baseId}/tables/{tableId}/records/{rowId}` | Returns single record |
| Update record | PATCH | `/api/v2/meta/bases/{baseId}/tables/{tableId}/records` | Body: `{ "Id": rowId, ...fields }` |
| Filter syntax | - | `where=(field,op,value)` | ops: eq, neq, like, gt, lt, etc. |

**Authentication:** `xc-token: {TOKEN}` header with `$env.NOCODB_API_TOKEN`.

**Base URL:** `$env.NOCODB_BASE_URL` (already in n8n.env.j2 as `NOCODB_BASE_URL`).

### API Contract: What Each Caller Expects

Extracted from all existing CF workflows that call these 4 webhooks:

#### cf-create-content (called by content-director skill via OpenClaw)
```json
// INPUT (POST body)
{
  "secret": "<hmac_secret>",
  "brand_id": "<brand_row_id>",
  "title": "Flash Studio Launch",
  "format": "reel-motion-text",
  "brief": { "objective": "...", "constraints": "..." }
}
// EXPECTED OUTPUT
{
  "status": "ok",
  "content_id": "<new_nocodb_row_id>"
}
```

#### cf-read-content (called by cf-brief-to-concept, cf-script-to-storyboard, cf-generate-assets, cf-rough-cut)
```json
// INPUT (POST body)
{
  "secret": "<hmac_secret>",
  "action": "read_content",
  "content_id": "<content_row_id>"
}
// EXPECTED OUTPUT — full record fields at top level
{
  "content_id": "...",
  "brand_id": "...",
  "title": "...",
  "format": "reel",
  "status": "concept",
  "current_step": 5,
  "brief": "{...}",
  "step4_concept": "{...}",
  "step5_casting": "{...}",
  "brand_tone": "...",
  "brand_name": "...",
  "brand_palette": {...},
  "brand_typography": "..."
}
```
**Critical:** cf-brief-to-concept's "Read Brand Profile" node calls cf-read-content and expects brand fields (brand_tone, brand_name, brand_palette, brand_typography) in the response. This means cf-read-content must JOIN content + brand data or the content row must contain brand fields.

**Resolution options:**
1. cf-read-content reads content row, then reads brand row via brand_id, merges
2. Content row contains denormalized brand fields (set at creation time)

Option 1 is cleaner. The workflow should do a second NocoDB call to fetch brand data when `brand_id` is present.

#### cf-update-content (called by cf-brief-to-concept, cf-script-to-storyboard, cf-invalidation-engine, cf-rough-cut, cf-kitsu-inbound)

Two calling patterns exist:

**Pattern A: with action field** (cf-brief-to-concept, cf-script-to-storyboard)
```json
{
  "secret": "<hmac_secret>",
  "action": "update_content",
  "content_id": "<id>",
  "fields": {
    "current_step": 5,
    "status": "awaiting_validation",
    "step1_enhanced_brief": "{...}",
    "step4_concept": "{...}"
  }
}
```

**Pattern B: via header secret** (cf-invalidation-engine, cf-kitsu-inbound)
```json
// Headers: x-webhook-secret: <secret>
{
  "content_id": "<id>",
  "fields": {
    "current_step": 3,
    "status": "reworking"
  }
}
```

The workflow must accept BOTH patterns: secret in body OR in x-webhook-secret header, action field optional (defaults to "update_content").

#### cf-scene (called by cf-script-to-storyboard, cf-generate-assets, cf-rough-cut, cf-invalidation-engine)

Action-routed webhook handling 4 sub-actions:

```json
// create_scene (cf-script-to-storyboard)
{
  "secret": "<hmac_secret>",
  "action": "create_scene",
  "content_id": "<id>",
  "scene_number": 1,
  "description": "...",
  "duration": 5,
  "dialogue": "...",
  "action": "...",     // NOTE: field name collision with route action!
  "transition": "cut",
  "status": "pending",
  "provider": ""
}

// list_scenes (cf-generate-assets, cf-rough-cut, cf-invalidation-engine)
{
  "secret": "<hmac_secret>" | header,
  "action": "list_scenes",
  "content_id": "<id>"
}
// Returns: { "scenes": [...] }

// update_scene (cf-generate-assets)
{
  "secret": "<hmac_secret>",
  "action": "update_scene",
  "content_id": "<id>",
  "scene_number": 1,
  "asset_url": "https://...",
  "provider": "comfyui",
  "status": "generated"
}

// invalidate_scene (cf-invalidation-engine)
{
  "secret": "<hmac_secret>" | header,
  "action": "invalidate_scene",
  "content_id": "<id>",
  "scene_id": "<row_id>"
}
```

### NocoDB Table IDs: Discovery at Runtime

The workflows need NocoDB table IDs (base_id + table_id) to make API calls. Two approaches:

1. **Hardcoded IDs** -- fragile, breaks on reprovisioning
2. **Runtime discovery** -- call NocoDB meta API to find base/table by name, cache in workflow static data

**Recommendation:** Use runtime discovery at workflow startup (first execution). The existing provisioning script already shows the pattern: `GET /api/v2/meta/bases/` then find by title. Cache in a Code node at the start of each workflow.

However, for simplicity and reliability in this gap closure phase: **hardcode the base and table names as lookups, not IDs**. Each workflow does a lightweight meta query on first call.

Better yet: use n8n environment variables for the base ID and table IDs, set during provisioning. Add `NOCODB_CF_BASE_ID`, `NOCODB_CONTENTS_TABLE_ID`, `NOCODB_SCENES_TABLE_ID`, `NOCODB_BRANDS_TABLE_ID` to `n8n.env.j2`. The provisioning script already discovers these IDs.

### Anti-Patterns to Avoid

- **Direct NocoDB access from OpenClaw/skills:** All data access goes through n8n webhooks (security sandbox boundary -- Phase 6 decision)
- **Hardcoding NocoDB row IDs:** Use field-based lookups (content_id, brand_id)
- **Skipping secret validation:** Every webhook MUST validate the HMAC secret
- **Ignoring the dual-secret pattern:** Some callers pass secret in body, others in x-webhook-secret header -- workflow must check both

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| NocoDB CRUD | Custom database layer | NocoDB REST API v2 | API already deployed, token in n8n env |
| Webhook auth | Custom auth mechanism | Existing HMAC secret pattern ($env.N8N_WEBHOOK_HMAC_SECRET) | All CF workflows already use this |
| Workflow registration | Custom deploy scripts | Existing n8n-provision Ansible loop | Add to existing copy + checksum + import + activate pipeline |
| Table ID discovery | Hardcoded UUIDs | NocoDB meta API or env vars | IDs change on reprovisioning |

## Common Pitfalls

### Pitfall 1: NocoDB Table/Base ID Discovery
**What goes wrong:** Hardcoding NocoDB table IDs that change when tables are recreated
**Why it happens:** The provisioning script uses a sentinel file -- if it runs again (sentinel deleted), new table IDs are generated
**How to avoid:** Store table IDs as n8n env vars (set during provisioning) or use name-based lookup via meta API at runtime
**Warning signs:** 404 errors on NocoDB API calls after a redeploy

### Pitfall 2: Field Name Collision in cf-scene
**What goes wrong:** The `create_scene` action receives an `action` field from the caller (scene action description) that collides with the routing `action` field
**Why it happens:** cf-script-to-storyboard sends `action: "scene action description"` as a scene field alongside `action: "create_scene"` as routing
**How to avoid:** Extract the routing action FIRST, then use remaining body fields for the NocoDB record. The routing action and scene field share the same name -- careful parsing needed.
**Warning signs:** Scene created with action="create_scene" instead of the actual scene action text

### Pitfall 3: Content Record Needs Brand Data
**What goes wrong:** cf-read-content returns only content fields, but callers expect brand data (brand_tone, brand_name, brand_palette)
**Why it happens:** Brand data lives in a separate `brands` table, not in the `contents` table
**How to avoid:** cf-read-content must check if brand_id exists in the content record and do a second lookup to `brands` table, merging brand fields into the response
**Warning signs:** "undefined" brand_tone in LLM prompts, missing brand colors in Remotion compositions

### Pitfall 4: NocoDB Record ID Field
**What goes wrong:** NocoDB auto-generates a row `Id` field (capital I). Callers use `content_id` which is stored as a field value, not as the NocoDB row ID.
**Why it happens:** In the data model, `content_id` is a logical identifier (could be a UUID generated by the caller), while NocoDB's `Id` is the internal row number.
**How to avoid:** When creating content, return the NocoDB `Id` as the `content_id`. For reads/updates, filter by the `Id` field or a custom ID field. Since the existing callers pass `content_id` which is the value they got back from `cf-create-content`, the simplest approach is to use NocoDB's auto-increment `Id` as the content_id.
**Warning signs:** "Record not found" when content_id is a UUID but NocoDB expects an integer row Id

### Pitfall 5: NocoDB SingleSelect Field Validation
**What goes wrong:** NocoDB rejects PATCH/POST if a SingleSelect field value is not in the predefined options list
**Why it happens:** The `status` field was defined with options `brief,concept,script,...` but callers send values like `awaiting_validation`, `reworking`, `generating`
**How to avoid:** Either (a) add all possible status values to the SingleSelect options during provisioning, or (b) change the field type to SingleLineText. Given the many status values used by callers, SingleLineText may be safer.
**Warning signs:** 422 errors on cf-update-content when setting status to unlisted values

### Pitfall 6: Extra Content Fields Not in Schema
**What goes wrong:** Callers send fields like `step1_enhanced_brief`, `step4_concept`, `step5_casting`, `step6_script`, etc. that don't exist in the `contents` table schema
**Why it happens:** The original table schema has only `brief`, `script`, `storyboard`, `assets_urls` -- not the per-step fields the workflows store
**How to avoid:** Either (a) add these columns to the NocoDB table (via API PATCH to add columns), or (b) use a generic JSON field to store step data, or (c) silently ignore unknown fields. NocoDB v2 actually ignores unknown fields in PATCH/POST -- they just don't get stored. This means step data would be LOST.
**How to fix:** Add columns for each step field during provisioning, or update the provisioning script to include them. This is critical -- without these columns, the pipeline stores nothing.
**Warning signs:** cf-read-content returns empty/null for step data that was supposedly stored

## Code Examples

### n8n Webhook Workflow JSON Structure (verified from existing cf-brief-to-concept.json)

```json
{
  "name": "CF Create Content",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "cf-create-content",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "cfcc-0001-...",
      "name": "Webhook Trigger",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [260, 380],
      "webhookId": "cfcc-webhook-..."
    },
    {
      "parameters": {
        "jsCode": "// Validate + create NocoDB record\n..."
      },
      "name": "Create Content",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "={{ { status: 'ok', content_id: $json.content_id } }}",
        "options": { "responseCode": 200 }
      },
      "name": "Webhook Response",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1.1
    }
  ],
  "connections": { ... },
  "settings": {
    "executionOrder": "v1",
    "saveDataSuccessExecution": "all",
    "saveDataErrorExecution": "all",
    "callerPolicy": "workflowsFromSameOwner"
  },
  "tags": [{ "name": "content-factory" }]
}
```

### NocoDB v2 API Call Pattern (from provisioning script)

```javascript
// List records with filter
const response = await $http.request({
  method: 'GET',
  url: `${$env.NOCODB_BASE_URL}/api/v2/meta/bases/${baseId}/tables/${tableId}/records`,
  headers: { 'xc-token': $env.NOCODB_API_TOKEN },
  qs: { where: `(Id,eq,${content_id})`, limit: 1 }
});

// Create record
const result = await $http.request({
  method: 'POST',
  url: `${$env.NOCODB_BASE_URL}/api/v2/meta/bases/${baseId}/tables/${tableId}/records`,
  headers: {
    'xc-token': $env.NOCODB_API_TOKEN,
    'Content-Type': 'application/json'
  },
  body: { title: "My Content", format: "reel", status: "brief" }
});

// Update record
await $http.request({
  method: 'PATCH',
  url: `${$env.NOCODB_BASE_URL}/api/v2/meta/bases/${baseId}/tables/${tableId}/records`,
  headers: {
    'xc-token': $env.NOCODB_API_TOKEN,
    'Content-Type': 'application/json'
  },
  body: { Id: rowId, status: "concept", current_step: 5 }
});
```

### NocoDB env vars already in n8n.env.j2

```
NOCODB_BASE_URL=https://{{ nocodb_subdomain }}.{{ domain_name }}
NOCODB_API_TOKEN={{ nocodb_api_token }}
```

### Secret Validation Pattern (from all existing CF workflows)

```javascript
const data = $input.first().json;
const body = data.body || data;
const expectedSecret = $env.N8N_WEBHOOK_HMAC_SECRET;
if (!expectedSecret) throw new Error('N8N_WEBHOOK_HMAC_SECRET not configured');
const receivedSecret = (data.headers || {})['x-webhook-secret'] || body.secret || '';
if (receivedSecret !== expectedSecret) throw new Error('Unauthorized');
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| NocoDB API v1 (`/api/v1/db/data/...`) | NocoDB API v2 (`/api/v2/meta/bases/.../tables/.../records`) | NocoDB 0.200+ | v2 is the current stable API |
| n8n `n8n-nodes-base.nocodb` node | Code node with HTTP requests | Project decision (Phase 6) | Direct HTTP gives more control, avoids credential node setup complexity |

## Open Questions

1. **NocoDB Table IDs for Runtime**
   - What we know: The provisioning script discovers IDs at deploy time, but they're not stored anywhere accessible to n8n workflows
   - What's unclear: Whether to add env vars to n8n.env.j2 (cleaner) or use runtime meta API discovery (more resilient)
   - Recommendation: Add `NOCODB_CF_BASE_ID`, `NOCODB_CONTENTS_TABLE_ID`, `NOCODB_SCENES_TABLE_ID`, `NOCODB_BRANDS_TABLE_ID` env vars to n8n.env.j2, populated by modifying the provisioning script to output these values

2. **Missing Content Table Columns**
   - What we know: Callers store per-step data (step1_enhanced_brief through step8_sound_design, brand_tone, etc.) but the contents table only has basic columns
   - What's unclear: Whether NocoDB silently drops unknown fields or errors
   - Recommendation: Add missing columns to provisioning script. At minimum: `step1_enhanced_brief`, `step2_research`, `step3_moodboard_prompts`, `step4_concept`, `step5_casting`, `step6_script`, `step7_scenes_count`, `step8_sound_design`, `brand_tone`, `brand_name`, `brand_palette`, `brand_typography`, `latest_preview_url`, `last_kitsu_sync`, `kitsu_task_status_id`. Use LongText/JSON types.

3. **DATA-06 Verification Method**
   - What we know: `kitsu-provision` role exists with full project structure script, 05-03-SUMMARY confirms it was run
   - What's unclear: Whether the sentinel file exists on Sese-AI (was it deployed?)
   - Recommendation: SSH to Sese-AI, verify sentinel + API query for project structure, mark DATA-06 complete

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Ansible + curl smoke tests |
| Config file | roles/n8n-provision/molecule/default/molecule.yml |
| Quick run command | `curl -sf -X POST http://localhost:5678/webhook/cf-create-content -H 'Content-Type: application/json' -d '{"secret":"<secret>","title":"test","format":"reel","brief":{"objective":"test"}}'` |
| Full suite command | `make deploy-role ROLE=n8n-provision ENV=prod` + manual webhook tests |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-06 | Kitsu project structure exists with 14 task types | smoke | `ssh sese 'cat /opt/javisi/configs/kitsu/.provision-complete'` | N/A (runtime check) |
| SC-1 | cf-create-content creates NocoDB row | smoke | `curl POST cf-create-content with test data` | Wave 0 |
| SC-2 | cf-update-content updates fields by content_id | smoke | `curl POST cf-update-content with test data` | Wave 0 |
| SC-3 | cf-read-content returns full record + brand data | smoke | `curl POST cf-read-content with test content_id` | Wave 0 |
| SC-4 | cf-scene handles create/list/update/invalidate | smoke | `curl POST cf-scene with each action` | Wave 0 |
| SC-5 | Kitsu project has 14 task types | smoke | `curl GET /api/data/task-types (via Kitsu API)` | N/A (runtime check) |

### Sampling Rate
- **Per task commit:** Ansible lint (`make lint`)
- **Per wave merge:** Deploy + smoke test all 4 webhook endpoints
- **Phase gate:** All 4 webhooks respond correctly + DATA-06 verified

### Wave 0 Gaps
- [ ] 4 workflow JSON files (cf-create-content.json, cf-update-content.json, cf-read-content.json, cf-scene.json)
- [ ] n8n-provision task loop entries for new workflows
- [ ] n8n.env.j2 additions for NocoDB table IDs (if env var approach chosen)
- [ ] Content table column additions in provisioning script (step data fields)

## Sources

### Primary (HIGH confidence)
- `roles/n8n-provision/files/workflows/cf-brief-to-concept.json` -- verified calling pattern for cf-read-content, cf-update-content
- `roles/n8n-provision/files/workflows/cf-script-to-storyboard.json` -- verified calling pattern for cf-read-content, cf-update-content, cf-scene
- `roles/n8n-provision/files/workflows/cf-generate-assets.json` -- verified calling pattern for cf-read-content, cf-scene
- `roles/n8n-provision/files/workflows/cf-rough-cut.json` -- verified calling pattern for cf-read-content, cf-scene
- `roles/n8n-provision/files/workflows/cf-invalidation-engine.json` -- verified calling pattern for cf-update-content, cf-scene
- `roles/n8n-provision/files/workflows/cf-kitsu-inbound.json` -- verified calling pattern for cf-update-content
- `roles/n8n-provision/files/workflows/cf-calendar-sync.json` -- verified calling pattern for cf-read-content
- `roles/content-factory-provision/templates/provision-nocodb-tables.sh.j2` -- NocoDB table schemas, API patterns
- `roles/kitsu-provision/templates/provision-kitsu.sh.j2` -- Zou API patterns, project structure
- `roles/n8n/templates/n8n.env.j2` -- available env vars (NOCODB_BASE_URL, NOCODB_API_TOKEN)
- `roles/n8n-provision/tasks/main.yml` -- workflow deploy pipeline (copy, checksum, import, activate)

### Secondary (MEDIUM confidence)
- [NocoDB API docs](https://nocodb.com/docs/product-docs/developer-resources/rest-apis) -- v2 API endpoint patterns
- `.planning/v2026.3-MILESTONE-AUDIT.md` -- gap identification and severity

### Tertiary (LOW confidence)
- NocoDB field validation behavior for unknown columns (needs runtime verification)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all components already deployed and used by existing workflows
- Architecture: HIGH -- exact calling patterns extracted from 7 existing workflow JSON files
- Pitfalls: HIGH -- field collision, missing columns, and table ID issues identified from code analysis
- DATA-06: MEDIUM -- code exists but deployment verification pending

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (stable -- all components already deployed)
