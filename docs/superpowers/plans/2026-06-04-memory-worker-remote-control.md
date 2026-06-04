# Memory-Worker Remote Control — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pilot the memory-worker from an iPhone via a Telegram bot (`/mem_status /mem_start /mem_stop /mem_run /mem_fix`), backed by a single `memctl` action surface, with the worker + bot running as sudo-free systemd-user units; harden `index.py` against stale locks.

**Architecture:** A static, env-driven `memctl.sh` (action library) + a static, stdlib-only `memory-bot.py` (Telegram long-poll front, chat-id auth) are deployed by the existing Ansible role `roles/llamaindex-memory-worker/`. The worker `service`/`timer` and a new `memory-bot.service` migrate from system units (root) to **user units** under `~mobuone/.config/systemd/user/` with linger enabled — so everything is controllable as `mobuone` without sudo. `index.py`'s lock gains PID validation (stale lock → auto-clear).

**Tech Stack:** Bash (`memctl`, `set -euo pipefail`), Python 3.12 stdlib only (`memory-bot.py` — `urllib`, no new pip dep), systemd-user + linger, Ansible (FQCN, idempotent), Telegram Bot API (outbound HTTPS), Qdrant REST (status).

**Spec:** `docs/superpowers/specs/2026-06-04-memory-worker-remote-control-design.md`.

---

## Grounding facts (verified 2026-06-04)
- Role: `roles/llamaindex-memory-worker/` — `defaults/main.yml`, `tasks/main.yml`, `handlers/main.yml`, `templates/*.j2`. Deploys SYSTEM units to `/etc/systemd/system/` (`become: true`).
- `memory_worker_user` = `mobuone` (uid **1000**); dirs under `/opt/workstation/{ai-memory-worker,configs,data}` owned by mobuone. Linger currently **off**.
- Worker service: `Type=oneshot`, `User=`/`Group={{ memory_worker_user }}`, `ExecStartPre=memory-wait-calm.sh`, `ExecStart=run-and-report.sh --mode incremental`, `Nice=19`, `WantedBy=multi-user.target`. Timer: `OnBootSec=5m`, `OnUnitActiveSec=30m`, `WantedBy=timers.target`.
- `index.py.j2`: `ensure_lock()` lines 108-114, `release_lock()` 117-121, `lock_path = state_dir/"index.lock"` (line 788). NO PID validation today.
- `memory-worker.env.j2`: HF + Qdrant + reporting vars. **No Telegram keys.**
- Inventory secrets pattern: `inventory/group_vars/all/main.yml` exposes `x: "{{ vault_x | default('') }}"`; vault in `inventory/group_vars/all/secrets.yml`. Existing Telegram vars exist (`telegram_monitoring_bot_token`, …) — the owner may reuse one.

---

## File Structure
| Path | New/Mod | Responsibility |
|---|---|---|
| `roles/llamaindex-memory-worker/files/memctl.sh` | NEW (static) | Action library `status\|start\|stop\|run\|fix`. Env-driven, sudo-free, sets `XDG_RUNTIME_DIR` defensively. |
| `roles/llamaindex-memory-worker/files/memory-bot.py` | NEW (static) | Telegram long-poll, chat-id auth, dispatch → `memctl`, reply. stdlib only. |
| `roles/llamaindex-memory-worker/tests/test_memctl.sh` | NEW | memctl behavior (status offline, fix PID-dead vs alive). |
| `roles/llamaindex-memory-worker/tests/test_memory_bot.py` | NEW | dispatch + auth + status formatting (mock Telegram + memctl). |
| `roles/llamaindex-memory-worker/tests/test_lock.py` | NEW | ensure_lock PID-stale behavior. |
| `roles/llamaindex-memory-worker/templates/memory-worker.service.user.j2` | NEW | User-unit variant (no User=/Group=, `WantedBy=default.target`). |
| `roles/llamaindex-memory-worker/templates/memory-worker.timer.user.j2` | NEW | User timer (`WantedBy=timers.target`). |
| `roles/llamaindex-memory-worker/templates/memory-bot.service.user.j2` | NEW | Bot user service (`Restart=always`, `WantedBy=default.target`). |
| `roles/llamaindex-memory-worker/templates/index.py.j2` | MOD | Harden `ensure_lock()` (PID validation). |
| `roles/llamaindex-memory-worker/templates/memory-worker.env.j2` | MOD | Add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_CHAT_ID`. |
| `roles/llamaindex-memory-worker/defaults/main.yml` | MOD | New vars (telegram token/chat, bot service name, user-unit dir, uid). |
| `roles/llamaindex-memory-worker/tasks/main.yml` | MOD | Uninstall system units; deploy scripts+user units; linger; `systemctl --user` enable. |
| `roles/llamaindex-memory-worker/handlers/main.yml` | MOD | User-scoped reload/restart handlers. |
| `inventory/group_vars/all/main.yml` | MOD | `memory_worker_telegram_*` mapped to `vault_*`. |
| `inventory/group_vars/all/secrets.yml` | MOD (vault) | `vault_memory_worker_telegram_bot_token`, `vault_memory_worker_telegram_owner_chat_id`. **Human via `ansible-vault edit`.** |

## Conventions
- Scripts read ALL config from ENV (paths, token, chat-id, qdrant) → unit-testable with env seams, deployed via `ansible.builtin.copy`. No Jinja in them.
- Ansible: FQCN, explicit `changed_when`/`failed_when`, `set -euo pipefail`+`executable: /bin/bash` on shell, idempotent (0 changed on 2nd run), tags `[llamaindex-memory-worker, phase?]`.
- `systemctl --user` tasks: `become: true` + `become_user: "{{ memory_worker_user }}"` + `environment: { XDG_RUNTIME_DIR: "/run/user/{{ memory_worker_uid }}" }`.
- Tests run locally on waza: bash/python directly against the static files. Runner: `bash roles/llamaindex-memory-worker/tests/run.sh`.

---

### Task 1: Harden `index.py` lock (PID validation)

**Files:** Modify `roles/llamaindex-memory-worker/templates/index.py.j2:108-114`; Create `roles/llamaindex-memory-worker/tests/test_lock.py`

- [ ] **Step 1: Write the failing test** (copies the target functions inline — they contain no Jinja, so they render identically)

```python
# roles/llamaindex-memory-worker/tests/test_lock.py
import os, tempfile, subprocess, sys
from pathlib import Path

# Mirror of the HARDENED ensure_lock/release_lock (must match index.py.j2 after Task 1).
def ensure_lock(lock_path: Path) -> None:
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            pid = int(lock_path.read_text().strip() or "0")
        except Exception:
            pid = 0
        alive = False
        if pid > 0:
            try:
                os.kill(pid, 0); alive = True
            except ProcessLookupError:
                alive = False
            except PermissionError:
                alive = True
        if alive:
            raise RuntimeError(f"lock held by live pid {pid}: {lock_path}") from exc
        lock_path.unlink(missing_ok=True)  # stale → reclaim
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))

def test_stale_lock_reclaimed():
    d = Path(tempfile.mkdtemp()); lp = d / "index.lock"
    lp.write_text("999999")  # almost-certainly-dead PID
    ensure_lock(lp)  # must NOT raise
    assert lp.read_text() == str(os.getpid())
    print("ok: stale lock reclaimed")

def test_live_lock_blocks():
    d = Path(tempfile.mkdtemp()); lp = d / "index.lock"
    lp.write_text(str(os.getpid()))  # our own (live) pid
    try:
        ensure_lock(lp); print("FAIL: live lock not blocked"); sys.exit(1)
    except RuntimeError:
        print("ok: live lock blocks")

if __name__ == "__main__":
    test_stale_lock_reclaimed(); test_live_lock_blocks(); print("ALL OK")
```

- [ ] **Step 2: Run → FAIL** (the test mirror is hardened but `index.py.j2` isn't yet — this test validates the LOGIC we'll paste; run to confirm the logic itself is sound)

```bash
python3 roles/llamaindex-memory-worker/tests/test_lock.py
```
Expected: `ALL OK` (the test's own mirror is correct). This test is the spec for Step 3.

- [ ] **Step 3: Apply the SAME hardened `ensure_lock` to `index.py.j2`** — replace lines 108-114 with the `ensure_lock` body from the test (verbatim, minus the test scaffolding). Leave `release_lock` (117-121) unchanged. Add a log line on stale reclaim if a logger is in scope.
  - **ALSO** guard the `main()` call sites (~804 `ensure_lock`, ~956 `finally: release_lock`) with an `acquired` flag, so a second instance that correctly refuses a LIVE lock does not delete the first instance's lock in its `finally`:
    ```python
    acquired = False
    try:
        ensure_lock(lock_path)
        acquired = True
        ...                      # existing body
    finally:
        if acquired:
            release_lock(lock_path)
    ```
    Without this, the live-lock detection is undermined by the unconditional `finally`.

- [ ] **Step 4: Verify the template still parses as Python after render** — render check:

```bash
python3 -c "import re,sys; s=open('roles/llamaindex-memory-worker/templates/index.py.j2').read(); s=re.sub(r'{{.*?}}','PLACEHOLDER',s); compile(s,'index.py','exec'); print('renders to valid python')"
```
Expected: `renders to valid python`.

- [ ] **Step 5: Commit**

```bash
cd /home/mobuone/VPAI
git add roles/llamaindex-memory-worker/templates/index.py.j2 roles/llamaindex-memory-worker/tests/test_lock.py
git commit -m "fix(memory-worker): PID-validated lock — stale lock auto-reclaims (root cause of 6-week dormancy)"
```

---

### Task 2: Provision Telegram secrets (Vault + vars + env template)

**Files:** Modify `inventory/group_vars/all/main.yml`, `roles/llamaindex-memory-worker/defaults/main.yml`, `roles/llamaindex-memory-worker/templates/memory-worker.env.j2`; Vault: `inventory/group_vars/all/secrets.yml`

- [ ] **Step 1: Add the vault-mapped vars** to `inventory/group_vars/all/main.yml` (near the existing `telegram_*` block):

```yaml
memory_worker_telegram_bot_token: "{{ vault_memory_worker_telegram_bot_token | default('') }}"
memory_worker_telegram_owner_chat_id: "{{ vault_memory_worker_telegram_owner_chat_id | default('') }}"
```

- [ ] **Step 2: Expose in role defaults** — add to `roles/llamaindex-memory-worker/defaults/main.yml`:

```yaml
# Telegram remote control
memory_worker_telegram_bot_token: "{{ memory_worker_telegram_bot_token | default('') }}"
memory_worker_telegram_owner_chat_id: "{{ memory_worker_telegram_owner_chat_id | default('') }}"
memory_worker_bot_service_name: "memory-bot"
memory_worker_user_unit_dir: "/home/{{ memory_worker_user }}/.config/systemd/user"
memory_worker_uid: 1000  # uid of memory_worker_user (mobuone) — used for XDG_RUNTIME_DIR
```

> If `memory_worker_uid` should not be hardcoded, derive it in tasks via `ansible.builtin.getent` (database: passwd, key: "{{ memory_worker_user }}") and use `getent_passwd[memory_worker_user][1]`. Hardcoding 1000 is acceptable for this single host; note the alternative.

- [ ] **Step 3: Add Telegram lines to `memory-worker.env.j2`** (after the reporting block):

```bash
# Telegram remote control (memory-bot)
TELEGRAM_BOT_TOKEN={{ memory_worker_telegram_bot_token }}
TELEGRAM_OWNER_CHAT_ID={{ memory_worker_telegram_owner_chat_id }}
```

- [ ] **Step 4: Add the vault secrets (HUMAN step)** — the executor must NOT invent secret values. Surface this command for the user to run via `!`:

```bash
ansible-vault edit inventory/group_vars/all/secrets.yml
# add:
#   vault_memory_worker_telegram_bot_token: "<token from @BotFather, or reuse monitoring bot>"
#   vault_memory_worker_telegram_owner_chat_id: "<your Telegram numeric chat id>"
```
Verify presence (without printing values):
```bash
ansible-vault view inventory/group_vars/all/secrets.yml | grep -c vault_memory_worker_telegram
```
Expected: `2`. (REX-62: `vault_*` must exist before deploy.)

- [ ] **Step 5: Commit** (only the non-secret files; secrets.yml committed by the human after edit)

```bash
git add inventory/group_vars/all/main.yml roles/llamaindex-memory-worker/defaults/main.yml roles/llamaindex-memory-worker/templates/memory-worker.env.j2
git commit -m "feat(memory-worker): wire Telegram bot token + owner chat-id (vault-backed)"
```

---

### Task 3: `memctl.sh` — action library + test

**Files:** Create `roles/llamaindex-memory-worker/files/memctl.sh`, `roles/llamaindex-memory-worker/tests/test_memctl.sh`, `roles/llamaindex-memory-worker/tests/run.sh`

- [ ] **Step 1: Write the failing test**

```bash
# roles/llamaindex-memory-worker/tests/test_memctl.sh
#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; MEMCTL="$HERE/../files/memctl.sh"
TMP="$(mktemp -d)"; export MEMCTL_STATE_DIR="$TMP/state" MEMCTL_SPOOL_DIR="$TMP/spool" MEMCTL_LOG="$TMP/w.log"
export MEMCTL_QDRANT_URL="http://127.0.0.1:1"  # unreachable on purpose
mkdir -p "$MEMCTL_STATE_DIR" "$MEMCTL_SPOOL_DIR"; echo '{}' > "$MEMCTL_STATE_DIR/memory_state.json"; : > "$MEMCTL_LOG"
fail=0; ok(){ [ "$1" = 1 ] && echo "  ok: $2" || { echo "  FAIL: $2"; fail=1; }; }

# status offline → valid JSON, qdrant_reachable false, exit 0
OUT="$(MEMCTL_TIMER_NAME=nonexistent bash "$MEMCTL" status 2>/dev/null)"; rc=$?
ok "$([ $rc -eq 0 ] && echo 1)" "status exits 0 even offline"
echo "$OUT" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["qdrant_reachable"] in (False,True); assert "spool_depth" in d' && ok 1 "status emits valid JSON with expected keys" || ok 0 "status JSON"

# REGRESSION: a DISABLED timer (is-enabled prints "disabled" + exits 1) must NOT break JSON.
FAKEBIN="$TMP/bin"; mkdir -p "$FAKEBIN"
printf '#!/bin/bash\n[ "$1" = "--user" ] && shift\ncase "$1" in is-enabled) echo disabled; exit 1;; is-active) echo inactive; exit 3;; esac\nexit 0\n' > "$FAKEBIN/systemctl"
chmod +x "$FAKEBIN/systemctl"
OUT="$(PATH="$FAKEBIN:$PATH" MEMCTL_TIMER_NAME=foo.timer bash "$MEMCTL" status 2>/dev/null)"
echo "$OUT" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["timer_enabled"]=="disabled" and d["timer_active"]=="inactive"' && ok 1 "disabled timer → valid JSON, single-line values" || ok 0 "disabled-timer JSON (multiline bug?)"

# fix: dead-PID lock → removed
echo 999999 > "$MEMCTL_STATE_DIR/index.lock"
bash "$MEMCTL" fix >/dev/null 2>&1
ok "$([ ! -f "$MEMCTL_STATE_DIR/index.lock" ] && echo 1)" "fix removes a dead-PID lock"

# fix: live-PID lock → preserved
echo $$ > "$MEMCTL_STATE_DIR/index.lock"
bash "$MEMCTL" fix >/dev/null 2>&1
ok "$([ -f "$MEMCTL_STATE_DIR/index.lock" ] && echo 1)" "fix preserves a live-PID lock"
rm -f "$MEMCTL_STATE_DIR/index.lock"

rm -rf "$TMP"; [ "$fail" = 0 ] && echo "test_memctl PASS" || { echo "test_memctl FAIL"; exit 1; }
```

Also create the runner:
```bash
# roles/llamaindex-memory-worker/tests/run.sh
#!/bin/bash
set -uo pipefail; cd "$(dirname "$0")"; f=0
bash test_memctl.sh || f=1
python3 test_memory_bot.py || f=1
python3 test_lock.py || f=1
[ "$f" = 0 ] && echo "ALL ROLE TESTS PASS" || { echo "ROLE TESTS FAILED"; exit 1; }
```

- [ ] **Step 2: Run → FAIL** (`memctl.sh` not found)

```bash
bash roles/llamaindex-memory-worker/tests/test_memctl.sh
```

- [ ] **Step 3: Implement `roles/llamaindex-memory-worker/files/memctl.sh`**

```bash
#!/bin/bash
# memctl.sh — memory-worker action surface (status|start|stop|run|fix).
# Env-driven, sudo-free, idempotent. Used by memory-bot.py, by the user in CLI,
# and by Claude. All actions local to waza; systemctl is --user.
set -uo pipefail

STATE_DIR="${MEMCTL_STATE_DIR:-/opt/workstation/data/ai-memory-worker/state}"
SPOOL_DIR="${MEMCTL_SPOOL_DIR:-/opt/workstation/data/ai-memory-worker/spool}"
LOG="${MEMCTL_LOG:-/opt/workstation/data/ai-memory-worker/logs/memory-worker.log}"
TIMER="${MEMCTL_TIMER_NAME:-llamaindex-memory-worker.timer}"
SERVICE="${MEMCTL_SERVICE_NAME:-llamaindex-memory-worker.service}"
QURL="${MEMCTL_QDRANT_URL:-${QDRANT_URL:-}}"
QKEY="${QDRANT_API_KEY:-}"
COLL="${MEMCTL_COLLECTION:-memory_v1}"
LOCK="$STATE_DIR/index.lock"
# systemctl --user needs a bus address even when invoked outside a user session.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

_uctl() { systemctl --user "$@" 2>/dev/null; }

_lock_pid() { [ -f "$LOCK" ] && cat "$LOCK" 2>/dev/null || echo ""; }
_pid_alive() { local p="$1"; [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }

cmd_status() {
  local last_line age last_ts spool lp alive state_n qpts qok ten tac
  last_line="$(tail -1 "$LOG" 2>/dev/null || true)"
  last_ts="$(printf '%s' "$last_line" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]{8}' | head -1 || true)"
  if [ -n "$last_ts" ]; then age=$(( $(date +%s) - $(date -d "$last_ts" +%s 2>/dev/null || echo 0) )); else age=-1; fi
  spool="$(ls "$SPOOL_DIR" 2>/dev/null | wc -l | tr -d ' ')"
  lp="$(_lock_pid)"; if _pid_alive "$lp"; then alive=true; else alive=false; fi
  state_n="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$STATE_DIR/memory_state.json" 2>/dev/null || echo 0)"
  # NB: `is-enabled` prints "disabled" AND exits 1 → a `|| echo unknown` would append a 2nd
  # line and break the JSON. Capture stdout only, default to "unknown" if empty.
  ten="$(_uctl is-enabled "$TIMER")"; ten="${ten:-unknown}"
  tac="$(_uctl is-active "$TIMER")"; tac="${tac:-unknown}"
  qpts=null; qok=false
  if [ -n "$QURL" ]; then
    local r; r="$(curl -s --max-time 8 -H "api-key: $QKEY" "$QURL/collections/$COLL" 2>/dev/null || true)"
    if [ -n "$r" ]; then qpts="$(printf '%s' "$r" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("result",{}).get("points_count","null"))' 2>/dev/null || echo null)"; [ "$qpts" != null ] && qok=true; fi
  fi
  printf '{"last_run_ts":"%s","age_seconds":%s,"spool_depth":%s,"lock_pid":"%s","lock_alive":%s,"state_entries":%s,"qdrant_points":%s,"qdrant_reachable":%s,"timer_enabled":"%s","timer_active":"%s"}\n' \
    "$last_ts" "${age}" "${spool:-0}" "$lp" "$alive" "${state_n:-0}" "${qpts}" "$qok" "$ten" "$tac"
}

cmd_start() { _uctl enable --now "$TIMER" && echo "OK: timer enabled+started"; }
cmd_stop()  { _uctl disable --now "$TIMER" && echo "OK: timer disabled"; }
cmd_run()   { _uctl start "$SERVICE" && echo "OK: one-shot run launched"; }
cmd_fix() {
  local lp removed=no; lp="$(_lock_pid)"
  if [ -n "$lp" ] && ! _pid_alive "$lp"; then rm -f "$LOCK" && removed=yes; fi
  _uctl start "$SERVICE" >/dev/null 2>&1 || true
  echo "OK: stale_lock_removed=$removed (pid=$lp); run triggered to drain spool"
}

case "${1:-}" in
  status) cmd_status ;;
  start)  cmd_start  ;;
  stop)   cmd_stop   ;;
  run)    cmd_run    ;;
  fix)    cmd_fix    ;;
  *) echo "usage: memctl {status|start|stop|run|fix}" >&2; exit 2 ;;
esac
```

- [ ] **Step 4: Run → PASS**

```bash
chmod +x roles/llamaindex-memory-worker/files/memctl.sh roles/llamaindex-memory-worker/tests/run.sh
bash roles/llamaindex-memory-worker/tests/test_memctl.sh
bash -n roles/llamaindex-memory-worker/files/memctl.sh && echo "syntax OK"
```
Expected: `test_memctl PASS`, `syntax OK`.

- [ ] **Step 5: Commit**

```bash
git add roles/llamaindex-memory-worker/files/memctl.sh roles/llamaindex-memory-worker/tests/test_memctl.sh roles/llamaindex-memory-worker/tests/run.sh
git commit -m "feat(memory-worker): memctl.sh — sudo-free action surface (status/start/stop/run/fix)"
```

---

### Task 4: `memory-bot.py` — Telegram front + test

**Files:** Create `roles/llamaindex-memory-worker/files/memory-bot.py`, `roles/llamaindex-memory-worker/tests/test_memory_bot.py`

- [ ] **Step 1: Write the failing test** (dispatch + auth, mock memctl + Telegram)

```python
# roles/llamaindex-memory-worker/tests/test_memory_bot.py
import importlib.util, os, sys
from pathlib import Path
BOT = Path(__file__).parent.parent / "files" / "memory-bot.py"
spec = importlib.util.spec_from_file_location("memory_bot", BOT)
mb = importlib.util.module_from_spec(spec); spec.loader.exec_module(mb)

calls = []
mb.run_memctl = lambda action: (calls.append(action) or f"OK:{action}")  # stub
replies = []
mb.send_message = lambda chat_id, text: replies.append((chat_id, text))   # stub

OWNER = 4242
def upd(text, chat=OWNER):
    return {"message": {"chat": {"id": chat}, "text": text}}

def run(label, cond): print(("  ok: " if cond else "  FAIL: ")+label); 
fails = 0
def check(label, cond):
    global fails
    print(("  ok: " if cond else "  FAIL: ")+label)
    if not cond: fails = 1

# authorized /mem_status → memctl status called + reply sent
calls.clear(); replies.clear()
mb.handle_update(upd("/mem_status"), owner_chat_id=OWNER)
check("authorized /mem_status dispatches status", calls == ["status"])
check("authorized command replies", len(replies) == 1 and replies[0][0] == OWNER)

# /mem_start /mem_stop /mem_run /mem_fix map correctly
for c, a in [("/mem_start","start"),("/mem_stop","stop"),("/mem_run","run"),("/mem_fix","fix")]:
    calls.clear(); mb.handle_update(upd(c), owner_chat_id=OWNER)
    check(f"{c} -> memctl {a}", calls == [a])

# foreign chat id → ignored (no memctl, no reply)
calls.clear(); replies.clear()
mb.handle_update(upd("/mem_status", chat=9999), owner_chat_id=OWNER)
check("foreign chat ignored (no dispatch)", calls == [] and replies == [])

# unknown command → no dispatch, polite reply (optional) but never memctl
calls.clear()
mb.handle_update(upd("/hello"), owner_chat_id=OWNER)
check("unknown command does not dispatch memctl", calls == [])

print("test_memory_bot PASS" if fails == 0 else "test_memory_bot FAIL"); sys.exit(fails)
```

- [ ] **Step 2: Run → FAIL** (module not found)

```bash
python3 roles/llamaindex-memory-worker/tests/test_memory_bot.py
```

- [ ] **Step 3: Implement `roles/llamaindex-memory-worker/files/memory-bot.py`** (stdlib only)

```python
#!/usr/bin/env python3
"""memory-bot.py — Telegram long-poll front for memctl. stdlib only.
Auth: only OWNER_CHAT_ID is honored. Reaches api.telegram.org outbound (no VPN).
Config via env: TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID, MEMCTL_PATH."""
import json, os, subprocess, sys, time, urllib.parse, urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER = int(os.environ.get("TELEGRAM_OWNER_CHAT_ID", "0") or "0")
MEMCTL = os.environ.get("MEMCTL_PATH", "/opt/workstation/ai-memory-worker/memctl.sh")
API = f"https://api.telegram.org/bot{TOKEN}"
CMD_MAP = {"/mem_status": "status", "/mem_start": "start", "/mem_stop": "stop",
           "/mem_run": "run", "/mem_fix": "fix"}

def _api(method, params, timeout=70):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"{API}/{method}", data=data, timeout=timeout) as r:
        return json.loads(r.read().decode())

def send_message(chat_id, text):
    try: _api("sendMessage", {"chat_id": chat_id, "text": text[:4000]}, timeout=20)
    except Exception as e: print(f"sendMessage failed: {e}", file=sys.stderr)

def run_memctl(action):
    try:
        out = subprocess.run(["bash", MEMCTL, action], capture_output=True, text=True, timeout=120)
        return (out.stdout or out.stderr or "(no output)").strip()
    except Exception as e:
        return f"memctl {action} error: {e}"

def _format(action, raw):
    if action != "status": return raw
    try:
        d = json.loads(raw); age = d.get("age_seconds", -1)
        agetxt = "jamais" if age < 0 else f"{age//60}min"
        return ("📊 memory-worker\n"
                f"dernier run: {agetxt} | spool: {d.get('spool_depth')}\n"
                f"lock: pid={d.get('lock_pid') or '-'} alive={d.get('lock_alive')}\n"
                f"qdrant: {d.get('qdrant_points')} pts (joignable={d.get('qdrant_reachable')})\n"
                f"timer: {d.get('timer_enabled')}/{d.get('timer_active')}")
    except Exception:
        return raw

def handle_update(update, owner_chat_id=OWNER):
    msg = (update or {}).get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip().split()[0] if msg.get("text") else ""
    if chat != owner_chat_id:
        print(f"ignored message from chat {chat}", file=sys.stderr); return
    action = CMD_MAP.get(text)
    if not action:
        send_message(chat, "Commandes: /mem_status /mem_start /mem_stop /mem_run /mem_fix"); return
    raw = run_memctl(action)
    send_message(chat, _format(action, raw))

def main():
    if not TOKEN or not OWNER:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_CHAT_ID missing", file=sys.stderr); sys.exit(1)
    offset = 0; backoff = 1
    while True:
        try:
            res = _api("getUpdates", {"offset": offset, "timeout": 50}, timeout=70)
            backoff = 1
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                try: handle_update(u, OWNER)
                except Exception as e: print(f"handle error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"poll error: {e}; backoff {backoff}s", file=sys.stderr)
            time.sleep(backoff); backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run → PASS**

```bash
python3 roles/llamaindex-memory-worker/tests/test_memory_bot.py
python3 -c "import ast; ast.parse(open('roles/llamaindex-memory-worker/files/memory-bot.py').read()); print('syntax OK')"
```

- [ ] **Step 5: Commit**

```bash
git add roles/llamaindex-memory-worker/files/memory-bot.py roles/llamaindex-memory-worker/tests/test_memory_bot.py
git commit -m "feat(memory-worker): memory-bot.py — Telegram long-poll front, chat-id auth (stdlib)"
```

---

### Task 5: systemd user-unit templates

**Files:** Create `templates/memory-worker.service.user.j2`, `templates/memory-worker.timer.user.j2`, `templates/memory-bot.service.user.j2`

- [ ] **Step 1: Create the worker service (user variant)** — same as system service MINUS `User=`/`Group=`, `WantedBy=default.target`:

```ini
[Unit]
Description=LlamaIndex memory worker (user)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={{ memory_worker_install_dir }}
EnvironmentFile={{ memory_worker_env_file }}
ExecStartPre={{ memory_worker_wait_calm_script }}
ExecStart={{ memory_worker_run_report_script }} --mode {{ memory_worker_index_mode }}
Nice=19
IOSchedulingClass=idle

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Create the timer (user variant)**:

```ini
[Unit]
Description=Run LlamaIndex memory worker on schedule (user)

[Timer]
OnBootSec={{ memory_worker_timer_on_boot_sec }}
OnUnitActiveSec={{ memory_worker_timer_on_unit_active_sec }}
Unit=llamaindex-memory-worker.service
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Create the bot service**:

```ini
[Unit]
Description=memory-worker Telegram control bot (user)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={{ memory_worker_install_dir }}
EnvironmentFile={{ memory_worker_env_file }}
Environment=MEMCTL_PATH={{ memory_worker_install_dir }}/memctl.sh
Environment=MEMCTL_QDRANT_URL={{ memory_worker_qdrant_url }}
Environment=MEMCTL_COLLECTION={{ memory_worker_collection_name }}
ExecStart={{ memory_worker_venv_dir }}/bin/python {{ memory_worker_install_dir }}/memory-bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

- [ ] **Step 4: Validate the templates render** (placeholder substitution → valid ini-ish):

```bash
for t in memory-worker.service.user memory-worker.timer.user memory-bot.service.user; do
  grep -q '\[Service\]\|\[Timer\]' roles/llamaindex-memory-worker/templates/$t.j2 && echo "$t OK"; done
```

- [ ] **Step 5: Commit**

```bash
git add roles/llamaindex-memory-worker/templates/memory-worker.service.user.j2 roles/llamaindex-memory-worker/templates/memory-worker.timer.user.j2 roles/llamaindex-memory-worker/templates/memory-bot.service.user.j2
git commit -m "feat(memory-worker): systemd user-unit templates (worker + timer + bot)"
```

---

### Task 6: Ansible tasks — migration system→user + deploy + handlers

**Files:** Modify `roles/llamaindex-memory-worker/tasks/main.yml`, `roles/llamaindex-memory-worker/handlers/main.yml`

- [ ] **Step 1: Reconcile the EXISTING role (mandatory — else deploy breaks).** Read the current `tasks/main.yml` line-by-line and apply:
  - **DELETE** the 3 system-unit tasks: `Deploy memory worker systemd service` (~l.160-171), `Deploy memory worker systemd timer` (~l.172-183), `Enable and start memory worker timer` (~l.195-202). They re-create the units Step 2 removes → double-unit + breaks idempotence. The user-unit tasks (Steps 5-6) replace them.
  - **REWRITE the 7 `notify: Restart llamaindex-memory-worker timer`** references (the system handler is being removed → a dangling notify errors by default):
    - `Deploy memory worker environment file` (~l.62) → `notify: Restart memory-bot (user)` (the bot reads `TELEGRAM_BOT_TOKEN` from this env at start).
    - `Deploy config.yml` (~l.72), `Deploy run-and-report.sh` (~l.136), `Deploy memory-wait-calm.sh` (~l.146), `Deploy webhook secret` (~l.158) → **remove the `notify:`** (these are read at the next worker run; no restart needed).
    - The 2 on the deleted unit tasks (l.170, l.182) disappear with the tasks.
  - **ADD `tags: [llamaindex-memory-worker, memory_remote]`** to the EXISTING `Deploy memory worker environment file` (~l.53), `Deploy memory worker index script` (~l.83), and `Verify memory worker script imports` (~l.184-193) tasks — otherwise `--tags memory_remote` skips the two most important changes (Telegram token + lock hardening) AND the py_compile gate.
  - In `handlers/main.yml`: rename the existing `Reload systemd` → `Reload systemd (system)` (still used by the legacy-file removal task) and keep it; **DELETE the now-unreferenced `Restart llamaindex-memory-worker timer` handler (~l.9-15)** — after the 7 notify rewrites nothing notifies it (dead handler). The user-scoped handlers are added in Step 7.

- [ ] **Step 1b: Add XDG anchor** — resolve uid (default `memory_worker_uid: 1000`, or `getent`); all `systemctl --user` tasks use `become_user: "{{ memory_worker_user }}"` + `environment: { XDG_RUNTIME_DIR: "/run/user/{{ memory_worker_uid }}" }`.

- [ ] **Step 2: Uninstall the SYSTEM units FIRST** (before installing user units — avoids double-active):

```yaml
- name: Disable + stop legacy system units
  ansible.builtin.systemd:
    name: "{{ item }}"
    state: stopped
    enabled: false
  become: true
  failed_when: false      # absent on fresh install is fine
  loop:
    - llamaindex-memory-worker.timer
    - llamaindex-memory-worker.service
  tags: [llamaindex-memory-worker, memory_remote]

- name: Remove legacy system unit files
  ansible.builtin.file:
    path: "/etc/systemd/system/{{ item }}"
    state: absent
  become: true
  loop:
    - llamaindex-memory-worker.service
    - llamaindex-memory-worker.timer
  notify: Reload systemd (system)
  tags: [llamaindex-memory-worker, memory_remote]
```

- [ ] **Step 3: Enable linger** (root, one-time, idempotent):

```yaml
- name: Enable linger for {{ memory_worker_user }} (user units run without login)
  ansible.builtin.command: "loginctl enable-linger {{ memory_worker_user }}"
  become: true
  args:
    creates: "/var/lib/systemd/linger/{{ memory_worker_user }}"
  tags: [llamaindex-memory-worker, memory_remote]
```

- [ ] **Step 4: Deploy memctl.sh + memory-bot.py** (static files, copy, owned by mobuone):

```yaml
- name: Deploy memctl.sh
  ansible.builtin.copy:
    src: memctl.sh
    dest: "{{ memory_worker_install_dir }}/memctl.sh"
    owner: "{{ memory_worker_user }}"
    group: "{{ memory_worker_user }}"
    mode: "0755"
  become: true
  tags: [llamaindex-memory-worker, memory_remote]

- name: Deploy memory-bot.py
  ansible.builtin.copy:
    src: memory-bot.py
    dest: "{{ memory_worker_install_dir }}/memory-bot.py"
    owner: "{{ memory_worker_user }}"
    group: "{{ memory_worker_user }}"
    mode: "0755"
  become: true
  notify: Restart memory-bot (user)
  tags: [llamaindex-memory-worker, memory_remote]
```

- [ ] **Step 5: Deploy user units** to `{{ memory_worker_user_unit_dir }}` (owned by mobuone, no root needed for the dir, but create it):

```yaml
- name: Ensure user systemd dir
  ansible.builtin.file:
    path: "{{ memory_worker_user_unit_dir }}"
    state: directory
    owner: "{{ memory_worker_user }}"
    group: "{{ memory_worker_user }}"
    mode: "0755"
  become: true
  tags: [llamaindex-memory-worker, memory_remote]

- name: Deploy user units
  ansible.builtin.template:
    src: "{{ item.src }}"
    dest: "{{ memory_worker_user_unit_dir }}/{{ item.dest }}"
    owner: "{{ memory_worker_user }}"
    group: "{{ memory_worker_user }}"
    mode: "0644"
  become: true
  loop:
    - { src: memory-worker.service.user.j2, dest: llamaindex-memory-worker.service }
    - { src: memory-worker.timer.user.j2,   dest: llamaindex-memory-worker.timer }
    - { src: memory-bot.service.user.j2,     dest: memory-bot.service }
  notify:
    - Reload systemd (user)
    - Restart memory-bot (user)
  tags: [llamaindex-memory-worker, memory_remote]
```

- [ ] **Step 6: daemon-reload + enable user units** (`--user`, with become_user + XDG):

```yaml
- name: Reload + enable user units
  ansible.builtin.systemd:
    name: "{{ item }}"
    scope: user
    enabled: true
    state: started
    daemon_reload: true
  become: true
  become_user: "{{ memory_worker_user }}"
  environment:
    XDG_RUNTIME_DIR: "/run/user/{{ memory_worker_uid }}"
  loop:
    - llamaindex-memory-worker.timer
    - memory-bot.service
  tags: [llamaindex-memory-worker, memory_remote]
```

> NB: `ansible.builtin.systemd` supports `scope: user` (ansible-core ≥2.13). If unavailable, fall back to `ansible.builtin.command: "systemctl --user ..."` with the same `become_user`+`environment`, `changed_when` set by parsing. Verify the installed ansible-core supports `scope`.

- [ ] **Step 7: Update handlers** — add user-scoped handlers to `handlers/main.yml`:

```yaml
- name: Reload systemd (system)
  ansible.builtin.systemd:
    daemon_reload: true
  become: true

- name: Reload systemd (user)
  ansible.builtin.systemd:
    daemon_reload: true
    scope: user
  become: true
  become_user: "{{ memory_worker_user }}"
  environment:
    XDG_RUNTIME_DIR: "/run/user/{{ memory_worker_uid }}"

- name: Restart memory-bot (user)
  ansible.builtin.systemd:
    name: memory-bot.service
    scope: user
    state: restarted
  become: true
  become_user: "{{ memory_worker_user }}"
  environment:
    XDG_RUNTIME_DIR: "/run/user/{{ memory_worker_uid }}"
  when: not ansible_check_mode
```

> Remove or supersede the old `Restart llamaindex-memory-worker timer` system handler usages (the env/config templates now notify the user-scoped restart). Reconcile the existing handler names referenced by the `.env`/`config.yml` deploy tasks (Task 2 / existing) so they point to user-scoped restarts.

- [ ] **Step 8: Lint**

```bash
cd /home/mobuone/VPAI && source .venv/bin/activate && make lint
```
Expected: pass (FQCN, no bare command without changed_when, etc.).

- [ ] **Step 9: Commit**

```bash
git add roles/llamaindex-memory-worker/tasks/main.yml roles/llamaindex-memory-worker/handlers/main.yml
git commit -m "feat(memory-worker): migrate to systemd-user units + deploy bot/memctl (sudo-free control)"
```

---

### Task 7: Deploy + live verification

- [ ] **Step 1: Run all role unit tests on waza**

```bash
bash roles/llamaindex-memory-worker/tests/run.sh
```
Expected: `ALL ROLE TESTS PASS`.

- [ ] **Step 2: Confirm vault secrets present** (human did Task 2 Step 4)

```bash
ansible-vault view inventory/group_vars/all/secrets.yml | grep -c vault_memory_worker_telegram
```
Expected: `2`. If 0 → STOP, ask the user to add them.

- [ ] **Step 3: Check-mode dry run**

```bash
source .venv/bin/activate
ansible-playbook playbooks/hosts/workstation.yml --tags memory_remote --check --diff
```
Review the diff: legacy system units removed, user units added, linger task, no unexpected changes.

- [ ] **Step 4: Deploy**

```bash
make deploy-workstation    # or: ansible-playbook playbooks/hosts/workstation.yml --tags memory_remote
```

- [ ] **Step 5: Verify live (no sudo)**

```bash
export XDG_RUNTIME_DIR=/run/user/1000
systemctl --user is-active memory-bot.service          # expect: active
systemctl --user is-enabled llamaindex-memory-worker.timer  # expect: enabled
ls /etc/systemd/system/llamaindex-memory-worker.* 2>&1 # expect: no such file (system units gone)
# memctl reads QDRANT_URL from the env file (injected via systemd EnvironmentFile at service runtime);
# in a plain shell, source it first so qdrant_reachable reflects reality:
set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
/opt/workstation/ai-memory-worker/memctl.sh status     # expect: JSON snapshot, qdrant_reachable true
```

- [ ] **Step 6: Verify idempotence** (2nd deploy = 0 changed)

```bash
ansible-playbook playbooks/hosts/workstation.yml --tags memory_remote | tail -3
```
Expected: `changed=0` in the recap.

- [ ] **Step 7: End-to-end from iPhone** (human): send `/mem_status` to the bot → expect the formatted snapshot reply. Then `/mem_start` → timer enabled; `/mem_run` → a run launches (drains spool); `/mem_status` → spool drops, age resets.

- [ ] **Step 8: Final commit** (if any tweaks)

```bash
git add -A roles/llamaindex-memory-worker/ && git commit -m "chore(memory-worker): post-deploy verification tweaks" || echo "nothing to commit"
```

---

## Done-Definition
- [ ] `bash roles/llamaindex-memory-worker/tests/run.sh` → ALL ROLE TESTS PASS (lock, memctl, bot).
- [ ] `make lint` passes.
- [ ] Deploy succeeds; system units gone; user units active+enabled; linger on.
- [ ] `memctl status` returns a live JSON snapshot (qdrant reachable).
- [ ] iPhone: all 5 commands work; foreign chat-ids ignored.
- [ ] 2nd deploy = `changed=0` (idempotent).
- [ ] `index.py` stale-lock auto-reclaim verified (the 6-week dormancy cause is fixed).

## Rollback
Per-commit `git revert` (atomic). Re-deploy reinstalls. To fully revert the unit migration: re-add system unit templates + tasks (kept in git history) and `systemctl --user disable` the user units + `loginctl disable-linger`. The bot is independent — disabling `memory-bot.service` removes remote control without touching ingestion.

## Out of scope (tracked)
- Dead-man's switch n8n alert (absence-of-report) + Grafana dashboard.
- MCP `memory_ops` for Claude (Claude calls `memctl` directly).
- iOS Shortcut transport (memctl already supports it).
- Pipeline-level improvements (hybrid search, chunk-level diff, VPAI re-index).
