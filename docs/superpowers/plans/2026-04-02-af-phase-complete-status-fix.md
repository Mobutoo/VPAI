# af-phase-complete Status Fix — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the `af-phase-complete` n8n workflow to update NocoDB project status + add CLI script + Claude Code hook.

**Architecture:** Add 6 nodes to the existing workflow JSON for dedup/status/PATCH, create a standalone bash script for manual invocation, add a postToolResult hook to settings.json.

**Tech Stack:** n8n workflow JSON, Bash (curl + jq), Claude Code hooks

**Spec:** `docs/superpowers/specs/2026-04-02-af-phase-complete-status-fix.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/af-notify-phase.sh` | Create | CLI wrapper — POST to af-phase-complete webhook |
| `scripts/n8n-workflows/af-phase-complete.json` | Modify | Add 6 nodes, rewire connections, update response |
| `.claude/settings.json` | Modify | Add `hooks` section for phase completion reminder |

## Parallelization

| Wave | Tasks | Why |
|------|-------|-----|
| Wave 1 | Task 1 (script) + Task 4 (hook) | Independent of each other and of the workflow |
| Wave 2 | Task 2 (nodes) → Task 3 (connections) | Sequential — connections reference node names |
| Wave 3 | Task 5 (validation) | Depends on all previous tasks |

---

### Task 1: Create CLI Script `scripts/af-notify-phase.sh`

**Files:**
- Create: `scripts/af-notify-phase.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
set -euo pipefail

# af-notify-phase.sh — Notify n8n af-phase-complete webhook
# Usage: ./scripts/af-notify-phase.sh --project <name> --phase <N> --name <phase_name> --summary <text> [--duration <min>] [--files <count>]

usage() {
  cat <<EOF
Usage: $0 --project <name> --phase <N> --name <phase_name> --summary <text> [--duration <min>] [--files <count>]

Required:
  --project   Project name (must match NocoDB exactly, case-sensitive)
  --phase     Phase number (integer)
  --name      Phase name (e.g. "Database Foundation & Auth")
  --summary   Phase summary text

Optional:
  --duration  Duration in minutes (default: 0)
  --files     Files changed count (default: 0)

Environment:
  AF_WEBHOOK_SECRET   Required. The webhook secret for authentication.
  N8N_WEBHOOK_URL     Optional. Default: https://mayi.ewutelo.cloud/webhook/af-phase-complete
EOF
  exit 1
}

# Defaults
PROJECT="" PHASE="" NAME="" SUMMARY="" DURATION=0 FILES=0

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)  PROJECT="$2"; shift 2 ;;
    --phase)    PHASE="$2"; shift 2 ;;
    --name)     NAME="$2"; shift 2 ;;
    --summary)  SUMMARY="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --files)    FILES="$2"; shift 2 ;;
    -h|--help)  usage ;;
    *)          echo "Unknown arg: $1"; usage ;;
  esac
done

# Validate required
[[ -z "$PROJECT" ]] && { echo "Error: --project is required"; usage; }
[[ -z "$PHASE" ]]   && { echo "Error: --phase is required"; usage; }
[[ -z "$NAME" ]]    && { echo "Error: --name is required"; usage; }
[[ -z "$SUMMARY" ]] && { echo "Error: --summary is required"; usage; }
[[ -z "${AF_WEBHOOK_SECRET:-}" ]] && { echo "Error: AF_WEBHOOK_SECRET env var is required"; exit 1; }

WEBHOOK_URL="${N8N_WEBHOOK_URL:-https://mayi.ewutelo.cloud/webhook/af-phase-complete}"

PAYLOAD=$(jq -n \
  --arg project_name "$PROJECT" \
  --argjson phase_number "$PHASE" \
  --arg phase_name "$NAME" \
  --arg summary "$SUMMARY" \
  --argjson duration_min "$DURATION" \
  --argjson files_changed "$FILES" \
  '{
    project_name: $project_name,
    phase_number: $phase_number,
    phase_name: $phase_name,
    summary: $summary,
    duration_min: $duration_min,
    files_changed: $files_changed,
    decisions: []
  }')

HTTP_CODE=$(curl -s -o /tmp/af-phase-response.json -w "%{http_code}" \
  -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-AF-Secret: $AF_WEBHOOK_SECRET" \
  -d "$PAYLOAD")

RESPONSE=$(cat /tmp/af-phase-response.json)

if [[ "$HTTP_CODE" == "200" ]]; then
  echo "OK: Phase $PHASE ($NAME) logged for $PROJECT"
  echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
  exit 0
else
  echo "FAIL: HTTP $HTTP_CODE"
  echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
  exit 1
fi
```

- [ ] **Step 2: Make executable**

Run: `chmod +x scripts/af-notify-phase.sh`

- [ ] **Step 3: Verify script parses args correctly**

Run: `./scripts/af-notify-phase.sh --help`
Expected: Usage text printed, exit 0.

Run: `./scripts/af-notify-phase.sh --project test`
Expected: Error about missing `--phase`, exit 1.

Run: `./scripts/af-notify-phase.sh --project test --phase 1 --name "Test" --summary "Test"`
Expected: Error about missing `AF_WEBHOOK_SECRET`, exit 1.

- [ ] **Step 4: Commit**

```bash
git add scripts/af-notify-phase.sh
git commit -m "feat(app-factory): add af-notify-phase.sh CLI script for phase completion webhook"
```

---

### Task 2: Add 6 New Nodes to `af-phase-complete.json`

**Files:**
- Modify: `scripts/n8n-workflows/af-phase-complete.json`

**Reference:** Spec section 3.1 defines all 6 nodes. The existing workflow has 13 nodes. We add 6 new ones to the `nodes` array.

- [ ] **Step 1: Read the current workflow file**

Read: `scripts/n8n-workflows/af-phase-complete.json`
Note the last node's position (error-telegram at [690, 600]) and the existing node IDs.

- [ ] **Step 2: Move existing nodes right to make room**

The new nodes will occupy positions [910..2230, 300]. The existing `NocoDB Insert Phase Log` is at [910, 300] — move it and all downstream existing nodes to new positions FIRST, before adding new nodes.

| Node | Old Position | New Position |
|------|-------------|-------------|
| `NocoDB Insert Phase Log` | [910, 300] | [1350, 200] |
| `Split Decisions` | [1130, 300] | [2450, 300] |
| `Has Decisions?` | [1350, 300] | [2670, 300] |
| `NocoDB Insert Decision` | [1570, 200] | [2890, 200] |
| `No Decisions` | [1570, 400] | [2890, 400] |
| `Call REX Indexer` | [1790, 300] | [3110, 300] |
| `Respond OK` | [2010, 300] | [3330, 300] |

Edit each node's `"position"` array in the JSON.

- [ ] **Step 3: Add Node 1 — `Check Duplicate Phase Log`**

Insert after the `parse-phase` node in the `nodes` array. This is an HTTP GET to check if a phase_log already exists for this (project_name, phase_number) pair.

```json
{
  "id": "check-duplicate",
  "name": "Check Duplicate Phase Log",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [910, 300],
  "parameters": {
    "method": "GET",
    "url": "=http://javisi_nocodb:8080/api/v2/tables/mx5x4nb739fjld1/records?where=(project_name,eq,{{ encodeURIComponent($json.project_name) }})~and(phase_number,eq,{{ $json.phase_number }})&limit=1",
    "sendHeaders": true,
    "headerParameters": {
      "parameters": [
        { "name": "xc-token", "value": "={{ $env.NOCODB_API_TOKEN }}" },
        { "name": "Content-Type", "value": "application/json" }
      ]
    },
    "options": {}
  }
}
```

- [ ] **Step 4: Add Node 2 — `Is New Phase?`**

```json
{
  "id": "is-new-phase",
  "name": "Is New Phase?",
  "type": "n8n-nodes-base.if",
  "typeVersion": 2,
  "position": [1130, 300],
  "parameters": {
    "conditions": {
      "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "strict" },
      "conditions": [
        {
          "id": "condition-new-phase",
          "leftValue": "={{ $json.pageInfo.totalRows }}",
          "rightValue": 0,
          "operator": { "type": "number", "operation": "equals" }
        }
      ],
      "combinator": "and"
    },
    "options": {}
  }
}
```

- [ ] **Step 5: Add Node 3 — `Fetch Current Status`**

```json
{
  "id": "fetch-current-status",
  "name": "Fetch Current Status",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [1570, 300],
  "parameters": {
    "method": "GET",
    "url": "=http://javisi_nocodb:8080/api/v2/tables/mvhxrbdyetpoyjb/records?where=(name,eq,{{ encodeURIComponent($('Parse Phase Data').first().json.project_name) }})&fields=status&limit=1",
    "sendHeaders": true,
    "headerParameters": {
      "parameters": [
        { "name": "xc-token", "value": "={{ $env.NOCODB_API_TOKEN }}" },
        { "name": "Content-Type", "value": "application/json" }
      ]
    },
    "options": {}
  }
}
```

- [ ] **Step 6: Add Node 4 — `Count Phase Logs`**

```json
{
  "id": "count-phase-logs",
  "name": "Count Phase Logs",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [1790, 300],
  "parameters": {
    "method": "GET",
    "url": "=http://javisi_nocodb:8080/api/v2/tables/mx5x4nb739fjld1/records?where=(project_name,eq,{{ encodeURIComponent($('Parse Phase Data').first().json.project_name) }})&fields=duration_min&limit=1000",
    "sendHeaders": true,
    "headerParameters": {
      "parameters": [
        { "name": "xc-token", "value": "={{ $env.NOCODB_API_TOKEN }}" },
        { "name": "Content-Type", "value": "application/json" }
      ]
    },
    "options": {}
  }
}
```

- [ ] **Step 7: Add Node 5 — `Compute Project Status`**

```json
{
  "id": "compute-status",
  "name": "Compute Project Status",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [2010, 300],
  "parameters": {
    "jsCode": "const countResult = $('Count Phase Logs').first().json;\nconst records = countResult.list || [];\nconst phases_completed = countResult.pageInfo?.totalRows || 0;\nconst total_duration = records.reduce((sum, r) => sum + (r.duration_min || 0), 0);\n\nconst statusResult = $('Fetch Current Status').first().json;\nconst current_status = (statusResult.list && statusResult.list[0]?.status) || 'intake';\n\nlet new_status = current_status;\nif (current_status === 'intake' || current_status === 'design') {\n  new_status = 'building';\n}\n\nreturn [{\n  json: {\n    project_name: $('Parse Phase Data').first().json.project_name,\n    phases_completed,\n    total_duration,\n    status: new_status\n  }\n}];"
  }
}
```

- [ ] **Step 8: Add Node 6 — `NocoDB Update Project`**

```json
{
  "id": "nocodb-update-project",
  "name": "NocoDB Update Project",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [2230, 300],
  "parameters": {
    "method": "PATCH",
    "url": "=http://javisi_nocodb:8080/api/v2/tables/mvhxrbdyetpoyjb/records?where=(name,eq,{{ encodeURIComponent($json.project_name) }})",
    "sendHeaders": true,
    "headerParameters": {
      "parameters": [
        { "name": "xc-token", "value": "={{ $env.NOCODB_API_TOKEN }}" },
        { "name": "Content-Type", "value": "application/json" }
      ]
    },
    "sendBody": true,
    "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ phases_completed: $json.phases_completed, total_duration: $json.total_duration, status: $json.status }) }}",
    "options": {}
  }
}
```

- [ ] **Step 9: Verify JSON is valid**

Run: `python3 -c "import json; json.load(open('scripts/n8n-workflows/af-phase-complete.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 10: Commit**

```bash
git add scripts/n8n-workflows/af-phase-complete.json
git commit -m "feat(app-factory): add project status update nodes to af-phase-complete workflow"
```

---

### Task 3: Rewire Connections in `af-phase-complete.json`

**Files:**
- Modify: `scripts/n8n-workflows/af-phase-complete.json` (connections section)

**Reference:** Spec section 3.2 flow diagram.

- [ ] **Step 1: Replace the `connections` object**

The full new connections object. Changes from original:
- `Parse Phase Data` → `Check Duplicate Phase Log` (was → `NocoDB Insert Phase Log`)
- New: `Check Duplicate Phase Log` → `Is New Phase?`
- New: `Is New Phase?` true → `NocoDB Insert Phase Log`, false → `Fetch Current Status`
- `NocoDB Insert Phase Log` → `Fetch Current Status` (was → `Split Decisions`)
- New: `Fetch Current Status` → `Count Phase Logs`
- New: `Count Phase Logs` → `Compute Project Status`
- New: `Compute Project Status` → `NocoDB Update Project`
- New: `NocoDB Update Project` → `Split Decisions`
- All other connections remain unchanged (`Split Decisions` → `Has Decisions?` → etc.)

```json
{
  "Webhook Phase Complete": {
    "main": [[{ "node": "Validate AF Secret", "type": "main", "index": 0 }]]
  },
  "Validate AF Secret": {
    "main": [
      [{ "node": "Parse Phase Data", "type": "main", "index": 0 }],
      [{ "node": "Respond 403", "type": "main", "index": 0 }]
    ]
  },
  "Parse Phase Data": {
    "main": [[{ "node": "Check Duplicate Phase Log", "type": "main", "index": 0 }]]
  },
  "Check Duplicate Phase Log": {
    "main": [[{ "node": "Is New Phase?", "type": "main", "index": 0 }]]
  },
  "Is New Phase?": {
    "main": [
      [{ "node": "NocoDB Insert Phase Log", "type": "main", "index": 0 }],
      [{ "node": "Fetch Current Status", "type": "main", "index": 0 }]
    ]
  },
  "NocoDB Insert Phase Log": {
    "main": [[{ "node": "Fetch Current Status", "type": "main", "index": 0 }]]
  },
  "Fetch Current Status": {
    "main": [[{ "node": "Count Phase Logs", "type": "main", "index": 0 }]]
  },
  "Count Phase Logs": {
    "main": [[{ "node": "Compute Project Status", "type": "main", "index": 0 }]]
  },
  "Compute Project Status": {
    "main": [[{ "node": "NocoDB Update Project", "type": "main", "index": 0 }]]
  },
  "NocoDB Update Project": {
    "main": [[{ "node": "Split Decisions", "type": "main", "index": 0 }]]
  },
  "Split Decisions": {
    "main": [[{ "node": "Has Decisions?", "type": "main", "index": 0 }]]
  },
  "Has Decisions?": {
    "main": [
      [{ "node": "NocoDB Insert Decision", "type": "main", "index": 0 }],
      [{ "node": "No Decisions", "type": "main", "index": 0 }]
    ]
  },
  "NocoDB Insert Decision": {
    "main": [[{ "node": "Call REX Indexer", "type": "main", "index": 0 }]]
  },
  "No Decisions": {
    "main": [[{ "node": "Call REX Indexer", "type": "main", "index": 0 }]]
  },
  "Call REX Indexer": {
    "main": [[{ "node": "Respond OK", "type": "main", "index": 0 }]]
  },
  "Error Trigger": {
    "main": [[{ "node": "NocoDB Log Error", "type": "main", "index": 0 }]]
  },
  "NocoDB Log Error": {
    "main": [[{ "node": "Telegram Alert Error", "type": "main", "index": 0 }]]
  }
}
```

- [ ] **Step 2: Update Respond OK response body**

Change the `Respond OK` node's `responseBody` to include project update info:

```json
"responseBody": "={{ JSON.stringify({ ok: true, project_updated: true, status: $('Compute Project Status').first().json.status, phases_completed: $('Compute Project Status').first().json.phases_completed, rex_indexed: true }) }}"
```

- [ ] **Step 3: Verify JSON is valid**

Run: `python3 -c "import json; json.load(open('scripts/n8n-workflows/af-phase-complete.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Verify all node names in connections exist in nodes array**

Run: `python3 -c "
import json
wf = json.load(open('scripts/n8n-workflows/af-phase-complete.json'))
node_names = {n['name'] for n in wf['nodes']}
for src, conn in wf['connections'].items():
    assert src in node_names, f'Connection source not found: {src}'
    for branch in conn.get('main', []):
        for target in branch:
            assert target['node'] in node_names, f'Connection target not found: {target[\"node\"]}'
print(f'OK: {len(node_names)} nodes, all connections valid')
"`
Expected: `OK: 19 nodes, all connections valid`

- [ ] **Step 5: Commit**

```bash
git add scripts/n8n-workflows/af-phase-complete.json
git commit -m "feat(app-factory): rewire af-phase-complete connections for project status update flow"
```

---

### Task 4: Add Claude Code Hook to `.claude/settings.json`

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Read the current file**

Read: `.claude/settings.json`
Currently has only `permissions` key.

- [ ] **Step 2: Add the `hooks` section**

Add `hooks` key alongside the existing `permissions` key:

```json
{
  "permissions": {
    "allow": [
      "Bash(make:*)",
      ...existing entries...
    ],
    "deny": []
  },
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

Only add the `hooks` key — do NOT modify the existing `permissions` section.

- [ ] **Step 3: Verify JSON is valid**

Run: `python3 -c "import json; json.load(open('.claude/settings.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "feat(app-factory): add postToolResult hook for phase completion reminder"
```

---

### Task 5: Validate Complete Workflow and Final Commit

**Files:**
- Read: `scripts/n8n-workflows/af-phase-complete.json` (verify final state)
- Read: `scripts/af-notify-phase.sh` (verify final state)
- Read: `.claude/settings.json` (verify final state)

- [ ] **Step 1: Validate workflow JSON structure**

Run: `python3 -c "
import json
wf = json.load(open('scripts/n8n-workflows/af-phase-complete.json'))

# Check node count
assert len(wf['nodes']) == 19, f'Expected 19 nodes, got {len(wf[\"nodes\"])}'

# Check new nodes exist
new_nodes = ['Check Duplicate Phase Log', 'Is New Phase?', 'Fetch Current Status', 'Count Phase Logs', 'Compute Project Status', 'NocoDB Update Project']
existing = {n['name'] for n in wf['nodes']}
for name in new_nodes:
    assert name in existing, f'Missing node: {name}'

# Check connections reference valid nodes
for src, conn in wf['connections'].items():
    assert src in existing, f'Bad connection source: {src}'
    for branch in conn.get('main', []):
        for target in branch:
            assert target['node'] in existing, f'Bad connection target: {target[\"node\"]}'

# Check key flow: Parse → Check Duplicate → Is New Phase? → ... → Update Project → Split Decisions
flow = ['Parse Phase Data', 'Check Duplicate Phase Log', 'Is New Phase?']
for i in range(len(flow) - 1):
    targets = [t['node'] for branch in wf['connections'][flow[i]]['main'] for t in branch]
    assert flow[i+1] in targets, f'{flow[i]} does not connect to {flow[i+1]}'

print('ALL CHECKS PASSED')
"`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 2: Validate CLI script**

Run: `bash -n scripts/af-notify-phase.sh && echo 'Syntax OK'`
Expected: `Syntax OK`

Run: `./scripts/af-notify-phase.sh --help 2>&1 | head -3`
Expected: Shows usage text.

- [ ] **Step 3: Validate settings.json**

Run: `python3 -c "
import json
s = json.load(open('.claude/settings.json'))
assert 'hooks' in s, 'Missing hooks key'
assert 'postToolResult' in s['hooks'], 'Missing postToolResult'
assert len(s['hooks']['postToolResult']) == 1, 'Expected 1 hook'
assert 'permissions' in s, 'Missing permissions (should be preserved)'
print('Settings OK')
"`
Expected: `Settings OK`
