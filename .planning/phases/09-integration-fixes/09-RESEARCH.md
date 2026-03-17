# Phase 9: Integration Fixes - Research

**Researched:** 2026-03-18
**Domain:** Cross-phase integration debugging (Ansible templates, n8n workflows, Zou API)
**Confidence:** HIGH

## Summary

Phase 9 fixes 8 specific integration issues identified by the v2026.3 milestone audit. All issues are concrete, file-level bugs -- wrong variable names, missing fields, endpoint mismatches, missing env vars, and missing runtime data (bot account, project, vault creds). No new libraries, patterns, or architecture decisions are needed.

Every fix has been verified by reading the actual source files. The issues fall into three categories: (1) Ansible template variable mismatches (event_handler, env vars, vault creds), (2) n8n workflow field/endpoint bugs (Remotion API, cf-rough-cut action field, STATUS_MAP), and (3) missing runtime data (bot account, Kitsu project).

**Primary recommendation:** Fix all 8 items as surgical edits to existing files. No new files needed. Deploy once at the end and run the 3 E2E smoke tests.

## Standard Stack

No new libraries. All fixes are edits to existing Ansible templates, n8n workflow JSON files, and Ansible vault.

### Files to Modify

| File | Fix | SC# |
|------|-----|-----|
| `roles/kitsu/templates/event_handler.py.j2` | `n8n_webhook_hmac_secret` -> `n8n_webhook_secret` | 1 |
| `roles/n8n-provision/templates/workflows/creative-pipeline.json.j2` | `/render` -> `/renders`, `composition` -> `compositionId`, `renderId` -> `jobId` | 2 |
| `roles/n8n/templates/n8n.env.j2` | Add `REMOTION_API_KEY` and `BYTEPLUS_API_KEY` env vars | 3 |
| `roles/n8n-provision/files/workflows/cf-rough-cut.json` | Add `action: 'update_content'` field to cf-update-content call | 4 |
| `roles/n8n-provision/templates/workflows/cf-kitsu-sync.json.j2` | Add `'locked': 'Approved'` to STATUS_MAP | 5 |
| `roles/kitsu-provision/templates/provision-kitsu.sh.j2` | Add bot account creation (javisi.bot@gmail.com) | 6 |
| `roles/kitsu-provision/templates/provision-kitsu.sh.j2` | Already creates project -- needs runtime execution | 7 |
| `inventory/group_vars/all/secrets.yml` | Update vault_kitsu_admin_email to `seko.mobutoo@gmail.com` | 8 |

## Architecture Patterns

### Fix Categories

**Category A: Variable/Field Name Fixes (SC 1, 2, 4, 5)**
Simple string replacements in templates. Testable by `ansible-playbook --check --diff`.

**Category B: Missing Env Vars (SC 3)**
Add lines to `n8n.env.j2`. Pattern matches existing env var declarations in the file.

**Category C: Runtime Data (SC 6, 7)**
Bot account creation and project provisioning require SSH to Sese-AI and running the provisioning script. The provisioning script already handles project creation (SC 7) but is blocked by the sentinel file. Bot account creation (SC 6) needs a new section in the script.

**Category D: Vault Update (SC 8)**
`ansible-vault edit` to fix the admin email.

### Execution Order

1. Template fixes (SC 1-5) -- all independent, can be done in parallel
2. Vault fix (SC 8) -- must happen before provisioning
3. Bot account script update (SC 6) -- edit provision-kitsu.sh.j2
4. Deploy to Sese-AI
5. Re-run provisioning (SC 6, 7) -- requires clearing sentinel or adding bot creation to idempotent section
6. E2E smoke tests

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bot account creation | Manual curl/docker exec | Add to provision-kitsu.sh.j2 using `zou create-admin` CLI | Idempotent, survives reprovisioning |
| Kitsu project reset | Delete sentinel and re-run full provisioning | Make bot creation section independent of sentinel | Project already exists, only bot is missing |

## Common Pitfalls

### Pitfall 1: Sentinel File Blocks Re-provisioning
**What goes wrong:** `provision-kitsu.sh.j2` exits early if sentinel file exists. Bot account won't be created.
**Why it happens:** Sentinel was written after Phase 5 provisioning, before bot creation was added.
**How to avoid:** Either (a) add bot creation BEFORE the sentinel check (in a separate idempotent section), or (b) temporarily remove sentinel and re-run, or (c) add a separate bot-provisioning section that runs independently.
**Recommended approach:** Add bot creation as a separate idempotent block that runs regardless of sentinel. Use `zou create-admin` which is idempotent (warns if user exists).

### Pitfall 2: Remotion API Response Handling Chain
**What goes wrong:** creative-pipeline.json.j2 has THREE mismatches with the actual Remotion server: endpoint, request field, and response field. Fixing only one still breaks the chain.
**Why it happens:** creative-pipeline was written before the Remotion server was finalized.
**How to avoid:** Fix all three in one edit:
- Line 151: `/render` -> `/renders`
- Line 162: `composition` -> `compositionId` (matches `RenderRequestSchema` in server/index.ts)
- Line 205 (Normalize output): `input.renderId` -> `input.jobId` (server returns `{ jobId: "..." }`)

### Pitfall 3: cf-rough-cut Calls creative-pipeline, Not Remotion Directly
**What goes wrong:** Fixing creative-pipeline fixes the cf-rough-cut -> Remotion path automatically.
**Why it matters:** cf-rough-cut (line 50) calls `http://localhost:5678/webhook/creative-pipeline` which then calls Remotion. The Remotion API fix is in creative-pipeline.json.j2, not in cf-rough-cut.json.

### Pitfall 4: REMOTION_API_KEY vs REMOTION_API_TOKEN
**What goes wrong:** creative-pipeline.json.j2 reads `$env.REMOTION_API_KEY` but the Remotion server uses `REMOTION_API_TOKEN`. n8n.env.j2 must expose the vault value as `REMOTION_API_KEY` (matching the workflow expectation).
**How to avoid:** In n8n.env.j2, add: `REMOTION_API_KEY={{ vault_remotion_api_token | default('') }}`. This maps the vault variable to the env var name the workflow expects.

### Pitfall 5: Vault Is Encrypted -- Can't grep for values
**What goes wrong:** secrets.yml is Ansible Vault encrypted. Cannot verify current values without `ansible-vault view`.
**How to avoid:** Use `ansible-vault edit inventory/group_vars/all/secrets.yml` to update `vault_kitsu_admin_email` to `seko.mobutoo@gmail.com` and `vault_kitsu_admin_password` to `mysecretpassword`.

### Pitfall 6: Bot Account Needs Vault Variables Too
**What goes wrong:** n8n.env.j2 already reads `vault_kitsu_bot_email` and `vault_kitsu_bot_password` (lines 191-194), but these may not exist in secrets.yml.
**How to avoid:** Verify and add `vault_kitsu_bot_email: javisi.bot@gmail.com` and `vault_kitsu_bot_password` to secrets.yml.

### Pitfall 7: SSH Access to Sese-AI
**What goes wrong:** Public IP (137.74.114.167) times out. Must use Tailscale IP.
**How to avoid:** Use `100.64.0.14` port 804 for all SSH/Ansible operations. This is already documented in STATE.md.

## Code Examples

### SC 1: Fix event_handler.py.j2 variable name

```python
# BEFORE (line 11):
WEBHOOK_SECRET = "{{ n8n_webhook_hmac_secret }}"

# AFTER:
WEBHOOK_SECRET = "{{ n8n_webhook_secret }}"
```

**Why:** Inventory defines `n8n_webhook_secret` (confirmed in `inventory/group_vars/all/main.yml:172`). The template uses `n8n_webhook_hmac_secret` which resolves to empty string.

### SC 2: Fix creative-pipeline.json.j2 Remotion integration

Three changes in the file:

```json
// BEFORE (line 151 — endpoint):
"url": "https://...remotion.../render",
// AFTER:
"url": "https://...remotion.../renders",

// BEFORE (line 162 — field name):
{ "name": "composition", "value": "={{ $json.composition }}" },
// AFTER:
{ "name": "compositionId", "value": "={{ $json.composition }}" },

// BEFORE (line 205 — response handling in Normalize output):
else if (input.renderId) {
  render_id = input.renderId;
// AFTER:
else if (input.jobId) {
  render_id = input.jobId;
```

**Evidence:** Remotion server `index.ts` line 85: `app.post("/renders", ...)`, line 29: `compositionId: z.string()`, line 112: `res.json({ jobId })`.

### SC 3: Add missing env vars to n8n.env.j2

```ini
# Add after the Kitsu section (after line 196):

# Remotion API key — used by creative-pipeline workflow for authenticated renders
{% if vault_remotion_api_token | default('') | length > 0 %}
REMOTION_API_KEY={{ vault_remotion_api_token }}
{% endif %}

# BytePlus API key — used by creative-pipeline workflow for Seedance video generation
{% if byteplus_api_key | default('') | length > 0 %}
BYTEPLUS_API_KEY={{ byteplus_api_key }}
{% endif %}
```

**Note:** The workflow reads `$env.REMOTION_API_KEY` but vault stores `vault_remotion_api_token`. The env var name must match what the workflow expects.

### SC 4: Add action field in cf-rough-cut.json

```javascript
// BEFORE (Store Rough Cut URL node, ~line 60):
body: {
  secret: expectedSecret,
  content_id,
  rough_cut_url,
  current_step: 10,
  status: 'awaiting_validation'
},

// AFTER:
body: {
  secret: expectedSecret,
  action: 'update_content',
  content_id,
  rough_cut_url,
  current_step: 10,
  status: 'awaiting_validation'
},
```

### SC 5: Add locked mapping to STATUS_MAP in cf-kitsu-sync.json.j2

```javascript
// BEFORE (Update Task Status node):
const STATUS_MAP = {
  'wip':         'WIP',
  'done':        'Done',
  'retake':      'Retake',
  'invalidated': 'Retake',
  'generating':  'Generating',
  'todo':        'Todo'
};

// AFTER:
const STATUS_MAP = {
  'wip':         'WIP',
  'done':        'Done',
  'retake':      'Retake',
  'invalidated': 'Retake',
  'generating':  'Generating',
  'todo':        'Todo',
  'locked':      'Approved'
};
```

**Note:** Kitsu default statuses include "Approved" (from `zou init-data`). "Locked" maps to "Approved" since lock gates prevent further changes.

### SC 6: Add bot account creation to provision-kitsu.sh.j2

```bash
# Add after admin creation (after line 36), BEFORE the API section:
echo "[$(date)] Creating bot account..."
docker exec "${CONTAINER}" /opt/zou/env/bin/zou create-admin \
  "{{ vault_kitsu_bot_email }}" --password "{{ vault_kitsu_bot_password }}" 2>&1 || {
  echo "[$(date)] WARNING: Bot account creation failed (may already exist)"
}
```

**Note:** `zou create-admin` is idempotent -- it warns if user exists but does not fail. The bot email `javisi.bot@gmail.com` and password must be in secrets.yml.

### SC 8: Vault credential fix

```bash
# Run manually:
cd /home/mobuone/VPAI
source .venv/bin/activate
ansible-vault edit inventory/group_vars/all/secrets.yml

# Change:
vault_kitsu_admin_email: "seko.mobutoo@gmail.com"
vault_kitsu_admin_password: "mysecretpassword"

# Verify bot credentials exist:
vault_kitsu_bot_email: "javisi.bot@gmail.com"
vault_kitsu_bot_password: "<generate-secure-password>"
```

## State of the Art

Not applicable -- this phase is pure bug fixing, no technology choices.

## Open Questions

1. **Kitsu "Approved" status existence**
   - What we know: `zou init-data` creates default statuses. "Approved" is a standard Zou status.
   - What's unclear: Whether it exists on the current Sese-AI instance. The provisioning script verifies statuses exist but doesn't create custom ones.
   - Recommendation: During deployment, verify with `curl http://kitsu:80/api/data/task-status` and create "Approved" if missing.

2. **Bot account password**
   - What we know: Bot email is `javisi.bot@gmail.com`. STATE.md says bot "Mobotoo" was created in Phase 5 decisions.
   - What's unclear: Whether bot password is already in vault. The audit says bot does NOT exist in Zou despite the decision.
   - Recommendation: Check vault for existing bot password. If absent, generate one and add it.

3. **Sentinel file handling for re-provisioning**
   - What we know: Sentinel at `{{ kitsu_provision_config_dir }}/.provision-complete` exists. Script skips if sentinel present.
   - What's unclear: Whether bot creation should be inside or outside sentinel guard.
   - Recommendation: Move bot creation ABOVE the sentinel check (alongside admin creation) so it runs every time. Both `zou create-admin` calls are idempotent.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Manual E2E (curl + SSH) |
| Config file | none |
| Quick run command | `curl -sf https://mayi.ewutelo.cloud/webhook/cf-kitsu-inbound -d '{"secret":"...","event_type":"task:status-changed","data":{}}'` |
| Full suite command | Run 3 E2E flows manually |

### Phase Requirements to Test Map
| SC# | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| SC-1 | event_handler uses correct variable | smoke | `ansible-playbook --check --diff -t kitsu` + grep rendered template | N/A |
| SC-2 | creative-pipeline calls /renders with compositionId | smoke | `curl -X POST https://remotion.ewutelo.cloud/renders -H 'Content-Type: application/json' -d '{"compositionId":"HelloWorld"}'` | N/A |
| SC-3 | n8n.env has REMOTION_API_KEY + BYTEPLUS_API_KEY | smoke | SSH + `docker exec n8n env \| grep -E 'REMOTION_API_KEY\|BYTEPLUS_API_KEY'` | N/A |
| SC-4 | cf-rough-cut sends action field | code review | Verify JSON contains `action` field in body | N/A |
| SC-5 | STATUS_MAP includes locked | code review | Verify JSON contains `locked` key | N/A |
| SC-6 | Bot account exists | smoke | `curl -X POST http://kitsu:80/api/auth/login -d '{"email":"javisi.bot@gmail.com","password":"..."}'` | N/A |
| SC-7 | Paul Taff project exists | smoke | `curl http://kitsu:80/api/data/projects` (via SSH) | N/A |
| SC-8 | Vault creds match server | manual | `ansible-vault view secrets.yml \| grep kitsu_admin` | N/A |

### Sampling Rate
- **Per task commit:** `ansible-playbook --check --diff` for template changes
- **Per wave merge:** Deploy + 3 E2E flows
- **Phase gate:** All 8 SCs verified on Sese-AI

### Wave 0 Gaps
None -- no test framework needed. All verification is curl/SSH-based smoke tests.

## Sources

### Primary (HIGH confidence)
- `roles/kitsu/templates/event_handler.py.j2` -- verified line 11 uses `n8n_webhook_hmac_secret`
- `roles/remotion/files/server/index.ts` -- verified endpoint `/renders` (L85), field `compositionId` (L29), response `jobId` (L112)
- `roles/n8n/templates/n8n.env.j2` -- verified REMOTION_API_KEY and BYTEPLUS_API_KEY absent
- `roles/n8n-provision/files/workflows/cf-rough-cut.json` -- verified missing `action` field (L60)
- `roles/n8n-provision/templates/workflows/cf-kitsu-sync.json.j2` -- verified STATUS_MAP missing `locked` (L114)
- `roles/n8n-provision/templates/workflows/creative-pipeline.json.j2` -- verified wrong endpoint/fields
- `inventory/group_vars/all/main.yml` -- verified `n8n_webhook_secret` (L172), `byteplus_api_key` (L130)
- `roles/comfyui/templates/docker-compose-creative.yml.j2` -- verified `vault_remotion_api_token` (L58)

### Secondary (MEDIUM confidence)
- `.planning/v2026.3-MILESTONE-AUDIT.md` -- audit findings match code review
- `.planning/STATE.md` -- runtime session findings (admin email, bot missing, Tailscale IP)

## Metadata

**Confidence breakdown:**
- Template fixes (SC 1-5): HIGH -- verified by reading actual source files
- Runtime data (SC 6-7): HIGH -- provisioning script read, bot creation pattern confirmed
- Vault fix (SC 8): MEDIUM -- vault is encrypted, cannot verify current values without decryption

**Research date:** 2026-03-18
**Valid until:** 2026-04-18 (stable -- no external API changes expected)
