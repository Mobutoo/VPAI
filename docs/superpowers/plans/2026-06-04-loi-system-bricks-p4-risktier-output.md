# LOI Système de Briques — P4 (risk-tier + OUTPUT guard) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two output-side guardrails of the agentic loop: (1) a **risk-tier HITL gate** that hard-blocks the actual Bash execution of irreversible `high`-risk commands until an explicit ack, and (2) an **OUTPUT guard** that scans the current turn's assistant output for secret/PII leakage and alerts (advisory + log).

**Architecture:**
- `risk-tier-guard.js` — PreToolUse on `Bash`. Matches `tool_input.command` against a `high`-risk table (reversibility-based). On match without a fresh `/tmp/claude-highrisk-ack`, `exit(2)` + stderr (same hard-gate mechanism as R0/R2/R7/R1), explaining the risk and how to acknowledge. The ack is consumed on use, so a false positive costs exactly one ack. It hooks ONLY `Bash` and reads the command-to-execute, so it cannot fire on a file *mention* of a dangerous string (that would be Write/Edit). Fail-open.
- `output-guard.sh` — Stop hook. Turn-scoped (same awk technique as `verify-stop-gate.sh`) over the current turn's **assistant text**, scanning for secret/PII patterns (private keys, known token prefixes, the Sese public IP, `password=`/`secret=` with values). On a hit: append to `~/.claude/metrics/secret-alerts.jsonl` AND emit a one-time non-looping advisory nudge ("secret possibly exposed — rotate?"). Alert over block (it's after-the-fact by nature). Fail-open.

**Tech Stack:** Node (risk-tier, consistent with the other gate hooks) + Bash (output-guard, consistent with verify-stop-gate). Test harness `runHook`/`runShell` + env seams + ack/marker fixtures.

**Design decisions (operator, 2026-06-04):** HITL = hard-block + ack marker. High-risk set = make deploy-prod, SQL UPDATE/DELETE, ctr leases delete / docker rm -v/volume rm, rm -rf, git push --force, ansible prod, vault destroy. OUTPUT guard = advisory + log.

**Spec:** `docs/superpowers/specs/2026-06-04-loi-system-bricks-design.md` §7 D4 + §8. Extends P1/P2/P3.

---

## Current substrate (verified 2026-06-04)
- PreToolUse `Bash` hooks already wired: `bash-lint.js`, `loi-op-enforcer.js`, `r0-topic-injector.js`, `mcp-intent-guard.js`, `gsd-validate-commit.sh`. The existing hard gates use `process.stderr.write(...) + process.exit(2)`.
- Stop hooks (post-P3): `stop-gate.sh`, `session-memory-writer.sh`, `metrics-aggregator.sh`, `verify-stop-gate.sh`. The turn-scoping awk idiom is in `verify-stop-gate.sh`.
- `~/.claude/metrics/` is created by `metrics-aggregator.sh`.
- `loi-op-enforcer.js` already blocks the Sese public IP `137.74.114.167` in Bash commands (R7) — OUTPUT guard's IP scan is about that IP appearing in the assistant's OWN response text, a different surface.

## File Structure
| Path | Responsibility |
|---|---|
| `~/.claude/hooks/risk-tier-guard.js` | NEW. PreToolUse Bash — hard-block high-risk command execution until ack. |
| `~/.claude/hooks/output-guard.sh` | NEW. Stop — scan turn's assistant output for secrets/PII, log + one-time advisory. |
| `~/.claude/hooks/test/test-risk-tier-guard.js` | NEW. |
| `~/.claude/hooks/test/test-output-guard.js` | NEW. |
| `~/.claude/settings.json` | Modify. Add risk-tier to PreToolUse Bash; output-guard to Stop. |

## Conventions
- Fail-open everywhere; deliberate gate via `exit(2)` (risk-tier) only.
- Risk-tier matches ONLY `tool_name === 'Bash'` `command`. Never Write/Edit (no mention/read false-positives).
- Ack escape keeps a false positive cheap (one marker). Document each `high` pattern.
- Test isolation via ack/marker paths under `/tmp/...test.<pid>` and env seams; `cleanMarkers`-style teardown.

---

### Task 1: `risk-tier-guard.js` (HITL hard-block) + test

**Files:**
- Create: `~/.claude/hooks/risk-tier-guard.js`
- Create: `~/.claude/hooks/test/test-risk-tier-guard.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-risk-tier-guard.js
'use strict';
const { runHook, ok, done } = require('./harness');
const fs = require('fs');
const ACK = '/tmp/claude-highrisk-ack';
function clean() { try { fs.unlinkSync(ACK); } catch (_) {} }
const blocks = r => r.code === 2 && /\[RISK-HIGH\]/.test(r.stderr);
clean();

// Each high-risk command (real Bash execution) → block without ack
const HIGH = [
  'make deploy-prod',
  'make deploy-role ROLE=caddy ENV=prod',
  'ansible-playbook playbooks/hosts/app-prod.yml',
  'ansible-playbook playbooks/stacks/site.yml',
  "psql -c 'DELETE FROM users WHERE id=1'",
  "docker exec javisi_postgresql psql -c 'UPDATE users SET admin=true'",
  'sudo ctr -n moby leases delete abc123',
  'docker rm -v javisi_n8n',
  'docker volume rm pgdata',
  'rm -rf /home/mobuone/VPAI/roles',
  'rm -r -f /home/mobuone/VPAI/roles',
  'rm -fR /home/mobuone/important',
  'git push --force origin main',
  'git push -f origin main',
  'vault secrets destroy kv/foo',
];
for (const cmd of HIGH) {
  clean();
  const r = runHook('risk-tier-guard.js', { tool_name: 'Bash', tool_input: { command: cmd } });
  ok(blocks(r), 'high-risk blocks (exit2): ' + cmd.slice(0, 40));
}

// With a fresh ack → allowed + ack consumed
clean(); fs.writeFileSync(ACK, '1');
let r = runHook('risk-tier-guard.js', { tool_name: 'Bash', tool_input: { command: 'make deploy-prod' } });
ok(r.code !== 2, 'high-risk WITH ack → allowed');
ok(!fs.existsSync(ACK), 'ack consumed on use');

// Low-risk commands → never block
clean();
for (const cmd of ['ls -la', 'git status', 'docker ps', 'make lint', 'rm -rf /tmp/scratch.test', 'git push origin main', 'grep -r foo .']) {
  r = runHook('risk-tier-guard.js', { tool_name: 'Bash', tool_input: { command: cmd } });
  ok(r.code !== 2, 'low-risk not blocked: ' + cmd);
}

// NOT a Bash tool → never block (a Write whose CONTENT mentions a dangerous cmd)
r = runHook('risk-tier-guard.js', { tool_name: 'Write', tool_input: { file_path: '/x/doc.md', content: 'run make deploy-prod then rm -rf /' } });
ok(r.code !== 2, 'Write mentioning a dangerous command is NOT blocked (only real Bash execution)');

// rm -rf strictly under /tmp → not blocked (common safe cleanup)
r = runHook('risk-tier-guard.js', { tool_name: 'Bash', tool_input: { command: 'rm -rf /tmp/claude-foo.test' } });
ok(r.code !== 2, 'rm -rf under /tmp only → not high-risk');

// git push --force-with-lease → not blocked (safe variant)
r = runHook('risk-tier-guard.js', { tool_name: 'Bash', tool_input: { command: 'git push --force-with-lease origin feat' } });
ok(r.code !== 2, '--force-with-lease is the safe variant → not blocked');

// Garbage stdin → fail-open
const { runHookRaw } = require('./harness');
r = runHookRaw('risk-tier-guard.js', '{ broken', {});
ok(r.code !== 2, 'garbage stdin → fail-open (no block)');

clean();
done();
```

- [ ] **Step 2: Run — expect FAIL**

```bash
node ~/.claude/hooks/test/test-risk-tier-guard.js
```

- [ ] **Step 3: Implement `risk-tier-guard.js`**

```javascript
#!/usr/bin/env node
'use strict';
// risk-tier-guard.js — PreToolUse (Bash). P4 risk-tier HITL (SPEC §7 D4).
// Hard-block (exit 2) l'EXÉCUTION Bash d'une commande HIGH-risk (irréversible)
// tant qu'un ack explicite n'existe pas (/tmp/claude-highrisk-ack, consommé à l'usage).
// Escape cheap : un faux positif coûte un ack. Ne lit que tool_input.command d'un
// Bash → ne peut PAS se déclencher sur une mention de la commande dans un fichier.
// Même mécanisme que les gates R0/R2/R7/R1 (stderr + exit 2). Fail-open : exit 0 sur erreur.
const fs = require('fs');
const ACK = '/tmp/claude-highrisk-ack';

// rm récursif-ET-force hors /tmp ? Robuste aux flags séparés (-r -f), collés
// (-rf/-fr), majuscule (-fR). Borné au segment rm (jusqu'au prochain ; && || |)
// pour ne pas attraper un -f d'une autre commande chaînée.
function rmRecursiveForceOutsideTmp(cmd) {
  const m = cmd.match(/\brm\b([^\n;&|]*)/);
  if (!m) return false;
  const seg = m[1];
  const hasR = /(^|\s)-\w*[rR]/.test(seg);   // -r, -rf, -R, -fR…
  const hasF = /(^|\s)-\w*f/.test(seg);      // -f, -rf, -fr…
  if (!hasR || !hasF) return false;
  // Cibles : tokens chemin-absolu / ~ / $HOME du segment. Aucun → relatif/glob → high.
  const toks = seg.split(/\s+/).filter(t => /^(\/|~|\$HOME)/.test(t));
  if (toks.length === 0) return true;
  return toks.some(t => !/^\/tmp(\/|$)/.test(t)); // un seul chemin hors /tmp → high
}

const HIGH = [
  { label: 'make deploy-prod', test: c => /\bmake\s+deploy-prod\b/.test(c) },
  { label: 'make deploy-role ENV=prod', test: c => /\bmake\s+deploy-role\b/.test(c) && /\bENV=prod\b/.test(c) },
  { label: 'ansible-playbook sur prod', test: c => /\bansible-playbook\b/.test(c) && /(app-prod|hosts\/prod|-prod\.yml|stacks\/site\.yml|ENV=prod|-e\s+\w*prod)/i.test(c) },
  { label: 'SQL UPDATE/DELETE', test: c => /\b(UPDATE\s+\S+\s+SET|DELETE\s+FROM)\b/i.test(c) },
  { label: 'ctr leases delete', test: c => /\bctr\b[\s\S]*\bleases\s+delete\b/.test(c) },
  { label: 'docker rm -v / volume rm', test: c => (/\bdocker\b[\s\S]*\brm\b/.test(c) && /\s-\w*v/.test(c)) || /\bdocker\s+volume\s+rm\b/.test(c) },
  { label: 'rm -rf (hors /tmp)', test: c => rmRecursiveForceOutsideTmp(c) },
  { label: 'git push --force', test: c => /\bgit\s+push\b/.test(c) && /--force(?!-with-lease)\b|\s-f\b/.test(c) },
  { label: 'vault destroy/delete', test: c => /\bvault\b[\s\S]*(destroy|delete)\b/.test(c) },
];

let input = '';
const timer = setTimeout(() => process.exit(0), 3000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => (input += c));
process.stdin.on('end', () => {
  clearTimeout(timer);
  try {
    const data = JSON.parse(input || '{}');
    if (data.tool_name !== 'Bash') process.exit(0);
    const cmd = ((data.tool_input || {}).command || '').toString();
    if (!cmd) process.exit(0);

    const hit = HIGH.find(h => { try { return h.test(cmd); } catch (_) { return false; } });
    if (!hit) process.exit(0);

    // Ack présent → consommer et autoriser une fois.
    try { if (fs.existsSync(ACK)) { fs.unlinkSync(ACK); process.exit(0); } } catch (_) {}

    process.stderr.write(
      `[RISK-HIGH] BLOQUÉ — commande à risque élevé (irréversible) : ${hit.label}.\n\n` +
      `  ${cmd}\n\n` +
      `Si l'action est intentionnelle et vérifiée :\n` +
      `  touch /tmp/claude-highrisk-ack\n` +
      `puis relance la commande (l'ack est consommé une fois).\n` +
      `Sinon : annule / choisis une variante réversible. Règle LOI risk-tier (P4).\n`
    );
    process.exit(2);
  } catch (_) {
    process.exit(0);
  }
});
```

- [ ] **Step 4: Run — expect PASS**

```bash
node ~/.claude/hooks/test/test-risk-tier-guard.js
node -c ~/.claude/hooks/risk-tier-guard.js && echo "syntax OK"
```
If any high-risk case fails to block or any low-risk case blocks, fix the matcher (do NOT loosen the test's intent). The `rm -rf` matcher is the trickiest — confirm `/tmp`-only is exempt and non-/tmp paths block.

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/risk-tier-guard.js hooks/test/test-risk-tier-guard.js
git commit -m "feat(hooks): risk-tier-guard — HITL hard-block on high-risk Bash until ack (P4)"
```
NEVER `git add -A`. Create ONLY those two files.

---

### Task 2: `output-guard.sh` (secret/PII scan) + test

**Files:**
- Create: `~/.claude/hooks/output-guard.sh`
- Create: `~/.claude/hooks/test/test-output-guard.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-output-guard.js
'use strict';
const { runShell, ok, done } = require('./harness');
const fs = require('fs');
const FIX = '/tmp/claude-output-fixture.' + process.pid + '.jsonl';
const ACK = '/tmp/claude-output-ack';
const MDIR = '/tmp/claude-metrics.outtest.' + process.pid;
function clean() { [FIX, ACK].forEach(p => { try { fs.unlinkSync(p); } catch (_) {} }); try { fs.rmSync(MDIR, { recursive: true, force: true }); } catch (_) {} }
function asst(text) { return JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text }] } }); }
function user(t) { return JSON.stringify({ type: 'user', message: { role: 'user', content: t } }); }
function write(lines) { fs.writeFileSync(FIX, lines.join('\n') + '\n'); }
clean();

const env = { R0_SESSION_JSONL: FIX, R0_METRICS_DIR: MDIR };
const blocks = r => /"decision"\s*:\s*"block"/.test(r.stdout);

// 1. Assistant output containing a private key → alert (nudge) + logged
write([user('montre la clé'), asst('Voici : -----BEGIN OPENSSH PRIVATE KEY-----\nMIIE...\n-----END OPENSSH PRIVATE KEY-----')]);
let r = runShell('output-guard.sh', { stop_hook_active: false }, env);
ok(r.code === 0, 'always exits 0 (advisory)');
ok(blocks(r) && /SECRET/.test(r.stdout), 'private key in output → one-time advisory nudge');
ok(fs.existsSync(MDIR + '/secret-alerts.jsonl'), 'alert appended to secret-alerts.jsonl');

// 2. Token prefix (sk-..., ghp_..., AKIA...) → alert
for (const tok of ['sk-abcdefghij0123456789ABCDEFGHIJ', 'ghp_0123456789abcdefABCDEF0123456789abcd', 'AKIA0123456789ABCDEF']) {
  clean();
  write([user('go'), asst('clé = ' + tok)]);
  r = runShell('output-guard.sh', { stop_hook_active: false }, env);
  ok(blocks(r), 'token prefix flagged: ' + tok.slice(0, 6));
}

// 2b. password=/secret= with a value → alert
clean(); write([user('go'), asst('Voici le mot de passe : password=SuperSecret42')]);
r = runShell('output-guard.sh', { stop_hook_active: false }, env);
ok(blocks(r), 'password=<value> in output → alert');

// 3. Sese public IP in the assistant output → alert
clean(); write([user('go'), asst('connecte-toi à 137.74.114.167 directement')]);
r = runShell('output-guard.sh', { stop_hook_active: false }, env);
ok(blocks(r), 'Sese public IP in output → alert');

// 4. Clean output → no alert
clean(); write([user('go'), asst('Tout est déployé via Tailscale 100.64.0.14, RAS.')]);
r = runShell('output-guard.sh', { stop_hook_active: false }, env);
ok(!blocks(r), 'clean output (VPN IP, no secret) → no alert');

// 5. Re-entry → allow (non-looping)
clean(); write([user('go'), asst('-----BEGIN PRIVATE KEY-----x-----END PRIVATE KEY-----')]);
r = runShell('output-guard.sh', { stop_hook_active: true }, env);
ok(!blocks(r), 're-entry stop_hook_active=true → allow (no loop)');

// 6. Ack marker → allow + consume
clean(); write([user('go'), asst('-----BEGIN PRIVATE KEY-----x-----END PRIVATE KEY-----')]);
fs.writeFileSync(ACK, '1');
r = runShell('output-guard.sh', { stop_hook_active: false }, env);
ok(!blocks(r), 'ack → allow'); ok(!fs.existsSync(ACK), 'ack consumed');

// 7. Missing JSONL → fail-open
r = runShell('output-guard.sh', { stop_hook_active: false }, { R0_SESSION_JSONL: '/nonexistent.jsonl', R0_METRICS_DIR: MDIR });
ok(!blocks(r) && r.code === 0, 'missing JSONL → fail-open');

clean();
done();
```

- [ ] **Step 2: Run — expect FAIL**

```bash
node ~/.claude/hooks/test/test-output-guard.js
```

- [ ] **Step 3: Implement `output-guard.sh`**

```bash
#!/bin/bash
# output-guard.sh — Stop hook (P4 OUTPUT guard, SPEC §7 D4).
# Scanne la sortie ASSISTANT du tour courant pour des secrets/PII probables
# (clés privées, préfixes de tokens connus, IP publique Sese, password=/secret=).
# Sur hit : log dans ~/.claude/metrics/secret-alerts.jsonl + nudge advisory UNIQUE.
# Alerte > blocage (après-coup par nature). NON-looping (re-entry → allow),
# escape /tmp/claude-output-ack. Fail-open : erreur → exit 0.
set -uo pipefail

INPUT=$(cat 2>/dev/null || true)
ACTIVE=$(printf '%s' "$INPUT" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("stop_hook_active", False))
except Exception: print(False)' 2>/dev/null || echo False)
[ "$ACTIVE" = "True" ] && exit 0
if [ -f /tmp/claude-output-ack ]; then rm -f /tmp/claude-output-ack; exit 0; fi

SESSION_JSONL="${R0_SESSION_JSONL:-$(ls -t "$HOME/.claude/projects/"*"/"*.jsonl 2>/dev/null | head -1)}"
[ -f "$SESSION_JSONL" ] || exit 0
METRICS_DIR="${R0_METRICS_DIR:-$HOME/.claude/metrics}"

# Tour courant (même technique que verify-stop-gate : reset sur vrai message user).
TURN=$(tail -n 600 "$SESSION_JSONL" 2>/dev/null | awk '
  /"type":"user"/ && !/tool_result/ { buf=""; next }
  { buf = buf $0 "\n" }
  END { printf "%s", buf }' || true)
[ -z "$TURN" ] && exit 0

# Patterns secrets/PII. Conservateur pour limiter le bruit.
SECRET_PAT='-----BEGIN [A-Z ]*PRIVATE KEY-----|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|137\.74\.114\.167|(password|passwd|secret|api[_-]?key|token)["'"'"' ]*[:=]["'"'"' ]*[A-Za-z0-9/_+.-]{8,}'

HIT=$(printf '%s' "$TURN" | grep -iEo -e "$SECRET_PAT" 2>/dev/null | head -1 || true)  # -e obligatoire : $SECRET_PAT commence par ----- (sinon pris pour des options)
[ -z "$HIT" ] && exit 0

# Log (jamais le secret en clair : on logge le TYPE + un hash court).
KIND=$(printf '%s' "$HIT" | sed -E 's/[A-Za-z0-9/_+.-]{6,}/<redacted>/g' | head -c 60)
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
mkdir -p "$METRICS_DIR" 2>/dev/null || true
printf '{"ts":"%s","kind":"secret-in-output","pattern":"%s"}\n' "$TS" "$KIND" >> "$METRICS_DIR/secret-alerts.jsonl" 2>/dev/null || true

cat << 'MSG'
{"decision":"block","reason":"[SECRET] Ta réponse contient un motif ressemblant à un secret/PII (clé privée, token, IP publique, password=/secret=). Vérifie : si un secret réel a été exposé en sortie, ROTATE-le et évite de le réafficher. Si c'est un faux positif (exemple, placeholder), crée /tmp/claude-output-ack puis arrête-toi (nudge unique, ne boucle pas). cf règle Secrets / OUTPUT guard P4."}
MSG
exit 0
```

- [ ] **Step 4: Run — expect PASS + syntax**

```bash
node ~/.claude/hooks/test/test-output-guard.js
chmod +x ~/.claude/hooks/output-guard.sh
bash -n ~/.claude/hooks/output-guard.sh && echo "syntax OK"
```

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/output-guard.sh hooks/test/test-output-guard.js
git commit -m "feat(hooks): output-guard — scan turn output for secrets/PII, log + advisory (P4)"
```
NEVER `git add -A`. Create ONLY those two files.

---

### Task 3: Wire both in settings.json + regression

**Files:**
- Modify: `~/.claude/settings.json` (PreToolUse `Bash` matcher gets risk-tier; `Stop` array gets output-guard)

- [ ] **Step 1: Backup + validate JSON**

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8"));console.log("valid")'
```

- [ ] **Step 2: Add risk-tier to PreToolUse** as a NEW `Bash` matcher entry (same shape as existing PreToolUse entries):

```json
{
  "matcher": "Bash",
  "hooks": [
    { "type": "command", "command": "node /home/mobuone/.claude/hooks/risk-tier-guard.js", "timeout": 5 }
  ]
}
```

- [ ] **Step 3: Add output-guard to the `Stop` array** (no matcher):

```json
{
  "hooks": [
    { "type": "command", "command": "bash /home/mobuone/.claude/hooks/output-guard.sh" }
  ]
}
```

- [ ] **Step 4: Validate edited JSON** (restore from `.bak` if it throws).

```bash
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8"));console.log("valid")'
```

- [ ] **Step 5: Full regression + targeted live smoke**

```bash
bash ~/.claude/hooks/test/run-all.sh
# Smoke risk-tier (direct hook call — does NOT execute the command, just tests the gate):
echo '{"tool_name":"Bash","tool_input":{"command":"make deploy-prod"}}' | node ~/.claude/hooks/risk-tier-guard.js; echo "exit=$?"   # expect [RISK-HIGH] + exit 2
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' | node ~/.claude/hooks/risk-tier-guard.js; echo "exit=$?"           # expect exit 0
```
Expected: `ALL TESTS PASS`; the deploy-prod smoke prints `[RISK-HIGH]` + `exit=2`; `ls -la` → `exit=0`.

> NB: after wiring, the risk-tier gate is LIVE for this session's Bash calls. It will block a real `make deploy-prod`/`rm -rf <non-tmp>`/etc. until `touch /tmp/claude-highrisk-ack`. This is intended.

- [ ] **Step 6: Commit + remove backup**

```bash
cd /home/mobuone/.claude
rm -f settings.json.bak
git add settings.json
git commit -m "feat(hooks): wire risk-tier-guard (PreToolUse Bash) + output-guard (Stop) — P4 live"
```

---

## P4 Done-Definition
- [ ] `node hooks/test/test-risk-tier-guard.js` green (each high-risk blocks; ack allows+consumes; low-risk & /tmp-rm & --force-with-lease & Write-mention never block; fail-open).
- [ ] `node hooks/test/test-output-guard.js` green (key/token/IP/password → alert+log; clean → none; re-entry/ack/missing → allow).
- [ ] `bash hooks/test/run-all.sh` → ALL TESTS PASS.
- [ ] Both wired; smoke confirms deploy-prod blocks, ls allowed.

## Out of scope / deferred
- MCP-side mutations (e.g. `mcp__postgres__pg_execute_mutation`) — risk-tier here is Bash-only; MCP mutation gating is a possible extension (MCP calls are already explicit).
- Pre-output secret interception (true redaction before the user sees it) — OUTPUT guard is Stop-time (after-the-fact alert) by design.
- Tuning matchers/patterns from observed false-positive rate (revisit via the metrics ledger).
- Backlog (from P1 review): R7 read-vs-connect precision; automated G4 cross-repo-label test.
