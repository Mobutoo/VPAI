# LOI Système de Briques — P3 (VERIFY) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the `verification-before-completion` discipline — when the assistant's last response claims completion (`corrigé`/`déployé`/`✅`/`tests passent`…) but no verification command (test/lint/validate/curl/run-all) appears in the recent turn, emit a ONE-TIME advisory nudge "preuve avant done".

**Architecture:** A NEW Stop hook `verify-stop-gate.sh` (separate from the GSD-oriented `stop-gate.sh`, which stays untouched). On stop, it reads the current session JSONL, inspects the recent tail for (a) a strong completion claim in the last assistant output and (b) the absence of any verification-command tool_use in that turn. If claim ∧ ¬verification, it returns `{"decision":"block","reason":...}` — but is **non-looping**: the `stop_hook_active` re-entry guard makes it fire at most once per stop attempt, and a `/tmp/claude-verify-ack` escape-hatch lets the model acknowledge and stop. This is the advisory tier (a single nudge that the model can immediately clear); hardening (require a real verification marker before the second stop) is deferred. Fail-open: any error → exit 0 (allow stop).

**Tech Stack:** Bash (`set -uo pipefail`), `python3` for stdin JSON field extraction (mirrors `stop-gate.sh`), grep over the session `.jsonl` tail. Test = `hooks/test/harness.js` `runShell` + fixture JSONL + `R0_SESSION_JSONL` seam + `stop_hook_active` stdin.

**Spec:** `docs/superpowers/specs/2026-06-04-loi-system-bricks-design.md` §7 D3 + §8 (verify-stop-gate, P3). Extends P1/P2.

---

## Current substrate (verified 2026-06-04)
- `~/.claude/hooks/stop-gate.sh` (Stop hook): GSD-only (`.planning` gate), reads stdin `stop_hook_active`+`cwd`, blocks on STATE.md `in.progress` via `{"decision":"block","reason":...}`, escape `/tmp/claude-task-complete`. **Leave untouched** — P3 is a separate concern.
- `settings.json` `Stop` array (post-P2): `stop-gate.sh`, `session-memory-writer.sh`, `metrics-aggregator.sh`.
- Session JSONL discoverable via `ls -t ~/.claude/projects/*/*.jsonl | head -1` (same as the P2 hook).
- In the JSONL, assistant text lives in escaped JSON; tool calls appear as `"name":"Bash"` / `"name":"mcp__..."`. The `✅` emoji may be unicode-escaped (`✅`).

## File Structure
| Path | Responsibility |
|---|---|
| `~/.claude/hooks/verify-stop-gate.sh` | NEW. One-time advisory nudge on completion-claim-without-verification. Non-looping, fail-open. |
| `~/.claude/hooks/test/test-verify-stop-gate.js` | NEW. Fixture-JSONL + stdin-driven test. |
| `~/.claude/settings.json` | Modify. Add to `Stop` array. |

## Conventions
- Fail-open: `set -uo pipefail`, `|| true` guards, exit 0 on every error path (allowing the stop).
- Non-looping invariant: MUST exit 0 when stdin `stop_hook_active` is true. A test asserts this.
- Test isolation: `R0_SESSION_JSONL=<fixture>`; the ack-marker test uses `/tmp/claude-verify-ack` and cleans it.
- Conservative trigger: only STRONG completion claims fire; lenient verification detection (any test/lint/validate/curl/run-all/MCP in the tail suppresses). Errs toward NOT nagging.

---

### Task 1: `verify-stop-gate.sh` + test

**Files:**
- Create: `~/.claude/hooks/verify-stop-gate.sh`
- Create: `~/.claude/hooks/test/test-verify-stop-gate.js`

- [ ] **Step 1: Write the failing test**

```javascript
// ~/.claude/hooks/test/test-verify-stop-gate.js
'use strict';
const { runShell, ok, done } = require('./harness');
const fs = require('fs');
const FIX = '/tmp/claude-verify-fixture.' + process.pid + '.jsonl';
const ACK = '/tmp/claude-verify-ack';
function clean() { try { fs.unlinkSync(FIX); } catch (_) {} try { fs.unlinkSync(ACK); } catch (_) {} }
// REALISTIC nested JSONL shapes (match the live transcript format).
function asst(text) { return JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text }] } }); }
function tool(name, cmd) { return JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name, input: { command: cmd || '' } }] } }); }
function user(text) { return JSON.stringify({ type: 'user', message: { role: 'user', content: text } }); }
function toolResult() { return JSON.stringify({ type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 'x', content: 'ok' }] } }); }
function write(lines) { fs.writeFileSync(FIX, lines.join('\n') + '\n'); }
clean();

const env = { R0_SESSION_JSONL: FIX };
const blocks = r => /"decision"\s*:\s*"block"/.test(r.stdout);

// 1. Claim + NO verification in the current turn → one-time advisory block
write([user('fais le déploiement'), tool('Edit'), asst('Voilà, le rôle caddy est déployé et corrigé.')]);
let r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(r.code === 0, 'always exits 0 (advisory, never hard-fails)');
ok(blocks(r) && /VERIFY/.test(r.stdout), 'claim without verification → one-time advisory block');

// 1b. ✅ alone as the completion signal (no other keyword) → block (I1 regression)
write([user('go'), tool('Edit'), asst('✅ Done.')]);
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(blocks(r), '✅ alone is a completion claim → nudge (literal UTF-8, not \\u2705)');

// 2. Claim + a verification command IN THE SAME turn → NO nudge
write([user('vérifie et déploie'), tool('Bash', 'bash hooks/test/run-all.sh'), toolResult(), asst('Tout est déployé, tests passent ✅.')]);
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(!blocks(r), 'claim WITH a verification command in-turn → no nudge');

// 3. No completion claim → no nudge
write([user('analyse ça'), asst("Je continue l'analyse, plusieurs points restent ouverts.")]);
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(!blocks(r), 'no completion claim → no nudge');

// 4. Re-entry (stop_hook_active=true) → always allow (non-looping invariant)
write([user('go'), tool('Edit'), asst('déployé et corrigé')]);
r = runShell('verify-stop-gate.sh', { stop_hook_active: true }, env);
ok(!blocks(r) && r.code === 0, 're-entry stop_hook_active=true → allow (no loop)');

// 5. Ack marker present → allow + consume marker
write([user('go'), tool('Edit'), asst('déployé et corrigé')]);
fs.writeFileSync(ACK, '1');
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(!blocks(r), 'ack marker → allow stop');
ok(!fs.existsSync(ACK), 'ack marker consumed (removed)');

// 6. Missing JSONL → fail-open allow
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, { R0_SESSION_JSONL: '/nonexistent.jsonl' });
ok(!blocks(r) && r.code === 0, 'missing JSONL → fail-open allow');

// 7. TURN-SCOPING (I2): an MCP qdrant search in a PRIOR turn must NOT suppress.
//    Last genuine user message starts a fresh turn with only an Edit + claim.
write([tool('mcp__qdrant__qdrant-find'), user('maintenant corrige'), tool('Edit'), asst('corrigé')]);
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(blocks(r), 'qdrant search in a PRIOR turn does not suppress (turn-scoped) → nudge');

// 8. A bare qdrant search IN-turn is NOT a verification (memory search ≠ proof) → still nudge
write([user('go'), tool('mcp__qdrant__qdrant-find'), tool('Edit'), asst('déployé')]);
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(blocks(r), 'bare qdrant-find in-turn is not verification → still nudge');

// 9. A real validation MCP in-turn suppresses
write([user('go'), tool('mcp__n8n-docs__validate_workflow'), asst('workflow déployé')]);
r = runShell('verify-stop-gate.sh', { stop_hook_active: false }, env);
ok(!blocks(r), 'validate_workflow in-turn → verification present → no nudge');

clean();
done();
```

- [ ] **Step 2: Run — expect FAIL**

```bash
node ~/.claude/hooks/test/test-verify-stop-gate.js
```

- [ ] **Step 3: Implement `verify-stop-gate.sh`**

```bash
#!/bin/bash
# verify-stop-gate.sh — Stop hook (P3 VERIFY, SPEC §7 D3).
# Nudge advisory UNIQUE : si la dernière réponse du TOUR COURANT annonce une
# complétion sans trace de commande de vérification DANS CE TOUR → rappelle
# "preuve avant done" (pattern verification-before-completion). NON-BLOQUANT
# durablement :
#   - re-entry (stop_hook_active=true) → allow (jamais de boucle)
#   - escape /tmp/claude-verify-ack → allow (le modèle acquitte)
# Tier advisory ; durcissement (exiger un marker de vérif réel) = différé.
# Fail-open : toute erreur → exit 0 (autorise le stop). stop-gate.sh (GSD) intouché.
set -uo pipefail

INPUT=$(cat 2>/dev/null || true)

# Re-entry guard — fire au plus une fois par tentative de stop.
ACTIVE=$(printf '%s' "$INPUT" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("stop_hook_active", False))
except Exception: print(False)' 2>/dev/null || echo False)
[ "$ACTIVE" = "True" ] && exit 0

# Escape-hatch : le modèle a acquitté → laisser passer (consommer le marker).
if [ -f /tmp/claude-verify-ack ]; then rm -f /tmp/claude-verify-ack; exit 0; fi

SESSION_JSONL="${R0_SESSION_JSONL:-$(ls -t "$HOME/.claude/projects/"*"/"*.jsonl 2>/dev/null | head -1)}"
[ -f "$SESSION_JSONL" ] || exit 0

# Scope au TOUR COURANT : lignes après le dernier VRAI message user.
# Piège : les tool_result sont aussi "type":"user" — ne PAS reset dessus.
# On ne reset le buffer que sur un message user SANS tool_result (= vrai début de tour).
TURN=$(tail -n 600 "$SESSION_JSONL" 2>/dev/null | awk '
  /"type":"user"/ && !/tool_result/ { buf=""; next }
  { buf = buf $0 "\n" }
  END { printf "%s", buf }' || true)
[ -z "$TURN" ] && exit 0

# (a) Claim de complétion FORT dans le tour ? (✅ = UTF-8 littéral, pas \uXXXX)
CLAIM_PAT='déploy[ée]|corrig[ée]|résolu|shipp[ée]|terminé|tests? (passent|verts|ok)|ça marche|all tests pass|✅'
printf '%s' "$TURN" | grep -iE "$CLAIM_PAT" >/dev/null 2>&1 || exit 0

# (b) Trace de vérification DANS LE TOUR ? Vraie vérif seulement — un simple
# qdrant-find (recherche mémoire) ne compte PAS comme preuve.
VERIF_PAT='"name":"Bash"[^}]*(test|lint|validate|pytest|npm( run)? test|make |curl|bash -n|run-all|diff)|validate_workflow|"name":"mcp__playwright__|"name":"mcp__n8n-docs__(validate|n8n_validate)'
printf '%s' "$TURN" | grep -iE "$VERIF_PAT" >/dev/null 2>&1 && exit 0

# Claim sans vérification dans le tour → nudge advisory unique (non-looping).
cat << 'MSG'
{"decision":"block","reason":"[VERIFY] Tu sembles annoncer une complétion (déployé/corrigé/résolu/tests passent/✅) sans trace de commande de vérification dans ce tour (test/lint/validate/curl/run-all/bash -n). Preuve avant done (pattern verification-before-completion) : lance la vérif et cite sa sortie. Si c'est déjà vérifié ou non applicable, crée /tmp/claude-verify-ack puis arrête-toi (nudge unique, ne boucle pas)."}
MSG
exit 0
```

- [ ] **Step 4: Run — expect PASS + syntax**

```bash
node ~/.claude/hooks/test/test-verify-stop-gate.js
chmod +x ~/.claude/hooks/verify-stop-gate.sh
bash -n ~/.claude/hooks/verify-stop-gate.sh && echo "syntax OK"
```

- [ ] **Step 5: Commit (`~/.claude`)**

```bash
cd /home/mobuone/.claude
git add hooks/verify-stop-gate.sh hooks/test/test-verify-stop-gate.js
git commit -m "feat(hooks): verify-stop-gate — one-time advisory nudge, proof-before-done (P3 VERIFY)"
```
NEVER `git add -A`. Stage ONLY those two files.

---

### Task 2: Wire in settings.json + regression

**Files:**
- Modify: `~/.claude/settings.json` (`Stop` array)

- [ ] **Step 1: Backup + validate JSON**

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8"));console.log("valid")'
```

- [ ] **Step 2: Add a new element to the `Stop` array** (no `matcher`, same shape as existing Stop entries):

```json
{
  "hooks": [
    { "type": "command", "command": "bash /home/mobuone/.claude/hooks/verify-stop-gate.sh" }
  ]
}
```

- [ ] **Step 3: Validate edited JSON** (restore from `.bak` if it throws).

```bash
node -e 'JSON.parse(require("fs").readFileSync(process.env.HOME+"/.claude/settings.json","utf8"));console.log("valid")'
```

- [ ] **Step 4: Full regression**

```bash
bash ~/.claude/hooks/test/run-all.sh
```
Expected: `ALL TESTS PASS`.

> No live smoke that triggers the block (it would nudge this very session). The unit tests cover behavior; ordering with `stop-gate.sh` is independent (both read their own inputs).

- [ ] **Step 5: Commit + remove backup**

```bash
cd /home/mobuone/.claude
rm -f settings.json.bak
git add settings.json
git commit -m "feat(hooks): wire verify-stop-gate into Stop (P3 VERIFY live, advisory)"
```

---

## P3 Done-Definition
- [ ] `node hooks/test/test-verify-stop-gate.js` green (claim-without-verif → block; claim+verif → allow; no-claim → allow; re-entry → allow; ack → allow+consume; missing JSONL → fail-open).
- [ ] Non-looping invariant proven (re-entry test).
- [ ] `bash hooks/test/run-all.sh` → ALL TESTS PASS.
- [ ] Wired in `Stop`; `stop-gate.sh` untouched.

## Out of scope / deferred
- Hardening to a real gate (require an actual verification marker written by a PostToolUse on test/validate before allowing the 2nd stop). Advisory-first per spec — measure adoption via P2's ledger before hardening.
- Tuning the claim/verification regexes from observed false-positive rate (revisit after a few sessions).
- P4 (risk-tier + OUTPUT guard).
