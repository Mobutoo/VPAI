# LOI Système de Briques — P2 (MESURE) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the open MEASURE loop — detect the founding-incident signature (806 Bash / 0 MCP) by aggregating per-session metrics into a persistent local ledger and alerting when a session matches `mcp_calls == 0 && bash_calls > floor`.

**Architecture:** A NEW Stop hook `metrics-aggregator.sh` recomputes per-session metrics directly from the current session JSONL (the same greps `session-memory-writer.sh` already uses, PLUS an `mcp` count it lacks), appends one JSON line to `~/.claude/metrics/sessions.jsonl`, and on a threshold breach emits an alert (stderr line + Telegram if configured). It recomputes independently rather than consuming `session-memory-writer.sh`'s fire-and-forget output — decoupled, so neither hook depends on the other's execution or ordering. Fail-open: exit 0 always; a Stop hook never blocks anyway.

**Tech Stack:** Bash (`set -uo pipefail`), grep over the session `.jsonl`, JSONL append. Test harness = existing `hooks/test/harness.js` `runShell` + a fixture JSONL; env seams `R0_SESSION_JSONL` / `R0_METRICS_DIR` / `R0_806_BASH_FLOOR` for isolation.

**Spec:** `docs/superpowers/specs/2026-06-04-loi-system-bricks-design.md` §7 D2 + §8 (metrics-aggregator, P2). Extends P1 (`docs/superpowers/plans/2026-06-04-loi-system-bricks-p1.md`).

---

## Cross-Repo Commit Map
All code in `~/.claude` (branch `main`), 1 hook = 1 commit. This plan doc in VPAI.

## Current substrate (verified 2026-06-04)
- `~/.claude/hooks/session-memory-writer.sh` (Stop hook) computes `TOOL_COUNT/ERROR_COUNT/COMPACT_COUNT/BASH_COUNT/BASH_PCT` from `$(ls -t ~/.claude/projects/*/*.jsonl | head -1)` and fire-and-forgets to Telegram + n8n `webhook/session-complete`. It does NOT compute an MCP count and persists nothing locally.
- `settings.json` `Stop` array currently has 2 entries: `stop-gate.sh`, `session-memory-writer.sh`.
- No `~/.claude/metrics/` directory yet.
- MCP tool_use entries in the JSONL carry `"name":"mcp__<server>__<tool>"`.

## File Structure
| Path | Responsibility |
|---|---|
| `~/.claude/hooks/metrics-aggregator.sh` | NEW. Recompute metrics (incl. `mcp`), append to `metrics/sessions.jsonl`, alert on 806/0 signature. Fail-open. |
| `~/.claude/hooks/test/test-metrics-aggregator.js` | NEW. Fixture-JSONL-driven test via `runShell` + env seams. |
| `~/.claude/settings.json` | Modify. Add the hook to the `Stop` array. |

## Conventions
- Fail-open: `set -uo pipefail` + `|| true` guards; exit 0 on every path.
- Test isolation: NEVER touch the real `~/.claude/metrics/` or real session JSONL — the test sets `R0_METRICS_DIR=/tmp/claude-metrics.test.<pid>`, `R0_SESSION_JSONL=<fixture>`, `R0_806_BASH_FLOOR` as needed, and cleans up.
- `BASH_FLOOR` default = **50** (the spec's `bash_calls > 50`), overridable via `R0_806_BASH_FLOOR`.

---

### Task 1: `metrics-aggregator.sh` + test

**Files:**
- Create: `~/.claude/hooks/metrics-aggregator.sh`
- Create: `~/.claude/hooks/test/test-metrics-aggregator.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-metrics-aggregator.js
'use strict';
const { runShell, ok, done } = require('./harness');
const fs = require('fs');

const MDIR = '/tmp/claude-metrics.test.' + process.pid;
const FIX = '/tmp/claude-sess-fixture.' + process.pid + '.jsonl';
function clean() { try { fs.rmSync(MDIR, { recursive: true, force: true }); } catch (_) {} try { fs.unlinkSync(FIX); } catch (_) {} }
function lastLine() {
  const raw = fs.readFileSync(MDIR + '/sessions.jsonl', 'utf8').trim().split('\n');
  return JSON.parse(raw[raw.length - 1]);
}
clean();

// Build a fixture JSONL simulating the 806/0 signature: many Bash tool_use, zero MCP.
function toolUse(name) { return JSON.stringify({ type: 'tool_use', name }); }
let lines = [];
for (let i = 0; i < 60; i++) lines.push(toolUse('Bash'));
lines.push(toolUse('Write'));
fs.writeFileSync(FIX, lines.join('\n') + '\n');

const env = { R0_METRICS_DIR: MDIR, R0_SESSION_JSONL: FIX, R0_806_BASH_FLOOR: '50' };

let r = runShell('metrics-aggregator.sh', {}, env);
ok(r.code === 0, 'hook exits 0 (fail-open / non-blocking)');
ok(fs.existsSync(MDIR + '/sessions.jsonl'), 'appends to sessions.jsonl');
let m = lastLine();
ok(m.bash === 60 && m.mcp === 0, 'counts bash=60, mcp=0 from fixture');
ok(m.tools === 61, 'tools = total tool_use count');
ok(m.alert === true, '806/0 signature (mcp=0 && bash>50) → alert true');
ok(/\[METRICS-806\]/.test(r.stdout), 'emits [METRICS-806] alert line on stdout');

// Healthy session: MCP present → no alert
clean();
lines = [];
for (let i = 0; i < 60; i++) lines.push(toolUse('Bash'));
lines.push(toolUse('mcp__qdrant__qdrant-find'));
fs.writeFileSync(FIX, lines.join('\n') + '\n');
r = runShell('metrics-aggregator.sh', {}, env);
m = lastLine();
ok(m.mcp === 1 && m.alert === false, 'session with ≥1 MCP call → no alert');
ok(!/\[METRICS-806\]/.test(r.stdout), 'no alert line when healthy');

// Low bash count, 0 mcp → no alert (below floor)
clean();
fs.writeFileSync(FIX, [toolUse('Bash'), toolUse('Bash')].join('\n') + '\n');
r = runShell('metrics-aggregator.sh', {}, env);
m = lastLine();
ok(m.alert === false, 'bash below floor → no alert even with 0 mcp');

// Missing JSONL → fail-open, no crash, no append
clean();
r = runShell('metrics-aggregator.sh', {}, { R0_METRICS_DIR: MDIR, R0_SESSION_JSONL: '/nonexistent.jsonl', R0_806_BASH_FLOOR: '50' });
ok(r.code === 0, 'missing JSONL → exit 0 (fail-open)');

clean();
done();
```

- [ ] **Step 2: Run — expect FAIL** (`Cannot find ... metrics-aggregator.sh` / runShell exit non-zero)

```bash
node ~/.claude/hooks/test/test-metrics-aggregator.js
```

- [ ] **Step 3: Implement `metrics-aggregator.sh`**

```bash
#!/bin/bash
# metrics-aggregator.sh — Stop hook. Ferme la boucle MESURE (SPEC §7 D2).
# Recompute per-session metrics from the session JSONL (incl. mcp_count, que
# session-memory-writer.sh n'a pas), append 1 ligne à ~/.claude/metrics/sessions.jsonl,
# et ALERTE sur la signature de l'incident fondateur : mcp_calls==0 && bash_calls > FLOOR
# (806 Bash / 0 MCP, cf docs/audits/2026-04-11-mop-generator-execution-audit.md).
# Recompute INDÉPENDANT (pas de dépendance d'ordre avec session-memory-writer).
# Fail-open : exit 0 toujours ; un Stop hook ne bloque pas de toute façon.
set -uo pipefail

METRICS_DIR="${R0_METRICS_DIR:-$HOME/.claude/metrics}"
BASH_FLOOR="${R0_806_BASH_FLOOR:-50}"

SESSION_JSONL="${R0_SESSION_JSONL:-$(ls -t "$HOME/.claude/projects/"*"/"*.jsonl 2>/dev/null | head -1)}"
[ -f "$SESSION_JSONL" ] || exit 0

PROJECT=$(basename "$(dirname "$SESSION_JSONL")" | sed 's/^-home-mobuone-//')
TOOL_COUNT=$(grep -c '"type":"tool_use"' "$SESSION_JSONL" 2>/dev/null) || TOOL_COUNT=0
ERROR_COUNT=$(grep -c '"is_error":true' "$SESSION_JSONL" 2>/dev/null) || ERROR_COUNT=0
COMPACT_COUNT=$(grep -c '"compact_boundary"' "$SESSION_JSONL" 2>/dev/null) || COMPACT_COUNT=0
BASH_COUNT=$(grep -c '"name":"Bash"' "$SESSION_JSONL" 2>/dev/null) || BASH_COUNT=0
MCP_COUNT=$(grep -c '"name":"mcp__' "$SESSION_JSONL" 2>/dev/null) || MCP_COUNT=0

BASH_PCT=$(( TOOL_COUNT > 0 ? BASH_COUNT * 100 / TOOL_COUNT : 0 ))

ALERT=false
if [ "$MCP_COUNT" -eq 0 ] && [ "$BASH_COUNT" -gt "$BASH_FLOOR" ]; then
  ALERT=true
fi

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
mkdir -p "$METRICS_DIR" 2>/dev/null || true
printf '{"ts":"%s","project":"%s","tools":%d,"errors":%d,"compacts":%d,"bash":%d,"bash_pct":%d,"mcp":%d,"alert":%s}\n' \
  "$TS" "$PROJECT" "$TOOL_COUNT" "$ERROR_COUNT" "$COMPACT_COUNT" "$BASH_COUNT" "$BASH_PCT" "$MCP_COUNT" "$ALERT" \
  >> "$METRICS_DIR/sessions.jsonl" 2>/dev/null || true

if [ "$ALERT" = "true" ]; then
  echo "[METRICS-806] ⚠️ Signature incident fondateur : ${BASH_COUNT} Bash / 0 MCP cette session (projet ${PROJECT}). Violation LOI MCP-first (R0/R1). cf docs/audits/2026-04-11-mop-generator-execution-audit.md"
  TELEGRAM_BOT="${TELEGRAM_BOT_TOKEN:-}"; TELEGRAM_CHAT="${TELEGRAM_CHAT_ID:-}"
  if [ -n "$TELEGRAM_BOT" ] && [ -n "$TELEGRAM_CHAT" ]; then
    curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage" \
      -H "Content-Type: application/json" \
      -d "{\"chat_id\":\"${TELEGRAM_CHAT}\",\"text\":\"⚠️ [806/0] ${PROJECT} : ${BASH_COUNT} Bash / 0 MCP — violation MCP-first cette session\"}" \
      >/dev/null 2>&1 &
  fi
fi
exit 0
```

- [ ] **Step 4: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-metrics-aggregator.js
chmod +x ~/.claude/hooks/metrics-aggregator.sh
bash -n ~/.claude/hooks/metrics-aggregator.sh && echo "syntax OK"
```
Expected: all `✓`, exit 0; `syntax OK`.

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/metrics-aggregator.sh hooks/test/test-metrics-aggregator.js
git commit -m "feat(hooks): metrics-aggregator — persist session metrics + alert on 806/0 signature (P2 MESURE)"
```
NEVER `git add -A`. Stage ONLY those two files.

---

### Task 2: Wire in settings.json + regression

**Files:**
- Modify: `~/.claude/settings.json` (`Stop` array)

- [ ] **Step 1: Backup + validate current JSON**

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8"));console.log("valid")'
```

- [ ] **Step 2: Add the aggregator to the `Stop` array** (a new array element, matching the existing Stop entry shape — they use no `matcher`, just `{hooks:[{type:"command", command}]}`):

```json
{
  "hooks": [
    { "type": "command", "command": "bash /home/mobuone/.claude/hooks/metrics-aggregator.sh" }
  ]
}
```

- [ ] **Step 3: Validate edited JSON**

```bash
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8"));console.log("valid")'
```
If it throws, restore from `.bak` and redo.

- [ ] **Step 4: Full regression + smoke**

```bash
bash ~/.claude/hooks/test/run-all.sh
# Smoke against the REAL current session JSONL (read-only append to the real metrics ledger is fine):
bash ~/.claude/hooks/metrics-aggregator.sh && tail -1 ~/.claude/metrics/sessions.jsonl
```
Expected: `ALL TESTS PASS`; the smoke appends one line reflecting THIS session (which has many MCP calls → `alert:false`).

- [ ] **Step 5: Commit + remove backup**

```bash
cd /home/mobuone/.claude
rm -f settings.json.bak
git add settings.json
git commit -m "feat(hooks): wire metrics-aggregator into Stop (P2 MESURE live)"
```

---

## P2 Done-Definition
- [ ] `node hooks/test/test-metrics-aggregator.js` green (806/0 fixture → alert; healthy → no alert; below-floor → no alert; missing JSONL → fail-open).
- [ ] `bash hooks/test/run-all.sh` → ALL TESTS PASS (P1 suites still green).
- [ ] Aggregator wired in `Stop`; smoke run appends a line for the live session with `alert:false`.
- [ ] `~/.claude/metrics/sessions.jsonl` accumulates one line per session ending.

## Out of scope
- Dashboards / trend analysis over `sessions.jsonl` (the ledger is the substrate; visualization is later).
- Hardening the alert into a block (MEASURE is observe-only by design — D1 already blocks the cause).
- P3 (VERIFY stop-gate), P4 (risk-tier + OUTPUT guard).
