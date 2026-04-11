# Fix af-phase-complete — Project Status Automation

> Closes the gap where NocoDB project status never transitions from `design` to `building` during GSD phase execution.

**Date:** 2026-04-02
**Status:** Approved
**Scope:** af-phase-complete workflow + CLI script + Claude Code hook

---

## 1. Problem

The `af-phase-complete` n8n workflow logs phase completion data (phase_logs, decisions, REX indexing) but never updates the `projects` table. The spec (section 3.4 + section 4) requires `af-phase-complete` to feed the `projects` table with `phases_completed`, `total_duration`, and `status`. This was never implemented.

Additionally, no mechanism exists to trigger the webhook automatically when a GSD phase completes. The spec says "called by Claude at each phase end" but no hook or convention enforces this.

Result: StoryEngine row Id=1 is stuck at `status=design` despite 2 phases completed.

---

## 2. Solution Overview

Three deliverables:

1. **Workflow fix** — Add 6 new nodes to `af-phase-complete.json` (dedup check, dedup gate, fetch status, count/sum, compute status, PATCH project)
2. **CLI script** — `scripts/af-notify-phase.sh` for manual/fallback invocation
3. **Claude Code hook** — `postToolResult` hook in `.claude/settings.json` that auto-detects phase completion and prints a reminder

---

## 3. Workflow Changes — `af-phase-complete.json`

### 3.0 NocoDB API Conventions

All NocoDB HTTP nodes MUST include these headers:

```json
{
  "xc-token": "={{ $env.NOCODB_API_TOKEN }}",
  "Content-Type": "application/json"
}
```

PATCH uses the `?where=` query parameter pattern (consistent with existing `af-deploy` workflow), NOT the `Id`-in-body pattern. Example:

```
PATCH /api/v2/tables/{table_id}/records?where=(name,eq,{value})
Body: { "field1": "value1", "field2": "value2" }
```

### 3.1 New Nodes (6 total)

**Node 1: `Check Duplicate Phase Log`**
- Type: `httpRequest` (GET)
- URL: `http://javisi_nocodb:8080/api/v2/tables/mx5x4nb739fjld1/records?where=(project_name,eq,{{ encodeURIComponent($json.project_name) }})~and(phase_number,eq,{{ $json.phase_number }})&limit=1`
- Headers: `xc-token` + `Content-Type` (as per section 3.0)
- Purpose: Idempotence guard — prevent double-insert if webhook fires twice for the same phase
- Output: `pageInfo.totalRows` indicates if record already exists

**Node 2: `Is New Phase?`**
- Type: `if`
- Condition: `$json.pageInfo.totalRows == 0`
- True branch → `Insert Phase Log` (existing node)
- False branch → `Fetch Current Status` (skip insert)

**Node 3: `Fetch Current Status`**
- Type: `httpRequest` (GET)
- URL: `http://javisi_nocodb:8080/api/v2/tables/mvhxrbdyetpoyjb/records?where=(name,eq,{{ encodeURIComponent($('Parse Phase Data').first().json.project_name) }})&fields=status&limit=1`
- Headers: `xc-token` + `Content-Type` (as per section 3.0)
- Purpose: Read current project status to decide transition
- Output: `list[0].status` (e.g., `"design"`)
- Both branches (new/duplicate) converge here

**Node 4: `Count Phase Logs`**
- Type: `httpRequest` (GET)
- URL: `http://javisi_nocodb:8080/api/v2/tables/mx5x4nb739fjld1/records?where=(project_name,eq,{{ encodeURIComponent($('Parse Phase Data').first().json.project_name) }})&fields=duration_min&limit=1000`
- Headers: `xc-token` + `Content-Type` (as per section 3.0)
- Purpose: Get total count and sum of `duration_min` for this project
- Note: `pageInfo.totalRows` gives the count; `list[]` gives records for summing. `limit=1000` is safe — no project will have >1000 phases in this system's lifetime.

**Node 5: `Compute Project Status`**
- Type: `code`
- Reads from TWO upstream nodes: `Count Phase Logs` (for metrics) AND `Fetch Current Status` (for current status)
- Logic:
  ```javascript
  // Read from Count Phase Logs (upstream node 4)
  const countResult = $('Count Phase Logs').first().json;
  const records = countResult.list || [];
  const phases_completed = countResult.pageInfo?.totalRows || 0;
  const total_duration = records.reduce((sum, r) => sum + (r.duration_min || 0), 0);

  // Read from Fetch Current Status (upstream node 3)
  const statusResult = $('Fetch Current Status').first().json;
  const current_status = (statusResult.list && statusResult.list[0]?.status) || 'intake';

  // Status transition: only escalate, never downgrade
  // af-deploy owns the "deployed" transition
  let new_status = current_status;
  if (current_status === 'intake' || current_status === 'design') {
    new_status = 'building';
  }

  return [{
    json: {
      project_name: $('Parse Phase Data').first().json.project_name,
      phases_completed,
      total_duration,
      status: new_status
    }
  }];
  ```

**Node 6: `NocoDB Update Project`**
- Type: `httpRequest` (PATCH)
- URL: `http://javisi_nocodb:8080/api/v2/tables/mvhxrbdyetpoyjb/records?where=(name,eq,{{ encodeURIComponent($json.project_name) }})`
- Headers: `xc-token` + `Content-Type` (as per section 3.0)
- Body: `{ "phases_completed": $json.phases_completed, "total_duration": $json.total_duration, "status": $json.status }`
- Uses `?where=` pattern (consistent with `af-deploy` node `nocodb-update-project-status`)

### 3.2 Updated Flow

```
Webhook → Validate Secret → Parse Phase Data
  → Check Duplicate Phase Log → Is New Phase?
    → [true]  Insert Phase Log ──┐
    → [false] ───────────────────┤
                                 ▼
              Fetch Current Status → Count Phase Logs → Compute Project Status → NocoDB Update Project
                                                                                       │
              Split Decisions → Has Decisions? → Insert Decision / No-op ◄─────────────┘
                                                       │
              Call REX Indexer ◄────────────────────────┘
                    │
              Respond OK
```

Key wiring:
- Both branches of `Is New Phase?` converge at `Fetch Current Status`
- `Compute Project Status` reads from both `Fetch Current Status` and `Count Phase Logs` (n8n `$('NodeName')` references by name, not by direct predecessor)
- `NocoDB Update Project` feeds into `Split Decisions` (existing node)
- `Split Decisions` and the rest of the existing flow are unchanged

### 3.3 Idempotence Guarantee

- `Check Duplicate Phase Log` prevents double-insert of phase_logs
- `Count Phase Logs` recalculates from all existing records (not incremental)
- `Compute Project Status` only escalates status (never downgrades)
- `NocoDB Update Project` uses `?where=` — PATCH is idempotent (same values overwritten)
- Calling the webhook N times for the same phase produces the same project state

### 3.4 Response Body

Update the existing `Respond OK` node to reflect the project update:

```json
{
  "ok": true,
  "phase_logged": true,
  "project_updated": true,
  "status": "<new_status>",
  "phases_completed": "<count>",
  "rex_indexed": true
}
```

---

## 4. CLI Script — `scripts/af-notify-phase.sh`

### Usage

```bash
./scripts/af-notify-phase.sh \
  --project "StoryEngine" \
  --phase 2 \
  --name "Core Domain Models" \
  --summary "Full CRUD API for projects, scenes, drafts, entities, facts. 26 tests passing." \
  --duration 45 \
  --files 18
```

### Important: `--project` value must match the `name` field in NocoDB `projects` table exactly (case-sensitive). For StoryEngine, the value stored by `af-intake` is `"StoryEngine"`.

### Behavior

1. Read `AF_WEBHOOK_SECRET` from env var (required)
2. Read `N8N_WEBHOOK_URL` from env var (default: `https://mayi.ewutelo.cloud/webhook/af-phase-complete`)
3. Validate required args (`--project`, `--phase`, `--name`, `--summary`)
4. POST JSON to webhook with `X-AF-Secret` header
5. Print response body (includes `status`, `phases_completed`)
6. Exit 0 on HTTP 200, 1 on any other status

### Script conventions

- `set -euo pipefail`
- No dependencies beyond `curl` and `jq`
- Secrets from env vars only, never CLI args

---

## 5. Claude Code Hook — `.claude/settings.json`

### Hook Definition

Add a `hooks` section to the existing `.claude/settings.json`:

```json
{
  "permissions": { ... },
  "hooks": {
    "postToolResult": [
      {
        "matcher": "Bash",
        "pattern": "VERIFICATION\\.md.*(PASS|approved)",
        "command": "echo '[AF] Phase completion detected. Run: scripts/af-notify-phase.sh --project <name> --phase <N> --name <phase_name> --summary <summary>'"
      }
    ]
  }
}
```

### Design Decision: Reminder vs Auto-Call

The hook prints a **reminder** rather than auto-calling the webhook. Reasons:
- GSD executor output format may vary — false positives would create garbage phase_logs
- The script needs `--project`, `--phase`, `--name`, `--summary` args that can't be reliably parsed from tool output
- Claude (the orchestrator) sees the reminder and calls the script with correct args

### Pattern Choice

The pattern `VERIFICATION\\.md.*(PASS|approved)` is narrow by design:
- Matches only GSD verification output (not arbitrary `git log` or `ls` results)
- GSD verifier writes VERIFICATION.md with PASS/FAIL verdicts — this is the most reliable signal
- Broader patterns like `phase.*complete` would match too many unrelated Bash outputs

If the hook proves too noisy or not useful, it can be removed. If GSD output stabilizes, it can be upgraded to auto-call.

### Rollback

To disable the hook without removing it: delete the `hooks` key from `.claude/settings.json`. No workflow side-effects — the webhook still works via manual script.

---

## 6. Status Transition Rules

```
Current Status    →  New Status    Trigger
─────────────────────────────────────────────
intake            →  building      af-phase-complete (any phase)
design            →  building      af-phase-complete (any phase)
building          →  building      af-phase-complete (no-op PATCH, idempotent)
building          →  deployed      af-deploy (smoke pass)
deployed          →  deployed      af-phase-complete (no-op PATCH, idempotent)
```

Only two workflows write `status`:
- `af-phase-complete` → can set `building`
- `af-deploy` → can set `deployed`

No other workflow touches `status`.

---

## 7. Backfill — StoryEngine

**Important:** The `project_name` must match the exact value in NocoDB. Verify with:
```bash
curl -s -H "xc-token: $NOCODB_API_TOKEN" \
  "http://javisi_nocodb:8080/api/v2/tables/mvhxrbdyetpoyjb/records?where=(Id,eq,1)&fields=name" | jq '.list[0].name'
```

After confirming the name, run the script twice to backfill phases 1 and 2:

```bash
export AF_WEBHOOK_SECRET="<from vault>"
./scripts/af-notify-phase.sh --project "<exact_name>" --phase 1 --name "Database Foundation & Auth" --summary "SQLAlchemy models, Alembic migrations, JWT auth, RBAC, 14 tests" --duration 0 --files 0
./scripts/af-notify-phase.sh --project "<exact_name>" --phase 2 --name "Core Domain Models & CRUD" --summary "Full CRUD API for projects, scenes, drafts, entities, facts, graph edges. 26 tests" --duration 0 --files 0
```

This will:
1. Insert 2 phase_log records (dedup-protected)
2. Set `phases_completed=2`, `total_duration=0` (unknown retroactively)
3. Transition `status` from `design` to `building`

---

## 8. Files Modified

| File | Action |
|------|--------|
| `scripts/n8n-workflows/af-phase-complete.json` | Add 6 nodes + rewire connections |
| `scripts/af-notify-phase.sh` | New file — CLI wrapper |
| `.claude/settings.json` | Add `hooks` section alongside existing `permissions` |

### Rollback

If the workflow changes cause errors in production:
1. Re-import the original `af-phase-complete.json` from git (`git show HEAD:scripts/n8n-workflows/af-phase-complete.json`)
2. Remove `hooks` from `.claude/settings.json`
3. The CLI script is standalone and has no side-effects if unused

---

## 9. Testing

1. **Unit**: POST to webhook with test data, verify phase_log inserted + project PATCH applied
2. **Idempotence**: POST same `(project_name, phase_number)` twice, verify phase_log count stays at 1 and project metrics unchanged
3. **Status guard**: Set project status to `deployed` manually, POST a phase, verify status stays `deployed`
4. **Script**: Run `af-notify-phase.sh` with valid args (expect 200), missing args (expect error), wrong secret (expect 403)
5. **Backfill**: Run the 2 StoryEngine backfill commands, verify NocoDB project row shows `status=building`, `phases_completed=2`
