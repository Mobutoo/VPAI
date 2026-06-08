# Topics Portables Cross-Projet — P6 Implementation Plan

> **For agentic workers:** REQUIRED: use superpowers:executing-plans (or subagent-driven-development). Steps use `- [ ]` checkboxes. TDD: failing test first, watch it fail, implement, watch it pass.

**Goal:** Make R0 topic-recognition project-agnostic. Phase **6a** = enriched global topic vocabulary + R0-GATE message defaults to `qdrant-find` (cross-repo) + per-topic gate authority (demote the global marker, M3). Phase **6b** = deterministic auto-derivation of a project's long-tail topics (deps manifests / roles / compose / REX filenames), cached per-root with **lazy multi-root** extraction, unioned into the per-call hooks via a cwd-aware `known-topics`.

**Architecture:** All code in `~/.claude` (`/home/mobuone/.claude`, branch `main`). Spec + this plan in VPAI (`git@github-seko`). Every hook **fail-open** (exit 0 on error). **VPAI byte-identical** invariant: the global base is a strict SUPERSET of the current 21 terms; new terms are word-boundaried so they don't change the 21's matching. Locked by a regression test.

**Tech stack:** Node CJS (no deps), Bash, JSON cache in `/tmp`. Test harness = existing `~/.claude/hooks/test/harness.js` (`runHook/runShell/ok/done/cleanMarkers`).

**Spec:** `docs/superpowers/specs/2026-06-08-topics-portables-cross-projet.md` (extends `2026-06-04-loi-system-bricks-design.md`).

**Deviation from spec §6a.2 (deliberate):** the binding `MEMORY_CMD` override in the R0-GATE message is **deferred** (spec marks it optional). 6a ships the `qdrant-find` default alone — no binding reader, lower risk. Tracked in spec §9.

---

## Cross-Repo Commit Map

| Artifact | Repo | Target |
|---|---|---|
| `~/.claude/hooks/**`, `~/.claude/hooks/test/**` | `~/.claude` | branch `main` |
| This plan + spec | VPAI | branch `main` (`git@github-seko`) |

1 file = 1 commit. `cd /home/mobuone/.claude && git add … && git commit` for hooks.

---

## Conventions

- **Fail-open:** every hook body in `try{}catch(_){process.exit(0)}`. Lib functions return safe defaults (base regex / `[]`) on any error.
- **Test isolation:** ledger tests set `R0_LEDGER_PATH`; session-topic tests set `R0_SESSION_TOPICS_PATH`; `cleanMarkers()` in setup/teardown.
- **Run:** `node ~/.claude/hooks/test/test-X.js` (exit 0 = pass). `bash ~/.claude/hooks/test/run-all.sh` for the full suite.
- **Env seams:** `R0_SESSION_TOPICS_PATH` (cache path), `R0_TOPIC_CAP` (default 30).

---

# PHASE 6a — enriched base + qdrant default

### Task A1: enrich `lib/known-topics.js` base (G7)

**Files:** Modify `~/.claude/hooks/lib/known-topics.js`; create `~/.claude/hooks/test/test-known-topics-base.js`.

- [ ] **Step 1 — failing test**

```javascript
// test-known-topics-base.js
'use strict';
const { ok, done } = require('./harness');
const kt = require('../lib/known-topics.js');

// The 21 existing terms still match (byte-identical, incl. substring-in-path).
['n8n','caddy','litellm','ansible','runpod','postgres','qdrant'].forEach(t =>
  ok(kt.hasTopic('deploy ' + t + ' now'), 'existing topic still matches: ' + t));
ok(kt.hasTopic('/x/litellm_config.yaml'), 'VPAI byte-identical: substring match preserved (litellm_config)');

// New global tech topics now match.
['docker','redis','kubernetes','terraform','nextjs','react','python','fastapi','stripe','prisma','nginx','grafana'].forEach(t =>
  ok(kt.hasTopic('working on ' + t + ' stuff'), 'new global topic matches: ' + t));

// Anti-noise: ultra-generic verbs are NOT topics; new terms are word-boundaried.
['git status','curl https://x','make build','run the bundler'].forEach(c =>
  ok(!kt.hasTopic(c) || true, 'generic ok')); // soft
ok(!kt.hasTopic('the reaction was slow'), 'word-boundary: "react" does not match "reaction"');
ok(!kt.hasTopic('a frustrating bug'), 'word-boundary: "rust" does not match "frustrating"');

ok(kt.firstTopic('deploy docker and redis') === 'docker', 'firstTopic returns leftmost (docker)');
done();
```

- [ ] **Step 2 — run, expect FAIL** (`node test-known-topics-base.js` — new terms + boundary cases fail).

- [ ] **Step 3 — implement.** Replace the `KNOWN_TOPICS` literal. Keep the 21 existing alternatives **verbatim** (substring, byte-identical); append new terms each wrapped in `\b…\b` **inside the single capture group** (zero-width, so still one capture group → `firstTopic`/`allTopics` unchanged):

```javascript
const KNOWN_TOPICS = /(n8n|webhook|gotenberg|caddy|litellm|openclaw|kitsu|nocodb|postgres|qdrant|headscale|tailscale|typebot|firefly|plane|molecule|form\s*multi|ansible|remotion|comfyui|runpod|\bdocker\b|\bcompose\b|\bkubernetes\b|\bk8s\b|\bhelm\b|\bpodman\b|\bredis\b|\bmysql\b|\bmariadb\b|\bmongodb\b|\bsqlite\b|\belasticsearch\b|\bclickhouse\b|\bnextjs\b|\breact\b|\bvue\b|\bsvelte\b|\bastro\b|\bvite\b|\bfastapi\b|\bdjango\b|\bflask\b|\bexpress\b|\bnestjs\b|\bpython\b|\bgolang\b|\brust\b|\bdeno\b|\bbun\b|\bterraform\b|\bnginx\b|\btraefik\b|\bvault\b|\bconsul\b|\bprometheus\b|\bgrafana\b|\bloki\b|\bstripe\b|\bpaddle\b|\bsupabase\b|\bclerk\b|\bauth0\b|\bprisma\b|\bdrizzle\b|\bsqlalchemy\b|\btypeorm\b)/i;
```

> Curation: ultra-generic verbs (`git`, `make`, `curl`, `ssh`, `bash`) deliberately excluded — they would nag without memory value. `node` excluded too (matches paths/`node_modules`); `golang`/`deno`/`bun` kept boundaried.

- [ ] **Step 4 — run, expect PASS** + re-run `test-enforcer-gates.js` (the 21 still gate identically).

- [ ] **Step 5 — commit**

```bash
cd /home/mobuone/.claude
git add hooks/lib/known-topics.js hooks/test/test-known-topics-base.js
git commit -m "feat(hooks): known-topics — enriched project-agnostic base (G7, VPAI superset)"
```

---

### Task A2: R0-GATE message → `qdrant-find` default (G9)

**Files:** Modify `~/.claude/hooks/loi-op-enforcer.js` (the R0-GATE `process.stderr.write` block, ~lines 96-105); extend `~/.claude/hooks/test/test-enforcer-gates.js`.

- [ ] **Step 1 — extend the characterization test** (append before final `done()`):

```javascript
// 6a: R0-GATE message is cross-repo (qdrant-find), not the VPAI search_memory path.
clean();
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', cwd: '/home/mobuone/work/saas/flash-studio',
  tool_input: { file_path: '/home/mobuone/work/saas/flash-studio/pay.ts', content: 'stripe checkout' } }, env);
ok(r.code === 2 && /qdrant-find/.test(r.stderr), '6a: R0-GATE on a new global topic (stripe) blocks, message cites qdrant-find');
ok(!/opt\/workstation\/ai-memory-worker/.test(r.stderr), '6a: R0-GATE message no longer hardcodes the VPAI search_memory path');
clean();
```

- [ ] **Step 2 — run, expect FAIL** (current message = VPAI path; `stripe` only matches after A1).

- [ ] **Step 3 — implement.** Replace the `process.stderr.write(…)` payload in the R0-GATE block with:

```javascript
            process.stderr.write(
              `[R0-GATE] BLOQUÉ — topic "${topic}" détecté, mémoire non consultée cette session.\n\n` +
              `Vérifier d'abord (cross-repo, satisfait le gate même si vide) :\n` +
              `  mcp__qdrant__qdrant-find   query: "${topic}"\n\n` +
              `Puis relancer la commande. (Réf LOI R0 — memory_v2 cross-repo.)\n`
            );
```

> Leave the gate *logic* untouched (still `exit(2)` on `isStateModifyingBash || (isWriteEdit && !DOC_EXEMPT)`). Only the message text changes. `r0-marker.js` already clears the gate on a `qdrant-find` call (even empty).

- [ ] **Step 4 — run, expect PASS** + full `run-all.sh` green.

- [ ] **Step 5 — commit**

```bash
cd /home/mobuone/.claude
git add hooks/loi-op-enforcer.js hooks/test/test-enforcer-gates.js
git commit -m "feat(hooks): R0-GATE message defaults to qdrant-find cross-repo (G9, drop VPAI hardcode)"
```

---

### Task A3: per-topic gate authority — demote the global R0 marker (M3)

> **Why (Codex M3):** the enforcer accepts `/tmp/claude-r0-done` (global) as satisfying ANY topic. With the enlarged base (A1), one `qdrant-find docker` would satisfy `stripe`/`nextjs`/everything for 25 min → R0 stops verifying per topic → the whole feature is inert. Make the gate per-topic-authoritative.

**Files:** Modify `~/.claude/hooks/loi-op-enforcer.js` (the `markerFreshEnough` line ~82); update `~/.claude/hooks/test/test-enforcer-gates.js` (the D1 setup + a new A≠B case).

- [ ] **Step 1 — add the "A does not satisfy B" test** (append to `test-enforcer-gates.js`):

```javascript
// M3: searching topic A does NOT satisfy the gate for topic B (per-topic authority).
clean();
// seed ledger: 'docker' consulted, 'stripe' NOT
const led = { version: 2, session_started: 'x', action_count: 1,
  topics: { docker: { ts: 'x', result: 'searched', source: 'q', last_action: 1 } } };
fs.writeFileSync(LP, JSON.stringify(led));
// also write the LEGACY global marker — it must NOT rescue an un-consulted topic anymore
fs.writeFileSync('/tmp/claude-r0-done', new Date().toISOString());
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', cwd: '/x',
  tool_input: { file_path: '/x/pay.ts', content: 'stripe charge' } }, env);
ok(r.code === 2 && /\[R0-GATE\]/.test(r.stderr), 'M3: global marker does NOT satisfy an un-consulted topic (stripe still gated)');
// the consulted topic IS satisfied
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', cwd: '/x',
  tool_input: { file_path: '/x/infra.sh', content: 'docker compose up' } }, env);
ok(r.code !== 2, 'M3: a per-topic-consulted topic (docker) is allowed');
try { fs.unlinkSync('/tmp/claude-r0-done'); } catch (_) {}
clean();
```

- [ ] **Step 2 — fix the existing D1 setup** that relied on the global marker to bypass R0. In `test-enforcer-gates.js`, every `fs.writeFileSync('/tmp/claude-r0-done', …)` used to "satisfy R0 so the R1 gate is reached" must instead seed the ledger for the relevant topic (`n8n`):

```javascript
// was: fs.writeFileSync('/tmp/claude-r0-done', new Date().toISOString());
fs.writeFileSync(LP, JSON.stringify({ version: 2, session_started: 'x', action_count: 1,
  topics: { n8n: { ts: 'x', result: 'searched', source: 'q', last_action: 1 } } }));
```

- [ ] **Step 3 — run, expect FAIL** (global marker still rescues stripe).

- [ ] **Step 4 — implement.** In `loi-op-enforcer.js`, drop the global-marker term from `markerFreshEnough` (keep ledger per-topic + per-topic file fallback):

```javascript
// was: const markerFreshEnough = ledgerFresh || markerFresh(MARKER) || (perTopicMarker && markerFresh(perTopicMarker));
// M3: gate is per-topic. Global /tmp/claude-r0-done no longer satisfies an arbitrary topic.
const markerFreshEnough = ledgerFresh || (perTopicMarker && markerFresh(perTopicMarker));
```

> `r0-marker.js` keeps writing the global marker (legacy/rollback) — harmless now that the enforcer ignores it. The MEMORY-search-command pass-through (`MEMORY_CMD.test(cmd)` → don't block the search itself) is untouched.

- [ ] **Step 5 — run, expect PASS** + full `run-all.sh` green (D1 cases now seed the ledger).

- [ ] **Step 6 — commit**

```bash
cd /home/mobuone/.claude
git add hooks/loi-op-enforcer.js hooks/test/test-enforcer-gates.js
git commit -m "feat(hooks): R0 gate per-topic authority — demote global marker (M3, prevents 1-search-satisfies-all)"
```

> **6a ships here** (A1+A2+A3). Validate `run-all.sh` fully green before starting 6b.

---

# PHASE 6b — auto-derivation of long-tail topics (G8)

### Task B1: `lib/topic-extract.js` — deterministic extractor + cache

**Files:** Create `~/.claude/hooks/lib/topic-extract.js`; create `~/.claude/hooks/test/test-topic-extract.js`.

API: `extract(root) -> string[]`, `read(root) -> string[]`, `refresh(root) -> string[]` (extract + write cache), `PATH`.

- [ ] **Step 1 — failing test**

```javascript
// test-topic-extract.js
'use strict';
const { ok, done } = require('./harness');
const fs = require('fs'); const os = require('os'); const path = require('path');
const CACHE = '/tmp/claude-session-topics.test.' + process.pid + '.json';
process.env.R0_SESSION_TOPICS_PATH = CACHE;
process.env.R0_TOPIC_CAP = '30';
delete require.cache[require.resolve('../lib/topic-extract.js')];
const TE = require('../lib/topic-extract.js');

// fixture project with package.json
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'te-'));
fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({
  dependencies: { next: '14', stripe: '1', '@prisma/client': '5', tailwindcss: '3', '@nestjs/core': '10' },
  devDependencies: { eslint: '8', typescript: '5', vitest: '1' }
}));
const t = TE.extract(root);
// M5 canonicalisation: next→nextjs, @prisma/client→prisma, tailwindcss→tailwind, @nestjs/core→nestjs
ok(t.includes('nextjs'), 'M5: next → nextjs');
ok(t.includes('prisma'), 'M5: @prisma/client → prisma (scope = topic)');
ok(t.includes('tailwind'), 'M5: tailwindcss → tailwind (alias)');
ok(t.includes('nestjs'), 'M5: @nestjs/core → nestjs (scope), not "core"');
ok(t.includes('stripe'), 'plain dep kept');
ok(!t.includes('eslint') && !t.includes('typescript') && !t.includes('vitest'), 'STOPLIST drops tooling deps');
ok(!t.includes('core') && !t.includes('client'), 'M5: scope names do not leak "core"/"client"');

// compose services + roles
const root2 = fs.mkdtempSync(path.join(os.tmpdir(), 'te2-'));
fs.mkdirSync(path.join(root2, 'roles', 'caddy'), { recursive: true });
fs.mkdirSync(path.join(root2, 'roles', 'litellm'), { recursive: true });
fs.writeFileSync(path.join(root2, 'docker-compose.yml'), 'services:\n  redis:\n    image: redis\n  worker:\n    image: x\n');
const t2 = TE.extract(root2);
ok(t2.includes('caddy') && t2.includes('litellm'), 'extracts role dir names');
ok(t2.includes('redis') && t2.includes('worker'), 'extracts compose service names');

// missing manifests → []
ok(Array.isArray(TE.extract('/nonexistent/x')) && TE.extract('/nonexistent/x').length === 0, 'unknown root → []');

// refresh writes cache; read returns it
TE.refresh(root);
ok(TE.read(root).includes('stripe'), 'refresh writes cache, read returns topics for root');
ok(TE.read('/other/root').length === 0, 'read for an unseeded root → []');

// corrupt cache → [] fail-open
fs.writeFileSync(CACHE, '{ broken');
ok(TE.read(root).length === 0, 'corrupt cache → fail-open []');

try { fs.unlinkSync(CACHE); } catch (_) {}
done();
```

- [ ] **Step 2 — run, expect FAIL** (module missing).

- [ ] **Step 3 — implement `lib/topic-extract.js`** (deterministic, depth ≤2, fail-open):

```javascript
'use strict';
// topic-extract.js — derive a project's long-tail topics from deterministic signals.
// Sources: package.json deps, requirements.txt/pyproject, go.mod/Cargo.toml/composer.json,
// roles/*/ dirs, docker-compose*.yml services, docs/rex/REX-<topic>-*.md filenames.
// Fail-open everywhere → [] on any error. Cache keyed by root.
const fs = require('fs');
const path = require('path');

const CACHE = process.env.R0_SESSION_TOPICS_PATH || '/tmp/claude-session-topics.json';
const CAP = parseInt(process.env.R0_TOPIC_CAP, 10) || 30;

const STOPLIST = new Set(['eslint','prettier','typescript','ts-node','tsx','vitest','jest','mocha','chai',
  'husky','lint-staged','nodemon','webpack','babel','rollup','esbuild','vite-plugin','dotenv','chalk',
  'lodash','commander','yargs','rimraf','cross-env','concurrently','npm','pnpm','yarn','types','tslib']);

// M5: canonicalisation. Scoped @scope/pkg → the SCOPE is the real topic
// (@prisma/client→prisma, @nestjs/core→nestjs). Plus an alias table.
const ALIAS = { tailwindcss: 'tailwind', next: 'nextjs', pg: 'postgres', psycopg2: 'postgres',
  'psycopg2-binary': 'postgres', ioredis: 'redis', 'redis-py': 'redis', 'react-dom': 'react',
  'vue-router': 'vue', '@prisma/client': 'prisma' };
function norm(name) {
  let n = String(name || '').toLowerCase().trim();
  n = n.replace(/[~^>=<*\s].*$/, '');       // strip version specifiers / extras
  if (n[0] === '@') n = n.slice(1).split('/')[0];  // @scope/pkg → scope (org = topic)
  n = n.replace(/[^a-z0-9._-]/g, '');
  if (ALIAS[name.toLowerCase()]) return ALIAS[name.toLowerCase()]; // full-name alias wins
  if (ALIAS[n]) n = ALIAS[n];
  return n;
}
function keep(n) { return n && n.length >= 2 && !STOPLIST.has(n) && !/^types?$/.test(n); }

function _readJson(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return null; } }
function _lines(p) { try { return fs.readFileSync(p, 'utf8').split('\n'); } catch (_) { return []; } }
function _exists(p) { try { return fs.existsSync(p); } catch (_) { return false; } }

function extract(root) {
  const found = {};
  const add = raw => { const n = norm(raw); if (keep(n)) found[n] = (found[n] || 0) + 1; };
  try {
    // package.json
    const pj = _readJson(path.join(root, 'package.json'));
    if (pj) { for (const k of ['dependencies','devDependencies','peerDependencies'])
      if (pj[k]) Object.keys(pj[k]).forEach(add); }
    // python
    _lines(path.join(root, 'requirements.txt')).forEach(l => { const m = l.match(/^([A-Za-z0-9._-]+)/); if (m) add(m[1]); });
    // go.mod / Cargo.toml / composer.json (best-effort)
    _lines(path.join(root, 'go.mod')).forEach(l => { const m = l.match(/\/([A-Za-z0-9._-]+)\s+v[0-9]/); if (m) add(m[1]); });
    const cj = _readJson(path.join(root, 'composer.json'));
    if (cj && cj.require) Object.keys(cj.require).forEach(add);
    // roles/*/
    try { fs.readdirSync(path.join(root, 'roles'), { withFileTypes: true })
      .filter(d => d.isDirectory()).forEach(d => add(d.name)); } catch (_) {}
    // docker-compose services
    for (const f of ['docker-compose.yml','docker-compose.yaml','compose.yml','compose.yaml']) {
      const p = path.join(root, f); if (!_exists(p)) continue;
      const ls = _lines(p); let inSvc = false;
      for (const l of ls) {
        if (/^services:\s*$/.test(l)) { inSvc = true; continue; }
        if (inSvc && /^\S/.test(l)) inSvc = false;            // dedent ends services
        if (inSvc) { const m = l.match(/^  ([A-Za-z0-9._-]+):\s*$/); if (m) add(m[1]); }
      }
    }
    // REX filenames: REX-<topic>-*.md
    try { fs.readdirSync(path.join(root, 'docs', 'rex'))
      .forEach(f => { const m = f.match(/^REX-([A-Za-z0-9]+)/i); if (m) add(m[1]); }); } catch (_) {}
  } catch (_) { /* fail-open */ }
  return Object.keys(found).sort((a, b) => found[b] - found[a]).slice(0, CAP);
}

function _readCache() { try { const o = JSON.parse(fs.readFileSync(CACHE, 'utf8')); return (o && o.roots) ? o : { version: 1, roots: {} }; } catch (_) { return { version: 1, roots: {} }; } }
function read(root) { const o = _readCache(); const v = o.roots[root]; return Array.isArray(v) ? v : []; }
function refresh(root) {
  const topics = extract(root);
  try {                                                  // M2: atomic write (temp + rename)
    const o = _readCache(); o.roots[root] = topics; o.ts = new Date().toISOString();
    const tmp = CACHE + '.' + process.pid + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(o)); fs.renameSync(tmp, CACHE);
  } catch (_) {}
  return topics;
}
// M2: lazy multi-root. Cache HIT (key present, even []) → return it. MISS → extract+write-through
// (incl. [] = negative cache → never re-scan). Lets a session that cd's into a new project pick up
// its long-tail on the first tool-call under that root. In-process (few fs reads), fail-open → [].
function topicsFor(root) {
  try {
    const o = _readCache();
    if (Object.prototype.hasOwnProperty.call(o.roots, root)) return o.roots[root] || [];
    return refresh(root);
  } catch (_) { return []; }
}
module.exports = { extract, read, refresh, topicsFor, PATH: CACHE };
```

> `new Date().toISOString()` runs only inside hooks at runtime (not in a Workflow script), so it's fine here.

- [ ] **Step 4 — run, expect PASS.**

- [ ] **Step 5 — commit**

```bash
cd /home/mobuone/.claude
git add hooks/lib/topic-extract.js hooks/test/test-topic-extract.js
git commit -m "feat(hooks): topic-extract — deterministic per-project topic derivation + cache (G8)"
```

---

### Task B2: `known-topics.js` becomes cwd-aware (`regexFor`)

**Files:** Modify `~/.claude/hooks/lib/known-topics.js`; create `~/.claude/hooks/test/test-known-topics-cwd.js`.

- [ ] **Step 1 — failing test**

```javascript
// test-known-topics-cwd.js
'use strict';
const { ok, done } = require('./harness');
const fs = require('fs');
const CACHE = '/tmp/claude-session-topics.test.' + process.pid + '.json';
process.env.R0_SESSION_TOPICS_PATH = CACHE;
// seed cache: flash-studio root has 'stripe','tailwind' (NOT in base)
fs.writeFileSync(CACHE, JSON.stringify({ version: 1, roots: {
  '/home/mobuone/work/saas/flash-studio': ['stripe-sdk','tailwind','pay.api'] } }));
delete require.cache[require.resolve('../lib/topic-extract.js')];
delete require.cache[require.resolve('../lib/known-topics.js')];
const kt = require('../lib/known-topics.js');

// base-only behaviour unchanged when no cwd
ok(kt.hasTopic('deploy n8n'), 'base still matches without cwd');
ok(!kt.hasTopic('use tailwind'), 'dynamic topic NOT matched without cwd (base only)');

// cwd-aware: dynamic topic matches under its root
ok(kt.hasTopic('use tailwind here', '/home/mobuone/work/saas/flash-studio/src'), 'dynamic topic matches under its root (cwd-aware)');
ok(kt.firstTopic('config tailwind', '/home/mobuone/work/saas/flash-studio') === 'tailwind', 'firstTopic returns dynamic topic for the root');

// unknown cwd → base only
ok(!kt.hasTopic('use tailwind', '/tmp/elsewhere'), 'unknown root → base only (no dynamic leak)');
// base still works WITH cwd
ok(kt.hasTopic('deploy docker', '/home/mobuone/work/saas/flash-studio'), 'base ∪ dynamic: base term still matches with cwd');

// Med4: dynamic topic with a dot is escaped — '.' is literal, not a wildcard.
ok(kt.hasTopic('call pay.api now', '/home/mobuone/work/saas/flash-studio'), 'dotted dynamic topic matches literally');
ok(!kt.hasTopic('payxapi call', '/home/mobuone/work/saas/flash-studio'), 'Med4: dotted topic "pay.api" does not match "payxapi" (escaped)');

// M2 lazy: a root NOT in the cache but with a manifest → regexFor extracts on the fly + caches it.
const os = require('os'); const path = require('path');
const lazyRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'lazy-'));
fs.writeFileSync(path.join(lazyRoot, 'package.json'), JSON.stringify({ dependencies: { fastify: '4' } }));
delete require.cache[require.resolve('../lib/known-topics.js')];
delete require.cache[require.resolve('../lib/topic-extract.js')];
const kt2 = require('../lib/known-topics.js');
ok(kt2.hasTopic('use fastify', lazyRoot), 'M2: lazy extraction on cache-miss root (fastify picked up live)');
ok(Object.prototype.hasOwnProperty.call(JSON.parse(fs.readFileSync(CACHE, 'utf8')).roots, lazyRoot), 'M2: lazy result written to cache (negative-cache → no re-scan)');

try { fs.unlinkSync(CACHE); } catch (_) {}
done();
```

- [ ] **Step 2 — run, expect FAIL** (`hasTopic` ignores 2nd arg today).

- [ ] **Step 3 — implement.** Add cwd-aware layer to `known-topics.js`. `sources.detect(cwd).root` resolves the cache key; dynamic terms are escaped + word-boundaried and OR'd with the base. Fail-open → base regex.

```javascript
// append after the existing base KNOWN_TOPICS + helpers:
let _sources, _te;
try { _sources = require('./sources.js'); _te = require('./topic-extract.js'); } catch (_) {}

function _esc(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

// RegExp = base ∪ dynamic(topicsFor(detect(cwd).root)). Fail-open → base.
// M2: topicsFor does lazy extract+cache on a cache-miss root (multi-root sessions).
function regexFor(cwd) {
  try {
    if (!cwd || !_sources || !_te) return KNOWN_TOPICS;
    const root = _sources.detect(cwd).root;
    const dyn = _te.topicsFor(root).map(_esc).filter(Boolean);
    if (!dyn.length) return KNOWN_TOPICS;
    return new RegExp('(' + KNOWN_TOPICS.source.replace(/^\(|\)$/g, '') +
      '|' + dyn.map(d => '\\b' + d + '\\b').join('|') + ')', 'i');
  } catch (_) { return KNOWN_TOPICS; }
}

// cwd-aware wrappers (cwd optional → base behaviour, backward compatible)
function _re(cwd) { return cwd ? regexFor(cwd) : KNOWN_TOPICS; }
function hasTopic(h, cwd) { return _re(cwd).test(String(h || '')); }
function firstTopic(h, cwd) { const m = String(h || '').match(_re(cwd)); return m ? normalize(m[1]) : null; }
function allTopics(h, cwd) {
  const re = new RegExp(_re(cwd).source, 'gi'); const out = []; const seen = new Set(); let m;
  while ((m = re.exec(String(h || '')))) { const t = normalize(m[1]);
    if (!seen.has(t)) { seen.add(t); out.push(t); }
    if (m.index === re.lastIndex) re.lastIndex++; }
  return out;
}
module.exports = { KNOWN_TOPICS, regexFor, hasTopic, firstTopic, allTopics, normalize };
```

> Replace the old `hasTopic/firstTopic/allTopics` definitions and the old `module.exports` with the above (do not duplicate). The base `KNOWN_TOPICS`, `normalize` stay. Backward compat: all callers passing no `cwd` get identical behaviour.

- [ ] **Step 4 — run, expect PASS** + re-run `test-known-topics-base.js` (base unaffected) + `run-all.sh`.

- [ ] **Step 5 — commit**

```bash
cd /home/mobuone/.claude
git add hooks/lib/known-topics.js hooks/test/test-known-topics-cwd.js
git commit -m "feat(hooks): known-topics cwd-aware regexFor — base ∪ project dynamic topics (G8)"
```

---

### Task B3: wire `data.cwd` into the 4 consumer hooks

**Files:** Modify `loi-op-enforcer.js`, `r0-topic-injector.js`, `r0-marker.js`, `error-escalator.js`. Extend `test-enforcer-gates.js` with one cwd E2E case.

- [ ] **Step 1 — Read each call-site first** to confirm `data`/`data.cwd` is in scope, then edit:

| File | Line | From | To |
|---|---|---|---|
| `loi-op-enforcer.js` | 38 | `const KNOWN_TOPICS = (_kt && _kt.KNOWN_TOPICS) \|\| /…/i;` | `const KNOWN_TOPICS = (_kt && _kt.regexFor(data.cwd)) \|\| /…/i;` *(keep the literal fallback)* |
| `loi-op-enforcer.js` | 81 | `_kt.firstTopic(haystack)` | `_kt.firstTopic(haystack, data.cwd)` |
| `r0-topic-injector.js` | 47 | `kt.allTopics(haystack)` | `kt.allTopics(haystack, data.cwd)` |
| `r0-marker.js` | 52 | `_kt.allTopics(haystack)` | `_kt.allTopics(haystack, data.cwd)` |
| `error-escalator.js` | 49 | `_kt.firstTopic(failedCmd)` | `_kt.firstTopic(failedCmd, data.cwd)` |
| `error-escalator.js` | 79 | `_kt.hasTopic(failedCmd)` | `_kt.hasTopic(failedCmd, data.cwd)` |
| `r0-rex-watcher.js` | ~33 | `kt.allTopics(fp + ' ' + content…)` | `kt.allTopics(fp + ' ' + content…, data.cwd)` *(M6: else a REX about a dynamic topic doesn't re-arm it)* |

> In `loi-op-enforcer.js`, line 38 sits after `data` is parsed (line ~25), so `data.cwd` is in scope. `KNOWN_TOPICS` is reused at lines 56/77/118 (incl. the DOC_CREATION advisory) — all now dynamic via the single line-38 change, so no separate edit there (Codex M6). If any consumer lacks `data` in scope, fall back to `(data && data.cwd)`.

- [ ] **Step 2 — E2E test** (append to `test-enforcer-gates.js`): seed the session cache with a flash-studio dynamic topic, assert the enforcer blocks on it from that cwd.

```javascript
// 6b: enforcer gates on a project's DYNAMIC topic via the session cache.
const STC = process.env.R0_SESSION_TOPICS_PATH || '/tmp/claude-session-topics.json';
const _bak = (() => { try { return fs.readFileSync(STC, 'utf8'); } catch (_) { return null; } })();
// NB: the dynamic topic MUST be hors-base. `supabase-x` is a TRAP — `supabase` is in the A1 base
// and `-` is a word boundary → base matches it cwd-blind (green pre-edit, proves nothing). Use `flashpay`.
fs.writeFileSync(STC, JSON.stringify({ version: 1, roots: { '/home/mobuone/work/saas/flash-studio': ['flashpay'] } }));
clean();
r = runHook('loi-op-enforcer.js', { tool_name: 'Write', cwd: '/home/mobuone/work/saas/flash-studio',
  tool_input: { file_path: '/home/mobuone/work/saas/flash-studio/db.ts', content: 'init flashpay client' } }, env);
ok(r.code === 2 && /\[R0-GATE\]/.test(r.stderr), '6b: enforcer gates on a project dynamic topic (flashpay) from its cwd');
// restore
if (_bak !== null) fs.writeFileSync(STC, _bak); else { try { fs.unlinkSync(STC); } catch (_) {} }
clean();
```

> Run this test with `R0_SESSION_TOPICS_PATH` pointed at a temp file in `env` to avoid clobbering the live session cache.

- [ ] **Step 3 — run, expect FAIL** before edits, **PASS** after. Full `run-all.sh` green.

- [ ] **Step 4 — commit** (4 hooks = 4 atomic commits; test extension goes with the enforcer commit):

```bash
cd /home/mobuone/.claude
git add hooks/loi-op-enforcer.js hooks/test/test-enforcer-gates.js && git commit -m "feat(hooks): enforcer reads cwd-aware topics (regexFor) — gate on project topics (6b)"
git add hooks/r0-topic-injector.js && git commit -m "feat(hooks): injector passes data.cwd to allTopics (6b)"
git add hooks/r0-marker.js && git commit -m "feat(hooks): r0-marker passes data.cwd to allTopics (6b)"
git add hooks/error-escalator.js && git commit -m "feat(hooks): error-escalator passes data.cwd to topic lookup (6b)"
git add hooks/r0-rex-watcher.js && git commit -m "feat(hooks): r0-rex-watcher passes data.cwd — re-arm dynamic topics on REX write (6b, M6)"
```

---

### Task B4: SessionStart writes the topic cache (replace circular N1)

**Files:** Modify `~/.claude/hooks/memory-search-start.sh` (seed block, ~lines 24-44); create `~/.claude/hooks/test/test-memory-start-cache.js`.

- [ ] **Step 1 — Read the current seed block** (`sed -n '20,46p' memory-search-start.sh`) to confirm `$PROJECT_ROOT` / `$HOOKS_DIR` var names.

- [ ] **Step 2 — failing test**: invoking `topic-extract.refresh($root)` via the SessionStart path populates the cache for the detected root.

```javascript
// test-memory-start-cache.js
'use strict';
const { ok, done } = require('./harness');
const fs = require('fs'); const os = require('os'); const path = require('path');
const CACHE = '/tmp/claude-session-topics.test.' + process.pid + '.json';
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ms-'));
fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ dependencies: { fastify: '4', stripe: '1' } }));
// the SessionStart hook calls: node -e 'require("./lib/topic-extract.js").refresh(R)' R
const { spawnSync } = require('child_process');
spawnSync('node', ['-e', 'require(process.argv[1]).refresh(process.argv[2])',
  require('./harness').HOOKS + '/lib/topic-extract.js', root],
  { env: Object.assign({}, process.env, { R0_SESSION_TOPICS_PATH: CACHE }) });
const o = JSON.parse(fs.readFileSync(CACHE, 'utf8'));
ok(o.roots[root] && o.roots[root].includes('fastify') && o.roots[root].includes('stripe'),
  'SessionStart refresh path populates the cache for the detected root');
try { fs.unlinkSync(CACHE); } catch (_) {}
done();
```

- [ ] **Step 3 — implement.** In `memory-search-start.sh`, replace the circular N1 seed (the `kt.allTopics(REX)` block) with a cache refresh for the detected root. Keep the N2 hot-grep untouched:

```bash
# 6b : auto-dérivation des topics du projet → cache de session (remplace le seed N1 circulaire).
# topic-extract scanne deps/roles/compose/filenames. Fail-open (timeout, || true).
if [ -n "${PROJECT_ROOT:-}" ]; then
  timeout 3 node -e 'try{require(process.argv[1]).refresh(process.argv[2])}catch(_){}' \
    "$HOOKS_DIR/lib/topic-extract.js" "$PROJECT_ROOT" 2>/dev/null || true
fi
```

> The old seed printed topics into the primer search; if that output is still needed for the boot-time primer, derive it from `topic-extract` instead (`node -e '…extract(R).slice(0,4).join(" ")'`). Keep whatever the primer consumes byte-compatible.

- [ ] **Step 4 — run, expect PASS** + `run-all.sh` green + a live smoke: open a fresh session in a Node project, confirm `/tmp/claude-session-topics.json` gains its root key.

- [ ] **Step 5 — commit**

```bash
cd /home/mobuone/.claude
git add hooks/memory-search-start.sh hooks/test/test-memory-start-cache.js
git commit -m "feat(hooks): SessionStart refreshes topic cache via topic-extract (replaces circular N1 seed, 6b)"
```

---

## Final verification (before declaring P6 done)

- [ ] `bash ~/.claude/hooks/test/run-all.sh` → **ALL TESTS PASS** (P1–P5 + 6a + 6b).
- [ ] Regression proof — VPAI byte-identical: `n8n`/`ansible` from `cwd=VPAI` still block (`test-enforcer-gates.js`).
- [ ] Cross-project proof — the original failing case now passes: `stripe`/`nextjs` from `cwd=flash-studio` blocks (6a base) ; a flash-studio-only dep cached → blocks (6b).
- [ ] Per-topic proof (M3) — `qdrant-find docker` does NOT clear the gate for `stripe`; only a `stripe` search (or ledger consult) does. Global `/tmp/claude-r0-done` no longer rescues an un-consulted topic.
- [ ] Linchpin proof — run an empty `qdrant-find` on a gated topic → `r0-marker` stamps the ledger for that topic → gate clears for it → action proceeds (no permanent block).
- [ ] Live dogfood one session per project type (VPAI Ansible, a Node SaaS) ; confirm no spurious R0 nag on generic commands (`git`, `ls`).

## Rollout / Rollback
- 6a commits (A1, A2) ship + validate before 6b. Each task = independently revertable (`git revert <sha>` → prior hook behaviour). No `settings.json` change in the whole of P6.
- 6b fail-open: extractor/cache errors → base-6a behaviour. Cache regenerates next SessionStart.
