# MOP Generator — n8n Multi-Step Form Workflow Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy, activate, and E2E-validate the n8n multi-step form workflow `mop-generator-v1` (ID `CP5gJrn1e2zZbPxh`) on Sese-AI so that a technician filling the 3-page form at `https://mayi.ewutelo.cloud/form/mop-generator` receives the generated PDF in their browser.

**Architecture:** File-first (not UI-first) n8n workflow management. The canonical source is `scripts/n8n-workflows/mop-generator-v1.json` — a git-tracked JSON file. Deployment uses `n8n import:workflow` CLI on a clean-slate DB (no UI editing, which caused the phantom stale-cache bug in exec 11740). The workflow chains: Intake (page 1) → Context (page 2) → Steps (page 3) → Aggregate (payload build) → HTTP Request (calls the already-working `mop-webhook-render-v1` webhook which returns `{id}` after Gotenberg render + disk persist) → Read PDF (loads `/data/mop/pdf/<id>.pdf` into `binary.data`) → Done (PDF) form completion with `respondWith=returnBinary, inputDataFieldName=data`. Error branches from HTTP Request and Read PDF converge on Done (Error).

**Tech Stack:** n8n 2.7.3 (form trigger v2.5, form v2.5, set v3.4, httpRequest v4.4, readWriteFile v1.1), PostgreSQL 18.3 (n8n state), Gotenberg (rendering, via the sibling webhook workflow), Caddy (TLS, VPN ACL), Tailscale (`100.64.0.14`), Node.js 20 (E2E test script).

**Reference spec:** `docs/superpowers/specs/2026-04-11-mop-machinery-design.md`
**Parent plan:** `docs/superpowers/plans/2026-04-11-mop-machinery-implementation.md` (this plan supersedes Task 3.4 within it).
**Debugging REX:** `docs/REX-SESSION-2026-04-11.md` (phantom cache root cause analysis).

---

## Context: Why a Focused Plan

The parent plan `2026-04-11-mop-machinery-implementation.md` Task 3.4 said "Build in n8n UI" with a node list only — no exact configs, no import protocol, no phantom-cache mitigation. A live debugging session on 2026-04-11 hit a phantom stale workflow definition in exec 11740 where `nodeExecutionStack[0]` referenced a non-existent "Render & Load" node with `typeVersion=1, position=[1140,240]` — proving UI-editing created drift between the DB `workflow_entity` and whatever runtime cache the form trigger reads. The solution is file-first deployment: never edit in the UI, always import from a versioned JSON.

## Pre-requisites (must be true before Task 1)

- Sese-AI reachable via Tailscale: `ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14` returns a shell.
- `javisi_n8n` container running (check: `docker ps | grep javisi_n8n`).
- `javisi_gotenberg` container running and healthy.
- `javisi_postgresql` container running.
- Sibling workflow `mop-webhook-render-v1` imported, active, and proven working (exec 11741 success during debug session 2026-04-11).
- Volume mounts in n8n compose: `/opt/javisi/data/mop → /data/mop` (contains `pdf/`, `templates/`, `index/`).
- Webhook `/webhook/mop-render` (POST) resolvable from inside `javisi_n8n` container at `http://localhost:5678/webhook/mop-render`.
- Caddy routes `mayi.ewutelo.cloud` → `javisi_n8n:5678` with VPN ACL enforced.
- Local repo has `scripts/n8n-workflows/mop-generator-v1.json` (8 nodes, 331 lines) — confirmed present, uncommitted.

## File Structure

- **Canonical workflow source:** `scripts/n8n-workflows/mop-generator-v1.json` — git-tracked, the ONLY place to edit this workflow.
- **Sibling workflow (already committed & working):** `scripts/n8n-workflows/mop-webhook-render-v1.json`.
- **E2E test harness:** `scripts/mop/e2e-mop-generator.js` (new file, replaces the prior `/tmp/mop-e2e-v3.js` which had a bug handling the `form-waiting` terminal state).
- **Deployment helper:** `scripts/mop/deploy-mop-generator.sh` (new file, automates clean-slate import + double restart).
- **REX update:** `docs/REX-SESSION-2026-04-11.md` (append "Clean import protocol & E2E validation" section).
- **Research doc update:** `.planning/research/mop-gotenberg-n8n.md` (append protocol findings — multipart requirement, phantom-cache trap, form-waiting terminal state, double-restart after activate).

---

## Task 1: Pre-flight Verification

**Purpose:** Confirm the environment is ready before touching n8n state. Catch missing prerequisites early.

**Files:**
- Read-only checks; no files created.

- [ ] **Step 1.1: Verify Tailscale SSH reachability**

Run: `ssh -i ~/.ssh/seko-vpn-deploy -p 804 -o ConnectTimeout=5 mobuone@100.64.0.14 'hostname && uptime'`
Expected: `sese-ai` (or the server hostname) + uptime line. Must NOT use `137.74.114.167`.

- [ ] **Step 1.2: Verify n8n, Postgres, Gotenberg containers**

Run:
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'javisi_(n8n|postgresql|gotenberg)'"
```
Expected: 3 lines, all `Up <duration> (healthy)` or `Up <duration>`.

- [ ] **Step 1.3: Verify `mop-webhook-render-v1` is active and working**

Run (copy to one line or heredoc on remote):
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 bash <<'REMOTE'
PG=$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
docker exec -i -e PGPASSWORD="$PG" javisi_postgresql \
  psql -h 127.0.0.1 -U n8n -d n8n -tAc \
  "SELECT id, name, active FROM workflow_entity WHERE name='mop-webhook-render-v1';"
REMOTE
```
Expected: `<id>|mop-webhook-render-v1|t` (active=true).

- [ ] **Step 1.4: Verify volume mounts and template files**

Run:
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  "docker exec javisi_n8n ls -la /data/mop/templates/mop.html /data/mop/templates/mop.css /data/mop/pdf/ /data/mop/index/ 2>&1 | head -20"
```
Expected: `mop.html` and `mop.css` exist; `pdf/` and `index/` are directories.

- [ ] **Step 1.5: Smoke test `mop-webhook-render-v1` end-to-end**

Run (from workstation):
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 bash <<'REMOTE'
docker exec javisi_n8n wget -qO- --post-data='{"title":"preflight","severity":"minor","perimeter":"test","incident":"preflight check","steps":[{"title":"s1","body":"b1","link_sp":"SP-001"}]}' \
  --header='Content-Type: application/json' \
  http://127.0.0.1:5678/webhook/mop-render
REMOTE
```
Expected: JSON response `{"ok":true,"id":"<N>","url":"...","bytes":<N>,"statusCode":200}`. If not, STOP — fix the sibling workflow first; there is no point importing the form workflow.

- [ ] **Step 1.6: Verify Caddy HTTPS route via Tailscale**

Run: `curl -sI https://mayi.ewutelo.cloud/form/mop-generator 2>&1 | head -3`
Expected: `HTTP/2 200` or `HTTP/2 404` (404 is OK here — it just means workflow is not yet active; 5xx or 000 means Caddy/network problem).

---

## Task 2: Verify Canonical Workflow JSON

**Purpose:** The file `scripts/n8n-workflows/mop-generator-v1.json` is the source of truth. Before deploying, verify it is structurally correct and matches the schema n8n expects.

**Files:**
- Read: `scripts/n8n-workflows/mop-generator-v1.json`

- [ ] **Step 2.1: Validate JSON syntax**

Run: `python3 -c "import json; json.load(open('scripts/n8n-workflows/mop-generator-v1.json')); print('OK')"`
Expected: `OK`. Any `JSONDecodeError` → fix the file first.

- [ ] **Step 2.2: Verify node count, IDs, typeVersions, positions**

Run:
```bash
python3 <<'PY'
import json
wf = json.load(open('scripts/n8n-workflows/mop-generator-v1.json'))
expected = [
    ("Intake",      "n8n-nodes-base.formTrigger", 2.5, "001"),
    ("Context",     "n8n-nodes-base.form",        2.5, "002"),
    ("Steps",       "n8n-nodes-base.form",        2.5, "003"),
    ("Aggregate",   "n8n-nodes-base.set",         3.4, "004"),
    ("HTTP Request","n8n-nodes-base.httpRequest", 4.4, "005"),
    ("Read PDF",    "n8n-nodes-base.readWriteFile",1.1, "006"),
    ("Done (PDF)",  "n8n-nodes-base.form",        2.5, "007"),
    ("Done (Error)","n8n-nodes-base.form",        2.5, "008"),
]
nodes = {n["name"]: n for n in wf["nodes"]}
assert len(nodes) == 8, f"expected 8 nodes, got {len(nodes)}"
for name, t, tv, suffix in expected:
    n = nodes[name]
    assert n["type"] == t, f"{name}: type {n['type']} != {t}"
    assert n["typeVersion"] == tv, f"{name}: tv {n['typeVersion']} != {tv}"
    assert n["id"].endswith(suffix), f"{name}: id {n['id']} does not end with {suffix}"
# Assert NO 'Render & Load' node (phantom from 2026-04-11 debugging)
assert "Render & Load" not in nodes, "phantom 'Render & Load' node present — reject"
print("OK: 8 nodes, no phantom")
PY
```
Expected: `OK: 8 nodes, no phantom`.

- [ ] **Step 2.3: Verify webhook path and binary field wiring**

Run:
```bash
python3 <<'PY'
import json
wf = json.load(open('scripts/n8n-workflows/mop-generator-v1.json'))
nodes = {n["name"]: n for n in wf["nodes"]}
assert nodes["Intake"]["parameters"]["path"] == "mop-generator"
assert nodes["Intake"]["webhookId"] == "mop-generator"
# HTTP Request targets the sibling webhook via localhost (inside container network)
assert nodes["HTTP Request"]["parameters"]["url"] == "http://localhost:5678/webhook/mop-render"
# Binary chain: Read PDF.dataPropertyName == Done (PDF).inputDataFieldName
assert nodes["Read PDF"]["parameters"]["options"]["dataPropertyName"] == "data"
assert nodes["Done (PDF)"]["parameters"]["inputDataFieldName"] == "data"
assert nodes["Done (PDF)"]["parameters"]["respondWith"] == "returnBinary"
# Done (Error) uses showText with expression
assert nodes["Done (Error)"]["parameters"]["respondWith"] == "showText"
# onError wiring for resilience
assert nodes["HTTP Request"].get("onError") == "continueErrorOutput"
assert nodes["Read PDF"].get("onError") == "continueErrorOutput"
print("OK: wiring correct")
PY
```
Expected: `OK: wiring correct`.

- [ ] **Step 2.4: Verify connections graph (HTTP Request has 2 outputs, Read PDF has 2 outputs)**

Run:
```bash
python3 <<'PY'
import json
wf = json.load(open('scripts/n8n-workflows/mop-generator-v1.json'))
c = wf["connections"]
# Linear chain up to HTTP Request
chain = [("Intake","Context"),("Context","Steps"),("Steps","Aggregate"),("Aggregate","HTTP Request")]
for src, dst in chain:
    assert c[src]["main"][0][0]["node"] == dst, f"{src} → {dst} broken"
# HTTP Request: output[0] → Read PDF, output[1] → Done (Error)
hr = c["HTTP Request"]["main"]
assert len(hr) == 2 and hr[0][0]["node"] == "Read PDF" and hr[1][0]["node"] == "Done (Error)"
# Read PDF: output[0] → Done (PDF), output[1] → Done (Error)
rp = c["Read PDF"]["main"]
assert len(rp) == 2 and rp[0][0]["node"] == "Done (PDF)" and rp[1][0]["node"] == "Done (Error)"
print("OK: connections correct")
PY
```
Expected: `OK: connections correct`.

- [ ] **Step 2.5: Commit the JSON file (first commit — it was uncommitted)**

Run:
```bash
cd /home/mobuone/VPAI
git add scripts/n8n-workflows/mop-generator-v1.json
git commit -m "feat(mop): add mop-generator-v1 n8n multi-step form workflow JSON

File-first source of truth for the technician-facing 3-page form
that produces a PDF MOP via the mop-webhook-render-v1 sibling workflow.
Deployment via n8n import:workflow CLI, never UI editing.
Ref: docs/superpowers/plans/2026-04-11-mop-workflow-n8n-multistep.md"
```

---

## Task 3: Write the Deployment Helper Script

**Purpose:** Codify the clean-slate import protocol so it is repeatable and can't drift. No UI editing ever.

**Files:**
- Create: `scripts/mop/deploy-mop-generator.sh`

- [ ] **Step 3.1: Write the deployment helper**

Create `scripts/mop/deploy-mop-generator.sh`:
```bash
#!/bin/bash
# Clean-slate deploy of mop-generator-v1 to Sese-AI via Tailscale.
#
# Protocol (file-first, never UI):
#   1. Copy canonical JSON to n8n container
#   2. Deactivate + delete all executions for workflow id
#   3. Restart n8n (flush runtime cache, wave 1)
#   4. import:workflow --input=... (upsert by id)
#   5. update:workflow --active=true
#   6. Restart n8n (flush runtime cache, wave 2 — n8n CLI emits
#      "Please restart n8n for changes to take effect" after update)
#   7. Wait for /healthz
#   8. Verify workflow_entity active + webhook_entity rows present
#
# Usage: ./scripts/mop/deploy-mop-generator.sh
#
# Requires: SSH alias / key to Sese-AI Tailscale IP (100.64.0.14).

set -euo pipefail

REMOTE="mobuone@100.64.0.14"
SSH_KEY="$HOME/.ssh/seko-vpn-deploy"
SSH_PORT="804"
SSH="ssh -i $SSH_KEY -p $SSH_PORT $REMOTE"
SCP="scp -i $SSH_KEY -P $SSH_PORT"

WF_ID="CP5gJrn1e2zZbPxh"
WF_NAME="mop-generator-v1"
LOCAL_JSON="scripts/n8n-workflows/mop-generator-v1.json"

echo "== [1/8] Copy canonical JSON to remote tmp =="
$SCP "$LOCAL_JSON" "$REMOTE:/tmp/mop-generator-v1.json"

echo "== [2/8] Deactivate + wipe executions =="
$SSH bash <<REMOTE_SCRIPT
set -euo pipefail
PG=\$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
PSQL="docker exec -i -e PGPASSWORD=\$PG javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n"
\$PSQL -c "UPDATE workflow_entity SET active=false WHERE id='${WF_ID}';" || true
\$PSQL -c "DELETE FROM execution_data WHERE \"executionId\" IN (SELECT id FROM execution_entity WHERE \"workflowId\"='${WF_ID}');"
\$PSQL -c "DELETE FROM execution_entity WHERE \"workflowId\"='${WF_ID}';"
REMOTE_SCRIPT

echo "== [3/8] Restart n8n (wave 1 — flush runtime cache pre-import) =="
$SSH 'docker restart javisi_n8n >/dev/null'
sleep 12

echo "== [4/8] Wait for /healthz =="
$SSH bash <<'REMOTE_SCRIPT'
for i in $(seq 1 20); do
  if docker exec javisi_n8n wget -qO- http://127.0.0.1:5678/healthz 2>/dev/null | grep -q ok; then
    echo "  ready after ${i}s"; exit 0
  fi
  sleep 2
done
echo "TIMEOUT waiting for /healthz"; exit 1
REMOTE_SCRIPT

echo "== [5/8] Copy JSON into container and import =="
$SSH 'docker cp /tmp/mop-generator-v1.json javisi_n8n:/tmp/mop-generator-v1.json'
$SSH 'docker exec javisi_n8n n8n import:workflow --input=/tmp/mop-generator-v1.json 2>&1 | tail -10'

echo "== [6/8] Activate workflow via CLI =="
$SSH "docker exec javisi_n8n n8n update:workflow --id=${WF_ID} --active=true 2>&1 | tail -5"

echo "== [7/8] Restart n8n (wave 2 — CLI warns 'restart required for changes to take effect') =="
$SSH 'docker restart javisi_n8n >/dev/null'
sleep 12
$SSH bash <<'REMOTE_SCRIPT'
for i in $(seq 1 20); do
  if docker exec javisi_n8n wget -qO- http://127.0.0.1:5678/healthz 2>/dev/null | grep -q ok; then
    echo "  ready after ${i}s"; exit 0
  fi
  sleep 2
done
echo "TIMEOUT waiting for /healthz"; exit 1
REMOTE_SCRIPT

echo "== [8/8] Verify workflow_entity + webhook_entity =="
$SSH bash <<REMOTE_SCRIPT
set -euo pipefail
PG=\$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
PSQL="docker exec -i -e PGPASSWORD=\$PG javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n"
echo "-- workflow_entity:"
\$PSQL -c "SELECT id, name, active, \"updatedAt\" FROM workflow_entity WHERE id='${WF_ID}';"
echo "-- webhook_entity (GET+POST for 'mop-generator'):"
\$PSQL -c "SELECT method, \"webhookPath\", \"workflowId\" FROM webhook_entity WHERE \"webhookPath\" LIKE '%mop-generator%';"
REMOTE_SCRIPT

echo
echo "== DEPLOY OK =="
echo "Form URL: https://mayi.ewutelo.cloud/form/mop-generator"
```

Then: `chmod +x scripts/mop/deploy-mop-generator.sh`

- [ ] **Step 3.2: Shellcheck the script**

Run: `shellcheck scripts/mop/deploy-mop-generator.sh 2>&1 | head -30`
Expected: Clean, or only SC2034/SC2086 warnings you can justify. Fix any SC2016 / SC2155 / SC2046 / SC2181.

- [ ] **Step 3.3: Commit the helper**

Run:
```bash
git add scripts/mop/deploy-mop-generator.sh
git commit -m "feat(mop): add clean-slate deploy helper for mop-generator-v1

Codifies the file-first import protocol: wipe executions → restart n8n
→ import:workflow → update --active=true → restart n8n → verify.

Double-restart is intentional: n8n CLI emits 'restart required for
changes to take effect' after update:workflow, and live debugging
on 2026-04-11 proved the runtime cache needs flushing on both sides
of the activate call to avoid stale workflow definitions in
nodeExecutionStack."
```

---

## Task 4: Execute Clean-Slate Deployment

**Purpose:** Run the deployment helper and land `mop-generator-v1` in the known-good state.

- [ ] **Step 4.1: Run the deploy helper**

Run: `./scripts/mop/deploy-mop-generator.sh 2>&1 | tee /tmp/mop-deploy.log`
Expected terminal output (key lines):
- `== [1/8] ... ==` through `== [8/8] ... ==` all visible
- `Successfully imported 1 workflow` (or similar n8n CLI message)
- `Activated workflow: mop-generator-v1`
- `workflow_entity:` row with `active=t`
- `webhook_entity:` two rows: `GET|mop-generator|CP5gJrn1e2zZbPxh` and `POST|mop-generator|CP5gJrn1e2zZbPxh`
- `== DEPLOY OK ==`

If any step fails: STOP, read `/tmp/mop-deploy.log`, do NOT proceed to Task 5.

- [ ] **Step 4.2: Sanity HTTP check via public HTTPS (Tailscale split DNS)**

Run: `curl -sI https://mayi.ewutelo.cloud/form/mop-generator 2>&1 | head -3`
Expected: `HTTP/2 200` (now that workflow is active).

- [ ] **Step 4.3: Fetch page 1 HTML and verify form fields render**

Run: `curl -sS https://mayi.ewutelo.cloud/form/mop-generator | grep -oE '(name="field-[0-9]"|Generate MOP|Step 1/3)' | sort -u`
Expected: `Generate MOP`, `Step 1/3`, `name="field-0"`, `name="field-1"`, `name="field-2"`.

---

## Task 5: Write the E2E Test Harness

**Purpose:** A repeatable, deterministic test that walks all 3 form pages, polls execution status, and saves the resulting PDF to disk. Replaces the buggy `/tmp/mop-e2e-v3.js` that only handled `success` (not `form-waiting`) as terminal state.

**Files:**
- Create: `scripts/mop/e2e-mop-generator.js`

- [ ] **Step 5.1: Write the test**

Create `scripts/mop/e2e-mop-generator.js`:
```javascript
// E2E test for n8n multi-step form `mop-generator-v1` via Tailscale HTTPS.
//
// Protocol (n8n form v2.5 multi-step):
//   POST /form/mop-generator          → 200 JSON {formWaitingUrl}
//   GET  {formWaitingUrl}/n8n-execution-status   (poll until 'form-waiting' or 'success')
//   GET  {formWaitingUrl}             → page 2 HTML
//   POST {formWaitingUrl}             → 200 JSON {formWaitingUrl (page 3)}
//   ... repeat for page 3
//   POST {formWaitingUrl}             → final completion
//   Poll status until 'success'       → GET {formWaitingUrl} to fetch binary PDF
//
// Terminal states handled: 'form-waiting' (next page) + 'success' (final). Prior
// /tmp/mop-e2e-v3.js only handled 'success' as terminal — missed the case where the
// completion node's form-waiting page IS the final PDF binary response.
//
// Transport: HTTPS via Caddy on mayi.ewutelo.cloud (split DNS → Tailscale 100.64.0.14).
// Usage: node scripts/mop/e2e-mop-generator.js [output.pdf]
// Exit: 0 = PDF saved, 1 = failure.

const https = require('https');
const fs = require('fs');

const HOST = 'mayi.ewutelo.cloud';
const PORT = 443;
const OUT_PDF = process.argv[2] || '/tmp/mop-e2e-result.pdf';
const BOUNDARY = '----MopE2EBoundary' + Date.now();

function multipart(fields) {
  const parts = [];
  for (const [k, v] of Object.entries(fields)) {
    parts.push('--' + BOUNDARY);
    parts.push('Content-Disposition: form-data; name="' + k + '"');
    parts.push('');
    parts.push(String(v));
  }
  parts.push('--' + BOUNDARY + '--', '');
  return parts.join('\r\n');
}

function req(method, path, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const opts = {
      hostname: HOST,
      port: PORT,
      path,
      method,
      headers: Object.assign({ host: HOST, 'user-agent': 'mop-e2e/1.0' }, headers),
      timeout: 60000,
    };
    const r = https.request(opts, (res) => {
      const ch = [];
      res.on('data', (c) => ch.push(c));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(ch) }));
    });
    r.on('error', reject);
    r.on('timeout', () => r.destroy(new Error('timeout ' + method + ' ' + path)));
    if (body) r.write(body);
    r.end();
  });
}

function postForm(path, fields) {
  const body = multipart(fields);
  return req('POST', path, body, {
    'content-type': 'multipart/form-data; boundary=' + BOUNDARY,
    'content-length': Buffer.byteLength(body),
  });
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function pollStatus(waitPath, label, maxAttempts = 120) {
  const statusPath = waitPath + '/n8n-execution-status';
  let interval = 500;
  for (let i = 0; i < maxAttempts; i++) {
    const r = await req('GET', statusPath, null, {});
    const text = r.body.toString('utf8').trim();
    process.stdout.write(`    [${label}] poll ${i + 1} [${r.status}]: ${text}\n`);
    if (text === 'form-waiting' || text === 'success') return text;
    if (['canceled', 'crashed', 'error'].includes(text)) return text;
    await sleep(interval);
    interval = Math.min(Math.round(interval * 1.1), 2000);
  }
  return 'timeout';
}

function parseJsonWait(r) {
  const ct = r.headers['content-type'] || '';
  if (!ct.includes('application/json')) return null;
  try {
    const j = JSON.parse(r.body.toString('utf8'));
    if (j.formWaitingUrl) {
      const m = j.formWaitingUrl.match(/\/form-waiting\/\d+/);
      return m ? m[0] : null;
    }
  } catch (e) {}
  return null;
}

async function main() {
  console.log('== MOP Generator E2E (HTTPS ' + HOST + ') ==');

  // Page 1: GET Intake
  console.log('\n[1a] GET /form/mop-generator');
  const g1 = await req('GET', '/form/mop-generator', null, {});
  console.log(`    status=${g1.status} bytes=${g1.body.length}`);
  if (g1.status !== 200) throw new Error('Intake GET failed');

  // Page 1: POST Intake → JSON {formWaitingUrl page 2}
  console.log('\n[1b] POST Intake');
  const p1 = await postForm('/form/mop-generator', {
    'field-0': 'E2E alarme LOS voie TH site TH2',
    'field-1': 'major',
    'field-2': 'DWDM Metro Nord',
  });
  console.log(`    status=${p1.status} ct=${p1.headers['content-type']}`);
  const wait1 = parseJsonWait(p1);
  if (!wait1) throw new Error('page 1 POST did not return formWaitingUrl; body=' + p1.body.toString('utf8').slice(0, 300));
  console.log(`    → ${wait1}`);

  // Poll → page 2 ready
  const s1 = await pollStatus(wait1, '1→2');
  if (s1 !== 'form-waiting') throw new Error(`page 2 not ready: status=${s1}`);

  // Page 2: GET + POST Context
  console.log('\n[2a] GET ' + wait1);
  const g2 = await req('GET', wait1, null, {});
  console.log(`    status=${g2.status} bytes=${g2.body.length}`);
  console.log('\n[2b] POST Context');
  const p2 = await postForm(wait1, {
    'field-0': 'OTU2, alarme AIS, carte ligne',
    'field-1': 'Alarme AIS sur port client 10GE, trafic down depuis 14:32.',
  });
  const wait2 = parseJsonWait(p2);
  if (!wait2) throw new Error('page 2 POST did not return formWaitingUrl');
  console.log(`    → ${wait2}`);

  const s2 = await pollStatus(wait2, '2→3');
  if (s2 !== 'form-waiting') throw new Error(`page 3 not ready: status=${s2}`);

  // Page 3: GET + POST Steps
  console.log('\n[3a] GET ' + wait2);
  const g3 = await req('GET', wait2, null, {});
  console.log(`    status=${g3.status} bytes=${g3.body.length}`);
  console.log('\n[3b] POST Steps (final submission)');
  const stepsText = [
    'Verifier alarmes NMS | Ouvrir NMS filtrer par equipement | SP-NMS-001',
    'Isoler la carte | Passer en out-of-service | SP-OTU-017',
    'Remplacer la carte | Remplacement hardware par spare | SP-HW-042',
  ].join('\n');
  const p3 = await postForm(wait2, { 'field-0': stepsText });
  console.log(`    status=${p3.status} ct=${p3.headers['content-type']}`);

  // After final POST: two possibilities
  //   (a) POST returned JSON {formWaitingUrl} → poll → GET binary
  //   (b) POST returned binary directly
  const ct3 = p3.headers['content-type'] || '';
  if (ct3.includes('application/pdf')) {
    fs.writeFileSync(OUT_PDF, p3.body);
    console.log(`\n✓ PDF saved: ${OUT_PDF} (${p3.body.length} bytes, magic=${p3.body.slice(0, 4).toString('hex')})`);
    if (p3.body.slice(0, 4).toString() !== '%PDF') throw new Error('not a valid PDF');
    process.exit(0);
  }
  const wait3 = parseJsonWait(p3);
  if (!wait3) {
    console.log('unexpected body:', p3.body.toString('utf8').slice(0, 500));
    throw new Error('final POST returned neither PDF nor formWaitingUrl');
  }
  console.log(`    → ${wait3}`);

  const s3 = await pollStatus(wait3, 'final', 180);
  console.log(`\n[final] poll terminal: ${s3}`);
  if (s3 !== 'success' && s3 !== 'form-waiting') throw new Error(`final poll: ${s3}`);

  console.log('\n[final] GET ' + wait3 + ' (fetch binary)');
  const gFinal = await req('GET', wait3, null, {});
  console.log(`    status=${gFinal.status} ct=${gFinal.headers['content-type']} bytes=${gFinal.body.length}`);
  if ((gFinal.headers['content-type'] || '').includes('application/pdf')) {
    fs.writeFileSync(OUT_PDF, gFinal.body);
    console.log(`\n✓ PDF saved: ${OUT_PDF} (${gFinal.body.length} bytes, magic=${gFinal.body.slice(0, 4).toString('hex')})`);
    if (gFinal.body.slice(0, 4).toString() !== '%PDF') throw new Error('not a valid PDF');
    process.exit(0);
  }
  console.log('body[0:500]:', gFinal.body.toString('utf8').slice(0, 500));
  throw new Error('final GET did not return a PDF');
}

main().catch((e) => { console.error('\nE2E FAIL:', e.message); process.exit(1); });
```

- [ ] **Step 5.2: Lint-check JavaScript (no linter installed, minimum `node --check`)**

Run: `node --check scripts/mop/e2e-mop-generator.js && echo OK`
Expected: `OK`.

- [ ] **Step 5.3: Commit the E2E harness**

Run:
```bash
git add scripts/mop/e2e-mop-generator.js
git commit -m "test(mop): add E2E harness for mop-generator-v1 multi-step form

Walks the 3 pages via HTTPS (Tailscale split DNS), polls execution
status between pages, handles both 'form-waiting' and 'success' as
terminal states on the final POST, fetches the binary PDF, verifies
%PDF magic bytes.

Fixes bug in prior /tmp/mop-e2e-v3.js which only treated 'success'
as terminal and missed the common case where the completion node's
form-waiting page IS the PDF binary response."
```

---

## Task 6: Execute E2E Happy Path

**Purpose:** Prove the technician-facing flow produces a valid PDF in the browser (modeled here by the test script).

- [ ] **Step 6.1: Run the E2E test**

Run: `node scripts/mop/e2e-mop-generator.js /tmp/mop-e2e-happy.pdf 2>&1 | tee /tmp/mop-e2e-happy.log`
Expected: Script exits 0. Last line: `✓ PDF saved: /tmp/mop-e2e-happy.pdf (<N> bytes, magic=25504446)` (magic `25504446` = `%PDF`).

- [ ] **Step 6.2: Verify PDF is valid and readable**

Run: `file /tmp/mop-e2e-happy.pdf && head -c 8 /tmp/mop-e2e-happy.pdf && echo && wc -c /tmp/mop-e2e-happy.pdf`
Expected: `PDF document, version 1.X or later`, first 8 bytes start with `%PDF-1.`, size > 1000 bytes.

- [ ] **Step 6.3: Verify execution in DB matches the test run**

Run:
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 bash <<'REMOTE'
PG=$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
docker exec -i -e PGPASSWORD="$PG" javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n -c \
  "SELECT id, status, \"startedAt\", \"stoppedAt\" FROM execution_entity WHERE \"workflowId\"='CP5gJrn1e2zZbPxh' ORDER BY id DESC LIMIT 3;"
REMOTE
```
Expected: Most recent row has `status=success`. No `crashed` / `error`.

- [ ] **Step 6.4: STOP criterion**

If Step 6.1 fails OR Step 6.2 shows garbage bytes OR Step 6.3 shows non-success:
1. Read `/tmp/mop-e2e-happy.log` and n8n container logs: `ssh ... 'docker logs javisi_n8n --tail 200'`
2. Query the failing execution's execution_data for the actual error node and message.
3. Apply systematic debugging (superpowers:systematic-debugging — Phase 1 first, no speculative fixes).
4. Do NOT proceed to Task 7 until happy path is green.

---

## Task 7: Execute E2E Error Branch

**Purpose:** Prove the `Done (Error)` branch actually renders on failure instead of silently crashing. Forces a failure via an unrenderable payload.

- [ ] **Step 7.1: Write a minimal error-injection test**

Create `scripts/mop/e2e-mop-generator-error.js` as a copy of the happy-path script with the following changes:
- Change title to `''` (empty) OR change the HTTP Request target in a feature-flag way — actually simpler: submit with `incident` field set to a value that the sibling webhook's `Prepare & Allocate` Code node will reject. If no such rejection exists, fall back to temporarily stopping `javisi_gotenberg` before the test (and restarting after).

The safest deterministic error is stopping Gotenberg. Use this approach:

```bash
# Step 7.1 (actual command): stop gotenberg → run happy test → expect error completion
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  'docker stop javisi_gotenberg'
node scripts/mop/e2e-mop-generator.js /tmp/mop-e2e-error.pdf 2>&1 | tee /tmp/mop-e2e-error.log || true
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  'docker start javisi_gotenberg && sleep 5 && docker ps | grep javisi_gotenberg'
```

Expected: Test script exits non-zero with `final GET did not return a PDF`, and `/tmp/mop-e2e-error.log` shows the final GET returned `text/html` containing `MOP generation failed` (because HTTP Request hit `continueErrorOutput` → Done (Error) `showText`).

- [ ] **Step 7.2: Verify the execution reached `Done (Error)` not `Done (PDF)`**

Run:
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 bash <<'REMOTE'
PG=$(docker exec javisi_n8n printenv DB_POSTGRESDB_PASSWORD)
EXEC_ID=$(docker exec -i -e PGPASSWORD="$PG" javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n -tAc \
  "SELECT id FROM execution_entity WHERE \"workflowId\"='CP5gJrn1e2zZbPxh' ORDER BY id DESC LIMIT 1;")
echo "latest exec: $EXEC_ID"
docker exec -i -e PGPASSWORD="$PG" javisi_postgresql psql -h 127.0.0.1 -U n8n -d n8n -tAc \
  "SELECT data FROM execution_data WHERE \"executionId\"=$EXEC_ID;" > /tmp/last-exec.json
python3 -c "
import json
d = json.load(open('/tmp/last-exec.json'))
root = d[0]
def deref(x, depth=0):
    if depth > 30: return '<deep>'
    if isinstance(x, str) and x.isdigit():
        i = int(x)
        if i < len(d): return deref(d[i], depth+1)
        return x
    if isinstance(x, dict): return {k: deref(v, depth+1) for k, v in x.items()}
    if isinstance(x, list): return [deref(v, depth+1) for v in x]
    return x
rd = deref(root.get('resultData'))
print('lastNodeExecuted:', rd.get('lastNodeExecuted'))
print('runData nodes:', list((rd.get('runData') or {}).keys()))
"
REMOTE
```
Expected: `lastNodeExecuted: Done (Error)` and `runData nodes` includes `Done (Error)` (not `Done (PDF)`).

- [ ] **Step 7.3: Re-run happy path to confirm recovery**

Run: `node scripts/mop/e2e-mop-generator.js /tmp/mop-e2e-recover.pdf 2>&1 | tail -5`
Expected: `✓ PDF saved: /tmp/mop-e2e-recover.pdf (<N> bytes, magic=25504446)`.

---

## Task 8: Document Findings & Close Out

**Purpose:** Update REX + research notes so the next person (or future Claude) doesn't re-learn the same traps.

**Files:**
- Modify: `docs/REX-SESSION-2026-04-11.md` (append)
- Modify: `.planning/research/mop-gotenberg-n8n.md` (append) — create if missing.

- [ ] **Step 8.1: Append clean-import protocol REX**

Append to `docs/REX-SESSION-2026-04-11.md`:

```markdown
## Clean-import protocol (resolved 2026-04-11)

**Problem recap:** Exec 11740 of `CP5gJrn1e2zZbPxh` showed a phantom
stale workflow definition in nodeExecutionStack[0] referencing a
non-existent "Render & Load" node (id=...005, tv=1, pos=[1140,240]),
despite workflow_entity containing the correct 8 nodes. Root cause:
UI editing drifted the runtime cache from the DB definition.

**Resolution:** File-first deployment via
`scripts/mop/deploy-mop-generator.sh`. Protocol:

1. Deactivate + DELETE execution_data / execution_entity for workflow id
2. `docker restart javisi_n8n` (wave 1 — flush runtime cache pre-import)
3. Wait for /healthz
4. `n8n import:workflow --input=<canonical.json>` (upsert by id)
5. `n8n update:workflow --id=<id> --active=true`
6. `docker restart javisi_n8n` (wave 2 — CLI warns "restart required")
7. Wait for /healthz
8. Verify workflow_entity.active=t + webhook_entity rows present

**Rule:** Never edit this workflow in the UI. The canonical source is
`scripts/n8n-workflows/mop-generator-v1.json`. Any change → edit the
file → re-run `scripts/mop/deploy-mop-generator.sh`.

**E2E validation:** `scripts/mop/e2e-mop-generator.js` walks the 3
pages, polls status, fetches the binary PDF, verifies %PDF magic
bytes. Happy + error branch both validated against the deployed
workflow.
```

- [ ] **Step 8.2: Append/create protocol notes in research**

Create `.planning/research/mop-gotenberg-n8n.md` if missing (or append if it exists) with:

```markdown
## n8n Form v2.5 multi-step — wire protocol (captured 2026-04-11)

- POST `/form/<webhookPath>` MUST be `multipart/form-data`; JSON/urlencoded
  trigger AssertionError inside formTrigger.
- HTML input names are `field-0`, `field-1`... (zero-indexed). Server maps
  them back to `fieldLabel` so downstream you read `$('NodeName').item.json.labelName`.
- Successful POST returns `200` + JSON `{formWaitingUrl: "...form-waiting/<execId>"}`.
- Between pages: GET `<formWaitingUrl>/n8n-execution-status` — terminal values
  `form-waiting` (next page ready) or `success` (execution done). `null` = still running.
- `responseMode=onReceived` (default since v2.2) means POST responds
  before the next node is ready → polling is REQUIRED; do not expect POST
  to block until the next page is computed.
- A multi-step form is a SINGLE execution that pauses between pages via
  `waitTill=3000-01-01`. Cross-page `$('Intake').item.json.title` works.
- Completion node with `respondWith=returnBinary, inputDataFieldName=data`
  reads `binary.data` from its input item. Upstream `readWriteFile (read)`
  must set `options.dataPropertyName='data'` — field names MUST match exactly.
- HEAD requests on form webhook URLs return 404 — expected; use GET.
- Traffic path: `mayi.ewutelo.cloud` → split DNS → Tailscale `100.64.0.14`
  → Caddy → `javisi_n8n:5678`. Never public IP (137.74.114.167).

## Phantom cache trap

UI editing a multi-step form workflow can leave the runtime cache out of
sync with `workflow_entity.nodes`, so executions reference ghost nodes
that no longer exist in the DB. Always use file-first import
(`n8n import:workflow`) + double-restart around activate. See
`scripts/mop/deploy-mop-generator.sh`.
```

- [ ] **Step 8.3: Commit the docs**

Run:
```bash
git add docs/REX-SESSION-2026-04-11.md .planning/research/mop-gotenberg-n8n.md
git commit -m "docs(mop): capture clean-import protocol + n8n form v2.5 wire protocol

- REX session 2026-04-11: resolution of the phantom stale workflow
  cache (exec 11740 'Render & Load') via file-first deploy helper.
- Research notes: exact HTTP sequence for multi-step form, terminal
  status values, completion-node binary field wiring trap."
```

- [ ] **Step 8.4: Update parent plan to point at this focused plan**

Edit `docs/superpowers/plans/2026-04-11-mop-machinery-implementation.md` Task 3.4 section: replace the vague node list with a one-line pointer:

```markdown
### Task 3.4: Build `mop-generator-v1` multi-step form workflow

**Superseded by:** `docs/superpowers/plans/2026-04-11-mop-workflow-n8n-multistep.md`
— focused plan with canonical JSON, clean-import protocol, E2E harness.
```

Run:
```bash
git add docs/superpowers/plans/2026-04-11-mop-machinery-implementation.md
git commit -m "docs(mop): point parent plan Task 3.4 at focused workflow plan"
```

---

## Done-When Criteria

- [ ] `scripts/n8n-workflows/mop-generator-v1.json` committed, structurally validated (8 nodes, no phantom).
- [ ] `scripts/mop/deploy-mop-generator.sh` committed, shellcheck-clean, runs end-to-end against Sese-AI.
- [ ] `scripts/mop/e2e-mop-generator.js` committed, `node --check` clean.
- [ ] Workflow `CP5gJrn1e2zZbPxh` active in `workflow_entity`, two rows in `webhook_entity` for `mop-generator`.
- [ ] Happy-path E2E saves a valid PDF (`%PDF` magic, > 1000 bytes) to `/tmp/mop-e2e-happy.pdf`.
- [ ] Latest execution in `execution_entity` has `status=success`, `lastNodeExecuted=Done (PDF)`.
- [ ] Error-branch E2E (Gotenberg stopped) reaches `Done (Error)` — verified in `execution_data`.
- [ ] REX + research docs updated and committed.
- [ ] Parent plan Task 3.4 replaced with a pointer to this plan.
- [ ] No further reference to the ghost "Render & Load" node anywhere.

## Known Traps (from live debugging 2026-04-11)

| Trap | Mitigation |
|---|---|
| UI editing drifts runtime cache from DB → phantom nodes in executionStack | File-first import only; deploy helper is the single entry point |
| `n8n update:workflow` warns "restart required" but is easy to miss | Double-restart in the helper (wave 1 pre-import, wave 2 post-activate) |
| Form trigger rejects JSON body with AssertionError | E2E harness sends `multipart/form-data` exclusively |
| `form-waiting` terminal state missed on final POST → binary never fetched | E2E harness treats both `form-waiting` and `success` as terminal |
| HEAD on `/form/...` returns 404 → looks like workflow not active | Use GET for health check; HEAD is not supported on n8n webhooks |
| `mayi.ewutelo.cloud` via public IP skips Caddy VPN ACL → 403 | Always rely on split DNS → Tailscale 100.64.0.14 |
| Read PDF `dataPropertyName` mismatched with Done (PDF) `inputDataFieldName` | Both hardcoded to `"data"` in the canonical JSON; validated in Task 2.3 |
| `HTTP Request` targeting `https://mayi...` would loop through Caddy | URL is `http://localhost:5678/webhook/mop-render` — inside container network |
| Gotenberg must be running for happy path; stop it intentionally to test error branch | Task 7 stops/restarts Gotenberg as part of the error-branch assertion |

## Rollback Plan

If deployment breaks the running system:

1. `docker exec javisi_n8n n8n update:workflow --id=CP5gJrn1e2zZbPxh --active=false`
2. `docker restart javisi_n8n`
3. Investigate with systematic-debugging Phase 1 before attempting re-deploy.

The sibling `mop-webhook-render-v1` is independent — it has its own webhook path and its own workflow id. Failures in `mop-generator-v1` do not affect it.
