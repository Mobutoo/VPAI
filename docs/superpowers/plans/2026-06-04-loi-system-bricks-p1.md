# LOI Système de Briques — P1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship P1 of the LOI-as-bricks refactor — event-driven topic re-arming (no clock), cross-project memory portability via `sources.yml`, LOI CORE/BINDING split, and the R1 hard-gate that closes the founding 806-Bash/0-MCP lesson.

**Architecture:** Two repos. **Code** (hooks, CORE.md, Mobutoo skill, `settings.json`) lives in `~/.claude` (`/home/mobuone/.claude`, branch `main`). **Binding + this plan doc** live in VPAI (`/home/mobuone/VPAI`, `.loi-binding.yml` + `docs/superpowers/plans/`). Every hook is **fail-open** (exit 0 on any error, never throw uncaught). The decay refactor is purely additive to the *injector* path; the founding R0/R2/R7 *gate* path (`isConsulted` + filesystem markers) must stay byte-identical — a characterization test locks this first.

**Tech Stack:** Node.js (CommonJS, no deps) for `.js` hooks; Bash for `.sh` hooks; YAML config (`sources.yml`, `.loi-binding.yml`) parsed in Node without a YAML lib (line-oriented parser, the file is flat); test harness = `spawnSync` + `assert` (zero framework).

**Spec:** `docs/superpowers/specs/2026-06-04-loi-system-bricks-design.md` (extends `docs/runbooks/SPEC-R0-CONTINU.md`).

---

## Cross-Repo Commit Map

| Artifact | Repo | Commit target |
|---|---|---|
| All `~/.claude/hooks/**`, `~/.claude/loi/CORE.md`, `~/.claude/skills/Mobutoo/SKILL.md`, `~/.claude/settings.json` | `~/.claude` | branch `main` |
| `/home/mobuone/VPAI/.loi-binding.yml` | VPAI | branch `main` (via `git@github-seko`) |
| This plan doc | VPAI | branch `main` |

> **Executor note:** `cd /home/mobuone/.claude && git add … && git commit` for hook commits; `cd /home/mobuone/VPAI && git add … && git commit` for binding. Do NOT cross paths in one commit. The spec mandates **1 hook = 1 commit** (§10).

---

## File Structure

**New files (`~/.claude/hooks/`):**
| Path | Responsibility |
|---|---|
| `lib/sources.js` | Parse `sources.yml` → `all() / detect(cwd) / docRoots()`. Fail-open to `[{name:basename, root:cwd, kinds:[]}]`. |
| `r0-rex-watcher.js` | PostToolUse `Write\|Edit`. On REX/runbook/audit/TROUBLESHOOTING write → extract topic(s) → `invalidate(topic)` (re-arm). Trigger **B**. |
| `n8n-validate-marker.js` | PostToolUse on `validate_workflow` MCP tools → write `/tmp/claude-validate-done` marker. Prerequisite for D1. |
| `test/harness.js` | `runHook(hookPath, inputObj, env)` + `runShell(...)` + re-exported `assert`. |
| `test/test-*.js` | One test file per hook (spec §9). |
| `test/run-all.sh` | Run every `test-*.js`, fail loud. |

**New files (other):**
| Path | Repo | Responsibility |
|---|---|---|
| `~/.claude/loi/CORE.md` | `~/.claude` | R0–R8 as parameterized principles `{MEMORY_CMD, VALIDATOR, SECURE_CHANNEL, DEPLOY_METHOD, BROWSER_DRIVER}`. |
| `/home/mobuone/VPAI/.loi-binding.yml` | VPAI | Fills CORE params + VPAI-hard rules (R9/R10/R11, concrete commands). |

**Modified files (`~/.claude/`):**
| Path | Change |
|---|---|
| `hooks/lib/ledger.js` | v2: `action_count`, `last_action`; new `bumpAction() / lastAction(topic)`; `isFresh` → decay (`< DECAY_N`); `stampTopic` sets `last_action`; v1→v2 read-as-is migration; `R0_LEDGER_PATH` env seam. **Preserve** `isConsulted / invalidateAll`. |
| `hooks/r0-topic-injector.js` | Call `ledger.bumpAction()` once per invocation; `isFresh` now decay-aware (trigger **A**). |
| `hooks/error-escalator.js` | `R0_DEBUG_THRESHOLD` default 2→**1**; `ERROR_ESCALATOR_THRESHOLD` (STOP-archi) default 5→**3** (trigger **C**). |
| `hooks/memory-search-start.sh` | Replace `case $PROJECT` with `sources.detect`; portable seed-topics from N=5 newest REX of detected project; multi-repo hot grep + official-docs tier (N1+N2). |
| `hooks/loi-op-enforcer.js` | R1 advisory → **hard gate** (`exit(2)`+stderr) on `import:workflow` / `docker cp *.json javisi_n8n` when no fresh validate marker (D1). |
| `skills/Mobutoo/SKILL.md` | CORE+BINDING engine; Step 4 `rm -f` → ledger-aware re-arm; LOI path via `sources.detect`. |
| `settings.json` | +1 PostToolUse `Write\|Edit` (r0-rex-watcher); +1 PostToolUse `mcp__n8n-docs__validate_workflow\|mcp__n8n-docs__n8n_validate_workflow` (n8n-validate-marker). |

---

## Conventions for all tasks

- **Fail-open invariant:** every hook wraps its body in `try{}catch(_){process.exit(0)}` (JS) or `set -uo pipefail` + `|| true` guards (sh). A test asserting "garbage stdin → exit 0, no stderr block" is part of every hook's test file.
- **Test isolation:** JS ledger tests set `R0_LEDGER_PATH=/tmp/claude-r0-ledger.test.<pid>.json` and `rm` it in teardown. Marker-touching tests MUST call `cleanMarkers()` (harness) in setup/teardown — it glob-removes `/tmp/claude-r0-done*` (global AND per-topic, since the enforcer accepts `/tmp/claude-r0-done-<topic>`) + `/tmp/claude-validate-done`. Never `rm` only the global marker — that leaves per-topic markers that cause spurious gate passes.
- **Run tests via** `node ~/.claude/hooks/test/test-X.js` (exit 0 = pass, non-zero = fail). @superpowers:test-driven-development — write the failing test first, watch it fail, then implement.
- **DECAY_N** default = **20**, overridable via env `R0_DECAY_N`.

---

### Task 1: Test harness + characterization lock of founding gates

Locks current R0/R2/R7 enforcer verdicts BEFORE any ledger edit, so the decay refactor provably doesn't move the founding gate.

**Files:**
- Create: `~/.claude/hooks/test/harness.js`
- Create: `~/.claude/hooks/test/run-all.sh`
- Create: `~/.claude/hooks/test/test-enforcer-gates.js`

- [ ] **Step 1: Write the harness**

```javascript
// ~/.claude/hooks/test/harness.js
'use strict';
const { spawnSync } = require('child_process');
const assert = require('assert');

const HOOKS = __dirname + '/..';

// Run a node hook with JSON stdin. Returns {stdout, stderr, code}. Never throws on non-zero exit.
function runHook(name, inputObj, extraEnv) {
  const r = spawnSync('node', [HOOKS + '/' + name], {
    input: JSON.stringify(inputObj || {}),
    encoding: 'utf8',
    env: Object.assign({}, process.env, extraEnv || {}),
    timeout: 8000,
  });
  return { stdout: r.stdout || '', stderr: r.stderr || '', code: r.status };
}

// Run a bash hook with JSON stdin.
function runShell(name, inputObj, extraEnv) {
  const r = spawnSync('bash', [HOOKS + '/' + name], {
    input: JSON.stringify(inputObj || {}),
    encoding: 'utf8',
    env: Object.assign({}, process.env, extraEnv || {}),
    timeout: 15000,
  });
  return { stdout: r.stdout || '', stderr: r.stderr || '', code: r.status };
}

// Remove every /tmp/claude-r0-done* marker (global + per-topic) — avoids the
// per-topic-marker flakiness class. Mirrors memory-search-start.sh's `rm -f …done*`.
function cleanMarkers() {
  const fs = require('fs');
  try {
    for (const f of fs.readdirSync('/tmp')) {
      if (f.indexOf('claude-r0-done') === 0 || f === 'claude-validate-done') {
        try { fs.unlinkSync('/tmp/' + f); } catch (_) {}
      }
    }
  } catch (_) {}
}

let _n = 0;
function ok(cond, msg) {
  _n++;
  if (!cond) { console.error('  ✗ ' + msg); process.exitCode = 1; }
  else console.error('  ✓ ' + msg);
}
function done() { console.error(`(${_n} assertions)`); }

module.exports = { runHook, runShell, ok, done, assert, HOOKS, cleanMarkers };
```

- [ ] **Step 2: Write the run-all script**

```bash
#!/bin/bash
# ~/.claude/hooks/test/run-all.sh — run every test-*.js, fail loud.
set -uo pipefail
cd "$(dirname "$0")"
fail=0
for t in test-*.js; do
  echo "=== $t ==="
  node "$t" || fail=1
done
[ "$fail" -eq 0 ] && echo "ALL TESTS PASS" || { echo "SOME TESTS FAILED"; exit 1; }
```

- [ ] **Step 3: Write the characterization test (will PASS against current code — it captures behavior, not absence)**

```javascript
// ~/.claude/hooks/test/test-enforcer-gates.js
'use strict';
const { runHook, ok, done, cleanMarkers } = require('./harness');
const fs = require('fs');

// Isolate: empty ledger + NO marker (global OR per-topic) so the R0 gate fires
// deterministically. The enforcer also accepts /tmp/claude-r0-done-<topic>
// (line 80), so cleanMarkers() must glob-remove all of them, not just the global.
const LP = '/tmp/claude-r0-ledger.test.' + process.pid + '.json';
const env = { R0_LEDGER_PATH: LP };
function clean() { try { fs.unlinkSync(LP); } catch (_) {} cleanMarkers(); }
clean();

// R2 — curl to form → BLOCK exit 2
let r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'curl https://mayi.ewutelo.cloud/form/abc' } }, env);
ok(r.code === 2 && /\[R2-GATE\]/.test(r.stderr), 'R2 curl-to-form blocks with exit 2');

// R7 — public IP → BLOCK
r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'ssh mobuone@137.74.114.167' } }, env);
ok(r.code === 2 && /\[R7-GATE\]/.test(r.stderr), 'R7 public IP blocks with exit 2');

// R7 — localhost:5678 → BLOCK
r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'curl localhost:5678/healthz' } }, env);
ok(r.code === 2 && /\[R7-GATE\]/.test(r.stderr), 'R7 localhost:5678 blocks with exit 2');

// R0 gate — Write on n8n topic, no marker → BLOCK
clean();
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', tool_input: { file_path: '/x/scripts/n8n-workflows/foo.json', content: 'n8n workflow' } }, env);
ok(r.code === 2 && /\[R0-GATE\]/.test(r.stderr), 'R0 gate blocks Write on n8n topic without memory search');

// Pure-read Bash → NO block
r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'git status' } }, env);
ok(r.code !== 2, 'pure-read git status is not blocked');

// Garbage stdin → fail-open exit 0
r = runHook('loi-op-enforcer.js', 'not json at all', env);
ok(r.code === 0 || r.code === null ? true : r.code !== 2, 'garbage stdin does not block (fail-open)');

clean();
done();
```

> Note: `runHook` JSON-stringifies its input, so the "garbage" case actually sends `"not json at all"` as a JSON string — the hook's `JSON.parse` yields a string, `.tool_input` is undefined, body no-ops to exit 0. That's the fail-open path we want to lock.

- [ ] **Step 4: Run it — expect PASS (current code already implements these gates)**

```bash
chmod +x ~/.claude/hooks/test/run-all.sh
node ~/.claude/hooks/test/test-enforcer-gates.js
```
Expected: all `✓`, exit 0. If any `✗` on R2/R7, STOP — the Explore map of current behavior is wrong; reconcile before continuing.

- [ ] **Step 4b: Apply the `R0_LEDGER_PATH` env seam to ledger.js NOW** (pulled forward from Task 3 Edit 1 — the R0-gate characterization needs ledger isolation, else the enforcer reads the LIVE session ledger where `n8n` is already consulted and the gate won't fire). Behavior-neutral when the env var is unset.

```javascript
// ~/.claude/hooks/lib/ledger.js line 13 — was: const PATH = '/tmp/claude-r0-ledger.json';
const PATH = process.env.R0_LEDGER_PATH || '/tmp/claude-r0-ledger.json';
```
Re-run `node ~/.claude/hooks/test/test-enforcer-gates.js` → now ALL `✓` (R0 gate fires against the isolated empty ledger). **Task 3 Edit 1 is now already applied — skip it there.**

- [ ] **Step 5: Commit (`~/.claude`) — two atomic commits**

```bash
cd /home/mobuone/.claude
git add hooks/lib/ledger.js
git commit -m "feat(hooks): R0_LEDGER_PATH env seam for test isolation (behavior-neutral)"
git add hooks/test/harness.js hooks/test/run-all.sh hooks/test/test-enforcer-gates.js
git commit -m "test(hooks): harness + characterization lock of R0/R2/R7 gates"
```

---

### Task 2: `lib/sources.js` — sources.yml parser (portability foundation)

**Files:**
- Create: `~/.claude/hooks/lib/sources.js`
- Create: `~/.claude/hooks/test/test-sources.js`
- Reference: `/opt/workstation/configs/ai-memory-worker/sources.yml` (5 sources; 2 are `kind:official-docs` = `typebot-docs`, `DOCS`; some sources have NO `kind:` tag — parser must tolerate).

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-sources.js
'use strict';
const { ok, done } = require('./harness');
const S = require('../lib/sources.js');

const all = S.all();
ok(Array.isArray(all) && all.length >= 5, 'all() returns >=5 sources');
ok(all.some(s => s.name === 'VPAI' && s.root === '/home/mobuone/VPAI'), 'VPAI source parsed with root');
ok(all.some(s => s.name === 'flash-studio'), 'flash-studio source parsed');

const det = S.detect('/home/mobuone/VPAI/roles/caddy');
ok(det && det.name === 'VPAI', 'detect() matches VPAI by longest-prefix root');

const unknown = S.detect('/home/mobuone/macgyver/x');
ok(unknown && unknown.root === '/home/mobuone/macgyver/x' && Array.isArray(unknown.kinds), 'detect() unknown cwd → fail-open basename source');

const docs = S.docRoots();
ok(docs.length === 2 && docs.every(d => d.kinds.includes('official-docs')), 'docRoots() = the 2 official-docs sources');
ok(docs.some(d => d.name === 'DOCS') && docs.some(d => d.name === 'typebot-docs'), 'docRoots() = DOCS + typebot-docs');

done();
```

- [ ] **Step 2: Run — expect FAIL** (`Cannot find module '../lib/sources.js'`)

```bash
node ~/.claude/hooks/test/test-sources.js
```

- [ ] **Step 3: Implement `lib/sources.js`**

```javascript
'use strict';
// sources.js — parse the memory worker's sources.yml (authoritative source registry).
// The file is a flat YAML list; we parse it line-oriented (no YAML dep). Fail-open.
const fs = require('fs');

const SOURCES_YML = process.env.R0_SOURCES_YML
  || '/opt/workstation/configs/ai-memory-worker/sources.yml';

// NOTE: the real sources.yml uses YAML BLOCK-LIST tags (not inline []):
//   tags:
//     - "kind:official-docs"
// Parse block-list via an inTags flag; keep the inline [..] regex as fallback.
function _parse() {
  // Returns [{name, root, scope, kinds:[...]}] from a flat `sources:` list.
  const raw = fs.readFileSync(SOURCES_YML, 'utf8');
  const out = [];
  let cur = null;
  let inTags = false;
  for (const lineRaw of raw.split('\n')) {
    const line = lineRaw.replace(/#.*$/, '');           // strip comments
    const mName = line.match(/^\s*-\s*name:\s*["']?([^"'\n]+?)["']?\s*$/);
    if (mName) { if (cur) out.push(_finish(cur)); cur = { name: mName[1].trim(), root: '', tags: [] }; inTags = false; continue; }
    if (!cur) continue;
    const mRoot = line.match(/^\s*root:\s*["']?([^"'\n]+?)["']?\s*$/);
    if (mRoot) { cur.root = mRoot[1].trim(); inTags = false; continue; }
    const mTags = line.match(/^\s*tags:\s*\[(.*)\]\s*$/);   // inline fallback
    if (mTags) {
      cur.tags = mTags[1].split(',').map(t => t.replace(/["'\s]/g, '')).filter(Boolean);
      inTags = false; continue;
    }
    if (/^\s*tags:\s*$/.test(line)) { inTags = true; continue; }   // block-list start
    if (inTags) {
      const mItem = line.match(/^\s*-\s*["']?([^"'\n#]+?)["']?\s*$/);
      if (mItem) { cur.tags.push(mItem[1].trim()); continue; }
      inTags = false; // first non-list line ends the tags block
    }
  }
  if (cur) out.push(_finish(cur));
  return out;
}

function _finish(s) {
  const kinds = s.tags.filter(t => t.startsWith('kind:')).map(t => t.slice('kind:'.length));
  const scopeTag = s.tags.find(t => t.startsWith('scope:'));
  return { name: s.name, root: s.root, scope: scopeTag ? scopeTag.slice('scope:'.length) : '', kinds };
}

function all() {
  try {
    const a = _parse().filter(s => s.root);
    return a.length ? a : _failopen(process.cwd());
  } catch (_) { return _failopen(process.cwd()); }
}

function _failopen(cwd) {
  const path = require('path');
  return [{ name: path.basename(cwd), root: cwd, scope: '', kinds: [] }];
}

// Longest-prefix root match against cwd. Unknown cwd → fail-open basename source.
function detect(cwd) {
  const path = require('path');
  const c = cwd || process.cwd();
  let best = null;
  for (const s of all()) {
    if (c === s.root || c.startsWith(s.root.replace(/\/?$/, '/'))) {
      if (!best || s.root.length > best.root.length) best = s;
    }
  }
  return best || { name: path.basename(c), root: c, scope: '', kinds: [] };
}

function docRoots() {
  return all().filter(s => s.kinds.includes('official-docs'));
}

module.exports = { all, detect, docRoots, SOURCES_YML };
```

- [ ] **Step 4: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-sources.js
```
Expected: all `✓`. (If `docRoots()` ≠ 2, re-read `sources.yml` — tag spelling may differ.)

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/lib/sources.js hooks/test/test-sources.js
git commit -m "feat(hooks): lib/sources.js — sources.yml parser (portability foundation)"
```

---

### Task 3: `lib/ledger.js` v2 — action_count + decay (additive)

**Files:**
- Modify: `~/.claude/hooks/lib/ledger.js`
- Create: `~/.claude/hooks/test/test-ledger-v2.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-ledger-v2.js
'use strict';
const { ok, done } = require('./harness');
const fs = require('fs');
const LP = '/tmp/claude-r0-ledger.test.' + process.pid + '.json';
process.env.R0_LEDGER_PATH = LP;
process.env.R0_DECAY_N = '3';                 // tiny decay for the test
function clean() { try { fs.unlinkSync(LP); } catch (_) {} }
clean();
delete require.cache[require.resolve('../lib/ledger.js')];
const L = require('../lib/ledger.js');

L.reset();
ok(L.read().action_count === 0, 'v2 fresh ledger has action_count=0');

L.stampTopic('n8n', 'searched', 'test');
ok(L.lastAction('n8n') === 0, 'stampTopic records last_action = current action_count');
ok(L.isFresh('n8n') === true, 'just-stamped topic is fresh (drift 0 < DECAY_N)');

L.bumpAction(); L.bumpAction(); L.bumpAction();   // action_count → 3, drift = 3 = DECAY_N
ok(L.read().action_count === 3, 'bumpAction increments action_count');
ok(L.isFresh('n8n') === false, 'topic goes stale at drift >= DECAY_N');

L.stampTopic('n8n', 'searched', 'test');           // re-touch refreshes
ok(L.isFresh('n8n') === true, 're-stamp refreshes last_action → fresh again');

// isConsulted / invalidateAll preserved
ok(L.isConsulted('n8n') === true, 'isConsulted preserved (result !== pending)');
L.stampTopic('caddy', 'pending', 'injector');
ok(L.isConsulted('caddy') === false, 'isConsulted false for pending');
L.invalidateAll();
ok(L.allTopics().length === 0, 'invalidateAll preserved');

// v1 migration: write a v1 ledger by hand, read as-is, topic with no last_action → stale
fs.writeFileSync(LP, JSON.stringify({ version: 1, session_started: 'x', topics: { caddy: { ts: 'x', result: 'hit', source: 'q' } } }));
delete require.cache[require.resolve('../lib/ledger.js')];
const L2 = require('../lib/ledger.js');
ok(L2.isFresh('caddy') === false, 'v1 topic without last_action treated as stale (re-arms on next touch)');
ok(L2.isConsulted('caddy') === true, 'v1 topic still satisfies isConsulted (gate path unaffected)');

// corrupt file → {} fail-open
fs.writeFileSync(LP, '{ broken');
delete require.cache[require.resolve('../lib/ledger.js')];
const L3 = require('../lib/ledger.js');
ok(L3.allTopics().length === 0 && L3.isFresh('x') === false, 'corrupt ledger → fail-open empty');

clean();
done();
```

- [ ] **Step 2: Run — expect FAIL** (`L.lastAction is not a function`, `action_count` undefined)

```bash
node ~/.claude/hooks/test/test-ledger-v2.js
```

- [ ] **Step 3: Implement the v2 edits in `lib/ledger.js`**

Edit 1 — PATH env seam (line 13): **ALREADY APPLIED in Task 1 Step 4b — verify it's present, skip if so.**
```javascript
const PATH = process.env.R0_LEDGER_PATH || '/tmp/claude-r0-ledger.json';
```

Edit 2 — DECAY_N constant + v2 empty (replace `_empty`, ~line 29):
```javascript
const DECAY_N = parseInt(process.env.R0_DECAY_N, 10) || 20; // PARAM: stale after N tool-calls of drift

function _empty() {
  return { version: 2, session_started: nowIso(), action_count: 0, topics: {} };
}
```

Edit 3 — `read()` tolerates missing `action_count` (after the `o.topics` guard, ~line 22):
```javascript
    if (!o || typeof o !== 'object') return _empty();
    if (!o.topics || typeof o.topics !== 'object') o.topics = {};
    if (typeof o.action_count !== 'number') o.action_count = 0; // v1 → v2 read-as-is
    return o;
```

Edit 4 — `stampTopic` records `last_action` (replace body, ~line 58):
```javascript
function stampTopic(topic, result, source) {
  if (!topic) return false;
  const o = read();
  o.topics[topic] = { ts: nowIso(), result: result || 'pending', source: source || '', last_action: o.action_count };
  return _write(o);
}
```

Edit 5 — `isFresh` becomes decay-aware (replace body, ~line 75):
```javascript
// frais = touché récemment (drift d'actions < DECAY_N). Trigger A (réarmement sans horloge).
// Tolère last_action absent (ledger v1) → traité comme STALE (le topic se ré-arme au prochain contact).
// Usage: INJECTOR (anti-spam + réarmement). 'pending' compte comme frais tant que dans la fenêtre.
function isFresh(topic) {
  if (!topic) return false;
  const o = read();
  const e = o.topics[topic];
  if (!e) return false;
  if (typeof e.last_action !== 'number') return false; // v1 entry → stale
  return (o.action_count - e.last_action) < DECAY_N;
}
```

Edit 6 — new `bumpAction` + `lastAction` (before `module.exports`, ~line 92):
```javascript
// +1 horloge logique de session — appelé par PreToolUse Bash|Write|Edit (injector).
function bumpAction() {
  const o = read();
  o.action_count = (typeof o.action_count === 'number' ? o.action_count : 0) + 1;
  return _write(o) ? o.action_count : -1;
}

// valeur d'action_count au dernier contact du topic (ou null).
function lastAction(topic) {
  if (!topic) return null;
  const e = read().topics[topic];
  return (e && typeof e.last_action === 'number') ? e.last_action : null;
}
```

Edit 7 — export the new functions (line 93):
```javascript
module.exports = { PATH, read, reset, invalidateAll, stampTopic, invalidate, isFresh, isConsulted, allTopics, bumpAction, lastAction };
```

- [ ] **Step 4: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-ledger-v2.js
```

- [ ] **Step 5: Re-run the founding-gate characterization test — must STILL PASS unchanged**

```bash
node ~/.claude/hooks/test/test-enforcer-gates.js
```
Expected: all `✓`. The enforcer uses `isConsulted`, not `isFresh` — proof the gate path didn't move.

- [ ] **Step 6: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/lib/ledger.js hooks/test/test-ledger-v2.js
git commit -m "feat(hooks): ledger v2 — action_count + decay isFresh (additive, gate path unchanged)"
```

---

### Task 4: `r0-topic-injector.js` — bumpAction (trigger A)

**Files:**
- Modify: `~/.claude/hooks/r0-topic-injector.js:30-46`
- Create: `~/.claude/hooks/test/test-injector-decay.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-injector-decay.js
'use strict';
const { runHook, ok, done } = require('./harness');
const fs = require('fs');
const LP = '/tmp/claude-r0-ledger.test.' + process.pid + '.json';
const env = { R0_LEDGER_PATH: LP, R0_DECAY_N: '3' };
function clean() { try { fs.unlinkSync(LP); } catch (_) {} }
clean();

const inp = { tool_name: 'Bash', cwd: '/home/mobuone/VPAI', tool_input: { command: 'ansible-playbook caddy.yml' } };

// 1st touch on 'caddy' → injects directive + stamps pending
let r = runHook('r0-topic-injector.js', inp, env);
ok(/R0-CONTINU/.test(r.stdout) && /caddy/.test(r.stdout), '1st touch injects caddy directive');

// action_count must have advanced (bumpAction ran)
const led = JSON.parse(fs.readFileSync(LP, 'utf8'));
ok(led.action_count >= 1, 'injector called bumpAction (action_count advanced)');

// immediate 2nd touch → fresh → NO re-injection
r = runHook('r0-topic-injector.js', inp, env);
ok(!/R0-CONTINU/.test(r.stdout), 'fresh topic not re-injected (anti-spam)');

// drift past DECAY_N via other tool-calls → stale → re-injects
runHook('r0-topic-injector.js', { tool_name: 'Bash', tool_input: { command: 'ls' } }, env);
runHook('r0-topic-injector.js', { tool_name: 'Bash', tool_input: { command: 'ls' } }, env);
runHook('r0-topic-injector.js', { tool_name: 'Bash', tool_input: { command: 'ls' } }, env);
r = runHook('r0-topic-injector.js', inp, env);
ok(/R0-CONTINU/.test(r.stdout) && /caddy/.test(r.stdout), 'topic re-armed after DECAY_N drift (trigger A)');

clean();
done();
```

- [ ] **Step 2: Run — expect FAIL** (re-injection never happens; old `isFresh` = "present forever")

```bash
node ~/.claude/hooks/test/test-injector-decay.js
```

- [ ] **Step 3: Implement** — add `ledger.bumpAction()` once per invocation. In `process.stdin.on('end', …)`, after the `data.session_type === 'task'` guard (line 34), before reading `ti`:

```javascript
    if (data.session_type === 'task') process.exit(0); // subagents hors R0

    ledger.bumpAction(); // trigger A : horloge logique de session (avant tout early-exit topic)

    const ti = data.tool_input || {};
```

> `bumpAction` must run on EVERY Bash/Write/Edit (even the memory-search command and no-topic calls) so drift reflects real session activity. It runs before the `MEMORY_CMD` early-exit. Line 45's `filter(t => !ledger.isFresh(t))` is now decay-aware automatically.

- [ ] **Step 4: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-injector-decay.js
```

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/r0-topic-injector.js hooks/test/test-injector-decay.js
git commit -m "feat(hooks): injector bumpAction — event-driven topic re-arm (trigger A)"
```

---

### Task 5: `r0-rex-watcher.js` — re-arm on REX write (trigger B)

**Files:**
- Create: `~/.claude/hooks/r0-rex-watcher.js`
- Create: `~/.claude/hooks/test/test-rex-watcher.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-rex-watcher.js
'use strict';
const { runHook, ok, done } = require('./harness');
const fs = require('fs');
const LP = '/tmp/claude-r0-ledger.test.' + process.pid + '.json';
const env = { R0_LEDGER_PATH: LP, R0_DECAY_N: '20' };
function seed() {
  fs.writeFileSync(LP, JSON.stringify({ version: 2, session_started: 'x', action_count: 5,
    topics: { n8n: { ts: 'x', result: 'searched', source: 'q', last_action: 5 } } }));
}
function fresh(t) { const o = JSON.parse(fs.readFileSync(LP, 'utf8')); return !!o.topics[t]; }

// Write a REX file mentioning n8n → invalidate('n8n')
seed();
runHook('r0-rex-watcher.js', { tool_name: 'Write',
  tool_input: { file_path: '/home/mobuone/VPAI/docs/rex/REX-n8n-deploy.md', content: 'n8n import fix' } }, env);
ok(!fresh('n8n'), 'writing a REX about n8n invalidates the n8n topic (trigger B)');

// Write a non-REX file → no invalidation
seed();
runHook('r0-rex-watcher.js', { tool_name: 'Write',
  tool_input: { file_path: '/home/mobuone/VPAI/roles/n8n/tasks/main.yml', content: 'n8n stuff' } }, env);
ok(fresh('n8n'), 'writing a non-REX file does NOT invalidate (only REX dirs trigger)');

// 5 REX writes invalidate but never trigger a search themselves (watcher only arms)
seed();
let r = runHook('r0-rex-watcher.js', { tool_name: 'Edit',
  tool_input: { file_path: '/home/mobuone/VPAI/docs/runbooks/TROUBLESHOOTING.md', new_string: 'caddy fix' } }, env);
ok(r.code !== 2, 'watcher never blocks (PostToolUse, fail-open)');

done();
```

- [ ] **Step 2: Run — expect FAIL** (`Cannot find module r0-rex-watcher.js`)

```bash
node ~/.claude/hooks/test/test-rex-watcher.js
```

- [ ] **Step 3: Implement `r0-rex-watcher.js`**

```javascript
#!/usr/bin/env node
'use strict';
// r0-rex-watcher.js — PostToolUse hook (matcher: Write|Edit). Trigger B.
// Quand un REX / runbook / audit / TROUBLESHOOTING est écrit, on INVALIDE le(s)
// topic(s) qu'il mentionne → la prochaine action sur ce topic re-grep le chaud
// et le REX frais remonte (boucle d'apprentissage intra-session). N'EFFECTUE
// AUCUNE recherche (anti-spam) : il arme, l'injector consulte au prochain call.
// Fail-open : exit 0 sur erreur, ne bloque jamais.

let ledger, kt;
try { ledger = require('./lib/ledger.js'); kt = require('./lib/known-topics.js'); }
catch (_) { process.exit(0); }

// Chemins dont l'écriture porte une LEÇON (REX) — déclenche le réarmement.
const REX_PATH = /(\/docs\/rex\/|\/docs\/runbooks\/|\/docs\/audits\/|TROUBLESHOOTING\.md$|REX-[^/]*\.md$)/i;

let input = '';
const timer = setTimeout(() => process.exit(0), 3000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => (input += c));
process.stdin.on('end', () => {
  clearTimeout(timer);
  try {
    const data = JSON.parse(input || '{}');
    const tn = data.tool_name || '';
    if (tn !== 'Write' && tn !== 'Edit') process.exit(0);
    const ti = data.tool_input || {};
    const fp = (ti.file_path || ti.path || '').toString();
    if (!REX_PATH.test(fp)) process.exit(0);

    // Topics from the filename + the written content.
    const content = (ti.content || ti.new_string || '').toString();
    const topics = kt.allTopics(fp + ' ' + content.slice(0, 2000));
    topics.forEach(t => ledger.invalidate(t)); // arme — pas de recherche ici

    if (topics.length) {
      process.stdout.write(
        `[R0-REX-WATCHER] REX écrit → topic(s) ré-armé(s) : ${topics.join(', ')}. ` +
        `La prochaine action sur un de ces topics ré-injectera le REX frais.`
      );
    }
    process.exit(0);
  } catch (_) { process.exit(0); }
});
```

- [ ] **Step 4: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-rex-watcher.js
```

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/r0-rex-watcher.js hooks/test/test-rex-watcher.js
git commit -m "feat(hooks): r0-rex-watcher — re-arm topic on REX write (trigger B)"
```

---

### Task 6: `error-escalator.js` — lower thresholds (trigger C)

**Files:**
- Modify: `~/.claude/hooks/error-escalator.js` (`R0_DEBUG_THRESHOLD` default 2→1; `ERROR_ESCALATOR_THRESHOLD` default 5→3)
- Create: `~/.claude/hooks/test/test-error-escalator.js`

- [ ] **Step 1: Read the current file first** to confirm exact lines for the two defaults (Explore: `ERROR_ESCALATOR_THRESHOLD` ~line 23, `R0_DEBUG_THRESHOLD` ~line 43) and how the error counter file is keyed (`/tmp/claude-errors-${sessionId}`, `sessionId = CLAUDE_SESSION_ID || PPID || 'default'`).

```bash
sed -n '18,90p' ~/.claude/hooks/error-escalator.js
```

- [ ] **Step 2: Write the failing test** (drive thresholds via env override so the test is deterministic regardless of defaults; then a separate assertion checks the DEFAULT changed)

```javascript
// ~/.claude/hooks/test/test-error-escalator.js
'use strict';
const { runHook, ok, done } = require('./harness');
const fs = require('fs');
const LP = '/tmp/claude-r0-ledger.test.' + process.pid + '.json';
const SID = 'testsess' + process.pid;
const errFile = '/tmp/claude-errors-' + SID;
const env = { R0_LEDGER_PATH: LP, CLAUDE_SESSION_ID: SID };
function clean() { [LP, errFile].forEach(p => { try { fs.unlinkSync(p); } catch (_) {} }); }
function seedTopic() { fs.writeFileSync(LP, JSON.stringify({ version: 2, session_started: 'x', action_count: 1,
  topics: { caddy: { ts: 'x', result: 'searched', source: 'q', last_action: 1 } } })); }
function freshCaddy() { try { return !!JSON.parse(fs.readFileSync(LP, 'utf8')).topics.caddy; } catch (_) { return false; } }

// A single failing tool-call on a topic command → re-inject + invalidate at failure #1.
// NB: known-topics.firstTopic() returns the LEFTMOST match — the command's first
// known topic MUST be 'caddy' (no earlier 'ansible' etc.), else the escalator
// invalidates the wrong topic and freshCaddy() never flips.
clean(); seedTopic();
const failInp = { tool_name: 'Bash', tool_input: { command: 'make deploy-role ROLE=caddy ENV=prod' }, tool_result: { is_error: true } };
let r = runHook('error-escalator.js', failInp, env);
ok(!freshCaddy(), 'failure #1 on a topic command invalidates the topic (trigger C, threshold=1)');

// Default check: source must declare default 1 and 3 (not 2 and 5)
const src = fs.readFileSync(require('./harness').HOOKS + '/error-escalator.js', 'utf8');
ok(/R0_DEBUG_THRESHOLD[^\n]*\|\|\s*1\b/.test(src) || /R0_DEBUG_THRESHOLD[^\n]*,\s*10\)\s*\|\|\s*1/.test(src), 'R0_DEBUG_THRESHOLD default = 1');
ok(/ERROR_ESCALATOR_THRESHOLD[^\n]*\|\|\s*3\b/.test(src) || /ERROR_ESCALATOR_THRESHOLD[^\n]*,\s*10\)\s*\|\|\s*3/.test(src), 'STOP-archi threshold default = 3');

// STOP-archi message still appears at 3 failures (R5 preserved)
clean(); seedTopic();
for (let i = 0; i < 3; i++) r = runHook('error-escalator.js', failInp, env);
ok(/hypothes|architecture|human|STOP/i.test(r.stdout + r.stderr), 'STOP-archi meta-cognition fires at failure #3 (R5 preserved)');

clean();
done();
```

- [ ] **Step 3: Run — expect FAIL** (defaults still 2 / 5)

```bash
node ~/.claude/hooks/test/test-error-escalator.js
```

- [ ] **Step 4: Implement** — rewrite the two threshold assignments to the **bare-integer fallback form** `parseInt(process.env.X, 10) || N`. The current code uses a quoted string default with no radix (`parseInt(process.env.ERROR_ESCALATOR_THRESHOLD || '5')` / `… || '2'`); the test regex (`\|\|\s*3\b` / `\|\|\s*1\b`, Step 2) requires `||` then whitespace then a bare digit, so the quoted-string form would NOT match. Replace both lines with:

```javascript
// SPEC 2026-06-04 §4 trigger C: ré-injection plus précoce (#1) + STOP-archi conforme LOI « 3 fixes ».
const ERROR_ESCALATOR_THRESHOLD = parseInt(process.env.ERROR_ESCALATOR_THRESHOLD, 10) || 3; // was '5'
// …
const DEBUG_THRESHOLD = parseInt(process.env.R0_DEBUG_THRESHOLD, 10) || 1; // was '2' — keep LHS name `DEBUG_THRESHOLD` (referenced at line 44)
```

> First read the exact current lines (Step 1's `sed`). Preserve the surrounding logic and variable names; only these two assignment expressions change. The env-var override path still works (`parseInt(env, 10)` is `NaN` when unset → falls through to the bare default).

- [ ] **Step 5: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-error-escalator.js
```

- [ ] **Step 6: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/error-escalator.js hooks/test/test-error-escalator.js
git commit -m "feat(hooks): error-escalator thresholds 2->1 / 5->3 (trigger C + R5 STOP-archi)"
```

---

### Task 7: `n8n-validate-marker.js` — validate marker (D1 prerequisite)

The PostToolUse half of D1: records that a `validate_workflow` ran, so the enforcer's PreToolUse gate can check it — the SAME marker mechanism as `r0-marker.js`/`/tmp/claude-r0-done`.

> **Design honesty (residual):** the inline `validate_workflow` payload (a workflow JSON object) cannot be reliably correlated to the *filename* later passed to `n8n import:workflow`. So the marker is **time-windowed and global** (`/tmp/claude-validate-done`, fresh < 30 min) — it asserts "a validate ran recently", matching the founding lesson "validate before import". Per-file correlation is tracked as a future enhancement (N3-adjacent), explicitly out of P1 scope.

**Files:**
- Create: `~/.claude/hooks/n8n-validate-marker.js`
- Create: `~/.claude/hooks/test/test-validate-marker.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-validate-marker.js
'use strict';
const { runHook, ok, done } = require('./harness');
const fs = require('fs');
const MARKER = '/tmp/claude-validate-done';
function clean() { try { fs.unlinkSync(MARKER); } catch (_) {} }
clean();

// validate_workflow MCP call → writes the marker
let r = runHook('n8n-validate-marker.js', { tool_name: 'mcp__n8n-docs__validate_workflow', tool_input: { workflow: { nodes: [] } } });
ok(fs.existsSync(MARKER), 'validate_workflow MCP call writes /tmp/claude-validate-done');
ok(r.code !== 2, 'marker hook never blocks (PostToolUse)');

// n8n_validate_workflow alias also writes
clean();
runHook('n8n-validate-marker.js', { tool_name: 'mcp__n8n-docs__n8n_validate_workflow', tool_input: { id: '123' } });
ok(fs.existsSync(MARKER), 'n8n_validate_workflow alias also writes marker');

// unrelated tool → no marker
clean();
runHook('n8n-validate-marker.js', { tool_name: 'Bash', tool_input: { command: 'ls' } });
ok(!fs.existsSync(MARKER), 'unrelated tool does not write marker');

clean();
done();
```

- [ ] **Step 2: Run — expect FAIL**

```bash
node ~/.claude/hooks/test/test-validate-marker.js
```

- [ ] **Step 3: Implement `n8n-validate-marker.js`**

```javascript
#!/usr/bin/env node
'use strict';
// n8n-validate-marker.js — PostToolUse hook.
// Matcher: mcp__n8n-docs__validate_workflow | mcp__n8n-docs__n8n_validate_workflow
// Écrit /tmp/claude-validate-done (timestamp) — preuve qu'un validate a tourné
// récemment. Le gate D1 de loi-op-enforcer.js le lit avant import:workflow.
// MÊME mécanisme que r0-marker.js. Fail-open : exit 0 toujours.
const fs = require('fs');
const MARKER = '/tmp/claude-validate-done';

let input = '';
const timer = setTimeout(() => process.exit(0), 3000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => (input += c));
process.stdin.on('end', () => {
  clearTimeout(timer);
  try {
    const data = JSON.parse(input || '{}');
    const tn = (data.tool_name || '').toString();
    if (/validate_workflow$/.test(tn)) {
      try { fs.writeFileSync(MARKER, new Date().toISOString()); } catch (_) {}
      process.stdout.write('[VALIDATE-MARKER] validate_workflow enregistré — import:workflow autorisé 30 min.');
    }
    process.exit(0);
  } catch (_) { process.exit(0); }
});
```

- [ ] **Step 4: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-validate-marker.js
```

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/n8n-validate-marker.js hooks/test/test-validate-marker.js
git commit -m "feat(hooks): n8n-validate-marker — record validate_workflow for D1 gate"
```

---

### Task 8: `loi-op-enforcer.js` — R1 hard-gate (D1)

Convert R1 from advisory to a hard block (`exit(2)`+stderr — identical mechanism to the R2/R7 gates) on `n8n import:workflow` / `docker cp *.json javisi_n8n` when no fresh validate marker exists.

**Files:**
- Modify: `~/.claude/hooks/loi-op-enforcer.js` (insert the R1 gate alongside the R7 gates, ~after line 186; keep the existing R1 advisories — they still help on the *edit* step)
- Modify: `~/.claude/hooks/test/test-enforcer-gates.js` (extend with D1 cases)

- [ ] **Step 1: Extend the characterization test with D1 cases**

Append to `test-enforcer-gates.js` (before final `done()`):

```javascript
// ── D1: R1 hard-gate on import:workflow ──────────────────────────────────────
const VMARK = '/tmp/claude-validate-done';
function rmMark() { try { fs.unlinkSync(VMARK); } catch (_) {} }

// No validate marker → import:workflow BLOCKS.
// NB: `n8n import:workflow` is BOTH a known topic (n8n) AND state-modifying-bash,
// so the EXISTING R0-GATE (lines 82-100) would fire first with [R0-GATE]. To reach
// and assert the R1 gate, satisfy R0 first by writing a fresh global marker.
clean(); rmMark();
fs.writeFileSync('/tmp/claude-r0-done', new Date().toISOString()); // satisfy R0 so R1 gate is reached
r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'n8n import:workflow --input=mop-get.json' } }, env);
ok(r.code === 2 && /\[R1-GATE\]/.test(r.stderr), 'D1: import:workflow without validate marker blocks (exit 2)');

// docker cp *.json javisi_n8n → also blocks (NOT state-modifying-bash, so R0 gate does not fire here)
clean(); rmMark();
r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'docker cp wf.json javisi_n8n:/tmp/wf.json' } }, env);
ok(r.code === 2 && /\[R1-GATE\]/.test(r.stderr), 'D1: docker cp json to javisi_n8n without validate marker blocks');

// With a FRESH validate marker → import allowed (note: R0 marker also needed since n8n is a topic)
clean(); rmMark();
fs.writeFileSync(VMARK, new Date().toISOString());
fs.writeFileSync('/tmp/claude-r0-done', new Date().toISOString()); // satisfy R0 gate too
r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'n8n import:workflow --input=mop-get.json' } }, env);
ok(r.code !== 2, 'D1: import:workflow WITH fresh validate marker (+R0) is allowed');
try { fs.unlinkSync('/tmp/claude-r0-done'); } catch (_) {}
rmMark();
```

- [ ] **Step 2: Run — expect FAIL** (R1 currently advisory; `[R1-GATE]` absent, import not blocked)

```bash
node ~/.claude/hooks/test/test-enforcer-gates.js
```

- [ ] **Step 3: Implement the R1 gate.** Insert this block in `loi-op-enforcer.js` immediately AFTER the localhost:5678 R7 gate (after line 186, before the R8 advisory at line 188). Place it inside the `try` of the `stdin 'end'` handler so `toolName`/`cmd` are in scope:

```javascript
    // ── R1 GATE (BLOCKING) — D1 : valider AVANT d'importer (leçon fondatrice 806/0) ──
    // Bloque import:workflow / docker cp *.json javisi_n8n si aucun validate_workflow
    // récent (marqueur écrit par n8n-validate-marker.js). Même mécanisme que R2/R7.
    {
      const VALIDATE_MARKER = '/tmp/claude-validate-done';
      const VALIDATE_MAX_AGE_MS = 30 * 60 * 1000; // 30 min
      const isImport = toolName === 'Bash' && (
        /n8n\s+import:workflow/.test(cmd) ||
        /docker\s+cp\s+\S*\.json\s+javisi_n8n/.test(cmd)
      );
      function validateFresh() {
        try { return (Date.now() - require('fs').statSync(VALIDATE_MARKER).mtimeMs) < VALIDATE_MAX_AGE_MS; }
        catch (_) { return false; }
      }
      if (isImport && !validateFresh()) {
        process.stderr.write(
          `[R1-GATE] BLOQUÉ — import workflow n8n sans validate_workflow récent (<30min).\n\n` +
          `Valider d'abord (MCP, zéro erreur bloquante) :\n` +
          `  mcp__n8n-docs__validate_workflow  (passer le JSON complet du workflow)\n\n` +
          `Règle LOI R1 — leçon fondatrice : 806 Bash / 0 MCP / 23 auto-compacts.\n` +
          `Voir docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md R1.\n`
        );
        process.exit(2);
      }
    }
    // ── FIN R1 GATE ──────────────────────────────────────────────────────────
```

> The existing R1 *advisories* (lines 119-135) stay — they fire on the JSON-edit step, earlier in the flow. This gate fires on the import/deploy step. Two complementary layers.

- [ ] **Step 4: Run — expect PASS (all old + new D1 assertions)**

```bash
node ~/.claude/hooks/test/test-enforcer-gates.js
```
Expected: every founding-gate assertion STILL passes + the 3 D1 assertions pass.

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/loi-op-enforcer.js hooks/test/test-enforcer-gates.js
git commit -m "feat(hooks): R1 hard-gate — block import:workflow without validate (D1, closes 806/0)"
```

#### Task 8b — R0-GATE precision: exempt pure-doc writes from the hard-block

Folded in per operator decision (2026-06-04): the R0 hard-gate fires on `isWriteEdit && topicMatch` regardless of path, so editing a markdown doc/memory/plan that merely *mentions* a topic (`n8n`, `caddy`…) gets `exit 2`'d — observed 4× in one session, including a block on editing this plan. Fix: exempt pure-doc/memory/plan paths from the hard block while KEEPING the DOC_CREATION advisory. Infra actions (state-modifying Bash, workflow-JSON edits) still hard-block. Separate concern from D1 → separate commit on the same file.

- [ ] **Step 6: Add doc-exemption assertions to `test-enforcer-gates.js`** (append before final `done()`)

```javascript
// ── R0-GATE precision: pure-doc writes are NOT hard-blocked (advisory only) ──
clean(); // empty ledger, no markers
// Markdown doc under docs/ mentioning n8n → NOT blocked (was the false positive)
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', tool_input: { file_path: '/home/mobuone/VPAI/docs/superpowers/plans/x.md', content: 'a plan that mentions n8n and caddy' } }, env);
ok(r.code !== 2, 'R0 precision: writing a .md plan mentioning a topic is NOT hard-blocked');
// Memory file mentioning a topic → NOT blocked
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', tool_input: { file_path: '/home/x/.claude/projects/p/memory/MEMORY.md', content: 'note about n8n' } }, env);
ok(r.code !== 2, 'R0 precision: writing a memory .md mentioning a topic is NOT hard-blocked');
// But a workflow JSON edit on a topic STILL hard-blocks (infra artifact, not a doc)
clean();
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', tool_input: { file_path: '/x/scripts/n8n-workflows/foo.json', content: 'n8n workflow' } }, env);
ok(r.code === 2 && /\[R0-GATE\]/.test(r.stderr), 'R0 precision: workflow JSON edit still hard-blocks (intent = infra)');
// And state-modifying Bash on a topic STILL hard-blocks
r = runHook('loi-op-enforcer.js', { tool_name: 'Bash', tool_input: { command: 'make deploy-role ROLE=caddy ENV=prod' } }, env);
ok(r.code === 2 && /\[R0-GATE\]/.test(r.stderr), 'R0 precision: state-modifying Bash on topic still hard-blocks');
```

- [ ] **Step 7: Run — expect FAIL** (first two assertions fail: docs currently hard-blocked)

```bash
node ~/.claude/hooks/test/test-enforcer-gates.js
```

- [ ] **Step 8: Implement the exemption.** In `loi-op-enforcer.js`, near the R0 constants (~line 41-54), add:

```javascript
    // Chemins PURE-DOC : l'écriture mentionne un topic mais n'agit PAS sur l'infra.
    // Exemptés du hard-block R0 (l'advisory DOC_CREATION reste). Match intent, pas string.
    const DOC_EXEMPT = /(\/docs\/.*\.md$|\/\.planning\/.*\.md$|\/memory\/[^/]*\.md$|MEMORY\.md$|REX-[^/]*\.md$|\.loi-binding\.yml$)/;
```

Then change the gate trigger condition (line 88) from:

```javascript
          if (isStateModifyingBash || isWriteEdit) {
```
to:

```javascript
          // Write/Edit ne déclenche le hard-block que si ce n'est PAS un pur doc (precision intent).
          if (isStateModifyingBash || (isWriteEdit && !DOC_EXEMPT.test(filePath))) {
```

> Note: the workflow-JSON path `scripts/n8n-workflows/*.json` is NOT matched by `DOC_EXEMPT` (it's `.json`, not `.md`), so it still hard-blocks — correct: a workflow JSON is an infra artifact, not a doc. The DOC_CREATION advisory (line 110-117) is unchanged and still fires for exempted docs.

- [ ] **Step 9: Run — expect PASS (all gate assertions, incl. founding + D1 + precision)**

```bash
node ~/.claude/hooks/test/test-enforcer-gates.js
```
Expected: founding R0/R2/R7 still green, D1 green, the 4 precision assertions green.

- [ ] **Step 10: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/loi-op-enforcer.js hooks/test/test-enforcer-gates.js
git commit -m "fix(hooks): R0-GATE precision — exempt pure-doc writes from hard-block (intent>string)"
```

---

### Task 9: `memory-search-start.sh` — portable seed + multi-repo grep (N1+N2)

Replace `case $PROJECT` with `sources.detect`; seed topics from the detected project's newest REX; hot-grep across all source roots + add an official-docs tier.

**Files:**
- Modify: `~/.claude/hooks/memory-search-start.sh`
- Create: `~/.claude/hooks/test/test-memory-search-start.js`

- [ ] **Step 1: Write the failing test** (shell hook; assert on stdout structure)

```javascript
// ~/.claude/hooks/test/test-memory-search-start.js
'use strict';
const { runShell, ok, done } = require('./harness');
const fs = require('fs');
const LP = '/tmp/claude-r0-ledger.test.' + process.pid + '.json';
const env = { R0_LEDGER_PATH: LP };
function clean() { try { fs.unlinkSync(LP); } catch (_) {} ['/tmp/claude-r0-done'].forEach(p => { try { fs.unlinkSync(p); } catch (_) {} }); }
clean();

// startup in VPAI → project detected as VPAI (not basename hack), header present
let r = runShell('memory-search-start.sh', { source: 'startup', cwd: '/home/mobuone/VPAI' }, env);
ok(/project: VPAI/.test(r.stdout), 'startup detects VPAI via sources.detect');
ok(r.code === 0, 'hook exits 0');

// unknown cwd → fail-open basename, no crash
r = runShell('memory-search-start.sh', { source: 'startup', cwd: '/tmp' }, env);
ok(r.code === 0, 'unknown cwd → fail-open, exit 0');

// clear in VPAI → recovery header
clean();
r = runShell('memory-search-start.sh', { source: 'clear', cwd: '/home/mobuone/VPAI' }, env);
ok(/REX recovery/.test(r.stdout), 'clear → recovery mode');

clean();
done();
```

> This test is intentionally light (exit-code + structural markers) because the hook does network/disk I/O against the live worker. Deeper multi-repo labelling is verified manually in Step 5.

- [ ] **Step 2: Run — expect PASS for the header today, but it still uses basename.** Confirm baseline:

```bash
node ~/.claude/hooks/test/test-memory-search-start.js
```
(If `project: VPAI` already passes via basename, that's fine — the test guards against regression, not the mechanism. The mechanism change is verified in Step 5.)

- [ ] **Step 3: Implement N1 — replace `case $PROJECT` (lines 18-27) with sources.detect.** Replace:

```bash
PROJECT="$(basename "$CWD")"

# Topics dominants par projet (primer / fallback recovery)
case "$PROJECT" in
  VPAI|vpai)        TOPICS="ansible caddy n8n litellm" ;;
  flash-studio)     TOPICS="flash-studio saas deployment" ;;
  flash-suite)      TOPICS="flash-suite workflow n8n" ;;
  story-engine)     TOPICS="story-engine content kitsu" ;;
  *)                TOPICS="$PROJECT" ;;
esac
```

with:

```bash
SOURCES="$HOOKS_DIR/lib/sources.js"
# N1 : projet détecté via sources.yml (fin du case cloué VPAI).
PROJECT="$(printf '%s' "$CWD" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(require(process.argv[1]).detect(s.trim()).name)}catch(_){const p=require("path");process.stdout.write(p.basename(s.trim()||"."))}})' "$SOURCES" 2>/dev/null || basename "$CWD")"
PROJECT_ROOT="$(printf '%s' "$CWD" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(require(process.argv[1]).detect(s.trim()).root)}catch(_){process.stdout.write(s.trim())}})' "$SOURCES" 2>/dev/null || echo "$CWD")"
[ -z "$PROJECT_ROOT" ] && PROJECT_ROOT="$CWD"

# N1 : topics-amorce portables = termes known-topics des 5 REX les plus récents du projet.
# Amorce vide tolérée (projet sans docs/rex/) → on s'appuie sur l'injector à l'usage.
TOPICS="$(
  if [ -d "$PROJECT_ROOT/docs/rex" ]; then
    ls -1t "$PROJECT_ROOT/docs/rex"/*.md 2>/dev/null | head -5 | xargs -r cat 2>/dev/null \
      | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const kt=require(process.argv[1]);const t=kt.allTopics(s).slice(0,4);process.stdout.write(t.join(" "))}catch(_){}})' "$HOOKS_DIR/lib/known-topics.js" 2>/dev/null
  fi
)"
# Fallback ultime si amorce vide : le nom du projet (comportement legacy minimal).
[ -z "$TOPICS" ] && TOPICS="$PROJECT"
```

- [ ] **Step 4: Implement N2 — multi-repo hot grep + official-docs tier.** Replace the `grep_hot()` function (lines 38-52) with a version that iterates all source roots and labels cross-project hits, bounded to top-5 total, current project first:

```bash
# grep CHAUD multi-repo (N2) : REX du projet courant d'abord, puis autres repos
# étiquetés [source], puis un palier doc-officielle local. <=5 chemins au total.
grep_hot() {
  local topic="$1" pat
  pat="$(printf '%s' "$topic" | sed 's/-/[ -]/g')"
  local GREP="grep -rIl -i -E"
  command -v rg >/dev/null 2>&1 && GREP="rg -l -i --no-messages -e"

  # 1) projet courant (prioritaire)
  local cur_dirs=()
  for d in "$PROJECT_ROOT/docs/rex" "$PROJECT_ROOT/docs/runbooks" "$PROJECT_ROOT/docs/audits" "$PROJECT_ROOT/.planning"; do
    [ -d "$d" ] && cur_dirs+=("$d")
  done
  [ -f "$PROJECT_ROOT/docs/TROUBLESHOOTING.md" ] && cur_dirs+=("$PROJECT_ROOT/docs/TROUBLESHOOTING.md")
  if [ ${#cur_dirs[@]} -gt 0 ]; then
    $GREP "$pat" "${cur_dirs[@]}" 2>/dev/null | head -5
  fi
}

# Hits cross-repo (autres roots) — étiquetés. Renvoie lignes "  - [source] path".
grep_hot_other() {
  local topic="$1" pat
  pat="$(printf '%s' "$topic" | sed 's/-/[ -]/g')"
  local GREP="grep -rIl -i -E"
  command -v rg >/dev/null 2>&1 && GREP="rg -l -i --no-messages -e"
  # liste {name|root} des sources via sources.js
  printf '%s' "$CWD" | node -e '
    let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
      try{const S=require(process.argv[1]);const cur=S.detect(s.trim()).root;
        S.all().filter(x=>x.root!==cur).forEach(x=>process.stdout.write(x.name+"|"+x.root+"\n"));
      }catch(_){}})' "$HOOKS_DIR/lib/sources.js" 2>/dev/null \
  | while IFS='|' read -r name root; do
      [ -z "$root" ] && continue
      for d in "$root/docs/rex" "$root/docs/runbooks"; do
        [ -d "$d" ] || continue
        $GREP "$pat" "$d" 2>/dev/null | head -2 | sed "s|^|  - [$name] |"
      done
    done | head -3
}

# Palier doc officielle locale (kind:official-docs) — chaud, avant context7/WebSearch.
grep_hot_docs() {
  local topic="$1" pat
  pat="$(printf '%s' "$topic" | sed 's/-/[ -]/g')"
  local GREP="grep -rIl -i -E"
  command -v rg >/dev/null 2>&1 && GREP="rg -l -i --no-messages -e"
  printf '%s' "$CWD" | node -e '
    let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
      try{const S=require(process.argv[1]);S.docRoots().forEach(x=>process.stdout.write(x.name+"|"+x.root+"\n"));}catch(_){}})' \
    "$HOOKS_DIR/lib/sources.js" 2>/dev/null \
  | while IFS='|' read -r name root; do
      [ -d "$root" ] || continue
      $GREP "$pat" "$root" 2>/dev/null | head -2 | sed "s|^|  - [$name] |"
    done | head -3
}
```

Then extend `emit_topic()` (after the existing current-project `hot=...` block, ~line 67-68) to append the two new tiers:

```bash
  hot="$(grep_hot "$topic")"
  [ -n "$hot" ] && { echo "REX CHAUD — projet courant ($PROJECT) :"; printf '%s\n' "$hot" | sed 's/^/  - /'; }
  other="$(grep_hot_other "$topic")"
  [ -n "$other" ] && { echo "REX CHAUD — autres projets :"; printf '%s\n' "$other"; }
  docs="$(grep_hot_docs "$topic")"
  [ -n "$docs" ] && { echo "DOC OFFICIELLE (local, kind:official-docs) :"; printf '%s\n' "$docs"; }
  echo ""
```

> Replace the OLD `grep_hot` usage in `emit_topic` accordingly. Keep `$CWD`-based fallbacks removed in favour of `$PROJECT_ROOT`. The cold search (`emit_topic do_cold=1`) path is unchanged.

- [ ] **Step 5: Run automated test + manual multi-repo check**

```bash
node ~/.claude/hooks/test/test-memory-search-start.js
# Manual: simulate a clear in VPAI, eyeball cross-repo labels
echo '{"source":"clear","cwd":"/home/mobuone/VPAI"}' | bash ~/.claude/hooks/memory-search-start.sh | head -40
```
Expected: test all `✓`; manual output shows `REX CHAUD — projet courant (VPAI)` and, where matches exist, `[flash-studio]`/`[DOCS]`/`[typebot-docs]` labels. Hot grep must complete fast (small REX corpus).

- [ ] **Step 6: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/memory-search-start.sh hooks/test/test-memory-search-start.js
git commit -m "feat(hooks): memory-search-start — sources.detect + multi-repo hot grep (N1+N2)"
```

---

### Task 10: LOI CORE.md + VPAI .loi-binding.yml (split)

**Files:**
- Create: `~/.claude/loi/CORE.md`
- Create: `/home/mobuone/VPAI/.loi-binding.yml`

- [ ] **Step 1: Write `~/.claude/loi/CORE.md`** — R0–R8 as parameterized principles. Params in `{{BRACES}}` resolved from the binding.

```markdown
# LOI CORE — Principes portables (R0–R8)

> Agnostique projet. Les `{{PARAMS}}` sont remplis par `<root>/.loi-binding.yml`
> (résolu via sources.detect). Hors projet connu : CORE seul, params non résolus
> = principe énoncé sans commande concrète. Source de vérité opérationnelle d'un
> projet donné : son `.loi-binding.yml` + ses REX (R9+ y vivent désormais).

| Règle | Principe portable | Param |
|---|---|---|
| R0 | Interroger la mémoire avant tout topic connu ; citer la source ; ne jamais inventer. | `{{MEMORY_CMD}}` |
| R1 | Valider l'artefact via l'outil faisant autorité AVANT de déployer. | `{{VALIDATOR}}` |
| R2 | Vrai navigateur pour tout flux web multi-étapes. | `{{BROWSER_DRIVER}}` |
| R3 | Éditer la source canonique → valider → commit → deploy. Zéro édition UI. | `{{DEPLOY_METHOD}}` |
| R4 | Valider chaque dépendance en isolation (sibling test). | — |
| R5 | systematic-debugging au 1er symptôme ; STOP-architecture à 3 fix. | — |
| R6 | Subagent pour toute investigation > 5 reads / 10 Bash. Envoyer des chemins. | — |
| R7 | Accéder à l'infra par le canal sécurisé sanctionné ; jamais l'endpoint public brut. | `{{SECURE_CHANNEL}}` |
| R8 | Preuve (doc/source/sortie) > souvenir avant toute feature tierce. | — |

Params attendus dans le binding : `MEMORY_CMD, VALIDATOR, SECURE_CHANNEL, DEPLOY_METHOD, BROWSER_DRIVER`.
```

- [ ] **Step 2: Write `/home/mobuone/VPAI/.loi-binding.yml`** — fills params + VPAI-hard rules (R9/R10/R11 reclassed as REX-backed rules).

```yaml
# .loi-binding.yml — instanciation VPAI de LOI-CORE (~/.claude/loi/CORE.md)
# Résolu via sources.detect(cwd). Hors-VPAI : CORE seul.
project: VPAI
params:
  MEMORY_CMD: >-
    set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a;
    /opt/workstation/ai-memory-worker/.venv/bin/python
    /opt/workstation/ai-memory-worker/search_memory.py
    --config /opt/workstation/configs/ai-memory-worker/config.yml --query
  VALIDATOR: "mcp__n8n-docs__validate_workflow (zéro erreur bloquante = prêt)"
  SECURE_CHANNEL: "Tailscale 100.64.0.14 — jamais l'IP publique 137.74.114.167 ni localhost:5678"
  DEPLOY_METHOD: "REST PUT /api/v1/workflows/:id (scripts/deploy-workflow.sh) ; JSON file-first dans scripts/n8n-workflows/"
  BROWSER_DRIVER: "Playwright MCP (browser_navigate → browser_fill_form → browser_click)"

# R9/R10/R11 — anciennement règles dures, désormais REX versionnés (grep chaud + Qdrant).
# Quand n8n monte de version, ces REX se périment via la mémoire, pas par édition manuelle.
rex_rules:
  R9: "IF node n8n 2.7.3 : typeVersion:1 + fixedCollection. typeVersion:2 crashe sur toutes conditions."
  R10: "workflow_history[activeVersionId] = source de vérité d'exécution. Après import CLI : publish:workflow --id=<id>."
  R11: "REST PUT /api/v1/workflows/:id = méthode primaire. Prérequis Caddy : route /api/v1/* → javisi_n8n:5678."
```

- [ ] **Step 3: Sanity-check the binding parses as YAML**

```bash
python3 -c "import yaml,sys; d=yaml.safe_load(open('/home/mobuone/VPAI/.loi-binding.yml')); assert d['project']=='VPAI'; assert set(['MEMORY_CMD','VALIDATOR','SECURE_CHANNEL','DEPLOY_METHOD','BROWSER_DRIVER'])<=set(d['params']); print('binding OK')"
```
Expected: `binding OK`.

- [ ] **Step 4: Commit (two repos, two commits)**

```bash
cd /home/mobuone/.claude
git add loi/CORE.md
git commit -m "feat(loi): CORE.md — R0-R8 portable principles (CORE/BINDING split)"
cd /home/mobuone/VPAI
git add .loi-binding.yml
git commit -m "feat(loi): VPAI .loi-binding.yml — fills CORE params + R9/R10/R11 as REX rules"
```

---

### Task 11: Mobutoo skill — CORE+BINDING engine + ledger-aware re-arm

**Files:**
- Modify: `~/.claude/skills/Mobutoo/SKILL.md`

- [ ] **Step 1: Read the current SKILL.md** to get exact step boundaries (Step 4 = `rm -f /tmp/claude-r0-done*`; Step 1 reads `LOI-OPERATIONNELLE-MCP-FIRST.md`).

```bash
cat ~/.claude/skills/Mobutoo/SKILL.md
```

- [ ] **Step 2: Rewrite Step 1-2 (table source)** to read CORE + detected binding instead of only `LOI-OPERATIONNELLE-MCP-FIRST.md`:

Replace the "read canonical source / build table" steps with:

```markdown
## Step 1 — Resolve LOI for the current project

1. Resolve binding path:
   `node -e 'process.stdout.write(require("/home/mobuone/.claude/hooks/lib/sources.js").detect(process.cwd()).root)'`
   → `<root>`. The binding is `<root>/.loi-binding.yml`.
2. Read `~/.claude/loi/CORE.md` (always).
3. IF `<root>/.loi-binding.yml` exists: read it, substitute `{{PARAMS}}` in the CORE
   table, and append the `rex_rules` (R9/R10/R11) as extra rows.
   ELSE: present CORE alone (9 universal principles) — note "hors projet bindé : CORE seul".

## Step 2 — Display the effective table

Markdown table: Rule | Trigger | Required action. ≤15 words/cell. CORE rows with
params filled from the binding; VPAI adds R9/R10/R11 from `rex_rules`.
```

- [ ] **Step 3: Rewrite Step 4 (the `rm -f` defect)** — ledger-aware re-arm that does NOT nuke consulted topics:

Replace:
```bash
rm -f /tmp/claude-r0-done*
```
with:
```markdown
## Step 4 — Re-arm R0 (ledger-aware)

Do NOT blindly `rm -f /tmp/claude-r0-done*` (that would force re-search of topics
already consulted this session). Instead re-arm only the coarse global marker so
NEW topics re-trigger, while the per-topic ledger (`isConsulted`) preserves work
already done:

```bash
rm -f /tmp/claude-r0-done            # global coarse marker only (NOT the per-topic -<topic> ones)
```

The per-topic markers `/tmp/claude-r0-done-<topic>` and the ledger entries stay,
so consulted topics remain satisfied; only un-consulted topics re-trigger R0.
```

- [ ] **Step 4: Verify the skill still renders** (it's a skill doc — verify the binding-resolution one-liner works):

```bash
cd /home/mobuone/VPAI && node -e 'process.stdout.write(require("/home/mobuone/.claude/hooks/lib/sources.js").detect(process.cwd()).root)'
```
Expected: `/home/mobuone/VPAI`.

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add skills/Mobutoo/SKILL.md
git commit -m "feat(mobutoo): CORE+BINDING engine + ledger-aware re-arm (no blind rm)"
```

---

### Task 12: Wire new hooks in settings.json + full regression

The spec mandates testing each hook in isolation BEFORE wiring (§9). Now wire the two NEW hooks (the modified ones are already wired).

**Files:**
- Modify: `~/.claude/settings.json` (PostToolUse section, ~lines 143-203)

- [ ] **Step 1: Back up settings.json + validate it is currently valid JSON**

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8")); console.log("valid")'
```

- [ ] **Step 1b: Fix the `ERROR_ESCALATOR_THRESHOLD` env override** (discovered during T6 execution). `settings.json` line ~7 has `"ERROR_ESCALATOR_THRESHOLD": "5"` in its `env` block, which OVERRIDES the new code default of 3 — making T6's STOP-archi=3 change inert live. Change that value to `"3"` so the spec's STOP-archi-at-3 actually takes effect:

```json
"ERROR_ESCALATOR_THRESHOLD": "3",
```
(`R0_DEBUG_THRESHOLD` is NOT in the env block, so its new default 1 already applies live — no change needed there.)

- [ ] **Step 2: Add the r0-rex-watcher PostToolUse entry** (matcher `Write|Edit`, timeout 3) and the validate-marker entry (matcher `mcp__n8n-docs__validate_workflow|mcp__n8n-docs__n8n_validate_workflow`, timeout 3) to the `PostToolUse` array. Each entry follows the existing format:

```json
{
  "matcher": "Write|Edit",
  "hooks": [
    { "type": "command", "command": "node /home/mobuone/.claude/hooks/r0-rex-watcher.js", "timeout": 3 }
  ]
},
{
  "matcher": "mcp__n8n-docs__validate_workflow|mcp__n8n-docs__n8n_validate_workflow",
  "hooks": [
    { "type": "command", "command": "node /home/mobuone/.claude/hooks/n8n-validate-marker.js", "timeout": 3 }
  ]
}
```

- [ ] **Step 3: Validate the edited JSON**

```bash
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8")); console.log("valid")'
```
Expected: `valid`. If it throws, restore from `.bak` and redo.

- [ ] **Step 4: Run the FULL test suite — regression gate**

```bash
bash ~/.claude/hooks/test/run-all.sh
```
Expected: `ALL TESTS PASS`. This re-runs every per-hook test + the founding-gate characterization (R0/R2/R7 still block, ledger v2, sources, injector decay, rex-watcher, error-escalator, validate-marker, D1, memory-search-start).

- [ ] **Step 5: Manual smoke — confirm hooks fire in a real session context**

```bash
# r0-rex-watcher fires on a REX-path write (simulate via direct stdin)
echo '{"tool_name":"Write","tool_input":{"file_path":"/home/mobuone/VPAI/docs/rex/REX-smoke.md","content":"caddy test"}}' | node ~/.claude/hooks/r0-rex-watcher.js
# validate-marker fires
echo '{"tool_name":"mcp__n8n-docs__validate_workflow","tool_input":{"workflow":{}}}' | node ~/.claude/hooks/n8n-validate-marker.js && ls -l /tmp/claude-validate-done
rm -f /tmp/claude-validate-done
```
Expected: watcher prints `[R0-REX-WATCHER]`; marker hook prints `[VALIDATE-MARKER]` and the file exists.

- [ ] **Step 6: Commit (`~/.claude`) + remove backup**

```bash
cd /home/mobuone/.claude
rm -f settings.json.bak
git add settings.json
git commit -m "feat(hooks): wire r0-rex-watcher + n8n-validate-marker (P1 complete)"
```

---

## P1 Done-Definition

- [ ] `bash ~/.claude/hooks/test/run-all.sh` → `ALL TESTS PASS`.
- [ ] Founding gates (R0/R2/R7) provably unchanged (characterization test green pre- and post-ledger-v2).
- [ ] Trigger A (decay re-arm), B (REX-write re-arm), C (failure #1 re-inject) each green.
- [ ] D1: `import:workflow` / `docker cp *.json javisi_n8n` blocked without a fresh validate marker.
- [ ] Task 8b: R0-GATE no longer hard-blocks pure-doc writes (advisory kept); workflow-JSON + state-modifying Bash still block.
- [ ] N1+N2: `memory-search-start.sh` uses `sources.detect`; multi-repo hot grep labels cross-project hits; official-docs tier present.
- [ ] CORE/BINDING split shipped; Mobutoo renders CORE+binding and re-arms ledger-aware.
- [ ] All hook commits in `~/.claude` (1 hook = 1 commit); `.loi-binding.yml` committed in VPAI.

## Post-review refinement (executed 2026-06-04, commit `868f4d6`)
Final integration review found that triggers B/C calling `ledger.invalidate(topic)` cleared `isConsulted` (not just `isFresh`), making the R0 hard-gate re-fire spuriously on the next infra action — the same over-blocking friction 8b targets. **Operator chose Option B:** added `ledger.rearm(topic)` (sets `last_action = action_count − DECAY_N − 1` → `isFresh` false for re-injection, entry kept so `isConsulted` stays true → gate does NOT re-block). `r0-rex-watcher.js` (B) and `error-escalator.js` DEBUG-threshold path (C) now call `rearm`; the STOP-archi `invalidateAll()` (3-fix hard reset) is intentionally left as a full reset. Tests updated to decay/isConsulted semantics. 53 assertions green.

## Rollback

Each phase is independently reversible: removing the two NEW `settings.json` entries reverts to legacy behavior — modified hooks degrade gracefully (decay isFresh is additive; thresholds are env-overridable). **R1 gate clarification:** the hook itself never throws (`validateFresh()` is fail-safe — returns `false` on any error), but a missing/expired validate marker means the import IS BLOCKED (`exit 2`), not allowed. So the gate fails *closed* on imports by design (that's the point — no validate, no import); it fails *open* only in the sense that it never crashes. To fully disable D1, remove the R1-GATE block or wire the validate-marker producer. `git revert` per-commit is safe because commits are atomic per hook.

**Ordering hazard (closed during execution):** the live `loi-op-enforcer.js` gained the D1 block the moment Task 8 committed, but its marker producer (`n8n-validate-marker.js`) is only wired in `settings.json`. Leaving that gap means imports are unsatisfiably blocked. Execution brought the `settings.json` wiring forward (right after Task 8) so the gate and its producer go live together.

## Out of scope (later phases, per spec §11)
- P2 MEASURE loop (metrics-aggregator), P3 VERIFY stop-gate, P4 risk-tier + OUTPUT guard.
- N3 archi-version → versioned-doc cross-reference.
- Per-file validate↔import correlation (D1 residual): current marker is time-windowed/global.

### Gate precision (string-match → intent) — R0 part FOLDED into Task 8b; R7 part still backlog
Observed live (4× in the 2026-06-04 session, incl. a hard-block on editing this very
plan because it contains "caddy"/"n8n"): the **R0-GATE and R7-GATE match a topic/IP
*string* anywhere in file content/command, not the *intent* of the action.**
- **R0 (Write/Edit on docs) → FOLDED into Task 8b** (operator decision 2026-06-04): pure
  doc/memory/plan writes (`.md` under `docs/`, `.planning/`, memory dir, `REX-*.md`,
  `.loi-binding.yml`) are exempted from the R0 hard-block, advisory kept.
- **R7 (read-vs-write of an IP/port) → still BACKLOG (candidate P5):** a `grep`/`cat`
  that merely *reads* `137.74.114.167` or `localhost:5678` still hard-blocks. Candidate
  fix: scope the R7 gate to network-verbs that actually *connect* (curl/wget/ssh/scp),
  not pure-read commands. Not folded — deferred.
